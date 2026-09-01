from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from . import settings
from .build.excel import (Row, Schema, dropdown_values, load_schema, resolve_dropdown, write_rows)
from .extract import text
from .extract.pdf_reader import PdfDocument, ocr_available, read_pdf
from .extract.text import detect, folder_name
from .mapping import memory
from .mapping.matcher import Matcher
from .mapping.memory import Profile, ProfileStore

# Flow: read PDF -> detect company -> group -> one Excel per company, written into that company's own folder.

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


def _capped(items: list[str], limit: int = 10) -> list[str]:
    items = list(items or [])
    if len(items) <= limit:
        return items
    return items[:limit] + [f"... dan {len(items) - limit} lainnya"]

def _format_value(column: str, raw, param: str = ""):
    if column in ("B", "S"):
        return text.format_date(text.parse_date(raw))
    if column in ("C", "T"):
        return text.parse_time(raw)
    if column == "Z":
        return text.parse_postal_code(raw)
    if column == "AQ":
        amount = text.parse_money(raw)
        # anything negative is a deductible line that was read as the claim amount
        return None if amount is None or amount < 0 else amount
    if column == "BT":
        return text.parse_percent(raw) or text.parse_percent(param)
    return text.clean_text(raw)


def _currency_in(raw: str, allowed: dict[str, str]) -> str | None:
    for word in re.findall(r"\b[A-Za-z]{2,3}\b", raw or ""):
        key = word.casefold()
        if key == "rp":
            key = "idr"
        hit = allowed.get(key)
        if hit:
            return hit
    return None

_METHOD_WEIGHT = {"exact": 3.0, "dictionary": 2.0, "semantic": 1.0}

def _confidence(method: str, score: float) -> float:
    return _METHOD_WEIGHT.get(method, 0.0) + float(score)

def _build_row(doc: PdfDocument, profile: Profile, matcher: Matcher, 
               schema: Schema,
               lists: dict[str, dict[str, str]]) -> tuple[Row, list[str]]:
    b = Row(source=doc.path.name)
    remarks: list[str] = []
    header = {k.letter: k.clean_name for k in schema}
    best: dict[str, tuple[float, object]] = {}
    source_text: dict[str, str] = {}

    for param, raw in doc.key_value_pairs().items():
        known = profile.parameter_map.get(param)
        if known:
            column, method, score = known["column"], known["method"], known["score"]
        else:
            c = matcher.match(param)
            if not c.accepted:
                profile.remember_unmatched(param, c.reason)
                continue
            profile.remember_parameter(param, c.column, c.method, c.score)
            column, method, score = c.column, c.method, c.score
            if c.needs_review:
                remarks.append(
                    f"'{param}' dipetakan ke {c.column} ({c.header}) lewat "
                    f"analisis makna dengan skor {c.score:.2f} - mohon dicek")

        value = _format_value(column, raw, param)
        if value is None or value == "":
            continue

        allowed = None if column in settings.FREE_TEXT_COLUMNS else lists.get(column)
        if allowed and isinstance(value, str):
            fitted = resolve_dropdown(allowed, value)
            if fitted is not None:
                value = fitted
            elif text.parse_date(value) is not None:
                remarks.append(
                    f"'{param}' berisi tanggal ({value}) padahal kolom {column} "
                    f"({header.get(column)}) hanya menerima pilihan dari daftar "
                    f"- tidak ditulis")
                continue
            else:
                remarks.append(
                    f"{column} ({header.get(column)}): '{value}' tidak ada di "
                    f"daftar pilihan - mohon pilih manual di Excel")

        rank = _confidence(method, score)
        if column not in best or rank > best[column][0]:
            best[column] = (rank, value)
            source_text[column] = str(raw)

    b.values = {column: value for column, (_, value) in best.items()}

    if "AQ" not in b.values and "BT" in b.values:
        dasar = text.share_base(source_text.get("BT", ""))
        if dasar:
            b.values["AQ"] = dasar
            source_text["AQ"] = source_text.get("BT", "")

    if "AP" not in b.values and lists.get("AP"):
        code = _currency_in(source_text.get("AQ", ""), lists["AP"])
        if code:
            b.values["AP"] = code

    # a digit misread by OCR still looks like a normal amount, so it is flagged
    if doc.is_scanned:
        for column in settings.MONEY_COLUMNS:
            if b.values.get(column) is not None:
                remarks.append(
                    f"{column} ({header.get(column)}): {b.values[column]} dibaca dari "
                    f"halaman hasil pindaian - mohon cocokkan dengan angka di PDF")

    b.values[settings.INSURED_NAME_COLUMN] = profile.official_name

    ref = text.letter_reference(doc.lines)
    if ref:
        b.values[settings.UNIQUE_REF_COLUMN] = ref

    # Notification Date is the date the letter was sent
    if settings.LETTER_DATE_COLUMN:
        d, _city, _ = text.letter_footer_date("\n".join(doc.lines))
        if d:
            b.values.setdefault(
                settings.LETTER_DATE_COLUMN,
                text.format_date(d, settings.LETTER_DATE_FORMAT))

    policy = b.values.get("D")
    if policy and policy in settings.SHARE_BY_POLICY:
        b.values["BT"] = f"{settings.SHARE_BY_POLICY[policy] * 100:.2f}%"

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
    lists = dropdown_values(str(settings.template_file()))
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
            b, remarks = _build_row(h.document, profile, matcher, schema, lists)
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
            summary = write_rows(rows, folder / excel_name, operator_email=operator_email, schema=schema)
            summary["company"] = profile.official_name
            if not summary["dropdowns_intact"]:
                result.notes.append(
                    f"{profile.official_name}: dropdown tidak utuh "
                    f"({summary['dropdowns_after']}/{summary['dropdowns_before']})")
            if summary["invalid"]:
                result.notes.append(
                    f"{profile.official_name}: {len(summary['invalid'])} nilai di luar "
                    f"daftar pilihan - lihat laporan")
            if summary["mandatory_empty"]:
                result.notes.append(
                    f"{profile.official_name}: kolom wajib kosong di semua baris - "
                    + ", ".join(summary["mandatory_empty"]))
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
            h.destination = memory.move_pdf(h.path, memory.undetected_folder(), reason=h.skipped or "perusahaan tidak terdeteksi")

    write_report(result)
    return result

def write_report(result: ProcessResult) -> Path:
    f = settings.OUTPUT_DIR / f"_Laporan_{result.started:%Y%m%d_%H%M%S}.txt"
    f.parent.mkdir(parents=True, exist_ok=True)

    b: list[str] = []
    b.append("Laporan:")
    b.append(f"Waktu   : {result.started:%Y-%m-%d %H:%M:%S}")
    b.append(f"Total   : {len(result.pdfs)} PDF | berhasil {len(result.succeeded)} | "
             f"dilewati {len(result.failed)} | perlu dicek lagi {len(result.needs_review)}")
    b.append("")
    for c in result.notes:
        b.append(f"Notes: {c}")
    if result.new_companies:
        b.append("")
        b.append("New Company:")
        b += [f"  - {n}" for n in result.new_companies]
    if result.excel_files:
        b.append("")
        b.append("File Excel yang Dihasilkan:")
        for e in result.excel_files:
            utuh = "dropdown utuh" if e["dropdowns_intact"] else "DROPDOWN RUSAK"
            b.append(f"  - {e['company']}: {e['rows']} baris, {utuh}")
            b.append(f"    {e['file']}")
            for line in _capped(e.get("corrected")):
                b.append(f"      ~ disamakan dengan daftar: {line}")
            for line in _capped(e.get("invalid")):
                b.append(f"      ! di luar daftar pilihan: {line}")
            if e.get("mandatory_empty"):
                b.append("      ! kolom wajib kosong di semua baris: "
                         + ", ".join(e["mandatory_empty"]))
    if result.needs_review:
        b.append("")
        b.append("Perlu Dicek Lagi:")
        for h in result.needs_review:
            b.append(f"  - {h.path.name} (perusahaan: {h.company or '-'}, "
                     f"keyakinan {h.confidence:.2f})")
            b += [f"      ! {w}" for w in h.warnings]
    if result.failed:
        b.append("")
        b.append("Dilewati:")
        b += [f"  - {h.path.name}: {h.skipped}" for h in result.failed]

    f.write_text("\n".join(b), encoding="utf-8")
    return f
