"""The evaluation: the chart reader's cells against the rules drafted by reading (the hand answer keys).

Two independent readings of the same chart must agree, for every hand-drafted rulebook (the nine residential
districts, DISTRICTS below). For
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
DISTRICTS = {"R-1b": "R-1B", "R-1a": "R-1A", "R-2a": "R-2A", "R-2b": "R-2B", "R-2c": "R-2C", "R-3a": "R-3A",
             "R-3aa": "R-3AA", "R-3b": "R-3B", "RU": "RU"}
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
    # note 7's "for the first 1-3 units" figures, new construction and by conversion (3 units, no rooms let: the
    # cell's number itself; the additions past 3 units are the rule's own worked examples)
    **{(*LOT_SIZE, f"{label}, {how}"): [("lot_area", "min", {"use": use, "conversion": how == "by conversion",
                                                              "dwelling_units": 3, "rooms_let_for_profit": 0},
                                         lambda n: n[0])]
       for label, use in (("One-family dwelling, attached", "one_family_attached"),
                          ("Multiple family dwelling", "multiple_family"))
       for how in ("new construction", "by conversion")},
    **_by_use(LOT_SIZE, "Fraternity, sorority, or group house", "lot_area", "fraternity_sorority_group_house"),
    **_by_use(LOT_WIDTH, "One-family dwelling, detached, zero lot line", "lot_width", "one_family_detached_zero_lot_line"),
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
# Numbered cells no measurement can check yet: cited only by flags, with the reason. (Dormitory parking needs
# persons housed; loading needs units and floor space.)
# Each is still required to be cited (by a flag), and never by a rule's formula.
FLAG_ONLY = {
    (14, "Residential", "Dormitory"),
    (14, "Minimum Loading Requirement", "Multiple dweling with 25 + units"),
    (14, "Minimum Loading Requirement", "Nursing home, hospital, or sanitarium"),
    (14, "Minimum Loading Requirement", "Neighborhood commercial facility"),   # "See §325-21": a reference, no limit
}
COUNTS = {"stories", "parking_spaces"}     # whole numbers: one more (or fewer) is the next value
EXACT = ("pass", "fail")                   # a limit's usual meaning: it passes at the figure and fails just past it

# R-2C's cells state several figures, each for its own uses (chart p.3 notes 4-6, 12, 14, 15), and its lot sizes
# grow with the occupants. Each figure is one limit for one use, with the stated facts that make the figure itself
# the limit: one occupant (note 4); one dwelling unit on the lot, a semi-detached house split along its party wall
# (note 5); one occupant in a two-family house's two units, so twice the figure (note 5); one occupant in three
# units, three times the figure (attached, note 6). With one occupant there is no split of occupants between units
# to choose, so the figure is exact. The 5th element, when given, is what the rule says
# at the figure and just past it where the law's figure holds only on a side Gordium can't identify: the strictest
# reading's 10 ft passes and just under it needs review ("pass", "needs_review"); the most lenient reading's 0 ft
# needs review and just under it fails ("needs_review", "fail"), tested where the height bonus (38 ft: 0 + 3 ft, its
# eaves 1 ft) lifts it above the lot line (a negative distance isn't a measurement).
_Z, _S, _A = "one_family_detached_zero_lot_line", "one_family_semi_detached", "one_family_attached"
# every yard well clear, so only the one measured binds (the other rules citing the cell pass on both sides)
_CLEAR = {y: 100 for y in ("front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard")}
_CLEAR |= {f"{y}_eaves": 100 for y in _CLEAR}
R2C = {
    (*LOT_SIZE, "One-family dwelling, detached"):
        [("lot_area", "min", {"use": "one_family_detached", "occupants": 1}, lambda n: n[0])],
    (*LOT_SIZE, "One-family dwelling, detached, zero lot line"):
        [("lot_area", "min", {"use": _Z, "occupants": 1}, lambda n: n[0])],
    (*LOT_SIZE, "One-family dwelling, semi-detached"):
        [("lot_area", "min", {"use": _S, "dwelling_units": 1, "occupants": 1}, lambda n: n[0])],
    (*LOT_SIZE, "Two-family dwelling"): [("lot_area", "min", {"use": "two_family", "occupants": 1}, lambda n: 2 * n[0])],
    **{(*LOT_SIZE, f"One-family dwelling, attached, {how}"):
       [("lot_area", "min", {"use": _A, "dwelling_units": 3, "occupants": 1, "attached_units_in_building": 3}, lambda n: 3 * n[0])]
       for how in ("new construction", "by conversion")},
    (3, "Maximum lot coverage by buildings", "Percent of lot area"): [
        ("building_area", "max", {"lot_area": 10_000, "use": use}, lambda n, i=i: n[i] * 10_000)
        for i, use in enumerate(("one_family_detached", "two_family", _A))],
    SIDE_ONE: [  # note 14: 10 ft (detached, two-family, other uses; unattached sides), 15 ft (zero lot line)
        ("side_yard_larger", "min", {"side_yard_smaller": 100, "use": "one_family_detached"}, lambda n: n[0]),
        ("side_yard_larger_eaves", "min", {"side_yard_smaller_eaves": 100, "use": "one_family_detached"},
         lambda n: n[0] - 2),
        ("side_yard_larger", "min", {**_CLEAR, "use": _Z}, lambda n: n[1]),
        # (the narrower side's walls 14 ft: only the wider side can be the 15 ft one, so its eave alone decides;
        # with both sides' walls 15 ft or more either side may be, and #18's which-side review answers instead)
        ("side_yard_larger_eaves", "min", {**_CLEAR, "use": _Z, "side_yard_smaller": 14, "side_yard_smaller_eaves": 14},
         lambda n: n[1] - 2),
        ("side_yard_smaller", "min", {**_CLEAR, "use": _S}, lambda n: n[0], ("pass", "needs_review")),
        ("side_yard_smaller_eaves", "min", {**_CLEAR, "use": _S}, lambda n: n[0] - 2,
         ("pass", "needs_review"))],
    SIDE_OTHER: [  # note 15: 0 ft (zero lot line, semi-detached attached side), 5 ft (detached, two-family, other),
        # 10 ft (zero lot line next to a non-zero-lot-line building or lot)
        ("side_yard_smaller", "min", {"side_yard_larger": 100, "use": "one_family_detached"}, lambda n: n[1]),
        ("side_yard_smaller_eaves", "min", {"side_yard_larger_eaves": 100, "use": "one_family_detached"},
         lambda n: n[1] - 2),
        ("side_yard_smaller", "min", {**_CLEAR, "use": _S, "building_height": 38}, lambda n: n[0] + 3,
         ("needs_review", "fail")),
        ("side_yard_smaller_eaves", "min", {**_CLEAR, "use": _S, "building_height": 38}, lambda n: n[0] + 3 - 2,
         ("needs_review", "fail")),
        ("side_yard_smaller", "min", {**_CLEAR, "use": _Z}, lambda n: n[2], ("pass", "needs_review")),
        ("side_yard_smaller_eaves", "min", {**_CLEAR, "use": _Z, "side_yard_smaller": 14}, lambda n: n[2] - 2,
         ("pass", "needs_review"))],   # (narrower walls 14 ft: that side can't be the 15 ft one, as above)
}
# R-3AA's stories cell "3/2 [fn11]" states two figures (note 11): the first the most stories, the second the fewest.
# The fewest binds a building covering more than 500 sf (§325-8A(15)'s exemption is R-3aa.stories' open question).
R3AA = {(3, "Maximum Building Height [fn10]", "Number of stories"): [
    ("stories", "max", {}, lambda n: n[0]),
    ("stories", "min", {"building_area": 1000}, lambda n: n[1])]}
PER_DISTRICT = {"R-2C": R2C, "R-3AA": R3AA}


def limits(cells) -> dict:
    """LIMITS for one district. Columns 12 and 13 together require one side yard at least the larger figure and the
    other at least the smaller (§325-8A(12), (13)): R-3a's 10 ft and 5 ft bind the wider and the narrower yard.
    A district whose cells hold several figures, each for its own uses (R-2C) or its own limit (R-3AA's "3/2"), has
    its own meanings for those rows (PER_DISTRICT), laid over the rest."""
    columns = {c["column"] for c in cells}
    own = next((PER_DISTRICT[c] for c in sorted(columns & set(PER_DISTRICT))), {})
    side = {(c["page"], c["section"], c["row"]): numbers(c["value"]) for c in cells
            if (c["page"], c["section"], c["row"]) in (SIDE_ONE, SIDE_OTHER)}
    one, other = side.get(SIDE_ONE, [0])[0], side.get(SIDE_OTHER, [0])[0]
    out = dict(LIMITS)
    if one != other:
        wide, narrow = ((SIDE_ONE, SIDE_OTHER) if one > other else (SIDE_OTHER, SIDE_ONE))
        # the other wall at the narrower figure, so only this side can carry the larger one (each side's eaves are
        # held to the minimum their side carries, #18's P0: a wall far out on both sides leaves either side open)
        out[wide] = [("side_yard_larger", "min", {"side_yard_smaller": min(one, other)}, lambda n: n[0]),
                     ("side_yard_larger_eaves", "min", {"side_yard_smaller_eaves": 100}, lambda n: n[0] - 2)]
        out[narrow] = [("side_yard_smaller", "min", {"side_yard_larger": 100}, lambda n: n[0]),
                       ("side_yard_smaller_eaves", "min", {"side_yard_larger_eaves": 100}, lambda n: n[0] - 2)]
    return {**out, **own}


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
            for i, (measure, kind, fixed, limit, *expected) in enumerate(table[key]):
                exact = expected[0] if expected else EXACT
                bound = limit(numbers(c["value"]))
                if measure == "lot_area":           # §325-8B(1): the figure applies once per primary building, so a
                    bound *= base.get("primary_buildings", 1)   # rule worked out for two needs it twice (queue 15)
                step = 1 if measure in COUNTS else 0.01
                past = bound + step if kind == "max" else bound - step
                at = outcome(rule, base | fixed | {measure: bound}, uses)
                beyond = outcome(rule, base | fixed | {measure: past}, uses)
                # not binding here: passes on both sides (or, for a side Gordium can't identify, reviews on both); or a
                # row cited as an input for another use (R-3b's other-use rule cites the multiple-family row for its
                # reading's least, so for a multiple dwelling it doesn't apply): that row is enforced by its own rule,
                # which the `tried` check below still requires
                idle = {("pass", "pass"), ("not_applicable", "not_applicable")} | (
                    {("needs_review", "needs_review")} if expected else set())
                assert (at, beyond) in {exact} | idle, \
                    f"{rule['id']}: chart {c['value']!r} for {c['row']!r} → {measure} {kind} {bound}; got {at} at it, {beyond} past it"
                if (at, beyond) == exact:
                    tried.add((key, i))
    # every stated limit in this district's column (each figure of a cell that states several, R-2C's) is enforced
    # exactly by some rule
    want = {(c["page"], c["section"], c["row"]) for c in numbered(cells)} - FLAG_ONLY
    assert tried == {(key, i) for key in want for i in range(len(table[key]))}


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
            for measure, _, fixed, limit, *_ in table.get((c["page"], c["section"], c["row"]), []):
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
    assert keys <= set(limits(cells)) | FLAG_ONLY
    by_rules = {(c["page"], c["section"], c["row"]) for rule in rules if rule["kind"] == "rule"
                for c in cited_rows(rule, cells)}
    assert not by_rules & FLAG_ONLY                       # a figure no measurement can check is never in a formula


# Hand rulebooks written before this check whose headers don't name p.14's "Allowed by variance" row (to fix in their
# own PR): R-1b's header lists no loading at all.
UNNAMED_TEXT_CELLS = {"R-1B"}


def test_every_worded_cell_is_cited_or_named_as_not_covered(district):
    """A cell that states a requirement in words, not a number (p.14's "Allowed by variance [fn2]" for nonresidential
    loading, "See §325-21"), is either cited by a rule or flag, or named in the rulebook's header as not covered yet,
    so the gap is never silent (#r3-hand review round 1: R-3aa's and RU's headers had dropped it)."""
    rules, cells = district
    column = cells[0]["column"]
    if column in UNNAMED_TEXT_CELLS:
        pytest.skip(f"{column}: known gap, fixed in its own PR")
    name = next(k for k, v in DISTRICTS.items() if v == column)
    header = "".join(line for line in (ITHACA / f"5_zoning_rules/{name}.yaml").read_text(encoding="utf-8")
                     .splitlines(keepends=True) if line.startswith("#"))
    cited = {id(c) for rule in rules for c in cited_rows(rule, cells)}
    worded = [c for c in cells if c["page"] != 2 and not numbers(c["value"]) and c["value"].strip() not in ("", "-")]
    missing = [(c["row"], c["value"]) for c in worded if id(c) not in cited
               and re.sub(r"\s*\[fn[^\]]*\]", "", c["value"]).strip() not in header]
    assert missing == []


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
    # a mark may carry a note ("•[fn5]" in RU: new construction one every 500 ft): the mark is the •, and the note
    # must be a rule of its own, a flag naming that use and quoting the note
    noted = {use_of(c): re.search(r"\[fn(\d+)\]", c["value"])[1] for c in primary if "[fn" in c["value"]}
    marks = {use_of(c): re.sub(r"\s*\[fn\d+\]", "", c["value"]) for c in primary}
    for use, n in noted.items():
        assert any(r["kind"] == "flag" and "applies_when" in r and use in formula.strings(r["applies_when"])
                   and any(s.get("page") == 2 and str(s.get("quote", "")).startswith(f"({n})") for s in r["sources"])
                   for r in rules), f"{use}'s note {n} (chart p.2) has no flag of its own"
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
