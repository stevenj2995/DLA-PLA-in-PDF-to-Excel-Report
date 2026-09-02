from __future__ import annotations
import io
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from .. import settings

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


def _scanned_lines(page, exe: str) -> list[str]:
    import pytesseract
    from PIL import Image

    pytesseract.pytesseract.tesseract_cmd = exe
    dpi = settings.OCR_DPI
    pix = page.get_pixmap(dpi=dpi)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    data = pytesseract.image_to_data(image, lang=settings.OCR_LANGUAGES, config=f"--psm {settings.OCR_PSM}", output_type=pytesseract.Output.DICT)
    words = []
    for i, text in enumerate(data["text"]):
        word = (text or "").strip()
        if not word or word in BORDER_ARTEFACTS:
            continue
        middle = float(data["top"][i]) + float(data["height"][i]) / 2.0
        words.append((float(data["left"][i]), middle, word))
    return _bands_to_lines(words, LINE_TOLERANCE * dpi / 72.0)


def read(path: str | Path, *, use_ocr: bool = True) -> Document:
    path = Path(path)
    document = Document(path=path)
    exe = find_tesseract() if use_ocr else None
    try:
        with fitz.open(path) as pdf:
            for number, page in enumerate(pdf, start=1):
                lines = _printed_lines(page)
                thin = sum(len(l.strip()) for l in lines) < settings.SCANNED_PAGE_CHARS
                if thin and exe and ocr_available():
                    try:
                        lines = _scanned_lines(page, exe)
                        document.pages.append(Page(number, lines, from_ocr=True))
                        continue
                    except Exception as e:
                        document.error = f"OCR gagal di halaman {number}: {e}"
                document.pages.append(Page(number, lines))
    except Exception as e:
        document.error = f"tidak bisa dibuka: {e}"
    return document
