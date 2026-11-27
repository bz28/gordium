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
               "403": "high_rise_building", "405": "underground_building",
               # part e: an ambulatory care facility, the fact Section 422, Table 1020.2 and 1020.3 read
               "422": "ambulatory_care_facility",
               # part f: a stage, a platform or a technical production area (410.5); a special amusement area, a space
               # the code gives its own exits or travel limit (the fact's words name it: 411); an aircraft-related
               # occupancy (412's means of egress, Table 412.6 with them)
               "410": "stages_or_platforms", "411": "special_egress_spaces", "412": "aircraft_related_occupancy"}


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
    """The section's pieces labeled rule or flag, its tables too (part f: Table 412.6 under 412.6)."""
    return [pid for pid in pieces if re.fullmatch(r"(?:Table )?" + re.escape(section) +
                                                  (r"(\.\d+)+" if "." not in section else r"(\.\d+)*"), pid)
            and labels.get(pid, {}).get("label") in ("rule", "flag")]


def _prefix(pid):
    """The id prefix of a piece's rule: general.bc_412_6_ for 412.6, general.bc_table_412_6_ for Table 412.6."""
    return "general.bc_" + pid.replace("Table ", "table_").replace(".", "_") + "_"


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
        rid = [r for r in block if r.startswith(_prefix(pid)) and
               not any(r.startswith(_prefix(q)) for q in wanted if q.startswith(pid + "."))]
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
GROUP_GATED = {"407": ["I-2"], "408": ["I-3"],
               # part e: 420's own scope and separations for Groups I-1 and R, its smoke barriers, housing units and
               # cooking for Group I-1 alone
               "420.1": ["I-1", "R-1", "R-2", "R-3", "R-4"], "420.2": ["I-1", "R-1", "R-2", "R-3", "R-4"],
               "420.3": ["I-1", "R-1", "R-2", "R-3", "R-4"], "420.6": ["I-1"], "420.7": ["I-1"], "420.8": ["I-1"],
               "420.9": ["I-1"],
               # part f: public parking garages are Group S-2 (311.3), and a private garage, Group U (406.3.1), may
               # comply with 406.4 in place of 406.3, an open one then with 406.5 (406.3, p.94, lines 49-50; review
               # round 1); HPM rooms are H-2, H-3 or H-4 serving an H-5, liquid storage rooms H-3 (202)
               "406.4.3": ["S-2", "U"], "406.5.7": ["S-2", "U"], "415.11.6": ["H-2", "H-3", "H-4", "H-5"]}
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
        rid = [r for r in block if r.startswith(_prefix(pid)) and
               not any(r.startswith(_prefix(q)) for q in wanted if q.startswith(pid + "."))]
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


def test_a_service_corridors_flags_show_where_the_building_may_be_group_h5_and_may_have_one(ctx, rules):
    """Part f: 415.11.3.3's and 415.11.3.4's flags, for a service corridor within a Group H-5 occupancy (415.11.3),
    show where the building may be Group H-5 (stated, two or more groups, or not stated) and doesn't state it has no
    service corridor: every group, each yes, no or not stated."""
    pieces, labels = _pieces(), load(LABELS)["labels"]
    block = _block_ids()
    wanted = _chapter_4(pieces, labels, "415.11.3")
    assert wanted == ["415.11.3.3", "415.11.3.4"]
    for pid in wanted:
        [rid] = [r for r in block if r.startswith(_prefix(pid))]
        rule = rules[rid]
        assert rule["kind"] == "flag" and rule["applies_when"] == 'occupancy_group in ["H-5", "mixed"] and service_corridors'
        quoted = {(s["page"], n) for s in rule["sources"] for n in range(s["lines"][0], s["lines"][1] + 1)}
        assert quoted == {(page, n) for page, a, b in pieces[pid]["lines"] for n in range(a, b + 1)}, pid
        for group in GROUPS + ["mixed", None]:
            for corridors in (True, False, None):
                given = {} if group is None else {"occupancy_group": group}
                if corridors is not None:
                    given["service_corridors"] = corridors
                may = group in ("H-5", "mixed", None) and corridors is not False
                assert outcome(rule, given, ctx.allowed()) == ("needs_review" if may else "not_applicable"), (
                    pid, group, corridors)


def test_each_flags_shown_words_hold_wherever_it_needs_review(rules):
    """Review round 2: a flag's needs-review line shows its first needs-review example's note (design_checker egress
    _flag_item), whatever the building states; so that note never says the architect stated something (404.1's once
    said "The building states it has an atrium" where it showed for a Group H building stating none)."""
    for rid in _block_ids():
        shown = next(e["note"] for e in rules[rid]["examples"] if e.get("expect") == "needs_review" and e.get("note"))
        assert not re.search(r"\bstates (it|the|that)\b|\bis stated\b(?! or not)", shown), (rid, shown)
    # the pattern itself catches the words round 2 found (a pattern that can't match pins nothing: found in part c)
    assert re.search(r"\bstates (it|the|that)\b|\bis stated\b(?! or not)", "The building states it has an atrium: Sections 404.1 to 404.11 apply")


def test_what_404_1_shows_by_is_said_where_people_read_it():
    """Review round 3: 404.1's flag shows by the group as well as the atrium fact; its label's reason and the README
    say so, not the atrium fact alone."""
    reason = load(LABELS)["labels"]["404.1"]["reason"]
    readme = (NY / "README.md").read_text(encoding="utf-8")
    assert "Group H (H-1 to H-5" in reason and "404.1's also in any building that may be Group H" in readme


def test_the_block_holds_chapter_4_only_in_book_order(rules):
    block = _block_ids()
    assert block and all(re.match(r"general\.bc_(table_)?4\d\d_", r) for r in block)
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


@pytest.mark.parametrize("mall", [True, None])
def test_a_story_with_more_exits_than_any_reading_asks_passes_with_the_facts_not_stated(ctx, rules, mall):
    """Review round 1 of part b: a band whose bound was `(4 + 1 if ... high_rise_building else 4)` stopped on an
    unstated high-rise (a conditional on an unknown fact is never three-valued), so a story with six exits needed
    review in a building that may hold a mall. More exits than any reading asks (Table 1006.3.3's four, 402.8's four,
    403.5.2's one more) pass whatever the mall, high-rise and underground facts are."""
    story = {"story_exit_count": 6, "story_occupant_load": 100, "egress_travel_distance": 50,
             "story_first_above_or_below_grade": True, "story_rooms_exit_directly_outside": False,
             "story_second_above_grade_plane": False, "story_fourth_or_higher_above_grade_plane": False,
             "story_dwelling_units": 1}
    plain = {"sprinklered_903_3_1_1": True, "sprinklered_903_3_1_2": False, "sprinklered_903_3_1_3": False,
             "assembly_fixed_seating": False, "emergency_escape_openings_1031": True}
    if mall is not None:
        plain["special_egress_spaces"] = mall
    cases = {"general.bc_1006_3_3_story_exits": {"occupancy_group": "I-4", "occupancy_group_i4": True,
                                                 "other_occupancy_present": False},
             "general.bc_table_1006_3_4_2__a_b_e_f_m_u": {"occupancy_group": "B"},
             "general.bc_table_1006_3_4_2__h_i_r": {"occupancy_group": "R-1"},
             "general.bc_table_1006_3_4_2__s": {"occupancy_group": "S-1"},
             "general.bc_table_1006_3_4_1__r2_dwelling_units": {"occupancy_group": "R-2", "r2_sleeping_units": False}}
    for rid, group in cases.items():
        [row] = parts.rows(rules[rid], {"story": [{"id": "p1", "measures": story}]}, {**plain, **group}, ctx.allowed())
        assert row["outcome"] == "pass", (rid, row)


def _said_not_brought_in(text):
    """Each stretch of a text that calls something not brought in: its sentence from the start through the end of the
    clause (between ";" or ":") holding the words, so a list before them counts ("a mall, a Group I-2 occupancy ...:
    each has its own distance, not brought in"; "Covered malls (402.8); atriums are not brought in") and a clause
    after them doesn't ("1014.9 (not brought in) is a person's check; Group I-2 ... per 407.4.3 (a flag) too")."""
    for sentence in re.split(r"(?<=\.)\s", text):
        clauses = list(re.finditer(r"[^;:]+(?:[;:]|$)", sentence))
        for n, clause in enumerate(clauses):
            if re.search(r"(?:not|n't|neither|nor) brought in", clause.group()):
                # a list the words open with a colon is theirs too ("not brought in: covered malls (402.8) and ...")
                end = clauses[n + 1].end() if clause.group().endswith(":") and n + 1 < len(clauses) else clause.end()
                yield sentence[:end]


def test_a_stretch_said_not_brought_in_runs_from_its_sentence_start_to_its_clause_end():
    assert list(_said_not_brought_in("Covered malls (402.8); atriums are not brought in.")) == [
        "Covered malls (402.8); atriums are not brought in."]
    [got] = _said_not_brought_in("Handrails as 1014.9 allows (not brought in) are a check; Group I-2 per 407.4.3 too.")
    assert "407.4.3" not in got and "Group I-2" not in got and "1014.9" in got
    # review round 5: the list a colon opens after the words
    [got] = _said_not_brought_in("Two uses are not brought in: covered malls (402.8) and Group I-2 occupancies.")
    assert "402.8" in got and _named_uses(got) == {"402.8", "407.4"}


def test_no_rule_text_says_a_brought_in_chapter_4_section_is_not_brought_in(rules):
    """Review round 1 of part c: Chapter 10's words still said 407.4 "aren't brought in" (the shared stale-words test
    reads only "not brought in" in a narrow pattern). No sentence of any rule's title, notes, review reasons or
    example notes, nor any label's reason, names a Chapter 4 section sources.yaml brings in (or a part under one, or
    the whole section a part is brought in from: "Section 420" once 420.2 is in, review round 1 of part e) and calls
    it not brought in."""
    brought = load(NY / "1_source_documents/sources.yaml")["documents"][0]["brought_in"]
    ours = [str(s) for s in brought["sections"] + brought["alone"] if re.fullmatch(r"4\d\d(\.\d+)*", str(s))]
    assert ours
    texts = []
    for r in rules.values():
        texts += [(r["id"], x) for x in [r.get("title"), r.get("notes")] + [w.get("reason") for w in
                  r.get("review_when") or []] + [e.get("note") for e in r.get("examples") or []] if isinstance(x, str)]
    for path in sorted((NY / "3_section_labels").glob("*.yaml")):
        labels = load(path)["labels"]
        assert isinstance(labels, dict) and labels, path
        texts += [(f"label {pid}", e["reason"]) for pid, e in labels.items()
                  if isinstance(e, dict) and isinstance(e.get("reason"), str)]
    bad = []
    for where, text in texts:
        # review rounds 2 to 5 of part c: a section named by its number or by its use ("a mall, a Group I-2
        # occupancy ...: each has its own distance, not brought in"), anywhere in the stretch said not brought in
        for stretch in _said_not_brought_in(text):
            named = re.findall(r"\b(4\d\d(?:\.\d+)+)\b", stretch) + re.findall(r"\bSection (4\d\d)\b", stretch)
            bad += [(where, n) for n in named + sorted(_named_uses(stretch))
                    if any(n == s or n.startswith(s + ".") or s.startswith(n + ".") for s in ours)]
    assert not bad, bad


# the sections part e brings in only in part, whose left-out parts the README lists (review rounds 1 and 2 of part e)
PARTLY_IN = ("420", "422")


def test_the_readmes_list_names_every_section_a_brought_in_piece_sends_to_that_isnt_in():
    """Review round 1 of part e: 420.1 sends to "Sections 420.1 through 420.11" and 422.1 to 422.1 through 422.7, and
    the README says which parts of Sections 420 and 422 part e leaves out; each section of those ranges that isn't
    brought in (nor under one that is) is in that list. (The other parts' scope sections send to ranges whose
    remaining sections no rule meets, and the README lists none of them.)"""
    brought = load(NY / "1_source_documents/sources.yaml")["documents"][0]["brought_in"]
    ours = [str(s) for s in brought["sections"] + brought["alone"]]
    readme = (NY / "README.md").read_text(encoding="utf-8")
    missing = []
    for rid in _block_ids():
        for src in _rules_by_id()[rid].get("sources") or []:
            for a, b in re.findall(r"Sections (4\d\d\.\d+) through (4\d\d\.\d+)", " ".join(src["quote"].split())):
                head = a.rsplit(".", 1)[0]
                if head != b.rsplit(".", 1)[0] or head not in PARTLY_IN:
                    continue
                for n in range(int(a.rsplit(".", 1)[1]), int(b.rsplit(".", 1)[1]) + 1):
                    s = f"{head}.{n}"
                    if not any(s == o or s.startswith(o + ".") for o in ours) and not _readme_names(readme, s):
                        missing.append((rid, s))
    assert not missing, sorted(set(missing))


def _readme_names(readme, section):
    """Whether the README names a section: by itself, or inside a range it prints ("422.4 to 422.7")."""
    if re.search(r"(?<![\d.])" + re.escape(section) + r"(?![\d])", readme):
        return True
    head, n = section.rsplit(".", 1)
    return any(int(lo) <= int(n) <= int(hi) for lo, hi in
               re.findall(r"(?<![\d.])" + re.escape(head) + r"\.(\d+) to " + re.escape(head) + r"\.(\d+)(?![\d])", readme))


def _rules_by_id():
    return {r["id"]: r for r in load(RULEBOOK)["rules"]}


def test_a_plural_term_is_the_definition_of_its_singular():
    """Review round 1 of part c: 201.2 makes the singular include the plural (p.32, lines 13-14), so "nursing home" in
    italics is NURSING HOMES and "life safety system" LIFE SAFETY SYSTEMS: both brought in (by name, the italics
    reader matching words only as printed), labeled, read a second time; and no reason given for an italic word left
    undefined argues that a plural term doesn't name its singular."""
    pieces, labels = _pieces(), load(LABELS)["labels"]
    for pid in ("202:nursing_homes", "202:life_safety_systems"):
        assert pid in pieces and labels[pid]["label"] == "reference", pid
    why = load(NY / "1_source_documents/sources.yaml")["documents"][0]["brought_in"]["italic_not_defined"]
    said = [(pid, w, t) for pid, words in why.items() for w, t in words.items()
            if re.search(r"plural, which the singular|singular, which the plural", t)]
    assert not said, said


VALUE = r"(?<![\d.,/])(\d+[ -]\d+/\d+|\d+/\d+|[\d,]*\.\d+|[\d,]+)"
# every unit the number reader (document_extraction/numbers.py) records that is imperial, and the metric ones
IMPERIAL = ("gross square foot", "net square foot", "square foot", "square inch", "cubic foot", "foot", "inch", "pound",
            "psf", "footcandle")
METRIC = ("mm", "cm", "m", "kg", "N", "lux")


def _figure(recorded):
    """(value, unit) of a recorded number ("less than 500 square foot", "19.1 mm", "1 1/2 inch", ".5 inch"), or None."""
    m = re.search(VALUE + r"\s+(" + "|".join(IMPERIAL + METRIC) + r")\b", recorded)
    if not m:
        return None
    whole, _, frac = m.group(1).replace(",", "").replace("-", " ").rpartition(" ") if "/" in m.group(1) \
        else ("", "", m.group(1).replace(",", ""))
    a, _, b = frac.partition("/")
    return (float(whole or 0) + (float(a) / float(b) if b else float(a))), m.group(2)


def _imperial(recorded):
    """Whether a recorded number carries an imperial unit word (whether or not _figure reads it)."""
    return re.search(r"\d\s+(?:gross\s+|net\s+)?(?:square\s+|cubic\s+)?(?:inch|foot|pound|psf|footcandle)\b", recorded)


def _metric(recorded):
    """Whether a recorded number carries a metric unit word."""
    return re.search(r"\d\s+(?:" + "|".join(METRIC) + r")\b", recorded)


# each imperial unit and the conversions it is printed with (square metres are recorded as "m", square mm as "mm")
CONVERSION = {"inch": {"mm": 25.4}, "foot": {"mm": 304.8, "m": 0.3048}, "square foot": {"m": 0.092903},
              "gross square foot": {"m": 0.092903}, "net square foot": {"m": 0.092903},
              "square inch": {"mm": 645.16, "m": 0.00064516}, "pound": {"kg": 0.45359, "N": 4.448}}
# pieces where the number reader records a figure without its unit, and that unit: a metric one ("50 pounds (220 N)":
# the newtons), or an imperial one (a unit word the reader doesn't know; "net" it reads since part c's fix check)
UNIT_NOT_RECORDED = {"408.3.2": "N"}
IMPERIAL_UNIT_NOT_RECORDED = {}


def _numbers(pid, entry):
    """A piece's recorded numbers, each unit the reader left out put back (the bare number before a metric figure takes
    the piece's imperial unit; a bare number after an imperial figure, its metric unit)."""
    numbers = list(entry["numbers"])
    metric, imperial = UNIT_NOT_RECORDED.get(str(pid)), IMPERIAL_UNIT_NOT_RECORDED.get(str(pid))
    for n, here in enumerate(numbers):
        bare = re.fullmatch(r"(?:and |not less than |not more than )?[\d,.]+", here)
        if bare and imperial and n + 1 < len(numbers) and _metric(numbers[n + 1]):
            numbers[n] = here + " " + imperial
        elif bare and metric and n and _imperial(numbers[n - 1]):
            numbers[n] = here + " " + metric
    return numbers


def _walk(numbers):
    """([(the imperial figure, the metric one printed after it, whether they disagree by more than 2%)], the indices of
    the metric figures compared, a split "22 860 mm"'s two halves both)."""
    out, used = [], set()
    for n, (here, after) in enumerate(zip(numbers, numbers[1:])):
        a, b = _figure(here), _figure(after)
        if not a or not b or a[1] not in CONVERSION or b[1] not in CONVERSION[a[1]]:
            continue
        metric, used = b[0], used | {n + 1}
        later = _figure(numbers[n + 2]) if n + 2 < len(numbers) else None
        if b[1] == "mm" and later and later[1] == "mm" and metric < 1000 and 100 <= later[0] < 1000:
            metric, used = metric * 1000 + later[0], used | {n + 2}      # "22 860 mm", read as "22 mm" and "860 mm"
        want = a[0] * CONVERSION[a[1]][b[1]]
        out.append((here, after, abs(metric - want) / want > 0.02))
    return out, used


def _compared(numbers):
    return _walk(numbers)[0]


def _misprinted(numbers):
    return [(here, after) for here, after, off in _compared(numbers) if off]


def test_the_conversion_walk_compares_every_imperial_figure():
    """Review rounds 3 to 5 of part c: the walk skipped feet printed with metres and pounds with kilograms, read
    "1 1/2 inch" as 1/2 and ".5 inch" as 5, and never saw a figure whose unit the reader left out. Every imperial
    figure a Chapter 4 piece records (by its unit word, read or not) is read, has a conversion, and is compared with
    the metric figure printed after it; and every metric figure is one compared (none is printed alone)."""
    assert _misprinted(["more than 420 foot", "12 m"]) and _misprinted(["not less than 3,500 pound", "158 kg"])
    assert not _misprinted(["more than 420 foot", "128 m"]) and not _misprinted(["75 foot", "22 mm", "860 mm"])
    assert _figure("not more than 1 1/2 inch") == (1.5, "inch") and _figure("2/3 inch") == (2 / 3, "inch")
    assert _figure(".5 inch") == (0.5, "inch") and _figure("22-1/2 inch") == (22.5, "inch")
    assert _compared(["greater than 1 1/2 square inch", "967 mm"]) == [("greater than 1 1/2 square inch", "967 mm", False)]
    assert _compared(["not exceed 5,000 square inch", "3.2 m"]) == [("not exceed 5,000 square inch", "3.2 m", False)]
    assert _compared(["not less than 30 net square foot", "2.8 m"]) == [("not less than 30 net square foot", "2.8 m", False)]
    pieces = load(NY / "text_verification.yaml")["pieces"]
    imperial = compared = 0
    for pid, entry in pieces.items():
        if re.fullmatch(r"4\d\d(\.\d+)*", str(pid)):
            numbers = _numbers(pid, entry)
            for n in numbers:
                if _imperial(n):
                    assert _figure(n) and _figure(n)[1] in CONVERSION, (pid, n)   # read, with a conversion
                    imperial += 1
            pairs, used = _walk(numbers)
            compared += len(pairs)
            alone = [m for k, m in enumerate(numbers) if _metric(m) and k not in used]
            assert not alone, (pid, alone)                     # a metric figure whose imperial one wasn't read
    assert imperial and compared == imperial, (compared, imperial)
    # 408.3.2's "50 pounds (220 N)": the newtons are recorded without their unit, and still compared (part d round 1)
    assert [x[:2] for x in _compared(_numbers("408.3.2", pieces["408.3.2"]))] == [
        ("not greater than 50 pound", "220 N"), ("50 pound", "220 N")]


def test_a_printed_figure_that_disagrees_with_its_conversion_is_said(rules):
    """Review rounds 1 to 3 of part c: 407.3.1.1 prints "2/3 inch (19.1 mm)" (19.1 mm is 3/4 inch) and 407.2.4
    "500 square feet (455 m2)" (500 sq ft is 46.45 m2). For every Chapter 4 piece, each imperial figure whose printed
    metric conversion disagrees by more than 2% is named in the second reading's flags and said in its flag's notes;
    which the State means is a person's check, and a reading Gordium gives cites where the same book prints the figure;
    never a claim about what another code prints without its source."""
    pieces = load(NY / "text_verification.yaml")["pieces"]
    found = {}
    for pid, entry in pieces.items():
        if re.fullmatch(r"4\d\d(\.\d+)+", str(pid)):
            for here, after in _misprinted(_numbers(pid, entry)):
                found.setdefault(str(pid), []).append((here, after))
    assert set(found) >= {"407.2.4", "407.3.1.1", "408.3.3", "408.8.3", "410.5.3.2"}, found   # the walk finds the ones it was written for
    block = _block_ids()
    for pid, pairs in found.items():
        flags = " ".join(pieces[pid].get("flags") or [])
        [rid] = [r for r in block if r.startswith(_prefix(pid))
                 and not any(r.startswith(_prefix(q)) for q in found if q.startswith(pid + "."))]
        notes = rules[rid]["notes"]
        for here, after in pairs:
            assert here.split()[-3 if "square" in here else -2] in flags and after.split()[0] in flags, (pid, here, after)
            assert after.split()[0] in notes, (pid, after)
        assert "model code" not in flags + notes, pid
        assert "person's check" in notes, pid
        assert "misprint" not in flags or "person's check" in flags, pid   # the second reading's words too (round 4)
        assert "misprint" not in notes or re.search(r"elsewhere \(p\.\d+, line \d+", notes), pid


# the uses Chapter 10's words name for Chapter 4's sections (Table 1017.2 note a's list, 1006.2.2's spaces), as word
# patterns matched in any case, so a plural, a missing article or a capital is caught too (review rounds 3 and 4 of part c)
USES = {r"\bmalls?\b": "402.8", r"\batriums?\b": "404.9", r"\bGroup I-2\b": "407.4",
        r"\bGroup I-2 care suites?\b": "407.4.4", r"\bhigh[- ]rise": "403.5", r"\bunderground\b": "405.7"}


def _named_uses(sentence):
    """The Chapter 4 sections a sentence names by their uses."""
    return {s for use, s in USES.items() if re.search(use, sentence, re.IGNORECASE)}


def test_the_uses_are_matched_in_any_number_case_and_without_an_article():
    assert _named_uses("Covered mall buildings and atriums are not brought in.") == {"402.8", "404.9"}
    assert _named_uses("Atriums and Group I-2 occupancies aren't brought in.") == {"404.9", "407.4"}
    assert _named_uses("High rise buildings are not brought in.") == {"403.5"}


def _sections(text):
    """The section numbers a plan line names, ranges expanded by their last part ("407.1 to 407.4" is 407.1 to
    407.4; "420.6 whole" is 420.6)."""
    out = set()
    for a, b in re.findall(r"(?<![\d.])(4\d\d(?:\.\d+)*)(?: to (4\d\d(?:\.\d+)*))?(?![\d])", text):
        out.add(a)
        if b and a.rsplit(".", 1)[0] == b.rsplit(".", 1)[0] and "." in a:
            head, lo = a.rsplit(".", 1)
            out |= {f"{head}.{n}" for n in range(int(lo), int(b.rsplit(".", 1)[1]) + 1)}
        elif b:
            out.add(b)
    return out


def _under(section, listed):
    return any(section == s or section.startswith(s + ".") for s in listed)


def test_the_plans_parts_list_names_each_parts_sections():
    """Review rounds 3 and 4 of part d: the plan's "Parts, in order" list still gave part d its first scope, and
    part d's status line reasoned about part e's 408.6.1. Each part's status line, up to what it brings in, names
    only sections under its own list line, never one under another part's."""
    plan = (REPO / "docs/decisions/2026-11-26_ny_building_chapter_4_egress.md").read_text(encoding="utf-8")
    parts = plan.split("## Parts, in order", 1)[1].split("## Status", 1)[0]
    status = plan.split("## Status", 1)[1]
    listed = {p: _sections(re.search(r"- \*\*" + p + r"\.[^\n]*", parts).group().split(":", 1)[1])
              for p in "abcdef"}
    for part in "abcdef":
        line = re.search(r"- \*\*" + part + r"\.\*\* Drafted[^\n]*", status).group()
        # every section the line names, brackets included (its reasoning sits there too); a dotted number only, never
        # "420 ft" or a rule id's "bc_407" (review round 4's fix check)
        stated = set(re.findall(r"(?<![\w.])(4\d\d\.\d+(?:\.\d+)*)(?!\d)", line.split("Drafted", 1)[1]))
        assert stated, part
        for s in stated:
            mine = _under(s, listed[part])
            theirs = [p for p in listed if p != part and _under(s, listed[p]) and not mine]
            assert mine and not theirs, (part, s, theirs)
    for part in listed:                                   # no part lists a section another part lists
        for other in listed:
            clash = [s for s in listed[part] if other != part and (_under(s, listed[other])
                                                                    or any(_under(o, {s}) for o in listed[other]))]
            assert not clash, (part, other, clash)
    assert _sections("407.1 to 407.4; 408.1") == {"407.1", "407.2", "407.3", "407.4", "408.1"}
    assert not _under("407.10", {"407.1"})


def test_an_unrated_group_b_corridor_where_an_ambulatory_care_facility_may_be_needs_review(ctx, rules):
    """Review round 1 of part e: 422.2 separates an ambulatory care facility (four or more care recipients who may be
    incapable of self-preservation) from adjacent corridors with a fire partition (708), so Table 1020.2's B row no
    longer passes an unrated corridor on its occupant load or NFPA 13 where one may be (stated, or not ruled out); a
    sure fail stays a fail, and stated none, the table decides."""
    r = rules["general.bc_table_1020_2_a_b_e_f_m_s_u"]
    base = {"occupancy_group": "B", "special_egress_spaces": False, "sprinklered_903_3_1_2": False,
            "sprinklered_903_3_1_3": False}

    def one(given, load, hours):
        [row] = parts.rows(r, {"corridor": [{"id": "c1", "measures": {"corridor_occupant_load": load,
                                                                       "corridor_fire_rating_hours": hours}}]},
                           {**base, **given}, ctx.allowed())
        return row["outcome"]
    for care in (True, None):
        given = {} if care is None else {"ambulatory_care_facility": care}
        assert one({**given, "sprinklered_903_3_1_1": True}, 100, 0) == "needs_review", care
        assert one({**given, "sprinklered_903_3_1_1": False}, 20, 0) == "needs_review", care
        assert one({**given, "sprinklered_903_3_1_1": False}, 100, 0) != "pass", care
        assert one({**given, "sprinklered_903_3_1_1": True}, 100, 1) == "pass", care
    assert one({"ambulatory_care_facility": False, "sprinklered_903_3_1_1": True}, 100, 0) == "pass"


def test_the_ambulatory_care_fact_says_what_it_decides():
    """Review round 2 of part e: the fact's name, its meaning and its Revit mark said only Table 1020.3's 72 in, though
    Section 422's flags and Table 1020.2's Group B band read it too."""
    names = (REPO / "packages/design_checker/design_checker/each_part.py").read_text(encoding="utf-8")
    name = names[names.index('    "ambulatory_care_facility": "'):].split('",\n', 1)[0]    # its words, both lines
    meaning = load(NY / "5_building_code_rules/drafted/records/proposed_measures.yaml")["ambulatory_care_facility"]["meaning"]
    marks = (REPO / "apps/revit_addin/src/Gordium.Revit.Reading/Marks.cs").read_text(encoding="utf-8")
    mark = marks[marks.index("AmbulatoryCareFacility = new("):][:1500].split(");", 1)[0]
    doc = (REPO / "docs/interior/interior_description_format.md").read_text(encoding="utf-8")
    block = doc[doc.index("  ambulatory_care_facility: "):].split("\n  corridors_within_dwelling_units:", 1)[0]
    summary = marks[:marks.index("AmbulatoryCareFacility = new(")].rsplit("/// <summary>", 1)[1]
    scope = (REPO / "packages/design_checker/design_checker/code_scope.py").read_text(encoding="utf-8")
    comment = scope[scope.index("# section group 4 (corridors)"):scope.index('"ambulatory_care_facility": "yes_no"')]
    tests = (REPO / "apps/revit_addin/tests/Gordium.Revit.Reading.Tests/CorridorFactsTests.cs").read_text(encoding="utf-8")
    test_summary = tests[:tests.index("public sealed class")]
    notes = {r["id"]: r for r in load(RULEBOOK)["rules"]}["general.bc_422_1_ambulatory_care_facilities"]["notes"]
    assert "1020.2" in notes and "1020.3" in notes                    # part e review round 4
    for words in (name, meaning, mark, block, summary, comment, test_summary):
        assert "422" in words and "1020.2" in words and "1020.3" in words, words[:120]


STORY_RULES = ["general.bc_1006_3_3_story_exits", "general.bc_table_1006_3_4_1__r2_dwelling_units",
               "general.bc_table_1006_3_4_2__a_b_e_f_m_u", "general.bc_table_1006_3_4_2__h_i_r",
               "general.bc_table_1006_3_4_2__s"]


@pytest.mark.parametrize("rid", STORY_RULES)
def test_each_story_band_example_is_decided_by_its_band(ctx, rules, rid):
    """Merge review of main into Chapter 4's line: #265's seating twin read a measure these examples didn't state, so
    it needed review on its own and no example showed the 402.8, 403.5.2 or 405.7.1 band. Each example a band was
    written for needs review with the band and passes without it."""
    import copy
    rule = rules[rid]
    allowed = ctx.allowed()
    bare = copy.deepcopy(rule)
    bare["review_when"] = [w for w in rule.get("review_when") or []
                           if not re.search(r"402\.8|403\.5\.2|405\.7\.1", w.get("reason") or "")]
    assert len(bare["review_when"]) < len(rule.get("review_when") or [])
    shown = [ex for ex in rule["examples"] if re.search(r"402\.8|403\.5\.2|405\.7\.1", ex.get("note") or "")
             and ex.get("expect") == "needs_review"]
    assert shown, rid
    for ex in shown:
        assert parts.worked_example(rule, ex, allowed)[0] == "needs_review", (rid, ex["note"][:60])
        assert parts.worked_example(bare, ex, allowed)[0] == "pass", (rid, ex["note"][:60])


# ---- part f: the Chapter 10 limits its sections tighten, held where the building may be that use --------------------
# From the law's words, never from the rules (pp.105, 109, 122):
# - 415.11.3.3 (p.122, lines 45-48): in a Group H-5 service corridor, at most 75 ft from any point to an exit, an exit
#   access corridor or a door into a fabrication area; dead ends at most 4 ft; at least two exits;
# - 415.11.3.4 (lines 49-50): a service corridor at least 5 ft wide, or 33 in wider than the widest cart, whichever is
#   greater (the carts aren't in the model, so no width is known to be enough);
# - 412.4.2 (p.109, lines 53-54): a residential aircraft hangar (Group U, 312.1) has two means of egress;
# - 410.5.3.3 (p.105, lines 57-59): where two means of egress are required from a technical production area, its
#   common path is at most 100 ft.
# Which corridor is a service corridor, which space a hangar or a technical production area, isn't in the model. A
# Group H-5 rule reads the stated group (a building of two or more groups is a flag: Table 1017.2's, 1006.2.1's and
# 1020.3's other-occupancies rows); the hangar and the technical production area by their stated facts, yes or not
# stated.
PART_F_GRID = {"egress_travel_distance": [10, 50, 74, 75, 75.5, 76, 100, 150, 200, 250, 300, 400],
               "story_exit_count": [0, 1, 2, 3, 4], "story_occupant_load": [1, 3, 5, 10, 11, 29, 30, 49, 50, 500, 501],
               "corridor_width": [24, 36, 44, 59.9, 60, 72, 96, 200],
               "corridor_occupant_load": [5, 30, 49, 50, 99, 100, 300],
               "corridor_dead_end_length": [0, 2, 4, 4.5, 10, 20, 30, 50],
               "corridor_dead_end_least_width": [1, 2, 5, 10, 30],
               "space_exit_count": [0, 1, 2, 3], "space_occupant_load": [1, 10, 20, 21, 30, 49, 50],
               "space_common_path": [10, 75, 99, 100, 100.5, 110, 125, 126]}
# each limit's measure, and the comparisons by which a rule's check holds a part to it: a story's travel at most
# so far, its exits and a space's at least so many, a corridor's width at least, a dead end and a common path at most
PART_F_LIMITS = {"egress_travel_distance": (ast.LtE, ast.Lt), "story_exit_count": (ast.GtE, ast.Gt),
                 "corridor_width": (ast.GtE, ast.Gt), "corridor_dead_end_length": (ast.LtE, ast.Lt),
                 "space_exit_count": (ast.GtE, ast.Gt), "space_common_path": (ast.LtE, ast.Lt)}


def _holds(rule):
    """The measures a rule's check holds to a limit (a comparison of the measure on its left, the limit's way); an exit
    count only where it is held to two (1006.2.1.1's three or four exits for 501 occupants or more ask nothing of a
    space with one), and a travel only by a rule holding no exit count (a story's single-exit allowance reads travel as
    its condition, the exit count rules hold it to two)."""
    out = set()
    for n in ast.walk(formula.parse(rule["check"])):
        if isinstance(n, ast.Compare):
            for m, ops in PART_F_LIMITS.items():
                held_to_two = re.search(r"(?<![\d.])2(?![\d.])", ast.unparse(n.comparators[0]))
                if m in ast.unparse(n.left) and isinstance(n.ops[0], ops) and \
                        (not m.endswith("exit_count") or held_to_two):
                    out.add(m)
    if out & {"story_exit_count", "space_exit_count"}:
        out.discard("egress_travel_distance")
    return out


def _part_f_walked(rules):
    """The rules each part f limit may tighten, found from the formulas: every per-part rule whose check holds one of
    the measures to a limit (1007.1.1's separation reads the exit count only to know whether two are required, and
    1006.2.1.1's three exits ask nothing of a space under 501: neither holds a count to at least two)."""
    return {rid: _holds(r) for rid, r in rules.items() if r.get("kind") == "rule" and r.get("for_each") and _holds(r)}


@pytest.mark.parametrize("seed", range(2))
def test_no_rule_passes_short_of_part_fs_limits_where_they_may_apply(ctx, rules, seed):
    """Property over every drafted rule whose check holds a story's travel or exits, a corridor's width or dead end, or
    a space's exits or common path to a limit (found from the formulas): every group, a building of two or more and
    one not stated, every sprinkler setting, every other fact yes, no or not stated, measures from a grid around each
    limit. In a building that may be Group H-5 (stated, two or more groups, or not stated) and may have a service
    corridor, no pass over 75 ft of travel, with fewer than two exits on a story, at any corridor width, or with a dead
    end over 4 ft (415.11.3.3, 415.11.3.4); in one that may be Group S-2, no story with fewer than two exits (406.5.7's
    two exit stairways); in one that may be Group U where an aircraft-related occupancy isn't ruled out, no space (not
    itself an exit) with fewer than two exits (412.4.2); where a stage, a platform or a technical production area isn't
    ruled out, no space (not itself an exit) with a common path over 100 ft (410.5.3.3)."""
    walked = _part_f_walked(rules)
    assert {"general.bc_table_1017_2_h5", "general.bc_table_1006_3_4_2__h_i_r", "general.bc_table_1020_3_corridor_width",
            "general.bc_1020_5_dead_end_other_groups", "general.bc_table_1006_2_1_u",
            "general.bc_table_1006_2_1_r2", "general.bc_table_1006_2_1_r3_r4"} <= set(walked), sorted(walked)
    allowed = ctx.allowed()
    rng = random.Random(seed)
    bad, passed = [], set()
    for rid in sorted(walked):
        rule, held = rules[rid], walked[rid]
        kind = rule["for_each"]
        own = parts.measure_kinds(kind)
        names = parts.formula_names(rule)
        for _ in range(500):
            given = {}
            # half the time a group the rule names (so each band rule is reached), else any, two or more, or none
            named = [g for g in GROUPS if f'"{g}"' in (rule.get("applies_when") or "")]
            group = rng.choice(named) if named and rng.random() < 0.5 else \
                rng.choice(GROUPS + ["mixed", None] + ["H-5", "S-2", "U", "R-2", "R-3"] * 3)
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
                    m[n] = rng.choice(PART_F_GRID.get(n, GRID.get(n, NUMBERS)))
            [row] = parts.rows(rule, {kind: [{"id": "p1", "measures": m}]}, given, allowed)
            if row["outcome"] != "pass":
                continue
            passed.add(rid)
            why = []
            # the building may be Group g, and the rule may meet it: stated g, or two or more groups or none stated where
            # the rule reads any group (1020.5's Group I-4 rule meets no Group H-5 building)
            applies = rule.get("applies_when") or ""
            may = lambda g: group == g or (group in ("mixed", None) and   # noqa: E731
                                           (not applies or g in applies or "mixed" in applies))
            if may("H-5") and given.get("service_corridors") is not False:
                if "egress_travel_distance" in held and not m.get("egress_travel_distance", 1e6) <= 75:
                    why.append("415.11.3.3's 75 ft")
                if "story_exit_count" in held and not m.get("story_exit_count", 0) >= 2:
                    why.append("415.11.3.3's two exits")
                if "corridor_width" in held:
                    why.append("415.11.3.4's width")
                if "corridor_dead_end_length" in held and not m.get("corridor_dead_end_length", 1e6) <= 4:
                    why.append("415.11.3.3's 4 ft dead end")
            if may("S-2") and "story_exit_count" in held and not m.get("story_exit_count", 0) >= 2:
                why.append("406.5.7's two exit stairways")
            if m.get("space_is_exit") is not True:
                if may("U") and given.get("aircraft_related_occupancy") is not False and "space_exit_count" in held \
                        and not m.get("space_exit_count", 0) >= 2:
                    why.append("412.4.2's two means of egress")
                if given.get("stages_or_platforms") is not False and "space_common_path" in held and \
                        not m.get("space_common_path", 1e6) <= 100:
                    why.append("410.5.3.3's 100 ft")
            if why:
                bad.append((rid, why, given, m))
    assert not bad, (sorted({(b[0], w) for b in bad for w in b[1]}), bad[:2])
    # not vacuous: the band rules still pass where the limits hold (Table 1017.2's H-5 row passes only with NFPA 13
    # and every fact it reads stated: its examples show it, test_each_part_f_band_is_shown_by_an_example...)
    assert {"general.bc_table_1006_2_1_u", "general.bc_table_1006_2_1_r2",
            "general.bc_table_1020_3_corridor_width"} - passed == set()


PART_F_BANDS = {"general.bc_table_1017_2_h5": "415.11.3.3", "general.bc_table_1006_3_4_2__h_i_r": "415.11.3.3",
                "general.bc_1020_3_corridor_capacity": "415.11.3.4",
                "general.bc_table_1020_3_corridor_width": "415.11.3.4",
                "general.bc_1020_5_dead_end_other_groups": "415.11.3.3", "general.bc_table_1006_2_1_u": "412.4.2",
                "general.bc_table_1006_2_1_r2": "410.5.3.3", "general.bc_table_1006_2_1_r3_r4": "410.5.3.3"}


@pytest.mark.parametrize("rid", sorted(PART_F_BANDS))
def test_each_part_f_band_is_shown_by_an_example_it_decides_and_quotes_its_section(ctx, rules, rid):
    """Each band part f adds has an example that needs review with it and passes without it (so the band, not another
    fact, decides it), and the rule quotes the section the band holds it to."""
    import copy
    rule, section = rules[rid], PART_F_BANDS[rid]
    allowed = ctx.allowed()
    bare = copy.deepcopy(rule)
    bare["review_when"] = [w for w in rule["review_when"] if "(" + section + ")" not in w["reason"]]
    assert len(bare["review_when"]) == len(rule["review_when"]) - 1, rid
    shown = [ex for ex in rule["examples"] if section in (ex.get("note") or "") and ex["expect"] == "needs_review"]
    assert shown, rid
    for ex in shown:
        assert parts.worked_example(rule, ex, allowed)[0] == "needs_review", (rid, ex["note"][:60])
        assert parts.worked_example(bare, ex, allowed)[0] == "pass", (rid, ex["note"][:60])
    assert any(src["quote"].startswith(("[F] " + section + " ", "[BE] " + section + " ")) for src in rule["sources"]), rid


def test_each_part_f_band_example_names_its_own_part():
    """Review round 1 of part f: each band example was copied from another example of its rule and kept that one's part
    name ("At 415.11.3.3's 75 ft" measuring 200 ft, "Apartment corridor at 44 in" measuring 72 in a Group H-5
    building). Each part f band example's part has a name no other example of the rule uses."""
    rules = _rules_by_id()
    for rid, section in PART_F_BANDS.items():
        names = [(e, p["name"]) for e in rules[rid]["examples"] for kind in (e.get("parts") or {})
                 for p in e["parts"][kind] if p.get("name")]
        for e, name in names:
            if section in (e.get("note") or "") and e["expect"] == "needs_review":
                assert sum(1 for _, n in names if n == name) == 1, (rid, name)


def test_410_5_3_2s_note_gives_table_1017_2s_largest_cells():
    """Review round 1 of part f: the note gave Table 1017.2 as "200 ft to 300 ft without a sprinkler system, 250 ft to
    400 ft with one", but the table prints I-4's 150 ft and H-1's 75 ft (p.341, lines 32 and 38). Its largest cells,
    typed from the page (line 31: F-2, S-2, U 300 and 400), are what 410.5.3.2's 300 ft and 400 ft never fall below."""
    notes = " ".join(_rules_by_id()["general.bc_410_5_3_2_exit_access_travel_distance"]["notes"].split())
    assert "largest cells are 300 ft without a sprinkler system and 400 ft with one, p.341, line 31" in notes
    assert not re.search(r"\b(200|250) ft to", notes)


def test_the_service_corridor_facts_words_name_every_rule_it_holds():
    """Review round 2 of part f: 1020.3's capacity band reads the service corridor fact in Group H-5 and in two or more
    groups, but the fact's meaning, the interior format and 415.11.3.4's notes named only Table 1020.3's width in
    Group H-5; and 406.5.7's notes said Chapter 10 checks the garage as Group S-2 though its flag shows for Group U."""
    meaning = " ".join(load(NY / "5_building_code_rules/drafted/records/proposed_measures.yaml")
                       ["service_corridors"]["meaning"].split())
    doc = (REPO / "docs/interior/interior_description_format.md").read_text(encoding="utf-8")
    block = " ".join(doc[doc.index("  service_corridors: "):].split("\n  facts_not_sent:", 1)[0].replace("#", " ").split())
    rules = _rules_by_id()
    notes = " ".join(rules["general.bc_415_11_3_4_service_corridor_width"]["notes"].split())
    for words in (meaning, block, notes):
        assert "1020.3's capacity" in words and "two or more groups" in words, words[:100]
    # review round 3: each rule named with its own verb (once "1020.3's capacity no corridor"), and the flags, gated on
    # Group H-5 or two or more groups, said so
    assert "capacity no corridor" not in meaning
    for words in (meaning, block):
        assert "Group H-5 or two or more groups, 415.11.3's flags" in words, words[:160]
    for rid in ("general.bc_415_11_3_3_service_corridor_egress", "general.bc_415_11_3_4_service_corridor_width"):
        assert rules[rid]["applies_when"].startswith('occupancy_group in ["H-5", "mixed"]'), rid
    garage = " ".join(rules["general.bc_406_5_7_open_parking_garage_egress"]["notes"].split())
    assert "as any Group S-2 building" not in garage and "p.58, lines 8-9" in garage
