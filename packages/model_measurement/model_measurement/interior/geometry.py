"""Flat surfaces over a plan region: the least clear height between a surface above and a reference surface below.

Used for a stair's headroom (the surfaces overhead against the line of the nosings) and a room's ceiling height
(the ceiling against the floor). Exact, never sampled: over a flat piece, the gap between two flat surfaces
changes linearly, so its least value is at a corner of where the piece and the region overlap.
"""

import math
from contextlib import contextmanager

from shapely.errors import GEOSException
from shapely.geometry import Polygon
from shapely.ops import unary_union

from model_measurement.interior.stops import Stop

FLAT = 1 / 16          # in: a surface's points may be this far off its plane (drawing noise)
COVER = 1e-6           # the share of a region's area a surface may leave uncovered (float noise)


class Surface:
    """A flat surface given by its corner points (x, y, z, in inches): its height over any plan point."""

    def __init__(self, points: list[tuple], what: str):
        # Newell's normal: robust for any simple polygon, whatever its first three points
        nx = ny = nz = 0.0
        for (x1, y1, z1), (x2, y2, z2) in zip(points, points[1:] + points[:1]):
            nx += (y1 - y2) * (z1 + z2)
            ny += (z1 - z2) * (x1 + x2)
            nz += (x1 - x2) * (y1 + y2)
        size = (nx * nx + ny * ny + nz * nz) ** 0.5
        if not all(map(math.isfinite, (nx, ny, nz, size))):     # coordinates so large their products overflow
            raise Stop("surface_out_of_range", what=what)
        if size == 0 or abs(nz) / size < 1e-6:
            raise Stop("surface_vertical", what=what)
        self.n = (nx / size, ny / size, nz / size)
        cx, cy, cz = (sum(p[i] for p in points) / len(points) for i in range(3))
        self.c = (cx, cy, cz)
        off = max(abs((x - cx) * self.n[0] + (y - cy) * self.n[1] + (z - cz) * self.n[2]) for x, y, z in points)
        if off > FLAT:
            raise Stop("surface_not_flat", what=what, off=round(off, 3))
        plan = Polygon([(x, y) for x, y, _ in points])
        if not plan.is_valid or plan.area <= 0:
            raise Stop("not_an_outline", what=what)
        self.plan = plan
        # how far the drawn points stand below the fitted plane, at most: the plane is lowered by it, so no drawn
        # point is ever lower than the surface read (the cautious side for headroom and ceiling height)
        self.below = max(0.0, max(self._fit(x, y) - z for x, y, z in points))

    def _fit(self, x: float, y: float) -> float:
        (a, b, c), (cx, cy, cz) = self.n, self.c
        return cz - (a * (x - cx) + b * (y - cy)) / c

    def z(self, x: float, y: float) -> float:
        return self._fit(x, y) - self.below


@contextmanager
def shapes(what: str):
    """Plan shapes worked out by the geometry library: if it fails on them (edges so nearly parallel it can't tell
    where they meet), that measure gets no value with a reason, never a crash that loses the whole house."""
    try:
        yield
    except GEOSException:
        raise Stop("shapes_failed", what=what) from None


def corners(geom) -> list[tuple]:
    """Every corner point of a shapely result, whatever its type (an overlap can be a polygon, several, or a line
    where two only touch)."""
    if geom.is_empty:
        return []
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in corners(g)]
    if isinstance(geom, Polygon):
        return [p for ring in [geom.exterior, *geom.interiors] for p in ring.coords]
    return list(geom.coords)


def covers(surfaces: list[Surface], pieces: list) -> bool:
    """Whether the surfaces, seen from above, cover the whole region (given in pieces: each is checked on its own,
    never unioned with its neighbours, whose shared edges can be too nearly parallel for the geometry library)."""
    plans = unary_union([s.plan for s in surfaces])
    left = sum(p.difference(plans).area for p in pieces)
    whole = sum(p.area for p in pieces)
    if not (math.isfinite(left) and math.isfinite(whole)):  # read.FAR keeps areas finite; never let inf <= inf pass
        raise Stop("surface_out_of_range", what="the region")
    return left <= COVER * whole


def least_gap(surfaces: list[Surface], pieces: list[tuple], what: str, region_words: str) -> float:
    """The least height of the surfaces above a reference over a region.

    pieces: [(plan polygon, reference height function)], the region in pieces over each of which the reference is
    flat (one per tread of a flight; one for a room's floor). The surfaces must cover the whole region (else Stop:
    a gap could be open sky or something not sent); where they overlap the lowest counts."""
    with shapes(what):
        if not covers(surfaces, [p for p, _ in pieces]):
            raise Stop("not_covered", what=what, region=region_words)
        gaps = [s.z(x, y) - ref(x, y)
                for poly, ref in pieces for s in surfaces for x, y in corners(s.plan.intersection(poly))]
    if not all(map(math.isfinite, gaps)):                     # never let one surface drop out of the least
        raise Stop("surface_out_of_range", what=what)
    if not gaps:                                              # nothing read over the region: never min() of none
        raise Stop("not_covered", what=what, region=region_words)
    return min(gaps)
