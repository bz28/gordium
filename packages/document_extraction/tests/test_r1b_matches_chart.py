"""The evaluation: the chart reader's cells against the rules drafted by reading (the hand answer keys).

Two independent readings of the same chart must agree, for every hand-drafted rulebook (R-1b, R-1a, R-3a). For
every chart row a rule cites (by page and lines, or a cell), the rule must pass exactly at the reader's value in
that district's column and fail just past it; for the use list, a • must be allowed, an SP must go to review, a -
must be neither. And in the other direction, every cell of the district that holds a number, and every primary use
marked • or SP, must be cited by some rule, so a rule the drafter missed is caught too.
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
# each hand-drafted rulebook and the chart's spelling of its district column
DISTRICTS = {"R-1b": "R-1B", "R-1a": "R-1A", "R-3a": "R-3A"}
COLUMN = DISTRICTS["R-1b"]     # the drafting eval (rule_drafting/tests/test_eval.py) grades R-1b drafts with this module
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
SIDE_ONE = (3, "Yard Dimensions", "Side (one side minimum)")
SIDE_OTHER = (3, "Yard Dimensions", "Side (other side minimum)")


@pytest.fixture(scope="module", params=sorted(DISTRICTS))
def district(request):
    """(rules, the district's cells) for one hand-drafted rulebook."""
    rows = [json.loads(line) for line in CELLS.open(encoding="utf-8")]
    cells = [r for r in rows[1:] if r.get("column") == DISTRICTS[request.param] and not r["heading"]]
    return load(ITHACA / f"5_zoning_rules/{request.param}.yaml")["rules"], cells


def numbers(value: str) -> list[float]:
    """The numbers a cell states, without its footnote markers: "25%/ 50 ft [fn16]" -> [0.25, 50]."""
    text = re.sub(r"\[fn[^\]]*\]", "", value)
    return [float(n.rstrip("%").replace(",", "")) / (100 if n.endswith("%") else 1) for n in NUMBER.findall(text)]


def cited_rows(rule, cells):
    """The chart data rows (the district's cells) whose lines the rule's sources cite."""
    out = []
    for s in rule["sources"]:
        if s["file"] != CHART:
            continue
        if "cell" in s:                                   # a cited cell: its own row (the column checked below)
            match = [c for c in cells if (c["page"], c["section"], c["row"].strip()) ==
                     (s["page"], s["cell"]["section"], s["cell"]["row"].strip()) and s["cell"]["column"] == c["column"]]
        else:
            cited = set(range(s["lines"][0], s["lines"][1] + 1))
            match = [c for c in cells if c["page"] == s["page"] and cited & set(c["row_lines"])]
        out += [c for c in match if c not in out]
    return out


LOT_SIZE, LOT_WIDTH = (3, "Minimum Lot Size [fn3]"), (3, "Minimum Lot Width")


def _by_use(section, row, measure, use):
    return {(*section, row): [(measure, "min", {"use": use}, lambda n: n[0])]}


# What each numbered chart row means, as a limit on one measurement: (measure, "min" or "max",
# measurements to hold fixed, the limit given the cell's numbers). This is the chart's own row label
# and section put into measurement terms, written once here; the numbers always come from the cell.
LIMITS = {
    (3, "Minimum Lot Size [fn3]", "One-family dwelling, detached"): [("lot_area", "min", {}, lambda n: n[0])],
    (3, "Minimum Lot Size [fn3]", "Other use"): [("lot_area", "min", {"use": "church"}, lambda n: n[0])],
    (3, "Minimum Lot Width", "One-family dwelling, detached"): [("lot_width", "min", {}, lambda n: n[0])],
    (3, "Minimum Lot Width", "Other use"): [("lot_width", "min", {"use": "church"}, lambda n: n[0])],
    # rows for the uses of the multi-family districts (R-3a): each limit holds for its own use
    **_by_use(LOT_SIZE, "One-family dwelling, semi-detached", "lot_area", "one_family_semi_detached"),
    **_by_use(LOT_SIZE, "Two-family dwelling", "lot_area", "two_family"),
    # note 7's "for the first 1-3 units" figure, new construction: the least any such building needs (a floor)
    **_by_use(LOT_SIZE, "One-family dwelling, attached, new construction", "lot_area", "one_family_attached"),
    **_by_use(LOT_SIZE, "Multiple family dwelling, new construction", "lot_area", "multiple_family"),
    **_by_use(LOT_SIZE, "Fraternity, sorority, or group house", "lot_area", "fraternity_sorority_group_house"),
    **_by_use(LOT_WIDTH, "One-family dwelling, semi-detached", "lot_width", "one_family_semi_detached"),
    **_by_use(LOT_WIDTH, "One-family dwelling, attached", "lot_width", "one_family_attached"),
    **_by_use(LOT_WIDTH, "Two-family dwelling", "lot_width", "two_family"),
    **_by_use(LOT_WIDTH, "Multiple family dwelling", "lot_width", "multiple_family"),
    **_by_use(LOT_WIDTH, "Fraternity, sorority, or group house", "lot_width", "fraternity_sorority_group_house"),
    (3, "Maximum Building Height [fn10]", "Number of stories"): [("stories", "max", {}, lambda n: n[0])],
    (3, "Maximum Building Height [fn10]", "Height in feet"): [("building_height", "max", {}, lambda n: n[0])],
    (3, "Maximum lot coverage by buildings", "Percent of lot area"):
        [("building_area", "max", {"lot_area": 10_000}, lambda n: n[0] * 10_000)],
    # each yard, and the same yard to the eaves, which §325-18B lets reach 2 ft into it ("not ... more than two
    # feet into any required yard")
    (3, "Yard Dimensions", "Front (minimum)"): [("front_yard", "min", {}, lambda n: n[0]),
                                                 ("front_yard_eaves", "min", {}, lambda n: n[0] - 2)],
    # R-1B's reading of the two side rows (its two minimums are equal, so either way round is exact); limits()
    # picks which yard each row binds for a district whose two minimums differ (R-3a's 10 ft and 5 ft)
    SIDE_ONE: [("side_yard_smaller", "min", {"side_yard_larger": 100}, lambda n: n[0]),
               ("side_yard_smaller_eaves", "min", {"side_yard_larger_eaves": 100}, lambda n: n[0] - 2)],
    SIDE_OTHER: [("side_yard_larger", "min", {"side_yard_smaller": 100}, lambda n: n[0]),
                 ("side_yard_larger_eaves", "min", {"side_yard_smaller_eaves": 100}, lambda n: n[0] - 2)],
    (3, "Yard Dimensions", "Rear (minimum, % of depth or feet, whichever is less)"): [
        ("rear_yard", "min", {"lot_depth": 160}, lambda n: n[0] * 160),       # the % governs
        ("rear_yard", "min", {"lot_depth": 400}, lambda n: n[1]),             # the cap governs
        ("rear_yard_eaves", "min", {"lot_depth": 160, "rear_yard": 1000}, lambda n: n[0] * 160 - 2),
        ("rear_yard_eaves", "min", {"lot_depth": 400, "rear_yard": 1000}, lambda n: n[1] - 2)],
    (14, "Residential", "First three bed or sleeping rooms per dwelling unit"):
        [("parking_spaces", "min", {"sleeping_rooms": 3}, lambda n: n[0])],
    (14, "Residential", "4-5 bed or sleeping rooms per dwelling unit"):
        [("parking_spaces", "min", {"sleeping_rooms": 5}, lambda n: n[0])],
    (14, "Residential", "Each additional bed or sleeping room"):           # 7 rooms: the 4-5 band, then 2 more
        [("parking_spaces", "min", {"sleeping_rooms": 7}, lambda n: 2 + 2 * n[0])],
}
# Numbered cells no measurement can check yet: cited only by flags, with the reason. (Note 7's conversion figures
# need a conversion yes/no; dormitory parking needs persons housed; loading needs units and floor space.)
# Each is still required to be cited (by a flag), and never by a rule's formula.
FLAG_ONLY = {
    (3, "Minimum Lot Size [fn3]", "One-family dwelling, attached, by conversion"),
    (3, "Minimum Lot Size [fn3]", "Multiple family dwelling, by conversion"),
    (14, "Residential", "Dormitory"),
    (14, "Minimum Loading Requirement", "Multiple dweling with 25 + units"),
    (14, "Minimum Loading Requirement", "Nursing home, hospital, or sanitarium"),
    (14, "Minimum Loading Requirement", "Neighborhood commercial facility"),   # "See §325-21": a reference, no limit
}
COUNTS = {"stories", "parking_spaces"}     # whole numbers: one more (or fewer) is the next value


def limits(cells) -> dict:
    """LIMITS for one district. Columns 12 and 13 together require one side yard at least the larger figure and the
    other at least the smaller (§325-8A(12), (13)): R-3a's 10 ft and 5 ft bind the wider and the narrower yard."""
    side = {(c["page"], c["section"], c["row"]): numbers(c["value"]) for c in cells
            if (c["page"], c["section"], c["row"]) in (SIDE_ONE, SIDE_OTHER)}
    one, other = side.get(SIDE_ONE, [0])[0], side.get(SIDE_OTHER, [0])[0]
    out = dict(LIMITS)
    if one == other:
        return out
    wide, narrow = ((SIDE_ONE, SIDE_OTHER) if one > other else (SIDE_OTHER, SIDE_ONE))
    out[wide] = [("side_yard_larger", "min", {"side_yard_smaller": 100}, lambda n: n[0]),
                 ("side_yard_larger_eaves", "min", {"side_yard_smaller_eaves": 100}, lambda n: n[0] - 2)]
    out[narrow] = [("side_yard_smaller", "min", {"side_yard_larger": 100}, lambda n: n[0]),
                   ("side_yard_smaller_eaves", "min", {"side_yard_larger_eaves": 100}, lambda n: n[0] - 2)]
    return out


def numbered(cells) -> list[dict]:
    return [c for c in cells if c["page"] != 2 and numbers(c["value"])]


def test_each_chart_value_is_exactly_where_the_rule_turns_from_pass_to_fail(district):
    """Not just "the number appears in the formula": starting from a rule's own passing example, the
    design passes at the chart's limit and fails just past it, so the number bounds the right measurement,
    in the right direction. Every chart limit must be enforced that way by some rule. A rule may also cite
    a row as an input that doesn't bind at its passing example (the height bonus cites the yard minimums
    it enlarges): then it passes on both sides, never fails at the limit."""
    rules, cells = district
    table = limits(cells)
    uses = {"use": set(load(ITHACA / "4_term_definitions/uses.yaml"))}
    tried = set()
    for rule in rules:
        if rule["kind"] != "rule":
            continue
        base = next(ex["given"] for ex in rule["examples"] if ex["expect"] == "pass")
        for c in cited_rows(rule, cells):
            key = (c["page"], c["section"], c["row"])
            if c["page"] == 2:
                continue
            assert key in table, f"{rule['id']} cites {key}, which has no stated meaning here"
            for measure, kind, fixed, limit in table[key]:
                bound = limit(numbers(c["value"]))
                step = 1 if measure in COUNTS else 0.01
                past = bound + step if kind == "max" else bound - step
                at = outcome(rule, base | fixed | {measure: bound}, uses)
                beyond = outcome(rule, base | fixed | {measure: past}, uses)
                assert (at, beyond) in {("pass", "fail"), ("pass", "pass")}, \
                    f"{rule['id']}: chart {c['value']!r} for {c['row']!r} → {measure} {kind} {bound}; got {at} at it, {beyond} past it"
                if (at, beyond) == ("pass", "fail"):
                    tried.add(key)
    # every stated limit in this district's column is enforced exactly by some rule
    assert tried == {(c["page"], c["section"], c["row"]) for c in numbered(cells)} - FLAG_ONLY


def _with_number_changed(text: str, n: float, new: float, which: int) -> tuple[str, int]:
    """The formula with the which-th number constant equal to n (counting from 0) replaced by new, and how
    many constants equal n it has."""
    seen = [0]

    class Swap(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) in (int, float) and abs(node.value - n) < 1e-9:
                seen[0] += 1
                if seen[0] - 1 == which:
                    return ast.copy_location(ast.Constant(new), node)
            return node
    return ast.unparse(Swap().visit(ast.parse(text, mode="eval"))), seen[0]


def _formulas(rule) -> list[tuple]:
    """(where, text) for every formula: ("check", ...), ("applies_when", ...), ("review_when", i, ...)."""
    out = [((k,), rule[k]) for k in ("applies_when", "check") if k in rule]
    return out + [(("review_when", i), r["when"]) for i, r in enumerate(rule.get("review_when", []))]


def occurrences(rule, n) -> list[tuple]:
    """Each place the number n is written in the rule's formulas: (where, which)."""
    return [(where, i) for where, text in _formulas(rule) for i in range(_with_number_changed(text, n, n, -1)[1])]


def number_matters(rule, n, where, which, cells, allowed, table=LIMITS) -> bool:
    """Does this one occurrence of the number n (from a cell the rule cites) decide anything? Changed alone,
    some outcome must change: on a worked example, or around a cited chart limit from each passing example
    (that's where an input like the bonus's yard minimum binds: at bound + the extra height)."""
    changed = copy.deepcopy(rule)
    if where[0] == "review_when":
        r = changed["review_when"][where[1]]
        r["when"] = _with_number_changed(r["when"], n, n * 1.5 + 1, which)[0]
    else:
        changed[where[0]] = _with_number_changed(changed[where[0]], n, n * 1.5 + 1, which)[0]
    probes = [ex["given"] for ex in rule["examples"]]
    for base in (ex["given"] for ex in rule["examples"] if ex["expect"] == "pass"):
        for c in cells:
            for measure, _, fixed, limit in table.get((c["page"], c["section"], c["row"]), []):
                probes += [base | fixed | {measure: limit(numbers(c["value"])) + k / 2} for k in range(-20, 21)]
    return any(outcome(rule, p, allowed) != outcome(changed, p, allowed) for p in probes)


def idle_numbers(rule, cells, allowed, table=LIMITS) -> list[str]:
    """Every number of every cited cell must be written in the formula at least as often as the cited cells
    state it (two side yards of 10 ft need two 10s), and every place it's written must decide something."""
    problems = []
    stated = [n for c in cells for n in numbers(c["value"])]
    for n in dict.fromkeys(stated):
        places = occurrences(rule, n)
        need = sum(abs(n - m) < 1e-9 for m in stated)
        if len(places) < need:
            rows = [c["row"] for c in cells if any(abs(n - m) < 1e-9 for m in numbers(c["value"]))]
            problems.append(f"{rule['id']}: {n:g} is stated by {need} cited cells ({', '.join(rows)}) "
                            f"but written {len(places)} times in its formula")
        problems += [f"{rule['id']}: the {i + 1}th {n:g} in {where[0]} changes nothing"
                     for where, i in places if not number_matters(rule, n, where, i, cells, allowed, table)]
    return problems


def test_every_cited_chart_number_in_a_formula_decides_something(district):
    """A rule can cite a row as an input whose limit doesn't bind at its first passing example (the height
    bonus cites the yard minimums), so the exact-limit test alone can't catch a wrong number there."""
    rules, cells = district
    uses = {"use": set(load(ITHACA / "4_term_definitions/uses.yaml"))}
    idle = []
    for rule in rules:
        if rule["kind"] == "rule":
            idle += idle_numbers(rule, [c for c in cited_rows(rule, cells) if c["page"] != 2], uses, limits(cells))
    assert idle == []


def test_every_numbered_cell_is_cited_by_a_rule_and_has_a_meaning(district):
    rules, cells = district
    cited = {id(c) for rule in rules for c in cited_rows(rule, cells)}
    assert [(c["page"], c["section"], c["row"], c["value"]) for c in numbered(cells) if id(c) not in cited] == []
    keys = {(c["page"], c["section"], c["row"]) for c in numbered(cells)}
    assert keys <= set(LIMITS) | FLAG_ONLY
    by_rules = {(c["page"], c["section"], c["row"]) for rule in rules if rule["kind"] == "rule"
                for c in cited_rows(rule, cells)}
    assert not by_rules & FLAG_ONLY                       # a figure no measurement can check is never in a formula


def test_use_list_matches_the_chart_marks(district):
    rules, cells = district
    uses = load(ITHACA / "4_term_definitions/uses.yaml")
    use_rule = next(r for r in rules if r["id"].endswith(".use"))

    def use_of(cell):
        ids = [k for k, v in uses.items() for s in v["sources"]
               if s["page"] == cell["page"] and set(range(s["lines"][0], s["lines"][1] + 1)) & set(cell["row_lines"])]
        assert len(ids) == 1, (cell["row"], ids)
        return ids[0]

    primary = [c for c in cells if c["page"] == 2 and c["section"] == "Primary Uses"]
    marks = {use_of(c): c["value"] for c in primary}
    assert set(marks.values()) <= {"•", "SP", "-"}
    assert set(marks) == set(uses)                                            # every use has a mark
    if use_rule["kind"] == "rule":
        allowed = formula.strings(use_rule["check"])
        flagged = set().union(*(formula.strings(w["when"]) for w in use_rule.get("review_when", [])))
    else:   # no use is "-" (R-3a): nothing can fail, so a flag sends the SP uses to review, the rest are permitted
        assert "-" not in marks.values()
        flagged = formula.strings(use_rule["applies_when"])
        allowed = set(uses) - flagged
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
