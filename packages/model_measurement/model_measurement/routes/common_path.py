"""Common path of egress travel (decision 5 of docs/decisions/2026-11-20_route_measurement.md), measured on the routes
themselves (paths.py), until those to two distinct exits part for good.

    shared(a, b)                          -> the travel distance from the start to the last point two routes share
    at_point(story_routes, p)             -> CommonPath(length, exits, routes)
    story_figure(story_routes, rooms=None) -> remote.Remote: decision 3's bound, with the common path as the value

IBC 2009 1002.1: "Paths that merge are common paths of travel." From a point clear of every ring, Gordium takes its
shortest route to each distinct exit (by `exit_id`, never by door). For two routes the common path is the travel
distance from the point to the **last point the two routes share** (a door centre, a ring, a stretch walked
together), so a stretch where they meet again after parting counts, and two routes that share only the start give 0.
Where two routes to one exit are equally short (within 1e-6 ft: paths.py keeps every tied route), the one that shares
more is taken (the cautious side). The point's common path is the least over the pairs of distinct exits it has
routes to. One exit on the story (or one the point reaches): the common path is the travel distance.

The story's figure is worked exactly as decision 3's (remote.farthest, the same samples, triangles and cluster
margins): the law's figure changes no faster than you walk, and Gordium's routes are one pair a person could take, so
its figure at a sample is never less than the law's. Lengths in inches.
"""

import math
from dataclasses import dataclass, field
from itertools import combinations

from model_measurement.routes.paths import EPS, StoryRoutes, _show
from model_measurement.routes.remote import Remote, farthest
from model_measurement.routes.stops import Stop

TOL = EPS                      # in: two routes this close share the point (their pieces come from the same formulas)
UNREACHED = ("no_route", "too_narrow")      # a point with no route to this exit (it may still have one to others)


@dataclass
class CommonPath:
    length: float              # in
    exits: tuple               # the pair of exit ids that gave it (one, when the point reaches one exit)
    routes: list = field(default_factory=list)      # the two routes taken (the tie that shares more)


# --- where two routes meet -------------------------------------------------------------------------------------------

def _arc_ends(piece):
    _, c, r, a, s = piece
    return (c[0] + r * math.cos(a), c[1] + r * math.sin(a)), (c[0] + r * math.cos(a + s), c[1] + r * math.sin(a + s))


def _on_arc(piece, q) -> float | None:
    """How far along the arc q lies (in), or None if q isn't on it (within TOL)."""
    _, c, r, a0, sweep = piece
    if abs(math.dist(q, c) - r) > TOL:
        return None
    off = ((math.atan2(q[1] - c[1], q[0] - c[0]) - a0) * (1 if sweep >= 0 else -1)) % (2 * math.pi)
    slack = TOL / r
    if off <= abs(sweep) + slack:
        return min(off, abs(sweep)) * r
    if off >= 2 * math.pi - slack:
        return 0.0
    return None


def _on_line(piece, q) -> float | None:
    _, a, b = piece
    d = (b[0] - a[0], b[1] - a[1])
    n = math.hypot(*d)
    if n <= TOL:
        return 0.0 if math.dist(a, q) <= TOL else None
    t = ((q[0] - a[0]) * d[0] + (q[1] - a[1]) * d[1]) / n
    if t < -TOL or t > n + TOL:
        return None
    foot = (a[0] + d[0] * t / n, a[1] + d[1] * t / n)
    return min(max(t, 0.0), n) if math.dist(foot, q) <= TOL else None


def _along(piece, q):
    return _on_line(piece, q) if piece[0] == "line" else _on_arc(piece, q)


def _ends(piece):
    return (piece[1], piece[2]) if piece[0] == "line" else _arc_ends(piece)


def _line_line(p, q) -> list:
    (_, a1, b1), (_, a2, b2) = p, q
    d1, d2 = (b1[0] - a1[0], b1[1] - a1[1]), (b2[0] - a2[0], b2[1] - a2[1])
    cross = d1[0] * d2[1] - d1[1] * d2[0]
    n1, n2 = math.hypot(*d1), math.hypot(*d2)
    if abs(cross) <= 1e-12 * max(n1 * n2, 1e-300):
        return []                                    # parallel: any meeting is an end on the other (taken apart)
    w = (a2[0] - a1[0], a2[1] - a1[1])
    t = (w[0] * d2[1] - w[1] * d2[0]) / cross
    return [(a1[0] + d1[0] * t, a1[1] + d1[1] * t)]


def _line_circle(line, c, r) -> list:
    _, a, b = line
    d = (b[0] - a[0], b[1] - a[1])
    n = math.hypot(*d)
    if n <= TOL:
        return []
    u = (d[0] / n, d[1] / n)
    t = (c[0] - a[0]) * u[0] + (c[1] - a[1]) * u[1]
    foot = (a[0] + u[0] * t, a[1] + u[1] * t)
    h = math.dist(foot, c)
    if abs(h - r) <= TOL:
        return [foot]                                # a tangent: it touches the ring at its foot
    if h > r:
        return []
    k = math.sqrt(r * r - h * h)
    return [(foot[0] - u[0] * k, foot[1] - u[1] * k), (foot[0] + u[0] * k, foot[1] + u[1] * k)]


def _circle_circle(c1, r1, c2, r2) -> list:
    d = math.dist(c1, c2)
    if d <= TOL or d > r1 + r2 + TOL or d < abs(r1 - r2) - TOL:
        return []
    a = (d * d + r1 * r1 - r2 * r2) / (2 * d)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    m = (c1[0] + (c2[0] - c1[0]) * a / d, c1[1] + (c2[1] - c1[1]) * a / d)
    if h <= TOL:
        return [m]
    ox, oy = -(c2[1] - c1[1]) * h / d, (c2[0] - c1[0]) * h / d
    return [(m[0] + ox, m[1] + oy), (m[0] - ox, m[1] - oy)]


def _meetings(p, q) -> list:
    """Candidate points both pieces may hold: every end of each (an overlap's ends are among them), and where the two
    cross or touch. Each is kept only if it lies on both."""
    out = list(_ends(p)) + list(_ends(q))
    if p[0] == "line" and q[0] == "line":
        out += _line_line(p, q)
    elif p[0] == "line" or q[0] == "line":
        line, arc = (p, q) if p[0] == "line" else (q, p)
        out += _line_circle(line, arc[1], arc[2])
    elif math.dist(p[1], q[1]) > TOL or abs(p[2] - q[2]) > TOL:
        out += _circle_circle(p[1], p[2], q[1], q[2])
    return out


def _starts(pieces) -> list:
    s, out = 0.0, []
    for q in pieces:
        out.append(s)
        s += math.dist(q[1], q[2]) if q[0] == "line" else abs(q[4]) * q[2]
    return out


def shared(a, b) -> float:
    """The travel distance (in) from the start of two routes from one point to the last point they share. Both are
    shortest routes from that point, so the stretch of each up to a shared point is as long as the other's; the
    greater of the two is taken (the cautious side)."""
    sa, sb = _starts(a.pieces), _starts(b.pieces)
    best = 0.0
    for i, p in enumerate(a.pieces):
        for j, q in enumerate(b.pieces):
            for x in _meetings(p, q):
                u, v = _along(p, x), _along(q, x)
                if u is not None and v is not None:
                    best = max(best, sa[i] + u, sb[j] + v)
    return best


# --- a point ---------------------------------------------------------------------------------------------------------

def at_point(routes: StoryRoutes, point) -> CommonPath:
    """The common path from a point clear of every ring (decision 5)."""
    tied, first = {}, None
    for e in sorted(routes.exits):
        try:
            tied[e] = routes.routes(point, [e])
        except Stop as s:
            if s.key not in UNREACHED:
                raise
            first = first or s
    if not tied:
        raise first if first is not None else Stop("no_route", x=_show(point)[0], y=_show(point)[1], exits="any exit")
    if len(tied) == 1:                                   # one exit: the common path is the travel distance
        (e, got), = tied.items()
        return CommonPath(got[0].length, (e,), [got[0]])
    best = None
    for e1, e2 in combinations(sorted(tied), 2):
        most = max(((shared(x, y), x, y) for x in tied[e1] for y in tied[e2]), key=lambda t: t[0])
        if best is None or most[0] < best.length:
            best = CommonPath(most[0], (e1, e2), [most[1], most[2]])
    return best


# --- the story's figure ----------------------------------------------------------------------------------------------

class _Rooms:
    def __init__(self, story, rooms):
        self.rooms = {k: v for k, v in story.rooms.items() if rooms is None or k in rooms}


class _CommonPathSampler:
    """What remote.farthest reads (`r`, `story.rooms`, `rings_for`, `travel`), with the common path as the value."""

    def __init__(self, routes: StoryRoutes, rooms=None):
        self.r, self._routes = routes.r, routes
        self.story = _Rooms(routes.story, rooms)

    def rings_for(self, room):
        return self._routes.rings_for(room)

    def travel(self, point, exit_ids=None):
        return at_point(self._routes, point).length


def story_figure(routes: StoryRoutes, rooms=None) -> Remote:
    """The greatest common path over the story's floor (or these rooms' only), as decision 3's bound: the clear floor's
    greatest sample plus 3 in (4.5 in next to the rings), each ring cluster's greatest clear-edge sample plus 1.5 in
    plus its margin (the walk out is shared by both routes). One exit on the story: the travel figure itself."""
    if len(routes.exits) < 2:
        return farthest(_TravelOnly(routes, rooms) if rooms is not None else routes)
    return farthest(_CommonPathSampler(routes, rooms))


class _TravelOnly(_CommonPathSampler):
    def travel(self, point, exit_ids=None):
        return self._routes.travel(point, exit_ids)
