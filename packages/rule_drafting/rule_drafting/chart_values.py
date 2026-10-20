"""Plain code (no AI) for the chart side of drafting: the chart's sections, the numbers in a cell, the
footnotes under a table, and the sections of the law a text points to.

The AI never types a chart number. A drafted chart rule names a *slot* for each number it needs (a row,
which number in that row's cell, whether it is a percent, how many numbers and which footnotes the cell
must have) and this module fills the slot from each district's own cell. A cell whose shape isn't the one
the template expects (another count of numbers, other footnotes, a "-") is never filled: that district's
rule is listed for a person instead.
"""

import re
from pathlib import Path

from rule_format.rulebook import read_jsonl

FOOTNOTE = re.compile(r"\[fn([^\]]*)\]")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
NOT_APPLICABLE = {"", "-"}          # the chart's "no requirement here" / "not permitted" marks


def load_cells(path: Path) -> tuple[dict, list[dict], list[dict]]:
    """(header, the per-page table records, the cells) from a chart reader's cells file."""
    rows = read_jsonl(path)
    return rows[0], [r for r in rows[1:] if "columns" in r], [r for r in rows[1:] if "value" in r]


def districts(tables: list[dict]) -> list[str]:
    """The district columns, in chart order (R-1A ... RU), from the first table that has them."""
    from rule_format.rulebook import DISTRICT_COLUMN
    for t in tables:
        names = [c["name"] for c in t["columns"] if DISTRICT_COLUMN.fullmatch(c["name"])]
        if names:
            return names
    return []


def sections(cells: list[dict], pages: list[int]) -> list[tuple[int, str]]:
    """(page, section) for every section with data rows on these pages, in chart order."""
    seen = []
    for c in cells:
        key = (c["page"], c["section"])
        if c["page"] in pages and c["section"] and not c["heading"] and key not in seen:
            seen.append(key)
    return seen


def section_rows(cells: list[dict], page: int, section: str) -> dict[str, dict[str, dict]]:
    """{row label: {column: cell}} for one section."""
    out: dict[str, dict[str, dict]] = {}
    for c in cells:
        if (c["page"], c["section"]) == (page, section) and not c["heading"]:
            out.setdefault(c["row"].strip(), {})[c["column"]] = c
    return out


def heading(cells: list[dict], page: int, section: str) -> dict | None:
    return next((c for c in cells if c["page"] == page and c["heading"] and c["row"].strip() == section.strip()), None)


def numbers(value: str) -> list[tuple[float, bool]]:
    """The numbers a cell states, in order, as (number, is a percent), without footnote markers:
    "25%/ 50 ft [fn16]" -> [(25, True), (50, False)]; "3/2 [fn11]" -> [(3, False), (2, False)]."""
    text = FOOTNOTE.sub(" ", value)
    return [(float(n.rstrip("%").replace(",", "")), n.endswith("%")) for n in NUMBER.findall(text)]


def footnotes(value: str) -> set[str]:
    """The footnote markers in a cell: "50 ft [fn16]" -> {"16"}; "[fn1,2]" -> {"1", "2"}."""
    return {n.strip() for m in FOOTNOTE.findall(value) for n in m.split(",") if n.strip()}


def fill(slot: dict, cell: dict | None) -> tuple[float | None, str | None]:
    """(the slot's number from this cell, None) or (None, why the cell can't fill it)."""
    if cell is None:
        return None, "no cell (or the chart reader couldn't read it with certainty)"
    value = cell["value"].strip()
    if FOOTNOTE.sub("", value).strip() in NOT_APPLICABLE:
        return None, f"the chart shows {value or 'nothing'!r} here"
    found = numbers(value)
    if len(found) != slot["numbers_in_cell"]:
        return None, f"the cell {value!r} has {len(found)} numbers, the rule expects {slot['numbers_in_cell']}"
    if footnotes(value) != set(slot["footnotes"]):
        return None, (f"the cell {value!r} has footnotes {sorted(footnotes(value)) or 'none'}, "
                      f"the rule expects {sorted(slot['footnotes']) or 'none'}")
    if not 1 <= slot["number"] <= len(found):
        return None, f"the rule asks for number {slot['number']} of {len(found)}"
    n, percent = found[slot["number"] - 1]
    if percent != slot["percent"]:
        return None, f"number {slot['number']} of {value!r} is {'' if percent else 'not '}a percent"
    return (n / 100 if percent else n), None


def number_text(n: float) -> str:
    """A number as it goes into a formula: 6000, 0.25, 2.5."""
    return str(int(n)) if float(n).is_integer() else repr(round(n, 10))


def notes_under_table(rows: list[dict], page: int, table_bottom: float) -> dict[str, dict]:
    """The footnotes printed under a chart's table: {"16": {"lines": [66, 66], "text": "(16) But not ..."}}.
    A note starts at a line beginning "(N)" (or "NOTES: (N)") and runs until the next one."""
    out: dict[str, dict] = {}
    current = None
    for r in rows:
        if r["page"] != page or r["top"] <= table_bottom:
            continue
        text = re.sub(r"^NOTES:\s*", "", r["text"])
        if m := re.match(r"\((\d+)\)", text):
            current = m[1]
            out[current] = {"lines": [r["line"], r["line"]], "text": text}
        elif current:
            out[current]["lines"][1] = r["line"]
            out[current]["text"] += " " + text
    return out


def section_refs(text: str) -> list[str]:
    """The sections of Chapter 325 a text points to, as piece ids: "§325-8(B)(1)" -> "325-8B",
    "§ 325-16" -> "325-16", "§325-29.1" -> "325-29.1". In order, once each."""
    out = []
    for num, letter in re.findall(r"§\s*325-(\d+(?:\.\d+)*)(?:\s*\(?([A-Z])\)?)?", text):
        pid = f"325-{num}{letter}"
        if pid not in out:
            out.append(pid)
    return out
