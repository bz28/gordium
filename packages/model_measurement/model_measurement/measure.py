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

MEASURES = list(load(MEASURES_FILE))

TOL = 0.01                # ft: two points closer than this are the same point
SAME = 1e-6               # ft: readings closer than this give the same value
PARALLEL = 30             # degrees: street lines turning more than this between them turn a corner
FLAT = math.cos(math.radians(2.39))   # a roof face flatter than 1/2 inch per foot (a drainage slope) is level
MAX_UNCLEAR_EDGES = 6     # more lot lines than this that could be side or rear: too many readings to list
STATED = {"use": "text", "stories": "count", "sleeping_rooms": "count", "parking_spaces": "count",
          "dwelling_units": "count", "rooms_let_for_profit": "count", "conversion": "yes_no"}
ASK = {"use": "no_use", "stories": "no_stories", "sleeping_rooms": "no_rooms", "parking_spaces": "no_rooms",
       "dwelling_units": "no_units", "rooms_let_for_profit": "no_units", "conversion": "no_units"}
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
              **({"line": x["line"]} if x.get("line") is not None else {})} for r, v, x in readings]
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
        return [(", ".join(f"line {i + 1} as a {'rear' if i in rear else 'side'} lot line" for i in varies),
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
        poly = Polygon(shell, holes).buffer(0)
        if poly.area > 1e-9:
            parts.append(poly)
    return ops.unary_union(parts) if parts else Polygon()


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
    return ops.unary_union(polys) if polys else Polygon()


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
    grid = [Point(x0 + (x1 - x0) * (i + 0.5) / n, y0 + (y1 - y0) * (j + 0.5) / n) for i in range(n) for j in range(n)]
    return [p for p in grid if shape.contains(p)] + [shape.representative_point()]


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
        for point in _samples(shape):
            z = _plane_z(f, point.x, point.y)
            above = [_plane_z(flat[j][0], point.x, point.y) for j in index.query(point)
                     if j != i and grown[j].contains(point)]
            if not any(h is not None and h > z + TOL for h in above):
                open_.append(f)
                break
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
    zone = reach.difference(walls.buffer(TOL))
    if others:
        zone = zone.difference(ops.unary_union(others).buffer(TOL))
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


MAX_COMBINATIONS = 200      # more combinations of roof readings than this: too many to list; left for review


def _with_others(main: dict, others: list[dict], main_with: dict | None = None) -> dict:
    """The main building's height read with the other solids: alone, and with every other solid as part of it
    (a wing or tower drawn as its own solid is part of the building; an accessory building may have its own
    limit, §325-25). `main_with` is the main building's height from the grade plane of the whole building (when
    the grade comes from spot grades, the walls of every solid; `others` are measured from it too). Every
    combination of each roof's own readings is listed. A question is named only if two readings that differ in
    that answer alone have different values: each solid's roof question on its own, and the accessory question."""
    unread = [o for o in others if o["value"] is None and not o["readings"]]
    if unread:                          # never dropped: it could be the tallest part
        return _missing("building_height", stop("other_height", reason=unread[0]["reason"]))

    def values(m):
        return [(r["reading"], r["value"], r.get("named") or {}) for r in m["readings"]] or [("", m["value"], {})]

    mine, theirs = values(main), [values(o) for o in others]
    mine_with = {w: v for w, v, _ in values(main_with or main)}
    if len(mine) * math.prod(len(t) for t in theirs) > MAX_COMBINATIONS:
        return _missing("building_height", stop("too_many_roofs"))
    names = [o["objects"][0] for o in others]
    combos = [((w, "alone") + (None,) * len(others), v, n) for w, v, n in mine]
    for w, v, n in mine:          # one answer to each open question holds for every solid: never mixed
        for picks in itertools.product(*theirs):
            named = _merge_named(n, *(pn for _, _, pn in picks))
            if named is not None:
                combos.append(((w, "with") + tuple(lbl for lbl, _, _ in picks),
                               max([mine_with.get(w, v)] + [x for _, x, _ in picks]), named))

    def matters(i):
        same = [k for k in range(len(combos[0][0])) if k != i and not (i == 1 and k >= 2)]
        return any(a[1] != b[1] and a[0][i] != b[0][i] and all(a[0][k] == b[0][k] for k in same)
                   for a in combos for b in combos)

    def roof_questions(m):
        return [q for q in (ROOF_KIND, PITCHED, ABOVE_ROOF) if m["reason"] and q in m["reason"]]

    questions = roof_questions(main) if matters(0) else []
    questions += [ACCESSORY] if matters(1) else []
    for j, o in enumerate(others):
        questions += roof_questions(o) if matters(2 + j) else []
    readings = []
    for choice, v, named in combos:
        words = "the main building only" if choice[1] == "alone" else "with every other solid as part of it" + "".join(
            f"; {n}: {lbl}" for n, lbl in zip(names, choice[2:]) if lbl)
        readings.append((_both(choice[0], words), v, {"named": named} if named else {}))
    basis = list({b["id"]: b for m in [main, *others] for b in m.get("basis") or []}.values())
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


def _pick_main(stacks: list[dict], facts: dict) -> dict | None:
    """The main building: the only one; the one named main_building; or the only one the architect hasn't
    listed as an accessory building (accessory_buildings). Else None: it's asked, never guessed."""
    def named(b, ids):
        return any(i in b.get("parts", [b["id"]]) for i in ids)
    if len(stacks) == 1:
        return stacks[0]
    if facts.get("main_building"):
        return next((b for b in stacks if named(b, [facts["main_building"]])), None)
    rest = [b for b in stacks if not named(b, facts.get("accessory_buildings") or [])]
    if len(rest) == 1 or not rest:
        return rest[0] if rest else None
    # solids that touch are one building (a porch, steps, a wing: part of it, §325-18A): when everything left
    # touches together, the main building is its tallest part (the cautious one for the height), then the largest
    plans = {b["id"]: _projection(b) for b in rest if b.get("faces")}
    if len(plans) != len(rest):
        return None
    if len(_touching(rest[0], rest, plans)) != len(rest) - 1:
        return None
    return max(rest, key=lambda b: (max(p[2] for f in b["faces"] for p in f["points"]), plans[b["id"]].area))


def grade_plane(buildings: list[dict], facts: dict) -> tuple:
    """(grade, None) or (None, reason): the grade plane from the spot grades in `facts`, at the main building's own
    walls (§325-3 GRADE PLANE: "on each side of the building"). The main building is the one stack of floor
    blocks, or the one named main_building; with several and none named, it's a question, as for the height."""
    stacks = _stacks(buildings)
    main = _pick_main(stacks, facts)
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
    outline = ops.unary_union(plans)
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
        out = _measure(site, facts)
    finally:
        _SKY.clear()
        _PLANES.clear()
        _PLAN_OF.clear()
    return {name: out[name] for name in MEASURES}


def _measure(site: dict, facts: dict) -> dict[str, dict]:
    out = {}
    for name, unit in STATED.items():
        v = facts.get(name)
        out[name] = (_record(name, unit, v, "stated by the architect (not measured from the model)")
                     if v is not None else _record(name, unit, reason=stop(ASK[name])))
    # the lot's zoning district is the zone the architect stated (the facts' "zone")
    out["district"] = (_record("district", "text", facts["zone"], "stated by the architect (the lot's zone)")
                       if facts.get("zone") else _record("district", "text", reason=stop("no_district")))
    buildings = site.get("buildings") or []
    grade = facts.get("grade_elevation")
    # objects are told apart by id below (spans, outlines): two with one id would leave one out silently
    ids = [b["id"] for b in buildings]
    same = sorted({i for i in ids if ids.count(i) > 1}, key=str)
    why_building = (stop("no_building") if not buildings else
                    "; ".join([p for b in buildings for p in b.get("problems") or []]
                              + [stop("same_id", id=i) for i in same]) or None)
    # the ground must meet the buildings, taken together (stacked floors, a basement or a tower drawn as its own
    # solid sit above or below it): at or above their lowest point and below their top. A level outside that (a
    # survey elevation typed for a model drawn at z = 0) would give a negative or inflated height, and an empty
    # cut at the ground blamed on overhangs.
    why_spots = None
    if facts.get("grade_points"):       # spot grades (or terrain sampled at the walls): the grade plane from them
        grade, why_spots = grade_plane(buildings, facts)
    zs = [p[2] for b in buildings for f in b.get("faces") or [] for p in f["points"]]
    lo, hi = (min(zs), max(zs)) if zs else (None, None)
    off = (lo, hi) if zs and grade is not None and (grade < lo - TOL or hi - lo > TOL and grade >= hi - TOL) else None
    # a solid wholly under the ground is a basement only if it is joined directly under the building: its top
    # meets the bottom of a solid above it (the building, or a basement already joined to it) and it lies within
    # that solid's plan. Any other (left at z = 0 when the rest was moved to a survey level, or a part left at its
    # old level) can't be told from a mistake, and its height (below zero) would drop out of every reading unseen.
    buried = None
    if grade is not None and not off:
        spans = {b["id"]: (min(p[2] for f in b["faces"] for p in f["points"]),
                           max(p[2] for f in b["faces"] for p in f["points"])) for b in buildings if b.get("faces")}
        plans = {b["id"]: _projection(b) for b in buildings if b["id"] in spans}
        joined = {i for i, (lo_, hi_) in spans.items() if hi_ > grade + TOL or hi_ - lo_ <= TOL}   # above, or a slab
        waiting = [i for i in spans if i not in joined]
        while True:                     # from the top down: a sub-basement joins under a joined basement
            found = [i for i in waiting
                     if ops.unary_union([plans[j] for j in joined if abs(spans[j][0] - spans[i][1]) <= TOL])
                     .buffer(TOL).contains(plans[i])]
            if not found:
                break
            joined |= set(found)
            waiting = [i for i in waiting if i not in found]
        buried = spans[waiting[0]] if waiting else None
    why_grade = (why_spots if why_spots else stop("no_ground") if grade is None else
                 stop("ground_off_building", ground=_r(grade), bottom=_r(off[0]), top=_r(off[1])) if off else
                 stop("buried_solid", ground=_r(grade), bottom=_r(buried[0]), top=_r(buried[1])) if buried else
                 None if facts.get("grade_points") else
                 stop("ground_unknown") if facts.get("ground_is_flat") is None else
                 None if facts["ground_is_flat"] else stop("sloped_ground"))
    # the grade decides height and stories. The plan (yards, building area) only needs the level where the building
    # meets the ground: with no grade (not given, not known to be flat, spot grades off the walls) that is the
    # building's own base, so the plan is still measured; a grade that contradicts the building (off it, a solid
    # buried under it) still stops the plan, since then even the base can't be trusted.
    why_plan = (stop("ground_off_building", ground=_r(grade), bottom=_r(off[0]), top=_r(off[1])) if off else
                stop("buried_solid", ground=_r(grade), bottom=_r(buried[0]), top=_r(buried[1])) if buried else None)
    plan_level = grade if (grade is not None and not why_grade) else lo
    # stacked floor blocks (each story its own solid, standing on the one below, as Gordium's starting building is
    # drawn) are one building, and its stories are counted from them: read from the shape, never typed
    buildings = _stacks(buildings)
    main = _pick_main(buildings, facts)      # the one main-building pick
    why_main = None if main else stop("no_main_building")
    # One decision for every building measurement: which building, and can it be measured (why_which). Stories
    # follow the rule of the fact model: a typed count is a stated fact and stands only when nothing drawn could be
    # counted (no building, or a main building that is one plain solid). Whenever the drawing can produce a count
    # (floor blocks or stacked solids on any building; or building objects with a problem, which might be either),
    # the stories come from the drawing, with the typed count as a cross-check reading, and every stop that
    # applies to the height applies to them identically (the grade is checked inside _stories).
    why_which = why_building or why_main
    countable = any(b.get("parts") for b in buildings) or bool(why_building and site.get("buildings"))
    # solids touching the main building are one building with it (§325-18A): its stories are the whole joined
    # building's, never one part's (review rounds 14-16; #14's _stories_over will take this rule's place)
    joined = [b for b in (_attached(main, buildings) if main is not None and not why_which else [])
              if b.get("parts") or _rise(b) >= STORY_ROOM]
    if countable and why_which:
        out["stories"] = _missing("stories", why_which)
    elif joined:
        out["stories"] = _stories_whole([main] + joined, grade, why_grade, facts.get("stories"))
    elif main is not None and main.get("parts"):
        out["stories"] = _stories(main, grade, why_grade, facts.get("stories"))
    why = why_which or why_grade
    out["building_height"] = _missing("building_height", why) if why else _height(main, grade, facts)
    others = [b for b in buildings if b is not main]
    if not why and others and (out["building_height"]["value"] is not None or out["building_height"]["readings"]):
        # read with the other solids as part of the building, the grade plane is the ground at the walls of all of
        # them (§325-3: "each side of the building"), not the main building's alone: a wing on lower ground
        # lowers it. Spot grades that don't reach those walls leave that reading, and so the height, unknown.
        with_grade, why_with = (_grade_from_points([main] + others, facts["grade_points"])
                                if facts.get("grade_points") else (grade, None))
        out["building_height"] = (_missing("building_height", stop("grade_with_others")) if why_with else
                                  _with_others(out["building_height"], [_height(b, with_grade, facts) for b in others],
                                               _height(main, with_grade, facts)))
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

    views = ({b["id"]: _views(b, plan_level, facts) for b in buildings} if plan_level is not None and not why_building
             else {})
    # each building on its own (each stack, each detached building): one wholly off the lot can't be measured
    # against it (outside_lot, whatever the others do); one that crosses a lot line is measured, and the yard to
    # its own crossings are recorded (_mark_crossings): it fails every rule that measures it, never a pass
    # one rule for each building on its own (each stack, each detached building), whatever the others are:
    # within the lot: measured as usual; partly outside: every rule that measures it does not comply
    # (_mark_crossings, naming the lines it crosses where they can be told); wholly outside: the rules that would
    # measure it need review (outside_lot: is it part of this design?)
    place = {}
    for b in buildings:
        p = _projection(b)
        place[b["id"]] = ("on" if p.within(lot.polygon.buffer(TOL)) else
                          "off" if p.intersection(lot.polygon).area <= 1e-6 else "partly")
    crossed = {i: _crossed(lot, _projection(next(b for b in buildings if b["id"] == i)))
               for i, s in place.items() if s == "partly"}
    crosses = bool(crossed)
    group = [main, *parts_of] if main is not None else []
    why_main_off = stop("outside_lot") if any(place.get(b["id"]) == "off" for b in group) else None
    why_acc_off = stop("outside_lot") if any(place.get(b["id"]) == "off" for b in detached) else None
    why_inside = why_building or (stop("outside_lot") if "off" in place.values() else None)    # coverage
    if why_inside or why_plan or plan_level is None:
        out["building_area"] = _missing("building_area", why_inside or why_plan or why_grade)
    else:
        out["building_area"] = _coverage(buildings, views, facts, main)
    if crosses:                         # coverage, the height and the accessory count: whatever else follows
        _mark_crossings(out, lot, lines, crossed, main, parts_of, detached)

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
    why_yards = why_building or why_main_off or why_rest
    if why_yards:
        for name in YARDS + EAVE_YARDS + ACCESSORY_YARDS:
            out[name] = _missing(name, why_yards)
        if why_main_off and not why_rest and not why_acc_off and detached:
            # only the main building is off the lot: an accessory building on it is still measured on its own
            _accessory_yards(out, lot, lines, facts, detached, views)
        return out
    _yards(out, lot, lines, facts, main, parts_of, detached, views)
    if why_acc_off:                              # an accessory building wholly off the lot: its own rule waits
        for name in ACCESSORY_YARDS:
            out[name] = _missing(name, why_acc_off)
    if crosses:
        _mark_crossings(out, lot, lines, crossed, main, parts_of, detached)
    return out


def _crossed(lot: Lot, plan) -> set:
    """The lot lines (by index) one building crosses: those its part outside the lot runs along."""
    outside = plan.difference(lot.polygon.buffer(TOL))
    if outside.area <= 1e-6:
        return set()
    reach = outside.buffer(2 * TOL)
    return {i for i, e in enumerate(lot.edges) if reach.intersection(LineString(e)).length > 4 * TOL}


def _mark_crossings(out: dict, lot: Lot, lines: dict, crossed: dict, main: dict, parts_of: list, detached: list):
    """A building that crosses a lot line stands partly on another lot: it fails every rule that measures it,
    whatever the readings or answers (the checker does that, check.crossing). Each measurement of a building
    records that building's own crossings, `crossings`: [{"who", "lines": street / side / rear}]: the main
    building's on the main yards, the eaves and the height; each accessory building's on the accessory
    measurements; every building's on the coverage."""
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
    if (entries_main or entries_acc) and "building_area" in out:
        out["building_area"]["crossings"] = entries_main + entries_acc


STORY_ROOM = 8.0     # ft: a plain solid this tall could hold a story (a porch slab or steps don't)


def _rise(b: dict) -> float:
    zs = [p[2] for f in b.get("faces") or [] for p in f["points"]]
    return max(zs) - min(zs) if zs else 0.0


def _stories_whole(parts: list[dict], grade, why_grade, stated) -> dict:
    """STORY for a building of several joined parts (§325-18A; the main building first), by one rule: stories are
    counted only from Gordium's floor blocks. A part that isn't floor blocks and could hold a story (STORY_ROOM or
    more) can't be counted, so the count typed stands as the architect's statement for the whole building, and
    only if it is at least the floors counted; else it needs review. A part below the ground is the §325-3
    basement question: needs review. Each reason says what is drawn."""
    ids = [i for b in parts for i in b.get("parts") or [b["id"]]]
    if why_grade:
        return _record("stories", "count", reason=why_grade)
    plain = [b for b in parts if not (b.get("parts") and any(b.get("floor") or []))]
    low = [b for b in plain if min(p[2] for f in b["faces"] for p in f["points"]) < grade - TOL]
    if low:
        return _record("stories", "count", reason=stop("basement_part", what=", ".join(b["id"] for b in low)))
    counts = []
    for stack in (b for b in parts if b not in plain):
        got = _stories(stack, grade, None, None)
        if got["value"] is None:        # its own reason: a floor block below the ground, misaligned, a bulkhead
            return got
        counts.append(int(got["value"]))
    counted = max(counts) if counts else None
    if not plain:
        readings = [("Gordium's floor blocks, the most on any part", counted, {})]
        if stated is not None:
            readings.append(("as stated by the architect", stated, {}))
        return _decide("stories", readings, "the floor blocks of the building counted (the most on any of its "
                       "joined parts)", ids, "the count typed disagrees with the floors drawn: a question (story)")
    for stack in (b for b in plain if b.get("parts")):
        # plain solids stacked one on another: the count typed against every stacked block a story, as for a
        # building on its own (a question when they disagree, never the typed count over the blocks drawn)
        got = _stories(stack, grade, None, stated)
        if got["value"] is None:
            return got
    what = ", ".join(b["id"] for b in plain)
    if stated is None:
        return _record("stories", "count", reason=stop("stories_plain_part", what=what))
    if counted is not None and stated < counted:
        return _record("stories", "count", reason=stop("stories_below_floors", typed=stated, drawn=counted))
    return _record("stories", "count", stated, "stated by the architect for the whole building (part of it isn't "
                   "drawn as floor blocks" + (f"; at least the {counted} floor blocks drawn" if counted else "") + ")",
                   ids)


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


def _views(building: dict, level: float, facts: dict) -> dict:
    """A building as the yards and coverage see it: `above`, the full outline, everything its solids cover seen
    from above (what every yard and coverage is measured to); `body`, the same without the candidate eaves
    (_eave_candidate: a suggestion only); `ground`, its walls at ground level; `candidate`, the candidate's
    fingerprint (None if there is none); `confirmed`, the architect's confirmation that it is eaves, if any."""
    above = _projection(building)
    candidate = _eave_candidate(building) if building.get("faces") else None
    zone = candidate["zone"] if candidate else None
    # the zone starts TOL past the walls; grown back by TOL (square corners) it meets them exactly
    body = above.difference(zone.buffer(TOL, join_style=2)) if zone is not None else above
    if body.is_empty:
        body = above
    has = above.difference(body.buffer(TOL)).area > 1e-6
    return {"above": above, "body": body, "ground": _section(building, level + TOL),
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
            idx = [i for i in chain if any(_same_point(lot.edges[i][0], a) and _same_point(lot.edges[i][-1], b) or
                                           _same_point(lot.edges[i][0], b) and _same_point(lot.edges[i][-1], a)
                                           for a, b in given)]
            if len(idx) != len(given) or not lot._contiguous(idx):
                return stop("address_not_a_street")
            candidates = [idx]
        else:
            candidates = [c for k in range(1, len(chain)) for c in (chain[:k], chain[k:])]
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
                         f"{', '.join(str(i + 1) for i in address)}") if len(candidates) > 1 else ""
                found.append((_both(where, words), {"left": left, "right": right, "sides": sides, "rear": rear,
                                                    "address": address}))
    # a reading the law excludes (its rear on a street, or no side line left) is dropped; if none is left, the
    # first reason says why. An address with too many lines stopped above (review round 9)
    problem = None if found else (problems[0] if problems else stop("no_rear_line"))
    return {"readings": found, "question": "; ".join(question), "basis": basis, "problem": problem,
            "candidates": candidates}


def _side_order(found) -> tuple:
    """The two side yards, the narrower first; two equal ones (within SAME) in a fixed order by where their lot line
    is (west, then south, first), so which is "smaller" never depends on the order the outlines were drawn in."""
    d, points = found
    (x, y), _ = points
    return (round(d / SAME) * SAME if SAME else d, round(x, 6), round(y, 6))


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
        on = f" (lot line{'s' if len(g) > 1 else ''} {', '.join(str(i + 1) for i in g)})" if len(groups) > 1 else ""
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
        return ops.unary_union([views[main["id"]][key]] + [views[b["id"]]["above"] for b in parts_of])
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
    stories = ([p for p, is_floor in zip(main.get("plans") or [], main["floor"]) if is_floor]
               if isinstance(main.get("floor"), list) else [])           # a stack's parts: which are floor blocks
    known = ops.unary_union([ground] + stories) if stories else ground
    if not ground.is_empty and body.difference(known.buffer(TOL)).area > 1e-6:
        shapes = [(w, s, {**n, PROJ: "part"}) for w, s, n in shapes]
        shapes.append(("to its walls at ground level, what sticks out above being a bay window or other projection",
                       ground, {PROJ: "projection"}))
        questions.append(PROJ_QUESTION)
    eave_shapes = [("", above, {})]
    if decks is not None:
        shapes += [(_both(w, "the solids standing apart read as freestanding decks"), s.union(decks), n)
                   for w, s, n in shapes]
        eave_shapes += [("the solids standing apart read as freestanding decks", above.union(decks), {})]
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
            for w, s, n in group:
                # each side yard keeps the lot line it was measured to, so one reading (an eave) can be set
                # against another (not an eave) to the same line, never to the other side's (review round 15)
                found = [(*_distance(lot.line(g), s), list(g)) for g in r["sides"]]
                (a, pa, la), (b, pb, lb) = sorted((found * 2)[:2], key=lambda f: _side_order(f[:2]))
                small.append((_both(words, w), a, {"points": pa, "named": n, "line": la}))
                large.append((_both(words, w), b, {"points": pb, "named": n, "line": lb}))
                d, p = _distance(lot.line(r["rear"]), s)
                rear.append((_both(words, w), d, {"points": p, "named": n}))
        eaves = ", eaves included" if suffix else ""
        out["side_yard_smaller" + suffix] = _decide("side_yard_smaller" + suffix, small,
                                                    "the least distance from the nearer side lot line to the building"
                                                    + eaves, objects, q, basis["side"])
        out["side_yard_larger" + suffix] = _decide("side_yard_larger" + suffix, large,
                                                   "the least distance from the farther side lot line to the building"
                                                   + eaves, objects, q, basis["side"])
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
