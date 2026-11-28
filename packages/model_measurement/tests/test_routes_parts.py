"""The parts the routes hand to the rules (routes/__init__.py: decision 11 of
docs/decisions/2026-11-20_route_measurement.md), and a small synthetic day-care story run through them and Maine's
real rules (rule_format.parts.rows / rule_result): pass, fail and needs review as the law says. Figures are worked by
hand in the comments; none is taken from the code under test."""

import math
import sys
from pathlib import Path

import pytest

from model_measurement.routes import measure
from rule_format import parts as part_rules
from rule_format.rulebook import REPO, Context, load

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import description, door, rect, room  # noqa: E402

MAINE = REPO / "regulations/jurisdictions/maine/maine_state"
RULES = MAINE / "5_building_code_rules/drafted/general.yaml"
NEW_DAY_CARE = {"nfpa_day_care_occupancy": True, "day_care_existing": False, "sprinklered_9_7": False,
                "sprinkler_supervised_9_7": False, "occupancy_group_i4": True, "sprinklered_903_3_1_1": False,
                "sprinklered_903_3_1_2": False}


def outlined(d, x1, y1, y0=0):
    d["story_outlines"] = [{"level": "L1", "outer": [list(p) for p in rect(-0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5)],
                            "inner": [list(p) for p in rect(0, y0, x1, y1)]}]
    return d


def day_care(branch=None, classroom_in_branch=False, unknown=False):
    """A corridor 0 to 60 by 11 to 19, an exit at each end (A west, B east); two classrooms north (0 to 29.75 and
    30.25 to 60, by 19.5 to 30) and to the south a storeroom (0 to 10), a toilet (10.5 to 20) and a classroom (20.5
    to 60), each by 0 to 10.5, each with one door on the corridor; walls 6 in. `branch`: the corridor also has a
    branch 8 ft wide south of x 62 to 70, out of a corridor extended to x 70, its end wall that far below the
    corridor's south wall."""
    corridor = rect(0, 11, 60, 19)
    rooms = [room("k1", rect(0, 19.5, 29.75, 30), use="day_care"), room("k2", rect(30.25, 19.5, 60, 30), use="day_care"),
             room("s", rect(0, 0, 10, 10.5), use="accessory_storage"), room("t", rect(10.5, 0, 20, 10.5), use="toilet"),
             room("k3", rect(20.5, 0, 60, 10.5), use="day_care")]
    doors = [door("a", (-0.25, 15), (0, 1), ("c", "outside"), exit_id="A"),
             door("d1", (15, 19.25), (1, 0), ("k1", "c")), door("d2", (45, 19.25), (1, 0), ("k2", "c")),
             door("ds", (5, 10.75), (1, 0), ("s", "c")), door("dt", (15, 10.75), (1, 0), ("t", "c")),
             door("d3", (40, 10.75), (1, 0), ("k3", "c"))]
    east = 60
    if branch is not None:
        east = 72
        corridor = [(0, 11), (62, 11), (62, 11 - branch), (70, 11 - branch), (70, 11), (72, 11), (72, 19), (0, 19)]
        if classroom_in_branch:   # a classroom east of the branch (to x 78), its door 5 ft from the end, its own exit C
            rooms.append(room("k4", rect(70.5, 11 - branch, 78, 10.5), use="day_care"))
            doors += [door("d4", (70.25, 11 - branch + 5), (0, 1), ("c", "k4")),
                      door("c4", (78.25, 11 - branch + 5), (0, 1), ("k4", "outside"), exit_id="C")]
    doors.append(door("b", (east + 0.25, 15), (0, 1), ("c", "outside"), exit_id="B"))
    d = description([room("c", corridor, name="Corridor")] + rooms, doors)
    if unknown:
        d["unknown_spaces"] = [{"id": "q", "name": "Space 9", "level": "L1"}]
    # the story's outline holds the branch too (a branch reaching south of y 0 lay outside it, a diagonal too short)
    return outlined(d, 78 if classroom_in_branch else east, 30, min(0, 11 - branch) if branch is not None else 0)


@pytest.fixture(scope="module")
def plain():
    return measure(day_care())


@pytest.fixture(scope="module")
def door_in_dead_end():
    return measure(day_care(branch=26, classroom_in_branch=True))


@pytest.fixture(scope="module")
def maine():
    ctx = Context.for_jurisdiction(MAINE)
    return {r["id"]: r for r in load(RULES)["rules"]}, ctx.allowed()


def result(rules, rid, got):
    rule, allowed = rules[0][rid], rules[1]
    return part_rules.rule_result(part_rules.rows(rule, got["parts"], NEW_DAY_CARE, allowed))


# --- the parts ---------------------------------------------------------------------------------------------------

def test_every_measure_parts_yaml_lists_is_measured_or_says_why_not(plain):
    for kind, given in plain["parts"].items():
        assert given, kind
        for part in given:
            for name in part_rules.measure_kinds(kind):
                assert (name in part["measures"]) != (name in part["not_measured"]), (kind, part["id"], name)


def test_the_story_part_holds_the_route_measures(plain):
    story, = plain["parts"]["story"]
    m = story["measures"]
    assert m["story_exit_count"] == 2
    # the farthest point: a far corner of a classroom; from (0, 30) in k1, through its door (15, 19.25) and west
    # along the corridor to (-0.25, 15): at least sqrt(15^2 + 10.75^2) = 18.454 + 15.25 ... far below 150
    assert 18.454 + 15 < m["egress_travel_distance"] < 150
    assert m["egress_travel_in_sleeping_room"] == 0.0                # no sleeping room on the story
    # exit remoteness: A's opening x -0.5 to 0, B's 60 to 60.5, both y 13.5 to 16.5: 60 ft; the diagonal of
    # -0.5 to 60.5 by -0.5 to 30.5: sqrt(61^2 + 31^2) = 68.425
    assert m["exit_remoteness_ratio"] == pytest.approx(60 / math.hypot(61, 31), abs=1e-9)
    # day-care net: 29.75 x 10.5 x 2 + 39.5 x 10.5 = 624.75 + 414.75 = 1039.5 sf
    assert m["story_day_care_net_area"] == pytest.approx(1039.5, abs=1e-9)
    assert "story_occupant_load" in story["not_measured"]
    assert [r["value"] for r in story["readings"]["story_building_area"]] == [1800.0, 61 * 31]
    assert story["readings"]["story_accessory_area"][0]["value"] == pytest.approx(105.0)    # 10 x 10.5
    assert "story_accessory_area" in story["not_measured"]


def test_the_space_parts_count_their_exit_access_doors(plain):
    spaces = {p["id"]: p for p in plain["parts"]["space"]}
    assert set(spaces) == {"k1", "k2", "s", "t", "k3"}                # every room but the corridor
    assert all(p["measures"]["space_exit_count"] == 1 for p in spaces.values())
    # a classroom's common path: its far corner to its door, where the two routes part
    assert spaces["k1"]["measures"]["space_common_path"] >= math.hypot(15, 10.75) - 1e-3


def test_the_corridor_part_has_no_dead_end_and_its_width(plain):
    c, = plain["parts"]["corridor"]
    assert c["measures"]["corridor_width"] == 96.0                    # 8 ft, in inches
    assert c["measures"]["corridor_dead_end_length"] == 0.0
    assert {"corridor_occupant_load", "corridor_fire_rating_hours", "corridor_walls_smoke_partitions"} <= set(
        c["not_measured"])


def test_7_one_stair_two_doors_one_exit_and_its_common_path_is_its_travel():
    d = outlined(description([room("c", rect(0, 0, 90, 8))],
                             [door("s1", (5, 8.25), (1, 0), ("c", "outside"), exit_id="S", kind="exit_enclosure"),
                              door("s2", (85, 8.25), (1, 0), ("c", "outside"), exit_id="S", kind="exit_enclosure")]),
                 90, 8)
    story, = measure(d)["parts"]["story"]
    assert story["measures"]["story_exit_count"] == 1
    assert "remoteness needs two" in story["not_measured"]["exit_remoteness_ratio"]
    assert story["measures"]["common_path_of_travel"] == story["measures"]["egress_travel_distance"]


def sleeping_room():
    """Test 13: a sleeping room 0 to 60 by 0 to 20, its corridor door at the west end (centre (-0.25, 10)) on a
    corridor x -8.5 to -0.5, y -10 to 30, exits at both its ends; a closet (60.5 to 64.5 by 8 to 12) whose door is at
    the far end (centre (60.25, 10))."""
    return outlined(description(
        [room("r", rect(0, 0, 60, 20), use="other", sleeping=True), room("c", rect(-8.5, -10, -0.5, 30)),
         room("k", rect(60.5, 8, 64.5, 12), use="closet")],
        [door("d", (-0.25, 10), (0, 1), ("r", "c")), door("kd", (60.25, 10), (0, 1), ("r", "k")),
         door("a", (-4.5, -10.25), (1, 0), ("c", "outside"), exit_id="A"),
         door("b", (-4.5, 30.25), (1, 0), ("c", "outside"), exit_id="B")]), 65, 30)


def test_13_a_sleeping_rooms_far_end_is_about_60_ft_from_its_corridor_door_never_its_closets():
    story, = measure(sleeping_room())["parts"]["story"]
    got = story["measures"]["egress_travel_in_sleeping_room"]
    far = math.hypot(60.25, 10)                                       # (60, 0) to (-0.25, 10): 61.074
    assert far - 1e-3 <= got <= far + 0.375 + 1e-3                   # decision 3's bound: at most 4.5 in more
    assert "closet" not in str(story["more"].get("egress_travel_from_room_door"))


def test_no_levels_no_parts_read():
    d = description([room("c", rect(0, 0, 10, 8))], [door("a", (-0.25, 4), (0, 1), ("c", "outside"), exit_id="A")])
    del d["levels"]
    got = measure(d)
    assert got["parts"] == {"story": None, "space": None, "corridor": None, "means_of_egress_door": None} \
        and got["problems"]


def test_an_unknown_space_may_be_a_space_or_a_corridor_and_its_story_needs_review():
    got = measure(day_care(unknown=True))
    assert any(p["id"] == "q" and "maybe" in p for p in got["parts"]["space"])
    assert any(p["id"] == "q (as a corridor)" and "maybe" in p for p in got["parts"]["corridor"])
    story, = got["parts"]["story"]
    assert "egress_travel_distance" in story["not_measured"] and "Space 9" in story["not_measured"][
        "egress_travel_distance"]


def test_a_room_with_no_use_may_be_a_corridor():
    d = day_care()
    del d["rooms"][1]["use"]                                          # k1
    got = measure(d)
    assert any(p["id"] == "k1 (as a corridor)" and "maybe" in p for p in got["parts"]["corridor"])


def test_8_a_door_in_a_dead_end_gives_the_corridor_two_readings(door_in_dead_end):
    c, = door_in_dead_end["parts"]["corridor"]
    assert "corridor_dead_end_length" not in c["measures"]
    assert sorted(r["value"] for r in c["readings"]["corridor_dead_end_length"]) == [5.0, 30.0]   # 26 + 4; to the door
    assert "open question 7" in c["not_measured"]["corridor_dead_end_length"]


# --- end to end: the real Maine rules ----------------------------------------------------------------------------

E2E = ["general.nfpa_16_2_6_2_point_in_room_to_exit", "general.nfpa_16_2_6_2_room_door_to_exit",
       "general.nfpa_16_2_6_2_sleeping_room_to_door", "general.nfpa_16_2_5_3_2_common_path_not_sprinklered",
       "general.nfpa_16_2_5_2_dead_end"]


def _corridor_with(**stated):
    d = day_care()
    next(r for r in d["rooms"] if r["id"] == "c").update(stated)
    c, = measure(d)["parts"]["corridor"]
    return c


@pytest.mark.parametrize("stated, rating, smoke", [
    ({"fire_rating_hours": 1, "walls_smoke_partitions": True}, 1, True),
    ({"fire_rating_hours": 0.5, "walls_smoke_partitions": False}, 0.5, False),
    ({"fire_rating_hours": 0}, 0, None),                         # 0: not rated (a statement, never "not given")
])
def test_a_corridors_stated_rating_and_smoke_partitions_are_its_measures(stated, rating, smoke):
    """The egress UI audit's finding 5 (2026-11-26): the corridor walls' fire-resistance rating and whether they are
    smoke partitions are the architect's to state (a rating is the assembly's, which the model's geometry can't
    show for certain), on the corridor's room (fire_rating_hours, walls_smoke_partitions); before, nothing could give
    them, so every rule reading them needed review for good."""
    c = _corridor_with(**stated)
    assert c["measures"]["corridor_fire_rating_hours"] == rating
    assert "corridor_fire_rating_hours" not in c["not_measured"]
    if smoke is None:
        assert "the room's Smoke partition walls mark" in c["not_measured"]["corridor_walls_smoke_partitions"]
    else:
        assert c["measures"]["corridor_walls_smoke_partitions"] is smoke


@pytest.mark.parametrize("stated", [{"fire_rating_hours": True}, {"fire_rating_hours": "1 HR"},
                                    {"fire_rating_hours": -1}, {"fire_rating_hours": float("nan")},
                                    {"walls_smoke_partitions": "yes"}, {"walls_smoke_partitions": 1}])
def test_a_corridor_fact_not_of_its_kind_is_said_never_read(stated):
    c = _corridor_with(**stated)
    m = {"fire_rating_hours": "corridor_fire_rating_hours", "walls_smoke_partitions": "corridor_walls_smoke_partitions"}[
        next(iter(stated))]
    assert m not in c["measures"] and " is given as " in c["not_measured"][m], c["not_measured"][m]


def test_a_corridor_fact_left_out_is_said_by_its_mark(plain):
    c, = plain["parts"]["corridor"]
    assert c["not_measured"]["corridor_fire_rating_hours"].startswith("not stated for this corridor:")
    assert "the room's Corridor rating minutes mark" in c["not_measured"]["corridor_fire_rating_hours"]
    assert "the room's Smoke partition walls mark" in c["not_measured"]["corridor_walls_smoke_partitions"]
    assert "fire_rating_hours" not in c["not_measured"]["corridor_fire_rating_hours"]
    assert "no mark for it" not in c["not_measured"]["corridor_fire_rating_hours"]


def test_end_to_end_a_small_day_care_story_complies_with_the_nfpa_route_rules(plain, maine):
    assert {rid: result(maine, rid, plain) for rid in E2E} == {rid: "pass" for rid in E2E}


def test_end_to_end_a_30_ft_dead_end_fails_the_nfpa_dead_end_rule(maine):
    got = measure(day_care(branch=26))                                # 26 + 4 = 30 ft, over 20 (not sprinklered)
    assert result(maine, "general.nfpa_16_2_5_2_dead_end", got) == "fail"
    assert result(maine, "general.nfpa_16_2_6_2_point_in_room_to_exit", got) == "pass"


def test_end_to_end_a_door_in_the_dead_end_needs_review_never_a_pass(maine, door_in_dead_end):
    # 30 ft without the door, 5 ft with it
    assert result(maine, "general.nfpa_16_2_5_2_dead_end", door_in_dead_end) == "needs_review"


def test_end_to_end_an_unknown_space_needs_review_never_a_pass(maine):
    got = measure(day_care(unknown=True))
    for rid in E2E[:4]:
        assert result(maine, rid, got) == "needs_review", rid


def test_end_to_end_the_ibc_flags_need_review_whatever_the_figures(plain, maine):
    for rid in ("general.ibc_1016_1_travel_distance", "general.ibc_1014_3_common_path", "general.ibc_1018_4_dead_end",
                "general.ibc_508_2_1_accessory_area", "general.ibc_1015_2_1_remoteness"):
        assert result(maine, rid, plain) == "needs_review", rid


# --- what needs review, one case each ---------------------------------------------------------------------------

def test_a_story_of_corridors_only_has_no_room_door_to_measure_from():
    d = outlined(description([room("c", rect(0, 0, 30, 8))],
                             [door("a", (-0.25, 4), (0, 1), ("c", "outside"), exit_id="A"),
                              door("b", (30.25, 4), (0, 1), ("c", "outside"), exit_id="B")]), 30, 8)
    story, = measure(d)["parts"]["story"]
    assert "no room besides its corridors" in story["not_measured"]["egress_travel_from_room_door"]


def test_a_closet_with_no_door_out_leaves_the_room_door_travel_unmeasured():
    """The sleeping room marked `lockable: true`: its closet, opening only into it, has no way out (decision 1a, as
    amended 2026-11-21: a room that can be locked is never passed through, even by its own closet's route)."""
    d = sleeping_room()
    d["rooms"][0]["lockable"] = True
    story, = measure(d)["parts"]["story"]
    assert "the room k has no door from which" in story["not_measured"]["egress_travel_from_room_door"]


def test_a_closet_off_a_sleeping_room_that_cant_be_locked_leaves_through_it():
    """Decision 1a as amended 2026-11-21 (Gordium's reading): the closet's door into the sleeping room is its exit
    access door. By hand: from the closet's door centre (60.25, 10) straight along y = 10 to the corridor door
    (-0.25, 10), 60.5 (every jamb 1.5 ft off the line), then to the nearer exit, A at (-4.5, -10.25) or B at
    (-4.5, 30.25), the same by symmetry: at least sqrt(4.25^2 + 20.25^2) = 20.691 more."""
    story, = measure(sleeping_room())["parts"]["story"]
    assert story["measures"]["egress_travel_from_room_door"] >= 60.5 + 20.691 - 1e-3
    assert "Gordium's reading" in story["confirm"]["egress_travel_from_room_door"]


def test_a_room_not_read_is_a_space_not_measured():
    d = day_care()
    del d["rooms"][1]["floor"]                                      # k1
    got = measure(d)
    k1 = next(p for p in got["parts"]["space"] if p["id"] == "k1")
    assert "isn't read" in k1["not_measured"]["space_exit_count"] and not k1["measures"]


def lobby_on_a_corridor():
    """A lobby (pass_through) open by a passage to a corridor: one floor a route may cross, so which of the
    lobby's doors lead out without coming back into it isn't worked out."""
    return description([room("c", rect(0, 0, 30, 8)), room("l", rect(0, 8, 10, 18), use="lobby", pass_through=True),
                        room("k", rect(10.5, 8.5, 30, 18), use="day_care")],
                       [door("a", (-0.25, 4), (0, 1), ("c", "outside"), exit_id="A"),
                        door("b", (30.25, 4), (0, 1), ("c", "outside"), exit_id="B"),
                        door("kd", (20, 8.25), (1, 0), ("c", "k"))],
                       passages=[(("c", "l"), [(0, 8), (10, 8)])])


def test_a_room_joined_by_passages_to_crossable_rooms_has_its_exit_access_unclear():
    got = measure(lobby_on_a_corridor())
    lobby = next(p for p in got["parts"]["space"] if p["id"] == "l")
    assert "joined by passages" in lobby["not_measured"]["space_exit_count"]


def test_a_passage_whose_middle_is_in_a_ring_needs_review(monkeypatch):
    import model_measurement.routes as routes_pkg
    from model_measurement.routes.floor import read
    from model_measurement.routes.paths import StoryRoutes, _Leg
    d = description([room("c", rect(0, 0, 30, 8)), room("s", rect(0, 8, 10, 18), use="accessory_storage")],
                    [door("a", (-0.25, 4), (0, 1), ("c", "outside"), exit_id="A")],
                    passages=[(("c", "s"), [(0, 8), (10, 8)])])
    s = read(d).stories["L1"]
    got = StoryRoutes(s)
    monkeypatch.setattr(_Leg, "inside", lambda self, p: True)
    with pytest.raises(routes_pkg.Stop) as stop:
        routes_pkg._room_access(s, got, s.rooms["s"], got._chain(frozenset(got.exits))[0])
    assert stop.value.key == "passage_in_ring"


def storage_in_storage():
    """A day-care room 0 to 20 by 0 to 10 (marked pass_through) with its exit (-0.25, 5) and a second exit (20.25, 5); a storeroom 0 to 10 by
    10.5 to 16 off it (door (5, 10.25)), and an inner storeroom 0 to 10 by 16.5 to 20 whose only door (5, 16.25) is
    into the storeroom, which can be locked: no route crosses a room that can be locked (IBC 1014.2 item 2), so the
    inner one has none (with the storeroom `lockable: false` it would leave through it: decision 1a as amended
    2026-11-21, test_routes_served.py)."""
    return description([room("r", rect(0, 0, 20, 10), use="day_care", pass_through=True),
                        room("s1", rect(0, 10.5, 10, 16), use="accessory_storage", lockable=True),
                        room("s2", rect(0, 16.5, 10, 20), use="accessory_storage")],
                       [door("a", (-0.25, 5), (0, 1), ("r", "outside"), exit_id="A"),
                        door("b", (20.25, 5), (0, 1), ("r", "outside"), exit_id="B"),
                        door("d1", (5, 10.25), (1, 0), ("r", "s1")), door("d2", (5, 16.25), (1, 0), ("s1", "s2"))])


def test_a_room_with_no_route_keeps_the_verdict_needs_review_with_the_figure_over_the_others_in_more():
    story, = measure(storage_in_storage())["parts"]["story"]
    for m in ("egress_travel_distance", "common_path_of_travel"):
        assert m not in story["measures"] and "has no route" in story["not_measured"][m]
        shown = story["more"][m]
        assert shown["label"] == ("greatest over the rooms measured; not a verdict, since s2 isn't measured (each "
                                  "room's reason in rooms_not_measured)")
        assert set(shown["rooms_not_measured"]) == {"s2"} and shown["rooms"] == 2
        assert "has no route" in shown["rooms_not_measured"]["s2"]
    # the travel's: the storeroom's far corner (10, 16) to its door (5, 10.25), then on to the nearest exit:
    # at least sqrt(5^2 + 5.75^2) = 7.620 + ...; well under the room's diagonal sum
    assert story["more"]["egress_travel_distance"]["figure"] > 7.620


def test_each_dead_end_is_its_own_pair_never_one_length_with_anothers_width(maine):
    """Test 17's H-plan (review round 1): dead ends of 30 by 14 ft and 22 by 8 ft are two corridor parts, (30, 14)
    complying with 1018.4's formula by exception 3 and (22, 8) failing it: never (30, 8)."""
    from test_routes_dead_ends import h_plan
    got = measure(h_plan())
    pairs = sorted((c["measures"]["corridor_dead_end_length"], c["measures"]["corridor_dead_end_least_width"])
                   for c in got["parts"]["corridor"])
    assert pairs == [(22.0, 8.0), (30.0, 14.0)]
    assert {c["id"] for c in got["parts"]["corridor"]} == {"c", "c (dead end 2)"}
    rule = dict(maine[0]["general.ibc_1018_4_dead_end"], kind="rule")
    rows = part_rules.rows(rule, got["parts"], NEW_DAY_CARE, maine[1])
    assert sorted(r["outcome"] for r in rows) == ["fail", "pass"]


def alcove_dead_end():
    """Test 3's branch, 8 ft wide, end wall 16 ft past the corridor, with an alcove 3 ft wide and 11 in deep centred
    in its end wall: the dead end is 16 + 11/12 + 4 = 20.917 ft."""
    poly = [(0, 0), (60, 0), (60, 8), (28, 8), (28, 24), (25.5, 24), (25.5, 24 + 11 / 12), (22.5, 24 + 11 / 12),
            (22.5, 24), (20, 24), (20, 8), (0, 8)]
    return description([room("c", poly)], [door("a", (-0.25, 4), (0, 1), ("c", "outside"), exit_id="A"),
                                           door("b", (60.25, 4), (0, 1), ("c", "outside"), exit_id="B")])


def test_end_to_end_a_dead_end_with_an_alcove_at_its_end_never_passes_at_20_ft(maine):
    got = measure(alcove_dead_end())
    c, = got["parts"]["corridor"]
    assert c["measures"]["corridor_dead_end_length"] == pytest.approx(20.917, abs=1e-3)
    assert result(maine, "general.nfpa_16_2_5_2_dead_end", got) == "fail"


def h_plan_with_doors():
    """The H-plan (test 17) with the right leg starting at y 30 (its foot 44 - 30 = 14 ft by 8), and a door 3 ft
    from each closed end into a classroom with its own exterior exit: readings of 30 and 3 ft for the left dead
    end, 14 and 3 ft for the right."""
    poly = [(0, 14), (14, 14), (14, 40), (60, 40), (60, 30), (68, 30), (68, 70), (60, 70), (60, 48), (14, 48),
            (14, 70), (0, 70)]
    return description([room("c", poly), room("w", rect(-20.5, 14, -0.5, 24), use="day_care"),
                        room("e", rect(68.5, 30, 88.5, 40), use="day_care")],
                       [door("a", (7, 70.25), (1, 0), ("c", "outside"), exit_id="A"),
                        door("b", (64, 70.25), (1, 0), ("c", "outside"), exit_id="B"),
                        door("wd", (-0.25, 17), (0, 1), ("w", "c")), door("wx", (-20.75, 17), (0, 1), ("w", "outside"), exit_id="W"),
                        door("ed", (68.25, 33), (0, 1), ("c", "e")), door("ex", (88.75, 33), (0, 1), ("e", "outside"), exit_id="E")])


def test_each_dead_end_part_has_its_own_readings(maine):
    got = measure(h_plan_with_doors())
    parts = {c["id"]: c for c in got["parts"]["corridor"]}
    first, second = parts["c"], parts["c (dead end 2)"]
    assert sorted(r["value"] for r in first["readings"]["corridor_dead_end_length"]) == [3.0, 30.0]
    assert sorted(r["value"] for r in second["readings"]["corridor_dead_end_length"]) == [3.0, 14.0]
    assert first["readings"] is not second["readings"]
    rows = {r["id"]: r["outcome"] for r in part_rules.rows(maine[0]["general.nfpa_16_2_5_2_dead_end"], got["parts"],
                                                            NEW_DAY_CARE, maine[1])}
    assert rows == {"c": "needs_review", "c (dead end 2)": "pass"}


def test_end_to_end_an_off_centre_alcove_at_a_dead_ends_end_never_passes_at_20_ft(maine):
    d = alcove_dead_end()
    d["rooms"][0]["floor"] = [list(p) for p in [(0, 0), (60, 0), (60, 8), (28, 8), (28, 24), (23.5, 24),
                                                (23.5, 24 + 11 / 12), (20.5, 24 + 11 / 12), (20.5, 24), (20, 24),
                                                (20, 8), (0, 8)]]
    assert result(maine, "general.nfpa_16_2_5_2_dead_end", measure(d)) == "fail"



def test_a_room_stopped_by_a_tie_is_not_measured_with_its_own_reason_never_called_no_route():
    # review round 12: a room whose figure stops on a tie (or any stop) is "not measured", each with its own reason;
    # the label never says it has no route
    from types import SimpleNamespace
    from model_measurement.routes import _over_rooms_measured
    from model_measurement.routes.stops import Stop
    story = SimpleNamespace(rooms={"c": SimpleNamespace(name="CORRIDOR (26)")})
    shown = _over_rooms_measured(story, {"c": Stop("too_many_ties", most=64, x=63.232, y=37.844)})
    assert "no route" not in shown["label"] and "has none" not in shown["label"]
    assert shown["rooms_not_measured"] == {"CORRIDOR (26)": Stop("too_many_ties", most=64, x=63.232, y=37.844).reason}


def test_each_corridor_fact_names_the_revit_mark_that_states_it():
    """A reason for a corridor fact not stated names the host's mark, never the file's key (CI on #229:
    test_plain_words); the mark it names is one the Revit add-in defines, feeding that very key."""
    import re
    from model_measurement.routes import CORRIDOR_STATED
    text = (REPO / "apps/revit_addin/src/Gordium.Revit.Reading/Marks.cs").read_text(encoding="utf-8")
    for key, _, mark in CORRIDOR_STATED.values():
        assert re.search(r'"Gordium: ' + re.escape(mark) + r'", new\("[^"]+"\), MarkValueKind\.\w+,\s*MarkBinding\.\w+, '
                         r'\[Rooms\], "rooms\[\]\.' + re.escape(key) + '"', text), (mark, key)


@pytest.mark.parametrize("key, bad", [("rooms", 5), ("rooms", True), ("unknown_spaces", 5), ("unknown_spaces", True),
                                      ("unknown_spaces", "x"),
                                      ("unknown_spaces", [{"id": ["u"], "name": "u", "level": "L1"}]),
                                      ("unknown_spaces", [{"id": "u", "name": "u", "level": ["X"]}]),
                                      ("unknown_spaces", [{"id": "u", "name": "u", "level": {"id": "X"}}]),
                                      ("story_outlines", [{"level": ["X"]}]),
                                      ("story_outlines", [{"level": {"id": "X"}}])])
def test_a_description_list_that_isnt_a_list_is_never_a_crash(key, bad):
    """A hand-written description may give its rooms or unknown spaces as a number or text: the routes say what
    they can't read (or measure without it), never a crash."""
    from routes_layouts import room_on_corridor
    d = dict(room_on_corridor(), **{key: bad})
    got = measure(d)
    if key == "rooms":
        assert got["problems"]


@pytest.mark.parametrize("level", [["X"], {"id": "X"}])
def test_an_unknown_space_on_a_level_that_isnt_text_is_still_a_maybe_space(level):
    """Cold round 2 of the room-id fix: an unknown space whose level can't be read is never dropped: it is a space
    and a corridor that may be on any story (its rows need review)."""
    from routes_layouts import room_on_corridor
    d = dict(room_on_corridor(), unknown_spaces=[{"id": "u", "name": "u", "level": level}])
    got = measure(d)
    for kind in ("space", "corridor"):
        mine = [p for p in got["parts"][kind] if p["id"] in ("u", "u (as a corridor)")]
        assert mine and mine[0].get("within") is None and mine[0].get("maybe"), kind

