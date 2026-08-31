from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from Backend import settings

PORT = 8000
WEB_CONFIG_FILE = Path(__file__).parent / "Frontend" / "config.js"


def check_setup() -> bool:
    ok = True
    try:
        print(f"  [OK]   Template standar : {settings.template_file().name}")
    except FileNotFoundError:
        print(f"  [GAGAL] Tidak ada file .xlsx di folder {settings.TEMPLATE_DIR}")
        ok = False

    from Backend.extract.pdf_reader import ocr_available
    if ocr_available():
        print("  [OK]   OCR (Tesseract)   : aktif")
    else:
        print("  [!]    OCR (Tesseract)   : tidak aktif -- PDF hasil pindaian "
              "tidak akan terbaca")

    import os
    if os.environ.get("ACCESS_CODE", "").strip():
        print("  [OK]   Kode akses        : aktif -- hanya yang tahu kode bisa "
              "mengunggah")
    else:
        print("  [!]    Kode akses        : TIDAK dipasang -- siapa pun yang "
              "punya tautannya bisa")
        print("                             mengunggah. Pasang dengan: "
              "set ACCESS_CODE=kode-anda")
    return ok


def start_server() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "Backend.server:app",
         "--host", "0.0.0.0", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(Path(__file__).parent),
    )


def start_tunnel(exe: str) -> tuple[subprocess.Popen, str | None]:
    """Start cloudflared and capture the public URL it prints."""
    p = subprocess.Popen(
        [exe, "tunnel", "--url", f"http://localhost:{PORT}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    url: list[str | None] = [None]

    def reader():
        pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
        for line in p.stdout:
            if url[0] is None:
                m = pattern.search(line)
                if m:
                    url[0] = m.group(0)

    threading.Thread(target=reader, daemon=True).start()
    for _ in range(60):
        if url[0]:
            break
        time.sleep(0.5)
    return p, url[0]


def update_web_config(url: str) -> bool:
    """Write the tunnel URL into Frontend/config.js, ready to commit and push."""
    if not WEB_CONFIG_FILE.exists():
        return False
    content = WEB_CONFIG_FILE.read_text(encoding="utf-8")
    updated = re.sub(r'window\.BACKEND_URL\s*=\s*"[^"]*";',
                  f'window.BACKEND_URL = "{url}";', content)
    if updated == content:
        return False
    WEB_CONFIG_FILE.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    print("\n=== DLA to Excel Report -- penyala backend ===\n")
    print("Memeriksa persiapan:")
    if not check_setup():
        print("\nAda yang belum siap. Perbaiki dulu, lalu jalankan ulang.")
        return 1

    print("\nMenyalakan server...")
    server = start_server()
    time.sleep(3)
    if server.poll() is not None:
        print("Server gagal menyala. Coba jalankan 'python server.py' untuk "
              "melihat pesan errornya.")
        return 1
    print(f"  Server jalan di http://localhost:{PORT}")

    exe = shutil.which("cloudflared")
    tunnel = None
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
        tunnel, url = start_tunnel(exe)
        if not url:
            print("  Terowongan gagal memberi URL. Cek koneksi internet.")
        else:
            written = update_web_config(url)
            print("\n==============================================================")
            print(" ALAMAT BACKEND PUBLIK:")
            print(f"   {url}")
            print("")
            if written:
                print(" Frontend/config.js sudah otomatis diperbarui.")
                print(" Supaya website Vercel memakai alamat ini, jalankan:")
                print("")
                print('   git add Frontend/config.js && git commit -m "alamat backend baru"')
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
        for p in (tunnel, server):
            if p and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
