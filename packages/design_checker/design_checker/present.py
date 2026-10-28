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
import math
import re
import urllib.parse
from pathlib import Path

from rule_export.workbook import citer, page_link, sections_lookup
from rule_format import formula
from rule_format.rulebook import MEASURE_KINDS, REPO, load, outcome, read_jsonl

from design_checker import reading_set, rhino_logic

COMPLIES, FAILS, REVIEW, NOT_CHECKED = "complies", "does_not_comply", "needs_review", "not_checked"
MARK = {FAILS: "✕", REVIEW: "?", COMPLIES: "✓", NOT_CHECKED: "–"}
SETUP_MARK = "⚠"                          # a setup or system problem: never an item status
WORDS = {FAILS: ("does not comply", "do not comply"), REVIEW: ("needs review", "need review"),
         COMPLIES: ("complies", "comply"), NOT_CHECKED: ("not checked", "not checked")}
ORDER = [FAILS, REVIEW, COMPLIES, NOT_CHECKED]
# the rules not in the rulebook yet (Ben, 2026-10-21): the grey group's name, and each row's words, in the panel and
# the report's Check sheet alike
NOT_YET = "Not checked yet"
NOT_YET_WHY = "Not in Gordium yet — coming in a later version. Check this by hand for now: {}"
GROUPS = [("fails", "Does not comply"), ("review", "Needs review"), ("complies", "Complies"),
          ("use_details", rhino_logic.USE_DETAILS_TITLE), ("not_checked", "Not checked"), ("not_covered", NOT_YET)]

from model_measurement.project import fact_conflict_rows  # noqa: E402  (lot facts that disagree: shown)
from model_measurement.measure import TAX_MAP_TOLERANCE as TOLERANCE  # noqa: E402  (lot lines from the tax map: right to within this)
LOT_LENGTHS = reading_set.LOT_LENGTHS
SITE_MEASURES = {"lot_area", "lot_width", "lot_depth", "use", "district"}
EIGHTH = 1 / 96                           # 1/8 in, in feet
PRECISION = ("Measured to 1/8 in.; values are never rounded toward compliance; near a limit they are shown with "
             "one more decimal.")
DRAFT = "Draft rulebook · not yet reviewed by a licensed professional"
# the code's own words for each measurement (J5)
NAMES = {"front_yard": "Front yard", "rear_yard": "Rear yard", "side_yard_smaller": "Side yard",
         "side_yard_larger": "Side yard", "building_area": "Lot coverage", "building_height": "Building height",
         "stories": "Stories", "lot_area": "Lot area", "lot_width": "Lot width", "lot_depth": "Lot depth",
         "use": "Use", "parking_spaces": "Parking", "sleeping_rooms": "Parking",
         "front_yard_eaves": "Eaves into front yard", "side_yard_smaller_eaves": "Eaves into side yard",
         "side_yard_larger_eaves": "Eaves into side yard", "rear_yard_eaves": "Eaves into rear yard",
         "accessory_front_yard": "Accessory building", "accessory_side_yard": "Accessory building, side",
         "accessory_rear_yard": "Accessory building, rear", "accessory_buildings": "Accessory building"}
ZOOM = {"building_height": "front", "stories": "front"}
YARD_ROWS = {"front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard", "front_yard_eaves",
             "side_yard_smaller_eaves", "side_yard_larger_eaves", "rear_yard_eaves"}   # the main building's yards
SIGNS = {ast.GtE: "≥", ast.Gt: ">", ast.LtE: "≤", ast.Lt: "<", ast.Eq: "=", ast.NotEq: "≠"}


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


def _rounds_to_nothing(margin: float, unit: str) -> bool:
    """Whether a margin to spare, rounded down to the unit's step as it is shown, is zero (+0'-0", +0 sf, +0%)."""
    if unit == "ft":
        return _eighths(margin, "down") == 0
    if unit == "sf":
        return math.floor(margin + 1e-9) == 0
    if unit == "%":
        return math.floor(margin * 100 + 1e-9) == 0
    return margin == 0


def margin_text(margin: float, unit: str) -> str:
    """+11'-7", −2'-6", at limit: a margin is never overstated (a positive one rounds down, a shortfall up). A
    shortfall is never "at limit": however small, it shows as at least the smallest step (−0'-0 1/8", −1 sf). A
    margin to spare that rounds down to nothing is "at limit", never "+0'-0"" (seen on 106 Ithaca Rd's survey
    house: a side yard 10'-0" and a hair)."""
    if margin < 0 and unit in ("ft", "sf", "%"):
        least = {"ft": EIGHTH, "sf": 1.0, "%": 0.01}[unit]
        gap = max(-margin, least)
        return "−" + (feet_inches(gap, "up") if unit == "ft" else _area(gap, "up") if unit == "sf" else _pct(gap, "up", 2))
    if unit in ("ft", "sf", "%") and _rounds_to_nothing(margin, unit):     # margin >= 0 here
        return "at limit"
    if unit == "ft":
        return "+" + feet_inches(margin, "down")
    if unit == "sf":
        return "+" + _area(margin, "down")
    if unit == "%":
        return "+" + _pct(margin, "down", 2)
    return ("+" if margin > 0 else "−" if margin < 0 else "") + (f"{abs(margin):g}" if margin else "at limit")


# ---- reading a rule's check ------------------------------------------------------------------------------

def _compares(check: str) -> list[ast.Compare]:
    """Every `measure <op> limit` in a check, in reading order."""
    out = [n for n in ast.walk(formula.parse(check).body)
           if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.left, ast.Name)
           and type(n.ops[0]) in SIGNS]
    return sorted(out, key=lambda n: (n.lineno, n.col_offset))


# A "Lot facts disagree" row offers to re-enter the counts that disagree (r2 round 6): project.fact_conflict_rows.


def could_settle(rule: dict, values: dict, key: str) -> bool:
    """Would entering an optional stated fact change this rule's result? Only if the rule's outcome differs between the
    least and the most it can be (the most occupants in one unit: 1 to the occupants). Unknown bounds: no."""
    hi = (values or {}).get(rhino_logic.OPTIONAL.get(key))
    if key not in rhino_logic.OPTIONAL or type(hi) is not int or hi < rhino_logic.minimum(key):
        return False
    use = values.get("use")
    allowed = {"use": {use}} if isinstance(use, str) else {"use": set()}
    known = {k: v for k, v in values.items() if v is not None}
    return outcome(rule, known | {key: rhino_logic.minimum(key)}, allowed) != outcome(rule, known | {key: hi}, allowed)


def _evaluate(text: str, values: dict):
    """A rule's expression at these values. A limit that depends on the use (R-2c's side yards, coverage: "15 if use
    == ...") is worked out for the stated use, as envelope._known_true does; with no use stated it can't be (None)."""
    use = values.get("use")
    kinds = MEASURE_KINDS | ({"use": frozenset([use])} if isinstance(use, str) else {})
    try:
        return formula.evaluate(text, values, kinds)
    except (formula.EvaluationError, formula.MissingMeasure, ArithmeticError):
        return None


def _plain_rhs(node, values: dict, measured: dict) -> str:
    """The limit with each measurement's value written in: max(min(25% × lot depth 90'-0", 50'-0"), 20'-0"). A
    choice the values decide ("6000 if use == ... else 7500" for the stated use, "7000 if conversion else 6000") is
    written as the branch taken; one they don't decide is written whole."""

    class Fold(ast.NodeTransformer):
        def visit_IfExp(self, n):
            self.generic_visit(n)
            taken = _evaluate(ast.unparse(n.test), values)
            return n.body if taken is True else n.orelse if taken is False else n

    class Show(ast.NodeTransformer):
        def visit_Name(self, n):
            if n.id not in measured:            # a function (min, max), not a measurement
                return n
            m = measured.get(n.id) or {}
            shown = value_text(values.get(n.id), m.get("unit") or "")
            return ast.Name(id=f"{n.id.replace('_', ' ')} {shown}")

    text = ast.unparse(Show().visit(Fold().visit(ast.parse(ast.unparse(node), mode="eval"))))
    text = re.sub(r"\b0\.(\d+) \* ", lambda m: f"{int(m.group(1)) * 10 ** (2 - len(m.group(1)))}% × ", text)
    return text.replace(" * ", " × ")


# ---- citations (E2, E3) ----------------------------------------------------------------------------------

def _documents(j: Path) -> dict:
    return {d["file"]: d for d in load(j / "1_source_documents/sources.yaml")["documents"]}


def _is_chart(source: dict, documents: dict) -> bool:
    return "chart" in (documents.get(source.get("file")) or {}).get("title", "").lower()


def _footnotes(text: str) -> list[str]:
    return re.findall(r"\[fn(\d+)\]", text) + re.findall(r"^(?:NOTES:\s*)?\((\d+)\)", text)


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
        # the footnote itself, at the bottom of the page; or a district's column heading carrying one ("RU [fn3]
        # Regulations": its note, one name whichever rule cites it, PR2 review round 6)
        if re.match(r"^(NOTES:\s*)?\(\d+\)", quote) or re.match(r"^\S+ \[fn[\d,]+\] Regulations$", quote):
            return ", ".join(["§325-8", "District Regulations Chart", district] +
                             [f"note {n}" for n in _footnotes(quote)])
        # a row of the use list (chart p.2: a use and its marks, • / SP / - per district) is the Use column whichever
        # rule cites it, so one link has one name; a heading or a note on that page is not (PR2 review round 5)
        uses = (source.get("cell") or {}).get("section") in ("Primary Uses", "Accessory Uses") or (
            source.get("page") == 2 and re.search(r"(?:(?:•|SP|-)(?:\[fn[\d,]+\])?\s+){4,}", quote + " ") is not None)
        row = _chart_row((source.get("cell") or {}).get("row") or quote) or ("Use" if uses else item_name)
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


LINK_WORDS = 5        # the search's least length; longer only where another line on the page begins alike


_LIST_NUMBER = r"\((?:\d+|[a-z]|[ivx]+)\)"


def _searchable(text: str) -> list[str]:
    """The words a PDF viewer's search finds in one run. The PDF stores a footnote marker ([fn4] is a superscript
    digit) and a list number ("(1) ONE-FAMILY DETACHED DWELLING" on chapter 325 p.7, "HOME OCCUPATION — (1) A" on
    p.12) apart from the words around them, so a search across one lands nowhere: leading markers are left out, and
    the search stops before the next one."""
    text = re.sub(r"^(?:\s*(?:\[fn\w*\]|" + _LIST_NUMBER + r"))+", "", text)
    return re.split(r"\[fn|\s" + _LIST_NUMBER + r"(?=\s)", text)[0].split()


def _unique_start(words: list[str], page: list[list[str]]) -> str:
    """The first LINK_WORDS words, more if another line of the page begins with them too ("One-family dwelling,
    detached, zero lot line - -" begins a row of both chart p.3 sections), so the search lands on this one."""
    n = LINK_WORDS
    while n < len(words) and sum(line[:n] == words[:n] for line in page) > 1:
        n += 1
    return " ".join(words[:n])


@functools.lru_cache(maxsize=16)
def _page_lines(j: Path, file: str) -> dict:
    """{(page, line): text} of one document's extracted text (2_extracted_text/<file stem>.jsonl)."""
    path = j / "2_extracted_text" / (Path(file).stem + ".jsonl")
    return {(r["page"], r["line"]): r["text"] for r in (read_jsonl(path) if path.exists() else []) if "line" in r}


def anchor_text(source: dict, j: Path) -> str:
    """The words a source points at on its page: its quote; for a chart cell, its row's own line, the one of the
    cell's row lines that begins with the row label (a label alone, "One-family dwelling, detached", is a row of
    both the lot-size and the lot-width sections of chart p.3; a cell's first row line can be a neighbouring cell's
    wrapped words, which the PDF doesn't hold in that order); else the label."""
    if source.get("quote"):
        return str(source["quote"])
    want = source.get("cell") or {}
    label = " ".join(str(want.get("row") or "").split())
    cell = next((c for c in _chart_cells(j) if c.get("file") == source.get("file") and c.get("page") == source.get("page")
                 and c.get("section") == want.get("section") and " ".join(str(c.get("row", "")).split()) == label), None)
    lines = _page_lines(j, source.get("file") or "")
    own = [lines.get((source.get("page"), n)) or "" for n in (cell or {}).get("row_lines") or []]
    return next((t for t in own if label and " ".join(t.split()).startswith(label)), label)


def link(source: dict, j: Path, documents: dict) -> str:
    """The page, plus the first words of what the source points at on it (anchor_text), so two sections never
    share a link."""
    words = _unique_start(_searchable(anchor_text(source, j)),
                          [_searchable(t) for (pg, _), t in _page_lines(j, source.get("file") or "").items()
                           if pg == source.get("page")])
    base = page_link(j, documents, source["file"], source.get("page"))
    return base + ("&search=" + urllib.parse.quote(f'"{words}"') if words else "")


# ---- the item for one rule -------------------------------------------------------------------------------

def _user_text(text: str) -> str:
    """The measuring's own words for a reader of the panel: no internal phrasing (C11), no question tags (only
    those: "(overhangs)" stays)."""
    text = re.sub(r"\s*\((?:" + "|".join(sorted(QUESTION_TAGS)) + r")\)", "", text or "")
    text = re.sub(r"(is|are) (an )?open questions? for the architects",
                  lambda m: ("aren't" if m.group(1) == "are" else "isn't") + " settled yet: confirm with the zoning office",
                  text)
    text = text.replace("(an open question for the architects)", "(confirm with the zoning office)")
    text = text.replace("an open question for the architects", "not settled yet: confirm with the zoning office")
    return text


RANK = {FAILS: 0, REVIEW: 1, COMPLIES: 2}        # how favourable: the panel never shows a row above the checker


def _status(row: dict) -> str:
    """The checker's verdict for a row (check.row_verdict); for a row without one, its outcome as drawn."""
    if row.get("Verdict"):
        return row["Verdict"]
    if row.get("Fails") or row.get("Error") == "FAIL":
        return FAILS
    if (row.get("Named") or {}).get("result") == "pass":      # complies under every reading research lists
        return COMPLIES
    return COMPLIES if row.get("Error") == "PASS" else REVIEW


def _fails_whatever_part(expr: str, values: dict, unknown: dict) -> bool:
    """One limit of a rule that fails whatever its unknown values are (check.fails_whatever): it fails too, under
    every setting it was proven under (each unknown number in it provably truest at 0)."""
    numbers = [n for n in unknown["names"] if MEASURE_KINDS.get(n) == "number" and n in formula.names(expr)]
    return all(formula.truth_direction(expr, n) == -1 for n in numbers) and all(
        _evaluate(expr, dict(values, **s)) is False for s in unknown["settings"])


def _fails_every_reading(expr: str, values: dict, measured: dict, facts: dict) -> bool:
    """One limit of a rule that fails under every reading of THE reading set (reading_set.combos): a measurement it
    reads that has readings and no value (a pitched roof's height) leaves it unknown as drawn, yet it fails whichever
    reading is taken (#20 review round 1: the eaves rows named the front yard, which passed, for a side eave that
    failed, because every limit holds the height bonus)."""
    names = formula.names(expr)
    if not any(values.get(n) is None and (measured.get(n) or {}).get("readings") for n in names):
        return False
    every = reading_set.combos(names, values, measured, facts)
    return bool(every) and all(_evaluate(expr, trial) is False for trial, _ in every)


FACT_WORDS = {"sleeping_rooms": "bedrooms", "parking_spaces": "parking spaces"}   # interior facts, as asked


def _and(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1] if words else ""


def _holds(expr: str, values: dict, row: dict):
    """True / False / None for a comparison, and under every reading research lists for a row decided that way
    (check.named_result): True only if it holds under all of them, False only if under none."""
    combos = (row.get("Named") or {}).get("combos")
    if not combos:
        return _evaluate(expr, values)
    got = {_evaluate(expr, c) for c in combos}
    return True if got == {True} else False if got == {False} else None


from model_measurement import measure as _measuring  # noqa: E402  (its open questions, by name)

# Every open question the measuring asks, each with a short name for the panel: by its tag ("(lot_depth)"), or by
# its own words where it has none. A test checks that every question the measuring can ask is here.
QUESTION_NAMES = {
    "lot_depth": "which lot lines count as side and which as rear",
    "height_of_building": "how the height of a pitched roof is taken",
    "yard_projections": "whether a yard is measured to the wall or to overhangs, and what counts as part of the "
                        "building",
    "building_area": "whether parts above the ground floor that stick out count in coverage",
    "lot_width": "whether frontage on a curved street is measured along the curve or straight across",
    "story": "how many stories the blocks drawn hold",
    _measuring.ROOF_KIND: "whether the roof is a mansard roof or a pitched one",
    _measuring.ABOVE_ROOF: "whether what rises above the main roof counts in the height",
    _measuring.ACCESSORY: "whether another solid is part of the building or an accessory building",
    "main_building": "which building is the main building (the starting house is assumed, not picked)",
}
QUESTION_TAGS = {k for k in QUESTION_NAMES if re.fullmatch(r"[a-z_]+", k)}


def question_name(question: str) -> str | None:
    """The short name of one open question the measuring asked (its tag's, or its own words'), or None."""
    tag = re.search(r"\(([a-z_]+)\)\s*$", question)
    return QUESTION_NAMES.get(tag.group(1) if tag else "") or QUESTION_NAMES.get(question.strip())


def _questions_of(record: dict) -> list[str]:
    """The open questions one measurement's own readings leave, by short name."""
    reason = (record or {}).get("reason") or ""
    if not reason.startswith("the readings give different values; "):
        return []
    labels = " ".join(r.get("reading") or "" for r in record.get("readings") or [])
    out = []
    for q in reason.split("; ")[1:]:
        if q.rstrip().endswith("(lot_depth)") and "lot line" not in labels:
            continue                        # its readings don't differ in which lines are side lines
        name = question_name(q) or _user_text(q)
        if name and name not in out:
            out.append(name)
    return out


def _depends(row: dict, status: str, measured: dict) -> str | None:
    """For a row (or one side yard: its own fields) that needs review and gives one answer under every reading:
    the open questions its result turns on (the checker's: check.turns_on, which also decided the status, so a
    result turning on none is simply the answer), each by its measurement's own short name; else None."""
    if not (row.get("Provisional") and not row.get("Survey") and status == REVIEW and row.get("Turns on")):
        return None
    asked = list(dict.fromkeys(q for n in row["Turns on"] for q in _questions_of(measured.get(n))))
    if not asked:
        return None
    word = "Complies" if row["Provisional"].startswith("passes") else "Does not comply"
    which = "an open question" if len(asked) == 1 else "open questions"
    return f"{word} under every reading, but it depends on {which}: {'; '.join(asked)}; confirm with the zoning office"


def _reason(row: dict) -> str | None:
    named = row.get("Named")
    if named and _status(row) == COMPLIES:
        return _user_text(named["text"][:1].upper() + named["text"][1:])
    if _status(row) != REVIEW:
        return None
    if named:
        return _user_text("Needs review: " + named["text"] + " · confirm with the zoning office")
    if row.get("Provisional") and "confirm the survey" in row["Provisional"]:
        word = "Complies" if row["Provisional"].startswith("passes") else "Does not comply"
        return f"{word} with the lot as drawn; the lot lines aren't from a survey · Pick survey lot lines…"
    if row.get("Provisional"):
        return _user_text(("Complies " if row["Provisional"].startswith("passes") else "Fails ") +
                          row["Provisional"].split(" ", 1)[1] + " the law allows; confirm with the zoning office")
    return _user_text(row.get("Why") or "")


def _bonus_waits(status: str, across_readings: bool) -> str:
    """How a row whose limit waits on the §325-16C height bonus begins, from its status (review round 12): it
    fails at every height reading, or even before the bonus (the base requirement is the least it can be), or it
    needs review. Never a status word the row doesn't have."""
    if status == FAILS:
        return ("Does not comply at any of the height's readings" if across_readings else
                "Does not comply even before the §325-16C height bonus")
    return "Needs review"


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


def _alternatives(check: str, values: dict, measured: dict, facts: dict | None = None) -> list[list[tuple]]:
    """For a rule that allows several ways to comply (`a or b and c …`), each way's failing comparisons as
    (name, proposed, sign, required, gap, moved, drawn): what the architect could change. [] if the rule has one way. With
    `facts`, a comparison fails if it does under any reading of THE reading set and its gap is the worst one's,
    with the as-drawn gap after it when that differs ("9'-7 3/4" (7'-7 3/4" as drawn)"): doing it makes that way
    hold under every reading, never leaves it in review (the architect's review, pass 2); `moved`: it differs;
    `drawn`: it fails as drawn (what the reason lists)."""
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
            rs = readings(c, ast.unparse(c), values, measured, facts) if facts is not None else []
            worst = min((r["margin"] for r in rs), default=None)
            drawn = _evaluate(ast.unparse(c), values) is False
            if drawn or (worst is not None and worst < 0):
                proposed, required, margin, unit, sign = _numbers(c, values, measured, "")
                gap = _gap(margin, unit) if margin is not None else ""
                moved = worst is not None and margin is not None and _gap(min(worst, margin), unit) != gap
                if moved:
                    gap = _gap(min(worst, margin), unit) + (f" ({gap} as drawn)" if margin < 0 else "")
                need = -min(worst if worst is not None else margin, margin) if margin is not None else None
                change = {c.left.id: _step(need, unit) * (1 if sign in ("≥", ">") else -1)} if need else {}
                failing.append((NAMES.get(c.left.id, c.left.id.replace("_", " ")), value_text(proposed, unit, sign),
                                sign, value_text(required, unit, sign, False), gap, moved, drawn, change))
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


def _raisers(items: list[dict], values: dict) -> dict:
    """measure -> [(comparison, item)]: for each rule with several ways to comply whose first way the design
    doesn't meet as drawn (the §325-16C height bonus: over 35'-0" only with every yard 1 ft larger per foot), the
    comparisons its other ways put on that measure: a yard it would raise."""
    out = {}
    for i in items:
        expr = i.get("_expr")
        body = ast.parse(expr, mode="eval").body if expr else None
        if not (isinstance(body, ast.BoolOp) and isinstance(body.op, ast.Or)):
            continue
        if _evaluate(ast.unparse(body.values[0]), values) is not False:
            continue
        for alt in body.values[1:]:
            comps = [c for c in ([alt] if isinstance(alt, ast.Compare) else getattr(alt, "values", []))
                     if isinstance(c, ast.Compare) and len(c.ops) == 1 and isinstance(c.left, ast.Name)
                     and type(c.ops[0]) in SIGNS]
            # a way the building can't take as drawn (over the bonus's own cap, 38'-6"): it raises nothing (the
            # review, R6: "…if it stays 60'-0" tall" offered a yard no 60 ft house could use)
            if any(c.left.id not in YARD_MEASURES and _evaluate(ast.unparse(c), values) is False for c in comps):
                continue
            for c in comps:
                if c.left.id in YARD_MEASURES:
                    out.setdefault(c.left.id, []).append((c, i))
    return out


def _while_raised(item, node, worst, raisers, values, measured, facts):
    """What a yard needs while the building keeps the height another rule's other way allows only with larger yards
    (the height bonus: "…; at least 33'-6" if it stays 36'-6" tall (the building height rule's other way raises
    this yard)"), from the same reading set, its worst reading, rounded up. As a clause ({"target", "height", "src",
    "changes", "also"}) the checker shows only when that rule then complies outright, every yard it raises with it
    (review round 4, G3), or None."""
    if item.get("measure") is None or not isinstance(values.get(node.left.id), (int, float)):
        return None
    more = []
    for c, src in raisers.get(node.left.id) or []:
        rs = readings(c, ast.unparse(c), values, measured, facts)
        low = min((r["margin"] for r in rs), default=None)
        if low is not None and low < worst - 1e-9:
            more.append((low, rs[0]["unit"], src))
    if not more:
        return None
    low, unit, src = min(more, key=lambda x: x[0])
    v = values[node.left.id]
    target = _up(v - low)                    # the distance it needs, rounded up once
    return {"target": feet_inches(target), "height": src["proposed"],
            "src": src["name"].lower(), "changes": {node.left.id: target - v},
            "also": [[src["rule"], None]]}           # the whole height rule: it complies, every raise held


def _step(amount: float, unit: str) -> float:
    """The change a hint names, as a number: `amount` rounded up the way its words are (to 1/8 in., a whole sf, a
    hundredth of a percent)."""
    k = {"ft": 96, "sf": 1, "%": 100}.get(unit, 1)
    return math.ceil(amount * k - 1e-9) / k


YARD_LINES = {"front_yard": "the front lot line", "rear_yard": "the rear lot line"}
# the eaves rows (PR 18, §325-18B) are their yards measured to the eaves: the same lot line, the same advice shape
# (the requirement for every part, eaves included), so the checker confirms what it says (#18 review round 26)
EAVE_YARD = {"front_yard_eaves": "front_yard", "side_yard_smaller_eaves": "side_yard_smaller",
             "side_yard_larger_eaves": "side_yard_larger", "rear_yard_eaves": "rear_yard"}
COMPASS = ("North", "South", "East", "West", "Northeast", "Northwest", "Southeast", "Southwest")


def _yard_line(name: str, measure: str) -> str:
    """The lot line a yard is measured from, as an architect says it: "the front lot line", "the west side lot
    line" (a side yard named by its compass side), else "that side lot line"."""
    measure = EAVE_YARD.get(measure, measure)
    if measure in YARD_LINES:
        return YARD_LINES[measure]
    side = name.split(", ", 1)[1] if ", " in name else ""
    return f"the {side.lower()} side lot line" if side in COMPASS else "that side lot line"


def _up(feet: float) -> float:
    """A distance rounded up to 1/8 in."""
    return math.ceil(feet * 96 - 1e-6) / 96


def _yard_advice(head, name, measure, value, need, required, note=""):
    """A yard's advice as its requirement, never one wall's move (review round 5, P2: on a stepped front, pulling
    back the nearest wall left the next one short): "keep every part of the building at least 25'-0" from the front
    lot line — now 22'-0 7/8" at its closest". Following it puts the building's closest part at the target, exactly
    what check.confirm_advice simulates. `need`: the exact shortfall (the target is the distance plus it, rounded up
    once: on a survey the requirement itself)."""
    target = _up(value + need)
    return {"head": head, "ways": [{"target": feet_inches(target), "changes": {measure: target - value}}],
            "yard": {"line": _yard_line(name, measure), "now": feet_inches(value, "down"),
                     "note": note if feet_inches(target) != required else "",
                     "part": "every part of the building, eaves included," if measure in EAVE_YARD else
                             "every part of the building"}}


def _drawn_advice(hint, node, margin, numbers, values, label="") -> dict | None:
    """The as-drawn "To comply" (_hint: the row's margin as drawn; coverage in sf) as advice, for the checker to
    confirm like any other (review round 3: without it, "lower the building 1'-6"" on a 36'-6" house was dropped,
    though lowering it makes the row comply)."""
    if not (hint or "").startswith("To comply: ") or node is None or margin is None:
        return None
    m, sign = node.left.id, numbers[4]
    if m == "building_area":
        allowed = _evaluate(ast.unparse(node.comparators[0]), values)
        if not isinstance(allowed, (int, float)) or not isinstance(values.get("building_area"), (int, float)):
            return None
        change = -_step(values["building_area"] - allowed, "sf")
    elif numbers[3] == "%":
        return None
    else:
        change = _step(-margin, numbers[3]) * (1 if sign in ("≥", ">") else -1)
    if (m in YARD_MEASURES or m in EAVE_YARD) and isinstance(values.get(m), (int, float)):
        required = _evaluate(ast.unparse(node.comparators[0]), values)
        return _yard_advice("To comply", label, m, values[m], -margin,
                            feet_inches(required, "up") if isinstance(required, (int, float)) else "")
    return {"head": "To comply", "ways": [{"text": hint[len("To comply: "):-1], "changes": {m: change}}]}


def advice_text(advice: dict | None) -> str | None:
    """A "To comply" sentence from its advice: "<head>: <way>, or <way>; <clause>." A yard's: "<head>: keep every part
    of the building at least <target> from <line>[ as drawn (<required> required, …)] — now <now> at its closest[;
    at least <target> if it stays <height> tall (…)]", or, its own figure not enough while the building stays that
    tall, "<head>: if it stays <height> tall, keep every part of the building at least <target> from <line> (…) —
    now <now> at its closest". None without either."""
    if not advice or not (advice.get("ways") or advice.get("clauses")):
        return None
    clauses = advice.get("clauses") or []
    yard = advice.get("yard")
    if yard is None:
        body = ", or ".join(w["text"] for w in advice["ways"]) + "".join("; " + c["text"] for c in clauses)
        return advice["head"] + ": " + body + "."
    raise_ = "(the {} rule's other way raises this yard)"
    now = f" — now {yard['now']} at its closest"
    if advice.get("ways"):
        body = (f"keep {yard.get('part', 'every part of the building')} at least {advice['ways'][0]['target']} "
                f"from {yard['line']}"
                f"{yard['note']}{now}" + "".join(f"; at least {c['target']} if it stays {c['height']} tall "
                                                 + raise_.format(c["src"]) for c in clauses))
    else:
        c = clauses[0]
        body = (f"if it stays {c['height']} tall, keep {yard.get('part', 'every part of the building')} at least "
                f"{c['target']} from "
                f"{yard['line']} {raise_.format(c['src'])}{now}")
    return advice["head"] + ": " + body + "."


def comply_hint(name: str, node, rs: list, values: dict, measured: dict, approx: bool) -> dict | None:
    """What to change so the row complies, from THE reading set (the verdict's own): the shortfall under its worst
    reading, rounded up, so the advised change makes it comply under every reading, never one that leaves it in
    review (the architect's review: "move 2'-11 3/8"" left a tax-map side yard needing review). On a tax-map lot
    it says so and gives the requirement too; on a survey, the one number. As advice: {"head", "ways": [{"text" or
    "target", "changes": {measure: signed change}}], "yard"} (advice_text says it; check.confirm_advice keeps only
    what the checker finds makes the row comply and no other row worse)."""
    sign = SIGNS[type(node.ops[0])]
    m = node.left.id
    worst = min(r["margin"] for r in rs)
    if worst >= 0:
        return None
    drawn, unit = _margin_of(node, values, measured)
    if m == "building_area":                     # coverage: the footprint, in sf, against the smallest allowed
        have = values.get("building_area")
        limits = [r["limit"] for r in rs if isinstance(r.get("limit"), (int, float))]
        if not isinstance(have, (int, float)) or not limits:
            return None
        need, as_drawn = have - min(limits), have - (_evaluate(ast.unparse(node.comparators[0]), values) or have)
        amount = lambda x: _area(x, "up")                                            # noqa: E731
        verb = lambda x: f"reduce the footprint by at least {amount(x)}"             # noqa: E731
        change = -_step(need, "sf")
    else:
        need, as_drawn = -worst, (-drawn if isinstance(drawn, (int, float)) else None)
        amount = lambda x: _gap(-x, unit)                                            # noqa: E731
        change = _step(need, unit) * (1 if sign in ("≥", ">") else -1)
        if m == "building_height":
            verb = lambda x: f"lower the building {amount(x)}"                       # noqa: E731
        else:
            verb = lambda x: f"{'increase' if sign in ('≥', '>') else 'reduce'} it by {amount(x)}"   # noqa: E731
    several = len({round(r["margin"], 9) for r in rs}) > 1
    whatever = "whatever the survey shows" if approx else "under every reading"
    head = "To comply " + whatever if several else "To comply"
    if (m in YARD_MEASURES or m in EAVE_YARD) and name.split(",")[0].endswith("yard") and \
            isinstance(values.get(m), (int, float)):
        required = _evaluate(ast.unparse(node.comparators[0]), values)
        req = feet_inches(required, "up") if isinstance(required, (int, float)) else ""
        note = (f" as drawn ({req} required, the lot lines ±{feet_inches(TOLERANCE)})" if approx else
                f" ({req} required, under every reading)") if several and req else ""
        return _yard_advice(head, name, m, values[m], need, req, note)
    shown = several and as_drawn and as_drawn > 0 and amount(as_drawn) != amount(need)
    drawn_part = f" ({amount(as_drawn)} as drawn)" if shown else ""
    return {"head": head, "ways": [{"text": verb(need) + drawn_part, "changes": {m: change}}]}


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


def _law_limit_way(check: str, values: dict, node):
    """For a rule whose ways to comply are each one limit on the same measure plus conditions only (R-1's occupancy:
    "unrelated_persons <= 1 or unrelated_persons <= 2 and owner_occupied and not accessory_dwelling_unit"), the limit
    the law sets here: the loosest of the ways whose conditions hold as stated (item 12: an owner-occupied R-1a house
    showed "1 required" where §325-3B allows 2). None for any other rule (a way with limits on other measures, e.g.
    the §325-16C height bonus raising the yards, keeps the row's own numbers)."""
    body = formula.parse(check).body
    if node is None or not (isinstance(body, ast.BoolOp) and isinstance(body.op, ast.Or)):
        return None
    m, op = node.left.id, type(node.ops[0])
    if op not in (ast.LtE, ast.Lt, ast.GtE, ast.Gt):
        return None
    best, best_limit = None, None
    for alt in body.values:
        parts = alt.values if isinstance(alt, ast.BoolOp) and isinstance(alt.op, ast.And) else [alt]
        limits = [p for p in parts if isinstance(p, ast.Compare)]
        others = [p for p in parts if not isinstance(p, ast.Compare)]
        if len(limits) != 1 or any(isinstance(n, ast.Compare) for p in others for n in ast.walk(p)):
            return None
        c = limits[0]
        if not (len(c.ops) == 1 and isinstance(c.left, ast.Name) and c.left.id == m and type(c.ops[0]) is op):
            return None
        if any(_evaluate(ast.unparse(p), values) is not True for p in others):
            continue                                   # this way's conditions don't hold (or aren't said)
        limit = _evaluate(ast.unparse(c.comparators[0]), values)
        if not isinstance(limit, (int, float)) or isinstance(limit, bool):
            continue
        looser = best_limit is None or (limit > best_limit if op in (ast.LtE, ast.Lt) else limit < best_limit)
        if looser:
            best, best_limit = c, limit
    return best


def _worst_reading(node, measured: dict, values: dict, review=()):
    """(worst reading, required) as text when the comparison fails under one of the measurement's readings, and the
    rule says fail there: none of its review conditions (`review`: the rule's review_when) holds at that reading
    (RU's note 3: two primary buildings on a lot over 60,000 sf fail the check but need review for the approvals,
    never "does not comply": PR2 review round 1)."""
    m = node.left.id
    readings = [r["value"] for r in (measured.get(m) or {}).get("readings") or [] if r.get("value") is not None]
    sign = SIGNS[type(node.ops[0])]
    if not readings:
        return None
    worst = min(readings) if sign in ("≥", ">") else max(readings)
    trial = dict(values, **{m: worst})
    if _evaluate(ast.unparse(node), trial) is not False:
        return None
    if any(_evaluate(r["when"], trial) is not False for r in review):
        return None
    shown = _display(*_numbers(node, trial, measured, ""))
    return shown[0], shown[1]


def _numbers(node, values: dict, measured: dict, name: str):
    """(proposed, required, margin, unit, sign) for one comparison; coverage as a percentage of lot area."""
    m = node.left.id
    sign = SIGNS[type(node.ops[0])]
    unit = (measured.get(m) or {}).get("unit") or ""
    proposed, required = values.get(m), _evaluate(ast.unparse(node.comparators[0]), values)
    if m == "building_area" and isinstance(required, (int, float)) and values.get("lot_area"):
        lot = values["lot_area"]                 # coverage in %, its own unit, even with the footprint unknown
        return (proposed / lot * 100 if isinstance(proposed, (int, float)) else None), required / lot * 100, None, \
            "%", sign
    if not isinstance(proposed, (int, float)) or not isinstance(required, (int, float)):
        return proposed, required, None, unit, sign
    margin = formula.margin(proposed, required, sign in ("≥", ">"))     # exact, as the comparison: never disagree
    return proposed, required, margin, unit, sign


def _display(proposed, required, margin, unit, sign):
    if unit == "%" and not isinstance(proposed, (int, float)):
        return "—", _pct(required, _toward(sign, False), 1), "", None
    if unit == "%":
        margin = formula.margin(proposed, required, sign not in ("≤", "<"))
        places = 2 if abs(margin) < 0.5 else 1
        return (_pct(proposed, _toward(sign, True), places), _pct(required, _toward(sign, False), places),
                margin_text(margin, "%"), margin)
    return (value_text(proposed, unit, sign, True), value_text(required, unit, sign, False),
            margin_text(margin, unit) if margin is not None else "", margin)


LEAST = {"ft": EIGHTH, "sf": 1.0, "%": 0.01}     # the smallest step each unit is shown in


def _amount(x: float, unit: str, direction: str) -> str:
    """An amount (never signed) in the row's unit, rounded in `direction`: 2'-0 5/8", 570 sf, 3.24%."""
    if unit == "ft":
        return feet_inches(x, direction)
    if unit == "sf":
        return _area(x, direction)
    if unit == "%":
        return _pct(x, direction, 2)
    return f"{x:g}"


def _margin_of(node, trial: dict, measured: dict):
    """(margin, unit) of one comparison for one set of values, exactly as the row shows it (coverage in %)."""
    proposed, required, margin, unit, sign = _numbers(node, trial, measured, "")
    if unit == "%" and isinstance(proposed, (int, float)) and isinstance(required, (int, float)):
        margin = formula.margin(proposed, required, sign not in ("≤", "<"))
    return margin, unit


def readings(node, expr: str, values: dict, measured: dict, facts: dict) -> list[dict]:
    """One row's readings: THE reading set (reading_set.combos, the checker's own: its verdict is decided over the
    same set) of every name its expression and its comparison read, each with the comparison `node`'s margin as
    the row shows it ("margin", "unit"), whether `expr` holds ("holds": True, False or None), and the row's own
    measure before any slack ("value") and its points ("points"). Empty when a value is unknown, a margin can't be
    worked out, or there are too many."""
    names = formula.names(ast.unparse(node)) | formula.names(expr)
    every = reading_set.combos(names, values, measured, facts)
    if not every:
        return []
    m, out = node.left.id, []
    for trial, picks in every:
        margin, unit = _margin_of(node, trial, measured)
        if margin is None:
            return []
        value, points, raised = picks.get(m, (values.get(m), None, 0.0))
        if raised and isinstance(node.ops[0], (ast.GtE, ast.Gt)):    # its own margin with the slack's full depth
            margin -= raised                                          # (the trial is kept at 0 for the verdict)
        out.append({"margin": margin, "unit": unit, "holds": _evaluate(expr, trial), "value": value,
                    "points": points, "limit": _evaluate(ast.unparse(node.comparators[0]), trial)})
    return out


def delta_words(status: str, span, unit: str, approx: bool) -> str:
    """The Delta, in words, everywhere it is shown (the panel, the notice, the report), from the row's margin over
    every reading (`span`: lowest, highest) and its final status. On one reading (a survey) the margin itself
    ("+2'-0" to spare", "−1'-4" short"); over several, what is true whichever is right: "at least 1'-0" short"
    (short under every one: the red part), "up to 2'-9" short" (short under some: amber), "at least 3'-0" to
    spare". Never overstated ("at least" rounds down, "up to" up) and never kinder than the status: "to spare"
    only on a row that complies; a row that needs review for another reason says its room "if confirmed"."""
    if span is None:
        return ""
    low, high = span
    least = LEAST.get(unit, 0)
    one = not approx and low == high
    if high < 0:                       # short under every reading
        if one:
            words = margin_text(high, unit) + " short"
        elif _rounds_to_nothing(-high, unit):
            words = "less than " + _amount(least, unit, "up") + " short"     # never "at least 0'-0" short"
        else:
            words = "at least " + _amount(-high, unit, "down") + " short"
        # the certain words only on a row that fails; one in review (it may comply another way) says to see why
        return words if status == FAILS else words + "; see why"
    if low < 0:                        # short under some
        return "up to " + _amount(max(-low, least), unit, "up") + " short"
    if _rounds_to_nothing(low, unit):
        return "at limit" if one else "at the limit at worst"
    room = margin_text(low, unit) if one else "at least " + _amount(low, unit, "down")
    return room + {COMPLIES: " to spare", REVIEW: " if confirmed"}.get(status, " here, but it does not comply")


def _worst_case(expr: str, values: dict, names: set, measured: dict, facts: dict) -> dict | None:
    """The values (a reading of THE reading set, reading_set.combos: the open questions, and on the tax map each
    lot line off by up to TOLERANCE, the lot area at either end) under which `expr` doesn't hold, or None if it
    holds under every one. Too many to work out, or a value unknown: the values as drawn (never a pass)."""
    every = reading_set.combos(names, values, measured, facts)
    if not every:
        return dict(values)
    return next((trial for trial, _ in every if _evaluate(expr, trial) is not True), None)


YARD_MEASURES = ("front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard")
COLOURS_NOTE = ("In the model: red is the part over the yard line whichever way the tax map's lot lines "
                f"(±{feet_inches(TOLERANCE)}) really lie (certain); amber is the part that depends on where a survey "
                "puts them.")


def _which(approx: bool, open_: bool) -> str:
    return " and ".join(([f"where the tax map's lot lines really are (±{feet_inches(TOLERANCE)})"] if approx else []) +
                        (["the open questions"] if open_ else [])) or "its readings"


def settle(items: list[dict], values: dict, measured: dict, facts: dict) -> None:
    """The ONE place each row's Delta, "approx" mark, colours and tax-map detail line are decided, from its
    readings (`readings`: THE reading set, on its expression and the comparison it was decided on, raised if a
    raise applies), AFTER every status change. The status is the checker's (check.row_verdict: the only place a
    row complies or fails); settle only ever lowers it (a complies with a reading that doesn't becomes needs
    review), never raises it. The panel, the notice, the report, the plan's labels and the red and amber all read
    only these.
      delta    the words (delta_words) for its final status;
      approx   whether the tax map's lot lines moved any value it reads;
      colour   a yard's: "red" (fails: short under every reading), "amber" (short under some), or "none";
      limits   for a yard in colour, per reading of where its line is: the lot-line point and how deep from the
               drawn line the wall is short under every ("near") and under some ("far") reading of the rest.
    A wall `x` from the drawn line has margin (margin + x − value) under a reading: short when x < value −
    margin. Red is short under every reading, amber under some (check.plan draws them)."""
    tax = bool((measured.get("lot_area") or {}).get("tolerance")) and not facts.get("lot_surveyed")
    raisers = _raisers(items, values)
    for i in items:
        node, expr = i.pop("_node", None), i.pop("_expr", None)
        # its own measurement is an open question (to the wall or to the overhangs?): the checker never lets it
        # comply, whatever is moved, so no "To comply" (the review, F5). An open question it turns on only through
        # its limit (the lot depth) goes away with the right change (lower the roof: the bonus no longer applies).
        # (Its own value is then unknown, so it has no as-drawn hint either.)
        stuck = node is not None and node.left.id in (i.pop("_turns_on", None) or [])
        i.update(delta="", approx=False, colour="none", limits=[])
        i["detail"].setdefault("colours", None)
        if node is None:
            continue
        rs = readings(node, expr or ast.unparse(node), values, measured, facts)
        if not rs:                       # no reading set (a value unknown): the margin as drawn, if it has one
            margin, unit = _margin_of(node, values, measured)
            if margin is not None:
                i["delta"] = delta_words(i["status"], (margin, margin), unit, False)
            continue
        span, unit = (min(r["margin"] for r in rs), max(r["margin"] for r in rs)), rs[0]["unit"]
        reads = formula.names(ast.unparse(node)) | formula.names(expr or "")
        lot = tax and bool(reads & (LOT_LENGTHS | {"lot_area"}))
        approx = tax and bool(formula.names(ast.unparse(node)) & (LOT_LENGTHS | {"lot_area"}))  # its own margin's
        open_ = any(values.get(n) is None for n in reads)
        holds = {r["holds"] for r in rs}
        if i["status"] == COMPLIES and holds != {True}:      # short under some reading: never a pass (only
            # ever more cautious: the checker alone decides a row complies or fails)
            i.update(status=REVIEW, mark=MARK[REVIEW], reason=(
                f"Complies as drawn, but not under every reading of {_which(lot, open_)} · Pick survey lot lines…"))
        i.update(delta=delta_words(i["status"], span, unit, approx), approx=approx)
        body = ast.parse(expr or ast.unparse(node), mode="eval").body
        one_way = not isinstance(body, ast.BoolOp) or (i.get("_raised") and isinstance(body.op, ast.And))
        if (i.get("_advice") or {}).get("crossing"):     # partly off the lot: its one advice, move it back (PR 18)
            pass
        elif node.left.id in SITE_MEASURES:            # a lot's own size is no design change (the review, F1, R4)
            if (i.get("hint") or "").startswith("To comply"):
                i["hint"], i["_advice"] = None, None
        elif span[0] < 0 and one_way and not stuck and (not i.get("hint") or i["hint"].startswith("To comply")):
            advice = comply_hint(i["name"], node, rs, values, measured, approx)
            if advice and isinstance(i.get("_raised"), tuple):   # a raised yard: the raise must hold too
                for way in advice["ways"]:
                    way["also"] = [list(i["_raised"])]
            clause = _while_raised(i, node, span[0], raisers, values, measured, facts) if advice else None
            if clause:
                advice["clauses"] = [clause]          # (shown alone if the yard's own figure isn't enough)
            if advice:                               # (the checker confirms each part: check.confirm_advice)
                i["hint"], i["_advice"] = advice_text(advice), advice
        i.pop("_raised", None)
        if approx and i["detail"].get("line"):
            i["detail"]["line"] = (f"{i['proposed']} proposed, {i['required']} required as drawn · with the tax map's "
                                   f"±{feet_inches(TOLERANCE)}: {i['delta']}")
        if node.left.id not in YARD_MEASURES or i["status"] not in (FAILS, REVIEW) or span[0] >= 0:
            continue
        i["colour"] = "red" if i["status"] == FAILS and span[1] < 0 else "amber"
        by_line = {}
        for r in rs:
            if r["points"] and isinstance(r["value"], (int, float)):
                depth = r["value"] - r["margin"]
                key = tuple(map(tuple, r["points"]))
                near, far = by_line.get(key, (depth, depth))
                by_line[key] = (min(near, depth), max(far, depth))
        i["limits"] = [{"points": [list(p) for p in k], "near": n, "far": f} for k, (n, f) in by_line.items()]
        if approx:
            i["detail"]["colours"] = COLOURS_NOTE


def _best_case(expr: str, values: dict, names: set, measured: dict, facts: dict) -> dict | None:
    """The values (a reading of THE reading set, as _worst_case's) under which `expr` holds, or None if it fails
    under every one: on a tax-map lot a rule fails only if it fails under every reading of where the lines are
    (Ben, 2026-10-21)."""
    return next((trial for trial, _ in reading_set.combos(names, values, measured, facts) or []
                 if _evaluate(expr, trial) is True), None)


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
    body = formula.parse(check).body if check else None
    if (_status(row) == FAILS and isinstance(body, ast.BoolOp) and isinstance(body.op, ast.And)
            and all(isinstance(v, ast.Compare) for v in body.values)):
        # a rule that is several limits at once (the eaves into every yard): name and show the one that fails
        unknown = row.get("Unknown")        # not measured: a limit that fails at every value they could take
        primary = next((c for c in compares if _evaluate(ast.unparse(c), values) is False
                        or unknown and _fails_whatever_part(ast.unparse(c), values, unknown)
                        or _fails_every_reading(ast.unparse(c), values, measured, facts)), primary)
    elif (_status(row) == REVIEW and rule.get("review_when") and isinstance(body, ast.BoolOp)
          and isinstance(body.op, ast.And) and all(isinstance(v, ast.Compare) for v in body.values)):
        # a several-limit rule held back by its own review_when (its reason is the row's): name the limit that
        # review is about, the measure it holds below a limit (the which-side eaves review: that side's eave),
        # never simply the first limit (#18: "Eaves into front yard" for a side eave's question)
        why_text = " ".join(str(row.get("Why") or "").split())
        said = {" ".join(w.split()) for w in str(row.get("Why") or "").split("; ")}
        at_least = {c.left.id for c in compares if isinstance(c.ops[0], (ast.GtE, ast.Gt))}
        about = []                      # (measure, the limit the review holds it below), in the rule's order
        for r in rule["review_when"]:
            reason = " ".join(str(r.get("reason") or "").split())
            # the row's reason is this one: a whole entry of it, or (a reason with "; " of its own) all of it in it
            if reason and (reason in said or len(reason) > 40 and reason in why_text):
                # each measure the review holds below a limit, where that holds as drawn (or can't be told), on a
                # measure the rule asks to be at least something: that limit is what the review is about
                about += [n for n in ast.walk(formula.parse(r["when"]).body)
                          if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.left, ast.Name)
                          and isinstance(n.ops[0], (ast.Lt, ast.LtE)) and n.left.id in at_least
                          and _evaluate(ast.unparse(n), values) is not False]
        failing = next((c for c in compares if _fails_every_reading(ast.unparse(c), values, measured, facts)), None)
        if failing is not None:         # a limit failing under every reading is named first (#18 round 4)
            primary = failing
        elif about:
            # the limit the question is about, as a requirement: "at least" the review's own limit (the side that
            # may be the 10 ft one: 7'-0" against 8'-0", never against the 5 ft side's 3'-0" it already meets)
            n = about[0]
            primary = ast.Compare(left=n.left, ops=[ast.GtE()], comparators=n.comparators)
    measure = primary.left.id if primary is not None else None
    name = NAMES.get(measure) or row.get("Short") or row.get("Requirement")
    if primary is None and names == {"use"}:          # use in [...]: the use, and whether it's permitted
        name = "Use"
    site = bool(names) and names <= SITE_MEASURES
    status, reason = _status(row), _reason(row)
    reason = _depends(row, status, measured) or reason
    splits = [c for c in compares if c.left.id in ("side_yard_smaller", "side_yard_larger")] if measure in (
        "side_yard_smaller", "side_yard_larger") else []
    # two side yards: always in the same order (by name), so equal yards never swap with the model's units
    same = len(splits) == 2 and len({ast.unparse(c.comparators[0]) for c in splits}) == 1
    parts = sorted(((c, _side_name(c.left.id, measured, facts.get("plan_north_deg") or 0.0, extras.get("side_lines"),
                                   same)) for c in splits),
                   key=lambda p: p[1]) \
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
        here = None                 # this side yard's own readings, when it was decided by them (below)
        expr = ast.unparse(node) if splits else check
        side_row = None
        if splits and node is not None and node.left.id in (row.get("Sides") or {}):
            st = row["Sides"][node.left.id]                 # each side yard: the checker's verdict for it, and
            side_row = {"Verdict": st, "Provisional": (row.get("Side provisional") or {}).get(node.left.id),
                        "Turns on": (row.get("Side turns on") or {}).get(node.left.id),
                        "Named": (row.get("Side named") or {}).get(node.left.id),
                        "Why": (measured.get(node.left.id) or {}).get("reason") or row.get("Why")}
            why = _depends(side_row, st, measured) or _reason(side_row)   # that verdict alone, never the pair's
                                                            # (complies: none; review: its open question)
        elif splits and node is not None and status != REVIEW:   # (no checker verdict per side: as drawn)
            holds = _evaluate(expr, values)
            st = COMPLIES if holds is True else FAILS if holds is False else REVIEW
        checker = st                                         # never shown above this (the guard in view)
        drawn = _evaluate(expr, values) if expr else None    # the row's expression as drawn (a flag has none)
        clean = row.get("Error") in ("PASS", "FAIL") or bool(splits)    # nothing but the readings undecided
        tax = not facts.get("lot_surveyed") and bool((measured.get("lot_area") or {}).get("tolerance"))
        raised = []                 # the rule complies another way it allows (the §325-16C height bonus): its
        if node is not None and drawn is True and st != FAILS and not splits and \
                _evaluate(ast.unparse(node), values) is False:         # (as drawn: the checker's status stands)
            way = _holding_way(check, values)          # numbers are that way's, and the yards it raises
            if way:
                node = next((c for c in way if c.left.id == node.left.id), node)
                raised = [c for c in way if c.left.id != node.left.id]
        if node is not None and not splits and not raised and check:
            node = _law_limit_way(check, values, node) or node     # the limit the law sets here (owner-occupied: 2)
        numbers = _numbers(node, values, measured, label) if node is not None else (None, None, None, "", "")
        proposed, required, margin_t, margin = (*_display(*numbers),) if node is not None else ("—", "—", "", None)
        if name == "Use":
            proposed = use_names.get(values.get("use"), values.get("use") or "—")
            required = {COMPLIES: "permitted", FAILS: "not permitted"}.get(st, "—")
        if st in (COMPLIES, REVIEW) and drawn is True and clean and tax and names & LOT_LENGTHS:
            worst = _worst_case(expr, values, names, measured, facts)   # complies as drawn: say how it may not
            if worst is not None:
                bad = next((c for c in ([node] + raised if raised else _compares(expr))     # the way it uses
                            if _evaluate(ast.unparse(c), worst) is False), node)
                w = _numbers(bad, worst, measured, label)
                what = "" if bad.left.id == node.left.id else NAMES.get(bad.left.id, bad.left.id.replace("_", " ")) + " "
                st = REVIEW
                why = (f"Lot lines are from the tax map (±{feet_inches(TOLERANCE)}): at worst "
                       f"{what}{_display(*w)[0]} against {_display(*w)[1]} · Pick survey lot lines…")
        own_named = (side_row or row).get("Named")
        if st == REVIEW and tax and node is not None and (own_named or {}).get("result") == "pass" and \
                formula.names(expr) & LOT_LENGTHS:
            # complies under every reading research lists as drawn; only the tax map's lines hold it back: say so,
            # and how (never "confirm with the zoning office": a survey settles it; review round 20)
            worst = _worst_case(expr, values, formula.names(expr), measured, facts)
            if worst is not None:
                w = _numbers(node, worst, measured, label)
                why = (f"Lot lines are from the tax map (±{feet_inches(TOLERANCE)}): as drawn it complies under "
                       f"every reading; at worst {_display(*w)[0]} against {_display(*w)[1]} · Pick survey lot lines…")
        tol = (measured.get("lot_area") or {}).get("tolerance")
        every = reading_set.rule_names(rule)
        survey_only = "lot_area" in every and (measured.get("lot_area") or {}).get("value") is None and all(
            values.get(n) is not None for n in every - {"lot_area"})        # nothing else it reads is open
        if st == COMPLIES and tol and tax and node is not None and row.get("Provisional") == SURVEY_ONLY:
            why = (f"Complies even at the tax-map worst case (lot area {_area(tol['low'], 'down')})"
                   " · Pick survey lot lines…")                        # the checker's verdict, said
        elif st == REVIEW and tol and tax and node is not None and survey_only:
            # waiting only on the survey: say why from the reading set (the lot area at its ends, spec C2)
            bad = _worst_case(expr, values, names, measured, facts)
            if bad is None:
                pass
            elif _evaluate(expr, values) is False and _best_case(expr, values, names, measured, facts) is not None:
                w = _numbers(node, _best_case(expr, values, names, measured, facts), measured, label)
                why = (f"Lot lines are from the tax map (±{feet_inches(TOLERANCE)}): as drawn it does not comply, "
                       f"but at best {_display(*w)[0]} against {_display(*w)[1]} · Pick survey lot lines…")
            else:
                w = _numbers(node, bad, measured, label)
                why = (f"Lot lines are from the tax map (±{feet_inches(TOLERANCE)}): at worst {_display(*w)[0]} "
                       f"against {_display(*w)[1]} · Pick survey lot lines…")
        as_drawn_fails = (drawn is False and clean) or (not side_row and (row.get("Readings") or {}).get("result") == "fail")
        if st == REVIEW and as_drawn_fails and tax and node is not None and (names & LOT_LENGTHS or tol):
            # fails as drawn, but the checker found a reading of the tax-map lines under which it complies: say how
            best = _best_case(expr, values, names, measured, facts)
            if best is not None:
                if _evaluate(ast.unparse(node), best) is True:      # its own comparison holds at best: say how
                    w = _numbers(node, best, measured, label)
                    could = f"at best {_display(*w)[0]} against {_display(*w)[1]}"
                else:                                               # it holds the rule's other way at best
                    could = "it could comply the rule's other way if the lines are off in its favour"
                why = (f"Lot lines are from the tax map (±{feet_inches(TOLERANCE)}): as drawn it does not comply, "
                       f"but {could} · Pick survey lot lines…")
        own = side_row or row                               # a side yard: its own words, never the pair's
        if st == FAILS and own.get("Provisional") and (side_row or not row.get("Error") == "FAIL") and \
                not (why or "").startswith("Does not comply whichever way it is read"):
            why = ("Does not comply with the lot as drawn; the lot lines aren't from a survey · Pick survey lot lines…"
                   if "confirm the survey" in own["Provisional"] else
                   "Fails under every reading considered (" + ", ".join(dict.fromkeys(
                       NAMES.get(n, n.replace("_", " ")).lower() for n in sorted(formula.names(expr) if expr else names)
                       if (measured.get(n) or {}).get("value") is None and (measured.get(n) or {}).get("readings")))
                   + ")")             # what was read (never the doubled "fails under every reading")
        line = _detail_line(proposed, required, margin_t, numbers[4] if node is not None else "", margin)
        hint = _hint(label, numbers[4], margin, numbers[3]) if node is not None and margin is not None else None
        if node is not None and node.left.id == "building_area" and margin is not None and margin < 0:
            allowed = _evaluate(ast.unparse(node.comparators[0]), values)
            if isinstance(allowed, (int, float)) and values.get("building_area") is not None:
                hint = f"To comply: reduce the footprint by at least {_area(values['building_area'] - allowed, 'up')}."
        advice = _drawn_advice(hint, node, margin, numbers, values, label)
        if advice and advice.get("yard"):            # a yard's: its requirement for every part (round 6, P3)
            hint = advice_text(advice)
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
                worst = _worst_reading(node, measured, values, rule.get("review_when") or ())
                # (the overhang question in coverage is settled in PR 18: coverage_seen_from_above, so
                # term-index's "both ways" words for it have nothing left to say)
                if worst is not None:                   # say the bad one first: "probably fine" it isn't
                    why = (f"At worst {worst[0]} against {worst[1]}: does not comply under that reading. " +
                           (why or ""))
        bound = ((measured.get("stories") or {}).get("reason") or "") if measure == "stories" else ""
        if st == REVIEW and "could hold up to" in bound:     # the drawing allows a range: say why, plainly,
            # every open question kept (the main building's, the accessory one), the bad reading first
            qs = [_user_text(q.replace(" (story)", "")) for q in bound.split("; ")[1:] if q.strip()]
            worst = why.split(": does not comply under that reading.")[0] + ": does not comply under that reading. " \
                if (why or "").startswith("At worst") else ""
            said = "; ".join(dict.fromkeys(q[0].upper() + q[1:] if i == 0 else q for i, q in enumerate(qs)))
            why = worst + said + "."
            if not (measured.get("stories") or {}).get("count_settles") and PICK_MAIN_WHY not in why:
                hint = PICK_MAIN if (measured.get("stories") or {}).get("main_assumed") else hint
        span_ft = None                   # a limit read two ways (the lot depth open), in feet: its range
        if node is not None and required == "—" and st in (REVIEW, FAILS):
            # the limit waits on an open measurement (the lot depth, on which lines are side or rear): show the
            # limit's range over its readings, and say once what it depends on (architect review P1-3)
            limit_expr = ast.unparse(node.comparators[0])
            open_ = [n for n in sorted(formula.names(limit_expr))
                     if values.get(n) is None and (measured.get(n) or {}).get("readings")]
            got = []
            if open_:
                import itertools
                for combo in itertools.product(*[[r["value"] for r in measured[n]["readings"]] for n in open_]):
                    x = _evaluate(limit_expr, dict(values, **dict(zip(open_, combo))))
                    if isinstance(x, (int, float)):
                        got.append(x)
            if got:
                unit = (measured.get(node.left.id) or {}).get("unit") or ""
                lo, hi = min(got), max(got)
                span_ft = [lo, hi] if unit == "ft" else None
                required = (value_text(lo, unit, numbers[4], False) if hi - lo < 1e-9 else
                            f"{value_text(lo, unit, numbers[4], False)} to {value_text(hi, unit, numbers[4], False)}")
                # the same limit under every reading: it depends on none of them (#20 review round 1)
                limit_q = [] if hi - lo < 1e-9 else list(dict.fromkeys(q for n in open_ for q in _questions_of(measured[n])))
                rest = list(dict.fromkeys(q for n in sorted(every - set(open_)) if values.get(n) is None
                                          and (measured.get(n) or {}).get("readings")
                                          for q in _questions_of(measured[n]) if q not in limit_q))
                sets = " and ".join(NAMES.get(n, n.replace("_", " ").capitalize()).lower() for n in open_)
                complying = (why or "").startswith("Complies")    # every reading complies: its own words stay
                if limit_q and st == FAILS:
                    why = (f"Does not comply whichever way it is read: needs {required} (the {sets} depends on "
                           f"{'; '.join(limit_q)})")
                elif limit_q and not complying and not (why or "").startswith("Lot lines are from the tax map") and \
                        not ((side_row or row).get("Provisional") or "").startswith("passes"):
                    # (the tax map's own sentence, and "complies under every reading, but it depends on …", say more)
                    why = (f"Needs {required}, depending on {'; '.join(limit_q)} (it sets the {sets}): ask the "
                           "zoning office" + (f"; also open: {'; '.join(rest)}" if rest else ""))
        alts = _alternatives(check, values, measured, facts) if st == FAILS and not why and not splits else []
        shown = [[x for x in alt if x[6]] for alt in alts]          # the reason: what fails as drawn
        if len(alts) > 1 and all(shown):                # several ways to comply, none met: say each one
            why = "Does not comply either way the rule allows: " + "; or ".join(
                ", ".join(f"{n} {p}, needs {s} {r}" for n, p, s, r, *_ in alt) for alt in shown)
            ways = [alt[0] for alt in alts if len(alt) == 1]
            if ways:
                advice = {"head": "To comply" + (" whatever the survey shows" if any(w[5] for w in ways) else ""),
                          "ways": [{"text": _fix(*w[:5]), "changes": w[7]} for w in ways]}
                hint = advice_text(advice)
        base_calc = None
        if (node is not None and st != COMPLIES and required in ("—", None) and values.get("building_height") is None
                and "building_height" in formula.names(ast.unparse(node.comparators[0]))):
            # a limit raised by the §325-16C height bonus, while the height can't be measured: show the base
            # requirement (no bonus) and say it may be more; never as complying
            limit = ast.unparse(node.comparators[0])
            unit = (measured.get(node.left.id) or {}).get("unit") or ""
            height = measured.get("building_height") or {}
            # why the bonus can't be worked out, read from the height's own measurement (review rounds 10-11)
            as_is = height.get("measured_as_is") is not None or bool(height.get("measured_as_is_readings"))
            # (a height measured with readings that disagree: the limit's range over them, said by the
            # one range block above; here the height isn't measured at all, or only on existing grade)
            base = _evaluate(limit, dict(values, building_height=0.0))
            if isinstance(base, (int, float)):
                required = f"{numbers[4]} {value_text(base, unit, numbers[4], False)}".strip()
                waits = ("the height is measured from existing grade only; the bonus needs it from finished grade"
                         if as_is else "the height isn't measured yet")
                more = f"more if the §325-16C height bonus applies; {waits}"
                why = f"{why} ({more})" if why else f"{_bonus_waits(st, False)} ({more})"
                line = f"{proposed} proposed · {required} required before the §325-16C height bonus"
                base_calc = f"Required: {required} before the §325-16C height bonus ({waits})"
        applied = _applied(names, measured)
        if applied["note"]:                     # Gordium's reading, applied: always said, never hidden
            why = f"{why} · {applied['note']}" if why else applied["note"]
        if row.get("Crossing"):                 # a building partly on another lot: fails, whatever else
            # the row's own verdict, the crossing set aside: its only failing fact? Never on a distance row (a yard,
            # eaves, an accessory building's yards): moving the building back changes the distance itself
            distance = node is not None and (node.left.id in YARD_ROWS or node.left.id.endswith("_yard"))
            was = st
            alone = was == COMPLIES and not distance
            st, why = FAILS, "Does not comply: " + row["Crossing"]
            # the only advice: move it back (no other "To comply" is shown for it; settle and
            # check.confirm_advice keep it as it is: no measured change can be simulated for it). "To comply" only
            # where the crossing is the row's only failing fact; anywhere else moving back is not enough (a yard, a
            # 50 ft height, a frame shed's 6 ft, coverage): its first step (#18 review rounds 26-27)
            advice = {"head": "To comply" if alone else "First",
                      "ways": [{"text": "move it back onto the lot", "changes": {}}], "crossing": True}
            hint = advice_text(advice)
            if was == COMPLIES and (node is None or node.left.id not in YARD_ROWS):   # failing fact: the crossing
                proposed, required, margin_t = "partly off the lot", "on the lot", ""
        out.append({
            "id": rule["id"] + ("#" + label.split(", ")[-1].lower() if splits else ""), "rule": rule["id"],
            "name": label, "group": "site" if site else "building", "status": st, "mark": MARK[st],
            "proposed": proposed, "required": required, "margin": margin_t if st != REVIEW or margin_t else "",
            "_node": node,                        # the comparison it was decided on (a raise replaces it); popped
            "_expr": expr,                        # and its whole expression (settle reads both)
            "_checker": checker,                  # the checker's verdict for it: the most it may show (view)
            # the open questions that verdict turns on: while there are any, no change to the design makes it comply
            "_turns_on": (side_row if side_row is not None else row).get("Turns on") or [],
            # the stated facts it reads that aren't set (R-3a's lot size: dwelling units…): its own "Enter …" button
            "needs": (rhino_logic.needs_of(reading_set.rule_names(rule), values,
                                           lambda k: st == REVIEW and could_settle(rule, values, k)) + (
                ["stories"] if "stories" in reading_set.rule_names(rule) and (
                    (measured.get("stories") or {}).get("stories_refused") or     # refused: Enter again, always
                    rhino_logic.stories_needed(measured.get("stories"))
                    and (measured.get("stories") or {}).get("count_settles", True)) else [])) if st != COMPLIES else [],
            # the count typed was refused (the measuring's code): the plugin rolls it back by this, never by words
            "refused": ((measured.get("stories") or {}).get("stories_refused")
                        if "stories" in reading_set.rule_names(rule) else None),
            "sign": numbers[4] if node is not None else "", "reason": why, "hint": hint,
            "_advice": advice if hint and advice and hint == advice_text(advice) else None,
            "_raises": list(raised),              # the comparisons themselves (worst cases need them); popped
            "zoom": ZOOM.get(measure, "top"), "measure": node.left.id if node is not None else None,
            "objects": (measured.get(node.left.id) or {}).get("objects", []) if node is not None else [],
            "points": (measured.get(node.left.id) or {}).get("points") if node is not None else None,
            # the limit as drawn, in feet, for the plan's faint required line (a yard, the height); None otherwise
            "limit_ft": (numbers[1] if node is not None and numbers[3] == "ft" and isinstance(numbers[1], (int, float))
                         else None),
            "limit_span_ft": span_ft,
            "detail": {
                "line": line,
                "quotes": quotes,
                "citation": combined(list(dict.fromkeys(c for c, _ in cited))),
                "links": list(dict.fromkeys(u for _, u in cited)),
                "cited": [{"citation": c, "link": u} for c, u in dict.fromkeys(cited)],
                "calc": base_calc or _calc(node, values, measured, required),
                "scope": _scope(extras, measured),
                # how the lot lines were read from the outline drawn, when it was cleaned (decided 2026-10-21)
                "outline": next((measured[n]["outline"] for n in sorted(names)
                                 if (measured.get(n) or {}).get("outline")), None),
                "precision": PRECISION,
                "at_limit": (f"At the limit: {proposed} exact" if margin_t == "at limit" else None),
                "basis": applied["all"],
                # what might be eaves (each overhang's fingerprint): what a confirmation (eaves_confirmed) names
                "eave_candidates": list(dict.fromkeys(c for n in sorted(names)
                                                      for c in (measured.get(n) or {}).get("eave_candidates") or [])),
            }})
        if node is not None and node.left.id == "building_height":
            out[-1]["detail"].update(_height_detail(j, facts, values, node, numbers))
    return out


def _applied(names: set, measured: dict) -> dict:
    """What research settled that a rule's measurements apply (each measurement's `basis`): {"all": each one's
    words (the law, Gordium's reading, or an answer), "note": the readings to confirm, short, for the reason}."""
    found = {}
    for n in sorted(names):
        for b in (measured.get(n) or {}).get("basis") or []:
            found.setdefault(b["id"], b)
    notes = []
    for b in found.values():
        if b["kind"] == "reading":
            first = b["text"].split(": ", 1)[-1].split(". ")[0].rstrip(".")
            notes.append(f"Gordium's reading · confirm with {b['confirm_with']}: {first}")
        elif b["kind"] == "answer":
            notes.append(b["text"])
    return {"all": [b["text"] for b in found.values()], "note": " · ".join(dict.fromkeys(notes))}


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


COMPASS = ("North", "Northeast", "East", "Southeast", "South", "Southwest", "West", "Northwest")
MIXED = "mixed"             # a side yard's readings measured toward different lines: no one name is true


def compass(dx: float, dy: float, plan_north_deg: float = 0.0) -> str | None:
    """The true compass point (8 of them) a plan direction (dx, dy) faces, the plan turned `plan_north_deg` from
    true north; None for no direction."""
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return None
    turn = math.radians(plan_north_deg or 0.0)
    east = dx * math.cos(turn) + dy * math.sin(turn)            # back from the plan to true north
    north = -dx * math.sin(turn) + dy * math.cos(turn)
    return COMPASS[int((math.degrees(math.atan2(east, north)) % 360 + 22.5) // 45) % 8]


def _side_name(measure: str, measured: dict, plan_north_deg: float = 0.0, side_lines=None,
               same_minimum: bool = False) -> str:
    """Side yard, East/Northeast/...: the true compass direction, on 8 points, from the building to the lot line the
    yard was measured to. `plan_north_deg` is how far the plan is turned from true north (a looked-up lot is drawn
    turned so its street runs along the bottom: lookup_box.frame's rotation); 0 for a lot drawn by hand (plan north
    = +y). Without a measured line: when both sides need the same minimum, the compass names of the lot's two
    side lines (`side_lines`, from the checker: which row is which can't mislead then); otherwise, or if both point
    the same way, narrower or wider."""
    def facing(pts):
        if not pts:
            return None
        return compass(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1], plan_north_deg)   # lot line minus building
    def faces(name):
        """The one direction every reading of a side yard was measured toward, or None if they differ (under one
        reading the narrower yard is to one side line, under another to the other: no compass name is true)."""
        m = measured.get(name) or {}
        found = {facing(r.get("points")) for r in m.get("readings") or []} or {facing(m.get("points"))}
        return found.pop() if len(found) == 1 else MIXED
    a, b = faces("side_yard_smaller"), faces("side_yard_larger")
    if a and b and a != b and MIXED not in (a, b):
        return "Side yard, " + (a if measure == "side_yard_smaller" else b)
    # the lot's side lines' names only when no reading says where the yard was measured to; never when the readings
    # point different ways (the narrower yard is to one line under one reading, to the other under another: F5)
    if a is None and b is None and same_minimum and side_lines and len(set(side_lines)) == 2:
        return "Side yard, " + (sorted(side_lines)[0] if measure == "side_yard_smaller" else sorted(side_lines)[1])
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
    out. Law text and footnotes are quoted as they are. A cell source is quoted as exactly that cell; if the chart
    has no such cell, as the source's own words (its section, row and column), never a neighbouring cell."""
    text = " ".join(str(source.get("quote", "")).split())
    if _is_chart(source, documents) and not re.match(r"^\(\d+\)", text):
        if text and all(re.fullmatch(r"R-\w+|\[fn\d+\]", w) for w in text.split()):
            return None
        lines = source.get("lines") or []
        cell = next((c for c in _chart_cells(j) if c["file"] == source.get("file") and c["page"] == source.get("page")
                     and c["column"].upper() == district.upper() and lines and lines[0] in (c.get("row_lines") or [])),
                    None)
        if cell is None and isinstance(source.get("cell"), dict):
            # exactly the cell cited, by the key the rule checks use (rule_format.rulebook._cell: page, section,
            # row stripped, column): never a near match, which once quoted a lot-width rule as the lot-size cell
            want = source["cell"]
            key = (source.get("page"), want.get("section"), str(want.get("row", "")).strip(), want.get("column"))
            cell = next((c for c in _chart_cells(j) if c["file"] == source.get("file")
                         and (c["page"], c.get("section"), c["row"].strip(), c["column"]) == key), None)
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

def _building_items(items: list[dict]) -> list[dict]:
    """The items counted as the building's: not the rules not in Gordium yet, and not the use details still waiting for
    an answer (their own group, "use_details")."""
    return [i for i in items if i["group"] != "not_covered" and not i.get("use_detail")]


def summary(items: list[dict]) -> str:
    """One line, the same everywhere: every item counted (site rows too), bad news first, no zero counts, never
    a check mark: "1 does not comply · 2 need review · 7 comply · 3 not checked". The use details still to answer are
    counted apart, last: "· 5 use details to answer" (not among the problems, and never among the passes)."""
    counted = _building_items(items)
    parts = []
    for st in ORDER:
        n = sum(1 for i in counted if i["status"] == st)
        if n:
            parts.append(f"{n} {WORDS[st][0 if n == 1 else 1]}")
    d = sum(1 for i in items if i.get("use_detail"))
    if d:
        parts.append(f"{d} use detail{'s' if d != 1 else ''} to answer")
    return " · ".join(parts) or "nothing checked"


def state(items: list[dict]) -> str:
    counted = _building_items(items)
    for st in (FAILS, REVIEW):
        if any(i["status"] == st for i in counted):
            return st
    # a use detail left unanswered is not a problem with the building, but it is not a pass either: never "complies"
    return REVIEW if any(i.get("use_detail") for i in items) else COMPLIES


from model_measurement.stops import stop as _stop  # noqa: E402

PICK_MAIN_WHY = _stop("no_main_building")        # the measuring's exact words when several buildings could be it
PICK_MAIN = "Pick the main building…"            # the row's hint, and the panel's button
ASSUMED_MAIN_NOTE = "assuming the starting house is the main building"      # a Gordium reading: to confirm
ASSUMED_MAIN = "Main building: the starting house (assumed) · change it with Main building…"


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
            worst = _worst_case(expr, values, formula.names(expr), measured, facts) if not facts.get("lot_surveyed") else None
            for t in items:
                if t is i or t.get("measure") != m or t["status"] == FAILS:
                    continue
                t["required"], t["margin"], t["hint"] = value_text(req, unit, sign, False), margin_text(margin, unit), None
                t["_node"] = c                           # its Delta and colours are the raised minimum's
                if unit == "ft":                         # the plan's faint required line too (review round 1, F1)
                    t["limit_ft"] = req
                t["_raised"] = (i["rule"], expr)         # (and its "To comply", confirmed against it: settle)
                t["_expr"] = f"({t['_expr']}) and ({expr})" if t.get("_expr") else expr
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


# What each looked-up fact decides (facts["unsettled"]): every measurement worked out from it. The lot outline decides
# the lot's area, width and depth and every yard; the street side decides which line is the front, so the yards and
# the lot's width and depth; the ground decides height and stories. An item needs review when ANY name in its rule's
# formula is one of them, not only its own measurement: the height bonus (§325-16C) complies through the yards and
# the lot depth (review round 1 of PR #19: it stayed "complies" on a doubtful lot).
YARDS = ("front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard")
UNSETTLED_DECIDES = {
    "lot": ("lot_area", "lot_width", "lot_depth") + YARDS,
    "street": ("lot_width", "lot_depth") + YARDS,
    "ground": ("building_height", "stories"),
}
UNSETTLED_NAMES = {"lot": "lot outline", "street": "street side", "ground": "ground levels"}


def _formula_names(item, rules_by_id):
    """Every measurement the item's rule reads (its formula), else its own measurement."""
    rule = (rules_by_id or {}).get(item.get("rule")) or {}
    try:
        return set(formula.names(rule["check"])) if rule.get("check") else {item.get("measure")} - {None}
    except Exception:                            # a formula that can't be read: its own measurement, at least
        return {item.get("measure")} - {None}


def _cautious_for_unsettled(items, unsettled, rules_by_id=None):
    """A looked-up fact found doubtful, not yet confirmed or changed by the architect: every item whose rule reads a
    measurement worked out from it needs review (coordinator, 2026-10-20: never a false pass)."""
    for key, why in (unsettled or {}).items():
        decides = set(UNSETTLED_DECIDES.get(key) or ())
        for i in items:
            if i["status"] != COMPLIES or not (_formula_names(i, rules_by_id) & decides):
                continue
            i.update(status=REVIEW, mark=MARK[REVIEW], hint="Edit site…",
                     reason=f"Complies on the looked-up {UNSETTLED_NAMES[key]}, which needs review: {why} · "
                            "confirm it (I checked this) or change it in Edit site…")


def _on_context(extras):
    """The left-out objects on the neighbourhood's layers (PR #23: its footprints are editable), said on the row."""
    k = len((extras or {}).get("context_left_out") or [])
    return (f" · {k} on the neighbourhood layers (Gordium::Context): move {'them' if k != 1 else 'it'} to the "
            "Building layer if part of your design") if k else ""


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
    _cautious_for_unsettled(items, facts.get("unsettled"), rules_by_id)
    for i in items:                                  # THE guard: never above the checker's verdict (round 3)
        checker = i.pop("_checker", None)
        if checker is not None and RANK[i["status"]] > RANK[checker]:
            i.update(status=checker, mark=MARK[checker])
    settle(items, values, measured, facts)          # Delta, colours, approx: from each row's readings, last
    for i in items:                                  # a row that needs review always says why (stress F12, F13)
        if i["status"] == REVIEW and not (i.get("reason") or "").strip():
            i["reason"] = ("Needs review: the checker can't settle it from the drawing as it is" +
                           (f" ({i['delta']})" if i.get("delta") else ""))
    for i in items:                                  # waiting on the main building: the row says how to pick it
        if PICK_MAIN_WHY in (i.get("reason") or "") and not i.get("hint"):
            i["hint"] = PICK_MAIN
    if facts.get("ground_assumed") == "flat":                 # on the rows the ground decides (MVP, Ben 2026-10-20)
        for i in items:
            if i.get("measure") in ("building_height", "stories"):
                i["note"] = "assuming flat ground"
    for i in items:                                  # measured from an assumed main building: said on the row
        if (measured.get(i.get("measure")) or {}).get("main_assumed"):
            i["note"] = "; ".join(n for n in (i.get("note"), ASSUMED_MAIN_NOTE) if n)
    for k, (conflict, needs) in enumerate(fact_conflict_rows(facts)):   # facts that disagree (r2 round 5): said
        items.append({"id": f"facts.conflict#{k + 1}", "rule": None, "name": "Lot facts disagree", "group": "site",
                      "status": REVIEW, "mark": MARK[REVIEW], "proposed": "", "required": "", "margin": "", "sign": "",
                      "zoom": None, "measure": None, "objects": [], "points": None,
                      # the same "Enter …" button as a row waiting on these counts, to correct either one
                      "hint": rhino_logic.enter_words(needs), "reason": conflict, "needs": list(needs),
                      "detail": {"line": "", "quotes": [], "citation": "", "links": [], "calc": None,
                                 "scope": _scope(extras, measured), "precision": PRECISION, "at_limit": None}})
    if left_out:
        n = len(left_out)
        items.append({"id": "scope.not_included", "rule": None, "name": "Objects on the lot not included",
                      "group": "building", "status": REVIEW, "mark": MARK[REVIEW], "proposed": str(n), "required": "0",
                      "margin": "", "sign": "", "zoom": "top", "measure": None, "objects": list(left_out),
                      "points": None, "hint": "Add to check…",
                      "ground_like": [o for o in extras.get("ground_like") or [] if o in left_out],
                      "reason": f"{n} object{'s' if n != 1 else ''} on the lot {'aren' if n != 1 else 'isn'}'t "
                                "measured (not on the Building layer) · Add to check…" + _on_context(extras) + (
                                    f" (" + str(len(extras.get("ground_like") or [])) + " looks like the ground: if it is, "
                                    "This is the ground)" if extras.get("ground_like") else ""),
                      "detail": {"line": "", "quotes": [], "citation": "", "links": [], "calc": None,
                                 "scope": _scope(extras, measured), "precision": PRECISION, "at_limit": None}})
    for row in interior:
        rule = rules_by_id[row["Rule id"]]
        needs = row.get("needs") or rhino_logic.needs_of(reading_set.rule_names(rule), values)
        measure = next((c.left.id for c in _compares(rule["check"])), None) if rule.get("check") else None
        items.append({"id": rule["id"], "rule": rule["id"],
                      "name": (NAMES.get(measure) or row.get("Requirement") or rule["id"]) + " · needs input",
                      "group": "not_checked",
                      "status": NOT_CHECKED, "mark": MARK[NOT_CHECKED], "proposed": "", "required": "", "margin": "",
                      "sign": "", "zoom": None, "measure": None, "objects": [], "points": None,
                      "needs": list(needs),               # exactly what its "Enter …" asks for
                      "hint": rhino_logic.enter_words(needs), "reason": rhino_logic.needs_reason(needs),
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
                      "hint": None, "reason": NOT_YET_WHY.format(g["section"]),
                      "detail": {"line": "", "quotes": [], "citation": g["section"], "links": [], "calc": None,
                                 "scope": "", "precision": "", "at_limit": None}})
    for i in items:                                  # the use details still to answer: their own group (never a pass)
        i["use_detail"] = rhino_logic.is_use_detail(i, facts)
    return {"items": items, "summary": summary(items), "state": state(items),
            "header": header(facts, dict(extras, waiting_main=any(
                PICK_MAIN_WHY in (m.get("reason") or "") for m in measured.values()),
                main_assumed=any(m.get("main_assumed") for m in measured.values())), documents, use_names),
            "groups": grouped(items)}


def grouped(items: list[dict]) -> list[dict]:
    """The panel's groups in order (empty ones left out); site items carry "Site · " in their group label."""
    by = {"fails": [], "review": [], "complies": [], "use_details": [], "not_checked": [], "not_covered": []}
    for i in items:
        key = ("not_covered" if i["group"] == "not_covered" else "use_details" if i.get("use_detail") else
               "not_checked" if i["status"] == NOT_CHECKED else
               {FAILS: "fails", REVIEW: "review", COMPLIES: "complies"}[i["status"]])
        by[key].append(i["id"])
    return [{"key": k, "title": t, "items": by[k]} for k, t in GROUPS if by[k]]


def grade_label(facts: dict) -> str:
    """Where the grade comes from, in words: "6 spot grades (finished)", "terrain (finished)", "flat at
    elevation 0'-0"", or "not set"."""
    kind = "existing" if facts.get("grade_is") == "existing" else "finished"
    if facts.get("ground_assumed") == "flat":                 # the MVP's assumption, said wherever the grade is
        if facts.get("ground_fall"):                          # a lookup found the ground: say plainly how it falls
            return (f"assumed flat (the looked-up ground falls about {facts['ground_fall']:g} ft across the lot; "
                    "height is checked as if flat)")
        return f"assumed flat (elevation {feet_inches(facts.get('grade_elevation') or 0)})"   # the team's words
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
    # the ordinance and its date only ("Ord. No. 2026-02 (May 6, 2026)"): the sources' note on what it changed
    # ("PUDs only") read as if the code applied only to PUDs
    amended = re.sub(r"\s*\(([^;)]*)[^)]*\)", r" (\1)", through.group(1)) if through else ""
    code = "Ch. 325" + (f" as amended through {amended}" if through else "") + (
        " · District Regulations Chart, " + re.sub(r".*\((.*)\).*", r"\1", chart["title"]) if chart else "")
    use = facts.get("use") or ""
    lot = ("Lot lines: survey" if facts.get("lot_surveyed") else
           f"Lot lines: tax map, approximate (±{feet_inches(TOLERANCE)})")
    grade = ("Ground: " if facts.get("ground_assumed") == "flat" else "Grade: ") + grade_label(facts)
    actions = (["Pick survey lot lines…"] if not facts.get("lot_surveyed") else []) + (
        ["Set grade…"] if grade_label(facts) == "not set" or facts.get("grade_is") == "existing" else [])
    # several buildings: which one the yards, height and stories are measured to, said, with a way to change it.
    # The checker's word decides it (its measuring asked for a pick), never a count made in Rhino (review round 1)
    main = ("Main building: not picked yet" if extras.get("waiting_main") else
            ASSUMED_MAIN if extras.get("main_assumed") else
            "Main building: " + extras["main_name"] if facts.get("main_building") and extras.get("main_name") else None)
    return {"place": " · ".join(p for p in [facts.get("address") or "", facts.get("zone") or "",
                                            use_names.get(use, use.replace("_", " "))] if p),
            "code": code, "draft": DRAFT, "lot": lot, "grade": grade, "actions": actions, "main": main,
            "sources": source_lines(extras.get("sources") or {})}


SOURCE_NAMES = {"address": "Address", "zone": "Zoning district", "use": "Use", "lot": "Lot", "street": "Front lot line (on the street)",
                "corner_lot": "Corner lot", "ground_marked": "Marked as the ground", "starting_house": "Starting house",
                "ground": "Ground", "dwelling_units": "Dwelling units", "rooms_let_for_profit": "Rooms let for profit",
                "conversion": "Conversion of an existing building"}


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
                                         i.get("delta") or ""] if p)
        return now, f"{i['name']} no longer complies" + (" · " + detail if detail else "")
    return now, f"{len(new)} items no longer comply: " + "; ".join(i["name"] for i in new)   # names hold commas
