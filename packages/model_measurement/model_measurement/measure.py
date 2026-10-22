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

import itertools
import math

import numpy as np

import shapely
from shapely import STRtree, ops
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.validation import explain_validity

from rule_format.rulebook import MEASURES_FILE, load

from .stops import stop
from .street_lines import street_verdict

MEASURES = list(load(MEASURES_FILE))

TOL = 0.01                # ft: two points closer than this are the same point
SAME = 1e-6               # ft: readings closer than this give the same value
PARALLEL, PERPENDICULAR = 30, 60   # degrees from the street: clearly a rear line / clearly a side line
FLAT = math.cos(math.radians(2.39))   # a roof face flatter than 1/2 inch per foot (a drainage slope) is level
MAX_UNCLEAR_EDGES = 4     # more lot lines than this of unclear kind: too many readings to list
STATED = {"use": "text", "stories": "count", "sleeping_rooms": "count", "parking_spaces": "count"}
ASK = {"use": "no_use", "stories": "no_stories", "sleeping_rooms": "no_rooms", "parking_spaces": "no_rooms"}
UNITS = {"lot_area": "sf", "lot_width": "ft", "lot_depth": "ft", "building_area": "sf", "building_height": "ft",
         "front_yard": "ft", "side_yard_smaller": "ft", "side_yard_larger": "ft", "rear_yard": "ft"}


def _r(x: float) -> float:
    return round(x, 6) + 0.0          # drops float noise (and -0.0); never rounds toward a limit by more than 1e-6


def _record(definition, unit, value=None, how="", objects=(), points=None, readings=(), reason=None) -> dict:
    return {"value": value, "unit": unit, "how": how, "definition": definition, "objects": list(objects),
            "points": points, "readings": list(readings), "reason": reason}


def _missing(name: str, reason: str) -> dict:
    return _record(name, UNITS.get(name) or STATED[name], reason=reason)


def _decide(name: str, readings: list[tuple[str, float, dict]], how: str, objects, question: str) -> dict:
    """One value if every reading gives the same number; else None, with the readings and the question."""
    values = [v for _, v, _ in readings]
    shown = [{"reading": r, "value": _r(v), **({"points": x["points"]} if x.get("points") else {})}
             for r, v, x in readings]
    if values and max(values) - min(values) <= SAME:
        how = how if len(readings) > 1 or not readings[0][0] else f"{how} ({readings[0][0]})"
        return _record(name, UNITS.get(name) or STATED[name], _r(values[0]), how, objects, readings[0][2].get("points"),
                       shown if len(readings) > 1 else [])
    # no value, but where it was measured is still known: the line of the smallest reading (for a yard, the
    # cautious one), so the panel can name the side and the viewport can draw it
    least = min(readings, key=lambda r: r[1])[2].get("points")
    return _record(name, UNITS.get(name) or STATED[name], None, how, objects, least, shown,
                   stop("readings_differ", question=question))


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
        elif facts.get("corner_lot") is not True:
            # lot width is frontage on ONE public right-of-way (§325-8, Column 7: street_lines): street lines on two
            # streets, or of no known street swinging more than TURN_LIMIT_DEG in all (a corner, even rounded into
            # short pieces), are never measured along both (review rounds 5 and 6, P0); a street that bends is
            # asked about, never called two
            ids = facts.get("street_ids")
            stale = ids is not None and not (isinstance(ids, list) and len(ids) == len(facts["street_line"]) and
                                             all(i is None or isinstance(i, str) for i in ids))
            # names that don't match the lines (saved before the lines changed): set aside, never used, and said
            # (review round 7, P1: they made the whole check fail)
            verdict, turn = ("stale", None) if stale else self.street_verdict(facts)
            if verdict == "stale":
                self.street_problem = stop("street_names_stale")
            elif verdict == "two":
                self.street_problem = stop("two_streets")
            elif verdict == "unsure":
                self.street_problem = stop("one_street_or_two", turn=round(turn or 0))

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
        (description, left side edges, right side edges, rear edges). Lines next to the street lines and
        about square to the street are side lines; lines not next to it and about parallel are rear lines;
        any other line could be either, so both are tried."""
        n, chain = len(self.edges), self.ordered_street()
        front = _chord([p for i in chain for p in (self.edges[i][0], self.edges[i][-1])])
        rest = [(chain[-1] + k) % n for k in range(1, n - len(chain) + 1)]     # from the street's end, around
        ends = {rest[0], rest[-1]}
        kinds = {}
        for i in rest:
            a = _angle(_chord(self.edges[i]), front)
            if i in ends and a >= PERPENDICULAR:
                kinds[i] = ("side",)
            elif i not in ends and a <= PARALLEL:
                kinds[i] = ("rear",)
            else:
                kinds[i] = ("side", "rear")
        unclear = [i for i in rest if len(kinds[i]) == 2]
        if len(unclear) > MAX_UNCLEAR_EDGES:
            return None
        found = []
        for choice in itertools.product(*(kinds[i] for i in rest)):
            k = dict(zip(rest, choice))
            # side lines run from each end of the street lines; the rear lines are what is left between them
            right = list(itertools.takewhile(lambda i: k[i] == "side", rest))
            left = list(itertools.takewhile(lambda i: k[i] == "side", reversed(rest)))
            rear = [i for i in rest if i not in right and i not in left]
            if not right or not left or not rear or any(k[i] != "rear" for i in rear):
                continue
            words = ", ".join(f"line {i + 1} as a {k[i]} lot line" for i in unclear)
            found.append((words, left, right, rear))
        return found


# ---- buildings -------------------------------------------------------------------------------------------

def _projection(building: dict):
    """The building seen from above: the union of its faces projected flat (vertical faces add nothing)."""
    parts = []
    for f in building["faces"]:
        shell = [tuple(p[:2]) for p in f["points"]]
        holes = [[tuple(p[:2]) for p in h] for h in f.get("holes") or []]
        poly = Polygon(shell, holes).buffer(0)
        if poly.area > 1e-9:
            parts.append(poly)
    return ops.unary_union(parts) if parts else Polygon()


def _cut_level(building: dict, buildings: list[dict], plan_level: float) -> float:
    """The level a building is cut at to read it at the ground: the higher of the grade plane and the lowest bottom
    of its connected group (_connected, the one grouping), never its own alone."""
    group = next((g for g in _connected(buildings) if any(b is building for b in g)), [building])
    return max(plan_level, min(_bottom(b) for b in group if b.get("faces")))


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


PITCHED = "the average height of a pitched roof is an open question for the architects (height_of_building)"
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


def _planes(faces: list[dict], work: dict | None = None) -> list[list[dict]]:
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


def _open_to_the_sky(faces: list[dict]) -> list[dict]:
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


def _height(building: dict, grade: float) -> dict:
    """HEIGHT OF BUILDING: from the grade plane "to the highest level of a flat or mansard roof or to the average
    height of a pitched ... roof", using "that section of the roof that has the highest elevation". The roof is
    the faces open to the sky. If its largest roof plane seen from above (the main roof; a meshed roof's faces
    count together) doesn't reach the top, something smaller rises
    above it (a parapet, chimney, bulkhead or a higher part): the roof is read both without it and with it, each
    the same way, and whether it counts is an open question."""
    zs = [p[2] for f in building["faces"] for p in f["points"]]
    top = max(zs)
    bottom = min(zs)
    roof = [f for f in _open_to_the_sky(building["faces"]) if not all(abs(p[2] - bottom) <= TOL for p in f["points"])]
    if not roof:
        return _missing("building_height", stop("no_roof"))
    how = "from the ground level (grade plane) to the top of the roof"
    # the main roof: the largest roof plane seen from above (its faces together, so a meshed roof counts whole)
    main_roof = max(_planes(roof), key=lambda g: (ops.unary_union([_plan(f) for f in g]).area,
                                                  max(p[2] for f in g for p in f["points"])))
    roof_top = max(p[2] for f in main_roof for p in f["points"])
    if roof_top >= top - TOL:
        readings, question = _roof_readings(roof, top, grade)
        return _decide("building_height", readings, how, _parts(building), question)
    below = [f for f in roof if all(p[2] <= roof_top + TOL for p in f["points"])]
    low, low_question = _roof_readings(below, roof_top, grade)
    high, high_question = _roof_readings(roof, top, grade)
    readings = [(_both("leaving out what rises above the main roof", w), v, x) for w, v, x in low]
    readings += [(_both("including what rises above the main roof", w), v, x) for w, v, x in high]
    return _decide("building_height", readings, how, _parts(building),
                   "; ".join(dict.fromkeys(q for q in (ABOVE_ROOF, low_question, high_question) if q)))


def _roof_readings(roof: list[dict], top: float, grade: float) -> tuple[list, str]:
    """The readings of a roof whose highest point is `top`, and the open question they leave ("" if none). Its
    highest section is the faces that reach the top: all level (or within a drainage slope of level), a flat
    roof to its highest level; all sloped, a pitched roof (midway between that section's eave and the ridge, or
    the ridge); both, a mansard (to its highest level) or a pitched or hip roof with a deck or ridge strip."""
    # by plane, so a meshed roof is read like one drawn with whole faces
    highest = [g for g in _planes(roof) if any(abs(p[2] - top) <= TOL for f in g for p in f["points"])]
    sloped = [g for g in highest if _normal_z(g[0]["points"]) < FLAT]
    if not sloped:
        return [("a flat roof, to its highest level", top - grade, {})], ""
    eave = min(p[2] for g in sloped for f in g for p in f["points"])
    readings = [("pitched: midway between eave and ridge", (eave + top) / 2 - grade, {}),
                ("pitched: to the ridge", top - grade, {})]
    if len(sloped) < len(highest):            # a level part at the top too
        return [("mansard: to its highest level", top - grade, {})] + readings, _both(ROOF_KIND, PITCHED)
    return readings, PITCHED


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


def _with_others(main: dict, others: list[dict], assemblies, main_with: dict | None = None) -> dict:
    """The main building's height read over the candidate buildings (_assemblies, the same list the stories are
    read over: alone, and with every other solid as part of it; a wing or tower drawn as its own solid is part of
    the building, an accessory building may have its own limit, §325-25), labelled with the assemblies' own words.
    `main` and `others` are the height records of the first assembly's building and of the others in the second.
    `main_with` is the main building's height from the grade plane of the whole building (when the grade comes from
    spot grades, the walls of every solid; `others` are measured from it too). Every combination of each roof's own
    readings is listed. A question is named only if two readings that differ in that answer alone have different
    values: each solid's roof question on its own, and the accessory question."""
    alone_words, with_words = _kind(assemblies, "main_only")["words"], _kind(assemblies, "with_others")["words"]
    unread = [o for o in others if o["value"] is None and not o["readings"]]
    if unread:                          # never dropped: it could be the tallest part
        return _missing("building_height", stop("other_height", reason=unread[0]["reason"]))

    def values(m):
        return [(r["reading"], r["value"]) for r in m["readings"]] or [("", m["value"])]

    mine, theirs = values(main), [values(o) for o in others]
    mine_with = dict(values(main_with or main))
    if len(mine) * math.prod(len(t) for t in theirs) > MAX_COMBINATIONS:
        return _missing("building_height", stop("too_many_roofs"))
    names = [o["objects"][0] for o in others]
    combos = [((w, "alone") + (None,) * len(others), v) for w, v in mine]
    combos += [((w, "with") + tuple(lbl for lbl, _ in picks), max([mine_with.get(w, v)] + [x for _, x in picks]))
               for w, v in mine for picks in itertools.product(*theirs)]

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
    for choice, v in combos:
        words = alone_words if choice[1] == "alone" else with_words + "".join(
            f"; {n}: {lbl}" for n, lbl in zip(names, choice[2:]) if lbl)
        readings.append((_both(choice[0], words), v, {}))
    return _decide("building_height", readings, main["how"], main["objects"] + names,
                   "; ".join(dict.fromkeys(questions)))


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
    """The candidate buildings the height is read over (_with_others), for every building measurement read from
    the drawing: the main building only, and, with other solids drawn, the main building with every other solid as
    part of it (a wing drawn as its own solid is part of the building; an accessory building isn't, §325-25). With
    the main building assumed (pick_main), each other building alone too, as if it were the main one: the pick
    the architect may make, so the assumption never gives a pass that pick wouldn't.
    Each is a labelled record {kind, words, members} (kind main_only, with_others, or as_main with `of`, the
    building's id), looked up by kind everywhere (_kind), never by position. Only a building that could be a
    principal one (_could_be_principal) is read as the main one."""
    out = [{"kind": "main_only", "words": "the main building only", "members": [main]}]
    if others:
        out.append({"kind": "with_others", "words": "with every other solid as part of it",
                    "members": [main] + list(others)})
    if assumed:
        out += [{"kind": "as_main", "of": _parts(b)[0], "words": MAIN_IF.format(_parts(b)[0]), "members": [b]}
                for b in others if _could_be_principal(b)]
    return out


def _with_each_as_main(record: dict, candidates: list[dict]) -> dict:
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
        h = _height(b, g) if not why else _missing("building_height", why)
        if h["value"] is None and not h["readings"]:
            return _missing("building_height", h["reason"])
        readings += [(_both(words, r["reading"]), r["value"], {}) for r in h["readings"]] or [(words, h["value"], {})]
        objects += _parts(b)
    question = "; ".join(q for q in [record.get("reason") and record["reason"].split("; ", 1)[-1], MAIN_QUESTION] if q)
    return _decide("building_height", readings, record.get("how") or "", list(dict.fromkeys(objects)), question)


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
            return _missing("stories", stop("stories_below_floors", typed=f"{stated:g}", drawn=counted))
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
            return _missing("stories", stop("stories_below_floors", typed=f"{stated:g}", drawn=counted))
        if stated > most:
            return _missing("stories", stop("stories_above_drawn", typed=f"{stated:g}", what=name,
                                            height=f"{_r(_rise(tallest)):g}", most=most))
        if stated < least:              # (no floor blocks drawn: fewer than the first story every building has)
            return _missing("stories", stop("stories_below_one", typed=f"{stated:g}"))
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


def _ground_against(solids: list[dict], grade, off_check: bool = True) -> str | None:
    """What is wrong with this ground level against these solids, or None: the ground must meet them, taken
    together (stacked floors, a basement or a tower drawn as its own solid sit above or below it), at or above their
    lowest point and below their top; and a solid wholly under the ground is a basement only if it is joined
    directly under the building. Checked for the whole site, and again for each candidate building at its own
    grade (_candidate_grades). With spot grades, whether the ground meets them is _floating's, at the footprint
    (off_check False): one test, whatever the spot grades' positions."""
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
    if off:
        return stop("ground_off_building", ground=_r(grade), bottom=_r(off[0]), top=_r(off[1]))
    if buried:
        return stop("buried_solid", ground=_r(grade), bottom=_r(buried[0]), top=_r(buried[1]))
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
                        (_ground_against(members, g, off_check=not spots) if g is not None else None)))
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
                 "lot_width": 2 * TAX_MAP_TOLERANCE, "lot_depth": 2 * TAX_MAP_TOLERANCE}


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
        (_ground_against(buildings, grade, off_check=False) if buildings and grade is not None else None)
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
                return stop("open_solid")
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
    return stop("open_solid")


def _connected(buildings: list[dict]) -> list[list[dict]]:
    """The buildings as connected groups: touching in plan (a balcony or a wing against the house's side) or one
    over another (as _stacks and _one_vertical_building join them). One helper, for the ground test."""
    groups = []
    for b in buildings:
        plan = _footprint(b) if b.get("faces") or b.get("plans") else None
        joined = [g for g in groups if plan is not None and any(
            (o.get("faces") or o.get("plans")) and _footprint(o).distance(plan) <= TOL for o in g)]
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
    near = [_projection(b) for b in others if b.get("faces")]
    if near:
        mine = ops.unary_union([_projection(b) for b in buildings if b.get("faces")])
        theirs = ops.unary_union(near)
        points = [p for p in points if not (theirs.distance(Point(p[:2])) <= SPOT_REACH
                                            and mine.distance(Point(p[:2])) > SPOT_REACH)]
        if not points:                  # every point is another building's ground: none for this one
            return stop("ground_unclear")
    if not zs or not points or not corners:
        return None
    pts = np.array([p[:3] for p in points], dtype=float)
    xy = pts[:, :2] - pts[:, :2].mean(axis=0)
    fits = len(pts) >= 3 and np.linalg.matrix_rank(xy) == 2 and np.linalg.cond(xy) < 30   # not near a line
    if fits:
        coef, *_ = np.linalg.lstsq(np.c_[pts[:, :2], np.ones(len(pts))], pts[:, 2], rcond=None)
        lo_z, hi_z = float(pts[:, 2].min()), float(pts[:, 2].max())     # never beyond the levels measured
        ground = [min(max(coef[0] * x + coef[1] * y + coef[2], lo_z), hi_z) for x, y in corners]
    else:                               # too few or in a line: the nearest spot grade at each corner
        ground = [pts[int(np.argmin(((pts[:, :2] - (x, y)) ** 2).sum(axis=1))), 2] for x, y in corners]
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
    out = _measure(site, facts)
    assumed = out.pop("_assumed_main", None)
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
    starting = [b for b in buildings if b.get("parts") and all(b["floor"])]
    return (starting[0], True) if len(starting) == 1 else (None, False)


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
    main = (buildings[0] if len(buildings) == 1 else
            next((b for b in buildings if b["id"] == facts.get("main_building")), None))
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
    ground_problem = (_meets_ground(stacked, spots, stacked) if spots else None) or \
        (_ground_against(buildings, grade, off_check=not spots) if grade is not None else None)
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
    plan_level = grade if (grade is not None and not why_grade) else lo
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
    out["building_height"] = _missing("building_height", why) if why else _height(main, grade)
    if not why and others and (out["building_height"]["value"] is not None or out["building_height"]["readings"]):
        # read with the other solids as part of the building, the grade plane is the ground at the walls of all of
        # them (§325-3: "each side of the building"), not the main building's alone: a wing on lower ground
        # lowers it. Spot grades that don't reach those walls leave that reading, and so the height, unknown.
        # (the candidate's own grade plane, _candidate_grades: the one the stories read too)
        why_g = next((c["why"] for c in candidates if c["why"]), None)    # a candidate's ground that can't be used
        with_grade = _kind(candidates, "with_others")["grade"]       # by its label, never its position
        out["building_height"] = (_missing("building_height", why_g) if why_g else
                                  _with_others(out["building_height"], [_height(b, with_grade) for b in others],
                                               candidates, _height(main, with_grade)))
        if assumed and not why_g:       # and each other building as the main one, from its own grade plane
            out["building_height"] = _with_each_as_main(out["building_height"], candidates)
    if facts.get("grade_is") == "existing":     # the grade plane is finished ground: existing ground can't decide
        for name in ("building_height", "stories"):
            if out[name].get("value") is None and not out[name].get("readings"):
                continue                       # nothing measured: its own reason (no ground, ...) says why
            as_is = out[name].get("value")     # what the ground as it is gives: shown, never decides (no reading)
            out[name] = _missing(name, stop("existing_grade"))
            if as_is is not None:
                out[name]["measured_as_is"] = as_is

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
    # has no angle in it). On a corner lot every one of them is an open question: which yards are front, side
    # and rear, and which frontage is the lot width (and the drawing can't show whether both streets were given).
    if not lot.street_problem and facts.get("corner_lot") is None:
        lot.street_problem = stop("corner_unknown")
    elif not lot.street_problem and facts["corner_lot"]:
        lot.street_problem = stop("corner_lot")
    if lot.street_problem:
        for name in ("lot_width", "lot_depth", "front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard"):
            out[name] = _missing(name, lot.street_problem)
    else:
        chain = lot.ordered_street()
        width = [("along the street line", lot.length(chain), {})]
        if any(lot.curved[i] for i in chain):
            ends = [lot.edges[chain[0]][0], lot.edges[chain[-1]][-1]]
            width.append(("straight across, end to end (chord)", math.dist(ends[0], ends[1]), {}))
        out["lot_width"] = _decide("lot_width", width, "the length of the lot line(s) on the street (frontage)",
                                   [lot.id], "whether frontage on a curved street is measured along the curve or "
                                   "straight across is an open question for the architects (lot_width)")

    footprints = {b["id"]: _projection(b) for b in buildings}
    everything = ops.unary_union(list(footprints.values())) if footprints else Polygon()
    # which buildings aren't inside the lot, by name: coverage counts every building, so it waits; the yards wait
    # only if the main building is one of them (the others are still in the yards' "any solid" reading)
    outside = [b for b in buildings if not footprints[b["id"]].within(lot.polygon.buffer(TOL))]
    main_out = any(b is main for b in outside)
    others_out = len(outside) - main_out
    what = " and ".join(([] if not main_out else ["the main building" if len(buildings) > 1 else "the building"]) +
                        ([] if not others_out else [f"{others_out} other building{'s' if others_out > 1 else ''}"
                                                    if main_out or main is not None else
                                                    f"{others_out} building{'s' if others_out > 1 else ''}"]))
    why_inside = why_building or (stop("outside_lot", what=what) if outside else None)
    why_main_inside = why_building or (why_inside if main_out else None)
    if why_inside or why_plan or plan_level is None:
        out["building_area"] = _missing("building_area", why_inside or why_plan or why_grade)
        if why_inside and outside and not why_building:     # which ones: the panel shows them
            out["building_area"]["objects"] = [i for b in outside for i in b.get("parts") or [b["id"]]]
    else:
        # each cut at its own bottom when the ground plane is below it (a slab above grade on a slope): never an
        # empty cut blamed on overhangs
        # each connected group (_connected: a house with its balcony or bay) cut at the higher of the grade plane
        # and the group's own lowest bottom: a raised balcony is never cut at its own bottom (it would count at
        # grade and erase the overhang question), a slab above grade on a slope never below itself (0 sf)
        cut = ops.unary_union([_section(b, _cut_level(b, buildings, plan_level) + TOL) for b in buildings])
        out["building_area"] = _decide(
            "building_area", [("covered from above", everything.area, {}), ("at the main grade level", cut.area, {})],
            "the ground area of every building on the lot, porches and decks included",
            [i for b in buildings for i in _parts(b)],
            "whether parts above the ground floor that stick out (overhangs) count is an open question for the "
            "architects (building_area)")

    if lot.street_problem:
        return out
    sides = "which lot lines count as side and rear lot lines is an open question for the architects (lot_depth)"
    readings = lot.readings()
    why_lines = (stop("lines_unclear", limit=MAX_UNCLEAR_EDGES) if readings is None else  # too many to list
                 stop("no_rear_line") if not readings else None)                         # none fits the definitions
    out["lot_depth"] = (_missing("lot_depth", why_lines) if why_lines else
                        _decide("lot_depth", [(w, (lot.length(l) + lot.length(r)) / 2, {}) for w, l, r, _ in readings],
                                "the average length of the two side lot lines", [lot.id], sides))

    yards = ("front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard")
    why_yards = why_main_inside or why_plan or why_main or (why_grade if plan_level is None else None)
    if why_yards:
        for name in yards:
            out[name] = _missing(name, why_yards)
        return out

    # each yard to the building seen from above and to its walls at the ground: both readings
    # with more than one solid, a porch or deck drawn as its own solid is part of the building for yards
    # (§325-18A) while an accessory building may follow other rules (§325-25): measure to it as well
    shapes = [(w, s) for w, s in (("to the building seen from above", footprints[main["id"]]),
                                  ("to its walls at ground level",
                                   _section(main, _cut_level(main, buildings, plan_level) + TOL))) if not s.is_empty]
    shapes += [("to any solid on the Building layer, seen from above", everything)] if len(buildings) > 1 else []
    eaves = ("whether a yard is measured to the wall or to overhangs (eaves, cornices), and whether another solid "
             "is a porch or deck (part of the building, §325-18A) or an accessory building (§325-25), are open "
             "questions for the architects (yard_projections)")
    objects = [lot.id, *_parts(main)]
    front = [(w, *_distance(lot.line(lot.ordered_street()), s)) for w, s in shapes]
    out["front_yard"] = _decide("front_yard", [(w, d, {"points": p}) for w, d, p in front],
                                "the least distance from the street lot line to the main building", objects, eaves)
    if why_lines:
        for name in ("side_yard_smaller", "side_yard_larger", "rear_yard"):
            out[name] = _missing(name, why_lines)
        return out
    small, large, rear = [], [], []
    for words, left, right, back in readings:
        for w, s in shapes:
            a, pa = _distance(lot.line(left), s)
            b, pb = _distance(lot.line(right), s)
            small.append((_both(words, w), min(a, b), {"points": pa if a <= b else pb}))
            large.append((_both(words, w), max(a, b), {"points": pb if a <= b else pa}))
        for w, s in shapes:
            d, p = _distance(lot.line(back), s)
            rear.append((_both(words, w), d, {"points": p}))
    both = f"{sides}; {eaves}"
    out["side_yard_smaller"] = _decide("side_yard_smaller", small,
                                       "the least distance from the nearer side lot line to the building", objects, both)
    out["side_yard_larger"] = _decide("side_yard_larger", large,
                                      "the least distance from the farther side lot line to the building", objects, both)
    out["rear_yard"] = _decide("rear_yard", rear, "the least distance from the rear lot line to the main building",
                               objects, both)
    return out
