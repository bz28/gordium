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

from shapely.geometry import Polygon

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


def held(story: Story) -> None:
    """Refuse (Stop) an outer outline that doesn't hold every room's outline and every exit door's clear opening, to
    within SLACK: drawn short (a wing only, a slip, a reader's bug), it shrinks the diagonal, so close exits would read
    as placed apart (BCNYS 1007.1.1, a false pass); never a diagonal from it."""
    if story.outer is None:
        return                                           # diagonal() says why
    shapes = [(r.name, r.outline) for r in story.rooms.values() if r is not None] +         [(d.name, opening(d)) for d in story.exits()]
    bound = story.outer.buffer(SLACK)
    out = [name for name, shape in shapes if not bound.covers(shape)]
    if out:
        raise Stop("outline_short", names=", ".join(sorted(out)[:3]) + (" and others" if len(out) > 3 else ""))


def ratio(story: Story) -> tuple:
    """(remoteness, diagonal, their ratio): the branch's `exit_remoteness_ratio`, from an outer outline that holds the
    story (held)."""
    far, across = remoteness(story), diagonal(story)
    held(story)
    return far, across, far.length / across.length
