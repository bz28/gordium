"""The Building Code's sleeping rooms and escape openings (section group 8a of
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md: BCNYS 1031.2): measured as the house code's are,
from the description's own rooms and openings alone (design_checker.egress._escape_openings), never its stairs,
guards or doors, never a house's `has_none` claims, and only for a Building Code law with a rule over them; each
sleeping room then linked to its story and doors (design_checker.escape_openings.link), no new geometry."""

import copy
import functools
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
        own = {k: v for k, v in mine["measures"].items() if k not in escape_openings.FROM_ROOM}   # 8b: its room's facts
        assert own == theirs["measures"] and mine["within"] == f"{theirs['within']} (sleeping room)"
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


def _separation():
    """The law's own 1007.1.1 rule alone (merge review of #240): two exits count only where placed apart as it asks."""
    return [r for r in _ny_rules() if r["id"] == "general.bc_1007_1_1_remoteness"]


# --- a sleeping room's own reach to the exits (1031.2 item 1, "access to only one exit"; PR: R-2 sleeping rooms) ----

def _with_space(more=None, confirm=None, within="L1", twice=False):
    parts, desc = _parts()
    space = {"id": "b", "name": "Bedroom", "within": within, "measures": {}, "not_measured": {}, "more": more or {}}
    if confirm:
        space["confirm"] = confirm
    parts["space"] = [space] + ([dict(space)] if twice else [])
    escape_openings.link(parts, desc, _separation())
    return parts["sleeping_room"][0]


def test_two_exits_on_the_story_and_every_way_out_of_the_room_reaching_two_is_no_one_exit():
    """BCNYS 1031.2 item 1 asks the escape opening of Group R-2 "in stories with only one exit or access to only one
    exit": where the routes show every door out of the room reaches two separate and distinct exits (1006.3; 202
    COMMON PATH OF EGRESS TRAVEL), the room isn't on such a story: no, with the doors and exits said."""
    p = _with_space({"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}, "remoteness_ratio": 0.6}})
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
        p = _with_space({"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}, "remoteness_ratio": 0.6}}, **kw)
        assert "sleeping_room_story_one_exit" not in p["measures"], kw


def test_a_reach_through_a_room_the_routes_read_through_says_the_reading():
    p = _with_space({"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}, "remoteness_ratio": 0.6}},
                    confirm={"space_exit_count": "Gordium's reading: Bedroom through Closet"})
    assert p["measures"]["sleeping_room_story_one_exit"] is False
    assert p["confirm"]["sleeping_room_story_one_exit"] == "Gordium's reading: Bedroom through Closet"


def test_an_opening_set_aside_on_its_rooms_reading_is_never_a_pass():
    """Merge review (this PR with main's 8b): an opening copies its room's one-exit answer, so where that answer is
    Gordium's reading (the routes run through a room it serves) the opening says the reading too, and its size rule,
    set aside for Group R-2 on it, needs review with the reading said, never a pass; a reading an opening arrives
    with for a room fact is never kept."""
    from rule_format import parts as rows_of
    from rule_format.rulebook import REPO as ROOT, Context, load
    ny = ROOT / "regulations/jurisdictions/new_york/new_york_state_building"
    rule = {r["id"]: r for r in load(ny / "5_building_code_rules/drafted/general.yaml")["rules"]}[
        "general.bc_1031_3_1_escape_opening_min_area"]
    allowed = Context.for_jurisdiction(ny).allowed()
    reading = "Gordium's reading: Bedroom through Closet"
    for confirm, outcome in ((reading, "needs_review"), (None, "pass")):
        parts, desc = _parts(openings=[{"id": "w", "within": "b", "measures": {"opening_net_clear_area": 2.0},
                                        "confirm": {"opening_room_one_exit": "stale"}}])
        space = {"id": "b", "name": "Bedroom", "within": "L1", "measures": {}, "not_measured": {},
                 "more": {"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}, "remoteness_ratio": 0.6}}}
        if confirm:
            space["confirm"] = {"space_exit_count": confirm}
        parts["space"] = [space]
        escape_openings.link(parts, desc, _separation())
        o = parts["emergency_escape_opening"][0]
        assert o["measures"]["opening_room_one_exit"] is False
        assert o["confirm"].get("opening_room_one_exit") == confirm
        [row] = rows_of.rows(rule, {"sleeping_room": parts["sleeping_room"], "emergency_escape_opening": [o]},
                             {"occupancy_group": "R-2"}, allowed)
        assert row["outcome"] == outcome, row
        if confirm:
            assert reading in row["reason"]


@pytest.mark.parametrize("bad", [["x"], "s", None])
def test_a_room_whose_confirm_or_more_isnt_a_mapping_is_never_a_crash(bad):
    """Merge review: a hand-built sleeping room arriving with a `confirm` or `more` that isn't a mapping, its reach
    standing on a reading: never a crash, the reading said."""
    for key in ("confirm", "more"):
        parts, desc = _parts()
        parts["sleeping_room"][0][key] = bad
        parts["space"] = [{"id": "b", "within": "L1", "measures": {}, "not_measured": {},
                           "more": {"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}, "remoteness_ratio": 0.6}},
                           "confirm": {"space_exit_count": "Gordium's reading"}}]
        escape_openings.link(parts, desc, _separation())
        room = parts["sleeping_room"][0]
        assert room["confirm"]["sleeping_room_story_one_exit"] == "Gordium's reading", key
        assert room["more"]["exits_reached"] == {"d": ["x", "y"]}, key


def test_a_reading_a_room_arrives_with_for_a_linked_fact_is_never_kept():
    """Merge review: like its values, a reading a sleeping room arrives with for one of the link's facts is the
    link's to give: dropped where the link gives none (and so never copied onto its openings); its other readings
    stay."""
    parts, desc = _parts()
    parts["sleeping_room"][0]["confirm"] = {"sleeping_room_story_one_exit": "stale", "other": "kept"}
    escape_openings.link(parts, desc)
    assert parts["sleeping_room"][0]["confirm"] == {"other": "kept"}
    assert "opening_room_one_exit" not in (parts["emergency_escape_opening"][0].get("confirm") or {})


def test_the_rooms_reach_decides_the_one_exit_question_only():
    """Review round 2 (PR 3): the reach fallback ran for every linked measure; a story's fourth-or-higher given as null
    would have taken the room's reach as its value. Now only the one-exit question reads the reach, and a null story
    value is never a value."""
    parts, desc = _parts(story={"id": "L1", "measures": {"story_exit_count": 2,
                                                        "story_fourth_or_higher_above_grade_plane": None}})
    parts["space"] = [{"id": "b", "within": "L1", "measures": {}, "not_measured": {},
                       "more": {"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}, "remoteness_ratio": 0.6}}}]
    escape_openings.link(parts, desc, _separation())
    p = parts["sleeping_room"][0]
    assert p["measures"]["sleeping_room_story_one_exit"] is False
    assert "sleeping_room_fourth_or_higher" not in p["measures"] and p["not_measured"]["sleeping_room_fourth_or_higher"]


def test_each_escape_opening_carries_its_rooms_three_facts():
    """Section group 8b: an opening's size rules fail only where 1031.2 requires it, which is its room's to say (its
    story's place, one exit, a door to outside): each is copied from the room, or its reason why not; an opening in no
    one sleeping room read gets none of them, so its rows need review (8d: whether another opening complies is worked
    out from the law's limits, test_which_openings_comply_*)."""
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
    # the room's reason, which this PR goes on to give the routes' why (here: no space part for the room)
    assert parts["emergency_escape_opening"][0]["not_measured"]["opening_room_one_exit"].endswith(
        "isn't worked out: the routes give no space part(s) for Bedroom")


LIMITS = [{"id": i, "for_each": "emergency_escape_opening", "within": "sleeping_room", "when_none": "not_applicable",
           "limit": lim, "check": f"({lim}) or opening_room_fourth_or_higher"}
          for i, lim in (("a", "opening_net_clear_area >= 5.7"), ("h", "opening_net_clear_height >= 24"))]


def _two(first, second, rules=LIMITS):
    parts, desc = _parts(openings=[{"id": "w", "within": "b", "measures": dict(first)},
                                   {"id": "v", "within": "b", "measures": dict(second)}])
    escape_openings.link(parts, desc, rules)
    return parts["sleeping_room"][0], parts["emergency_escape_opening"]


def test_which_openings_comply_counts_only_known_ones():
    """Section group 8d: an opening complies only where every limit is known true; any known false, it doesn't; else not
    known. The room counts the known compliant ones (not measured where none is known to and one is unknown), and each
    opening says whether another in its room is known to comply."""
    good, small, unknown = {"opening_net_clear_area": 6, "opening_net_clear_height": 30}, \
        {"opening_net_clear_area": 4, "opening_net_clear_height": 30}, {"opening_net_clear_height": 30}
    room, (w, v) = _two(small, good)                            # the coordinator's case 1
    assert room["measures"]["sleeping_room_compliant_openings"] == 1
    assert w["measures"]["opening_room_other_compliant"] is True and v["measures"]["opening_room_other_compliant"] is False
    room, (w, v) = _two(small, small)                           # the coordinator's case 2
    assert room["measures"]["sleeping_room_compliant_openings"] == 0
    assert w["measures"]["opening_room_other_compliant"] is False
    room, (w, v) = _two(small, unknown)                         # never compliant on an unknown
    assert "sleeping_room_compliant_openings" not in room["measures"]
    assert "opening_room_other_compliant" not in w["measures"]
    room, (w, v) = _two(good, unknown)
    assert room["measures"]["sleeping_room_compliant_openings"] == 1
    room, (w, v) = _two(good, good, rules=[])                   # no limits read: nothing complies on nothing
    assert "sleeping_room_compliant_openings" not in room["measures"]
    assert escape_openings.complies({"measures": good}, escape_openings.limits(LIMITS)) is True
    assert escape_openings.complies({"measures": small}, escape_openings.limits(LIMITS)) is False
    assert escape_openings.complies({"measures": unknown}, escape_openings.limits(LIMITS)) is None
    assert escape_openings.complies({"measures": good}, []) is None


GOOD = {"opening_net_clear_area": 6, "opening_net_clear_height": 30, "opening_net_clear_width": 24,
        "opening_sill_height": 40, "opening_is_door": False, "opening_below_grade": False}
SMALL = {**GOOD, "opening_net_clear_area": 4, "opening_at_grade": False}


def _room_check(first, second):
    """The two openings linked with the law's own rules (their limits), then 1031.2's row for the room and 1031.3.1's
    rows for the openings, Group R-3, no sprinkler system, the room below the fourth story with no door to outside."""
    from rule_format import parts as part_rules
    from rule_format.rulebook import Context, load
    ny = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
    rules = {r["id"]: r for r in load(ny / "5_building_code_rules/drafted/general.yaml")["rules"]}
    one = {"id": "L1", "measures": {"story_exit_count": 1, "story_fourth_or_higher_above_grade_plane": False}}
    parts, desc = _parts(story=one, openings=[{"id": "w", "within": "b", "measures": dict(first)},
                                              {"id": "v", "within": "b", "measures": dict(second)}])
    escape_openings.link(parts, desc, list(rules.values()))
    given = {"occupancy_group": "R-3", **{f"sprinklered_903_3_1_{n}": False for n in (1, 2, 3)}}
    allowed = Context.for_jurisdiction(ny).allowed()
    room = part_rules.rows(rules["general.bc_1031_2_escape_opening_where_required"], parts, given, allowed)
    sizes = part_rules.rows(rules["general.bc_1031_3_1_escape_opening_min_area"], parts, given, allowed)
    return [r["outcome"] for r in room], {r["id"]: r["outcome"] for r in sizes}


def test_a_small_opening_beside_a_compliant_one_passes_1031_2_and_every_small_one_fails_it():
    """The coordinator's two cases (section group 8d), through the law's own rules: one marked opening too small and
    another that complies: 1031.2 passes, and the small one needs review on its size, never a fail (it isn't the one
    relied on); every marked opening too small: 1031.2 fails where it requires one, and so does each small one."""
    room, sizes = _room_check(SMALL, GOOD)
    assert room == ["pass"] and sizes == {"w": "needs_review", "v": "pass"}
    room, sizes = _room_check(SMALL, SMALL)
    assert room == ["fail"] and sizes == {"w": "fail", "v": "fail"}
    room, sizes = _room_check(SMALL, {k: v for k, v in GOOD.items() if k != "opening_sill_height"})   # one not known
    assert room == ["needs_review"] and sizes["w"] == "needs_review"


WELL_SHORT = {**GOOD, "opening_below_grade": True, "area_well_area": 8, "area_well_projection": 36, "area_well_width": 36,
              "area_well_depth": 30, "opening_fully_openable": True, "area_well_other_encroachment": 0,
              "area_well_ladder_encroachment": 0}


def test_an_area_well_short_of_its_limit_keeps_the_opening_from_counting():
    """Review round 1 of 8d: the well and ladder limits count too. An opening below grade that meets 1031.3 but whose
    well is under 9 sq ft doesn't comply: beside a compliant one, 1031.2 passes and its well row needs review; alone,
    1031.2 fails where it requires one."""
    room, _ = _room_check(WELL_SHORT, GOOD)
    assert room == ["pass"]
    room, _ = _room_check(WELL_SHORT, WELL_SHORT)
    assert room == ["fail"]
    assert escape_openings.complies({"measures": WELL_SHORT}, escape_openings.limits(_ny_rules())) is False
    assert escape_openings.complies({"measures": {**WELL_SHORT, "area_well_area": 9}},
                                    escape_openings.limits(_ny_rules())) is True


def test_a_rule_over_escape_openings_with_no_limit_leaves_compliance_unknown():
    """Review round 1 of 8d: an escape-opening rule without a limit has a requirement no count can read, so no opening
    is counted compliant (never past a rule whose requirement isn't known)."""
    rules = _ny_rules() + [{"id": "t.new", "for_each": "emergency_escape_opening", "check": "opening_operable"}]
    assert escape_openings.limits(rules) == []
    parts, desc = _parts(openings=[{"id": "w", "within": "b", "measures": dict(GOOD)}])
    escape_openings.link(parts, desc, rules)
    assert "sleeping_room_compliant_openings" not in parts["sleeping_room"][0]["measures"]


@functools.lru_cache(maxsize=1)
def _ny_rulebook():
    from rule_format.rulebook import load
    return tuple(load(REPO / "regulations/jurisdictions/new_york/new_york_state_building/5_building_code_rules/"
                             "drafted/general.yaml")["rules"])


def _ny_rules():
    return list(_ny_rulebook())



def test_a_rule_that_doesnt_apply_where_1031_2_does_leaves_compliance_unknown():
    """Review round 2 of 8d: a limit is held to every opening only because its rule applies wherever 1031.2 does. A
    rule applying more narrowly (another occupancy list, or one reading the opening) would hold an opening to a
    requirement the law doesn't place on it: no opening counts, never a wrong fail."""
    rules = _ny_rules()
    narrow = [dict(r, applies_when='occupancy_group in ["R-2"]') if r["id"].endswith("min_height") else r for r in rules]
    assert escape_openings.limits(rules) and escape_openings.limits(narrow) == []


def test_openings_the_rows_refuse_never_decide_a_rooms_count():
    """Review round 2 of 8d: two openings sharing an id (one described twice, its sizes in conflict), an opening that
    can't be read, or one whose figure stands on a reading to confirm, is never counted, either way: the room's count
    isn't known, so 1031.2 needs review, never a pass on the compliant twin or a fail beside an unreadable one."""
    def room(openings):
        parts, desc = _parts(openings=openings)
        escape_openings.link(parts, desc, _ny_rules())
        return parts["sleeping_room"][0]
    twins = room([{"id": "w", "within": "b", "measures": dict(GOOD)}, {"id": "w", "within": "b", "measures": dict(SMALL)}])
    assert "sleeping_room_compliant_openings" not in twins["measures"]
    bad = room([{"id": "w", "within": "b", "measures": dict(SMALL)}, {"id": "v", "within": "b", "measures": "big"}])
    assert "sleeping_room_compliant_openings" not in bad["measures"]
    told = room([{"id": "w", "within": "b", "measures": dict(GOOD),
                  "confirm": {"opening_net_clear_area": "Gordium's reading"}}])
    assert "sleeping_room_compliant_openings" not in told["measures"]
    plain = room([{"id": "w", "within": "b", "measures": dict(GOOD)}])
    assert plain["measures"]["sleeping_room_compliant_openings"] == 1


def test_an_unknown_count_names_the_opening_and_the_figures_missing():
    """Review round 2 of 8d: the reason a person sees names what to give, never only "a figure not measured"."""
    parts, desc = _parts(openings=[{"id": "w", "name": "North window", "within": "b",
                                    "measures": {k: v for k, v in GOOD.items() if k != "opening_net_clear_area"}}])
    escape_openings.link(parts, desc, _ny_rules())
    why = parts["sleeping_room"][0]["not_measured"]["sleeping_room_compliant_openings"]
    assert "North window" in why and "opening_net_clear_area" in why


def test_a_limit_its_own_rules_validation_refuses_never_counts():
    """Review round 3 of 8d (a false pass): a rule whose limit drifted from its check (refused by rule_format) gives
    no limits at all, so a 5.2 sq ft window (5.7 required off grade) can't pass 1031.2 on the drifted 5."""
    rules = _ny_rules()
    drift = [dict(r, limit=r["limit"].replace("5.7", "5")) if r["id"].endswith("min_area") else r for r in rules]
    assert escape_openings.limits(rules) and escape_openings.limits(drift) == []


def _small_beside(other):
    """1031.2's row for the room and 1031.3.1's row for a small opening w in it, beside `other` (R-3, no
    sprinklers, the room on a one-exit story below the fourth)."""
    from rule_format import parts as part_rules
    from rule_format.rulebook import Context
    ny = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
    rules = {r["id"]: r for r in _ny_rules()}
    one = {"id": "L1", "measures": {"story_exit_count": 1, "story_fourth_or_higher_above_grade_plane": False}}
    parts, desc = _parts(story=one, openings=[{"id": "w", "within": "b", "measures": dict(SMALL)}, other])
    escape_openings.link(parts, desc, list(rules.values()))
    given = {"occupancy_group": "R-3", **{f"sprinklered_903_3_1_{n}": False for n in (1, 2, 3)}}
    allowed = Context.for_jurisdiction(ny).allowed()
    room = part_rules.rows(rules["general.bc_1031_2_escape_opening_where_required"], parts, given, allowed)
    sizes = part_rules.rows(rules["general.bc_1031_3_1_escape_opening_min_area"], parts, given, allowed)
    return [r["outcome"] for r in room], {r.get("id"): r["outcome"] for r in sizes}


def test_an_opening_that_may_be_the_rooms_never_lets_it_or_its_neighbour_fail():
    """Review round 3 of 8d (a wrong fail): an opening within no room read (none named, a mistyped id), or one that
    can't be read (beside the small one, or with no `within`), could be the room's compliant one: 1031.2 and the
    small opening's row need review, never a fail."""
    for other in ({"id": "v", "measures": dict(GOOD)}, {"id": "v", "within": "typo", "measures": dict(GOOD)},
                  {"id": "v", "within": "b", "measures": "big"}, {"id": "v", "measures": "big"},
                  {"id": "w", "within": "b", "measures": dict(GOOD)}):
        room, sizes = _small_beside(other)
        assert room == ["needs_review"], other
        assert sizes.get("w") != "fail", other
    room, sizes = _small_beside({"id": "v", "within": "b", "measures": dict(SMALL)})
    assert room == ["fail"] and sizes["w"] == "fail"


def test_the_unknown_reason_names_only_the_figures_that_left_it_unknown():
    """Review round 3 of 8d: an opening above grade isn't asked for its area well's figures (its well limits hold
    whatever they are), so the reason names only the one figure missing."""
    parts, desc = _parts(openings=[{"id": "w", "name": "North window", "within": "b",
                                    "measures": {k: v for k, v in GOOD.items() if k != "opening_net_clear_area"}}])
    escape_openings.link(parts, desc, _ny_rules())
    why = parts["sleeping_room"][0]["not_measured"]["sleeping_room_compliant_openings"]
    assert "opening_net_clear_area" in why and "area_well" not in why


def test_a_rule_held_within_another_kind_leaves_compliance_unknown():
    """Review round 4 of 8d: an opening rule within another kind (a basement-only requirement) isn't a sleeping room
    opening's, so no limits are held (never a wrong fail on a requirement the room's opening doesn't have)."""
    rules = _ny_rules()
    other = [dict(r, within="basement") if r["id"].endswith("min_area") else r for r in rules]
    assert escape_openings.limits(rules) and escape_openings.limits(other) == []


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


def test_an_opening_never_keeps_a_room_fact_of_its_own():
    """Review of the unreadable-opening skip (a false pass): an opening that carries a room fact itself (here, that its
    room is on the fourth story or higher) and can't be read keeps none of it: the room's facts are only the room's."""
    one = {"id": "L1", "measures": {"story_exit_count": 1, "story_fourth_or_higher_above_grade_plane": False}}
    for why in (None, [], {}):
        parts, desc = _parts(story=one, openings=[{"id": "v", "within": "b", "not_measured": why, "measures": {
            "opening_net_clear_area": 4.0, "opening_room_fourth_or_higher": True}}])
        escape_openings.link(parts, desc)
        assert parts["emergency_escape_opening"][0]["measures"].get("opening_room_fourth_or_higher") is not True, why


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
     {"id": "b", "within": "L1", "confirm": ["x"], "more": {"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}, "remoteness_ratio": 0.6}}}),
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


def test_an_opening_takes_only_its_rooms_own_facts():
    """Review (8b): an opening copies a room fact only where the room has it and no reason beside it, and a room that
    can't be read gives its openings none (never a crash): a stale room value never sets an opening's rule aside."""
    one = {"id": "L1", "measures": {"story_exit_count": 1, "story_fourth_or_higher_above_grade_plane": False}}
    for bad in (["sleeping_room_fourth_or_higher"], "text"):
        parts, desc = _parts(story=one, openings=[{"id": "w", "within": "b", "measures": {}}, {"id": "v"}])
        parts["sleeping_room"][0]["measures"] = bad
        escape_openings.link(parts, desc)
        assert not set(escape_openings.FROM_ROOM) & set(parts["emergency_escape_opening"][0]["measures"]), bad
    rooms = [{"id": "b", "measures": {"sleeping_room_fourth_or_higher": True},
              "not_measured": {"sleeping_room_fourth_or_higher": "not known"}}]
    openings = [{"id": "w", "within": "b", "measures": {}, "not_measured": {}}]
    escape_openings._to_openings(rooms, openings)
    assert "opening_room_fourth_or_higher" not in openings[0]["measures"]
    assert openings[0]["not_measured"]["opening_room_fourth_or_higher"] == "not known"


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


def test_a_room_that_cant_be_read_or_a_count_that_isnt_one_gives_its_openings_nothing():
    """Confirming round on 82651de3: a room holding all four facts but reasons that can't be read gives its openings
    none of them (8d: the other-openings fact is the compliance count's, not the room's)."""
    full = {"sleeping_room_fourth_or_higher": True, "sleeping_room_story_one_exit": True,
            "sleeping_room_door_to_outside": False, "sleeping_room_escape_openings": 1}
    for why in ("text", ["sleeping_room_fourth_or_higher"], None):
        openings = [{"id": "w", "within": "b", "measures": {}, "not_measured": {}}]
        escape_openings._to_openings([{"id": "b", "measures": dict(full), "not_measured": why}], openings)
        assert not set(escape_openings.FROM_ROOM) & set(openings[0]["measures"]), why


def test_a_sleeping_room_whose_id_isnt_text_is_never_a_crash():
    """8d merge review: a room whose id is a list or a mapping counts no compliant openings (not known), never a
    crash."""
    for rid in (["b"], {"id": "b"}):
        parts, desc = _parts(openings=[])
        parts["sleeping_room"][0]["id"] = rid
        escape_openings.link(parts, desc, _ny_rules())
        assert "sleeping_room_compliant_openings" not in parts["sleeping_room"][0]["measures"]


def test_an_opening_whose_room_isnt_text_is_never_a_crash():
    """#242's merge review (reachable from a description: an opening's `room` given as a list or a mapping): the
    count and each opening's other-compliant fact are not known, never a crash."""
    for where in (["b"], {"id": "b"}):
        parts, desc = _parts(openings=[{"id": "w", "within": "b", "measures": dict(GOOD)},
                                       {"id": "v", "within": where, "measures": dict(GOOD)}])
        escape_openings.link(parts, desc, _ny_rules())
        assert "sleeping_room_compliant_openings" not in parts["sleeping_room"][0]["measures"]
        for o in parts["emergency_escape_opening"]:
            assert "opening_room_other_compliant" not in (o.get("measures") or {}), where



def _reach_check(openings, reading=None, ratio=0.6, system="none"):
    """Merge review of #240 on 8d: a Group R-2 sleeping room on a story of two exits whose routes show every way out
    reaching two (no escape opening asked by 1031.2 item 1), with the law's own rules, ids as the pipeline gives them
    (the room's own id apart from the routes' space part). Returns 1031.2's outcome, each opening's outcomes over the
    twelve opening rules, and the room's compliant count (or its reason)."""
    from rule_format import parts as part_rules
    from rule_format.rulebook import Context, load
    ny = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
    rules = load(ny / "5_building_code_rules/drafted/general.yaml")["rules"]
    room = {"id": "b (sleeping room)", "name": "Bedroom", "measures": {}, "not_measured": {}, "more": {"described_id": "b"}}
    space = {"id": "b", "name": "Bedroom", "within": "L1", "measures": {}, "not_measured": {},
             "more": {"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}, "remoteness_ratio": ratio}}}
    if reading:
        space["confirm"] = {"space_exit_count": reading}
    parts = {"sleeping_room": [room], "space": [space],
             "story": [{"id": "L1", "measures": {"story_exit_count": 2, "story_fourth_or_higher_above_grade_plane": False}}],
             "emergency_escape_opening": [dict(o, within="b (sleeping room)") for o in openings],
             "means_of_egress_door": [{"id": "d", "more": {"sides": ["b", "c"]}}]}
    building = {"sprinkler_system": system} if system else {}
    escape_openings.link(parts, {"rooms": [{"id": "b", "level": "L1"}], "building": building}, rules)
    given = {"occupancy_group": "R-2", **{f"sprinklered_903_3_1_{n}": False for n in (1, 2, 3)}}
    allowed = Context.for_jurisdiction(ny).allowed()
    by_id = {r["id"]: r for r in rules}
    [where] = part_rules.rows(by_id["general.bc_1031_2_escape_opening_where_required"], parts, given, allowed)
    rows = {}
    for r in rules:
        if r.get("for_each") == "emergency_escape_opening":
            for row in part_rules.rows(r, parts, given, allowed):
                if row["id"] is not None:                # with no opening, a rule's own row: doesn't apply
                    rows.setdefault(row["id"], set()).add(row["outcome"])
    m = parts["sleeping_room"][0]
    return where["outcome"], rows, m["measures"].get("sleeping_room_compliant_openings",
                                                     m["not_measured"].get("sleeping_room_compliant_openings"))


def test_an_r2_room_reaching_two_exits_asks_no_opening_and_never_passes_on_a_reading():
    """BCNYS 1031.2 item 1 asks Group R-2 only "in stories with only one exit or access to only one exit": a room whose
    routes reach two separate exits is asked no escape opening, so 1031.2 passes with none, and a small one isn't held
    to the size or well rules; where that reach stands on Gordium's reading, nothing passes on it (8d's count beside
    it changes nothing)."""
    assert _reach_check([])[0] == "pass"
    where, rows, count = _reach_check([{"id": "w", "measures": dict(SMALL)}])
    assert where == "pass" and rows == {"w": {"pass"}} and count == 0
    for openings in ([], [{"id": "w", "measures": dict(SMALL)}], [{"id": "w", "measures": dict(GOOD)}]):
        where, rows, _ = _reach_check(openings, reading="Gordium's reading: Bedroom through Closet")
        assert where == "needs_review" and all(o == {"needs_review"} for o in rows.values()), (openings, rows)


def test_an_opening_arriving_with_a_confirm_that_isnt_a_mapping_never_counts_compliant():
    """Merge review of #240 on 8d: the opening's compliance is read on the opening as given (8d review round 2: a
    `confirm` that isn't a mapping leaves it not known), before the room's reading is copied onto it."""
    _, _, count = _reach_check([{"id": "w", "measures": dict(GOOD), "confirm": "junk"}], reading="Gordium's reading")
    assert not isinstance(count, int), count


def test_an_opening_not_known_says_why_in_its_own_terms():
    """Merge review of #240 (8d's reasons, after compliance moved before the room's facts are copied): an opening
    with no figures at all names the figures its limits read, and one whose confirm can't be read says so, never "a
    reading to confirm"."""
    from design_checker.escape_openings import _unknown_why, limits
    held = limits(_ny_rules())
    assert "opening_net_clear_area" in _unknown_why([({"id": "w"}, None)], held)
    said = _unknown_why([({"id": "w", "measures": dict(GOOD), "confirm": "junk"}, None)], held)
    assert "its confirm can't be read" in said and "opening_net_clear_area" not in said, said


def test_two_exits_closer_than_1007_1_1_asks_leave_the_r2_room_needing_its_opening_or_a_review():
    """Merge review of #240 (a false pass its confirming round found: two exit doors 3 ft apart passed 1031.2 with no
    escape opening). Two exits count for 1031.2 item 1 only where placed apart as BCNYS 1007.1.1 (p.318) asks, held
    with the law's own rule general.bc_1007_1_1_remoteness: "not less than one-half of the length of the maximum
    overall diagonal dimension", one-third with an NFPA 13 or 13R system (exception 2). A pair that isn't: the room's
    one-exit question stays open (a story with one exit as Tables 1006.3.4(1) and (2) permit may be what it is), so
    1031.2 needs review with no opening, never a pass."""
    assert _reach_check([], ratio=0.6)[0] == "pass"
    for ratio, system, outcome in ((0.05, "none", "needs_review"), (0.05, "nfpa_13", "needs_review"),
                                   (0.4, "none", "needs_review"), (0.4, None, "needs_review"),
                                   (0.4, "nfpa_13d", "needs_review"), (0.4, "nfpa_13", "pass"),
                                   (0.4, "nfpa_13r", "pass"), (0.5, None, "pass")):
        where, _, _ = _reach_check([], ratio=ratio, system=system)
        assert where == outcome, (ratio, system, where)


@pytest.mark.parametrize("ratio", [None, "0.6", True, float("nan"), -1])
def test_a_reach_whose_ratio_isnt_a_figure_is_never_two(ratio):
    """A hand-built reach without the routes' ratio (or one that isn't a number): how far apart its exits are isn't
    known, so the one-exit question stays open."""
    p = _with_space({"exits_reached": {"two": True, "doors": {"d": ["x", "y"]}, "remoteness_ratio": ratio}})
    assert "sleeping_room_story_one_exit" not in p["measures"]
    assert "1007.1.1" in p["not_measured"]["sleeping_room_story_one_exit"]


def test_without_the_laws_separation_rule_two_exits_are_never_two():
    """The law's 1007.1.1 rule not read (no rules given, or none over stories reading the ratio): not two."""
    parts, desc = _parts()
    parts["space"] = [{"id": "b", "within": "L1", "measures": {}, "not_measured": {}, "more": {
        "exits_reached": {"two": True, "doors": {"d": ["x", "y"]}, "remoteness_ratio": 0.9}}}]
    escape_openings.link(parts, desc)
    assert "sleeping_room_story_one_exit" not in parts["sleeping_room"][0]["measures"]
