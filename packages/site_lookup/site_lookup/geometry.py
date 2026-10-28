"""Plain plane geometry in EPSG:2261 feet: areas, distances and point-in-polygon. No GIS library needed,
because every service is asked to answer in that one projected coordinate system."""

import math

Point = tuple[float, float]


def open_ring(ring: list) -> list[Point]:
    """A ring without its repeated closing point, and without consecutive duplicate points."""
    pts = [(float(x), float(y)) for x, y, *_ in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    out = [p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > 1e-6]
    return out


def area(ring: list[Point]) -> float:
    """Area by the shoelace formula (always positive)."""
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def centroid(ring: list[Point]) -> Point:
    a = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1])) / 2
    if abs(a) < 1e-9:
        return (sum(x for x, _ in ring) / len(ring), sum(y for _, y in ring) / len(ring))
    cx = sum((x1 + x2) * (x1 * y2 - x2 * y1) for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))
    cy = sum((y1 + y2) * (x1 * y2 - x2 * y1) for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))
    return (cx / (6 * a), cy / (6 * a))


def inside(p: Point, ring: list[Point]) -> bool:
    """Point in polygon (ray casting); a point on an edge counts as inside."""
    x, y = p
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if seg_distance(p, (x1, y1), (x2, y2)) < 1e-6:
            return True
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def inside_any(p: Point, rings: list[list[Point]]) -> bool:
    """Inside a polygon given as rings (outer and holes, even-odd rule)."""
    return sum(inside(p, r) for r in rings) % 2 == 1


def seg_distance(p: Point, a: Point, b: Point) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def polyline_distance(p: Point, path: list[Point]) -> float:
    return min(seg_distance(p, a, b) for a, b in zip(path, path[1:])) if len(path) > 1 else math.dist(p, path[0])


def angle_between(s1: tuple[Point, Point], s2: tuple[Point, Point] | None) -> float:
    """The angle in degrees (0–90) between two segments' directions, ignoring which way they point."""
    if s2 is None:
        return 90.0
    (a, b), (c, d) = s1, s2
    a1 = math.atan2(b[1] - a[1], b[0] - a[0])
    a2 = math.atan2(d[1] - c[1], d[0] - c[0])
    diff = abs(math.degrees(a1 - a2)) % 180
    return min(diff, 180 - diff)


def edges(ring: list[Point]) -> list[tuple[Point, Point]]:
    return list(zip(ring, ring[1:] + ring[:1]))


def bounds(ring: list[Point], pad: float = 0.0) -> tuple[float, float, float, float]:
    xs, ys = [x for x, _ in ring], [y for _, y in ring]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def grid_inside(ring: list[Point], n: int = 30) -> list[Point]:
    """About n × n evenly spaced sample points inside the polygon (for sharing it out between zones)."""
    x0, y0, x1, y1 = bounds(ring)
    step = max(x1 - x0, y1 - y0) / n
    pts = []
    y = y0 + step / 2
    while y < y1:
        x = x0 + step / 2
        while x < x1:
            if inside((x, y), ring):
                pts.append((x, y))
            x += step
        y += step
    return pts


Box = tuple[float, float, float, float]       # x0, y0, x1, y1


def clip_ring(ring: list[Point], box: Box) -> list[Point]:
    """The part of a polygon inside an axis-aligned box (Sutherland–Hodgman, one side of the box at a time). A
    polygon reaching out of the box comes back closed along the box's edge; one wholly outside comes back empty."""
    x0, y0, x1, y1 = box
    sides = ((lambda p: p[0] >= x0, lambda a, b: _at_x(a, b, x0)), (lambda p: p[0] <= x1, lambda a, b: _at_x(a, b, x1)),
             (lambda p: p[1] >= y0, lambda a, b: _at_y(a, b, y0)), (lambda p: p[1] <= y1, lambda a, b: _at_y(a, b, y1)))
    out = list(ring)
    for keep, cross in sides:
        pts, out = out, []
        for i, b in enumerate(pts):
            a = pts[i - 1]
            if keep(b):
                if not keep(a):
                    out.append(cross(a, b))
                out.append(b)
            elif keep(a):
                out.append(cross(a, b))
        if not out:
            return []
    out = [p for i, p in enumerate(out) if i == 0 or math.dist(p, out[i - 1]) > 1e-6]
    if len(out) > 1 and math.dist(out[0], out[-1]) <= 1e-6:
        out = out[:-1]
    return out if len(out) >= 3 and area(out) > 1e-6 else []


def clip_path(path: list[Point], box: Box) -> list[list[Point]]:
    """The pieces of a polyline inside an axis-aligned box (Liang–Barsky on each segment; consecutive pieces that
    meet are joined)."""
    pieces: list[list[Point]] = []
    for a, b in zip(path, path[1:]):
        seg = _clip_segment(a, b, box)
        if seg is None:
            continue
        if pieces and math.dist(pieces[-1][-1], seg[0]) < 1e-6:
            pieces[-1].append(seg[1])
        else:
            pieces.append([seg[0], seg[1]])
    return pieces


def _at_x(a: Point, b: Point, x: float) -> Point:
    t = (x - a[0]) / (b[0] - a[0])
    return (x, a[1] + t * (b[1] - a[1]))


def _at_y(a: Point, b: Point, y: float) -> Point:
    t = (y - a[1]) / (b[1] - a[1])
    return (a[0] + t * (b[0] - a[0]), y)


def _clip_segment(a: Point, b: Point, box: Box) -> tuple[Point, Point] | None:
    x0, y0, x1, y1 = box
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:                    # parallel to this side and outside it
                return None
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 >= t1:
            return None
    return (a[0] + t0 * dx, a[1] + t0 * dy), (a[0] + t1 * dx, a[1] + t1 * dy)
