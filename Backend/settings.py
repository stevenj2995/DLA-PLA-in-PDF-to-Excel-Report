from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STANDAR_DIR = ROOT / "STANDAR"
INPUT_DIR = ROOT / "INPUT"
OUTPUT_DIR = ROOT / "OUTPUT"
MEMORY_DIR = ROOT / "MEMORY"

FOLDER_TIDAK_TERDETEKSI = "_TIDAK_TERDETEKSI"
SUBFOLDER_PDF = "PDF"

# struktur sheet standar
SHEET_UTAMA = "MosyClaimTask"
BARIS_GRUP = 2
BARIS_HEADER = 3
BARIS_FLAG = 4
BARIS_DATA_AWAL = 5

# peran kolom
KOLOM_DARI_PDF = [
    "B", "C", "D", "E", "H", "I", "S", "T", "V", "Y",
    "Z", "AA", "AB", "AC", "AI", "AK", "AL", "AQ", "BT",
]

KOLOM_KONSTAN = {
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

KOLOM_EMAIL_OPERATOR = "N"
KOLOM_NOMOR_URUT = "A"
KOLOM_REF_UNIK = "Y"
KOLOM_NAMA_TERTANGGUNG = "H"   # Reported Name, diisi dari hasil deteksi
KOLOM_RUMUS = {
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

KOLOM_KOSONG = [
    "G", "J", "K", "L", "M", "P", "Q", "R", "X", "AE", "AG", "AH", "AJ",
    "AS", "AU", "AV", "AW", "AX", "AY", "AZ", "BH", "BI", "BK", "BL", "BM",
]
KOLOM_MONITORING = ["BN", "BO", "BP", "BQ", "BR", "BS"]
KOLOM_DITUNDA = ["BT"]
KOLOM_FEE = ["BB", "BC", "BD", "BE", "BF", "BG", "BJ"]

# threshold
YAKIN = 0.85
RAGU = 0.60

PERUSAHAAN_TUJUAN = [
    "asuransi astra buana",
    "astra buana",
    "asuransi astra",
]

# Nama perusahaan SELALU diambil dari tertanggung - pemilik polis yang
# mengalami kerugian. Bukan penerbit laporan, bukan pihak tujuan.
#
# JALUR UTAMA: label di bawah ini dicocokkan UTUH dengan tulisan di kiri titik
# dua, lalu nilai di kanannya dipakai apa adanya. Harus utuh, karena
# "Insured Interest", "Insured Period", "Total Sum Insured", dan "Reinsured"
# sama-sama memuat kata "insured" tapi bukan nama tertanggung.
# Semua bentuk di bawah dipanen dari 10 DLA asli.
LABEL_NAMA_TERTANGGUNG = {
    "insured", "the insured", "insured name", "insured's name",
    "name of insured", "name of the insured", "insured party",
    "tertanggung", "nama tertanggung", "pemegang polis", "nama pemegang polis",
    "policyholder", "policy holder",
}

# JALUR CADANGAN: dipakai hanya kalau tidak ada satu pun label di atas.
# Ini cuma kata penanda di dekat nama, dicocokkan per kata utuh.
LABEL_TERTANGGUNG = ["tertanggung", "insured", "pemegang polis", "nama tertanggung"]
LABEL_TUJUAN = ["kepada", "kepada yth", "ditujukan kepada", "to"]

BENTUK_BADAN_USAHA = [
    "pt", "cv", "ud", "pd", "persero", "tbk", "perseroan terbatas", "ltd", "inc",
]

KOLOM_TANGGAL_SURAT = "S"
FORMAT_TANGGAL_SURAT = "iso"

SHARE_PER_POLIS = {}

# OCR
TESSERACT_PATH = None
OCR_BAHASA = "ind+eng"
AMBANG_HALAMAN_SCAN = 120


def file_standar() -> Path:
    kandidat = sorted(STANDAR_DIR.glob("*.xlsx"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    kandidat = [p for p in kandidat if not p.name.startswith("~$")]
    if not kandidat:
        raise FileNotFoundError(f"Tidak ada file .xlsx di {STANDAR_DIR}")
    return kandidat[0]


def siapkan_folder() -> None:
    for d in (INPUT_DIR, OUTPUT_DIR, MEMORY_DIR):
        d.mkdir(parents=True, exist_ok=True)
