"""PR 18: what the checker can now measure, worked by hand from the code's words before running Gordium, and
pinned. Pitched roofs (§325-3 HEIGHT OF BUILDING), eaves in yards (§325-18B), porches and steps (§325-18A),
accessory buildings (§325-25), corner lots (§325-19C), and the "every reading" rule: where an open question
has named readings, the design complies only if it passes under all of them, does not comply only if it fails
under all of them, and otherwise needs review, saying which readings it fails under.

Every site is built the way an architect draws it in Rhino: the lot on the Site layer, Gordium's floor blocks
(each one story), a roof drawn as its own solid standing on them, other solids beside them. The last test builds
the same thing as a real .3dm with rhino3dm and checks the file."""

import copy

import pytest
import rhino3dm as r

from design_checker import present
from design_checker.check import check, check_site
from model_measurement import interpretations
from model_measurement.read_3dm import FLOOR_KEY

JURISDICTION = "regulations/jurisdictions/new_york/ithaca_city"
LOT = [(0, 0), (60, 0), (60, 120), (0, 120)]                       # 60 x 120 ft, the street along y = 0
FACTS = {"jurisdiction": JURISDICTION, "zone": "R-1b", "use": "one_family_detached", "corner_lot": False,
         "street_line": [[[0, 0], [60, 0]]], "lot_surveyed": True, "ground_is_flat": True, "grade_elevation": 0}


def prism(outline, z0, z1, id, floor=None):
    n = len(outline)
    walls = [{"points": [[*outline[i], z0], [*outline[(i + 1) % n], z0], [*outline[(i + 1) % n], z1], [*outline[i], z1]]}
             for i in range(n)]
    out = {"id": id, "faces": [{"points": [[x, y, z0] for x, y in outline]},
                               {"points": [[x, y, z1] for x, y in outline]}, *walls], "problems": []}
    return {**out, "floor": floor} if floor is not None else out


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def floors(x0, y0, x1, y1, n, h=10.0):
    """Gordium's floor blocks: n stories of h ft, each marked as one story."""
    return [prism(rect(x0, y0, x1, y1), k * h, (k + 1) * h, f"floor {k + 1}", floor=h) for k in range(n)]


def roof(x0, y0, x1, y1, base, ridge, over, fascia, id="roof"):
    """A gable roof drawn as its own solid, standing at `base` on walls x0..x1, y0..y1: its level underside (the
    soffit) reaches `over` past the walls on the two eave sides (x), with a vertical fascia `fascia` deep; the
    roof slopes up from the top of the fascia to the ridge, which runs along y over the middle. With no fascia
    (0) the soffit meets the roof surface at its edge: nothing hangs below the roof edge, a proven eave."""
    xa, xb, xm, lo = x0 - over, x1 + over, (x0 + x1) / 2, base + fascia
    faces = [[(xa, y0, base), (xb, y0, base), (xb, y1, base), (xa, y1, base)],
             [(xa, y0, lo), (xm, y0, ridge), (xm, y1, ridge), (xa, y1, lo)],
             [(xm, y0, ridge), (xb, y0, lo), (xb, y1, lo), (xm, y1, ridge)]]
    if fascia:
        faces += [[(xa, y0, base), (xa, y1, base), (xa, y1, lo), (xa, y0, lo)],
                  [(xb, y0, base), (xb, y1, base), (xb, y1, lo), (xb, y0, lo)],
                  [(xa, y0, base), (xb, y0, base), (xb, y0, lo), (xm, y0, ridge), (xa, y0, lo)],
                  [(xa, y1, base), (xb, y1, base), (xb, y1, lo), (xm, y1, ridge), (xa, y1, lo)]]
    else:
        faces += [[(xa, y0, base), (xb, y0, base), (xm, y0, ridge)], [(xa, y1, base), (xb, y1, base), (xm, y1, ridge)]]
    return {"id": id, "faces": [{"points": [list(p) for p in f]} for f in faces], "problems": []}


def run(buildings, lot=LOT, **facts):
    n = len(lot)
    site = {"units": "ft", "problems": [], "buildings": buildings,
            "lot": {"id": "lot", "edges": [{"points": [list(lot[i]), list(lot[(i + 1) % n])], "curved": False}
                                           for i in range(n)]}}
    return check_site(site, {**FACTS, **facts})


def rows(result, rule):
    return [i for i in result["view"]["items"] if i.get("rule") == rule]


def status(result, rule):
    """A rule's status: the most cautious of its rows (side yards are two rows)."""
    order = [present.FAILS, present.REVIEW, present.NOT_CHECKED, present.COMPLIES]
    return min((i["status"] for i in rows(result, rule)), key=order.index)


# ---- 1. pitched roofs ------------------------------------------------------------------------------------------

HOUSE = (15, 30, 45, 70)          # 30 x 40 ft, 30 ft back from the street, 15 ft from each side line, 50 from the rear


def test_P1_a_pitched_roof_that_complies_under_every_eave_reading():
    """Two floor blocks (20 ft) and a gable roof solid on them: soffit at 20 ft reaching 1.5 ft past the walls, a
    0.5 ft fascia, ridge 30 ft. HEIGHT OF BUILDING (§325-3) "to the average height of a pitched ... roof": midway
    between eave and ridge (finding pitched_roof_midpoint, Gordium's reading). Which eave is open
    (height_of_building#1), so every reading:
      the slope runs from the fascia top (20.5 ft, 1.5 ft outside the wall) to the ridge (30 ft, 15 ft in from the
      wall): 9.5 / 16.5 = 0.5758 ft per ft.
      lowest eave (the soffit, 20 ft):        (20 + 30) / 2 = 25.0
      drip edge (the roof edge, 20.5 ft):     (20.5 + 30) / 2 = 25.25
      wall plate (over the wall: 20.5 + 1.5 × 0.5758 = 21.3636 ft): (21.3636 + 30) / 2 = 25.68
    All ≤ 35 ft: complies under every reading."""
    res = run(floors(*HOUSE, 2) + [roof(*HOUSE, 20, 30, 1.5, 0.5)])
    h = res["measurements"]["building_height"]
    assert h["value"] is None
    assert {r["named"]["height_of_building#1"]: r["value"] for r in h["readings"]} == {
        "lowest_eave": 25.0, "drip_edge": 25.25, "wall_plate": 25.681818}
    item = rows(res, "R-1b.height")[0]
    assert item["status"] == present.COMPLIES
    assert "every reading" in item["reason"] and "Gordium's reading · confirm with the City zoning office" in item["reason"]
    assert item["proposed"] == "25'-0\" to 25'-8 1/4\""              # the span, each end rounded up (a maximum)


def test_P2_a_pitched_roof_that_passes_under_one_eave_reading_only_needs_review_naming_the_others():
    """Three floor blocks (30 ft), roof ridge 40 ft, soffit 30, fascia 0.5, overhang 1.5; the house 25 ft from the
    street. Slope (40 − 30.5) / 16.5 = 0.5758.
      lowest eave: (30 + 40) / 2 = 35.0 ≤ 35: complies.
      drip edge: (30.5 + 40) / 2 = 35.25 > 35: the §325-16C bonus then needs every yard 0.25 ft larger, a 25.25 ft
      front yard; it is 25: fails.
      wall plate: (31.3636 + 40) / 2 = 35.68: fails the same way.
    Mixed: needs review, naming the readings it fails under."""
    res = run(floors(15, 25, 45, 65, 3) + [roof(15, 25, 45, 65, 30, 40, 1.5, 0.5)])
    item = rows(res, "R-1b.height")[0]
    assert item["status"] == present.REVIEW
    assert "wall plate" in item["reason"] and "drip edge" in item["reason"] and "lowest eave" in item["reason"]
    assert item["reason"].index("wall plate") < item["reason"].index("complies if")       # the failing ones first


def test_P3_a_pitched_roof_that_fails_under_every_eave_reading_does_not_comply():
    """The same house with a 45 ft ridge: the lowest reading is (30 + 45) / 2 = 37.5 > 35, so the bonus needs a
    27.5 ft front yard; it is 25 under every reading: does not comply."""
    res = run(floors(15, 25, 45, 65, 3) + [roof(15, 25, 45, 65, 30, 45, 1.5, 0.5)])
    assert status(res, "R-1b.height") == present.FAILS
    assert res["summary"]["state"] == "fail"


def test_an_answer_outranks_the_readings(monkeypatch):
    """When the City or the architects answer which eave (`answers` with `reading: wall_plate`), only that reading
    is measured, and it says who answered. P2 under the wall plate alone: 35.68 > 35, the front yard 25 < 25.68:
    does not comply."""
    real = interpretations.research_entries

    def answered(jurisdiction):
        entries = copy.deepcopy(real(jurisdiction))
        for where, e in entries:
            if where.endswith(" height_of_building"):
                e["open_questions"], e["research"] = [], []
                e["answers"] = [{"question": "Which eave?", "answer": "The top of the wall plate.",
                                 "answered_by": "the City zoning office", "answered_on": "2026-11-01",
                                 "reading": "wall_plate"}]
        return entries
    monkeypatch.setattr(interpretations, "research_entries", answered)
    interpretations.clear_cache()
    try:
        res = run(floors(15, 25, 45, 65, 3) + [roof(15, 25, 45, 65, 30, 40, 1.5, 0.5)])
        h = res["measurements"]["building_height"]
        assert h["value"] == 35.681818 and h["readings"] == []
        assert status(res, "R-1b.height") == present.FAILS
    finally:
        monkeypatch.undo()
        interpretations.clear_cache()


# ---- 2. eaves and other projections into yards ----------------------------------------------------------------

def test_Y1_eaves_may_reach_two_feet_into_a_required_yard_and_no_more():
    """§325-18B: eaves "shall not project more than two feet into any required yard". The house 12 ft from the west
    line (walls), the 10 ft side yard required, so the eaves must stay 8 ft from the line.
      overhang 2.0: eaves at 12 − 2 = 10 ≥ 8: complies; the side yard itself is to the walls: 12 ≥ 10.
      overhang 4.5: eaves at 12 − 4.5 = 7.5 < 8: does not comply (the side yard, to the walls, still complies)."""
    house = (12, 30, 42, 70)
    # no fascia: nothing past the walls hangs below the roof edge, so the overhang is proven an eave
    ok = run(floors(*house, 2) + [roof(*house, 20, 28, 2.0, 0)])
    assert ok["measurements"]["side_yard_smaller"]["value"] == 12.0
    assert ok["measurements"]["side_yard_smaller_eaves"]["value"] == 10.0
    assert status(ok, "R-1b.yard_projections") == present.COMPLIES
    assert status(ok, "R-1b.side_yards") == present.COMPLIES
    over = run(floors(*house, 2) + [roof(*house, 20, 28, 4.5, 0)])
    assert over["measurements"]["side_yard_smaller_eaves"]["value"] == 7.5
    assert status(over, "R-1b.yard_projections") == present.FAILS
    assert status(over, "R-1b.side_yards") == present.COMPLIES
    # a 0.5 ft fascia hangs below the roof edge: most likely the eave, but it could be a shallow story, so the
    # side yard is also read to the whole outline (12 − 2 = 10, still ≥ 10: complies under both; with the
    # 4.5 ft overhang, 7.5 < 10 as a story: needs review, never a pass)
    judged = run(floors(*house, 2) + [roof(*house, 20, 28, 2.0, 0.5)])
    side = judged["measurements"]["side_yard_smaller"]
    assert {r["named"]["model#overhang"]: r["value"] for r in side["readings"]} == {"eave": 12.0, "story": 10.0}
    assert status(judged, "R-1b.side_yards") == present.COMPLIES
    judged_over = run(floors(*house, 2) + [roof(*house, 20, 28, 4.5, 0.5)])
    assert status(judged_over, "R-1b.side_yards") == present.REVIEW


def test_Y2_porch_steps_count_in_the_front_yard():
    """§325-18A: porches, decks, ramps and landings are "part of the building ... for required yards"; the City
    counts porch steps too (finding steps_count, Gordium's reading; BZA #3224, R-1b). Steps 4 ft deep in front of a
    house 28 ft back: front yard 28 − 4 = 24 < 25: does not comply, and it says the reading."""
    steps = prism(rect(25, 24, 35, 28), 0, 2, "steps")
    res = run(floors(15, 28, 45, 68, 2) + [steps])
    assert res["measurements"]["front_yard"]["value"] == 24.0
    item = rows(res, "R-1b.front_yard")[0]
    assert item["status"] == present.FAILS
    assert "Gordium's reading · confirm with the City zoning office: Yes" in item["reason"]
    assert res["measurements"]["accessory_buildings"]["value"] == 0      # touching the house: part of it


# ---- 3. accessory buildings ------------------------------------------------------------------------------------

def test_A1_a_garage_counts_in_coverage_and_keeps_its_own_distances():
    """A 24 x 24 garage, listed as an accessory building, 6 ft from the east line and 6 ft from the rear, 90 ft
    from the street. §325-25: not in a required front yard (90 ≥ 25); §325-25C in R-1: 6 ft from a side lot line
    (6 ≥ 6), 3 ft from the rear (6 ≥ 3); whether that holds for a building that isn't frame is open (325-25C#1), but
    it passes under every reading. Coverage counts it (garages_count): 30 × 40 + 24 × 24 = 1,776 ≤ 25% of 7,200 =
    1,800: complies."""
    garage = prism(rect(30, 90, 54, 114), 0, 12, "garage")
    res = run(floors(*HOUSE, 2) + [garage], accessory_buildings=["garage"])
    m = res["measurements"]
    assert (m["accessory_front_yard"]["value"], m["accessory_side_yard"]["value"],
            m["accessory_rear_yard"]["value"]) == (90.0, 6.0, 6.0)
    assert status(res, "R-1b.accessory_buildings") == present.COMPLIES
    assert m["building_area"]["value"] == 1776.0
    cover = rows(res, "R-1b.lot_coverage")[0]
    assert cover["status"] == present.COMPLIES and "garages count" in cover["reason"].lower()
    assert m["rear_yard"]["value"] == 50.0                            # the chart's yards: to the house


def test_A2_a_garage_4_ft_from_the_side_line_depends_on_whether_it_is_frame():
    """The garage 4 ft from the east line (x 32..56). Frame (stated): §325-25C, 4 < 6: does not comply (the law).
    Construction not stated: frame_distances_apply and r1_distances_apply_to_all_accessory_buildings (4 < 6: fails)
    against front_yard_rule_only (complies): needs review, naming the readings it fails under."""
    garage = prism(rect(32, 90, 56, 114), 0, 12, "garage")
    unknown = run(floors(*HOUSE, 2) + [garage], accessory_buildings=["garage"])
    item = rows(unknown, "R-1b.accessory_buildings")[0]
    assert item["status"] == present.REVIEW
    assert "frame distances apply" in item["reason"] and "front yard rule only" in item["reason"]
    frame = run(floors(*HOUSE, 2) + [garage], accessory_buildings=["garage"], accessory_frame=True)
    assert status(frame, "R-1b.accessory_buildings") == present.FAILS


def test_a_garage_in_the_front_yard_does_not_comply_under_any_reading():
    """§325-25A: "not in a required front yard". A shed 20 ft from the street: 20 < 25 whatever it is built of."""
    shed = prism(rect(48, 20, 56, 28), 0, 8, "shed")
    res = run(floors(*HOUSE, 2) + [shed], accessory_buildings=["shed"])
    assert status(res, "R-1b.accessory_buildings") == present.FAILS


# ---- 4. corner lots --------------------------------------------------------------------------------------------

CORNER = {"corner_lot": True, "street_line": [[[0, 0], [60, 0]], [[60, 0], [60, 120]]],
          "address_street_line": [[[0, 0], [60, 0]]]}


def test_C1_a_corner_lot_with_a_front_yard_on_each_street():
    """60 x 120 lot, streets along y = 0 (the address) and x = 60. §325-19C: every yard facing a street is a front
    yard (25 ft). The house 10..35 x 25..65: from y = 0, 25; from x = 60, 25: complies. §325-8A(14)(d): the rear
    yard is opposite the address street: 120 − 65 = 55 ≥ 25% of 120 = 30. One side yard is left (x = 0): 10 ≥ 10,
    against Column 13 (Gordium's reading corner_lot_side_yard_column_13)."""
    res = run(floors(10, 25, 35, 65, 2), **CORNER)
    m = res["measurements"]
    assert (m["front_yard"]["value"], m["side_yard_smaller"]["value"], m["side_yard_larger"]["value"],
            m["rear_yard"]["value"], m["lot_depth"]["value"]) == (25.0, 10.0, 10.0, 55.0, 120.0)
    for rule in ("R-1b.front_yard", "R-1b.side_yards", "R-1b.rear_yard"):
        assert status(res, rule) == present.COMPLIES, rule
    assert "Column 13" in rows(res, "R-1b.side_yards")[0]["reason"]


def test_C2_a_corner_lot_house_too_close_to_the_second_street_does_not_comply():
    """The house widened to x = 40: 60 − 40 = 20 ft from the second street, a front yard: 20 < 25."""
    res = run(floors(10, 25, 40, 65, 2), **CORNER)
    assert res["measurements"]["front_yard"]["value"] == 20.0
    assert status(res, "R-1b.front_yard") == present.FAILS


# ---- the same, from a real Rhino file -----------------------------------------------------------------------------

def _model_with_roof_and_garage(path):
    m = r.File3dm()
    m.Settings.ModelUnitSystem = r.UnitSystem.Feet
    for name in ("Site", "Building"):
        layer = r.Layer()
        layer.Name = name
        m.Layers.Add(layer)

    def on(layer, floor=None, id=None):
        a = r.ObjectAttributes()
        a.LayerIndex = layer
        if floor:
            a.SetUserString(FLOOR_KEY, floor)
        if id:
            a.SetUserString("gordium:id", id)
        return a
    m.Objects.AddPolyline(r.Polyline([r.Point3d(x, y, 0) for x, y in LOT + LOT[:1]]), on(0))
    x0, y0, x1, y1 = HOUSE
    for k in range(2):
        m.Objects.AddBrep(r.Brep.CreateFromBoundingBox(r.BoundingBox(x0, y0, 10 * k, x1, y1, 10 * (k + 1))),
                          on(1, f"{k + 1};10", f"floor {k + 1}"))
    xa, xb, xm, base, lo, ridge = x0 - 1.5, x1 + 1.5, (x0 + x1) / 2, 20, 20.5, 30
    mesh = r.Mesh()
    for p in [(xa, y0, base), (xb, y0, base), (xb, y1, base), (xa, y1, base), (xa, y0, lo), (xb, y0, lo),
              (xb, y1, lo), (xa, y1, lo), (xm, y0, ridge), (xm, y1, ridge)]:
        mesh.Vertices.Add(*p)
    for f in [(0, 3, 2, 1), (0, 4, 7, 3), (1, 2, 6, 5), (4, 8, 9, 7), (8, 5, 6, 9),
              (0, 1, 5), (0, 5, 8), (0, 8, 4), (3, 7, 9), (3, 9, 6), (3, 6, 2)]:
        mesh.Faces.AddFace(*f)
    m.Objects.AddMesh(mesh, on(1, id="roof"))
    m.Objects.AddBrep(r.Brep.CreateFromBoundingBox(r.BoundingBox(30, 90, 0, 54, 114, 12)), on(1, id="garage"))
    m.Write(str(path), 8)
    return path


def test_a_real_rhino_model_with_a_roof_solid_and_a_garage(tmp_path):
    """P1's house and A1's garage drawn in a .3dm (floor blocks as solids marked as Gordium's floors, the roof as a
    closed mesh, the garage as a solid) and checked from the file, as the Rhino command does: the same answers."""
    path = _model_with_roof_and_garage(tmp_path / "pitched.3dm")
    res = check(path, {**FACTS, "accessory_buildings": ["garage"]})
    h = res["measurements"]["building_height"]
    assert {r["named"]["height_of_building#1"]: r["value"] for r in h["readings"]} == {
        "lowest_eave": 25.0, "drip_edge": 25.25, "wall_plate": 25.681818}
    for rule in ("R-1b.height", "R-1b.accessory_buildings", "R-1b.yard_projections", "R-1b.front_yard"):
        assert status(res, rule) == present.COMPLIES, rule
    assert res["measurements"]["side_yard_smaller_eaves"]["value"] == 13.5        # 15 − 1.5
    # coverage: house 1,200 + garage 576 = 1,776 with the eaves left out; 1,320 + 576 = 1,896 counted in full:
    # over 1,800 under that reading only, so it needs review, naming it
    cover = rows(res, "R-1b.lot_coverage")[0]
    assert cover["status"] == present.REVIEW and "eaves counted" in cover["reason"]


@pytest.mark.parametrize("rule", ["R-1b.yard_projections", "R-1b.accessory_buildings"])
def test_the_new_rules_add_nothing_to_the_starting_envelope(rule):
    """The envelope is the walls' room; eaves and accessory buildings never shrink it (no 'can't read' note)."""
    res = run(floors(*HOUSE, 2))
    assert not any(rule in n for n in res["envelope"]["notes"])
    assert res["envelope"]["outline"]


# ---- review round 1 pins ---------------------------------------------------------------------------------------

def test_a_story_cantilevered_beside_a_roof_solid_is_part_of_the_building_never_an_eave():
    """Round 1, P0 (a false pass). Floors 1-2 at 15..45 x 26..70; a third floor block (z 20-30) at 15..45 x
    24.5..36, reaching 1.5 ft toward the street; a gable roof solid on floor 2 over y 36..70. The third floor is
    a story (yards_to_nearest_part: cantilevered floors count): front yard 24.5 < 25, does not comply. Coverage
    still counts it: 30 × 44 + 30 × 1.5 = 1,365 sf (the roof has no overhang, so no eave reading)."""
    third = prism(rect(15, 24.5, 45, 36), 20, 30, "floor 3", floor=10.0)
    res = run(floors(15, 26, 45, 70, 2) + [third, roof(15, 36, 45, 70, 20, 33, 0.0, 0.5)])
    assert res["measurements"]["front_yard"]["value"] == 24.5
    assert status(res, "R-1b.front_yard") == present.FAILS
    assert res["measurements"]["building_area"]["value"] == 1365.0


def test_a_story_cantilevered_beside_an_overhanging_roof_solid_stays_in_every_coverage_reading():
    """The same, with the roof reaching 1.5 ft past the side walls: every eave reading still counts the
    cantilevered floor; eaves left out: 30 × 44 + 30 × 1.5 = 1,365 sf."""
    third = prism(rect(15, 24.5, 45, 36), 20, 30, "floor 3", floor=10.0)
    res = run(floors(15, 26, 45, 70, 2) + [third, roof(15, 36, 45, 70, 20, 33, 1.5, 0.5)])
    area = {r["named"].get("building_area#1", "story"): r["value"]
            for r in res["measurements"]["building_area"]["readings"]}
    assert area["eaves_not_counted"] == 1365.0
    assert res["measurements"]["front_yard"]["value"] == 24.5


def test_a_tower_standing_on_the_roofs_base_past_the_walls_stays_part_of_the_building():
    """Round 2 rebuild, so it reaches the eave code: the gable roof solid covers all of floor 2 and has real eaves
    (1 ft past the side walls, proven: no fascia); a flat-roofed tower (a plain solid) stands on floor 2 beside
    it, reaching 2 ft past the front wall. The tower is never an eave: the front yard is read to it, 30 − 2 = 28
    (and, since it isn't a Gordium floor block, also to the walls at the ground)."""
    tower = prism(rect(20, 28, 28, 36), 20, 34, "tower")
    res = run(floors(*HOUSE, 2) + [roof(*HOUSE, 20, 30, 1.0, 0), tower])
    m = res["measurements"]
    assert any("building_area#1" in (r.get("named") or {}) for r in m["building_area"]["readings"])   # eaves exist
    assert min(r["value"] for r in m["front_yard"]["readings"] or [m["front_yard"]]) == 28.0
    assert m["front_yard_eaves"]["value"] == 28.0
    assert m["side_yard_smaller"]["value"] == 15.0 and m["side_yard_smaller_eaves"]["value"] == 14.0


def gable_story(x0, y0, x1, y1, z0, eave, ridge, id="upper"):
    """A story and its gable drawn as ONE plain solid (not a Gordium floor block): walls z0..eave, a ridge along
    y over the middle, no overhang."""
    xm = (x0 + x1) / 2
    faces = [[(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
             [(x0, y0, z0), (x0, y1, z0), (x0, y1, eave), (x0, y0, eave)],
             [(x1, y0, z0), (x1, y1, z0), (x1, y1, eave), (x1, y0, eave)],
             [(x0, y0, eave), (xm, y0, ridge), (xm, y1, ridge), (x0, y1, eave)],
             [(xm, y0, ridge), (x1, y0, eave), (x1, y1, eave), (xm, y1, ridge)],
             [(x0, y0, z0), (x1, y0, z0), (x1, y0, eave), (xm, y0, ridge), (x0, y0, eave)],
             [(x0, y1, z0), (x1, y1, z0), (x1, y1, eave), (xm, y1, ridge), (x0, y1, eave)]]
    return {"id": id, "faces": [{"points": [list(p) for p in f]} for f in faces], "problems": []}


# ---- review round 2: nothing is left out of the building unless proven an eave ---------------------------------

def test_a_story_and_its_gable_in_one_solid_cantilevering_past_floor_1_is_never_an_eave():
    """Round 2, P0 (a false pass on 3db8e70: front yard 26.0, complies). Floor 1 a Gordium floor block at
    15..45 x 26..70; the second story and its gable one plain solid at 15..45 x 24.5..70 (walls z 10-20, ridge 30).
    Past floor 1 the solid's walls reach down to z 10, far below its roof edge (20): a story, not an eave. The
    front yard is read to it, 24.5 < 25: never complies."""
    res = run([prism(rect(15, 26, 45, 70), 0, 10, "floor 1", floor=10.0), gable_story(15, 24.5, 45, 70, 10, 20, 30)])
    front = res["measurements"]["front_yard"]
    assert min(r["value"] for r in front["readings"] or [front]) == 24.5
    assert status(res, "R-1b.front_yard") != present.COMPLIES
    assert res["measurements"]["building_area"]["value"] == 30 * 45.5          # all of it, seen from above


def test_a_dormer_on_floor_2_reaching_past_the_front_wall_counts():
    """A dormer block (a plain solid) on floor 2 beside the roof solid, 1 ft past the front wall: 30 − 1 = 29."""
    dormer = prism(rect(25, 29, 32, 34), 20, 26, "dormer")
    res = run(floors(*HOUSE, 2) + [roof(*HOUSE, 20, 30, 1.0, 0), dormer])
    front = res["measurements"]["front_yard"]
    assert min(r["value"] for r in front["readings"] or [front]) == 29.0


def test_a_bay_window_and_a_balcony_touching_the_house_count():
    """A bay window (a solid from 3 to 12 ft, 2 ft deep) and a balcony slab (10 to 10.5 ft, 3 ft deep) touching
    the front wall: part of the building (§325-18A; the balcony projects more than 2 ft): front 30 − 3 = 27; both
    counted in coverage: 1,200 + 2 × 8 + 3 × 6 = 1,234 sf."""
    bay = prism(rect(18, 28, 26, 30), 3, 12, "bay")
    balcony = prism(rect(32, 27, 38, 30), 10, 10.5, "balcony")
    res = run(floors(*HOUSE, 2) + [roof(*HOUSE, 20, 30, 0.0, 0), bay, balcony])
    assert res["measurements"]["front_yard"]["value"] == 27.0
    assert res["measurements"]["building_area"]["value"] == 1234.0


def test_a_roof_that_doesnt_stand_on_the_floors_counts_whole():
    """A roof solid floating 1 ft above floor 2 (not standing on it) and reaching 1 ft past every wall: it
    touches the house in plan, so it is part of it, and nothing proves its overhang an eave: the yards are to its
    edge: front 30 − 1 = 29."""
    floating = roof(14, 29, 46, 71, 21, 31, 0.0, 0)
    res = run(floors(*HOUSE, 2) + [floating])
    front = res["measurements"]["front_yard"]
    assert min(r["value"] for r in front["readings"] or [front]) == 29.0


def test_a_roof_on_a_roof_never_drops_the_lower_roof():
    """A second gable roof solid standing on the first one's ridge level, both on the house: the lower roof (on
    the floors, no overhang) is a part the upper one stands on, so nothing of it is ever an eave; the front yard
    is at most the floors' 30."""
    low = roof(*HOUSE, 20, 30, 0.0, 0, id="roof 1")
    high = roof(20, 35, 40, 65, 30, 36, 0.5, 0, id="roof 2")
    res = run(floors(*HOUSE, 2) + [low, high])
    front = res["measurements"]["front_yard"]
    assert max(r["value"] for r in front["readings"] or [front]) <= 30.0
    assert res["measurements"]["building_area"]["value"] == 1200.0 or any(
        r["value"] >= 1200.0 for r in res["measurements"]["building_area"]["readings"])


def test_a_hip_roof_solid_with_eaves_all_round_is_a_proven_eave():
    """A hip roof solid on floor 2: soffit at 20 reaching 1 ft past every wall, sloping from its edge (20) to a
    point at 30, nothing below its edge: proven eaves. Yards to the walls (front 30), eaves 1 ft into them
    (front 29)."""
    x0, y0, x1, y1 = HOUSE
    e = [(x0 - 1, y0 - 1), (x1 + 1, y0 - 1), (x1 + 1, y1 + 1), (x0 - 1, y1 + 1)]
    apex = [(x0 + x1) / 2, (y0 + y1) / 2, 30]
    hip = {"id": "hip", "problems": [], "faces": [{"points": [[x, y, 20] for x, y in e]}] +
           [{"points": [[*e[i], 20], [*e[(i + 1) % 4], 20], apex]} for i in range(4)]}
    res = run(floors(*HOUSE, 2) + [hip])
    m = res["measurements"]
    assert (m["front_yard"]["value"], m["front_yard_eaves"]["value"]) == (30.0, 29.0)


def test_an_answer_with_no_reading_to_the_eave_question_replaces_every_reading(monkeypatch):
    """Round 2, P3: the City answers height_of_building's open eave question without naming a reading: every
    reading is replaced, and the code can't follow the answer, so the height stops (needs review), never the
    readings shown as still open. The same for the eave coverage question."""
    real = interpretations.research_entries

    def answered(jurisdiction):
        entries = copy.deepcopy(real(jurisdiction))
        for where, e in entries:
            if where.endswith(" height_of_building") or where.endswith(" building_area"):
                q = e["open_questions"][0]
                e["answers"] = [{"question": q, "answer": "We decide case by case.",
                                 "answered_by": "the City zoning office", "answered_on": "2026-11-01"}]
        return entries
    monkeypatch.setattr(interpretations, "research_entries", answered)
    interpretations.clear_cache()
    try:
        res = run(floors(*HOUSE, 2) + [roof(*HOUSE, 20, 30, 1.5, 0)])
        h, area = res["measurements"]["building_height"], res["measurements"]["building_area"]
        assert h["value"] is None and h["readings"] == [] and status(res, "R-1b.height") == present.REVIEW
        assert area["value"] is None and area["readings"] == []
    finally:
        monkeypatch.undo()
        interpretations.clear_cache()


def test_a_roof_drawn_in_one_solid_with_its_walls_never_drops_its_overhang_from_the_yards():
    """One solid: walls 12..42 to 20 ft, the roof reaching 2 ft past them. Its overhang can't be told from a
    story under the same roof, so it counts as the building (12 − 2 = 10 to the overhang); the walls at the
    ground (12) are the other reading."""
    walls = prism(rect(12, 30, 42, 70), 0, 20, "house")
    faces = [f for f in walls["faces"] if not all(p[2] == 20 for p in f["points"])]
    faces += [{"points": [[10, 30, 19], [27, 30, 30], [27, 70, 30], [10, 70, 19]]},
              {"points": [[27, 30, 30], [44, 30, 19], [44, 70, 19], [27, 70, 30]]}]
    res = run([{"id": "house", "faces": faces, "problems": []}])
    side = res["measurements"]["side_yard_smaller"]
    assert side["value"] is None and sorted(r["value"] for r in side["readings"]) == [10.0, 12.0]


def test_an_answer_that_picks_another_reading_replaces_gordiums_reading(monkeypatch):
    """Round 1, P2. The City answers the pitched-roof question differently from the finding (reading
    `to_the_ridge`, which the measuring has no code for): Gordium's midpoint reading is never applied or shown;
    the height stops (needs review), never a guess."""
    real = interpretations.research_entries

    def answered(jurisdiction):
        entries = copy.deepcopy(real(jurisdiction))
        for where, e in entries:
            if where.endswith(" height_of_building"):
                f = next(f for f in e["findings"] if f["id"] == "pitched_roof_midpoint")
                e["answers"] = [{"question": f["question"], "answer": "To the ridge.", "reading": "to_the_ridge",
                                 "answered_by": "the City zoning office", "answered_on": "2026-11-01"}]
        return entries
    monkeypatch.setattr(interpretations, "research_entries", answered)
    interpretations.clear_cache()
    try:
        res = run(floors(*HOUSE, 2) + [roof(*HOUSE, 20, 30, 1.5, 0.5)])
        h = res["measurements"]["building_height"]
        assert h["value"] is None and h["readings"] == [] and "no longer have" in h["reason"]
        assert "Gordium's reading" not in (rows(res, "R-1b.height")[0]["reason"] or "")
        assert status(res, "R-1b.height") == present.REVIEW
    finally:
        monkeypatch.undo()
        interpretations.clear_cache()


def test_corner_lot_front_and_rear_rows_dont_cite_the_side_yard_reading():
    """Round 1, P3: the Column 13 reading is about the side yard only."""
    res = run(floors(10, 25, 35, 65, 2), **CORNER)
    for rule in ("R-1b.front_yard", "R-1b.rear_yard"):
        assert "Column 13" not in (rows(res, rule)[0]["reason"] or ""), rule
    assert "Column 13" in rows(res, "R-1b.side_yards")[0]["reason"]
