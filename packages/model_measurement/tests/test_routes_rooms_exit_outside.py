"""Whether a story's rooms exit directly outside (BCNYS 1006.3.4 item 2, p.317: "Rooms, areas and spaces complying
with Section 1006.2.1 with exits that discharge directly to the exterior at the level of exit discharge, are
permitted to have one exit or access to a single exit"), worked out from the model: routes.rooms_exit_outside.

The property walk: a row of three rooms along an outside wall, each with a door to the outside marked as an exterior
exit door at discharge, one not marked, one onto an exterior stair, or none, each pair joined by a door, open (a
passage) or walled; and again with a corridor along them that each room opens into or not, with or without its own
exit, the rooms residential or with no function, the building stating corridors within dwelling units no or nothing.
The oracle, written apart from the code from item 2's "rooms, areas and spaces": rooms joined by doors or passages
are one space; each needs its own exit straight outside (yes); a space reaching the outside only through a corridor
shared with another dwelling unit can't rely on item 2 (no), which the model shows only where the corridor reaches an
exit, two or more residential spaces open into it and the building states no corridor is within a dwelling unit;
everything else isn't known (a door outside not marked: exits are marked, never guessed; a corridor that may be a
space's own hallway; the story's routes not read)."""

import itertools
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from routes_layouts import description, door, rect, room  # noqa: E402

from model_measurement.routes import OUTSIDE_FACT, measure, rooms_exit_outside  # noqa: E402
from model_measurement.routes.floor import read  # noqa: E402
from model_measurement.routes.stops import STOPS, Stop  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
OUTSIDE_KEYS = {"outside_no_rooms", "outside_door_not_marked", "outside_way_unclear", "outside_hall_unclear",
                "outside_into_exit", "outside_stair", "outside_link_elsewhere",
                "outside_link_unread"}
KINDS = ("marked", "unmarked", "stair", "none")
SIDES = ("door", "passage", "wall")


def row(kinds, joins, uses=("other", "other", "other"), corridor=None, function=None, corridor_exit=True,
        within=None, hall="corridor"):
    """Three 10 by 10 ft rooms side by side (x 0-10, 10.5-20.5, 21-31; a 6 in wall between), each door to the
    outside on the south wall (y = -0.25), `joins` between rooms 0-1 and 1-2 (a door, a passage with no wall: then
    the rooms touch, or a plain wall). `corridor`: None, or which rooms open into a corridor along their north side
    (y 10.5-16.5), itself with a marked exit door outside at its west end."""
    rooms, doors, passages, x = [], [], [], 0.0
    xs = []
    for i, (kind, use) in enumerate(zip(kinds, uses)):
        x0 = x
        x1 = x0 + 10
        xs.append((x0, x1))
        rooms.append(room(f"r{i}", rect(x0, 0, x1, 10), use=use, lockable=False, pass_through=False))
        if function:
            rooms[-1]["function"] = function
        if kind != "none":
            d = door(f"o{i}", ((x0 + x1) / 2, -0.25), (1, 0), (f"r{i}", "outside"),
                     exit_id=None if kind == "unmarked" else f"o{i}",
                     kind="exterior_stair_or_ramp" if kind == "stair" else "exterior_at_discharge")
            doors.append(d)
        x = x1 + (0.5 if i < 2 and joins[i] != "passage" else 0)
    for i, j in enumerate(joins):
        if j == "door":
            doors.append(door(f"d{i}", (xs[i][1] + 0.25, 5), (0, 1), (f"r{i}", f"r{i + 1}")))
        elif j == "passage":
            passages.append(((f"r{i}", f"r{i + 1}"), [(xs[i][1], 0), (xs[i][1], 10)]))
    top = 10
    if corridor is not None:
        rooms.append(room("c", rect(0, 10.5, x, 16.5), use=hall, lockable=False, pass_through=True))
        if corridor_exit:
            doors.append(door("oc", (-0.25, 13.5), (0, 1), ("c", "outside"), exit_id="oc"))
        for i in corridor:
            doors.append(door(f"e{i}", ((xs[i][0] + xs[i][1]) / 2, 10.25), (1, 0), (f"r{i}", "c")))
        top = 16.5
    desc = description(rooms, doors, passages)
    desc["stairs"] = []                                  # no stair, ramp or ladder on the story: said, as a host says it
    desc["has_none"] = [{"kind": k, "source": "the test's row: none drawn"}
                        for k in ("ramp", "alternating_tread_device", "ships_ladder")]
    if within is not None:
        desc["building"] = {"corridors_within_dwelling_units": within}
    desc["story_outlines"] = [{"level": "L1", "outer": [[-0.5, -0.5], [x + 0.5, -0.5], [x + 0.5, top + 0.5],
                                                        [-0.5, top + 0.5]],
                               "inner": [[0, 0], [x, 0], [x, top], [0, top]]}]
    return desc


def _story(desc):
    """The story's fact as the route measuring sets it (measured, or its reason), from the floor read alone: the
    walks don't need the routes' travel figures (measure() runs the same function; the apartment test goes through
    it)."""
    story = read(desc).stories["L1"]
    try:
        from model_measurement.routes import _stair_points
        from model_measurement.routes import _links_listed
        got = rooms_exit_outside(story, {r["id"]: r for r in desc["rooms"]}, desc.get("building"),
                                 _stair_points(desc), _links_listed(desc))
        return {"measures": {OUTSIDE_FACT: got}, "not_measured": {}}
    except Stop as s:
        return {"measures": {}, "not_measured": {OUTSIDE_FACT: s.reason}}


def oracle(kinds, joins, corridor=None, function=None, corridor_exit=True, within=None, hall="corridor"):
    """True, False, or None (not known): see the module's words."""
    if "stair" in kinds:                                 # travel along an exterior stair isn't read: the story isn't
        return None
    if "marked" not in kinds and not (corridor is not None and corridor_exit):
        return None                                      # no exit marked on the story: its routes aren't read
    owner = list(range(3))
    for i, j in enumerate(joins):
        if j in ("door", "passage"):
            old, new = owner[i + 1], owner[i]
            owner = [new if o == old else o for o in owner]
    spaces = {o: {i for i in range(3) if owner[i] == o} for o in set(owner)}
    touched = {owner[i] for i in (corridor or ())}
    shared = len(touched) >= 2 and function == "residential" and within is False and corridor_exit and \
        hall == "corridor"                               # a lobby may be a dwelling's own foyer
    verdicts = []
    for o, members in spaces.items():
        has = {kinds[i] for i in members}
        if "marked" in has or (corridor is not None and corridor_exit and touched == {o}):  # its own door, or its
            verdicts.append(True)                                                           # vestibule's
        elif "unmarked" in has:
            verdicts.append(None)
        elif shared and o in touched:
            verdicts.append(False)
        else:
            verdicts.append(None)
    if corridor is not None and not touched:            # a corridor opening into no room: a space of its own
        verdicts.append(True if corridor_exit else None)
    if False in verdicts:
        return False
    return None if None in verdicts else True


@pytest.mark.parametrize("joins", list(itertools.product(SIDES, repeat=2)), ids="-".join)
def test_the_walk_every_value_measured_is_the_oracles_and_every_other_needs_review(joins):
    seen = set()
    for kinds in itertools.product(KINDS, repeat=3):
        sp = _story(row(kinds, joins))
        want = oracle(kinds, joins)
        seen.add(sp["measures"].get(OUTSIDE_FACT))
        if want is None:
            assert OUTSIDE_FACT not in sp["measures"], (kinds, joins, sp["measures"].get(OUTSIDE_FACT))
            assert OUTSIDE_FACT in sp["not_measured"], (kinds, joins)
        else:
            assert sp["measures"].get(OUTSIDE_FACT) is want, (kinds, joins, sp["not_measured"].get(OUTSIDE_FACT))
    assert True in seen, seen                                                                  # never vacuous


@pytest.mark.parametrize("joins", list(itertools.product(("door", "wall"), repeat=2)), ids="-".join)
def test_the_walk_with_a_corridor(joins):
    """The same row with a corridor along it, each room opening into it or not (shared, a vestibule of one space, or
    opening into none), with and without its own exit, the rooms residential or with no function, the building
    stating corridors within dwelling units no or nothing."""
    seen = set()
    for opens in itertools.product((False, True), repeat=3):
        corridor = [i for i in range(3) if opens[i]]
        for kinds, function, corridor_exit, within, hall in itertools.product(
                itertools.product(("marked", "unmarked", "none"), repeat=3), ("residential", None), (True, False),
                (False, None), ("corridor", "lobby")):
            if hall == "lobby" and (function is None or within is None):
                continue                                 # the lobby matters only where a corridor could be shared
            sp = _story(row(kinds, joins, corridor=corridor, function=function, corridor_exit=corridor_exit,
                            within=within, hall=hall))
            want = oracle(kinds, joins, corridor, function, corridor_exit, within, hall)
            seen.add(sp["measures"].get(OUTSIDE_FACT))
            case = (kinds, joins, corridor, function, corridor_exit, within, hall)
            if want is None:
                assert OUTSIDE_FACT not in sp["measures"], (case, sp["measures"].get(OUTSIDE_FACT))
            else:
                assert sp["measures"].get(OUTSIDE_FACT) is want, (case, sp["not_measured"].get(OUTSIDE_FACT))
    assert True in seen and (False in seen or "wall" not in joins), seen           # never vacuous


def test_a_hallway_within_one_tenant_or_house_is_never_a_no():
    """Review round 2 (PR 2): a shop with its front door marked and toilets off a back corridor (with or without its
    own rear exit), and a house with bedrooms off a hall marked a corridor, read "no" (the corridor counted as shared),
    failing a one-exit story outright. A corridor is shared only between dwelling units the building says have no
    corridor within them."""
    for corridor_exit in (True, False):
        shop = row(("marked", "none", "none"), ("wall", "wall"), uses=("other", "toilet", "toilet"),
                   corridor=[0, 1, 2], corridor_exit=corridor_exit)
        assert _story(shop)["measures"].get(OUTSIDE_FACT) is not False, corridor_exit
    house = row(("marked", "none", "none"), ("wall", "wall"), corridor=[0, 1, 2], function="residential")
    assert _story(house)["measures"].get(OUTSIDE_FACT) is not False
    stated = row(("marked", "none", "none"), ("wall", "wall"), corridor=[0, 1, 2], function="residential",
                 within=False)
    assert _story(stated)["measures"][OUTSIDE_FACT] is False         # the building says the corridor is no unit's


def test_a_room_reached_through_another_of_its_space_is_part_of_it():
    """Review round 1 (PR 2): a bedroom off a living room with its own door out, a workroom off a shop, a closet off a
    room whose use isn't given (so not taken as served, decision 1a), a toilet off a lockable room: each is part of the
    space whose exit its occupants reach through it (1016.2), never a space without an exit ("no" removed the item 2
    review, so a one-exit story failed outright)."""
    for use, host in (("other", {}), ("workroom", {}), ("closet", {"use": None}), ("toilet", {"lockable": True}),
                      ("other", {"sleeping": True})):
        desc = row(("marked", "marked", "marked"), ("wall", "wall"))
        desc["rooms"][0].update(host)
        desc["rooms"].append(room("k", rect(0, 10.5, 5, 15), use=use, lockable=False, pass_through=False,
                                  sleeping=use == "other"))
        desc["doors"].append(door("dk", (2.5, 10.25), (1, 0), ("r0", "k")))
        sp = _story(desc)
        assert sp["measures"].get(OUTSIDE_FACT) is not False, (use, host, sp["not_measured"].get(OUTSIDE_FACT))


def test_an_unknown_space_or_a_room_not_read_is_never_a_yes():
    desc = row(("marked", "marked", "marked"), ("wall", "wall"))
    desc["unknown_spaces"] = [{"id": "u", "name": "Space 9", "level": "L1", "outline": [[0, 11], [5, 11], [5, 15]]}]
    sp = _story(desc)
    assert OUTSIDE_FACT not in sp["measures"]
    assert sp["not_measured"][OUTSIDE_FACT].startswith(STOPS["story_not_measured"].split("{")[0])


APARTMENT = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json"


def test_the_four_unit_apartment_its_apartments_reach_the_outside_only_by_the_corridor_and_stairs():
    """As marked for the eval (each apartment residential) and stating its corridors are within no dwelling unit:
    the two apartments on each story reach the outside only through the shared corridor and the stair enclosures
    (themselves exits, left out): no on both stories. As Revit sent it (no function, no corridor fact): not
    measured."""
    sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
    import make_ny_build_data as build
    interior = build.interior_of()
    interior["building"] = {**interior["building"], "corridors_within_dwelling_units": False}
    # its stairs within the two enclosures (exits), and no ramp or ladder: said, as the Revit reader says them
    interior["stairs"] = [{"id": f"flight {x}", "nosings": [[[x, 13, 0], [x, 17, 0]]]} for x in (4.5, 55.5)]
    interior["has_none"] = [{"kind": k, "source": "the eval building: none drawn"}
                            for k in ("ramp", "alternating_tread_device", "ships_ladder")]
    assert [s["measures"][OUTSIDE_FACT] for s in measure(interior)["parts"]["story"]] == [False, False]
    got = measure(json.loads(APARTMENT.read_text(encoding="utf-8"))["interior"])
    for s in got["parts"]["story"]:
        assert s["not_measured"][OUTSIDE_FACT].startswith(STOPS["outside_hall_unclear"].split("{")[0])


def test_each_reason_has_a_case():
    seen = set()
    desc = row(("marked", "unmarked", "marked"), ("wall", "wall"))
    reason = _story(desc)["not_measured"][OUTSIDE_FACT]
    assert reason == STOPS["outside_door_not_marked"].format(name="r1", door="o1")
    seen.add("outside_door_not_marked")
    only_exit = description([room("s", rect(0, 0, 10, 10), use="other")],
                            [door("in", (10.25, 5), (0, 1), ("s", "outside"), exit_id="s", kind="exit_enclosure")])
    sp = _story(only_exit)
    assert sp["not_measured"][OUTSIDE_FACT] == STOPS["outside_no_rooms"], sp["not_measured"]
    seen.add("outside_no_rooms")
    alone = _story(row(("marked", "none", "marked"), ("wall", "wall")))["not_measured"][OUTSIDE_FACT]
    assert alone == STOPS["outside_way_unclear"].format(name="r1")
    seen.add("outside_way_unclear")
    hall = _story(row(("marked", "none", "none"), ("wall", "wall"), corridor=[0, 1, 2]))["not_measured"][OUTSIDE_FACT]
    assert hall == STOPS["outside_hall_unclear"].format(name="r1")
    seen.add("outside_hall_unclear")
    into = _story(_into_exit(("none", "marked", "marked"), [0, 1]))["not_measured"][OUTSIDE_FACT]
    assert into == STOPS["outside_into_exit"].format(name="r0", door="se")
    seen.add("outside_into_exit")
    seen.add("outside_stair")                            # test_a_stair_within_a_space_on_the_shared_corridor...
    seen.add("outside_link_elsewhere")                   # test_a_door_drawn_on_another_level_is_never_a_no
    seen.add("outside_link_unread")                      # test_unreadable_doors_or_openings_never_crash_or_give_a_no
    assert seen == OUTSIDE_KEYS


def _into_exit(kinds, opens):
    """The row with a corridor, residential, the building stating no corridor within a unit, and room 0's door out
    replaced by its own door into a stair enclosure (an exit) that discharges outside."""
    desc = row(kinds, ("wall", "wall"), corridor=opens, function="residential", within=False)
    desc["rooms"].append(room("s", rect(0, -6.5, 10, -0.5), use="other", lockable=False, pass_through=False))
    desc["doors"] = [d for d in desc["doors"] if d["id"] != "o0"]
    desc["doors"].append(door("se", (5, -0.25), (1, 0), ("r0", "s"), exit_id="s", kind="exit_enclosure"))
    desc["doors"].append(door("so", (-0.25, -3.5), (0, 1), ("s", "outside"), exit_id="s", kind="exit_enclosure"))
    return desc


def test_a_foyer_or_a_space_with_its_own_door_into_an_exit_is_never_a_no():
    """Review round 3 (PR 2): a house's foyer marked a lobby, opening onto its living room and study, read as a
    shared corridor ("no"); and a space with its own door into a stair enclosure, opening onto the shared corridor
    too, read "no" though its own exit door may be its direct way out. Neither is known: not measured. (A space with
    no exit of its own on the shared corridor is still "no".)"""
    foyer = row(("none", "none", "none"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False,
                hall="lobby")
    assert _story(foyer)["measures"].get(OUTSIDE_FACT) is not False
    got = _story(_into_exit(("none", "marked", "marked"), [0, 1]))
    assert got["not_measured"][OUTSIDE_FACT] == STOPS["outside_into_exit"].format(name="r0", door="se")
    assert _story(_into_exit(("none", "none", "marked"), [0, 1]))["measures"][OUTSIDE_FACT] is False   # room 1


def test_a_space_with_any_way_out_besides_the_shared_corridor_is_never_a_no():
    """Review round 4 (PR 2): a living room on the shared corridor whose own foyer (a lobby or a corridor, with the
    front door marked) also opens into a coat closet read "no" (the foyer, touching two spaces, wasn't merged into
    it); and a space joined to a stair enclosure by an opening with no door read "no". "No" stands only where the
    shared corridor is the space's one way out of itself."""
    for hall in ("lobby", "corridor"):
        desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
        desc["doors"] = [d for d in desc["doors"] if d["id"] != "o0"]
        desc["rooms"].append(room("f", rect(0, -6.5, 10, -0.5), use=hall, lockable=False, pass_through=True))
        desc["rooms"].append(room("k", rect(10.5, -6.5, 14, -0.5), use="closet", lockable=False, pass_through=False))
        desc["doors"] += [door("fa", (5, -0.25), (1, 0), ("r0", "f")),
                          door("fo", (-0.25, -3.5), (0, 1), ("f", "outside"), exit_id="fo"),
                          door("fk", (10.25, -3.5), (0, 1), ("f", "k"))]
        assert _story(desc)["measures"].get(OUTSIDE_FACT) is not False, hall
        del desc["rooms"][-1]                            # without the closet the foyer is the living room's own:
        desc["doors"] = [d for d in desc["doors"] if d["id"] != "fk"]       # its front door, so yes
        assert _story(desc)["measures"][OUTSIDE_FACT] is True, hall
    desc = _into_exit(("none", "marked", "marked"), [0, 1])
    desc["doors"] = [d for d in desc["doors"] if d["id"] != "se"]
    desc["passages"] = [{"rooms": ["r0", "s"], "line": [[0, 0], [10, 0]]}]
    desc["rooms"][-1]["floor"] = [list(p) for p in rect(0, -6, 10, 0)]
    got = _story(desc)
    assert got["not_measured"][OUTSIDE_FACT] == STOPS["outside_into_exit"].format(
        name="r0", door="the opening between r0 and s")


def test_a_stair_within_a_space_on_the_shared_corridor_is_never_a_no():
    """Review round 5 (PR 2): the upper floor of a two-story unit on the shared corridor, its own stair down to its
    front door: the stair wasn't seen, so "no". A stair in a space is another way out of it: not measured; a stair
    within an exit enclosure leaves the apartment's "no" standing."""
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    desc["stairs"] = [{"id": "st", "nosings": [[[2, 2, 0], [4, 2, 0]], [[2, 3, 0.6], [4, 3, 0.6]]]}]
    got = _story(desc)
    assert got["not_measured"][OUTSIDE_FACT] == STOPS["outside_stair"].format(name="r0")
    desc["stairs"] = [{"id": "st", "nosings": [[[2, 50, 0], [4, 50, 0]]]}]          # in no room at all: may be
    assert _story(desc)["measures"].get(OUTSIDE_FACT) is not False                 # anywhere
    desc["stairs"] = [{"id": "st", "nosings": [[[22, 2, 0], [24, 2, 0]]]}]          # in room 2, a space opening only
    assert _story(desc)["measures"].get(OUTSIDE_FACT) is not False                 # outside: may be room 0's own
    desc["stairs"] = [{"id": "st", "nosings": [[[13, 2, 0], [15, 2, 0]]]}]          # in room 1, on the corridor
    assert _story(desc)["measures"][OUTSIDE_FACT] is False
    desc["stairs"] = [{"id": "st", "nosings": "unreadable"}]
    assert _story(desc)["measures"].get(OUTSIDE_FACT) is not False


def test_stairs_not_read_or_a_ramp_not_ruled_out_is_never_a_no():
    """Review round 6 (PR 2): no stairs list (not read: the format's silence) was taken as no stairs, so the upper floor
    of a two-story unit on the shared corridor read "no" though its own stair may lead to its door out. A stair list
    not given, a ramp, alternating tread device or ship's ladder not said to be none: may be anywhere, never a "no".
    Malformed stairs never crash the measuring."""
    from model_measurement.routes import _stair_points
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    assert _story(desc)["measures"][OUTSIDE_FACT] is False
    for drop in ("stairs", "has_none"):
        d = {k: v for k, v in desc.items() if k != drop}
        got = _story(d)
        assert got["not_measured"][OUTSIDE_FACT] == STOPS["outside_stair"].format(name="r0"), drop
    for bad in (5, [{"nosings": [[{"x": 1}, [1, 1, 0]]]}]):
        assert {"points": []} in _stair_points({**desc, "stairs": bad})


@pytest.mark.parametrize("change", ["contradicted", "extra_key", "reading_not_bool", "twice", "unhashable",
                                    "reading_true"])
def test_a_has_none_claim_the_format_refuses_never_rules_out_a_ramp(change):
    """Review round 7 (PR 2): the routes read has_none loosely, taking claims the format refuses (contradicted by a
    ramp list, a mistyped key, a reading not true or false, a kind said twice) as "no ramps", giving a wrong "no"; an
    unhashable kind crashed the measuring. Now only the format's own claims count."""
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    if change == "contradicted":
        desc["ramps"] = [{"id": "rp"}]
    elif change == "extra_key":
        desc["has_none"][0] = {"kind": "ramp", "source": "s", "readng": True}
    elif change == "reading_not_bool":
        desc["has_none"][0] = {"kind": "ramp", "source": "s", "reading": "yes"}
    elif change == "twice":
        desc["has_none"].append({"kind": "ramp", "source": "t", "reading": True})
    elif change == "reading_true":                       # a reading of the law, not what the drawing shows (round 16)
        desc["has_none"][0] = {"kind": "ramp", "source": "s", "reading": True}
    else:
        desc["has_none"].append({"kind": {"x": 1}, "source": "s"})
        desc["has_none"].append({"kind": ["ramp"], "source": "s"})
    if change != "unhashable":
        assert _story(desc)["not_measured"][OUTSIDE_FACT] == STOPS["outside_stair"].format(name="r0"), change
    got = measure(desc)["parts"]["story"][0]
    if change == "unhashable":
        assert got["measures"][OUTSIDE_FACT] is False   # the valid claims still stand, and nothing crashed
    else:
        assert got["not_measured"][OUTSIDE_FACT] == STOPS["outside_stair"].format(name="r0"), change


def test_a_stair_partly_in_no_room_may_be_within_the_space():
    """Review round 8 (PR 2): the upper floor of a two-story unit whose stairwell is left out of its room's outline
    (its top nosings in no room) and whose lower nosings run under the corridor: one point in another room counted it
    outside, "no". A stair is outside the space only when every nosing stands in another room. A malformed openings
    list beside a basement claim never stops the measuring."""
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    desc["rooms"][0]["floor"] = [[0, 0], [10, 0], [10, 10], [3, 10], [3, 7], [0, 7]]
    desc["stairs"] = [{"id": "st", "nosings": [[[0.5, 8.5, 0], [2.5, 8.5, 0]], [[0.5, 9.5, -0.6], [2.5, 9.5, -0.6]],
                                               [[0.5, 12, -2], [2.5, 12, -2]], [[0.5, 13, -2.6], [2.5, 13, -2.6]]]}]
    assert _story(desc)["not_measured"][OUTSIDE_FACT] == STOPS["outside_stair"].format(name="r0")
    bad = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    bad["has_none"].append({"kind": "basement", "source": "s"})
    bad["openings"] = 5
    measure(bad)                                         # returns: never a crash


def test_a_stair_in_a_room_with_no_door_may_be_the_spaces_own():
    """Review round 9 (PR 2): a stair wholly in a room drawn with no door or opening (the unit's own stairwell, its
    opening left out) counted as elsewhere: "no". Only rooms joined to something place a stair elsewhere. A nosing
    that isn't two ends makes its stair one that may be anywhere."""
    from model_measurement.routes import _stair_points
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    desc["rooms"].append(room("S", rect(0, -6.5, 10, -0.5), use="other", lockable=False, pass_through=False))
    desc["stairs"] = [{"id": "st", "nosings": [[[2, -5, 0], [4, -5, 0]], [[2, -4, 0.6], [4, -4, 0.6]],
                                               [[2, -1.5, 1.2], [4, -1.5, 1.2]]]}]
    assert _story(desc)["measures"].get(OUTSIDE_FACT) is not False
    assert {"points": []} in _stair_points({**desc, "stairs": [{"nosings": [[[22, 2, 0], [24, 2, 0]], []]}]})


@pytest.mark.parametrize("case", ["pair", "closet", "outside_door"])
def test_a_stair_in_rooms_joined_only_to_each_other_or_the_outside_may_be_the_spaces_own(case):
    """Review round 10 (PR 2): a stair in rooms joined only to each other (a stairwell and its landing) or only to the
    outside (a unit's stair hall holding its front door), the opening into the unit left out, still counted as
    elsewhere: "no". Only the shared circulation (halls, exits, and spaces opening into them) places a stair
    elsewhere; a stair in a room of the shared corridor's other space still leaves the "no"."""
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    nosings = [[[1, -5, 0], [3, -5, 0]], [[1, -4, 0.6], [3, -4, 0.6]], [[1, -1.5, 1.2], [3, -1.5, 1.2]]]
    if case == "pair":
        desc["rooms"] += [room("S", rect(0, -6.5, 5, -0.5), use="other", lockable=False, pass_through=False),
                          room("L", rect(5, -6.5, 10, -0.5), use="other", lockable=False, pass_through=False)]
        desc["passages"].append({"rooms": ["S", "L"], "line": [[5, -6.5], [5, -0.5]]})
    elif case == "closet":
        desc["rooms"] += [room("S", rect(0, -6.5, 5, -0.5), use="other", lockable=False, pass_through=False),
                          room("K", rect(5.5, -6.5, 10, -0.5), use="closet", lockable=False, pass_through=False)]
        desc["doors"].append(door("dk", (5.25, -3.5), (0, 1), ("S", "K")))
    else:
        desc["rooms"].append(room("S", rect(0, -12.5, 10, -0.5), use="other", lockable=False, pass_through=False))
        desc["doors"].append(door("so", (-0.25, -8), (0, 1), ("S", "outside")))
        nosings = [[[1, -11, 0], [3, -11, 0]], [[1, -10, 0.6], [3, -10, 0.6]]]
    desc["stairs"] = [{"id": "st", "nosings": nosings}]
    assert _story(desc)["measures"].get(OUTSIDE_FACT) is not False, case
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    desc["stairs"] = [{"id": "st", "nosings": [[[13, 2, 0], [15, 2, 0]]]}]          # in room 1, on the corridor
    assert _story(desc)["measures"][OUTSIDE_FACT] is False


def test_a_door_drawn_on_another_level_is_never_a_no():
    """Review round 11 (PR 2): room 0's own exterior door put on another level vanished from its story (stopped only
    there), so the shared corridor looked like its one way out: "no". A door or opening the description gives for a
    room of the story but the story didn't read leaves it not measured."""
    desc = row(("marked", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    desc["levels"].append({"id": "L2", "name": "Level 2", "elevation": 10})
    desc["rooms"].append(room("u", rect(0, 0, 10, 10), use="other", lockable=False, pass_through=False, level="L2",
                              floor_elevation=10))
    next(d for d in desc["doors"] if d["id"] == "o0")["level"] = "L2"
    got = {s["id"]: s for s in measure(desc)["parts"]["story"]}["L1"]
    assert got["not_measured"][OUTSIDE_FACT] == STOPS["outside_link_elsewhere"].format(name="r0")


@pytest.mark.parametrize("case", ["hall_alone", "hall_to_outside", "own_foyer", "exit_from_outside"])
@pytest.mark.parametrize("use", ["corridor", "lobby"])
def test_a_stair_in_a_hall_or_exit_no_other_space_shares_may_be_the_spaces_own(case, use):
    """Review round 12 (PR 2): a hall or exit counted as shared circulation by its use alone, so the unit's own
    stairwell marked a corridor or lobby (alone, with its front door, beside its own foyer) or an exit entered only
    from outside placed a stair elsewhere: "no". Only halls two or more spaces open into, the exits entered from them,
    and those spaces' rooms are shared."""
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    nosings = [[[1, -5, 0], [3, -5, 0]], [[1, -4, 0.6], [3, -4, 0.6]], [[1, -1.5, 1.2], [3, -1.5, 1.2]]]
    if case == "hall_alone":
        desc["rooms"].append(room("H", rect(0, -6.5, 10, -0.5), use=use, lockable=False, pass_through=True))
    elif case == "hall_to_outside":
        desc["rooms"].append(room("H", rect(0, -12.5, 10, -0.5), use=use, lockable=False, pass_through=True))
        desc["doors"].append(door("ho", (-0.25, -8), (0, 1), ("H", "outside"), exit_id="ho"))
        nosings = [[[1, -11, 0], [3, -11, 0]], [[1, -10, 0.6], [3, -10, 0.6]]]
    elif case == "own_foyer":
        desc["rooms"] += [room("S", rect(0, -6.5, 5, -0.5), use="other", lockable=False, pass_through=False),
                          room("F", rect(5.5, -6.5, 10, -0.5), use=use, lockable=False, pass_through=True)]
        desc["doors"] += [door("sf", (5.25, -3.5), (0, 1), ("S", "F")),
                          door("fo", (10.25, -3.5), (0, 1), ("F", "outside"), exit_id="fo")]
    else:
        desc["rooms"].append(room("S", rect(0, -6.5, 10, -0.5), use="other", lockable=False, pass_through=False))
        desc["doors"].append(door("se", (-0.25, -3.5), (0, 1), ("S", "outside"), exit_id="S", kind="exit_enclosure"))
    desc["stairs"] = [{"id": "st", "nosings": nosings}]
    assert _story(desc)["measures"].get(OUTSIDE_FACT) is not False, (case, use)


@pytest.mark.parametrize("bad", [("doors", 5), ("passages", 5), ("doors", True), ("passages", 1.5),
                                 ("openings", 5), ("door_sides", "r0"), ("door_sides", None),
                                 ("passage_rooms", ["r0", 5]), ("opening_room", None)])
def test_unreadable_doors_or_openings_never_crash_or_give_a_no(bad):
    """Review rounds 12-13 (PR 2): a doors or passages value that isn't a list crashed the measuring; a door, opening
    or listed opening whose rooms can't be read (it may be any room's), filed on another level so the story itself
    reads whole, was dropped, giving "no"."""
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    desc["levels"].insert(0, {"id": "L2", "name": "Level 2", "elevation": 0})
    desc["rooms"].append(room("u", rect(-10, 0, 0, 10), use="other", lockable=False, pass_through=False, level="L2"))
    key, value = bad
    if key == "door_sides":
        extra = dict(desc["doors"][0], id="x", level="L2")
        if value is None:
            extra.pop("sides")
        else:
            extra["sides"] = value
        desc["doors"].append(extra)
    elif key == "passage_rooms":
        desc["passages"].append({"rooms": value, "line": [[0, 0], [0, 10]], "level": "L2"})
    elif key == "opening_room":
        desc["openings"] = [{"id": "p", "room": value, "operation": "sliding_door", "escape": False}]
    else:
        desc[key] = value
    got = {s["id"]: s for s in measure(desc)["parts"]["story"]}
    assert got["L1"]["measures"].get(OUTSIDE_FACT) is not False, bad
    if key not in ("doors", "passages", "passage_rooms"):    # those also stop the story's own read
        assert got["L1"]["not_measured"][OUTSIDE_FACT] == STOPS["outside_link_unread"], bad


def test_an_opening_drawn_on_another_level_is_never_a_no():
    """The passage half of round 11: an opening joining a room of this story to one on another level leaves it not
    measured."""
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    desc["levels"].insert(0, {"id": "L2", "name": "Level 2", "elevation": 0})
    desc["rooms"].append(room("u", rect(-10, 0, 0, 10), use="other", lockable=False, pass_through=False, level="L2"))
    desc["passages"].append({"rooms": ["u", "r0"], "line": [[0, 0], [0, 10]]})
    got = {s["id"]: s for s in measure(desc)["parts"]["story"]}["L1"]
    assert got["measures"].get(OUTSIDE_FACT) is not False


@pytest.mark.parametrize("operation", ["sliding_door", "side_hinged_door", "pivot", "other", None])
def test_a_door_listed_only_among_the_openings_is_never_a_no(operation):
    """Review round 13 (PR 2): a patio door listed in `openings` (every window and door that could be an escape
    opening) but not in `doors` was never read: the shared corridor looked like the space's one way out, "no". An
    opening that is or may be a door, not read as a door on its story, leaves it not measured; a window doesn't."""
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    o = {"id": "p1", "room": "r0", "escape": False}
    if operation:
        o["operation"] = operation
    desc["openings"] = [o]
    got = _story(desc)
    assert got["measures"].get(OUTSIDE_FACT) is not False, operation
    assert got["not_measured"][OUTSIDE_FACT] == STOPS["outside_link_elsewhere"].format(name="r0")
    for window in ("casement", "fixed"):                 # a window, or a unit that doesn't open: still "no"
        o["operation"] = window
        assert _story(desc)["measures"][OUTSIDE_FACT] is False, window
    o.update(id="o1", operation="side_hinged_door", room=None)  # a listed door, sent among the openings as Revit does
    assert _story(desc)["measures"][OUTSIDE_FACT] is False


@pytest.mark.parametrize("oid", [["p"], {"a": 1}, 7])
def test_an_opening_whose_id_isnt_text_never_crashes_or_gives_a_no(oid):
    """Review round 14 (PR 2): an opening (that may be a door) whose id is a list or dict crashed the measuring (an
    unhashable id looked up among the doors); one with no text id is never a door read on the story."""
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    desc["openings"] = [{"id": oid, "room": "r0", "operation": "sliding_door", "escape": False}]
    got = {s["id"]: s for s in measure(desc)["parts"]["story"]}["L1"]
    assert got["measures"].get(OUTSIDE_FACT) is not False, oid


def test_an_opening_reusing_a_doors_id_for_another_room_is_never_a_no():
    """Review round 14 (PR 2): an opening with a listed door's id was skipped whatever room it named; one naming a room
    the door doesn't join contradicts it, and may be that room's own way out."""
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    desc["openings"] = [{"id": "o1", "room": "r0", "operation": "sliding_door", "escape": False}]
    assert _story(desc)["measures"].get(OUTSIDE_FACT) is not False
    desc["openings"][0]["room"] = "r1"                   # the door's own room: that door, still "no"
    assert _story(desc)["measures"][OUTSIDE_FACT] is False


def test_a_fixed_unit_stating_a_clear_opening_may_be_a_door():
    """Review round 15 (PR 2): a unit marked fixed whose maker's clear opening says it opens (door-sized, at the floor)
    contradicts itself: it may be the room's own door out, so the story isn't measured; a plain fixed unit is still
    never a way out."""
    desc = row(("none", "marked", "marked"), ("wall", "wall"), corridor=[0, 1], function="residential", within=False)
    desc["openings"] = [{"id": "p1", "room": "r0", "operation": "fixed", "escape": False,
                         "frame": {"left": 0, "right": 36, "bottom": 0, "top": 80},
                         "stated_clear": {"width": 34, "height": 78, "bottom": 0, "source": "maker"}}]
    got = _story(desc)
    assert got["measures"].get(OUTSIDE_FACT) is not False
    assert got["not_measured"][OUTSIDE_FACT] == STOPS["outside_link_elsewhere"].format(name="r0")
    del desc["openings"][0]["stated_clear"]
    assert _story(desc)["measures"][OUTSIDE_FACT] is False


@pytest.mark.parametrize("y, expect_no", [(10.02, False), (12, True)])
def test_a_stair_within_an_inch_of_the_space_may_be_its_own(y, expect_no):
    """Review round 16 (PR 2): a nosing up to an inch inside a shared corridor that opens straight into the space (a
    passage, no wall) may be the space's own stair: not a "no". One well inside the corridor is the corridor's."""
    rooms = [room("r0", rect(0, 0, 10, 10), use="other", lockable=False, pass_through=False, function="residential"),
             room("r1", rect(10.5, 0, 20.5, 9.5), use="other", lockable=False, pass_through=False,
                  function="residential"),
             room("c", rect(0, 10, 20.5, 16), use="corridor", lockable=False, pass_through=True)]
    doors = [door("o1", (15, -0.25), (1, 0), ("r1", "outside"), exit_id="o1", kind="exterior_at_discharge"),
             door("e1", (15, 9.75), (1, 0), ("r1", "c")),
             door("oc", (-0.25, 13), (0, 1), ("c", "outside"), exit_id="oc")]
    desc = description(rooms, doors, [(("r0", "c"), [(0, 10), (10, 10)])])
    desc["stairs"] = [{"id": "st", "nosings": [[[2, y, 0], [4, y, 0]], [[2, y, 0.6], [4, y, 0.6]]]}]
    desc["has_none"] = [{"kind": k, "source": "s"} for k in ("ramp", "alternating_tread_device", "ships_ladder")]
    desc["building"] = {"corridors_within_dwelling_units": False}
    got = _story(desc)["measures"].get(OUTSIDE_FACT)
    assert (got is False) is expect_no, (y, got)


def test_no_stairs_beside_more_than_one_story_never_settles_the_space():
    """"No stairs" (an empty list) isn't taken where the building has more than one floor (#279's refusal, merged into
    the story facts): a stair left undrawn may stand within the space, its own way out to another story, so the "no"
    a shared corridor gives (above) isn't measured, whether the second floor is drawn or only stated."""
    from model_measurement.routes import measure
    stated = row(("marked", "none", "none"), ("wall", "wall"), corridor=[0, 1, 2], function="residential",
                 within=False)
    assert _story(stated)["measures"][OUTSIDE_FACT] is False
    two = {**stated, "building": {**stated["building"], "stories_above_grade_plane": 2}}
    got = _story(two)
    assert OUTSIDE_FACT not in got["measures"], got
    assert "the model says it has none but the building may have another story" in got["not_measured"][OUTSIDE_FACT]
    story = next(s for s in measure(stated, stated_stories=(2, "the check gives {n}"))["parts"]["story"])
    assert OUTSIDE_FACT not in story["measures"] and OUTSIDE_FACT in story["not_measured"], story
