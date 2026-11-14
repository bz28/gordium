"""Reading values out of an interior description: every length turned into inches, every shape checked.

A value that isn't there or isn't the right shape raises Stop: that measurement gets no value. Nothing is ever
filled in with a default. The format: docs/interior/interior_description_format.md.
"""

import math

from shapely.geometry import Polygon

from model_measurement.interior.stops import Stop

FORMAT = "gordium.interior/1"
INCHES = {"in": (1, 1), "ft": (12, 1), "mm": (1, 25.4), "m": (1000, 25.4)}   # (times, divided by)


def number(value, what: str) -> float:
    """A plain number (never true/false, never infinite or NaN)."""
    if value is None:
        raise Stop("missing", what=what)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise Stop("not_a_length", what=what)
    return float(value)


def choice(value, choices, what: str):
    if value is None:
        raise Stop("missing", what=what)
    if not isinstance(value, str) or value not in choices:
        raise Stop("choice", what=what, got=value, choices=", ".join(choices))
    return value


class Reader:
    """Lengths in the description's own units, read as inches."""

    def __init__(self, units: str):
        self.times, self.per = INCHES[units]

    def length(self, value, what: str) -> float:
        return number(value, what) * self.times / self.per

    def size(self, value, what: str) -> float:
        """A length that can't be less than zero (a width, a thickness, an offset)."""
        got = self.length(value, what)
        if got < 0:
            raise Stop("negative", what=what, value=tidy(got))
        return got

    def point(self, value, n: int, what: str) -> tuple:
        if not isinstance(value, (list, tuple)) or len(value) != n:
            raise Stop("not_a_point", what=what, n=n)
        return tuple(self.length(v, what) for v in value)

    def points(self, value, n: int, what: str, least: int) -> list[tuple]:
        if value is None:
            raise Stop("missing", what=what)
        if not isinstance(value, (list, tuple)) or len(value) < least:
            raise Stop("not_an_outline" if least >= 3 else "not_a_polyline", what=what)
        return [self.point(v, n, what) for v in value]

    def outline(self, value, what: str) -> Polygon:
        """A closed plan outline (x, y), simple and enclosing an area."""
        poly = Polygon(self.points(value, 2, what, 3))
        if not poly.is_valid or poly.area <= 0:
            raise Stop("not_an_outline", what=what)
        return poly

    def rectangle(self, value, what: str) -> tuple:
        """left, right, bottom, top in an element's own elevation (u along it, z up)."""
        if value is None:
            raise Stop("missing", what=what)
        if not isinstance(value, dict):
            raise Stop("not_a_rectangle_given", what=what)
        left, right, bottom, top = (self.length(value.get(k), f"{what}'s {k}") for k in ("left", "right", "bottom",
                                                                                          "top"))
        if not (right > left and top > bottom):
            raise Stop("not_a_rectangle_given", what=what)
        return left, right, bottom, top


def name_of(part: dict) -> str:
    return str(part.get("name") or part.get("id") or "(no name)")


def tidy(value: float) -> float:
    """Float noise off (to a millionth of an inch or sq ft, far finer than any drawing): 5.699999999 is 5.7."""
    return round(value, 6) + 0.0
