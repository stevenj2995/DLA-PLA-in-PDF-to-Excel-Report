from __future__ import annotations
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

PORT = 8000
ROOT = Path(__file__).parent
VERCEL_SITE = "https://dla-pla-pdf-to-excel-report.vercel.app"


def check_setup() -> bool:
    from Backend import profiles
    from Backend.extract.pdf_reader import find_tesseract, ocr_available

    print("Perusahaan didukung:", ", ".join(p.name for p in profiles.ALL))
    drafts = [p.name for p in profiles.DRAFTS]
    if drafts:
        print("Belum aktif (menunggu ditinjau):", ", ".join(drafts))

    if ocr_available():
        print("OCR:", "AKTIF -", find_tesseract())
    else:
        print("OCR: TIDAK AKTIF - PDF hasil pindaian akan dilewati")
        print("     pasang dengan: winget install --id UB-Mannheim.TesseractOCR")

    # this script can open a public tunnel, so an empty code matters
    if os.environ.get("ACCESS_CODE", "").strip():
        print("Kode akses: AKTIF")
    else:
        print("Kode akses: BELUM DIPASANG - siapa pun yang punya tautannya bisa mengunggah")
        print("            pasang dengan: set ACCESS_CODE=kode-anda")
    return True


_CLOUDFLARED_CANDIDATES = (
    r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    r"C:\Program Files\cloudflared\cloudflared.exe",
)


def find_cloudflared() -> str | None:
    """winget puts it on the machine PATH, which a terminal opened before the
    install will not have picked up yet."""
    found = shutil.which("cloudflared")
    if found:
        return found
    return next((p for p in _CLOUDFLARED_CANDIDATES if Path(p).exists()), None)


def start_server() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "Backend.server:app",
         "--host", "0.0.0.0", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(ROOT),
    )


def start_tunnel(exe: str) -> tuple[subprocess.Popen, str | None]:
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


def main() -> int:
    print()
    print("DLA to Excel")
    print()
    if not check_setup():
        return 1

    print()
    print("Menyalakan server...")
    server = start_server()
    time.sleep(3)
    if server.poll() is not None:
        print("Server gagal menyala.")
        return 1

    bar = "=" * 62
    print()
    print(bar)
    print(" BUKA DI BROWSER:")
    print(f"   http://localhost:{PORT}")
    print(bar)

    exe = find_cloudflared()
    tunnel = None
    if exe:
        print()
        print("Membuka terowongan ke internet...")
        tunnel, url = start_tunnel(exe)
        if not url:
            print("Terowongan gagal dibuka. Yang di laptop ini tetap jalan.")
        else:
            print()
            print(bar)
            print(" LEWAT VERCEL - klik tautan ini:")
            print(f"   {VERCEL_SITE}/?api={url}")
            print()
            print(" Alamat terowongan berubah tiap run.py dijalankan, jadi pakai")
            print(" tautan di atas lagi setiap kali. Browser mengingatnya.")
            print()
            print(" Tanpa Vercel, halaman yang sama juga ada di:")
            print(f"   {url}")
            print(bar)
    else:
        print()
        print("Cloudflared belum terpasang, jadi baru bisa dipakai dari laptop ini.")
        print("  winget install --id Cloudflare.cloudflared")

    print()
    print("Backend AKTIF. Ctrl+C untuk mematikan.")
    print()
    try:
        server.wait()
    except KeyboardInterrupt:
        print()
        print("Mematikan backend...")
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
