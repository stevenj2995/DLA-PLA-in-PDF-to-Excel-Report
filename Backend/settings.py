import os

# upload limits
MAX_FILES = 250
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_TOTAL_BYTES = 400 * 1024 * 1024
# A zip of a few hundred DLAs is the normal way in. The extracted ceiling is
# separate from the upload ceiling so a small archive cannot unpack into
# something enormous.
MAX_ZIP_BYTES = 200 * 1024 * 1024
MAX_EXTRACTED_BYTES = 600 * 1024 * 1024
SESSION_MINUTES = 15

ACCESS_CODE = os.environ.get("ACCESS_CODE", "").strip()

TESSERACT_PATH = None
OCR_LANGUAGES = "ind+eng"
OCR_DPI = 300
OCR_PSM = 6
SCANNED_PAGE_CHARS = 120
OCR_WORKERS = min(8, (os.cpu_count() or 2))
