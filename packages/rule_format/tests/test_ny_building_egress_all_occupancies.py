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
NFPA13 = {S1: True, S2: False}
NONE = {S1: False, S2: False}
STATED = {"egress_balcony_increase_taken": False, "assembly_fixed_seating": False}

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


def _cites(rule, page, line):
    return any(s.get("page") == page and s["lines"][0] <= line <= s["lines"][1] for s in rule["sources"])


@pytest.mark.parametrize("line", sorted(TABLE_1017_2))
def test_table_1017_2_each_row_at_its_limit_and_just_past(ctx, rules, line):
    groups, without, with_, slug = TABLE_1017_2[line]
    rule = rules[f"general.bc_table_1017_2_{slug}"]
    assert _cites(rule, 341, line)
    for g in groups:
        given = {"occupancy_group": g} | STATED
        assert _one(rule, "story", {"egress_travel_distance": with_}, given | NFPA13, ctx) == "pass", (g, with_)
        past = with_ + 0.01 + (100 if g == "H-5" else 150 if g in ("F-1", "S-1") else 0)  # past 1017.2.3, 1017.2.2
        assert _one(rule, "story", {"egress_travel_distance": past}, given | NFPA13, ctx) == "fail", (g, past)
        if without is None:          # Not Permitted without a sprinkler system, whatever the distance
            assert _one(rule, "story", {"egress_travel_distance": 1}, given | NONE, ctx) == "fail", g
        else:
            assert _one(rule, "story", {"egress_travel_distance": without}, given | NONE, ctx) == "pass", g
            assert _one(rule, "story", {"egress_travel_distance": without + 0.01}, given | NONE, ctx) == "fail", g
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
    assert _one(row, "story", {"egress_travel_distance": 300.01}, r2 | {"egress_balcony_increase_taken": True},
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
