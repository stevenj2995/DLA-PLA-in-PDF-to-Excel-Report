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
WEB_CONFIG = ROOT / "Frontend" / "config.js"


def check_setup() -> bool:
    from Backend import profiles
    print("Perusahaan didukung:", ", ".join(p.name for p in profiles.ALL))
    drafts = [p.name for p in profiles.DRAFTS]
    if drafts:
        print("Belum aktif (menunggu ditinjau):", ", ".join(drafts))

    # this script always tries to open a public tunnel, so an empty code matters
    if os.environ.get("ACCESS_CODE", "").strip():
        print("Kode akses: AKTIF")
    else:
        print("Kode akses: BELUM DIPASANG - siapa pun yang punya tautannya bisa mengunggah")
        print("            pasang dengan: set ACCESS_CODE=kode-anda")
    return True


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


def update_web_config(url: str) -> bool:
    if not WEB_CONFIG.exists():
        return False
    text = WEB_CONFIG.read_text(encoding="utf-8")
    updated = re.sub(r'window\.BACKEND_URL\s*=\s*"[^"]*";',
                     f'window.BACKEND_URL = "{url}";', text)
    if updated == text:
        return False
    WEB_CONFIG.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    print("\nDLA to Excel\n")
    if not check_setup():
        return 1

    print("\nMenyalakan server...")
    server = start_server()
    time.sleep(3)
    if server.poll() is not None:
        print("Server gagal menyala.")
        return 1
    print(f"Server aktif di: http://localhost:{PORT}")

    exe = shutil.which("cloudflared")
    tunnel = None
    if not exe:
        print("\nCloudflared belum terpasang, jadi backend hanya bisa diakses dari laptop ini.")
        print("  winget install --id Cloudflare.cloudflared")
    else:
        print("\nMembuka terowongan ke internet...")
        tunnel, url = start_tunnel(exe)
        if not url:
            print("Terowongan gagal dibuka. Periksa koneksi internet.")
        else:
            written = update_web_config(url)
            print("\n" + "=" * 62)
            print(" ALAMAT BACKEND PUBLIK:")
            print(f"   {url}")
            if written:
                print("\n Frontend/config.js sudah diperbarui otomatis.")
                print(" Deploy ulang Vercel supaya halaman publik memakai alamat ini.")
            print("=" * 62)

    print("\nBackend AKTIF. Ctrl+C untuk mematikan.\n")
    try:
        server.wait()
    except KeyboardInterrupt:
        print("\nMematikan backend...")
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
