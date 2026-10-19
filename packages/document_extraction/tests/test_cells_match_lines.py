"""Cross-check every district column: the chart reader's cells against the plain extracted text.

Two independent methods read the same chart rows. The chart reader places words by the rectangles
the PDF draws (2_extracted_text/*.cells.jsonl). The text extractor (PR 3) just reads each line left
to right (2_extracted_text/*.jsonl). For a row that sits on one line, the line must be exactly the
row's label followed by its cells' values in column order (a merged cell once). A row that can't be
compared that way (its label or a value wraps onto other lines) is listed with the reason, never
skipped quietly; the list is pinned below, so a new one fails the test until someone looks at it.

What it proves and doesn't: every value of every district, and their order, are the same by both
methods (no word lost, added, changed or reordered). A line has no columns, so it can't tell which
column an empty cell is in; that comes from the drawn rectangles, test_charts.py's spot checks of
other districts, and test_r1b_matches_chart.py for R-1B.
"""

import json
from collections import defaultdict
from pathlib import Path

from rule_format.rulebook import tokenize

REPO = Path(__file__).resolve().parents[3]
TEXT = REPO / "regulations/jurisdictions/new_york/ithaca_city/2_extracted_text"
NOT_COMPARABLE = {   # (page, row): why. Each is checked by hand against the PDF in test_charts.py.
    (2, "Tower for the receipt or transmission of electronic signals or generation of electricity"):
        "label wraps onto 3 lines around its values",
    (3, "Percent of lot area"): "the R-2C value wraps onto the lines above and below",
    (3, "Side (other side minimum)"): "the R-2C value wraps onto the lines above and below",
    (3, "Rear (minimum, % of depth or feet, whichever is less)"): "label and every value wrap onto a 2nd line",
    (14, "First three bed or sleeping rooms per dwelling unit"): "label wraps around the merged value",
    (14, "Dormitory"): "the R-3A and R-3B values wrap onto 4 lines",
}


def cross_check():
    """{page: {"agreed": [...], "disagreed": [...], "not_comparable": {row: why}}}"""
    lines = {}
    for line in (TEXT / "zoning_charts_2026-04.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if "line" in r:
            lines[(r["page"], r["line"])] = r["text"]
    rows = defaultdict(list)
    for line in (TEXT / "zoning_charts_2026-04.cells.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if "row" in r and not r["heading"]:
            rows[(r["page"], r["top"], r["bottom"])].append(r)
    report = defaultdict(lambda: {"agreed": [], "disagreed": [], "not_comparable": {}})
    for (page, _, _), cells in sorted(rows.items()):
        row = cells[0]["row"]
        if len(cells[0]["row_lines"]) != 1:
            report[page]["not_comparable"][row] = f"on lines {cells[0]['row_lines']}"
            continue
        merged = {}
        for c in cells:                       # column order; a merged cell counts once
            merged.setdefault((c["x0"], c["x1"]), c["value"])
        by_cells = tokenize(row) + [t for v in merged.values() for t in tokenize(v)]
        by_lines = tokenize(lines[(page, cells[0]["row_lines"][0])])
        report[page]["agreed" if by_cells == by_lines else "disagreed"].append(row)
    return report


def test_every_comparable_row_agrees_value_for_value():
    report = cross_check()
    assert {p: r["disagreed"] for p, r in report.items() if r["disagreed"]} == {}
    assert sum(len(r["agreed"]) for r in report.values()) >= 50          # the comparison really ran (56 today)


def test_rows_that_cant_be_compared_are_exactly_the_listed_ones():
    report = cross_check()
    found = {(p, row) for p, r in report.items() for row in r["not_comparable"]}
    assert found == set(NOT_COMPARABLE)


if __name__ == "__main__":   # the counts for the PR description
    for page, r in sorted(cross_check().items()):
        n = len(r["agreed"]) + len(r["disagreed"])
        print(f"p.{page}: {n} rows compared, {len(r['agreed'])} agreed, {len(r['disagreed'])} disagreed, "
              f"{len(r['not_comparable'])} not comparable: {r['not_comparable']}")
