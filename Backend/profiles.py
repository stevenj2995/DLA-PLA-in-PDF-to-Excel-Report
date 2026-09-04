from __future__ import annotations
from dataclasses import dataclass

from .extract import parser

TAKE = {
    "raw": lambda v: v,
    "amount": parser.amount,
    "last_amount": parser.last_number,
    "currency": parser.currency,
    "text_only": parser.without_money,
    "strip_currency": parser.strip_currency,
}


@dataclass(frozen=True)
class Column:
    header: str
    source: str
    take: str = "raw"


@dataclass(frozen=True)
class Profile:
    key: str
    name: str
    marks: tuple[str, ...]
    columns: tuple[Column, ...]
    skip_headings: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    bulleted_money: bool = False
    split_shared_lines: bool = False
    reviewed: bool = True
    # satu berkas bisa memuat dla yang sama, diterbitkan ulang untuk tiap
    # reasuradur. dua ini menandai salinan mana yang milik kita.
    titles: tuple[str, ...] = ()          # judul-judul yang menandai awal satu advice
    owner_label: str = ""
    owner_names: tuple[str, ...] = ()
    # column source name for the bare line printed right under the title,
    # for companies whose own document number carries no label at all
    reference_after_title: str = ""

    def matches(self, labels) -> bool:
        return all(m in labels for m in self.marks)

# Profile JRP
JRP = Profile(
    key="jrp",
    name="JRP",
    marks=("Ref No", "Risk Cover", "Appointed Adjuster"),
    skip_headings=("debit note", "credit note"),
    ignore=("Definite Claim Amount", "Deductible"),
    # this project reads both kinds of advice, so a file re-issuing PLAs per
    # reinsurer splits the same way a file re-issuing DLAs does.
    titles=("definite loss advice", "preliminary loss advice"),
    owner_label="Reinsurer",
    owner_names=("astra buana", "asuransi astra buana", "asuransi astra"),
    columns=(
        # Parameter yang akan diambil saat dibaca
        Column("Ref No", "Ref No"),
        Column("Claim No", "Claim No"),
        Column("Class of Business", "Class of Business"),
        Column("Address", "Address"),
        Column("Reinsurer", "Reinsurer"),
        Column("Policy No.", "Policy No."),
        Column("Insured Name", "Insured Name"),
        Column("Insurance Period", "Insurance Period"),
        Column("Serial No", "Serial No"),
        Column("Engine No", "Engine No"),
        Column("Risk Cover", "Risk Cover"),
        Column("Insured Interest", "Insured Interest", "text_only"),
        Column("Currency", "Total Sum Insured", "currency"),
        Column("Total Sum Insured", "Total Sum Insured", "amount"),
        Column("Date of Loss", "Date of Loss"),
        Column("Place of Loss", "Place of Loss"),
        Column("Cause of Loss", "Cause of Loss"),
        Column("Appointed Adjuster", "Appointed Adjuster"),
        Column("Currency", "Nett Amount", "currency"),
        Column("Definite Claim Amount", "Nett Amount", "amount"),
        Column("Currency", "Your Share on Nett Loss", "currency"),
        Column("Your Share on Nett Loss", "Your Share on Nett Loss", "last_amount"),
        Column("Description of Loss", "Description of Loss"),
        Column("Remarks", "Remarks"),
    ),
)

# Profile Askrindo
ASKRINDO = Profile(
    key="askrindo",
    name="Askrindo",
    marks=("No DLA", "Askrindo Share"),
    columns=(
        # Parameter yang akan diambil saat dibaca
        Column("No DLA", "No DLA"),
        Column("Class of Business", "Class of Business"),
        Column("Type of Policy", "Type of Policy"),
        Column("PLA No", "PLA No"),
        Column("Reinsurer", "Reinsurer"),
        Column("Policy No", "Policy No"),
        Column("Insured Name", "Insured Name"),
        Column("Insured Period", "Insured Period"),
        Column("Currency", "Total Sum Insured", "currency"),
        Column("Total Sum Insured", "Total Sum Insured", "amount"),
        Column("Date of Loss", "Date of Loss"),
        Column("Place of Loss", "Place of Loss"),
        Column("Cause of Loss", "Cause of Loss"),
        Column("Description of Loss", "Description of Loss"),
        Column("Currency", "Net Amount", "currency"),
        Column("Loss Amount 100%", "Net Amount", "amount"),
        Column("Askrindo Share", "Askrindo Share"),
        Column("Your Share", "Your Share"),
        Column("Currency", "Your Share on Nett Loss", "currency"),
        Column("Your Share on Nett Loss", "Your Share on Nett Loss", "last_amount"),
        Column("Remarks", "Remarks"),
    ),
)

# KMDastur
#
# Ownership is unresolved: JRP names the addressee in a printed field
# ("Reinsurer : ASTRA BUANA"), but KMDastur's only sample has no such field at
# all -- Astra Buana's name appears solely in the letterhead at the top of the
# page. owner_label/owner_names are left unset until that is designed, which
# means a file holding more than one advice is refused outright rather than
# guessed at (see _labels_of): safe, but such a file would currently be
# rejected rather than read. Confirm with more real KMDastur files whether
# that shape ever occurs before this is called finished.
KMDASTUR = Profile(
    key="kmdastur",
    name="KMDastur",
    marks=("Name of Reinsured", "Interest Insured"),
    bulleted_money=True,
    titles=("definite loss advice",),
    # KMDastur prints its own document number as a bare line under the title,
    # with no label attached -- "307/CF/103/CPM/VII/2026" under "DEFINITE LOSS
    # ADVICE". Column name asked for on 2026-09-04: matches the title above it
    # for now; change the header below once a better name is decided.
    reference_after_title="Definite Loss Advice",
    # only the nett is kept, matching the rule for JRP's own amount block
    ignore=("Indemnity", "Deductible"),
    reviewed=False,
    columns=(
        # Parameter yang akan diambil saat dibaca
        Column("Definite Loss Advice", "Definite Loss Advice"),
        Column("Class of Business", "Class of Business"),
        Column("Policy Number", "Policy Number"),
        Column("Your Reference", "Your Reference"),
        Column("Period of Insurance", "Period of Insurance"),
        Column("Name of Reinsured", "Name of Reinsured"),
        Column("Name of Insured", "Name of Insured"),
        Column("Interest Insured", "Interest Insured"),
        Column("Currency", "Total Sum Insured", "currency"),
        # kept whole, not just the first number: "IDR X part of IDR Y" would
        # lose the treaty total if only the cedant's share were taken
        Column("Total Sum Insured", "Total Sum Insured", "strip_currency"),
        Column("Date of Loss", "Date of Loss"),
        Column("Cause of Loss", "Cause of Loss"),
        Column("Place of Loss", "Place of Loss"),
        Column("Description of Loss", "Description of Loss"),
        Column("Currency", "Nett Amount", "currency"),
        Column("Definite Loss Amount", "Nett Amount", "amount"),
        Column("Currency", "Your Share", "currency"),
        Column("Your Share", "Your Share", "last_amount"),
        Column("Remarks", "Remarks"),
    ),
)

ALL = (JRP,)
DRAFTS = (ASKRINDO, KMDASTUR)

def by_key(key: str) -> Profile | None:
    return next((p for p in ALL if p.key == key), None)


def detect(labels) -> Profile | None:
    hits = [p for p in ALL if p.matches(labels)]
    return hits[0] if len(hits) == 1 else None
