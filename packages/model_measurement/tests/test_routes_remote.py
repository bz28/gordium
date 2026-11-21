"""Decision 3 (routes/remote.py): the story's travel figure, on the route note's tests
(docs/decisions/2026-11-20_route_measurement.md). Every figure is a literal from the note, or worked by hand in the
comment beside it; none is taken from the code under test. Tolerance 1e-3 ft. Plus a brute force written here: the
same routes on a 6-in grid of clear points, by the slow exact route (`route`), against the sampled figure."""

import math
import sys
from pathlib import Path

import pytest

from model_measurement.routes import remote
from model_measurement.routes.remote import droppable, farthest, own_h
from model_measurement.routes.stops import Stop

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import (FT, at, column_room, description, door, l_corridor, rect, room,  # noqa: E402
                            room_on_corridor, routes, table_room)

TOL = 1e-3


def ft(x):
    return x / FT


def corridor_two_exits():
    """Test 19: a corridor 0 to 40 by 0 to 6, exit doors centred at (-0.25, 3) and (40.25, 3)."""
    return description([room("c", rect(0, 0, 40, 6))],
                       [door("a", (-0.25, 3), (0, 1), ("c", "outside"), exit_id="A"),
                        door("b", (40.25, 3), (0, 1), ("c", "outside"), exit_id="B")])


def niche():
    """Test 18: a room 0 to 20 by 0 to 10, its exit centred at (-0.25, 5), a niche 20 in wide, 2 ft deep."""
    w = 10 / 12
    return description([room("r", [(0, 0), (20, 0), (20, 10), (10 + w, 10), (10 + w, 12), (10 - w, 12),
                                   (10 - w, 10), (0, 10)], use="day_care")],
                       [door("x", (-0.25, 5), (0, 1), ("r", "outside"), exit_id="A")])


def stub():
    """A wall stub 6 in thick reaching 4 ft into a room 0 to 20 by 0 to 10 from its north wall (x 9.75 to 10.25):
    its two end corners are 6 in apart, so their rings make one cluster, whose margin is the walk out sampled."""
    return description([room("r", [(0, 0), (20, 0), (20, 10), (10.25, 10), (10.25, 6), (9.75, 6), (9.75, 10),
                                   (0, 10)], use="day_care")],
                       [door("x", (-0.25, 5), (0, 1), ("r", "outside"), exit_id="A")])


def cluster_at(got, x, y):
    return next(c for c in got.clusters if any(math.dist(r, at(x, y)) < 1e-6 for r in c.rings))


# --- test 1: the corner cluster, and the story's figure --------------------------------------------------------------

def test_1_the_story_figure_is_the_clear_floors_and_the_corner_cluster_is_far_below():
    got = farthest(routes(l_corridor()))
    assert ft(got.greatest) == pytest.approx(60.393, abs=TOL) and got.at == at(40, 30)
    assert 60.393 - TOL <= ft(got.figure) <= 60.643 + TOL and got.part == "the clear floor"
    corner = cluster_at(got, 34, 6)
    assert ft(corner.edge_greatest) == pytest.approx(37.450, abs=TOL)       # at (34, 7): the note's test 1
    assert corner.edge_at == pytest.approx(at(34, 7), abs=1e-6)
    assert corner.how == "lone ring in sight of its corner" and ft(corner.margin) == pytest.approx(1.0, abs=1e-9)
    assert ft(corner.bound) == pytest.approx(38.575, abs=TOL)               # 37.450 + 1.5 in + 12 in


def test_1_the_clear_points_next_to_the_rings_are_bounded_through_the_edge():
    """The triangles a ring reaches are kept, and their clear points bounded by the greatest edge sample plus
    3 in + 1.5 in: 37.450 + 0.375 = 37.825."""
    got = farthest(routes(l_corridor()))
    assert ft(got.near_rings_bound) == pytest.approx(37.825, abs=TOL)


# --- test 2, test 19: the greatest isn't at a corner --------------------------------------------------------------

def test_2_the_sampling_finds_the_far_walls_middle_behind_the_column():
    got = farthest(routes(column_room()))
    assert ft(got.greatest) == pytest.approx(30.931, abs=TOL) and got.at == pytest.approx(at(30, 5), abs=1e-6)
    assert 30.931 - TOL <= ft(got.figure) <= 30.931 + 0.25 + TOL


def test_19_the_drop_test_takes_the_triangles_own_h():
    tri = [at(19, 0), at(21, 0), at(19, 1.5)]
    assert ft(own_h(tri)) == pytest.approx(1.25, abs=1e-9)                 # the hypotenuse's middle (20, 0.75)
    values = [19.482 * FT, 19.482 * FT, 19.308 * FT]
    assert not droppable(tri, values, 19.75 * FT)                            # 19.482 + 1.25 = 20.732 > 19.75: kept
    assert droppable(tri, values, 20.8 * FT)


def test_19_the_story_figure_reaches_the_ridge_between_two_exits():
    got = farthest(routes(corridor_two_exits()))
    assert ft(got.greatest) == pytest.approx(20.471, abs=TOL)               # sqrt(20.25^2 + 3^2), at (20, 0)/(20, 6)
    assert 20.471 - TOL <= ft(got.figure) <= 20.471 + 0.25 + TOL


def test_own_h_of_a_triangle():
    # an equilateral triangle of side 3: its circumcentre, 3 / sqrt(3) = 1.7321 from each corner; an obtuse one
    # (0, 0), (4, 0), (2, 1): the point on its long side where the short sides' bisectors meet it, (1.25, 0) and
    # (2.75, 0), 1.25 from the nearer corners
    assert own_h([(0, 0), (3, 0), (1.5, 1.5 * math.sqrt(3))]) == pytest.approx(math.sqrt(3), abs=1e-9)
    assert own_h([(0, 0), (4, 0), (2, 1)]) == pytest.approx(1.25, abs=1e-9)


# --- the clusters ------------------------------------------------------------------------------------------------

def test_a_cluster_of_two_rings_has_its_walk_out_sampled():
    """The stub's end corners (9.75, 6) and (10.25, 6): the farthest walk out of their rings' union is from either
    corner, 1 ft (straight away from the other, to its ring's edge: then 1.5 ft from the other corner). The margin is
    that sampled walk (to edge samples at most 3 in apart: at most 1.5 in more) plus 3 in."""
    got = farthest(routes(stub()))
    pair = cluster_at(got, 9.75, 6)
    assert len(pair.rings) == 2 and pair.how == "walk out sampled"
    assert 1.0 + 0.25 - TOL <= ft(pair.margin) <= 1.0 + 0.125 + 0.25 + TOL
    assert pair.bound == pytest.approx(pair.edge_greatest + 1.5 + pair.margin, abs=1e-9)


def test_18_a_niche_under_24_in_makes_the_story_need_review():
    with pytest.raises(Stop) as stop:
        farthest(routes(niche()))
    assert stop.value.key == "too_narrow"
    assert "an opening too narrow for NFPA 7.6.1's 12-in clearance from both sides" in stop.value.reason


def test_a_cluster_with_no_clear_edge_needs_review(monkeypatch):
    """A guard (the clear arcs are found exactly, so a cluster on the floor always has some, or its pocket's arcs
    stop first): made to happen by giving no arcs."""
    monkeypatch.setattr(remote, "_clear_arcs", lambda floor, rings, r, walls: [])
    with pytest.raises(Stop) as stop:
        farthest(routes(l_corridor()))
    assert stop.value.key == "cluster_shut"


def test_a_point_with_no_walk_out_needs_review(monkeypatch):
    monkeypatch.setattr(remote._Walk, "__call__", lambda self, p: math.inf)
    with pytest.raises(Stop) as stop:
        farthest(routes(stub()))
    assert stop.value.key == "walk_shut"


# --- the brute force -------------------------------------------------------------------------------------------

def _clear_grid(desc, step):
    got = routes(desc)
    s = got.story
    out = []
    for room_ in s.rooms.values():
        x0, y0, x1, y1 = room_.outline.bounds
        nx, ny = int((x1 - x0) / step), int((y1 - y0) / step)
        for i in range(nx + 1):
            for j in range(ny + 1):
                p = (x0 + i * step, y0 + j * step)
                try:
                    out.append((got.route(p).length, got.travel(p), p))
                except Stop as e:
                    assert e.key in ("inside_ring", "not_on_floor"), e.reason
    return got, out


@pytest.mark.parametrize("layout", [l_corridor, column_room, table_room, corridor_two_exits])
def test_the_sampled_figure_is_above_every_point_of_a_grid_and_close_to_it(layout):
    got, grid = _clear_grid(layout(), 6.0)
    assert grid
    for slow, fast, p in grid:                                            # the fast length is the exact route's
        assert fast == pytest.approx(slow, abs=1e-6), p
    top = max(slow for slow, _, _ in grid)
    figure = farthest(got).figure
    assert top <= figure + 1e-6 and figure - top <= 0.5 * FT
