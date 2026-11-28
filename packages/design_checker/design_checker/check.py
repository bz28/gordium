"""Check a design: measure the model, run the zone's rules, build the envelope, and say it in one line.

Every result comes from the checker's `outcome()` (the project report, PR 10, refuses a rulebook that fails the
rule checks). row_verdict decides each row, and each side yard of a pair, over THE reading set (reading_set: the
open questions' readings, and on a tax-map lot the lines' slack and the lot area's ends): fails if it fails under
every reading, complies if it passes under every one and its result turns on no open question (turns_on), else
needs review. That verdict
is the single source of truth: the panel (present) shows it or something more cautious, never more favourable.
This module also gathers what the Rhino panel and the viewport show: the rows, a short summary, the objects to
show in red, the envelope and the plan.
"""

import ast
import hashlib
import itertools
import json
import math
import os
import pickle
import re
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path

import shapely
import yaml

from design_checker import code_scope, egress, present, reading_set, site_json, ui_data
from design_checker import rhino_logic as logic
from design_checker.rhino_logic import COLUMN_DELTA
from envelope_builder import start as generator
from envelope_builder.envelope import envelope
from model_measurement.places import measuring
from model_measurement.plugin_measuring import TAX_MAP_TOLERANCE
from model_measurement.project import fact_problems, load_facts, working
from model_measurement.stops import joined, reason_part
from model_measurement.read_3dm import read_site
from model_measurement.stops import in_words
from project_report.report import OUTPUT_EXTRA, OUTPUT_HEADERS, build, tables
from rule_format import formula, parts
from rule_format.place import UnknownPlace
from rule_format.place import place as place_of_folder
from rule_format.place import plugin_place
from rule_format.rulebook import (MEASURE_KINDS, REPO, STATE_SETTINGS, Context, load, load_bytes, outcome, rulebook_for,
                                  unknown_settings)

COLUMNS = OUTPUT_HEADERS + OUTPUT_EXTRA
# Facts about the inside of a building (rooms, parking spaces). This phase checks the outside only: a rule waiting
# on one of these goes in its own group, "not checked yet: interior", out of the counts. A rule they decide once
# entered (a FAIL included) is shown like any other: nothing that fails is ever hidden.
# What sets a row aside as "not checked yet: interior" (out of the counts): only these, inside the building. Every
# other stated fact (rhino_logic.STATED_FACTS: what can be ASKED, such as R-3a's dwelling units) leaves its row a
# review row, with its own "Enter …" button from `needs` (PR #20 round 2: never hidden, even when it fails).
INTERIOR = set(logic.INTERIOR_FACTS)
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


def _why(row: dict, rules: dict, measured: dict, allowed: dict | None = None, facts: dict | None = None) -> dict:
    """The row, plus "Why": for a NEEDS REVIEW row whose measurements are missing, why each is missing (the
    measuring's own reason: "a building isn't on the lot (is it part of this design?)", "enter bedrooms / parking spaces"), else the
    report's reason. A rule's own review_when that holds under every reading of THE reading set (with `allowed`)
    comes first, and the readings of a measurement then change nothing, so their question is left out: the rule's
    own question, never one that changes nothing (#20 review round 1: an eaves row asking which side is the 10 ft one
    said instead to ask the City how a pitched roof's height is taken, though every height reading gave the same
    answer)."""
    reasons = []
    if row["Error"] == "NEEDS REVIEW":
        rule = rules[row["Rule id"]]
        values = {k: m.get("value") for k, m in measured.items()}
        own = _review_reasons(rule, measured, allowed, facts) if allowed is not None else []
        for name in sorted(set().union(*(formula.names(rule[k]) for k in ("applies_when", "check") if rule.get(k)))):
            if own and (measured.get(name) or {}).get("readings"):
                continue                # needs review under every one of its readings: it changes nothing
            reason = (measured.get(name) or {}).get("reason")
            if name in logic.OPTIONAL and not present.could_settle(rule, values, name):
                continue        # an optional fact that can't change this row isn't why it needs review (r2 round 2)
            if (measured.get(name) or {}).get("value") is None and reason and reason not in reasons:
                reasons.append(reason)
        reasons = [reason_part("review_when", r) for r in own] + reasons
    if reasons:
        return {**row, "Why": joined(reasons)}
    # the report's own reason, under what it is (a flag: a person decides; else the rule's review)
    flag = (rules.get(row["Rule id"]) or {}).get("kind") == "flag"
    why = row["Why it needs review"]
    return {**row, "Why": reason_part("flag" if flag else "review", why) if why else why}


def _review_reasons(rule: dict, measured: dict, allowed: dict, facts: dict | None) -> list[str]:
    """The reasons of a rule's review_when entries that hold under every reading of THE reading set (a needs-review
    the rule itself asks for, whatever the open measurements turn out to be), in the rule's order."""
    from rule_format.rulebook import _condition
    entries = rule.get("review_when") or []
    if not entries:
        return []
    names = reading_set.rule_names(rule)
    values = {k: m["value"] for k, m in measured.items()}
    every = reading_set.combos(names, values, measured, facts)
    if not every:
        return []
    kinds = MEASURE_KINDS | {k: v if isinstance(v, str) else frozenset(v) for k, v in allowed.items()}
    out = None
    for trial, _ in every:
        if outcome(rule, trial, allowed) != "needs_review":
            return []
        held = []
        for r in entries:
            try:
                if _condition(r["when"], trial, kinds):
                    held.append(" ".join(str(r.get("reason") or "").split()))
            except Exception:                   # a condition that can't be read under this reading
                pass
        out = list(dict.fromkeys(h for h in held if h)) if out is None else [h for h in out if h in held]
        if not out:                             # none holds under every reading: the readings' own questions
            return []
    return out or []


SURVEY = "lot_area"        # a lot not yet surveyed: its one reading is the lot as drawn
MAX_COMBINATIONS = 200     # more combinations of readings than this: not worked out (stays a plain NEEDS REVIEW)


MODEL_WORDS = {"model#eave": {"eave": "what reaches past the walls an eave",
                               "not_eave": "what reaches past the walls not an eave"},
               "model#projection": {"projection": "what sticks out a projection", "part": "what sticks out a story"},
               "model#narrower": {}}          # its readings say their own line: "the side along lot line 3 …"
EAVE_YARD_WORDS = {"front_yard": "front yard", "side_yard_smaller": "side yard", "side_yard_larger": "side yard",
                 "rear_yard": "rear yard"}


def _reading_words(tag: str, rid: str) -> str:
    for model, words in MODEL_WORDS.items():          # measure.EAVE (per solid for the height), measure.PROJ
        if tag == model or tag.startswith(model + ":"):
            return words.get(rid, rid)
    return rid.replace("_", " ")


def _eave_text(found: dict, measured: dict) -> str | None:
    """For a row that needs review only because something might be an eave: what to confirm, in plain words
    ("confirm the part reaching 1'-6" past the walls toward the front yard is an eave (§325-18B allows up to 2 ft
    into a required yard)"), or None when the eave question isn't what decides it."""
    tags = found["tags"]
    if not any(t == "model#eave" or t.startswith("model#eave:") for t in tags) or found["result"] != "mixed":
        return None
    if any(MODEL_WORDS["model#eave"]["eave"] in w for w in found["fails_under"]):
        return None                         # it fails even with the overhang an eave: not just a confirmation
    reach = []
    for yard in dict.fromkeys(EAVE_YARD_WORDS.values()):
        # each reading read with the overhang an eave, against the same reading (the same lot lines, the same
        # other answers) with it not, to the same lot line: the most it reaches, over every reading, never one
        # reading picked by the order the readings came in (stress F7), never the narrower side yard under one
        # reading against the other side's under another (review round 15: the two side yards are paired by line)
        pairs = {}
        for name in (n for n, y in EAVE_YARD_WORDS.items() if y == yard):
            for r in (measured.get(name) or {}).get("readings") or []:
                side = (r.get("named") or {}).get("model#eave")
                if side in ("eave", "not_eave") and r.get("value") is not None:
                    rest = tuple(sorted((t, v) for t, v in r["named"].items() if t != "model#eave"))
                    words = "; ".join(w for w in r["reading"].split("; ")
                                      if not w.startswith("what reaches past the walls"))
                    line = tuple(r["line"]) if r.get("line") is not None else name
                    pairs.setdefault((rest, words, line), {})[side] = r["value"]
        gaps = [p["eave"] - p["not_eave"] for p in pairs.values() if "eave" in p and "not_eave" in p]
        if gaps and max(gaps) > 1e-6:
            reach.append(f"{present.feet_inches(max(gaps), 'up')} past the walls toward the {yard}")
    where = ("the part reaching " + "; ".join(dict.fromkeys(reach))) if reach else "what the roof reaches past the walls"
    return (f"it complies only if {where} is an eave (§325-18B allows eaves up to 2 ft into a required yard). "
            "Gordium will ask you to confirm it in the panel in the next release; until then this stays needs review")


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


def every_reading(rule: dict, measured: dict, allowed: dict, facts: dict | None = None) -> tuple[str, str] | None:
    """For a rule that needs review only because measurements have readings instead of a value: ("pass", how) if
    it passes under every reading, ("fail", how) if it fails under every one, else None (or when a measurement
    has no reading, or there are too many). The readings are THE reading set (reading_set.combos: those of one
    lot reading together; with `facts` on a tax-map lot, also the lot lines' slack and the lot area's low and
    high), the same set the panel's words and colours come from (present.settle). Never a result: the row stays
    NEEDS REVIEW (only outcome() decides results); this says the design complies, or doesn't, whichever way the
    open question is answered."""
    names = reading_set.rule_names(rule)
    open_ = sorted(n for n in names if (measured.get(n) or {}).get("value") is None)
    values = {k: m["value"] for k, m in measured.items()}
    every = reading_set.combos(names, values, measured, facts) if open_ else None
    if not every:
        return None
    got = {outcome(rule, trial, allowed) for trial, _ in every}
    if got not in ({"pass"}, {"fail"}):
        return None
    word = "passes" if got == {"pass"} else "fails"
    survey = SURVEY in open_ and len((measured.get(SURVEY) or {}).get("readings") or []) == 1
    others = [n for n in open_ if n != SURVEY or not survey]
    return got.pop(), (f"{word} with the lot as drawn (confirm the survey)" if survey and not others else
                       f"{word} under every reading" +
                       (" and with the lot as drawn (confirm the survey)" if survey else ""))


def fails_whatever(rule: dict, measured: dict, allowed: dict, facts: dict | None = None) -> dict | None:
    """The every-reading rule for values that aren't measured or given at all (decided 2026-10-21): a rule that
    fails for every value they could take does not comply. Returns {"names": the unknown measurements, "settings":
    the values it was proven under}, or None.

    Proven, never sampled. Each unknown number (no value, no readings) is one the rule's check is provably truest
    at when it is 0 (formula.truth_direction -1: only +, -, max/min and positive multiples of it, compared with
    < <= > >=; the §325-16C height bonus is one): it is taken at 0 (measures are never negative). Each unknown
    yes/no fact is tried both ways. None of them is in the rule's applies_when or review_when. The rule fails
    under every one of those settings: then it fails whatever they are. Any other unknown (a text, a number not
    proven), or a pass under any setting, and it is None. Never the other way: missing data never makes a rule
    comply (principle 4)."""
    if rule.get("kind") != "rule" or not rule.get("check"):
        return None
    names = reading_set.rule_names(rule)
    unknown = sorted(n for n in names if (measured.get(n) or {}).get("value") is None
                     and not (measured.get(n) or {}).get("readings"))
    settings = unknown_settings(rule, unknown, MEASURE_KINDS)     # the proof's settings (shared with parts.rows)
    if settings is None:
        return None
    values = {k: m["value"] for k, m in measured.items()}
    # the rest over THE reading set (each reading of what has readings; on a tax-map lot the lines' slack and the
    # lot area's low and high): it fails whatever the unknown values are only if it fails under every one of them
    every = reading_set.combos(names - set(unknown), values, measured, facts)
    if every is None:
        return None
    trials = [t for t, _ in every] or [values]
    if all(outcome(rule, {**t, **s}, allowed) == "fail" for t in trials for s in settings):
        return {"names": unknown, "settings": settings}
    return None


def waits_on_interior(row: dict, rule: dict, measured: dict, allowed: dict) -> bool:
    """Whether a row goes in its own group, "not checked yet: interior": it needs review only because a fact about
    the inside of the building (INTERIOR) isn't given, and it isn't already proven to fail whatever that fact is
    (fails_whatever, run first: nothing that fails is ever hidden; #20 review round 2)."""
    names = formula.names(rule["check"]) if rule.get("check") else set()      # a flag has no check
    return (row["Error"] == "NEEDS REVIEW"
            and any((measured.get(n) or {}).get("value") is None for n in names & INTERIOR)
            and not fails_whatever(rule, measured, allowed))


def crossing(rule: dict, measured: dict) -> str | None:
    """"The main building crosses the side lot line" when a building this rule measures stands partly off the lot
    (its measurements' `crossings`, each building its own): the rule does not comply whatever the readings or
    answers. None otherwise."""
    names = set()
    for key in ("applies_when", "check"):
        if rule.get(key):
            names |= formula.names(rule[key])
    found = {}
    for n in sorted(names):
        for c in (measured.get(n) or {}).get("crossings") or []:
            found.setdefault(c["who"], set()).update(c["lines"])
    if not found:
        return None
    def where(lines):
        if not lines:                                   # past a corner, or a line that can't be named
            return "it reaches past the lot line"
        return f"it crosses the {' and '.join(sorted(lines))} lot line{'s' if len(lines) > 1 else ''}"
    text = "; ".join(f"{who} is not entirely on the lot ({where(lines)})" for who, lines in found.items())
    return text[:1].upper() + text[1:]


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
    if found["result"] == "pass" and all(t.startswith("model#") for t in found["tags"]):
        text = "complies to the full outline, whatever reaches past the walls is"    # eaves don't matter here
    text = _eave_text(found, measured) or text
    return {**found, "text": text}


def turns_on(rule: dict, measured: dict, allowed: dict, facts: dict | None = None) -> list[str] | None:
    """The open measurements a rule's result turns on: each whose readings it needs (with it unknown and everything
    else at any of its readings from THE reading set, the result can't be told). An open question it doesn't turn
    on doesn't hold it back (either answer gives the same result). None if there are too many readings."""
    names = reading_set.rule_names(rule)
    values = {k: m["value"] for k, m in measured.items()}
    out = []
    for n in sorted(n for n in names if values.get(n) is None and (measured.get(n) or {}).get("readings")):
        every = reading_set.combos(names - {n}, values, measured, facts)
        if every is None:
            return None
        if any(outcome(rule, dict(trial, **{n: None}), allowed) == "needs_review" for trial, _ in every or [(values, None)]):
            out.append(n)
    return out


def row_verdict(rule: dict, measured: dict, allowed: dict, facts: dict | None = None, check: str | None = None) -> str:
    """THE verdict of a rule (or, with `check`, of one of its comparisons: a side yard of a pair, with the rule's
    applies_when and review_when) over THE reading set (reading_set.combos): fails if it fails under every reading;
    complies if it passes under every one and turns on no open question (turns_on; the lot area of a tax-map lot
    is read at its low and high ends, so it counts as known); otherwise needs review. The ONLY place a row is
    decided: the panel shows this or something more cautious, never more favourable (review round 3)."""
    rule = dict(rule, check=check) if check else rule
    names = reading_set.rule_names(rule)
    values = {k: m["value"] for k, m in measured.items()}
    tax = reading_set.tax_map(measured, facts)
    every = reading_set.combos(names, values, measured, facts)
    if not every:                                   # a value unknown, or too many: as drawn, never kinder
        got = outcome(rule, values, allowed)
        lot = names & (reading_set.LOT_LENGTHS | {SURVEY})
        if got == "needs_review" and every is not None and fails_whatever(rule, measured, allowed, facts):
            return present.FAILS                    # fails whatever the values not measured are (decided 2026-10-21)
        if got == "fail" and tax and lot:
            # fails as drawn with a value unknown: on the tax map it fails only if it fails with the lines off
            # either way too, over what is known (the unknown values stay unknown: a fail here doesn't need them,
            # as a 45 ft house is over the most the height bonus allows whatever its yards: stress F13)
            known = {n for n in names if values.get(n) is not None or (measured.get(n) or {}).get("readings")}
            rest = reading_set.combos(known, values, measured, facts)
            if rest and all(outcome(rule, trial, allowed) == "fail" for trial, _ in rest):
                return present.FAILS
        return present.FAILS if got == "fail" and not (tax and lot) else \
            present.COMPLIES if got == "pass" and not (tax and lot) else present.REVIEW
    got = {outcome(rule, trial, allowed) for trial, _ in every}
    if got == {"fail"}:
        return present.FAILS
    turns = turns_on(rule, measured, allowed, facts)
    open_ = (set(turns) if turns is not None else {n for n in names if values.get(n) is None}) - \
        ({SURVEY} if tax else set())
    if got == {"pass"} and open_:
        # every reading research lists for the open questions (named, kind: reading): complies only if it passes
        # under all of them, and nothing else is open (PR 18's every-reading rule)
        named = named_result(rule, measured, allowed)
        if named and named["result"] == "pass" and set(named["open"]) >= open_:
            return present.COMPLIES
    return present.COMPLIES if got == {"pass"} and not open_ else present.REVIEW


def _changed(measured: dict, changes: dict) -> dict:
    """The measurements with each named one changed by its amount (its value and every reading of it): the design
    as a "To comply" would leave it."""
    out = dict(measured)
    for m, d in changes.items():
        rec = dict(measured.get(m) or {})
        if isinstance(rec.get("value"), (int, float)):
            rec["value"] = rec["value"] + d
        rec["readings"] = [dict(r, value=r["value"] + d) if isinstance(r.get("value"), (int, float)) else r
                           for r in rec.get("readings") or []]
        out[m] = rec
    return out


def _raised_by(rules: list, values: dict) -> dict:
    """measure -> [(rule, comparison)]: the yards a rule with several ways to comply raises as the design stands
    (`values`): its first way not met, another way met, that way's comparison on the yard (the height bonus), as
    present._raise_yards shows them on the panel."""
    out = {}
    for rule in rules:
        body = formula.parse(rule["check"]).body if rule.get("check") else None
        if not (isinstance(body, ast.BoolOp) and isinstance(body.op, ast.Or)):
            continue
        if present._evaluate(ast.unparse(body.values[0]), values) is not False:
            continue
        for alt in body.values[1:]:
            if present._evaluate(ast.unparse(alt), values) is not True:
                continue
            for c in [alt] if isinstance(alt, ast.Compare) else getattr(alt, "values", []):
                if isinstance(c, ast.Compare) and isinstance(c.left, ast.Name) and c.left.id in present.YARD_MEASURES:
                    out.setdefault(c.left.id, []).append((rule, ast.unparse(c)))
            break
    return out


def confirm_advice(items: list[dict], by_id: dict, measured: dict, allowed: dict, facts: dict,
                   site: dict | None = None) -> None:
    """Every "To comply" is the checker's to confirm. Each piece (each way, each "…if it stays that tall" clause) is
    applied to the measurements and every row decided again by row_verdict, a yard with any raise the height bonus
    then puts on it, as the panel shows it: the piece is kept only if its row then complies, every rule it answers
    to complies (a clause: the whole height rule), and no other row is worse than it is now (review round 4: a move
    re-checked against its own row and its opposite yard alone newly failed side yards on a narrowing lot, and a
    raised rear yard; the "if it stays tall" figure, other raised yards). Pieces only ever change one measurement,
    one wall pulled back, so the re-decision is exact. Nothing left: no hint. A "To comply" with no change the
    checker can try is dropped (the architect's review, pass 2; round 2, R1: 106's rear yard told to move)."""
    rules = [by_id[i["rule"]] for i in items if by_id.get(i.get("rule"))]
    rules = list({r["id"]: r for r in rules}.values())

    def statuses(changes):
        changed = _changed(measured, changes)
        raised = _raised_by(rules, {k: m.get("value") for k, m in changed.items()})
        out = {}
        for it in items:
            rule = by_id.get(it.get("rule"))
            if rule is None:
                continue
            m = it.get("measure")
            st = row_verdict(rule, changed, allowed, facts, check=side_checks(rule).get(m))
            for r, e in raised.get(m) or []:
                got = row_verdict(r, changed, allowed, facts, check=e)
                st = got if present.RANK[got] < present.RANK[st] else st
            out[it["id"]] = st
        return out

    before = None
    for i in items:
        advice = i.pop("_advice", None)
        if not (i.get("hint") or "").startswith("To comply"):
            continue
        if advice is None or by_id.get(i.get("rule")) is None:
            i["hint"] = None
            continue
        if advice.get("crossing"):       # a building partly off the lot: "move it back onto the lot" is the one
            continue                     # advice, a fact no measured change can simulate (kept as said: PR 18)
        before = before or statuses({})

        def holds(part):
            if not part["changes"]:
                return False
            after = statuses(part["changes"])
            changed = _changed(measured, part["changes"])
            return after.get(i["id"]) == present.COMPLIES \
                and all(row_verdict(by_id[r], changed, allowed, facts, check=e) == present.COMPLIES
                        for r, e in part.get("also") or [] if r in by_id) \
                and all(present.RANK[after[k]] >= present.RANK[v] for k, v in before.items() if k in after)

        ways = [w for w in advice["ways"] if holds(w)]
        clauses = [c for c in advice.get("clauses") or [] if holds(c)]
        i["hint"] = present.advice_text(dict(advice, ways=ways, clauses=clauses))


def side_lines(site: dict, facts: dict) -> list[str] | None:
    """The true compass names of the lot's two side lines, each from the lot's middle to the line: what a side yard
    is called when it couldn't be measured. Only when the measuring itself knows which lines are sides: the lot not
    a corner lot (unknown counts as maybe), and every reading of its lines giving the same two names (review round
    1). None otherwise, or without a lot."""
    from model_measurement.plugin_measuring import Lot
    if facts.get("corner_lot") is not False or not (site.get("lot") or {}).get("edges") or not facts.get("street_line"):
        return None
    lot = Lot(site, facts)
    readings = None if lot.problems or lot.street_problem else lot.readings()
    if not readings:
        return None
    middle = lot.polygon.centroid
    pairs = set()
    for _, left, right, _ in readings:
        names = [present.compass(lot.line(g).centroid.x - middle.x, lot.line(g).centroid.y - middle.y,
                                 facts.get("plan_north_deg") or 0.0) for g in (left, right)]
        if not all(names):
            return None
        pairs.add(tuple(sorted(names)))
    return list(pairs.pop()) if len(pairs) == 1 else None


def side_checks(rule: dict) -> dict:
    """A rule's comparisons of the two side yards, each as its own check (the panel shows each side as a row)."""
    if not rule.get("check"):
        return {}
    return {c.left.id: ast.unparse(c) for c in present._compares(rule["check"])
            if c.left.id in ("side_yard_smaller", "side_yard_larger")}


def verdict(rule: dict, measured: dict, allowed: dict) -> str:
    """The checker's own result for one rule, as its rows mark it: outcome(), except that a needs review that fails
    under every reading (or with the lot as drawn) is a "fail" (the row's "Fails")."""
    got = outcome(rule, {k: m["value"] for k, m in measured.items()}, allowed)
    if got == "needs_review":
        found = every_reading(rule, measured, allowed)
        if found and found[0] == "fail" or fails_whatever(rule, measured, allowed):
            return "fail"
    return got


def largest_legal_building(site: dict, facts: dict, measured: dict, rules: list[dict], **options) -> dict:
    """envelope_builder's largest legal building, proven with the checker's own verdict (above) before it is
    placed: never a building the check that follows shows as not complying (audit P1-3)."""
    return generator.largest_legal_building(site, facts, measured, rules, verdict=verdict, **options)


def _rules_pass(n: int) -> str:
    return f"{n} rule passes" if n == 1 else f"{n} rules pass"


def summary(rows: list[dict], items: list[dict] | None = None) -> dict:
    """The check's own one-line answer (the result's "summary"): all pass; it complies under every reading (rules
    waiting only on how the law is read, each passing whichever way it goes); or what fails and what needs review. A
    rule that passes only with the lot as drawn still needs review (amber) until the survey is confirmed: a lot not
    yet surveyed is a missing fact, not a reading, so it is never shown as complying. No row at all is "Nothing
    checked", needs review: a check that decided nothing never passes.

    Given the view's `items`, it is never less cautious than the panel (Ben, 2026-11-09): its state is the panel's
    (present.state) whenever that is the more cautious one, and its text is the panel's own line (present.summary, one
    summary everywhere: D3), so a row still waiting (a fact to answer, the bedrooms; a rule not in this release, the
    overlays), a rule's row the panel holds at needs review (a doubtful looked-up fact, a tax-map reading) and a row
    that isn't a rule's (objects on the lot not included, lot facts that disagree) are never left out of it. Its
    lines: the rule rows' own, then each counted row of the view that fails, needs review or waits and isn't already
    among them."""
    s = _rows_summary(rows)
    if items is None:
        return s
    view = present.state(items)
    caution = {"fail": 3, "review": 2, "complies": 1, "pass": 0}
    floor = {present.FAILS: "fail", present.REVIEW: "review"}.get(view, s["state"])
    state = max(s["state"], floor, key=caution.__getitem__)
    fails, review, _ = _sorted_rows(rows)
    said = {r.get("Rule id") for r in fails + review}          # the rows its own lines already say
    # (a rule the rows hold at review but the panel says fails gets the panel's reason too: review round 4)
    failed = {r.get("Rule id") for r in fails}
    extra = [i for i in present._building_items(items) if i["status"] != present.COMPLIES
             and not (i.get("rule") and i["rule"] in (failed if i["status"] == present.FAILS else said))]
    return {"state": state, "text": present.summary(items), "lines": s["lines"] + [
        f"{short(i['name'])}: {i['reason']}" if i.get("reason") else short(i["name"]) for i in extra]}


def _sorted_rows(rows: list[dict]) -> tuple[list, list, list]:
    """The rule rows as (fails, review, passes)."""
    # counted from the checker's one decision (row_verdict) only: a needs-review row never counts as passing,
    # whatever its named readings say (review round 20); a row without a verdict, by its outcome
    def verdict_of(r):
        return r.get("Verdict") or (present.FAILS if r.get("Fails") or r["Error"] == "FAIL" else
                                    present.COMPLIES if r["Error"] == "PASS" else present.REVIEW)
    fails = [r for r in rows if verdict_of(r) == present.FAILS or r.get("Fails")]
    review = [r for r in rows if verdict_of(r) == present.REVIEW and r not in fails]
    passes = [r for r in rows if verdict_of(r) == present.COMPLIES and r not in fails]
    return fails, review, passes


def _rows_summary(rows: list[dict]) -> dict:
    """summary() from the rule rows alone: a line for each of its fails and review rows."""
    fails, review, passes = _sorted_rows(rows)
    if not fails and not review and not passes:     # nothing checked is never a pass (principle 4)
        return {"state": "review", "text": "Nothing checked", "lines": []}
    if not fails and not review:
        return {"state": "pass", "text": f"All {len(passes)} rules pass", "lines": []}
    if not fails and all(r.get("Provisional") and not r.get("Survey") for r in review):
        waiting = {}
        for r in review:
            waiting.setdefault(r["Provisional"], []).append(short(r["Requirement"]))
        return {"state": "complies", "text": f"Complies: {_rules_pass(len(passes))}, {len(review)} pass whichever "
                                             "way open questions go",
                "lines": [", ".join(names) + ": " + why for why, names in waiting.items()]}
    lines = [r.get("Line") or (_amount(r) if r["Error"] == "FAIL" else f"{short(r['Requirement'])}: {r['Provisional']}")
             for r in fails]
    lines += [f"{short(r['Requirement'])}: {r.get('Provisional') or (r.get('Named') or {}).get('text') or r['Why']}"
              for r in review]
    # counted in rules, said so: the panel counts its rows, and one rule can be two rows (the side yards: the
    # audit of main, 2026-10-29: "8 pass" beside the panel's "9 comply")
    counts = _rules_pass(len(passes)) + (f" · {len(fails)} fail" if fails else "") + (
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


def _report(t: dict, view: dict, report_path: Path, site_file: "Path | list[Path] | None" = None,
            interior_sha256: str | None = None, interior_waiting: bool = True) -> None:
    """The architects'-format workbook (PR 10), saying what the panel says (spec I1, I2): each rule's Error and
    Comparison are its items' most cautious status (a rule the panel shows as needing review is never PASS here),
    and a Check tab lists every item, the summary, the draft-rulebook label and the lot and grade sources."""
    from rule_export.workbook import title, write_block
    word = {present.FAILS: ("FAIL", "Outside table limit"), present.REVIEW: ("NEEDS REVIEW", "Needs review"),
            present.COMPLIES: ("PASS", "Within table limit"), present.NOT_CHECKED: ("NOT CHECKED", "Needs input")}
    worst, shown = {}, {}
    for i in view["items"]:
        if i["rule"] and i["status"] in word:
            rank = present.ORDER.index(i["status"])
            if i["rule"] not in worst or rank < present.ORDER.index(worst[i["rule"]][0]):
                worst[i["rule"]] = (i["status"], i.get("reason") or "")
            shown.setdefault(i["rule"], []).append(i)
    col = {h: n for n, h in enumerate(COLUMNS)}
    rows = []
    for r in t["output"]:
        r = list(r)
        found = worst.get(r[col["Rule id"]])
        if found:
            # every column of the row from the panel's items (the same verdicts): its Error, Comparison and Why,
            # and what it shows as Proposed, so a PASS never sits beside "Can't check: … missing"
            r[col["Error"]], r[col["Comparison"]] = word[found[0]]
            r[col["Why it needs review"]] = found[1] if found[0] == present.REVIEW else ""
            items = [i for i in shown[r[col["Rule id"]]] if i.get("proposed")]
            if len(items) == 1:         # the row as the panel shows it, in one unit: limit, proposed, units
                r[col["Proposed"]] = items[0]["proposed"]
                if items[0].get("required") and items[0].get("sign"):
                    r[col["Table limit"]] = f"{items[0]['sign']} {items[0]['required']}"
                if "%" in str(items[0]["proposed"]):            # coverage: a share of the lot area, not sf
                    r[col["Units"]] = "% of lot area"
            elif items:
                r[col["Proposed"]] = "; ".join(f"{i['name']}: {i['proposed']}" for i in items)
        rows.append(r)
    # an input the measurement couldn't settle (a tax-map lot's area) shows what the panel shows, said as drawn
    by_measure = {i.get("measure"): i for i in view["items"] if i.get("measure") and i.get("proposed")}
    inputs = []
    for r in t["inputs"]:
        r = list(r)
        i = by_measure.get(r[0].lower().replace(" ", "_"))
        if r[1] is None and i is not None and "%" not in str(i["proposed"]):     # only in the input's own unit
            r[1], r[3] = i["proposed"], "as drawn (the panel's reading); " + str(r[3])
        inputs.append(r)
    wb = build({**t, "output": rows, "inputs": inputs, "title": view["header"].get("place") or t["title"]})
    ws = wb.create_sheet("Check")
    h = view["header"]
    title(ws, f"GORDIUM | {view['summary']}")
    lines = [h["place"], h["code"], h["draft"], h["lot"], h["grade"]] + ([h["main"]] if h.get("main") else []) + \
        (h.get("sources") or [])   # where each fact came from
    # which interior the egress rows were worked out from (its fingerprint), so a saved report is traceable to it
    lines.append("Interior: none drawn yet" if not interior_sha256 else
                 f"Interior: sha256 {interior_sha256} (no rooms drawn yet, egress not checked)" if interior_waiting
                 else f"Interior checked: sha256 {interior_sha256}")
    note = next((i["detail"]["outline"] for i in view["items"] if (i.get("detail") or {}).get("outline")), None)
    if note:                            # the lot lines read from a cleaned outline: said once, with the lot (PR 18)
        lines.append("Lot lines: " + note)
    for n, text in enumerate(lines, start=2):
        ws.cell(row=n, column=1, value=text)
    by_id = {i["id"]: i for i in view["items"]}
    out = []
    for g in present.grouped(view["items"]):
        for item_id in g["items"]:
            i = by_id[item_id]
            # the note ("assuming flat ground") with the item, as the panel shows it; that column is reasons only
            out.append([g["title"], i["mark"], i["name"] + (" · " + i["note"] if i.get("note") else ""), i["proposed"],
                        i["required"], i.get("delta") or "", i.get("reason") or "",
                        i["detail"].get("citation") or "",
                        (i["detail"].get("links") or [""])[0]])
    write_block(ws, len(lines) + 3, [("Group", 22), ("Mark", 6), ("Item", 34), ("Proposed", 12), ("Required", 12),
                                     (COLUMN_DELTA, 10), ("Why it needs review", 60), ("Citation", 50), ("Link", 40)], out)
    wb.move_sheet("Check", offset=-wb.sheetnames.index("Check"))     # the architect's sheet first, open on it
    wb.active = 0
    for ws_ in wb.worksheets:
        ws_.sheet_view.tabSelected = ws_.title == "Check"
    # written beside it, then moved into place: a write that fails half way never leaves a broken report there
    report_path = Path(report_path)
    part = report_path.with_name("." + report_path.name + ".part")
    files = [] if site_file is None else [Path(site_file)] if isinstance(site_file, (str, Path)) else list(site_file)
    try:
        wb.save(part)
        # the earlier report's site file (and its interior file: check_description's) is set aside, not deleted,
        # until the new report is in place: a report that can't be moved in (open in Excel on Windows) leaves the
        # earlier one beside its own site and interior
        aside = []
        for kept in files:
            if not kept.exists():
                continue
            try:
                os.replace(kept, _aside(kept))
            except OSError as e:             # said as that file's trouble, not the report's
                _put_back(aside)
                raise _SiteInTheWay(e, kept, report_path) from e
            aside.append(kept)
        try:
            os.replace(part, report_path)
        except BaseException:                # not moved in (or stopped right here): the earlier files go back,
            if part.exists():                # unless the move did happen (its part is gone)
                _put_back(aside)
            raise
    finally:
        if part.exists():
            part.unlink()


def _put_back(aside: list) -> None:
    """The earlier report's files set aside, each put back; the first that can't be is raised after the rest are tried
    (one that can't go back stays set aside: it is the earlier report's only copy)."""
    failed = None
    for kept in aside:
        try:
            os.replace(_aside(kept), kept)
        except OSError as e:
            failed = failed or e
    if failed is not None:
        raise failed


# What a check or a start is doing, in the architect's words, as each stage begins (the plugin's progress line)
STEPS = {"read": "Reading the model…", "measure": "Measuring the building…", "rules": "Checking the rules…",
         "report": "Writing the zoning report…", "lot": "Reading the lot…",
         "largest": "Finding the largest building that complies…"}


def _quiet(text: str) -> None:
    """No progress line (the command line, the tests)."""


def check(model_path: Path, facts: dict, report_path: Path | None = None, building_problems: list | None = None,
          extras: dict | None = None, step=None, today: str | None = None, interior: dict | None = None) -> dict:
    """Everything the Rhino command shows, for one model and its lot facts. `building_problems` are what the
    Rhino command found on the Building layer and couldn't send (a block, a surface): each one makes every
    building measure need review, never silently dropped. `extras` is what the command adds for the panel: what
    it sent (scope), objects on the lot it didn't send (each makes the check need review), the grade source.

    The model goes through the site description another design tool sends (site_json, docs/protocol/): read, made a
    description (the grade from the facts, the unsent objects and the left-out ones from the request), written as
    JSON text and read back, then checked by check_description, so Rhino's check takes the path Revit's will.
    `today` is the day of the check as YYYY-MM-DD, given by the host (the plugin: rhino_logic.city_day): how old a
    saved lookup is (present.overlays_lookup). The checker never reads the clock; without it, no lookup counts as
    recent, so the overlays row stays. `interior`: the interior description (gordium.interior/1), or None when
    no interior is drawn (egress then waits: egress.py)."""
    today = present.checked_today(today)       # a day that isn't one: refused before anything is read
    problems = fact_problems(facts)            # the same check as a facts file: a plain refusal, never a crash
    problems += [f"no {k} given" for k in ("jurisdiction", "zone") if not facts.get(k)]
    if problems:
        raise ValueError("lot facts: " + "; ".join(problems))
    model_path = Path(model_path)
    (step or _quiet)(STEPS["read"])
    doc = site_json.legacy_description(read_site(model_path, facts), facts, building_problems, extras,
                                       _host(model_path))
    return check_description(site_json.through_json(doc), _without(facts, ("grade_points",)), report_path,
                             _without(extras or {}, site_json.LEFT_OUT_EXTRAS), step=step, name=model_path.name,
                             today=today, interior=interior)


def _without(d: dict, keys) -> dict:
    return {k: v for k, v in d.items() if k not in keys}


def _host(model_path: Path) -> dict:
    """Which file a check read (for tracing in the description; never used in a decision)."""
    import rhino3dm
    return {"name": "gordium check (rhino3dm)", "version": rhino3dm.__version__, "document": Path(model_path).name,
            "model_units": "feet (read_site converts)"}


SITE_SUFFIX = ".site.json"      # beside a zoning report: the exact site description it was worked out from
INTERIOR_SUFFIX = ".interior.json"   # beside it too: the exact interior description its egress rows were worked out from


def _described(kept: Path) -> str:
    """Which description a file beside a report holds, in the report_error's words."""
    return "the interior description" if kept.name.endswith(INTERIOR_SUFFIX) else "the site description"


class _SiteInTheWay(OSError):
    """The earlier report's site or interior file couldn't be set aside (locked, say): the new report wasn't moved in."""

    def __init__(self, error: OSError, site_file: Path, report_path: Path):
        super().__init__(error.errno, error.strerror)
        self.words = (f"{_described(site_file)} beside the report: {error.strerror or error} ({site_file}), so the new "
                      f"report wasn't saved ({report_path})")


def _aside(site_file: Path) -> Path:
    """Where the earlier report's site file waits while the new report is moved in (hidden, never read back)."""
    return site_file.with_name("." + site_file.name + ".old")


def check_description(doc: dict, facts: dict, report_path: Path | None = None, extras: dict | None = None,
                      step=None, name: str | None = None, today: str | None = None, interior: dict | None = None) -> dict:
    """check() for a site description (gordium.site/1: site_json; the worker's check_site): refused whole if it
    isn't exactly v1 (site_json.SiteRefused), else measured and checked as check_site does. With a report, the
    description is kept beside it (<report name>.site.json), so any report can be traced to exactly the site it was
    worked out from and, with the same lot facts (not in the site file), worked out again. A report is never beside
    another check's site: the new site file is written (as a hidden part file) before the report; the earlier one is
    set aside only once the new report is saved, put back if that report can't be moved in, and dropped once it is;
    then the new one is moved in. A site file that can't be written means no report is written, and the earlier
    report keeps its site (report_error says why); at worst, a check stopped between the two leaves a report with no
    site file beside it, never a wrong one. `today`: the host's day, as check() takes it; `interior`: the interior
    description, as check_site takes it (beside the site description, never inside it: gordium.site/1 is
    unchanged).

    The interior is kept the same way, beside the site (<report name>.interior.json), so the report's egress rows can
    be worked out again too (the Revit interior design note, section 5): written first, moved in with the site, and
    never an earlier check's interior left beside a new report: a check with no interior sets the earlier one aside
    with the earlier site and drops it once the new report is in (put back with it if the report can't be)."""
    today = present.checked_today(today)     # a day that isn't one: refused before any file is touched
    site, facts, extras = site_json.for_measuring(site_json.to_site(doc), facts, extras)
    _refuse_bad_facts(facts)                 # a refused request leaves the earlier report and its site alone
    beside, site_error = [], None            # beside: (kept file, its part file, its description or None)
    if report_path is not None:
        report_path = Path(report_path)
        for suffix, content in ((SITE_SUFFIX, doc), (INTERIOR_SUFFIX, interior)):
            kept = report_path.with_name(report_path.stem + suffix)
            part = kept.with_name("." + kept.name + ".part")    # as the report's own half-written copy is named
            beside.append((kept, part, content))
            if content is None or site_error is not None:
                continue
            try:
                text = json.dumps(content, indent=1, sort_keys=True, allow_nan=False) + "\n"
            except ValueError as e:          # not strict JSON (a NaN): not kept, so no report (review round 1)
                site_error = (_NotWritten(OSError(None, f"it isn't strict JSON ({e})")), kept)
                continue
            try:
                part.write_text(text, encoding="utf-8")
            except OSError as e:
                site_error = (_NotWritten(e), kept)
    try:                                     # a site that can't be kept: no report written (the earlier one stays)
        out = check_site(site, facts, name or doc["host"]["document"] or "model",
                         None if site_error else report_path, extras, step=step,
                         site_file=None if site_error or not beside else [kept for kept, _, _ in beside],
                         today=today, interior=interior)
    except BaseException:                    # stopped or failed: no half-written file left behind; an earlier one
        for kept, part, _ in beside:         # still set aside is the replaced report's (_report puts it back when
            _unlink(part)                    # its report isn't moved in), so it goes
            _unlink(_aside(kept))
        raise
    if beside:
        moved = []
        if out["report_error"] is None and site_error is None:
            for kept, part, content in beside:
                if content is None:
                    continue
                try:
                    os.replace(part, kept)
                except OSError as e:
                    site_error = (e, kept)
                    break
                moved.append(kept)
        if site_error is not None and out["report_error"] is None:     # never a report beside the wrong site
            error, kept = site_error
            if not isinstance(error, _NotWritten):
                _unlink(report_path)
                for done in moved:           # beside no report now: gone with it
                    _unlink(done)
            out["report_error"] = (f"{_described(kept)} beside the report: {error.strerror or error} "
                                   f"({kept}), so the new report wasn't saved ({report_path})")
        for kept, part, _ in beside:
            _unlink(part)
            if out["report_error"] is None or site_error is not None:  # the report it was beside was replaced; else
                _unlink(_aside(kept))        # it was put back, or, if that failed, is the earlier report's only copy
    return out


class _NotWritten(OSError):
    """The site or interior file couldn't be written before the check (or isn't strict JSON): the report wasn't written
    either."""

    def __init__(self, error: OSError):
        super().__init__(error.errno, error.strerror)


def _refuse_bad_facts(facts: dict) -> None:
    problems = fact_problems(facts) + [f"no {k} given" for k in ("jurisdiction", "zone") if not facts.get(k)]
    if problems:
        raise ValueError("lot facts: " + "; ".join(problems))
    egress.refuse_state_alone(facts["jurisdiction"])     # a state's law is checked only through a place
    if no_rules_for(facts):                    # said plainly, never the report's temporary file and its words
        raise ValueError(no_rules_for(facts))


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def no_rules_for(facts: dict) -> str | None:
    """Why a district can't be checked, in plain words, when it has no rulebook (saved facts naming B-1a raised the
    report's own "<temp path>/project.yaml: no rulebook for zone 'B-1a' in …": the audit of main, 2026-10-29);
    None when it has one. The districts that do are listed from the rulebooks themselves."""
    j = REPO / facts["jurisdiction"]
    if rulebook_for(j, facts["zone"]) is not None:
        return None
    have = sorted({p.stem for folder in (j / "5_zoning_rules", j / "5_zoning_rules/drafted") if folder.is_dir()
                   for p in folder.glob("*.yaml")}, key=lambda z: [int(t) if t.isdigit() else t.lower()
                                                                  for t in re.split(r"(\d+)", z)])
    listed = ", ".join(have[:-1]) + " and " + have[-1] if len(have) > 1 else "".join(have) or "none yet"
    return f"Gordium doesn't have rules for district {facts['zone']} yet. It has rules for {listed}."


def check_site(site: dict, facts: dict, name: str = "model", report_path: Path | None = None,
               extras: dict | None = None, step=None, site_file: Path | None = None,
               today: str | None = None, interior: dict | None = None) -> dict:
    """check() for a site already read (the lot and the buildings, in feet), e.g. one a test or a scenario
    generator builds. Exactly the same measuring, rules and presentation as a model read from a file. `site_file`
    (check_description's) is set aside while the report is moved in, and put back if it can't be.

    The place's zoning, and every state law it inherits (egress: New York's house code for Ithaca) run on the
    interior's parts: `interior` is the interior description (gordium.interior/1), or None when none is drawn, and
    then each inherited law waits ("waiting, no rooms drawn yet"), never a pass (egress.py). The view's `sections`
    give each law's own state; its state and summary are over both."""
    today = present.checked_today(today)
    _refuse_bad_facts(facts)
    site = in_words(site)           # problems as words, coded ones too ({code, args}): the report says them plainly
    model_path = Path(name)
    say = step or _quiet
    say(STEPS["measure"])
    measured = measuring(facts["jurisdiction"]).measure(site, facts)     # the lot's own place's measuring
    project = {"title": facts.get("title") or model_path.stem, "jurisdiction": facts.get("jurisdiction"),
               "zone": facts.get("zone"),
               "measurements": {k: {"value": m["value"], "from": working(m, model_path.name)} for k, m in measured.items()}}
    say(STEPS["rules"])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "project.yaml"
        path.write_text(yaml.safe_dump(project, sort_keys=False, allow_unicode=True), encoding="utf-8")
        t = tables(path)              # refuses a project or rulebook that fails its checks (ValueError)
    rules = load(rulebook_for(REPO / facts["jurisdiction"], facts["zone"]))["rules"]
    by_id = {r["id"]: r for r in rules}
    allowed = {"use": Context.for_jurisdiction(REPO / facts["jurisdiction"]).uses}
    every = [_why(dict(zip(COLUMNS, r)), by_id, measured, allowed, facts) for r in t["output"]]
    waiting = [r for r in every if waits_on_interior(r, by_id[r["Rule id"]], measured, allowed)]
    for r in waiting:                   # exactly which stated facts each one waits for (its "Enter …" asks those)
        r["needs"] = logic.needs_of(reading_set.rule_names(by_id[r["Rule id"]]), {k: m.get("value") for k, m in measured.items()})
    rows = [{**r, "Line": _amount(r, by_id[r["Rule id"]], measured)} if r["Error"] == "FAIL" else r
            for r in every if r not in waiting]
    for r in rows:
        r["Short"] = short(r["Requirement"])
    for r in rows:
        found = every_reading(by_id[r["Rule id"]], measured, allowed, facts) if r["Error"] == "NEEDS REVIEW" else None
        review = r["Error"] == "NEEDS REVIEW"
        # every reading research lists (its words: what to confirm), and values not measured under which the rule
        # fails whatever they are: what the row's line says (the verdict itself is row_verdict's)
        r["Named"] = named_result(by_id[r["Rule id"]], measured, allowed) if review else None
        r["Unknown"] = fails_whatever(by_id[r["Rule id"]], measured, allowed, facts) if review and not found else None
        r["Provisional"] = found[1] if found else None
        # the readings it was worked out under (their values, the open measurements): the panel's tax-map best and
        # worst cases run over each of them, as for a row decided over named readings (review round 14)
        r["Readings"] = readings_of(by_id[r["Rule id"]], measured, allowed) if review else None
        r["Survey"] = bool(found and "confirm the survey" in found[1])     # waits on a fact, not an interpretation
        rule = by_id[r["Rule id"]]
        r["Verdict"] = row_verdict(rule, measured, allowed, facts)          # the ONE decision (round 3)
        r["Sides"] = {m: row_verdict(rule, measured, allowed, facts, check=c) for m, c in side_checks(rule).items()}
        r["Side provisional"] = {m: (every_reading(dict(rule, check=c), measured, allowed, facts) or (None, None))[1]
                                 for m, c in side_checks(rule).items()}      # each side's words, as a row's
        # each side's readings research lists (its words: what to confirm, the eave to mark), as a row's Named
        r["Side named"] = {m: named_result(dict(rule, check=c), measured, allowed) for m, c in side_checks(rule).items()}
        r["Side turns on"] = {m: turns_on(dict(rule, check=c), measured, allowed, facts)
                              for m, c in side_checks(rule).items()}
        r["Fails"] = r["Verdict"] == present.FAILS                          # fails whichever way it goes
        r["Turns on"] = turns_on(rule, measured, allowed, facts)            # the open questions its result needs
        if r["Fails"] and r["Named"] and not r.get("Line"):
            r["Line"] = f"{short(r['Requirement'])}: {r['Named']['text']}"
        if r["Fails"] and r["Unknown"] and not r.get("Line"):
            gone = [plain_name(n) for n in r["Unknown"]["names"]]
            r["Line"] = (f"{short(r['Requirement'])}: does not comply whatever the {' and the '.join(gone)} "
                         f"{'is' if len(gone) == 1 else 'are'}")
        if r["Fails"] and not r.get("Line"):
            r["Line"] = f"{short(r['Requirement'])}: {r['Provisional']}"
        r["Crossing"] = crossing(by_id[r["Rule id"]], measured)
        if r["Crossing"]:            # a building on the neighbour's land: no reading or answer can clear it
            r["Fails"], r["Line"] = True, f"{short(r['Requirement'])}: {r['Crossing']}"
    lot_id = (site.get("lot") or {}).get("id")
    red = sorted({o for r in rows if r["Fails"]
                  for name in formula.names(by_id[r["Rule id"]]["check"]) for o in measured.get(name, {}).get("objects", [])
                  if o != lot_id})
    values = {k: m["value"] for k, m in measured.items()}
    dims = [d for r in rows if r["Error"] == "FAIL" for d in _failing_distances(by_id[r["Rule id"]], measured, values)]
    extras = {**(extras or {}), "side_lines": side_lines(site, facts),   # compass names when a side isn't measured
              # the lookup's "no overlay here", only for the lot it was found on and only while recent on the
              # host's day (never taken from the caller)
              "overlays_none_found": present.overlays_lookup(site.get("lot"), facts, today)}
    v = present.view(rows, waiting, by_id, measured, facts, extras)
    confirm_advice(v["items"], by_id, measured, allowed, facts, site)   # each "To comply" the checker's, or none
    found = egress.laws(facts["jurisdiction"])        # by place: the state law it inherits, its rules checked
    law = egress.check(found, interior, _with_stories_bound(values, measured, facts,
                                                            getattr(measuring(facts["jurisdiction"]), "fact_conflicts",
                                                                    None)), allowed,
                       ground=_story_ground(facts))
    egress.add_to_view(v, law, found["place"])
    # what the rebuilt results pane reads beyond today's fields (C1-C9): new fields only, never a status
    place_folder = egress._folder(facts["jurisdiction"])
    try:                             # a hint for the high-rise question only, never a value (high_rise_hint.py)
        from design_checker import high_rise_hint
        hint = high_rise_hint.words(high_rise_hint.figure(interior, _story_ground(facts)))
    except Exception:
        hint = None
    ui_data.add(v, rules_by_id=by_id, laws=found["laws"], site=site, values=values,
                place=measuring(facts["jurisdiction"]), place_folder=place_folder,
                documents=ui_data.place_documents(place_folder), high_rise_hint=hint)
    report_error = None
    if report_path is not None:      # a report that can't be written never takes the check's result with it
        try:
            say(STEPS["report"])
            _report(t, v, report_path, site_file, law["interior_sha256"], law["waiting"])
        except OSError as e:
            report_error = e.words if isinstance(e, _SiteInTheWay) else f"{e.strerror or e} ({report_path})"
    # one guard for the whole check (review round 21): geometry the measuring couldn't work out draws nothing
    # from it (no envelope, no overlays), and a geometry failure here does the same, never a crash
    geo = next((r["geometry_error"] for r in measured.values() if r.get("geometry_error")), None)
    try:
        env = envelope(site, _envelope_facts(site, facts), measured, rules) if not geo else None
    except shapely.errors.GEOSException as e:
        geo = f"the drawing's geometry couldn't be worked out ({str(e).split(':')[0][:80]})"
        env = None
    if env is None:
        env = {"outline": None, "holes": [], "base": None, "top": None, "yards": {}, "height": None,
               "coverage": None, "notes": [geo] if geo else []}
    try:
        drawn = plan(site, env, v, measured, facts, overlays=not geo)
    except shapely.errors.GEOSException:
        drawn = plan(site, env, v, measured, facts, overlays=False)
    # the notice (spec G): the items that don't comply now and did at the last check the command sent ("before")
    statuses, notice_text = present.notice((extras or {}).get("before"), v["items"])
    return {"rows": rows, "interior": waiting, "not_applicable": [dict(zip(COLUMNS, r)) for r in t["not_applicable"]],
            "summary": summary(rows, v["items"]), "red": red, "dims": dims, "measurements": measured,
            "envelope": env, "problems": site.get("problems") or [], "view": v, "plan": drawn,
            "report_error": report_error,
            "statuses": statuses, "notice": notice_text,
            "sections": v["sections"],          # zoning's, then each inherited law's, each with its own state
            "egress": {k: law[k] for k in ("rows", "results", "interior", "interior_sha256")},
            "which_code": egress.which_code(law)}      # which New York code governs the building (code_scope.py)


def _story_ground(facts: dict) -> dict:
    """The ground the Building Code's story places are worked out from (model_measurement.routes.story_place): the
    lot facts' stated ground; flat ground the host only assumed is refused, with the lot's own place's reason where
    its measuring gives one."""
    from model_measurement.routes.story_place import ground_of
    unsafe = getattr(measuring(facts["jurisdiction"]), "flat_assumption_unsafe", None)
    return ground_of(facts, unsafe(facts) if unsafe else None)


def _with_stories_bound(values: dict, measured: dict, facts: dict | None = None, conflicts=None) -> dict:
    """The values egress reads, with what the measuring established for which New York code governs:
    code_scope.STORIES_DRAWN where the count was read from the drawn parts (the measuring then checked nothing drawn
    is below the ground: places/ithaca_city/measure.py _stories_whole), never where it is a typed count kept because
    nothing countable is drawn (no parts named) or any measurement hit a geometry error; code_scope.STORIES_HOW, typed
    (the architect's count kept within what the drawing allows) or read; the most stories the drawing allows
    (code_scope.STORIES_AT_MOST) where the count is an open question between readings; code_scope.SET_ASIDE, each
    stated fact the measuring set aside for contradicting another ({name: its reason}: the place's own
    `conflicts`, its measuring's fact_conflicts), never read as unstated; and code_scope.STORIES_TYPED, the story
    count the architect typed (a number), settled or not, which egress reads against "no stairs"."""
    record = measured.get("stories") or {}
    drawn = bool(record.get("objects")) and not any(isinstance(r, dict) and r.get("geometry_error")
                                                   for r in measured.values())
    how = "typed" if record.get("stated") is True else "read"     # the measuring's flag (measure.py), never its words
    aside = {}
    for why, names in (conflicts(facts or {}) if conflicts else []):
        for k in names:
            if k in code_scope.READS:
                aside.setdefault(k, why)
    out = {**values, code_scope.STORIES_DRAWN: drawn, code_scope.STORIES_HOW: how, code_scope.SET_ASIDE: aside}
    typed = (facts or {}).get("stories")
    if type(typed) is int or type(typed) is float and math.isfinite(typed):   # the architect's own count (any size)
        out[code_scope.STORIES_TYPED] = typed
    most = [r.get("value") for r in record.get("readings") or [] if isinstance(r, dict)]
    if values.get("stories") is not None or not most or not all(type(v) in (int, float) for v in most):
        return out
    return {**out, code_scope.STORIES_AT_MOST: max(most)}


def _envelope_facts(site: dict, facts: dict) -> dict:
    """The facts the envelope is drawn from. Spot grades (or terrain sampled at the walls) that the measuring
    accepts give the grade plane, so the height plane is drawn from it; existing ground never sets it (it isn't
    the grade the code measures from), so then only the buildable area is drawn; nor does flat ground assumed on a
    lot that may slope (measure.flat_assumption_unsafe: its height and stories need review, so no height plane)."""
    from model_measurement.plugin_measuring import flat_assumption_unsafe
    if facts.get("grade_is") == "existing" or flat_assumption_unsafe(facts):
        return {**facts, "ground_is_flat": None}
    if facts.get("grade_points"):
        from model_measurement.plugin_measuring import envelope_grade   # the measuring's own refusals, the same function
        grade, why = envelope_grade(site.get("buildings") or [], facts)
        return {**facts, "ground_is_flat": True, "grade_elevation": grade} if why is None else {**facts, "ground_is_flat": None}
    return facts


def _ring(polygon) -> list:
    """A polygon's outline as [[x, y], ...], without edges shorter than 0.001 ft."""
    return [list(p) for p in polygon.simplify(0.001).exterior.coords[:-1]]


SHORTEST_LABELLED_EDGE = 1.0          # ft: lot edges shorter than this get no length label in plan


def hole_free(region) -> list:
    """A region as pieces without holes (each drawn by its outline alone): a polygon with a hole is cut in two
    by the vertical line through the hole's middle, again until none is left (review round 2: strips all round
    a house, a ring with the complying core as its hole, were drawn as the whole footprint)."""
    from shapely.geometry import box
    out, todo = [], [g for g in getattr(region, "geoms", [region]) if region is not None and not region.is_empty]
    while todo:
        g = todo.pop()
        if g.geom_type != "Polygon":
            todo += [p for p in getattr(g, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
            continue
        if not g.interiors:
            out.append(g)
            continue
        x = g.interiors[0].centroid.x
        x0, y0, x1, y1 = g.bounds
        for half in (g.intersection(box(x0 - 1, y0 - 1, x, y1 + 1)), g.intersection(box(x, y0 - 1, x1 + 1, y1 + 1))):
            todo += [p for p in getattr(half, "geoms", [half]) if p.geom_type in ("Polygon", "MultiPolygon")]
    return out


YARD_MEASURES = present.YARD_MEASURES


RUN_TURN_DEG = 20      # lot edges turning less than this from one to the next are one run, labelled once


def edge_runs(edges: list[dict]) -> list[tuple[list, float]]:
    """The lot's edges as runs to label (display only; the measurements use every edge): consecutive edges that
    carry on in nearly the same direction (turning less than RUN_TURN_DEG) are one run, a curve drawn as short
    segments labelled once with its whole length, as an architect would dimension it (the real 106 Ithaca Rd: its
    front, eight segments of about 10 ft along Ithaca Road, crowded the plan with eight labels). Each run: (its
    points, its length in feet). The caller leaves out runs under 1 ft (a tax map's jog of an inch or two)."""
    pieces = []
    for e in edges:
        pts = [list(p[:2]) for p in e["points"]]
        for a, b in zip(pts, pts[1:]):
            if math.dist(a, b) > 1e-9:
                pieces.append((a, b))
    if not pieces:
        return []

    def heading(a, b):
        return math.atan2(b[1] - a[1], b[0] - a[0])

    def turn(p, q):
        d = abs(heading(*p) - heading(*q)) % (2 * math.pi)
        return math.degrees(min(d, 2 * math.pi - d))
    # a run turns less than RUN_TURN_DEG in all, not just from piece to piece: a rounded corner drawn as short
    # pieces (each turning a little) is a corner, never one run joining two sides on a chord across the lot
    runs = [[pieces[0]]]
    for piece in pieces[1:]:
        if turn(runs[-1][-1], piece) < RUN_TURN_DEG and turn(runs[-1][0], piece) < RUN_TURN_DEG:
            runs[-1].append(piece)
        else:
            runs.append([piece])
    if (len(runs) > 1 and turn(runs[-1][-1], runs[0][0]) < RUN_TURN_DEG
            and turn(runs[-1][0], runs[0][-1]) < RUN_TURN_DEG):                # the ring closes inside a run
        runs[0] = runs.pop() + runs[0]
    return [([r[0][0]] + [b for _, b in r], sum(math.dist(a, b) for a, b in r)) for r in runs]


def _yard_lines(lot, measure: str, point):
    """The lot lines a yard is measured from, as the measurement takes them: every group (the street lines, a
    side, the rear lines, under each reading of the lot) that the yard's lot-line point lies on."""
    from shapely.geometry import Point
    groups = [lot.ordered_street()] if measure == "front_yard" else [
        g for _, left, right, back in (lot.readings() or []) for g in ((left, right) if measure != "rear_yard" else (back,))]
    hit = sorted({i for g in groups if lot.line(g).distance(Point(point)) < 0.01 for i in g})
    return lot.line(hit) if hit else None


def _clip_above(points: list, z: float) -> list:
    """A face's points clipped to the part at height z or above (Sutherland-Hodgman against one level)."""
    out = []
    for k, p in enumerate(points):
        q = points[(k + 1) % len(points)]
        if p[2] >= z:
            out.append(list(p))
        if (p[2] >= z) != (q[2] >= z):               # the edge crosses the level: where it does
            t = (z - p[2]) / (q[2] - p[2])
            out.append([p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]), z])
    return out


WALL_TILT = 1e-3      # a face whose plan is under this share of its own area is a wall (plumb, or within a hair)


def _is_wall(points: list) -> bool:
    """Whether a face stands upright: its plan (seen from above) is under WALL_TILT of its own area (Newell's
    method), so a wall a hair out of plumb is a wall too (review of the #28 fix, L1)."""
    nx = ny = nz = 0.0
    for k, p in enumerate(points):
        q = points[(k + 1) % len(points)]
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    full = (nx * nx + ny * ny + nz * nz) ** 0.5
    return full <= 1e-12 or abs(nz) <= WALL_TILT * full


def walls_beyond(building: dict, z: float, region) -> bool:
    """Whether a wall (a face seen edge-on from above) rises over height z somewhere `region` (what above() sees)
    doesn't cover: its plan, 0.05 ft each side, not inside the region."""
    from shapely.geometry import LineString
    for f in building.get("faces") or []:
        if not any(p[2] > z + 1e-6 for p in f["points"]):
            continue
        if not _is_wall(f["points"]):
            continue                                    # not a wall: above() already sees it
        clipped = [p[:2] for p in _clip_above(f["points"], z)]
        trace = LineString(clipped) if len(clipped) >= 2 else None
        if trace is not None and trace.length > 1e-6 and not region.buffer(0.05).contains(trace):
            return True
    return False


def above(building: dict, z: float):
    """The building seen from above where it rises above height z: each face clipped to z and above, projected
    flat (a pitched roof's strip along its ridge, a flat roof's whole outline; vertical faces add nothing)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    parts = []
    for f in building.get("faces") or []:
        if not any(p[2] > z + 1e-6 for p in f["points"]) or _is_wall(f["points"]):
            continue                                    # (a wall's sliver of plan adds nothing: walls_beyond)
        shell = _clip_above(f["points"], z)
        if len(shell) < 3:
            continue
        poly = Polygon([p[:2] for p in shell]).buffer(0)
        for h in f.get("holes") or []:
            hole = _clip_above(h, z)
            if len(hole) >= 3:
                poly = poly.difference(Polygon([p[:2] for p in hole]).buffer(0))
        if poly.area > 1e-9:
            parts.append(poly)
    return unary_union(parts) if parts else Polygon()


REQUIRED_HALF_FT = 6.0     # the faint required line: this far either side of its yard's dimension
HEIGHT_DIM_OFFSET_FT = 4.0  # the height dimension stands this far out from the building's corner


def _dim_label(i: dict) -> str:
    """A dimension's words, as the plan shows them: its mark, its name, the measured distance (feet-inches) and,
    when it fails, what is needed."""
    return (f"{i['mark']} {i['name']} {i['proposed']}" +
            (f", needs {i['required']}" if i["status"] == present.FAILS and i.get("required") else "") +
            (" (approx.)" if i.get("approx") else ""))


ORDINALS = {1: "1st", 2: "2nd", 3: "3rd"}
ON_WALL_FT = 0.01                    # a closest point this near the ground floor's outline is on its wall


def measured_to(points: list, solids: list, footprint) -> str:
    """What a yard's dimension is measured to, when it is not the ground-floor wall: "2nd-floor overhang", or
    "a part above the ground floor" when no floor level names it (a bay, eaves, a sloped underside). "" for the
    ground-floor wall (today's plain label) and whenever it can't be told. Labelling only: the yard is measured "from
    the ground upward", to its least distance (§325-3 Yard), so the number and its pass or fail never change.
    `points`: the yard's measured closest points (one on the building seen from above, one on the lot line);
    `solids`: (building, its projection) pairs; the ground floor is every horizontal face at the lowest level."""
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    if not points or len(points) < 2 or footprint is None or footprint.is_empty or not solids:
        return ""
    from shapely.geometry import LineString
    ends = [Point(p[:2]) for p in points]
    house = min(ends, key=lambda q: footprint.boundary.distance(q))
    lot_end = ends[1] if house is ends[0] else ends[0]
    dx, dy = house.x - lot_end.x, house.y - lot_end.y
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-9:
        return ""
    far = 1e4 / length               # the lot line here: square to the dimension through its lot end
    line = LineString([(lot_end.x - dy * far, lot_end.y + dx * far), (lot_end.x + dy * far, lot_end.y - dx * far)])
    flats = []                       # (z, outline) of every horizontal face
    for b, _ in solids:
        for f in b["faces"]:
            zs = [p[2] for p in f["points"]]
            if len(zs) >= 3 and max(zs) - min(zs) < 1e-6:
                poly = Polygon([tuple(p[:2]) for p in f["points"]]).buffer(0)
                if poly.area > 1e-9:
                    flats.append((zs[0], poly))
    if not flats:
        return ""
    bottom = min(z for z, _ in flats)
    ground = unary_union([poly for z, poly in flats if z - bottom < 1e-6])
    if ground.is_empty or ground.distance(line) - length <= ON_WALL_FT:
        return ""                   # the ground floor's wall is as near: today's plain label
    levels = sorted({round(min(p[2] for f in b["faces"] for p in f["points"]), 4) for b, _ in solids})
    starts = sorted(z for z, poly in flats if z - bottom >= 1e-6 and poly.boundary.distance(house) <= ON_WALL_FT)
    if starts and len(levels) > 1 and round(starts[0], 4) in levels:
        n = levels.index(round(starts[0], 4)) + 1
        return f"{ORDINALS.get(n, str(n) + 'th')}-floor overhang"
    return "a part above the ground floor"


def number_to(number: str, proposed: str, what: str) -> str:
    """The drawn number with what it is measured to (measured_to), the number itself unchanged: "22'-0\" (to 2nd-floor
    overhang)"; a range (the yard read two ways, the open question of walls or overhangs) names its nearer end, the
    one measured to the overhang: "? 27'-0\" (to 2nd-floor overhang) to 30'-0\"". `what` "": `number` as it is."""
    if not what or proposed not in number:
        return number
    low, sep, high = proposed.partition(" to ")
    return number.replace(proposed, low + f" (to {what})" + (sep + high if sep else ""))


def required_lines(points: list, item: dict, edges: list) -> tuple[list, str | None]:
    """The yard's required line(s) across its dimension, and why there is none: one at its limit (`limit_ft`), or,
    when the limit depends on an open measurement (the lot depth, on the tax map), one at each end of its range
    (`limit_span_ft`), so every dimensioned yard shows where its minimum lies (Rhino check of #29)."""
    lo_hi = item.get("limit_span_ft")
    limits = [item["limit_ft"]] if isinstance(item.get("limit_ft"), (int, float)) else (
        sorted(set(lo_hi)) if lo_hi else [])
    lines = [x for x in (required_line(points, limit, edges) for limit in limits) if x]
    why = None if lines else ("its limit is not a length in feet" if not limits else
                              "the minimum is 0 ft (on the lot line)" if all(x <= 0 for x in limits) else
                              "the dimension has no length")
    return lines, why


def required_tags(item: dict) -> list:
    """The small tag at each required line's end, in the order of required_lines: "min 25'-0\"" (feet-inches, as
    the panel's Required column rounds a minimum: up)."""
    lo_hi = item.get("limit_span_ft")
    limits = [item["limit_ft"]] if isinstance(item.get("limit_ft"), (int, float)) else (
        sorted(set(lo_hi)) if lo_hi else [])
    return ["min " + present.value_text(x, "ft", "≥", False) for x in limits if x > 0]


def required_line(points: list, limit, edges: list) -> list | None:
    """Where the yard's required line crosses its dimension (plan, feet): a short line square to the dimension,
    `limit` from the lot line along it, REQUIRED_HALF_FT either side, drawn faint. The dimension's lot-line end is
    whichever end lies nearer the lot's outline (a measurement's points are a lot-line point and a building point).
    None without a limit in feet or a dimension of some length."""
    from shapely.geometry import LineString, Point
    if not isinstance(limit, (int, float)) or limit <= 0 or not points or len(points) < 2:
        return None
    a, b = [list(p[:2]) for p in points[:2]]
    length = math.dist(a, b)
    if length < 1e-6:
        return None
    if edges:
        ring = LineString([tuple(p[:2]) for e in edges for p in e["points"]])
        if ring.distance(Point(b)) < ring.distance(Point(a)):
            a, b = b, a
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    cx, cy = a[0] + ux * limit, a[1] + uy * limit
    return [[cx - uy * REQUIRED_HALF_FT, cy + ux * REQUIRED_HALF_FT], [cx + uy * REQUIRED_HALF_FT, cy - ux * REQUIRED_HALF_FT]]


DIM_NEAR_FT = 0.02    # a wall run's "nearest part": within this (1/4") of the yard as measured
STRAIGHT_FT = 1e-3    # a footprint point this close to the line through its neighbours lies on a straight wall
BEND_SLACK_FT = 0.5   # at a bend in the lot line in front of the wall: a square dimension at most this much longer


def _wall_runs(footprint) -> list:
    """The footprint's outline as wall runs: its pieces, those that carry straight on joined (a gable's footprint
    keeps a point mid-wall under the ridge: review round 3 of #29, F1)."""
    out = []
    for g in getattr(footprint, "geoms", [footprint]):
        for ring_ in [g.exterior, *g.interiors]:
            pts = [p for p in list(ring_.coords)[:-1]]
            pts = [p for k, p in enumerate(pts) if math.dist(p, pts[k - 1]) > 1e-9]
            n = len(pts)
            if n < 3:
                continue

            def straight(k):                      # pts[k] lies on a straight line from pts[k-1] to pts[k+1]
                a, b, c = pts[k - 1], pts[k], pts[(k + 1) % n]
                cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
                dot = (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1])
                # off the line from a to c by under STRAIGHT_FT (feet, not an angle: a model's single-precision
                # points sit 1e-6 ft off a straight wall; review round 4, F1)
                return abs(cross) / max(math.dist(a, c), 1e-12) <= STRAIGHT_FT and dot > 0
            corners = [k for k in range(n) if not straight(k)]
            for j, k in enumerate(corners):
                end = corners[(j + 1) % len(corners)]
                chain = [pts[(k + i) % n] for i in range(((end - k) % n or n) + 1)]
                out += _straight_runs(chain)
    return out


def _straight_runs(chain: list) -> list:
    """A chain of points joined into runs that each stay within STRAIGHT_FT of their own end-to-end line
    (Douglas-Peucker): a wall drawn as many short pieces along a curve is many runs, never one chord in front of
    it (independent review of #29, round 5)."""
    a, b = chain[0], chain[-1]
    length = math.dist(a, b)
    far, at = 0.0, None
    for k, p in enumerate(chain[1:-1], 1):
        off = (abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / length if length > 1e-12
               else math.dist(a, p))
        if off > far:
            far, at = off, k
    if at is None or far <= STRAIGHT_FT:
        return [(a, b)] if length > 1e-9 else []
    return _straight_runs(chain[:at + 1]) + _straight_runs(chain[at:])


DIM_CANDIDATES = 15   # positions offered along a wall run for the viewport to place a yard's dimension clear


def dim_points(points: list, measure: str, shape, footprint, edges: list, worst: bool = True) -> list:
    """Where a yard's dimension is drawn by preference (plan, feet): [its lot-line end, its building end]; the first
    of dim_candidates, or the measurement's own pair when there is none."""
    found = dim_candidates(points, measure, shape, footprint, edges, worst)
    return found[0] if found else points


def dim_candidates(points: list, measure: str, shape, footprint, edges: list, worst: bool = True) -> list:
    """Where a yard's dimension may be drawn (plan, feet), best first: pairs [its lot-line end, its building end],
    as a drawing would place it (Rhino checks of #29). The building end lies on the wall run facing the yard's lot
    line, never a corner the next yard's dimension shares; the lot end is its square projection onto the lot-line
    piece it falls on (0° by construction). Best is nearest the middle of the run; the plugin draws the first (its
    number placed by rhino_logic.place_dim_label).
    How far along the run it may go: a yard that fails or needs review (`worst`) is dimensioned where it is
    shortest, within DIM_NEAR_FT of the yard as measured (the drawing never shows more room than the label);
    a complying yard anywhere its dimension is within BEND_SLACK_FT of it (a lot line a fraction of a degree off
    the wall: anywhere along it). At a bend in the lot line right in front of the wall the nearest square position
    within BEND_SLACK_FT. The label is always the yard as measured, its closest point. None (an empty list) when
    there is no lot shape or footprint to work from."""
    from shapely.geometry import LineString, Point
    if not points or len(points) < 2 or shape is None or footprint is None or footprint.is_empty:
        return []
    a, b = [tuple(p[:2]) for p in points[:2]]
    if edges:
        ring = LineString([tuple(p[:2]) for e in edges for p in e["points"]])
        if ring.distance(Point(b)) < ring.distance(Point(a)):
            a, b = b, a
    lines = _yard_lines(shape, measure, a)
    if lines is None:
        return []
    pieces = [(q[k], q[k + 1]) for g in getattr(lines, "geoms", [lines]) for q in [list(g.coords)]
              for k in range(len(q) - 1) if math.dist(q[k], q[k + 1]) > 1e-9]
    near = Point(b)
    measured = lines.distance(near)
    runs = [r for r in _wall_runs(footprint) if LineString(r).distance(near) < 1e-6]
    if not runs or not pieces:
        return []
    facing = min(pieces, key=lambda s: LineString(s).distance(near))

    def turn(run):                                 # how far the run is from parallel to the lot-line piece
        (p, q), (u, w) = run, facing
        cross = (q[0] - p[0]) * (w[1] - u[1]) - (q[1] - p[1]) * (w[0] - u[0])
        return abs(cross) / (math.dist(p, q) * math.dist(u, w))
    p, q = min(runs, key=turn)
    steps = 200
    at = [(p[0] + (q[0] - p[0]) * t / steps, p[1] + (q[1] - p[1]) * t / steps) for t in range(steps + 1)]

    def onto(start, piece):                        # square projection onto a piece, if it falls on it
        (u, w) = piece
        dx, dy = w[0] - u[0], w[1] - u[1]
        t = ((start[0] - u[0]) * dx + (start[1] - u[1]) * dy) / (dx * dx + dy * dy)
        return (u[0] + t * dx, u[1] + t * dy) if -1e-9 <= t <= 1 + 1e-9 else None

    def square(k, slack):                          # the dimension from at[k], if square and short enough
        feet = [x for x in (onto(at[k], piece) for piece in pieces) if x is not None]
        if not feet:
            return None
        foot = min(feet, key=lambda x: math.dist(x, at[k]))
        if footprint.boundary.distance(Point(at[k])) > 1e-6:      # a start never off the wall (backstop)
            return None
        return [list(foot), list(at[k])] if math.dist(foot, at[k]) <= measured + slack + 1e-6 else None
    middle = steps // 2
    # never at the corners themselves; a complying yard's kept off the last twentieth of the wall (room for the
    # neighbouring yard's), a short one where it is shortest, however near the corner that is
    inner = range(1, steps) if worst else range(steps // 20, steps - steps // 20 + 1)
    # a short yard: where it is shortest, its corner too before any slack (review round 6, F1: a house turned
    # against its lot is shortest at a corner); then the bend slack
    ends = range(steps + 1)
    tries = ([(inner, DIM_NEAR_FT), (ends, DIM_NEAR_FT), (inner, BEND_SLACK_FT), (ends, BEND_SLACK_FT)] if worst
             else [(inner, BEND_SLACK_FT), (ends, BEND_SLACK_FT)])
    found = []
    for ks, slack in tries:
        found = [(k, d) for k, d in ((k, square(k, slack)) for k in ks) if d]
        if found:
            break
    if len(found) > DIM_CANDIDATES:                 # spread evenly along the run, both ways from the best
        spread = max(1, -(-(found[-1][0] - found[0][0]) // (DIM_CANDIDATES - 1)))
        best = min(found, key=lambda kd: abs(kd[0] - middle))[0]
        found = [(k, d) for k, d in found if (k - best) % spread == 0]
    if worst and slack > DIM_NEAR_FT:               # with slack: the shortest first (round 6, F1); within 1/4"
        return [d for k, d in sorted(found, key=lambda kd: (round(math.dist(*kd[1]), 4), abs(kd[0] - middle)))]
    # every one as short as the yard: nearest the middle, off the shared corner (round 7, F2)
    return [d for k, d in sorted(found, key=lambda kd: abs(kd[0] - middle))]


def height_dim(site: dict, env: dict, v: dict, measured: dict) -> dict | None:
    """The height's vertical dimension for the elevations (feet): from the grade plane up the measured height,
    beside the buildings' corner (HEIGHT_DIM_OFFSET_FT out from it), labelled and coloured as the height row, the
    limit as a faint line across it. None without a grade, a measured height (the larger reading when they
    differ: never drawn lower than it may be) or a building."""
    item = next((i for i in v["items"] if i.get("measure") == "building_height"), None)
    record = (measured or {}).get("building_height") or {}
    value = record.get("value")
    if value is None and record.get("readings"):
        value = max(r["value"] for r in record["readings"] if isinstance(r.get("value"), (int, float)))
    pts = [p for b in site.get("buildings") or [] for f in b.get("faces") or [] for p in f["points"]]
    if item is None or not isinstance(value, (int, float)) or not env or env.get("base") is None or not pts:
        return None
    x = max(p[0] for p in pts) + HEIGHT_DIM_OFFSET_FT
    y = min(p[1] for p in pts) - HEIGHT_DIM_OFFSET_FT
    limit = item.get("limit_ft")
    return {"at": [x, y], "base": env["base"], "top": env["base"] + value, "status": item["status"],
            "label": _dim_label(item), "number": logic.dim_number(item["mark"], item["proposed"], item["status"]),
            "limit": env["base"] + limit if isinstance(limit, (int, float)) else None}


def from_tax_map(facts) -> bool:
    """Whether the lot's lines are the tax map's (each right only to within ±TAX_MAP_TOLERANCE): anything but a lot
    marked surveyed, an unknown one too (as the rows read it: present.py's "(approx.)"; review of feature 4, F2)."""
    return not (facts or {}).get("lot_surveyed")


def cautious_outline(outline, facts) -> list | None:
    """On a tax-map lot, the buildable outline drawn in by TAX_MAP_TOLERANCE on every side: where the building
    stands clear however the tax map's lines really lie, as a list of rings (a narrow outline can come apart in
    pieces, each kept; none at all where nothing is left 2'-0" in: an empty list, never the outline as drawn: review
    of feature 4, F3). None on a survey or without an outline (Ben, 2026-10-25: the cautious outline to snap to; the
    as-drawn one dashed)."""
    from shapely.geometry import Polygon
    from envelope_builder.envelope import QUAD_SEGS
    from model_measurement.plugin_measuring import TAX_MAP_TOLERANCE
    if not outline or not from_tax_map(facts):
        return None
    inner = Polygon(outline).buffer(-TAX_MAP_TOLERANCE, quad_segs=QUAD_SEGS)   # every lot line 2'-0" nearer: at
    # an inside corner too, exactly 2'-0" (a square join made it 2'-10": review of feature 4, round 4, F2)
    return [_ring(g) for g in getattr(inner, "geoms", [inner]) if g.geom_type == "Polygon" and not g.is_empty]


def full_yard_lines(shape, lot: dict, items: list) -> list:
    """Each measured yard's required line in full across the lot (plan, feet): its lot line(s) moved in by the
    row's limit, clipped to the lot; a limit that waits on an open measurement (the lot depth on the tax map:
    `limit_span_ft`) gives a line at each end of its range, as required_lines does (review of feature 4, F4).
    [{"measure", "name", "status", "limit_ft", "points": [[x, y], ...]}], one entry per piece; nothing for a yard
    without a limit in feet or without a lot shape. The lot is the measurement's own polygon, curved lines and
    all (F5)."""
    from shapely.geometry import LineString, Point
    from envelope_builder.envelope import QUAD_SEGS
    if shape is None or not (lot or {}).get("edges"):
        return []
    area = shape.polygon.buffer(0)
    out = []
    for i in items:
        lo_hi = i.get("limit_span_ft")
        limits = [i["limit_ft"]] if isinstance(i.get("limit_ft"), (int, float)) else (
            sorted(set(lo_hi)) if lo_hi else [])
        if i.get("measure") not in YARD_MEASURES or not i.get("points"):
            continue
        a, b = [tuple(p[:2]) for p in i["points"][:2]]
        lot_end = a if area.exterior.distance(Point(a)) <= area.exterior.distance(Point(b)) else b
        lines = _yard_lines(shape, i["measure"], lot_end)
        if lines is None:
            continue
        for limit in limits:
            if limit <= 0:
                continue
            # round corners at the envelope's own fineness (its QUAD_SEGS), so the line and the envelope's arc
            # agree (reviews of dd44f1b, F3, and d5fca99, R1)
            band = area.intersection(lines.buffer(limit, quad_segs=QUAD_SEGS))
            # (only its polygon parts: a touch at a point or along a line makes a collection, whose boundary is
            # None in shapely 2.1: review of feature 4, F8)
            parts = [g for g in getattr(band, "geoms", [band]) if g.geom_type == "Polygon" and not g.is_empty]
            for part in parts:
                inner = part.boundary.difference(area.exterior.buffer(1e-6))
                for g in getattr(inner, "geoms", [inner]):
                    if isinstance(g, LineString) and g.length > 1e-3:
                        out.append({"measure": i["measure"], "name": i.get("name"), "status": i.get("status"),
                                    "limit_ft": limit, "points": [list(p) for p in g.coords]})
    return out


def plan(site: dict, env: dict, v: dict, measured: dict, facts: dict | None = None, overlays: bool = True) -> dict:
    """What the viewport draws in plan (feet): each lot edge with its length, the yard lines measured (each with
    its item's status), and where the building breaks a limit: the strip of its footprint inside a required yard,
    or the part above the height limit (spec F2, F4, F5). The building itself stays neutral.
    Each yard's red and amber are its own row's (present.settle: from the row's readings, after every status
    change), never another yard's: red where its wall is short under every reading, amber under some."""
    from model_measurement.plugin_measuring import Lot, _projection, union as unary_union
    from model_measurement.stops import stop

    lot = site.get("lot") or {}
    edges = [{"points": [list(r[0][:2]), list(r[-1][:2])], "length": present.feet_inches(length)}
             for r, length in edge_runs(lot.get("edges") or [])
             if length >= SHORTEST_LABELLED_EDGE]   # a tax-map sliver (0'-1 5/8"): no label, it only clutters
    solids = [(b, _projection(b)) for b in site.get("buildings") or [] if b.get("faces")] if overlays else []
    footprint = unary_union([p for _, p in solids]) if solids else None
    shape = Lot(site, facts or {}) if overlays and lot.get("edges") and facts and facts.get("street_line") else None
    yards = []
    for i in v["items"]:
        if not (i.get("points") and i.get("measure") in YARD_MEASURES):
            continue
        worst = i["status"] in (present.FAILS, present.REVIEW)
        options = dim_candidates(i["points"], i["measure"], shape, footprint, lot.get("edges") or [], worst) or \
            [i["points"]]
        candidates = []
        for at in options:
            lines, why = required_lines(at, i, lot.get("edges") or [])
            candidates.append({"points": at, "required_lines": lines})
        # a yard with no required line says why, on its label (review round 3, F2)
        yards.append({"points": candidates[0]["points"], "measured_points": i["points"], "status": i["status"],
                      "label": _dim_label(i) + (f" · no required line: {why}" if why else ""),
                      "required_lines": candidates[0]["required_lines"], "required_why": why,
                      # on the drawing: its number only, the "min" tags only where it fails or needs review
                      "number": number_to(logic.dim_number(i["mark"], i["proposed"], i["status"]), i["proposed"],
                                          measured_to(i["points"], solids, footprint)),
                      "required_tags": required_tags(i) if i["status"] in (present.FAILS, present.REVIEW) else [],
                      "candidates": candidates})
    encroach = []
    tops = [p[2] for b, _ in solids for f in b["faces"] for p in f["points"]]
    statuses = {i["measure"]: i["status"] for i in v["items"] if i.get("measure")}
    if footprint is not None and not footprint.is_empty and env and env.get("outline") and tops:
        rows = []                                  # (the row, its red region or None, its amber regions)
        for i in v["items"]:
            if i.get("colour") not in ("red", "amber") or shape is None:
                continue
            near, far = [], []
            for limit in i.get("limits") or []:
                lines = _yard_lines(shape, i["measure"], limit["points"][0])
                if lines is None:
                    continue
                strip = (lambda d: footprint.intersection(lines.buffer(d, quad_segs=32)) if d > 0 else None)
                near.append(strip(limit["near"]))
                far.append(strip(limit["far"]))
            red = None
            if i["colour"] == "red" and near and all(g is not None for g in near):
                red = near[0]
                for g in near[1:]:                          # short under EVERY reading: where every one says so
                    red = red.intersection(g)
            rows.append((i, red, [g for g in far if g is not None]))
        reds = [r for _, r, _ in rows if r is not None]
        red_all = unary_union(reds) if reds else None
        # each region is its own row's (the side yard's, the rear yard's…), named on it, and coloured once: where
        # two rows' strips overlap (a corner), the first row's; amber never where any row is red
        taken = {present.FAILS: None, present.REVIEW: red_all}
        regions = []
        for i, red, ambers in rows:
            for region, status in ((red, present.FAILS), (unary_union(ambers) if ambers else None, present.REVIEW)):
                if region is None or region.is_empty:
                    continue
                if taken[status] is not None:
                    region = region.difference(taken[status])
                taken[status] = region if taken[status] is None else unary_union([taken[status], region])
                regions.append((region, status, i))
        # per building: only the part of THAT building in the yard, from its own bottom to its own top (a garage
        # in a side yard is never coloured up to the house's ridge). The viewport then cuts each building by its
        # block (Rhino's boolean), so a cantilever over a yard is coloured, not the air under it. Outlines
        # simplified to 0.001 ft: the subtraction leaves edges 1e-14 ft long, which Rhino can't extrude.
        for region, status, i in regions:
            for b, own in solids:
                zs = [p[2] for f in b["faces"] for p in f["points"]]
                for g in hole_free(region.intersection(own)):
                    if g.area > 1e-3:
                        encroach.append({"outline": _ring(g), "base": min(zs), "top": max(zs), "why": "yard",
                                         "status": status, "building": b.get("id"), "measure": i.get("measure"),
                                         "row": i.get("name")})
        # the worst of the maximum-height rows: a district with a minimum height (B-1b, B-2d, the CBD districts) has a
        # second building-height row ("≥"), whose "complies" must never hide the maximum's failure (only what rises
        # above the limit plane is ever drawn)
        height = next((s for s in (present.FAILS, present.REVIEW) if any(
            i.get("measure") == "building_height" and i.get("sign") != "≥" and i["status"] == s for i in v["items"])),
            statuses.get("building_height"))
        if height in (present.FAILS, present.REVIEW) and env.get("top") is not None:
            for b, own in solids:                       # only what rises above the limit: a roof's ridge, not its eaves
                top = max(p[2] for f in b["faces"] for p in f["points"])
                # a curved surface the reader left out (a vault) may rise over the limit from walls below it: a
                # block over its plan at the limit, no taller here; Rhino reaches it to the real solid's top and
                # cuts it (rhino_logic.block_span), nothing when the solid stays under (review of 2cae58d, F1)
                unread = bool(set(b.get("problems") or []) & {stop("curved_surface"), stop("curved_edge")})
                if top <= env["top"] + 1e-6 and not unread:
                    continue
                top = max(top, env["top"])
                region = above(b, env["top"])
                # nothing above it seen from above, or a wall rising over the limit outside what is (a vault read as
                # walls, alone or beside a flat roof): its own plan, never less (independent review of #28, P1, L1)
                if region.is_empty or region.area <= 1e-3 or walls_beyond(b, env["top"], region):
                    region = own
                for g in hole_free(region):
                    if g.area > 1e-3:
                        encroach.append({"outline": _ring(g), "base": env["top"], "top": top, "why": "height",
                                         "status": height, "building": b.get("id"),
                                         "measure": "building_height", "row": "Building height"})
    return {"edges": edges, "yards": yards, "encroach": encroach, "height": height_dim(site, env, v, measured),
            "footprint": [_ring(g) for g in getattr(footprint, "geoms", [footprint])
                          if footprint is not None and not footprint.is_empty and g.geom_type == "Polygon"],
            "buildable": env.get("outline") if env else None, "height_plane": env.get("top") if env else None,
            # what the architect snaps to (Osnap curves on Gordium::Envelope): the cautious outline on a tax-map lot
            # (every lot line 2'-0" nearer), and each yard's required line in full
            "buildable_cautious": cautious_outline(env.get("outline") if env else None, facts),
            "lot_from_tax_map": from_tax_map(facts),
            "yard_lines": full_yard_lines(shape, lot, v["items"])}


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


TAX_MAP_NOTE = ("Largest house that complies even if the tax-map lines are 2'-0\" off; limited by {limit}. Use my "
                "survey… for the full size.")
NOT_PROVEN = ("Starting house: Gordium couldn't keep it clear of the tax map's 2'-0\" tolerance on this lot; the items "
              "that say so need review until a survey.")


def limit_words(out, lot_area):
    """What stopped the starting house growing, in the architect's words, with its number (Ben, 2026-10-21: "limited
    by coverage 25%"): the lot coverage limit and its percent of the lot, or the yards and their minimums."""
    ft = lambda v: present.feet_inches(v, "up")                    # noqa: E731 (a minimum: up, as the panel)
    if out.get("limited_by") == "coverage" and out.get("coverage_allowed") and lot_area:
        return "lot coverage " + present._pct(out["coverage_allowed"] / lot_area * 100, "down", 2)
    yards = out.get("yards") or {}
    split = out.get("side_split")
    sides = ("sides " + ft(split["larger"]) + " and " + ft(split["smaller"])) if split else \
        ("sides " + ft(yards.get("side", 0)))
    if yards:
        return "the yards (front " + ft(yards.get("front", 0)) + ", " + sides + ", rear " + ft(yards.get("rear", 0)) + ")"
    return "the yards"


def side_words(split, plan_north_deg=0.0):
    """Which side the larger side yard is on, in the architect's words, seen from the street, each side with its
    true compass point: 'Side yards: 10'-0" on the left (north), 5'-0" on the right (south), seen from the street.'
    None when the two side yards are the same (no choice was made)."""
    if not split:
        return None
    ft = lambda v: present.feet_inches(v, "up")                    # noqa: E731 (a minimum: up, as the panel)

    def named(side):
        where = present.compass(*split[side + "_toward"], plan_north_deg or 0.0)
        return f"{ft(split[side])} on the {side}" + (f" ({where.lower()})" if where else "")

    first = split["larger_side"]
    second = "right" if first == "left" else "left"
    return f"Side yards: {named(first)}, {named(second)}, seen from the street."


def margin_note(keep, buffer, tax, proven, limit="the yards"):
    """What the starting house is and keeps back, in the architect's words, with what limited it (Ben's wording when
    it is the tax map alone: "Largest house that complies even if the tax-map lines are 2'-0" off; limited by …")."""
    ft = lambda v: present.feet_inches(v, "nearest")
    if tax and not proven:
        return NOT_PROVEN
    if tax and not buffer:
        note = TAX_MAP_NOTE.format(limit=limit)
        return note if abs(keep - TAX_MAP_TOLERANCE) < 1e-9 else note.replace(
            "limited by", "kept " + ft(keep) + " back; limited by", 1)
    if tax:
        return (f"Starting house keeps {ft(keep)} back from each limit: {ft(keep - buffer)} because the lot is from "
                f"the tax map (use a survey for the full area) and {ft(buffer)} your design buffer; limited by "
                f"{limit}.")
    if buffer:
        return f"Starting house keeps {ft(keep)} back from each limit (your design buffer); limited by {limit}."
    return f"Largest house the rules allow; limited by {limit} (the lot is from a survey)."   # (only the tax-map
    #                                         wording is Ben's; "complies" is the panel's to say: review of feature 5, F6)


LOT_ONLY = {"lot_area", "lot_width", "lot_depth"}   # items about the lot itself, whatever the house


def _kept_back_building(site, drawing, measured, rules, floor_to_floor, design_buffer, larger_side=None):
    """The starting house, kept back from the limits so that it complies even at the tax-map worst case (Ben,
    2026-10-20): on a lot not from a survey, every yard line moves in by the tax-map tolerance and coverage is sized
    for the smallest lot the tax map allows; on a survey it goes to the limits. A design buffer (ft) is added on top
    of either. Proven, not assumed: the house is checked with the panel's own worst case, and if any item would still
    need review from the tolerance (a rear yard minimum also grows with the lot depth) it steps back 3 in. more.
    `larger_side`: where the larger side yard goes ("left" or "right", seen from the street; None: Gordium's choice),
    kept on the side first chosen while it steps back."""
    from envelope_builder.start import floor_solids
    tax = not drawing.get("lot_surveyed")
    buffer = max(design_buffer or 0.0, 0.0)
    keep = (TAX_MAP_TOLERANCE if tax else 0.0) + buffer
    tol = (measured.get("lot_area") or {}).get("tolerance")
    drawn = next((r["value"] for r in (measured.get("lot_area") or {}).get("readings") or []), None)
    scale = tol["low"] / drawn if tax and tol and drawn else 1.0
    out = largest_legal_building(site, drawing, measured, rules, floor_to_floor=floor_to_floor, keep_back=keep,
                                 coverage_scale=scale, larger_side=larger_side)
    first = out.get("side_split")
    side = first["larger_side"] if first else larger_side
    proven = not tax
    for _ in range(12):
        if not tax or not out.get("floors"):
            break
        view = check_site({**site, "buildings": floor_solids(out["floors"])}, drawing)["view"]
        if not any(i["status"] == present.REVIEW and "tax map" in (i.get("reason") or "") for i in view["items"]
                   if i.get("measure") and i["measure"] not in LOT_ONLY):   # the lot's own size: no house fixes it
            proven = True
            break
        keep += 0.25
        out = largest_legal_building(site, drawing, measured, rules, floor_to_floor=floor_to_floor, keep_back=keep,
                                     coverage_scale=scale, larger_side=side)
    if first and out.get("side_split"):          # Gordium's choice stays its choice while it steps back
        out["side_split"]["asked"] = first["asked"]
    out["kept_back"] = keep
    if out.get("coverage_allowed") and scale:      # the rule's own allowance on the lot as drawn; what it was sized to
        out["coverage_target"] = out["coverage_allowed"]
        out["coverage_allowed"] = out["coverage_allowed"] / scale
    lot_area = (measured.get("lot_area") or {}).get("value") or drawn   # what the allowance is a share of
    out["margin_note"] = margin_note(keep, buffer, tax, proven, limit_words(out, lot_area)) \
        if out.get("floors") else None
    sides = side_words(out.get("side_split"), drawing.get("plan_north_deg")) if out["margin_note"] else None
    if sides:                                    # which side the larger side yard is on (Switch side yards swaps)
        out["margin_note"] += " " + sides
    if out["margin_note"]:                        # said always: what the house is and what limits it (Ben's
        out["notes"].append(out["margin_note"])   # "reassure in place")
    return out


def start(model_path: Path, facts: dict, floor_to_floor: float | None = None, design_buffer: float = 0.0,
          larger_side: str | None = None, step=None) -> dict:
    """The largest legal starting building for the lot in a model (its buildings, if any, left out): stacked
    floor blocks, one per story, from the zone's rules (envelope_builder.start). With no grade set, it is drawn
    standing at the lot's own level (and said so): the check then says height and stories need review until the
    grade is set, so nothing about the height is taken as settled."""
    problems = fact_problems(facts) + [f"no {k} given" for k in ("jurisdiction", "zone") if not facts.get(k)]
    if problems:
        raise ValueError("lot facts: " + "; ".join(problems))
    if no_rules_for(facts):
        raise ValueError(no_rules_for(facts))
    (step or _quiet)(STEPS["lot"])
    # through the site description, as check(): its lot only (a start leaves the buildings out)
    doc = site_json.legacy_description({**read_site(Path(model_path), facts), "buildings": []}, facts,
                                       host=_host(Path(model_path)))
    return start_description(site_json.through_json(doc), _without(facts, ("grade_points",)), floor_to_floor,
                             design_buffer, larger_side, step=step)


def start_description(doc: dict, facts: dict, floor_to_floor: float | None = None, design_buffer: float = 0.0,
                      larger_side: str | None = None, step=None) -> dict:
    """start() for a site description (the worker's start_site): its lot and grade; its buildings left out."""
    problems = fact_problems(facts) + [f"no {k} given" for k in ("jurisdiction", "zone") if not facts.get(k)]
    if problems:
        raise ValueError("lot facts: " + "; ".join(problems))
    if no_rules_for(facts):
        raise ValueError(no_rules_for(facts))
    site, facts, _ = site_json.for_measuring(site_json.to_site(doc), facts)
    say = step or _quiet
    site = {**site, "buildings": []}
    if site.get("problems"):
        return {"floors": [], "notes": list(site["problems"])}
    rules = load(rulebook_for(REPO / facts["jurisdiction"], facts["zone"]))["rules"]
    # spot grades with no building yet: the grade plane is their average (as the envelope draws it); then drawn on it
    # (the spots themselves aren't at the new building's walls: it's drawn on their plane, and the check that follows
    # judges the spots as they are)
    drawing = facts
    from model_measurement.plugin_measuring import flat_assumption_unsafe
    unsafe_flat = flat_assumption_unsafe(facts)
    if unsafe_flat:                     # flat ground assumed on a lot that may not be: drawn standing at the lot's
        # level all the same (as with no grade, below), its height and stories from the zone's limits; the check
        # that follows says they need review (measure.flat_assumption_unsafe), and so does this note
        drawing = {k: v for k, v in facts.items() if k not in ("ground_assumed", "ground_fall")}
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
    say(STEPS["largest"])
    measured = measuring(facts["jurisdiction"]).measure(site, drawing)  # the lot's own place's measuring
    geo = next((r["geometry_error"] for r in measured.values() if r.get("geometry_error")), None)
    if geo:                             # nothing drawn from geometry the measuring couldn't work out
        return {"floors": [], "notes": [geo], "preview": None}
    out = _kept_back_building(site, drawing, measured, rules, floor_to_floor, design_buffer, larger_side)
    if existing and out.get("floors"):
        out["notes"].append("drawn on the ground as it is: building height and stories need review until you tick "
                            "No regrading near the house (or set the finished ground)")
    out["preview"] = _start_preview(out, measured)
    if unsafe_flat and out.get("floors"):
        out["notes"].append("drawn as if the ground were flat, at the lot's level: building height and stories need "
                            "review (" + unsafe_flat.split(":")[0] + ")")
    if no_grade and out.get("floors"):
        out["notes"].append("drawn standing at the lot's level: building height and stories need review until the "
                            "grade is set")
    return out


def sample_site() -> dict:
    """The sample project GordiumStart offers, the plugin's place's sample lot (its jurisdiction.yaml sample_site;
    Ithaca: 106 Ithaca Rd's real lot, as the State tax map draws it, parcel 84.-2-6), placed exactly as the address
    lookup places it (lot_outline_tax_map.yaml: its source, the frame, made by code from a recorded lookup), so the
    sample and a looked-up 106 are the same drawing and the neighbourhood map lines up around it. A tax-map outline:
    each lot line may be 2'-0" off, so the lot size and every yard are checked under every reading of where the
    lines are. Its facts (zone, use) prefilled for the architect to confirm. Points in feet."""
    sample = plugin_place().sample_site
    if sample is None:
        raise ValueError(f"{plugin_place().name} has no sample site (sample_site in its jurisdiction.yaml)")
    folder, address = sample["folder"], sample["address"]
    outline = load(folder / "lot_outline_tax_map.yaml")
    facts = {**load_facts(folder / "spreadsheet_design_model_facts.yaml"), "lot_surveyed": False,
             "street_line": outline["street_line"], "corner_lot": bool(outline.get("corner_lot")),
             "plan_north_deg": outline["frame"]["rotation_deg"],     # the plan's turn from true north: compass names
             # each street line's street, as the lookup found it: one street (Ithaca Rd), however it curves
             "street_ids": [" ".join(w.capitalize() for w in str(outline.get("street") or "").split()) or None]
             * len(outline["street_line"])}
    keep = {"jurisdiction", "zone", "use", "street_line", "corner_lot", "ground_is_flat", "grade_elevation",
            "lot_surveyed", "plan_north_deg", "street_ids"}
    return {"address": address, "lot": [list(p) for p in outline["ring"]],
            "lot_name": "Lot · " + address.split(",")[0] + " · from the State tax map (parcel "
                        + outline["source"]["print_key"]
                        + "), each line ±2'-0\", not a survey",
            "frame": outline["frame"],
            # the street its street line is on, as the lookup found it on the State tax map ("ITHACA RD"): the
            # box's, like a looked-up street (not a checker fact)
            "street_name": " ".join(w.capitalize() for w in str(outline.get("street") or "").split()) or None,
            "street_source": "the State tax map (the sample's lookup)",
            "facts": {k: v for k, v in facts.items() if k in keep}}


def _use_lists(body) -> list:
    """The use names a formula lists in `use in [...]` (the chart's own rows) or names in `use == "..."` (one row, as
    the bed-and-breakfast inn's review in R-1 and R-2), in order. Missing the second once left the box saying a use
    "won't comply" while its rule said needs review (review round 1 of PR 65)."""
    import ast
    out = []
    for node in ast.walk(body):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "use":
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, ast.In) and isinstance(comp, ast.List):
                    out += [e.value for e in comp.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                elif isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                    out.append(comp.value)
    return out


def use_choices(rules: list, names: dict, district: str) -> list:
    """The uses the district's chart lists, for the box's Use dropdown (Ben, 2026-10-25): from the district's own
    use rule, never a hand-kept list, as [{"id", "name", "permitted", "note"}]. Permitted ones first, then those the
    chart marks otherwise, each saying so with the chart's page. A use rule is written one of two ways: a rule
    whose check lists the permitted uses and whose review_when lists the special-permit ones (R-1b), or a flag that
    applies to the special-permit uses, every other city use permitted (R-3a's "every other listed use is
    permitted"). Every city use, none marked, when the district has no use rule (nothing to narrow it by)."""
    from rule_format import formula
    rule = next((r for r in rules if r.get("topic") == "uses" and (r.get("check") or r.get("applies_when"))), None)
    if rule is None:
        return [{"id": k, "name": n, "permitted": None, "note": None} for k, n in names.items()]
    page = next((s.get("page") for s in rule.get("sources") or [] if "chart" in (s.get("file") or "")), None)
    cite = f"zoning chart p.{page}" if page else "the zoning chart"

    def entry(u, note=None):
        return {"id": u, "name": names.get(u, u.replace("_", " ")), "permitted": note is None, "note": note}

    if rule.get("check"):
        permitted = _use_lists(formula.parse(rule["check"]).body)
        special = [(u, (r.get("reason") or "").split(". ")[0].rstrip(".")) for r in rule.get("review_when") or []
                   for u in _use_lists(formula.parse(r["when"]).body)]
    else:
        flagged = _use_lists(formula.parse(rule["applies_when"]).body)
        permitted = [u for u in names if u not in flagged]
        special = [(u, "by special permit") for u in flagged]
    out, seen = [], set()
    for u in permitted:
        if u not in seen:
            seen.add(u)
            out.append(entry(u))
    for u, why in special:
        if u not in seen:
            seen.add(u)
            said = why if "chart" in why else (f"{why} ({cite})" if why else cite)
            out.append(entry(u, f"Not permitted by right in {district}: {said}."))
    return out


def follow_up_facts(rules: list, use: str | None, uses: dict, read: set | None = None) -> list:
    """The facts the box asks after the use, derived from the rulebook (Ben, 2026-10-25: no hand-kept list): every
    stated fact (rhino_logic.STATED_FACTS: what only the architect can say) that a rule of this district reads, in
    its applies_when, check or review_when, when that rule can apply to this use (its applies_when not false for
    it). Never the stories (measured), never the interior's (bedrooms, parking: on hold), never one the use itself
    says (one-family: one dwelling unit). `read`: _read_for(rules, use, uses), when the caller has it already
    (options works it out once per district and use, for this and implied_for)."""
    read = _read_for(rules, use, uses) if read is None else read
    implied = logic.implied_facts(use)
    return [k for k in logic.STATED_FACTS if k in read and k != "stories"
            and k not in INTERIOR and k not in logic.DRAWN_FACTS and k not in implied]


def implied_for(rules: list, use: str | None, uses: dict, read: set | None = None) -> dict:
    """What the use itself says (rhino_logic.implied_facts) for the facts this district's rules read for it, and
    only those (a fact no rule reads is never sent: the checker knows only the facts its rules can use). `read`:
    as follow_up_facts's."""
    read = _read_for(rules, use, uses) if read is None else read
    return {k: v for k, v in logic.implied_facts(use).items() if k in read}


def _read_for(rules: list, use: str | None, uses: dict, memo: dict | None = None) -> set:
    """Every name the district's rules read when they can apply to this use (applies_when not false for it). `memo`:
    kept for one options answer (_options), the same `uses` throughout: each applies_when text's verdict for a use and
    each rule's names, worked out once rather than once per district and use (21 districts × 37 uses)."""
    from rule_format import formula
    # every name described exactly as the checker's own verdict describes it (outcome: the city's measures and the
    # uses, check_site), so a condition is settled here as it is there: false for this use whatever the rest turns
    # out to be ("use in [multiple_family] and not conversion" for a one-family house) asks nothing, and a rule the
    # checker could still find applicable (a name it can't type) is asked (review round 2: typed apart, a row
    # needed review that the box never asked about)
    kinds = MEASURE_KINDS | {"use": frozenset(uses)}
    memo = {} if memo is None else memo
    wanted = set()
    for rule in rules:
        if rule.get("applies_when") and use is not None:
            key = ("applies_when", rule["applies_when"], use)
            if key not in memo:
                try:
                    memo[key] = formula.evaluate(rule["applies_when"], {"use": use}, kinds) is False
                except (formula.MissingMeasure, formula.EvaluationError):
                    memo[key] = False             # depends on what isn't known yet: it may apply, so asked
            if memo[key]:
                continue                          # not this use's rule: nothing it reads is asked
        key = ("names", id(rule))                 # the rule dicts live as long as the memo (one _options)
        if key in memo:
            wanted |= memo[key]
            continue
        names = reading_set.rule_names(rule)
        if parts.is_part_rule(rule):
            # a rule for each part: its parts' own measures come from the parts (the interior), never asked in the
            # box; the building facts it reads (stories, use) are asked like any rule's, so its rows aren't left
            # needing review for a fact the architect was never asked (a fact not asked is unknown: needs review)
            try:
                names -= parts.all_measures()
            except (ValueError, OSError):     # parts.yaml broken (python -m rule_format says so): every name kept
                pass
        memo[key] = frozenset(names)
        wanted |= names
    return wanted


def options(jurisdiction: str) -> dict:
    """What the confirm dialog offers: the zones that have a rulebook, the city's use names, and per district the
    uses its chart lists (use_choices) and per use the facts to ask after it (follow_up_facts); and the uses whose
    buildings the Building Code covers (building_code_uses), for the Setup form's occupancy group and sprinkler system.

    Worked out once per exact input (the answer depends on nothing else): every file it reads is read once here
    (_options_files), the answer is worked out from those bytes alone, and it is kept by their SHA-256 and names
    (the folder listing decides the zones) and by the code's own lists it reads (_options_lists). A file changed in
    any way, added or removed is worked out again. What is kept is the answer pickled, and every call un-pickles a
    fresh copy, so a caller that edits what it got can't change the next caller's. An error is never kept (the
    same error every time), and at most _OPTIONS_MAX answers are (least recently used goes first)."""
    j = REPO / jurisdiction
    files = _options_files(j)
    key = (tuple((name, None if data is None else hashlib.sha256(data).digest()) for name, data in files.items()),
           _options_lists())
    with _OPTIONS_LOCK:
        frozen = _OPTIONS.get(key)
        if frozen is not None:
            _OPTIONS.move_to_end(key)
    if frozen is None:
        frozen = pickle.dumps(_options(j, files), protocol=pickle.HIGHEST_PROTOCOL)
        with _OPTIONS_LOCK:
            _OPTIONS[key] = frozen
            while len(_OPTIONS) > _OPTIONS_MAX:
                _OPTIONS.popitem(last=False)
    return pickle.loads(frozen)


_OPTIONS: "OrderedDict[tuple, bytes]" = OrderedDict()   # (input names and SHA-256s, code lists) -> answer, pickled
_OPTIONS_LOCK = threading.Lock()                      # the Rhino command may ask from more than one thread
_OPTIONS_MAX = 16                                     # a session has one city; tests writing temp cities stay bounded
USES_FILE = "4_term_definitions/uses.yaml"


def _options_files(j: Path) -> dict:
    """Every file options reads, by its path in the jurisdiction (as posix), sorted: each rulebook the folder listing
    finds (5_zoning_rules/*.yaml and 5_zoning_rules/drafted/*.yaml, hand-drafted and AI-drafted both, whichever
    rulebook_for picks), the city's uses (uses.yaml) and the settings (state.yaml) of each state law the place
    inherits, each with its bytes, None for a rulebook name that isn't a file, for no uses.yaml and no state.yaml (one that is there but can't be read, a folder, is an error, as before). The only place
    options reads the disk: the answer is worked out from these bytes and names alone, even which rulebook is a
    district's (test_options_cache pins that nothing else is opened or looked at)."""
    found = [p for folder in (j / "5_zoning_rules", j / "5_zoning_rules/drafted") if folder.is_dir()
             for p in folder.glob("*.yaml")]
    files = {p.relative_to(j).as_posix(): p.read_bytes() if p.is_file() else None
             for p in sorted(set(found), key=lambda p: p.relative_to(j).as_posix())}
    uses = j / USES_FILE
    files[USES_FILE] = uses.read_bytes() if uses.exists() else None
    # the settings of each state law the place inherits (whether it splits buildings between books: building_code_uses),
    # by their path from the place's folder ("../new_york_state/state.yaml")
    try:
        inherited = [folder for folder, _ in place_of_folder(j).inherited_rulebooks()]
    except UnknownPlace:                          # a folder that is no place (a copy of a city's rulebooks) inherits none
        inherited = []
    for folder in inherited:
        settings = folder / STATE_SETTINGS
        files[Path(os.path.relpath(settings, j)).as_posix()] = settings.read_bytes() if settings.is_file() else None
    return files



def building_code_uses(names: dict, files: dict) -> list:
    """The uses whose buildings the Building Code covers whatever else is stated (code_scope.by_use), in the uses
    file's order, where a state law the place inherits splits buildings between books (state.yaml `scope`: New
    York's); none elsewhere. A host's Setup form asks for the facts the Building Code's rules turn on (occupancy
    group, sprinkler system) before the first check of such a use (UI polish, Ben 2026-11-23)."""
    def splits(data):
        try:
            got = load_bytes(data) if data is not None else None
        except Exception:                         # a settings file that can't be read splits nothing (its own problem
            return False                          # is said by the check, state_settings_problems)
        return isinstance(got, dict) and got.get("scope") in code_scope.CODES
    if not any(splits(data) for name, data in files.items() if name.startswith("../") and name.endswith("/" + STATE_SETTINGS)):
        return []
    return [u for u in names if code_scope.by_use(u) == code_scope.BUILDING]


def _options_lists():
    """The code's own lists the options answer reads (a test may swap one): which facts are stated, drawn, interior
    or implied by a use, and how each measure is typed."""
    return repr((list(logic.STATED_FACTS), sorted(INTERIOR), tuple(logic.DRAWN_FACTS),
                 sorted((u, sorted(v.items())) for u, v in logic.IMPLIED_BY_USE.items()),
                 sorted(MEASURE_KINDS.items())))


def _options(j: Path, files: dict) -> dict:
    """The options answer, from the files' bytes (_options_files) alone."""
    def read(path: Path):
        data = files.get(path.relative_to(j).as_posix())
        if data is None:                          # appeared or went between the listing and now: never a guess
            raise ValueError(f"{path} changed while the options were read; ask again")
        return load_bytes(data)
    def there(path: Path) -> bool:                # rulebook_for's choice made from what was read, never the disk
        return files.get(path.relative_to(j).as_posix()) is not None
    zones = sorted({Path(name).stem for name, data in files.items() if name != USES_FILE and data is not None
                    and rulebook_for(j, Path(name).stem, there)})
    uses = (read(j / USES_FILE) or {}) if files.get(USES_FILE) is not None else {}
    names = {k: v.get("name", k) for k, v in uses.items() if isinstance(v, dict)}
    district_uses, follow_ups, implied, memo = {}, {}, {}, {}
    books = []                                    # every rulebook kept alive with the memo, which keys rules by id
    for zone in zones:
        rules = read(rulebook_for(j, zone, there))["rules"]
        books.append(rules)
        district_uses[zone] = use_choices(rules, names, zone)
        every = list(dict.fromkeys([u["id"] for u in district_uses[zone]] + list(names)))   # a saved use the
        read_for = {u: _read_for(rules, u, names, memo) for u in every}                     # district doesn't list
        follow_ups[zone] = {u: follow_up_facts(rules, u, names, read_for[u]) for u in every}   # is asked its own
        implied[zone] = {u: implied_for(rules, u, names, read_for[u]) for u in every}          # too
    return {"zones": zones, "uses": names, "district_uses": district_uses, "follow_ups": follow_ups,
            "implied": implied, "building_code_uses": building_code_uses(names, files)}
