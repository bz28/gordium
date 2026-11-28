"""Rules for each part: "for each sleeping room", "for each escape opening of each sleeping room", "for each stair".

A per-part rule names the part kind it repeats over (`for_each`), optionally the kind those parts sit in (`within`),
and what the law says when there is nothing to check (`when_none`). The kinds, and the measures each part carries,
are a fixed list engineers write (parts.yaml). The result is one row per part, each decided by the same outcome()
as every zoning rule, so missing values and three-valued logic mean exactly what they mean there. Plain code, no AI.
Why and what was rejected: docs/decisions/2026-11-12_rules_for_each_part.md.

Never a silent pass: parts not read, a malformed part, or nothing to check each give a row of their own.
"""

import itertools
from pathlib import Path

import yaml

from . import formula
from .formula import EvaluationError, FormulaError, MissingMeasure

PARTS_FILE = Path(__file__).with_name("parts.yaml")
PART_FIELDS = ("for_each", "within", "when_none", "limit")   # a rule's fields for repeating over parts
# `limit` (section group 8d): the part's own requirement, apart from whether the law asks it of this part, so code can
# tell which parts comply (design_checker/escape_openings.py counts a sleeping room's compliant escape openings). On
# the parsed formulas: the check a top-level "(<limit>) or <set-aside>", every review_when a top-level "... and not
# (<limit>) and ...", no "if ... else", the limit's measures the part's own (never one marked `from`) and read nowhere
# else in the rule, and an applies_when reading no part measure: the two can't drift apart (limit_problems).
EXAMPLE_FIELDS = ("parts", "rows")                     # a per-part rule's worked example: the parts, the rows expected
PART_ENTRY_FIELDS = {"id", "name", "within", "measures"}
ROW_FIELDS = {"part", "within", "outcome"}             # an expected row: the part's id, the id of the part it sits in
OUTCOMES = ("pass", "fail", "needs_review", "not_applicable")
WHEN_NONE = ("fail", "needs_review", "not_applicable")  # never "pass": nothing checked never passes
UNITS = {"ft", "sf", "in", "count", "text", "yes_no"}
UNIT_KINDS = {"text": "text", "yes_no": "boolean"}       # every other unit is a number (as in measures.yaml)
KIND_FIELDS = {"meaning", "within", "measures"}
MEASURE_FIELDS = {"unit", "meaning", "from"}
# `from` (section group 8d, review round 1): a measure the checker copies onto a part from another part (an escape
# opening's room facts), never the part's own figure: a `limit` may not read one


def registry_problems(kinds, building_measures) -> list[str]:
    """Problems with a parts registry (parts.yaml's shape): every kind a meaning and its measures, each measure a
    known unit and a meaning, measure names unique across kinds and never a building measure's, `within` naming
    other known kinds."""
    if not isinstance(kinds, dict) or not kinds:
        return ["parts.yaml must be a non-empty mapping of part kinds"]
    p, seen = [], {}
    for name, k in kinds.items():
        if not (isinstance(name, str) and formula_name(name)):
            p.append(f"part kind {name!r}: a name is lowercase letters, digits and _")
            continue
        if not isinstance(k, dict):
            p.append(f"{name}: must be a mapping")
            continue
        p += [f"{name}: unknown field {f!r}" for f in k.keys() - KIND_FIELDS]
        if not (isinstance(k.get("meaning"), str) and k["meaning"].strip()):
            p.append(f"{name}: needs a 'meaning'")
        within = k.get("within", [])
        if not (isinstance(within, list) and all(isinstance(w, str) for w in within)):
            p.append(f"{name}: 'within' must be a list of part kinds")
        else:
            p += [f"{name}: within unknown part kind {w!r}" for w in within if w not in kinds or w == name]
        measures = k.get("measures")
        if not isinstance(measures, dict) or not measures:
            p.append(f"{name}: needs 'measures'")
            continue
        for m, d in measures.items():
            if not (isinstance(m, str) and formula_name(m)):
                p.append(f"{name}: measure {m!r}: a name is lowercase letters, digits and _")
                continue
            if not isinstance(d, dict) or d.keys() - MEASURE_FIELDS or d.get("unit") not in UNITS \
                    or not (isinstance(d.get("meaning"), str) and d["meaning"].strip()):
                p.append(f"{name}: measure {m!r} needs a unit from {sorted(UNITS)} and a meaning")
            if isinstance(d, dict) and "from" in d and (d["from"] not in kinds or d["from"] == name):
                p.append(f"{name}: measure {m!r}: 'from' must name another part kind, the one it is copied from")
            if m in building_measures:
                p.append(f"{name}: measure {m!r} is also a building measure (measures.yaml)")
            if m in seen:
                p.append(f"{name}: measure {m!r} is also a measure of {seen[m]}")
            seen.setdefault(m, name)
    return p


def formula_name(name: str) -> bool:
    return name.isidentifier() and name == name.lower() and not name.startswith("_")


def load_registry(path=PARTS_FILE, building_measures=None) -> dict:
    """parts.yaml, checked: a registry with problems is refused (ValueError), never half used."""
    if building_measures is None:
        from .rulebook import MEASURE_KINDS
        building_measures = MEASURE_KINDS
    kinds = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if problems := registry_problems(kinds, building_measures):
        raise ValueError(f"{path}: " + "; ".join(problems))
    return kinds


_REGISTRY = None


def registry() -> dict:
    """The part kinds (parts.yaml), read once."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = load_registry()
    return _REGISTRY


def is_part_rule(rule: dict) -> bool:
    """A rule with any of the per-part fields: never answered as a whole-building rule."""
    return isinstance(rule, dict) and any(k in rule for k in PART_FIELDS)


def measure_kinds(kind: str) -> dict:
    """The measures a part of this kind carries, by their kind ("number", "boolean" or "text"); {} for an unknown
    kind."""
    k = registry().get(kind) if isinstance(kind, str) else None
    return {m: UNIT_KINDS.get(d["unit"], "number") for m, d in (k or {}).get("measures", {}).items()}


def all_measures() -> set[str]:
    """Every part measure of every kind: a building rule may use none of them."""
    return {m for k in registry().values() for m in k["measures"]}


def rule_problems(rule: dict) -> list[str]:
    """Problems with a rule's per-part fields (validation). A rule without them has none."""
    if not is_part_rule(rule):
        return []
    try:
        kinds, p = registry(), []
    except (ValueError, OSError) as e:
        return [f"rule_format/parts.yaml can't be read: {e}"]
    kind, within, none = rule.get("for_each"), rule.get("within"), rule.get("when_none")
    if "for_each" not in rule:
        return ["'within' and 'when_none' only go with 'for_each'"]
    if not isinstance(kind, str) or kind not in kinds:
        p.append(f"for_each: unknown part kind {kind!r} (rule_format/parts.yaml lists {sorted(kinds)})")
    elif "within" in rule and (not isinstance(within, str) or within not in kinds.get(kind, {}).get("within", [])):
        p.append(f"within: a {kind} can sit within {kinds[kind].get('within', [])}, not {within!r}")
    if isinstance(rule.get("applies_when"), str) and none != "not_applicable" and isinstance(kind, str):
        try:
            on_part = sorted(formula.names(rule["applies_when"]) & set(measure_kinds(kind)))
        except FormulaError:
            on_part = []                 # an applies_when that can't be read is refused by the rule's own checks
        if on_part:
            p.append(f"applies_when uses {on_part}, measures of the part: a rule that must find a {_words(kind)} "
                     f"(when_none: {none}) can't rule parts out, or a {_words(rule.get('within') or 'building')} "
                     f"whose every {_words(kind)} is ruled out has no row that fails; say how parts differ inside "
                     f"'check' (a if condition else b)")
    p += limit_problems(rule)
    if none not in WHEN_NONE:
        p.append(f"when_none: what the law says when there is nothing to check, one of {WHEN_NONE} "
                 f"(never pass), got {none!r}")
    return p


def _spaced(text: str) -> str:
    return " ".join(text.split())


def limit_problems(rule: dict) -> list[str]:
    """A rule's `limit` (section group 8d), in its one fixed shape, checked on the parsed formulas (review round 1 of
    8d: a text match let drift through):

    - the limit reads only the part's own figures: none of its names is read anywhere else in the rule (the check's
      set-aside, a band's other conditions, applies_when), so it never carries a fact copied from elsewhere;
    - the check is a top-level "or" whose first operand is the limit (as parsed), the rest the set-aside;
    - every review_when is a top-level "and" with "not (<limit>)" (as parsed) one of its operands, so no band fires
      where the limit holds;
    - no "if ... else" anywhere in the check or a band (it binds looser than "or").

    A check or band that drifts from its limit could pass what the limit fails, or count as compliant a part its own
    rule doesn't pass: refused."""
    import ast
    if "limit" not in rule:
        return []
    limit, check, kind = rule.get("limit"), rule.get("check"), rule.get("for_each")
    if not isinstance(limit, str) or not limit.strip():
        return ["limit: the part's own requirement, a formula"]
    try:
        reads = formula.names(limit)
        lim = ast.dump(formula.parse(limit).body)
    except FormulaError as e:
        return [f"limit can't be read: {e}"]
    own = set(measure_kinds(kind)) if isinstance(kind, str) else set()
    copied = {m for m, d in (registry().get(kind, {}).get("measures") or {}).items()
              if isinstance(d, dict) and "from" in d} if isinstance(kind, str) else set()
    if reads - (own - copied):
        return [f"limit reads {sorted(reads - (own - copied))}, not the {_words(kind or 'part')}'s own figures (a fact "
                f"copied from another part, or another kind's): a limit is the part's own requirement"]

    def parsed(text, where):
        try:
            body = formula.parse(text).body
        except FormulaError as e:
            raise ValueError(f"{where} can't be read: {e}")
        if any(isinstance(n, ast.IfExp) for n in ast.walk(body)):
            raise ValueError(f"{where} has an 'if ... else', which binds looser than its limit: refused with a limit")
        return body

    if not isinstance(check, str):
        return ["check must be \"(<limit>) or <the condition setting it aside>\""]
    p = []
    try:
        body = parsed(check, "check")
        if not (isinstance(body, ast.BoolOp) and isinstance(body.op, ast.Or) and ast.dump(body.values[0]) == lim):
            return [f"check must be exactly \"({_spaced(limit)}) or <the condition setting it aside>\", its limit first"]
        elsewhere = set()
        for v in body.values[1:]:
            elsewhere |= {n.id for n in ast.walk(v) if isinstance(n, ast.Name)}
        for n, r in enumerate(rule.get("review_when") or [], 1):
            when = r.get("when") if isinstance(r, dict) else None
            if not isinstance(when, str):
                continue
            band = parsed(when, f"review_when {n}")
            gate = [v for v in (band.values if isinstance(band, ast.BoolOp) and isinstance(band.op, ast.And) else [])
                    if isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.Not) and ast.dump(v.operand) == lim]
            if not gate:
                p.append(f"review_when {n} must be \"... and not ({_spaced(limit)}) and ...\": every band of a rule with a "
                         f"limit fires only where the limit fails")
                continue
            for v in band.values:
                if v is not gate[0]:
                    elsewhere |= {x.id for x in ast.walk(v) if isinstance(x, ast.Name)}
        if isinstance(rule.get("applies_when"), str):
            elsewhere |= formula.names(rule["applies_when"])
            if formula.names(rule["applies_when"]) & own:
                p.append("applies_when reads the part's measures: with a limit, whether the rule applies must be "
                         "the building's alone, so a part is held to its limit only where the rule applies (review "
                         "round 2 of 8d)")
    except ValueError as e:
        return [str(e)]
    if reads & elsewhere:
        p.append(f"the limit reads {sorted(reads & elsewhere)}, which the rule reads outside its limit too: a limit is the "
                 f"part's own figures only")
    return p


def _name(part: dict) -> str:
    n = part.get("name")
    return n.strip() if isinstance(n, str) and n.strip() else part["id"]


def _words(kind: str) -> str:
    return kind.replace("_", " ")


def _plural(kind: str) -> str:
    return _words(kind) + "s"


ANYWHERE = object()      # an unreadable part that doesn't say where it is: it could be in any of them


def _read(parts, kind: str, everywhere: dict) -> tuple[list[dict] | None, list[str], set]:
    """The well-formed parts of one kind, a problem for each that isn't, and the ids the parts that aren't say they
    are within (such a part is there, just unreadable: never "none"). None if the kind wasn't read."""
    given = parts.get(kind) if isinstance(parts, dict) else None
    if not isinstance(given, list):
        return None, [], set()
    good, problems, doubtful = [], [], set()
    for n, part in enumerate(given, 1):
        if not isinstance(part, dict):
            problems.append(f"{_words(kind)} #{n} isn't a part (a mapping)")
        elif not (isinstance(part.get("id"), str) and part["id"].strip()):
            problems.append(f"{_words(kind)} #{n} has no id")
        elif everywhere.get(part["id"], 0) > 1:
            problems.append(f"two parts have the id {part['id']!r}")
        elif "within" in part and not isinstance(part["within"], str):
            problems.append(f"{_words(kind)} {_name(part)}: what it is within isn't an id")
        elif "measures" in part and not isinstance(part["measures"], dict):
            problems.append(f"{_words(kind)} {_name(part)}: its measures aren't a mapping")
        else:
            good.append(part)
            continue
        # where the unreadable part is: the id it names, or (none it can name) any part it could be within
        doubtful.add(part["within"] if isinstance(part, dict) and isinstance(part.get("within"), str) else ANYWHERE)
    # one problem per duplicated id, however many parts share it
    return good, list(dict.fromkeys(problems)), doubtful


def _ids(parts) -> dict:
    """How many parts carry each id, over every kind given (ids are unique across the whole building)."""
    count = {}
    for given in (parts.values() if isinstance(parts, dict) else []):
        for part in given if isinstance(given, list) else []:
            if isinstance(part, dict) and isinstance(part.get("id"), str):
                count[part["id"]] = count.get(part["id"], 0) + 1
    return count


def _maybe(part) -> str | None:
    """Why a part may not be of its kind at all (`maybe`: an enclosed space whose use isn't known may or may not be
    a sleeping room), or None. Every row about such a part, or about a part sitting in it, needs review with this
    reason, unless the rule doesn't apply to it whatever it is (not applicable): never a pass, never a fail, and its
    kind's rules are never "none" while it may be one. A `maybe` that isn't text still counts (said, never dropped)."""
    if not isinstance(part, dict) or "maybe" not in part:
        return None
    why = part["maybe"]
    return why.strip() if isinstance(why, str) and why.strip() else "it may not be a part of this kind"


def _ref(part: dict, kind: str) -> dict:
    return {"kind": kind, "id": part["id"], "name": _name(part)}


def _confirm(part, mine, shown) -> list[str]:
    """The words a part gives (`confirm`: {measure: words}) for the measures this row reads that it has a value for:
    each stands on a reading to confirm (Gordium's reading), shown with the row, never hidden. Words that aren't
    text are said as given."""
    given = part.get("confirm")
    if not isinstance(given, dict):
        return []
    return [str(given[m]) for m in sorted(shown) if m in mine and m in given]


def _architect_stated(part, mine, shown) -> list[str]:
    """The words a part gives (`architect_stated`: {measure: words}) for the measures this row reads that it has a
    value for: what the architect stated that the figure stands on (the rooms marked not occupied that a travel
    figure leaves out: route note decision 1b). Shown with the row, never hidden; unlike `confirm` it is the
    architect's own statement, not a reading of Gordium's, so it never holds a pass."""
    given = part.get("architect_stated")
    if not isinstance(given, dict):
        return []
    return [str(given[m]) for m in sorted(shown) if m in mine and m in given]


def _rests_on(part, mine, shown) -> list[str]:
    """The words a part gives (`rests_on`: {measure: words}) for the measures this row reads that it has a value for:
    Gordium's reading the figure stands on and the requirement that must hold for it (the dwelling units counted on a
    story stand on 1016.2.1, a person's check shown in the same answer). Shown with the row, never hidden; it never
    holds a pass (the requirement it rests on is checked, or flagged, on its own)."""
    given = part.get("rests_on")
    if not isinstance(given, dict):
        return []
    return [str(given[m]) for m in sorted(shown) if m in mine and m in given]


def _row(rule, result, part=None, within=None, reason=None, values=None, none=False, unknown=None) -> dict:
    """One row. `none`: the row is the rule's when_none answer (nothing to check). `unknown`: the part's measures
    that weren't given, for a part that fails whatever they are (the 2026-10-21 proof)."""
    return {"rule": rule.get("id"), "part": rule["for_each"], "id": part["id"] if part else None,
            "name": _name(part) if part else None, "within": within, "outcome": result, "reason": reason,
            "values": values or {}, "none": none, "unknown": unknown or []}


def part_outcome(rule: dict, values: dict, allowed: dict) -> str:
    """One part's result: outcome() of the rule (its per-part fields set aside) over the building's values and the
    part's own, with the part's measures described by parts.yaml."""
    from .rulebook import _outcome
    plain = {k: v for k, v in rule.items() if k not in PART_FIELDS}
    return _outcome(plain, values, allowed, measure_kinds(rule.get("for_each")))


def _none_outcome(rule: dict, values: dict, allowed: dict) -> str:
    """The result when there is nothing to check: the rule's when_none, if the rule applies to this building.
    Its applies_when is worked out over the building's values with every part measure unknown (three-valued: one
    that could go either way, when when_none isn't "not applicable", needs review). A review_when over the
    building's values alone that holds, or might, needs review; one about a part has no part to look at."""
    from .rulebook import _condition, _kinds
    answer = rule["when_none"]
    kinds = _kinds(allowed, measure_kinds(rule["for_each"]))
    part = set(measure_kinds(rule["for_each"]))
    try:
        if "applies_when" in rule and not _condition(rule["applies_when"], values, kinds):
            return "not_applicable"
    except (MissingMeasure, EvaluationError, FormulaError, ArithmeticError):
        return "not_applicable" if answer == "not_applicable" else "needs_review"
    if answer == "not_applicable":
        return answer
    for r in rule.get("review_when", []):
        if formula.names(r["when"]) & part:
            continue
        try:
            if _condition(r["when"], values, kinds):
                return "needs_review"
        except (MissingMeasure, EvaluationError, FormulaError, ArithmeticError):
            return "needs_review"
    return answer


def rows(rule: dict, parts, values: dict, allowed: dict) -> list[dict]:
    """The rule's rows: one per part (with `within`: per part, grouped under the part it sits in; a part it sits in
    with none of them gets one row, the rule's when_none), never none at all.

    parts: {kind: [{"id", "name"?, "within"?: <id of the part it sits in>, "measures"?: {measure: value},
    "maybe"?: <why it may not be of this kind at all: its rows, and those of the parts in it, need review>}]}. A kind
    the rule needs that isn't a list wasn't read: one needs-review row. values: the building's measures. Only the
    part kind's own measures are taken from a part (a part can't change a building value)."""
    if rule_problems(rule):
        return [_row(rule if isinstance(rule.get("for_each"), str) else dict(rule, for_each=None), "needs_review",
                     reason="the rule's per-part fields aren't valid")]
    try:
        formula_names(rule)
        shaped = all(isinstance(r, dict) and isinstance(r.get("when"), str) for r in rule.get("review_when", [])) \
            and (isinstance(rule.get("check"), str) or rule.get("kind") == "flag") \
            and isinstance(rule.get("applies_when", ""), str)
    except (FormulaError, AttributeError, TypeError):
        shaped = False
    if not shaped:                                       # never frozen so (validation refuses it); never a crash
        return [_row(rule, "needs_review", reason="the rule's formulas can't be read")]
    kind, parent = rule["for_each"], rule.get("within")
    own = set(measure_kinds(kind))
    everywhere = _ids(parts)
    children, problems, doubtful = _read(parts, kind, everywhere)
    parents, parent_problems, _ = _read(parts, parent, everywhere) if parent else ([], [], set())
    unread = [k for k, got in ((kind, children), (parent, parents)) if k and got is None]
    if unread:
        return [_row(rule, "needs_review", reason=f"the {' and the '.join(_plural(k) for k in unread)} aren't read yet")]
    # each problem once, even when a part of each kind shares one id
    out = [_row(rule, "needs_review", reason=p) for p in dict.fromkeys(parent_problems + problems)]
    values = building_values(values)

    def checked(part, within=None, maybe=None):
        mine = {m: v for m, v in (part.get("measures") or {}).items() if m in own}
        known = {**values, **mine}
        result, unknown, reason = part_outcome(rule, known, allowed), None, None
        combos = _combinations(rule, part, own, mine)
        hoped = None
        if combos is not None:                   # measures given as named readings: every combination decides
            result, reason = _under_readings(rule, known, allowed, combos)
        elif result == "needs_review" and (unknown := fails_whatever(rule, known, allowed)):
            result = "fail"                      # fails whatever the measures not given are (2026-10-21)
        elif result == "needs_review" and (got := under_bounds(rule, part, own, known, allowed)) is not None:
            if got[0] == "proven":               # the same answer for every value up to the measure's ceiling
                result, reason = got[1], got[2]
            else:                                # stating these facts would prove it: asked for (words only)
                hoped = got[1]
        shown = {m: mine.get(m) for m in sorted(formula_names(rule) & own)}
        why = _maybe(part) or maybe
        if why and result != "not_applicable":   # it, or the part it sits in, may not be of its kind at all
            return _row(rule, "needs_review", part, within, reason=why, values=shown)
        row = _row(rule, result, part, within, reason=reason, values=shown, unknown=unknown)
        if hoped:
            row["bound_facts"] = hoped
        confirm = _confirm(part, mine, shown) if result != "not_applicable" else []
        confirm = list(dict.fromkeys(confirm))
        if confirm and result == "pass":         # a pass that stands on a reading to confirm: never a pass on it
            row["outcome"] = "needs_review"      # (principle 4; as each_part.check_parts does for a has-none reading)
            row["reason"] = "complies only if this reading is confirmed: " + "; ".join(confirm)
        elif confirm:                            # a fail (or a needs review) keeps its own reason and comparison,
            row["confirm"] = confirm             # the reading said beside it
        said = list(dict.fromkeys(_architect_stated(part, mine, shown))) if result != "not_applicable" else []
        if said:                                 # the architect's statement the figure stands on, said beside it
            row["architect_stated"] = said
        rests = list(dict.fromkeys(_rests_on(part, mine, shown))) if result != "not_applicable" else []
        if rests:                                # the reading and the requirement the figure stands on, said beside it
            row["rests_on"] = rests
        return row

    if not parent:
        out += [checked(p) for p in children]
        if not children and not problems:
            out.append(_row(rule, _none_outcome(rule, values, allowed), reason=f"no {_plural(kind)}", none=True))
        return out
    by_parent = {p["id"]: [] for p in parents}
    # every part id given, and its kind: a part within a kind this rule isn't about (a basement) isn't its business
    kind_of = {p["id"]: k for k, given in (parts.items() if isinstance(parts, dict) else [])
               if isinstance(given, list) for p in given if isinstance(p, dict) and isinstance(p.get("id"), str)}
    for c in children:
        where = c.get("within")
        if where in by_parent:
            by_parent[where].append(c)
        elif kind_of.get(where) in registry()[kind].get("within", []) and kind_of.get(where) != parent \
                and everywhere.get(where) == 1:
            continue
        else:                            # nowhere, or an id two parts share: never dropped
            doubtful.add(ANYWHERE)           # it could be any room's (a mistyped id): no room is "none"
            out.append(_row(rule, "needs_review", c,
                            reason=f"{_words(kind)} {_name(c)} isn't within any {_words(parent)} that was read"))
    for p in parents:
        within = _ref(p, parent)
        mine = by_parent[p["id"]]
        out += [checked(c, within, _maybe(p)) for c in mine]
        none = _none_outcome(rule, values, allowed) if not mine else None
        if not mine and (p["id"] in doubtful or ANYWHERE in doubtful):          # it has one we can't read: not "none"
            out.append(_row(rule, "needs_review", within=within, reason=f"an {_words(kind)} that may be in it can't be read"))
        elif not mine and _maybe(p) and none != "not_applicable":   # what "none" means hangs on what it is
            out.append(_row(rule, "needs_review", within=within, reason=_maybe(p)))
        elif not mine:
            out.append(_row(rule, none, within=within, reason=f"no {_words(kind)}", none=True))
    if not parents and not parent_problems:
        out.append(_row(rule, "not_applicable", reason=f"no {_plural(parent)}"))
    return out


MAX_READING_COMBINATIONS = 200      # more than this: not worked out (the row stays needs review)


def reading_combinations(rule: dict, part: dict, own: set, mine: dict):
    """The combinations of the named readings a part gives for the measures this rule reads and the part has no
    value for (`readings`: {measure: [{"value", "named": {question: answer}}]}, the shape the checker's zoning
    readings take: design_checker/check.py readings_of). Readings are combined question by question, as there: one
    answer to an open question holds for the whole part, so a measure takes, under each answer, the value of its
    reading named so. [(answer key, {measure: value}), ...], the key "question = answer, ..." (an engineer's key,
    never shown: an architect reads reading_words); None when the rule reads no such measure (nothing changes for
    it); [] when the readings can't be read or are too many (the row needs review)."""
    got = _combinations(rule, part, own, mine)
    if not got:
        return got
    return [(", ".join(f"{t} = {v}" for t, v in answer.items()), combo) for answer, combo in got]


def _combinations(rule: dict, part: dict, own: set, mine: dict):
    """reading_combinations with each combination's answers as {question: answer}."""
    given = part.get("readings")
    if not isinstance(given, dict):
        return None
    try:
        names = formula_names(rule)
    except FormulaError:
        return None
    open_ = sorted(n for n in names & own if n not in mine and n in given)
    if not open_:
        return None
    readings = {}
    for n in open_:
        got = given[n]
        if not (isinstance(got, list) and got and all(
                isinstance(r, dict) and isinstance(r.get("named"), dict) and r["named"]
                and all(isinstance(k, str) and isinstance(v, str) for k, v in r["named"].items())
                and type(r.get("value")) in (int, float) for r in got)):
            return []
        readings[n] = got
    tags = sorted({t for n in open_ for r in readings[n] for t in r["named"]})
    answers = [sorted({r["named"][t] for n in open_ for r in readings[n] if t in r["named"]}) for t in tags]
    out = []
    for picked in itertools.product(*answers):
        answer = dict(zip(tags, picked))
        combo = {}
        for n in open_:
            fits = {r["value"] for r in readings[n] if all(answer.get(t) == v for t, v in r["named"].items())}
            if len(fits) != 1:
                return []                        # no reading, or two values, under one answer: not worked out
            combo[n] = fits.pop()
        out.append((answer, combo))
        if len(out) > MAX_READING_COMBINATIONS:
            return []
    return out


# The open questions a part's named readings answer (the tags the route measuring names them by:
# model_measurement/model_measurement/routes/dead_ends.py QUESTION, routes/areas.py STORY_AREA_QUESTION and
# ACCESSORY_AREA_QUESTION), in an architect's words: the question as its own list names it (the open questions of
# docs/decisions/2026-11-20_route_measurement.md, by number) and what each answer means. A test checks every tag the
# measuring gives is here; a tag that isn't is still said in words, never as "tag = answer".
READING_QUESTIONS = {
    "door_ends_dead_end": {
        "question": "whether a door into a room with another way out ends a dead end", "number": 7,
        "answers": {"with_door": "the door ends the dead end", "without_door": "the door doesn't end it"}},
    "story_area_face": {
        "question": "whether a story's area is measured inside its exterior walls or to their outer faces",
        "number": 3,
        "answers": {"inside": "the story's area is measured inside its walls",
                    "outer_faces": "the story's area is measured to the walls' outer faces"}},
    "accessory_area_face": {
        "question": "whether a storage room's area is measured inside its walls or to their outer faces",
        "number": 3,
        "answers": {"inside": "the storage rooms' area is measured inside their walls",
                    "outer_faces": "the storage rooms' area is measured to the walls' outer faces"}},
}
# what follows the open questions in every reason _under_readings gives for a mixed result (is_reading_words)
_UNDER = (": under one reading it complies (", ": under either reading it doesn't comply", ": under every reading it "
          "doesn't comply", ": it complies if ")


def _plain(name: str) -> str:
    return name.replace("_", " ")


def _answer_words(answer: dict) -> str:
    """One combination of answers in words: "the door ends the dead end" (and, for two questions, both)."""
    said = []
    for tag, value in answer.items():
        known = READING_QUESTIONS.get(tag, {}).get("answers", {})
        said.append(known.get(value) or f"the answer to “{_plain(tag)}” is “{_plain(value)}”")
    return " and ".join(said)


def question_words(tags) -> str:
    """The open questions named by these tags, in words with their numbers: "whether a door into a room with another
    way out ends a dead end is an open question (question 7)"."""
    tags = list(dict.fromkeys(tags))
    asked = [READING_QUESTIONS.get(t, {}).get("question") or f"“{_plain(t)}”" for t in tags]
    numbers = list(dict.fromkeys(str(READING_QUESTIONS[t]["number"]) for t in tags if t in READING_QUESTIONS))
    which = " and ".join(asked) + (" is an open question" if len(asked) == 1 else " are open questions")
    if numbers:
        which += f" (question{'s' if len(numbers) > 1 else ''} {' and '.join(numbers)})"
    return which


def reading_words(answers: list[dict], good: list[dict], bad: list[dict]) -> str:
    """A mixed result under the readings, in words: which open question it turns on and what it gives under each
    answer, never a tag or "tag = answer"."""
    tags = [t for a in answers for t in a]
    first = question_words(tags)
    if len(answers) == 2 and len(good) == 1 and len(bad) == 1:
        return (f"{first}: under one reading it complies ({_answer_words(good[0])}), under the other it doesn't "
                f"comply or can't be told ({_answer_words(bad[0])})")
    if not good:
        return (f"{first}: under {'either reading' if len(answers) == 2 else 'every reading'} it doesn't comply or "
                f"can't be told ({'; '.join(map(_answer_words, bad))})")
    return (f"{first}: it complies if {' or if '.join(map(_answer_words, good))}; it doesn't comply or can't be "
            f"told if {' or if '.join(map(_answer_words, bad))}")


def is_reading_words(text) -> bool:
    """Whether a row's reason is reading_words' (a mixed result under an open question's readings)."""
    return isinstance(text, str) and "open question" in text and any(u in text for u in _UNDER)


def _under_readings(rule: dict, known: dict, allowed: dict, combos: list) -> tuple:
    """The rule under every combination of readings: pass only if it passes under every one, fail only if it fails
    under every one, else needs review naming, in words, the open question and the readings it fails (or can't be
    told) under."""
    if not combos:
        return "needs_review", "its measures' readings can't be combined"
    got = [(answer, part_outcome(rule, {**known, **values}, allowed)) for answer, values in combos]
    results = {r for _, r in got}
    if results in ({"pass"}, {"fail"}, {"not_applicable"}):
        return results.pop(), None
    bad = [a for a, r in got if r != "pass"]
    good = [a for a, r in got if r == "pass"]
    return "needs_review", reading_words([a for a, _ in got], good, bad)


# A part's ceilings on measures it has no value for (`bounds`: {measure: {"at_most": n, "why": words, "if_stated"?:
# {"at_most": n, "why", "facts": [the building facts that, stated, prove it]}}}): the most the measure can be, proven
# by the measuring (design_checker/occupant_load.py: a story's area at the densest occupant load factor). A rule is
# decided on them only where every formula it has is provably monotone in each such measure (formula.truth_direction:
# its truth moves one way as the measure grows) and gives the same truth at none and at the ceiling: then it gives
# that truth for every value between, so no value the measure can really take decides it otherwise.
BOUNDS = "bounds"
CEILING, IF_STATED = "at_most", "if_stated"
MAX_BOUNDED = 3                     # more ceilings on one row than this: not tried (2 ** n corners)
SETTLED_WORDS = {"pass": "complies", "fail": "does not comply", "not_applicable": "does not apply"}


def _ceiling(v) -> bool:
    return type(v) in (int, float) and v == v and v != float("inf") and v >= 0


def under_bounds(rule: dict, part: dict, own: set, known: dict, allowed: dict):
    """The rule on a part whose open measures have ceilings (BOUNDS): ("proven", outcome, reason) where it gives
    one answer for every value from none up to the proven ceilings; ("hoped", facts) where it would at the ceilings
    stating those facts gives (words only: the row keeps its own result); None otherwise. Only ever an answer the
    law's words give at every value the measure can take (principle 4)."""
    given = part.get(BOUNDS)
    if not isinstance(given, dict):
        return None
    try:
        names = formula_names(rule)
    except FormulaError:
        return None
    open_ = sorted(n for n in names & own if known.get(n) is None and isinstance(given.get(n), dict))
    if not open_ or len(open_) > MAX_BOUNDED:
        return None
    texts = [t for t in [rule.get("applies_when"), rule.get("check")] + [r.get("when") for r in
                                                                        rule.get("review_when", [])]
             if isinstance(t, str)]
    try:
        if any(n in formula.names(t) and formula.truth_direction(t, n) is None for t in texts for n in open_):
            return None
    except FormulaError:
        return None
    from .rulebook import _condition, _kinds
    kinds = _kinds(allowed, measure_kinds(rule.get("for_each")))

    def settles(tops: dict):
        corners = [dict(zip(open_, c)) for c in itertools.product(*[(0, tops[n]) for n in open_])]
        for t in texts:
            if not formula.names(t) & set(open_):
                continue
            seen = set()
            for c in corners:
                try:
                    seen.add(_condition(t, {**known, **c}, kinds))
                except (MissingMeasure, EvaluationError, FormulaError, ArithmeticError):
                    return None
            if len(seen) != 1:
                return None
        got = {part_outcome(rule, {**known, **c}, allowed) for c in corners}
        return got.pop() if len(got) == 1 and got != {"needs_review"} else None

    tops = {n: given[n].get(CEILING) for n in open_}
    if all(_ceiling(v) for v in tops.values()) and (out := settles(tops)):
        kind = rule.get("for_each")
        said = "; ".join(f"its {_plain(n.removeprefix(f'{kind}_'))} can be at most {tops[n]:g}" + (
            f": {given[n]['why']}" if isinstance(given[n].get("why"), str) else "") for n in open_)
        return "proven", out, f"{SETTLED_WORDS[out]} at any value up to the most it can be ({said})"
    hoped, facts = {}, []
    for n in open_:
        stated = given[n].get(IF_STATED) if isinstance(given[n].get(IF_STATED), dict) else {}
        hoped[n] = stated.get(CEILING, tops[n])
        facts += [f for f in stated.get("facts") or [] if isinstance(f, str) and f not in facts]
    if facts and all(_ceiling(v) for v in hoped.values()) and settles(hoped):
        return "hoped", facts
    return None


def building_values(values: dict) -> dict:
    """The building's values without any part measure's name: a part's measure comes from the part, never from a
    building value that happens to share its name (a part missing it is then missing it)."""
    every = all_measures()
    return {k: v for k, v in (values or {}).items() if k not in every}


def formula_names(rule: dict) -> set[str]:
    """Every measure name in the rule's applies_when, check and review_when (FormulaError if one can't be read)."""
    return set().union(*(formula.names(t) for t in [rule.get("applies_when"), rule.get("check")]
                         + [r.get("when") for r in rule.get("review_when", [])] if isinstance(t, str)))


def rule_result(rule_rows: list[dict]) -> str:
    """A per-part rule's one answer from its rows: fail if any row fails; else needs review if any does; else pass
    if any row passes; else (only not-applicable rows) not applicable. No rows is needs review: nothing checked
    never passes."""
    got = {r["outcome"] for r in rule_rows}
    for o in ("fail", "needs_review", "pass"):
        if o in got:
            return o
    return "not_applicable" if got == {"not_applicable"} else "needs_review"


def fails_whatever(rule: dict, values: dict, allowed: dict) -> list[str] | None:
    """The "fails whatever the missing number is" proof (decided 2026-10-21; rulebook.unknown_settings, the same
    proof the checker's zoning rows use) for one part: the measures the rule reads that weren't given (absent or
    None), if the part fails under every setting the proof tries; else None. A value given but unusable (NaN, below
    0, the wrong kind) isn't unknown: the row stays needs review. Only ever turns needs review into fail, never into
    pass (principle 4)."""
    from .rulebook import MEASURE_KINDS, unknown_settings
    unknown = sorted(n for n in formula_names(rule) if values.get(n) is None)
    settings = unknown_settings(rule, unknown, MEASURE_KINDS | measure_kinds(rule.get("for_each")))
    if settings and all(part_outcome(rule, {**values, **s}, allowed) == "fail" for s in settings):
        return unknown
    return None


# --- worked examples ------------------------------------------------------------------------------------------------
# A per-part rule's worked example is a small design: the building's measures (`given`), its parts (`parts`, as the
# checker is given them) and every row the rule must give (`rows`: {part: id, within: id, outcome}, a key left out
# where the row has none, as for a room's "no escape opening" row), with the rule's one answer (`expect`). Checked
# by parts.rows itself, so the examples prove the rows the checker will show. At least one example must show the
# rule's when_none: a row for nothing to check, whose answer is the rule's when_none.

def _fits(kind, value) -> bool:
    if kind == "boolean":
        return type(value) is bool
    if kind == "text":
        return type(value) is str
    return type(value) in (int, float) and value == value and abs(value) != float("inf") and value >= 0


def _example_shape(rule: dict, ex: dict) -> list[str]:
    """What is wrong with the shape of one per-part worked example (its `given` is checked by the rulebook)."""
    p, kinds = [], [k for k in (rule.get("for_each"), rule.get("within")) if isinstance(k, str)]
    given, want = ex.get("parts"), ex.get("rows")
    if not isinstance(given, dict):
        p.append("a rule for each part needs 'parts': the parts by kind, {kind: [{id, name, within, measures}]}")
    else:
        ids = []
        for kind, listed in given.items():
            if kind not in kinds:
                p.append(f"'parts' has {kind!r}, not a kind this rule reads ({kinds})")
                continue
            if not isinstance(listed, list):
                p.append(f"parts {kind}: must be a list")
                continue
            own = measure_kinds(kind)
            for n, part in enumerate(listed, 1):
                where = f"{_words(kind)} #{n}"
                if not isinstance(part, dict) or part.keys() - PART_ENTRY_FIELDS:
                    p.append(f"{where}: a part is a mapping of {sorted(PART_ENTRY_FIELDS)}")
                    continue
                if not (isinstance(part.get("id"), str) and part["id"].strip()):
                    p.append(f"{where}: needs an id")
                else:
                    ids.append(part["id"])
                p += [f"{where}: {k} must be text" for k in ("name", "within") if k in part and not isinstance(part[k], str)]
                measures = part.get("measures", {})
                if not isinstance(measures, dict):
                    p.append(f"{where}: measures must be a mapping")
                    continue
                p += [f"{where}: {m!r} isn't a measure of a {_words(kind)} (rule_format/parts.yaml)"
                      for m in sorted(measures.keys() - set(own), key=str)]
                p += [f"{where}: wrong kind of value for {m!r} (rule_format/parts.yaml units)"
                      for m in sorted(measures.keys() & set(own)) if not _fits(own[m], measures[m])]
        p += [f"two parts have the id {i!r}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    if not (isinstance(want, list) and want):
        p.append("a rule for each part needs 'rows': every row it gives, [{part: id, within: id, outcome}]")
    else:
        for n, row in enumerate(want, 1):
            if not isinstance(row, dict) or row.keys() - ROW_FIELDS or row.get("outcome") not in OUTCOMES \
                    or any(k in row and not isinstance(row[k], str) for k in ("part", "within")):
                p.append(f"row {n}: {{part: id, within: id, outcome: one of {list(OUTCOMES)}}} (part and within "
                         "left out where the row has none)")
    return p


def _row_key(row: dict) -> tuple:
    return row["id"], (row.get("within") or {}).get("id"), row["outcome"]


def _shown(keys) -> str:
    return "; ".join(f"{o}" + (f" for {i}" if i else "") + (f" in {w}" if w else "") for i, w, o in keys) or "none"


def worked_example(rule: dict, ex: dict, allowed: dict):
    """What a worked example comes out as: a whole-building rule's outcome(); a per-part rule's one answer and its
    rows (each part's id, the id of the part it sits in, and its result). Two versions of a rule decide an example
    the same way only if these are equal (the drafter's test of whether a number decides anything)."""
    from .rulebook import outcome
    if not is_part_rule(rule):
        return outcome(rule, ex.get("given") or {}, allowed)
    got = rows(rule, ex.get("parts"), ex.get("given") or {}, allowed)
    return rule_result(got), tuple(sorted((_row_key(r) for r in got), key=repr))


def examples_problems(rule: dict, examples: list, allowed: dict, run: bool = True) -> list[str]:
    """Problems with a per-part rule's worked examples: each one's shape, then (run: the rule has no other problem)
    each one's rows and answer as parts.rows gives them, and at least one example showing the rule's when_none.
    With parts.yaml unreadable, nothing (validation already says so: the rule is refused, never a crash)."""
    try:
        registry()
    except (ValueError, OSError):
        return []
    p, shown_none, part_rows = [], False, set()
    for n, ex in enumerate(examples, 1):
        shape = _example_shape(rule, ex) if isinstance(ex, dict) else ["must be a mapping"]
        p += [f"example {n}: {x}" for x in shape]
        if shape or not run or not isinstance(ex.get("given"), dict):
            continue
        got = rows(rule, ex["parts"], ex["given"], allowed)
        have = sorted((_row_key(r) for r in got), key=repr)
        want = sorted(((r.get("part"), r.get("within"), r["outcome"]) for r in ex["rows"]), key=repr)
        if have != want:
            p.append(f"example {n}: expected rows {_shown(want)}; got {_shown(have)}")
        elif (result := rule_result(got)) != ex.get("expect"):
            p.append(f"example {n}: expected {ex.get('expect')}, got {result}")
        else:
            shown_none |= any(r["none"] and r["outcome"] == rule.get("when_none") for r in got)
            part_rows |= {r["outcome"] for r in got if r["id"] is not None}
    # the check itself exercised: a part that passes it and a part that fails it (a "none" row fails whatever the
    # check says, so it can't stand in for a failing part: an always-true check would pass every real part)
    if run and not p and rule.get("kind") == "rule" and not {"pass", "fail"} <= part_rows:
        p.append("a rule for each part needs worked examples with a part that passes its check and a part that fails "
                 "it (a row for nothing to check doesn't exercise the check)")
    if run and not p and not shown_none:
        where = _words(rule["within"]) if rule.get("within") else "building"
        p.append(f"no worked example shows when_none ({rule.get('when_none')}): give one with a {where} that has no "
                 f"{_words(rule.get('for_each') or 'part')}, whose row is {rule.get('when_none')}")
    return p
