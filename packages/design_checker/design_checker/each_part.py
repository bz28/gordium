"""Check the rules for each part (bedrooms, escape openings, stairs): one row per part, named, as panel items.

Plain code, no AI. Each part's result is rule_format.parts.rows' (the same outcome() as every zoning rule); this
module names each row for the architect ("Bedroom 2 › Window 5: net clear area 5.1 sq ft, needs ≥ 5.7 sq ft"), gives
each rule its one answer (parts.rule_result), and turns the rows into panel items whose overall answer is
present.state's, the same as the zoning rows'. Design: docs/decisions/2026-11-12_rules_for_each_part.md.
"""

import ast

from rule_format import formula, parts
from rule_format.parts import part_outcome

from design_checker import present
from model_measurement.interior import KINDS as INTERIOR_KINDS
from model_measurement.interior.stops import STOPS

STATUS = {"pass": present.COMPLIES, "fail": present.FAILS, "needs_review": present.REVIEW}
UNIT_WORDS = {"sf": "sq ft", "count": "", "yes_no": "", "text": ""}
SIGNS = {ast.GtE: "≥", ast.Gt: ">", ast.LtE: "≤", ast.Lt: "<"}
MIRROR = {ast.GtE: ast.LtE, ast.Gt: ast.Lt, ast.LtE: ast.GtE, ast.Lt: ast.Gt}
INTERIOR_NOT_STARTED = "interior.not_started"
INTERIOR_NOT_STARTED_WHY = "the interior isn't checked yet (bedrooms, escape openings, stairs, exit doors): " \
                           "start the interior to check them"


def part_rules(rules: list[dict]) -> list[dict]:
    """The rules for each part in a rulebook (for_each)."""
    return [r for r in rules if parts.is_part_rule(r)]


def check_parts(rules: list[dict], given, values: dict, allowed: dict) -> dict:
    """Every per-part rule's rows, each rule's one answer, and the panel items.

    given: the parts read, {kind: [part, …]} (parts.rows), or None when the interior isn't being checked at all
    (the architect hasn't started it): then no part is checked and one counted item says so, so the design is never
    shown as complying with rules nobody checked (needs review: principle 4). values: the building's measures."""
    rules = part_rules(rules)
    if given is None:
        items = [_item(INTERIOR_NOT_STARTED, None, "Interior", present.REVIEW, INTERIOR_NOT_STARTED_WHY)] \
            if rules else []
        return {"rows": [], "results": {_key(r, n): "needs_review" for n, r in enumerate(rules, 1)}, "items": items}
    more = _more(given)
    given, why_not = cautious(given)
    home = _homes(given)
    out, results, open_ = [], {}, {}
    for n, rule in enumerate(rules, 1):
        got = parts.rows(rule, given, values, allowed)
        for row in got:
            if not row.get("within") and row["id"] is not None:   # a window checked on its own: its room named too
                row["home"] = home.get((row["part"], row["id"]))
            row["line"] = line(row, rule, values, allowed, why_not.get((row["part"], row["id"])))
            open_[id(row)] = unsettled(row, rule, given, values, allowed, why_not.get((row["part"], row["id"])),
                                       more.get((row["part"], row["id"])))
        out += got
        key = _key(rule, n)          # two rules with one id (never validated so): one answer from both, never kinder
        results[key] = parts.rule_result(got + [{"outcome": results[key]}] if key in results else got)
    items, ids = [], set()
    for r in out:
        if r["outcome"] in STATUS:
            items.append(_item(_row_id(r, ids), r["rule"], label(r), STATUS[r["outcome"]], r["line"], r))
            items[-1]["element"] = items[-1]["name"]     # the part, as named: its line in the grouped results
            if open_.get(id(r)):     # why it needs review, for grouping the panel's lines (words only: never a status)
                items[-1]["open"] = open_[id(r)]
    return {"rows": out, "results": results, "items": items}


# the measuring's own words for a measure Gordium doesn't give the rules yet (model_measurement.interior.stops):
# a measure stopped with one of these is Gordium's gap, never something the architect left out
GORDIUM_GAPS = (STOPS["not_measured_yet"], STOPS["in_more_not_rules"])
# the part kinds the interior description can give, and its list for each (model_measurement.interior.KINDS): one
# left out is the drawing's to give; any other kind (handrails, ramps…) Gordium has no way to read yet
READ_KINDS = {kind: spec[0] for kind, spec in INTERIOR_KINDS.items()}
NOT_READ, NOT_MEASURED = "not_read", "not_measured"


def _unread(rule: dict, given) -> list[str]:
    """The part kinds this rule needs that weren't read at all (a list left out of the description): parts.rows'
    own test (`_read` gives None)."""
    kinds = [rule.get("for_each"), rule.get("within")]
    return [k for k in kinds if isinstance(k, str) and
            not isinstance(given.get(k) if isinstance(given, dict) else None, list)]


# a part kind the rules name that the measuring measures under another kind: the rules' open sides are the
# description's guards (model_measurement.interior measures each guard's height and openings)
STAND_INS = {"open_side": "guard"}


def _stand_ins(rule: dict, unread: list, given, allowed: dict) -> dict | None:
    """When a kind this rule needs isn't read but the measuring measured its stand-in (a guard for an open side):
    the stand-in's values the rule reads, each part's, and a concern if the check fails on them ("guard height
    30 in, needs ≥ 36 in"). Words only, the row's status is unchanged; None when nothing stands in."""
    if not isinstance(given, dict):
        return None
    names = parts.formula_names(rule)
    worked, concerns = [], []
    for k in unread:
        for p in given.get(STAND_INS.get(k)) or []:
            got = {m: v for m, v in ((p or {}).get("measures") or {}).items() if m in names and v is not None}
            if not got:
                continue
            worked += [f"{p.get('name') or p.get('id')}: {_words(rule, m)} {_n(v)}{_unit(rule, m)}"
                       for m, v in got.items()]
            try:
                c = _first_failing(rule, got, allowed, if_it_applies=True) \
                    if isinstance(rule.get("check"), str) else None
            except Exception:
                c = None
            if c:
                concerns.append(f"{p.get('name') or p.get('id')}: {c}")
    if not worked:
        return None
    out = {"gordium": None, "measures": [], "gaps": [], "worked": [],
           "notes": ["measured as guards, not yet given to these rules: " + ", ".join(dict.fromkeys(worked))],
           "inputs": [], "decide": False}
    if concerns:
        out["concern"] = "; ".join(concerns)
    return out


def _more(given) -> dict:
    """{(kind, part id): the values the measuring worked out but doesn't give the rules yet (its `more`)}."""
    if not isinstance(given, dict):
        return {}
    return {(k, p["id"]): p["more"] for k, listed in given.items() if isinstance(listed, list) for p in listed
            if isinstance(p, dict) and isinstance(p.get("id"), str) and isinstance(p.get("more"), dict)}


def unsettled(row: dict, rule: dict, given, values: dict, allowed: dict, why_not: dict | None,
              more: dict | None = None) -> dict | None:
    """Why a needs-review row isn't settled, for grouping the results (docs/decisions/2026-11-16_results_grouping.md);
    None for any other row. Words only: the row's status is parts.rows', never changed here.

      {"gordium": NOT_READ, "kinds": [...]}      the part kinds aren't read at all (parts.rows' "aren't read yet")
      {"gordium": NOT_MEASURED, "kind", "measures"}  every measure missing is one Gordium doesn't measure yet, and
                                                 the rule reads nothing of this part that was measured
      {"gordium": None, "concern"?, "measures", "gaps", "inputs", "decide"}   anything else: the architect's to
                                                 look at. `concern`: the check fails on what was measured ("riser
                                                 height 9 in, needs ≤ 8.25 in"), so it may not comply
    A row with a concern, or one reading anything measured, is never Gordium's gap: what was measured can show a
    problem, so it is shown to the architect, never folded away (principle 4). `more`: the part's values the
    measuring works out but doesn't give the rules yet (a stair's riser variation): they count as measured here,
    and a check that fails on them is a concern too (words only: the rules never read them)."""
    if row.get("outcome") != "needs_review":
        return None
    unread = _unread(rule, given)
    if row.get("reason"):
        if unread and row["reason"] == f"the {' and the '.join(parts._plural(k) for k in unread)} aren't read yet":
            drawn = [k for k in unread if k in READ_KINDS]
            stood = _stand_ins(rule, unread, given, allowed)
            if stood is not None:    # measured under another kind (a guard for an open side): never a gap
                return stood
            if not drawn:            # kinds Gordium has no way to read yet: its gap
                return {"gordium": NOT_READ, "kinds": unread}
            # a kind the description can give but left out (no `stairs` list): the drawing's to give, never a gap
            return {"gordium": None, "measures": [], "gaps": [], "notes": [],
                    "inputs": [f"the {parts._plural(k).replace('_', ' ')} aren't in the interior drawing (no "
                               f"`{READ_KINDS[k]}` list)" for k in drawn], "decide": False}
        return {"gordium": None, "measures": [], "gaps": [], "inputs": [], "notes": [row["reason"]],
                "decide": False}
    why_not = why_not or {}
    try:
        from rule_format.rulebook import _kinds
        kinds = _kinds(allowed, parts.measure_kinds(rule.get("for_each")))
        known = {**parts.building_values(values), **(row.get("values") or {})}
        missing = [m for m in sorted(parts.formula_names(rule)) if not _usable(known.get(m), kinds.get(m))]
        worked = {m: v for m, v in (more or {}).items() if m in missing and _usable(v, kinds.get(m))}
        concern = _first_failing(rule, {**known, **worked}, allowed, if_it_applies=True) \
            if isinstance(rule.get("check"), str) else None
    except Exception:            # never a crash, never a fold: shown to the architect as it is
        return {"gordium": None, "measures": [], "gaps": [], "inputs": [], "decide": True}
    own = row.get("values") or {}
    gaps = [m for m in missing if m in own and why_not.get(m) in GORDIUM_GAPS]
    measured = [m for m, v in own.items() if _usable(v, kinds.get(m))] + list(worked)
    # a reason the measuring gave about this part that is not Gordium's gap ("this door is sliding") is a fact found
    # about it: its rules stay with the architect, never folded as unread (review round 1 on #111)
    found = [r for r in why_not.values() if r not in GORDIUM_GAPS]
    if missing and len(gaps) == len(missing) and not measured and not concern and not found:
        return {"gordium": NOT_MEASURED, "kind": rule.get("for_each"), "measures": [_words(rule, m) for m in gaps]}
    out = {"gordium": None, "measures": [_words(rule, m) for m in missing],
           "gaps": [_words(rule, m) for m in gaps if m not in worked],
           "worked": [f"{_words(rule, m)} {_n(v)}{_unit(rule, m)}" for m, v in worked.items()],
           "inputs": [why_not[m] if m in why_not else f"{_words(rule, m)} not measured (or not usable)"
                      for m in missing if m not in gaps],
           "decide": not missing}       # every measure known, still needs review: a person's judgment (review_when, a flag)
    if concern:
        out["concern"] = concern
    return out


def cautious(given) -> tuple:
    """(the parts as the rules read them, {(kind, part id): {measure: why it has no value}}). A part's measure that
    its measuring also gives a reason for (`not_measured`) is taken out of its measures: the measuring doubts it,
    so a rule reading it needs review, never a pass on it (model_measurement.interior gives one or the other; this
    holds whatever a host sends). Nothing else changes: anything not a part is left for parts.rows to name."""
    if not isinstance(given, dict):
        return given, {}
    out, why = {}, {}
    for kind, listed in given.items():
        if not isinstance(listed, list):
            out[kind] = listed
            continue
        out[kind] = []
        for part in listed:
            stopped = part.get("not_measured") if isinstance(part, dict) else None
            if isinstance(stopped, dict) and isinstance(part.get("measures"), dict):
                part = dict(part, measures={m: v for m, v in part["measures"].items() if m not in stopped})
            if isinstance(stopped, dict) and isinstance(part.get("id"), str):
                why[(kind, part["id"])] = {m: str(w) for m, w in stopped.items()}
            out[kind].append(part)
    return out, why


def _homes(given) -> dict:
    """{(kind, part id): the name of the part it sits in}, for each part that says, by an id given once, which
    part it is in (an escape opening's room): words only, so "Bedroom 2 › Window 5" names a window whose rule isn't
    grouped by room."""
    if not isinstance(given, dict):
        return {}
    every = [(k, p) for k, listed in given.items() if isinstance(listed, list) for p in listed
             if isinstance(p, dict) and isinstance(p.get("id"), str)]
    ids = [p["id"] for _, p in every]
    names = {p["id"]: parts._name(p) for _, p in every if ids.count(p["id"]) == 1}
    return {(k, p["id"]): names[p["within"]] for k, p in every
            if isinstance(p.get("within"), str) and p["within"] in names}


def _row_id(row: dict, taken: set) -> str:
    """A row's item id, the same at every check of the same parts: the rule, the part it sits in and the part
    ("general.r319_2_3@br2/w5"), so a re-check's notice and the panel's selection follow the same part. Two rows
    alike (two problems of one rule) get #2, #3."""
    base = f"{row['rule']}@{(row.get('within') or {}).get('id') or '-'}/{row.get('id') or '-'}"
    got, n = base, 1
    while got in taken:
        n += 1
        got = f"{base}#{n}"
    taken.add(got)
    return got


def _key(rule: dict, n: int) -> str:
    """A rule's key among the results: its id, or (a rule without one, never validated so) its place in the list,
    so two such rules never share one answer."""
    return rule["id"] if isinstance(rule.get("id"), str) else f"rule #{n}"


def _title(rule: dict) -> str:
    return rule.get("title") if isinstance(rule.get("title"), str) else rule.get("id") or "the rule"


def _item(item_id, rule_id, name, status, reason, row=None) -> dict:
    """A panel item, with every field the panel and the report read on any item (present.view's)."""
    return {"id": item_id, "rule": rule_id, "name": name, "group": "interior", "status": status,
            "mark": present.MARK[status], "proposed": "", "required": "", "margin": "", "sign": "", "zoom": None,
            "measure": None, "objects": [], "points": None, "hint": None, "reason": reason, "use_detail": False,
            "part": ({k: row[k] for k in ("part", "id", "name", "within")} if row else None),
            "detail": {"line": reason or "", "quotes": [], "citation": "", "links": [], "calc": None, "scope": "",
                       "precision": "", "at_limit": None}}


def label(row: dict) -> str:
    """The part a row is about, as the architect names it: "Bedroom 2 › Window 5", "Bedroom 2", "Stair 1"; for a
    row about no one part, the rule's part kind ("Stairs")."""
    names = [row["within"]["name"]] if row.get("within") else [row["home"]] if row.get("home") else []
    names += [row["name"]] if row.get("name") else []
    if names:
        return " › ".join(names)
    return (row["part"].replace("_", " ").capitalize() + "s") if isinstance(row.get("part"), str) else "Parts"


def line(row: dict, rule: dict, values: dict, allowed: dict, why_not: dict | None = None) -> str:
    """One line naming the part and why: "Bedroom 2 › Window 5: net clear area 5.1 sq ft, needs ≥ 5.7 sq ft".
    `why_not`: the part's measuring's reason for each measure it has no value for (its `not_measured`), said
    wherever the line names that measure as not measured."""
    head = label(row)
    why_not = why_not or {}

    def gone(m: str) -> str:
        return f"{_words(rule, m)} (not measured: {why_not[m]})" if m in why_not else _words(rule, m)
    if row["reason"]:
        return f"{head}: {row['reason']}"
    if row["outcome"] == "fail":
        known = {**parts.building_values(values), **row["values"]}
        if row.get("unknown"):           # proven (parts.fails_whatever): it fails whatever the measures not given are
            if any(m in why_not for m in row["unknown"]):
                return f"{head}: {_title(rule)}: does not comply whatever the " + \
                    " and the ".join(gone(m) for m in row["unknown"])
            names = " and the ".join(_words(rule, m) for m in row["unknown"])
            return f"{head}: {_title(rule)}: does not comply whatever the {names} (not measured)"
        return f"{head}: {_first_failing(rule, known, allowed) or _title(rule)}"
    if row["outcome"] == "needs_review":
        from rule_format.rulebook import _kinds
        kinds = _kinds(allowed, parts.measure_kinds(rule.get("for_each")))
        known = {**parts.building_values(values), **row["values"]}
        # the part's measures and the building's the rule reads (stories, use…): each one missing or unusable
        missing = [m for m in sorted(parts.formula_names(rule)) if not _usable(known.get(m), kinds.get(m))]
        if missing and any(m in why_not for m in missing):
            return f"{head}: " + "; ".join(f"{_words(rule, m)} not measured: {why_not[m]}" if m in why_not
                                          else f"{_words(rule, m)} not measured (or not usable)" for m in missing)
        if missing:
            return f"{head}: {', '.join(_words(rule, m) for m in missing)} not measured (or not usable)"
        return f"{head}: {_title(rule)}: needs review"
    return f"{head}: {_title(rule)}" + (": complies" if row["outcome"] == "pass" else ": not applicable")


def _usable(v, kind) -> bool:
    """A value a formula can use for a measure of this kind (formula._measure's test): yes/no for "boolean", text for
    "text", a finite number ≥ 0 (never true/false) for a number."""
    if kind == "boolean":
        return type(v) is bool
    if kind == "text":
        return type(v) is str
    if isinstance(kind, (set, frozenset)):          # a text measure with its allowed values (the city's uses)
        return type(v) is str and v in kind
    return type(v) in (int, float) and v == v and abs(v) != float("inf") and v >= 0


def _unit(rule: dict, measure: str) -> str:
    d = parts.registry().get(rule["for_each"], {}).get("measures", {}).get(measure) or {}
    u = UNIT_WORDS.get(d.get("unit"), d.get("unit") or "")
    return f" {u}" if u else ""


def _words(rule: dict, measure: str) -> str:
    return measure.replace("opening_", "").replace("stair_", "").replace("door_", "").replace("_", " ")


def _first_failing(rule: dict, values: dict, allowed: dict, if_it_applies: bool = False) -> str | None:
    """The first comparison of the check that fails, in plain words: "net clear area 5.1 sq ft, needs ≥ 5.7 sq ft".
    Each comparison is decided by outcome() itself (part_outcome), so the words never disagree with the result.
    `if_it_applies`: whether the rule applies left aside (its applies_when not known yet): the check fails on what
    was measured if it does apply (unsettled's "may not comply"; words only, never a result)."""
    if if_it_applies:
        rule = {k: v for k, v in rule.items() if k != "applies_when"}
    for node in _all_of(formula.parse(rule["check"]).body):
        if not (isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in SIGNS):
            continue
        left, op, right = node.left, type(node.ops[0]), node.comparators[0]
        if not isinstance(left, ast.Name) and isinstance(right, ast.Name):    # "5.7 <= area": read as "area >= 5.7"
            left, op, right = right, MIRROR[op], left
        if not isinstance(left, ast.Name):
            continue
        if part_outcome({**rule, "check": ast.unparse(node), "review_when": []}, values, allowed) != "fail":
            continue
        name, need = left.id, _value(ast.unparse(right), values, rule, allowed)
        if need is None:
            continue
        return f"{_words(rule, name)} {_n(values.get(name))}{_unit(rule, name)}, needs {SIGNS[op]} " \
               f"{_n(need)}{_unit(rule, name)}"
    return None


def _all_of(node) -> list:
    """The comparisons the check needs every one of: the check itself, or the parts of an `and` (nested `and`s
    too). A comparison inside `or`, `not` or if-else isn't on its own the reason a part fails, so it is never named."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return [n for v in node.values for n in _all_of(v)]
    return [node]


def _value(text: str, values: dict, rule: dict, allowed: dict):
    from rule_format.rulebook import _kinds
    try:
        got = formula.evaluate(text, values, _kinds(allowed, parts.measure_kinds(rule["for_each"])))
    except (formula.EvaluationError, formula.MissingMeasure, ArithmeticError):
        return None
    return got if type(got) in (int, float) else None


def _n(x) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else f"{x:,}" if isinstance(x, int) else str(x)
