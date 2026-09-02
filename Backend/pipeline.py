from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

from . import profiles
from .build import excelGenerator
from .extract import parser, pdf_reader
from .profiles import Profile

SOURCE_COLUMN = "Sumber PDF"


@dataclass
class FileResult:
    path: Path
    ok: bool = False
    reason: str = ""
    values: list[str] = field(default_factory=list)
    from_ocr: bool = False
    note: str = ""
    missing: list[str] = field(default_factory=list)   # columns the letter lacks
    extra: dict[str, str] = field(default_factory=dict)  # labels the profile ignores

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class BatchResult:
    profile: Profile | None = None
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    files: list[FileResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    rejected: str = ""
    excel_path: Path | None = None

    @property
    def done(self) -> list[FileResult]:
        return [f for f in self.files if f.ok]

    @property
    def skipped(self) -> list[FileResult]:
        return [f for f in self.files if not f.ok]

    @property
    def deviating(self) -> list[FileResult]:
        return [f for f in self.files if f.ok and (f.missing or f.extra)]

    @property
    def scanned(self) -> list[FileResult]:
        return [f for f in self.files if f.ok and f.from_ocr]

    @property
    def noted(self) -> list[FileResult]:
        return [f for f in self.files if f.ok and f.note]


def _sections_merged(document) -> dict[str, str]:
    """Every label in the file, for working out which company it is from."""
    found: dict[str, str] = {}
    for page in document.pages:
        found.update(parser.pairs(page.lines, bulleted_money=True))
    return found


def _sections(document, profile: Profile | None) -> list[dict[str, str]]:
    """Each advice in the file as its own set of label:value pairs.

    One file can carry the same DLA reissued for every reinsurer on the risk,
    each with a different share. A page that does not carry the owner label is
    treated as a continuation of the advice above it.
    """
    skip = profile.skip_headings if profile else ()
    owner = profile.owner_label if profile else ""
    out: list[dict[str, str]] = []
    for page in document.pages:
        if any(h.casefold() in skip for h in page.headings()):
            continue
        found = parser.pairs(
            page.lines,
            split_shared_lines=profile.split_shared_lines if profile else False,
            bulleted_money=profile.bulleted_money if profile else True,
        )
        if not found:
            continue
        if out and (not owner or owner not in found):
            out[-1].update(found)
        else:
            out.append(found)
    return out


def _labels_of(document, profile: Profile | None) -> tuple[dict[str, str], str]:
    """The one advice that is ours, plus a note when there was a choice to make.

    Merging every page into one bag lets the last advice win, and that is how a
    Tugure share of 1% once landed on a row that should have carried Astra
    Buana's 6%. When several advices sit in one file, the one addressed to us is
    the one taken -- and if that cannot be told apart, nothing is taken at all.
    """
    sections = _sections(document, profile)
    if not sections:
        return {}, ""
    if len(sections) == 1:
        return sections[0], ""

    label = profile.owner_label if profile else ""
    names = profile.owner_names if profile else ()
    if not label or not names:
        raise ValueError(f"berkas memuat {len(sections)} DLA, dan profil "
                         f"belum tahu mana yang milik kita")

    mine = [s for s in sections
            if any(n in (s.get(label, "") or "").casefold() for n in names)]
    others = [s.get(label, "?") for s in sections if s not in mine]
    if len(mine) != 1:
        raise ValueError(
            f"berkas memuat {len(sections)} DLA untuk reasuradur berbeda "
            f"({', '.join(s.get(label, '?') for s in sections)}), dan "
            f"{'tidak satu pun' if not mine else f'{len(mine)}'} ditujukan ke kita")
    return mine[0], (f"berkas memuat {len(sections)} DLA; diambil yang ditujukan ke "
                     f"{mine[0].get(label)}, sisanya dilewati ({', '.join(others)})")


def read_one(path: Path, profile: Profile) -> FileResult:
    result = FileResult(path=path)
    document = pdf_reader.read(path)
    if document.error:
        result.reason = document.error
        return result
    if not document.has_text:
        result.reason = ("tidak ada teks yang bisa dibaca - kemungkinan hasil "
                         "pindaian, perlu OCR")
        return result

    result.from_ocr = document.used_ocr
    try:
        found, note = _labels_of(document, profile)
    except ValueError as e:
        result.reason = str(e)
        return result
    result.note = note
    used = {c.source for c in profile.columns} | set(profile.ignore)
    for column in profile.columns:
        raw = found.get(column.source)
        if raw is None:
            result.missing.append(column.source)
            result.values.append("")
            continue
        result.values.append(profiles.TAKE[column.take](raw))
    result.extra = {k: v for k, v in found.items() if k not in used and v}
    result.ok = True
    return result


def run(paths, *, profile_key: str | None = None, progress=None) -> BatchResult:
    """Read a batch of one company's DLAs into a single sheet.

    Documents that do not carry exactly the parameters the profile expects are
    still read, and any unexpected label becomes a further column. Whether that
    is acceptable is not decided here -- the caller sees `deviating` and asks.
    """
    paths = [Path(p) for p in paths]
    batch = BatchResult()

    profile = profiles.by_key(profile_key) if profile_key else None
    if profile is None:
        profile = _detect(paths, batch)
        if profile is None:
            return batch
    batch.profile = profile

    for i, path in enumerate(paths, start=1):
        if progress:
            progress(i, len(paths), path.name)
        batch.files.append(read_one(path, profile))

    if not batch.done:
        batch.rejected = "Tidak ada satu pun PDF yang bisa dibaca."
        return batch

    extra_headers: list[str] = []
    for f in batch.done:
        for label in f.extra:
            if label not in extra_headers:
                extra_headers.append(label)

    batch.headers = [c.header for c in profile.columns] + extra_headers + [SOURCE_COLUMN]
    for f in batch.done:
        batch.rows.append(f.values + [f.extra.get(h, "") for h in extra_headers] + [f.name])

    if extra_headers:
        batch.notes.append(
            f"{len(extra_headers)} parameter di luar profil {profile.name} ikut "
            f"dimasukkan sebagai kolom tambahan: {', '.join(extra_headers)}.")
    if batch.scanned:
        batch.notes.append(
            f"{len(batch.scanned)} PDF tidak punya lapisan teks dan dibaca lewat OCR. "
            f"Huruf dan angkanya bisa salah baca tanpa terlihat keliru, jadi mohon "
            f"dicocokkan dengan dokumen aslinya.")
    blank = [f.name for f in batch.done if f.missing]
    if blank:
        batch.notes.append(
            f"{len(blank)} PDF tidak memuat sebagian parameter, selnya dikosongkan.")
    return batch


def _detect(paths: list[Path], batch: BatchResult) -> Profile | None:
    for path in paths:
        document = pdf_reader.read(path)
        if document.error or not document.has_text:
            continue
        found = profiles.detect(_sections_merged(document))
        if found:
            return found
    batch.rejected = (
        "Perusahaan tidak dikenali dari PDF yang diunggah. Saat ini baru "
        + ", ".join(p.name for p in profiles.ALL) + " yang didukung.")
    return None


def to_excel(batch: BatchResult, folder: Path, stem: str = "") -> Path | None:
    if not batch.rows:
        return None
    name = stem or (batch.profile.name if batch.profile else "DLA")
    batch.excel_path = excelGenerator.write(Path(folder) / f"{name}.xlsx", batch.headers, batch.rows)
    return batch.excel_path
