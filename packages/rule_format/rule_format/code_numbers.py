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
   accepted, so the edge stays where the law puts it (more than 30 is never 30 or more). A number in arithmetic
   (20 - 4/3 * riser) is checked by value only, and so is one in an if's test, which only picks which limit applies
   ("27 if stair_handrail_sides > 1 else 31.5": where a handrail is on one side), never passes anything itself.
   review_when is checked by value only.
3. A number the verification file flags (a flag quoting it) counts only if the flag resolves it: it gives the
   comparison the second reading has ("(>=)", "the second reading (none) is right") or says the number is part of
   one length ("one length"). Otherwise the rule is refused: such a number is for a person (make it a flag, which
   always needs review).

Plain code, no AI. Used by rulebook validation (every rule citing such a book) and by the drafter's number binding.
"""

import ast
import re
from fractions import Fraction

from . import formula, parts

CONVERSIONS = {"mm", "cm", "m", "rad", "kg"}          # printed in brackets after the US number: never a limit here
OPPOSITE = {"<": ">=", ">": "<=", ">=": "<", "<=": ">"}
MIRROR = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}
OPS = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!="}
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
    return {"shown": " + ".join(m["shown"] for m in members), "values": values, "comparison": first["comparison"],
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


def quote_statements(quote: str) -> set[tuple]:
    """(value, unit) of every number a quote states."""
    from document_extraction.numbers import statements
    return {(value_of(s["value"]), s["unit"]) for s in statements(quote) if value_of(s["value"]) is not None}


def candidates(sources: list[dict], ctx) -> list[dict]:
    """The second-reading numbers a rule may use: those of the pieces its sources sit in that its quotes state."""
    out = []
    for s in sources:
        book = ctx.verification.get(s.get("file")) if isinstance(s, dict) and isinstance(s.get("file"), str) else None
        if not book or not isinstance(s.get("quote"), str):
            continue
        stated = quote_statements(s["quote"])
        for pid in pieces_of(s, book):
            for length in readings(book["pieces"].get(pid) or {}):
                if all(st in stated for st in length["statements"]):
                    out.append(length | {"piece": pid})
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
    allowed = candidates(sources, ctx)
    units = _units(rule, ctx)
    out = []
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
    for number, op, sure, measures in _uses(tree):
        if number == 0:
            continue
        unit_classes = {UNIT_OF.get(units.get(m)) for m in measures} - {None}
        fits = [c for c in allowed if any(_close(v, number) for u, v in c["values"].items()
                                          if not unit_classes or u in unit_classes or u == "any")]
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
        if not directions or op is None:
            continue
        if op in ("==", "!="):
            out.append(f"number {shown} in '{key}' is compared with {op}: a limit of the law is never an equality")
            continue
        reads = {c["comparison"] for c in fits}
        if reads == {"none"}:
            out.append(f"number {shown} in '{key}': the second reading says the law sets no limit with it ('none': a "
                       f"conversion, a count or a permission, {fits[0]['piece']}: {fits[0]['shown']!r}); it can't be compared with")
            continue
        ok = any(c == "between" or op == c or (not sure and op == OPPOSITE.get(c)) for c in reads)
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
                for i, op in enumerate(ops):
                    sign = OPS.get(type(op))
                    a, b = sides[i], sides[i + 1]
                    for side, other, mirrored in ((b, a, False), (a, b, True)):
                        names = {n.id for n in ast.walk(other) if isinstance(n, ast.Name)}
                        for number, direct in _numbers(side):
                            needed = None
                            if sign is not None and direct and not selector:
                                needed = MIRROR.get(sign, sign) if mirrored else sign
                                if not positive:
                                    needed = OPPOSITE.get(needed, {"==": "!=", "!=": "=="}.get(needed))
                            out.append((number, needed, sure and len(ops) == 1, names))
                for side in sides:
                    for n in _conditions(side):              # an if's test inside a side: it picks a limit
                        walk(n, positive, False, True)
            case _:
                for number, _ in _numbers(node):
                    out.append((number, None, False, set()))
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


def _numbers(node) -> list[tuple]:
    """(number, direct) for every number in one side of a comparison: direct when the side is the number itself or an
    if-else choosing between numbers; a constant divided by a constant is one number (four-thirds is 4 / 3)."""
    match node:
        case ast.Constant(value=v) if type(v) in (int, float):
            return [(Fraction(v), True)]
        case ast.UnaryOp(op=ast.USub(), operand=ast.Constant(value=v)) if type(v) in (int, float):
            return [(-Fraction(v), True)]
        case ast.IfExp(body=b, orelse=e):
            return _numbers(b) + _numbers(e)                     # the test is walked as a condition of its own
        case ast.BinOp(left=ast.Constant(value=a), op=ast.Div(), right=ast.Constant(value=b)) \
                if type(a) in (int, float) and type(b) in (int, float) and b:
            return [(Fraction(a) / Fraction(b), False)]
        case ast.BinOp(left=l, right=r):
            return [(n, False) for n, _ in _numbers(l) + _numbers(r)]
        case ast.Call(args=args):
            return [(n, False) for a in args for n, _ in _numbers(a)]
        case ast.Compare() | ast.BoolOp() | ast.UnaryOp(op=ast.Not()):
            return []                                            # a condition inside: walked on its own
    return []


def book_values(quote: str, entry: dict) -> set[float]:
    """Every value a quote of a verified piece backs for the drafter's number binding: its second-reading numbers the
    quote states, in every unit they can stand for (8 1/4 inches: 8.25 and its feet; 6 feet 8 inches: 80)."""
    stated = quote_statements(quote)
    return {float(v) for length in readings(entry) if all(st in stated for st in length["statements"])
            for v in length["values"].values()}
