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
    """Review round 1: a house's claims (here, that the house has no patio covers) set opening measures in the house
    measuring; the building's openings carry none of them."""
    d = _description()
    house = egress.measure_interior({**d, "has_none": [{"kind": "patio_cover", "source": "the test", "reading": False}]})
    claimed = {k for o in house["parts"]["emergency_escape_opening"] for k in o["measures"]} - {
        k for o in egress.measure_interior(d)["parts"]["emergency_escape_opening"] for k in o["measures"]}
    assert claimed, "the claim must set something in the house measuring, or this test pins nothing"
    got = egress._measured(_law(STORY_RULE, ROOM_RULE), {**d, "has_none": [{"kind": "patio_cover", "source": "the test", "reading": False}]}, {})
    assert got["has_none"] == {}
    for o in got["parts"]["emergency_escape_opening"]:
        assert not set(o["measures"]) & claimed


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
    assert p["measures"] == {"sleeping_room_escape_openings": 1, "sleeping_room_door_to_outside": False}
    # review round 1 (a false pass): a story's two exits don't show the room's occupants reach two (each dwelling unit
    # may reach only one, Table 1006.3.4(1)), so the one-exit question stays open there
    assert p["not_measured"]["sleeping_room_story_one_exit"].endswith("isn't worked out")
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
    assert set(p["measures"]) == {"sleeping_room_escape_openings", "sleeping_room_door_to_outside"}


def test_a_room_id_two_rooms_share_counts_no_openings_and_no_doors():
    """Review round 1 (a false pass): two rooms with one id, one a sleeping room: an opening marked in that id may be in
    the other room, so none is counted (nor its doors), and the rule needs review, never a pass on it."""
    parts, desc = _parts()
    desc["rooms"].append({"id": "b", "level": "L1"})
    escape_openings.link(parts, desc)
    p = parts["sleeping_room"][0]
    for k in ("sleeping_room_escape_openings", "sleeping_room_door_to_outside", "sleeping_room_fourth_or_higher"):
        assert k not in p["measures"] and p["not_measured"][k], k



def test_each_escape_opening_carries_its_rooms_three_facts():
    """Section group 8b: an opening's size rules fail only where 1031.2 requires it, which is its room's to say (its
    story's place, one exit, a door to outside): each is copied from the room, or its reason why not; an opening in no
    one sleeping room read gets none of them, so its rows need review."""
    one = {"id": "L1", "measures": {"story_exit_count": 1, "story_fourth_or_higher_above_grade_plane": False}}
    parts, desc = _parts(story=one)
    parts["emergency_escape_opening"][0]["not_measured"] = {k: "Gordium doesn't measure this yet"
                                                           for k in escape_openings.FROM_ROOM}
    parts["emergency_escape_opening"].append({"id": "x", "within": "nowhere", "measures": {}})
    escape_openings.link(parts, desc)
    w, x = parts["emergency_escape_opening"]
    assert w["measures"] == {"opening_room_fourth_or_higher": False, "opening_room_one_exit": True,
                             "opening_room_door_to_outside": False}
    assert not set(w["measures"]) & set(w["not_measured"])
    assert not set(escape_openings.FROM_ROOM) & set(x["measures"])
    assert set(escape_openings.FROM_ROOM) <= set(x["not_measured"])
    parts, desc = _parts()                                   # two exits: not measured on the room, nor on its opening
    escape_openings.link(parts, desc)
    assert parts["emergency_escape_opening"][0]["not_measured"]["opening_room_one_exit"].endswith("isn't worked out")
