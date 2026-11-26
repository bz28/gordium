"""The Building Code's sleeping rooms and escape openings (section group 8a of
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md: BCNYS 1031.2): measured as the house code's are,
from the description's own rooms and openings alone (design_checker.egress._escape_openings), never its stairs,
guards or doors, never a house's `has_none` claims, and only for a Building Code law with a rule over them; each
sleeping room then linked to its story and doors (design_checker.escape_openings.link), no new geometry."""

import copy
from pathlib import Path

import pytest
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
    assert "isn't worked out: the routes give no space part(s) for Bedroom" in p["not_measured"]["sleeping_room_story_one_exit"]
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


# --- a sleeping room's own reach to the exits (1031.2 item 1, "access to only one exit"; PR: R-2 sleeping rooms) ----

def _with_space(more=None, confirm=None, within="L1", twice=False):
    parts, desc = _parts()
    space = {"id": "b", "name": "Bedroom", "within": within, "measures": {}, "not_measured": {}, "more": more or {}}
    if confirm:
        space["confirm"] = confirm
    parts["space"] = [space] + ([dict(space)] if twice else [])
    escape_openings.link(parts, desc)
    return parts["sleeping_room"][0]


def test_two_exits_on_the_story_and_every_way_out_of_the_room_reaching_two_is_no_one_exit():
    """BCNYS 1031.2 item 1 asks the escape opening of Group R-2 "in stories with only one exit or access to only one
    exit": where the routes show every door out of the room reaches two separate and distinct exits (1006.3; 202
    COMMON PATH OF EGRESS TRAVEL), the room isn't on such a story: no, with the doors and exits said."""
    p = _with_space({"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}}})
    assert p["measures"]["sleeping_room_story_one_exit"] is False
    assert p["more"]["exits_reached"] == {"d": ["x", "y"]}


@pytest.mark.parametrize("more, why", [
    ({"exits_reached": {"two": False, "why": "the door d reaches one exit (x)"}}, "reaches one exit"),
    ({"exits_reached": {"two": True, "doors": {"d": ["x", "x"]}}}, "reaches two exits"),     # one exit named twice
    ({"exits_reached": {"two": True, "doors": {}}}, "reaches two exits"),                  # no door at all
    ({"exits_reached": {"two": True, "doors": {"d": ["x", "y"], "e": ["x"]}}}, "reaches two exits"),
    ({"exits_reached": {"two": "yes", "doors": {"d": ["x", "y"]}}}, "reaches two exits"),
    ({"exits_reached": ["x", "y"]}, "routes aren't measured"),
    ({}, "routes aren't measured"),
])
def test_anything_short_of_every_way_out_reaching_two_exits_leaves_it_unmeasured(more, why):
    """A wrong no sets aside the escape opening 1031.2 asks (a false pass), so anything but a whole, well-formed two
    leaves the one-exit question open, with the routes' reason."""
    p = _with_space(more)
    assert "sleeping_room_story_one_exit" not in p["measures"]
    assert why in p["not_measured"]["sleeping_room_story_one_exit"], p["not_measured"]


def test_the_rooms_own_space_part_on_its_own_level_only():
    """A space part of another level with the same id, or two parts for the room, never stand in for its own."""
    for kw in ({"within": "L2"}, {"twice": True}):
        p = _with_space({"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}}}, **kw)
        assert "sleeping_room_story_one_exit" not in p["measures"], kw


def test_a_reach_through_a_room_the_routes_read_through_says_the_reading():
    p = _with_space({"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}}},
                    confirm={"space_exit_count": "Gordium's reading: Bedroom through Closet"})
    assert p["measures"]["sleeping_room_story_one_exit"] is False
    assert p["confirm"]["sleeping_room_story_one_exit"] == "Gordium's reading: Bedroom through Closet"


def test_the_rooms_reach_decides_the_one_exit_question_only():
    """Review round 2 (PR 3): the reach fallback ran for every linked measure; a story's fourth-or-higher given as null
    would have taken the room's reach as its value. Now only the one-exit question reads the reach, and a null story
    value is never a value."""
    parts, desc = _parts(story={"id": "L1", "measures": {"story_exit_count": 2,
                                                        "story_fourth_or_higher_above_grade_plane": None}})
    parts["space"] = [{"id": "b", "within": "L1", "measures": {}, "not_measured": {},
                       "more": {"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}}}}]
    escape_openings.link(parts, desc)
    p = parts["sleeping_room"][0]
    assert p["measures"]["sleeping_room_story_one_exit"] is False
    assert "sleeping_room_fourth_or_higher" not in p["measures"] and p["not_measured"]["sleeping_room_fourth_or_higher"]


def test_an_opening_within_no_sleeping_room_read_leaves_every_rooms_count_unknown():
    """An escape opening whose room isn't a sleeping room read (none named, a mistyped room), or that can't be read,
    may be this room's: its count isn't known, never 0 (a wrong fail on 1031.2 once the room's story is placed, as
    main's stated ground now does); one in the room itself still counts."""
    for other in ({"id": "v"}, {"id": "v", "within": "typo"}, {"id": "w", "within": "b"}, "not a part",
                  {"id": "v", "within": ["b"]}, {"id": "v", "within": {"id": "b"}},      # never a crash (review)
                  {"id": "v", "within": "L1"}, {"id": "v", "within": "b", "measures": "big"}):  # a story isn't a room
        p = _linked(openings=[{"id": "w", "within": "b", "measures": {}}, other])
        assert "sleeping_room_escape_openings" not in p["measures"], other
        assert "may be this room's" in p["not_measured"]["sleeping_room_escape_openings"]
    assert _linked()["measures"]["sleeping_room_escape_openings"] == 1


@pytest.mark.parametrize("count", [None, "2", True, float("nan"), float("inf")])
def test_a_story_exit_count_that_isnt_a_number_is_not_known_never_a_crash(count):
    """Parts built by hand (the routes only ever count exits) may give a story's exit count as null or text: the
    room's one-exit question is not known (its rows need review), never a crash and never read as two exits."""
    story = {"id": "L1", "measures": {"story_exit_count": count, "story_fourth_or_higher_above_grade_plane": False}}
    p = _linked(story=story)
    assert "sleeping_room_story_one_exit" not in p["measures"]
    assert "not a number" in p["not_measured"]["sleeping_room_story_one_exit"]


def test_a_huge_whole_exit_count_is_two_or_more_never_a_crash():
    """Review: a whole number too big for a float is still a count (two or more): never a crash."""
    story = {"id": "L1", "measures": {"story_exit_count": 10 ** 400, "story_fourth_or_higher_above_grade_plane": False}}
    p = _linked(story=story)
    assert "sleeping_room_story_one_exit" not in p["measures"]



@pytest.mark.parametrize("measures", [["x"], "text"])
def test_a_storys_measures_that_arent_a_mapping_are_never_a_crash(measures):
    p = _linked(story={"id": "L1", "measures": measures})
    assert "sleeping_room_story_one_exit" not in p["measures"]


def test_a_value_a_room_arrives_with_never_stands_beside_its_reason():
    """Review (a false pass from a hand-built part): a sleeping room part that already says it is on the fourth story
    or higher, linked where its level isn't given, keeps no value: only the link's own, here a reason."""
    parts, desc = _parts()
    parts["sleeping_room"][0]["measures"] = {"sleeping_room_fourth_or_higher": True, "sleeping_room_escape_openings": 9}
    desc["rooms"][0]["level"] = None
    escape_openings.link(parts, desc)
    room = parts["sleeping_room"][0]
    assert "sleeping_room_fourth_or_higher" not in room["measures"]
    assert room["not_measured"]["sleeping_room_fourth_or_higher"]
    assert room["measures"]["sleeping_room_escape_openings"] == 1
    for bad in (["sleeping_room_fourth_or_higher"], "text"):
        parts, desc = _parts()
        parts["sleeping_room"][0]["measures"] = bad
        escape_openings.link(parts, desc)                # never a crash


@pytest.mark.parametrize("count", [1.5, -1, -3])
def test_an_exit_count_that_isnt_a_whole_count_is_not_known(count):
    """Review: 1.5 or -3 exits isn't a count of exits: the one-exit question is not known, never "one exit"."""
    p = _linked(story={"id": "L1", "measures": {"story_exit_count": count}})
    assert "sleeping_room_story_one_exit" not in p["measures"]


@pytest.mark.parametrize("story, space", [
    ({"id": "L1", "measures": ["x"], "not_measured": ["x"]}, None),
    ({"id": ["L1"], "measures": {"story_exit_count": 2}}, None),
    ({"id": "L1", "measures": {"story_exit_count": 2}}, {"id": "b", "within": "L1", "more": ["x"], "not_measured": ["x"]}),
    ({"id": "L1", "measures": {"story_exit_count": 2}},
     {"id": "b", "within": "L1", "more": {"exits_reached": {"two": True, "doors": {"d": [{"a": 1}, {"b": 2}]}}}}),
    ({"id": "L1", "measures": {"story_exit_count": 2}},
     {"id": "b", "within": "L1", "confirm": ["x"], "more": {"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}}}}),
    ({"id": "L1", "measures": {"story_exit_count": 2}}, {"id": ["b"], "within": "L1"}),
])
def test_hand_built_story_and_space_facts_are_never_a_crash(story, space):
    """Review: a story or space part built by hand with fields of the wrong shape leaves what it can't say not
    measured, never a crash; a reach whose exits aren't named exits is never two."""
    parts, desc = _parts(story=story)
    if space is not None:
        parts["space"] = [space]
    escape_openings.link(parts, desc)
    room = parts["sleeping_room"][0]                     # never a crash; a reach to exits not named isn't two
    if space is not None and "doors" in str(space) and "confirm" not in space:
        assert room["measures"].get("sleeping_room_story_one_exit") is not False

