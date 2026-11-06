"""The decisions the Rhino command makes, as plain functions (no Rhino, Python 3.9), so CI can test them. The
Rhino script (apps/rhino_plugin/gordium_rhino.py) imports this file directly.
"""

import contextlib
import json
import math
import sys
import types

# Host-neutral code lives in host_core/ (facts, streets, lookup, the start box, the place, freshness, the report's
# and the panel's words, the neighbourhood, the box's edits, the worker client), moved there unchanged so a second
# host (a Revit add-in) can use it too. Every moved name is still offered here, the very same object
# (logic.X is host_core.<module>.X), so the Rhino plugin and its tests are unchanged.
if __package__:              # design_checker.rhino_logic: the checker, the tests
    from .host_core import facts as _facts, lookup as _lookup, place as _place, start_box as _start_box
    from .host_core import streets as _streets
    from .host_core import context as _context, edits as _edits, freshness as _freshness, report as _report
    from .host_core import panel_words as _panel_words, worker_client as _worker_client
else:                        # Rhino: this file by its folder on sys.path (gordium_rhino.py), so host_core is beside it
    for _name in [n for n in sys.modules if n == "host_core" or n.startswith("host_core.")]:
        del sys.modules[_name]           # a copy loaded before (another checkout, an older load): this folder's
    from host_core import facts as _facts, lookup as _lookup, place as _place, start_box as _start_box
    from host_core import streets as _streets
    from host_core import context as _context, edits as _edits, freshness as _freshness, report as _report
    from host_core import panel_words as _panel_words, worker_client as _worker_client
HOST_CORE = (_place, _streets, _facts, _lookup, _start_box, _freshness, _report, _panel_words, _context, _edits,
             _worker_client)
MOVED = {name: module for module in HOST_CORE for name in module.__all__}   # name -> the module that defines it
globals().update({name: getattr(module, name) for name, module in MOVED.items()})


class _Facade(types.ModuleType):
    """This module, refusing to rebind a moved name: `logic.X = ...` (or monkeypatch.setattr(logic, "X", ...))
    would change only this module's copy, never the one host_core's own functions read, so the change would
    silently do nothing. Patch the name where it is defined (MOVED[name]) and in every module that imports it."""

    def __setattr__(self, name, value):
        if name in MOVED:
            raise AttributeError("%s moved to %s: set it there, not on rhino_logic" % (name, MOVED[name].__name__))
        super().__setattr__(name, value)

    def __delattr__(self, name):
        if name in MOVED:
            raise AttributeError("%s moved to %s: delete it there, not on rhino_logic" % (name, MOVED[name].__name__))
        super().__delattr__(name)


if __name__ in sys.modules:          # imported (not run from a file by a loader that keeps it to itself)
    sys.modules[__name__].__class__ = _Facade


LAYERS = {"lot": "Site", "building": "Building"}
ID_KEY = "gordium:id"                   # the same keys as model_measurement.read_3dm (a test keeps them equal)
FLOOR_KEY = "gordium:floor"            # user text on a floor block GordiumStart drew: "<story>;<height drawn, ft>"
MASSING = "Gordium::Massing"            # where GordiumStart draws the starting building: building objects too
MASSING_ROOF = MASSING + "::Roof"       # its roof's sublayer (the architect's own roof goes there too): a building
SOLIDS = ("Brep", "Extrusion", "Mesh", "SubD")
DRAWING_AIDS = ("Curve", "Point", "PointCloud", "TextDot", "AnnotationBase", "Hatch", "TextEntity", "Dimension",
                "Leader", "LinearDimension", "AngularDimension", "RadialDimension", "OrdinateDimension")


def massing_floor(n):
    """The sublayer of the starting house's floor n (1 up): Gordium::Massing::Floor 1, … (Ben, 2026-10-21)."""
    return MASSING + "::Floor " + str(int(n))


def on_layer(full_path, layer):
    """A layer or one of its sublayers ("Building::Garage")."""
    return full_path == layer or full_path.startswith(layer + "::")


CONTEXT = "Gordium::Context"            # the context map (neighbouring parcels, streets, notes): drawing only
ENVELOPE = "Gordium::Envelope"          # the curves the architect snaps to (the buildable outline, the yard lines)
ENVELOPE_KEY = "gordium_envelope"       # on each of those curves: what it is (Gordium's own, redrawn each check)
CONTEXT_KEY = "gordium_context"         # on each context object: the endpoints.yaml source it was drawn from
HOLDING_LAYER = "Gordium::Replaced (Cancel restores)"   # objects a start box replaced, until Draw (BoxSession)
HELD_FROM = "gordium_held_from"                          # on each held object: the layer it came from
ADDED_BY = "gordium_added"                               # on each object a start box drew: its session, until Draw
HELD_BY = "gordium_held_by"                              # on each held object: the session holding it
OPEN_SESSIONS = set()          # the sessions of start boxes open now (recovery never touches theirs: review round 4)


class BoxGate:
    """One start box at a time (review round 4: Edit site… from the panel during a pick opened a second box)."""

    def __init__(self):
        self.open = False

    def enter(self):
        if self.open:
            return False
        self.open = True
        return True

    def leave(self):
        self.open = False


def envelope_outlines(env, plan):
    """The buildable outline(s) the blue envelope is drawn on (feet): on a tax-map lot the cautious one, every lot
    line 2'-0" nearer (each piece of it; none where nothing is left: the as-drawn outline is then only the dashed
    curve on Gordium::Envelope), so the envelope shows where a building complies however the tax map's lines lie
    (Ben, 2026-10-21: "cautious envelope on tax-map lots"); on a survey the outline as drawn. Largest first, by the
    shoelace area (_ring_area): plain Python, because Rhino's own Python runs this module and has no shapely (every
    check in Rhino failed "No module named 'shapely'")."""
    outline = (env or {}).get("outline")
    if not outline:
        return []
    plan = plan or {}
    cautious = plan.get("buildable_cautious")
    if not plan.get("lot_from_tax_map") or cautious is None:
        return [outline]
    rings = [cautious] if cautious and isinstance(cautious[0][0], (int, float)) else list(cautious)
    return sorted(rings, key=lambda r: -abs(_ring_area(r)))


def envelope_curves(plan):
    """The curves drawn on Gordium::Envelope for the architect to snap to (Osnap), from check.plan, in feet: each
    {"points" [[x, y], ...], "closed", "dashed", "what"}. The buildable outline (on a tax-map lot the cautious one,
    every lot line 2'-0" nearer, solid; the outline as drawn dashed) and each yard's required line in full (dashed
    on a tax-map lot: it is as drawn). Never measured (classify); redrawn at every check."""
    plan = plan or {}
    tax = bool(plan.get("lot_from_tax_map"))        # dashed whenever the lot is the tax map's, whatever is left 2'-0"
    cautious, drawn = plan.get("buildable_cautious") or [], plan.get("buildable")   # in (review of feature 4, F3)
    if cautious and isinstance(cautious[0][0], (int, float)):       # (one ring)
        cautious = [cautious]
    out = []
    for ring in cautious if tax else []:
        out.append({"points": ring, "closed": True, "dashed": False, "what": "buildable outline (cautious)"})
    if drawn:
        out.append({"points": drawn, "closed": True, "dashed": tax,
                    "what": "buildable outline" + (" (as drawn, tax map)" if tax else "")})
    for y in plan.get("yard_lines") or []:
        out.append({"points": y["points"], "closed": False, "dashed": tax,
                    "what": "required line: " + (y.get("name") or y.get("measure") or "yard")})
    return out


def classify(full_path, kind, holds_building=False):
    """What the Rhino command does with one object, from its layer's full path and its geometry's type name:
    "lot" (a curve on the lot layer: a possible lot outline), "building" (a solid or mesh on the building layer),
    None (anything else, ignored), or a problem sentence. Nothing that could be part of a building is dropped:
    a block on the building layer, or a block holding building objects wherever it is placed, and any other
    geometry on the building layer, are problems, so the checker says NEEDS REVIEW."""
    if on_layer(full_path, HOLDING_LAYER):           # held by an open start box: never measured or sent
        return None
    if on_layer(full_path, CONTEXT):                 # the neighbourhood drawn for context: never measured or sent
        return None
    if on_layer(full_path, ENVELOPE) and kind.endswith("Curve"):   # the curves to snap to: Gordium's, never
        return None                                  # measured (anything else there is judged as anywhere: F7)
    if on_layer(full_path, MASSING):
        full_path = LAYERS["building"]
    if kind.startswith("InstanceReference") and (on_layer(full_path, LAYERS["building"]) or holds_building):
        return "a block on the Building layer can't be measured yet (explode it)"
    if on_layer(full_path, LAYERS["lot"]):
        return "lot" if kind.endswith("Curve") else None
    if not on_layer(full_path, LAYERS["building"]):
        return None
    if kind in SOLIDS:
        return "building"
    if kind in DRAWING_AIDS or kind.endswith("Curve") or kind.endswith("Dimension"):
        return None
    return "a " + kind + " on the Building layer can't be measured yet (explode it or turn it into a solid)"


def own_buildings(objects):
    """The ids of the architect's buildings among `objects` ((id, layer full path, geometry type name, whether it is
    a block holding a building)), as the checker sees them (classify): solids on Building and its sublayers, and
    everything there it can't measure (a block, a surface: each a problem the check names), and a block holding a
    building wherever it is placed; never the starting house (Gordium::Massing) or what a start box holds. What a
    reset asks about and clears (re-lookup review round 2: blocks and surfaces on Building were left behind)."""
    return [i for i, layer, kind, holds in objects
            if not on_layer(layer, MASSING) and classify(layer, kind, holds) not in (None, "lot")]


def dock_host(hosts, serial):
    """The docked panel to fill for the document in front: Rhino makes one per document window (keyed by the
    document's number); a panel made without one (key 0) serves when the front document has none."""
    if serial is not None and serial in hosts:
        return hosts[serial]
    return hosts.get(0)


def place_panel_now(placed):
    """Whether to size and place the panel's floating window: only until it has been seen shown (Rhino's own
    200 x 200 window), never again after ("docked" or "floating"): the architect's own size and place stay
    (round 1: it jumped back to the right edge on every live re-check)."""
    return placed is None


def block_span(entry, solid_bottom=None, solid_top=None):
    """The heights (feet) a coloured block is cut from in Rhino: the checker's (check.plan), reaching to the real
    solid's own top (and, for a yard strip, its own bottom) when Rhino's solid goes further. The checker measures
    only the faces it can read (a curved vault is left out: its height needs review), so its top can be the wall
    tops, while the vault above them is just as much over the limit (the Rhino check of #28 at fc0b023: only the
    band from 35 to 36 ft was coloured, under a vault to 42 ft). A height block always starts at the limit."""
    base, top = entry["base"], entry["top"]
    if solid_top is not None:
        top = max(top, solid_top)
    if solid_bottom is not None and entry.get("why") != "height":
        base = min(base, solid_bottom)
    return base, top


def offending_pieces(pieces, block):
    """What a coloured block draws: the building's own part inside it (Rhino's boolean intersection, `pieces`), or
    the block itself when the intersection gave nothing (it failed, or the building is a mesh or a solid Rhino
    can't cut; a block instance is never measured: it is a setup problem, "explode it"), so a failing part is never
    left uncoloured because a boolean failed."""
    kept = [p for p in pieces or [] if p is not None]
    return kept or [block]


def draws_in(checked, viewport):
    """Whether a result is drawn in a viewport: only in the document it is the result for (Rhino for Mac keeps
    several models open side by side; one model's verdict never shows on another)."""
    return checked is not None and checked == viewport


def after_confirm(choice):
    """What the confirm dialog's answer means: "keep" (OK), "change" (Change…), or "cancel" (closed, Esc):
    a cancel saves nothing, since nothing is used until the architect says OK."""
    return {"ok": "keep", "change": "change"}.get(choice, "cancel")


def accepts_pick(object_id, candidate_ids):
    """Whether a clicked object can be saved as the lot or the main building: only one of the candidates the
    check reads (a closed outline on the Site layer, a solid on the Building layer); any other pick would be
    saved and then dropped on the next check, so the pick prompt lets only candidates be clicked."""
    return object_id in candidate_ids


def option_names(kind, count):
    """Command-line options naming each candidate ("Lot1", "Lot2"), so one that can't be clicked (locked or
    hidden: Rhino won't select it) can still be chosen."""
    return ["%s%d" % (kind, i + 1) for i in range(count)]


def crosses(segment, x, y, w, h):
    """Whether the segment ((x1, y1), (x2, y2)) touches the w × h box at (x, y) (screen pixels): clipped to the
    box's slab in x, then in y (Liang–Barsky)."""
    (x1, y1), (x2, y2) = segment
    t0, t1, dx, dy = 0.0, 1.0, x2 - x1, y2 - y1
    for p, q in ((-dx, x1 - x), (dx, x + w - x1), (-dy, y1 - y), (dy, y + h - y1)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def beside_line(a, b, w, h, gap=6):
    """Where a w × h label for the dimension line a–b goes (its top left, screen pixels): beside the line, never on
    it. A mostly horizontal line has it above, centred; a mostly vertical one to its right, centred."""
    (xa, ya), (xb, yb) = a, b
    if abs(xb - xa) >= abs(yb - ya):
        return (xa + xb) / 2 - w / 2, min(ya, yb) - gap - h
    return max(xa, xb) + gap, (ya + yb) / 2 - h / 2


def hint_text(hint, buttons):
    """The detail pane's hint as words, or None: never the words of a button it already shows ("Pick the main
    building…", "Enter …"), nor "Add to check…" (a row a left-out solid makes cautious names it in its reason; the
    one button is on the left-out row itself: the review, F2)."""
    if not hint or hint.rstrip("…") in {b.rstrip("…") for b in buttons} or hint == "Add to check…":
        # (a button's words end in "…" where the hint's may not: "Enter bedrooms and parking spaces")
        return None
    return hint


LABEL_MIN_LOT_PX = 120      # a lot smaller than this on screen (zoomed out to the neighbourhood): no labels on it


def label_width(text, size):
    """A one-line label's width on screen, pixels (its text and its backing box's margins)."""
    return len(text) * size * 0.58 + 14


DIM_TICK_PX = 10        # a dimension's architectural tick: this long on screen, at 45° to its line
HALO_PX = 1           # a dimension's halo: this many pixels each side of its line
FAINT_ALPHA = 110       # the required line, faint: the status colour at this opacity (of 255)


# a yard's dimension and its label, placed on screen as a drawing would (Rhino checks of #29, 2026-10-25)
DIM_RGB = {"complies": ((92, 96, 100), (176, 180, 184)),          # (light viewport, dark viewport): neutral grey,
           "needs_review": ((138, 88, 0), (233, 180, 76)),          # amber, red: colour only what's wrong
           "does_not_comply": ((184, 55, 31), (240, 122, 112))}
REQUIRED_RGB = ((96, 96, 96), (190, 190, 190))     # the required line: a clear dashed grey, with its "min" tag
# (darker on a light viewport, lighter on a dark one than the first version: Rhino check of #29 at f6642a9)
DIM_LABEL_H_PX = 18     # a dimension's label: its height on screen
DIM_LABEL_GAP_PX = 4    # and its gap from the dimension line (and past the line's outer end)


def dim_rgb(status, dark):
    """A dimension's colour (r, g, b): red fails, amber needs review, a neutral dark grey (light on a dark viewport)
    complies: drafting's convention, and Ben's "colour only what's wrong"."""
    return DIM_RGB.get(status, DIM_RGB["complies"])[1 if dark else 0]


def rect_quad(box):
    """An (x, y, w, h) screen box as its four corners."""
    x, y, w, h = box
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _segments_cross(p, q, r, s_):
    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2, d3, d4 = side(r, s_, p), side(r, s_, q), side(p, q, r), side(p, q, s_)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def _point_in(pt, poly):
    x, y = pt
    hit = False
    for k in range(len(poly)):
        (x0, y0), (x1, y1) = poly[k - 1], poly[k]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def shapes_hit(a, b):
    """Whether two screen polygons (lists of corners) overlap: an edge of one crosses the other's, or one lies
    inside the other."""
    for k in range(len(a)):
        for j in range(len(b)):
            if _segments_cross(a[k - 1], a[k], b[j - 1], b[j]):
                return True
    return bool(a and b) and (_point_in(a[0], b) or _point_in(b[0], a))


def _along(a, b):
    n = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
    return ((b[0] - a[0]) / n, (b[1] - a[1]) / n), n


def _point_segment(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    t = 0.0 if n <= 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return ((p[0] - a[0] - t * dx) ** 2 + (p[1] - a[1] - t * dy) ** 2) ** 0.5


TAG_SIZE = 11            # a "min" tag's text size (readable at the default zoom: Rhino check of #29 at f6642a9)
VIEW_MARGIN_PX = 3      # every number and tag stays this far inside the view


def dim_number(mark, proposed, status):
    """What a dimension shows on the drawing, as a drawing does: its number only, "✕ " or "? " before it when the
    yard fails or needs review (colour says the rest). Its name, what it needs and "(approx.)" are the panel's and
    the notice's (Rhino checks of #29: a long label never fit a plan)."""
    return (mark + " " if status in ("does_not_comply", "needs_review") and mark else "") + proposed


def inside_view(shape, view, margin=VIEW_MARGIN_PX):
    """Whether a screen polygon lies wholly inside the view (w, h), `margin` px in. True without a view."""
    if not view:
        return True
    return all(margin <= x <= view[0] - margin and margin <= y <= view[1] - margin for x, y in shape)


PRIORITY = {"does_not_comply": 0, "needs_review": 1}      # what is wrong placed first: it gets the clear spots


#                                        (0.7 × 11 px ≈ 8 px: the smallest that still reads)


#                        of #29 at 5891efc: the rear number touched an edge length)


def limit_label_spot(line, house, w, h=18, view=None, gap=8, taken=()):
    """Where an elevation's "Height limit 35'-0"" label goes (screen): past an end of the limit line, outside the
    building's extent (`house`: its box on screen, x0, y0, x1, y1), centred on the line's height, in view; the
    left end first, and the end whose spot covers nothing drawn (`taken`, boxes: the height's number, the status
    box, the notice) before one that does. It never covers the coloured parts (Rhino check of #28 at fc0b023).
    (x, y) of its top left, or None when neither end has room in view."""
    (ax, ay), (bx, by) = sorted(line)
    spots = [(min(ax, house[0] if house else ax) - gap - w, ay - h / 2),
             (max(bx, house[2] if house else bx) + gap, by - h / 2)]
    shown = [(x, y) for x, y in spots if inside_view(rect_quad((x, y, w, h)), view)]
    for x, y in shown:
        if not any(shapes_hit(rect_quad((x, y, w, h)), rect_quad(t)) for t in taken):
            return x, y
    return shown[0] if shown else None


def _bbox(shape):
    xs, ys = [p[0] for p in shape], [p[1] for p in shape]
    return min(xs), min(ys), max(xs), max(ys)


def dim_ticks(a, b, size=DIM_TICK_PX):
    """A drawing-style dimension's two end ticks on screen: at each end of the line a to b, a short slash at 45°
    to the line (as an architect draws one, whichever way the line runs), `size` pixels long. [] for a line of no
    length on screen (seen end on)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = (dx * dx + dy * dy) ** 0.5
    if n < 1e-9:
        return []
    ux, uy = dx / n, dy / n
    sx, sy = (ux - uy) * 0.5 ** 0.5 * size / 2, (uy + ux) * 0.5 ** 0.5 * size / 2   # the line turned 45°
    return [((p[0] - sx, p[1] - sy), (p[0] + sx, p[1] + sy)) for p in (a, b)]


def dims_shown(zoomed_in, elevation=False):
    """Whether a yard's dimension (its line, ticks, faint required line) is drawn at all: only at working zoom
    (zoomed out to the neighbourhood every dimension gives way with the labels, labels_shown), and never in an
    elevation (Front, Right…), where every yard's line would lie flat on the ground line. Its words also follow
    Show on-screen labels (yard_label_shown) and show in plan only. The height's dimension is the other way round:
    elevations only."""
    return bool(zoomed_in) and not elevation


def labels_shown(lot_px):
    """Whether the lot's plan labels (its edge lengths, its yards) are drawn at this zoom: not when the lot on
    screen (`lot_px`, its larger side, pixels; None: no lot drawn, nothing to judge by) is under LABEL_MIN_LOT_PX,
    zoomed out to the neighbourhood (Ben, on #23's capture: there they piled into a column with long leaders).
    Every one of them, together; zoomed back in, all of them again. The status box isn't a plan label: it stays.
    At working zoom nothing is hidden for being long (review round 2, R5: judged label by label, a four-view lot
    lost its yard labels, a failing shortfall with them, and 106's 10'-4" edge its length): a short edge's label
    sits beside it with a leader (needs_leader)."""
    return lot_px is None or lot_px >= LABEL_MIN_LOT_PX


def needs_leader(line_px, width):
    """A lot edge shorter on screen than its label: the label goes beside it, off the other lines, with a short
    leader back to the edge's middle (as a dimension too short for its text is drawn)."""
    return line_px < width


def leader_end(point, box):
    """Where a leader from `point` (x, y) meets a label's `box` (left, top, width, height): the box's nearest
    point (on its edge, or `point` itself if inside)."""
    left, top, w, h = box
    return (min(max(point[0], left), left + w), min(max(point[1], top), top + h))


def place_label(line, w, h, obstacles=(), taken=(), gap=6, view=None):
    """Where a w × h label for the dimension `line` ((x1, y1), (x2, y2), screen pixels) goes: (left, top, clear).
    The spots beside its line are tried in turn (a mostly horizontal line: above, below, each centred, then
    shifted to either end; a mostly vertical one: right, left, then shifted up or down); the first that crosses
    no line in `obstacles` (other dimensions, the lot's and the house's edges; its own line always) and covers
    no box in `taken` is used. With `view` (its width and height), only spots wholly on screen are tried (seen in
    Rhino: "Side yard, Southwest …, needs 10'-0" (approx.)" went 15 px off the left edge). If none is clear, the
    first spot, kept on screen, and False (the caller moves it off the others)."""
    (xa, ya), (xb, yb) = line
    x0, x1, y0, y1 = min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)
    # nearest the line's middle first: centred on either side, then shifted along it (a label far along its line
    # reads as another edge's: seen in Rhino, the west edge's length ended up under the front edge)
    if x1 - x0 >= y1 - y0:
        xs = [(x0 + x1) / 2 - w / 2, x1 - w, x0, x0 - w - gap, x1 + gap]
        spots = [(x, top) for x in xs for top in (y0 - gap - h, y1 + gap)]
    else:
        ys = [(y0 + y1) / 2 - h / 2, y0, y1 - h, y0 - h - gap, y1 + gap]
        spots = [(left, y) for y in ys for left in (x1 + gap, x0 - gap - w)]
    lines = list(obstacles) + [line]
    on_screen = [(x, y) for x, y in spots if view is None or (0 <= x and x + w <= view[0] and 0 <= y and y + h <= view[1])]
    for left, top in on_screen:
        if not any(crosses(s, left, top, w, h) for s in lines) and \
                not any(left < a + c and a < left + w and top < b + e and b < top + h for a, b, c, e in taken):
            return left, top, True
    left, top = (on_screen or spots)[0]
    if view is not None:                     # nowhere beside it on screen: the first spot, moved onto the screen
        left, top = min(max(left, 0), max(view[0] - w, 0)), min(max(top, 0), max(view[1] - h, 0))
    return left, top, False


def _point_seg(px, py, line):
    """A point's distance from a segment (screen pixels)."""
    (ax, ay), (bx, by) = line
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def box_gap(line, box):
    """How far a box (left, top, w, h) is from a screen line ((x1, y1), (x2, y2)), exactly: 0 when they touch."""
    left, top, w, h = box
    if crosses(line, left, top, w, h):
        return 0.0
    corners = ((left, top), (left + w, top), (left, top + h), (left + w, top + h))
    ends = [((max(left - x, 0, x - left - w) ** 2 + max(top - y, 0, y - top - h) ** 2) ** 0.5) for x, y in line]
    return min(ends + [_point_seg(x, y, line) for x, y in corners])


LABEL_MIN_SIZE = 9                 # a plan label's text is never smaller (readable on screen)
LABEL_LEAD_REACH = 3               # how far a led label may sit from its line: this many label heights
LABEL_STEP = 6                     # the lattice the spots near a line are tried on, screen pixels


def label_height(rows, size):
    """A plan label's height on screen: its lines (size + 5 px each: 16 px at 11 pt) and 4 of margin."""
    return 4 + (size + 5) * rows


def _over(box, other):
    """Whether two (left, top, w, h) boxes overlap (touching edges don't)."""
    return min(box[0] + box[2], other[0] + other[2]) > max(box[0], other[0]) and \
        min(box[1] + box[3], other[1] + other[3]) > max(box[1], other[1])


def _inside(x, y, poly):
    """Whether a point is inside a polygon (screen points; even-odd)."""
    inside = False
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def box_over_shape(box, poly):
    """Whether a box (left, top, w, h) covers any of a polygon (its screen points), 3 px around it included."""
    left, top, w, h = box[0] - 3, box[1] - 3, box[2] + 6, box[3] + 6
    if len(poly) < 3:
        return False
    if any(crosses(edge, left, top, w, h) for edge in zip(poly, poly[1:] + poly[:1])):
        return True
    if any(left <= x <= left + w and top <= y <= top + h for x, y in poly):
        return True
    return _inside(left + w / 2, top + h / 2, poly)


LABEL_INSET = 4                    # a plan label stays this far inside the view (#29 at e4e5018: one on its edge)
AXIS_ICON_PX = 80                  # Rhino's world-axis icon, bottom left of every view: a square this wide kept clear
# (the Rhino job at 8bfabdd: it spans x 34-76, y 593-634 in a 657 x 668 view), 3 px more around it
AXIS_ICON_SCALE = 1.0              # the display's scaling where screen pixels are physical (set by the plugin)


def axis_icon_box(view):
    """Where Rhino draws the world-axis icon in a view (w, h): its bottom-left corner, AXIS_ICON_PX (scaled by
    AXIS_ICON_SCALE) and 3 px around it (#29 at e4e5018: a label on it)."""
    side = int(round(AXIS_ICON_PX * AXIS_ICON_SCALE)) + 3
    return 0, view[1] - side, side, side


def label_breaks_hard(line, box, view, hard_boxes=(), hard_lines=(), hard_shapes=(), placed=()):
    """Which HARD rule a plan label's box (left, top, w, h) breaks, or None. HARD: on screen; over no building
    footprint nor coloured part (`hard_shapes`: their outlines on screen, 3 px around them), nor the notice, the
    status box or the north arrow (`hard_boxes`, 3 px around them), nor a label already placed (`placed`: a label is
    never hidden under another, the Rhino job at 4bb6d4d); 3 px off its own dimension `line` (the front yard's ran along
    its own label's edge, the Rhino job at 822fb6f) and every line in
    `hard_lines` (every other yard's dimension, 3 px around it: the southwest label sat 1 px beside the front's)."""
    left, top, w, h = box
    if view is not None:
        i_ = LABEL_INSET
        if left < i_ or top < i_ or left + w > view[0] - i_ or top + h > view[1] - i_:
            return "off screen or on its edge"
        if _over(box, axis_icon_box(view)):
            return "over the world-axis icon"
    if any(box_over_shape(box, shape) for shape in hard_shapes):
        return "over a building or its coloured part"
    if any(_over(box, (a - 3, b - 3, c + 6, e + 6)) for a, b, c, e in hard_boxes):
        return "over the notice, the status box or the north arrow"
    if any(_over(box, other) for other in placed):
        return "over another label"
    if crosses(line, left - 3, top - 3, w + 6, h + 6):
        return "on its own line"
    if any(crosses(other, left - 3, top - 3, w + 6, h + 6) for other in hard_lines if other != line):
        return "on another yard's dimension"
    return None


def label_spots(line, w, h, reach, step=LABEL_STEP):
    """Every spot for a w × h label within `reach` of its dimension `line` (screen pixels), on a `step` lattice from
    the line's own corner, nearest first."""
    (xa, ya), (xb, yb) = line
    x0, x1, y0, y1 = min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)
    spots = []
    nx, ny = int((x1 - x0 + w + 2 * reach) / step) + 1, int((y1 - y0 + h + 2 * reach) / step) + 1
    for j in range(ny):
        top = y0 - h - reach + j * step
        for i in range(nx):
            left = x0 - w - reach + i * step
            gap = box_gap(line, (left, top, w, h))
            if gap <= reach:
                spots.append((gap, left, top))
    spots.sort()
    return spots


def _seg_x_in_band(seg, ylo, yhi):
    """The x extent of a segment's part inside the horizontal band ylo..yhi (screen pixels), or None."""
    (x1, y1), (x2, y2) = seg
    if max(y1, y2) < ylo or min(y1, y2) > yhi:
        return None
    if abs(y2 - y1) < 1e-12:
        return min(x1, x2), max(x1, x2)
    ta, tb = (ylo - y1) / (y2 - y1), (yhi - y1) / (y2 - y1)
    t0, t1 = max(0.0, min(ta, tb)), min(1.0, max(ta, tb))
    xa_, xb_ = x1 + t0 * (x2 - x1), x1 + t1 * (x2 - x1)
    return min(xa_, xb_), max(xa_, xb_)


class _LabelField:
    """The things a plan label must keep off, prepared once for a label (the Rhino job at 822fb6f: testing every
    spot against every obstacle took up to 309 ms a label). For one row of spots (a top, a w × h label) each
    obstacle is the stretch of lefts it rules out, worked out once for the row: a box or a placed label its width
    plus the label's; a line or a building's outline the extent of its part inside the row's band (3 px around),
    plus the label's width. That is exact for boxes, lines and convex outlines, and never less than the truth for
    others (a spot it lets through always keeps the HARD rules; label_breaks_hard still checks the one chosen)."""

    def __init__(self, line, view, hard_boxes=(), hard_lines=(), hard_shapes=(), placed=(), soft_lines=()):
        self.view = view
        self.rects = [(a - 3, b - 3, c + 6, e + 6) for a, b, c, e in hard_boxes] + [tuple(p)[:4] for p in placed]
        if view is not None:
            self.rects.append(axis_icon_box(view))
        self.segs = [(line, 3)] + [(d, 3) for d in hard_lines if d != line]
        self.polys = []
        for shape_ in hard_shapes:
            if len(shape_) >= 3:
                pts = [tuple(q) for q in shape_]
                self.polys.append((list(zip(pts, pts[1:] + pts[:1])), min(q[1] for q in pts), max(q[1] for q in pts)))
        self.soft = [s_ for s_ in soft_lines if s_ != line]

    def _blocked(self, top, w, h):
        out = []
        for rx, ry, rw, rh in self.rects:
            if min(top + h, ry + rh) > max(top, ry):
                out.append((rx - w, rx + rw))
        for seg, m in self.segs:
            r = _seg_x_in_band(seg, top - m, top + h + m)
            if r is not None:
                out.append((r[0] - m - w, r[1] + m))
        ylo, yhi = top - 3, top + h + 3
        for edges, pymin, pymax in self.polys:
            if pymax < ylo or pymin > yhi:
                continue
            lo = hi = None
            for edge in edges:
                r = _seg_x_in_band(edge, ylo, yhi)
                if r is not None:
                    lo = r[0] if lo is None else min(lo, r[0])
                    hi = r[1] if hi is None else max(hi, r[1])
            if lo is not None:
                out.append((lo - 3 - w, hi + 3))
        return out

    def pieces(self, top, w, h, base, step, n):
        """The runs of lattice spots (lefts base + i·step, i < n) on the row at `top` that keep every HARD rule,
        each cut where the number of lot lines a label there crosses changes: [(i0, i1, crossed)]."""
        if self.view is not None and (top < LABEL_INSET or top + h > self.view[1] - LABEL_INSET):
            return []
        lo_i, hi_i = 0, n - 1
        if self.view is not None:
            lo_i = max(lo_i, int(math.ceil((LABEL_INSET - base) / step - 1e-9)))
            hi_i = min(hi_i, int(math.floor((self.view[0] - LABEL_INSET - w - base) / step + 1e-9)))
        if lo_i > hi_i:
            return []

        def index_span(a, b):
            return int(math.ceil((a - base) / step - 1e-9)), int(math.floor((b - base) / step + 1e-9))
        blocked = sorted(index_span(a, b) for a, b in self._blocked(top, w, h))
        free, at = [], lo_i
        for a, b in blocked:
            if b < at:
                continue
            if a > at:
                free.append((at, min(a - 1, hi_i)))
            at = max(at, b + 1)
            if at > hi_i:
                break
        if at <= hi_i:
            free.append((at, hi_i))
        free = [(a, b) for a, b in free if a <= b]
        if not free or not self.soft:
            return [(a, b, 0) for a, b in free]
        soft = []
        for seg in self.soft:
            r = _seg_x_in_band(seg, top, top + h)
            if r is not None:
                soft.append(index_span(r[0] - w, r[1]))
        out = []
        for a, b in free:
            cuts = sorted({a, b + 1} | {c for s0, s1 in soft for c in (s0, s1 + 1) if a < c <= b})
            for c0, c1 in zip(cuts, cuts[1:]):
                out.append((c0, c1 - 1, sum(s0 <= c0 <= s1 for s0, s1 in soft)))
        return out


def _nearest_index(line, top, w, h, base, step, i0, i1):
    """The spot in the run i0..i1 nearest its line (a label's distance from its line along a row is convex: one
    least; worked out directly for a level or plumb line, else by a ternary search)."""
    (xa, ya), (xb, yb) = line
    if abs(xa - xb) < 1e-9 or abs(ya - yb) < 1e-9:      # level or plumb: the x gap alone decides along a row
        lo = int(math.ceil((min(xa, xb) - w - base) / step - 1e-9))
        hi = int(math.floor((max(xa, xb) - base) / step + 1e-9))
        return i0 if hi < i0 else i1 if lo > i1 else max(i0, lo)

    def g(i):
        return box_gap(line, (base + i * step, top, w, h))
    a, b = i0, i1
    while b - a > 2:
        m1, m2 = a + (b - a) // 3, b - (b - a) // 3
        if g(m1) <= g(m2):
            b = m2
        else:
            a = m1
    return min(range(a, b + 1), key=lambda i: (g(i), i))


def place_dim_label(line, text, size, view, hard_boxes=(), hard_lines=(), soft_boxes=(), soft_lines=(),
                    hard_shapes=(), placed=()):
    """Where a plan label for the dimension `line` goes (screen pixels), by one complete set of rules (the Rhino job
    at 319dc5d: each round's fix moved the southwest yard's label onto the next obstacle nobody had listed):
    - HARD, never broken (label_breaks_hard): on screen; over no building footprint or coloured part
      (`hard_shapes`), nor the notice, the status box or the north arrow (`hard_boxes`), nor a label placed before
      (`placed`); 3 px off its own line and every other yard's dimension (`hard_lines`).
    - SOFT, least first: other labels covered (`soft_boxes`), then, for a led label, the HARD things its leader
      crosses, then lines crossed (`soft_lines`: the lot's edges), then its distance from its own line.
    - Within one label height of its line, on one line, then on two (name, then numbers: label_lines), the spots
      on a LABEL_STEP lattice; then smaller, a point at a time down to LABEL_MIN_SIZE; then, at its own size, up to
      LABEL_LEAD_REACH label heights away; then the nearest spots anywhere on screen that break no HARD rule, at
      its own size, then the smallest. A label more than 8 px from its line is led to it (`led`). Only when no spot
      on the whole screen keeps every HARD rule is one broken (`forced`, never silent; still over no label placed
      before), so a failing yard's label is never dropped.
    Fast (the Rhino job at 822fb6f: up to 309 ms a label): each row of spots is worked out as runs that keep the
    HARD rules (_LabelField), only the nearest spot of each run is weighed, and the rows nearest the line go first
    (then those nearest its middle), stopping at the first spot beside the line with nothing SOFT against it.
    Returns {"left", "top", "w", "h", "rows", "size", "led", "forced", "gap"}."""
    (xa, ya), (xb, yb) = line
    mx, my = (xa + xb) / 2, (ya + yb) / 2
    x0, x1, y0, y1 = min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)
    two = label_lines(text)
    variants = [[text]] + ([two] if len(two) == 2 else [])
    field = _LabelField(line, view, hard_boxes, hard_lines, hard_shapes, placed, soft_lines)
    lead_boxes = list(hard_boxes) + list(soft_boxes)

    def shape(rows, pt):
        return max(label_width(r, pt) for r in rows), label_height(len(rows), pt)

    def result(rows, pt, left, top, w, h, forced=False):
        gap = box_gap(line, (left, top, w, h))
        return {"left": left, "top": top, "w": w, "h": h, "rows": rows, "size": pt, "led": gap > 8,
                "forced": forced, "gap": gap}

    def score(box, gap):
        left, top, w, h = box
        covered = sum(_over(box, other) for other in soft_boxes)
        led_hits = 0
        if gap > 8:                      # its leader: from its line's middle to the label's nearest edge
            lead = ((mx, my), leader_end((mx, my), box))
            led_hits = sum(_seg_hits_shape(lead, shape_) for shape_ in hard_shapes) + \
                sum(_seg_hits_box(lead, b_) for b_ in lead_boxes)
        crossed = sum(crosses(s_, left, top, w, h) for s_ in field.soft)
        return covered, led_hits, crossed, gap, left, top

    def candidates(w, h, base_x, base_y, step, nx, ny, reach, enough=None):
        """The nearest spot of each HARD-keeping run, rows nearest the line first (then nearest its middle); with
        `enough`, stop once that many are found and no row left is nearer; else at the first row with a spot
        beside the line (unled) with nothing SOFT against it, or once no row left could beat the best."""
        rows_ = sorted((max(0.0, y0 - (base_y + j * step + h), base_y + j * step - y1),
                        abs(base_y + j * step + h / 2 - my), j) for j in range(ny))   # nearest, then mid-line
        found, best_ = [], None
        for ydist, _, j in rows_:
            if ydist > reach:
                break
            if best_ is not None and best_[:3] == (0, 0, 0) and ydist >= best_[3]:
                break                                    # nothing in the rows left can beat it
            if enough is not None and len(found) >= enough and ydist >= found[enough - 1][0]:
                break
            top = base_y + j * step
            for i0, i1, _ in field.pieces(top, w, h, base_x, step, nx):
                i = _nearest_index(line, top, w, h, base_x, step, i0, i1)
                order_ = [i] + [k for d in range(1, i1 - i0 + 1) for k in (i - d, i + d) if i0 <= k <= i1]
                for k in order_:                         # the nearest; a neighbour only if label_breaks_hard
                    box = (base_x + k * step, top, w, h)  # refuses it (never expected: the runs are exact)
                    gap = box_gap(line, box)
                    if gap <= reach and not label_breaks_hard(line, box, view, hard_boxes, hard_lines, hard_shapes,
                                                              placed):
                        break
                else:
                    continue
                if enough is not None:
                    found.append((gap, box))
                    found.sort(key=lambda q: (q[0], q[1][0], q[1][1]))
                    continue
                s_ = score(box, gap)
                if s_[1]:                                # a led label's leader across something: the rest of
                    for k in range(i0, i1 + 1):          # the run weighed too (the review of 9d021d8)
                        box_ = (base_x + k * step, top, w, h)
                        gap_ = box_gap(line, box_)
                        if gap_ <= reach and not label_breaks_hard(line, box_, view, hard_boxes, hard_lines,
                                                                   hard_shapes, placed):
                            s_ = min(s_, score(box_, gap_))
                if best_ is None or s_ < best_:
                    best_ = s_
            if best_ is not None and best_[:3] == (0, 0, 0) and best_[3] <= 8:
                break                                    # beside its line, nothing SOFT against it: taken
        return found if enough is not None else best_

    def near(rows, pt, reach):
        w, h = shape(rows, pt)
        nx = int((x1 - x0 + w + 2 * reach) / LABEL_STEP) + 1
        ny = int((y1 - y0 + h + 2 * reach) / LABEL_STEP) + 1
        got = candidates(w, h, x0 - w - reach, y0 - h - reach, LABEL_STEP, nx, ny, reach)
        return None if got is None else result(rows, pt, got[4], got[5], w, h)

    for pt in range(int(size), LABEL_MIN_SIZE - 1, -1):          # within one label height: its size, then smaller
        for rows in variants:
            got = near(rows, pt, shape(rows, pt)[1])
            if got is not None:
                return got
    for rows in variants:                                        # led, up to LABEL_LEAD_REACH heights away
        got = near(rows, size, LABEL_LEAD_REACH * shape(rows, size)[1])
        if got is not None:
            return got
    if view is not None:                                         # the nearest spots on screen that keep the rules
        for pt in (int(size), LABEL_MIN_SIZE):
            for rows in variants:
                w, h = shape(rows, pt)
                nx, ny = int((view[0] - w) // 12) + 1, int((view[1] - h) // 12) + 1
                clear = candidates(w, h, 0, 0, 12, nx, ny, float("inf"), enough=40)[:40]
                if clear:
                    s_ = min(score(box, gap) for gap, box in clear)
                    return result(rows, pt, s_[4], s_[5], w, h)
    rows = variants[-1]                                          # nowhere keeps them all: never over another
    w, h = shape(rows, LABEL_MIN_SIZE)                           # label still (the review of 3446e94), else
    if view is not None:                                         # beside its line; said either way, never dropped
        i_ = LABEL_INSET
        free = sorted((box_gap(line, (left, top, w, h)), left, top) for top in range(i_, int(view[1] - h - i_) + 1, 12)
                      for left in range(i_, int(view[0] - w - i_) + 1, 12)
                      if not any(_over((left, top, w, h), other)
                                 for other in list(placed) + [axis_icon_box(view)]))   # nor on the axis icon
        if free:
            return result(rows, LABEL_MIN_SIZE, free[0][1], free[0][2], w, h, forced=True)
    left, top = min(xa, xb), max(ya, yb) + 6
    if view is not None:
        i_ = LABEL_INSET
        left = min(max(left, i_), max(view[0] - w - i_, i_))
        top = min(max(top, i_), max(view[1] - h - i_, i_))
        if _over((left, top, w, h), axis_icon_box(view)):          # off the axis icon: above it (review of 7e6d824)
            top = max(i_, axis_icon_box(view)[1] - h)
    return result(rows, LABEL_MIN_SIZE, left, top, w, h, forced=True)


def hull(points):
    """The convex hull of screen points, counter-clockwise (a building's footprint on screen when its outline isn't
    given in order: never smaller than the footprint, and turned with it, never its whole bounding box)."""
    pts = sorted(set((round(x, 3), round(y, 3)) for x, y in points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


LABEL_ORDER = {"does_not_comply": 0, "needs_review": 1, "complies": 2}   # failing first, the edges' lengths last
LABEL_SETTLE_S = 0.08        # the view still this long: the labels are placed (never while it moves)


class LabelRun:
    """Placing a frame's plan labels a few at a time (place_dim_label), outside the drawing loop: failing yards
    first, then those needing review, those that comply, the edges' lengths last; each one placed is HARD for the
    ones after (never hidden under another, the Rhino job at 4bb6d4d). `step` places labels until its time budget
    is spent (one at least), so Rhino stays responsive between steps (the review of 3446e94: the whole search at
    once froze it each time the view came to rest). `items`: dicts with "key", "text", "line" (screen), "size" and
    "status" (None for an edge). `spots`: {key: placement}, each with the line it was placed for ("line") and its
    place in the order ("order")."""

    def __init__(self, items, view, keep=(), dims=(), shapes=(), lines=(), carried=None):
        self.view, self.keep, self.shapes, self.carried = view, list(keep), list(shapes), dict(carried or {})
        self.dims = [tuple(map(tuple, d)) for d in dims]
        self.lines = [tuple(map(tuple, s_)) for s_ in lines if tuple(map(tuple, s_)) not in self.dims]
        self.todo = [item for _, item in sorted(enumerate(items), key=lambda ki: (
            LABEL_ORDER.get(ki[1].get("status"), 3), ki[0]))]
        self.placed, self.spots, self.slowest = [], {}, 0.0

    def kept(self, item, own):
        """The label's place carried with the view while it moved, when it still keeps every HARD rule beside its
        line at its own size with nothing SOFT against it (no jump when the view comes to rest), else None."""
        was = self.carried.get(item["key"])
        if not was or was.get("forced") or was["size"] != item["size"]:
            return None
        box = (was["left"], was["top"], was["w"], was["h"])
        gap = box_gap(own, box)
        if gap > 8 or label_breaks_hard(own, box, self.view, self.keep, self.dims, self.shapes, self.placed):
            return None
        if any(crosses(s_, *box) for s_ in self.lines if s_ != own):
            return None
        return dict(was, led=False, gap=gap)

    def step(self, budget_s=None):
        """Place labels until the next would pass `budget_s` seconds (by the slowest so far; one at least; None:
        all). Whether every one is placed."""
        import time as time_
        start, done = time_.perf_counter(), 0
        while self.todo:
            if budget_s is not None and done and time_.perf_counter() - start + self.slowest > budget_s:
                break
            done += 1
            began = time_.perf_counter()
            item = self.todo.pop(0)
            own = tuple(map(tuple, item["line"]))
            got = self.kept(item, own) or place_dim_label(
                own, item["text"], item["size"], self.view, hard_boxes=self.keep, hard_lines=self.dims,
                soft_lines=self.lines, hard_shapes=self.shapes, placed=list(self.placed))
            got = dict(got, line=own, order=len(self.spots))
            self.placed.append((got["left"], got["top"], got["w"], got["h"]))
            self.spots[item["key"]] = got
            self.slowest = max(self.slowest, time_.perf_counter() - began)
        return not self.todo


def place_labels(items, view, keep=(), dims=(), shapes=(), lines=()):
    """Every plan label of a frame placed at once (LabelRun to the end): {key: placement}."""
    run = LabelRun(items, view, keep, dims, shapes, lines)
    run.step()
    return run.spots


def shown_while_moving(carried, view, keep=(), dims=(), shapes=()):
    """Which labels carried along with a moving view (logic.follow) may be drawn this frame: only those that keep
    every HARD rule where they are now (label_breaks_hard: on screen, off the buildings, the boxes, the dimensions
    and the labels shown before them), in the order they were placed; the rest are hidden until the view rests and
    they are placed again (the Rhino job at 5b46c99: old places on screen, then a jump). `carried`: [(item, got)]
    with item["line"] the line on screen now. Returns the same pairs, those shown."""
    out, taken = [], []
    dims = [tuple(map(tuple, d)) for d in dims]
    for item, got in sorted(carried, key=lambda ig: ig[1].get("order", 0)):
        box = (got["left"], got["top"], got["w"], got["h"])
        if label_breaks_hard(tuple(map(tuple, item["line"])), box, view, list(keep), dims, list(shapes), taken):
            continue
        out.append((item, got))
        taken.append(box)
    return out


def follow(got, line):
    """A placement carried along while the view moves (never searched in the drawing loop): the same offset from
    its line's middle as when it was placed, at the line's middle on screen now."""
    (xa, ya), (xb, yb) = got["line"]
    (xc, yc), (xd, yd) = line
    dx, dy = (xc + xd) / 2 - (xa + xb) / 2, (yc + yd) / 2 - (ya + yb) / 2
    return dict(got, left=got["left"] + dx, top=got["top"] + dy, line=tuple(map(tuple, line)))


def _seg_hits_box(seg, box):
    return crosses(seg, box[0], box[1], box[2], box[3])


def _seg_hits_shape(seg, poly):
    """Whether a segment touches a polygon (crosses an edge, or lies inside it)."""
    (ax, ay), (bx, by) = seg
    if len(poly) < 3:
        return False
    for (cx, cy), (dx, dy) in zip(poly, poly[1:] + poly[:1]):
        d = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx)
        if abs(d) < 1e-12:
            continue
        t = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / d
        u = ((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / d
        if 0 <= t <= 1 and 0 <= u <= 1:
            return True
    return _inside((ax + bx) / 2, (ay + by) / 2, poly)


LABEL_KEEP = (                     # spaces never broken in a plan label (#29 at e4e5018: "101'-1" / "1/2"")
    r"(\d+'-\d+) (\d+/\d+\")",            # a measurement: 101'-1 1/2", 7'-0 5/8" (as NOTICE_KEEP's first)
    r"^([✕?✓]) (\S)",                     # a status mark with its first word: never alone on a line
    r"\b(min|max|needs) (\d)",             # the word that says what the number is, with it
)


def label_lines(text):
    """A plan label as two lines, for when it won't fit beside its line on one: its name, then its numbers
    ("✕ Side yard, Southwest" / "7'-0 5/8", needs 10'-0" (approx.)"). One line when it has no name before a number
    (a lot edge's length), never broken inside a measurement nor after a status mark alone (LABEL_KEEP)."""
    import re
    kept = text
    for keep in LABEL_KEEP:
        kept = re.sub(keep, lambda m: "\u00a0".join(m.groups()), kept)
    words = kept.split(" ")

    def number(w):
        return w.lstrip("✕?✓\u00a0")[:1].isdigit() or w.split("\u00a0")[-1][:1].isdigit() and "\u00a0" in w
    k = next((i for i, w in enumerate(words) if i and number(w)), None)
    if k is None or any(number(w) for w in words[:k]):     # no name before the numbers: one line
        return [text]
    return [" ".join(words[:k]).replace("\u00a0", " "), " ".join(words[k:]).replace("\u00a0", " ")]


NOTICE_SHARES = (0.4, 0.5, 0.6, 0.7, 0.8)   # the notice's boxes, narrowest first: a share of the view's width each
NOTICE_MAX_SHARE = NOTICE_SHARES[-1]         # never wider (a two-line band above the model, never a bar over it)
NOTICE_MIN_CHARS = 24                        # ...never narrower than this many characters a line


NOTICE_KEEP = (                    # spaces never broken in the notice (each becomes a non-breaking one)
    r"(\d+'-\d+) (\d+/\d+\")",            # a measurement: 7'-0 5/8"
    r"(\d[\d,.]*) (sf|%|ft)\b",             # an area, a share, a length: 7,033 sf, 35 %
    r"([\d\"'%]) (short|over|proposed|required)\b",   # the word that says what the number is
    r"^(✕) (\S)",                           # the mark with its first word
)


def notice_lines(lines, view_w, share=NOTICE_MAX_SHARE, size=13):
    """The notice's lines wrapped to at most `share` of the view's width (gordium_ui text_box_size's measure: size *
    0.6 pixels a character, 22 of margin), never under NOTICE_MIN_CHARS a line. Broken between its " · " parts first;
    a part is broken between its words only when it is too long even for NOTICE_MAX_SHARE (a heading kept whole where
    a wider box allows it: review of 87e105d), and never at a space in NOTICE_KEEP (7'-0 5/8" stays whole: review
    round 1); each notice line's rest indented under its first. Zoomed in tight, one long line was a bar across the
    whole plan, over the drawing being judged (architect's eye, #28 at 92cf742)."""
    import re
    import textwrap
    chars = max(NOTICE_MIN_CHARS, int((view_w * share - 22) / (size * 0.6)))
    widest = max(NOTICE_MIN_CHARS, int((view_w * NOTICE_MAX_SHARE - 22) / (size * 0.6)))
    out = []
    for line in lines:
        start, row = len(out), ""
        for part in line.split(" · "):
            for keep in NOTICE_KEEP:
                part = re.sub(keep, lambda m: "\u00a0".join(m.groups()), part)
            if row and len(row) + 3 + len(part) <= chars:
                row += " · " + part
                continue
            if row:
                out.append(row)
            indent = "  " if len(out) > start else ""
            if len(indent) + len(part) <= widest:          # whole, even past this share: the limit allows it
                pieces = [part]
            else:
                pieces = textwrap.wrap(part, chars - 2, break_long_words=False, break_on_hyphens=False) or [part]
            for k, piece in enumerate(pieces[:-1]):
                out.append((indent if k == 0 else "  ") + piece)
            row = (indent if len(pieces) == 1 else "  ") + pieces[-1]
        out.append(row)
    return [t.replace("\u00a0", " ") for t in out]


def notice_box(lines, size=13):
    """The (width, height) the notice's box takes on screen: gordium_ui.text_box_size's measure."""
    return max(len(t) for t in lines) * (size * 0.6) + 22, len(lines) * (size + 9) + 10


def notice_place(view_w, view_h, lines, model, taken=(), size=13):
    """The notice as drawn in a view: (lines, (left, top), width, height), or None. Its most compact box first (lines
    of at most 40 % of the view's width), then wider ones up to NOTICE_MAX_SHARE, never a box wider than that (fewer, longer lines: a band that fits above or
    below the model where a tall box can't), each in the first corner clear of the model and of every box in `taken`
    (notice_spot); None when no box fits a clear corner: then it is not drawn over the model, and the panel's
    message line says it (review round 1: one narrow box alone hid the side yard's notice in the default framed
    view; the Rhino job at a9a9a45: in the real docked Top view, 657 x 668 px, three lines at most 60 % wide were
    4 px too tall for the band above the model, so it wasn't drawn: two lines at 80 % fit)."""
    for share in NOTICE_SHARES:
        wrapped = notice_lines(lines, view_w, share, size)
        w, h = notice_box(wrapped, size)
        if w > view_w * NOTICE_MAX_SHARE:    # a part that won't break narrower: never wider than the limit (review)
            continue
        spot = notice_spot(view_w, view_h, w, h, model, taken)
        if spot is not None:
            return wrapped, spot, w, h
    return None


def notice_spot(view_w, view_h, w, h, model, taken=(), gap=12):
    """Where a w × h notice goes in a view (screen pixels): (left, top), or None. The corners are tried in turn (top
    left under the view's name, bottom left above the axes, top right, bottom right); the first that covers none of
    the model (`model`: its on-screen box, x0, y0, x1, y1, or None) and no box in `taken` (the status box) is used;
    None when there is none: the notice is never drawn over the building or lot being judged, nor over the status box
    (architect's review, 2026-10-21: bottom left, it hid the lot's lower edge and dimensions; #28 at 92cf742: zoomed
    in tight, a bar across the plan)."""
    spots = [(gap, 34), (gap, view_h - h - 64), (view_w - w - gap, 34), (view_w - w - gap, view_h - h - 40)]

    def overlap(x, y, box):
        a, b, c, e = box
        return max(0.0, min(x + w, c) - max(x, a)) * max(0.0, min(y + h, e) - max(y, b))
    clear = [(x, y) for x, y in spots if 0 <= x and x + w <= view_w and 0 <= y and y + h <= view_h   # on screen
             and not any(overlap(x, y, (a, b, a + c, b + e)) for a, b, c, e in taken)
             and not (model and overlap(x, y, model))]
    return clear[0] if clear else None


def clear_spot(taken, x, y, w, h, avoid=()):
    """Where a w × h label wanted at (x, y) (its top left, in screen pixels) covers none already drawn this frame
    (`taken`, a list of (x, y, w, h)): the nearest free position a label's height down or up, tried in turn, never
    moved up off the top of the view; the spot is then taken. If none is free within four steps (a tall box such as
    the status box in the way), the label goes just below everything it would cover."""
    def hits(top):
        return any(x < a + c and a < x + w and top < b + e and b < top + h for a, b, c, e in taken) or \
            any(crosses(s, x, top, w, h) for s in avoid)       # nor any line it must stay off (its dimension)
    top = None
    for k in range(9):
        trial = y + (k + 1) // 2 * (h + 3) * (1 if k % 2 else -1)
        if (trial >= 0 or trial >= y) and not hits(trial):        # never moved up off the top of the view
            top = trial
            break
    if top is None:                   # a tall box in the way (the status box): just below whatever it covers
        below = y
        for _ in range(len(taken) + 1):
            over = [b + e for a, b, c, e in taken if x < a + c and a < x + w and below < b + e and b < below + h]
            if not over:
                top = below
                break
            below = max(over) + 3
    top = y if top is None else top
    taken.append((x, top, w, h))
    return top


def status_box(viewport_width, rows, size=13):
    """Where the status box goes (top right of a view): (x, y, w, h) in screen pixels, the same size
    gordium_ui.draw_text_box draws it. Reserved before the labels, so no label is drawn under it."""
    width = max(len(r) for r in rows) * (size * 0.6) + 22
    height = len(rows) * (size + 9) + 10
    return (viewport_width - width - 14, 14, width, height)


def survey_pick(n_lots, picked, outlined):
    """Pick survey lot lines…: (the lot to mark as surveyed, or None; what to say, or None). Enter, with lots to
    choose from, keeps the one outlined (as the prompt says); no lot at all says how to draw one."""
    if n_lots == 0:
        return None, "No lot outline to pick: draw the surveyed lot as one closed polyline on the Site layer."
    if picked:
        return picked, None
    if outlined:
        return outlined, None
    return None, "No lot is outlined yet: run Pick survey lot lines… again and click the surveyed lot outline."


def could_be_building(kind, solid=False, faces=0):
    """Whether a Rhino object off the Building layer could be a building the check is leaving out (so lot coverage
    needs review): a solid, an extrusion, a SubD, a block, any polysurface of more than one face (a garage missing
    a face is still a garage) and any mesh of more than a few faces, open or closed (an imported shed is often an
    unwelded mesh). Not a single flat surface, a curve or a point. `kind` is the geometry's type name. Size is never
    a reason to leave one out: one mesh holding a garage and a shed spreads over most of the lot as well."""
    if kind in ("Extrusion", "SubD", "InstanceReferenceGeometry"):
        return True
    if kind == "Brep":
        return solid or faces > 1
    if kind == "Mesh":
        return solid or faces > 4
    return False


def looks_like_ground(kind, closed, extents, lot_extents, reach=1.0):
    """Whether a left-out object looks like the ground: an open mesh or surface (never a closed solid, a block, a
    SubD or an extrusion) whose plan extents (x0, y0, x1, y1) span the whole lot's, give or take `reach`. Only a
    label for the panel's "This is the ground"; it is never left out of the check on this guess."""
    if closed or kind not in ("Mesh", "Brep"):
        return False
    x0, y0, x1, y1 = extents
    a0, b0, a1, b1 = lot_extents
    return x0 <= a0 + reach and y0 <= b0 + reach and x1 >= a1 - reach and y1 >= b1 - reach


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


def reaches_into_lot(lot_ring, points, reach, box=None):
    """Whether an object whose plan points (any (x, y) of it: vertices, points along its edges) are `points`
    reaches into the lot (`lot_ring`, its outline's points) by more than `reach` (model units): the part of its
    plan footprint (their convex hull) inside the lot, averaged across (twice its area over its perimeter), is
    wider than `reach`. Wholly on the lot, straddling a lot line or mostly past it: on the lot. Touching the
    line from outside, a hair over it, or off the lot but inside the lot's bounding box (a rotated or jogged
    lot, the neighbour's house): not. The hull only ever makes an object bigger, the cautious direction.
    `box`, the object's plan bounding box (x0, y0, x1, y1), is its footprint whenever the points don't outline
    one (fewer than 3, or all in a line, as a sphere's seam is): a solid always covers some ground, so such
    points under-describe it."""
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
        hull = _hull([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    if len(hull) < 3 or _ring_area(hull) <= 1e-12:
        return False
    part = _clip(lot, hull)
    if len(part) < 3:
        return False
    area = abs(_ring_area(part))
    perimeter = sum(((part[i][0] - part[i - 1][0]) ** 2 + (part[i][1] - part[i - 1][1]) ** 2) ** 0.5
                    for i in range(len(part)))
    return perimeter > 0 and 2 * area / perimeter > reach


# ---- every callback Rhino or Eto calls goes through guard() -----------------------------------------------------
# On the Mac an exception that escapes a callback into native code (a view's paint, a cell formatting event, a
# display conduit's draw, an idle or document event) aborts Rhino outright (seen 2026-10-20: an Eto paint handler
# raised; xamarin_process_managed_exception → abort). So no callback may raise: guard() catches everything, writes
# it to the log, says it once on the command line (REPORT, set by the Rhino command), and returns a harmless
# fallback (draw nothing, change nothing). tests/test_check.py scans the plugin for any callback without it.
ERROR_LOG = None          # the log file's path (the Rhino command sets it; else <temp>/gordium_errors.log)
REPORT = None             # a function(text) that writes a line to Rhino's command line
_reported = set()


def guard(fn, where, fallback=None):
    """fn, wrapped so it never raises: an exception is logged (with where it happened) and fallback returned."""
    def safe(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:                      # noqa: BLE001  (any error: native code must never see it)
            import os
            import tempfile
            import time
            import traceback
            path = ERROR_LOG or os.path.join(tempfile.gettempdir(), "gordium_errors.log")
            try:
                with open(path, "a", encoding="utf-8") as log:
                    log.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + where + "\n" + traceback.format_exc() + "\n")
                if REPORT is not None and where not in _reported:
                    _reported.add(where)
                    REPORT("Gordium: ⚠ couldn't " + where + " (it was skipped; details in " + path + ")")
            except Exception:                  # noqa: BLE001  (even the report must not raise)
                pass
            return fallback
    return safe


# ---- address type-ahead (the place's site_lookup adapter's suggest, in lookup_box's own process; the box shows the list) ----
SUGGEST_DELAY_S = 0.3          # s after the last key before the City's address layer is asked
SUGGEST_LIMIT_S = 4.0          # s: slower than this, it is no help: "Suggestions unavailable"
SUGGEST_MIN_CHARS = 4
SUGGESTIONS_UNAVAILABLE = "Suggestions unavailable: type the full address and press Look up."
NO_MATCH = "No matching address suggested: type the full address and press Look up."


BOX_TEXT_WIDTH = 560           # px: the start box's long lines wrap here (one unbroken amber line stretched the box
                               # across the screen: Rhino run of #33 a3eb1d7)
LIST_ROW_PX, LIST_PAD_PX = 20, 2   # (2: the frame's border, so a row's text sits centred, not high: Rhino run of ee8f2ce)


def list_height(rows, row_px=LIST_ROW_PX):
    """The suggestion list's height in px: as tall as its rows (1 to 8) at `row_px` each (the pitch Rhino lays its
    rows out at, read from the list where it can be), never rows of empty space (Rhino run of a3eb1d7: one suggestion
    sat above five empty rows)."""
    return max(1, min(int(rows or 0), 8)) * int(row_px) + LIST_PAD_PX


def wants_suggestions(text, chosen=None):
    """Whether to ask for suggestions for what is typed: at least SUGGEST_MIN_CHARS characters, and not the
    suggestion just picked (picking one never opens the list again)."""
    text = str(text or "")
    return len(text.lstrip()) >= SUGGEST_MIN_CHARS and text != chosen


HINT_NOTE_PX = 20          # the quiet note's one line (size 10) and its row spacing


def hint_rows_px(list_shown, list_px, note):
    """How much taller the start box is while its suggestion rows show: the list (and its spacing) and the note's
    line, each only while shown (review round 1: an offline note showed with nothing added, pushing Draw down)."""
    return ((list_px + 6) if list_shown else 0) + (HINT_NOTE_PX if note else 0)


def hint_rows_shown(list_shown, note):
    """Whether the start box's suggestion rows (the type-ahead list and its quiet note) take any room: only while
    one of them has something to show (the architect's review, 2026-10-28: an empty gap under Address)."""
    return bool(list_shown) or bool(note)


def suggestions_shown(answer, typed):
    """(the list, a quiet note) for a type-ahead answer, or None when it is for something no longer typed (a stale
    answer is dropped). Offline, an error or too slow: no list and the note that suggestions are unavailable (the
    box still works by typing). None found: a quiet note says so, so the architect can tell the list is working
    (UX review 2026-10-27: "312 Hudson St" showed nothing at all)."""
    answer = answer or {}
    if answer.get("query") != typed:
        return None
    if answer.get("status") == "ok":
        found = [str(s) for s in answer.get("suggestions") or []]
        return found, "" if found else NO_MATCH
    return [], SUGGESTIONS_UNAVAILABLE


def list_step(index, count, key):
    """The list's selection after Down or Up in the address box (none selected: -1). Stays within the list."""
    if count <= 0:
        return -1
    if key == "down":
        return min(index + 1, count - 1)
    if key == "up":
        return max(index - 1, 0)
    return index


def grown_height(client_height, content_height, padding):
    """The start box's new inner height when a line shown again needs more room (the amber line back after "Corner
    lot?" is set to Not answered): the content's own height plus the box's padding above and below, if that is more
    than the box has; else None. Never smaller: the box doesn't jump as answers change (a box opened with the line
    hidden had no room for it, and Cancel and Draw were cut off at the bottom: the Rhino walk, 2026-10-28)."""
    want = int(math.ceil(content_height)) + padding
    return want if want > client_height else None


def is_elevation_view(parallel, direction_z, tolerance=0.01):
    """Whether a viewport is an elevation (Front, Right, Back, Left): a parallel projection looking level, where the
    height limit is labelled."""
    return bool(parallel) and abs(direction_z) <= tolerance


def north_vector(plan_north_deg):
    """True north as a direction in the plan (x, y): plan north (+y) when the plan isn't turned; a looked-up lot
    is drawn turned `plan_north_deg` (lookup_box.frame), and its north arrow turns with it."""
    import math
    t = math.radians(plan_north_deg or 0.0)
    return (-math.sin(t), math.cos(t))


def building_name(layer, name, grouped):
    """What the panel calls a building: the starting house Gordium drew (its floors grouped on the massing layer),
    else the object's name, else its layer ("a solid on Building")."""
    if on_layer(layer, MASSING):                     # its floors and roof each on its own sublayer
        return "the starting house"
    if name:
        return name + (" (and its group)" if grouped else "")
    return ("a group on " if grouped else "a solid on ") + layer


def prune_hosts(hosts, open_serials):
    """The docked panel's hosts for documents still open (and the one made without a document, key 0): a closed
    document's panel is never kept (review: 125 of them after a day of tests)."""
    keep = set(open_serials) | {0}
    return {k: v for k, v in (hosts or {}).items() if k in keep}


def is_plan_view(parallel, direction_z, tolerance=0.99):
    """Whether a viewport is a plan view, where plan labels belong: a parallel projection looking (nearly) straight
    down. Not a perspective (labels sit on the massing) and not an elevation (Front, Right: every plan label piles
    up on the ground line)."""
    return bool(parallel) and direction_z <= -tolerance


DIM_LIFT_FT = 0.1       # the yard dimensions stand this far above the lot's level (never in it, never under it)


def dim_level(lot_level_ft):
    """The height (feet) the yard dimensions are drawn at: just above the lot's own level (its outline's lowest
    point), so the ground and a lot drawn above z 0 never hide them where they are depth-tested; 0 + lift
    without a lot."""
    return (lot_level_ft or 0.0) + DIM_LIFT_FT


def lines_on_top(parallel, direction_z):
    """Whether Gordium's lines (the lot line, the envelope's outline, the dimensions, the neighbourhood) are drawn
    over everything in this view: in plan yes, so a line under the roof (the buildable outline, a dimension to the
    wall) stays visible; in every other view (perspective, the elevations, shaded or not) no: depth-tested, hidden
    behind the solids in front of them, as the model's own lines are (Ben, 2026-10-21)."""
    return is_plan_view(parallel, direction_z)


def model_ticks(a, b, size):
    """A dimension's end ticks in the model (drawn depth-tested with it): for a level line, at each end a slash at
    45° to it in plan (dim_ticks on x and y), at that end's own height; for an upright one (the height), a slash
    leaning 45° across x, y and z, so it shows in the Front and the Right views alike. `size` in model units.
    Each tick is a pair of (x, y, z)."""
    if ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 > 1e-9:
        return [((p0[0], p0[1], end[2]), (p1[0], p1[1], end[2]))
                for (p0, p1), end in zip(dim_ticks(a[:2], b[:2], size), (a, b))]
    if abs(b[2] - a[2]) < 1e-9:
        return []
    s = size / 2 / 3 ** 0.5                  # a slash of length `size` along (1, -1, 1)
    return [((p[0] - s, p[1] + s, p[2] - s), (p[0] + s, p[1] - s, p[2] + s)) for p in (a, b)]


class BoxSession:
    def __init__(self, table):
        import uuid
        self.table = table
        self.token = uuid.uuid4().hex                  # marks what this session draws and holds
        OPEN_SESSIONS.add(self.token)                  # live: recovery leaves its objects alone
        self.added, self.held = [], []
        self.layers_before = set(table.layer_names())
        self.views = table.save_views()

    def add(self, ids):
        """Objects this session drew: Cancel deletes them, and so does crash recovery (each carries the session's
        mark in the model until Draw)."""
        for i in ids:
            if i:
                self.table.mark_added(i, self.token)
                self.added.append(i)

    def hold(self, object_id):
        """Take an object out of the model for this session: one it drew is simply deleted; any other is held (Cancel
        brings it back as it was)."""
        if not object_id or not self.table.exists(object_id):
            return
        if object_id in self.added:
            self.added.remove(object_id)
            self.table.delete(object_id)
            return
        self.held.append((object_id, self.table.layer_of(object_id)))
        self.table.hold(object_id, self.token)

    def rollback(self):
        """Cancel, Esc or an error: the model as the box found it (objects, the layers it made, the views). Even if
        a step fails, the session is closed (no longer live), so whatever it left is recovered at the next start
        (verification round of PR #19: a raising rollback left its held objects stranded until Rhino restarted)."""
        try:
            for i in self.added:
                if self.table.exists(i):
                    self.table.delete(i)
            for i, layer in self.held:
                if self.table.exists(i):
                    self.table.release(i, layer)
            made = set(self.table.layer_names()) - self.layers_before
            for name in sorted(made, key=lambda n: -n.count("::")):      # sublayers first
                self.table.remove_layer_if_empty(name)
            self.table.restore_views(self.views)
            self.added, self.held = [], []
        finally:
            OPEN_SESSIONS.discard(self.token)

    def commit(self):
        """Draw: what was replaced goes for good, and what was drawn is kept (its session mark cleared)."""
        for i, _ in self.held:
            if self.table.exists(i):
                self.table.delete(i)
        for i in self.added:
            if self.table.exists(i):
                self.table.clear_mark(i)
        self.table.remove_layer_if_empty(HOLDING_LAYER)
        self.added, self.held = [], []
        OPEN_SESSIONS.discard(self.token)


def recover_held(table, live=None):
    """Box sessions Rhino didn't finish (it closed): what they drew deleted, what they held back on the layer it came
    from, so the model is as it was before those boxes opened. A session still open (`live`, OPEN_SESSIONS) is never
    touched. (removed, put back)."""
    live = OPEN_SESSIONS if live is None else live
    removed = [i for i, token in table.added_objects() if token not in live]
    for i in removed:
        table.delete(i)
    back = [(i, layer) for i, layer, token in table.held_objects() if token not in live]
    for i, layer in back:
        table.release(i, layer)
    table.remove_layer_if_empty(HOLDING_LAYER)
    return len(removed), len(back)


# ---- edits made without touching an object (the audit of main, 2026-10-29): live mode heard only objects added,
# deleted, replaced or re-attributed, so these left a ✓ showing as current over a model that had changed.
def layer_edit_counts(event, old, new):
    """Whether a layer change can change what Gordium checks. Which objects are the lot and the buildings is decided
    by each object's layer's full path (classify), hidden and locked objects counted too, so a layer renamed or
    moved under another parent counts (`old`, `new`: the layer's (name, parent id) before and after, None if it
    can't be read: then it counts), and so does one deleted or brought back. Its colour, whether it is shown or
    locked, the current layer, a new empty layer and the order of the layer list don't (Gordium itself changes
    those on its own layers at every check: counting them would grey every result it had just shown). `event`:
    Rhino's LayerTableEventType's name (Added, Deleted, Undeleted, Modified, Sorted, Current)."""
    if event in ("Deleted", "Undeleted"):
        return True
    if event == "Modified":
        return old is None or new is None or tuple(old) != tuple(new)
    return event not in ("Added", "Sorted", "Current")       # any other kind Rhino adds: counted, never missed


def block_edit_counts(event):
    """Whether a block definition change can change what Gordium checks: a block's contents edited (BlockEdit),
    redefined, deleted or brought back changes every building placed from it. A new definition (nothing placed from
    it yet: placing one adds an object, heard on its own) and the order of the list don't. `event`: Rhino's
    InstanceDefinitionTableEventType's name."""
    return event not in ("Added", "Sorted")


def units_edit_counts(seen, now):
    """Whether a document properties change changed the model's units, the one property the check reads (every
    length is taken to feet by its scale): `seen`, the units last noted for this document (None: none yet, so it
    counts, never assumed unchanged), `now` the units after the change. Rhino says only that some property
    changed (a render setting, a note), so the units are compared."""
    return seen is None or seen != now


@contextlib.contextmanager
def undo_step(doc, words):
    """Everything written to `doc` inside it is one undo step called `words` (Rhino's BeginUndoRecord /
    EndUndoRecord), ended even when the change fails. Serial 0: Rhino is already recording (inside a command), and
    that record holds the change: never ended here."""
    serial = doc.BeginUndoRecord(words)
    try:
        yield
    finally:
        if serial:
            doc.EndUndoRecord(serial)


# ---- the context map (design_checker.context_box): the neighbourhood around a looked-up lot ---------------------
CONTEXT_LIMIT_S = 20                    # the whole fetch (three map requests, about 1 s); the Rhino side stops it then
CONTEXT_ENTRY = "context"               # the document string holding the context's snapshot (records, never data)
NO_CONTEXT = ("No neighbourhood to show: it is drawn around a lot the start box looked up (GordiumStart, type the "
              "address, Look up, Draw).")


def guides_of(held, doc_serial):
    """Whether the live footprints held (STATE["context_guides"]) belong to this document."""
    return bool(held) and held.get("doc") == doc_serial


def guides_on_screen(held, doc_serial):
    """Whether this document's footprints are on screen: held for it AND with something to draw. The drawing's and
    the merge's question (keep the ones on screen?). Whether to fetch again is needs_refetch's (review round 8: a
    fetch that worked and found none is not a failure)."""
    return guides_of(held, doc_serial) and bool(held.get("lines"))


def needs_refetch(held, record, doc_serial):
    """Whether the tick or a Draw on the same lot should fetch the neighbourhood again: nothing drawn for this lot
    yet (no record: after a Draw with the tick off, or a first fetch that failed outright; review of the editable
    outlines, round 2), a live-only layer (a source that may not be kept, shown on screen and never saved) with
    nothing on screen for this document (a reopened file), or any layer, stored or live-only, whose last fetch
    failed (review round 9: parcels down on the first Draw were never fetched again). A layer kept from an earlier
    fetch that worked carries that fetch's "found" entry (context_merge), so a kept layer doesn't loop. A fetch that
    worked and found nothing is not fetched again (review round 8). guides_on_screen stays the drawing's and the
    merge's question."""
    layers = list(((record or {}).get("layers") or {}).values())
    if not layers:
        return True              # nothing drawn for this lot: the tick (or Draw) fetches it
    if any(not is_stored(v) for v in layers) and not guides_of(held, doc_serial):
        return True              # (the footprints are kept since 2026-10-21: a reopened file has them, nothing to fetch)
    return any((v or {}).get("status") not in DREW for v in layers)


CONTEXT_EDITABLE = (CONTEXT + "::Buildings",)   # left unlocked: the architect drags and edits the footprints (Ben)
GEOM_KEY = "gordium_context_geom"       # on each outline Gordium draws: the fingerprint of its points as drawn
PIECE_KEY = "gordium_context_id"        # on each outline: the parcel, street piece or footprint it is
EDITED_KEY = "gordium_context_edited"   # on an outline the architect edited: it is theirs (Gordium never removes it)
FRAME_KEY = "gordium_context_frame"     # on each outline: the lot (lookup frame) it was drawn around
DRAWN_KEY = "gordium_context_drawn_as"  # on each outline: its own object id when drawn (a copy keeps it, but not as its
                                        # own id: a copy is never the outline itself)


def outermost_first(layers):
    """Layer indexes (from (index, full path) pairs) ordered parent before sublayer, so setting a parent's state can
    never undo a sublayer's set after it (Rhino 8: a parent's IsVisible gives its sublayers its lock; review round 5)."""
    return [i for i, path in sorted(layers, key=lambda x: (x[1].count("::"), x[0]))]


def context_not_cleared(count):
    """What the architect is told when Rhino refused to delete or mark some of Gordium's neighbourhood objects (a
    layer still locked or hidden): never drawn over silently (review round 5)."""
    return ("Gordium could not remove %d neighbourhood object%s it drew earlier (a locked or hidden layer?). Unlock "
            "and show the Gordium layers, then press Draw again, or delete them by hand." % (count, "" if count == 1 else "s"))


def with_not_cleared(text, count):
    """A message with the not-cleared warning first when Rhino refused to remove some of Gordium's objects: the panel
    shows one line, so a warning said on its own is overwritten by the next message (review round 6); a "removed"
    line never stands alone while objects are left."""
    return text if not count else context_not_cleared(count) + " " + text


def context_locked(path):
    """Whether a context layer is locked after drawing: the leaf layers but the editable ones (the footprints), never
    an ancestor of an editable one (Gordium::Context itself): in Rhino a locked parent locks its sublayers' objects,
    so the footprints couldn't be dragged (review of the editable outlines, P1)."""
    if not on_layer(path, CONTEXT) or any(on_layer(path, e) for e in CONTEXT_EDITABLE):
        return False
    return not any(on_layer(e, path) for e in CONTEXT_EDITABLE)


def outline_key(points, attributes=None):
    """The fingerprint of an outline as Rhino holds it: every coordinate of its points, Z included (to a millionth of
    a model unit), and its attributes as the plugin's _attrs_print reads them (each of FINGERPRINT_ATTRIBUTES, the
    layer, linetype and material by their ids, the groups, the architect's own user text). Review of the editable
    outlines, P1: a footprint moved up to the terrain, renamed or recoloured was taken as unedited, deleted and drawn
    again at z = 0."""
    import hashlib
    import json
    flat = [[round(float(c), 6) for c in p] for p in points or []]
    return hashlib.sha1(json.dumps([flat, attributes or {}], sort_keys=True).encode("utf-8")).hexdigest()[:20]


def is_edited(stored_key, points, attributes=None):
    """Whether an outline Gordium drew has been edited since (moved in any direction, reshaped, renamed, recoloured):
    it no longer matches the fingerprint written when it was drawn (Ben, 2026-10-21: Gordium's redraw or clear removes
    only outlines it drew that the architect hasn't edited; an edited one is the architect's and stays). No
    fingerprint: not one of these."""
    return bool(stored_key) and outline_key(points, attributes) != stored_key


def frame_key(frame):
    """A short fingerprint of a lookup frame (which lot, placed how): an outline remembers the lot it was drawn for."""
    import hashlib
    import json
    return hashlib.sha1(json.dumps(frame or {}, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def suppressed(edited, current_frame_key):
    """The ids not to draw again: those of outlines the architect edited that are the very outline Gordium drew (its
    own id is the one it was drawn as: not a copy, which carries the original's user text under a new id) and were
    drawn around this same lot (not one kept from another address, whose ids belong to another square). Review of the
    editable outlines, P2: a copy, or an outline kept from another address, hid an unedited neighbour. `edited`:
    [{id, frame, drawn_as, own}]."""
    return sorted(set(e.get("id") for e in edited or [] if e.get("id") and e.get("frame") == current_frame_key
                      and e.get("drawn_as") and e.get("drawn_as") == e.get("own")))


# The attributes of an outline in its fingerprint (the plugin's _attrs_print), by name: each one an architect can
# change on an outline in Rhino 7 or 8, one that Rhino lacks left out by _attrs_print (review of the editable outlines, round 2: a short list missed print width and
# colour, material, groups). A fixed list, not every property by reflection (round 3): a property one Rhino version
# adds would make every outline drawn under the last one look edited. Table positions are never fingerprinted (the
# layer, linetype and material go by their ids, the groups by theirs: _attrs_print): a deleted layer isn't saved, so
# on reopening a file the later layers' indexes move down, and every untouched outline looked edited, kept forever.
FINGERPRINT_ATTRIBUTES = ("Name", "Url", "Mode", "Visible", "Space", "ViewportId", "DisplayOrder", "WireDensity",
                          "ObjectDecoration", "ColorSource", "ObjectColor", "LinetypeSource", "PlotColorSource",
                          "PlotColor", "PlotWeightSource", "PlotWeight", "MaterialSource", "CastsShadows",
                          "ReceivesShadows", "LinetypePatternScale")   # the last: Rhino 8 only (round 4)


def attribute_text(value):
    """An attribute's value as stable text for the fingerprint (a number, a flag, an enum's name, an id; a colour by
    its ARGB number, never its name, which a colour read back from a file doesn't keep)."""
    if hasattr(value, "ToArgb"):
        return str(int(value.ToArgb()))
    if isinstance(value, float):
        return repr(round(value, 9))
    return str(value)


def kept_on_clear(stored_key, drawn_as, own_id, points, attributes):
    """Whether a clear or redraw keeps an object on the context layers (it is the architect's): any outline that isn't
    exactly the one Gordium drew. A copy (pasted in place too: same points, same attributes) is never the outline
    itself, its own id isn't the one it was drawn as; an edited outline no longer matches its fingerprint. Only
    Gordium's own untouched outlines, and its notes (no fingerprint), are deleted (Ben, 2026-10-21; review round 2)."""
    if not stored_key:
        return False
    return not drawn_as or drawn_as != own_id or is_edited(stored_key, points, attributes)


def skip_edited(objects, edited_ids):
    """The objects to draw, less those the architect has edited and kept (by their parcel, street piece or footprint
    id): an edited outline is not drawn a second time beside it."""
    edited = set(i for i in edited_ids or [] if i)
    return [o for o in objects or [] if not o.get("id") or o["id"] not in edited]


def left_out_candidate(layer_path):
    """Whether a solid on this layer that reaches into the lot is one the check must say it left out (review row:
    "Objects on the lot not included"): every layer but the Building layer and Gordium's own, except the
    neighbourhood's (Gordium::Context), whose footprints the architect may extrude or put a building on (editable
    since Ben's decision, 2026-10-21). Review of the editable outlines, P0: a solid there was never measured and
    never made the check need review."""
    return not on_layer(layer_path, "Gordium") or on_layer(layer_path, CONTEXT)


def context_left_out(layers_by_id):
    """Of the left-out objects (id: its layer), those on the neighbourhood's layers: the review row tells the
    architect to move them to the Building layer."""
    return sorted(i for i, layer in (layers_by_id or {}).items() if on_layer(layer or "", CONTEXT))


def context_objects(payload):
    """What may be written into the .3dm: objects from a source whose store is raw (the payload's layers say which),
    and Gordium's own marks (frame, north arrow, scale bar, credits). Anything else is never written, whatever the
    payload's object list holds."""
    payload = payload or {}
    raw = set(s.get("source") for s in (payload.get("layers") or {}).values() if is_stored(s))
    return [o for o in payload.get("objects") or []
            if (o.get("source") in raw or o.get("source") == "gordium") and on_layer(o.get("layer") or "", CONTEXT)]


def context_guides(payload):
    """What is only shown on screen (never written): every guide, from a source that may not be kept."""
    return [g.get("points") for g in (payload or {}).get("guides") or [] if len(g.get("points") or []) > 1]


def context_says(payload):
    """The line after the neighbourhood is drawn (or why it isn't): what an architect needs, as "Neighbourhood drawn:
    229 parcels, 38 streets, 322 buildings (footprints from 2014)." (architect review of PR #23: the line listed
    agencies and storage rules). "shown only" is added only for footprints from a source that may not be kept. Who
    made the data is on the drawing's Sources note; what a failed service left out follows (the payload's message)."""
    payload = payload or {}
    if payload.get("status") not in ("found",):
        return payload.get("message") or "Couldn't fetch the neighbourhood: the lot is drawn without it."
    n = payload.get("counts") or {}
    said = "%d parcels, %d streets" % (n.get("parcels", 0), n.get("streets", 0))
    if n.get("buildings"):
        layer = (payload.get("layers") or {}).get("buildings") or {}
        dates = ", ".join(layer.get("dates") or [])
        said += ", %d buildings (footprints %s%s)" % (n["buildings"], "from " + dates if dates else "of unknown date",
                                                       "" if is_stored(layer) else ", shown only")
    return "Neighbourhood drawn: " + said + "." + (" " + payload["message"] if payload.get("message") else "")


HANDLES = ("hooks", "doc_hooks", "command_hook", "overlay", "panel", "panel_parts", "toast_timer", "label_timer",
           "worker", "worker_sends", "worker_lines", "live_timer", "live_check")


def sweep(leftovers, state=None, release=None):
    """Undo everything an earlier copy of the plugin left attached to Rhino (event handlers, its drawing, its
    panel, its checker): `leftovers` maps a name to its undo, kept outside the plugin's state so clearing the
    state can't lose it. Each undo runs even if another fails; returns how many ran. Given the plugin's `state`,
    its handles to those things are forgotten too (so it never says a detached hook is attached), each RELEASED
    first through `release(key, value)`: a copy from before LEFTOVERS existed recorded nothing there, so without
    this its handlers, drawing, panel and checker would stay attached with nothing left to undo them (review
    round 2). Releasing twice is harmless. What the architect asked for (live mode on, the choices) stays."""
    n = 0
    for key in list(leftovers):
        undo = leftovers.pop(key, None)
        try:
            undo()
            n += 1
        except Exception:                      # noqa: BLE001  (already gone: nothing to undo)
            pass
    for key in HANDLES if state is not None else ():
        if key in state and release is not None:
            try:
                release(key, state[key])
            except Exception:                  # noqa: BLE001  (already gone: nothing to release)
                pass
        state.pop(key, None)
    return n


def current_only(fn, is_current):
    """fn, run only while is_current() (this copy of the plugin is the loaded one): an older copy's handler that
    is still attached does nothing, so it can never act on, or wait on, the current copy's checker."""
    def run(*args):
        if not is_current():
            return None
        return fn(*args)
    return run


# ---- processes started from Rhino: never a console window (Windows) -----------------------------------------------
CREATE_NO_WINDOW = 0x08000000            # Windows: a console program started from a window program shows no console
STARTF_USESHOWWINDOW, SW_HIDE = 0x00000001, 0


def spawn_options(os_name, subprocess_module):
    """What every process Gordium starts from Rhino is started with (gordium_ui.spawn): on Windows, no console window
    (the cofounders saw a terminal pop up while Gordium ran: Python started from Rhino, a window program, opens one
    unless told not to), and its window hidden too; elsewhere nothing extra."""
    if os_name != "nt":
        return {}
    info = subprocess_module.STARTUPINFO()
    info.dwFlags |= STARTF_USESHOWWINDOW
    info.wShowWindow = SW_HIDE
    return {"creationflags": CREATE_NO_WINDOW, "startupinfo": info}


def open_command(os_name, target):
    """How a file or link is opened with the computer's own app: ("startfile", target) on Windows (os.startfile:
    `open` is macOS's), ("run", ["open", target]) on macOS."""
    return ("startfile", target) if os_name == "nt" else ("run", ["open", target])


class ServerBook:
    """The checker processes Gordium started from Rhino, kept in a small file (`path`) so a later load, a reload,
    or Rhino closing stops the earlier ones still running: exactly one server per Rhino (the coordinator found 30
    orphaned `design_checker serve` children of Rhino, one per plugin load; on Windows each a console window too).
    Each entry: the checker's process number and start time, and the Rhino that started it (`me`: its number and
    start time). A Rhino stops only its own checkers, and those of a Rhino no longer running (a crash); another
    Rhino's are left alone (review round 7, P1: one file for every Rhino, so two open models stopped each other's
    checker). A process is stopped only while it is the one recorded: the same number AND start time (round 7, P2:
    a number the system gave again to another program is never touched). `started_at(pid)`: that process's start
    time, None when it isn't running; `stop(pid)`: the operating system's (gordium_rhino), stand-ins in CI."""

    def __init__(self, path, me, started_at, stop):
        self.path, self.me, self.started_at, self.stop = path, dict(me), started_at, stop

    def entries(self):
        """The record's entries; anything unreadable (an older format: bare numbers) is left out, never stopped."""
        try:
            with open(self.path, encoding="utf-8") as f:
                got = json.load(f)
        except (OSError, ValueError, TypeError):
            return []
        keys = ("pid", "start", "owner", "owner_start")
        return [e for e in got if isinstance(e, dict) and all(k in e for k in keys)] if isinstance(got, list) else []

    def pids(self):
        return [e["pid"] for e in self.entries()]

    def _write(self, entries):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(entries, f)
        except OSError:
            pass

    def _mine_or_orphaned(self, e):
        mine = e["owner"] == self.me["pid"] and e["owner_start"] == self.me["start"]
        return mine or self.started_at(e["owner"]) != e["owner_start"]       # its Rhino is gone

    def stop_all(self, keep=None):
        """Stop this Rhino's recorded checkers (and orphans) still running, but `keep` (an entry); every other
        Rhino's entries stay recorded, as they are."""
        left = []
        for e in self.entries():
            if keep is not None and e["pid"] == keep["pid"] and e["start"] == keep["start"]:
                continue
            running = self.started_at(e["pid"]) == e["start"]                # the same process, not its number reused
            if self._mine_or_orphaned(e):
                if running:
                    self.stop(e["pid"])
            elif running:
                left.append(e)
        self._write(left + ([keep] if keep is not None else []))

    def started(self, pid):
        """A new checker of this Rhino: its earlier ones stopped, this one recorded (another Rhino's untouched)."""
        self.stop_all(keep={"pid": pid, "start": self.started_at(pid), "owner": self.me["pid"],
                            "owner_start": self.me["start"]})
