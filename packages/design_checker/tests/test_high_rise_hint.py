"""The high-rise question's hint (design_checker/high_rise_hint.py): the model's height of its highest level over the
lowest finished ground it states, shown on the question's card where under 75 ft, and never a value: the fact stays
unstated until the architect answers, so Section 403's flags still show and 403.5.2's band still holds."""

from design_checker import code_scope, high_rise_hint, present, ui_data

LEVELS = [{"id": "L1", "name": "Level 1", "elevation": 100}, {"id": "L2", "name": "Level 2", "elevation": 110},
          {"id": "R", "name": "Roof", "elevation": 121}]


def _description(levels=LEVELS, openings=()):
    return {"units": "ft", "all_levels": list(levels), "openings": list(openings)}


def test_the_figure_is_the_highest_level_roof_included_over_the_lowest_finished_ground():
    fig = high_rise_hint.figure(_description(), {"flat": 99.0})
    assert fig == {"height_in": (121 - 99) * 12, "level": "Roof", "ground_in": 99 * 12}
    spots = high_rise_hint.figure(_description(), {"spots": [[0, 0, 99.5], [10, 0, 98.0]]})
    assert spots["height_in"] == (121 - 98) * 12                    # the lowest spot, not the highest
    # finished ground stated lower at an opening, or an area well's floor, counts too
    low = high_rise_hint.figure(_description(openings=[{"ground_outside": [97.0, 98.0]}]), {"flat": 99.0})
    assert low["height_in"] == (121 - 97) * 12
    well = high_rise_hint.figure(_description(openings=[{"area_well": {"floor_elevation": 95.0}}]), {"flat": 99.0})
    assert well["height_in"] == (121 - 95) * 12


def test_no_figure_without_finished_ground_every_level_or_a_readable_one():
    assert high_rise_hint.figure(_description(), {"none": "no ground stated"}) is None     # existing or none
    assert high_rise_hint.figure({"units": "ft", "levels": LEVELS}, {"flat": 99.0}) is None  # every level not sent
    assert high_rise_hint.figure(_description(levels=[{"id": "L1", "elevation": "high"}]), {"flat": 99.0}) is None
    assert high_rise_hint.figure(_description(openings=[{"ground_outside": "low"}]), {"flat": 99.0}) is None
    assert high_rise_hint.figure(None, {"flat": 99.0}) is None


def test_the_words_show_only_under_75_ft_and_say_the_answer_decides():
    words = high_rise_hint.words({"height_in": 22 * 12, "level": "Roof", "ground_in": 0})
    assert "22.0 ft" in words and "Roof" in words and "decided only by your answer" in words
    assert "likely not a high-rise" in words
    assert high_rise_hint.words({"height_in": 75 * 12, "level": "Roof", "ground_in": 0}) is None   # 75 ft or more
    assert high_rise_hint.words({"height_in": 200 * 12, "level": "Roof", "ground_in": 0}) is None
    assert high_rise_hint.words(None) is None


def _row():
    causes = [{"kind": "mark", "key": "fact:high_rise_building", "words": "high-rise: not stated", "elements": [],
               "measure": "high_rise_building"}]
    return {"id": "egress.general.bc_table_1006_3_4_2__a_b_e_f_m_u@L1", "rule": "general.bc_table_1006_3_4_2__a_b_e_f_m_u",
            "group": present.LAW_GROUP, "status": present.REVIEW, "causes": causes, "law_key": "x"}


def test_the_hint_goes_on_the_high_rise_card_and_decides_nothing():
    view = {"items": [_row()]}
    hint = high_rise_hint.words({"height_in": 22 * 12, "level": "Roof", "ground_in": 0})
    ui_data.add(view, rules_by_id={}, laws=[], site=None, values={}, high_rise_hint=hint)
    [item] = view["items"]
    [ask] = item["asks"]
    assert ask["field"] == ui_data.HIGH_RISE_FIELD and ask["hint"] == hint and ask["why"].endswith(hint)
    assert item["status"] == present.REVIEW                         # the row still needs review: nothing decided
    # no hint, no change to the card's words
    plain = {"items": [_row()]}
    ui_data.add(plain, rules_by_id={}, laws=[], site=None, values={})
    assert "hint" not in plain["items"][0]["asks"][0] and plain["items"][0]["asks"][0]["why"] == "high-rise: not stated"


def test_the_fact_stays_unstated_until_the_architect_answers():
    # the building block as a host sends it with no answer: the fact isn't among the measures, so its flags show and
    # the band holds (needs review); stated, it is the architect's answer only
    assert "high_rise_building" not in code_scope.building_measures({"occupancy_groups": ["B"]})
    assert code_scope.building_measures({"occupancy_groups": ["B"], "high_rise_building": False})["high_rise_building"] is False
    import inspect
    src = inspect.getsource(high_rise_hint)
    assert "building_measures" not in src and "high_rise_building\"] =" not in src   # the hint writes no fact
