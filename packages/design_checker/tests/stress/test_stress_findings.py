"""What the architect stress test (PR 22) found in PR 18's measuring (F1, F3, F5), fixed in PR 18.

Copied from the stress branch with its xfail marks removed: each now guards its fix.

Originally: What the architect stress test found, each shrunk to its fewest edits and pinned as a named test.

A finding is a bug in Gordium's own code: it is fixed in the PR that owns that code, not here. Until then its test
is marked xfail(strict=True) with the finding's id: CI stays green, and the day the fix lands the test passes,
strict xfail turns that into a failure, and the mark is taken off (the test then guards the fix).

Each test says what an architect would do, what Gordium says, and what the law says (the oracle's working)."""

import random
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


# ---- the oracle's side of each finding (plain tests: they must pass, so a broken oracle fails CI) ----------------

def test_the_oracle_on_F1_the_shed_and_the_house_fail_on_the_stepped_side_line():
    assert oracle.verdicts(_with_shed("jog", JOG_SHED))["R-1b.accessory_buildings"]["verdict"] == oracle.FAIL
    d, _ = generate.build("jog", [{"op": "move_house", "dx": 19, "dy": 0}])
    assert oracle.verdicts(d)["R-1b.side_yards"]["verdict"] == oracle.FAIL


def test_the_oracle_on_F3_the_height_is_35_ft():
    d, _ = generate.build(*F3_CASE)
    assert oracle.verdicts(d)["R-1b.height"]["verdict"] == oracle.PASS
    assert oracle.measure(d)["height"] == (pytest.approx(35.0), pytest.approx(35.0))


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


# ---- F7 (P2, for #18; stress-tests d32d437): the overhangs named depend on the outline order --------------------

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
    walls toward the side yard". With every outline written the other way round they also asked about "0'-0 3/8"
    past the walls toward the rear yard", an overhang that isn't there. The same with a mansard 3 ft past every
    wall: 3'-0" toward the rear yard one way, 3'-0 3/4" the other. Same design, same rows."""
    for case in (F7_GABLE, F7_MANSARD):
        texts = _eave_texts(case)
        assert texts[0] == texts[1] == texts[2], case[1][0]["kind"]


# ---- F8 (P0) and F9 (P3), stress-tests 73fc39a: pinned as passing in #18 -----------------------------------------

F8_CASE = ("jog", [{"op": "floor_wing", "heights": [7.5], "face": 0, "depth": 8.5, "below": 0.0, "typed": "none"}])


def test_F8_a_7_ft_6_plain_wing_with_nothing_typed_is_counted_from_the_drawing():
    """The jog lot's starting house (3 floor blocks) with a plain solid wing 7'-6" tall joined to its east wall,
    nothing typed. A plain part 7 ft or taller (NYS R305.1, #14's one stories definition) may hold a story the
    drawing doesn't show (the old 8 ft line missed that). Read from the drawing (term-index a7557f7): 7'-6" holds
    at most 1 story at 7 ft a story, beside the house's 3 floor blocks, so the building has 3 stories whatever the
    wing holds: the one count the drawing allows, said with its reason."""
    d = generate.build(*F8_CASE)[0]
    m = harness.gordium(d)["measurements"]["stories"]
    assert m["value"] == 3 and "could hold up to 1 story" in m["how"], m


F9_CASE = ("sloped", [{"op": "move_floor", "k": 0, "dx": 0.0, "dy": -5.75}, {"op": "rotate", "deg": -0.9},
                      {"op": "add_roof", "kind": "roof", "axis": 0, "over": 0.0, "fascia": 0.0, "inset": 3.5,
                       "rise": 7.25}])


def test_F9_the_spot_grade_reason_is_the_same_whichever_way_the_outlines_run():
    """The sloped lot's starting house on its spot grades, floor 1 moved 5'-9" toward the street, rotated 0.9
    degrees, a gable roof solid on top: 'N walls without one' was 7 drawn as given and 9 with each outline started
    at its next point. The same building has one number of walls, whatever the drawing order."""
    d = generate.build(*F9_CASE)[0]
    reasons = []
    for order in ("as_drawn", "reversed", "shifted"):
        rows = harness.items_by_rule(harness.gordium(d, order))
        reasons.append([i["reason"] for r in ("R-1b.height", "R-1b.stories") for i in rows[r]])
    assert reasons[0] == reasons[1] == reasons[2], reasons


# ---- F11 (P3) and F12 (P2), stress-tests 5e642c9: pinned as passing in #18 ---------------------------------------

F11_CASE = ("sample_survey", [{"op": "rotate", "deg": 4.7},
                              {"op": "add_roof", "kind": "roof", "axis": 1, "over": 1.0, "fascia": 1.0, "inset": 3.0,
                               "rise": 8.0}])


def test_F11_the_side_yard_rows_are_named_the_same_whichever_way_the_outlines_run():
    """The surveyed sample lot's starting house rotated 4.7 degrees, a gable roof solid on it with eaves 1 ft past
    the side walls: the side yard rows were "narrower"/"wider" one way and "East"/"West" the other. One building,
    one way of naming its side yards."""
    d = generate.build(*F11_CASE)[0]
    names = [sorted(i["name"] for i in harness.items_by_rule(harness.gordium(d, order))["R-1b.side_yards"])
             for order in ("as_drawn", "reversed", "shifted")]
    assert names[0] == names[1] == names[2], names


F12_CASE = ("sample_tax", [{"op": "move_floor", "k": 1, "dx": -3.0, "dy": -3.75},
                           {"op": "add_roof", "kind": "mansard", "axis": 1, "over": 0.5, "fascia": 0.5, "inset": 3.5,
                            "rise": 6.75}])


def test_F12_every_side_yard_row_that_needs_review_says_why():
    """Floor 2 moved on its own 3 ft west and 3'-9" toward the street, a mansard on the top floor 6 in. past its
    walls, on the tax-map sample lot: "Side yard, East" needed review with no reason at all."""
    rows = harness.items_by_rule(harness.gordium(generate.build(*F12_CASE)[0]))["R-1b.side_yards"]
    assert all((i["reason"] or "").strip() for i in rows if i["status"] == REVIEW), [i["name"] for i in rows]


def test_every_row_that_needs_review_says_why_over_a_stress_sample():
    """The invariant behind F12: a needs-review row always says what it waits for, on any design. 60 random
    designs from the stress generator (its lots and edits)."""
    import random
    rng = random.Random(1812)
    for _ in range(60):
        case = generate.random_case(rng)
        d = generate.build(case["lot"], case["edits"])[0]
        for i in harness.gordium(d)["view"]["items"]:
            if i["status"] == REVIEW:
                assert (i["reason"] or "").strip(), (case["lot"], case["edits"], i["name"])


# ---- F13 (P1) and F14 (P0), stress-tests 3373ba0: pinned as passing in #18 ---------------------------------------

F13_CASE = ("sample_tax", [{"op": "off_lot", "target": "house", "line": 1, "amount": 9.25},
                           {"op": "add_floor", "h": 10.0}])


def test_F13_a_45_ft_house_wholly_off_a_tax_map_lot_does_not_comply_on_height_and_says_why():
    """The starting house dragged wholly off the tax-map sample lot, then a fourth floor block (45'-0"): 45 ft is
    over 35 ft and over the 38'-6" the §325-16C bonus can ever reach, whatever the yards or lot lines: does not
    comply, with its reason (it needed review with no reason at all)."""
    res = harness.gordium(generate.build(*F13_CASE)[0])
    h = harness.items_by_rule(res)["R-1b.height"]
    assert all((i["reason"] or "").strip() or i["status"] == FAILS for i in h), h
    assert harness.statuses(res)["R-1b.height"] == FAILS


F14_CASE = ("sample_survey", [{"op": "rotate", "deg": -8.7},
                              {"op": "add_roof", "kind": "roof", "axis": 0, "over": 0.0, "fascia": 0.0, "inset": 3.25,
                               "rise": 13.75}])


def test_F14_a_rotated_house_with_a_gable_roof_is_checked_without_crashing():
    """The surveyed sample lot's starting house rotated 8.7 degrees with a gable roof solid on it: the overlay of
    its faces raised a GEOS 'side location conflict' and the check gave no answer. The faces are made valid and,
    if the overlay still fails, unioned on a fine grid; every row has a status, and a needs-review row a reason."""
    res = harness.gordium(generate.build(*F14_CASE)[0])
    assert harness.statuses(res)
    assert all((i["reason"] or "").strip() for i in res["view"]["items"] if i["status"] == REVIEW)


# ---- F16 (#18): nothing measured depends on the order the outlines were drawn in -----------------------------------

F16_CASE = ("corner", [{"op": "rotate", "deg": -5.3}, {"op": "move_house", "dx": 10.0, "dy": 7.75},
                       {"op": "add_roof", "kind": "roof", "axis": 1, "over": 0.5, "fascia": 1.0, "inset": 4.75,
                        "rise": 10.75}])


def test_F16_the_eaves_not_counted_coverage_leaves_out_both_eaves_whichever_way_the_outlines_run():
    """Stress F16 (P2): the corner lot's 40 x 35 house rotated 5.3 degrees, moved 10 ft east and 7'-9" back, a
    gable roof solid with eaves 6 in. past its two 35 ft side walls. Seen from above: walls 40 x 35 = 1,400 sf,
    with both eaves 1,440 sf (independently: the oracle, below). 'Eaves not counted' was 1,420 sf drawn as given
    or starting elsewhere (one eave strip dropped by a second overlay along nearly the same edges), 1,400 sf
    reversed. Now 1,400 every way."""
    d = generate.build(*F16_CASE)[0]
    for order in ("as_drawn", "reversed", "shifted"):
        m = harness.gordium(d, order)["measurements"]["building_area"]
        low = {r["named"].get("building_area#1"): r["value"] for r in m["readings"]}["eaves_not_counted"]
        assert low == pytest.approx(1400.0, abs=0.5), (order, low)


def test_the_oracle_on_F16_walls_1400_and_with_both_eaves_1440():
    d, done = generate.build(*F16_CASE)
    assert len(done) == 3
    assert oracle.measure(d)["area"] == (pytest.approx(1440.0), pytest.approx(1400.0))


def _measured(design, order):
    """Every measurement as order-free facts: its value and each reading's value with its named answers (the
    reading's words name lot lines by the drawn numbering, which a different start point renumbers)."""
    from model_measurement.measure import measure
    out = {}
    for name, r in measure(generate.gordium_site(design, order), generate.gordium_facts(design)).items():
        value = round(r["value"], 2) if isinstance(r.get("value"), (int, float)) else r.get("value")
        readings = sorted((round(x["value"], 2), tuple(sorted((x.get("named") or {}).items())))
                          for x in r.get("readings") or [])
        out[name] = (value, readings, r.get("value") is None and not r.get("readings"))
    return out


def test_every_measurement_is_the_same_whichever_way_and_from_wherever_the_outlines_are_drawn():
    """Metamorphic (F16): the same design drawn with every outline and face the other way round, or starting at
    its next point, measures the same: every measurement's value, and every reading's value with its named
    answers. Every lot (the 106 Ithaca Rd sample, on the tax map and on a survey, and the others), as drawn and
    after random architect's edits (rotations, roofs and eaves, mansards, dormers, porches, wings, accessory
    buildings, moved lines)."""
    rng = random.Random(16)
    cases = [(lt, []) for lt in generate.LOTS] + [F16_CASE]
    cases += [(c["lot"], c["edits"]) for c in (generate.random_case(rng) for _ in range(40))]
    checked = 0
    for lt, edits in cases:
        d, _done = generate.build(lt, edits)
        base = _measured(d, "as_drawn")
        for order in ("reversed", "shifted"):
            other = _measured(d, order)
            diff = {n: (base[n], other[n]) for n in base if base[n] != other[n]}
            assert not diff, (lt, edits, order, diff)
            checked += 1
    assert checked == 2 * len(cases)


# ---- F17 (#18): the way the house is drawn never decides whether a building across a line counts ------------------

F17_CASE = ("jog", [{"op": "add_accessory", "kind": "garage", "w": 8.25, "d": 12.5, "h": 13.0, "where": "side",
                     "face": 2, "fx": 0.79, "fy": 0.75, "gap": 2.0, "listed": False, "frame": None}])


def test_F17_a_garage_across_the_lot_line_gives_coverage_the_same_answer_however_the_house_is_drawn():
    """Stress F17 (P2): one edit on the jog lot, an unlisted 8'-3" x 12'-6" garage at x 59.75..68, y 88..100.6,
    across the stepped side line x = 62. A building across a lot line makes every rule that measures it not
    comply (PR 18), and coverage measures every building on the lot, whichever is the main one. With the house as
    floor blocks (the starting house the main building) coverage did not comply; drawn as one plain solid or
    meshes (the main building then unpicked) it complied, 12%. Now it does not comply every way."""
    d = generate.build(*F17_CASE)[0]
    got = {style: harness.statuses(harness.gordium_file(d, "ft", style))["R-1b.lot_coverage"]
           for style in ("blocks", "one_solid", "mesh")}
    assert set(got.values()) == {FAILS}, got


def test_drawing_the_house_as_floor_blocks_a_solid_or_a_mesh_never_flips_a_row_between_fails_and_complies():
    """Metamorphic (F17): the same design written to Rhino with the house as Gordium's floor blocks, as one plain
    solid, or as meshes may change what can be read (stories from floor blocks, the main building assumed or to
    pick), so a row may move to or from needs review; but never from does not comply to complies or back. Every
    lot as drawn, the F17 case, and 15 random architect's edit sequences."""
    rng = random.Random(17)
    cases = [(lt, []) for lt in generate.LOTS] + [F17_CASE]
    cases += [(c["lot"], c["edits"]) for c in (generate.random_case(rng) for _ in range(15))]
    compared = []
    for lt, edits in cases:
        d, _done = generate.build(lt, edits)
        got = {}
        for style in ("blocks", "one_solid", "mesh"):
            try:
                got[style] = harness.statuses(harness.gordium_file(d, "ft", style))
            except ValueError as e:         # a house whose floors don't stack on one outline has no one-solid form
                assert "don't stack" in str(e), e
        compared.append(len(got))
        for rule in set().union(*got.values()):
            seen = {got[style].get(rule) for style in got}
            assert not {FAILS, COMPLIES} <= seen, (lt, edits, rule, {k: v.get(rule) for k, v in got.items()})
    assert sum(n >= 2 for n in compared) >= 15, compared

