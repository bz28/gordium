"""The eval: Rhino models of 106 Ithaca Rd, measured by Gordium, against the architects' own spreadsheet.

1. spreadsheet_design_model.3dm, the design drawn exactly as their spreadsheet describes it: every measurement
   equals their cell and every result equals their PASS/FAIL (11/11).
2. model.3dm, the architects' own Rhino model, as they sent it: its house solid sits away from the lot, so the
   yards can't be measured (NEEDS REVIEW, never a guess). With the solid moved onto its own outline on the
   Site layer (the exact shift is found from the vertices, not typed in), the numbers are compared with the
   spreadsheet and every difference is pinned and explained in docs/discrepancies_with_architects.md.
"""

import copy
import re

import openpyxl
import pytest

from model_measurement.__main__ import pairs, text
from model_measurement.measure import measure
from model_measurement.project import load_facts
from model_measurement.read_3dm import read_site
from rule_format.rulebook import REPO, Context, load, outcome, rulebook_for

SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
CELL = re.compile(r"(\w+)!([A-Z]+\d+)")


@pytest.fixture(scope="module")
def theirs():
    design = load(SITE / "spreadsheet_design.yaml")
    book = openpyxl.load_workbook(REPO / design["spreadsheet"], data_only=True)
    cells = {}
    for name, m in design["measurements"].items():
        if name != "use":
            first, *minus = [book[s][c].value for s, c in CELL.findall(m["from"])]
            cells[name] = first - sum(minus)
    results = {design["compare"][r[0].value]: r[6].value.lower() for r in book["Output"].iter_rows(min_row=3)
               if r[0].value}
    rules = load(rulebook_for(REPO / design["jurisdiction"], design["zone"]))["rules"]
    ctx = Context.for_jurisdiction(REPO / design["jurisdiction"])
    return cells, results, {r["id"]: r for r in rules}, {"use": ctx.uses}


def ours(measured, rules, allowed, compared):
    values = {k: m["value"] for k, m in measured.items()}
    return {i: outcome(rules[i], values, allowed) for i in compared}


def test_the_spreadsheet_design_drawn_as_a_model_gives_their_numbers_and_their_results(theirs):
    cells, results, rules, allowed = theirs
    facts = load_facts(SITE / "spreadsheet_design_model_facts.yaml")
    measured = measure(read_site(SITE / "spreadsheet_design_model.3dm", facts), facts)
    for name, value in cells.items():
        if name == "lot_area":      # their 6,674 sf is the real lot's (with its jog); the drawing is 73 x 90
            assert measured[name]["value"] == 73 * 90
            continue
        assert measured[name]["value"] == value, f"{name}: measured {measured[name]['value']}, they have {value}"
    assert ours(measured, rules, allowed, results) == results          # 11/11 of their rows


@pytest.fixture(scope="module")
def their_model():
    facts = load_facts(SITE / "model_facts.yaml")
    return facts, read_site(SITE / "model.3dm", facts)


def test_their_model_as_sent_measures_the_lot_but_not_the_yards(their_model):
    facts, site = their_model
    m = measure(site, facts)
    assert m["lot_area"]["value"] is None and "survey" in m["lot_area"]["reason"]     # drawn, not surveyed
    assert round(m["lot_area"]["readings"][0]["value"]) == 6675 and m["lot_width"]["value"] == 73.0
    assert m["building_height"]["value"] == 35.0
    for name in ("front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard", "building_area"):
        assert m[name]["value"] is None and m[name]["reason"] == "a building isn't on the lot (is it part of this design?)"


def _on_its_outline(site):
    """Their house solid moved onto its own outline on the Site layer: the shift that maps every corner of the
    solid's base onto a corner of the outline (it exists; they are the same shape)."""
    import rhino3dm as r
    model = r.File3dm.Read(str(SITE / "model.3dm"))
    names = [layer.FullPath for layer in model.Layers]
    outline = next(o.Geometry for o in model.Objects if names[o.Attributes.LayerIndex] == "Site"
                   and isinstance(o.Geometry, r.PolylineCurve) and str(o.Attributes.Id) != site["lot"]["id"])
    corners = [(outline.Point(i).X, outline.Point(i).Y) for i in range(outline.PointCount - 1)]
    base = [p for f in site["buildings"][0]["faces"] for p in f["points"] if p[2] == 0]
    for cx, cy in corners:
        dx, dy = cx - base[0][0], cy - base[0][1]
        if all(any(abs(x + dx - a) < 1e-6 and abs(y + dy - b) < 1e-6 for a, b in corners) for x, y, _ in base):
            moved = copy.deepcopy(site)
            for f in moved["buildings"][0]["faces"]:
                f["points"] = [[x + dx, y + dy, z] for x, y, z in f["points"]]
            return moved
    raise AssertionError("the solid isn't a moved copy of the outline")


def test_their_model_with_the_house_on_its_outline_against_their_spreadsheet(their_model, theirs):
    facts, site = their_model
    cells, results, rules, allowed = theirs
    m = measure(_on_its_outline(site), facts)
    got = {k: m[k]["value"] for k in cells}
    # same as the spreadsheet
    assert got["lot_width"] == cells["lot_width"] == 73
    assert got["front_yard"] == cells["front_yard"] == 30
    assert got["side_yard_smaller"] == got["side_yard_larger"] == 10 == cells["side_yard_smaller"]
    assert got["building_height"] == cells["building_height"] == 35
    # different, each explained in docs/discrepancies_with_architects.md
    # their model's house is about 53.3-53.6 x 40.4-40.8 ft (not quite rectangular); the sheet's is 53 x 35
    assert round(got["building_area"], 1) == 2169.2 and cells["building_area"] == 1855
    # the house is deeper, so the rear yard is the sheet's unused "Back Offset" input (20 ft), not 25 ft
    # (with the back line read as part of the east side line, the jog alone is the rear line: every reading the
    # geometry allows, review round 8; the nearest is still 20 ft)
    assert min(r["value"] for r in m["rear_yard"]["readings"]) == 20.0 and cells["rear_yard"] == 25
    assert got["lot_depth"] is None and cells["lot_depth"] == 90              # the jog: three readings, none 90
    assert sorted(round(r["value"], 2) for r in m["lot_depth"]["readings"]) == [94.82, 100.06, 128.69]
    # results: never a PASS where they don't agree. The two rules that need the lot depth need review, and so
    # do the two that need the lot area: their model's lot is drawn from the map, not a survey
    mine = ours(m, rules, allowed, results)
    assert {k: v for k, v in mine.items() if v != results[k]} == {
        "R-1b.rear_yard": "needs_review",
        "R-1b.lot_area_one_family_detached": "needs_review", "R-1b.lot_coverage": "needs_review"}


def test_the_committed_measured_projects_match_a_fresh_measurement():
    found = pairs()
    assert {p[0].name for p in found} >= {"model.3dm", "spreadsheet_design_model.3dm"}
    for model, facts, out in found:
        assert out.read_text(encoding="utf-8") == text(model, facts), f"{out.name} is out of date: run python -m model_measurement"


def test_the_committed_spreadsheet_model_matches_its_generator(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("make", REPO / "packages/model_measurement/tests/make_spreadsheet_model.py")
    make = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(make)
    fresh = tmp_path / "fresh.3dm"
    make.build().Write(str(fresh), 8)
    facts = load_facts(SITE / "spreadsheet_design_model_facts.yaml")
    a, b = read_site(SITE / "spreadsheet_design_model.3dm", facts), read_site(fresh, facts)
    for x in (a, b):            # object ids are new on every write
        x["lot"]["id"] = None
        for building in x["buildings"]:
            building["id"] = None
    assert a == b


@pytest.mark.parametrize("bad, message", [({"grade_elevation": "0"}, "grade_elevation must be a number"),
                                          ({"street_line": [[[0, 0]]]}, "street_line must be"),
                                          ({"stories": "3"}, "stories must be a whole number"),
                                          ({"zone": 7}, "zone must be text"),
                                          ({"corner_lot": "no"}, "corner_lot must be yes or no")])
def test_mistyped_lot_facts_are_refused_with_a_plain_message(tmp_path, bad, message):
    import yaml
    from model_measurement.project import project
    facts = {**load_facts(SITE / "spreadsheet_design_model_facts.yaml"), **bad}
    path = tmp_path / "facts.yaml"
    path.write_text(yaml.safe_dump({"lot_facts": facts}), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_facts(path)
    with pytest.raises(ValueError, match=message):
        project(SITE / "spreadsheet_design_model.3dm", facts)
