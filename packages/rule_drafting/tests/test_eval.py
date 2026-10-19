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


def covering(hand_rule, drafted, ctx):
    """The drafted rules that cite a chart row or law line the hand rule quotes. Footnotes are left out
    (many rows share one), and so are the cells a hand rule cites: in the answer key a rule quotes its own
    subject and cites cells only as inputs (the height bonus cites the yard minimums it enlarges)."""
    def lines(rule, quotes_only=False):
        sources = [s for s in rule["sources"] if not (quotes_only and "cell" in s)]
        notes = {(s["file"], s["page"], n) for s in sources if s.get("quote", "").startswith("(")
                 and s["file"] == CHART for n in range(s["lines"][0], s["lines"][1] + 1)}
        return _cited_lines(sources, ctx) - notes
    wanted = lines(hand_rule, quotes_only=True)
    return [r for r in drafted if lines(r) & wanted]


def combined(rules, values, ctx):
    results = {outcome(r, values, ctx.allowed()) for r in rules}
    for result in ("fail", "needs_review", "pass"):
        if result in results:
            return result
    return "not_applicable"


def test_drafted_r1b_agrees_with_the_hand_drafted_r1b(hand, drafted_r1b, ctx):
    disagreements, compared = [], 0
    for h in hand:
        rules = covering(h, drafted_r1b, ctx)
        if not rules:
            continue                                   # not drafted yet; test_every_hand_rule_is_covered checks
        for ex in h["examples"]:
            compared += 1
            got = combined(rules, ex["given"], ctx)
            if got != ex["expect"]:
                disagreements.append(f"{h['id']} {ex['given']}: hand {ex['expect']}, drafted {got} "
                                     f"({', '.join(r['id'] for r in rules)})")
    assert compared, "no drafted rule covers any hand rule"
    assert disagreements == []


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
    for rule in drafted_r1b:
        passing = [ex["given"] for ex in rule.get("examples", []) if ex["expect"] == "pass"]
        if rule["kind"] != "rule" or not passing:
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
        if rule["kind"] != "rule":
            continue
        rows = [c for c in chart.cited_rows(rule, cells) if c["page"] != 2]
        used = chart.formula_numbers(rule)
        for c in rows:
            for n in chart.numbers(c["value"]):
                if not any(abs(n - u) < 1e-9 for u in used):
                    idle.append(f"{rule['id']}: cites {c['row']!r} but doesn't use {n:g}")
                elif not chart.number_matters(rule, n, rows, ctx.allowed()):
                    idle.append(f"{rule['id']}: {n:g} from {c['row']!r} changes nothing")
    assert idle == []


def test_every_hand_rule_is_covered_once_drafting_is_complete(hand, drafted_r1b, ctx):
    if not (LOG.exists() and load(LOG).get("complete")):
        pytest.skip("drafting not complete yet")
    assert [h["id"] for h in hand if not covering(h, drafted_r1b, ctx)] == []


def test_drafted_r1b_matches_the_architects_spreadsheet(hand, drafted_r1b, ctx):
    design = load(SITE)
    values = {k: m["value"] for k, m in design["measurements"].items()} | {"district": "R-1b"}
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
        if (got := combined(rules, values, ctx)) != theirs.lower():
            wrong.append(f"{label}: they say {theirs}, drafted rules say {got}")
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
