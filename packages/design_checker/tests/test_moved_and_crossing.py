"""Ben's one-floor-moved cases on the sample lot, and a building that crosses a lot line (review round 4).

The starting house on 106 Ithaca Rd's 73 x 90 lot (from the tax map) sits 12 ft from each side line and 27 ft from
the street, 3 floor blocks. Moving any one floor block 5 ft east puts it 12 − 5 = 7 ft from the east line (10 ft
required): the side yard does not comply, whichever floor it is. Moving only the top floor 6 ft toward the street
puts it 27 − 6 = 21 ft back (25 required, 23 at best on the tax-map lot): the front yard does not comply."""

import sys

import pytest

from design_checker import present
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "packages/design_checker/tests"))
from test_every_reading import floors, prism, rect, rows, run, status  # noqa: E402
from test_quickstart import _check, _moved, house  # noqa: E402,F401  (house: the module fixture)
from host_source import host_text


@pytest.mark.parametrize("which", [0, 1, 2])
def test_one_floor_moved_5_ft_east_does_not_comply_on_the_east_side(house, which):
    # (106 Ithaca Rd's real tax-map outline since term-index 3b808e2: the starting house is 51'-4" x 29'-8", its
    # sides Northeast and Southwest; 12'-0 3/8" from the northeast line, 27'-0 3/4" from the street)
    got, facts = house
    items = _check(_moved(got["floors"], dx=5, which=which), facts)
    east = items["Side yard, Northeast"]
    assert (east["status"], east["proposed"]) == (present.FAILS, "7'-0 3/8\"")


def test_only_the_top_floor_moved_toward_the_street_is_judged_at_every_reading_of_the_tax_map_lines(house):
    """4 ft: 23'-0" as drawn, but the tax-map street line may be 2 ft off in its favour: at best 25'-0" against
    25'-0": needs review (term-index f1784e3, the every-reading rule on a tax-map lot). 6 ft: 21'-0", at best
    23'-0" < 25'-0": does not comply under every reading."""
    # (106 Ithaca Rd's real tax-map outline since term-index 3b808e2: the starting house is 51'-4" x 29'-8", its
    # sides Northeast and Southwest; 12'-0 3/8" from the northeast line, 27'-0 3/4" from the street)
    got, facts = house
    front = _check(_moved(got["floors"], dy=-4, which=2), facts)["Front yard"]
    assert (front["status"], front["proposed"]) == (present.REVIEW, "23'-0 7/8\"")
    assert "as drawn it does not comply, but at best 25'-0 7/8\"" in front["reason"]
    front = _check(_moved(got["floors"], dy=-6, which=2), facts)["Front yard"]
    assert (front["status"], front["proposed"]) == (present.FAILS, "21'-1\"")


def test_the_eaves_rule_names_the_yard_it_fails_in(house):
    """Review round 4 (found running the floor cases): the house moved 7 ft east fails the eaves rule on the east
    side (5 ft, and at best 5 + 2 = 7 on the tax-map lot, < 10 − 2), so its row says the side yard and 5'-0", never
    'Eaves into front yard 27'-0"'. (5 ft east, 7'-0", now needs review: at best 9'-0" ≥ 8'-0", term-index f1784e3.)"""
    got, facts = house
    items = _check(_moved(got["floors"], dx=7), facts, grade_is="finished")   # the height known (the bonus term)
    eaves =[i for n, i in items.items() if n.startswith("Eaves into")]
    assert len(eaves) == 1 and eaves[0]["status"] == present.FAILS
    assert (eaves[0]["name"], eaves[0]["proposed"]) == ("Eaves into side yard", "5'-0 3/8\"")   # 12'-0 3/8" - 7


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


def test_a_crossing_building_is_told_only_to_move_back_onto_the_lot_and_the_checker_keeps_it():
    """PR 18 with the arch-fixes-2 batch (#15): a building partly off the lot fails whatever else, and its one advice
    is "To comply: move it back onto the lot." Every row of a rule the crossing fails shows that advice and no
    other (never the yard's own "keep every part … at least" figure, which settle would otherwise work out from the
    negative margin), and check.confirm_advice keeps it (no measured change can simulate it; a dropped hint would
    leave the architect with no way out). Both the side line (yard rows) and the street line (front yard)."""
    for res, rule in ((run(floors(50, 30, 65, 70, 2)), "R-1b.side_yards"),
                      (run(floors(15, -5, 45, 30, 2)), "R-1b.front_yard")):
        crossing = [i for i in rows(res, rule) if "crosses" in (i["reason"] or "")]
        assert crossing, rows(res, rule)
        for i in crossing:
            assert i["status"] == present.FAILS
            # #18 review rounds 26-27: on a yard row moving back isn't enough to meet the yard: its first step only
            assert i["hint"] in ("First: move it back onto the lot.", "To comply: move it back onto the lot."), i["hint"]
            assert not i["hint"].startswith("To comply") or "yard" not in i["name"].lower(), i
        assert not any("_advice" in i for i in res["view"]["items"])      # popped by confirm_advice


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
    from design_checker.check import summary
    s = summary(res["rows"])["text"]     # the rule rows' own count (the result's line says the panel's words)
    passes = int(s.split(" rule")[0]) if " pass" in s else 0
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
    facts = {**facts, "grade_is": "existing"}       # (the fixture is finished ground since term-index: say existing)
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
    assert front["required"] == "25'-6\" to 26'-10\""             # (the one range block's words, term-index)
    # the one range block's sentence (term-index, architect review P1-3): what it needs, depending on how the
    # height is taken; never "isn't measured" or "before the bonus"
    assert front["reason"].startswith("Needs 25'-6\" to 26'-10\", depending on how the height of a pitched roof"), \
        front["reason"]
    assert "isn't measured" not in front["reason"] and "before the" not in front["reason"]


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


def test_an_eaves_row_that_fails_at_every_height_reading_never_says_needs_review():
    """Round 12, P2: the same gable 11 ft nearer the street (front wall 15 ft back, GABLE (15, 15, 45, 55)): the
    front eaves are 15'-0" against 25'-6" to 26'-10" (the requirement at each height reading): it fails at all of
    them, and the reason begins with the status it has, never 'Needs review' beside 'Does not comply'."""
    from test_every_reading import roof
    b = (15, 15, 45, 55)
    got = rows(run(floors(*b, 3) + [roof(*b, 30, 45, 2.0, 1.0)]), "R-1b.yard_projections")
    front = next(r for r in got if r["name"] == "Eaves into front yard")
    assert front["status"] == present.FAILS and front["proposed"] == "15'-0\""
    assert front["required"] == "25'-6\" to 26'-10\""
    # (the checker's words since #15's verdict landed: fails under every reading, naming what was read)
    assert front["reason"].startswith("Does not comply whichever way it is read: needs 25'-6\" to 26'-10\""), \
        front["reason"]
    assert "Needs review" not in front["reason"]


def test_the_bonus_wait_prefix_follows_the_status():
    """Round 12: one helper picks how a bonus-waiting row begins, from its status, for both cases."""
    assert present._bonus_waits(present.FAILS, True) == "Does not comply at any of the height's readings"
    assert present._bonus_waits(present.FAILS, False) == "Does not comply even before the §325-16C height bonus"
    assert present._bonus_waits(present.REVIEW, True) == present._bonus_waits(present.REVIEW, False) == "Needs review"


# ---- round 12 decision: a rule that fails at every value an unmeasured number could take does not comply ---------

def test_an_eaves_row_that_misses_even_the_base_fails_whatever_the_height():
    """Ben/coordinator 2026-10-21: front_yard_eaves >= 25 + max(h - 35, 0) - 2 is at least 23 ft for every
    height. The gable's front eaves are 15 ft back: with no ground (nothing measured) or on existing grade only,
    the height is unknown, yet 15 < 23 fails at every height: does not comply, never needs review."""
    from test_every_reading import roof
    b = (15, 15, 45, 55)
    for facts in ({"grade_elevation": None, "ground_is_flat": None}, {"grade_is": "existing"}):
        res = run(floors(*b, 3) + [roof(*b, 30, 45, 2.0, 1.0)], **facts)
        assert res["measurements"]["building_height"]["value"] is None
        front = next(r for r in rows(res, "R-1b.yard_projections") if r["name"] == "Eaves into front yard")
        assert front["status"] == present.FAILS and front["required"] == "≥ 23'-0\"", facts
        assert front["reason"].startswith("Does not comply even before the §325-16C height bonus"), front["reason"]
        assert "R-1b.yard_projections" in {r["Rule id"] for r in res["rows"] if r["Fails"]}


def test_an_eaves_row_that_meets_the_base_stays_needs_review_with_the_height_unknown():
    """Never a false pass: the front eaves 24 ft back meet the base 23 ft, but the bonus could raise it past 24
    (any height over 36 ft): with the height unknown, needs review, never complies, never fails."""
    from test_every_reading import roof
    b = (15, 24, 45, 64)
    res = run(floors(*b, 3) + [roof(*b, 30, 45, 2.0, 1.0)], grade_elevation=None, ground_is_flat=None)
    front = next(r for r in rows(res, "R-1b.yard_projections") if r["name"] == "Eaves into front yard")
    assert front["proposed"] == "24'-0\"" and front["status"] == present.REVIEW


def test_fails_whatever_needs_proof_and_one_unknown():
    """The rule fails whatever only when it is proven truest at 0 and fails there; a rule truest for a large
    value, two unknown values, or a value with readings are left to needs review."""
    from design_checker.check import fails_whatever
    rule = {"id": "t", "kind": "rule", "check": "front_yard_eaves >= 25 + max(building_height - 35, 0) - 2"}
    unknown = {"value": None, "readings": []}
    assert fails_whatever(rule, {"front_yard_eaves": {"value": 15.0}, "building_height": unknown}, {})["names"] == \
        ["building_height"]
    assert fails_whatever(rule, {"front_yard_eaves": {"value": 24.0}, "building_height": unknown}, {}) is None
    assert fails_whatever(rule, {"front_yard_eaves": unknown, "building_height": unknown}, {}) is None
    readings = {"value": None, "readings": [{"reading": "a", "value": 40.0}, {"reading": "b", "value": 50.0}]}
    assert fails_whatever(rule, {"front_yard_eaves": {"value": 15.0}, "building_height": readings}, {}) is None
    taller = {"id": "t", "kind": "rule", "check": "building_height >= 40"}     # truest when tall: never failed
    assert fails_whatever(taller, {"building_height": unknown}, {}) is None


def test_the_eaves_row_names_the_yard_that_fails_whatever_the_height():
    """The eaves rule is four limits at once; with the height unknown none can be evaluated as it stands, so the
    row named the first (front). The house 15..45 x 30..100 on the 60 x 120 lot: front eaves 30 ft (base 23: may
    pass), rear eaves 20 ft against at least max(min(0.25 x 120, 50), 20) - 2 = 28 ft at any height: the rear
    fails whatever the height, and the row is that one."""
    from test_every_reading import roof
    b = (15, 30, 45, 100)
    res = run(floors(*b, 3) + [roof(*b, 30, 45, 2.0, 1.0)], grade_elevation=None, ground_is_flat=None)
    got = rows(res, "R-1b.yard_projections")
    assert [r["name"] for r in got] == ["Eaves into rear yard"] and got[0]["status"] == present.FAILS
    assert got[0]["proposed"] == "20'-0\"" and got[0]["required"] == "≥ 28'-0\""


def test_an_unmeasured_height_on_a_tax_map_lot_fails_only_if_it_fails_under_every_reading_of_the_lines():
    """The two every-reading rules together. Height unknown (no ground), the lot from the tax map. Front eaves
    22 ft: as drawn 22 < 23 (the base, the height at its most favourable, 0), but the street line may be 2 ft off
    in its favour: 24 >= 23 could comply: needs review. 20 ft: at best 22 < 23: does not comply."""
    from test_every_reading import roof
    got = {}
    for front in (22, 20):
        b = (15, front, 45, front + 40)
        res = run(floors(*b, 3) + [roof(*b, 30, 45, 2.0, 1.0)], grade_elevation=None, ground_is_flat=None,
                  lot_surveyed=False)
        got[front] = next(r for r in rows(res, "R-1b.yard_projections") if r["name"] == "Eaves into front yard")
    assert got[22]["status"] == present.REVIEW and got[22]["reason"]       # the checker's verdict (row_verdict)
    assert got[20]["status"] == present.FAILS


@pytest.mark.parametrize("extra", [{"applies_when": "building_height < 50"},
                                   {"review_when": [{"when": "building_height > 60", "why": "t"}]}])
def test_fails_whatever_never_uses_a_number_that_decides_whether_the_rule_applies(extra):
    """Round 13, P3: the check alone fails at h = 0 (15 < 23), but whether the rule applies (or must be
    reviewed) depends on the same unknown height: not known, so never 'does not comply'."""
    from design_checker.check import fails_whatever
    rule = {"id": "t", "kind": "rule", "check": "front_yard_eaves >= 25 + max(building_height - 35, 0) - 2", **extra}
    measured = {"front_yard_eaves": {"value": 15.0}, "building_height": {"value": None, "readings": []}}
    assert fails_whatever(rule, measured, {}) is None


def test_a_rule_failing_under_every_lot_line_reading_on_a_tax_map_lot_is_judged_with_the_lucky_lines_too():
    """Round 14, P1. Scenario 09's five-sided lot from the tax map, the house's rear wall at y = 87: rear yard
    27.28 ft against 27'-6" (depth 110) or 31.69 ft (depth 126.77): it fails under every reading of the lot
    lines. With the lines 2 ft in its favour (rear yard 29.28, depth 110 - 4 = 106, 26'-6" required) it complies:
    on a tax-map lot that is needs review ('at best'), never does not comply; the requirement is shown under each
    reading, never a dash."""
    import copy
    from design_checker import scenarios
    from design_checker.check import check_site
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "09_five_sided_lot.yaml"))
    sc["lot"]["surveyed"] = False
    for b in sc["buildings"]:
        b["outline"] = [[15, 30], [45, 30], [45, 87], [15, 87]]
    s, f, extras = scenarios.site(sc)
    rear = {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}["Rear yard"]
    assert rear["status"] == present.REVIEW, rear                          # the checker's verdict (row_verdict)
    assert "as drawn it does not comply, but at best 29'-3" in rear["reason"] and "against 26'-6\"" in rear["reason"]
    assert rear["required"] == "27'-6\" to 31'-8 3/8\"", rear["required"]   # 31.6926 ft, rounded up


def test_a_rule_failing_under_every_lot_line_reading_on_a_survey_says_which_measurement_it_was_read_over():
    """Round 14, P1: the same house on the surveyed lot fails under every reading: the reason names what was read
    (the lot depth), never the doubled 'Fails under every reading considered (fails under every reading)'."""
    import copy
    from design_checker import scenarios
    from design_checker.check import check_site
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "09_five_sided_lot.yaml"))
    for b in sc["buildings"]:
        b["outline"] = [[15, 30], [45, 30], [45, 87], [15, 87]]
    s, f, extras = scenarios.site(sc)
    rear = {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}["Rear yard"]
    assert rear["status"] == present.FAILS
    # (the one range block's words: what it needs, and what that depends on, never the doubled phrase)
    assert rear["reason"].startswith("Does not comply whichever way it is read: needs 27'-6\" to 31'-8 3/8\" (the "
                                     "lot depth depends on"), rear["reason"]
    assert "fails under every reading" not in rear["reason"]


def test_fails_whatever_with_several_unknowns_numbers_at_zero_and_yes_no_both_ways():
    """#20 review round 2: several unknown values. Each number provably truest at 0 is taken at 0, each yes/no
    tried both ways; the rule does not comply only if it fails under every one of those settings. The shape of
    R-3a note 7 (lot_area >= (7000 if conversion else 6000) + 750 * max(units - 3, 0) + 500 * rooms), written with
    measures this branch has: a yes/no (accessory_distances_apply) and two counts."""
    from design_checker.check import fails_whatever
    rule = {"id": "t", "kind": "rule", "check": "lot_area >= (7000 if accessory_distances_apply else 6000) + 750 * "
                                                "max(sleeping_rooms - 3, 0) + 500 * parking_spaces"}
    unknown = {"value": None, "readings": []}
    # 3,000 sf: fails at 0 past 3, 0, and the yes/no either way: whatever they are
    got = fails_whatever(rule, {"lot_area": {"value": 3000.0}, "sleeping_rooms": unknown,
                                "parking_spaces": unknown, "accessory_distances_apply": unknown}, {})
    assert got["names"] == ["accessory_distances_apply", "parking_spaces", "sleeping_rooms"]
    assert len(got["settings"]) == 2 and {s["accessory_distances_apply"] for s in got["settings"]} == {False, True}
    # the counts given (3, 0), the yes/no not: 5,999 fails both ways (6,000 / 7,000)
    assert fails_whatever(rule, {"lot_area": {"value": 5999.0}, "sleeping_rooms": {"value": 3},
                                 "parking_spaces": {"value": 0}, "accessory_distances_apply": unknown}, {})
    # 6,500 sf: one way it would pass: never 'does not comply' (and never a pass)
    assert fails_whatever(rule, {"lot_area": {"value": 6500.0}, "sleeping_rooms": unknown,
                                 "parking_spaces": {"value": 0}, "accessory_distances_apply": {"value": False}},
                          {}) is None
    assert fails_whatever(rule, {"lot_area": {"value": 6500.0}, "sleeping_rooms": {"value": 3},
                                 "parking_spaces": {"value": 0}, "accessory_distances_apply": unknown}, {}) is None
    # a number the formula can't be proven truest at 0 for: never decided
    odd = {"id": "t", "kind": "rule", "check": "lot_area >= 6000 + 750 * sleeping_rooms * parking_spaces"}
    assert fails_whatever(odd, {"lot_area": {"value": 10.0}, "sleeping_rooms": unknown,
                                "parking_spaces": unknown}, {}) is None


def test_a_rule_waiting_on_an_interior_fact_that_fails_whatever_it_is_is_never_hidden():
    """#20 review round 2: a row waiting on an interior fact went to 'not checked' before fails_whatever ran, so a
    proven fail was hidden. A rule shaped like parking: at least 1 + max(bedrooms - 3, 0) spaces, truest at 0
    bedrooms. With 0 spaces and the bedrooms not given it fails whatever they are: shown, never 'not checked'. With
    1 space it could comply (3 bedrooms or fewer): it waits for the bedrooms."""
    from design_checker.check import waits_on_interior
    rule = {"id": "t", "kind": "rule", "check": "parking_spaces >= 1 + max(sleeping_rooms - 3, 0)"}
    row = {"Error": "NEEDS REVIEW"}
    rooms = {"value": None, "readings": []}
    assert not waits_on_interior(row, rule, {"parking_spaces": {"value": 0}, "sleeping_rooms": rooms}, {})
    assert waits_on_interior(row, rule, {"parking_spaces": {"value": 1}, "sleeping_rooms": rooms}, {})
    assert not waits_on_interior({"Error": "PASS"}, rule, {"parking_spaces": {"value": 1}, "sleeping_rooms": rooms}, {})


def test_the_interior_facts_have_one_definition():
    """#20 review round 2, P3: present.py kept a second, unused copy of check.INTERIOR, edited by hand alongside
    it. One definition only (check.INTERIOR)."""
    from design_checker import check
    text = (REPO / "packages/design_checker/design_checker/present.py").read_text(encoding="utf-8")
    assert "INTERIOR =" not in text and not hasattr(present, "INTERIOR") and check.INTERIOR


def test_an_interior_row_is_named_by_its_rule_and_asks_for_the_facts_it_waits_for():
    """#20 review round 2, P2: every interior row was 'Parking · needs input', asking for bedrooms and parking
    whatever it waited for. Now named from its own rule, listing the facts it needs. R-1b's one-family parking with
    the bedrooms given and the spaces not: 'Parking · needs input', asking for the parking spaces only."""
    res = run(floors(15, 30, 45, 70, 2), sleeping_rooms=3)
    item = next(i for i in res["view"]["items"] if i["rule"] == "R-1b.parking_one_family")
    assert item["status"] == present.NOT_CHECKED and item["name"] == "Parking · needs input"
    assert item["needs"] == ["parking_spaces"] and item["hint"] == "Enter parking spaces"
    both = next(i for i in run(floors(15, 30, 45, 70, 2))["view"]["items"] if i["rule"] == "R-1b.parking_one_family")
    assert both["needs"] == ["sleeping_rooms", "parking_spaces"]           # (#15's enter-needs: its order)
    assert both["reason"] == "Needs bedrooms and parking spaces, which the model doesn't show"


def test_a_side_yards_own_verdict_is_the_checkers_and_never_looser_than_named_result():
    """Review round 19, P2 (now #15's row_verdict per side, with PR 18's every-reading rule for named readings):
    one side yard with readings of its own. Eave readings named, but two values under each (11 / 12 as an eave,
    10.5 / 11.5 not: which lot lines are side lines, an unnamed question): never complies (named_result is None
    for it): needs review. The same side with one value under each named reading, all passing: complies."""
    from design_checker.check import named_result, row_verdict
    measured = {"side_yard_smaller": {"value": None, "readings": [
        {"reading": "a", "value": 11.0, "named": {"model#eave": "eave"}},
        {"reading": "b", "value": 12.0, "named": {"model#eave": "eave"}},
        {"reading": "a", "value": 10.5, "named": {"model#eave": "not_eave"}},
        {"reading": "b", "value": 11.5, "named": {"model#eave": "not_eave"}}]},
        "side_yard_larger": {"value": 8.0, "readings": []}}
    rule = {"id": "R-1b.side_yards", "kind": "rule", "check": "side_yard_smaller >= 10 and side_yard_larger >= 10"}
    assert named_result({**rule, "check": "side_yard_smaller >= 10"}, measured, {}) is None
    assert row_verdict(rule, measured, {}, None, check="side_yard_smaller >= 10") == present.REVIEW
    one = {**measured, "side_yard_smaller": {"value": None, "readings": [
        {"reading": "", "value": 11.0, "named": {"model#eave": "eave"}},
        {"reading": "", "value": 10.5, "named": {"model#eave": "not_eave"}}]}}
    assert row_verdict(rule, one, {}, None, check="side_yard_smaller >= 10") == present.COMPLIES


def test_a_row_held_back_only_by_the_tax_maps_lines_says_so_and_never_counts_as_passing():
    """Review round 20, P2: eaves 1'-6" past side walls 11'-6" from each line, on the tax map: as drawn it complies
    under every eave reading (the yards to the eaves 10'-0" against 8'-0"), but with each line 2 ft in it may not.
    The row says that (the tax map, at worst, a survey settles it), never 'complies ... confirm with the zoning
    office'; and the summary never counts it as passing (it counts from the checker's verdict only)."""
    from test_every_reading import roof
    res = run(floors(11.5, 30, 44.5, 70, 2) + [roof(11.5, 30, 44.5, 70, 20, 28, 1.5, 1.0)], lot_surveyed=False)
    side = [i for i in rows(res, "R-1b.side_yards") if i["status"] == present.REVIEW]
    assert side and all("tax map" in i["reason"] and "zoning office" not in i["reason"] for i in side), side
    assert res["summary"]["state"] != "pass"
    assert any("Side yard" in line for line in res["summary"]["lines"]), res["summary"]


def test_a_geometry_error_anywhere_in_the_check_is_a_reason_never_a_crash(monkeypatch):
    """Review round 21, P2: the F14 guard covered the measuring only; the check's plan and envelope worked the
    overlays out again, unguarded, and crashed. One guard for the whole check: a GEOS failure while measuring
    flags every measurement, nothing is drawn from it (no envelope, no overlays), and every building row needs
    review saying why."""
    import shapely
    from model_measurement.places.ithaca_city import measure as m

    def broken(building):
        raise shapely.errors.GEOSException("TopologyException: side location conflict at 1 2")
    monkeypatch.setattr(m, "_projection_now", broken)
    res = run(floors(15, 30, 45, 70, 2))
    assert res["plan"]["encroach"] == [] and res["envelope"]["outline"] is None
    building = [i for i in res["view"]["items"] if i.get("measure") in (
        "front_yard", "side_yard_smaller", "rear_yard", "building_height", "building_area")]
    assert building and all(i["status"] == present.REVIEW and "geometry couldn't be worked out" in i["reason"]
                            for i in building), [(i["name"], i["status"], i["reason"]) for i in building]


def test_the_envelope_and_the_plan_use_the_one_union_rule():
    """Round 21: the plan drawn and the envelope union shapes with the measuring's own rule (measure.union, the
    grid fallback included), never a second copy that can crash where the measuring didn't."""
    text = {p: (REPO / p).read_text(encoding="utf-8") for p in (
        "packages/design_checker/design_checker/check.py", "packages/envelope_builder/envelope_builder/envelope.py")}
    assert all("ops.unary_union(" not in t for t in text.values())
    assert "union as unary_union" in text["packages/design_checker/design_checker/check.py"]


def test_the_outline_cleaning_note_is_shown_in_the_panel_and_the_report(tmp_path):
    """Review round 21, P2: the note was in each item's detail and nothing showed it. The panel's detail lists it
    (apps/rhino_plugin/gordium_ui.py show_detail) and the report's Check sheet says it once, with the lot."""
    import openpyxl
    from design_checker.check import check_site, sample_site
    ui = host_text("rhino", "ui", purpose="wiring")
    show = ui.split("def show_detail", 1)[1].split("\ndef ", 1)[0]
    # (since #53, show_detail lists the plain notes from rhino_logic.detail_parts, which keeps this one in view)
    assert 'split = logic.detail_parts(det)' in show and 'for text in split["notes"]:' in show
    from design_checker import rhino_logic
    assert "the outline" in rhino_logic.detail_parts({"outline": "the outline"})["notes"]
    s = sample_site()
    n = len(s["lot"])
    site = {"units": "ft", "problems": [], "buildings": floors(20, 30, 50, 60, 2),
            "lot": {"id": "lot", "edges": [{"points": [list(s["lot"][i]), list(s["lot"][(i + 1) % n])], "curved": False}
                                           for i in range(n)]}}
    report = tmp_path / "check.xlsx"
    res = check_site(site, {**s["facts"], "ground_is_flat": True, "grade_elevation": 0.0}, report_path=report)
    note = next(i["detail"]["outline"] for i in res["view"]["items"] if i["detail"].get("outline"))
    assert note.startswith("tax-map outline cleaned within 0.25 ft")
    sheet = openpyxl.load_workbook(report)["Check"]
    assert any(c.value == "Lot lines: " + note for c in sheet["A"]), [c.value for c in sheet["A"]][:12]


def test_no_starting_house_is_drawn_from_geometry_the_measuring_couldnt_work_out(monkeypatch, tmp_path):
    """Review round 21, P2: the starting-house generator read the lot again after the measuring had failed on it
    and crashed. A geometry error while measuring is flagged on every measurement, and the generator draws nothing
    from it, saying why."""
    import rhino3dm as r
    import shapely
    from design_checker.check import sample_site, start
    from model_measurement.places.ithaca_city import measure as m
    sample = sample_site()
    model = r.File3dm()
    model.Settings.ModelUnitSystem = r.UnitSystem.Feet
    layer = r.Layer()
    layer.Name = "Site"
    model.Layers.Add(layer)
    attrs = r.ObjectAttributes()
    attrs.LayerIndex = 0
    model.Objects.AddPolyline([r.Point3d(x, y, 0) for x, y in sample["lot"] + sample["lot"][:1]], attrs)
    path = tmp_path / "lot.3dm"
    model.Write(str(path), 8)

    def broken(self, tol, kind):
        raise shapely.errors.GEOSException("TopologyException: side location conflict at 1 2")
    monkeypatch.setattr(m.Lot, "_simplify", broken)
    out = start(path, {**sample["facts"], "address": sample["address"], "grade_is": "finished",
                       "ground_is_flat": True, "grade_elevation": 0.0})
    assert out["floors"] == [] and any("geometry couldn't be worked out" in n for n in out["notes"]), out


def test_an_eaves_rows_advice_is_its_yards_requirement_eaves_included_never_move_the_building():
    """#18 review round 26 (P2): after the merge the eaves rows ("Eaves into side yard") were told "move the
    building 4'-0" farther from that lot line", which the checker 'confirmed' by changing only that one eaves
    distance; doing it left the row failing (the far side's eaves came closer). An eaves row's advice is now its yard's
    requirement for every part, eaves included, the one change check.confirm_advice simulates."""
    res = run(floors(4, 30, 51, 70, 2))
    eaves = [i for i in res["view"]["items"] if i["name"].startswith("Eaves into") and i.get("hint")]
    assert eaves, [(i["name"], i["status"], i.get("hint")) for i in res["view"]["items"]]
    for i in eaves:
        assert "move the building" not in i["hint"], i["hint"]
        if i["hint"].startswith("To comply"):
            assert "every part of the building, eaves included, at least" in i["hint"] and "lot line" in i["hint"]


def test_to_comply_move_back_is_said_only_where_the_crossing_is_the_rows_only_failing_fact():
    """#18 review round 27 (P2): "To comply: move it back onto the lot." was still shown on crossing rows where
    moving back is not enough: a 50 ft, 5-story house's height and stories, coverage of a 63 x 80 footprint, a frame
    shed's 6 ft side distance. It is "To comply" only where the row complies with the crossing set aside; otherwise
    "First: …", and such a row keeps its own figure (50'-0", never only "partly off the lot")."""
    tall = run(floors(50, 30, 65, 70, 5))
    for name in ("Building height", "Stories"):
        i = next(x for x in tall["view"]["items"] if x["name"] == name)
        assert i["status"] == present.FAILS and i["hint"] == "First: move it back onto the lot.", (name, i["hint"])
        assert i["proposed"] != "partly off the lot", (name, i["proposed"])
    wide = run(floors(-5, 30, 58, 110, 1))
    cov = next(x for x in wide["view"]["items"] if x["name"] == "Lot coverage")
    assert cov["hint"] == "First: move it back onto the lot.", cov["hint"]
    low = run(floors(50, 30, 65, 70, 2))                      # 2 stories, 20 ft: height complies but for crossing
    h = next(x for x in low["view"]["items"] if x["name"] == "Building height")
    assert h["hint"] == "To comply: move it back onto the lot." and h["proposed"] == "partly off the lot", h
