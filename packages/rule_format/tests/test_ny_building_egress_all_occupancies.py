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


# a story or space part as the routes give one whose story's rooms all state non-assembly functions (no seating
# served by aisles, 1030.7: design_checker/occupant_load.py), unless a test says otherwise
NO_SEATING = {"story": {"story_assembly_seating_possible": False}, "space": {"space_assembly_seating_possible": False}}


def _one(rule, kind, measures, given, ctx):
    measures = {**NO_SEATING.get(kind, {}), **measures}
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
         "1010.1.2": (323, 11, 23), "1010.1.2.1": (323, 24, 25)}                       # section group 6b                                                       # section group 5c      # review round 1 of group 4c: its five conditions quoted too
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
}
NO_LIMIT = {"1006.2.1", "1017.2", "1020.5", "1020.2", "1020.3", "1020.4", "1020.6", "1020.7", "1020.6.1", "1005.3.1", "1005.3.2", "1005.4", "1005.5", "1005.6", "1005.7",
            "1005.7.1", "1005.7.2", "1005.7.3", "1010.1", "1010.1.1", "1010.1.1.1", "1010.1.2",
            "1010.1.2.1"}          # the piece naming itself
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
    secs = [str(x) for x in brought["sections"] + brought["alone"] if not str(x).startswith("Table")]
    pat = re.compile(r"(?:Section )?(\d{3,4}(?:\.\d+)*)(?:'s)?[^.;]{0,40}?(?:\(|, )[^()]{0,40}?not brought in")

    def stale(t):
        return [m.group(0) for m in pat.finditer(t) if any(m.group(1) == s or m.group(1).startswith(s + ".")
                                                         for s in secs)]
    bad = []
    for r in load(RULEBOOK)["rules"]:
        texts = [r.get("title"), r.get("notes")] + [w["reason"] for w in r.get("review_when") or []] + \
                [e.get("note") for e in r.get("examples") or []]
        bad += [(r["id"], x) for t in texts if isinstance(t, str) for x in stale(t)]
    bad += [("sources.yaml", x) for x in stale((NY / "1_source_documents/sources.yaml").read_text(encoding="utf-8"))]
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
    than <n>' is '>' everywhere in this book (a condition, but a comparison all the same)."""
    pieces = load(NY / "text_verification.yaml")["pieces"]
    seen = []
    for pid, e in pieces.items():
        for n, comp in zip(e["second_reading_numbers"], e["second_reading_comparisons"]):
            if str(n).startswith("more than "):
                seen.append((pid, n, comp))
    assert seen and all(comp == ">" for _, _, comp in seen), [x for x in seen if x[2] != ">"]


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




def test_a_restaurant_story_with_no_fixed_seats_never_passes_a_travel_or_common_path_row(ctx, rules):
    """BCNYS 1030.7 (p.354, lines 50-51): "Where aisles are provided for seating, the distance shall be measured along
    the aisles and aisle accessways without travel over or on the seats", fixed seats or loose: every occupied portion
    with seats, tables or displays has aisles (1030.9), and seating at tables has aisle accessways (1030.13.1). A Group
    A-2 restaurant story (tables and chairs) with fixed seating stated no: 100 ft of travel and a one-exit dining room's
    20 ft common path, both within their rows, need review where a room on the story may seat people served by aisles
    (the routes' story and space parts, design_checker/occupant_load.py) and pass where none may. Every rule that
    reviews on fixed seating for travel or a common path reviews on the story's seating too (1020.3's corridor capacity
    aside: its fixed-seating review is the seating's capacity factors, not travel)."""
    a2 = {"occupancy_group": "A-2", "occupancy_group_i4": False, "other_occupancy_present": True, **NONE, **STATED}
    travel = rules["general.bc_table_1017_2_a_e_f1_m_r_s1"]
    for seats, want in ((True, "needs_review"), (False, "pass")):
        assert _one(travel, "story", {**_travel(100), "story_assembly_seating_possible": seats}, a2, ctx) == want
    cp = rules["general.bc_table_1006_2_1_a_e_m"]
    space = {"space_is_exit": False, "space_exit_count": 1, "space_occupant_load": 40, "space_common_path": 20}
    for seats, want in ((True, "needs_review"), (False, "pass")):
        assert _one(cp, "space", {**space, "space_assembly_seating_possible": seats}, a2, ctx) == want
    for rid, r in rules.items():
        fixed = [w["when"] for w in r.get("review_when") or [] if re.search(r"assembly_fixed_seating", w["when"])]
        if not fixed or rid == "general.bc_1020_3_corridor_capacity":
            continue
        m = {"story": "story_assembly_seating_possible", "space": "space_assembly_seating_possible"}[r["for_each"]]
        twins = [w["when"] for w in r["review_when"] if re.search(rf"{m}", w["when"])]
        assert [re.sub(r"assembly_fixed_seating", m, f) for f in fixed] == twins, rid
        assert all(_cites(r, 354, 50) or "1030.7" in w["reason"] for w in r["review_when"] if m in w["when"]), rid
