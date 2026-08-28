# Potongan HTML untuk app.py. Gayanya sendiri ada di styles.css sebelah,
# supaya file ini isinya Python saja dan enak dibaca.
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from . import config

# Dipakai app.py untuk mewarnai kartu angka. Warna lainnya ada di styles.css.
BIRU = "#125DAB"
HIJAU = "#0E9F6E"
KUNING = "#C77700"
MERAH = "#D64545"

LOGO = config.ROOT / "PICTURE ASSETS" / "logo.png"
BERKAS_GAYA = Path(__file__).with_name("styles.css")


@lru_cache(maxsize=1)
def css() -> str:
    return "<style>\n" + BERKAS_GAYA.read_text(encoding="utf-8") + "</style>"


@lru_cache(maxsize=1)
def logo_base64() -> str:
    return base64.b64encode(LOGO.read_bytes()).decode() if LOGO.exists() else ""


def ada_logo() -> bool:
    return LOGO.exists()


def judul_utama(judul: str) -> str:
    return (f'<div class="astra-judul-utama">{judul}'
            f'<span class="astra-judul-garis"></span></div>')

def langkah(aktif: int, selesai: set[int] | None = None) -> str:
    selesai = selesai or set()
    nama = ["Pilih sumber PDF", "Isi email", "Proses & unduh"]
    isi = []
    for i, n in enumerate(nama, start=1):
        kelas = "selesai" if i in selesai else ("aktif" if i == aktif else "nanti")
        tanda = "✓" if i in selesai else str(i)
        isi.append(
            f'<div class="astra-langkah {kelas}">'
            f'<span class="astra-bulat">{tanda}</span><span>{n}</span></div>')
        if i < len(nama):
            isi.append('<div class="astra-garis"></div>')
    return f'<div class="astra-langkah-rail">{"".join(isi)}</div>'


def statistik(data: list[tuple[str, int, str, str]]) -> str:
    kartu = []
    for label, nilai, ikon, warna in data:
        kartu.append(
            f'<div class="astra-stat" style="--aksen:{warna}">'
            f'<div class="astra-stat-ikon">{ikon}</div>'
            f'<div class="astra-stat-angka">{nilai}</div>'
            f'<div class="astra-stat-label">{label}</div></div>')
    return f'<div class="astra-stat-baris">{"".join(kartu)}</div>'


def kartu_hasil(nama: str, baris: int, lokasi: str) -> str:
    return (f'<div class="astra-hasil">'
            f'<div class="astra-hasil-ikon">📊</div>'
            f'<div class="astra-hasil-teks"><b>{nama}</b>'
            f'<span>{baris} baris · {lokasi}</span></div></div>')


def kosong(ikon: str, judul: str, pesan: str) -> str:
    return (f'<div class="astra-kosong"><div class="astra-kosong-ikon">{ikon}</div>'
            f'<div class="astra-kosong-judul">{judul}</div>'
            f'<div class="astra-kosong-pesan">{pesan}</div></div>')
