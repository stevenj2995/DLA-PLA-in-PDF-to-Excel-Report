"""HTTP entry point. Started by run.py -- never run this file directly.

The page itself is hosted on Vercel (Frontend/), but every PDF is processed
here. Uploads never pass through Vercel: the browser posts them straight to
this backend tunnel address.

How long uploads live:
  - the PDF is deleted AS SOON AS its Excel exists (seconds)
  - the Excel is deleted after SESSION_TTL, or when the server stops
  - orphan folders from earlier runs are swept when the server starts
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

from . import pipeline, settings
from .extract import pdf_reader

# ------------------------------------------------------------------- limits
# This backend is reachable from the internet through the tunnel, so cap what
# may come in.
MAX_FILES = 10
MAX_FILE_BYTES = 15 * 1024 * 1024      # 15 MB per PDF
MAX_TOTAL_BYTES = 50 * 1024 * 1024       # 50 MB sekali proses
SESSION_TTL = 15 * 60                        # hasil dibuang setelah 15 menit
SWEEP_INTERVAL = 60                             # penyapu latar jalan tiap 1 menit

# When set, visitors must enter this code before anything is processed:
#   set ACCESS_CODE=rahasia123
# Empty means anyone holding the link can upload.
ACCESS_CODE = os.environ.get("ACCESS_CODE", "").strip()

# Extra origins allowed to call this backend (your own domain, etc.),
# comma separated in the ALLOWED_ORIGINS environment variable.
ALLOWED_ORIGINS = [
    a.strip() for a in os.environ.get("ALLOWED_ORIGINS", "").split(",") if a.strip()
]

# Always allowed:
#   - every *.vercel.app subdomain, because each deploy gets a fresh preview
#     address and your fixed domain may not exist yet
#   - localhost AND 127.0.0.1 on any port, for local testing. Both must be
#     listed: browsers treat them as DIFFERENT origins, so allowing only one
#     makes local testing fail on CORS.
ORIGIN_PATTERN = r"https://[\w-]+\.vercel\.app|http://(localhost|127\.0\.0\.1)(:\d+)?"

app = FastAPI(title="DLA to Excel Report", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ORIGIN_PATTERN,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# The pipeline swaps settings.OUTPUT_DIR/MEMORY_DIR while it runs, so only one
# request may run at a time -- otherwise two would overwrite each other.
_lock = threading.Lock()
_sessions: dict[str, dict] = {}


@contextmanager
def isolated_workspace():
    """Point OUTPUT_DIR and MEMORY_DIR at a throwaway folder.

    Trained company profiles are copied in so detection stays accurate, but
    anything learned from a visitor PDF stops at that copy and is deleted with
    it. The real Memory/ on this laptop is never touched.
    """
    original_output, original_memory = settings.OUTPUT_DIR, settings.MEMORY_DIR
    workspace = Path(tempfile.mkdtemp(prefix="dla_"))
    # set True by the caller when the folder is still needed for downloads;
    # otherwise (e.g. the run failed halfway) it is dropped immediately
    keep = {"keep": False}
    try:
        settings.OUTPUT_DIR = workspace / "OUTPUT"
        settings.MEMORY_DIR = workspace / "MEMORY"
        settings.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        if original_memory.exists():
            for f in original_memory.glob("*.json"):
                shutil.copy2(f, settings.MEMORY_DIR / f.name)
        yield workspace, keep
    finally:
        settings.OUTPUT_DIR, settings.MEMORY_DIR = original_output, original_memory
        if not keep["keep"]:
            shutil.rmtree(workspace, ignore_errors=True)


def _drop_expired_sessions() -> None:
    cutoff = time.time() - SESSION_TTL
    for sid in [s for s, d in list(_sessions.items()) if d["time"] < cutoff]:
        d = _sessions.pop(sid, None)
        if d:
            shutil.rmtree(d["workspace"], ignore_errors=True)


def _drop_all_sessions() -> None:
    """Called when the server stops -- leave nobody files behind."""
    for sid in list(_sessions):
        d = _sessions.pop(sid, None)
        if d:
            shutil.rmtree(d["workspace"], ignore_errors=True)


def _sweep_orphan_folders() -> int:
    """Drop dla_* folders no session owns any more.

    Safety net for a server that dies suddenly (power cut, laptop closed): the
    session list dies with the process, so without this sweep a visitor PDF
    folder would never be deleted.

    Only folders older than SESSION_TTL are dropped. That age limit matters:
    without it, starting a second server -- or merely importing this module
    from another script -- would wipe sessions live in the first one, and its
    visitors would suddenly see "result expired".
    """
    n = 0
    cutoff = time.time() - SESSION_TTL
    active = {str(d["workspace"]) for d in _sessions.values()}
    for f in Path(tempfile.gettempdir()).glob("dla_*"):
        if not f.is_dir() or str(f) in active:
            continue
        try:
            if f.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue
        shutil.rmtree(f, ignore_errors=True)
        n += 1
    return n


def _background_sweeper() -> None:
    # Sweeps both: expired sessions AND orphan folders. The second must not be
    # skipped -- an orphan is not in _sessions, so sweeping sessions alone
    # leaves it sitting there until the next server start, possibly days.
    while True:
        time.sleep(SWEEP_INTERVAL)
        try:
            _drop_expired_sessions()
            _sweep_orphan_folders()
        except Exception:
            pass


# Runs at import, not under __main__ -- run.py starts this through
# "uvicorn Backend.server:app", so a __main__ block would never execute and
# the cleanup would never happen.
_ORPHANS_REMOVED = _sweep_orphan_folders()

threading.Thread(target=_background_sweeper, daemon=True).start()
atexit.register(_drop_all_sessions)


def _delete_all_pdfs(workspace: Path) -> int:
    n = 0
    for f in workspace.rglob("*.pdf"):
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n


@app.get("/api/status")
def status():
    """Drives the backend-live indicator on the page."""
    try:
        template = settings.template_file().name
    except FileNotFoundError:
        template = None
    return {
        "ready": template is not None,
        "template": template,
        "ocr": pdf_reader.ocr_available(),
        "max_files": MAX_FILES,
        "max_file_mb": MAX_FILE_BYTES // (1024 * 1024),
        "needs_code": bool(ACCESS_CODE),
        "session_minutes": SESSION_TTL // 60,
    }


@app.post("/api/process")
async def process(email: str = Form(...), files: list[UploadFile] = File(...),
                 code: str = Form("")):
    # compare_digest so the check duration cannot leak how many leading
    # characters were already right
    if ACCESS_CODE and not hmac.compare_digest(code.strip(), ACCESS_CODE):
        raise HTTPException(403, "Kode akses salah.")
    if not email.strip():
        raise HTTPException(400, "Email wajib diisi.")
    if not files:
        raise HTTPException(400, "Tidak ada berkas yang diunggah.")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Maksimal {MAX_FILES} PDF sekali proses.")

    _drop_expired_sessions()

    if not _lock.acquire(blocking=False):
        raise HTTPException(
            429, "Sedang memproses permintaan lain. Coba lagi beberapa detik.")
    try:
        with isolated_workspace() as (workspace, keep):
            incoming = workspace / "INCOMING"
            incoming.mkdir(parents=True)

            total = 0
            for b in files:
                if not (b.filename or "").lower().endswith(".pdf"):
                    raise HTTPException(400, f"'{b.filename}' bukan file PDF.")
                data = await b.read()
                if len(data) > MAX_FILE_BYTES:
                    raise HTTPException(
                        400, f"'{b.filename}' lebih dari "
                             f"{MAX_FILE_BYTES // (1024*1024)} MB.")
                total += len(data)
                if total > MAX_TOTAL_BYTES:
                    raise HTTPException(400, "Total unggahan terlalu besar.")
                # using the name as given could overwrite another file or
                # escape the folder ("../"), so keep the basename only
                (incoming / Path(b.filename).name).write_bytes(data)

            result = pipeline.run(
                operator_email=email.strip(), input_folder=incoming)

            # The PDF is not needed once the Excel exists. The pipeline moved
            # it into OUTPUT/<company>/PDF/; delete it now so the document does
            # not wait for the session to expire.
            _delete_all_pdfs(workspace)

            sid = uuid.uuid4().hex
            downloads = {}
            excel_list = []
            for e in result.excel_files:
                f = Path(e["file"])
                fid = uuid.uuid4().hex[:12]
                downloads[fid] = f
                excel_list.append({
                    "id": fid,
                    "company": e["company"],
                    "rows": e["rows"],
                    "file_name": f.name,
                    "dropdowns_intact": e["dropdowns_intact"],
                    "dropdowns_after": e["dropdowns_after"],
                    "dropdowns_before": e["dropdowns_before"],
                })

            # workspace is kept until expiry so the Excel stays downloadable
            _sessions[sid] = {"workspace": workspace, "time": time.time(), "file": downloads}
            keep["keep"] = True

            return {
                "session": sid,
                "summary": {
                    "pdfs": len(result.pdfs),
                    "ok": len(result.succeeded),
                    "review": len(result.needs_review),
                    "skipped": len(result.failed),
                },
                "notes": result.notes,
                "new_companies": result.new_companies,
                "excel": excel_list,
                "review": [
                    {"file": h.path.name,
                     "company": h.company or "tidak terdeteksi",
                     "confidence": round(h.confidence, 2),
                     "warnings": h.warnings}
                    for h in result.needs_review
                ],
                "skipped": [
                    {"file": h.path.name, "reason": h.skipped}
                    for h in result.failed
                ],
            }
    finally:
        _lock.release()


@app.get("/api/download/{session}/{fid}")
def download(session: str, fid: str):
    d = _sessions.get(session)
    if not d or fid not in d["file"]:
        raise HTTPException(404, "Hasil sudah kedaluwarsa. Silakan proses ulang.")
    f: Path = d["file"][fid]
    if not f.exists():
        raise HTTPException(404, "Berkas tidak ditemukan lagi.")
    return FileResponse(
        f, filename=f.name,
        media_type="application/vnd.openxmlformats-officedocument."
                   "spreadsheetml.sheet")


@app.post("/api/finish/{session}")
def finish(session: str):
    """Called when the visitor presses "I am done".

    Deletes every trace of that session right away, without waiting for
    SESSION_TTL: the Excel, the temporary company profiles, the report, and the
    folder holding them. (The uploaded PDF went as soon as the Excel existed.)

    Deliberately does not raise when the session is gone -- someone pressing
    the button twice, or whose session already expired, should still see
    "all clear" rather than an error that leaves them unsure.
    """
    d = _sessions.pop(session, None)
    if d is None:
        return {"deleted": True, "files": 0,
                "message": "Tidak ada data tersisa untuk sesi ini."}

    workspace: Path = d["workspace"]
    try:
        count = sum(1 for f in workspace.rglob("*") if f.is_file())
    except OSError:
        count = 0
    shutil.rmtree(workspace, ignore_errors=True)

    # report honestly -- if something survived (e.g. a file Windows has locked
    # because it is open), the visitor deserves to know
    still_there = workspace.exists()
    return {
        "deleted": not still_there,
        "files": count,
        "message": ("Semua data Anda sudah dihapus dari server."
                  if not still_there else
                  "Sebagian berkas tidak bisa dihapus sekarang; akan dihapus "
                  "otomatis dalam beberapa menit."),
    }
