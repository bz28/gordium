"""The numbers a rule drafted from a building code may use: the second reading's, never the extracted words alone.

A building code book kept outside the repo (New York's Residential Code) has every number of every brought-in piece
read a second time from the page images, and each number's comparison read a third way from the whole printed
sentence (text_verification.yaml; rule_format/state_law.py checks that file). A rule's formula is checked against
those readings, not against the words its quote happens to hold, because the words are what a misreading would get
wrong ("8 1/4" read as "8", a dropped "not"). Egress step 3 (2026-11-13). For each number a rule's formulas use
(0 and true/false aside):

1. It is one of the cited pieces' second-reading numbers, and the cited quote states it (the same value and unit), in
   the unit of the measure it is compared with: 8 1/4 inches is 8.25 for a measure in inches, 6 feet 8 inches is 80
   (a feet number followed by an inches number with no words between is one length), 5.7 square feet is 5.7 for a
   measure in square feet. Millimetres, metres and radians are the book's conversions and back nothing.
2. Its comparison, as the second reading reads it (">=", "<=", ">", "<", "between", "none"), fits how the formula
   uses it. A "none" number is no limit (a conversion, a count, a permission to exceed) and can't be compared with.
   A comparison that must hold for the formula to hold (the whole check or applies_when, a part of an "and" at its
   top, a "not" turned round: "not (x > 8.25)" needs x <= 8.25, with De Morgan followed) must be the law's own:
   `stair_riser_height <= 8.25` for "not more than 8 1/4 inches", never `> 8.25`, which a dropped "not" would give.
   Anywhere else (one side of an "or", an if's test, where the same number can be a trigger written either way:
   "area_well_depth <= 44 or area_well_ladder") the law's comparison or its exact opposite (> for <=, >= for <) is
   accepted, so the edge stays where the law puts it (more than 30 is never 30 or more). A chain (0 <= x < 36) is
   an "and" of its comparisons. A number in arithmetic keeps its direction where it can be told (riser > 8.25 + 0
   is a dropped "not"; x <= 15 - c reads c the other way round), and a term the law reads "none" is allowed only in
   a formula of the law's kind, a measure times a number (the 20 of "20 inches minus four-thirds of the riser"),
   never where a measure is only added or taken away (sphere - 4 > 0 is a limit, refused); where the direction
   can't be told (a divisor, another function) it is checked by value only; inside a formula of the law's kind its
   direction isn't checked either (its numbers are read "none": terms, not limits). Beside a length or an area a
   count's reading never fits, even with a count measure on the same side. Membership (in, not in) is equality
   with each item. A range ("10-inch to 14-inch", read "between" on both) has its lower number read >= and its
   upper <=. A number the walk can't place is reported, never let through. A number in an if's test, which picks which limit applies
   ("27 if stair_handrail_sides > 1 else 31.5": where handrails are on both sides), is checked by value only: a
   test written the wrong way round (">= 1") gives the looser limit to the wrong stairs and passes this check; the
   worked examples and the answer key comparison are what catch it. review_when is checked by value only. But a
   section's number the law names ("Section 9.7, in which case": a decimal in digits, no unit, no limit words, read
   "none") is never a quantity, so it backs no number anywhere: a comparison, an if's test, a term multiplied
   into a formula, review_when (_named_part).
   A reading with limit words of its own ("more than one") is backed only by a quote printing those words before
   it, never by the bare value elsewhere in the quote (_has_words), and a list item's own number in a quote ("1. In
   open parking garages", "this code. 2. In other than Group H") backs no reading at all (_without_list_numbers).
   A count, a degree or a percent backs only a number with no unit of its own (a count, or a coefficient such as
   the 0.5 of "one-half of the floor area"), never a length or an area.
3. A number the verification file flags (a flag quoting it) counts only if the flag resolves it: it gives the
   comparison the second reading has ("(>=)", "the second reading (none) is right") or says the number is part of
   one length ("one length"). Otherwise the rule is refused: such a number is for a person (make it a flag, which
   always needs review). A table cell whose unit is printed only in its column's heading ("(feet)") is a length in
   feet where such a flag says so ("a length in feet": _column_feet), and one whose heading prints "(inches)" a
   length in inches where it says "a length in inches"; otherwise it is a count.
4. A range a table prints joined by a hyphen ("1-500", Table 1006.3.3 of the 2025 Building Code of New York State)
   counts only where a verification flag of its piece names it as "printed range 'A-B'" and the cited quote prints
   it: numbers.py reads no number after a hyphen (so "R-2" is never a number), so without that its upper end is lost.
   Its lower end is read >= and its upper <=, both as counts (_printed_ranges).

Plain code, no AI. Used by rulebook validation (every rule citing such a book) and by the drafter's number binding.
"""

import ast
import re
from fractions import Fraction

from . import formula, parts

CONVERSIONS = {"mm", "cm", "m", "rad", "kg"}          # printed in brackets after the US number: never a limit here
OPPOSITE = {"<": ">=", ">": "<=", ">=": "<", "<=": ">"}
MIRROR = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}
OPS = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=",
       ast.In: "==", ast.NotIn: "!="}                     # membership is equality with each item
UNIT_OF = {"in": "in", "ft": "ft", "sf": "sf", "count": "count"}     # a measure's unit -> the reading's unit class
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
          "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
          "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000, "a": 1}
_PARTS = {"half": 2, "halves": 2, "quarter": 4, "quarters": 4, "third": 3, "thirds": 3, "fourth": 4, "fourths": 4,
          "fifth": 5, "fifths": 5, "sixth": 6, "sixths": 6, "eighth": 8, "eighths": 8}


def value_of(text: str) -> Fraction | None:
    """A number as numbers.py writes it ("8 1/4", "3/8", "5.7", "1,000", "four", "twenty-one", "one-half",
    "one and one third"), exactly; None if it isn't one."""
    t = text.strip().lower().replace(",", "")
    try:
        if m := re.fullmatch(r"(\d+)[ -](\d+)/(\d+)", t):
            return int(m[1]) + Fraction(int(m[2]), int(m[3]))
        if re.fullmatch(r"\d+/\d+|\d+(?:\.\d+)?|\.\d+", t):
            return Fraction(t)
    except (ValueError, ZeroDivisionError):
        return None
    if m := re.fullmatch(r"(\w+) and (\w+)[- ](\w+)", t):          # "one and one third"
        whole, part = _WORDS.get(m[1]), _part(m[2], m[3])
        return whole + part if whole is not None and part is not None else None
    if m := re.fullmatch(r"(\w+)[- ](\w+)", t):
        if m[2] in _PARTS:
            return _part(m[1], m[2])
        if m[1] in _WORDS and m[2] in _WORDS and _WORDS[m[2]] < 10:      # "twenty-one"
            return Fraction(_WORDS[m[1]] + _WORDS[m[2]])
    if t in _PARTS:                                                      # "half" alone
        return Fraction(1, _PARTS[t])
    return Fraction(_WORDS[t]) if t in _WORDS else None


def _part(count: str, part: str) -> Fraction | None:
    n = _WORDS.get(count)
    return None if n is None or part not in _PARTS else Fraction(n, _PARTS[part])


def readings(entry: dict) -> list[dict]:
    """A piece's second-reading numbers (text_verification.yaml), each with its value in every unit it can stand for,
    its comparison as the second reading reads it, and whether a flag quotes it and resolves it."""
    from document_extraction.numbers import statements
    if not isinstance(entry, dict):
        return []                        # a malformed entry: state_law.verification_problems says why
    shown = [s for s in entry.get("second_reading_numbers") or [] if isinstance(s, str)]
    comps = entry.get("second_reading_comparisons") or []
    flags = [str(f) for f in entry.get("flags") or []]
    out = []
    for i, s in enumerate(shown):
        st = statements(s)
        st = st[0] if len(st) == 1 else None
        value = value_of(st["value"]) if st else None
        comp = comps[i] if i < len(comps) else "none"
        flag = next((f for f in flags if f"'{s}'" in f), None)
        out.append({"shown": s, "value": value, "unit": (st or {}).get("unit", ""), "comparison": comp,
                    "flag": flag, "resolved": flag is None or _resolves(flag, comp), "index": i})
    lengths = []
    for i, r in enumerate(out):
        if r["value"] is None or r["unit"] in CONVERSIONS:
            continue
        if r["unit"] == "foot":
            nxt = out[i + 1] if i + 1 < len(out) else None
            if nxt and nxt["unit"] == "inch" and nxt["value"] is not None and _plain_number(nxt["shown"]):
                whole = r["value"] * 12 + nxt["value"]       # "6 feet 8 inches": one length
                lengths.append(_length(r, {"in": whole, "ft": whole / 12}, members=[r, nxt]))
                continue
            lengths.append(_length(r, {"ft": r["value"], "in": r["value"] * 12}))
        elif r["unit"] == "inch":
            if i > 0 and out[i - 1]["unit"] == "foot" and _plain_number(r["shown"]):
                continue                                      # the inches of a feet-and-inches length (above)
            lengths.append(_length(r, {"in": r["value"], "ft": r["value"] / 12}))
        elif r["unit"] == "square foot":
            lengths.append(_length(r, {"sf": r["value"]}))
        elif r["unit"] == "percent":
            lengths.append(_length(r, {"count": r["value"] / 100, "any": r["value"] / 100}))
        else:                                                 # a count ("four risers", "one side"), degrees, units
            lengths.append(_length(r, {"count": r["value"], "any": r["value"]}))
    return lengths


def _plain_number(shown: str) -> bool:
    """A number with no words of its own before it (the "8 inch" of "6 feet 8 inches")."""
    from document_extraction.numbers import statements
    st = statements(shown)
    return len(st) == 1 and not st[0]["before"]


def _length(first: dict, values: dict, members=None) -> dict:
    members = members or [first]
    from document_extraction.numbers import statements
    words = statements(first["shown"])
    worded = (" ".join(words[0]["before"].lower().split()), first["value"], first["unit"]) if len(words) == 1 else None
    return {"shown": " + ".join(m["shown"] for m in members), "values": values, "comparison": first["comparison"],
            "worded": worded,
            "unit": first["unit"], "statements": [(m["value"], m["unit"]) for m in members],
            "flags": [m["flag"] for m in members if m["flag"]],
            "resolved": all(m["resolved"] for m in members) or (len(members) > 1 and all(
                m["resolved"] or "one length" in (m["flag"] or "") for m in members))}


def _resolves(flag: str, comparison: str) -> bool:
    """A flag resolves its number when it says which reading is right and that is the second reading's comparison:
    it gives that comparison in brackets ("at least 5 square feet (>=)"), says the second reading is right with it
    ("so the second reading (none) is right"), or says the number is part of one length."""
    return (f"({comparison})" in flag and (comparison != "none" or "second reading (none) is right" in flag)) \
        or "one length" in flag


def _worded_statements(quote: str) -> set[tuple]:
    """(the words before it, value, unit) of every number a quote states, as the reading's own words are matched."""
    from document_extraction.numbers import statements
    return {(" ".join(s["before"].lower().split()), value_of(s["value"]), s["unit"])
            for s in statements(_without_list_numbers(quote)) if value_of(s["value"]) is not None}


def _has_words(length: dict) -> bool:
    """A reading with limit words of its own ("more than one", "not less than 36"): a quote backs it only where it
    prints the same words before it, never by the bare value (1017.3's "more than one" was backed by "Exceptions:
    1. In open parking garages", a list item's number)."""
    return bool(length.get("worded") and length["worded"][0])


def _named_part(fits: list[dict]) -> bool:
    """Every reading a number fits is a decimal printed in digits with no unit or limit words of its own, read
    "none": the number of a section the law names ("Section 9.7, in which case", "Section 1004.1. In each story"),
    never a quantity, so no formula may use it anywhere. A section is never numbered 0.x, so a fraction such as the
    0.5 of a coefficient is left to the checks below."""
    return bool(fits) and all(c["comparison"] == "none" and not c.get("unit") and not (c.get("worded") or ("",))[0]
                              and re.fullmatch(r"[1-9]\d*\.\d+", c["shown"].strip()) for c in fits)


def quote_statements(quote: str) -> set[tuple]:
    """(value, unit) of every number a quote states."""
    from document_extraction.numbers import statements
    return {(value_of(s["value"]), s["unit"]) for s in statements(_without_list_numbers(quote))
            if value_of(s["value"]) is not None}


# A list item's own number inside a quote: after the start, a stop, a colon or a semicolon, and followed by a stop
# and a capital ("Exceptions: 1. In open parking garages", "this code. 2. In other than Group H", "3.1. Where")
LIST_NUMBER = re.compile(r"(^|[.:;]\s+)\d+(?:\.\d+)*\.\s+(?=[A-Z\[])")


def _without_list_numbers(quote: str) -> str:
    """The quote with each list item's own number left out: it numbers an item, never a quantity, so it backs no
    reading ("2. In other than Group H" once backed 1016.2's "two or more"). A number ending a sentence after a word
    ("not more than 2. Where") is a quantity, and stays."""
    return LIST_NUMBER.sub(lambda m: m[1], quote)


def unverified_reading(entry: dict) -> dict:
    """A piece of a book not verified (text_verification `not_verified`: no second reading was ever made), read the
    only way it can be: its numbers as the extracted text has them, with the comparison its recorded words give
    (numbers.comparisons). For a flag's drafted check only, which never decides a result: it keeps the drafted
    formula on the book's printed numbers (an OCR misreading included, until a bought copy is checked)."""
    from document_extraction.numbers import comparisons
    numbers = [n for n in (entry.get("numbers") or []) if isinstance(n, str)] if isinstance(entry, dict) else []
    return {"second_reading_numbers": numbers, "second_reading_comparisons": comparisons(numbers)}


def candidates(sources: list[dict], ctx, flag: bool = False) -> list[dict]:
    """The second-reading numbers a rule may use: those of the pieces its sources sit in that its quotes state. A
    book not verified has none for a rule; for a flag (flag=True), its extracted text's numbers (unverified_reading)."""
    out = []
    for s in sources:
        book = ctx.verification.get(s.get("file")) if isinstance(s, dict) and isinstance(s.get("file"), str) else None
        if not book or not isinstance(s.get("quote"), str):
            continue
        if book.get("not_verified") and not flag:
            continue                          # never read a second time: backs no number of a rule
        stated = quote_statements(s["quote"])
        worded = _worded_statements(s["quote"])
        for pid in pieces_of(s, book):
            entry = book["pieces"].get(pid) or {}
            lengths = _between_ends(readings(unverified_reading(entry) if book.get("not_verified") else entry))
            if book.get("not_verified"):          # a flag's drafted check: no second reading says more than this
                lengths = [_unverified(length) for length in lengths]
            lengths = [_in_feet(length, s["quote"]) for length in lengths]
            if not book.get("not_verified"):
                lengths = [_column_feet(length) for length in lengths]
            # a value the piece reads more than one way (R320.2: "not less than 34" and, for ship's ladders, "not
            # more than 34"): a reading counts only where the quote states it with the same words before it
            ways: dict = {}
            for length in lengths:
                ways.setdefault(tuple(length["statements"]), set()).add(length["comparison"])
            for length in lengths:
                if not all(st in stated for st in length["statements"]):
                    continue
                if (len(ways[tuple(length["statements"])]) > 1 or _has_words(length)) \
                        and length["worded"] not in worded:
                    continue
                out.append(length | {"piece": pid})
            if not book.get("not_verified"):
                out += [r | {"piece": pid} for r in _printed_ranges(entry, s["quote"])]
    return out


PRINTED_RANGE = re.compile(r"printed range '(\d[\d,]*)-(\d[\d,]*)'")


def _printed_ranges(entry: dict, quote: str) -> list[dict]:
    """A range a table prints joined by a hyphen ("1-500": Table 1006.3.3 of the 2025 Building Code of New York
    State): numbers.py reads no number after a hyphen (so "R-2" and "I-4" are never numbers), so it loses the range's
    upper end. A flag of the second reading that names it ("printed range '1-500'", read on the page image and by
    position) makes both ends numbers a rule may use, where the cited quote prints that range: the lower an at-least
    (>=), the upper an at-most (<=), counts with no unit."""
    out = []
    flags = [str(f) for f in (entry.get("flags") or [])] if isinstance(entry, dict) else []
    for f in flags:
        for m in PRINTED_RANGE.finditer(f):
            printed = f"{m[1]}-{m[2]}"
            if not re.search(rf"(?<![\w.,\-]){re.escape(printed)}(?![\w,\-])", quote):
                continue
            for text, comparison in ((m[1], ">="), (m[2], "<=")):
                v = value_of(text)
                if v is None:
                    continue
                out.append({"shown": text, "values": {"count": v, "any": v}, "comparison": comparison,
                            "worded": None, "unit": "", "statements": [(v, "")], "flags": [f], "resolved": True})
    return out


def _in_feet(length: dict, quote: str) -> dict:
    """A number the quote prints in feet as "ft" (NFPA 101: "shall not exceed 100 ft (30 m)"): numbers.py reads no
    unit from "ft" (its readings, and the recorded second reading, have none), so the quote's own "ft" right after
    the same number says it is a length in feet. Only a number with no unit of its own, only where the quote prints
    it so; its comparison stays the second reading's."""
    if not set(length["values"]) <= {"count", "any"} or len(length["statements"]) != 1:
        return length
    value = length["statements"][0][0]
    printed = re.findall(r"(?<![\w.,/])(\d[\d,]*(?:\.\d+)?)\s*ft\b", quote.lower())
    if not any(value_of(n) == value for n in printed):
        return length
    return dict(length, values=dict(length["values"], ft=value, **{"in": value * 12}))


COLUMN_FEET = "a length in feet"     # a verification flag's words for a table cell whose column heading prints "(feet)"
COLUMN_INCHES = "a length in inches"  # ... and for one whose heading prints "(inches)" (Table 1020.3, section group 4)


def _column_feet(length: dict) -> dict:
    """A table cell prints its unit in its column's heading ("(feet)": Tables 1006.2.1 and 1017.2 of the 2025 Building
    Code of New York State; "(inches)": Table 1020.3), never beside the number, so numbers.py reads it with no unit.
    A flag of the second reading quoting the number that says it is "a length in feet" (or "a length in inches")
    (its column read by position and on the page image: text_verification.yaml) makes it one. Only a number with no
    unit of its own, and only by such a flag: another table's cells (an occupant load) stay counts. Its comparison
    stays the second reading's."""
    if not set(length["values"]) <= {"count", "any"} or len(length["statements"]) != 1:
        return length
    value = length["statements"][0][0]
    if any(COLUMN_FEET in f for f in length["flags"]):
        return dict(length, values=dict(length["values"], ft=value, **{"in": value * 12}))
    if any(COLUMN_INCHES in f for f in length["flags"]):
        return dict(length, values=dict(length["values"], ft=value / 12, **{"in": value}))
    return length


def _unverified(length: dict) -> dict:
    """A number of a book not verified, for a flag's drafted check (which never decides a result). With no second
    reading, nothing but the printed text says what it is: a table cell prints its unit in its column's heading
    ("(feet)", Table 1016.1), never beside the number, so a number with no unit of its own may stand for a length or
    an area; and where the recorded words give no comparison ("none": every table cell) its direction is not checked.
    The value must still be printed in a cited piece and stated in the quote, and the examples' drafted_check prove
    the drafted formula's direction against worked values."""
    out = dict(length, unverified=True)
    if set(length["values"]) <= {"count", "any"}:
        v = length["values"].get("any", length["values"].get("count"))
        out["values"] = dict(length["values"], ft=v, sf=v, **{"in": v})
    return out


def _between_ends(lengths: list[dict]) -> list[dict]:
    """A range ("10-inch to 14-inch") is read "between" on both its numbers, in order: the lower one is an at-least
    (>=) and the upper an at-most (<=), so each is checked the law's way. A "between" number with no partner stays
    "between", which no comparison fits."""
    out, pending = [], None
    for length in lengths:
        if length["comparison"] != "between":
            out.append(length)
            continue
        if pending is None:
            pending = length
            continue
        lo, hi = sorted((pending, length), key=lambda x: min(x["values"].values()))
        out += [lo | {"comparison": ">="}, hi | {"comparison": "<="}]
        pending = None
    if pending is not None:
        out.append(pending)
    return out


def pieces_of(source: dict, book: dict) -> list[str]:
    """The pieces a source's lines sit in (a quote of one piece sits in one)."""
    page, lines = source.get("page"), source.get("lines")
    if not (type(page) is int and isinstance(lines, list) and len(lines) == 2 and all(type(n) is int for n in lines)):
        return []
    return [pid for pid, segments in book["lines"].items()
            if any(p == page and a <= lines[0] and lines[1] <= b for p, a, b in segments)]


def cites_book(sources: list[dict], ctx) -> bool:
    """Whether a rule cites a book whose numbers were read twice (a badly shaped source cites nothing: its own check
    says why)."""
    return any(isinstance(s, dict) and isinstance(s.get("file"), str) and s["file"] in getattr(ctx, "verification", {})
               for s in sources or [] if isinstance(sources, list))


def problems(rule: dict, sources: list[dict], ctx) -> list[str]:
    """Every number a rule citing a verified book uses must be a second-reading number of a cited piece, stated in
    the quote, in the measure's unit, used the way the law reads it (module docstring). [] if all are."""
    flag = rule.get("kind") == "flag"
    allowed = candidates(sources, ctx, flag=flag)
    units = _units(rule, ctx)
    out = []
    unverified = sorted({s["file"] for s in sources if isinstance(s, dict) and isinstance(s.get("file"), str)
                         and (ctx.verification.get(s["file"]) or {}).get("not_verified")})
    if unverified and not flag:
        out.append(f"cites {', '.join(unverified)}, whose numbers were never read a second time (not_verified in its "
                   "text_verification file): a rule may not stand on them; make it a flag (always needs review), "
                   "its check kept as the drafted test")
    for key in ("applies_when", "check"):
        if isinstance(rule.get(key), str):
            out += _formula_problems(rule[key], key, allowed, units, directions=True)
    for r in rule.get("review_when") or []:
        if isinstance(r, dict) and isinstance(r.get("when"), str):
            out += _formula_problems(r["when"], "review_when", allowed, units, directions=False)
    return list(dict.fromkeys(out))


def _units(rule: dict, ctx) -> dict:
    """Each measure name's unit (measures.yaml, the proposed measures, and the rule's part kind in parts.yaml)."""
    from .rulebook import MEASURES_FILE, load
    units = {n: m.get("unit") for n, m in (load(MEASURES_FILE) or {}).items() if isinstance(m, dict)}
    units |= {n: m.get("unit") for n, m in (getattr(ctx, "proposed", {}) or {}).items() if isinstance(m, dict)}
    try:
        kind = parts.registry().get(rule.get("for_each")) if isinstance(rule.get("for_each"), str) else None
    except (ValueError, OSError):
        kind = None
    units |= {n: d["unit"] for n, d in ((kind or {}).get("measures") or {}).items()}
    return units


def _formula_problems(text: str, key: str, allowed: list[dict], units: dict, directions: bool) -> list[str]:
    try:
        tree = formula.parse(text).body
    except formula.FormulaError:
        return []                                             # reported with the formula
    out = []
    uses = _uses(tree)
    seen = {u[0] for u in uses}
    parts_of_one = {id(x) for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)
                    and isinstance(n.left, ast.Constant) and isinstance(n.right, ast.Constant) for x in (n.left, n.right)}
    for node in ast.walk(tree):
        if id(node) not in parts_of_one and isinstance(node, ast.Constant) and type(node.value) in (int, float) and node.value != 0 \
                and Fraction(node.value) not in seen and -Fraction(node.value) not in seen \
                and not any(_close(Fraction(node.value), n) for n in seen):
            out.append(f"number {float(node.value):g} in '{key}' sits where the number check can't read it "
                       "(write it as a comparison of a measure with the law's number)")
    for number, op, sure, measures, in_formula, rate in uses:
        if number == 0:
            continue
        unit_classes = {UNIT_OF.get(units.get(m)) for m in measures} - {None}
        if rate and rate[0] and {UNIT_OF.get(units.get(m)) for m in rate[0]} == {"count"}:
            # a rate: counts times it give the length it is compared with (inches per occupant)
            unit_classes = {UNIT_OF.get(units.get(m)) for m in rate[1]} & {"in", "ft", "sf"}
        # a count, a degree or a percent ("any") backs a number with no unit of its own (a coefficient, a count),
        # never a length or an area
        length = bool(unit_classes & {"in", "ft", "sf"})
        fits = [c for c in allowed if any(_close(v, number) for u, v in c["values"].items()
                                          if (u in unit_classes and not (length and u == "count"))
                                          or (u == "any" and unit_classes <= {"count"}))]
        shown = f"{float(number):g}"
        if not fits:
            out.append(f"number {shown} in '{key}' isn't one of the second-reading numbers (text_verification.yaml) "
                       f"of the pieces its quotes cite, stated in those quotes"
                       + (f", in {'/'.join(sorted(unit_classes))}" if unit_classes else ""))
            continue
        if not any(c["resolved"] for c in fits):
            out.append(f"number {shown} in '{key}': the second reading flags it ({fits[0]['flags'][0][:120]!r}) and "
                       "the flag doesn't resolve it: a person decides (make the rule a flag, which needs review)")
            continue
        fits = [c for c in fits if c["resolved"]]
        if _named_part(fits) and not all(c.get("unverified") for c in fits):   # anywhere: a test, a term, review_when
            out.append(f"number {shown} in '{key}' is the number of a section the law names ({fits[0]['piece']}: "
                       f"{fits[0]['shown']!r}), never a quantity: no formula may use it (a test, a term of a "
                       "formula, review_when)")
            continue
        if not directions or op is None:
            continue
        if op in ("==", "!="):
            out.append(f"number {shown} in '{key}' is compared with {op}: a limit of the law is never an equality "
                       "(a measured length never equals a number or a formula exactly; where the law sets a formula, "
                       "check it within a tolerance it states, or make the rule a flag)")
            continue
        reads = {c["comparison"] for c in fits}
        if reads == {"none"} and in_formula:
            continue                                          # a term of the law's formula (20 inches minus ...)
        if reads == {"none"} and all(c.get("unverified") for c in fits):
            continue                                          # no reading says its direction (_unverified)
        if reads == {"none"}:
            out.append(f"number {shown} in '{key}': the second reading says the law sets no limit with it ('none': a "
                       f"conversion, a count or a permission, {fits[0]['piece']}: {fits[0]['shown']!r}); it can't be compared with")
            continue
        ok = any(op == c or (not sure and op == OPPOSITE.get(c)) for c in reads)
        if not ok:
            law = " or ".join(sorted(reads - {"none"}))
            where = "where it must hold for the formula to hold" if sure else "here"
            out.append(f"number {shown} in '{key}' needs {op} {shown} to hold, but the law reads {law} {shown} "
                       f"({fits[0]['piece']}: {fits[0]['shown']!r}, the second reading); {where} it must be "
                       + ("the law's own comparison" if sure else "the law's comparison or its exact opposite"))
    return out


def _close(a: Fraction, b: Fraction) -> bool:
    return abs(Fraction(a) - Fraction(b)) <= Fraction(1, 10 ** 6)


def _uses(tree) -> list[tuple]:
    """(number, its comparison as the formula needs it to hold, with the number on the right, or None in arithmetic;
    whether that comparison must hold for the whole formula to hold; the measure names on the other side) for every
    number in a formula. A comparison under a "not" is turned round ("not (x > 8.25)" needs x <= 8.25), and De Morgan
    is followed: under a "not", an "or" works as an "and" (both parts must fail) and an "and" as an "or"."""
    out = []

    def walk(node, positive, sure, selector=False):
        match node:
            case ast.BoolOp(op=op, values=vs):
                both = isinstance(op, ast.And) == positive      # every part must go the formula's way
                for v in vs:
                    walk(v, positive, sure and both, selector)
            case ast.UnaryOp(op=ast.Not(), operand=x):
                walk(x, not positive, sure, selector)
            case ast.IfExp(test=t, body=b, orelse=e):
                walk(t, positive, False, True)                   # it only picks which limit applies
                walk(b, positive, sure, selector)
                walk(e, positive, sure, selector)
            case ast.Compare(left=left, ops=ops, comparators=rights):
                sides = [left, *rights]
                # a chain (a < x < b) holds when each of its comparisons does, as an "and": under a "not", as an "or"
                pair_sure = sure if len(ops) == 1 else sure and positive
                for i, op in enumerate(ops):
                    sign = OPS.get(type(op))
                    a, b = sides[i], sides[i + 1]
                    for side, other, mirrored in ((b, a, False), (a, b, True)):
                        # the measures it is compared with: the other side's, and its own side's (8.25 - riser < 0)
                        # (an if's test inside a side only picks a limit: its measures say nothing of the unit)
                        names = _compared_names(other) | _compared_names(side)
                        for number, grows, coefficient in _numbers(side):
                            needed = None
                            if sign in ("==", "!=") and not selector:
                                needed = sign                # an equality, even with arithmetic: never a limit
                            elif sign is not None and grows is not None and not selector:
                                needed = MIRROR.get(sign, sign) if mirrored else sign
                                if grows < 0:                # x <= 15 - c holds as c grows smaller: c is read c <= ...
                                    needed = MIRROR[needed]
                                if not positive:
                                    needed = OPPOSITE.get(needed, {"==": "!=", "!=": "=="}.get(needed))
                            # a coefficient (0.5 * floor area) has no unit of its own; one that multiplies counts
                            # only and is compared with a length is a rate, in that length's unit (1005.3.2: 0.2
                            # inch per occupant): the side's and the other side's measures, for _formula_problems
                            rate = (frozenset(_compared_names(side)), frozenset(_compared_names(other))) \
                                if coefficient else None
                            out.append((number, needed, pair_sure, set() if coefficient else names, _formula(side),
                                        rate))
                for side in sides:
                    for n in _conditions(side):              # an if's test inside a side: it picks a limit
                        walk(n, positive, False, True)
            case _:
                for number, _, _ in _numbers(node):
                    out.append((number, None, False, set(), True, None))
                for n in _conditions(node):
                    walk(n, positive, False, True)

    walk(tree, True, True)
    return out


def _conditions(node) -> list:
    """The outermost conditions inside an expression (an if's test inside a side of a comparison)."""
    found = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.Compare, ast.BoolOp)) or (isinstance(child, ast.UnaryOp) and isinstance(child.op, ast.Not)):
            found.append(child)
        else:
            found += _conditions(child)
    return found


def _numbers(node, grows=1, coefficient=False) -> list[tuple]:
    """(number, how the side moves as the number grows: +1, -1 or None when that can't be told, whether it multiplies a
    measure: a coefficient) for every number in one side of a comparison. A number standing alone, or as a branch of an
    if-else, grows +1; a number divided by a number is one number (four-thirds is 4 / 3); each number of other
    arithmetic is its own (8.25 + 0: 8.25, which grows the side as a limit standing alone would). Through
    + and - and through multiplying or dividing by a measure or a positive number the direction is followed (measures
    are never negative); through anything else (a divisor, a call other than min or max) it can't be told."""
    match node:
        case ast.Constant(value=v) if type(v) in (int, float):
            return [(Fraction(v), grows, coefficient)]
        case ast.BinOp(left=ast.Constant(value=a), op=ast.Div(), right=ast.Constant(value=b)) \
                if type(a) in (int, float) and type(b) in (int, float) and b:
            return [(Fraction(a) / Fraction(b), grows, coefficient)]        # four-thirds: one number
        case ast.IfExp(body=b, orelse=e):
            return _numbers(b, grows, coefficient) + _numbers(e, grows, coefficient)   # the test is walked apart
        case ast.UnaryOp(op=ast.USub(), operand=x):
            return _numbers(x, _flip(grows), coefficient)
        case ast.BinOp(left=l, op=ast.Add(), right=r):
            return _numbers(l, grows, coefficient) + _numbers(r, grows, coefficient)
        case ast.BinOp(left=l, op=ast.Sub(), right=r):
            return _numbers(l, grows, coefficient) + _numbers(r, _flip(grows), coefficient)
        case ast.BinOp(left=l, op=ast.Mult(), right=r):
            return (_numbers(l, _times(grows, r), coefficient or _has_name(r))
                    + _numbers(r, _times(grows, l), coefficient or _has_name(l)))
        case ast.BinOp(left=l, op=ast.Div(), right=r):
            return _numbers(l, _times(grows, r), coefficient or _has_name(r)) + _numbers(r, None, True)
        case ast.BinOp(left=l, right=r):
            return _numbers(l, None, coefficient) + _numbers(r, None, coefficient)
        case ast.Call(func=ast.Name(id=f), args=args):
            return [n for a in args for n in _numbers(a, grows if f in ("min", "max") else None, coefficient)]
        case ast.List(elts=items) | ast.Tuple(elts=items) | ast.Set(elts=items):
            return [n for x in items for n in _numbers(x, grows, coefficient)]
        case ast.Compare() | ast.BoolOp() | ast.UnaryOp(op=ast.Not()):
            return []                                            # a condition inside: walked on its own
    return []


def _fold(node) -> Fraction | None:
    """The value of arithmetic of numbers only (no measure in it), or None."""
    match node:
        case ast.Constant(value=v) if type(v) in (int, float):
            return Fraction(v)
        case ast.UnaryOp(op=ast.USub(), operand=x):
            v = _fold(x)
            return None if v is None else -v
        case ast.BinOp(left=l, op=op, right=r):
            a, b = _fold(l), _fold(r)
            if a is None or b is None:
                return None
            match op:
                case ast.Add():
                    return a + b
                case ast.Sub():
                    return a - b
                case ast.Mult():
                    return a * b
                case ast.Div() if b:
                    return a / b
    return None


def _formula(side) -> bool:
    """A side that is a formula of the law's kind: a measure multiplied or divided by a number (20 - 4/3 * riser), where
    a number read "none" is a term, not a limit. A number with a measure only added or taken away (sphere - 4 > 0) is
    still a limit and is refused as one."""
    def scaled(n):                  # a measure times (or over) a number that isn't 0: 4/3 * riser, never 0 * riser
        if not (isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Mult, ast.Div))):
            return False
        for a, b in ((n.left, n.right), (n.right, n.left)):
            v = _fold(a)
            if v is not None and v != 0 and _has_name(b):
                return True
        return False
    return any(scaled(n) for n in ast.walk(side))


def _compared_names(node) -> set[str]:
    """The measure names in an expression, leaving out those inside a condition (an if's test) and function names."""
    if isinstance(node, (ast.Compare, ast.BoolOp)) or (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)):
        return set()
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Call):
        return {n for a in node.args for n in _compared_names(a)}
    return {n for c in ast.iter_child_nodes(node) for n in _compared_names(c)}


def _flip(grows):
    return None if grows is None else -grows


def _times(grows, other):
    """How a product moves with one factor: as the factor does when the other is a measure or a positive number."""
    v = _fold(other)
    if v is not None:
        return grows if v > 0 else _flip(grows) if v < 0 else None
    return grows if _has_name(other) and not _numbers_only_negative(other) else None


def _has_name(node) -> bool:
    return any(isinstance(n, ast.Name) for n in ast.walk(node))


def _numbers_only_negative(node) -> bool:
    """A factor that could be negative although it names a measure (a difference, a negation): direction unknown."""
    return any(isinstance(n, (ast.UnaryOp, ast.BinOp)) and isinstance(getattr(n, "op", None), (ast.USub, ast.Sub))
               for n in ast.walk(node))


def book_values(quote: str, entry: dict) -> set[float]:
    """Every value a quote of a verified piece backs for the drafter's number binding: its second-reading numbers the
    quote states, in every unit they can stand for (8 1/4 inches: 8.25 and its feet; 6 feet 8 inches: 80)."""
    stated = quote_statements(quote)
    return {float(v) for length in readings(entry) if all(st in stated for st in length["statements"])
            for v in length["values"].values()}
