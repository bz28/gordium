"""The compliance report for one project, in the architects' own spreadsheet format.

The architects check a design with a two-tab workbook (test_data/answer_keys/.../Gordium_Single_Family_Simple_v1.xlsx):
"Inputs" (the design's numbers, then the table values the check uses) and "Output" (one row per requirement:
Requirement · Table limit · Proposed · Units · Comparison · PDF page · Error, where "Error" holds PASS/FAIL).
This module fills in the same two tabs for any project file, from the rulebook for its zone. Plain code, no AI.

- Which rows: every rule in the zone's rulebook (`rulebook_for`: hand-drafted first, else AI-drafted). Rules
  that apply (or whose applicability can't be decided) come first; rules that don't apply are listed after,
  under their own heading, so nothing is silently dropped.
- The result of every row comes from `rule_format.outcome()` and nothing else.
- "Table limit" and "Proposed" are read off the rule's own formula: each comparison of a measure against an
  expression is evaluated with this project's numbers, e.g. rear_yard >= max(min(0.25 * lot_depth, 50), 20)
  gives a limit of 22.5 ft for a 90 ft deep lot. A formula that isn't made of such comparisons shows its
  formula only. The formula is always in its own column.
- Our columns go after the architects' seven: the rule id, the formula, why a row needs review, the city's
  exact words, the page and a link, which rulebook it came from.
"""

import ast
import math
from pathlib import Path

import yaml
from openpyxl import Workbook

from openpyxl.styles import Border, Font, PatternFill, Side
from rule_export.workbook import FONT, INK, citer, page_link, title, write_block
from . import plain
from rule_format import formula
from rule_format.formula import EvaluationError, MissingMeasure
from rule_format.published import frozen
from rule_format.rulebook import MEASURE_KINDS, MEASURES_FILE, REPO, load, load_bytes, outcome, rulebook_for

# The architects' tab names and headers, copied from their file, in their order.
INPUTS_TAB, OUTPUT_TAB = "Inputs", "Output"
INPUTS_TITLE = "Inputs and sources"
INPUT_HEADERS = ["Model / project input", "Value", "Units / meaning"]
PARAMETER_HEADERS = ["Table parameters", "Value", "Source: tables PDF"]
OUTPUT_HEADERS = ["Requirement", "Table limit", "Proposed", "Units", "Comparison", "PDF page", "Error"]
# Ours, after theirs.
INPUT_EXTRA = ["Where the value comes from"]
PARAMETER_EXTRA = ["Rule", "Link"]
OUTPUT_EXTRA = ["Rule id", "Formula", "Why it needs review", "Citation", "City's exact words", "Link", "Rulebook"]
# What the Output tab shows after the architects' columns (in their words); the rule id, formula and rulebook,
# for checking the rules themselves, are on their own tab at the end (TRACE_TAB).
OUTPUT_SHOWN = ["Why it needs review", "Citation", "City's exact words", "Link"]
TRACE_TAB = "Rule trace"
TRACE_HEADERS = ["Requirement", "Rule id", "Formula", "Rulebook"]

RESULT = {"pass": "PASS", "fail": "FAIL", "needs_review": "NEEDS REVIEW", "not_applicable": "NOT APPLICABLE"}
COMPARISON = {"pass": "Within table limit", "fail": "Outside table limit", "needs_review": "Needs review",
              "not_applicable": "Not applicable"}
INPUT_FILL = "FFFFF1BF"                # the architects' yellow for values typed in
OURS_FILL = "FFDDEBF7"                 # light blue on the headers of the columns we add; not a color in their
                                       # key (there yellow = typed in, grey = worked out by formula)
RESULT_INK = {"FAIL": "FF0000", "NEEDS REVIEW": "9A6400"}   # their FAIL is red; review is amber
# Column widths: theirs where their file sets one (Inputs A-C; Output A, B, D-G; their Output C has none, so
# Excel's default, and ours is 14 to fit a list of measurements), then ours.
INPUT_WIDTHS = [43, 17, 46.375, 40]
OUTPUT_WIDTHS = [34, 20, 14, 12, 25, 14, 12.625] + [28, 40, 40, 40, 60, 10, 30]
OUTPUT_SHOWN_WIDTHS = [34, 20, 14, 12, 25, 14, 12.625] + [50, 40, 60, 10]

MEASURES = load(MEASURES_FILE)
SYMBOL = {ast.GtE: "≥", ast.LtE: "≤", ast.Gt: ">", ast.Lt: "<", ast.Eq: "=", ast.NotEq: "≠"}
PROJECT_FIELDS = {"title", "jurisdiction", "zone", "measurements", "spreadsheet", "compare"}


# ---- the project file ----------------------------------------------------------------------------------

def load_project(path: Path) -> dict:
    """A project file: title, jurisdiction (a folder), zone, and measurements {name: {value, from}}. Fields the
    answer-key test uses (spreadsheet, compare) may be there too. Anything else is an error, so a typo can't
    silently drop a value."""
    try:
        project = load(path) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        raise ValueError(f"{path}: can't read the project file ({type(e).__name__}: {e})") from e
    if not isinstance(project, dict):
        raise ValueError(f"{path}: a project file must be a mapping of fields (title, jurisdiction, zone, measurements)")
    if "measurements" in project and not isinstance(project["measurements"], dict):
        raise ValueError(f"{path}: measurements must be a mapping {{name: {{value, from}}}}")
    problems = [f"unknown field {k!r}" for k in project if k not in PROJECT_FIELDS]
    problems += [f"missing {k!r}" for k in ("title", "jurisdiction", "zone", "measurements") if k not in project]
    problems += [f"{k!r} must be text" for k in ("title", "jurisdiction", "zone")
                 if k in project and not (isinstance(project[k], str) and project[k].strip())]
    for name, m in (project.get("measurements") or {}).items():
        if name not in MEASURES:
            problems.append(f"measurement {name!r} isn't in measures.yaml")
        elif not (isinstance(m, dict) and m.keys() == {"value", "from"}):
            problems.append(f"measurement {name!r} needs exactly a value and where it comes from ('from')")
        elif not (isinstance(m["from"], str) and m["from"].strip()):
            problems.append(f"measurement {name!r} needs where it comes from ('from'), as text")
        elif not (m["value"] is None or type(m["value"]) in (int, str)
                  or type(m["value"]) is float and math.isfinite(m["value"])
                  or type(m["value"]) is bool and MEASURE_KINDS.get(name) == "boolean"):
            problems.append(f"measurement {name!r} value must be a number or text (a finite number; yes/no for a yes/no "
                            "measure; or empty: not measured yet)")
    if not problems:                             # a real jurisdiction inside the repo, with its source list
        j = (REPO / project["jurisdiction"]).resolve()
        places = (REPO / "regulations/jurisdictions").resolve()
        if not (j.is_relative_to(places) and (j / "1_source_documents/sources.yaml").is_file()):
            problems.append(f"jurisdiction {project['jurisdiction']!r} isn't a jurisdiction folder in "
                            "regulations/jurisdictions (one with 1_source_documents/sources.yaml)")
    if not problems and rulebook_for(REPO / project["jurisdiction"], project["zone"]) is None:
        problems.append(f"no rulebook for zone {project['zone']!r} in {project['jurisdiction']}")
    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    return project


# ---- reading limits off a formula -----------------------------------------------------------------------

def _number(x) -> str:
    """A number as people write it (6,674; 22.5); anything else as it is, so a wrong kind of value (true, '25')
    never looks like a usable number."""
    if type(x) is float and math.isfinite(x):
        return f"{x:,.2f}".rstrip("0").rstrip(".")
    return f"{x:,}" if type(x) is int else repr(x)


def _pretty(text: str) -> str:
    """A formula with the comparison signs people write (≥ ≤ ≠), the one style for every shown limit."""
    for op, sign in ((" >= ", " ≥ "), (" <= ", " ≤ "), (" != ", " ≠ "), (" == ", " = ")):
        text = text.replace(op, sign)
    return text


def _unit(measure: str) -> str:
    """The unit the architects would write: ft, sf, or for a count the thing counted (stories, spaces, rooms)."""
    unit = MEASURES.get(measure, {}).get("unit", "")
    return measure.split("_")[-1] if unit == "count" else "use" if unit == "text" else unit


def _value(node, values, kinds):
    """The value of a sub-expression for this project, or None when it can't be worked out."""
    try:
        return formula.evaluate(ast.unparse(node), values, kinds)
    except (MissingMeasure, EvaluationError, ArithmeticError, formula.FormulaError):
        return None


def _comparisons(node) -> list | None:
    """The formula as alternatives (or) of conditions (and) of comparisons `measure op expression`, or None
    when it has another shape. Each comparison is (measure, op, expression node)."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        parts = [_comparisons(v) for v in node.values]
        return None if None in parts else [a for p in parts for a in p]
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        parts = [_comparisons(v) for v in node.values]
        if None in parts or any(len(p) != 1 for p in parts):
            return None
        return [[c for p in parts for c in p[0]]]
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.left, ast.Name):
        return [[(node.left.id, node.ops[0], node.comparators[0])]]
    return None


def limit_and_proposed(check: str, values: dict, kinds: dict, use_names: dict) -> tuple[str, str, str]:
    """(table limit, proposed, units) for a rule's check, read off its comparisons for this project."""
    alternatives = _comparisons(formula.parse(check).body)
    if not alternatives:
        return "see formula", "", ""
    subjects = list(dict.fromkeys(m for alt in alternatives for m, _, _ in alt))
    main = alternatives[0][0][0]                       # the measure the requirement is about
    def show(measure, op, expr, named):
        if isinstance(op, (ast.In, ast.NotIn)):
            allowed = [use_names.get(e.value, e.value) for e in expr.elts if isinstance(e, ast.Constant)]
            return ("Permitted: " if isinstance(op, ast.In) else "Not: ") + "; ".join(allowed)
        v = _value(expr, values, kinds)
        shown = _number(v) if v is not None else f"? ({_pretty(ast.unparse(expr))})"
        return f"{measure} {SYMBOL[type(op)]} {shown}" if named else f"{SYMBOL[type(op)]} {shown}"
    named = len(subjects) > 1
    if len(alternatives) == 1 and len(alternatives[0]) == 1 and not isinstance(alternatives[0][0][1], (ast.In, ast.NotIn)):
        m, op, expr = alternatives[0][0]                   # one comparison: limit and proposed as plain numbers
        v, p = _value(expr, values, kinds), values.get(m)
        if type(v) in (int, float) and type(p) in (int, float):
            return f"{SYMBOL[type(op)]} {_number(v)}", p, _unit(m)
    limit = " or ".join("; ".join(show(m, op, e, named or m != main) for m, op, e in alt) for alt in alternatives)
    def proposed(m):
        v = values.get(m)
        if v is None:
            return "not given"
        return use_names.get(v, v) if _unit(m) == "use" and isinstance(v, str) else _number(v)
    shown_subjects = [m for m in subjects if m == main or named]
    prop = proposed(main) if not named else "; ".join(f"{m} = {proposed(m)}" for m in shown_subjects)
    units = {_unit(m) for m in subjects}
    return limit, prop, units.pop() if len(units) == 1 else ""


def table_values(check: str) -> str:
    """The limits a check uses, as written (the right-hand side of each comparison): e.g. for the rear yard
    "max(min(0.25 * lot_depth, 50), 20)": a quarter of the lot depth, at most 50 ft, at least 20 ft."""
    alternatives = _comparisons(formula.parse(check).body)
    if not alternatives:
        return _pretty(check)
    # Each comparison is printed whole by Python's own printer, so brackets stay where the meaning needs them.
    return " or ".join("; ".join(_pretty(ast.unparse(ast.Compare(ast.Name(m), [op], [e]))) for m, op, e in alt)
                       for alt in alternatives)


def _unreadable(node, values: dict, kinds: dict) -> list[str]:
    """Every measure the checker reads on the way it works this formula out, that is missing or unusable.
    The checker reads every part of and/or, comparisons, arithmetic and min/max, but only the branch an
    `a if test else b` takes, so an untaken branch is never blamed (and when the test itself can't be
    worked out, only the test's measures are)."""
    if isinstance(node, ast.IfExp):
        if bad := _unreadable(node.test, values, kinds):
            return bad
        try:
            test = formula.evaluate(ast.unparse(node.test), values, kinds)
        except (EvaluationError, ArithmeticError):
            return []
        if type(test) is not bool:                  # the checker refuses a test that isn't true/false: no branch
            return []
        return _unreadable(node.body if test else node.orelse, values, kinds)
    if isinstance(node, ast.Name):
        try:
            formula.evaluate(node.id, values, kinds)       # the checker's own test of a usable value
            return []
        except MissingMeasure:
            return [node.id]
    children = node.args if isinstance(node, ast.Call) else ast.iter_child_nodes(node)   # min/max aren't measures
    return list(dict.fromkeys(n for child in children for n in _unreadable(child, values, kinds)))


def _problems(text: str, values: dict, kinds: dict) -> list[str]:
    """Why a formula can't be worked out for this project, or [] when the checker works it out: every
    measurement it needs that is missing or unusable (with its value), else the evaluation error."""
    try:
        formula.evaluate(text, values, kinds)
        return []
    except MissingMeasure:
        bad = _unreadable(formula.parse(text).body, values, kinds)
        missing = [n for n in bad if values.get(n) is None]
        unusable = [f"{n} = {values[n]!r}" for n in bad if values.get(n) is not None]
        return ([f"missing measurement: {', '.join(missing)}"] if missing else []) + \
               ([f"unusable value: {', '.join(unusable)}"] if unusable else []) or ["a measurement can't be used"]
    except (EvaluationError, ArithmeticError) as e:
        return [f"can't be worked out ({e})"]


def needs_review_reason(rule: dict, values: dict, kinds: dict) -> str:
    """Why a row needs review, in plain words, found in the same order outcome() decides it: whether the rule
    applies, then a flag, then each review condition, then the check. (The result itself always comes from
    outcome(); this only explains it.)"""
    if rule.get("applies_when") and (p := _problems(rule["applies_when"], values, kinds)):
        return "Can't tell whether this rule applies: " + "; ".join(p) + "."
    if rule.get("kind") == "flag":
        return "A judgment call: a person decides (this rule is a flag)."
    for r in rule.get("review_when") or []:
        if p := _problems(r["when"], values, kinds):
            return f"Can't tell whether {r['when']!r}: " + "; ".join(p) + "."
        if formula.evaluate(r["when"], values, kinds) is True:
            return " ".join(str(r.get("reason", "")).split())
    p = _problems(rule["check"], values, kinds) if rule.get("check") else []
    return ("Can't check: " + "; ".join(p) + ".") if p else "The check can't be worked out with these values."


# ---- the workbook --------------------------------------------------------------------------------------

def tables(project_path: Path) -> dict:
    """The two tabs as plain rows (so tests check content without Excel)."""
    project = load_project(project_path)
    j = REPO / project["jurisdiction"]
    book_path = rulebook_for(j, project["zone"])
    # Only a jurisdiction and rulebook that pass the same checks as `python -m rule_format` give results,
    # so a rule edited and never checked can't give PASS (approval is deferred: code is the last defense). Those
    # checks are made once and frozen (rule_format/published.py: compile, then freeze): the rulebook's certificate,
    # checked against every file it was worked out from, or no report; never a live check to fall back on.
    if book_path is None:
        raise ValueError(f"{project['jurisdiction']}: no rulebook for zone {project['zone']!r}, so no report")
    got = frozen(j, book_path)
    if got["problems"]:
        shown = book_path.relative_to(REPO) if book_path.is_relative_to(REPO) else book_path
        raise ValueError(f"{shown} doesn't pass the rule checks (python -m rule_format) or its frozen copy can't be "
                         "used, so no report: " + "; ".join(got["problems"]))
    book = load_bytes(got["book"])                    # the very bytes the certificate was checked against
    uses_file = j / "4_term_definitions/uses.yaml"
    uses = (load(uses_file) or {}) if uses_file.exists() else {}
    use_names = {k: v.get("name", k) for k, v in uses.items() if isinstance(v, dict)}
    documents = got["documents"]
    values = {k: m["value"] for k, m in project["measurements"].items()}
    allowed = {"use": got["kinds"]["use"]}            # the same list the checker and the tests use
    kinds = MEASURE_KINDS | {k: frozenset(v) for k, v in allowed.items()}
    which = book_path.relative_to(j / "5_zoning_rules").as_posix()
    cite = citer(j, documents)

    inputs = [[k.replace("_", " ").capitalize(), use_names.get(m["value"], m["value"]),
               f"{_unit(k)}; {' '.join(str(MEASURES[k]['meaning']).split())}", str(m["from"])]
              for k, m in project["measurements"].items()]

    rows, links, params, param_links, later = [], [], [], [], []
    for rule in book.get("rules") or []:
        result = outcome(rule, values, allowed)
        sources = rule.get("sources") or [{}]
        first = sources[0]
        link = page_link(j, documents, first.get("file", ""), first.get("page")) if first.get("file") else None
        limit, proposed, units = (limit_and_proposed(rule["check"], values, kinds, use_names) if rule.get("check")
                                  else ("a person decides", "", ""))
        row = [rule.get("title", rule.get("id", "")), limit, proposed, units, COMPARISON[result],
               first.get("page", ""), RESULT[result], rule.get("id", ""), rule.get("check", ""),
               needs_review_reason(rule, values, kinds) if result == "needs_review" else "",
               cite(first), " ".join(str(first.get("quote", "")).split()),
               f"Open p.{first['page']}" if first.get("file") else "",
               f"{which} ({rule.get('drafted_by', '')}, {rule.get('status', '')})"]
        (later if result == "not_applicable" else rows).append((row, link))
        if result != "not_applicable" and rule.get("check"):     # the limit as the table writes it
            params.append([rule.get("title", ""), table_values(rule["check"]),
                           cite(first),
                           rule.get("id", ""), f"Open p.{first['page']}" if first.get("file") else ""])
            param_links.append(link)
    return {"title": project["title"], "use_names": use_names, "inputs": inputs, "parameters": params,
            "rules": book.get("rules") or [], "uses": allowed["use"],      # what the rows were worked out from
            "parameter_links": param_links,
            "output": [r for r, _ in rows], "output_links": [l for _, l in rows],
            "not_applicable": [r for r, _ in later], "not_applicable_links": [l for _, l in later]}


def _mark_ours(ws, top: int, bottom: int, first: int, last: int) -> None:
    """Set our added columns (first..last) apart from the architects': light blue on our headers, and a line
    down the left edge of the first one."""
    edge = Border(left=Side(style="medium", color=INK))
    for c in range(first, last + 1):
        ws.cell(row=top, column=c).fill = PatternFill("solid", fgColor=OURS_FILL)
    for r in range(top, bottom):
        ws.cell(row=r, column=first).border = edge


def _color_results(ws, top: int, bottom: int, column: int) -> None:
    for r in range(top, bottom):
        cell = ws.cell(row=r, column=column)
        if cell.value in RESULT_INK:
            cell.font = Font(name=FONT, size=11, bold=True, color=RESULT_INK[cell.value])


def _note(ws, cell: str, text: str, size=10, bold=False) -> None:
    ws[cell] = text
    ws[cell].font = Font(name=FONT, size=size, bold=bold, italic=not bold, color=INK)


def shown(t: dict, use_names: dict | None = None) -> dict:
    """The tables as an architect reads them (plain.py): titles, not measure names; lengths in feet and inches and
    areas in square feet, rounded never in the design's favour; no file names. The values and verdicts are t's:
    only how they are written changes."""
    col = {h: n for n, h in enumerate(OUTPUT_HEADERS + OUTPUT_EXTRA)}
    names = use_names if use_names is not None else t.get("use_names") or {}

    def row(r):
        unit, lim = r[col["Units"]], r[col["Table limit"]]
        out = [r[col["Requirement"]], plain.limit(lim, unit, names), plain.proposed(r[col["Proposed"]], unit, lim, names),
               r[col["Units"]], r[col["Comparison"]], r[col["PDF page"]], r[col["Error"]],
               plain.names(r[col["Why it needs review"]], names), r[col["Citation"]], r[col["City's exact words"]],
               r[col["Link"]]]
        return out

    inputs = [[i[0], plain.input_value(i[0].lower().replace(" ", "_"), i[1]),
               plain.meaning(i[2]).replace("use; ", "", 1) if i[2].startswith("use; ") else plain.meaning(i[2]),
               plain.source(i[3])] for i in t["inputs"]]
    # the rule as words ("R-1b rear yard"): its id, for the trace tab, without the code's dots and underscores
    params = [[p[0], plain.names(p[1], names), p[2], str(p[3]).replace(".", " ").replace("_", " "), *p[4:]]
              for p in t["parameters"]]
    trace = [[r[col["Requirement"]], r[col["Rule id"]], r[col["Formula"]], r[col["Rulebook"]]]
             for r in t["output"] + t["not_applicable"]]
    return {**t, "inputs": inputs, "parameters": params, "output": [row(r) for r in t["output"]],
            "not_applicable": [row(r) for r in t["not_applicable"]], "trace": trace}


def build(t: dict) -> Workbook:
    """The architects' two tabs, laid out like theirs: title in A1, bold headers on row 2, their columns in
    their order, widths, font and colors (yellow for typed-in values, red for FAIL), in their words (shown): our
    columns come after theirs, set apart by a light blue on the headers (a color their key doesn't use) and a line
    down the left edge. The rule ids, formulas and rulebook, for checking the rules, are on a last tab."""
    t = shown(t)
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = "Gordium (generated: python -m project_report)"
    ws = wb.create_sheet(INPUTS_TAB)
    title(ws, INPUTS_TITLE)
    end = write_block(ws, 2, list(zip(INPUT_HEADERS + INPUT_EXTRA, INPUT_WIDTHS)), t["inputs"],
                      fills={"Value": [INPUT_FILL] * len(t["inputs"])})
    _mark_ours(ws, 2, end, len(INPUT_HEADERS) + 1, len(INPUT_HEADERS + INPUT_EXTRA))
    # Under the inputs, so it keeps their widths (None); only Link, its own fifth column, gets one.
    params_end = write_block(ws, end + 2, [(h, 10 if h == "Link" else None) for h in PARAMETER_HEADERS + PARAMETER_EXTRA],
                             t["parameters"], links={"Link": t["parameter_links"]})
    _mark_ours(ws, end + 2, params_end, len(PARAMETER_HEADERS) + 1, len(PARAMETER_HEADERS + PARAMETER_EXTRA))
    key = len(PARAMETER_HEADERS + PARAMETER_EXTRA) + 2          # a key to the colors, like theirs, to the right
    _note(ws, ws.cell(row=2, column=key).coordinate, "Key", size=12, bold=True)
    ws.cell(row=3, column=key).fill = PatternFill("solid", fgColor=INPUT_FILL)
    _note(ws, ws.cell(row=3, column=key + 1).coordinate, "typed into the project file")
    ws.cell(row=4, column=key).fill = PatternFill("solid", fgColor=OURS_FILL)
    _note(ws, ws.cell(row=4, column=key + 1).coordinate, "where each value comes from, and the city's own words")

    ws = wb.create_sheet(OUTPUT_TAB)
    title(ws, f"GORDIUM | {t['title']} (draft rules, checked by code)")
    first_ours = len(OUTPUT_HEADERS) + 1
    _note(ws, ws.cell(row=1, column=first_ours).coordinate, "Why, and the city's own words")
    columns = list(zip(OUTPUT_HEADERS + OUTPUT_SHOWN, OUTPUT_SHOWN_WIDTHS))
    end = write_block(ws, 2, columns, t["output"], links={"Link": t["output_links"]})
    _mark_ours(ws, 2, end, first_ours, len(columns))
    _color_results(ws, 3, end, OUTPUT_HEADERS.index("Error") + 1)
    if t["not_applicable"]:
        _note(ws, f"A{end + 1}", "Rules in this zone that don't apply to this project", size=12, bold=True)
        later_end = write_block(ws, end + 2, [(h, None) for h, _ in columns], t["not_applicable"],
                                links={"Link": t["not_applicable_links"]})
        _mark_ours(ws, end + 2, later_end, first_ours, len(columns))
    ws.freeze_panes = "A3"

    ws = wb.create_sheet(TRACE_TAB)
    title(ws, "For checking the rules: each requirement's rule, its formula and the rulebook it came from")
    write_block(ws, 2, list(zip(TRACE_HEADERS, [34, 34, 60, 50])), t["trace"])
    return wb


def output_path(project_path: Path) -> Path:
    return project_path.with_name(f"{project_path.stem}_report.xlsx")
