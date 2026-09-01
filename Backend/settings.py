import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "Output"

# upload limits
MAX_FILES = 250
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_TOTAL_BYTES = 400 * 1024 * 1024
SESSION_MINUTES = 15

ACCESS_CODE = os.environ.get("ACCESS_CODE", "").strip()
