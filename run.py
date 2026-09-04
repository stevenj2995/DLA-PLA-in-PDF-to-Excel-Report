from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path

PORT = 8000
ROOT = Path(__file__).parent

HOST = "127.0.0.1"


def check_setup() -> None:
    from Backend import profiles
    from Backend.extract.pdf_reader import find_tesseract, ocr_available

    drafts = [p.name for p in profiles.DRAFTS]

    if ocr_available():
        print("Status OCR:", "AKTIF -", find_tesseract())
    else:
        print("Status OCR: TIDAK AKTIF")

def start_server() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "Backend.server:app",
         "--host", HOST, "--port", str(PORT), "--log-level", "warning"],
        cwd=str(ROOT),
    )


def main() -> int:
    print("DLA to Excel")
    check_setup()

    print()
    print("Turning server on...")
    server = start_server()
    time.sleep(3)
    if server.poll() is not None:
        print("Server failed to turn on!")
        return 1

    bar = "=" * 62
    print()
    print(bar)
    print("BUKA DI BROWSER:")
    print()
    print(f"http://localhost:{PORT}")
    print()
    print("Press Ctrl+C to turn off server.")
    print(bar)

    try:
        server.wait()
    except KeyboardInterrupt:
        print()
        print("Turning off backend")
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
