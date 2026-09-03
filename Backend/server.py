from __future__ import annotations
import hmac
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
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


def _unpack_zip(archive: Path, into: Path) -> list[Path]:
    """PDFs out of an archive, ignoring how the sender organised it.

    Only the bare file name is used, never the path recorded inside the archive,
    so an entry named ../../something cannot write outside the workspace. Sizes
    are checked against the declared header before anything is written, which is
    what stops a small archive unpacking into an enormous one.
    """
    out: list[Path] = []
    total = 0
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if not name.lower().endswith(".pdf") or name.startswith("."):
                continue
            if len(out) >= settings.MAX_FILES:
                break
            total += info.file_size
            if info.file_size > settings.MAX_FILE_BYTES or total > settings.MAX_EXTRACTED_BYTES:
                raise HTTPException(status_code=400,
                                    detail="Isi ZIP melebihi batas ukuran.")
            target = into / name
            stem, suffix, n = target.stem, target.suffix, 2
            while target.exists():
                target = into / f"{stem} ({n}){suffix}"
                n += 1
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            out.append(target)
    return out


async def _collect(files: list[UploadFile], into: Path) -> list[Path]:
    saved: list[Path] = []
    total = 0
    for item in files:
        name = Path(item.filename or "").name
        lowered = name.lower()
        if not (lowered.endswith(".pdf") or lowered.endswith(".zip")):
            continue
        body = await item.read()
        total += len(body)
        ceiling = settings.MAX_ZIP_BYTES if lowered.endswith(".zip") else settings.MAX_FILE_BYTES
        if len(body) > ceiling or total > settings.MAX_TOTAL_BYTES:
            raise HTTPException(status_code=400, detail="Ukuran unggahan melebihi batas.")

        if lowered.endswith(".zip"):
            archive = into / name
            archive.write_bytes(body)
            try:
                saved.extend(_unpack_zip(archive, into))
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400,
                                    detail=f"{name} bukan berkas ZIP yang sah.") from None
            finally:
                archive.unlink(missing_ok=True)
        else:
            target = into / name
            target.write_bytes(body)
            saved.append(target)
    return saved[: settings.MAX_FILES]


def _summary(batch) -> dict:
    return {
        "pdfs": len(batch.files),
        "rows": batch.total_rows,
        "tables": len(batch.groups),
        "skipped": len(batch.skipped),
    }


def _skipped_by_reason(batch) -> list[dict]:
    """Twenty files skipped for the same reason is one line, not twenty cards."""
    grouped: dict[str, list[str]] = {}
    for f in batch.skipped:
        grouped.setdefault(f.reason, []).append(f.name)
    return [{"reason": reason, "files": names}
            for reason, names in sorted(grouped.items(), key=lambda x: -len(x[1]))]


def _report(batch, session: str, file_id: str | None, out: Path | None) -> dict:
    return {
        "session": session,
        "company": batch.profile.name if batch.profile else None,
        "rejected": batch.rejected,
        "summary": _summary(batch),
        "groups": [{"caption": g.caption, "headers": g.headers,
                    "preview": g.rows[:5], "rows": len(g.rows)}
                   for g in batch.groups],
        "notes": [{"text": n.text, "detail": n.detail, "level": n.level}
                  for n in batch.notes],
        "skipped": _skipped_by_reason(batch),
        "excel": ({"id": file_id, "file_name": out.name, "rows": batch.total_rows,
                   "tables": len(batch.groups)} if out else None),
    }


def _finish_batch(batch, session: str, workspace: Path) -> dict:
    out = pipeline.to_excel(batch, workspace / "out")
    file_id = uuid.uuid4().hex if out else None
    with _lock:
        _sessions[session] = {"time": time.time(), "workspace": workspace,
                              "files": {file_id: out} if out else {}, "batch": None}
    return _report(batch, session, file_id, out)


@app.get("/api/status")
def status():
    _drop_expired()
    return {
        "ok": True,
        "max_files": settings.MAX_FILES,
        "max_file_mb": settings.MAX_FILE_BYTES // (1024 * 1024),
        "max_zip_mb": settings.MAX_ZIP_BYTES // (1024 * 1024),
        "session_minutes": settings.SESSION_MINUTES,
        "needs_code": bool(settings.ACCESS_CODE),
        "ocr": ocr_available(),
        "companies": [{"key": p.key, "name": p.name} for p in profiles.ALL],
        "drafts": [{"key": p.key, "name": p.name} for p in profiles.DRAFTS],
    }


@app.post("/api/process")
async def process(
    files: list[UploadFile] = File(...),
    company: str = Form(""),
    code: str = Form(""),
):
    if settings.ACCESS_CODE and not hmac.compare_digest(code.strip(), settings.ACCESS_CODE):
        raise HTTPException(status_code=403, detail="Kode akses salah.")
    if company and profiles.by_key(company) is None:
        raise HTTPException(status_code=400, detail="Perusahaan tidak dikenali.")

    _drop_expired()
    workspace = Path(tempfile.mkdtemp(prefix="dla_"))
    incoming = workspace / "in"
    incoming.mkdir(parents=True, exist_ok=True)

    try:
        saved = await _collect(files, incoming)
        if not saved:
            raise HTTPException(status_code=400,
                                detail="Tidak ada PDF di dalam yang diunggah.")
        batch = pipeline.run(saved, profile_key=company or None)
    except HTTPException:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(workspace, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Gagal memproses: {e}") from e
    finally:
        # the PDFs have been read; they do not stay on disk any longer
        shutil.rmtree(incoming, ignore_errors=True)

    # Uneven parameters used to stop here and ask whether to merge or refuse.
    # They no longer pollute anything: each set of parameters becomes its own
    # table in the sheet, so there is nothing left to decide.
    return _finish_batch(batch, uuid.uuid4().hex, workspace)


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
# own origin. Mounted last so the /api routes above keep priority.
FRONTEND = Path(__file__).resolve().parent.parent / "Frontend"
if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
