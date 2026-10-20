"""Show your work: an open question carries the research behind it, and a settled one its finding.

Checked by code on rules, definitions and section labels alike (all three go through _approval_problems), with
the real Ithaca text, so a quote in a finding is verified like a rule's."""

import copy

import pytest

from rule_format.rulebook import REPO, Context, load, pending_research, research_problems, validate_terms

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
    assert len(research) == sum(len(e.get("open_questions", [])) for _, e in entries()) == 18
    assert all(x["searched"] and not x["why_open"].startswith("pending") and x["report"].startswith(REPORT)
               for x in research)


def test_the_eaves_rule_settles_where_yards_are_measured_to():
    """The question once sent to the architects is answered by §325-18B, quoted."""
    found = {f["id"]: f for _, e in entries() for f in e.get("findings", [])}
    yards = found["yards_to_nearest_part"]
    assert yards["kind"] == "law" and any(s.get("page") == 49 and "two feet" in s.get("quote", "") for s in yards["sources"])
    assert found["perpendicular_lot_depth"]["strength"] == "city_practice"
    assert found["adu_needs_no_parking"]["kind"] == "law"
