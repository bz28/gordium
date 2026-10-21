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
          "margin": "−2'-6\""}]
    now, text = present.notice(None, a)
    assert text is None
    _, text = present.notice({"x": present.COMPLIES}, a)
    assert text == "Rear yard no longer complies · 20'-0\" proposed · 22'-6\" required · −2'-6\""
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
    assert present.TAX_MAP_SLACK is TAX_MAP_SLACK                                   # the checker reads the same one
    worst = present._worst_case("lot_width >= 70", {"lot_width": 73.0}, {"lot_width"})
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
    assert present._turns_on(rule, measured, {}, {}) == []       # either one decides it: it turns on neither


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
