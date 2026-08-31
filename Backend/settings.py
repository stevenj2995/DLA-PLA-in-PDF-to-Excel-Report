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
COLUMNS_FROM_PDF = [
    "B", "C", "D", "E", "H", "I", "S", "T", "V", "Y",
    "Z", "AA", "AB", "AC", "AI", "AK", "AL", "AQ", "BT",
]

CONSTANT_COLUMNS = {
    "F": "CPM - Heavy Equipment - CPM",
    "N": None,
    "O": "Y",
    "U": "Occurrence",
    "W": "Partial Loss Accident",
    "AD": "N",
    "AF": "MGQ",
    "AN": "CASC - Casco",
    "AO": "Reinstate",
    "AP": "IDR",
    "AT": "0",
    "BA": "Y",
}

OPERATOR_EMAIL_COLUMN = "N"
ROW_NUMBER_COLUMN = "A"
UNIQUE_REF_COLUMN = "Y"
INSURED_NAME_COLUMN = "H"   # Reported Name, filled from detection
FORMULA_COLUMNS = {
    "AM": ('="Klaim yang terjadi dengan detail sebagai berikut."&"\n\n"'
           '&"Lokasi:"&" "&AA{r}&"\nDOL:"&" "&B{r}&"\n"'
           '&"Nature of Damage:"&" "&AC{r}&"\n"'
           '&"Cause of Loss:"&" "&AB{r}&"\n"'
           '&"Kejadian sudden and unforseen"&"\n\n"'
           '&"Nilai Adjustment "&" "&AP{r}&"\n"'
           '&"Net Adjustment = "&" "&AQ{r}&"\n"'
           '&"AAB Share = "&" "&AQ{r}*(BT{r})&""'),
    "AR": "=AQ{r}*{share}",
}

EMPTY_COLUMNS = [
    "G", "J", "K", "L", "M", "P", "Q", "R", "X", "AE", "AG", "AH", "AJ",
    "AS", "AU", "AV", "AW", "AX", "AY", "AZ", "BH", "BI", "BK", "BL", "BM",
]
MONITORING_COLUMNS = ["BN", "BO", "BP", "BQ", "BR", "BS"]
DEFERRED_COLUMNS = ["BT"]
FEE_COLUMNS = ["BB", "BC", "BD", "BE", "BF", "BG", "BJ"]

# detection confidence thresholds
CONFIDENT = 0.85
UNSURE = 0.60

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


def ensure_folders() -> None:
    for d in (OUTPUT_DIR, MEMORY_DIR):
        d.mkdir(parents=True, exist_ok=True)
