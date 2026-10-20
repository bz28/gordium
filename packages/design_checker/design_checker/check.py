"""Check a design: measure the model, run the zone's rules, build the envelope, and say it in one line.

Every result comes from the project report (PR 10), which takes them only from the checker's `outcome()` and
refuses a rulebook that fails the rule checks. This module adds nothing to a result; it only gathers what the
Rhino panel and the viewport message show: the rows, a short summary, the objects to show in red, the envelope.
"""

import ast
import itertools
import math
import re
import tempfile
from pathlib import Path

import yaml

from envelope_builder.envelope import envelope
from envelope_builder.start import largest_legal_building
from model_measurement.measure import measure
from model_measurement.project import fact_problems, load_facts, working
from model_measurement.read_3dm import read_site
from project_report.report import OUTPUT_EXTRA, OUTPUT_HEADERS, build, tables
from rule_format import formula
from rule_format.rulebook import MEASURE_KINDS, REPO, Context, load, outcome, rulebook_for

COLUMNS = OUTPUT_HEADERS + OUTPUT_EXTRA
# Facts about the inside of a building (rooms, parking spaces). This phase checks the outside only: a rule waiting
# on one of these goes in its own group, "not checked yet: interior", out of the counts. A rule they decide once
# entered (a FAIL included) is shown like any other: nothing that fails is ever hidden.
INTERIOR = {"sleeping_rooms", "parking_spaces"}
NUMBER = re.compile(r"^([≥≤<>=]) (-?[\d,]+(?:\.\d+)?)$")


def short(title: str) -> str:
    """A rule's title, short enough for one line: 'Rear yard minimum (chart p.3, …)' -> 'Rear yard'."""
    words = title.split(" (")[0].split(",")[0]
    words = re.sub(r"^(Maximum|Minimum) ", "", words)
    words = re.sub(r" (minimum|maximum)$", "", words)
    return words[:1].upper() + words[1:]


def _amount(row: dict) -> str:
    """'Rear yard 20 ft, needs ≥ 22.5 ft (2.5 ft short)' for a one-number limit; else the formula's words."""
    limit, proposed, units = row["Table limit"], row["Proposed"], row["Units"]
    m = NUMBER.match(str(limit))
    if m and isinstance(proposed, (int, float)):
        need = float(m.group(2).replace(",", ""))
        gap = abs(proposed - need)
        side = "over" if m.group(1) in "≤<" else "short"
        return f"{short(row['Requirement'])} {_n(proposed)} {units}, needs {limit} {units} ({_n(gap)} {units} {side})"
    return f"{short(row['Requirement'])}: {proposed} (needs {limit})"


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


MAX_COMBINATIONS = 200     # more combinations of readings than this: not worked out (stays a plain NEEDS REVIEW)
SURVEY = "lot_area"        # a lot not yet surveyed: its one reading is the lot as drawn


def every_reading(rule: dict, measured: dict, allowed: dict) -> tuple[str, str] | None:
    """For a rule that needs review only because measurements have readings instead of a value: ("pass", how) if
    it passes under every combination of their readings (taken independently, which covers every real
    combination), ("fail", how) if it fails under every one, else None (or when a measurement has no reading, or
    there are too many). Never a result: the row stays NEEDS REVIEW (only outcome() decides results); this says
    the design complies, or doesn't, whichever way the open question is answered."""
    names = set()
    for key in ("applies_when", "check"):
        if rule.get(key):
            names |= formula.names(rule[key])
    for r in rule.get("review_when") or []:
        names |= formula.names(r["when"])
    open_ = sorted(n for n in names if (measured.get(n) or {}).get("value") is None)
    choices = [[x["value"] for x in (measured.get(n) or {}).get("readings") or []] for n in open_]
    if not open_ or any(not c for c in choices) or math.prod(len(c) for c in choices) > MAX_COMBINATIONS:
        return None
    values = {k: m["value"] for k, m in measured.items()}
    got = {outcome(rule, {**values, **dict(zip(open_, combo))}, allowed) for combo in itertools.product(*choices)}
    if got not in ({"pass"}, {"fail"}):
        return None
    word = "passes" if got == {"pass"} else "fails"
    survey = SURVEY in open_ and len(choices[open_.index(SURVEY)]) == 1
    others = [n for n in open_ if n != SURVEY or not survey]
    return got.pop(), (f"{word} with the lot as drawn (confirm the survey)" if survey and not others else
                       f"{word} under every reading of the lot" +
                       (" and with the lot as drawn (confirm the survey)" if survey else ""))


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
    lines = [_amount(r) if r["Error"] == "FAIL" else f"{short(r['Requirement'])}: {r['Provisional']}" for r in fails]
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
                          "label": f"{name.replace('_', ' ')} {_n(m['value'])} ft, needs {sign} {_n(need)}"})
    return found


def check(model_path: Path, facts: dict, report_path: Path | None = None, building_problems: list | None = None) -> dict:
    """Everything the Rhino command shows, for one model and its lot facts. `building_problems` are what the
    Rhino command found on the Building layer and couldn't send (a block, a surface): each one makes every
    building measure need review, never silently dropped."""
    problems = fact_problems(facts)            # the same check as a facts file: a plain refusal, never a crash
    problems += [f"no {k} given" for k in ("jurisdiction", "zone") if not facts.get(k)]
    if problems:
        raise ValueError("lot facts: " + "; ".join(problems))
    model_path = Path(model_path)
    site = read_site(model_path, facts)
    if building_problems:
        site["buildings"].append({"id": "Building layer", "faces": [], "problems": list(building_problems)})
    measured = measure(site, facts)
    project = {"title": facts.get("title") or model_path.stem, "jurisdiction": facts.get("jurisdiction"),
               "zone": facts.get("zone"),
               "measurements": {k: {"value": m["value"], "from": working(m, model_path.name)} for k, m in measured.items()}}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "project.yaml"
        path.write_text(yaml.safe_dump(project, sort_keys=False, allow_unicode=True))
        t = tables(path)              # refuses a project or rulebook that fails its checks (ValueError)
    if report_path is not None:
        build(t).save(report_path)
    rules = load(rulebook_for(REPO / facts["jurisdiction"], facts["zone"]))["rules"]
    by_id = {r["id"]: r for r in rules}
    every = [_why(dict(zip(COLUMNS, r)), by_id, measured) for r in t["output"]]
    def checks(rule):                   # a flag has no check
        return formula.names(rule["check"]) if rule.get("check") else set()

    waiting = [r for r in every if r["Error"] == "NEEDS REVIEW" and any(
        (measured.get(n) or {}).get("value") is None for n in checks(by_id[r["Rule id"]]) & INTERIOR)]
    rows = [{**r, "Line": _amount(r)} if r["Error"] == "FAIL" else r for r in every if r not in waiting]
    for r in rows:
        r["Short"] = short(r["Requirement"])
    allowed = {"use": Context.for_jurisdiction(REPO / facts["jurisdiction"]).uses}
    for r in rows:
        found = every_reading(by_id[r["Rule id"]], measured, allowed) if r["Error"] == "NEEDS REVIEW" else None
        r["Provisional"] = found[1] if found else None
        r["Survey"] = bool(found and "confirm the survey" in found[1])     # waits on a fact, not an interpretation
        r["Fails"] = r["Error"] == "FAIL" or bool(found and found[0] == "fail")   # fails whichever way it goes
        if r["Fails"] and not r.get("Line"):
            r["Line"] = f"{short(r['Requirement'])}: {r['Provisional']}"
    lot_id = (site.get("lot") or {}).get("id")
    red = sorted({o for r in rows if r["Fails"]
                  for name in formula.names(by_id[r["Rule id"]]["check"]) for o in measured.get(name, {}).get("objects", [])
                  if o != lot_id})
    values = {k: m["value"] for k, m in measured.items()}
    dims = [d for r in rows if r["Error"] == "FAIL" for d in _failing_distances(by_id[r["Rule id"]], measured, values)]
    return {"rows": rows, "interior": waiting, "not_applicable": [dict(zip(COLUMNS, r)) for r in t["not_applicable"]],
            "summary": summary(rows), "red": red, "dims": dims, "measurements": measured,
            "envelope": envelope(site, facts, measured, rules), "problems": site.get("problems") or []}


def start(model_path: Path, facts: dict) -> dict:
    """The largest legal starting building for the lot in a model (its buildings, if any, left out): stacked
    floor blocks, one per story, from the zone's rules (envelope_builder.start)."""
    problems = fact_problems(facts) + [f"no {k} given" for k in ("jurisdiction", "zone") if not facts.get(k)]
    if problems:
        raise ValueError("lot facts: " + "; ".join(problems))
    site = {**read_site(Path(model_path), facts), "buildings": []}
    if site.get("problems"):
        return {"floors": [], "notes": list(site["problems"])}
    rules = load(rulebook_for(REPO / facts["jurisdiction"], facts["zone"]))["rules"]
    return largest_legal_building(site, facts, measure(site, facts), rules)


SAMPLE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"


def sample_site() -> dict:
    """The sample project GordiumStart offers: 106 Ithaca Rd's lot as the architects' spreadsheet gives it,
    73'-0" x 90'-0" (their model of it; not a survey, so lot size and coverage wait for one), and its facts,
    prefilled for the architect to confirm. Points in feet."""
    facts = {**load_facts(SAMPLE / "spreadsheet_design_model_facts.yaml"), "lot_surveyed": False}
    site = read_site(SAMPLE / "spreadsheet_design_model.3dm", facts)
    lot = site.get("lot") or {}
    points = [e["points"][0] for e in lot.get("edges") or []]
    keep = {"jurisdiction", "zone", "use", "street_line", "corner_lot", "ground_is_flat", "grade_elevation",
            "lot_surveyed"}
    return {"address": "106 Ithaca Rd, Ithaca, NY", "lot": points,
            "lot_name": "Lot · 106 Ithaca Rd · 73'-0\" x 90'-0\" from the architects' spreadsheet, not a survey",
            "facts": {k: v for k, v in facts.items() if k in keep}}


def options(jurisdiction: str) -> dict:
    """What the confirm dialog offers: the zones that have a rulebook, and the city's use names."""
    j = REPO / jurisdiction
    zones = sorted({p.stem for folder in (j / "5_zoning_rules", j / "5_zoning_rules/drafted") if folder.is_dir()
                    for p in folder.glob("*.yaml") if rulebook_for(j, p.stem)})
    uses_file = j / "4_term_definitions/uses.yaml"
    uses = load(uses_file) or {} if uses_file.exists() else {}
    return {"zones": zones, "uses": {k: v.get("name", k) for k, v in uses.items() if isinstance(v, dict)}}
