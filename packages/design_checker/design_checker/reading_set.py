"""THE set of readings a check is decided over: one enumeration for the checker's verdict (check.every_reading:
Fails and Provisional) and for what the panel says and colours (present.settle). Plain code; no AI.

A value a rule reads is uncertain when
  - its measurement has several readings (which lot lines are side or rear, wall or overhang): each one;
  - the lot lines are from the tax map (facts given and the lot not surveyed): a lot length off by its
    TAX_MAP_SLACK either way (a yard by 2'-0", a lot width or depth, between two lines, by 4'-0"), and the lot
    area at the low and high ends its measurement gives (tolerance).
Readings of two measurements under different readings of the lot's side and rear lines are never combined (the
lot depth of one reading with the rear yard of another isn't a real case), which also keeps the count small.
"""

import itertools
import math

from model_measurement.measure import TAX_MAP_SLACK

LOT_LENGTHS = {"lot_width", "lot_depth", "front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard"}
MAX_READINGS = 20000          # more combinations than this: not worked out (left for review, never a result)


def rule_names(rule: dict) -> set:
    """Every name a rule reads: its applies_when, its check and each review_when (the one list the verdict, the
    open questions and a row's "Enter …" all read)."""
    from rule_format import formula
    names = set()
    for key in ("applies_when", "check"):
        if rule.get(key):
            names |= formula.names(rule[key])
    for r in rule.get("review_when") or []:
        names |= formula.names(r["when"])
    return names


def lot_reading(words: str | None) -> str | None:
    """Which reading of the lot's side and rear lines a measurement's reading is under ("line 13 as a rear lot
    line, ..."), or None when it doesn't depend on one."""
    first = (words or "").split("; ")[0]
    return first if " lot line" in first else None


def tax_map(measured: dict, facts: dict | None) -> bool:
    """Whether the tax map's slack applies: facts given, the lot not surveyed, and a lot area with a tolerance."""
    return facts is not None and not facts.get("lot_surveyed") and \
        bool((measured.get("lot_area") or {}).get("tolerance"))


def choices(n: str, values: dict, measured: dict, facts: dict | None) -> list[tuple]:
    """Every value measure `n` could take: (value as measured, its points, its lot reading, value in the trial,
    how far the trial value was raised to keep it from going below 0).
    A measure with a value: that value; else each of its readings. On the tax map a lot length is also off by its
    slack either way, and the lot area is at the low or high end of its tolerance. Empty: unknown."""
    rec = measured.get(n) or {}
    tax = tax_map(measured, facts)
    if n == "lot_area" and tax:
        tol = rec["tolerance"]
        return [(tol["low"], None, None, tol["low"], 0.0), (tol["high"], None, None, tol["high"], 0.0)]
    if values.get(n) is not None:            # a value (a number, or a word such as the use): that one
        base = [(values[n], tuple(map(tuple, rec.get("points") or [])) or None, None)]
    else:
        base = list(dict.fromkeys((r["value"], tuple(map(tuple, r.get("points") or rec.get("points") or [])) or None,
                                   lot_reading(r.get("reading")))
                                  for r in rec.get("readings") or [] if r.get("value") is not None))
    if n in LOT_LENGTHS and tax:            # never below 0: a wall within the slack of its line is at most on it
        return [(v, p, k, max(0.0, v + d * TAX_MAP_SLACK[n]), max(0.0, -(v + d * TAX_MAP_SLACK[n])))
                for v, p, k in base for d in (-1, 1)]
    return [(v, p, k, v, 0.0) for v, p, k in base]


def combos(names, values: dict, measured: dict, facts: dict | None = None):
    """Every combination of the names' values, the readings of one lot reading kept together: a list of
    (trial values, picks: {name: (value as measured, points, how far its trial value was raised from below 0)}).
    [] when a name's value is unknown; None when there are more than MAX_READINGS."""
    names = sorted(names)
    per = [choices(n, values, measured, facts) for n in names]
    if any(not c for c in per):
        return []
    keys = sorted({c[2] for cs in per for c in cs if c[2] is not None}) or [None]
    groups = [g for g in ([[c for c in cs if c[2] in (None, key)] for cs in per] for key in keys) if all(g)]
    if sum(math.prod(len(o) for o in g) for g in groups) > MAX_READINGS:
        return None
    out = []
    for options in groups:
        for combo in itertools.product(*options):
            out.append((dict(values, **{n: c[3] for n, c in zip(names, combo)}),
                        {n: (c[0], [list(p) for p in c[1]] if c[1] else None, c[4]) for n, c in zip(names, combo)}))
    return out
