"""The B-district rulebooks against the chart reader's cells: two independent readings of the same chart must agree.

The rulebooks (5_zoning_rules/B-1a.yaml ... B-5.yaml) were drafted by reading the zoning chart (p.4 uses, p.5
dimensions); the chart reader (document_extraction/charts.py) read the same pages into cells from what the PDF draws.
For each district's own column: every mark on p.4 decides the use rule (• passes, SP needs review, - fails), and every
number on p.5 is a limit some rule passes exactly at and fails just past. In the other direction, every p.5 cell of the
district that states a number is cited by some rule, so a row the drafter skipped is caught.
"""

import json
import re
from pathlib import Path

import pytest

from rule_format.rulebook import load, outcome

REPO = Path(__file__).resolve().parents[3]
ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
CELLS = ITHACA / "2_extracted_text/zoning_charts_2026-04.cells.jsonl"
CHART = "zoning_charts_2026-04.pdf"
DISTRICTS = {"B-1a": "B-1A", "B-1b": "B-1B", "B-2a": "B-2A", "B-2d": "B-2D", "B-4": "B-4", "B-5": "B-5"}
USES = load(ITHACA / "4_term_definitions/uses.yaml")
ALLOWED = {"use": set(USES)}
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
LOT, WIDTH = "Minimum Lot Size", "Minimum Lot Width"
MAXH, MINH = "Maximum Building Height [fn3]", "Minimum Building Height [fn3,6]"
YARD = "Yard Dimensions"
REAR = "Rear (minimum, % of depth or feet, whichever is less)"

# Every measure a B rule reads, at a value that passes everything (a two-story building well inside every limit):
# a test moves one measure at a time from here.
BASE = {"lot_area": 30000, "lot_width": 150, "lot_depth": 200, "building_area": 1000, "building_height": 30,
        "stories": 2, "front_yard": 30, "side_yard_smaller": 30, "side_yard_larger": 30, "rear_yard": 60,
        "conversion": False, "dwelling_units": 1, "rooms_let_for_profit": 0}

# What a p.5 row means as a limit on one measure: (measure, "min"/"max", the use that reads the row, the limit from
# the cell's numbers). Written once from the row labels; the numbers always come from each district's own cell.
ROWS = {
    (LOT, "One-family dwelling, detached"): ("lot_area", "min", {"use": "one_family_detached"}),
    (LOT, "One-family dwelling, semi-detached"): ("lot_area", "min", {"use": "one_family_semi_detached"}),
    (LOT, "One-family dwelling, attached, new construction"): ("lot_area", "min", {"use": "one_family_attached"}),
    (LOT, "One-family dwelling, attached, by conversion"): ("lot_area", "min", {"use": "one_family_attached", "conversion": True}),
    (LOT, "Two-family dwelling"): ("lot_area", "min", {"use": "two_family"}),
    (LOT, "Multiple family dwelling, new construction"): ("lot_area", "min", {"use": "multiple_family"}),
    (LOT, "Multiple family dwelling, by conversion"): ("lot_area", "min", {"use": "multiple_family", "conversion": True}),
    (LOT, "Other use"): ("lot_area", "min", {"use": "business_or_professional_office"}),
    (WIDTH, "Other use"): ("lot_width", "min", {"use": "business_or_professional_office"}),
    (MAXH, "Number of stories"): ("stories", "max", {}),
    # yards held at 0, so the §325-16C bonus (taller with larger yards) can't lift the limit
    (MAXH, "Height in feet"): ("building_height", "max", {"front_yard": 0, "side_yard_smaller": 0, "side_yard_larger": 0,
                                                       "rear_yard": 0}),
    (MINH, "Number of stories"): ("stories", "min", {}),
    (MINH, "Height in feet"): ("building_height", "min", {}),
    ("Maximum Lot Coverage by Buildings", "Percent of lot area"): ("building_area", "max", {}),
    (YARD, "Front (minimum)"): ("front_yard", "min", {}),
    (YARD, "Side (one side minimum)"): ("side_yard_larger", "min", {}),
    (YARD, "Side (other side minimum)"): ("side_yard_smaller", "min", {}),
}


def numbers(value: str) -> list[float]:
    text = re.sub(r"\[fn[^\]]*\]", "", value)
    return [float(n.rstrip("%").replace(",", "")) / (100 if n.endswith("%") else 1) for n in NUMBER.findall(text)]


def _cells(column):
    rows = [json.loads(line) for line in CELLS.open(encoding="utf-8")][1:]
    return [r for r in rows if r.get("column") == column and "value" in r and not r["heading"]]


def _citing(rules, cell):
    return [r for r in rules for s in r["sources"] if s["file"] == CHART and s.get("cell") == {
        "section": cell["section"], "row": cell["row"], "column": cell["column"]} and s["page"] == cell["page"]]


def _verdicts(rules, values):
    return [outcome(r, values, ALLOWED) for r in rules if r["kind"] == "rule"]


@pytest.mark.parametrize("district", sorted(DISTRICTS))
def test_every_use_mark_decides_the_use_rule(district):
    rules = load(ITHACA / f"5_zoning_rules/{district}.yaml")["rules"]
    use_rule = next(r for r in rules if r["id"] == f"{district}.use")
    by_name = {v["name"]: k for k, v in USES.items()}
    marks = [c for c in _cells(DISTRICTS[district]) if c["page"] == 4 and c["section"] == "Primary Uses"]
    assert len(marks) == 34
    for c in marks:
        use = by_name[c["row"]]
        want = {"•": "pass", "SP": "needs_review", "-": "fail"}[c["value"]]
        assert outcome(use_rule, {"use": use}, ALLOWED) == want, (district, c["row"], c["value"])
        assert _citing([use_rule], c), (district, c["row"])
    # a use the commercial chart doesn't list at all is never permitted
    assert outcome(use_rule, {"use": "fraternity_sorority_group_house"}, ALLOWED) == "fail"


@pytest.mark.parametrize("district", sorted(DISTRICTS))
def test_every_dimension_cell_is_a_limit_some_rule_holds(district):
    rules = load(ITHACA / f"5_zoning_rules/{district}.yaml")["rules"]
    checked = 0
    for c in _cells(DISTRICTS[district]):
        if c["page"] != 5 or (c["section"], c["row"]) not in ROWS or not numbers(c["value"]):
            continue
        measure, way, fixed = ROWS[(c["section"], c["row"])]
        citing = _citing(rules, c)
        assert citing, f"{district}: no rule cites {c['section']} / {c['row']}"
        n = numbers(c["value"])[0]
        limit = n * BASE["lot_area"] if measure == "building_area" else n
        at = dict(BASE, **fixed, **{measure: limit})
        past = dict(at, **{measure: limit + 0.01 if way == "max" else limit - 0.01})
        if measure == "building_area":       # coverage: the lot is held, the buildings grow
            at["lot_area"] = past["lot_area"] = BASE["lot_area"]
        assert all(v != "fail" for v in _verdicts(citing, at)), (district, c["row"], at)
        if district == "B-2a" and measure == "building_area":
            assert "needs_review" in _verdicts(citing, past)     # note 7: up to 75% with parking nearby
        else:
            assert "fail" in _verdicts(citing, past), (district, c["row"], past)
        checked += 1
    assert checked >= 9


@pytest.mark.parametrize("district", sorted(DISTRICTS))
def test_the_rear_yard_is_the_percent_capped_and_floored(district):
    rules = {r["id"]: r for r in load(ITHACA / f"5_zoning_rules/{district}.yaml")["rules"]}
    cell = next(c for c in _cells(DISTRICTS[district]) if c["page"] == 5 and c["row"] == REAR)
    pct, cap = numbers(cell["value"])
    rear = rules[f"{district}.rear_yard"]
    assert _citing([rear], cell)
    for depth in (50, 100, 140, 400):
        need = max(min(pct * depth, cap), 10)          # note 9: but not less than 10 ft
        assert outcome(rear, {"rear_yard": need, "lot_depth": depth}, ALLOWED) == "pass"
        assert outcome(rear, {"rear_yard": need - 0.01, "lot_depth": depth}, ALLOWED) == "fail"


def test_every_b_district_on_the_bulk_chart_has_a_rulebook():
    """B-2C is on the use chart (p.4) but has no column on the bulk chart (p.5): it has no rulebook (the plan,
    docs/decisions/2026-11-22_commercial_districts.md). Every other B column does."""
    rows = [json.loads(line) for line in CELLS.open(encoding="utf-8")][1:]
    bulk = {c["name"] for r in rows if r.get("page") == 5 and "columns" in r for c in r["columns"]}
    uses = {c["name"] for r in rows if r.get("page") == 4 and "columns" in r for c in r["columns"]}
    assert {n for n in bulk if n.startswith("B-")} == set(DISTRICTS.values())
    assert {n for n in uses if n.startswith("B-")} - set(DISTRICTS.values()) == {"B-2C"}
    assert not (ITHACA / "5_zoning_rules/B-2c.yaml").exists()
