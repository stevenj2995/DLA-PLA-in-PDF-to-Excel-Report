
from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .. import settings
from ..extract.text import folder_name, group_name, normalize

MOVE_LOG_NAME = "_catatan_pemindahan.jsonl"


def _log_move(entry: dict) -> None:
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with (settings.OUTPUT_DIR / MOVE_LOG_NAME).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

# add a number when the name is taken, so nothing gets overwritten
def _free_name(destination: Path) -> Path:
    if not destination.exists():
        return destination
    stem, suffix = destination.stem, destination.suffix
    for i in range(2, 1000):
        candidate = destination.with_name(f"{stem} ({i}){suffix}")
        if not candidate.exists():
            return candidate
    return destination.with_name(f"{stem} ({datetime.now():%H%M%S}){suffix}")


def move_pdf(pdf: Path, target_folder: Path, *, reason: str = "") -> Path:
    target_folder.mkdir(parents=True, exist_ok=True)
    destination = _free_name(target_folder / pdf.name)
    shutil.move(str(pdf), str(destination))
    _log_move({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "from": str(pdf),
        "to": str(destination),
        "reason": reason,
    })
    return destination


def company_folder(group: str, entitas: str) -> Path:
    return settings.OUTPUT_DIR / folder_name(group) / folder_name(entitas)


def undetected_folder() -> Path:
    return settings.OUTPUT_DIR / settings.FOLDER_TIDAK_TERDETEKSI


def list_pdfs(folder: Path) -> list[Path]:
    folder = Path(folder)
    if not folder.exists():
        return []
    return sorted(p for p in folder.rglob("*.pdf")
                  if p.is_file() and not p.name.startswith("~"))

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _file_name(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_").lower() or "tanpa_nama"


@dataclass
class Profile:
    official_name: str
    key: str = ""
    group: str = ""
    folder: str = ""
    aliases: list[str] = field(default_factory=list)
    parameter_map: dict[str, dict] = field(default_factory=dict)
    unmatched: dict[str, str] = field(default_factory=dict)
    pdf_count: int = 0
    processed_refs: list[str] = field(default_factory=list)
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)
    note: str = ("File ini boleh diedit manual. Ubah 'grup' atau 'folder' "
                    "kalau sistem salah menempatkan, lalu simpan.")

    def __post_init__(self):
        self.key = self.key or normalize(self.official_name)
        self.group = self.group or group_name(self.official_name)
        self.folder = self.folder or folder_name(self.official_name)
        if self.official_name not in self.aliases:
            self.aliases.insert(0, self.official_name)

    def add_alias(self, name: str) -> bool:
        if name and name not in self.aliases:
            self.aliases.append(name)
            return True
        return False

    def remember_parameter(self, pdf_param: str, column: str, method: str, score: float) -> None:
        self.parameter_map[pdf_param] = {
            "column": column, "method": method, "score": round(float(score), 3),
            "recorded": _now(),
        }
        self.unmatched.pop(pdf_param, None)

    def remember_unmatched(self, pdf_param: str, reason: str) -> None:
        if pdf_param not in self.parameter_map:
            self.unmatched[pdf_param] = f"N/A: {reason}"

    def column_for(self, pdf_param: str) -> str | None:
        entry = self.parameter_map.get(pdf_param)
        return entry["column"] if entry else None


class ProfileStore:
    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory or settings.MEMORY_DIR)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Profile] = {}
        self._load_all()

    def _load_all(self) -> None:
        for f in self.directory.glob("*.json"):
            try:
                p = Profile(**json.loads(f.read_text(encoding="utf-8")))
                self._cache[p.key] = p
            except Exception:
                continue  # corrupt file

    def all_profiles(self) -> list[Profile]:
        return sorted(self._cache.values(), key=lambda p: p.official_name)

    def find(self, name: str) -> Profile | None:
        key = normalize(name)
        if key in self._cache:
            return self._cache[key]
        for p in self._cache.values():
            if any(normalize(a) == key for a in p.aliases):
                return p
        return None
    
    def get_or_create(self, name: str) -> tuple[Profile, bool]:
        existing = self.find(name)
        if existing:
            if existing.add_alias(name):
                self.save(existing)
            return existing, False
        p = Profile(official_name=name)
        self._cache[p.key] = p
        self.save(p)
        return p, True

    def save(self, p: Profile) -> Path:
        p.updated = _now()
        f = self.directory / f"{_file_name(p.key)}.json"
        f.write_text(json.dumps(asdict(p), indent=2, ensure_ascii=False),
                     encoding="utf-8")
        return f
