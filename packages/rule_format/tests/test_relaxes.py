"""`relaxes: <rule id>`: an exception that widens another rule (rule_format README, "An exception that widens a
rule"). The relaxed rule passes if its own check passes, or if a relaxing rule applies (all its conditions met) and
passes its own check; never otherwise."""
import copy
import itertools
import sys
from pathlib import Path

import yaml

from rule_format.rulebook import apply_relaxes, outcome, validate, zone_rules

sys.path.insert(0, str(Path(__file__).parent))
from test_rulebook import CTX, RULE  # noqa: E402

# The hand R-1b height rule (5_zoning_rules/R-1b.yaml): the chart's 35 ft and the §325-16C bonus in one formula.
COMBINED = {"id": "R-1b.height", "kind": "rule", "check": (
    "building_height <= 35 or building_height <= 35 + 0.1 * 35"
    " and front_yard >= 25 + (building_height - 35)"
    " and side_yard_smaller >= 10 + (building_height - 35)"
    " and side_yard_larger >= 10 + (building_height - 35)"
    " and rear_yard >= max(min(0.25 * lot_depth, 50), 20) + (building_height - 35)")}
# The same law as two rules: the chart's limit, and the bonus relaxing it when every yard is increased.
BASE = {"id": "R-1b.height_chart", "kind": "rule", "check": "building_height <= 35"}
BONUS = {"id": "R-1b.height_bonus", "kind": "rule", "relaxes": "R-1b.height_chart",
         "applies_when": ("front_yard >= 25 + (building_height - 35)"
                          " and side_yard_smaller >= 10 + (building_height - 35)"
                          " and side_yard_larger >= 10 + (building_height - 35)"
                          " and rear_yard >= max(min(0.25 * lot_depth, 50), 20) + (building_height - 35)"),
         "check": "building_height <= 35 + 0.1 * 35"}
GRID = {"building_height": [None, 30, 35, 35.5, 36, 38.5, 38.6, 41],
        "front_yard": [None, 25, 26, 28.5],
        "side_yard_smaller": [None, 10, 11, 13.5],
        "side_yard_larger": [None, 10.5, 13.5],
        "rear_yard": [None, 20, 26, 28.5, 53.5],
        "lot_depth": [None, 60, 104, 200, 250]}


def designs():
    for combo in itertools.product(*GRID.values()):
        yield {k: v for k, v in zip(GRID, combo) if v is not None}


def test_the_hand_r1b_height_and_its_relaxes_version_give_the_same_verdict_for_every_design():
    relaxed = {r["id"]: r for r in apply_relaxes([BASE, BONUS])}["R-1b.height_chart"]
    seen = set()
    for values in designs():
        want = outcome(COMBINED, values, {})
        assert outcome(relaxed, values, {}) == want, values
        seen.add(want)
    assert seen == {"pass", "fail", "needs_review"}           # the grid reaches every verdict


def test_a_relaxing_rule_widens_only_when_all_its_conditions_are_met():
    relaxed = {r["id"]: r for r in apply_relaxes([BASE, BONUS])}["R-1b.height_chart"]
    for values in designs():
        got = outcome(relaxed, values, {})
        if got == "pass":                     # passes only by the base, or by the bonus with all its conditions met
            assert outcome(BASE, values, {}) == "pass" or (
                outcome(BONUS, values, {}) == "pass"), values
        if outcome(BASE, values, {}) == "fail" and outcome(BONUS, values, {}) != "pass":
            assert got != "pass", values      # an unknown or unmet condition never widens


def test_several_relaxers_each_widen_on_their_own_and_a_relaxer_stays_its_own_rule():
    other = {"id": "R-1b.other", "kind": "rule", "relaxes": "R-1b.height_chart", "applies_when": "abuts_r1_district",
             "check": "building_height <= 40"}
    rules = apply_relaxes([BASE, BONUS, other])
    relaxed = rules[0]
    assert relaxed["relaxed_by"] == ["R-1b.height_bonus", "R-1b.other"] and rules[1:] == [BONUS, other]
    assert outcome(relaxed, {"building_height": 39, "abuts_r1_district": True}, {}) == "pass"
    assert outcome(relaxed, {"building_height": 39, "abuts_r1_district": False}, {}) == "fail"
    assert apply_relaxes([BASE]) == [BASE]
    # a relaxer's review_when holds the widened rule for review where the widening is what decides, not elsewhere
    careful = other | {"review_when": [{"when": "lot_depth > 500", "reason": "deep lot"}]}
    relaxed = apply_relaxes([BASE, careful])[0]
    assert outcome(relaxed, {"building_height": 39, "abuts_r1_district": True, "lot_depth": 600}, {}) == "needs_review"
    assert outcome(relaxed, {"building_height": 30, "abuts_r1_district": True, "lot_depth": 600}, {}) == "pass"


def test_relaxes_is_checked_statically():
    def problems(*rules):
        return [p for p in validate({"district": "R-1b", "rules": list(rules)}, CTX) if "relax" in p]
    assert problems(BASE, BONUS) == []
    assert any("isn't a rule of this rulebook" in p for p in problems(BASE, BONUS | {"relaxes": "R-2a.height"}))
    assert any("relaxes itself" in p for p in problems(BONUS | {"relaxes": BONUS["id"]}))
    loop = BASE | {"relaxes": BONUS["id"], "applies_when": "abuts_r1_district"}
    assert any("cycle" in p for p in problems(loop, BONUS))
    assert any("needs its condition" in p for p in problems(BASE, {k: v for k, v in BONUS.items() if k != "applies_when"}))
    assert any("no check to widen" in p for p in problems(BASE | {"kind": "flag"}, BONUS))


def test_each_rules_examples_document_its_own_formula_relaxed_or_not():
    """The chart's height rule keeps its "36 ft fails" example when §325-16C relaxes it (drafted in another unit):
    examples are judged on the rule as written, so linking an exception never breaks the rule it widens."""
    base = copy.deepcopy(RULE)
    relief = {"id": "R-1b.rear_relief", "kind": "rule", "topic": "dimensions", "title": "x", "relaxes": RULE["id"],
              "applies_when": 'use == "one_family_detached"', "check": "rear_yard >= 0.25 * lot_depth - 10"}
    linked = [p for p in validate({"district": "R-1b", "rules": [base, relief]}, CTX) if p.startswith(RULE["id"] + ":")]
    assert not any("example" in p for p in linked)       # its 21 ft fail example still holds as written
    base["examples"].append({"given": {"use": "one_family_detached", "rear_yard": 15, "lot_depth": 90}, "expect": "pass"})
    linked = [p for p in validate({"district": "R-1b", "rules": [base, relief]}, CTX) if p.startswith(RULE["id"] + ":")]
    assert any("example 3" in p for p in linked)         # a pass only by the exception isn't the rule's own


def test_the_checker_reads_rules_with_their_relaxes_links_applied(tmp_path):
    rules_dir = tmp_path / "5_zoning_rules"
    rules_dir.mkdir()
    (rules_dir / "R-1b.yaml").write_text(yaml.safe_dump({"district": "R-1b", "rules": [BASE, BONUS]}), encoding="utf-8")
    got = {r["id"]: r for r in zone_rules(tmp_path, "R-1b")}
    tall = {"building_height": 37, "front_yard": 27, "side_yard_smaller": 12, "side_yard_larger": 12, "rear_yard": 30,
            "lot_depth": 100}
    assert outcome(got["R-1b.height_chart"], tall, {}) == "pass" and outcome(BASE, tall, {}) == "fail"
