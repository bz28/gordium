"""Check a design: measure the model, run the zone's rules, build the envelope, and say it in one line.

Every result comes from the project report (PR 10), which takes them only from the checker's `outcome()` and
refuses a rulebook that fails the rule checks. This module adds nothing to a result; it only gathers what the
Rhino panel and the viewport message show: the rows, a short summary, the objects to show in red, the envelope.
"""

import ast
import re
import tempfile
from pathlib import Path

import yaml

from envelope_builder.envelope import envelope
from model_measurement.measure import measure
from model_measurement.project import fact_problems, working
from model_measurement.read_3dm import read_site
from project_report.report import OUTPUT_EXTRA, OUTPUT_HEADERS, build, tables
from rule_format import formula
from rule_format.rulebook import MEASURE_KINDS, REPO, load, rulebook_for

COLUMNS = OUTPUT_HEADERS + OUTPUT_EXTRA
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


def summary(rows: list[dict]) -> dict:
    """One line for the viewport corner: all pass, or what fails and what needs review."""
    fails = [r for r in rows if r["Error"] == "FAIL"]
    review = [r for r in rows if r["Error"] == "NEEDS REVIEW"]
    passes = [r for r in rows if r["Error"] == "PASS"]
    if not fails and not review:
        return {"state": "pass", "text": f"All {len(passes)} rules pass", "lines": []}
    lines = [_amount(r) for r in fails] + [f"{short(r['Requirement'])}: {r['Why']}" for r in review]
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
    rows = [_why(dict(zip(COLUMNS, r)), by_id, measured) for r in t["output"]]
    lot_id = (site.get("lot") or {}).get("id")
    red = sorted({o for r in rows if r["Error"] == "FAIL"
                  for name in formula.names(by_id[r["Rule id"]]["check"]) for o in measured.get(name, {}).get("objects", [])
                  if o != lot_id})
    values = {k: m["value"] for k, m in measured.items()}
    dims = [d for r in rows if r["Error"] == "FAIL" for d in _failing_distances(by_id[r["Rule id"]], measured, values)]
    return {"rows": rows, "not_applicable": [dict(zip(COLUMNS, r)) for r in t["not_applicable"]],
            "summary": summary(rows), "red": red, "dims": dims, "measurements": measured,
            "envelope": envelope(site, facts, measured, rules), "problems": site.get("problems") or []}


def options(jurisdiction: str) -> dict:
    """What the confirm dialog offers: the zones that have a rulebook, and the city's use names."""
    j = REPO / jurisdiction
    zones = sorted({p.stem for folder in (j / "5_zoning_rules", j / "5_zoning_rules/drafted") if folder.is_dir()
                    for p in folder.glob("*.yaml") if rulebook_for(j, p.stem)})
    uses_file = j / "4_term_definitions/uses.yaml"
    uses = load(uses_file) or {} if uses_file.exists() else {}
    return {"zones": zones, "uses": {k: v.get("name", k) for k, v in uses.items() if isinstance(v, dict)}}
