"""The QUICKSTART's "Test it yourself" expectations, checked in code (apps/rhino_plugin/QUICKSTART.md): the sample
project (106 Ithaca Rd as the State tax map draws it, placed as the address lookup places it), the starting house
GordiumStart draws, and each test's edit made the way the guide says, with the numbers the guide promises. The numbers are read from the guide itself
(said() below), so if a number in the guide changes, this fails."""
import copy
import re

import pytest

from design_checker import present
from design_checker import rhino_logic as logic
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


# PR 18 reads every reading of which of 106's lot lines are side and rear lines (its real tax-map outline, cleaned
# within 0.25 ft: 15 lines -> 9): the starting house is legal under every one, 51'-4" x 29'-8" (was 35'-11" x
# 37'-4"); the guide's numbers were re-derived for it once #18 landed (the Rhino job, 2026-10-28).
RANGE = r"(\d+'-\d+(?: \d/\d)?\"(?: to \d+'-\d+(?: \d/\d)?\")?)"   # a length, or a range: 24'-11 7/8" to 26'-6 1/8"


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
    # the MVP: flat ground assumed, at the lot level, finished (rhino_logic.ground_facts with FLAT_GROUND), with
    # the fall the lookup finds for 106 (its recorded USGS answer: test_lookup_box pins 14.2 ft)
    facts = {**SAMPLE["facts"], "address": SAMPLE["address"], "grade_is": "finished", "ground_is_flat": True,
             "grade_elevation": 0.0, "ground_assumed": "flat", "ground_fall": 14.2}
    return start(path, facts), facts


def _check(floors, facts, extra=(), extras=None, **over):
    return {i["name"]: i for i in check_site(_site(floors, extra), {**facts, **over}, extras=extras)["view"]["items"]}


def _moved(floors, dx=0.0, dy=0.0, which=None):
    out = copy.deepcopy(floors)
    for k, f in enumerate(out):
        if which is None or k == which:
            f["outline"] = [[x + dx, y + dy] for x, y in f["outline"]]
    return out


def _left_side(items):
    """The side yard on the left, seen from the street (the street is along the bottom of Top view): the side yard
    measured to the lower x. By position, not by its compass name (named by plan north until the compass fix)."""
    sides = [i for i in items.values() if i["name"].startswith("Side yard") and i.get("points")]
    return min(sides, key=lambda i: min(p[0] for p in i["points"]))


def _regions(floors, facts, **over):
    """The plan's coloured regions: (why, status) for each."""
    plan = check_site(_site(floors), {**facts, **over})["plan"]
    return {(e["why"], e["status"]) for e in plan["encroach"]}


def _wall_out(floors, feet, side="left"):
    out = copy.deepcopy(floors)
    edge = min if side == "left" else max
    x = edge(p[0] for p in out[0]["outline"])
    for f in out:
        f["outline"] = [[px - feet if side == "left" and px == x else px + feet if side == "right" and px == x else px,
                         py] for px, py in f["outline"]]
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
    front, = said(r"front yard (\d+'-\d+(?: \d/\d)?\") \(needs")
    left, right = said(r"side yard, southwest (\d+'-\d+(?: \d/\d)?\") \(needs 10'-0\"\); northeast, "
                       r"(\d+'-\d+(?: \d/\d)?\")")
    coverage, = said(r"coverage (\d+\.\d%) \(the limit")
    sides = sorted((i for i in items.values() if i["name"].startswith("Side yard")),
                   key=lambda i: min(p[0] for p in i["points"]))
    assert (items["Front yard"]["proposed"], sides[0]["proposed"], sides[1]["proposed"]) == (front, left, right)
    assert [s["name"] for s in sides] == ["Side yard, Southwest", "Side yard, Northeast"]   # true north, as looked up
    assert items["Lot coverage"]["proposed"] == coverage and items["Lot coverage"]["status"] == present.COMPLIES
    said(r"\*\*Rear yard\*\*: which of the short lines at the back count as side lot lines")
    rear, height = items["Rear yard"], items["Building height"]
    assert rear["status"] == present.REVIEW and rear["reason"] == ("Complies under every reading, but it depends on an "
                                                                    "open question: which lot lines count as side and "
                                                                    "which as rear; confirm with the zoning office")
    said(r"\*\*Eaves into front yard\*\* waits on the same question, and on the height")
    eaves = items["Eaves into front yard"]
    assert eaves["status"] == present.REVIEW and "side and rear" in eaves["reason"] and \
        eaves["reason"].startswith("the ground falls about 14.2 ft")
    said(r"Complies under every\s+reading, but it depends on an open question: which lot lines count as side and "
         r"which as rear; confirm with the\s+zoning office")
    tall_at, stories_at, fall = said(r"\*\*Building height\*\* \((\d+'-\d+\"), at the limit\) and \*\*Stories\*\* "
                                     r"\((\d), at the limit\): the lookup found the ground falls\s+about ([\d.]+) ft")
    assert float(fall) == facts["ground_fall"]
    for row, at in ((height, tall_at), (items["Stories"], stories_at)):    # the sloped-lot fix: never a pass
        assert (row["proposed"], row["status"], row["note"]) == (at, present.REVIEW, "assuming flat ground")
    why, = said(r'neither can be decided: "(the ground falls .+? against your survey)"')
    assert " ".join(why.split()) in height["reason"] and " ".join(why.split()) in items["Stories"]["reason"]
    said("Thirteen rows need review from the start")
    stream = "New structures at least 20 ft from an inlet wall or stream bank"
    said(r"\*\*" + stream + r"\*\*: the start box's stream question was left Not answered")
    assert [i["name"] for i in items.values() if i["status"] == present.REVIEW and not i.get("use_detail")] == [
        stream, "Stories", "Building height", "Rear yard", "Eaves into front yard", "One-family occupancy",
        "Private garage: not more than three cars", *ADU_ROWS]
    assert items[stream]["reason"].startswith("say whether any inlet wall or stream bank") and \
        set(items[stream]["needs"]) == {"stream_near_lot", "stream_distance"}       # waits on the question, nothing else
    button, = said(r"Answer it with the row's \*\*(.+?)…\*\* button")
    assert button == logic.answer_words(items[stream]["needs"])
    # the garage's car limit (chart p.2 note 6): waits on the cars only; the number of garages is asked after
    garage = items["Private garage: not more than three cars"]
    said(r"\*\*Private garage: not more than three cars\*\*: the start box's garage question was left Not answered")
    assert garage["needs"] == ["garage_cars"] and garage["reason"].startswith("enter how many cars the lot's private")
    button, = said(r"Answer it with the row's\s+\*\*(Enter the cars.+?)…\*\* button")
    assert button == logic.answer_words(garage["needs"])
    for cars, status in ((3, present.COMPLIES), (4, present.REVIEW), (7, present.REVIEW)):
        decided = _check(got["floors"], facts, garage_cars=cars)["Private garage: not more than three cars"]
        assert decided["status"] == status, (cars, decided)
        assert decided["needs"] == ([] if cars == 3 else ["private_garages"]), (cars, decided)  # "then asks how many"
    assert _check(got["floors"], facts, garage_cars=4, private_garages=1)[
        "Private garage: not more than three cars"]["status"] == present.FAILS
    # the start box's ADU question (Ben, 2026-10-30): left Not answered, the six ADU rows and the occupancy row wait
    said(r"The six \*\*accessory dwelling unit\*\* rows .+? and \*\*One-family occupancy\*\*: the start box's ADU "
         r"question was\s+left Not answered")
    why, = said(r'they wait on it \("(say whether an accessory dwelling unit .+?)"\)')
    for name in (*ADU_ROWS, "One-family occupancy"):
        assert " ".join(why.split()) in items[name]["reason"] and "accessory_dwelling_unit" in items[name]["needs"]
    button, = said(r"Answer it with an ADU row's \*\*(.+?)…\*\* button")
    assert button == logic.answer_words(items[ADU_ROWS[0]]["needs"])
    said(r"\*\*No ADU on the lot\*\* and\s+the six ADU rows go")
    assert logic.yes_no_words("accessory_dwelling_unit")[0] == "No ADU on the lot"
    no = _check(got["floors"], facts, accessory_dwelling_unit=False)
    assert not set(no) & set(ADU_ROWS) and no["One-family occupancy"]["use_detail"]
    said("On a lot the lookup finds level, both comply")
    level = _check(got["floors"], facts, ground_fall=0.0)
    assert all(level[n]["status"] == present.COMPLIES for n in ("Building height", "Stories"))
    said("Lot area complies even at the tax map's worst case")
    assert items["Lot area"]["status"] == present.COMPLIES


ADU_ROWS = ["Accessory dwelling unit: at most one per parcel", "Accessory dwelling unit: at most two bedrooms",
            "Detached ADU: not in the primary front yard nor a required one",
            "Attached ADU: at most 40% of the primary structure's floor area",
            "Detached ADU: 800 sf footprint; two stories and 20 ft",
            "Detached ADU: 5 ft from the side and rear lot lines"]


def test_15_a_backyard_cottage(house):
    """A 20 x 16 x 18 ft box behind the starting house (30..50 x 64..80: 12 ft and more from the rear lot line, which
    runs at y = 92.3 to 93.2, and over 25 ft from each side), picked as a detached ADU's building."""
    import sys
    sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
    from test_measure import box
    got, facts = house
    said(r"draw a `Box` 20 × 16 × 18 ft on the Building layer behind\s+the house")
    adu = {"accessory_dwelling_unit": True, "adu_detached": True, "adu_existing_building": False, "adus_on_parcel": 1,
           "adu_bedrooms": 2, "adu_building": "cottage"}
    rows = _check(got["floors"], facts, [box(30, 64, 50, 80, 0, 18, id="cottage")], **adu)
    size, setbacks, front = rows[ADU_ROWS[4]], rows[ADU_ROWS[5]], rows[ADU_ROWS[2]]
    said(r"not nearer the street than the house:\s+complies")
    assert front["status"] == present.COMPLIES, front
    said(r"5 ft or more from the side and rear lot lines: it is, under every reading, but on this lot it "
         r"needs\s+review like the house's rear yard")
    assert setbacks["status"] == present.REVIEW and setbacks["reason"] == rows["Rear yard"]["reason"], setbacks
    footprint, = said(r"Its size \((\d+) sf footprint, 18 ft, at most 2 stories\) \*\*needs\s+review\*\* here")
    assert size["proposed"] == f"{footprint} sf" and size["status"] == present.REVIEW
    assert size["reason"].startswith("the ground falls about 14.2 ft") and "flat ground" in size["note"]
    said(r"On a lot\s+the lookup finds level it complies, and made 22 ft tall it \*\*does not comply\*\*")
    level = dict(facts, ground_fall=0.0)
    assert _check(got["floors"], level, [box(30, 64, 50, 80, 0, 18, id="cottage")], **adu)[ADU_ROWS[4]]["status"] \
        == present.COMPLIES
    assert _check(got["floors"], level, [box(30, 64, 50, 80, 0, 22, id="cottage")], **adu)[ADU_ROWS[4]]["status"] \
        == present.FAILS
    said(r"Move it in front\s+of the house: \*\*does not comply\*\*")
    assert _check(got["floors"], facts, [box(30, 5, 50, 21, 0, 18, id="cottage")], **adu)[ADU_ROWS[2]]["status"] \
        == present.FAILS


def test_1_on_screen_labels_are_off_until_ticked():
    from design_checker import rhino_logic as logic
    said(r"Tick Show on-screen labels\*\* in the panel: each yard's label")
    assert logic.labels_on({}) is False and logic.labels_on({"show_labels": True}) is True
    assert logic.yard_label_shown(False, present.FAILS) and not logic.yard_label_shown(False, present.COMPLIES)


def test_2_move_back_5_ft(house):
    got, facts = house
    dy, front = said(r"Move the house (\d+) ft back.\*\* Front yard (\d+'-\d+(?: \d/\d)?\"): complies")
    items = _check(_moved(got["floors"], dy=float(dy)), facts)
    assert (items["Front yard"]["proposed"], items["Front yard"]["status"]) == (front, present.COMPLIES)
    assert items["Rear yard"]["status"] == present.REVIEW                       # "the rear yard still needs review"


def test_3_short_only_under_some_readings_needs_review_short_under_all_fails(house):
    """A rule fails only if it fails under every reading (of the tax map's lines, and of an open question of the
    law); short under only some, it needs review (Ben, 2026-10-21)."""
    got, facts = house
    dy, proposed = said(r"Move it (\d+) ft back instead.\*\* Rear yard " + RANGE + r": \*\*needs review")
    rear = _check(_moved(got["floors"], dy=float(dy)), facts)["Rear yard"]
    assert (rear["status"], rear["proposed"]) == (present.REVIEW, proposed)
    dy, proposed, short = said(r"Now move it (\d+) ft back:\*\*\s+Rear yard\s+" + RANGE + r": \*\*does not "
                               r"comply\*\*, \"still (\d+'-\d+(?: \d/\d)?\") short under every reading\"")
    dy_fails = dy
    moved = _moved(got["floors"], dy=float(dy))
    rear = _check(moved, facts)["Rear yard"]
    assert (rear["status"], rear["proposed"]) == (present.FAILS, proposed)
    assert rear["delta"].endswith(f" short (still {short} short under every reading)"), rear["delta"]
    assert ("yard", present.FAILS) in _regions(moved, facts)                    # "the strip ... turns red"
    # short under only some readings (the tax map's slack and the back-line question): needs review, amber only
    low, high = said(r"From (\d+) to (\d+) ft back it still needs review")
    for dy in range(int(low), int(high) + 1):
        moved = _moved(got["floors"], dy=float(dy))
        rear = _check(moved, facts)["Rear yard"]
        assert rear["status"] == present.REVIEW and rear["delta"].endswith(" under another reading)"), (dy, rear["delta"])
        assert ("yard", present.FAILS) not in _regions(moved, facts), dy
        row = next(x for x in check_site(_site(moved), facts)["rows"] if x["Rule id"] == "R-1b.rear_yard")
        assert not row["Fails"], (dy, row["Provisional"])        # the checker itself: one reading set (round 2)
    first = int(said(r"From (\d+) ft back it does not comply")[0])     # the first whole foot short under every reading
    assert first == int(high) + 1 and first < int(dy_fails)
    for dy in range(first, int(dy_fails) + 1):
        rear = _check(_moved(got["floors"], dy=float(dy)), facts)["Rear yard"]
        assert rear["status"] == present.FAILS and " short (still " in rear["delta"], (dy, rear["delta"])


def test_4_pull_the_rear_wall_back_coverage_fails_on_every_tax_map_lot(house):
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    top = max(p[1] for p in floors[0]["outline"])
    feet, coverage = said(r"pull the rear wall (\d+) ft back.*?Lot coverage (\d+\.\d+%)")
    for f in floors:
        f["outline"] = [[x, y + float(feet) if y == top else y] for x, y in f["outline"]]
    items = _check(floors, facts)
    assert items["Lot coverage"]["status"] == present.FAILS and items["Lot coverage"]["proposed"] == coverage


def test_5_raise_the_roof_fails(house):
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    feet, height, short = said(r"raise the roof (\d+) ft\*\* \(the top face of Floor 3\). On this sloping lot "
                               r"Building height " + LEN + r" still\s+\*\*needs review\*\* \(the ground, as above\)\. "
                               r"On a lot the lookup finds level it \*\*does not comply\*\*, (\d+'-\d+\") over")
    floors[-1]["top"] += float(feet)
    h = _check(floors, facts)["Building height"]
    assert (h["status"], h["proposed"]) == (present.REVIEW, height)            # 14.2 ft of fall: never a fail or pass
    assert ("height", present.FAILS) not in _regions(floors, facts)
    level = {**facts, "ground_fall": 0.0}                                      # a lot the lookup found level
    h = _check(floors, level)["Building height"]
    assert (h["status"], h["proposed"], h["delta"], h["approx"]) == (present.FAILS, height, short + " over", False)
    assert ("height", present.FAILS) in _regions(floors, level)                 # "the part above 35'-0" turns red"


def test_6_the_left_side_wall_out(house):
    got, facts = house
    feet, proposed, drawn, best = said(
        r"move the southwest wall (\d+) ft out\*\*.*?Side yard, Southwest (\d+'-\d+(?: \d/\d)?\"): \*\*needs review\*\*, "
        r"(\d+'-\d+(?: \d/\d)?\") short as drawn, \"(\+\d+'-\d+(?: \d/\d)?\") if the tax-map lines are 2 ft off the other way\"")
    side = _left_side(_check(_wall_out(got["floors"], float(feet)), facts))
    assert (side["status"], side["proposed"], side["delta"]) == (
        present.REVIEW, proposed, f"{drawn} short ({best} if the tax-map lines are 2 ft off the other way)")
    feet, proposed, drawn, least = said(
        r"Move it (\d+) ft out\s+instead:\*\* (\d+'-\d+(?: \d/\d)?\"): \*\*does not comply\*\*, (\d+'-\d+(?: \d/\d)?\") short, "
        r"\"still (\d+'-\d+(?: \d/\d)?\") short if the tax-map lines are 2 ft off the other way\"")
    out = _wall_out(got["floors"], float(feet))
    side = _left_side(_check(out, facts))
    assert (side["status"], side["proposed"], side["delta"]) == (
        present.FAILS, proposed, f"{drawn} short (still {least} short if the tax-map lines are 2 ft off the other way)")
    assert ("yard", present.FAILS) in _regions(out, facts)                      # "that strip turns red"


def test_8_a_garage_not_on_the_building_layer(house):
    got, facts = house
    items = _check(got["floors"], facts, extras={"not_included": ["garage"], "touching": []}, grade_is="finished")
    assert items["Objects on the lot not included"]["status"] == present.REVIEW
    assert items["Lot coverage"]["status"] == present.REVIEW


def test_9_one_floor_moved_on_its_own(house):
    got, facts = house
    said(r"Move one floor on its own\*\* \(Floor 2, 3 ft to the right, seen from the street\)")
    items = _check(_moved(got["floors"], dx=3, which=1), facts)
    assert items["Stories"]["status"] == present.REVIEW and "floors misaligned" in items["Stories"]["reason"]


def test_10_the_height_bonus_waits_for_the_open_question(house):
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    feet, = said(r"raise the roof (\d+) ft \(\d+'-\d+\"\), move the\s+house 3 ft back, and pull each side wall 3 ft in. "
                 r"On this lot Building height \*\*needs review\*\*")
    floors[-1]["top"] += float(feet)
    x0, x1 = min(p[0] for p in floors[0]["outline"]), max(p[0] for p in floors[0]["outline"])
    for f in floors:
        f["outline"] = [[x + (3 if x == x0 else -3 if x == x1 else 0), y + 3] for x, y in f["outline"]]
    h = _check(floors, facts)["Building height"]
    assert h["status"] == present.REVIEW and "side and rear lot lines" in h["reason"]


def test_11_delta_in_words(house):
    from design_checker import rhino_logic as logic
    got, facts = house
    front_words, cell_1, cell_2, up_words, least_words, survey_words = (" ".join(w.split()) for w in said(
        r'after test 2 the Front yard row\'s details\s+read "(.+?\))" \(the list says it shorter, on two lines: "(.+?)" '
        r'over "(.+?)"\); in test 6 '
        r'the Southwest side yard reads "(.+?\))" \(3 ft out: it may comply\) and "(.+?\))" \(5 ft out: the red '
        r'strip\).*?With a survey it reads the margin itself: after test 2,\s+"(\+\d+\'-\d+(?: \d/\d)?")"'))
    back, = said(r"Move the house (\d+) ft back")
    front = _check(_moved(got["floors"], dy=float(back)), facts)["Front yard"]
    assert front["delta"] == front_words and front["delta_cell"] == cell_1 + "\n" + cell_2
    assert _left_side(_check(_wall_out(got["floors"], 3), facts))["delta"] == up_words
    assert _left_side(_check(_wall_out(got["floors"], 5), facts))["delta"] == least_words
    surveyed = _check(_moved(got["floors"], dy=float(back)), facts, lot_surveyed=True)["Front yard"]
    assert surveyed["delta"] == survey_words == surveyed["margin"]          # a bare "+": complies, to spare


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
    assert "spot grades" not in (on["Building height"]["reason"] or "")      # the grades at the walls are used
    assert on["Building height"]["status"] != present.FAILS
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
    wide, deep, left = said("a new starting house goes to the limits: " + LEN + " × " + LEN
                            + r", its southwest\s+side yard at (\d+'-\d+(?: \d/\d)?\"), complying")
    ys = [p[1] for p in full["floors"][0]["outline"]]
    assert (present.feet_inches(max(xs) - min(xs)), present.feet_inches(max(ys) - min(ys))) == (wide, deep)
    side = _left_side(_check(full["floors"], surveyed))
    assert (side["name"], side["proposed"], side["status"]) == ("Side yard, Southwest", left, present.COMPLIES)


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


def test_on_a_survey_the_tax_maps_slack_is_gone(house):
    """The tax-map slack is the tax map's: with surveyed lot lines, the left wall 3 ft out (9'-0 1/2" against
    10'-0") is simply short; on the tax map it needed review (test 6)."""
    got, facts = house
    side = _left_side(_check(_wall_out(got["floors"], 3), facts, lot_surveyed=True))
    assert side["status"] == present.FAILS and side["proposed"] == "9'-0 1/2\""


def test_coverage_over_only_on_some_tax_map_lots_needs_review(house):
    """The rear wall 6 ft back: 26.1% of the lot as drawn, but 23.7% of the largest lot the tax map allows (every
    line 2 ft out): it fails only under some readings, so it needs review."""
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    top = max(p[1] for p in floors[0]["outline"])
    for f in floors:
        f["outline"] = [[x, y + 6 if y == top else y] for x, y in f["outline"]]
    cov = _check(floors, facts)["Lot coverage"]
    assert cov["status"] == present.REVIEW and cov["proposed"] == "26.1%" and "at best 23.7%" in cov["reason"]


def test_a_side_yard_short_under_every_reading_fails_in_the_checker_itself(house):
    """Review round 2: the house moved 11 ft right and 18 ft back on 106 is 0'-9 7/8" from its Northeast line,
    short by at least 7'-2" whichever lines are the sides (it was 26 ft right for the narrower house before
    PR 18). The checker gave up (18 x 18 readings, over its 200) and
    said needs review while the panel's own set said "at least … short": one reading set now decides both."""
    got, facts = house
    moved = _moved(got["floors"], dx=11.0, dy=18.0)
    for surveyed in (True, False):
        r = check_site(_site(moved), {**facts, "lot_surveyed": surveyed})
        row = next(x for x in r["rows"] if x["Rule id"] == "R-1b.side_yards")
        assert row["Fails"], (surveyed, row["Provisional"])                      # the checker's own verdict
        side = next(i for i in r["view"]["items"] if i["name"] == "Side yard, Northeast")
        assert (side["status"], side["colour"]) == (present.FAILS, "red"), (surveyed, side["status"], side["delta"])
        if surveyed:                    # a survey reads the margin itself (guide, test 11): every reading agrees here
            assert side["delta"] == side["margin"] + " short" and side["delta"].startswith("−"), side["delta"]
        else:
            assert side["delta"].startswith(side["margin"].lstrip("−") + " short (still "), side["delta"]   # as drawn first
        assert any(e["why"] == "yard" and e["status"] == present.FAILS for e in r["plan"]["encroach"])


def test_a_row_with_no_reading_set_never_says_to_spare_unless_it_complies(house, tmp_path):
    """Review round 2: with no reading set (a corner lot: the yards can't be read, so neither can the height's
    bonus clause), a needs-review height row fell back to "+1'-0" to spare". Settle is the only writer of the
    Delta: "+1'-0" if confirmed"; the panel, the report and the notice show only its words."""
    import openpyxl
    from design_checker.check import _report
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    floors[-1]["top"] -= 1.0
    facts = {**facts, "ground_fall": 0.0}           # a level lot: the height measured, its Delta the question here
    for over in ({"corner_lot": True}, {"street_line": None, "street_ids": None}):
        r = check_site(_site(floors), {**facts, **over})
        h = next(i for i in r["view"]["items"] if i["name"] == "Building height")
        assert h["status"] == present.REVIEW and "to spare" not in (h.get("delta") or ""), (over, h["delta"])
        assert h["delta"] == h["margin"] + " if confirmed", (over, h["delta"])
    report = tmp_path / "r.xlsx"
    check_site(_site(floors), {**facts, "corner_lot": True}, report_path=report)
    sheet = openpyxl.load_workbook(report)["Check"]
    rows = list(sheet.iter_rows(values_only=True))
    head = next(x for x in rows if x and "Item" in x)
    cell = next(x for x in rows if x and str(x[head.index("Item")]).startswith("Building height"))
    assert "to spare" not in str(cell[head.index(next(c for c in head if c and "Delta" in str(c)))])


def test_a_span_of_readings_is_whole_in_its_detail(house):
    """In Rhino (panel_width, 380 px): the sample house 5 ft left reads its rear yard as a span, "35'-0 5/8" to
    35'-8 3/4"", cut short in the narrow panel's cell and said nowhere else: its detail line was empty (it was
    worked out while the value was still a dash). The span and its limit are now the detail's line (on a tax-map
    lot, with the Delta the row shows)."""
    got, facts = house
    items = _check(_moved(got["floors"], dx=-5), facts)
    spans = {n: i for n, i in items.items() if " to " in (i["proposed"] or "")}
    assert "Rear yard" in spans, sorted(spans)
    for name, i in spans.items():
        line = i["detail"]["line"]
        assert line.startswith(f"{i['proposed']} proposed") and f"{i['required']} required" in line, (name, line)
        if i.get("approx"):
            assert line.endswith(i["delta"]), (name, line, i["delta"])


def test_the_rear_yards_span_shows_its_tightest_pair_in_the_list(house):
    """The audit of main (2026-10-29): the starting house's Rear yard showed a range in both columns ("34'-11 7/8" to
    36'-3 3/8"" against "24'-1 7/8" to 32'-10 1/8""), hard to read. The list now shows the tightest reading's pair,
    marked "(varies)", and that pair's margin first in the Delta (36'-3 3/8" − 32'-10 1/8" = 3'-5 1/4", by hand); the
    row's own words keep both ranges (the details and the report), so it is never hidden that it is a range."""
    from design_checker import rhino_logic as logic
    got, facts = house
    rear = _check(got["floors"], facts)["Rear yard"]
    assert rear["proposed"] == "34'-11 7/8\" to 36'-3 3/8\"" and rear["required"] == "24'-1 7/8\" to 32'-10 1/8\""
    assert rear["cells"] == {"proposed": "36'-3 3/8\" (varies)", "required": "32'-10 1/8\" (varies)"}
    assert rear["delta"] == "+3'-5 1/4\" if confirmed (at least +0'-5 1/4\" under every reading)"
    assert rear["delta_cell"] == "worst +0'-5 1/4\"\nif confirmed"     # in review: never kinder than the status
    assert rear["detail"]["line"].startswith(rear["proposed"] + " proposed, " + rear["required"] + " required")
    assert logic.list_values(rear)[1:] == ("36'-3 3/8\" (varies)", "32'-10 1/8\" (varies)", rear["delta_cell"])
    side = _check(got["floors"], facts)["Side yard, Southwest"]     # one reading as drawn: no cells, its own value
    assert "cells" not in side and logic.list_values(side)[1:] == (side["proposed"], side["required"],
                                                                  "+2'-0 1/2\"\nworst +0'-0 1/2\"")


def test_the_starting_house_on_a_sloping_lot_is_the_flat_lots_and_says_so(house, tmp_path):
    """The sloped-lot fix: the starting house is still drawn standing at the lot's level, sized by the zone's
    limits exactly as on a level lot (it relies on flat ground), and its note says height and stories need review."""
    import rhino3dm as r
    got, facts = house
    assert any(n.startswith("drawn as if the ground were flat") and "falls about 14.2 ft" in n for n in got["notes"])
    m = r.File3dm()
    m.Settings.ModelUnitSystem = r.UnitSystem.Feet
    layer = r.Layer()
    layer.Name = "Site"
    m.Layers.Add(layer)
    attrs = r.ObjectAttributes()
    attrs.LayerIndex = 0
    m.Objects.AddPolyline([r.Point3d(x, y, 0) for x, y in SAMPLE["lot"] + SAMPLE["lot"][:1]], attrs)
    path = tmp_path / "lot.3dm"
    m.Write(str(path), 8)
    level = start(path, {**facts, "ground_fall": 0.0})
    assert level["floors"] == got["floors"]
    assert not any("as if the ground were flat" in n for n in level["notes"])
    # the envelope draws no height plane over a lot that may slope (its height needs review), only the buildable area
    sloped_env = check_site(_site(got["floors"]), facts)["envelope"]
    level_env = check_site(_site(got["floors"]), {**facts, "ground_fall": 0.0})["envelope"]
    assert level_env["top"] is not None and level_env["outline"]
    assert sloped_env["top"] is None and sloped_env["base"] is None and sloped_env["outline"] == level_env["outline"]
