"""Remoteness and the diagonal (decision 7 of docs/decisions/2026-11-20_route_measurement.md): straight lines, exact.

    remoteness(story) -> Remoteness(length, exits, doors, centres)
    diagonal(story)   -> Diagonal(length, corners)
    ratio(story)      -> (remoteness, diagonal, ratio)

The distance between two exits is the straight line between the nearest edges of their clear openings (NFPA 101
7.5.1.3.2 "measured in a straight line between the nearest edge of the exits"; the IBC names no point, and the
nearest edge is the shortest choice), through walls, as both books say "in a straight line". A door's clear opening
is taken through the whole wall (its clear width by the wall's thickness), so its nearest edge is on whichever face
is nearer the other exit: the shortest choice again, the less favourable for a rule asking for at least so much.
Between two exits with several doors each (one stair enclosure entered by two doors, one `exit_id`), their closest
pair of doors counts; the two farthest-apart exits count. Fewer than two distinct exits: no remoteness.

The diagonal is the longest straight line between two corners of the story's outer outline (the longest line in a
polygon always ends at corners, so this is exact; the outer faces give the longer diagonal, the cautious side).
Door centres, the figure a sheet may have measured instead, are given beside (`centres`). Lengths in inches.
"""

import math
from dataclasses import dataclass
from itertools import combinations

from shapely.geometry import LineString, Point, Polygon

from model_measurement.routes.floor import Door, Story
from model_measurement.routes.stops import Stop


@dataclass
class Remoteness:
    length: float             # in: the two farthest-apart exits, nearest edges of their closest doors
    exits: tuple              # their exit ids
    doors: tuple              # the door ids that gave it
    centres: float            # in: the same worked between door centres (for a sheet that measured so)


@dataclass
class Diagonal:
    length: float             # in
    corners: tuple            # its two ends


def opening(door: Door) -> Polygon:
    """The door's clear opening through its wall: its clear width along the wall, the wall's thickness across."""
    (cx, cy), (ax, ay), (nx, ny) = door.centre, door.along, door.normal
    w, t = door.width / 2, door.thickness / 2
    return Polygon([(cx + ax * u + nx * v, cy + ay * u + ny * v) for u, v in ((-w, -t), (w, -t), (w, t), (-w, t))])


def _exits(story: Story) -> dict:
    out = {}
    for d in story.exits():
        out.setdefault(d.exit_id, []).append(d)
    return out


def remoteness(story: Story) -> Remoteness:
    exits = _exits(story)
    if len(exits) < 2:
        raise Stop("too_few_exits", count=len(exits))
    best = None
    for a, b in combinations(sorted(exits), 2):
        near = min(((opening(x).distance(opening(y)), x.id, y.id) for x in exits[a] for y in exits[b]))
        if best is None or near[0] > best.length:
            best = Remoteness(near[0], (a, b), (near[1], near[2]), 0.0)
    # the door-centre figure worked on its own (its farthest pair may be another)
    best.centres = max(min(math.dist(x.centre, y.centre) for x in exits[a] for y in exits[b])
                       for a, b in combinations(sorted(exits), 2))
    return best


def diagonal(story: Story) -> Diagonal:
    if story.outer is None:
        raise Stop("outline_needed", reason=story.outline_stop or "no outline is given for it")
    pts = list(story.outer.exterior.coords)[:-1]
    length, a, b = max((math.dist(p, q), p, q) for p, q in combinations(pts, 2))
    return Diagonal(length, (a, b))


SLACK = 0.5      # in: the outer outline holds every room and exit door to within this (rounding only)
WALL_MIN = 3.5   # in: the thinnest an exterior wall can be (a 2x4 stud wall alone): the outer outline is at least this
                 # far outside the inner one everywhere, as the walls' outer faces are outside their inside ones


def held(story: Story) -> None:
    """Refuse (Stop) outlines that could give a diagonal shorter than the story's: an outer outline that doesn't hold
    every room's outline and every exit door's clear opening (to within SLACK: drawn short, a wing only, a slip, a
    reader's bug); an inner outline that doesn't hold every room (the walls' inside faces are outside the rooms); and
    an outer outline that isn't at least WALL_MIN beyond every wall side of the inner one (drawn at the walls' inside
    faces, it holds every room but is a wall short at each end). Any of them would make close exits read as placed apart
    (BCNYS 1007.1.1, a false pass): never a diagonal from them."""
    if story.outer is None:
        return                                           # diagonal() says why
    shapes = [(r.name, r.outline) for r in story.rooms.values() if r is not None]
    exits = [(d.name, opening(d)) for d in story.exits()]
    bound = story.outer.buffer(SLACK)
    out = [name for name, shape in shapes + exits if not bound.covers(shape)]
    if story.inner is not None:
        inside = story.inner.buffer(SLACK)
        out += [name for name, shape in shapes if not inside.covers(shape) and name not in out]
    if out:
        out = sorted(set(out))                           # each name once (two rooms may share one)
        raise Stop("outline_short", names=", ".join(out[:3]) + (" and others" if len(out) > 3 else ""))
    if story.inner is None:                              # its inner outline not read: that reason, not a guess
        raise Stop("outline_needed", reason=story.outline_stop or "its inner outline isn't read")
    if not _walled(story.outer.buffer(SLACK), story.inner):
        raise Stop("outline_not_outer", wall=f"{WALL_MIN:g}")


WALL_SIDE = 36.0  # in: a side of the inner outline longer than this is a wall's inside face (a shorter one may be a
                  # wall's end where two walls in line stand apart, kept where it is: StoryOutlines.cs WallEnd, 2 ft on
                  # the outer outline, its inner side longer by the walls' difference in thickness, a foot here: a
                  # bigger difference is checked, and so refused, never a pass)


def _walled(bound, inner) -> bool:
    """Whether the outer outline (`bound`: grown by SLACK, rounding only) is at least WALL_MIN beyond the inner one
    along every wall: each wall side of the inner outline (longer than WALL_SIDE, its pieces in line joined), less
    WALL_MIN at each end, moved out by WALL_MIN, lies inside it, and so does each outside corner between two wall sides
    moved out by WALL_MIN along both (the corners the diagonal runs between, never cut back), whichever way the outline
    runs. An outline with no wall side long enough to check isn't shown to be outside it (False). An outer outline at
    the inside faces, on any wall or corner, fails."""
    pts = list(inner.simplify(SLACK / 8).exterior.coords)[:-1]   # pieces in line joined (a side given in short pieces)
    sides = []                                           # each side: (a, b, its length, its outward normal)
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        length = math.dist(a, b)
        if length <= 0:
            continue
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        nx, ny = uy, -ux                                 # one normal; flipped where it points into the inner outline
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if inner.contains(Point(mid[0] + nx, mid[1] + ny)):
            nx, ny = -nx, -ny
        sides.append((a, b, length, (ux, uy), (nx, ny)))
    d, checked = WALL_MIN, 0
    for k, (a, b, length, (ux, uy), (nx, ny)) in enumerate(sides):
        if length <= WALL_SIDE:
            continue
        checked += 1
        side = LineString([(a[0] + ux * d + nx * d, a[1] + uy * d + ny * d), (b[0] - ux * d + nx * d, b[1] - uy * d + ny * d)])
        if not bound.covers(side):
            return False
        a2, b2, length2, _, (mx, my) = sides[(k + 1) % len(sides)]
        dot = nx * mx + ny * my                          # where an outline WALL_MIN out puts the corner (a mitre:
        if dot <= -1 + 1e-9:                             # d (n + m) / (1 + n.m), d (n + m) at a square corner)
            continue
        corner = (b[0] + (nx + mx) * d / (1 + dot), b[1] + (ny + my) * d / (1 + dot))
        if length2 > WALL_SIDE and not inner.contains(Point(corner)) and not bound.covers(Point(corner)):
            return False                                 # an outside corner between two walls, cut back
    return checked > 0


def ratio(story: Story) -> tuple:
    """(remoteness, diagonal, their ratio): the branch's `exit_remoteness_ratio`, from outlines that hold the story
    (held)."""
    far, across = remoteness(story), diagonal(story)
    held(story)
    return far, across, far.length / across.length
