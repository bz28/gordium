"""Stairs (R318.7): each flight's risers, treads, headroom and clear width.

A flight is given by the leading edge (nosing) of each tread, bottom to top, ending with the nosing of the floor
or landing at its top, and the finished elevation at its foot. Only straight flights with rectangular treads are
measured: winder treads (R318.7.5.2.1) are measured at the walkline, not yet, so they give no value.

Coordinates along the flight: s runs up the flight, at a right angle to the first nosing; a runs across it, to the
left looking up. Definitions: docs/interior/interior_measurements.md.
"""

import math

from shapely.geometry import Polygon, box
from shapely.ops import transform, unary_union

from model_measurement.interior.geometry import Surface, least_gap, shapes
from model_measurement.interior.read import tidy, yes_no
from model_measurement.interior.stops import Stop

LEVEL = 1 / 16          # in: a nosing's ends may differ this much in height, or in position along the run
# in: how far a drawn side (a wall face) may stand out beyond the tread ends: what lies between them below handrail
# height, a skirt board or a stringer, at most a 2x stringer's actual 1 1/2 in. Farther, the side isn't this stair's
STRINGER = 1.5
STRINGER_WORDS = "1 1/2"


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
            if a1 == a2:                                          # a point, not a nosing across the stair
                raise Stop("not_a_polyline", what=f"nosing {n} (its two ends)")
            self.ends.append((min(a1, a2), max(a1, a2)))          # (right end, left end)
        # coordinates so large their squares overflow give a run direction of NaN, which every comparison above lets
        # through: no value, never a NaN depth or a crash further on
        if not all(map(math.isfinite, [*self.r, *(v for e in self.s_ends + self.ends for v in e)])):
            raise Stop("nosings_out_of_range")
        # each tread at its shallowest and its deepest (the nosings' ends paired the worst way)
        self.treads = [b[0] - a[1] for a, b in zip(self.s_ends, self.s_ends[1:])]
        self.treads_most = [b[1] - a[0] for a, b in zip(self.s_ends, self.s_ends[1:])]
        for n, depth in enumerate(self.treads, 1):
            if depth <= 0:
                raise Stop("nosings_not_forward", n=n, depth=tidy(depth))
        return self

    def span(self):
        """From the first nosing to the farther end of the top one, along the run: the whole flight."""
        return self.s_ends[0][0], self.s_ends[-1][1]

    def tread_spans(self):
        """Where each tread's end stands along the run: [(s from, s to, (right a, left a))]. A tread reaches from its
        nosing's nearer end to the next one's farther end (a nosing drawn a hair askew is covered at both ends, and
        where two treads overlap both count), and the top nosing stands between its own two ends."""
        out = [(a[0], b[1], e) for a, b, e in zip(self.s_ends, self.s_ends[1:], self.ends)]
        return out + [(self.s_ends[-1][0], self.s_ends[-1][1], self.ends[-1])]

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
            return a1 if s2 == s1 else a1 + (s - s1) / (s2 - s1) * (a2 - a1)
    return None


def side_lines(st: dict, flight: Flight, reader) -> dict:
    """Each side of the flight, left and right: its plan line from `along`, run from the first nosing to the top
    one, or "open" (nothing bounds it: the tread ends do)."""
    start, end = flight.span()
    sides = st.get("sides")
    if not isinstance(sides, dict):
        raise Stop("missing", what="the stair's sides (left and right)")
    out = {}
    for side in ("left", "right"):
        given = sides.get(side)
        if given == "open":
            out[side] = "open"
            continue
        line = along(flight, reader.points(given, 2, f"the stair's {side} side", 2), "side", side)
        if at(line, start) is None or at(line, end) is None:
            raise Stop("side_not_along", side=side, what="side")
        off = side_off_treads(line, flight, side)
        if off > STRINGER + 1e-9:
            raise Stop("side_off_treads", side=side, off=tidy(off), most=STRINGER_WORDS)
        out[side] = line
    return out


def side_off_treads(line, flight: Flight, side: str) -> float:
    """How far a drawn side stands out beyond its treads' ends, at most (0 where every tread reaches it or runs past
    it, into the wall). A side bounds the stair only where it stands at the tread ends (a skirt or stringer between,
    STRINGER at most): drawn farther off, it would widen the stair, and anything checked against it (a guard on it,
    a handrail between the sides) would count wherever it is. Each tread holds its nosing's end back to the next
    nosing (Flight.tread_spans); the side is straight between its points, so the gap is greatest at a point of it
    or at a tread's ends: exact."""
    k = 1 if side == "left" else 0
    sign = 1 if side == "left" else -1
    worst = 0.0
    for s1, s2, e in flight.tread_spans():
        for s in {s1, s2, *(s for s, _ in line if s1 < s < s2)}:
            worst = max(worst, sign * (at(line, s) - e[k]))
    return worst


def widths(st: dict, flight: Flight, reader) -> tuple[float, float | None, int | None, str | None]:
    """(clear width above the handrail, clear width at and below it, handrail sides, why the second or the third
    isn't measured)."""
    start, end = flight.span()
    given_sides = side_lines(st, flight, reader)
    # each tread is a rectangle: its nosing's ends hold back to the next nosing (never drawn toward it, which would
    # widen a tread below a wider one), and where two treads meet, both count; the top nosing counts between its
    # own two ends, so a side read to its farther end is read over a tread there (Flight.tread_spans)
    k = {"right": 0, "left": 1}
    treads = {side: [[(s1, e[k[side]]), (s2, e[k[side]])] for s1, s2, e in flight.tread_spans()] for side in k}
    bound = {}
    for side, line in given_sides.items():
        bound[side] = treads[side] if line == "open" else [line]
    handrails, why = {"left": [], "right": []}, None
    given = st.get("handrails")
    if not isinstance(given, list):
        why = Stop("missing", what="the stair's handrails (an empty list for none)").reason
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
    for line in [*bound["left"], *bound["right"], *treads["left"], *treads["right"], *handrails["left"],
                 *handrails["right"]]:
        breaks |= {s for s, _ in line if start <= s <= end}
    breaks = sorted(breaks)

    def inward(side, lines, s):
        got = [a for a in (at(line, s) for line in lines) if a is not None]
        return min(got) if side == "left" else max(got)

    def least(left, right):
        return min(inward("left", left, s) - inward("right", right, s) for s in breaks)

    above = least(bound["left"], bound["right"])
    if above <= 0:
        raise Stop("sides_cross", width=tidy(above))
    at_treads = least([*bound["left"], *treads["left"]], [*bound["right"], *treads["right"]])
    if at_treads <= 0:                   # the treads lie beyond a side: the width above them still stands
        return above, None, None, Stop("treads_cross", width=tidy(at_treads)).reason
    if why:
        return above, None, None, why
    low = least([*bound["left"], *treads["left"], *handrails["left"]],
                [*bound["right"], *treads["right"], *handrails["right"]])
    if low <= 0:                         # the handrails do it (the sides alone don't): the width above them stands
        return above, None, None, Stop("handrails_cross", width=tidy(low)).reason
    # a side has a handrail (R318.7.1) only where one runs the whole flight, from above its lowest nosing to above
    # the top one (R320.5): one drawn part way, or off the flight, would credit the side with a handrail it lacks
    # and between the stair's sides: one beyond a wall, or past an open side's tread ends, isn't this stair's
    first, top = flight.span()

    def on_stair(line):
        if at(line, first) is None or at(line, top) is None:
            return False
        return all(inward("right", bound["right"], s) <= at(line, s) <= inward("left", bound["left"], s)
                   for s in breaks)

    for side, lines in handrails.items():
        if lines and not any(on_stair(line) for line in lines):
            return above, low, None, Stop("handrail_part_way", side=side).reason
    return above, low, sum(1 for side in handrails.values() if side), None


def headroom(st: dict, flight: Flight, reader) -> float:
    """The least height from the line connecting the nosings up to anything overhead, over the flight's whole
    width from its first nosing to its top one (R318.7.2)."""
    given = st.get("overhead")
    if given is None:
        raise Stop("missing", what="what is above the flight")
    if not isinstance(given, list):
        raise Stop("not_a_list", key="overhead")
    if not given:
        raise Stop("nothing_overhead")
    surfaces = [Surface(reader.points(p, 3, f"overhead surface {n}", 3), f"overhead surface {n}")
                for n, p in enumerate(given, 1)]
    # each tread is a rectangle: its nosing's width, back to the next riser. With the shape between neighbouring
    # nosings, a tread wider than the next (a flared starter step) is covered all over, never cut at a corner.
    # Along the run each reaches from its nosing's nearer end to the next one's farther end: a nosing drawn a hair
    # askew (within LEVEL) is covered at both its ends (the first one sets the run, so it is never askew)
    # Everything is worked out in the flight's own frame (s along the run, a across it), where the treads' edges run
    # along or across the run: unioned and cut in plan, near-parallel edges of a turned flight made the geometry
    # library fail
    with shapes("what is overhead"):
        quads = []
        for j in range(len(flight.s) - 1):
            (r1, l1), (r2, l2) = flight.ends[j], flight.ends[j + 1]
            s1, s2 = flight.s_ends[j][0], flight.s_ends[j + 1][1]
            quads.append(Polygon([(s1, r1), (s2, r2), (s2, l2), (s1, l1)]))
            quads.append(Polygon([(s1, r1), (s2, r1), (s2, l1), (s1, l1)]))
        # and each nosing's own strip, across its own ends, between its nearer and farther end along the run: the top
        # one is no tread's start, so where it is wider than the one below, its nearer end lay outside the area
        for (s1, s2), (r, l) in zip(flight.s_ends, flight.ends):
            if s2 > s1:
                quads.append(Polygon([(s1, r), (s2, r), (s2, l), (s1, l)]))
        # cut the flight at every bend of the nosing line, so the line is straight over each piece and the least gap
        # is at a piece's corner (the pieces of the treads alone would hide a bend inside one)
        first, top = flight.span()
        cuts = sorted({first, top, *(s for s, _ in flight.line() if first < s < top)})
        wide = max(abs(a) for ends in flight.ends for a in ends) + 1.0
        pieces = []
        band = unary_union(quads)
        for s1, s2 in zip(cuts, cuts[1:]):
            pieces.append((band.intersection(box(s1, -wide, s2, wide)), lambda s, a: flight.nosing_z(s)))
        # and the overhead surfaces seen in the same frame (turning a shape keeps its area and its corners)
        framed = [InFrame(f, flight) for f in surfaces]
    return least_gap(framed, pieces, "what is overhead", "flight")


def headroom_past_bottom(st: dict, flight: Flight, reader) -> float:
    """The 2025 Building Code of New York State's 1011.3 headroom past the foot of the flight: "Such headroom shall be
    continuous above the stairway to the point where the line intersects the landing below, one tread depth beyond
    the bottom riser." The least height to anything overhead, over the first nosing's width, from the first nosing
    back to the farther of one tread depth (the flight's deepest: treads are measured between nosings, and the bottom
    riser's face stands at or behind the first nosing, never in front of it) and wherever the line connecting the
    nosings, carried on down at its first slope, meets the floor or landing at the foot (a bottom riser taller than
    the next puts that farther back; review round 1). The height is taken from that line, and from the floor or
    landing wherever the line has gone below it (a bottom riser shorter than the next; review round 2), never from
    under the floor. Needs two nosings (the flight placed in plan). Used by the
    Building Code check only (model_measurement/routes/stair_rooms.py): the house code's R318.7.2 has no such
    stretch."""
    given = st.get("overhead")
    if given is None:
        raise Stop("missing", what="what is above the flight")
    if not isinstance(given, list):
        raise Stop("not_a_list", key="overhead")
    if not given:
        raise Stop("nothing_overhead")
    surfaces = [Surface(reader.points(p, 3, f"overhead surface {n}", 3), f"overhead surface {n}")
                for n, p in enumerate(given, 1)]
    (s1, z1), (s2, z2) = flight.line()[:2]
    slope = (z2 - z1) / (s2 - s1)
    meets = (z1 - flight.bottom) / slope if slope > 0 else 0       # how far back the line reaches the floor
    back = max(max(flight.treads_most), meets)
    right, left = flight.ends[0]
    with shapes("what is overhead"):
        # over the line where it stands above the floor; over the floor beyond (each reference flat or straight over
        # its piece, so the least gap is at a piece's corner)
        pieces = [(Polygon([(s1 - meets, right), (s1, right), (s1, left), (s1 - meets, left)]),
                   lambda s, a: z1 - (s1 - s) * slope)] if meets > 0 else []
        if back > meets:
            pieces.append((Polygon([(s1 - back, right), (s1 - meets, right), (s1 - meets, left), (s1 - back, left)]),
                           lambda s, a: flight.bottom))
        framed = [InFrame(f, flight) for f in surfaces]
    return least_gap(framed, pieces, "what is overhead", "stretch one tread depth past the flight's bottom riser")


class InFrame:
    """A surface seen in a flight's own frame (s, a): its plan turned into it, its height read back in plan."""

    def __init__(self, surface: Surface, flight: Flight):
        self.plan = transform(lambda x, y: (flight.s_of(x, y), flight.a_of(x, y)), surface.plan)
        self.z = lambda s, a: surface.z(*flight.xy(s, a))


def _spiral(st: dict, not_straight: str | None, measures: dict, stopped: dict) -> None:
    """`stair_spiral` from the description's `spiral` (the host's own record of the flight's shape: Revit's run
    style), taken only where the nosings agree with it. A spiral stairway (R202) is "a stairway with a plan view of
    closed circular form and uniform section-shaped treads, attached to and radiating from a minimum-diameter
    supporting column": a flight measured as straight with rectangular treads (`not_straight` None) is not one. So
    `false` is taken only for a flight measured straight. `true` is never taken yet: nothing measured shows that
    closed circular form (a flight that isn't measured straight may be any curved stair), and true would make the
    ordinary R318.7 rules not applicable (review round 1: a false-pass path for a curved stair). Otherwise, or not
    given, it is not measured (its rules need review)."""
    try:
        said = yes_no(st, "spiral", "the flight", "it is a spiral stairway", required=False)
    except Stop as s:
        said = s
    if isinstance(said, Stop):
        stopped["stair_spiral"] = said.reason
    elif said is None:
        stopped["stair_spiral"] = Stop("spiral_not_said").reason
    elif said is False and not_straight is not None:
        stopped["stair_spiral"] = Stop("spiral_not_straight", reason=not_straight).reason
    elif said is True:
        stopped["stair_spiral"] = Stop("spiral_but_straight" if not_straight is None else "spiral_not_shown").reason
    else:
        measures["stair_spiral"] = said


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
        _spiral(st, s.reason, measures, stopped)
        return measures, more, stopped, None
    measures["stair_riser_height"] = tidy(max(flight.risers))
    # the variation is R318.7.5.1's own measure ("The greatest riser height within any flight of stairs shall not
    # exceed the smallest by more than 3/8 inch"), each riser read at its tallest and shortest: given to the rules
    # (Ben, 2026-11-20: a riser drawn taller than the rest fails the flight, never only needs review)
    measures["stair_riser_variation"] = tidy(max(flight.risers) - min(flight.risers_least))
    more.update(stair_total_rise=tidy(flight.z[-1] - flight.bottom), stair_risers=len(flight.risers))
    try:
        flight.plan()
    except Stop as s:
        stop(names, s.reason)
        _spiral(st, s.reason, measures, stopped)
        return measures, more, stopped, None
    _spiral(st, None, measures, stopped)
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
            # given to the rules (section group 7c, 2026-11-26: worked out and tested since 2026-11-13, kept in
            # `more` until a rule needed it), and kept in `more` too, where the panel has shown it
            more["stair_clear_width_at_handrail"] = measures["stair_clear_width_at_handrail"] = tidy(low)
            if why:
                stop(["stair_handrail_sides"], why)
            else:
                more["stair_handrail_sides"] = measures["stair_handrail_sides"] = rails
    except Stop as s:
        stop(["stair_clear_width", "stair_clear_width_at_handrail", "stair_handrail_sides"], s.reason)
    return measures, more, stopped, flight

