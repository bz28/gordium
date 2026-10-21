"""The checker the Rhino command uses: results only from the report (and so from outcome()), the one-line
summary, which objects turn red, the failing distances, and the background JSON worker."""

import io
import json
import math

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


def test_the_spreadsheet_model_gives_ten_passes_and_the_coverage_fail(facts, tmp_path):
    result = check(MODEL, facts, tmp_path / "report.xlsx")
    assert (tmp_path / "report.xlsx").exists()
    errors = {r["Rule id"]: r["Error"] for r in result["rows"]}
    # their nine rows pass, and so does R-1b.yard_projections (a box: no eaves, the yards to the eaves are the yards)
    assert errors["R-1b.lot_coverage"] == "FAIL" and list(errors.values()).count("PASS") == 10
    assert errors["R-1b.yard_projections"] == "PASS"
    s = result["summary"]
    assert s["state"] == "fail" and s["text"] == "10 pass · 1 fail"
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


def test_each_row_waiting_on_stated_facts_asks_for_exactly_those(facts):
    """A row waiting on facts only the architect can state carries `needs`: exactly those it reads that aren't set,
    in the order they are asked. Its "Enter …" button (named from them) asks for exactly those: one parking fact
    entered, the row then asks only for the other."""
    from design_checker import rhino_logic as logic
    result = check(MODEL, {**facts, "sleeping_rooms": None, "parking_spaces": None})
    row = next(r for r in result["interior"] if r["Rule id"] == "R-1b.parking_one_family")
    item = next(i for i in result["view"]["items"] if i["rule"] == "R-1b.parking_one_family")
    assert row["needs"] == item["needs"] == ["sleeping_rooms", "parking_spaces"]
    assert (item["name"], item["hint"], item["reason"]) == (
        "Parking · needs input", "Enter bedrooms and parking spaces",
        "Needs bedrooms and parking spaces, which the model doesn't show")
    half = check(MODEL, {**facts, "sleeping_rooms": 3, "parking_spaces": None})
    item = next(i for i in half["view"]["items"] if i["rule"] == "R-1b.parking_one_family")
    assert item["needs"] == ["parking_spaces"] and item["hint"] == "Enter parking spaces"
    # two concepts (review round 1): what can be ASKED (every stated fact) and what sets a row aside as "not
    # checked yet: interior" (only these two): a row reading R-3a's facts stays a review row, never hidden
    import design_checker.check as check_mod
    assert check_mod.INTERIOR == {"sleeping_rooms", "parking_spaces"}
    assert set(logic.STATED_FACTS) > check_mod.INTERIOR
    # R-3a's lot size (PR #20): a needs-review row whose condition reads dwelling units, rooms let for profit and
    # whether it is a conversion: its own button asks those three, a count, a count and a yes / no
    names = {"lot_area", "dwelling_units", "rooms_let_for_profit", "conversion", "use"}
    needs = logic.needs_of(names, {"use": "multiple_dwelling", "lot_area": 7000})
    assert needs == ["dwelling_units", "rooms_let_for_profit", "conversion"]
    assert logic.enter_words(needs) == "Enter dwelling units, rooms let for profit and whether it is a conversion"
    assert [logic.STATED_FACTS[k][1] for k in needs] == ["count", "count", "yes_no"]
    assert logic.needs_of(names, {"dwelling_units": 4, "rooms_let_for_profit": 0, "conversion": False}) == []
    # the panel asks exactly the row's own list (never a fixed pair), and saves through update_counts
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert 'a["enter"](i["needs"])' in ui and "Enter bedrooms and parking spaces…" not in ui
    assert "for key in needs:" in rhino and "logic.update_counts(facts, answers)" in rhino


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
    assert replies[0]["result"]["summary"]["text"] == "10 pass · 1 fail"
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
    # R-3a note 7's facts (#20 round 3): whole numbers 0 or more, a yes/no; skipped stays unset, never 0 or no
    got = update_counts({}, {"dwelling_units": 5, "rooms_let_for_profit": 0, "conversion": False})
    assert got == {"dwelling_units": 5, "rooms_let_for_profit": 0, "conversion": False}
    assert update_counts({"conversion": True}, {"dwelling_units": None, "conversion": None}) == {"conversion": True}
    for bad in ({"dwelling_units": -1}, {"rooms_let_for_profit": 2.5}):
        with pytest.raises(ValueError):
            update_counts({}, bad)
    assert missing({"sleeping_rooms": 3}) == ["jurisdiction", "zone", "use", "street_line",
                                              "lot_surveyed"]   # no grade, no corner answer: checked, they wait
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
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    before = code_fingerprint(str(tmp_path))
    assert code_fingerprint(str(tmp_path)) == before
    (tmp_path / "pkg" / "a.py").write_text("x = 22\n", encoding="utf-8")
    after = code_fingerprint(str(tmp_path))
    assert after != before
    assert restart_checker(True, before, after) and restart_checker(False, before, before)
    assert not restart_checker(True, after, after)
    (tmp_path / "pkg" / "measures.yaml").write_text("a: 1\n", encoding="utf-8")       # data the checker loads counts too
    assert code_fingerprint(str(tmp_path)) != after


def test_a_file_gone_during_the_fingerprint_is_a_change_not_a_crash(tmp_path, monkeypatch):
    import os
    from design_checker import rhino_logic
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.py~").write_text("temp\n", encoding="utf-8")
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


def test_the_checker_and_the_panel_read_one_reading_set():
    """Review round 2: the checker took its readings independently and gave up past 200 combinations, while the
    panel's set kept each lot reading's measurements together: they disagreed. Both now read reading_set.combos:
    the readings of one lot reading together (2 + 2, not 2 x 2 here), a word (the use, read by applies_when)
    taken as it is, and on a tax-map lot the slack, a yard never below 0."""
    from design_checker import reading_set
    from design_checker.check import every_reading
    a, b = "line 10 as a side lot line", "line 10 as a rear lot line"
    measured = {"rear_yard": {"value": None, "readings": [{"reading": a + "; to the wall", "value": 23},
                                                          {"reading": b + "; to the wall", "value": 27}]},
                "lot_depth": {"value": None, "readings": [{"reading": a, "value": 100}, {"reading": b, "value": 90}]},
                "use": {"value": "one_family_detached"}}
    values = {k: m["value"] for k, m in measured.items()}
    every = reading_set.combos({"rear_yard", "lot_depth"}, values, measured)
    assert sorted((t["rear_yard"], t["lot_depth"]) for t, _ in every) == [(23, 100), (27, 90)]   # never 23 with 90
    rule, uses = dict(REAR, applies_when='use == "one_family_detached"'), {"use": {"one_family_detached"}}
    assert every_reading(rule, measured, uses) is None               # 23 < 25 under one reading, 27 >= 22.5 the other
    fails = {**measured, "rear_yard": {"value": None, "readings": [{"reading": a + "; to the wall", "value": 20},
                                                                   {"reading": b + "; to the wall", "value": 21}]}}
    assert every_reading(rule, fails, uses) == ("fail", "fails under every reading")   # the use read as a word
    tax = {"side_yard_smaller": {"value": 1.0}, "lot_area": {"value": None, "tolerance": {"low": 5000, "high": 6000},
                                                             "readings": [{"reading": "as drawn", "value": 5500}]}}
    trials = reading_set.combos({"side_yard_smaller"}, {"side_yard_smaller": 1.0}, tax, {"lot_surveyed": False})
    assert sorted(t["side_yard_smaller"] for t, _ in trials) == [0.0, 3.0]          # 1 − 2 kept at 0


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
    """106 Ithaca Rd as the State tax map draws it (7,033.8 sf; 7,033.5 as placed, its points rounded to 1/10,000 ft) -> the starting house
    kept 2'-0" back from every limit: 35'-11" x 37'-4", three floors to 35'-0", 27'-0 3/4" from the street. Here the
    left side yard binds, not coverage: 19.1% of the lot as drawn, well under 25% of the smallest lot the tax map
    allows (6,357 sf, the checker's own worst case)."""
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
    from design_checker import present
    lot = Polygon(s["lot"])
    from rule_format.rulebook import load
    stored = load(REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/lot_outline_tax_map.yaml")
    assert abs(lot.area - stored["area_sf"]) < 1 and s["facts"]["lot_surveyed"] is False   # placed points rounded
    # (PR 18: legal under every reading of which of 106's lot lines are side and rear lines, its tax-map outline
    # cleaned within 0.25 ft: 15 lines -> 9; the strictest rear line sets the depth, so the house is wide and shallow)
    assert (present.feet_inches(x1 - x0), present.feet_inches(y1 - y0)) == ("51'-4\"", "29'-8\"")
    assert round(outline.area / lot.area * 100, 1) == 21.7 and outline.area <= 0.25 * 6357
    assert len(got["floors"]) == 3 and got["floors"][-1]["top"] == 35
    from design_checker.check import check_site
    from envelope_builder.start import floor_solids
    n = len(s["lot"])
    lot_site = {"id": "lot", "edges": [{"points": [list(s["lot"][i]) + [0.0], list(s["lot"][(i + 1) % n]) + [0.0]],
                                        "curved": False} for i in range(n)]}
    view = check_site({"units": "ft", "lot": lot_site, "buildings": floor_solids(got["floors"]), "problems": []},
                      {**s["facts"], "jurisdiction": s["facts"]["jurisdiction"]})["view"]
    front = {i["name"]: i for i in view["items"]}["Front yard"]
    assert front["proposed"] == "27'-0 3/4\"" and front["status"] == present.COMPLIES     # 25'-0" + 2'-0", and more


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
    # tax-map lot, kept 2'-0" back (worked by hand): width 73 − 2 × (10 + 2) = 49'-0"; coverage for the smallest lot
    # the tax map allows (every line 2 ft in), 25% × 69 × 86 = 1,483.5 sf, so depth 1,483.5 / 49 = 30.28 → 30'-3"
    # (whole inches, down); 49 × 30.25 = 1,482.25 sf = 22.56% of the drawn 6,570 sf: shown to 0.1%, up
    assert got["preview"]["coverage"] == "22.6%"
    assert got["preview"]["coverage"] == present._display(got["area"] / 6570 * 100, 25.0, None, "%", "≤")[0]
    assert got["preview"]["size"] == "49'-0\" × 30'-3\"" and got["preview"]["height"] == "35'-0\""
    assert got["preview"]["limit"] == "25%"                 # the limit beside it (A11), a maximum rounded down


def test_on_a_tax_map_lot_the_starting_house_complies_even_at_the_worst_case(facts):
    """Ben, 2026-10-20: kept 2'-0" back from every limit and under coverage at the worst case, so nothing about the
    generated house needs review because of the tax map; on a survey it goes exactly to the limits."""
    from design_checker.check import TAX_MAP_NOTE, check_site, start
    from envelope_builder.start import floor_solids
    from model_measurement.read_3dm import read_site
    tax = start(MODEL, {**facts, "lot_surveyed": False})
    assert tax["kept_back"] == 2.0 and TAX_MAP_NOTE in tax["notes"] and tax["preview"]["kept_back"] == "2'-0\""
    assert tax["margin_note"] == TAX_MAP_NOTE
    # coverage is sized for the worst case, so no note says it needs review (review round 7)
    assert not any("NEEDS REVIEW for coverage" in n for n in tax["notes"])
    site = {**read_site(MODEL, facts), "buildings": floor_solids(tax["floors"])}
    view = check_site(site, {**facts, "lot_surveyed": False})["view"]
    assert not [i["name"] for i in view["items"] if i["status"] == present.REVIEW and "tax map" in (i["reason"] or "")
                and i.get("measure") not in ("lot_area", "lot_width", "lot_depth")]
    lot_area = next(i for i in view["items"] if i["name"] == "Lot area")    # the lot's own size, not the house's:
    assert lot_area["status"] == present.REVIEW and "at worst 5,934 sf against 6,000 sf" in lot_area["reason"]
    surveyed = start(MODEL, {**facts, "lot_surveyed": True})
    assert surveyed["kept_back"] == 0.0 and TAX_MAP_NOTE not in surveyed["notes"]
    xs = [p[0] for p in surveyed["floors"][0]["outline"]]
    assert max(xs) - min(xs) == pytest.approx(53.0)                 # 73 − 2 × 10: exactly at the side yards
    buffered = start(MODEL, {**facts, "lot_surveyed": True}, design_buffer=1.0)
    xs = [p[0] for p in buffered["floors"][0]["outline"]]
    assert buffered["kept_back"] == 1.0 and max(xs) - min(xs) == pytest.approx(51.0)   # 1 ft more on each side


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
    assert "ZeroDivisionError" in (tmp_path / "errors.log").read_text(encoding="utf-8")
    assert logic.guard(lambda x: x + 1, "add")(1) == 2                 # passes through when nothing goes wrong
    logic.ERROR_LOG = logic.REPORT = None


def test_every_callback_the_plugin_gives_rhino_or_eto_is_guarded():
    """Every `obj.Event += handler`, every System.EventHandler(...) and every display conduit method: through
    rhino_logic.guard, so an error inside one is logged and skipped, never raised into native code."""
    import re
    unguarded = []
    for path in PLUGIN:
        text = path.read_text(encoding="utf-8")
        guarded_names = set(re.findall(r"^\s*(\w+) = System\.EventHandler[^\n]*\((?:g\.)?logic\.guard\(", text, re.M))
        # the plugin's own route: _handler(...) guards (checked below), _on(owner, "Event", name) attaches
        guarded_names |= set(re.findall(r"^\s*(\w+) = _handler\(", text, re.M))
        for name in re.findall(r"_on\([\w.]+, \"\w+\", (\w+)\)", text):
            if name not in guarded_names:
                unguarded.append(f"{path.name}: _on(..., {name}) not made by _handler")
        for n, line in enumerate(text.splitlines(), 1):
            m = re.match(r"\s*[\w.\[\]\"']+\.([A-Z]\w*) \+= (.+)", line)
            if m and line.strip() == "event += handler" and path.name == "gordium_rhino.py":
                continue                                   # inside _on: every caller's handler is checked above
            if m and not (re.match(r"(g\.)?logic\.guard\(", m.group(2)) or m.group(2).strip() in guarded_names):
                unguarded.append(f"{path.name}:{n}: {line.strip()}")
            if "System.EventHandler" in line and "(" in line.split("System.EventHandler", 1)[1] \
                    and "logic.guard(" not in line and "_handler(System.EventHandler" not in line:
                unguarded.append(f"{path.name}:{n}: {line.strip()}")
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    overlay = rhino.split("class Overlay", 1)[1].split("\nclass ", 1)[0].split("\ndef ", 1)[0]
    for method in re.findall(r"    def ((?:ObjectCulling|CalculateBoundingBox|PreDrawObjects|PostDrawObjects|"
                             r"DrawForeground|DrawOverlay|DrawObject)\(self, e\):\n(?:        .*\n)+)", overlay):
        if "_conduit(" not in method:
            unguarded.append("Overlay: " + method.splitlines()[0].strip())
    assert unguarded == [], unguarded
    handler = rhino.split("def _handler(", 1)[1].split("\ndef ", 1)[0]
    assert "logic.guard(logic.current_only(" in handler
    assert "def _conduit(" in rhino and "logic.guard(" in rhino.split("def _conduit(", 1)[1].split("\ndef ", 1)[0]
    # an error raised while the Mac draws a view aborted Rhino (2026-10-20, before the guard): every paint handler is
    # guarded (the panel's wrapping cells are drawn); the section diagram is still drawn once into a bitmap
    import re as _re
    paints = [m for p in PLUGIN for m in _re.findall(r"\.Paint \+= (.*)", p.read_text(encoding="utf-8"))]
    assert all(m.startswith("logic.guard(") for m in paints), paints


def test_the_dash_patterns_fit_rhinos_signed_int32():
    """DrawPatternedPolyline takes an Int32: a mask with the top bit set raised "value too large to convert" every
    frame (caught by the guard), so the property line and the envelope were never dashed."""
    import re
    text = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
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
    rows = {r["key"]: r for r in logic.box_rows(_box(), flat=False)}
    assert rows["zone"]["tick"] == ("I confirm", False) and not logic.can_draw(_box())
    assert logic.can_draw(_box(district_confirmed=True))


def test_the_box_has_only_the_approved_rows_with_their_sources():
    from design_checker import rhino_logic as logic
    rows = logic.box_rows(_box(), flat=False)
    assert [r["key"] for r in rows] == ["address", "zone", "use", "lot", "street", "ground"]
    by = {r["key"]: r for r in rows}
    assert by["address"]["actions"] == [("lookup", "Look up (coming soon)", False)]      # lookup: a later PR
    assert by["zone"]["text"] == "R-1b · entered by you"
    assert by["lot"]["text"] == "6,570 sf · from the tax map (±2 ft, approximate)"
    assert by["lot"]["actions"] == [("lot", "Use my survey…", True)]
    assert by["street"]["text"] == "Ithaca Rd"                          # the street of the address (P1-4)
    assert by["ground"]["text"] == "flat at the lot level · as drawn"
    assert by["ground"]["tick"] == ("No regrading near the house", False)
    assert [a for a, _, _ in by["ground"]["actions"]] == ["spot", "terrain", "regrade"]
    assert logic.NOT_CHECKED_YET == "Not checked yet: overlays (historic, gorge, flood) · pitched roofs"
    box = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8").split("def start_box(", 1)[1].split("\ndef ", 1)[0]
    for gone in ("Existing building", "Floor to floor", "\"Roof\"", "Ground is", "Envelope only", "Massing"):
        assert gone not in box, gone                                          # removed from the box


def test_the_amber_line_names_what_to_do():
    from design_checker import rhino_logic as logic
    assert logic.uncertain(_box(corner_lot=False)) is None               # answered: no amber line
    assert logic.uncertain(_box(corner_lot=True)) == "This lot faces two streets: pick the front"
    assert logic.uncertain(_box(corner_lot=False, zones_found=["R-1b", "R-2a"])) == \
        "This lot is in two zones: pick the zone that applies"


def test_no_regrading_near_the_house_toggles_height_between_checked_and_needs_review(facts):
    from design_checker import rhino_logic as logic
    from design_checker.check import check
    for ticked, expected in ((True, {"complies", "does_not_comply"}), (False, {"needs_review"})):
        ground = logic.ground_facts(_box(no_regrading=ticked), 0.0, flat=False)
        got = check(MODEL, {**facts, **{k: v for k, v in ground.items() if v is not None}})
        height = {i["name"]: i for i in got["view"]["items"]}["Building height"]
        assert height["status"] in expected, (ticked, height["status"], height["reason"])
    assert logic.ground_facts(_box(ground={"kind": "regrade"}), 0.0, flat=False)["grade_is"] == "finished"   # set as finished


def test_every_fact_records_its_source_and_who_confirmed_it_and_the_panel_and_report_show_it(facts, tmp_path):
    import openpyxl
    from design_checker import rhino_logic as logic
    from design_checker.check import check
    sources = logic.fact_sources(_box(district_confirmed=True), "2026-10-20", confirmed=True)
    assert sources["zone"] == {"value": "R-1b", "source": "entered by you", "confirmed_by": "you", "date": "2026-10-20"}
    assert sources["lot"] == {"value": "6,570 sf", "source": "the tax map (±2 ft, approximate)",
                              "confirmed_by": "you", "date": "2026-10-20"}       # the source said once
    unticked = logic.fact_sources(_box(), "2026-10-20", confirmed=True)
    assert unticked["zone"]["confirmed_by"] is None                       # the district needs its own tick
    got = check(MODEL, facts, tmp_path / "r.xlsx", extras={"sources": sources})
    lines = got["view"]["header"]["sources"]
    assert "Zoning district: R-1b · entered by you · confirmed by you, 2026-10-20" in lines
    text = " ".join(str(c.value) for r in openpyxl.load_workbook(tmp_path / "r.xlsx")["Check"].iter_rows() for c in r if c.value)
    assert "Zoning district: R-1b · entered by you" in text


def test_start_on_existing_ground_still_draws_the_house_and_says_height_waits(facts):
    """The box's default: ground as drawn, No regrading unticked (existing ground). The house is drawn standing on
    it; the check that follows says height and stories need review (C5)."""
    from design_checker.check import start
    got = start(MODEL, {**facts, "lot_surveyed": True, "grade_is": "existing"})
    assert len(got["floors"]) == 3
    assert any("No regrading near the house" in n for n in got["notes"])
    height = {i["name"]: i for i in check(MODEL, {**facts, "grade_is": "existing"})["view"]["items"]}["Building height"]
    assert height["status"] == present.REVIEW


def test_system_colors_come_from_eto_drawing():
    """Eto.Forms has no SystemColors: asking it raised, so the dark-panel check always said "light" (unreadable text
    on a dark panel) and a complying item's detail failed to draw. They are Eto.Drawing.SystemColors."""
    for path in PLUGIN:
        assert "ef.SystemColors" not in path.read_text(encoding="utf-8"), path.name


# ---- review round 5 ----------------------------------------------------------------------------------------------

def test_a_corner_lot_is_never_guessed_the_box_asks_and_the_yards_wait(facts):
    from design_checker import rhino_logic as logic
    unanswered = _box(corner_lot=None)
    street = {r["key"]: r for r in logic.box_rows(unanswered)}["street"]
    assert street["choice"] == ("Corner lot?", ["Not answered", "No: one street", "Yes: two streets"], 0)
    assert logic.uncertain(unanswered) == "Does this lot face two streets? Answer Corner lot? under Street side"
    assert logic.uncertain(_box(corner_lot=True)) == "This lot faces two streets: pick the front"
    assert logic.uncertain(_box(corner_lot=False)) is None
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    suggested = rhino.split("def suggested_facts(", 1)[1].split("\ndef ", 1)[0]
    assert "logic.suggested_facts(" in suggested and "corner_lot" not in suggested   # the tested logic decides
    got = check(MODEL, {k: v for k, v in facts.items() if k != "corner_lot"})          # unanswered
    yards = {i["name"]: i for i in got["view"]["items"]}
    assert yards["Front yard"]["status"] == present.REVIEW


def test_gordiums_own_defaults_say_suggested_and_a_change_says_entered_by_you():
    from design_checker import rhino_logic as logic
    s = logic.fact_sources(_box(corner_lot=False), "2026-10-20", confirmed=True)
    assert s["use"]["source"] == "suggested by Gordium" and s["street"]["source"] == "suggested by Gordium"
    assert s["corner_lot"]["value"] == "no, one street" and s["corner_lot"]["source"] == "suggested by Gordium"
    s = logic.fact_sources(_box(use_source="entered by you", corner_lot=True, corner_source="entered by you"),
                           "2026-10-20", confirmed=True)
    assert s["use"]["source"] == "entered by you" and s["corner_lot"]["source"] == "entered by you"
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8").split("def start_box(", 1)[1]
    for key in ("address_source", "use_source", "corner_source", "zone_source"):   # a change in the box records it
        assert f'state["{key}"] = logic.ENTERED' in ui, key


def test_finished_ground_and_existing_spot_grades_are_never_mixed():
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert 'FINISHED_LAYER = "Gordium::Grade::Finished"' in rhino
    assert "GRADE_LAYER if what == \"spot\" else FINISHED_LAYER" in rhino          # placed apart
    check_facts = rhino.split("def check_facts(", 1)[1].split("\ndef ", 1)[0]
    assert '_grade_points(doc, facts["grade_from"] == "finished_spots")' in check_facts   # read apart, by the facts


def test_the_confirm_tick_survives_a_pick_and_ground_marking_can_be_undone():
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    loop = rhino.split("def confirm(", 1)[1].split("\ndef ", 1)[0]
    assert "dict(_box_state(doc, facts, options, saved_ui, mode), **ticked)" in loop
    assert '"district_confirmed"' in loop.split("ticked = {k: state[k]", 1)[1].split(")", 1)[0]
    assert "def not_the_ground(" in rhino and '"not_ground": not_the_ground' in rhino
    survey = rhino.split("def pick_survey(", 1)[1].split("\ndef ", 1)[0]
    assert '_set_source(doc, "lot"' in survey                                      # its source never goes stale


# ---- review round 6 ----------------------------------------------------------------------------------------------

def test_an_unanswered_corner_lot_never_stops_the_check_it_makes_the_yards_wait(facts):
    from design_checker import rhino_logic as logic
    unanswered = {k: v for k, v in facts.items() if k != "corner_lot"}
    assert "corner_lot" not in logic.missing(unanswered)                       # the check runs
    items = {i["name"]: i for i in check(MODEL, unanswered)["view"]["items"]}
    assert items["Front yard"]["status"] == present.REVIEW
    assert items["Lot coverage"]["status"] in (present.FAILS, present.COMPLIES, present.REVIEW)   # measured


def test_which_spot_grades_count_is_a_saved_fact_never_the_boxs_unsaved_state():
    from design_checker import rhino_logic as logic
    assert logic.ground_facts(_box(ground={"kind": "regrade"}), 0.0, flat=False)["grade_from"] == "finished_spots"
    assert logic.ground_facts(_box(ground={"kind": "spot"}), 0.0, flat=False)["grade_from"] == "spot"
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    check_facts = rhino.split("def check_facts(", 1)[1].split("\ndef ", 1)[0]
    assert "_ui_state" not in check_facts.split("elif", 1)[0]                   # the points from the facts alone
    loop = rhino.split("def confirm(", 1)[1].split("\ndef ", 1)[0].split("while True:", 1)[1]
    assert "_save_ui_state" not in loop                                         # Cancel saves nothing
    drawn = rhino.split("def _drawn(", 1)[1].split("\ndef ", 1)[0]
    assert "sources = fact_sources(doc)" in drawn and "sources.update(" in drawn  # the ground marking is kept
    assert "from_sample=True" in rhino.split("def gordium_start(", 1)[1]


def test_units_are_converted_in_one_place_both_ways():
    """Gordium works in feet; the Rhino side converts at five helpers and nowhere else (a mm template showed why the
    edge must be one place: there the start had to be checked line by line)."""
    import re
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    helpers = ("_scale", "_model_point", "_model_length", "_feet_point", "_feet_length", "_feet_area", "_facts_in_feet")
    outside = []
    for chunk in re.split(r"\n(?=def )", rhino):
        name = re.match(r"def (\w+)", chunk)
        if name and name.group(1) in helpers:
            continue
        for line in chunk.splitlines():
            if re.search(UNITS_PATTERN, line) and "logic.to_feet(facts, _scale(doc))" not in line:
                outside.append(line.strip())
    assert outside == [], outside
    assert "def frame_site(" in rhino and "frame_site(doc, facts)" in rhino.split("def gordium_start(", 1)[1]


UNITS_PATTERN = r"_scale\(|\* k\b|\* scale\b|/ scale\b|\* k\)"     # any use of the scale, whatever follows it


def test_the_units_scan_catches_a_conversion_inside_a_call():
    r"""Review round 7: `_scale\(doc\)(?!\))` let `foo(y / _scale(doc))` through."""
    import re
    assert re.search(UNITS_PATTERN, "    x = foo(y / _scale(doc))")
    assert re.search(UNITS_PATTERN, "    x = y * _scale(doc)")


def test_a_value_measured_on_existing_ground_shows_with_its_review_mark_not_a_dash(facts, tmp_path):
    import openpyxl
    got = check(MODEL, {**facts, "grade_is": "existing"}, tmp_path / "r.xlsx")
    rows = {i["name"]: i for i in got["view"]["items"]}
    height, stories = rows["Building height"], rows["Stories"]
    assert (height["status"], height["mark"]) == (present.REVIEW, "?") and height["proposed"] not in ("—", "")
    assert stories["status"] == present.REVIEW and stories["proposed"] not in ("—", "")
    assert "No regrading near the house" in height["reason"]                 # the reason says what settles it
    text = " ".join(str(c.value) for r in openpyxl.load_workbook(tmp_path / "r.xlsx")["Check"].iter_rows() for c in r if c.value)
    assert height["proposed"] in text                                          # the report shows the value too
    assert got["measurements"]["building_height"]["value"] is None            # it still never decides the rule


def test_plan_labels_only_in_a_view_looking_straight_down():
    from design_checker.rhino_logic import is_plan_view
    assert is_plan_view(True, -1.0)                      # Top
    assert not is_plan_view(True, 0.0)                   # Front, Right: elevations
    assert not is_plan_view(False, -1.0)                 # a perspective, even from above
    assert not is_plan_view(True, 1.0)                   # Bottom
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert "plan = logic.is_plan_view(e.Viewport.IsParallelProjection, e.Viewport.CameraDirection.Z)" in rhino


def test_the_margin_note_says_what_was_kept_and_which_part_is_the_buffer(facts):
    """Review round 7: with a 1'-0" buffer on a tax-map lot the house keeps 3'-0" back; the note said 2'-0"."""
    from design_checker.check import NOT_PROVEN, TAX_MAP_NOTE, margin_note, start
    got = start(MODEL, {**facts, "lot_surveyed": False}, design_buffer=1.0)
    assert got["kept_back"] == 3.0
    assert got["margin_note"] == ("Starting house keeps 3'-0\" back from each limit: 2'-0\" because the lot is from "
                                  "the tax map (use a survey for the full area) and 1'-0\" your design buffer.")
    assert got["margin_note"] in got["notes"] and TAX_MAP_NOTE not in got["notes"]
    assert margin_note(2.25, 0.0, True, True).startswith("Starting house keeps 2'-3\" back")
    assert margin_note(2.0, 0.0, True, False) == NOT_PROVEN          # never claimed without the proof
    assert margin_note(0.0, 0.0, False, True) == "Starting house goes to the limits (the lot is from a survey)."


def test_the_starting_house_fact_is_gordiums_never_confirmed_by_you():
    """Review round 7: it was saved "confirmed by you" for a figure the architect never saw; and with no house drawn
    there is no fact. Gordium saves it only after the house is drawn, and clears an earlier one first."""
    from design_checker import rhino_logic as logic
    fact = logic.starting_house_fact("Starting house keeps 2'-0\" back ...", "2026-10-20")
    assert fact["confirmed_by"] is None and fact["source"] == logic.SUGGESTED
    assert logic.starting_house_fact(None, "2026-10-20") is None
    line = present.source_lines({"starting_house": fact})[0]
    assert "confirmed by you" not in line and "not confirmed" in line
    # round 8: said once, as the house first drawn; the not-proven note too
    from design_checker.check import NOT_PROVEN, TAX_MAP_NOTE
    lines = [present.source_lines({"starting_house": logic.starting_house_fact(n, "2026-10-20")})[0]
             for n in (TAX_MAP_NOTE, NOT_PROVEN)]
    assert lines[0].startswith("Starting house: as first drawn, it keeps 2'-0\" back from each limit")
    assert lines[1].startswith("Starting house: as first drawn, Gordium couldn't keep it clear")
    assert not any(ln.count("Starting house") > 1 for ln in lines) and NOT_PROVEN.endswith(".")
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    body = rhino[rhino.index("def gordium_start"):]
    # round 8: cleared before any way out (a start that draws nothing keeps no earlier start's margin)
    assert body.index('_set_source(doc, "starting_house", None, None)') < body.index('if not start.get("floors")') \
        < body.index("add_floors(doc, start)") < body.index("logic.starting_house_fact(")


def test_a_design_buffer_is_read_or_draw_stays_off():
    """Review round 7: 6" (inches alone) or "6 in" was read as 0, silently."""
    from design_checker import rhino_logic as logic
    assert logic.parse_feet('6"') == 0.5 and logic.parse_feet("6 in") == 0.5 and logic.parse_feet("1'-6\"") == 1.5
    assert logic.parse_feet("") == 0.0 and logic.parse_feet("abc") is None and logic.parse_feet("-1") is None
    state = {"district_confirmed": True, "design_buffer": "abc"}
    assert not logic.can_draw(state) and logic.draw_reason(state) == logic.BUFFER_UNREAD
    assert logic.can_draw({**state, "design_buffer": '6"'})


def test_the_design_buffer_is_set_when_starting_not_in_edit_site():
    """Review round 7: Edit site… showed it, but changing it there redrew nothing."""
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert 'buffer = ef.TextBox() if mode == "start" and not logic.FLAT_GROUND else None' in ui
    guide = (REPO / "apps/rhino_plugin/QUICKSTART.md").read_text(encoding="utf-8")
    from design_checker import rhino_logic as logic
    # (hidden while the MVP assumes flat ground: the box has no Advanced then)
    assert "Edit site… → Advanced" not in guide and (logic.FLAT_GROUND or
                                                     "Advanced → Design buffer** in the GordiumStart box" in guide)


def test_frame_site_frames_the_lot_and_house_not_the_whole_file():
    """Review round 7: Zoom All Extents undid the per-view framing and took in anything far away in the file."""
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    start = rhino.index("def frame_site")
    body = rhino[start:start + 1800]
    assert "_Extents" not in body and '"_-Zoom _All _Selected"' in body and "doc.Objects.Select(i)" in body


def test_spec_item_ids_are_unique():
    import collections
    import re
    spec = (REPO / "docs/design/rhino_ui_spec.md").read_text(encoding="utf-8")
    ids = collections.Counter(re.findall(r"^([A-Z]\d+) \[", spec, re.M))
    assert [i for i, n in ids.items() if n > 1] == []


def _panel_actions(rhino):
    """The functions the panel's buttons call (gordium_rhino._actions), by name."""
    import re
    body = rhino[rhino.index("def _actions():"):rhino.index("\ndef panel():")]
    return sorted(set(re.findall(r'"\w+": (\w+)[,}]', body)) - {"ui"})


def test_the_zoning_report_button_writes_the_report_for_the_model_now_then_opens_it():
    """Ben's test, 2026-10-20: after GordiumStart the button did nothing (it only opened a report GordiumCheck had
    written, and GordiumStart, live checks and Retry never write one). Now it checks the model as it is, writing the
    report, opens it, and says where it was saved, or why not."""
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    body = rhino[rhino.index("def open_report():"):rhino.index("\ndef off():")]
    assert "run_check(doc, report=True)" in body and "os.path.getmtime(path) != before" in body
    assert body.count("say(") >= 4 and "if os.path.exists(path):\n" not in body
    from design_checker import rhino_logic as logic
    assert logic.report_message("/x/a_gordium_report.xlsx", True) == "Report saved to /x/a_gordium_report.xlsx (opened)."
    assert logic.report_message("/x/r.xlsx", False, "lot facts missing: zone") == \
        "Zoning report not saved: lot facts missing: zone."
    assert "open it with Excel, Numbers or any spreadsheet app" in logic.report_message("/x/r.xlsx", True, opened=False)


def test_no_panel_button_does_nothing_silently():
    """Every way out of a panel action that doesn't do its job says why first (say(): the command line and the
    panel's message line). A bare return with nothing said is how the report button failed unseen."""
    import re
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    names = _panel_actions(rhino)
    assert {"open_report", "zoom_to", "hide_massing", "add_to_check", "pick_survey"} <= set(names)
    silent = []
    for name in names:
        m = re.search(r"\ndef " + name + r"\(.*?(?=\n(?:def |class |[A-Z_]+ = ))", rhino, re.S)
        if m is None:
            continue
        lines = [ln for ln in m.group(0).splitlines() if ln.strip()]
        for k, ln in enumerate(lines):
            if ln.strip() in ("return", "return None") and not any("say(" in x for x in lines[max(0, k - 3):k]):
                silent.append(name + ": " + lines[k - 1].strip())
    assert silent == [], silent
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert 'parts["message"] = label(' in ui and "def say(parts, text):" in ui


def test_pick_survey_with_enter_keeps_the_outlined_lot_and_only_no_lot_says_draw_one():
    """Review round 10: Enter, with two lots, said "No lot outline to pick" (the prompt says Enter keeps the one
    outlined)."""
    from design_checker import rhino_logic as logic
    assert logic.survey_pick(2, None, "lot-a") == ("lot-a", None)
    assert logic.survey_pick(2, "lot-b", "lot-a") == ("lot-b", None)
    assert logic.survey_pick(0, None, None)[1].startswith("No lot outline to pick")
    assert logic.survey_pick(2, None, None)[0] is None and "No lot outline" not in logic.survey_pick(2, None, None)[1]
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert 'logic.survey_pick(len(lots), picked, facts.get("lot_id"))' in rhino


def test_the_panel_message_line_is_cleared_by_every_check():
    """Review round 10: "Report saved to …" stayed after later edits and checks."""
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    body = rhino[rhino.index("def run_check("):rhino.index("def _toast(")]
    # round 11: before anything that can fail, so a check that fails early clears it too
    assert body.index('ui.say(STATE.get("panel_parts"), "")') < body.index("facts = current_facts(doc)")
    report = rhino[rhino.index("def open_report():"):rhino.index("\ndef off():")]
    assert report.index("run_check(doc, report=True)") < report.index("say(logic.report_message(path, True")


def test_a_report_that_cant_be_written_keeps_the_check_and_says_why(facts, tmp_path):
    """Review round 10: a report file that couldn't be written (a read-only folder, the file open elsewhere) threw
    away the check's result as well."""
    blocked = tmp_path / "ro"          # a "folder" that is a file can't hold the report on any computer (Windows
    blocked.write_text("", encoding="utf-8")       # ignores a read-only folder's permissions, so chmod proves nothing)
    got = check(MODEL, facts, blocked / "r.xlsx")
    assert got["view"]["items"] and got["report_error"] and "r.xlsx" in got["report_error"]
    assert check(MODEL, facts, tmp_path / "ok.xlsx")["report_error"] is None
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    # round 11: said by run_check, so GordiumCheck (which asks for the report too) is never silent about it
    body = rhino[rhino.index("def run_check("):rhino.index("def _toast(")]
    assert 'if report and result.get("report_error"):' in body and "say(logic.report_message(path, False" in body
    # round 12: "out of date" only for a report that was there before this check, not one its own write left
    assert body.index("had_report = bool(report) and os.path.exists(report_path(doc))") < body.index("result = ask(")
    assert 'result["report_error"], stale=had_report))' in body
    from design_checker import rhino_logic as logic
    assert logic.report_message("/x/r.xlsx", False, "Permission denied", stale=True).endswith(
        "The report already at /x/r.xlsx is from an earlier check: out of date.")


def test_no_viewport_label_is_drawn_under_the_status_box():
    """Coordinator, from the captures (2026-10-20): the status box covered the lot's top length label. The box is
    reserved first; a label it would cover moves just below it."""
    from design_checker import rhino_logic as logic
    box = logic.status_box(1000, ["Gordium · ? 2 need review · 8 comply · 2 not checked", "Draft rulebook · Lot lines",
                                  "Grade: flat at elevation 0'-0\" (existing)", "one more line"])
    x, y, w, h = box
    taken = [box]
    top = logic.clear_spot(taken, 600, 20, 120, 20)                # a label wanted under the box
    assert top >= y + h
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    conduit = rhino[rhino.index("    taken = []"):]
    assert conduit.index("logic.status_box(") < conduit.index("ui.label_at(")


def test_a_report_write_that_fails_half_way_leaves_no_broken_report(facts, tmp_path, monkeypatch):
    """Review round 12: the report was saved straight to its path, so a write failing part way (disk full) left a
    broken file there. It is written beside it and moved into place."""
    import openpyxl

    def broken(self, path):
        open(path, "wb").write(b"PK half a workbook")
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(openpyxl.Workbook, "save", broken)
    got = check(MODEL, facts, tmp_path / "r.xlsx")
    assert "No space left on device" in got["report_error"] and got["view"]["items"]
    assert sorted(p.name for p in tmp_path.iterdir()) == []          # no report, no leftover part file


def test_a_starting_house_is_drawn_on_existing_spot_grades_placed_at_the_lot(facts):
    """Found in Rhino (PR #19's lookup; reachable here with hand-placed spot grades): with existing spot grades away
    from where the house goes, the generator measured the house it had just drawn from those spots, found its
    height "not measurable" and drew nothing. Their plane sets the drawing level; the check still says the ground
    is existing."""
    from design_checker.check import start
    spots = [[0.0, 0.0, 1.0], [73.0, 0.0, 2.0], [73.0, 90.0, 4.0], [0.0, 90.0, 3.0], [36.5, 45.0, 2.5]]
    got = start(MODEL, {**{k: v for k, v in facts.items() if k not in ("ground_is_flat", "grade_elevation")},
                        "grade_from": "spot", "grade_is": "existing", "grade_points": spots})
    assert len(got["floors"]) == 3 and any("drawn on the ground as it is" in n for n in got["notes"])
    assert got["floors"][0]["base"] == pytest.approx(2.5, abs=0.01)          # the spots' plane: their average


def test_the_panel_header_has_no_code_edition_line_but_the_report_keeps_it(facts, tmp_path):
    """MVP list (Ben's team): the panel drops "Ch. 325 as amended through Ord. No. … · District Regulations Chart";
    the report keeps it."""
    import openpyxl
    from design_checker import rhino_logic as logic
    got = check(MODEL, facts, tmp_path / "r.xlsx")
    head = got["view"]["header"]
    assert "Ch. 325" in head["code"]
    lines = logic.panel_header(head)
    assert not any("Ch. 325" in t or "Ordinance" in t or "Ord. No." in t for t in lines["above"] + lines["below"])
    assert lines["above"] == [head["place"]] and lines["below"][0] == head["draft"]
    text = " ".join(str(c) for ws in openpyxl.load_workbook(tmp_path / "r.xlsx").worksheets
                    for row in ws.iter_rows(values_only=True) for c in row if c)
    assert "Ch. 325" in text
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert 'head.get("code")' not in ui and "logic.panel_header(head)" in ui


def test_the_delta_column_is_named_delta_in_the_panel_and_the_report(facts, tmp_path):
    """MVP list: "Margin" renamed "Delta" everywhere the architect sees it."""
    import openpyxl
    from design_checker import rhino_logic as logic
    check(MODEL, facts, tmp_path / "r.xlsx")
    cells = [c for ws in openpyxl.load_workbook(tmp_path / "r.xlsx").worksheets
             for row in ws.iter_rows(values_only=True) for c in row if isinstance(c, str)]
    assert logic.COLUMN_DELTA == "Delta" and "Delta" in cells and "Margin" not in cells
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert '(logic.COLUMN_DELTA, 86)' in ui and '"Margin"' not in ui


def test_on_screen_labels_are_off_by_default_and_a_tick_turns_them_on_per_document():
    """MVP list (Ben's team): the yard and lot-edge labels and the viewport's status box are off unless the
    architect ticks Show on-screen labels, which this document remembers. The yard lines and the red stay."""
    from design_checker import rhino_logic as logic
    assert logic.labels_on({}) is False and logic.labels_on(None) is False
    assert logic.labels_on({"show_labels": True}) is True and logic.labels_on({"show_labels": False}) is False
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    draw = rhino[rhino.index("def draw_screen("):rhino.index("def _status_rows(")]
    assert 'labels = bool(STATE.get("labels_by_doc", {}).get(o.doc))' in draw
    assert "if plan and logic.yard_label_shown(labels, status):" in draw and "if not o.message or not labels:" in draw
    assert "if plan and labels else []" in draw                                   # lot-edge labels: only when on
    assert "d.Draw2dLine(System.Drawing.PointF(a.X, a.Y)" in draw.split("yard_label_shown")[0]   # lines regardless
    tick = rhino[rhino.index("def set_labels("):rhino.index("def set_envelope(")]
    assert "show_labels=bool(on)" in tick and "_save_ui_state(doc, state)" in tick
    check_code = rhino[rhino.index("def run_check("):rhino.index("def _toast(")]
    assert "logic.labels_on(_ui_state(doc))" in check_code and "ui.set_labels_tick(" in check_code
    assert '"labels": set_labels' in rhino
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert 'box.Text = "Show on-screen labels"' in ui and "box.Checked = False" in ui.split("def _labels_box(")[1]


def test_with_labels_off_a_failing_yards_shortfall_still_shows():
    """Coordinator refinement (a): labels off hides passing and neutral labels and the status box, never a failing
    yard's shortfall ("✕ Rear yard 21'-2", needs 22'-6""): it is the live feedback."""
    from design_checker import rhino_logic as logic
    from design_checker.check import plan
    assert logic.yard_label_shown(False, "does_not_comply") and logic.yard_label_shown(True, "complies")
    assert not logic.yard_label_shown(False, "complies") and not logic.yard_label_shown(False, "needs_review")
    items = [{"points": [[0, 0], [0, 21.17]], "status": "does_not_comply", "mark": "✕", "name": "Rear yard",
              "proposed": "21'-2\"", "required": "22'-6\"", "measure": "rear_yard", "reason": ""},
             {"points": [[0, 0], [12, 0]], "status": "complies", "mark": "✓", "name": "Side yard, West",
              "proposed": "12'-0\"", "required": "10'-0\"", "measure": "side_yard_smaller", "reason": ""}]
    got = plan({"lot": {"edges": []}, "buildings": []}, {"outline": [], "holes": []}, {"items": items}, {})
    labels = [y["label"] for y in got["yards"]]
    assert "✕ Rear yard 21'-2\", needs 22'-6\"" in labels and "✓ Side yard, West 12'-0\"" in labels
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert "if plan and logic.yard_label_shown(labels, status):" in rhino


def test_the_code_edition_line_is_in_the_legend_and_the_report_not_the_panel(facts, tmp_path):
    """Coordinator refinement (b): which version of the law was checked stays traceable: the legend ("?") says it."""
    from design_checker import rhino_logic as logic
    head = check(MODEL, facts, tmp_path / "r.xlsx")["view"]["header"]
    assert logic.legend_text(head["code"]).endswith("Checked against: " + head["code"])
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert '"legend": lambda: ui.legend(((STATE.get("last") or {}).get("header") or {}).get("code"))' in rhino


def test_the_delta_says_to_spare_or_short_in_words(facts, tmp_path):
    """Coordinator refinement (c): the sign unmistakable beside the colour, in the panel and the report; the value
    itself (and the answer key's) unchanged."""
    import openpyxl
    from design_checker import rhino_logic as logic
    assert present.delta_words(present.COMPLIES, (2.0, 2.0), "ft", False) == "+2'-0\" to spare"
    assert present.delta_words(present.FAILS, (-1 - 1 / 3, -1 - 1 / 3), "ft", False) == "−1'-4\" short"
    assert present.delta_words(present.COMPLIES, (0.0, 0.0), "ft", False) == "at limit"
    got = check(MODEL, facts, tmp_path / "r.xlsx")
    margins = [i["margin"] for i in got["view"]["items"] if i["margin"]]
    assert margins and not any(m.endswith(("to spare", "short")) for m in margins)        # the data as it was
    cells = [c for ws in openpyxl.load_workbook(tmp_path / "r.xlsx").worksheets
             for row in ws.iter_rows(values_only=True) for c in row if isinstance(c, str)]
    assert any(c.endswith(" to spare") for c in cells)
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert '(i.get("delta") or "")' in ui and "delta_text" not in ui          # settle's words only (round 2)



def test_flat_ground_is_assumed_for_the_mvp_behind_one_switch(facts, tmp_path):
    """MVP list (Ben): no Ground section in the start box; the ground is flat at the lot level and finished, so height
    and stories are checked, each row saying "assuming flat ground", and the report states it. Switched off, the
    Ground row and the spot-grade paths come back (a switch, not a deletion)."""
    import openpyxl
    from design_checker import rhino_logic as logic
    from model_measurement.project import fact_problems
    assert logic.FLAT_GROUND is True
    assert "ground" not in {r["key"] for r in logic.box_rows({})}
    assert "ground" in {r["key"] for r in logic.box_rows({}, flat=False)}                        # the switch
    flat = logic.ground_facts({"ground": {"kind": "spot"}, "no_regrading": False}, 2.0)
    assert flat == {"grade_is": "finished", "ground_is_flat": True, "grade_elevation": 2.0, "grade_from": None,
                    "ground_assumed": "flat"}
    assert logic.ground_facts({"ground": {"kind": "spot"}}, 2.0, flat=False)["grade_from"] == "spot"
    # the check itself at the house's own base (0 here): a ground above it would put part of the house below
    # grade, which the stories rule rightly asks about (a basement or cellar, §325-3; #14's one stories definition)
    level = logic.ground_facts({"ground": {"kind": "spot"}, "no_regrading": False}, 0.0)
    sent = {**facts, **{k: v for k, v in level.items() if v is not None}}
    assert fact_problems(sent) == []
    got = check(MODEL, sent, tmp_path / "r.xlsx")
    rows = {i["name"]: i for i in got["view"]["items"]}
    for name in ("Building height", "Stories"):
        assert rows[name]["status"] == present.COMPLIES and rows[name]["note"] == "assuming flat ground"
        assert logic.row_name(rows[name]) == name + " · assuming flat ground"
    assert "assumed" in got["view"]["header"]["grade"]
    text = " ".join(str(c) for ws in openpyxl.load_workbook(tmp_path / "r.xlsx").worksheets
                    for row in ws.iter_rows(values_only=True) for c in row if c)
    assert "assuming flat ground" in text and "assumed flat (elevation 0'-0\")" in text      # the lot level here
    # round 1: the note is with the item, never under "Why it needs review" on a row that complies
    sheet = openpyxl.load_workbook(tmp_path / "r.xlsx")["Check"]
    head = next(r for r in sheet.iter_rows(values_only=True) if "Why it needs review" in r)
    why, item = head.index("Why it needs review"), head.index("Item")
    row = next(r for r in sheet.iter_rows(values_only=True) if r[item] == "Stories · assuming flat ground")
    assert not row[why]
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert "logic.row_name(i)" in ui


# ---- the plugin and the worker stay in step (audit P1-1) -----------------------------------------------------

def test_a_stray_line_on_the_workers_stdout_never_reaches_the_plugin(facts):
    """A library print() or C code writing to file descriptor 1 inside the worker once put every later answer
    one request behind (a check could show the previous check's result). Answers now have their own channel."""
    import subprocess
    import sys
    noisy = ("import os, design_checker.__main__ as m\n"
             "real = m.answer\n"
             "def answer(r):\n"
             "    print('a library says hello')\n"
             "    os.write(1, b'C code says hello\\n')\n"
             "    return real(r)\n"
             "m.answer = answer\n"
             "m.main(['serve'])\n")
    requests = [{"id": 1, "cmd": "facts", "facts": {"lot_area_sqft": 1}}, {"id": 2, "cmd": "facts", "facts": {}}]
    run = subprocess.run([sys.executable, "-u", "-c", noisy], input="".join(json.dumps(r) + "\n" for r in requests),
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    replies = [json.loads(line) for line in run.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2]
    assert replies[0]["result"]["problems"] and replies[1]["result"]["problems"] == []
    assert "a library says hello" in run.stderr and "C code says hello" in run.stderr


def test_the_plugin_takes_only_this_requests_answer_and_never_waits_forever():
    import queue
    from design_checker import rhino_logic as logic

    def lines(*items):
        q = queue.Queue()
        for item in items:
            q.put(item)
        return q

    assert logic.answer_for(lines('{"id": 7, "ok": true, "result": 1}\n'), 7, 1) == {"id": 7, "ok": True, "result": 1}
    assert logic.answer_for(lines(None), 7, 1) is None                              # the checker stopped
    for wrong in ('{"id": 6, "ok": true, "result": "the last check"}\n', "a library says hello\n", "[1]\n"):
        with pytest.raises(logic.CheckerOutOfStep):                                 # never an earlier answer
            logic.answer_for(lines(wrong, '{"id": 7, "ok": true}\n'), 7, 1)
    with pytest.raises(logic.CheckerOutOfStep, match="no answer in"):               # a hung check: not forever
        logic.answer_for(lines(), 7, 0.05)
    assert logic.ask_limit("check") >= 60
    assert logic.ask_limit("start") >= 120          # the largest building takes work in step with the lot's depth


def test_the_plugin_reads_answers_with_a_time_limit_and_restarts_an_out_of_step_checker():
    """The Rhino side can't run in CI: its source must use the tested logic (no bare readline on the pipe)."""
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    ask = src[src.index("def ask("):src.index("\n\n\n", src.index("def ask("))]
    assert "logic.exchange(" in ask and "_stop_worker()" in ask and "readline" not in ask and "stdin" not in ask
    assert "logic.pipes(p)" in src                  # the pipes served by threads (test_checker_pipes.py)


# ---- the starting building is proven with the checker's own verdict (audit P1-3) -----------------------------

def _jogged_unsurveyed():
    import sys
    sys.path.insert(0, str(REPO / "packages/envelope_builder/tests"))
    from test_start import FACTS, JOGGED, RULES, lot
    facts = {**FACTS, "lot_surveyed": False, "street_line": [[[0, 0], [73, 0]]]}
    return {"units": "ft", "lot": lot(JOGGED), "buildings": [], "problems": []}, facts, RULES


def test_the_generators_proof_counts_a_rule_that_fails_with_the_lot_as_drawn():
    """A 51 x 36 ft house on 106 Ithaca Rd's jogged lot, not yet surveyed: 27.5% of the lot as drawn, over 25%.
    The check says lot coverage fails with the lot as drawn; plain outcome() says only needs review, so the
    generator's proof once accepted it."""
    from design_checker.check import verdict
    from envelope_builder.start import _failing
    site, facts, rules = _jogged_unsurveyed()
    floors = [{"outline": [[11, 28], [62, 28], [62, 64], [11, 64]], "base": 0, "top": 10}]
    assert _failing(site, facts, floors, rules, None) == []                      # plain outcome(): accepted
    assert _failing(site, facts, floors, rules, None, verdict) == ["R-1b.lot_coverage"]


def test_the_checker_proves_every_starting_building_with_its_own_verdict(monkeypatch):
    from design_checker import check as checker
    from envelope_builder import start as generator
    seen = []
    real = generator._failing
    monkeypatch.setattr(generator, "_failing", lambda *a: seen.append(a[-1]) or real(*a))
    site, facts, rules = _jogged_unsurveyed()
    out = checker.largest_legal_building(site, facts, checker.measure(site, facts), rules)
    assert out["floors"] and seen == [checker.verdict]


# ---- an object off the Building layer counts as on the lot when it reaches into it (audit P1-2) ---------------

def test_an_object_reaching_into_the_lot_counts_as_on_it_and_a_neighbour_does_not():
    """The plugin once counted an unmeasured solid only when its bounding box's centre was in the lot's bounding
    box: an addition mostly past the rear line, or a garage straddling a side line, wasn't reported, so lot
    coverage could show COMPLIES. Now its footprint is tested against the lot's outline."""
    import math
    from design_checker.rhino_logic import ON_LOT_REACH, reaches_into_lot

    def rect(x0, y0, x1, y1):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    lot = rect(0, 0, 73, 90)
    on = {"shed wholly on the lot": rect(5, 70, 15, 80),
          "addition 23 x 20 ft on the lot, its centre past the rear line": rect(50, 70, 80, 130),
          "garage straddling the side line, centre outside": rect(65, 20, 85, 40),
          "a neighbour's garage 1 ft over the line": rect(72, 20, 93, 40),
          "a site mesh covering the whole lot": rect(-50, -50, 150, 150)}
    off = {"the neighbour's house touching the side line": rect(73, 20, 93, 40),
           "a neighbour drawn a hair over the line": rect(72.95, 20, 93, 40),
           "the house across the street": rect(10, -60, 40, -20)}
    for name, footprint in on.items():
        assert reaches_into_lot(lot, footprint, ON_LOT_REACH), name
    for name, footprint in off.items():
        assert not reaches_into_lot(lot, footprint, ON_LOT_REACH), name
    turn = math.radians(30)                                  # a rotated lot: its bounding box is far bigger
    rotated = [(x * math.cos(turn) - y * math.sin(turn), x * math.sin(turn) + y * math.cos(turn)) for x, y in lot]
    neighbour = rect(45, 95, 60, 110)       # inside the lot's bounding box (x -45..63, y 0..114), off the lot
    assert not reaches_into_lot(rotated, neighbour, ON_LOT_REACH)
    assert reaches_into_lot(rotated, [(x + 1, y + 1) for x, y in rect(0, 0, 10, 10)], ON_LOT_REACH)
    jogged = [(0, 0), (73, 0), (73, 99.4), (10.5, 99.4), (10.5, 90.3), (0, 90.3)]
    assert not reaches_into_lot(jogged, rect(0, 91, 10, 99), ON_LOT_REACH)       # in the jog's notch: off the lot
    assert reaches_into_lot(jogged, rect(5, 85, 20, 98), ON_LOT_REACH)


def test_the_plugin_tests_left_out_objects_against_the_lot_outline():
    """The Rhino side can't run in CI: its source must use the tested logic, not the bounding-box centre."""
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    body = src[src.index("def _not_included("):src.index("\ndef ", src.index("def _not_included(") + 10)]
    assert "logic.reaches_into_lot(" in body and ".Center" not in body



def test_the_panel_columns_fit_a_rhino_sized_panel_and_wrap():
    """Architect's review (2026-10-21): the dock was 540-620 px, nearly half the screen; Rhino's own panels are
    300-400. At 380 px every column fits (the item takes what is left), and every cell wraps to two lines instead
    of being cut off (drawn cells: a text cell is one line). Each tick has its own row (side by side they ran off).
    In Rhino, panel_width_in_rhino.py measures every cell's text at 380 and 540."""
    import ast
    import re
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    width = int(re.search(r"^PANEL_WIDTH = (\d+)", ui, re.M).group(1))
    columns = re.search(r"^COLUMNS = (\[.*\])", ui, re.M).group(1).replace("logic.COLUMN_DELTA", "'Delta'")
    cols = dict(ast.literal_eval(columns))
    assert 380 <= width <= 420 and sum(cols.values()) + 40 <= 380             # fits the narrowest Rhino panel
    assert "col.Expand = i == 0" in ui and "ef.DrawableCell()" in ui and "ef.TextBoxCell(" not in ui
    assert int(re.search(r"^ROW_HEIGHT = (\d+)", ui, re.M).group(1)) >= 2 * 16           # two lines
    assert "ft.Wrap = ed.FormattedTextWrapMode.Word" in ui
    for tick in ("_envelope_box(actions)", "_massing_box(actions)", "_labels_box(actions, parts)"):
        assert "    layout.Add(row(%s))" % tick in ui, tick


def test_a_yard_label_sits_beside_its_dimension_line_never_on_it():
    """Seen in Rhino (2026-10-21): "Side yard, West 7'-0", needs 10'-0"" was crossed by its own dimension line. The
    label goes beside the line (above a horizontal one, right of a vertical one), and moving it off another label
    never puts it back on the line."""
    from design_checker.rhino_logic import beside_line, clear_spot, crosses
    assert crosses(((0, 10), (100, 10)), 40, 0, 30, 20) and not crosses(((0, 10), (100, 10)), 40, 11, 30, 20)
    assert crosses(((0, 0), (100, 100)), 40, 40, 5, 5) and not crosses(((0, 0), (100, 100)), 60, 0, 30, 20)
    for a, b in [((0, 300), (200, 300)), ((50, 0), (50, 400)), ((0, 300), (200, 260)), ((50, 0), (90, 400)),
                 ((200, 300), (0, 300))]:
        w, h = 180, 20
        x, y = beside_line(a, b, w, h)
        assert not crosses((a, b), x, y, w, h), (a, b)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        assert abs(x + w / 2 - mid[0]) < w and abs(y + h / 2 - mid[1]) < 60           # still next to its line
        taken = [(x - 20, y - 5, w + 40, h + 10)]                                      # another label there first
        top = clear_spot(taken, x, y, w, h, avoid=[(a, b)])
        assert not crosses((a, b), x, top, w, h), (a, b, top)


def test_a_yard_label_is_never_placed_off_the_screen():
    """Seen in Rhino (2026-10-21, the highlight check): with its compass name the label "✕ Side yard, Southwest
    7'-0 5/8", needs 10'-0" (approx.)" (about 400 px) beside a short dimension near the view's left edge went 15 px
    off it. Spots off the screen are never used; with none clear, the first is moved onto it."""
    from design_checker.rhino_logic import place_label
    own = ((150, 411), (205, 411))                          # lot line to wall, near the left of a 1062 x 668 view
    w, h, view = 400, 20, (1062, 668)
    left, top, clear = place_label(own, w, h, view=view)
    assert 0 <= left and left + w <= view[0] and 0 <= top and top + h <= view[1] and clear
    wall = [((0, 380), (1062, 380)), ((0, 440), (1062, 440)), ((420, 0), (420, 668))]   # nowhere beside it is clear
    left, top, clear = place_label(own, w, h, wall, view=view)
    assert 0 <= left and left + w <= view[0] and 0 <= top and top + h <= view[1]
    assert place_label(own, w, h)[0] < 0                    # without the view's size it would have gone off it
    # with no room for it on one line, it goes on two: its name, then its numbers (half as wide, so it fits)
    from design_checker.rhino_logic import label_lines
    assert label_lines("✕ Side yard, Southwest 7'-0 5/8\", needs 10'-0\" (approx.)") == [
        "✕ Side yard, Southwest", "7'-0 5/8\", needs 10'-0\" (approx.)"]
    assert label_lines("75'-10\" (approx.)") == ["75'-10\" (approx.)"]          # a lot edge's length: one line
    assert label_lines("? Rear yard 27'-6 7/8\"") == ["? Rear yard", "27'-6 7/8\""]


def test_a_yard_label_stays_off_every_dimension_and_edge_not_only_its_own():
    """The Top view in Rhino (2026-10-21, after the first fix): the West yard's label sat above its own short
    dimension but across the front yard's vertical dimension. Placement tries the spots beside its line and takes
    the first that crosses no line: other dimensions, the lot's edges, the house's edges."""
    from design_checker.rhino_logic import crosses, place_label
    own = ((265, 230), (310, 230))                          # the West yard, lot line to wall (screen pixels)
    obstacles = [((310, 30), (310, 230)),                    # the front yard's dimension, vertical
                 ((265, 30), (265, 610)), ((265, 30), (735, 30)),   # the lot's west and front edges
                 ((310, 230), (625, 230)), ((310, 230), (310, 435)), ((310, 435), (625, 435))]   # the house
    w, h = 250, 20
    left, top, clear = place_label(own, w, h, obstacles)
    assert clear and not any(crosses(s, left, top, w, h) for s in obstacles + [own]), (left, top)
    assert abs(top + h / 2 - 230) < 40                     # still beside its own line
    # the centred spot (the first tried) crosses the vertical dimension: it was not the one used
    assert crosses(obstacles[0], (265 + 310) / 2 - w / 2, 230 - 6 - h, w, h)
    # another label already there: the next clear spot
    left2, top2, clear2 = place_label(own, w, h, obstacles, taken=[(left, top, w, h)])
    assert clear2 and (left2, top2) != (left, top)
    # a vertical lot edge whose right side is the house: centred on its left, not shifted along its right (Rhino:
    # the west edge's length went under the front edge, where it read as the front edge's)
    edge = ((265, 30), (265, 610))
    house = [((310, 230), (625, 230)), ((310, 230), (310, 435)), ((310, 435), (625, 435))]
    left3, top3, clear3 = place_label(edge, 115, h, house)
    assert clear3 and left3 + 115 <= 265 and abs(top3 + h / 2 - 320) < 1, (left3, top3)
    # boxed in on every side: says so, and the caller falls back to moving it off the other labels
    cage = [((0, y), (1000, y)) for y in range(0, 640, 10)]
    assert place_label(own, w, h, cage)[2] is False


def test_the_suggested_facts_never_answer_the_corner_lot_question():
    """eval-integrity P1-5: the guarantee was pinned only by the plugin's source text (setting corner_lot to False
    in suggested_facts passed). Now the decisions are plain logic, run here on every kind of model."""
    from design_checker import rhino_logic as logic
    square = {"id": "lot", "area": 6570.0, "bottom": 0.0,
              "segments": [((0, 0), (73, 0)), ((73, 0), (73, 90)), ((73, 90), (0, 90)), ((0, 90), (0, 0))]}
    corner_like = {"id": "corner", "area": 9000.0, "bottom": 0.0,           # two street-facing sides, low on screen
                   "segments": [((0, 0), (90, 0)), ((90, 0), (90, 100)), ((90, 100), (0, 100)), ((0, 100), (0, 0))]}
    houses = [{"id": "house", "bottom": 1.0, "volume": 30000.0}, {"id": "shed", "bottom": 0.5, "volume": 900.0}]
    for lots in ([], [square], [square, corner_like], [{**square, "segments": []}]):
        for buildings in ([], houses[:1], houses):
            for zones in ([], ["R-1b"], ["R-1a", "R-1b"]):
                got = logic.suggested_facts("j", zones, lots, buildings)
                assert "corner_lot" in got and got["corner_lot"] is None, (lots, buildings, zones)
                assert got["lot_surveyed"] is False                   # the safe answer: size waits for a survey
    got = logic.suggested_facts("j", ["R-1b"], [square, corner_like], houses)
    assert got["lot_id"] == "corner" and got["street_line"] == [[[0, 0], [90, 0]]]
    assert got["main_building"] == "house" and got["grade_elevation"] == 0.5 and got["zone"] == "R-1b"
    assert logic.suggested_facts("j", [], [square], [])["grade_elevation"] == 0.0     # no building: the lot's level


def test_a_solid_whose_points_dont_outline_it_counts_by_its_box():
    """Review of the P1-2 fix: a sphere's vertices and seam points lie on one meridian, a straight line in plan,
    so their hull has no area and the sphere was left out. A solid always covers some ground: its plan box
    stands in for the outline whenever the points don't give one."""
    import math
    from design_checker.rhino_logic import ON_LOT_REACH, reaches_into_lot
    lot = [(0, 0), (73, 0), (73, 90), (0, 90)]
    seam = [(30 + 5 * math.sin(t * math.pi / 8), 40) for t in range(9)]          # pole to pole, in plan
    assert reaches_into_lot(lot, seam, ON_LOT_REACH, box=(25, 35, 35, 45))
    assert reaches_into_lot(lot, [(30, 40)], ON_LOT_REACH, box=(25, 35, 35, 45))
    assert not reaches_into_lot(lot, [(100, 40), (110, 40)], ON_LOT_REACH, box=(95, 35, 115, 45))   # off the lot
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    body = src[src.index("def _not_included("):src.index("\ndef ", src.index("def _not_included(") + 10)]
    assert "logic.reaches_into_lot(ring, _plan_points(g), reach, box)" in body
    assert "f.PointAt(" in src[src.index("def _plan_points("):]


def test_the_box_pre_filter_never_drops_an_object_that_reaches_the_lot():
    """Review of the P1-2 fix: only objects whose box comes near the lot's get outlined. Any footprint that
    reaches into the lot has a box near the lot's, so the pre-filter can't change an answer."""
    import random
    from design_checker.rhino_logic import ON_LOT_REACH, box_near_lot, reaches_into_lot
    lot = [(0, 0), (73, 0), (73, 90), (0, 90)]
    lot_box = (0, 0, 73, 90)
    rnd = random.Random(7)
    for _ in range(3000):
        pts = [(rnd.uniform(-150, 220), rnd.uniform(-150, 240)) for _ in range(rnd.randint(3, 6))]
        pts = [(x, y) for x, y in pts]
        box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        if reaches_into_lot(lot, pts, ON_LOT_REACH, box):
            assert box_near_lot(box, lot_box, ON_LOT_REACH), pts
    assert not box_near_lot((100, 0, 120, 20), lot_box, ON_LOT_REACH)
    assert box_near_lot((73, 0, 90, 20), lot_box, ON_LOT_REACH)                  # touching: still outlined
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    body = src[src.index("def _not_included("):src.index("\ndef ", src.index("def _not_included(") + 10)]
    assert body.index("logic.box_near_lot(") < body.index("_plan_points(g)")


def test_the_notice_never_hides_the_model_when_there_is_room():
    """Architect's review (2026-10-21): bottom left, the "no longer complies" notice hid the lot's lower edge and
    dimensions. Screen numbers from that Top view (1000 x 640, the lot from y 30 to 610, x 265 to 735); the notice
    690 x 32; the status box top right."""
    from design_checker.rhino_logic import notice_spot
    status = (518, 12, 467, 56)

    def covers(x, y, box, w=690, h=32):
        a, b, c, e = box
        return min(x + w, c) > max(x, a) and min(y + h, e) > max(y, b)
    # framed tight (as it was): every corner covers some of the lot; never the status box
    x, y = notice_spot(1000, 640, 690, 32, (265, 30, 735, 610), [status])
    assert not covers(x, y, (518, 12, 985, 68))
    # framed with room (FRAME_ROOM 0.75: the lot from y 102 to 538): top left is clear of the lot; with the status
    # box there too, bottom left; nothing covered either way
    roomy = (324, 102, 676, 538)
    assert notice_spot(1000, 640, 690, 32, roomy) == (12, 34)
    x, y = notice_spot(1000, 640, 690, 32, roomy, [status])
    assert (x, y) == (12, 640 - 32 - 64) and not covers(x, y, roomy) and not covers(x, y, (518, 12, 985, 68))
    assert notice_spot(1000, 640, 690, 32, None) == (12, 34)                    # no model on screen: top left


def test_the_setup_brings_the_panel_back_with_rhino():
    """A Gordium tab Rhino reopens at launch is empty until something registers the panel: GordiumPanel does only
    that (no check, no checker), install.py adds it, and the guide says, for Mac and Windows, to put it in Rhino's
    startup commands (no setting a script can change). startup_panel_in_rhino.py runs it in Rhino."""
    app = REPO / "apps/rhino_plugin"
    import ast
    tree = ast.parse((app / "gordium_panel.py").read_text(encoding="utf-8"))
    calls = [ast.unparse(n) for n in tree.body[1:] if isinstance(n, ast.Expr)]        # after the docstring
    assert calls == ["sys.path.insert(0, HERE)", "gordium_rhino.register_dock()"], calls   # nothing else runs
    install = (app / "install.py").read_text(encoding="utf-8")
    assert '"GordiumPanel": "gordium_panel.py"' in install and "Run these commands every time Rhino starts" in install
    guide = " ".join((app / "QUICKSTART.md").read_text(encoding="utf-8").split())        # the guide wraps its lines
    assert "Rhino → Settings… → General" in guide and "Tools → Options → General" in guide
    assert guide.count("add the line `GordiumPanel`") == 2 and "Gordium: GordiumPanel -> gordium_panel.py" in guide


def test_the_stored_sample_ring_is_rebuilt_from_the_states_own_outline():
    """Round 1: the stored 106 ring said "generated by code" with its generator on another branch and nothing
    checking it. The State's own ring is stored beside it; here it is placed as the address lookup places it
    (design_checker.lookup_box.frame, PR #19: survey feet to feet from the origin, turned by rotation_deg, its
    corner at 0, 0, to 1/10,000 ft) and must give the stored ring, its street line and its area."""
    import yaml
    stored = yaml.safe_load((REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/lot_outline_tax_map.yaml")
                            .read_text(encoding="utf-8"))
    raw = stored["state_ring_epsg2261_us_survey_ft"]
    assert raw[0] == raw[-1] and len(raw) == len(stored["ring"]) + 1
    us = (1200 / 3937) / 0.3048                             # survey feet to feet (site_lookup.lookup.US_SURVEY_FT)
    ox, oy = stored["frame"]["origin_epsg2261_us_survey_ft"]
    outline = [[round((x - ox) * us, 2), round((y - oy) * us, 2)] for x, y in raw[:-1]]
    a = math.radians(stored["frame"]["rotation_deg"])
    turned = [[x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)] for x, y in outline]
    x0, y0 = min(p[0] for p in turned), min(p[1] for p in turned)
    ring = [[x - x0, y - y0] for x, y in turned]
    assert max(abs(u - v) for p, q in zip(ring, stored["ring"]) for u, v in zip(p, q)) < 2e-4
    n = len(stored["ring"])
    assert stored["street_line"] == [[stored["ring"][i], stored["ring"][(i + 1) % n]] for i in stored["street_edges"]]
    area = abs(sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(raw, raw[1:]))) / 2 * us ** 2
    assert round(area, 1) == stored["area_sf"]


def test_lot_edges_are_labelled_as_an_architect_dimensions_them():
    """The real 106 Ithaca Rd (Rhino, 2026-10-21): sixteen labels, eight of them for the ~10 ft pieces of its curved
    front, crowded the plan and one couldn't find room. Edges carrying on in nearly the same direction are one run,
    labelled with its whole length; a jog under 1 ft isn't labelled. The measurements still use every edge."""
    from design_checker.check import edge_runs, sample_site
    from design_checker import present
    ring = sample_site()["lot"]
    runs = edge_runs([{"points": [ring[i], ring[(i + 1) % len(ring)]]} for i in range(len(ring))])
    assert [(len(pts) - 1, present.feet_inches(length)) for pts, length in runs] == [
        (8, "75'-10\""), (1, "101'-1 1/2\""), (2, "10'-4 1/8\""), (1, "69'-6 1/8\""), (3, "92'-1 3/8\"")]
    rect = [[0, 0], [50, 0], [50, 100], [0, 100]]
    assert [round(length, 6) for _, length in edge_runs([{"points": [rect[i], rect[(i + 1) % 4]]} for i in range(4)])] \
        == [50, 100, 50, 100]
    # round 1: a rounded corner (a 10 ft radius in six 15° pieces) joined the 40 ft front, the arc and the 90 ft side
    # into one "145'-8"" label on the chord across the lot. A run turns less than RUN_TURN_DEG in all.
    from design_checker.check import RUN_TURN_DEG
    arc = [[40 + 10 * math.sin(math.radians(a)), 10 - 10 * math.cos(math.radians(a))] for a in range(0, 91, 15)]
    fillet = [[0, 0]] + arc + [[50, 100], [0, 100]]
    runs = edge_runs([{"points": [fillet[i], fillet[(i + 1) % len(fillet)]]} for i in range(len(fillet))])
    for pts, _ in runs:
        a, b, y, z = pts[0], pts[1], pts[-2], pts[-1]
        first, last = math.atan2(b[1] - a[1], b[0] - a[0]), math.atan2(z[1] - y[1], z[0] - y[0])
        d = abs(first - last) % (2 * math.pi)
        assert math.degrees(min(d, 2 * math.pi - d)) < RUN_TURN_DEG, pts
    assert runs[0][0][0] == [0, 0] and 40 <= runs[0][1] < 45       # the 40 ft front (and a piece of the arc), no side
    assert max(length for _, length in runs) < 101                  # never the 145'-8" across the lot


def test_the_lot_fact_rounds_its_area_down_like_the_lot_area_row():
    """106 Ithaca Rd in Rhino (2026-10-21): the site facts said 7,034 sf (to the nearest) while the Lot area row said
    7,033 sf (rounded down, never in the architect's favour). One rounding for both."""
    from design_checker import rhino_logic as logic
    assert logic.lot_size(7033.5) == "7,033 sf" and logic.lot_size(6570.0) == "6,570 sf"


def test_the_module_docs_say_how_a_row_is_decided():
    """check.py's own description of a row's verdict, and the QUICKSTART's, match row_verdict: a row that passes
    under every reading complies unless its result turns on an open question."""
    from design_checker import check as checking
    assert "turns_on" in checking.__doc__ and "nothing it reads open" not in checking.__doc__
    quick = " ".join((checking.REPO / "apps/rhino_plugin/QUICKSTART.md").read_text(encoding="utf-8").split())
    assert "the row simply complies" in quick and "it still needs review, because only the zoning office" not in quick


def test_the_architects_review_fixes_in_the_panel_and_the_plan():
    """The architect's-eye review of the whole flow (2026-10-21), #15's items: a north arrow turned to true north,
    a closed document's panel let go, the height limit labelled in elevations only, the empty file's start box
    honest about the lot, several buildings saying which is measured with a way to pick it, coverage in % even
    with the footprint unknown, compass names kept when a side couldn't be measured, edge lengths without
    "(approx.)", "needs input" said once, and docked labels wrapping at the panel's width."""
    import ast as ast_
    from design_checker import rhino_logic as logic
    assert logic.north_vector(0) == (pytest.approx(0), 1)
    for turn in (0, 90, 306.3799):                      # whatever the plan's turn, the arrow points to true north
        assert present.compass(*logic.north_vector(turn), turn) == "North", turn
    x, y = logic.north_vector(306.3799)
    assert (round(x, 3), round(y, 3)) == (0.805, 0.593)             # up and to the right on 106 Ithaca Rd's plan
    assert logic.prune_hosts({0: "a", 5: "b", 7: "c"}, [7]) == {0: "a", 7: "c"}
    assert logic.is_elevation_view(True, 0.0) and not logic.is_elevation_view(True, -1.0)
    assert not logic.is_elevation_view(False, 0.0)
    rows = {r["key"]: r for r in logic.box_rows({}, flat=True)}
    assert rows["lot"]["text"] == logic.NO_LOT and rows["lot"]["text"].startswith("no lot yet: draw it")
    assert rows["street"]["text"] == "set from the lot, once there is one"
    drawn = {r["key"]: r for r in logic.box_rows({"lot_area": 7033.8}, flat=True)}
    assert drawn["lot"]["text"].startswith("7,033 sf") and drawn["street"]["text"] == "the highlighted line"
    # coverage keeps its unit (%) with the footprint unknown; a side keeps its compass name when both need the same
    node = ast_.parse("building_area <= 0.25 * lot_area", mode="eval").body
    numbers = present._numbers(node, {"building_area": None, "lot_area": 7033.8}, {}, "")
    assert present._display(*numbers)[:2] == ("—", "25%")
    assert present._side_name("side_yard_smaller", {}, 0, ["Southwest", "Northeast"], True) == "Side yard, Northeast"
    assert present._side_name("side_yard_larger", {}, 0, ["Southwest", "Northeast"], True) == "Side yard, Southwest"
    assert present._side_name("side_yard_smaller", {}, 0, ["Southwest", "Northeast"], False) == "Side yard, narrower"
    # several buildings: the header says which is measured, the waiting rows how to pick it
    head = present.header({"lot_surveyed": True}, {"waiting_main": True}, {}, {})
    assert head["main"] == "Main building: not picked yet"
    assert present.header({"lot_surveyed": True}, {}, {}, {})["main"] is None
    assert present.header({"lot_surveyed": True, "main_building": "x"}, {"main_name": "Garage"}, {}, {})["main"] == \
        "Main building: Garage"
    assert logic.building_name(logic.MASSING, "Floor 3", True) == "the starting house"   # never one of its floors
    assert logic.building_name("Building", "Garage", False) == "Garage"
    assert logic.building_name("Building", "", False) == "a solid on Building"
    assert logic.shorten("short", 20) == "short"
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert '"main": pick_main_building' in rhino and 'button("Main building…", a["main"])' in ui
    assert ')), e["length"],' in rhino and '" (approx.)"' not in rhino        # the length alone, no "(approx.)"
    assert '"needs input"' not in ui
    assert "return label(text, color, bold, size, True, (WRAP_AT or PANEL_WIDTH - 48) if DOCKED" in ui
    assert "WRAP_AT = _wrap_width(parts) if DOCKED" in ui
    assert "d.DrawBrepWires(o.envelope" not in rhino                # its outline only: no isocurve bands


def test_review_round_1_of_the_architects_fixes():
    """arch-fixes review round 1: (1) a side yard is named by compass only when the measuring knows which lines are
    sides (no corner lot, every reading the same pair); (2) citation links keep what tells them apart; (3) a failed
    check clears every overlay field; (4) "Main building" comes from the checker's own stop; (5) the pick hint
    matches that stop exactly; (6) "no lot yet" only without a lot; (7) the height limit qualified without a grade
    plane."""
    import ast as ast_
    from design_checker import rhino_logic as logic, scenarios
    from design_checker.check import check_site, side_lines
    from model_measurement.stops import stop
    sc = scenarios.load(scenarios.paths()[0])
    site, facts, extras = scenarios.site(sc)
    for corner in (True, None):
        f = dict(facts, corner_lot=corner)
        assert side_lines(site, f) is None, corner
        names = sorted(i["name"] for i in check_site(site, f, extras=extras)["view"]["items"]
                       if i["name"].startswith("Side yard"))
        assert names == ["Side yard, narrower", "Side yard, wider"], (corner, names)
    from model_measurement import measure as measuring
    rect = [(0, 0), (50, 0), (50, 100), (0, 100)]           # edges: 0 front, 1 east, 2 back, 3 west
    plain = {**site, "lot": {"id": "lot", "edges": [{"points": [list(rect[i]), list(rect[(i + 1) % 4])]}
                                                    for i in range(4)]}}
    flat = dict(facts, corner_lot=False, street_line=[[[0, 0], [50, 0]]], plan_north_deg=0)
    assert side_lines(plain, flat) == ["East", "West"]
    real = measuring.Lot.readings
    try:                                                     # two readings that name the sides differently: none
        measuring.Lot.readings = lambda self: [("a", [3], [1], [2]), ("b", [3], [2], [1])]
        assert side_lines(plain, flat) is None
    finally:
        measuring.Lot.readings = real
    # (2) every scenario item's links: distinct words for distinct citations, at both panel widths
    for path in scenarios.paths():
        s_, f_, e_ = scenarios.site(scenarios.load(path))
        for item in check_site(s_, f_, extras=e_)["view"]["items"]:
            cites = list(dict.fromkeys(c["citation"] for c in item["detail"].get("cited") or []))
            for room in (352, 192):
                texts = [logic.link_text(c, int(room / 7.5)) for c in cites]
                assert len(set(texts)) == len(texts), (item["name"], room, texts)
                assert all(len(t) <= int(room / 7.5) for t in texts), texts
    assert logic.link_text("§325-8, District Regulations Chart, R-1b, Rear yard column, note 16", 40).endswith("note 16")
    # (3) every overlay field a check sets is reset by _clear
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    tree = ast_.parse(src)
    fn = {n.name: n for n in tree.body if isinstance(n, ast_.FunctionDef)}

    def assigned(node):
        return {t.attr for a in ast_.walk(node) if isinstance(a, ast_.Assign)
                for t in ([*a.targets[0].elts] if isinstance(a.targets[0], ast_.Tuple) else [a.targets[0]])
                if isinstance(t, ast_.Attribute) and isinstance(t.value, ast_.Name) and t.value.id == "o"}
    set_by_check = assigned(fn["run_check"]) | assigned(fn["_draw_plan"])
    cleared = assigned(fn["_clear"])
    assert {"envelope_lines", "height_limit", "north", "unmeasured"} <= cleared
    assert not (set_by_check - cleared - {"doc", "message", "toast"}), set_by_check - cleared
    # (4) the header follows the checker: a detached second building asks for a pick; two solids stacked on one
    # outline are one building to the measuring, so no pick is asked and none is said
    import copy
    house = site["buildings"][0]

    def moved(b, dx=0.0, dz=0.0, bid="b2"):
        b = copy.deepcopy(b)
        b["id"] = bid
        for face in b["faces"]:
            face["points"] = [[x + dx, y, z + dz] for x, y, z in face["points"]]
            face["holes"] = [[[x + dx, y, z + dz] for x, y, z in h] for h in face.get("holes") or []]
        return b
    zs = [p_[2] for face in house["faces"] for p_ in face["points"]]
    xs = [p_[0] for face in house["faces"] for p_ in face["points"]]
    one_more = {"detached": moved(house, dx=-(max(xs) - min(xs)) - 3), "stacked": moved(house, dz=max(zs) - min(zs))}
    got = {}
    for name, b2 in one_more.items():
        v = check_site({**site, "buildings": [house, b2]}, dict(facts, corner_lot=False), extras=extras)["view"]
        got[name] = (v["header"]["main"], any(present.PICK_MAIN_WHY in (i.get("reason") or "") for i in v["items"]))
    assert got == {"detached": ("Main building: not picked yet", True), "stacked": (None, False)}, got
    # (5) the hint only for the exact stop
    assert present.PICK_MAIN_WHY == stop("no_main_building") and present.PICK_MAIN_WHY not in stop("too_many_roofs")
    # (6) a lot whose area couldn't be worked out is still a lot
    rows = {r["key"]: r for r in logic.box_rows({"lot_area": None, "has_lot": True}, flat=True)}
    assert rows["lot"]["text"] != logic.NO_LOT and rows["lot"]["text"].startswith("area not known")
    # (7) the height limit, qualified without the checker's grade plane
    assert logic.height_limit_text(35.0, "35'-0\"") == "Height limit 35'-0\""
    assert "no grade plane yet" in logic.height_limit_text(None, "35'-0\"")
    assert "logic.height_limit_text(" in src
