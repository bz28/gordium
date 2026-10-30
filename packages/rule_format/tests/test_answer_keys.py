"""Our draft R-1b (drafted by Claude, in 5_zoning_rules/) against the architects' own spreadsheet check of 106 Ithaca Rd.

The spreadsheet is read as they sent it. Every measurement must equal the cells it names, and
our result must equal their PASS/FAIL on every row. The other R-1b rules must not apply or pass.
"""

import re

import openpyxl
import pytest

from rule_format.rulebook import REPO, Context, load, outcome, rulebook_for

SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/spreadsheet_design.yaml"
CELL = re.compile(r"(\w+)!([A-Z]+\d+)")    # Inputs!B4: sheet and cell


@pytest.fixture(scope="module")
def site():
    design = load(SITE)
    book = openpyxl.load_workbook(REPO / design["spreadsheet"], data_only=True)
    rules = {r["id"]: r for r in load(rulebook_for(REPO / design["jurisdiction"], design["zone"]))["rules"]}
    ctx = Context.for_jurisdiction(REPO / "regulations/jurisdictions/new_york/ithaca_city")
    values = {k: m["value"] for k, m in design["measurements"].items()}
    results = {i: outcome(r, values, {"use": ctx.uses}) for i, r in rules.items()}
    return design, book, results


def test_measurements_equal_the_spreadsheet_cells(site):
    design, book, _ = site
    for name, m in design["measurements"].items():
        expr = m["from"]
        if name == "use":
            assert book["Output"]["C3"].value == "Detached one-family"
            continue
        first, *minus = [book[sheet][cell].value for sheet, cell in CELL.findall(expr)]   # "A - B - C"
        worked_out = first - sum(minus)
        assert worked_out == m["value"], f"{name}: {expr} = {worked_out}, not {m['value']}"


def test_every_spreadsheet_row_is_compared(site):
    design, book, _ = site
    rows = [r[0].value for r in book["Output"].iter_rows(min_row=3) if r[0].value]
    assert sorted(rows) == sorted(design["compare"])


def test_our_results_match_theirs_on_every_row(site):
    design, book, results = site
    for row in book["Output"].iter_rows(min_row=3):
        label, theirs = row[0].value, row[6].value
        if label:
            rule = design["compare"][label]
            assert results[rule] == theirs.lower(), f"{label}: they say {theirs}, {rule} says {results[rule]}"


def test_rules_they_dont_cover_dont_apply_or_pass(site):
    design, _, results = site
    others = {i: r for i, r in results.items() if i not in design["compare"].values()}
    # their house has no eaves (the yards to the eaves are the yards); the spreadsheet doesn't say whether there
    # is an accessory building, who lives in the house or whether a home occupation is planned, so those rules
    # wait for them (never a pass); nor how many primary buildings stand on the lot (§325-8B(1), queue item 15), so
    # the lot area for each, the shared-yards and South Hill rows wait for the count; nor
    # whether a stream or inlet is near the lot (§325-26), so that row waits too; nor how many cars a private garage
    # holds (chart p.2 note 6), so the garage row waits
    assert others == {"R-1b.lot_area_other_use": "not_applicable", "R-1b.lot_width_other_use": "not_applicable",
                      "R-1b.parking_other_uses": "not_applicable", "R-1b.yard_projections": "pass",
                      "R-1b.accessory_buildings": "needs_review", "R-1b.occupancy_one_family": "needs_review",
                      "R-1b.home_occupation_size": "needs_review", "R-1b.home_occupation": "needs_review",
                      "R-1b.lot_area_each_primary_building": "needs_review",
                      "R-1b.yards_not_shared": "needs_review", "R-1b.south_hill_overlay": "needs_review",
                      "R-1b.stream_setback": "needs_review", "R-1b.private_garage": "needs_review"}
