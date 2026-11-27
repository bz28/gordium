"""What the results panel needs beyond a row's words (docs/revit/ui_design_pass.md section 4, PR 5): each
needs-review row's causes as data, how far off as words, a ratio rule's limit as a length, and each quote's source.

Presentation only, plain code, no AI: nothing here reads or changes a status (a row's verdict is parts.rows' or the
checker's), and every figure is one the measuring or the rule gave, worked one way only and rounded so it is never
kinder than the figures (room to spare rounds down; a certain shortfall is never overstated as room).

New fields on an item (each optional; a host that doesn't know them ignores them):

  causes      [{kind, key, words, elements, rooms?, field?, fields?}] for a needs-review row, the first the one to act
              on first.
              kind: "mark" (a fact or a mark the architect states), "fix_model" (the model or its marks, as the
              cause's words say), "measure_by_hand" (Gordium doesn't read or measure this yet), "decide" (a person
              decides: a flag rule, an open question, a reading to confirm). key: rows sharing a key share the cause
              (one card, one job). elements: the element ids the cause names (the rooms with no route). field: on a
              mark, the description field it needs the architect to state ("doors[].exit", "openings[].escape",
              "rooms[].sleeping", "stairs", "facts.zone"), so a host names its own mark (Revit's Gordium: Exit door
              feeds doors[].exit); fields: every one, when it needs several facts. No field where the description
              has none for it yet (a mark Gordium doesn't have) or the cause is a pick, never a field guessed.
  how_far     how far off, in words that always carry their direction ("2.5 ft short", "1.2 ft over",
              "116.16 ft to spare if confirmed", "at the limit"), never a bare signed number; over several readings,
              what is true whichever is right ("at least …", "up to …").
  (The rebuilt pane reads each row's `asks` instead: one per clause, each with its kind and a headline, the
  causes' words as its why; ui_data.py, docs/revit/checker_ui_data.md. These fields stay as they are.)
  limit_length  for a rule whose limit is a ratio of two lengths (IBC 1015.2.1's 1/3 of the diagonal): the two
              lengths and the limit as a length, {measure, measured, limit, of, unit, words}.
"""

import ast
import math
import re

from rule_format import formula, parts
from rule_format.rulebook import _kinds

from design_checker import present

MARK, FIX_MODEL, BY_HAND, DECIDE = "mark", "fix_model", "measure_by_hand", "decide"
KINDS = (MARK, FIX_MODEL, BY_HAND, DECIDE)
UNIT_WORDS = {"ft": "ft", "in": "in", "sf": "sq ft"}
# a ratio of two lengths the measuring gives beside the ratio (`more`): the measure, its numerator and denominator
# keys, and how the row says them. Only where the ratio is exactly their quotient (checked) is a length worked out.
RATIO_LENGTHS = {"exit_remoteness_ratio": ("nearest_edges", "diagonal", "exits {measured} apart",
                                           "of the {of} diagonal")}
FLAG_WORDS = "a flag rule: a person decides, even once it is measured"
REVIEW_WHEN_WORDS = "the law asks a person to decide here (its review condition holds)"
NO_ROUTE = ("no_route", "no_route_host_blocked", "no_route_via_host", "no_exit_access")
OUTCOME_STATUS = {"pass": present.COMPLIES, "fail": present.FAILS, "needs_review": present.REVIEW}
STEP = 0.01                      # the step a how-far is shown in, in its unit
# a reason that asks for a mark says so in the word itself ("mark", "marks", "marked", "unmarked"), never inside a
# room's name or a value a reason quotes ("Supermarket", "Landmark hall", a function "market": group 3 review round 8)
MARK_WORD = re.compile(r"\b(un)?mark(s|ed)?\b")
# a part's measure the description's own field states, as a host's mark gives it (never one measured): its cause is
# a mark, naming that field, so the host's card opens its mark (the door-type mark Gordium: Leaves; before it the
# reason said "no mark for it in the model yet", a dead end in Revit)
MEASURE_FIELDS = {"moe_door_leaves": "doors[].leaves"}


# ---- how far off ------------------------------------------------------------------------------------------------


def _floor(x: float) -> float:
    return math.floor(x / STEP + 1e-9) * STEP


def _ceil(x: float) -> float:
    return math.ceil(x / STEP - 1e-9) * STEP


def _amount(x: float, unit: str) -> str:
    text = f"{x:,.2f}".rstrip("0").rstrip(".")
    return f"{text} {UNIT_WORDS.get(unit, unit)}".rstrip() if unit else text


def how_far_words(status: str, margins: list[float], unit: str, maximum: bool) -> str | None:
    """How far off, from the margin under each reading (room to spare positive), in words with their direction:
    `maximum`: the rule is a most (≤, <), so a shortfall is "over"; else "short". Never overstated: room rounds
    down (the least over the readings), "at least" short rounds down, "up to" and one reading's shortfall round up
    (as zoning's delta, present.delta_words). Never kinder than the status: room on a row in review says "if
    confirmed", on a row that fails another way "room here; see why"; a shortfall on a row not failing says "see
    why"."""
    if not margins or any(not isinstance(m, (int, float)) or m != m or abs(m) == math.inf for m in margins):
        return None
    gap = "over" if maximum else "short"
    low, high = min(margins), max(margins)
    one = low == high
    if low >= 0:
        room = _floor(low)
        if room <= 0:
            words = "at the limit" if one else "at the limit at worst"
        else:
            words = ("" if one else "at least ") + _amount(room, unit) + " to spare"
        if status == present.REVIEW:
            return words + " if confirmed"
        if status == present.FAILS:
            return words.replace(" to spare", "") + " room here; see why" if room > 0 else words + " here; see why"
        return words
    if high < 0:
        if one:
            words = _amount(max(_ceil(-high), STEP), unit) + " " + gap
        elif _floor(-high) <= 0:     # the least shortfall rounds to nothing, another may be far more: the
            words = f"{gap} under every reading"          # direction alone, never "less than 0.01 short"
        else:
            words = "at least " + _amount(_floor(-high), unit) + " " + gap
        return words if status == present.FAILS else words + "; see why"
    return f"up to {_amount(max(_ceil(-low), STEP), unit)} {gap} under some reading" + (
        "" if status == present.FAILS else "; see why")


def _one_compare(check: str, values: dict, kinds: dict):
    """The check's one numeric comparison with a measure on its left (`a <= 20`, or `ok and a <= 200` where every
    other term holds), as (measure, op, limit), or None: an `or`, two comparisons, or anything not worked out has no
    one margin, so no how-far (never a guess)."""
    try:
        body = formula.parse(check).body
    except formula.FormulaError:
        return None
    terms = body.values if isinstance(body, ast.BoolOp) and isinstance(body.op, ast.And) else [body]
    found = [t for t in terms if isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.left, ast.Name)
             and type(t.ops[0]) in (ast.GtE, ast.Gt, ast.LtE, ast.Lt)]
    if len(found) != 1:
        return None
    node = found[0]
    for t in terms:
        if t is not node:
            try:
                if formula.evaluate(ast.unparse(t), values, kinds) is not True:
                    return None
            except Exception:
                return None
    try:
        limit = formula.evaluate(ast.unparse(node.comparators[0]), values, kinds)
    except Exception:
        return None
    if type(limit) not in (int, float):
        return None
    return node.left.id, type(node.ops[0]), float(limit)


def _margin(value: float, op, limit: float) -> float:
    return value - limit if op in (ast.GtE, ast.Gt) else limit - value


def figures(rule: dict, row: dict, part: dict | None, building: dict, allowed: dict,
            more: dict | None) -> dict:
    """{how_far?, limit_length?} for a part's row: from its own measured values (each reading's, where the measure
    is given as readings), never from a value it doesn't have."""
    if row.get("outcome") not in ("pass", "fail", "needs_review") or not isinstance(rule.get("check"), str):
        return {}
    kind = rule.get("for_each")
    own = set(parts.measure_kinds(kind))
    kinds = _kinds(allowed, parts.measure_kinds(kind))
    mine = {m: v for m, v in ((part or {}).get("measures") or {}).items() if m in own}
    known = {**parts.building_values(building), **mine}
    combos = parts.reading_combinations(rule, part or {}, own, mine) if part else None
    trials = [known] if combos is None else [{**known, **v} for _, v in combos]
    if not trials:
        return {}
    got = [_one_compare(rule["check"], t, kinds) for t in trials]
    if any(g is None for g in got) or len({(g[0], g[1]) for g in got}) != 1:
        return {}
    name, op = got[0][0], got[0][1]
    values = [t.get(name) for t in trials]
    if any(type(v) not in (int, float) for v in values):
        return {}
    unit = (parts.registry().get(kind, {}).get("measures", {}).get(name) or {}).get("unit") or ""
    maximum = op in (ast.LtE, ast.Lt)
    out = {}
    lengths = _ratio_lengths(name, values, [g[2] for g in got], (more or {}).get(name))
    if lengths is not None:
        margins = [_margin(lengths["measured"], op, lim) for lim in lengths["_limits"]]
        unit = "ft"
        out["limit_length"] = {k: v for k, v in lengths.items() if not k.startswith("_")}
    elif unit in UNIT_WORDS or (unit == "count" and not name.endswith("_ratio")):
        margins = [_margin(v, op, g[2]) for v, g in zip(values, got)]
        unit = "" if unit == "count" else unit
    else:                                            # a ratio with no lengths beside it, yes/no, text: no how-far
        return out
    words = how_far_words(OUTCOME_STATUS[row["outcome"]], margins, unit, maximum)
    if words:
        out["how_far"] = words
    return out


def _ratio_lengths(name: str, values: list, limits: list, more) -> dict | None:
    """The ratio's limit as a length: {measure, measured, limit, of, unit, words}, from the two lengths the
    measuring gives beside the ratio, only when the ratio is their quotient (one value: no readings)."""
    spec = RATIO_LENGTHS.get(name)
    if spec is None or not isinstance(more, dict) or len(set(values)) != 1 or len(set(limits)) != 1:
        return None
    top, bottom = more.get(spec[0]), more.get(spec[1])
    if type(top) not in (int, float) or type(bottom) not in (int, float) or bottom <= 0:
        return None
    if abs(top / bottom - values[0]) > 1e-9:
        return None                                  # not the quotient of these two: no length is said
    limit = limits[0] * bottom
    # the limit said rounded up (stricter for an at-least), the length found rounded down: never kinder
    words = (spec[2].format(measured=_amount(_floor(top), "ft")) + ", needs ≥ " + _amount(_ceil(limit), "ft") +
             f" ({_fraction(limits[0])} " + spec[3].format(of=_amount(_ceil(bottom), "ft")) + ")")
    return {"measure": name, "measured": top, "limit": limit, "of": bottom, "ratio": limits[0], "unit": "ft",
            "words": words, "_limits": [limit]}


def _fraction(x: float) -> str:
    for d in (2, 3, 4, 5, 10):
        if abs(x * d - round(x * d)) < 1e-9:
            return f"{round(x * d)}/{d}"
    return f"{x:g} times"


# ---- causes -----------------------------------------------------------------------------------------------------

def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _rooms_cause(found: dict) -> dict:
    ids = sorted(found)
    no_route = all(found[r].get("stop") in NO_ROUTE for r in ids)
    names = ", ".join(found[r].get("name") or r for r in ids)
    words = (_plural(len(ids), "room has", "rooms have") + " no route to an exit" if no_route else
             _plural(len(ids), "room isn't", "rooms aren't") + " measured") + f": {names}"
    return {"kind": FIX_MODEL, "key": "rooms:" + ",".join(ids), "words": words, "elements": ids,
            "rooms": [{"id": r, "name": found[r].get("name"), "why": found[r].get("why"), "stop": found[r].get("stop")}
                      for r in ids]}


def needed(rule: dict, known: dict, kinds: dict, depth: int = 3) -> list[str]:
    """The measures the rule's formulas read that the row has no usable value for, on the way they are worked out
    (a formula stops at the first measure it lacks; `not a or b` with `a` true never reads `b`): every name a
    formula stops at, then each yes/no one tried both ways to find what it would read next. A measure the formulas
    never reach on these values is no cause (each_part.unsettled lists every name, which is more cautious for its
    words; a cause names only what the architect has to give)."""
    texts = [t for t in [rule.get("applies_when"), rule.get("check")] + [w.get("when") for w in
             rule.get("review_when") or [] if isinstance(w, dict)] if isinstance(t, str)]
    out = []

    def walk(text, vals, left):
        try:
            formula.evaluate(text, vals, kinds)
        except formula.MissingMeasure as e:
            if e.name not in out:
                out.append(e.name)
            if left and kinds.get(e.name) == "boolean":
                for v in (False, True):
                    walk(text, {**vals, e.name: v}, left - 1)
        except Exception:
            pass
    for t in texts:
        walk(t, dict(known), depth)
    return out


def causes(rule: dict, row: dict, open_: dict | None, part: dict | None, more: dict | None, why_not: dict | None,
           building: dict, allowed: dict, gaps: tuple) -> list[dict]:
    """A needs-review part row's causes, in the order to act on them (see the module's note); [] for any other."""
    if row.get("outcome") != "needs_review":
        return []
    out, keys = [], set()

    def add(c):
        if c["key"] not in keys:
            keys.add(c["key"])
            out.append(c)
    own_id = [row["id"]] if isinstance(row.get("id"), str) else []
    o = open_ or {}
    flag = rule.get("kind") == "flag"
    if o.get("gordium") == "not_read":
        add({"kind": BY_HAND, "key": "not_read:" + ",".join(o.get("kinds") or []),
             "words": "not read from the model yet: " + ", ".join(k.replace("_", " ") for k in o.get("kinds") or []),
             "elements": []})
    elif o.get("gordium") == "not_measured":
        add({"kind": BY_HAND, "key": f"not_measured:{o.get('kind')}:" + ",".join(o.get("measures") or []),
             "words": "not measured from the model yet: " + ", ".join(o.get("measures") or []), "elements": own_id})
    why_not = why_not or {}
    kind = rule.get("for_each")
    own = set(parts.measure_kinds(kind))
    kinds = _kinds(allowed, parts.measure_kinds(kind))
    known = {**parts.building_values(building), **(row.get("values") or {})}
    from design_checker.each_part import NOT_SENT, _usable, _words
    if flag:                       # a person decides with every figure the rule reads: each one missing is a cause
        try:
            missing = [m for m in sorted(parts.formula_names(rule)) if not _usable(known.get(m), kinds.get(m))]
        except formula.FormulaError:
            missing = []
    else:                          # a rule: only what its formulas reach on these values (needed)
        missing = needed(rule, known, kinds)
    readings = (part or {}).get("readings") if isinstance((part or {}).get("readings"), dict) else {}
    rooms = {}
    for m in missing:
        found = ((more or {}).get(m) or {}).get("room_ids_not_measured") if isinstance((more or {}).get(m), dict) \
            else None
        if isinstance(found, dict) and found:
            rooms.update({k: v for k, v in found.items() if isinstance(v, dict)})
    if rooms:
        add(_rooms_cause(rooms))
    for m in missing:
        if m in readings or o.get("gordium") in ("not_read", "not_measured"):
            continue                                  # an open question's (below), or Gordium's gap (above)
        if isinstance(((more or {}).get(m) or {}), dict) and ((more or {}).get(m) or {}).get("room_ids_not_measured"):
            continue                                  # the rooms' (above)
        why = why_not.get(m)
        if why in gaps:
            add({"kind": BY_HAND, "key": f"gap:{kind}:{m}", "words": f"{_words(rule, m)}: Gordium doesn't measure "
                 "this yet: measure it by hand", "elements": own_id})
        elif m not in own:                            # the building's: a fact the architect states for the project
            add({"kind": MARK, "key": f"fact:{m}", "words": f"{_words(rule, m)}: not stated for the project",
                 "elements": [], "measure": m, "field": f"facts.{m}"})
        elif why and (MARK_WORD.search(why) or "stated by the architect" in why or m in MEASURE_FIELDS):
            # a mark set on other elements than this row's (a story's occupant load waits on its rooms' function marks:
            # occupant_load.FUNCTION_ROOMS) names those elements, never the row's own (a level can't hold a room mark)
            held = (more or {}).get(m)
            on = held.get("room_ids_without_function") if isinstance(held, dict) else None
            add({"kind": MARK, "key": f"mark:{kind}:{m}", "words": f"{_words(rule, m)}: {why}",
                 "elements": list(on) if on else own_id,
                 "measure": m, **({"field": MEASURE_FIELDS[m]} if m in MEASURE_FIELDS else {})})
        else:
            add({"kind": FIX_MODEL, "key": f"model:{kind}:{m}:{why or ''}",
                 "words": f"{_words(rule, m)} not measured" + (f": {why}" if why else " (or not usable)"),
                 "elements": own_id, "measure": m})
    for note in o.get("inputs") or []:
        if NOT_SENT in note:
            add({"kind": FIX_MODEL, "key": f"drawing:{note}", "words": note, "elements": []})
    if row.get("has_none"):
        add({"kind": DECIDE, "key": f"reading:{row['has_none']}", "words": row.get("reason") or "a reading to confirm",
             "elements": own_id})
    elif not flag and readings and parts.is_reading_words(row.get("reason")):
        tags = sorted({t for m in missing if isinstance(readings.get(m), list) for r in readings[m]
                       if isinstance(r, dict) and isinstance(r.get("named"), dict) for t in r["named"]})
        add({"kind": DECIDE, "key": "question:" + ",".join(tags), "words": row["reason"], "elements": own_id,
             "questions": tags})
    elif not flag and row.get("reason") and not out:
        add({"kind": DECIDE, "key": f"reason:{row['reason']}", "words": row["reason"], "elements": own_id})
    if flag:
        add({"kind": DECIDE, "key": "flag", "words": FLAG_WORDS, "elements": own_id})
    elif not missing and not out:
        for w in rule.get("review_when") or []:      # a review condition that holds: the law's own reason
            try:
                holds = formula.evaluate(w["when"], known, kinds) is True
            except Exception:
                holds = False
            if holds:
                words = " ".join(str(w.get("reason") or REVIEW_WHEN_WORDS).split())
                add({"kind": DECIDE, "key": f"review_when:{words}", "words": words, "elements": own_id})
    if not out:                                       # never a row in review without a cause to act on
        add({"kind": DECIDE, "key": f"reason:{row.get('reason') or rule.get('id')}",
             "words": row.get("reason") or "needs review", "elements": own_id})
    return out


def sources(rule: dict) -> list[dict]:
    """Each of the rule's sources as data, in the order its quotes are shown (egress._decorated): the file, page and
    lines its words are on."""
    return [{"file": s.get("file"), "page": s.get("page"),
             "lines": s.get("lines") if isinstance(s.get("lines"), list) else None}
            for s in rule.get("sources") or [] if isinstance(s, dict)]
