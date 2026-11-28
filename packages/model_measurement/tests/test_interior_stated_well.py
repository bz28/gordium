"""What the architect states of an escape opening and its area well (`openings[].stated_well`; in Revit the window's
or door's own marks: a well isn't in Revit's vocabulary). Each value given is handed to the rules as the architect's
statement; one left out is not stated, its reason naming the field and the mark (so the pane's card opens it), never 0
or no; a statement that can't be read, or disagrees with a drawn well, gives no value. What the ground given outside
the opening measures, and its disagreements with a statement: test_interior_ground_well.py."""

import copy
import functools

import pytest

from model_measurement.interior import has_none, measure
from model_measurement.interior.openings import LADDER_WORDS, STATED_WELL, WELL_FIELDS

from test_interior_measures import base, opening_measures

# the area in the description's units squared: base() is in inches, so 1512 sq in is 10.5 sq ft
FULL = {"below_grade": True, "area": 1512, "width": 40, "projection": 38, "depth": 50, "ladder": "ladder",
        "ladder_width": 14, "ladder_projection": 4, "rung_spacing": 12, "step_tread": 6, "step_riser": 10,
        "full_height": True, "ladder_encroachment": 4, "other_encroachment": 0}


def stated(well, **kw):
    """base()'s opening stating `well`. Stated below grade, its ground is 1 in over its clear bottom (20 in), so the
    two agree (base()'s ground, 0, would show it 20 in above grade: a disagreement, test_interior_ground_well.py)."""
    d = base()
    d["openings"][0]["stated_well"] = well
    if isinstance(well, dict) and well.get("below_grade") is True:
        d["openings"][0]["ground_outside"] = 21
    d["openings"][0].update(kw)
    return d


def test_every_statement_given_is_handed_to_the_rules_as_given():
    m, stopped, more = opening_measures(stated(dict(FULL)))
    assert {k: m[k] for k in WELL_FIELDS} == {
        "opening_below_grade": True, "area_well_area": 10.5, "area_well_width": 40.0, "area_well_projection": 38.0,
        "area_well_depth": 50.0, "area_well_ladder": True, "area_well_steps": False, "area_well_ladder_width": 14.0,
        "area_well_ladder_projection": 4.0, "area_well_rung_spacing": 12.0, "area_well_step_tread": 6.0,
        "area_well_step_riser": 10.0, "area_well_ladder_full_height": True, "area_well_ladder_encroachment": 4.0,
        "area_well_other_encroachment": 0.0}
    assert not set(WELL_FIELDS) & set(stopped) and not set(WELL_FIELDS) & set(more)


def test_a_statement_left_out_is_not_stated_naming_its_field_and_mark_never_0_or_no():
    m, stopped, _ = opening_measures(stated({}, ground_outside=None))      # no ground: the model gives none of them
    for key, (measure, _, _, mark) in STATED_WELL.items():
        for got in [measure] if measure else ["area_well_ladder", "area_well_steps"]:
            assert got not in m, got
            assert "(" + mark + ")" in stopped[got] and "doesn't state" in stopped[got], (got, stopped[got])
    assert "climb out by (a ladder, steps or none), and the model doesn't give it (its area well marks)" in \
        stopped["area_well_ladder"]
    assert "(its below-grade mark)" in stopped["opening_below_grade"]
    assert "doesn't state" in stopped["opening_below_grade"]


def test_a_description_with_no_stated_well_is_as_before():
    _, stopped, _ = opening_measures(base())
    assert stopped["opening_below_grade"] == "Gordium doesn't measure this yet"
    assert stopped["area_well_other_encroachment"] == "Gordium doesn't measure this yet"


@pytest.mark.parametrize("well", ["deep", [], {"below_grade": True, "depht": 50}])
def test_a_stated_well_that_cant_be_trusted_refuses_every_statement(well):
    m, stopped, _ = opening_measures(stated(well))
    for k in WELL_FIELDS:
        assert k not in m and "stated area well isn't read" in stopped[k], k
    if isinstance(well, dict):
        assert "depht" in stopped["opening_below_grade"]


@pytest.mark.parametrize("key, value, said", [
    ("below_grade", "yes", "the text 'yes'"), ("full_height", 1, "1"), ("width", -36, "can't be less than zero"),
    ("depth", "50", "isn't a length"), ("area", -9, "an area can't be less than zero"), ("area", True, "isn't a length"),
    ("ladder", "Ladder", "not one of ladder, steps, ladder_blocked, steps_blocked, none")])
def test_a_statement_gordium_cant_read_gives_no_value_and_says_why(key, value, said):
    well = dict(FULL)
    well[key] = value
    m, stopped, _ = opening_measures(stated(well))
    measure = STATED_WELL[key][0] or "area_well_ladder"
    assert measure not in m
    assert said in stopped[measure] and STATED_WELL[key][3] in stopped[measure], stopped[measure]


@pytest.mark.parametrize("word", sorted(LADDER_WORDS))
def test_the_ladder_word_gives_both_ladder_measures(word):
    well = dict(FULL, ladder=word, ladder_encroachment=0)                # nothing reaches into the well
    m, _, _ = opening_measures(stated(well))
    assert (m["area_well_ladder"], m["area_well_steps"]) == LADDER_WORDS[word]
    # a ladder or steps the open window blocks is never the ladder 1031.5.2 accepts
    assert m["area_well_ladder"] is (word in ("ladder", "steps"))


@pytest.mark.parametrize("word", ["none", "ladder", "ladder_blocked", "steps_blocked"])
@pytest.mark.parametrize("reach, outcome", [({"other_encroachment": 10}, "fail"), ({"ladder_encroachment": 8}, "fail"),
                                            ({"other_encroachment": None}, "needs_review"),
                                            ({"ladder_encroachment": None}, "needs_review")])
def test_a_crowded_well_fails_both_codes_size_rules_and_one_not_stated_needs_review(word, reach, outcome):
    # PR #247's review round 1 found the house code's size rules (RCNYS R319.4.1) reading the size alone, so a 36 in
    # well with a meter in it passed; they read the two reaches now, as BCNYS 1031.5.1's do (the same words)
    well = {k: v for k, v in {**FULL, "ladder": word, "depth": 50, "width": 40, "projection": 40, "area": 40 * 40,
                              "ladder_encroachment": 0, **reach}.items() if v is not None}
    if word == "none" and "ladder_encroachment" in reach:          # with none, the ladder's reach is 0 by itself
        well.pop("ladder_encroachment", None)
        well["other_encroachment"] = 10 if outcome == "fail" else None
        well = {k: v for k, v in well.items() if v is not None}
    m, _, _ = opening_measures(stated(well))
    for k in ("area_well_area", "area_well_width", "area_well_projection"):
        assert k in m, k                                         # the size reaches the rules as stated
    house = _house_outcomes(well)
    building = _outcomes(well)
    for got in [house[r] for r in HOUSE_SIZE_RULES] + [building[r] for r in WELL_RULES[:3]]:
        assert got == outcome, (word, reach, house, building)


def test_no_ladder_means_nothing_climbs_into_the_well_and_a_reach_stated_besides_refuses():
    well = dict(FULL, ladder="none")
    well.pop("ladder_encroachment")
    m, _, _ = opening_measures(stated(well))
    assert m["area_well_ladder_encroachment"] == 0.0
    m, _, _ = opening_measures(stated(dict(FULL, ladder="none", ladder_encroachment=0)))
    assert m["area_well_ladder_encroachment"] == 0.0
    for reach, said in ((3, "stated as 3 in"), ("3", "a value Gordium can't read")):
        m, stopped, _ = opening_measures(stated(dict(FULL, ladder="none", ladder_encroachment=reach)))
        for k in ("area_well_ladder", "area_well_steps", "area_well_ladder_encroachment"):
            assert k not in m and "has no ladder or steps, yet" in stopped[k] and said in stopped[k], k


def test_a_ladder_not_stated_leaves_a_reach_that_is_stated_as_it_is():
    well = dict(FULL)
    well.pop("ladder")
    m, stopped, _ = opening_measures(stated(well))
    assert m["area_well_ladder_encroachment"] == 4.0
    assert "area_well_ladder" not in m and "(its area well marks)" in stopped["area_well_ladder"]


def test_a_stated_size_that_disagrees_with_the_drawn_well_gives_neither():
    d = stated(dict(FULL, width=40, depth=20, ladder_encroachment=0), ground_outside=30)
    d["openings"][0]["area_well"] = {"floor_elevation": 10, "width": 36, "projection": 38}
    m, stopped, more = opening_measures(d)
    assert "area_well_width" not in m and "drawn area well gives" in stopped["area_well_width"]
    assert more["area_well_width"] == 36.0                       # the drawn one stays where it was, not for the rules
    assert m["area_well_projection"] == 38.0 and m["area_well_depth"] == 20.0   # these agree
    d["openings"][0]["stated_well"]["width"] = 36 + 1 / 32       # within 1/16 in: agree
    m, _, _ = opening_measures(d)
    assert m["area_well_width"] == pytest.approx(36 + 1 / 32)


def test_a_stated_area_over_the_width_times_projection_refuses_all_three():
    # a semicircular well's area is less than its rectangle's, never more: more means one of the three is wrong
    m, stopped, _ = opening_measures(stated(dict(FULL, area=40 * 38 + 14.4)))      # 0.1 sq ft over
    for k in ("area_well_area", "area_well_width", "area_well_projection"):
        assert k not in m and "can't hold" in stopped[k], k
    m, _, _ = opening_measures(stated(dict(FULL, area=40 * 38)))
    assert m["area_well_area"] == pytest.approx(40 * 38 / 144)


def test_a_feet_description_states_its_sizes_in_feet_and_its_area_in_square_feet():
    d = base()
    d["units"] = "ft"
    for room in d["rooms"]:
        room["floor"] = [[x / 12, y / 12] for x, y in room["floor"]]
        room["floor_elevation"] = 0
        room["ceiling_height"] = 8
    o = d["openings"][0]
    o["frame"] = {k: v / 12 for k, v in o["frame"].items()}
    o["hinged"] = {**o["hinged"], "sash_width": 2.5, "sash_thickness": 2 / 12}
    o["stated_well"] = {"area": 9.5, "width": 3.5, "projection": 3.25, "depth": 4, "ladder": "none",
                        "other_encroachment": 0}
    got = measure(d)["parts"]["emergency_escape_opening"][0]["measures"]
    assert (got["area_well_area"], got["area_well_width"], got["area_well_projection"], got["area_well_depth"]) == \
        (9.5, 42.0, 39.0, 48.0)


def test_a_no_basements_claim_cant_stand_beside_an_opening_stated_below_grade_or_with_a_well():
    for well, refused in (({"below_grade": True}, True), ({"depth": 50}, True), ({"below_grade": "yes"}, True),
                          ("deep", True), ({}, False), ({"below_grade": False}, False)):
        d = stated(copy.deepcopy(well))
        d["openings"][0]["ground_outside"] = None
        got = has_none.below_ground(d)
        assert (got is not None) is refused, (well, got)


# ---- end to end: the statements, measured, through the Building Code's area well rules (BCNYS 1031.5 to 1031.5.2.2)

WELL_RULES = ("general.bc_1031_5_area_well_required", "general.bc_1031_5_1_area_well_min_projection",
              "general.bc_1031_5_1_area_well_min_width", "general.bc_1031_5_2_area_well_ladder_over_44",
              "general.bc_1031_5_2_1_area_well_ladder", "general.bc_1031_5_2_2_area_well_steps")


@functools.cache
def _book():
    from rule_format.rulebook import REPO, Context, load
    ny = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
    return ({r["id"]: r for r in load(ny / "5_building_code_rules/drafted/general.yaml")["rules"]},
            Context.for_jurisdiction(ny).allowed())


def _outcomes(well, **kw):
    """Each area well rule's outcome for the base bedroom's window stated so, in a Group R-3 building with no sprinkler
    system, the room below the fourth story, with one exit and no door to outside or other opening (1031.2 asks it)."""
    from rule_format import parts
    rules, allowed = _book()
    part = measure(stated(well, **kw))["parts"]["emergency_escape_opening"][0]
    room = {"opening_room_fourth_or_higher": False, "opening_room_one_exit": True,
            "opening_room_door_to_outside": False, "opening_room_other_compliant": False}
    given = {"occupancy_group": "R-3", **{k: False for k in ("sprinklered_903_3_1_1", "sprinklered_903_3_1_2",
                                                             "sprinklered_903_3_1_3")}}
    out = {}
    for rid in WELL_RULES:
        got = parts.rows(rules[rid], {"emergency_escape_opening": [{"id": "o", "within": "r",
                                                                    "measures": {**part["measures"], **room}}],
                                      "sleeping_room": [{"id": "r", "measures": {}}]}, given, allowed)
        out[rid] = got[0]["outcome"]
    return out


def test_the_pr_example_well_stated_in_revit_passes_its_size_and_ladder_rules():
    # 50 in deep, 40 by 38 in, 10.5 sq ft, a ladder 14 in wide, rungs 4 in out and 12 in apart, full height, reaching 4
    # in into the well (a required ladder may take 6 in), nothing else in it
    well = dict(FULL)
    assert set(_outcomes(well).values()) == {"pass"}, _outcomes(well)


def test_a_ladder_the_open_window_blocks_fails_1031_5_2_and_a_blank_ladder_needs_review():
    got = _outcomes(dict(FULL, ladder="ladder_blocked", ladder_encroachment=0))
    assert got["general.bc_1031_5_2_area_well_ladder_over_44"] == "fail", got
    # reaching 4 in into the well besides: still no ladder it accepts, so 1031.5.2 fails it; whether the exception
    # allows an obstructed ladder's reach is an open question, so no size rule in either code passes it (review round 2).
    # The Building Code's size rules hold section group 8d's limits, which can't carry the open question's review band
    # (merge of #257 with 8d, the coordinator's option A): they read it strictly, an obstructed ladder not the one
    # 1031.5.2 requires, so they fail beside 1031.5.2's own fail (no verdict changes: the opening fails either way);
    # not stated whether it is blocked, they need review; the house code's keep the review
    for word in ("ladder_blocked", "steps_blocked", None):
        well = {k: v for k, v in dict(FULL, ladder=word).items() if v is not None}
        got, house = _outcomes(well), _house_outcomes(well)
        if word:
            assert got["general.bc_1031_5_2_area_well_ladder_over_44"] == "fail", got
        assert {got[r] for r in WELL_RULES[:3]} == {"fail" if word else "needs_review"}, (word, got)
        assert {house[r] for r in HOUSE_SIZE_RULES} == {"needs_review"}, (word, house)
    # not stated whether it is a ladder, steps or none: the 50 in well's ladder rule needs review; the ladder's and the
    # steps' own sizes pass where every one stated is within both (either way it complies), and need review where one
    # falls short (an 11 in ladder or steps: which it is decides)
    well = dict(FULL)
    well.pop("ladder")
    got = _outcomes(well)
    assert got["general.bc_1031_5_2_area_well_ladder_over_44"] == "needs_review", got
    got = _outcomes(dict(well, ladder_width=11))
    for rid in ("general.bc_1031_5_2_1_area_well_ladder", "general.bc_1031_5_2_2_area_well_steps"):
        assert got[rid] == "needs_review", (rid, got[rid])
    assert _outcomes(dict(FULL, ladder_width=11))["general.bc_1031_5_2_1_area_well_ladder"] == "fail"


def test_nothing_stated_never_passes_and_not_below_grade_needs_no_well():
    # nothing stated and no ground given (base()'s ground, under the clear bottom, measures it not below grade:
    # test_interior_ground_well.py)
    assert "pass" not in _outcomes({}, ground_outside=None).values()
    assert set(_outcomes({"below_grade": False}).values()) == {"pass"}


HOUSE_SIZE_RULES = ("general.r319_4_1_area_well_min_width", "general.r319_4_1_area_well_min_projection",
                    "general.r319_4_1_area_well_min_area")


@functools.cache
def _house_book():
    from rule_format.rulebook import REPO, Context, load
    ny = REPO / "regulations/jurisdictions/new_york/new_york_state"
    return ({r["id"]: r for r in load(ny / "5_building_code_rules/drafted/general.yaml")["rules"]},
            Context.for_jurisdiction(ny).allowed())


def _house_outcomes(well):
    """The house code's area well size rules (RCNYS R319.4.1) for the base bedroom's window stated so, one window's
    own outcome (parts.part_outcome)."""
    from rule_format import parts
    rules, allowed = _house_book()
    part = measure(stated(well))["parts"]["emergency_escape_opening"][0]
    out = {}
    for rid in HOUSE_SIZE_RULES:
        rule = rules[rid]
        out[rid] = parts.part_outcome(rule, part["measures"], allowed)
    return out


def test_a_clear_well_with_no_ladder_passes_the_house_size_rules():
    well = {**FULL, "ladder": "none", "depth": 30, "width": 36, "projection": 36, "area": 36 * 36}
    well.pop("ladder_encroachment")
    assert {_house_outcomes(well)[r] for r in HOUSE_SIZE_RULES} == {"pass"}


@pytest.mark.parametrize("shown", ["well", "ground"])
def test_not_below_grade_cant_stand_beside_a_drawn_well_or_ground_above_the_opening(shown):
    # review round 1 (a false pass from a hand-written description): stated not below grade, drawn below it
    d = stated({"below_grade": False})
    if shown == "well":
        d["openings"][0].update(area_well={"floor_elevation": 10, "width": 36, "projection": 36}, ground_outside=30)
    else:
        d["openings"][0]["ground_outside"] = 30                        # base()'s clear bottom is at 20
    m, stopped, _ = opening_measures(d)
    assert "opening_below_grade" not in m and "yet the model shows" in stopped["opening_below_grade"]
    d["openings"][0]["ground_outside"] = 0
    d["openings"][0].pop("area_well", None)
    m, _, _ = opening_measures(d)
    assert m["opening_below_grade"] is False


def test_a_drawn_wells_size_not_stated_says_the_drawing_gives_it():
    # review round 1: "the model doesn't give it" was false beside a drawn well
    d = stated({"below_grade": True}, ground_outside=30)
    d["openings"][0]["area_well"] = {"floor_elevation": 10, "width": 36, "projection": 36}
    _, stopped, more = opening_measures(d)
    assert more["area_well_width"] == 36.0
    assert "drawn area well gives" in stopped["area_well_width"] and "doesn't give it" not in stopped["area_well_width"]


@pytest.mark.parametrize("ladder, depth, reach, outcome", [
    ("ladder", 50, 6, "pass"), ("ladder", 50, 7, "fail"), ("ladder", 44, 2, "fail"), ("steps", 45, 6, "pass"),
    ("ladder", 30, 0, "pass"), ("ladder", None, 2, "needs_review"), ("ladder", 50, None, "needs_review")])
def test_only_the_required_ladder_may_reach_into_the_well_and_6_in_at_most(ladder, depth, reach, outcome):
    # R319.4.1 exception: "The ladder or steps required by Section R319.4.2" (a well over 44 in deep) "shall be
    # permitted to encroach not more than 6 inches (152 mm) into the required dimensions of the area well."
    well = {k: v for k, v in {**FULL, "ladder": ladder, "depth": depth, "ladder_encroachment": reach, "width": 40,
                              "projection": 40, "area": 40 * 40}.items() if v is not None}
    house, building = _house_outcomes(well), _outcomes(well)
    assert {house[r] for r in HOUSE_SIZE_RULES} == {outcome}, (ladder, depth, reach, house)
    assert {building[r] for r in WELL_RULES[:3]} == {outcome}, (ladder, depth, reach, building)


def test_a_house_well_30_to_36_in_with_a_ladder_keeps_the_answer_keys_review():
    # the answer key needs review for a well 30 to under 36 in with a ladder or steps: kept (whether the 6 in may come
    # off the well's own size isn't settled); under 30 in it fails, and anything else in it fails
    base_ = {**FULL, "width": 33, "projection": 40, "area": 33 * 40, "ladder_encroachment": 3}
    assert _house_outcomes(base_)["general.r319_4_1_area_well_min_width"] == "needs_review"
    assert _house_outcomes({**base_, "width": 29, "area": 29 * 40})["general.r319_4_1_area_well_min_width"] == "fail"
    assert _house_outcomes({**base_, "other_encroachment": 1})["general.r319_4_1_area_well_min_width"] == "fail"
    assert _house_outcomes({**base_, "ladder": "none", "ladder_encroachment": 0})[
        "general.r319_4_1_area_well_min_width"] == "fail"


def test_not_below_grade_cant_stand_beside_a_ground_where_no_clear_bottom_is_known():
    # review round 2: with the clear opening unread, a ground given can't be compared, so "not below" isn't taken
    d = stated({"below_grade": False}, ground_outside=30, operation="awning")       # awning: needs a maker's opening
    m, stopped, _ = opening_measures(d)
    assert "opening_below_grade" not in m and "bottom isn't known" in stopped["opening_below_grade"]
