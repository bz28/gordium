"""The QUICKSTART's "Test it yourself" expectations, checked in code (apps/rhino_plugin/QUICKSTART.md): the sample
project (106 Ithaca Rd as the State tax map draws it, placed as the address lookup places it), the starting house
GordiumStart draws, and each test's edit made the way the guide says, with the numbers the guide promises. The numbers are read from the guide itself
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
    assert rear["status"] == present.REVIEW and "confirm with the zoning office" in rear["reason"]
    tall_at, = said(r"\*\*Building height\*\*: (\d+'-\d+\") is at the limit and complies")
    assert (height["proposed"], height["status"], height["margin"], height["note"]) == (
        tall_at, present.COMPLIES, "at limit", "assuming flat ground")   # the bonus's open question doesn't matter
    said("One row needs review from the start")
    assert [i["name"] for i in items.values() if i["status"] == present.REVIEW and i.get("measure")] == ["Rear yard"]
    stories, = said(r"Stories (\d) complies, at the limit, saying \"assuming flat ground\"")
    assert items["Stories"]["proposed"] == stories and items["Stories"]["status"] == present.COMPLIES
    said("Lot area complies even at the tax map's worst case")
    assert items["Lot area"]["status"] == present.COMPLIES


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
    dy, proposed = said(r"Move it (\d+) ft back instead.\*\* Rear yard (\d+'-\d+(?: \d/\d)?\"): \*\*needs review")
    rear = _check(_moved(got["floors"], dy=float(dy)), facts)["Rear yard"]
    assert (rear["status"], rear["proposed"]) == (present.REVIEW, proposed)
    dy, proposed, short = said(r"Now move it (\d+) ft back:\*\* Rear yard\s+(\d+'-\d+(?: \d/\d)?\"): \*\*does not "
                               r"comply\*\*, at least (\d+'-\d+(?: \d/\d)?\") short")
    moved = _moved(got["floors"], dy=float(dy))
    rear = _check(moved, facts)["Rear yard"]
    assert (rear["status"], rear["proposed"], rear["delta"]) == (present.FAILS, proposed, f"at least {short} short")
    assert ("yard", present.FAILS) in _regions(moved, facts)                    # "the strip ... turns red"
    # short under only some readings (the depth's 4'-0" slack and the back-line question): needs review, amber only
    low, high = said(r"From (\d+) to (\d+) ft back it still needs review")
    for dy in range(int(low), int(high) + 1):
        moved = _moved(got["floors"], dy=float(dy))
        rear = _check(moved, facts)["Rear yard"]
        assert rear["status"] == present.REVIEW and rear["delta"].startswith("up to "), (dy, rear["delta"])
        assert ("yard", present.FAILS) not in _regions(moved, facts), dy
        row = next(x for x in check_site(_site(moved), facts)["rows"] if x["Rule id"] == "R-1b.rear_yard")
        assert not row["Fails"], (dy, row["Provisional"])        # the checker itself: one reading set (round 2)


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
    feet, height, short = said(r"raise the roof (\d+) ft\*\* \(the top face of Floor 3\). Building height " + LEN
                               + r": \*\*does not comply\*\*,\s+(−\d+'-\d+\") short \(the height doesn't depend on "
                               r"the lot lines\)")
    floors[-1]["top"] += float(feet)
    h = _check(floors, facts)["Building height"]
    assert (h["status"], h["proposed"], h["delta"], h["approx"]) == (present.FAILS, height, short + " short", False)
    assert ("height", present.FAILS) in _regions(floors, facts)                 # "the part above 35'-0" turns red"


def test_6_the_left_side_wall_out(house):
    got, facts = house
    feet, proposed, up_to = said(r"move the southwest wall (\d+) ft out\*\*.*?Side yard, Southwest (\d+'-\d+(?: \d/\d)?\"):"
                                 r" \*\*needs review\*\*, up to (\d+'-\d+(?: \d/\d)?\") short")
    side = _left_side(_check(_wall_out(got["floors"], float(feet)), facts))
    assert (side["status"], side["proposed"], side["delta"]) == (present.REVIEW, proposed, "up to " + up_to + " short")
    feet, proposed, least = said(r"Move it (\d+) ft out instead:\*\* (\d+'-\d+(?: \d/\d)?\"): \*\*does not comply\*\*,"
                                 r" at least (\d+'-\d+(?: \d/\d)?\") short")
    out = _wall_out(got["floors"], float(feet))
    side = _left_side(_check(out, facts))
    assert (side["status"], side["proposed"], side["delta"]) == (present.FAILS, proposed, "at least " + least + " short")
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
    front_words, up_words, least_words, survey_words = (" ".join(w.split()) for w in said(
        r'after test 2 the Front yard row reads "(at least \d+\'-\d+(?: \d/\d)?" to\s+spare)"; in test 6 the Southwest\s+'
        r'side yard reads "(up to \d+\'-\d+(?: \d/\d)?" short)" \(3 ft out: it may comply\) and "(at least\s+'
        r'\d+\'-\d+(?: \d/\d)?" short)" \(5 ft out: the red strip\).*?With a survey it reads the\s+margin itself: '
        r'after test 2, "(\+\d+\'-\d+(?: \d/\d)?" to spare)"'))
    back, = said(r"Move the house (\d+) ft back")
    front = _check(_moved(got["floors"], dy=float(back)), facts)["Front yard"]
    assert front["delta"] == front_words
    assert _left_side(_check(_wall_out(got["floors"], 3), facts))["delta"] == up_words
    assert _left_side(_check(_wall_out(got["floors"], 5), facts))["delta"] == least_words
    surveyed = _check(_moved(got["floors"], dy=float(back)), facts, lot_surveyed=True)["Front yard"]
    assert surveyed["delta"] == survey_words == surveyed["margin"] + " to spare"


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
    wide, deep, left = said("a new starting house goes exactly to the limits: " + LEN + " × " + LEN
                            + r", its southwest\s+side yard at " + LEN + ", at limit, complying")
    ys = [p[1] for p in full["floors"][0]["outline"]]
    assert (present.feet_inches(max(xs) - min(xs)), present.feet_inches(max(ys) - min(ys))) == (wide, deep)
    side = _left_side(_check(full["floors"], surveyed))
    assert (side["name"], side["proposed"], side["margin"], side["status"]) == (
        "Side yard, Southwest", left, "at limit", present.COMPLIES)


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
    """The tax-map slack is the tax map's: with surveyed lot lines, the left wall 3 ft out (9'-0 5/8" against
    10'-0") is simply short; on the tax map it needed review (test 6)."""
    got, facts = house
    side = _left_side(_check(_wall_out(got["floors"], 3), facts, lot_surveyed=True))
    assert side["status"] == present.FAILS and side["proposed"] == "9'-0 5/8\""


def test_coverage_over_only_on_some_tax_map_lots_needs_review(house):
    """The rear wall 12 ft back: 25.2% of the lot as drawn, but 22.9% of the largest lot the tax map allows (every
    line 2 ft out): it fails only under some readings, so it needs review."""
    got, facts = house
    floors = copy.deepcopy(got["floors"])
    top = max(p[1] for p in floors[0]["outline"])
    for f in floors:
        f["outline"] = [[x, y + 12 if y == top else y] for x, y in f["outline"]]
    cov = _check(floors, facts)["Lot coverage"]
    assert cov["status"] == present.REVIEW and cov["proposed"] == "25.2%" and "at best 22.9%" in cov["reason"]


def test_a_side_yard_short_under_every_reading_fails_in_the_checker_itself(house):
    """Review round 2: the house moved 26 ft right and 18 ft back on 106 is about 1'-2" from its Northeast line,
    short by at least 8'-8" whichever lines are the sides. The checker gave up (18 x 18 readings, over its 200) and
    said needs review while the panel's own set said "at least … short": one reading set now decides both."""
    got, facts = house
    moved = _moved(got["floors"], dx=26.0, dy=18.0)
    for surveyed in (True, False):
        r = check_site(_site(moved), {**facts, "lot_surveyed": surveyed})
        row = next(x for x in r["rows"] if x["Rule id"] == "R-1b.side_yards")
        assert row["Fails"], (surveyed, row["Provisional"])                      # the checker's own verdict
        side = next(i for i in r["view"]["items"] if i["name"] == "Side yard, Northeast")
        assert (side["status"], side["colour"]) == (present.FAILS, "red"), (surveyed, side["status"], side["delta"])
        assert side["delta"].startswith("at least ") and side["delta"].endswith(" short")
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
    for over in ({"corner_lot": True}, {"street_line": None}):
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
