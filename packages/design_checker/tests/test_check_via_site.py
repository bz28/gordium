"""check() and start() go through the site description (site_json; docs/protocol/), so Rhino's check takes the path
another design tool's will: the worker's check_site and start_site give exactly what check and start give, on both
106 Ithaca Rd models, every recorded session's requests, every scenario and deep-run site as drawn and after its
edit; what the Rhino command left out of a check is in the description's left_out and still makes the check need
review (scenario 06, a garage on the Default layer); a description that says the lot wasn't all looked at
(inventory_complete false) leaves no building measure complying; anything said twice (grade points in the facts,
left-out objects in the extras) is refused; and a report keeps the exact description beside it."""

import copy
import json
from pathlib import Path

import pytest

from design_checker import goldens, replay, scenarios, site_json
from design_checker.__main__ import answer
from design_checker.check import SITE_SUFFIX, _aside, check, check_description, check_site, start, start_description
from model_measurement.project import load_facts
from model_measurement.read_3dm import read_site
from model_measurement.stops import TOOL_WORDS, stop
from rule_format.place import plugin_place

PLACE = plugin_place()
SAMPLE = PLACE.test_sites / "106_ithaca_rd"
MODELS = [(SAMPLE / f"{m}.3dm", load_facts(SAMPLE / f"{m}_facts.yaml")) for m in ("model", "spreadsheet_design_model")]
COMPLIES = "complies"


def _same(a, b) -> bool:
    return goldens.canonical_text(a) == goldens.canonical_text(b)


def _facts(facts):
    return {k: v for k, v in facts.items() if k != "grade_points"}


def _extras(extras):
    return {k: v for k, v in (extras or {}).items() if k not in site_json.LEFT_OUT_EXTRAS}


def _worker(cmd, **request):
    reply = answer({"id": 1, "cmd": cmd, "protocol": "1.0", **request})
    assert reply["ok"], reply
    return reply["result"]


def _check_site(doc, facts, extras=None, **request):
    """The worker's check_site on a description, sent as JSON text as another tool would."""
    return _worker("check_site", site=site_json.through_json(doc), facts=_facts(facts), extras=_extras(extras),
                   **request)


# ---- the same answers --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path, facts", MODELS, ids=[p.stem for p, _ in MODELS])
def test_a_model_checked_is_the_same_as_its_description_checked(path, facts):
    doc = site_json.read_model(path, facts, inventory_complete=True)
    assert _same(check(path, facts), _check_site(doc, facts))


def test_every_recorded_check_and_start_is_the_same_through_the_worker_s_new_commands():
    found = 0
    for session in replay.sessions():
        for e in replay.entries(session):
            request = dict(e["request"])
            if request["cmd"] not in ("check", "start") or not json.loads(e["reply"])["ok"]:
                continue
            request["model"] = str(session / request["model"])
            facts = request["facts"]
            if request["cmd"] == "check":
                doc = site_json.legacy_description(read_site(request["model"], facts), facts,
                                                   request.get("building_problems"), request.get("extras"))
                new = _check_site(doc, facts, request.get("extras"))
            else:
                doc = site_json.legacy_description({**read_site(request["model"], facts), "buildings": []}, facts)
                new = _worker("start_site", site=site_json.through_json(doc), facts=_facts(facts),
                              floor_to_floor=request.get("floor_to_floor"),
                              design_buffer=request.get("design_buffer"), larger_side=request.get("larger_side"))
            assert _same(answer({**request, "progress": False})["result"], new), (session.name, e["n"])
            found += 1
    assert found >= 5


@pytest.mark.parametrize("path", scenarios.paths(PLACE.test_sites / "scenarios") +
                         scenarios.paths(PLACE.test_sites / "deep_run"), ids=lambda p: p.stem)
def test_every_scenario_checked_through_its_description_is_the_same(path):
    sc = scenarios.load(path)
    for moved in (False, True) if sc.get("then") else (False,):
        site, facts, extras = scenarios.site(sc, moved)
        doc = site_json.legacy_description(site, facts, None, extras)
        assert _same(check_site(site, facts, extras=extras), _check_site(doc, facts, extras)), (path.stem, moved)


@pytest.mark.parametrize("path, facts", MODELS, ids=[p.stem for p, _ in MODELS])
def test_a_start_is_the_same_as_its_description_started(path, facts):
    doc = site_json.legacy_description({**read_site(path, facts), "buildings": []}, facts)
    for _, f2f, buffer, side in goldens.START_OPTIONS:
        new = _worker("start_site", site=site_json.through_json(doc), facts=_facts(facts), floor_to_floor=f2f,
                      design_buffer=buffer, larger_side=side)
        assert _same(start(path, facts, f2f, buffer, side), new)


# ---- what was left out, and what the tool didn't look at --------------------------------------------------------

def _garage_description(touching):
    sc = scenarios.load(PLACE.test_sites / "scenarios/06_detached_garage_not_on_the_building_layer.yaml")
    site, facts, extras = scenarios.site(sc)
    doc = site_json.legacy_description(site, facts, None, extras)
    assert [o["id"] for o in doc["left_out"]] == ["garage"]
    doc["left_out"][0]["touching"] = touching
    return {i["id"]: i for i in _check_site(doc, facts)["view"]["items"]}


def test_a_garage_left_out_is_in_the_description_and_still_needs_review():
    items = _garage_description(False)
    assert items["scope.not_included"]["status"] == "needs_review"
    assert items["scope.not_included"]["objects"] == ["garage"]
    assert items["R-1b.lot_coverage"]["status"] == "needs_review"
    assert items["R-1b.front_yard"]["status"] == COMPLIES        # not touching: the yards stand


def test_a_left_out_object_not_known_to_touch_counts_as_touching():
    items = _garage_description(None)
    for rule in ("R-1b.front_yard", "R-1b.rear_yard", "R-1b.height", "R-1b.stories", "R-1b.lot_coverage"):
        assert items[rule]["status"] == "needs_review", rule
    assert _garage_description(True)["R-1b.front_yard"]["status"] == "needs_review"


BUILDING_MEASURES = {"stories", "building_height", "building_area", "front_yard", "side_yard_larger",
                     "side_yard_smaller", "rear_yard", "front_yard_eaves"}


@pytest.mark.parametrize("name", ["01_every_limit_at_the_line", "06_detached_garage_not_on_the_building_layer"])
def test_a_description_whose_lot_wasnt_all_looked_at_leaves_no_building_measure_complying(name):
    site, facts, extras = scenarios.site(scenarios.load(PLACE.test_sites / f"scenarios/{name}.yaml"))
    doc = site_json.legacy_description(site, facts, None, extras)
    before = {i["id"]: i for i in _check_site(doc, facts)["view"]["items"]}
    after = {i["id"]: i for i in _check_site(dict(doc, inventory_complete=False), facts)["view"]["items"]}
    assert any(i["status"] == COMPLIES and i.get("measure") in BUILDING_MEASURES for i in before.values())
    for k, i in after.items():
        assert not (i["status"] == COMPLIES and i.get("measure") in BUILDING_MEASURES), k
        if k in before and before[k]["status"] == COMPLIES and before[k].get("measure") in BUILDING_MEASURES:
            assert stop("inventory_incomplete") in i["reason"], k
    assert {k for k, i in after.items() if i["status"] == COMPLIES} < {k for k, i in before.items()
                                                                       if i["status"] == COMPLIES}


def test_an_unsent_object_makes_every_building_measure_need_review():
    path, facts = MODELS[1]
    doc = site_json.read_model(path, facts, inventory_complete=True)
    plain = {i["id"]: i for i in _check_site(doc, facts)["view"]["items"]}
    doc["unsent"] = [{"id": "block-7", "layer": "Building", "kind": "block",
                      "problem": {"code": "not_a_solid", "args": {"kind": "a block", "layer": "Building"}}}]
    sent = {i["id"]: i for i in _check_site(doc, facts)["view"]["items"]}
    complying = [k for k, i in plain.items() if i["status"] == COMPLIES and i.get("measure") in BUILDING_MEASURES]
    assert complying and all(sent[k]["status"] != COMPLIES for k in complying)


def test_the_rhino_commands_own_words_for_a_block_go_as_its_words_and_still_need_review():
    path, facts = MODELS[1]
    words = "a block on the Building layer can't be measured yet (explode it)"     # rhino_logic.classify's
    doc = site_json.legacy_description(read_site(path, facts), facts, [words])
    assert doc["unsent"] == [{"id": "Building layer#1", "layer": "Building", "kind": "unknown",
                              "problem": {"code": TOOL_WORDS, "args": {"words": words}}}]
    assert _same(check(path, facts, building_problems=[words]), _check_site(doc, facts))
    surface = "a Surface on the Building layer can't be measured yet (explode it or turn it into a solid)"
    assert site_json.legacy_description(read_site(path, facts), facts, [surface])["unsent"][0]["problem"] == \
        {"code": "not_a_solid", "args": {"kind": "a Surface", "layer": "Building"}}


# ---- one source for each thing: refused when said twice --------------------------------------------------------

def test_the_grade_and_the_left_out_objects_come_only_from_the_description():
    path, facts = MODELS[1]
    doc = site_json.through_json(site_json.read_model(path, facts, inventory_complete=True))
    spots = {"source": "spot", "points": [[0, 0, 100.0], [10, 0, 100.0], [0, 10, 101.0]]}
    for request, reason in (
            ({"facts": {**facts, "grade_points": [[0, 0, 0]]}}, "grade_points belong in the site description"),
            ({"facts": facts, "extras": {"not_included": ["shed"]}}, "not_included belongs in the site description"),
            ({"facts": facts, "extras": {"touching": []}}, "touching belongs in the site description"),
            ({"facts": {**facts, "grade_from": "terrain"}, "site": dict(doc, grade=spots)},
             "grade_from is 'terrain' but the site's grade is 'spot'")):
        reply = answer({"id": 2, "cmd": "check_site", "protocol": "1.0", "site": doc, **request})
        assert not reply["ok"] and reason in reply["error"], reply


def test_a_description_that_isnt_v1_is_refused_by_check_site_and_start_site():
    path, facts = MODELS[1]
    doc = site_json.through_json(site_json.read_model(path, facts))
    bad = dict(doc, colour="red")
    for cmd in ("check_site", "start_site"):
        reply = answer({"id": 3, "cmd": cmd, "protocol": "1.0", "site": bad, "facts": _facts(facts)})
        assert not reply["ok"] and "site description refused: site: unknown field 'colour'" in reply["error"]


def test_extras_naming_objects_that_werent_left_out_are_refused():
    path, facts = MODELS[1]
    with pytest.raises(site_json.SiteRefused, match="shed named as touching"):
        site_json.legacy_description(read_site(path, facts), facts, None, {"not_included": [], "touching": ["shed"]})
    with pytest.raises(ValueError, match="shed named as touching"):
        check(path, facts, extras={"not_included": ["garage"], "ground_like": ["shed"]})


def test_the_spot_grades_go_through_the_description_and_back_into_the_facts():
    sc = scenarios.load(PLACE.test_sites / "scenarios/07_spot_grades_on_a_slope_then_the_house_moves.yaml")
    site, facts, extras = scenarios.site(sc)
    doc = site_json.legacy_description(site, facts, None, extras)
    assert doc["grade"] == {"source": "spot", "points": facts["grade_points"]}
    measured, sent, _ = site_json.for_measuring(site_json.to_site(doc), _facts(facts), {})
    assert sent == facts
    no_source = {k: v for k, v in facts.items() if k != "grade_from"}
    assert site_json.for_measuring(site_json.to_site(site_json.legacy_description(site, no_source)),
                                   _facts(no_source))[1] == no_source       # spot grades: grade_from stays unsaid
    terrain = dict(doc, grade=dict(doc["grade"], source="terrain"))
    assert site_json.for_measuring(site_json.to_site(terrain), _facts(no_source))[1]["grade_from"] == "terrain"


# ---- the report keeps its site --------------------------------------------------------------------------------

def test_a_report_keeps_the_exact_description_it_was_worked_out_from(tmp_path):
    path, facts = MODELS[1]
    report = tmp_path / "house_zoning_report.xlsx"
    doc = site_json.read_model(path, facts, inventory_complete=True)
    result = _check_site(doc, facts, report=str(report))
    assert result["report_error"] is None and report.exists()
    kept = tmp_path / ("house_zoning_report" + SITE_SUFFIX)
    assert json.loads(kept.read_text(encoding="utf-8")) == site_json.through_json(doc)
    assert not list(tmp_path.glob("*.part")) and not list(tmp_path.glob(".*.part"))
    assert _check_site(doc, facts, report=str(report))["report_error"] is None      # over the earlier one: replaced,
    assert sorted(p.name for p in tmp_path.iterdir()) == [kept.name, report.name]   # nothing set aside left over
    again = tmp_path / "again.xlsx"
    check(path, facts, again)                      # Rhino's check keeps its description too
    assert site_json.to_site(json.loads((tmp_path / ("again" + SITE_SUFFIX)).read_text(encoding="utf-8")))
    assert _same(check_description(json.loads(kept.read_text(encoding="utf-8")), _facts(facts))["view"],
                 result["view"])                    # worked out again from the kept description: the same answer


def test_a_description_that_cant_be_kept_takes_its_report_with_it(tmp_path, monkeypatch):
    path, facts = MODELS[1]
    report = tmp_path / "house.xlsx"
    real = type(report).write_text

    def refuse(self, *args, **kwargs):
        if self.name.endswith(SITE_SUFFIX + ".part"):
            raise PermissionError(13, "Permission denied")
        return real(self, *args, **kwargs)
    monkeypatch.setattr(type(report), "write_text", refuse)
    result = check(path, facts, report)
    assert result["report_error"].startswith("the site description beside the report: Permission denied")
    assert list(tmp_path.iterdir()) == []                      # neither the report nor a half-written copy


def test_a_report_is_never_beside_another_checks_site(tmp_path, monkeypatch):
    import design_checker.check as check_module
    path, facts = MODELS[1]
    report = tmp_path / "house.xlsx"
    stale = tmp_path / ("house" + SITE_SUFFIX)
    stale.write_text('{"stale": true}', encoding="utf-8")

    def stopped(*args, **kwargs):            # the checker stopped after the report is in place (Rhino's Cancel)
        raise KeyboardInterrupt
    monkeypatch.setattr(check_module, "envelope", stopped)
    with pytest.raises(KeyboardInterrupt):
        check(path, facts, report)
    assert report.exists() and not stale.exists()           # at worst a report without its site, never a wrong one
    assert not list(tmp_path.glob(".*.part"))
    monkeypatch.undo()
    stale.write_text('{"stale": true}', encoding="utf-8")
    real = type(report).write_text

    def refuse(self, *args, **kwargs):
        if self.name.endswith(SITE_SUFFIX + ".part"):
            raise PermissionError(13, "Permission denied")
        return real(self, *args, **kwargs)
    monkeypatch.setattr(type(report), "write_text", refuse)
    before = report.read_bytes()
    result = check(path, facts, report)
    assert result["report_error"].startswith("the site description beside the report: Permission denied")
    assert sorted(tmp_path.iterdir()) == sorted([report, stale]) and report.read_bytes() == before   # the earlier report,
    assert stale.read_text(encoding="utf-8") == '{"stale": true}'                           # and its site, untouched


def test_a_report_that_cant_be_saved_leaves_the_earlier_report_beside_its_own_site(tmp_path, monkeypatch):
    """Review of PR 74: the earlier site file was deleted before measuring, so a new report that couldn't be moved in
    (on Windows, the earlier one open in Excel) left the earlier report with no site to work it out again from. Now
    the earlier site is set aside only once the new report is saved, and put back when it can't be moved in."""
    import os
    path, facts = MODELS[1]
    report = tmp_path / "house.xlsx"
    doc = site_json.read_model(path, facts, inventory_complete=True)
    assert check_description(site_json.through_json(doc), _facts(facts), report)["report_error"] is None
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert sorted(before) == ["house.site.json", "house.xlsx"]
    real = os.replace

    def locked(src, dst):                    # Windows: a file open in Excel can't be replaced
        if Path(dst) == report:
            raise PermissionError(13, "Permission denied")
        return real(src, dst)
    monkeypatch.setattr(os, "replace", locked)
    moved = copy.deepcopy(doc)
    moved["buildings"] = moved["buildings"][:1]
    result = check_description(site_json.through_json(moved), _facts(facts), report)
    assert result["report_error"].startswith("Permission denied") and result["view"]["items"]
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before   # both, as they were; nothing left over


def test_a_site_that_cant_be_written_means_no_report_is_written(tmp_path, monkeypatch):
    """Review round 2 (PR 4): the report isn't written at all, so nothing ever stands beside the wrong site."""
    import design_checker.check as check_module
    path, facts = MODELS[1]
    report = tmp_path / "house.xlsx"
    real, asked = type(report).write_text, []

    def refuse(self, *args, **kwargs):
        if self.name.endswith(SITE_SUFFIX + ".part"):
            raise PermissionError(13, "Permission denied")
        return real(self, *args, **kwargs)
    real_check_site = check_module.check_site

    def spy(site, facts, name="model", report_path=None, *args, **kwargs):
        asked.append(report_path)
        return real_check_site(site, facts, name, report_path, *args, **kwargs)
    monkeypatch.setattr(type(report), "write_text", refuse)
    monkeypatch.setattr(check_module, "check_site", spy)
    result = check(path, facts, report)
    assert asked == [None] and result["report_error"].startswith("the site description beside the report")
    assert list(tmp_path.iterdir()) == []


def test_rhino_clears_the_site_descriptions_half_written_copy_too(tmp_path):
    """Review round 2 (PR 4): a Cancel in Rhino leaves neither the report's nor its site's part file."""
    import os
    from design_checker import rhino_logic as logic
    from host_source import host_text
    assert logic.SITE_SUFFIX == SITE_SUFFIX
    src = host_text("rhino", "plugin", purpose="wiring")
    fn = src[src.index("def _drop_report_part("):src.index("\ndef off(")]
    space = {"os": os, "logic": logic}
    exec(fn, space)
    report = tmp_path / "house.xlsx"
    parts = [tmp_path / ".house.xlsx.part", tmp_path / (".house" + SITE_SUFFIX + ".part"),
             _aside(tmp_path / ("house" + SITE_SUFFIX))]
    for p in parts + [report]:
        p.write_text("x", encoding="utf-8")
    space["_drop_report_part"](str(report))
    assert sorted(tmp_path.iterdir()) == [report]
    space["_drop_report_part"](str(tmp_path / "gone" / "house.xlsx"))      # never raises


def test_a_refused_request_leaves_the_earlier_report_and_its_site_alone(tmp_path):
    """Review round 3 (PR 4): facts refused before any file is touched."""
    path, facts = MODELS[1]
    report = tmp_path / "house.xlsx"
    doc = site_json.read_model(path, facts, inventory_complete=True)
    check_description(site_json.through_json(doc), _facts(facts), report)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert sorted(before) == ["house.site.json", "house.xlsx"]
    with pytest.raises(ValueError, match="no zone given"):
        check_description(site_json.through_json(doc), {**_facts(facts), "zone": None}, report)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_a_district_with_no_rules_is_refused_on_every_path_before_any_file_is_touched(tmp_path):
    """Main's plain refusal of a district with no rulebook (PR 67's audit: no_rules_for) on the description's paths
    too: check() and check_description refuse it before the site file or the report is written (the earlier report
    and its site stay as they were), and start() and start_description refuse it too (review of the main merge)."""
    path, facts = MODELS[1]
    report = tmp_path / "house.xlsx"
    doc = site_json.read_model(path, facts, inventory_complete=True)
    check_description(site_json.through_json(doc), _facts(facts), report)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    no_rules = "Gordium doesn't have rules for district B-1a yet"
    with pytest.raises(ValueError, match=no_rules):
        check_description(site_json.through_json(doc), {**_facts(facts), "zone": "B-1a"}, report)
    with pytest.raises(ValueError, match=no_rules):
        check(path, {**facts, "zone": "B-1a"}, report)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    with pytest.raises(ValueError, match=no_rules):
        start(path, {**facts, "zone": "B-1a"})
    with pytest.raises(ValueError, match=no_rules):
        start_description(site_json.through_json(doc), {**_facts(facts), "zone": "B-1a"})


def test_a_description_with_no_buildings_whose_lot_wasnt_all_looked_at_leaves_no_building_measure_complying():
    """Review round 4 (PR 4): with no building sent, the stories were 0 and complied, though the tool said it
    hadn't sent everything."""
    path, facts = MODELS[0]
    doc = site_json.read_model(path, facts, inventory_complete=False)
    doc["buildings"] = []
    items = {i["id"]: i for i in _check_site(doc, facts)["view"]["items"]}
    assert items["R-1b.stories"]["status"] == "needs_review"
    for rule in ("R-1b.height", "R-1b.lot_coverage", "R-1b.front_yard", "R-1b.rear_yard"):
        assert items.get(rule, {"status": "needs_review"})["status"] != COMPLIES, rule
    assert not [i for i in items.values() if i["status"] == COMPLIES and any(
        m in i["id"] for m in ("stories", "height", "coverage", "yard", "building_area"))]


def test_a_locked_site_file_is_said_as_the_site_file_and_a_site_that_cant_go_back_is_kept(tmp_path, monkeypatch):
    """Review round 1 (PR 74 fix): the earlier site file locked was said as the report's trouble, and when putting it
    back failed too, its set-aside copy (the earlier report's only one) was deleted."""
    import os
    path, facts = MODELS[1]
    report = tmp_path / "house.xlsx"
    kept = tmp_path / ("house" + SITE_SUFFIX)
    doc = site_json.through_json(site_json.read_model(path, facts, inventory_complete=True))
    check_description(doc, _facts(facts), report)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    real = os.replace

    def locked(src, dst):
        if Path(src) == kept:
            raise PermissionError(13, "Permission denied")
        return real(src, dst)
    monkeypatch.setattr(os, "replace", locked)
    result = check_description(doc, _facts(facts), report)
    assert result["report_error"] == (f"the site description beside the report: Permission denied ({kept}), so the "
                                      f"new report wasn't saved ({report})")
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before

    def stuck(src, dst):                     # the report can't be moved in, and the site can't go back either
        if Path(dst) in (report, kept):
            raise PermissionError(13, "Permission denied")
        return real(src, dst)
    monkeypatch.setattr(os, "replace", stuck)
    assert check_description(doc, _facts(facts), report)["report_error"]
    assert _aside(kept).read_bytes() == before[kept.name] and report.read_bytes() == before[report.name]


def test_a_check_stopped_just_after_its_report_moved_in_never_puts_the_earlier_site_back(tmp_path, monkeypatch):
    """Review round 2 (PR 74 fix): a stop landing just after the report's move had happened put the earlier site file
    back beside the new report."""
    import os
    path, facts = MODELS[1]
    report = tmp_path / "house.xlsx"
    kept = tmp_path / ("house" + SITE_SUFFIX)
    doc = site_json.through_json(site_json.read_model(path, facts, inventory_complete=True))
    check_description(doc, _facts(facts), report)
    assert kept.exists()
    real = os.replace

    def moved_then_stopped(src, dst):
        real(src, dst)
        if Path(dst) == report:
            raise KeyboardInterrupt
    monkeypatch.setattr(os, "replace", moved_then_stopped)
    with pytest.raises(KeyboardInterrupt):
        check_description(doc, _facts(facts), report)
    assert report.exists() and not kept.exists() and not _aside(kept).exists()      # a report with no site, at worst


def test_check_site_takes_the_hosts_day_as_check_does(tmp_path):
    """Main's day of the check (PR 92: `today`, how old the overlays lookup is) goes through the description's path:
    check() passes it on to check_description and check_site, and the worker's check_site command takes it as the
    check command does. With the lookup's "no overlay here" from yesterday the overlays row goes; with no day it
    stays (no lookup counts as recent); a day that isn't one is refused (merge of main, 2026-11-14)."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from test_flood_lookup_age import TODAY, facts_found_on
    from test_overlays_none_found import _model, release_rows
    model = _model(tmp_path, [(0, 0), (60, 0), (60, 110), (0, 110)])
    facts = facts_found_on("2026-11-11")
    doc = site_json.read_model(model, facts, inventory_complete=True)
    dated = _check_site(doc, facts, today=TODAY)
    assert release_rows(dated["view"]) == []
    assert _same(dated["view"], check(model, facts, today=TODAY)["view"])
    assert release_rows(_check_site(doc, facts)["view"]) == ["release.overlays"]
    assert release_rows(check_description(site_json.through_json(doc), _facts(facts), today=TODAY)["view"]) == []
    bad = answer({"id": 1, "cmd": "check_site", "protocol": "1.0", "site": site_json.through_json(doc),
                  "facts": _facts(facts), "today": "12 Nov"})
    assert not bad["ok"] and "today must be the day of the check" in bad["error"]
