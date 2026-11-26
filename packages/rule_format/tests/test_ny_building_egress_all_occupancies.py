"""New York's Building Code egress rules for every occupancy group (section group 1 of
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md): each printed row of Table 1017.2 (p.341) and Table
1006.2.1 (p.315), and 1020.5's exceptions (p.344), chart-matched (and 1016.2's intervening spaces, group 2a): every group of every row passes at its limit and
fails just past it, in each column, the values typed here from the page (never read from the rules). A building of
two or more groups, or one whose group isn't stated, never passes. Needs no code cache (the rules' quotes are
checked word for word by `python -m rule_format` where the cache is)."""

import pytest

from rule_format import parts
from rule_format.rulebook import REPO, Context, load

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
RULEBOOK = NY / "5_building_code_rules/drafted/general.yaml"
A = ["A-1", "A-2", "A-3", "A-4", "A-5"]
R = ["R-1", "R-2", "R-3", "R-4"]
S1, S2 = "sprinklered_903_3_1_1", "sprinklered_903_3_1_2"
NFPA13 = {S1: True, S2: False, "sprinklered_903_3_1_3": False}
NONE = {S1: False, S2: False, "sprinklered_903_3_1_3": False}
STATED = {"egress_balcony_increase_taken": False, "assembly_fixed_seating": False, "special_egress_spaces": False,
          "building_has_atrium": False, "merchandise_pads": False}

# Table 1017.2, p.341: line -> (groups, without a sprinkler system (None: Not Permitted), with one, the rule)
TABLE_1017_2 = {
    28: (A + ["E", "F-1", "M"] + R + ["S-1"], 200, 250, "a_e_f1_m_r_s1"),
    29: (["I-1"], None, 250, "i1"),
    30: (["B"], 200, 300, "b"),
    31: (["F-2", "S-2", "U"], 300, 400, "f2_s2_u"),
    32: (["H-1"], None, 75, "h1"),
    33: (["H-2"], None, 100, "h2"),
    34: (["H-3"], None, 150, "h3"),
    35: (["H-4"], None, 175, "h4"),
    36: (["H-5"], None, 200, "h5"),
    37: (["I-2", "I-3"], None, 200, "i2_i3"),
}
# Table 1006.2.1, p.315: line -> (groups, most occupants, common path without a sprinkler system up to 30 and over 30
# occupants (None: NP), with one, the rule)
TABLE_1006_2_1 = {
    21: (A + ["E", "M"], 49, 75, 75, 75, "a_e_m"),
    22: (["B"], 49, 100, 75, 100, "b"),
    23: (["F-1", "F-2"], 49, 75, 75, 100, "f"),
    24: (["H-1", "H-2", "H-3"], 3, None, None, 25, "h1_h2_h3"),
    25: (["H-4", "H-5"], 10, None, None, 75, "h4_h5"),
    26: (["I-1", "I-2"], 10, None, None, 75, "i1_i2"),
    27: (["I-3"], 10, None, None, 100, "i3"),
    28: (["R-1"], 10, None, None, 75, "r1"),
    29: (["R-2"], 20, None, None, 125, "r2"),
    30: (["R-3", "R-4"], 20, None, None, 125, "r3_r4"),
    32: (["S-1", "S-2"], 29, 100, 75, 100, "s"),
    33: (["U"], 49, 100, 75, 75, "u"),
}
EXCEPTION_2 = ["B", "E", "F-1", "F-2", "I-1", "M", "R-1", "R-2", "S-1", "S-2", "U"]   # 1020.5 exception 2 (p.344)


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(NY)


@pytest.fixture(scope="module")
def rules():
    return {r["id"]: r for r in load(RULEBOOK)["rules"]}


def _one(rule, kind, measures, given, ctx):
    [row] = parts.rows(rule, {kind: [{"id": "p1", "measures": measures}]}, given, ctx.allowed())
    return row["outcome"]


def _travel(feet):
    """A story's travel, its sleeping rooms' within 407.4.2's 50 ft (Group I-2)."""
    return {"egress_travel_distance": feet, "egress_travel_in_sleeping_room": 50}


def _cites(rule, page, line):
    return any(s.get("page") == page and s["lines"][0] <= line <= s["lines"][1] for s in rule["sources"])


@pytest.mark.parametrize("line", sorted(TABLE_1017_2))
def test_table_1017_2_each_row_at_its_limit_and_just_past(ctx, rules, line):
    groups, without, with_, slug = TABLE_1017_2[line]
    rule = rules[f"general.bc_table_1017_2_{slug}"]
    assert _cites(rule, 341, line)
    for g in groups:
        given = {"occupancy_group": g} | STATED
        at = "needs_review" if g == "I-3" else "pass"            # 408.6.1's smoke-barrier distances (review round 1)
        over = "needs_review" if g == "S-2" else "fail"          # 1017.3 exception 1: an open parking garage
        assert _one(rule, "story", _travel(with_), given | NFPA13, ctx) == at, (g, with_)
        past = with_ + 0.01 + (100 if g == "H-5" else 150 if g in ("F-1", "S-1") else 0)  # past 1017.2.3, 1017.2.2
        assert _one(rule, "story", _travel(past), given | NFPA13, ctx) == over, (g, past)
        if without is None:          # Not Permitted without a sprinkler system, whatever the distance
            assert _one(rule, "story", _travel(1), given | NONE, ctx) == "fail", g
        else:
            assert _one(rule, "story", _travel(without), given | NONE, ctx) == "pass", g
            assert _one(rule, "story", _travel(without + 0.01), given | NONE, ctx) == over, g
    other = next(g for g in ("B", "M") if g not in groups)
    assert _one(rule, "story", {"egress_travel_distance": 10}, {"occupancy_group": other} | NFPA13, ctx) == \
        "not_applicable"


def test_an_nfpa_13r_system_counts_only_in_group_r(ctx, rules):
    """Note b: 903.3.1.1 or 903.3.1.2, and 903.3.1.2 (p.274) permits NFPA 13R in Group R only: an apartment floor
    gets 250 ft with it; a shop within 250 ft only by it needs review; note c (B) gives a 13R system nothing."""
    row = rules["general.bc_table_1017_2_a_e_f1_m_r_s1"]
    nfpa_13r = {S1: False, S2: True} | STATED
    assert _one(row, "story", {"egress_travel_distance": 250}, {"occupancy_group": "R-2"} | nfpa_13r, ctx) == "pass"
    assert _one(row, "story", {"egress_travel_distance": 250}, {"occupancy_group": "M"} | nfpa_13r, ctx) == \
        "needs_review"
    assert _one(rules["general.bc_table_1017_2_b"], "story", {"egress_travel_distance": 250},
                {"occupancy_group": "B"} | nfpa_13r, ctx) == "fail"


def test_an_allowance_not_ruled_out_never_fails_within_it(ctx, rules):
    """Over the row's distance, within an increase whose conditions aren't measured or stated (1017.2.1's balcony,
    1017.2.2's F-1/S-1, 1017.2.3's H-5, Group A's assembly seating): needs review, never fail."""
    row = rules["general.bc_table_1017_2_a_e_f1_m_r_s1"]
    r2 = {"occupancy_group": "R-2"} | NONE
    assert _one(row, "story", {"egress_travel_distance": 300}, r2 | {"assembly_fixed_seating": False}, ctx) == \
        "needs_review"                                                       # the balcony increase not stated
    assert _one(row, "story", {"egress_travel_distance": 300}, r2 | STATED, ctx) == "fail"
    assert _one(row, "story", {"egress_travel_distance": 300.01}, r2 | STATED | {"egress_balcony_increase_taken": True},
                ctx) == "fail"                                               # past the 100 ft more too
    assert _one(row, "story", {"egress_travel_distance": 390}, {"occupancy_group": "S-1"} | NFPA13 | STATED, ctx) == \
        "needs_review"
    assert _one(row, "story", {"egress_travel_distance": 260}, {"occupancy_group": "A-2"} | NFPA13 |
                {"egress_balcony_increase_taken": False}, ctx) == "needs_review"
    h5 = rules["general.bc_table_1017_2_h5"]
    assert _one(h5, "story", {"egress_travel_distance": 280}, {"occupancy_group": "H-5"} | NFPA13 | STATED, ctx) == \
        "needs_review"


@pytest.mark.parametrize("line", sorted(TABLE_1006_2_1))
def test_table_1006_2_1_each_row_at_its_limits_and_just_past(ctx, rules, line):
    groups, most, up_to_30, over_30, with_, slug = TABLE_1006_2_1[line]
    rule = rules[f"general.bc_table_1006_2_1_{slug}"]
    assert _cites(rule, 315, line)
    for g in groups:
        given = {"occupancy_group": g} | STATED
        one = {"space_is_exit": False, "space_exit_count": 1}
        at = "needs_review" if g == "I-2" else "pass"                       # note d: 407.4, a person's check
        assert _one(rule, "space", one | {"space_occupant_load": most, "space_common_path": with_}, given | NFPA13,
                    ctx) == at, g
        assert _one(rule, "space", one | {"space_occupant_load": most + 0.5, "space_common_path": 1}, given | NFPA13,
                    ctx) == "fail", g
        note_e = "needs_review" if g in ("R-3", "R-4") else "fail"    # note e: common path only if mixed
        assert _one(rule, "space", one | {"space_occupant_load": 1, "space_common_path": with_ + 0.01},
                    given | NFPA13, ctx) == note_e, g
        if up_to_30 is None:         # NP without a sprinkler system (R-3, R-4: note e, a person's check)
            np_ = "needs_review" if g in ("R-3", "R-4") else "fail"
            assert _one(rule, "space", one | {"space_occupant_load": 1, "space_common_path": 1}, given | NONE,
                        ctx) == np_, g
        else:
            assert _one(rule, "space", one | {"space_occupant_load": min(30, most), "space_common_path": up_to_30},
                        given | NONE, ctx) == "pass", g
            assert _one(rule, "space", one | {"space_occupant_load": min(30, most),
                                              "space_common_path": up_to_30 + 0.01}, given | NONE, ctx) == "fail", g
            if most > 30:
                assert _one(rule, "space", one | {"space_occupant_load": 31, "space_common_path": over_30},
                            given | NONE, ctx) == "pass", g
                assert _one(rule, "space", one | {"space_occupant_load": 31, "space_common_path": over_30 + 0.01},
                            given | NONE, ctx) == "fail", g
        two = {"space_is_exit": False, "space_exit_count": 2, "space_occupant_load": 400}
        assert _one(rule, "space", two | {"space_common_path": with_}, given | NFPA13, ctx) == "pass", g
        assert _one(rule, "space", two | {"space_common_path": with_ + 0.01}, given | NFPA13, ctx) == "needs_review", g


def test_a_stair_enclosure_is_not_a_space_the_table_counts_and_an_unknown_one_never_passes(ctx, rules):
    rule = rules["general.bc_table_1006_2_1_r2"]
    r2 = {"occupancy_group": "R-2"} | NONE
    apartment = {"space_exit_count": 1}
    assert _one(rule, "space", apartment | {"space_is_exit": True}, r2, ctx) == "pass"
    assert _one(rule, "space", apartment | {"space_is_exit": False}, r2, ctx) == "fail"   # NP, whatever its load
    assert _one(rule, "space", apartment, r2, ctx) == "needs_review"                     # not known: never a fail


def test_dead_ends_for_every_group_but_i4(ctx, rules):
    """1020.5 (p.344): 20 ft; 50 ft in exception 2's groups with NFPA 13 (903.3.1.1, not 13R); under 2.5 x the least
    width for any group; Groups I-3 and I-2 within their exceptions' 50 and 30 ft need review."""
    rule = rules["general.bc_1020_5_dead_end_other_groups"]
    groups = load(NY / "5_building_code_rules/drafted/records/proposed_measures.yaml")["occupancy_group"]["values"]
    for g in groups:
        if g in ("I-4", "mixed"):
            continue
        given = {"occupancy_group": g}
        limit = 50 if g in EXCEPTION_2 else 20
        assert _one(rule, "corridor", {"corridor_dead_end_length": limit, "corridor_dead_end_least_width": 5},
                    given | NFPA13, ctx) == "pass", g
        if g in ("I-2", "I-3"):      # within exception 4's 30 ft or 1's 50 ft: their conditions aren't stated
            within = 30 if g == "I-2" else 50
            assert _one(rule, "corridor", {"corridor_dead_end_length": within, "corridor_dead_end_least_width": 5},
                        given | NFPA13, ctx) == "needs_review", g
        past = 50.01 if g == "I-3" else 30.01 if g == "I-2" else limit + 0.01
        assert _one(rule, "corridor", {"corridor_dead_end_length": past, "corridor_dead_end_least_width": 5},
                    given | NFPA13, ctx) == "fail", g
        assert _one(rule, "corridor", {"corridor_dead_end_length": 20.01, "corridor_dead_end_least_width": 5},
                    given | {S1: False, S2: True}, ctx) == ("needs_review" if g in ("I-2", "I-3") else "fail"), g
        assert _one(rule, "corridor", {"corridor_dead_end_length": 60, "corridor_dead_end_least_width": 24.01},
                    given | NONE, ctx) == "pass", g                                    # exception 3
    assert _one(rule, "corridor", {"corridor_dead_end_length": 30}, {"occupancy_group": "I-4"} | NFPA13, ctx) == \
        "not_applicable"


ROW_RULES = [f"general.bc_table_1017_2_{v[3]}" for v in TABLE_1017_2.values()] + \
            [f"general.bc_table_1006_2_1_{v[5]}" for v in TABLE_1006_2_1.values()] + \
            ["general.bc_1020_5_dead_end_other_groups", "general.bc_1016_2_intervening_spaces_other_groups"]


def test_a_mixed_or_unstated_building_never_passes_a_row_and_its_flags_show(ctx, rules):
    kinds = {"story": {"egress_travel_distance": 5}, "space": {"space_is_exit": False, "space_exit_count": 3,
                                                               "space_occupant_load": 3, "space_common_path": 5},
             "corridor": {"corridor_dead_end_length": 5, "corridor_dead_end_least_width": 5}}
    kinds["space"] |= {"space_egress_through_locked_room": 0, "space_egress_through_kitchen_storage": 0,
                       "space_egress_sleeping_through_sleeping_or_toilet": 0, "space_egress_through_other_room": 0,
                       "space_egress_through_electrically_locked_lobby": 0}
    for rid in ROW_RULES:
        r = rules[rid]
        assert _one(r, r["for_each"], kinds[r["for_each"]], {"occupancy_group": "mixed"} | NFPA13, ctx) == \
            "not_applicable", rid
        assert _one(r, r["for_each"], kinds[r["for_each"]], NFPA13, ctx) == "needs_review", rid
    from rule_format.rulebook import outcome
    for rid in ("general.bc_table_1017_2_other_occupancies", "general.bc_table_1006_2_1_other_occupancies",
                "general.bc_1020_5_other_occupancies", "general.bc_1016_2_other_occupancies"):
        assert outcome(rules[rid], {"occupancy_group": "mixed"}, ctx.allowed()) == "needs_review", rid
        assert outcome(rules[rid], {"occupancy_group": "R-2"}, ctx.allowed()) == "not_applicable", rid
        assert outcome(rules[rid], {}, ctx.allowed()) == "needs_review", rid


def test_every_group_has_a_travel_and_a_one_exit_row_and_one_only(rules):
    groups = [g for g in load(NY / "5_building_code_rules/drafted/records/proposed_measures.yaml")
              ["occupancy_group"]["values"] if g not in ("mixed", "I-4")]
    for table in (TABLE_1017_2, TABLE_1006_2_1):
        rows = [v[0] for v in table.values()]
        assert sorted(g for row in rows for g in row) == sorted(groups)


def test_an_occupancy_group_the_list_doesnt_hold_is_refused(ctx, rules):
    from rule_format.rulebook import _rule_problems
    bad = dict(rules["general.bc_table_1017_2_b"], applies_when='occupancy_group in ["Group B"]')
    assert any("unknown occupancy_group 'Group B'" in p for p in _rule_problems(bad, "general", ctx))
    assert not any("occupancy_group" in p for p in _rule_problems(rules["general.bc_table_1017_2_b"], "general", ctx))


def test_intervening_spaces_for_every_group_but_i4(ctx, rules):
    """1016.2 (pp.340-341) for every group but I-4: a lockable room, a bathroom or another sleeping area, a kitchen
    or storage room crossed fails; item 6's exceptions (a kitchen of the same dwelling or sleeping unit; a Group M
    stockroom) and items 2 and 3 (an accessory intervening room) need review where they are all that fails."""
    rule = rules["general.bc_1016_2_intervening_spaces_other_groups"]
    clear = {"space_egress_through_locked_room": 0, "space_egress_through_kitchen_storage": 0,
             "space_egress_sleeping_through_sleeping_or_toilet": 0, "space_egress_through_other_room": 0,
             "space_egress_through_electrically_locked_lobby": 0}
    kitchen = clear | {"space_egress_through_kitchen_storage": 1}
    for g in ("A-2", "B", "E", "M", "R-2", "S-1"):
        assert _one(rule, "space", clear, {"occupancy_group": g}, ctx) == "pass", g
        assert _one(rule, "space", clear | {"space_egress_through_locked_room": 1}, {"occupancy_group": g}, ctx) == \
            "fail", g
        assert _one(rule, "space", clear | {"space_egress_through_other_room": 1}, {"occupancy_group": g}, ctx) == \
            "needs_review", g
        want = "needs_review" if g in ("M", "R-2") else "fail"
        assert _one(rule, "space", kitchen, {"occupancy_group": g}, ctx) == want, g
    assert _one(rule, "space", kitchen | {"space_egress_through_locked_room": 1}, {"occupancy_group": "M"}, ctx) == \
        "fail"
    assert _one(rule, "space", clear, {"occupancy_group": "I-4"}, ctx) == "not_applicable"
    assert _one(rule, "space", clear, {"occupancy_group": "mixed"}, ctx) == "not_applicable"


# ---- review round 1 (2026-11-23): every cross-reference of a drafted table has a handler -----------------------------

import json
import re

# Each drafted piece's lines (the sections file) that must all be quoted somewhere in the rulebook, so a reference
# in them can't go unseen; and each section a reference names -> (the rule that handles it, a word its text holds)
SCOPE = {"Table 1017.2": (341, 28, 59), "Table 1006.2.1": (315, 21, 44), "1006.2.1": (315, 3, 13),
         "1017.2": (341, 23, 23), "1020.5": (344, 37, 47),
         # section group 4: the corridor sections and tables drafted
         "1020.2": (343, 40, 53), "Table 1020.2": (344, 7, 18), "1020.3": (344, 21, 24), "Table 1020.3": (344, 27, 34),
         "1020.4": (344, 35, 36), "1020.6": (344, 48, 53), "1020.6 (part 2)": (345, 3, 6), "1020.7": (345, 17, 23),
         "1020.6.1": (345, 7, 16),
         # section group 5a: egress capacity
         "1005.3.1": (313, 51, 55), "1005.3.1 (part 2)": (314, 3, 13), "1005.3.2": (314, 14, 28),
         "1005.4": (314, 29, 30), "1005.5": (314, 31, 33), "1005.6": (314, 34, 36),       # section group 5b
         "1005.7": (314, 37, 38), "1005.7.1": (314, 39, 49), "1005.7.2": (314, 50, 53),
         "1005.7.3": (314, 54, 54),
         "1010.1": (322, 28, 36), "1010.1.1": (322, 37, 58), "1010.1.1 (part 2)": (323, 3, 5),
         "1010.1.1.1": (323, 6, 10),
         "1010.1.2": (323, 11, 23), "1010.1.2.1": (323, 24, 25),
         # section group 6c: the rest of 1010.1
         "1010.1.3": (323, 26, 36), "1010.1.3.1": (323, 37, 37), "1010.1.3.2": (323, 38, 39),
         "1010.1.4": (323, 40, 56), "1010.1.4 (part 2)": (324, 3, 5), "1010.1.5": (324, 6, 11),
         "1010.1.6": (324, 12, 25), "1010.1.7": (324, 26, 32),
         # section group 6d: 1010.2 to 1010.2.7 and Table 1010.2.4
         "1010.2": (324, 33, 34), "1010.2.1": (324, 35, 40), "1010.2.2": (324, 41, 42), "1010.2.3": (324, 43, 48),
         "1010.2.4": (324, 49, 58), "1010.2.4 (part 2)": (325, 3, 35), "Table 1010.2.4": (325, 36, 61),
         "1010.2.5": (326, 3, 3), "1010.2.6": (326, 4, 22), "1010.2.7": (326, 23, 30),
         # section group 9a: 1003 (general means of egress) and 1012 (ramps), each a flag quoting its piece whole
         "1003.2": (310, 35, 46), "1003.3": (310, 47, 48), "1003.3.1": (310, 49, 53), "1003.3.1 (part 2)": (311, 3, 4),
         "1003.3.2": (311, 5, 11), "1003.3.3": (311, 12, 14), "1003.3.4": (311, 15, 15), "1003.4": (311, 16, 16),
         "1003.5": (311, 17, 31), "1003.6": (311, 32, 35), "1003.7": (311, 36, 38), "1012.1": (335, 23, 29),
         "1012.2": (335, 30, 32),
         "1012.3": (335, 33, 34), "1012.4": (335, 35, 35), "1012.5": (335, 36, 37), "1012.5.1": (335, 38, 40),
         "1012.5.2": (335, 41, 43), "1012.5.3": (335, 44, 46), "1012.6": (335, 47, 48), "1012.6.1": (335, 49, 50),
         "1012.6.2": (335, 51, 51), "1012.6.3": (335, 52, 57), "1012.6.4": (336, 3, 6), "1012.6.5": (336, 7, 8),
         "1012.7": (336, 9, 10), "1012.7.1": (336, 11, 11), "1012.7.2": (336, 12, 13), "1012.8": (336, 14, 15), "1012.9": (336, 16, 16),
         "1012.10": (336, 17, 24), "1012.10.1": (336, 25, 27), "1012.10.2": (336, 28, 29),
         # section group 9b: 1008 (means of egress illumination) and 1013 (exit signs), each a flag quoting its piece
         "1008.1": (318, 31, 32), "1008.2": (318, 33, 40), "1008.2.1": (318, 41, 49), "1008.2.2": (318, 50, 52),
         "1008.2.3": (318, 53, 57), "1008.2.4": (319, 3, 4), "1008.3": (319, 5, 22), "1008.3.1": (319, 23, 25),
         "1008.3.2": (319, 26, 31), "1013.1": (336, 31, 45), "1013.2": (336, 46, 52), "1013.3": (336, 53, 54),
         "1013.4": (336, 55, 57), "1013.5": (337, 3, 5), "1013.5.1": (337, 6, 7), "1013.6": (337, 8, 8),
         "1013.6.1": (337, 9, 16), "1013.6.2": (337, 17, 18), "1013.6.3": (337, 19, 26),
         # section group 9c
         "1009.1": (319, 33, 41), "1009.2": (319, 42, 53), "1009.2.1": (319, 54, 57), "1009.2.1 (part 2)": (320, 3, 8),
         "1009.2.2": (320, 9, 14), "1009.3": (320, 15, 16), "1009.3.1": (320, 17, 20), "1009.3.2": (320, 21, 26),
         "1009.3.3": (320, 27, 38), "1009.4": (320, 39, 40), "1009.4.1": (320, 41, 42), "1009.4.2": (320, 43, 51),
         "1009.5": (320, 52, 54), "1009.6": (320, 55, 55), "1009.6.1": (320, 56, 57), "1009.6.2": (321, 3, 5),
         "1009.6.3": (321, 6, 9), "1009.6.4": (321, 10, 15), "1009.6.5": (321, 16, 17), "1009.7": (321, 18, 21),
         "1009.7.1": (321, 22, 23), "1009.7.2": (321, 24, 32), "1009.7.3": (321, 33, 35), "1009.7.4": (321, 36, 39),
         "1009.8": (321, 40, 52), "1009.8.1": (321, 53, 58), "1009.8.2": (322, 3, 5), "1009.9": (322, 6, 14),
         "1009.10": (322, 15, 19), "1009.11": (322, 20, 26),
         # section group 9d
         "1018.1": (342, 40, 44), "1018.2": (342, 45, 46), "1018.3": (342, 47, 50), "1018.5": (343, 3, 7),
         "1019.1": (343, 9, 11), "1019.2": (343, 12, 12), "1019.3": (343, 13, 32), "1019.4": (343, 33, 36),
         # section group 9e: 1021 (egress balconies), 1022 (exits), 1023 (interior exit stairways and ramps)
         "1021.1": (345, 25, 26), "1021.2": (345, 27, 30), "1021.3": (345, 31, 32), "1021.4": (345, 33, 39),
         "1022.1": (345, 41, 44), "1022.2": (345, 45, 46), "1022.2.1": (345, 47, 47), "1022.2.2": (345, 48, 48),
         "1023.1": (345, 50, 54), "1023.2": (345, 55, 56), "1023.2 (part 2)": (346, 3, 10), "1023.3": (346, 11, 14),
         "1023.3.1": (346, 15, 26), "1023.4": (346, 27, 30), "1023.5": (346, 31, 44), "1023.6": (346, 45, 56),
         "1023.7": (346, 57, 58), "1023.7 (part 2)": (347, 3, 5), "1023.7.1": (347, 6, 10),
         "1023.7.2": (347, 11, 22), "1023.8": (347, 23, 25), "1023.9": (347, 26, 30), "1023.9.1": (347, 31, 41),
         "1023.10": (347, 42, 44), "1023.11": (347, 45, 47), "1023.12": (347, 48, 49), "1023.12.1": (347, 50, 60),
         "1023.12.1 (part 2)": (348, 3, 4), "1023.12.2": (348, 5, 8), "1023.13": (348, 9, 9)}                       # section group 6b                                                       # section group 5c      # review round 1 of group 4c: its five conditions quoted too
ROWS_1017 = [f"general.bc_table_1017_2_{v[3]}" for v in TABLE_1017_2.values()]
HANDLERS = {
    # Table 1017.2 note a's sections, and its notes b to e
    "402.8": (ROWS_1017, "402.8"), "407.4": ("general.bc_table_1017_2_i2_i3", "407.4.2"),
    "408.6.1": ("general.bc_table_1017_2_i2_i3", "408.6.1"), "408.8.1": ("general.bc_table_1017_2_i2_i3", "408.6.1"),
    "411.2": (ROWS_1017, "411.2"), "412.6": (ROWS_1017, "412.6"), "1006.2.2.2": (ROWS_1017, "1006.2.2.2"),
    "1006.2.2.3": (ROWS_1017, "1006.2.2.3"), "1006.3.4": ("general.bc_1006_3_3_story_exits", "1006.3.4"),
    "407.4.2": ("general.bc_407_4_2_sleeping_room_travel", "407.4.2"),
    "1017.2.2": ("general.bc_table_1017_2_a_e_f1_m_r_s1", "1017.2.2"),
    "1017.2.3": ("general.bc_table_1017_2_h5", "1017.2.3"),
    "1030.7": ("general.bc_table_1017_2_a_e_f1_m_r_s1", "1030.7"), "3103.4": (ROWS_1017, "3103.4"),
    "3104.9": (ROWS_1017, "3104.9"), "903.3.1.1": (ROWS_1017, "sprinklered_903_3_1_1"),
    "903.3.1.2": ("general.bc_table_1017_2_a_e_f1_m_r_s1", "903.3.1.2"),
    "903.2.5.1": ("general.bc_table_1017_2_note_d_group_h", "903.2.5.1"),
    "903.3.1.3": ("general.bc_table_1017_2_a_e_f1_m_r_s1", "sprinklered_903_3_1_3"),
    "903.2.8": ("general.bc_table_1017_2_a_e_f1_m_r_s1", "1006.2.2.6"),
    # Table 1006.2.1's notes, and 1006.2.1's own
    "903.2.5": ("general.bc_table_1017_2_note_d_group_h", "903.2.5"),
    "1030.8": ("general.bc_table_1006_2_1_a_e_m", "1030.8"), "1006.2.2.1": ("general.bc_table_1006_2_1_b", "1006.2.2"), "1006.2.2.6": ("general.bc_table_1006_2_1_r3_r4", "1006.2.2.6"),
    "1004.2": ("general.bc_1006_2_1_two_exits", "1004.2"),
    # section group 4: 1020.2, Table 1020.2's notes, 1020.3
    "708": ("general.bc_1020_2_fire_partitions", "708"), "705.5": ("general.bc_1020_2_fire_partitions", "705.5"),
    "705.9": ("general.bc_1020_2_fire_partitions", "705.9"),
    "1006.2": ("general.bc_table_1020_2_a_b_e_f_m_s_u", "one means of egress"),
    "407.2": ("general.bc_table_1020_2_note_a_group_i2", "407.2"),
    "407.3": ("general.bc_table_1020_2_note_a_group_i2", "407.3"),
    "408.8": ("general.bc_table_1020_2_i1_i3", "408.8"),
    "903.2.8": ("general.bc_table_1020_2_r", "903.2.8"),
    "1005.1": ("general.bc_1020_3_corridor_capacity", "1005.1"),
    # section group 4c: the rest of Section 1020
    "1005.7": ("general.bc_1020_4_obstruction", "1005.7"), "1016.2": ("general.bc_1020_7_continuity", "1016.2"),
    # section group 5a: 1005.3.1 and 1005.3.2's exceptions
    "907.5.2.2": ("general.bc_1020_3_corridor_capacity", "907.5.2.2"),
    "1030.6.2": ("general.bc_1020_3_corridor_capacity", "1030.6.2"),
    "1030.6.3": ("general.bc_1020_3_corridor_capacity", "1030.6.3"), "909": ("general.bc_1020_3_corridor_capacity", "909"),
    # section group 5c: 1005.7's
    "1014.9": ("general.bc_1005_7_2_projections", "1014.9"), "407.4.3": ("general.bc_1005_7_2_projections", "407.4.3"),
    "1003.3": ("general.bc_1005_7_3_protruding_objects", "1003.3"),
    # section group 6a: 1010.1's and 1010.1.1's (the rest of 1010, gates, turnstiles, exterior exit doors: flagged;
    # a shower compartment's door per the Plumbing Code: the width rule's compartment review)
    "1010.3.4": ("general.bc_1010_1_doors_general", "1010.3.4"), "1022.2": ("general.bc_1010_1_doors_general", "1022.2"),
    "1010.4": ("general.bc_1010_1_doors_general", "1010.4"), "1010.4.1": ("general.bc_1010_1_doors_general", "1010.4.1"),
    "1010.5": ("general.bc_1010_1_doors_general", "1010.5"), "1010.5.4": ("general.bc_1010_1_doors_general", "1010.5.4"),
    "421.4.2": ("general.bc_1010_1_1_door_width", "421.4.2"), "421": ("general.bc_1010_1_1_door_width", "421.4.2"),
    # section group 6b: 1010.1.2's exceptions 5 to 7 (revolving, power-operated, special-purpose sliding doors)
    "1010.3.1": ("general.bc_1010_1_2_door_types", "1010.3.1"), "1010.3.2": ("general.bc_1010_1_2_door_types", "1010.3.2"),
    "1010.3.3": ("general.bc_1010_1_2_door_types", "1010.3.3"),
    # section group 6c: 1010.1.4's exception 6 (equipment spaces not required to be accessible)
    "1103.2.9": ("general.bc_1010_1_4_floor_elevation", "1103.2.9"),
    # section group 6d: pool barriers, two-way communication, the posted load, fire door assemblies, high-rise stairs
    "3109.2.7": ("general.bc_1010_2_3_hardware_height", "3109.2.7"),
    "3109.2.8": ("general.bc_1010_2_3_hardware_height", "3109.2.8"),
    "1009.8.1": ("general.bc_1010_2_4_locks_and_latches", "1009.8.1"),
    "1009.8.2": ("general.bc_1010_2_4_locks_and_latches", "1009.8.2"),
    "1004.9": ("general.bc_1010_2_4_locks_and_latches", "1004.9"),
    "716": ("general.bc_table_1010_2_4_inactive_leaf_bolts", "716"),
    "403.5.3": ("general.bc_1010_2_6_stairway_doors", "403.5.3"),
    # section group 9a: 1003.2's exceptions (each only loosens the 7 ft 6 in; the flag never passes), 1003.5's
    # exceptions and its stair, handrail and seating-aisle references, 1003.7's elevators (section group 9c's 1009)
    "1011.3": ("general.bc_1003_2_ceiling_height", "1011.3"), "1208.2": ("general.bc_1003_2_ceiling_height", "1208.2"),
    "406.2.2": ("general.bc_1003_2_ceiling_height", "406.2.2"), "505.2": ("general.bc_1003_2_ceiling_height", "505.2"),
    "1011.5": ("general.bc_1003_5_elevation_change", "1011.5"),
    "1030.14": ("general.bc_1003_5_elevation_change", "1030.14"),
    "1030.16": ("general.bc_1003_5_elevation_change", "1030.16"),
    "1009.4": ("general.bc_1003_7_elevators_escalators_moving_walks", "1009.4"),
    # section group 9b: 1008.2.1's self-luminous markings, 1008.2.3's dispersal area, 1008.3's discharge areas
    "1025.2.1": ("general.bc_1008_2_1_illumination_level", "1025.2.1"),
    "1025.2.2": ("general.bc_1008_2_1_illumination_level", "1025.2.2"),
    "1025.2.4": ("general.bc_1008_2_1_illumination_level", "1025.2.4"),
    "1028.5": ("general.bc_1008_2_3_exit_discharge_illumination", "1028.5"),
    "1028.2": ("general.bc_1008_3_emergency_illumination", "1028.2"),
    # section group 9c
    "1006.3": ("general.bc_1009_1_accessible_means_of_egress_required", "1006.3"),
    "1019.3": ("general.bc_1009_2_continuity_and_components", "1019.3"),
    "1019.4": ("general.bc_1009_2_continuity_and_components", "1019.4"),
    "712": ("general.bc_1009_4_2_elevator_area_of_refuge", "712"),
    "1110.11": ("general.bc_1009_5_platform_lifts", "1110.11"),
    "1017.1": ("general.bc_1009_6_1_area_of_refuge_travel_distance", "1017.1"),
    "709": ("general.bc_1009_6_4_area_of_refuge_separation", "709"),
    # section group 9d
    "404": ("general.bc_1019_3_exit_access_stairway_enclosure", "404"),
    "712.1.9": ("general.bc_1019_3_exit_access_stairway_enclosure", "712.1.9"),
    "713": ("general.bc_1019_3_exit_access_stairway_enclosure", "713"),
    "408": ("general.bc_1019_4_exit_access_stairways_groups_i2_i3", "408"),
    # section group 9e (716 and 1028.2 handled above, by 6d's and 9b's flags; 1023.4's, 1023.6's and 1023.1's
    # flags name them too)
    "705": ("general.bc_1021_4_egress_balcony_location", "705"),
    "707": ("general.bc_1023_2_enclosure_construction", "707"),
    "711": ("general.bc_1023_2_enclosure_construction", "711"),
    "408.3.8": ("general.bc_1023_2_enclosure_construction", "408.3.8"),
    "404.6": ("general.bc_1023_2_enclosure_construction", "404.6"),
    "510.2": ("general.bc_1023_2_enclosure_construction", "510.2"),
    "909.20.4": ("general.bc_1023_3_1_extension", "909.20.4"),
    "714": ("general.bc_1023_5_penetrations", "714"),
    "714.4.2": ("general.bc_1023_5_penetrations", "714.4.2"),
    "1025.4": ("general.bc_1023_9_1_stairway_sign_requirements", "1025.4"),
    "403.5.4": ("general.bc_1023_12_smokeproof_enclosures", "403.5.4"),
    "405.7.2": ("general.bc_1023_12_smokeproof_enclosures", "405.7.2"),
    "412.2.2.1": ("general.bc_1023_12_smokeproof_enclosures", "412.2.2.1"),
    "909.20": ("general.bc_1023_12_smokeproof_enclosures", "909.20"),
    "905.3": ("general.bc_1023_13_standpipes", "905.3"),
    "905.4": ("general.bc_1023_13_standpipes", "905.4"),
}
NO_LIMIT = {"1006.2.1", "1017.2", "1020.5", "1020.2", "1020.3", "1020.4", "1020.6", "1020.7", "1020.6.1", "1005.3.1", "1005.3.2", "1005.4", "1005.5", "1005.6", "1005.7",
            "1005.7.1", "1005.7.2", "1005.7.3", "1010.1", "1010.1.1", "1010.1.1.1", "1010.1.2",
            "1010.1.2.1", "1010.1.3", "1010.1.3.1", "1010.1.3.2", "1010.1.4", "1010.1.5", "1010.1.6",
            "1010.1.7", "1010.2", "1010.2.1", "1010.2.2", "1010.2.3", "1010.2.4", "1010.2.5", "1010.2.6", "1010.2.7",
            "1003.2", "1003.3", "1003.3.1", "1003.3.2", "1003.3.3", "1003.3.4", "1003.4", "1003.5", "1003.6", "1003.7",
            "1012.1", "1012.2", "1012.3", "1012.4", "1012.5", "1012.5.1", "1012.5.2", "1012.5.3", "1012.6", "1012.6.1",
            "1012.6.2", "1012.6.3", "1012.6.4", "1012.6.5", "1012.7", "1012.7.1", "1012.7.2", "1012.8", "1012.9", "1012.10",
            "1012.10.1", "1012.10.2",
            "1008.1", "1008.2", "1008.2.1", "1008.2.2", "1008.2.3", "1008.2.4", "1008.3", "1008.3.1", "1008.3.2",
            "1013.1", "1013.2", "1013.3", "1013.4", "1013.5", "1013.5.1", "1013.6", "1013.6.1", "1013.6.2", "1013.6.3",
            "1009.1", "1009.10", "1009.11", "1009.2", "1009.2.1", "1009.2.2", "1009.3", "1009.3.1", "1009.3.2", "1009.3.3", "1009.4", "1009.4.1", "1009.4.2", "1009.5", "1009.6", "1009.6.1", "1009.6.2", "1009.6.3", "1009.6.4", "1009.6.5", "1009.7", "1009.7.1", "1009.7.2", "1009.7.3", "1009.7.4", "1009.8", "1009.8.1", "1009.8.2", "1009.9",
            "1018.1", "1018.2", "1018.3", "1018.5", "1019.1", "1019.2", "1019.3", "1019.4",
            "1021.1", "1021.2", "1021.3", "1021.4", "1022.1", "1022.2", "1022.2.1", "1022.2.2", "1023.1", "1023.2", "1023.3", "1023.3.1", "1023.4", "1023.5", "1023.6", "1023.7", "1023.7.1", "1023.7.2", "1023.8", "1023.9", "1023.9.1", "1023.10", "1023.11", "1023.12", "1023.12.1", "1023.12.2", "1023.13"}          # the piece naming itself
# lines that name no section and set nothing: 'For SI' and 'NP =' (Table 1006.2.1), 'For SI' (Table 1017.2),
# 'Exceptions:' (1020.5)
UNQUOTED = {(315, 34), (315, 35), (341, 39), (344, 39),
            (343, 42), (344, 34),       # group 4: 1020.2's 'Exceptions:', Table 1020.3's 'For SI'
            (344, 49), (345, 21),       # group 4c: 1020.6's and 1020.7's 'Exceptions:'
            (313, 55), (314, 17),       # group 5a: 1005.3.1's and 1005.3.2's 'Exceptions:'
            (314, 41)}                  # group 5c: 1005.7.1's 'Exceptions:'


def _quoted(book, page, a, b):
    lines = set()
    text = []
    for r in book["rules"]:
        for s in r.get("sources") or []:
            if s.get("page") == page and s["lines"][1] >= a and s["lines"][0] <= b:
                lines |= set(range(s["lines"][0], s["lines"][1] + 1))
                text.append(s["quote"])
    return lines, " ".join(text)


def test_every_cross_reference_in_a_drafted_piece_has_a_handler(rules):
    """A section a drafted table's notes (or its section) name may tighten its limit for some condition: each has a
    rule or a review that handles it, named here, so a reference added without one fails."""
    book = load(RULEBOOK)
    for piece, (page, a, b) in SCOPE.items():
        lines, text = _quoted(book, page, a, b)
        missing = [n for n in range(a, b + 1) if n not in lines and (page, n) not in UNQUOTED]
        assert not missing, (piece, missing)            # every line quoted (but those that name no section)
        refs = set(re.findall(r"\b\d{3,4}(?:\.\d+)+\b|(?<=Section )\d{3}\b", text)) - NO_LIMIT
        refs = {x for x in refs if not re.fullmatch(r"\d+\.\d", x) or x.count(".") > 1 or len(x) > 4}
        for ref in sorted(refs):
            if ref in ("903", "304.8", "1.0", "0.5"):
                continue
            assert ref in HANDLERS, (piece, ref)
    for ref, (rids, word) in HANDLERS.items():
        for rid in [rids] if isinstance(rids, str) else rids:
            assert word in json.dumps(rules[rid]), (ref, rid, word)


def test_a_fixed_seat_assembly_space_never_passes_on_the_tables_common_path(ctx, rules):
    """Review round 1, P0: Table 1006.2.1 note c sends an assembly space with fixed seating to 1030.8 (p.355): 30 ft
    from any seat (75 ft under 50 occupants), whatever the number of exits; with fixed seating stated or not ruled out,
    a space over it needs review, never a pass on the table's 75 ft."""
    r = rules["general.bc_table_1006_2_1_a_e_m"]
    two = {"space_is_exit": False, "space_exit_count": 2, "space_occupant_load": 300, "space_common_path": 60}
    base = {"occupancy_group": "A-1", "special_egress_spaces": False, "merchandise_pads": False} | NFPA13
    assert _one(r, "space", two, base | {"assembly_fixed_seating": True}, ctx) == "needs_review"
    assert _one(r, "space", two, base, ctx) == "needs_review"                       # not stated
    # review round 3: the common path is exit access travel (202), measured along the aisles (1030.7): with fixed
    # seating it needs review at any length, in any group; a measured fail still fails
    assert _one(r, "space", two | {"space_common_path": 10}, base | {"assembly_fixed_seating": True}, ctx) ==         "needs_review"
    for g in ("E", "B", "M"):
        rr = rules["general.bc_table_1006_2_1_b" if g == "B" else "general.bc_table_1006_2_1_a_e_m"]
        one = {"space_is_exit": False, "space_exit_count": 1, "space_occupant_load": 20, "space_common_path": 60}
        assert _one(rr, "space", one, base | {"occupancy_group": g, "assembly_fixed_seating": True}, ctx) ==             "needs_review", g
        assert _one(rr, "space", one | {"space_occupant_load": 60}, base | {"occupancy_group": g,
                                                                           "assembly_fixed_seating": True}, ctx) ==             "fail", g                                                   # over 49 occupants: fails, measured or not
    i4 = rules["general.bc_1006_2_1_two_exits"]
    assert _one(i4, "space", {"space_is_exit": False, "space_exit_count": 1, "space_occupant_load": 5,
                              "space_common_path": 60}, {"occupancy_group_i4": True, "assembly_fixed_seating": True,
                                                         "special_egress_spaces": False} | NFPA13, ctx) == "needs_review"
    assert _one(r, "space", two, base | {"assembly_fixed_seating": False}, ctx) == "pass"
    store = two | {"space_common_path": 40}                                         # 1018.4: merchandise pads
    m = {"occupancy_group": "M", "special_egress_spaces": False, "assembly_fixed_seating": False} | NFPA13
    assert _one(r, "space", store, m, ctx) == "needs_review"
    assert _one(r, "space", store, m | {"merchandise_pads": False}, ctx) == "pass"


def test_an_nfpa_13d_group_r3_or_r4_is_held_to_1006_2_2_6(ctx, rules):
    """Review round 1, P0: Table 1017.2 note e's NFPA 13D building (903.3.1.3) gets the column without a sprinkler
    system, but 1006.2.2.6 (p.316) caps Group R-3 at 125 ft and R-4 at 75 ft; the sprinkler system not stated, over
    either needs review."""
    r = rules["general.bc_table_1017_2_a_e_f1_m_r_s1"]
    d13 = {"sprinklered_903_3_1_1": False, "sprinklered_903_3_1_2": False, "sprinklered_903_3_1_3": True} | STATED
    assert _one(r, "story", _travel(125), {"occupancy_group": "R-3"} | d13, ctx) == "pass"
    assert _one(r, "story", _travel(125.01), {"occupancy_group": "R-3"} | d13, ctx) == "fail"
    assert _one(r, "story", _travel(75), {"occupancy_group": "R-4"} | d13, ctx) == "pass"
    assert _one(r, "story", _travel(75.01), {"occupancy_group": "R-4"} | d13, ctx) == "fail"
    assert _one(r, "story", _travel(150), {"occupancy_group": "R-3"} | STATED, ctx) == "needs_review"
    assert _one(r, "story", _travel(150), {"occupancy_group": "R-2"} | d13, ctx) == "pass"    # R-2: 1006.2.2.6 not


def test_a_space_with_its_own_limit_stated_or_not_ruled_out_never_passes_a_travel_row(ctx, rules):
    """Review round 1: note a's spaces (a mall, a temporary structure's 100 ft, a refrigeration room's 150 ft ...)
    and 1017.3.2.3's atrium can hold a building to less than its row: stated or not ruled out, the row needs review."""
    r = rules["general.bc_table_1017_2_b"]
    b = {"occupancy_group": "B"} | NFPA13 | STATED
    assert _one(r, "story", _travel(60), b, ctx) == "pass"
    assert _one(r, "story", _travel(60), b | {"special_egress_spaces": True}, ctx) == "needs_review"
    assert _one(r, "story", _travel(60), {k: v for k, v in b.items() if k != "special_egress_spaces"}, ctx) == \
        "needs_review"
    assert _one(r, "story", _travel(250), b | {"building_has_atrium": True}, ctx) == "needs_review"
    assert _one(r, "story", _travel(150), b | {"building_has_atrium": True}, ctx) == "pass"
    i2 = rules["general.bc_table_1017_2_i2_i3"]
    g = {"occupancy_group": "I-2"} | NFPA13 | STATED
    assert _one(i2, "story", _travel(150), g, ctx) == "pass"                          # 50 ft in the room
    assert _one(i2, "story", {"egress_travel_distance": 150, "egress_travel_in_sleeping_room": 50.01}, g, ctx) == \
        "needs_review"                                                                 # over 407.4.2's 50 ft


# ---- section group 2 (2026-11-23): a story's exits and exit separation for every group -----------------------------

FIRST, SECOND, FOURTH = ("story_first_above_or_below_grade", "story_second_above_grade_plane",
                         "story_fourth_or_higher_above_grade_plane")
# Table 1006.3.4(2), p.317 lines 39-43: (groups, the story, most occupants, travel without / with NFPA 13 per note b,
# which is printed on the first story's B, F and S only: group 2's review round 1, 2026-11-24)
TABLE_1006_3_4_2 = [
    (A + ["E", "M", "U"], FIRST, 49, 75, 75), (["B", "F-1", "F-2"], FIRST, 49, 75, 100),
    (["H-2", "H-3"], FIRST, 3, 25, 25), (["H-4", "H-5", "I-1", "I-2", "I-3", "R-1"], FIRST, 10, 75, 75),
    (["S-1"], FIRST, 29, 75, 100), (["M"], SECOND, 29, 75, 75), (["B", "F-1", "F-2", "S-1"], SECOND, 29, 75, 75)]
STORY_FACTS = {"emergency_escape_openings_1031": True, "r2_sleeping_units": False} | STATED


def _story_rule(rules, g):
    fam = ("a_b_e_f_m_u" if g in A + ["B", "E", "F-1", "F-2", "M", "U"] else "s" if g.startswith("S") else "h_i_r")
    return rules[f"general.bc_table_1006_3_4_2__{fam}"]


def _story(where, load, travel, exits=1, **more):
    return {"story_exit_count": exits, "story_occupant_load": load, "egress_travel_distance": travel,
            FIRST: where == FIRST, SECOND: where == SECOND, FOURTH: False, "story_rooms_exit_directly_outside": False,
            **more}


def test_table_1006_3_4_2_each_row_at_its_limits_and_just_past(ctx, rules):
    for groups, where, most, without, with_ in TABLE_1006_3_4_2:
        for g in groups:
            r = _story_rule(rules, g)
            given = {"occupancy_group": g} | STORY_FACTS
            ok = "needs_review" if g == "I-3" else "pass"      # 408.6.1's smoke-barrier distances aren't drawn
            assert _one(r, "story", _story(where, most, with_), given | NFPA13, ctx) == ok, (g, where)
            assert _one(r, "story", _story(where, most + 0.5, 10), given | NFPA13, ctx) == "fail", (g, where)
            assert _one(r, "story", _story(where, 1, with_ + 0.01), given | NFPA13, ctx) == "fail", (g, where)
            assert _one(r, "story", _story(where, most, without), given | NONE, ctx) == ok, (g, where)
            assert _one(r, "story", _story(where, most, without + 0.01), given | NONE, ctx) == "fail", (g, where)
    for g in ("A-2", "E", "U", "H-4", "I-1", "R-1"):                         # not in the second-story row
        r = _story_rule(rules, g)
        assert _one(r, "story", _story(SECOND, 1, 10), {"occupancy_group": g} | STORY_FACTS | NFPA13, ctx) == "fail", g
    for g in ("B", "F-1", "F-2", "S-1"):            # note b's 100 ft never reaches the second story (p.317 line 43)
        r = _story_rule(rules, g)
        assert _one(r, "story", _story(SECOND, 29, 90), {"occupancy_group": g} | STORY_FACTS | NFPA13, ctx) == "fail", g
        assert _one(r, "story", _story(FIRST, 29, 90), {"occupancy_group": g} | STORY_FACTS | NFPA13, ctx) == "pass", g
    third = _story(None, 1, 10)
    assert _one(_story_rule(rules, "B"), "story", third, {"occupancy_group": "B"} | NFPA13, ctx) == "fail"  # NP


def test_group_i3_allowed_one_exit_by_its_travel_needs_review_and_a_measured_fail_still_fails(ctx, rules):
    """408.6.1 (Table 1017.2 note a) also limits Group I-3's travel to a door in a smoke barrier, which isn't drawn:
    the single-exit allowance never passes I-3 on the routes' travel (review round 5's walk, 2026-11-24)."""
    h = rules["general.bc_table_1006_3_4_2__h_i_r"]
    i3 = {"occupancy_group": "I-3"} | STORY_FACTS | NFPA13
    assert _one(h, "story", _story(FIRST, 10, 75), i3, ctx) == "needs_review"
    assert _one(h, "story", _story(FIRST, 10, 75.01), i3, ctx) == "fail"
    assert _one(h, "story", _story(FIRST, 10, 300, exits=2), i3, ctx) == "pass"       # Table 1006.3.3's two exits
    assert _one(h, "story", _story(FIRST, 10, 75), {"occupancy_group": "I-1"} | STORY_FACTS | NFPA13, ctx) == "pass"


def test_two_exits_by_table_1006_3_3_and_r3_r4_with_one(ctx, rules):
    r = _story_rule(rules, "B")
    b = {"occupancy_group": "B"} | NFPA13
    assert _one(r, "story", _story(FIRST, 500, 300, exits=2), b, ctx) == "pass"
    assert _one(r, "story", _story(FIRST, 500.5, 300, exits=2), b, ctx) == "fail"           # 501-1,000: three
    assert _one(r, "story", _story(FIRST, 1000, 300, exits=3), b, ctx) == "pass"
    assert _one(r, "story", _story(FIRST, 1000.5, 300, exits=3), b, ctx) == "fail"          # more: four
    h = rules["general.bc_table_1006_3_4_2__h_i_r"]
    assert _one(h, "story", _story(SECOND, 40, 200), {"occupancy_group": "R-3"} | NFPA13 | STATED, ctx) == "pass"
    assert _one(h, "story", _story(FIRST, 2, 10), {"occupancy_group": "H-1"} | NFPA13, ctx) == "fail"  # no H-1 row


def test_table_1006_3_4_1_group_r2_of_dwelling_units(ctx, rules):
    """p.317 lines 21-24: a basement or first to third story, 4 dwelling units, 125 ft, only with note a's system
    and escape openings; the fourth story and higher NP. Sleeping units are Table 1006.3.4(2)'s (note b)."""
    r = rules["general.bc_table_1006_3_4_1__r2_dwelling_units"]
    du = {"occupancy_group": "R-2", "r2_sleeping_units": False, "emergency_escape_openings_1031": True} | STATED
    one = {"story_exit_count": 1, "story_occupant_load": 16, "egress_travel_distance": 125, FOURTH: False,
           "story_dwelling_units": 4, "story_rooms_exit_directly_outside": False}
    assert _one(r, "story", one, du | NFPA13, ctx) == "pass"
    assert _one(r, "story", one, du | {S1: False, S2: True}, ctx) == "pass"                 # NFPA 13R
    assert _one(r, "story", one | {"story_dwelling_units": 5}, du | NFPA13, ctx) == "fail"
    assert _one(r, "story", one | {"egress_travel_distance": 125.01}, du | NFPA13, ctx) == "fail"
    assert _one(r, "story", one | {FOURTH: True}, du | NFPA13, ctx) == "fail"
    assert _one(r, "story", one, du | NONE, ctx) == "fail"                                   # note a: sprinklered
    assert _one(r, "story", one, du | NFPA13 | {"emergency_escape_openings_1031": False}, ctx) == "fail"
    assert _one(r, "story", one, {"occupancy_group": "R-2"} | NFPA13, ctx) == "needs_review"  # units not stated
    two = one | {"story_exit_count": 2, "story_dwelling_units": 9}
    assert _one(r, "story", two, du | NONE, ctx) == "pass"
    sleeping = rules["general.bc_table_1006_3_4_2__h_i_r"]
    su = du | {"r2_sleeping_units": True}
    assert _one(sleeping, "story", _story(FIRST, 10, 75), su | NFPA13, ctx) == "pass"
    assert _one(sleeping, "story", _story(FIRST, 10, 75), su | NONE, ctx) == "fail"          # note a


def test_a_close_pair_fails_in_another_group_where_two_are_required(ctx, rules):
    """1007.1.1 for every group (group 2): a close pair fails where the group's own row can't allow one exit, and
    needs review where it could (read loosely), never failing a story or space one exit would serve."""
    story = rules["general.bc_1007_1_1_remoteness"]
    b = {"occupancy_group": "B", "occupancy_group_i4": False, "other_occupancy_present": True} | NFPA13
    close = {"exit_remoteness_ratio": 0.2, "story_exit_count": 2, "story_dwelling_units": 0}
    assert _one(story, "story", close | _story(FIRST, 120, 90, exits=2), b, ctx) == "fail"
    assert _one(story, "story", close | _story(FIRST, 40, 90, exits=2), b, ctx) == "needs_review"
    space = rules["general.bc_1007_1_1_space_remoteness"]
    room = {"space_exit_count": 2, "space_exit_remoteness_ratio": 0.2, "space_common_path": 40, "space_is_exit": False}
    assert _one(space, "space", room | {"space_occupant_load": 60}, b, ctx) == "fail"
    assert _one(space, "space", room | {"space_occupant_load": 30}, b, ctx) == "needs_review"
    mixed = b | {"occupancy_group": "mixed"}
    assert _one(space, "space", room | {"space_occupant_load": 60}, mixed, ctx) == "needs_review"
    # group 2's review round 1 (2026-11-24): an S-2 story may have one exit at any load (1006.3.4 item 3, a
    # mechanically parked garage), and a one-group R-3 or R-4 space of 20 or fewer at any common path (Table 1006.2.1
    # note e): a close pair needs review there, never a fail; S-1 and R-2 past their rows still fail
    s2, s1 = b | {"occupancy_group": "S-2"}, b | {"occupancy_group": "S-1"}
    assert _one(story, "story", close | _story(FIRST, 120, 90, exits=2), s2, ctx) == "needs_review"
    assert _one(story, "story", close | _story(FIRST, 120, 90, exits=2), s1, ctx) == "fail"
    far = room | {"space_common_path": 150, "space_occupant_load": 15}
    for g in ("R-3", "R-4"):
        assert _one(space, "space", far, b | {"occupancy_group": g}, ctx) == "needs_review", g
    assert _one(space, "space", far, b | {"occupancy_group": "R-2"}, ctx) == "fail"


def test_a_close_pair_on_a_story_follows_each_table_row_exactly_where_one_exit_could_do(ctx, rules):
    """Group 2's review round 2 (2026-11-24): 1007.1.1's loose one-exit test reads each Table 1006.3.4(2) row at its
    own larger column, as the story-exit rules do (the table above): at the row's limit a close pair needs review
    (one exit could do); just past it, where the row fails one exit, the close pair fails, sprinklered."""
    story = rules["general.bc_1007_1_1_remoteness"]
    close = {"exit_remoteness_ratio": 0.2, "story_dwelling_units": 0}
    for groups, where, most, without, with_ in TABLE_1006_3_4_2:
        for g in groups:
            given = {"occupancy_group": g, "occupancy_group_i4": False, "other_occupancy_present": True} | NFPA13
            at = close | _story(where, most, with_, exits=2)
            assert _one(story, "story", at, given, ctx) == "needs_review", (g, where)
            for past in (_story(where, most, with_ + 0.01, exits=2), _story(where, most + 0.5, 10, exits=2)):
                assert _one(story, "story", close | past, given, ctx) == "fail", (g, where, past)
            assert _one(_story_rule(rules, g), "story", _story(where, most, with_ + 0.01), given | STORY_FACTS,
                        ctx) == "fail", (g, where)                      # the row itself fails one exit there


def test_the_readme_counts_the_pieces_and_numbers_the_second_reading_holds():
    """Review round 2 (P3): the folder's README states how many pieces are brought in and how many numbers were
    read twice; both must be the second reading's own counts, so a piece brought in can't leave them stale."""
    pieces = load(NY / "text_verification.yaml")["pieces"]
    numbers = sum(len(e["numbers"]) for e in pieces.values())
    readme = (NY / "README.md").read_text(encoding="utf-8")
    assert f"{len(pieces)} pieces." in readme and f"(all {len(pieces)} pieces, {numbers} numbers, agree)" in readme


def test_needed_by_is_checked_against_the_rules_that_read_each_fact(tmp_path):
    """Review round 2 (P3): rule_format refuses a proposed measure whose needed_by names a rule that doesn't read it,
    or misses one that does."""
    from rule_format.rulebook import needed_by_problems
    book = tmp_path / "general.yaml"
    book.write_text("rules:\n- id: general.a\n  check: x_fact and y > 1\n- id: general.b\n  applies_when: x_fact\n",
                    encoding="utf-8")
    proposed = tmp_path / "proposed.yaml"
    proposed.write_text("x_fact:\n  unit: yes_no\n  needed_by: [general.a, general.c]\n", encoding="utf-8")
    got = needed_by_problems(proposed, [book])
    assert any("general.c" in p and "don't read it" in p for p in got)
    assert any("general.b" in p and "misses" in p for p in got)
    assert needed_by_problems(NY / "5_building_code_rules/drafted/records/proposed_measures.yaml",
                              [RULEBOOK]) == []


def test_the_words_an_architect_reads_carry_no_engineer_key(ctx):
    """Review round 2: a rule's title, notes, review reasons and worked examples' notes are shown to the architect,
    so `python -m rule_format` refuses a snake_case key or a rule id in them where the law asks for plain words
    (state.yaml plain_words: true, this folder's); a file path stays a reference."""
    from rule_format.rulebook import plain_words_problems, rulebook_file_problems
    assert load(NY / "state.yaml")["plain_words"] is True
    assert rulebook_file_problems(RULEBOOK, ctx) == []
    bad = {"rules": [{"id": "general.x", "title": "T", "notes": "Shown while other_occupancy_present (see "
                      "general.bc_1020_5_dead_end; test_data/answer_keys/a_b/hand_check.yaml)."}]}
    [got] = plain_words_problems(bad)
    assert "other_occupancy_present" in got and "general.bc_1020_5_dead_end" in got and "hand_check" not in got


def test_no_text_calls_a_brought_in_section_not_brought_in():
    """Review round 3 (P3): a section sources.yaml brings in (sections or alone, and the parts under a section) is
    never called 'not brought in' in the words an architect reads, nor in sources.yaml's own notes."""
    import re
    brought = load(NY / "1_source_documents/sources.yaml")["documents"][0]["brought_in"]
    secs = [str(x) for x in brought["sections"] if not str(x).startswith("Table")]
    alone = [str(x) for x in brought["alone"]]     # brought in without the parts under them (1010.2 without 1010.2.14)
    pat = re.compile(r"(?:Section )?(\d{3,4}(?:\.\d+)*)(?:'s)?[^.;]{0,40}?(?:\(|, )[^()]{0,40}?not brought in")

    def brought_in(n):
        return n in alone or any(n == s or n.startswith(s + ".") for s in secs)

    # review round 1 of section group 9e: a list before a bracket that names no section of its own ("meet 1022.2,
    # gates 1010.4 and turnstiles 1010.5 (not brought in)") calls every section in it not brought in
    listed = re.compile(r"([^;:()]{0,160})\(([^()]*?)\b(?:not|none|neither) brought in\)")

    # review round 2 of section group 9e (P3): a clause saying its sections "isn't" or "aren't" brought in
    # ("1023 isn't brought in yet", "1006.1 to 1006.3.2, 1011 ... aren't brought in"), a range holding every section
    # from its first to its last; what a bracket says is left to the bracket checks
    said = re.compile(r"\b(?:is|are)(?:n'?'?t| not)(?: yet)? brought in")
    num = r"(?<![\d.])(?<!Table )(\d{3,4}(?:\.\d+)*)(?![\d])"

    def key(n):
        return tuple(int(x) for x in n.split("."))

    def in_range(a, b):
        return any(key(a) <= key(s) <= key(b) + (999,) for s in secs + alone)

    def said_stale(t):
        out = []
        for clause in re.split(r"(?<=[;:])\s|(?<=[a-z)'\"])\.\s", t):
            m = said.search(clause)
            if not m:
                continue
            head = clause[:m.start()]
            if head.count("(") > head.count(")"):          # said inside a bracket: the bracket's own list
                head = head[head.rindex("(") + 1:]
            while re.search(r"\([^()]*\)", head):
                head = re.sub(r"\([^()]*\)", "", head)
            # only the list the verb is said of ("..., while 1015 isn't": 1015, not the sentence's subject)
            head = " ".join(head.split()) + " "
            head = re.search(r"((?:(?:Sections? )?\d{3,4}(?:\.\d+)*(?:''?s own words)?(?:,? (?:and|or|to|with) |, | ))*)$",
                             head).group(1)
            for a, b in re.findall(num + r" to " + num, head):
                if in_range(a, b):
                    out.append(clause)
            head = re.sub(num + r" to " + num, "", head)
            out += [clause for n in re.findall(num, head) if brought_in(n)]
        return out

    assert said_stale("1023 isn't brought in yet.") and said_stale("1006.1 to 1006.3.2 and 1011 aren't brought in.")
    assert not said_stale("1104 and 3006 aren't brought in (1023 is its own).")
    assert not said_stale("Exits meet 1003 to 1015 (1011 and 1014 aren't brought in yet).")
    assert not said_stale("1012.9 was a reference, so nothing showed while 1015 isn't brought in.")

    def stale(t):
        out = [m.group(0) for m in pat.finditer(t) if brought_in(m.group(1))] + said_stale(t)
        for m in listed.finditer(t):
            if re.search(r"\d{3}", m.group(2)):
                continue
            out += [m.group(0) for n in re.findall(r"(?<![\d.])(?<!Table )(\d{3,4}(?:\.\d+)*)(?!\d)", m.group(1))
                    if brought_in(n)]
        return out
    bad = []
    for r in load(RULEBOOK)["rules"]:
        texts = [r.get("title"), r.get("notes")] + [w["reason"] for w in r.get("review_when") or []] + \
                [e.get("note") for e in r.get("examples") or []]
        bad += [(r["id"], x) for t in texts if isinstance(t, str) for x in stale(t)]
    bad += [("sources.yaml", x) for x in stale((NY / "1_source_documents/sources.yaml").read_text(encoding="utf-8"))]
    # review round 1 of section group 9e (P2): the label reasons too, which the label review page shows (1017.2.1's
    # and 1010.1's still called 1021 and 1022.2 not brought in)
    for pid, lab in load(NY / "3_section_labels/gov.ny.building.2025.yaml")["labels"].items():
        bad += [(pid, x) for x in stale(lab.get("reason") or "")]
    assert not bad, bad


def test_the_single_exit_special_spaces_reason_names_exactly_the_spaces_the_fact_lists():
    """Review round 6 (2026-11-24): the reason once named a stage, which neither Table 1017.2 note a nor 1006.2.2 sends
    to its own section. Its spaces are now the special_egress_spaces fact's own list, word for word, and no reason
    on that fact names a space outside it."""
    meaning = load(NY / "5_building_code_rules/drafted/records/proposed_measures.yaml")["special_egress_spaces"]["meaning"]
    spaces = meaning.split("as the architect states it: ", 1)[1].split("; left unstated", 1)[0]
    found = 0
    for r in load(RULEBOOK)["rules"]:
        for w in r.get("review_when") or []:
            if "special_egress_spaces" not in w["when"]:
                continue
            assert "stage" not in w["reason"].lower(), r["id"]
            if "1006.3.4's single-exit travel limit" in w["reason"]:
                assert f"own exits or exit access travel limit: {spaces}." in w["reason"], r["id"]
                found += 1
    assert found >= 1



def test_every_rule_on_a_spaces_own_exits_lets_an_exit_be():
    """PR #181 review (2026-11-24), the class: a rule reading a space's exits, occupant load or common path is about
    a space exit access serves (1006.2.1, 1007.1), so its check lets a space that is itself an exit be
    (space_is_exit), and each of its reviews leaves one out, or an exit stair fails or needs review on rules not
    its own (Group I-4's two-exit rule failed each stair of the four-unit apartment)."""
    import yaml
    path = (REPO / "regulations/jurisdictions/new_york/new_york_state_building/5_building_code_rules/drafted/"
            "general.yaml")
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = rules["rules"] if isinstance(rules, dict) else rules
    space = ("space_exit_count", "space_occupant_load", "space_common_path")
    checked = []
    for r in rules:
        check = str(r.get("check", ""))
        if not any(m in check for m in space):
            continue
        checked.append(r["id"])
        assert check.startswith("space_is_exit or "), r["id"]
        for w in r.get("review_when") or []:
            assert str(w["when"]).startswith("not space_is_exit and "), (r["id"], w["when"])
    assert "general.bc_1006_2_1_two_exits" in checked and len(checked) >= 16


def test_every_occupant_load_factor_is_quoted_word_for_word_from_its_row():
    """Section group 3's frozen factors (records/occupant_load_factors.yaml) sit outside the rulebook's own checks
    (rulebook_paths leaves records/ out), so their quotes are checked here as a rule's are: each at its page and lines,
    word for word, where the code cache is; elsewhere each one not checked is listed, never passed (review of group 3,
    round 1, 2026-11-24)."""
    from rule_format.rulebook import _source_problems
    data = load(NY / "5_building_code_rules/drafted/records/occupant_load_factors.yaml")
    sources = [e["source"] for e in data["functions"].values()] + [data["increase_cap"]["source"]]
    assert len(sources) == len(data["functions"]) + 1 and all(isinstance(x, dict) for x in sources)
    ctx = Context.for_jurisdiction(NY)
    assert _source_problems(sources, ctx) == []
    if ctx.skipped:                                    # no code cache on this machine: every quote said, none passed
        assert len(ctx.skipped) == len(sources), ctx.skipped
        pytest.skip(f"{len(sources)} quotes not checked here: {ctx.skipped[0]}")


# ---- section group 4 (2026-11-25): Table 1020.3, corridor width (p.344, lines 27-33) --------------------------------

# Table 1020.3, p.344: line -> the row's width in inches, typed from the page
TABLE_1020_3 = {27: 44, 28: 24, 29: 36, 30: 36, 31: 72, 32: 72, 33: 96}
ONE_GROUP = A + ["B", "E", "F-1", "F-2", "H-1", "H-2", "H-3", "H-4", "H-5", "I-1", "I-2", "I-3", "I-4", "M"] + R + \
    ["S-1", "S-2", "U"]


def _corridor(width, load_):
    return {"corridor_width": width, "corridor_occupant_load": load_}


def test_table_1020_3_every_row_passes_at_its_width_and_not_just_short_of_it(ctx, rules):
    """Each row of Table 1020.3 (p.344) for every group: at its width it passes (where the row is the one that
    applies), just short of it it fails, or needs review where a looser row the model can't see may apply (24 in to
    mechanical, plumbing or electrical equipment; 36 in within a dwelling unit; Group I-2's exception, 1020.3, p.344
    lines 23-24; stretcher traffic in an ambulatory care facility, stated)."""
    r = rules["general.bc_table_1020_3_corridor_width"]
    assert all(_cites(r, 344, line) for line in TABLE_1020_3)
    no_amb = {"ambulatory_care_facility": False}
    for g in ONE_GROUP:
        given = {"occupancy_group": g} | no_amb
        if g == "I-2":
            assert _one(r, "corridor", _corridor(TABLE_1020_3[33], 200), given, ctx) == "pass"
            assert _one(r, "corridor", _corridor(TABLE_1020_3[33] - 0.5, 200), given, ctx) == "needs_review"
            assert _one(r, "corridor", _corridor(TABLE_1020_3[28] - 0.5, 10), given, ctx) == "fail"
            continue
        # line 27: any facility not listed, 44 in (50 occupants or more, under 100 for Group E)
        assert _one(r, "corridor", _corridor(TABLE_1020_3[27], 50), given, ctx) == "pass", g
        assert _one(r, "corridor", _corridor(TABLE_1020_3[27] - 0.5, 50), given, ctx) == "needs_review", g  # line 30
        assert _one(r, "corridor", _corridor(TABLE_1020_3[30] - 0.5, 50), given, ctx) == "needs_review", g  # line 28
        # line 29: fewer than 50 occupants, 36 in
        assert _one(r, "corridor", _corridor(TABLE_1020_3[29], 49.5), given, ctx) == "pass", g
        assert _one(r, "corridor", _corridor(TABLE_1020_3[29] - 0.5, 49.5), given, ctx) == "needs_review", g
        # line 28: 24 in at the least, for any corridor
        assert _one(r, "corridor", _corridor(TABLE_1020_3[28], 10), given, ctx) == "needs_review", g
        assert _one(r, "corridor", _corridor(TABLE_1020_3[28] - 0.5, 10), given, ctx) == "fail", g
        # line 31: Group E with 100 or more, 72 in
        want = ("pass", "fail") if g == "E" else ("pass", "pass")
        assert (_one(r, "corridor", _corridor(TABLE_1020_3[31], 100), given, ctx),
                _one(r, "corridor", _corridor(TABLE_1020_3[31] - 0.5, 100), given, ctx)) == want, g
    # line 32: stretcher traffic in an ambulatory care facility (Group B, 304.1), stated or not ruled out
    for amb in ({"ambulatory_care_facility": True}, {}):
        b = {"occupancy_group": "B"} | amb
        assert _one(r, "corridor", _corridor(TABLE_1020_3[32], 60), b, ctx) == "pass"
        assert _one(r, "corridor", _corridor(TABLE_1020_3[32] - 0.5, 60), b, ctx) == "needs_review"
    # a building of two or more groups, or one whose group isn't stated, never passes
    assert _one(r, "corridor", _corridor(120, 10), {"occupancy_group": "mixed"}, ctx) == "not_applicable"
    assert _one(r, "corridor", _corridor(120, 10), {}, ctx) == "needs_review"
    assert rules["general.bc_table_1020_3_other_occupancies"]["applies_when"] == 'occupancy_group == "mixed"'


def test_a_corridors_capacity_is_1005_3_2s_factor_at_its_limit_and_just_past_it(ctx, rules):
    """Section group 5a: 1020.3 asks the capacity of 1005.1, for a corridor 1005.3.2's (p.314): 0.2 in per occupant
    (lines 14-16), 0.15 with a 903.3.1.1 or 903.3.1.2 system and a voice/alarm system other than in Groups H and I-2
    (exception 1, lines 18-22); fixed seating not ruled out (exceptions 2 and 3: smoke-protected or open-air seating's
    own factors) needs review short of it. Was 4a's flag."""
    r = rules["general.bc_1020_3_corridor_capacity"]
    assert r["kind"] == "rule" and _cites(r, 314, 15) and _cites(r, 314, 20) and _cites(r, 344, 21)
    plain = {S1: False, S2: False, "emergency_voice_alarm_system": False, "assembly_fixed_seating": False}
    for g in ("B", "I-2", "H-3", "mixed"):
        given = {"occupancy_group": g} | plain
        assert _one(r, "corridor", _corridor(44, 220), given, ctx) == "pass", g      # 0.2 x 220 = 44
        assert _one(r, "corridor", _corridor(44, 220.5), given, ctx) == "fail", g
    voice = {S1: True, S2: False, "emergency_voice_alarm_system": True, "assembly_fixed_seating": False}
    # review round 1 of group 5a: a building of two or more groups is each portion's (1004.4): between the two
    # factors, a person's check, never a fail on 0.2 alone
    for g, want in (("B", "pass"), ("R-2", "pass"), ("I-2", "fail"), ("H-3", "fail"), ("mixed", "needs_review")):
        assert _one(r, "corridor", _corridor(45, 300), {"occupancy_group": g} | voice, ctx) == want, g   # 0.15 x 300
        assert _one(r, "corridor", _corridor(44.9, 300), {"occupancy_group": g} | voice, ctx) == "fail", g
    assert _one(r, "corridor", _corridor(45, 300), {"occupancy_group": "mixed"} | voice | {
        "emergency_voice_alarm_system": False}, ctx) == "fail"
    # review round 1 (P1): 903.3.1.2 (13R) counts in Group R; elsewhere it is a person's check, never a pass on 0.15
    r13r = voice | {S1: False, S2: True}
    assert _one(r, "corridor", _corridor(45, 300), {"occupancy_group": "R-2"} | r13r, ctx) == "pass"
    assert _one(r, "corridor", _corridor(45, 300), {"occupancy_group": "B"} | r13r, ctx) == "needs_review"
    assert _one(r, "corridor", _corridor(44.9, 300), {"occupancy_group": "B"} | r13r, ctx) == "fail"
    no_voice = voice | {"emergency_voice_alarm_system": False}
    assert _one(r, "corridor", _corridor(45, 300), {"occupancy_group": "B"} | no_voice, ctx) == "fail"
    seats = voice | {"assembly_fixed_seating": True}
    assert _one(r, "corridor", _corridor(44.9, 300), {"occupancy_group": "A-3"} | seats, ctx) == "needs_review"
    # the group not stated: never a pass (the walk, test_ny_building_corridor_walk.py, covers it at every factor)
    assert _one(r, "corridor", _corridor(80, 400), voice, ctx) == "needs_review"


# ---- section group 4b (2026-11-25): Table 1020.2, corridor fire-resistance rating (p.344, lines 7-18) ----------------

# Table 1020.2, p.344: line -> (groups, the occupant load above which a rating applies (None: All), hours without a
# sprinkler system (None: Not Permitted), with one (note c: 903.3.1.1 or 903.3.1.2), the rule), typed from the page
TABLE_1020_2 = {
    7: (["H-1", "H-2", "H-3"], None, None, 1, "h1_h2_h3"),
    8: (["H-4", "H-5"], 30, None, 1, "h4_h5"),
    9: (A + ["B", "E", "F-1", "F-2", "M", "S-1", "S-2", "U"], 30, 1, 0, "a_b_e_f_m_s_u"),
    10: (R, 10, None, 0.5, "r"),
    11: (["I-2"], None, None, 0, "i2"),
    12: (["I-1", "I-3"], None, None, 1, "i1_i3"),
    13: (["I-4"], None, 1, 0, "i4"),
}
NO_UNITS = {"corridors_within_dwelling_units": False}
EXCEPTED = {"B", "E", "S-2"}          # 1020.2 exceptions 4, 1 and 3 (p.343): reviewed where the rating falls short


def _rating(load_, hours=None):
    m = {"corridor_occupant_load": load_}
    if hours is not None:
        m["corridor_fire_rating_hours"] = hours
    return m


def test_table_1020_2_every_row_passes_at_its_rating_and_not_just_short_of_it(ctx, rules):
    """Each row of Table 1020.2 (p.344) for every group: with a sprinkler system (NFPA 13) and without, at the row's
    occupant load and just past it, at its rating and just under it; Not Permitted fails whatever the rating."""
    for line, (groups, over, without, with_, rid) in TABLE_1020_2.items():
        r = rules[f"general.bc_table_1020_2_{rid}"]
        assert _cites(r, 344, line), rid
        many = (over or 0) + 0.5                                   # just past the row's load (any load for "All")
        for g in groups:
            for system, need in ((NFPA13, with_), (NONE, without)):
                given = {"occupancy_group": g} | system | NO_UNITS
                if need is None:                                  # Not Permitted
                    assert _one(r, "corridor", _rating(many, 5), given, ctx) == "fail", (g, line)
                    continue
                if need:
                    assert _one(r, "corridor", _rating(many, need), given, ctx) == "pass", (g, line)
                    # 1020.2's exceptions (p.343) and note b (Group I-3's reduction, 408.8) need review short of it
                    short = "needs_review" if (g in EXCEPTED and system is NONE) or (g == "I-3" and system is NFPA13)                         else "fail"
                    assert _one(r, "corridor", _rating(many, need - 0.25), given, ctx) == short, (g, line)
                else:
                    assert _one(r, "corridor", _rating(many), given, ctx) == "pass", (g, line)    # 0: none asked
            if over is not None:                                  # at the row's load: no rating asked
                assert _one(r, "corridor", _rating(over), {"occupancy_group": g} | NONE | NO_UNITS, ctx) == "pass", g
    # note d (p.344 lines 17-18): Group R-3 and R-4 with 903.3.1.3 (NFPA 13D), 1 hour; R-1 and R-2 have no such cell
    r = rules["general.bc_table_1020_2_r"]
    d13 = {S1: False, S2: False, "sprinklered_903_3_1_3": True} | NO_UNITS
    assert _cites(r, 344, 17)
    assert _one(r, "corridor", _rating(11, 1), {"occupancy_group": "R-3"} | d13, ctx) == "pass"
    assert _one(r, "corridor", _rating(11, 0.75), {"occupancy_group": "R-3"} | d13, ctx) == "fail"
    # review round 1 of group 4b: note d's 903.2.8 permits 13D in Group R-4 only in Condition 1 (903.2.8.2, p.271),
    # which isn't stated: never a pass on it; under 1 hour it fails either way (round 2)
    for h in (1, 2):
        assert _one(r, "corridor", _rating(11, h), {"occupancy_group": "R-4"} | d13, ctx) == "needs_review", h
    assert _one(r, "corridor", _rating(11, 0.75), {"occupancy_group": "R-4"} | d13, ctx) == "fail"
    assert _one(r, "corridor", _rating(11, 1), {"occupancy_group": "R-2"} | d13, ctx) == "fail"
    # note c's 903.3.1.2 (NFPA 13R): Group R's 0.5 hour; elsewhere "where allowed", a person's check
    s13r = {S1: False, S2: True, "sprinklered_903_3_1_3": False} | NO_UNITS
    assert _one(r, "corridor", _rating(11, 0.5), {"occupancy_group": "R-2"} | s13r, ctx) == "pass"
    for rid, g in (("h1_h2_h3", "H-1"), ("i1_i3", "I-1"), ("i2", "I-2"), ("i4", "I-4"), ("a_b_e_f_m_s_u", "M")):
        assert _one(rules[f"general.bc_table_1020_2_{rid}"], "corridor", _rating(31, 0.5),
                    {"occupancy_group": g} | s13r, ctx) == "needs_review", rid
    # exception 2 (p.343 lines 47-48): a corridor within a dwelling or sleeping unit, stated or not ruled out
    for units in ({"corridors_within_dwelling_units": True}, {}):
        assert _one(r, "corridor", _rating(11, 0), {"occupancy_group": "R-2"} | NONE | units, ctx) == "needs_review"
    # note b (p.344 line 15): Group I-3's reduction (408.8) under 1 hour with a sprinkler system
    assert _one(rules["general.bc_table_1020_2_i1_i3"], "corridor", _rating(5, 0.5),
                {"occupancy_group": "I-3"} | NFPA13, ctx) == "needs_review"
    # a building of two or more groups, or one whose group isn't stated, never passes
    assert rules["general.bc_table_1020_2_other_occupancies"]["applies_when"] == 'occupancy_group == "mixed"'
    for rid in ("a_b_e_f_m_s_u", "r", "i4"):
        rr = rules[f"general.bc_table_1020_2_{rid}"]
        assert _one(rr, "corridor", _rating(5, 2), {"occupancy_group": "mixed"} | NFPA13, ctx) == "not_applicable"
        assert _one(rr, "corridor", _rating(5, 2), NFPA13, ctx) == "needs_review"


def test_table_1020_3_within_a_dwelling_unit_needs_review_only_while_not_ruled_out(ctx, rules):
    """Group 4b: Table 1020.3's 36 in within a dwelling unit (p.344 line 30) needs review only while the building
    states it has such corridors or doesn't say; stated no, a 43.5 in corridor serving 50 fails."""
    r = rules["general.bc_table_1020_3_corridor_width"]
    base = {"occupancy_group": "R-2", "ambulatory_care_facility": False}
    for units, want in (({"corridors_within_dwelling_units": True}, "needs_review"), ({}, "needs_review"),
                        (NO_UNITS, "fail")):
        assert _one(r, "corridor", _corridor(43.5, 50), base | units, ctx) == want, units


def test_more_than_one_reads_the_same_comparison_in_every_piece():
    """Review round 1 of group 5b (P3): 1005.5's 'Where more than one exit ... is required' was read 'none' while
    1020.5's same words read '>': the second reading says what the printed sentence says of each number, so 'more
    than <n>' is '>' everywhere in this book (a condition, but a comparison all the same). Section group 9a: where the
    sentence denies the verb before it ('shall not overhang that post or pylon more than 4 inches', 1003.3.2), the
    number is a maximum, '<=': the one such sentence is named here, its words checked. A number recorded with its
    'not' ('not more than 6 inch', 'not project horizontally more than 4 inch') is '<=', but 1012.6.3's 'not be
    required to be more than 48 inch', the least a landing needs, '>=' with its verification flag (review round 4)."""
    pieces = load(NY / "text_verification.yaml")["pieces"]
    denied = {("1003.3.2", "more than 4 inch"): "shall not overhang that post or pylon more than 4 inches"}
    seen = []
    for pid, e in pieces.items():
        for n, comp in zip(e["second_reading_numbers"], e["second_reading_comparisons"]):
            if str(n).startswith("more than ") and (pid, n) not in denied:
                seen.append((pid, n, comp))
    assert seen and all(comp == ">" for _, _, comp in seen), [x for x in seen if x[2] != ">"]
    capped = {("1012.6.3", "not be required to be more than 48 inch"): ">="}
    for pid, e in pieces.items():
        for n, comp in zip(e["second_reading_numbers"], e["second_reading_comparisons"]):
            if re.search(r"\bnot\b.*\bmore than\b", str(n)):
                assert comp == capped.get((pid, n), "<="), (pid, n, comp)
                if (pid, n) in capped:
                    assert any(f"'{n}' ({comp})" in f for f in e.get("flags") or []), (pid, n)
    for (pid, n), words in denied.items():
        e = pieces[pid]
        assert e["second_reading_comparisons"][e["second_reading_numbers"].index(n)] == "<=", (pid, n)
        assert any(words in " ".join(s["quote"].split()) for s in load(NY / "3_section_labels/gov.ny.building.2025.yaml")[
            "labels"][pid]["sources"]), (pid, words)


def test_the_readmes_not_brought_in_list_names_no_section_brought_in():
    """Review round 1 of group 5c (P3): the README listed 1005.7 as not brought in after this group brought it in.
    Every section number in its 'References in the brought-in sections that are not brought in' list is neither a
    brought-in section nor one under it."""
    readme = (NY / "README.md").read_text(encoding="utf-8")
    listed = readme.split("## References in the brought-in sections that are not brought in", 1)[1].split("\n## ", 1)[0]
    brought = load(NY / "1_source_documents/sources.yaml")["documents"][0]["brought_in"]
    ids = [str(x) for x in brought["sections"] + brought["alone"] if not str(x).startswith("Table")]
    tables = {str(x) for x in brought["sections"] if str(x).startswith("Table")}
    # round 2: tables by name first ("Table 1006.3.4(1)", "Tables 705.5 and 705.9"), before brackets are dropped
    named = []
    # ("Table 1017.2's note a lists": a brought-in table named as the source of a reference, not as one)
    # round 3: "Tables X and Y" names two tables; "Table X and Y" a table and a section (Y stays for the section check)
    num = r"\d{3,4}(?:\.\d+)*(?:\(\d\))?"
    plural = rf"Tables ({num}) and ({num})(?!'s)"
    single = rf"Table ({num})(?![\d.(]|'s)"
    for m in re.finditer(plural, listed):
        named += [f"Table {g}" for g in m.groups()]
    for m in re.finditer(single, listed):
        named.append(f"Table {m.group(1)}")
    bad = [t for t in named if t in tables]
    listed = re.sub(plural, "", listed)
    listed = re.sub(single, "", listed)
    listed = re.sub(rf"Table {num}'s", "", listed)       # a table named as a reference's source
    listed = re.sub(r"\([^()]*\)", "", listed)             # what a reference is for, in brackets, may name a section
    # the parts under a section brought in alone ("903.3.1.2's parts"); a section brought in whole has its parts in
    listed = re.sub(r"(\d{3,4}(?:\.\d+)*)'s parts", lambda m: "" if m.group(1) in brought["alone"] else m.group(1),
                    listed)
    bad += [n for n in re.findall(r"\b\d{3,4}(?:\.\d+)*\b", listed)
            if any(n == b or (n.startswith(b + ".") and b not in brought["alone"]) for b in ids)]
    assert named and not bad, bad


# ---- section group 6a (2026-11-25): door size, 1010.1.1 (pp.322-323) ------------------------------------------------

ON_CORRIDOR = {"moe_door_exit": False, "moe_door_exterior": False, "moe_door_to_corridor": True,
               "moe_door_to_room_under_10_sf": False}           # no exception can loosen it (with no units' corridors)
BETWEEN_ROOMS = ON_CORRIDOR | {"moe_door_to_corridor": False}
OUTSIDE = BETWEEN_ROOMS | {"moe_door_exterior": True}
NO_UNITS = {"corridors_within_dwelling_units": False}


def _door(width=None, height=None, leaves=1, **sides):
    m = (ON_CORRIDOR | sides) | ({"moe_door_leaves": leaves} if leaves is not None else {})
    m |= {k: v for k, v in (("moe_door_clear_width", width), ("moe_door_clear_height", height)) if v is not None}
    return m


def test_1010_1_1_width_at_its_limits_and_just_past(ctx, rules):
    """1010.1.1's widths, typed from the page: 32 in (p.322 line 38), 41 1/2 in for Group I-2 bed movement (line 42),
    exception 2's 28 in (line 48), exception 7's 31.75 in (line 58), exception 8's 20 in (p.323 line 4); exceptions
    1 and 6 (lines 45, 55) and 3 (line 49) set no width."""
    r = rules["general.bc_1010_1_1_door_width"]
    for line in (38, 42, 45, 48, 49, 55, 58):
        assert _cites(r, 322, line), line
    assert _cites(r, 323, 4)
    b = {"occupancy_group": "B"} | NO_UNITS
    one = lambda m, g=b: _one(r, "means_of_egress_door", m, g, ctx)
    assert one(_door(32)) == "pass" and one(_door(31.99, moe_door_exit=True)) == "fail"   # into an exit: nothing loosens it
    assert one(_door(31.99)) == "needs_review"          # on a corridor: it may serve a compartment (8: 20 in, round 1)
    i2 = {"occupancy_group": "I-2"} | NO_UNITS
    assert one(_door(41.5), i2) == "pass" and one(_door(41.49), i2) == "needs_review" and one(_door(31.99, moe_door_exit=True), i2) == "fail"
    i3 = {"occupancy_group": "I-3"} | NO_UNITS
    assert one(_door(28), i3) == "needs_review" and one(_door(27.99, moe_door_exit=True), i3) == "fail" and one(_door(32), i3) == "pass"
    # exception 7 (31.75, within a Type B unit: only a door between two rooms) and 8 (20, a compartment: any door but
    # one into an exit enclosure, passageway or horizontal exit, review rounds 1 and 2)
    assert one(_door(31.75, **BETWEEN_ROOMS)) == "needs_review" and one(_door(19.99, **BETWEEN_ROOMS)) == "fail"
    assert one(_door(20, **BETWEEN_ROOMS)) == "needs_review" and one(_door(31.75, moe_door_exit=True)) == "fail"
    assert one(_door(24, **OUTSIDE)) == "needs_review"   # a compartment may open outside (review round 1)
    assert one(_door(24, **(OUTSIDE | {"moe_door_exit": True}))) == "needs_review"   # by a door marked an exit (round 2)
    # exception 3: a storage closet under 10 sq ft, no width
    assert one(_door(10, moe_door_to_room_under_10_sf=True)) == "needs_review"
    # exceptions 1 and 6 (Groups R-2, R-3; I-1, R-2, R-3, R-4): no width for a door that may be in a unit
    for g in ("R-2", "R-3", "I-1", "R-4"):
        gg = {"occupancy_group": g} | NO_UNITS
        assert one(_door(10, **BETWEEN_ROOMS), gg) == "needs_review", g
        assert one(_door(10), gg) == "fail", g                                   # on a corridor in no unit
        assert one(_door(10), {"occupancy_group": g}) == "needs_review", g        # the corridors not stated
        assert one(_door(10, moe_door_exit=True), {"occupancy_group": g}) == "fail", g   # into an exit enclosure
    assert one(_door(10, **BETWEEN_ROOMS), {"occupancy_group": "R-1"} | NO_UNITS) == "fail"   # R-1: neither exception


def test_1010_1_1_height_at_its_limits_and_just_past(ctx, rules):
    """80 in (p.322 line 43), exception 4's 78 in within a unit (line 51), exception 5's 76 in for a unit's exterior
    door (line 54)."""
    r = rules["general.bc_1010_1_1_door_height"]
    for line in (43, 51, 54):
        assert _cites(r, 322, line), line
    one = lambda m: _one(r, "means_of_egress_door", m, NO_UNITS, ctx)
    assert one(_door(height=80)) == "pass" and one(_door(height=79.99)) == "fail"
    assert one(_door(height=78, **BETWEEN_ROOMS)) == "needs_review" and one(_door(height=77.99, **BETWEEN_ROOMS)) == "fail"
    assert one(_door(height=76, **OUTSIDE)) == "needs_review" and one(_door(height=75.99, **OUTSIDE)) == "fail"
    assert one(_door(height=78, moe_door_exit=True, **{k: v for k, v in BETWEEN_ROOMS.items() if k != "moe_door_exit"}))         == "fail"                                                     # an exit door is no door within a unit


def test_1010_1_1_takes_no_size_from_anything_but_the_stated_clear_opening(ctx, rules):
    """The hard condition (section group 6a): the sizes are the maker's stated clear opening, or none: a door with
    no width or height measured needs review on both rules, never a pass (and never a fail: nothing measured)."""
    for rid in ("general.bc_1010_1_1_door_width", "general.bc_1010_1_1_door_height"):
        for g in ("B", "R-2", "I-2"):
            assert _one(rules[rid], "means_of_egress_door", _door(), {"occupancy_group": g} | NO_UNITS, ctx) ==                 "needs_review", (rid, g)


# ---- section group 6b (2026-11-25): door kind and swing, 1010.1.2 and 1010.1.2.1 (p.323) -----------------------------

H = ["H-1", "H-2", "H-3", "H-4", "H-5"]


def test_1010_1_2_1_swing_at_its_limit_and_just_past(ctx, rules):
    """1010.1.2.1 (p.323 lines 24-25): a swinging door swings with egress travel where it serves 50 or more, or a
    Group H occupancy, typed from the page; a door that isn't swinging is asked nothing."""
    r = rules["general.bc_1010_1_2_1_direction_of_swing"]
    assert _cites(r, 323, 24) and _cites(r, 323, 25)
    one = lambda m, g: _one(r, "means_of_egress_door", m, {"occupancy_group": g}, ctx)
    against = {"moe_door_swinging": True, "moe_door_swings_with_egress": False, "moe_door_exterior": False, "moe_door_exit": False}
    for g in ("B", "A-2", "R-2"):
        assert one(against | {"moe_door_occupant_load": 49.99}, g) == "pass", g
        assert one(against | {"moe_door_occupant_load": 50}, g) == "fail", g
    for g in H:
        assert one(against | {"moe_door_occupant_load": 1}, g) == "fail", g
    # two or more groups: under 50, whether a Group H occupancy is among them isn't shown (found by the walk)
    assert one(against | {"moe_door_occupant_load": 1}, "mixed") == "needs_review"
    assert one(against | {"moe_door_occupant_load": 50}, "mixed") == "fail"
    assert one({"moe_door_swinging": True, "moe_door_occupant_load": 1}, "H-3") == "needs_review"  # swing not stated
    assert one({"moe_door_swinging": False, "moe_door_occupant_load": 500}, "H-1") == "pass"       # not swinging
    inside = {"moe_door_exterior": False, "moe_door_exit": False}
    assert one({"moe_door_swinging": True, "moe_door_swings_with_egress": True, "moe_door_occupant_load": 900} | inside,
               "B") == "pass"
    # review round 2: a door to outside that isn't an exit, outdoor areas not ruled out: either way, never decided
    patio = {"moe_door_swinging": True, "moe_door_exterior": True, "moe_door_exit": False, "moe_door_occupant_load": 900}
    for swings in (True, False):
        assert one(patio | {"moe_door_swings_with_egress": swings}, "B") == "needs_review", swings
        assert _one(r, "means_of_egress_door", patio | {"moe_door_swings_with_egress": swings},
                    {"occupancy_group": "B", "occupied_outdoor_areas": False}, ctx) == ("pass" if swings else "fail")


def test_1010_1_2_door_kind_is_never_a_fail(ctx, rules):
    """1010.1.2 (p.323 lines 11-23): exception 7's power-operated doors are allowed in every group, and the model
    doesn't say whether a door is power-operated, so a door of another kind is a person's check, never a fail."""
    r = rules["general.bc_1010_1_2_door_types"]
    assert _cites(r, 323, 11) and _cites(r, 323, 20)
    for g in ("B", "H-1", "R-2", "I-3"):
        assert _one(r, "means_of_egress_door", {"moe_door_swinging": False}, {"occupancy_group": g}, ctx) ==             "needs_review", g
        assert _one(r, "means_of_egress_door", {"moe_door_swinging": True}, {"occupancy_group": g}, ctx) ==             "not_applicable", g


# ---- section group 6c (2026-11-25): the rest of 1010.1, 1010.1.3 to 1010.1.7 (pp.323-324) -----------------------------

FLAGS_6C = {"general.bc_1010_1_3_door_forces": (323, 26), "general.bc_1010_1_4_floor_elevation": (324, 5),
            "general.bc_1010_1_5_landings": (324, 9), "general.bc_1010_1_6_thresholds": (324, 25),
            "general.bc_1010_1_7_door_arrangement": (324, 32)}


@pytest.mark.parametrize("rid", sorted(FLAGS_6C))
def test_1010_1_3_to_1010_1_7_are_always_a_persons_check(ctx, rules, rid):
    """Forces, floor levels, landings, thresholds and doors in a series aren't in the model: each is a flag shown for
    every building, whatever its group or doors, never a pass or a fail (typed from the page: the line each cites)."""
    r = rules[rid]
    assert r["kind"] == "flag" and "applies_when" not in r and "for_each" not in r
    assert _cites(r, *FLAGS_6C[rid])
    from rule_format.rulebook import outcome
    for g in ("B", "H-1", "R-2", "A-1", "mixed", None):
        given = {} if g is None else {"occupancy_group": g}
        assert outcome(r, given, ctx.allowed()) == "needs_review", (rid, g)


def test_1010_1_3_2_a_door_not_stated_side_hinged_is_a_persons_check(ctx, rules):
    """1010.1.3.2 (p.323 lines 38-39): a manual horizontal sliding door required to latch; any door that isn't stated
    side-hinged may be one (sliding, folding, pocket, other, or not stated): a person's check, never a pass; a
    side-hinged door is set aside."""
    r = rules["general.bc_1010_1_3_2_sliding_door_latch"]
    assert _cites(r, 323, 38) and _cites(r, 323, 39)
    for g in ("B", "H-1", "R-2"):
        assert _one(r, "means_of_egress_door", {"moe_door_swinging": False}, {"occupancy_group": g}, ctx) ==             "needs_review", g
        assert _one(r, "means_of_egress_door", {}, {"occupancy_group": g}, ctx) == "needs_review", g
        assert _one(r, "means_of_egress_door", {"moe_door_swinging": True}, {"occupancy_group": g}, ctx) ==             "not_applicable", g


def test_the_6c_flags_state_each_exceptions_own_conditions(rules):
    """Review round 1 of group 6c: a flag's note is what a person checks by, so an exception's conditions are stated
    whole, never looser or stricter than the page (p.323 lines 46-56, p.324 lines 22-25 and 30-32)."""
    note = lambda rid: " ".join(rules[rid]["examples"][0]["note"].split())
    floor = note("general.bc_1010_1_4_floor_elevation")
    assert "with an impervious surface up to 4 inches lower" in floor                       # exception 5
    assert "other than an exterior storm or screen door, not swinging over it" in floor       # exception 2
    assert "storm and screen doors included, may swing over either landing" in floor          # exception 3
    # review round 4: exception 3 is for dwelling AND sleeping units (p.323 line 49), as round 3 wrote it
    assert "Group R-2 and R-3 dwelling or sleeping units not required to be Accessible, Type A or Type B" in floor
    sill = note("general.bc_1010_1_6_thresholds")
    assert "4 3/4 inches for a sliding door and 4 1/2 inches for others" in sill               # exception 2
    series = note("general.bc_1010_1_7_door_arrangement")
    assert "need not be 48 inches from the other door (they still swing as above)" in series  # exception 2
    assert "other than within Type A units" in series                                          # exception 3
    # review round 2: 1010.1.3's 5 pounds is for any interior manual swinging door not REQUIRED to be fire rated
    # (p.323 lines 32-34), and 1010.1.7 is any two doors in a series, not only a vestibule's (p.324 line 26)
    forces = note("general.bc_1010_1_3_door_forces")
    assert "and one required to be fire rated, is set in motion by at most 30 pounds" in forces
    assert "a fire-rated one" not in forces
    assert "(in a vestibule or anywhere else on the way out)" in series


def test_the_6c_labels_name_their_exceptions():
    """Review round 3 of group 6c: a label read alone never states a requirement stricter than the page; 1010.1.7's
    names its three exceptions (p.324 lines 28-32), as 1010.1.4's, 1010.1.5's and 1010.1.6's do theirs."""
    labels = load(NY / "3_section_labels/gov.ny.building.2025.yaml")["labels"]
    reason = lambda pid: " ".join(labels[pid]["reason"].split())
    assert "with exceptions for horizontal sliding power-operated doors, Group R-2 and R-3 storm and screen doors, and " \
           "doors within those units other than Type A units" in reason("1010.1.7")
    assert "with six exceptions" in reason("1010.1.4")
    assert "36 in Groups R-3 and U and within Group R-2 units" in reason("1010.1.5")
    assert "with exceptions for Group R-2 and R-3 exterior doors and Type B units" in reason("1010.1.6")
# ---- section group 6d (2026-11-25): door operations, 1010.2 to 1010.2.7 and Table 1010.2.4 (pp.324-326) ----------------

FLAGS_6D = {"general.bc_1010_2_door_operations": (324, 33), "general.bc_1010_2_1_unlatching": (324, 35),
            "general.bc_1010_2_2_hardware": (324, 41), "general.bc_1010_2_3_hardware_height": (324, 43),
            "general.bc_1010_2_4_locks_and_latches": (325, 35), "general.bc_table_1010_2_4_inactive_leaf_bolts": (325, 61),
            "general.bc_1010_2_5_closet_doors": (326, 3), "general.bc_1010_2_6_stairway_doors": (326, 22)}


@pytest.mark.parametrize("rid", sorted(FLAGS_6D))
def test_1010_2_to_1010_2_6_are_always_a_persons_check(ctx, rules, rid):
    """Locks, latches, bolts and hardware aren't in the model: each is a flag shown for every building, whatever its
    group, never a pass or a fail (typed from the page: the line each cites)."""
    r = rules[rid]
    assert r["kind"] == "flag" and "applies_when" not in r and "for_each" not in r
    assert _cites(r, *FLAGS_6D[rid])
    from rule_format.rulebook import outcome
    for g in ("B", "H-1", "R-2", "A-1", "E", "I-3", "mixed", None):
        given = {} if g is None else {"occupancy_group": g}
        assert outcome(r, given, ctx.allowed()) == "needs_review", (rid, g)


def test_1010_2_7_is_asked_wherever_the_building_may_be_group_e_b_or_i4(ctx, rules):
    """1010.2.7 (p.326 lines 23-25): Group E, Group B educational and Group I-4 occupancies; Group B is asked in full
    (whether it is educational isn't stated), two or more groups and an unstated group too; set aside only for a single
    stated group of another kind."""
    from rule_format.rulebook import outcome
    r = rules["general.bc_1010_2_7_educational_locking"]
    assert _cites(r, 326, 23) and _cites(r, 326, 30)
    for g in ("E", "B", "I-4", "mixed", None):
        given = {} if g is None else {"occupancy_group": g}
        assert outcome(r, given, ctx.allowed()) == "needs_review", g
    for g in ("A-1", "R-2", "I-2", "M", "S-1", "H-3", "F-1", "U", "I-1", "I-3", "R-1"):
        assert outcome(r, {"occupancy_group": g}, ctx.allowed()) == "not_applicable", g


def test_the_6d_flags_state_each_permissions_own_conditions(rules):
    """Review round 1 of group 6d: a flag's note is what a person checks by, so each exception or permission is stated
    with its own conditions (pp.324-326), never looser or stricter than the page."""
    note = lambda rid: " ".join(rules[rid]["examples"][0]["note"].split())
    bolts = note("general.bc_table_1010_2_4_inactive_leaf_bolts")
    # note b is printed on Group I-2's row whether or not the pair complies with 716 (p.325 lines 52-53)
    assert "Group I-2 patient care and sleeping rooms, that leaf not needed (constant latching bolts, and automatic flush " \
           "bolts under note b, whether or not under 716)" in bolts
    stair = note("general.bc_1010_2_6_stairway_doors")
    assert "when a fire alarm system is present in an area served by the stairway" in stair           # exception 3.2
    locks = note("general.bc_1010_2_4_locks_and_latches")
    assert "or persons receiving care pose a security threat" in locks                                # item 2
    assert "keys all clinical staff carry at all times" in locks
    assert "a weatherproof telephone or two-way communication system" in locks                          # item 8.2
    assert "a key-operated lock readily distinguishable as locked, a clear window" in locks             # item 8.3
    assert "on the egress side on or adjacent to the door" in locks and "on a contrasting background" in locks  # 3.3
    unlatch = note("general.bc_1010_2_1_unlatching")
    assert "each openable from the inside without a key or tool" in unlatch                              # item 5
    assert "that leaf without a doorknob, panic hardware or similar operating hardware" in unlatch       # item 4
    # review round 2: 1010.2.6 permits no lock against egress, and 1010.2.9 to 1010.2.15 permit other locking systems
    ops = note("general.bc_1010_2_door_operations")
    assert "stairway doors per 1010.2.6," not in ops and "a stairway door per 1010.2.6 still opens from the egress side" in ops
    assert "the locking systems of 1010.2.9 to 1010.2.15" in ops and "electrical locking systems" not in ops
    assert "(or a locking system of 1010.2.9 to 1010.2.15, section group 6e)" in locks


def test_the_6d_labels_say_their_section_group():
    """Review round 1 of group 6d: the labels it adds say section group 6d, not 6c."""
    labels = load(NY / "3_section_labels/gov.ny.building.2025.yaml")["labels"]
    for pid in ("1010.2", "1010.2.1", "1010.2.4", "Table 1010.2.4", "1010.2.7", "202:manual_bolt", "202:egress_court",
                "202:initiating_device", "202:life_safety_systems"):
        assert labels[pid]["notes"].endswith("Section group 6d."), pid
    assert labels["1010.1.7"]["notes"].endswith("Section group 6c.")


def test_no_rule_text_carries_yaml_quoting_into_what_people_read():
    """Review round 3 of group 6e: a rewrite once wrapped a rule's notes in its YAML quotes twice, so the workbook
    showed "'Section group 6e ... description''s ...". Every title, note, reason and example note, as loaded, has no
    doubled apostrophe and doesn't start with a quote."""
    bad = []
    for r in load(RULEBOOK)["rules"]:
        texts = [r.get("title"), r.get("notes")] + [w.get("reason") for w in r.get("review_when") or []] + \
                [e.get("note") for e in r.get("examples") or []]
        bad += [(r["id"], t[:60]) for t in texts if isinstance(t, str) and ("''" in t or t.startswith("'"))]
    assert not bad, bad


GROUP_9_SECTIONS = ("1003", "1012", "1008", "1013", "1009", "1018", "1019",        # section groups 9a to 9d
                    "1021", "1022", "1023")                                       # section group 9e


def test_every_section_group_9_reference_with_words_to_follow_is_quoted_by_a_rule():
    """Review round 1 of section group 9a (P1): 1012.9 ('Guards shall be provided where required by Section 1015') was
    labeled a reference that no flag quoted, so nothing showed a ramp's guards while 1015 isn't brought in; 1012.1's
    'shall comply' sentences (ramped aisles, curb ramps) the same. Every piece of section group 9's sections labeled
    reference (GROUP_9_SECTIONS, each later PR of group 9 adding its own) is quoted whole by some rule or flag, but a
    scope that only says where the chapter's sections apply."""
    labels = load(NY / "3_section_labels/gov.ny.building.2025.yaml")["labels"]
    book = load(RULEBOOK)
    scope_only = {"1003.1"}                          # 'The general requirements ... shall apply to all three elements'
    for pid, lab in labels.items():
        if pid.split(".")[0] not in GROUP_9_SECTIONS or lab["label"] != "reference" or pid in scope_only:
            continue
        for s in lab["sources"]:
            lines, _ = _quoted(book, s["page"], *s["lines"])
            assert set(range(s["lines"][0], s["lines"][1] + 1)) <= lines, (pid, s["page"], s["lines"])


def test_each_section_group_9_flag_names_what_it_points_to_that_isnt_brought_in():
    """Review round 3 of section group 9a (P3): the README says of each reference not brought in that 'the rule's notes
    say so'; 1012.8's flag pointed to 1014 and 1012.6's to ICC A117.1 without saying. Every section (or ICC A117.1)
    a group 9 flag's quotes name, and that isn't brought in, is named in the flag's notes."""
    labels = load(NY / "3_section_labels/gov.ny.building.2025.yaml")["labels"]
    brought = set(labels)
    for r in load(RULEBOOK)["rules"]:
        sid = r["id"].removeprefix("general.bc_").split("_")[0]
        if r.get("kind") != "flag" or sid not in GROUP_9_SECTIONS:
            continue
        quotes = " ".join(s["quote"] for s in r["sources"])
        named = set(re.findall(r"(?:Sections?|through|or|and|,) (\d{3,4}(?:\.\d+)*)", quotes))
        # review round 1 of section group 9b: chapters and standards too (Chapter 27, UL 924, NFPA 72, ASME A17.1)
        named |= set(re.findall(r"\b((?:Chapter|UL|NFPA) \d+|ICC A117\.1|ASME A17\.1)\b", quotes))
        # review round 4: in a sentence of the notes saying it isn't brought in, the reference whole; a section is
        # brought in only where its own id is a piece (1030 isn't, though 1030.7 and 1030.8 are)
        said = [s for s in re.split(r"(?<=\.) ", r.get("notes") or "") if re.search(r"(?:n't|not) brought in", s)]
        for ref in sorted(named):
            if ref in brought:
                continue
            assert any(re.search(rf"(?<![\d.]){re.escape(ref)}(?![\d]|\.\d)", s) for s in said), (r["id"], ref)


def test_no_source_or_law_file_holds_a_control_character():
    """Review round 5 of section group 9a (P2): a fix script wrote a regex's word boundaries through an ordinary
    string, so this file held four backspace characters where they belonged and the check they guarded never ran. No
    Python file under packages, apps or tests, and no law file under regulations, holds a control character but tab,
    newline and carriage return."""
    control = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    bad = []
    for top, globs in (("packages", ("*.py",)), ("apps", ("*.py",)), ("tests", ("*.py",)),
                       ("regulations", ("*.yaml", "*.md"))):
        for g in globs:
            for f in (REPO / top).rglob(g):
                if control.search(f.read_text(encoding="utf-8", errors="replace")):
                    bad.append(str(f.relative_to(REPO)))
    assert not bad, bad


def test_no_title_puts_a_bare_apostrophe_after_a_word_not_ending_in_s():
    """Review round 2 of section group 9c (P3): 'Areas of refuge' wheelchair spaces' put a plural's apostrophe on a
    word that isn't plural. A title people read never has a bare apostrophe after a letter other than s."""
    bad = [r["id"] for r in load(RULEBOOK)["rules"] if re.search(r"[a-rt-z]' ", r.get("title") or "")]
    assert not bad, bad


# Review round 1 of section group 9d (P2): a flag hidden where the law may still apply is a silent pass, and the flags'
# own examples didn't catch a wrong condition (hiding 1018.5 for two or more groups passed them all). Written from the
# law, never from the rules: where each section group 9 flag with a condition is NOT applicable (its exception spares the
# whole building, or its own words exclude the group); everywhere else, the unstated cases included, it shows.
SPRINKLED = ("nfpa_13", "nfpa_13r", "nfpa_13 alone", "nfpa_13r alone")   # 903.3.1.1 or 903.3.1.2 stated, "equipped throughout"
HIDDEN_WHERE = {
    "general.bc_1008_2_illumination_required": lambda g, s: g == "U",                       # exception 1
    "general.bc_1013_1_exit_signs_where_required": lambda g, s: g == "U",                   # exception 3
    "general.bc_1008_2_2_group_i2_exterior_landings": lambda g, s: g not in ("I-2", "mixed", None),
    "general.bc_1013_2_low_level_exit_signs_group_r1": lambda g, s: g not in ("R-1", "mixed", None) or s in SPRINKLED,
    "general.bc_1009_3_2_stairway_width": lambda g, s: s in SPRINKLED,                      # exception 1
    "general.bc_1009_3_3_area_of_refuge_at_stairways": lambda g, s: s in SPRINKLED or g == "R-2",   # exceptions 2, 5
    "general.bc_1009_4_2_elevator_area_of_refuge": lambda g, s: s in SPRINKLED,             # exception 2
    "general.bc_1009_7_2_assisted_rescue_separation": lambda g, s: s in SPRINKLED,
    "general.bc_1009_7_4_assisted_rescue_stairways": lambda g, s: s in SPRINKLED,
    "general.bc_1009_8_two_way_communication": lambda g, s: g in ("I-2", "I-3"),            # exception 6
    "general.bc_1018_3_aisles_groups_b_m": lambda g, s: g not in ("B", "M", "mixed", None),
    "general.bc_1018_5_aisles_other_occupancies": lambda g, s: g in ("B", "M"),             # "other than ... B and M"
    "general.bc_1019_3_exit_access_stairway_enclosure": lambda g, s: g in ("I-2", "I-3"),   # "other than I-2 and I-3"
    "general.bc_1019_4_exit_access_stairways_groups_i2_i3": lambda g, s: g not in ("I-2", "I-3", "mixed", None),
}
GROUPS_9 = ["A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "H-1", "H-2", "H-3", "H-4", "H-5", "I-1", "I-2",
            "I-3", "I-4", "M", "R-1", "R-2", "R-3", "R-4", "S-1", "S-2", "U", "mixed", None]
SPRINKLERS_9 = {"none": {"sprinklered_903_3_1_1": False, "sprinklered_903_3_1_2": False},
                "nfpa_13": {"sprinklered_903_3_1_1": True, "sprinklered_903_3_1_2": False},
                "nfpa_13r": {"sprinklered_903_3_1_1": False, "sprinklered_903_3_1_2": True}, None: {},
                # review round 2 of section group 9d: one of the two facts stated, the other not
                "nfpa_13 alone": {"sprinklered_903_3_1_1": True}, "nfpa_13r alone": {"sprinklered_903_3_1_2": True},
                "not 13 alone": {"sprinklered_903_3_1_1": False}, "not 13r alone": {"sprinklered_903_3_1_2": False}}


def test_each_section_group_9_flag_with_a_condition_hides_only_where_the_law_spares_the_building(ctx, rules):
    from rule_format.rulebook import outcome
    conditioned = {rid for rid, r in rules.items() if r.get("kind") == "flag" and r.get("applies_when")
                   and rid.removeprefix("general.bc_").split("_")[0] in GROUP_9_SECTIONS}
    conditioned -= {"general.bc_1018_4_merchandise_pads"}       # round 1's (2026-11-23), walked with Table 1006.2.1
    assert conditioned == set(HIDDEN_WHERE), conditioned ^ set(HIDDEN_WHERE)      # a new condition needs its oracle
    for rid, hidden in HIDDEN_WHERE.items():
        for g in GROUPS_9:
            for s, facts in SPRINKLERS_9.items():
                values = facts | ({"occupancy_group": g} if g else {})
                want = "not_applicable" if hidden(g, s) else "needs_review"
                assert outcome(rules[rid], values, ctx.allowed()) == want, (rid, g, s)


def test_each_section_group_9_flag_without_a_condition_shows_for_every_building(ctx, rules):
    """Section group 9e: the walk above tries only the flags with a condition; a flag given none must show (a person's
    check) for every group, two or more and none stated, and every sprinkler setting, so a condition added to one
    later fails here unless HIDDEN_WHERE gives it an oracle from the law. Section group 9e's 26 flags have none: whether
    a building has an egress balcony, an interior exit stairway, a smokeproof enclosure or standpipes isn't a fact
    Gordium is given, and no exception of 1021 to 1023 spares a whole building."""
    from rule_format.rulebook import outcome
    plain = sorted(rid for rid, r in rules.items() if r.get("kind") == "flag" and not r.get("applies_when")
                   and rid.removeprefix("general.bc_").split("_")[0] in GROUP_9_SECTIONS)
    assert sum(rid.startswith(("general.bc_1021_", "general.bc_1022_", "general.bc_1023_")) for rid in plain) == 26
    for rid in plain:
        for g in GROUPS_9:
            for s, facts in SPRINKLERS_9.items():
                values = facts | ({"occupancy_group": g} if g else {})
                assert outcome(rules[rid], values, ctx.allowed()) == "needs_review", (rid, g, s)


def test_1019_3s_congregate_residence_exception_is_for_stairways_only(rules):
    """Review round 1 of section group 9d (P1): 1019.3's exception 3 reads 'Exit access stairways serving and contained
    within a Group R-3 congregate residence or a Group R-4 facility' (p.343, lines 19-20), naming no ramps where its
    other exceptions do; the shown reason said 'stairway or ramp' for it, so a person could accept an open ramp there."""
    r = rules["general.bc_1019_3_exit_access_stairway_enclosure"]
    assert any("Exit access stairways serving and contained within a Group R-3" in " ".join(s["quote"].split())
               for s in r["sources"])
    note = " ".join(r["examples"][0]["note"].split())
    assert "exit access stairways (not ramps) within a Group R-3 congregate residence" in note



# Review round 1 of section group 9e (P1, P2): a shown reason that names an exception wider than the book prints it
# (a ramp given a stairways-only exception, a condition of two dropped, "not less than" said as "up to") lets a person
# accept what the law forbids. Each phrase below is the book's limit in the reason's words; each banned phrase was one.
SHOWN_MUST_SAY = {
    "general.bc_1023_1_interior_exit_stairways_general": (["except as 1028.2 permits (no more than half"], ["but as 1028.2 allows"]),
    # review round 2: 510.2's exception isn't an atrium's
    "general.bc_1023_2_enclosure_construction": (["exit stairways (not ramps) within an atrium enclosed per 404.6,",
                                                  "exit stairways (not ramps) per 510.2",
                                                  "exit stairways and ramps in Group I-3 per 408.3.8"],
                                                 ["atrium enclosed per 404.6 or per 510.2"]),
    "general.bc_1023_3_termination": (["that form one continuous protected enclosure"], []),
    "general.bc_1023_7_2_roof_assemblies": (["unless the code otherwise requires it", "extending at least 10 feet above the roof"],
                                            ["up to 10 feet"]),
    "general.bc_1023_12_1_smokeproof_termination": (["and the openings are protected as for access from other floors"], []),
}


def test_section_group_9e_reasons_name_each_exception_as_printed(rules):
    for rid, (must, never) in SHOWN_MUST_SAY.items():
        note = " ".join(rules[rid]["examples"][0]["note"].split())
        assert all(m in note for m in must), (rid, [m for m in must if m not in note])
        assert not any(n in note for n in never), rid


GROUP_9E_ON = ("1021", "1022", "1023")          # section group 9e on: each flag's own piece's label gives its reason


def test_a_flags_label_reason_is_its_shown_reason(rules):
    """Review round 1 of section group 9e: the four reasons above were wrong in the flag and in its piece's label alike;
    fixing one and not the other would show the reader two different laws. From section group 9e on, the label of a
    flag's first piece (the one its id names) gives the flag's shown reason word for word."""
    labels = load(NY / "3_section_labels/gov.ny.building.2025.yaml")["labels"]
    n = 0
    for rid, r in rules.items():
        sid = rid.removeprefix("general.bc_").split("_")[0]
        if r.get("kind") != "flag" or sid not in GROUP_9E_ON:
            continue
        piece = re.sub(r"^(\d{4})_((?:\d+_)*)[a-z].*$", lambda m: m[1] + "." + m[2].rstrip("_").replace("_", "."),
                       rid.removeprefix("general.bc_")).rstrip(".")
        assert labels[piece]["label"] == "flag", (rid, piece)
        assert " ".join(labels[piece]["reason"].split()) == " ".join(r["examples"][0]["note"].split()), rid
        n += 1
    assert n == 26


def test_every_up_to_limit_in_a_section_group_9e_reason_is_a_maximum_in_the_book(rules):
    """Review round 1 of section group 9e (P2): 1023.7.2's reason said 'up to 10 feet above the roof' for the book's 'not
    less than 10 feet'. Each 'up to N' in a group 9e flag's reason is a figure its quote caps ('need not exceed',
    'not exceeding', 'not more than', 'maximum', 'up to', 'or less')."""
    caps = r"(?:need not exceed|not exceeding|not more than|maximum(?: of)?|up to|not greater than)"
    for rid, r in rules.items():
        if r.get("kind") != "flag" or rid.removeprefix("general.bc_").split("_")[0] not in GROUP_9E_ON:
            continue
        note = " ".join(r["examples"][0]["note"].split())
        quote = " ".join(" ".join(s["quote"] for s in r["sources"]).split())
        for n in re.findall(r"\bup to (\d+(?: \d/\d)?)", note):
            assert re.search(rf"{caps}[^.;]{{0,20}}?\b{re.escape(n)}\b|\b{re.escape(n)}\b[^.;]{{0,25}}or less", quote), (rid, n)


def test_1022_1s_notes_name_what_of_1003_to_1015_isnt_brought_in(rules):
    """Review round 1 of section group 9e (P3): 1022.1 sends exits to 'the applicable requirements of Sections 1003
    through 1015'; its notes named only 1011, 1014 and 1015 as not brought in, but 1006's general parts and 1010.3 to
    1010.5.4 aren't either."""
    notes = rules["general.bc_1022_1_exits_general"]["notes"]
    assert all(s in notes for s in ("1006.1, 1006.2's own words and 1006.3 to 1006.3.2", "1010.3 to 1010.5.4", "1011",
                                    "1014", "1015"))
    assert "1006.1 to 1006.3.2" not in notes         # review round 2: that range holds 1006.2.1 and 1006.2.2, brought in


def test_the_readme_names_each_section_group_9e_flag_that_reads_icc_a117_1():
    """Review round 1 of section group 9e (P3): the README's 'Chapter 11 and ICC A117.1' entry names the flag reading
    it in each place; 1023.11's (tactile floor-level signs) was missing."""
    readme = (NY / "README.md").read_text(encoding="utf-8")
    entry = readme.split("Chapter 11 and ICC A117.1 (", 1)[1].split("), ", 1)[0]
    for r in load(RULEBOOK)["rules"]:
        sid = r["id"].removeprefix("general.bc_").split("_")[0]
        if r.get("kind") == "flag" and sid in GROUP_9E_ON and "ICC A117.1 isn't brought in" in (r.get("notes") or ""):
            piece = ".".join(p for p in r["id"].removeprefix("general.bc_").split("_") if p.isdigit())
            assert f"{piece}'s flag" in entry, r["id"]
