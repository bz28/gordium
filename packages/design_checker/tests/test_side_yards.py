"""Unequal side yards on the starting house (UX review 2026-10-27): where a district lets the two side yards differ
(R-2b, §325-8 Column 11: one side 5 ft, the other 10 ft), the starting house puts the larger on one side only, says
which side, and Switch side yards puts it on the other. The envelope and every check stay cautious and unchanged.

R-2b's rulebook is in another PR, so these tests use R-1b's real rulebook with R-2b's dimensional numbers put in
(side yards 5 and 10 ft, front yard 10 ft, coverage 35%, lot 35 ft wide and 3,000 sf): the same rule shapes the
generator and the checker read. Expected values are worked by hand from the lot (35 ft x 100 ft)."""

import copy
import json

import pytest

from design_checker import check, present
from design_checker import rhino_logic as logic
from envelope_builder.envelope import envelope
from envelope_builder.start import _frame, _tie_side, floor_solids
from model_measurement.places.ithaca_city.measure import Lot, measure
from rule_format.rulebook import REPO, rulebook_for
from host_source import host_text

ITHACA = "regulations/jurisdictions/new_york/ithaca_city"
R2B = {"R-1b.side_yards": "side_yard_smaller >= 5 and side_yard_larger >= 10",
       "R-1b.front_yard": "front_yard >= 10", "R-1b.lot_coverage": "building_area <= 0.35 * lot_area",
       "R-1b.lot_width_one_family_detached": "lot_width >= 35",
       "R-1b.lot_area_one_family_detached": "lot_area >= 3000",
       # R-2b's own eaves rule (R-2b.yaml, §325-18B), as the stack below this one added R-1b's (its yards less 2 ft)
       "R-1b.yard_projections": "front_yard_eaves >= 10 + max(building_height - 35, 0) - 2 and side_yard_smaller_eaves "
                                ">= 5 + max(building_height - 35, 0) - 2 and side_yard_larger_eaves >= 10 + "
                                "max(building_height - 35, 0) - 2 and rear_yard_eaves >= max(min(0.25 * lot_depth, 50), "
                                "20) + max(building_height - 35, 0) - 2"}
FACTS = {"jurisdiction": ITHACA, "zone": "R-1b", "use": "one_family_detached", "corner_lot": False,
         "lot_surveyed": True, "ground_is_flat": True, "grade_elevation": 0, "street_line": [[[0, 0], [35, 0]]]}


@pytest.fixture
def r2b(monkeypatch):
    """The checker reading R-1b with R-2b's numbers. check_site takes the rulebook from the report, which parses the
    very bytes its frozen certificate was checked against (project_report.report.load_bytes), so that read is
    changed too."""
    from project_report import report
    real, real_bytes = check.load, report.load_bytes

    def r2b_numbers(book):
        if isinstance(book, dict) and "rules" in book:
            book = copy.deepcopy(book)
            for r in book["rules"]:
                r["check"] = R2B.get(r["id"], r.get("check"))
        return book

    monkeypatch.setattr(check, "load", lambda path: r2b_numbers(real(path)))
    monkeypatch.setattr(report, "load_bytes", lambda data: r2b_numbers(real_bytes(data)))
    return check.load(rulebook_for(REPO / ITHACA, "R-1b"))["rules"]


def site(points):
    n = len(points)
    return {"units": "ft", "lot": {"id": "lot", "edges": [{"points": [list(points[i]), list(points[(i + 1) % n])]}
                                                          for i in range(n)]}, "buildings": [], "problems": []}


NARROW = [(0, 0), (35, 0), (35, 100), (0, 100)]          # 204 Utica St's width: 35 ft, the street along y = 0


def house(rules, facts=FACTS, points=NARROW, larger_side=None):
    s = site(points)
    out = check._kept_back_building(s, facts, measure(s, facts), rules, None, 0.0, larger_side)
    return s, out


def xs(out):
    ring = out["floors"][0]["outline"]
    return min(p[0] for p in ring), max(p[0] for p in ring)


def fails(s, out, facts):
    view = check.check_site({**s, "buildings": floor_solids(out["floors"])}, facts)["view"]
    return [i["id"] for i in view["items"] if i["status"] == present.FAILS], view


@pytest.mark.parametrize("surveyed", [True, False])
def test_the_narrow_lot_gets_one_larger_side_yard_on_the_left_and_both_ways_comply(r2b, surveyed):
    """35 ft lot: 35 - 10 - 5 = 20 ft wide on a survey (it was 35 - 2 x 10 = 15 ft before); on a tax-map lot every
    line is kept back as well (kept_back on each side). Facing the lot from the street (y = 0, the lot at +y),
    left is west (x = 0): the tie (a rectangle: both sides give the same house) goes left, not on a corner lot."""
    facts = {**FACTS, "lot_surveyed": surveyed}
    s, auto = house(r2b, facts)
    k = auto["kept_back"]
    assert (k == 0.0) if surveyed else (k >= 2.0)
    assert xs(auto) == pytest.approx((10 + k, 35 - 5 - k))                   # 10 ft on the left, 5 ft on the right
    assert auto["side_split"]["larger_side"] == "left" and not auto["side_split"]["asked"]
    assert "Side yards: 10'-0\" on the left (west), 5'-0\" on the right (east), seen from the street." \
        in auto["margin_note"]
    assert auto["margin_note"] in auto["notes"]
    assert fails(s, auto, facts)[0] == []
    _, switched = house(r2b, facts, larger_side="right")
    assert xs(switched) == pytest.approx((5 + switched["kept_back"], 35 - 10 - switched["kept_back"]))
    assert switched["side_split"]["larger_side"] == "right" and switched["side_split"]["asked"]
    assert "Side yards: 10'-0\" on the right (east), 5'-0\" on the left (west), seen from the street." \
        in switched["margin_note"]
    got, view = fails(s, switched, facts)
    assert got == []
    if surveyed:            # nothing about the house waits on anything but the architect's own facts
        sides = next(i for i in view["items"] if i["id"].startswith("R-1b.side_yards"))
        assert sides["status"] == present.COMPLIES


def test_the_envelope_stays_cautious(r2b):
    """The drawn envelope (and so the snap curves and the yard lines) keeps the larger side yard on both sides."""
    s = site(NARROW)
    env = envelope(s, FACTS, measure(s, FACTS), r2b)
    x = [p[0] for p in env["outline"]]
    assert min(x) == pytest.approx(10.001) and max(x) == pytest.approx(25 - 0.001)
    assert env["side_split"] == {"smaller": 5, "larger": 10} and env["yards"]["side"] == 10


def test_the_side_that_gives_the_larger_house_is_chosen(r2b):
    """A lot whose right side line slants out: a yard measured square to a slanted line costs more width, so the
    10 ft yard goes on the straight side. Mirrored, it goes on the other side: the larger house wins, not the left."""
    slanted = [(0, 0), (35, 0), (85, 100), (0, 100)]
    _, out = house(r2b, points=slanted)
    _, other = house(r2b, points=slanted, larger_side="right")
    assert out["side_split"]["larger_side"] == "left" and out["area"] > other["area"] + 1
    mirrored = [(0, 0), (35, 0), (35, 100), (-50, 100)]
    _, out = house(r2b, points=mirrored)
    _, other = house(r2b, points=mirrored, larger_side="left")
    assert out["side_split"]["larger_side"] == "right" and out["area"] > other["area"] + 1


def test_on_a_corner_lot_a_tie_puts_the_larger_yard_away_from_the_side_street():
    """The tie-break alone (the envelope doesn't draw corner lots yet, §325-19C): the side line on the second
    street gets the smaller yard."""
    s = site(NARROW)
    lot = Lot(s, FACTS)
    angle, origin = _frame(lot)
    front = [[0, 0], [35, 0]]
    assert _tie_side(lot, {"corner_lot": True, "street_line": [front, [[35, 0], [35, 100]]]}, angle, origin) == "left"
    assert _tie_side(lot, {"corner_lot": True, "street_line": [front, [[0, 100], [0, 0]]]}, angle, origin) == "right"
    assert _tie_side(lot, {"corner_lot": False, "street_line": [front, [[0, 100], [0, 0]]]}, angle, origin) == "left"


def test_a_side_yard_rule_with_two_ways_to_comply_is_never_split(r2b):
    """Review round 1, F1: with `(5 and 10) or (7 and 7)` the panel reads each side's comparison on its own (a 5 ft
    side would show as failing 7 ft), so the starting house keeps the cautious larger yard on both sides."""
    rules = [dict(r, check="(side_yard_smaller >= 5 and side_yard_larger >= 10) or "
                           "(side_yard_smaller >= 7 and side_yard_larger >= 7)") if r["id"] == "R-1b.side_yards" else r
             for r in r2b]
    s = site(NARROW)
    assert envelope(s, FACTS, measure(s, FACTS), rules)["side_split"] is None
    _, out = house(rules)
    assert out["side_split"] is None and "Side yards" not in out["margin_note"]


def test_equal_side_yards_are_unchanged():
    """R-1b (10 ft both sides): no split, no side words, the same house whichever side is asked for."""
    rules = check.load(rulebook_for(REPO / ITHACA, "R-1b"))["rules"]
    points = [(0, 0), (73, 0), (73, 90), (0, 90)]
    facts = {**FACTS, "street_line": [[[0, 0], [73, 0]]]}
    _, out = house(rules, facts, points)
    _, asked = house(rules, facts, points, larger_side="right")
    assert out["side_split"] is None and xs(out) == pytest.approx((10, 63)) and xs(asked) == xs(out)
    assert "Side yards" not in out["margin_note"] and not logic.can_switch("Starting house: " + out["margin_note"])


def test_a_split_house_that_would_break_a_rule_is_never_placed(r2b):
    """The checker's verdict saying the side yards fail for any house under 10 ft on a side: neither split house
    is placed; the larger yard goes on both sides, and the note says why. Asked for a side: the same."""
    s = site(NARROW)
    m = measure(s, FACTS)

    def strict(rule, measured, allowed):
        if rule["id"] == "R-1b.side_yards" and ((measured.get("side_yard_smaller") or {}).get("value") or 99) < 10 - 1e-6:
            return "fail"
        return check.verdict(rule, measured, allowed)

    from envelope_builder.start import largest_legal_building
    for asked in (None, "right"):
        out = largest_legal_building(s, FACTS, m, r2b, verdict=strict, larger_side=asked)
        assert out["floors"] and out["side_split"] is None
        assert xs(out) == pytest.approx((10, 25))
        assert any("would break R-1b.side_yards" in n for n in out["notes"])


def test_switch_plan_redraws_only_the_house_as_drawn():
    start = {"floors": [{"outline": [[10, 10], [30, 10], [30, 50], [10, 50]], "base": 0, "top": 11},
                        {"outline": [[10, 10], [30, 10], [30, 50], [10, 50]], "base": 11, "top": 22}],
             "side_split": {"larger_side": "left"}}
    tags = [logic.start_tag(start, i, 11.0, 0.0) for i in range(2)]
    boxes = [((10, 10, 0), (30, 50, 11)), ((10, 10, 11), (30, 50, 22))]
    volumes = [20 * 40 * 11.0] * 2
    assert logic.switch_plan(list(zip(tags, boxes, volumes))) == {"larger_side": "right", "floor_to_floor": 11.0,
                                                                  "design_buffer": 0.0}
    moved = [((11, 10, 0), (31, 50, 11)), boxes[1]]
    assert "changed" in logic.switch_plan(list(zip(tags, moved, volumes)))["refused"]
    notched = [volumes[0] - 2 * 2 * 11, volumes[1]]          # a corner notched out: the same box, a smaller solid
    assert "changed" in logic.switch_plan(list(zip(tags, boxes, notched)))["refused"]
    assert "changed" in logic.switch_plan(list(zip(tags, boxes, [None, None])))["refused"]   # not measurable
    chase = [volumes[0] - 1 * 1 * 10, volumes[1]]            # a 1 ft x 1 ft chase, 10 ft tall: still an edit
    assert "changed" in logic.switch_plan(list(zip(tags, boxes, chase)))["refused"]
    assert "locked or hidden" in logic.switch_plan([(t, b, v, i == 1) for i, (t, b, v) in
                                          enumerate(zip(tags, boxes, volumes))])["refused"]
    assert "missing" in logic.switch_plan([(tags[0], boxes[0], volumes[0])])["refused"]
    assert "no starting house" in logic.switch_plan([])["refused"]
    same = [logic.start_tag({**start, "side_split": None}, i, 11.0, 0.0) for i in range(2)]
    assert "same on both sides" in logic.switch_plan(list(zip(same, boxes, volumes)))["refused"]
    assert json.loads(tags[0])["larger_side"] == "left"
    assert logic.can_switch("Starting house: as first drawn, the largest … Side yards: 10'-0\" on the left (west), …")
    assert not logic.can_switch("Starting house: as first drawn, the largest house the rules allow; limited by …")


def test_switch_in_rhino_is_one_undo_step_and_draws_before_it_deletes():
    """The Rhino code (run in Rhino by apps/rhino_plugin/tests/side_yards_in_rhino.py): the panel's button under the
    Starting house fact, wired through the gated actions; the new house drawn inside one Undo record before the old
    one is deleted, and only when the checker gave a house with the larger yard on the side asked for."""
    rhino = host_text("rhino", "plugin", purpose="wiring")
    ui = host_text("rhino", "ui", purpose="wiring")
    assert '"switch_sides": switch_side_yards' in rhino
    assert 'if logic.can_switch(s):' in ui and 'button(logic.SWITCH_LABEL, a["switch_sides"])' in ui
    body = rhino[rhino.index("def switch_side_yards"):rhino.index("def _said_sides")]
    assert body.index('split.get("larger_side") != plan["larger_side"]') < body.index("doc.BeginUndoRecord(") \
        < body.index("add_floors(doc, start,") < body.index("if not doc.Objects.Delete(o, True)") \
        < body.index("doc.Objects.Undelete(o)") < body.index("doc.Objects.Delete(new, True, True)") \
        < body.index("doc.EndUndoRecord(record)")
    assert "o.IsReference" in rhino[rhino.index("def _start_floors"):rhino.index("def switch_side_yards")]
    assert "a.SetUserString(logic.START_KEY, logic.start_tag(start, i, floor_to_floor, design_buffer))" in rhino


def test_switch_side_yards_with_no_document_open_says_what_to_do():
    """Every file closed (Rhino.RhinoDoc.ActiveDoc is None): Switch side yards said nothing and crashed on the first
    use of the document. It says "Open a Rhino model first." and touches nothing, as every other command does (#51)."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    src = host_text("rhino", "plugin", purpose="wiring")
    said = []

    def touched(*args, **kwargs):
        raise AssertionError("the plugin touched the model or the checker with no document open")
    ns = {"Rhino": SimpleNamespace(RhinoDoc=SimpleNamespace(ActiveDoc=None),
                                   RhinoApp=SimpleNamespace(WriteLine=said.append)),
          "logic": logic, "STATE": {}, "ui": MagicMock(), "_start_floors": touched, "ask": touched,
          "current_facts": touched, "export": touched}
    for name in ("say", "switch_side_yards"):
        exec(src[src.index("def %s(" % name):].split("\ndef ", 1)[0], ns)      # noqa: S102
    assert ns["switch_side_yards"]() is None
    assert said == ["Gordium: " + logic.NO_DOCUMENT]
