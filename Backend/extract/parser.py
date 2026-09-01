from __future__ import annotations
import re

# A parameter is whatever sits left of the first colon. The label is kept short
# on purpose: a long run of words before a colon is prose, not a label.
RE_PAIR = re.compile(r"^(?P<label>[A-Za-z][A-Za-z0-9 ./&'%()\-]{1,38}?)\s*:\s*(?P<value>.*)$")

# A second pair sharing the same printed line, as in
#     Policy Number : 227000806122400025    Note No. : 002231/DN/2700/01/26
RE_SECOND_PAIR = re.compile(r"\s{2,}(?P<label>[A-Z][A-Za-z0-9 ./&'()\-]{1,30}?)\s*:\s*(?P<value>.*)$")

# Lines that carry no data and must never become a parameter or be glued onto
# the value above: page footers, the closing line, a bare signing date, and the
# block of glyphs a digital signature stamp renders as.
RE_JUNK = re.compile(r"(?i)page \d+ of \d+|for and on behalf of")
RE_GLYPH = re.compile(r"^[A-Z]{40,}$")
RE_SIGN_DATE = re.compile(r"^\s*,?\s*\d{1,2}[/-]\d{1,2}[/-]\d{4}\s*$")

CURRENCIES = r"IDR|USD|SGD|EUR|AUD|JPY|GBP|Rp"
RE_CURRENCY = re.compile(r"\b(" + CURRENCIES + r")\b", re.I)
RE_NUMBER = re.compile(r"\d[\d.,]*\d|\d")
# The amount is the run of digits attached to the currency, not merely the first
# number on the line: Askrindo prints 'RUBBER TYRED GANTRY (R6) IDR 16,076,308,354.63'
# and the first number there is the 6 of R6.
RE_AMOUNT = re.compile(r"(?:" + CURRENCIES + r")\s*\(?\s*(?P<amount>[\d.,]*\d)", re.I)

# KMDastur writes the amount block as a heading with bulleted children, and the
# bullet is a colon with nothing before it:
#     Indemnity IDR 90,500,000.00
#     Definite Loss Amount :
#     : Deductible IDR (35,000,000.00)
#     : Nett Amount IDR 55,500,000.00
RE_BULLET_MONEY = re.compile(
    r"^[:\s]*(?P<label>[A-Za-z][A-Za-z ./&'\-]{1,38}?)\s*:?\s+"
    r"(?P<value>(?:" + CURRENCIES + r")\s*\(?-?[\d.,]+\)?)\s*$", re.I)


# The closing line of a letter -- "Jakarta, July 31, 2026", "Jakarta, 27 April
# 2026". Everything after it is signature, licence numbers and branch lists, so
# reading stops there rather than gluing all of it onto the last value.
RE_LETTER_CLOSE = re.compile(
    r"^[A-Z][A-Za-z .]{2,24},\s+(?:\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},\s+\d{4})\s*$")


def is_junk(line: str) -> bool:
    return bool(RE_GLYPH.match(line) or RE_SIGN_DATE.match(line) or RE_JUNK.search(line))


def pairs(lines: list[str], *, split_shared_lines: bool = False,
          bulleted_money: bool = False) -> dict[str, str]:
    """Label -> value, in the order the document prints them.

    A line with no label continues the value above it, which is how wrapped
    addresses and descriptions come back whole. Junk breaks that chain so the
    footer never lands inside the last value.
    """
    found: dict[str, str] = {}
    last: str | None = None
    for raw in lines:
        line = " ".join(str(raw).split())
        if not line or is_junk(line):
            last = None
            continue

        pair = RE_PAIR.match(line)
        if bulleted_money and not pair:
            bullet = RE_BULLET_MONEY.match(line)
            if bullet:
                found.setdefault(" ".join(bullet.group("label").split()),
                                 bullet.group("value").strip())
                last = None
                continue
        if not pair:
            if RE_LETTER_CLOSE.match(line):
                break
            if last:
                found[last] = f"{found[last]} {line}".strip()
            continue

        label = " ".join(pair.group("label").split())
        value = pair.group("value").strip()
        if split_shared_lines:
            second = RE_SECOND_PAIR.search(" " + value)
            if second:
                value = value[: second.start()].strip()
                found.setdefault(" ".join(second.group("label").split()),
                                 second.group("value").strip())
        found[label] = value
        last = label
    return found


def currency(text: str) -> str:
    m = RE_CURRENCY.search(text or "")
    return m.group(1).upper() if m else ""


def first_number(text: str) -> str:
    m = RE_NUMBER.search(text or "")
    return m.group(0) if m else ""


def last_number(text: str) -> str:
    found = RE_NUMBER.findall(text or "")
    return found[-1] if found else ""


def amount(text: str) -> str:
    m = RE_AMOUNT.search(text or "")
    return m.group("amount") if m else first_number(text)


def without_money(text: str) -> str:
    """'Equipment IDR 49,185,430,585.00' -> 'Equipment'."""
    return RE_CURRENCY.split(text or "", maxsplit=1)[0].strip(" :-,")
