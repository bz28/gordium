import json
import shutil
from pathlib import Path

import pdfplumber
import pytest

import document_extraction.__main__ as cli
from document_extraction import charts as chart_reader
from document_extraction.charts import line_tokens, read_charts, read_page, render
from document_extraction.extract import _mark_superscripts, page_lines, sha256

REPO = Path(__file__).resolve().parents[3]
ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
CHARTS = ITHACA / "1_source_documents/zoning_charts_2026-04.pdf"
SAVED = ITHACA / "2_extracted_text/zoning_charts_2026-04.cells.jsonl"
PAGES = [2, 3, 14]
DISTRICTS = ["R-1A", "R-1B", "R-2A", "R-2B", "R-2C", "R-3A", "R-3AA", "R-3B", "RU"]


@pytest.fixture(scope="module")
def cells():
    return read_charts(CHARTS, PAGES)


def cell(cells, page, row, column, section=None):
    found = [r for r in cells[1:] if r.get("page") == page and r.get("row") == row and r.get("column") == column
             and (section is None or r.get("section") == section)]
    assert len(found) == 1, (page, row, column, section, len(found))
    return found[0]


# The real charts ----------------------------------------------------------------------------------------

def test_saved_cells_match_a_fresh_read(cells):
    assert SAVED.read_text(encoding="utf-8") == "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in cells)
    assert cells[0] == {"file": CHARTS.name, "sha256": sha256(CHARTS), "pages": PAGES, "reader": chart_reader.READER}


def test_every_page_finds_the_district_columns(cells):
    pages = {r["page"]: r for r in cells[1:] if "columns" in r}
    assert sorted(pages) == PAGES
    for page in PAGES:
        names = [c["name"] for c in pages[page]["columns"]]
        assert names[:9] == DISTRICTS                                       # groups like "R-1" aren't columns
    assert [c["name"] for c in pages[2]["columns"]][9:] == ["Additional Regulations"]
    r1b = next(c for c in pages[3]["columns"] if c["name"] == "R-1B")
    assert r1b["headers"] == ["Single Family Residential", "R-1", "R-1B"]
    assert next(c for c in pages[2]["columns"] if c["name"] == "R-1B")["headers"][1] == "R-1 [fn1,2]"


def test_only_the_notes_under_page_2_are_unresolved(cells):
    unresolved = [r for r in cells[1:] if "unresolved" in r]
    assert [(r["page"], r["unresolved"]) for r in unresolved] == [(2, "lines right after the table don't fit its columns")]
    assert unresolved[0]["text"].startswith("NOTES: (1) In R-1 and R-2 Districts")


def test_every_line_inside_a_table_is_in_exactly_one_row(cells):
    """No word is lost: each line between the header and the table's end belongs to one row."""
    with pdfplumber.open(CHARTS) as pdf:
        for page in PAGES:
            table = next(r for r in cells[1:] if r.get("page") == page and "columns" in r)
            lines, _ = page_lines(pdf.pages[page - 1])
            inside = {n for n, line in enumerate(lines, 1)
                      if table["top"] < (line["top"] + line["bottom"]) / 2 < table["bottom"]}
            rows = {}
            for r in cells[1:]:
                if r.get("page") == page and "row" in r:
                    rows.setdefault((r["top"], r["bottom"]), set()).update(r["row_lines"])
            taken = [n for ns in rows.values() for n in ns]
            assert sorted(taken) == sorted(inside) and len(taken) == len(set(taken))


def test_every_row_has_one_value_for_every_column(cells):
    columns = {r["page"]: [c["name"] for c in r["columns"]] for r in cells[1:] if "columns" in r}
    rows = {}
    for r in cells[1:]:
        if "row" in r:
            rows.setdefault((r["page"], r["top"]), []).append(r["column"])
    assert all(names == columns[page] for (page, _), names in rows.items())
    assert len(rows) == 72


def test_every_word_of_a_row_is_in_its_label_or_one_cell(cells):
    """Joining a row's label and its distinct cells gives back exactly the words on its lines."""
    with pdfplumber.open(CHARTS) as pdf:
        for page in PAGES:
            lines, body = page_lines(pdf.pages[page - 1])
            rows = {}
            for r in cells[1:]:
                if r.get("page") == page and "row" in r:
                    row = rows.setdefault((r["top"], r["bottom"]), {"label": r["row"], "lines": r["row_lines"], "cells": {}})
                    row["cells"][(r["x0"], r["x1"])] = r["value"]
            for row in rows.values():
                words = sorted(t.text for n in row["lines"] for t in line_tokens(lines[n - 1], n, body))
                placed = (row["label"] + " " + " ".join(row["cells"].values())).replace("[fn", " [fn").split()
                assert sorted(w for w in placed) == sorted(" ".join(words).replace("[fn", " [fn").split()), row["label"]


def test_line_numbers_and_text_match_the_extracted_text():
    saved = [json.loads(line) for line in (ITHACA / "2_extracted_text/zoning_charts_2026-04.jsonl").open()][1:]
    with pdfplumber.open(CHARTS) as pdf:
        for page in PAGES:
            lines, body = page_lines(pdf.pages[page - 1])
            texts = {r["line"]: r["text"] for r in saved if r["page"] == page}
            assert {n: render(line_tokens(line, n, body)) for n, line in enumerate(lines, 1)} == texts
            assert all(render(line_tokens(line, n, body)) == _mark_superscripts(line, body)
                       for n, line in enumerate(lines, 1))


@pytest.mark.parametrize("page, section, row, column, value", [
    (3, "Yard Dimensions", "Front (minimum)", "R-3A", "10 ft"),
    (3, "Minimum Lot Width", "One-family dwelling, detached", "R-2B", "35 ft"),
    (3, "Maximum Building Height [fn10]", "Number of stories", "R-3AA", "3/2 [fn11]"),
    (3, "Maximum lot coverage by buildings", "Percent of lot area", "R-2C", "35%/40% /50% [fn12]"),   # 3 lines
    (3, "Yard Dimensions", "Side (other side minimum)", "R-2C", "0 ft /5 ft / 10 ft [fn15]"),
    (3, "Yard Dimensions", "Rear (minimum, % of depth or feet, whichever is less)", "RU", "25% / 50 ft [fn17]"),
    (3, "Minimum Lot Size [fn3]", "Fraternity, sorority, or group house", "R-1A", ""),                 # empty cell
    (2, "Primary Uses", "Multiple family dwelling [fn4]", "RU", "•[fn5]"),
    (2, "Primary Uses", "School and related buildings", "Additional Regulations", "§325-10(C)(4)"),
    (2, "Accessory Uses", "Tower for the receipt or transmission of electronic signals or generation of electricity",
     "R-2B", "SP"),                                                                            # label on 3 lines
    (2, "Accessory Uses", "Tower for the receipt or transmission of electronic signals or generation of electricity",
     "Additional Regulations", "§325-9B(1)(j)"),
    (3, "Yard Dimensions", "Rear (minimum, % of depth or feet, whichever is less)", "R-3A", "20%/ 50 ft [fn16]"),
    (14, "Residential", "Dormitory", "R-3A", "1 space per 4 persons housed"),                       # 4 lines
    (14, "Residential", "Dormitory", "R-3B", "1 space per 4 persons housed"),
    (14, "Residential", "Dormitory", "RU", "1 space per 4 persons housed"),
    (14, "Residential", "Dormitory", "R-3AA", "-"),
    (14, "Minimum Loading Requirement", "Neighborhood commercial facility", "R-2B", "See §325-21"),
])
def test_cells_of_other_districts(cells, page, section, row, column, value):
    assert cell(cells, page, row, column, section)["value"] == value


def test_merged_cells_apply_to_every_district_they_cover(cells):
    parking = cell(cells, 14, "First three bed or sleeping rooms per dwelling unit", "R-1B")
    assert parking["value"] == "1 space per dwelling unit" and parking["spans"] == DISTRICTS
    assert parking["row_lines"] == [9, 10, 11]                                 # the label wraps around the value
    loading = cell(cells, 14, "Neighborhood commercial facility", "R-2A")       # merged by drawn borders
    assert loading["spans"] == ["R-2A", "R-2B", "R-2C"]
    assert cell(cells, 3, "Front (minimum)", "R-1B")["spans"] == ["R-1B"]


def test_headings_name_the_section_of_the_rows_below(cells):
    heading = cell(cells, 3, "Yard Dimensions", "R-1B")
    assert heading["heading"] is True and heading["value"] == ""
    assert cell(cells, 3, "Front (minimum)", "R-1B")["section"] == "Yard Dimensions"
    lot_size = cell(cells, 3, "One-family dwelling, detached", "R-1B", "Minimum Lot Size [fn3]")
    lot_width = cell(cells, 3, "One-family dwelling, detached", "R-1B", "Minimum Lot Width")
    assert (lot_size["value"], lot_width["value"]) == ("6,000 sf", "50 ft")    # same label, two sections


def test_notes_under_a_chart_are_not_a_row(cells):
    rows = {r["row"] for r in cells[1:] if r.get("page") in (2, 14) and "row" in r}
    assert not any(row.startswith("NOTES") for row in rows)


def test_check_catches_a_hand_edited_cells_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO", tmp_path)
    src = tmp_path / "regulations/jurisdictions/ny/town/1_source_documents"
    src.mkdir(parents=True)
    shutil.copy(CHARTS, src / CHARTS.name)
    (src / "sources.yaml").write_text(f"documents:\n  - file: {CHARTS.name}\n    sha256: {sha256(CHARTS)}\n"
                                      f"    chart_pages: [3]\n")
    assert cli.main([]) == 0 and cli.main(["--check"]) == 0
    out = src.parent / "2_extracted_text" / f"{CHARTS.stem}.cells.jsonl"
    rows = out.read_text().splitlines()
    n = next(i for i, r in enumerate(rows) if '"column": "R-1B"' in r and '"Front (minimum)"' in r)
    rows[n] = rows[n].replace('"value": "25 ft"', '"value": "20 ft"')
    out.write_text("\n".join(rows) + "\n")
    assert cli.main(["--check"]) == 1


# Built pages: each safeguard on its own --------------------------------------------------------------

class Page:
    """Just the parts of a pdfplumber page the chart reader looks at."""

    def __init__(self, rects, lines, verticals=()):
        self.rects = [{"x0": a, "x1": b, "top": t, "bottom": u, "width": b - a, "height": u - t}
                      for a, t, b, u in rects]
        self.lines = [{"x0": x, "x1": x, "top": t, "bottom": u} for x, t, u in verticals]
        self._lines = lines


def line(top, *words):
    """A line of 10 pt text: words = (x0, text) or (x0, text, "fn") for a raised 6 pt footnote marker."""
    text, chars = [], []
    for word in words:
        x, w, fn = word[0], word[1], len(word) > 2
        text.append(w)
        for i, _ in enumerate(w):
            size = 6 if fn else 10
            chars.append({"x0": x + 5 * i, "x1": x + 5 * i + 4, "top": top, "size": size,
                          "bottom": top + (5 if fn else 10)})
    return {"text": " ".join(text), "chars": chars, "top": top, "bottom": top + 10}


HEADER = [(0, 0, 100, 20), (100, 0, 200, 10), (100, 10, 150, 20), (150, 10, 200, 20)]   # label | R-1 over R-1A R-1B
HEADER_LINES = [line(0, (120, "R-1")), line(10, (105, "R-1A"), (155, "R-1B"))]


def read(monkeypatch, rects, lines, verticals=()):
    page = Page(HEADER + rects, HEADER_LINES + lines, verticals)
    monkeypatch.setattr(chart_reader, "page_lines", lambda p: (p._lines, 10.0))
    return read_page(page, 1)


def test_a_group_header_is_not_a_column(monkeypatch):
    out = read(monkeypatch, [(0, 20, 100, 40), (100, 20, 150, 40), (150, 20, 200, 40)],
               [line(25, (5, "Front"), (110, "25"), (160, "10"))])
    assert [c["name"] for c in out[0]["columns"]] == ["R-1A", "R-1B"]
    assert {r["column"]: r["value"] for r in out[1:]} == {"R-1A": "25", "R-1B": "10"}


def test_a_white_row_between_shaded_rows_is_read(monkeypatch):
    shaded = [(0, 20, 100, 40), (100, 20, 150, 40), (150, 20, 200, 40), (0, 60, 100, 80), (100, 60, 150, 80),
              (150, 60, 200, 80)]
    out = read(monkeypatch, shaded, [line(25, (5, "Front"), (110, "1")), line(45, (5, "Side"), (110, "2")),
                                     line(65, (5, "Rear"), (110, "3"))])
    assert [(r["row"], r["value"]) for r in out[1:] if r["column"] == "R-1A"] == [("Front", "1"), ("Side", "2"), ("Rear", "3")]


def test_a_word_across_a_cell_edge_is_unresolved(monkeypatch):
    out = read(monkeypatch, [(0, 20, 100, 40), (100, 20, 150, 40), (150, 20, 200, 40)],
               [line(25, (5, "Front"), (140, "25ft"))])                       # 140–159 crosses 150
    assert any(r.get("unresolved") == "word crosses a cell edge" and r["text"] == "25ft" for r in out)
    assert not any(r.get("value") == "25ft" for r in out)


def test_a_band_holding_two_rows_is_unresolved(monkeypatch):
    shaded = [(0, 20, 100, 30), (100, 20, 150, 30), (150, 20, 200, 30), (0, 30, 100, 90), (100, 30, 150, 90),
              (150, 30, 200, 90)]
    out = read(monkeypatch, shaded, [line(20, (5, "Front"), (110, "1")), line(32, (5, "Side"), (110, "2")),
                                     line(75, (5, "Rear"), (110, "3"))])
    assert any(r.get("unresolved") == "band looks like more than one row" for r in out)
    assert not any(r.get("row") == "Side Rear" for r in out)


def test_a_drawn_merged_cell_covers_every_column_under_it(monkeypatch):
    out = read(monkeypatch, [(0, 20, 100, 40), (100, 20, 200, 40)], [line(25, (5, "Parking"), (120, "1"), (127, "space"))])
    values = {r["column"]: (r["value"], r["spans"]) for r in out[1:]}
    assert values == {"R-1A": ("1 space", ["R-1A", "R-1B"]), "R-1B": ("1 space", ["R-1A", "R-1B"])}


def test_drawn_vertical_borders_merge_a_white_row(monkeypatch):
    shaded = [(0, 20, 100, 40), (100, 20, 150, 40), (150, 20, 200, 40)]
    lines = [line(25, (5, "Front"), (110, "1")), line(45, (5, "Loading"), (130, "See"), (147, "§1"))]
    plain = read(monkeypatch, shaded, lines)                                   # without borders: unsure, reported
    assert any(r.get("unresolved") == "lines right after the table don't fit its columns" and r["lines"] == [4]
               for r in plain)
    assert not any(r.get("row") == "Loading" for r in plain)
    bordered = read(monkeypatch, shaded, lines, verticals=[(0, 40, 55), (100, 40, 55), (200, 40, 55)])
    loading = [r for r in bordered[1:] if r.get("row") == "Loading"]
    assert {r["column"]: r["value"] for r in loading} == {"R-1A": "See §1", "R-1B": "See §1"}


def test_a_stripe_across_the_whole_row_is_unresolved(monkeypatch):
    out = read(monkeypatch, [(0, 20, 200, 40)], [line(25, (5, "Front"), (110, "25"), (160, "10"))])
    assert any(r.get("unresolved") == "cell covers the label and a column" and r["text"] == "Front 25 10" for r in out)
    assert not any("value" in r for r in out)


def test_an_outer_border_alone_does_not_merge_a_row(monkeypatch):
    shaded = [(0, 20, 100, 40), (100, 20, 150, 40), (150, 20, 200, 40)]
    out = read(monkeypatch, shaded, [line(25, (5, "Front"), (110, "1"), (160, "2")),
                                     line(45, (5, "Rear"), (110, "3"), (160, "4"))], verticals=[(0, 0, 60), (200, 0, 60)])
    assert any(r.get("unresolved") == "cell covers the label and a column" and r["text"] == "Rear 3 4" for r in out)
    assert not any(r.get("value") == "Rear 3 4" for r in out)


def test_a_district_name_in_a_body_cell_is_not_taken_for_a_header(monkeypatch):
    shaded = [(0, 20, 100, 40), (100, 20, 150, 40), (150, 20, 200, 40), (0, 60, 100, 80), (100, 60, 150, 80),
              (150, 60, 200, 80)]
    out = read(monkeypatch, shaded, [line(25, (5, "Front"), (110, "1"), (160, "2")),
                                     line(65, (5, "Same"), (110, "3"), (160, "RU"))])
    assert out == [{"page": 1, "unresolved": "district names at different heights; can't tell the header",
                    "text": "R-1A, RU"}]


def test_a_row_whose_values_are_all_unplaced_is_not_a_heading(monkeypatch):
    shaded = [(0, 20, 100, 40), (100, 20, 150, 40), (150, 20, 200, 40), (0, 60, 100, 80), (100, 60, 150, 80),
              (150, 60, 200, 80)]
    out = read(monkeypatch, shaded, [line(25, (5, "Front"), (140, "25ft")),            # crosses 150
                                     line(45, (5, "Side"), (110, "5"), (160, "6"))])
    assert not any(r.get("row") == "Front" for r in out)                       # the whole row is unresolved
    assert {r["section"] for r in out if r.get("row") == "Side"} == {None}     # and names no section


def test_a_row_with_one_uncertain_cell_writes_none_of_its_values(monkeypatch):
    out = read(monkeypatch, [(0, 20, 150, 40), (150, 20, 200, 40)], [line(25, (5, "Front"), (110, "25"), (160, "10"))])
    assert any(r.get("unresolved") == "cell covers the label and a column" for r in out)
    assert not any("value" in r for r in out)                                  # not even R-1B's "10"


def test_a_header_column_left_of_the_districts_is_unresolved(monkeypatch):
    page = Page([(0, 0, 50, 20), (50, 0, 100, 20), (100, 0, 150, 20), (0, 20, 50, 40), (50, 20, 100, 40),
                 (100, 20, 150, 40)],
                [line(5, (55, "B-1"), (105, "R-1A")), line(25, (5, "Front"), (60, "25"), (110, "10"))])
    monkeypatch.setattr(chart_reader, "page_lines", lambda p: (p._lines, 10.0))
    assert read_page(page, 1) == [{"page": 1, "unresolved": DIVIDED, "text": "B-1, 25"}]


DIVIDED = "the label area is divided: a column left of the districts?"


def test_an_unnamed_column_left_of_the_districts_is_caught_on_white_rows_too(monkeypatch):
    rects = [(0, 0, 50, 20), (50, 0, 100, 20), (100, 0, 150, 20)]                # header: label | (unnamed) | R-1A
    rects += [(0, t, 50, t + 20) for t in (20, 60)] + [(50, t, 100, t + 20) for t in (20, 60)] \
        + [(100, t, 150, t + 20) for t in (20, 60)]                             # shaded rows; "Side" is white
    page = Page(rects, [line(5, (105, "R-1A")), line(25, (5, "Front"), (110, "10")),
                        line(45, (5, "Side"), (60, "5"), (110, "6")), line(65, (5, "Rear"), (110, "7"))])
    monkeypatch.setattr(chart_reader, "page_lines", lambda p: (p._lines, 10.0))
    out = read_page(page, 1)
    assert out[0]["unresolved"] == DIVIDED and not any("value" in r for r in out)   # no "Side 5" row
    bordered = Page([(0, 0, 100, 20), (100, 0, 150, 20), (0, 20, 100, 40), (100, 20, 150, 40)],
                    [line(5, (105, "R-1A")), line(25, (5, "Front"), (60, "25"), (110, "10"))],
                    verticals=[(50, 20, 40)])                                   # a border inside the label area
    assert read_page(bordered, 1)[0]["unresolved"] == DIVIDED


def test_a_column_covered_by_two_cells_is_unresolved(monkeypatch):
    out = read(monkeypatch, [(0, 20, 100, 40), (100, 20, 200, 40), (100, 20, 150, 40)],   # merged + R-1A's own
               [line(25, (5, "Front"), (160, "25"))])
    assert any(r.get("unresolved") == "column covered by more than one cell" for r in out)
    assert not any("value" in r for r in out)


def test_a_label_area_split_into_cells_is_unresolved(monkeypatch):
    page = Page([(0, 0, 50, 20), (50, 0, 100, 20), (100, 0, 150, 20), (0, 20, 50, 40), (50, 20, 100, 40),
                 (100, 20, 150, 40)],                                         # an unnamed column left of R-1A
                [line(5, (105, "R-1A")), line(25, (5, "Front"), (60, "25"), (110, "10"))])
    monkeypatch.setattr(chart_reader, "page_lines", lambda p: (p._lines, 10.0))
    out = read_page(page, 1)
    assert out == [{"page": 1, "unresolved": DIVIDED, "text": "(unnamed), 25"}]   # no "Front 25" row
    nested = read(monkeypatch, [(0, 20, 100, 40), (0, 20, 40, 40), (100, 20, 150, 40), (150, 20, 200, 40)],
                  [line(25, (5, "Front"), (60, "25"), (110, "10"))])            # two label cells, both at the left
    assert any(r.get("unresolved") == "label area is split into cells" for r in nested)
    assert not any("value" in r for r in nested)


def test_every_column_gets_a_cell_or_the_row_is_unresolved(monkeypatch):
    shaded = [(0, 20, 100, 40), (100, 20, 150, 40), (160, 20, 200, 40),       # R-1B's cell drawn short, empty
              (0, 60, 100, 80), (100, 60, 150, 80), (150, 60, 200, 80)]
    out = read(monkeypatch, shaded, [line(25, (5, "Front"), (110, "25")), line(65, (5, "Side"), (110, "5"))])
    assert any(r.get("unresolved") == "cell covers part of a column" and r["lines"] == [3] for r in out)
    assert not any(r.get("row") == "Front" for r in out)                       # not written without R-1B
    heading_only = read(monkeypatch, [(0, 20, 100, 40), (100, 20, 125, 40), (125, 20, 200, 40)],
                        [line(25, (5, "Yard"), (30, "Dimensions"))])          # no column has a whole cell
    assert not any(r.get("heading") for r in heading_only)
    assert any("unresolved" in r for r in heading_only)


def test_a_table_without_drawn_body_rows_is_unresolved_not_a_crash(monkeypatch):
    out = read(monkeypatch, [], [line(25, (5, "Front"), (110, "1"))])
    assert out[1:] == [{"page": 1, "unresolved": "no body rows drawn under the header"}]


def test_a_cell_covering_part_of_a_column_is_unresolved(monkeypatch):
    out = read(monkeypatch, [(0, 20, 100, 40), (100, 20, 175, 40), (175, 20, 200, 40)],
               [line(25, (5, "Front"), (110, "1"))])
    assert any(r.get("unresolved") == "cell covers part of a column" for r in out)


def test_a_cell_under_no_column_is_unresolved(monkeypatch):
    out = read(monkeypatch, [(0, 20, 100, 40), (100, 20, 150, 40), (150, 20, 200, 40), (200, 20, 260, 40)],
               [line(25, (5, "Front"), (110, "1"), (210, "x"))])
    assert any(r.get("unresolved") == "cell under no column" and r["text"] == "x" for r in out)


def test_notes_running_across_the_columns_end_the_table(monkeypatch):
    shaded = [(0, 20, 100, 40), (100, 20, 150, 40), (150, 20, 200, 40)]
    out = read(monkeypatch, shaded, [line(25, (5, "Front"), (110, "1")),
                                     line(45, (5, "Rear"), (110, "2")),
                                     line(52, (5, "NOTES:"), (90, "(1)"), (140, "across"))])   # crosses 100 and 150
    assert {r["row"] for r in out[1:] if "row" in r} == {"Front"}
    assert out[0]["bottom"] == 40                                              # ends after the last drawn row
    assert any(r.get("unresolved") == "lines right after the table don't fit its columns" and r["lines"] == [4, 5]
               for r in out)                                               # Rear and the notes, reported together


def test_a_last_white_row_that_fits_is_read(monkeypatch):
    shaded = [(0, 20, 100, 40), (100, 20, 150, 40), (150, 20, 200, 40)]
    out = read(monkeypatch, shaded, [line(25, (5, "Front"), (110, "1")), line(45, (5, "Rear"), (110, "2")),
                                     line(80, (5, "NOTES:"), (90, "(1)"), (140, "across"))])   # far below: not this row
    assert [r["value"] for r in out[1:] if r.get("row") == "Rear"] == ["2", ""]
    assert out[0]["bottom"] == 55 and not any("unresolved" in r for r in out)


def test_a_footnote_is_its_own_token_in_a_cell(monkeypatch):
    out = read(monkeypatch, [(0, 20, 100, 40), (100, 20, 150, 40), (150, 20, 200, 40)],
               [line(25, (5, "Front"), (110, "50"), (122, "16", "fn"))])
    assert next(r for r in out[1:] if r["column"] == "R-1A")["value"] == "50 [fn16]"


def test_a_page_without_a_table_says_so(monkeypatch):
    monkeypatch.setattr(chart_reader, "page_lines", lambda p: (p._lines, 10.0))
    assert read_page(Page([], [line(5, (5, "Notes"))]), 4) == [{"page": 4, "unresolved": "no table drawn on this page"}]
    no_districts = Page([(0, 0, 100, 20)], [line(5, (5, "Title"))])
    assert read_page(no_districts, 4) == [{"page": 4, "unresolved": "no district header found"}]
