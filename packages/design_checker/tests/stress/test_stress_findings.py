"""What the architect stress test found, each shrunk to its fewest edits and pinned as a named test.

A finding is a bug in Gordium's own code: it is fixed in the PR that owns that code, not here. Until then its test
is marked xfail(strict=True) with the finding's id: CI stays green, and the day the fix lands the test passes,
strict xfail turns that into a failure, and the mark is taken off (the test then guards the fix). Each xfail names
raises=AssertionError: only the finding's own assertion counts as "still reproduces", never a crash or a changed
output shape.

Fixed (the marks are off; the tests guard the fixes): F1, F3, F5 in PR #18 (77796ee); F2 by the stack-keeper
(2 ft per line everywhere, carried up in d43e11f); F4 in #12 (the same_id stop, b5a899b); F6, F7 in #18 (ca4f6c3,
4ce81b3); F8, F9 in #18 (1729590, #14's 7 ft line and walls counted once). F10, F11, F12 (#14's stories, a36ccff; merged a98149b). F13, F14 in #18 (1262820). Open: F15.

Each test says what an architect would do, what Gordium says, and what the law says (the oracle's working)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate  # noqa: E402
import harness  # noqa: E402
import oracle  # noqa: E402

COMPLIES, FAILS, REVIEW = harness.COMPLIES, harness.FAILS, harness.REVIEW


@pytest.fixture(scope="module", autouse=True)
def fast():
    harness.fast_reads()
    yield
    harness.slow_reads()


def _check(design):
    res = harness.gordium(design)
    return harness.statuses(res), harness.items_by_rule(res)


def _with_shed(lot_name, outline, listed=True, frame=True):
    d = generate.starting_design(lot_name)
    d["parts"].append({"id": "shed", "kind": "shed", "group": "accessory", "outline": outline, "z0": 0.0, "z1": 9.0})
    d["listed"], d["frame"] = (["shed"] if listed else []), frame
    return d


# ---- F1 (P0): on a lot whose side line steps in (a jog), the stepped part is read as a rear lot line -------------

JOG_SHED = [[48.0, 95.0], [58.0, 95.0], [58.0, 105.0], [48.0, 105.0]]


def test_F1_a_frame_shed_4_ft_from_the_jog_lots_stepped_side_line_does_not_comply():
    """The jog lot: 70 ft at the street, its east line stepping in 8 ft at 80 ft back and running on to the rear at
    x = 62. A listed frame shed at x 48..58, y 95..105: 4 ft from that line. The line runs back alongside the lot,
    like the side line in front of it; §325-25C in R-1: frame accessory buildings "not less than six feet from any
    side lot line": 4 < 6, does not comply. Gordium measures the line as a rear lot line (accessory rear yard 4 ft,
    3 ft required) and the side yard to the corner of the jog (19'-7"): complies. Even if which lines are side and
    which rear on a jog were an open question, a pass under one reading only must be needs review, never complies."""
    got, _ = _check(_with_shed("jog", JOG_SHED))
    assert got["R-1b.accessory_buildings"] != COMPLIES


def test_F1_the_house_moved_toward_the_stepped_side_line_does_not_comply_on_that_side():
    """One edit: Gordium's starting house on the jog lot (10..37 x 25..95) moved 19 ft east (29..56). Its east wall
    is 6 ft from the stepped side line x = 62 (from 80 to 95 ft back): side yard 6 < 10, does not comply. Gordium:
    side yard East 14'-0" (to x = 70) complies, and reads the 6 ft as a rear yard."""
    d, _ = generate.build("jog", [{"op": "move_house", "dx": 19, "dy": 0}])
    got, _ = _check(d)
    assert got["R-1b.side_yards"] != COMPLIES


# ---- F2 (P1, fixed): the tax map's 2 ft was taken off each dimension for area, off each line for yards ------

OLD_TAX_HOUSE = ("sample_tax", [{"op": "stretch", "face": 1, "amount": 58.833333333333336 - 57.25}])
JUST_OVER = ("sample_tax", [{"op": "stretch", "face": 1, "amount": 0.25}])


def test_F2_the_old_starting_house_with_each_line_2_ft_closer_never_complies():
    """106 Ithaca Rd from the tax map (73 x 90) and the starting house Gordium drew before the fix (49'-0" x
    31'-10", 1,559.8 sf). Each lot line may be 2 ft off: (73 - 4) x (90 - 4) = 5,934 sf, coverage 26.3% > 25%, and
    the lot is under the 6,000 sf minimum. Gordium used (73 - 2) x (90 - 2) = 6,248 sf (1 ft per line) and said
    both comply. Neither may comply."""
    got, _ = _check(generate.build(*OLD_TAX_HOUSE)[0])
    assert got["R-1b.lot_coverage"] != COMPLIES and got["R-1b.lot_area_one_family_detached"] != COMPLIES


def test_F2_the_new_starting_house_complies_with_each_line_2_ft_closer_and_a_quarter_foot_more_does_not():
    """Today's starting house (49'-0" x 30'-3", 1,482.25 sf) fits 25% of 5,934 = 1,483.5 sf: Gordium says complies,
    and the oracle agrees with each line 2 ft in. Pulled 3 in. further back (1,494.5 sf) it still passes with each
    line 1 ft in (the old worst case) but not 2 ft in: never complies."""
    start = generate.starting_design("sample_tax")
    assert oracle.verdicts(start, tolerance=True)["R-1b.lot_coverage"]["verdict"] == oracle.PASS
    assert _check(start)[0]["R-1b.lot_coverage"] == COMPLIES
    over = generate.build(*JUST_OVER)[0]
    assert oracle.verdicts(over, tolerance=True, tolerance_ft=1.0)["R-1b.lot_coverage"]["verdict"] == oracle.PASS
    assert oracle.verdicts(over, tolerance=True)["R-1b.lot_coverage"]["slack"] < 0
    assert _check(over)[0]["R-1b.lot_coverage"] != COMPLIES


# ---- F3 (P2): one floor moved: a height reading at a lower floor's top, and it comes and goes with the drawing ---

F3_CASE = ("sample_tax", [{"op": "move_floor", "k": 2, "dx": -3.25, "dy": 6.0}, {"op": "rotate", "deg": 7.3}])


def test_F3_the_same_house_drawn_the_other_way_round_keeps_its_height():
    """Gordium's starting house on the sample lot (3 floors, 35'-0"), the top floor moved on its own (3'-3" west,
    6'-0" back), then the house rotated 7.3 degrees. Its height is 35'-0" whichever way its outlines run: the top
    of the third floor block is the highest level of its flat roof (§325-3 HEIGHT OF BUILDING). Gordium: drawn one
    way, 35'-0" complies; with every outline written the other way round, "23'-4" to 35'-0"", a reading at the
    second floor's top, needs review. (On a house over the limit the low reading would turn a sure 'does not
    comply' into 'needs review'.) Also seen with no rotation, from a model in millimeters (narrow lot, the house
    moved, then floor 1 moved) and in inches."""
    d, _ = generate.build(*F3_CASE)
    readings = []
    got = []
    for order in ("as_drawn", "reversed", "shifted"):
        res = harness.gordium(d, order)
        got.append(harness.statuses(res)["R-1b.height"])
        h = res["measurements"]["building_height"]
        readings += [h["value"]] if h["value"] is not None else [r["value"] for r in h["readings"]]
    assert min(readings) == pytest.approx(35.0) and len(set(got)) == 1, (readings, got)


# ---- F5 (P2): the side yard rows swap East and West when the outlines are drawn the other way round ---------------

F5_CASE = ("sample_tax", [{"op": "add_roof", "kind": "mansard", "axis": 0, "over": 3.0, "fascia": 0.5, "inset": 3.25,
                           "rise": 11.25},
                          {"op": "add_accessory", "kind": "shed", "w": 23.25, "d": 21.75, "h": 15.0, "where": "front",
                           "face": 0, "fx": 0.15, "fy": 0.76, "gap": 7.25, "listed": False, "frame": None}])


def test_F5_the_west_side_yard_stays_west_whichever_way_the_outlines_run():
    """The sample lot's starting house with a mansard reaching 3 ft past every wall (9 ft from each side line at
    its base, 12 to the walls), and an unlisted 23'-3" x 21'-9" shed in the front yard 9'-6 3/4" from the WEST line.
    West: 9'-0" to 9'-6 3/4" (the shed may be a second main building), East: 9'-0" to 12'-0". Drawn as given,
    Gordium says exactly that; with every outline written the other way round it puts 9'-0" to 9'-6 3/4" (does not
    comply, shown red) on the East row and the East numbers on the West row: the wrong side named."""
    d, _ = generate.build(*F5_CASE)
    for order in ("as_drawn", "reversed", "shifted"):
        rows = {i["name"]: i for i in harness.items_by_rule(harness.gordium(d, order))["R-1b.side_yards"]}
        assert {"Side yard, West", "Side yard, East"} <= set(rows) or order != "as_drawn"
        assert rows["Side yard, West"]["proposed"] == "9'-0\" to 9'-6 3/4\"", order
        assert rows["Side yard, East"]["proposed"] == "9'-0\" to 12'-0\"", order


# ---- F4 (P2): two solids with the same id: one is dropped from the story count -----------------------------------

def test_F4_four_floors_with_a_repeated_id_never_comply_as_three_stories():
    """Gordium's starting house on the surveyed sample lot plus a fourth floor block whose id repeats floor 2's (the
    site as check_site takes it; Rhino's exported copies carry unique ids, an API caller or a scenario may not).
    Gordium measures the height to the fourth floor (46'-8") but counts 3 stories: stories complies. Four floor
    blocks are 4 stories (3 allowed); a repeated id should be refused or measured, never silently dropped."""
    d, _ = generate.build("sample_survey", [{"op": "add_floor", "h": 11.6666666667}])
    site = generate.gordium_site(d)
    site["buildings"][-1]["id"] = "floor 2"
    res = harness.run_site(site, generate.gordium_facts(d))
    assert harness.statuses(res)["R-1b.stories"] != COMPLIES


# ---- F6 (P0, fixed in #18 ca4f6c3): a plain-solid house with a wing of floor blocks takes a typed story count below them -----

F6_CASE = ("sample_survey", [{"op": "plain_wing", "n": 3, "face": 1, "depth": 12, "h": 10.0, "typed": 1}])


def test_F6_a_typed_count_below_the_floor_blocks_drawn_never_complies():
    """One edit: the surveyed sample lot's starting house redrawn as one plain solid (53'-0" x 30'-11", 35'-0", no
    floor marks), with a wing of three of Gordium's floor blocks (10 ft each) against its rear wall, and the
    architect's typed story count 1. The wing alone is three stories drawn (STORY, §325-3: between one floor level
    and the next), so the building has at least 3, and the plain solid's own stories aren't drawn: a typed 1 can't
    be the building's count. Never complies until that is resolved. Gordium: Stories 1, complies."""
    got, _ = _check(generate.build(*F6_CASE)[0])
    assert got["R-1b.stories"] != COMPLIES


def test_the_oracle_on_F6_the_typed_count_below_the_drawn_floors_can_not_pass():
    d, done = generate.build(*F6_CASE)
    assert len(done) == 1
    assert oracle.verdicts(d)["R-1b.stories"]["verdict"] == oracle.NOT_PASS
    ok, _ = generate.build("sample_survey", [{**F6_CASE[1][0], "n": 4, "typed": None}])
    assert oracle.verdicts(ok)["R-1b.stories"]["verdict"] == oracle.FAIL          # 4 floor blocks: at least 4 > 3


# ---- F7 (P2, fixed in #18 4ce81b3): on the jog lot the overhangs named "toward the rear yard" depend on the outline order -----

F7_GABLE = ("jog", [{"op": "add_roof", "kind": "roof", "axis": 1, "over": 0.5, "fascia": 0.0, "inset": 4.25,
                     "rise": 8.25}])
F7_MANSARD = ("jog", [{"op": "add_roof", "kind": "mansard", "axis": 0, "over": 3.0, "fascia": 1.0, "inset": 3.5,
                       "rise": 6.25}])


def _eave_texts(case):
    d = generate.build(*case)[0]
    out = []
    for order in ("as_drawn", "reversed", "shifted"):
        rows = harness.items_by_rule(harness.gordium(d, order))
        out.append(sorted((i["name"], i["status"], i["reason"]) for r in ("R-1b.front_yard", "R-1b.side_yards")
                          for i in rows[r]))
    return out


def test_F7_a_side_eave_gable_names_the_same_overhangs_whichever_way_the_outlines_run():
    """The jog lot's starting house with a gable roof solid whose eaves reach 6 in. past the two side walls (axis 1):
    nothing reaches past the front or rear wall. Drawn as given, the side yard rows ask to confirm "0'-6" past the
    walls toward the side yard". With every outline written the other way round they also ask about "0'-0 3/8"
    past the walls toward the rear yard", an overhang that isn't there (the architect would be asked to confirm an
    eave that doesn't exist). The same with a mansard 3 ft past every wall: 3'-0" toward the rear yard one way,
    3'-0 3/4" the other. Same design, same rows: the words must not depend on the drawing order."""
    for case in (F7_GABLE, F7_MANSARD):
        texts = _eave_texts(case)
        assert texts[0] == texts[1] == texts[2], case[1][0]["kind"]


# ---- F8 (P0, fixed in #18 1729590): a plain wing 7 to 8 ft tall, nothing typed, complied from the floors alone

F8_CASE = ("jog", [{"op": "floor_wing", "heights": [7.5], "face": 0, "depth": 8.5, "below": 0.0, "typed": "none"}])


def test_F8_a_7_ft_6_plain_wing_with_nothing_typed_never_complies():
    """One edit: the jog lot's starting house (3 floor blocks, 35'-0") with a plain solid wing 7'-6" tall joined to
    its east wall. The agreed rule (coordinator, 2026-10-21): stories are counted only from floor blocks; a plain
    part 7 ft or taller may hold a story the drawing doesn't show, so only a typed count of at least the floors
    counted (and the plain blocks stacked) stands. Nothing is typed: the count is open, never complies. Gordium:
    Stories 3, complies; #18's line is 8 ft (ca4f6c3). Decided 2026-10-21: 7 ft is right (#14's one definition, cited
    to NYS R305.1); this passes when #18 swaps its 8 ft copy for #14's definition (arriving via term-index)."""
    got, _ = _check(generate.build(*F8_CASE)[0])
    assert got["R-1b.stories"] != COMPLIES


def test_the_oracle_on_F8_a_7_ft_6_plain_wing_opens_the_count():
    d, done = generate.build(*F8_CASE)
    assert len(done) == 1
    assert oracle.verdicts(d)["R-1b.stories"]["verdict"] == oracle.NOT_PASS


# ---- F9 (P3, fixed in #18 1729590): the spot-grade reason counted the walls differently by outline order ----

F9_CASE = ("sloped", [{"op": "move_floor", "k": 0, "dx": 0.0, "dy": -5.75}, {"op": "rotate", "deg": -0.9},
                      {"op": "add_roof", "kind": "roof", "axis": 0, "over": 0.0, "fascia": 0.0, "inset": 3.5,
                       "rise": 7.25}])


def test_F9_the_spot_grade_reason_is_the_same_whichever_way_the_outlines_run():
    """The sloped lot's starting house (on its four spot grades), floor 1 moved 5'-9" toward the street, the house
    rotated 0.9 degrees, a gable roof solid on top. Height and stories need review either way ("spot grades no
    longer at the building's walls"), but the reason says "7 walls without one" drawn as given and "9 walls without
    one" with each outline starting at its next point. The same building has one number of walls."""
    d = generate.build(*F9_CASE)[0]
    reasons = []
    for order in ("as_drawn", "reversed", "shifted"):
        rows = harness.items_by_rule(harness.gordium(d, order))
        reasons.append([i["reason"] for r in ("R-1b.height", "R-1b.stories") for i in rows[r]])
    assert reasons[0] == reasons[1] == reasons[2], reasons


# ---- F10 (P0, fixed by #14's stories definition): a floor block above a gap isn't counted, so a typed count below the blocks drawn stands ----------

F10_CASE = ("sample_survey", [{"op": "delete_floor", "which": "middle"},
                              {"op": "floor_wing", "heights": [9.0], "face": 1, "depth": 10, "below": 0.0,
                               "typed": "below"}])


def test_F10_a_typed_count_below_the_floor_blocks_drawn_never_complies_even_with_a_gap():
    """Two edits: the surveyed sample lot's starting house with its middle floor block deleted (floor 1 at 0-11'-8",
    floor 3 left where it was, 23'-4" to 35'-0"), and a 9 ft plain wing on its rear wall with 1 typed. Two floor
    blocks are drawn, so the building has at least 2 stories (STORY, §325-3); a plain part 7 ft or taller leaves the
    typed count standing only if at least the floors counted (the agreed rule): 1 < 2, never complies. Gordium:
    Stories 1, complies (it counts only the block at the ground; the block above the gap is left out of the
    count, so the typed 1 stands). The same with the fourth floor of a gapped stack and 2 typed (long run, seed 29,
    corner lot)."""
    got, _ = _check(generate.build(*F10_CASE)[0])
    assert got["R-1b.stories"] != COMPLIES


def test_the_oracle_on_F10_two_blocks_drawn_and_one_typed_can_not_pass():
    d, done = generate.build(*F10_CASE)
    assert len(done) == 2 and d["typed_stories"] == 1
    assert oracle.verdicts(d)["R-1b.stories"]["verdict"] == oracle.NOT_PASS


# ---- F11 (P3, fixed in #18 a36ccff): a rotated house's side yard rows are named by compass one way, narrower/wider the other -

F11_CASE = ("sample_survey", [{"op": "rotate", "deg": 4.7},
                              {"op": "add_roof", "kind": "roof", "axis": 1, "over": 1.0, "fascia": 1.0, "inset": 3.0,
                               "rise": 8.0}])


def test_F11_the_side_yard_rows_are_named_the_same_whichever_way_the_outlines_run():
    """The surveyed sample lot's starting house rotated 4.7 degrees, a gable roof solid on it with eaves 1 ft past
    the side walls. Drawn as given, the side yard rows are "Side yard, narrower" and "Side yard, wider"; with each
    outline starting at its next point they are "Side yard, East" and "Side yard, West" (the same numbers and
    statuses). One building, one way of naming its side yards."""
    d = generate.build(*F11_CASE)[0]
    names = [sorted(i["name"] for i in harness.items_by_rule(harness.gordium(d, order))["R-1b.side_yards"])
             for order in ("as_drawn", "reversed", "shifted")]
    assert names[0] == names[1] == names[2], names


# ---- F12 (P2, fixed in #18 a36ccff): a side yard row needs review and gives no reason ------------------------------------------

F12_CASE = ("sample_tax", [{"op": "move_floor", "k": 1, "dx": -3.0, "dy": -3.75},
                           {"op": "add_roof", "kind": "mansard", "axis": 1, "over": 0.5, "fascia": 0.5, "inset": 3.5,
                            "rise": 6.75}])


def test_F12_every_side_yard_row_that_needs_review_says_why():
    """Two edits on the tax-map sample lot: floor 2 moved on its own 3 ft west and 3'-9" toward the street, then a
    mansard on the top floor reaching 6 in. past its walls. "Side yard, East" says needs review, 11'-6" to 12'-0",
    with no reason at all (the West row does give one). A needs-review row must say what it waits for."""
    rows = harness.items_by_rule(harness.gordium(generate.build(*F12_CASE)[0]))["R-1b.side_yards"]
    assert all((i["reason"] or "").strip() for i in rows if i["status"] == REVIEW), [i["name"] for i in rows]


# ---- F13 (P1, fixed in #18 1262820): on a tax-map lot, a 45 ft house wholly off the lot: height needs review, with no reason ----------

F13_CASE = ("sample_tax", [{"op": "off_lot", "target": "house", "line": 1, "amount": 9.25},
                           {"op": "add_floor", "h": 10.0}])


def test_F13_a_45_ft_house_wholly_off_a_tax_map_lot_does_not_comply_on_height_and_says_why():
    """Two edits on the tax-map sample lot: the starting house dragged wholly off the lot past its east line, then
    a fourth floor block (45'-0"). The height doesn't depend on the lot: 45 ft is over 35 ft, and over the 38'-6"
    the §325-16C bonus can ever reach, so it does not comply whatever the yards or lot lines. Gordium: needs
    review, 45'-0", with an empty reason (the same house on a surveyed lot: does not comply, with its reason)."""
    d = generate.build(*F13_CASE)[0]
    h = harness.items_by_rule(harness.gordium(d))["R-1b.height"]
    assert all((i["reason"] or "").strip() for i in h)
    assert harness.statuses(harness.gordium(d))["R-1b.height"] == FAILS


def test_the_oracle_on_F13_the_45_ft_house_fails_height_anywhere():
    d, done = generate.build(*F13_CASE)
    assert len(done) == 2 and oracle.verdicts(d)["R-1b.height"]["verdict"] == oracle.FAIL


# ---- F14 (P0, a crash, fixed in #18 1262820): a rotated house with a gable roof solid: the check raises a GEOS error ----------------------

F14_CASE = ("sample_survey", [{"op": "rotate", "deg": -8.7},
                              {"op": "add_roof", "kind": "roof", "axis": 0, "over": 0.0, "fascia": 0.0, "inset": 3.25,
                               "rise": 13.75}])


def test_F14_a_rotated_house_with_a_gable_roof_is_checked_without_crashing():
    """Two edits on the surveyed sample lot: the starting house rotated 8.7 degrees, then a gable roof solid on it
    (no overhang, ridge 13'-9" above the walls). The check stops with "TopologyException: side location conflict"
    (shapely unary_union in measure._projection_now, from _attached in _assemblies): no answer at all in Rhino.
    Whatever it can't read should need review with a reason, never crash."""
    res = harness.gordium(generate.build(*F14_CASE)[0])
    assert harness.statuses(res)


# ---- F15 (P3): the 'ground doesn't meet the buildings' stop comes and goes with the spot grades -------------------

F15_CASE = ("sloped", [{"op": "shift_floor", "k": 3, "dz": 3.25, "carry": False}])


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="F15: 'the ground doesn't meet the buildings' holds the yards only while the spots are at the walls")
def test_F15_the_yards_of_a_floating_house_do_not_wait_on_the_ground_only_sometimes():
    """The sloped lot's starting house (on its four spot grades, ground 2.0 ft) with floor 1 raised 3'-3" on its
    own: nothing reaches the ground (5'-3" to 37'-0"). Gordium stops every yard and the coverage ("the ground level
    doesn't meet the buildings"). Pull the west wall in 1'-11" and the spots are no longer at the walls, that stop
    is no longer read, and the yards and coverage are measured (complies) although the house still floats. The
    plan yards don't depend on the ground; either way, the same floating house must get the same yard results.
    (Found as invariant c: with a listed shed in front, shrinking the house turned coverage from needs review to
    does not comply.)"""
    d = generate.build(*F15_CASE)[0]
    pulled = generate.apply(d, {"op": "stretch", "face": 2, "amount": -1.94})
    a, b = harness.statuses(harness.gordium(d)), harness.statuses(harness.gordium(pulled))
    for rule in ("R-1b.front_yard", "R-1b.side_yards", "R-1b.rear_yard"):
        assert a[rule] == b[rule], (rule, a[rule], b[rule])


# ---- the oracle's side of each finding (plain tests: they must pass, so a broken oracle fails CI) ----------------

def test_the_oracle_on_F1_the_shed_and_the_house_fail_on_the_stepped_side_line():
    assert oracle.verdicts(_with_shed("jog", JOG_SHED))["R-1b.accessory_buildings"]["verdict"] == oracle.FAIL
    d, _ = generate.build("jog", [{"op": "move_house", "dx": 19, "dy": 0}])
    assert oracle.verdicts(d)["R-1b.side_yards"]["verdict"] == oracle.FAIL


def test_the_oracle_on_F2_each_line_2_ft_closer_fails_coverage_and_lot_area():
    t = oracle.verdicts(generate.build(*OLD_TAX_HOUSE)[0], tolerance=True)
    assert t["R-1b.lot_coverage"]["slack"] < 0 and t["R-1b.lot_area_one_family_detached"]["slack"] < 0
    assert t["_measured"]["lot_area"][0] == pytest.approx(69 * 86)


def test_the_oracle_on_F3_the_height_is_35_ft():
    d, _ = generate.build(*F3_CASE)
    assert oracle.verdicts(d)["R-1b.height"]["verdict"] == oracle.PASS
    assert oracle.measure(d)["height"] == (pytest.approx(35.0), pytest.approx(35.0))


def test_the_regression_cases_still_build_every_edit():
    """A regression case whose edits stopped applying (the generator changed) would test nothing."""
    for lot_name, edits in (F3_CASE, F5_CASE, ("jog", [{"op": "move_house", "dx": 19, "dy": 0}])):
        assert len(generate.build(lot_name, edits)[1]) == len(edits)


def _turned(value, deg):
    """Every [x, y(, z)] in a site or facts value turned `deg` (a multiple of 90) about the origin, exactly."""
    if isinstance(value, dict):
        return {k: _turned(v, deg) for k, v in value.items()}
    if isinstance(value, list) and value and all(isinstance(c, (int, float)) for c in value) and len(value) in (2, 3):
        x, y = value[0], value[1]
        x, y = {0: (x, y), 90: (-y, x), 180: (-x, -y), 270: (y, -x)}[deg]
        return [x, y, *value[2:]]
    if isinstance(value, list):
        return [_turned(v, deg) for v in value]
    return value


def test_F5_a_side_yard_named_by_compass_only_holds_distances_to_that_line():
    """Round 8, P2: the whole F5 site (lot, buildings, street) turned 0, 90, 180 and 270 degrees, every outline
    order. A row named "Side yard, <direction>" must show only distances measured toward that direction, under
    every reading; where they differ the rows say narrower and wider, never a wrong side."""
    def facing(pts):
        dx, dy = pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]
        return ("East" if dx > 0 else "West") if abs(dx) >= abs(dy) else ("North" if dy > 0 else "South")
    d, _ = generate.build(*F5_CASE)
    for deg in (0, 90, 180, 270):
        for order in ("as_drawn", "reversed", "shifted"):
            res = harness.run_site(_turned(generate.gordium_site(d, order), deg),
                                   _turned(generate.gordium_facts(d), deg))
            m = res["measurements"]
            names = []
            for i in harness.items_by_rule(res)["R-1b.side_yards"]:
                names.append(i["name"])
                direction = i["name"].split(", ")[-1]
                if direction in ("narrower", "wider"):
                    continue
                rec = m[i["measure"]]
                pts = [r["points"] for r in rec["readings"] if r.get("points")] or [rec["points"]]
                assert {facing(p) for p in pts} == {direction}, (deg, order, i["name"])
            assert len(names) == 2, names

