from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import settings
from .build.excel import Row, Schema, load_schema, write_rows
from .extract import text
from .extract.pdf_reader import PdfDocument, ocr_available, read_pdf
from .extract.text import detect, folder_name
from .mapping import memory
from .mapping.matcher import Matcher
from .mapping.memory import Profile, ProfileStore

# Flow: read PDF -> detect company -> group -> one Excel per company,
# written into that company's own folder.

@dataclass
class PdfResult:
    path: Path
    document: PdfDocument | None = None
    company: str | None = None
    confidence: float = 0.0
    level: str = "undetected"
    row: Row | None = None
    warnings: list[str] = field(default_factory=list)
    skipped: str | None = None
    destination: Path | None = None


@dataclass
class ProcessResult:
    started: datetime = field(default_factory=datetime.now)
    pdfs: list[PdfResult] = field(default_factory=list)
    excel_files: list[dict] = field(default_factory=list)
    new_companies: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> list[PdfResult]:
        return [h for h in self.pdfs if h.row is not None]

    @property
    def needs_review(self) -> list[PdfResult]:
        return [h for h in self.pdfs if h.warnings and h.skipped is None]

    @property
    def failed(self) -> list[PdfResult]:
        return [h for h in self.pdfs if h.skipped]


def _format_value(column: str, raw):
    if column in ("B", "S"):
        d = text.parse_date(raw)
        return text.format_date(d) or text.clean_text(raw, 40)
    if column in ("C", "T"):
        return text.parse_time(raw) or text.clean_text(raw, 20)
    if column == "Z":
        return text.parse_postal_code(raw) or text.clean_text(raw, 10)
    if column == "AQ":
        return text.parse_money(raw)
    if column == "BT":
        return text.parse_percent(raw)
    return text.clean_text(raw)


def _build_row(doc: PdfDocument, profile: Profile, matcher: Matcher,
               schema: Schema) -> tuple[Row, list[str]]:
    b = Row(source=doc.path.name)
    remarks: list[str] = []

    for param, raw in doc.key_value_pairs().items():
        column = profile.column_for(param)
        if column is None:
            c = matcher.match(param)
            if c.accepted:
                profile.remember_parameter(param, c.column, c.method, c.score)
                column = c.column
                if c.needs_review:
                    remarks.append(
                        f"'{param}' dipetakan ke {c.column} ({c.header}) lewat "
                        f"analisis makna dengan skor {c.score:.2f} - mohon dicek")
            else:
                profile.remember_unmatched(param, c.reason)
                continue
        if column in b.values:
            continue  # first occurrence wins
        value = _format_value(column, raw)
        if value is not None and value != "":
            b.values[column] = value

    # Reported Name is the insured, already settled during detection from the
    # "Insured Name" / "Name of Insured" label. Overwritten here because the
    # matcher often grabs some other party -- most often Astra Buana itself.
    b.values[settings.INSURED_NAME_COLUMN] = profile.official_name

    if settings.LETTER_DATE_COLUMN:
        d, city, _ = text.letter_footer_date(doc.text)
        if d:
            b.values.setdefault(
                settings.LETTER_DATE_COLUMN,
                text.format_date(d, settings.LETTER_DATE_FORMAT))
            if city:
                b.values.setdefault("AA", city)

    policy = b.values.get("D")
    if policy and policy in settings.SHARE_BY_POLICY:
        share = settings.SHARE_BY_POLICY[policy]
        b.values["BT"] = f"{share * 100:g}%"
        b.values["_aab_share"] = f"{share * 100:g}%"

    for k in schema.match_targets:
        if k.letter in settings.DEFERRED_COLUMNS:
            continue
        if k.letter not in b.values:
            b.values[k.letter] = (
                f"N/A: tidak ada parameter yang cocok di PDF untuk '{k.clean_name}'")

    b.warnings = remarks
    return b, remarks

def run(
    *,
    operator_email: str,
    input_folder: Path,
    progress=None,
) -> ProcessResult:
    def _report(message: str):
        if progress:
            progress(message)

    settings.ensure_folders()
    result = ProcessResult()
    schema = load_schema()
    matcher = Matcher(schema)
    store = ProfileStore()

    result.notes.append(f"Jalur analisis makna: {matcher.mode}")
    if not ocr_available():
        result.notes.append(
            "OCR belum terpasang")

    pdf_files = memory.list_pdfs(input_folder)
    if not pdf_files:
        result.notes.append(f"Tidak ada PDF di {input_folder}")
        return result

    groups: dict[str, list[PdfResult]] = {}
    for p in pdf_files:
        _report(f"Membaca {p.name}")
        h = PdfResult(path=p)
        h.document = read_pdf(p)
        h.warnings.extend(h.document.warnings)

        if h.document.error:
            h.skipped = h.document.error
            result.pdfs.append(h)
            continue

        d = detect(h.document.lines, file_name=p.name)
        h.company, h.confidence, h.level = d.name, d.confidence, d.level
        h.warnings.extend(d.warnings)
        result.pdfs.append(h)

        if d.level == "undetected":
            continue
        profile, is_new = store.get_or_create(d.name)
        if is_new:
            result.new_companies.append(profile.official_name)
        groups.setdefault(profile.key, []).append(h)

    stamp = result.started.strftime("%Y%m%d")
    for members in groups.values():
        profile = store.find(members[0].company)
        _report(f"Menyusun {profile.official_name} ({len(members)} PDF)")
        folder = memory.company_folder(profile.group, profile.folder)
        pdf_folder = folder / settings.PDF_SUBFOLDER

        rows: list[Row] = []
        for h in members:
            b, remarks = _build_row(h.document, profile, matcher, schema)
            ref = b.values.get(settings.UNIQUE_REF_COLUMN)
            is_new = ref and not str(ref).startswith("N/A")
            if is_new and ref in profile.processed_refs:
                h.skipped = f"sudah pernah diproses (ref {ref})"
                h.destination = memory.move_pdf(h.path, pdf_folder, reason="duplikat")
                continue
            if is_new:
                profile.processed_refs.append(str(ref))
            h.row = b
            h.warnings.extend(remarks)
            rows.append(b)

        if rows:
            excel_name = f"{folder_name(profile.official_name)}_{stamp}.xlsx"
            summary = write_rows(rows, folder / excel_name,
                                 operator_email=operator_email, schema=schema)
            summary["company"] = profile.official_name
            if not summary["dropdowns_intact"]:
                result.notes.append(
                    f"{profile.official_name}: dropdown tidak utuh "
                    f"({summary['dropdowns_after']}/{summary['dropdowns_before']})")
            result.excel_files.append(summary)

        for h in members:
            if h.destination is None:
                h.destination = memory.move_pdf(
                    h.path, pdf_folder,
                    reason=f"{profile.official_name} (keyakinan {h.confidence:.2f})")
        profile.pdf_count += len(rows)
        store.save(profile)

    for h in result.pdfs:
        if h.destination is None and h.path.exists():
            h.destination = memory.move_pdf(
                h.path, memory.undetected_folder(),
                reason=h.skipped or "perusahaan tidak terdeteksi")

    write_report(result)
    return result


def write_report(result: ProcessResult) -> Path:
    f = settings.OUTPUT_DIR / f"_LAPORAN_{result.started:%Y%m%d_%H%M%S}.txt"
    f.parent.mkdir(parents=True, exist_ok=True)

    b: list[str] = []
    b.append("LAPORAN PROSES OTOMASI PDF -> EXCEL")
    b.append(f"Waktu   : {result.started:%Y-%m-%d %H:%M:%S}")
    b.append(f"Total   : {len(result.pdfs)} PDF | berhasil {len(result.succeeded)} | "
             f"dilewati {len(result.failed)} | perlu ditinjau {len(result.needs_review)}")
    b.append("")
    for c in result.notes:
        b.append(f"CATATAN: {c}")
    if result.new_companies:
        b.append("")
        b.append("PERUSAHAAN BARU (profil memory dibuat):")
        b += [f"  - {n}" for n in result.new_companies]
    if result.excel_files:
        b.append("")
        b.append("FILE EXCEL YANG DIHASILKAN:")
        for e in result.excel_files:
            utuh = "dropdown utuh" if e["dropdowns_intact"] else "DROPDOWN RUSAK"
            b.append(f"  - {e['company']}: {e['rows']} baris, {utuh}")
            b.append(f"    {e['file']}")
    if result.needs_review:
        b.append("")
        b.append("PERLU DITINJAU:")
        for h in result.needs_review:
            b.append(f"  - {h.path.name} (perusahaan: {h.company or '-'}, "
                     f"keyakinan {h.confidence:.2f})")
            b += [f"      ! {w}" for w in h.warnings]
    if result.failed:
        b.append("")
        b.append("DILEWATI:")
        b += [f"  - {h.path.name}: {h.skipped}" for h in result.failed]

    f.write_text("\n".join(b), encoding="utf-8")
    return f
