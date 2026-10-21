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


MAPPING = REPO / "packages/rule_drafting/evals/2026-10-20_stage1/hand_to_drafted.yaml"


def mapping() -> dict:
    """The reviewed hand-to-drafted mapping (evals/2026-10-20_stage1/hand_to_drafted.yaml)."""
    return load(MAPPING) if MAPPING.exists() else {"keys": {}, "general_unmatched": {}}


def kinder(got: str, expect: str) -> bool:
    """The drafted answer lets through what the key doesn't: a pass, or "doesn't apply" (nothing shown), where the
    key says fail or needs review."""
    return got in ("pass", "not_applicable") and expect in ("fail", "needs_review")


def grade_mapped(book: dict, entries: dict, drafted: list[dict], ctx) -> dict:
    """Every worked example of a hand key, graded by its reviewed pairs. Agreement: the mapped rules together (judge
    units and exception parts). False pass: each judge unit on its own, its missing inputs left missing (never taken
    from the draft's own example), so neither an unrelated rule nor a supplied value can hide a pass."""
    district = book["district"]
    by_id = {r["id"]: r for r in drafted}
    out = {"district": district, "total": 0, "agree": [], "disagree": [], "undrafted": [], "false_pass": []}
    for h in book["rules"]:
        e = entries[h["id"]]
        units = [[by_id[i] for i in u] for u in e.get("judge") or []]
        every = [r for u in units for r in u] + [by_id[i] for i in e.get("parts") or []]
        for ex in h.get("examples", []):
            out["total"] += 1
            item = {"hand": h["id"], "given": ex["given"], "expect": ex["expect"]}
            if not every:
                out["undrafted"].append(item)
                continue
            values = {"district": district} | ex["given"]
            got, notes = combined(every, values, ctx, set(ctx.proposed))
            item |= {"got": got, "drafted": [r["id"] for r in every], "notes": notes}
            (out["agree"] if got == ex["expect"] else out["disagree"]).append(item)
            for u in units:
                alone, _ = combined(u, values, ctx, frozenset())
                if kinder(alone, ex["expect"]):
                    out["false_pass"].append(item | {"got": alone, "drafted": [r["id"] for r in u]})
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
        return grade_mapped(book, entries, drafted_rules_for(district), ctx)
    drafted = drafted_rules_for(district) if drafted is None else drafted
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


def test_no_drafted_rule_passes_what_any_hand_key_does_not(ctx):
    """Never a false pass, against every hand key present: a drafted PASS where the key says fail or needs review."""
    if not (DRAFTED / "general.yaml").exists():
        pytest.skip("nothing drafted yet")
    assert {p.name: grade_hand_key(p, ctx)["false_pass"] for p in hand_keys()} == {p.name: [] for p in hand_keys()}


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
    from_law = law_unit_rules() if from_law is None else from_law
    found = []
    for h in hand:
        rules = [r for r in covering(h, drafted, ctx, from_law) if r["id"] in from_law]
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
        if rule["kind"] == "rule":
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
             if not (e["rules"] or e.get("reason") or e.get("unresolved") or e.get("failed"))]
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


def test_a_hand_flag_is_covered_by_a_numeric_draft_on_its_cell_and_a_wrong_pass_shows(ctx, tmp_path):
    """Review round 6: a hand rule that measures nothing (a use flag) required the draft to measure nothing too, so a
    numeric drafted rule on the same cell was filed undrafted, and its pass against the key's needs review never
    reached false_pass."""
    import yaml
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
    assert general - general_mapped == set(m["general_unmatched"]), sorted((general - general_mapped) ^ set(m["general_unmatched"]))
    # and every key in the mapping is graded by its pairs: each graded example names only its hand rule's mapped rules
    for path in hand_keys():
        rules = m["keys"][path.name]["rules"]
        g = grade_hand_key(path, ctx)
        for x in g["agree"] + g["disagree"]:
            e = rules[x["hand"]]
            mapped = {i for u in e.get("judge") or [] for i in u} | set(e.get("parts") or [])
            assert set(x["drafted"]) <= mapped, (path.name, x["hand"], sorted(set(x["drafted"]) - mapped))


def _mutated(rule: dict, how: str) -> dict:
    """The rule made to always pass, or never apply."""
    base = {k: v for k, v in rule.items() if k not in ("applies_when", "check", "review_when")}
    if how == "pass":
        return base | {"kind": "rule", "check": "0 <= 0"}
    return base | {"kind": "rule", "applies_when": "0 > 1", "check": "0 <= 0"}


def test_the_grader_catches_every_mapped_rule_turned_into_a_false_pass(ctx):
    """Mutation test (review round 7): every judge unit of every mapped hand rule, made to always pass or never apply,
    must be reported as a false pass on that hand rule (when the key has an example that fails or needs review): the
    grader has no blind spot left, the way the type table is mutation-tested."""
    if not (DRAFTED / "general.yaml").exists():
        pytest.skip("nothing drafted yet")
    m = mapping()
    missed, tried = [], 0
    for path in hand_keys():
        book, entries = load(path), m["keys"][path.name]["rules"]
        drafted = drafted_rules_for(book["district"])
        for h in book["rules"]:
            if not any(ex["expect"] in ("fail", "needs_review") for ex in h.get("examples", [])):
                continue
            for unit in entries[h["id"]].get("judge") or []:
                for how in ("pass", "not_applicable"):
                    tried += 1
                    flipped = [_mutated(r, how) if r["id"] in unit else r for r in drafted]
                    g = grade_mapped(book | {"rules": [h]}, entries, flipped, ctx)
                    if not g["false_pass"]:
                        missed.append((path.name, h["id"], unit, how))
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
    lot = next(r for r in load(DRAFTED / "R-3a.yaml")["rules"] if r["id"] == "R-3a.min_lot_area_other_use")
    entries = {"R-3a.use": {"judge": [["R-3a.use"]], "reason": "x"}}
    g = grade_mapped({"district": "R-3a", "rules": [hand_flag]}, entries, [dropped, lot], ctx)
    assert [x["got"] for x in g["false_pass"]] == ["not_applicable"]
    assert grade_mapped({"district": "R-3a", "rules": [hand_flag]}, entries, [use, lot], ctx)["false_pass"] == []
