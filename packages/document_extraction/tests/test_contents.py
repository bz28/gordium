"""Each law's contents list (document_extraction/contents.py): read from the law itself, never typed in."""

import json
from pathlib import Path

import pytest
import yaml

from document_extraction import contents
from rule_format.rulebook import cached

REPO = Path(__file__).resolve().parents[3]
NY = REPO / "regulations/jurisdictions/new_york"
ZONING = NY / "ithaca_city"
BCNYS = NY / "new_york_state_building"
RCNYS = NY / "new_york_state"


def _rows(folder: Path) -> list[dict]:
    path = next((folder / "2_extracted_text").glob("*.contents.jsonl"))
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def _in_cache(folder: Path) -> bool:
    docs = yaml.safe_load((folder / "1_source_documents/sources.yaml").read_text(encoding="utf-8"))["documents"]
    return all(cached(d).exists() for d in docs if d.get("kept_outside_repo") is True)


def _current(folder: Path):
    path, text, problems, skipped = contents.build(folder)
    assert skipped is None and problems == []
    assert path.read_text(encoding="utf-8") == text, f"{path.name} is stale: python -m document_extraction contents"


def test_zoning_contents_is_current():
    _current(ZONING)


@pytest.mark.parametrize("folder", [BCNYS, RCNYS], ids=["bcnys", "rcnys"])
def test_code_book_contents_is_current(folder):
    if not _in_cache(folder):
        pytest.skip("the book is kept outside the repo and isn't in the code cache here")
    _current(folder)


def test_bcnys_contents_pins():
    head, *rows = _rows(BCNYS)
    assert head["problems"] == [] and head["pages"] == [16, 17, 18, 19, 20, 21]
    chapters = [r for r in rows if r["kind"] == "chapter"]
    assert [c["number"] for c in chapters] == [str(n) for n in range(1, 36)]
    ch10 = next(c for c in chapters if c["number"] == "10")
    assert (ch10["title"], ch10["book_page"]) == ("MEANS OF EGRESS", 289)
    s = next(r for r in rows if r["number"] == "1006")
    assert (s["title"], s["chapter"], s["book_page"]) == ("Number of Exits and Exit Access Doorways", "10", 293)
    # wrapped over two lines in the book, joined
    assert next(r for r in rows if r["number"] == "117")["title"] == \
        "Inspection of Solid Fuel-burning Heating Appliances, Chimneys and Flues"
    # every section the extraction brings in is listed
    pieces = [json.loads(x)["id"] for x in (BCNYS / "2_extracted_text/gov.ny.building.2025.sections.jsonl")
              .read_text(encoding="utf-8").splitlines()[1:]]
    have = {r["number"] for r in rows if r["kind"] == "section"}
    assert {contents.section_of(p) for p in pieces} - {None} <= have


def test_rcnys_contents_pins():
    head, *rows = _rows(RCNYS)
    assert head["problems"] == []
    ch3 = [r["number"] for r in rows if r["kind"] == "section" and r.get("chapter") == "3"]
    assert "R301" in ch3 and "R319" in ch3 and all(n.startswith("R3") for n in ch3)
    part3 = next(r for r in rows if r["kind"] == "part" and r["number"] == "III")
    assert part3["book_page"] == 535 and "kept as printed" in part3["note"]       # the book's own misprint


def test_zoning_contents_pins():
    head, *rows = _rows(ZONING)
    arts = [r["number"] for r in rows if r["kind"] == "article"]
    assert arts == ["I", "II", "III", "IV", "V", "VA", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
    s = next(r for r in rows if r["number"] == "325-8")
    assert s["chapter"] == "II" and s["title"] == "District regulations."
    assert next(r for r in rows if r["number"] == "325-28")["chapter"] == "V"


def test_gutter_splits_two_columns():
    w = lambda x0, x1, top, t: {"x0": x0, "x1": x1, "top": top, "text": t}
    words = [w(54, 90, 72, "101"), w(95, 309, 72, "Scope"), w(333, 350, 72, "411"), w(357, 560, 72, "Special"),
             w(66, 300, 85, "102"), w(340, 570, 85, "412")]
    x = contents.gutter(words)
    assert 309 < x < 333
    assert contents.gutter([w(54, 560, 72, "across")]) is None


def test_wrapped_entry_joined_and_unended_entry_is_a_problem():
    lines = [{"page": 1, "line": n, "text": t} for n, t in enumerate([
        "CHAPTER 9 FIRE PROTECTION AND LIFE", "SAFETY SYSTEMS . . . . . . 247",
        "429 Health Care Facilities in Special Flood Hazard Areas112",
        "805 Combustible Materials in Types I and II", "Construction. . . . . 244",
        "806 Never ends"], 1)]
    rows, problems = contents.entries(lines)
    assert [(r["number"], r["title"], r["book_page"]) for r in rows] == [
        ("9", "FIRE PROTECTION AND LIFE SAFETY SYSTEMS", 247),
        ("429", "Health Care Facilities in Special Flood Hazard Areas", 112),
        ("805", "Combustible Materials in Types I and II Construction", 244),
        ("806", "Never ends", None)]
    assert len(problems) == 1 and "806 has no printed page" in problems[0]


def test_a_section_brought_in_but_not_listed_is_a_problem():
    rows = [{"kind": "chapter", "number": "1", "title": "X", "book_page": 1, "page": 1, "line": 1},
            {"kind": "section", "number": "101", "title": "Y", "book_page": 1, "page": 1, "line": 2, "chapter": "1"}]
    assert contents.checks_icc(rows, ["101.2"]) == []
    assert any("1006" in p for p in contents.checks_icc(rows, ["101.2", "Table 1006.2.1"]))
    assert any("isn't in its chapter" in p for p in contents.checks_icc(
        rows + [{"kind": "section", "number": "205", "title": "Z", "book_page": 2, "page": 1, "line": 3,
                 "chapter": "1"}], []))


def test_a_zoning_section_title_leaves_out_its_footnote_mark_and_history_note():
    assert contents.heading("Accessory Dwelling Units (ADUs).[fn24] [Added 5-7-2025 by Ord. No. 2025-04]") == \
        "Accessory Dwelling Units (ADUs)."
    assert contents.heading("Shot clock tolls, extensions and reasonable delay periods. [Added 10-6-2021 by Ord.") \
        == "Shot clock tolls, extensions and reasonable delay periods."
    assert contents.heading("(Reserved)[fn7]") == "(Reserved)"
    assert contents.heading("Title.") == "Title."
    rows = {r["number"]: r for r in _rows(ZONING) if r.get("kind") == "section"}
    assert rows["325-28"]["title"] == "Accessory Dwelling Units (ADUs)."
    assert rows["325-28"]["printed"].startswith("Accessory Dwelling Units (ADUs).[fn24] [Added")
