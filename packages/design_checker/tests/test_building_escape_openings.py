"""The Building Code's sleeping rooms and escape openings (section group 8a of
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md: BCNYS 1031.2): measured as the house code's are,
from the description's own rooms and openings alone (design_checker.egress._escape_openings), never its stairs,
guards or doors, never a house's `has_none` claims, and only for a Building Code law with a rule over them; each
sleeping room then linked to its story and doors (design_checker.escape_openings.link), no new geometry."""

import copy
from pathlib import Path

import yaml

from design_checker import code_scope, egress, escape_openings

REPO = Path(__file__).resolve().parents[3]
HOUSE = REPO / "test_data/interior_houses/2_two_story_small_window/house.yaml"


def _description():
    d = yaml.safe_load(HOUSE.read_text(encoding="utf-8"))
    assert any(r.get("sleeping") for r in d["rooms"]) and d["openings"]
    return d


def _law(*rules):
    return {"scope": code_scope.BUILDING, "folder": str(REPO / "no_such_folder"), "rules": list(rules)}


ROOM_RULE = {"id": "t.room", "for_each": "sleeping_room"}
STORY_RULE = {"id": "t.story", "for_each": "story"}


def _rid(parts):
    return {p["id"] for p in parts}


def test_a_building_code_law_reading_sleeping_rooms_gets_them_and_their_openings_as_the_house_code_does():
    d = _description()
    house = egress.measure_interior(d)
    got = egress._measured(_law(STORY_RULE, ROOM_RULE), d, {})
    # each keeps the description's id in `more`, its own id naming its kind (a routes' space has the room's id)
    assert {p["more"]["described_id"] for p in got["parts"]["sleeping_room"]} == _rid(house["parts"]["sleeping_room"])
    assert {p["id"] for p in got["parts"]["sleeping_room"]} == {f"{i} (sleeping room)" for i in
                                                               _rid(house["parts"]["sleeping_room"])}
    for mine, theirs in zip(got["parts"]["emergency_escape_opening"], house["parts"]["emergency_escape_opening"]):
        assert mine["measures"] == theirs["measures"] and mine["within"] == f"{theirs['within']} (sleeping room)"
        assert mine["more"]["described_id"] == theirs["id"]
    assert got["has_none"] == {}
    # a law with no rule over them measures none of them
    plain = egress._measured(_law(STORY_RULE), d, {})
    assert "sleeping_room" not in plain["parts"] and "emergency_escape_opening" not in plain["parts"]


def test_a_room_said_not_to_be_a_sleeping_room_never_becomes_one():
    d = _description()
    for r in d["rooms"]:
        r["sleeping"] = False
    got = egress._escape_openings(d)
    assert got["parts"]["sleeping_room"] == []
    d = _description()
    for r in d["rooms"]:
        r.pop("sleeping", None)                         # not said: no room is taken for a sleeping room, the kind unread
    got = egress._escape_openings(d)
    assert got["parts"]["sleeping_room"] is None and got["problems"]


def test_a_houses_claims_never_reach_a_building():
    d = _description()
    d["has_none"] = {"sleeping_loft": True}
    got = egress._measured(_law(STORY_RULE, ROOM_RULE), d, {})
    assert got["has_none"] == {}


def _parts(level="L1", story=None, doors=None, openings=None):
    story = {"id": "L1", "measures": {"story_exit_count": 2}, "not_measured": {
        "story_fourth_or_higher_above_grade_plane": "Gordium doesn't measure this yet"}} if story is None else story
    return {"sleeping_room": [{"id": "b", "name": "Bedroom", "measures": {}, "not_measured": {}}],
            "story": [story],
            "emergency_escape_opening": [{"id": "w", "within": "b", "measures": {}}] if openings is None else openings,
            "means_of_egress_door": [{"id": "d", "more": {"sides": ["b", "c"]}}] if doors is None else doors}, \
        {"rooms": [{"id": "b", "level": level}]}


def _linked(**kw):
    parts, desc = _parts(**kw)
    escape_openings.link(parts, desc)
    return parts["sleeping_room"][0]


def test_each_sleeping_room_is_linked_to_its_story_its_openings_and_its_doors():
    p = _linked()
    assert p["measures"] == {"sleeping_room_escape_openings": 1, "sleeping_room_story_one_exit": False,
                             "sleeping_room_door_to_outside": False}
    # its story's place not measured: the room's isn't either, with the story's reason (never a guess)
    assert "sleeping_room_fourth_or_higher" not in p["measures"]
    assert p["not_measured"]["sleeping_room_fourth_or_higher"].endswith("Gordium doesn't measure this yet")
    one = {"id": "L1", "measures": {"story_exit_count": 1, "story_fourth_or_higher_above_grade_plane": True}}
    p = _linked(story=one, doors=[{"id": "d", "more": {"sides": ["b", "outside"]}}], openings=[])
    assert p["measures"] == {"sleeping_room_escape_openings": 0, "sleeping_room_story_one_exit": True,
                             "sleeping_room_fourth_or_higher": True, "sleeping_room_door_to_outside": True}


def test_what_isnt_known_of_a_sleeping_room_is_left_unmeasured():
    for kw, unmeasured in (({"level": None}, {"sleeping_room_fourth_or_higher", "sleeping_room_story_one_exit"}),
                           ({"level": "L9"}, {"sleeping_room_fourth_or_higher", "sleeping_room_story_one_exit"}),
                           ({"openings": None}, set()),
                           ({"doors": [{"id": "d", "more": {}}]}, {"sleeping_room_door_to_outside"})):
        parts, desc = _parts(**{k: v for k, v in kw.items() if k != "openings"})
        if "openings" in kw:
            parts["emergency_escape_opening"] = None
            unmeasured = {"sleeping_room_escape_openings"}
        escape_openings.link(parts, desc)
        p = parts["sleeping_room"][0]
        for k in unmeasured:
            assert k not in p["measures"] and p["not_measured"][k], (kw, k)
    parts, desc = _parts()
    parts["means_of_egress_door"] = None
    escape_openings.link(parts, desc)
    assert "sleeping_room_door_to_outside" not in parts["sleeping_room"][0]["measures"]
    # an enclosed space with no room drawn in it stays a maybe, linked to nothing
    parts, desc = _parts()
    parts["sleeping_room"][0]["maybe"] = "an enclosed space with no room drawn in it"
    escape_openings.link(parts, desc)
    assert parts["sleeping_room"][0]["measures"] == {}


def test_the_links_measures_replace_the_house_measurings_not_measured_yet():
    """A sleeping room part from the interior measuring says each of these four is "not measured yet"; the link's own
    value or reason replaces it, so a linked value is never hidden behind a stale reason."""
    parts, desc = _parts()
    parts["sleeping_room"][0]["not_measured"] = {k: "Gordium doesn't measure this yet" for k in escape_openings.NEW_MEASURES}
    escape_openings.link(parts, desc)
    p = parts["sleeping_room"][0]
    assert not set(p["measures"]) & set(p["not_measured"])
    assert set(p["measures"]) == {"sleeping_room_escape_openings", "sleeping_room_story_one_exit",
                                  "sleeping_room_door_to_outside"}
