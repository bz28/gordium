"""The permit sheets' words for a rule's Required and Proposed columns (words.required_and_proposed)."""


def test_an_area_well_size_rows_reach_is_said_in_words_and_its_values_never_round_toward_compliance():
    # PR feat/r319-well-encroachment: R319.4.1's size rules read what reaches into the well; the Required column says
    # it in words (never the formula), and the Proposed column shows each reach, a reach (at most) rounded up and the
    # depth (more than 44 in) rounded down, so a fail never reads as compliant (review round 3)
    from rule_format.rulebook import REPO, load
    from permit_sheets.words import required_and_proposed
    book = load(REPO / "regulations/jurisdictions/new_york/new_york_state/5_building_code_rules/drafted/general.yaml")
    rule = next(r for r in book["rules"] if r["id"] == "general.r319_4_1_area_well_min_width")
    need, have = required_and_proposed(rule, {"area_well_width": 40, "area_well_ladder": True, "area_well_depth": 44.04,
                                              "area_well_ladder_encroachment": 6.04,
                                              "area_well_other_encroachment": 0.04})
    assert need.startswith("area well width 3'-0\" min; nothing else in its required dimensions") and "per formula" not in need
    assert "area well ladder encroachment 6 1/8\"" in have and "area well other encroachment 1/8\"" in have, have
    assert "area well depth over 3'-8\"" in have and "ladder or steps clear of the open window yes" in have, have
    # with nothing reaching in, the ladder and depth decide nothing and aren't shown
    _, have = required_and_proposed(rule, {"area_well_width": 40, "area_well_ladder": False, "area_well_depth": 30,
                                           "area_well_ladder_encroachment": 0, "area_well_other_encroachment": 0})
    assert "clear of the open window" not in have and "depth" not in have, have
    # a depth the checker reads as 44 in (float noise within its tolerance) is never said "over" (review round 5)
    _, have = required_and_proposed(rule, {"area_well_width": 40, "area_well_ladder": True, "area_well_depth": 44 + 1e-7,
                                           "area_well_ladder_encroachment": 3, "area_well_other_encroachment": 0})
    assert "area well depth 3'-8\"" in have and "over" not in have, have
    # a depth the checker can't use (a well floor drawn above the ground, or not a finite number) is printed as it is,
    # never "over", and never stops the sheets being made (review round 6)
    for bad in (-1, float("nan"), float("inf"), 1e308, 10 ** 400, 10 ** 5000, [10 ** 5000], "50", True):
        _, have = required_and_proposed(rule, {"area_well_width": 40, "area_well_ladder": True, "area_well_depth": bad,
                                               "area_well_ladder_encroachment": 3, "area_well_other_encroachment": 0})
        assert "over" not in have, (bad, have)
    # a reach given as a yes/no value isn't 0: the ladder and depth stay shown
    _, have = required_and_proposed(rule, {"area_well_width": 40, "area_well_ladder": True, "area_well_depth": 30,
                                           "area_well_ladder_encroachment": False, "area_well_other_encroachment": 0})
    assert "clear of the open window" in have, have
    # R319.4.2's check reads the ladder alone: never set aside
    ladder = next(r for r in book["rules"] if r["id"] == "general.r319_4_2_area_well_ladder_over_44")
    assert required_and_proposed(ladder, {"area_well_ladder": False})[0] == "yes"
