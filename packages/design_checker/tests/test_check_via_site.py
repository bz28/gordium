"""check() and start() go through the site description (site_json; docs/protocol/), so Rhino's check takes the path
another design tool's will: the worker's check_site and start_site give exactly what check and start give, on both
106 Ithaca Rd models, every recorded session's requests, every scenario and deep-run site as drawn and after its
edit; what the Rhino command left out of a check is in the description's left_out and still makes the check need
review (scenario 06, a garage on the Default layer); a description that says the lot wasn't all looked at
(inventory_complete false) leaves no building measure complying; anything said twice (grade points in the facts,
left-out objects in the extras) is refused; and a report keeps the exact description beside it."""

import copy
import json

import pytest

from design_checker import goldens, replay, scenarios, site_json
from design_checker.__main__ import answer
from design_checker.check import SITE_SUFFIX, check, check_description, check_site, start, start_description
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
    result = check(path, facts, report)
    assert result["report_error"].startswith("the site description beside the report: Permission denied")
    assert list(tmp_path.iterdir()) == []
