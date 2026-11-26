"""The room each flight of stairs stands in (model_measurement/routes/stair_rooms.py, section group 7c): a flight is in
an exit stair enclosure only where every nosing end stands over a room the routes read as itself an exit; a room not
an exit gives no, and anything unclear gives no value (so the dwelling-unit exceptions stay open: needs review)."""

from pathlib import Path

import pytest
import yaml

from model_measurement.routes import measure
from model_measurement.routes.stair_rooms import apply, in_exit_enclosure
from model_measurement.routes.stops import STOPS

REPO = Path(__file__).resolve().parents[3]
STAIR_KEYS = {"stair_no_nosings", "stair_room_unread", "stair_over_no_room", "stair_room_exit_unknown"}


def _room(rid, x0, x1, floor=0):
    return {"id": rid, "name": rid, "floor_elevation": floor, "floor": [[x0, 0], [x1, 0], [x1, 40], [x0, 40]]}


def _stair(xs=(10, 20, 30), z=7):
    return {"id": "s", "nosings": [[[x, 0, z * (n + 1)], [x, 36, z * (n + 1)]] for n, x in enumerate(xs)]}


def _desc(rooms, stairs):
    return {"units": "in", "rooms": rooms, "stairs": stairs}


def _exit(**ids):
    return [{"id": k, "measures": {} if v is None else {"space_is_exit": v}} for k, v in ids.items()]


def test_a_flight_wholly_over_an_exit_enclosure_is_in_one():
    got = in_exit_enclosure(_desc([_room("enc", 0, 40)], [_stair()]), _exit(enc=True))
    assert got == {"s": True}


def test_a_flight_over_a_room_not_an_exit_is_not():
    got = in_exit_enclosure(_desc([_room("unit", 0, 40)], [_stair()]), _exit(unit=False))
    assert got == {"s": False}
    # one nosing over a dwelling's room is enough: part of the flight is in it
    got = in_exit_enclosure(_desc([_room("enc", 0, 25), _room("unit", 25, 40)], [_stair()]),
                            _exit(enc=True, unit=False))
    assert got == {"s": False}


def test_the_floor_under_a_nosing_is_the_highest_at_or_below_it():
    # a flight rising from an enclosure's ground floor to a room on the floor above: the upper room counts only
    # where its floor is at or below the nosing (the top nosing, at its floor)
    up = _room("up", 25, 40, floor=21)
    assert in_exit_enclosure(_desc([_room("enc", 0, 40), up], [_stair()]), _exit(enc=True, up=False)) == {"s": False}
    up = _room("up", 25, 40, floor=22)                       # above the top nosing (21): not under the flight
    assert in_exit_enclosure(_desc([_room("enc", 0, 40), up], [_stair()]), _exit(enc=True, up=False)) == {"s": True}


def test_a_nosing_on_a_walls_face_is_in_the_room():
    got = in_exit_enclosure(_desc([_room("enc", 10, 30)], [_stair()]), _exit(enc=True))
    assert got == {"s": True}


@pytest.mark.parametrize("key", sorted(STAIR_KEYS))
def test_each_unclear_case_gives_no_value_with_its_reason(key):
    rooms, spaces, stair = [_room("enc", 0, 40)], _exit(enc=True), _stair()
    if key == "stair_no_nosings":
        stair = {"id": "s", "nosings": []}
    elif key == "stair_room_unread":
        rooms = rooms + [{"id": "bad", "name": "bad", "floor_elevation": 0, "floor": [[0, 0]]}]
    elif key == "stair_over_no_room":
        rooms = [_room("enc", 0, 15)]
    elif key == "stair_room_exit_unknown":
        spaces = _exit(enc=None)
    got = in_exit_enclosure(_desc(rooms, [stair]), spaces)["s"]
    assert not isinstance(got, bool) and got.key == key and got.reason.startswith(STOPS[key].split("{")[0])
    part = {"id": "s", "measures": {}, "not_measured": {}, "more": {"stair_risers": 3}}
    apply([part], _desc(rooms, [stair]), spaces)
    assert "stair_in_exit_enclosure" not in part["measures"]
    assert part["not_measured"]["stair_in_exit_enclosure"] == got.reason


def test_apply_gives_the_rules_the_room_and_the_risers():
    part = {"id": "s", "measures": {"stair_handrail_sides": 1},
            "not_measured": {"stair_in_exit_enclosure": "not yet", "stair_riser_count": "not yet"},
            "more": {"stair_risers": 3}}
    apply([part], _desc([_room("enc", 0, 40)], [_stair()]), _exit(enc=True))
    assert part["measures"] == {"stair_handrail_sides": 1, "stair_in_exit_enclosure": True, "stair_riser_count": 3,
                                "stair_handrail_each_side": False}
    # no foot or overhead given: the headroom past the bottom riser isn't measured, with the interior measuring's reason
    assert set(part["not_measured"]) == {"stair_headroom_past_bottom"}
    assert "bottom elevation" in part["not_measured"]["stair_headroom_past_bottom"]


def test_each_side_is_both_sides_and_unknown_where_the_sides_are():
    for sides, each in ((2, True), (1, False), (0, False)):
        part = {"id": "s", "measures": {"stair_handrail_sides": sides}, "not_measured": {}, "more": {}}
        apply([part], _desc([_room("enc", 0, 40)], [_stair()]), _exit(enc=True))
        assert part["measures"]["stair_handrail_each_side"] is each
    part = {"id": "s", "measures": {}, "not_measured": {"stair_handrail_sides": "a handrail runs part way"}, "more": {}}
    apply([part], _desc([_room("enc", 0, 40)], [_stair()]), _exit(enc=True))
    assert "stair_handrail_each_side" not in part["measures"]
    assert part["not_measured"]["stair_handrail_each_side"] == "a handrail runs part way"


def _overhead(stair, *surfaces):
    return {**stair, "bottom_elevation": 0, "overhead": [[[x0, -10, z], [x1, -10, z], [x1, 50, z], [x0, 50, z]]
                                                         for x0, x1, z in surfaces]}


def test_the_headroom_past_the_bottom_riser_follows_the_nosing_line_down_one_tread():
    """1011.3: risers 7 in, treads 10 in, the first nosing at x 10, 7 in up: the line carried down meets the floor at
    x 0. A ceiling at 87 in over all of it leaves 80 in at the first nosing and more behind it, where the line is
    lower; a beam at 85 in over the stretch alone (x 2 to 4) leaves 85 - 7 * (x - 0) / 10 at its far edge, 82.2 in."""
    stair = _stair()
    desc = _desc([_room("enc", -20, 40)], [_overhead(stair, (-20, 40, 87))])
    part = {"id": "s", "measures": {}, "not_measured": {}, "more": {}}
    apply([part], desc, _exit(enc=True))
    assert part["measures"]["stair_headroom_past_bottom"] == 80
    desc = _desc([_room("enc", -20, 40)], [_overhead(stair, (-20, 2, 120), (2, 4, 85), (4, 40, 120))])
    part = {"id": "s", "measures": {}, "not_measured": {}, "more": {}}
    apply([part], desc, _exit(enc=True))
    assert part["measures"]["stair_headroom_past_bottom"] == pytest.approx(85 - 2.8)
    # the stretch one tread back (x 0): a beam beyond it is the landing's, not the flight's
    desc = _desc([_room("enc", -20, 40)], [_overhead(stair, (-20, -0.5, 60), (-0.5, 40, 120))])
    part = {"id": "s", "measures": {}, "not_measured": {}, "more": {}}
    apply([part], desc, _exit(enc=True))
    assert part["measures"]["stair_headroom_past_bottom"] > 80
    # nothing over part of the stretch: no value (a gap could be open sky or something not sent)
    desc = _desc([_room("enc", -20, 40)], [_overhead(stair, (5, 40, 120))])
    part = {"id": "s", "measures": {}, "not_measured": {}, "more": {}}
    apply([part], desc, _exit(enc=True))
    assert "stair_headroom_past_bottom" not in part["measures"]
    assert "doesn't cover" in part["not_measured"]["stair_headroom_past_bottom"]


@pytest.mark.parametrize("variant", ["compliant", "failing"])
def test_the_stair_test_buildings_flights_are_in_its_exit_enclosure(variant):
    d = yaml.safe_load((REPO / f"test_data/test_sites/new_york/stair_enclosure/stair_enclosure_{variant}.yaml")
                       .read_text(encoding="utf-8"))
    assert in_exit_enclosure(d, measure(d)["parts"]["space"]) == {"f1": True, "f2": True}
    # were its Level 1 room a space (a dwelling's room), both flights would stand partly in it
    spaces = measure(d)["parts"]["space"]
    for p in spaces:
        if p["id"] == "L1S":
            p["measures"]["space_is_exit"] = False
    assert in_exit_enclosure(d, spaces) == {"f1": False, "f2": False}


def test_a_taller_bottom_riser_carries_the_stretch_to_where_the_line_meets_the_floor():
    """Review round 1 of group 7c (P0): a 6 7/8 in bottom riser under 6 1/2 in ones, on 11 in treads. The line through
    the nosings, carried down at its slope (6.5 in per 11 in), meets the floor 11.635 in behind the first nosing, past
    one tread: a beam at 80 in over the strip 11.05 to 11.6 in back stands 79.65 to 79.98 in over the line, under 80.
    Measured back one tread alone it was missed (113 in)."""
    stair = {"id": "s", "bottom_elevation": 0,
             "nosings": [[[x, 0, z], [x, 36, z]] for x, z in ((10, 6.875), (21, 13.375), (32, 19.875))]}
    desc = _desc([_room("enc", -20, 40)], [_overhead(stair, (-20, -1.6, 200), (-1.6, -1.05, 80), (-1.05, 40, 200))])
    part = {"id": "s", "measures": {}, "not_measured": {}, "more": {}}
    apply([part], desc, _exit(enc=True))
    assert part["measures"]["stair_headroom_past_bottom"] < 80
    assert part["measures"]["stair_headroom_past_bottom"] == pytest.approx(80 - (6.875 - 11.05 * 6.5 / 11), abs=1e-6)


def test_a_shorter_bottom_riser_reads_the_headroom_from_the_floor_where_the_line_is_below_it():
    """Review round 2 of group 7c (P1): a 6 3/4 in bottom riser under 7 in ones, on 11 in treads: the line through
    the nosings meets the floor 10.6 in behind the first nosing, short of one tread depth. Past that the line is under
    the floor, so the height is taken from the floor: a beam 79.95 in up, 10.9 to 11 in back, is 79.95 in clear, under
    80 (from the line it read 80.14)."""
    stair = {"id": "s", "bottom_elevation": 0,
             "nosings": [[[x, 0, z], [x, 36, z]] for x, z in ((10, 6.75), (21, 13.75), (32, 20.75))]}
    desc = _desc([_room("enc", -20, 40)], [_overhead(stair, (-20, -1, 200), (-1, -0.9, 79.95), (-0.9, 40, 200))])
    part = {"id": "s", "measures": {}, "not_measured": {}, "more": {}}
    apply([part], desc, _exit(enc=True))
    assert part["measures"]["stair_headroom_past_bottom"] == pytest.approx(79.95, abs=1e-6)


def test_the_stretch_ends_one_tread_back_from_the_first_nosing_where_the_line_meets_the_floor_sooner():
    """Review round 2 (P3): "one tread depth beyond the bottom riser" never reaches farther than one tread behind the
    first nosing (the riser's face stands at or behind the nosing): a low beam just beyond it, over even 7 in risers
    on 10 in treads, is the landing's (the landings flag), not this measure's."""
    stair = _stair()
    desc = _desc([_room("enc", -20, 40)], [_overhead(stair, (-20, -0.1, 75), (-0.1, 40, 200))])
    part = {"id": "s", "measures": {}, "not_measured": {}, "more": {}}
    apply([part], desc, _exit(enc=True))
    assert part["measures"]["stair_headroom_past_bottom"] > 80
    desc = _desc([_room("enc", -20, 40)], [_overhead(stair, (-20, 0.1, 75), (0.1, 40, 200))])
    part = {"id": "s", "measures": {}, "not_measured": {}, "more": {}}
    apply([part], desc, _exit(enc=True))
    assert part["measures"]["stair_headroom_past_bottom"] < 80
