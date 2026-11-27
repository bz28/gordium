"""A property walk over every drafted Chapter 10 rule of New York's Building Code that reads a measure the law
tightens (review rounds 2 to 5, 2026-11-23: docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md).

Scope, worked out, never listed: every drafted rule whose formulas read a story's travel, a space's common path or a
Group I-2 sleeping room's own travel (AFFECTED). A walked rule that never applies in any case fails, so a rule can't
drop out of the walk unnoticed.

Settings: every occupancy group (A-1 to U, a building of two or more groups, and one whose group isn't stated, one
test each), each sprinkler system or none stated, and each building fact yes, no or not stated. For each rule the
settings are first collapsed to the distinct values of the facts that rule reads (and the tightened limits on the
measures it reads), so a rule is run once per setting that can change its answer.

Property: a pass never rests on the affected measure. Where a tightening applies (its fact yes or not stated) and the
measure is past the tightened limit (0 where the law doesn't trust the routes' figure at all), the rule must still
pass with the measure raised far past every limit; else it passed on a figure the law doesn't trust or on a looser
limit. The tightened limits are written from the law's own list of what tightens the tables (the plan's review round
1 table), never from the rules. Completeness is checked too: the facts the walk varies are exactly the building facts
the drafted rules read."""

import ast
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
# the building facts the walk varies (each yes, no, not stated), beside the group and the sprinkler system
FACTS = ("assembly_fixed_seating", "special_egress_spaces", "merchandise_pads", "building_has_atrium",
         "egress_balcony_increase_taken", "r2_sleeping_units", "emergency_escape_openings_1031",
         "occupied_outdoor_areas", "ambulatory_care_facility", "corridors_within_dwelling_units",
         "emergency_voice_alarm_system", "high_rise_building", "underground_building", "stages_or_platforms",
         "aircraft_related_occupancy")   # the last: Table 1020.3's (the corridor walk's,
# test_ny_building_corridor_walk.py, which varies it with every width and load; here for completeness)
DERIVED = ("occupancy_group", "occupancy_group_i4", "other_occupancy_present", "sprinklered_903_3_1_1",
           "sprinklered_903_3_1_2", "sprinklered_903_3_1_3")


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


# The measures a tightening makes unreliable or holds to a shorter limit; every drafted rule reading one is walked
AFFECTED = ("egress_travel_distance", "space_common_path", "egress_travel_in_sleeping_room")
FAR = 10_000


def _reads(r):
    out = set()
    for t in [r.get("applies_when"), r.get("check")] + [w["when"] for w in r.get("review_when") or []]:
        if t:
            out |= formula.names(t)
    return out


def walked_rules(rules):
    """Every drafted rule whose formulas read a measure a tightening affects: worked out, never listed by hand."""
    return [r for r in rules if r["kind"] == "rule" and _reads(r) & set(AFFECTED)]


def story_limits(group, sprinkler, facts):
    """The tightened limit on each story measure where a tightening applies (0: the figure can't be trusted)."""
    travel = []
    if _may(facts["assembly_fixed_seating"]):
        travel.append(0)            # 202, 1030.7: measured along the aisles, never over the seats
    if group in ("I-3", UNSTATED):
        travel.append(0)            # 408.6.1: smoke-barrier distances, not measured
    if _may(facts["special_egress_spaces"]):
        travel.append(50)           # note a's and 1006.2.2's spaces: their own distances, the shortest 50 ft
    d13 = sprinkler == "nfpa_13d" or sprinkler is UNSTATED
    if group in ("R-3", UNSTATED) and d13:
        travel.append(125)          # 1006.2.2.6
    if group in ("R-4", UNSTATED) and d13:
        travel.append(75)
    if _may(facts["building_has_atrium"]):
        travel.append(200)          # 1017.3.2.3
    out = {"egress_travel_distance": min(travel)} if travel else {}
    if group in ("I-2", UNSTATED):
        out["egress_travel_in_sleeping_room"] = 50                  # 407.4.2
    return out


def space_limits(group, facts, load_):
    cp = []
    if _may(facts["assembly_fixed_seating"]):
        cp.append(0)                # 202, 1030.7, 1030.8: a fixed-seat room's path is along its aisles
    if group in ("M", UNSTATED) and _may(facts["merchandise_pads"]):
        cp.append(75 if load_ <= 50 else 30)                        # 1018.4
    return {"space_common_path": min(cp)} if cp else {}


_SEEN = {}
_READS = {}


def _outcome(r, kind, m, given, ctx):
    """A rule's row, worked out once for each set of the values it reads (the walk's cases repeat them)."""
    reads = _READS.get(r["id"])
    if reads is None:
        reads = _READS[r["id"]] = _reads(r)
    key = (r["id"], tuple((k, given.get(k, UNSTATED), m.get(k, UNSTATED)) for k in sorted(reads)))
    if key not in _SEEN:
        _SEEN[key] = parts.rows(r, {kind: [{"id": "p", "measures": m}]}, given, ctx.allowed())[0]["outcome"]
    return _SEEN[key]


STORY_CASES = [dict(egress_travel_distance=t, egress_travel_in_sleeping_room=i, story_exit_count=x,
                    story_occupant_load=n, story_first_above_or_below_grade=f, story_second_above_grade_plane=False,
                    story_fourth_or_higher_above_grade_plane=False, story_rooms_exit_directly_outside=False,
                    story_dwelling_units=2, exit_remoteness_ratio=0.9, story_assembly_seating_possible=s)
               for t, i, x, n, f, s in itertools.product((51, 76, 126, 201), (51,), (1, 2), (5, 40), (True, False),
                                                         (True, False))]
SPACE_CASES = [dict(space_is_exit=False, space_exit_count=x, space_occupant_load=n, space_common_path=c,
                    space_exit_remoteness_ratio=0.9, space_assembly_seating_possible=s)
               for x, n, c, s in itertools.product((1, 2), (5, 40, 60), (31, 76, 126), (True, False))]
# a room on the story may seat people served by aisles, fixed seats or not (the routes' story and space parts,
# design_checker/occupant_load.py assembly_seating): 1030.7 (p.354, lines 50-51) measures travel "along the aisles and
# aisle accessways without travel over or on the seats" wherever aisles are provided for seating, and the common path
# is a portion of exit access travel (202), so neither figure can be trusted there
SEATING = {"story": ("story_assembly_seating_possible", "egress_travel_distance"),
           "space": ("space_assembly_seating_possible", "space_common_path")}


WHERE = GROUPS + ["mixed", "unstated"]          # one test each, so the parts of the suite spread them
SETTINGS = list(itertools.product(SPRINKLERS, _fact_values()))
LOADS = sorted({m["space_occupant_load"] for m in SPACE_CASES})


def _group(where):
    return UNSTATED if where == "unstated" else where


def _distinct(r, group, keep=None):
    """One group's settings for one rule, collapsed to the distinct values of the facts the rule reads and of the
    tightened limits on the measures it reads: [(given, limits, sprinkler, facts)], limits by occupant load for a
    space (1018.4's limit turns on it). `keep` picks the settings first (by their facts)."""
    reads = _reads(r)
    out = {}
    for sprinkler, facts in SETTINGS:
        if keep and not keep(facts):
            continue
        given = _given(group, sprinkler, facts)
        if r["for_each"] == "story":
            lim = story_limits(group, sprinkler, facts)
            sig = tuple(sorted((k, v) for k, v in lim.items() if k in reads))
        else:
            lim = {n: space_limits(group, facts, n) for n in LOADS}
            sig = tuple((n, tuple(sorted((k, v) for k, v in lim[n].items() if k in reads))) for n in LOADS)
        out.setdefault((tuple((k, given.get(k, UNSTATED)) for k in sorted(reads)), sig), (given, lim, sprinkler, facts))
    return list(out.values())


def _cases(r):
    return STORY_CASES if r["for_each"] == "story" else SPACE_CASES


def _limits(r, lim, m):
    out = dict(lim if r["for_each"] == "story" else lim[m["space_occupant_load"]])
    seating, measure = SEATING[r["for_each"]]
    if m.get(seating):
        out[measure] = 0
    return out


def test_the_walk_covers_every_walked_rule_and_each_applies_somewhere(ctx, rules):
    """Each walked rule is a story or space rule (the parts the walk builds) and applies in at least one case."""
    walked = walked_rules(rules)
    assert walked and {r["for_each"] for r in walked} <= {"story", "space"}
    never = [r["id"] for r in walked
             if not any(_outcome(r, r["for_each"], m, given, ctx) != "not_applicable"
                        for where in WHERE[::-1] for given, *_ in _distinct(r, _group(where)) for m in _cases(r))]
    assert never == [], "walked rules that never applied in any case"


@pytest.mark.parametrize("where", WHERE)
def test_no_pass_rests_on_a_measure_a_tightening_makes_unreliable_or_shorter(ctx, rules, where):
    """For every walked rule, every setting of this group and each story or space case: where a tightening applies
    and the measure is past its tightened limit, a pass must not depend on the measure (raised far past every limit,
    the rule still passes); else the rule rests on a figure the law doesn't trust or a looser limit."""
    group = _group(where)
    bad = []
    for r in walked_rules(rules):
        kind, reads = r["for_each"], _reads(r)
        for given, lim, sprinkler, facts in _distinct(r, group):
            for m in _cases(r):
                past = [n for n, v in _limits(r, lim, m).items() if n in reads and m[n] > v]
                if not past or _outcome(r, kind, m, given, ctx) != "pass":
                    continue
                for name in past:
                    if _outcome(r, kind, m | {name: FAR}, given, ctx) != "pass":
                        bad.append((r["id"], where, sprinkler if sprinkler is not UNSTATED else "unstated",
                                    {k: "unstated" if v is UNSTATED else v for k, v in facts.items() if v is not False},
                                    name, m[name], _limits(r, lim, m)[name]))
    assert not bad, f"{len(bad)} passes resting on a tightened measure, e.g. {bad[:3]}"


def _needs_two_exits(text):
    """The check compares the space's exit count against 2 (`space_exit_count >= 2`), found in its parsed formula."""
    return any(isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) and n.left.id == "space_exit_count"
               and len(n.ops) == 1 and isinstance(n.ops[0], ast.GtE) and isinstance(n.comparators[0], ast.Constant)
               and n.comparators[0].value == 2 for n in ast.walk(formula.parse(text)))


def _two_exit_rows(rules):
    return [r for r in rules if r["kind"] == "rule" and r.get("check") and _needs_two_exits(r["check"])]


def test_the_one_exit_walk_finds_every_table_1006_2_1_row_and_no_other_rule(rules):
    """The rows are Table 1006.2.1's (one per group's row) and Group I-4's own two-exit rule, and no others."""
    expected = {r["id"] for r in rules if r["kind"] == "rule" and r["id"].startswith("general.bc_table_1006_2_1_")}
    assert len(expected) >= 12
    assert {r["id"] for r in _two_exit_rows(rules)} == expected | {"general.bc_1006_2_1_two_exits"}


@pytest.mark.parametrize("where", WHERE)
def test_no_table_1006_2_1_row_passes_a_one_exit_space_a_1006_2_2_room_may_be(ctx, rules, where):
    """1006.2.2's rooms need two exits by their use: with such a room stated or not ruled out, no row that decides a
    space's second exit (its check compares the exit count against 2) passes a one-exit space."""
    bad = []
    for r in _two_exit_rows(rules):
        for given, *_ in _distinct(r, _group(where), keep=lambda f: _may(f["special_egress_spaces"])):
            bad += [r["id"] for m in SPACE_CASES
                    if m["space_exit_count"] < 2 and _outcome(r, "space", m, given, ctx) == "pass"]
    assert not bad, bad[:5]
