"""What the Rhino panel, the viewport and the report show for one check: the items, their statuses, the summary,
the header, and the notice when an item newly stops complying (docs/design/rhino_ui_spec.md).

Results still come only from the checker's `outcome()` (via check.py). This module can only make a result more
cautious, never less: an item the checker passes needs review when the lot lines are approximate and a 2'-0"
error could make it fail (spec C2), or when the roof isn't flat (C6); nothing that needs review or fails is ever
shown as complying. It also says each value the way an architect reads it (feet and inches, never rounded toward
compliance, C9), names what was measured (C8), quotes the code and cites it the way an examiner does (E1–E4), and
writes one summary used everywhere (D3).
"""

import ast
import functools
import itertools
import math
import re
import urllib.parse
from pathlib import Path

from rule_export.workbook import citer, page_link, sections_lookup
from rule_format import formula
from rule_format.rulebook import MEASURE_KINDS, REPO, load, read_jsonl

from design_checker.rhino_logic import delta_text  # one formatter: the panel, the report, the notice

COMPLIES, FAILS, REVIEW, NOT_CHECKED = "complies", "does_not_comply", "needs_review", "not_checked"
MARK = {FAILS: "✕", REVIEW: "?", COMPLIES: "✓", NOT_CHECKED: "–"}
SETUP_MARK = "⚠"                          # a setup or system problem: never an item status
WORDS = {FAILS: ("does not comply", "do not comply"), REVIEW: ("needs review", "need review"),
         COMPLIES: ("complies", "comply"), NOT_CHECKED: ("not checked", "not checked")}
ORDER = [FAILS, REVIEW, COMPLIES, NOT_CHECKED]
GROUPS = [("fails", "Does not comply"), ("review", "Needs review"), ("complies", "Complies"),
          ("not_checked", "Not checked"), ("not_covered", "Not covered by this rulebook")]

from model_measurement.measure import TAX_MAP_TOLERANCE as TOLERANCE  # noqa: E402  (lot lines from the tax map: right to within this)
LOT_LENGTHS = {"lot_width", "lot_depth", "front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard"}
SITE_MEASURES = {"lot_area", "lot_width", "lot_depth", "use", "district"}
INTERIOR = {"sleeping_rooms", "parking_spaces"}
EIGHTH = 1 / 96                           # 1/8 in, in feet
PRECISION = ("Measured to 1/8 in.; values are never rounded toward compliance; near a limit they are shown with "
             "one more decimal.")
DRAFT = "Draft rulebook · not yet reviewed by a licensed professional"
# the code's own words for each measurement (J5)
NAMES = {"front_yard": "Front yard", "rear_yard": "Rear yard", "side_yard_smaller": "Side yard",
         "side_yard_larger": "Side yard", "building_area": "Lot coverage", "building_height": "Building height",
         "stories": "Stories", "lot_area": "Lot area", "lot_width": "Lot width", "lot_depth": "Lot depth",
         "use": "Use", "parking_spaces": "Parking", "sleeping_rooms": "Parking"}
ZOOM = {"building_height": "front", "stories": "front"}
SIGNS = {ast.GtE: "≥", ast.Gt: ">", ast.LtE: "≤", ast.Lt: "<", ast.Eq: "=", ast.NotEq: "≠"}
ROOF_NOT_FLAT = "Roof not flat; this roof's height rule isn't checked in this release"


# ---- numbers as an architect reads them -----------------------------------------------------------------

def _eighths(feet: float, direction: str) -> int:
    x = feet / EIGHTH
    if abs(x - round(x)) < 1e-6:
        return int(round(x))
    return math.floor(x) if direction == "down" else math.ceil(x) if direction == "up" else int(round(x))


def feet_inches(feet: float, direction: str = "nearest") -> str:
    """25'-0", 22'-6", 30'-10 7/8": to 1/8 in, rounded in `direction` (down, up or nearest)."""
    n = _eighths(abs(feet), direction if feet >= 0 else {"down": "up", "up": "down"}.get(direction, direction))
    ft, rest = divmod(n, 96)
    inch, eighth = divmod(rest, 8)
    frac = ""
    if eighth:
        g = math.gcd(eighth, 8)
        frac = f" {eighth // g}/{8 // g}"
    return ("-" if feet < 0 and n else "") + f"{ft}'-{inch}{frac}\""


def _area(sf: float, direction: str) -> str:
    v = math.floor(sf) if direction == "down" else math.ceil(sf) if direction == "up" else round(sf)
    return f"{v:,} sf"


def _pct(x: float, direction: str, places: int) -> str:
    k = 10 ** places
    v = math.floor(x * k + 1e-9) / k if direction == "down" else math.ceil(x * k - 1e-9) / k if direction == "up" else round(x, places)
    return f"{v:.{places}f}".rstrip("0").rstrip(".") + "%"


def _toward(sign: str, for_proposed: bool) -> str:
    """Rounding that never favors compliance: a value that must be at least something rounds down, at most up;
    the required value the other way (stricter)."""
    at_least = sign in ("≥", ">")
    if for_proposed:
        return "down" if at_least else "up"
    return "up" if at_least else "down"


def value_text(value, unit: str, sign: str = "", for_proposed: bool = True) -> str:
    if value is None:
        return "—"
    if unit == "ft":
        return feet_inches(value, _toward(sign, for_proposed) if sign else "nearest")
    if unit == "sf":
        return _area(value, _toward(sign, for_proposed) if sign else "nearest")
    if unit == "count":
        return str(int(value)) if float(value).is_integer() else str(value)
    return str(value)


def margin_text(margin: float, unit: str) -> str:
    """+11'-7", −2'-6", at limit: a margin is never overstated (a positive one rounds down, a shortfall up). A
    shortfall is never "at limit": however small, it shows as at least the smallest step (−0'-0 1/8", −1 sf)."""
    if margin < 0 and unit in ("ft", "sf", "%"):
        least = {"ft": EIGHTH, "sf": 1.0, "%": 0.01}[unit]
        gap = max(-margin, least)
        return "−" + (feet_inches(gap, "up") if unit == "ft" else _area(gap, "up") if unit == "sf" else _pct(gap, "up", 2))
    if unit == "ft":
        if abs(margin) < EIGHTH / 2:
            return "at limit"
        return ("+" if margin > 0 else "−") + feet_inches(abs(margin), "down" if margin > 0 else "up")
    if unit == "sf":
        if abs(margin) < 0.5:
            return "at limit"
        return ("+" if margin > 0 else "−") + _area(abs(margin), "down" if margin > 0 else "up")
    if unit == "%":
        if abs(margin) < 0.005:
            return "at limit"
        return ("+" if margin > 0 else "−") + _pct(abs(margin), "down" if margin > 0 else "up", 2)
    return ("+" if margin > 0 else "−" if margin < 0 else "") + (f"{abs(margin):g}" if margin else "at limit")


# ---- reading a rule's check ------------------------------------------------------------------------------

def _compares(check: str) -> list[ast.Compare]:
    """Every `measure <op> limit` in a check, in reading order."""
    out = [n for n in ast.walk(formula.parse(check).body)
           if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.left, ast.Name)
           and type(n.ops[0]) in SIGNS]
    return sorted(out, key=lambda n: (n.lineno, n.col_offset))


def _evaluate(text: str, values: dict):
    try:
        return formula.evaluate(text, values, MEASURE_KINDS)
    except (formula.EvaluationError, formula.MissingMeasure, ArithmeticError):
        return None


def _plain_rhs(node, values: dict, measured: dict) -> str:
    """The limit with each measurement's value written in: max(min(25% × lot depth 90'-0", 50'-0"), 20'-0")."""

    class Show(ast.NodeTransformer):
        def visit_Name(self, n):
            if n.id not in measured:            # a function (min, max), not a measurement
                return n
            m = measured.get(n.id) or {}
            shown = value_text(values.get(n.id), m.get("unit") or "")
            return ast.Name(id=f"{n.id.replace('_', ' ')} {shown}")

    text = ast.unparse(Show().visit(ast.parse(ast.unparse(node), mode="eval")))
    text = re.sub(r"\b0\.(\d+) \* ", lambda m: f"{int(m.group(1)) * 10 ** (2 - len(m.group(1)))}% × ", text)
    return text.replace(" * ", " × ")


# ---- citations (E2, E3) ----------------------------------------------------------------------------------

def _documents(j: Path) -> dict:
    return {d["file"]: d for d in load(j / "1_source_documents/sources.yaml")["documents"]}


def _is_chart(source: dict, documents: dict) -> bool:
    return "chart" in (documents.get(source.get("file")) or {}).get("title", "").lower()


def _footnotes(text: str) -> list[str]:
    return re.findall(r"\[fn(\d+)\]", text) + re.findall(r"^\((\d+)\)", text)


# a chart row in the code's words, by how the chart's row label begins: the same row is cited the same way
# whichever rule cites it
CHART_ROWS = [("Front (minimum)", "Front yard"), ("Side (one side", "Side yard, one side"),
              ("Side (other side", "Side yard, other side"), ("Rear (minimum", "Rear yard"),
              ("Height in feet", "Building height"), ("Maximum Building Height", "Building height"),
              ("Number of stories", "Stories"), ("Percent of lot area", "Lot coverage")]


def _chart_row(text: str) -> str | None:
    for start, name in CHART_ROWS:
        if text.startswith(start):
            return name
    return None


def citation(source: dict, item_name: str, district: str, section_of, documents: dict) -> str:
    """As an examiner writes it: "§325-8, District Regulations Chart, R-1b, Rear yard column, note 16" for the
    chart (a footnote line: "…, note 16"); "§325-8A, p.25" for the law."""
    if _is_chart(source, documents):
        quote = " ".join(str(source.get("quote", "")).split())
        if re.match(r"^\(\d+\)", quote):                  # the footnote itself, at the bottom of the page
            return ", ".join(["§325-8", "District Regulations Chart", district] +
                             [f"note {n}" for n in _footnotes(quote)])
        row = _chart_row((source.get("cell") or {}).get("row") or quote) or item_name
        return ", ".join(["§325-8", "District Regulations Chart", district, f"{row} column"])
    lines = source.get("lines") or [None]
    where = section_of(source.get("file"), source.get("page"), lines[0]) if lines[0] else ""
    return ", ".join(p for p in [where.split(" (")[0] if where else "", f"p.{source.get('page')}"] if p)


def combined(citations: list[str]) -> str:
    """One item's citations, as one line: a footnote cited with its row reads "…, Rear yard column, note 16"."""
    notes = [c.rsplit(", ", 1)[1] for c in citations if re.search(r", note \d+$", c) and "column" not in c]
    rest = [c for c in citations if not (re.search(r", note \d+$", c) and "column" not in c)]
    for k, c in enumerate(rest):
        if c.endswith(" column") and notes:
            rest[k] = c + ", " + ", ".join(notes)
            notes = []
            break
    return "; ".join(dict.fromkeys(rest + [f"District Regulations Chart, {n}" for n in notes]))


def link(source: dict, j: Path, documents: dict) -> str:
    """The page, plus the first words of the quote to find on it, so two sections never share a link."""
    words = " ".join(str(source.get("quote") or (source.get("cell") or {}).get("row") or "").split()[:5])
    base = page_link(j, documents, source["file"], source.get("page"))
    return base + ("&search=" + urllib.parse.quote(f'"{words}"') if words else "")


# ---- the item for one rule -------------------------------------------------------------------------------

def _user_text(text: str) -> str:
    """The measuring's own words for a reader of the panel: no internal phrasing (C11), no measure tags."""
    text = re.sub(r"\s*\(([a-z_]+)\)", "", text or "")
    text = re.sub(r"(is|are) (an )?open questions? for the architects",
                  lambda m: ("aren't" if m.group(1) == "are" else "isn't") + " settled yet: confirm with the zoning office",
                  text)
    text = text.replace("(an open question for the architects)", "(confirm with the zoning office)")
    text = text.replace("an open question for the architects", "not settled yet: confirm with the zoning office")
    return text


def _status(row: dict) -> str:
    if row.get("Fails") or row.get("Error") == "FAIL":
        return FAILS
    return COMPLIES if row.get("Error") == "PASS" else REVIEW


def _reason(row: dict) -> str | None:
    if _status(row) != REVIEW:
        return None
    if row.get("Provisional") and "confirm the survey" in row["Provisional"]:
        word = "Complies" if row["Provisional"].startswith("passes") else "Does not comply"
        return f"{word} with the lot as drawn; the lot lines aren't from a survey · Pick survey lot lines…"
    if row.get("Provisional"):
        return _user_text(("Complies " if row["Provisional"].startswith("passes") else "Fails ") +
                          row["Provisional"].split(" ", 1)[1] + " the law allows; confirm with the zoning office")
    return _user_text(row.get("Why") or "")


def _hint(name: str, sign: str, margin: float, unit: str) -> str | None:
    if margin is None or margin >= 0:
        return None
    gap = _gap(margin, unit)                  # rounded up: a fix never falls short
    if name.split(",")[0].endswith("yard"):          # "Side yard, East" too
        return f"To comply: move the building {gap} farther from that lot line."
    if name == "Building height":
        return f"To comply: lower the building {gap}."
    if name == "Lot coverage":
        return f"To comply: reduce the footprint by {gap}."
    return f"To comply: {'increase' if sign in ('≥', '>') else 'reduce'} it by {gap}."


def _alternatives(check: str, values: dict, measured: dict) -> list[list[tuple]]:
    """For a rule that allows several ways to comply (`a or b and c …`), each way's failing comparisons as
    (name, proposed, sign, required, gap): what the architect could change. [] if the rule has one way."""
    body = formula.parse(check).body
    if not (isinstance(body, ast.BoolOp) and isinstance(body.op, ast.Or)):
        return []
    out = []
    for alt in body.values:
        failing = []
        for c in ([alt] if isinstance(alt, ast.Compare) else
                  [v for v in getattr(alt, "values", []) if isinstance(v, ast.Compare)]):
            if not (len(c.ops) == 1 and isinstance(c.left, ast.Name) and type(c.ops[0]) in SIGNS):
                continue
            if _evaluate(ast.unparse(c), values) is False:
                proposed, required, margin, unit, sign = _numbers(c, values, measured, "")
                failing.append((NAMES.get(c.left.id, c.left.id.replace("_", " ")), value_text(proposed, unit, sign),
                                sign, value_text(required, unit, sign, False),
                                _gap(margin, unit) if margin is not None else ""))
        out.append(failing)
    return out


def _range(measure: str, measured: dict, values: dict, sign: str) -> str | None:
    """The span of a measurement's readings when they disagree ("12'-0" to 15'-0""), each end rounded the
    cautious way; coverage as a share of the lot."""
    readings = [r["value"] for r in (measured.get(measure) or {}).get("readings") or [] if r.get("value") is not None]
    if len(set(readings)) < 2:
        return None
    lo, hi = min(readings), max(readings)
    if measure == "building_area" and values.get("lot_area"):
        lot = values["lot_area"]
        return f"{_pct(lo / lot * 100, 'up', 1)} to {_pct(hi / lot * 100, 'up', 1)}"
    unit = (measured.get(measure) or {}).get("unit") or ""
    return f"{value_text(lo, unit, sign)} to {value_text(hi, unit, sign)}"


SURVEY_ONLY = "passes with the lot as drawn (confirm the survey)"     # check.every_reading's words


def _gap(margin: float, unit: str) -> str:
    """How much to change to comply, rounded UP (a fix that falls short by 1/8 in. is no fix)."""
    gap = abs(margin)
    if unit == "ft":
        return feet_inches(gap, "up")
    if unit == "sf":
        return _area(gap, "up")
    if unit == "%":
        return _pct(gap, "up", 2)
    return f"{math.ceil(gap - 1e-9):g}"


def _fix(name, proposed, sign, required, gap) -> str:
    """One way to comply, in an architect's words. A yard is made deeper keeping the others: moving the whole
    building would take the room from another yard, which may need it too (the height bonus raises them all)."""
    if name.endswith("yard"):
        return f"make the {name.lower()} {gap} deeper, keeping the other yards"
    if name == "Building height":
        return f"lower the building {gap}"
    return f"{'increase' if sign in ('≥', '>') else 'reduce'} {name.lower()} by {gap}"


def _holding_way(check: str, values: dict) -> list | None:
    """For a rule with several ways to comply (`a or b and c …`) that holds by a way other than the first, that
    way's comparisons; else None."""
    body = formula.parse(check).body
    if not (isinstance(body, ast.BoolOp) and isinstance(body.op, ast.Or)):
        return None
    for k, alt in enumerate(body.values):
        if _evaluate(ast.unparse(alt), values) is True:
            if k == 0:
                return None
            return [c for c in ([alt] if isinstance(alt, ast.Compare) else getattr(alt, "values", []))
                    if isinstance(c, ast.Compare) and len(c.ops) == 1 and isinstance(c.left, ast.Name)
                    and type(c.ops[0]) in SIGNS]
    return None


def _worst_reading(node, measured: dict, values: dict):
    """(worst reading, required) as text when the comparison fails under one of the measurement's readings."""
    m = node.left.id
    readings = [r["value"] for r in (measured.get(m) or {}).get("readings") or [] if r.get("value") is not None]
    sign = SIGNS[type(node.ops[0])]
    if not readings:
        return None
    worst = min(readings) if sign in ("≥", ">") else max(readings)
    trial = dict(values, **{m: worst})
    if _evaluate(ast.unparse(node), trial) is not False:
        return None
    shown = _display(*_numbers(node, trial, measured, ""))
    return shown[0], shown[1]


def _numbers(node, values: dict, measured: dict, name: str):
    """(proposed, required, margin, unit, sign) for one comparison; coverage as a percentage of lot area."""
    m = node.left.id
    sign = SIGNS[type(node.ops[0])]
    unit = (measured.get(m) or {}).get("unit") or ""
    proposed, required = values.get(m), _evaluate(ast.unparse(node.comparators[0]), values)
    if m == "building_area" and isinstance(required, (int, float)) and proposed is not None and values.get("lot_area"):
        lot = values["lot_area"]
        return proposed / lot * 100, required / lot * 100, None, "%", sign
    if not isinstance(proposed, (int, float)) or not isinstance(required, (int, float)):
        return proposed, required, None, unit, sign
    margin = proposed - required if sign in ("≥", ">") else required - proposed
    return proposed, required, margin, unit, sign


def _display(proposed, required, margin, unit, sign):
    if unit == "%":
        margin = (required - proposed) if sign in ("≤", "<") else (proposed - required)
        places = 2 if abs(margin) < 0.5 else 1
        return (_pct(proposed, _toward(sign, True), places), _pct(required, _toward(sign, False), places),
                margin_text(margin, "%"), margin)
    return (value_text(proposed, unit, sign, True), value_text(required, unit, sign, False),
            margin_text(margin, unit) if margin is not None else "", margin)


def _worst_case(expr: str, values: dict, names: set) -> dict | None:
    """The values that make `expr` false when each lot length is off by up to TOLERANCE, or None if it holds
    for every combination (2 ** n combinations, n ≤ 6)."""
    lengths = sorted(n for n in names & LOT_LENGTHS if isinstance(values.get(n), (int, float)))
    for signs in itertools.product((-1, 1), repeat=len(lengths)):
        trial = dict(values, **{n: values[n] + s * TOLERANCE for n, s in zip(lengths, signs)})
        if _evaluate(expr, trial) is not True:
            return trial
    return None


YARD_MEASURES = ("front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard")
COLOURS_NOTE = ("In the model: red is the part over the yard line even if the tax map's lot line is "
                f"{feet_inches(TOLERANCE)} out (certain); amber is the part that depends on where a survey puts the line.")


def colours_note(measure: str | None, status: str, measured: dict) -> str | None:
    """What the red and amber in the model mean for this yard, when its lot lines are from the tax map and it
    fails or needs review (the "?" legend says it too); otherwise nothing."""
    tax = bool((measured.get("lot_area") or {}).get("tolerance"))
    return COLOURS_NOTE if tax and measure in YARD_MEASURES and status in (FAILS, REVIEW) else None


def _scope(extras: dict, measured: dict) -> str:
    s = extras.get("scope") or {}
    area = (measured.get("building_area") or {})
    footprint = area.get("value")
    if footprint is None and area.get("readings"):
        footprint = max(r["value"] for r in area["readings"])
    parts = []
    if s.get("solids") is not None:
        parts.append((f"{s['groups']} group, " if s.get("groups") else "") + f"{s['solids']} solid" +
                     ("s" if s["solids"] != 1 else "") + (f" on {s['layer']}" if s.get("layer") else ""))
    if footprint is not None:
        parts.append(f"footprint {_area(footprint, 'up')}")
    return "Measured: " + " · ".join(parts) if parts else ""


def _calc(node, values, measured, required) -> str | None:
    """How the required value was worked out, when it isn't just a number from the chart."""
    if node is None or required in ("—", None) or isinstance(node.comparators[0], ast.Constant):
        return None
    if node.left.id == "building_area":
        allowed = _evaluate(ast.unparse(node.comparators[0]), values) if values.get("lot_area") else None
        if allowed is None or values.get("building_area") is None:
            return None
        return (f"Allowed: {_plain_rhs(node.comparators[0], values, measured)} = {_area(allowed, 'down')}; "
                f"footprint {_area(values['building_area'], 'up')}")
    return f"Required: {_plain_rhs(node.comparators[0], values, measured)} = {required}"


def _items_for(row, rule, measured, values, facts, extras, cite, documents, j, use_names) -> list[dict]:
    check = rule.get("check")
    compares = _compares(check) if check else []
    names = formula.names(check) if check else set()
    primary = compares[0] if compares else None
    measure = primary.left.id if primary is not None else None
    name = NAMES.get(measure) or row.get("Short") or row.get("Requirement")
    if primary is None and names == {"use"}:          # use in [...]: the use, and whether it's permitted
        name = "Use"
    site = bool(names) and names <= SITE_MEASURES
    status, reason = _status(row), _reason(row)
    splits = [c for c in compares if c.left.id in ("side_yard_smaller", "side_yard_larger")] if measure in (
        "side_yard_smaller", "side_yard_larger") else []
    # two side yards: always in the same order (by name), so equal yards never swap with the model's units
    parts = sorted(((c, _side_name(c.left.id, measured)) for c in splits), key=lambda p: p[1]) \
        if len(splits) == 2 else [(primary, name)]
    district = facts.get("zone") or ""
    sources = rule.get("sources") or []
    quotes = [q for q in (_quote(s, j, documents, district, cite) for s in sources) if q is not None]
    # each source as an examiner cites it, with its own link (named by the rule's item: both side yards cite the
    # same chart rows)
    cited = [(citation(s, name, district, cite.section, documents), link(s, j, documents))
             for s in sources if s.get("file")]
    out = []
    for node, label in parts:
        st, why = status, reason
        expr = ast.unparse(node) if splits else check
        if splits and node is not None and status != REVIEW:      # each side yard on its own comparison
            holds = _evaluate(expr, values)
            st = COMPLIES if holds is True else FAILS if holds is False else REVIEW
        raised = []                 # the rule complies another way it allows (the §325-16C height bonus): its
        if node is not None and st == COMPLIES and not splits and _evaluate(ast.unparse(node), values) is False:
            way = _holding_way(check, values)          # numbers are that way's, and the yards it raises
            if way:
                node = next((c for c in way if c.left.id == node.left.id), node)
                raised = [c for c in way if c.left.id != node.left.id]
        numbers = _numbers(node, values, measured, label) if node is not None else (None, None, None, "", "")
        proposed, required, margin_t, margin = (*_display(*numbers),) if node is not None else ("—", "—", "", None)
        if name == "Use":
            proposed = use_names.get(values.get("use"), values.get("use") or "—")
            required = {COMPLIES: "permitted", FAILS: "not permitted"}.get(st, "—")
        if measure == "building_height" and st != FAILS and (measured.get("building_height") or {}).get("readings"):
            if any("pitched" in r["reading"] or "mansard" in r["reading"] for r in measured["building_height"]["readings"]):
                st, why = REVIEW, ROOF_NOT_FLAT
        if st == COMPLIES and not facts.get("lot_surveyed") and names & LOT_LENGTHS:
            worst = _worst_case(expr, values, names)
            if worst is not None:
                bad = next((c for c in ([node] + raised if raised else _compares(expr))     # the way it uses
                            if _evaluate(ast.unparse(c), worst) is False), node)
                w = _numbers(bad, worst, measured, label)
                what = "" if bad.left.id == node.left.id else NAMES.get(bad.left.id, bad.left.id.replace("_", " ")) + " "
                st = REVIEW
                why = (f"Lot lines are from the tax map (±{feet_inches(TOLERANCE)}): at worst "
                       f"{what}{_display(*w)[0]} against {_display(*w)[1]} · Pick survey lot lines…")
        tol = (measured.get("lot_area") or {}).get("tolerance")
        if st == REVIEW and tol and node is not None and row.get("Provisional") == SURVEY_ONLY:
            # waiting only on the survey: the same worst case as the lot lengths, for the lot area (spec C2)
            ends = [dict(values, lot_area=tol["low"]), dict(values, lot_area=tol["high"])]
            bad = next((v for v in ends if _evaluate(expr, v) is not True), None) or next(
                (w for v in ends for w in [_worst_case(expr, v, names)] if w is not None), None)
            if bad is None:
                st, why = COMPLIES, (f"Complies even at the tax-map worst case (lot area {_area(tol['low'], 'down')})"
                                     " · Pick survey lot lines…")
            else:
                w = _numbers(node, bad, measured, label)
                why = (f"Lot lines are from the tax map (±{feet_inches(TOLERANCE)}): at worst {_display(*w)[0]} "
                       f"against {_display(*w)[1]} · Pick survey lot lines…")
        if st == FAILS and row.get("Provisional") and not row.get("Error") == "FAIL":
            why = ("Does not comply with the lot as drawn; the lot lines aren't from a survey · Pick survey lot lines…"
                   if "confirm the survey" in row["Provisional"] else
                   "Fails under every reading considered (" + _user_text(row["Provisional"]) + ")")
        line = _detail_line(proposed, required, margin_t, numbers[4] if node is not None else "", margin)
        hint = _hint(label, numbers[4], margin, numbers[3]) if node is not None and margin is not None else None
        if node is not None and node.left.id == "building_area" and margin is not None and margin < 0:
            allowed = _evaluate(ast.unparse(node.comparators[0]), values)
            if isinstance(allowed, (int, float)) and values.get("building_area") is not None:
                hint = f"To comply: reduce the footprint by at least {_area(values['building_area'] - allowed, 'up')}."
        if raised and st == FAILS:               # fails anyway: nothing to raise
            raised = []
        if raised and st == COMPLIES:            # (on a tax-map lot the reason stays the tax map: the yards still rise)
            hint, why = None, "Complies using the rule's other way, which needs: " + "; ".join(dict.fromkeys(
                f"{NAMES.get(c.left.id, c.left.id)}{'s' if c.left.id.startswith('side_yard') else ''} "
                f"{SIGNS[type(c.ops[0])]} "
                f"{value_text(_evaluate(ast.unparse(c.comparators[0]), values), (measured.get(c.left.id) or {}).get('unit') or '', SIGNS[type(c.ops[0])], False)}"
                for c in raised))
        as_is = (measured.get(node.left.id) or {}).get("measured_as_is") if node is not None else None
        if as_is is not None and proposed == "—":      # measured, but the result waits (existing ground): the value
            proposed = value_text(as_is, (measured.get(node.left.id) or {}).get("unit") or "", numbers[4])   # with ?
        if node is not None and proposed == "—":        # the readings disagree: show their span, not a dash
            span = _range(node.left.id, measured, values, numbers[4])
            if span:
                proposed = span
                if node.left.id == "building_area" and values.get("lot_area"):    # the limit in the same unit
                    allowed = _evaluate(ast.unparse(node.comparators[0]), values)
                    if isinstance(allowed, (int, float)):
                        required = _pct(allowed / values["lot_area"] * 100, _toward(numbers[4], False), 1)
                worst = _worst_reading(node, measured, values)
                if worst is not None:                   # say the bad one first: "probably fine" it isn't
                    why = (f"At worst {worst[0]} against {worst[1]}: does not comply under that reading. " +
                           (why or ""))
        alts = _alternatives(check, values, measured) if st == FAILS and not why and not splits else []
        if len(alts) > 1 and all(alts):                 # several ways to comply, none met: say each one
            why = "Does not comply either way the rule allows: " + "; or ".join(
                ", ".join(f"{n} {p}, needs {s} {r}" for n, p, s, r, _ in alt) for alt in alts)
            fixes = [_fix(*alt[0]) for alt in alts if len(alt) == 1]
            hint = "To comply: " + ", or ".join(fixes) + "." if fixes else hint
        out.append({
            "id": rule["id"] + ("#" + label.split(", ")[-1].lower() if splits else ""), "rule": rule["id"],
            "name": label, "group": "site" if site else "building", "status": st, "mark": MARK[st],
            "proposed": proposed, "required": required, "margin": margin_t if st != REVIEW or margin_t else "",
            "sign": numbers[4] if node is not None else "", "reason": why, "hint": hint,
            "_raises": list(raised),              # the comparisons themselves (worst cases need them); popped
            "zoom": ZOOM.get(measure, "top"), "measure": node.left.id if node is not None else None,
            "objects": (measured.get(node.left.id) or {}).get("objects", []) if node is not None else [],
            "points": (measured.get(node.left.id) or {}).get("points") if node is not None else None,
            "detail": {
                "line": line,
                "quotes": quotes,
                "citation": combined(list(dict.fromkeys(c for c, _ in cited))),
                "links": list(dict.fromkeys(u for _, u in cited)),
                "cited": [{"citation": c, "link": u} for c, u in dict.fromkeys(cited)],
                "calc": _calc(node, values, measured, required),
                "scope": _scope(extras, measured),
                "precision": PRECISION,
                "at_limit": (f"At the limit: {proposed} exact" if margin_t == "at limit" else None),
                "colours": colours_note(node.left.id if node is not None else None, st, measured),
            }})
        if node is not None and node.left.id == "building_height":
            out[-1]["detail"].update(_height_detail(j, facts, values, node, numbers))
    return out


def _height_detail(j: Path, facts: dict, values: dict, node, numbers) -> dict:
    """E5: what an examiner checks a height by. The city's whole HEIGHT OF BUILDING and GRADE PLANE definitions,
    each spot grade with where it is and its elevation, and the numbers for a section diagram (not to scale) of
    the lot lines, the yards, the grade plane, the building and the limit. Zoom to opens the front elevation."""
    terms = load(j / "4_term_definitions/definitions.yaml") or {}
    definitions = [{"term": terms[k]["term"], "text": " ".join(" ".join(str(s["quote"]).split())
                                                             for s in terms[k].get("sources") or [] if s.get("quote"))}
                   for k in ("height_of_building", "grade_plane") if k in terms]
    spots = [f"({feet_inches(p[0])}, {feet_inches(p[1])}) · elevation {feet_inches(p[2])}"
             for p in facts.get("grade_points") or [] if len(p) >= 3]
    limit = numbers[1] if isinstance(numbers[1], (int, float)) else None
    diagram = {k: values.get(m) for k, m in (("height", "building_height"), ("front", "front_yard"),
                                              ("rear", "rear_yard"), ("depth", "lot_depth"))}
    diagram["limit"] = limit
    diagram["label"] = "Diagram, not to scale"
    rounding = {"height": "up", "limit": "down", "front": "down", "rear": "down"}     # never toward compliance
    diagram["text"] = {k: feet_inches(diagram[k], d) if isinstance(diagram[k], (int, float)) else "—"
                       for k, d in rounding.items()}
    return {"definitions": definitions, "spots": spots, "diagram": diagram,
            "zoom_note": "Zoom to opens the front elevation"}


def _side_name(measure: str, measured: dict) -> str:
    """Side yard, East/West/North/South: the compass direction from the building to the lot line the yard was
    measured to (plan north = +y), so a lot whose street runs north-south gets North and South. Without a
    measured line, or if both point the same way, narrower or wider."""
    def facing(pts):
        if not pts:
            return None
        dx, dy = pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]      # lot-line end minus building end
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:          # a yard of 0: no direction to name it by
            return None
        return ("East" if dx > 0 else "West") if abs(dx) >= abs(dy) else ("North" if dy > 0 else "South")
    a = facing((measured.get("side_yard_smaller") or {}).get("points"))
    b = facing((measured.get("side_yard_larger") or {}).get("points"))
    if a and b and a != b:
        return "Side yard, " + (a if measure == "side_yard_smaller" else b)
    return "Side yard, " + ("narrower" if measure == "side_yard_smaller" else "wider")


@functools.lru_cache(maxsize=8)
def _chart_cells(j: Path) -> tuple:
    """Every chart cell the extraction read (2_extracted_text/*.cells.jsonl): file, page, section, row, column,
    value, lines."""
    out = []
    for f in sorted((j / "2_extracted_text").glob("*.cells.jsonl")):
        rows = read_jsonl(f)                 # the first row names the file; then a page's columns, then each cell
        name = rows[0].get("file") if rows else None
        out += [dict(r, file=name) for r in rows[1:] if "column" in r and "value" in r]
    return tuple(out)


def _quote(source: dict, j: Path, documents: dict, district: str, cite) -> dict | None:
    """The city's words for one source, as the panel shows them (E1, E4). A chart row is quoted as its section and
    row label and the district's own cell ("Minimum Lot Size · One-family dwelling, detached · R-1B: "6,000 sf""),
    never the whole row of every district; the bare row of district names (it only says which column) is left
    out. Law text and footnotes are quoted as they are."""
    text = " ".join(str(source.get("quote", "")).split())
    if _is_chart(source, documents) and not re.match(r"^\(\d+\)", text):
        if text and all(re.fullmatch(r"R-\w+|\[fn\d+\]", w) for w in text.split()):
            return None
        lines = source.get("lines") or []
        cell = next((c for c in _chart_cells(j) if c["file"] == source.get("file") and c["page"] == source.get("page")
                     and c["column"].upper() == district.upper() and lines and lines[0] in (c.get("row_lines") or [])),
                    None)
        if cell is None and source.get("cell"):
            want = source["cell"]
            cell = next((c for c in _chart_cells(j) if c["file"] == source.get("file") and c["page"] == source.get("page")
                         and c["column"].upper() == str(want.get("column", "")).upper()
                         and c["row"].startswith(str(want.get("row", ""))[:20])), None)
        if cell is not None and str(cell.get("value") or "").strip():   # a heading row has no value: its own words
            section = re.sub(r"\s*\[fn[\d,]+\]", "", cell.get("section") or "")
            row = re.sub(r"\s*\[fn[\d,]+\]", "", cell["row"])
            return {"text": f"{section} · {row} · {cell['column']}: {cell['value']}", "where": cite(source)}
    return {"text": text or _cell_words(source), "where": cite(source)}


def _cell_words(source: dict) -> str:
    c = source.get("cell") or {}
    return " · ".join(str(c[k]) for k in ("section", "row", "column") if c.get(k))


def _detail_line(proposed, required, margin_t, sign, margin) -> str:
    if proposed in ("—", None):
        return ""
    if margin is None:
        return f"{proposed} proposed · {required} required"
    if margin_t == "at limit":
        return f"{proposed} proposed {sign} {required} required · at the limit"
    if margin < 0:
        word = "over by" if sign in ("≤", "<") else "short"
        return f"{proposed} proposed, {required} required → {word} {margin_t.lstrip('−')}"
    return f"{proposed} proposed {sign} {required} required · {margin_t}"


# ---- the whole view --------------------------------------------------------------------------------------

def summary(items: list[dict]) -> str:
    """One line, the same everywhere: every item counted (site rows too), bad news first, no zero counts, never
    a check mark: "1 does not comply · 2 need review · 7 comply · 3 not checked"."""
    counted = [i for i in items if i["group"] != "not_covered"]
    parts = []
    for st in ORDER:
        n = sum(1 for i in counted if i["status"] == st)
        if n:
            parts.append(f"{n} {WORDS[st][0 if n == 1 else 1]}")
    return " · ".join(parts) or "nothing checked"


def state(items: list[dict]) -> str:
    counted = [i for i in items if i["group"] != "not_covered"]
    for st in (FAILS, REVIEW):
        if any(i["status"] == st for i in counted):
            return st
    return COMPLIES


BUILDING_MEASURES = ("front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard", "building_height", "stories")


def _raise_yards(items, measured, values, facts):
    """A rule that complies by its other way (the §325-16C height bonus: every yard 1 ft larger per extra foot)
    raises the yards that way names: each yard row that doesn't already fail then shows that larger minimum and
    its true margin, so a "+2'-0"" never invites moving the house onto a yard the bonus needs. Only ever stricter.
    On a tax-map lot the raised comparison gets the same worst case as every other item (C2): every lot length it
    depends on (the yard, and the lot depth the rear minimum is taken from) off by the tolerance."""
    for i in items:
        for c in i.pop("_raises", None) or []:
            m, sign = c.left.id, SIGNS[type(c.ops[0])]
            req, v = _evaluate(ast.unparse(c.comparators[0]), values), values.get(m)
            if not isinstance(req, (int, float)) or not isinstance(v, (int, float)):
                continue
            unit = (measured.get(m) or {}).get("unit") or ""
            margin = v - req if sign in ("≥", ">") else req - v
            expr = ast.unparse(c)
            worst = _worst_case(expr, values, formula.names(expr)) if not facts.get("lot_surveyed") else None
            for t in items:
                if t is i or t.get("measure") != m or t["status"] == FAILS:
                    continue
                t["required"], t["margin"], t["hint"] = value_text(req, unit, sign, False), margin_text(margin, unit), None
                if worst is not None:                    # the raised minimum fails at the tax-map worst case
                    w = _display(*_numbers(c, worst, measured, t["name"]))
                    t.update(status=REVIEW, mark=MARK[REVIEW], reason=(
                        f"Lot lines are from the tax map (±{feet_inches(TOLERANCE)}): at worst {w[0]} against "
                        f"{w[1]}, the minimum {i['name'].lower()}'s other way needs · Pick survey lot lines…"))
                elif t["status"] == COMPLIES:
                    t["reason"] = (f"At least {t['required']} while {i['name'].lower()} uses the rule's other way, "
                                   "which raises this yard")
                # (a row in review for another reason keeps it, with the raised numbers)
                t["detail"]["line"] = _detail_line(t["proposed"], t["required"], t["margin"], sign, margin)
                t["detail"]["calc"] = f"Required: {t['required']}, raised by {i['name'].lower()}'s other way"
                t["detail"]["at_limit"] = f"At the limit: {t['proposed']} exact" if t["margin"] == "at limit" else None
    for i in items:
        i.pop("_raises", None)


def _cautious_for_left_out(items, left_out, touching):
    """Solids on the lot that aren't measured can change a result that looks like it complies (never a false
    pass): lot coverage counts every building on the lot, principal and accessory (§325-8A), so it needs review
    whenever one is left out; one touching the building may be part of it (a porch or deck counts in the yards,
    §325-18A), so then the yards, height and stories need review too. `touching` is the ids of the left-out solids
    that touch the measured buildings; not given, any of them might."""
    if not left_out:
        return
    n = len(left_out)
    some = f"{n} object{'s' if n != 1 else ''} on the lot {'aren' if n != 1 else 'isn'}'t measured"
    near = list(left_out) if touching is None else [o for o in left_out if o in set(touching)]
    for i in items:
        if i["status"] != COMPLIES:
            continue
        if i.get("measure") == "building_area":
            why = f"Complies for the buildings measured; {some}, and lot coverage counts every building on the lot"
        elif i.get("measure") in BUILDING_MEASURES and near:
            why = (f"Complies for the buildings measured; {len(near)} object{'s' if len(near) != 1 else ''} "
                   "touching the building isn't measured (a porch or deck is part of the building, §325-18A)")
        else:
            continue
        i.update(status=REVIEW, mark=MARK[REVIEW], hint="Add to check…", reason=why + " · Add to check…")


def view(rows, interior, rules_by_id, measured, facts, extras=None, jurisdiction=None) -> dict:
    """Every item, grouped; the summary; the header. `extras` is what the Rhino command adds: what it sent
    (scope), objects on the lot it didn't include, and the grade and lot sources."""
    extras = extras or {}
    j = REPO / (jurisdiction or facts["jurisdiction"])
    documents = _documents(j)
    section_of = sections_lookup(j)
    cite = citer(j, documents)
    cite.section = section_of            # the examiner's citation needs the section alone
    uses_file = j / "4_term_definitions/uses.yaml"
    use_names = {k: v.get("name", k) for k, v in (load(uses_file) or {}).items()
                 if isinstance(v, dict)} if uses_file.exists() else {}
    values = {k: m.get("value") for k, m in measured.items()}
    if values.get("lot_area") is None and (measured.get("lot_area") or {}).get("readings"):
        values = dict(values, lot_area=measured["lot_area"]["readings"][0]["value"])   # the lot as drawn
    items = []
    for row in rows:
        items += _items_for(row, rules_by_id[row["Rule id"]], measured, values, facts, extras, cite, documents, j,
                            use_names)
    left_out = extras.get("not_included") or []
    _raise_yards(items, measured, values, facts)
    _cautious_for_left_out(items, left_out, extras.get("touching"))
    if facts.get("ground_assumed") == "flat":                 # on the rows the ground decides (MVP, Ben 2026-10-20)
        for i in items:
            if i.get("measure") in ("building_height", "stories"):
                i["note"] = "assuming flat ground"
    if left_out:
        n = len(left_out)
        items.append({"id": "scope.not_included", "rule": None, "name": "Objects on the lot not included",
                      "group": "building", "status": REVIEW, "mark": MARK[REVIEW], "proposed": str(n), "required": "0",
                      "margin": "", "sign": "", "zoom": "top", "measure": None, "objects": list(left_out),
                      "points": None, "hint": "Add to check…",
                      "ground_like": [o for o in extras.get("ground_like") or [] if o in left_out],
                      "reason": f"{n} object{'s' if n != 1 else ''} on the lot {'aren' if n != 1 else 'isn'}'t "
                                "measured (not on the Building layer) · Add to check…" + (
                                    f" (" + str(len(extras.get("ground_like") or [])) + " looks like the ground: if it is, "
                                    "This is the ground)" if extras.get("ground_like") else ""),
                      "detail": {"line": "", "quotes": [], "citation": "", "links": [], "calc": None,
                                 "scope": _scope(extras, measured), "precision": PRECISION, "at_limit": None}})
    for row in interior:
        rule = rules_by_id[row["Rule id"]]
        items.append({"id": rule["id"], "rule": rule["id"], "name": "Parking · needs input", "group": "not_checked",
                      "status": NOT_CHECKED, "mark": MARK[NOT_CHECKED], "proposed": "", "required": "", "margin": "",
                      "sign": "", "zoom": None, "measure": None, "objects": [], "points": None,
                      "hint": "Enter bedrooms and parking spaces",
                      "reason": "Needs bedrooms and parking spaces, which the model doesn't show",
                      "detail": {"line": "", "quotes": [{"text": " ".join(str(s.get("quote", "")).split()),
                                                         "where": cite(s)} for s in rule.get("sources") or []],
                                 "citation": "", "links": [], "calc": None, "scope": "", "precision": "",
                                 "at_limit": None}})
    gaps = load(j / "not_checked_yet.yaml") if (j / "not_checked_yet.yaml").exists() else {}
    for g in gaps.get("not_in_this_release") or []:
        items.append({"id": "release." + g["id"], "rule": None,          # short in the list; in full below
                      "name": g["name"].split(" (")[0] + " · not in this release",
                      "group": "not_checked", "status": NOT_CHECKED, "mark": MARK[NOT_CHECKED], "proposed": "",
                      "required": "", "margin": "", "sign": "", "zoom": None, "measure": None, "objects": [],
                      "points": None, "hint": None, "reason": g["name"] + ": " + g["why"],
                      "detail": {"line": "", "quotes": [], "citation": "", "links": [], "calc": None, "scope": "",
                                 "precision": "", "at_limit": None}})
    for g in gaps.get("not_covered") or []:
        items.append({"id": "gap." + g["id"], "rule": None, "name": f"{g['section']} {g['name']}",
                      "group": "not_covered", "status": NOT_CHECKED, "mark": "", "proposed": "", "required": "",
                      "margin": "", "sign": "", "zoom": None, "measure": None, "objects": [], "points": None,
                      "hint": None, "reason": "Not encoded in this rulebook yet: check by hand",
                      "detail": {"line": "", "quotes": [], "citation": g["section"], "links": [], "calc": None,
                                 "scope": "", "precision": "", "at_limit": None}})
    return {"items": items, "summary": summary(items), "state": state(items),
            "header": header(facts, extras, documents, use_names), "groups": grouped(items)}


def grouped(items: list[dict]) -> list[dict]:
    """The panel's groups in order (empty ones left out); site items carry "Site · " in their group label."""
    by = {"fails": [], "review": [], "complies": [], "not_checked": [], "not_covered": []}
    for i in items:
        key = ("not_covered" if i["group"] == "not_covered" else "not_checked" if i["status"] == NOT_CHECKED else
               {FAILS: "fails", REVIEW: "review", COMPLIES: "complies"}[i["status"]])
        by[key].append(i["id"])
    return [{"key": k, "title": t, "items": by[k]} for k, t in GROUPS if by[k]]


def grade_label(facts: dict) -> str:
    """Where the grade comes from, in words: "6 spot grades (finished)", "terrain (finished)", "flat at
    elevation 0'-0"", or "not set"."""
    kind = "existing" if facts.get("grade_is") == "existing" else "finished"
    if facts.get("ground_assumed") == "flat":                 # the MVP's assumption, said wherever the grade is
        return f"flat at the lot level, assumed (finished, elevation {feet_inches(facts.get('grade_elevation') or 0)})"
    points = facts.get("grade_points") or []
    if points:
        source = "terrain" if facts.get("grade_from") == "terrain" else f"{len(points)} spot grades"
        return f"{source} ({kind})"
    if facts.get("ground_is_flat") and facts.get("grade_elevation") is not None:          # (flat: say which kind)
        return f"flat at elevation {feet_inches(facts['grade_elevation'])}" + (" (existing)" if kind == "existing" else "")
    return "not set"


def header(facts: dict, extras: dict, documents: dict, use_names: dict) -> dict:
    law = next((d for d in documents.values() if "chapter 325" in d.get("title", "").lower()), {})
    chart = next((d for d in documents.values() if "chart" in d.get("title", "").lower()), {})
    through = re.search(r"amendments through (Ord\. No\. [\w-]+(?: \([^)]*\))?)", " ".join(str(law.get("notes", "")).split()))
    code = "Ch. 325" + (f" as amended through {through.group(1)}" if through else "") + (
        " · District Regulations Chart, " + re.sub(r".*\((.*)\).*", r"\1", chart["title"]) if chart else "")
    use = facts.get("use") or ""
    lot = ("Lot lines: survey" if facts.get("lot_surveyed") else
           f"Lot lines: tax map, approximate (±{feet_inches(TOLERANCE)})")
    grade = "Grade: " + grade_label(facts)
    actions = (["Pick survey lot lines…"] if not facts.get("lot_surveyed") else []) + (
        ["Set grade…"] if grade_label(facts) == "not set" or facts.get("grade_is") == "existing" else [])
    return {"place": " · ".join(p for p in [facts.get("address") or "", facts.get("zone") or "",
                                            use_names.get(use, use.replace("_", " "))] if p),
            "code": code, "draft": DRAFT, "lot": lot, "grade": grade, "actions": actions,
            "sources": source_lines(extras.get("sources") or {})}


SOURCE_NAMES = {"address": "Address", "zone": "Zoning district", "use": "Use", "lot": "Lot", "street": "Street side",
                "corner_lot": "Corner lot", "ground_marked": "Marked as the ground", "starting_house": "Starting house",
                "ground": "Ground"}


def source_lines(sources: dict) -> list[str]:
    """Each site fact with where it came from, as the panel and the report show it: "Zoning district: R-1b ·
    entered by you · confirmed by you, 2026-10-20". The checker never reads these: only the facts' values."""
    out = []
    for key, name in SOURCE_NAMES.items():
        s = sources.get(key)
        if not s or s.get("value") in (None, ""):
            continue
        who = f"confirmed by {s['confirmed_by']}, {s.get('date')}" if s.get("confirmed_by") else "not confirmed"
        out.append(f"{name}: {s['value']} · {s.get('source') or 'not known'} · {who}")
    return out


def notice(before: dict | None, items: list[dict]) -> tuple[dict, str | None]:
    """(statuses now, the notice): one line for the items that don't comply now and did at the last check
    ("Rear yard no longer complies · 20'-0" proposed · 22'-6" required · −2'-6" short", Delta in the panel's
    words), several merged ("2 items no
    longer comply: Rear yard; Lot coverage"). None on the first check or when nothing newly fails."""
    now = {i["id"]: i["status"] for i in items}
    if before is None:
        return now, None
    new = [i for i in items if i["status"] == FAILS and before.get(i["id"]) != FAILS]
    if not new:
        return now, None
    if len(new) == 1:
        i = new[0]
        detail = " · ".join(p for p in [f"{i['proposed']} proposed" if i["proposed"] not in ("", "—") else "",
                                         f"{i['required']} required" if i["required"] not in ("", "—") else "",
                                         delta_text(i["margin"])] if p)
        return now, f"{i['name']} no longer complies" + (" · " + detail if detail else "")
    return now, f"{len(new)} items no longer comply: " + "; ".join(i["name"] for i in new)   # names hold commas
