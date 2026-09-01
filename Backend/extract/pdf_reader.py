from __future__ import annotations
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
import fitz
import io
import pytesseract
from PIL import Image
from .. import settings

_TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]


def find_tesseract() -> str | None:
    if settings.TESSERACT_PATH and Path(settings.TESSERACT_PATH).exists():
        return settings.TESSERACT_PATH
    found = shutil.which("tesseract")
    if found:
        return found
    for p in _TESSERACT_CANDIDATES:
        if p and Path(p).exists():
            return p
    return None


def ocr_available() -> bool:
    return find_tesseract() is not None


@dataclass
class Page:
    number: int
    text: str = ""
    lines: list[str] = field(default_factory=list)  # rebuilt from word positions
    from_ocr: bool = False
    image_count: int = 0


@dataclass
class PdfDocument:
    path: Path
    pages: list[Page] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(h.text for h in self.pages)

    @property
    def is_scanned(self) -> bool:
        return any(h.from_ocr for h in self.pages) or (
            bool(self.pages)
            and all(len(h.text.strip()) < settings.SCANNED_PAGE_THRESHOLD for h in self.pages)
        )

    @property
    def lines(self) -> list[str]:
        out: list[str] = []
        for h in self.pages:
            out.extend(h.lines or h.text.splitlines())
        return out

    def key_value_pairs(self) -> dict[str, str]:
        return extract_key_values(self.lines)

RE_KV = re.compile(
    r"(?P<key>[A-Za-z][A-Za-z0-9 ./&'%()\-]{1,45}?)\s*[:\uff1a]\s*"
    r"(?P<value>.*?)(?=\s+[A-Za-z][A-Za-z0-9 ./&'%()\-]{1,45}?\s*[:\uff1a]|$)"
)

def lines_by_position(page: fitz.Page, tolerance: float = 3.0) -> list[str]:
    bands: dict[int, list[tuple[float, str]]] = {}
    for x0, y0, _x1, _y1, text, *_ in page.get_text("words"):
        bands.setdefault(round(y0 / tolerance), []).append((x0, text))
    return [" ".join(t for _, t in sorted(items)) for _, items in sorted(bands.items())]


# Amount blocks are written as a heading with bulleted sub-lines, and the bullet
# is a colon with nothing before it:
#     Indemnity IDR 90,500,000.00
#     Definite Loss Amount :
#     : Deductible IDR (35,000,000.00)
#     : Nett Amount IDR 55,500,000.00
# RE_KV needs a label to the left of the colon, so it reads none of them and the
# heading swallows the deductible line as its own value.
RE_MONEY_LINE = re.compile(
    r"^[:\s]*(?P<key>[A-Za-z][A-Za-z ./&'\-]{1,40}?)\s*[:：]?\s*"
    r"(?P<value>(?:[A-Z]{2,3}|Rp)\s*\(?-?[\d.,]+\)?)\s*$"
)


def extract_key_values(lines: list[str]) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for i, b in enumerate(lines):
        found = False
        for m in RE_KV.finditer(b):
            key = " ".join(m.group("key").split())
            value = " ".join(m.group("value").split())
            if len(key) < 2:
                continue
            found = True
            if not value and i + 1 < len(lines) and not _is_pair(lines[i + 1]):
                value = " ".join(lines[i + 1].split())
            if value:
                pairs.setdefault(key, value)
        if not found:
            m = RE_MONEY_LINE.match(b)
            if m:
                key = " ".join(m.group("key").split())
                if len(key) >= 2:
                    pairs.setdefault(key, " ".join(m.group("value").split()))
    return pairs


def _is_pair(line: str) -> bool:
    return bool(RE_KV.search(line)) or bool(RE_MONEY_LINE.match(line))


def _ocr_page(page: fitz.Page, dpi: int = 300) -> str:
    exe = find_tesseract()
    if not exe:
        raise RuntimeError("tesseract belum terpasang")

    pytesseract.pytesseract.tesseract_cmd = exe
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img, lang=settings.OCR_LANGUAGES)


def read_pdf(path: str | Path, *, use_ocr: bool = True) -> PdfDocument:
    path = Path(path)
    result = PdfDocument(path=path)
    try:
        doc = fitz.open(path)
    except Exception as e:
        result.error = f"tidak bisa dibuka: {e}"
        return result

    if doc.needs_pass:
        result.error = "PDF terkunci password"
        doc.close()
        return result

    result.metadata = {k: v for k, v in (doc.metadata or {}).items() if v}
    needs_ocr = False

    for i, page in enumerate(doc, start=1):
        h = Page(number=i)
        try:
            h.text = page.get_text() or ""
            h.lines = lines_by_position(page)
            h.image_count = len(page.get_images(full=True))
        except Exception as e:
            result.warnings.append(f"halaman {i}: gagal dibaca ({e})")

        if len(h.text.strip()) < settings.SCANNED_PAGE_THRESHOLD:
            needs_ocr = True
        result.pages.append(h)

    if needs_ocr and use_ocr:
        if not ocr_available():
            result.warnings.append(
                "PDF ini hasil scan tapi OCR belum terpasang."
            )
        else:
            for h in result.pages:
                if len(h.text.strip()) >= settings.SCANNED_PAGE_THRESHOLD:
                    continue
                try:
                    h.text = _ocr_page(doc[h.number - 1])
                    h.lines = h.text.splitlines()
                    h.from_ocr = True
                except Exception as e:
                    result.warnings.append(f"halaman {h.number}: OCR gagal ({e})")

    doc.close()
    if not result.text.strip() and not result.error:
        result.error = "tidak ada teks yang bisa dibaca"
    return result
