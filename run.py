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
        print(f"Template standar : {settings.template_file().name}")
    except FileNotFoundError:
        print(f"Tidak ada file excel di folder! {settings.TEMPLATE_DIR}")
        ok = False

    from Backend.extract.pdf_reader import ocr_available
    if ocr_available():
        print("Status OCR: AKTIF")
    else:
        print("Status OCR: TIDAK AKTIF")

    return ok


def start_server() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "Backend.server:app",
         "--host", "0.0.0.0", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(Path(__file__).parent),
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


def update_web_config(url: str) -> bool:
    if not WEB_CONFIG_FILE.exists():
        return False
    content = WEB_CONFIG_FILE.read_text(encoding="utf-8")
    updated = re.sub(r'window\.BACKEND_URL\s*=\s*"[^"]*";', f'window.BACKEND_URL = "{url}";', content)
    if updated == content:
        return False
    WEB_CONFIG_FILE.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    print("\nDLA/PLA to Excel Report\n")
    print("Checking:")
    if not check_setup():
        print("\nAda yang belum siap.")
        return 1

    print("\nStarting server...")
    server = start_server()
    time.sleep(3)
    if server.poll() is not None:
        print("Server gagal menyala.")
        return 1
    print(f"Server online at: http://localhost:{PORT}")

    exe = shutil.which("cloudflared")
    tunnel = None
    if not exe:
        print("\n--------------------------------------------------------------")
        print("Cloudflared belum terpasang")
        print("winget install --id Cloudflare.cloudflared")
        print("")
        print("--------------------------------------------------------------")
    else:
        print("\nOpening tunnel to the internet...")
        tunnel, url = start_tunnel(exe)
        if not url:
            print("Failed to open tunnel. Check your internet connection!")
        else:
            written = update_web_config(url)
            print("\n==============================================================")
            print(" ALAMAT BACKEND PUBLIK:")
            print(f"   {url}")
            print("")
            if written:
                print(" Frontend/config.js updated automatically.")
            print("==============================================================")

    print("\nBackend is ACTIVE. Ctrl+C to TURN OFF.\n")
    try:
        server.wait()
    except KeyboardInterrupt:
        print("\nTurning off backend...")
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
