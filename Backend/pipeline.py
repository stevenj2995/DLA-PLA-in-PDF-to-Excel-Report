from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

from . import profiles, settings
from .build import excel
from .extract import parser, pdf_reader
from .profiles import Profile

SOURCE_COLUMN = "Sumber PDF"


@dataclass
class FileResult:
    path: Path
    ok: bool = False
    reason: str = ""
    values: list[str] = field(default_factory=list)
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


def _labels_of(document, profile: Profile | None) -> dict[str, str]:
    """Every label:value in the document, minus pages that are another document."""
    skip = profile.skip_headings if profile else ()
    found: dict[str, str] = {}
    for page in document.pages:
        heading = page.heading.strip().casefold()
        if any(heading == s for s in skip):
            continue
        found.update(parser.pairs(
            page.lines,
            split_shared_lines=profile.split_shared_lines if profile else False,
            bulleted_money=profile.bulleted_money if profile else True,
        ))
    return found


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

    found = _labels_of(document, profile)
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


def run(paths, *, profile_key: str | None = None, on_mismatch: str = "merge",
        progress=None) -> BatchResult:
    """Read a batch of one company's DLAs into a single sheet.

    on_mismatch decides what happens when a document does not carry exactly the
    parameters the profile expects: 'merge' keeps going, adding any unexpected
    label as a further column and leaving blanks where one is absent, while
    'reject' refuses the whole batch so it can be looked at.
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

    if on_mismatch == "reject" and batch.deviating:
        first = batch.deviating[0]
        batch.rejected = (
            f"{len(batch.deviating)} dari {len(batch.done)} PDF parameternya tidak "
            f"sama dengan yang lain, contohnya {first.name}. Batch ditolak sesuai "
            f"pilihan Anda.")
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
        found = profiles.detect(_labels_of(document, None))
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
    batch.excel_path = excel.write(Path(folder) / f"{name}.xlsx", batch.headers, batch.rows)
    return batch.excel_path
