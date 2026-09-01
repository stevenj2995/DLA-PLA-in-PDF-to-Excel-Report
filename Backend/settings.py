import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "Template"
OUTPUT_DIR = ROOT / "Output"
MEMORY_DIR = ROOT / "Memory"

UNDETECTED_FOLDER = "_TIDAK_TERDETEKSI"
PDF_SUBFOLDER = "PDF"

# layout of the standard sheet
MAIN_SHEET = "MosyClaimTask"
GROUP_ROW = 2
HEADER_ROW = 3
FLAG_ROW = 4
FIRST_DATA_ROW = 5

# what each column is for
COLUMNS_FROM_PDF = ["B", "H", "V", "Y", "AB", "AC", "AP", "AQ", "BT"]

CONSTANT_COLUMNS = {
    "F": "CPM - Heavy Equipment - CPM",
    "N": None,   # the operator's own email, asked for when the service is used
    "U": "Occurrence",
    "W": "Partial Loss Accident",
    "AI": "COMP - Comprehensive",
}

OPERATOR_EMAIL_COLUMN = "N"
ROW_NUMBER_COLUMN = "A"
UNIQUE_REF_COLUMN = "Y"
INSURED_NAME_COLUMN = "H"   # Reported Name, filled from detection
# Investigation & Conclusion and Discount are both left blank, so nothing is
# written as a formula any more. The mechanism stays for whenever one comes back.
FORMULA_COLUMNS: dict[str, str] = {}

EMPTY_COLUMNS = [
    "G", "J", "K", "L", "M", "P", "Q", "R", "X", "AE", "AG", "AH", "AJ",
    "AS", "AU", "AV", "AW", "AX", "AY", "AZ", "BH", "BI", "BK", "BL", "BM",
]
MONITORING_COLUMNS = ["BN", "BO", "BP", "BQ", "BR", "BS"]
# read from the document when it is there, left blank when it is not -- no
# "N/A" marker is written into these
DEFERRED_COLUMNS = ["BT", "AC"]
FEE_COLUMNS = ["BB", "BC", "BD", "BE", "BF", "BG", "BJ"]

# detection confidence thresholds
CONFIDENT = 0.85
UNSURE = 0.60

# How close a PDF parameter must be to a column before its value is written.
# At 0.60 the matcher accepted things like 'Loss Adjuster' as Time of Loss and
# 'Type of Policy' as Policy No.; measured against the sample letters, every
# correct semantic match sits at 0.75 or above.
MATCH_MINIMUM = 0.75

# Labels that show up in DLA letters but have no column in this template at all.
# Without this the matcher pushes them into whichever column scores highest --
# 'Coverage Period' ended up in Coverage, holding a date range.
NOT_A_COLUMN = [
    "period of insurance", "insurance period", "insured period", "coverage period",
    "policy period", "periode pertanggungan", "masa pertanggungan",
    "jangka waktu pertanggungan",
    "deductible", "deductible amount", "risiko sendiri",
    "loss adjuster", "appointed adjuster", "adjuster",
    "cedant", "cedent", "cedant with", "reinsurer", "reinsured",
    "name of reinsured", "reinsurance",
    "bank address", "bank account", "account no", "account name",
    "type of policy", "class of business", "note no", "total unit",
    "beneficiary name", "claim status", "remarks", "loss", "risk",
]

OWN_COMPANY_NAMES = [
    "asuransi astra buana",
    "astra buana",
    "asuransi astra",
]

INSURED_NAME_LABELS = {
    "insured", "the insured", "insured name", "insured's name",
    "name of insured", "name of the insured", "insured party",
    "tertanggung", "nama tertanggung", "pemegang polis", "nama pemegang polis",
    "policyholder", "policy holder",
}

INSURED_HINT_LABELS = ["tertanggung", "insured", "pemegang polis", "nama tertanggung"]
RECIPIENT_HINT_LABELS = ["kepada", "kepada yth", "ditujukan kepada", "to"]

LEGAL_ENTITY_FORMS = [
    "pt", "cv", "ud", "pd", "persero", "tbk", "perseroan terbatas", "ltd", "inc",
]

LETTER_DATE_COLUMN = "S"
LETTER_DATE_FORMAT = "iso"

SHARE_BY_POLICY = {}

# OCR
TESSERACT_PATH = None
OCR_LANGUAGES = "ind+eng"
SCANNED_PAGE_THRESHOLD = 120


def template_file() -> Path:
    candidates = sorted(TEMPLATE_DIR.glob("*.xlsx"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    candidates = [p for p in candidates if not p.name.startswith("~$")]
    if not candidates:
        raise FileNotFoundError(f"Tidak ada file .xlsx di {TEMPLATE_DIR}")
    return candidates[0]

def long_path(p) -> str:
    s = str(Path(p).resolve())
    if os.name == "nt" and len(s) >= 250 and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + s
    return s


def ensure_folders() -> None:
    for d in (OUTPUT_DIR, MEMORY_DIR):
        d.mkdir(parents=True, exist_ok=True)
