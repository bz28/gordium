"""Stairs (R318.7): each flight's risers, treads, headroom and clear width.

A flight is given by the leading edge (nosing) of each tread, bottom to top, ending with the nosing of the floor
or landing at its top, and the finished elevation at its foot. Only straight flights with rectangular treads are
measured: winder treads (R318.7.5.2.1) are measured at the walkline, not yet, so they give no value.

Coordinates along the flight: s runs up the flight, at a right angle to the first nosing; a runs across it, to the
left looking up. Definitions: docs/interior/interior_measurements.md.
"""

from shapely.geometry import Polygon
from shapely.ops import unary_union

from model_measurement.interior.geometry import Surface, least_gap
from model_measurement.interior.read import tidy
from model_measurement.interior.stops import Stop

LEVEL = 1 / 16          # in: a nosing's ends may differ this much in height, or in position along the run


class Flight:
    """The nosings read: their heights z, their places s along the run, and their ends' places a across it."""

    def __init__(self, st: dict, reader):
        given = st.get("nosings")
        if not isinstance(given, list) or not given:
            raise Stop("too_few_nosings", n=1)
        self.bottom = reader.length(st.get("bottom_elevation"), "the stair's bottom elevation")
        self.nosings = []
        for n, g in enumerate(given, 1):
            ends = reader.points(g, 3, f"nosing {n}", 2)
            if len(ends) != 2:
                raise Stop("not_a_polyline", what=f"nosing {n} (its two ends)")
            (x1, y1, z1), (x2, y2, z2) = ends
            if abs(z1 - z2) > LEVEL:
                raise Stop("nosing_not_level", n=n, off=tidy(abs(z1 - z2)))
            self.nosings.append(((x1, y1), (x2, y2), (min(z1, z2), max(z1, z2))))
        # a nosing's ends may differ by drawing noise: each riser is read at its tallest and its shortest (ends
        # paired the worst way), and the line connecting the nosings at their higher ends (less headroom above it)
        low = [self.bottom] + [z[0] for _, _, z in self.nosings]
        high = [self.bottom] + [z[1] for _, _, z in self.nosings]
        self.z = high[1:]
        self.risers = [b - a for a, b in zip(low, high[1:])]               # tallest
        self.risers_least = [b - a for a, b in zip(high, low[1:])]         # shortest
        for n, rise in enumerate(self.risers_least, 1):
            if rise <= 0:
                raise Stop("not_bottom_to_top", n=n, rise=tidy(rise))

    def plan(self):
        """Place the flight in plan (needs two nosings): the run and across directions, each nosing's s and its
        ends' a. Stop on winders or nosings that don't move up the run."""
        if len(self.nosings) < 2:
            raise Stop("too_few_nosings", n=2)
        (p1, p2, _), (q1, q2, _) = self.nosings[0], self.nosings[1]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        size = (dx * dx + dy * dy) ** 0.5
        if size == 0:
            raise Stop("not_a_polyline", what="nosing 1 (its two ends)")
        rx, ry = -dy / size, dx / size                          # at a right angle to the first nosing
        mid = ((q1[0] + q2[0]) / 2 - p1[0], (q1[1] + q2[1]) / 2 - p1[1])
        if rx * mid[0] + ry * mid[1] < 0:                         # pointing up the flight
            rx, ry = -rx, -ry
        self.origin, self.r, self.a = p1, (rx, ry), (-ry, rx)     # a: the run turned left
        self.s, self.s_ends, self.ends = [], [], []
        for n, (e1, e2, _) in enumerate(self.nosings, 1):
            s1, s2 = self.s_of(*e1), self.s_of(*e2)
            if abs(s1 - s2) > LEVEL:
                raise Stop("winders", n=n, off=tidy(abs(s1 - s2)))
            self.s.append((s1 + s2) / 2)
            self.s_ends.append((min(s1, s2), max(s1, s2)))
            a1, a2 = self.a_of(*e1), self.a_of(*e2)
            self.ends.append((min(a1, a2), max(a1, a2)))          # (right end, left end)
        # each tread at its shallowest and its deepest (the nosings' ends paired the worst way)
        self.treads = [b[0] - a[1] for a, b in zip(self.s_ends, self.s_ends[1:])]
        self.treads_most = [b[1] - a[0] for a, b in zip(self.s_ends, self.s_ends[1:])]
        for n, depth in enumerate(self.treads, 1):
            if depth <= 0:
                raise Stop("nosings_not_forward", n=n, depth=tidy(depth))
        return self

    def s_of(self, x, y):
        return (x - self.origin[0]) * self.r[0] + (y - self.origin[1]) * self.r[1]

    def a_of(self, x, y):
        return (x - self.origin[0]) * self.a[0] + (y - self.origin[1]) * self.a[1]

    def xy(self, s, a):
        return (self.origin[0] + s * self.r[0] + a * self.a[0], self.origin[1] + s * self.r[1] + a * self.a[1])

    def line(self):
        """The line connecting the nosings, the cautious way: through each nosing's higher end, placed at its end
        nearer the foot (so the line, which rises, stands as high as either end lets it): [(s, z)]."""
        return [(lo, z) for (lo, _), z in zip(self.s_ends, self.z)]

    def nosing_z(self, s):
        """The height of the line connecting the nosings at s; past either end of it, level with that end."""
        pts = self.line()
        if s <= pts[0][0]:
            return pts[0][1]
        for (s1, z1), (s2, z2) in zip(pts, pts[1:]):
            if s <= s2:
                return z1 + (s - s1) / (s2 - s1) * (z2 - z1)
        return pts[-1][1]


def along(flight: Flight, points, what: str, side: str):
    """A plan line as a function a(s) along the flight: [(s, a)] with s increasing. Stop if it doubles back or
    doesn't run the flight's whole length. Coverage is the caller's (a handrail may run part of it)."""
    sa = [(flight.s_of(x, y), flight.a_of(x, y)) for x, y in points]
    if sa[0][0] > sa[-1][0]:
        sa.reverse()
    if any(b[0] <= a[0] for a, b in zip(sa, sa[1:])):
        raise Stop("side_not_along", side=side, what=what)
    return sa


def at(line, s):
    """a(s) on a line from `along`, or None where it doesn't reach."""
    for (s1, a1), (s2, a2) in zip(line, line[1:]):
        if s1 - 1e-9 <= s <= s2 + 1e-9:
            return a1 + (s - s1) / (s2 - s1) * (a2 - a1)
    return None


def widths(st: dict, flight: Flight, reader) -> tuple[float, float | None, int | None, str | None]:
    """(clear width above the handrail, clear width at and below it, handrail sides, why the second or the third
    isn't measured)."""
    start, end = flight.s[0], flight.s[-1]
    sides = st.get("sides")
    if not isinstance(sides, dict):
        raise Stop("missing", what="the stair's sides (`sides`: left and right)")
    treads = {"right": [(s, e[0]) for s, e in zip(flight.s, flight.ends)],
              "left": [(s, e[1]) for s, e in zip(flight.s, flight.ends)]}
    bound = {}
    for side in ("left", "right"):
        given = sides.get(side)
        if given == "open":
            bound[side] = treads[side]
            continue
        line = along(flight, reader.points(given, 2, f"the stair's {side} side", 2), "side", side)
        if at(line, start) is None or at(line, end) is None:
            raise Stop("side_not_along", side=side, what="side")
        bound[side] = line
    handrails, why = {"left": [], "right": []}, None
    given = st.get("handrails")
    if not isinstance(given, list):
        why = Stop("missing", what="the stair's handrails (`handrails`: a list, empty for none)").reason
    else:
        for n, h in enumerate(given, 1):
            if not isinstance(h, dict):
                raise Stop("not_a_mapping", what="handrail", n=n)
            side = h.get("side")
            if side not in ("left", "right"):
                raise Stop("handrail_side", got=side)
            handrails[side].append(along(flight, reader.points(h.get("inner_edge"), 2, f"handrail {n}'s inner edge",
                                                               2), "handrail", side))
    breaks = {start, end}
    for line in [*bound.values(), *treads.values(), *handrails["left"], *handrails["right"]]:
        breaks |= {s for s, _ in line if start <= s <= end}
    breaks = sorted(breaks)

    def inward(side, lines, s):
        got = [a for a in (at(line, s) for line in lines) if a is not None]
        return min(got) if side == "left" else max(got)

    above = min(inward("left", [bound["left"]], s) - inward("right", [bound["right"]], s) for s in breaks)
    if above <= 0:
        raise Stop("sides_cross", width=tidy(above))
    if why:
        return above, None, None, why
    low = min(inward("left", [bound["left"], treads["left"], *handrails["left"]], s)
              - inward("right", [bound["right"], treads["right"], *handrails["right"]], s) for s in breaks)
    if low <= 0:
        raise Stop("sides_cross", width=tidy(low))
    # a side has a handrail (R318.7.1) only where one runs the whole flight, from above its lowest nosing to above
    # the top one (R320.5): one drawn part way, or off the flight, would credit the side with a handrail it lacks
    first, top = flight.s_ends[0][0], flight.s_ends[-1][1]
    for side, lines in handrails.items():
        if lines and not any(at(line, first) is not None and at(line, top) is not None for line in lines):
            return above, low, None, Stop("handrail_part_way", side=side).reason
    return above, low, sum(1 for side in handrails.values() if side), None


def headroom(st: dict, flight: Flight, reader) -> float:
    """The least height from the line connecting the nosings up to anything overhead, over the flight's whole
    width from its first nosing to its top one (R318.7.2)."""
    given = st.get("overhead")
    if given is None:
        raise Stop("missing", what="what is above the flight (`overhead`)")
    if not isinstance(given, list):
        raise Stop("not_a_list", key="overhead")
    if not given:
        raise Stop("nothing_overhead")
    surfaces = [Surface(reader.points(p, 3, f"overhead surface {n}", 3), f"overhead surface {n}")
                for n, p in enumerate(given, 1)]
    quads = []
    for j in range(len(flight.s) - 1):
        (r1, l1), (r2, l2) = flight.ends[j], flight.ends[j + 1]
        quads.append(Polygon([flight.xy(flight.s[j], r1), flight.xy(flight.s[j + 1], r2),
                              flight.xy(flight.s[j + 1], l2), flight.xy(flight.s[j], l1)]))
    band = unary_union(quads)
    # cut the flight at every bend of the nosing line, so the line is straight over each piece and the least gap
    # is at a piece's corner (the pieces of the treads alone would hide a bend inside one)
    cuts = sorted({flight.s[0], flight.s[-1], *(s for s, _ in flight.line() if flight.s[0] < s < flight.s[-1])})
    wide = max(abs(a) for ends in flight.ends for a in ends) + 1.0
    pieces = []
    for s1, s2 in zip(cuts, cuts[1:]):
        strip = Polygon([flight.xy(s1, -wide), flight.xy(s2, -wide), flight.xy(s2, wide), flight.xy(s1, wide)])
        pieces.append((band.intersection(strip), lambda x, y: flight.nosing_z(flight.s_of(x, y))))
    return least_gap(surfaces, pieces, "what is overhead", "flight")


def measure_stair(st: dict, reader) -> tuple[dict, dict, dict, Flight | None]:
    """(measures, more, not_measured, the flight placed in plan or None) for one flight."""
    measures, more, stopped = {}, {}, {}
    names = ("stair_riser_height", "stair_riser_variation", "stair_total_rise", "stair_risers", "stair_tread_depth",
             "stair_tread_variation", "stair_headroom", "stair_clear_width", "stair_clear_width_at_handrail",
             "stair_handrail_sides")

    def stop(which, reason):                                   # every measure not yet measured
        for n in which:
            if n not in measures and n not in more:
                stopped.setdefault(n, reason)

    try:
        flight = Flight(st, reader)
    except Stop as s:
        stop(names, s.reason)
        return measures, more, stopped, None
    measures["stair_riser_height"] = tidy(max(flight.risers))
    more.update(stair_riser_variation=tidy(max(flight.risers) - min(flight.risers_least)),
                stair_total_rise=tidy(flight.z[-1] - flight.bottom), stair_risers=len(flight.risers))
    try:
        flight.plan()
    except Stop as s:
        stop(names, s.reason)
        return measures, more, stopped, None
    measures["stair_tread_depth"] = tidy(min(flight.treads))
    more["stair_tread_variation"] = tidy(max(flight.treads_most) - min(flight.treads))
    try:
        measures["stair_headroom"] = tidy(headroom(st, flight, reader))
    except Stop as s:
        stop(["stair_headroom"], s.reason)
    try:
        above, low, rails, why = widths(st, flight, reader)
        measures["stair_clear_width"] = tidy(above)
        if low is None:
            stop(["stair_clear_width_at_handrail", "stair_handrail_sides"], why)
        else:
            more["stair_clear_width_at_handrail"] = tidy(low)
            if why:
                stop(["stair_handrail_sides"], why)
            else:
                more["stair_handrail_sides"] = rails
    except Stop as s:
        stop(["stair_clear_width", "stair_clear_width_at_handrail", "stair_handrail_sides"], s.reason)
    return measures, more, stopped, flight

