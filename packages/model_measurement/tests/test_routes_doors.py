"""Each door's `means_of_egress_door` part (model_measurement/routes/doors.py, section group 6a): every door the
description gives is a part, and its clear width and height come ONLY from the maker's stated clear opening, never
from the door's plan width alone, its size or its leaf (the hard condition: a door with none isn't measured, so
BCNYS 1010.1.1 needs review for it, never a pass)."""

import copy
import sys
from pathlib import Path

import pytest

from model_measurement.routes import measure
from model_measurement.routes.doors import door_parts
from model_measurement.routes.floor import read
from model_measurement.routes.stops import STOPS

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import description, door, rect, room  # noqa: E402

DOOR_KEYS = {"door_no_stated_clear", "door_clear_not_read", "door_clear_disagree", "door_leaves_not_given",
             "door_leaves_not_read", "door_exit_kind_not_read", "door_sides_not_read", "door_side_no_use",
             "door_side_room_not_read"}
STATED = {"width": 34 / 12, "height": 80 / 12, "source": "maker's catalogue, p.4"}


def _office(**door_more):
    """A room 0 to 20 by 0 to 15 on a corridor 15.5 to 23.5 (its door at (10, 15.25)), the corridor's exit west."""
    d = door("d", (10, 15.25), (1, 0), ("r", "c"), width=34 / 12)
    d.update(door_more)
    x = door("x", (-0.25, 19.5), (0, 1), ("c", "outside"), exit_id="A")
    return description([room("r", rect(0, 0, 20, 15), use="other", lockable=True),
                        room("c", rect(0, 15.5, 30, 23.5))], [d, x])


def _parts(desc):
    return {p["id"]: p for p in measure(desc)["parts"]["means_of_egress_door"]}


def _why(part, measure_name):
    return part["not_measured"][measure_name]


def test_a_door_with_a_stated_clear_opening_has_its_sizes_and_sides():
    got = _parts(_office(stated_clear=dict(STATED), leaves=1))
    d = got["d"]
    assert d["within"] == "L1" and d["name"] == "d"
    assert d["measures"]["moe_door_clear_width"] == pytest.approx(34)
    assert d["measures"]["moe_door_clear_height"] == pytest.approx(80)
    assert d["measures"]["moe_door_leaves"] == 1
    assert d["measures"]["moe_door_exit"] is False and d["measures"]["moe_door_exterior"] is False
    assert d["measures"]["moe_door_to_corridor"] is True
    assert d["measures"]["moe_door_to_room_under_10_sf"] is False
    x = got["x"]
    assert x["measures"]["moe_door_exit"] is True and x["measures"]["moe_door_exterior"] is True
    assert x["more"]["exit_kind"] == "exterior_at_discharge"


def test_the_hard_condition_no_stated_clear_opening_no_size_whatever_the_plan_says():
    """The plan's clear width is what the routes pass a door by, but alone it is never the door's clear width here:
    no stated clear opening, neither size is measured (and the routes still read the door)."""
    got = measure(_office())
    d = {p["id"]: p for p in got["parts"]["means_of_egress_door"]}["d"]
    for m in ("moe_door_clear_width", "moe_door_clear_height"):
        assert m not in d["measures"]
        assert _why(d, m) == STOPS["door_no_stated_clear"].format(name="d")
    assert not got["parts"]["story"][0]["not_measured"].get("story_exit_count")   # the routes read it as before


def test_a_malformed_stated_clear_opening_gives_neither_size():
    for bad in ({"width": 34 / 12, "source": "x"}, {"width": 34 / 12, "height": 80 / 12}, "34 x 80",
                {**STATED, "depth": 1}, {**STATED, "width": 0}):
        d = _parts(_office(stated_clear=bad))["d"]
        for m in ("moe_door_clear_width", "moe_door_clear_height"):
            assert m not in d["measures"], bad
            assert _why(d, m).startswith("the door d's clear opening isn't read: "), bad


def test_a_plan_width_that_disagrees_with_the_stated_one_leaves_the_width_unmeasured():
    d = _office(stated_clear=dict(STATED))
    d["doors"][0]["plan"]["clear_width"] = 36 / 12
    got = _parts(d)["d"]
    assert "moe_door_clear_width" not in got["measures"]
    assert _why(got, "moe_door_clear_width") == STOPS["door_clear_disagree"].format(name="d", where="plan", size="width",
                                                                              other=36.0, stated=34.0)
    assert got["measures"]["moe_door_clear_height"] == pytest.approx(80)        # its height is the maker's still
    d["doors"][0]["plan"]["clear_width"] = (34 + 1 / 32) / 12                      # within 1/16 in: the same
    assert _parts(d)["d"]["measures"]["moe_door_clear_width"] == pytest.approx(34)
    d["doors"][0]["plan"]["clear_width"] = "wide"
    assert _why(_parts(d)["d"], "moe_door_clear_width").startswith("the door d's clear opening isn't read: ")


def test_a_door_the_routes_cant_read_is_still_a_part():
    """No plan: the routes can't place it (its story's routes need review), but it is still a door of the building:
    its part is there, measured from its stated clear opening, so a rule over every door never passes without it."""
    d = _office(stated_clear=dict(STATED))
    del d["doors"][0]["plan"]
    got = measure(d)
    parts = {p["id"]: p for p in got["parts"]["means_of_egress_door"]}
    assert parts["d"]["measures"]["moe_door_clear_width"] == pytest.approx(34)
    assert "story_exit_count" in got["parts"]["story"][0]["not_measured"]


def test_leaves_stated_or_not():
    assert _why(_parts(_office())["d"], "moe_door_leaves") == STOPS["door_leaves_not_given"].format(name="d")
    assert _parts(_office(leaves=2))["d"]["measures"]["moe_door_leaves"] == 2
    for bad in (3, 0, True, "1", 1.5):
        assert _why(_parts(_office(leaves=bad))["d"], "moe_door_leaves").startswith("the door d gives its leaves as")


def test_the_leaves_meaning_gives_the_mullioned_pair_reading():
    """A pair with a mullion is two openings, each needing the 32 in: 1 only at the narrower leaf's own clear width.
    The part's meaning (what the rulebook and spreadsheet show) and this module's own account both say so, as the
    interior format and the Revit mark do; a "no mullion" reading alone would let a mullioned pair be stated 1 at
    the pair's whole width."""
    import yaml

    import model_measurement.routes.doors as doors
    root = Path(__file__).resolve().parents[3]
    kinds = yaml.safe_load((root / "packages/rule_format/rule_format/parts.yaml").read_text(encoding="utf-8"))
    meaning = kinds["means_of_egress_door"]["measures"]["moe_door_leaves"]["meaning"]
    for words in (meaning, " ".join(doors.__doc__.split())):
        assert "a pair with a mullion is two openings, each needing the 32 in" in words
        assert "narrower leaf's own opening" in words


def test_an_exit_kind_not_read_is_not_measured():
    d = _office()
    d["doors"][0]["exit_kind"] = "fire_escape"
    assert _why(_parts(d)["d"], "moe_door_exit").startswith("the door d gives its kind of exit as")


def test_sides_not_read_leave_the_side_facts_unmeasured():
    d = _office()
    d["doors"][0]["sides"] = ["r"]
    got = _parts(d)["d"]
    for m in ("moe_door_exterior", "moe_door_to_corridor", "moe_door_to_room_under_10_sf"):
        assert _why(got, m) == STOPS["door_sides_not_read"].format(name="d")


def test_a_side_that_is_no_room_read_leaves_what_it_would_settle_unmeasured():
    d = _office()
    d["unknown_spaces"] = [{"id": "q", "name": "Space 9", "level": "L1"}]
    d["doors"][0]["sides"] = ["q", "c"]
    got = _parts(d)["d"]
    assert got["measures"]["moe_door_to_corridor"] is True                     # one side is a corridor: settled
    assert _why(got, "moe_door_to_room_under_10_sf").startswith("a side of the door d is 'q', which is an enclosed")
    d["doors"][0]["sides"] = ["r", "nowhere"]
    got = _parts(d)["d"]
    assert _why(got, "moe_door_to_corridor").startswith("a side of the door d is 'nowhere', which is not a room given")


def test_a_room_with_no_use_may_be_a_corridor():
    d = _office()
    del d["rooms"][0]["use"]
    d["doors"][1]["sides"] = ["r", "outside"]
    d["doors"][1]["plan"]["centre"] = [-0.25, 7.5]
    got = _parts(d)
    assert _why(got["x"], "moe_door_to_corridor") == STOPS["door_side_no_use"].format(name="x", room="r")
    assert got["d"]["measures"]["moe_door_to_corridor"] is True                # its other side is the corridor


def test_a_room_under_10_sq_ft_and_a_room_not_read():
    d = _office()
    d["rooms"].append(room("k", rect(20.5, 0, 23.5, 3.25), use="closet"))     # 9.75 sq ft
    d["doors"].append(door("kd", (22, 3.5), (1, 0), ("k", "c")))
    got = _parts(d)
    assert got["kd"]["measures"]["moe_door_to_room_under_10_sf"] is True
    big = copy.deepcopy(d)
    big["rooms"][-1]["floor"] = [list(p) for p in rect(20.5, 0, 23.5, 3.34)]   # 10.02 sq ft
    big["doors"][-1]["plan"]["centre"] = [22, 3.59]
    assert _parts(big)["kd"]["measures"]["moe_door_to_room_under_10_sf"] is False
    d["rooms"][-1]["floor"] = "not an outline"
    assert _why(_parts(d)["kd"], "moe_door_to_room_under_10_sf") == STOPS["door_side_room_not_read"].format(
        name="kd", room="k")


def test_the_doors_not_read_no_parts():
    d = _office()
    del d["doors"]
    assert measure(d)["parts"]["means_of_egress_door"] is None
    assert door_parts({**_office(), "doors": "none"}, read(_office())) is None
    assert door_parts({**_office(), "units": "cubits"}, read(_office())) is None


def test_a_door_given_twice_or_without_an_id_is_its_own_part():
    d = _office()
    d["doors"].append(copy.deepcopy(d["doors"][0]))
    d["doors"].append({**copy.deepcopy(d["doors"][0]), "id": None})
    ids = [p["id"] for p in door_parts(d, read(_office()))]
    assert ids == ["d", "x", "door #3", "door #4"]


def test_sizes_in_inches_whatever_the_description_units():
    d = _office(stated_clear={"width": 34, "height": 80, "source": "maker"})
    d["units"] = "in"
    for r in d["rooms"]:
        r["floor"] = [[x * 12, y * 12] for x, y in r["floor"]]
    for x in d["doors"]:
        x["plan"] = {k: ([v[0] * 12, v[1] * 12] if k == "centre" else v * 12 if k in ("clear_width", "wall_thickness")
                         else v) for k, v in x["plan"].items()}
    d["doors"][0]["plan"]["clear_width"] = 34
    got = _parts(d)["d"]
    assert got["measures"]["moe_door_clear_width"] == pytest.approx(34)
    assert got["measures"]["moe_door_clear_height"] == pytest.approx(80)


def _drawn(width_in=34.0, height_in=80.0):
    """A side-hinged door drawn as the house reading measures it (feet, as the layouts): pin at the hinge-side
    corner, a 1 3/4 in leaf, its clear width latch stop less the open leaf's face, its height head stop less threshold."""
    ft = 1 / 12
    latch = width_in + 1.75
    return {"operation": "side_hinged", "hinge_side": "left", "stops": {"hinge": 0, "latch": latch * ft},
            "hinge_pin": [0, 1.75 * ft], "leaf_closed": [[0, 0], [latch * ft, 1.75 * ft]],
            "threshold_top": 0, "head_stop_bottom": height_in * ft}


def test_a_drawn_door_that_disagrees_with_its_stated_opening_leaves_that_size_unmeasured():
    """Review round 1 of section group 6a (P0): a door stated 34 by 84 in but drawn 70 in high was measured at 84 and
    passed 1010.1.1's 80 in. Every figure given for a size must agree with the maker's within 1/16 in, the drawn door
    as the house reading measures it (its stops, hinge pin and leaf; its threshold and head stop), else that size
    isn't measured; where they agree the smallest counts (round 2): never the larger, never a figure off the maker's."""
    tall = {**STATED, "height": 84 / 12}
    got = _parts(_office(stated_clear=tall, **_drawn(34, 70)))["d"]
    assert "moe_door_clear_height" not in got["measures"]
    assert _why(got, "moe_door_clear_height") == STOPS["door_clear_disagree"].format(
        name="d", where="drawing", size="height", other=70.0, stated=84.0)
    assert got["measures"]["moe_door_clear_width"] == pytest.approx(34)            # its drawn width agrees
    got = _parts(_office(stated_clear=dict(STATED), **_drawn(28.75, 80)))["d"]
    assert "moe_door_clear_width" not in got["measures"]
    assert _why(got, "moe_door_clear_width") == STOPS["door_clear_disagree"].format(
        name="d", where="drawing", size="width", other=28.75, stated=34.0)
    assert got["measures"]["moe_door_clear_height"] == pytest.approx(80)
    got = _parts(_office(stated_clear=dict(STATED), **_drawn(34 + 1 / 32, 80 - 1 / 32)))["d"]   # within 1/16 in
    assert got["measures"]["moe_door_clear_width"] == pytest.approx(34)                 # the smaller: the maker's
    # review round 2: within 1/16 in the smaller counts, never the maker's larger: 80 in stated, 79 31/32 drawn
    assert got["measures"]["moe_door_clear_height"] == pytest.approx(80 - 1 / 32) and got["measures"][
        "moe_door_clear_height"] < 80
    d = _office(stated_clear=dict(STATED))
    d["doors"][0]["plan"]["clear_width"] = (34 - 1 / 32) / 12                         # the plan's width, smaller
    assert _parts(d)["d"]["measures"]["moe_door_clear_width"] == pytest.approx(34 - 1 / 32)


def test_a_drawing_that_cant_be_measured_leaves_its_size_unmeasured():
    """A door drawn but not measurable from its drawing (a stop missing, a sliding door's stops, a head stop under
    the threshold) gets no size of that kind, even with a maker's figure: that figure could be more than the door."""
    bad = _drawn()
    del bad["stops"]["latch"]
    got = _parts(_office(stated_clear=dict(STATED), **bad))["d"]
    assert _why(got, "moe_door_clear_width").startswith("the door d's clear opening isn't read: ")
    assert got["measures"]["moe_door_clear_height"] == pytest.approx(80)
    sliding = {**_drawn(), "operation": "sliding"}
    assert "moe_door_clear_width" not in _parts(_office(stated_clear=dict(STATED), **sliding))["d"]["measures"]
    low = {"threshold_top": 1, "head_stop_bottom": 0}
    got = _parts(_office(stated_clear=dict(STATED), **low))["d"]
    assert _why(got, "moe_door_clear_height").startswith("the door d's clear opening isn't read: ")
    assert got["measures"]["moe_door_clear_width"] == pytest.approx(34)

