from __future__ import annotations
import hmac
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import pipeline, profiles, settings
from .extract.pdf_reader import ocr_available

# Local use only. The page is served by this same process, so nothing legitimate
# calls in from another origin -- and a public origin has no business here.
ORIGIN_PATTERN = r"http://(localhost|127\.0\.0\.1)(:\d+)?"

app = FastAPI(title="DLA to Excel", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=ORIGIN_PATTERN,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_lock = threading.Lock()
_sessions: dict[str, dict] = {}


def _drop_expired() -> None:
    cutoff = time.time() - settings.SESSION_MINUTES * 60
    for sid in [s for s, d in list(_sessions.items()) if d["time"] < cutoff]:
        data = _sessions.pop(sid, None)
        if data:
            shutil.rmtree(data["workspace"], ignore_errors=True)


@app.get("/api/status")
def status():
    _drop_expired()
    return {
        "ok": True,
        "max_files": settings.MAX_FILES,
        "max_file_mb": settings.MAX_FILE_BYTES // (1024 * 1024),
        "session_minutes": settings.SESSION_MINUTES,
        "needs_code": bool(settings.ACCESS_CODE),
        "ocr": ocr_available(),
        "companies": [{"key": p.key, "name": p.name} for p in profiles.ALL],
    }


@app.post("/api/process")
async def process(
    files: list[UploadFile] = File(...),
    code: str = Form(""),
    on_mismatch: str = Form("merge"),
):
    if settings.ACCESS_CODE and not hmac.compare_digest(code.strip(), settings.ACCESS_CODE):
        raise HTTPException(status_code=403, detail="Kode akses salah.")
    if not files:
        raise HTTPException(status_code=400, detail="Tidak ada berkas yang diunggah.")
    if len(files) > settings.MAX_FILES:
        raise HTTPException(status_code=400,
                            detail=f"Maksimal {settings.MAX_FILES} PDF sekali proses.")

    _drop_expired()
    workspace = Path(tempfile.mkdtemp(prefix="dla_"))
    incoming = workspace / "in"
    incoming.mkdir(parents=True, exist_ok=True)

    total = 0
    saved: list[Path] = []
    try:
        for item in files:
            if not (item.filename or "").lower().endswith(".pdf"):
                continue
            body = await item.read()
            total += len(body)
            if len(body) > settings.MAX_FILE_BYTES or total > settings.MAX_TOTAL_BYTES:
                shutil.rmtree(workspace, ignore_errors=True)
                raise HTTPException(status_code=400, detail="Ukuran unggahan melebihi batas.")
            target = incoming / Path(item.filename).name
            target.write_bytes(body)
            saved.append(target)

        if not saved:
            shutil.rmtree(workspace, ignore_errors=True)
            raise HTTPException(status_code=400, detail="Tidak ada berkas PDF yang sah.")

        batch = pipeline.run(saved, on_mismatch=on_mismatch)
        out = pipeline.to_excel(batch, workspace / "out")
    except HTTPException:
        raise
    except Exception as e:
        shutil.rmtree(workspace, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Gagal memproses: {e}") from e
    finally:
        # the PDFs have been read; they do not stay on disk any longer
        shutil.rmtree(incoming, ignore_errors=True)

    session = uuid.uuid4().hex
    file_id = uuid.uuid4().hex
    with _lock:
        _sessions[session] = {
            "time": time.time(),
            "workspace": workspace,
            "files": {file_id: out} if out else {},
        }

    return {
        "session": session,
        "company": batch.profile.name if batch.profile else None,
        "rejected": batch.rejected,
        "summary": {
            "pdfs": len(batch.files),
            "rows": len(batch.rows),
            "columns": len(batch.headers),
            "skipped": len(batch.skipped),
            "deviating": len(batch.deviating),
        },
        "headers": batch.headers,
        "preview": batch.rows[:5],
        "notes": batch.notes,
        "skipped": [{"file": f.name, "reason": f.reason} for f in batch.skipped],
        "scanned": [f.name for f in batch.scanned],
        "deviating": [{"file": f.name, "missing": f.missing,
                       "extra": sorted(f.extra)} for f in batch.deviating],
        "excel": ({"id": file_id, "file_name": out.name, "rows": len(batch.rows),
                   "columns": len(batch.headers)} if out else None),
    }


@app.get("/api/download/{session}/{file_id}")
def download(session: str, file_id: str):
    _drop_expired()
    data = _sessions.get(session)
    if not data or file_id not in data.get("files", {}):
        raise HTTPException(status_code=404, detail="Berkas sudah tidak tersedia.")
    path: Path = data["files"][file_id]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Berkas sudah dihapus.")
    return FileResponse(
        path, filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/finish/{session}")
def finish(session: str):
    data = _sessions.pop(session, None)
    if data is None:
        return {"deleted": True, "files": 0,
                "message": "Tidak ada data tersisa untuk sesi ini."}
    workspace: Path = data["workspace"]
    try:
        count = sum(1 for f in workspace.rglob("*") if f.is_file())
    except OSError:
        count = 0
    shutil.rmtree(workspace, ignore_errors=True)
    gone = not workspace.exists()
    return {
        "deleted": gone,
        "files": count,
        "message": ("Semua data Anda sudah dihapus dari server." if gone else
                    "Sebagian berkas belum bisa dihapus; akan terhapus otomatis "
                    "dalam beberapa menit."),
    }


# The page is served by the backend itself, so it always talks to the API on its
# own origin -- nothing to configure, and no CORS involved. Mounted last so the
# /api routes above keep priority.
FRONTEND = Path(__file__).resolve().parent.parent / "Frontend"
if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
