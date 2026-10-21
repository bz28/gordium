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


def test_complies_only_when_the_checker_passed_or_it_holds_at_the_tax_map_worst_case(tax_map):
    """The one way a row the checker left NEEDS REVIEW reads complies: it waits only on the survey, and it holds
    at both ends of the tax-map tolerance (spec C2). Nothing else is ever made less cautious."""
    rows = {r["Rule id"]: r for r in tax_map["rows"]}
    for i in tax_map["view"]["items"]:
        if i["rule"] and i["status"] == present.COMPLIES and rows[i["rule"]]["Error"] != "PASS":
            assert rows[i["rule"]]["Provisional"] == present.SURVEY_ONLY, i["name"]
            assert "worst case" in i["reason"], i["name"]
    area = items(tax_map["view"])["Lot area"]                      # the 73 × 90 lot of 106 Ithaca Rd
    assert area["status"] == present.COMPLIES and "worst case (lot area 6,248 sf)" in area["reason"]   # 71 × 88


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
          "margin": "−2'-6\""}]
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
