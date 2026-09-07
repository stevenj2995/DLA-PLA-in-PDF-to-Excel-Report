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
    titles: tuple[str, ...] = ()
    owner_label: str = ""
    owner_names: tuple[str, ...] = ()
    owner_from_letterhead: bool = False
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
    titles=("definite loss advice", "preliminary loss advice"),
    owner_label="Reinsurer",
    owner_names=("astra buana", "asuransi astra buana", "asuransi astra"),
    columns=(
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
    titles=("definite loss advice",),
    owner_label="Reinsurer",
    owner_names=("astra buana", "asuransi astra buana", "asuransi astra"),
    ignore=("Loss Amount 100%", "Deductible"),
    columns=(
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
KMDASTUR = Profile(
    key="kmdastur",
    name="KMDastur",
    marks=("Name of Reinsured", "Interest Insured"),
    bulleted_money=True,
    titles=("definite loss advice",),
    owner_label="Kop Surat",
    owner_names=("astra buana", "asuransi astra buana", "asuransi astra"),
    owner_from_letterhead=True,
    reference_after_title="Definite Loss Advice",
    ignore=("Indemnity", "Deductible", "Kop Surat",
            "Definite Loss Amount Indemnity", "Definite Loss Amount Expense", "Expense"),
    reviewed=False,
    columns=(
        # Parameter yang akan diambil saat dibaca
        Column("No. Reff DLA", "Definite Loss Advice"),
        Column("Our Reference", "Our Reference"),
        Column("Class of Business", "Class of Business"),
        Column("Type of Insurance", "Type of Insurance"),
        Column("Policy Number", "Policy Number"),
        Column("Your Reference", "Your Reference"),
        Column("Period of Insurance", "Period of Insurance"),
        Column("Name of Reinsured", "Name of Reinsured"),
        Column("Name of Insured", "Name of Insured"),
        Column("Interest Insured", "Interest Insured"),
        Column("Currency", "Total Sum Insured", "currency"),
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

ALL = (JRP, KMDASTUR)
DRAFTS = (ASKRINDO,)

def by_key(key: str) -> Profile | None:
    return next((p for p in ALL if p.key == key), None)


def detect(labels) -> Profile | None:
    hits = [p for p in ALL if p.matches(labels)]
    return hits[0] if len(hits) == 1 else None
