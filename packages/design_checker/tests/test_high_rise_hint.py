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
    assert "22.0 ft" in words and "Roof" in words and "decided by your answer" in words
    # what would still make it a high-rise, never that it likely isn't one (review round 1 of the marks PR)
    assert "more than 53.0 ft below that ground" in words and "linked model" in words and "occupiable roof" in words
    for said in ("likely", "usually", "a roof level included"):
        assert said not in words
    near = high_rise_hint.words({"height_in": 74.96 * 12, "level": "Roof", "ground_in": 0})
    assert "75.0" not in near and "74.9 ft above" in near and "more than 0.0 ft below" in near   # rounded down
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
    assert "not stated. From the model:" in ask["why"]                # a sentence of its own (marks PR round 2)
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


def test_the_plan_says_both_facts_have_their_marks_now():
    # review round 1 of the marks PR: part b's line still said neither fact had a Revit mark
    from pathlib import Path
    doc = (Path(__file__).resolve().parents[3] / "docs/decisions/2026-11-26_ny_building_chapter_4_egress.md").read_text(
        encoding="utf-8")
    assert "Revit mark yet" not in doc and "likely isn't one" in doc
    for fact in ("high_rise_building", "underground_building"):
        assert code_scope.MARK[fact] in doc, fact


def test_the_figure_rounds_down_past_float_noise_and_never_reads_75():
    # review round 2 of the marks PR: 9.999999999998 ft (Revit's) read 10.9 over ground -1, not 11.0
    for feet, shown in ((70.3, "70.3 ft"), (0.7, "0.7 ft"), (11 - 1.6e-12, "11.0 ft")):
        assert shown + " above" in high_rise_hint.words({"height_in": feet * 12, "level": "L", "ground_in": 0})
    near = high_rise_hint.words({"height_in": 74.999999999998 * 12, "level": "L", "ground_in": 0})
    assert "75.0" not in near and "74.9 ft above" in near


def test_a_room_floor_above_the_highest_level_is_the_figure():
    # review round 2 of the marks PR: a roof terrace drawn on the top level with a base offset is higher still
    levels = [{"id": "L1", "name": "Level 1", "elevation": 0}, {"id": "L4", "name": "Level 4", "elevation": 60}]
    terrace = {"units": "ft", "all_levels": levels, "openings": [],
               "rooms": [{"id": "r1", "name": "Roof terrace", "level": "L4", "floor_elevation": 70}]}
    fig = high_rise_hint.figure(terrace, {"flat": 0})
    assert fig["level"] == "Roof terrace" and "(Roof terrace) is 70.0 ft above" in high_rise_hint.words(fig)
    terrace["rooms"][0]["floor_elevation"] = 78
    assert high_rise_hint.words(high_rise_hint.figure(terrace, {"flat": 0})) is None     # 75 ft or more: no hint
    terrace["rooms"][0]["floor_elevation"] = "up"
    assert high_rise_hint.figure(terrace, {"flat": 0}) is None


def test_a_real_check_hands_the_hint_to_the_cards_and_decides_nothing(monkeypatch):
    """Review round 2 of the marks PR: the four-unit apartment's Revit request, every level sent and flat finished
    ground stated 1 ft under Level 1, through the worker's answer: the check works the figure out from the request's
    own interior and lot facts (Level 2, 9.999999999998 ft, so 11.0 ft) and hands the words to the cards, and the
    answer states no high-rise value."""
    import json
    from pathlib import Path
    from design_checker.__main__ import answer
    folder = Path(__file__).resolve().parents[3] / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment"
    request = json.loads((folder / "revit_check_site_request.json").read_text(encoding="utf-8"))
    request["interior"]["all_levels"] = list(request["interior"]["levels"])
    request["facts"].update({"ground_is_flat": True, "grade_elevation": -1})
    handed, add = [], ui_data.add
    monkeypatch.setattr(ui_data, "add", lambda *a, **k: (handed.append(k.get("high_rise_hint")), add(*a, **k))[1])
    reply = answer(request)
    assert reply["ok"], reply.get("error")
    [hint] = handed
    assert hint and "(Level 2) is 11.0 ft above" in hint and "more than 64.0 ft below" in hint
    text = json.dumps(reply["result"])
    assert '"high_rise_building": false' not in text and '"high_rise_building": true' not in text


def test_an_unread_room_floor_or_a_top_below_the_ground_gives_no_hint():
    # review round 3 of the marks PR: the Revit reader leaves an unread floor out (a slab not found under a terrace);
    # a model whose top is below the ground it states has no figure to give
    levels = [{"id": "L1", "name": "Level 1", "elevation": 0}, {"id": "L4", "name": "Level 4", "elevation": 60}]
    unread = {"units": "ft", "all_levels": levels, "openings": [], "rooms": [{"id": "r1", "name": "Terrace", "level": "L4"}]}
    assert high_rise_hint.figure(unread, {"flat": 0}) is None
    assert high_rise_hint.words({"height_in": -120, "level": "B1", "ground_in": 0}) is None


def test_the_tolerance_is_float_noise_only_never_a_round_up():
    # review round 3 of the marks PR: any tolerance of 0.05 ft or more would round the margin up
    words = high_rise_hint.words({"height_in": 70.26 * 12, "level": "L", "ground_in": 0})
    assert "70.2 ft above" in words and "more than 4.7 ft below" in words
    assert "70.2 ft above" in high_rise_hint.words({"height_in": 70.2999 * 12, "level": "L", "ground_in": 0})
