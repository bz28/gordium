"""The rule-by-rule comparison of the drafts with the hand answer keys (evals/2026-10-27_rule_by_rule, queue item 11):
its report is current, every verdict difference has a law decision, and its causes are told apart as described."""

import importlib.util
import re
from pathlib import Path

import pytest

from rule_format.rulebook import REPO, Context, load

HERE = REPO / "packages/rule_drafting/evals/2026-10-27_rule_by_rule"
spec = importlib.util.spec_from_file_location("compare", HERE / "compare.py")


@pytest.fixture(scope="module")
def cmp():
    if not (REPO / "regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/RU.yaml").exists():
        pytest.skip("needs every hand key (PR #30's RU among them) beside the drafts")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def data(cmp):
    return cmp.compare(Context.for_jurisdiction(cmp.te.ITHACA))


def test_the_committed_report_is_the_report_of_this_checkout(cmp, data):
    """report.md is compare.py's output for the drafts and keys here, with the two commits it names."""
    committed = (HERE / "report.md").read_text(encoding="utf-8")
    drafts, keys = re.search(r"at `(\w+)`\. Hand keys: .* at `(\w+)`", committed.replace("\n", " ")).groups()
    assert cmp.report(data, drafts, keys, load(cmp.DECISIONS)) == committed


def test_every_verdict_difference_has_a_law_decision(cmp, data):
    """A drafted verdict that isn't only more cautious is decided by the law: which side matches, quoted, and what was
    done (decisions.yaml); none left undecided, none decided that isn't a difference."""
    verdict = {r["hand"] for k in data["keys"].values() for r in k["rules"] if r["status"] == "verdict"}
    decisions = load(cmp.DECISIONS)
    assert verdict == set(decisions)
    for d in decisions.values():
        assert {"law", "side", "done"} <= set(d)
        assert "§" in d["law"] or "chart" in d["law"]                 # the law quoted, with where it is


def test_no_false_pass_and_the_height_rows_differ_only_where_the_bonus_isnt_drafted(data):
    """With §325-16C's bonus proven where it is drafted, height differs only in R-2c and RU (unresolved there)."""
    assert all(k["summary"].get("false_pass", 0) == 0 for k in data["keys"].values())
    differing = {r["hand"] for k in data["keys"].values() for r in k["rules"]
                 if r["hand"].endswith(".height") and r["status"] != "match"}
    assert differing == {"R-2c.height", "RU.height"}


def test_a_cautious_answer_says_why(cmp):
    """The drafter's to-do: a flag, a review condition that fires, an input the example doesn't give."""
    ctx = Context.for_jurisdiction(cmp.te.ITHACA)
    assert cmp.cause({"kind": "flag", "applies_when": "use == \"church\""}, {"use": "church"}, ctx).startswith(
        "drafted as a flag")
    rule = {"kind": "rule", "check": "lot_area >= 6000",
            "review_when": [{"when": "lot_area < 7000", "reason": "Close to the line. More words."}]}
    assert cmp.cause(rule, {"lot_area": 6500}, ctx) == "a review condition fires: Close to the line"
    assert cmp.cause({"kind": "rule", "check": "stories <= 3 and building_height <= 35"}, {"stories": 2}, ctx) == (
        "reads an input the key's example doesn't give: building_height")
    assert cmp.kind_of("pass", "needs_review") == "cautious" and cmp.kind_of("pass", "fail") == "verdict"
