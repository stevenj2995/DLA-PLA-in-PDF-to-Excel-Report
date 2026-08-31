
from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

from .. import settings

# ---------------------------------------- reading the template structure

@dataclass
class Column:
    index: int          # 1-based
    letter: str        # "A", "AB", ...
    group: str | None  # merged header on row 2
    header: str | None # header on row 3 -- what parameters are matched against
    flag: str | None   # "Mandatory" / "Optional"
    role: str = "empty"
    number_format: str = "@"

    @property
    def name(self) -> str:
        return (self.header or self.group or self.letter).strip()

    @property
    def clean_name(self) -> str:
        n = self.name.split("\n")[0]
        return " ".join(n.replace("(YYYY-MM-DD)", "").replace("(HH:MM)", "")
                         .replace("(Y/N)", "").split()).strip()

    @property
    def full_name(self) -> str:
        if self.group and self.header and self.group != self.header:
            return f"{self.group} - {self.clean_name}"
        return self.clean_name


@dataclass
class Schema:
    columns: list[Column] = field(default_factory=list)

    def __iter__(self):
        return iter(self.columns)

    def __len__(self):
        return len(self.columns)

    @property
    def match_targets(self) -> list[Column]:
        # only these columns may receive a value matched from the PDF
        return [k for k in self.columns if k.role == "from_pdf"]

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for k in self.columns:
            out[k.role] = out.get(k.role, 0) + 1
        return out


def _role_of(letter: str) -> str:
    if letter == settings.ROW_NUMBER_COLUMN:
        return "row_number"
    if letter in settings.CONSTANT_COLUMNS:
        return "constant"
    if letter in settings.FORMULA_COLUMNS:
        return "formula"
    if letter in settings.COLUMNS_FROM_PDF:
        return "from_pdf"
    if letter in settings.MONITORING_COLUMNS:
        return "monitoring"
    if letter in settings.FEE_COLUMNS:
        return "fee"
    return "empty"


@lru_cache(maxsize=4)
def load_schema(template_path: str | None = None) -> Schema:
    path = Path(template_path) if template_path else settings.template_file()
    wb = openpyxl.load_workbook(path, read_only=False)
    ws = wb[settings.MAIN_SHEET]

    group: dict[int, str] = {}
    for m in ws.merged_cells.ranges:
        if m.min_row == settings.GROUP_ROW:
            value = ws.cell(settings.GROUP_ROW, m.min_col).value
            for c in range(m.min_col, m.max_col + 1):
                if value is not None:
                    group[c] = str(value).strip()

    columns: list[Column] = []
    for c in range(1, ws.max_column + 1):
        letter = get_column_letter(c)
        g = group.get(c)
        if g is None:
            v = ws.cell(settings.GROUP_ROW, c).value
            g = str(v).strip() if v is not None else None
        h = ws.cell(settings.HEADER_ROW, c).value
        f = ws.cell(settings.FLAG_ROW, c).value
        fmt = ws.cell(settings.FIRST_DATA_ROW, c).number_format or "@"
        columns.append(Column(
            index=c, letter=letter, group=g,
            header=str(h).strip() if h is not None else None,
            flag=str(f).strip() if f is not None else None,
            role=_role_of(letter), number_format=fmt,
        ))
    wb.close()
    return Schema(columns)

# ------------------------------------- writing rows into a copy of the template

RE_EXTLST = re.compile(r"<extLst>.*?</extLst>", re.S)
RE_XR_UID = re.compile(r'\s+xr:uid="[^"]*"')
RE_X14_DV = re.compile(r"<x14:dataValidation\b")


@dataclass
class Row:
    values: dict[str, object] = field(default_factory=dict)  # keyed by column letter
    source: str = ""  # file name of the PDF it came from
    warnings: list[str] = field(default_factory=list)


# openpyxl drops cross-sheet validations, so the dropdowns are patched back in
# at the XML level; this finds the sheet part to patch.
def _main_sheet_part(zf: zipfile.ZipFile) -> str:
    wb_xml = zf.read("xl/workbook.xml").decode("utf-8")
    m = re.search(
        r'<sheet[^>]*name="%s"[^>]*r:id="(rId\d+)"' % re.escape(settings.MAIN_SHEET),
        wb_xml,
    )
    if not m:
        return "xl/worksheets/sheet1.xml"
    rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    m2 = re.search(r'<Relationship[^>]*Id="%s"[^>]*Target="([^"]+)"' % m.group(1), rels)
    if not m2:
        return "xl/worksheets/sheet1.xml"
    target = m2.group(1).lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def _read_extlst(template_path: Path, part: str) -> str | None:
    with zipfile.ZipFile(template_path) as z:
        xml = z.read(part).decode("utf-8")
    m = RE_EXTLST.search(xml)
    if not m:
        return None
    return RE_XR_UID.sub("", m.group(0))


def _patch_extlst(source: Path, destination: Path, part: str, block: str) -> None:
    with zipfile.ZipFile(source) as zin, \
         zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == part:
                s = RE_EXTLST.sub("", data.decode("utf-8"))
                s = s.replace("</worksheet>", block + "</worksheet>")
                data = s.encode("utf-8")
            zout.writestr(item, data)

def count_dropdowns(path: Path) -> int:
    with zipfile.ZipFile(path) as z:
        xml = z.read(_main_sheet_part(z)).decode("utf-8", "ignore")
    return len(RE_X14_DV.findall(xml))


def write_rows(
    rows: list[Row],
    destination: Path,
    *,
    operator_email: str,
    template_path: Path | None = None,
    schema: Schema | None = None,
    start_number: int = 1,
) -> dict:
    template_path = Path(template_path or settings.template_file())
    schema = schema or load_schema(str(template_path))
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(template_path) as z:
        part = _main_sheet_part(z)
    block = _read_extlst(template_path, part)
    dropdowns_before = count_dropdowns(template_path)

    wb = openpyxl.load_workbook(template_path)
    ws = wb[settings.MAIN_SHEET]

    fmt = {k.letter: ws.cell(settings.FIRST_DATA_ROW, k.index).number_format for k in schema}

    for r in range(settings.FIRST_DATA_ROW, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None

    constants = dict(settings.CONSTANT_COLUMNS)
    constants[settings.OPERATOR_EMAIL_COLUMN] = operator_email

    for i, b in enumerate(rows):
        r = settings.FIRST_DATA_ROW + i
        for k in schema:
            cell = ws.cell(r, k.index)
            cell.number_format = fmt.get(k.letter, "@")

            if k.letter == settings.ROW_NUMBER_COLUMN:
                cell.value = str(start_number + i)
            elif k.letter in constants and k.letter not in b.values:
                v = constants[k.letter]
                if v is not None:
                    cell.value = v
            elif k.letter in settings.FORMULA_COLUMNS:
                cell.value = _formula(k.letter, r, b)
            elif k.letter in b.values:
                v = b.values[k.letter]
                cell.value = None if v is None or v == "" else v

    wb.save(destination)
    wb.close()

    dropdowns_after = count_dropdowns(destination)
    if block and dropdowns_after < dropdowns_before:
        temp_path = destination.with_suffix(".tmp.xlsx")
        shutil.move(str(destination), str(temp_path))
        try:
            _patch_extlst(temp_path, destination, part, block)
        finally:
            temp_path.unlink(missing_ok=True)
        dropdowns_after = count_dropdowns(destination)

    return {
        "file": str(destination),
        "rows": len(rows),
        "dropdowns_before": dropdowns_before,
        "dropdowns_after": dropdowns_after,
        "dropdowns_intact": dropdowns_after == dropdowns_before,
    }


def _formula(letter: str, r: int, b: Row) -> str | None:
    pattern = settings.FORMULA_COLUMNS[letter]
    if letter == "AR":
        share = b.values.get("_aab_share")
        return pattern.format(r=r, share=share) if share else None
    return pattern.format(r=r)
