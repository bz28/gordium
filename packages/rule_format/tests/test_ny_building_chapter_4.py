"""New York's Building Code Chapter 4, the sections that change the means of egress
(docs/decisions/2026-11-26_ny_building_chapter_4_egress.md). Part a: covered and open mall buildings (402.1, 402.8)
and atriums (404.1, 404.9 to 404.11), each piece a flag shown only where the building may be that use; and, where
402.8 governs over Chapter 10 (402.8: "the requirements of Sections 402.8.1 through 402.8.8 shall apply"), no
Chapter 10 rule passes on a figure 402.8 changes in a building that may hold a mall. Needs no code cache."""

import json
import random
import re

import pytest

from rule_format import formula, parts
from rule_format.rulebook import REPO, Context, load, outcome

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
RULEBOOK = NY / "5_building_code_rules/drafted/general.yaml"
SECTIONS = NY / "2_extracted_text/gov.ny.building.2025.sections.jsonl"
LABELS = NY / "3_section_labels/gov.ny.building.2025.yaml"
START = "# ---- Chapter 4 (special detailed requirements based on occupancy and use)"
END = "# ---- end of Chapter 4 ----"
GROUPS = ["A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "H-1", "H-2", "H-3", "H-4", "H-5", "I-1", "I-2",
          "I-3", "I-4", "M", "R-1", "R-2", "R-3", "R-4", "S-1", "S-2", "U"]
# the stated fact each part a section's flags turn on: a mall is a space the code gives its own exits or travel limit
# (the fact's own words name "a covered or open mall (402.8)"); an atrium is its own fact
SHOWN_WHERE = {"402": "special_egress_spaces", "404": "building_has_atrium"}


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(NY)


@pytest.fixture(scope="module")
def rules():
    return {r["id"]: r for r in load(RULEBOOK)["rules"]}


def _pieces():
    rows = [json.loads(l) for l in SECTIONS.read_text(encoding="utf-8").splitlines()]
    return {p["id"]: p for p in rows[1:]}


def _chapter_4(pieces, labels, section):
    return [pid for pid in pieces if re.fullmatch(section + r"(\.\d+)+", pid)
            and labels.get(pid, {}).get("label") in ("rule", "flag")]


def _block_ids():
    text = RULEBOOK.read_text(encoding="utf-8")
    assert text.count(START) == 1 and text.count(END) == 1 and text.index(START) < text.index(END)
    block = text[text.index(START):text.index(END)]
    nxt = text[text.index(END):].split("\n- id: ", 2)[1].split("\n", 1)[0]
    assert nxt == "general.bc_508_2_1_classification"     # the block sits just before 508.2.1's rules
    return re.findall(r"\n- id: (\S+)", block)


@pytest.mark.parametrize("section", sorted(SHOWN_WHERE))
def test_each_piece_has_its_flag_shown_only_where_the_building_may_be_that_use(ctx, rules, section):
    """Every piece of the section labeled rule or flag has a flag named for it, in the Chapter 4 block, that quotes
    every line of the piece and turns on the section's fact: shown (needs review) where it is stated yes or not
    stated, not applicable only where the architect states no. Run through the real rule reader, not the examples."""
    pieces, labels = _pieces(), load(LABELS)["labels"]
    block = _block_ids()
    fact = SHOWN_WHERE[section]
    wanted = _chapter_4(pieces, labels, section)
    assert wanted
    for pid in wanted:
        rid = [r for r in block if r.startswith("general.bc_" + pid.replace(".", "_") + "_") and
               not any(r.startswith("general.bc_" + q.replace(".", "_") + "_") for q in wanted
                       if q.startswith(pid + "."))]
        assert len(rid) == 1, (pid, rid)
        rule = rules[rid[0]]
        if pid == "404.1":      # its ban covers every atrium; the fact, only those egress passes through or areas open to
            assert rule["kind"] == "flag" and rule["applies_when"].startswith(fact + " or "), pid
            for group in GROUPS + ["mixed"]:
                want = "needs_review" if group.startswith("H") or group == "mixed" else "not_applicable"
                assert outcome(rule, {fact: False, "occupancy_group": group}, ctx.allowed()) == want, group
            assert outcome(rule, {fact: False}, ctx.allowed()) == "needs_review"
        else:
            assert rule["kind"] == "flag" and rule["applies_when"] == fact, pid
        quoted = {(s["page"], n) for s in rule["sources"] for n in range(s["lines"][0], s["lines"][1] + 1)}
        assert quoted == {(page, n) for page, a, b in pieces[pid]["lines"] for n in range(a, b + 1)}, pid
        for value, want in ((True, "needs_review"), (None, "needs_review"), (False, "not_applicable")):
            given = {} if value is None else {fact: value, "occupancy_group": "B"}
            assert outcome(rule, given, ctx.allowed()) == want, (pid, value)


def test_each_flags_shown_words_hold_wherever_it_needs_review(rules):
    """Review round 2: a flag's needs-review line shows its first needs-review example's note (design_checker egress
    _flag_item), whatever the building states; so that note never says the architect stated something (404.1's once
    said "The building states it has an atrium" where it showed for a Group H building stating none)."""
    for rid in _block_ids():
        shown = next(e["note"] for e in rules[rid]["examples"] if e.get("expect") == "needs_review" and e.get("note"))
        assert not re.search(r"states (it|the|that)|is stated(?! or not)", shown), (rid, shown)


def test_the_block_holds_chapter_4_only_in_book_order(rules):
    block = _block_ids()
    assert block and all(re.match(r"general\.bc_4\d\d_", r) for r in block)
    first = [(rules[r]["sources"][0]["page"], rules[r]["sources"][0]["lines"][0]) for r in block]
    assert first == sorted(first)


# ---- 402.8 over Chapter 10: no pass on a figure 402.8 changes, where a mall is stated or not ruled out -------------
# What 402.8 changes, from its own words (pp.86-87), never from the rules:
# - the mall's occupants come from Equation 4-1 on the gross leasable area (402.8.2.1), not the rooms' functions: so
#   a story's or a corridor's occupant load the model works out from its rooms may be short of the mall's (a mall
#   drawn as a corridor carries none of its own). A pass must stand with that load raised past every limit;
# - a mall taken as a corridor is at least 20 ft (240 in) wide (402.8.1.1), and an exit passageway or corridor from
#   it 66 in (402.8.6): which corridor is the mall isn't in the model, so a corridor's width passes only at 240 in;
# - a dead-end mall is at most twice the mall's narrowest width within the dead end (402.8.6 exception).
# (A space's own load is the code's, 402.8.2: a tenant space by its function, the mall's own function left not
# measured by Table 1004.5, so a space's load is not one 402.8 changes.)
RAISED = ("story_occupant_load", "corridor_occupant_load")
MALL_WIDTH_IN = 240
AFFECTED = set(RAISED) | {"corridor_width", "corridor_dead_end_length"}
GRID = {"story_occupant_load": [0, 5, 10, 29, 30, 49, 50, 100, 300, 500, 501, 1000, 1001, 2000],
        "corridor_occupant_load": [0, 5, 10, 29, 30, 31, 49, 50, 99, 100, 300, 1000],
        "corridor_width": [24, 36, 44, 51.4, 66, 72, 96, 200, 239.9, 240, 300, 2000],
        "corridor_dead_end_length": [0, 5, 10, 19.9, 20, 25, 30, 40, 50, 60, 100],
        "corridor_dead_end_least_width": [3, 5, 6, 8, 10, 20, 30],
        "corridor_fire_rating_hours": [0, 0.5, 1, 2],
        "story_exit_count": [0, 1, 2, 3, 4, 5],
        "egress_travel_distance": [10, 50, 75, 76, 100, 125, 126, 200],
        "story_dwelling_units": [1, 4, 5, 10],
        "exit_remoteness_ratio": [0.2, 0.34, 0.5, 0.7]}
NUMBERS = [0, 1, 10, 50, 100, 500]


def _walked(rules):
    out = []
    for rid, r in rules.items():
        if r.get("kind") != "rule":
            continue
        names = parts.formula_names(r)
        if names & AFFECTED:
            out.append(rid)
    return sorted(out)


@pytest.mark.parametrize("seed", range(4))
def test_no_rule_passes_on_a_figure_402_8_changes_where_a_mall_isnt_ruled_out(ctx, rules, seed):
    """Property, over every drafted rule reading a story's or a corridor's occupant load, a corridor's width or a dead
    end (found from the formulas): with a mall stated or not ruled out, a pass stands with the story's and corridor's
    load raised far past every limit, only at a corridor width of 240 in or more, and only with a dead end at most
    twice its least width. Every group, a building of two or more and one not stated; every sprinkler setting; every
    other fact the rule reads yes, no or not stated; measures from a grid around each printed limit."""
    walked = _walked(rules)
    assert len(walked) >= 10, walked
    allowed = ctx.allowed()
    rng = random.Random(seed)
    passes = {rid: 0 for rid in walked}
    bad = []
    for rid in walked:
        rule = rules[rid]
        kind = rule.get("for_each")
        own = parts.measure_kinds(kind) if kind else {}
        names = parts.formula_names(rule)
        for _ in range(1500):
            given = {}
            group = rng.choice(GROUPS + ["mixed", None])
            if group is not None:
                given.update(occupancy_group=group, occupancy_group_i4=group == "I-4",
                             other_occupancy_present=group != "I-4")
            sprinkler = rng.choice([(True, False, False), (False, True, False), (False, False, True),
                                    (False, False, False), None])
            if sprinkler:
                given.update(zip(("sprinklered_903_3_1_1", "sprinklered_903_3_1_2", "sprinklered_903_3_1_3"), sprinkler))
            for n in names:
                if n in own or n in given or n == "special_egress_spaces":
                    continue
                if allowed.get(n) == "boolean":
                    v = rng.choice([True, False, None])
                    if v is not None:
                        given[n] = v
            if rng.random() < 0.5:
                given["special_egress_spaces"] = True
            m = {}
            for n in names & set(own):
                if own[n] == "boolean":
                    v = rng.choice([True, False, None])
                    if v is not None:
                        m[n] = v
                else:
                    m[n] = rng.choice(GRID.get(n, NUMBERS))
            [row] = parts.rows(rule, {kind: [{"id": "p1", "measures": m}]}, given, allowed)
            if row["outcome"] != "pass":
                continue
            passes[rid] += 1
            raised = {**m, **{n: 10 ** 6 for n in RAISED if n in names}}
            [again] = parts.rows(rule, {kind: [{"id": "p1", "measures": raised}]}, given, allowed)
            why = []
            if again["outcome"] != "pass":
                why.append("passes only on the load the rooms give")
            if "corridor_width" in names and not (m.get("corridor_width", 0) >= MALL_WIDTH_IN):
                why.append("passes a corridor narrower than a mall's 240 in")
            if "corridor_dead_end_length" in names and m.get("corridor_dead_end_length", 0) > 0 and \
                    not m["corridor_dead_end_length"] <= 2 * m.get("corridor_dead_end_least_width", 0):
                why.append("passes a dead end longer than twice its least width")
            if why:
                bad.append((rid, given, m, why))
    by_rule = {}
    for rid, _, _, why in bad:
        by_rule.setdefault(rid, set()).update(why)
    assert not bad, (by_rule, bad[:3])
    # the walk isn't vacuous: every walked rule passes somewhere with a mall not ruled out (four exits or more, a
    # corridor of 240 in or more, no dead end, a rated or sprinklered corridor...), but the corridor's capacity, which
    # no width passes at every load (review round 1)
    assert {rid for rid, n in passes.items() if n == 0} <= {"general.bc_1020_3_corridor_capacity"}, passes
