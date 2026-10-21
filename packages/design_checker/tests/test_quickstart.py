"""The QUICKSTART's "Test it yourself" expectations, checked in code (apps/rhino_plugin/QUICKSTART.md): the sample
project (106 Ithaca Rd, a 73'-0" x 90'-0" tax-map lot), the starting house GordiumStart draws, and each test's edit
made the way the guide says, with the numbers the guide promises. The numbers are read from the guide itself
(said() below), so if a number in the guide changes, this fails."""
import copy
import re

import pytest

from design_checker import present
from design_checker.check import check_site, sample_site, start
from envelope_builder.start import floor_solids
from rule_format.rulebook import REPO

SAMPLE = sample_site()
GUIDE = (REPO / "apps/rhino_plugin/QUICKSTART.md").read_text(encoding="utf-8")
GUIDE = GUIDE.split("## Test it yourself", 1)[1].split("\n## ", 1)[0]
LEN = r"(\d+'-\d+\")"                        # a length as the guide writes it: 27'-0"


def said(pattern: str) -> tuple:
    """The numbers the guide's "Test it yourself" section says, by a pattern of its words (spaces match any
    run of spaces or line breaks). Fails if the guide no longer says it."""
    m = re.search(pattern.replace(" ", r"\s+"), GUIDE, re.S)
    assert m, f"QUICKSTART no longer says: {pattern}"
    return m.groups()


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
    wide, deep, tall, floors = said("The starting house is " + LEN + " wide and " + LEN + " deep, " + LEN
                                    + r" tall, in (\w+) floors")
    assert (present.feet_inches(max(xs) - min(xs)), present.feet_inches(max(ys) - min(ys))) == (wide, deep)
    assert present.feet_inches(got["floors"][-1]["top"]) == tall
    assert len(got["floors"]) == {"two": 2, "three": 3, "four": 4}[floors]
    items = _check(got["floors"], facts)
    front, = said("front yard " + LEN + r" \(needs")
    side, = said("side yards " + LEN + r" \(need")
    rear, = said("rear yard " + LEN + r" \(needs")
    coverage, = said(r"coverage (\d+\.\d%) \(the limit")
    assert (items["Front yard"]["proposed"], items["Side yard, East"]["proposed"], items["Rear yard"]["proposed"]) \
        == (front, side, rear)
    height, stories = said("Building height " + LEN + r" and Stories (\d) comply, at the limit, each saying "
                           r'"assuming flat ground"')
    h = items["Building height"]
    assert (h["proposed"], h["status"], h["margin"], h["note"]) == (height, present.COMPLIES, "at limit",
                                                                     "assuming flat ground")
    assert items["Stories"]["proposed"] == stories and items["Stories"]["status"] == present.COMPLIES
    assert items["Lot coverage"]["proposed"] == coverage and items["Lot coverage"]["status"] == present.COMPLIES


def test_1_on_screen_labels_are_off_until_ticked():
    from design_checker import rhino_logic as logic
    said(r"Tick Show on-screen labels\*\* in the panel: each yard's label")
    assert logic.labels_on({}) is False and logic.labels_on({"show_labels": True}) is True
    assert logic.yard_label_shown(False, present.FAILS) and not logic.yard_label_shown(False, present.COMPLIES)


def test_2_move_back_5_ft(house):
    got, facts = house
    dy, front, rear = said(r"Move the house (\d+) ft back \(away from the street\).\*\* Front yard " + LEN
                           + ", rear yard " + LEN)
    items = _check(_moved(got["floors"], dy=float(dy)), facts, grade_is="finished")
    assert (items["Front yard"]["proposed"], items["Rear yard"]["proposed"]) == (front, rear)
    assert items["Rear yard"]["status"] == present.COMPLIES


def test_3_move_back_10_ft_the_rear_yard_fails(house):
    got, facts = house
    dy, proposed, required, margin, words = said(
        r"Move it (\d+) ft back instead.\*\* Rear yard " + LEN + " against " + LEN
        + r" required: \*\*does not comply, (−\d+'-\d+\")\*\* as drawn. On this tax-map lot its Delta reads "
        r'"(up to \d+\'-\d+" short)"')
    items = _check(_moved(got["floors"], dy=float(dy)), facts, grade_is="finished")
    rear = items["Rear yard"]
    assert (rear["status"], rear["proposed"], rear["required"], rear["margin"], rear["delta"]) == \
        (present.FAILS, proposed, required, margin, " ".join(words.split()))


def test_4_pull_the_rear_wall_6_ft_coverage_fails(house):
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    top = max(p[1] for p in floors[0]["outline"])
    feet, coverage = said(r"pull the rear wall (\d+) ft back.*?Lot coverage (\d+\.\d%)")
    for f in floors:
        f["outline"] = [[x, y + float(feet) if y == top else y] for x, y in f["outline"]]
    items = _check(floors, facts, grade_is="finished")
    assert items["Lot coverage"]["status"] == present.FAILS and items["Lot coverage"]["proposed"] == coverage


def test_5_raise_the_roof_3_ft_fails_both_ways(house):
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    feet, height, needs = said(r"raise the roof (\d+) ft\*\* \(the top face of Floor 3\). Building height " + LEN
                               + r'.*?"(Front yard \d+\'-\d+", needs ≥ \d+\'-\d+")"')
    floors[-1]["top"] += float(feet)
    h = _check(floors, facts, grade_is="finished")["Building height"]
    assert h["status"] == present.FAILS and h["proposed"] == height
    assert " ".join(needs.split()) in h["reason"]                 # the guide wraps its lines


def test_6_widen_4_ft_to_the_east(house):
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    east = max(p[0] for p in floors[0]["outline"])
    feet, proposed, margin, coverage, worst = said(
        r"widen the house (\d+) ft to the east\*\* \(the east face\). Side yard, East " + LEN
        + r": \*\*does not comply, (−\d+'-\d+\")\*\*, and lot coverage (\d+\.\d%) needs review: at the tax map's"
        r" worst case it would be (\d+\.\d%)")
    for f in floors:
        f["outline"] = [[x + float(feet) if x == east else x, y] for x, y in f["outline"]]
    items = _check(floors, facts, grade_is="finished")
    side = items["Side yard, East"]
    assert (side["status"], side["proposed"], side["margin"]) == (present.FAILS, proposed, margin)
    assert items["Lot coverage"]["status"] == present.REVIEW and items["Lot coverage"]["proposed"] == coverage
    assert f"at worst {worst}" in items["Lot coverage"]["reason"]


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
    feet, required, front_required, front_margin = said(
        r"raise the roof (\d+) ft \(\d+'-\d+\"\).*?Building height complies\s+against " + LEN
        + r"; the Front yard row shows " + LEN + r" required, (\+\d+'-\d+\")")
    assert feet == "3"                        # the edits below are the guide's: 3 ft back and 3 ft in on each side
    floors[-1]["top"] += 3                                         # 38'-0": every yard must be 3 ft larger
    # on a tax-map lot, 2 ft more than that (the worst case): 3 ft back (front 30'-0" ≥ 28 + 2) and 3 ft in on each
    # side (15'-0" ≥ 13 + 2); the rear, 29'-9", is at worst 27'-9" ≥ 24 + 1.5 (the lot 4 ft deeper: 25'-6")
    for f in floors:
        f["outline"] = [[x + (3 if x == 12.0 else -3 if x == 61.0 else 0), y + 3] for x, y in f["outline"]]
    items = _check(floors, facts, grade_is="finished")
    assert items["Building height"]["status"] == present.COMPLIES and items["Building height"]["required"] == required
    assert (items["Front yard"]["required"], items["Front yard"]["margin"]) == (front_required, front_margin)
    assert items["Side yard, West"]["required"] == "13'-0\"" and items["Front yard"]["status"] == present.COMPLIES


def test_11_delta_in_words(house):
    from design_checker import rhino_logic as logic
    got, facts = house
    front_words, rear_words, survey_words = said(
        r'after test 2 the Front yard row reads "(at least \d+\'-\d+" to spare)"; after test 3 the Rear yard row '
        r'reads "(up to \d+\'-\d+" short)".*?With a survey it reads the margin itself, such as "(\+\d+\'-\d+" to spare)"')
    back2, = said(r"Move the house (\d+) ft back \(away from the street\)")
    back3, = said(r"Move it (\d+) ft back instead")
    front = _check(_moved(got["floors"], dy=float(back2)), facts)["Front yard"]
    rear = _check(_moved(got["floors"], dy=float(back3)), facts)["Rear yard"]
    front_words, rear_words, survey_words = (" ".join(w.split()) for w in (front_words, rear_words, survey_words))
    assert (front["delta"], rear["delta"]) == (front_words, rear_words)              # the guide wraps its lines
    surveyed = _check(_moved(got["floors"], dy=float(back2)), facts, lot_surveyed=True)["Front yard"]
    assert surveyed["delta"] == survey_words == logic.delta_text(surveyed["margin"])


def test_spot_grades_when_flat_ground_is_switched_off(house):
    """Not in the guide while the MVP assumes flat ground: the spot-grade path behind the switch still works."""
    got, facts = house
    o = got["floors"][0]["outline"]
    x0, x1 = min(p[0] for p in o), max(p[0] for p in o)
    y0, y1 = min(p[1] for p in o), max(p[1] for p in o)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2               # one point just outside each wall, as the guide says
    spots = [[mx, y0 - 0.5, 0.0], [mx, y1 + 0.5, 0.0], [x0 - 0.5, my, 0.0], [x1 + 0.5, my, 0.0]]
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
    wide, deep = said("a new starting house goes exactly to the limits: " + LEN + " × " + LEN)
    ys = [p[1] for p in full["floors"][0]["outline"]]
    assert (present.feet_inches(max(xs) - min(xs)), present.feet_inches(max(ys) - min(ys))) == (wide, deep)
    items = _check(full["floors"], surveyed)
    assert items["Side yard, West"]["margin"] == "at limit" and items["Side yard, West"]["status"] == present.COMPLIES


def test_the_quickstart_test_reads_the_guide():
    """eval-integrity P2: the numbers were typed into this test, so changing the guide (say "coverage 99.9%")
    left every test passing. A guide that no longer says a number fails said()."""
    import pytest as _p
    global GUIDE
    real = GUIDE
    try:
        GUIDE = re.sub(r"coverage \d+\.\d% \(the limit", "coverage 99.9% (the limit", real)
        assert said(r"coverage (\d+\.\d%) \(the limit") == ("99.9%",)
        GUIDE = re.sub(r"rear yard \d+'-\d+\" \(needs", "rear yard twenty (needs", real)
        with _p.raises(AssertionError, match="QUICKSTART no longer says"):
            said("rear yard " + LEN + r" \(needs")
    finally:
        GUIDE = real
