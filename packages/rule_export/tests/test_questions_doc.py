"""docs/questions_for_architects.md is the complete list of what the architects must answer: every open question
recorded anywhere (the same list as the workbook's Questions tab) is cited there by its tag, `[<id>#<n>]`, the
n-th open question of that rule, definition or label; and every result-changing (🔴) item in
docs/discrepancies_with_architects.md is cited as `[discrepancy <number>]`. A question added, answered or
renumbered without updating the page fails here, so the page can't silently fall behind the files."""

import re
from collections import Counter

from rule_export.workbook import tables
from rule_format.rulebook import REPO

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
DOC = (REPO / "docs/questions_for_architects.md").read_text(encoding="utf-8")
DISCREPANCIES = (REPO / "docs/discrepancies_with_architects.md").read_text(encoding="utf-8")


def recorded_questions() -> list[str]:
    """`<id>#<n>` for every open question, in the Questions tab's order (the one list of them)."""
    seen, tags = Counter(), []
    for row in tables(ITHACA)["Questions"]["rows"]:
        seen[row[2]] += 1
        tags.append(f"{row[2]}#{seen[row[2]]}")
    return tags


def test_every_recorded_question_is_on_the_page_and_nothing_else():
    cited = re.findall(r"`\[([^\]`\s]+#\d+)\]`", DOC)
    recorded = recorded_questions()
    assert len(recorded) == len(set(recorded))
    assert sorted(set(recorded) - set(cited)) == [], "open questions missing from docs/questions_for_architects.md"
    assert sorted(set(cited) - set(recorded)) == [], "the page cites questions no file records (answered or renumbered?)"
    assert [t for t, n in Counter(cited).items() if n > 1] == [], "each question is cited once"


def test_every_result_changing_discrepancy_is_on_the_page():
    red = {m for m in re.findall(r"^\| (\d+\.\d+) \|.*🔴", DISCREPANCIES, re.M)}
    cited = set(re.findall(r"\[discrepancy (\d+\.\d+)\]", DOC))
    assert red, "the discrepancies table format changed; update this test"
    assert sorted(red - cited) == [] and sorted(cited - red) == []
