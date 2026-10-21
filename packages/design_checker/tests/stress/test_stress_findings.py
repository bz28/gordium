"""What the architect stress test found, each shrunk to its fewest edits and pinned as a named test.

A finding is a bug in Gordium's own code: it is fixed in the PR that owns that code, not here. Until then its test
is marked xfail(strict=True) with the finding's id: CI stays green, and the day the fix lands the test passes,
strict xfail turns that into a failure, and the mark is taken off (the test then guards the fix). Each xfail names
raises=AssertionError: only the finding's own assertion counts as "still reproduces", never a crash or a changed
output shape.

Fixed (the marks are off; the tests guard the fixes): F1, F3, F5, fixed in PR #18 (77796ee). Still open: F2 (the
tax-map tolerance for area; Ben decided 2 ft per line everywhere, being fixed), F4 (a repeated id).

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


# ---- F2 (P1, needs a decision): the tax map's 2 ft is taken off each dimension for area, off each line for yards -

@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="F2: the tax-map worst case moves each lot line 1 ft for area (2 ft for yards)")
def test_F2_the_starting_house_on_the_sample_lot_with_each_line_2_ft_closer():
    """No edits: 106 Ithaca Rd from the tax map (73 x 90) and Gordium's starting house (49'-0" x 31'-10",
    1,559.8 sf). Gordium keeps the house 2'-0" back from every yard limit because each lot line may be 2 ft off.
    With each line 2 ft closer the lot is (73 - 4) x (90 - 4) = 5,934 sf: coverage 1,559.8 / 5,934 = 26.3% > 25%,
    and the lot is under the 6,000 sf minimum. Gordium's worst case is (73 - 2) x (90 - 2) = 6,248 sf (each line
    1 ft): "Complies even at the tax-map worst case", 25.0%, and lot area complies. Either the yards' worst case or
    the area's is wrong: they can't both be the tax map 2 ft off."""
    got, items = _check(generate.starting_design("sample_tax"))
    assert got["R-1b.lot_coverage"] != COMPLIES and got["R-1b.lot_area_one_family_detached"] != COMPLIES


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

@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="F4: a solid sharing another's id is dropped from the stories count")
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


# ---- the oracle's side of each finding (plain tests: they must pass, so a broken oracle fails CI) ----------------

def test_the_oracle_on_F1_the_shed_and_the_house_fail_on_the_stepped_side_line():
    assert oracle.verdicts(_with_shed("jog", JOG_SHED))["R-1b.accessory_buildings"]["verdict"] == oracle.FAIL
    d, _ = generate.build("jog", [{"op": "move_house", "dx": 19, "dy": 0}])
    assert oracle.verdicts(d)["R-1b.side_yards"]["verdict"] == oracle.FAIL


def test_the_oracle_on_F2_each_line_2_ft_closer_fails_coverage_and_lot_area():
    t = oracle.verdicts(generate.starting_design("sample_tax"), tolerance=True)
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
