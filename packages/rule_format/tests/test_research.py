"""Show your work: an open question carries the research behind it, and a settled one its finding.

Checked by code on rules, definitions and section labels alike (all three go through _approval_problems), with
the real Ithaca text, so a quote in a finding is verified like a rule's."""

import copy

import pytest

import re

from rule_format.rulebook import (REPO, Context, finding_conflicts, load, pending_research, research_entries,
                                  research_problems, validate_terms)

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
REPORT = "docs/research/2026-10-20_architect_questions.md"
Q = "Is a yard measured to the wall or to the eave?"
EAVES = {"file": "chapter_325_zoning_2026-10.pdf", "page": 49, "lines": [15, 16],
         "quote": "such features shall not project more than two feet into any required yard"}
BZA = {"rank": 2, "cite": "BZA, ZONE-25-12, 132 Cherry St (2026)",
       "url": "https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_03032026-3164"}
RESEARCH = {"question": Q, "searched": ["325-18B", "325-3B:side_yard"], "sources": [EAVES],
            "why_open": "The code says eaves may project 2 ft, not where the yard is measured to.",
            "readings": [{"id": "to_wall", "reading": "to the wall"}, {"id": "to_eave", "reading": "to the eave"}],
            "report": f"{REPORT} §2.1"}
LAW = {"id": "yards_to_nearest_part", "question": Q, "kind": "law", "answer": "To the nearest part; eaves 2 ft.",
       "sources": [EAVES], "strength": "strong", "report": f"{REPORT} §2.1"}
READING = {"id": "steps_count", "question": "Do steps count?", "kind": "reading", "answer": "Yes.",
           "sources": [BZA], "strength": "city_practice", "confirm_with": "the City zoning office"}


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(ITHACA)


def problems(ctx, **entry):
    return research_problems(entry, ctx)


def test_an_open_question_without_research_is_refused_with_a_clear_message(ctx):
    found = problems(ctx, open_questions=[Q])
    assert len(found) == 1 and "needs exactly one 'research' entry" in found[0] and "why_open" in found[0]
    assert problems(ctx, open_questions=[Q], research=[RESEARCH]) == []
    assert problems(ctx, open_questions=[Q], research=[RESEARCH, RESEARCH])          # one per question


def test_nothing_searched_is_allowed_only_while_it_says_pending(ctx):
    empty = RESEARCH | {"searched": [], "readings": []}
    assert any("lists no sections" in p for p in problems(ctx, open_questions=[Q], research=[empty]))
    pending = pending_research(Q, "raised by the drafting script")
    assert pending["why_open"].startswith("pending") and problems(ctx, open_questions=[Q], research=[pending]) == []


def test_open_questions_of_the_wrong_shape_get_one_message_not_one_per_letter(ctx):
    assert research_problems({"open_questions": "why?"}, ctx) == []      # open_question_problems says it's not a list


def test_searched_sections_must_exist(ctx):
    bad = RESEARCH | {"searched": ["325-18B", "325-99Z"]}
    assert any("don't exist: 325-99Z" in p for p in problems(ctx, open_questions=[Q], research=[bad]))


def test_research_on_a_question_that_isnt_open_is_refused(ctx):
    assert any("isn't one of the open questions" in p for p in problems(ctx, research=[RESEARCH]))


def test_readings_still_in_play_are_two_or_more_with_names_measurement_code_can_use(ctx):
    for readings, message in [([{"id": "to_wall", "reading": "to the wall"}], "one reading isn't open"),
                              ([{"id": "Wall", "reading": "x"}, {"id": "eave", "reading": "y"}], "lowercase"),
                              ([{"id": "a", "reading": "x"}, {"id": "a", "reading": "y"}], "used once")]:
        assert any(message in p for p in problems(ctx, open_questions=[Q], research=[RESEARCH | {"readings": readings}]))


def test_an_answer_from_the_law_quotes_the_law_exactly(ctx):
    assert problems(ctx, findings=[LAW]) == []
    assert any("quotes the law" in p for p in problems(ctx, findings=[LAW | {"sources": [BZA]}]))
    moved = LAW | {"sources": [EAVES | {"lines": [20, 21]}]}
    assert any("quote isn't at lines 20-21" in p for p in problems(ctx, findings=[moved]))
    assert any("a weaker one is a reading" in p for p in problems(ctx, findings=[LAW | {"strength": "moderate"}]))


def test_a_reading_is_no_stronger_than_its_best_source_and_says_who_confirms_it(ctx):
    assert problems(ctx, findings=[READING]) == []
    assert any("stronger than its best source (rank 2" in p
               for p in problems(ctx, findings=[READING | {"strength": "strong"}]))
    assert problems(ctx, findings=[READING | {"strength": "weak"}]) == []            # weaker than its source: fine
    assert any("strength" in p for p in problems(ctx, findings=[READING | {"strength": "likely"}]))
    no_one = {k: v for k, v in READING.items() if k != "confirm_with"}
    assert any("who should confirm it" in p for p in problems(ctx, findings=[no_one]))
    assert any("rank must be 2, 3 or 4" in p for p in problems(ctx, findings=[READING | {"sources": [BZA | {"rank": 1}]}]))
    assert any("https://" in p for p in problems(ctx, findings=[READING | {"sources": [BZA | {"url": "cityofithaca"}]}]))


def test_a_question_is_open_or_found_not_both(ctx):
    found = problems(ctx, open_questions=[Q], research=[RESEARCH], findings=[LAW])
    assert any("open or found, not both" in p for p in found)
    assert any("used once" in p for p in problems(ctx, findings=[LAW, LAW | {"question": "another?"}]))


def test_the_report_and_its_section_must_exist(ctx):
    assert any("must name a research report" in p
               for p in problems(ctx, findings=[LAW | {"report": "docs/research/missing.md §2.1"}]))
    assert any("has no section 9.9" in p for p in problems(ctx, findings=[LAW | {"report": f"{REPORT} §9.9"}]))


def test_definitions_are_checked_too(ctx):
    definitions = copy.deepcopy(load(ITHACA / "4_term_definitions/definitions.yaml"))
    assert validate_terms(definitions, ctx, "definitions") == []
    del definitions["lot"]["research"]
    assert any("lot: open question" in p and "'research'" in p for p in validate_terms(definitions, ctx, "definitions"))


# ---- the filed research (2026-10-20) ----------------------------------------------------------------------

def entries():
    yield from load(ITHACA / "4_term_definitions/definitions.yaml").items()
    yield from ((r["id"], r) for r in load(ITHACA / "5_zoning_rules/R-1b.yaml")["rules"])
    yield from load(ITHACA / "3_section_labels/chapter_325_zoning_2026-10.yaml")["labels"].items()


def test_every_open_question_was_researched_and_none_is_pending():
    """The 2026-10-20 pass researched every question then open: none is left pending, and every one names the
    sections read, its report section and why it is still open."""
    research = [x for _, e in entries() for x in e.get("research", [])]
    assert len(research) == sum(len(e.get("open_questions", [])) for _, e in entries()) == 19
    assert all(x["searched"] and not x["why_open"].startswith("pending") and x["report"].startswith(REPORT)
               for x in research)


def test_the_eaves_rule_settles_where_yards_are_measured_to():
    """The question once sent to the architects is answered by §325-18B, quoted."""
    found = {f["id"]: f for _, e in entries() for f in e.get("findings", [])}
    yards = found["yards_to_nearest_part"]
    assert yards["kind"] == "law" and any(s.get("page") == 49 and "two feet" in s.get("quote", "") for s in yards["sources"])
    assert found["perpendicular_lot_depth"]["strength"] == "city_practice"
    assert found["adu_needs_no_parking"]["kind"] == "law"


# ---- review round 1 (2026-10-20): what research may claim -------------------------------------------------

NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
                "nine": "9", "ten": "10", "twelve": "12"}


def claims(text: str) -> set[str]:
    """The numbers (spelled or not) and district names a text states, leaving out references (sections, pages,
    chart columns, list markers): those say where words are, not what they say."""
    text = re.sub(r"§\s*[\w.\-()\[\]]+|\bp\.\s*\d+|\bColumns? \d+|\(\d\)", " ", text)
    words = {NUMBER_WORDS[w.lower()] for w in re.findall(r"[A-Za-z]+", text) if w.lower() in NUMBER_WORDS}
    return words | set(re.findall(r"\b[A-Z]{1,2}-\d+[a-z]*\b", text)) | \
        {n for n in re.findall(r"(?<![\w-])\d+(?:\.\d+)?", text)}


def test_a_law_answer_states_no_number_or_district_its_quotes_dont():
    """An answer filed as the law says nothing its quotes don't: every number and district name in it is in one of
    its quotes from the code. (The height-bonus answer once said "the bonus doesn't apply in U-1"; the code says
    the bonus's limits don't apply there, and no quote said U-1.)"""
    for where, e in entries():
        for f in e.get("findings") or []:
            if f["kind"] == "law":
                quoted = set().union(*(claims(s["quote"]) for s in f["sources"] if "file" in s))
                assert claims(f["answer"]) <= quoted, (where, f["id"], claims(f["answer"]) - quoted)


def test_the_height_bonus_answer_keeps_u1_to_what_the_code_says():
    bonus = next(f for _, e in entries() for f in e.get("findings") or [] if f["id"] == "height_bonus_main_building_only")
    assert "U-1" not in bonus["answer"]


def test_no_finding_settles_what_an_open_question_still_asks(ctx):
    """The 12 ft story test was filed as the law while story's open question still asked whether "computed at the
    main entrance side" overrides "at any point", and basement kept the same words open."""
    assert finding_conflicts(research_entries(ITHACA)) == []
    story = next(e for w, e in entries() if w == "story")
    assert not [f for f in story.get("findings") or [] if f["kind"] == "law" and "at any point" in
                " ".join(s.get("quote", "") for s in f["sources"])]
    readings = {g["id"] for x in story["research"] for g in x.get("readings") or []}
    assert {"any_side", "main_entrance_side_only"} <= readings


OPEN = {"open_questions": ["Bay windows?"], "research": [{"question": "Bay windows?", "sources": [EAVES]}]}


def test_a_finding_touching_an_open_question_anywhere_must_name_it():
    """Quoted words or shared cited lines, in the same entry or another one: the finding names the open question in
    still_open (a real one), and says in its answer what is still open."""
    law = {"findings": [{"id": "f", "kind": "law", "answer": "Up to 2 ft.", "sources": [EAVES]}]}
    words = {"open_questions": ['Is "not project more than two feet" measured to the wall?']}
    assert any("quotes 'not project more than two feet'" in p for p in finding_conflicts([("a x", law), ("b y", words)]))
    found = finding_conflicts([("a x", law), ("b y", OPEN)])                          # another entry, same lines
    assert any("cites p.49 lines 15-16, which the research on open question y#1 cites" in p for p in found)
    reading = {"findings": [law["findings"][0] | {"kind": "reading"}]}
    assert finding_conflicts([("a x", reading), ("b y", OPEN)])                       # a reading too
    named = {"findings": [law["findings"][0] | {"still_open": ["y#1"], "answer": "Up to 2 ft; bay windows still open."}]}
    assert finding_conflicts([("a x", named), ("b y", OPEN)]) == []
    unsaid = {"findings": [named["findings"][0] | {"answer": "Up to 2 ft."}]}
    assert any("answer must say what is still open" in p for p in finding_conflicts([("a x", unsaid), ("b y", OPEN)]))
    wrong = {"findings": [named["findings"][0] | {"still_open": ["y#2"]}]}
    assert any("y#2, which isn't an open question" in p for p in finding_conflicts([("a x", wrong), ("b y", OPEN)]))


def test_in_an_entry_with_open_questions_every_finding_says_which_it_leaves_open():
    """This replaces guessing from words like "eave": the relation is a field, so it can't be forgotten."""
    entry = OPEN | {"findings": [{"id": "f", "kind": "law", "answer": "A.", "sources": []}]}
    assert any("says which of them it leaves open" in p for p in finding_conflicts([("a x", entry)]))
    entry["findings"][0]["still_open"] = []
    assert finding_conflicts([("a x", entry)]) == []


def test_the_side_yard_finding_names_the_r1_question_it_leaves_open():
    """accessory_structures_follow_325_25 cites §325-25C's R-1 clause (p.67), which 325-25C#1 asks about; without
    its still_open the check refuses it."""
    found = research_entries(ITHACA)
    side = next(e for w, e in found if w.endswith(" side_yard"))
    f = next(f for f in side["findings"] if f["id"] == "accessory_structures_follow_325_25")
    assert f["still_open"] == ["325-25C#1"]
    del f["still_open"]
    assert any("accessory_structures_follow_325_25" in p and "325-25C#1" in p for p in finding_conflicts(found))


def test_the_accessory_question_cites_the_r1_clause_that_drops_frame():
    label = next(e for w, e in entries() if w == "325-25C")
    r = label["research"][0]
    assert any(s.get("page") == 67 and s.get("lines") == [7, 8] for s in r["sources"])
    assert "r1_distances_apply_to_all_accessory_buildings" in {g["id"] for g in r["readings"]}


def test_each_findings_sources_are_about_that_finding():
    """The #3093 garage-coverage sentence once backed the side-yard and corner-lot findings too."""
    found = {f["id"]: f for _, e in entries() for f in e.get("findings") or []}
    def yates(fid):
        return [s["quote"] for s in found[fid]["sources"] if "Yates" in s.get("cite", "")]
    assert yates("accessory_structures_follow_325_25") and all("side yard" in q for q in yates("accessory_structures_follow_325_25"))
    assert yates("corner_lot_side_yard_column_13") and all("Column 13" in q for q in yates("corner_lot_side_yard_column_13"))
    assert all("lot coverage" in q for q in yates("garages_count"))


def test_a_note_never_says_open_question_once_none_is_open():
    for where, e in entries():
        if not e.get("open_questions"):
            assert "open question" not in str(e.get("notes", "")).lower(), where


def test_an_answer_may_only_pick_one_of_its_questions_readings_or_a_finding():
    """Review round 1: an answer's `reading` names one of its question's research readings, or a finding of the
    entry; anything else (a typo) is refused, so an answer is never silently ignored."""
    import datetime

    from rule_format.rulebook import REPO, Context, _answer_problems
    ctx = Context.for_jurisdiction(REPO / "regulations/jurisdictions/new_york/ithaca_city")
    entry = {"research": [{"question": "Which eave?", "readings": [{"id": "wall_plate", "reading": "w"},
                                                                   {"id": "drip_edge", "reading": "d"}]}],
             "findings": [{"id": "pitched_roof_midpoint", "question": "Midpoint?"}]}
    ctx.reviewers = {"the City zoning office"}
    who = "the City zoning office"
    base = {"question": "Which eave?", "answer": "x", "answered_by": who, "answered_on": datetime.date(2026, 11, 1)}
    assert _answer_problems([{**base, "reading": "wall_plate"}], ctx, entry) == []
    # a finding may be picked only by an answer to its own question (round 2)
    assert _answer_problems([{**base, "reading": "pitched_roof_midpoint"}], ctx, entry)
    assert _answer_problems([{**base, "question": "Midpoint?", "reading": "pitched_roof_midpoint"}], ctx, entry) == []
    assert _answer_problems([{**base, "reading": "wall_plat"}], ctx, entry)
