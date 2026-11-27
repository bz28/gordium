"""New York's Building Code Chapter 4, the sections that change the means of egress
(docs/decisions/2026-11-26_ny_building_chapter_4_egress.md). Part a: covered and open mall buildings (402.1, 402.8)
and atriums (404.1, 404.9 to 404.11), each piece a flag shown only where the building may be that use; and, where
402.8 governs over Chapter 10 (402.8: "the requirements of Sections 402.8.1 through 402.8.8 shall apply"), no
Chapter 10 rule passes on a figure 402.8 changes in a building that may hold a mall. Needs no code cache."""

import ast
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
SHOWN_WHERE = {"402": "special_egress_spaces", "404": "building_has_atrium",
               # part b: a high-rise (202) or a building over 420 ft (403.2.2, 403.5.2); an underground building (405.1)
               "403": "high_rise_building", "405": "underground_building"}


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


# part c: a section for one occupancy group, its flags shown where the building is stated that group, two or more
# groups, or none (a building stated one other group: not applicable)
GROUP_GATED = {"407": ["I-2"]}
# pieces a rule outside the Chapter 4 block already checks (Chapter 10's review round 1 brought them in alone)
CHECKED_BEFORE = {"407.4.2": "general.bc_407_4_2_sleeping_room_travel"}


@pytest.mark.parametrize("section", sorted(GROUP_GATED))
def test_each_piece_of_a_groups_section_has_its_flag_shown_only_for_that_group(ctx, rules, section):
    pieces, labels = _pieces(), load(LABELS)["labels"]
    block = _block_ids()
    groups = GROUP_GATED[section]
    wanted = [pid for pid in _chapter_4(pieces, labels, section) if pid not in CHECKED_BEFORE]
    assert wanted and all(rid in rules for rid in CHECKED_BEFORE.values())
    for pid in wanted:
        rid = [r for r in block if r.startswith("general.bc_" + pid.replace(".", "_") + "_") and
               not any(r.startswith("general.bc_" + q.replace(".", "_") + "_") for q in wanted if q.startswith(pid + "."))]
        assert len(rid) == 1, (pid, rid)
        rule = rules[rid[0]]
        gate = "occupancy_group in " + str(groups + ["mixed"]).replace("'", '"')
        assert rule["kind"] == "flag" and rule["applies_when"] == gate, pid
        quoted = {(s["page"], n) for s in rule["sources"] for n in range(s["lines"][0], s["lines"][1] + 1)}
        assert quoted == {(page, n) for page, a, b in pieces[pid]["lines"] for n in range(a, b + 1)}, pid
        for group in GROUPS + ["mixed", None]:
            given = {} if group is None else {"occupancy_group": group}
            want = "needs_review" if group in groups + ["mixed", None] else "not_applicable"
            assert outcome(rule, given, ctx.allowed()) == want, (pid, group)


def test_each_flags_shown_words_hold_wherever_it_needs_review(rules):
    """Review round 2: a flag's needs-review line shows its first needs-review example's note (design_checker egress
    _flag_item), whatever the building states; so that note never says the architect stated something (404.1's once
    said "The building states it has an atrium" where it showed for a Group H building stating none)."""
    for rid in _block_ids():
        shown = next(e["note"] for e in rules[rid]["examples"] if e.get("expect") == "needs_review" and e.get("note"))
        assert not re.search(r"states (it|the|that)|is stated(?! or not)", shown), (rid, shown)


def test_what_404_1_shows_by_is_said_where_people_read_it():
    """Review round 3: 404.1's flag shows by the group as well as the atrium fact; its label's reason and the README
    say so, not the atrium fact alone."""
    reason = load(LABELS)["labels"]["404.1"]["reason"]
    readme = (NY / "README.md").read_text(encoding="utf-8")
    assert "Group H (H-1 to H-5" in reason and "404.1's also in any building that may be Group H" in readme


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


# ---- part b: 403.5.2's additional stairway and 405.7.1's two exits on each floor level -------------------------------
# From the law's words (pp.90, 93), never from the rules: a building other than Group R-2 more than 420 ft in building
# height has one interior exit stairway more than 1006.3 asks (403.5.2); each floor level of an underground building has
# at least two exits (405.7.1). Neither the height nor which floors are underground is in the model, so with the stated
# fact yes or not stated a story exit rule passes only past both.
def _required(load_):
    """Table 1006.3.3 (p.316): 2 exits for 1 to 500 occupants, 3 for 501 to 1,000, 4 for more."""
    return 2 if load_ <= 500 else 3 if load_ <= 1000 else 4


@pytest.mark.parametrize("seed", range(2))
def test_no_story_passes_short_of_403_5_2_or_405_7_1_where_they_may_apply(ctx, rules, seed):
    """Property over every drafted rule reading a story's exit count (found from the formulas): every group, a
    building of two or more and one not stated, every sprinkler setting, every other fact yes, no or not stated, the
    story's measures from a grid: where a high-rise isn't ruled out and the building isn't stated Group R-2, a pass has
    one exit more than Table 1006.3.3 asks; where an underground building isn't ruled out, a pass has two exits."""
    # the rules that hold a story to a number of exits: their check compares its exit count with Table 1006.3.3's
    # (1007.1.1's separation reads the count only to know whether two are required, and asks nothing of it)
    walked = sorted(rid for rid, r in rules.items() if r.get("kind") == "rule" and r.get("for_each") == "story"
                    and any(isinstance(n, ast.Compare) and "story_exit_count" in ast.unparse(n.left)
                            and isinstance(n.ops[0], (ast.GtE, ast.Gt))
                            for n in ast.walk(formula.parse(r["check"]))))
    assert walked == sorted(["general.bc_1006_3_3_story_exits", "general.bc_table_1006_3_4_1__r2_dwelling_units",
                             "general.bc_table_1006_3_4_2__a_b_e_f_m_u", "general.bc_table_1006_3_4_2__h_i_r",
                             "general.bc_table_1006_3_4_2__s"]), walked
    allowed = ctx.allowed()
    rng = random.Random(seed)
    own = parts.measure_kinds("story")
    bad = []
    for rid in walked:
        rule = rules[rid]
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
                if n not in own and n not in given and allowed.get(n) == "boolean":
                    v = rng.choice([True, False, None])
                    if v is not None:
                        given[n] = v
            m = {}
            for n in names & set(own):
                if own[n] == "boolean":
                    v = rng.choice([True, False, None])
                    if v is not None:
                        m[n] = v
                else:
                    m[n] = rng.choice(GRID.get(n, NUMBERS))
            [row] = parts.rows(rule, {"story": [{"id": "p1", "measures": m}]}, given, allowed)
            if row["outcome"] != "pass":
                continue
            count, load_ = m.get("story_exit_count"), m.get("story_occupant_load")
            if given.get("high_rise_building", None) is not False and group != "R-2" and \
                    not (count is not None and load_ is not None and count >= _required(load_) + 1):
                bad.append((rid, "403.5.2", given, m))
            if given.get("underground_building", None) is not False and not (count is not None and count >= 2):
                bad.append((rid, "405.7.1", given, m))
    assert not bad, (sorted({(b[0], b[1]) for b in bad}), bad[:3])
