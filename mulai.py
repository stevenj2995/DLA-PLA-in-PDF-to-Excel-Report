"""Penyala backend untuk website publik. Jalankan: python mulai.py

Skrip ini menyalakan dua hal sekaligus:
  1. server.py  -- yang benar-benar memproses PDF, di laptop ini
  2. terowongan -- supaya server itu bisa dihubungi dari halaman Vercel

Selama jendela ini terbuka, websitenya hidup. Begitu ditutup, website akan
menampilkan "Backend sedang tidak aktif" -- itu memang perilaku yang diharapkan.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from src import config

PORT = 8000
BERKAS_CONFIG_WEB = Path(__file__).parent / "web" / "config.js"


def cek_persiapan() -> bool:
    ok = True
    try:
        print(f"  [OK]   Template standar : {config.file_standar().name}")
    except FileNotFoundError:
        print(f"  [GAGAL] Tidak ada file .xlsx di folder {config.STANDAR_DIR}")
        ok = False

    from src.pdf_reader import ocr_tersedia
    if ocr_tersedia():
        print("  [OK]   OCR (Tesseract)   : aktif")
    else:
        print("  [!]    OCR (Tesseract)   : tidak aktif -- PDF hasil pindaian "
              "tidak akan terbaca")

    import os
    if os.environ.get("KODE_AKSES", "").strip():
        print("  [OK]   Kode akses        : aktif -- hanya yang tahu kode bisa "
              "mengunggah")
    else:
        print("  [!]    Kode akses        : TIDAK dipasang -- siapa pun yang "
              "punya tautannya bisa")
        print("                             mengunggah. Pasang dengan: "
              "set KODE_AKSES=kode-anda")
    return ok


def jalankan_server() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app",
         "--host", "0.0.0.0", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(Path(__file__).parent),
    )


def jalankan_terowongan(exe: str) -> tuple[subprocess.Popen, str | None]:
    """Nyalakan cloudflared dan tangkap URL publik yang dicetaknya."""
    p = subprocess.Popen(
        [exe, "tunnel", "--url", f"http://localhost:{PORT}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    url: list[str | None] = [None]

    def baca():
        pola = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
        for baris in p.stdout:
            if url[0] is None:
                m = pola.search(baris)
                if m:
                    url[0] = m.group(0)

    threading.Thread(target=baca, daemon=True).start()
    for _ in range(60):
        if url[0]:
            break
        time.sleep(0.5)
    return p, url[0]


def perbarui_config_web(url: str) -> bool:
    """Tulis URL terowongan ke web/config.js supaya tinggal commit & push."""
    if not BERKAS_CONFIG_WEB.exists():
        return False
    isi = BERKAS_CONFIG_WEB.read_text(encoding="utf-8")
    baru = re.sub(r'window\.ALAMAT_BACKEND\s*=\s*"[^"]*";',
                  f'window.ALAMAT_BACKEND = "{url}";', isi)
    if baru == isi:
        return False
    BERKAS_CONFIG_WEB.write_text(baru, encoding="utf-8")
    return True


def main() -> int:
    print("\n=== DLA to Excel Report -- penyala backend ===\n")
    print("Memeriksa persiapan:")
    if not cek_persiapan():
        print("\nAda yang belum siap. Perbaiki dulu, lalu jalankan ulang.")
        return 1

    print("\nMenyalakan server...")
    server = jalankan_server()
    time.sleep(3)
    if server.poll() is not None:
        print("Server gagal menyala. Coba jalankan 'python server.py' untuk "
              "melihat pesan errornya.")
        return 1
    print(f"  Server jalan di http://localhost:{PORT}")

    exe = shutil.which("cloudflared")
    terowongan = None
    if not exe:
        print("\n--------------------------------------------------------------")
        print(" cloudflared belum terpasang, jadi backend ini baru bisa")
        print(" dihubungi dari laptop ini saja. Untuk membukanya ke internet:")
        print("")
        print("   winget install --id Cloudflare.cloudflared")
        print("")
        print(" lalu jalankan ulang skrip ini.")
        print("--------------------------------------------------------------")
        print("\n Sementara itu kamu tetap bisa menguji halaman webnya secara")
        print(" lokal (lihat README bagian 'Uji coba di laptop sendiri').")
    else:
        print("\nMembuka terowongan ke internet...")
        terowongan, url = jalankan_terowongan(exe)
        if not url:
            print("  Terowongan gagal memberi URL. Cek koneksi internet.")
        else:
            ditulis = perbarui_config_web(url)
            print("\n==============================================================")
            print(" ALAMAT BACKEND PUBLIK:")
            print(f"   {url}")
            print("")
            if ditulis:
                print(" web/config.js sudah otomatis diperbarui.")
                print(" Supaya website Vercel memakai alamat ini, jalankan:")
                print("")
                print('   git add web/config.js && git commit -m "alamat backend baru"')
                print("   git push")
                print("")
            print(" Atau tanpa deploy ulang, buka halamanmu dengan tambahan:")
            print(f"   ?api={url}")
            print("==============================================================")

    print("\nBackend aktif. Tekan Ctrl+C untuk mematikan.\n")
    try:
        server.wait()
    except KeyboardInterrupt:
        print("\nMematikan...")
    finally:
        for p in (terowongan, server):
            if p and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
