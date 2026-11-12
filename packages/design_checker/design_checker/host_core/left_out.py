"""Which objects a check leaves out, and why: the same decisions for every design tool (a host). The host looks at
its model and sends what it saw of each object that could be a building and isn't measured (its id, its 3D box,
its plan points, and for a placed block or linked model what it holds, at every depth); these functions decide
whether it is on the lot (so left out: the check needs review), whether it may be touching the house, and when it
has no box that covers all of it. The Rhino plugin calls them in its own Python (through rhino_logic.py, which
offers every name here unchanged); any other host (the Revit add-in) asks the worker's session command
`objects.left_out` (protocol.py), which serves these same functions.

What stays with the host: which objects to send (Rhino: solids, meshes, SubDs and blocks off the Building layer and
Gordium's own layers, rhino_logic.could_be_building and left_out_candidate; Revit: by category, its design note),
and measuring them (a box, plan points, a definition's status as the host's own API names it). What is decided
here: everything after that, so the two hosts can't drift apart on a choice that could turn "needs review" into
"complies" (principle 4: never a false pass).

  no_box_reasons      for each object, why it has no box that covers all of it (or None: it has one)
  left_out_decisions  for each object, whether it is left out of the check (on the lot), and why
  touching_decisions  for each object, whether it may be part of the house (its box within 0.1 ft of a building's)

And for the architect, never a decision: linked_file_problems (for an object left out because a linked file isn't
up to date, which definition's file it is and what is wrong with it) and linked_file_words (the sentence saying
so, and what to do, with the host's own menu words: host_core has none).

What a host sends, in its own model units (`feet_per_unit` says how many feet one unit is):

  an object      {"id": "...", "box": [x0, y0, z0, x1, y1, z1] or null, "points": [[x, y], ...],
                  "definition": "<id>" or null}
                 `definition` only for a placed block or linked model: leave the key out entirely for anything
                 else, since null means a block whose definition isn't there (no box: left out and touching).
                 `box` is the host's own box for it, null when the host has none (an empty block, an empty SubD).
                 `points` (only asked of an object whose box comes near the lot): enough of it in plan to outline
                 it (vertices, points along its edges and over its faces; its box's corners when it has none). In
                 the host's own Python it may be a function giving them, so a far object is never outlined.
  definitions    {"<id>": {"status": "...", "parts": [{"box": [...] or null, "definition": "<id>"}, ...]}}
                 what each placed block's definition holds (each part as an object, without id or points) and
                 its status: the host's word for whether what it holds is the design (Rhino's ArchiveFileStatus
                 by name; BLOCK_CONTENTS_KNOWN are the two that say it is). Each definition once, however often
                 it is placed.
  lot            {"ring": [[x, y], ...] (its outline's points: at least 3, around some area, or it is refused),
                  "box": [x0, y0, x1, y1] (its plan box, grown to hold the ring if it doesn't)} or null
  buildings      the measured buildings' boxes, [x0, y0, z0, x1, y1, z1] each (null: none to give, skipped)

Moved here from rhino_logic.py unchanged (rhino_logic still offers every name): ON_LOT_REACH, box_near_lot,
BLOCK_CONTENTS_KNOWN, block_contents_known, reaches_into_lot and its helpers. New: the three decisions, which were
written out twice before, in the Rhino command (gordium_rhino._not_included, _touching and a _whole_box) and in the
reference adapter (conformance_rhino._left_out, _box). Python 3.9 and the standard library only: Rhino 8 imports this
into its own Python 3.9."""

import math

__all__ = ['_inside', 'ON_LOT_REACH', '_ring_area', '_hull', '_clip', 'box_near_lot', 'BLOCK_CONTENTS_KNOWN',
    'block_contents_known', 'reaches_into_lot', '_Depth', 'DEPTH_QUESTIONS', '_deep', '_stretches_inside',
    'TOUCH_GAP', 'MAX_BLOCK_DEPTH', 'NO_BOX', 'WHY', '_finite', '_sent_box', '_covers', 'OBJECT_KEYS', '_sent_object',
    '_sent_definitions', '_why_no_box', '_judged', 'no_box_reasons', 'left_out_decisions', '_sent_points', 'touching_decisions',
    'LINK_PROBLEM', 'LINK_WORDS', 'LINK_FIX', '_culprit', 'linked_file_problems', 'linked_file_words']


def _inside(x, y, poly):
    """Whether a point is inside a polygon (screen points; even-odd)."""
    inside = False
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


ON_LOT_REACH = 0.1        # ft: how far into the lot an object must reach to count as on it (a neighbour drawn
                          # touching the lot line, or a hair over it, stays off)


def _ring_area(ring):
    """The signed area of a closed ring of (x, y) points (counterclockwise: positive)."""
    return sum(ring[i - 1][0] * ring[i][1] - ring[i][0] * ring[i - 1][1] for i in range(len(ring))) / 2


def _hull(points):
    """The convex hull of (x, y) points, counterclockwise (Andrew's monotone chain)."""
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) < 3:
        return pts

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _clip(subject, convex):
    """The part of the ring `subject` (any simple polygon) inside the counterclockwise convex ring `convex`
    (Sutherland-Hodgman). Its area is the overlap's area."""
    out = list(subject)
    for i in range(len(convex)):
        a, b = convex[i - 1], convex[i]
        inside = [(b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0 for p in out]
        nxt = []
        for k in range(len(out)):
            p, q, pin, qin = out[k - 1], out[k], inside[k - 1], inside[k]
            if pin != qin:
                dx, dy = q[0] - p[0], q[1] - p[1]
                den = (b[0] - a[0]) * dy - (b[1] - a[1]) * dx
                t = ((b[1] - a[1]) * (p[0] - a[0]) - (b[0] - a[0]) * (p[1] - a[1])) / den if den else 0.0
                nxt.append((p[0] + t * dx, p[1] + t * dy))
            if qin:
                nxt.append(q)
        out = nxt
        if not out:
            break
    return out


def box_near_lot(box, lot_box, reach):
    """Whether a plan box (x0, y0, x1, y1) comes within `reach` of the lot's plan box: a quick test before any
    outline work. Exact in the cautious direction: an object whose box misses the lot's box grown by `reach`
    can't reach into the lot (its footprint lies inside its box, and the lot inside the lot's)."""
    x0, y0, x1, y1 = box
    a0, b0, a1, b1 = lot_box
    return x0 <= a1 + reach and a0 - reach <= x1 and y0 <= b1 + reach and b0 - reach <= y1


# A block definition's contents are the block only when it isn't linked to a file, or its linked file was read and
# hasn't changed since (RhinoCommon's InstanceDefinitionArchiveFileStatus, by name).
BLOCK_CONTENTS_KNOWN = ("NotALinkedInstanceDefinition", "LinkedFileIsUpToDate")


def block_contents_known(archive_status) -> bool:
    """Whether what a block definition holds in the document is the block: its ArchiveFileStatus (the enum value or
    its name) is one of BLOCK_CONTENTS_KNOWN. Every other status is not: LinkedFileNotFound (live Rhino 8.35, Mac,
    2026-11-12: the definition then holds one text label, "Missing block file: ...", at the centre of the last
    known shape, a valid box of a single point, so the block looks whole and nowhere near the house),
    LinkedFileNotReadable, and LinkedFileIsNewer / IsOlder / IsDifferent (the file has changed since it was read:
    what is drawn may not be the design). A status not in the list, or none, is not known either."""
    return str(archive_status).split(".")[-1] in BLOCK_CONTENTS_KNOWN


def reaches_into_lot(lot_ring, points, reach, box=None):
    """Whether an object whose plan points (any (x, y) of it: vertices, points along its edges) are `points`
    reaches into the lot (`lot_ring`, its outline's points) by more than `reach` (model units): the part of its
    plan footprint (their convex hull) inside the lot, averaged across (twice its area over its perimeter), is
    wider than `reach`, or some of it stands more than `reach` inside the lot's outline (however thin it is: a
    1-inch fin wall, a mast, an upright panel; the averaged width measures only how thick it is). Wholly on the
    lot, straddling a lot line or mostly past it: on the lot. Touching the line from outside, a hair over it (no
    more than `reach` in: a wall drawn skewed counts once its deep end is more than `reach` in), or off the lot
    but inside the lot's bounding box (a rotated or jogged lot, the neighbour's house): not. The hull only ever
    makes an object bigger, the cautious direction.
    `box`, the object's plan bounding box (x0, y0, x1, y1), is its footprint whenever the points don't outline
    one (fewer than 3, or all in a line, as a sphere's seam is): a solid always covers some ground, so such
    points under-describe it. When the box covers no ground either (a point or a line in plan: an upright panel,
    a block of one label), the object lies along that line, and it is on the lot when some of the line stands
    more than `reach` inside the outline."""
    lot = [(float(x), float(y)) for x, y in lot_ring]
    if len(lot) > 1 and lot[0] == lot[-1]:
        lot = lot[:-1]
    if len(lot) < 3:
        return False
    if _ring_area(lot) < 0:
        lot.reverse()
    hull = _hull(points)
    if (len(hull) < 3 or _ring_area(hull) <= 1e-12) and box is not None:
        x0, y0, x1, y1 = box
        square = _hull([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        hull = square if len(square) >= 3 and _ring_area(square) > 1e-12 else _hull([(x0, y0), (x1, y1)])
    if len(hull) >= 3 and _ring_area(hull) > 1e-12:
        part = _clip(lot, hull)
        if len(part) >= 3:
            area = abs(_ring_area(part))
            perimeter = sum(((part[i][0] - part[i - 1][0]) ** 2 + (part[i][1] - part[i - 1][1]) ** 2) ** 0.5
                            for i in range(len(part)))
            if perimeter > 0 and 2 * area / perimeter > reach:
                return True
    # However thin (or rounded to nothing: a flat wall's points are seldom exactly in a line): some of its outline
    # standing more than `reach` inside the lot. Each side of its outline is cut to the stretches of it inside the
    # lot (a jog's notch or a U's gap isn't the lot), and each stretch is searched for its deepest point (_deep).
    if not hull:
        return False
    xs, ys = [x for x, _ in hull], [y for _, y in hull]
    depth = _Depth(lot, (min(xs), min(ys), max(xs), max(ys)), 2 * reach)
    if len(hull) == 1:
        return _inside(hull[0][0], hull[0][1], lot) and depth(*hull[0]) > reach
    inside = _inside(hull[0][0], hull[0][1], lot)               # walked round: it changes only where a side crosses
    for a, b in zip(hull, hull[1:] + hull[:1]):
        if a == b:
            continue
        stretches, inside = _stretches_inside(a, b, depth.edges, lot, inside)
        if any(_deep(a, b, t0, t1, depth, reach) for t0, t1 in stretches):
            return True
    return False


class _Depth:
    """How far a point inside the lot is from the lot's outline, up to `cap` (more than that reads as `cap`): only
    the outline edges near the object's plan box (`box`, grown by `cap`), found through a grid, are measured (a
    GIS lot outline has hundreds of points, a round tank's outline thousands)."""

    def __init__(self, lot, box, cap):
        x0, y0, x1, y1 = box[0] - 2 * cap, box[1] - 2 * cap, box[2] + 2 * cap, box[3] + 2 * cap
        self.cap, self.box, self.asked = cap, (x0, y0, x1, y1), 0
        self.edges = [(a, b) for a, b in zip([lot[-1]] + lot[:-1], lot)
                      if min(a[0], b[0]) <= x1 and max(a[0], b[0]) >= x0 and min(a[1], b[1]) <= y1
                      and max(a[1], b[1]) >= y0]
        self.cell = max(cap, (x1 - x0 + y1 - y0) / 256)
        self.grid = None                                         # built at the first question

    def _build(self):
        self.grid = {}
        x0, y0, x1, y1 = self.box
        for e in self.edges:                                     # each edge in the cells along it, in the box
            (ax, ay), (bx, by) = e
            lo, hi = 0.0, 1.0                                    # the part of it inside the box (Liang-Barsky)
            for d, q0, q1 in ((bx - ax, x0 - ax, x1 - ax), (by - ay, y0 - ay, y1 - ay)):
                if d:
                    t0, t1 = sorted((q0 / d, q1 / d))
                    lo, hi = max(lo, t0), min(hi, t1)
            if lo > hi:
                continue
            length = (hi - lo) * ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
            n = int(length / (self.cell / 2)) + 1
            for k in range(n + 1):
                t = lo + (hi - lo) * k / n
                key = (int((ax + (bx - ax) * t) // self.cell), int((ay + (by - ay) * t) // self.cell))
                self.grid.setdefault(key, set()).add(e)

    def __call__(self, x, y):
        if self.grid is None:
            self._build()
        self.asked += 1
        i, j = int(x // self.cell), int(y // self.cell)
        best = self.cap * self.cap
        for di in range(-2, 3):                                  # an edge within `cap` passes within 2 cells
            for dj in range(-2, 3):
                for (ax, ay), (bx, by) in self.grid.get((i + di, j + dj), ()):
                    dx, dy = bx - ax, by - ay
                    t = min(1.0, max(0.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy))) if dx or dy else 0.0
                    best = min(best, (x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2)
        return best ** 0.5


DEPTH_QUESTIONS = 20000   # depth questions per object before the depth search gives up and says "on the lot"


def _deep(a, b, t0, t1, depth, reach, slack=0.5):
    """Whether some point of the stretch a + t (b - a), t from t0 to t1 (inside the lot), is more than `reach` from
    the lot's outline. A point's depth changes by at most its own move along the stretch, so a piece whose ends are
    d0 and d1 deep and which is L long goes no deeper than (d0 + d1 + L) / 2: pieces that can't go deeper than
    `reach` (and a `slack` share of it, so a wall drawn at the reach along a long line ends) are dropped, the others
    halved, until a point deeper than `reach` is found or none is left. No point more than `reach` (1 + slack) in,
    0.15 ft, is missed, however the lot's corners and notches fall along it. Between that and `reach`, a stretch
    whose middle goes deeper than its ends can be: one cutting across a square lot corner 0.21 ft from it goes
    0.105 ft in and reads as off, and one crossing a strip of the lot 0.29 ft wide goes 0.145 ft in. After
    DEPTH_QUESTIONS questions for one object (a long wall running just inside the line along a jagged outline), it
    counts as on the lot: the cautious answer, never a long wait on every check."""
    (ax, ay), (bx, by) = a, b
    length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
    at = lambda t: depth(ax + (bx - ax) * t, ay + (by - ay) * t)   # noqa: E731
    pieces = [(t0, t1, at(t0), at(t1))]
    while pieces:
        if depth.asked > DEPTH_QUESTIONS:
            return True
        s, e, ds, de = pieces.pop()
        if ds > reach or de > reach:
            return True
        if (ds + de + (e - s) * length) / 2 <= reach * (1 + slack):
            continue
        m = (s + e) / 2
        dm = at(m)
        pieces += [(s, m, ds, dm), (m, e, dm, de)]
    return False


def _stretches_inside(a, b, edges, lot, a_inside):
    """The stretches (t0, t1) of the segment a-b (a + t (b - a), t from 0 to 1) inside the ring `lot`, and whether
    b is inside: cut where it crosses one of the lot's outline `edges` (those near it), each piece kept when its
    middle is inside. A side crossing nothing is wholly inside or outside, as its start (`a_inside`) is."""
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    ts, touched = [0.0, 1.0], False
    for (cx, cy), (ex, ey) in edges:
        if max(cx, ex) < min(ax, bx) or min(cx, ex) > max(ax, bx) or max(cy, ey) < min(ay, by) \
                or min(cy, ey) > max(ay, by):
            continue
        fx, fy = ex - cx, ey - cy
        den = dx * fy - dy * fx
        if den == 0:                                            # parallel: on the same line, it runs along it
            touched = touched or (cx - ax) * dy - (cy - ay) * dx == 0
            continue
        t = ((cx - ax) * fy - (cy - ay) * fx) / den
        u = ((cx - ax) * dy - (cy - ay) * dx) / den
        if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
            touched = True                                      # its ends on the outline count: asked, not carried
            if 0.0 < t < 1.0:
                ts.append(t)
    if not touched:
        return ([(0.0, 1.0)] if a_inside else []), a_inside
    ts.sort()
    return [(t0, t1) for t0, t1 in zip(ts, ts[1:])
            if t1 > t0 and _inside(ax + dx * (t0 + t1) / 2, ay + dy * (t0 + t1) / 2, lot)], _inside(bx, by, lot)


# ---- the three decisions -----------------------------------------------------------------------------------------

TOUCH_GAP = 0.1           # ft: a left-out object whose box comes this near a building's box may be part of it
MAX_BLOCK_DEPTH = 32      # blocks inside blocks deeper than this: not looked into (no box), as Rhino's command did

# Why an object has no box that covers all of it: each one counts as on the lot and touching, never dropped.
NO_BOX = {
    "no_box": "the design tool gave no box for it (an empty block, an empty SubD)",
    "block_not_found": "a block whose definition isn't in the model, or nested more than 32 deep",
    "block_empty": "a block whose definition holds nothing",
    "contents_not_known": "a block or linked model whose contents may not be the design (its linked file is "
                          "missing, unreadable, or changed since it was read)",
}
# Why an object is, or isn't, left out of the check (every NO_BOX reason is left out too).
WHY = dict(NO_BOX, **{
    "on_lot": "its footprint reaches more than 0.1 ft into the lot",
    "off_lot": "its footprint doesn't reach more than 0.1 ft into the lot",
    "far_from_lot": "its box is nowhere near the lot",
    "no_lot": "there is no lot outline to measure against",
})


def _finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _sent_box(value, n, what):
    """A box as sent: None, or n finite numbers (the low corner then the high one). Anything else is refused: a
    host's mistake is never read as a box, or as no box."""
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != n or not all(_finite(v) for v in value):
        raise ValueError("%s: a box is null or %d numbers (the low corner, then the high one)" % (what, n))
    return value


def _covers(box):
    """Whether a box covers something: each low coordinate no higher than its high one (a box of one point is
    valid; RhinoCommon's BoundingBox.IsValid)."""
    if box is None:
        return False
    half = len(box) // 2
    return all(box[i] <= box[i + half] for i in range(half))


OBJECT_KEYS = ("id", "box", "points", "definition")


def _sent_object(o, what, part=False):
    if not isinstance(o, dict):
        raise ValueError("%s: each object is an object {id, box, points, definition}" % what)
    extra = sorted(set(o) - set(OBJECT_KEYS))
    if extra:            # a field this worker doesn't read is refused, never quietly ignored
        raise ValueError("%s: an object has no field %s (it has: %s)" % (what, ", ".join(extra),
                                                                          ", ".join(OBJECT_KEYS)))
    if not part and not isinstance(o.get("id"), str):
        raise ValueError("%s: each object has an id (text)" % what)
    _sent_box(o.get("box"), 6, what)
    d = o.get("definition")
    if d is not None and not isinstance(d, str):
        raise ValueError("%s: a block's definition is its id (text) or null" % what)
    return o


def _sent_definitions(definitions):
    definitions = {} if definitions is None else definitions
    if not isinstance(definitions, dict):
        raise ValueError("definitions: {id: {status, parts}}")
    for k, d in definitions.items():
        if not isinstance(d, dict) or set(d) - {"status", "parts"} or not isinstance(d.get("parts", []), list) \
                or not (d.get("status") is None or isinstance(d.get("status"), str)):
            raise ValueError("definitions: each is {\"status\": text or null, \"parts\": [objects]} (%s)" % k)
        for p in d.get("parts") or []:
            _sent_object(p, "definitions", part=True)
    return definitions


def _why_no_box(o, definitions, memo):
    """Why the object `o` has no box that covers all of it, or None when it has one (its own box). No box: the host
    gave none; or it is a placed block whose definition, at any depth, isn't there, holds nothing, isn't what the
    block is (block_contents_known: a linked file not found, not readable or changed since it was read) or holds a
    part with no box; or a block placed more than MAX_BLOCK_DEPTH blocks deep, counting from this object (not looked
    into, as Rhino's command never did). A linked block whose file has moved holds, in live Rhino 8.35 (Mac), one
    text label at the centre of the last known shape: a valid box of a single point, which said "whole" and "off
    the lot", while the shed it stands for may touch the house. Rhino leaves an invalid box out when it joins a
    block's parts, so a block holding a part with no box has its other parts' box alone.
    `memo` ({definition id: (why, how many blocks deep it goes)}, one per look) has each definition walked once,
    however many times it is placed, and its answer is the same wherever it is placed: the depth is counted at each
    placement (review round 4: the Rhino command's `wholes` kept the answer of the depth a definition was first met
    at, so beyond 32 deep the answer hung on which object was sent first)."""
    try:
        why, levels = _judged(o, definitions, memo, set())
    except RecursionError:                   # (only a malformed request: hundreds of blocks inside blocks)
        raise ValueError("objects: blocks nested too deep to read")
    if why is None and levels > MAX_BLOCK_DEPTH + 1:      # itself and 32 blocks below it are looked into
        return "block_not_found"
    return why


def _judged(o, definitions, memo, walking):
    """(why `o` has no box, or None; how many blocks deep it goes, itself included: 0 for a plain object), whatever
    depth it is placed at. A definition met again while it is being walked (only in a malformed request: a block
    can't hold itself) is not found."""
    if not _covers(o.get("box")):
        return "no_box", 0
    if "definition" not in o:
        return None, 0
    d = o.get("definition")
    if d is None or d not in definitions or d in walking:
        return "block_not_found", 1
    if d not in memo:
        entry, walking = definitions[d], walking | {d}
        if not block_contents_known(entry.get("status")):
            memo[d] = "contents_not_known", 0
        elif not entry.get("parts"):
            memo[d] = "block_empty", 0
        else:                                    # the first part with no box decides (and stops the walk)
            why, levels = None, 0
            for p in entry["parts"]:
                w, k = _judged(p, definitions, memo, walking)
                if w:
                    why = w
                    break
                levels = max(levels, k)
            memo[d] = why, levels
    why, levels = memo[d]
    return why, levels + 1


def no_box_reasons(objects, definitions=None):
    """For each object (in order): {"id", "why"}, `why` one of NO_BOX's codes when it has no box that covers all of
    it (so it can't be placed: on the lot and touching, never dropped), None when its own box covers it."""
    if not isinstance(objects, list):
        raise ValueError("objects: a list")
    definitions, memo = _sent_definitions(definitions), {}
    return [{"id": o["id"], "why": _why_no_box(o, definitions, memo)}
            for o in (_sent_object(o, "objects") for o in objects)]


def left_out_decisions(lot, objects, definitions=None, feet_per_unit=1.0):
    """For each object (in order): {"id", "left_out", "why"} (`why` one of WHY's codes). Left out when its plan
    footprint reaches more than ON_LOT_REACH (0.1 ft) into the lot's outline, partly or wholly (reaches_into_lot),
    and when it has no box that covers all of it (no_box_reasons: it can't be told off the lot, so it counts as on
    it, never dropped). An object whose box misses the lot's box grown by the reach is off the lot without being
    outlined (box_near_lot): its points are asked for only after that. With no lot (null), nothing is left out:
    the lot's own problem makes the check need review."""
    if not isinstance(objects, list):
        raise ValueError("objects: a list")
    if not _finite(feet_per_unit) or feet_per_unit <= 0:
        raise ValueError("feet_per_unit: how many feet one model unit is, a number above 0")
    objects = [_sent_object(o, "objects") for o in objects]
    definitions = _sent_definitions(definitions)
    if lot is None:
        return [{"id": o["id"], "left_out": False, "why": "no_lot"} for o in objects]
    if not isinstance(lot, dict) or sorted(lot) != ["box", "ring"] or not isinstance(lot["ring"], list):
        raise ValueError("lot: null or {\"ring\": [[x, y], ...], \"box\": [x0, y0, x1, y1]}")
    lot_box = _sent_box(lot["box"], 4, "lot")
    if lot_box is None:
        raise ValueError("lot: its box is 4 numbers")
    ring = _sent_points(lot["ring"], "lot")
    if len(set(ring)) < 3 or abs(_ring_area(ring)) <= 1e-12:     # no outline to measure against: never "off"
        raise ValueError("lot: its ring is an outline, at least 3 points around some area")
    xs, ys = [x for x, _ in ring], [y for _, y in ring]          # the box only ever grows to hold the ring, so a
    lot_box = (min(lot_box[0], min(xs)), min(lot_box[1], min(ys)),   # box sent too small can't skip an object
               max(lot_box[2], max(xs)), max(lot_box[3], max(ys)))   # (Rhino's curve box already holds its ring)
    reach = ON_LOT_REACH / feet_per_unit                       # ft -> model units
    out, memo = [], {}
    for o in objects:
        why = _why_no_box(o, definitions, memo)
        if why is None:
            x0, y0, _, x1, y1, _ = o["box"]
            box = (x0, y0, x1, y1)                             # its plan box
            if not box_near_lot(box, lot_box, reach):          # far from the lot: no outline work
                why = "far_from_lot"
            else:
                points = o.get("points")
                points = _sent_points(points() if callable(points) else points, "objects (%s)" % o["id"])
                why = "on_lot" if reaches_into_lot(ring, points, reach, box) else "off_lot"
        out.append({"id": o["id"], "left_out": why not in ("far_from_lot", "off_lot"), "why": why})
    return out


def _sent_points(points, what):
    if not isinstance(points, (list, tuple)) or not all(
            isinstance(p, (list, tuple)) and len(p) == 2 and _finite(p[0]) and _finite(p[1]) for p in points):
        raise ValueError("%s: points are a list of [x, y]" % what)
    return [(p[0], p[1]) for p in points]


def touching_decisions(objects, buildings, definitions=None, feet_per_unit=1.0):
    """For each object (in order): {"id", "touching"}: True when its 3D box comes within TOUCH_GAP (0.1 ft) of any
    building's box (edges meeting count), False when it doesn't, None when it has no box that covers all of it
    (no_box_reasons: it may be touching, so it counts as touching). Boxes say "touching" more often than the shapes
    do, which only ever makes the check more cautious."""
    if not isinstance(objects, list) or not isinstance(buildings, list):
        raise ValueError("objects and buildings: lists")
    if not _finite(feet_per_unit) or feet_per_unit <= 0:
        raise ValueError("feet_per_unit: how many feet one model unit is, a number above 0")
    objects = [_sent_object(o, "objects") for o in objects]
    definitions, memo = _sent_definitions(definitions), {}
    gap = TOUCH_GAP / feet_per_unit
    grown = [(b[0] - gap, b[1] - gap, b[2] - gap, b[3] + gap, b[4] + gap, b[5] + gap)
             for b in (_sent_box(b, 6, "buildings") for b in buildings) if _covers(b)]
    out = []
    for o in objects:
        if _why_no_box(o, definitions, memo) is not None:
            out.append({"id": o["id"], "touching": None})
            continue
        x0, y0, z0, x1, y1, z1 = o["box"]
        out.append({"id": o["id"], "touching": any(x0 <= k[3] and k[0] <= x1 and y0 <= k[4] and k[1] <= y1
                                                    and z0 <= k[5] and k[2] <= z1 for k in grown)})
    return out


# ---- what to tell the architect about a linked file (words only: no decision reads these) ------------------------

# What is wrong with a linked file, by its definition's status (ArchiveFileStatus by name): "missing", "unreadable",
# "changed"; any other status that isn't BLOCK_CONTENTS_KNOWN (none, or one this list doesn't have) is "not_known".
LINK_PROBLEM = {"LinkedFileNotFound": "missing", "LinkedFileNotReadable": "unreadable",
                "LinkedFileIsNewer": "changed", "LinkedFileIsOlder": "changed", "LinkedFileIsDifferent": "changed"}
LINK_WORDS = {
    "missing": "can't be found",
    "unreadable": "can't be read",
    "changed": "has changed since it was loaded",
    "not_known": "may have changed since it was loaded (the design tool can't say whether it is up to date)",
}
# What to do, in any design tool's words. A host adds where to click in its own menus (linked_file_words' `how`):
# Rhino's are in rhino_logic.LINK_HOW; Revit's (Manage Links: Reload, Reload From) will be the add-in's own.
LINK_FIX = {
    "missing": "relink it to where the file is now",
    "unreadable": "check that the file opens, then reload it",
    "changed": "reload it",
    "not_known": "reload it",
}


def _culprit(o, definitions, memo, seen):
    """The id of the definition, at any depth, whose linked file makes `o` "contents_not_known" (_judged's own
    path: the first part with no box decides), or None when that isn't why."""
    d = o.get("definition")
    if d is None or d not in definitions or d in seen:
        return None
    entry = definitions[d]
    if not block_contents_known(entry.get("status")):
        return d
    for p in entry.get("parts") or []:
        why, _ = _judged(p, definitions, memo, set())
        if why:
            return _culprit(p, definitions, memo, seen | {d}) if why == "contents_not_known" else None
    return None


def linked_file_problems(objects, definitions=None):
    """For each object (in order): {"id", "definition", "problem"}: for one with no box because a linked file isn't
    up to date (no_box_reasons' "contents_not_known"), the id of the definition (at any depth) whose file it is and
    what is wrong with that file (LINK_PROBLEM's word, "not_known" for any other status); else both None. Words
    only: the object stays left out and counts as touching whatever this says."""
    if not isinstance(objects, list):
        raise ValueError("objects: a list")
    definitions, memo = _sent_definitions(definitions), {}
    out = []
    for o in (_sent_object(o, "objects") for o in objects):
        d = _culprit(o, definitions, memo, set()) if _why_no_box(o, definitions, memo) == "contents_not_known" \
            else None
        status = None if d is None else str(definitions[d].get("status")).split(".")[-1]
        out.append({"id": o["id"], "definition": d, "problem": None if d is None else LINK_PROBLEM.get(status, "not_known")})
    return out


def linked_file_words(name, problem, how=None, path=None):
    """The sentence telling the architect about one linked file: what is wrong with it (LINK_WORDS), where it was
    looked for when it is missing or unreadable (`path`, as the host has it), and what to do (LINK_FIX), with where
    to click in the host's own menus (`how`, the host's words; none: the plain fix alone). For example "Linked file
    'garage.3dm' has changed since it was loaded: reload it (...) so Gordium can measure it"."""
    if problem not in LINK_WORDS:
        raise ValueError("problem: one of %s" % ", ".join(sorted(LINK_WORDS)))
    where = " at %s" % path if path and problem in ("missing", "unreadable") else ""
    return "Linked file '%s' %s%s: %s%s so Gordium can measure it" % (
        name, LINK_WORDS[problem], where, LINK_FIX[problem], " (%s)" % how if how else "")
