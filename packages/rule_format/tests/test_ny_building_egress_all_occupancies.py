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
         "1017.2": (341, 23, 23), "1020.5": (344, 37, 47)}
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
}
NO_LIMIT = {"1006.2.1", "1017.2", "1020.5"}          # the piece naming itself
# lines that name no section and set nothing: 'For SI' and 'NP =' (Table 1006.2.1), 'For SI' (Table 1017.2),
# 'Exceptions:' (1020.5)
UNQUOTED = {(315, 34), (315, 35), (341, 39), (344, 39)}


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
    assert _one(r, "space", two | {"space_common_path": 30}, base | {"assembly_fixed_seating": True}, ctx) == "pass"
    assert _one(r, "space", two | {"space_occupant_load": 49, "space_common_path": 75},
                base | {"assembly_fixed_seating": True}, ctx) == "pass"
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
# Table 1006.3.4(2), p.317 lines 39-43: (groups, the story, most occupants, travel without / with NFPA 13 per note b)
TABLE_1006_3_4_2 = [
    (A + ["E", "M", "U"], FIRST, 49, 75, 75), (["B", "F-1", "F-2"], FIRST, 49, 75, 100),
    (["H-2", "H-3"], FIRST, 3, 25, 25), (["H-4", "H-5", "I-1", "I-2", "I-3", "R-1"], FIRST, 10, 75, 75),
    (["S-1"], FIRST, 29, 75, 100), (["M"], SECOND, 29, 75, 75), (["B", "F-1", "F-2", "S-1"], SECOND, 29, 75, 100)]
STORY_FACTS = {"emergency_escape_openings_1031": True, "r2_sleeping_units": False}


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
            assert _one(r, "story", _story(where, most, with_), given | NFPA13, ctx) == "pass", (g, where)
            assert _one(r, "story", _story(where, most + 0.5, 10), given | NFPA13, ctx) == "fail", (g, where)
            assert _one(r, "story", _story(where, 1, with_ + 0.01), given | NFPA13, ctx) == "fail", (g, where)
            assert _one(r, "story", _story(where, most, without), given | NONE, ctx) == "pass", (g, where)
            assert _one(r, "story", _story(where, most, without + 0.01), given | NONE, ctx) == "fail", (g, where)
    for g in ("A-2", "E", "U", "H-4", "I-1", "R-1"):                         # not in the second-story row
        r = _story_rule(rules, g)
        assert _one(r, "story", _story(SECOND, 1, 10), {"occupancy_group": g} | STORY_FACTS | NFPA13, ctx) == "fail", g
    third = _story(None, 1, 10)
    assert _one(_story_rule(rules, "B"), "story", third, {"occupancy_group": "B"} | NFPA13, ctx) == "fail"  # NP


def test_two_exits_by_table_1006_3_3_and_r3_r4_with_one(ctx, rules):
    r = _story_rule(rules, "B")
    b = {"occupancy_group": "B"} | NFPA13
    assert _one(r, "story", _story(FIRST, 500, 300, exits=2), b, ctx) == "pass"
    assert _one(r, "story", _story(FIRST, 500.5, 300, exits=2), b, ctx) == "fail"           # 501-1,000: three
    assert _one(r, "story", _story(FIRST, 1000, 300, exits=3), b, ctx) == "pass"
    assert _one(r, "story", _story(FIRST, 1000.5, 300, exits=3), b, ctx) == "fail"          # more: four
    h = rules["general.bc_table_1006_3_4_2__h_i_r"]
    assert _one(h, "story", _story(SECOND, 40, 200), {"occupancy_group": "R-3"} | NFPA13, ctx) == "pass"
    assert _one(h, "story", _story(FIRST, 2, 10), {"occupancy_group": "H-1"} | NFPA13, ctx) == "fail"  # no H-1 row


def test_table_1006_3_4_1_group_r2_of_dwelling_units(ctx, rules):
    """p.317 lines 21-24: a basement or first to third story, 4 dwelling units, 125 ft, only with note a's system
    and escape openings; the fourth story and higher NP. Sleeping units are Table 1006.3.4(2)'s (note b)."""
    r = rules["general.bc_table_1006_3_4_1__r2_dwelling_units"]
    du = {"occupancy_group": "R-2", "r2_sleeping_units": False, "emergency_escape_openings_1031": True}
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
    room = {"space_exit_count": 2, "space_exit_remoteness_ratio": 0.2, "space_common_path": 40}
    assert _one(space, "space", room | {"space_occupant_load": 60}, b, ctx) == "fail"
    assert _one(space, "space", room | {"space_occupant_load": 30}, b, ctx) == "needs_review"
    mixed = b | {"occupancy_group": "mixed"}
    assert _one(space, "space", room | {"space_occupant_load": 60}, mixed, ctx) == "needs_review"


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
