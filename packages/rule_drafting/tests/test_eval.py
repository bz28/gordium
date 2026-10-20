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
from pathlib import Path

import openpyxl
import pytest

from rule_format.rulebook import Context, _cited_lines, district_name, load, outcome, validate

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
    wanted = lines(hand_rule, quotes_only=True)
    return [r for r in drafted if lines(r, quotes_only=r["id"] in from_law) & wanted]


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


def test_drafted_r1b_agrees_with_the_hand_drafted_r1b(hand, drafted_r1b, ctx):
    disagreements, compared = [], 0
    for h in hand:
        rules = covering(h, drafted_r1b, ctx)
        if not rules:
            continue                                   # not drafted yet; test_every_hand_rule_is_covered checks
        for ex in h["examples"]:
            compared += 1
            got, notes = judge_r1b_example(rules, ex["given"], ctx)
            if got != ex["expect"]:
                disagreements.append(f"{h['id']} {ex['given']}: hand {ex['expect']}, drafted {got} "
                                     f"({', '.join(r['id'] for r in rules)})" + (f" [{'; '.join(notes)}]" if notes else ""))
    assert compared, "no drafted rule covers any hand rule"
    assert disagreements == []


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


def test_drafted_r1b_turns_from_pass_to_fail_exactly_at_each_chart_value(drafted_r1b, ctx):
    """The hand examples can be loose (30 ft passes, 24 fails, whether the limit is 25 or 30). So each drafted
    R-1b rule is also tried at the R-1B chart value it cites and just past it, with the same row meanings the
    chart reader's own test uses: it must pass at the value and fail just past it, or not bind there."""
    spec = importlib.util.spec_from_file_location(
        "r1b_chart", REPO / "packages/document_extraction/tests/test_r1b_matches_chart.py")
    chart = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chart)
    cells = [c for c in (json.loads(line) for line in chart.CELLS.open(encoding="utf-8"))
             if c.get("column") == chart.COLUMN and not c.get("heading")]
    cited, enforced, wrong = set(), set(), []
    from_law = law_unit_rules()                   # a law piece's rule takes chart cells as inputs, not as its limit
    for rule in drafted_r1b:
        passing = [ex["given"] for ex in rule.get("examples", []) if ex["expect"] == "pass"]
        if rule["kind"] != "rule" or not passing or rule["id"] in from_law:
            continue
        for c in chart.cited_rows(rule, cells):
            key = (c["page"], c["section"], c["row"])
            if key not in chart.LIMITS:
                continue
            cited.add(key)
            for measure, kind, fixed, limit in chart.LIMITS[key]:
                bound = limit(chart.numbers(c["value"]))
                past = bound + (1 if measure in chart.COUNTS else 0.01) * (1 if kind == "max" else -1)
                at = outcome(rule, passing[0] | fixed | {measure: bound}, ctx.allowed())
                beyond = outcome(rule, passing[0] | fixed | {measure: past}, ctx.allowed())
                if (at, beyond) == ("pass", "fail"):
                    enforced.add(key)
                elif (at, beyond) != ("pass", "pass"):
                    wrong.append(f"{rule['id']}: {measure} {kind} {bound} from {c['value']!r}: {at} at it, {beyond} past it")
    assert wrong == []
    assert sorted(cited - enforced) == []                     # every chart value a draft cites is enforced exactly
    idle = []                                                 # and no cited number is ignored or idle
    for rule in drafted_r1b:
        if rule["kind"] == "rule" and rule["id"] not in from_law:
            idle += chart.idle_numbers(rule, [c for c in chart.cited_rows(rule, cells) if c["page"] != 2], ctx.allowed())
    assert idle == []


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
             if not (e["rules"] or e.get("reason") or e.get("unresolved") or e.get("failed"))]
    assert empty == []


def test_every_drafted_rulebook_passes_the_inspector(ctx):
    books = sorted(DRAFTED.glob("*.yaml"))
    if not books:
        pytest.skip("nothing drafted yet")
    assert {p.name: validate(load(p), ctx) for p in books} == {p.name: [] for p in books}
