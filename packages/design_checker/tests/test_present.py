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
    # +2'-6" is less than the tax map can take: 2'-0" nearer the rear line, and 1'-0" more required from a lot depth
    # 4'-0" more (each side lot line 2'-0" longer, Ben 2026-10-21)
    assert tm["Rear yard"]["status"] == present.REVIEW and "tax map" in tm["Rear yard"]["reason"]
    assert tm["Lot width"]["status"] == present.COMPLIES
    sv = items(check(MODEL, surveyed)["view"])
    assert sv["Side yard, West"]["status"] == present.COMPLIES      # a survey: no tolerance


def test_complies_only_when_the_checker_passed_or_it_holds_at_the_tax_map_worst_case(tax_map):
    """The one way a row the checker left NEEDS REVIEW reads complies: it waits only on the survey, and it holds
    at both ends of the tax-map tolerance (spec C2). Nothing else is ever made less cautious."""
    rows = {r["Rule id"]: r for r in tax_map["rows"]}
    for i in tax_map["view"]["items"]:
        if i["rule"] and i["status"] == present.COMPLIES and rows[i["rule"]]["Error"] != "PASS":
            assert rows[i["rule"]]["Provisional"] == present.SURVEY_ONLY, i["name"]
            assert "worst case" in i["reason"], i["name"]
    area = items(tax_map["view"])["Lot area"]                      # the 73 × 90 lot of 106 Ithaca Rd
    assert area["status"] == present.REVIEW and "at worst 5,934 sf against 6,000 sf" in area["reason"]  # 69 × 86


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
    assert present.margin_text(-0.001, "ft") == "−0'-0 1/8\""        # a shortfall is never "at limit"
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
          "margin": "−2'-6\"", "delta": "−2'-6\" short"}]                       # settle's words (the only writer)
    now, text = present.notice(None, a)
    assert text is None
    _, text = present.notice({"x": present.COMPLIES}, a)
    assert text == "Rear yard no longer complies · 20'-0\" proposed · 22'-6\" required · −2'-6\" short"
    b = a + [{"id": "y", "name": "Lot coverage", "status": present.FAILS, "proposed": "", "required": "", "margin": ""}]
    _, text = present.notice({"x": present.COMPLIES, "y": present.COMPLIES}, b)
    assert text == "2 items no longer comply: Rear yard; Lot coverage"     # "; ": names have commas
    c = a + [{"id": "z", "name": "Side yard, East", "status": present.FAILS, "proposed": "", "required": "", "margin": ""}]
    _, text = present.notice({"x": present.COMPLIES, "z": present.COMPLIES}, c)
    assert text == "2 items no longer comply: Rear yard; Side yard, East"
    _, text = present.notice({"x": present.FAILS}, a)                       # already failing: no notice
    assert text is None


# ---- I: the report says what the panel says ------------------------------------------------------------------------

def test_the_report_never_shows_pass_for_a_rule_the_panel_says_needs_review(surveyed, tmp_path):
    report = tmp_path / "r.xlsx"
    result = check(MODEL, {**surveyed, "lot_surveyed": False}, report)
    out = openpyxl.load_workbook(report)["Output"]
    header = [c.value for c in out[2]]
    req, err = header.index("Requirement"), header.index("Error")
    errors = {row[req]: row[err] for row in out.iter_rows(min_row=3, values_only=True) if row[req]}
    side = next(k for k in errors if k.startswith("Side yards"))
    assert errors[side] == "NEEDS REVIEW"                                     # the panel's side yards need review
    check_tab = openpyxl.load_workbook(report)["Check"]
    text = " ".join(str(c.value) for row in check_tab.iter_rows() for c in row if c.value)
    assert "Draft rulebook" in text and "tax map" in text and "Overlays" in text and "§325-8" in text


# ---- J: symbols and words ------------------------------------------------------------------------------------------

def test_every_status_has_its_own_shape_and_the_codes_words(tax_map):
    assert len(set(present.MARK.values())) == 4 and present.SETUP_MARK not in present.MARK.values()
    names = {i["name"] for i in tax_map["view"]["items"]}
    assert {"Front yard", "Rear yard", "Lot coverage", "Building height", "Stories"} <= names
    assert not any(re.search(r"\bsetback\b", n, re.I) for n in names)


# ---- F: what the viewport draws in plan: red only where the building breaks a limit -----------------------------

CITY = "regulations/jurisdictions/new_york/ithaca_city"


def _plot(*buildings, lot_=RECT):
    return {"units": "ft", "lot": lot_, "buildings": list(buildings), "problems": []}


def test_red_is_only_the_strip_inside_a_failing_side_yard_even_without_a_grade():
    from design_checker.check import check_site
    facts = {**FACTS, "jurisdiction": CITY, "ground_is_flat": None, "grade_elevation": None}
    r = check_site(_plot(box(6, 25, 35, 65)), facts)               # west wall 6 ft from the line: needs 10 ft
    assert items(r["view"])["Side yard, West"]["status"] == present.FAILS
    assert r["envelope"]["outline"] and r["envelope"]["top"] is None   # the plan is drawn, never a height plane
    (strip,) = r["plan"]["encroach"]
    xs = [p[0] for p in strip["outline"]]
    assert strip["why"] == "yard" and min(xs) == pytest.approx(6) and max(xs) == pytest.approx(10, abs=0.01)
    ok = check_site(_plot(box(10, 25, 35, 65)), facts)
    assert ok["plan"]["encroach"] == []                          # nothing breaks a yard: no red at all


def test_the_red_strip_has_no_hairline_edges_and_stands_on_the_building_without_a_grade():
    import math
    from design_checker.check import check_site
    facts = {**FACTS, "jurisdiction": CITY, "ground_is_flat": None, "grade_elevation": None}
    (strip,) = check_site(_plot(box(6, 25, 35, 65, 412, 442)), facts)["plan"]["encroach"]
    ring = strip["outline"]
    assert min(math.dist(ring[i - 1], ring[i]) for i in range(len(ring))) > 0.001    # Rhino extrudes it
    assert strip["base"] == pytest.approx(412) and strip["top"] == pytest.approx(442)


def test_red_above_the_height_limit_is_only_the_part_above_it():
    from design_checker.check import check_site
    r = check_site(_plot(box(10, 25, 35, 65, 0, 38)), {**FACTS, "jurisdiction": CITY, "stories": 3})
    assert items(r["view"])["Building height"]["status"] == present.FAILS
    (top,) = r["plan"]["encroach"]
    assert top["why"] == "height" and top["base"] == pytest.approx(35) and top["top"] == pytest.approx(38)


def _regions(r):
    """Each coloured region: (status, its x from, x to, area in sf)."""
    from shapely.geometry import Polygon
    return sorted(((e["status"], round(min(p[0] for p in e["outline"]), 2), round(max(p[0] for p in e["outline"]), 2),
                    round(Polygon(e["outline"]).area, 1)) for e in r["plan"]["encroach"]), key=lambda t: t[1])


def test_amber_is_the_part_of_the_building_in_a_tax_map_yards_caution_zone():
    """West wall 11 ft from the line, the side yard needs 10 (front 30 ft back, rear 35: well clear): on a survey
    it complies (no colour); on the tax map (±2 ft) it needs review, and amber is exactly the part within 2 ft of
    the yard line: x 11 to 12, the house's 35 ft depth (35 sf). Never red."""
    from design_checker.check import check_site
    house = box(11, 30, 35, 65)
    surveyed = check_site(_plot(house), {**FACTS, "jurisdiction": CITY})
    assert items(surveyed["view"])["Side yard, West"]["status"] == present.COMPLIES and _regions(surveyed) == []
    tax = check_site(_plot(house), {**FACTS, "jurisdiction": CITY, "lot_surveyed": False})
    assert items(tax["view"])["Side yard, West"]["status"] == present.REVIEW
    assert items(tax["view"])["Front yard"]["status"] == present.COMPLIES
    assert _regions(tax) == [(present.REVIEW, 11, pytest.approx(12, abs=0.02), pytest.approx(35, abs=0.8))]


def test_amber_follows_every_yard_in_doubt():
    """The same house with its front wall at exactly 25 ft (the requirement): the front yard needs review too, so
    amber is the L of both caution strips: x 11 to 12 the full 40 ft depth (40 sf) plus y 25 to 27 the remaining
    23 ft of width (46 sf): 86 sf."""
    from design_checker.check import check_site
    tax = check_site(_plot(box(11, 25, 35, 65)), {**FACTS, "jurisdiction": CITY, "lot_surveyed": False})
    assert items(tax["view"])["Front yard"]["status"] == present.REVIEW
    assert _regions(tax) == [(present.REVIEW, 11, 35, pytest.approx(86, abs=1.5))]


def test_the_delta_on_the_tax_map_says_what_holds_however_the_lines_lie():
    """Architect's review (2026-10-21): "−3'-0" short" while red was only 1 ft. Worked by hand (lot 50 x 100, side
    yards need 10 ft, the tax map ±2 ft on each lot length the rule reads):
    - West wall 7 ft from the line: the yard is really 5 to 9 ft, so 1 to 5 ft short: "at least 1'-0" short"
      (the red part), never "−3'-0" short";
    - 11 ft: really 9 to 13: "up to 1'-0" short" (amber, no red); 16 ft: really 14 to 18: "at least 4'-0" to spare";
    - the same walls on a survey: the margin itself."""
    from design_checker.check import check_site
    tax = {**FACTS, "jurisdiction": CITY, "lot_surveyed": False}
    words = {x: items(check_site(_plot(box(x, 30, 35, 65)), tax)["view"])["Side yard, West"] for x in (7, 11, 16)}
    assert [(words[x]["delta"], words[x]["approx"]) for x in (7, 11, 16)] == [
        ("at least 1'-0\" short", True), ("up to 1'-0\" short", True), ("at least 4'-0\" to spare", True)]
    assert words[7]["margin"] == "−3'-0\"" and words[7]["status"] == present.FAILS     # as drawn, unchanged
    assert "as drawn" in words[7]["detail"]["line"] and "at least 1'-0\" short" in words[7]["detail"]["line"]
    survey = items(check_site(_plot(box(7, 30, 35, 65)), {**FACTS, "jurisdiction": CITY})["view"])["Side yard, West"]
    assert (survey["delta"], survey["approx"]) == ("−3'-0\" short", False)
    # the notice and the report say the same words as the panel
    before = {i["id"]: i["status"] for i in check_site(_plot(box(16, 30, 35, 65)), tax)["view"]["items"]}
    now = check_site(_plot(box(7, 30, 35, 65)), tax)["view"]["items"]
    assert present.notice(before, now)[1].endswith("· at least 1'-0\" short")
    # round 2: settle is the ONLY writer of the Delta; nothing falls back to the as-drawn margin's words
    for path in ("packages/design_checker/design_checker/check.py", "packages/design_checker/design_checker/present.py",
                 "apps/rhino_plugin/gordium_ui.py"):
        assert "delta_text" not in (REPO / path).read_text(encoding="utf-8"), path


def test_delta_words_never_overstate():
    C, R, F = present.COMPLIES, present.REVIEW, present.FAILS
    assert present.delta_words(F, (-5.0, -1.0), "ft", True) == "at least 1'-0\" short"
    assert present.delta_words(F, (-5.0, -1.0 - 1 / 200), "ft", True) == "at least 1'-0\" short"   # rounded down
    assert present.delta_words(R, (-3.25, 1.75), "ft", True) == "up to 3'-3\" short"
    assert present.delta_words(R, (-3.25 + 1 / 200, 1.75), "ft", True) == "up to 3'-3\" short"    # rounded up
    assert present.delta_words(C, (0.0, 4.0), "ft", True) == "at the limit at worst"
    assert present.delta_words(C, (5.0, 9.0), "ft", True) == "at least 5'-0\" to spare"
    assert present.delta_words(C, (7.0, 7.0), "ft", False) == "+7'-0\" to spare"            # one reading: the margin
    assert present.delta_words(F, (-1.25, -1.25), "ft", False) == "−1'-3\" short"
    assert present.delta_words(C, None, "ft", False) == ""
    # never kinder than the status: room on a row that needs review is "if confirmed", never "to spare"
    assert present.delta_words(R, (7.0, 7.0), "ft", False) == "+7'-0\" if confirmed"
    assert present.delta_words(R, (5.0, 9.0), "ft", True) == "at least 5'-0\" if confirmed"
    # round 2: the certain words ("at least … short") only on a row that fails; one in review says to see why
    assert present.delta_words(R, (-5.0, -1.0), "ft", True) == "at least 1'-0\" short; see why"
    assert present.delta_words(R, (-1.0, -1.0), "ft", False) == "−1'-0\" short; see why"
    assert "to spare" not in present.delta_words(F, (1.0, 2.0), "ft", False)
    # every unit: lot area in sf, coverage in % (round 1: "+570 sf to spare" on a lot area that needs review)
    assert present.delta_words(R, (-66.2, 570.4), "sf", True) == "up to 67 sf short"
    assert present.delta_words(F, (-1000.0, -384.6), "sf", True) == "at least 384 sf short"
    assert present.delta_words(C, (0.937, 6.2), "%", True) == "at least 0.93% to spare"
    assert present.delta_words(F, (-6.2, -0.004), "%", True) == "less than 0.01% short"


def test_on_the_tax_map_red_is_over_under_every_reading_and_amber_is_the_rest_of_the_doubt():
    """West wall 6 ft from the drawn line, the side yard needs 10, the line is ±2 ft: the yard line is really
    somewhere from x 8 to 12. Red is over under every reading (x 6 to 8: 2 x 35 = 70 sf); amber is the doubt
    (x 8 to 12: 4 x 35 = 140 sf). They never overlap. On a survey the same wall is red 6 to 10, no amber."""
    from design_checker.check import check_site
    house = box(6, 30, 35, 65)
    r = check_site(_plot(house), {**FACTS, "jurisdiction": CITY, "lot_surveyed": False})
    assert items(r["view"])["Side yard, West"]["status"] == present.FAILS
    assert _regions(r) == [(present.FAILS, 6, pytest.approx(8, abs=0.02), pytest.approx(70, abs=1.5)),
                           (present.REVIEW, pytest.approx(8, abs=0.02), pytest.approx(12, abs=0.02),
                            pytest.approx(140, abs=1.5))]
    survey = check_site(_plot(house), {**FACTS, "jurisdiction": CITY})
    assert _regions(survey) == [(present.FAILS, 6, pytest.approx(10, abs=0.02), pytest.approx(140, abs=1.5))]


def test_a_yard_in_red_or_amber_says_what_the_colours_mean_in_its_detail():
    from design_checker.check import check_site
    tax = {**FACTS, "jurisdiction": CITY, "lot_surveyed": False}
    r = items(check_site(_plot(box(6, 30, 35, 65)), tax)["view"])
    assert r["Side yard, West"]["detail"]["colours"] == present.COLOURS_NOTE      # fails: red and amber
    assert "certain" in present.COLOURS_NOTE and "2'-0\"" in present.COLOURS_NOTE
    assert r["Side yard, East"]["detail"]["colours"] is None                       # complies: no colour
    review = items(check_site(_plot(box(11, 30, 35, 65)), tax)["view"])
    assert review["Side yard, West"]["detail"]["colours"] == present.COLOURS_NOTE  # needs review: amber
    survey = items(check_site(_plot(box(6, 30, 35, 65)), {**FACTS, "jurisdiction": CITY})["view"])
    assert survey["Side yard, West"]["detail"]["colours"] is None                  # a survey: red only, nothing to say


def test_a_height_that_needs_review_is_amber_above_the_limit():
    from design_checker.check import plan
    site = _plot(box(10, 25, 35, 65, 0, 38))
    env = {"outline": [[0, 0], [50, 0], [50, 100], [0, 100]], "top": 35, "base": 0}
    for status in (present.REVIEW, present.FAILS):
        (top,) = plan(site, env, {"items": [{"measure": "building_height", "status": status}]}, {})["encroach"]
        assert (top["why"], top["status"], top["base"], top["top"]) == ("height", status, 35, 38)
    assert plan(site, env, {"items": [{"measure": "building_height", "status": present.COMPLIES}]}, {})["encroach"] == []


def test_the_colour_comes_from_the_result_only():
    """rhino_logic.highlight: the one place a result becomes a colour (the conduit draws only what it names)."""
    sys.path.insert(0, str(REPO / "packages/design_checker/design_checker"))
    import rhino_logic
    assert [rhino_logic.highlight(s) for s in (present.FAILS, present.REVIEW, present.COMPLIES, "not_checked", None)] \
        == ["red", "amber", None, None, None]
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    scene = src.split("def draw_scene(", 1)[1].split("\ndef ", 1)[0]
    assert "name = logic.highlight(status)" in scene and "colour = ui.HIGHLIGHT[name]" in scene
    # drawn after the translucent envelope, so its blue never tints them (seen muddy in Rhino, 2026-10-21)
    assert scene.index("o.envelope, Rhino.Display.DisplayMaterial") < scene.index("ui.HIGHLIGHT[name]")
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert "FromArgb(215, 38, 61)" in ui and "FromArgb(242, 169, 0)" in ui      # #D7263D, #F2A900


def test_the_plan_labels_each_lot_edge_and_each_measured_yard():
    from design_checker.check import check_site
    r = check_site(_plot(box(10, 25, 35, 65)), {**FACTS, "jurisdiction": CITY})
    assert sorted(e["length"] for e in r["plan"]["edges"]) == ["100'-0\"", "100'-0\"", "50'-0\"", "50'-0\""]
    labels = [y["label"] for y in r["plan"]["yards"]]
    assert all(y["points"] for y in r["plan"]["yards"])
    for name in ("Front yard", "Side yard, West", "Side yard, East", "Rear yard"):    # side yards too
        assert any(lb[2:].startswith(name + " ") for lb in labels), (name, labels)


def test_the_envelope_height_plane_comes_from_spot_grades_and_never_from_existing_ground():
    from design_checker.check import check_site
    house = box(10, 25, 35, 65, 2, 30)
    spots = [[22, 24, 1], [22, 66, 3], [9, 45, 2], [36, 45, 2]]       # one per wall: grade plane 2
    base = {**FACTS, "jurisdiction": CITY, "ground_is_flat": None, "grade_elevation": None, "grade_points": spots}
    r = check_site(_plot(house), base)
    assert r["envelope"]["base"] == pytest.approx(2) and r["envelope"]["top"] == pytest.approx(37)
    assert check_site(_plot(house), {**base, "grade_is": "existing"})["envelope"]["top"] is None


# ---- E1: a cited chart cell is quoted as exactly that cell --------------------------------------------------

def _expected_cell_text(cell):
    section = re.sub(r"\s*\[fn[\d,]+\]", "", cell.get("section") or "")
    row = re.sub(r"\s*\[fn[\d,]+\]", "", cell["row"])
    return f"{section} · {row} · {cell['column']}: {cell['value']}"


def test_every_cited_chart_cell_is_quoted_as_exactly_its_own_cell():
    """Every cell source in every rulebook (hand-made and drafted): the panel's quote is that cell, found by the
    same key the rule checks use, never a cell whose row merely starts the same way in another section (a
    lot-width rule was once quoted as the lot-size cell's 10,000 sf)."""
    import yaml
    from rule_format.rulebook import Context, _cell
    j = REPO / "regulations/jurisdictions/new_york/ithaca_city"
    ctx, documents = Context.for_jurisdiction(j), present._documents(j)
    seen = 0
    for path in sorted((j / "5_zoning_rules").rglob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for rule in (data or {}).get("rules") or []:
            for s in rule.get("sources") or []:
                if not isinstance(s.get("cell"), dict) or s.get("lines"):
                    continue
                cell = _cell(s, ctx)
                q = present._quote(s, j, documents, s["cell"].get("column", ""), lambda src: "")
                want = _expected_cell_text(cell) if cell and str(cell.get("value") or "").strip() else present._cell_words(s)
                assert q["text"] == want, (path.name, rule["id"], s["cell"], q["text"])
                seen += 1
    assert seen > 0


def test_two_sections_with_the_same_row_are_never_mixed_up(monkeypatch, tmp_path):
    """The chart's Minimum Lot Size and Minimum Lot Width sections both have a "One-family dwelling, detached"
    row: a source citing the width cell is quoted as the width cell, and a cell the chart doesn't have is quoted
    as its own words, never as a near match."""
    cells = ({"file": "c.pdf", "page": 3, "section": "Minimum Lot Size", "row": "One-family dwelling, detached",
              "column": "R-1A", "value": "10,000 sf", "row_lines": [10]},
             {"file": "c.pdf", "page": 3, "section": "Minimum Lot Width", "row": "One-family dwelling, detached",
              "column": "R-1A", "value": "75 ft", "row_lines": [20]})
    monkeypatch.setattr(present, "_chart_cells", lambda j: cells)
    documents = {"c.pdf": {"title": "Zoning charts"}}

    def quote(section, row):
        source = {"file": "c.pdf", "page": 3, "cell": {"section": section, "row": row, "column": "R-1A"}}
        return present._quote(source, tmp_path, documents, "R-1A", lambda s: "")["text"]

    assert quote("Minimum Lot Width", "One-family dwelling, detached") == \
        "Minimum Lot Width · One-family dwelling, detached · R-1A: 75 ft"
    assert quote("Minimum Lot Width", "One-family dwelling, detached, by conversion") == \
        "Minimum Lot Width · One-family dwelling, detached, by conversion · R-1A"


def test_the_tax_map_worst_case_moves_every_lot_line_2_ft_the_unlucky_way():
    """Ben, 2026-10-21 (stress test F2): one rule for every lot-dependent item, worked by hand on 106 Ithaca Rd's
    73 x 90 lot: lot area at worst 69 x 86 = 5,934 sf (was 71 x 88 = 6,248, 1 ft per line), a lot width or depth
    off by 4 ft (two lines), a yard by 2 ft (one line). One definition, used by measurement, checker and generator."""
    from shapely.geometry import Polygon
    from model_measurement.measure import TAX_MAP_SLACK, tax_map_lot_area
    area = tax_map_lot_area(Polygon([(0, 0), (73, 0), (73, 90), (0, 90)]))
    assert (area["low"], area["high"]) == (69 * 86, 77 * 94) == (5934, 7238)
    assert TAX_MAP_SLACK["lot_width"] == TAX_MAP_SLACK["lot_depth"] == 4.0 and TAX_MAP_SLACK["rear_yard"] == 2.0
    from design_checker import reading_set
    assert reading_set.TAX_MAP_SLACK is TAX_MAP_SLACK                               # the checker reads the same one
    tax = {"lot_area": {"tolerance": area}}                  # a tax-map lot (its area's tolerance), not surveyed
    worst = present._worst_case("lot_width >= 70", {"lot_width": 73.0}, {"lot_width"}, tax, {"lot_surveyed": False})
    assert worst == {"lot_width": 69.0}                                             # 73 − 4: fails 70 at worst


def test_at_the_limit_and_complies_never_disagree():
    """PR #20 review: margins were worked out in floats (26.4 − 0.2 × 132 = −3.6e-15), so a rear yard exactly at
    its limit could show "−0'-0 1/8"" beside "complies". The margin now comes from formula.margin, the same exact
    arithmetic and tolerance as the comparison."""
    import ast as _ast
    node = _ast.parse("rear_yard >= 0.2 * lot_depth", mode="eval").body
    values = {"rear_yard": 26.4, "lot_depth": 132}
    numbers = present._numbers(node, values, {"rear_yard": {"unit": "ft"}}, "Rear yard")
    assert numbers[2] == 0.0 and present._display(*numbers)[2] == "at limit"
    assert present.formula.evaluate("rear_yard >= 0.2 * lot_depth", values, present.MEASURE_KINDS) is True
    noisy = {"rear_yard": 26.399999999999995, "lot_depth": 132}          # the geometry's float noise: complies
    assert present.formula.evaluate("rear_yard >= 0.2 * lot_depth", noisy, present.MEASURE_KINDS) is True
    assert present._display(*present._numbers(node, noisy, {"rear_yard": {"unit": "ft"}}, "Rear yard"))[2] == "at limit"
    short = present._numbers(node, {"rear_yard": 26.39, "lot_depth": 132}, {"rear_yard": {"unit": "ft"}}, "Rear yard")
    assert short[2] < 0 and present._display(*short)[2].startswith("−")
    cov = _ast.parse("building_area <= 0.35 * lot_area", mode="eval").body
    pct = present._numbers(cov, {"building_area": 1750.7, "lot_area": 5002}, {"building_area": {"unit": "sf"}}, "x")
    assert present._display(*pct)[2] == "at limit"


def test_lot_area_and_coverage_deltas_use_the_tax_map_lot_area_like_their_verdict(tax_map):
    """Round 1: a Lot area that needs review read "+570 sf to spare". Its Delta and coverage's are taken over the
    lot area's own tax-map range (low to high), the same readings as the verdict."""
    r = tax_map
    v = items(r["view"])
    tol = r["measurements"]["lot_area"]["tolerance"]
    area = v["Lot area"]
    assert area["status"] == present.REVIEW and area["approx"]
    assert area["delta"] == "up to " + present._area(6000 - tol["low"], "up") + " short"     # never "to spare"
    cov = v["Lot coverage"]
    assert cov["approx"] and cov["status"] == present.FAILS and cov["delta"].startswith("at least ")
    assert cov["delta"] != cov["margin"] + " short"                   # the certain shortfall, not the as-drawn one


def test_the_height_row_is_never_marked_tax_map_approximate(tax_map):
    """Round 1: the height's own comparison reads no lot length (only its bonus clause does): its Delta is its
    margin, and it is not "(approx.)"."""
    r = tax_map
    h = items(r["view"])["Building height"]
    assert h["approx"] is False and h["delta"] in ("at limit", h["margin"] + " to spare", h["margin"] + " short")
    assert "tax map" not in h["detail"]["line"]


def test_red_and_amber_agree_with_the_rear_yards_own_readings():
    """Round 1: red and amber were the footprint against all yards grown by a flat 2'-0", while the rear verdict
    also moves the lot depth 4'-0" (its minimum by 1'-0"). Each yard's colours are now its own readings'."""
    from design_checker.check import check_site
    tax = {**FACTS, "jurisdiction": CITY, "lot_surveyed": False}
    r = check_site(_plot(box(10, 30, 35, 78.5)), tax)                 # rear wall 3'-6" over the drawn 25'-0"
    rear = items(r["view"])["Rear yard"]
    assert (rear["status"], rear["delta"]) == (present.FAILS, "at least 0'-6\" short")
    red = [g for g in r["plan"]["encroach"] if g["status"] == present.FAILS]
    (strip,) = red
    ys = [p[1] for p in strip["outline"]]
    assert min(ys) == pytest.approx(78.0, abs=0.01) and max(ys) == pytest.approx(78.5, abs=0.01)   # 0'-6" deep
    r = check_site(_plot(box(10, 30, 35, 72.5)), tax)                 # 2'-6" clear: needs review, "up to 0'-6" short"
    rear = items(r["view"])["Rear yard"]
    assert (rear["status"], rear["delta"], rear["colour"]) == (present.REVIEW, "up to 0'-6\" short", "amber")
    amber = [p for g in r["plan"]["encroach"] if g["status"] == present.REVIEW for p in g["outline"]]
    assert max(p[1] for p in amber) == pytest.approx(72.5, abs=0.01)      # the rear doubt (69.5 to 72.5 deep) shows


def test_red_is_only_for_a_yard_that_fails_never_one_that_needs_review():
    """Round 1: whenever any yard failed, red was the footprint over every yard, so a yard that only needs review
    was painted red. West wall 4 ft over (fails), rear wall 2'-6" over (needs review)."""
    from design_checker.check import check_site
    r = check_site(_plot(box(6, 30, 35, 77.5)), {**FACTS, "jurisdiction": CITY, "lot_surveyed": False})
    v = items(r["view"])
    assert v["Side yard, West"]["status"] == present.FAILS and v["Rear yard"]["status"] == present.REVIEW
    from shapely.geometry import Polygon
    red = [Polygon(g["outline"]) for g in r["plan"]["encroach"] if g["status"] == present.FAILS]
    xs = [p[0] for g in red for p in g.exterior.coords]
    assert max(xs) == pytest.approx(8, abs=0.01) and min(xs) == pytest.approx(6)
    # only the side yard's certain strip, x 6 to 8 the house's whole depth (2 x 47.5 = 95 sf): never the rear strip
    # (y 77 to 77.5 across the house) of a yard that only needs review
    assert sum(g.area for g in red) == pytest.approx(95, abs=0.5)


def _shown_agrees(i):
    """The invariants between a row's status, the Delta the architect sees (settle's words, the only ones) and its
    colour: "to spare" only on a row that complies; the certain words ("at least … short", "less than … short", a
    survey's "−… short") only on a row that fails, and on a yard always with red; a row that complies never says
    "short"; red only on a row that fails."""
    d, st = i.get("delta") or "", i["status"]
    certain = d.endswith(" short") and d.startswith(("at least ", "less than ", "−"))
    assert "to spare" not in d or st == present.COMPLIES, (i["name"], st, d)
    assert not certain or st == present.FAILS, (i["name"], st, d)
    assert not (certain and i["measure"] in present.YARD_MEASURES) or i["colour"] == "red", (i["name"], i["colour"], d)
    assert st != present.COMPLIES or "short" not in d, (i["name"], st, d)
    assert i["colour"] != "red" or st == present.FAILS, (i["name"], st)
    assert i["colour"] == "none" or i["measure"] in present.YARD_MEASURES, i["name"]


def _oracle(x0, y0, x1, y1, slack):
    """By hand, on the plain 50 x 100 lot (street along y = 0): each yard's verdict over every reading (its line off
    by `slack` either way, the lot depth by twice that), and the strip of the house short under every reading."""
    from shapely.geometry import box as rect
    rear_low, rear_high = 0.25 * (100 - 2 * slack), 0.25 * (100 + 2 * slack)     # max(min(.25 d, 50), 20): 24..26
    yards = {"Front yard": (y0, 25, 25, rect(-1, -1, 51, 25 - slack)),
             "Side yard, West": (x0, 10, 10, rect(-1, -1, 10 - slack, 101)),
             "Side yard, East": (50 - x1, 10, 10, rect(40 + slack, -1, 51, 101)),
             "Rear yard": (100 - y1, rear_low, rear_high, rect(-1, 100 - (rear_low - slack), 51, 101))}
    out = {}
    for name, (v, need_low, need_high, strip) in yards.items():
        status = (present.COMPLIES if v - slack >= need_high else present.FAILS if v + slack < need_low
                  else present.REVIEW)
        out[name] = (status, strip)
    return out


def test_verdict_delta_and_colour_never_disagree_for_any_design():
    """Review rounds 1 and 2: random houses on (a) the plain 50 x 100 lot, checked against a hand oracle: each yard's
    verdict and the red area (the footprint inside the failing yards' certain strips, holes included: a house
    failing all four yards is a ring of red round a complying core); (b) the real 106 Ithaca Rd lot, whose back
    lines are an open question (side or rear: real readings); (c) a corner lot. On the tax map and on a survey,
    every row's shown Delta, status and colour agree (_shown_agrees)."""
    import random
    from shapely.geometry import Polygon, box as rect
    from shapely.ops import unary_union
    from design_checker.check import check_site, sample_site
    from test_measure import lot as lot_of
    rnd = random.Random(15)
    plain = [(0, 0), (50, 0), (50, 100), (0, 100)]
    for k in range(60):
        x0, y0 = rnd.uniform(1, 18), rnd.uniform(8, 40)
        x1, y1 = rnd.uniform(x0 + 8, 49), rnd.uniform(y0 + 10, 99)
        surveyed = k % 2 == 0
        r = check_site(_plot(box(x0, y0, x1, y1, 0, rnd.choice((30, 34.99, 35))), lot_=lot_of(plain)),
                       {**FACTS, "jurisdiction": CITY, "lot_surveyed": surveyed})
        rows = {i["name"]: i for i in r["view"]["items"]}
        for i in rows.values():
            if i.get("measure"):
                _shown_agrees(i)
        oracle = _oracle(x0, y0, x1, y1, 0.0 if surveyed else 2.0)
        for name, (status, _) in oracle.items():
            assert rows[name]["status"] == status, (k, name, rows[name]["status"], status, rows[name]["delta"])
        house = rect(x0, y0, x1, y1)
        want = house.intersection(unary_union([strip for st, strip in oracle.values() if st == present.FAILS] or [rect(0, 0, 0, 0)]))
        red = sum(Polygon(e["outline"]).area for e in r["plan"]["encroach"]
                  if e["why"] == "yard" and e["status"] == present.FAILS)
        assert abs(red - want.area) < 0.5, (k, red, want.area)
    # (b) the real 106 lot: its back lines are side or rear (an open question): real readings, grouped by lot reading
    sample = sample_site()
    ring, facts = sample["lot"], {**sample["facts"], "jurisdiction": sample["facts"]["jurisdiction"]}
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    open_seen = 0
    for k in range(40):
        x0, y0 = rnd.uniform(min(xs) + 1, 40), rnd.uniform(min(ys) + 5, 40)
        x1, y1 = rnd.uniform(x0 + 8, max(xs) - 1), rnd.uniform(y0 + 10, max(ys) - 2)
        r = check_site(_plot(box(x0, y0, x1, y1, 0, rnd.choice((30, 35))), lot_=lot_of(ring)),
                       {**facts, "lot_surveyed": k % 2 == 0})
        open_seen += any(m.get("value") is None and m.get("readings") for m in r["measurements"].values())
        for i in r["view"]["items"]:
            if i.get("measure"):
                _shown_agrees(i)
        reds = [i for i in r["view"]["items"] if i.get("colour") == "red"]
        assert not [e for e in r["plan"]["encroach"] if e["why"] == "yard" and e["status"] == present.FAILS] or reds
    assert open_seen >= 10                                  # the open question really was exercised
    # (c) a corner lot: the yards can't be read; nothing says "to spare" or the certain words unless it should
    for k in range(10):
        r = check_site(_plot(box(rnd.uniform(1, 15), rnd.uniform(5, 30), rnd.uniform(30, 49), rnd.uniform(60, 95),
                                 0, rnd.choice((30, 34, 37)))),
                       {**FACTS, "jurisdiction": CITY, "corner_lot": True, "lot_surveyed": k % 2 == 0})
        for i in r["view"]["items"]:
            if i.get("measure"):
                _shown_agrees(i)


def _never_above_the_checker(r):
    """Review round 3: the checker (check.row_verdict over the reading set) is the only place a row complies or
    fails; every panel item is its row's verdict (a side yard: its side's) or more cautious, never more
    favourable."""
    rows = {x["Rule id"]: x for x in r["rows"]}
    for i in r["view"]["items"]:
        row = rows.get(i.get("rule"))
        if row is None:
            continue
        verdict = (row.get("Sides") or {}).get(i.get("measure")) or row["Verdict"]
        assert present.RANK[i["status"]] <= present.RANK[verdict], (i["name"], i["status"], verdict, i["reason"])


def _sample106():
    from design_checker.check import sample_site
    from test_measure import lot as lot_of
    sample = sample_site()
    return lot_of(sample["lot"]), dict(sample["facts"])


def test_an_unmeasured_porch_touching_the_house_keeps_a_side_yard_in_review():
    """Review round 3 (P0): a side yard whose value is an open question was raised to complies after the left-out
    caution had run, so a porch touching the house (part of it for yards, §325-18A) no longer mattered."""
    from design_checker.check import check_site
    lot, facts = _sample106()
    r = check_site(_plot(box(10.2806, 24.0480, 39.2642, 73.2738, 0, 30), lot_=lot), {**facts, "lot_surveyed": True},
                   extras={"not_included": ["porch-1"], "touching": ["porch-1"]})
    side = items(r["view"])["Side yard, Northeast"]
    assert side["status"] == present.REVIEW, (side["status"], side["reason"])
    assert "touching" in side["reason"] or "depends on" in side["reason"]
    _never_above_the_checker(r)


def test_an_unknown_use_keeps_the_lot_area_in_review_with_its_reason():
    """Review round 3 (P1): with the use unknown the checker leaves the lot area needing review ("choose the use");
    the panel's survey step ignored applies_when and showed complies."""
    from design_checker.check import check_site
    lot, facts = _sample106()
    r = check_site(_plot(box(12, 30, 60, 80, 0, 30), lot_=lot), {**facts, "use": None, "lot_surveyed": False})
    area = next(i for i in r["view"]["items"] if i["rule"] == "R-1b.lot_area_one_family_detached")
    assert area["status"] == present.REVIEW and "choose the use" in area["reason"], (area["status"], area["reason"])
    _never_above_the_checker(r)


def test_a_side_yard_that_complies_only_under_every_reading_of_an_open_question_needs_review():
    """Review round 3 (P2): like every other row that passes under every reading of an open question, the side
    yard needs review and names the question; it never shows a green "complies" with no reason."""
    from design_checker.check import check_site
    lot, facts = _sample106()
    r = check_site(_plot(box(10.2806, 24.0480, 39.2642, 73.2738, 0, 30), lot_=lot), {**facts, "lot_surveyed": True})
    side = items(r["view"])["Side yard, Northeast"]
    assert side["status"] == present.REVIEW and (side["reason"] or "").startswith("Complies under every reading, but it depends on"), (
        side["status"], side["reason"])
    assert "if confirmed" in side["delta"] and "to spare" not in side["delta"]
    _never_above_the_checker(r)


def test_a_side_yard_says_only_its_own_verdicts_reason_never_the_pairs():
    """Review round 4: a side the checker passes inherited the pair row's needs-review reason (a green "complies"
    saying "depends on open questions"). Each side's reason comes from its own verdict: complies, none; needs
    review, its own open question; fails, its own words."""
    from design_checker.check import check_site
    lot, facts = _sample106()
    for surveyed in (True, False):
        r = check_site(_plot(box(14, 24.0480, 39.2642, 73.2738, 0, 30), lot_=lot), {**facts, "lot_surveyed": surveyed})
        rows = {x["Rule id"]: x for x in r["rows"]}
        sides = [i for i in r["view"]["items"] if i["name"].startswith("Side yard")]
        assert len(sides) == 2
        for i in sides:
            verdict = rows[i["rule"]]["Sides"][i["measure"]]
            if i["status"] == present.COMPLIES:
                assert not i["reason"], (surveyed, i["name"], i["reason"])
            if i["status"] == present.REVIEW and verdict == present.REVIEW:
                assert i["reason"] and "depends on" in i["reason"] or "tax map" in i["reason"], (surveyed, i["reason"])
        assert any(i["status"] == present.COMPLIES for i in sides) or not surveyed, [(i["name"], i["status"]) for i in sides]


def test_the_guard_only_lowers_it_never_undoes_the_panels_caution():
    """Round 3's guard caps a row at the checker's verdict; it never lifts a row the panel made more cautious. A
    complying house on a surveyed lot with an unmeasured porch touching it: the checker passes the yards (it
    measures only the house), the panel makes them need review (§325-18A), and that stands."""
    from design_checker.check import check_site
    r = check_site(_plot(box(12, 30, 38, 65)), {**FACTS, "jurisdiction": CITY},
                   extras={"not_included": ["porch"], "touching": ["porch"]})
    rows = {x["Rule id"]: x for x in r["rows"]}
    front = items(r["view"])["Front yard"]
    assert rows[front["rule"]]["Verdict"] == present.COMPLIES
    assert front["status"] == present.REVIEW and "touching" in front["reason"]


def test_the_panel_is_never_above_the_checker_for_any_design():
    """Review round 3's property: random houses on the plain lot, the real 106 lot (open questions) and a corner
    lot, on the tax map and on a survey, with unmeasured objects (touching or not) and an unknown use: no panel
    item is ever more favourable than its row's verdict from the checker."""
    import random
    from design_checker.check import check_site
    from test_measure import lot as lot_of
    rnd = random.Random(3)
    lot106, facts106 = _sample106()
    plain = ({**FACTS, "jurisdiction": CITY}, lot_of([(0, 0), (50, 0), (50, 100), (0, 100)]), (50, 100))
    lots = [plain, (facts106, lot106, (76, 92)), ({**FACTS, "jurisdiction": CITY, "corner_lot": True}, plain[1], (50, 100))]
    for k in range(60):
        facts, lot, (w, d) = lots[k % 3]
        x0, y0 = rnd.uniform(1, w * 0.4), rnd.uniform(5, d * 0.4)
        x1, y1 = rnd.uniform(x0 + 8, w - 1), rnd.uniform(y0 + 10, d - 2)
        extras = rnd.choice([None, {"not_included": ["porch"], "touching": ["porch"]}, {"not_included": ["shed"],
                                                                                        "touching": []}])
        over = {"lot_surveyed": k % 2 == 0, **({"use": None} if k % 7 == 0 else {})}
        r = check_site(_plot(box(x0, y0, x1, y1, 0, rnd.choice((30, 35, 38))), lot_=lot), {**facts, **over},
                       extras=extras)
        _never_above_the_checker(r)
        for i in r["view"]["items"]:
            if i.get("measure"):
                _shown_agrees(i)


def test_red_with_a_complying_core_is_drawn_without_the_core():
    """Review round 2: a house failing all four yards: its red is a ring round the complying core (a polygon with
    a hole), drawn as the whole footprint (only the outline was kept). Each piece is now hole-free and the red is
    exactly the strips: 1,368.06 sf of the 2,868.06 sf footprint."""
    from shapely.geometry import Polygon
    from design_checker.check import check_site, hole_free
    r = check_site(_plot(box(7.252, 12.068, 41.783, 95.125, 0, 36)), {**FACTS, "jurisdiction": CITY})
    red = [Polygon(e["outline"]) for e in r["plan"]["encroach"] if e["why"] == "yard" and e["status"] == present.FAILS]
    assert sum(g.area for g in red) == pytest.approx(1368.06, abs=0.5)
    ring = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [[(3, 3), (7, 3), (7, 7), (3, 7)]])
    pieces = hole_free(ring)
    assert all(not g.interiors for g in pieces) and sum(g.area for g in pieces) == pytest.approx(84)


def test_a_margin_that_rounds_to_nothing_is_at_the_limit_never_plus_zero():
    """106 Ithaca Rd's survey house (2026-10-21): a side yard 10'-0" and a hair read "+0'-0" to spare". A margin to
    spare that rounds down to nothing is "at limit"; a shortfall is never zero (at least the smallest step); the
    tax-map words never say "at least 0'-0"". Every unit, at and around each step."""
    e = present.EIGHTH
    cases = {
        ("ft", 0.0): "at limit", ("ft", e * 0.3): "at limit", ("ft", e * 0.5): "at limit", ("ft", e * 0.99): "at limit",
        ("ft", e): "+0'-0 1/8\"", ("ft", e * 1.5): "+0'-0 1/8\"", ("ft", -e * 0.3): "−0'-0 1/8\"",
        ("ft", -e * 1.5): "−0'-0 1/4\"",
        ("sf", 0.4): "at limit", ("sf", 0.6): "at limit", ("sf", 1.0): "+1 sf", ("sf", 1.7): "+1 sf",
        ("sf", -0.2): "−1 sf",
        ("%", 0.004): "at limit", ("%", 0.007): "at limit", ("%", 0.01): "+0.01%", ("%", 0.019): "+0.01%",
        ("%", -0.003): "−0.01%",
    }
    got = {k: present.margin_text(k[1], k[0]) for k in cases}
    assert got == cases
    C, F = present.COMPLIES, present.FAILS
    assert present.delta_words(C, (e * 0.7, 4.0), "ft", True) == "at the limit at worst"
    assert present.delta_words(F, (-5.0, -e * 0.7), "ft", True) == "less than 0'-0 1/8\" short"
    assert present.delta_words(F, (-5.0, -e), "ft", True) == "at least 0'-0 1/8\" short"
    zeros = ("+0'-0\"", "−0'-0\"", "+0 sf", "−0 sf", "+0%", "−0%", "at least 0'-0\"")
    for k in range(-400, 401):                                  # a fine sweep across the steps of every unit
        for unit, step in (("ft", e / 8), ("sf", 1 / 8), ("%", 0.01 / 8)):
            text = present.margin_text(k * step, unit)
            assert not any(z in text for z in zeros), (unit, k * step, text)
        for low, high in ((k * e / 8, 4.0), (-5.0, k * e / 8 - 1e-9)):
            if low <= high:
                for status in (present.COMPLIES, present.REVIEW, present.FAILS):
                    for approx in (True, False):
                        text = present.delta_words(status, (low, high), "ft", approx)
                        assert not any(z in text for z in zeros), (low, high, text)


def test_a_row_complying_under_every_reading_names_only_the_questions_it_turns_on():
    """Review of e949a01: the wording named every question in the joined reason. Now only the open measurements
    the result turns on (with one unknown and the others at any reading, the result can't be told), each by its
    own reason's short name: scenario 10's side yard turns on the overhang question only (its lot lines are clear),
    never on which lot lines are side lines."""
    from design_checker import scenarios
    from design_checker.check import check_site
    s, f, extras = scenarios.site(scenarios.load(scenarios.FOLDER / "10_one_floor_moved_on_its_own.yaml"))
    side = {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}["Side yard, East"]
    assert side["reason"] == ("Complies under every reading, but it depends on an open question: whether a yard is "
                              "measured to the wall or to overhangs, and what counts as part of the building; "
                              "confirm with the zoning office")
    rule = {"id": "x", "kind": "rule", "check": "side_yard_smaller >= 10 or side_yard_larger >= 10"}
    measured = {"side_yard_smaller": {"value": None, "readings": [{"reading": "r", "value": 12}, {"reading": "s", "value": 15}]},
                "side_yard_larger": {"value": None, "readings": [{"reading": "r", "value": 12}, {"reading": "s", "value": 15}]}}
    from design_checker.check import turns_on
    assert turns_on(rule, measured, {}) == []                    # either one decides it: it turns on neither


def test_every_open_question_the_measuring_asks_has_a_short_name():
    """One table: every tagged question in the measuring code, and every untagged one it keeps as a constant."""
    import re
    from pathlib import Path
    from model_measurement import measure
    src = Path(measure.__file__).read_text(encoding="utf-8")
    tags = set(re.findall(r"open questions? for the architects \(([a-z_]+)\)", src)) | set(re.findall(r"\((story)\)\"", src))
    assert tags and all(t in present.QUESTION_NAMES for t in tags), tags - set(present.QUESTION_NAMES)
    for constant in (measure.ROOF_KIND, measure.ABOVE_ROOF, measure.ACCESSORY, measure.PITCHED):
        assert present.question_name(constant), constant
    assert present._user_text("parts that stick out (overhangs) count (building_area)") == \
        "parts that stick out (overhangs) count"                    # only tags are stripped

def test_side_yards_are_named_by_the_true_compass_on_a_turned_plan():
    """A looked-up lot is drawn turned so its street runs along the bottom (106 Ithaca Rd: 306.38 degrees), so
    "East" in the plan isn't east: its side yards face northeast and southwest. A hand-drawn lot (no turn) keeps
    East/West."""
    sides = {"side_yard_smaller": {"points": [[73.0, 40.0], [61.0, 40.0]]},     # lot line end, building end
             "side_yard_larger": {"points": [[0.0, 40.0], [12.0, 40.0]]}}
    assert present._side_name("side_yard_smaller", sides) == "Side yard, East"
    assert present._side_name("side_yard_larger", sides) == "Side yard, West"
    assert present._side_name("side_yard_smaller", sides, 306.38) == "Side yard, Northeast"
    assert present._side_name("side_yard_larger", sides, 306.38) == "Side yard, Southwest"
    from design_checker import scenarios
    from design_checker.check import check_site
    s, f, extras = scenarios.site(scenarios.load(scenarios.FOLDER / "01_every_limit_at_the_line.yaml"))
    names = {i["name"] for i in check_site(s, {**f, "plan_north_deg": 306.38}, extras=extras)["view"]["items"]}
    assert {"Side yard, Northeast", "Side yard, Southwest"} <= names
    names = {i["name"] for i in check_site(s, f, extras=extras)["view"]["items"]}
    assert {"Side yard, East", "Side yard, West"} <= names


def _feet(text):
    """4'-11 3/8" -> 4.921875 (feet_inches read back)."""
    import re
    ft, inch, frac = re.fullmatch(r"(\d+)'-(\d+)(?: (\d+/\d+))?\"", text).groups()
    num, den = (frac or "0/1").split("/")
    return int(ft) + (int(inch) + int(num) / int(den)) / 12


def test_doing_what_to_comply_says_makes_that_row_comply_on_the_tax_map_and_on_a_survey():
    """The architect's review (pass 2, P1): on a tax-map lot "To comply" gave the shortfall as drawn, and moving
    by it left the side yard needing review. The advice now comes from the verdict's own reading set: for random
    houses on the plain lot, tax map and survey, doing exactly what a row's "To comply" says (that wall pulled in,
    or the roof lowered, by the amount it gives; for the height's two ways, each in turn) makes that row COMPLY.
    On the tax map it says "whatever the survey shows" and gives the as-drawn figure as well; on a survey, one
    number. A yard the height bonus would raise says what it needs if the building stays that tall too; the test
    does each: that figure with the height kept, its own with the roof brought down to 35'-0" (review round 1, F4:
    moving by the yard's own figure alone had left it in review)."""
    import random
    import re
    from design_checker.check import check_site
    from test_measure import lot as lot_of
    rnd = random.Random(21)
    plain = lot_of([(0, 0), (50, 0), (50, 100), (0, 100)])
    pull = {"Side yard, West": (1, 0), "Side yard, East": (-1, 2), "Front yard": (1, 1), "Rear yard": (-1, 3)}
    one = r"(\d+'-\d+(?: \d/\d)?\")"
    drawn = r"(?: \(" + one + r" as drawn\))?"
    length = one + drawn
    tall = r"(?:; " + one + r" if it stays \d+'-\d+(?: \d/\d)?\" tall \(the building height rule's other way raises this yard\))?"
    ways = {"move": re.compile(r"(move the building|make this yard) " + one +
                               r" (?:farther from that lot line|deeper, keeping the other yards)" + drawn + tall),
            "lower": re.compile(r"lower the building " + length),
            "deeper": re.compile(r"make the (front yard|rear yard|side yard) " + length + r" deeper, keeping the other yards")}
    tried = {True: 0, False: 0}
    kinds = set()
    for k in range(80):
        surveyed = k % 2 == 0
        x0, y0 = rnd.uniform(4, 14), rnd.uniform(18, 30)
        x1, y1 = rnd.uniform(36, 47), rnd.uniform(70, 82)
        h = rnd.choice((30, 35, 36.5, 38))
        facts = {**FACTS, "jurisdiction": CITY, "lot_surveyed": surveyed}
        rows = {i["name"]: i for i in check_site(_plot(box(x0, y0, x1, y1, 0, h), lot_=plain), facts)["view"]["items"]}
        for name, i in rows.items():
            hint = i.get("hint") or ""
            if not hint.startswith("To comply") or not (name in pull or name == "Building height"):
                continue
            head, _, body = hint.partition(": ")
            assert head in ("To comply", "To comply whatever the survey shows") and body.endswith("."), (k, name, hint)
            for part in body[:-1].split(", or "):
                kind, m = next(((kd, w.fullmatch(part)) for kd, w in ways.items() if w.fullmatch(part)), (None, None))
                assert m, (k, name, part)
                whole = kind == "move" and m.group(1) == "move the building"   # else only that wall pulled in
                yard, gap_t, drawn_t = (m.group(1), m.group(2), m.group(3)) if kind == "deeper" else \
                    (None, m.group(2), m.group(3)) if kind == "move" else (None, m.group(1), m.group(2))
                if kind == "move" and m.group(4):              # while it stays this tall: its own figure too
                    tall_gap = _feet(m.group(4))
                    assert tall_gap > _feet(gap_t), (k, name, hint)
                    sign, at = pull[name]
                    c = [x0, y0, x1, y1]
                    c[at] += sign * _feet(gap_t)
                    if whole:
                        c[at ^ 2] += sign * _feet(gap_t)
                    lowered = {j["name"]: j for j in check_site(_plot(box(*c, 0, 35), lot_=plain), facts)["view"]["items"]}
                    assert lowered[name]["status"] == present.COMPLIES, (k, name, hint, lowered[name]["reason"])
                    gap_t = m.group(4)                         # and with the height kept: the larger figure
                    kinds.add(("tall", True))
                if surveyed:                                   # a survey: one number, said plainly
                    assert head == "To comply" and drawn_t is None, (k, name, hint)
                if drawn_t:                                    # the as-drawn figure only beside a larger one
                    assert _feet(drawn_t) < _feet(gap_t) and head.endswith("survey shows"), (k, name, hint)
                gap, c, hh = _feet(gap_t), [x0, y0, x1, y1], h
                if kind == "lower":
                    hh = h - gap
                else:
                    side = "Side yard, West" if x0 <= 50 - x1 else "Side yard, East"    # the smaller one
                    sign, at = pull[name if kind == "move" else side if yard == "side yard" else yard.capitalize()]
                    c[at] += sign * gap
                    if whole:                                  # the whole building: the opposite yard shrinks
                        c[at ^ 2] += sign * gap
                r2 = check_site(_plot(box(*c, 0, hh), lot_=plain), facts)
                every = {j["name"]: j for j in r2["view"]["items"]}
                after = every[name]
                assert after["status"] == present.COMPLIES, (k, name, part, after["status"], after["reason"])
                if kind == "move":                             # review round 3, F2: and never at the opposite
                    opp = {0: "Side yard, East", 2: "Side yard, West", 1: "Rear yard", 3: "Front yard"}[pull[name][1]]
                    assert present.RANK[every[opp]["status"]] >= present.RANK[rows[opp]["status"]], \
                        (k, name, part, opp, rows[opp]["status"], every[opp]["status"])
                    kinds.add(("keep" if not whole else "whole", True))
                tried[surveyed] += 1
                kinds.add((kind, bool(drawn_t)))
    assert tried[True] >= 15 and tried[False] >= 15, tried          # both kinds of lot really exercised
    assert {("move", True), ("move", False), ("lower", False), ("deeper", False), ("tall", True), ("keep", True),
            ("whole", True)} <= kinds, kinds
    # the architect's case, word for word (the coordinator's wording): a west side yard 2'-11 3/8" short as drawn
    words = {}
    for surveyed in (False, True):
        for b in ((7.053, 26, 38, 72, 30), (16, 20, 34, 66, 36.5)):
            r = check_site(_plot(box(*b[:4], 0, b[4]), lot_=plain), {**FACTS, "jurisdiction": CITY, "lot_surveyed": surveyed})
            words.update({(surveyed, b[4], i["name"]): i.get("hint") for i in r["view"]["items"]})
    # this 31 ft house has 19 ft between its side yards, which need 20: moving it west would take the east yard
    # under its minimum, so the advice keeps the other yards (review round 3, F2)
    assert words[(False, 30, "Side yard, West")] == ("To comply whatever the survey shows: make this yard 4'-11 3/8\" "
                                                     "deeper, keeping the other yards (2'-11 3/8\" as drawn).")
    assert words[(True, 30, "Side yard, West")] == "To comply: make this yard 2'-11 3/8\" deeper, keeping the other yards."
    # a 26 ft house, the east yard 17 ft: room to move it, so the coordinator's words, exactly
    for surveyed, want in ((False, "To comply whatever the survey shows: move the building 4'-11 3/8\" farther from that "
                                   "lot line (2'-11 3/8\" as drawn)."),
                           (True, "To comply: move the building 2'-11 3/8\" farther from that lot line.")):
        r = check_site(_plot(box(7.053, 26, 33, 72, 0, 30), lot_=plain), {**FACTS, "jurisdiction": CITY, "lot_surveyed": surveyed})
        assert next(i for i in r["view"]["items"] if i["name"] == "Side yard, West")["hint"] == want
    assert words[(False, 30, "Front yard")] == ("To comply whatever the survey shows: make this yard 1'-0\" deeper, "
                                                "keeping the other yards.")  # in review as drawn: what makes it comply
    # (the rear yard, 28'-0" against up to 26'-0" at the tax map's worst, has no foot to give)
    assert words[(False, 36.5, "Building height")] == (
        "To comply whatever the survey shows: lower the building 1'-6\", or make the front yard 8'-6\" (6'-6\" as drawn) "
        "deeper, keeping the other yards.")
    assert words[(True, 36.5, "Building height")] == ("To comply: lower the building 1'-6\", or make the front yard 6'-6\" "
                                                      "deeper, keeping the other yards.")
    assert words[(False, 36.5, "Front yard")] == (
        "To comply whatever the survey shows: make this yard 7'-0\" deeper, keeping the other yards (5'-0\" as drawn); "
        "8'-6\" if it stays 36'-6\" tall (the building height rule's other way raises this yard).")
    assert words[(True, 36.5, "Front yard")] == (
        "To comply: move the building 5'-0\" farther from that lot line; 6'-6\" if it stays 36'-6\" tall (the building "
        "height rule's other way raises this yard).")
    # review round 1, F1: a lot's own size is no design change: a tax-map lot that complies as drawn but not at
    # its smallest reading gets no "increase it by …" (no change to the design, nor any survey, could do it)
    for w_, d_ in ((51, 118), (50, 125)):
        r = check_site(_plot(box(10, 26, w_ - 12, 72, 0, 30), lot_=lot_of([(0, 0), (w_, 0), (w_, d_), (0, d_)])),
                       {**FACTS, "jurisdiction": CITY, "lot_surveyed": False, "street_line": [[[0, 0], [w_, 0]]]})
        site = {i["name"]: i for i in r["view"]["items"] if i.get("measure") in present.SITE_MEASURES}
        assert site and all(not (i.get("hint") or "").startswith("To comply") for i in site.values()), \
            {n: (i["status"], i.get("hint")) for n, i in site.items()}
        assert any(i["status"] == present.REVIEW for i in site.values())         # the case really arose
    # a yard the height bonus raises (a 36'-6" house using the other way), complying as drawn but not at the tax
    # map's worst: its own "To comply" from the raised minimum, and doing it makes the row comply
    raised = {}
    for y0 in (27, 28.5):
        r = check_site(_plot(box(15, y0, 35, 66, 0, 36.5), lot_=plain), {**FACTS, "jurisdiction": CITY, "lot_surveyed": False})
        raised[y0] = next(i for i in r["view"]["items"] if i["name"] == "Front yard")
    assert raised[27]["status"] == present.REVIEW and "other way needs" in raised[27]["reason"]
    assert raised[27]["hint"] == "To comply whatever the survey shows: move the building 1'-6\" farther from that lot line."
    assert raised[28.5]["status"] == present.COMPLIES                          # 27 + 1'-6"


def test_a_row_that_turns_on_an_open_question_is_never_told_how_to_comply():
    """Review round 1, F5: the checker never lets a row whose result turns on an open question comply (whether a
    yard is measured to the wall or to the overhangs), so no move can. Scenario 10 with floor 2 overhanging 7 ft
    east: the east side yard turns on it, and it gets no "To comply" (it had "move the building 2'-0" …", and
    after that move it still needed review)."""
    import copy
    from design_checker import scenarios
    from design_checker.check import check_site
    base = scenarios.load(scenarios.FOLDER / "10_one_floor_moved_on_its_own.yaml")
    seen = 0
    for shift in (0, -2, -5):
        sc = copy.deepcopy(base)
        b = sc["buildings"][0]
        b["outline"] = [[x + shift, y] for x, y in b["outline"]]
        b["move_floor"] = {"floor": 2, "by": [7, 0]}
        s, f, extras = scenarios.site(sc)
        r = check_site(s, f, extras=extras)
        rows = {x["Rule id"]: x for x in r["rows"]}
        for i in r["view"]["items"]:
            row = rows.get(i.get("rule")) or {}
            turns = (row.get("Side turns on") or {}).get(i.get("measure")) if i.get("measure") in (row.get("Sides") or {}) \
                else row.get("Turns on")
            if turns:
                seen += i["name"] == "Side yard, East"
                assert not (i.get("hint") or "").startswith("To comply"), (shift, i["name"], turns, i.get("hint"))
    assert seen == 3
    # but an open question a row turns on only through its limit goes away with the right change: a 36'-6" house
    # on 106 (its back lines side or rear: the lot depth the bonus's rear yard reads is open) keeps "lower the
    # building 1'-6"", and lowering it makes the row comply
    import random
    from shapely.geometry import Polygon, box as rect
    from design_checker.check import sample_site
    from test_measure import lot as lot_of
    sample = sample_site()
    ring = sample["lot"]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    rnd, kept = random.Random(5), 0
    for k in range(120):
        x0, y0 = rnd.uniform(min(xs) + 1, 40), rnd.uniform(min(ys) + 5, 40)
        x1, y1 = rnd.uniform(x0 + 8, max(xs) - 1), rnd.uniform(y0 + 10, max(ys) - 2)
        h = rnd.choice((30, 36.5))
        if not Polygon(ring).buffer(-2).contains(rect(x0, y0, x1, y1)):
            continue                     # a house over a lot line is in review for that, whatever its height
        facts = {**sample["facts"], "lot_surveyed": k % 2 == 0}
        r = check_site(_plot(box(x0, y0, x1, y1, 0, h), lot_=lot_of(ring)), facts)
        rows = {x["Rule id"]: x for x in r["rows"]}
        item = next(i for i in r["view"]["items"] if i["name"] == "Building height")
        if rows[item["rule"]].get("Turns on") and (item.get("hint") or "").startswith("To comply: lower the building"):
            gap = _feet(item["hint"].split("lower the building ")[1].split(",")[0].rstrip("."))
            r2 = check_site(_plot(box(x0, y0, x1, y1, 0, h - gap), lot_=lot_of(ring)), facts)
            again = next(i for i in r2["view"]["items"] if i["name"] == "Building height")
            assert again["status"] == present.COMPLIES, (k, item["hint"], again["reason"])
            kept += 1
    assert kept >= 3, kept
    # and coverage on a tax-map lot, which lists the lot area as what it turns on (scenario 08): "reduce the
    # footprint by at least 76 sf", and taking 76 sf off makes it comply
    from shapely.geometry import Polygon as Shape
    sc08 = scenarios.load(scenarios.FOLDER / "08_tax_map_lot_front_yard_within_two_feet.yaml")
    cov = {}
    for cut in (0, 76):
        sc = copy.deepcopy(sc08)
        b = sc["buildings"][0]
        xs = [p[0] for p in b["outline"]]
        dx = cut / (Shape(b["outline"]).area / (max(xs) - min(xs)))          # the east side trimmed by `cut` sf
        b["outline"] = [[x - dx if abs(x - max(xs)) < 1e-9 else x, y] for x, y in b["outline"]]
        s, f, extras = scenarios.site(sc)
        r = check_site(s, f, extras=extras)
        cov[cut] = next(i for i in r["view"]["items"] if i["name"] == "Lot coverage")
        assert next(x for x in r["rows"] if x["Rule id"] == cov[cut]["rule"]).get("Turns on") == ["lot_area"]
    assert cov[0]["hint"] == "To comply whatever the survey shows: reduce the footprint by at least 76 sf."
    assert cov[76]["status"] == present.COMPLIES, cov[76]["reason"]



def test_the_report_opens_on_the_check_sheet_and_every_tab_says_what_the_panel_says(surveyed, tmp_path):
    """Architect review in Rhino (P1-4): the report opened on Inputs, its Output showed PASS beside "Can't check:
    lot_area missing" and "not given" beside the panel's 7,033 sf, its title was the model's file name and its code
    line read "PUDs only". Now it opens on the Check sheet; each Output row's Error, Why and Proposed come from the
    panel's items; an input the measurement left open shows the panel's reading; the code line names the
    ordinance and its date only."""
    import openpyxl
    report = tmp_path / "r.xlsx"
    check(MODEL, {**surveyed, "lot_surveyed": False, "address": "106 Ithaca Rd, Ithaca, NY"}, report)
    wb = openpyxl.load_workbook(report)
    assert wb.sheetnames[0] == "Check" and wb.active.title == "Check"
    out = wb["Output"]
    head = [c.value for c in out[2]]
    rows = [r for r in out.iter_rows(min_row=3, values_only=True) if r[0] and r[head.index("Error")]]
    for r in rows:
        if r[head.index("Error")] == "PASS":
            assert not r[head.index("Why it needs review")], r
            assert r[head.index("Proposed")] not in (None, "", "not given", "—"), r
    assert "106 Ithaca Rd" in str(out["A1"].value)
    text = " ".join(str(c.value) for c in wb["Check"]["A"] if c.value)
    assert "PUDs" not in text and "Ord. No." in text
    from design_checker import rhino_logic as logic
    # the street line's own street only: the address's street may not be the line highlighted (review of P1-4)
    assert logic.street_name({"address": "106 Ithaca Rd, Ithaca, NY 14850"}) == "the highlighted line"
    assert logic.street_name({"street_name": "Ithaca Rd"}) == "Ithaca Rd"



def test_a_limit_waiting_on_the_lot_depth_shows_its_range_and_says_once_why():
    """Architect review in Rhino (P1-3): on the sample 106 lot the rear yard's detail repeated "the readings give
    different values … isn't settled yet" two or three times and showed "—" as Required. Now Required is the
    limit's range over the lot depth's readings, and the reason is one sentence saying what it depends on."""
    from design_checker.check import check_site
    lot, facts = _sample106()
    house = box(10.2806, 24.0480, 39.2642, 73.2738, 0, 30)
    for surveyed, status in ((False, present.REVIEW), (True, present.FAILS)):
        r = check_site(_plot(house, lot_=lot), {**facts, "lot_surveyed": surveyed})
        rear = items(r["view"])["Rear yard"]
        assert rear["status"] == status and rear["required"] == "21'-1 5/8\" to 25'-5 1/2\"", rear
        assert rear["reason"].count("which lot lines") == 1, rear["reason"]
        assert "readings give different values" not in rear["reason"] and "isn't settled" not in rear["reason"]
    assert rear["reason"].startswith("Does not comply whichever way it is read: needs 21'-1 5/8\"")
    r = check_site(_plot(house, lot_=lot), {**facts, "lot_surveyed": False})
    assert items(r["view"])["Rear yard"]["reason"].startswith(
        "Needs 21'-1 5/8\" to 25'-5 1/2\", depending on which lot lines count as side and which as rear "
        "(it sets the lot depth): ask the zoning office")


def test_coverage_that_turns_on_the_overhang_question_says_both_ways():
    """Architect review in Rhino (P2-10): "At worst 28.5% against 25%: does not comply under that reading. the
    readings give different values; whether parts … count isn't settled yet" said one way, twice. Now both ways in
    one sentence; complying either way keeps its own words."""
    from design_checker.check import check_site
    lot, facts = _sample106()
    ground = box(12, 30, 40, 70, 0, 10, "a")
    r = check_site(_plot(ground, box(12, 30, 62, 70, 10, 20, "b"), lot_=lot),
                   {**facts, "lot_surveyed": True, "main_building": "a"})
    cov = items(r["view"])["Lot coverage"]
    assert cov["reason"] == ("If overhangs count (an open question), coverage is 28.5%, over 25%; if not, 16%: "
                             "ask the zoning office"), cov["reason"]
    r = check_site(_plot(ground, box(12, 30, 52, 70, 10, 20, "b"), lot_=lot),
                   {**facts, "lot_surveyed": True, "main_building": "a"})
    assert items(r["view"])["Lot coverage"]["reason"].startswith("Complies under every reading")


def test_an_assumed_main_building_is_said_on_the_panel_and_the_check_sheet(tmp_path):
    """Review of the main-building default (P1): the assumption reached only the report's Inputs tab; height,
    stories and yards read COMPLIES with no caveat. The header says "Main building: the starting house (assumed)"
    and every row measured from it carries the note, on the Check sheet too."""
    import openpyxl
    from design_checker.check import check_site
    from test_measure import floor
    lot, facts = _sample106()
    house = [floor(12, 30, 36, 70, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
    garage = box(45, 75, 55, 90, 0, 10, "garage")
    r = check_site(_plot(*house, garage, lot_=lot), {**facts, "lot_surveyed": True, "stories": 3},
                   report_path=tmp_path / "r.xlsx")
    assert r["view"]["header"]["main"] == present.ASSUMED_MAIN
    by = items(r["view"])
    for name in ("Building height", "Stories", "Front yard"):
        assert present.ASSUMED_MAIN_NOTE in (by[name].get("note") or ""), (name, by[name])
    text = " ".join(str(c.value) for row in openpyxl.load_workbook(tmp_path / "r.xlsx")["Check"].iter_rows()
                    for c in row if c.value)
    assert present.ASSUMED_MAIN in text and present.ASSUMED_MAIN_NOTE in text



def test_the_report_keeps_each_rows_units_and_the_panels_words(surveyed, tmp_path):
    """Review of P1-4 (P2): the coverage item's percentage went into the Building area input and the coverage
    row, both in sf. A row taken from the panel takes its limit and units with it; an input only in its own unit."""
    import openpyxl
    from design_checker.check import check_site
    lot, facts = _sample106()
    ground = box(12, 30, 40, 70, 0, 10, "a")
    check_site(_plot(ground, box(12, 30, 62, 70, 10, 20, "b"), lot_=lot),
               {**facts, "lot_surveyed": True, "main_building": "a"}, report_path=tmp_path / "r.xlsx")
    wb = openpyxl.load_workbook(tmp_path / "r.xlsx")
    out, ins = wb["Output"], wb["Inputs"]
    head = [c.value for c in out[2]]
    cov = next(r for r in out.iter_rows(min_row=3, values_only=True) if r[0] and "coverage" in r[0].lower())
    assert "%" in str(cov[head.index("Proposed")]) and "%" in str(cov[head.index("Table limit")])
    assert cov[head.index("Units")] == "% of lot area"
    area = next(r for r in ins.iter_rows(min_row=3, values_only=True) if r[0] == "Building area")
    assert "%" not in str(area[1])


def test_wording_never_sends_the_architect_to_ask_when_the_answer_cant_change_the_result():
    """Review of P1-3 and P2-10: a rear yard complying under every lot-depth reading lost "Complies under every
    reading" for "Needs … ask the zoning office"; coverage failing both ways still said "an open question … ask"."""
    from design_checker.check import check_site
    lot, facts = _sample106()
    r = check_site(_plot(box(12, 30, 40, 50, 0, 30), lot_=lot), {**facts, "lot_surveyed": False})
    rear = items(r["view"])["Rear yard"]
    assert rear["required"] == "21'-1 5/8\" to 25'-5 1/2\"" and rear["reason"].startswith("Complies under every reading"), rear
    r = check_site(_plot(box(12, 30, 48, 85, 0, 10, "a"), box(10, 28, 50, 90, 10, 20, "b"), lot_=lot),
                   {**facts, "lot_surveyed": True, "main_building": "a"})
    cov = items(r["view"])["Lot coverage"]
    assert cov["reason"].startswith("Does not comply either way: coverage is") and "ask" not in cov["reason"], cov


def _walls_spots(x0, y0, x1, y1, z):
    """A spot grade at the middle of each wall of a rectangle, just outside it, at level z."""
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    return [[mx, y0 - 0.5, z], [mx, y1 + 0.5, z], [x0 - 0.5, my, z], [x1 + 0.5, my, z]]


def test_an_assumed_main_building_is_never_kinder_than_picking_the_starting_house():
    """Round 2 of the main-building fixes (P0): the candidates were read by position, so the "with every other
    solid" height came from the last other building's own (higher) ground: with the main building assumed, a
    height complied that picking the starting house fails. Property, over random layouts on the sample lot
    (a starting house and one or two other buildings, each on its own ground, spot grades at every wall): with
    the starting house assumed, no row is ever kinder than with it picked."""
    import random
    from design_checker.check import check_site
    from test_measure import floor
    lot, facts = _sample106()
    rnd = random.Random(5)
    compared = 0
    for _ in range(30):
        floors, h = rnd.choice([2, 3, 3]), rnd.choice([11, 11.6])        # 3 x 11.6 = 34.8 ft: near the limit
        house = [floor(12, 30, 36, 60, z0=h * i, z1=h * (i + 1), id=f"f{i}") for i in range(floors)]
        points = _walls_spots(12, 30, 36, 60, 0)
        others = []
        for k in range(rnd.choice([1, 2, 2])):           # two: one on lower ground, one on higher, often
            x0, y0 = rnd.choice([(40, 30), (14, 66), (40, 66)])
            if any(o["id"].startswith(f"o{x0}{y0}") for o in others):
                continue
            ground, top = rnd.choice([-8, -6, -3, 0, 3, 5, 8]), rnd.choice([8, 12, 20, 30])
            others.append(box(x0, y0, x0 + 8, y0 + 10, ground, ground + top, f"o{x0}{y0}"))
            points += _walls_spots(x0, y0, x0 + 8, y0 + 10, ground)
        base = {**facts, "lot_surveyed": True, "stories": floors, "ground_is_flat": None, "grade_elevation": None,
                "grade_points": points}
        site_ = _plot(*house, *others, lot_=lot)
        assumed = items(check_site(site_, base)["view"])
        picked = items(check_site(site_, {**base, "main_building": "f0"})["view"])
        from model_measurement.measure import measure
        m_a, m_p = measure(site_, base), measure(site_, {**base, "main_building": "f0"})
        for name in ("building_height", "stories"):     # the pick's every reading is among the assumption's
            def vals(r):
                return {round(x["value"], 3) for x in r["readings"]} or ({round(r["value"], 3)} if r["value"] is not None else set())
            assert vals(m_p[name]) <= vals(m_a[name]) or not vals(m_a[name]), (name, m_p[name], m_a[name])
        for name, i in picked.items():
            if name in assumed and i["status"] in present.RANK and assumed[name]["status"] in present.RANK:
                compared += 1
                assert present.RANK[assumed[name]["status"]] <= present.RANK[i["status"]], \
                    (name, assumed[name]["status"], i["status"], assumed[name]["reason"], [o["id"] for o in others])
    assert compared > 150



def test_the_with_every_other_solid_height_is_read_from_its_own_grade_not_the_last_buildings():
    """Round 2 (P0), the reviewer's case: a 34.8 ft starting house on ground 0, a garage on lower ground (-8) and
    one on higher ground (+5). Read by position, the "with every other solid" height took the last garage's own
    ground (+5) and the assumed house complied; picking the house reads it from the ground at all their walls
    (lower) and it doesn't. Assumed, it is never kinder."""
    from design_checker.check import check_site
    from test_measure import floor
    lot, facts = _sample106()
    house = [floor(12, 30, 36, 60, z0=11.6 * i, z1=11.6 * (i + 1), id=f"f{i}") for i in range(3)]
    low, high = box(40, 30, 48, 40, -8, 4, "low"), box(40, 66, 48, 76, 5, 15, "high")
    points = _walls_spots(12, 30, 36, 60, 0) + _walls_spots(40, 30, 48, 40, -8) + _walls_spots(40, 66, 48, 76, 5)
    base = {**facts, "lot_surveyed": True, "stories": 3, "ground_is_flat": None, "grade_elevation": None,
            "grade_points": points}
    site_ = _plot(*house, low, high, lot_=lot)
    from model_measurement.measure import measure
    def with_others(f):
        return next(r["value"] for r in measure(site_, f)["building_height"]["readings"]
                    if r["reading"].startswith("with every other solid"))
    assert with_others(base) == pytest.approx(with_others({**base, "main_building": "f0"})) == pytest.approx(35.8)
    picked = items(check_site(site_, {**base, "main_building": "f0"})["view"])["Building height"]
    assumed = items(check_site(site_, base)["view"])["Building height"]
    assert picked["status"] != present.COMPLIES, picked
    assert present.RANK[assumed["status"]] <= present.RANK[picked["status"]], (assumed, picked)


def test_every_to_comply_is_confirmed_by_the_checker_on_the_real_106_lot_too():
    """Review round 2: the advice is the checker's to confirm (check.confirm_advice: each change re-decided by
    row_verdict; kept only if the row then complies).
    R1: on 106 a rear yard's limit waits on which lines are side or rear (the lot depth), so no move makes it
    comply: it is never told to move. Doing what any other row on 106 says (the front yard: the house moved back
    from the street; the height: the roof lowered) makes it comply, measured again from the moved house, not by
    the checker's own arithmetic.
    R4: a lot's own size gets no "To comply", on the tax map or a survey.
    R6: a house over the height bonus's own cap (38'-6") is not told what a yard needs "if it stays that tall".
    The side finding: a height row that complies under every reading but turns on open questions isn't told to
    lower the building unless lowering it makes it comply."""
    import random
    import re
    from shapely.geometry import Polygon, box as rect
    from design_checker.check import check_site, sample_site
    from test_measure import lot as lot_of
    sample = sample_site()
    ring = sample["lot"]
    lot106 = lot_of(ring)
    r = check_site(_plot(box(4.232, 29.235, 59.558, 77.162, 0, 30), lot_=lot106), {**sample["facts"], "lot_surveyed": True})
    rear = next(i for i in r["view"]["items"] if i["name"] == "Rear yard")
    assert rear["status"] == present.FAILS and rear.get("hint") is None, rear.get("hint")
    rnd, followed = random.Random(3), {"front": 0, "lower": 0}
    for k in range(80):
        x0, y0 = rnd.uniform(2, 30), rnd.uniform(10, 40)
        x1, y1 = rnd.uniform(x0 + 15, 74), rnd.uniform(y0 + 15, 99)
        if not Polygon(ring).buffer(-1).contains(rect(x0, y0, x1, y1)):
            continue
        h = rnd.choice((30, 36.5))
        facts = {**sample["facts"], "lot_surveyed": k % 2 == 0}
        items = {i["name"]: i for i in check_site(_plot(box(x0, y0, x1, y1, 0, h), lot_=lot106), facts)["view"]["items"]}
        assert not (items["Rear yard"].get("hint") or "").startswith("To comply"), (k, items["Rear yard"]["hint"])
        front = items["Front yard"].get("hint") or ""
        m = re.match(r"To comply[^:]*: (move the building|make this yard) (\d+'-\d+(?: \d/\d)?\")", front)
        tall = re.search(r"; (\d+'-\d+(?: \d/\d)?\") if it stays", front)     # the house stays this tall: that
        if m and items["Front yard"].get("points"):          # figure; along the line it was measured on
            gap = _feet((tall or m).group(1 if tall else 2))
            (ax, ay), (bx, by) = items["Front yard"]["points"][:2]
            mid = ((x0 + x1) / 2, (y0 + y1) / 2)
            if (ax - mid[0]) ** 2 + (ay - mid[1]) ** 2 > (bx - mid[0]) ** 2 + (by - mid[1]) ** 2:
                (ax, ay), (bx, by) = (bx, by), (ax, ay)          # a: on the wall, b: on the street line
            n = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
            ux, uy = (ax - bx) / n, (ay - by) / n
            if m.group(1) == "move the building":            # the whole house moved away
                c = (x0 + ux * gap, y0 + uy * gap, x1 + ux * gap, y1 + uy * gap)
            else:                                            # only its front wall pulled back, the rest kept
                c = (x0, y0 + gap / abs(uy), x1, y1)
            again = check_site(_plot(box(*c, 0, h), lot_=lot106), facts)
            got = next(i for i in again["view"]["items"] if i["name"] == "Front yard")
            if Polygon(ring).buffer(-1).contains(rect(*c)) and c[1] < c[3] - 5:
                assert got["status"] == present.COMPLIES, (k, front, got["status"], got["reason"])
                followed["front"] += 1
        height = items["Building height"].get("hint") or ""
        m = re.match(r"To comply[^:]*: lower the building (\d+'-\d+(?: \d/\d)?\")", height)
        if m:
            again = check_site(_plot(box(x0, y0, x1, y1, 0, h - _feet(m.group(1))), lot_=lot106), facts)
            got = next(i for i in again["view"]["items"] if i["name"] == "Building height")
            assert got["status"] == present.COMPLIES, (k, height, got["reason"])
            followed["lower"] += 1
    assert followed["front"] >= 3 and followed["lower"] >= 3, followed
    # the side finding: surveyed 106, 36'-6", complies under every reading but turns on open questions
    r = check_site(_plot(box(16, 28, 40, 52, 0, 36.5), lot_=lot106), {**sample["facts"], "lot_surveyed": True})
    hgt = next(i for i in r["view"]["items"] if i["name"] == "Building height")
    m = re.match(r"To comply[^:]*: lower the building (\d+'-\d+(?: \d/\d)?\")", hgt.get("hint") or "")
    if m:
        again = check_site(_plot(box(16, 28, 40, 52, 0, 36.5 - _feet(m.group(1))), lot_=lot106),
                           {**sample["facts"], "lot_surveyed": True})
        assert next(i for i in again["view"]["items"] if i["name"] == "Building height")["status"] == present.COMPLIES
    # R4
    small = lot_of([(0, 0), (50, 0), (50, 100), (0, 100)])
    for surveyed in (False, True):
        r = check_site(_plot(box(12, 26, 38, 70, 0, 30), lot_=small), {**FACTS, "jurisdiction": CITY, "lot_surveyed": surveyed})
        area = next(i for i in r["view"]["items"] if i["name"] == "Lot area")
        assert area["status"] == present.FAILS and not (area.get("hint") or "").startswith("To comply"), area.get("hint")
    # R6
    r = check_site(_plot(box(12, 20, 38, 66, 0, 60), lot_=small), {**FACTS, "jurisdiction": CITY, "lot_surveyed": True})
    fy = next(i for i in r["view"]["items"] if i["name"] == "Front yard")
    assert fy["hint"] == "To comply: move the building 5'-0\" farther from that lot line.", fy["hint"]


def test_a_raised_yards_advice_is_confirmed_against_the_raise_not_just_its_own_minimum(monkeypatch):
    """Review round 3, F3: a yard the height bonus raises is short of the raised minimum, not its own; confirmed
    against its own minimum alone, any change at all passed (a tenth of the figure kept the hint). Now each change
    is also decided against the raise it answers to: a tenth of it is no fix, so no hint, while the real figure
    (1'-6": the front yard 27'-0" against 26'-6", 25'-0" at the tax map's worst) stays."""
    from design_checker.check import check_site
    from test_measure import lot as lot_of
    plain = lot_of([(0, 0), (50, 0), (50, 100), (0, 100)])
    facts = {**FACTS, "jurisdiction": CITY, "lot_surveyed": False}

    def front():
        r = check_site(_plot(box(15, 27, 35, 66, 0, 36.5), lot_=plain), facts)
        return next(i for i in r["view"]["items"] if i["name"] == "Front yard")

    assert front()["hint"] == "To comply whatever the survey shows: move the building 1'-6\" farther from that lot line."
    real = present.comply_hint

    def tenth(*a, **k):                  # every advised change a tenth of what it says
        advice = real(*a, **k)
        for way in (advice or {}).get("ways") or []:
            way["changes"] = {m: d / 10 for m, d in way["changes"].items()}
        return advice

    monkeypatch.setattr(present, "comply_hint", tenth)
    got = front()
    assert got["status"] == present.REVIEW and got["hint"] is None, got["hint"]
