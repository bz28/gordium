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
    shown = [{"reading": r, "value": _r(v)} for r, v, _ in readings]
    if values and max(values) - min(values) <= SAME:
        how = how if len(readings) > 1 or not readings[0][0] else f"{how} ({readings[0][0]})"
        return _record(name, UNITS.get(name) or STATED[name], _r(values[0]), how, objects, readings[0][2].get("points"),
                       shown if len(readings) > 1 else [])
    return _record(name, UNITS.get(name) or STATED[name], None, how, objects, None, shown,
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


# A plain solid (no floors drawn) whose top is more than this above the grade could hold a story: the lowest ceiling
# a habitable room may have (7 ft, NYS Residential Code R305.1). Lower (a porch slab, steps, a deck) it can't.
STORY_ROOM = 7.0            # ft
WHOLE = "as stated by the architect for the whole building (a joined part's stories aren't drawn)"
MAX_COMBINATIONS = 200      # more combinations of roof readings than this: too many to list; left for review


def _with_others(main: dict, others: list[dict], assemblies) -> dict:
    """The main building's height read over the candidate buildings (_assemblies, the same list the stories are
    read over: alone, and with every other solid as part of it; a wing or tower drawn as its own solid is part of
    the building, an accessory building may have its own limit, §325-25), labelled with the assemblies' own words.
    `main` and `others` are the height records of the first assembly's building and of the others in the second.
    Every combination of each roof's own readings is listed. A question is named only if two readings that differ
    in that answer alone have different values: each solid's roof question on its own, and the accessory
    question."""
    (alone_words, _), (with_words, _) = assemblies[0], assemblies[1]
    unread = [o for o in others if o["value"] is None and not o["readings"]]
    if unread:                          # never dropped: it could be the tallest part
        return _missing("building_height", stop("other_height", reason=unread[0]["reason"]))

    def values(m):
        return [(r["reading"], r["value"]) for r in m["readings"]] or [("", m["value"])]

    mine, theirs = values(main), [values(o) for o in others]
    if len(mine) * math.prod(len(t) for t in theirs) > MAX_COMBINATIONS:
        return _missing("building_height", stop("too_many_roofs"))
    names = [o["objects"][0] for o in others]
    combos = [((w, "alone") + (None,) * len(others), v) for w, v in mine]
    combos += [((w, "with") + tuple(lbl for lbl, _ in picks), max([v] + [x for _, x in picks]))
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


def _holds_a_story(solid: dict, grade, first_floor_top) -> bool:
    """Whether a plain solid (no floors drawn) could hold a story: its top more than STORY_ROOM above the grade, or
    above the top of the main building's first floor. Not knowing the grade or its top, it could."""
    top = max((p[2] for f in solid.get("faces") or [] for p in f["points"]), default=None)
    if top is None or grade is None:
        return True
    return top - grade > STORY_ROOM or (first_floor_top is not None and top > first_floor_top + TOL)


def _assemblies(main: dict, others: list[dict]) -> list[tuple[str, list[dict]]]:
    """The candidate buildings the height is read over (_with_others), for every building measurement read from
    the drawing: the main building only, and, with other solids drawn, the main building with every other solid as
    part of it (a wing drawn as its own solid is part of the building; an accessory building isn't, §325-25)."""
    out = [("the main building only", [main])]
    if others:
        out.append(("with every other solid as part of it", [main] + list(others)))
    return out


def _stories_over(assemblies, grade, why_grade, stated) -> dict:
    """STORY over the same candidate buildings as the height: each assembly's count is the most stories of any
    building in it that can be counted (its floor blocks, or its stacked solids beside the typed count, _stories);
    an assembly with nothing countable in it is the typed count, as a reading only. A plain solid (no floors drawn)
    tall enough to hold a story (_holds_a_story) has an unknown count, so an assembly with one and something
    countable is the count typed for the whole building, and only if no countable part has more floors (else the
    readings disagree: the story question); with no count typed it needs review. If the assemblies' counts differ,
    it is the accessory question; if any count can't be read, stories need review with its reason."""
    readings, questions, objects = [], [], []
    main = assemblies[0][1][0]
    first = (main["spans"][main["floor"].index(True)][1] if main.get("parts") and any(main["floor"]) else None)
    for words, members in assemblies:
        # a stack of floor blocks is counted on its own; plain stacked solids only beside the typed count
        counted = [_stories(b, grade, why_grade, None if any(b["floor"]) else stated)
                   for b in members if b.get("parts")]
        objects += [i for b in members for i in _parts(b)]
        for r in counted:
            if r["value"] is None and not r["readings"]:
                return _missing("stories", r["reason"])
            if r["value"] is None and r["reason"]:
                questions.append(r["reason"].split("; ", 1)[-1])
        if not counted:
            if stated is None:
                return _missing("stories", stop("no_stories"))
            readings.append((_both(words, "as stated by the architect"), stated, {}))
            continue
        choices = [[(x["reading"], x["value"]) for x in r["readings"]] or [("", r["value"])] for r in counted]
        plain = [b for b in members if not b.get("parts") and _holds_a_story(b, grade, first)]
        if plain:                       # its stories aren't drawn: only the count typed covers the whole building
            if stated is None:
                return _missing("stories", stop("joined_part_stories", part=plain[0]["id"]))
            readings.append((_both(words, WHOLE), stated, {}))
            for picks in itertools.product(*choices):
                if max(v for _, v in picks) > stated:          # a part has more floors than the count typed
                    readings.append((_both(words, *[w for w, _ in picks]), max(v for _, v in picks), {}))
                    questions.append("the count typed disagrees with the floors drawn: a question (story)")
            continue
        for picks in itertools.product(*choices):
            readings.append((_both(words, *[w for w, _ in picks]), max(v for _, v in picks), {}))
    if stated is not None and not any("as stated by the architect" in w for w, _, _ in readings):
        readings.append(("as stated by the architect", stated, {}))      # the typed count: a reading beside them
        if any(v != stated for _, v, _ in readings):
            questions.append("the count typed disagrees with the floors drawn: a question (story)")
    values = {v for _, v, _ in readings}
    if len(assemblies) > 1 and len({max(v for w, v, _ in readings if w.startswith(a)) for a, _ in assemblies}) > 1:
        questions.append(ACCESSORY)
    return _decide("stories", readings, "the stories of the building counted from the model (floor blocks or stacked "
                   "solids; the count typed is a reading beside them)", list(dict.fromkeys(objects)),
                   "; ".join(dict.fromkeys(questions)) if len(values) > 1 else "")


# ---- measuring -------------------------------------------------------------------------------------------

def _both(*words) -> str:
    return "; ".join(w for w in words if w)


def _distance(line, shape):
    a, b = ops.nearest_points(line, shape)
    return line.distance(shape), [[_r(a.x), _r(a.y)], [_r(b.x), _r(b.y)]]


def measure(site: dict, facts: dict) -> dict[str, dict]:
    """Every measurement in measures.yaml, in its order, each with its working, for one site and its lot facts."""
    out = _measure(site, facts)
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
    main = (buildings[0] if len(buildings) == 1 else
            next((b for b in buildings if b["id"] == facts.get("main_building")), None))
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
    why_grade = (stop("no_ground") if grade is None else
                 stop("ground_off_building", ground=_r(grade), bottom=_r(off[0]), top=_r(off[1])) if off else
                 stop("buried_solid", ground=_r(grade), bottom=_r(buried[0]), top=_r(buried[1])) if buried else
                 stop("ground_unknown") if facts.get("ground_is_flat") is None else
                 None if facts["ground_is_flat"] else stop("sloped_ground"))
    # stacked floor blocks (each story its own solid, standing on the one below, as Gordium's starting building is
    # drawn) are one building, and its stories are counted from them: read from the shape, never typed
    buildings = _stacks(buildings)
    main = (buildings[0] if len(buildings) == 1 else
            next((b for b in buildings if facts.get("main_building") in b.get("parts", [b["id"]])), None))
    why_main = None if main else stop("no_main_building")
    others = [b for b in buildings if b is not main]
    # One decision for every building measurement: which building (why_which), over which candidate buildings
    # (_assemblies: the main one alone, and with every other solid as part of it). The typed story count is a
    # stated fact: it stands as the value only when nothing drawn anywhere can be counted (no floor blocks and no
    # stacked solids on any building, and no building object with a problem, which might be either). Otherwise
    # the stories come from the drawing over the same assemblies as the height, the typed count only a reading
    # beside them, and every stop that applies to the height applies to them.
    why_which = why_building or why_main
    countable = any(b.get("parts") for b in buildings) or bool(why_building and site.get("buildings"))
    if countable:
        out["stories"] = (_missing("stories", why_which) if why_which else
                          _stories_over(_assemblies(main, others), grade, why_grade, facts.get("stories")))
    why = why_which or why_grade
    out["building_height"] = _missing("building_height", why) if why else _height(main, grade)
    if not why and others and (out["building_height"]["value"] is not None or out["building_height"]["readings"]):
        out["building_height"] = _with_others(out["building_height"], [_height(b, grade) for b in others],
                                              _assemblies(main, others))

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
    why_inside = (why_building or
                  (None if everything.within(lot.polygon.buffer(TOL)) else stop("outside_lot")))
    if why_inside or why_grade:
        out["building_area"] = _missing("building_area", why_inside or why_grade)
    else:
        cut = ops.unary_union([_section(b, grade + TOL) for b in buildings])
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
    why_yards = why_inside or why_grade or why_main
    if why_yards:
        for name in yards:
            out[name] = _missing(name, why_yards)
        return out

    # each yard to the building seen from above and to its walls at the ground: both readings
    # with more than one solid, a porch or deck drawn as its own solid is part of the building for yards
    # (§325-18A) while an accessory building may follow other rules (§325-25): measure to it as well
    shapes = [(w, s) for w, s in (("to the building seen from above", footprints[main["id"]]),
                                  ("to its walls at ground level", _section(main, grade + TOL))) if not s.is_empty]
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
