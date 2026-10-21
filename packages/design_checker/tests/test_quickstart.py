"""The QUICKSTART's "Test it yourself" expectations, checked in code (apps/rhino_plugin/QUICKSTART.md): the sample
project (106 Ithaca Rd, a 73'-0" x 90'-0" tax-map lot), the starting house GordiumStart draws, and each test's edit
made the way the guide says, with the numbers the guide promises. If a number in the guide changes, this fails."""
import copy

import pytest

from design_checker import present
from design_checker.check import check_site, sample_site, start
from envelope_builder.start import floor_solids

SAMPLE = sample_site()


def _site(floors, extra=()):
    lot = SAMPLE["lot"]
    n = len(lot)
    edges = [{"points": [list(lot[i]) + [0.0], list(lot[(i + 1) % n]) + [0.0]], "curved": False} for i in range(n)]
    return {"units": "ft", "lot": {"id": "lot", "edges": edges}, "buildings": floor_solids(floors) + list(extra),
            "problems": []}


@pytest.fixture(scope="module")
def house(tmp_path_factory):
    import rhino3dm as r
    m = r.File3dm()
    m.Settings.ModelUnitSystem = r.UnitSystem.Feet
    layer = r.Layer()
    layer.Name = "Site"
    m.Layers.Add(layer)
    attrs = r.ObjectAttributes()
    attrs.LayerIndex = 0
    m.Objects.AddPolyline([r.Point3d(x, y, 0) for x, y in SAMPLE["lot"] + SAMPLE["lot"][:1]], attrs)
    path = tmp_path_factory.mktemp("qs") / "lot.3dm"
    m.Write(str(path), 8)
    # the MVP: flat ground assumed, at the lot level, finished (rhino_logic.ground_facts with FLAT_GROUND)
    facts = {**SAMPLE["facts"], "address": SAMPLE["address"], "grade_is": "finished", "ground_is_flat": True,
             "grade_elevation": 0.0, "ground_assumed": "flat"}
    return start(path, facts), facts


def _check(floors, facts, extra=(), extras=None, **over):
    return {i["name"]: i for i in check_site(_site(floors, extra), {**facts, **over}, extras=extras)["view"]["items"]}


def _moved(floors, dx=0.0, dy=0.0, which=None):
    out = copy.deepcopy(floors)
    for k, f in enumerate(out):
        if which is None or k == which:
            f["outline"] = [[x + dx, y + dy] for x, y in f["outline"]]
    return out


def test_the_starting_house_on_the_sample_lot(house):
    got, facts = house
    xs = [p[0] for p in got["floors"][0]["outline"]]
    ys = [p[1] for p in got["floors"][0]["outline"]]
    assert (min(xs), max(xs), min(ys), round(max(ys) * 12)) == (12.0, 61.0, 27.0, 706)     # 49'-0" x 31'-10"
    assert got["floors"][-1]["top"] == 35.0 and len(got["floors"]) == 3
    items = _check(got["floors"], facts)
    assert (items["Front yard"]["proposed"], items["Side yard, East"]["proposed"], items["Rear yard"]["proposed"]) \
        == ("27'-0\"", "12'-0\"", "31'-2\"")
    height = items["Building height"]
    assert (height["proposed"], height["status"], height["margin"]) == ("35'-0\"", present.COMPLIES, "at limit")
    assert height["note"] == "assuming flat ground" and items["Stories"]["status"] == present.COMPLIES
    assert items["Lot coverage"]["proposed"] == "23.8%" and items["Lot coverage"]["status"] == present.COMPLIES


def test_1_on_screen_labels_are_off_until_ticked():
    from design_checker import rhino_logic as logic
    assert logic.labels_on({}) is False and logic.labels_on({"show_labels": True}) is True
    assert logic.yard_label_shown(False, present.FAILS) and not logic.yard_label_shown(False, present.COMPLIES)


def test_2_move_back_5_ft(house):
    got, facts = house
    items = _check(_moved(got["floors"], dy=5), facts, grade_is="finished")
    assert (items["Front yard"]["proposed"], items["Rear yard"]["proposed"]) == ("32'-0\"", "26'-2\"")
    assert items["Rear yard"]["status"] == present.COMPLIES


def test_3_move_back_10_ft_the_rear_yard_fails(house):
    got, facts = house
    items = _check(_moved(got["floors"], dy=10), facts, grade_is="finished")
    rear = items["Rear yard"]
    assert (rear["status"], rear["proposed"], rear["required"], rear["margin"]) == \
        (present.FAILS, "21'-2\"", "22'-6\"", "−1'-4\"")


def test_4_pull_the_rear_wall_6_ft_coverage_fails(house):
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    top = max(p[1] for p in floors[0]["outline"])
    for f in floors:
        f["outline"] = [[x, y + 6 if y == top else y] for x, y in f["outline"]]
    items = _check(floors, facts, grade_is="finished")
    assert items["Lot coverage"]["status"] == present.FAILS and items["Lot coverage"]["proposed"] == "28.3%"


def test_5_raise_the_roof_3_ft_fails_both_ways(house):
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    floors[-1]["top"] += 3
    h = _check(floors, facts, grade_is="finished")["Building height"]
    assert h["status"] == present.FAILS and h["proposed"] == "38'-0\""
    assert "Front yard 27'-0\", needs ≥ 28'-0\"" in h["reason"]


def test_6_widen_4_ft_to_the_east(house):
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    east = max(p[0] for p in floors[0]["outline"])
    for f in floors:
        f["outline"] = [[x + 4 if x == east else x, y] for x, y in f["outline"]]
    items = _check(floors, facts, grade_is="finished")
    side = items["Side yard, East"]
    assert (side["status"], side["proposed"], side["margin"]) == (present.FAILS, "8'-0\"", "−2'-0\"")
    assert items["Lot coverage"]["status"] == present.FAILS and items["Lot coverage"]["proposed"] == "25.7%"


def test_8_a_garage_not_on_the_building_layer(house):
    got, facts = house
    items = _check(got["floors"], facts, extras={"not_included": ["garage"], "touching": []}, grade_is="finished")
    assert items["Objects on the lot not included"]["status"] == present.REVIEW
    assert items["Lot coverage"]["status"] == present.REVIEW


def test_9_one_floor_moved_on_its_own(house):
    got, facts = house
    items = _check(_moved(got["floors"], dx=3, which=1), facts, grade_is="finished")
    assert items["Stories"]["status"] == present.REVIEW and "floors misaligned" in items["Stories"]["reason"]


def test_10_the_height_bonus_done_right(house):
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    floors[-1]["top"] += 3                                         # 38'-0": every yard must be 3 ft larger
    # on a tax-map lot, 2 ft more than that (the worst case): 3 ft back (front 30'-0" ≥ 28 + 2) and 3 ft in on each
    # side (15'-0" ≥ 13 + 2); the rear, 28'-2", is at worst 26'-2" ≥ 23 + 3 (the lot 2 ft deeper)
    for f in floors:
        f["outline"] = [[x + (3 if x == 12.0 else -3 if x == 61.0 else 0), y + 3] for x, y in f["outline"]]
    items = _check(floors, facts, grade_is="finished")
    assert items["Building height"]["status"] == present.COMPLIES and items["Building height"]["required"] == "38'-6\""
    assert (items["Front yard"]["required"], items["Front yard"]["margin"]) == ("28'-0\"", "+2'-0\"")
    assert items["Side yard, West"]["required"] == "13'-0\"" and items["Front yard"]["status"] == present.COMPLIES


def test_11_delta_in_words(house):
    from design_checker import rhino_logic as logic
    got, facts = house
    front = _check(_moved(got["floors"], dy=5), facts)["Front yard"]
    rear = _check(_moved(got["floors"], dy=10), facts)["Rear yard"]
    assert logic.delta_text(front["margin"]) == "+7'-0\" to spare"
    assert logic.delta_text(rear["margin"]) == "−1'-4\" short"


def test_spot_grades_when_flat_ground_is_switched_off(house):
    """Not in the guide while the MVP assumes flat ground: the spot-grade path behind the switch still works."""
    got, facts = house
    spots = [[36.5, 26.5, 0.0], [36.5, 59.4, 0.0], [11.5, 43.0, 0.0], [61.5, 43.0, 0.0]]
    grade = {k: v for k, v in facts.items() if k not in ("ground_is_flat", "grade_elevation", "ground_assumed")}
    on = _check(got["floors"], grade, grade_is="finished", grade_from="finished_spots", grade_points=spots)
    assert on["Building height"]["status"] == present.COMPLIES
    off = _check(_moved(got["floors"], dy=5), grade, grade_is="finished", grade_from="finished_spots",
                 grade_points=spots)
    assert off["Building height"]["status"] == present.REVIEW
    assert "spot grades no longer at the building's walls" in off["Building height"]["reason"]


def test_12_a_corner_lot_makes_the_yards_wait(house):
    got, facts = house
    items = _check(got["floors"], facts, grade_is="finished", corner_lot=True)
    assert items["Front yard"]["status"] == present.REVIEW


def test_13_on_a_survey_the_starting_house_goes_to_the_limits(house, tmp_path):
    got, facts = house
    surveyed = {**facts, "lot_surveyed": True, "grade_is": "finished"}
    import rhino3dm as r
    m = r.File3dm()
    m.Settings.ModelUnitSystem = r.UnitSystem.Feet
    layer = r.Layer()
    layer.Name = "Site"
    m.Layers.Add(layer)
    attrs = r.ObjectAttributes()
    attrs.LayerIndex = 0
    m.Objects.AddPolyline([r.Point3d(x, y, 0) for x, y in SAMPLE["lot"] + SAMPLE["lot"][:1]], attrs)
    m.Write(str(tmp_path / "lot.3dm"), 8)
    full = start(tmp_path / "lot.3dm", surveyed)
    xs = [p[0] for p in full["floors"][0]["outline"]]
    assert max(xs) - min(xs) == 53.0                                  # 73 − 2 × 10: 53'-0" x 30'-11"
    items = _check(full["floors"], surveyed)
    assert items["Side yard, West"]["margin"] == "at limit" and items["Side yard, West"]["status"] == present.COMPLIES
