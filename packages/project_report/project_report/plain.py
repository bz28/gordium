"""The report in an architect's words: measure names as titles, lengths in feet and inches, areas in whole square
feet, no file names. Display only: every value and verdict is worked out before this, from the checker's numbers.

Rounding is never in the design's favour: a proposed value is rounded toward failing its limit (down against
"at least", up against "at most"), and a limit toward being stricter."""

import math
import re

from rule_format.rulebook import MEASURES_FILE, load

MEASURES = load(MEASURES_FILE)
TITLES = {k: k.replace("_", " ").capitalize() for k in MEASURES}
# measures whose limits are maxima: a value is rounded up for them where no limit says which way
MAXIMA = {"building_height", "building_area", "stories", "lot_coverage"}
_NAME = re.compile(r"\b(" + "|".join(sorted(map(re.escape, MEASURES), key=len, reverse=True)) + r")\b")
_NUMBER = r"-?\d[\d,]*(?:\.\d+)?"


def feet_inches(x: float, toward: str | None = None) -> str:
    """A length in feet as an architect writes it, to the nearest 1/8 inch, rounded `toward` "down" or "up" (or
    to the nearest): 75.835 -> 75'-10", 22.5 -> 22'-6", 0.14 -> 0'-1 5/8"."""
    eighths = x * 12 * 8
    n = math.floor(eighths + 1e-9) if toward == "down" else math.ceil(eighths - 1e-9) if toward == "up" \
        else round(eighths)
    sign, n = ("-" if n < 0 else ""), abs(n)
    feet, rest = divmod(n, 96)
    inches, frac = divmod(rest, 8)
    if frac:
        g = math.gcd(frac, 8)
        return f"{sign}{feet}'-{inches} {frac // g}/{8 // g}\""
    return f"{sign}{feet}'-{inches}\""


def number(x: float, unit: str, toward: str | None = None) -> str:
    """A value with its unit, as the report shows it: ft in feet and inches, sf in whole square feet (with a
    comma), other numbers as written."""
    if unit == "ft":
        return feet_inches(x, toward)
    if unit == "sf":
        n = math.floor(x + 1e-9) if toward == "down" else math.ceil(x - 1e-9) if toward == "up" else round(x)
        return f"{n:,} sf"
    if float(x).is_integer():
        return f"{int(x):,}"
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def _value(text: str) -> float:
    return float(text.replace(",", ""))


def _unit(name: str) -> str:
    return MEASURES.get(name, {}).get("unit", "")


def _direction(op: str, proposed: bool) -> str | None:
    """Which way to round: a proposed value toward failing, a limit toward strict."""
    at_least = op in ("≥", ">")
    at_most = op in ("≤", "<")
    if not (at_least or at_most):
        return None
    return ("down" if at_least else "up") if proposed else ("up" if at_least else "down")


def names(text: str, use_names: dict | None = None) -> str:
    """Every measure name as its title, every use id as its name, and × for *: the words, not the code."""
    text = re.sub(r"\buse (not in|in) \[([^\]]*)\]",
                  lambda m: ("Use: one of " if m.group(1) == "in" else "Use: none of ") +
                  "; ".join((use_names or {}).get(u.strip(" '\""), u.strip(" '\"")) for u in m.group(2).split(",")),
                  str(text))
    out = _NAME.sub(lambda m: TITLES[m.group(1)], text)
    for k, v in sorted((use_names or {}).items(), key=lambda kv: -len(kv[0])):
        out = re.sub(r"(?<![\w\"'])" + re.escape(k) + r"(?![\w\"'])", v, out)
        out = out.replace(f"'{k}'", v).replace(f'"{k}"', v)
    return out.replace(" * ", " × ")


def limit(text, unit: str, use_names=None) -> str:
    """A Table limit in words: "≥ 22.5" (ft) -> "≥ 22'-6""; "Building height ≤ 35 or …" with each number in its
    measure's unit."""
    if not isinstance(text, str):
        return text
    single = re.fullmatch(r"([≥≤<>=≠]) (" + _NUMBER + r")", text)
    if single and unit in ("ft", "sf"):
        return f"{single.group(1)} {number(_value(single.group(2)), unit, _direction(single.group(1), False))}"

    def each(m):
        name, op, value = m.group(1), m.group(2), m.group(3)
        return f"{name} {op} {number(_value(value), _unit(name), _direction(op, False))}" if _unit(name) in ("ft", "sf") \
            else m.group(0)
    text = re.sub(r"\b([a-z_]+) ([≥≤<>=≠]) (" + _NUMBER + r")(?![\w.])", each, text)
    return names(text, use_names)


def proposed(value, unit: str, limit_text, use_names=None):
    """A Proposed value in words, rounded toward failing the limit beside it."""
    lim = limit_text if isinstance(limit_text, str) else ""
    if type(value) in (int, float) and unit in ("ft", "sf"):
        op = lim[:1]
        return number(value, unit, _direction(op, True))
    if not isinstance(value, str):
        return value

    def each(m):
        name, raw = m.group(1), m.group(2)
        found = re.search(re.escape(name) + r" ([≥≤<>])", lim)
        toward = _direction(found.group(1), True) if found else ("up" if name in MAXIMA else "down")
        return f"{name} = {number(_value(raw), _unit(name), toward)}" if _unit(name) in ("ft", "sf") else m.group(0)
    return names(re.sub(r"\b([a-z_]+) = (" + _NUMBER + r")(?![\w.])", each, value), use_names)


def input_value(name: str, value):
    """An input's value in words, rounded the cautious way for its kind (a maximum up, anything else down)."""
    if type(value) in (int, float) and _unit(name) in ("ft", "sf"):
        return number(value, _unit(name), "up" if name in MAXIMA else "down")
    return value


def source(text) -> str:
    """Where a value came from, without file names: "measured from x.3dm: …" -> "measured from the model: …"."""
    text = re.sub(r"measured from [^\s:]+\.3dm", "measured from the model", str(text))
    return names(text)


def meaning(text: str) -> str:
    """A measure's meaning without the repository's file names."""
    return re.sub(r"\s*\([^)]*\.(?:yaml|py|jsonl)\)", "", str(text))
