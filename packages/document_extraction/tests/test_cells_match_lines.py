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
CONFECTIONERY = "Confectionery, millinery, dressmaking or other activities involving light hand fabrication as well as sales"
THEATER = "Theater, bowling alley, auditorium, or other similar place of public assembly"
SHOP = "Printing, heating, welding, air conditioning, plumbing, or similar shop"
NOT_COMPARABLE = {   # (page, row): why. Each is read by hand from the PDF in BY_HAND below.
    (2, "Tower for the receipt or transmission of electronic signals or generation of electricity"):
        "label wraps onto 3 lines around its values",
    (3, "Percent of lot area"): "the R-2C value wraps onto the lines above and below",
    (3, "Side (other side minimum)"): "the R-2C value wraps onto the lines above and below",
    (3, "Rear (minimum, % of depth or feet, whichever is less)"): "label and every value wrap onto a 2nd line",
    (14, "First three bed or sleeping rooms per dwelling unit"): "label wraps around the merged value",
    (14, "Dormitory"): "the R-3A and R-3B values wrap onto 4 lines",
    (4, CONFECTIONERY): "label wraps onto 3 lines around its values",
    (4, THEATER): "label wraps onto 3 lines around its values",
    (4, SHOP): "label wraps onto 3 lines around its values",
    (4, "Tower for the receipt or transmission of electronic signals or generation of electricity"):
        "label wraps onto 3 lines around its values",
    (5, "Rear (minimum, % of depth or feet, whichever is less)"): "label and every value wrap onto 3 lines",
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
    assert found == set(BY_HAND)                     # and every one of them is asserted in full below


# The rows the line method can't check, every column read by hand from the PDF: each word's x position
# on the cited lines against the drawn column edges (p.2: R-1A 259–302 … RU 605–672, Additional
# Regulations 672–756; p.3: R-1A 256–310 … RU 693–755; p.14: R-1A 236–285 … RU 596–756), top line first.
REAR = "25%/ 50 ft [fn16]"
B4 = ["B-1A", "B-1B", "B-2A", "B-2C", "B-2D", "B-4", "B-5", "Central Business", "Additional Regulations"]
BY_HAND = {
    # p.2 lines 35-37: "SP" at x 275, 318, 361, 405, 448, 491, 534, 577, 632 on line 36; "§325-9B(1)(j)" at 680
    (2, "Tower for the receipt or transmission of electronic signals or generation of electricity"):
        dict.fromkeys(["R-1A", "R-1B", "R-2A", "R-2B", "R-2C", "R-3A", "R-3AA", "R-3B", "RU"], "SP")
        | {"Additional Regulations": "§325-9B(1)(j)"},
    # p.3 lines 33-35: line 34 has 20% @273, 25% @324, 30% @375, 35% @426, 35% @545, 35% @601, 40% @656,
    # 25% [fn13] @710; R-2C (460-526) has "35%/40%" @470 on line 33 and "/50% [fn12]" @475 on line 35
    (3, "Percent of lot area"): {"R-1A": "20%", "R-1B": "25%", "R-2A": "30%", "R-2B": "35%",
                                 "R-2C": "35%/40% /50% [fn12]", "R-3A": "35%", "R-3AA": "35%", "R-3B": "40%",
                                 "RU": "25% [fn13]"},
    # p.3 lines 39-41: line 40 has 10 ft @274, @325, @375, 5 ft @429, @548, @604, @659, 10 ft @715;
    # R-2C has "0 ft /5 ft /" @470 on line 39 and "10 ft [fn15]" @479 on line 41
    (3, "Side (other side minimum)"): {"R-1A": "10 ft", "R-1B": "10 ft", "R-2A": "10 ft", "R-2B": "5 ft",
                                       "R-2C": "0 ft /5 ft / 10 ft [fn15]", "R-3A": "5 ft", "R-3AA": "5 ft",
                                       "R-3B": "5 ft", "RU": "10 ft"},
    # p.3 lines 42-43: line 42 has "25%/" @270, 321, 372, 422, 480, "20%/" @541, "25%/" @598, "20%/" @653,
    # "25% /" @710; line 43 has "50 ft [fn16]" under each, "50 ft [fn17]" @710
    (3, "Rear (minimum, % of depth or feet, whichever is less)"):
        {"R-1A": REAR, "R-1B": REAR, "R-2A": REAR, "R-2B": REAR, "R-2C": REAR, "R-3A": "20%/ 50 ft [fn16]",
         "R-3AA": REAR, "R-3B": "20%/ 50 ft [fn16]", "RU": "25% / 50 ft [fn17]"},
    # p.14 lines 9-11: "1 space per dwelling unit" @447-545 on line 10, in one drawn rectangle 236-756
    (14, "First three bed or sleeping rooms per dwelling unit"):
        dict.fromkeys(["R-1A", "R-1B", "R-2A", "R-2B", "R-2C", "R-3A", "R-3AA", "R-3B", "RU"], "1 space per dwelling unit"),
    # p.14 lines 14-18: "-" @259, 314, 362, 396, 430 and @520 on line 16; R-3A (449-498) has "1 space" @457,
    # "per 4" @463, "persons" @458, "housed" @459 on lines 14, 15, 17, 18; R-3B (546-596) the same @556-561;
    # RU "1 space per 4 persons housed" @617 on line 16
    (14, "Dormitory"): {"R-1A": "-", "R-1B": "-", "R-2A": "-", "R-2B": "-", "R-2C": "-",
                        "R-3A": "1 space per 4 persons housed", "R-3AA": "-",
                        "R-3B": "1 space per 4 persons housed", "RU": "1 space per 4 persons housed"},
    # p.4 (commercial uses; B-1A 302-344, B-1B -386, B-2A -428, B-2C -469, B-2D -511, B-4 -548, B-5 -584, Central
    # Business -676, Additional Regulations -756), each mark on the middle line of three:
    # line 36 "-" @322, 363, "•" @401, 443, 485, 524, 560, 624
    (4, CONFECTIONERY): dict(zip(B4, ["-", "-", "•", "•", "•", "•", "•", "•", ""])),
    # line 39 "-" @322, 363, "•" @401, 443, "-" @489, "•" @524, 560, 624
    (4, THEATER): dict(zip(B4, ["-", "-", "•", "•", "-", "•", "•", "•", ""])),
    # line 47 "-" @322, 363, 405, 447, 489, "•" @524, 560, "-" @628
    (4, SHOP): dict(zip(B4, ["-", "-", "-", "-", "-", "•", "•", "-", ""])),
    # line 56 "SP" @318, 360, 401, 443, 485, 524, 561, 625; "§325-9B(1)(j)" @685
    (4, "Tower for the receipt or transmission of electronic signals or generation of electricity"):
        dict(zip(B4, ["SP"] * 8 + ["§325-9B(1)(j)"])),
    # p.5 lines 32-34 (B-1A 269-325, B-1B -379, B-2A -439, B-2D -493, B-4 -547, B-5 -601, Central Business -756):
    # "15%/" @283, "10%/" @338, "15%/" @395, 452, 506, 560 on line 32; "10 ft" @668 on line 33; "20 ft [fn9]"
    # @283, "15 ft [fn9]" @338, "20 ft [fn9]" @395, 452, 506, 560 on line 34
    (5, "Rear (minimum, % of depth or feet, whichever is less)"):
        {"B-1A": "15%/ 20 ft [fn9]", "B-1B": "10%/ 15 ft [fn9]", "B-2A": "15%/ 20 ft [fn9]", "B-2D": "15%/ 20 ft [fn9]",
         "B-4": "15%/ 20 ft [fn9]", "B-5": "15%/ 20 ft [fn9]", "Central Business": "10 ft"},
}


def _cells():
    return [json.loads(line) for line in (TEXT / "zoning_charts_2026-04.cells.jsonl").open(encoding="utf-8")][1:]


def test_every_column_of_the_wrapped_rows_matches_the_pdf_read_by_hand():
    cells = _cells()
    for (page, row), expected in BY_HAND.items():
        got = {c["column"]: c["value"] for c in cells if c.get("page") == page and c.get("row") == row}
        assert got == expected, (page, row)


def test_wrapped_rows_lose_and_invent_nothing():
    """Order-free: the words on a wrapped row's lines, less its label, are exactly its cells' words
    (a merged cell once), so nothing on those lines is lost and nothing in a cell comes from elsewhere."""
    lines = {}
    for line in (TEXT / "zoning_charts_2026-04.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if "line" in r:
            lines[(r["page"], r["line"])] = r["text"]
    cells = _cells()
    for page, row in BY_HAND:
        mine = [c for c in cells if c.get("page") == page and c.get("row") == row]
        on_lines = sorted(t for n in mine[0]["row_lines"] for t in tokenize(lines[(page, n)]))
        label = tokenize(row)
        for t in label:
            on_lines.remove(t)
        in_cells = sorted(t for v in {(c["x0"], c["x1"]): c["value"] for c in mine}.values() for t in tokenize(v))
        assert in_cells == on_lines, (page, row)


if __name__ == "__main__":   # the counts for the PR description
    for page, r in sorted(cross_check().items()):
        n = len(r["agreed"]) + len(r["disagreed"])
        print(f"p.{page}: {n} rows compared, {len(r['agreed'])} agreed, {len(r['disagreed'])} disagreed, "
              f"{len(r['not_comparable'])} not comparable: {r['not_comparable']}")
