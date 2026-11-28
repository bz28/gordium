"""New York's commercial egress rules (the 2025 Building Code of New York State) against the Maine architect's hand
check of a day-care centre, as if the same building were in New York
(test_data/answer_keys/portland_me_19_libby_st/hand_check.yaml), and the rules' shape: every number a rule uses
stands on the second reading (text_verification.yaml), a table cell is a length in feet only where its verification
flag says so, and what the law leaves open never passes. Needs no code cache (the rules' numbers come from the repo's
verification file); the quotes are checked word for word by `python -m rule_format` where the cache is. Decided:
docs/decisions/2026-11-21_ny_building_code.md."""

import copy

import pytest
import yaml

from rule_format import code_numbers, parts
from rule_format.place import places
from rule_format.rulebook import REPO, Context, load, rulebook_file_problems

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
RULEBOOK = NY / "5_building_code_rules/drafted/general.yaml"
KEY = REPO / "test_data/answer_keys/portland_me_19_libby_st/hand_check.yaml"
I4 = {"occupancy_group_i4": True, "sprinklered_903_3_1_1": True, "sprinklered_903_3_1_2": False,
      # the sheet's day care has none of the spaces that tighten the tables (review rounds 1 and 2, 2026-11-23)
      "assembly_fixed_seating": False, "special_egress_spaces": False, "egress_balcony_increase_taken": False,
      # Chapter 4 part b: the day care is neither a high-rise (403.5.2) nor underground (405.7.1)
      "high_rise_building": False, "underground_building": False}


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(NY)


@pytest.fixture(scope="module")
def rules():
    return {r["id"]: r for r in load(RULEBOOK)["rules"]}


def _rows(rule, kind, measures, given, ctx):
    # these spaces are rooms exit access serves, never an exit themselves: said, since a space's exit rules let an
    # exit be and so need review where it isn't known (PR #181)
    if kind == "space":
        measures = {"space_is_exit": False, **measures}
    # a day care's rooms, none seating people served by aisles (1030.7: the routes' story and space parts say so from
    # the rooms' functions, design_checker/occupant_load.py), unless a test says otherwise
    measures = {**{"story": {"story_assembly_seating_possible": False},
                   "space": {"space_assembly_seating_possible": False}}.get(kind, {}), **measures}
    return [r["outcome"] for r in parts.rows(rule, {kind: [{"id": "p1", "measures": measures}]}, given, ctx.allowed())]


def test_the_rulebook_is_valid(ctx):
    assert rulebook_file_problems(RULEBOOK, ctx) == []


def test_ithaca_inherits_it_beside_the_house_code_and_a_check_picks_one():
    """Wired into Check project 2026-11-22 (docs/decisions/2026-11-22_which_ny_code.md): Ithaca inherits both of New
    York's books, each saying which buildings it covers, so a check runs the one that covers the building."""
    [ithaca] = [p for p in places() if NY in p.inherits]
    assert [f.name for f in ithaca.inherits] == ["new_york_state", "new_york_state_building"]
    assert [load(f / "state.yaml")["scope"] for f in ithaca.inherits] == ["residential_code", "building_code"]


# What the sheet measured, the measure Gordium reads it as, and the rule that decides it here
SHEET = {
    "Exit access travel distance (the most remote point to an exit)":
        ("general.bc_1017_2_travel_distance", "story", {"egress_travel_distance": 130.667}),
    "Common path of egress travel":
        ("general.bc_1006_2_1_two_exits", "space", {"space_common_path": 48.5, "space_exit_count": 2,
                                                     "space_occupant_load": 30}),
    "Dead-end corridor":
        ("general.bc_1020_5_dead_end", "corridor", {"corridor_dead_end_length": 21.5,
                                                    "corridor_dead_end_least_width": 10}),
    "Exit (or exit access doorway) remoteness":
        ("general.bc_1007_1_1_remoteness", "story", {"exit_remoteness_ratio": 0.8745, "story_exit_count": 2}),
    "Accessory storage area on the story":
        ("general.bc_508_2_3_accessory_area", "story", {"story_accessory_area": 1428, "story_gross_floor_area": 16509,
                                                        "story_net_floor_area": 15000}),   # net supposed: the sheet has none
}


def test_the_sheets_building_passes_each_new_york_limit_as_it_passed_maines(ctx, rules):
    """The sheet's own numbers, under New York's 2025 limits for the same I-4, sprinklered (NFPA 13) building: the same
    result as the sheet, pass, for each check; each rule has a worked example on those numbers."""
    key = yaml.safe_load(KEY.read_text(encoding="utf-8"))
    checks = {c["what"]: c for c in key["checks"]}
    for what, (rid, kind, measures) in SHEET.items():
        assert checks[what]["result"] == "pass"
        assert _rows(rules[rid], kind, measures, I4, ctx) == ["pass"], rid
        assert any("The answer key" in (e.get("note") or "") and e["expect"] == "pass" for e in rules[rid]["examples"]), rid


def test_the_limits_are_new_yorks(rules):
    """2025 BCNYS: travel 200 ft with NFPA 13 (note c), 150 ft without; one-exit space 10 occupants and 75 ft; dead end
    20 ft or 2.5 x its width; one-third of the diagonal sprinklered, one-half not; 10 percent of the story."""
    has = {rid: r.get("check") for rid, r in rules.items()}
    assert has["general.bc_1017_2_travel_distance"] == "egress_travel_distance <= (200 if sprinklered_903_3_1_1 else 150)"
    assert "space_occupant_load <= 10" in has["general.bc_1006_2_1_two_exits"]
    assert "space_common_path <= 75" in has["general.bc_1006_2_1_two_exits"]
    assert has["general.bc_1020_5_dead_end"] == ("corridor_dead_end_length <= 20 or corridor_dead_end_length < 2.5 * "
                                                 "corridor_dead_end_least_width")
    assert "1 / 3 if" in has["general.bc_1007_1_1_remoteness"] and "else 1 / 2" in has["general.bc_1007_1_1_remoteness"]
    assert has["general.bc_508_2_3_accessory_area"] == ("story_accessory_area <= 0.10 * story_net_floor_area and "
                                                        "story_accessory_area <= 0.10 * story_gross_floor_area")


def test_travel_with_an_nfpa_13r_system_only_is_held_to_150_ft(ctx, rules):
    r = rules["general.bc_1017_2_travel_distance"]
    nfpa_13r = I4 | {"sprinklered_903_3_1_1": False, "sprinklered_903_3_1_2": True}
    assert _rows(r, "story", {"egress_travel_distance": 180}, I4, ctx) == ["pass"]
    assert _rows(r, "story", {"egress_travel_distance": 180}, nfpa_13r, ctx) == ["fail"]
    assert _rows(r, "story", {"egress_travel_distance": 180}, {"occupancy_group_i4": True}, ctx) == ["needs_review"]


def test_a_two_exit_space_over_75_ft_needs_review_while_the_tables_reading_is_open(ctx, rules):
    """Table 1006.2.1 may cap the common path (as the 2009 IBC's 1014.3 did) or only call for a second exit: a space with
    two exits and a common path over 75 ft is never passed, and never failed, until the question is answered."""
    r = rules["general.bc_1006_2_1_two_exits"]
    two = {"space_exit_count": 2, "space_occupant_load": 30}
    assert _rows(r, "space", two | {"space_common_path": 75}, I4, ctx) == ["pass"]
    assert _rows(r, "space", two | {"space_common_path": 80}, I4, ctx) == ["needs_review"]
    one = {"space_exit_count": 1, "space_occupant_load": 8}
    assert _rows(r, "space", one | {"space_common_path": 80}, I4, ctx) == ["fail"]
    assert _rows(r, "space", one | {"space_common_path": 30}, I4 | {"sprinklered_903_3_1_1": False}, ctx) == ["fail"]
    assert r["open_questions"] and r["research"][0]["why_open"]


def test_a_path_through_a_locked_room_fails_even_when_it_also_crosses_another_room(ctx, rules):
    r = rules["general.bc_1016_2_intervening_spaces"]
    m = {"space_egress_through_locked_room": 1, "space_egress_through_kitchen_storage": 0,
         "space_egress_sleeping_through_sleeping_or_toilet": 0, "space_egress_through_other_room": 1}
    assert _rows(r, "space", m, I4, ctx) == ["fail"]
    assert _rows(r, "space", m | {"space_egress_through_locked_room": 0}, I4, ctx) == ["needs_review"]


def test_every_piece_labeled_rule_or_flag_has_a_rule_and_every_table_one_named_for_it():
    got = yaml.safe_load((NY / "6_coverage_report/gov.ny.building.2025.rules.yaml").read_text(encoding="utf-8"))
    assert got["not_checked_yet"] == []
    for pid, e in got["pieces"].items():
        if pid.startswith("Table "):
            assert e["rules"] and all("_table_" in r for r in e["rules"]), (pid, e["rules"])


def test_every_rule_number_stands_on_the_second_reading(ctx, rules):
    for rid, r in rules.items():
        if r["kind"] == "rule":
            assert code_numbers.cites_book(r["sources"], ctx), rid
            assert code_numbers.problems(r, r["sources"], ctx) == [], rid


def test_a_table_cell_is_a_length_in_feet_only_where_its_flag_says_so(ctx, rules, monkeypatch):
    """Table 1017.2 prints "(feet)" in its column headings, never beside a number, so its cells are read with no unit;
    the verification flag naming them "a length in feet" makes them one (code_numbers._column_feet). Without it the
    cell is a count and backs no travel distance; and an occupant-load cell of Table 1006.2.1 never backs a length."""
    r = rules["general.bc_1017_2_travel_distance"]
    assert code_numbers.problems(r, r["sources"], ctx) == []
    entry = ctx.verification["gov.ny.building.2025.pdf"]["pieces"]["Table 1017.2"]
    stripped = copy.deepcopy(ctx.verification)
    stripped["gov.ny.building.2025.pdf"]["pieces"]["Table 1017.2"] = dict(
        entry, flags=[f.replace(code_numbers.COLUMN_FEET, "a number") for f in entry["flags"]])
    monkeypatch.setattr(ctx, "verification", stripped)
    assert any("isn't one of" in p and "200" in p for p in code_numbers.problems(r, r["sources"], ctx))
    monkeypatch.undo()
    space = rules["general.bc_1006_2_1_two_exits"]
    as_feet = dict(space, check="space_exit_count >= 2 or space_common_path <= 10")     # 10 is an occupant load
    assert any("isn't one of" in p for p in code_numbers.problems(as_feet, space["sources"], ctx))


# ---- review round 1 (2026-11-22) ------------------------------------------------------------------------------------

def test_accessory_area_between_the_net_and_gross_readings_never_passes(ctx, rules):
    """508.2.3's "floor area of the story" is open between 202 FLOOR AREA, GROSS and NET: pass only within 10 percent
    of the net (the smaller), fail only over 10 percent of the gross, needs review between or where one is missing."""
    r = rules["general.bc_508_2_3_accessory_area"]
    both = {"story_gross_floor_area": 16509, "story_net_floor_area": 15000}
    assert _rows(r, "story", both | {"story_accessory_area": 1600}, {}, ctx) == ["needs_review"]
    assert _rows(r, "story", {"story_accessory_area": 1600, "story_gross_floor_area": 16509}, {}, ctx) == ["needs_review"]
    assert _rows(r, "story", both | {"story_accessory_area": 1400}, {}, ctx) == ["pass"]
    assert _rows(r, "story", both | {"story_accessory_area": 1700}, {}, ctx) == ["fail"]
    assert _rows(r, "story", {"story_accessory_area": 1700, "story_gross_floor_area": 16509}, {}, ctx) == ["fail"]
    research = r["research"][0]
    assert r["open_questions"] and {g["id"] for g in research["readings"]} == {"gross_floor_area", "net_floor_area"}
    assert {"202:floor_area_gross", "202:floor_area_net"} <= set(research["searched"])


def test_floor_area_gross_and_net_are_brought_in_quoted_and_measured_by_their_definitions():
    pieces = {p["id"] for p in map(__import__("json").loads, (NY / "2_extracted_text/gov.ny.building.2025.sections.jsonl")
                                   .read_text(encoding="utf-8").splitlines()[1:])}
    assert {"202:floor_area_gross", "202:floor_area_net"} <= pieces
    defs = load(NY / "4_term_definitions/definitions.yaml")
    assert defs["bc_floor_area_gross"]["sources"][0]["quote"].startswith("[BE] FLOOR AREA, GROSS.")
    assert defs["bc_floor_area_net"]["sources"][0]["quote"].startswith("[BE] FLOOR AREA, NET.")
    story = parts.load_registry()["story"]["measures"]
    gross, net = story["story_gross_floor_area"]["meaning"], story["story_net_floor_area"]["meaning"]
    assert "202 FLOOR AREA, GROSS" in gross and "exclusive of vent shafts and courts" in gross
    assert "shafts with no openings or interior courts" in gross
    assert "202 FLOOR AREA, NET" in net and "toilet rooms, mechanical rooms and closets" in net


def test_each_space_with_two_or_more_doorways_has_their_separation_checked(ctx, rules):
    """1007.1 separates exits and exit access doorways 'serving spaces, including individual building stories': a room
    is checked, not only its story; an unmeasured room needs review, never a pass."""
    r = rules["general.bc_1007_1_1_space_remoteness"]
    assert r["for_each"] == "space"
    i4_only = I4 | {"other_occupancy_present": False}
    room = {"space_exit_count": 2, "space_occupant_load": 30, "space_common_path": 40}
    assert _rows(r, "space", room | {"space_exit_remoteness_ratio": 0.2}, i4_only, ctx) == ["fail"]
    assert _rows(r, "space", room | {"space_exit_remoteness_ratio": 0.4}, i4_only, ctx) == ["pass"]
    assert _rows(r, "space", room | {"space_exit_remoteness_ratio": 0.4}, i4_only | {"sprinklered_903_3_1_1": False},
                 ctx) == ["fail"]                                            # unsprinklered: one-half
    assert _rows(r, "space", room, i4_only, ctx) == ["needs_review"]         # not measured
    three = rules["general.bc_1007_1_2_space_three_or_more"]
    assert three["for_each"] == "space"
    assert _rows(three, "space", {"space_exit_count": 3, "space_occupant_load": 600, "space_exit_remoteness_ratio": 0.2},
                 I4, ctx) == ["fail"]
    got = yaml.safe_load((NY / "6_coverage_report/gov.ny.building.2025.rules.yaml").read_text(encoding="utf-8"))
    assert "general.bc_1007_1_1_space_remoteness" in got["pieces"]["1007.1.1"]["rules"]
    assert "general.bc_1007_1_2_space_three_or_more" in got["pieces"]["1007.1.2"]["rules"]


def test_only_a_lobby_taking_item_4s_exception_escapes_the_locked_room_fail(ctx, rules):
    """1016.2 item 4's exception is only for an elevator lobby's electrically locked exit access door per 1010.2.14:
    such a lobby needs review; any other lockable lobby is a locked room and fails."""
    r = rules["general.bc_1016_2_intervening_spaces"]
    clear = {"space_egress_through_locked_room": 0, "space_egress_through_kitchen_storage": 0,
             "space_egress_sleeping_through_sleeping_or_toilet": 0, "space_egress_through_other_room": 0,
             "space_egress_through_electrically_locked_lobby": 0}
    assert _rows(r, "space", clear, I4, ctx) == ["pass"]
    assert _rows(r, "space", clear | {"space_egress_through_electrically_locked_lobby": 1}, I4, ctx) == ["needs_review"]
    assert _rows(r, "space", clear | {"space_egress_through_locked_room": 1,
                                      "space_egress_through_electrically_locked_lobby": 1}, I4, ctx) == ["fail"]
    meaning = parts.load_registry()["space"]["measures"]["space_egress_through_locked_room"]["meaning"]
    assert "enclosed elevator lobbies included" in meaning and "electrically locked" in meaning


# ---- review round 2 (2026-11-22) ------------------------------------------------------------------------------------

def test_three_or_more_doorways_fail_1007_1_2_only_where_three_are_required(ctx, rules):
    """1007.1.2 applies 'Where access to three or more exits is required' (a space: 1006.2.1.1, from 501 occupants),
    not wherever three doors are drawn: a small room with three close doors needs review, never fail."""
    r = rules["general.bc_1007_1_2_space_three_or_more"]
    small = {"space_exit_count": 3, "space_occupant_load": 6, "space_common_path": 20, "space_exit_remoteness_ratio": 0.2}
    assert _rows(r, "space", small, I4, ctx) == ["needs_review"]
    assert _rows(r, "space", small | {"space_occupant_load": 501}, I4, ctx) == ["fail"]
    assert _rows(r, "space", {k: v for k, v in small.items() if k != "space_occupant_load"}, I4, ctx) == ["needs_review"]
    assert _rows(rules["general.bc_1007_1_1_space_remoteness"], "space", small, I4 | {"other_occupancy_present": False},
                 ctx) == ["needs_review"]                                   # the two rules agree on that room
    assert any(e["expect"] == "needs_review" and e["parts"]["space"][0]["measures"].get("space_occupant_load") == 6
               for e in r["examples"])
    story = rules["general.bc_1007_1_2_three_or_more_exits"]      # a story's: only 'a reasonable distance apart' is a person's
    assert story["kind"] == "flag"


def test_a_close_pair_outside_group_i4_needs_review_never_fails(ctx, rules):
    """Only Table 1006.2.1's I-4 row is encoded: a Group B office of 30 (its row allows 49 with one exit) with two close
    doors may not need two, so it needs review; so does a space whose occupancy isn't stated."""
    r = rules["general.bc_1007_1_1_space_remoteness"]
    office = {"space_exit_count": 2, "space_exit_remoteness_ratio": 0.2, "space_occupant_load": 30, "space_common_path": 40}
    group_b = {"occupancy_group_i4": False, "other_occupancy_present": True, "sprinklered_903_3_1_1": True,
               "sprinklered_903_3_1_2": False}
    assert _rows(r, "space", office, group_b, ctx) == ["needs_review"]
    assert _rows(r, "space", office, I4 | {"other_occupancy_present": True}, ctx) == ["needs_review"]
    assert _rows(r, "space", office, {"sprinklered_903_3_1_1": True, "sprinklered_903_3_1_2": False}, ctx) == ["needs_review"]
    assert _rows(r, "space", office, I4 | {"other_occupancy_present": False}, ctx) == ["fail"]


def test_the_floor_area_question_cites_no_forum_as_support(rules):
    research = rules["general.bc_508_2_3_accessory_area"]["research"][0]
    text = " ".join(g["reading"] for g in research["readings"]) + " ".join(s["cite"] for s in research["sources"])
    assert "forum" not in text.lower()
    # why_open names practitioners only among what was searched and not relied on, never as support
    support = research["why_open"].split("(searched")[0].lower()
    assert "practitioner" not in support and "forum" not in support


# ---- review round 3 (2026-11-22) ------------------------------------------------------------------------------------

def test_a_story_that_may_have_one_exit_is_never_failed_for_two_close_exits(ctx, rules):
    """A story needs two exits only where 1006.3.3 and 1006.3.4 say so: Group I on the first story with at most 10
    occupants and 75 ft (Table 1006.3.4(2)) may have one, so its two close exits need review, never fail; so do a
    story whose rooms exit directly outside (1006.3.4 item 2) and a story in another occupancy. An upper story of
    Group I, or one over 10 occupants, needs two, and there a close pair fails."""
    r = rules["general.bc_1007_1_1_remoteness"]
    i4 = I4 | {"other_occupancy_present": False}
    close = {"exit_remoteness_ratio": 0.2, "story_exit_count": 2}
    small = close | {"story_first_above_or_below_grade": True, "story_occupant_load": 8, "egress_travel_distance": 60}
    assert _rows(r, "story", small, i4, ctx) == ["needs_review"]
    assert _rows(r, "story", small | {"story_occupant_load": 40, "story_rooms_exit_directly_outside": True}, i4, ctx) \
        == ["needs_review"]
    assert _rows(r, "story", small, I4 | {"other_occupancy_present": True}, ctx) == ["needs_review"]
    assert _rows(r, "story", small | {"story_occupant_load": 40, "story_rooms_exit_directly_outside": False}, i4, ctx) \
        == ["fail"]
    assert _rows(r, "story", close | {"story_first_above_or_below_grade": False, "story_rooms_exit_directly_outside": False},
                 i4, ctx) == ["fail"]
    assert _rows(r, "story", close | {"story_first_above_or_below_grade": False}, i4, ctx) == ["needs_review"]  # blank
    exits = rules["general.bc_1006_3_3_story_exits"]
    one = {"story_exit_count": 1, "story_first_above_or_below_grade": True, "story_occupant_load": 8,
           "egress_travel_distance": 60}
    assert _rows(exits, "story", one, i4, ctx) == ["pass"]
    assert _rows(exits, "story", one | {"story_first_above_or_below_grade": False, "story_rooms_exit_directly_outside": False},
                 i4, ctx) == ["fail"]


# ---- review round 4 (2026-11-22) ------------------------------------------------------------------------------------

def test_an_upper_story_whose_rooms_exit_directly_outside_needs_review_in_both_story_rules(ctx, rules):
    """1006.3.4 item 2 sets no story: rooms that exit directly to the exterior at the level of exit discharge may be
    on an upper story of a sloping site. Stated there, one exit may do: never a fail, never a pass."""
    i4 = I4 | {"other_occupancy_present": False}
    upper = {"story_first_above_or_below_grade": False, "story_rooms_exit_directly_outside": True,
             "story_occupant_load": 40, "egress_travel_distance": 60}
    assert _rows(rules["general.bc_1006_3_3_story_exits"], "story", upper | {"story_exit_count": 1}, i4, ctx)         == ["needs_review"]
    assert _rows(rules["general.bc_1007_1_1_remoteness"], "story", upper | {"story_exit_count": 2,
                                                                            "exit_remoteness_ratio": 0.3}, i4, ctx)         == ["needs_review"]


def test_an_occupant_load_just_over_500_never_passes_with_two_exits(ctx, rules):
    """Table 1006.3.3 prints the two-exit band '1-500': anything over 500 (500.5) needs three, for a story and, on the
    safe side, for a space (1006.2.1.1: three from 501)."""
    i4 = I4 | {"other_occupancy_present": False}
    story = {"story_exit_count": 2, "story_occupant_load": 500.5, "story_first_above_or_below_grade": True,
             "egress_travel_distance": 100, "story_rooms_exit_directly_outside": False}
    assert _rows(rules["general.bc_1006_3_3_story_exits"], "story", story, i4, ctx) == ["fail"]
    assert _rows(rules["general.bc_1006_3_3_story_exits"], "story", story | {"story_occupant_load": 500}, i4, ctx) == ["pass"]
    space = {"space_is_exit": False, "space_exit_count": 2, "space_occupant_load": 500.5}
    assert _rows(rules["general.bc_1006_2_1_1_three_or_more_exits"], "space", space, i4, ctx) == ["fail"]
    three = {"space_exit_count": 3, "space_occupant_load": 500.5, "space_exit_remoteness_ratio": 0.2}
    assert _rows(rules["general.bc_1007_1_2_space_three_or_more"], "space", three, i4, ctx) == ["fail"]
    for rid in ("general.bc_1006_3_3_story_exits", "general.bc_1006_2_1_1_three_or_more_exits",
                "general.bc_1007_1_2_space_three_or_more"):
        assert "< 501" not in str(rules[rid].get("check")) + str(rules[rid].get("review_when")), rid


def test_a_printed_range_backs_its_upper_end_only_where_its_flag_names_it(ctx, rules, monkeypatch):
    """'1-500': numbers.py loses the 500 (no number after a hyphen, so 'R-2' is never a number); the verification flag
    naming the printed range makes it a number the rule may use (code_numbers._printed_ranges), and only then."""
    r = rules["general.bc_1006_3_3_story_exits"]
    assert code_numbers.problems(r, r["sources"], ctx) == []
    entry = ctx.verification["gov.ny.building.2025.pdf"]["pieces"]["Table 1006.3.3"]
    stripped = copy.deepcopy(ctx.verification)
    stripped["gov.ny.building.2025.pdf"]["pieces"]["Table 1006.3.3"] = dict(
        entry, flags=[f.replace("printed range", "range") for f in entry["flags"]])
    monkeypatch.setattr(ctx, "verification", stripped)
    assert any("500" in p for p in code_numbers.problems(r, r["sources"], ctx))


def test_both_space_rules_record_the_over_500_reading_with_its_sources(rules):
    """The 500 of a space's two-exit band is Table 1006.3.3's printed '1-500', used for a space by analogy, and a
    fractional load over 500 needs three: Gordium's reading (a finding), with 1006.2.1.1, Table 1006.3.3, OCCUPANT
    LOAD and 1004.5 as its sources, for the architects to confirm."""
    for rid in ("general.bc_1006_2_1_1_three_or_more_exits", "general.bc_1007_1_2_space_three_or_more"):
        r = rules[rid]
        found = [f for f in r.get("findings") or [] if f.get("id") == "space_over_500_needs_three"]
        assert len(found) == 1, rid
        f = found[0]
        assert f["kind"] == "reading" and f["confirm_with"] == "the architects", rid
        quoted = " ".join(s.get("quote", "") for s in f["sources"] if "file" in s)
        assert "501 to 1,000" in quoted and "1-500" in quoted and "OCCUPANT LOAD" in quoted, rid
        assert any(s.get("rank") == 3 and "1004.5" in s["cite"] for s in f["sources"]), rid
        assert "by analogy" in r["notes"] and "the finding on loads over 500" in r["notes"], rid
    label = load(NY / "3_section_labels/gov.ny.building.2025.yaml")["labels"]["Table 1006.3.3"]["reason"]
    assert "general.bc_1006_2_1_1_three_or_more_exits" in label and "general.bc_1007_1_2_space_three_or_more" in label
