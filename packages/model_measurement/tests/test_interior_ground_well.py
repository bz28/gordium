"""What the ground given outside an escape opening (`ground_outside`: in Revit, a Toposolid the architect marks as the
finished ground, sampled at the wall's outer face) measures for an opening that sends `stated_well`: whether its clear
opening's bottom is below the adjacent grade (BCNYS 1031.5, RCNYS R319.4), and the least depth its area well can have.
A statement wins over the ground, unless the two disagree by more than 1/16 in: then neither is used, the reason naming
both. Never a guess: a ground within 1/16 in of the bottom, a ground that can't be read or an unknown bottom gives no
value, and the least depth reaches the rules only past 44 in, as a reading to confirm.

base()'s escape opening: its clear bottom at 20 in (inches throughout)."""

import functools
import re
from pathlib import Path

import pytest
import yaml

from model_measurement.interior import measure
from model_measurement.interior.openings import DEPTH_READING, LADDER_DEPTH

from test_interior_measures import base

REPO = Path(__file__).parents[3]


def ground(at, well=None, **kw):
    d = base()
    d["openings"][0].update(ground_outside=at, stated_well={} if well is None else well, **kw)
    return d


def part(d):
    return measure(d)["parts"]["emergency_escape_opening"][0]


# ---- below grade --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("at, below", [(21, True), (19, False), ([10, 30], True), ([0, 19.9], False),
                                       (20 + 1 / 8, True), (20 - 1 / 8, False)])
def test_the_ground_over_the_clear_bottom_measures_below_grade_and_under_it_not(at, below):
    p = part(ground(at))
    assert p["measures"]["opening_below_grade"] is below
    assert "opening_below_grade" not in p["not_measured"] and "opening_below_grade" not in p.get("stated", {})


def test_sloped_ground_over_one_end_of_the_bottom_is_below_grade():
    # grade is the finished ground "adjoining the building" (RCNYS R202): over part of the bottom is below it there
    p = part(ground([12, 26]))
    assert p["measures"]["opening_below_grade"] is True


@pytest.mark.parametrize("at", [20, 20 + 1 / 32, 20 - 1 / 32, [19, 20.05]])
def test_a_ground_within_a_sixteenth_of_the_bottom_settles_nothing(at):
    p = part(ground(at))
    assert "opening_below_grade" not in p["measures"]
    assert "within 1/16 in of its clear opening's bottom" in p["not_measured"]["opening_below_grade"]
    assert "(its below-grade mark)" in p["not_measured"]["opening_below_grade"]


def test_no_bottom_known_or_a_ground_that_cant_be_read_settles_nothing():
    p = part(ground(30, frame=None))
    assert "clear opening's bottom isn't known" in p["not_measured"]["opening_below_grade"]
    p = part(ground("high"))
    assert "the ground outside it can't be read" in p["not_measured"]["opening_below_grade"]


def test_no_ground_given_changes_nothing():
    d = base()
    d["openings"][0].update(ground_outside=None, stated_well={})
    p = part(d)
    assert "opening_below_grade" not in p["measures"] and "area_well_depth" not in p["measures"]
    assert "doesn't state" in p["not_measured"]["opening_below_grade"]
    d["openings"][0]["stated_well"] = {"below_grade": True, "depth": 30}
    p = part(d)
    assert (p["measures"]["opening_below_grade"], p["measures"]["area_well_depth"]) == (True, 30.0)
    assert "confirm" not in p


@pytest.mark.parametrize("at", [30, 60, 80])
def test_an_opening_the_ground_shows_below_grade_gets_no_grade_floor_answer(at):
    # it stands in a well whose floor isn't drawn: the well's floor and the ground around it are both "the finished
    # ground level adjacent to the opening" (open question 4.6), so the 5 sq ft exception is never given on one alone
    p = part(ground(at))
    assert "opening_at_grade" not in p["measures"]
    assert "open question (4.6)" in p["not_measured"]["opening_at_grade"]
    # over the ground, the ground around it is the one adjoining it (within 1/16 in of it: not settled, below)
    assert part(ground(19))["measures"]["opening_at_grade"] is True
    assert part(ground(0))["measures"]["opening_at_grade"] is True
    assert part(ground(-30))["measures"]["opening_at_grade"] is False


@pytest.mark.parametrize("at, well", [(0, {"below_grade": True}), (20 + 1 / 32, {"below_grade": True}),
                                      (20, {}), (30, {"below_grade": False}), ("high", {})])
def test_grade_floor_is_answered_only_once_below_grade_is_settled_as_no(at, well):
    # stated below grade (the ground contradicting it, or within 1/16 in), the ground within 1/16 in, a statement the
    # ground contradicts, a ground that can't be read: it may stand in a well whose floor isn't drawn (review round 1)
    p = part(ground(at, well))
    assert "opening_at_grade" not in p["measures"]
    assert "open question (4.6)" in p["not_measured"]["opening_at_grade"] or "isn't a length" in         p["not_measured"]["opening_at_grade"]
    assert part(ground(0, {"below_grade": False}))["measures"]["opening_at_grade"] is True


def test_a_window_stated_below_grade_never_passes_the_grade_floor_area_on_a_ground_it_disputes():
    # 30 in by 27 in clear (5.625 sq ft): enough only for a grade-floor opening (RCNYS R319.2.1, 5 sq ft, else 5.7)
    from rule_format import parts
    from rule_format.rulebook import Context, load
    ny = REPO / "regulations/jurisdictions/new_york/new_york_state"
    rule = next(r for r in load(ny / "5_building_code_rules/drafted/general.yaml")["rules"]
                if r["id"] == "general.r319_2_1_escape_opening_min_net_clear_area")
    allowed = Context.for_jurisdiction(ny).allowed()
    for at in (0, 20 + 1 / 32):
        d = ground(at, {"below_grade": True})
        d["openings"][0]["frame"]["top"] = 47
        p = part(d)
        rows = parts.rows(rule, {"emergency_escape_opening": [{"id": "o", "within": "r", "measures": p["measures"]}],
                                 "sleeping_room": [{"id": "r", "measures": {}}]}, {}, allowed)
        assert rows[0]["outcome"] != "pass", (at, rows[0])


def test_a_drawn_well_keeps_its_own_reading():
    # the drawn well's own floor and depth are the drawing's: the ground doesn't measure below grade beside one
    p = part(ground(30, area_well={"floor_elevation": -10, "width": 36, "projection": 36}))
    assert "opening_below_grade" not in p["measures"]
    assert "doesn't state" in p["not_measured"]["opening_below_grade"]


# ---- a statement and the ground disagreeing ------------------------------------------------------------------------

def test_stated_below_grade_with_the_ground_under_every_bottom_is_no_value_naming_both():
    p = part(ground(0, {"below_grade": True}))
    why = p["not_measured"]["opening_below_grade"]
    assert "opening_below_grade" not in p["measures"]
    assert "is stated to be below the adjacent grade, yet the model shows the ground outside it at 0 in, 20 in below " \
           "its clear opening's bottom" in why and "(its below-grade mark)" in why


def test_stated_not_below_grade_with_the_ground_over_a_bottom_is_no_value_naming_both():
    p = part(ground(30, {"below_grade": False}))
    why = p["not_measured"]["opening_below_grade"]
    assert "is stated not to be below the adjacent grade, yet the model shows the ground outside it at 30 in" in why


@pytest.mark.parametrize("at, said", [(20.03, True), (19.97, True), (20.03, False), (19.97, False),
                                      (40, True), (0, False)])
def test_a_statement_the_ground_agrees_with_within_a_sixteenth_wins(at, said):
    p = part(ground(at, {"below_grade": said}))
    assert p["measures"]["opening_below_grade"] is said


# ---- the least depth -----------------------------------------------------------------------------------------------

def test_a_well_deeper_than_44_in_whatever_its_floor_gets_the_least_depth_as_a_reading_to_confirm():
    p = part(ground(80))                                    # 80 - 20: at least 60 in deep
    assert p["measures"]["area_well_depth"] == 60.0
    assert p["confirm"] == {"area_well_depth": DEPTH_READING.format(least="60")}
    assert "Gordium's reading" in p["confirm"]["area_well_depth"]


@pytest.mark.parametrize("at", [21, 50, 20 + LADDER_DEPTH, 20 + LADDER_DEPTH + 1 / 32])
def test_a_least_depth_of_44_in_or_less_isnt_handed_to_the_rules(at):
    p = part(ground(at))
    assert "area_well_depth" not in p["measures"] and "confirm" not in p
    why = p["not_measured"]["area_well_depth"]
    assert "so the well is at least that deep, but its floor isn't drawn" in why and "(its area well marks)" in why


def test_a_stated_depth_wins_unless_it_is_less_than_the_least_depth():
    p = part(ground(80, {"depth": 70}))                     # 70 in stated, at least 60 shown: the statement
    assert p["measures"]["area_well_depth"] == 70.0 and "confirm" not in p
    p = part(ground(80, {"depth": 60 - 1 / 32}))            # within 1/16 in
    assert p["measures"]["area_well_depth"] == pytest.approx(60 - 1 / 32)
    p = part(ground(80, {"depth": 40}))
    assert "area_well_depth" not in p["measures"]
    why = p["not_measured"]["area_well_depth"]
    assert "states its area well's vertical depth as 40 in, yet the model shows the ground outside it 60 in above " \
           "its clear opening's bottom" in why and "Gordium's reading" in why


def test_the_least_depth_is_measured_only_below_grade():
    p = part(ground(10))                                    # above grade: no depth from the ground
    assert "area_well_depth" not in p["measures"]
    assert "doesn't state its area well's vertical depth, and the model doesn't give it" in \
        p["not_measured"]["area_well_depth"]


# ---- through the Building Code's area well rules -------------------------------------------------------------------

WELL_RULES = ("general.bc_1031_5_area_well_required", "general.bc_1031_5_2_area_well_ladder_over_44")


@functools.cache
def _book():
    from rule_format.rulebook import Context, load
    ny = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
    return ({r["id"]: r for r in load(ny / "5_building_code_rules/drafted/general.yaml")["rules"]},
            Context.for_jurisdiction(ny).allowed())


def _rows(d):
    """Each area well rule's row for base()'s window, as test_interior_stated_well._outcomes sets the building, the
    part's `confirm` kept."""
    from rule_format import parts
    rules, allowed = _book()
    p = part(d)
    room = {"opening_room_fourth_or_higher": False, "opening_room_one_exit": True,
            "opening_room_door_to_outside": False, "opening_room_has_other_openings": False}
    given = {"occupancy_group": "R-3", **{k: False for k in ("sprinklered_903_3_1_1", "sprinklered_903_3_1_2",
                                                             "sprinklered_903_3_1_3")}}
    one = {"id": "o", "within": "r", "measures": {**p["measures"], **room}, **({"confirm": p["confirm"]}
                                                                            if "confirm" in p else {})}
    return {rid: parts.rows(rules[rid], {"emergency_escape_opening": [one],
                                         "sleeping_room": [{"id": "r", "measures": {}}]}, given, allowed)[0]
            for rid in WELL_RULES}


def test_an_opening_the_ground_shows_below_grade_with_no_well_stated_never_passes():
    rows = _rows(ground(30))
    assert {r["outcome"] for r in rows.values()} <= {"needs_review", "fail"}


def test_a_deep_well_with_no_ladder_fails_and_with_one_complies_only_once_the_reading_is_confirmed():
    rows = _rows(ground(80, {"ladder": "none"}))
    ladder = rows["general.bc_1031_5_2_area_well_ladder_over_44"]
    assert ladder["outcome"] == "fail" and ladder.get("confirm")
    rows = _rows(ground(80, {"ladder": "ladder", "full_height": True}))
    ladder = rows["general.bc_1031_5_2_area_well_ladder_over_44"]
    assert ladder["outcome"] == "needs_review"
    assert ladder["reason"].startswith("complies only if this reading is confirmed: Gordium's reading")


def test_an_opening_the_ground_shows_above_grade_needs_no_well():
    rows = _rows(ground(0))
    assert {r["outcome"] for r in rows.values()} <= {"pass", "not_applicable"}


def test_every_rule_reads_the_depth_only_past_44_in():
    """The least depth settles a rule only where the rule asks whether the well is more than 44 in deep: a rule
    reading the depth any other way (another figure, at least, less than) would need the well's true depth, which the
    ground alone doesn't give. Every rule of every book is read here, so such a rule fails this test first."""
    def expressions(node):
        """Every condition in a rule (its check, applies_when and each review_when's when), at any depth."""
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("check", "applies_when", "when") and isinstance(v, str):
                    yield v
                else:
                    yield from expressions(v)
        elif isinstance(node, list):
            for v in node:
                yield from expressions(v)

    seen = 0
    for path in REPO.glob("regulations/**/5_*rules/**/*.yaml"):
        if "as_drafted" in path.parts:
            continue                                     # the AI's drafts as made: never checked against
        text = path.read_text(encoding="utf-8")
        if "area_well_depth" not in text:
            continue                                     # a book that never reads it
        book = yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
        for rule in book.get("rules") or [] if isinstance(book, dict) else []:
            for text in expressions(rule):
                for hit in re.finditer(r"area_well_depth\b(.{0,6})", text, re.S):
                    seen += 1
                    assert re.match(r"\s+>\s+44(?![\d.])", hit.group(1)), (path.name, rule.get("id"), text)
    assert seen > 20
