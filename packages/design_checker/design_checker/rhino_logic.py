"""The decisions the Rhino command makes, as plain functions (no Rhino, Python 3.9), so CI can test them. The
Rhino script (apps/rhino_plugin/gordium_rhino.py) imports this file directly.
"""

import json
import queue
import threading

LAYERS = {"lot": "Site", "building": "Building"}
ID_KEY = "gordium:id"                   # the same keys as model_measurement.read_3dm (a test keeps them equal)
FLOOR_KEY = "gordium:floor"            # user text on a floor block GordiumStart drew: "<story>;<height drawn, ft>"
MASSING = "Gordium::Massing"            # where GordiumStart draws the starting building: building objects too
SOLIDS = ("Brep", "Extrusion", "Mesh", "SubD")
DRAWING_AIDS = ("Curve", "Point", "PointCloud", "TextDot", "AnnotationBase", "Hatch", "TextEntity", "Dimension",
                "Leader", "LinearDimension", "AngularDimension", "RadialDimension", "OrdinateDimension")
# the grade isn't required: without one the check runs and height and stories need review until it's set (spec C3)
REQUIRED = ("jurisdiction", "zone", "use", "street_line", "lot_surveyed")   # corner lot unanswered: the yards wait (C)


def on_layer(full_path, layer):
    """A layer or one of its sublayers ("Building::Garage")."""
    return full_path == layer or full_path.startswith(layer + "::")


CONTEXT = "Gordium::Context"            # the context map (neighbouring parcels, streets, notes): drawing only
CONTEXT_KEY = "gordium_context"         # on each context object: the endpoints.yaml source it was drawn from
HOLDING_LAYER = "Gordium::Replaced (Cancel restores)"   # objects a start box replaced, until Draw (BoxSession)
HELD_FROM = "gordium_held_from"                          # on each held object: the layer it came from
ADDED_BY = "gordium_added"                               # on each object a start box drew: its session, until Draw
HELD_BY = "gordium_held_by"                              # on each held object: the session holding it
OPEN_SESSIONS = set()          # the sessions of start boxes open now (recovery never touches theirs: review round 4)
BOX_BUSY = "Finish or cancel the open start box first."


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


def missing(facts):
    """The required lot facts not yet given: the confirm dialog shows whenever any is missing."""
    facts = facts or {}
    return [k for k in REQUIRED if facts.get(k) is None or facts.get(k) == []]


def with_suggestions(saved, suggested):
    """The facts to confirm: what is saved, with suggestions only for what is missing."""
    out = dict(suggested)
    out.update({k: v for k, v in (saved or {}).items() if v is not None})
    return out


def update_counts(facts, answers):
    """Bedrooms, parking spaces and stories from the Lot facts prompts. An answer of None means the prompt was
    skipped: the fact stays as it was (unset stays unset, so its rules stay NEEDS REVIEW), never 0."""
    out = dict(facts or {})
    for key in ("sleeping_rooms", "parking_spaces", "stories"):
        if answers.get(key) is not None:
            out[key] = int(answers[key])
    return out


def to_feet(facts, scale):
    """Facts read off the model (street line ends, ground level), in model units, as feet (scale = feet per
    model unit). Everything Gordium measures and stores is in feet."""
    out = dict(facts)
    if out.get("street_line"):
        out["street_line"] = [[[c * scale for c in p] for p in line] for line in out["street_line"]]
    if out.get("grade_elevation") is not None:
        out["grade_elevation"] = out["grade_elevation"] * scale
    return out


def drop_stale(facts, lot_ids, building_ids):
    """The saved facts without a lot or main building that is no longer in the model (redrawn, joined, deleted):
    the lot's street lines go with it, so the confirm dialog asks again instead of keeping an id nothing has."""
    out = dict(facts or {})
    if out.get("lot_id") and out["lot_id"] not in lot_ids:
        out.pop("lot_id")
        out.pop("street_line", None)
    if out.get("main_building") and out["main_building"] not in building_ids:
        out.pop("main_building")
    return out


def venv_python(root, os_name):
    """Where the repo's virtual environment keeps Python: bin/python (Mac, Linux), Scripts\\python.exe (Windows)."""
    if os_name == "nt":
        return "\\".join((root, ".venv", "Scripts", "python.exe"))
    return "/".join((root, ".venv", "bin", "python"))


def draws_in(checked, viewport):
    """Whether a result is drawn in a viewport: only in the document it is the result for (Rhino for Mac keeps
    several models open side by side; one model's verdict never shows on another)."""
    return checked is not None and checked == viewport


def code_fingerprint(packages_dir):
    """What the checker's code is now: every file under packages/ (code and the data it loads) with its size and
    time, as one text. The
    background checker is started again whenever this changes (an update while Rhino is open), so results never
    come from code that is no longer there."""
    import os
    found = []
    for root, dirs, files in os.walk(packages_dir):         # code and the data it loads (measures.yaml), not caches
        dirs[:] = sorted(d for d in dirs if d != "__pycache__" and not d.startswith(".") and not d.endswith(".egg-info"))
        for name in sorted(files):
            if not name.endswith((".pyc", ".pyo")) and not name.startswith("."):
                path = os.path.join(root, name)
                try:
                    st = os.stat(path)
                    found.append("%s:%d:%d" % (os.path.relpath(path, packages_dir), st.st_size, st.st_mtime_ns))
                except OSError:         # gone between listing and reading (an editor's temporary file): changed
                    found.append("%s:gone" % os.path.relpath(path, packages_dir))
    return "|".join(found)


def restart_checker(alive, started_with, now):
    """Whether to start the background checker again: it stopped, or the code changed since it started."""
    return not alive or started_with != now


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


def after_lot_pick(facts, picked_lot):
    """The facts after the lot is (re)picked: a different lot drops the street lines, which belonged to the old
    one (they are asked again on the new lot), and so Enter can't keep them."""
    out = dict(facts)
    if picked_lot and picked_lot != out.get("lot_id"):
        out["lot_id"] = picked_lot
        out.pop("street_line", None)
        out.pop("plan_north_deg", None)      # the looked-up lot's turn belonged to it
    return out


def street_enter_keeps(facts):
    """Whether Enter at the first street-line prompt keeps the street lines saved for this lot."""
    return bool(facts.get("street_line"))


def after_corner_answer(facts, was_corner):
    """The facts after the corner-lot answer: a changed answer drops the street lines (a corner lot has two
    streets, any other lot one), so they are picked again and Enter can't keep the old ones."""
    out = dict(facts)
    if out.get("corner_lot") != was_corner:
        out.pop("street_line", None)
    return out


def suggested_facts(jurisdiction, zones, lots, buildings):
    """The start box's prefilled lot facts, in the model's units (the plugin converts them to feet), for the
    architect to confirm. `lots`: the Site layer's closed outlines, each {"id", "area", "bottom" (its lowest
    level), "segments": [((x, y), (x, y)), ...]}; `buildings`: each {"id", "bottom", "volume" (of its box)}.
    The largest outline is the lot, its lowest line on screen the street side; the ground is flat at the
    buildings' lowest point (or the lot's level); the lot is not from a survey; the first zone with rules; a
    detached one-family house; the largest solid the main building. The corner-lot question is never answered
    here: always None, so the box asks it and the yards wait for the answer."""
    facts = {"jurisdiction": jurisdiction, "zone": zones[0] if zones else None, "use": "one_family_detached",
             "corner_lot": None, "ground_is_flat": True, "lot_surveyed": False}
    lot = max(lots, key=lambda l: l["area"]) if lots else None
    if lot is not None:
        facts["lot_id"] = lot["id"]
        if lot["segments"]:
            a, b = min(lot["segments"], key=lambda s: (s[0][1] + s[1][1]) / 2)
            facts["street_line"] = [[[a[0], a[1]], [b[0], b[1]]]]
    ground = suggested_ground([b["bottom"] for b in buildings], lot["bottom"] if lot is not None else None)
    if ground is not None:
        facts["grade_elevation"] = ground
    if len(buildings) > 1:
        facts["main_building"] = max(buildings, key=lambda b: b["volume"])["id"]
    facts["corner_lot"] = None                     # never guessed, whatever came before
    return facts


def suggested_ground(building_bottoms, lot_bottom):
    """The ground level to suggest (feet or model units, as given): the lowest point of the buildings, or with no
    building yet (a new project on the architect's own lot) the lot outline's level. Shown in the dialog, never
    used unconfirmed."""
    return min(building_bottoms) if building_bottoms else lot_bottom


def clear_spot(taken, x, y, w, h):
    """Where a w × h label wanted at (x, y) (its top left, in screen pixels) covers none already drawn this frame
    (`taken`, a list of (x, y, w, h)): the nearest free position a label's height down or up, tried in turn, never
    moved up off the top of the view; the spot is then taken. If none is free within four steps (a tall box such as
    the status box in the way), the label goes just below everything it would cover."""
    def hits(top):
        return any(x < a + c and a < x + w and top < b + e and b < top + h for a, b, c, e in taken)
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


# ---- the start box (spec A, as approved 2026-10-20): what it shows, decided here so CI can test it ------------
NOT_CHECKED_YET = "Not checked yet: overlays (historic, gorge, flood) · pitched roofs"
ENTERED = "entered by you"
FLOOR_TO_FLOOR = 11 + 8 / 12                 # ft: the starting house's floor height (editable later in GordiumFacts)
CORNER_CHOICES = ["Not answered", "No: one street", "Yes: two streets"]   # the Street side row's question
SUGGESTED = "suggested by Gordium"
GROUND_CHOICES = [("spot", "Place spot grades…"), ("terrain", "Pick terrain…"),
                  ("regrade", "I'll regrade: set finished ground…")]


def lot_text(area, surveyed, source=None):
    """The Lot row: "6,570 sf · from the tax map (±2 ft, approximate)" or "… · from your survey"; with the map
    service the lookup read it from ("… · NYS Tax Parcels Public")."""
    size = f"{area:,.0f} sf" if isinstance(area, (int, float)) else "area not known"
    return size + " · from " + ("your survey" if surveyed else "the tax map (±2 ft, approximate)") + \
        (" · " + source if source and not surveyed else "")


def ground_text(ground):
    """The Ground row: what the ground is and where it came from ("flat at the lot level · as drawn", "4 spot
    grades, 0'-0" to 3'-0" · placed by you", "terrain · picked by you", or finished ground you set)."""
    kind = ground.get("kind") or "flat"
    if kind == "flat":
        return "flat at the lot level · as drawn"
    span = ground.get("range") or ""
    what = {"spot": f"{ground.get('count', 0)} spot grades", "terrain": "terrain",
            "regrade": f"finished ground you set ({ground.get('count', 0)} spot grades)"}[kind]
    return what + (", " + span if span else "") + " · " + (ground.get("source") or
                                                         ("picked by you" if kind == "terrain" else "placed by you"))


def box_rows(state):
    """The start box, top to bottom: one dict per row {key, label, text, actions [(action, label, enabled)],
    tick (label, checked) or None, review (an amber line) or None, check ("I checked this", ticked) or None}.
    `state`: address, zone, zone_source, district_confirmed, use, use_name, lot_area, lot_surveyed, street_name,
    ground {kind, count, range}, no_regrading, lookup (this session's), doubts, live, checked, lot_missing."""
    look = state.get("lookup") or {}
    doubts, live = state.get("doubts") or {}, state.get("live") or {}
    checked = set(state.get("checked") or [])

    def review(key):                  # a doubt about what is drawn (or this lookup's zone): amber, why, I checked this
        why = live.get(key) or doubts.get(key)
        if key == "zone":             # the zone's own doubts and the overlays found, together
            why = " ".join(t for t in (live.get("zone"), live.get("overlays")) if t) or None
        return {"review": "? " + why if why else None,
                "check": ("I checked this", key in checked) if key in CHECKABLE and key in doubts else None}

    lot_actions = [("lot", "Use my survey…", not state.get("lot_surveyed"))]
    if look.get("guide") or state.get("lot_missing"):
        lot_actions.insert(0, ("draw_lot", "Draw my lot…", True))
    rows = [
        {"key": "address", "label": "Address", "text": state.get("address") or "",
         "actions": [("lookup", "Looking up…" if look.get("looking") else "Look up", not look.get("looking"))],
         "tick": None, "matches": look.get("matches") or [],
         "status": LOOKING.format(look["looking"]) if look.get("looking") else None},
        {"key": "zone", "label": "Zoning district",
         "text": (state.get("zone") or "—") + " · " + (state.get("zone_source") or ENTERED),
         "actions": [("zone", "Change", True)], "tick": ("I confirm", bool(state.get("district_confirmed")))},
        {"key": "use", "label": "Use", "text": state.get("use_name") or state.get("use") or "—",
         "actions": [("use", "Change", True)], "tick": None},
        {"key": "lot", "label": "Lot",
         "text": ("no lot yet: draw it, or pick a closed outline on the Site layer" if state.get("lot_missing") else
                  lot_text(state.get("lot_area"), state.get("lot_surveyed"), state.get("lot_source"))),
         "actions": lot_actions, "tick": None},
        {"key": "street", "label": "Street side", "text": state.get("street_name") or "the highlighted line",
         "actions": [("street", "Change…", True)], "tick": None,
         "choice": ("Corner lot?", CORNER_CHOICES, {None: 0, False: 1, True: 2}[state.get("corner_lot")])},
        {"key": "ground", "label": "Ground", "text": ground_text(state.get("ground") or {}),
         "actions": [(k, t, True) for k, t in GROUND_CHOICES],
         "tick": ("No regrading near the house", bool(state.get("no_regrading")))},
    ]
    for r in rows:
        r.update(review(r["key"]))
    return rows


# ---- the address lookup (design_checker.lookup_box runs it; this turns its answer into the box's choices) ----
#
# What the box keeps, and for how long (review round 1 of PR #19):
# - saved_ui["doubts"] {row: reason}: what is doubtful about the lot, street side and ground DRAWN in the model. It
#   changes only when that thing is replaced (a lookup that draws a new lot) or the architect confirms it (I checked
#   this) or changes it; a failed, empty or own-lot lookup never touches it. Only a reason its sources allow keeping
#   is saved; otherwise a plain DOUBT_KEPT.
# - keys starting with "_" belong to this box session only (the lookup's live wording, its asks and matches, the
#   City's zones and street name, the model edits to undo on Cancel) and are never written to the .3dm
#   (storable_ui, the one write boundary).

LOOKUP_LIMIT_S = 45                               # the whole lookup; the box says so, the Rhino side stops it then
LOOKING = "Looking up {}… (up to %d s)" % LOOKUP_LIMIT_S
CHECKABLE = ("lot", "street", "ground")          # what "I checked this" settles (the district has its own tick)
DOUBT_KEPT = "The lookup found this doubtful (its reason came from a source that can't be kept): check it."
LOOKUP_SAYS = {                                   # the box's line when a lookup couldn't fill it in
    "not_found": "No City of Ithaca address found for {query}: check the spelling, or draw the lot.",
    "outside_city": "{message}",
    "offline": "Couldn't reach the map services (offline?): enter the site by hand.",
    "error": "A map service answered with an error: enter the site by hand.",
    "timeout": "The lookup took too long: enter the site by hand, or try again.",
    "multiple": "{message} Pick one under Address, then Look up again.",
}
ROW_OF = {"address": "lot", "parcel": "lot", "lot": "lot", "street_side": "street", "corner_lot": "street",
          "ground": "ground", "zone": "zone", "overlays": "overlays"}
SOURCE_OF = {"address": "NYS Geocoder", "lot": "NYS Tax Parcels Public", "street": "City roads",
             "ground": "USGS 3DEP, today's ground", "zone": "City zoning map, used live"}   # if the payload has none
GUIDE = ("The State's tax map didn't answer; the City's outline is shown as a dashed guide only (it can't be kept): "
         "Draw my lot… over it, or pick your own outline.")


def storable_ui(saved_ui):
    """What of the box's choices may be written into the .3dm: never a session key ("_…": the lookup's live wording,
    the City's zones and street name, its asks)."""
    return {k: v for k, v in (saved_ui or {}).items() if not str(k).startswith("_")}


def lookup_says(payload):
    """The line for a lookup that didn't find the site (None when it did)."""
    status = (payload or {}).get("status")
    if status in (None, "found"):
        return None
    text = LOOKUP_SAYS.get(status, LOOKUP_SAYS["error"])
    return text.format(query=payload.get("query") or "this address", message=payload.get("message") or "").strip()


def lookup_may_replace(facts, saved_ui):
    """Whether a lookup may replace the model's lot: none yet, or the one a lookup or the sample drew (and still the
    lot). Never one the architect drew, picked or surveyed."""
    lot = (facts or {}).get("lot_id")
    return not lot or lot == (saved_ui or {}).get("replaceable_lot")


def lookup_choices(payload, facts, saved_ui, zones=(), replaces=True):
    """(facts, saved_ui) after a lookup, as a pick returns them. Each found fact a suggestion with its own service's
    name, never confirmed (the district must be ticked again: "_reconfirm"). The lot, street side and ground (and
    their doubts) only when the lookup's lot replaces the model's (`replaces`); for the architect's own lot, only
    the address and the district. A lookup that found nothing changes nothing but its own line."""
    payload = payload or {}
    facts, saved_ui = dict(facts), dict(saved_ui)
    look = {"status": payload.get("status") or "error", "says": lookup_says(payload),
            "asks": list(payload.get("asks") or []), "matches": list(payload.get("matches") or []),
            "query": payload.get("query")}
    saved_ui["_lookup"] = look
    if look["status"] != "found":
        return facts, saved_ui
    got, details = payload.get("facts") or {}, payload.get("details") or {}
    labels, kept = payload.get("labels") or {}, payload.get("kept_reasons") or {}

    def value(name):
        return (got.get(name) or {}).get("value")

    def label(name, row):
        return labels.get(name) or SOURCE_OF[row]

    live, keep = {}, {}
    for name, d in details.items():          # every doubtful or asked fact's reason, by row; reasons add up
        if d.get("status") in ("needs_review", "ask") and d.get("reason"):
            row = ROW_OF.get(name, name)
            live[row] = _merged(live.get(row), d["reason"])
            keep[row] = _merged(keep.get(row), kept.get(name) or DOUBT_KEPT)
    found_overlays = value("overlays") or []
    if found_overlays:                       # what was found, by name, not only that something was
        live["overlays"] = _merged("Found on this lot: " + "; ".join(found_overlays) + ".", live.get("overlays") or "")
    if value("address"):
        facts["address"] = value("address")
        saved_ui["address_source"] = SUGGESTED + " · " + label("address", "address")
    zone = value("zone")
    names = {z.lower(): z for z in zones} if zones else {}
    if isinstance(zone, list):                   # two zones: the box asks which applies
        found = [names.get(z.lower(), z) for z in zone]
        saved_ui["_zones_found"] = found
        facts["zone"] = found[0]
    elif zone:
        facts["zone"] = names.get(zone.lower(), zone)
        saved_ui.pop("_zones_found", None)
    if zone:
        saved_ui["zone_source"] = SUGGESTED + " · " + label("zone", "zone")
    saved_ui["_reconfirm"] = True                # a looked-up district is the architect's only once ticked again
    saved_ui["_live"] = {k: v for k, v in live.items() if k in ("zone", "overlays")}
    if not replaces:                             # the architect's own lot: its lot, street side and ground stay
        return facts, saved_ui
    side = value("street_side") or {}
    if side.get("street"):
        street_kept = payload.get("street_storable")
        saved_ui.pop("street_name" if not street_kept else "_street_name", None)
        saved_ui["street_name" if street_kept else "_street_name"] = side["street"].title()
        saved_ui["street_source"] = SUGGESTED + " · " + label("street_side", "street")
    corner = value("corner_lot")
    streets = side.get("streets") or {}
    if corner == "no":
        facts["corner_lot"] = False
    elif corner == "yes" or (corner == "ask" and len(streets) > 1):
        facts["corner_lot"] = True               # it faces two streets (the box asks which line is the front)
    else:
        facts.pop("corner_lot", None)            # unknown: asked, never guessed
    if corner:
        saved_ui["corner_source"] = SUGGESTED + " · " + label("corner_lot", "street")
    lot = value("lot") or {}
    writes = payload.get("writes") or {}
    if lot:
        facts["lot_surveyed"] = False            # the tax map: ±2'-0" and the 2'-0" starting-house margin apply
        saved_ui["lot_source"] = label("lot", "lot")
        saved_ui["lot_area"] = lot.get("area_sf")
    if writes.get("spots"):
        saved_ui["ground_kind"] = "spot"
        saved_ui["ground_source"] = SUGGESTED + " · " + label("ground", "ground")
    if lot and not writes.get("lot_ring"):      # the City's parcels: a guide only, never kept
        look["guide"] = True
        live["lot"] = GUIDE + (" " + live["lot"] if live.get("lot") else "")
    # the doubts about what is now drawn: this lookup's, for the rows it replaced; earlier ticks don't carry over
    saved_ui["doubts"] = {k: v for k, v in keep.items() if k in CHECKABLE}
    saved_ui["_live"].update({k: v for k, v in live.items() if k in CHECKABLE})
    saved_ui["checked"] = []
    return facts, saved_ui


def _merged(old, reason):
    """Reasons add up, each said once (one that already holds another replaces it)."""
    if not old or old in reason:
        return reason
    return old if reason in old else old + " " + reason


def unsettled(saved_ui, checked=None):
    """The checker's facts["unsettled"]: each doubt about what is drawn the architect hasn't ticked I checked this
    for (or changed). Empty when there are none. Only kept-safe wording (the doubts saved)."""
    done = set(checked if checked is not None else (saved_ui or {}).get("checked") or [])
    return {k: v for k, v in ((saved_ui or {}).get("doubts") or {}).items() if k in CHECKABLE and k not in done}


def settle(saved_ui, row):
    """The architect changed that row (picked another street line, their survey or a lot they drew, other ground):
    it is theirs now, so no doubt about it is left."""
    saved_ui = dict(saved_ui)
    saved_ui["doubts"] = {k: v for k, v in (saved_ui.get("doubts") or {}).items() if k != row}
    saved_ui["_live"] = {k: v for k, v in (saved_ui.get("_live") or {}).items() if k != row}
    saved_ui["checked"] = [k for k in saved_ui.get("checked") or [] if k != row]
    if row == "lot":
        saved_ui["replaceable_lot"] = None           # never replaced by a later lookup
        saved_ui.pop("lot_source", None)
    if row == "street":                          # the architect's own line: no looked-up name stays on it
        saved_ui.pop("_street_name", None)
        saved_ui.pop("street_name", None)
    return saved_ui


UNDER_A_BOX = ("check", "save_facts", "open_box")   # what may not happen while a start box is open


def allowed(action, box_open):
    """Whether `action` may run now: a check, writing the lot facts and opening a second start box never happen while
    a start box is open (its own edits wait for it to close); anything else may."""
    return not (box_open and action in UNDER_A_BOX)


def pick_effect(what, outcome, facts, saved_ui):
    """(facts, saved_ui) after one of the start box's picks, from what the pick gave (the Rhino side only gathers it):
    street: the lot line [a, b] clicked; lot (Use my survey…): the outline picked; draw_lot: the outline drawn;
    terrain: the surface picked; spot / regrade: the points placed. Esc, Enter or nothing picked (`outcome` empty):
    nothing changes, every doubt stays (eval-integrity audit: Esc on Place spot grades wiped the ground's doubt)."""
    facts, saved_ui = dict(facts), dict(saved_ui)
    if not outcome:
        return facts, saved_ui
    if what == "street":
        facts["street_line"] = [outcome]
        saved_ui["street_source"] = ENTERED
        saved_ui = settle(saved_ui, "street")
    elif what in ("lot", "draw_lot"):
        facts = after_lot_pick(facts, outcome) if outcome != facts.get("lot_id") else facts
        facts["lot_surveyed"] = what == "lot"          # Use my survey…: a survey; drawn over the guide: not
        saved_ui = settle(saved_ui, "lot")
        if what == "draw_lot":
            saved_ui["lot_source"] = "drawn by you"
    elif what == "terrain":
        saved_ui.update(terrain_id=outcome, ground_kind="terrain")
        saved_ui = settle(saved_ui, "ground")
    elif what in ("spot", "regrade"):
        saved_ui = after_ground_pick(saved_ui, what, len(outcome))
    return facts, saved_ui


def after_ground_pick(saved_ui, what, placed):
    """Place spot grades / I'll regrade, with `placed` points actually added: the ground is the architect's only
    then. Esc or Enter with none placed changes nothing (review round 1: it settled a doubtful ground)."""
    if not placed:
        return dict(saved_ui)
    saved_ui = settle(saved_ui, "ground")
    saved_ui["ground_kind"] = what
    saved_ui.pop("ground_source", None)
    return saved_ui



def parse_feet(text):
    """A length the architect typed, in feet: 11'-8", 1' 6", 6", 6 in, 1.5, 1.5 ft, 2' -> feet; empty -> 0.0;
    anything it can't read -> None, never a silent 0."""
    import re
    t = (text or "").strip().lower()
    if not t:
        return 0.0
    t = re.sub(r"\s*(feet|foot|ft)\b", "'", t)
    t = re.sub(r"\s*(inches|inch|in)\b", '"', t)
    num = r"(\d+(?:\.\d+)?)"
    m = re.fullmatch(num + r"\s*'?", t)                                  # feet: 2, 2', 1.5 ft
    if m:
        return float(m.group(1))
    m = re.fullmatch(num + r"\s*'\s*-?\s*" + num + r'\s*"?', t)        # feet and inches: 11'-8", 1' 6
    if m:
        return float(m.group(1)) + float(m.group(2)) / 12
    m = re.fullmatch(num + r'\s*"', t)                                  # inches alone: 6", 6 in
    if m:
        return float(m.group(1)) / 12
    return None


def report_message(path, written, error=None, opened=True, open_error=None, stale=False):
    """What the panel says after a report was asked for (Zoning report… or GordiumCheck): never nothing (Ben's
    test, 2026-10-20: the button did nothing after GordiumStart, because only GordiumCheck wrote the report).
    `stale`: an earlier report is still at that path, so it is said to be out of date."""
    if not written:
        return ("Zoning report not saved: " + (error or "the check could not run") + "." +
                (" The report already at " + path + " is from an earlier check: out of date." if stale else ""))
    if opened:
        return "Report saved to " + path + " (opened)."
    return ("Report saved to " + path + ". It couldn't be opened here" + (": " + open_error if open_error else "") +
            "; open it with Excel, Numbers or any spreadsheet app.")


BUSY = "A check is running: try again in a moment."
NO_DOCUMENT = "Open a Rhino model first."


BUFFER_UNREAD = "Design buffer not understood: type it like 1'-6\" or 6\""


def draw_reason(state):
    """Why Draw is off, in one line; "" when it is on."""
    if not state.get("district_confirmed"):
        return "Confirm the district to continue."
    if parse_feet(state.get("design_buffer")) is None:
        return BUFFER_UNREAD
    if state.get("lot_missing"):
        return "Draw or pick the lot to continue."
    return ""


def can_draw(state):
    """Draw is on only once the district is confirmed (a looked-up district is only a suggestion), the design
    buffer, if typed, can be read, and there is a lot."""
    return draw_reason(state) == ""


def starting_house_fact(note, today):
    """The site fact for how far the starting house keeps back from the limits: Gordium's own figure, so never
    "confirmed by you" (the architect didn't confirm it). None when no house was drawn (`note` None)."""
    if not note:
        return None
    # the panel puts "Starting house: " in front, and it describes the house as Gordium drew it (the architect
    # may since have moved or replaced it), so it says so
    said = note[len("Starting house: "):] if note.startswith("Starting house: ") else \
        "it " + note[len("Starting house "):] if note.startswith("Starting house ") else note
    return {"value": "as first drawn, " + said, "source": SUGGESTED, "confirmed_by": None, "date": today}


def uncertain(state):
    """The one amber line for a case the box can't settle by itself, with what to do; None when there's none."""
    says = (state.get("lookup") or {}).get("says")
    question = _question(state)
    return " · ".join(t for t in (question, says) if t) or None     # never one instead of the other


def _question(state):
    """Every question the box still has (each one, never only the first)."""
    asks = []
    if state.get("corner_lot") is None:          # never guessed: unanswered, the yards wait for it (§325-19C)
        asks.append("Does this lot face two streets? Answer Corner lot? under Street side")
    elif state.get("corner_lot"):
        asks.append("This lot faces two streets: pick the front")
    if len(state.get("zones_found") or []) > 1:
        asks.append("This lot is in two zones: pick the zone that applies")
    return " · ".join(asks) or None


def ground_facts(state, lot_level):
    """The facts the checker gets from the Ground row (the checker never sees where a fact came from). Ground you
    set as finished, or ticked "No regrading near the house", counts as the finished grade the code measures
    from; ground only as it is (existing), unticked, gives height and stories needs review (spec C5)."""
    ground = state.get("ground") or {}
    kind = ground.get("kind") or "flat"
    finished = kind == "regrade" or bool(state.get("no_regrading"))
    out = {"grade_is": "finished" if finished else "existing"}
    if kind == "flat":
        out.update(ground_is_flat=True, grade_elevation=lot_level, grade_from=None)
    else:
        out.update(ground_is_flat=None, grade_elevation=None,     # the facts say which points: never the ui state
                   grade_from={"terrain": "terrain", "regrade": "finished_spots"}.get(kind, "spot"))
    return out


def fact_sources(state, today, confirmed):
    """Every fact the box set, as {value, source, confirmed_by, date}: saved in the .3dm beside the facts and
    shown in the panel and the report. `confirmed`: the architect pressed Draw (the district needs its own tick)."""
    by = "you" if confirmed else None
    ground = state.get("ground") or {}
    kind = ground.get("kind") or "flat"

    def fact(value, source, who=by):
        return {"value": value, "source": source, "confirmed_by": who, "date": today}

    return {
        "address": fact(state.get("address") or None, state.get("address_source") or ENTERED),
        "zone": fact(state.get("zone"), state.get("zone_source") or ENTERED,
                     by if state.get("district_confirmed") else None),
        "use": fact(state.get("use_name") or state.get("use"), state.get("use_source") or SUGGESTED),
        "lot": fact(lot_text(state.get("lot_area"), state.get("lot_surveyed")),
                    "your survey" if state.get("lot_surveyed") else
                    "the tax map (±2 ft)" + (" · " + state["lot_source"] if state.get("lot_source") else "")),
        # the street's name only when it may be kept (the City's roads may not: "street_name_saved" then None)
        "street": fact((state.get("street_name_saved") if "street_name_saved" in state else state.get("street_name"))
                       or "the highlighted line",
                       state.get("street_source") or SUGGESTED),
        "corner_lot": fact({None: None, False: "no, one street", True: "yes, two streets"}[state.get("corner_lot")],
                           state.get("corner_source") or SUGGESTED),
        "ground": fact(ground_text(ground) + (" · no regrading near the house" if state.get("no_regrading") else ""),
                       "as drawn" if kind == "flat" else ground.get("source") or
                       ("picked by you" if kind == "terrain" else "placed by you")),
    }


def district_confirmed(mode, zone_fact, zone):
    """Whether "I confirm" starts ticked: never on a new project (GordiumStart); on an existing one only if this
    same district was confirmed at an earlier Draw (its saved source says who confirmed it)."""
    zone_fact = zone_fact or {}
    return mode != "start" and bool(zone_fact.get("confirmed_by")) and zone_fact.get("value") == zone


def is_plan_view(parallel, direction_z, tolerance=0.99):
    """Whether a viewport is a plan view, where plan labels belong: a parallel projection looking (nearly) straight
    down. Not a perspective (labels sit on the massing) and not an elevation (Front, Right: every plan label piles
    up on the ground line)."""
    return bool(parallel) and direction_z <= -tolerance


# ---- the start box as one transaction (review rounds 1-2 of PR #19) ----------------------------------------------
#
# The box's model edits go through one BoxSession, owned by the box (gordium_rhino.confirm) and never copied. An object
# the session replaces is never deleted while the box is open: it is HELD, moved to a hidden holding layer with the
# layer it came from written on it, so Cancel (or Esc, or any error) puts the very same object back, and so does the
# next GordiumStart if Rhino closed in between (recover_held). Draw deletes what is held. Nothing on the holding layer
# is ever measured or sent to the checker (classify). `table` is the model, as a few plain calls (gordium_rhino's
# RhinoTable; a fake in the tests).

class Cancelled(Exception):
    """Esc at a prompt: the whole edit is cancelled and nothing is saved (Enter keeps what is there)."""


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


def should_recheck(dirty_at, now, running, box_open, wait, last_at=None):
    """Live mode's re-check after an edit: only once the model has been still for `wait` seconds, no check is running,
    no start box is open (its own edits mark the model changed; the check waits for the box to close, then runs:
    verification round of PR #19), and no check has finished since that edit (`last_at`: GordiumStart's own check
    after its box already covers the box's edits)."""
    if last_at is not None and dirty_at and last_at >= dirty_at:
        return False
    return bool(dirty_at) and now - dirty_at >= wait and not running and not box_open


def controls_enabled(box_open, zoom_ok):
    """(the panel's controls, Zoom to): all off while a start box is open; on closing, worked out from the panel as
    it is now, never restored from a list saved when the box opened (the header's buttons may have been rebuilt in
    between, after a document switch: verification round 4 of PR #19). Zoom to also needs a selected, current item
    (`zoom_ok`, as gordium_ui.show decides it)."""
    return (not box_open, (not box_open) and bool(zoom_ok))


def last_check_at(checked_at, document):
    """When the last completed check of THIS document finished (None: none yet). Never a placeholder's time, and
    never another document's (verification round 4: switching documents dropped the pending re-check)."""
    return (checked_at or {}).get(document)


def gate_actions(actions, box_open, say, open_ok=("legend",)):
    """The panel's actions, each doing nothing but saying BOX_BUSY while a start box is open (one choke point: none of
    them writes to the model, runs a check or opens another box under an open one; verification round of PR #19).
    `open_ok`: the ones that only show something (the legend)."""
    def gated(name, fn):
        def run(*args, **kwargs):
            if box_open() and name not in open_ok:
                say(BOX_BUSY)
                return None
            return fn(*args, **kwargs)
        return run
    return {name: gated(name, fn) for name, fn in actions.items()}


def recovery_message(removed, back):
    """What recovery did, in words (None when it did nothing)."""
    def n(k):
        return "%d object%s" % (k, "s" if k != 1 else "")
    parts = (["removed %s an unfinished start box drew" % n(removed)] if removed else []) + \
        (["put back %s it had set aside" % n(back)] if back else [])
    return " and ".join(parts) or None


def draw_then_commit(session, save):
    """Draw: everything that can fail first (the facts, the box's choices, the sources: `save`), the session's
    commit last, so a failure leaves the session to be rolled back (run_box) with nothing lost."""
    result = save()
    session.commit()
    return result


def run_box(session, loop):
    """The box's loop: any way out but Draw's (Cancel returns None from it; Esc, an error) rolls the session back."""
    try:
        result = loop()
    except BaseException:
        session.rollback()
        raise
    if result is None:
        session.rollback()
    return result


def pick_or_nothing(pick, facts, saved_ui):
    """One pick the box asked for: Esc at its prompt changes nothing."""
    try:
        return pick()
    except Cancelled:
        return facts, saved_ui


def apply_lookup(table, session, answer, facts, saved_ui, zones=()):
    """(facts, saved_ui, guide ring or None) after a lookup's answer, with its model edits made through the session:
    the lot it may replace (lookup_may_replace) and every spot grade drawn for that lot (a lookup's or the
    architect's: grades never mix across lots) held; the State's outline drawn as the lot curve and USGS ground as
    spot grades (only what lookup_box.writes allows); the City's outline only as a guide. The architect's own lot,
    its street side and ground are never touched."""
    replaces = lookup_may_replace(facts, saved_ui)
    facts, saved_ui = lookup_choices(answer, facts, saved_ui, zones, replaces=replaces)
    if (answer or {}).get("status") != "found":
        return facts, saved_ui, None
    if not replaces:
        saved_ui["_lookup"]["says"] = "Your own lot is kept: the lookup filled in the address and the district only."
        return facts, saved_ui, None
    w = answer.get("writes") or {}
    for old in [facts.get("lot_id")] + list(table.ground_points()):
        session.hold(old)
    for k in ("lot_id", "street_line", "plan_north_deg"):
        facts.pop(k, None)
    saved_ui.update(from_sample=False, replaceable_lot=None, lookup_frame=None, ground_kind="flat", lookup_spots=[])
    guide = None
    if w.get("lot_ring"):
        lot_id = table.add_lot(w["lot_ring"], "Lot · " + (facts.get("address") or "looked up"))
        session.add([lot_id])
        facts["lot_id"] = lot_id
        if w.get("street_line"):
            facts["street_line"] = w["street_line"]
        if (w.get("frame") or {}).get("rotation_deg") is not None:   # the plan is turned: name sides by true north
            facts["plan_north_deg"] = w["frame"]["rotation_deg"]
        spots = [table.add_spot(p) for p in w.get("spots") or []]
        session.add(spots)
        saved_ui.update(replaceable_lot=lot_id, lookup_frame=w.get("frame"), lookup_spots=spots)
        if spots:
            saved_ui["ground_kind"] = "spot"
    elif w.get("guide_ring"):
        guide = w["guide_ring"]
    saved_ui["lookup_snapshot"] = w.get("snapshot")
    return facts, saved_ui, guide


# ---- the context map (design_checker.context_box): the neighbourhood around a looked-up lot ---------------------
CONTEXT_LIMIT_S = 20                    # the whole fetch (three map requests, about 1 s); the Rhino side stops it then
CONTEXT_ENTRY = "context"               # the document string holding the context's snapshot (records, never data)
NO_CONTEXT = ("No neighbourhood to show: it is drawn around a lot the start box looked up (GordiumStart, type the "
              "address, Look up, Draw).")


def context_command(python, frame, fixture=None):
    """The context_box command for a lookup's saved frame (the box's `lookup_frame`), or None when there is no
    looked-up lot to centre it on (the sample lot, a drawn or picked lot, a file saved before the context map)."""
    frame = frame or {}
    origin, shift = frame.get("origin_epsg2261_us_survey_ft"), frame.get("shift_ft")
    if not origin or not shift or frame.get("rotation_deg") is None:
        return None
    args = [python, "-m", "design_checker.context_box", "--origin", repr(float(origin[0])), repr(float(origin[1])),
            "--rotation", repr(float(frame["rotation_deg"])), "--shift", repr(float(shift[0])), repr(float(shift[1]))]
    if frame.get("parcel_id"):
        args += ["--parcel", str(frame["parcel_id"])]
    return args + (["--fixture", fixture] if fixture else [])


def context_frame(facts, saved_ui):
    """The lookup frame to draw the neighbourhood around, only while the lot in the model is the one that lookup drew
    (still its `replaceable_lot`): a lot the architect drew, picked or surveyed, or one a later lookup couldn't
    place (no frame), has no neighbourhood drawn around an earlier address."""
    saved_ui = saved_ui or {}
    lot = (facts or {}).get("lot_id")
    frame = saved_ui.get("lookup_frame")
    if saved_ui.get("from_sample"):      # the sample lot (review round 3: it kept an earlier lookup's frame)
        return None
    return frame if frame and lot and lot == saved_ui.get("replaceable_lot") else None


def same_frame(a, b):
    """Whether two lookup frames are the same placement (one definition for every caller: context_step,
    context_merge, and through it draw_context; review round 7)."""
    return bool(a) and bool(b) and a == b


def is_stored(layer):
    """Whether a context layer's source may be kept in the file (store raw): its objects are in the .3dm. One
    definition for writing (context_objects), keeping (context_merge) and the live footprints (keeps_live)."""
    return (layer or {}).get("store") == "raw"


def guides_of(held, doc_serial):
    """Whether the live footprints held (STATE["context_guides"]) belong to this document."""
    return bool(held) and held.get("doc") == doc_serial


def guides_on_screen(held, doc_serial):
    """Whether this document's footprints are on screen: held for it AND with something to draw. The drawing's and
    the merge's question (keep the ones on screen?). Whether to fetch again is needs_refetch's (review round 8: a
    fetch that worked and found none is not a failure)."""
    return guides_of(held, doc_serial) and bool(held.get("lines"))


def needs_refetch(held, record, doc_serial):
    """Whether the tick or a Draw on the same lot should fetch the neighbourhood again: nothing held for this
    document (a reopened file: the footprints are never saved), or any layer, stored or live-only, whose last fetch
    failed (the record says so: review round 9, parcels down on the first Draw were never fetched again). A layer
    kept from an earlier fetch that worked carries that fetch's "found" entry (context_merge), so a kept layer
    doesn't loop. A fetch that worked and found nothing is not fetched again (review round 8: it was, on every Draw
    and tick, because "on screen" also meant "something to draw"). guides_on_screen stays the drawing's and the
    merge's question."""
    if not guides_of(held, doc_serial):
        return True
    return any((v or {}).get("status") not in DREW for v in ((record or {}).get("layers") or {}).values())


def context_step(frame, drawn, on):
    """What a box's Draw does to the neighbourhood: frame = the lot's (context_frame), drawn = the frame the one in
    the file was drawn around (context_record), on = the panel's tick.
    "keep": nothing to change (the same lot, or no lot of a lookup's and nothing drawn);
    "clear": the lot isn't a lookup's any more, so the earlier neighbourhood goes;
    "draw": a lookup's lot without its neighbourhood: the earlier one goes, this one is drawn;
    "off": the same, with Show neighbourhood off: the earlier one goes, and the box says it wasn't drawn."""
    if not frame:
        return "clear" if drawn else "keep"
    if same_frame(drawn, frame):
        return "keep"
    return "draw" if on else "off"


def context_record(payload, frame):
    """What the document's strings keep of a drawn neighbourhood: its snapshot (records and the storable layers'
    counts, never a live-only source's data) and the frame it was drawn around."""
    return dict((payload or {}).get("snapshot") or {}, frame=frame)


DREW = ("found", "partial")             # a context layer whose service answered (its objects are replaced)


def context_replaces(payload):
    """The sources whose saved objects a fetch replaces: each layer whose service answered (found or partial), and
    Gordium's own marks when any did. A layer whose service failed keeps what was saved (review of PR #23: one
    service down deleted every layer's objects, and the record then said they had failed)."""
    layers = (payload or {}).get("layers") or {}
    out = set(v.get("source") for v in layers.values() if v.get("status") in DREW and v.get("source"))
    return out | ({"gordium"} if out else set())


LIVE_ONLY = "shown live, not saved in this file."   # site_lookup.context's mark on a live-only layer's credit line
NOTE_WIDTH = 60                          # characters per line of the Sources note (it sits inside the square)
NOTE_HEIGHT_FT = 2.5                     # its text height (about the scale bar label's): ~95 ft wide at 60 characters
NOTE_LINE_FT = 1.7 * NOTE_HEIGHT_FT      # the most one displayed line may take, spacing included (the in-Rhino claim)


def note_text(credits):
    """The Sources note: each credit line wrapped to NOTE_WIDTH characters (Rhino job's screenshots, PR #23: one long
    line ran off the view). One helper for context_box (the first draw) and context_merge (a kept layer's line)."""
    import textwrap
    out = []
    for line in credits or []:
        out += textwrap.wrap(line, NOTE_WIDTH) or [""]
    return "\n".join(out)


def keeps_live(kept, old_record):
    """Whether a live-only layer is among the kept ones (its guides on screen stay, its credit line is carried)."""
    layers = (old_record or {}).get("layers") or {}
    return any(not is_stored(layers.get(n)) for n in kept or [])


def context_merge(payload, old_record, frame, live_on_screen=False):
    """The plan for drawing a fetch over the neighbourhood already in the file: the ONE decision the panel's message,
    the record, the objects deleted and the footprints on screen all follow (review rounds 6-7). A dict:
    payload (what to draw and say), record (what the file keeps), kept (the layers kept), replace (the sources
    whose objects go: rhino_logic.context_replaces around the same frame; None, every one, around another),
    keep_guides (the footprints on screen stay).
    Around the same frame, each layer whose service failed and that is still there is kept: a stored layer is in
    the file; a live-only one (the footprints, never saved) only when its guides are on screen for this document
    (`live_on_screen`, from guides_on_screen). A kept layer's record entries (the layer, its requests, its credit
    line, when it was fetched) are carried over and the Sources dot still lists it. Around another frame (or none
    saved) nothing is carried over: the earlier address's go."""
    record = context_record(payload, frame)
    old = old_record or {}
    plan = {"payload": payload, "record": record, "kept": [], "replace": None, "keep_guides": False}
    if not same_frame(old.get("frame"), frame):
        return plan
    plan["replace"] = context_replaces(payload)
    was = old.get("layers") or {}
    kept = [n for n, v in ((payload or {}).get("layers") or {}).items()
            if v.get("status") not in DREW and (was.get(n) or {}).get("status") in DREW
            and (is_stored(was.get(n)) or live_on_screen)]
    if not kept:
        return plan
    live_kept = keeps_live(kept, old)
    sources = set(was[n]["source"] for n in kept)
    record["layers"] = dict(record.get("layers") or {}, **{n: was[n] for n in kept})
    record["sources"] = list(record.get("sources") or []) + [r for r in old.get("sources") or []
                                                              if r.get("source") in sources]
    credits = list(record.get("credits") or [])
    credits += [c for c in old.get("credits") or [] if c not in credits and (live_kept or LIVE_ONLY not in c)]
    record["credits"] = credits
    # when each layer kept in THIS fetch was really fetched (review round 6: never a layer fetched again since)
    record["kept_from"] = {n: (old.get("kept_from") or {}).get(n) or old.get("fetched") for n in kept}
    objects = []
    for o in payload.get("objects") or []:
        if o.get("source") == "gordium" and o.get("name") == "Sources":
            o = dict(o, text=note_text(credits))
        objects.append(o)
    note = "Kept the %s drawn earlier (the service didn't answer)." % " and ".join(kept)
    counts = dict(payload.get("counts") or {}, **{n: was[n]["count"] for n in kept if "count" in was[n]})
    plan.update(kept=kept, keep_guides=live_kept,
                payload=dict(payload, objects=objects, counts=counts,
                             message=((payload.get("message") or "") + " " + note).strip()))
    return plan


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
    """The line after the neighbourhood is drawn (or why it isn't)."""
    payload = payload or {}
    if payload.get("status") not in ("found",):
        return payload.get("message") or "Couldn't fetch the neighbourhood: the lot is drawn without it."
    n = payload.get("counts") or {}
    kept = "%d neighbouring parcels and %d street lines (State tax map and streets, kept in this file)" % (
        n.get("parcels", 0), n.get("streets", 0))
    live = "; %d building footprints shown live (not saved)" % n["buildings"] if n.get("buildings") else ""
    sources = " ".join(payload.get("live_credits") or []) if n.get("buildings") else ""
    return "Neighbourhood drawn: " + kept + live + "." + (" " + payload["message"] if payload.get("message") else "") + \
        (" " + sources if sources else "")


ASK_LIMIT_S = 60          # s: the longest the plugin waits for one answer (the first also starts Python, loads rules)
ASK_LIMITS_S = {"start": 120}   # s, per command that can take longer: the largest building, on a deep lot


def ask_limit(cmd):
    """How long the plugin waits for the checker's answer to one `cmd` request."""
    return ASK_LIMITS_S.get(cmd, ASK_LIMIT_S)


class CheckerOutOfStep(RuntimeError):
    """The checker's next line can't be trusted to be this request's answer: the plugin restarts the checker and
    shows nothing from it."""


def pipes(process):
    """The checker's two pipes, each served by its own thread: (sends, lines). Rhino's thread never reads or writes
    a pipe, so a checker that stops answering (or stops reading a large request) can never freeze Rhino; the
    plugin only puts on `sends` and waits on `lines` with a time limit (answer_for). Put None on `sends` to end
    the writer."""
    sends, lines = queue.Queue(), queue.Queue()
    threading.Thread(target=_read_lines, args=(process.stdout, lines), daemon=True,
                     name="gordium-reader-%s" % getattr(process, "pid", "")).start()
    threading.Thread(target=_write_lines, args=(process.stdin, sends, process), daemon=True,
                     name="gordium-writer-%s" % getattr(process, "pid", "")).start()
    return sends, lines


def _read_lines(stream, lines):
    """The reader thread: every line the checker writes, then None when it stops."""
    try:
        for line in stream:
            lines.put(line)
    except (OSError, ValueError):            # the pipe closed under it (the checker was stopped)
        pass
    finally:
        lines.put(None)


def _write_lines(stream, sends, process=None):
    """The writer thread: each request, in order, until None, the checker stops reading (then the reader sees it
    stop, or ask's time limit runs out), or the checker process ends (however it was stopped)."""
    try:
        while True:
            try:
                text = sends.get(timeout=1)
            except queue.Empty:
                if process is not None and process.poll() is not None:
                    return
                continue
            if text is None:
                return
            stream.write(text)
            stream.flush()
    except (OSError, ValueError):
        pass


def exchange(sends, lines, request, limit):
    """Send one request (a dict with its "id") and wait at most `limit` s for its answer (answer_for)."""
    sends.put(json.dumps(request) + "\n")
    return answer_for(lines, request["id"], limit)


HANDLES = ("hooks", "doc_hooks", "command_hook", "overlay", "panel", "panel_parts", "toast_timer",
           "worker", "worker_sends", "worker_lines")


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


def answer_for(lines, request_id, limit):
    """The checker's answer to request `request_id`, from `lines` (a queue the plugin's reader thread fills with
    every line the checker writes, then None when it stops); None if it stopped. Raises CheckerOutOfStep when no
    line comes within `limit` seconds, when the line isn't an answer, or when it is another request's answer:
    then later lines may belong to earlier requests, so the plugin restarts the checker rather than ever showing
    an earlier check's result as this one's."""
    try:
        line = lines.get(timeout=limit)
    except queue.Empty:
        raise CheckerOutOfStep("the Gordium checker gave no answer in %d s, so it was restarted" % limit)
    if line is None:
        return None
    try:
        answer = json.loads(line)
    except ValueError:
        answer = None
    if not isinstance(answer, dict) or answer.get("id") != request_id:
        raise CheckerOutOfStep("the Gordium checker's answer didn't match the request, so it was restarted and "
                               "nothing from it is shown")
    return answer
