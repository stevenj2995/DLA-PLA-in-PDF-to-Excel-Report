
from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import config
from .teks import nama_folder, nama_grup, normalisasi

# sortir dan pindahkan PDF

NAMA_CATATAN = "_catatan_pemindahan.jsonl"


def _catat(baris: dict) -> None:
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with (config.OUTPUT_DIR / NAMA_CATATAN).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(baris, ensure_ascii=False) + "\n")

# kalau nama sudah dipakai, tambahkan nomor supaya tidak menimpa
def _nama_bebas(tujuan: Path) -> Path:
    if not tujuan.exists():
        return tujuan
    batang, akhiran = tujuan.stem, tujuan.suffix
    for i in range(2, 1000):
        kandidat = tujuan.with_name(f"{batang} ({i}){akhiran}")
        if not kandidat.exists():
            return kandidat
    return tujuan.with_name(f"{batang} ({datetime.now():%H%M%S}){akhiran}")


def pindahkan(pdf: Path, folder_tujuan: Path, *, alasan: str = "") -> Path:
    folder_tujuan.mkdir(parents=True, exist_ok=True)
    tujuan = _nama_bebas(folder_tujuan / pdf.name)
    shutil.move(str(pdf), str(tujuan))
    _catat({
        "waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dari": str(pdf),
        "ke": str(tujuan),
        "alasan": alasan,
    })
    return tujuan


def folder_perusahaan(grup: str, entitas: str) -> Path:
    return config.OUTPUT_DIR / nama_folder(grup) / nama_folder(entitas)


def folder_tidak_terdeteksi() -> Path:
    return config.OUTPUT_DIR / config.FOLDER_TIDAK_TERDETEKSI


def kembalikan_semua(sampai: str | None = None) -> int:
    f = config.OUTPUT_DIR / NAMA_CATATAN
    if not f.exists():
        return 0
    baris = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    jumlah = 0
    for b in reversed(baris):
        if sampai and b["waktu"] < sampai:
            continue
        ke, dari = Path(b["ke"]), Path(b["dari"])
        if ke.exists():
            dari.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(ke), str(_nama_bebas(dari)))
            jumlah += 1
    return jumlah


def daftar_pdf(folder: Path | None = None) -> list[Path]:
    folder = Path(folder or config.INPUT_DIR)
    if not folder.exists():
        return []
    return sorted(p for p in folder.rglob("*.pdf")
                  if p.is_file() and not p.name.startswith("~"))

# profil memory per perusahaan
def _sekarang() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _nama_berkas(kunci: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", kunci).strip("_").lower() or "tanpa_nama"


@dataclass
class Profil:
    nama_resmi: str
    kunci: str = ""
    grup: str = ""
    folder: str = ""
    alias: list[str] = field(default_factory=list)
    peta_parameter: dict[str, dict] = field(default_factory=dict)
    tidak_cocok: dict[str, str] = field(default_factory=dict)
    jumlah_pdf: int = 0
    ref_sudah_diproses: list[str] = field(default_factory=list)
    dibuat: str = field(default_factory=_sekarang)
    diperbarui: str = field(default_factory=_sekarang)
    catatan: str = ("File ini boleh diedit manual. Ubah 'grup' atau 'folder' "
                    "kalau sistem salah menempatkan, lalu simpan.")

    def __post_init__(self):
        self.kunci = self.kunci or normalisasi(self.nama_resmi)
        self.grup = self.grup or nama_grup(self.nama_resmi)
        self.folder = self.folder or nama_folder(self.nama_resmi)
        if self.nama_resmi not in self.alias:
            self.alias.insert(0, self.nama_resmi)

    def tambah_alias(self, nama: str) -> bool:
        if nama and nama not in self.alias:
            self.alias.append(nama)
            return True
        return False

    def ingat_parameter(self, param_pdf: str, kolom: str, cara: str, skor: float) -> None:
        self.peta_parameter[param_pdf] = {
            "kolom": kolom, "cara": cara, "skor": round(float(skor), 3),
            "dicatat": _sekarang(),
        }
        self.tidak_cocok.pop(param_pdf, None)

    def ingat_tidak_cocok(self, param_pdf: str, alasan: str) -> None:
        if param_pdf not in self.peta_parameter:
            self.tidak_cocok[param_pdf] = f"N/A: {alasan}"

    def kolom_untuk(self, param_pdf: str) -> str | None:
        entri = self.peta_parameter.get(param_pdf)
        return entri["kolom"] if entri else None


class GudangProfil:
    def __init__(self, direktori: Path | None = None):
        self.dir = Path(direktori or config.MEMORY_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Profil] = {}
        self._muat_semua()

    def _muat_semua(self) -> None:
        for f in self.dir.glob("*.json"):
            try:
                p = Profil(**json.loads(f.read_text(encoding="utf-8")))
                self._cache[p.kunci] = p
            except Exception:
                continue # file rusak

    def semua(self) -> list[Profil]:
        return sorted(self._cache.values(), key=lambda p: p.nama_resmi)

    def cari(self, nama: str) -> Profil | None:
        kunci = normalisasi(nama)
        if kunci in self._cache:
            return self._cache[kunci]
        for p in self._cache.values():
            if any(normalisasi(a) == kunci for a in p.alias):
                return p
        return None
    
    def ambil_atau_buat(self, nama: str) -> tuple[Profil, bool]:
        ada = self.cari(nama)
        if ada:
            if ada.tambah_alias(nama):
                self.simpan(ada)
            return ada, False
        p = Profil(nama_resmi=nama)
        self._cache[p.kunci] = p
        self.simpan(p)
        return p, True

    def simpan(self, p: Profil) -> Path:
        p.diperbarui = _sekarang()
        f = self.dir / f"{_nama_berkas(p.kunci)}.json"
        f.write_text(json.dumps(asdict(p), indent=2, ensure_ascii=False),
                     encoding="utf-8")
        return f
