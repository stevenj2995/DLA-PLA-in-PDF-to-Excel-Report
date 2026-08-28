from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from . import config

BULAN_ID = {
    "januari": 1, "jan": 1,
    "februari": 2, "pebruari": 2, "feb": 2,
    "maret": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "agustus": 8, "agu": 8, "ags": 8,
    "september": 9, "sep": 9, "sept" : 9,
    "oktober": 10, "okt": 10, "oct" : 10, "october" : 10,
    "november": 11, "nov": 11, "nopember": 11, 
    "desember": 12, "des": 12, "dec" : 12, "december" : 12
}
BULAN_EN = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3,  "mar": 3,
    "april": 4, "apr": 4,
    "may": 5, 
    "june": 6, "jun": 6,
    "july": 7, "jul": 7, 
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "october": 10, "oct": 10, 
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}
BULAN = {**BULAN_EN, **BULAN_ID}

# "Jakarta, 22 Agustus 2026" / "Surabaya, 22 August 2026"
RE_KAKI_SURAT = re.compile(
    r"(?P<kota>[A-Z][A-Za-z\.\s]{2,30}?)\s*,\s*"
    r"(?P<hari>\d{1,2})\s+(?P<bulan>[A-Za-z]{3,12})\s+(?P<tahun>\d{4})"
)
RE_TGL_TEKS = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,12})\s+(\d{4})\b")
RE_TGL_ANGKA = re.compile(r"\b(\d{1,4})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b")
RE_JAM = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")


def _tgl(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


# baca tanggal dari berbagai bentuk penulisan Indonesia maupun Inggris
def parse_tanggal(teks: str) -> date | None:
    if not teks:
        return None
    s = str(teks).strip()

    m = RE_TGL_TEKS.search(s)
    if m:
        bulan = BULAN.get(m.group(2).lower())
        if bulan:
            hasil = _tgl(int(m.group(3)), bulan, int(m.group(1)))
            if hasil:
                return hasil

    m = RE_TGL_ANGKA.search(s)
    if m:
        a, b, c = (int(x) for x in m.groups())
        if len(m.group(1)) == 4:
            return _tgl(a, b, c)
        tahun = c + 2000 if c < 100 else c
        return _tgl(tahun, b, a) or _tgl(tahun, a, b)  # dd/mm lalu mm/dd
    return None

def tanggal_kaki_surat(teks: str) -> tuple[date | None, str | None, str | None]:
    for m in reversed(list(RE_KAKI_SURAT.finditer(teks or ""))):
        bulan = BULAN.get(m.group("bulan").lower())
        if not bulan:
            continue
        d = _tgl(int(m.group("tahun")), bulan, int(m.group("hari")))
        if d:
            kota = " ".join(m.group("kota").split()).strip(" .,")
            return d, kota, m.group(0)
    return None, None, None

def format_tanggal(d: date | None, gaya: str = "iso") -> str | None:
    if d is None:
        return None
    if gaya == "asli":
        nama = [k for k, v in BULAN_ID.items() if v == d.month and len(k) > 3]
        return f"{d.day} {nama[0].capitalize() if nama else d.month} {d.year}"
    return d.strftime("%Y-%m-%d")


def parse_jam(teks: str) -> str | None:
    m = RE_JAM.search(str(teks or ""))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


# "Rp 1.024.770.200,00" -> 1024770200.0
def parse_uang(teks: str) -> float | None:
    if teks is None:
        return None
    if isinstance(teks, (int, float)):
        return float(teks)

    s = re.sub(r"(?i)\b(rp|idr|usd|sgd)\b\.?", " ", str(teks))
    s = re.sub(r"[^\d,.\-]", "", s).strip()
    if not s or not re.search(r"\d", s):
        return None

    ada_titik, ada_koma = "." in s, "," in s
    if ada_titik and ada_koma:
        desimal = "," if s.rfind(",") > s.rfind(".") else "."
        ribuan = "." if desimal == "," else ","
        s = s.replace(ribuan, "").replace(desimal, ".")
    elif ada_koma:
        ekor = s.split(",")[-1] # 1-2 angka di belakang = desimal
        s = s.replace(",", "." if len(ekor) <= 2 and s.count(",") == 1 else "")
    elif ada_titik:
        ekor = s.split(".")[-1]
        if not (len(ekor) <= 2 and s.count(".") == 1):
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_kode_pos(teks: str) -> str | None:
    m = re.search(r"\b(\d{5})\b", str(teks or ""))
    return m.group(1) if m else None

def parse_persen(teks: str) -> str | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", str(teks or ""))
    return m.group(1).replace(",", ".") + "%" if m else None


def rapikan_teks(teks: str, maks: int = 500) -> str:
    return " ".join(str(teks or "").split())[:maks]


# membaca nama perusahaan
_SP = r"[^\S\n]"
_KATA = r"[A-Z][A-Za-z0-9&'\.\-]*"

RE_PERUSAHAAN = re.compile(
    rf"\b(?:PT|CV|UD|PD)\.?{_SP}+"
    rf"(?P<nama>{_KATA}(?:{_SP}+(?:{_KATA}|dan|and|of|de)){{0,6}})"
    rf"(?P<ekor>{_SP}*\((?:Persero|PERSERO|Tbk|TBK)\))?"
)
# bentuk terbalik
RE_PERUSAHAAN_BALIK = re.compile(
    rf"(?P<nama>{_KATA}(?:{_SP}+[A-Za-z0-9&'\.\-()]+){{0,6}}?){_SP}*,{_SP}*(?:PT|CV)\.?\b"
)

# kata yang menandakan nama sudah habis dan ini mulai label kolom berikutnya
RE_POTONG = re.compile(
    r"\b(?:Jl|Jalan|Telp|Telepon|Fax|Email|NPWP|Nomor|No|Nama|Alamat|Tanggal|Tgl|"
    r"Date|Time|Policy|Polis|Lokasi|Penyebab|Jenis|Nilai|Kode|Kepada|Perihal|Hal)\b",
    re.I,
)

_TERLARANG_WINDOWS = r'[<>:"/\\|?*\x00-\x1f]'
_NAMA_CADANGAN = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_ROMAWI = r"(?:I{1,3}|IV|VI{0,3}|IX|XI{0,3})"
_BADAN = {"PT", "CV", "UD", "PD", "PERSERO", "TBK", "LTD", "INC", "LLC"}


# samakan tanda hubung/kutip aneh supaya tidak bikin nama folder gagal
def _rapikan_unicode(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    for aneh, ganti in (("–", "-"), ("—", "-"), ("−", "-"),
                        ("‘", "'"), ("’", "'"),
                        ("“", '"'), ("”", '"'), ("�", " ")):
        s = s.replace(aneh, ganti)
    return " ".join(s.split())


def normalisasi(nama: str) -> str:
    s = _rapikan_unicode(nama).upper()
    s = re.sub(r"\(([^)]*)\)", r" \1 ", s)
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    return " ".join(k for k in s.split() if k not in _BADAN)

# Cabang regional dikumpulkan ke induknya: "Pelabuhan Indonesia Regional 4"
# dan "Pelabuhan Indonesia" masuk grup yang sama. Nomornya bisa angka romawi
# (REGIONAL III) maupun angka biasa (REGIONAL 4) - dua-duanya dipakai di DLA.
_NOMOR = rf"(?:{_ROMAWI}|\d{{1,2}})"


def nama_grup(nama: str) -> str:
    inti = normalisasi(nama)
    inti = re.sub(rf"\s+REGIONAL(\s*-?\s*{_NOMOR})*\s*$", "", inti)
    inti = re.sub(rf"(\s+{_ROMAWI})+\s*$", "", inti)
    inti = re.sub(r"\s+\d+\s*$", "", inti)
    return (inti.strip() or normalisasi(nama)).title()


def nama_folder(nama: str, maks: int = 90) -> str:
    s = re.sub(_TERLARANG_WINDOWS, " ", _rapikan_unicode(nama))
    s = " ".join(s.split()).rstrip(" .")
    if len(s) > maks:
        s = s[:maks].rstrip(" .")
    if s.upper().split(".")[0] in _NAMA_CADANGAN:
        s = f"_{s}"
    return s or "TANPA_NAMA"


@dataclass
class Kandidat:
    nama: str
    skor: float = 0.0
    posisi: int = -1
    peran: str = ""
    alasan: list[str] = field(default_factory=list)


@dataclass
class HasilDeteksi:
    nama: str | None = None
    keyakinan: float = 0.0
    kandidat: list[Kandidat] = field(default_factory=list)
    peringatan: list[str] = field(default_factory=list)

    @property
    def tingkat(self) -> str:
        if self.nama and self.keyakinan >= config.YAKIN:
            return "yakin"
        if self.nama and self.keyakinan >= config.RAGU:
            return "ragu"
        return "tidak_terdeteksi"


def _tujuan(nama: str) -> bool:
    n = normalisasi(nama)
    return any(normalisasi(t) in n for t in config.PERUSAHAAN_TUJUAN)


# buang ekor yang sebenarnya label kolom berikutnya
def _potong(nama: str) -> str:
    m = RE_POTONG.search(nama)
    return " ".join(nama[:m.start()].split()) if m else " ".join(nama.split())


# semua penyebutan nama perusahaan beserta posisinya di teks
def cari_nama_perusahaan(teks: str) -> list[tuple[str, int]]:
    hasil: list[tuple[str, int]] = []
    for m in RE_PERUSAHAAN.finditer(teks):
        nama = _potong(m.group("nama"))
        if len(normalisasi(nama)) >= 4:
            hasil.append((f"PT {nama}{m.group('ekor') or ''}".strip(), m.start()))
    for m in RE_PERUSAHAAN_BALIK.finditer(teks):
        nama = _potong(m.group("nama"))
        if len(normalisasi(nama)) >= 4:
            hasil.append((f"PT {nama}", m.start()))
    return hasil

# Dicocokkan per KATA UTUH, bukan potongan teks. Kalau pakai potongan,
# "Name of Reinsured" ikut terbaca sebagai "insured" - dan perusahaan yang
# menyerahkan risiko (reasuradur) tertukar dengan pemilik polis.
def _ada_label(cuplik: str, daftar: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(l)}\b", cuplik) for l in daftar)


def _label_sebelum(teks: str, posisi: int, jarak: int = 60) -> str:
    cuplik = teks[max(0, posisi - jarak):posisi].lower()
    if _ada_label(cuplik, config.LABEL_TERTANGGUNG):
        return "tertanggung"
    if _ada_label(cuplik, config.LABEL_TUJUAN):
        return "tujuan"
    return ""

RE_LABEL_NILAI = re.compile(r"^\s*(?P<label>[^:：]{2,50})[:：]\s*(?P<nilai>.*)$")

# "PT A and/or PT B and/or PT C" atau "PT A QQ PT B" -> ambil yang pertama saja.
# Yang disebut duluan adalah tertanggung utama; sisanya pihak yang ikut.
RE_PIHAK_LAIN = re.compile(r"(?i)\s+(?:and\s*/\s*or|dan\s*/\s*atau|q\.?q\.?)\s+")


def _bersih_label(s: str) -> str:
    return " ".join(s.lower().replace(".", "").split())


# JALUR UTAMA. Kalau dokumennya menulis "Name of Insured : X", maka X ADALAH
# tertanggungnya - tidak perlu ditebak lewat skor. Dijalankan atas baris hasil
# susun-posisi, supaya label dan nilainya tetap bersebelahan.
def nama_tertanggung_dari_label(baris: list[str]) -> tuple[str | None, str | None]:
    for i, b in enumerate(baris):
        m = RE_LABEL_NILAI.match(b)
        if not m or _bersih_label(m.group("label")) not in config.LABEL_NAMA_TERTANGGUNG:
            continue

        nilai = m.group("nilai").strip()
        # label tanpa nilai di kanannya -> nilainya ada di baris bawahnya
        if not nilai and i + 1 < len(baris) and not RE_LABEL_NILAI.match(baris[i + 1]):
            nilai = baris[i + 1].strip()

        nilai = RE_PIHAK_LAIN.split(_potong(nilai))[0].strip(" ,.;-")
        if len(normalisasi(nilai)) >= 4 and not _tujuan(nilai):
            return nilai, " ".join(m.group("label").split())
    return None, None


def deteksi(baris: list[str], *, nama_file: str = "") -> HasilDeteksi:
    hasil = HasilDeteksi()
    teks = "\n".join(baris)
    if not teks.strip():
        hasil.peringatan.append("PDF tidak punya teks yang bisa dibaca")
        return hasil

    nama, label = nama_tertanggung_dari_label(baris)
    if nama:
        hasil.nama = nama
        hasil.keyakinan = 1.0
        hasil.kandidat = [Kandidat(nama=nama, skor=1.0, peran="tertanggung",
                                   alasan=[f"diambil dari label '{label}'"])]
        return hasil

    hasil.peringatan.append(
        "Tidak ada label tertanggung (Insured Name / Name of Insured / "
        "Tertanggung) - nama ditebak dari sebaran nama di teks")

    skor: dict[str, Kandidat] = {}
    for nama, posisi in cari_nama_perusahaan(teks):
        if _tujuan(nama):
            continue
        kunci = normalisasi(nama)
        if not kunci:
            continue

        k = skor.get(kunci)
        if k is None:
            k = skor[kunci] = Kandidat(nama=nama, posisi=posisi)
        k.skor += 1.0
        if posisi < k.posisi or k.posisi < 0:
            k.posisi = posisi

        peran = _label_sebelum(teks, posisi)
        if peran and not k.peran:
            k.peran = peran
            k.alasan.append(f"disebut sebagai {peran}")

        if nama_file and kunci in normalisasi(nama_file):
            if "cocok dengan nama file" not in k.alasan:
                k.skor += 2.0
                k.alasan.append("cocok dengan nama file")

    # Yang dicari SELALU tertanggung - pemilik polis yang mengalami kerugian.
    # Penerbit laporan (adjuster/broker) dan pihak tujuan tidak dipakai.
    for k in skor.values():
        k.skor += 6.0 if k.peran == "tertanggung" else -2.0
        k.skor = max(k.skor, 0.0)

    urut = [k for k in sorted(skor.values(), key=lambda x: x.skor, reverse=True)
            if k.skor > 0]
    if not urut:
        hasil.peringatan.append(
            "Tidak ada nama perusahaan yang terbaca!")
        return hasil

    total = sum(k.skor for k in urut) or 1.0
    for k in urut:
        k.skor = round(k.skor / total, 3)

    hasil.kandidat = urut
    hasil.nama = urut[0].nama
    hasil.keyakinan = urut[0].skor

    if len(urut) > 1 and urut[0].skor - urut[1].skor < 0.15:
        hasil.peringatan.append(
            f"Dua kandidat nyaris seimbang: '{urut[0].nama}' vs '{urut[1].nama}'")
    if re.search(rf"\b{_ROMAWI}\b", hasil.nama or ""):
        hasil.peringatan.append(
            "Nama mengandung angka romawi (I/II/III/IV) yang gampang tertukar "
            "saat OCR - mohon dicek folder tujuannya")
    return hasil
