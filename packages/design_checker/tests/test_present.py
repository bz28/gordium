"""What the panel, the viewport and the report show (design_checker/present.py; docs/design/rhino_ui_spec.md):
each test names the spec criterion it pins. Results come from the checker; present can only make one more
cautious, so most of these check that something is never shown as complying without evidence."""

import re
import sys
from pathlib import Path

import openpyxl
import pytest

from design_checker import present
from design_checker.check import check
from model_measurement.measure import measure
from model_measurement.project import fact_problems, load_facts
from rule_format.rulebook import REPO, load

SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
MODEL = SITE / "spreadsheet_design_model.3dm"
RULES = {r["id"]: r for r in load(REPO / "regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/R-1b.yaml")["rules"]}
sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_measure import FACTS, RECT, box, sloped_roof_box  # noqa: E402


@pytest.fixture(scope="module")
def surveyed():
    return load_facts(SITE / "spreadsheet_design_model_facts.yaml")


@pytest.fixture(scope="module")
def tax_map(surveyed):
    return check(MODEL, {**surveyed, "lot_surveyed": False, "address": "106 Ithaca Rd, Ithaca, NY"})


def items(view):
    return {i["name"]: i for i in view["items"]}


# ---- D3: one summary, every row counted, bad news first, never a check mark ----------------------------------

def test_the_summary_counts_every_row_bad_news_first_and_never_shows_a_check_mark():
    rows = [{"status": s, "group": g} for s, g in [
        (present.COMPLIES, "site"), (present.COMPLIES, "site"), (present.REVIEW, "site"), (present.COMPLIES, "building"),
        (present.FAILS, "building"), (present.REVIEW, "building"), (present.NOT_CHECKED, "not_checked"),
        (present.NOT_CHECKED, "not_covered")]]
    assert present.summary(rows) == "1 does not comply · 2 need review · 3 comply · 1 not checked"
    assert present.summary([{"status": present.COMPLIES, "group": "building"}]) == "1 complies"
    assert "✓" not in present.summary(rows) and "0 " not in present.summary(rows)


def test_the_same_summary_is_used_for_the_panel_and_the_report(tax_map, surveyed, tmp_path):
    report = tmp_path / "r.xlsx"
    result = check(MODEL, {**surveyed, "lot_surveyed": False}, report)
    title = openpyxl.load_workbook(report)["Check"]["A1"].value
    assert title == "GORDIUM | " + result["view"]["summary"]


# ---- C2: tax-map lot lines, ±2'-0" worst case ------------------------------------------------------------------

def test_an_at_limit_yard_needs_review_on_a_tax_map_lot_but_complies_on_a_survey(tax_map, surveyed):
    tm = items(tax_map["view"])
    assert tm["Side yard, West"]["status"] == present.REVIEW
    assert "tax map" in tm["Side yard, West"]["reason"] and "8'-0\"" in tm["Side yard, West"]["reason"]
    assert tm["Rear yard"]["status"] == present.COMPLIES          # +2'-6" > 2'-0" even at the worst case
    assert tm["Lot width"]["status"] == present.COMPLIES
    sv = items(check(MODEL, surveyed)["view"])
    assert sv["Side yard, West"]["status"] == present.COMPLIES      # a survey: no tolerance


def test_the_tolerance_only_ever_makes_a_result_more_cautious(tax_map):
    rows = {r["Rule id"]: r["Error"] for r in tax_map["rows"]}
    for i in tax_map["view"]["items"]:
        if i["rule"] and i["status"] == present.COMPLIES:
            assert rows[i["rule"]] == "PASS"                         # never complies unless the checker passed it


# ---- C3–C6: the grade, the roof ---------------------------------------------------------------------------------

def _site(buildings):
    return {"units": "ft", "lot": RECT, "buildings": buildings, "problems": []}


def test_no_grade_means_height_and_stories_wait_for_one():
    m = measure(_site([box(10, 25, 35, 65)]), {**FACTS, "grade_elevation": None, "ground_is_flat": None})
    assert m["building_height"]["value"] is None and "ground level isn't given" in m["building_height"]["reason"]


def test_spot_grades_at_the_walls_give_the_grade_plane_and_moving_the_house_needs_review():
    spots = [[22, 24, 1.0], [22, 66, 3.0], [9, 45, 2.0], [36, 45, 2.0]]      # one at each wall of x 10-35, y 25-65
    f = {**FACTS, "grade_elevation": None, "ground_is_flat": None, "grade_points": spots}
    m = measure(_site([box(10, 25, 35, 65, 0, 30)]), f)
    assert m["building_height"]["value"] == pytest.approx(30 - 2.0)          # average of the walls' levels
    moved = measure(_site([box(10, 45, 35, 85, 0, 30)]), f)                  # the house moved 20 ft back
    assert moved["building_height"]["value"] is None
    assert "spot grades no longer at the building's walls" in moved["building_height"]["reason"]


def test_existing_grade_makes_height_and_stories_need_review():
    m = measure(_site([box(10, 25, 35, 65)]), {**FACTS, "grade_is": "existing"})
    for name in ("building_height", "stories"):
        assert m[name]["value"] is None and "existing grade" in m[name]["reason"]


def test_grade_facts_are_checked_like_any_other():
    assert fact_problems({"grade_points": [[1, 2]]}) and fact_problems({"grade_is": "rough"})
    assert not fact_problems({"grade_points": [[1, 2, 3]], "grade_from": "terrain", "grade_is": "finished"})


def test_a_roof_that_isnt_flat_needs_review_even_if_every_reading_passes():
    measured = measure(_site([sloped_roof_box(10, 25, 35, 65, 20, 30, "house")]), FACTS)
    row = {"Rule id": "R-1b.height", "Error": "NEEDS REVIEW", "Provisional": "passes under every reading",
           "Why": "the readings give different values", "Short": "Building height", "Requirement": "Building height"}
    v = present.view([row], [], RULES, measured, {**FACTS, "jurisdiction": "regulations/jurisdictions/new_york/ithaca_city",
                                                  "zone": "R-1b"})
    h = items(v)["Building height"]
    assert h["status"] == present.REVIEW and h["reason"] == present.ROOF_NOT_FLAT


# ---- C8: what was measured, and what wasn't ----------------------------------------------------------------------

def test_each_item_says_what_was_measured_and_objects_left_out_need_review(surveyed):
    r = check(MODEL, surveyed, extras={"scope": {"groups": 1, "solids": 3, "layer": "Gordium::Massing"},
                                       "not_included": ["a", "b"]})
    i = items(r["view"])
    assert i["Front yard"]["detail"]["scope"].startswith("Measured: 1 group, 3 solids on Gordium::Massing · footprint")
    left = i["Objects on the lot not included"]
    assert left["status"] == present.REVIEW and left["objects"] == ["a", "b"] and "Add to check" in left["reason"]
    assert "review" in r["view"]["summary"]


# ---- C9: never rounded toward compliance -------------------------------------------------------------------------

def test_values_are_never_rounded_toward_compliance():
    assert present.feet_inches(22.5) == "22'-6\""
    assert present.value_text(24.999, "ft", "≥", True) == "24'-11 7/8\""     # a minimum: proposed rounds down
    assert present.value_text(35.001, "ft", "≤", True) == "35'-0 1/8\""      # a maximum: proposed rounds up
    assert present.margin_text(0.04, "ft") == "+0\"" .replace("+0\"", "+0'-0 3/8\"")
    assert present.margin_text(-0.001, "ft") == "at limit"
    assert present.margin_text(-0.02, "ft") == "−0'-0 1/4\""                # a shortfall is never shown smaller


def test_coverage_near_the_limit_gets_one_more_decimal(surveyed):
    r = check(MODEL, {**surveyed, "lot_surveyed": True})
    cov = items(r["view"])["Lot coverage"]
    assert cov["proposed"] == "28.3%" and cov["margin"].startswith("−")


# ---- C10, C11: plain words for the user --------------------------------------------------------------------------

def test_no_internal_phrasing_reaches_the_panel(tax_map):
    text = str(tax_map["view"])
    assert "for the architects" not in text and "(lot_depth)" not in text


# ---- E: citations, links, quotes ----------------------------------------------------------------------------------

def test_citations_are_written_the_way_an_examiner_writes_them(tax_map):
    rear = items(tax_map["view"])["Rear yard"]["detail"]
    assert "§325-8, District Regulations Chart, R-1b, Rear yard column, note 16" in rear["citation"]
    assert "§325-8A, p.25" in rear["citation"]


def test_no_two_sections_share_a_link(tax_map):
    seen = {}
    for i in tax_map["view"]["items"]:
        for c in i["detail"].get("cited") or []:
            seen.setdefault(c["link"], set()).add(c["citation"])
    assert all(len(c) == 1 for c in seen.values()), {u: c for u, c in seen.items() if len(c) > 1}


def test_details_quote_the_chart_cells_verbatim(tax_map):
    i = items(tax_map["view"])
    for name in ("Rear yard", "Front yard", "Lot coverage", "Building height"):
        assert any(q["text"] for q in i[name]["detail"]["quotes"]), name
    assert any("But not less than 20 ft" in q["text"] for q in i["Rear yard"]["detail"]["quotes"])


# ---- D: groups, header -------------------------------------------------------------------------------------------

def test_groups_come_in_order_and_include_what_isnt_checked(tax_map):
    keys = [g["key"] for g in tax_map["view"]["groups"]]
    assert keys == sorted(keys, key=["fails", "review", "complies", "not_checked", "not_covered"].index)
    names = [i["name"] for i in tax_map["view"]["items"]]
    assert any(n.startswith("Overlays") for n in names) and any("§325-19C" in n for n in names)


def test_the_header_names_the_code_edition_the_draft_and_the_sources(tax_map):
    h = tax_map["view"]["header"]
    assert h["code"].startswith("Ch. 325 as amended through Ord. No. 2026-02")
    assert "Draft rulebook" in h["draft"] and "tax map" in h["lot"] and "Pick survey lot lines…" in h["actions"]


def test_side_yards_are_two_rows_west_and_east(tax_map):
    names = [i["name"] for i in tax_map["view"]["items"]]
    assert "Side yard, West" in names and "Side yard, East" in names


# ---- G: the notice ------------------------------------------------------------------------------------------------

def test_the_notice_is_one_line_for_newly_failing_items_and_none_on_the_first_check():
    a = [{"id": "x", "name": "Rear yard", "status": present.FAILS, "proposed": "20'-0\"", "required": "22'-6\"",
          "margin": "−2'-6\""}]
    now, text = present.notice(None, a)
    assert text is None
    _, text = present.notice({"x": present.COMPLIES}, a)
    assert text == "Rear yard no longer complies · 20'-0\" proposed · 22'-6\" required · −2'-6\""
    b = a + [{"id": "y", "name": "Lot coverage", "status": present.FAILS, "proposed": "", "required": "", "margin": ""}]
    _, text = present.notice({"x": present.COMPLIES, "y": present.COMPLIES}, b)
    assert text == "2 items no longer comply: Rear yard, Lot coverage"
    _, text = present.notice({"x": present.FAILS}, a)                       # already failing: no notice
    assert text is None


# ---- I: the report says what the panel says ------------------------------------------------------------------------

def test_the_report_never_shows_pass_for_a_rule_the_panel_says_needs_review(surveyed, tmp_path):
    report = tmp_path / "r.xlsx"
    result = check(MODEL, {**surveyed, "lot_surveyed": False}, report)
    out = openpyxl.load_workbook(report)["Output"]
    header = [c.value for c in out[2]]
    rid, err = header.index("Rule id"), header.index("Error")
    errors = {row[rid]: row[err] for row in out.iter_rows(min_row=3, values_only=True) if row[rid]}
    assert errors["R-1b.side_yards"] == "NEEDS REVIEW"                       # the panel's side yards need review
    check_tab = openpyxl.load_workbook(report)["Check"]
    text = " ".join(str(c.value) for row in check_tab.iter_rows() for c in row if c.value)
    assert "Draft rulebook" in text and "tax map" in text and "Overlays" in text and "§325-8" in text


# ---- J: symbols and words ------------------------------------------------------------------------------------------

def test_every_status_has_its_own_shape_and_the_codes_words(tax_map):
    assert len(set(present.MARK.values())) == 4 and present.SETUP_MARK not in present.MARK.values()
    names = {i["name"] for i in tax_map["view"]["items"]}
    assert {"Front yard", "Rear yard", "Lot coverage", "Building height", "Stories"} <= names
    assert not any(re.search(r"\bsetback\b", n, re.I) for n in names)
