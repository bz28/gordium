"""Street lot lines: one street or two. Plain Python (math only): the measuring (measure.Lot) and the plugin's start
box (design_checker.rhino_logic, which loads this file by its path inside Rhino) decide it the same way.

The law: lot width is the lot's frontage on a public right-of-way (§325-8, Column 7: "Lots hereafter used for a
permitted use in each use district shall have frontage measured on a public right-of-way equal to or greater than the
width specified in this column"), so it is measured along one street; a length along two streets is no frontage.

One street or two is the street's identity first (the lookup's street; the name the architect gives a line): the
same street, however it bends, is one; two named streets are two. Only when no identity is known does the drawing
decide, and then only as a safety net: street lines whose heading changes more than TURN_LIMIT_DEG in all (a corner,
even one rounded into several short pieces) are an open question, never measured along both."""

import math

TURN_LIMIT_DEG = 30.0       # street lines turning more than this in all, their street unknown: one street or two?


def _near(p, q, tolerance):
    return abs(p[0] - q[0]) <= tolerance and abs(p[1] - q[1]) <= tolerance


def chain(lines, tolerance=0.5):
    """The lines (each a list of points: a straight line's two ends, or a curved edge's points) as one run of points,
    each line turned to follow the last; None if a line doesn't share an end with the one before."""
    lines = [[tuple(p[:2]) for p in line] for line in lines or [] if len(line) >= 2]
    if not lines:
        return None
    first = lines[0]
    if len(lines) > 1 and not (_near(first[-1], lines[1][0], tolerance) or _near(first[-1], lines[1][-1], tolerance)):
        first = first[::-1]                     # the first line points toward the second
    points = list(first)
    for line in lines[1:]:
        if _near(points[-1], line[0], tolerance):
            points += line[1:]
        elif _near(points[-1], line[-1], tolerance):
            points += line[::-1][1:]
        else:
            return None
    return points


def heading_change(lines, tolerance=0.5):
    """How far the street's direction swings along the lines, in degrees: the spread of the running heading (a
    corner rounded into four 22.5° pieces swings 90°, like a square one; a street gently curving a few degrees).
    None if the lines don't run end to end."""
    points = chain(lines, tolerance)
    if points is None:
        return None
    steps = [(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]) if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-9]
    run, low, high = 0.0, 0.0, 0.0
    for u, v in zip(steps, steps[1:]):
        turn = math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1]))
        run += turn
        low, high = min(low, run), max(high, run)
    return high - low


def matching_ids(lines, ids):
    """The street names `ids` when they match the street lines one for one (a list as long as `lines`, each a name
    or None), else None: THE validity rule for street_ids, for the measuring (a mismatch is stale, set aside) and the
    start box (a mismatch is unnamed, never indexed past its end; arch-fixes-2 review round 8)."""
    if isinstance(ids, list) and len(ids) == len(lines or []) and all(i is None or isinstance(i, str) for i in ids):
        return ids
    return None


def street_verdict(lines, ids=None, tolerance=0.5):
    """("one" | "two" | "unsure", the heading change or None): "two" when the lines name two different streets
    (`ids`, one per line, None where unknown); "one" when they all name one street, or, none named, they swing no
    more than TURN_LIMIT_DEG; "unsure" when nothing names them and they swing more (or don't run end to end)."""
    named = {_norm(i) for i in ids or [] if i}
    if len(named) > 1:
        return "two", None
    if named and len([i for i in ids if i]) == len(lines or []):
        return "one", None
    turn = heading_change(lines, tolerance)
    if turn is None or turn > TURN_LIMIT_DEG:
        return "unsure", turn
    return "one", turn


def _norm(name):
    return " ".join(str(name).lower().replace(".", " ").split())
