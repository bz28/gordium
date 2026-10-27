"""Grade the drafted rules, once a drafting run has produced them (these tests skip until then).

1. Against the hand-drafted R-1b (the answer key, never shown to the drafter): for every worked example in
   it, the drafted rules covering the same chart rows or law lines must give the same outcome.
2. Against the architects' own spreadsheet check of 106 Ithaca Rd: the drafted R-1b rules still give their
   PASS/FAIL on every row.
3. Every district's chart rules cite only that district's own cells (so its numbers are its own).
4. Every unit the log says was drafted produced a rule, a reason, or an entry for a person; once the run is
   complete, every unit was drafted.
5. Every drafted rulebook passes the inspector.

"Covering" is by citation: a drafted rule covers a hand rule when it cites a cell on one of the chart rows
the hand rule quotes, or a line of the law the hand rule quotes. Several drafted rules may cover one hand
rule; together they fail if any fails, need review if any does, and pass if one passes (or none applies).
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

import openpyxl
import pytest

from rule_format.rulebook import (Context, _cited_lines, apply_relaxes, district_name, load, outcome, proven_relaxers,
                                  validate)

REPO = Path(__file__).resolve().parents[3]
ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
DRAFTED = ITHACA / "5_zoning_rules/drafted"
LOG = DRAFTED / "records/drafting_log.yaml"
CHART = "zoning_charts_2026-04.pdf"
SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/spreadsheet_design.yaml"
R1B = {"district": "R-1b"}       # every answer-key example is an R-1b lot, as the checker would know


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(ITHACA)


@pytest.fixture(scope="module")
def drafted_r1b():
    if not (DRAFTED / "R-1b.yaml").exists():
        pytest.skip("no drafted R-1b yet: run python -m rule_drafting draft")
    rules = load(DRAFTED / "R-1b.yaml")["rules"]
    if (DRAFTED / "general.yaml").exists():
        rules += load(DRAFTED / "general.yaml")["rules"]
    return rules


@pytest.fixture(scope="module")
def hand():
    return load(ITHACA / "5_zoning_rules/R-1b.yaml")["rules"]


def law_unit_rules() -> set[str]:
    """The drafted rules whose unit is a piece of the law (not a chart section), from the drafting log."""
    if not LOG.exists():
        return set()
    return {rid for unit, e in load(LOG)["units"].items() if not unit.startswith("chart-") for rid in e["rules"]}


def covering(hand_rule, drafted, ctx, from_law=None):
    """The drafted rules that cite a chart row or law line the hand rule quotes. Footnotes are left out
    (many rows share one). A rule's subject is what it quotes, not the cells it takes as inputs: in the answer
    key a rule cites cells only as inputs (the height bonus cites the yard minimums it enlarges), and so does a
    rule drafted from a piece of the law (§325-16C's rules read the chart's height and yards), so those cells
    are left out for both. from_law: the drafted rules from law pieces (default: from the drafting log)."""
    from_law = law_unit_rules() if from_law is None else from_law

    def lines(rule, quotes_only=False):
        sources = [s for s in rule["sources"] if not (quotes_only and "cell" in s)]
        notes = {(s["file"], s["page"], n) for s in sources if s.get("quote", "").startswith("(")
                 and s["file"] == CHART for n in range(s["lines"][0], s["lines"][1] + 1)}
        return _cited_lines(sources, ctx) - notes
    # A hand rule that quotes a chart row's text (the hand R-1b) is about those rows, and its cells are inputs. One that
    # quotes no chart text (only law, footnotes, or the bare row of district names) and cites cells, like the hand
    # R-3a's yards, coverage and use, is about its cells: they are matched too, so a drafted rule citing them covers it.
    def chart_text(s):
        words = str(s.get("quote", "")).split()
        return (s.get("file") == CHART and "lines" in s and not str(s.get("quote", "")).startswith("(")
                and not all(re.fullmatch(r"R-\w+|RU|\[fn[\d,]+\]", w) for w in words))
    # ... or quotes chart text of the same section as its cells (the hand R-1a's use rule quotes use rows, some
    # refused, and cites the use cells). The R-1b height rule quotes the height row and cites yard cells: inputs.
    chart_cells = ctx.cells.get(CHART, {})

    def section_of(line_page):
        page, n = line_page
        return {re.sub(r"\s*\[fn[\d,]+\]", "", k[1]) for k, c in chart_cells.items() if k[0] == page and n in c["row_lines"]}
    quoted_sections = set().union(*(section_of((s["page"], n)) for s in hand_rule["sources"] if chart_text(s)
                                    for n in range(s["lines"][0], s["lines"][1] + 1))) if any(
        chart_text(s) for s in hand_rule["sources"]) else set()
    cell_sections = {re.sub(r"\s*\[fn[\d,]+\]", "", s["cell"]["section"]) for s in hand_rule["sources"] if "cell" in s}
    about_cells = not quoted_sections or bool(cell_sections) and cell_sections <= quoted_sections
    quoted = lines(hand_rule, quotes_only=True)
    wanted = lines(hand_rule, quotes_only=not about_cells)
    # a match made only through a cell must also measure the same thing (the accessory rule cites the front-yard cell
    # as an input; the drafted front-yard rule doesn't cover it)
    from rule_format import formula

    def names(rule):
        return {n for t in rule_formulas(rule) for n in formula.names(t)} - {"district"}

    def measured(rule):                  # use and district pick which number applies; they aren't what is checked
        return names(rule) - {"use"}

    def covers(r):
        mine = lines(r, quotes_only=r["id"] in from_law)
        if mine & quoted:
            return True
        # A cell match needs a measure in common when the hand rule measures something (R-2c's side yards cite the
        # use rows as inputs: the permitted-use rule doesn't cover them). A hand rule that measures nothing (a use
        # flag: R-3a.parking_dormitory) is covered by any drafted rule on its cell that selects one of its uses, a
        # numeric one included, so a drafted pass against its needs review still reaches false_pass (round 6).
        same = measured(r) & measured(hand_rule) if measured(hand_rule) else selected_uses(r) & selected_uses(hand_rule)
        return bool(mine & wanted and same)
    return [r for r in drafted if covers(r)]


def selected_uses(rule) -> set[str]:
    """The uses a rule's formulas name, compared with `use` (use == "dormitory", use in [...])."""
    from rule_format import formula
    return {v for t in rule_formulas(rule) for name, v in formula.compared_strings(t) if name == "use"}


def rule_formulas(rule):
    return [rule[k] for k in ("applies_when", "check") if k in rule] + [r["when"] for r in rule.get("review_when", [])]


def with_new_measures(rule, given, proposed):
    """The hand example's values plus, for each new measure the drafted rule declared (proposed_measures.yaml)
    that the hand example doesn't give, the value the drafted rule's own passing example gives it: the
    ordinary case ("no second primary building on the lot"), so a missing input never stands in for a real
    disagreement. Returns (values, what was supplied, what no example supplies)."""
    from rule_format import formula
    needed = sorted({n for t in rule_formulas(rule) for n in formula.names(t)} & set(proposed) - set(given))
    passing = [ex["given"] for ex in rule.get("examples", []) if ex["expect"] == "pass"]
    supplied, missing = {}, []
    for name in needed:
        source = next((g for g in passing if name in g), None)
        if source is None:
            missing.append(name)
        else:
            supplied[name] = source[name]
    return given | supplied, supplied, missing


def combined(rules, values, ctx, proposed=frozenset()):
    """(outcome, notes): every covering rule judged on the example with its declared new measures supplied."""
    results, notes = set(), []
    from rule_format import formula
    for r in rules:
        given, supplied, missing = with_new_measures(r, values, proposed)
        if missing:
            notes.append(f"{r['id']} needs {missing}, which neither the example nor its own passing example gives")
        elif supplied:
            notes.append(f"{r['id']} given {supplied} from its own passing example")
        # an ordinary measure the hand example lacks is named, never filled from the draft (that could hide a
        # real disagreement): the drafted rule needs review there, and the note says why
        if other := sorted({n for t in rule_formulas(r) for n in formula.names(t)} - set(given) - set(proposed)):
            notes.append(f"{r['id']} needs {other}, which the hand example doesn't give")
        results.add(outcome(r, given, ctx.allowed()))
    for result in ("fail", "needs_review", "pass"):
        if result in results:
            return result, notes
    return "not_applicable", notes


def judge_r1b_example(rules, given, ctx):
    """An answer-key example judged by the drafted rules covering it, as an R-1b lot (the checker always knows
    the lot's district; the spreadsheet comparison gives it too)."""
    return combined(rules, R1B | given, ctx, set(ctx.proposed))


def hand_keys() -> list[Path]:
    """Every hand-written rulebook (5_zoning_rules/<district>.yaml, not drafted/): each is an answer key."""
    return sorted(p for p in (ITHACA / "5_zoning_rules").glob("*.yaml"))


def drafted_rules_for(district: str) -> list[dict]:
    """The drafted rules the checker would use for a district with no hand rulebook: its own and general.yaml's."""
    books = [DRAFTED / f"{district}.yaml", DRAFTED / "general.yaml"]
    return [r for b in books if b.exists() for r in load(b)["rules"]]


def drafted_as_checked(district: str, proven: frozenset | None = None) -> list[dict]:
    """The drafted rules as the checker reads them (rule_format.zone_rules): each exception composed into the rule it
    relaxes (apply_relaxes), an AI-drafted one widening only once proven (records/proven_relaxers.yaml), else the
    relaxed rule needs review where only it would pass. Graded so, the drafts' height row reads as the checker shows it
    (2026-10-27: graded apart, the chart's 35 ft failed a 37 ft house the §325-16C bonus allows)."""
    return apply_relaxes(drafted_rules_for(district), proven_relaxers(ITHACA) if proven is None else proven)


def _edges(rules: list[dict], point: dict, ctx, moved: str | None = None) -> list[tuple[str, float]]:
    """Where a verdict can turn near this design: for each comparison `measure op expression` in the rules, the
    expression's value here (the cap 35 + 0.1 * 35, a yard's 25 + (building_height - 35)); and for each min / max of a
    measure times a number and a number, the measure where the two meet (0.25 * lot_depth and 50: 200 ft). With
    `moved`, only the edges that measure moves (a yard's edge moves with the height)."""
    import ast
    from rule_format import formula
    out = []
    for r in rules:
        for t in [r.get("applies_when"), r.get("check")] + [w["when"] for w in r.get("review_when") or []]:
            if not t:
                continue
            for node in ast.walk(ast.parse(t, mode="eval")):
                if isinstance(node, ast.Compare):        # each link of a chain, either way round (#21 round 2)
                    sides = [node.left] + list(node.comparators)
                    for a, b in zip(sides, sides[1:]):
                        for name, other in ((a, b), (b, a)):
                            if not isinstance(name, ast.Name) or isinstance(other, ast.Name) and other.id == name.id:
                                continue
                            if moved is not None and moved not in {n.id for n in ast.walk(other)
                                                                   if isinstance(n, ast.Name)}:
                                continue
                            try:
                                v = formula.evaluate(ast.unparse(other), point, ctx.kinds())
                            except Exception:
                                continue
                            if type(v) in (int, float):
                                out.append((name.id, float(v)))
                if moved is None and isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("min", "max"):
                    consts = [a.value for a in node.args if isinstance(a, ast.Constant)]
                    for arg in node.args:
                        if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mult):
                            for k, n in [(arg.left, arg.right), (arg.right, arg.left)]:
                                if isinstance(k, ast.Constant) and isinstance(n, ast.Name) and k.value:
                                    out += [(n.id, c / k.value) for c in consts]
    return sorted(set(out))


def proof_points(hand_rule: dict, rules: list[dict], district: str, ctx) -> list[dict]:
    """design_points, then each design moved to just below, at and just above every edge a verdict can turn on
    (_edges); then each design moved so, moved again to the edges that move with it (a height on its cap moves each
    yard's edge): a slightly wrong cap (35 + 0.11 * 35) or a dropped 50 ft rear-yard cap is seen (#21 review: the
    plain grid jumped from 38.01 to 38.99 ft and never tried 200 ft)."""
    points = design_points(hand_rule, rules, district, ctx)
    seen = {tuple(sorted(p.items())) for p in points}
    every = [hand_rule] + rules

    def moves(frontier, by_moved):
        new = []
        for point, moved in frontier:
            for name, v in _edges(every, point, ctx, moved if by_moved else None):
                if name in ("use", "district") or type(point.get(name, 0)) is bool:
                    continue
                for d in (-0.001, 0.0, 0.001):
                    q = point | {name: round(v + d, 6)}
                    key = tuple(sorted(q.items()))
                    if q[name] >= 0 and key not in seen:
                        seen.add(key)
                        new.append((q, name))
        return new
    first = moves([(p, None) for p in points], False)
    second = moves(first, True)
    return points + [q for q, _ in first + second]


def relaxer_mismatches(hand_rule: dict, base: dict, relaxer: dict, district: str, ctx, first: bool = False) -> list[dict]:
    """Where an AI-drafted relaxer, composed into the rule it relaxes as a trusted one, gives a different verdict from
    the hand key's rule, over every design proof_points makes for them (design_points, then every edge a verdict can
    turn on, each side of it): [] proves them equal, the proof records/proven_relaxers.yaml needs."""
    composed = {r["id"]: r for r in apply_relaxes([base, relaxer], frozenset({relaxer["id"]}))}[base["id"]]
    points = proof_points(hand_rule, [base, relaxer], district, ctx)
    assert len(points) > 100, (hand_rule["id"], len(points))       # never a proof over (next to) no designs
    out = []
    for point in points:
        key, got = outcome(hand_rule, point, ctx.allowed()), outcome(composed, point, ctx.allowed())
        if key != got:
            out.append({"given": point, "key": key, "composed": got})
            if first:                  # one is enough to show a relaxer isn't proven
                break
    return out


MAPPING = REPO / "packages/rule_drafting/evals/2026-10-20_stage1/hand_to_drafted.yaml"


def mapping() -> dict:
    """The reviewed hand-to-drafted mapping (evals/2026-10-20_stage1/hand_to_drafted.yaml)."""
    return load(MAPPING) if MAPPING.exists() else {"keys": {}, "general_unmatched": {}}


def kinder(got: str, expect: str) -> bool:
    """The drafted answer lets through what the key doesn't: a pass, or "doesn't apply" (nothing shown), where the
    key says fail or needs review."""
    return got in ("pass", "not_applicable") and expect in ("fail", "needs_review")


def _formula_names(rules) -> set[str]:
    from rule_format import formula
    return {n for r in rules for t in rule_formulas(r) for n in formula.names(t)}


def _numbers_in(rules) -> set[float]:
    from rule_format import formula
    return {float(x) for r in rules for t in rule_formulas(r) for x in formula.numbers(t)}


def design_points(hand_rule: dict, rules: list[dict], district: str, ctx, limit: int = 4000,
                  uses: frozenset = frozenset()) -> list[dict]:
    """The designs the drafted rules are compared on: every hand example, each input it doesn't give filled in (a
    yes/no both ways; a number from the examples or a formula's constants), each with every use a formula names (and
    one it doesn't), then every input varied one at a time over its values: the examples' numbers and each constant
    and one either side. Every input has a value, so a "needs review" from a missing input never stands in for a
    verdict."""
    from rule_format import formula
    every = [hand_rule] + rules
    kinds = ctx.kinds()
    names = sorted(_formula_names(every) - {"district"})
    examples = [ex["given"] for r in every for ex in r.get("examples") or []] or [{}]
    constants = sorted(_numbers_in(every))
    values = {}
    for n in names:
        if n == "use":       # the uses the key allows in this district (a forbidden use fails on the use rule anyway)
            own = [ex["given"] for ex in hand_rule.get("examples") or []]
            values[n] = sorted(set(uses) | {v for f in rule_formulas(hand_rule) for name, v in formula.compared_strings(f)
                                            if name == "use"} | {g["use"] for g in own if isinstance(g.get("use"), str)}) or ["church"]
        elif kinds.get(n) == "boolean" or any(isinstance(g.get(n), bool) for g in examples):
            values[n] = [True, False]
        elif kinds.get(n) == "text":
            continue
        else:
            seen = {float(g[n]) for g in examples if type(g.get(n)) in (int, float)}
            near = {c + d for c in constants for d in (-1, 0, 1)} | {x + d for x in seen for d in (-0.01, 0, 0.01)}
            values[n] = sorted(v for v in seen | near if v >= 0)
    points, seen_points = [], set()

    def add(point):
        key = tuple(sorted(point.items()))
        if key not in seen_points and len(points) < limit:
            seen_points.add(key)
            points.append(point)
    import itertools
    flags = [n for n, v in values.items() if v == [True, False]][:6]          # every yes/no combination as a start
    # every use a formula names (and one none names) as a start too: varied from one use only, a zero-lot-line
    # house was only ever tried with no parking spaces, so a bedroom rule passing it where the key asks for review
    # was never seen (gap re-draft)
    named = sorted({v for r in every for f in rule_formulas(r) for name, v in formula.compared_strings(f) if name == "use"}
                   & (set(uses) or set(values.get("use", []))))     # a use the key forbids fails on its use rule
    starts = ([[u] for u in named + [next((u for u in values["use"] if u not in named), None)] if u is not None]
              if "use" in values else [[None]])
    for given in [ex["given"] for ex in hand_rule.get("examples") or []] or [{}]:
        for (use,), combo in itertools.product(starts, itertools.product([True, False], repeat=len(flags))):
            base = {"district": district} | {n: v[0] for n, v in values.items() if v} | dict(zip(flags, combo))
            base |= given | ({"use": use} if use is not None else {})
            add(base)
            for n, vs in values.items():
                for v in vs:
                    add(base | {n: v})
    return points


def _judge(rules: list[dict], point: dict, ctx) -> str:
    results = {outcome(r, point, ctx.allowed()) for r in rules}
    return next((x for x in ("fail", "needs_review", "pass") if x in results), "not_applicable")


def grade_mapped(book: dict, entries: dict, drafted: list[dict], ctx) -> dict:
    """Every worked example of a hand key, graded by its reviewed pairs (hand_to_drafted.yaml).
    Agreement: on the key's own examples, the mapped rules together (judge units and exception parts).
    False pass (review round 8): each judge unit's rules, and the exception parts as their own group, are compared with
    the hand rule as formulas, on every design design_points makes (each input filled in, varied one at a time): a
    false pass wherever the drafted rules pass or don't apply and the hand rule says fail or needs review. Flags are
    judged one by one, so a flag's permanent "needs review" can't hide another rule's pass; no input is left missing.
    A group that doesn't apply to a design isn't a false pass where another rule of the same question applies and
    fails it or sends it to review (parking: the bedroom rule for one-family houses, the flag for every other use)."""
    district = book["district"]
    by_id = {r["id"]: r for r in drafted}
    out = {"district": district, "total": 0, "agree": [], "disagree": [], "undrafted": [], "false_pass": []}
    use_rule = next((r for r in book["rules"] if r["id"] == f"{district}.use"), None)
    allowed = frozenset(u for u in ctx.uses if use_rule is None
                        or outcome(use_rule, {"use": u, "district": district}, ctx.allowed()) != "fail")
    for h in book["rules"]:
        assert h["id"] in entries, f"{h['id']}: not in hand_to_drafted.yaml (review it and add it)"
        e = entries[h["id"]]
        units = [[by_id[i] for i in u] for u in e.get("judge") or []]
        parts = [by_id[i] for i in e.get("parts") or []]
        every = [r for u in units for r in u] + parts
        same = e.get("same_measures") or {}             # a drafted measure that is the key's under another name
        for ex in h.get("examples", []):
            out["total"] += 1
            item = {"hand": h["id"], "given": ex["given"], "expect": ex["expect"]}
            if not every:
                out["undrafted"].append(item)
                continue
            given = ex["given"] | {d: ex["given"][k] for d, k in same.items() if k in ex["given"]}
            got, notes = combined(every, {"district": district} | given, ctx, set(ctx.proposed) - set(same))
            item |= {"got": got, "drafted": [r["id"] for r in every], "notes": notes}
            (out["agree"] if got == ex["expect"] else out["disagree"]).append(item)
        groups = [[r for r in u if r.get("kind") != "flag"] for u in units] + [[r] for u in units for r in u
                                                                             if r.get("kind") == "flag"] + [parts]
        # a measure only the hand key uses (described on the key's own branch) is evaluated as a number, as there
        own = {n: {"unit": "count", "meaning": "the hand key's own measure"} for n in _formula_names([h])
               if n not in ctx.kinds() and n not in ("use", "district")}
        saved, ctx.proposed = ctx.proposed, ctx.proposed | own
        try:
            for group in (g for g in groups if g):
                for point in design_points(h, group, district, ctx, uses=allowed):
                    point = point | {d: point[k] for d, k in same.items() if k in point}
                    key = outcome(h, point, ctx.allowed())
                    got = _judge(group, point, ctx)
                    if got == "not_applicable" and any(_judge(g, point, ctx) in ("fail", "needs_review")
                                                       for g in groups if g and g is not group):
                        continue                # another rule of this question applies here: the checker shows it
                    if kinder(got, key):
                        out["false_pass"].append({"hand": h["id"], "given": point, "expect": key, "got": got,
                                                  "drafted": [r["id"] for r in group],
                                                  "parts": group is parts})
                        break                           # one design per group is enough to show it
        finally:
            ctx.proposed = saved
    return out


def grade_hand_key(path, ctx, drafted=None) -> dict:
    """Every worked example of one hand key, each counted once: agree, disagree (with the drafted outcome), or
    undrafted (no drafted rule covers its hand rule: a miss, reported apart, never left out of the total). A false
    pass is a drafted pass, or a drafted "doesn't apply" (no failing item: the checker shows nothing), where the key
    says fail or needs review. drafted: the drafted rules (default: the district's and general.yaml's)."""
    book = load(path)
    district = book["district"]
    entries = mapping()["keys"].get(Path(path).name, {}).get("rules")
    if drafted is None and entries is not None:           # a key in the reviewed mapping: graded by its pairs
        return grade_mapped(book, entries, drafted_as_checked(district), ctx)
    drafted = drafted_as_checked(district) if drafted is None else drafted
    out = {"district": district, "total": 0, "agree": [], "disagree": [], "undrafted": [], "false_pass": []}
    for h in book["rules"]:
        cov = covering(h, drafted, ctx)
        for ex in h.get("examples", []):
            out["total"] += 1
            item = {"hand": h["id"], "given": ex["given"], "expect": ex["expect"]}
            if not cov:
                out["undrafted"].append(item)
                continue
            got, notes = combined(cov, {"district": district} | ex["given"], ctx, set(ctx.proposed))
            item |= {"got": got, "drafted": [r["id"] for r in cov], "notes": notes}
            (out["agree"] if got == ex["expect"] else out["disagree"]).append(item)
            if got in ("pass", "not_applicable") and ex["expect"] in ("fail", "needs_review"):
                out["false_pass"].append(item)
    return out


def test_every_hand_example_of_every_hand_key_is_counted(ctx):
    """Eval integrity (2026-10-20): 32/39 left out the 4 lot-width examples no drafted rule covered. Every example of
    every hand key now counts: agree + disagree + undrafted is its total."""
    if not (DRAFTED / "general.yaml").exists():
        pytest.skip("nothing drafted yet")
    for path in hand_keys():
        g = grade_hand_key(path, ctx)
        assert g["total"] == sum(len(r.get("examples", [])) for r in load(path)["rules"]) > 0
        assert len(g["agree"]) + len(g["disagree"]) + len(g["undrafted"]) == g["total"], path.name


def test_no_drafted_rule_passes_what_any_hand_key_does_not_beyond_the_known_list(ctx):
    """Never a false pass, against every hand key present: a drafted pass (or "doesn't apply") where the key says fail
    or needs review. The real ones the grader finds today are listed in hand_to_drafted.yaml (known_false_passes), each
    with its cause, until re-drafted: a new one fails here, and so does a fixed one until the list says so."""
    if not (DRAFTED / "general.yaml").exists():
        pytest.skip("nothing drafted yet")
    m = mapping()["keys"]
    found = {p.name: sorted({x["hand"] for x in grade_hand_key(p, ctx)["false_pass"]}) for p in hand_keys()}
    known = {p.name: sorted(m.get(p.name, {}).get("known_false_passes") or {}) for p in hand_keys()}
    assert found == known


FLOORS = REPO / "packages/rule_drafting/evals/2026-10-20_stage1/agreement_floors.yaml"


def test_agreement_with_every_hand_key_never_falls_below_its_recorded_floor(ctx):
    """How many worked examples the drafts get right is a reported eval metric (evals/2026-10-20_stage1/grade.json,
    every difference listed and judged), not a pass/fail test: the drafts' known differences are cautious (needs
    review or fail where the key passes). It may rise, never fall: a change that loses an agreement fails here. The
    hard rule is test_no_drafted_rule_passes_what_any_hand_key_does_not: never a false pass."""
    if not (DRAFTED / "general.yaml").exists():
        pytest.skip("nothing drafted yet")
    floors = load(FLOORS)
    for path in hand_keys():
        g = grade_hand_key(path, ctx)
        assert path.name in floors, f"{path.name}: no agreement floor recorded in {FLOORS.name}"
        assert len(g["agree"]) >= floors[path.name], (path.name, len(g["agree"]), floors[path.name],
                                                      [(x["hand"], x["given"], x["expect"], x["got"]) for x in g["disagree"]])


def test_a_declared_new_measure_is_supplied_from_the_drafts_own_passing_example(ctx):
    """Runs without drafts: a drafted rule that needs a measure the hand example doesn't give is judged with the
    value its own passing example gives it; one no example gives is named, never silently 'needs_review'."""
    rule = {"id": "R-1b.one_building", "kind": "rule", "check": "lot_area >= 6000 and not second_building",
            "examples": [{"given": {"lot_area": 6000, "second_building": False}, "expect": "pass"},
                         {"given": {"lot_area": 6000, "second_building": True}, "expect": "fail"}]}
    allowed = ctx.allowed() | {"second_building": "boolean"}
    assert outcome(rule, {"lot_area": 6000}, allowed) == "needs_review"          # what hid disagreements
    given, supplied, missing = with_new_measures(rule, {"lot_area": 5000}, {"second_building"})
    assert supplied == {"second_building": False} and missing == []
    assert outcome(rule, given, allowed) == "fail"                               # the real answer shows
    bare = rule | {"examples": [e for e in rule["examples"] if e["expect"] == "fail"]}
    assert with_new_measures(bare, {"lot_area": 5000}, {"second_building"})[2] == ["second_building"]
    # an ordinary measure the hand example lacks is named, never filled from the draft
    deep = {"id": "R-1b.depth", "kind": "rule", "check": "rear_yard >= 0.25 * lot_depth",
            "examples": [{"given": {"rear_yard": 25, "lot_depth": 100}, "expect": "pass"}]}
    got, notes = combined([deep], {"rear_yard": 25}, ctx)
    assert got == "needs_review" and any("['lot_depth'], which the hand example doesn't give" in n for n in notes)


def test_an_answer_key_example_is_judged_as_an_r1b_lot(ctx):
    """Runs without drafts: a drafted rule that names the district it doesn't apply to is decided on a hand
    example, which never says its district, instead of 'needs review' for a missing district."""
    rule = {"id": "R-1b.rear", "kind": "rule", "applies_when": 'district != "RU"', "check": "rear_yard >= 20",
            "examples": [{"given": {"rear_yard": 20}, "expect": "pass"}, {"given": {"rear_yard": 19}, "expect": "fail"}]}
    assert outcome(rule, {"rear_yard": 19}, ctx.allowed()) == "needs_review"
    assert judge_r1b_example([rule], {"rear_yard": 19}, ctx)[0] == "fail"


def test_a_law_pieces_rule_doesnt_cover_the_chart_rows_it_only_reads(ctx):
    """Runs without drafts: §325-16C's drafted 'front yard grows with extra height' reads the front-yard cell
    as an input; it covers the hand rule quoting §325-16C, not the hand front-yard rule quoting that row."""
    hand = load(ITHACA / "5_zoning_rules/R-1b.yaml")["rules"]
    front = next(h for h in hand if h["id"] == "R-1b.front_yard")
    cell = {"file": CHART, "page": 3, "cell": {"section": "Yard Dimensions", "row": "Front (minimum)", "column": "R-1B"}}
    bonus = {"id": "R-1b.325_16c_extra_front", "kind": "rule", "sources": [cell], "check": "front_yard >= 25"}
    assert covering(front, [bonus], ctx, from_law=set()) == [bonus]          # as a chart rule, it would
    assert covering(front, [bonus], ctx, from_law={bonus["id"]}) == []       # as a law piece's input, not


def exception_false_passes(hand, drafted, ctx, from_law=None):
    """Answer-key examples that fail, where the drafted rules from law pieces covering them, judged alone,
    pass. Each unit is drafted on its own, so a law exception (§325-16C's extra height with larger yards) and
    the chart limit it relaxes (35 ft) are separate rules, and today the limit's FAIL hides an incomplete
    exception. Once an exception can relax a limit, an exception that leaves out a requirement (one of the
    yards) would let an illegal design pass. Judged alone, it shows now."""
    from rule_format import formula
    from_law = law_unit_rules() if from_law is None else from_law
    found = []
    for h in hand:
        limited = formula.names(h["check"]) if h.get("check") else set()
        # a law rule answers this question only if its check limits something the hand rule's check does (§325-16C's
        # stories limit quotes the same sentence as the height bonus, but limits stories, not the height)
        rules = [r for r in covering(h, drafted, ctx, from_law) if r["id"] in from_law
                 and r.get("check") and formula.names(r["check"]) & limited]
        for ex in h["examples"] if rules else []:
            if ex["expect"] == "fail" and judge_r1b_example(rules, ex["given"], ctx)[0] == "pass":
                found.append(f"{h['id']} {ex['given']}: the hand key fails it; "
                             f"{', '.join(r['id'] for r in rules)} alone pass it")
    return found


def test_drafted_exception_rules_never_pass_what_the_answer_key_fails(hand, drafted_r1b, ctx):
    assert exception_false_passes(hand, drafted_r1b, ctx) == []


def test_an_exception_that_forgets_any_yard_is_caught(ctx):
    """Runs without drafts: §325-16C(1) enlarges each required front, side and rear yard. An exception rule set
    that leaves out any one of them passes an answer-key example where only that yard isn't enlarged, and is
    caught; the complete set is not flagged. (The smaller side yard stands for both sides: the larger one is
    never smaller.)"""
    hand = [h for h in load(ITHACA / "5_zoning_rules/R-1b.yaml")["rules"] if h["id"] == "R-1b.height"]
    quote = next(s for s in hand[0]["sources"] if s.get("quote", "").startswith("(1) Each required"))
    def rule(rid, check):
        return {"id": f"R-1b.x_{rid}", "kind": "rule", "sources": [quote], "applies_when": "building_height > 35",
                "check": check, "examples": []}
    yards = {"front": "front_yard >= 25 + (building_height - 35)",
             "sides": "side_yard_smaller >= 10 + (building_height - 35) and side_yard_larger >= 10 + (building_height - 35)",
             "rear": "rear_yard >= max(min(0.25 * lot_depth, 50), 20) + (building_height - 35)"}
    limit = rule("limit", "building_height <= 35 + 0.1 * 35")
    complete = [limit] + [rule(name, check) for name, check in yards.items()]
    assert exception_false_passes(hand, complete, ctx, from_law={r["id"] for r in complete}) == []
    for left_out in yards:
        rules = [r for r in complete if r["id"] != f"R-1b.x_{left_out}"]
        assert exception_false_passes(hand, rules, ctx, from_law={r["id"] for r in rules}) != [], left_out


def load_chart_test():
    """The chart reader's own R-1B test module: its row meanings (LIMITS), cells and helpers."""
    spec = importlib.util.spec_from_file_location(
        "r1b_chart", REPO / "packages/document_extraction/tests/test_r1b_matches_chart.py")
    chart = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chart)
    cells = [c for c in (json.loads(line) for line in chart.CELLS.open(encoding="utf-8"))
             if c.get("column") == chart.COLUMN and not c.get("heading")]
    return chart, cells


# Which side yard each side column binds is a reading of §325-8A(12)-(13) ("one side yard will be at least ...",
# "One side yard shall be at least ..."), an open question for the architects: R-2c's Column 12 (10/15 ft) is
# larger than its Column 13 (0/5/10 ft), which suggests the larger yard meets Column 12. R-1B's two minimums are
# both 10 ft, so either reading enforces the cell exactly; the chart reader's test uses one, a draft may use the other.
SIDE_ROWS = {"Side (one side minimum)", "Side (other side minimum)"}
OTHER_SIDE = {"side_yard_smaller": "side_yard_larger", "side_yard_larger": "side_yard_smaller",
              "side_yard_smaller_eaves": "side_yard_larger_eaves", "side_yard_larger_eaves": "side_yard_smaller_eaves"}


def side_cells_equal(chart, cells) -> bool:
    """R-1B's two side-yard minimums state the same numbers (only then can either reading be right)."""
    found = {c["row"]: chart.numbers(c["value"]) for c in cells if c["page"] == 3 and c["row"] in SIDE_ROWS}
    return len(found) == 2 and len({tuple(v) for v in found.values()}) == 1


def readings(key, chart, cells):
    """The chart reader's meanings of a row, plus, for a side-yard row whose two R-1B minimums are equal, the
    other side's reading."""
    out = list(chart.LIMITS[key])
    if key[2] in SIDE_ROWS and side_cells_equal(chart, cells):
        out += [(OTHER_SIDE[m], kind, {m: 100}, limit) for m, kind, fixed, limit in chart.LIMITS[key]]
    return out


def chart_value_results(rules, chart, cells, ctx):
    """(cited rows, rows enforced exactly, wrong) for the drafted chart rules (a law piece's rule takes chart
    cells as inputs, not as its limit). A row is enforced when, under some reading, the rule passes at the value
    and fails just past it; it's wrong when, under any reading, it does something else than that or not binding.
    The two side-yard rows are judged as a pair: enforced only if one binds the smaller side yard and the other
    the larger (either way round), never both the same yard."""
    cited, enforced, wrong = set(), set(), []
    binds = {}                                      # row -> the measures it was enforced on
    from_law = law_unit_rules()
    for rule in rules:
        passing = [ex["given"] for ex in rule.get("examples", []) if ex["expect"] == "pass"]
        if rule["kind"] != "rule" or not passing or rule["id"] in from_law:
            continue
        for c in chart.cited_rows(rule, cells):
            key = (c["page"], c["section"], c["row"])
            if key not in chart.LIMITS:
                continue
            cited.add(key)
            for measure, kind, fixed, limit in readings(key, chart, cells):
                bound = limit(chart.numbers(c["value"]))
                past = bound + (1 if measure in chart.COUNTS else 0.01) * (1 if kind == "max" else -1)
                at = outcome(rule, passing[0] | fixed | {measure: bound}, ctx.allowed())
                beyond = outcome(rule, passing[0] | fixed | {measure: past}, ctx.allowed())
                if (at, beyond) == ("pass", "fail"):
                    enforced.add(key)
                    binds.setdefault(key, set()).add(measure)
                elif (at, beyond) != ("pass", "pass"):
                    wrong.append(f"{rule['id']}: {measure} {kind} {bound} from {c['value']!r}: {at} at it, {beyond} past it")
    sides = [k for k in cited if k[2] in SIDE_ROWS]
    if len(sides) == 2 and not any(a != b for a in binds.get(sides[0], ()) for b in binds.get(sides[1], ())):
        enforced -= set(sides)
        wrong.append("the two side-yard minimums don't bind the two side yards (one the smaller, one the larger)")
    return cited, enforced, wrong


def test_drafted_r1b_turns_from_pass_to_fail_exactly_at_each_chart_value(drafted_r1b, ctx):
    """The hand examples can be loose (30 ft passes, 24 fails, whether the limit is 25 or 30). So each drafted
    R-1b rule is also tried at the R-1B chart value it cites and just past it, with the same row meanings the
    chart reader's own test uses: it must pass at the value and fail just past it, or not bind there."""
    chart, cells = load_chart_test()
    cited, enforced, wrong = chart_value_results(drafted_r1b, chart, cells, ctx)
    assert wrong == []
    assert sorted(cited - enforced) == []                     # every chart value a draft cites is enforced exactly
    assert idle_chart_numbers(drafted_r1b, chart, cells, ctx) == []       # and no cited number is ignored or idle


def test_either_reading_of_the_side_yard_columns_counts_and_a_wrong_number_still_shows(ctx, monkeypatch):
    """Runs without drafts: 'one side minimum' applied to the larger yard is enforced (R-1B's two minimums are
    equal); 12 ft where the chart says 10 is wrong under every reading."""
    chart, cells = load_chart_test()
    monkeypatch.setattr(sys.modules[__name__], "law_unit_rules", lambda: set())
    one_side = {"file": CHART, "page": 3, "cell": {"section": "Yard Dimensions", "row": "Side (one side minimum)", "column": "R-1B"}}
    def rule(check):
        return {"id": "R-1b.side", "kind": "rule", "sources": [one_side], "check": check,
                "examples": [{"given": {"side_yard_larger": 12, "side_yard_smaller": 12}, "expect": "pass"}]}
    cited, enforced, wrong = chart_value_results([rule("side_yard_larger >= 10")], chart, cells, ctx)
    assert wrong == [] and cited == enforced != set()
    cited, enforced, wrong = chart_value_results([rule("side_yard_larger >= 12 and side_yard_smaller >= 12")],
                                                 chart, cells, ctx)
    assert wrong != []
    other_side = {"file": CHART, "page": 3,
                  "cell": {"section": "Yard Dimensions", "row": "Side (other side minimum)", "column": "R-1B"}}
    same_yard = [rule("side_yard_larger >= 10"), rule("side_yard_larger >= 10") | {"id": "R-1b.side2", "sources": [other_side]}]
    cited, enforced, wrong = chart_value_results(same_yard, chart, cells, ctx)
    assert cited - enforced and wrong                    # both rows on the larger yard: the smaller has no limit
    one_each = [rule("side_yard_larger >= 10"), rule("side_yard_smaller >= 10") | {"id": "R-1b.side2", "sources": [other_side]}]
    cited, enforced, wrong = chart_value_results(one_each, chart, cells, ctx)
    assert cited == enforced and len(cited) == 2 and wrong == []
    key = (3, "Yard Dimensions", "Side (one side minimum)")         # the other reading only while R-1B's are equal
    assert len(readings(key, chart, cells)) == 2 * len(chart.LIMITS[key])
    unequal = [c | {"value": "5 ft"} if c["row"] == "Side (other side minimum)" else c for c in cells]
    assert len(readings(key, chart, unequal)) == len(chart.LIMITS[key])


def idle_chart_numbers(rules, chart, cells, ctx):
    """Every number of every chart cell a rule cites is used in its formula and decides something. Unlike the
    exact-limit test, this covers a law piece's rules too: they cite cells as inputs (§325-16C reads the yard
    minimums), which is exactly where a cell's number could sit idle without the exact-limit test noticing."""
    idle = []
    for rule in rules:
        # a rule relaxing another never passes on its own until proven equal to a hand-written key rule over the
        # generative grid (rule_format apply_relaxes, records/proven_relaxers.yaml): that proof tests its numbers, finer
        # than one example per number ('35 + 0.1 * 35': a tenth of a foot)
        if rule["kind"] == "rule" and not rule.get("relaxes"):
            idle += chart.idle_numbers(rule, [c for c in chart.cited_rows(rule, cells) if c["page"] != 2], ctx.allowed())
    return idle


def test_a_law_pieces_rule_that_ignores_a_cell_it_cites_is_caught(ctx, monkeypatch):
    """Runs without drafts: a §325-16C-style rule citing the front-yard cell but never using its 25 ft is caught,
    though it comes from a law piece (exempt only from the exact-limit test)."""
    chart, cells = load_chart_test()
    cell = {"file": CHART, "page": 3, "cell": {"section": "Yard Dimensions", "row": "Front (minimum)", "column": "R-1B"}}
    ignores = {"id": "R-1b.325_16c_extra_front", "kind": "rule", "sources": [cell], "applies_when": "building_height > 35",
               "check": "front_yard >= 1 + (building_height - 35)",
               "examples": [{"given": {"building_height": 36, "front_yard": 2}, "expect": "pass"},
                            {"given": {"building_height": 36, "front_yard": 1}, "expect": "fail"}]}
    monkeypatch.setattr(sys.modules[__name__], "law_unit_rules", lambda: {ignores["id"]})
    assert idle_chart_numbers([ignores], chart, cells, ctx) != []


def test_every_hand_rule_is_covered_once_drafting_is_complete(hand, drafted_r1b, ctx):
    if not (LOG.exists() and load(LOG).get("complete")):
        pytest.skip("drafting not complete yet")
    assert [h["id"] for h in hand if not covering(h, drafted_r1b, ctx)] == []


def test_drafted_r1b_matches_the_architects_spreadsheet(hand, drafted_r1b, ctx):
    design = load(SITE)
    values = {k: m["value"] for k, m in design["measurements"].items()} | R1B
    book = openpyxl.load_workbook(REPO / design["spreadsheet"], data_only=True)
    hand_by_id = {h["id"]: h for h in hand}
    complete = LOG.exists() and load(LOG).get("complete")
    wrong, compared = [], 0
    for row in book["Output"].iter_rows(min_row=3):
        label, theirs = row[0].value, row[6].value
        if not label:
            continue
        rules = covering(hand_by_id[design["compare"][label]], drafted_r1b, ctx)
        if not rules:
            assert not complete, f"{label}: no drafted rule covers it"
            continue
        compared += 1
        got, notes = combined(rules, values, ctx, set(ctx.proposed))
        if got != theirs.lower():
            wrong.append(f"{label}: they say {theirs}, drafted rules say {got}" + (f" [{'; '.join(notes)}]" if notes else ""))
    assert compared, "no spreadsheet row is covered by a drafted rule yet"
    assert wrong == []


def test_each_districts_chart_rules_cite_only_its_own_cells():
    books = sorted(p for p in DRAFTED.glob("*.yaml") if p.stem != "general")
    if not books:
        pytest.skip("nothing drafted yet")
    foreign = [(p.stem, r["id"], s["cell"]["column"]) for p in books for r in load(p)["rules"]
               for s in r["sources"] if "cell" in s and district_name(s["cell"]["column"]) != p.stem]
    assert foreign == []


def test_every_drafted_unit_produced_rules_a_reason_or_a_person_entry():
    if not LOG.exists():
        pytest.skip("nothing drafted yet")
    log = load(LOG)
    empty = [u for u, e in log["units"].items()
             if not (e["rules"] or e.get("reason") or e.get("unresolved") or e.get("failed") or e.get("withdrawn"))]
    assert empty == []


def test_every_drafted_rulebook_passes_the_inspector(ctx):
    books = sorted(DRAFTED.glob("*.yaml"))
    if not books:
        pytest.skip("nothing drafted yet")
    assert {p.name: validate(load(p), ctx) for p in books} == {p.name: [] for p in books}


def test_a_hand_rule_about_its_cells_is_matched_by_a_drafted_rule_citing_them(ctx):
    """The hand R-3a cites chart cells as its subject (with the law's column definitions), and stage 1's grade counted
    its yards, coverage and use rules as undrafted although drafted rules cite the same cells. A cell match also
    needs a shared measure (a cell cited as an input isn't the subject), and a rule quoting another section's chart
    row (the R-1b height rule, citing yard cells as inputs) keeps matching only by its quotes."""
    side = {"file": CHART, "page": 3, "cell": {"section": "Yard Dimensions", "row": "Side (one side minimum)",
                                               "column": "R-3A"}}
    law = {"file": "chapter_325_zoning_2026-10.pdf", "page": 25, "lines": [15, 17], "quote": "Column 12"}
    drafted = {"id": "R-3a.side", "check": "side_yard_larger >= 10", "sources": [side]}
    hand = {"id": "h", "check": "side_yard_larger >= 10", "sources": [side, law]}
    assert covering(hand, [drafted], ctx, from_law=set()) == [drafted]
    as_input = hand | {"check": "accessory_side_yard >= 3"}
    assert covering(as_input, [drafted], ctx, from_law=set()) == []
    height = next(c for (pg, sec, row, col), c in ctx.cells[CHART].items() if pg == 3 and sec.startswith("Maximum Building")
                  and col == "R-3A")
    quoted = {"file": CHART, "page": 3, "lines": [height["row_lines"][0]] * 2, "quote": "Feet 35 35 35"}
    other = hand | {"check": "building_height <= 40 and side_yard_larger >= 10", "sources": [quoted, side]}
    assert covering(other, [drafted], ctx, from_law=set()) == []


GRADE = REPO / "packages/rule_drafting/evals/2026-10-20_stage1/grade.json"


def test_the_committed_grade_is_the_grade_of_these_drafts(ctx):
    """evals/2026-10-20_stage1/grade.json is grade_all.py's output for the drafts and hand keys of this checkout:
    regenerated whenever either changes (`python packages/rule_drafting/evals/2026-10-20_stage1/grade_all.py
    packages/rule_drafting/evals/2026-10-20_stage1/grade.json`)."""
    if not (DRAFTED / "general.yaml").exists():
        pytest.skip("nothing drafted yet")
    committed = json.loads(GRADE.read_text(encoding="utf-8"))
    assert sorted(committed) == [p.name for p in hand_keys()]
    for path in hand_keys():
        g = grade_hand_key(path, ctx)
        assert committed[path.name]["summary"]["agree"] == len(g["agree"]), path.name
        assert committed[path.name]["summary"]["disagree"] == len(g["disagree"]), path.name
        assert committed[path.name]["summary"]["undrafted"] == len(g["undrafted"]), path.name


def test_a_drafted_rule_that_doesnt_apply_where_the_key_fails_is_a_false_pass(ctx, tmp_path):
    """Review round 1: only a drafted "pass" counted. A drafted rule whose condition is too narrow (§325-19E's
    lot-area rule leaving out group houses) shows nothing at all, a silent pass, where the key says fail."""
    import yaml
    side = {"file": CHART, "page": 3, "cell": {"section": "Yard Dimensions", "row": "Side (one side minimum)",
                                               "column": "R-3A"}}
    key = tmp_path / "R-3a.yaml"
    key.write_text(yaml.safe_dump({"district": "R-3a", "rules": [
        {"id": "R-3a.k", "check": "side_yard_larger >= 10", "sources": [side],
         "examples": [{"given": {"side_yard_larger": 4, "use": "dormitory"}, "expect": "fail"}]}]}), encoding="utf-8")
    narrow = {"id": "R-3a.d", "kind": "rule", "applies_when": 'use == "one_family_detached"',
              "check": "side_yard_larger >= 10", "sources": [side]}
    g = grade_hand_key(key, ctx, drafted=[narrow])
    assert len(g["false_pass"]) == 1 and g["false_pass"][0]["got"] == "not_applicable"
    nothing = grade_hand_key(key, ctx, drafted=[])         # no drafted rule: counted as undrafted, never left out
    assert nothing["total"] == 1 and len(nothing["undrafted"]) == 1


def test_a_rule_citing_use_rows_as_inputs_isnt_covered_by_the_permitted_use_rule(ctx):
    """The blind R-2 keys: R-2c's side-yard minimums depend on the use, so the key cites the use rows; the harness
    matched the drafted permitted-use rule (use in [...]) and judged the side yards as passing: a false pass of the
    grader. Use picks which number applies; a cell match needs a measure in common."""
    use_cell = {"file": CHART, "page": 2, "cell": {"section": "Primary Uses", "row": "One-family dwelling, semi-detached [fn4]",
                                                   "column": "R-2C"}}
    side = {"file": CHART, "page": 3, "cell": {"section": "Yard Dimensions", "row": "Side (other side minimum)",
                                               "column": "R-2C"}}
    hand = {"id": "h", "check": 'side_yard_smaller >= (10 if use == "one_family_semi_detached" else 5)',
            "sources": [use_cell, side]}
    use_rule = {"id": "R-2c.use", "check": 'use in ["one_family_semi_detached"]', "sources": [use_cell]}
    assert covering(hand, [use_rule], ctx, from_law=set()) == []
    hand_use = {"id": "hu", "kind": "flag", "applies_when": 'use in ["one_family_semi_detached"]', "sources": [use_cell]}
    assert covering(hand_use, [use_rule], ctx, from_law=set()) == [use_rule]      # two use rules still match


def test_a_hand_flag_is_covered_by_a_numeric_draft_on_its_cell_and_a_wrong_pass_shows(ctx, tmp_path, monkeypatch):
    """Review round 6: a hand rule that measures nothing (a use flag) required the draft to measure nothing too, so a
    numeric drafted rule on the same cell was filed undrafted, and its pass against the key's needs review never
    reached false_pass."""
    import yaml
    monkeypatch.setattr(ctx, "proposed", ctx.proposed | {"persons_housed": {"unit": "count", "meaning": "persons housed"}})
    cell = {"file": CHART, "page": 14, "cell": {"section": "Residential", "row": "Dormitory", "column": "R-3A"}}
    if not any(k[1] == "Residential" and k[2] == "Dormitory" for k in ctx.cells.get(CHART, {})):
        cell = {"file": CHART, "page": 2, "cell": {"section": "Primary Uses", "row": "Dormitory", "column": "R-3A"}}
    flag = {"id": "R-3a.k", "kind": "flag", "applies_when": 'use == "dormitory"', "sources": [cell],
            "examples": [{"given": {"use": "dormitory", "parking_spaces": 9, "persons_housed": 8},
                          "expect": "needs_review"}]}
    numeric = {"id": "R-3a.d", "kind": "rule", "applies_when": 'use == "dormitory"',
               "check": "parking_spaces >= persons_housed / 4", "sources": [cell]}
    assert covering(flag, [numeric], ctx, from_law=set()) == [numeric]
    key = tmp_path / "R-3a.yaml"
    key.write_text(yaml.safe_dump({"district": "R-3a", "rules": [flag]}), encoding="utf-8")
    g = grade_hand_key(key, ctx, drafted=[numeric])
    assert len(g["false_pass"]) == 1 and g["false_pass"][0]["got"] == "pass"


def test_no_example_counted_undrafted_has_a_draft_on_its_cell_doing_the_same_job(ctx):
    """Round 6's guard, across every hand key present: an example counted undrafted must have no drafted rule that
    cites one of its hand rule's cells (by cell) and does the same job: measures the same thing, or, for a hand rule
    that measures nothing, selects one of its uses. Otherwise the grader is hiding a covered rule from the grade."""
    from rule_format import formula
    if not (DRAFTED / "general.yaml").exists():
        pytest.skip("nothing drafted yet")

    def cells(rule):
        return {(s["page"], s["cell"]["section"], s["cell"]["row"].strip(), s["cell"]["column"])
                for s in rule.get("sources") or [] if "cell" in s}

    def measured(rule):
        return {n for t in rule_formulas(rule) for n in formula.names(t)} - {"district", "use"}
    for path in hand_keys():
        g = grade_hand_key(path, ctx)
        book = {r["id"]: r for r in load(path)["rules"]}
        drafted = drafted_rules_for(g["district"])
        notes = mapping()["keys"].get(path.name, {}).get("rules", {})
        for hid in {x["hand"] for x in g["undrafted"]}:
            h = book[hid]
            for r in drafted:
                if not cells(h) & cells(r) or r["id"] in (notes.get(hid, {}).get("not_same") or {}):
                    continue
                job = measured(h) & measured(r) if measured(h) else selected_uses(h) & selected_uses(r)
                assert not job, (path.name, hid, r["id"])


def test_every_hand_and_drafted_rule_is_in_the_reviewed_mapping(ctx):
    """Review round 7: matching by citations opened a new blind spot each time it was tuned. The pairs are now a frozen
    file reviewed by hand from the law; a hand rule or a drafted rule it doesn't account for fails here, so a new
    draft or a new key forces a new review."""
    if not (DRAFTED / "general.yaml").exists():
        pytest.skip("nothing drafted yet")
    m = mapping()
    general = {r["id"] for r in load(DRAFTED / "general.yaml")["rules"]}
    general_mapped = set()
    for path in hand_keys():
        assert path.name in m["keys"], f"{path.name}: not in hand_to_drafted.yaml (review its rules)"
        k = m["keys"][path.name]
        hand = {r["id"] for r in load(path)["rules"]}
        assert set(k["rules"]) == hand, (path.name, sorted(hand ^ set(k["rules"])))
        drafted = {r["id"] for r in drafted_rules_for(k["district"])}
        named = {i for e in k["rules"].values() for u in e.get("judge") or [] for i in u} | \
            {i for e in k["rules"].values() for i in e.get("parts") or []}
        assert named <= drafted, (path.name, sorted(named - drafted))            # no stale id
        assert all(e.get("reason") for e in k["rules"].values())
        own = {i for i in drafted if not i.startswith("general.")}
        assert own - named == set(k["unmatched"]), (path.name, sorted((own - named) ^ set(k["unmatched"])))
        general_mapped |= named & general
    # a general rule is acknowledged by any key of the reviewed file (a key on another branch included)
    general_mapped |= {i for k in m["keys"].values() for e in k["rules"].values()
                       for i in [x for u in e.get("judge") or [] for x in u] + list(e.get("parts") or [])} & general
    assert general - general_mapped == set(m["general_unmatched"]), sorted((general - general_mapped) ^ set(m["general_unmatched"]))
    # and every key in the mapping is graded by its pairs: each graded example names only its hand rule's mapped rules
    for path in hand_keys():
        rules = m["keys"][path.name]["rules"]
        g = grade_hand_key(path, ctx)
        for x in g["agree"] + g["disagree"]:
            e = rules[x["hand"]]
            mapped = {i for u in e.get("judge") or [] for i in u} | set(e.get("parts") or [])
            assert set(x["drafted"]) <= mapped, (path.name, x["hand"], sorted(set(x["drafted"]) - mapped))


def _loosened(rule: dict, review: bool = True) -> dict:
    """The rule with its check made always true, its applies_when and review_when kept (a flag becomes such a rule);
    with review=False its review_when dropped too: a rule whose job for this hand rule is its review conditions
    (RU.use sends the three uses note 5 spaces 500 ft apart to review, PR #30's key) is probed by losing them."""
    loose = rule | {"kind": "rule", "check": "0 <= 0"}
    return loose if review else {k: v for k, v in loose.items() if k != "review_when"}


def test_the_grader_catches_every_mapped_rule_loosened(ctx):
    """Mutation test (review rounds 7, 8): every drafted rule mapped to a hand rule, judge members and exception parts
    alike, one at a time, its check loosened to always true with its conditions kept, must be reported as a false
    pass: no rule's mistake can hide behind another rule or a missing input."""
    if not (DRAFTED / "general.yaml").exists():
        pytest.skip("nothing drafted yet")
    m = mapping()
    missed, tried = [], 0
    for path in hand_keys():
        book, entries = load(path), m["keys"][path.name]["rules"]
        drafted = drafted_rules_for(book["district"])
        base = {h["id"]: grade_mapped(book | {"rules": [h]}, entries, drafted, ctx)["false_pass"] for h in book["rules"]}
        for h in book["rules"]:
            e = entries[h["id"]]
            for rid in sorted({i for u in e.get("judge") or [] for i in u} | set(e.get("parts") or [])):
                tried += 1
                flipped = [_loosened(r) if r["id"] == rid else r for r in drafted]
                g = grade_mapped(book | {"rules": [h]}, entries, flipped, ctx)
                if len(g["false_pass"]) <= len(base[h["id"]]) and not any(rid in x["drafted"] for x in g["false_pass"]):
                    bare = [_loosened(r, review=False) if r["id"] == rid else r for r in drafted]
                    g = grade_mapped(book | {"rules": [h]}, entries, bare, ctx)     # its job may be its review
                    if len(g["false_pass"]) <= len(base[h["id"]]) and not any(rid in x["drafted"] for x in g["false_pass"]):
                        missed.append((path.name, h["id"], rid))
    assert tried and missed == []


def test_a_dropped_special_permit_use_is_a_false_pass_whatever_else_cites_the_use_rows(ctx):
    """Review round 7 (P0): drafted R-3a.use with 'school' taken out of its special-permit list shows nothing for a
    school, a false pass. The citation matcher also paired the hand flag with numeric rules that only quote the use
    rows as inputs, whose missing lot area gave needs review and hid it. Judged by the reviewed pair on its own, it
    shows."""
    hand_flag = {"id": "R-3a.use", "kind": "flag", "applies_when": 'use in ["school"]',
                 "examples": [{"given": {"use": "school"}, "expect": "needs_review"}]}
    use = next(r for r in load(DRAFTED / "R-3a.yaml")["rules"] if r["id"] == "R-3a.use")
    dropped = use | {"applies_when": use["applies_when"].replace('"school", ', "").replace(', "school"', "")}
    assert '"school"' not in dropped["applies_when"]
    lot = next(r for r in load(DRAFTED / "R-3a.yaml")["rules"]
               if r["id"].startswith("R-3a.min_lot_") and r["id"].endswith("_other_use"))     # its id per answer
    entries = {"R-3a.use": {"judge": [["R-3a.use"]], "reason": "x"}}
    g = grade_mapped({"district": "R-3a", "rules": [hand_flag]}, entries, [dropped, lot], ctx)
    assert [x["got"] for x in g["false_pass"]] == ["not_applicable"]
    assert grade_mapped({"district": "R-3a", "rules": [hand_flag]}, entries, [use, lot], ctx)["false_pass"] == []


def test_a_measure_declared_the_same_is_given_one_value_on_the_keys_own_examples_too(ctx, monkeypatch):
    """Review round 9: same_measures was applied only to the false-pass designs; on the key's own examples the draft's
    measure was filled from its own passing example (4 units), so the right 3-to-6 rule showed passing 2 and 7."""
    monkeypatch.setattr(ctx, "proposed", ctx.proposed | {
        "dwelling_units_in_building": {"unit": "count", "meaning": "dwelling units in the building"},
        "attached_units_in_building": {"unit": "count", "meaning": "attached units in the building"}})
    hand = {"id": "R-2c.k", "kind": "rule", "applies_when": 'use == "one_family_attached"',
            "check": "attached_units_in_building >= 3 and attached_units_in_building <= 6",
            "examples": [{"given": {"use": "one_family_attached", "attached_units_in_building": n}, "expect": e}
                         for n, e in ((2, "fail"), (4, "pass"), (7, "fail"))]}
    drafted = {"id": "general.d", "kind": "rule", "applies_when": 'use == "one_family_attached"',
               "check": "dwelling_units_in_building >= 3 and dwelling_units_in_building <= 6", "sources": [],
               "examples": [{"given": {"use": "one_family_attached", "dwelling_units_in_building": 4}, "expect": "pass"}]}
    entries = {"R-2c.k": {"judge": [["general.d"]], "reason": "x",
                          "same_measures": {"dwelling_units_in_building": "attached_units_in_building"}}}
    g = grade_mapped({"district": "R-2c", "rules": [hand]}, entries, [drafted], ctx)
    assert len(g["agree"]) == 3 and g["disagree"] == [] and g["false_pass"] == []


def test_a_rule_that_doesnt_apply_is_no_false_pass_where_another_rule_of_the_question_covers_the_design(ctx):
    """Parking after the gap re-draft: the bedroom rule applies to one-family houses, a code-made flag to every other
    use. Neither alone answers a church and a one-family house, but together they do; a pass is still never hidden."""
    hand = {"id": "R-1a.k", "kind": "flag", "applies_when": 'use != "one_family_detached"',
            "examples": [{"given": {"use": "church"}, "expect": "needs_review"}]}
    rule = {"id": "R-1a.r", "kind": "rule", "applies_when": 'use == "one_family_detached"', "check": "parking_spaces >= 1",
            "sources": [], "examples": [{"given": {"use": "one_family_detached", "parking_spaces": 1}, "expect": "pass"}]}
    flag = {"id": "R-1a.f", "kind": "flag", "applies_when": 'use != "one_family_detached"', "sources": []}
    entries = {"R-1a.k": {"judge": [["R-1a.r", "R-1a.f"]], "reason": "x"}}
    assert grade_mapped({"district": "R-1a", "rules": [hand]}, entries, [rule, flag], ctx)["false_pass"] == []
    alone = {"R-1a.k": {"judge": [["R-1a.r"]], "reason": "x"}}
    assert grade_mapped({"district": "R-1a", "rules": [hand]}, alone, [rule], ctx)["false_pass"]
    loose = flag | {"applies_when": 'use != "church"'}         # the flag misses the church: the rule's N/A counts again
    assert grade_mapped({"district": "R-1a", "rules": [hand]}, entries, [rule, loose], ctx)["false_pass"]


def test_the_grid_tries_every_use_a_formula_names_with_its_other_inputs_varied(ctx):
    """The key flags a zero-lot-line house's parking (needs review); a draft's bedroom rule passes it with enough
    spaces. Varied from the key's example uses only, the grid tried that house with no spaces, so the pass was never
    seen."""
    hand = {"id": "R-2c.k", "kind": "flag", "applies_when": 'use in ["one_family_detached_zero_lot_line", "two_family"]',
            "examples": [{"given": {"use": "two_family"}, "expect": "needs_review"}]}
    rule = {"id": "R-2c.r", "kind": "rule", "check": "parking_spaces >= 1", "sources": [],
            "applies_when": 'use in ["one_family_detached", "one_family_detached_zero_lot_line"]',
            "examples": [{"given": {"use": "one_family_detached", "parking_spaces": 1}, "expect": "pass"}]}
    points = design_points(hand, [rule], "R-2c", ctx)
    assert any(p["use"] == "one_family_detached_zero_lot_line" and p["parking_spaces"] >= 1 for p in points)
    flag = {"id": "R-2c.f", "kind": "flag", "applies_when": 'use == "two_family"', "sources": []}   # covers two-family
    got = grade_mapped({"district": "R-2c", "rules": [hand]}, {"R-2c.k": {"judge": [["R-2c.r", "R-2c.f"]], "reason": "x"}},
                       [rule, flag], ctx)
    assert [(x["given"]["use"], x["got"]) for x in got["false_pass"]] == [("one_family_detached_zero_lot_line", "pass")]


def test_every_mapping_reason_describes_the_drafts_there_are():
    """Review round 15: after §325-16C's parts were refused, the height reasons still said the bonus was "drafted as
    separate rules: parts of the answer", and the eaves reasons named a flag no longer drafted. A reason that
    claims parts has parts, and a drafted rule id a reason names is drafted."""
    import re as _re
    m = mapping()
    stale = []
    for name, k in m["keys"].items():
        have = {r["id"] for r in drafted_rules_for(k["district"])}
        for hid, e in k["rules"].items():
            if "parts of the answer" in e["reason"] and not e.get("parts"):
                stale.append((name, hid, "claims parts"))
            held = {i for u in e.get("held_judge") or [] for i in u}   # out of the rulebook while on hold
            for rid in _re.findall(r"\b(?:general|R-\w+)\.[a-z0-9_]+\b", e["reason"]):
                if rid not in have and rid not in held:
                    stale.append((name, hid, rid))
    assert stale == []


def test_a_law_rule_limiting_another_measure_doesnt_answer_the_height_question(ctx):
    """2026-10-25: §325-16C's stories limit ('above the chart height, stories <= the chart stories') quotes the
    bonus's sentence, so it was judged as the height bonus and 'passed' a 37 ft house the key fails; the chart's
    height rule fails that house. A law rule answers a hand rule only where its check limits what the hand rule's does;
    a law rule on the height itself still does."""
    hand = [h for h in load(ITHACA / "5_zoning_rules/R-1b.yaml")["rules"] if h["id"] == "R-1b.height"]
    quote = next(s for s in hand[0]["sources"] if s.get("quote", "").startswith("(1) Each required"))
    stories = {"id": "R-1b.x_stories", "kind": "rule", "sources": [quote], "applies_when": "building_height > 35",
               "check": "stories <= 3", "examples": []}
    assert exception_false_passes(hand, [stories], ctx, from_law={stories["id"]}) == []
    height = stories | {"id": "R-1b.x_limit", "check": "building_height <= 35 + 0.1 * 35"}
    assert exception_false_passes(hand, [height], ctx, from_law={height["id"]}) != []


def test_a_held_parking_question_says_it_is_on_hold_and_keeps_its_reviewed_pairs():
    """Parking-hold review: the 17 parking entries said the re-draft 'was refused by the checks'; the rules were drafted
    and checked, then put on hold (Ben, 2026-10-25). The reason says so, and held_judge keeps the reviewed pairs."""
    m = mapping()
    held = [(k, hid, e) for k in m["keys"].values() for hid, e in k["rules"].items()
            if hid.split(".", 1)[1].startswith("parking_") and e.get("held_judge")]
    assert held
    for _, hid, e in held:
        assert e["judge"] == [] and e["reason"].startswith("not checked yet: parking is on hold"), hid
        assert "refused by the checks" not in e["reason"], hid


def test_a_rule_whose_job_is_its_review_is_probed_by_losing_it(ctx):
    """PR #30's RU key: RU.spacing_500_ft (note 5) is answered by RU.use's review of the three uses, so loosening
    RU.use's check alone changes nothing; dropping its review too must show as a false pass."""
    hand = {"id": "RU.spacing", "kind": "flag", "applies_when": 'use == "dormitory"',
            "examples": [{"given": {"use": "dormitory"}, "expect": "needs_review"}]}
    use = {"id": "RU.u", "kind": "rule", "check": 'use in ["two_family"]', "sources": [],
           "review_when": [{"when": 'use == "dormitory"', "reason": "note 5"}]}
    entries = {"RU.spacing": {"judge": [["RU.u"]], "reason": "x"}}
    book = {"district": "RU", "rules": [hand]}
    assert grade_mapped(book, entries, [use], ctx)["false_pass"] == []
    assert grade_mapped(book, entries, [_loosened(use)], ctx)["false_pass"] == []            # the check alone: idle
    assert grade_mapped(book, entries, [_loosened(use, review=False)], ctx)["false_pass"]    # its review: caught


PROVEN = ITHACA / "5_zoning_rules/drafted/records/proven_relaxers.yaml"


def test_every_proven_relaxer_equals_the_hand_key_rule_it_stands_for(ctx):
    """records/proven_relaxers.yaml (2026-10-27): each AI-drafted relaxer listed there widens the rule it relaxes
    because, composed into it, it gives the hand key's verdict on every design proof_points makes. Each is proven again
    here, against its key (which must be in this checkout: no unchecked entry), and its fingerprint is the rule as it
    now stands (rule_format trusts that content only)."""
    from rule_format.rulebook import relaxer_fingerprint
    proven = load(PROVEN) or {}
    assert proven, "nothing proven"
    for rid, entry in proven.items():
        district = rid.split(".", 1)[0]
        said = re.search(r"relaxer_mismatches: equals (\S+) \((\S+\.yaml)\)", entry["proof"])
        assert said and said.group(2) == f"{district}.yaml", (rid, entry)
        key_path = ITHACA / "5_zoning_rules" / said.group(2)
        assert key_path.exists(), f"{rid}: proven against {said.group(2)}, which this checkout doesn't have"
        drafted = {r["id"]: r for r in drafted_rules_for(district)}
        relaxer = drafted[rid]
        assert entry["fingerprint"] == relaxer_fingerprint(relaxer), f"{rid}: changed since it was proven"
        hand = {r["id"]: r for r in load(key_path)["rules"]}[said.group(1)]
        assert relaxer_mismatches(hand, drafted[relaxer["relaxes"]], relaxer, district, ctx) == [], rid


def test_a_relaxer_that_leaves_out_a_condition_is_never_proven(ctx):
    """The proof is not vacuous: §325-16C's bonus with the side yards left out, or a 20% allowance, differs from the
    hand key somewhere on the designs."""
    district = "R-1b"
    drafted = {r["id"]: r for r in drafted_rules_for(district)}
    relaxer = drafted["R-1b.325_16c_height_exception_extra_height"]
    hand = {r["id"]: r for r in load(ITHACA / "5_zoning_rules/R-1b.yaml")["rules"]}["R-1b.height"]
    base = drafted[relaxer["relaxes"]]
    assert relaxer_mismatches(hand, base, relaxer, district, ctx) == []
    no_sides = relaxer | {"applies_when": relaxer["applies_when"].replace(
        " and side_yard_larger >= 10 + (building_height - 35) and side_yard_smaller >= 10 + (building_height - 35)", "")}
    assert no_sides["applies_when"] != relaxer["applies_when"]
    assert relaxer_mismatches(hand, base, no_sides, district, ctx, first=True)
    twenty = relaxer | {"check": "building_height <= 35 + 0.2 * 35"}
    assert relaxer_mismatches(hand, base, twenty, district, ctx, first=True)
    # #21 review: a cap a little off, either way, and a rear-yard cap loosened or dropped, are seen too
    for check in ("building_height <= 35 + 0.11 * 35", "building_height <= 35 + 0.1 * 35 + 0.4",
                  "building_height <= 35 + 0.1 * 35 - 0.4"):
        assert relaxer_mismatches(hand, base, relaxer | {"check": check}, district, ctx, first=True), check
    # #21 round 2: written the other way round, a hair off the key's edge
    for check in ("35 + 0.1 * 35 + 0.0009 >= building_height", "0 <= building_height <= 38.5009"):
        assert relaxer_mismatches(hand, base, relaxer | {"check": check}, district, ctx, first=True), check
    side = relaxer | {"applies_when": relaxer["applies_when"].replace(
        "side_yard_larger >= 10 + (building_height - 35)", "10 + (building_height - 35) - 0.0005 <= side_yard_larger")}
    assert side["applies_when"] != relaxer["applies_when"]
    assert relaxer_mismatches(hand, base, side, district, ctx, first=True)
    for rear in ("max(20, min(0.25 * lot_depth, 48))", "max(20, 0.25 * lot_depth)", "max(18, min(0.25 * lot_depth, 50))"):
        loose = relaxer | {"applies_when": relaxer["applies_when"].replace("max(20, min(0.25 * lot_depth, 50))", rear)}
        assert loose["applies_when"] != relaxer["applies_when"]
        assert relaxer_mismatches(hand, base, loose, district, ctx, first=True), rear


def test_the_height_row_is_graded_as_the_checker_reads_it(ctx):
    """2026-10-27: graded rule by rule, the chart's 35 ft failed the hand key's 37 ft house with every yard increased
    (the §325-16C bonus, drafted as its own rule relaxing it). Composed as the checker composes it, and proven equal to
    the key, every height example agrees."""
    if not (DRAFTED / "general.yaml").exists():
        pytest.skip("nothing drafted yet")
    for path in hand_keys():
        g = grade_hand_key(path, ctx)
        assert not [x for x in g["disagree"] if x["hand"].endswith(".height")], path.name
