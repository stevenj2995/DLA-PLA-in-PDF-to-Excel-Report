from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import fitz # PyMuPDF

from . import config

_KANDIDAT_TESSERACT = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]


def cari_tesseract() -> str | None:
    if config.TESSERACT_PATH and Path(config.TESSERACT_PATH).exists():
        return config.TESSERACT_PATH
    ada = shutil.which("tesseract")
    if ada:
        return ada
    for p in _KANDIDAT_TESSERACT:
        if p and Path(p).exists():
            return p
    return None


def ocr_tersedia() -> bool:
    return cari_tesseract() is not None


@dataclass
class Halaman:
    nomor: int
    teks: str = ""
    baris: list[str] = field(default_factory=list)   # disusun ulang dari posisi kata
    dari_ocr: bool = False
    jumlah_gambar: int = 0


@dataclass
class DokumenPdf:
    path: Path
    halaman: list[Halaman] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    peringatan: list[str] = field(default_factory=list)
    gagal: str | None = None

    @property
    def teks(self) -> str:
        return "\n".join(h.teks for h in self.halaman)

    @property
    def hasil_scan(self) -> bool:
        return any(h.dari_ocr for h in self.halaman) or (
            bool(self.halaman)
            and all(len(h.teks.strip()) < config.AMBANG_HALAMAN_SCAN for h in self.halaman)
        )

    @property
    def baris(self) -> list[str]:
        semua: list[str] = []
        for h in self.halaman:
            semua.extend(h.baris or h.teks.splitlines())
        return semua

    def pasangan_kunci_nilai(self) -> dict[str, str]:
        return ekstrak_key_value(self.baris)

RE_KV = re.compile(
    r"(?P<kunci>[A-Za-z][A-Za-z0-9 ./&'%()\-]{1,45}?)\s*[:\uff1a]\s*"
    r"(?P<nilai>.*?)(?=\s+[A-Za-z][A-Za-z0-9 ./&'%()\-]{1,45}?\s*[:\uff1a]|$)"
)


# menyusun ulang baris dari posisi kata, bukan dari urutan baca PyMuPDF.
def baris_menurut_posisi(page: fitz.Page, toleransi: float = 3.0) -> list[str]:
    pita: dict[int, list[tuple[float, str]]] = {}
    for x0, y0, _x1, _y1, teks, *_ in page.get_text("words"):
        pita.setdefault(round(y0 / toleransi), []).append((x0, teks))
    return [" ".join(t for _, t in sorted(isi)) for _, isi in sorted(pita.items())]


def ekstrak_key_value(baris: list[str]) -> dict[str, str]:
    hasil: dict[str, str] = {}
    for i, b in enumerate(baris):
        for m in RE_KV.finditer(b):
            kunci = " ".join(m.group("kunci").split())
            nilai = " ".join(m.group("nilai").split())
            if len(kunci) < 2:
                continue
            if not nilai and i + 1 < len(baris) and not RE_KV.search(baris[i + 1]):
                nilai = " ".join(baris[i + 1].split())
            if nilai:
                hasil.setdefault(kunci, nilai)
    return hasil


def _ocr_halaman(page: fitz.Page, dpi: int = 300) -> str:
    exe = cari_tesseract()
    if not exe:
        raise RuntimeError("tesseract belum terpasang")
    import io

    import pytesseract
    from PIL import Image

    pytesseract.pytesseract.tesseract_cmd = exe
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img, lang=config.OCR_BAHASA)


def baca(path: str | Path, *, pakai_ocr: bool = True) -> DokumenPdf:
    path = Path(path)
    dok = DokumenPdf(path=path)
    try:
        doc = fitz.open(path)
    except Exception as e:
        dok.gagal = f"tidak bisa dibuka: {e}"
        return dok

    if doc.needs_pass:
        dok.gagal = "PDF terkunci password"
        doc.close()
        return dok

    dok.metadata = {k: v for k, v in (doc.metadata or {}).items() if v}
    butuh_ocr = False

    for i, page in enumerate(doc, start=1):
        h = Halaman(nomor=i)
        try:
            h.teks = page.get_text() or ""
            h.baris = baris_menurut_posisi(page)
            h.jumlah_gambar = len(page.get_images(full=True))
        except Exception as e:
            dok.peringatan.append(f"halaman {i}: gagal dibaca ({e})")

        if len(h.teks.strip()) < config.AMBANG_HALAMAN_SCAN:
            butuh_ocr = True
        dok.halaman.append(h)

    if butuh_ocr and pakai_ocr:
        if not ocr_tersedia():
            dok.peringatan.append(
                "PDF ini hasil scan (nyaris tanpa teks) tapi OCR belum terpasang. "
                "Pasang Tesseract OCR dulu, isinya tidak bisa dibaca."
            )
        else:
            for h in dok.halaman:
                if len(h.teks.strip()) >= config.AMBANG_HALAMAN_SCAN:
                    continue
                try:
                    h.teks = _ocr_halaman(doc[h.nomor - 1])
                    h.baris = h.teks.splitlines()
                    h.dari_ocr = True
                except Exception as e:
                    dok.peringatan.append(f"halaman {h.nomor}: OCR gagal ({e})")

    doc.close()
    if not dok.teks.strip() and not dok.gagal:
        dok.gagal = "tidak ada teks yang bisa dibaca"
    return dok
