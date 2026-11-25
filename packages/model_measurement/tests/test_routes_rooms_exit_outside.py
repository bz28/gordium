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
                "outside_into_exit"}
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
        got = rooms_exit_outside(story, {r["id"]: r for r in desc["rooms"]}, desc.get("building"))
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
    desc = _into_exit(("none", "marked", "marked"), [0, 1])
    desc["doors"] = [d for d in desc["doors"] if d["id"] != "se"]
    desc["passages"] = [{"rooms": ["r0", "s"], "line": [[0, 0], [10, 0]]}]
    desc["rooms"][-1]["floor"] = [list(p) for p in rect(0, -6, 10, 0)]
    assert _story(desc)["measures"].get(OUTSIDE_FACT) is not False
