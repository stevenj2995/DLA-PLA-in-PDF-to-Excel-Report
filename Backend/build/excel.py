from __future__ import annotations
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

SHEET_NAME = "DLA"
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True)
MIN_WIDTH, MAX_WIDTH = 10, 52


def write(path: str | Path, headers: list[str], rows: list[list[str]]) -> Path:
    """One sheet: the document's own parameters as headers, one row per PDF.

    Everything is written as text on purpose. The values are lifted from the PDF
    exactly as printed -- '49,185,430,585.00' stays that string, so Excel cannot
    reinterpret a number or a date into something the letter never said.
    """
    path = Path(path)
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME

    ws.append(headers)
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    for row in rows:
        ws.append(["" if v is None else str(v) for v in row])

    for i in range(1, len(headers) + 1):
        letter = get_column_letter(i)
        longest = max([len(str(headers[i - 1]))] +
                      [len(str(r[i - 1])) for r in rows if i <= len(r)] or [0])
        ws.column_dimensions[letter].width = max(MIN_WIDTH, min(MAX_WIDTH, longest + 2))
        for cell in ws[letter][1:]:
            cell.alignment = Alignment(vertical="top", wrap_text=False)
            cell.number_format = "@"

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    wb.close()
    return path
