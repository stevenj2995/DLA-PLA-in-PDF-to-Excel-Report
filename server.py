"""Backend untuk website publik. Jalankan di laptop ini: python server.py

Halaman webnya sendiri di-host di Vercel (folder web/), tapi semua pemrosesan
PDF terjadi di sini. Tidak ada dokumen yang disimpan permanen: setiap permintaan
dikerjakan di folder sementara yang langsung dihapus setelah diunduh.
"""
from __future__ import annotations

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
UMUR_SESI = 30 * 60                        # hasil dibuang setelah 30 menit

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
    for sid in [s for s, d in _sesi.items() if d["waktu"] < batas]:
        shutil.rmtree(_sesi.pop(sid)["ruang"], ignore_errors=True)


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
    }


@app.post("/api/proses")
async def proses(email: str = Form(...), berkas: list[UploadFile] = File(...)):
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
