"""The checker the Rhino command uses: results only from the report (and so from outcome()), the one-line
summary, which objects turn red, the failing distances, and the background JSON worker."""

import io
import json

import pytest

from design_checker.__main__ import answer, serve
from design_checker import present
from design_checker.check import check, short, summary
from model_measurement.project import load_facts
from rule_format.rulebook import REPO

SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
MODEL = SITE / "spreadsheet_design_model.3dm"


@pytest.fixture(scope="module")
def facts():
    return load_facts(SITE / "spreadsheet_design_model_facts.yaml")


def test_the_spreadsheet_model_gives_nine_passes_and_the_coverage_fail(facts, tmp_path):
    result = check(MODEL, facts, tmp_path / "report.xlsx")
    assert (tmp_path / "report.xlsx").exists()
    errors = {r["Rule id"]: r["Error"] for r in result["rows"]}
    assert errors["R-1b.lot_coverage"] == "FAIL" and list(errors.values()).count("PASS") == 9
    s = result["summary"]
    assert s["state"] == "fail" and s["text"] == "9 pass · 1 fail"
    assert s["lines"] == ["Lot coverage by buildings 1,855 sf, needs ≤ 1,642.5 sf (212.5 sf over)"]
    assert len(result["red"]) == 1                       # the house, not the lot
    assert result["dims"] == []                          # coverage isn't a distance


def test_a_failing_yard_is_drawn_as_the_line_it_was_measured_along(facts, tmp_path):
    import rhino3dm as r
    model = r.File3dm.Read(str(MODEL))
    for o in model.Objects:
        if isinstance(o.Geometry, r.Brep):
            o.Geometry.Translate(r.Vector3d(0, 3, 0))    # the house 3 ft back: rear yard 22 < 22.5
    moved = tmp_path / "moved.3dm"
    model.Write(str(moved), 8)
    result = check(moved, facts)
    assert "Rear yard 22 ft, needs ≥ 22.5 ft (0.5 ft short)" in result["summary"]["lines"]
    assert [d["measure"] for d in result["dims"]] == ["rear_yard"]
    assert result["dims"][0]["points"] == [[10.0, 90.0], [10.0, 68.0]]


def test_needs_review_rows_say_why_in_the_measuring_words(facts):
    """Parking waits on bedrooms and parking spaces (inside the building): it goes in its own group, "not checked
    yet: interior", out of the counts, with its reason; coverage still fails."""
    result = check(MODEL, {**facts, "sleeping_rooms": None, "parking_spaces": None})
    parking = next(r for r in result["interior"] if r["Rule id"] == "R-1b.parking_one_family")
    assert parking["Error"] == "NEEDS REVIEW" and parking["Why"] == "enter bedrooms / parking spaces"
    assert all(r["Rule id"] != "R-1b.parking_one_family" for r in result["rows"])
    assert result["summary"]["state"] == "fail" and "need review" not in result["summary"]["text"]


def test_an_interior_rule_that_fails_is_never_hidden(facts):
    result = check(MODEL, {**facts, "sleeping_rooms": 3, "parking_spaces": 0})
    parking = next(r for r in result["rows"] if r["Rule id"] == "R-1b.parking_one_family")
    assert parking["Error"] == "FAIL" and result["interior"] == []


def test_start_gives_the_largest_legal_building_as_stacked_floors(facts):
    from design_checker.check import start
    got = start(MODEL, {**facts, "lot_surveyed": True})
    assert len(got["floors"]) == 3 and got["height"] == 35
    assert [f["base"] for f in got["floors"]] == sorted(f["base"] for f in got["floors"])
    assert got["floors"][-1]["top"] == 35


def test_start_with_spot_grades_stands_the_building_on_their_grade_plane(facts):
    from design_checker.check import start
    spots = [[30, 1, 4.0], [30, 80, 6.0], [1, 40, 5.0], [70, 40, 5.0]]          # no building yet: their average, 5
    got = start(MODEL, {**facts, "lot_surveyed": True, "ground_is_flat": None, "grade_elevation": None,
                        "grade_from": "spot", "grade_points": spots})
    assert len(got["floors"]) == 3 and got["floors"][0]["base"] == 5.0 and got["floors"][-1]["top"] == 40.0
    assert not any("lot's level" in n for n in got["notes"])


def test_short_titles():
    assert short("Rear yard minimum (chart p.3, note 16; lot depth §325-8A(14))") == "Rear yard"
    assert short("Maximum building height, with the §325-16C bonus") == "Building height"


def test_all_pass_summary():
    assert summary([{"Error": "PASS", "Requirement": "x"}] * 3) == {"state": "pass", "text": "All 3 rules pass",
                                                                     "lines": []}


def test_the_worker_answers_line_by_line_and_never_stops_on_a_bad_request(facts):
    stdin = io.StringIO("\n".join([json.dumps({"id": 1, "cmd": "check", "model": str(MODEL), "facts": facts}),
                                   "not json",
                                   json.dumps({"id": 3, "cmd": "nope"}),
                                   json.dumps({"id": 4, "cmd": "options", "jurisdiction": facts["jurisdiction"]})]) + "\n")
    out = io.StringIO()
    serve(stdin, out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r["ok"] for r in replies] == [True, False, False, True]
    assert replies[0]["result"]["summary"]["text"] == "9 pass · 1 fail"
    assert replies[3]["result"]["zones"] == ["R-1b"]


def test_bad_lot_facts_are_a_plain_refusal(facts):
    reply = answer({"id": 1, "cmd": "check", "model": str(MODEL), "facts": {**facts, "grade_elevation": "0"}})
    assert reply["ok"] is False and "grade_elevation must be a number" in reply["error"]


def test_only_the_failing_distance_of_a_rule_is_drawn(facts, tmp_path):
    import rhino3dm as r
    model = r.File3dm.Read(str(MODEL))
    for o in model.Objects:
        if isinstance(o.Geometry, r.Brep):
            o.Geometry.Translate(r.Vector3d(-2, 0, 0))     # 8 ft from the left side, 12 ft from the right
    moved = tmp_path / "moved.3dm"
    model.Write(str(moved), 8)
    dims = check(moved, facts)["dims"]
    assert [(d["measure"], d["label"]) for d in dims] == [("side_yard_smaller", "side yard 8 ft, needs ≥ 10")]


def test_what_rhino_couldnt_send_makes_building_measures_need_review(facts):
    result = check(MODEL, facts, building_problems=["a block on the Building layer can't be measured yet (explode it)"])
    coverage = next(r for r in result["rows"] if r["Rule id"] == "R-1b.lot_coverage")
    assert coverage["Error"] == "NEEDS REVIEW" and "block" in coverage["Why"]


def test_no_jurisdiction_or_zone_is_a_plain_refusal(facts):
    with pytest.raises(ValueError, match="no zone given"):
        check(MODEL, {k: v for k, v in facts.items() if k != "zone"})


def test_rhino_decisions():
    from design_checker.rhino_logic import classify, missing, to_feet, update_counts, with_suggestions
    assert classify("Building::Garage", "Brep") == "building"
    assert classify("Building", "InstanceReferenceGeometry").startswith("a block")
    assert classify("Default", "InstanceReferenceGeometry", holds_building=True).startswith("a block")
    assert classify("Building", "PlaneSurface").startswith("a PlaneSurface")
    assert classify("Building", "LineCurve") is None and classify("Site::Old", "PolylineCurve") == "lot"
    assert classify("Default", "Brep") is None
    assert update_counts({"stories": 2}, {"stories": None, "sleeping_rooms": 3}) == {"stories": 2, "sleeping_rooms": 3}
    assert "sleeping_rooms" not in update_counts({}, {"sleeping_rooms": None})       # skipped: never 0
    assert missing({"sleeping_rooms": 3}) == ["jurisdiction", "zone", "use", "street_line", "corner_lot",
                                              "lot_surveyed"]          # no grade yet: checked, height needs review
    assert with_suggestions({"stories": 3, "zone": None}, {"zone": "R-1b"}) == {"zone": "R-1b", "stories": 3}
    assert to_feet({"street_line": [[[0, 0], [12, 0]]], "grade_elevation": 24}, 1 / 12) == {
        "street_line": [[[0.0, 0.0], [1.0, 0.0]]], "grade_elevation": 2.0}


def test_a_lot_or_building_no_longer_in_the_model_is_asked_again():
    from design_checker.rhino_logic import drop_stale, missing, with_suggestions
    saved = {"lot_id": "old", "street_line": [[[0, 0], [5, 0]]], "main_building": "gone", "zone": "R-1b"}
    fresh = drop_stale(saved, {"new"}, {"house"})
    assert fresh == {"zone": "R-1b"} and "street_line" in missing(fresh)
    merged = with_suggestions(fresh, {"lot_id": "new", "street_line": [[[0, 0], [73, 0]]]})
    assert merged["lot_id"] == "new" and merged["street_line"] == [[[0, 0], [73, 0]]]
    assert drop_stale(saved, {"old"}, {"gone"}) == saved


def test_the_venv_python_on_each_system():
    from design_checker.rhino_logic import venv_python
    assert venv_python("/repo", "posix") == "/repo/.venv/bin/python"
    assert venv_python("C:\\repo", "nt") == "C:\\repo\\.venv\\Scripts\\python.exe"


def test_a_result_is_drawn_only_in_its_own_document():
    from design_checker.rhino_logic import draws_in
    assert draws_in(5, 5) and not draws_in(5, 6) and not draws_in(None, 5)


def test_saved_facts_are_checked_like_a_facts_file():
    from design_checker.__main__ import answer
    for bad in ({"zone": "R-1b", "grade_elevation": "abc"}, {"street_line": 5}):
        assert answer({"id": 1, "cmd": "facts", "facts": bad})["result"]["problems"], bad
    assert answer({"id": 2, "cmd": "facts", "facts": {"zone": "R-1b"}})["result"]["problems"] == []


def test_the_checker_restarts_when_its_code_changes(tmp_path):
    from design_checker.rhino_logic import code_fingerprint, restart_checker
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    before = code_fingerprint(str(tmp_path))
    assert code_fingerprint(str(tmp_path)) == before
    (tmp_path / "pkg" / "a.py").write_text("x = 22\n")
    after = code_fingerprint(str(tmp_path))
    assert after != before
    assert restart_checker(True, before, after) and restart_checker(False, before, before)
    assert not restart_checker(True, after, after)
    (tmp_path / "pkg" / "measures.yaml").write_text("a: 1\n")       # data the checker loads counts too
    assert code_fingerprint(str(tmp_path)) != after


def test_a_file_gone_during_the_fingerprint_is_a_change_not_a_crash(tmp_path, monkeypatch):
    import os
    from design_checker import rhino_logic
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "pkg" / "b.py~").write_text("temp\n")
    before = rhino_logic.code_fingerprint(str(tmp_path))
    real = os.stat
    monkeypatch.setattr(os, "stat", lambda p, *a, **k: (_ for _ in ()).throw(FileNotFoundError(p))
                        if str(p).endswith("~") else real(p, *a, **k))
    after = rhino_logic.code_fingerprint(str(tmp_path))
    assert after != before and "b.py~:gone" in after


def test_only_a_candidate_can_be_picked_as_the_lot_or_main_building():
    from design_checker.rhino_logic import accepts_pick
    assert accepts_pick("lot-1", {"lot-1", "lot-2"}) and not accepts_pick("a-sketch", {"lot-1"})


def test_every_candidate_can_be_chosen_by_name():
    from design_checker.rhino_logic import option_names
    assert option_names("Lot", 3) == ["Lot1", "Lot2", "Lot3"]


def test_a_new_lot_drops_the_old_street_line_and_enter_keeps_only_a_current_one():
    from design_checker.rhino_logic import after_lot_pick, street_enter_keeps
    facts = {"lot_id": "a", "street_line": [[[0, 0], [5, 0]]]}
    assert after_lot_pick(facts, "a") == facts and street_enter_keeps(facts)
    moved = after_lot_pick(facts, "b")
    assert moved == {"lot_id": "b"} and not street_enter_keeps(moved)
    assert after_lot_pick(facts, None) == facts


def test_a_changed_corner_answer_drops_the_street_lines():
    from design_checker.rhino_logic import after_corner_answer, street_enter_keeps
    two = {"corner_lot": False, "street_line": [[[0, 0], [5, 0]], [[5, 0], [5, 9]]]}
    assert not street_enter_keeps(after_corner_answer(two, True))
    assert after_corner_answer(two, False) == two


def test_closing_the_confirm_dialog_saves_nothing():
    from design_checker.rhino_logic import after_confirm
    assert (after_confirm("ok"), after_confirm("change"), after_confirm(None)) == ("keep", "change", "cancel")


# ---- open questions: passes (or fails) whichever way they're answered ---------------------------------------

def _m(value=None, readings=()):
    return {"value": value, "readings": [{"reading": f"r{i}", "value": v} for i, v in enumerate(readings)]}


REAR = {"id": "rear", "kind": "rule", "check": "rear_yard >= max(min(0.25 * lot_depth, 50), 20)"}
COVER = {"id": "cover", "kind": "rule", "check": "building_area <= 0.25 * lot_area"}


def test_a_rule_that_passes_under_every_reading_says_so_and_stays_needs_review():
    from design_checker.check import every_reading
    measured = {"rear_yard": _m(None, [26, 27]), "lot_depth": _m(None, [90, 96.6])}
    assert every_reading(REAR, measured, {}) == ("pass", "passes under every reading")


def test_one_reading_that_fails_means_no_answer():
    from design_checker.check import every_reading
    measured = {"rear_yard": _m(None, [23, 27]), "lot_depth": _m(None, [90, 96.6])}   # 23 < 24.15
    assert every_reading(REAR, measured, {}) is None


def test_a_lot_not_yet_surveyed_is_the_lot_as_drawn_and_said_so():
    from design_checker.check import every_reading
    ok = {"building_area": _m(1600), "lot_area": _m(None, [6674.5])}
    over = {"building_area": _m(1800), "lot_area": _m(None, [6674.5])}
    assert every_reading(COVER, ok, {}) == ("pass", "passes with the lot as drawn (confirm the survey)")
    assert every_reading(COVER, over, {}) == ("fail", "fails with the lot as drawn (confirm the survey)")


def test_a_measurement_with_no_reading_at_all_is_never_worked_out():
    from design_checker.check import every_reading
    assert every_reading(COVER, {"building_area": _m(1600), "lot_area": _m(None)}, {}) is None


def test_the_summary_says_complies_only_when_every_open_question_passes():
    rows = [{"Error": "PASS", "Requirement": "Front yard"},
            {"Error": "NEEDS REVIEW", "Requirement": "Rear yard", "Provisional": "passes under every reading"}]
    assert summary(rows)["state"] == "complies"
    survey = rows[:1] + [{"Error": "NEEDS REVIEW", "Requirement": "Lot coverage by buildings", "Survey": True,
                          "Provisional": "passes with the lot as drawn (confirm the survey)", "Why": "no survey"}]
    s = summary(survey)                 # a lot not yet surveyed is a missing fact: amber, never a green complies
    assert s["state"] == "review" and s["lines"] == ["Lot coverage by buildings: passes with the lot as drawn (confirm the survey)"]
    rows.append({"Error": "NEEDS REVIEW", "Requirement": "Rear yard", "Provisional": None, "Why": "x"})
    assert summary(rows)["state"] == "review"


def test_a_rule_failing_under_every_reading_counts_as_failing():
    rows = [{"Error": "PASS", "Requirement": "Front yard"},
            {"Error": "NEEDS REVIEW", "Requirement": "Lot coverage by buildings", "Fails": True,
             "Provisional": "fails with the lot as drawn (confirm the survey)"}]
    s = summary(rows)
    assert s["state"] == "fail" and s["lines"] == ["Lot coverage by buildings: fails with the lot as drawn (confirm the survey)"]


# ---- the start flow and the "no longer complies" notice ----------------------------------------------------

def test_the_check_gives_the_notice_for_items_that_newly_fail(facts):
    first = check(MODEL, facts)
    assert first["notice"] is None                                      # the first check: nothing is "new"
    before = {k: ("complies" if k == "R-1b.lot_coverage" else v) for k, v in first["statuses"].items()}
    again = check(MODEL, facts, extras={"before": before})
    assert again["notice"].startswith("Lot coverage no longer complies · ")
    assert check(MODEL, facts, extras={"before": first["statuses"]})["notice"] is None   # still failing


def test_the_massing_layer_holds_building_objects():
    from design_checker import rhino_logic as logic
    assert logic.classify("Gordium::Massing", "Brep") == "building"
    assert logic.classify("Gordium", "Brep") is None


def test_the_sample_lot_gives_the_spec_massing():
    """73'-0" x 90'-0" (6,570 sf) -> 53'-0" x 30'-11" = 1,639 sf, 24.94% of the lot, at the 25'-0" front yard."""
    import math
    import tempfile
    from pathlib import Path

    import rhino3dm as r
    from shapely.geometry import Polygon

    from design_checker.check import sample_site, start
    s = sample_site()
    m = r.File3dm()
    m.Settings.ModelUnitSystem = r.UnitSystem.Feet
    layer = r.Layer()
    layer.Name = "Site"
    m.Layers.Add(layer)
    attrs = r.ObjectAttributes()
    attrs.LayerIndex = 0
    m.Objects.AddPolyline([r.Point3d(x, y, 0) for x, y in s["lot"] + s["lot"][:1]], attrs)
    path = Path(tempfile.mkdtemp()) / "lot.3dm"
    m.Write(str(path), 8)
    got = start(path, s["facts"])
    outline = Polygon(got["floors"][0]["outline"])
    x0, y0, x1, y1 = outline.bounds
    assert Polygon(s["lot"]).area == 6570 and s["facts"]["lot_surveyed"] is False
    assert (x1 - x0, round((y1 - y0) * 12, 6)) == (53, 30 * 12 + 11)
    assert round(outline.area) == 1639 and round(outline.area / 6570 * 100, 2) == 24.94
    assert y0 == 25 and len(got["floors"]) == 3 and got["floors"][-1]["top"] == 35


def test_a_flag_needing_review_never_crashes_the_check(facts):
    result = check(MODEL, {**facts, "use": "two_family"})
    flag = next(r for r in result["rows"] if r["Rule id"] == "R-1b.parking_other_uses")
    assert flag["Error"] == "NEEDS REVIEW"


def test_a_new_project_on_the_architects_own_lot_suggests_the_lots_ground_level():
    from design_checker import rhino_logic as logic
    assert logic.suggested_ground([], 12.0) == 12.0               # no building yet: the lot's level
    assert logic.suggested_ground([3.0, 1.0], 12.0) == 1.0        # the lowest point of the buildings
    assert logic.suggested_ground([], None) is None


def test_the_height_is_said_plainly(facts):
    tall = check(MODEL, {**facts, "stories": 3}, building_problems=None)
    from design_checker.check import _first_failing
    m = dict(tall["measurements"], building_height={**tall["measurements"]["building_height"], "value": 38})
    rule = {"check": "building_height <= 35 or building_height <= 38.5 and front_yard >= 25 + (building_height - 35)"}
    assert _first_failing(rule, m) == "Building height 38 ft, needs ≤ 35 ft"


def test_viewport_labels_never_cover_each_other():
    from design_checker.rhino_logic import clear_spot
    taken = []
    assert clear_spot(taken, 100, 100, 120, 20) == 100            # the first stays where it was wanted
    assert clear_spot(taken, 150, 105, 120, 20) == 128            # overlapping: moved a label's height down
    assert clear_spot(taken, 400, 100, 60, 20) == 100             # clear of the others: stays
    boxes = taken
    for i, (x, y, w, h) in enumerate(boxes):
        for a, b, c, e in boxes[i + 1:]:
            assert not (x < a + c and a < x + w and y < b + e and b < y + h)


def test_the_start_preview_and_the_panel_say_the_same_coverage(facts):
    from design_checker.check import start
    got = start(MODEL, {**facts, "lot_surveyed": False})
    assert got["preview"]["coverage"] == "24.95%"      # 1,638.6 / 6,570 = 24.941%: a maximum, rounded up
    assert got["preview"]["coverage"] == present._pct(got["area"] / 6570 * 100, "up", 2)
    assert got["preview"]["size"] == "53'-0\" × 30'-11\"" and got["preview"]["height"] == "35'-0\""
    assert got["preview"]["limit"] == "25%"                 # the limit beside it (A11), a maximum rounded down


def test_a_shortfall_is_never_shown_as_at_limit():
    assert present.margin_text(-0.001, "ft") == "−0'-0 1/8\""
    assert present.margin_text(-0.2, "sf") == "−1 sf" and present.margin_text(-0.001, "%") == "−0.01%"
    assert present.margin_text(0.001, "ft") == "at limit"


def test_side_yards_are_named_by_compass_direction_of_their_lot_line():
    north_south = {"side_yard_smaller": {"points": [[5, 60], [5, 50]]}, "side_yard_larger": {"points": [[5, 0], [5, 10]]}}
    assert present._side_name("side_yard_smaller", north_south) == "Side yard, North"
    assert present._side_name("side_yard_larger", north_south) == "Side yard, South"
    east_west = {"side_yard_smaller": {"points": [[0, 40], [10, 40]]}, "side_yard_larger": {"points": [[50, 40], [35, 40]]}}
    assert present._side_name("side_yard_smaller", east_west) == "Side yard, West"
    assert present._hint("Side yard, East", "≥", -4.0, "ft") == "To comply: move the building 4'-0\" farther from that lot line."


def test_what_off_the_building_layer_could_be_a_building_left_out():
    from design_checker.rhino_logic import could_be_building
    assert could_be_building("Mesh", solid=False, faces=120)        # an imported shed: an open, unwelded mesh
    assert could_be_building("Brep", solid=False, faces=5)          # a garage missing a face
    assert could_be_building("SubD") and could_be_building("InstanceReferenceGeometry")
    assert not could_be_building("Brep", solid=False, faces=1)      # one flat surface
    assert not could_be_building("PolylineCurve") and not could_be_building("Point")


# ---- no callback may raise into Rhino: on the Mac that aborts Rhino (2026-10-20) --------------------------------

PLUGIN = [REPO / "apps/rhino_plugin" / n for n in ("gordium_rhino.py", "gordium_ui.py")] + sorted(
    (REPO / "apps/rhino_plugin/tests").glob("*_in_rhino.py"))


def test_guard_catches_logs_and_says_it_once(tmp_path):
    from design_checker import rhino_logic as logic
    said = []
    logic.ERROR_LOG, logic.REPORT = str(tmp_path / "errors.log"), said.append
    logic._reported.clear()
    boom = logic.guard(lambda: 1 / 0, "draw the test", fallback="nothing")
    assert boom() == "nothing" and boom() == "nothing"                 # never raises
    assert said == ["Gordium: ⚠ couldn't draw the test (it was skipped; details in " + logic.ERROR_LOG + ")"]
    assert "ZeroDivisionError" in (tmp_path / "errors.log").read_text()
    assert logic.guard(lambda x: x + 1, "add")(1) == 2                 # passes through when nothing goes wrong
    logic.ERROR_LOG = logic.REPORT = None


def test_every_callback_the_plugin_gives_rhino_or_eto_is_guarded():
    """Every `obj.Event += handler`, every System.EventHandler(...) and every display conduit method: through
    rhino_logic.guard, so an error inside one is logged and skipped, never raised into native code."""
    import re
    unguarded = []
    for path in PLUGIN:
        text = path.read_text()
        guarded_names = set(re.findall(r"^\s*(\w+) = System\.EventHandler[^\n]*\((?:g\.)?logic\.guard\(", text, re.M))
        for n, line in enumerate(text.splitlines(), 1):
            m = re.match(r"\s*[\w.\[\]\"']+\.([A-Z]\w*) \+= (.+)", line)
            if m and not (re.match(r"(g\.)?logic\.guard\(", m.group(2)) or m.group(2).strip() in guarded_names):
                unguarded.append(f"{path.name}:{n}: {line.strip()}")
            if "System.EventHandler" in line and "(" in line.split("System.EventHandler", 1)[1] \
                    and "logic.guard(" not in line:
                unguarded.append(f"{path.name}:{n}: {line.strip()}")
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text()
    overlay = rhino.split("class Overlay", 1)[1].split("\nclass ", 1)[0].split("\ndef ", 1)[0]
    for method in re.findall(r"    def ((?:ObjectCulling|CalculateBoundingBox|PreDrawObjects|PostDrawObjects|"
                             r"DrawForeground|DrawOverlay|DrawObject)\(self, e\):\n(?:        .*\n)+)", overlay):
        if "_conduit(" not in method:
            unguarded.append("Overlay: " + method.splitlines()[0].strip())
    assert unguarded == [], unguarded
    assert "def _conduit(" in rhino and "logic.guard(" in rhino.split("def _conduit(", 1)[1].split("\ndef ", 1)[0]
    assert "Paint +=" not in "".join(p.read_text() for p in PLUGIN)    # draw once into a bitmap instead


def test_the_dash_patterns_fit_rhinos_signed_int32():
    """DrawPatternedPolyline takes an Int32: a mask with the top bit set raised "value too large to convert" every
    frame (caught by the guard), so the property line and the envelope were never dashed."""
    import re
    text = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text()
    code = re.search(r"^def _signed\(bits\):\n(?:    .*\n)+", text, re.M).group(0)
    code += "\n".join(re.findall(r"^(?:PHANTOM|DASHED) = .*$", text, re.M))
    found = {}
    exec(code, found)                                    # noqa: S102  (the file's own two constants)
    for name in ("PHANTOM", "DASHED"):
        assert -(1 << 31) <= found[name] < (1 << 31), name
        assert found[name] & 0xFFFFFFFF == found[name] % (1 << 32)       # the same 32 bits


# ---- the start box as approved 2026-10-20 (spec A) ----------------------------------------------------------------

def _box(**over):
    return {"address": "106 Ithaca Rd, Ithaca, NY", "zone": "R-1b", "use": "one_family_detached",
            "use_name": "One-family dwelling, detached", "lot_area": 6570.0, "lot_surveyed": False,
            "ground": {"kind": "flat"}, **over}


def test_i_confirm_is_unticked_on_a_new_project_and_draw_waits_for_it():
    from design_checker import rhino_logic as logic
    confirmed = {"value": "R-1b", "source": "entered by you", "confirmed_by": "you", "date": "2026-10-20"}
    assert not logic.district_confirmed("start", confirmed, "R-1b")             # a new project: always unticked
    assert logic.district_confirmed("check", confirmed, "R-1b")                 # this district, confirmed before
    assert not logic.district_confirmed("check", confirmed, "R-2a")             # changed since: confirm again
    assert not logic.district_confirmed("check", {}, "R-1b")
    rows = {r["key"]: r for r in logic.box_rows(_box())}
    assert rows["zone"]["tick"] == ("I confirm", False) and not logic.can_draw(_box())
    assert logic.can_draw(_box(district_confirmed=True))


def test_the_box_has_only_the_approved_rows_with_their_sources():
    from design_checker import rhino_logic as logic
    rows = logic.box_rows(_box())
    assert [r["key"] for r in rows] == ["address", "zone", "use", "lot", "street", "ground"]
    by = {r["key"]: r for r in rows}
    assert by["address"]["actions"] == [("lookup", "Look up (coming soon)", False)]      # lookup: a later PR
    assert by["zone"]["text"] == "R-1b · entered by you"
    assert by["lot"]["text"] == "6,570 sf · from the tax map (±2 ft, approximate)"
    assert by["lot"]["actions"] == [("lot", "Use my survey…", True)]
    assert by["street"]["text"] == "the highlighted line"
    assert by["ground"]["text"] == "flat at the lot level · as drawn"
    assert by["ground"]["tick"] == ("No regrading near the house", False)
    assert [a for a, _, _ in by["ground"]["actions"]] == ["spot", "terrain", "regrade"]
    assert logic.NOT_CHECKED_YET == "Not checked yet: overlays (historic, gorge, flood) · pitched roofs"
    box = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text().split("def start_box(", 1)[1].split("\ndef ", 1)[0]
    for gone in ("Existing building", "Floor to floor", "\"Roof\"", "Ground is", "Envelope only", "Massing"):
        assert gone not in box, gone                                          # removed from the box


def test_the_amber_line_names_what_to_do():
    from design_checker import rhino_logic as logic
    assert logic.uncertain(_box()) is None
    assert logic.uncertain(_box(corner_lot=True)) == "This lot faces two streets: pick the front"
    assert logic.uncertain(_box(zones_found=["R-1b", "R-2a"])) == "This lot is in two zones: pick the zone that applies"


def test_no_regrading_near_the_house_toggles_height_between_checked_and_needs_review(facts):
    from design_checker import rhino_logic as logic
    from design_checker.check import check
    for ticked, expected in ((True, {"complies", "does_not_comply"}), (False, {"needs_review"})):
        ground = logic.ground_facts(_box(no_regrading=ticked), 0.0)
        got = check(MODEL, {**facts, **{k: v for k, v in ground.items() if v is not None}})
        height = {i["name"]: i for i in got["view"]["items"]}["Building height"]
        assert height["status"] in expected, (ticked, height["status"], height["reason"])
    assert logic.ground_facts(_box(ground={"kind": "regrade"}), 0.0)["grade_is"] == "finished"   # set as finished


def test_every_fact_records_its_source_and_who_confirmed_it_and_the_panel_and_report_show_it(facts, tmp_path):
    import openpyxl
    from design_checker import rhino_logic as logic
    from design_checker.check import check
    sources = logic.fact_sources(_box(district_confirmed=True), "2026-10-20", confirmed=True)
    assert sources["zone"] == {"value": "R-1b", "source": "entered by you", "confirmed_by": "you", "date": "2026-10-20"}
    assert sources["lot"]["source"] == "the tax map (±2 ft)"
    unticked = logic.fact_sources(_box(), "2026-10-20", confirmed=True)
    assert unticked["zone"]["confirmed_by"] is None                       # the district needs its own tick
    got = check(MODEL, facts, tmp_path / "r.xlsx", extras={"sources": sources})
    lines = got["view"]["header"]["sources"]
    assert "Zoning district: R-1b · entered by you · confirmed by you, 2026-10-20" in lines
    text = " ".join(str(c.value) for r in openpyxl.load_workbook(tmp_path / "r.xlsx")["Check"].iter_rows() for c in r if c.value)
    assert "Zoning district: R-1b · entered by you" in text
