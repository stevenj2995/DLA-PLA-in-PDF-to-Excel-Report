from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path

PORT = 8000
ROOT = Path(__file__).parent

# Loopback on purpose. 0.0.0.0 would also answer everyone else on the office
# wifi, and what goes through here are real claim documents.
HOST = "127.0.0.1"


def check_setup() -> None:
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


def start_server() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "Backend.server:app",
         "--host", HOST, "--port", str(PORT), "--log-level", "warning"],
        cwd=str(ROOT),
    )


def main() -> int:
    print()
    print("DLA to Excel")
    print()
    check_setup()

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
    print()
    print(" Halaman dan pemrosesan ada di alamat yang sama, di laptop ini")
    print(" saja. Tidak ada yang keluar ke internet.")
    print(bar)
    print()
    print("Ctrl+C untuk mematikan.")
    print()

    try:
        server.wait()
    except KeyboardInterrupt:
        print()
        print("Mematikan backend...")
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
