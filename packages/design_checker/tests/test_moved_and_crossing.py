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


def test_the_eaves_rows_show_their_base_requirement_while_the_height_waits_for_finished_grade(house):
    """Seen on a demo: the sample starting house with the ground as it is (No regrading not ticked, grade
    existing). The eaves rule's limits grow with the §325-16C height bonus, and the height can't be measured, so
    Required showed '—'. It shows the base requirement (front 25 − 2 = 23'-0"), says it may be more, and never
    complies."""
    got, facts = house
    assert facts["grade_is"] == "existing"
    eaves = [i for n, i in _check(got["floors"], facts).items() if n.startswith("Eaves into")]
    assert eaves and all(i["status"] != present.COMPLIES for i in eaves)
    front = next(i for i in eaves if i["name"] == "Eaves into front yard")
    assert front["required"] == "≥ 23'-0\""
    # the detail says the same: the base before the bonus, never a formula with the height unknown (round 9)
    assert "23'-0\"" in front["detail"]["line"] and "—" not in front["detail"]["line"].split("proposed")[1]
    assert "before the §325-16C height bonus" in front["detail"]["calc"] and "—" not in front["detail"]["calc"]
    # round 10, P3: the calc keeps the sign, and says why the bonus waits as it is here: the ground as it is was
    # measured, but the law measures the height from finished grade (not "the height isn't measured")
    assert front["detail"]["calc"].startswith("Required: ≥ 23'-0\" before the §325-16C height bonus")
    for text in (front["reason"], front["detail"]["calc"]):
        assert "measured from existing grade only; the bonus needs it from finished grade" in text, text
        assert "isn't measured yet" not in text, text


def test_the_eaves_rows_say_the_height_isnt_measured_when_there_is_no_ground(house):
    """Round 10, P3: finished grade ticked but no ground given: the height isn't measured at all, and the eaves
    rows say that (with the base ≥ 23'-0" before the bonus), never 'existing grade'."""
    got, facts = house
    items = _check(got["floors"], facts, grade_is="finished", grade_elevation=None, grade_points=None)
    front = items["Eaves into front yard"]
    assert front["status"] != present.COMPLIES and front["required"] == "≥ 23'-0\""
    assert front["detail"]["calc"] == "Required: ≥ 23'-0\" before the §325-16C height bonus (the height isn't measured yet)"
    assert "existing grade" not in front["reason"] and "the height isn't measured yet" in front["reason"]


GABLE = (15, 26, 45, 66)        # 30 x 40 ft, 26 ft from the street; 3 floors of 10 ft, then the roof


def _gable_with_overhang(**facts):
    """Three 10 ft floor blocks and a gable roof solid on them (base 30, ridge 45), its soffit 2 ft past the side
    walls with a 1 ft fascia. The height's readings, midway between eave and ridge: (30 + 45) / 2 = 37.5 (lowest
    eave, or wall plate), (31 + 45) / 2 = 38.0 (the drip edge, the top of the fascia), and 38.82 (the roof edge
    read with the overhang left out: the slope at the walls, 32.65, (32.65 + 45) / 2)."""
    from test_every_reading import roof
    return rows(run(floors(*GABLE, 3) + [roof(*GABLE, 30, 45, 2.0, 1.0)], **facts), "R-1b.yard_projections")


def test_the_eaves_rows_show_the_requirement_at_each_height_reading_when_they_disagree():
    """Round 11, P3: the height IS measured, but its readings disagree (37'-6" to 38'-9 7/8"): over 35 ft, so the
    bonus certainly applies, and '≥ 23'-0" before the bonus' understated it. The front eaves requirement at each
    reading, 25 + (h − 35) − 2: 25.5 (25'-6") to 26.82 (26'-10" rounded the strict way); the front eaves are at
    26'-0", inside that span: needs review, saying the readings disagree, never 'isn't measured'."""
    front = next(r for r in _gable_with_overhang() if r["name"] == "Eaves into front yard")
    assert front["status"] == present.REVIEW and front["proposed"] == "26'-0\""
    assert front["required"] == "≥ 25'-6\" to 26'-10\""
    for text in (front["reason"], front["detail"]["calc"], front["detail"]["line"]):
        assert "37'-6\" to 38'-9 7/8\"" in text and "isn't measured" not in text and "before the" not in text, text
    assert "at each reading of the height" in front["detail"]["calc"]


def test_the_eaves_rows_on_existing_grade_say_so_only_when_the_ground_as_it_is_was_measured():
    """Round 11, P3: existing grade with the ground given: the height was measured on it (its readings disagree
    there too, so no one value): 'measured from existing grade only'. Existing grade with no ground at all: nothing
    was measured: 'isn't measured yet'. Both show the base ≥ 23'-0" before the bonus (the legal height is unknown)."""
    measured = next(r for r in _gable_with_overhang(grade_is="existing") if r["name"] == "Eaves into front yard")
    nothing = next(r for r in _gable_with_overhang(grade_is="existing", grade_elevation=None, ground_is_flat=None)
                   if r["name"] == "Eaves into front yard")
    for row in (measured, nothing):
        assert row["status"] == present.REVIEW and row["required"] == "≥ 23'-0\""
    assert "measured from existing grade only; the bonus needs it from finished grade" in measured["detail"]["calc"]
    assert nothing["detail"]["calc"] == "Required: ≥ 23'-0\" before the §325-16C height bonus (the height isn't measured yet)"
    assert "the height isn't measured yet" in nothing["reason"] and "existing grade only" not in nothing["reason"]


# ---- review round 8: every lot-line reading the geometry allows ---------------------------------------------------

def test_a_jog_then_a_slanted_line_is_also_read_as_the_side_line_running_on():
    """Round 8, P0 (a false pass on 77796ee: complies). Lot (0,0) (60,0) (60,100) (70,100) (90,130) (0,130): the east
    side jogs out 10 ft at 100 ft back, then slants 56° to the back corner. Read with jog and slant running on as
    the east side line: east side 100 + 10 + 36.06 = 146.06, depth (146.06 + 130) / 2 = 138.03, rear 34.5 ft; the
    house (10..30 x 30..99) is 31 ft from the rear line: fails. Never complies."""
    res = run(floors(10, 30, 30, 99, 2), lot=[(0, 0), (60, 0), (60, 100), (70, 100), (90, 130), (0, 130)])
    depth = res["measurements"]["lot_depth"]
    assert 138.03 in {round(r["value"], 2) for r in depth["readings"]}
    assert status(res, "R-1b.rear_yard") != present.COMPLIES


def test_a_double_jog_is_also_read_as_one_stepped_side_line():
    """Round 8: the east side steps out twice (100 -> 106 -> 112); read as one stepped side line it is
    80 + 6 + 20 + 6 + 30 = 142, depth (142 + 130) / 2 = 136."""
    res = run(floors(10, 30, 40, 70, 2),
              lot=[(0, 0), (100, 0), (100, 80), (106, 80), (106, 100), (112, 100), (112, 130), (0, 130)],
              street_line=[[[0, 0], [100, 0]]])
    assert 136.0 in {round(r["value"], 2) for r in res["measurements"]["lot_depth"]["readings"]}


def test_the_sample_lot_and_scenario_09_keep_their_answers():
    """106 Ithaca Rd's sample (a 73 x 90 rectangle) is unchanged: one reading, depth 90, no 'line ... as a rear lot
    line' words, the rear yard complies; scenario 09 still needs review on its rear yard, and its house moved 4 ft
    back never complies."""
    res = run(floors(12, 27, 61, 59, 3), lot=[(0, 0), (73, 0), (73, 90), (0, 90)], street_line=[[[0, 0], [73, 0]]])
    depth = res["measurements"]["lot_depth"]
    assert depth["value"] == 90.0 and depth["readings"] == [] and "as a rear lot line" not in depth["how"]
    assert status(res, "R-1b.rear_yard") == present.COMPLIES
    assert status(run(floors(15, 30, 45, 80, 2), lot=FIVE_SIDED), "R-1b.rear_yard") == present.REVIEW
    assert status(run(floors(15, 34, 45, 84, 2), lot=FIVE_SIDED), "R-1b.rear_yard") != present.COMPLIES


def test_a_main_building_off_the_lot_leaves_an_accessory_building_on_it_measured():
    """Round 8, P3: the house wholly off the lot (y 150..190 on a 120 ft lot) waits; the listed frame shed on the
    lot (20..30 x 90..100) is measured on its own: 20 ft from the west line, 20 from the rear: complies."""
    res = run(floors(15, 150, 45, 190, 2) + [prism(rect(20, 90, 30, 100), 0, 10, "shed")],
              accessory_buildings=["shed"], accessory_frame=True)
    assert res["measurements"]["accessory_side_yard"]["value"] == 20.0
    assert status(res, "R-1b.accessory_buildings") == present.COMPLIES
    assert status(res, "R-1b.front_yard") == present.REVIEW


def test_an_accessory_building_beside_an_off_lot_house_still_waits_for_trustworthy_ground():
    """Round 9, P1 (complies on befd63e): the house off the lot, a listed frame shed on it, and the ground level
    above every building (500 ft: it contradicts the model). With the house on the lot the shed's distances wait;
    with the house off it they must wait too."""
    res = run(floors(15, 150, 45, 190, 2) + [prism(rect(20, 90, 30, 100), 0, 10, "shed")],
              accessory_buildings=["shed"], accessory_frame=True, grade_elevation=500)
    assert res["measurements"]["accessory_side_yard"]["value"] is None
    assert status(res, "R-1b.accessory_buildings") != present.COMPLIES
