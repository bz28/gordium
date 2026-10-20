"""docs/how_gordium_is_built.md is the 'start here' guide, so it must match what this branch contains: every
package is named, and a step whose output exists isn't marked 'Later'. The questions page claims only what
the code does."""

import re

from rule_format.rulebook import MEASURES_FILE, REPO, load

GUIDE = (REPO / "docs/how_gordium_is_built.md").read_text(encoding="utf-8")
ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"


def _row(step: str) -> str:
    return next(line for line in GUIDE.splitlines() if line.startswith(f"| {step}"))


def test_the_guide_names_every_package():
    packages = [p.name for p in (REPO / "packages").iterdir() if (p / p.name).is_dir()]
    assert packages and not [p for p in packages if f"`{p}" not in GUIDE]


def test_a_step_whose_output_exists_is_not_marked_later():
    outputs = {"3. Pieces and labels": list((ITHACA / "3_section_labels").glob("*.yaml")),
               "6. Coverage report": list((ITHACA / "6_coverage_report").glob("*.md"))}
    for step, found in outputs.items():
        if found:
            assert not _row(step).rstrip(" |").endswith("Later"), step


def test_the_questions_page_claims_no_main_or_accessory_distinction_the_code_lacks():
    """§4.5: nothing tells a main building from an accessory one, so the page may not say the bonus is
    limited to the main building as something Gordium enforces."""
    if any(re.search("accessory|main_building", m) for m in load(MEASURES_FILE)):
        return
    doc = (REPO / "docs/questions_for_architects.md").read_text(encoding="utf-8")
    assert "the bonus is for the main building only" not in doc


def test_the_guide_says_who_drafted_r1b_and_that_it_is_not_yet_an_answer_key():
    """Every R-1b rule records drafted_by: claude and none is approved, so the start-here guide may not call
    it hand-drafted or present it as an answer key already (principle 5: who drafted is traceable)."""
    rules = load(ITHACA / "5_zoning_rules/R-1b.yaml")["rules"]
    pr5 = next(line for line in GUIDE.splitlines() if line.startswith("| 5 |"))
    step5 = _row("5. Rules")
    if all(r.get("drafted_by") == "claude" for r in rules):
        assert "by hand" not in pr5 + step5 and "Claude" in pr5 and "Claude" in step5
    if not any(r.get("status") == "approved" for r in rules):
        assert "answer key once" in pr5


def test_side_branches_are_marked_and_none_joins_through_another():
    """PRs whose work isn't in this branch are marked side branches, and no row says a side branch reaches
    the main line through another side branch."""
    rows = [line for line in GUIDE.splitlines() if re.match(r"\| \d+ \|", line)]
    assert all("joins the main line through" not in r for r in rows)
    if not (REPO / ".github/pull_request_template.md").exists():
        assert "side branch" in next(r for r in rows if r.startswith("| 2 |"))
    if not (REPO / "packages/document_extraction/document_extraction/charts.py").exists():
        assert "side branch" in next(r for r in rows if r.startswith("| 6 |"))
