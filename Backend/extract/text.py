from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from .. import settings

MONTHS_ID = {
    "januari": 1, "jan": 1,
    "februari": 2, "pebruari": 2, "feb": 2,
    "maret": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "agustus": 8, "agu": 8, "ags": 8,
    "september": 9, "sep": 9, "sept" : 9,
    "oktober": 10, "okt": 10, "oct" : 10, "october" : 10,
    "november": 11, "nov": 11, "nopember": 11, 
    "desember": 12, "des": 12, "dec" : 12, "december" : 12
}
MONTHS_EN = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3,  "mar": 3,
    "april": 4, "apr": 4,
    "may": 5, 
    "june": 6, "jun": 6,
    "july": 7, "jul": 7, 
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "october": 10, "oct": 10, 
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}
MONTHS = {**MONTHS_EN, **MONTHS_ID}

# "Jakarta, 22 Agustus 2026" / "Surabaya, 22 August 2026"
RE_LETTER_FOOTER = re.compile(
    r"(?P<city>[A-Z][A-Za-z\.\s]{2,30}?)\s*,\s*"
    r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]{3,12})\s+(?P<year>\d{4})"
)
# "Jakarta, October 27, 2024" -- the month-first order English letters use
RE_LETTER_FOOTER_MONTH_FIRST = re.compile(
    r"(?P<city>[A-Z][A-Za-z\.\s]{2,30}?)\s*,\s*"
    r"(?P<month>[A-Za-z]{3,12})\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})"
)
# Both orders, and any of space, hyphen or slash between the parts: these
# letters write "20 November 2024", "12-Jan-2025" and "October 27, 2024" alike.
RE_DATE_WORDS = re.compile(r"\b(\d{1,2})[\s\-/]+([A-Za-z]{3,12})[\s\-/,]+(\d{4})\b")
RE_DATE_MONTH_FIRST = re.compile(r"\b([A-Za-z]{3,12})[\s\-/]+(\d{1,2})[\s\-/,]+(\d{4})\b")
RE_DATE_NUMERIC = re.compile(r"\b(\d{1,4})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b")
RE_TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")


def _date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(text: str) -> date | None:
    if not text:
        return None
    s = str(text).strip()

    m = RE_DATE_WORDS.search(s)
    if m:
        month = MONTHS.get(m.group(2).lower())
        if month:
            result = _date(int(m.group(3)), month, int(m.group(1)))
            if result:
                return result

    m = RE_DATE_MONTH_FIRST.search(s)
    if m:
        month = MONTHS.get(m.group(1).lower())
        if month:
            result = _date(int(m.group(3)), month, int(m.group(2)))
            if result:
                return result

    m = RE_DATE_NUMERIC.search(s)
    if m:
        a, b, c = (int(x) for x in m.groups())
        if len(m.group(1)) == 4:
            return _date(a, b, c)
        year = c + 2000 if c < 100 else c
        return _date(year, b, a) or _date(year, a, b)  # try dd/mm first, then mm/dd
    return None

def letter_footer_date(text: str) -> tuple[date | None, str | None, str | None]:
    body = text or ""
    for pattern in (RE_LETTER_FOOTER, RE_LETTER_FOOTER_MONTH_FIRST):
        for m in reversed(list(pattern.finditer(body))):
            month = MONTHS.get(m.group("month").lower())
            if not month:
                continue
            d = _date(int(m.group("year")), month, int(m.group("day")))
            if d:
                city = " ".join(m.group("city").split()).strip(" .,")
                return d, city, m.group(0)
    return None, None, None

def format_date(d: date | None, style: str = "iso") -> str | None:
    if d is None:
        return None
    if style == "original":
        name = [k for k, v in MONTHS_ID.items() if v == d.month and len(k) > 3]
        return f"{d.day} {name[0].capitalize() if name else d.month} {d.year}"
    return d.strftime("%Y-%m-%d")


def parse_time(text: str) -> str | None:
    m = RE_TIME.search(str(text or ""))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


# "Rp 1.024.770.200,00" -> 1024770200.0
def parse_money(text: str) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)

    s = re.sub(r"(?i)\b(rp|idr|usd|sgd)\b\.?", " ", str(text))
    # accounting notation: (35,000,000.00) is a deduction, not an amount
    negative = bool(re.search(r"\(\s*[\d.,]+\s*\)", s))
    s = re.sub(r"[^\d,.\-]", "", s).strip()
    if not s or not re.search(r"\d", s):
        return None

    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        s = s.replace(thousands, "").replace(decimal, ".")
    elif has_comma:
        tail = s.split(",")[-1] # 1-2 angka di belakang = desimal
        s = s.replace(",", "." if len(tail) <= 2 and s.count(",") == 1 else "")
    elif has_dot:
        tail = s.split(".")[-1]
        if not (len(tail) <= 2 and s.count(".") == 1):
            s = s.replace(".", "")
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative and value > 0 else value


RE_PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
RE_NUMBER = re.compile(r"\d[\d.,]*")


# "IDR 4,946,764.00 x 2.5 % = 123,669.10" -- the figure the share is taken of,
# which is the nett claim. Only trusted when the arithmetic on the line adds up,
# so a line that merely mentions a percentage never yields a number.
def share_base(text: str) -> float | None:
    s = str(text or "")
    m = RE_PERCENT.search(s)
    if not m:
        return None
    rate = float(m.group(1).replace(",", ".")) / 100.0
    if not rate:
        return None
    numbers = [n for n in (parse_money(x)
                           for x in RE_NUMBER.findall(RE_PERCENT.sub(" ", s))) if n]
    for i, base in enumerate(numbers):
        for result in numbers[i + 1:]:
            if abs(base * rate - result) <= max(1.0, abs(result) * 0.01):
                return base
    return None


def parse_postal_code(text: str) -> str | None:
    m = re.search(r"\b(\d{5})\b", str(text or ""))
    return m.group(1) if m else None

# written the way the template writes it: "3,5%" and "6.000000%" both become
# "3.50%" / "6.00%", so the Share column reads the same on every row
def parse_percent(text: str) -> str | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", str(text or ""))
    if not m:
        return None
    return "%.2f%%" % float(m.group(1).replace(",", "."))


def clean_text(text: str, limit: int = 500) -> str:
    return " ".join(str(text or "").split())[:limit]


_SP = r"[^\S\n]"
_WORD = r"[A-Z][A-Za-z0-9&'\.\-]*"

RE_COMPANY = re.compile(
    rf"\b(?:PT|CV|UD|PD)\.?{_SP}+"
    rf"(?P<name>{_WORD}(?:{_SP}+(?:{_WORD}|dan|and|of|de)){{0,6}})"
    rf"(?P<tail>{_SP}*\((?:Persero|PERSERO|Tbk|TBK)\))?"
)
# reversed form: "Nama Perusahaan, PT"
RE_COMPANY_REVERSED = re.compile(
    rf"(?P<name>{_WORD}(?:{_SP}+[A-Za-z0-9&'\.\-()]+){{0,6}}?){_SP}*,{_SP}*(?:PT|CV)\.?\b"
)

# words that mean the name has ended and the next field label has started
RE_NEXT_LABEL = re.compile(
    r"\b(?:Jl|Jalan|Telp|Telepon|Fax|Email|NPWP|Nomor|No|Nama|Alamat|Tanggal|Tgl|"
    r"Date|Time|Policy|Polis|Lokasi|Penyebab|Jenis|Nilai|Kode|Kepada|Perihal|Hal)\b",
    re.I,
)

_WINDOWS_FORBIDDEN = r'[<>:"/\\|?*\x00-\x1f]'
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_ROMAN = r"(?:I{1,3}|IV|VI{0,3}|IX|XI{0,3})"
_ENTITY_FORMS = {"PT", "CV", "UD", "PD", "PERSERO", "TBK", "LTD", "INC", "LLC"}


# normalise odd dashes and quotes -- they break folder names on Windows
def _normalize_unicode(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    for odd, repl in (("–", "-"), ("—", "-"), ("−", "-"),
                        ("‘", "'"), ("’", "'"),
                        ("“", '"'), ("”", '"'), ("�", " ")):
        s = s.replace(odd, repl)
    return " ".join(s.split())


def normalize(name: str) -> str:
    s = _normalize_unicode(name).upper()
    s = re.sub(r"\(([^)]*)\)", r" \1 ", s)
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    return " ".join(k for k in s.split() if k not in _ENTITY_FORMS)

_NUMBER = rf"(?:{_ROMAN}|\d{{1,2}})"


def group_name(name: str) -> str:
    core = normalize(name)
    core = re.sub(rf"\s+REGIONAL(\s*-?\s*{_NUMBER})*\s*$", "", core)
    core = re.sub(rf"(\s+{_ROMAN})+\s*$", "", core)
    core = re.sub(r"\s+\d+\s*$", "", core)
    return (core.strip() or normalize(name)).title()


def folder_name(name: str, limit: int = 90) -> str:
    s = re.sub(_WINDOWS_FORBIDDEN, " ", _normalize_unicode(name))
    s = " ".join(s.split()).rstrip(" .")
    if len(s) > limit:
        s = s[:limit].rstrip(" .")
    if s.upper().split(".")[0] in _RESERVED_NAMES:
        s = f"_{s}"
    return s or "TANPA_NAMA"


@dataclass
class Candidate:
    name: str
    score: float = 0.0
    position: int = -1
    role: str = ""
    reasons: list[str] = field(default_factory=list)


@dataclass
class DetectionResult:
    name: str | None = None
    confidence: float = 0.0
    candidates: list[Candidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        if self.name and self.confidence >= settings.CONFIDENT:
            return "confident"
        if self.name and self.confidence >= settings.UNSURE:
            return "unsure"
        return "undetected"


def _is_own_company(name: str) -> bool:
    n = normalize(name)
    return any(normalize(t) in n for t in settings.OWN_COMPANY_NAMES)


# drop the tail that is really the next field label
def _cut_at_next_label(name: str) -> str:
    m = RE_NEXT_LABEL.search(name)
    return " ".join(name[:m.start()].split()) if m else " ".join(name.split())


def find_company_names(text: str) -> list[tuple[str, int]]:
    result: list[tuple[str, int]] = []
    for m in RE_COMPANY.finditer(text):
        name = _cut_at_next_label(m.group("name"))
        if len(normalize(name)) >= 4:
            result.append((f"PT {name}{m.group('tail') or ''}".strip(), m.start()))
    for m in RE_COMPANY_REVERSED.finditer(text):
        name = _cut_at_next_label(m.group("name"))
        if len(normalize(name)) >= 4:
            result.append((f"PT {name}", m.start()))
    return result

def _has_label(window: str, labels: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(l)}\b", window) for l in labels)


def _label_before(text: str, position: int, distance: int = 60) -> str:
    window = text[max(0, position - distance):position].lower()
    if _has_label(window, settings.INSURED_HINT_LABELS):
        return "tertanggung"
    if _has_label(window, settings.RECIPIENT_HINT_LABELS):
        return "tujuan"
    return ""

RE_LABEL_VALUE = re.compile(r"^\s*(?P<label>[^:：]{2,50})[:：]\s*(?P<value>.*)$")

# "PT A and/or PT B" or "PT A QQ PT B" -> keep the first only. The one named
# first is the main insured; the rest are joined parties.
RE_OTHER_PARTIES = re.compile(r"(?i)\s+(?:and\s*/\s*or|dan\s*/\s*atau|q\.?q\.?)\s+")


def _clean_label(s: str) -> str:
    return " ".join(s.lower().replace(".", "").split())


def insured_name_from_label(lines: list[str]) -> tuple[str | None, str | None]:
    for i, b in enumerate(lines):
        m = RE_LABEL_VALUE.match(b)
        if not m or _clean_label(m.group("label")) not in settings.INSURED_NAME_LABELS:
            continue

        value = m.group("value").strip()
        # label with nothing to its right -> the value is on the next line
        if not value and i + 1 < len(lines) and not RE_LABEL_VALUE.match(lines[i + 1]):
            value = lines[i + 1].strip()

        value = RE_OTHER_PARTIES.split(_cut_at_next_label(value))[0].strip(" ,.;-")
        if len(normalize(value)) >= 4 and not _is_own_company(value):
            return value, " ".join(m.group("label").split())
    return None, None


def detect(lines: list[str], *, file_name: str = "") -> DetectionResult:
    result = DetectionResult()
    text = "\n".join(lines)
    if not text.strip():
        result.warnings.append("PDF tidak punya teks yang bisa dibaca")
        return result

    name, label = insured_name_from_label(lines)
    if name:
        result.name = name
        result.confidence = 1.0
        result.candidates = [Candidate(name=name, score=1.0, role="tertanggung",
                                   reasons=[f"diambil dari label '{label}'"])]
        return result

    result.warnings.append(
        "Tidak ada label tertanggung (Insured Name / Name of Insured / "
        "Tertanggung) - nama ditebak dari sebaran nama di teks")

    score: dict[str, Candidate] = {}
    for name, position in find_company_names(text):
        if _is_own_company(name):
            continue
        key = normalize(name)
        if not key:
            continue

        k = score.get(key)
        if k is None:
            k = score[key] = Candidate(name=name, position=position)
        k.score += 1.0
        if position < k.position or k.position < 0:
            k.position = position

        role = _label_before(text, position)
        if role and not k.role:
            k.role = role
            k.reasons.append(f"disebut sebagai {role}")

        if file_name and key in normalize(file_name):
            if "cocok dengan nama file" not in k.reasons:
                k.score += 2.0
                k.reasons.append("cocok dengan nama file")

    for k in score.values():
        k.score += 6.0 if k.role == "tertanggung" else -2.0
        k.score = max(k.score, 0.0)

    ranked = [k for k in sorted(score.values(), key=lambda x: x.score, reverse=True)
            if k.score > 0]
    if not ranked:
        result.warnings.append(
            "Tidak ada nama perusahaan yang terbaca!")
        return result

    total = sum(k.score for k in ranked) or 1.0
    for k in ranked:
        k.score = round(k.score / total, 3)

    result.candidates = ranked
    result.name = ranked[0].name
    result.confidence = ranked[0].score

    if len(ranked) > 1 and ranked[0].score - ranked[1].score < 0.15:
        result.warnings.append(
            f"Dua kandidat nyaris seimbang: '{ranked[0].name}' vs '{ranked[1].name}'")
    if re.search(rf"\b{_ROMAN}\b", result.name or ""):
        result.warnings.append(
            "Nama mengandung angka romawi yang gampang tertukar saat OCR")
    return result
