"""Backend untuk website publik. Jalankan di laptop ini: python server.py

Halaman webnya sendiri di-host di Vercel (folder web/), tapi semua pemrosesan
PDF terjadi di sini. Berkas yang diunggah TIDAK pernah melewati Vercel --
browser pengunjung mengirimnya langsung ke alamat terowongan backend ini.

Umur berkas unggahan:
  - PDF asli dihapus BEGITU Excel-nya jadi (hitungan detik)
  - Excel hasil dihapus setelah UMUR_SESI, atau saat server dimatikan
  - Folder yatim dari sesi sebelumnya dibersihkan saat server menyala
"""
from __future__ import annotations

import atexit
import hmac
import os
import shutil
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src import config, pdf_reader, pipeline

# ----------------------------------------------------------------- batas aman
# Backend ini terbuka ke internet lewat terowongan, jadi batasi apa yang masuk.
MAKS_BERKAS = 10
MAKS_UKURAN_BERKAS = 15 * 1024 * 1024      # 15 MB per PDF
MAKS_UKURAN_TOTAL = 50 * 1024 * 1024       # 50 MB sekali proses
UMUR_SESI = 15 * 60                        # hasil dibuang setelah 15 menit
JEDA_SAPU = 60                             # penyapu latar jalan tiap 1 menit

# Kalau diisi, pengunjung wajib memasukkan kode ini sebelum bisa memproses.
# Isi lewat variabel lingkungan:  set KODE_AKSES=rahasia123
# Kosong = siapa pun yang punya tautannya bisa mengunggah.
KODE_AKSES = os.environ.get("KODE_AKSES", "").strip()

# Alamat tambahan yang boleh memanggil backend ini (domain sendiri, dsb).
# Isi lewat variabel lingkungan ASAL_DIIZINKAN, dipisah koma.
ASAL_DIIZINKAN = [
    a.strip() for a in os.environ.get("ASAL_DIIZINKAN", "").split(",") if a.strip()
]

# Yang selalu diizinkan:
#   - semua subdomain *.vercel.app, karena setiap deploy Vercel membuat
#     alamat pratinjau baru dan domain tetapmu belum tentu sudah ada
#   - localhost DAN 127.0.0.1 di port mana pun, untuk uji coba di laptop.
#     Dua-duanya harus ditulis: bagi browser keduanya asal yang BERBEDA,
#     jadi mengizinkan salah satu saja bikin uji lokal gagal kena CORS.
POLA_ASAL = r"https://[\w-]+\.vercel\.app|http://(localhost|127\.0\.0\.1)(:\d+)?"

app = FastAPI(title="DLA to Excel Report", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ASAL_DIIZINKAN,
    allow_origin_regex=POLA_ASAL,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# pipeline menukar config.OUTPUT_DIR/MEMORY_DIR saat berjalan, jadi hanya boleh
# satu proses pada satu waktu -- kalau tidak, dua permintaan akan saling menimpa
_gembok = threading.Lock()
_sesi: dict[str, dict] = {}


@contextmanager
def ruang_terisolasi():
    """Alihkan OUTPUT_DIR dan MEMORY_DIR ke folder sementara.

    Profil perusahaan yang sudah terlatih disalin masuk supaya deteksi tetap
    akurat, tapi apa pun yang dipelajari dari PDF pengunjung berhenti di salinan
    itu dan ikut terhapus. Memory asli di laptop tidak pernah tersentuh.
    """
    asli_output, asli_memory = config.OUTPUT_DIR, config.MEMORY_DIR
    ruang = Path(tempfile.mkdtemp(prefix="dla_"))
    # diisi True oleh pemanggil kalau folder masih dibutuhkan untuk unduhan;
    # kalau tidak (mis. proses gagal di tengah), folder langsung dibuang
    penanda = {"disimpan": False}
    try:
        config.OUTPUT_DIR = ruang / "OUTPUT"
        config.MEMORY_DIR = ruang / "MEMORY"
        config.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        if asli_memory.exists():
            for f in asli_memory.glob("*.json"):
                shutil.copy2(f, config.MEMORY_DIR / f.name)
        yield ruang, penanda
    finally:
        config.OUTPUT_DIR, config.MEMORY_DIR = asli_output, asli_memory
        if not penanda["disimpan"]:
            shutil.rmtree(ruang, ignore_errors=True)


def _bersihkan_sesi_lama() -> None:
    batas = time.time() - UMUR_SESI
    for sid in [s for s, d in list(_sesi.items()) if d["waktu"] < batas]:
        d = _sesi.pop(sid, None)
        if d:
            shutil.rmtree(d["ruang"], ignore_errors=True)


def _buang_semua_sesi() -> None:
    """Dipanggil saat server dimatikan -- jangan tinggalkan berkas siapa pun."""
    for sid in list(_sesi):
        d = _sesi.pop(sid, None)
        if d:
            shutil.rmtree(d["ruang"], ignore_errors=True)


def _sapu_folder_yatim() -> int:
    """Buang folder dla_* yang sudah tidak dimiliki sesi mana pun.

    Ini jaring pengaman untuk server yang mati mendadak (listrik putus, laptop
    ditutup): daftar sesi ikut hilang bersama prosesnya, jadi folder PDF
    pengunjung tidak akan pernah terhapus tanpa penyapu ini.

    Hanya folder yang lebih tua dari UMUR_SESI yang dibuang. Batas umur itu
    penting: tanpanya, menjalankan server kedua -- atau sekadar meng-import
    modul ini dari skrip lain -- akan menghapus sesi yang sedang aktif di
    server pertama, dan pengunjungnya tiba-tiba melihat "hasil kedaluwarsa".
    """
    n = 0
    batas = time.time() - UMUR_SESI
    aktif = {str(d["ruang"]) for d in _sesi.values()}
    for f in Path(tempfile.gettempdir()).glob("dla_*"):
        if not f.is_dir() or str(f) in aktif:
            continue
        try:
            if f.stat().st_mtime > batas:
                continue
        except OSError:
            continue
        shutil.rmtree(f, ignore_errors=True)
        n += 1
    return n


def _penyapu_latar() -> None:
    # Menyapu dua-duanya: sesi yang kedaluwarsa DAN folder yatim. Yang kedua
    # tidak boleh dilewatkan -- folder yatim tidak ada di daftar _sesi, jadi
    # kalau hanya sesi yang disapu, ia menganggur sampai server berikutnya
    # menyala, dan itu bisa berhari-hari.
    while True:
        time.sleep(JEDA_SAPU)
        try:
            _bersihkan_sesi_lama()
            _sapu_folder_yatim()
        except Exception:
            pass


# Dijalankan saat modul diimpor, bukan di blok __main__ -- mulai.py menyalakan
# server lewat "uvicorn server:app", jadi blok __main__ tidak pernah dieksekusi
# dan pembersihan tidak akan pernah terjadi kalau ditaruh di sana.
_YATIM = _sapu_folder_yatim()

threading.Thread(target=_penyapu_latar, daemon=True).start()
atexit.register(_buang_semua_sesi)


def _hapus_semua_pdf(ruang: Path) -> int:
    n = 0
    for f in ruang.rglob("*.pdf"):
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n


@app.get("/api/status")
def status():
    """Dipakai halaman web untuk menyalakan indikator 'backend aktif'."""
    try:
        standar = config.file_standar().name
    except FileNotFoundError:
        standar = None
    return {
        "siap": standar is not None,
        "standar": standar,
        "ocr": pdf_reader.ocr_tersedia(),
        "maks_berkas": MAKS_BERKAS,
        "maks_ukuran_mb": MAKS_UKURAN_BERKAS // (1024 * 1024),
        "perlu_kode": bool(KODE_AKSES),
        "umur_sesi_menit": UMUR_SESI // 60,
    }


@app.post("/api/proses")
async def proses(email: str = Form(...), berkas: list[UploadFile] = File(...),
                 kode: str = Form("")):
    # compare_digest supaya lama pengecekan tidak membocorkan berapa banyak
    # karakter awal yang sudah benar
    if KODE_AKSES and not hmac.compare_digest(kode.strip(), KODE_AKSES):
        raise HTTPException(403, "Kode akses salah.")
    if not email.strip():
        raise HTTPException(400, "Email wajib diisi.")
    if not berkas:
        raise HTTPException(400, "Tidak ada berkas yang diunggah.")
    if len(berkas) > MAKS_BERKAS:
        raise HTTPException(400, f"Maksimal {MAKS_BERKAS} PDF sekali proses.")

    _bersihkan_sesi_lama()

    if not _gembok.acquire(blocking=False):
        raise HTTPException(
            429, "Sedang memproses permintaan lain. Coba lagi beberapa detik.")
    try:
        with ruang_terisolasi() as (ruang, penanda):
            masuk = ruang / "MASUK"
            masuk.mkdir(parents=True)

            total = 0
            for b in berkas:
                if not (b.filename or "").lower().endswith(".pdf"):
                    raise HTTPException(400, f"'{b.filename}' bukan file PDF.")
                isi = await b.read()
                if len(isi) > MAKS_UKURAN_BERKAS:
                    raise HTTPException(
                        400, f"'{b.filename}' lebih dari "
                             f"{MAKS_UKURAN_BERKAS // (1024*1024)} MB.")
                total += len(isi)
                if total > MAKS_UKURAN_TOTAL:
                    raise HTTPException(400, "Total unggahan terlalu besar.")
                # pakai nama file apa adanya bisa menimpa file lain atau keluar
                # dari folder ("../"), jadi ambil nama dasarnya saja
                (masuk / Path(b.filename).name).write_bytes(isi)

            hasil = pipeline.proses(
                email_operator=email.strip(), folder_input=masuk)

            # PDF sudah tidak diperlukan lagi setelah Excel jadi. Pipeline
            # memindahkannya ke OUTPUT/<perusahaan>/PDF/; buang sekarang juga
            # supaya dokumen pengunjung tidak menunggu sampai sesi kedaluwarsa.
            _hapus_semua_pdf(ruang)

            sid = uuid.uuid4().hex
            unduhan = {}
            daftar_excel = []
            for e in hasil.excel:
                f = Path(e["file"])
                fid = uuid.uuid4().hex[:12]
                unduhan[fid] = f
                daftar_excel.append({
                    "id": fid,
                    "perusahaan": e["perusahaan"],
                    "baris": e["baris"],
                    "nama_file": f.name,
                    "dropdown_utuh": e["dropdown_utuh"],
                    "dropdown_hasil": e["dropdown_hasil"],
                    "dropdown_asli": e["dropdown_asli"],
                })

            # ruang dipertahankan sampai kedaluwarsa supaya Excel bisa diunduh
            _sesi[sid] = {"ruang": ruang, "waktu": time.time(), "file": unduhan}
            penanda["disimpan"] = True

            return {
                "sesi": sid,
                "ringkasan": {
                    "pdf": len(hasil.pdf),
                    "berhasil": len(hasil.berhasil),
                    "ditinjau": len(hasil.perlu_ditinjau),
                    "dilewati": len(hasil.gagal),
                },
                "catatan": hasil.catatan_umum,
                "perusahaan_baru": hasil.perusahaan_baru,
                "excel": daftar_excel,
                "ditinjau": [
                    {"nama": h.path.name,
                     "perusahaan": h.perusahaan or "tidak terdeteksi",
                     "keyakinan": round(h.keyakinan, 2),
                     "peringatan": h.peringatan}
                    for h in hasil.perlu_ditinjau
                ],
                "dilewati": [
                    {"nama": h.path.name, "alasan": h.dilewati}
                    for h in hasil.gagal
                ],
            }
    finally:
        _gembok.release()


@app.get("/api/unduh/{sesi}/{fid}")
def unduh(sesi: str, fid: str):
    d = _sesi.get(sesi)
    if not d or fid not in d["file"]:
        raise HTTPException(404, "Hasil sudah kedaluwarsa. Silakan proses ulang.")
    f: Path = d["file"][fid]
    if not f.exists():
        raise HTTPException(404, "Berkas tidak ditemukan lagi.")
    return FileResponse(
        f, filename=f.name,
        media_type="application/vnd.openxmlformats-officedocument."
                   "spreadsheetml.sheet")


@app.post("/api/selesai/{sesi}")
def selesai(sesi: str):
    """Dipanggil pengunjung saat menekan "saya sudah selesai".

    Menghapus seluruh jejak sesi itu sekarang juga, tanpa menunggu UMUR_SESI:
    Excel hasil, profil perusahaan sementara, laporan, dan folder induknya.
    (PDF unggahannya sendiri sudah dihapus sejak Excel-nya jadi.)

    Sengaja tidak melempar error kalau sesinya tidak ada -- pengunjung yang
    menekan tombol dua kali, atau yang sesinya sudah kedaluwarsa duluan, tetap
    harus melihat jawaban "sudah bersih", bukan pesan gagal yang bikin ragu.
    """
    d = _sesi.pop(sesi, None)
    if d is None:
        return {"terhapus": True, "berkas": 0,
                "pesan": "Tidak ada data tersisa untuk sesi ini."}

    ruang: Path = d["ruang"]
    try:
        jumlah = sum(1 for f in ruang.rglob("*") if f.is_file())
    except OSError:
        jumlah = 0
    shutil.rmtree(ruang, ignore_errors=True)

    # laporkan apa adanya -- kalau ada yang tersisa (mis. berkas terkunci
    # Windows karena sedang dibuka), pengunjung berhak tahu
    masih_ada = ruang.exists()
    return {
        "terhapus": not masih_ada,
        "berkas": jumlah,
        "pesan": ("Semua data Anda sudah dihapus dari server."
                  if not masih_ada else
                  "Sebagian berkas tidak bisa dihapus sekarang; akan dihapus "
                  "otomatis dalam beberapa menit."),
    }


if __name__ == "__main__":
    import uvicorn
    if _YATIM:
        print(f"Dibersihkan: {_YATIM} folder sementara tertinggal dari sesi sebelumnya.")
    uvicorn.run(app, host="0.0.0.0", port=8000)
