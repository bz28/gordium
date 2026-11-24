"""A story's route work is shared between its farthest() runs (the story's, each room's, the occupied rooms'), and
only within one measure() call: what is remembered (each point's travel, each point's first legs to the door
centres, each room's floor and rings, each cluster's walk out) is kept on the story's own StoryRoutes, made afresh
by every measure() call, so two buildings checked one after the other in the long-running worker each get their
own answer, even with the same room and door ids."""

import copy
import sys
from pathlib import Path

from model_measurement.routes import measure
from model_measurement.routes import paths

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import rect, room_on_corridor  # noqa: E402
from test_routes_not_occupied import layout  # noqa: E402


def _bigger(desc):
    """The same rooms and doors by id, the room 10 ft deeper (every route in it longer)."""
    d = copy.deepcopy(desc)
    r = next(x for x in d["rooms"] if x["id"] == "r")
    r["floor"] = [list(p) for p in rect(0, -10, 20, 15)]
    return d


def test_two_buildings_back_to_back_each_get_their_own_answer():
    a, b, c = room_on_corridor(), _bigger(room_on_corridor()), layout(marked=True)
    first = {"a": measure(a), "b": measure(b), "c": measure(c)}
    assert first["a"] != first["b"]                       # the same ids, different answers
    again = {"c": measure(c), "b": measure(b), "a": measure(a)}       # the other order: nothing carried over
    assert again == first
    for k, d in (("a", a), ("b", b), ("c", c)):           # and each alone, after the others
        assert measure(copy.deepcopy(d)) == first[k]


def test_what_is_remembered_lives_on_the_storys_routes_only(monkeypatch):
    made = []
    init = paths.StoryRoutes.__init__

    def spy(self, *a, **k):
        init(self, *a, **k)
        made.append(self)

    monkeypatch.setattr(paths.StoryRoutes, "__init__", spy)
    measure(layout(marked=True))
    first = [r for r in made if r._travels]
    assert first, "the story's travel samples are remembered on its StoryRoutes"
    made.clear()
    measure(layout(marked=True))
    assert made and all(r not in first for r in made)     # a new measure() call: new StoryRoutes, new memos
    assert all(not r._travels or r._travels is not s._travels for r in made for s in first)


def test_the_four_unit_apartments_route_measures_share_their_work(monkeypatch):
    """The four-unit apartment's route measures (test_data/test_sites/new_york/ithaca_city/four_unit_apartment),
    counted, not timed: the `_along` calls placing meetings on the routes' pieces (main 434,948: every candidate
    placed on both pieces, every pair of pieces whose boxes touch; now 109,120: a candidate off one piece never
    placed on the other, each piece's own ends placed once, pairs whose reach is apart skipped) and the clear-line
    tests of the first legs (`_Leg.clear_to`: main 24,756, every exit's routes from a point asking the same door
    centres again; now 18,946). The bounds sit between, so a sharing taken out fails here."""
    from model_measurement.routes import common_path, paths
    from rule_format.rulebook import REPO
    sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
    import make_ny_build_data as build
    interior = build.interior_of()
    counts = {"along": 0, "clear_to": 0}

    def counted(f, key):
        def call(*a, **k):
            counts[key] += 1
            return f(*a, **k)
        return call

    monkeypatch.setattr(common_path, "_along", counted(common_path._along, "along"))
    monkeypatch.setattr(paths._Leg, "clear_to", counted(paths._Leg.clear_to, "clear_to"))
    got = measure(interior)
    assert [s["id"] for s in got["parts"]["story"]] == ["L1", "L2"]
    assert counts["along"] <= 200_000, counts             # main: 434,948; now 109,120
    assert counts["clear_to"] <= 21_500, counts           # main: 24,756; now 18,946
