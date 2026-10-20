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

from shapely import ops
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.validation import explain_validity

from rule_format.rulebook import MEASURES_FILE, load

MEASURES = list(load(MEASURES_FILE))

TOL = 0.01                # ft: two points closer than this are the same point
SAME = 1e-6               # ft: readings closer than this give the same value
PARALLEL, PERPENDICULAR = 30, 60   # degrees from the street: clearly a rear line / clearly a side line
FLAT = math.cos(math.radians(2.39))   # a roof face flatter than 1/2 inch per foot (a drainage slope) is level
MAX_UNCLEAR_EDGES = 4     # more lot lines than this of unclear kind: too many readings to list
STATED = {"use": "text", "stories": "count", "sleeping_rooms": "count", "parking_spaces": "count"}
ASK = {"use": "choose the use", "stories": "enter the number of stories",
       "sleeping_rooms": "enter bedrooms / parking spaces", "parking_spaces": "enter bedrooms / parking spaces"}
UNITS = {"lot_area": "sf", "lot_width": "ft", "lot_depth": "ft", "building_area": "sf", "building_height": "ft",
         "front_yard": "ft", "side_yard_smaller": "ft", "side_yard_larger": "ft", "rear_yard": "ft"}


def _r(x: float) -> float:
    return round(x, 6) + 0.0          # drops float noise (and -0.0); never rounds toward a limit by more than 1e-6


def _record(definition, unit, value=None, how="", objects=(), points=None, readings=(), reason=None) -> dict:
    return {"value": value, "unit": unit, "how": how, "definition": definition, "objects": list(objects),
            "points": points, "readings": list(readings), "reason": reason}


def _missing(name: str, reason: str) -> dict:
    return _record(name, UNITS[name], reason=reason)


def _decide(name: str, readings: list[tuple[str, float, dict]], how: str, objects, question: str) -> dict:
    """One value if every reading gives the same number; else None, with the readings and the question."""
    values = [v for _, v, _ in readings]
    shown = [{"reading": r, "value": _r(v)} for r, v, _ in readings]
    if values and max(values) - min(values) <= SAME:
        how = how if len(readings) > 1 or not readings[0][0] else f"{how} ({readings[0][0]})"
        return _record(name, UNITS[name], _r(values[0]), how, objects, readings[0][2].get("points"),
                       shown if len(readings) > 1 else [])
    return _record(name, UNITS[name], None, how, objects, None, shown,
                   f"the readings give different values; {question}")


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
            self.problems.append("the lot outline isn't one closed loop of lot lines")
        elif not self.polygon.is_valid or self.polygon.area <= 0:
            self.problems.append(f"the lot outline crosses itself ({explain_validity(self.polygon)})")
        street = [i for i, e in enumerate(self.edges)
                  if any(_same_point(e[0], a) and _same_point(e[-1], b) or _same_point(e[0], b) and _same_point(e[-1], a)
                         for a, b in facts.get("street_line") or [])]
        self.street = street
        self.street_problem = None
        if not facts.get("street_line"):
            self.street_problem = "the street side isn't given: pick the lot line on the street"
        elif len(street) != len(facts["street_line"]):
            self.street_problem = "a street line given doesn't match a lot line: pick the street side again"
        elif not self._contiguous(street):
            self.street_problem = "the street lot lines given aren't next to each other"
        elif len(street) == n:
            self.street_problem = ("every lot line is on a street: which yards are front, side and rear is an open "
                                   "question for the architects")

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


def _open_to_the_sky(faces: list[dict]) -> list[dict]:
    """The faces of a solid that nothing of it covers: no other face lies above a point inside them. Undersides
    (soffits, the floor of an upper storey that sticks out) and floors are covered; roofs are not."""
    flat = [(f, Polygon([p[:2] for p in f["points"]]).buffer(0)) for f in faces if _normal_z(f["points"]) > 0.001]
    open_ = []
    for f, shape in flat:
        if shape.area <= 1e-9:
            continue
        inside = shape.representative_point()
        z = _plane_z(f, inside.x, inside.y)
        if not any(g is not f and other.buffer(TOL).contains(inside) and (_plane_z(g, inside.x, inside.y) or z) > z + TOL
                   for g, other in flat):
            open_.append(f)
    return open_


def _height(building: dict, grade: float) -> dict:
    """HEIGHT OF BUILDING: from the grade plane "to the highest level of a flat or mansard roof or to the average
    height of a pitched ... roof", using "that section of the roof that has the highest elevation". The roof is
    the faces open to the sky. If its largest face (the main roof) doesn't reach the top, something smaller rises
    above it (a parapet, chimney, bulkhead or a higher part): the roof is read both without it and with it, each
    the same way, and whether it counts is an open question."""
    zs = [p[2] for f in building["faces"] for p in f["points"]]
    top = max(zs)
    bottom = min(zs)
    roof = [f for f in _open_to_the_sky(building["faces"]) if not all(abs(p[2] - bottom) <= TOL for p in f["points"])]
    if not roof:
        return _missing("building_height", "the roof's shape can't be read (no faces open to the sky)")
    how = "from the ground level (grade plane) to the top of the roof"
    main_roof = max(roof, key=lambda f: (Polygon([p[:2] for p in f["points"]],
                                                 [[p[:2] for p in h] for h in f.get("holes") or []]).buffer(0).area,
                                         max(p[2] for p in f["points"])))
    roof_top = max(p[2] for p in main_roof["points"])
    if roof_top >= top - TOL:
        readings, question = _roof_readings(roof, top, grade)
        return _decide("building_height", readings, how, [building["id"]], question)
    below = [f for f in roof if all(p[2] <= roof_top + TOL for p in f["points"])]
    low, low_question = _roof_readings(below, roof_top, grade)
    high, high_question = _roof_readings(roof, top, grade)
    readings = [(_both("leaving out what rises above the main roof", w), v, x) for w, v, x in low]
    readings += [(_both("including what rises above the main roof", w), v, x) for w, v, x in high]
    return _decide("building_height", readings, how, [building["id"]],
                   "; ".join(dict.fromkeys(q for q in (ABOVE_ROOF, low_question, high_question) if q)))


def _roof_readings(roof: list[dict], top: float, grade: float) -> tuple[list, str]:
    """The readings of a roof whose highest point is `top`, and the open question they leave ("" if none). Its
    highest section is the faces that reach the top: all level (or within a drainage slope of level), a flat
    roof to its highest level; all sloped, a pitched roof (midway between that section's eave and the ridge, or
    the ridge); both, a mansard (to its highest level) or a pitched or hip roof with a deck or ridge strip."""
    highest = [f for f in roof if any(abs(p[2] - top) <= TOL for p in f["points"])]
    sloped = [f for f in highest if _normal_z(f["points"]) < FLAT]
    if not sloped:
        return [("a flat roof, to its highest level", top - grade, {})], ""
    eave = min(p[2] for f in sloped for p in f["points"])
    readings = [("pitched: midway between eave and ridge", (eave + top) / 2 - grade, {}),
                ("pitched: to the ridge", top - grade, {})]
    if len(sloped) < len(highest):            # a level part at the top too
        return [("mansard: to its highest level", top - grade, {})] + readings, _both(ROOF_KIND, PITCHED)
    return readings, PITCHED


MAX_COMBINATIONS = 200      # more combinations of roof readings than this: too many to list; left for review


def _with_others(main: dict, others: list[dict]) -> dict:
    """The main building's height read with the other solids: alone, and with every other solid as part of it
    (a wing or tower drawn as its own solid is part of the building; an accessory building may have its own
    limit, §325-25). Every combination of each roof's own readings is listed. A question is named only if two
    readings that differ in that answer alone have different values: each solid's roof question on its own,
    and the accessory question."""
    unread = [o for o in others if o["value"] is None and not o["readings"]]
    if unread:                          # never dropped: it could be the tallest part
        return _missing("building_height", "another solid's height can't be read: " + unread[0]["reason"])

    def values(m):
        return [(r["reading"], r["value"]) for r in m["readings"]] or [("", m["value"])]

    mine, theirs = values(main), [values(o) for o in others]
    if len(mine) * math.prod(len(t) for t in theirs) > MAX_COMBINATIONS:
        return _missing("building_height", "too many solids with open roof questions to list every reading: "
                                           "pick the main building's parts, or ask the architects")
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
        words = "the main building only" if choice[1] == "alone" else "with every other solid as part of it" + "".join(
            f"; {n}: {lbl}" for n, lbl in zip(names, choice[2:]) if lbl)
        readings.append((_both(choice[0], words), v, {}))
    return _decide("building_height", readings, main["how"], main["objects"] + names,
                   "; ".join(dict.fromkeys(questions)))


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
                     if v is not None else _record(name, unit, reason=ASK[name]))
    buildings = site.get("buildings") or []
    grade = facts.get("grade_elevation")
    main = (buildings[0] if len(buildings) == 1 else
            next((b for b in buildings if b["id"] == facts.get("main_building")), None))
    why_building = ("no building on the Building layer" if not buildings else
                    "; ".join(p for b in buildings for p in b.get("problems") or []) or None)
    why_grade = ("the ground level isn't given: enter it (the grade plane)" if grade is None else
                 "say whether the ground is flat" if facts.get("ground_is_flat") is None else
                 None if facts["ground_is_flat"] else
                 "sloped ground: the grade plane (§325-3) needs the ground levels around the walls, which aren't "
                 "measured yet")
    why_main = None if main else "more than one building: pick the main building"
    why = why_building or why_grade or why_main
    out["building_height"] = _missing("building_height", why) if why else _height(main, grade)
    others = [b for b in buildings if b is not main]
    if not why and others and (out["building_height"]["value"] is not None or out["building_height"]["readings"]):
        out["building_height"] = _with_others(out["building_height"], [_height(b, grade) for b in others])

    problems = list(site.get("problems") or [])
    lot = Lot(site, facts) if site.get("lot") and not problems else None
    if lot is None or lot.problems:
        reason = "; ".join(problems or (lot.problems if lot else ["no lot outline"]))
        for name in UNITS:
            out.setdefault(name, _missing(name, reason))
        return out
    if facts.get("lot_surveyed"):
        out["lot_area"] = _record("lot_area", "sf", _r(lot.polygon.area), "the area inside the lot lines (a survey)",
                                  [lot.id])
    else:                               # a drawn lot isn't a surveyed one: the lot area waits for a survey
        out["lot_area"] = _record("lot_area", "sf", None, "the area inside the lot lines", [lot.id], None,
                                  [{"reading": "the lot as drawn", "value": _r(lot.polygon.area)}],
                                  "say whether the lot outline is from a survey" if facts.get("lot_surveyed") is None
                                  else "the lot outline isn't from a survey: the lot area needs one (an open question "
                                       "for the architects)")

    # where the street is decides the lot width, the yards and the lot depth. Whether the lot is a corner lot
    # (two streets, §325-19C) is stated by the architect, never guessed from the drawing (the city's definition
    # has no angle in it). On a corner lot every one of them is an open question: which yards are front, side
    # and rear, and which frontage is the lot width (and the drawing can't show whether both streets were given).
    if not lot.street_problem and facts.get("corner_lot") is None:
        lot.street_problem = ("say whether this is a corner lot (two streets meet at it, §325-19C): enter corner lot "
                              "yes or no")
    elif not lot.street_problem and facts["corner_lot"]:
        lot.street_problem = ("a corner lot: which yards are front, side and rear yards, and which street's frontage "
                              "is the lot width (§325-19C), are open questions for the architects")
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
                  (None if everything.within(lot.polygon.buffer(TOL)) else "a building isn't inside the lot"))
    if why_inside or why_grade:
        out["building_area"] = _missing("building_area", why_inside or why_grade)
    else:
        cut = ops.unary_union([_section(b, grade + TOL) for b in buildings])
        out["building_area"] = _decide(
            "building_area", [("covered from above", everything.area, {}), ("at the main grade level", cut.area, {})],
            "the ground area of every building on the lot, porches and decks included", list(footprints),
            "whether parts above the ground floor that stick out (overhangs) count is an open question for the "
            "architects (building_area)")

    if lot.street_problem:
        return out
    sides = "which lot lines count as side and rear lot lines is an open question for the architects (lot_depth)"
    readings = lot.readings()
    why_lines = None if readings else "the side and rear lot lines can't be told apart"
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
    objects = [lot.id, main["id"]]
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
