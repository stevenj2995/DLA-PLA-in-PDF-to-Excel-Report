from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import fitz

# Words are grouped into visual lines by their y position. Anything within the
# same band is one line, left to right -- that is how a DLA reads on paper.
LINE_TOLERANCE = 3.0


@dataclass
class Page:
    number: int
    lines: list[str] = field(default_factory=list)

    @property
    def heading(self) -> str:
        return next((l for l in self.lines if l), "")

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass
class Document:
    path: Path
    pages: list[Page] = field(default_factory=list)
    error: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    @property
    def has_text(self) -> bool:
        return any(l.strip() for p in self.pages for l in p.lines)


def _lines_of(page) -> list[str]:
    bands: dict[int, list[tuple[float, str]]] = {}
    for x0, y0, _x1, _y1, word, *_ in page.get_text("words"):
        bands.setdefault(round(y0 / LINE_TOLERANCE), []).append((x0, word))
    out = []
    for _, items in sorted(bands.items()):
        out.append(" ".join(w for _, w in sorted(items)))
    return out


def read(path: str | Path) -> Document:
    path = Path(path)
    doc = Document(path=path)
    try:
        with fitz.open(path) as f:
            for i, page in enumerate(f, start=1):
                doc.pages.append(Page(number=i, lines=_lines_of(page)))
    except Exception as e:
        doc.error = f"tidak bisa dibuka: {e}"
    return doc
