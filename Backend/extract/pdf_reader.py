from __future__ import annotations
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from .. import settings

# Tesseract spreads one page across cores by itself, which leaves little for a
# second page to use. Holding it to one core each and running several pages side
# by side finishes a ten-page scan in half the time.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

LINE_TOLERANCE = 3.0

BORDER_ARTEFACTS = {"|", "!", "¦", "_", "—", "–", "l|", "||"}

_TESSERACT_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
)


def find_tesseract() -> str | None:
    if settings.TESSERACT_PATH and Path(settings.TESSERACT_PATH).exists():
        return settings.TESSERACT_PATH
    found = shutil.which("tesseract")
    if found:
        return found
    return next((p for p in _TESSERACT_CANDIDATES if p and Path(p).exists()), None)


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return find_tesseract() is not None


@dataclass
class Page:
    number: int
    lines: list[str] = field(default_factory=list)
    from_ocr: bool = False

    def headings(self, depth: int = 6) -> list[str]:
        """The first few printed lines. The document title is not always the
        first of them: OCR reads the letterhead logo as text, so a scanned JRP
        page starts with 'jasa raharja putera' where the digital one starts
        with 'DEBIT NOTE'."""
        found = [l.strip() for l in self.lines if l.strip()]
        return found[:depth]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass
class Document:
    path: Path
    pages: list[Page] = field(default_factory=list)
    error: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    @property
    def has_text(self) -> bool:
        return any(l.strip() for p in self.pages for l in p.lines)

    @property
    def used_ocr(self) -> bool:
        return any(p.from_ocr for p in self.pages)


def _bands_to_lines(words, tolerance: float) -> list[str]:
    lines: list[list[tuple[float, str]]] = []
    anchor = None
    for x, y, word in sorted(words, key=lambda w: w[1]):
        if anchor is None or abs(y - anchor) > tolerance:
            lines.append([])
            anchor = y
        lines[-1].append((x, word))
    return [" ".join(w for _, w in sorted(group)) for group in lines]


def _printed_lines(page) -> list[str]:
    words = [(x0, y0, w) for x0, y0, _x1, _y1, w, *_ in page.get_text("words")]
    return _bands_to_lines(words, LINE_TOLERANCE)


def _page_image(page):
    """The page as a greyscale image, without a PNG round trip.

    Encoding to PNG and decoding it back cost more than rendering the page in
    the first place. Greyscale is what Tesseract reduces the image to anyway,
    and it holds a third of the pixels of RGB.
    """
    from PIL import Image

    pix = page.get_pixmap(dpi=settings.OCR_DPI, colorspace=fitz.csGRAY)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def _read_image(image, exe: str) -> list[str]:
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = exe
    data = pytesseract.image_to_data(
        image, lang=settings.OCR_LANGUAGES,
        config=f"--psm {settings.OCR_PSM}", output_type=pytesseract.Output.DICT)
    words = []
    for i, text in enumerate(data["text"]):
        word = (text or "").strip()
        if not word or word in BORDER_ARTEFACTS:
            continue
        middle = float(data["top"][i]) + float(data["height"][i]) / 2.0
        words.append((float(data["left"][i]), middle, word))
    return _bands_to_lines(words, LINE_TOLERANCE * settings.OCR_DPI / 72.0)


def _ocr_pages(pdf, wanted: list[int], exe: str) -> dict[int, list[str]]:
    """Read the scanned pages, several at a time.

    Tesseract runs as a separate program, so the thread waiting on it holds no
    lock and the cores are genuinely used in parallel. Rendering stays on this
    thread because a PyMuPDF document must not be touched from several at once,
    and the pages are done in batches so only a handful of images are in memory.
    """
    out: dict[int, list[str]] = {}
    workers = max(1, min(settings.OCR_WORKERS, len(wanted)))
    for start in range(0, len(wanted), workers):
        batch = wanted[start:start + workers]
        images = {i: _page_image(pdf[i]) for i in batch}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            jobs = {i: pool.submit(_read_image, img, exe) for i, img in images.items()}
            for i, job in jobs.items():
                out[i] = job.result()
    return out


def read(path: str | Path, *, use_ocr: bool = True) -> Document:
    path = Path(path)
    document = Document(path=path)
    exe = find_tesseract() if use_ocr and ocr_available() else None
    try:
        with fitz.open(path) as pdf:
            printed: list[list[str]] = []
            scanned: list[int] = []
            for i, page in enumerate(pdf):
                lines = _printed_lines(page)
                printed.append(lines)
                if exe and sum(len(l.strip()) for l in lines) < settings.SCANNED_PAGE_CHARS:
                    scanned.append(i)

            read_back: dict[int, list[str]] = {}
            if scanned:
                try:
                    read_back = _ocr_pages(pdf, scanned, exe)
                except Exception as e:
                    document.error = f"OCR gagal: {e}"

            for i, lines in enumerate(printed):
                document.pages.append(
                    Page(i + 1, read_back.get(i, lines), from_ocr=i in read_back))
    except Exception as e:
        document.error = f"tidak bisa dibuka: {e}"
    return document
