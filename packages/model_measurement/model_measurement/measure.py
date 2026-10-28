"""Measure a lot and its buildings the way the city defines each measurement. Plain code, no AI.

Input is plain geometry (see `read_3dm.read_site`): the lot outline as edges, each building as polygon faces,
all in feet, plus lot facts the architect states (which lot line is on the street, the ground level, the use,
stories, bedrooms, parking). Output is one record per measurement in measures.yaml:

    {"value": 30.0 | None, "unit": "ft", "how": "...", "definition": "front_yard", "objects": [...],
     "points": [[x, y], [x, y]], "readings": [{"reading": "...", "value": 30.0}], "reason": None | "..."}

Never a guess (principle 4). Where the law can be read more than one way (is a jog a side or a rear lot line?
is a yard measured to the wall or to the eave?), every reading is measured. If they all give the same number,
that is the value; if not, the value is None, the readings are listed, and the reason says which open question
decides it, so the checker gives NEEDS REVIEW. Anything missing (no street side given, a building outside the
lot, curved surfaces) also gives None with a reason.
"""

import copy
import hashlib
import itertools
import math

import numpy as np
import shapely
from shapely import STRtree, ops
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.validation import explain_validity

from rule_format.rulebook import MEASURES_FILE, load

from . import interpretations as law
from .stops import stop
from .street_lines import matching_ids, street_verdict

MEASURES = list(load(MEASURES_FILE))

TOL = 0.01                # ft: two points closer than this are the same point
SAME = 1e-6               # ft: readings closer than this give the same value
PARALLEL = 30             # degrees: street lines turning more than this between them turn a corner
FLAT = math.cos(math.radians(2.39))   # a roof face flatter than 1/2 inch per foot (a drainage slope) is level
MAX_UNCLEAR_EDGES = 6     # more lot lines than this that could be side or rear: too many readings to list
STATED = {"use": "text", "stories": "count", "sleeping_rooms": "count", "parking_spaces": "count",
          "dwelling_units": "count", "rooms_let_for_profit": "count", "conversion": "yes_no",
          "occupants": "count", "occupants_most_in_one_unit": "count",
          "attached_units_in_building": "count", "abuts_r1_district": "yes_no",
          "unrelated_persons": "count", "unrelated_persons_with_children": "count", "owner_occupied": "yes_no",
          "functional_family_unit": "yes_no", "home_occupation": "yes_no", "home_occupation_area": "sf",
          "home_occupation_unit_area": "sf", "accessory_dwelling_unit": "yes_no"}
ASK = {"use": "no_use", "stories": "no_stories", "sleeping_rooms": "no_rooms", "parking_spaces": "no_rooms",
       "dwelling_units": "no_units", "rooms_let_for_profit": "no_units", "conversion": "no_units",
       "occupants": "no_occupants", "occupants_most_in_one_unit": "no_occupant_split",
       "attached_units_in_building": "no_building_units", "abuts_r1_district": "no_abuts_r1",
       "unrelated_persons": "no_household", "unrelated_persons_with_children": "no_household",
       "owner_occupied": "no_household", "functional_family_unit": "no_household",
       "home_occupation": "no_home_occupation", "home_occupation_area": "no_home_occupation",
       "home_occupation_unit_area": "no_home_occupation", "accessory_dwelling_unit": "no_household"}
UNITS = {"lot_area": "sf", "lot_width": "ft", "lot_depth": "ft", "building_area": "sf", "building_height": "ft",
         "front_yard": "ft", "side_yard_smaller": "ft", "side_yard_larger": "ft", "rear_yard": "ft",
         "front_yard_eaves": "ft", "side_yard_smaller_eaves": "ft", "side_yard_larger_eaves": "ft",
         "rear_yard_eaves": "ft", "accessory_front_yard": "ft", "accessory_side_yard": "ft",
         "accessory_rear_yard": "ft", "accessory_buildings": "count", "accessory_distances_apply": "yes_no"}
YARDS = ("front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard")
EAVE_YARDS = tuple(f"{y}_eaves" for y in YARDS)
ACCESSORY_YARDS = ("accessory_front_yard", "accessory_side_yard", "accessory_rear_yard")
LOT_LINE_MEASURES = ("lot_width", "lot_depth") + YARDS + EAVE_YARDS + ACCESSORY_YARDS   # need the street side
TOUCH = 0.1               # ft: a solid this close to the main building (in plan) is part of it (a porch, steps)


def _r(x: float) -> float:
    return round(x, 6) + 0.0          # drops float noise (and -0.0); never rounds toward a limit by more than 1e-6


def _record(definition, unit, value=None, how="", objects=(), points=None, readings=(), reason=None,
            basis=()) -> dict:
    """One measurement. `basis`: the findings it applies (interpretations.basis: the law, or Gordium's reading to
    confirm), so the panel can say so. Each reading may carry `named`: {open-question tag: reading id}, the
    readings research lists, so the checker combines them question by question (check.every_reading)."""
    return {"value": value, "unit": unit, "how": how, "definition": definition, "objects": list(objects),
            "points": points, "readings": list(readings), "reason": reason, "basis": [b for b in basis if b]}


class _Stop(Exception):
    """A measurement can't go on: its reason (from the stops table)."""


def _missing(name: str, reason: str) -> dict:
    return _record(name, UNITS.get(name) or STATED[name], reason=reason)


def _decide(name: str, readings: list[tuple[str, float, dict]], how: str, objects, question: str,
            basis=()) -> dict:
    """One value if every reading gives the same number; else None, with the readings and the question."""
    values = [v for _, v, _ in readings]
    shown = [{"reading": r, "value": _r(v), **({"points": x["points"]} if x.get("points") else {}),
              **({"named": dict(x["named"])} if x.get("named") else {}),
              **({"line": x["line"]} if x.get("line") is not None else {}),
              **({"pairing": x["pairing"]} if x.get("pairing") is not None else {})} for r, v, x in readings]
    if values and max(values) - min(values) <= SAME:
        how = how if len(readings) > 1 or not readings[0][0] else f"{how} ({readings[0][0]})"
        return _record(name, UNITS.get(name) or STATED[name], _r(values[0]), how, objects, readings[0][2].get("points"),
                       shown if len(readings) > 1 else [], basis=basis)
    # no value, but where it was measured is still known: the line of the smallest reading (for a yard, the
    # cautious one), so the panel can name the side and the viewport can draw it
    least = min(readings, key=lambda r: r[1])[2].get("points")
    return _record(name, UNITS.get(name) or STATED[name], None, how, objects, least, shown,
                   stop("readings_differ", question=question), basis=basis)


def _merge_named(*dicts) -> dict | None:
    """The named readings of a combination, or None if two parts answer the same question differently (a
    combination that can't happen: one answer holds for the whole design)."""
    out = {}
    for d in dicts:
        for k, v in (d or {}).items():
            if out.setdefault(k, v) != v:
                return None
    return out


# ---- the lot ---------------------------------------------------------------------------------------------

def _angle(a, b) -> float:
    """Angle in degrees (0-90) between two directions, ignoring which way each points."""
    (ax, ay), (bx, by) = a, b
    na, nb = math.hypot(ax, ay), math.hypot(bx, by)
    return math.degrees(math.acos(min(1.0, abs(ax * bx + ay * by) / (na * nb))))


def _chord(points):
    return (points[-1][0] - points[0][0], points[-1][1] - points[0][1])


def _same_point(p, q) -> bool:
    return math.dist(p[:2], q[:2]) <= TOL


OUTLINE_SURVEY = 0.01     # ft: a surveyed outline is read as drawn, its lines in line and of no length merged
OUTLINE_TAX_MAP = 0.25    # ft: a tax-map outline is cleaned within this (inside its 2 ft per line)


class Lot:
    """The lot outline, its edges in order, and which edges are on the street."""

    def __init__(self, site: dict, facts: dict):
        lot = site["lot"]
        self.id = lot["id"]
        self.edges = [[tuple(p[:2]) for p in e["points"]] for e in lot["edges"]]
        self.curved = [bool(e.get("curved")) for e in lot["edges"]]
        n = len(self.edges)
        ring = [p for e in self.edges for p in e[:-1]]
        self.polygon = Polygon(ring)
        self.problems = []
        if n < 3 or any(not _same_point(self.edges[i][-1], self.edges[(i + 1) % n][0]) for i in range(n)):
            self.problems.append(stop("lot_not_a_loop"))
        elif not self.polygon.is_valid or self.polygon.area <= 0:
            self.problems.append(stop("lot_crosses_itself", why=explain_validity(self.polygon)))
        street = [i for i, e in enumerate(self.edges)
                  if any(_same_point(e[0], a) and _same_point(e[-1], b) or _same_point(e[0], b) and _same_point(e[-1], a)
                         for a, b in facts.get("street_line") or [])]
        self.street = street
        self.street_problem = None
        if not facts.get("street_line"):
            self.street_problem = stop("no_street")
        elif len(street) != len(facts["street_line"]):
            self.street_problem = stop("street_not_a_lot_line")
        elif not self._contiguous(street):
            self.street_problem = stop("street_lines_apart")
        elif len(street) == n:
            self.street_problem = stop("all_street")
        elif facts.get("corner_lot") is not True:
            # lot width is frontage on ONE public right-of-way (§325-8, Column 7: street_lines): street lines on two
            # streets, or of no known street swinging more than TURN_LIMIT_DEG in all (a corner, even rounded into
            # short pieces), are never measured along both (review rounds 5 and 6, P0); a street that bends is
            # asked about, never called two
            ids = facts.get("street_ids")
            stale = ids is not None and matching_ids(facts["street_line"], ids) is None
            # names that don't match the lines (saved before the lines changed): set aside, never used, and said
            # (review round 7, P1: they made the whole check fail)
            verdict, turn = ("stale", None) if stale else self.street_verdict(facts)
            if verdict == "stale":
                self.street_problem = stop("street_names_stale")
            elif verdict == "two":
                self.street_problem = stop("two_streets")
            elif verdict == "unsure":
                self.street_problem = stop("one_street_or_two", turn=round(turn or 0))
        # the outline cleaned within its accuracy (PR 18) only after every street check above, which reads the
        # lines as drawn (street_ids are matched to them end to end); a lot with a problem is never cleaned
        self.outline_note = None
        self.drawn, self.pieces = self.edges, None
        if not self.problems and not self.street_problem:
            self._simplify(OUTLINE_SURVEY if facts.get("lot_surveyed") else OUTLINE_TAX_MAP,
                           "survey" if facts.get("lot_surveyed") else "tax-map")

    def _simplify(self, tol: float, kind: str):
        """The lot lines read from the outline cleaned within its own accuracy (decided 2026-10-21): a vertex goes
        when taking it out moves the outline by no more than `tol` (0.01 ft on a survey: lines in line, lines of
        no length; 0.25 ft on the tax map, far inside the 2 ft per line every verdict already tries both ways).
        A vertex where the street meets the other lines, or at a curved line, always stays. The data is cleaned,
        never the law: every reading the lines left allow is still read. The lot's area stays the outline drawn."""
        n = len(self.edges)
        street = set(self.street)
        pts = [self.edges[i][0] for i in range(n)]
        keep = [i for i in range(n) if self.curved[i] or self.curved[i - 1] or ((i in street) != ((i - 1) % n in street))]
        alive = list(range(n))

        def cost(k):                    # removing alive[k]: how far the outline moves (every vertex it spans)
            m = len(alive)
            a_, b_ = alive[k - 1], alive[(k + 1) % m]
            chord = LineString([pts[a_], pts[b_]])
            span = []
            j = (a_ + 1) % n
            while j != b_:
                span.append(j)
                j = (j + 1) % n
            return max(chord.distance(Point(pts[j])) for j in span)

        while len(alive) > 3:
            best = min(((cost(k), k) for k in range(len(alive)) if alive[k] not in keep), default=None)
            if best is None or best[0] > tol:
                break
            alive.pop(best[1])
        if len(alive) == n:
            return
        old = n
        edges, curved, new_street, pieces = [], [], [], []
        for k, i in enumerate(alive):
            j = alive[(k + 1) % len(alive)]
            run = [(i + t) % n for t in range(((j - i) % n) or n)]
            # the line is the DRAWN pieces it groups, run end to end: the cleaned outline only decides which pieces
            # form one lot line (street, side, rear; the readings); every distance is to the pieces drawn, never
            # to a chord across them (review round 20: a chord over a dent moved the line outward)
            edges.append([q for r in run for q in (self.edges[r] if r == run[0] else self.edges[r][1:])])
            curved.append(any(self.curved[r] for r in run))
            pieces.append(run)
            if all(r in street for r in run):
                new_street.append(k)
        self.drawn, self.pieces = self.edges, pieces
        self.edges, self.curved, self.street = edges, curved, new_street
        self.outline_note = (f"{kind} outline cleaned within {tol:g} ft: its {old} drawn lines read as {len(edges)} "
                             f"lot lines (distances still to the lines drawn)")

    def label(self, i: int) -> str:
        """Lot line i in the architect's own numbering (the lines drawn): "9", or "9 to 11" for pieces read as one."""
        run = self.pieces[i] if self.pieces else [i]
        return str(run[0] + 1) if len(run) == 1 else f"{run[0] + 1} to {run[-1] + 1}"

    def line_of_piece(self, p: int) -> int:
        """The lot line a drawn piece is part of."""
        return next(k for k, run in enumerate(self.pieces) if p in run) if self.pieces else p

    def street_verdict(self, facts):
        """street_lines.street_verdict over the street lot lines in order along the street (each edge's own points:
        a curved edge's swing counts), each with the street the facts name it on (`street_ids`, one per
        `street_line`, None where unknown)."""
        n, s = len(self.edges), set(self.street)
        start = next(i for i in self.street if (i - 1) % n not in s)
        order = [(start + k) % n for k in range(len(self.street))]
        given, ids = facts.get("street_line") or [], facts.get("street_ids") or []

        def named(i):
            e = self.edges[i]
            for k, (a, b) in enumerate(given):
                if (_same_point(e[0], a) and _same_point(e[-1], b)) or (_same_point(e[0], b) and _same_point(e[-1], a)):
                    return ids[k] if k < len(ids) else None
            return None

        return street_verdict([self.edges[i] for i in order], [named(i) for i in order])

    def _contiguous(self, idx) -> bool:
        n = len(self.edges)
        s = set(idx)
        return sum(1 for i in s if (i + 1) % n not in s) == 1 or len(s) == n

    def line(self, idx) -> MultiLineString:
        return MultiLineString([LineString(self.edges[i]) for i in idx])

    def length(self, idx) -> float:
        return sum(LineString(self.edges[i]).length for i in idx)

    def ordered_street(self) -> list[int]:
        n, s = len(self.edges), set(self.street)
        start = next(i for i in self.street if (i - 1) % n not in s)
        return [(start + k) % n for k in range(len(self.street))]

    def readings(self):
        """Every way to read which lot lines are side lines and which are rear lines: a list of
        (description, left side edges, right side edges, rear edges), or None when there are too many to list.

        Every reading the geometry allows, none pruned by angle (review round 8): walking out from each end of the
        street lines, the lines run on as that side lot line for one or more lines, and the rear lot line is what
        is left between the two sides. Excluded only where the law excludes it: a line touching the street is a
        side line, never the rear (so each side starts with the line at the street's end), and a reading with
        no rear line isn't one. More than MAX_UNCLEAR_EDGES lines that could be either: too many to list, so
        the measuring stops (needs review), never fewer readings silently."""
        n, chain = len(self.edges), self.ordered_street()
        rest = [(chain[-1] + k) % n for k in range(1, n - len(chain) + 1)]     # from the street's end, around
        if len(rest) - 2 > MAX_UNCLEAR_EDGES:          # the lines between the two lines at the street's ends
            return None
        found = []
        for k1 in range(1, len(rest)):
            for k2 in range(1, len(rest) - k1):
                right, left = rest[:k1], list(reversed(rest))[:k2]
                rear = rest[k1:len(rest) - k2]
                found.append((left, right, rear))
        middle = rest[1:-1]
        varies = [i for i in middle if len({i in r for _l, _r, r in found}) == 2]
        return [(", ".join(f"line {self.label(i)} as a {'rear' if i in rear else 'side'} lot line" for i in varies),
                 left, right, rear) for left, right, rear in found]


# ---- buildings -------------------------------------------------------------------------------------------

_PLAN_OF = {}         # id of a faces list -> (that list, its projection), for one measure() call


def _projection(building: dict):
    """The building seen from above: the union of its faces projected flat (vertical faces add nothing). Worked
    out once per solid and measure() call."""
    faces = building["faces"]
    held = _PLAN_OF.get(id(faces))
    if held is not None and held[0] is faces:
        return held[1]
    found = _projection_now(building)
    _PLAN_OF[id(faces)] = (faces, found)
    return found


def _projection_now(building: dict):
    parts = []
    for f in building["faces"]:
        shell = [tuple(p[:2]) for p in f["points"]]
        holes = [[tuple(p[:2]) for p in h] for h in f.get("holes") or []]
        poly = shapely.make_valid(Polygon(shell, holes)).buffer(0)
        if poly.area > 1e-9:
            parts.append(poly)
    return union(parts)


def union(parts):
    """The one union rule for plans (measuring, the plan drawn, the envelope): the shapes together, made valid;
    where faces meet at slivers too thin for the overlay (a rotated gable: stress F14), the same union with every
    point on a 1e-6 ft grid, far below anything measured (TOL is 0.01 ft). Always in one canonical form
    (shapely.normalize: each ring oriented one way, starting at its lowest point), so nothing derived from it
    depends on the order the outlines were drawn in (stress F16)."""
    parts = [p for p in parts if p is not None and not p.is_empty]
    if not parts:
        return Polygon()
    try:
        return shapely.normalize(ops.unary_union(parts).buffer(0))
    except shapely.errors.GEOSException:
        return shapely.normalize(shapely.union_all(parts, grid_size=1e-6).buffer(0))


def _at_ground(building: dict, buildings: list[dict], plan_level: float, points, grade_known: bool,
               home=None) -> object:
    """The solid read at the ground, decided per SOLID (#15 rounds 7-8). Resting on the ground: cut at the higher
    of its grade and its own bottom (a slab above grade on a slope is never cut below itself). Its grade: the grade
    plane for the main building and every solid joined to it (`home`, _grade_home); a separate building with spot
    grades of its own (a shed on lower ground) at its own §325-3 grade plane (_separate_grade; review rounds 9-10). Raised off it
    (a balcony): left out (Polygon()), so it counts only from above. Whether it rests: from ITS OWN ground
    (ground_for: the spot grades at its walls, never another building's) when there is any; else from the grade
    when the ground is known (flat); else, the ground not known, never from ground data but from the drawing
    (_raised_by_shape): a solid above the lowest one is not raised for that alone."""
    if not building.get("faces"):
        return Polygon()
    bottom = _bottom(building)
    others = [b for b in buildings if b is not building]
    ground = ground_for([building], points, others)[0] if points else None
    level = plan_level
    if ground:
        rests = bottom <= max(ground) + TOL
        level = _separate_grade(building, buildings, points, home)
        if level is None:
            level = plan_level if _is_home(building, home) else sum(ground) / len(ground)
    elif grade_known:
        rests = bottom <= plan_level + TOL
    else:
        rests = not _raised_by_shape(building, buildings)
    return _section(building, max(level, bottom) + TOL) if rests else Polygon()


def _raised_by_shape(building: dict, buildings: list[dict]) -> bool:
    """With the ground not known, whether the drawing itself shows a solid raised off the ground: it stands over
    another solid, or it overhangs (nothing under its footprint while a solid it touches rests lower: a balcony)."""
    plan, bottom = _projection(building), _bottom(building)
    others = [b for b in buildings if b is not building and b.get("faces")]
    under = [b for b in others if _projection(b).intersection(plan).area > TOL and _bottom(b) < bottom - TOL]
    if any(_extent(b)[1] <= bottom + TOL for b in under):
        return True                      # on top of another solid
    group = next((g for g in _connected(buildings) if any(b is building for b in g)), [building])
    lower = any(_bottom(b) < bottom - TOL for b in group if b is not building)
    return lower and not under


def _bottom(building: dict) -> float:
    """A building's lowest point."""
    return min(p[2] for f in building["faces"] for p in f["points"])


def _section(building: dict, z: float):
    """The building cut by a level plane at height z: the area inside its walls at that height."""
    lines = []
    for f in building["faces"]:
        for ring in [f["points"], *(f.get("holes") or [])]:
            hits = []
            for p, q in zip(ring, ring[1:] + ring[:1]):
                if (p[2] - z) * (q[2] - z) < 0:
                    t = (z - p[2]) / (q[2] - p[2])
                    hits.append((round(p[0] + t * (q[0] - p[0]), 9), round(p[1] + t * (q[1] - p[1]), 9)))  # faces meet
            if len(hits) >= 2:
                d = (hits[-1][0] - hits[0][0], hits[-1][1] - hits[0][1])
                hits.sort(key=lambda h: h[0] * d[0] + h[1] * d[1])
                lines += [LineString(hits[i:i + 2]) for i in range(0, len(hits) - 1, 2)]
    polys = list(ops.polygonize(ops.unary_union(lines))) if lines else []
    return union(polys)                 # canonical, whichever way the faces run (stress F16)


def _normal_z(points) -> float:
    """The up-down part of a flat face's direction (0 = a wall, 1 = level), by Newell's method."""
    nx = ny = nz = 0.0
    for p, q in zip(points, points[1:] + points[:1]):
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    n = math.sqrt(nx * nx + ny * ny + nz * nz)
    return abs(nz) / n if n else 0.0


PITCHED = ("which eave the average height of a pitched roof is taken from (the lowest eave, the wall plate or the "
           "drip edge) is an open question for the architects (height_of_building)")
EAVES = ("lowest_eave", "wall_plate", "drip_edge")          # height_of_building's open question, by reading id
EAVE_WORDS = {"lowest_eave": "the underside of the lowest eave", "wall_plate": "the top of the wall plate",
              "drip_edge": "the roof edge, or drip line"}
ROOF_KIND = ("whether a roof with both a level part and sloped sides at its top is a mansard roof (to its highest "
             "level) or a pitched or hip roof (to its average height) is an open question for the architects")
ABOVE_ROOF = ("something rises above the main roof (a parapet, chimney, bulkhead or a higher part of the "
              "building): whether it counts in the height (§325-3 leaves out bulkheads, chimneys and similar "
              "constructions) is an open question for the architects")
ACCESSORY = ("whether another solid is part of the building or an accessory building (§325-25) is an open question "
             "for the architects")


def _plane_z(face: dict, x: float, y: float):
    """The height of a flat face at (x, y), or None for a wall."""
    pts = face["points"]
    nx = ny = nz = 0.0
    for p, q in zip(pts, pts[1:] + pts[:1]):
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    if abs(nz) < 1e-12:
        return None
    x0, y0, z0 = pts[0]
    return z0 - (nx * (x - x0) + ny * (y - y0)) / nz


def _plan(face: dict):
    """A face seen from above, with its holes."""
    return Polygon([p[:2] for p in face["points"]], [[p[:2] for p in h] for h in face.get("holes") or []]).buffer(0)


def _samples(shape, n: int = 7) -> list:
    """Points spread over a shape (a grid inside it, and one point surely inside)."""
    x0, y0, x1, y1 = shape.bounds
    grid = [(x0 + (x1 - x0) * (i + 0.5) / n, y0 + (y1 - y0) * (j + 0.5) / n) for i in range(n) for j in range(n)]
    inside = shapely.contains_xy(shape, [x for x, _ in grid], [y for _, y in grid])      # all at once
    return [Point(x, y) for (x, y), yes in zip(grid, inside) if yes] + [shape.representative_point()]


def _unit_normal(points) -> tuple:
    nx = ny = nz = 0.0
    for p, q in zip(points, points[1:] + points[:1]):
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    n = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / n, ny / n, nz / n


_PLANES = {}         # the same faces (by identity) -> their plane groups, for one measure() call


def _planes(faces: list[dict], work: dict | None = None) -> list[list[dict]]:
    """_planes_now, read once per set of faces and measure() call (the height and the eaves both ask). With
    `work` (the test that counts the grouping's work), always grouped afresh."""
    if work is not None:
        return _planes_now(faces, work)
    key = tuple(id(f) for f in faces)
    held = _PLANES.get(key)
    if held is None or any(a is not b for a, b in zip(held[0], faces)):
        held = (list(faces), _planes_now(faces))
        _PLANES[key] = held
    return held[1]


def _planes_now(faces: list[dict], work: dict | None = None) -> list[list[dict]]:
    """The faces grouped into planes. Each group's plane is fitted over every corner of every face in it (least
    squares), not taken from one face: a small triangle's own normal carries its corners' rounding noise (a
    single-precision mesh far from the origin: a tenth of a degree over a 1.4 ft triangle, 0.04 ft across a
    roof), and a plane fitted over the whole group doesn't. Faces that share an edge (two corners within TOL)
    join when every corner of the smaller group's faces lies within TOL of the larger group's plane, and every
    corner of the joined group lies within TOL of the plane fitted over it, so a group never drifts. So a roof
    drawn as many triangles (a mesh, with rounding noise) is one roof plane, two separate roofs at the same level
    stay two, and a curved roof isn't one plane. A distance, not an angle: the same tolerance as everywhere else.

    About n log n: a group keeps its corners' moments (count, sum, sum of outer products), so a joined plane is one
    3 x 3 fit; its corners as a list of blocks, the smaller group's appended to the larger's in place (union by
    size); and a bound on how far its corners can be from its plane (grown at each join by how far the plane
    moved, times the group's reach), so all of its corners are gathered and checked again only when that bound
    passes TOL (and then the exact distance replaces the bound). `work`, if given, counts the corner blocks moved
    and the corners gathered (for the test that keeps this about n log n)."""
    work = work if work is not None else {}
    work.setdefault("blocks_moved", 0)
    work.setdefault("corners_gathered", 0)
    area = [_plan(f).area for f in faces]
    parent = list(range(len(faces)))
    members = {i: [i] for i in range(len(faces))}
    size = {i: area[i] for i in range(len(faces))}
    origin = np.array(faces[0]["points"][0], dtype=float) if faces else np.zeros(3)
    chunks, moments, plane, reach, off = {}, {}, {}, {}, {}
    for i, f in enumerate(faces):
        pts = np.array(f["points"], dtype=float) - origin          # near the origin: no cancellation in the sums
        c = pts.mean(0)
        n = np.array(_unit_normal(f["points"]))
        chunks[i], moments[i] = [pts], (len(pts), pts.sum(0), pts.T @ pts)
        plane[i] = (n, c)
        reach[i] = float(np.linalg.norm(pts - c, axis=1).max())
        off[i] = float(np.abs((pts - c) @ n).max())               # a bound: how far a corner can be off the plane

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def near_plane(g, face):                # every corner of `face` within TOL of group g's plane
        n, c = plane[g]
        return all(abs(float(n @ (np.array(q, dtype=float) - origin - c))) <= TOL for q in face["points"])

    def join(big, small):                   # the joined group's plane, reach and bound; None if it would drift
        (k1, s1, q1), (k2, s2, q2) = moments[big], moments[small]
        k, total, outer = k1 + k2, s1 + s2, q1 + q2
        c = total / k
        n = np.linalg.eigh(outer / k - np.outer(c, c))[1][:, 0]
        nb, cb = plane[big]
        if n @ nb < 0:
            n = -n
        ps = np.concatenate(chunks[small])
        bound = max(off[big] + float(np.linalg.norm(n - nb)) * reach[big] + abs(float(n @ (cb - c))),
                    float(np.abs((ps - c) @ n).max()))
        far = max(reach[big] + float(np.linalg.norm(cb - c)), float(np.linalg.norm(ps - c, axis=1).max()))
        whole = None
        if bound > TOL:                     # the bound can't tell: every corner, exactly
            whole = np.concatenate(chunks[big] + chunks[small])
            work["corners_gathered"] += len(whole)
            bound = float(np.abs((whole - c) @ n).max())
            if bound > TOL:
                return None
            far = float(np.linalg.norm(whole - c, axis=1).max())
        return (k, total, outer), (n, c), far, bound, whole

    def cell(p):
        return tuple(math.floor(c / TOL) for c in p)

    cells = {}
    for i, f in enumerate(faces):
        for p in f["points"]:
            cells.setdefault(cell(p), []).append((i, p))
    for i, f in enumerate(faces):
        shared = {}
        for p in f["points"]:
            cx, cy, cz = cell(p)
            near = {j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
                    for j, q in cells.get((cx + dx, cy + dy, cz + dz), []) if j != i and math.dist(p, q) <= TOL}
            for j in near:
                shared[j] = shared.get(j, 0) + 1
        for j, count in shared.items():
            a, b = root(i), root(j)
            if count < 2 or a == b:
                continue
            big, small = (a, b) if size[a] >= size[b] else (b, a)
            if not all(near_plane(big, faces[k]) for k in members[small]):
                continue
            joined = join(big, small)
            if joined is None:              # some corner off the joined plane: it would drift
                continue
            moments[big], plane[big], reach[big], off[big], whole = joined
            if whole is not None:           # checked exactly: its corners, as one block from now on
                chunks[big] = [whole]
                chunks.pop(small)
            else:                           # in place: the smaller group's corners join the larger's list
                work["blocks_moved"] += len(chunks[small])
                chunks[big].extend(chunks.pop(small))
            parent[small] = big
            members[big] += members.pop(small)
            size[big] += size.pop(small)
            for d in (moments, plane, reach, off):
                d.pop(small)
    return [[faces[k] for k in group] for group in members.values()]


_SKY = {}            # id of a faces list -> (that list, its faces open to the sky), for one measure() call


def _roof_faces(building: dict) -> list[dict]:
    """The faces open to the sky, the building's own base left out (a floor at the bottom is never a roof, and
    can't cover anything above it, so it is left out before the sky is read: the same result, much faster on a
    meshed floor). Read once per solid and measure() call."""
    faces = building["faces"]
    held = _SKY.get(("roof", id(faces)))
    if held is not None and held[0] is faces:
        return held[1]
    bottom = min(p[2] for f in faces for p in f["points"])
    found = _open_to_the_sky([f for f in faces if not all(abs(p[2] - bottom) <= TOL for p in f["points"])])
    _SKY[("roof", id(faces))] = (faces, found)
    return found


def _open_to_the_sky(faces: list[dict]) -> list[dict]:
    """The faces of a solid that aren't wholly covered by the solid itself (read once per solid and measure() call:
    the height, the eaves and the yards all ask)."""
    held = _SKY.get(id(faces))
    if held is not None and held[0] is faces:
        return held[1]
    found = _open_to_the_sky_now(faces)
    _SKY[id(faces)] = (faces, found)
    return found


def _open_to_the_sky_now(faces: list[dict]) -> list[dict]:
    """The faces of a solid that aren't wholly covered by the solid itself: a face is open if at some point of it
    (holes left out) no other face lies above. Undersides (soffits, the floor of an upper storey that sticks out)
    and floors are covered; roofs, and a roof with a chimney through a hole in it, are not."""
    flat = [(f, _plan(f)) for f in faces if _normal_z(f["points"]) > 0.001]
    grown = [shape.buffer(TOL) for _, shape in flat]          # each outline grown once, and indexed
    index = STRtree(grown)
    open_ = []
    for i, (f, shape) in enumerate(flat):
        if shape.area <= 1e-9:
            continue
        points = _samples(shape)
        xy = shapely.get_coordinates(points)
        covered = set()
        # every (point, other face whose grown outline contains it) pair at once: the same test as contains
        for k, j in zip(*index.query(points, predicate="within")):
            if j != i and k not in covered:
                h = _plane_z(flat[j][0], xy[k][0], xy[k][1])
                z = _plane_z(f, xy[k][0], xy[k][1])
                if h is not None and h > z + TOL:
                    covered.add(k)
        if len(covered) < len(points):
            open_.append(f)
    return open_


def _height(building: dict, grade: float, facts: dict) -> dict:
    try:
        return _height_of(building, grade, facts)
    except _Stop as e:
        return _missing("building_height", str(e))


def _height_of(building: dict, grade: float, facts: dict) -> dict:
    """HEIGHT OF BUILDING: from the grade plane "to the highest level of a flat or mansard roof or to the average
    height of a pitched ... roof", using "that section of the roof that has the highest elevation". The roof is
    the faces open to the sky. If its largest roof plane seen from above (the main roof; a meshed roof's faces
    count together) doesn't reach the top, something smaller rises
    above it (a parapet, chimney, bulkhead or a higher part): the roof is read both without it and with it, each
    the same way, and whether it counts is an open question."""
    zs = [p[2] for f in building["faces"] for p in f["points"]]
    top = max(zs)
    bottom = min(zs)
    roof = _roof_faces(building)
    if not roof:
        return _missing("building_height", stop("no_roof"))
    how = "from the ground level (grade plane) to the top of the roof"
    # the main roof: the largest roof plane seen from above (its faces together, so a meshed roof counts whole)
    main_roof = _main_roof(_planes(roof))
    roof_top = max(p[2] for f in main_roof for p in f["points"])
    if roof_top >= top - TOL:
        readings, question, basis = _roof_readings(roof, top, grade, building, facts)
        return _decide("building_height", readings, how, _parts(building), question, basis)
    below = [f for f in roof if all(p[2] <= roof_top + TOL for p in f["points"])]
    low, low_question, low_basis = _roof_readings(below, roof_top, grade, building, facts)
    high, high_question, high_basis = _roof_readings(roof, top, grade, building, facts)
    readings = [(_both("leaving out what rises above the main roof", w), v, x) for w, v, x in low]
    readings += [(_both("including what rises above the main roof", w), v, x) for w, v, x in high]
    basis = list({b["id"]: b for b in low_basis + high_basis}.values())
    return _decide("building_height", readings, how, _parts(building),
                   "; ".join(dict.fromkeys(q for q in (ABOVE_ROOF, low_question, high_question) if q)), basis)


def _main_roof(groups: list[list[dict]]) -> list[dict]:
    """The main roof: the roof plane that shows the most from above (its plan less what any higher roof plane
    covers: a lower floor's top under the floor above shows only where that floor doesn't cover it), the higher
    of two that show the same (to 0.01 sf, so rounding in a rotated or reordered drawing never decides it)."""
    plans = [ops.unary_union([_plan(f) for f in g]) for g in groups]
    lows = [min(p[2] for f in g for p in f["points"]) for g in groups]
    highs = [max(p[2] for f in g for p in f["points"]) for g in groups]

    def shows(k):
        above = [plans[j] for j in range(len(groups)) if j != k and lows[j] > highs[k] + TOL]
        return plans[k].difference(ops.unary_union(above)).area if above else plans[k].area
    best = max(range(len(groups)), key=lambda k: (round(shows(k), 2), round(highs[k], 4)))
    return groups[best]


def _roof_readings(roof: list[dict], top: float, grade: float, building: dict, facts: dict) -> tuple[list, str, list]:
    """The readings of a roof whose highest point is `top`, the open question they leave ("" if none) and the
    findings applied. Its highest section is the faces that reach the top: all level (or within a drainage slope
    of level), a flat roof to its highest level; all sloped, a pitched roof; both, a mansard (to its highest
    level) or a pitched or hip roof with a deck or ridge strip.

    A pitched roof is measured midway between eave and ridge, on that highest section (the finding
    pitched_roof_midpoint, Gordium's reading). Which eave is still open (height_of_building's open question):
    each reading research lists is measured (_eaves), and named, so the checker can say complies only if every
    one passes. Where that section's eaves are at different heights, the wall plate and drip edge are read at
    the lowest and the highest of them (which one is the question's second half)."""
    # by plane, so a meshed roof is read like one drawn with whole faces
    highest = [g for g in _planes(roof) if any(abs(p[2] - top) <= TOL for f in g for p in f["points"])]
    sloped = [g for g in highest if _normal_z(g[0]["points"]) < FLAT]
    if not sloped:
        return [("a flat roof, to its highest level", top - grade, {})], "", []
    midpoint = law.finding(facts, "height_of_building", "pitched_roof_midpoint")
    which = law.question(facts, "height_of_building", EAVES)
    if midpoint is None or which["state"] == "missing":
        raise _Stop(stop("law_missing", what="the pitched-roof height (height_of_building: the midpoint finding and "
                                             "its open question, which eave)"))
    candidate = _eave_candidate(building, sloped)
    eaves = _eaves(building, sloped, candidate)
    # what the roof reaches past its walls is only a candidate eave: unless the architect confirmed it, every
    # reading is also taken with it NOT an eave (no eave construction, no wall plate inside it: the roof edge)
    open_eave = candidate["zone"] is not None and not _confirmed(facts, candidate)
    tag = f"{EAVE}:{building['id']}"         # each solid's overhang is its own question (a garage's and the house's)
    edge = min(eaves["drip_edge"])
    readings = []
    for rid in which["readings"]:
        if rid not in eaves:
            raise _Stop(stop("reading_unknown", reading=rid, entry="height_of_building"))
        zs = eaves[rid]
        named = {"named": {which["tag"]: rid, **({tag: "eave"} if open_eave else {})}}
        ends = [("", min(zs))] if max(zs) - min(zs) <= TOL else [
            (", the lowest of its eaves", min(zs)), (", the highest of its eaves", max(zs))]
        readings += [(f"pitched: midway between eave ({EAVE_WORDS[rid]}{end}) and ridge", (z + top) / 2 - grade, named)
                     for end, z in ends]
        if open_eave:
            readings.append((f"pitched: midway between the roof edge and ridge, what reaches past the walls not an "
                             f"eave ({EAVE_WORDS[rid]})", (edge + top) / 2 - grade,
                             {"named": {which["tag"]: rid, tag: "not_eave"}}))
    basis = [law.basis(midpoint)]
    if candidate["zone"] is not None and _confirmed(facts, candidate):
        basis.append(_eave_basis(_confirmed(facts, candidate)))
    eave_open = max(v for _, v, _ in readings) - min(v for _, v, _ in readings) > SAME    # the eave matters here
    pitched = _both(PITCHED, EAVE_QUESTION if open_eave else "") if eave_open else ""
    if len(sloped) < len(highest):            # a level part at the top too
        return ([("mansard: to its highest level", top - grade, {})] + readings, _both(ROOF_KIND, pitched), basis)
    return readings, pitched, basis


MAX_LEVELS = 64           # horizontal cuts at most, to find the building's outline under its roof


def _body(building: dict, z0: float, z1: float):
    """The building seen from above, below height z1 (its eaves left out): every horizontal cut of it between
    z0 and z1, taken just above and below each corner height (a cut only changes there) and midway between,
    joined. Exact for walls that stand straight up (a massing model); a sloping wall is cut at its ends."""
    corners = sorted({round(p[2], 4) for f in building["faces"] for p in f["points"] if z0 + TOL < p[2] < z1 - TOL})
    levels = {z0 + TOL, z1 - TOL} | {z + d for z in corners for d in (-TOL, TOL)}
    ends = sorted([z0 + TOL] + corners + [z1 - TOL])
    levels |= {(a + b) / 2 for a, b in zip(ends, ends[1:])}
    levels = sorted(z for z in levels if z0 < z < z1) or [(z0 + z1) / 2]
    if len(levels) > MAX_LEVELS:                # a finely meshed wall: evenly spread cuts, the ends kept
        step = (len(levels) - 1) / (MAX_LEVELS - 1)
        levels = [levels[round(k * step)] for k in range(MAX_LEVELS)]
    cuts = [c for c in (_section(building, z) for z in levels) if not c.is_empty]
    return ops.unary_union(cuts) if cuts else Polygon()


def _pitched_section(building: dict) -> list:
    """The plane groups of the main roof's highest section when it is pitched, else [] (the same roof _height
    reads: the faces open to the sky, the largest roof plane's top)."""
    zs = [p[2] for f in building["faces"] for p in f["points"]]
    if not zs:
        return []
    bottom = min(zs)
    roof = _roof_faces(building)
    if not roof:
        return []
    groups = _planes(roof)
    main_roof = _main_roof(groups)
    top = max(p[2] for f in main_roof for p in f["points"])
    return [g for g in groups if _normal_z(g[0]["points"]) < FLAT
            and any(abs(p[2] - top) <= TOL for f in g for p in f["points"])
            and all(p[2] <= top + TOL for f in g for p in f["points"])]


def _roof_part(building: dict, sloped: list) -> tuple | None:
    """(walls, base, faces) when the pitched section is drawn as its own solid standing on the building (a roof
    solid on the floor blocks, joined by _stacks): the plan of the parts right under it, the height it stands
    at, and its own faces. Then its eaves are exactly what of it reaches past those walls. None when the roof is
    one solid with the walls (an overhang then can't be told from an upper floor)."""
    parts = building.get("part_faces")
    if not parts or not sloped:
        return None
    mine = {id(f) for g in sloped for f in g}
    k = next((i for i, faces in enumerate(parts) if mine <= {id(f) for f in faces}), None)
    if k is None or building["floor"][k]:                 # a Gordium floor block is a story, never a roof
        return None
    base = building["spans"][k][0]
    under = [building["plans"][i] for i, (_lo, hi) in enumerate(building["spans"]) if i != k and abs(hi - base) <= TOL]
    return (ops.unary_union(under), base, parts[k], k) if under else None


EAVE = "model#eave"        # whether what a pitched roof reaches past its walls is an eave: eave / not_eave
PROJ = "model#projection"  # whether what sticks out past the walls at the ground is a projection: projection / part


def _eave_candidate(building: dict, sloped: list | None = None) -> dict | None:
    """What MIGHT be eaves: the geometry only suggests, it never decides (an overhang can't be told from a story,
    a mansard, a gable volume or a knee wall by its shape alone). The one helper the height, the yards and the
    coverage all use. {"walls": the plan of the walls under the pitched roof, "faces": the roof solid's own faces
    (None for a roof drawn in one solid with the walls), "zone": what of the roof reaches past those walls (None
    if nothing), "overhang": its fingerprint (where it is and how big), which an architect's confirmation names}.
    None for a flat roof.

    The walls: for a pitched roof drawn as its own solid standing on the building, the parts it stands on; for a
    roof drawn in one solid with the walls, the building below the roof's lowest edge. The zone leaves out what
    any other part covers (a story or tower beside the roof stays building, never a candidate)."""
    sloped = _pitched_section(building) if sloped is None else sloped
    if not sloped:
        return None
    part = _roof_part(building, sloped)
    if part:
        walls, _base, faces, k = part
        reach = _projection({"faces": faces})
        others = [p for i, p in enumerate(building["plans"]) if i != k]
        makers = [(building["parts"][k], faces)]          # the solid whose faces make the overhang
    else:
        bottom = min(p[2] for f in building["faces"] for p in f["points"])
        edge = min(p[2] for g in sloped for f in g for p in f["points"])
        walls, faces, others = _body(building, bottom, edge), None, []
        reach = ops.unary_union([_plan(f) for g in sloped for f in g])
        makers = list(zip(building.get("parts") or [building["id"]], building.get("part_faces") or [building["faces"]]))
    # what reaches past the walls and past every other part, in ONE overlay: subtracting the other parts after
    # the walls cut along nearly the same edges twice, and GEOS then dropped one whole eave strip, or kept it, by
    # the order the outlines were drawn in (stress F16: 1,420 sf for 1,400)
    zone = reach.difference(union([walls, *others]).buffer(TOL))
    if zone.area <= 1e-6:
        return {"walls": walls, "faces": faces, "zone": None, "overhang": None}
    return {"walls": walls, "faces": faces, "zone": zone, "overhang": _fingerprint(makers, zone)}


def _fingerprint(makers: list, zone) -> str:
    """What an eave confirmation names: a sha256 over (a) the ids of the solids whose faces make the overhang,
    (b) every vertex of those solids, to 0.01 ft, and (c) the overhang's own outline, to 0.01 ft. Any edit to those
    solids (a deeper fascia, a knee wall, a moved ridge, another solid swapped in with the same shape) gives a
    new one, so the question is asked again; the same model gives the same one."""
    def r(v):
        return f"{round(v, 2) + 0.0:.2f}"
    text = []
    for solid_id, faces in makers:
        text.append("solid " + str(solid_id))
        text += [" ".join(r(c) for p in f["points"] for c in p) for f in faces]
    for poly in getattr(shapely.normalize(zone), "geoms", [shapely.normalize(zone)]):   # the same ring, any order
        if poly.geom_type == "Polygon":
            text.append("zone " + " ".join(r(c) for x, y in poly.exterior.coords for c in (x, y)))
    return "eave:" + hashlib.sha256("\n".join(text).encode("utf-8")).hexdigest()[:24]


def _confirmed(facts: dict, candidate: dict | None) -> dict | None:
    """The confirmation that this very overhang is eaves (`eaves_confirmed`, naming its fingerprint), or None. The
    fingerprint (_fingerprint) covers the solids that make the overhang, every vertex of them and the overhang's
    outline: any edit to them asks again; a confirmation never carries over to a different overhang."""
    if not candidate or not candidate["overhang"]:
        return None
    return next((c for c in facts.get("eaves_confirmed") or []
                 if isinstance(c, dict) and c.get("overhang") == candidate["overhang"] and c.get("value") is True), None)


def _eaves(building: dict, sloped: list[list[dict]], candidate: dict) -> dict:
    """Each eave reading of a pitched roof section, as the heights of its eaves (one per roof plane), for the
    overhang read AS eaves (whether it is, is _eave_candidate's question, never decided here):
    - drip_edge: the roof edge, or drip line: the lowest point of each roof plane's surface;
    - wall_plate: the top of the wall plate: where each roof plane passes over the outside face of the walls
      under it (the roof surface there: a roof drawn with thickness is read at its top, the higher, cautious way);
    - lowest_eave: the underside of the lowest eave: the lowest point of the roof beyond the walls under it (its
      soffit, the bottom of its fascia), or, with no overhang, the roof edge itself."""
    walls, faces = candidate["walls"], candidate["faces"]
    grown = walls.buffer(TOL)
    drip, plate, under = [], [], []
    for g in sloped:
        plan = ops.unary_union([_plan(f) for f in g])
        low = min(p[2] for f in g for p in f["points"])
        drip.append(low)
        if plan.intersection(walls).area <= 1e-6:     # a roof plane over no wall (all overhang): no plate of its own
            continue
        heights = []                                 # each face at the corners of its part over the walls (a meshed
        for f in g:                                  # roof: each triangle on its own plane, no rounding drift)
            inside = _plan(f).intersection(walls)
            if inside.area > 1e-9:
                heights += [_plane_z(f, x, y) for poly in getattr(inside, "geoms", [inside])
                            if poly.geom_type == "Polygon" for ring in [poly.exterior, *poly.interiors]
                            for x, y in ring.coords]
        plate.append(min(h for h in heights if h is not None))
        reach = plan.buffer(TOL)
        beyond = [p[2] for f in (faces or building["faces"]) for p in f["points"]
                  if reach.contains(Point(p[0], p[1])) and not grown.contains(Point(p[0], p[1]))]
        under.append(min(beyond + [low]) if plan.difference(grown).area > 1e-6 else low)
    if not plate:
        raise _Stop(stop("eave_unclear"))
    return {"drip_edge": drip, "wall_plate": plate, "lowest_eave": [min(under)]}


# A plain part standing on the ground and lower than this fits inside the first story every building has, so it
# can't add one: the lowest ceiling a habitable room may have (7 ft, NYS Residential Code R305.1). A porch slab,
# steps or a deck. §325-3's STORY has no least height, so anywhere else (raised, on a roof, below the ground) a
# part of any height might be a story.
STORY_ROOM = 7.0            # ft
ROOM_AREA = 70.0            # sf: the least floor area of a habitable room (NYS Residential Code R304.1)
# With no main building picked and exactly one starting house, it is the main building, assumed (a marker on
# every measurement made from it: "main_assumed"); every other building that could be a principal one (enclosed,
# at least STORY_ROOM tall, at least ROOM_AREA: R305.1, R304.1) is also read as if it were the main one.
MAIN_IF = "if {} were the main building"
MAIN_QUESTION = ("which building is the main building (the starting house is assumed, not picked) is a question "
                 "(main_building)")
MAX_COMBINATIONS = 200      # more combinations of roof readings than this: too many to list; left for review


OWN_KINDS = ("main_only", "with_others")    # the main building's own candidates (as_main: another's)


def _with_others(candidates: list[dict], names: list[str]) -> dict:
    """The main building's height read over the candidate buildings (_assemblies, the same list the stories are
    read over: the main building with the solids touching it, §325-18A, and, with solids standing apart, with every
    other solid as part of it: an accessory building may have its own limit, §325-25). `candidates` are those
    labelled records (kinds main_only and with_others, looked up by kind, never by position), each with `height`,
    the main building's height, and `part_heights`, each other solid's height or None when it isn't one of its
    parts, every height measured from that candidate's own grade plane (§325-3: the ground on each side of THAT
    building; review round 18: a detached garage's ground never moves the house's). `names` are the other solids'
    ids. Every combination of each roof's own readings is listed. A question is named only if two readings that
    differ in that answer alone have different values: each solid's roof question on its own, and the accessory
    question."""
    own = [c for c in candidates if c["kind"] in OWN_KINDS]
    unread = [h for c in own for h in c["part_heights"] if h is not None and h["value"] is None and not h["readings"]]
    if unread:                          # never dropped: it could be the tallest part
        return _missing("building_height", stop("other_height", reason=unread[0]["reason"]))

    def values(m):
        return [(r["reading"], r["value"], r.get("named") or {}) for r in m["readings"]] or [("", m["value"], {})]

    sizes = [len(values(c["height"])) * math.prod(len(values(h)) for h in c["part_heights"] if h is not None)
             for c in own]
    if sum(sizes) > MAX_COMBINATIONS:
        return _missing("building_height", stop("too_many_roofs"))
    combos = []
    for k, c in enumerate(own):
        theirs = [values(h) if h is not None else [(None, None, {})] for h in c["part_heights"]]
        for w, v, n in values(c["height"]):      # one answer to each open question holds for every solid: never mixed
            for picks in itertools.product(*theirs):
                named = _merge_named(n, *(pn for _, _, pn in picks))
                if named is not None:
                    combos.append(((w, k) + tuple(lbl for lbl, _, _ in picks),
                                   max([v] + [x for _, x, _ in picks if x is not None]), named))

    def matters(i):
        same = [k for k in range(len(combos[0][0])) if k != i and not (i == 1 and k >= 2)]
        return any(a[1] != b[1] and a[0][i] != b[0][i] and all(a[0][k] == b[0][k] for k in same)
                   for a in combos for b in combos)

    def roof_questions(m):
        return [q for q in (ROOF_KIND, PITCHED, ABOVE_ROOF) if m and m["reason"] and q in m["reason"]]

    main = _kind(own, "main_only")["height"]
    questions = roof_questions(main) if matters(0) else []
    questions += [ACCESSORY] if matters(1) else []
    for j in range(len(names)):
        part = next((c["part_heights"][j] for c in own if c["part_heights"][j] is not None), None)
        questions += roof_questions(part) if matters(2 + j) else []
    readings = []
    for choice, v, named in combos:
        words = own[choice[1]]["words"] + "".join(f"; {n}: {lbl}" for n, lbl in zip(names, choice[2:]) if lbl)
        readings.append((_both(choice[0], words), v, {"named": named} if named else {}))
    records = [c["height"] for c in own] + [h for c in own for h in c["part_heights"] if h is not None]
    basis = list({b["id"]: b for m in records for b in m.get("basis") or []}.values())
    return _decide("building_height", readings, main["how"], main["objects"] + names,
                   "; ".join(dict.fromkeys(questions)), basis)


def _parts(building: dict) -> list[str]:
    """A building's objects: its own id, or every floor block of a stacked building."""
    return building.get("parts") or [building["id"]]


def _is_floor(building: dict, spans: dict) -> bool:
    """A floor block Gordium drew, still at the height it was drawn: only then is it one story. Stretched, scaled
    or merged with others, its height changes and it is a block like any other (a reading, never an override)."""
    drawn = building.get("floor")
    span = spans.get(building["id"])
    return drawn is not None and span is not None and abs((span[1] - span[0]) - drawn) <= TOL


def _stacks(buildings: list[dict]) -> list[dict]:
    """Solids stacked floor on floor (each standing on the one below it, overlapping it seen from above) joined
    into one building: its faces together, its parts listed (`parts`, bottom first) with their spans. A solid
    that stands alone stays as it is."""
    spans = {b["id"]: (min(p[2] for f in b["faces"] for p in f["points"]),
                       max(p[2] for f in b["faces"] for p in f["points"])) for b in buildings if b.get("faces")}
    plans = {i: _projection(b) for i, b in ((b["id"], b) for b in buildings) if i in spans}
    parent = {b["id"]: b["id"] for b in buildings}

    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i

    for a in spans:
        for b in spans:
            if a != b and abs(spans[a][1] - spans[b][0]) <= TOL and plans[a].intersection(plans[b]).area > 1e-6:
                parent[root(b)] = root(a)
    groups = {}
    for b in buildings:
        groups.setdefault(root(b["id"]), []).append(b)
    out = []
    for members in groups.values():
        if len(members) == 1 and not _is_floor(members[0], spans):    # one solid, not a Gordium floor block
            out.append(members[0])
            continue
        members.sort(key=lambda b: spans[b["id"]][0])
        out.append({"id": members[0]["id"], "parts": [b["id"] for b in members],
                    "spans": [spans[b["id"]] for b in members], "plans": [plans[b["id"]] for b in members],
                    "floor": [_is_floor(b, spans) for b in members],
                    "faces": [f for b in members for f in b["faces"]],
                    "part_faces": [b["faces"] for b in members],     # the same face objects, by part
                    "problems": [p for b in members for p in b.get("problems") or []]})
    return out


def _stories(building: dict, grade, why_grade, stated) -> dict:
    """STORY, read from the shape: the floor blocks Gordium drew (each marked as one story) standing on or above the
    ground, counted. Any other way of counting is a reading, never an override: a block that isn't one of Gordium's
    floors (a podium, a bulkhead, a roof solid: its stories can't be told from its height) and the count the
    architect typed. If the readings disagree, it's a question. A block below the ground is a basement or cellar,
    whether it counts as a story (§325-3) isn't measured yet."""
    how = "the floor blocks of the building counted (each story drawn as its own solid by Gordium)"
    floors = [i for i, f in enumerate(building["floor"]) if f]
    if not floors:                      # nobody marked these as one story each: the typed count, or ask
        readings = [("as stated by the architect", stated, {})] if stated is not None else []
        readings += [("every stacked block a story", len(building["parts"]), {})] if readings else []
        if not readings:
            return _record("stories", "count", reason=stop("no_stories"))
        return _decide("stories", readings, "stated by the architect (not measured from the model)", building["parts"],
                       "the stacked blocks aren't Gordium's floor blocks, so how many stories they hold can't be told "
                       "from the model; the count typed and the blocks disagree (story)")
    if why_grade:
        return _record("stories", "count", reason=why_grade)
    if any(lo < grade - TOL for lo, _ in building["spans"]):
        return _record("stories", "count", reason=stop("basement_story"))
    plans = [building["plans"][i] for i in floors]
    if any(plans[i].difference(plans[i - 1].buffer(TOL)).area > 1e-6 for i in range(1, len(plans))):
        return _record("stories", "count", reason=stop("floors_misaligned"))
    readings = [("Gordium's floor blocks", len(floors), {})]
    if len(floors) < len(building["parts"]):    # something else stacked on them (a bulkhead, a penthouse)
        readings.append(("every stacked block a story", len(building["parts"]), {}))
    if stated is not None:
        readings.append(("as stated by the architect", stated, {}))
    return _decide("stories", readings, how, building["parts"],
                   "whether a block that isn't one of Gordium's floors (a bulkhead, a penthouse) is a story, or the "
                   "count typed, disagrees with the floors drawn: a question (story)")


def _extent(building: dict) -> tuple:
    """The bottom and top of a building's solids (None, None if it has no faces)."""
    zs = [p[2] for f in building.get("faces") or [] for p in f["points"]]
    return (min(zs), max(zs)) if zs else (None, None)


def _rise(building: dict) -> float:
    """How tall a building's solids are, bottom to top (0 if it has no faces)."""
    lo, hi = _extent(building)
    return hi - lo if lo is not None else 0.0


def _kind(candidates: list[dict], kind: str) -> dict | None:
    """The candidate building of one kind (main_only, with_others): looked up by its label, never by position."""
    return next((c for c in candidates if c["kind"] == kind), None)


def _could_be_principal(b: dict) -> bool:
    """Whether a solid could be a principal building (and so the main one): enclosed, at least STORY_ROOM tall, and
    large enough to hold a habitable room (70 sf, NYS Residential Code R304.1). A deck or porch slab, a balcony, a
    chimney or a small shed can't."""
    return bool(b.get("faces")) and not b.get("problems") and _rise(b) >= STORY_ROOM - TOL and \
        _projection(b).area >= ROOM_AREA - TOL


def _assemblies(main: dict, others: list[dict], assumed: bool = False) -> list[dict]:
    """The candidate buildings every building measurement read from the drawing is read over (the height,
    _with_others; the stories, _stories_over), each a labelled record {kind, words, members} looked up by kind
    everywhere (_kind), never by position:
    main_only, the main building as one building: itself with every solid touching it (§325-18A: a wing, a porch
    or an attached garage drawn as its own solid is part of it), the main building first among its members;
    with_others, with solids standing apart, the main building with every other solid as part of it too (one
    standing apart may be an accessory building, §325-25: the accessory question);
    as_main (with `of`, the building's id), with the main building assumed (pick_main), each other building alone,
    as if it were the main one (the pick the architect may make: never a pass that pick wouldn't). Only a building
    that could be a principal one (_could_be_principal) is read as the main one."""
    drawn = [main] + list(others)
    joined = _attached(main, drawn) if all(b.get("faces") for b in drawn) else []
    out = [{"kind": "main_only", "members": [main] + joined,
            "words": "the main building only" if not joined else
            "the main building and the solids touching it (§325-18A)"}]
    if len(joined) < len(others):       # solids standing apart: the accessory question
        out.append({"kind": "with_others", "words": "with every other solid as part of it",
                    "members": [main] + list(others)})
    if assumed:
        out += [{"kind": "as_main", "of": _parts(b)[0], "words": MAIN_IF.format(_parts(b)[0]), "members": [b]}
                for b in others if _could_be_principal(b)]
    return out


def _with_each_as_main(record: dict, candidates: list[dict], facts: dict) -> dict:
    """The height read with each other building as the main one (the as_main candidates), each from its own
    grade plane, beside the readings already found; the main-building question if they differ. A height that
    couldn't be read at all (its own stop) stays as it is: nothing to add to."""
    extra = [c for c in candidates if c["kind"] == "as_main"]
    if not extra or (record["value"] is None and not record["readings"]):
        return record
    readings = [(r["reading"], r["value"], {}) for r in record["readings"]] or \
        [("the starting house as the main building", record["value"], {})]
    objects = list(record.get("objects") or [])
    for c in extra:
        (b,), words, g, why = c["members"], c["words"], c.get("grade"), c.get("why")
        h = _height(b, g, facts) if not why else _missing("building_height", why)
        if h["value"] is None and not h["readings"]:
            return _missing("building_height", h["reason"])
        readings += [(_both(words, r["reading"]), r["value"], {}) for r in h["readings"]] or [(words, h["value"], {})]
        objects += _parts(b)
    question = "; ".join(q for q in [record.get("reason") and record["reason"].split("; ", 1)[-1], MAIN_QUESTION] if q)
    return _decide("building_height", readings, record.get("how") or "", list(dict.fromkeys(objects)), question)


REFUSALS = ("below_floors", "above_drawn", "below_one")   # a count typed the drawing rules out: its stop is
# stories_<code>, and the record carries the code (stories_refused) so whoever asked rolls the count back by it,
# never by matching the words


def _refused(code: str, reason: str) -> dict:
    """The stories record for a count typed and refused: needs review with its reason, and the code."""
    assert code in REFUSALS
    return dict(_missing("stories", reason), stories_refused=code)


def _stories_whole(parts: list[dict], grade, why_grade, stated, called: str | None = None) -> dict:
    """STORY of one building made of parts (the main building first; with #18, the parts touching it, §325-18A),
    read from the drawing as far as it allows. Gordium's floor blocks are counted; a part drawn as a plain solid (or
    plain solids stacked) h tall holds at most floor(h / 7 ft) stories (the lowest habitable ceiling, R305.1), and
    every building holds at least a first story (§325-3). The building's least is the floors counted (or one), its
    most the most any part could hold: equal, it is read; between, it asks (the count entered stands only within
    them). A part below the ground is the §325-3 basement question; a plain part starting above the ground may be
    another story; parts one over another in plan with a real gap, or one sunk into another, are a question: each
    needs review whatever was typed. With only floor blocks, the most counted on any part, a count typed beside it
    (fewer is refused; more is a question). `called`: how the building is named in the words ("the building"),
    else by the part's id. Each reason says what is drawn."""
    ids = [i for b in parts for i in _parts(b)]
    if why_grade:
        return _missing("stories", why_grade)
    plain = [b for b in parts if not (b.get("parts") and any(b.get("floor") or []))]
    low = [b for b in plain if _extent(b)[0] is not None and _extent(b)[0] < grade - TOL]
    if low:
        return _missing("stories", stop("basement_part", what=", ".join(b["id"] for b in low)))
    # a plain part starting above the ground (beside the roof or over it, touching in plan or not) may be another
    # story: no seam in plan decides it, so the count typed stands only when every plain part starts at the ground
    raised = [b for b in plain if _extent(b)[0] is not None and _extent(b)[0] > grade + TOL]
    if raised:
        return _missing("stories", stop("part_raised", what=", ".join(b["id"] for b in raised)))
    floored = [b for b in parts if b not in plain]
    for kind, lower, upper in _apart_in_one_plan(parts):    # over a gap (a floor not drawn?), or partly inside
        if kind == "gap":
            return _missing("stories", stop("floors_apart", low=_r(_extent(lower)[1]), high=_r(_extent(upper)[0])))
        return _missing("stories", stop("parts_overlap", what=upper["id"], low=_r(_extent(upper)[0]),
                                        high=_r(_extent(lower)[1])))
    counts = []
    for stack in floored:
        got = _stories(stack, grade, None, None)
        if got["value"] is None:        # its own reason: a floor block below the ground, misaligned, a bulkhead
            return got
        counts.append(int(got["value"]))
    counted = max(counts) if counts else None
    if not plain:
        if stated is not None and stated < counted:     # fewer than the floors drawn: refused, never a reading
            return _refused("below_floors", stop("stories_below_floors", typed=f"{stated:g}", drawn=counted))
        readings = [("Gordium's floor blocks" + (", the most on any part" if len(counts) > 1 else ""), counted, {})]
        if stated is not None:
            readings.append(("as stated by the architect", stated, {}))
        return _decide("stories", readings, "the floor blocks of the building counted (each story drawn as its own "
                       "solid by Gordium)", ids, "the count typed disagrees with the floors drawn: a question (story)")
    # read from the drawing as far as it allows: a plain part h tall can hold at most floor(h / 7 ft) stories
    # (the lowest ceiling a habitable room may have, R305.1), and holds at least one if it can hold one; the
    # building's least is the floors counted (or that one), its most the most any part could hold
    could = {b["id"]: math.floor((_rise(b) + TOL) / STORY_ROOM) for b in plain}
    tallest = max(plain, key=_rise)
    least = max([counted or 0, 1])      # every building has a first story (§325-3: from a floor to the roof)
    most = max([counted or 0, 1] + list(could.values()))
    name = called or tallest["id"]      # the building by name, never the main one's words for another solid
    holds = (f"{name}, {_r(_rise(tallest)):g} ft tall, could hold up to {could[tallest['id']]} "
             f"stor{'y' if could[tallest['id']] == 1 else 'ies'} (7 ft a story, R305.1)")
    if stated is not None:              # the architect's count for the whole building: only within what's drawn
        if counted is not None and stated < counted:
            return _refused("below_floors", stop("stories_below_floors", typed=f"{stated:g}", drawn=counted))
        if stated > most:
            return _refused("above_drawn", stop("stories_above_drawn", typed=f"{stated:g}", what=name,
                                            height=f"{_r(_rise(tallest)):g}", most=most))
        if stated < least:              # (no floor blocks drawn: fewer than the first story every building has)
            return _refused("below_one", stop("stories_below_one", typed=f"{stated:g}"))
        return _record("stories", "count", _r(stated), "stated by the architect for the whole building, within what "
                       f"the drawing allows ({least} to {most}: {holds})", ids)
    if least == most:                   # the drawing allows one count only: read, nothing to ask
        return _record("stories", "count", _r(least), f"read from the drawing: {holds}" +
                       (f"; {counted} floor blocks drawn" if counted else ""), ids)
    return _decide("stories", [(f"at least: {'the floor blocks drawn' if counted else 'one story'}", least, {}),
                               (f"at most: {holds}", most, {})],
                   "the stories the drawing allows (floor blocks counted; a plain solid at 7 ft a story, R305.1)", ids,
                   f"a {_r(_rise(tallest)):g} ft solid ({name}) could hold up to {could[tallest['id']]} "
                   "stories: draw its floors or enter the count (story)")


def _footprint(building: dict):
    """A building seen from above (a stack: its blocks' plans together)."""
    return ops.unary_union(building["plans"]) if building.get("plans") else _projection(building)


def _overlap_in_plan(a: dict, b: dict) -> bool:
    return _footprint(a).intersection(_footprint(b)).area > 1e-6


def _apart_in_one_plan(parts: list[dict]) -> list[tuple[str, dict, dict]]:
    """Parts of one building one over another in plan that don't stand on each other or side by side: each such
    pair ("gap" or "overlap", lower, upper). A gap: no overlap in height, more than TOL apart (a floor deleted, a
    block lifted, a room floating over the roof). An overlap: one starts partly inside the other (a floor moved
    down into the one below, a room sunk into the roof). Parts that touch (TOL), or start at one level (an
    L-shaped house), are neither. So moving a part a little never turns one count into another."""
    out = []
    for i, a in enumerate(parts):
        for b in parts[i + 1:]:
            (lo_a, hi_a), (lo_b, hi_b) = _extent(a), _extent(b)
            if None in (lo_a, lo_b) or not _overlap_in_plan(a, b):
                continue
            lower, upper = (a, b) if lo_a <= lo_b else (b, a)
            top, bottom = _extent(lower)[1], _extent(upper)[0]
            if bottom > top + TOL:
                out.append(("gap", lower, upper))
            elif abs(bottom - top) > TOL and abs(lo_a - lo_b) > TOL:
                out.append(("overlap", lower, upper))
    return out


def _one_vertical_building(parts: list[dict], everyone: list[dict]) -> list[dict]:
    """parts, with every solid drawn over or under one of them in plan (plain or floor blocks, touching or not):
    a building is everything one over another in plan, whatever the vertical gap (a tolerance never decides what
    the building is); whichever candidate building is read."""
    out = list(parts)
    grew = True
    while grew:
        grew = False
        for b in everyone:
            if not any(b is o for o in out) and b.get("faces") and \
                    any(p.get("faces") and _overlap_in_plan(p, b) for p in out):
                out.append(b)
                grew = True
    return out


def _fits_in_the_first_story(part: dict, grade) -> bool:
    """A plain part standing on the ground (its bottom at the grade) and lower than STORY_ROOM: it can't add a
    story. Not knowing the grade, or anything else (raised, on a roof, below the ground, stacked), it might."""
    lo, _ = _extent(part)
    return (not part.get("parts") and grade is not None and lo is not None and abs(lo - grade) <= TOL
            and _rise(part) < STORY_ROOM - TOL)


def _ground_against(solids: list[dict], grade, off_check: bool = True, points=None, pool=None,
                    home=None) -> str | None:
    """What is wrong with this ground level against these solids, or None: the ground must meet them, taken
    together (stacked floors, a basement or a tower drawn as its own solid sit above or below it), at or above their
    lowest point and below their top; and a solid wholly under the ground is a basement only if it is joined
    directly under the building. Checked for the whole site, and again for each candidate building at its own
    grade (_candidate_grades). With spot grades, whether the ground meets them is _floating's, at the footprint
    (off_check False): one test, whatever the spot grades' positions. Whether a solid is wholly under the ground:
    the grade's own building (`home`: the main building or the candidate, and every solid joined to it) against the
    grade, as its height and stories are; a separate building with spot grades of its own against its own ground
    (a shed on lower ground is never "under" the house's grade; review rounds 9-10). `pool`: every building on
    the lot (default: these solids)."""
    zs = [p[2] for b in solids for f in b.get("faces") or [] for p in f["points"]]
    lo, hi = (min(zs), max(zs)) if zs else (None, None)
    off = (lo, hi) if off_check and zs and grade is not None and (
        grade < lo - TOL or hi - lo > TOL and grade >= hi - TOL) else None
    # a solid wholly under the ground is a basement only if it is joined directly under the building: its top
    # meets the bottom of a solid above it (the building, or a basement already joined to it) and it lies within
    # that solid's plan. Any other (left at z = 0 when the rest was moved to a survey level, or a part left at its
    # old level) can't be told from a mistake, and its height (below zero) would drop out of every reading unseen.
    buried = None
    if grade is not None and not off:
        spans = {b["id"]: (min(p[2] for f in b["faces"] for p in f["points"]),
                           max(p[2] for f in b["faces"] for p in f["points"])) for b in solids if b.get("faces")}
        plans = {b["id"]: _projection(b) for b in solids if b["id"] in spans}
        level = {}                      # a separate building's own ground; the grade's own building: the grade
        for b in solids:
            if points and b["id"] in spans and not _is_home(b, home):
                own = _separate_grade(b, pool or solids, points, home)
                if own is None:             # its spot grades don't give a grade plane: its lowest ground there
                    ground, _ = ground_for([b], points, [x for x in (pool or solids) if x is not b])
                    own = min(ground) if ground else None
                level[b["id"]] = grade if own is None else own
        at = lambda i: level.get(i, grade)  # noqa: E731
        joined = {i for i, (lo_, hi_) in spans.items() if hi_ > at(i) + TOL or hi_ - lo_ <= TOL}   # above, or a slab
        waiting = [i for i in spans if i not in joined]
        while True:                     # from the top down: a sub-basement joins under a joined basement
            found = [i for i in waiting
                     if ops.unary_union([plans[j] for j in joined if abs(spans[j][0] - spans[i][1]) <= TOL])
                     .buffer(TOL).contains(plans[i])]
            if not found:
                break
            joined |= set(found)
            waiting = [i for i in waiting if i not in found]
        buried = (at(waiting[0]), *spans[waiting[0]]) if waiting else None
    if off:
        return stop("ground_off_building", ground=_r(grade), bottom=_r(off[0]), top=_r(off[1]))
    if buried:
        return stop("buried_solid", ground=_r(buried[0]), bottom=_r(buried[1]), top=_r(buried[2]))
    return None


def _candidate_grades(assemblies, buildings: list[dict], facts: dict, grade, why_grade) -> list[dict]:
    """Each candidate with its own grade plane added (grade, why), one per assembly (§325-3: "the average of
    finished ground level on each side of the building"). With one ground level given, or flat ground, it is the
    same for every candidate; from spot grades, the walls of that candidate's own solids, a point at another
    solid's walls being that solid's ground, never this one's. The main building alone keeps the grade found. A
    whole-site grade stop holds for every candidate; and each candidate's ground is checked against its own
    solids at its own grade (_ground_against: off them, or a solid buried under them)."""
    out = []
    main = _kind(assemblies, "main_only")["members"][0] if assemblies else None
    for c in assemblies:
        members = c["members"]
        if why_grade or not facts.get("grade_points") or (len(members) == 1 and members[0] is main):
            g, why = grade, why_grade               # (another building alone, as the main one: its own walls)
        else:
            rest = [b for b in buildings if not any(b is m for m in members)]
            g, why = _grade_from_points(members, facts["grade_points"], rest)
            why = stop("grade_with_others") if why else None
        spots = facts.get("grade_points")
        out.append(dict(c, grade=g, why=why or (_meets_ground(members, spots, buildings) if spots else None) or
                        (_ground_against(members, g, off_check=not spots, points=spots, pool=buildings,
                                         home=_joined_ids(members, buildings))
                         if g is not None else None)))
    return out


def _stories_over(assemblies, grade, why_grade, stated) -> dict:
    """STORY over the same candidate buildings as the height (_assemblies): each one's stories by the one rule
    (_stories_whole; its parts are the main building and every other part, with every solid over or under one
    of them in plan (_one_vertical_building), except a plain one standing on the
    ground and lower than STORY_ROOM, which fits inside the first story: a porch slab or steps. A part raised off
    the ground, on a roof or reaching below it stays in, whatever its height). A count that can't be read for any
    of them needs review with its reason; if they differ, it is the accessory question (and the main-building
    question with as_main candidates). Each candidate's own grade plane (_candidate_grades), the one the height
    reads; else `grade` for all."""
    found = []
    everyone = list({id(b): b for c in assemblies for b in c["members"]}.values())
    for c in assemblies:
        words, members = c["words"], c["members"]
        g, why_g = (c["grade"], c["why"]) if "grade" in c else (grade, why_grade)
        parts = _one_vertical_building(members, everyone)
        parts = parts[:1] + [b for b in parts[1:] if not _fits_in_the_first_story(b, g)]
        # the count typed is the main building's: another building read as the main one has only its own drawing
        r = _stories_whole(parts, g, why_g, None if c["kind"] == "as_main" else stated,
                           "the building" if c["kind"] == "main_only" and len(parts) == 1 else None)
        if r["value"] is None and not r["readings"]:
            return r
        found.append((words, r, c["kind"]))
    # whether a count entered could settle it: only if every candidate still open is one the count is for (never
    # another building read as the main one: pick the main building first)
    ranged = [kind for _, r, kind in found if r["value"] is None and "could hold up to" in (r["reason"] or "")]
    settles = bool(ranged) and "as_main" not in ranged
    if len(found) == 1:
        return dict(found[0][1], count_settles=settles)
    readings, questions, objects = [], [], []
    for words, r, _ in found:
        objects += r["objects"]
        if r["value"] is None:
            questions.append(r["reason"].split("; ", 1)[-1])
        for x in r["readings"] or [{"reading": r["how"], "value": r["value"]}]:
            readings.append((_both(words, x["reading"]), x["value"], {}))
    if len({max(x["value"] for x in r["readings"] or [r]) for _, r, _ in found}) > 1:
        questions.append(ACCESSORY)
        if any(kind == "as_main" for _, _, kind in found):
            questions.append(MAIN_QUESTION)
    return dict(_decide("stories", readings, "the stories of the building, read over its candidate buildings",
                        list(dict.fromkeys(objects)), "; ".join(dict.fromkeys(questions))), count_settles=settles)


# ---- measuring -------------------------------------------------------------------------------------------

def _both(*words) -> str:
    return "; ".join(w for w in words if w)


def _distance(line, shape):
    a, b = ops.nearest_points(line, shape)
    return line.distance(shape), [[_r(a.x), _r(a.y)], [_r(b.x), _r(b.y)]]


TAX_MAP_TOLERANCE = 2.0   # ft: a lot line from the tax map is taken as right to within this (spec C2)
# How far each lot measurement can be off on a tax-map lot, with every lot line up to TAX_MAP_TOLERANCE the unlucky
# way (Ben, 2026-10-21): a yard runs to one line; a lot width or depth runs between two. The one definition: the
# checker's worst case (design_checker.present) and the starting house (design_checker.check) read it from here.
TAX_MAP_SLACK = {"front_yard": TAX_MAP_TOLERANCE, "side_yard_smaller": TAX_MAP_TOLERANCE,
                 "side_yard_larger": TAX_MAP_TOLERANCE, "rear_yard": TAX_MAP_TOLERANCE,
                 "lot_width": 2 * TAX_MAP_TOLERANCE, "lot_depth": 2 * TAX_MAP_TOLERANCE,
                 # the same yards to the eaves, and an accessory building's distances: each to one line
                 **{name: TAX_MAP_TOLERANCE for name in ("front_yard_eaves", "side_yard_smaller_eaves",
                                                         "side_yard_larger_eaves", "rear_yard_eaves",
                                                         "accessory_front_yard", "accessory_side_yard",
                                                         "accessory_rear_yard")}}


def tax_map_lot_area(polygon) -> dict:
    """The smallest and largest lot area the tax map allows: every lot line moved TAX_MAP_TOLERANCE in, or out
    (73 x 90 -> 69 x 86 = 5,934 sf at the smallest). The one definition of the worst-case lot area."""
    return {"ft": TAX_MAP_TOLERANCE, "low": _r(polygon.buffer(-TAX_MAP_TOLERANCE, join_style=2).area),
            "high": _r(polygon.buffer(TAX_MAP_TOLERANCE, join_style=2).area)}
SPOT_REACH = 2.0     # ft: a spot grade this close to a wall (in plan) is the ground level at that wall


def _building_problems(buildings: list[dict]) -> str | None:
    """Why the buildings can't be measured at all, or None: none drawn; the reader's problems; two objects with
    one id; an object with no faces; one that encloses nothing (_unenclosed). THE refusal, for the measuring and
    for the envelope alike."""
    if not buildings:
        return stop("no_building")
    ids = [b["id"] for b in buildings]
    same = sorted({i for i in ids if ids.count(i) > 1}, key=str)
    return "; ".join([p for b in buildings for p in b.get("problems") or []]
                     + [stop("same_id", id=i) for i in same]
                     + ([stop("empty_building")] if any(not b.get("faces") and not b.get("problems")
                                                        for b in buildings) else [])
                     + list(dict.fromkeys(why for b in buildings if b.get("faces") and not b.get("problems")
                                          for why in [_unenclosed(b)] if why))) or None


def envelope_grade(buildings: list[dict], facts: dict) -> tuple:
    """(grade, None) or (None, reason): the grade plane the envelope may be drawn from, by the measuring's own
    refusals (THE same functions): buildings it can't measure, a grade plane it can't find, and buildings that
    don't meet the ground (_meets_ground)."""
    why = _building_problems(buildings) if buildings else None     # none yet: the spot grades alone
    if why:
        return None, why
    grade, why = grade_plane(buildings, facts)
    if why:
        return None, why
    stacked = _stacks(buildings)
    # the measuring's own ground test (the same two functions): meeting the ground, and no solid buried under it
    why = _meets_ground(stacked, facts["grade_points"], stacked) or \
        (_ground_against(buildings, grade, off_check=False, points=facts["grade_points"],
                         home=_grade_home(buildings, facts))
         if buildings and grade is not None else None)
    return (None, why) if why else (grade, None)


def _unenclosed(building: dict) -> str | None:
    """open_solid when a building object encloses no volume, read from its own faces (the reader also checks it;
    this never relies on that). Seen along each axis (from above, from the front, from the side), a closed solid's
    faces cover its outline there at least twice, once on each side: every face counts as it is drawn, so a wall a
    hair off plumb is never left out. Walls only or faces of no area (nothing seen from above), or a face missing
    (a wall: seen from the side, covered once), is open. A top missing over walls on a floor is left to no_roof,
    its own words."""
    faces = building["faces"]

    def seen(k):                        # along axis k: the faces' outlines there, and their area added up
        drop = [i for i in range(3) if i != k]
        shapes = []
        for f in faces:
            ring = [(p[drop[0]], p[drop[1]]) for p in f["points"]]
            holes = [[(p[drop[0]], p[drop[1]]) for p in h] for h in f.get("holes") or []]
            shapes.append(Polygon(ring, holes).buffer(0) if len(ring) >= 3 else Polygon())
        return sum(g.area for g in shapes), ops.unary_union(shapes).area if shapes else 0.0

    short = []
    for k in (2, 0, 1):
        total, outline = seen(k)
        if outline <= 1e-6:
            if k == 2:
                return stop("open_solid", what=_called(building))
            continue
        if total < 2 * outline * (1 - 1e-3):
            short.append(k)
    if not short:
        return None
    bottom = min(p[2] for f in faces for p in f["points"])
    level = [f for f in faces if abs(_normal_z(f["points"])) > 0.001]
    walls = len(level) < len(faces)
    if short == [2] and walls and all(all(abs(p[2] - bottom) <= TOL for p in f["points"]) for f in level):
        return None                     # walls on a floor, nothing over them: no_roof says so
    return stop("open_solid", what=_called(building))


def _called(building: dict) -> str:
    """An object as the architect finds it: its Rhino name, else its id (Zoom to finds it by id)."""
    return building.get("name") or building["id"]


def _open_ids(buildings: list[dict]) -> list:
    """The objects that aren't closed solids (the reader's word, or the measuring's own _unenclosed)."""
    shut = stop("open_solid", what="")
    return [b["id"] for b in buildings if any(str(p).startswith(shut) for p in b.get("problems") or [])
            or (b.get("faces") and not b.get("problems") and _unenclosed(b))]


def _joined_ids(members: list[dict], buildings: list[dict]) -> set:
    """The ids of these solids and every solid joined to them (_connected): one building for the ground."""
    ids = {i for m in members for i in _parts(m)}
    for g in _connected(buildings):
        if any(i in ids for b in g for i in _parts(b)):
            ids |= {i for b in g for i in _parts(b)}
    return ids


def _grade_home(buildings: list[dict], facts: dict) -> set | None:
    """The solids the grade plane is read for (grade_plane: pick_main's main building), with every solid joined to
    them: one building, read against that grade by every test (height, stories, buried, the cut). None: no main."""
    main, _ = pick_main(_stacks(buildings), facts)
    return _joined_ids([main], buildings) if main is not None else None


def _is_home(building: dict, home) -> bool:
    """Whether a solid belongs to the grade's own building (or there is no telling: then it does)."""
    return home is None or any(i in home for i in _parts(building))


def _separate_grade(building: dict, buildings: list[dict], points, home):
    """A separate building's own grade plane (§325-3, _grade_from_points over its joined group, from its own spot
    grades), or None: the grade's own building (the grade plane is its), no spot grades, or none to be found."""
    if not points or _is_home(building, home):
        return None
    group = next((g for g in _connected(buildings) if any(b is building for b in g)), [building])
    rest = [b for b in buildings if not any(b is x for x in group)]
    grade, why = _grade_from_points(group, points, rest)
    return None if why else grade


def _connected(buildings: list[dict]) -> list[list[dict]]:
    """The buildings as connected groups: touching in plan (a balcony or a wing against the house's side, within
    TOUCH: the same distance that makes a solid part of the main building for the yards, _touching; #18 review round
    25) or one over another (as _stacks and _one_vertical_building join them). One helper, for the ground test."""
    groups = []
    for b in buildings:
        plan = _footprint(b) if b.get("faces") or b.get("plans") else None
        joined = [g for g in groups if plan is not None and any(
            (o.get("faces") or o.get("plans")) and _footprint(o).distance(plan) <= TOUCH for o in g)]
        merged = [b] + [o for g in joined for o in g]
        groups = [g for g in groups if not any(g is j for j in joined)] + [merged]
    return groups


def _meets_ground(solids: list[dict], points: list, pool: list[dict]) -> str | None:
    """Whether each building group (_connected: touching in plan or one over another, so a balcony against the
    house's side is part of it, never a building floating on its own) meets the ground the spot grades describe at
    its own footprint (_floating), the points at another group's walls being that group's ground: one plane per
    building, so a terraced lot is never one plane misfitted across it. A raised part inside a group is the
    stories' own question (part_raised). The first problem, or None. `solids` and `pool` (every building on the
    lot) as _stacks joined them."""
    for group in _connected(solids):
        mine = {i for b in group for i in _parts(b)}
        rest = [x for x in pool if not set(_parts(x)) & mine]
        why = _floating(group, points, rest)
        if why:
            return why
    return None


def _fits(pts) -> bool:
    """Whether the spot grades fix a plane well: three or more, not near a line."""
    xy = pts[:, :2] - pts[:, :2].mean(axis=0)
    return len(pts) >= 3 and np.linalg.matrix_rank(xy) == 2 and np.linalg.cond(xy) < 30


def _ground_at(corners: list, points: list) -> list:
    """THE ground under each corner from the spot grades (for _floating and the ground cut alike): their best-fit
    plane when they fix one well, clamped to the levels measured (never extrapolated), else the nearest point's."""
    pts = np.array([p[:3] for p in points], dtype=float)
    if _fits(pts):
        coef, *_ = np.linalg.lstsq(np.c_[pts[:, :2], np.ones(len(pts))], pts[:, 2], rcond=None)
        lo_z, hi_z = float(pts[:, 2].min()), float(pts[:, 2].max())     # never beyond the levels measured
        return [min(max(coef[0] * x + coef[1] * y + coef[2], lo_z), hi_z) for x, y in corners]
    return [float(pts[int(np.argmin(((pts[:, :2] - (x, y)) ** 2).sum(axis=1))), 2]) for x, y in corners]


def _own_points(buildings: list[dict], points: list, others: list = ()) -> list:
    """The spot grades that are these buildings' ground: a point at one of the `others`' walls (and not at these
    buildings') is that building's ground, never these (THE filter, for the grade plane, _floating and the cut)."""
    near = [_projection(b) for b in others if b.get("faces")]
    if not near or not points:
        return list(points or [])
    mine = ops.unary_union([_projection(b) for b in buildings if b.get("faces")])
    theirs = ops.unary_union(near)
    return [p for p in points if not (theirs.distance(Point(p[:2])) <= SPOT_REACH
                                      and mine.distance(Point(p[:2])) > SPOT_REACH)]


def ground_for(buildings: list[dict], points: list, others: list = ()) -> tuple:
    """THE ground model: (the ground under each corner of these buildings' footprint, or None when there is none
    of their own; their own spot grades). From their own spot grades only (_own_points), by _ground_at. _floating,
    the ground cut (_at_ground) and the envelope (through _meets_ground) all read it."""
    corners = [p[:2] for b in buildings for f in b.get("faces") or [] for p in f["points"]]
    own = _own_points(buildings, points, others)
    return (_ground_at(corners, own) if own and corners else None), own


def _floating(buildings: list[dict], points: list, others: list = ()) -> str | None:
    """Whether the buildings meet the ground the spot grades describe, ONE test whatever the points' positions
    (stress F15): the ground at every corner of their footprint (every face point seen from above), from the
    points' best-fit plane when they fix one well (three or more, not near a line), else the nearest point's
    level, clamped to the levels measured (never extrapolated). They meet it if their bottom is at or below the
    ground at some corner (on a slope the rest stands above it by no more than the ground's own fall across the
    footprint: an exposed foundation) and their top is above it; otherwise ground_off_building, or ground_unclear
    when the points can't tell. A point at one of the `others`' walls (and not these buildings') is that
    building's ground, never these: left out, as for the grade plane."""
    zs = [p[2] for b in buildings for f in b.get("faces") or [] for p in f["points"]]
    corners = [p[:2] for b in buildings for f in b.get("faces") or [] for p in f["points"]]    # never empty
    if not zs or not points or not corners:
        return None
    ground, points = ground_for(buildings, points, others)
    if not points:                      # every point is another building's ground: none for this one
        return stop("ground_unclear")
    pts = np.array([p[:3] for p in points], dtype=float)
    fits = _fits(pts)
    bottom, top = min(zs), max(zs)
    gaps = [bottom - g for g in ground]          # above the ground (+) or below it (-) at each corner
    meets = min(gaps) <= TOL and top > max(ground) + TOL
    if meets:
        return None
    if not fits:                                # the nearest points only: floating if they are near every corner
        far = max(float(np.sqrt(((pts[:, :2] - (x, y)) ** 2).sum(axis=1)).min()) for x, y in corners)
        if far > 5 * SPOT_REACH:
            return stop("ground_unclear")
    worst = max(ground)
    return stop("ground_off_building", ground=_r(worst), bottom=_r(bottom), top=_r(top))


def grade_plane(buildings: list[dict], facts: dict) -> tuple:
    """(grade, None) or (None, reason): the grade plane from the spot grades in `facts`, at the main building's own
    walls (§325-3 GRADE PLANE: "on each side of the building"). The main building is pick_main's, as for every
    measurement (an assumed starting house too); with none, it's a question, as for the height."""
    stacks = _stacks(buildings)
    main, _ = pick_main(stacks, facts)          # THE pick (an assumed starting house too: the others are read too)
    if stacks and main is None:
        return None, stop("no_main_building")
    return _grade_from_points([main] if main else [], facts["grade_points"], [b for b in stacks if b is not main])


def _grade_from_points(buildings: list[dict], points: list, others: list = ()) -> tuple:
    """GRADE PLANE: "the average of finished ground level on each side of the building at exterior walls",
    from spot grades placed in the model (or the terrain sampled at the walls). Each wall of the buildings'
    outline seen from above (any longer than 1 ft) gets the levels of the points within SPOT_REACH of it; the grade
    plane is the average of the walls' averages. (grade, None), or (None, reason) when a point is off the walls or
    a wall has none: after the building moves, the points no longer say the ground level at its walls.
    `buildings` is the building measured (the main building); a point at the walls of one of the `others` (a
    detached garage) is that building's ground, never this one's: it is left out, not counted as off."""
    plans = [_projection(b) for b in buildings if b.get("faces")]
    if not plans:
        return sum(p[2] for p in points) / len(points), None
    # each wall once, however the outlines were drawn: points along a straight wall (where the union joined the
    # solids, or where a ring happened to start) are dropped, so one wall is never split in two (stress F9)
    outline = ops.unary_union(plans).simplify(TOL, preserve_topology=True)
    rings = [g.exterior for g in getattr(outline, "geoms", [outline]) if not g.is_empty]
    walls = [LineString([a, b]) for ring in rings for a, b in zip(ring.coords, ring.coords[1:])
             if math.dist(a, b) > 1.0]
    if not walls:                       # a round or finely faceted outline: no wall longer than 1 ft to sort by
        return None, stop("grade_walls_unclear")
    elsewhere = [_projection(b) for b in others if b.get("faces")]          # filled: a point under one is its own
    elsewhere = ops.unary_union(elsewhere) if elsewhere else None      # the other buildings, in plan
    levels, off = {i: [] for i in range(len(walls))}, 0
    for x, y, z in points:
        here = Point(x, y)
        i = min(range(len(walls)), key=lambda k: walls[k].distance(here))
        if walls[i].distance(here) <= SPOT_REACH:
            levels[i].append(z)
        elif outline.contains(here):            # under the building itself (a terrain sample where a wing joins):
            continue                            # ground beneath it, not off its walls
        elif elsewhere is None or elsewhere.distance(here) > SPOT_REACH:
            off += 1
    bare = sum(1 for v in levels.values() if not v)
    if off or bare:
        return None, stop("grade_off_walls", off=off, count=len(points), bare=bare)
    return sum(sum(v) / len(v) for v in levels.values()) / len(levels), None


def measure(site: dict, facts: dict) -> dict[str, dict]:
    """Every measurement in measures.yaml, in its order, each with its working, for one site and its lot facts."""
    _SKY.clear()
    _PLANES.clear()
    _PLAN_OF.clear()
    try:
        try:
            out = _measure(site, facts)
            if site.get("lot") and site["lot"].get("edges"):
                # the decision line: how the lot lines read were cleaned from the outline drawn (its own accuracy);
                # inside the one guard, so a lot whose geometry can't be worked out stops here too (round 21)
                note = Lot(site, facts).outline_note
                for name in LOT_LINE_MEASURES if note else ():
                    if name in out:
                        out[name]["outline"] = note
        except shapely.errors.GEOSException as e:
            # the drawing's geometry couldn't be worked out: every measurement needs review, saying why; never a
            # crash (no answer at all in Rhino) and never a guess (stress F14)
            why = stop("geometry_error", what=str(e).split(":")[0][:80])
            out = {name: (_record(name, "text", reason=why) if name == "district" else _missing(name, why))
                   for name in MEASURES}
            for r in out.values():          # the flag the rest of the check reads: no overlays drawn from it
                r["geometry_error"] = why
            for name, unit in STATED.items():           # what the architect stated still stands
                if facts.get(name) is not None:
                    out[name] = _record(name, unit, facts[name], "stated by the architect (not measured from the model)")
            _set_aside_conflicts(out, facts)
            if facts.get("zone"):
                out["district"] = _record("district", "text", facts["zone"], "stated by the architect (the lot's zone)")
    finally:
        _SKY.clear()
        _PLANES.clear()
        _PLAN_OF.clear()
    assumed = out.pop("_assumed_main", None)
    shut = stop("open_solid", what="")
    open_ids = _open_ids(site.get("buildings") or []) if any(
        shut in (r.get("reason") or "") for r in out.values() if isinstance(r, dict)) else []
    for name in MEASURES:               # a row waiting on an open object points at it (Zoom to finds it), and
        r = out[name]                   # still at any building off the lot named beside it (review round 24)
        if open_ids and r.get("value") is None and shut in (r.get("reason") or ""):
            out[name] = dict(r, objects=list(dict.fromkeys([*open_ids, *(r.get("objects") or [])])))
    if assumed:                         # every measurement made from the starting house carries the marker
        for name in MEASURES:
            r = out[name]
            if set(r.get("objects") or []) & set(assumed) and (r.get("value") is not None or r.get("readings")):
                out[name] = dict(r, main_assumed=True)
    return {name: out[name] for name in MEASURES}


def pick_main(buildings: list[dict], facts: dict) -> tuple:
    """THE main-building pick, (main, assumed), for every measurement (and the grade plane): the only building;
    else the one picked (main_building names one of its blocks); else, with none picked, Gordium's own starting
    house if exactly one building is all floor blocks GordiumStart drew (assumed: every other building that could
    be a principal one, _could_be_principal, is then also read as if it were the main one, _assemblies); else
    none. `buildings`: as _stacks joins them."""
    if len(buildings) == 1:
        return buildings[0], False
    picked = next((b for b in buildings if facts.get("main_building") in b.get("parts", [b["id"]])), None)
    if picked is not None or facts.get("main_building"):
        return picked, False
    def named(b, ids):
        return any(i in b.get("parts", [b["id"]]) for i in ids)
    # (PR 18) the only one the architect hasn't listed as an accessory building; or, when everything left touches
    # together (one building, §325-18A: a porch, steps, a wing), its tallest part, then the largest
    rest = [b for b in buildings if not named(b, facts.get("accessory_buildings") or [])]
    if len(rest) == 1:
        return rest[0], False
    plans = {b["id"]: _projection(b) for b in rest if b.get("faces")}
    if rest and len(plans) == len(rest) and len(_touching(rest[0], rest, plans)) == len(rest) - 1:
        return max(rest, key=lambda b: (max(p[2] for f in b["faces"] for p in f["points"]),
                                        plans[b["id"]].area)), False
    starting = [b for b in buildings if b.get("parts") and all(b["floor"])]
    return (starting[0], True) if len(starting) == 1 else (None, False)


# the dwelling units a use itself says (§325-3B: a one-family dwelling is a dwelling unit; a two-family dwelling holds two)
IMPLIED_UNITS = {"one_family_detached": 1, "two_family": 2}


def fact_conflicts(facts: dict) -> list[tuple[str, tuple]]:
    """Stated facts each well formed but contradicting each other: (the reason, the facts in it). Every fact in one is
    set aside with that reason (_set_aside_conflicts), so no row reading it can comply on facts that contradict each
    other (#38: R-1b's occupancy row complied on two unrelated-people counts that disagreed, because only the count
    R-3 and RU read was set aside); the panel also shows each one as a "Lot facts disagree" row with the button to
    re-enter them (project.fact_conflict_rows)."""
    out = []
    here, building = facts.get("dwelling_units"), facts.get("attached_units_in_building")
    if facts.get("use") == "one_family_attached" and type(here) is int and type(building) is int and here > building:
        out.append((stop("attached_counts_disagree", here=here, building=building),
                    ("dwelling_units", "attached_units_in_building")))
    # the unrelated people counted with minor dependent children can't be fewer than without them: a mistyped pair,
    # and which count is wrong can't be told (review round 2 set aside only the one R-3 and RU read)
    without, with_ = facts.get("unrelated_persons"), facts.get("unrelated_persons_with_children")
    if type(without) is int and type(with_) is int and with_ < without:
        out.append((stop("household_counts_disagree", without=without, with_=with_),
                    ("unrelated_persons", "unrelated_persons_with_children")))
    # the occupants of every unit on the lot together, and the most in any one unit (R-2c notes 4-6): the most in one
    # unit can't be more than all of them, and the units can't hold more than units x the most in one (#38 review
    # round 1: 2 units, 10 occupants, at most 1 in a unit read as "both units lived in" and complied on 7,200 sf)
    total, most = facts.get("occupants"), facts.get("occupants_most_in_one_unit")
    if type(total) is int and type(most) is int:
        stated = facts.get("dwelling_units")
        units = stated if type(stated) is int else IMPLIED_UNITS.get(facts.get("use"))
        # an accessory dwelling unit on the lot (or not said) is one more unit whose occupants count too (review round 2:
        # a house of 2 and an ADU of 2 are 4 occupants, at most 2 in one): no ceiling then. No unit at all is the
        # rules' own case (R-2c: "no dwelling unit stated"), not this one.
        if most > total:
            out.append((stop("occupant_split_disagree", most=most, occupants=total),
                        ("occupants", "occupants_most_in_one_unit")))
        elif units and facts.get("accessory_dwelling_unit") is False and total > units * most:
            # "no ADU" is one of the answers that can't all be true (review round 3: R-1b's occupancy rule reads it and
            # complied on it), so it is set aside too; the units only when stated (else the use's own, §325-3B)
            said = type(stated) is int          # the units entered, or the use's own count (review round 4: say which)
            out.append((stop("occupant_counts_disagree", occupants=total, units=units,
                             unit_words=("dwelling unit" if units == 1 else "dwelling units") + (
                                 "" if said else " (what this use is, §325-3B)"),
                             most=most, held=units * most,
                             check="the occupant counts, the dwelling units" if said else "the occupant counts"),
                        ("occupants", "occupants_most_in_one_unit", "accessory_dwelling_unit")
                        + (("dwelling_units",) if type(stated) is int else ())))
    return out


def _set_aside_conflicts(out: dict, facts: dict) -> None:
    """Every stated fact in a contradiction (fact_conflicts) is set aside with the contradiction as its reason: the
    rules that read it need review, saying so, and never comply on it."""
    for why, names in fact_conflicts(facts):
        for name in names:
            before = out.get(name) or {}
            reason = why if before.get("value") is not None or not before.get("reason") else before["reason"] + "; " + why
            out[name] = _record(name, STATED[name], reason=reason)


def _measure(site: dict, facts: dict) -> dict[str, dict]:
    out = {}
    for name, unit in STATED.items():
        v = facts.get(name)
        out[name] = (_record(name, unit, v, "stated by the architect (not measured from the model)")
                     if v is not None else _record(name, unit, reason=stop(ASK[name])))
    _set_aside_conflicts(out, facts)
    # the lot's zoning district is the zone the architect stated (the facts' "zone")
    out["district"] = (_record("district", "text", facts["zone"], "stated by the architect (the lot's zone)")
                       if facts.get("zone") else _record("district", "text", reason=stop("no_district")))
    buildings = site.get("buildings") or []
    grade = facts.get("grade_elevation")
    # objects are told apart by id below (spans, outlines): two with one id are refused (_building_problems)
    why_building = _building_problems(buildings)
    # the ground must meet the buildings, taken together (stacked floors, a basement or a tower drawn as its own
    # solid sit above or below it): at or above their lowest point and below their top. A level outside that (a
    # survey elevation typed for a model drawn at z = 0) would give a negative or inflated height, and an empty
    # cut at the ground blamed on overhangs.
    why_spots = None
    if facts.get("grade_points") and not why_building:     # spot grades (or terrain sampled at the walls): the
        grade, why_spots = grade_plane(buildings, facts)        # grade plane, once the buildings can be measured
    zs = [p[2] for b in buildings for f in b.get("faces") or [] for p in f["points"]]
    lo, hi = (min(zs), max(zs)) if zs else (None, None)
    spots = facts.get("grade_points") if not why_building else None
    # whether the buildings meet the ground: with spot grades ONE test, at their footprint, whatever the points'
    # positions (stress F15: the grade plane's average and the footprint judged it differently); else the level
    stacked = _stacks(buildings) if spots else []
    home = _grade_home(buildings, facts) if spots else None       # the solids the grade plane is read for
    ground_problem = (_meets_ground(stacked, spots, stacked) if spots else None) or \
        (_ground_against(buildings, grade, off_check=not spots, points=spots, home=home)
         if grade is not None else None)
    why_grade = (why_spots if why_spots else stop("no_ground") if grade is None else
                 ground_problem if ground_problem else
                 None if facts.get("grade_points") else
                 stop("ground_unknown") if facts.get("ground_is_flat") is None else
                 None if facts["ground_is_flat"] else stop("sloped_ground"))
    # the grade decides height and stories. The plan (yards, building area) only needs the level where the building
    # meets the ground: with no grade (not given, not known to be flat, spot grades off the walls) that is the
    # building's own base, so the plan is still measured; a grade that contradicts the building (off it, a solid
    # buried under it) still stops the plan, since then even the base can't be trusted.
    why_plan = ground_problem
    grade_known = grade is not None and not why_grade       # a real ground level, not the buildings' own base
    plan_level = grade if grade_known else lo
    # stacked floor blocks (each story its own solid, standing on the one below, as Gordium's starting building is
    # drawn) are one building, and its stories are counted from them: read from the shape, never typed
    buildings = _stacks(buildings)
    main, assumed = pick_main(buildings, facts)
    if assumed:                         # every other possible principal building is also read as the main one
        out["_assumed_main"] = list(main["parts"])
    why_main = None if main else stop("no_main_building")
    others = [b for b in buildings if b is not main]
    # One decision for every building measurement: which building (why_which), over which candidate buildings
    # (_assemblies: the main one alone, and with every other solid as part of it). The typed story count is a
    # stated fact: it stands as the value only when nothing drawn anywhere can be counted (no floor blocks and no
    # stacked solids on any building, and no building object with a problem, which might be either). Otherwise
    # the stories come from the drawing over the same assemblies as the height, the typed count only a reading
    # beside them, and every stop that applies to the height applies to them.
    why_which = why_building or why_main
    countable = bool(buildings) or bool(why_building and site.get("buildings"))   # every drawn part is checked
    # the candidate buildings, each with its own grade plane: the one list the stories and the height read
    candidates = _candidate_grades(_assemblies(main, others, assumed) if not why_which else [], buildings, facts,
                                   grade, why_grade)
    if countable:
        out["stories"] = (_missing("stories", why_which) if why_which else
                          _stories_over(candidates, grade, why_grade, facts.get("stories")))
    why = why_which or why_grade
    out["building_height"] = _missing("building_height", why) if why else _height(main, grade, facts)
    if not why and others and (out["building_height"]["value"] is not None or out["building_height"]["readings"]):
        # each candidate building measured from its own grade plane (§325-3: the ground at ITS walls): a wing on
        # lower ground lowers the grade of the building it is part of; a detached garage's ground never moves the
        # house's (review round 18). A candidate whose grade can't be found leaves the height unknown. Each
        # candidate by its label (kind), never its position (round 2 of the main-building fixes).
        why_g = next((c["why"] for c in candidates if c["why"]), None)    # a candidate's ground that can't be used
        if why_g:
            out["building_height"] = _missing("building_height", why_g)
        else:
            own = [dict(c, height=out["building_height"] if len(c["members"]) == 1 else _height(main, c["grade"], facts),
                        part_heights=[_height(b, c["grade"], facts) if any(b is m for m in c["members"]) else None
                                      for b in others])
                   for c in candidates if c["kind"] in OWN_KINDS]
            out["building_height"] = _with_others(own, [_parts(b)[0] for b in others])
        if assumed and not why_g:       # and each other building as the main one, from its own grade plane
            out["building_height"] = _with_each_as_main(out["building_height"], candidates, facts)
    if facts.get("grade_is") == "existing":     # the grade plane is finished ground: existing ground can't decide
        for name in ("building_height", "stories"):
            if out[name].get("value") is None and not out[name].get("readings"):
                continue                       # nothing measured: its own reason (no ground, ...) says why
            as_is = out[name].get("value")     # what the ground as it is gives: shown, never decides (no reading)
            as_is_readings = sorted({r["value"] for r in out[name].get("readings") or [] if r.get("value") is not None})
            out[name] = _missing(name, stop("existing_grade"))
            if as_is is not None:
                out[name]["measured_as_is"] = as_is
            elif as_is_readings:               # its readings disagree: kept, so what waits is said as it is
                out[name]["measured_as_is_readings"] = as_is_readings

    # the accessory buildings (§325-25): every solid standing apart from the main building (one touching it, a
    # porch, deck, steps or an attached garage, is part of it). Counted even without a lot outline.
    parts_of = _attached(main, buildings) if main is not None and not why_building else []
    detached = [b for b in buildings if main is not None and b is not main and b not in parts_of]
    out["accessory_buildings"] = (
        _missing("accessory_buildings", why_building or why_main) if why_building or why_main else
        _record("accessory_buildings", "count", len(detached),
                "the solids on the Building layer standing apart from the main building (§325-25)",
                [i for b in detached for i in _parts(b)]))
    out["accessory_distances_apply"] = _distances_apply(facts, detached, why_building or why_main)

    problems = list(site.get("problems") or [])
    lot = Lot(site, facts) if site.get("lot") and not problems else None
    if lot is None or lot.problems:
        reason = "; ".join(problems or (lot.problems if lot else [stop("no_lot")]))
        for name in UNITS:
            out.setdefault(name, _missing(name, reason))
        return out
    if facts.get("lot_surveyed"):
        out["lot_area"] = _record("lot_area", "sf", _r(lot.polygon.area), "the area inside the lot lines (a survey)",
                                  [lot.id])
    else:                               # a drawn lot isn't a surveyed one: the lot area waits for a survey
        out["lot_area"] = _record("lot_area", "sf", None, "the area inside the lot lines", [lot.id], None,
                                  [{"reading": "the lot as drawn", "value": _r(lot.polygon.area)}],
                                  stop("survey_unknown") if facts.get("lot_surveyed") is None else stop("not_surveyed"))
        # tax-map lot lines can each be off by up to TAX_MAP_TOLERANCE: the outline moved that much in or out
        # (73 × 90 → 69 × 86 at the smallest). Not a value: the area still waits for a survey; this only lets a
        # result that holds at both ends be said (spec C2)
        out["lot_area"]["tolerance"] = tax_map_lot_area(lot.polygon)

    # where the street is decides the lot width, the yards and the lot depth. Whether the lot is a corner lot
    # (two streets, §325-19C) is stated by the architect, never guessed from the drawing (the city's definition
    # has no angle in it).
    if not lot.street_problem and facts.get("corner_lot") is None:
        lot.street_problem = stop("corner_unknown")
    lines = None if lot.street_problem else _lot_lines(lot, facts)
    why_street = lot.street_problem or (lines if isinstance(lines, str) else None)
    if why_street:
        for name in LOT_LINE_MEASURES:
            out[name] = _missing(name, why_street)
    else:
        out["lot_width"] = _width(lot, facts, lines)

    # each building as the yards and coverage see it. Its walls at ground level (`ground`): decided per solid,
    # from the one ground model (_at_ground, #15 rounds 7-8): a solid resting on the ground is cut at the higher of
    # the grade plane and its own bottom; one raised off it (a balcony) is left out. `buildings` as _stacks joined
    # them, the list _at_ground reads (each solid's neighbours, its own spot grades)
    views = ({b["id"]: _views(b, facts, _at_ground(b, buildings, plan_level, spots, grade_known, home))
              for b in buildings} if plan_level is not None and not why_building else {})
    # one rule for each building on its own (each stack, each detached building), whatever the others are:
    # within the lot: measured as usual; partly outside: every rule that measures it does not comply
    # (_mark_crossings, naming the lines it crosses where they can be told); wholly outside: the rules that would
    # measure it need review (outside_lot: is it part of this design?). An object covering nothing seen from above
    # has nowhere to be placed: it is open (_unenclosed), refused with its own name by _building_problems, so it
    # is never placed here
    place = {}
    for b in buildings:
        p = _projection(b)
        if not p.is_empty:
            place[b["id"]] = ("on" if p.within(lot.polygon.buffer(TOL)) else
                              "off" if p.intersection(lot.polygon).area <= 1e-6 else "partly")
    crossed = {i: _crossed(lot, _projection(next(b for b in buildings if b["id"] == i)))
               for i, s in place.items() if s == "partly"}
    crosses = bool(crossed)
    group = [main, *parts_of] if main is not None else []
    # an object that isn't a closed solid stops every measurement, by name (_building_problems; measure() points
    # every row waiting on it at it). When that is the only thing wrong, a building wholly off the lot is still
    # said beside it, naming its own objects (review round 24): the architect sees both at once
    opened = set(_open_ids(site.get("buildings") or [])) if why_building else set()
    only_open = bool(opened) and _building_problems(
        [b for b in site.get("buildings") or [] if b["id"] not in opened]) is None
    beside = not why_building or only_open      # whether the placement's own reasons can be said

    def placed(bs):                 # the buildings the placement can speak for (never an open object)
        return [b for b in bs if not set(_parts(b)) & opened] if beside else []

    def off_named(bs):              # which buildings are wholly outside the lot, by name (term-index's words)
        off = [b for b in bs if place.get(b["id"]) == "off"]
        main_off = any(b is main for b in off)
        n = len(off) - main_off
        return " and ".join((["the main building" if len(buildings) > 1 else "the building"] if main_off else []) +
                            ([f"{n} other building{'s' if n > 1 else ''}" if main_off or main is not None else
                              f"{n} building{'s' if n > 1 else ''}"] if n else []))

    def unplaced(bs):               # wholly off the lot: the rules that would measure it wait, naming them
        bs = placed(bs)
        return stop("outside_lot", what=off_named(bs)) if any(place.get(b["id"]) == "off" for b in bs) else None

    def unplaced_ids(bs):           # the objects that reason is about: the panel shows them
        return [i for b in placed(bs) if place.get(b["id"]) == "off" for i in _parts(b)]

    def both(*whys):                # every reason that applies, each naming its own buildings (round 22)
        return "; ".join(w for w in whys if w) or None
    why_main_off = unplaced(group)
    why_acc_off = unplaced(detached)
    why_inside = both(why_building, unplaced(buildings))    # coverage
    if why_inside or why_plan or plan_level is None:
        out["building_area"] = _missing("building_area", why_inside or why_plan or why_grade)
        if why_inside and unplaced_ids(buildings):     # which ones: the panel shows them
            out["building_area"]["objects"] = unplaced_ids(buildings)
    else:
        out["building_area"] = _coverage(buildings, views, facts, main)
    if crosses:                         # coverage, the height and the accessory count: whatever else follows
        _mark_crossings(out, lot, lines, crossed, main, parts_of, detached, buildings)

    if why_street:
        return out
    if lines["problem"]:
        out["lot_depth"] = _missing("lot_depth", lines["problem"])
    else:
        out["lot_depth"] = _decide("lot_depth", [(w, (lot.length(r["left"]) + lot.length(r["right"])) / 2, {})
                                                 for w, r in lines["readings"]],
                                   "the average length of the two side lot lines", [lot.id], lines["question"],
                                   lines["basis"]["depth"])

    # every other reason the plan can't be trusted, on its own (never read off an `or` chain: review round 9)
    why_rest = why_building or why_plan or why_main or (why_grade if plan_level is None else None)
    why_yards = both(why_building, why_main_off) if why_building else why_main_off or why_rest
    if why_yards:
        for name in YARDS + EAVE_YARDS + ACCESSORY_YARDS:
            out[name] = _missing(name, why_yards)
        if why_main_off and (why_building or not why_rest):      # the unplaced buildings named (round 22)
            for name in YARDS + EAVE_YARDS:
                out[name]["objects"] = unplaced_ids(group)
        if why_building:                # an open object: the accessory rules wait on it, and on their own placement
            for name in ACCESSORY_YARDS:
                out[name] = dict(_missing(name, both(why_building, why_acc_off)), objects=unplaced_ids(detached))
        elif why_main_off and not why_rest and why_acc_off:
            for name in ACCESSORY_YARDS:        # an accessory building unplaced too: its own reason, its own ids
                out[name] = dict(_missing(name, why_acc_off), objects=unplaced_ids(detached))
        elif why_main_off and not why_rest and detached:
            # only the main building is off the lot: an accessory building on it is still measured on its own
            _accessory_yards(out, lot, lines, facts, detached, views)
        return out
    _yards(out, lot, lines, facts, main, parts_of, detached, views)
    if why_acc_off:                              # an accessory building wholly off the lot: its own rule waits
        for name in ACCESSORY_YARDS:
            out[name] = dict(_missing(name, why_acc_off), objects=unplaced_ids(detached))
    if crosses:
        _mark_crossings(out, lot, lines, crossed, main, parts_of, detached, buildings)
    return out


def _crossed(lot: Lot, plan) -> set:
    """The lot lines (by index) one building crosses: those its part outside the lot runs along."""
    outside = plan.difference(lot.polygon.buffer(TOL))
    if outside.area <= 1e-6:
        return set()
    reach = outside.buffer(2 * TOL)
    return {i for i, e in enumerate(lot.edges) if reach.intersection(LineString(e)).length > 4 * TOL}


def _mark_crossings(out: dict, lot: Lot, lines: dict, crossed: dict, main: dict, parts_of: list, detached: list,
                    buildings: list):
    """A building that crosses a lot line stands partly on another lot: it fails every rule that measures it,
    whatever the readings or answers (the checker does that, check.crossing). Each measurement of a building
    records that building's own crossings, `crossings`: [{"who", "lines": street / side / rear}]: the main
    building's on the main yards, the eaves and the height; each accessory building's on the accessory
    measurements; every building's on the coverage, whichever is the main building, or with none known yet
    (coverage counts every building on the lot: stress F17, a garage across a line failed coverage with the house
    drawn as floor blocks and complied with it drawn as one solid, the main building then unpicked)."""
    sides = {i for _w, r in lines["readings"] for g in r["sides"] for i in g} if lines and not isinstance(lines, str) else set()
    rears = {i for _w, r in lines["readings"] for i in r["rear"]} if lines and not isinstance(lines, str) else set()

    def kinds(idx):                  # the lines that can be named: street, side, rear (an unclear one isn't)
        return sorted({"street" if i in lot.street else "side" if i in sides else "rear" if i in rears else ""
                       for i in idx} - {""})
    group = [main, *parts_of] if main is not None else []
    partly = [b for b in group if b["id"] in crossed]
    mine = set().union(*(crossed[b["id"]] for b in partly)) if partly else set()
    entries_main = [{"who": "the main building", "lines": kinds(mine)}] if partly else []
    entries_acc = [{"who": f'accessory building "{_parts(b)[0]}"', "lines": kinds(crossed[b["id"]])}
                   for b in detached if b["id"] in crossed]
    for name in YARDS + EAVE_YARDS + ("building_height", "stories"):
        if entries_main and name in out:
            out[name]["crossings"] = entries_main
    for name in ACCESSORY_YARDS + ("accessory_buildings", "accessory_distances_apply"):
        if entries_acc and name in out:
            out[name]["crossings"] = entries_acc
    known = {id(b) for b in group + list(detached)}
    entries_any = [{"who": f'building "{_parts(b)[0]}"', "lines": kinds(crossed[b["id"]])}
                   for b in buildings if b["id"] in crossed and id(b) not in known]
    if (entries_main or entries_acc or entries_any) and "building_area" in out:
        out["building_area"]["crossings"] = entries_main + entries_acc + entries_any


def _attached(main: dict, buildings: list[dict]) -> list[dict]:
    """The solids touching the main building in plan (within TOUCH), or touching one that does: a porch, deck,
    steps, ramp or landing (part of the building, §325-18A; steps: Gordium's reading steps_count), or an attached
    garage (Gordium's reading attached_garage_is_main_building)."""
    return _touching(main, buildings, {b["id"]: _projection(b) for b in buildings})


def _touching(seed: dict, candidates: list[dict], plans: dict) -> list[dict]:
    """The candidates joined to `seed` in plan, within TOUCH of it or of one already joined: the one test of
    "solids that touch are one building", used to pick the main building and to find its parts."""
    found, grown = [], plans[seed["id"]]
    while new := [b for b in candidates if b is not seed and b not in found and plans[b["id"]].distance(grown) <= TOUCH]:
        found += new
        grown = ops.unary_union([grown] + [plans[b["id"]] for b in new])
    return found


def _distances_apply(facts: dict, detached: list[dict], why: str | None) -> dict:
    """Whether §325-25C's side and rear distances apply to the accessory buildings. A frame building: yes, the
    law (accessory_structures_follow_325_25). Not frame, or not stated: §325-25C's open question, every reading
    research lists (frame_distances_apply: yes; r1_distances_apply_to_all_accessory_buildings: yes in an R-1
    district, otherwise no; front_yard_rule_only: no). A frame building gives the same as the first reading,
    so a construction not stated adds no reading."""
    name = "accessory_distances_apply"
    if why:
        return _missing(name, why)
    if not detached:
        return _record(name, "yes_no", reason=stop("no_accessory"))
    rule = law.finding(facts, "side_yard", "accessory_structures_follow_325_25")
    if facts.get("accessory_frame") is True:
        if rule is None:
            return _record(name, "yes_no", reason=stop("law_missing", what="§325-25's finding (side_yard)"))
        return _record(name, "yes_no", True, "frame accessory buildings (stated): §325-25C's distances apply",
                       basis=[law.basis(rule)])
    q = law.question(facts, "325-25C", NOT_FRAME)
    if q["state"] == "missing":
        return _record(name, "yes_no", reason=stop("law_missing", what="§325-25C's open question (not frame)"))
    r1 = str(facts.get("zone") or "").upper().startswith("R-1")
    known = {"frame_distances_apply": True, "r1_distances_apply_to_all_accessory_buildings": r1,
             "front_yard_rule_only": False}
    readings = []
    for rid in q["readings"]:
        if rid not in known:
            return _record(name, "yes_no", reason=stop("reading_unknown", reading=rid, entry="325-25C"))
        readings.append({"reading": NOT_FRAME_WORDS[rid], "value": known[rid], "named": {q["tag"]: rid}})
    how = ("accessory buildings not stated as frame" if facts.get("accessory_frame") is None else
           "accessory buildings that aren't frame (stated)") + ": §325-25C's distances, read every way research lists"
    values = {r["value"] for r in readings}
    if len(values) == 1:
        return _record(name, "yes_no", values.pop(), how, readings=readings if len(readings) > 1 else [],
                       basis=[law.basis(rule)])
    return _record(name, "yes_no", None, how, readings=readings, reason=stop("readings_differ", question=(
        "whether §325-25C's distances apply to an accessory building that isn't frame is an open question for the "
        "architects (325-25C); say whether the accessory buildings are frame (accessory_frame)")),
        basis=[law.basis(rule)])


NOT_FRAME = ("frame_distances_apply", "r1_distances_apply_to_all_accessory_buildings", "front_yard_rule_only")
NOT_FRAME_WORDS = {"frame_distances_apply": "the frame distances apply to every accessory building",
                   "r1_distances_apply_to_all_accessory_buildings": "in R-1, the 6 ft side / 3 ft rear distances apply "
                                                                    "to every accessory building",
                   "front_yard_rule_only": "only \"not in a required front yard\" applies"}
EAVE_COVERAGE = ("eaves_not_counted", "eaves_over_2ft_counted", "eaves_counted")   # building_area's open question
EAVE_QUESTION = ("whether what the pitched roof reaches past the walls is an eave (§325-18B) or part of the building "
                 "can't be told from the model: the architect confirms it (eaves_confirmed)")
PROJ_QUESTION = ("whether a part below the roof that sticks out past the walls at the ground is an upper floor "
                 "(part of the building) or a bay window (a projection, §325-18B) can't be told from the model "
                 "(yard_projections)")
PROJECTION = 2.0          # ft: eaves and similar features may project this far into a required yard (§325-18B)


def _views(building: dict, facts: dict, ground) -> dict:
    """A building as the yards and coverage see it: `above`, the full outline, everything its solids cover seen
    from above (what every yard and coverage is measured to); `body`, the same without the candidate eaves
    (_eave_candidate: a suggestion only); `ground`, its walls at ground level, as given (_at_ground: decided per solid
    from the one ground model; empty for a solid raised off the ground); `candidate`, the candidate's
    fingerprint (None if there is none); `confirmed`, the architect's confirmation that it is eaves, if any."""
    above = _projection(building)
    candidate = _eave_candidate(building) if building.get("faces") else None
    zone = candidate["zone"] if candidate else None
    # the zone starts TOL past the walls; grown back by TOL (square corners) it meets them exactly
    body = above.difference(zone.buffer(TOL, join_style=2)) if zone is not None else above
    if body.is_empty:
        body = above
    has = above.difference(body.buffer(TOL)).area > 1e-6
    return {"above": above, "body": body, "ground": ground,
            "candidate": candidate["overhang"] if has else None,
            "confirmed": _confirmed(facts, candidate) if has else None}


def _coverage(buildings: list[dict], views: dict, facts: dict, main: dict | None) -> dict:
    """Lot coverage: every building on the lot, principal and accessory, seen from above (porches, decks,
    cantilevered floors included): the finding coverage_seen_from_above, and garages count (garages_count).
    Whether eaves count is building_area's open question: where a pitched roof has eaves, every reading."""
    name = "building_area"
    seen = law.finding(facts, "building_area", "coverage_seen_from_above")
    garages = law.finding(facts, "building_area", "garages_count") if len(buildings) > 1 else None
    if seen is None or (len(buildings) > 1 and garages is None):
        return _missing(name, stop("law_missing", what="building_area's findings (coverage seen from above, garages)"))
    basis = [law.basis(seen)] + ([law.basis(garages)] if garages else [])
    objects = [i for b in buildings for i in _parts(b)]
    how = "the area of every building on the lot seen from above, principal and accessory, porches and decks included"
    above = ops.unary_union([v["above"] for v in views.values()])
    candidates = [v for v in views.values() if v["candidate"]]
    if not candidates:                    # nothing that might be an eave: the full outline, the result
        return _record(name, "sf", _r(above.area), how, objects, basis=basis)
    q = law.question(facts, "building_area", EAVE_COVERAGE)
    if q["state"] == "missing":
        return _missing(name, stop("law_missing", what="building_area's open question (eaves)"))
    body = ops.unary_union([v["body"] for v in views.values()])
    beyond = ops.unary_union([v["body"].buffer(PROJECTION, join_style=2) for v in views.values()])
    shapes = {"eaves_not_counted": body, "eaves_counted": above,
              "eaves_over_2ft_counted": ops.unary_union([body, above.difference(beyond)])}
    readings = []
    for rid in q["readings"]:
        if rid not in shapes:
            return _missing(name, stop("reading_unknown", reading=rid, entry="building_area"))
        words = {"eaves_not_counted": "eaves left out", "eaves_counted": "eaves counted in full",
                 "eaves_over_2ft_counted": "the part of the eaves beyond 2 ft counted"}[rid]
        readings.append((words, shapes[rid].area, {"named": {q["tag"]: rid, EAVE: "eave"}}))
    question = "whether roof eaves count toward lot coverage is an open question for the architects (building_area)"
    if all(v["confirmed"] for v in candidates):           # the architect confirmed these are eaves
        readings = [(w, v, {"named": {k: r for k, r in x["named"].items() if k != EAVE}}) for w, v, x in readings]
        basis = basis + [_eave_basis(v["confirmed"]) for v in candidates]
    else:                                                 # not confirmed: the full outline is a reading too
        readings.append(("what reaches past the walls not an eave: the full outline", above.area,
                         {"named": {EAVE: "not_eave"}}))
        question += "; " + EAVE_QUESTION
    record = _decide(name, readings, how, objects, question, basis)
    record["eave_candidates"] = [v["candidate"] for v in candidates]
    return record


def _eave_basis(confirmation: dict) -> dict:
    """An architect's eave confirmation as a measurement shows what it applied."""
    return {"id": "eaves_confirmed", "entry": "lot facts", "kind": "answer", "confirm_with": None,
            "text": f"eaves confirmed by {confirmation.get('confirmed_by')}, {confirmation.get('date')}"}


def _lot_lines(lot: Lot, facts: dict):
    """Which lot lines are front, side and rear, every way they can be read: {"readings": [(words, {"left",
    "right": the two side lot lines (lot depth), "sides": the side lines that aren't on a street (the side yards),
    "rear", "address": the street the address is on})], "question", "basis", "problem", "candidates"}, or a reason
    (text) when the lot's streets themselves can't be read (no lot line is measured then).

    A lot on one street: the street is the front. A corner lot (§325-19C, the law: corner_lot_two_front_yards):
    every yard facing a street is a front yard; the rear yard is opposite the street the lot's address is on
    (§325-8A(14)(d)); the side lot lines are read from that street, and those on the other street are front
    yards, so one side yard is left, checked against Column 13 (Gordium's reading corner_lot_side_yard_column_13;
    both side measures are that one yard). Which street is the address street is a fact (address_street_line);
    not given, each end of the street lines is read as it."""
    streets = set(lot.street)
    basis, question = {"front": [], "side": [], "rear": [], "depth": []}, [("which lot lines count as side and rear lot lines is an open question for the "
                            "architects (lot_depth)")]
    if facts.get("corner_lot"):
        two = law.finding(facts, "front_yard", "corner_lot_two_front_yards")
        one = law.finding(facts, "side_yard", "corner_lot_side_yard_column_13")
        if two is None or one is None:
            return stop("law_missing", what="the corner-lot findings (front_yard, side_yard)")
        basis = {"front": [law.basis(two)], "side": [law.basis(one)], "rear": [], "depth": []}
        chain = lot.ordered_street()
        if not any(_turn(lot.edges[a], lot.edges[b]) > PARALLEL for a, b in zip(chain, chain[1:])):
            return stop("corner_one_street")    # stated a corner lot, but the lines given never turn a corner
        given = facts.get("address_street_line")
        if given:
            # the picks are drawn pieces: each matched to a drawn piece, then to the lot line it is part of
            hits = [next((q for q, e in enumerate(lot.drawn) if _same_point(e[0], a) and _same_point(e[-1], b) or
                          _same_point(e[0], b) and _same_point(e[-1], a)), None) for a, b in given]
            idx = sorted({lot.line_of_piece(q) for q in hits if q is not None} & set(chain))
            if None in hits or not idx or not lot._contiguous(idx) or any(lot.line_of_piece(q) not in chain for q in hits):
                return stop("address_not_a_street")
            candidates = [idx]
        else:
            # the address street is one of the streets: the street lines split only where they may turn a corner
            # (_street_splits), never mid-street (one street drawn in pieces is still one street, §325-8A col. 7)
            candidates = [c for k in _street_splits(lot, chain) for c in (chain[:k], chain[k:])]
            question.append("which street the lot's address is on decides which yard is the rear yard (§325-8A(14)(d)): "
                            "pick the address street (address_street_line)")
    else:
        candidates = [lot.ordered_street()]

    def unclear() -> dict:
        # too many to list: the side and rear lines wait, whatever other addresses give (never fewer readings
        # silently); the frontage and the front yards don't depend on them and are still measured (review round 10)
        return {"readings": [], "question": "; ".join(question), "basis": basis,
                "problem": stop("lines_unclear", limit=MAX_UNCLEAR_EDGES), "candidates": candidates}
    if len(candidates) > MAX_UNCLEAR_EDGES * 2:
        return unclear()
    found, problems = [], []
    for address in candidates:
        view = copy.copy(lot)
        view.street = list(address)
        readings = view.readings()
        if readings is None:
            return unclear()
        for words, left, right, rear in readings:
            sides = [g for g in ([i for i in left if i not in streets], [i for i in right if i not in streets]) if g]
            if any(i in streets for i in rear):
                problems.append(stop("rear_on_street"))
            elif not sides:
                problems.append(stop("no_side_line"))
            else:
                where = (f"the address on lot line{'s' if len(address) > 1 else ''} "
                         f"{', '.join(lot.label(i) for i in address)}") if len(candidates) > 1 else ""
                found.append((_both(where, words), {"left": left, "right": right, "sides": sides, "rear": rear,
                                                    "address": address}))
    # a reading the law excludes (its rear on a street, or no side line left) is dropped; if none is left, the
    # first reason says why. An address with too many lines stopped above (review round 9)
    problem = None if found else (problems[0] if problems else stop("no_rear_line"))
    return {"readings": found, "question": "; ".join(question), "basis": basis, "problem": problem,
            "candidates": candidates}


JOINT = 15                # degrees: a joint between two street lines turning no more than this is within one street


def _heading(edge) -> float:
    (x, y) = _chord(edge)
    return math.degrees(math.atan2(y, x))


def _street_splits(lot: "Lot", chain: list) -> list[int]:
    """Where a corner lot's street lines (`chain`, in order along the lot) may split into two streets: the indexes k
    with chain[:k] one street and chain[k:] the other. A joint turning more than PARALLEL (30 degrees) is a corner
    for sure; one turning more than JOINT (15) but no more than PARALLEL may be. Between the sure corners, a run of
    pieces each joining within JOINT is one street only while it turns no more than PARALLEL in all (its pieces'
    headings within PARALLEL of each other); a run that turns more (a corner rounded into many short pieces) may
    split at any of its joints. The same limits as the Rhino panel's corner street pick (#15 7a16aa6: joints of 15
    degrees or less, 30 or less in all, one street; over 30 a corner). Every split that may be is a reading; one
    street drawn in pieces is never split mid-street (the frontage of one street, §325-8A col. 7, never two streets
    added)."""
    turns = [_turn(lot.edges[a], lot.edges[b]) for a, b in zip(chain, chain[1:])]
    sure = {k + 1 for k, t in enumerate(turns) if t > PARALLEL}
    maybe = {k + 1 for k, t in enumerate(turns) if JOINT < t <= PARALLEL}
    bounds = [0, *sorted(sure), len(chain)]
    for a, b in zip(bounds, bounds[1:]):
        heads = [_heading(lot.edges[i]) for i in chain[a:b]]
        spread = max((min(abs(x - y) % 360, 360 - abs(x - y) % 360) for x in heads for y in heads), default=0.0)
        if spread > PARALLEL:
            maybe |= set(range(a + 1, b))
    return sorted(sure | maybe)


def _two_sides(found: list) -> list:
    """The two side yards (distance, points, ...), the narrower first. Two within TOL of each other (0.01 ft: the
    same as everywhere else here) are equal, and go in a fixed order by where their lot line is (west, then south,
    first): never by a difference of float noise, so which is "smaller" never depends on how the outlines were
    drawn (stress F11: 8.822476 against 8.82251 ft swapped with the outline order)."""
    a, b = (found * 2)[:2]
    if abs(a[0] - b[0]) > TOL:
        return [a, b] if a[0] < b[0] else [b, a]
    key = lambda f: (round(f[1][0][0], 6), round(f[1][0][1], 6))    # noqa: E731  (the lot-line end of the reading)
    first, second = sorted([a, b], key=key)
    # the lines by position, the values still in order: the smaller side yard is never more than the larger
    # (review round 19; the two differ by at most TOL here)
    low, high = sorted((a[0], b[0]))
    return [(low, *first[1:]), (high, *second[1:])]


def _eaves_by_wall_side(lot: "Lot", r: dict, words: str, w: str, shape, walls: list) -> list:
    """The two side yards to the eaves (`shape`: the building seen from above) under one reading of the lot's lines
    (`r`), each to the lot line of ITS side yard to the walls: [(the narrower's reading, the wider's reading)], one
    pair per way the walls order the sides. The narrower side yard to the eaves is to the side lot line whose side
    yard to the walls is the narrower one (side_yard_smaller's line), the wider to the other, so a side's eaves are
    held to the minimum that side carries (P0, #21 review round 22: walls 9'-6" west and 10'-0" east, eaves 9'-0"
    west and 6'-6" east; sorted on their own, the east eave, 3'-6" into the 10 ft yard R-3a requires there, was
    read against the 5 ft side's limit and passed).

    `walls`: the wall readings (words, shape, named) that go with this eave shape. When they all order the sides
    the same way: one pair, worded as before. When they don't (an overhang read as an eave or not moves a wall
    yard): one pair per wall reading, named and worded as it is, so a rule is checked under each. Two wall side
    yards within TOL of each other are equal (which one is narrower is float noise, _two_sides): then either side
    may be the narrower one, and both pairings are readings (a rule holds only if it holds both ways), each marked
    with its `pairing` (0 as _two_sides orders the lines, 1 swapped), so the checker never sets one pairing's
    narrower side against the other's wider (both eaves to the same lot line: reading_set.combos)."""
    pairs = []
    for ww, ws, wn in walls:
        found = [(*_distance(lot.line(g), ws), list(g)) for g in r["sides"]]
        (_, _, la), (_, _, lb) = _two_sides(found)
        ea = (*_distance(lot.line(la), shape), la)
        eb = (*_distance(lot.line(lb), shape), lb)
        if len(found) == 2 and abs(found[0][0] - found[1][0]) <= TOL:
            pairs += [(ww, wn, ea, eb, 0), (_both(ww, "the walls equally far from both sides: either side the narrower"),
                                            wn, eb, ea, 1)]
        else:
            pairs.append((ww, wn, ea, eb, None))
    if len({(_r(a[0]), _r(b[0])) for _, _, a, b, _ in pairs}) == 1:      # every way gives the same two numbers
        _, _, ea, eb, _ = pairs[0]
        return [((_both(words, w), ea[0], {"points": ea[1], "named": {}, "line": ea[2]}),
                 (_both(words, w), eb[0], {"points": eb[1], "named": {}, "line": eb[2]}))]
    return [((_both(words, ww), ea[0], {"points": ea[1], "named": wn, "line": ea[2], "pairing": k}),
             (_both(words, ww), eb[0], {"points": eb[1], "named": wn, "line": eb[2], "pairing": k}))
            for ww, wn, ea, eb, k in pairs]


def _turn(a, b) -> float:
    """How far the lot outline turns, in degrees (0-180), from one lot line to the next (end to end)."""
    (ax, ay), (bx, by) = _chord(a), _chord(b)
    d = abs(math.degrees(math.atan2(ay, ax) - math.atan2(by, bx))) % 360
    return min(d, 360 - d)


def _width(lot: Lot, facts: dict, lines) -> dict:
    """Lot width: the frontage, the length of the lot line(s) on the street. On a curved street also straight
    across (lot_width's open question). On a corner lot, each street's frontage (which street's frontage is the
    lot width is not settled)."""
    chain = lot.ordered_street()
    groups = [chain]
    if facts.get("corner_lot"):
        groups = [c for c in lines["candidates"]] + [[i for i in chain if i not in c] for c in lines["candidates"]]
        groups = [g for k, g in enumerate(groups) if g and g not in groups[:k]]
    width = []
    for g in groups:
        on = f" (lot line{'s' if len(g) > 1 else ''} {', '.join(lot.label(i) for i in g)})" if len(groups) > 1 else ""
        width.append(("along the street line" + on, lot.length(g), {}))
        if any(lot.curved[i] for i in g):
            ends = [lot.edges[g[0]][0], lot.edges[g[-1]][-1]]
            width.append(("straight across, end to end (chord)" + on, math.dist(ends[0], ends[1]), {}))
    question = ("whether frontage on a curved street is measured along the curve or straight across is an open "
                "question for the architects (lot_width)")
    if len(groups) > 1:
        question += "; which street's frontage is the lot width of a corner lot isn't settled (lot_width)"
    return _decide("lot_width", width, "the length of the lot line(s) on the street (frontage)", [lot.id], question)


def _yards(out: dict, lot: Lot, lines: dict, facts: dict, main: dict, parts_of: list, detached: list, views: dict):
    """The front, side and rear yards, the same yards to the eaves, and the accessory buildings' distances.

    Each yard is measured to the nearest part of the building, its eaves left out: the law (yards_to_nearest_part,
    §325-3 YARD, §325-18A). Solids touching the main building are part of it. Eaves may project up to 2 ft into
    a required yard (§325-18B): the *_eaves measures are the same yards to the building seen from above, eaves
    included, for that rule. Two things a massing model can't show give readings of their own: something below
    the roof that sticks out past the walls at the ground (an upper floor, part of the building; or a bay window,
    a projection), and a solid standing apart that the architect hasn't listed as an accessory building (an
    accessory building, or a freestanding deck, which is part of the building, §325-18A)."""
    rule = law.finding(facts, "yard_projections", "yards_to_nearest_part")
    steps = law.finding(facts, "yard_projections", "steps_count") if parts_of else None
    garage = law.finding(facts, "side_yard", "attached_garage_is_main_building") if parts_of else None
    if rule is None or (parts_of and (steps is None or garage is None)):
        for name in YARDS + EAVE_YARDS + ACCESSORY_YARDS:
            out[name] = _missing(name, stop("law_missing", what="the yard findings (yard_projections, side_yard)"))
        return
    found = [law.basis(f) for f in (rule, steps, garage) if f]
    basis = {k: found + v for k, v in lines["basis"].items()}     # each yard only what applies to it
    listed = facts.get("accessory_buildings") or []
    unlisted = [b for b in detached if not any(i in listed for i in _parts(b))]

    def joined(key):
        # the main building and every solid touching it are one building (§325-18A): each view of it is the same
        # view of every one of them (its walls at ground level, its body, its outline from above), so the yards
        # never depend on which of them is called the main one (property: test_present, touching solids)
        return union([views[b["id"]][key] for b in [main, *parts_of]])
    body, ground, above = joined("body"), joined("ground"), joined("above")
    decks = ops.unary_union([views[b["id"]]["above"] for b in unlisted]) if unlisted else None
    questions = []
    # every yard is to the full outline (everything the solids cover from above). Only where something might be
    # an eave (_eave_candidate suggests it) and the architect hasn't confirmed it, the yard is also read without
    # it: both readings, so it complies only if it does either way, unless the eaves are confirmed
    mine = [views[b["id"]] for b in [main, *parts_of]]
    candidates = [v for v in mine if v["candidate"]]
    eave_candidates = [v["candidate"] for v in candidates]
    if not candidates:
        shapes = [("", above, {})]
    elif all(v["confirmed"] for v in candidates):
        shapes = [("", body, {})]                     # confirmed eaves: the yard is to the building without them
        for b in (_eave_basis(v["confirmed"]) for v in candidates):
            basis = {k: v + [b] for k, v in basis.items()}
    else:
        shapes = [("", above, {EAVE: "not_eave"}),
                  ("what reaches past the walls read as an eave (to be confirmed)", body, {EAVE: "eave"})]
        questions.append(EAVE_QUESTION)
    # what sticks out past the walls at the ground and is neither a Gordium floor block (a story, the law) nor a
    # candidate eave could be an upper floor or a bay window (a projection): both readings
    stories = [p for b in [main, *parts_of] if isinstance(b.get("floor"), list)    # each stack's floor blocks
               for p, is_floor in zip(b.get("plans") or [], b["floor"]) if is_floor]
    known = ops.unary_union([ground] + stories) if stories else ground
    if not ground.is_empty and body.difference(known.buffer(TOL)).area > 1e-6:
        shapes = [(w, s, {**n, PROJ: "part"}) for w, s, n in shapes]
        shapes.append(("to its walls at ground level, what sticks out above being a bay window or other projection",
                       ground, {PROJ: "projection"}))
        questions.append(PROJ_QUESTION)
    eave_shapes = [("", above, {})]
    walls_of = [list(shapes)]       # for each eave shape, the wall readings that say which side is the narrower
    if decks is not None:
        shapes += [(_both(w, "the solids standing apart read as freestanding decks"), s.union(decks), n)
                   for w, s, n in shapes]
        eave_shapes += [("the solids standing apart read as freestanding decks", above.union(decks), {})]
        walls_of.append(shapes[len(walls_of[0]):])
        questions.append("whether a solid standing apart from the main building is an accessory building (§325-25) or "
                         "a freestanding deck (part of the building, §325-18A): list the accessory buildings "
                         "(accessory_buildings)")
    objects = [lot.id, *_parts(main), *[i for b in parts_of for i in _parts(b)]]
    streets = lot.line(lot.street)
    lot_question = lines["question"]
    for suffix, group in (("", shapes), ("_eaves", eave_shapes)):
        q = "; ".join([lot_question] + questions)
        front = [(w, *_distance(streets, s), n) for w, s, n in group]
        out["front_yard" + suffix] = _decide(
            "front_yard" + suffix, [(w, d, {"points": p, "named": n}) for w, d, p, n in front],
            "the least distance from the street lot line(s) to the main building" + (", eaves included" if suffix else ""),
            objects, "; ".join(questions) or q, basis["front"])
        if lines["problem"]:
            for name in ("side_yard_smaller", "side_yard_larger", "rear_yard"):
                out[name + suffix] = _missing(name + suffix, lines["problem"])
            continue
        small, large, rear = [], [], []
        for words, r in lines["readings"]:
            for k, (w, s, n) in enumerate(group):
                if suffix:
                    # the eaves side yards are to the wall side yards' own lot lines (P0, #21 review round 22):
                    # never sorted narrower-first on their own
                    for narrower, wider in _eaves_by_wall_side(lot, r, words, w, s, walls_of[k]):
                        small.append(narrower)
                        large.append(wider)
                else:
                    # each side yard keeps the lot line it was measured to, so one reading (an eave) can be set
                    # against another (not an eave) to the same line, never to the other side's (review round 15)
                    found = [(*_distance(lot.line(g), s), list(g)) for g in r["sides"]]
                    (a, pa, la), (b, pb, lb) = _two_sides(found)
                    small.append((_both(words, w), a, {"points": pa, "named": n, "line": la}))
                    large.append((_both(words, w), b, {"points": pb, "named": n, "line": lb}))
                d, p = _distance(lot.line(r["rear"]), s)
                rear.append((_both(words, w), d, {"points": p, "named": n}))
        eaves = ", eaves included" if suffix else ""
        out["side_yard_smaller" + suffix] = _decide(
            "side_yard_smaller" + suffix, small, "the least distance from the side lot line of the narrower side "
            "yard (to the walls) to the building, eaves included" if suffix else
            "the least distance from the nearer side lot line to the building", objects, q, basis["side"])
        out["side_yard_larger" + suffix] = _decide(
            "side_yard_larger" + suffix, large, "the least distance from the side lot line of the wider side yard "
            "(to the walls) to the building, eaves included" if suffix else
            "the least distance from the farther side lot line to the building", objects, q, basis["side"])
        out["rear_yard" + suffix] = _decide("rear_yard" + suffix, rear,
                                            "the least distance from the rear lot line to the main building" + eaves,
                                            objects, q, basis["rear"])
    for name in YARDS + ("building_height",):
        if name in out:
            out[name]["eave_candidates"] = eave_candidates
    _accessory_yards(out, lot, lines, facts, detached, views)


def _accessory_yards(out: dict, lot: Lot, lines: dict, facts: dict, detached: list, views: dict):
    """Each accessory building's distances (§325-25, the law: accessory_structures_follow_325_25): from the
    street lot line(s) (not in a required front yard; a corner lot has two front yards, §325-25A), the side lot
    lines and the rear lot line, to the nearest one, seen from above."""
    if not detached:
        for name in ACCESSORY_YARDS:
            out[name] = _missing(name, stop("no_accessory"))
        return
    rule = law.finding(facts, "side_yard", "accessory_structures_follow_325_25")
    if rule is None:
        for name in ACCESSORY_YARDS:
            out[name] = _missing(name, stop("law_missing", what="§325-25's finding (side_yard)"))
        return
    shape = ops.unary_union([views[b["id"]]["above"] for b in detached])
    objects = [lot.id, *[i for b in detached for i in _parts(b)]]
    d, p = _distance(lot.line(lot.street), shape)
    out["accessory_front_yard"] = _record("accessory_front_yard", "ft", _r(d),
                                          "the least distance from the street lot line(s) to an accessory building",
                                          objects, p, basis=[law.basis(rule)])
    if lines["problem"]:
        for name in ("accessory_side_yard", "accessory_rear_yard"):
            out[name] = _missing(name, lines["problem"])
        return
    side, rear = [], []
    for words, r in lines["readings"]:
        d, p = min((_distance(lot.line(g), shape) for g in r["sides"]), key=lambda x: x[0])
        side.append((words, d, {"points": p}))
        d, p = _distance(lot.line(r["rear"]), shape)
        rear.append((words, d, {"points": p}))
    out["accessory_side_yard"] = _decide("accessory_side_yard", side, "the least distance from a side lot line to an "
                                         "accessory building", objects, lines["question"], [law.basis(rule)])
    out["accessory_rear_yard"] = _decide("accessory_rear_yard", rear, "the least distance from the rear lot line to "
                                         "an accessory building", objects, lines["question"], [law.basis(rule)])
