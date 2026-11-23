"""The CBD rulebooks against the chart reader's cells: two independent readings of the same chart must agree.

The charts give all six CBD sub-districts one column, "Central Business", headed "CBD-50, -60, -85, -100, -120, -140"
(p.4 uses, p.5 dimensions); each sub-district's maximum height is its suffix (note 5), and CBD-140 also has 12 stories
(note 4). The rulebooks (5_zoning_rules/CBD-50.yaml ... CBD-140.yaml) were drafted by reading the chart; the chart
reader (document_extraction/charts.py) read the same pages into cells. For each district: every mark on p.4 decides the
use rule (• passes, SP needs review, - fails), every number on p.5 is a limit some rule passes exactly at and fails just
past, and every "-" on p.5 (no lot size, no front or side yard) is no limit at all.
"""

import json
import re
from pathlib import Path

import pytest

from rule_format.place import place
from rule_format.rulebook import load, outcome

REPO = Path(__file__).resolve().parents[3]
ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
CELLS = ITHACA / "2_extracted_text/zoning_charts_2026-04.cells.jsonl"
CHART = "zoning_charts_2026-04.pdf"
COLUMN = "Central Business"
DISTRICTS = ["CBD-50", "CBD-60", "CBD-85", "CBD-100", "CBD-120", "CBD-140"]
USES = load(ITHACA / "4_term_definitions/uses.yaml")
ALLOWED = {"use": set(USES)}
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
MAXH, MINH = "Maximum Building Height [fn3]", "Minimum Building Height [fn3,6]"
REAR = "Rear (minimum, % of depth or feet, whichever is less)"

# Every measure a CBD rule reads, at a value that passes everything (a three-story building well inside every limit):
# a test moves one measure at a time from here.
BASE = {"use": "business_or_professional_office", "lot_area": 30000, "lot_width": 150, "lot_depth": 200, "building_area": 1000, "building_height": 30,
        "stories": 3, "front_yard": 0, "side_yard_smaller": 0, "side_yard_larger": 0, "rear_yard": 60,
        "rear_yard_eaves": 60, "conversion": False, "dwelling_units": 1, "rooms_let_for_profit": 0}

# What a p.5 row with a number means as a limit on one measure: (measure, "min"/"max", what else the row needs).
ROWS = {
    ("Minimum Lot Width", "Other use"): ("lot_width", "min", {"use": "business_or_professional_office"}),
    ("Minimum Lot Width", "Motel"): ("lot_width", "min", {"use": "hotel_motel", "lot_area": 20000}),
    (MINH, "Number of stories"): ("stories", "min", {}),
    (MINH, "Height in feet"): ("building_height", "min", {}),
    ("Maximum Lot Coverage by Buildings", "Percent of lot area"): ("building_area", "max", {}),
    ("Yard Dimensions", REAR): ("rear_yard", "min", {}),
}


def numbers(value: str) -> list[float]:
    text = re.sub(r"\[fn[^\]]*\]", "", value)
    return [float(n.rstrip("%").replace(",", "")) / (100 if n.endswith("%") else 1) for n in NUMBER.findall(text)]


def _rows():
    return [json.loads(line) for line in CELLS.open(encoding="utf-8")][1:]


def _cells():
    return [r for r in _rows() if r.get("column") == COLUMN and "value" in r and not r["heading"]]


def _citing(rules, cell):
    return [r for r in rules for s in r["sources"] if s["file"] == CHART and s.get("cell") == {
        "section": cell["section"], "row": cell["row"], "column": cell["column"]} and s["page"] == cell["page"]]


def _rules(district):
    return load(ITHACA / f"5_zoning_rules/{district}.yaml")["rules"]


def _verdicts(rules, values):
    return [outcome(r, values, ALLOWED) for r in rules if r["kind"] == "rule"]


def test_the_cbd_column_heading_names_the_six_districts_with_rulebooks_and_no_other():
    """The heading as the reader read it, spelled out, is jurisdiction.yaml's shared column; each has a rulebook. CBD-52,
    which the City's online map shows, is in neither chart nor §325-4: no rulebook (an open question)."""
    heads = {c["name"]: c["headers"] for r in _rows() if r.get("page") in (4, 5) and "columns" in r for c in r["columns"]}
    head = heads[COLUMN][-1]
    assert head in ("CBD-50, -60, -85, -100, -120, -140",)
    spelled = ["CBD" + part.strip() if part.strip().startswith("-") else part.strip() for part in head.split(",")]
    assert spelled == DISTRICTS == place(ITHACA).shared_columns[COLUMN]
    assert sorted(p.stem for p in (ITHACA / "5_zoning_rules").glob("CBD*.yaml")) == sorted(DISTRICTS)
    assert not (ITHACA / "5_zoning_rules/CBD-52.yaml").exists()


@pytest.mark.parametrize("district", DISTRICTS)
def test_every_use_mark_decides_the_use_rule(district):
    use_rule = next(r for r in _rules(district) if r["id"] == f"{district}.use")
    by_name = {v["name"]: k for k, v in USES.items()}
    marks = [c for c in _cells() if c["page"] == 4 and c["section"] == "Primary Uses"]
    assert len(marks) == 34
    for c in marks:
        want = {"•": "pass", "SP": "needs_review", "-": "fail"}[c["value"]]
        assert outcome(use_rule, {"use": by_name[c["row"]]}, ALLOWED) == want, (district, c["row"], c["value"])
        assert _citing([use_rule], c), (district, c["row"])
    assert outcome(use_rule, {"use": "fraternity_sorority_group_house"}, ALLOWED) == "fail"


@pytest.mark.parametrize("district", DISTRICTS)
def test_every_dimension_cell_is_a_limit_some_rule_holds(district):
    rules = _rules(district)
    checked = 0
    for c in _cells():
        if c["page"] != 5 or not numbers(c["value"]) or c["value"].startswith("see note"):   # note 5: its own test
            continue
        assert (c["section"], c["row"]) in ROWS, f"a CBD number nobody reads: {c['section']} / {c['row']}"
        measure, way, fixed = ROWS[(c["section"], c["row"])]
        citing = _citing(rules, c)
        assert citing, f"{district}: no rule cites {c['section']} / {c['row']}"
        n = numbers(c["value"])[0]
        limit = n * BASE["lot_area"] if measure == "building_area" else n
        at = dict(BASE, **fixed, **{measure: limit})
        past = dict(at, **{measure: limit + 0.01 if way == "max" else limit - 0.01})
        assert all(v != "fail" for v in _verdicts(citing, at)), (district, c["row"], at)
        assert "fail" in _verdicts(citing, past), (district, c["row"], past)
        checked += 1
    assert checked == len(ROWS)


@pytest.mark.parametrize("district", DISTRICTS)
def test_the_height_is_the_districts_suffix_and_the_stories_only_cbd_140s(district):
    """Note 5: "Each of the CBD sub-districts have a maximum building height that corresponds with its suffix"; note 4:
    "CBD-140 has a maximum building height of 12 stories". The height cell reads "see note 5", the stories cell "- [fn4]"."""
    rules = {r["id"].split(".", 1)[1]: r for r in _rules(district)}
    h = int(district.split("-")[1])
    cell = next(c for c in _cells() if c["page"] == 5 and c["section"] == MAXH and c["row"] == "Height in feet")
    assert cell["value"] == "see note 5" and _citing([rules["height"]], cell)
    at = dict(BASE, building_height=h, rear_yard=10)
    assert outcome(rules["height"], at, ALLOWED) == "pass"
    assert all(v != "fail" for v in _verdicts(rules.values(), at))
    assert outcome(rules["height"], dict(at, building_height=h + 0.01), ALLOWED) == "fail"
    stories = next(c for c in _cells() if c["page"] == 5 and c["section"] == MAXH and c["row"] == "Number of stories")
    assert stories["value"] == "- [fn4]"
    if district == "CBD-140":
        assert _citing([rules["stories"]], stories)
        assert outcome(rules["stories"], {"stories": 12}, ALLOWED) == "pass"
        assert outcome(rules["stories"], {"stories": 13}, ALLOWED) == "fail"
    else:
        assert "stories" not in rules
        assert all(v != "fail" for v in _verdicts(rules.values(), dict(BASE, stories=40)))


@pytest.mark.parametrize("district", DISTRICTS)
def test_a_dash_on_the_bulk_chart_is_no_limit(district):
    """The CBD column's lot sizes (every use but a motel) and its front and side yards are "-": a tiny lot and a building
    on its street and side lot lines fail nothing (a motel's lot is §325-22A's)."""
    rules = _rules(district)
    dashes = {(c["section"], c["row"]) for c in _cells() if c["page"] == 5 and c["value"] == "-"}
    assert {("Yard Dimensions", "Front (minimum)"), ("Yard Dimensions", "Side (one side minimum)"),
            ("Yard Dimensions", "Side (other side minimum)"), ("Minimum Lot Size", "Other use")} <= dashes
    for use in ("business_or_professional_office", "multiple_family", "one_family_detached", "retail_store_or_service_commercial"):
        small = dict(BASE, use=use, lot_area=1200, building_area=1200, lot_width=10, front_yard=0, side_yard_smaller=0,
                     side_yard_larger=0)
        assert all(v != "fail" for v in _verdicts(rules, small)), (district, use)


def test_the_two_story_minimum_follows_section_325_16g_and_note_6():
    """§325-16G's two stories, "notwithstanding anything to the contrary", name CBD-60 to CBD-140, not CBD-50: there a
    one-story building of 500 sf or less is exempt (note 6); elsewhere it needs review (an open question, §5.26)."""
    small = {"stories": 1, "building_area": 500}
    for d in DISTRICTS:
        rule = next(r for r in _rules(d) if r["id"] == f"{d}.min_stories")
        assert outcome(rule, small, ALLOWED) == ("pass" if d == "CBD-50" else "needs_review"), d
        assert outcome(rule, {"stories": 1, "building_area": 500.01}, ALLOWED) == "fail", d


def test_no_cbd_rulebook_asks_for_loading_and_each_flags_what_8d_adds():
    """§325-21C: "There shall be no off-street loading requirement for any properties located in any CBD zoning
    district." §325-8D: active street-level use in every CBD district (3); CBD-50's historic review (1); CBD-85's West
    Green Street stepback (2)."""
    for d in DISTRICTS:
        ids = {r["id"].split(".", 1)[1]: r for r in _rules(d)}
        assert "loading" not in ids
        assert ids["active_street_level_use"]["kind"] == "flag" and "applies_when" not in ids["active_street_level_use"]
        assert ("historic_review" in ids) == (d == "CBD-50")
        assert ("green_street_stepback" in ids) == (d == "CBD-85")
