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
            assert mine and {r["kind"] for r in mine} == {v["label"]}, pid


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
        if v["label"] != "flag":
            continue
        for r in _own(book, pid):
            quote = " ".join(s["quote"] for s in r["sources"])
            shown = {m.group(0) for m in TOKEN.finditer(_shown_note(r))}
            missing = sorted(x for x in _refs(quote) - {pid} if x not in shown)
            assert not missing, (r["id"], missing)


def test_every_chapter_9_flag_is_a_persons_check_never_a_pass(labels, book, ctx):
    """A flag has no check, and needs review for every building it isn't narrowed away from; a narrowed one is
    narrowed only by a fact the architect states (the groups, the sprinkler system) and needs review while that fact
    isn't stated."""
    allowed = ctx.allowed()
    by = {"occupancy_group", "group_h_present", "sprinklered_903_3_1_2", "sprinklered_903_3_1_3"}
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