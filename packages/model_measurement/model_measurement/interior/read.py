"""Reading values out of an interior description: every length turned into inches, every shape checked.

A value that isn't there or isn't the right shape raises Stop: that measurement gets no value. Nothing is ever
filled in with a default. The format: docs/interior/interior_description_format.md.
"""

import math

from shapely.geometry import Polygon

from model_measurement.interior.stops import Stop, given_as

FORMAT = "gordium.interior/1"
INCHES = {"in": (1, 1), "ft": (12, 1), "mm": (1, 25.4), "m": (1000, 25.4)}   # (times, divided by)
# in: the farthest any length may be, about 15,800 miles. Every length a house can have is far inside it, and inside
# it every sum, difference, product and area worked out from lengths stays a finite number: no measure can overflow
# to infinity (where `inf <= inf` passes a check, or an empty overlap is read as covered)
FAR = 1e9


def number(value, what: str) -> float:
    """A plain number (never true/false, never infinite or NaN)."""
    if value is None:
        raise Stop("missing", what=what)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Stop("not_a_length", what=what)
    try:
        value = float(value)
    except OverflowError:                                    # an integer too big for a float
        raise Stop("not_a_length", what=what) from None
    if not math.isfinite(value):
        raise Stop("not_a_length", what=what)
    return value


def yes_no(item: dict, key: str, what: str, question: str, required: bool):
    """A yes/no mark (a room's sleeping, lockable, pass_through, not_occupied; an opening's escape; a door's exit; a
    flight's spiral; an obstruction's fixed): True or False as given; not given, None where it is optional, else
    flag_missing ("door D01 doesn't say whether it is the required exit door (yes or no)"); given as anything
    else, flag_not_yes_no ("door D01 gives whether it is the required exit door as the text 'yes', not as a yes/no
    value"), never read as yes or no. `what`: who says it ("door D01", or "it" where the reason already names it)."""
    got = item.get(key) if isinstance(item, dict) else None
    if isinstance(got, bool):
        return got
    if got is None:
        if required:
            raise Stop("flag_missing", what=what, question=question)
        return None
    raise Stop("flag_not_yes_no", what=what, question=question, got=given_as(got))


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
        got = number(value, what) * self.times / self.per
        if not math.isfinite(got):                           # finite as written, not once in inches
            raise Stop("not_a_length", what=what)
        if abs(got) > FAR:
            raise Stop("too_far", what=what)
        return got

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
