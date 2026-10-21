"""The stress test's oracle checked on its own, before it is trusted to judge Gordium.

1. Its rule formulas give every worked example in R-1b.yaml its expected answer (they are copied by hand from the
   rulebook's `check` text, so a copying mistake fails here).
2. Hand-worked designs (worked out on paper from the code's words, not by running Gordium) give the numbers shown.
"""

import math
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate  # noqa: E402
import oracle  # noqa: E402
from rule_format.rulebook import REPO  # noqa: E402

RULEBOOK = REPO / "regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/R-1b.yaml"


def _world(given):
    g = dict(given)
    w = {"front": g.get("front_yard"), "rear": g.get("rear_yard"), "depth": g.get("lot_depth"),
         "area": g.get("building_area"), "lot_area": g.get("lot_area"), "height": g.get("building_height"),
         "stories": g.get("stories"), "width": g.get("lot_width"),
         "front_eaves": g.get("front_yard_eaves"), "rear_eaves": g.get("rear_yard_eaves")}
    sides = [g[k] for k in ("side_yard_smaller", "side_yard_larger") if k in g]
    w["side"] = min(sides) if sides else None
    eaves = [g[k] for k in ("side_yard_smaller_eaves", "side_yard_larger_eaves") if k in g]
    w["side_eaves"] = min(eaves) if eaves else None
    if g.get("accessory_buildings"):
        w["accessories"] = [(g["accessory_front_yard"], g.get("accessory_side_yard"), g.get("accessory_rear_yard"))]
        w["distances_apply"] = g.get("accessory_distances_apply", True)
    return w


def _examples():
    book = yaml.safe_load(RULEBOOK.read_text(encoding="utf-8"))
    for rule in book["rules"]:
        if rule["id"] in oracle.RULE_FUNCTIONS:
            for k, ex in enumerate(rule.get("examples") or []):
                if ex["expect"] in ("pass", "fail"):
                    yield pytest.param(rule["id"], ex, id=f"{rule['id']}#{k + 1}")


@pytest.mark.parametrize("rule,example", list(_examples()))
def test_the_oracles_formulas_give_every_rulebook_example_its_answer(rule, example):
    slack = oracle.RULE_FUNCTIONS[rule](_world(example["given"]))
    assert (slack >= -oracle.EPS) == (example["expect"] == "pass"), (rule, example, slack)


def test_every_rule_the_stress_test_judges_has_examples():
    ids = {p.values[0] for p in _examples()}
    assert set(oracle.RULE_FUNCTIONS) <= ids


def test_the_starting_house_on_the_sample_lot_by_hand():
    """106 Ithaca Rd, 73 x 90, the starting house 12..61 x 27..58'-10" (49'-0" x 31'-10"), 3 floors to 35'-0":
    front 27, sides 12, rear 90 - 58.8333 = 31.1667 (needs 25% of 90 = 22.5); coverage 49 x 31.8333 = 1559.83 sf of
    6,570 = 23.74%; height 35 <= 35 (at the limit); 3 stories."""
    d = generate.starting_design("sample_tax")
    m = oracle.measure(d)
    assert m["yards"]["front"] == (27.0, 27.0) and m["yards"]["side"] == (12.0, 12.0)
    assert m["yards"]["rear"][0] == pytest.approx(90 - 58.833333, abs=1e-5)
    assert m["area"][0] == pytest.approx(49 * (58.833333 - 27), abs=1e-3)
    assert m["lot_area"] == (6570.0, 6570.0) and m["height"][0] == pytest.approx(35.0)
    v = oracle.verdicts(d)
    for rule in ("R-1b.front_yard", "R-1b.side_yards", "R-1b.rear_yard", "R-1b.lot_coverage", "R-1b.height",
                 "R-1b.stories", "R-1b.yard_projections"):
        assert v[rule]["verdict"] == oracle.PASS, rule
    assert v["R-1b.accessory_buildings"]["verdict"] == oracle.NA


def test_the_tax_map_tolerance_by_hand():
    """Each line 2 ft closer: yards 2 ft less (front 25, sides 10: still pass, at the limit), the lot
    (73 - 4) x (90 - 4) = 5,934 sf: under the 6,000 sf minimum, and coverage 1,559.83 / 5,934 = 26.3% > 25%."""
    t = oracle.verdicts(generate.starting_design("sample_tax"), tolerance=True)
    assert t["_measured"]["lot_area"][0] == pytest.approx(69 * 86)
    assert t["R-1b.front_yard"]["slack"] == pytest.approx(0.0) and t["R-1b.side_yards"]["slack"] == pytest.approx(0)
    assert t["R-1b.lot_area_one_family_detached"]["verdict"] != oracle.PASS
    assert t["R-1b.lot_coverage"]["slack"] < 0


def _gable(over, fascia, axis=0, rise=10.0):
    """The surveyed sample lot's starting house (10..63 x 25..55'-11", 53'-0" x 30'-11", at every limit), its top
    floor taken off (23'-4" tall), a gable roof solid on it. axis 0: the house's first edge (63,25) -> (63,55.9167)
    runs front to back, so the eaves are on the front and rear walls; axis 1: on the side walls."""
    d = generate.starting_design("sample_survey")
    d = generate.apply(d, {"op": "delete_floor", "which": "top"})
    return generate.apply(d, {"op": "add_roof", "kind": "roof", "axis": axis, "over": over, "fascia": fascia,
                              "rise": rise, "inset": 3})


def test_a_gable_roofs_height_range_by_hand():
    """Eaves on the side walls (axis 1: 53 ft apart), soffit at 23.333, fascia 0.5 (roof edge 23.833), ridge 33.333,
    1.5 ft past the walls. The slope from the edge to the ridge: (33.333 - 23.833) / (26.5 + 1.5) = 0.3393 ft/ft;
    the roof surface over the wall (the wall plate reading) 23.833 + 1.5 x 0.3393 = 24.342. Lowest reading
    (soffit + ridge) / 2 = 28.333; highest (wall plate + ridge) / 2 = 28.838. The attic may be a story: 2 or 3."""
    d = _gable(1.5, 0.5, axis=1)
    m = oracle.measure(d)
    assert m["height"][1] == pytest.approx((23.333333 + 33.333333) / 2, abs=1e-5)
    assert m["height"][0] == pytest.approx((23.833333 + 1.5 * 9.5 / 28 + 33.333333) / 2, abs=1e-5)
    assert m["stories"] == (3, 2)


def test_an_overhang_is_a_range_for_the_yards():
    """A 3 ft overhang on the front and rear walls (axis 0): the front yard is 25 to the walls and 22 to the
    overhang; the side yards (10, no overhang there) are exact. The front yard passes if the 3 ft is an eave
    (25 >= 25) and fails if it isn't (22 < 25): undecided. The eaves rule: 22 < 25 - 2 = 23: fails either way."""
    d = _gable(3.0, 0.0, axis=0)
    m = oracle.measure(d)
    assert m["yards"]["front"] == (22.0, 25.0) and m["yards"]["side"] == (10.0, 10.0)
    v = oracle.verdicts(d)
    assert v["R-1b.front_yard"]["verdict"] == oracle.UNDECIDED
    assert v["R-1b.side_yards"]["verdict"] == oracle.PASS
    assert v["R-1b.yard_projections"]["verdict"] == oracle.FAIL


def test_a_building_wholly_off_the_lot_can_have_no_yard():
    d = generate.apply(generate.starting_design("narrow"), {"op": "off_lot", "target": "house", "line": 1,
                                                            "amount": 5})
    v = oracle.verdicts(d)
    assert v["_measured"]["where"]["main"] == "off"
    for rule in ("R-1b.front_yard", "R-1b.side_yards", "R-1b.rear_yard"):
        assert v[rule]["verdict"] == oracle.NOT_PASS


def test_a_building_across_a_lot_line_has_no_yard_there():
    d = generate.apply(generate.starting_design("narrow"), {"op": "cross_line", "target": "house", "line": 1,
                                                            "amount": 3})
    v = oracle.verdicts(d)
    assert v["_measured"]["where"]["main"] == "crossing" and v["_measured"]["yards"]["side"][1] == 0.0
    assert v["R-1b.side_yards"]["verdict"] == oracle.FAIL


def test_a_jog_lots_stepped_side_line_is_a_side_line():
    """The jog lot's east line steps in to x = 62 from 80 ft back: that line runs back from the jog to the rear,
    alongside the lot like the side line in front of it. A shed 4 ft from it is 4 ft from a side lot line
    (§325-25C, R-1: 6 ft): it fails, frame."""
    d = generate.starting_design("jog")
    d["parts"].append({"id": "shed", "kind": "shed", "group": "accessory", "outline": [[48, 95], [58, 95], [58, 105],
                                                                                        [48, 105]], "z0": 0, "z1": 9})
    d["listed"], d["frame"] = ["shed"], True
    v = oracle.verdicts(d)
    assert v["_measured"]["accessories"][0][1][1] == 4.0
    assert v["R-1b.accessory_buildings"]["verdict"] == oracle.FAIL


def test_spot_grades_give_the_grade_plane_only_at_the_walls():
    d = generate.starting_design("sloped")
    m = oracle.measure(d)
    assert m["height"] == (pytest.approx(35.0), pytest.approx(35.0))       # (1 + 3 + 2 + 2) / 4 = 2: 37 - 2
    moved = generate.apply(d, {"op": "move_house", "dx": 0, "dy": 5})
    assert oracle.measure(moved)["height"] is None                       # the spots are no longer at its walls


def test_a_dormer_past_the_wall_is_a_range_never_a_fail():
    """Review round 1: a dormer reaching 1.5 ft past the side wall (10 ft from the line), the eaves 2 ft past it:
    the dormer might be a projection (yard_projections#1, open for bay windows) or part of the building, the eave an
    eave or not: the side yard is 8 to 10, undecided, never a fail claimed for every reading."""
    d, done = generate.build("sample_survey", [
        {"op": "delete_floor", "which": "top"},
        {"op": "add_roof", "kind": "roof", "axis": 1, "over": 2.0, "fascia": 0.0, "inset": 3, "rise": 10},
        {"op": "add_dormer", "side": 0, "t0": 0.3, "span": 0.2, "past": 1.5, "h": 6}])
    assert len(done) == 3
    assert oracle.measure(d)["yards"]["side"] == (8.0, 10.0)
    assert oracle.verdicts(d)["R-1b.side_yards"]["verdict"] == oracle.UNDECIDED


def test_a_porch_left_standing_apart_is_not_the_house():
    """A porch on the east wall, then the house's east wall pulled 2 ft in: the porch stands 2 ft off. It is no
    longer part of the main building: a building not listed (accessory or main?), so the accessory rule is
    undecided."""
    d, done = generate.build("narrow", [{"op": "add_porch", "kind": "porch", "face": 0, "t0": 0.2, "span": 0.3,
                                         "depth": 4, "h": 10}, {"op": "stretch", "face": 0, "amount": -2}])
    assert len(done) == 2
    _, detached = oracle.main_and_detached(d)
    assert [p["kind"] for g in detached for p in g] == ["porch"]
    assert oracle.verdicts(d)["R-1b.accessory_buildings"]["verdict"] == oracle.UNDECIDED
