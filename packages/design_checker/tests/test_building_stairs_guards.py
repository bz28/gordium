"""The Building Code's stairs and guards (section group 7 of docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md:
1011 stairs, 1014 handrails, 1015 guards, for every occupancy): measured as the house code's are, from the interior
description's own `stairs` and `guards` (design_checker.egress._stairs_and_guards), never its rooms, openings or exit
door, and only for a Building Code law with a rule over them, so a check whose rules read none says nothing about
stairs it doesn't check. A house description with a stair stands in for a non-house building's: the measuring reads
only the stairs and guards, whatever the rooms are."""

import copy
from pathlib import Path

import yaml

from design_checker import code_scope, egress

REPO = Path(__file__).resolve().parents[3]
HOUSE = REPO / "test_data/interior_houses/3_tall_riser/house.yaml"


def _description():
    d = yaml.safe_load(HOUSE.read_text(encoding="utf-8"))
    assert d["stairs"] and d["guards"]
    return d


def _law(*rules):
    return {"scope": code_scope.BUILDING, "folder": str(REPO / "no_such_folder"), "rules": list(rules)}


STAIR_RULE = {"id": "t.stair", "for_each": "stair"}
GUARD_RULE = {"id": "t.guard", "for_each": "open_side"}
STORY_RULE = {"id": "t.story", "for_each": "story"}
BUILDING_OWN = ("stair_in_exit_enclosure", "stair_riser_count", "stair_headroom_past_bottom", "stair_handrail_each_side")


def _without_own(stairs):
    return [{**p, "measures": {k: v for k, v in p["measures"].items() if k not in BUILDING_OWN},
             "not_measured": {k: v for k, v in p["not_measured"].items() if k not in BUILDING_OWN}} for p in stairs]


def test_a_building_code_law_reading_stairs_gets_the_stairs_and_guards_measured_as_the_house_code_does():
    d = _description()
    house = egress.measure_interior(d)
    for rule in (STAIR_RULE, GUARD_RULE):
        got = egress._measured(_law(STORY_RULE, rule), d, {})
        # but for the Building Code's own values of each flight (section group 7c: model_measurement/routes/
        # stair_rooms.py), each one either worked out or given its reason, and every other value as the house's
        assert _without_own(got["parts"]["stair"]) == _without_own(house["parts"]["stair"])
        for p in got["parts"]["stair"]:
            assert all((k in p["measures"]) != (k in p["not_measured"]) for k in BUILDING_OWN), p["id"]
        assert got["parts"]["stair"][0]["measures"]["stair_riser_count"] == \
            house["parts"]["stair"][0]["more"]["stair_risers"]
        assert got["parts"]["guard"] == house["parts"]["guard"]
        assert "story" in got["parts"]                      # the routes' parts are still there


def test_its_rooms_openings_and_doors_are_never_read_as_a_houses():
    # a commercial story's rooms say nothing of sleeping, and it has no escape openings or exit door marked: none of
    # that is a problem of the stairs' and guards' reading
    d = _description()
    d["rooms"] = [{"id": "office", "name": "Office"}]
    d["openings"] = [{"id": "w1", "name": "Window"}]
    d["doors"] = [{"id": "d1", "name": "Door"}]
    d["has_none"] = [{"kind": "sleeping_loft", "source": "the house's own claim"}]
    assert egress.measure_interior(d)["parts"]["stair"][0]["measures"]["stair_serves_sleeping_loft"] is False
    got = egress._stairs_and_guards(d)
    assert set(got["parts"]) == {"stair", "guard"}
    assert got["parts"]["stair"] and got["parts"]["guard"] is not None
    assert got["problems"] == [], got["problems"]
    # a house's claims are never read (review round 1): "no sleeping lofts" sets nothing on a building's stair
    assert all("stair_serves_sleeping_loft" not in s["measures"] for s in got["parts"]["stair"])


def test_stairs_not_given_are_not_read_never_none():
    d = _description()
    del d["stairs"], d["guards"]
    got = egress._measured(_law(STAIR_RULE), d, {})
    assert got["parts"]["stair"] is None and got["parts"]["guard"] is None
    assert any("stairs" in p for p in got["problems"]) and any("guards" in p for p in got["problems"])


def test_a_law_with_no_rule_over_them_measures_none_and_says_nothing_of_them():
    d = _description()
    del d["stairs"], d["guards"]
    got = egress._measured(_law(STORY_RULE), d, {})
    assert "stair" not in got["parts"] and "guard" not in got["parts"]
    assert not any("stairs" in p or "guards" in p for p in got["problems"]), got["problems"]


def test_the_two_readings_are_kept_apart():
    # one check may run a law that reads stairs and one that doesn't: each is measured once, as it asks
    d = _description()
    readings = {}
    with_stairs = egress._measured(_law(STAIR_RULE), copy.deepcopy(d), readings)
    without = egress._measured(_law(STORY_RULE), copy.deepcopy(d), readings)
    assert "stair" in with_stairs["parts"] and "stair" not in without["parts"]
    assert len(readings) == 2
