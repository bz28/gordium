"""Reading "no sleeping lofts" on the Orangetown house (its Revit recording) is counted, not timed: a count is the
same on every machine and under any load. room_within asks each room's ceiling (_top) once, however many rooms stand
over it, and _top unions the pieces under a height once for every piece starting there. Main made 3,345 unary_union
calls and 30 _top calls here (about 12 s of CPU on Ben's laptop, about 70 s inside Revit's check); this makes 11 and
3 (well under a second). The bounds sit far between, so a speed-up taken out fails here. The answers are the same
to the byte (proved on every interior test house, the recordings and Orangetown when it was made)."""
import json

from model_measurement.interior import has_none
from rule_format.rulebook import REPO

RECORDING = REPO / "test_data/interior_houses/recorded/revit/orangetown_ny_80_south_william.json"


def _counted(monkeypatch):
    counts = {"unary_union": 0, "_top": 0}

    def counted(f, key):
        def call(*a, **k):
            counts[key] += 1
            return f(*a, **k)
        return call

    monkeypatch.setattr(has_none, "unary_union", counted(has_none.unary_union, "unary_union"))
    monkeypatch.setattr(has_none, "_top", counted(has_none._top, "_top"))
    return counts


def test_orangetowns_no_sleeping_lofts_is_read_with_a_hundredth_of_the_unions(monkeypatch):
    interior = json.loads(RECORDING.read_text(encoding="utf-8"))["interior"]
    counts = _counted(monkeypatch)
    assert has_none.room_within(interior) is None            # no room within another's height: the claim stands
    assert counts["unary_union"] <= 100, counts               # main: 3,345; now 11
    assert counts["_top"] <= 6, counts                        # main: 30 (one per pair of rooms); now 3 (one per room)


def _piece(x0, y0, x1, y1, z):
    return [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]


def test_pieces_starting_at_one_height_share_one_union_and_each_is_judged_on_its_own():
    # two low pieces covering 0-10; over them, two starting at 12 (one union of the low pieces serves both): one
    # wholly over them (hidden) and one reaching past them (not hidden: its 14 counts); and one at 20, hidden too
    low = [_piece(0, 0, 5, 10, 8), _piece(5, 0, 10, 10, 9)]
    over = _piece(1, 1, 9, 9, 12)
    high = _piece(2, 2, 4, 4, 20)
    past = [[8, 0, 12], [12, 0, 12], [12, 10, 14], [8, 10, 12]]          # reaches past the low pieces: its 14 counts
    assert has_none._top({"ceilings": low + [over, past, high]}, 0.0) == 14
    inside = [[8, 0, 12], [10, 0, 12], [10, 10, 14], [8, 10, 12]]        # now wholly over them too
    assert has_none._top({"ceilings": low + [over, inside, high]}, 0.0) == 9    # the low pieces' ceiling: 9


def test_the_union_is_made_once_per_height(monkeypatch):
    room = {"ceilings": [_piece(0, 0, 10, 10, 8)] + [_piece(i, 0, i + 1, 1, 12) for i in range(10)]}
    counts = _counted(monkeypatch)
    assert has_none._top(room, 0.0) == 8                      # every piece at 12 is over the one at 8
    assert counts["unary_union"] == 1, counts                 # main: one per piece, 10
