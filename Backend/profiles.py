from __future__ import annotations
from dataclasses import dataclass, field

from .extract import parser

# How a value is lifted out of the printed text.
#   raw            take it as it stands
#   amount         the digits attached to the currency
#   last_amount    the digits of the last number on the line
#   currency       the currency code only
#   text_only      drop the money, keep the words
TAKE = {
    "raw": lambda v: v,
    "amount": parser.amount,
    "last_amount": parser.last_number,
    "currency": parser.currency,
    "text_only": parser.without_money,
}


@dataclass(frozen=True)
class Column:
    header: str
    source: str          # the label as the document prints it
    take: str = "raw"


@dataclass(frozen=True)
class Profile:
    key: str
    name: str
    marks: tuple[str, ...]              # labels that identify this company
    columns: tuple[Column, ...]
    skip_headings: tuple[str, ...] = ()  # pages that are a different document
    ignore: tuple[str, ...] = ()         # labels deliberately not carried over
    bulleted_money: bool = False
    split_shared_lines: bool = False
    reviewed: bool = True                # confirmed with Steven, column by column

    def matches(self, labels) -> bool:
        return all(m in labels for m in self.marks)


# JRP -- two documents in one file; only the DLA page is used, the DEBIT NOTE
# page is ignored. Column list confirmed 2026-09-01.
JRP = Profile(
    key="jrp",
    name="JRP",
    marks=("Ref No", "Risk Cover", "Appointed Adjuster"),
    skip_headings=("debit note", "credit note"),
    # the gross and the deductible of the amount block: only the nett is kept
    ignore=("Definite Claim Amount", "Deductible"),
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
        # the block is named for its heading, the figure taken is the nett
        Column("Currency", "Nett Amount", "currency"),
        Column("Definite Claim Amount", "Nett Amount", "amount"),
        Column("Currency", "Your Share on Nett Loss", "currency"),
        Column("Your Share on Nett Loss", "Your Share on Nett Loss", "last_amount"),
        Column("Description of Loss", "Description of Loss"),
        Column("Remarks", "Remarks"),
    ),
)

# Askrindo -- single page. Column list taken from the eighteen parameters Steven
# listed, plus the currency split.
ASKRINDO = Profile(
    key="askrindo",
    name="Askrindo",
    marks=("No DLA", "Askrindo Share"),
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

# KMDastur -- single page, amount block written as bulleted children. Columns
# derived from the document, not yet gone through with Steven.
KMDASTUR = Profile(
    key="kmdastur",
    name="KMDastur",
    marks=("Name of Reinsured", "Interest Insured"),
    bulleted_money=True,
    reviewed=False,
    columns=(
        Column("Class of Business", "Class of Business"),
        Column("Policy Number", "Policy Number"),
        Column("Your Reference", "Your Reference"),
        Column("Period of Insurance", "Period of Insurance"),
        Column("Name of Reinsured", "Name of Reinsured"),
        Column("Name of Insured", "Name of Insured"),
        Column("Interest Insured", "Interest Insured"),
        Column("Currency", "Total Sum Insured", "currency"),
        Column("Total Sum Insured", "Total Sum Insured", "amount"),
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

# Only JRP is in service. Askrindo and KMDastur above are drafts read off a
# single document each and have not been gone through with Steven, so they stay
# out of detection until they have been -- a half-checked profile writing a
# wrong column is worse than refusing the file.
ALL = (JRP,)
DRAFTS = (ASKRINDO, KMDASTUR)


def by_key(key: str) -> Profile | None:
    return next((p for p in ALL if p.key == key), None)


def detect(labels) -> Profile | None:
    """The profile whose marker labels are all present in the document."""
    hits = [p for p in ALL if p.matches(labels)]
    return hits[0] if len(hits) == 1 else None
