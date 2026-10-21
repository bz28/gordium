"""Ben's one-floor-moved cases on the sample lot, and a building that crosses a lot line (review round 4).

The starting house on 106 Ithaca Rd's 73 x 90 lot (from the tax map) sits 12 ft from each side line and 27 ft from
the street, 3 floor blocks. Moving any one floor block 5 ft east puts it 12 − 5 = 7 ft from the east line (10 ft
required): the side yard does not comply, whichever floor it is. Moving only the top floor 4 ft toward the street
puts it 27 − 4 = 23 ft back (25 required): the front yard does not comply."""

import sys

import pytest

from design_checker import present
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "packages/design_checker/tests"))
from test_every_reading import floors, prism, rect, rows, run, status  # noqa: E402
from test_quickstart import _check, _moved, house  # noqa: E402,F401  (house: the module fixture)


@pytest.mark.parametrize("which", [0, 1, 2])
def test_one_floor_moved_5_ft_east_does_not_comply_on_the_east_side(house, which):
    got, facts = house
    items = _check(_moved(got["floors"], dx=5, which=which), facts)
    east = items["Side yard, East"]
    assert (east["status"], east["proposed"]) == (present.FAILS, "7'-0\"")


def test_only_the_top_floor_moved_4_ft_toward_the_street_does_not_comply_in_front(house):
    got, facts = house
    front = _check(_moved(got["floors"], dy=-4, which=2), facts)["Front yard"]
    assert (front["status"], front["proposed"]) == (present.FAILS, "23'-0\"")


def test_the_eaves_rule_names_the_yard_it_fails_in(house):
    """Review round 4 (found running the floor cases): the house moved 5 ft east fails the eaves rule on the east
    side (7 < 10 − 2), so its row says the side yard and 7'-0", never 'Eaves into front yard 27'-0"'."""
    got, facts = house
    items = _check(_moved(got["floors"], dx=5), facts, grade_is="finished")   # the height known (the bonus term)
    eaves =[i for n, i in items.items() if n.startswith("Eaves into")]
    assert len(eaves) == 1 and eaves[0]["status"] == present.FAILS
    assert (eaves[0]["name"], eaves[0]["proposed"]) == ("Eaves into side yard", "7'-0\"")


def test_a_building_crossing_the_side_lot_line_does_not_comply_and_says_so():
    """The house 50..65 on a 60 ft wide lot: it crosses the east lot line. The side yard there is 0: does not
    comply, 'crosses the lot line', never needs review or a pass."""
    res = run(floors(50, 30, 65, 70, 2))
    side = rows(res, "R-1b.side_yards")
    assert status(res, "R-1b.side_yards") == present.FAILS
    assert all(i["status"] == present.FAILS and "The main building is not entirely on the lot (it crosses the side lot line)" in (i["reason"] or "")
               for i in side)                       # both side rows: the building is on the neighbour's land
    assert not any(i["status"] == present.COMPLIES for r in ("R-1b.side_yards", "R-1b.yard_projections")
                   for i in rows(res, r) if "crosses" in (i["reason"] or ""))


def test_a_building_crossing_the_street_line_does_not_comply_in_front():
    res = run(floors(15, -5, 45, 30, 2))
    front = rows(res, "R-1b.front_yard")[0]
    assert front["status"] == present.FAILS and "crosses the street lot line" in front["reason"]


def test_a_building_wholly_off_the_lot_still_waits():
    """Wholly outside (no part on the lot): it can't be measured against the lot: needs review, as before."""
    res = run([prism(rect(70, 30, 90, 70), 0, 20, "house")])
    assert status(res, "R-1b.front_yard") == present.REVIEW


# ---- verification round (4d0a2e6): each building is placed on the lot on its own ------------------------------

def test_a_house_wholly_off_the_lot_never_complies_because_a_shed_is_on_it():
    """Case A (a false pass on 4d0a2e6: every row complied). The house past the rear line (y 150..190 on a 120 ft
    deep lot), a listed frame shed on the lot: the house can't be measured against the lot, so no yard complies."""
    res = run(floors(15, 150, 45, 190, 2) + [prism(rect(20, 90, 30, 100), 0, 10, "shed")],
              accessory_buildings=["shed"], accessory_frame=True, stories=2)
    for rule in ("R-1b.front_yard", "R-1b.side_yards", "R-1b.rear_yard"):
        assert status(res, rule) != present.COMPLIES, rule


def test_a_shed_wholly_off_the_lot_never_complies_because_the_house_is_on_it():
    """Case B: the house on the lot, a listed shed off it (x 70..80 on a 60 ft wide lot): the accessory rule
    never complies."""
    res = run(floors(15, 30, 45, 70, 2) + [prism(rect(70, 90, 80, 100), 0, 10, "shed")],
              accessory_buildings=["shed"], accessory_frame=True)
    assert status(res, "R-1b.accessory_buildings") != present.COMPLIES


def test_only_the_line_actually_crossed_says_crosses():
    """A building 50..65 x 0..70: its front face lies exactly on the street line (inside the lot), and it crosses
    the east line. Every main-yard row fails, naming the line actually crossed (the side), never the street."""
    res = run(floors(50, 0, 65, 70, 2))
    front = rows(res, "R-1b.front_yard")[0]
    assert front["status"] == present.FAILS and "street lot line" not in (front["reason"] or "")
    assert any("crosses the side lot line" in (i["reason"] or "") for i in rows(res, "R-1b.side_yards"))


# ---- verification round 2 (bd86179): crossing a lot line is a fact about each building ------------------------

def test_a_shed_across_the_side_line_fails_the_accessory_rule_even_under_the_front_yard_only_answer(monkeypatch):
    """Reviewer's case: a listed shed across the east line, and the §325-25C question answered
    front_yard_rule_only (no side or rear distances for a building that isn't frame). It is partly on the
    neighbour's land: no reading or answer clears it. The row names the shed and the line, and shows the
    crossing, not the passing front distance."""
    import copy

    from model_measurement import interpretations
    real = interpretations.research_entries

    def answered(jurisdiction):
        entries = copy.deepcopy(real(jurisdiction))
        for where, e in entries:
            if where.endswith(" 325-25C"):
                e["answers"] = [{"question": e["open_questions"][0], "answer": "Only the front yard rule.",
                                 "reading": "front_yard_rule_only", "answered_by": "the City zoning office",
                                 "answered_on": "2026-11-01"}]
        return entries
    monkeypatch.setattr(interpretations, "research_entries", answered)
    interpretations.clear_cache()
    try:
        res = run(floors(15, 30, 45, 70, 2) + [prism(rect(52, 90, 64, 100), 0, 10, "shed")],
                  accessory_buildings=["shed"], accessory_frame=False)
        acc = rows(res, "R-1b.accessory_buildings")[0]
        assert acc["status"] == present.FAILS
        assert 'accessory building "shed" is not entirely on the lot (it crosses the side lot line)' in acc["reason"].lower()
        assert acc["proposed"] == "partly off the lot"
    finally:
        monkeypatch.undo()
        interpretations.clear_cache()


def test_a_shed_across_the_rear_line_leaves_the_houses_rear_yard_unmarked():
    """The shed crosses the rear line; the house is 10 ft from it (30 required): the house's rear yard does not
    comply on its own distance, never 'crosses'; coverage fails for the shed."""
    res = run(floors(15, 30, 45, 110, 2) + [prism(rect(20, 112, 30, 125), 0, 10, "shed")],
              accessory_buildings=["shed"], accessory_frame=True)
    rear = rows(res, "R-1b.rear_yard")[0]
    assert rear["status"] == present.FAILS and "crosses" not in (rear["reason"] or "")
    assert status(res, "R-1b.accessory_buildings") == present.FAILS
    assert 'accessory building "shed" is not entirely on the lot (it crosses the rear lot line)' in rows(res, "R-1b.lot_coverage")[0]["reason"].lower()


def test_a_house_across_the_side_line_leaves_the_accessory_rows_unmarked():
    res = run(floors(50, 30, 65, 70, 2) + [prism(rect(10, 90, 20, 100), 0, 10, "shed")],
              accessory_buildings=["shed"], accessory_frame=True)
    acc = rows(res, "R-1b.accessory_buildings")[0]
    assert "crosses" not in (acc["reason"] or "") and acc["status"] == present.COMPLIES
    assert status(res, "R-1b.side_yards") == present.FAILS


# ---- round 7: one rule for each building on its own --------------------------------------------------------------

def _front_yard_only(monkeypatch):
    import copy

    from model_measurement import interpretations
    real = interpretations.research_entries

    def answered(jurisdiction):
        entries = copy.deepcopy(real(jurisdiction))
        for where, e in entries:
            if where.endswith(" 325-25C"):
                e["answers"] = [{"question": e["open_questions"][0], "answer": "Only the front yard rule.",
                                 "reading": "front_yard_rule_only", "answered_by": "the City zoning office",
                                 "answered_on": "2026-11-01"}]
        return entries
    monkeypatch.setattr(interpretations, "research_entries", answered)
    interpretations.clear_cache()
    return interpretations


CORNER_SHED = prism(rect(-0.015, 110, 8, 120.015), 0, 9, "shed")      # its corner 0.015 ft past the lot corner


@pytest.mark.parametrize("with_house_across", [True, False])
def test_a_shed_poking_past_a_lot_corner_never_complies_whatever_the_house_does(monkeypatch, with_house_across):
    """Round 7, P0: a shed whose corner pokes 0.015 ft past the lot corner (0, 120), §325-25C answered
    front_yard_rule_only. Partly off the lot: its rule does not comply, alone or beside a house that itself
    crosses the east line (the same answer either way: one building never changes another's)."""
    interpretations = _front_yard_only(monkeypatch)
    try:
        house = floors(50, 30, 65, 70, 2) if with_house_across else floors(15, 30, 45, 70, 2)
        res = run(house + [CORNER_SHED], accessory_buildings=["shed"], accessory_frame=False)
        acc = rows(res, "R-1b.accessory_buildings")[0]
        assert acc["status"] == present.FAILS
        assert 'accessory building "shed" is not entirely on the lot' in acc["reason"].lower()
    finally:
        monkeypatch.undo()
        interpretations.clear_cache()


def test_a_crossing_whose_line_cant_be_named_says_the_lot_line_never_lot_lot_line():
    """Round 7, P2: the house crossing the east line on a lot whose corner status isn't stated (so no side or rear
    line can be named): 'it reaches past the lot line', never 'the lot lot line'."""
    res = run(floors(50, 30, 65, 70, 2), corner_lot=None)
    reasons = " ".join(i["reason"] or "" for i in res["view"]["items"])
    assert "lot lot line" not in reasons
    assert "The main building is not entirely on the lot (it reaches past the lot line)" in \
        rows(res, "R-1b.lot_coverage")[0]["reason"]


def test_a_rule_failing_for_a_crossing_counts_once():
    """Round 7, P3: a crossing rule that would comply under every reading is counted as a fail only."""
    res = run(floors(15, 30, 45, 70, 2) + [prism(rect(52, 90, 64, 100), 0, 10, "shed")],
              accessory_buildings=["shed"], accessory_frame=True)
    s = res["summary"]["text"]
    passes = int(s.split(" pass")[0]) if " pass" in s else 0
    assert passes == sum(1 for r in res["rows"] if not r["Fails"] and r["Error"] == "PASS" or
                         not r["Fails"] and (r.get("Named") or {}).get("result") == "pass")


def test_the_stories_rule_fails_too_for_a_main_building_partly_off_the_lot():
    res = run(floors(50, 30, 65, 70, 2))
    assert status(res, "R-1b.stories") == present.FAILS


FIVE_SIDED = [(0, 0), (60, 0), (60, 110), (30, 125), (0, 110)]     # scenario 09's lot: the back two short lines


def test_the_five_sided_lots_short_back_line_is_also_read_as_part_of_a_side_line():
    """Eval-integrity audit P1-2 (a false pass on a831e38: complies). Scenario 09's house moved 4 ft back
    (15..45 x 34..84). Read as the rear lot line, the two short back lines give depth (110 + 110) / 2 = 110,
    27'-6" required, and the house is 29.96 ft away: complies. Read with the east short line part of the east
    side line, depth (110 + 143.54) / 2 = 126.77 ft, 31'-8 5/16" required, and the house is still 29.96 ft from
    the west short line: fails. Every reading is evaluated: never complies."""
    res = run(floors(15, 34, 45, 84, 2), lot=FIVE_SIDED)
    depth = res["measurements"]["lot_depth"]
    assert sorted({round(r["value"], 2) for r in depth["readings"]}) == [110.0, 126.77]
    assert status(res, "R-1b.rear_yard") != present.COMPLIES
