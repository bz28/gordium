"""What the panel, the viewport and the report show (design_checker/present.py; docs/design/rhino_ui_spec.md):
each test names the spec criterion it pins. Results come from the checker; present can only make one more
cautious, so most of these check that something is never shown as complying without evidence."""

import ast
import copy
import json
import random
import re
import sys
from pathlib import Path

import openpyxl
import pytest

from design_checker import present
from design_checker.check import check
from model_measurement.places.ithaca_city.measure import measure
from model_measurement.project import fact_problems, load_facts
from rule_format.rulebook import REPO, load

SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
MODEL = SITE / "spreadsheet_design_model.3dm"
RULES = {r["id"]: r for r in load(REPO / "regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/R-1b.yaml")["rules"]}
sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_measure import FACTS, RECT, box, sloped_roof_box  # noqa: E402
from host_source import host_text


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


def test_a_row_waiting_on_readings_that_arent_named_still_needs_review():
    """A rule whose readings aren't the named readings of an open question (here a lot line that is a side or a
    rear line) keeps the plain rule: passing every reading still needs review (pitched roofs are now measured:
    tests/test_every_reading.py)."""
    row = {"Rule id": "R-1b.rear_yard", "Error": "NEEDS REVIEW", "Provisional": "passes under every reading",
           "Why": "the readings give different values", "Short": "Rear yard", "Requirement": "Rear yard minimum"}
    measured = measure(_site([box(10, 25, 35, 65)]), FACTS)
    measured["rear_yard"] = {**measured["rear_yard"], "value": None,
                             "readings": [{"reading": "a", "value": 35.0}, {"reading": "b", "value": 40.0}]}
    v = present.view([row], [], RULES, measured, {**FACTS, "jurisdiction": "regulations/jurisdictions/new_york/ithaca_city",
                                                  "zone": "R-1b"})
    assert items(v)["Rear yard"]["status"] == present.REVIEW


# ---- C8: what was measured, and what wasn't ----------------------------------------------------------------------

def test_each_item_says_what_was_measured_and_objects_left_out_need_review(surveyed):
    r = check(MODEL, surveyed, extras={"scope": {"groups": 1, "solids": 3, "layer": "Gordium::Massing"},
                                       "not_included": ["a", "b"]})
    i = items(r["view"])
    assert i["Front yard"]["detail"]["scope"].startswith("Measured: 1 group, 3 solids on Gordium::Massing · footprint")
    left = i["Objects on the lot not included"]
    assert left["status"] == present.REVIEW and left["objects"] == ["a", "b"] and "Add to check" in left["reason"]
    assert "review" in r["view"]["summary"]


def test_a_solid_on_the_neighbourhood_layers_makes_the_check_need_review_and_says_where(surveyed):
    """PR #23 (review of the editable outlines, P0): a solid on Gordium::Context over the lot is left out like any
    other; the row says it is on the neighbourhood layers and how to fix it; the check is never "comply"."""
    r = check(MODEL, surveyed, extras={"not_included": ["ctx"], "context_left_out": ["ctx"]})
    left = items(r["view"])["Objects on the lot not included"]
    assert left["status"] == present.REVIEW and left["objects"] == ["ctx"]
    assert "1 on the neighbourhood layers (Gordium::Context): move it to the Building layer" in left["reason"]
    assert "review" in r["view"]["summary"]
    plain = items(check(MODEL, surveyed, extras={"not_included": ["shed"]})["view"])["Objects on the lot not included"]
    assert "neighbourhood" not in plain["reason"]


LINKED = ("Linked file 'garage.3dm' has changed since it was loaded: reload it (Edit \u25b8 Blocks \u25b8 Block "
          "Definitions, select it, then Update) so Gordium can see where it is")


def test_the_left_out_row_says_what_to_do_about_a_linked_file_and_nothing_else_changes(surveyed):
    """Ben, 2026-11-12: a linked block whose file is missing or changed stays left out and touching (it can't be
    measured), and the row now says which file and what to do, in the host's words (extras["left_out_advice"]),
    once however many of its placings are left out. Every row's status, mark and words but that sentence are the
    same as without it: the advice is words, never a decision's input."""
    extras = {"not_included": ["garage", "garage_again", "shed"], "touching": ["garage", "garage_again"]}
    plain = check(MODEL, surveyed, extras=extras)["view"]
    told = check(MODEL, surveyed, extras={**extras, "left_out_advice": {"garage": LINKED, "garage_again": LINKED}})["view"]
    left = items(told)["Objects on the lot not included"]
    assert left["status"] == present.REVIEW and left["objects"] == ["garage", "garage_again", "shed"]
    assert left["reason"] == items(plain)["Objects on the lot not included"]["reason"] + " \u00b7 " + LINKED
    assert left["reason"].count("garage.3dm") == 1
    assert [(i["id"], i["status"], i["mark"]) for i in told["items"]] == \
        [(i["id"], i["status"], i["mark"]) for i in plain["items"]]
    assert [i for i in told["items"] if i["id"] != "scope.not_included"] == \
        [i for i in plain["items"] if i["id"] != "scope.not_included"]
    assert told["summary"] == plain["summary"]


@pytest.mark.parametrize("advice, words", [
    ({"nowhere": LINKED}, "nowhere given advice"),
    ({"garage": ""}, "left_out_advice is {object id"),
    ({"garage": 7}, "left_out_advice is {object id"),
    (["garage"], "left_out_advice is {object id")])
def test_advice_for_an_object_not_left_out_or_not_words_is_refused(surveyed, advice, words):
    from design_checker.site_json import SiteRefused
    with pytest.raises(SiteRefused, match=re.escape(words)):
        check(MODEL, surveyed, extras={"not_included": ["garage"], "left_out_advice": advice})


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
    assert keys[-1] == "new_york/new_york_state"           # egress (the state law Ithaca inherits): last, its own group
    keys = keys[:-1]
    assert keys == sorted(keys, key=["fails", "review", "complies", "use_details", "not_checked", "not_covered"].index)
    names = [i["name"] for i in tax_map["view"]["items"]]
    assert any(n.startswith("Overlays") for n in names) and any("§325-17B" in n for n in names)


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
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    blocks = tax["plan"]["encroach"]
    assert {e["status"] for e in blocks} == {present.REVIEW}
    assert {e["row"] for e in blocks} == {"Front yard", "Side yard, West"}      # each strip named for its own row
    joined = unary_union([Polygon(e["outline"]) for e in blocks])
    assert joined.area == pytest.approx(86, abs=1.5) and joined.bounds[0] == pytest.approx(11)
    assert sum(Polygon(e["outline"]).area for e in blocks) == pytest.approx(joined.area, abs=0.01)   # never twice


def test_the_delta_on_the_tax_map_says_what_holds_however_the_lines_lie():
    """Architect's review (2026-10-21): "−3'-0" short" while red was only 1 ft. Worked by hand (lot 50 x 100, side
    yards need 10 ft, the tax map ±2 ft on each lot length the rule reads):
    - West wall 7 ft from the line: the yard is really 5 to 9 ft, so 1 to 5 ft short: "at least 1'-0" short"
      (the red part), never "−3'-0" short";
    - 11 ft: really 9 to 13: "up to 1'-0" short" (amber, no red); 16 ft: really 14 to 18: at least 4'-0" to
      spare, "≥ +4'-0"";
    - the same walls on a survey: the margin itself."""
    from design_checker.check import check_site
    tax = {**FACTS, "jurisdiction": CITY, "lot_surveyed": False}
    words = {x: items(check_site(_plot(box(x, 30, 35, 65)), tax)["view"])["Side yard, West"] for x in (7, 11, 16)}
    # the audit of main (2026-10-29): the margin as drawn first, then the end of the ±2 ft that decides the status
    off = "if the tax-map lines are 2 ft off"
    assert [(words[x]["delta"], words[x]["approx"]) for x in (7, 11, 16)] == [
        (f"3'-0\" short (still 1'-0\" short {off} the other way)", True),
        (f"+1'-0\" if confirmed (1'-0\" short {off})", True), (f"+6'-0\" (+4'-0\" {off})", True)]
    assert [words[x]["delta_cell"] for x in (7, 11, 16)] == [
        "−3'-0\"\nbest −1'-0\"", "+1'-0\" if so\nworst −1'-0\"", "+6'-0\"\nworst +4'-0\""]
    assert words[7]["margin"] == "−3'-0\"" and words[7]["status"] == present.FAILS     # as drawn, unchanged
    assert words[7]["detail"]["line"] == "7'-0\" proposed, 10'-0\" required · " + words[7]["delta"]
    survey = items(check_site(_plot(box(7, 30, 35, 65)), {**FACTS, "jurisdiction": CITY})["view"])["Side yard, West"]
    assert (survey["delta"], survey["approx"]) == ("−3'-0\" short", False)
    # the notice and the report say the same words as the panel
    before = {i["id"]: i["status"] for i in check_site(_plot(box(16, 30, 35, 65)), tax)["view"]["items"]}
    now = check_site(_plot(box(7, 30, 35, 65)), tax)["view"]["items"]
    assert present.notice(before, now)[1].endswith("· " + words[7]["delta"])
    # round 2: settle is the ONLY writer of the Delta; nothing falls back to the as-drawn margin's words
    for path in ("packages/design_checker/design_checker/check.py", "packages/design_checker/design_checker/present.py"):
        assert "delta_text" not in (REPO / path).read_text(encoding="utf-8"), path
    assert "delta_text" not in host_text("rhino", "ui", purpose="wiring")


def test_delta_words_never_overstate():
    C, R, F = present.COMPLIES, present.REVIEW, present.FAILS
    assert present.delta_words(F, (-5.0, -1.0), "ft", True) == "at least 1'-0\" short"
    assert present.delta_words(F, (-5.0, -1.0 - 1 / 200), "ft", True) == "at least 1'-0\" short"   # rounded down
    assert present.delta_words(R, (-3.25, 1.75), "ft", True) == "up to 3'-3\" short"
    assert present.delta_words(R, (-3.25 + 1 / 200, 1.75), "ft", True) == "up to 3'-3\" short"    # rounded up
    assert present.delta_words(C, (0.0, 4.0), "ft", True) == "at the limit at worst"
    assert present.delta_words(C, (5.0, 9.0), "ft", True) == "≥ +5'-0\""                   # at least that, to spare
    assert present.delta_words(C, (7.0, 7.0), "ft", False) == "+7'-0\""                     # one reading: the margin
    assert present.delta_words(F, (-1.25, -1.25), "ft", False) == "−1'-3\" short"
    assert present.delta_words(C, None, "ft", False) == ""
    # never kinder than the status: room on a row that needs review is "if confirmed", never a bare "+"
    assert present.delta_words(R, (7.0, 7.0), "ft", False) == "+7'-0\" if confirmed"
    assert present.delta_words(R, (5.0, 9.0), "ft", True) == "≥ +5'-0\" if confirmed"
    # round 2: the certain words ("at least … short") only on a row that fails; one in review says to see why
    assert present.delta_words(R, (-5.0, -1.0), "ft", True) == "at least 1'-0\" short; see why"
    assert present.delta_words(R, (-1.0, -1.0), "ft", False) == "−1'-0\" short; see why"
    # room, yet it fails: never the "+" of a row that complies (panel-wording review round 1, P3)
    assert present.delta_words(F, (1.0, 1.0), "ft", False) == "1'-0\" room here; see why"
    assert present.delta_words(F, (2.0, 5.0), "ft", True) == "at least 2'-0\" room here; see why"
    # every unit: lot area in sf, coverage in % (round 1: "+570 sf to spare" on a lot area that needs review)
    assert present.delta_words(R, (-66.2, 570.4), "sf", True) == "up to 67 sf short"
    assert present.delta_words(F, (-1000.0, -384.6), "sf", True) == "at least 384 sf short"
    assert present.delta_words(C, (0.937, 6.2), "%", True) == "≥ +0.93%"
    assert present.delta_words(F, (-6.2, -0.004), "%", True) == "less than 0.01% short"


def test_a_maximum_passed_says_over_and_a_minimum_not_met_says_short():
    """Architect's review (2026-10-28): One-family occupancy (at most 1 family, 3 drawn) read "−2 short; see why"
    while its detail said "over by 2". A most (≤, <) passed reads "2 over", with its units ("1'-6" over", "120 sf
    over"), in every form; a least not met keeps "short" and its "−"."""
    C, R, F = present.COMPLIES, present.REVIEW, present.FAILS
    assert present.delta_words(R, (-2.0, -2.0), "count", False, maximum=True) == "2 over; see why"
    assert present.delta_words(F, (-1.5, -1.5), "ft", False, maximum=True) == "1'-6\" over"
    assert present.delta_words(F, (-120.0, -120.0), "sf", False, maximum=True) == "120 sf over"
    assert present.delta_words(F, (-5.0, -1.0), "ft", True, maximum=True) == "at least 1'-0\" over"
    assert present.delta_words(R, (-3.25, 1.75), "ft", True, maximum=True) == "up to 3'-3\" over"
    assert present.delta_words(F, (-6.2, -0.004), "%", True, maximum=True) == "less than 0.01% over"
    assert present.delta_words(C, (7.0, 7.0), "ft", False, maximum=True) == "+7'-0\""     # room reads the same
    assert present.delta_words(F, (-1.5, -1.5), "ft", False) == "−1'-6\" short"            # a minimum: unchanged
    # which it is comes from the rule's own comparison: building height is a most, a yard a least
    assert present._is_maximum(ast.parse("building_height <= 35", mode="eval").body)
    assert not present._is_maximum(ast.parse("rear_yard >= 25", mode="eval").body)


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


def test_only_what_rises_above_the_height_limit_is_coloured_a_roofs_ridge_not_its_eaves():
    """A roof sloping from 30 ft (at y 25) to 40 ft (at y 65) under a 35 ft limit: only the half of the plan where
    the roof is above 35 ft (y 45 to 65, 25 × 20 = 500 sf) is coloured, never the whole 1,000 sf footprint."""
    from shapely.geometry import Polygon
    from design_checker.check import plan
    from test_measure import sloped_roof_box
    site = _plot(sloped_roof_box(10, 25, 35, 65, 30, 40, "house"))
    env = {"outline": [[0, 0], [50, 0], [50, 100], [0, 100]], "top": 35, "base": 0}
    (top,) = plan(site, env, {"items": [{"measure": "building_height", "status": present.FAILS}]}, {})["encroach"]
    assert Polygon(top["outline"]).area == pytest.approx(500, abs=0.01)
    assert min(p[1] for p in top["outline"]) == pytest.approx(45)
    assert (top["base"], top["top"], top["building"]) == (35, 40, "house")


def test_a_building_over_the_limit_with_only_walls_above_it_is_still_coloured_over_its_own_plan():
    """Independent review of #28, P1: a vault or dome read as walls (its curved roof faces left out) rises over the
    limit with nothing above it seen from above; it was coloured nowhere. Never less than its own plan."""
    from shapely.geometry import Polygon
    from design_checker.check import plan
    house = box(10, 25, 35, 65, 0, 38)
    house["faces"] = [f for f in house["faces"] if not all(p[2] == 38 for p in f["points"])]   # its top left out
    env = {"outline": [[0, 0], [50, 0], [50, 100], [0, 100]], "top": 35, "base": 0}
    for status in (present.FAILS, present.REVIEW):
        tops = [e for e in plan(_plot(house), env, {"items": [{"measure": "building_height", "status": status}]},
                                {})["encroach"] if e["why"] == "height"]
        assert [(t["base"], t["top"], t["status"]) for t in tops] == [(35, 38, status)]
        assert Polygon(tops[0]["outline"]).area == pytest.approx(1000)


def test_a_vault_read_as_walls_beside_a_flat_roof_over_the_limit_is_coloured_too():
    """Review of the #28 fix (L1): one building whose flat roof part rises over the limit (seen from above) and a
    vault part read as walls also over it: the walls lie outside what is seen from above, so its whole plan."""
    from shapely.geometry import Polygon
    from design_checker.check import plan
    from test_measure import sloped_roof_box
    flat = box(10, 25, 20, 65, 0, 38)
    vault = box(20, 25, 35, 65, 0, 38)
    vault["faces"] = [f for f in vault["faces"] if not all(p[2] == 38 for p in f["points"])]
    house = {"id": "house", "faces": flat["faces"] + vault["faces"], "problems": []}
    env = {"outline": [[0, 0], [50, 0], [50, 100], [0, 100]], "top": 35, "base": 0}
    tops = [e for e in plan(_plot(house), env, {"items": [{"measure": "building_height", "status": present.FAILS}]},
                            {})["encroach"] if e["why"] == "height"]
    assert sum(Polygon(t["outline"]).area for t in tops) == pytest.approx(1000)        # the vault's 600 sf too
    for f in vault["faces"]:                     # the same vault, its walls' tops 1e-4 ft out of plumb
        for p in f["points"]:
            if p[2] == 38:
                p[0] += 1e-4                     # (both ways: every wall leans)
                p[1] += 1e-4
    house = {"id": "house", "faces": flat["faces"] + vault["faces"], "problems": []}
    tops = [e for e in plan(_plot(house), env, {"items": [{"measure": "building_height", "status": present.FAILS}]},
                            {})["encroach"] if e["why"] == "height"]
    assert sum(Polygon(t["outline"]).area for t in tops) == pytest.approx(1000, abs=0.1)
    gable = plan(_plot(sloped_roof_box(10, 25, 35, 65, 30, 40, "house")), env,
                 {"items": [{"measure": "building_height", "status": present.FAILS}]}, {})["encroach"]
    assert Polygon(gable[0]["outline"]).area == pytest.approx(500, abs=0.01)           # a roof's walls: still its ridge


def test_a_vault_springing_below_the_limit_gets_a_block_at_the_limit_for_rhino_to_reach_its_real_top():
    """Review of 2cae58d (F1): walls to 30 ft read, a curved vault to 42 ft left out: the checker's own top is
    under the 35 ft limit, so no block was made and nothing was coloured. Now a block over its plan at the limit
    (no height of its own here); Rhino reaches it to the real vault's top (rhino_logic.block_span)."""
    from shapely.geometry import Polygon
    from design_checker.check import check_site
    from model_measurement.stops import stop
    vault = box(10, 25, 35, 65, 0, 30)
    vault["faces"] = [f for f in vault["faces"] if not all(p[2] == 30 for p in f["points"])]
    vault["problems"] = [stop("curved_surface")]
    r = check_site(_plot(vault), {**FACTS, "jurisdiction": CITY})
    assert items(r["view"])["Building height"]["status"] == present.REVIEW
    tops = [e for e in r["plan"]["encroach"] if e["why"] == "height"]
    assert [(t["base"], t["top"]) for t in tops] == [(35, 35)]
    assert Polygon(tops[0]["outline"]).area == pytest.approx(1000)
    assert logic_span(tops[0], 0.0, 42.0) == (35, 42.0) and logic_span(tops[0], 0.0, 30.0) == (35, 35)


def logic_span(entry, bottom, top):
    from design_checker import rhino_logic
    return rhino_logic.block_span(entry, bottom, top)


def test_a_building_with_a_curved_surface_never_complies_on_height_and_is_coloured_above_the_limit():
    """The vault probe at fc0b023: walls to 36 ft read, the curved vault left out by the reader (a problem it reports):
    the height row needs review, never complies, and the block over the limit covers the building's plan (the
    Rhino side cuts the real vault from there: rhino_logic.block_span)."""
    from shapely.geometry import Polygon
    from design_checker.check import check_site
    from model_measurement.stops import stop
    vault = box(10, 25, 35, 65, 0, 36)
    vault["faces"] = [f for f in vault["faces"] if not all(p[2] == 36 for p in f["points"])]
    vault["problems"] = [stop("curved_surface")]
    r = check_site(_plot(vault), {**FACTS, "jurisdiction": CITY})
    assert items(r["view"])["Building height"]["status"] == present.REVIEW
    tops = [e for e in r["plan"]["encroach"] if e["why"] == "height"]
    assert tops and all(t["status"] == present.REVIEW for t in tops)
    assert sum(Polygon(t["outline"]).area for t in tops) == pytest.approx(1000)


def test_only_the_buildings_that_rise_above_the_limit_are_coloured_each_to_its_own_top():
    from shapely.geometry import Polygon
    from design_checker.check import plan
    site = _plot(box(10, 25, 35, 65, 0, 38, "house"), box(36, 70, 46, 80, 0, 12, "garage"))
    env = {"outline": [[0, 0], [50, 0], [50, 100], [0, 100]], "top": 35, "base": 0}
    tops = plan(site, env, {"items": [{"measure": "building_height", "status": present.FAILS}]}, {})["encroach"]
    assert [(t["base"], t["top"], round(Polygon(t["outline"]).area, 3)) for t in tops] == [(35, 38, 1000)]
    assert tops[0]["building"] == "house"                                     # the low garage: nothing


def test_a_yard_strip_is_cut_per_building_each_from_its_own_bottom_to_its_own_top():
    """A 30 ft house and a separate 10 ft wing both 2 ft from the west line, short of it under every reading by
    4 ft: each building gets its own strip, the wing's only up to the wing's own 10 ft (never the house's 30)."""
    from design_checker.check import plan
    site = _plot(box(2, 25, 20, 65, 0, 30, "house"), box(2, 68, 10, 80, 1, 10, "wing"))
    env = {"outline": [[10, 25], [40, 25], [40, 65], [10, 65]], "top": 35, "base": 0}
    item = {"measure": "side_yard_smaller", "status": present.FAILS, "colour": "red",
            "limits": [{"points": [[0, 40], [2, 40]], "near": 4, "far": 4}]}
    strips = plan(site, env, {"items": [item]}, {}, FACTS)["encroach"]
    assert sorted((e["base"], e["top"]) for e in strips) == [(0, 30), (1, 10)]     # the wing never to 30 ft
    got = sorted((e["building"], e["status"], e["base"], e["top"], round(max(p[0] for p in e["outline"]), 3))
                 for e in strips)
    assert got == [("house", present.FAILS, 0, 30, 4.0), ("wing", present.FAILS, 1, 10, 4.0)]


def test_the_colour_comes_from_the_result_only():
    """rhino_logic.highlight: the one place a result becomes a colour (the conduit draws only what it names)."""
    sys.path.insert(0, str(REPO / "packages/design_checker/design_checker"))
    import rhino_logic
    assert [rhino_logic.highlight(s) for s in (present.FAILS, present.REVIEW, present.COMPLIES, "not_checked", None)] \
        == ["red", "amber", None, None, None]
    src = host_text("rhino", "plugin", purpose="wiring")
    scene = src.split("def draw_scene(", 1)[1].split("\ndef ", 1)[0]
    # each part drawn in draw_scene's one loop, the red after the amber (merged with depth-lines, whose see-through
    # fills are pinned in the scene itself: test_depth)
    coloured = scene[scene.index("for g, status, _ in rest + red:"):]
    assert "name = logic.highlight(status)" in coloured and "colour = ui.HIGHLIGHT[name]" in coloured
    # drawn after the translucent envelope, so its blue never tints them (seen muddy in Rhino, 2026-10-21)
    assert scene.index("o.envelope, Rhino.Display.DisplayMaterial") < scene.index("for g, status, _ in rest + red:")
    ui = host_text("rhino", "ui", purpose="wiring")
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
    from model_measurement.places.ithaca_city.measure import TAX_MAP_SLACK, tax_map_lot_area
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
    # as drawn (6,570 sf), then short at the tax map's low end: never a bare "to spare" on a row in review
    assert area["delta"] == ("+570 sf if confirmed (" + present._area(6000 - tol["low"], "up") +
                             " short if the tax-map lines are 2 ft off)")
    cov = v["Lot coverage"]
    assert cov["approx"] and cov["status"] == present.FAILS
    head, tail = cov["delta"].split(" (", 1)
    assert head == cov["margin"].lstrip("−") + " over"                # as drawn, a most: past it is "over"
    assert tail.startswith("still ") and tail.endswith(" over if the tax-map lines are 2 ft off the other way)")
    assert tail.split()[1] != cov["margin"].lstrip("−")               # the certain excess, not the as-drawn one


def test_the_height_row_is_never_marked_tax_map_approximate(tax_map):
    """Round 1: the height's own comparison reads no lot length (only its bonus clause does): its Delta is its
    margin, and it is not "(approx.)"."""
    r = tax_map
    h = items(r["view"])["Building height"]
    assert h["approx"] is False and h["delta"] in ("at limit", h["margin"], h["margin"].lstrip("−") + " over")
    assert "tax map" not in h["detail"]["line"]


def test_red_and_amber_agree_with_the_rear_yards_own_readings():
    """Round 1: red and amber were the footprint against all yards grown by a flat 2'-0", while the rear verdict
    also moves the lot depth 4'-0" (its minimum by 1'-0"). Each yard's colours are now its own readings'."""
    from design_checker.check import check_site
    tax = {**FACTS, "jurisdiction": CITY, "lot_surveyed": False}
    r = check_site(_plot(box(10, 30, 35, 78.5)), tax)                 # rear wall 3'-6" over the drawn 25'-0"
    rear = items(r["view"])["Rear yard"]
    assert (rear["status"], rear["delta"]) == (    # 3'-6" short as drawn; still 0'-6" short at best
        present.FAILS, "3'-6\" short (still 0'-6\" short if the tax-map lines are 2 ft off the other way)")
    red = [g for g in r["plan"]["encroach"] if g["status"] == present.FAILS]
    (strip,) = red
    ys = [p[1] for p in strip["outline"]]
    assert min(ys) == pytest.approx(78.0, abs=0.01) and max(ys) == pytest.approx(78.5, abs=0.01)   # 0'-6" deep
    r = check_site(_plot(box(10, 30, 35, 72.5)), tax)                 # 2'-6" clear: needs review, "up to 0'-6" short"
    rear = items(r["view"])["Rear yard"]
    assert (rear["status"], rear["delta"], rear["colour"]) == (
        present.REVIEW, "+2'-6\" if confirmed (0'-6\" short if the tax-map lines are 2 ft off)", "amber")
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
    colour: a bare room ("+2'-0"", "≥ +3'-0"": to spare) only on a row that complies; the certain words ("at least
    … short", "less than … over", a survey's "−… short" or "… over") only on a row that fails, and on a yard always
    with red; a row that complies never says "short" or "over"; red only on a row that fails."""
    d, st = i.get("delta") or "", i["status"]
    if re.search(r" \(.*(" + re.escape(present.TAX_OFF) + r"( the other way)?|under every reading|under another "
                 r"reading)\)(; see why)?$", d):
        # a tax-map lot's Delta, or a span's (present.tax_delta): "<as drawn> (<the end that decides it> if the
        # tax-map lines are 2 ft off[ the other way] | under every reading | under another reading)": certain only
        # when short even at best ("still"), room bare only if it complies (review round 1 of plain-words: the
        # "under … reading" forms fell to the old words' checks)
        head, tail = d.split(" (", 1)
        certain = tail.startswith("still ") and not d.endswith("; see why")
        bare_room = head.startswith("+") and not head.endswith(" if confirmed")
        says_short = any(w in x for x in (head, tail) for w in (" short", " over"))
    else:
        certain = (d.endswith(" short") and d.startswith(("at least ", "less than ", "−"))) or (
            d.endswith(" over") and not d.startswith("up to "))
        bare_room = d.startswith(("+", "≥ +")) and not d.endswith(" if confirmed")
        says_short = d.endswith((" short", " over"))
    assert not bare_room or st == present.COMPLIES, (i["name"], st, d)
    assert not certain or st == present.FAILS, (i["name"], st, d)
    cell = i.get("delta_cell")              # the list's two-line form: never kinder than the status either
    if cell:
        assert st == present.COMPLIES or not (cell.startswith("+") and "−" not in cell and " short" not in cell
                                              and " over" not in cell), (i["name"], st, cell)
        assert st != present.FAILS or not cell.startswith("+"), (i["name"], st, cell)
        assert st == present.COMPLIES or not cell.startswith("worst +") or cell.endswith("\nif confirmed"), cell
    assert not (certain and i["measure"] in present.YARD_MEASURES) or i["colour"] == "red", (i["name"], i["colour"], d)
    assert st != present.COMPLIES or not says_short, (i["name"], st, d)
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
    # (#18 reads every lot-line reading of 106's real outline: the wider side is the one whose value is the open
    # question; the narrower is 9'-4 3/4" from the west line under every reading and fails)
    side = items(r["view"])["Side yard, wider"]
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
    # (#18 reads every lot-line reading of 106's real outline: the wider side is the one whose value is the open
    # question; the narrower is 9'-4 3/4" from the west line under every reading and fails)
    side = items(r["view"])["Side yard, wider"]
    assert side["status"] == present.REVIEW and (side["reason"] or "").startswith("Complies under every reading, but it depends on"), (
        side["status"], side["reason"])
    # never a bare "+", which is to spare: in the words ("+9'-6" if confirmed (at least … under every reading)") and
    # in the list's shorter form ("worst +9'-6"" over "if confirmed")
    assert side["delta"].split(" (", 1)[0].endswith(" if confirmed"), side["delta"]
    assert side["delta_cell"].endswith("\nif confirmed"), side["delta_cell"]
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
    own reason's short name. (PR #18 settles scenario 10's overhang in law, yards_to_nearest_part, so its side
    yard complies outright; scenario 09's rear yard turns on the lot-line question only.)"""
    from design_checker import scenarios
    from design_checker.check import check_site
    s, f, extras = scenarios.site(scenarios.load(scenarios.FOLDER / "09_five_sided_lot.yaml"))
    rear = {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}["Rear yard"]
    assert rear["reason"] == ("Complies under every reading, but it depends on an open question: which lot lines "
                              "count as side and which as rear; confirm with the zoning office")
    rule = {"id": "x", "kind": "rule", "check": "side_yard_smaller >= 10 or side_yard_larger >= 10"}
    measured = {"side_yard_smaller": {"value": None, "readings": [{"reading": "r", "value": 12}, {"reading": "s", "value": 15}]},
                "side_yard_larger": {"value": None, "readings": [{"reading": "r", "value": 12}, {"reading": "s", "value": 15}]}}
    from design_checker.check import turns_on
    assert turns_on(rule, measured, {}) == []                    # either one decides it: it turns on neither


def test_every_open_question_the_measuring_asks_has_a_short_name():
    """One table: every tagged question in the measuring code, and every untagged one it keeps as a constant."""
    import re
    from pathlib import Path
    from model_measurement.places.ithaca_city import measure
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


_LAWS_ONCE = {}


@pytest.fixture
def same_laws(monkeypatch):
    """Many-house tests read the place's laws once, in the test only (the checker keeps no cache: one was tried
    and taken out for stale-law bugs, docs/decisions/2026-11-23_laws_validation_speed.md). check_site asks
    egress.laws for them on every call, and that re-checks the state law's whole rulebook each time (about 70% of
    a call); between two houses it can't change (the same place, no file touched), so every check_site here is the
    real one, run on laws read by the real egress.laws, each call getting its own deep copy (a deep copy shares
    functions, so each law's section lookup and its table are shared; nothing writes to them, and the guard
    below compares the table). Only for CITY; any other place is read as usual. It can't hide a stale-law bug:
    these tests check the advice, not the reading of the laws, and after each test a fresh read must still
    equal the reused one (a file changed, a shared table changed, or a result captured under another test's
    patch, fails)."""
    from design_checker import egress
    real = egress.laws
    if CITY not in _LAWS_ONCE:
        _LAWS_ONCE[CITY] = real(CITY)
    monkeypatch.setattr(egress, "laws",
                        lambda j: copy.deepcopy(_LAWS_ONCE[CITY]) if j == CITY else real(j))
    yield
    assert _by_value(real(CITY)) == _by_value(_LAWS_ONCE[CITY]), "the laws reused are no longer a fresh read's"


def _by_value(found):
    """egress.laws's answer with each law's `section_of` (a new function on every read) as the code and the table
    it reads, so two reads compare by what they hold."""
    return {**found, "laws": [{**law, "section_of": law["section_of"] and (
        law["section_of"].__code__, [c.cell_contents for c in law["section_of"].__closure__])}
        for law in found["laws"]]}


def test_two_reads_of_the_laws_compare_equal_and_a_changed_one_does_not():
    """same_laws's guard really compares: a second read equals the first, and one changed section table, rule or
    problem doesn't."""
    import types
    from design_checker import egress
    a, b = egress.laws(CITY), egress.laws(CITY)
    assert a != b and _by_value(a) == _by_value(b)                 # plain == fails only on the new function
    n, law = next((n, law) for n, law in enumerate(a["laws"]) if law["section_of"] and law["rules"])
    f = law["section_of"]
    (spans,) = [c.cell_contents for c in f.__closure__]
    changed = {**spans, next(iter(spans)): []}
    other = types.FunctionType(f.__code__, f.__globals__, f.__name__, f.__defaults__, (types.CellType(changed),))

    def with_law(**change):
        return {**a, "laws": [{**x, **change} if i == n else x for i, x in enumerate(a["laws"])]}
    assert _by_value(with_law(section_of=other)) != _by_value(a)
    assert _by_value(with_law(rules=law["rules"][1:])) != _by_value(a)
    assert _by_value(with_law(problems=["stale"])) != _by_value(a)


def _random_houses():
    """The 80 random houses, drawn from Random(21) in the order the single test drew them (a fixed list, so any
    chunk of it is the same houses): (k, surveyed, x0, y0, x1, y1, height)."""
    rnd = random.Random(21)
    out = []
    for k in range(80):
        x0, y0 = rnd.uniform(4, 14), rnd.uniform(18, 30)
        x1, y1 = rnd.uniform(36, 47), rnd.uniform(70, 82)
        out.append((k, k % 2 == 0, x0, y0, x1, y1, rnd.choice((30, 35, 36.5, 38))))
    return out


# The 80 houses run in 8 chunks of 10 (as one test they took about 913 s on CI, past its 900 s per-test limit).
# Each chunk asserts its share: at least 2 hints followed on a survey and 2 on the tax map (8 x 2 = 16, the whole
# test's 15 or more on each; a run of all 80 followed 12-20 of each per chunk), and every kind the whole test
# required that a run of all 80 found in that chunk (the "if it stays tall" figure only in house 78), so each
# required kind is still required of a chunk that has it (checked below, without running a house).
_CHUNKS = {f"houses_{a:02d}_{a + 9:02d}": range(a, a + 10) for a in range(0, 80, 10)}
_EACH_TRIED = 2
_KINDS_REQUIRED = {("need", True), ("need", False), ("lower", False), ("tall", False)}
_KINDS_IN = {**dict.fromkeys(_CHUNKS, {("need", True), ("need", False), ("lower", False)}),
             "houses_70_79": _KINDS_REQUIRED}


def test_the_house_chunks_cover_all_80_houses_and_every_kind_the_whole_test_required():
    """The split keeps the single test's guarantee: every house is in exactly one chunk, the chunks' "followed"
    shares add up to at least 15 on each kind of lot, and every required kind is asserted by some chunk."""
    ks = sorted(k for r in _CHUNKS.values() for k in r)
    assert ks == list(range(80)) == [h[0] for h in _random_houses()]
    assert _EACH_TRIED * len(_CHUNKS) >= 15
    assert set(_KINDS_IN) == set(_CHUNKS) and _KINDS_REQUIRED <= set().union(*_KINDS_IN.values())


def _feet(text):
    """4'-11 3/8" -> 4.921875 (feet_inches read back)."""
    import re
    ft, inch, frac = re.fullmatch(r"(\d+)'-(\d+)(?: (\d+/\d+))?\"", text).groups()
    num, den = (frac or "0/1").split("/")
    return int(ft) + (int(inch) + int(num) / int(den)) / 12


def _follow_to_comply(houses):
    """For each house, check it, then do exactly what each yard or height row's "To comply" says and check again:
    that row must COMPLY and no row get worse. Returns (followed on a survey / on the tax map, kinds followed)."""
    from design_checker.check import check_site
    from test_measure import lot as lot_of
    plain = lot_of([(0, 0), (50, 0), (50, 100), (0, 100)])
    pull = {"Side yard, West": (1, 0), "Side yard, East": (-1, 2), "Front yard": (1, 1), "Rear yard": (-1, 3)}
    lines = {"Side yard, West": "the west side lot line", "Side yard, East": "the east side lot line",
             "Front yard": "the front lot line", "Rear yard": "the rear lot line"}
    one = r"(\d+'-\d+(?: \d/\d)?\")"
    raises = r"\(the building height rule's other way raises this yard\)"
    tall = r"if it stays \d+'-\d+(?: \d/\d)?\" tall"
    yard = re.compile(r"keep every part of the building at least " + one + r" from (.+?)(?: as drawn \(" + one +
                      r" required, the lot lines ±2'-0\"\)| \(" + one + r" required, under every reading\))? — now " +
                      one + r" at its closest(?:; at least " + one + " " + tall + " " + raises + ")?")
    alone = re.compile(tall + r", keep every part of the building at least " + one + r" from (.+?) " + raises +
                       r" — now " + one + " at its closest")
    lower = re.compile(r"lower the building " + one)
    deeper = re.compile(r"make the (front yard|rear yard|side yard) " + one + r"(?: \(" + one +
                        r" as drawn\))? deeper, keeping the other yards")
    tried = {True: 0, False: 0}
    kinds = set()
    for k, surveyed, x0, y0, x1, y1, h in houses:
        facts = {**FACTS, "jurisdiction": CITY, "lot_surveyed": surveyed}
        rows = {i["name"]: i for i in check_site(_plot(box(x0, y0, x1, y1, 0, h), lot_=plain), facts)["view"]["items"]}

        def follow(c, hh, name, what):
            again = {j["name"]: j for j in check_site(_plot(box(*c, 0, hh), lot_=plain), facts)["view"]["items"]}
            assert again[name]["status"] == present.COMPLIES, (k, name, what, again[name]["status"], again[name]["reason"])
            worse = [(n, rows[n]["status"], j["status"]) for n, j in again.items()
                     if n in rows and {j["status"], rows[n]["status"]} <= set(present.RANK) and present.RANK[j["status"]] < present.RANK[rows[n]["status"]]]
            assert not worse, (k, name, what, worse)
            tried[surveyed] += 1

        for name, i in rows.items():
            hint = i.get("hint") or ""
            if not hint.startswith("To comply") or not (name in pull or name == "Building height"):
                continue
            head, _, body = hint.partition(": ")
            assert head in ("To comply", "To comply whatever the survey shows") and body.endswith("."), (k, name, hint)
            body = body[:-1]
            if name in pull:
                m, a = yard.fullmatch(body), alone.fullmatch(body)
                assert m or a, (k, name, hint)
                if m:
                    target, line, req, tall_t = m.group(1), m.group(2), m.group(3) or m.group(4), m.group(6)
                    figures = [(target, "need"), (tall_t, "tall")]
                else:
                    target, line, req, tall_t = a.group(1), a.group(2), None, None
                    figures = [(target, "tall alone")]
                assert line == lines[name], (k, name, hint)
                if surveyed:
                    assert head == "To comply" and req is None, (k, name, hint)
                if req:                              # the requirement beside the as-drawn target, never above it
                    assert _feet(req) < _feet(target) and head.endswith("survey shows"), (k, name, hint)
                sign, at = pull[name]
                now = {"Side yard, West": x0, "Side yard, East": 50 - x1, "Front yard": y0, "Rear yard": 100 - y1}[name]
                for figure, kind in figures:
                    if figure:                       # every part at least that far: the near wall pulled in to it
                        c = [x0, y0, x1, y1]
                        c[at] += sign * (_feet(figure) - now)
                        follow(c, h, name, (kind, figure))
                        kinds.add((kind, bool(req)))
            else:
                for part in body.split(", or "):
                    m, d = lower.fullmatch(part), deeper.fullmatch(part)
                    assert m or d, (k, name, part)
                    if m:
                        follow([x0, y0, x1, y1], h - _feet(m.group(1)), name, part)
                        kinds.add(("lower", False))
                    else:
                        c = [x0, y0, x1, y1]
                        side = "Side yard, West" if x0 <= 50 - x1 else "Side yard, East"
                        sign, at = pull[side if d.group(1) == "side yard" else d.group(1).capitalize()]
                        c[at] += sign * _feet(d.group(2))
                        follow(c, h, name, part)
                        kinds.add(("deeper", bool(d.group(3))))
    return tried, kinds


@pytest.mark.parametrize("chunk", list(_CHUNKS))
def test_doing_what_to_comply_says_makes_that_row_comply_on_the_tax_map_and_on_a_survey(chunk, same_laws):
    """The architect's review (pass 2, P1): on a tax-map lot "To comply" gave the shortfall as drawn, and moving
    by it left the side yard needing review. The advice comes from the verdict's own reading set and the checker
    confirms each piece (check.confirm_advice). For random houses on the plain lot, tax map and survey, doing
    exactly what a row's "To comply" says (a yard: that wall pulled back by the figure, the house's height kept; the
    height: the roof lowered, or the front yard made deeper) makes that row COMPLY and leaves no row worse (review
    round 4: a whole-building move it said before broke other yards). The 80 houses run in 8 chunks, each asserting
    its own share of the coverage (_CHUNKS); the wording, word for word, is the next test."""
    houses = [h for h in _random_houses() if h[0] in _CHUNKS[chunk]]
    tried, kinds = _follow_to_comply(houses)
    assert tried[True] >= _EACH_TRIED and tried[False] >= _EACH_TRIED, tried   # both kinds of lot really exercised
    assert _KINDS_IN[chunk] <= kinds, (chunk, kinds)


def test_to_comply_says_the_requirement_word_for_word_and_doing_it_makes_the_row_comply(same_laws):
    """The wording, the coordinator's: the requirement first, "keep every part of the building at least 12'-0" from
    the west side lot line as drawn (10'-0" required, the lot lines ±2'-0") — now 7'-0 5/8" at its closest"; on the
    tax map "whatever the survey shows" and the as-drawn figure, on a survey one number; a yard the height bonus
    raises also says what it needs "if it stays 36'-6" tall", or that alone when its own figure wouldn't do while it
    stays that tall. (Split from the 80 random houses above for time, every assert kept.) Plus the fixed cases
    review rounds found (a lot's own size, the raised yard, G1 and G3)."""
    from design_checker.check import check_site
    from test_measure import lot as lot_of
    plain = lot_of([(0, 0), (50, 0), (50, 100), (0, 100)])
    # the coordinator's case, word for word: a west side yard 2'-11 3/8" short as drawn; and the others
    words = {}
    for surveyed in (False, True):
        for b in ((7.053, 26, 38, 72, 30), (16, 20, 34, 66, 36.5)):
            r = check_site(_plot(box(*b[:4], 0, b[4]), lot_=plain), {**FACTS, "jurisdiction": CITY, "lot_surveyed": surveyed})
            words.update({(surveyed, b[4], i["name"]): i.get("hint") for i in r["view"]["items"]})
    # the requirement, never one wall's move (review round 5, P2: on a stepped front the next wall stayed short)
    assert words[(False, 30, "Side yard, West")] == (
        "To comply whatever the survey shows: keep every part of the building at least 12'-0\" from the west side lot "
        "line as drawn (10'-0\" required, the lot lines ±2'-0\") — now 7'-0 5/8\" at its closest.")
    assert words[(True, 30, "Side yard, West")] == (
        "To comply: keep every part of the building at least 10'-0\" from the west side lot line — now 7'-0 5/8\" at its "
        "closest.")
    assert words[(False, 30, "Front yard")] == (                       # in review as drawn: what makes it comply
        "To comply whatever the survey shows: keep every part of the building at least 27'-0\" from the front lot line "
        "as drawn (25'-0\" required, the lot lines ±2'-0\") — now 26'-0\" at its closest.")
    assert words[(False, 36.5, "Building height")] == (
        "To comply whatever the survey shows: lower the building 1'-6\", or make the front yard 8'-6\" (6'-6\" as drawn) "
        "deeper, keeping the other yards.")
    assert words[(True, 36.5, "Building height")] == ("To comply: lower the building 1'-6\", or make the front yard 6'-6\" "
                                                      "deeper, keeping the other yards.")
    # tax map: its own 7'-0" wouldn't do while it stays 36'-6" tall (the bonus then raises it): that figure alone
    assert words[(False, 36.5, "Front yard")] == (
        "To comply whatever the survey shows: if it stays 36'-6\" tall, keep every part of the building at least 28'-6\" "
        "from the front lot line (the building height rule's other way raises this yard) — now 20'-0\" at its closest.")
    tax = {**FACTS, "jurisdiction": CITY, "lot_surveyed": False}       # that figure alone, followed: the front wall
    before = {i["name"]: i["status"] for i in check_site(_plot(box(16, 20, 34, 66, 0, 36.5), lot_=plain), tax)["view"]["items"]}
    after = {i["name"]: i["status"] for i in check_site(_plot(box(16, 28.5, 34, 66, 0, 36.5), lot_=plain), tax)["view"]["items"]}
    assert after["Front yard"] == present.COMPLIES and all(                # 8'-6" back, the house still 36'-6"
        present.RANK[after[n]] >= present.RANK[s] for n, s in before.items() if {s, after.get(n)} <= set(present.RANK))
    assert words[(True, 36.5, "Front yard")] == (
        "To comply: keep every part of the building at least 25'-0\" from the front lot line — now 20'-0\" at its "
        "closest; at least 26'-6\" if it stays 36'-6\" tall (the building height rule's other way raises this yard).")
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
    assert raised[27]["hint"] == (
        "To comply whatever the survey shows: keep every part of the building at least 28'-6\" from the front lot line as "
        "drawn (26'-6\" required, the lot lines ±2'-0\") — now 27'-0\" at its closest.")
    assert raised[28.5]["status"] == present.COMPLIES                          # 27 + 1'-6"
    # review round 4: G1, a lot narrowing away from the street: the front wall pulled back, the side yards kept
    # (moving the whole house had failed both); G3: the "if it stays tall" figure isn't offered when the other
    # yards it raises would then fall short (lowering the roof fixes all of them, and says so)
    trap = lot_of([(0, 0), (60, 0), (40, 90), (20, 90)])
    r = check_site(_plot(box(22, 22, 38, 50, 0, 30), lot_=trap),
                   {**FACTS, "jurisdiction": CITY, "lot_surveyed": True, "street_line": [[[0, 0], [60, 0]]]})
    assert next(i for i in r["view"]["items"] if i["name"] == "Front yard")["hint"] == \
        "To comply: keep every part of the building at least 25'-0\" from the front lot line — now 22'-0\" at its closest."
    r = check_site(_plot(box(12.326, 24.997, 34.441, 63.134, 0, 36.5), lot_=plain),
                   {**FACTS, "jurisdiction": CITY, "lot_surveyed": False})
    g3 = {i["name"]: i.get("hint") for i in r["view"]["items"]}
    assert g3["Front yard"] is None and g3["Building height"] == "To comply: lower the building 1'-6\".", g3


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
                assert not (i.get("hint") or "").startswith("To comply"), (shift, i["name"], turns, i.get("hint"))
    # (with PR 18 a whole floor moved past the walls is part of the building, never an eave: scenario 10's east
    # side yard is measured to it, no open question, and fails with its own To comply. The wall-or-overhang
    # question is now an overhang that may be an eave (§325-18B, test_every_reading): the side yard to the walls
    # 11 ft, to the full outline 9 ft, needs review until the architect confirms it; no move settles it)
    sys.path.insert(0, str(REPO / "packages/design_checker/tests"))
    from test_every_reading import CONFIRMED_HOUSE, floors, roof, run
    for shift in (0, -0.5, -1):
        x0, y0, x1, y1 = CONFIRMED_HOUSE
        r = run(floors(x0 + shift, y0, x1 + shift, y1, 2) + [roof(x0 + shift, y0, x1 + shift, y1, 20, 28, 2.0, 0)])
        rows = {x["Rule id"]: x for x in r["rows"]}
        for i in r["view"]["items"]:
            row = rows.get(i.get("rule")) or {}
            turns = (row.get("Side turns on") or {}).get(i.get("measure")) if i.get("measure") in (row.get("Sides") or {}) \
                else row.get("Turns on")
            if turns and i.get("measure") in turns and i["status"] != present.COMPLIES:
                seen += i["name"] == "Side yard, West"
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
    # (PR 18: 106's lot lines read from its outline cleaned within 0.25 ft, every reading of which are side and
    # rear: the limit runs 24'-1 7/8" to 32'-10 1/8"; the rear wall is 19'-6" to 20'-3 1/2" back, short even with
    # the tax map's lines 2 ft in its favour: does not comply on the tax map too)
    for surveyed, status in ((False, present.FAILS), (True, present.FAILS)):
        r = check_site(_plot(house, lot_=lot), {**facts, "lot_surveyed": surveyed})
        rear = items(r["view"])["Rear yard"]
        assert rear["status"] == status and rear["required"] == "24'-1 7/8\" to 32'-10 1/8\"", rear
        assert rear["reason"].count("which lot lines") == 1, rear["reason"]
        assert "readings give different values" not in rear["reason"] and "isn't settled" not in rear["reason"]
    assert rear["reason"].startswith("Does not comply whichever way it is read: needs 24'-1 7/8\"")


def test_coverage_with_an_upper_floor_overhang_is_read_as_seen_from_above_and_says_the_reading():
    """Architect review in Rhino (P2-10) asked that coverage turning on the overhang question say it once. PR 18
    settles that question: research reads coverage as everything above ground seen from above
    (coverage_seen_from_above), cantilevered upper floors included. So a floor block overhanging the one below
    counts: 28.5% does not comply, 22.8% complies, each saying the reading it applied (Gordium's reading, to
    confirm)."""
    from design_checker.check import check_site
    lot, facts = _sample106()
    ground = box(12, 30, 40, 70, 0, 10, "a")
    r = check_site(_plot(ground, box(12, 30, 62, 70, 10, 20, "b"), lot_=lot),
                   {**facts, "lot_surveyed": True, "main_building": "a"})
    cov = items(r["view"])["Lot coverage"]
    # (PR 18: research settled it as Gordium's reading coverage_seen_from_above, everything above ground seen from
    # above, cantilevered upper floors included: 28.5%, over 25%, does not comply, saying the reading it applied)
    assert cov["status"] == present.FAILS and cov["proposed"] == "28.5%", cov
    assert "Gordium's reading" in cov["reason"] and "seen from above" in cov["reason"], cov["reason"]
    r = check_site(_plot(ground, box(12, 30, 52, 70, 10, 20, "b"), lot_=lot),
                   {**facts, "lot_surveyed": True, "main_building": "a"})
    cov = items(r["view"])["Lot coverage"]
    assert cov["status"] == present.COMPLIES and "Gordium's reading" in cov["reason"], cov


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
    reading" for "Needs … ask the zoning office"; coverage failing both ways still said "an open question … ask".
    (PR 18: the sample lot's depth readings are 96.62, 131.37 and 101.79 ft, so the limit, 25% of the depth, runs
    24'-1 7/8" to 32'-10 1/8", as in the rear-yard test above; coverage is read as seen from above, its overhang
    question settled, so a coverage failing has no question left to ask about.)"""
    from design_checker.check import check_site
    lot, facts = _sample106()
    r = check_site(_plot(box(12, 30, 40, 50, 0, 30), lot_=lot), {**facts, "lot_surveyed": False})
    rear = items(r["view"])["Rear yard"]
    assert rear["required"] == "24'-1 7/8\" to 32'-10 1/8\"" and rear["reason"].startswith("Complies under every reading"), rear
    r = check_site(_plot(box(12, 30, 48, 85, 0, 10, "a"), box(10, 28, 50, 90, 10, 20, "b"), lot_=lot),
                   {**facts, "lot_surveyed": True, "main_building": "a"})
    cov = items(r["view"])["Lot coverage"]
    assert cov["status"] == present.FAILS and "ask" not in cov["reason"], cov



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
        from model_measurement.places.ithaca_city.measure import measure
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
    from model_measurement.places.ithaca_city.measure import measure
    def with_others(f):
        return next(r["value"] for r in measure(site_, f)["building_height"]["readings"]
                    if r["reading"].startswith("with every other solid"))
    assert with_others(base) == pytest.approx(with_others({**base, "main_building": "f0"})) == pytest.approx(35.8)
    picked = items(check_site(site_, {**base, "main_building": "f0"})["view"])["Building height"]
    assumed = items(check_site(site_, base)["view"])["Building height"]
    assert picked["status"] != present.COMPLIES, picked
    assert present.RANK[assumed["status"]] <= present.RANK[picked["status"]], (assumed, picked)


def test_never_kinder_than_picking_the_starting_house_with_solids_touching_it():
    """The main-building property (round 2) with #18's touching candidates in it (§325-18A: a solid touching the
    house is part of it, one main_only candidate). Random layouts on the sample lot: the starting house, and one or
    two other solids, each on its own ground with spot grades at every wall, often touching the house (on its east
    or north wall) and often standing apart. Left to Gordium, no row is ever kinder than with the starting house
    picked, and the pick's every height and story reading is among Gordium's own."""
    import random
    from design_checker.check import check_site
    from model_measurement.places.ithaca_city.measure import measure
    from test_measure import floor
    lot, facts = _sample106()
    rnd = random.Random(18)
    compared = touching = 0
    for _ in range(30):
        floors, h = rnd.choice([2, 3, 3]), rnd.choice([11, 11.6])
        house = [floor(12, 30, 36, 60, z0=h * i, z1=h * (i + 1), id=f"f{i}") for i in range(floors)]
        points = _walls_spots(12, 30, 36, 60, 0)
        others, spots = [], []
        for _k in range(rnd.choice([1, 2, 2])):
            x0, y0 = rnd.choice([(36, 30), (36, 48), (14, 60), (26, 60), (40, 30), (14, 66), (40, 66)])
            if any(not (x0 + 8 <= o[0] or o[0] + 8 <= x0 or y0 + 10 <= o[1] or o[1] + 10 <= y0) for o in spots):
                continue                                # never overlapping another solid
            ground, top = (0 if (x0 == 36 or y0 == 60) and rnd.random() < 0.5 else
                           rnd.choice([-8, -6, -3, 0, 3, 5, 8])), rnd.choice([8, 12, 20, 30, 40])
            spots.append((x0, y0))
            touching += x0 == 36 or y0 == 60
            others.append(box(x0, y0, x0 + 8, y0 + 10, ground, ground + top, f"o{x0}_{y0}"))
            points += _walls_spots(x0, y0, x0 + 8, y0 + 10, ground)
        base = {**facts, "lot_surveyed": True, "stories": floors, "ground_is_flat": None, "grade_elevation": None,
                "grade_points": points}
        site_ = _plot(*house, *others, lot_=lot)
        m_a, m_p = measure(site_, base), measure(site_, {**base, "main_building": "f0"})
        for name in ("building_height", "stories"):

            def vals(r):
                return {round(x["value"], 3) for x in r["readings"]} or (
                    {round(r["value"], 3)} if r["value"] is not None else set())
            assert vals(m_p[name]) <= vals(m_a[name]) or not vals(m_a[name]), (name, m_p[name], m_a[name])
        assumed = items(check_site(site_, base)["view"])
        picked = items(check_site(site_, {**base, "main_building": "f0"})["view"])
        for name, i in picked.items():
            if name in assumed and i["status"] in present.RANK and assumed[name]["status"] in present.RANK:
                compared += 1
                assert present.RANK[assumed[name]["status"]] <= present.RANK[i["status"]], \
                    (name, assumed[name]["status"], i["status"], assumed[name]["reason"], spots)
    assert compared > 150 and touching >= 10, (compared, touching)


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
        m = re.match(r"To comply[^:]*: (?:if it stays [^,]+, )?keep every part of the building at least "
                     r"(\d+'-\d+(?: \d/\d)?\") from the front lot line", front)
        tall = re.search(r"; at least (\d+'-\d+(?: \d/\d)?\") if it stays", front)   # the house stays this tall:
        now = re.search(r"now (\d+'-\d+(?: \d/\d)?\") at its closest", front)       # that figure; the front
        if m and now and items["Front yard"].get("points"):  # wall pulled in to it, along the line measured on
            gap = _feet((tall or m).group(1)) - _feet(now.group(1))
            (ax, ay), (bx, by) = items["Front yard"]["points"][:2]
            mid = ((x0 + x1) / 2, (y0 + y1) / 2)
            if (ax - mid[0]) ** 2 + (ay - mid[1]) ** 2 > (bx - mid[0]) ** 2 + (by - mid[1]) ** 2:
                (ax, ay), (bx, by) = (bx, by), (ax, ay)          # a: on the wall, b: on the street line
            n = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
            ux, uy = (ax - bx) / n, (ay - by) / n
            c = (x0, y0 + gap / abs(uy), x1, y1)            # only its front wall pulled back, the rest kept
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
    assert fy["hint"] == ("To comply: keep every part of the building at least 25'-0\" from the front lot line — now "
                          "20'-0\" at its closest."), fy["hint"]


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

    assert front()["hint"] == ("To comply whatever the survey shows: keep every part of the building at least 28'-6\" "
                               "from the front lot line as drawn (26'-6\" required, the lot lines ±2'-0\") — now 27'-0\" "
                               "at its closest.")
    real = present.comply_hint

    def tenth(*a, **k):                  # every advised change a tenth of what it says
        advice = real(*a, **k)
        for way in (advice or {}).get("ways") or []:
            way["changes"] = {m: d / 10 for m, d in way["changes"].items()}
        return advice

    monkeypatch.setattr(present, "comply_hint", tenth)
    got = front()
    assert got["status"] == present.REVIEW and got["hint"] is None, got["hint"]


def test_a_yards_advice_is_its_requirement_for_every_part_never_one_walls_move():
    """Review round 4 (G2) and round 5 (P2): a yard's advice is the requirement every part of the building must meet,
    "keep every part of the building at least 28'-6" from the front lot line … — now 27'-0" at its closest", never
    "pull the front wall back": on a stepped front the next wall in stays short. Following it puts the closest part
    at the target, which is what the checker re-decides (check.confirm_advice), every row with it: the raised rear
    yard of a 36'-6" house isn't made worse (G2), and no "at its closest point" guesswork about which wall."""
    from design_checker.check import check_site
    from test_measure import lot as lot_of
    plain = lot_of([(0, 0), (50, 0), (50, 100), (0, 100)])
    facts = {**FACTS, "jurisdiction": CITY, "lot_surveyed": False}
    r = check_site(_plot(box(15, 27, 35, 70.5, 0, 36.5), lot_=plain), facts)
    items = {i["name"]: i for i in r["view"]["items"]}
    assert items["Front yard"]["hint"] == (
        "To comply whatever the survey shows: keep every part of the building at least 28'-6\" from the front lot line as "
        "drawn (26'-6\" required, the lot lines ±2'-0\") — now 27'-0\" at its closest.")
    after = {i["name"]: i for i in check_site(_plot(box(15, 28.5, 35, 70.5, 0, 36.5), lot_=plain), facts)["view"]["items"]}
    assert after["Front yard"]["status"] == present.COMPLIES
    assert all(present.RANK[after[n]["status"]] >= present.RANK[i["status"]] for n, i in items.items()
               if n in after and {after[n]["status"], i["status"]} <= set(present.RANK))
    hints = [i.get("hint") or "" for i in r["view"]["items"]]
    assert not any("pull the" in h or "wall back" in h or "this yard needs" in h for h in hints), hints

def test_each_safeguard_on_the_if_it_stays_tall_figure_holds_on_its_own(monkeypatch):
    """Review round 4, G3, two safeguards, each pinned alone. (1) The "…if it stays 36'-6" tall" figure is shown
    only when the height rule then complies: with the side yards already failing, the bonus can never hold, so the
    figure would be false though no row gets worse. (2) No piece of advice is kept if it leaves any row worse: with
    the height rule's check taken off the clause, following it on the G3 house puts its side yards in review."""
    from design_checker.check import check_site
    from test_measure import lot as lot_of
    plain = lot_of([(0, 0), (50, 0), (50, 100), (0, 100)])
    tax = {**FACTS, "jurisdiction": CITY, "lot_surveyed": False}
    r = check_site(_plot(box(7, 20, 43, 66, 0, 36.5), lot_=plain), tax)          # (1) sides 7'-0": failing
    rows = {i["name"]: i for i in r["view"]["items"]}
    assert rows["Side yard, West"]["status"] == present.FAILS
    assert "if it stays" not in (rows["Front yard"].get("hint") or ""), rows["Front yard"].get("hint")
    real = present._while_raised

    def unchecked(*a, **k):                               # (2) the clause without the height rule's own check
        got = real(*a, **k)
        return dict(got, also=[]) if got else got

    monkeypatch.setattr(present, "_while_raised", unchecked)
    r = check_site(_plot(box(12.326, 24.997, 34.441, 63.134, 0, 36.5), lot_=plain), tax)
    front = next(i for i in r["view"]["items"] if i["name"] == "Front yard")
    assert "if it stays" not in (front.get("hint") or ""), front.get("hint")



def _degenerate(kind, problem):
    """A building object as a model can hold one: walls only (an open polysurface), a single face, a face of no
    area, points in a line, or no faces; with the reading's own problem, or (a defence) without one."""
    b = box(40, 70, 48, 80, 0, 10, "odd")
    if kind == "walls":
        b["faces"] = [f for f in b["faces"] if len({round(p[2], 6) for p in f["points"]}) > 1]
    elif kind == "one_face":
        b["faces"] = b["faces"][:1]
    elif kind == "zero_area":
        b["faces"] = [{"points": [[40, 70, 0], [40, 70, 0], [40, 70, 0]]}] + b["faces"][1:]
    elif kind == "collinear":
        b["faces"] = [{"points": [[40, 70, 0], [44, 70, 0], [48, 70, 0]]}]
    elif kind == "none":
        b["faces"] = []
    if problem:
        b["problems"] = ["a building isn't a closed solid"]
    return b


@pytest.mark.parametrize("kind", ["walls", "one_face", "zero_area", "collinear", "none"])
def test_a_degenerate_building_object_never_raises_and_never_passes(kind):
    """Main-building round 3 (P1): a building object of walls only crashed the ground check (an empty convex
    hull) when spot grades were set, before its own problem could stop the building measurements. Fuzz: every
    degenerate object, alone or beside a good house, with or without spot grades and with or without its
    reading's problem, goes through measure() and check_site without an exception, and with its problem, the
    building measurements wait with that reason."""
    from design_checker.check import check_site
    from model_measurement.places.ithaca_city.measure import measure
    from test_measure import floor
    lot, facts = _sample106()
    for house in (False, True):
        for spots in (False, True):
            for problem in (False, True):
                blds = ([floor(12, 30, 36, 60, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
                        if house else []) + [_degenerate(kind, problem)]
                f = {**facts, "lot_surveyed": True, "stories": 3}
                if spots:
                    f.update(ground_is_flat=None, grade_elevation=None,
                             grade_points=_walls_spots(12, 30, 36, 60, 0) + _walls_spots(40, 70, 48, 80, 0))
                m = measure(_plot(*blds, lot_=lot), f)
                view = check_site(_plot(*blds, lot_=lot), f)["view"]
                # with or without the reader's problem (round 4: the measuring finds it itself), the degenerate
                # object stops the building measurements, and no building row complies
                for name in ("building_height", "front_yard"):
                    assert m[name]["value"] is None and "isn't a closed solid" in (m[name]["reason"] or "") or \
                        kind == "none" and "nothing to measure" in (m[name]["reason"] or ""), (name, problem, m[name])
                built = [i for i in view["items"] if i.get("group") == "building" and i["status"] == present.COMPLIES]
                assert not built, (kind, house, spots, problem, [i["name"] for i in built])



def test_the_ground_work_waits_for_buildings_that_can_be_measured(monkeypatch):
    """Main-building round 4 (P3): the guards keeping the grade plane and the ground check off a building the
    reading refused were unpinned. With them raising, a problem building's measurement still returns."""
    import model_measurement.places.ithaca_city.measure as M
    from test_measure import floor

    def boom(*a, **k):
        raise AssertionError("ran on a building that can't be measured")
    monkeypatch.setattr(M, "grade_plane", boom)
    monkeypatch.setattr(M, "_floating", boom)
    monkeypatch.setattr(M, "_meets_ground", boom)
    lot, facts = _sample106()
    f = {**facts, "lot_surveyed": True, "stories": 3, "ground_is_flat": None, "grade_elevation": None,
         "grade_points": _walls_spots(12, 30, 36, 60, 0)}
    m = M.measure(_plot(_degenerate("walls", True), lot_=lot), f)
    assert "isn't a closed solid" in m["building_height"]["reason"]


def _slope_house(dx, dy, bottom):
    """A three-floor house on a lot falling toward the street, and its four spot grades as first placed: front 1.0,
    rear 3.0, sides 2.0 (stress F15). The house drawn from `bottom`, moved by (dx, dy) from where they were placed."""
    from test_measure import floor
    house = [floor(10 + dx, 30 + dy, 35 + dx, 60 + dy, z0=bottom + 10 * i, z1=bottom + 10 * (i + 1), id=f"f{i}")
             for i in range(3)]
    spots = [[22.5, 29.5, 1.0], [22.5, 60.5, 3.0], [9.5, 45, 2.0], [35.5, 45, 2.0]]
    facts = {**FACTS, "jurisdiction": CITY, "ground_is_flat": None, "grade_elevation": None, "grade_points": spots,
             "stories": 3, "lot_surveyed": True}
    return _plot(*house), facts


def test_raised_or_moved_the_ground_is_judged_by_one_test():
    """Stress F15 (the move case): a house raised 9 in. (bottom 2.75) on the slope was stopped by the grade plane's
    average ("the ground level (2.0 ft) doesn't meet the buildings"); moved 2'-2" back, the spot grades left the
    walls, the footprint path found the ground under it, and the rear yard went from needs review to complies while
    getting smaller. One test now, at the footprint: its rear corners stand in the ground (3.0), so it meets it in
    both places, and the rear yard's verdict doesn't change. Raised 3.25 ft it floats in both places."""
    from design_checker.check import check_site
    for bottom, meets in ((2.75, True), (3.25, False)):
        verdicts = []
        for dy in (0, 26 / 12):
            r = check_site(*_slope_house(0, dy, bottom))
            rear = items(r["view"])["Rear yard"]
            said = "doesn't meet the buildings" in (rear.get("reason") or "")
            assert said == (not meets), (bottom, dy, rear)
            verdicts.append(rear["status"])
        assert verdicts[0] == verdicts[1] or not meets and present.COMPLIES not in verdicts, (bottom, verdicts)


def test_moving_along_the_slope_never_turns_a_ground_stop_into_complies():
    """Property: moving the house along the contours (sideways: the ground under it doesn't change) in small steps,
    while its spot grades fall off the side walls, never turns a row stopped by the ground into one that complies:
    the ground is judged at the footprint, never by whether the points sit at the walls."""
    from design_checker.check import check_site
    for bottom in (2.0, 2.75, 3.0, 3.25, 4.0):
        before = None
        for step in range(0, 9):
            r = check_site(*_slope_house(-0.5 * step, 0, bottom))
            now = {i["name"]: i for i in r["view"]["items"]}
            if before:
                for name, i in now.items():
                    was = before.get(name)
                    if was and was["status"] == present.REVIEW and "meet the buildings" in (was.get("reason") or ""):
                        assert i["status"] != present.COMPLIES, (bottom, step, name, was["reason"])
            before = now


def test_the_stories_row_asks_for_the_whole_buildings_count_and_takes_it():
    """Demo fact-check (2), and Ben: read the geometry before ever asking. A plain solid h tall can hold at most
    floor(h / 7 ft) stories (R305.1). A 12 ft garage beside the starting house holds one: the Stories row never asks
    for a count (with the main building picked it complies). A 30 ft plain house could hold one to four in R-1b
    (3 allowed): the row says why and its own Enter button asks; 3 entered complies; 5 (more than 30 ft could
    hold) is refused with the measuring's words."""
    from design_checker import rhino_logic as logic
    from design_checker.check import check_site
    from test_measure import floor
    lot, facts = _sample106()
    base = {**facts, "lot_surveyed": True}
    base.pop("stories", None)
    house = [floor(12, 30, 36, 60, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
    garage = box(40, 66, 50, 86, 0, 12, "garage")
    st = items(check_site(_plot(*house, garage, lot_=lot), base)["view"])["Stories"]
    assert "stories" not in st["needs"] and "enter the count" not in (st["reason"] or "")
    st = items(check_site(_plot(*house, garage, lot_=lot), {**base, "main_building": "f0"})["view"])["Stories"]
    assert st["status"] == present.COMPLIES, st
    big = box(12, 30, 36, 60, 0, 30, "house")
    st = items(check_site(_plot(big, lot_=lot), base)["view"])["Stories"]
    assert st["status"] == present.REVIEW and "stories" in st["needs"]
    # the bad reading first, then why (stories review round 1, P3)
    assert st["reason"] == ("At worst 4 against 3: does not comply under that reading. A 30 ft solid (the building) "
                            "could hold up to 4 stories: draw its floors or enter the count.")
    assert logic.enter_words(st["needs"]) == "Enter the number of stories"
    view = check_site(_plot(big, lot_=lot), logic.update_counts(base, {"stories": 3}))["view"]
    assert items(view)["Stories"]["status"] == present.COMPLIES and logic.refused_stories(view["items"]) is None
    view = check_site(_plot(big, lot_=lot), logic.update_counts(base, {"stories": 5}))["view"]
    kept = [{k: i.get(k) for k in ("id", "name", "status", "reason", "refused")} for i in view["items"]]
    said = logic.refused_stories(kept)
    assert said and "more than the drawing could hold" in said and "at most 4" in said and "wasn't kept" in said
    view = check_site(_plot(*house, lot_=lot), logic.update_counts(base, {"stories": 2}))["view"]
    assert "fewer than the floor blocks drawn (3)" in (logic.refused_stories(
        [{k: i.get(k) for k in ("name", "reason", "refused")} for i in view["items"]]) or "")
    rhino = host_text("rhino", "plugin", purpose="wiring")
    assert "logic.refused_stories(" in rhino



def test_with_the_main_building_assumed_the_stories_row_points_to_the_pick_not_to_enter():
    """Stories review round 1 (P2): with the starting house only assumed, a 20 ft barn read as the main one
    ignores the count typed, yet the row offered Enter: entering changed nothing (a loop), and only the last
    question was shown, calling the barn "the building". Now Enter is offered only when a count can settle the
    row; else it points to Pick the main building…, every open question is kept, and the barn is named."""
    from design_checker.check import check_site
    from test_measure import floor
    lot, facts = _sample106()
    house = [floor(12, 30, 36, 60, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
    barn = box(40, 66, 50, 86, 0, 20, "barn")
    st = items(check_site(_plot(*house, barn, lot_=lot), {**facts, "lot_surveyed": True, "stories": 3})["view"])[
        "Stories"]
    assert "stories" not in st["needs"] and st["hint"] == present.PICK_MAIN, st
    assert "(barn) could hold up to 2 stories" in st["reason"] and "which building is the main building" in st["reason"]



def test_a_count_of_0_is_rolled_back_by_its_code_and_enter_stays():
    """#15 round 7 (2): "0" was refused in new words the plugin didn't match, so it was kept and the Enter button
    vanished. The plugin rolls back by the measuring's code, with its own words, and Enter stays on the row."""
    from design_checker.check import check_site
    from design_checker import rhino_logic as logic
    lot, facts = _sample106()
    base = {**facts, "lot_surveyed": True}
    big = box(12, 30, 36, 60, 0, 30, "house")
    view = check_site(_plot(big, lot_=lot), logic.update_counts(base, {"stories": 0}))["view"]
    st = items(view)["Stories"]
    assert st["refused"] == "below_one" and "stories" in st["needs"], st
    said = logic.refused_stories(view["items"])
    assert said and "fewer than one" in said and "wasn't kept" in said
    rhino = host_text("rhino", "plugin", purpose="wiring")
    assert '"group", "needs", "hint", "refused")' in rhino


def test_chart_quotes_follow_a_re_extraction_in_the_same_session(tmp_path):
    """A long Rhino session: the extracted chart text is replaced (re-extraction, same folder, same file names).
    The next panel quotes the new text, not the one cached under the folder name."""
    folder = tmp_path / "2_extracted_text"
    folder.mkdir()
    f = folder / "c.pdf.cells.jsonl"

    def write(value):
        f.write_text(json.dumps({"file": "c.pdf"}) + "\n" + json.dumps(
            {"page": 3, "section": "Minimum Lot Size", "row": "One-family dwelling, detached", "column": "R-1A",
             "value": value, "row_lines": [10]}) + "\n", encoding="utf-8")

    def quote():
        source = {"file": "c.pdf", "page": 3, "quote": "x", "lines": [10]}
        return present._quote(source, tmp_path, {"c.pdf": {"title": "Zoning charts"}}, "R-1A", lambda s: "")["text"]

    write("10,000 sf")
    assert quote().endswith("R-1A: 10,000 sf")
    write("12,000 sf")
    assert quote().endswith("R-1A: 12,000 sf")


def test_a_range_rule_that_complies_shows_the_limit_it_is_nearest():
    """R-3aa's stories are a range (at least 2, at most 3; chart p.3 note 11). The light run in Rhino (2026-10-28)
    showed a 3-story house as "3 | 2 required | complies": the first limit, the minimum, beside a count at the
    maximum. A complying range row shows the limit the design is nearest: 3 stories against 3, 2 against 2, and
    4 stories still does not comply against 3."""
    from design_checker.check import check_site
    from test_measure import floor
    lot, facts = _sample106()
    base = {**facts, "lot_surveyed": True, "zone": "R-3aa", "main_building": "f0"}
    base.pop("stories", None)
    for n, required, status in ((3, "3", present.COMPLIES), (2, "2", present.COMPLIES),
                                (4, "3", present.FAILS)):
        house = [floor(12, 30, 36, 60, z0=8 * i, z1=8 * (i + 1), id=f"f{i}") for i in range(n)]
        st = items(check_site(_plot(*house, lot_=lot), base)["view"])["Stories"]
        assert (st["proposed"], st["required"], st["status"]) == (str(n), required, status), st


def test_the_delta_cell_is_never_kinder_than_the_status():
    """Review round 1 of plain-words: the list's two-line Delta dropped the words that qualify it. A row in review
    with room under every reading showed "+4'-0 3/4" / worst +2'-0 3/4"" (no "if confirmed"); a row that fails
    another way showed "+2'-0" / worst +0'-6"" beside its ✕; one at limit read "at limit room here"."""
    off = "if the tax-map lines are 2 ft off"
    assert present.tax_delta(present.REVIEW, 4 + 0.75 / 12, (2 + 0.75 / 12, 6), "ft") == (
        f"+4'-0 3/4\" if confirmed (+2'-0 3/4\" {off})", "worst +2'-0 3/4\"\nif confirmed")
    assert present.tax_delta(present.FAILS, 2.0, (0.5, 4), "ft") == (
        f"2'-0\" room here; see why (+0'-6\" {off})", "2'-0\" room\nsee why")
    assert present.tax_delta(present.FAILS, 0.004, (-0.1, 2), "ft") == (
        f"at limit here; see why (0'-1 1/4\" short {off})", "at limit\nsee why")
    # a row in review that may be short keeps both numbers: the shortfall is shown, nothing kinder
    # ... and says its room "if so" (the head's "if confirmed"): never a bare "+" beside a review mark (the sceptic of
    # plain-words round 5); at limit too
    assert present.tax_delta(present.REVIEW, 2.0, (-0.02, 4), "ft")[1] == "+2'-0\" if so\nworst −0'-0 1/4\""
    assert present.tax_delta(present.REVIEW, 0.004, (-0.02, 4), "ft")[1] == "at limit if so\nworst −0'-0 1/4\""
    assert present.tax_delta(present.COMPLIES, 3.4375, (0.4375, 6), "ft")[1] == "+3'-5 1/4\"\nworst +0'-5 1/4\""


def test_the_delta_words_never_read_as_a_pass_on_a_row_that_is_not_one():
    """Review round 2 of plain-words: a row in review at the limit read "at limit (…)" like a pass; one with several
    readings at the limit read "at least at limit"; a row that fails another way with room under some reading had
    no "see why"; and a surveyed lot whose readings all agreed was told about the tax map."""
    off = "if the tax-map lines are 2 ft off"
    assert present.tax_delta(present.REVIEW, 0.0, (0.0, 2), "ft")[0] == f"at limit if confirmed (at limit {off})"
    assert present.tax_delta(present.REVIEW, 1.0, (0.004, 2), "ft", several=True)[0] == \
        "+1'-0\" if confirmed (at limit at worst)"
    assert present.tax_delta(present.FAILS, -0.3, (-0.3, 1.75), "ft")[0].endswith("the other way); see why")
    assert present.tax_delta(present.FAILS, -0.25, (-2.25, 1.75), "ft")[1] == "−0'-3\"\nsee why"   # round 3
    assert present.TAX_OFF not in present.tax_delta(present.COMPLIES, 2.0, (2.0, 2.0), "ft", several=True)[0]
    src = Path(present.__file__).read_text(encoding="utf-8")
    assert "_is_maximum(node), several or not approx)" in src           # settle: a survey never says the tax map
