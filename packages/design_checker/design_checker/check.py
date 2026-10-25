"""Check a design: measure the model, run the zone's rules, build the envelope, and say it in one line.

Every result comes from the checker's `outcome()` (the project report, PR 10, refuses a rulebook that fails the
rule checks). row_verdict decides each row, and each side yard of a pair, over THE reading set (reading_set: the
open questions' readings, and on a tax-map lot the lines' slack and the lot area's ends): fails if it fails under
every reading, complies if it passes under every one and its result turns on no open question (turns_on), else
needs review. That verdict
is the single source of truth: the panel (present) shows it or something more cautious, never more favourable.
This module also gathers what the Rhino panel and the viewport show: the rows, a short summary, the objects to
show in red, the envelope and the plan.
"""

import ast
import math
import os
import re
import tempfile
from pathlib import Path

import yaml

from design_checker import present, reading_set
from design_checker import rhino_logic as logic
from design_checker.rhino_logic import COLUMN_DELTA
from envelope_builder import start as generator
from envelope_builder.envelope import envelope
from model_measurement.measure import TAX_MAP_TOLERANCE, measure
from model_measurement.project import fact_problems, load_facts, working
from model_measurement.read_3dm import read_site
from project_report.report import OUTPUT_EXTRA, OUTPUT_HEADERS, build, tables
from rule_format import formula
from rule_format.rulebook import MEASURE_KINDS, REPO, Context, load, outcome, rulebook_for

COLUMNS = OUTPUT_HEADERS + OUTPUT_EXTRA
# Facts about the inside of a building (rooms, parking spaces). This phase checks the outside only: a rule waiting
# on one of these goes in its own group, "not checked yet: interior", out of the counts. A rule they decide once
# entered (a FAIL included) is shown like any other: nothing that fails is ever hidden.
# What sets a row aside as "not checked yet: interior" (out of the counts): only these, inside the building. Every
# other stated fact (rhino_logic.STATED_FACTS: what can be ASKED, such as R-3a's dwelling units) leaves its row a
# review row, with its own "Enter …" button from `needs` (PR #20 round 2: never hidden, even when it fails).
INTERIOR = {"sleeping_rooms", "parking_spaces"}
NUMBER = re.compile(r"^([≥≤<>=]) (-?[\d,]+(?:\.\d+)?)$")


def short(title: str) -> str:
    """A rule's title, short enough for one line: 'Rear yard minimum (chart p.3, …)' -> 'Rear yard'."""
    words = title.split(" (")[0].split(",")[0]
    words = re.sub(r"^(Maximum|Minimum) ", "", words)
    words = re.sub(r" (minimum|maximum)$", "", words)
    return words[:1].upper() + words[1:]


def plain_name(measure: str) -> str:
    """A measurement as an architect says it: side_yard_smaller -> side yard."""
    return measure.replace("_smaller", "").replace("_larger", "").replace("_", " ")


def _first_failing(rule: dict, measured: dict) -> str | None:
    """For a rule with several comparisons (the height with its bonus): the first one that fails, in plain words,
    'Building height 38 ft, needs ≤ 35 ft'. None if none can be worked out."""
    values = {k: m["value"] for k, m in measured.items()}
    signs = {ast.GtE: "≥", ast.Gt: ">", ast.LtE: "≤", ast.Lt: "<"}
    for node in ast.walk(formula.parse(rule["check"]).body):
        if not (isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.left, ast.Name)
                and type(node.ops[0]) in signs):
            continue
        name, m = node.left.id, measured.get(node.left.id) or {}
        try:
            holds = formula.evaluate(ast.unparse(node), values, MEASURE_KINDS)
            need = formula.evaluate(ast.unparse(node.comparators[0]), values, MEASURE_KINDS)
        except (formula.EvaluationError, formula.MissingMeasure, ArithmeticError):
            continue
        if holds is False:
            unit = m.get("unit") or ""
            unit = "" if unit == "count" else " " + unit
            return (f"{plain_name(name).capitalize()} {_n(m['value'])}{unit}, needs "
                    f"{signs[type(node.ops[0])]} {_n(need)}{unit}")
    return None


def _amount(row: dict, rule: dict | None = None, measured: dict | None = None) -> str:
    """'Rear yard 20 ft, needs ≥ 22.5 ft (2.5 ft short)' for a one-number limit; for a rule with several
    comparisons, the first that fails; else the formula's words."""
    limit, proposed, units = row["Table limit"], row["Proposed"], row["Units"]
    m = NUMBER.match(str(limit))
    if m and isinstance(proposed, (int, float)):
        need = float(m.group(2).replace(",", ""))
        gap = abs(proposed - need)
        side = "over" if m.group(1) in "≤<" else "short"
        return f"{short(row['Requirement'])} {_n(proposed)} {units}, needs {limit} {units} ({_n(gap)} {units} {side})"
    plain = _first_failing(rule, measured) if rule and measured and rule.get("check") else None
    return plain or f"{short(row['Requirement'])}: {proposed} (needs {limit})"


def _n(x) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else f"{x:,}"


def _why(row: dict, rules: dict, measured: dict) -> dict:
    """The row, plus "Why": for a NEEDS REVIEW row whose measurements are missing, why each is missing (the
    measuring's own reason: "a building isn't inside the lot", "enter bedrooms / parking spaces"), else the
    report's reason."""
    reasons = []
    if row["Error"] == "NEEDS REVIEW":
        rule = rules[row["Rule id"]]
        for name in sorted(set().union(*(formula.names(rule[k]) for k in ("applies_when", "check") if rule.get(k)))):
            reason = (measured.get(name) or {}).get("reason")
            if (measured.get(name) or {}).get("value") is None and reason and reason not in reasons:
                reasons.append(reason)
    return {**row, "Why": "; ".join(reasons) or row["Why it needs review"]}


SURVEY = "lot_area"        # a lot not yet surveyed: its one reading is the lot as drawn


def every_reading(rule: dict, measured: dict, allowed: dict, facts: dict | None = None) -> tuple[str, str] | None:
    """For a rule that needs review only because measurements have readings instead of a value: ("pass", how) if
    it passes under every reading, ("fail", how) if it fails under every one, else None (or when a measurement
    has no reading, or there are too many). The readings are THE reading set (reading_set.combos: those of one
    lot reading together; with `facts` on a tax-map lot, also the lot lines' slack and the lot area's low and
    high), the same set the panel's words and colours come from (present.settle). Never a result: the row stays
    NEEDS REVIEW (only outcome() decides results); this says the design complies, or doesn't, whichever way the
    open question is answered."""
    names = reading_set.rule_names(rule)
    open_ = sorted(n for n in names if (measured.get(n) or {}).get("value") is None)
    values = {k: m["value"] for k, m in measured.items()}
    every = reading_set.combos(names, values, measured, facts) if open_ else None
    if not every:
        return None
    got = {outcome(rule, trial, allowed) for trial, _ in every}
    if got not in ({"pass"}, {"fail"}):
        return None
    word = "passes" if got == {"pass"} else "fails"
    survey = SURVEY in open_ and len((measured.get(SURVEY) or {}).get("readings") or []) == 1
    others = [n for n in open_ if n != SURVEY or not survey]
    return got.pop(), (f"{word} with the lot as drawn (confirm the survey)" if survey and not others else
                       f"{word} under every reading" +
                       (" and with the lot as drawn (confirm the survey)" if survey else ""))


def turns_on(rule: dict, measured: dict, allowed: dict, facts: dict | None = None) -> list[str] | None:
    """The open measurements a rule's result turns on: each whose readings it needs (with it unknown and everything
    else at any of its readings from THE reading set, the result can't be told). An open question it doesn't turn
    on doesn't hold it back (either answer gives the same result). None if there are too many readings."""
    names = reading_set.rule_names(rule)
    values = {k: m["value"] for k, m in measured.items()}
    out = []
    for n in sorted(n for n in names if values.get(n) is None and (measured.get(n) or {}).get("readings")):
        every = reading_set.combos(names - {n}, values, measured, facts)
        if every is None:
            return None
        if any(outcome(rule, dict(trial, **{n: None}), allowed) == "needs_review" for trial, _ in every or [(values, None)]):
            out.append(n)
    return out


def row_verdict(rule: dict, measured: dict, allowed: dict, facts: dict | None = None, check: str | None = None) -> str:
    """THE verdict of a rule (or, with `check`, of one of its comparisons: a side yard of a pair, with the rule's
    applies_when and review_when) over THE reading set (reading_set.combos): fails if it fails under every reading;
    complies if it passes under every one and turns on no open question (turns_on; the lot area of a tax-map lot
    is read at its low and high ends, so it counts as known); otherwise needs review. The ONLY place a row is
    decided: the panel shows this or something more cautious, never more favourable (review round 3)."""
    rule = dict(rule, check=check) if check else rule
    names = reading_set.rule_names(rule)
    values = {k: m["value"] for k, m in measured.items()}
    tax = reading_set.tax_map(measured, facts)
    every = reading_set.combos(names, values, measured, facts)
    if not every:                                   # a value unknown, or too many: as drawn, never kinder
        got = outcome(rule, values, allowed)
        lot = names & (reading_set.LOT_LENGTHS | {SURVEY})
        return present.FAILS if got == "fail" and not (tax and lot) else \
            present.COMPLIES if got == "pass" and not (tax and lot) else present.REVIEW
    got = {outcome(rule, trial, allowed) for trial, _ in every}
    if got == {"fail"}:
        return present.FAILS
    turns = turns_on(rule, measured, allowed, facts)
    open_ = (set(turns) if turns is not None else {n for n in names if values.get(n) is None}) - \
        ({SURVEY} if tax else set())
    return present.COMPLIES if got == {"pass"} and not open_ else present.REVIEW


def _changed(measured: dict, changes: dict) -> dict:
    """The measurements with each named one changed by its amount (its value and every reading of it): the design
    as a "To comply" would leave it."""
    out = dict(measured)
    for m, d in changes.items():
        rec = dict(measured.get(m) or {})
        if isinstance(rec.get("value"), (int, float)):
            rec["value"] = rec["value"] + d
        rec["readings"] = [dict(r, value=r["value"] + d) if isinstance(r.get("value"), (int, float)) else r
                           for r in rec.get("readings") or []]
        out[m] = rec
    return out


def _raised_by(rules: list, values: dict) -> dict:
    """measure -> [(rule, comparison)]: the yards a rule with several ways to comply raises as the design stands
    (`values`): its first way not met, another way met, that way's comparison on the yard (the height bonus), as
    present._raise_yards shows them on the panel."""
    out = {}
    for rule in rules:
        body = formula.parse(rule["check"]).body if rule.get("check") else None
        if not (isinstance(body, ast.BoolOp) and isinstance(body.op, ast.Or)):
            continue
        if present._evaluate(ast.unparse(body.values[0]), values) is not False:
            continue
        for alt in body.values[1:]:
            if present._evaluate(ast.unparse(alt), values) is not True:
                continue
            for c in [alt] if isinstance(alt, ast.Compare) else getattr(alt, "values", []):
                if isinstance(c, ast.Compare) and isinstance(c.left, ast.Name) and c.left.id in present.YARD_MEASURES:
                    out.setdefault(c.left.id, []).append((rule, ast.unparse(c)))
            break
    return out


def confirm_advice(items: list[dict], by_id: dict, measured: dict, allowed: dict, facts: dict,
                   site: dict | None = None) -> None:
    """Every "To comply" is the checker's to confirm. Each piece (each way, each "…if it stays that tall" clause) is
    applied to the measurements and every row decided again by row_verdict, a yard with any raise the height bonus
    then puts on it, as the panel shows it: the piece is kept only if its row then complies, every rule it answers
    to complies (a clause: the whole height rule), and no other row is worse than it is now (review round 4: a move
    re-checked against its own row and its opposite yard alone newly failed side yards on a narrowing lot, and a
    raised rear yard; the "if it stays tall" figure, other raised yards). Pieces only ever change one measurement,
    one wall pulled back, so the re-decision is exact. Nothing left: no hint. A "To comply" with no change the
    checker can try is dropped (the architect's review, pass 2; round 2, R1: 106's rear yard told to move)."""
    rules = [by_id[i["rule"]] for i in items if by_id.get(i.get("rule"))]
    rules = list({r["id"]: r for r in rules}.values())

    def statuses(changes):
        changed = _changed(measured, changes)
        raised = _raised_by(rules, {k: m.get("value") for k, m in changed.items()})
        out = {}
        for it in items:
            rule = by_id.get(it.get("rule"))
            if rule is None:
                continue
            m = it.get("measure")
            st = row_verdict(rule, changed, allowed, facts, check=side_checks(rule).get(m))
            for r, e in raised.get(m) or []:
                got = row_verdict(r, changed, allowed, facts, check=e)
                st = got if present.RANK[got] < present.RANK[st] else st
            out[it["id"]] = st
        return out

    before = None
    for i in items:
        advice = i.pop("_advice", None)
        if not (i.get("hint") or "").startswith("To comply"):
            continue
        if advice is None or by_id.get(i.get("rule")) is None:
            i["hint"] = None
            continue
        before = before or statuses({})

        def holds(part):
            if not part["changes"]:
                return False
            after = statuses(part["changes"])
            changed = _changed(measured, part["changes"])
            return after.get(i["id"]) == present.COMPLIES \
                and all(row_verdict(by_id[r], changed, allowed, facts, check=e) == present.COMPLIES
                        for r, e in part.get("also") or [] if r in by_id) \
                and all(present.RANK[after[k]] >= present.RANK[v] for k, v in before.items() if k in after)

        ways = [w for w in advice["ways"] if holds(w)]
        clauses = [c for c in advice.get("clauses") or [] if holds(c)]
        i["hint"] = present.advice_text(dict(advice, ways=ways, clauses=clauses))


def side_lines(site: dict, facts: dict) -> list[str] | None:
    """The true compass names of the lot's two side lines, each from the lot's middle to the line: what a side yard
    is called when it couldn't be measured. Only when the measuring itself knows which lines are sides: the lot not
    a corner lot (unknown counts as maybe), and every reading of its lines giving the same two names (review round
    1). None otherwise, or without a lot."""
    from model_measurement.measure import Lot
    if facts.get("corner_lot") is not False or not (site.get("lot") or {}).get("edges") or not facts.get("street_line"):
        return None
    lot = Lot(site, facts)
    readings = None if lot.problems or lot.street_problem else lot.readings()
    if not readings:
        return None
    middle = lot.polygon.centroid
    pairs = set()
    for _, left, right, _ in readings:
        names = [present.compass(lot.line(g).centroid.x - middle.x, lot.line(g).centroid.y - middle.y,
                                 facts.get("plan_north_deg") or 0.0) for g in (left, right)]
        if not all(names):
            return None
        pairs.add(tuple(sorted(names)))
    return list(pairs.pop()) if len(pairs) == 1 else None


def side_checks(rule: dict) -> dict:
    """A rule's comparisons of the two side yards, each as its own check (the panel shows each side as a row)."""
    if not rule.get("check"):
        return {}
    return {c.left.id: ast.unparse(c) for c in present._compares(rule["check"])
            if c.left.id in ("side_yard_smaller", "side_yard_larger")}


def verdict(rule: dict, measured: dict, allowed: dict) -> str:
    """The checker's own result for one rule, as its rows mark it: outcome(), except that a needs review that fails
    under every reading (or with the lot as drawn) is a "fail" (the row's "Fails")."""
    got = outcome(rule, {k: m["value"] for k, m in measured.items()}, allowed)
    if got == "needs_review":
        found = every_reading(rule, measured, allowed)
        if found and found[0] == "fail":
            return "fail"
    return got


def largest_legal_building(site: dict, facts: dict, measured: dict, rules: list[dict], **options) -> dict:
    """envelope_builder's largest legal building, proven with the checker's own verdict (above) before it is
    placed: never a building the check that follows shows as not complying (audit P1-3)."""
    return generator.largest_legal_building(site, facts, measured, rules, verdict=verdict, **options)


def summary(rows: list[dict]) -> dict:
    """One line for the viewport corner: all pass; it complies under every reading (rules waiting only on how the
    law is read, each passing whichever way it goes); or what fails and what needs review. A rule that passes only
    with the lot as drawn still needs review (amber) until the survey is confirmed: a lot not yet surveyed is a
    missing fact, not a reading, so it is never shown as complying."""
    fails = [r for r in rows if r.get("Fails") or r["Error"] == "FAIL"]
    review = [r for r in rows if r["Error"] == "NEEDS REVIEW" and r not in fails]
    passes = [r for r in rows if r["Error"] == "PASS"]
    if not fails and not review:
        return {"state": "pass", "text": f"All {len(passes)} rules pass", "lines": []}
    if not fails and all(r.get("Provisional") and not r.get("Survey") for r in review):
        waiting = {}
        for r in review:
            waiting.setdefault(r["Provisional"], []).append(short(r["Requirement"]))
        return {"state": "complies", "text": f"Complies: {len(passes)} pass, {len(review)} pass whichever way open "
                                             "questions go",
                "lines": [", ".join(names) + ": " + why for why, names in waiting.items()]}
    lines = [r.get("Line") or (_amount(r) if r["Error"] == "FAIL" else f"{short(r['Requirement'])}: {r['Provisional']}")
             for r in fails]
    lines += [f"{short(r['Requirement'])}: {r.get('Provisional') or r['Why']}" for r in review]
    counts = f"{len(passes)} pass" + (f" · {len(fails)} fail" if fails else "") + (
        f" · {len(review)} need review" if review else "")
    return {"state": "fail" if fails else "review", "text": counts, "lines": lines}


def _failing_distances(rule: dict, measured: dict, values: dict) -> list[dict]:
    """Each distance whose own comparison fails, as the line it was measured along, to draw in the model. A
    distance that passes isn't drawn, even inside a failing rule (the other side yard, the bonus's yards)."""
    found = []
    for node in ast.walk(formula.parse(rule["check"]).body):
        if not (isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.left, ast.Name)):
            continue
        name, m = node.left.id, measured.get(node.left.id) or {}
        if not m.get("points") or m.get("value") is None:
            continue
        try:
            holds = formula.evaluate(ast.unparse(node), values, MEASURE_KINDS)
            need = formula.evaluate(ast.unparse(node.comparators[0]), values, MEASURE_KINDS)
        except (formula.EvaluationError, formula.MissingMeasure, ArithmeticError):
            continue
        if holds is False and name not in [d["measure"] for d in found]:
            sign = {ast.GtE: "≥", ast.Gt: ">", ast.LtE: "≤", ast.Lt: "<"}.get(type(node.ops[0]), "")
            found.append({"rule": rule["id"], "measure": name, "points": m["points"],
                          "label": f"{plain_name(name)} {_n(m['value'])} ft, needs {sign} {_n(need)}"})
    return found


def _report(t: dict, view: dict, report_path: Path) -> None:
    """The architects'-format workbook (PR 10), saying what the panel says (spec I1, I2): each rule's Error and
    Comparison are its items' most cautious status (a rule the panel shows as needing review is never PASS here),
    and a Check tab lists every item, the summary, the draft-rulebook label and the lot and grade sources."""
    from rule_export.workbook import title, write_block
    word = {present.FAILS: ("FAIL", "Outside table limit"), present.REVIEW: ("NEEDS REVIEW", "Needs review"),
            present.COMPLIES: ("PASS", "Within table limit"), present.NOT_CHECKED: ("NOT CHECKED", "Needs input")}
    worst, shown = {}, {}
    for i in view["items"]:
        if i["rule"] and i["status"] in word:
            rank = present.ORDER.index(i["status"])
            if i["rule"] not in worst or rank < present.ORDER.index(worst[i["rule"]][0]):
                worst[i["rule"]] = (i["status"], i.get("reason") or "")
            shown.setdefault(i["rule"], []).append(i)
    col = {h: n for n, h in enumerate(COLUMNS)}
    rows = []
    for r in t["output"]:
        r = list(r)
        found = worst.get(r[col["Rule id"]])
        if found:
            # every column of the row from the panel's items (the same verdicts): its Error, Comparison and Why,
            # and what it shows as Proposed, so a PASS never sits beside "Can't check: … missing"
            r[col["Error"]], r[col["Comparison"]] = word[found[0]]
            r[col["Why it needs review"]] = found[1] if found[0] == present.REVIEW else ""
            items = [i for i in shown[r[col["Rule id"]]] if i.get("proposed")]
            if len(items) == 1:         # the row as the panel shows it, in one unit: limit, proposed, units
                r[col["Proposed"]] = items[0]["proposed"]
                if items[0].get("required") and items[0].get("sign"):
                    r[col["Table limit"]] = f"{items[0]['sign']} {items[0]['required']}"
                if "%" in str(items[0]["proposed"]):            # coverage: a share of the lot area, not sf
                    r[col["Units"]] = "% of lot area"
            elif items:
                r[col["Proposed"]] = "; ".join(f"{i['name']}: {i['proposed']}" for i in items)
        rows.append(r)
    # an input the measurement couldn't settle (a tax-map lot's area) shows what the panel shows, said as drawn
    by_measure = {i.get("measure"): i for i in view["items"] if i.get("measure") and i.get("proposed")}
    inputs = []
    for r in t["inputs"]:
        r = list(r)
        i = by_measure.get(r[0].lower().replace(" ", "_"))
        if r[1] is None and i is not None and "%" not in str(i["proposed"]):     # only in the input's own unit
            r[1], r[3] = i["proposed"], "as drawn (the panel's reading); " + str(r[3])
        inputs.append(r)
    wb = build({**t, "output": rows, "inputs": inputs, "title": view["header"].get("place") or t["title"]})
    ws = wb.create_sheet("Check")
    h = view["header"]
    title(ws, f"GORDIUM | {view['summary']}")
    lines = [h["place"], h["code"], h["draft"], h["lot"], h["grade"]] + ([h["main"]] if h.get("main") else []) + \
        (h.get("sources") or [])   # where each fact came from
    for n, text in enumerate(lines, start=2):
        ws.cell(row=n, column=1, value=text)
    by_id = {i["id"]: i for i in view["items"]}
    out = []
    for g in present.grouped(view["items"]):
        for item_id in g["items"]:
            i = by_id[item_id]
            # the note ("assuming flat ground") with the item, as the panel shows it; that column is reasons only
            out.append([g["title"], i["mark"], i["name"] + (" · " + i["note"] if i.get("note") else ""), i["proposed"],
                        i["required"], i.get("delta") or "", i.get("reason") or "",
                        i["detail"].get("citation") or "",
                        (i["detail"].get("links") or [""])[0]])
    write_block(ws, len(lines) + 3, [("Group", 22), ("Mark", 6), ("Item", 34), ("Proposed", 12), ("Required", 12),
                                     (COLUMN_DELTA, 10), ("Why it needs review", 60), ("Citation", 50), ("Link", 40)], out)
    wb.move_sheet("Check", offset=-wb.sheetnames.index("Check"))     # the architect's sheet first, open on it
    wb.active = 0
    for ws_ in wb.worksheets:
        ws_.sheet_view.tabSelected = ws_.title == "Check"
    # written beside it, then moved into place: a write that fails half way never leaves a broken report there
    report_path = Path(report_path)
    part = report_path.with_name("." + report_path.name + ".part")
    try:
        wb.save(part)
        os.replace(part, report_path)
    finally:
        if part.exists():
            part.unlink()


def check(model_path: Path, facts: dict, report_path: Path | None = None, building_problems: list | None = None,
          extras: dict | None = None) -> dict:
    """Everything the Rhino command shows, for one model and its lot facts. `building_problems` are what the
    Rhino command found on the Building layer and couldn't send (a block, a surface): each one makes every
    building measure need review, never silently dropped. `extras` is what the command adds for the panel: what
    it sent (scope), objects on the lot it didn't send (each makes the check need review), the grade source."""
    problems = fact_problems(facts)            # the same check as a facts file: a plain refusal, never a crash
    problems += [f"no {k} given" for k in ("jurisdiction", "zone") if not facts.get(k)]
    if problems:
        raise ValueError("lot facts: " + "; ".join(problems))
    model_path = Path(model_path)
    site = read_site(model_path, facts)
    if building_problems:
        site["buildings"].append({"id": "Building layer", "faces": [], "problems": list(building_problems)})
    return check_site(site, facts, model_path.name, report_path, extras)


def check_site(site: dict, facts: dict, name: str = "model", report_path: Path | None = None,
               extras: dict | None = None) -> dict:
    """check() for a site already read (the lot and the buildings, in feet), e.g. one a test or a scenario
    generator builds. Exactly the same measuring, rules and presentation as a model read from a file."""
    problems = fact_problems(facts) + [f"no {k} given" for k in ("jurisdiction", "zone") if not facts.get(k)]
    if problems:
        raise ValueError("lot facts: " + "; ".join(problems))
    model_path = Path(name)
    measured = measure(site, facts)
    project = {"title": facts.get("title") or model_path.stem, "jurisdiction": facts.get("jurisdiction"),
               "zone": facts.get("zone"),
               "measurements": {k: {"value": m["value"], "from": working(m, model_path.name)} for k, m in measured.items()}}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "project.yaml"
        path.write_text(yaml.safe_dump(project, sort_keys=False, allow_unicode=True), encoding="utf-8")
        t = tables(path)              # refuses a project or rulebook that fails its checks (ValueError)
    rules = load(rulebook_for(REPO / facts["jurisdiction"], facts["zone"]))["rules"]
    by_id = {r["id"]: r for r in rules}
    every = [_why(dict(zip(COLUMNS, r)), by_id, measured) for r in t["output"]]
    def checks(rule):                   # a flag has no check
        return formula.names(rule["check"]) if rule.get("check") else set()

    waiting = [r for r in every if r["Error"] == "NEEDS REVIEW" and any(
        (measured.get(n) or {}).get("value") is None for n in checks(by_id[r["Rule id"]]) & INTERIOR)]
    for r in waiting:                   # exactly which stated facts each one waits for (its "Enter …" asks those)
        r["needs"] = logic.needs_of(reading_set.rule_names(by_id[r["Rule id"]]), {k: m.get("value") for k, m in measured.items()})
    rows = [{**r, "Line": _amount(r, by_id[r["Rule id"]], measured)} if r["Error"] == "FAIL" else r
            for r in every if r not in waiting]
    for r in rows:
        r["Short"] = short(r["Requirement"])
    allowed = {"use": Context.for_jurisdiction(REPO / facts["jurisdiction"]).uses}
    for r in rows:
        found = every_reading(by_id[r["Rule id"]], measured, allowed, facts) if r["Error"] == "NEEDS REVIEW" else None
        r["Provisional"] = found[1] if found else None
        r["Survey"] = bool(found and "confirm the survey" in found[1])     # waits on a fact, not an interpretation
        rule = by_id[r["Rule id"]]
        r["Verdict"] = row_verdict(rule, measured, allowed, facts)          # the ONE decision (round 3)
        r["Sides"] = {m: row_verdict(rule, measured, allowed, facts, check=c) for m, c in side_checks(rule).items()}
        r["Side provisional"] = {m: (every_reading(dict(rule, check=c), measured, allowed, facts) or (None, None))[1]
                                 for m, c in side_checks(rule).items()}      # each side's words, as a row's
        r["Side turns on"] = {m: turns_on(dict(rule, check=c), measured, allowed, facts)
                              for m, c in side_checks(rule).items()}
        r["Fails"] = r["Verdict"] == present.FAILS                          # fails whichever way it goes
        r["Turns on"] = turns_on(rule, measured, allowed, facts)            # the open questions its result needs
        if r["Fails"] and not r.get("Line"):
            r["Line"] = f"{short(r['Requirement'])}: {r['Provisional']}"
    lot_id = (site.get("lot") or {}).get("id")
    red = sorted({o for r in rows if r["Fails"]
                  for name in formula.names(by_id[r["Rule id"]]["check"]) for o in measured.get(name, {}).get("objects", [])
                  if o != lot_id})
    values = {k: m["value"] for k, m in measured.items()}
    dims = [d for r in rows if r["Error"] == "FAIL" for d in _failing_distances(by_id[r["Rule id"]], measured, values)]
    extras = {**(extras or {}), "side_lines": side_lines(site, facts)}   # compass names when a side isn't measured
    v = present.view(rows, waiting, by_id, measured, facts, extras)
    confirm_advice(v["items"], by_id, measured, allowed, facts, site)   # each "To comply" the checker's, or none
    report_error = None
    if report_path is not None:      # a report that can't be written never takes the check's result with it
        try:
            _report(t, v, report_path)
        except OSError as e:
            report_error = f"{e.strerror or e} ({report_path})"
    env = envelope(site, _envelope_facts(site, facts), measured, rules)
    # the notice (spec G): the items that don't comply now and did at the last check the command sent ("before")
    statuses, notice_text = present.notice((extras or {}).get("before"), v["items"])
    return {"rows": rows, "interior": waiting, "not_applicable": [dict(zip(COLUMNS, r)) for r in t["not_applicable"]],
            "summary": summary(rows), "red": red, "dims": dims, "measurements": measured,
            "envelope": env, "problems": site.get("problems") or [], "view": v, "plan": plan(site, env, v, measured, facts),
            "report_error": report_error,
            "statuses": statuses, "notice": notice_text}


def _envelope_facts(site: dict, facts: dict) -> dict:
    """The facts the envelope is drawn from. Spot grades (or terrain sampled at the walls) that the measuring
    accepts give the grade plane, so the height plane is drawn from it; existing ground never sets it (it isn't
    the grade the code measures from), so then only the buildable area is drawn."""
    if facts.get("grade_is") == "existing":
        return {**facts, "ground_is_flat": None}
    if facts.get("grade_points"):
        from model_measurement.measure import envelope_grade   # the measuring's own refusals, the same function
        grade, why = envelope_grade(site.get("buildings") or [], facts)
        return {**facts, "ground_is_flat": True, "grade_elevation": grade} if why is None else {**facts, "ground_is_flat": None}
    return facts


def _ring(polygon) -> list:
    """A polygon's outline as [[x, y], ...], without edges shorter than 0.001 ft."""
    return [list(p) for p in polygon.simplify(0.001).exterior.coords[:-1]]


SHORTEST_LABELLED_EDGE = 1.0          # ft: lot edges shorter than this get no length label in plan


def hole_free(region) -> list:
    """A region as pieces without holes (each drawn by its outline alone): a polygon with a hole is cut in two
    by the vertical line through the hole's middle, again until none is left (review round 2: strips all round
    a house, a ring with the complying core as its hole, were drawn as the whole footprint)."""
    from shapely.geometry import box
    out, todo = [], [g for g in getattr(region, "geoms", [region]) if region is not None and not region.is_empty]
    while todo:
        g = todo.pop()
        if g.geom_type != "Polygon":
            todo += [p for p in getattr(g, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
            continue
        if not g.interiors:
            out.append(g)
            continue
        x = g.interiors[0].centroid.x
        x0, y0, x1, y1 = g.bounds
        for half in (g.intersection(box(x0 - 1, y0 - 1, x, y1 + 1)), g.intersection(box(x, y0 - 1, x1 + 1, y1 + 1))):
            todo += [p for p in getattr(half, "geoms", [half]) if p.geom_type in ("Polygon", "MultiPolygon")]
    return out


YARD_MEASURES = present.YARD_MEASURES


RUN_TURN_DEG = 20      # lot edges turning less than this from one to the next are one run, labelled once


def edge_runs(edges: list[dict]) -> list[tuple[list, float]]:
    """The lot's edges as runs to label (display only; the measurements use every edge): consecutive edges that
    carry on in nearly the same direction (turning less than RUN_TURN_DEG) are one run, a curve drawn as short
    segments labelled once with its whole length, as an architect would dimension it (the real 106 Ithaca Rd: its
    front, eight segments of about 10 ft along Ithaca Road, crowded the plan with eight labels). Each run: (its
    points, its length in feet). The caller leaves out runs under 1 ft (a tax map's jog of an inch or two)."""
    pieces = []
    for e in edges:
        pts = [list(p[:2]) for p in e["points"]]
        for a, b in zip(pts, pts[1:]):
            if math.dist(a, b) > 1e-9:
                pieces.append((a, b))
    if not pieces:
        return []

    def heading(a, b):
        return math.atan2(b[1] - a[1], b[0] - a[0])

    def turn(p, q):
        d = abs(heading(*p) - heading(*q)) % (2 * math.pi)
        return math.degrees(min(d, 2 * math.pi - d))
    # a run turns less than RUN_TURN_DEG in all, not just from piece to piece: a rounded corner drawn as short
    # pieces (each turning a little) is a corner, never one run joining two sides on a chord across the lot
    runs = [[pieces[0]]]
    for piece in pieces[1:]:
        if turn(runs[-1][-1], piece) < RUN_TURN_DEG and turn(runs[-1][0], piece) < RUN_TURN_DEG:
            runs[-1].append(piece)
        else:
            runs.append([piece])
    if (len(runs) > 1 and turn(runs[-1][-1], runs[0][0]) < RUN_TURN_DEG
            and turn(runs[-1][0], runs[0][-1]) < RUN_TURN_DEG):                # the ring closes inside a run
        runs[0] = runs.pop() + runs[0]
    return [([r[0][0]] + [b for _, b in r], sum(math.dist(a, b) for a, b in r)) for r in runs]


def _yard_lines(lot, measure: str, point):
    """The lot lines a yard is measured from, as the measurement takes them: every group (the street lines, a
    side, the rear lines, under each reading of the lot) that the yard's lot-line point lies on."""
    from shapely.geometry import Point
    groups = [lot.ordered_street()] if measure == "front_yard" else [
        g for _, left, right, back in (lot.readings() or []) for g in ((left, right) if measure != "rear_yard" else (back,))]
    hit = sorted({i for g in groups if lot.line(g).distance(Point(point)) < 0.01 for i in g})
    return lot.line(hit) if hit else None


def _clip_above(points: list, z: float) -> list:
    """A face's points clipped to the part at height z or above (Sutherland-Hodgman against one level)."""
    out = []
    for k, p in enumerate(points):
        q = points[(k + 1) % len(points)]
        if p[2] >= z:
            out.append(list(p))
        if (p[2] >= z) != (q[2] >= z):               # the edge crosses the level: where it does
            t = (z - p[2]) / (q[2] - p[2])
            out.append([p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]), z])
    return out


WALL_TILT = 1e-3      # a face whose plan is under this share of its own area is a wall (plumb, or within a hair)


def _is_wall(points: list) -> bool:
    """Whether a face stands upright: its plan (seen from above) is under WALL_TILT of its own area (Newell's
    method), so a wall a hair out of plumb is a wall too (review of the #28 fix, L1)."""
    nx = ny = nz = 0.0
    for k, p in enumerate(points):
        q = points[(k + 1) % len(points)]
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    full = (nx * nx + ny * ny + nz * nz) ** 0.5
    return full <= 1e-12 or abs(nz) <= WALL_TILT * full


def walls_beyond(building: dict, z: float, region) -> bool:
    """Whether a wall (a face seen edge-on from above) rises over height z somewhere `region` (what above() sees)
    doesn't cover: its plan, 0.05 ft each side, not inside the region."""
    from shapely.geometry import LineString
    for f in building.get("faces") or []:
        if not any(p[2] > z + 1e-6 for p in f["points"]):
            continue
        if not _is_wall(f["points"]):
            continue                                    # not a wall: above() already sees it
        clipped = [p[:2] for p in _clip_above(f["points"], z)]
        trace = LineString(clipped) if len(clipped) >= 2 else None
        if trace is not None and trace.length > 1e-6 and not region.buffer(0.05).contains(trace):
            return True
    return False


def above(building: dict, z: float):
    """The building seen from above where it rises above height z: each face clipped to z and above, projected
    flat (a pitched roof's strip along its ridge, a flat roof's whole outline; vertical faces add nothing)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    parts = []
    for f in building.get("faces") or []:
        if not any(p[2] > z + 1e-6 for p in f["points"]) or _is_wall(f["points"]):
            continue                                    # (a wall's sliver of plan adds nothing: walls_beyond)
        shell = _clip_above(f["points"], z)
        if len(shell) < 3:
            continue
        poly = Polygon([p[:2] for p in shell]).buffer(0)
        for h in f.get("holes") or []:
            hole = _clip_above(h, z)
            if len(hole) >= 3:
                poly = poly.difference(Polygon([p[:2] for p in hole]).buffer(0))
        if poly.area > 1e-9:
            parts.append(poly)
    return unary_union(parts) if parts else Polygon()


REQUIRED_HALF_FT = 6.0     # the faint required line: this far either side of its yard's dimension
HEIGHT_DIM_OFFSET_FT = 4.0  # the height dimension stands this far out from the building's corner


def _dim_label(i: dict) -> str:
    """A dimension's words, as the plan shows them: its mark, its name, the measured distance (feet-inches) and,
    when it fails, what is needed."""
    return (f"{i['mark']} {i['name']} {i['proposed']}" +
            (f", needs {i['required']}" if i["status"] == present.FAILS and i.get("required") else "") +
            (" (approx.)" if i.get("approx") else ""))


def required_lines(points: list, item: dict, edges: list) -> tuple[list, str | None]:
    """The yard's required line(s) across its dimension, and why there is none: one at its limit (`limit_ft`), or,
    when the limit depends on an open measurement (the lot depth, on the tax map), one at each end of its range
    (`limit_span_ft`), so every dimensioned yard shows where its minimum lies (Rhino check of #29)."""
    lo_hi = item.get("limit_span_ft")
    limits = [item["limit_ft"]] if isinstance(item.get("limit_ft"), (int, float)) else (
        sorted(set(lo_hi)) if lo_hi else [])
    lines = [x for x in (required_line(points, limit, edges) for limit in limits) if x]
    why = None if lines else ("its limit is not a length in feet" if not limits else
                              "the minimum is 0 ft (on the lot line)" if all(x <= 0 for x in limits) else
                              "the dimension has no length")
    return lines, why


def required_tags(item: dict) -> list:
    """The small tag at each required line's end, in the order of required_lines: "min 25'-0\"" (feet-inches, as
    the panel's Required column rounds a minimum: up)."""
    lo_hi = item.get("limit_span_ft")
    limits = [item["limit_ft"]] if isinstance(item.get("limit_ft"), (int, float)) else (
        sorted(set(lo_hi)) if lo_hi else [])
    return ["min " + present.value_text(x, "ft", "≥", False) for x in limits if x > 0]


def required_line(points: list, limit, edges: list) -> list | None:
    """Where the yard's required line crosses its dimension (plan, feet): a short line square to the dimension,
    `limit` from the lot line along it, REQUIRED_HALF_FT either side, drawn faint. The dimension's lot-line end is
    whichever end lies nearer the lot's outline (a measurement's points are a lot-line point and a building point).
    None without a limit in feet or a dimension of some length."""
    from shapely.geometry import LineString, Point
    if not isinstance(limit, (int, float)) or limit <= 0 or not points or len(points) < 2:
        return None
    a, b = [list(p[:2]) for p in points[:2]]
    length = math.dist(a, b)
    if length < 1e-6:
        return None
    if edges:
        ring = LineString([tuple(p[:2]) for e in edges for p in e["points"]])
        if ring.distance(Point(b)) < ring.distance(Point(a)):
            a, b = b, a
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    cx, cy = a[0] + ux * limit, a[1] + uy * limit
    return [[cx - uy * REQUIRED_HALF_FT, cy + ux * REQUIRED_HALF_FT], [cx + uy * REQUIRED_HALF_FT, cy - ux * REQUIRED_HALF_FT]]


DIM_NEAR_FT = 0.02    # a wall run's "nearest part": within this (1/4") of the yard as measured
STRAIGHT_FT = 1e-3    # a footprint point this close to the line through its neighbours lies on a straight wall
BEND_SLACK_FT = 0.5   # at a bend in the lot line in front of the wall: a square dimension at most this much longer


def _wall_runs(footprint) -> list:
    """The footprint's outline as wall runs: its pieces, those that carry straight on joined (a gable's footprint
    keeps a point mid-wall under the ridge: review round 3 of #29, F1)."""
    out = []
    for g in getattr(footprint, "geoms", [footprint]):
        for ring_ in [g.exterior, *g.interiors]:
            pts = [p for p in list(ring_.coords)[:-1]]
            pts = [p for k, p in enumerate(pts) if math.dist(p, pts[k - 1]) > 1e-9]
            n = len(pts)
            if n < 3:
                continue

            def straight(k):                      # pts[k] lies on a straight line from pts[k-1] to pts[k+1]
                a, b, c = pts[k - 1], pts[k], pts[(k + 1) % n]
                cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
                dot = (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1])
                # off the line from a to c by under STRAIGHT_FT (feet, not an angle: a model's single-precision
                # points sit 1e-6 ft off a straight wall; review round 4, F1)
                return abs(cross) / max(math.dist(a, c), 1e-12) <= STRAIGHT_FT and dot > 0
            corners = [k for k in range(n) if not straight(k)]
            for j, k in enumerate(corners):
                end = corners[(j + 1) % len(corners)]
                chain = [pts[(k + i) % n] for i in range(((end - k) % n or n) + 1)]
                out += _straight_runs(chain)
    return out


def _straight_runs(chain: list) -> list:
    """A chain of points joined into runs that each stay within STRAIGHT_FT of their own end-to-end line
    (Douglas-Peucker): a wall drawn as many short pieces along a curve is many runs, never one chord in front of
    it (independent review of #29, round 5)."""
    a, b = chain[0], chain[-1]
    length = math.dist(a, b)
    far, at = 0.0, None
    for k, p in enumerate(chain[1:-1], 1):
        off = (abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / length if length > 1e-12
               else math.dist(a, p))
        if off > far:
            far, at = off, k
    if at is None or far <= STRAIGHT_FT:
        return [(a, b)] if length > 1e-9 else []
    return _straight_runs(chain[:at + 1]) + _straight_runs(chain[at:])


DIM_CANDIDATES = 15   # positions offered along a wall run for the viewport to place a yard's dimension clear


def dim_points(points: list, measure: str, shape, footprint, edges: list, worst: bool = True) -> list:
    """Where a yard's dimension is drawn by preference (plan, feet): [its lot-line end, its building end]; the first
    of dim_candidates, or the measurement's own pair when there is none."""
    found = dim_candidates(points, measure, shape, footprint, edges, worst)
    return found[0] if found else points


def dim_candidates(points: list, measure: str, shape, footprint, edges: list, worst: bool = True) -> list:
    """Where a yard's dimension may be drawn (plan, feet), best first: pairs [its lot-line end, its building end],
    as a drawing would place it (Rhino checks of #29). The building end lies on the wall run facing the yard's lot
    line, never a corner the next yard's dimension shares; the lot end is its square projection onto the lot-line
    piece it falls on (0° by construction). Best is nearest the middle of the run; the viewport takes the first
    whose label sits clear on screen (rhino_logic.place_dimension).
    How far along the run it may go: a yard that fails or needs review (`worst`) is dimensioned where it is
    shortest, within DIM_NEAR_FT of the yard as measured (the drawing never shows more room than the label);
    a complying yard anywhere its dimension is within BEND_SLACK_FT of it (a lot line a fraction of a degree off
    the wall: anywhere along it). At a bend in the lot line right in front of the wall the nearest square position
    within BEND_SLACK_FT. The label is always the yard as measured, its closest point. None (an empty list) when
    there is no lot shape or footprint to work from."""
    from shapely.geometry import LineString, Point
    if not points or len(points) < 2 or shape is None or footprint is None or footprint.is_empty:
        return []
    a, b = [tuple(p[:2]) for p in points[:2]]
    if edges:
        ring = LineString([tuple(p[:2]) for e in edges for p in e["points"]])
        if ring.distance(Point(b)) < ring.distance(Point(a)):
            a, b = b, a
    lines = _yard_lines(shape, measure, a)
    if lines is None:
        return []
    pieces = [(q[k], q[k + 1]) for g in getattr(lines, "geoms", [lines]) for q in [list(g.coords)]
              for k in range(len(q) - 1) if math.dist(q[k], q[k + 1]) > 1e-9]
    near = Point(b)
    measured = lines.distance(near)
    runs = [r for r in _wall_runs(footprint) if LineString(r).distance(near) < 1e-6]
    if not runs or not pieces:
        return []
    facing = min(pieces, key=lambda s: LineString(s).distance(near))

    def turn(run):                                 # how far the run is from parallel to the lot-line piece
        (p, q), (u, w) = run, facing
        cross = (q[0] - p[0]) * (w[1] - u[1]) - (q[1] - p[1]) * (w[0] - u[0])
        return abs(cross) / (math.dist(p, q) * math.dist(u, w))
    p, q = min(runs, key=turn)
    steps = 200
    at = [(p[0] + (q[0] - p[0]) * t / steps, p[1] + (q[1] - p[1]) * t / steps) for t in range(steps + 1)]

    def onto(start, piece):                        # square projection onto a piece, if it falls on it
        (u, w) = piece
        dx, dy = w[0] - u[0], w[1] - u[1]
        t = ((start[0] - u[0]) * dx + (start[1] - u[1]) * dy) / (dx * dx + dy * dy)
        return (u[0] + t * dx, u[1] + t * dy) if -1e-9 <= t <= 1 + 1e-9 else None

    def square(k, slack):                          # the dimension from at[k], if square and short enough
        feet = [x for x in (onto(at[k], piece) for piece in pieces) if x is not None]
        if not feet:
            return None
        foot = min(feet, key=lambda x: math.dist(x, at[k]))
        if footprint.boundary.distance(Point(at[k])) > 1e-6:      # a start never off the wall (backstop)
            return None
        return [list(foot), list(at[k])] if math.dist(foot, at[k]) <= measured + slack + 1e-6 else None
    middle = steps // 2
    # never at the corners themselves; a complying yard's kept off the last twentieth of the wall (room for the
    # neighbouring yard's), a short one where it is shortest, however near the corner that is
    inner = range(1, steps) if worst else range(steps // 20, steps - steps // 20 + 1)
    found = []
    for slack in ((DIM_NEAR_FT, BEND_SLACK_FT) if worst else (BEND_SLACK_FT,)):
        found = [(k, d) for k, d in ((k, square(k, slack)) for k in inner) if d]
        if found:
            break
    if not found:                                   # a short wall: its own ends too
        found = [(k, d) for k, d in ((k, square(k, BEND_SLACK_FT)) for k in range(steps + 1)) if d]
    if len(found) > DIM_CANDIDATES:                 # spread evenly along the run, both ways from the best
        spread = max(1, -(-(found[-1][0] - found[0][0]) // (DIM_CANDIDATES - 1)))
        best = min(found, key=lambda kd: abs(kd[0] - middle))[0]
        found = [(k, d) for k, d in found if (k - best) % spread == 0]
    return [d for k, d in sorted(found, key=lambda kd: abs(kd[0] - middle))]


def height_dim(site: dict, env: dict, v: dict, measured: dict) -> dict | None:
    """The height's vertical dimension for the elevations (feet): from the grade plane up the measured height,
    beside the buildings' corner (HEIGHT_DIM_OFFSET_FT out from it), labelled and coloured as the height row, the
    limit as a faint line across it. None without a grade, a measured height (the larger reading when they
    differ: never drawn lower than it may be) or a building."""
    item = next((i for i in v["items"] if i.get("measure") == "building_height"), None)
    record = (measured or {}).get("building_height") or {}
    value = record.get("value")
    if value is None and record.get("readings"):
        value = max(r["value"] for r in record["readings"] if isinstance(r.get("value"), (int, float)))
    pts = [p for b in site.get("buildings") or [] for f in b.get("faces") or [] for p in f["points"]]
    if item is None or not isinstance(value, (int, float)) or not env or env.get("base") is None or not pts:
        return None
    x = max(p[0] for p in pts) + HEIGHT_DIM_OFFSET_FT
    y = min(p[1] for p in pts) - HEIGHT_DIM_OFFSET_FT
    limit = item.get("limit_ft")
    return {"at": [x, y], "base": env["base"], "top": env["base"] + value, "status": item["status"],
            "label": _dim_label(item), "limit": env["base"] + limit if isinstance(limit, (int, float)) else None}


def plan(site: dict, env: dict, v: dict, measured: dict, facts: dict | None = None) -> dict:
    """What the viewport draws in plan (feet): each lot edge with its length, the yard lines measured (each with
    its item's status), and where the building breaks a limit: the strip of its footprint inside a required yard,
    or the part above the height limit (spec F2, F4, F5). The building itself stays neutral.
    Each yard's red and amber are its own row's (present.settle: from the row's readings, after every status
    change), never another yard's: red where its wall is short under every reading, amber under some."""
    from model_measurement.measure import Lot, _projection
    from shapely.ops import unary_union

    lot = site.get("lot") or {}
    edges = [{"points": [list(r[0][:2]), list(r[-1][:2])], "length": present.feet_inches(length)}
             for r, length in edge_runs(lot.get("edges") or [])
             if length >= SHORTEST_LABELLED_EDGE]   # a tax-map sliver (0'-1 5/8"): no label, it only clutters
    solids = [(b, _projection(b)) for b in site.get("buildings") or [] if b.get("faces")]
    footprint = unary_union([p for _, p in solids]) if solids else None
    shape = Lot(site, facts or {}) if lot.get("edges") and facts and facts.get("street_line") else None
    yards = []
    for i in v["items"]:
        if not (i.get("points") and i.get("measure") in YARD_MEASURES):
            continue
        worst = i["status"] in (present.FAILS, present.REVIEW)
        options = dim_candidates(i["points"], i["measure"], shape, footprint, lot.get("edges") or [], worst) or \
            [i["points"]]
        candidates = []
        for at in options:
            lines, why = required_lines(at, i, lot.get("edges") or [])
            candidates.append({"points": at, "required_lines": lines})
        # a yard with no required line says why, on its label (review round 3, F2)
        yards.append({"points": candidates[0]["points"], "measured_points": i["points"], "status": i["status"],
                      "label": _dim_label(i) + (f" · no required line: {why}" if why else ""),
                      "required_lines": candidates[0]["required_lines"], "required_why": why,
                      "required_tags": required_tags(i), "candidates": candidates})
    encroach = []
    tops = [p[2] for b, _ in solids for f in b["faces"] for p in f["points"]]
    statuses = {i["measure"]: i["status"] for i in v["items"] if i.get("measure")}
    if footprint is not None and not footprint.is_empty and env and env.get("outline") and tops:
        rows = []                                  # (the row, its red region or None, its amber regions)
        for i in v["items"]:
            if i.get("colour") not in ("red", "amber") or shape is None:
                continue
            near, far = [], []
            for limit in i.get("limits") or []:
                lines = _yard_lines(shape, i["measure"], limit["points"][0])
                if lines is None:
                    continue
                strip = (lambda d: footprint.intersection(lines.buffer(d, quad_segs=32)) if d > 0 else None)
                near.append(strip(limit["near"]))
                far.append(strip(limit["far"]))
            red = None
            if i["colour"] == "red" and near and all(g is not None for g in near):
                red = near[0]
                for g in near[1:]:                          # short under EVERY reading: where every one says so
                    red = red.intersection(g)
            rows.append((i, red, [g for g in far if g is not None]))
        reds = [r for _, r, _ in rows if r is not None]
        red_all = unary_union(reds) if reds else None
        # each region is its own row's (the side yard's, the rear yard's…), named on it, and coloured once: where
        # two rows' strips overlap (a corner), the first row's; amber never where any row is red
        taken = {present.FAILS: None, present.REVIEW: red_all}
        regions = []
        for i, red, ambers in rows:
            for region, status in ((red, present.FAILS), (unary_union(ambers) if ambers else None, present.REVIEW)):
                if region is None or region.is_empty:
                    continue
                if taken[status] is not None:
                    region = region.difference(taken[status])
                taken[status] = region if taken[status] is None else unary_union([taken[status], region])
                regions.append((region, status, i))
        # per building: only the part of THAT building in the yard, from its own bottom to its own top (a garage
        # in a side yard is never coloured up to the house's ridge). The viewport then cuts each building by its
        # block (Rhino's boolean), so a cantilever over a yard is coloured, not the air under it. Outlines
        # simplified to 0.001 ft: the subtraction leaves edges 1e-14 ft long, which Rhino can't extrude.
        for region, status, i in regions:
            for b, own in solids:
                zs = [p[2] for f in b["faces"] for p in f["points"]]
                for g in hole_free(region.intersection(own)):
                    if g.area > 1e-3:
                        encroach.append({"outline": _ring(g), "base": min(zs), "top": max(zs), "why": "yard",
                                         "status": status, "building": b.get("id"), "measure": i.get("measure"),
                                         "row": i.get("name")})
        height = statuses.get("building_height")
        if height in (present.FAILS, present.REVIEW) and env.get("top") is not None:
            for b, own in solids:                       # only what rises above the limit: a roof's ridge, not its eaves
                top = max(p[2] for f in b["faces"] for p in f["points"])
                if top <= env["top"] + 1e-6:
                    continue
                region = above(b, env["top"])
                # nothing above it seen from above, or a wall rising over the limit outside what is (a vault read as
                # walls, alone or beside a flat roof): its own plan, never less (independent review of #28, P1, L1)
                if region.is_empty or region.area <= 1e-3 or walls_beyond(b, env["top"], region):
                    region = own
                for g in hole_free(region):
                    if g.area > 1e-3:
                        encroach.append({"outline": _ring(g), "base": env["top"], "top": top, "why": "height",
                                         "status": height, "building": b.get("id"),
                                         "measure": "building_height", "row": "Building height"})
    return {"edges": edges, "yards": yards, "encroach": encroach, "height": height_dim(site, env, v, measured),
            "footprint": [_ring(g) for g in getattr(footprint, "geoms", [footprint])
                          if footprint is not None and not footprint.is_empty and g.geom_type == "Polygon"],
            "buildable": env.get("outline") if env else None, "height_plane": env.get("top") if env else None}


def _start_preview(out: dict, measured: dict) -> dict | None:
    """The start box's preview numbers, in the panel's own words (present.py: a maximum such as coverage is
    rounded up at the shown precision, so the box and the panel always agree)."""
    floors = out.get("floors") or []
    if not floors:
        return None
    ring = floors[0]["outline"]
    sides = [math.dist(ring[i - 1][:2], ring[i][:2]) for i in range(len(ring))]
    lot = (measured.get("lot_area") or {})
    lot_area = lot.get("value") or next((r["value"] for r in lot.get("readings") or []), None)
    area = out.get("area")
    return {"floors": len(floors), "height": present.feet_inches(out.get("height") or 0, "nearest"),
            "size": f"{present.feet_inches(max(sides), 'nearest')} × {present.feet_inches(min(sides), 'nearest')}",
            "area": present._area(area, "up") if area else None,
            "coverage": (present._display(area / lot_area * 100, (out.get("coverage_allowed") or 0) / lot_area * 100,
                                          None, "%", "≤")[0]          # the panel's own text, so they always agree
                         if area and lot_area and out.get("coverage_allowed") else None),
            "limit": (present._pct(out["coverage_allowed"] / lot_area * 100, "down", 2)      # a maximum: down
                      if out.get("coverage_allowed") and lot_area else None),
            "kept_back": present.feet_inches(out["kept_back"], "nearest") if out.get("kept_back") else None}


TAX_MAP_NOTE = ("Starting house keeps 2'-0\" back from each limit because the lot is from the tax map; use a survey "
                "for the full area.")
NOT_PROVEN = ("Starting house: Gordium couldn't keep it clear of the tax map's 2'-0\" tolerance on this lot; the items "
              "that say so need review until a survey.")


def margin_note(keep, buffer, tax, proven):
    """What the starting house keeps back, in the architect's words (Ben's wording when it is the tax map alone)."""
    ft = lambda v: present.feet_inches(v, "nearest")
    if tax and not proven:
        return NOT_PROVEN
    if tax and not buffer:
        return TAX_MAP_NOTE if abs(keep - TAX_MAP_TOLERANCE) < 1e-9 else TAX_MAP_NOTE.replace("2'-0\"", ft(keep), 1)
    if tax:
        return (f"Starting house keeps {ft(keep)} back from each limit: {ft(keep - buffer)} because the lot is from "
                f"the tax map (use a survey for the full area) and {ft(buffer)} your design buffer.")
    if buffer:
        return f"Starting house keeps {ft(keep)} back from each limit (your design buffer)."
    return "Starting house goes to the limits (the lot is from a survey)."


LOT_ONLY = {"lot_area", "lot_width", "lot_depth"}   # items about the lot itself, whatever the house


def _kept_back_building(site, drawing, measured, rules, floor_to_floor, design_buffer):
    """The starting house, kept back from the limits so that it complies even at the tax-map worst case (Ben,
    2026-10-20): on a lot not from a survey, every yard line moves in by the tax-map tolerance and coverage is sized
    for the smallest lot the tax map allows; on a survey it goes to the limits. A design buffer (ft) is added on top
    of either. Proven, not assumed: the house is checked with the panel's own worst case, and if any item would still
    need review from the tolerance (a rear yard minimum also grows with the lot depth) it steps back 3 in. more."""
    from envelope_builder.start import floor_solids
    tax = not drawing.get("lot_surveyed")
    buffer = max(design_buffer or 0.0, 0.0)
    keep = (TAX_MAP_TOLERANCE if tax else 0.0) + buffer
    tol = (measured.get("lot_area") or {}).get("tolerance")
    drawn = next((r["value"] for r in (measured.get("lot_area") or {}).get("readings") or []), None)
    scale = tol["low"] / drawn if tax and tol and drawn else 1.0
    out = largest_legal_building(site, drawing, measured, rules, floor_to_floor=floor_to_floor, keep_back=keep,
                                 coverage_scale=scale)
    proven = not tax
    for _ in range(12):
        if not tax or not out.get("floors"):
            break
        view = check_site({**site, "buildings": floor_solids(out["floors"])}, drawing)["view"]
        if not any(i["status"] == present.REVIEW and "tax map" in (i.get("reason") or "") for i in view["items"]
                   if i.get("measure") and i["measure"] not in LOT_ONLY):   # the lot's own size: no house fixes it
            proven = True
            break
        keep += 0.25
        out = largest_legal_building(site, drawing, measured, rules, floor_to_floor=floor_to_floor, keep_back=keep,
                                     coverage_scale=scale)
    out["kept_back"] = keep
    if out.get("coverage_allowed") and scale:      # the rule's own allowance on the lot as drawn; what it was sized to
        out["coverage_target"] = out["coverage_allowed"]
        out["coverage_allowed"] = out["coverage_allowed"] / scale
    out["margin_note"] = margin_note(keep, buffer, tax, proven) if out.get("floors") else None
    if out["margin_note"] and (tax or buffer):
        out["notes"].append(out["margin_note"])
    return out


def start(model_path: Path, facts: dict, floor_to_floor: float | None = None, design_buffer: float = 0.0) -> dict:
    """The largest legal starting building for the lot in a model (its buildings, if any, left out): stacked
    floor blocks, one per story, from the zone's rules (envelope_builder.start). With no grade set, it is drawn
    standing at the lot's own level (and said so): the check then says height and stories need review until the
    grade is set, so nothing about the height is taken as settled."""
    problems = fact_problems(facts) + [f"no {k} given" for k in ("jurisdiction", "zone") if not facts.get(k)]
    if problems:
        raise ValueError("lot facts: " + "; ".join(problems))
    site = {**read_site(Path(model_path), facts), "buildings": []}
    if site.get("problems"):
        return {"floors": [], "notes": list(site["problems"])}
    rules = load(rulebook_for(REPO / facts["jurisdiction"], facts["zone"]))["rules"]
    # spot grades with no building yet: the grade plane is their average (as the envelope draws it); then drawn on it
    # (the spots themselves aren't at the new building's walls: it's drawn on their plane, and the check that follows
    # judges the spots as they are)
    drawing = facts
    if facts.get("grade_points"):       # their plane sets the drawing level, existing ground too (the check that
        # follows still says existing ground needs review); the points themselves never go on to measure the house
        # drawn (they are at the lot, not at its walls: its height would be "not measurable" and nothing drawn,
        # found in Rhino with the address lookup's ground, 2026-10-20)
        drawing = {k: v for k, v in _envelope_facts(site, {**facts, "grade_is": "finished"}).items()
                   if k not in ("grade_points", "grade_from")}
        drawing["grade_is"] = facts.get("grade_is")
        if drawing["grade_is"] is None:
            drawing.pop("grade_is")
    no_grade = not (drawing.get("ground_is_flat") and drawing.get("grade_elevation") is not None)
    if no_grade:                        # drawn at the lot's level; the check still has no grade
        lot_z = min((p[2] for e in (site.get("lot") or {}).get("edges", []) for p in e["points"] if len(p) > 2),
                    default=0.0)
        drawing = {**{k: v for k, v in drawing.items() if k not in ("grade_points", "grade_from")},
                   "ground_is_flat": True, "grade_elevation": lot_z}
    existing = drawing.get("grade_is") == "existing"
    if existing:                        # drawn standing on the ground shown; the check still says it is existing
        drawing = {**drawing, "grade_is": "finished"}
    measured = measure(site, drawing)
    out = _kept_back_building(site, drawing, measured, rules, floor_to_floor, design_buffer)
    if existing and out.get("floors"):
        out["notes"].append("drawn on the ground as it is: building height and stories need review until you tick "
                            "No regrading near the house (or set the finished ground)")
    out["preview"] = _start_preview(out, measured)
    if no_grade and out.get("floors"):
        out["notes"].append("drawn standing at the lot's level: building height and stories need review until the "
                            "grade is set")
    return out


SAMPLE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"


SAMPLE_OUTLINE = SAMPLE / "lot_outline_tax_map.yaml"


def sample_site() -> dict:
    """The sample project GordiumStart offers: 106 Ithaca Rd's real lot, as the State tax map draws it (parcel
    84.-2-6), placed exactly as the address lookup places it (lot_outline_tax_map.yaml: its source, the frame, made
    by code from a recorded lookup), so the sample and a looked-up 106 are the same drawing and the neighbourhood
    map lines up around it. A tax-map outline: each lot line may be 2'-0" off, so the lot size and every yard are
    checked under every reading of where the lines are. Its facts (zone, use) prefilled for the architect to
    confirm. Points in feet."""
    outline = load(SAMPLE_OUTLINE)
    facts = {**load_facts(SAMPLE / "spreadsheet_design_model_facts.yaml"), "lot_surveyed": False,
             "street_line": outline["street_line"], "corner_lot": bool(outline.get("corner_lot")),
             "plan_north_deg": outline["frame"]["rotation_deg"],     # the plan's turn from true north: compass names
             # each street line's street, as the lookup found it: one street (Ithaca Rd), however it curves
             "street_ids": [" ".join(w.capitalize() for w in str(outline.get("street") or "").split()) or None]
             * len(outline["street_line"])}
    keep = {"jurisdiction", "zone", "use", "street_line", "corner_lot", "ground_is_flat", "grade_elevation",
            "lot_surveyed", "plan_north_deg", "street_ids"}
    return {"address": "106 Ithaca Rd, Ithaca, NY", "lot": [list(p) for p in outline["ring"]],
            "lot_name": "Lot · 106 Ithaca Rd · from the State tax map (parcel " + outline["source"]["print_key"]
                        + "), each line ±2'-0\", not a survey",
            "frame": outline["frame"],
            # the street its street line is on, as the lookup found it on the State tax map ("ITHACA RD"): the
            # box's, like a looked-up street (not a checker fact)
            "street_name": " ".join(w.capitalize() for w in str(outline.get("street") or "").split()) or None,
            "street_source": "the State tax map (the sample's lookup)",
            "facts": {k: v for k, v in facts.items() if k in keep}}


def options(jurisdiction: str) -> dict:
    """What the confirm dialog offers: the zones that have a rulebook, and the city's use names."""
    j = REPO / jurisdiction
    zones = sorted({p.stem for folder in (j / "5_zoning_rules", j / "5_zoning_rules/drafted") if folder.is_dir()
                    for p in folder.glob("*.yaml") if rulebook_for(j, p.stem)})
    uses_file = j / "4_term_definitions/uses.yaml"
    uses = load(uses_file) or {} if uses_file.exists() else {}
    return {"zones": zones, "uses": {k: v.get("name", k) for k, v in uses.items() if isinstance(v, dict)}}
