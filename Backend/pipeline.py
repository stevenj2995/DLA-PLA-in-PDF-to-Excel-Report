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
    total_dla: int = 0                 # advices found in this file, ours or not
    astra_dla: int = 0                 # 0 or 1: whether one of them was ours
    shape: tuple[str, ...] = ()        # labels this advice actually carried
    missing: list[str] = field(default_factory=list)   # columns the letter lacks
    extra: dict[str, str] = field(default_factory=dict)  # labels the profile ignores

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class Note:
    """One line for the results page, with the long list folded away behind it."""
    text: str
    detail: list[str] = field(default_factory=list)
    level: str = "info"          # info | warn


@dataclass
class Group:
    """One table: every advice here carried the same set of parameters."""
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    files: list[FileResult] = field(default_factory=list)
    caption: str = ""


@dataclass
class BatchResult:
    profile: Profile | None = None
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    files: list[FileResult] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
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

    @property
    def total_rows(self) -> int:
        return sum(len(g.rows) for g in self.groups)

    @property
    def total_dla(self) -> int:
        return sum(f.total_dla for f in self.files)

    @property
    def astra_dla(self) -> int:
        return sum(f.astra_dla for f in self.files)

    @property
    def other_dla(self) -> int:
        return self.total_dla - self.astra_dla


def _sections_merged(document) -> dict[str, str]:
    """Every label in the file, for working out which company it is from."""
    found: dict[str, str] = {}
    for page in document.pages:
        found.update(parser.pairs(page.lines, bulleted_money=True))
    return found


def _starts_advice(page, profile: Profile | None) -> bool:
    """Whether this page begins a new advice.

    The document's own title is the boundary. Counting pages and halving them
    would give the same answer on the files seen so far, but only because each
    advice happens to be one page plus one debit note -- an advice that runs to
    two pages, or one issued without a debit note, would throw that off.
    """
    if not profile or not profile.titles:
        return True
    headings = [h.casefold() for h in page.headings()]
    return any(title in h for title in profile.titles for h in headings)


def _sections(document, profile: Profile | None) -> list[dict[str, str]]:
    """Each advice in the file as its own set of label:value pairs.

    One file can carry the same DLA reissued for every reinsurer on the risk,
    each with a different share. Pages after a title belong to the advice that
    title opened, so an advice spanning several pages still comes back whole.
    """
    skip = profile.skip_headings if profile else ()
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
        if out and not _starts_advice(page, profile) and not _contradicts(out[-1], found, profile):
            out[-1].update(found)
        else:
            out.append(found)
    return out


def _contradicts(advice: dict, page: dict, profile: Profile | None) -> bool:
    """Whether this page restates what the advice above already said, differently.

    A continuation page adds fields; it does not disagree about them. When it
    disagrees, the page is really a new document whose title this profile does
    not recognise -- and merging it would quietly overwrite the advice above,
    which is exactly how a Tugure share once landed on an Astra row.

    This is the net under the title list: a document type nobody has told the
    profile about still gets split rather than silently blended.
    """
    owner = profile.owner_label if profile else ""
    if owner and owner in advice and owner in page:
        if (page[owner] or "").strip() != (advice[owner] or "").strip():
            return True
    clashes = sum(1 for k, v in page.items()
                  if k in advice and v and advice[k] and v.strip() != advice[k].strip())
    return clashes >= 2


def _labels_of(document, profile: Profile | None):
    """The one advice addressed to us, how many others sat beside it, and why
    none was picked when that happens.

    Returns (found, note, reason, total, other): `found` is None when nothing
    was picked, in which case `reason` explains it. `total` is how many advices
    the file held regardless of outcome, and `other` how many of those were not
    ours -- both needed to answer "how many DLA in total, how many for Astra".

    Whose advice it is gets checked however many the file holds. Trusting a
    lone advice without looking is what let files ending in REINS through: each
    held a single advice belonging to Tugure or Reasuransi Indonesia Utama, and
    nineteen of their rows reached the sheet as if they were ours.
    """
    sections = _sections(document, profile)
    total = len(sections)
    if not sections:
        return None, "", "tidak ditemukan DLA di berkas ini", 0, 0

    label = profile.owner_label if profile else ""
    names = profile.owner_names if profile else ()
    if not label or not names:
        if total == 1:
            return sections[0], "", "", 1, 0
        return None, "", (f"berkas memuat {total} DLA, dan profil belum tahu "
                          f"mana yang milik kita"), total, 0

    def addressee(section) -> str:
        return (section.get(label) or "?").strip()

    def is_ours(section) -> bool:
        return any(n in addressee(section).casefold() for n in names)

    mine = [s for s in sections if is_ours(s)]
    others = [addressee(s) for s in sections if not is_ours(s)]

    if len(mine) == 1:
        if not others:
            return mine[0], "", "", total, 0
        note = (f"berkas memuat {total} DLA; diambil yang ditujukan ke "
               f"{addressee(mine[0])}, sisanya dilewati ({', '.join(others)})")
        return mine[0], note, "", total, len(others)

    if not mine:
        named = [x for x in others if x != "?"]
        if not named:
            return None, "", (f"tidak ada baris '{label}' di berkas ini, jadi "
                              f"tidak bisa dipastikan DLA ini ditujukan ke "
                              f"siapa"), total, 0
        return None, "", (f"DLA di berkas ini ditujukan ke {', '.join(named)}, "
                          f"bukan ke kita"), total, total

    return None, "", (f"{len(mine)} DLA di berkas ini sama-sama ditujukan ke "
                      f"kita, tidak bisa ditentukan mana yang dipakai"), total, 0


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
    found, note, reason, total, other = _labels_of(document, profile)
    result.total_dla = total
    if found is None:
        result.reason = reason
        return result
    result.note = note
    result.astra_dla = 1
    used = {c.source for c in profile.columns} | set(profile.ignore)
    for column in profile.columns:
        raw = found.get(column.source)
        if raw is None:
            result.missing.append(column.source)
            result.values.append("")
            continue
        result.values.append(profiles.TAKE[column.take](raw))
    result.extra = {k: v for k, v in found.items() if k not in used and v}
    present = {c.source for c in profile.columns if c.source in found}
    result.shape = tuple(sorted(present | set(result.extra)))
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

    batch.groups = _grouped(batch.done, profile)
    if batch.groups:
        batch.headers = batch.groups[0].headers
        batch.rows = batch.groups[0].rows

    if len(batch.groups) > 1:
        batch.notes.append(Note(
            f"Hasilnya dipisah menjadi {len(batch.groups)} tabel dalam satu sheet, "
            f"karena parameter antar dokumen memang berbeda-beda.",
            [f"Tabel {i + 1}: {len(g.rows)} DLA, {len(g.headers) - 1} parameter"
             for i, g in enumerate(batch.groups)]))

    extras = sorted({k for f in batch.done for k in f.extra})
    if extras:
        batch.notes.append(Note(
            f"{len(extras)} parameter di luar profil {profile.name} ikut jadi kolom.",
            extras))

    if batch.noted:
        kita = profile.owner_names[0].title() if profile.owner_names else "kita"
        batch.notes.append(Note(
            f"{len(batch.noted)} berkas memuat lebih dari satu DLA. Yang diambil "
            f"selalu yang ditujukan ke {kita}.",
            [f"{f.name} - {f.note}" for f in batch.noted]))

    if batch.scanned:
        batch.notes.append(Note(
            f"{len(batch.scanned)} PDF dibaca lewat OCR karena tidak punya lapisan "
            f"teks. Huruf dan angkanya bisa salah baca tanpa terlihat keliru, jadi "
            f"mohon dicocokkan dengan dokumen aslinya.",
            [f.name for f in batch.scanned], level="warn"))

    blank = [f for f in batch.done if f.missing]
    if blank:
        batch.notes.append(Note(
            f"{len(blank)} PDF tidak memuat sebagian parameter, selnya dikosongkan.",
            [f"{f.name} - tidak ada: {', '.join(f.missing)}" for f in blank]))

    return batch


def _grouped(files: list[FileResult], profile: Profile) -> list[Group]:
    """Advices carrying the same parameters become one table.

    Forcing everything into a single table means the columns are the union of
    what every document had, so a document missing half of them contributes a
    row of blanks and the sheet becomes hard to read. Kept apart, each table is
    exactly as wide as the documents in it.
    """
    order: list[tuple[str, ...]] = []
    buckets: dict[tuple[str, ...], list[FileResult]] = {}
    for f in files:
        if f.shape not in buckets:
            buckets[f.shape] = []
            order.append(f.shape)
        buckets[f.shape].append(f)

    groups: list[Group] = []
    for shape in order:
        members = buckets[shape]
        keep = [i for i, c in enumerate(profile.columns) if c.source in shape]
        extras: list[str] = []
        for f in members:
            for label in f.extra:
                if label not in extras:
                    extras.append(label)
        headers = ([profile.columns[i].header for i in keep] + extras + [SOURCE_COLUMN])
        rows = [[f.values[i] for i in keep] + [f.extra.get(x, "") for x in extras] + [f.name]
                for f in members]
        groups.append(Group(headers=headers, rows=rows, files=members,
                            caption=f"{len(rows)} DLA - {len(headers) - 1} parameter"))

    # the widest table first, so the sheet opens on the main one
    groups.sort(key=lambda g: (-len(g.rows), -len(g.headers)))
    return groups


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
    if not batch.groups:
        return None
    name = stem or (batch.profile.name if batch.profile else "DLA")
    batch.excel_path = excelGenerator.write(Path(folder) / f"{name}.xlsx", batch.groups)
    return batch.excel_path
