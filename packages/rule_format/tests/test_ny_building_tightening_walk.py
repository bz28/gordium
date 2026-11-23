"""A property walk over every drafted Chapter 10 limit rule of New York's Building Code (review round 2, 2026-11-23:
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md): for every occupancy group (A-1 to U, a building of two
or more groups, and one whose group isn't stated), every value of every building fact the rules read (yes, no, not
stated; each sprinkler system, or none stated) and measures just inside and just past each tightened limit, no rule
of the drafted tables passes where a tightening applies (its fact yes or not stated) and the measure is past the
tightened limit. The oracle is written from the law's own list of what tightens the tables (the plan's review round
1 table), never from the rules. Completeness is checked too: the facts the walk varies are exactly the building facts
the drafted rules read, so a rule reading a new fact the walk doesn't vary fails here."""

import itertools

import pytest

from rule_format import formula, parts
from rule_format.rulebook import REPO, Context, load

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
RULEBOOK = NY / "5_building_code_rules/drafted/general.yaml"
PROPOSED = NY / "5_building_code_rules/drafted/records/proposed_measures.yaml"
GROUPS = ["A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "H-1", "H-2", "H-3", "H-4", "H-5", "I-1", "I-2",
          "I-3", "I-4", "M", "R-1", "R-2", "R-3", "R-4", "S-1", "S-2", "U"]
UNSTATED = object()
SPRINKLERS = {"nfpa_13": (True, False, False), "nfpa_13r": (False, True, False), "nfpa_13d": (False, False, True),
              "none": (False, False, False), UNSTATED: None}
YES_NO = (True, False, UNSTATED)
# the building facts the walk varies (each yes, no, not stated), beside the group and the sprinkler system
FACTS = ("assembly_fixed_seating", "special_egress_spaces", "merchandise_pads", "building_has_atrium",
         "egress_balcony_increase_taken")
DERIVED = ("occupancy_group", "occupancy_group_i4", "other_occupancy_present", "sprinklered_903_3_1_1",
           "sprinklered_903_3_1_2", "sprinklered_903_3_1_3")


def _scope(rules):
    """The rules that hold a drafted table's travel or common-path limit (the ones a tightening narrows); 407.4.2's
    rule measures a sleeping room's own travel, not the story's, so it isn't one."""
    keep = ("general.bc_table_1017_2_", "general.bc_table_1006_2_1_", "general.bc_1017_2_travel_distance",
            "general.bc_1006_2_1_two_exits", "general.bc_1006_2_2_6_")
    return [r for r in rules if r["kind"] == "rule" and r["id"].startswith(keep)]


def _given(group, sprinkler, facts):
    g = {}
    if group == "mixed":
        g.update(occupancy_group="mixed", occupancy_group_i4=False, other_occupancy_present=True)
    elif group is not UNSTATED:
        g.update(occupancy_group=group, occupancy_group_i4=group == "I-4", other_occupancy_present=group != "I-4")
    if SPRINKLERS[sprinkler] is not None:
        g.update(zip(("sprinklered_903_3_1_1", "sprinklered_903_3_1_2", "sprinklered_903_3_1_3"), SPRINKLERS[sprinkler]))
    g.update({k: v for k, v in facts.items() if v is not UNSTATED})
    return g


def _may(v):
    return v is True or v is UNSTATED


# ---- the oracle: the law's tightenings (from the plan's review round 1 table), never the rules ----------------------

def tightened_story(group, sprinkler, facts, travel, in_room):
    """Why no travel row may pass here, or None."""
    if _may(facts["assembly_fixed_seating"]):
        return "1030.7: assembly seating's travel is measured along the aisles, never over the seats"
    if _may(facts["special_egress_spaces"]) and travel > 50:
        return "note a's and 1006.2.2's spaces have their own, shorter distances"
    d13 = sprinkler == "nfpa_13d" or sprinkler is UNSTATED
    if group in ("R-3", "R-4", UNSTATED) and d13 and travel > (125 if group == "R-3" else 75):
        return "1006.2.2.6: Group R-3 125 ft, R-4 75 ft with an NFPA 13D system"
    if _may(facts["building_has_atrium"]) and travel > 200:
        return "1017.3.2.3: 200 ft within an atrium"
    if group in ("I-2", UNSTATED) and in_room > 50:
        return "407.4.2: 50 ft within a Group I-2 sleeping room"
    if group in ("I-3", UNSTATED):
        return "408.6.1: Group I-3's smoke-barrier distances"
    return None


def tightened_space(group, facts, exits, load_, common):
    if _may(facts["assembly_fixed_seating"]) and common > (75 if load_ < 50 else 30):
        return "1030.8: 30 ft from any seat (75 ft under 50 occupants), any group, any number of exits"
    if group in ("M", UNSTATED) and _may(facts["merchandise_pads"]) and common > (75 if load_ <= 50 else 30):
        return "1018.4: 30 ft from any point in a merchandise pad (75 ft for 50 or fewer)"
    if _may(facts["special_egress_spaces"]) and exits < 2:
        return "1006.2.2: boiler, refrigeration and electrical rooms need two exits"
    return None


def _fact_values():
    """Each fact through yes, no and not stated, the others at their loosest (no) and all not stated together."""
    base = {k: False for k in FACTS}
    out = [dict(base), {k: UNSTATED for k in FACTS}]
    for k in FACTS:
        for v in (True, UNSTATED):
            out.append(base | {k: v})
    return out


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(NY)


@pytest.fixture(scope="module")
def rules():
    return load(RULEBOOK)["rules"]


def test_the_walk_varies_every_building_fact_the_drafted_rules_read(rules):
    proposed = set(load(PROPOSED))
    read = set()
    for r in rules:
        for t in [r.get("applies_when"), r.get("check")] + [w["when"] for w in r.get("review_when") or []]:
            if t:
                read |= formula.names(t) & proposed
    walked = set(FACTS) | set(DERIVED)
    assert read - walked == set(), "facts the drafted rules read that the walk doesn't vary"


def test_no_table_row_passes_past_a_tightening_that_applies(ctx, rules):
    scope = _scope(rules)
    story_rules = [r for r in scope if r["for_each"] == "story"]
    space_rules = [r for r in scope if r["for_each"] == "space"]
    bad = []
    for group, sprinkler, facts in itertools.product(GROUPS + ["mixed", UNSTATED], SPRINKLERS, _fact_values()):
        given = _given(group, sprinkler, facts)
        for travel, in_room in itertools.product((49, 51, 74, 76, 124, 126, 199, 201), (40, 51)):
            why = tightened_story(group, sprinkler, facts, travel, in_room)
            if not why:
                continue
            m = {"egress_travel_distance": travel, "egress_travel_in_sleeping_room": in_room}
            for r in story_rules:
                [row] = parts.rows(r, {"story": [{"id": "p", "measures": m}]}, given, ctx.allowed())
                if row["outcome"] == "pass":
                    bad.append((r["id"], group if group is not UNSTATED else "unstated", sprinkler, facts, m, why))
        for exits, load_, common in itertools.product((1, 2), (1, 49, 60), (29, 31, 74, 76, 124)):
            why = tightened_space(group, facts, exits, load_, common)
            if not why:
                continue
            m = {"space_is_exit": False, "space_exit_count": exits, "space_occupant_load": load_,
                 "space_common_path": common}
            for r in space_rules:
                [row] = parts.rows(r, {"space": [{"id": "p", "measures": m}]}, given, ctx.allowed())
                if row["outcome"] == "pass":
                    bad.append((r["id"], group if group is not UNSTATED else "unstated", sprinkler, facts, m, why))
    assert not bad, f"{len(bad)} passes past a tightening, e.g. {bad[:3]}"
