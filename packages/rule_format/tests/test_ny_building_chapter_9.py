"""New York's Building Code Chapter 9 (fire protection and life safety systems), the parts egress turns on
(docs/decisions/2026-11-27_ny_building_chapter_9.md): where a sprinkler system is required (903.2) and which system
903.3.1 permits. A rule fails where the law requires a system for the stated groups and the stated system is none, or
one 903.3.1 doesn't permit there; it passes only where the stated system is one the law permits; anything the model
or the stated facts leave open needs review. Each rule is walked over every group (and buildings of two or more),
every sprinkler system and every fact it reads, against an oracle written from the law, never from the rules. Needs no
code cache (the quotes are checked word for word by `python -m rule_format` where the cache is)."""

import itertools
import json
import re

import pytest

from design_checker import code_scope
from rule_format import formula, parts
from rule_format.rulebook import REPO, Context, load, outcome

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
RULEBOOK = NY / "5_building_code_rules/drafted/general.yaml"
SECTIONS = NY / "2_extracted_text/gov.ny.building.2025.sections.jsonl"
LABELS = NY / "3_section_labels/gov.ny.building.2025.yaml"
CHAPTER_9 = re.compile(r"(Table )?9\d\d(\.\d+)*$")
GROUPS = ["A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "H-1", "H-2", "H-3", "H-4", "H-5", "I-1", "I-2",
          "I-3", "I-4", "M", "R-1", "R-2", "R-3", "R-4", "S-1", "S-2", "U"]
# buildings of two or more groups: an R, H or I portion with another, I-4 alone among the I groups, none of the three
MIXED = [["M", "R-2"], ["B", "R-1"], ["R-2", "R-3"], ["B", "H-2"], ["H-5", "F-1"], ["I-1", "R-2"], ["I-2", "B"],
         ["I-3", "A-3"], ["I-4", "B"], ["I-4", "R-3"], ["A-2", "B"], ["S-2", "M", "U"]]
SPRINKLERS = [None, "none", "nfpa_13", "nfpa_13r", "nfpa_13d"]
RULES = ("general.bc_903_2_5_1_group_h_sprinklers", "general.bc_903_2_6_group_i_sprinklers",
         "general.bc_903_2_8_group_r_sprinklers")
UNSTATED = None


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(NY)


@pytest.fixture(scope="module")
def book():
    return load(RULEBOOK)["rules"]


@pytest.fixture(scope="module")
def pieces():
    rows = [json.loads(line) for line in SECTIONS.read_text(encoding="utf-8").splitlines()]
    return {p["id"]: p for p in rows[1:] if CHAPTER_9.match(p["id"])}


@pytest.fixture(scope="module")
def labels(pieces):
    return {k: v for k, v in load(LABELS)["labels"].items() if k in pieces}


def _rid(pid: str) -> str:
    """The id prefix the coverage report reads as naming a piece (section_labeling.coverage): general.bc_903_2_8_ for
    903.2.8, general.bc_table_903_2_5_2_ for Table 903.2.5.2."""
    return "general.bc_" + "".join(c if c.isalnum() else "_" for c in pid.lower()) + "_"


def _own(book, pid):
    """The rules naming the piece itself: 903.2.8's, never 903.2.8.1's (the next word after the number is a word)."""
    return [r for r in book if re.match(re.escape(_rid(pid)) + "[a-z]", r["id"])]


def _rule(book, rid):
    [r] = [r for r in book if r["id"] == rid]
    return r


def test_every_chapter_9_piece_brought_in_is_labeled_and_every_rule_or_flag_has_its_own(pieces, labels, book):
    assert pieces and set(labels) == set(pieces)
    for pid, v in labels.items():
        if v["label"] in ("flag", "rule"):
            mine = _own(book, pid)
            kinds = {r["kind"] for r in mine}
            # a flag piece has flags only; a rule piece a rule, and maybe a flag for what its rule can't read (907.2.3)
            assert mine and (kinds == {"flag"} if v["label"] == "flag" else "rule" in kinds), pid


def test_every_chapter_9_rule_and_flag_quotes_every_line_of_its_piece(pieces, labels, book):
    """Each rule or flag quotes its whole piece, every exception with it, so an exception that loosens or tightens it
    can't go unseen."""
    for pid, v in labels.items():
        if v["label"] not in ("flag", "rule"):
            continue
        quoted = {(s["page"], n) for r in _own(book, pid) for s in r["sources"]
                  for n in range(s["lines"][0], s["lines"][1] + 1)}
        for page, a, b in pieces[pid]["lines"]:
            assert {(page, n) for n in range(a, b + 1)} <= quoted, pid


TOKEN = re.compile(r"(?<![\d.-])\d{3,4}(?:\.\d+)*(?:\(\d\))?(?![\d.]*\d)|Chapter \d+|NFPA \d+[A-Z]?")


def _refs(text: str) -> set[str]:
    out = set()
    for m in re.finditer(r"(?:Sections?|Tables?) ((?:\d{3,4}(?:\.\d+)*(?:\(\d\))?(?:, | and | or | through )?)+)", text):
        out |= set(re.findall(r"\d{3,4}(?:\.\d+)*(?:\(\d\))?", m.group(1)))
    out |= set(re.findall(r"Chapter \d+", text))
    return out


def _shown_note(rule: dict) -> str:
    """The words a flag's result shows (design_checker/egress.py _flag_item: the first example's note that needs
    review)."""
    return next((e["note"] for e in rule.get("examples") or [] if e.get("note") and e.get("expect") == "needs_review"),
                "")


def test_every_section_a_chapter_9_flag_names_is_named_in_its_words(labels, book):
    """Every section or chapter a flagged piece sends to is named in what the architect reads on its flag, so a
    person's check never leaves out a section the law joins to it (the piece's own number aside)."""
    for pid, v in labels.items():
        if v["label"] not in ("flag", "rule"):
            continue
        for r in _own(book, pid):
            if r["kind"] != "flag":           # a rule piece's own flag too (907.2.3's manual fire alarm system)
                continue
            quote = " ".join(s["quote"] for s in r["sources"])
            shown = {m.group(0) for m in TOKEN.finditer(_shown_note(r))}
            missing = sorted(x for x in _refs(quote) - {pid} if x not in shown)
            assert not missing, (r["id"], missing)


def test_every_chapter_9_flag_is_a_persons_check_never_a_pass(labels, book, ctx):
    """A flag has no check, and needs review for every building it isn't narrowed away from; a narrowed one is
    narrowed only by a fact the architect states (the groups, the sprinkler system) and needs review while that fact
    isn't stated."""
    allowed = ctx.allowed()
    by = {"occupancy_group", "group_h_present", "sprinklered_903_3_1_1", "sprinklered_903_3_1_2", "sprinklered_903_3_1_3",
          "nfpa_13r_stated", "occupied_outdoor_areas", "ambulatory_care_facility",   # part b: 903.2.1.6, 903.2.2.1
          "emergency_voice_alarm_system", "townhouse_units",              # part c: 907.2.1.1; part e: 905.3
          "separate_means_of_egress"}
    for pid, v in labels.items():
        if v["label"] != "flag":
            continue
        for r in _own(book, pid):
            assert r["kind"] == "flag" and "check" not in r, r["id"]
            if "applies_when" in r:
                assert formula.names(r["applies_when"]) <= by, r["id"]
            assert outcome(r, {}, allowed) == "needs_review", r["id"]


def test_chapter_9_rules_sit_in_book_order_between_chapters_7_and_10(book):
    """The convention that keeps parallel chapters' rules from colliding when merged (docs/decisions/
    2026-11-27_ny_building_chapter_9.md decision 1): Chapter 9's rules sit together, in book order, after Chapter 7's
    and before Chapter 10's first rule (1004.7)."""
    ids = [r["id"] for r in book]
    nine = [i for i, rid in enumerate(ids) if re.match(r"general\.bc_(table_)?9\d\d_", rid)]
    assert nine == list(range(nine[0], nine[-1] + 1))
    assert ids[nine[-1] + 1] == "general.bc_1004_7_outdoor_areas"
    assert re.match(r"general\.bc_(table_)?7\d\d_", ids[nine[0] - 1])

    def key(rid):
        m = re.match(r"general\.bc_(?:table_)?((?:\d+_)+)", rid)
        return [int(x) for x in m.group(1).strip("_").split("_")]
    assert [key(ids[i]) for i in nine] == sorted(key(ids[i]) for i in nine)


# ---- the walk: every group, every sprinkler system, every fact, against the law ----------------------------------

def _required(rid: str, groups, system, stories, townhouse, sleeping):
    """The law's answer for one building: "pass", "fail", "needs_review" or "not_applicable", written from 903.2.5.1,
    903.2.6, 903.2.8 and 903.3.1 (never from the rules). groups None: not stated; system None: not stated."""
    if groups is None:
        return {"needs_review"}
    one = groups[0] if len(set(groups)) == 1 else None
    if rid.endswith("group_h_sprinklers"):
        if not any(g.startswith("H-") for g in groups):
            return {"not_applicable"}
        if system is None:
            return {"needs_review"}
        if system == "nfpa_13":
            return {"pass"}                       # 903.2.5.1 with 903.3.1.1
        if system == "none" or one:               # 903.3.1: 13R is Group R's, 13D the dwellings'
            return {"fail"}
        return {"needs_review"}                   # two or more groups, 13R or 13D: which portion has which
    if rid.endswith("group_i_sprinklers"):
        i13 = any(g in ("I-1", "I-2", "I-3") for g in groups)
        if not i13 and "I-4" not in groups:
            return {"not_applicable"}
        if system is None:
            return {"needs_review"}
        if system == "nfpa_13":
            return {"pass"}
        if system == "none":
            return {"fail"} if i13 else {"needs_review"}     # exceptions 2 and 3 are I-4's alone
        if one is None or one == "I-4":
            return {"needs_review"}
        if one == "I-1" and system == "nfpa_13r":
            return {"needs_review"}               # exception 1: Condition 1
        return {"fail"}                           # 13D in I-1 to I-3, 13R in I-2 and I-3
    # 903.2.8
    if not any(g.startswith("R-") for g in groups):
        return {"not_applicable"}
    if system is None:
        return {"needs_review"}
    if system == "nfpa_13" or (one == "R-3" and system == "nfpa_13d"):
        return {"pass"}                           # 903.3.1.1; 903.2.8.1 with 903.3.1.3
    if system == "none":
        return {"fail"}
    if system == "nfpa_13r" and all(g.startswith("R-") for g in groups) and stories is not None and stories > 4:
        return {"fail"}                           # 903.3.1.2 item 1: the Group R occupancy, here the building
    if one is None:
        return {"needs_review"}
    if system == "nfpa_13r":                      # 903.3.1.2: four stories or fewer, heights not in the model
        return {"fail"} if stories is not None and stories > 4 else {"needs_review"}
    if one == "R-2" and townhouse is False and sleeping is False:
        return {"fail"}                           # more than two dwelling units (310.3), not townhouses: 903.3.1.3
    return {"needs_review"}                       # R-4 Condition 1; a dwelling or townhouses not ruled out


def _cases():
    for groups in [None] + [[g] for g in GROUPS] + MIXED:
        for system in SPRINKLERS:
            for stories, townhouse, sleeping in itertools.product((UNSTATED, 1, 4, 5, 9), (UNSTATED, False, True),
                                                                  (UNSTATED, False, True)):
                yield groups, system, stories, townhouse, sleeping


def _answer(rule, building, allowed) -> str:
    """The rule's answer for one building as the checker gives it: the 903.2 rules are read on each story (the Building
    Code check reads its rules part by part), so one story's row; a flag or other building-wide rule, its outcome."""
    values = code_scope.building_measures(building)
    if not parts.is_part_rule(rule):
        return outcome(rule, values, allowed)
    [row] = parts.rows(rule, {rule["for_each"]: [{"id": "p1", "name": "Level 1", "measures": {}}]}, values, allowed)
    return row["outcome"]


def _building(groups, system, stories, townhouse, sleeping) -> dict:
    b = {"occupancy_groups": groups, "sprinkler_system": system, "stories_above_grade_plane": stories,
         "townhouse_units": townhouse, "r2_sleeping_units": sleeping}
    return {k: v for k, v in b.items() if v is not None}


@pytest.mark.parametrize("rid", RULES)
def test_each_903_2_rule_gives_the_laws_answer_for_every_building(book, ctx, rid):
    """The walk: every group alone and twelve buildings of two or more, each sprinkler system or none stated, the
    stories, townhouse units and Group R-2's sleeping units each stated or not, the building block worked into the
    rulebook's measures as the checker does (code_scope.building_measures). The rule's answer is the law's, exactly:
    never a pass the law doesn't give, never a fail it doesn't."""
    rule, allowed, wrong = _rule(book, rid), ctx.allowed(), []
    for case in _cases():
        got = _answer(rule, _building(*case), allowed)
        if got not in _required(rid, *case):
            wrong.append((case, got, _required(rid, *case)))
    assert not wrong, wrong[:5]


def test_the_walks_oracle_catches_a_rule_changed(book, ctx):
    """The pin: each rule changed the way a slip would (13R counted outside Group R, 13D counted in Group R-2, the
    stories ignored, a building of two or more groups with no system let through) disagrees with the oracle."""
    allowed = ctx.allowed()
    mutants = {
        "general.bc_903_2_5_1_group_h_sprinklers": {"check": "sprinklered_903_3_1_1 or sprinklered_903_3_1_2"},
        "general.bc_903_2_6_group_i_sprinklers": {"applies_when": "group_i1_i2_i3_present"},
        "general.bc_903_2_8_group_r_sprinklers": {"check": "sprinklered_903_3_1_1 or sprinklered_903_3_1_2"},
    }
    for rid, change in mutants.items():
        rule = {**_rule(book, rid), **change}
        assert any(_answer(rule, _building(*c), allowed) not in _required(rid, *c)
                   for c in _cases()), rid
    # the stories: since review round 3 a stated count over four makes the 13R fact itself no (code_scope), so the
    # building measures, not the rule's band, are what a slip would break
    rule = _rule(book, "general.bc_903_2_8_group_r_sprinklers")
    stated = code_scope.building_measures(_building(["R-2"], "nfpa_13r", 5, None, None))
    assert stated["sprinklered_903_3_1_2"] is False
    assert _answer(rule, _building(["R-2"], "nfpa_13r", 5, None, None), allowed) == "fail"
    assert _required(RULES[2], ["R-2"], "nfpa_13r", 5, None, None) == {"fail"}


def test_the_new_measures_follow_the_stated_groups_and_facts():
    m = code_scope.building_measures({"occupancy_groups": ["M", "R-2"], "stories_above_grade_plane": 3,
                                      "townhouse_units": False})
    assert (m["group_r_present"], m["group_h_present"], m["group_i1_i2_i3_present"]) == (True, False, False)
    assert m["stories_above_grade_plane"] == 3 and m["townhouse_units"] is False and m["occupancy_group"] == "mixed"
    m = code_scope.building_measures({"occupancy_groups": ["I-4", "H-3"]})
    assert (m["group_r_present"], m["group_h_present"], m["group_i1_i2_i3_present"]) == (False, True, False)
    assert "group_r_present" not in code_scope.building_measures({"sprinkler_system": "none"})   # groups not stated


def test_the_13r_flag_shows_wherever_a_13r_system_is_stated_or_the_system_isnt(book, ctx):
    """Group 5a's false pass came from an NFPA 13R system outside Group R: 903.3.1.2's flag is a person's check for
    every building with a 13R system stated, in Group R too (its heights aren't in the model), and while the system
    isn't stated; set aside only where another system is stated."""
    allowed = ctx.allowed()
    for rid in ("general.bc_903_3_1_2_nfpa_13r_limits", "general.bc_903_3_1_2_2_corridors_balconies_13r"):
        r = _rule(book, rid)
        for groups in [None, ["R-2"], ["B"], ["M", "R-2"]]:
            got = outcome(r, code_scope.building_measures(_building(groups, "nfpa_13r", 3, None, None)), allowed)
            assert got == "needs_review", (rid, groups)
            assert outcome(r, code_scope.building_measures(_building(groups, None, 3, None, None)),
                           allowed) == "needs_review"
            for other in ("none", "nfpa_13", "nfpa_13d"):
                assert outcome(r, code_scope.building_measures(_building(groups, other, 3, None, None)),
                               allowed) == "not_applicable"


# ---- part b (2026-11-27): the groups whose requirement turns on fire area, occupant load or story -----------------

# each per-room rule, its group and the limits typed from the page (903.2.1.1 to 903.2.1.4: p.269 lines 33-34, 40-41,
# 46-47, 52-53; 903.2.3: p.270 lines 27 and 31; 903.2.4: p.270 line 34; 903.2.7: p.271 line 24; 903.2.9: p.271 line 45):
# a fire area over the area, or with an occupant load of the load or more (None: no occupant load condition)
ROOM_RULES = {
    "general.bc_903_2_1_1_group_a1_sprinklers": ("A-1", 12000, 300),
    "general.bc_903_2_1_2_group_a2_sprinklers": ("A-2", 5000, 100),
    "general.bc_903_2_1_3_group_a3_sprinklers": ("A-3", 12000, 300),
    "general.bc_903_2_1_4_group_a4_sprinklers": ("A-4", 12000, 300),
    "general.bc_903_2_3_group_e_sprinklers": ("E", 12000, 300),
    "general.bc_903_2_4_group_f1_sprinklers": ("F-1", 12000, None),
    "general.bc_903_2_7_group_m_sprinklers": ("M", 12000, None),
    "general.bc_903_2_9_group_s1_sprinklers": ("S-1", 12000, None),
}


def _room_law(group_of_rule, limit, load_limit, groups, system, area, load):
    """The law's answer for one room, written from 903.2.1.1 to 903.2.9 and 903.3.1 (never from the rules): a room
    lies within one fire area, so a room over the area or at the load settles the requirement; anything else about
    its fire area (its true size, its floor, other fire areas) isn't in the model."""
    if groups is None:
        return {"needs_review"}
    if len(set(groups)) != 1 or groups[0] != group_of_rule:
        return {"not_applicable"}                 # another group, or two or more: 903.2's flag
    if system is None:
        return {"needs_review"}
    if system == "nfpa_13":
        return {"pass"}
    settled = (area is not None and area > limit) or (load_limit is not None and load is not None and
                                                      load >= load_limit)
    return {"fail"} if settled else {"needs_review"}


def _room_answer(rule, building, measures, allowed):
    values = code_scope.building_measures(building)
    [row] = parts.rows(rule, {"space": [{"id": "p1", "name": "Room", "measures": measures}]}, values, allowed)
    return row["outcome"]


@pytest.mark.parametrize("rid", sorted(ROOM_RULES))
def test_each_room_rule_gives_the_laws_answer_for_every_room(book, ctx, rid):
    """The walk: every group alone, two buildings of two or more groups and none stated; each sprinkler system or none
    stated; the room's floor area and occupant load around each printed limit, or not measured. The rule's row is
    the law's, exactly."""
    group, limit, load_limit = ROOM_RULES[rid]
    rule, allowed, wrong = _rule(book, rid), ctx.allowed(), []
    areas = [None, 0, limit - 1, limit, limit + 0.01, 10 * limit]
    loads = [None] if load_limit is None else [None, 0, load_limit - 1, load_limit - 0.01, load_limit, load_limit + 5]
    for groups in [None, [group], ["M", "R-2"], [group, "B"]] + [[g] for g in GROUPS if g != group]:
        for system in SPRINKLERS:
            for area, load in itertools.product(areas, loads):
                m = {k: v for k, v in (("space_floor_area", area), ("space_occupant_load", load)) if v is not None}
                got = _room_answer(rule, _building(groups, system, None, None, None), m, allowed)
                if got not in _room_law(group, limit, load_limit, groups, system, area, load):
                    wrong.append((groups, system, area, load, got))
    assert not wrong, wrong[:5]


def test_the_room_walks_oracle_catches_a_limit_changed(book, ctx):
    """The pin: a limit moved the way a misread would move it (12,000 read 1,200; 300 read 30; 'or more' read 'more
    than') disagrees with the oracle."""
    allowed = ctx.allowed()
    rid = "general.bc_903_2_1_1_group_a1_sprinklers"
    r = _rule(book, rid)
    for old, new in (("> 12000", "> 1200"), (">= 300", ">= 30"), (">= 300", "> 300")):
        w = r["review_when"][0]
        mutant = {**r, "review_when": [{**w, "when": w["when"].replace(old, new)}]}
        cases = [(1500, None), (None, 30), (None, 300)]
        assert any(_room_answer(mutant, _building(["A-1"], "none", None, None, None),
                                {k: v for k, v in (("space_floor_area", a), ("space_occupant_load", ld)) if v is not None},
                                allowed) not in _room_law("A-1", 12000, 300, ["A-1"], "none", a, ld)
                   for a, ld in cases), (old, new)

def test_no_rule_passes_on_a_13r_system_outside_group_r(book, ctx):
    """Review round 1 (2026-11-27), the class: 903.3.1.2 permits an NFPA 13R system only in Group R occupancies, so no
    rule may pass a part with a 13R system stated in a building of another group (or two or more groups) that it
    doesn't pass with no system at all. 1007.1.1's two remoteness rules and Group I-4's two-exit rule (1006.2.1) did
    (a Group B story's exits 0.4 of the diagonal apart passed at one-third). Walked over every rule that reads the
    13R fact, each worked example's parts, and every group but R."""
    allowed, wrong, walked = ctx.allowed(), [], 0
    others = [[g] for g in GROUPS if not g.startswith("R-")] + [["M", "R-2"], ["B", "I-1"]]
    for r in book:
        reads = {n for t in [r.get("check")] + [w["when"] for w in r.get("review_when") or []] if t
                 for n in formula.names(t)}
        if r["kind"] != "rule" or "sprinklered_903_3_1_2" not in reads or not parts.is_part_rule(r):
            continue
        for e in r.get("examples") or []:
            kind = r["for_each"]
            if not (e.get("parts") or {}).get(kind):
                continue
            # the example's other facts, its groups and system replaced by each case's
            facts = {k: v for k, v in e["given"].items()
                     if code_scope.DERIVED.get(k, (None,))[0] not in ("occupancy_groups", "sprinkler_system")}
            for groups in others:
                answers = {}
                for system in ("nfpa_13r", "none"):
                    values = {**facts, **code_scope.building_measures({"occupancy_groups": groups,
                                                                       "sprinkler_system": system})}
                    answers[system] = [row["outcome"] for row in parts.rows(r, e["parts"], values, allowed)]
                walked += 1
                for with_13r, without in zip(answers["nfpa_13r"], answers["none"]):
                    if with_13r == "pass" and without != "pass":
                        wrong.append((r["id"], groups, e.get("note", "")[:60]))
    assert walked > 500 and not wrong, wrong[:5]



def test_part_bs_label_reasons_name_their_own_group_and_limits(labels, book):
    """Part b review round 1: the eight per-room rules' labels shared one reason naming no group, and claimed an
    occupant-load limit for F-1, M and S-1, which have none; two flag reasons said "a person's check" twice. Each
    rule's reason now names the group its rule reads and an occupant load only where its rule reads one; no reason
    repeats itself; and a piece labeled reference has no rule or flag of its own."""
    for rid in ROOM_RULES:
        r = _rule(book, rid)
        pid = r["title"].split("(BCNYS ")[1].rstrip(")")
        reason = labels[pid]["reason"]
        assert f"Group {ROOM_RULES[rid][0]} fire area" in reason, pid
        assert ("occupant load" in reason) == ("space_occupant_load" in formula.names(r["review_when"][0]["when"])), pid
    for pid, v in labels.items():
        assert "check.:" not in v["reason"] and v["reason"].count("a person's check") <= 1, pid
        if v["label"] in ("reference", "not_for_checking"):
            assert not _own(book, pid), pid


def test_the_room_rules_fail_only_where_both_occupant_load_readings_reach_the_limit(book, ctx):
    """Part b review round 1 (a test gap): most rooms' occupant loads come as two readings (occupant_load.py: a gross
    factor, or 1004.5.1's increase not ruled out). A fail needs the lower reading at the limit; a split needs review;
    NFPA 13 passes."""
    allowed = ctx.allowed()
    for rid, (group, limit, load_limit) in ROOM_RULES.items():
        if load_limit is None:
            continue
        rule = _rule(book, rid)

        def answer(lo, hi, system):
            part = {"id": "p1", "name": "Room", "measures": {"space_floor_area": 100},
                    "readings": {"space_occupant_load": [{"value": lo, "named": {"increase": "no"}},
                                                         {"value": hi, "named": {"increase": "yes"}}]}}
            [row] = parts.rows(rule, {"space": [part]}, code_scope.building_measures(
                _building([group], system, None, None, None)), allowed)
            return row["outcome"]
        assert answer(load_limit - 1, load_limit + 50, "none") == "needs_review", rid
        assert answer(load_limit, load_limit + 50, "none") == "fail", rid
        assert answer(load_limit, load_limit + 50, "nfpa_13r") == "fail", rid
        assert answer(load_limit - 1, load_limit + 50, "nfpa_13") == "pass", rid


def test_the_grandstands_flag_shows_for_a_school(book, ctx):
    """Part b review round 1: 903.2.1.5.1 is worded for any enclosed space under grandstands or bleachers, and an
    assembly space associated with Group E is part of it (303.1.3, p.68), so a building stated Group E sees it."""
    r = _rule(book, "general.bc_903_2_1_5_1_under_grandstands")
    assert outcome(r, code_scope.building_measures({"occupancy_groups": ["E"]}), ctx.allowed()) == "needs_review"
def test_the_separation_thresholds_are_decided_with_the_groups_not_stated(book, ctx):
    """Review round 2 (2026-11-27): with a 13R system stated and the groups not, 1007.1.1's and 1007.1.2's thresholds
    were an if-else on an unknown test, so a pair a full diagonal apart needed review (and a pair at 0.2 no longer
    failed): stating a 13R system gave a worse answer than stating none. Written as "at least one-half, or at least
    one-third where the system counts", each gives the same answer as with no system or NFPA 13."""
    allowed = ctx.allowed()
    cases = [("general.bc_1007_1_1_remoteness", "story", {"story_exit_count": 2, "exit_remoteness_ratio": 0.87}, "pass"),
             ("general.bc_1007_1_1_space_remoteness", "space",
              {"space_is_exit": False, "space_exit_count": 2, "space_exit_remoteness_ratio": 0.6}, "pass"),
             ("general.bc_1007_1_2_space_three_or_more", "space",
              {"space_is_exit": False, "space_exit_count": 3, "space_occupant_load": 600,
               "space_exit_remoteness_ratio": 0.2}, "fail")]
    for rid, kind, m, want in cases:
        for system in ("none", "nfpa_13", "nfpa_13r"):
            values = code_scope.building_measures({"sprinkler_system": system})
            [row] = parts.rows(_rule(book, rid), {kind: [{"id": "p1", "name": "Part", "measures": m}]}, values, allowed)
            assert row["outcome"] == want, (rid, system, row["outcome"])


def test_the_13r_flag_says_what_chapter_10_counts(book, ctx):
    """Review rounds 2 and 3: a stated NFPA 13R system counts in Chapter 10's allowances only in a building stated
    Group R alone, and not where it states more than four stories above grade plane (903.3.1.2 item 1: a Group R
    occupancy of six stories isn't one 13R is permitted in, so 1007.1.1's one-third doesn't apply); its heights are the
    architect's statement. The flag's shown words say exactly that."""
    note = _shown_note(_rule(book, "general.bc_903_3_1_2_nfpa_13r_limits"))
    assert "only in a building stated Group R" in note and "more than four" in note and "nor one Chapter 10" not in note
    allowed = ctx.allowed()
    def story(stories, ratio):
        b = {"occupancy_groups": ["R-2"], "sprinkler_system": "nfpa_13r"}
        if stories is not None:
            b["stories_above_grade_plane"] = stories
        [row] = parts.rows(_rule(book, "general.bc_1007_1_1_remoteness"),
                           {"story": [{"id": "p1", "name": "L1", "measures": {"story_exit_count": 2,
                                                                             "exit_remoteness_ratio": ratio}}]},
                           code_scope.building_measures(b), allowed)
        return row["outcome"]
    assert story(6, 0.4) != "pass" and story(6, 0.6) == "pass"
    assert story(4, 0.4) == "pass" and story(None, 0.4) == "pass"        # the stories stated within, or not stated
    assert code_scope.building_measures({"occupancy_groups": ["M", "R-2"], "sprinkler_system": "nfpa_13r",
                                         "stories_above_grade_plane": 6})["sprinklered_903_3_1_2"] is True


def test_the_vehicle_storage_flags_show_for_every_group(book, ctx):
    """Part b review round 2: 903.2.10.1 and 903.2.10.2 are worded for buildings used to store vehicles, whatever
    their group, and storage accessory to another occupancy is part of it (311.1.1), so a Group B office's truck bay
    or a Group R-2 building's car stacker is its own: both flags show for every group."""
    allowed = ctx.allowed()
    for rid in ("general.bc_903_2_10_1_commercial_parking", "general.bc_903_2_10_2_mechanical_access_garages"):
        for groups in (["B"], ["F-1"], ["R-2"], ["M"], ["S-2"]):
            assert outcome(_rule(book, rid), code_scope.building_measures({"occupancy_groups": groups}),
                           allowed) == "needs_review", (rid, groups)


# ---- part c (2026-11-27): the emergency voice/alarm system by the occupancy's occupant load (907.2.1.1, 907.2.3) ----

# each rule, its groups, the part it is read on and its limit typed from the page (907.2.1.1, p.285 lines 9-11: "an
# occupant load of 1,000 or more", read on each room since Group A occupancies separated per 707.3.10 count apart,
# 907.2.1, p.284 lines 40-42; 907.2.3 exception 2, p.285 lines 42-43: not required "with occupant loads of 100 or
# less", read on each story)
VOICE_RULES = {"general.bc_907_2_1_1_group_a_voice_alarm": (["A-1", "A-2", "A-3", "A-4", "A-5"], 1000, ">=", "space"),
               "general.bc_907_2_3_group_e_voice_alarm": (["E"], 100, ">", "story")}


def _voice_law(groups_of_rule, limit, op, groups, voice, load):
    """The law's answer for one room or story, from 907.2.1, 907.2.1.1 and 907.2.3 (never from the rules): a room (A)
    or story (E) at the limit settles that the system is required, its occupancy's load being at least the room's or
    story's; less, the rest of the occupancy may reach it; Group A-5's outdoor bleachers may take exceptions 2 or 3."""
    if groups is None:
        return {"needs_review"}
    if len(set(groups)) != 1 or groups[0] not in groups_of_rule:
        return {"not_applicable"}
    if voice is None:
        return {"needs_review"}
    if voice:
        return {"pass"}
    if groups[0] == "A-5":
        return {"needs_review"}
    settled = load is not None and (load >= limit if op == ">=" else load > limit)
    return {"fail"} if settled else {"needs_review"}


@pytest.mark.parametrize("rid", sorted(VOICE_RULES))
def test_each_voice_alarm_rule_gives_the_laws_answer(book, ctx, rid):
    groups_of_rule, limit, op, kind = VOICE_RULES[rid]
    measure = "space_occupant_load" if kind == "space" else "story_occupant_load"
    rule, allowed, wrong = _rule(book, rid), ctx.allowed(), []
    for groups in [None, ["M", "R-2"], [groups_of_rule[0], "B"]] + [[g] for g in GROUPS]:
        for voice in (None, True, False):
            for load in (None, 0, limit - 1, limit - 0.01, limit, limit + 0.01, limit + 1, 10 * limit):
                b = {"occupancy_groups": groups} if groups else {}
                if voice is not None:
                    b["emergency_voice_alarm_system"] = voice
                m = {} if load is None else {measure: load}
                [row] = parts.rows(rule, {kind: [{"id": "p1", "name": "Part", "measures": m}]},
                                   code_scope.building_measures(b), allowed)
                if row["outcome"] not in _voice_law(groups_of_rule, limit, op, groups, voice, load):
                    wrong.append((groups, voice, load, row["outcome"]))
    assert not wrong, wrong[:5]


def test_part_cs_review_round_1(book, ctx):
    """Part c review round 1: a Group A-1 story of three 400-person rooms (each its own occupancy where separated per
    707.3.10) never fails 907.2.1.1 (it is read on each room); a building of two or more groups with no voice/alarm
    system stated sees 907.2.1.1's flag; 907.2.5's organic coatings show for Group F; 907.2's note keeps the single
    box where sprinklers stand in for the others."""
    allowed = ctx.allowed()
    r = _rule(book, "general.bc_907_2_1_1_group_a_voice_alarm")
    assert r["for_each"] == "space"
    rooms = [{"id": f"p{n}", "name": f"Auditorium {n}", "measures": {"space_occupant_load": 400}} for n in range(3)]
    rows = parts.rows(r, {"space": rooms}, code_scope.building_measures(
        {"occupancy_groups": ["A-1"], "emergency_voice_alarm_system": False}), allowed)
    assert {x["outcome"] for x in rows} == {"needs_review"}
    flag = _rule(book, "general.bc_907_2_1_1_mixed_voice_alarm")
    assert outcome(flag, code_scope.building_measures({"occupancy_groups": ["A-1", "B"]}), allowed) == "needs_review"
    assert outcome(flag, code_scope.building_measures({"occupancy_groups": ["A-1", "B"],
                                                       "emergency_voice_alarm_system": True}), allowed) ==         "not_applicable"
    h = _rule(book, "general.bc_907_2_5_group_h_fire_alarm")
    assert outcome(h, code_scope.building_measures({"occupancy_groups": ["F-1"]}), allowed) == "needs_review"
    assert "a single one still" in _shown_note(_rule(book, "general.bc_907_2_where_required"))


def test_part_cs_review_round_2(book, labels):
    """Part c review round 2: 907.2.1.1's label says it is read on each room (707.3.10's separate occupancies) and names
    its flag for a building of two or more groups; Group E's flag never sends a building of two or more groups to the
    voice/alarm rule, which isn't applicable there; and the review pins of parts a and b, which a rewrite of this file
    once dropped, are all here."""
    reason = labels["907.2.1.1"]["reason"]
    assert "per room" in reason and "general.bc_907_2_1_1_mixed_voice_alarm" in reason and "per story" not in reason
    note = _shown_note(_rule(book, "general.bc_907_2_3_group_e_manual_fire_alarm"))
    assert "in a building of two or more groups it is this check" in note
    for name in ("test_part_bs_label_reasons_name_their_own_group_and_limits", "test_the_grandstands_flag_shows_for_a_school",
                 "test_the_room_rules_fail_only_where_both_occupant_load_readings_reach_the_limit",
                 "test_the_separation_thresholds_are_decided_with_the_groups_not_stated",
                 "test_the_13r_flag_says_what_chapter_10_counts", "test_no_rule_passes_on_a_13r_system_outside_group_r",
                 "test_the_vehicle_storage_flags_show_for_every_group"):
        assert name in globals(), name


def test_the_group_e_rules_reason_keeps_its_exception_to_areas_below_exit_discharge(book):
    """Part b review round 3: 903.2.3's exception (every classroom with an exterior exit door at ground level) lifts the
    requirement only "in any area below the lowest level of exit discharge serving that area" (p.270 lines 29-30), never
    for a Group E fire area on a floor above it; the review reason says so."""
    reason = _rule(book, "general.bc_903_2_3_group_e_sprinklers")["review_when"][0]["reason"]
    assert "below the lowest level of exit discharge" in reason


def test_part_ds_review_round_1(book, ctx):
    """Part d review round 1: 907.2.11.8's portable alarms are for every hotel, motel and lodging house, and a
    nontransient hotel or motel is Group R-2 (310.3); 907.5.2.2's design flags show in a building of two or more groups
    though the whole building states no voice/alarm system (907.2.1.1 may require one for a part); the fire alarm and
    smoke alarm notes keep every condition their exceptions carry."""
    allowed = ctx.allowed()
    hotel = _rule(book, "general.bc_907_2_11_8_portable_smoke_alarms")
    assert outcome(hotel, code_scope.building_measures({"occupancy_groups": ["R-2"]}), allowed) == "needs_review"
    mixed = code_scope.building_measures({"occupancy_groups": ["A-2", "B"], "emergency_voice_alarm_system": False})
    for k in ("voice_alarm_design", "1_voice_alarm_override", "2_voice_alarm_live_messages", "3_voice_alarm_other_uses",
              "4_voice_alarm_captions", "5_voice_alarm_standby_power"):
        assert outcome(_rule(book, f"general.bc_907_5_2_2_{k}"), mixed, allowed) == "needs_review", k
    for rid in ("general.bc_907_2_8_1_group_r1_fire_alarm", "general.bc_907_2_9_1_group_r2_fire_alarm"):
        assert "attic and crawl spaces" in _shown_note(_rule(book, rid)) and "common areas" in _shown_note(_rule(book, rid))
    assert "leading directly to the exits" in _shown_note(_rule(book, "general.bc_907_2_9_1_group_r2_fire_alarm"))
    assert "leading directly to an exit" in _shown_note(_rule(book, "general.bc_907_2_9_3_group_r2_college_detection"))
    two = _shown_note(_rule(book, "general.bc_907_2_11_2_group_r_smoke_alarm_locations"))
    assert "crawl spaces" in two and "upper-floor" in two and "prevent a required alarm" in two
    assert "prevent a required alarm" in _shown_note(_rule(book, "general.bc_907_2_11_1_group_r1_smoke_alarm_locations"))


ANY_STANDPIPE = {"general.bc_905_3_6_marina_standpipes", "general.bc_905_3_7_roof_garden_standpipes", "general.bc_905_4_class_i_hose_connections",
                 "general.bc_905_4_1_standpipe_protection", "general.bc_905_4_2_standpipe_interconnection"}


def test_part_es_standpipe_flags_follow_905_3s_exceptions(book, ctx):
    """Part e: 905.3's exceptions leave standpipe systems out of Group R-3 and Group R-2 townhouses only; every other
    building, a Group R-2 whose units aren't stated townhouse units among them, sees the standpipe flags; 909.20's
    smokeproof enclosures and 911.1's fire command center are a person's check for every building (their triggers are
    heights above the fire department's access the model doesn't show)."""
    allowed = ctx.allowed()
    standpipes = [r for r in book if r["id"].startswith("general.bc_905_") and r["id"] != "general.bc_905_3_2_group_a_standpipes"
                  and r["id"] not in ANY_STANDPIPE]
    assert len(standpipes) == 5
    for r in standpipes:
        def got(b):
            return outcome(r, code_scope.building_measures(b), allowed)
        assert got({"occupancy_groups": ["R-3"]}) == "not_applicable", r["id"]
        assert got({"occupancy_groups": ["R-2"], "townhouse_units": True, "separate_means_of_egress": True}) == \
            "not_applicable", r["id"]
        for b in ({"occupancy_groups": ["R-2"]}, {"occupancy_groups": ["R-2"], "townhouse_units": False},
                  {"occupancy_groups": ["B"]}, {}):
            assert got(b) == "needs_review", (r["id"], b)
    assert "four or more stories" in _shown_note(_rule(book, "general.bc_905_3_1_class_iii_by_height"))
    for r in book:
        if r["id"].startswith(("general.bc_909_", "general.bc_911_")):
            assert "applies_when" not in r and outcome(r, {}, allowed) == "needs_review", r["id"]


def test_a_verification_flag_names_the_comparison_its_second_reading_records():
    """Part e review round 1's class: a second-reading flag that says "the second reading is right" quotes each number
    with the comparison that reading records for it ('four' (<=) is 905.3.1's "four vehicles or less", not its "four or
    more stories"), so the record a person reads says which number on the page differs."""
    import yaml
    tv = yaml.safe_load((NY / "text_verification.yaml").read_text(encoding="utf-8"))["pieces"]
    checked, bad = 0, []
    for pid, e in tv.items():
        nums, cmps = e.get("numbers") or [], e.get("second_reading_comparisons")
        if not cmps:
            continue
        for flag in e.get("flags") or []:
            for part in re.split(r"(?<=\.) (?=')", flag):
                if "second reading is right" not in part:
                    continue
                for n, c in re.findall(r"'([^']+)' \((<=|>=|<|>|none)\)", part):
                    hit = [i for i, x in enumerate(nums) if x == n or x.endswith(" " + n)]
                    if hit:
                        checked += 1
                        if not any(cmps[i] == c for i in hit):
                            bad.append((pid, n, c, [cmps[i] for i in hit]))
    assert checked >= 100 and not bad, bad
    assert "loading docks" in " ".join(tv["905.3.1"]["flags"])


def test_part_es_review_round_1(book, ctx):
    """Part e review round 1: a Group R-2 building is a townhouse (905.3's exception) only where its units are
    townhouse units with a separate means of egress (BCNYS 202), so stating townhouse units with no separate means of
    egress, or leaving it unstated, keeps the standpipe flags; 905.3.1's exception 5 needs the fire department not to use
    the hose lines too, and its heights are from the lowest and highest levels of access; 905.3.3's flow is while the
    sprinklers are supplied; 909.20.3.3's opening is the natural ventilation's; 909.20's notes give 1023.12's three
    sections."""
    allowed = ctx.allowed()
    for r in book:
        if r["id"].startswith("general.bc_905_") and r["id"] not in ANY_STANDPIPE | {"general.bc_905_3_2_group_a_standpipes"}:
            def got(b):
                return outcome(r, code_scope.building_measures(b), allowed)
            assert got({"occupancy_groups": ["R-2"], "townhouse_units": True, "separate_means_of_egress": True}) == \
                "not_applicable", r["id"]
            for b in ({"occupancy_groups": ["R-2"], "townhouse_units": True, "separate_means_of_egress": False},
                      {"occupancy_groups": ["R-2"], "townhouse_units": True}):
                assert got(b) == "needs_review", (r["id"], b)
    n = _shown_note(_rule(book, "general.bc_905_3_1_class_iii_by_height"))
    assert "trained personnel or the fire department" in n and "lowest level of fire department vehicle access" in n
    assert "the highest" in n and "finding the lowest level of access" in n
    n = _shown_note(_rule(book, "general.bc_905_3_3_mall_standpipes"))
    assert "sprinkler system's demand" in n and "residual pressure loss at that flow" in n
    r = _rule(book, "general.bc_909_20_3_3_smokeproof_vestibule_ventilation")
    assert "naturally ventilated" in r["title"] and "ventilated by natural means" in _shown_note(r)
    notes = _rule(book, "general.bc_909_20_smokeproof_enclosures")["notes"]
    assert "403.5.4" in notes and "405.7.2" in notes and "412.2.2.1" in notes and "exit discharge" in notes
    for r in book:
        if r["id"].startswith(("general.bc_905_", "general.bc_909_", "general.bc_911_")):
            pid = re.match(r"general\.bc_(\d+(?:_\d+)*)_", r["id"]).group(1).replace("_", ".")
            assert f"{pid}: {pid}:" not in r["notes"], r["id"]


def test_part_ds_review_round_2(book):
    """Part d review round 2: Group I's notes keep their exceptions' conditions (boxes at exits only where at all care
    providers' control stations or other constantly attended locations; door-closers' detectors on the unit sides,
    installed per their listing, performing the alerting function), and the smoke alarm notes their reliefs (a hallway
    serving bedrooms, garages excluded from a level's area)."""
    i = _shown_note(_rule(book, "general.bc_907_2_6_group_i_fire_alarm"))
    assert "all care providers' control stations" in i and "at exits" in i
    i2 = _shown_note(_rule(book, "general.bc_907_2_6_2_group_i2_smoke_detection"))
    assert "required alerting function" in i2 and "unit sides" in i2 and "audible and visual alarm" in i2
    for rid in ("general.bc_907_2_11_1_group_r1_smoke_alarm_locations", "general.bc_907_2_11_2_group_r_smoke_alarm_locations"):
        n = _shown_note(_rule(book, rid))
        assert "serving bedrooms" in n and "garages excluded" in n and "clearly audible" in n, rid


LABEL_COPIES_NOTE = ("907.2.6", "907.2.7", "907.2.8", "907.2.9", "907.2.10", "907.2.11", "907.5.2.2", "905.3", "905.4",
                     "909.1", "909.20", "911.1")


def test_part_ds_review_round_3(book):
    """Part d review round 3: the label reasons of parts d and e are their flags' shown notes word for word (the
    generated review file showed the wording rounds 1 and 2 had fixed in the notes only), and the notes keep every
    condition: letters 3 inches high, not a sign; basements; a bathroom's door or opening; the room a sleeping loft opens
    to; what Group I's exception 2 relieves; I-3's equivalent protection; a commercial source of power."""
    import yaml
    labels = yaml.safe_load(LABELS.read_text(encoding="utf-8"))["labels"]
    rules = {r["id"]: r for r in book}
    checked = 0
    for pid, v in labels.items():
        if v.get("label") != "flag" or not (pid in LABEL_COPIES_NOTE or pid.startswith(tuple(p + "." for p in LABEL_COPIES_NOTE))):
            continue
        rid = re.search(r"\((general\.bc_[a-z0-9_]+)\)\.$", v["reason"]).group(1)
        assert v["reason"] == _shown_note(rules[rid])[:-1] + f" ({rid}).", pid
        checked += 1
    assert checked >= 35
    assert "its letters at least 3 inches high" in _shown_note(rules["general.bc_907_2_11_8_portable_smoke_alarms"])
    for rid in ("general.bc_907_2_11_1_group_r1_smoke_alarm_locations", "general.bc_907_2_11_2_group_r_smoke_alarm_locations"):
        n = _shown_note(rules[rid])
        assert "including basements" in n and "door or opening of a bathroom" in n and "a sleeping loft opens to" in n, rid
    assert "occupant notification needn't be activated" in _shown_note(rules["general.bc_907_2_6_group_i_fire_alarm"])
    i3 = _shown_note(rules["general.bc_907_2_6_3_3_group_i3_smoke_detection"])
    assert "equivalent protection" in i3 and "contiguous day rooms" in i3 and "normally open" in i3
    assert "four or fewer occupants" in i3   # round 4: what exception 3 counts
    assert "served from a commercial source" in _shown_note(rules["general.bc_907_2_11_6_smoke_alarm_power"])


def test_no_line_is_set_aside_by_a_13r_system_outside_group_r(book, ctx):
    """The merge of main (2026-11-27), part a's class carried to every rule and flag: 903.3.1.2 permits an NFPA 13R
    system only in Group R occupancies, so a line whose exception reads "equipped throughout with an automatic
    sprinkler system in accordance with Section 903.3.1.1 or 903.3.1.2" is set aside by a stated 13R system only in a
    building stated Group R. Section group 9c's and 9b's flags (1009.3.2, 1009.3.3, 1009.4.2, 1009.7.2, 1009.7.4,
    1013.2) read the 13R fact alone, so a Group B building with a 13R system lost them. Walked over every line whose
    applies_when reads the 13R fact, every group but R and two buildings of two or more groups: stating a 13R system
    never makes a line not applicable that shows with no system."""
    allowed, wrong, walked = ctx.allowed(), [], 0
    others = [[g] for g in GROUPS if not g.startswith("R-")] + [["M", "R-2"], ["B", "I-1"], ["B", "R-1"]]
    for r in book:
        if not r.get("applies_when") or "sprinklered_903_3_1_2" not in formula.names(r["applies_when"]):
            continue
        for groups in others:
            def got(system):
                return outcome(r, code_scope.building_measures({"occupancy_groups": groups, "sprinkler_system": system}),
                               allowed)
            walked += 1
            if got("nfpa_13r") == "not_applicable" and got("none") != "not_applicable":
                wrong.append((r["id"], groups))
    assert walked > 100 and not wrong, wrong[:8]


def test_part_es_review_round_2(book, ctx):
    """Part e review round 2: 905.3's exceptions say only where standpipes "are not required"; a system not required
    may still be installed and must meet the code (901.2's exception), so the flags that bind any standpipe provided
    (905.3.7's roof gardens, 905.4's hose connections, 905.4.1's protection, 905.4.2's interconnection) show in Group
    R-3 and Group R-2 townhouses too; 909.20.6.1's three ways keep their conditions; 905.3.1's exception 1 is a
    building sprinklered throughout."""
    allowed = ctx.allowed()
    for rid in ANY_STANDPIPE:
        r = _rule(book, rid)
        assert "applies_when" not in r and "901.2" in _shown_note(r), rid
        for b in ({"occupancy_groups": ["R-3"]}, {"occupancy_groups": ["R-2"], "townhouse_units": True,
                                                  "separate_means_of_egress": True}, {}):
            assert outcome(r, code_scope.building_measures(b), allowed) == "needs_review", (rid, b)
    n = _shown_note(_rule(book, "general.bc_909_20_6_1_ventilation_systems"))
    assert "connected to the enclosure directly or by ductwork enclosed by 2-hour" in n
    assert "its intake or exhaust directly from and to the outside" in n and "other mechanical equipment included" in n
    assert "sprinklered throughout with a 903.3.1.1" in _shown_note(_rule(book, "general.bc_905_3_1_class_iii_by_height"))


def test_the_townhouse_unit_is_quoted_as_the_book_prints_it():
    """The merge review of Chapter 9 part e (round 3, P3): BCNYS 202 TOWNHOUSE UNIT reads "a yard or public way on not
    fewer than two sides, and has a separate means of egress" (p.65, lines 5-6); the townhouse fact's meaning and the
    definition's second-reading flag had "not less than", the house code's (R202) words."""
    import yaml
    measures = yaml.safe_load((NY / "5_building_code_rules/drafted/records/proposed_measures.yaml").read_text(encoding="utf-8"))
    meaning = " ".join(measures["townhouse_units"]["meaning"].split())
    assert "not fewer than two sides" in meaning and "separate means of egress" in meaning
    tv = yaml.safe_load((NY / "text_verification.yaml").read_text(encoding="utf-8"))["pieces"]["202:townhouse_unit"]
    assert "not fewer than two sides" in " ".join(tv["flags"]) and "not less than" not in " ".join(tv["flags"])


def test_part_es_review_round_3(book, ctx):
    """Part e review round 3: each note keeps its piece's conditions (905.3.2's dry standpipes are automatic or
    semiautomatic; 905.3.1's basements and 905.3.3's pressure loss in full; 909.20.5.2's stack pressures; 909.20.6's
    approved location; 905.4's fire code official and its hose-reach exception for horizontal exits too); the doors of
    909.20.3 and 909.20.5 say which of the two ways they belong to; the flags binding any standpipe say so first; and
    905.3.6's marinas bind whatever standpipes are there (901.2)."""
    def n(rid):
        return _shown_note(_rule(book, rid))
    assert "Class I automatic dry, semiautomatic dry or manual wet" in n("general.bc_905_3_2_group_a_standpipes")
    assert "basements sprinklered throughout" in n("general.bc_905_3_1_class_iii_by_height")
    assert "to the hydraulically most remote hose connection" in n("general.bc_905_3_3_mall_standpipes")
    assert "maximum anticipated stack pressures" in n("general.bc_909_20_5_2_pressure_difference")
    assert "at an approved location" in n("general.bc_909_20_6_ventilating_equipment")
    h = n("general.bc_905_4_class_i_hose_connections")
    assert "unless the fire code official approves otherwise" in h and "horizontal exit's wall and in every exit passageway" in h
    for rid in ("general.bc_909_20_3_1_smokeproof_balcony_doors", "general.bc_909_20_3_2_smokeproof_vestibule_doors"):
        assert n(rid).startswith("In a smokeproof enclosure ventilated by natural means (909.20.3)"), rid
    for rid in ("general.bc_909_20_5_1_pressurized_vestibule_doors", "general.bc_909_20_5_2_pressure_difference"):
        assert n(rid).startswith("In a pressurized stair and vestibule (909.20.5)"), rid
    for rid in ("general.bc_905_4_class_i_hose_connections", "general.bc_905_4_1_standpipe_protection"):
        assert n(rid).startswith("Where a Class I or Class III standpipe system is installed (Class III through 905.6"), rid
    assert outcome(_rule(book, "general.bc_905_3_6_marina_standpipes"),
                   code_scope.building_measures({"occupancy_groups": ["R-3"]}), ctx.allowed()) == "needs_review"


def test_a_line_a_13r_system_doesnt_spare_says_why(book):
    """The merge review (2026-11-27): a flag set aside by a 903.3.1.1 or 903.3.1.2 system shows where a stated 13R
    system doesn't count (outside Group R, or above 903.3.1.2's four stories), so its words must say why, as 716.2.2.3's
    do; each has worked examples for 13R in and outside Group R."""
    guarded = [r for r in book if r["kind"] == "flag" and "sprinklered_903_3_1_2 and occupancy_group in" in
               " ".join(str(r.get("applies_when", "")).split())]
    assert len(guarded) >= 7
    for r in guarded:
        if r["id"] == "general.bc_716_2_2_3_exit_enclosure_door_temperature_rise":
            continue
        assert "a 13R system counts only in Group R, within 903.3.1.2's four stories, and in Group I-1 Condition 1" in _shown_note(r), r["id"]
        kinds = {(str(e["given"].get("occupancy_group", "")).startswith("R-"), e["expect"]) for e in r["examples"]
                 if e["given"].get("sprinklered_903_3_1_2") is True and not e["given"].get("sprinklered_903_3_1_1")}
        assert (True, "not_applicable") in kinds and (False, "needs_review") in kinds, r["id"]
