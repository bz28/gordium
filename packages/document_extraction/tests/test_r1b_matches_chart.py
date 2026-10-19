"""The evaluation: the chart reader's R-1B cells against the R-1b rules drafted by reading.

Two independent readings of the same chart must agree. For every chart row an R-1b rule cites (by
page and lines), the rule must pass exactly at the reader's R-1B value and fail just past it; for the
use list, a • must be allowed, an SP must go to review, a - must be neither. And in the other
direction, every R-1B cell that holds a number, and every primary use marked • or SP, must be cited
by some rule, so a rule the drafter missed is caught too.
"""

import ast
import copy
import json
import re
from pathlib import Path

import pytest

from rule_format import formula
from rule_format.rulebook import load, outcome

REPO = Path(__file__).resolve().parents[3]
ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
CELLS = ITHACA / "2_extracted_text/zoning_charts_2026-04.cells.jsonl"
CHART = "zoning_charts_2026-04.pdf"
COLUMN = "R-1B"          # the chart's spelling of the district the rule file names R-1b
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


@pytest.fixture(scope="module")
def r1b_cells():
    rows = [json.loads(line) for line in CELLS.open(encoding="utf-8")]
    return [r for r in rows[1:] if r.get("column") == COLUMN and not r["heading"]]


@pytest.fixture(scope="module")
def rules():
    return load(ITHACA / "5_zoning_rules/R-1b.yaml")["rules"]


def numbers(value: str) -> list[float]:
    """The numbers a cell states, without its footnote markers: "25%/ 50 ft [fn16]" -> [0.25, 50]."""
    text = re.sub(r"\[fn[^\]]*\]", "", value)
    return [float(n.rstrip("%").replace(",", "")) / (100 if n.endswith("%") else 1) for n in NUMBER.findall(text)]


def cited_rows(rule, cells):
    """The chart data rows (R-1B cells) whose lines the rule's sources cite."""
    out = []
    for s in rule["sources"]:
        if s["file"] != CHART:
            continue
        if "cell" in s:                                   # a cited cell: its own row (R-1B column checked below)
            match = [c for c in cells if (c["page"], c["section"], c["row"].strip()) ==
                     (s["page"], s["cell"]["section"], s["cell"]["row"].strip()) and s["cell"]["column"] == c["column"]]
        else:
            cited = set(range(s["lines"][0], s["lines"][1] + 1))
            match = [c for c in cells if c["page"] == s["page"] and cited & set(c["row_lines"])]
        out += [c for c in match if c not in out]
    return out


# What each numbered chart row means, as a limit on one measurement: (measure, "min" or "max",
# measurements to hold fixed, the limit given the cell's numbers). This is the chart's own row label
# and section put into measurement terms, written once here; the numbers always come from the cell.
LIMITS = {
    (3, "Minimum Lot Size [fn3]", "One-family dwelling, detached"): [("lot_area", "min", {}, lambda n: n[0])],
    (3, "Minimum Lot Size [fn3]", "Other use"): [("lot_area", "min", {"use": "church"}, lambda n: n[0])],
    (3, "Minimum Lot Width", "One-family dwelling, detached"): [("lot_width", "min", {}, lambda n: n[0])],
    (3, "Minimum Lot Width", "Other use"): [("lot_width", "min", {"use": "church"}, lambda n: n[0])],
    (3, "Maximum Building Height [fn10]", "Number of stories"): [("stories", "max", {}, lambda n: n[0])],
    (3, "Maximum Building Height [fn10]", "Height in feet"): [("building_height", "max", {}, lambda n: n[0])],
    (3, "Maximum lot coverage by buildings", "Percent of lot area"):
        [("building_area", "max", {"lot_area": 10_000}, lambda n: n[0] * 10_000)],
    (3, "Yard Dimensions", "Front (minimum)"): [("front_yard", "min", {}, lambda n: n[0])],
    (3, "Yard Dimensions", "Side (one side minimum)"):
        [("side_yard_smaller", "min", {"side_yard_larger": 100}, lambda n: n[0])],
    (3, "Yard Dimensions", "Side (other side minimum)"):
        [("side_yard_larger", "min", {"side_yard_smaller": 100}, lambda n: n[0])],
    (3, "Yard Dimensions", "Rear (minimum, % of depth or feet, whichever is less)"): [
        ("rear_yard", "min", {"lot_depth": 160}, lambda n: n[0] * 160),       # the % governs
        ("rear_yard", "min", {"lot_depth": 400}, lambda n: n[1])],            # the cap governs
    (14, "Residential", "First three bed or sleeping rooms per dwelling unit"):
        [("parking_spaces", "min", {"sleeping_rooms": 3}, lambda n: n[0])],
    (14, "Residential", "4-5 bed or sleeping rooms per dwelling unit"):
        [("parking_spaces", "min", {"sleeping_rooms": 5}, lambda n: n[0])],
    (14, "Residential", "Each additional bed or sleeping room"):           # 7 rooms: the 4-5 band, then 2 more
        [("parking_spaces", "min", {"sleeping_rooms": 7}, lambda n: 2 + 2 * n[0])],
}
COUNTS = {"stories", "parking_spaces"}     # whole numbers: one more (or fewer) is the next value


def test_each_chart_value_is_exactly_where_the_rule_turns_from_pass_to_fail(rules, r1b_cells):
    """Not just "the number appears in the formula": starting from a rule's own passing example, the
    design passes at the chart's limit and fails just past it, so the number bounds the right measurement,
    in the right direction. Every chart limit must be enforced that way by some rule. A rule may also cite
    a row as an input that doesn't bind at its passing example (the height bonus cites the yard minimums
    it enlarges): then it passes on both sides, never fails at the limit."""
    uses = {"use": set(load(ITHACA / "4_term_definitions/uses.yaml"))}
    tried = set()
    for rule in rules:
        if rule["kind"] != "rule":
            continue
        base = next(ex["given"] for ex in rule["examples"] if ex["expect"] == "pass")
        for c in cited_rows(rule, r1b_cells):
            key = (c["page"], c["section"], c["row"])
            if c["page"] == 2:
                continue
            assert key in LIMITS, f"{rule['id']} cites {key}, which has no stated meaning here"
            for measure, kind, fixed, limit in LIMITS[key]:
                bound = limit(numbers(c["value"]))
                step = 1 if measure in COUNTS else 0.01
                past = bound + step if kind == "max" else bound - step
                at = outcome(rule, base | fixed | {measure: bound}, uses)
                beyond = outcome(rule, base | fixed | {measure: past}, uses)
                assert (at, beyond) in {("pass", "fail"), ("pass", "pass")}, \
                    f"{rule['id']}: chart {c['value']!r} for {c['row']!r} → {measure} {kind} {bound}; got {at} at it, {beyond} past it"
                if (at, beyond) == ("pass", "fail"):
                    tried.add(key)
    assert tried == set(LIMITS)                                  # every stated limit is enforced exactly by some rule


def _with_number_changed(text: str, n: float, new: float) -> str:
    """The formula with every number constant equal to n replaced by new."""
    class Swap(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) in (int, float) and abs(node.value - n) < 1e-9:
                return ast.copy_location(ast.Constant(new), node)
            return node
    return ast.unparse(Swap().visit(ast.parse(text, mode="eval")))


def number_matters(rule, n, cells, allowed) -> bool:
    """Does the number n (from a cell the rule cites) decide anything? Changed in the rule's formulas, some
    outcome must change: on a worked example, or around a cited chart limit from each passing example
    (that's where an input like the bonus's yard minimum binds: at bound + the extra height)."""
    changed = copy.deepcopy(rule)
    for key in ("applies_when", "check"):
        if key in changed:
            changed[key] = _with_number_changed(changed[key], n, n * 1.5 + 1)
    for r in changed.get("review_when", []):
        r["when"] = _with_number_changed(r["when"], n, n * 1.5 + 1)
    probes = [ex["given"] for ex in rule["examples"]]
    for base in (ex["given"] for ex in rule["examples"] if ex["expect"] == "pass"):
        for c in cells:
            for measure, _, fixed, limit in LIMITS.get((c["page"], c["section"], c["row"]), []):
                probes += [base | fixed | {measure: limit(numbers(c["value"])) + k / 2} for k in range(-20, 21)]
    return any(outcome(rule, p, allowed) != outcome(changed, p, allowed) for p in probes)


def formula_numbers(rule) -> list[float]:
    texts = [rule[k] for k in ("applies_when", "check") if k in rule] + [r["when"] for r in rule.get("review_when", [])]
    return [n for t in texts for n in formula.numbers(t)]


def test_every_cited_chart_number_in_a_formula_decides_something(rules, r1b_cells):
    """A rule can cite a row as an input whose limit doesn't bind at its first passing example (the height
    bonus cites the yard minimums), so the exact-limit test alone can't catch a wrong number there. Every
    number a cited cell gives must appear in the rule's formula and change some outcome when changed."""
    uses = {"use": set(load(ITHACA / "4_term_definitions/uses.yaml"))}
    idle = []
    for rule in rules:
        if rule["kind"] != "rule":
            continue
        cells = [c for c in cited_rows(rule, r1b_cells) if c["page"] != 2]
        used = formula_numbers(rule)
        for c in cells:
            for n in numbers(c["value"]):
                if not any(abs(n - u) < 1e-9 for u in used):
                    idle.append(f"{rule['id']}: cites {c['row']!r} ({c['value']}) but its formula doesn't use {n:g}")
                elif not number_matters(rule, n, cells, uses):
                    idle.append(f"{rule['id']}: {n:g} from {c['row']!r} changes nothing")
    assert idle == []


def test_every_numbered_r1b_cell_is_cited_by_a_rule_and_has_a_meaning(rules, r1b_cells):
    cited = {id(c) for rule in rules for c in cited_rows(rule, r1b_cells)}
    numbered = [c for c in r1b_cells if c["page"] != 2 and numbers(c["value"])]
    assert [(c["page"], c["section"], c["row"], c["value"]) for c in numbered if id(c) not in cited] == []
    assert {(c["page"], c["section"], c["row"]) for c in numbered} == set(LIMITS)


def test_r1b_use_list_matches_the_chart_marks(rules, r1b_cells):
    uses = load(ITHACA / "4_term_definitions/uses.yaml")
    use_rule = next(r for r in rules if r["id"] == "R-1b.use")
    allowed = formula.strings(use_rule["check"])
    flagged = set().union(*(formula.strings(w["when"]) for w in use_rule.get("review_when", [])))

    def use_of(cell):
        ids = [k for k, v in uses.items() for s in v["sources"]
               if s["page"] == cell["page"] and set(range(s["lines"][0], s["lines"][1] + 1)) & set(cell["row_lines"])]
        assert len(ids) == 1, (cell["row"], ids)
        return ids[0]

    primary = [c for c in r1b_cells if c["page"] == 2 and c["section"] == "Primary Uses"]
    marks = {use_of(c): c["value"] for c in primary}
    assert set(marks.values()) <= {"•", "SP", "-"}
    assert {u for u, m in marks.items() if m == "•"} == allowed               # every • allowed, nothing else
    assert {u for u, m in marks.items() if m == "SP"} == flagged              # every SP sent to review
    cited = {use_of(c) for c in cited_rows(use_rule, primary)}
    assert allowed | flagged <= cited                                         # and each one's row is cited


@pytest.mark.parametrize("value, expected", [
    ("6,000 sf", [6000]), ("25%", [0.25]), ("25%/ 50 ft [fn16]", [0.25, 50]), ("3/2 [fn11]", [3, 2]),
    ("1 space per dwelling unit", [1]), ("+ 1 space per room", [1]), ("-", []), ("Allowed by variance [fn2]", []),
])
def test_numbers_read_from_a_cell(value, expected):
    assert numbers(value) == expected
