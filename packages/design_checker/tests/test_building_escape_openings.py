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


def test_an_opening_within_no_sleeping_room_read_leaves_every_rooms_count_unknown():
    """An escape opening whose room isn't a sleeping room read (none named, a mistyped room), or that can't be read,
    may be this room's: its count isn't known, never 0 (a wrong fail on 1031.2 once the room's story is placed, as
    main's stated ground now does); one in the room itself still counts."""
    for other in ({"id": "v"}, {"id": "v", "within": "typo"}, {"id": "w", "within": "b"}, "not a part",
                  {"id": "v", "within": ["b"]}, {"id": "v", "within": {"id": "b"}},      # never a crash (review)
                  {"id": "v", "within": "L1"}, {"id": "v", "within": "b", "measures": "big"},  # a story isn't a room
                  {"within": "b", "measures": {}}, {"id": 5, "within": "b"}, {"id": "", "within": "b"},
                  {"id": "   ", "within": "b"}):        # no id, not text, blank: an opening that can't be read
        p = _linked(openings=[{"id": "w", "within": "b", "measures": {}}, other])
        assert "sleeping_room_escape_openings" not in p["measures"], other
        assert "may be this room's" in p["not_measured"]["sleeping_room_escape_openings"]
    assert _linked()["measures"]["sleeping_room_escape_openings"] == 1


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


def test_a_room_whose_reasons_cant_be_read_keeps_no_value_it_arrives_with():
    """Confirming round on 4f56db51: a room arriving with a value and reasons that aren't a mapping (null, text)
    keeps none of the value; a room's or door's `more` that isn't a mapping is never a crash."""
    for why in (None, "x"):
        parts, desc = _parts()
        parts["sleeping_room"][0].update(measures={"sleeping_room_fourth_or_higher": True}, not_measured=why)
        escape_openings.link(parts, desc)
        assert parts["sleeping_room"][0]["measures"].get("sleeping_room_fourth_or_higher") is not True, why
    parts, desc = _parts(doors=[{"id": "d", "more": ["x"]}])
    parts["sleeping_room"][0]["more"] = ["x"]
    escape_openings.link(parts, desc)                   # never a crash
    assert "sleeping_room_door_to_outside" not in parts["sleeping_room"][0]["measures"]


def test_hand_built_stories_are_never_a_guess_or_a_crash():
    """Skeptic of a152d6ce: two story parts sharing the room's level id are no one story (never the last one's place,
    a guess); a story exit count that isn't a whole count, story facts of the wrong shape, a room id that isn't
    text: not known, never a crash."""
    parts, desc = _parts()
    parts["story"] = [{"id": "L1", "measures": {"story_fourth_or_higher_above_grade_plane": False}},
                      {"id": "L1", "measures": {"story_fourth_or_higher_above_grade_plane": True}}]
    escape_openings.link(parts, desc)
    assert "sleeping_room_fourth_or_higher" not in parts["sleeping_room"][0]["measures"]
    for count in (None, "2", True, 1.5, -3, float("nan"), float("inf"), ["x"]):
        p = _linked(story={"id": "L1", "measures": {"story_exit_count": count}})
        assert "sleeping_room_story_one_exit" not in p["measures"], count
    assert _linked(story={"id": "L1", "measures": {"story_exit_count": 1}})["measures"][
        "sleeping_room_story_one_exit"] is True
    for story in ({"id": "L1", "measures": 5}, {"id": "L1", "measures": True, "not_measured": ["x"]},
                  {"id": ["L1"], "measures": {}}):
        _linked(story=story)                             # never a crash
    parts, desc = _parts()
    parts["story"] = 5
    parts["sleeping_room"][0]["more"] = {"described_id": ["b"]}
    escape_openings.link(parts, desc)                   # never a crash


def test_an_opening_in_a_room_whose_id_another_part_shares_leaves_the_count_unknown():
    parts, desc = _parts()
    parts["basement"] = [{"id": "b", "measures": {}}]    # the room's id is two parts': which is the opening's isn't known
    escape_openings.link(parts, desc)
    assert "sleeping_room_escape_openings" not in parts["sleeping_room"][0]["measures"]

