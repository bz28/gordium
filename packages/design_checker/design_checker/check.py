"""Check a design: measure the model, run the zone's rules, build the envelope, and say it in one line.

Every result comes from the project report (PR 10), which takes them only from the checker's `outcome()` and
refuses a rulebook that fails the rule checks. This module adds nothing to a result; it only gathers what the
Rhino panel and the viewport message show: the rows, a short summary, the objects to show in red, the envelope.
"""

import ast
import itertools
import math
import os
import re
import tempfile
from pathlib import Path

import yaml

from design_checker import present
from envelope_builder.envelope import MARGIN, envelope
from envelope_builder.start import largest_legal_building
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


MAX_COMBINATIONS = 200     # more combinations of readings than this: not worked out (stays a plain NEEDS REVIEW)
SURVEY = "lot_area"        # a lot not yet surveyed: its one reading is the lot as drawn


OVERHANG_WORDS = {"eave": "the overhang an eave", "story": "the overhang part of a story"}   # measure.OVERHANG


def _reading_words(tag: str, rid: str) -> str:
    if tag == "model#overhang":
        return OVERHANG_WORDS.get(rid, rid)
    return rid.replace("_", " ")


def readings_of(rule: dict, measured: dict, allowed: dict) -> dict | None:
    """Every combination of the readings a rule's open measurements have, and the rule's outcome under each:
    {"result": "pass" | "fail" | "mixed", "named": every reading is one research lists (by question), "tags",
    "fails_under" / "passes_under": the named readings each way, "combos": the values of each combination}.
    None when a measurement has no reading, or there are too many.

    Readings research lists are combined question by question: one answer to an open question holds for the
    whole design (a garage's roof and the house's are read with the same eave). Any other reading (a jog as a
    side or a rear line, a solid that may be a deck) varies on its own, which covers every real combination."""
    names = set()
    for key in ("applies_when", "check"):
        if rule.get(key):
            names |= formula.names(rule[key])
    for r in rule.get("review_when") or []:
        names |= formula.names(r["when"])
    open_ = sorted(n for n in names if (measured.get(n) or {}).get("value") is None)
    readings = {n: (measured.get(n) or {}).get("readings") or [] for n in open_}
    if not open_ or any(not readings[n] for n in open_):
        return None
    tags = sorted({t for n in open_ for r in readings[n] for t in r.get("named") or {}})
    ids = [sorted({r["named"][t] for n in open_ for r in readings[n] if t in (r.get("named") or {})}) for t in tags]
    if math.prod(len(i) for i in ids) > MAX_COMBINATIONS:
        return None
    values = {k: m["value"] for k, m in measured.items()}
    named, combos, fails, passes, got, total = bool(tags), [], [], [], set(), 0
    for picked in itertools.product(*ids):
        answer = dict(zip(tags, picked))
        choices = []
        for n in open_:
            fits = list(dict.fromkeys(r["value"] for r in readings[n]
                                      if all(answer.get(t) == v for t, v in (r.get("named") or {}).items())))
            if not fits:
                return None
            # named: under each answer the measurement has one value (readings that differ only in other ways but
            # give the same number leave nothing else open)
            named &= len(fits) == 1 and all(r.get("named") for r in readings[n])
            choices.append(fits)
        total += math.prod(len(c) for c in choices)
        if total > MAX_COMBINATIONS:
            return None
        here = set()
        for combo in itertools.product(*choices):
            trial = {**values, **dict(zip(open_, combo))}
            here.add(outcome(rule, trial, allowed))
            combos.append(trial)
        got |= here
        words = ", ".join(_reading_words(t, v) for t, v in answer.items())
        if "fail" in here or "needs_review" in here:
            fails.append(words)
        if here == {"pass"}:
            passes.append(words)
    result = "pass" if got == {"pass"} else "fail" if got == {"fail"} else "mixed"
    return {"result": result, "named": named, "tags": tags, "fails_under": fails, "passes_under": passes,
            "combos": combos, "open": open_}


def every_reading(rule: dict, measured: dict, allowed: dict) -> tuple[str, str] | None:
    """For a rule that needs review only because measurements have readings instead of a value: ("pass", how) if
    it passes under every combination of their readings, ("fail", how) if it fails under every one, else None
    (or when a measurement has no reading, or there are too many). Results come only from outcome(); this says
    the design complies, or doesn't, whichever way the open question is answered. Whether that is shown as a
    result depends on the readings (named_result)."""
    found = readings_of(rule, measured, allowed)
    if found is None or found["result"] == "mixed":
        return None
    word = "passes" if found["result"] == "pass" else "fails"
    open_ = found["open"]
    survey = SURVEY in open_ and len((measured.get(SURVEY) or {}).get("readings") or []) == 1
    others = [n for n in open_ if n != SURVEY or not survey]
    return found["result"], (f"{word} with the lot as drawn (confirm the survey)" if survey and not others else
                             f"{word} under every reading" +
                             (" and with the lot as drawn (confirm the survey)" if survey else ""))


def named_result(rule: dict, measured: dict, allowed: dict) -> dict | None:
    """The "every reading" rule for open questions research has named readings for: when every reading a
    rule's open measurements have is one of those (nothing else unknown: no survey waiting, no model question),
    the rule complies if it passes under all of them, does not comply if it fails under all of them, and needs
    review otherwise, naming the readings it fails under. {"result", "text", "tags", "fails_under",
    "passes_under", "combos"}, or None when it doesn't apply (the row keeps the plain rule)."""
    found = readings_of(rule, measured, allowed)
    if found is None or not found["named"]:
        return None
    every = "; ".join(found["passes_under"] + [w for w in found["fails_under"] if w not in found["passes_under"]])
    text = {"pass": f"complies under every reading of the open question ({every})",
            "fail": f"does not comply under any reading of the open question ({every})",
            "mixed": (f"does not comply if the open question is answered {' or '.join(found['fails_under'])}; "
                      f"complies if {' or '.join(found['passes_under']) or 'none'}")}[found["result"]]
    return {**found, "text": text}


def summary(rows: list[dict]) -> dict:
    """One line for the viewport corner: all pass; it complies under every reading (rules waiting only on how the
    law is read, each passing whichever way it goes); or what fails and what needs review. A rule that passes only
    with the lot as drawn still needs review (amber) until the survey is confirmed: a lot not yet surveyed is a
    missing fact, not a reading, so it is never shown as complying."""
    fails = [r for r in rows if r.get("Fails") or r["Error"] == "FAIL"]
    named = [r for r in rows if (r.get("Named") or {}).get("result") == "pass"]   # complies under every reading
    review = [r for r in rows if r["Error"] == "NEEDS REVIEW" and r not in fails and r not in named]
    passes = [r for r in rows if r["Error"] == "PASS"] + named
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
    lines += [f"{short(r['Requirement'])}: {r.get('Provisional') or (r.get('Named') or {}).get('text') or r['Why']}"
              for r in review]
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
    worst = {}
    for i in view["items"]:
        if i["rule"] and i["status"] in word:
            rank = present.ORDER.index(i["status"])
            if i["rule"] not in worst or rank < present.ORDER.index(worst[i["rule"]][0]):
                worst[i["rule"]] = (i["status"], i.get("reason") or "")
    col = {h: n for n, h in enumerate(COLUMNS)}
    rows = []
    for r in t["output"]:
        r = list(r)
        found = worst.get(r[col["Rule id"]])
        if found:
            r[col["Error"]], r[col["Comparison"]] = word[found[0]]
            if found[0] == present.REVIEW and found[1]:
                r[col["Why it needs review"]] = found[1]
        rows.append(r)
    wb = build({**t, "output": rows})
    ws = wb.create_sheet("Check")
    h = view["header"]
    title(ws, f"GORDIUM | {view['summary']}")
    lines = [h["place"], h["code"], h["draft"], h["lot"], h["grade"]] + (h.get("sources") or [])   # where each fact came from
    for n, text in enumerate(lines, start=2):
        ws.cell(row=n, column=1, value=text)
    by_id = {i["id"]: i for i in view["items"]}
    out = []
    for g in present.grouped(view["items"]):
        for item_id in g["items"]:
            i = by_id[item_id]
            out.append([g["title"], i["mark"], i["name"], i["proposed"], i["required"], i["margin"],
                        i.get("reason") or "", i["detail"].get("citation") or "",
                        (i["detail"].get("links") or [""])[0]])
    write_block(ws, len(lines) + 3, [("Group", 22), ("Mark", 6), ("Item", 34), ("Proposed", 12), ("Required", 12),
                                     ("Margin", 10), ("Why it needs review", 60), ("Citation", 50), ("Link", 40)], out)
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
    rows = [{**r, "Line": _amount(r, by_id[r["Rule id"]], measured)} if r["Error"] == "FAIL" else r
            for r in every if r not in waiting]
    for r in rows:
        r["Short"] = short(r["Requirement"])
    allowed = {"use": Context.for_jurisdiction(REPO / facts["jurisdiction"]).uses}
    for r in rows:
        review = r["Error"] == "NEEDS REVIEW"
        named = named_result(by_id[r["Rule id"]], measured, allowed) if review else None
        found = every_reading(by_id[r["Rule id"]], measured, allowed) if review and not named else None
        r["Named"] = named              # every reading research lists: complies / does not comply / needs review
        r["Provisional"] = found[1] if found else None
        r["Survey"] = bool(found and "confirm the survey" in found[1])     # waits on a fact, not an interpretation
        r["Fails"] = r["Error"] == "FAIL" or bool(found and found[0] == "fail") or bool(
            named and named["result"] == "fail")   # fails whichever way it goes
        if r["Fails"] and named and not r.get("Line"):
            r["Line"] = f"{short(r['Requirement'])}: {named['text']}"
        if r["Fails"] and not r.get("Line"):
            r["Line"] = f"{short(r['Requirement'])}: {r['Provisional']}"
    lot_id = (site.get("lot") or {}).get("id")
    red = sorted({o for r in rows if r["Fails"]
                  for name in formula.names(by_id[r["Rule id"]]["check"]) for o in measured.get(name, {}).get("objects", [])
                  if o != lot_id})
    values = {k: m["value"] for k, m in measured.items()}
    dims = [d for r in rows if r["Error"] == "FAIL" for d in _failing_distances(by_id[r["Rule id"]], measured, values)]
    v = present.view(rows, waiting, by_id, measured, facts, extras)
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
            "envelope": env, "problems": site.get("problems") or [], "view": v, "plan": plan(site, env, v, measured),
            "report_error": report_error,
            "statuses": statuses, "notice": notice_text}


def _envelope_facts(site: dict, facts: dict) -> dict:
    """The facts the envelope is drawn from. Spot grades (or terrain sampled at the walls) that the measuring
    accepts give the grade plane, so the height plane is drawn from it; existing ground never sets it (it isn't
    the grade the code measures from), so then only the buildable area is drawn."""
    if facts.get("grade_is") == "existing":
        return {**facts, "ground_is_flat": None}
    if facts.get("grade_points"):
        from model_measurement.measure import grade_plane
        grade, why = grade_plane(site.get("buildings") or [], facts)
        return {**facts, "ground_is_flat": True, "grade_elevation": grade} if why is None else {**facts, "ground_is_flat": None}
    return facts


def _ring(polygon) -> list:
    """A polygon's outline as [[x, y], ...], without edges shorter than 0.001 ft."""
    return [list(p) for p in polygon.simplify(0.001).exterior.coords[:-1]]


YARD_MEASURES = ("front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard")


def plan(site: dict, env: dict, v: dict, measured: dict) -> dict:
    """What the viewport draws in plan (feet): each lot edge with its length, the yard lines measured (each with
    its item's status), and where the building breaks a limit: the strip of its footprint inside a required yard,
    or the part above the height limit (spec F2, F4, F5). The building itself stays neutral."""
    from model_measurement.measure import _projection
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    lot = site.get("lot") or {}
    edges = []
    for e in lot.get("edges") or []:
        a, b = e["points"][0], e["points"][-1]
        length = sum(math.dist(p[:2], q[:2]) for p, q in zip(e["points"], e["points"][1:]))
        edges.append({"points": [list(a[:2]), list(b[:2])], "length": present.feet_inches(length)})
    yards = [{"points": i["points"], "status": i["status"], "label": f"{i['mark']} {i['name']} {i['proposed']}" +
              ("" if i["status"] != present.REVIEW or "tax map" not in (i.get("reason") or "") else " (approx.)")}
             for i in v["items"] if i.get("points") and i.get("measure") in YARD_MEASURES]
    encroach = []
    plans = [_projection(b) for b in site.get("buildings") or [] if b.get("faces")]
    footprint = unary_union(plans) if plans else None
    tops = [p[2] for b in site.get("buildings") or [] for f in b.get("faces") or [] for p in f["points"]]
    statuses = {i["measure"]: i["status"] for i in v["items"] if i.get("measure")}
    if footprint is not None and not footprint.is_empty and env and env.get("outline") and tops:
        # the envelope sits MARGIN inside every yard (so it is never illegal); grown back by twice that, a wall
        # exactly at its limit leaves no hairline of red
        buildable = Polygon(env["outline"], env.get("holes") or []).buffer(2 * MARGIN, join_style=2)
        yard_fail = any(s == present.FAILS for m, s in statuses.items() if m in YARD_MEASURES)
        strip = footprint.difference(buildable) if yard_fail else None
        # outlines simplified to 0.001 ft: the subtraction leaves edges 1e-14 ft long, which Rhino can't extrude;
        # without a grade the strip stands on the building's own base, never at 0
        for g in getattr(strip, "geoms", [strip]) if strip is not None and not strip.is_empty else []:
            if g.area > 1e-3:
                encroach.append({"outline": _ring(g), "base": env["base"] if env.get("base") is not None else min(tops),
                                 "top": max(tops), "why": "yard"})
        if statuses.get("building_height") == present.FAILS and env.get("top") is not None and max(tops) > env["top"]:
            for g in getattr(footprint, "geoms", [footprint]):
                encroach.append({"outline": _ring(g), "base": env["top"], "top": max(tops), "why": "height"})
    return {"edges": edges, "yards": yards, "encroach": encroach,
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
                   if i.get("measure")):
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
