"""Lot facts in, project file out: the bridge from a measured model to the checker and the report (PR 10).

A project file (see packages/project_report/README.md) is title, jurisdiction, zone and measurements, each
measurement with `from`: where its value came from. Here `from` is the working: how it was measured, between
which points, or why there is no value.
"""

import math
from pathlib import Path

from rule_format.rulebook import load

from .measure import measure
from .read_3dm import read_site

FACT_FIELDS = {"title", "jurisdiction", "zone", "use", "lot_id", "street_line", "grade_elevation", "main_building",
               "stories", "sleeping_rooms", "parking_spaces"}


def _number(x) -> bool:
    return type(x) in (int, float) and math.isfinite(x)


def _point(p) -> bool:
    return isinstance(p, list) and len(p) == 2 and all(_number(v) for v in p)


def fact_problems(facts: dict) -> list[str]:
    """What's wrong with lot facts, by field. One check for every way facts arrive (a file, the Rhino command)."""
    problems = [f"unknown lot fact {k!r}" for k in sorted(set(facts) - FACT_FIELDS)]
    text = {"title", "jurisdiction", "zone", "use", "lot_id", "main_building"}
    problems += [f"{k} must be text" for k in sorted(text & set(facts))
                 if facts[k] is not None and not isinstance(facts[k], str)]
    if facts.get("grade_elevation") is not None and not _number(facts["grade_elevation"]):
        problems.append("grade_elevation must be a number (the ground level, in feet)")
    for k in ("stories", "sleeping_rooms", "parking_spaces"):
        if facts.get(k) is not None and not (type(facts[k]) is int and facts[k] >= 0):
            problems.append(f"{k} must be a whole number, 0 or more")
    street = facts.get("street_line")
    if street is not None and not (isinstance(street, list) and street and all(
            isinstance(s, list) and len(s) == 2 and all(_point(p) for p in s) for s in street)):
        problems.append("street_line must be a list of lot lines, each two points [[x, y], [x, y]]")
    return problems


def load_facts(path: Path) -> dict:
    """A lot facts file: `lot_facts:` with the fields above. Anything else is an error, so a typo can't
    silently drop a fact."""
    data = load(path) or {}
    facts = data.get("lot_facts") if isinstance(data, dict) else None
    if not isinstance(facts, dict) or set(data) != {"lot_facts"}:
        raise ValueError(f"{path}: a lot facts file has exactly one field, lot_facts")
    problems = fact_problems(facts)
    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    return facts


def _num(x) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def working(record: dict, model: str) -> str:
    """The `from` text for one measurement: how it was found, or why it couldn't be."""
    if record["value"] is None:
        text = f"not measured: {record['reason']}"
    elif record["how"].startswith("stated"):
        return f"{record['how']} (lot facts)"
    else:
        text = f"measured from {model}: {record['how']}"
        if record["points"]:
            (ax, ay), (bx, by) = record["points"]
            text += f"; between ({_num(ax)}, {_num(ay)}) and ({_num(bx)}, {_num(by)})"
    if record["readings"]:
        shown = "; ".join(f"{r['reading']} = {_num(r['value'])}" for r in record["readings"])
        text += f" [readings: {shown}]"
    return text


def project(model_path: Path, facts: dict) -> dict:
    """The project file for a model: the facts' title, jurisdiction and zone, and every measurement."""
    problems = fact_problems(facts)
    if problems:
        raise ValueError("lot facts: " + "; ".join(problems))
    measured = measure(read_site(model_path, facts), facts)
    return {"title": facts.get("title") or Path(model_path).stem, "jurisdiction": facts.get("jurisdiction"),
            "zone": facts.get("zone"),
            "measurements": {name: {"value": r["value"], "from": working(r, Path(model_path).name)}
                             for name, r in measured.items()}}
