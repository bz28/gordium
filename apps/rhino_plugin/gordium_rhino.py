#! python3
"""Gordium in Rhino 8: GordiumCheck checks the open model against its zone's rules, shows the largest legal
building (the envelope). After an edit the results grey out until the panel's Check (or, with Check after every
edit ticked, Gordium checks again by itself).

This script only talks to Rhino. All measuring and checking is Gordium's own Python (the repo's packages, run
by its .venv in the background; docs/decisions/2026-10-20_rhino_talks_to_python.md): the lot and building
objects are copied into a small temporary .3dm, sent with the lot facts, and the answer is drawn. Nothing in
the model is changed: highlights, the envelope and the message are drawn on top (a display conduit).

Commands (set up by install.py): GordiumStart (a new project: the lot and the largest legal starting building),
GordiumCheck, GordiumLive (Check after every edit, on/off), GordiumFacts (edit the lot facts), GordiumOff (stop and clear the drawing).
"""

import json
import math
import os
import subprocess
import sys
import tempfile
import time

import Eto.Drawing as ed
import Eto.Forms as ef
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = sc.sticky.setdefault("gordium_state", {})
# what this copy attaches to Rhino (event handlers, the drawing, the panel, the checker), each with its undo: kept
# OUTSIDE STATE, so a reload that clears STATE can't orphan them; every import first undoes the previous copy's
# (2026-10-21: 23 orphaned copies' handlers were found attached; one, from before the reader thread, read the
# checker's pipe on Rhino's thread and froze Rhino)
LEFTOVERS = sc.sticky.setdefault("gordium_leftovers", {})
_MODULE = sys.modules.get(__name__)
REPO = STATE.get("repo") or os.path.dirname(os.path.dirname(HERE))   # apps/rhino_plugin -> the repo
JURISDICTION = "regulations/jurisdictions/new_york/ithaca_city"
CITY = "City of Ithaca"
sys.path.insert(0, os.path.join(REPO, "packages", "design_checker", "design_checker"))
import rhino_logic as logic  # noqa: E402  (plain Python, tested in CI: which objects, which facts)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import gordium_ui as ui  # noqa: E402  (the panel, the start box, the drawing helpers)

# an earlier copy's handlers, drawing, panel and checker are undone, released and forgotten at the end of this
# file (logic.sweep, once the functions that release them exist)


def _is_current():
    return sys.modules.get(__name__) is _MODULE


def _on(owner, name, handler):
    """Attach a handler to a Rhino event, remembered in LEFTOVERS so a later copy can always detach it."""
    event = getattr(owner, name)
    event += handler
    LEFTOVERS["%s.%s:%d" % (owner.__name__, name, id(handler))] = lambda: _off(owner, name, handler)


def _off(owner, name, handler):
    """Detach it if attached (a sweep, or an older copy's state, may already have: pythonnet then raises)."""
    event = getattr(owner, name)
    try:
        event -= handler
    except ValueError:                       # "unknown event handler": already detached
        pass
    LEFTOVERS.pop("%s.%s:%d" % (owner.__name__, name, id(handler)), None)


def _redraw():
    """Redraw the front document's views; nothing when no document is open (Rhino's start screen)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is not None:
        doc.Views.Redraw()


def _handler(kind, fn, where):
    """An event handler: guarded (never raises into Rhino) and inert once another copy of this script is loaded."""
    return kind(logic.guard(logic.current_only(fn, _is_current), where))

# no callback may raise into Rhino (on the Mac that aborts Rhino): rhino_logic.guard catches, logs, says it once
logic.ERROR_LOG = os.path.join(tempfile.gettempdir(), "gordium_errors.log")
logic.REPORT = Rhino.RhinoApp.WriteLine
CONDUIT_WORDS = {"cull": "choose what to draw", "bounds": "size the drawing", "draw_scene": "draw in the model",
                 "draw_screen": "draw the labels and status"}


def _conduit(name, o, e):
    """The display conduit's one way in: the named drawing function, guarded (a failure draws nothing this frame
    and is logged and said once, never raised into Rhino's drawing)."""
    logic.guard(globals().get(name) or (lambda *a: None), CONDUIT_WORDS.get(name, name))(o, e)


LAYERS = logic.LAYERS
ID_KEY = "gordium:id"
SECTION, ENTRY = "Gordium", "lot_facts"
UI_ENTRY = "ui"                              # the start box's own choices (district confirmed, grade source…)
GRADE_LAYER = "Gordium::Grade"               # spot grades of the ground as it is: point objects the architect places
FINISHED_LAYER = "Gordium::Grade::Finished"  # finished ground the architect will grade to ("I'll regrade"): kept apart
IDLE_SECONDS = 0.5                           # a re-check waits this long after the last edit
TOAST_SECONDS = 6                            # the "no longer complies" notice shows this long at most

GREEN, RED, AMBER = System.Drawing.Color.FromArgb(31, 122, 77), System.Drawing.Color.FromArgb(200, 50, 43), \
    System.Drawing.Color.FromArgb(154, 100, 0)
BLUE = System.Drawing.Color.FromArgb(29, 95, 138)
CONTEXT_GUIDE = System.Drawing.Color.FromArgb(135, 135, 135)    # the live footprints (the context map)


# ---- the background checker ------------------------------------------------------------------------------

def _python():
    """The repo's .venv Python (3.12): this checkout's, or the main checkout's for a worktree."""
    d = REPO
    while True:
        candidate = logic.venv_python(d, os.name)
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(d)
        if parent == d:
            raise RuntimeError("no .venv found above " + REPO)
        d = parent


def _worker():
    """The background checker, started again if it stopped or the code changed since it started."""
    p = STATE.get("worker")
    packages = os.path.join(REPO, "packages")
    now = logic.code_fingerprint(packages)
    if p is not None and logic.restart_checker(p.poll() is None, STATE.get("worker_code"), now):
        _stop_worker()                               # the process and its writer thread
        p = None
    if p is None:
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"      # UTF-8 everywhere in the checker, third-party code too (Windows uses cp1252)
        env["PYTHONPATH"] = os.pathsep.join(STATE.get("extra_paths", []) + [
            os.path.join(packages, n) for n in sorted(os.listdir(packages)) if os.path.isdir(os.path.join(packages, n))])
        log = open(os.path.join(tempfile.gettempdir(), "gordium_worker.log"), "a", encoding="utf-8")
        p = ui.spawn([_python(), "-u", "-m", "design_checker", "serve"], cwd=REPO, env=env,   # (no console on
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,            # Windows: ui.spawn)
                     universal_newlines=True, encoding="utf-8")
        SERVERS.started(p.pid)                       # the only one: any other still recorded is stopped
        # its pipes served by threads: Rhino's thread never reads or writes one (rhino_logic.pipes)
        STATE["worker_sends"], STATE["worker_lines"] = logic.pipes(p)
        STATE["worker"] = p
        STATE["worker_code"] = now
        LEFTOVERS["worker"] = _stop_worker               # a later copy of this script stops it, writer too
    return p


def _started_at(pid):
    """When the process with this number started (its own identity: a number is given again to other programs), or
    None when none is running."""
    try:
        p = System.Diagnostics.Process.GetProcessById(int(pid))
        return None if p.HasExited else str(p.StartTime.ToUniversalTime().Ticks)
    except Exception:
        return None


def _python_process(pid):
    """The process with this number if it is still running and is Python, else None."""
    try:
        p = System.Diagnostics.Process.GetProcessById(int(pid))
        return p if not p.HasExited and "python" in (p.ProcessName or "").lower() else None
    except Exception:
        return None


def _stop_pid(pid):
    p = _python_process(pid)                   # (ServerBook has matched its start time first)
    if p is not None:
        try:
            p.Kill()
        except Exception:
            pass


# every checker Gordium started, recorded with this Rhino as its owner: a new one, a reload or Rhino closing stops
# this Rhino's others (exactly one), never another Rhino's
_ME = System.Diagnostics.Process.GetCurrentProcess().Id
SERVERS = logic.ServerBook(os.path.join(tempfile.gettempdir(), "gordium_servers.json"),
                           {"pid": _ME, "start": _started_at(_ME)}, _started_at, _stop_pid)


def _stop_worker():
    """Stop the checker and forget it (the next request starts a fresh one)."""
    p = STATE.pop("worker", None)
    STATE.pop("worker_lines", None)
    sends = STATE.pop("worker_sends", None)
    if sends is not None:
        sends.put(None)
    LEFTOVERS.pop("worker", None)
    if p is not None and p.poll() is None:
        p.kill()
    SERVERS.stop_all()                               # and any an earlier load left running


def ask(request):
    """Send one request to the checker and wait for its answer."""
    _worker()
    STATE["next_id"] = STATE.get("next_id", 0) + 1
    request = dict(request, id=STATE["next_id"])
    try:                                     # only this request's answer, within its time limit; no pipe I/O here
        answer = logic.exchange(STATE["worker_sends"], STATE["worker_lines"], request,
                                logic.ask_limit(request.get("cmd")))
    except logic.CheckerOutOfStep as e:
        _stop_worker()
        raise RuntimeError(str(e) + " (see gordium_worker.log in the temp folder)")
    if answer is None:
        _stop_worker()
        raise RuntimeError("the Gordium checker stopped (see gordium_worker.log in the temp folder)")
    if not answer.get("ok"):
        raise ValueError(answer.get("error"))
    return answer["result"]


# ---- the model -------------------------------------------------------------------------------------------
# Which objects are the lot and the buildings is decided by rhino_logic (tested in CI): every object on the Site
# and Building layers and their sublayers is looked at, and anything that might be part of a building but can't
# be sent (a block, a surface) becomes a problem the checker reports, never dropped.

def _scale(doc):
    """Feet per model unit: everything Gordium stores and measures is in feet."""
    return Rhino.RhinoMath.UnitScale(doc.ModelUnitSystem, Rhino.UnitSystem.Feet)


def _holds_building(definition, depth=0):
    """Whether a block holds, at any depth, an object on the Building layer (or below it)."""
    if definition is None or depth > 32:
        return depth > 32
    for o in definition.GetObjects():
        layer = sc.doc.Layers[o.Attributes.LayerIndex].FullPath
        if logic.on_layer(layer, LAYERS["building"]):
            return True
        if isinstance(o, Rhino.DocObjects.InstanceObject) and _holds_building(o.InstanceDefinition, depth + 1):
            return True
    return False


def _sorted_objects(doc):
    """(lot candidates, buildings, problems) for the whole model."""
    lots, buildings, problems = [], [], []
    every = Rhino.DocObjects.ObjectEnumeratorSettings()
    every.NormalObjects, every.LockedObjects, every.HiddenObjects = True, True, True   # hidden still counts
    every.IdefObjects = False
    for o in doc.Objects.GetObjectList(every):
        layer = doc.Layers[o.Attributes.LayerIndex].FullPath
        kind = type(o.Geometry).__name__
        holds = isinstance(o, Rhino.DocObjects.InstanceObject) and _holds_building(o.InstanceDefinition)
        what = logic.classify(layer, kind, holds)
        if what == "lot" and o.Geometry.IsClosed:
            lots.append(o)
        elif what == "building":
            buildings.append(o)
        elif what not in (None, "lot"):
            problems.append(what)
    return lots, buildings, sorted(set(problems))


def _lot_candidates(doc):
    return _sorted_objects(doc)[0]


def _buildings(doc):
    return _sorted_objects(doc)[1]


def _segments(curve):
    return [(s.PointAtStart, s.PointAtEnd) for s in curve.DuplicateSegments()] or [(curve.PointAtStart, curve.PointAtEnd)]


def _area(curve):
    props = rg.AreaMassProperties.Compute(curve)
    return props.Area if props else 0.0


def _find(doc, object_id):
    try:
        return doc.Objects.FindId(System.Guid(object_id))
    except Exception:
        return None


def suggested_facts(doc, zones):
    """Prefilled lot facts, for the architect to confirm: the largest closed outline on the Site layer as the
    lot, its lowest line on the screen (the bottom of the Top view) as the street side, the corner-lot question left
    unanswered (never guessed: the yards wait for the answer; the box asks it), flat ground at the lowest point
    of the buildings, the lot not from a survey (the safe answer:
    lot size and coverage wait for one), the first zone with rules, a detached one-family house, and the largest
    solid as the main building. Every one is shown in the dialog; nothing is used until the architect says OK.
    In feet, whatever the model's units. The decisions are rhino_logic.suggested_facts (tested in CI); this only
    reads the model."""
    lots, buildings, _ = _sorted_objects(doc)
    lot_data = [{"id": str(o.Id), "area": _area(o.Geometry), "bottom": o.Geometry.GetBoundingBox(True).Min.Z,
                 "segments": [((a.X, a.Y), (b.X, b.Y)) for a, b in _segments(o.Geometry)]} for o in lots]
    boxes = [o.Geometry.GetBoundingBox(True) for o in buildings]
    building_data = [{"id": str(o.Id), "bottom": b.Min.Z, "volume": b.Diagonal.X * b.Diagonal.Y * b.Diagonal.Z}
                     for o, b in zip(buildings, boxes)]
    facts = logic.suggested_facts(JURISDICTION, zones, lot_data, building_data)
    return logic.to_feet(facts, _scale(doc))


def load_facts(doc):
    text = doc.Strings.GetValue(SECTION, ENTRY)
    unreadable = ValueError("the saved lot facts can't be read: run GordiumFacts to enter them again")
    try:
        facts = json.loads(text) if text else None
    except ValueError:
        raise unreadable
    if facts is not None and not isinstance(facts, dict):
        raise unreadable
    try:
        problems = ask({"cmd": "facts", "facts": facts})["problems"] if facts is not None else []
    except ValueError as e:             # the checker failed, not the facts: never treated as unreadable (reset)
        raise RuntimeError("the Gordium checker failed: " + str(e))
    if problems:                        # the same check as a facts file
        raise unreadable
    return facts


def current_facts(doc):
    """The saved facts, without a lot or main building that is no longer in the model."""
    lots, buildings, _ = _sorted_objects(doc)
    return logic.drop_stale(load_facts(doc), {str(o.Id) for o in lots}, {str(o.Id) for o in buildings})


def save_facts(doc, facts):
    if not logic.allowed("save_facts", _box_open()):   # nothing writes the facts under an open box (Draw writes its own)
        say(logic.BOX_BUSY)
        return
    _save_facts(doc, facts)


def _save_facts(doc, facts):
    doc.Strings.SetString(SECTION, ENTRY, json.dumps(facts))


def export(doc, path):
    """The lot outlines and buildings, copied into a small .3dm in the model's units (each copy keeps its
    object's id); and the problems: what is on the Building layer but can't be sent."""
    lots, buildings, problems = _sorted_objects(doc)
    f = Rhino.FileIO.File3dm()
    f.Settings.ModelUnitSystem = doc.ModelUnitSystem
    for kind in ("lot", "building"):
        layer = Rhino.DocObjects.Layer()
        layer.Name = LAYERS[kind]
        f.AllLayers.Add(layer)
    for index, objects in enumerate((lots, buildings)):
        for o in objects:
            attrs = Rhino.DocObjects.ObjectAttributes()
            attrs.LayerIndex = index
            attrs.SetUserString(ID_KEY, str(o.Id))
            floor = o.Attributes.GetUserString(logic.FLOOR_KEY)
            if floor:
                attrs.SetUserString(logic.FLOOR_KEY, floor)
            g = o.Geometry
            if isinstance(g, rg.SubD):
                g = g.ToBrep(rg.SubDToBrepOptions.Default)
            f.Objects.Add(g, attrs)
    f.Write(path, 8)
    return problems


# ---- the units boundary: Gordium works in feet; these five are the only places that convert, both ways -----
# (tests/test_check.py scans this file: no other line multiplies or divides by the unit factor)

def _model_point(doc, p, z=0.0):
    """A point in feet (from the facts or the checker), in the model's units."""
    k = 1.0 / _scale(doc)
    return rg.Point3d(p[0] * k, p[1] * k, z * k)


def _model_length(doc, feet):
    """A length or height in feet, in the model's units."""
    return feet / _scale(doc)


def _feet_point(doc, point):
    """A model point (a Point3d, in the model's units) in feet: [x, y, z]."""
    k = _scale(doc)
    return [point.X * k, point.Y * k, point.Z * k]


def _feet_length(doc, model):
    """A length or a level in the model's units, in feet."""
    return model * _scale(doc)


def _feet_area(doc, model_area):
    """An area in the model's units squared, in square feet."""
    return model_area * _scale(doc) ** 2


def street_curve(doc, facts):
    return [rg.Line(_model_point(doc, a), _model_point(doc, b)) for a, b in facts.get("street_line") or []]


# ---- drawing on top of the model -------------------------------------------------------------------------

class Overlay(Rhino.Display.DisplayConduit):
    """Everything Gordium draws: the envelope (see-through), failing buildings in red, the lot and street
    line while confirming, and the result message in the corner of each view.

    Rhino's Python makes one .NET class for a Python class that extends a Rhino class and keeps it for the whole
    session: a class redefined after an update to this script keeps running its first methods (and making a new
    class under a new name at run time crashes Rhino). So these methods only hand over to this module's
    functions, which an update does replace."""

    def __init__(self):
        Rhino.Display.DisplayConduit.__init__(self)
        self.envelope = None
        self.red = []
        self.red_ids = set()
        self.dims = []               # (line, label) for each failing distance
        self.confirm = None          # (lot curve, street lines, main building) while the dialog is open
        self.message = None          # (state, text, lines)
        self.box = rg.BoundingBox.Empty
        self.envelope_lines, self.height_limit, self.north, self.unmeasured = None, None, None, []

    def ObjectCulling(self, e):
        sys.modules[__name__]._conduit("cull", self, e)

    def CalculateBoundingBox(self, e):
        sys.modules[__name__]._conduit("bounds", self, e)

    def PostDrawObjects(self, e):
        sys.modules[__name__]._conduit("draw_scene", self, e)

    def DrawForeground(self, e):
        sys.modules[__name__]._conduit("draw_screen", self, e)


def _here(o, e):
    """Whether this viewport belongs to the document the drawing is for."""
    return e.RhinoDoc is not None and logic.draws_in(getattr(o, "doc", None), e.RhinoDoc.RuntimeSerialNumber)


def cull(o, e):
    if not _here(o, e):
        return
    if e.RhinoObject is not None and str(e.RhinoObject.Id) in o.red_ids:
        e.CullObject = True                  # drawn by draw_scene in red instead


def bounds(o, e):
    if _here(o, e) and o.box.IsValid:
        e.IncludeBoundingBox(o.box)
    context = STATE.get("context_guides") or {}
    if e.RhinoDoc is not None and logic.guides_on_screen(context, e.RhinoDoc.RuntimeSerialNumber) \
            and context.get("box") is not None and context["box"].IsValid:
        e.IncludeBoundingBox(context["box"])         # the live footprints reach past the lot


def stale(o):
    """The model changed since the result on screen was checked, by more than a moment (F7, H1): until the
    re-check, nothing is shown as complying or not."""
    t = STATE.get("dirty")
    return bool(t and time.time() - t >= ui.STALE_SECONDS and (STATE.get("last") or {}).get("at", 0) < t)


def draw_scene(o, e):
    if not _here(o, e):
        return
    d = e.Display
    dark = ui.viewport_dark()
    old = stale(o)
    for g in o.red:                          # a failing solid the plan can't show a part of (kept for blocks, SubD)
        if isinstance(g, rg.Mesh):
            d.DrawMeshWires(g, ui.status_color("does_not_comply", dark))
        else:
            d.DrawBrepWires(g, ui.status_color("does_not_comply", dark), 2)
    if getattr(o, "yards_zone", None) is not None:          # the required yards, lightly shaded
        d.DrawBrepShaded(o.yards_zone, Rhino.Display.DisplayMaterial(BLUE, 0.9))
    if o.envelope is not None:               # see-through, drawn after the solids so they show through it
        d.DrawBrepShaded(o.envelope, Rhino.Display.DisplayMaterial(BLUE, 0.88))
        # its outline only, the top dashed (the height limit): its faces' edges and isocurves banded the
        # elevations (the architect's review, 2026-10-21)
        bottom, top = getattr(o, "envelope_lines", None) or (None, None)
        if bottom is not None:
            d.DrawPolyline(bottom, BLUE, 1)
            d.DrawPatternedPolyline(top, BLUE, ui.DASHED, 2, False)
    for pts in getattr(o, "unmeasured", None) or []:     # objects on the lot the check doesn't measure: dashed, light
        d.DrawPatternedPolyline(pts, System.Drawing.Color.FromArgb(150, 150, 150), ui.DASHED, 1, True)
    if not old:                              # after the envelope, so its blue never tints them (F5)
        for g, status, _ in getattr(o, "encroach", None) or []:   # only the part over: red fails, amber review
            name = logic.highlight(status)
            colour = ui.HIGHLIGHT[name]
            d.DrawBrepShaded(g, Rhino.Display.DisplayMaterial(colour, ui.HIGHLIGHT_TRANSPARENCY))
            d.DrawBrepWires(g, colour, ui.HIGHLIGHT_EDGE[name])
    for pt in getattr(o, "grade_points", None) or []:           # spot grades
        d.DrawPoint(pt, Rhino.Display.PointStyle.X, 5, ui.status_color("complies", dark))
    if getattr(o, "lot_outline", None) is not None:              # the property line: phantom (F2)
        pts = o.lot_outline
        d.DrawPatternedPolyline(pts, ui.status_color("complies", dark), ui.PHANTOM, 2, True)
    context = STATE.get("context_guides") or {}
    if logic.guides_on_screen(context, e.RhinoDoc.RuntimeSerialNumber) \
            and (STATE.get("context_by_doc") or {}).get(e.RhinoDoc.RuntimeSerialNumber, True):
        for line in context.get("lines") or []:          # the neighbouring footprints: live only, never in the file
            d.DrawPolyline(line, CONTEXT_GUIDE, 1)
    guide = STATE.get("lookup_guide")
    if guide is not None and getattr(o, "confirm", None) is not None:    # only while the start box is open
        d.DrawPatternedPolyline(guide, ui.status_color("needs_review", ui.viewport_dark()), ui.DASHED, 2, True)
    if o.confirm is not None:
        lot, lines, main = o.confirm
        if lot is not None:
            d.DrawCurve(lot, GREEN, 4)
        for line in lines:
            d.DrawLine(line, BLUE, 7)
        if isinstance(main, rg.Brep):
            d.DrawBrepWires(main, BLUE, 3)
        elif isinstance(main, rg.Mesh):
            d.DrawMeshWires(main, BLUE, 3)


def _model_on_screen(o, viewport):
    """The model's box on screen (x0, y0, x1, y1): the lot's and the house's edges and the yard dimensions."""
    pts = [viewport.WorldToClient(p) for line in getattr(o, "plan_lines", None) or [] for p in (line.From, line.To)]
    return (min(p.X for p in pts), min(p.Y for p in pts), max(p.X for p in pts), max(p.Y for p in pts)) if pts else None


def _notice_box(o, viewport, taken):
    """The "no longer complies" notice, if showing in this view (the active one only, G1): (lines, x, y, w, h),
    placed off the model and off the boxes in `taken` (logic.notice_spot), and then taken itself."""
    toast = getattr(o, "toast", None)
    active = Rhino.RhinoDoc.ActiveDoc.Views.ActiveView
    if not toast or time.time() >= toast[1] or active is None or viewport.Id != active.ActiveViewportID:
        return None
    lines = ["✕ " + line for line in toast[0]]
    w, h = ui.text_box_size(lines, 13)
    x, y = logic.notice_spot(viewport.Bounds.Width, viewport.Bounds.Height, w, h, _model_on_screen(o, viewport), taken)
    taken.append((x, y, w, h))
    return lines, x, y, w, h


def _screen_size(viewport, points):
    """The larger side, in pixels, of the points' box on screen (None without points)."""
    if not points:
        return None
    on = [viewport.WorldToClient(p) for p in points]
    return max(max(p.X for p in on) - min(p.X for p in on), max(p.Y for p in on) - min(p.Y for p in on))


def _in_active_view(e):
    """Whether this frame is the active view's: the status box is drawn there only, not in all four (the
    architect's review, pass 2)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    active = doc.Views.ActiveView if doc is not None else None
    return active is not None and e.Viewport.Id == active.ActiveViewportID


def _dimension(d, viewport, line, color):
    """A drawing-style dimension on screen: its line and an architectural tick at 45° across each end, each on a
    thin halo (dark on a light viewport, light on a dark one) so it reads over the red and amber it often crosses
    (the failing yard's dimension, the one that matters most: Rhino check of #29). Drawn on screen after the model
    (DrawForeground), so always above the highlight."""
    a, b = viewport.WorldToClient(line.From), viewport.WorldToClient(line.To)
    strokes = [((a.X, a.Y), (b.X, b.Y))] + logic.dim_ticks((a.X, a.Y), (b.X, b.Y))
    halo = ui.halo(ui.viewport_dark())
    for ink, width in ((halo, 2 + 2 * logic.HALO_PX), (color, 2)):          # the halo under, the line over it
        for (x0, y0), (x1, y1) in strokes:
            d.Draw2dLine(System.Drawing.PointF(x0, y0), System.Drawing.PointF(x1, y1), ink, width)


def _required(d, viewport, line, tag, dark):
    """A yard's required line: a clear dashed mid-grey across its dimension, with a small "min 25'-0\"" tag at its
    end (Rhino check of #29: the faint line barely registered)."""
    r, g, b = logic.REQUIRED_RGB[1 if dark else 0]
    grey = System.Drawing.Color.FromArgb(r, g, b)
    d.DrawPatternedLine(line.From, line.To, grey, ui.DASHED, 1)
    if tag:
        q = viewport.WorldToClient(line.To)
        d.Draw2dText(tag, grey, rg.Point2d(q.X + 4, q.Y - 6), False, 10)


def _dim_label(d, viewport, quad, text, color, dark, line, kind):
    """A dimension's label in its place (logic.place_dimension): its backing and outline, and its words written
    along the dimension (readable: logic.text_angle), in the plan's own plane; past the line's end, a leader."""
    plane_z = (getattr(overlay(), "lot_outline", None) or [rg.Point3d(0, 0, 0)])[0].Z

    def model(p):
        ray = viewport.ClientToWorld(rg.Point2d(p[0], p[1]))
        ok, t = rg.Intersect.Intersection.LinePlane(ray, rg.Plane(rg.Point3d(0, 0, plane_z), rg.Vector3d.ZAxis))
        return ray.PointAt(t) if ok else None
    corners = [model(p) for p in quad]
    if any(c is None for c in corners):
        return
    d.DrawPolygon(corners, ui.backing(dark), True)
    d.DrawPolygon(corners, color, False)
    a, b = line
    angle = math.radians(logic.text_angle(a, b))
    cx, cy = sum(p[0] for p in quad) / 4, sum(p[1] for p in quad) / 4
    centre, ahead = model((cx, cy)), model((cx + math.cos(angle) * 10, cy + math.sin(angle) * 10))
    xaxis = ahead - centre
    plane = rg.Plane(centre, xaxis, rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, xaxis))
    if plane.YAxis * (model((cx, cy - 10)) - centre) < 0:     # screen y runs down: keep the words upright
        plane = rg.Plane(centre, xaxis, -plane.YAxis)
    height = centre.DistanceTo(model((cx, cy + 11)))
    words = Rhino.Display.Text3d(text, plane, height)
    words.HorizontalAlignment = Rhino.DocObjects.TextHorizontalAlignment.Center
    words.VerticalAlignment = Rhino.DocObjects.TextVerticalAlignment.Middle
    d.Draw3dText(words, color)
    words.Dispose()
    if kind == "end":                                       # a leader from the line's outer end to the label
        near = min(quad, key=lambda p: (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2)
        d.Draw2dLine(System.Drawing.PointF(a[0], a[1]), System.Drawing.PointF(near[0], near[1]), color, 1)


def draw_screen(o, e):
    if not _here(o, e):
        return
    d = e.Display
    for point, text in getattr(o, "labels", None) or []:   # each candidate's name while a pick prompt is open
        p = e.Viewport.WorldToClient(point)
        width = len(text) * 8 + 16
        d.Draw2dRectangle(System.Drawing.Rectangle(int(p.X) - width // 2, int(p.Y) - 12, width, 24), BLUE, 1,
                          System.Drawing.Color.White)
        d.Draw2dText(text, BLUE, rg.Point2d(p.X - width // 2 + 8, p.Y - 8), False, 14)
    dark = ui.viewport_dark()
    old = stale(o)
    labels = bool(STATE.get("labels_by_doc", {}).get(o.doc))     # Show on-screen labels (off by default)
    taken = []                               # labels drawn this frame: none covers another, nor the status box
    boxed = bool(o.message and labels and _in_active_view(e))   # the status box once, in the view being worked in
    if boxed:
        taken.append(logic.status_box(e.Viewport.Bounds.Width, _status_rows(o, stale(o))))
    # labels only in a plan view: parallel and looking straight down (Top). In 3D they sat on the massing, and in
    # the Front and Right elevations every plan label piled up on the ground line (Ben's test, 2026-10-20)
    plan = logic.is_plan_view(e.Viewport.IsParallelProjection, e.Viewport.CameraDirection.Z)
    on_screen = [((a.X, a.Y), (b.X, b.Y)) for a, b in ((e.Viewport.WorldToClient(line.From),
                                                         e.Viewport.WorldToClient(line.To))
                                                        for line in getattr(o, "plan_lines", None) or [])]
    obstacles = on_screen if plan else []
    # zoomed out to the neighbourhood (the lot under LABEL_MIN_LOT_PX on screen), the lot's plan labels give way
    # (judged from the lot's edges, which a lot with arcs has too, else its outline: review round 3, F5)
    lot_points = [q for _, _, edge in getattr(o, "edge_labels", None) or [] for q in (edge.From, edge.To)]
    zoomed_in = logic.labels_shown(_screen_size(e.Viewport, lot_points or getattr(o, "lot_outline", None)))
    north = getattr(o, "north", None)
    if plan and north is not None:           # a small north arrow by the lot, true north (the plan may be turned);
        taken.append(ui.north_arrow(d, e.Viewport, north[0], north[1], ui.status_color("complies", dark)))   # no label on it
    # the notice first (placed off the model and the status box), so no label is drawn under it either
    notice = _notice_box(o, e.Viewport, taken)
    elevation = logic.is_elevation_view(e.Viewport.IsParallelProjection, e.Viewport.CameraDirection.Z)
    shown = logic.dims_shown(zoomed_in, elevation)     # drawing-style dimensions: none zoomed out, none flat in elevation
    for point, text, edge in (getattr(o, "edge_labels", None) or []) if plan and labels and zoomed_in else []:
        ui.label_at(d, e.Viewport, point, text, ui.status_color("complies", dark), dark, 11, taken,   # each edge's
                    along=(edge.From, edge.To), obstacles=obstacles, leader=True)   # length, beside it, off every
        # line; an edge shorter than its label gets a leader back to it (logic.needs_leader)
    # each yard: its dimension placed where it and its label sit clear (logic.place_dimension: the status box, the
    # notice, the edges' length labels, the labels before it, never inside the house), its required line dashed
    # grey with its "min" tag, its label on the line (Rhino checks of #29)
    o.placed = {}
    footprint = [[(q.X, q.Y) for q in (e.Viewport.WorldToClient(p) for p in ring)]
                 for ring in getattr(o, "footprint", None) or []]
    away = None
    if footprint:
        pts = [p for ring in footprint for p in ring]
        away = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    for k, (line, text, status) in enumerate((getattr(o, "yard_dims", None) or []) if shown else []):
        color = ui.dim_color("complies" if old else status, dark)
        options = (getattr(o, "yard_options", None) or {}).get(k) or [(line, [])]
        on_screen = [((a.X, a.Y), (b.X, b.Y)) for a, b in ((e.Viewport.WorldToClient(c.From),
                                                             e.Viewport.WorldToClient(c.To)) for c, _ in options)]
        if old:
            text = text.split(" ", 1)[1] if text[:1] in ("?", "✕", "✓") else text
        width = None                         # no words: only the line is placed
        if plan and logic.yard_label_shown(labels, status) and zoomed_in:
            width = logic.label_width(text, 11)
        blocks = [logic.rect_quad(box) for box in taken]
        index, quad, kind = logic.place_dimension(on_screen, width, blocks, footprint[0] if footprint else None, away)
        chosen, required = options[index]
        o.placed[k] = (index, quad, kind)
        for r, tag in zip(required, ((getattr(o, "yard_tags", None) or {}).get(k) or []) + [None] * len(required)):
            _required(d, e.Viewport, r, tag, dark)
        _dimension(d, e.Viewport, chosen, color)
        if quad is not None:
            _dim_label(d, e.Viewport, quad, text, color, dark, on_screen[index], kind)
            xs, ys = [p[0] for p in quad], [p[1] for p in quad]
            taken.append((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
    height = getattr(o, "height_dim", None)
    if height is not None and elevation and zoomed_in:       # the height, dimensioned up from the grade plane
        line, text, status, limit = height
        color = ui.dim_color("complies" if old else status, dark)
        _dimension(d, e.Viewport, line, color)
        if limit is not None:                                # the limit: faint, across the dimension
            q = e.Viewport.WorldToClient(limit)
            d.Draw2dLine(System.Drawing.PointF(q.X - 14, q.Y), System.Drawing.PointF(q.X + 14, q.Y),
                         ui.faint(ui.status_color("complies" if old else status, dark)), 1)
        if old:
            text = text.split(" ", 1)[1] if text[:1] in ("?", "✕", "✓") else text
        if logic.yard_label_shown(labels, status):
            ui.label_at(d, e.Viewport, (line.From + line.To) / 2, text, color, dark, 11, taken,
                        along=(line.From, line.To))
    limit = getattr(o, "height_limit", None)
    if limit is not None and logic.is_elevation_view(e.Viewport.IsParallelProjection, e.Viewport.CameraDirection.Z):
        corners = [e.Viewport.WorldToClient(p) for p in limit[0]]
        left = min(corners, key=lambda p: p.X)       # the height limit, labelled at its left end in an elevation
        ui.draw_text_box(d, [limit[1]], BLUE, int(left.X), int(left.Y) - 30, dark, 13)
    if notice is not None:
        lines, x, y, _, _ = notice
        ui.draw_text_box(d, lines, ui.status_color("does_not_comply", dark), int(x), int(y), dark, 13)
    if not boxed:
        return
    state = "stale" if old else o.message[0]
    color = ui.status_color({"does_not_comply": "does_not_comply", "needs_review": "needs_review"}.get(state, "complies"),
                            dark)
    rows = _status_rows(o, old)
    x, y, _, _ = logic.status_box(e.Viewport.Bounds.Width, rows)
    ui.draw_text_box(d, rows, color, int(x), y, dark, 13)


def _status_rows(o, old):
    """The status box's lines: the summary, then up to 3 notes (never ✓ (D3); "–" means not checked)."""
    state, text, lines = o.message
    if old:                                  # out of date: neutral, no status (F7); press Check, or checking
        front = Rhino.RhinoDoc.ActiveDoc
        never = logic.last_check_at(STATE.get("checked_at"), front.RuntimeSerialNumber if front else None) is None
        state, text, lines = "stale", logic.out_of_date_line(_auto(front), not never), lines[:1]
    mark = {"does_not_comply": "✕", "needs_review": "?"}.get(state, "")
    return ["Gordium · " + (mark + " " if mark else "") + text] + list(lines)[:3]


def overlay():
    """The one drawing layer (its drawing code is always this script's current functions, see Overlay)."""
    o = STATE.get("overlay")
    if o is None:
        o = Overlay()
        STATE["overlay"] = o
    LEFTOVERS["overlay"] = lambda: setattr(o, "Enabled", False)    # on every enable (a reused one too)
    o.Enabled = True
    if not STATE.get("doc_hooks"):          # whatever turned drawing on: another document clears it
        documents(True)
    return o


def _drawable(g):
    """A building as a Brep or a mesh, which is what can be drawn (an extrusion or SubD becomes a Brep); a copy,
    or None if it can't be made."""
    if isinstance(g, rg.Extrusion):
        g = g.ToBrep()
    elif isinstance(g, rg.SubD):
        g = g.ToBrep(rg.SubDToBrepOptions.Default)
    elif g is not None:
        g = g.Duplicate()
    return g if isinstance(g, (rg.Brep, rg.Mesh)) else None


def _red_copy(g):
    """A failing object's copy for drawing in red: a hair (about 0.03 ft) larger than the object, so it wraps
    it instead of flickering against its faces; or None if it can't be made. Only drawn; the model is never
    changed."""
    g = _drawable(g)
    if g is None:
        return None
    box = g.GetBoundingBox(True)
    size = max(box.Diagonal.X, box.Diagonal.Y, box.Diagonal.Z, 1e-6)
    g.Transform(rg.Transform.Scale(box.Center, 1 + 0.06 / size))
    return g


def _drawn_envelope(doc, facts, env):
    """The envelope to draw. Without a grade the checker gives the buildable area but no height plane (height
    needs review until the grade is set); it is drawn the way the starting building is, standing on the lot's
    level, so the architect sees the room there is. A drawing aid only: no result depends on it."""
    if not env or env.get("top") is not None or not env.get("outline") or env.get("height") is None:
        return env
    lot = _find(doc, facts.get("lot_id") or "")
    if lot is None:
        return env
    z = _feet_length(doc, lot.Geometry.GetBoundingBox(True).Min.Z)
    return dict(env, base=z, top=z + env["height"])


def _envelope_lines(doc, env):
    """The envelope's outline at its base and at its top (the height limit), in the model's units."""
    if not env.get("outline") or env.get("top") is None or env.get("base") is None:
        return None
    lines = []
    for z in (env["base"], env["top"]):
        pts = [_model_point(doc, (x, y), z) for x, y in env["outline"]]
        lines.append(pts + [pts[0]])
    return tuple(lines)


def _north(doc, facts):
    """Where the north arrow goes and which way it points: just past the lot's top right corner, true north from
    the plan's turn (plan_north_deg). None without a lot."""
    lot = _find(doc, facts.get("lot_id") or "")
    if lot is None:
        return None
    box = lot.Geometry.GetBoundingBox(True)
    x, y = logic.north_vector(facts.get("plan_north_deg"))
    pad = _model_length(doc, 12.0)
    return rg.Point3d(box.Max.X + pad, box.Max.Y - pad, box.Min.Z), rg.Vector3d(x, y, 0)


def _unmeasured_outlines(doc, ids):
    """The plan outline (box) of each object on the lot the check doesn't measure, drawn dashed and light."""
    out = []
    for i in ids or []:
        o = _find(doc, i)
        if o is None:
            continue
        b = o.Geometry.GetBoundingBox(True)
        z = b.Max.Z
        out.append([rg.Point3d(b.Min.X, b.Min.Y, z), rg.Point3d(b.Max.X, b.Min.Y, z), rg.Point3d(b.Max.X, b.Max.Y, z),
                    rg.Point3d(b.Min.X, b.Max.Y, z), rg.Point3d(b.Min.X, b.Min.Y, z)])
    return out


def _envelope_brep(doc, env):
    """The envelope (in feet, from the checker) as a solid in the model's units."""
    if not env or not env.get("outline") or env.get("top") is None or env.get("base") is None:
        return None
    base, top = _model_length(doc, env["base"]), _model_length(doc, env["top"])
    pts = [_model_point(doc, (x, y), env["base"]) for x, y in env["outline"]]
    pts.append(pts[0])
    curve = rg.PolylineCurve(pts)
    ext = rg.Extrusion.Create(curve, base - top, True)   # extrudes along -normal: sign by winding
    brep = ext.ToBrep() if ext else None
    if brep is not None and brep.GetBoundingBox(True).Max.Z < top - 1e-6:
        brep = rg.Extrusion.Create(curve, top - base, True).ToBrep()
    return brep


# ---- the panel -------------------------------------------------------------------------------------------

def _proud(doc, brep):
    """The block grown by ui.HIGHLIGHT_PROUD_FT on every side (drawing only: the checker's geometry is exact), so
    it never shares a face with the house it marks."""
    box = brep.GetBoundingBox(True)
    eps = _model_length(doc, ui.HIGHLIGHT_PROUD_FT)
    size = box.Max - box.Min
    scale = [1 + 2 * eps / v if v > 1e-9 else 1 for v in (size.X, size.Y, size.Z)]
    brep.Transform(rg.Transform.Scale(rg.Plane(box.Center, rg.Vector3d.ZAxis), *scale))
    return brep


def _prism(doc, outline, base, top):
    """A closed prism (outline in feet, base and top heights in feet) in the model's units, or None."""
    if not outline or top is None or base is None or top - base <= 1e-9:
        return None
    pts = [_model_point(doc, (x, y), base) for x, y in outline]
    pts.append(pts[0])
    line = rg.Polyline(pts)
    line.DeleteShortSegments(doc.ModelAbsoluteTolerance)   # an edge shorter than that can't be extruded
    if line.Count < 4:
        return None
    curve = rg.PolylineCurve(line)
    ext = rg.Extrusion.Create(curve, _model_length(doc, base - top), True)   # along -normal: sign by winding
    brep = ext.ToBrep() if ext else None
    if brep is not None and brep.GetBoundingBox(True).Max.Z < _model_length(doc, top) - 1e-6:
        brep = rg.Extrusion.Create(curve, _model_length(doc, top - base), True).ToBrep()
    return brep


def _solids_for(doc, entries):
    """Each coloured block's building as a solid Rhino can cut, made once per building per check (a Brep copy, an
    extrusion or SubD converted; None for a mesh or anything else): the blocks of one building share it
    (independent review of #28, P3)."""
    out = {}
    for e in entries:
        key = e.get("building") or ""
        if key not in out:
            found = _find(doc, key)
            out[key] = _drawable(found.Geometry) if found is not None else None
    return out


def _offending(doc, e, solids=None):
    """The part of its building inside one coloured block (check.plan: a yard strip from the building's bottom to
    its top, or what rises above the height limit): Rhino's intersection of the building with the block, so a
    cantilever over a yard is coloured and not the air under it, a roof's ridge and not the sky over its slopes.
    The block is cut a hair larger (_proud) so none of its faces lies on the building's own. The block itself when
    Rhino can't intersect (a mesh, a boolean that fails): never nothing (logic.offending_pieces). `solids`: the
    buildings made once for the check (_solids_for); without it, this block's own."""
    block = _prism(doc, e["outline"], e["base"], e["top"])
    if block is None:
        return []
    solid = (solids if solids is not None else _solids_for(doc, [e])).get(e.get("building") or "")
    pieces = None
    if isinstance(solid, rg.Brep) and solid.IsSolid:       # a boolean that raises colours the block, never stops the check
        pieces = logic.guard(lambda: rg.Brep.CreateBooleanIntersection(
            solid, _proud(doc, block.DuplicateBrep()), doc.ModelAbsoluteTolerance),
            "cut the colour to the building's own shape: its whole block is coloured instead")()
    return logic.offending_pieces(pieces, block)


def _actions():
    """What the panel's buttons do (gordium_ui.make_panel): each one gated, so while a start box is open none of them
    touches the model (rhino_logic.gate_actions)."""
    return logic.gate_actions(PANEL_ACTIONS(), _box_open, say)


def PANEL_ACTIONS():
    return {"zoom": zoom_to, "report": open_report, "envelope": set_envelope, "edit_site": edit_facts,
            "survey": pick_survey, "grade": set_grade, "enter": enter_rooms, "add": add_to_check,
            "legend": lambda: ui.legend(((STATE.get("last") or {}).get("header") or {}).get("code")),
            "retry": lambda: run_check(Rhino.RhinoDoc.ActiveDoc, report=False), "ground": this_is_the_ground,
            "massing": hide_massing, "not_ground": not_the_ground, "labels": set_labels, "main": pick_main_building,
            "context": show_context, "check": check_now, "auto_check": set_auto_check}


DOCK_ID = "7c3e9a51-2d84-4b6f-9e17-5a0c8d2f4b63"   # the Gordium panel's id: Rhino remembers where it is docked


def register_dock():
    """Register the Gordium panel with Rhino (once per Rhino session; every Gordium command calls this, and the
    setup's startup command does, so a tab Rhino restores at launch is filled, never empty). A docked panel
    needs a .NET type carrying a Guid attribute, which a Python class can't: one is made here with
    Reflection.Emit, an Eto Panel whose constructor hands itself and its document's number to Python (the
    current copy of this script, through a static field). The type outlives reloads (sticky, outside
    gordium_state). Returns the panel id, or None (then the floating window is used; why is logged, said once)."""
    return logic.guard(_register_dock, "make the docked panel (the floating window is used)", fallback=None)()


def _register_dock():
    made = sc.sticky.get("gordium_dock")
    if made is None:
        made = sc.sticky["gordium_dock"] = _emit_dock_type()
    made.GetField("Build").SetValue(None, System.Action[ef.Panel, System.UInt32](
        logic.guard(_fill_dock, "fill the Gordium panel")))
    if not sc.sticky.get("gordium_dock_registered"):
        host = Rhino.PlugIns.PlugIn.Find(Rhino.PlugIns.PlugIn.IdFromName("RhinoCodePlugin"))
        Rhino.UI.Panels.RegisterPanel(host, made, "Gordium", System.Drawing.SystemIcons.Information)
        sc.sticky["gordium_dock_registered"] = True
    return made.GUID


def _emit_dock_type():
    from System.Reflection import AssemblyName, CallingConventions, FieldAttributes, MethodAttributes, TypeAttributes
    from System.Reflection.Emit import AssemblyBuilder, AssemblyBuilderAccess, CustomAttributeBuilder, OpCodes
    asm = AssemblyBuilder.DefineDynamicAssembly(AssemblyName("GordiumDock"), AssemblyBuilderAccess.Run)
    tb = asm.DefineDynamicModule("GordiumDock").DefineType("GordiumDock.Panel", TypeAttributes.Public, ef.Panel)
    guid = System.Type.GetType("System.Runtime.InteropServices.GuidAttribute")
    tb.SetCustomAttribute(CustomAttributeBuilder(guid.GetConstructor(System.Array[System.Type]([System.String])),
                                                 System.Array[System.Object]([DOCK_ID])))
    action = System.Type.GetType("System.Action`2").MakeGenericType(
        System.Array[System.Type]([System.Type.GetType("Eto.Forms.Panel, Eto"), System.UInt32]))
    build = tb.DefineField("Build", action, FieldAttributes.Public | FieldAttributes.Static)
    base = System.Type.GetType("Eto.Forms.Panel, Eto").GetConstructor(System.Type.EmptyTypes)
    for args in ([], [System.UInt32]):      # Rhino makes it with the document's number (or none)
        il = tb.DefineConstructor(MethodAttributes.Public, CallingConventions.Standard,
                                  System.Array[System.Type](args)).GetILGenerator()
        skip = il.DefineLabel()
        il.Emit(OpCodes.Ldarg_0)
        il.Emit(OpCodes.Call, base)
        il.Emit(OpCodes.Ldsfld, build)
        il.Emit(OpCodes.Brfalse_S, skip)
        il.Emit(OpCodes.Ldsfld, build)
        il.Emit(OpCodes.Ldarg_0)
        il.Emit(OpCodes.Ldarg_1 if args else OpCodes.Ldc_I4_0)
        il.Emit(OpCodes.Callvirt, action.GetMethod("Invoke"))
        il.MarkLabel(skip)
        il.Emit(OpCodes.Ret)
    return tb.CreateType()


def _fill_dock(host, serial):
    """Rhino made the panel for a document window: remember it (closed documents' panels let go); it is filled when
    Gordium shows its results."""
    hosts = logic.prune_hosts(sc.sticky.get("gordium_dock_hosts"),
                              [d.RuntimeSerialNumber for d in Rhino.RhinoDoc.OpenDocuments()])
    hosts[int(serial)] = host
    sc.sticky["gordium_dock_hosts"] = hosts
    host.MinimumSize = ed.Size(ui.PANEL_WIDTH, 420)      # floating, Rhino sizes it by this (not 200 x 200)
    label = ef.Label()
    label.Text = "Gordium: run GordiumStart or GordiumCheck to check this model."
    host.Content = label


def _box_open():
    gate = STATE.get("box_gate")
    return bool(gate is not None and gate.open)


def panel():
    """The Gordium panel, made once and shown: docked in Rhino's own panels (Mac and Windows), or a floating
    window if the panel couldn't be registered."""
    p = STATE.get("panel_parts")
    doc = Rhino.RhinoDoc.ActiveDoc
    dock = register_dock()
    if dock is not None:
        ui.open_dock(dock)
        host = logic.dock_host(sc.sticky.get("gordium_dock_hosts") or {}, doc.RuntimeSerialNumber if doc else None)
        if host is not None:
            if p is None or getattr(p["form"], "host", None) is not host or not p["form"].Visible:
                p = ui.make_panel(_actions(), ui.DockHost(dock, host), context_on=_context_on(doc))
                ui.set_auto_tick(p, _auto(doc))
                STATE["panel_parts"] = p
                LEFTOVERS["panel"] = p["form"].Close
            if logic.place_panel_now(p.get("placed")):          # once: then where the architect puts it
                p["placed"] = ui.fit_floating(host, Rhino.UI.RhinoEtoApp.MainWindowForDocument(doc) if doc else None)
            return p
    if p is None or not p["form"].Visible:
        p = ui.make_panel(_actions(), context_on=_context_on(doc))
        ui.set_auto_tick(p, _auto(doc))
        STATE["panel_parts"] = p
        LEFTOVERS["panel"] = p["form"].Close
        p["form"].Show()
    return p


def show_panel(p, result, facts, error=None):
    """Fill the panel from the checker's view (or say the check couldn't run). Kept by name for the scripted
    tests; the panel's contents come only from `result["view"]`."""
    ui.show(p, (result or {}).get("view"), error=error)


def zoom_to(item):
    """Frame the selected item: yards in Top, height and stories in a front elevation (D9)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if not item:
        say("Zoom to: select an item in the list first.")
        return
    box = rg.BoundingBox.Empty
    for i in item.get("objects") or []:
        o = _find(doc, i)
        if o is not None:
            box.Union(o.Geometry.GetBoundingBox(True))
    for p in item.get("points") or []:
        box.Union(_model_point(doc, p))
    if not box.IsValid:
        say("Zoom to: " + (item.get("name") or "this item") + " has nothing drawn in the model to zoom to.")
        return
    box.Inflate(max(box.Diagonal.Length * 0.25, _model_length(doc, 5)))
    view = doc.Views.Find("Front" if item.get("zoom") == "front" else "Top", False) or doc.Views.ActiveView
    doc.Views.ActiveView = view
    view.ActiveViewport.ZoomBoundingBox(box)
    doc.Objects.UnselectAll()                # and selected, so it's clear what the row is about (the review)
    picked = [o for o in (_find(doc, i) for i in item.get("objects") or []) if o is not None and o.IsSelectable()]
    for o in picked:
        o.Select(True)
    if picked:
        say("Zoom to: " + (item.get("name") or "this item") + ": " + str(len(picked)) + " object" +
            ("s" if len(picked) != 1 else "") + " selected.")
    view.Redraw()


def set_labels(on):
    """Show on-screen labels: the viewport's labels and status box, on or off, saved in this document."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        say(logic.NO_DOCUMENT)
        return
    state = dict(_ui_state(doc), show_labels=bool(on))
    _save_ui_state(doc, state)
    STATE.setdefault("labels_by_doc", {})[doc.RuntimeSerialNumber] = logic.labels_on(state)
    doc.Views.Redraw()


def _auto(doc):
    """This document's Check after every edit (rhino_logic.auto_check), read once from its settings and kept per
    document (the idle handler asks often)."""
    if doc is None:
        return False
    known = STATE.setdefault("auto_by_doc", {})
    if doc.RuntimeSerialNumber not in known:
        known[doc.RuntimeSerialNumber] = logic.auto_check(_ui_state(doc))
    return known[doc.RuntimeSerialNumber]


def set_auto_check(on):
    """Check after every edit, on or off, saved in this document. Turned on with the results out of date: checks
    now (it would have)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        say(logic.NO_DOCUMENT)
        return
    if not STATE.get("live"):           # the tick needs edits noticed to act on them
        live(True)
    _save_ui_state(doc, dict(_ui_state(doc), auto_check=bool(on)))
    STATE.setdefault("auto_by_doc", {})[doc.RuntimeSerialNumber] = bool(on)
    ui.set_auto_tick(STATE.get("panel_parts"), on)
    # the edit's own time is kept (never moved earlier: a check from before it would then count as covering it,
    # review round 1, P1): turned on, the next idle checks it (it is already older than IDLE_SECONDS, or soon)
    if STATE.get("dirty") and STATE.get("panel_parts") is not None:
        ui.show(STATE["panel_parts"], None, checking=True)     # the header: checking, or press Check
    say("Checks after every edit: " + ("on" if on else "off (press Check after you edit)"))
    doc.Views.Redraw()


def check_now():
    """The panel's Check: the model as it is now, checked (the results no longer greyed)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        say(logic.NO_DOCUMENT)
        return None
    STATE["dirty"] = None
    return run_check(doc, report=False)


def set_envelope(on):
    STATE["envelope_on"] = bool(on)
    run_check(Rhino.RhinoDoc.ActiveDoc, report=False)


def _ui_state(doc):
    try:
        return json.loads(doc.Strings.GetValue(SECTION, UI_ENTRY) or "{}")
    except ValueError:
        return {}


def _save_ui_state(doc, state):
    """The box's choices into the .3dm: only what may be kept (rhino_logic.storable_ui: never a session key)."""
    doc.Strings.SetString(SECTION, UI_ENTRY, json.dumps(logic.storable_ui(state)))


def pick_survey():
    """Pick survey lot lines…: the lot outline the architect says is from a survey (a closed curve on the Site
    layer); lot size and coverage no longer wait for one."""
    doc = Rhino.RhinoDoc.ActiveDoc
    try:
        facts = current_facts(doc)
        lots = _lot_candidates(doc)
        picked = _pick(doc, "Click the surveyed lot outline (Site layer); Enter keeps the one outlined", lots, "Lot",
                       Rhino.DocObjects.ObjectType.Curve) if len(lots) > 1 else (str(lots[0].Id) if lots else None)
    except Cancelled:
        say("Cancelled: nothing changed.")
        return
    picked, why = logic.survey_pick(len(lots), picked, facts.get("lot_id"))
    if not picked:
        say(why)
        return
    facts = logic.after_lot_pick(facts, picked) if picked != facts.get("lot_id") else facts
    facts["lot_surveyed"] = True
    saved_ui = logic.settle(_ui_state(doc), "lot")
    _save_ui_state(doc, saved_ui)
    left = logic.unsettled(saved_ui)
    if left:
        facts["unsettled"] = left
    else:
        facts.pop("unsettled", None)
    _set_source(doc, "lot", logic.lot_text(None, True).replace("area not known · ", ""), "your survey")
    save_facts(doc, facts)
    run_check(doc, report=False)


def _grade_points(doc, finished=False):
    """Spot grades: the point objects on Gordium::Grade (or, finished, on Gordium::Grade::Finished only), in feet.
    The two are never mixed: an existing spot grade must never count as finished grade."""
    index = doc.Layers.FindByFullPath(FINISHED_LAYER if finished else GRADE_LAYER, -1)
    if index < 0:
        return []
    return [_feet_point(doc, o.Geometry.Location)
            for o in doc.Objects.FindByLayer(doc.Layers[index]) or [] if isinstance(o.Geometry, rg.Point)]


def _terrain_points(doc, terrain_id):
    """The terrain sampled just outside each wall of each building, every time the check runs: so the grade
    follows the building when it moves (C4). Feet."""
    terrain = _find(doc, terrain_id or "")
    if terrain is None:
        return []
    out = []
    for b in _buildings(doc):
        box = b.Geometry.GetBoundingBox(True)
        center = box.Center
        brep = _drawable(b.Geometry)
        edges = []
        if isinstance(brep, rg.Brep):
            for face in brep.Faces:
                n = face.NormalAt(face.Domain(0).Mid, face.Domain(1).Mid)
                if n.Z < -0.9:                         # the bottom face: its edges are the walls at the ground
                    loop = face.OuterLoop.To3dCurve()
                    edges += [(s.PointAtStart, s.PointAtEnd) for s in loop.DuplicateSegments()]
        for a, c in edges:
            mid = (a + c) / 2
            out_dir = rg.Vector3d(mid.X - center.X, mid.Y - center.Y, 0)
            out_dir.Unitize()
            probe = mid + out_dir * _model_length(doc, 1.0)          # 1 ft outside the wall
            hit = _down_onto(terrain.Geometry, probe)
            if hit is not None:
                out.append(_feet_point(doc, hit))
    return out


def _down_onto(geometry, p):
    line = rg.Line(rg.Point3d(p.X, p.Y, p.Z + 1e5), rg.Point3d(p.X, p.Y, p.Z - 1e5))
    if isinstance(geometry, rg.Mesh):
        hits = rg.Intersect.Intersection.MeshLine(geometry, line)
        hits = hits[0] if isinstance(hits, tuple) else hits
    else:
        brep = _drawable(geometry)
        if brep is None:
            return None
        ok, curves, hits = rg.Intersect.Intersection.CurveBrep(rg.LineCurve(line), brep, 0.001)
    hits = list(hits or [])
    return max(hits, key=lambda h: h.Z) if hits else None


def set_grade():
    """Set grade…: the start box, open at its Grade row."""
    edit_facts()


def enter_rooms(needs):
    """A row's "Enter …" button: one prompt for each fact it waits for (`needs`, the row's own list), a whole number
    or yes / no. Enter skips one: it stays unset (never 0 or no), so its rule keeps waiting."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if not needs:
        say("This row isn't waiting for anything you can enter.")
        return
    try:
        facts = current_facts(doc)
        answers = {}
        for key in needs:
            prompt, kind, _ = logic.STATED_FACTS[key]
            answers[key] = _count(prompt) if kind == "count" else _ask_yes_no_or_skip(prompt)
    except Cancelled:
        say("Cancelled: nothing changed.")
        return
    save_facts(doc, logic.update_counts(facts, answers))
    run_check(doc, report=False)
    refused = logic.refused_stories((STATE.get("last") or {}).get("items")) if "stories" in answers else None
    if refused:                         # fewer stories than the floors drawn: the measuring refuses it, so is it
        save_facts(doc, facts)
        run_check(doc, report=False)
        say(refused)


def pick_main_building():
    """Pick the main building… (the panel): with several buildings, the one the yards, height and stories are
    measured to. Click it, or choose one; Enter keeps it."""
    doc = Rhino.RhinoDoc.ActiveDoc
    facts = current_facts(doc)
    buildings = _buildings(doc)
    if len(buildings) < 2:
        say("There is only one building: it is the main building.")
        return
    try:
        picked = _pick(doc, "Click the main building (a solid on the Building layer), or choose one; Enter keeps it",
                       buildings, "Building")
    except Cancelled:
        say("Cancelled: nothing changed.")
        return
    if picked:
        facts["main_building"] = picked
        save_facts(doc, facts)
    run_check(doc, report=False)


def add_to_check(ids):
    """Add to check…: objects on the lot that aren't measured go on the Building layer, so every rule measures
    them."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if not ids:
        say("Nothing selected to add to the check: pick the objects in the row first.")
        return
    index = _layer(doc, LAYERS["building"])
    for i in ids or []:
        o = _find(doc, i)
        if o is not None:
            attrs = o.Attributes.Duplicate()
            attrs.LayerIndex = index
            doc.Objects.ModifyAttributes(o, attrs, True)
    run_check(doc, report=False)


def _not_included(doc, lot):
    """Anything on the lot (its footprint reaching more than 0.1 ft into the lot's outline, partly or wholly:
    rhino_logic.reaches_into_lot) that could be a building and isn't measured (rhino_logic.could_be_building: solids,
    polysurfaces, meshes, SubD, blocks; not the picked terrain, what the architect marked as the ground, the
    Building layer or Gordium's own layers): each one makes the check need review (C8). Nothing is ever left out
    on a guess: a topography mesh stays here (marked as looking like the ground, see _ground_like) until the
    architect says "This is the ground"."""
    if lot is None:
        return []
    ring = _plan_points(lot.Geometry)
    reach = _model_length(doc, logic.ON_LOT_REACH)              # ft -> model units
    lot_box = _plan_box(lot.Geometry)
    out = []
    every = Rhino.DocObjects.ObjectEnumeratorSettings()          # hidden and locked too, as for the Building layer:
    every.NormalObjects, every.LockedObjects, every.HiddenObjects = True, True, True   # a hidden shed still counts
    state = _ui_state(doc)
    known_ground = {str(state.get("terrain_id") or "")} | set(state.get("ground_ids") or [])
    for o in doc.Objects.GetObjectList(every):
        layer = doc.Layers[o.Attributes.LayerIndex].FullPath
        g = o.Geometry
        could_be = logic.could_be_building(
            type(g).__name__, (isinstance(g, rg.Brep) and g.IsSolid) or (isinstance(g, rg.Mesh) and g.IsClosed),
            g.Faces.Count if isinstance(g, (rg.Brep, rg.Mesh)) else 0)
        if not could_be or str(o.Id) in known_ground or logic.on_layer(layer, LAYERS["building"]) \
                or not logic.left_out_candidate(layer):        # Gordium's own layers, but for the neighbourhood's
            continue
        box = _plan_box(g)
        if not logic.box_near_lot(box, lot_box, reach):             # far from the lot: no outline work
            continue
        if logic.reaches_into_lot(ring, _plan_points(g), reach, box):   # its footprint, against the lot's outline
            out.append(str(o.Id))
    return out


def _plan_box(g):
    """An object's plan bounding box, (x0, y0, x1, y1), in the model's units."""
    b = g.GetBoundingBox(True)
    return (b.Min.X, b.Min.Y, b.Max.X, b.Max.Y)


def _plan_points(g):
    """Points of an object in plan, (x, y), enough to outline it: a curve's points along it; a mesh's vertices; a
    solid's vertices and points along its edges (curved walls too); anything else (a block, a SubD), its bounding
    box's corners (bigger than the object: the cautious direction), as for a mesh of over 50,000 vertices."""
    if isinstance(g, rg.Curve):
        ok, poly = g.TryGetPolyline()
        pts = list(poly) if ok else [g.PointAt(t) for t in g.DivideByCount(64, True)]
    elif isinstance(g, rg.Mesh):
        pts = list(g.Vertices)
    else:
        brep = g if isinstance(g, rg.Brep) else (g.ToBrep() if isinstance(g, rg.Extrusion) else None)
        if brep is not None:
            pts = [v.Location for v in brep.Vertices]
            for e in brep.Edges:
                pts += [e.PointAt(t) for t in (e.DivideByCount(8, True) or [])]
            for f in brep.Faces:                 # a dome or a revolved solid: its surface gives its outline
                u, v = f.Domain(0), f.Domain(1)
                pts += [f.PointAt(u.ParameterAt(i / 6.0), v.ParameterAt(k / 6.0)) for i in range(7) for k in range(7)]
        else:
            pts = []
    if not pts or len(pts) > 50000:          # nothing to outline it by, or a huge mesh (a terrain): its box's corners
        b = g.GetBoundingBox(True)
        pts = [b.Min, b.Max, rg.Point3d(b.Min.X, b.Max.Y, 0), rg.Point3d(b.Max.X, b.Min.Y, 0)]
    return [(p.X, p.Y) for p in pts]


def _ground_like(doc, ids, lot):
    """Of the left-out objects, the open meshes and surfaces spreading over most of the lot: they look like the
    ground, so the row offers "This is the ground". Only a label: they stay left out until the architect says."""
    if lot is None:
        return []
    box = lot.Geometry.GetBoundingBox(True)
    out = []
    for i in ids:
        o = _find(doc, i)
        g = o.Geometry if o is not None else None
        if g is None:
            continue
        ob = g.GetBoundingBox(True)
        closed = (isinstance(g, rg.Brep) and g.IsSolid) or (isinstance(g, rg.Mesh) and g.IsClosed)
        if logic.looks_like_ground(type(g).__name__, closed, (ob.Min.X, ob.Min.Y, ob.Max.X, ob.Max.Y),
                                   (box.Min.X, box.Min.Y, box.Max.X, box.Max.Y)):
            out.append(i)
    return out


def this_is_the_ground(ids):
    """The panel's "This is the ground": the architect's own word that these objects are the ground, saved in the
    file with who said it and when (a site fact, shown in the panel and the report, with "Not the ground" to undo
    it); then the check runs again without them."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if not ids:
        say("Nothing selected to mark as the ground: pick the objects in the row first.")
        return
    state = _ui_state(doc)
    state["ground_ids"] = sorted(set(state.get("ground_ids") or []) | set(ids or []))
    _save_ui_state(doc, state)
    n = len(state["ground_ids"])
    _set_source(doc, "ground_marked", f"{n} object{'s' if n != 1 else ''} left out of the check as the ground",
                logic.ENTERED)
    run_check(doc, report=False)


def not_the_ground():
    """Undo "This is the ground": every object marked so is checked again (counted as left out until added)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    state = _ui_state(doc)
    state.pop("ground_ids", None)
    _save_ui_state(doc, state)
    _set_source(doc, "ground_marked", None, None)
    run_check(doc, report=False)


def _set_source(doc, key, value, source, confirmed_by="you"):
    """One site fact's source, changed outside the start box (the panel's buttons): {value, source, confirmed_by,
    date}, saved with the others; value None removes it. So the panel and the report never show a stale source."""
    sources = fact_sources(doc)
    if value is None:
        sources.pop(key, None)
    else:
        sources[key] = {"value": value, "source": source, "confirmed_by": confirmed_by,
                        "date": logic.city_day()}
    doc.Strings.SetString(SECTION, SOURCES_ENTRY, json.dumps(sources))


def _extras(doc, facts):
    """What the panel needs to say about the check beyond the measurements: what was sent (C8), objects on the
    lot left out, the use's name."""
    buildings = _buildings(doc)
    groups = {i for o in buildings for i in (o.Attributes.GetGroupList() or [])}
    layers = sorted({doc.Layers[o.Attributes.LayerIndex].FullPath for o in buildings})
    left_out = _not_included(doc, _find(doc, facts.get("lot_id") or ""))
    main = _find(doc, facts.get("main_building") or "") if facts.get("main_building") else None
    return {"scope": {"groups": len(groups), "solids": len(buildings), "layer": ", ".join(layers)},
            "main_name": logic.building_name(doc.Layers[main.Attributes.LayerIndex].FullPath, main.Attributes.Name,
                                             bool(main.Attributes.GetGroupList())) if main else None,
            "not_included": left_out, "touching": _touching(doc, left_out, buildings),
            "context_left_out": logic.context_left_out(
                {i: doc.Layers[_find(doc, i).Attributes.LayerIndex].FullPath for i in left_out if _find(doc, i)}),
            "ground_like": _ground_like(doc, left_out, _find(doc, facts.get("lot_id") or "")),
            "sources": fact_sources(doc)}


def _touching(doc, ids, buildings):
    """The left-out solids that may be part of the building: their box within 0.1 ft of a building's box. Boxes
    say "touching" more often than the shapes do, which only ever makes the check more cautious."""
    gap = _model_length(doc, 0.1)
    boxes = []
    for b in buildings:
        bb = b.Geometry.GetBoundingBox(True)
        bb.Inflate(gap)
        boxes.append(bb)
    out = []
    for i in ids:
        o = _find(doc, i)
        bb = o.Geometry.GetBoundingBox(True) if o is not None else None
        if bb is not None and any(rg.BoundingBox.Intersection(bb, k).IsValid for k in boxes):
            out.append(i)
    return out


# ---- the confirm dialog and the lot facts ----------------------------------------------------------------

def _describe(facts, uses):
    ground = facts.get("grade_elevation")
    return ((facts["address"] + "\n" if facts.get("address") else "") +
            CITY + " · zone " + str(facts.get("zone")) + " · " + uses.get(facts.get("use"), str(facts.get("use"))) +
            "\n" + logic.STREET_LABEL + " = the highlighted blue line · " +
            ("a corner lot (two streets)" if facts.get("corner_lot") else "not a corner lot") +
            ("\nMain building = the one outlined in blue" if facts.get("main_building") else "") +
            "\nGround: " + ("flat" if facts.get("ground_is_flat") else "sloped") + " at z = " +
            ("?" if ground is None else format(ground, "g")) + " ft · lot outline " +
            ("from a survey" if facts.get("lot_surveyed") else "not from a survey (lot size and coverage wait for one)"))


def _highlight(doc, facts):
    """Outline what the facts say now: the lot in green, its street lines in blue, the main building in blue."""
    lot = _find(doc, facts.get("lot_id") or "")
    main = _find(doc, facts.get("main_building") or "") if facts.get("main_building") else None
    o = overlay()
    o.doc = doc.RuntimeSerialNumber
    o.confirm = (lot.Geometry if lot else None, street_curve(doc, facts), _drawable(main.Geometry) if main else None)
    doc.Views.Redraw()


SOURCES_ENTRY = "fact_sources"               # Gordium / fact_sources: {fact: {value, source, confirmed_by, date}}


def fact_sources(doc):
    try:
        return json.loads(doc.Strings.GetValue(SECTION, SOURCES_ENTRY) or "{}")
    except ValueError:
        return {}


def _lot_level(doc, facts):
    """The lot outline's level, in feet (the ground "as drawn" when nothing else says where it is)."""
    lot = _find(doc, facts.get("lot_id") or "")
    return _feet_length(doc, lot.Geometry.GetBoundingBox(True).Min.Z) if lot is not None else 0.0


def _box_state(doc, facts, options, saved_ui, mode="check"):
    """The start box's state from the facts, their saved sources and the box's own choices (rhino_logic.box_rows
    turns it into rows). "I confirm" is unticked on every new project: only a district confirmed at an earlier
    Draw, and unchanged since, stays ticked."""
    sources = fact_sources(doc)
    lot = _find(doc, facts.get("lot_id") or "")
    area = None
    if lot is not None:
        amp = rg.AreaMassProperties.Compute(lot.Geometry)
        area = _feet_area(doc, amp.Area) if amp else None
    zone_fact = sources.get("zone") or {}
    confirmed = logic.district_confirmed(mode, zone_fact, facts.get("zone")) and not saved_ui.get("_reconfirm")
    kind = saved_ui.get("ground_kind") or {"spot": "spot", "terrain": "terrain", "finished_spots": "regrade"}.get(
        facts.get("grade_from"), "flat")
    points = _grade_points(doc, kind == "regrade")      # the set the ground row names, never both mixed
    if kind in ("spot", "regrade") and not points:
        kind = "flat"
    zs = [p[2] for p in points]
    span = (_ft_text(min(zs)) + " to " + _ft_text(max(zs))) if zs and kind in ("spot", "regrade") else ""
    ground_source = saved_ui.get("ground_source") if kind == "spot" else None
    default = "the sample project" if saved_ui.get("from_sample") else logic.SUGGESTED

    def source(key, fallback=None):                    # a lookup's (this session), what was saved at the last Draw,
        return saved_ui.get(key + "_source") or (sources.get(key) or {}).get("source") or fallback or default

    return {"address": facts.get("address") or "", "address_source": source("address"),
            "zone": facts.get("zone"),          # no district: no source (never the last Draw's "suggested")
            "zone_source": source("zone", logic.ENTERED) if facts.get("zone") else None,
            "zone_said": saved_ui.get("_zone_said"),     # the lookup's words, this session only
            "district_confirmed": confirmed, "use": facts.get("use"), "use_source": source("use"),
            "use_name": (options.get("uses") or {}).get(facts.get("use"), facts.get("use")),
            "lot_area": area, "has_lot": lot is not None, "lot_surveyed": bool(facts.get("lot_surveyed")),
            # the street's name only with its street line (a survey outline or a corner answer drops the line:
            # review round 3, F6); this session's lookup words first, then the name saved at the last Draw
            "street_name": (saved_ui.get("_street_name") or saved_ui.get("street_name") or facts.get("street_name"))
            if facts.get("street_line") else None,
            "street_name_saved": None if saved_ui.get("_street_name") or not facts.get("street_line")
            else saved_ui.get("street_name"),
            "street_source": saved_ui.get("street_source") or source("street"),
            "ground": {"kind": kind, "count": len(points), "range": span, "source": ground_source},
            "ground_fall": saved_ui.get("ground_fall"),     # the looked-up ground's fall: said, never used (MVP)
            "no_regrading": bool(saved_ui.get("no_regrading")), "corner_lot": facts.get("corner_lot"),
            "corner_source": saved_ui.get("corner_source") or source("corner_lot"),
            "zones_found": saved_ui.get("_zones_found") or [],
            "design_buffer": saved_ui.get("design_buffer") or "0'-0\"",
            "lot_source": saved_ui.get("lot_source"), "lookup": saved_ui.get("_lookup") or {},
            "doubts": saved_ui.get("doubts") or {}, "live": saved_ui.get("_live") or {},
            "checked": list(saved_ui.get("checked") or []), "lot_missing": lot is None,
            "_poll": _lookup_poll if (saved_ui.get("_lookup") or {}).get("looking") else None}


def _ft_text(feet):
    inches = int(round(feet * 12 * 8))            # to 1/8 in
    sign = "-" if inches < 0 else ""
    ft, rest = divmod(abs(inches), 96)
    whole, eighth = divmod(rest, 8)
    return "%s%d'-%d%s\"" % (sign, ft, whole, (" %d/8" % eighth) if eighth else "")


def _apply_box(doc, facts, state, saved_ui):
    """The facts (what the checker gets) and the box's own choices, from what the box says."""
    facts, saved_ui = logic.corner_answered(facts, saved_ui, state.get("corner_lot"))   # a changed answer: the
    facts = dict(facts, address=state["address"] or None, zone=state["zone"], use=state["use"],  # street picked again
                 lot_surveyed=bool(state.get("lot_surveyed")))
    if not facts.get("address"):
        facts.pop("address")
    facts.pop("grade_points", None)                 # read (or sampled) from the model at every check
    for key, value in logic.ground_facts(state, _lot_level(doc, facts)).items():
        if value is None:
            facts.pop(key, None)
        else:
            facts[key] = value
    saved_ui = dict(logic.saved_sources(saved_ui, state), ground_kind=(state.get("ground") or {}).get("kind") or "flat",
                    no_regrading=bool(state.get("no_regrading")), design_buffer=state.get("design_buffer") or "0'-0\"",
                    checked=list(state.get("checked") or []))
    left = logic.unsettled(saved_ui)                # looked-up facts found doubtful, not yet checked or changed
    if left:
        facts["unsettled"] = left
    else:
        facts.pop("unsettled", None)
    return facts, saved_ui


def _place_spots(doc, prompt, layer_path=GRADE_LAYER):
    """Each click places a spot grade; Enter or Esc when done. The ids of the points placed (none: nothing changed)."""
    layer = _layer(doc, layer_path)
    placed = []
    while True:
        rc, point = Rhino.Input.RhinoGet.GetPoint(prompt, True)
        if rc != Rhino.Commands.Result.Success:
            break
        attrs = Rhino.DocObjects.ObjectAttributes()
        attrs.LayerIndex = layer
        placed.append(str(doc.Objects.AddPoint(point, attrs)))
        doc.Views.Redraw()
    return placed


class RhinoTable:
    """The model as rhino_logic.BoxSession and apply_lookup use it: a few plain calls on one document."""

    def __init__(self, doc):
        self.doc = doc

    def exists(self, object_id):
        return _find(self.doc, object_id or "") is not None

    def delete(self, object_id):
        o = _find(self.doc, object_id)
        if o is not None:
            self.doc.Objects.Delete(o, True)

    def layer_of(self, object_id):
        return self.doc.Layers[_find(self.doc, object_id).Attributes.LayerIndex].FullPath

    def _move(self, object_id, layer_path, held_from):
        o = _find(self.doc, object_id)
        attrs = o.Attributes.Duplicate()
        attrs.LayerIndex = _layer(self.doc, layer_path)
        attrs.SetUserString(logic.HELD_FROM, held_from)
        self.doc.Objects.ModifyAttributes(o, attrs, True)

    def hold(self, object_id, token):
        """Onto the hidden holding layer, the layer it came from and the session holding it written on it (for
        Cancel, and for a Rhino that closed mid-session: recover_held)."""
        self._move(object_id, logic.HOLDING_LAYER, self.layer_of(object_id))
        self._mark(object_id, logic.HELD_BY, token)
        holding = self.doc.Layers.FindByFullPath(logic.HOLDING_LAYER, -1)
        if holding >= 0 and self.doc.Layers[holding].IsVisible:
            self.doc.Layers[holding].IsVisible = False

    def release(self, object_id, layer_path):
        self._move(object_id, layer_path, None)
        self._mark(object_id, logic.HELD_BY, None)

    def mark_added(self, object_id, token):
        self._mark(object_id, logic.ADDED_BY, token)

    def clear_mark(self, object_id):
        self._mark(object_id, logic.ADDED_BY, None)

    def _mark(self, object_id, key, value):
        o = _find(self.doc, object_id)
        if o is not None:
            attrs = o.Attributes.Duplicate()
            attrs.SetUserString(key, value)
            self.doc.Objects.ModifyAttributes(o, attrs, True)

    def added_objects(self):
        every = Rhino.DocObjects.ObjectEnumeratorSettings()
        every.NormalObjects, every.LockedObjects, every.HiddenObjects = True, True, True
        return [(str(o.Id), o.Attributes.GetUserString(logic.ADDED_BY)) for o in self.doc.Objects.GetObjectList(every)
                if o.Attributes.GetUserString(logic.ADDED_BY)]

    def held_objects(self):
        index = self.doc.Layers.FindByFullPath(logic.HOLDING_LAYER, -1)
        if index < 0:
            return []
        return [(str(o.Id), o.Attributes.GetUserString(logic.HELD_FROM) or LAYERS["lot"],
                 o.Attributes.GetUserString(logic.HELD_BY))
                for o in self.doc.Objects.FindByLayer(self.doc.Layers[index]) or []]

    def layer_names(self):
        return [layer.FullPath for layer in self.doc.Layers if not layer.IsDeleted]

    def remove_layer_if_empty(self, path):
        index = self.doc.Layers.FindByFullPath(path, -1)
        if index < 0:
            return
        layer = self.doc.Layers[index]
        if not (self.doc.Objects.FindByLayer(layer) or []) and not layer.GetChildren():
            self.doc.Layers.Delete(index, True)

    def save_views(self):
        return [(v.ActiveViewportID, Rhino.DocObjects.ViewportInfo(v.ActiveViewport)) for v in self.doc.Views]

    def restore_views(self, saved):
        for view_id, info in saved or []:
            view = self.doc.Views.Find(view_id)
            if view is not None:
                view.ActiveViewport.SetViewProjection(info, True)
        self.doc.Views.Redraw()

    def add_lot(self, ring, name):
        return str(_add_lot(self.doc, {"lot": ring, "lot_name": name}))

    def add_spot(self, p):
        attrs = Rhino.DocObjects.ObjectAttributes()
        attrs.LayerIndex = _layer(self.doc, GRADE_LAYER)
        return str(self.doc.Objects.AddPoint(_model_point(self.doc, p[:2], p[2]), attrs))

    def ground_points(self):
        ids = []
        for path in (GRADE_LAYER, FINISHED_LAYER):
            index = self.doc.Layers.FindByFullPath(path, -1)
            if index >= 0:
                ids += [str(o.Id) for o in self.doc.Objects.FindByLayer(self.doc.Layers[index]) or []
                        if isinstance(o.Geometry, rg.Point)]
        return ids


def _recover(doc):
    """Objects a start box held when Rhino closed mid-session: back where they were (rhino_logic.recover_held)."""
    said = logic.recovery_message(*logic.recover_held(RhinoTable(doc)))   # never a box still open
    if said:
        say(said[0].upper() + said[1:] + ".")


def _draw_lot(doc):
    """Draw my lot…: click each corner (Enter closes it, Esc: nothing drawn). The new closed outline's id, or None."""
    corners = []
    while True:
        rc, point = Rhino.Input.RhinoGet.GetPoint(
            "Click the next corner of your lot (Enter closes it, at least 3)" if corners else
            "Click the first corner of your lot (the dashed guide is the City's outline)", True)
        if rc != Rhino.Commands.Result.Success:
            break
        corners.append(point)
    if len(corners) < 3 or rc == Rhino.Commands.Result.Cancel:
        return None
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = _layer(doc, LAYERS["lot"])
    attrs.Name = "Lot · drawn by you"
    return str(doc.Objects.AddCurve(rg.PolylineCurve(corners + [corners[0]]), attrs))


def _get_point(prompt):
    """A point clicked at the command line (Enter accepted as done): the box's picks, one place to stand in for."""
    return Rhino.Input.RhinoGet.GetPoint(prompt, True)


def _box_pick(doc, what, facts, saved_ui, session):
    """One pick the start box asked for, with the box hidden. Esc or Enter: nothing changes (Esc at any prompt,
    rhino_logic.pick_or_nothing). Every model edit goes through the box's session."""
    try:
        return logic.pick_or_nothing(lambda: _one_pick(doc, what, dict(facts), dict(saved_ui), session),
                                     facts, saved_ui)
    finally:
        _highlight(doc, facts)


def _one_pick(doc, what, facts, saved_ui, session):
    if what == "lookup":
        saved_ui = _lookup_start(facts, saved_ui)
    elif what == "lookup_done":
        facts, saved_ui = _lookup_done(doc, facts, saved_ui, session)
    else:                                      # the pick's outcome only; rhino_logic.pick_effect decides the rest
        facts, saved_ui = logic.pick_effect(what, _pick_outcome(doc, what, facts, saved_ui, session), facts, saved_ui)
    _highlight(doc, facts)
    return facts, saved_ui


def _pick_outcome(doc, what, facts, saved_ui, session):
    """What one pick gave, or None (Esc at any prompt, Enter with nothing clicked). Drawn objects go through the
    session. The street: {"picks": the lot lines clicked, "name": the clicked line's street}; rhino_logic.pick_effect
    sets the street lines from them (pick_street / street_lines_after_picks, through set_street_lines)."""
    if what == "street":
        lot = _find(doc, facts.get("lot_id") or "")
        if lot is None:
            return None
        corner = facts.get("corner_lot") is True     # a corner lot: every line on a street, Enter when done
        picks = []
        while True:
            rc, point = _get_point(logic.street_pick_prompt(corner, len(picks)))
            if rc == Rhino.Commands.Result.Cancel:
                return None                           # Esc: nothing changes, the lines clicked so far too
            if rc != Rhino.Commands.Result.Success:   # Enter: done
                break
            a, b = min(_segments(lot.Geometry), key=lambda s: rg.Line(s[0], s[1]).DistanceTo(point, True))
            picks.append([_feet_point(doc, a)[:2], _feet_point(doc, b)[:2]])
            if not corner:
                break
        if not picks:
            return None
        if corner:
            return {"picks": picks, "name": None}     # two streets: unnamed until named
        picked = picks[0]
        name = logic.street_name_after_pick(saved_ui.get("street_name"), facts.get("street_line"),
                                            picked, ids=facts.get("street_ids"))   # the line's own street?
        if name is None:                                       # else asked, never guessed
            ask = Rhino.Input.Custom.GetString()   # literal: a street's name has spaces ("Cayuga St")
            ask.SetCommandPrompt("Which street is this lot line on? (Enter leaves it unnamed)")
            ask.AcceptNothing(True)
            got = ask.GetLiteralString()
            if got == Rhino.Input.GetResult.Cancel:
                return None                           # Esc: nothing changes
            name = (ask.StringResult() or "").strip() or None if got == Rhino.Input.GetResult.String else None
        return {"picks": [picked], "name": name}
    if what == "lot":                            # Use my survey: the surveyed outline
        return _pick(doc, "Click your surveyed lot outline (a closed curve on the Site layer); Enter keeps it",
                     _lot_candidates(doc), "Lot", Rhino.DocObjects.ObjectType.Curve)
    if what == "draw_lot":                       # over the City's outline (a guide, never kept)
        drawn = _draw_lot(doc)
        session.add([drawn])
        return drawn
    if what == "terrain":
        go = Rhino.Input.Custom.GetObject()
        go.SetCommandPrompt("Click the terrain surface or mesh")
        go.GeometryFilter = Rhino.DocObjects.ObjectType.Surface | Rhino.DocObjects.ObjectType.PolysrfFilter | \
            Rhino.DocObjects.ObjectType.Mesh
        return str(go.Object(0).ObjectId) if go.Get() == Rhino.Input.GetResult.Object else None
    if what in ("spot", "regrade"):
        placed = _place_spots(doc, "Click a spot grade at a wall (Enter when done)" if what == "spot" else
                              "Click the finished ground you'll grade to, at each wall (Enter when done)",
                              GRADE_LAYER if what == "spot" else FINISHED_LAYER)
        session.add(placed)
        return placed
    return None


def confirm(doc, facts, options, mode="check"):
    """The start box, prefilled (spec A). Draw keeps the facts once the district is confirmed, with where each came
    from (saved beside them); a pick closes the box, picks in the model, and shows the box again with the result;
    closing it (or Esc) saves nothing (None)."""
    gate = STATE.setdefault("box_gate", logic.BoxGate())
    if not logic.allowed("open_box", _box_open()) or not gate.enter():   # one start box at a time
        say(logic.BOX_BUSY)
        return None
    result = None
    changed_before = STATE.get("dirty")
    try:
        ui.set_box_open(STATE.get("panel_parts"), True)
        result = _confirm(doc, facts, options, mode)
    finally:
        gate.leave()
        ui.set_box_open(STATE.get("panel_parts"), False)
        # Cancel put the model back: it is as changed (or not) as it was when the box opened, so current results
        # never grey out for the box's own rolled-back edits (the Check button: nothing re-checks them)
        # (the edit's own time kept: never moved earlier, which could let a check from before it count as covering
        # it; with Check after every edit on, the next idle past IDLE_SECONDS checks: review round 1, P1)
        STATE["dirty"] = logic.changed_after_box(changed_before, STATE.get("dirty"), result is not None)
    if result is not None:              # Draw (GordiumStart or Edit site…): the neighbourhood follows the lot
        logic.guard(sync_context, "draw the neighbourhood")(doc, result)
    return result


def _confirm(doc, facts, options, mode):
    o = overlay()
    _clear(o)                           # facts are being set: no earlier result (of any model) stays shown
    o.message = None
    _highlight(doc, facts)
    _recover(doc)                       # anything an unfinished earlier box set aside, back first
    saved_ui = _ui_state(doc)
    session = logic.BoxSession(RhinoTable(doc))     # this box's model edits, owned here, never copied
    try:
        return logic.run_box(session, lambda: _box_loop(doc, facts, options, mode, saved_ui, session))
    finally:
        _lookup_stop()
        o.confirm = None
        o.labels = []
        STATE.pop("lookup_guide", None)
        doc.Views.Redraw()


def _box_loop(doc, facts, options, mode, saved_ui, session):
    """The box until Draw (the facts) or Cancel (None); rhino_logic.run_box rolls the session back on any way out
    but Draw's, Esc and errors included."""
    if STATE.get("auto_ok"):          # scripted runs (tests, the demo): the architect ticks and draws
        STATE["zones"] = options.get("zones") or []
        for what in STATE.get("box_picks") or []:      # ...after the picks the architect would make, in order
            state = dict(_box_state(doc, facts, options, saved_ui, mode), **(STATE.get("box_overrides") or {}))
            facts, saved_ui = _apply_box(doc, facts, state, saved_ui)
            facts, saved_ui = _box_pick(doc, what, facts, saved_ui, session)
            started = time.time()
            while what == "lookup" and _lookup_poll() is None and time.time() - started < logic.LOOKUP_LIMIT_S + 5:
                time.sleep(0.2)
            if what == "lookup":
                facts, saved_ui = _box_pick(doc, "lookup_done", facts, saved_ui, session)
            if STATE.get("box_cancel_after_picks"):   # the in-Rhino test of Cancel
                return None
        state = _box_state(doc, facts, options, saved_ui, mode)
        if STATE.get("on_confirm"):   # ...after recording what the box shows, before the tick
            STATE["on_confirm"](doc, facts, _describe(facts, options["uses"]), state)
        state = dict(state, district_confirmed=True, **(STATE.get("box_overrides") or {}))
        return _drawn(doc, facts, state, saved_ui, session)
    ticked = {}                       # this box session's ticks and changed sources, kept across picks
    while True:
        state = dict(_box_state(doc, facts, options, saved_ui, mode), **ticked)
        state["_on_shown"] = STATE.get("on_box_shown")     # the dialog capture in the in-Rhino test
        STATE["zones"] = options.get("zones") or []
        what = ui.start_box(state, options, mode)
        if what is None:
            return None                      # rolled back by run_box: the model as it was
        if what == "draw":
            return _drawn(doc, facts, state, saved_ui, session)
        ticked = {k: state[k] for k in ("district_confirmed", "zone_source", "address_source", "use_source",
                                        "corner_source", "checked") if k in state}   # (saved only at Draw)
        if what in ("pick:lookup", "pick:lookup_done"):   # the lookup's answer replaces them (and the district
            ticked = {}                                   # must be confirmed again)
        facts, saved_ui = _apply_box(doc, facts, state, saved_ui)
        facts, saved_ui = _box_pick(doc, what.split(":", 1)[1], facts, saved_ui, session)
        # (nothing saved until Draw: Cancel leaves the facts, the box's choices and the model as they were)


# ---- the address lookup: design_checker.lookup_box in its own short-lived process ----------------------------

def _lookup_start(facts, saved_ui):
    """Look up: start the lookup for the address typed (its own process, never Rhino's Python); the box opens again
    saying "Looking up…" and closes itself when the answer is in (_lookup_poll)."""
    _lookup_stop()
    address = (facts.get("address") or "").strip()
    if not address:                    # nothing else changes: the doubts about what is drawn stay
        return dict(saved_ui, _lookup={"says": "Type the address first, then Look up."})
    out = os.path.join(tempfile.gettempdir(), "gordium_lookup_%d.json" % int(time.time() * 1000))
    packages = os.path.join(REPO, "packages")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"                             # UTF-8 everywhere, Windows included
    env["PYTHONPATH"] = os.pathsep.join(STATE.get("extra_paths", []) + [
        os.path.join(packages, n) for n in sorted(os.listdir(packages)) if os.path.isdir(os.path.join(packages, n))])
    args = [_python(), "-m", "design_checker.lookup_box", address]
    if STATE.get("lookup_fixture"):                      # the in-Rhino test: recorded answers, no live call
        args += ["--fixture", STATE["lookup_fixture"]]
    sink = open(out, "w", encoding="utf-8")             # to a file: a long answer never fills a pipe
    err = open(os.path.join(tempfile.gettempdir(), "gordium_worker.log"), "a", encoding="utf-8")
    STATE["lookup"] = {"proc": ui.spawn(args, cwd=REPO, env=env, stdout=sink, stderr=err),   # no console window
                       "out": out, "sink": sink, "err": err, "started": time.time(), "query": address}
    return dict(saved_ui, _lookup={"looking": address})


def _lookup_poll():
    """None while the lookup runs; then its answer (also kept for _lookup_done). Stopped after LOOKUP_LIMIT_S."""
    run = STATE.get("lookup")
    if run is None:
        return {"status": "error", "query": None}
    if "answer" in run:
        return run["answer"]
    p = run["proc"]
    if p.poll() is None:
        if time.time() - run["started"] < logic.LOOKUP_LIMIT_S:
            return None
        run["answer"] = {"status": "timeout", "query": run["query"]}      # the answer first, then the cleanup
        _lookup_kill(run)
        _lookup_files_done(run)
        return run["answer"]
    run["sink"].close()
    try:
        with open(run["out"], encoding="utf-8") as f:
            run["answer"] = json.loads(f.read().strip().splitlines()[-1])
    except Exception as e:
        run["answer"] = {"status": "error", "query": run["query"], "detail": str(e)[:200]}
    _lookup_files_done(run)
    return run["answer"]


def _lookup_files_done(run):
    """The lookup's output file and log handle: closed, and the output file removed. Never raises: a file Windows
    still holds is left in the temp folder."""
    for handle in (run.get("sink"), run.get("err")):
        if handle is not None and not handle.closed:
            handle.close()
    try:
        if os.path.exists(run.get("out") or ""):
            os.remove(run["out"])
    except OSError:
        pass


def _lookup_stop():
    run = STATE.pop("lookup", None)
    if run is None:
        return
    _lookup_kill(run)
    _lookup_files_done(run)


def _lookup_kill(run):
    """Stop the lookup and wait for it to be gone (on Windows its output file stays open until then)."""
    if run["proc"].poll() is None:
        run["proc"].kill()
        try:
            run["proc"].wait(timeout=5)
        except Exception:
            pass


def _lookup_done(doc, facts, saved_ui, session):
    """The lookup's answer into the box and the model (rhino_logic.apply_lookup, tested in CI): only what each
    source allows is drawn; the lot it may replace, and that lot's spot grades, are held by the session (Cancel
    brings them back); the architect's own lot is never touched. The City's outline is a guide on screen only."""
    answer = _lookup_poll() or {"status": "error"}
    _lookup_stop()
    facts, saved_ui, guide = logic.apply_lookup(RhinoTable(doc), session, answer, facts, saved_ui,
                                                STATE.get("zones") or [])
    STATE.pop("lookup_guide", None)
    if guide:
        pts = [_model_point(doc, p) for p in guide]
        STATE["lookup_guide"] = pts + [pts[0]]
    if answer.get("status") == "found":
        logic.guard(frame_site, "frame the looked-up lot")(doc, facts)
    return facts, saved_ui


def _drawn(doc, facts, state, saved_ui, session=None):
    """Draw: the facts for the checker, and every fact's source and confirmation saved in the .3dm; what the box
    replaced goes for good."""
    def save():
        out, ui_state = _apply_box(doc, facts, state, saved_ui)
        _save_ui_state(doc, ui_state)
        sources = fact_sources(doc)        # what the box doesn't set (the ground marking) is kept
        sources.update(logic.fact_sources(state, logic.city_day(), confirmed=True))
        doc.Strings.SetString(SECTION, SOURCES_ENTRY, json.dumps(sources))
        return out

    if session is None:
        return save()
    return logic.draw_then_commit(session, save)     # the commit last: a failure before it is rolled back


def hide_massing(hidden):
    """Hide starting house: the Gordium::Massing layer off (still checked: only its drawing is turned off)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    index = doc.Layers.FindByFullPath(logic.MASSING, -1)
    if index < 0:
        say("There is no starting house in this file to hide (run GordiumStart on a new file to draw one).")
        return
    doc.Layers[index].IsVisible = not hidden
    doc.Views.Redraw()


Cancelled = logic.Cancelled          # Esc at a prompt: the whole edit is cancelled and nothing is saved


def _go_on(rc):
    if rc == Rhino.Commands.Result.Cancel or rc == Rhino.Input.GetResult.Cancel:
        raise Cancelled()


def _yes_no(prompt, current):
    rc = Rhino.Input.RhinoGet.GetBool(prompt, True, "No", "Yes", bool(current))
    _go_on(rc[0])
    return bool(rc[1]) if rc[0] == Rhino.Commands.Result.Success else current


def _count(prompt):
    """A whole number the architect types, or None when the prompt is skipped (never a default)."""
    gi = Rhino.Input.Custom.GetInteger()
    gi.SetCommandPrompt(prompt + " (Enter to skip)")
    gi.AcceptNothing(True)
    gi.SetLowerLimit(0, False)
    got = gi.Get()
    _go_on(got)
    return gi.Number() if got == Rhino.Input.GetResult.Number else None


def _ask_yes_no_or_skip(prompt):
    """Yes (True) or No (False), or None when the prompt is skipped (never a default; _yes_no keeps a current
    answer instead)."""
    go = Rhino.Input.Custom.GetOption()
    go.SetCommandPrompt(prompt + " (Enter to skip)")
    yes, no = go.AddOption("Yes"), go.AddOption("No")
    go.AcceptNothing(True)
    got = go.Get()
    _go_on(got)
    return (go.OptionIndex() == yes) if got == Rhino.Input.GetResult.Option else None


def change_facts(doc, facts, options):
    """Every lot fact, one prompt each (Enter keeps what is there; Esc cancels the whole edit: None, nothing
    saved). Model points become feet."""
    try:
        return _change_facts(doc, dict(facts), options)
    except Cancelled:
        return None


def _new_get_object():
    return Rhino.Input.Custom.GetObject()


def _pick(doc, prompt, candidates, kind, geometry=None):
    """The id of a candidate, clicked (only they can be) or chosen by name from the options (Lot1, Lot2…, for one
    that is locked or hidden and so can't be clicked), or None on Enter (keep what is there). Esc cancels the
    edit. Nothing already selected is taken (it could be anything), and the pick is left unselected, so one prompt
    never answers the next by itself."""
    ids = {str(o.Id) for o in candidates}
    doc.Objects.UnselectAll()
    go = _new_get_object()
    go.SetCommandPrompt(prompt)
    go.AcceptNothing(True)
    go.EnablePreSelect(False, True)
    by_option, labels = {}, []
    for name, o in zip(logic.option_names(kind, len(candidates)), candidates):
        by_option[go.AddOption(name)] = str(o.Id)
        labels.append((o.Geometry.GetBoundingBox(True).Center, name))
    overlay().labels = labels           # the names on screen, so a name always points at its object
    doc.Views.Redraw()
    if geometry is not None:
        go.GeometryFilter = geometry
    go.SetCustomGeometryFilter(Rhino.Input.Custom.GetObjectGeometryFilter(
        lambda obj, geo, part: obj is not None and logic.accepts_pick(str(obj.Id), ids)))
    try:
        got = go.Get()
        _go_on(got)
    finally:
        overlay().labels = []
        doc.Objects.UnselectAll()
        doc.Views.Redraw()
    picked = (str(go.Object(0).ObjectId) if got == Rhino.Input.GetResult.Object else
              by_option.get(go.OptionIndex()) if got == Rhino.Input.GetResult.Option else None)
    return picked if picked is not None and logic.accepts_pick(picked, ids) else None


def _ask_zone(options, current):
    return Rhino.Input.RhinoGet.GetString("Zone (" + ", ".join(options["zones"]) + ")", True, current or "")


def _change_facts(doc, facts, options):
    zone = _ask_zone(options, facts.get("zone"))
    _go_on(zone[0])
    if zone[0] == Rhino.Commands.Result.Success and zone[1] in options["zones"]:
        facts["zone"] = zone[1]
    names = list(options["uses"].items())
    use = Rhino.UI.Dialogs.ShowListBox("Gordium", "Use of the lot", [n for _, n in names],
                                       options["uses"].get(facts.get("use"), ""))
    if use is None:
        raise Cancelled()
    if use:
        facts["use"] = next(k for k, n in names if n == use)
    lots, buildings, _ = _sorted_objects(doc)
    if len(lots) > 1:
        picked = _pick(doc, "Click the lot outline (a closed curve on the Site layer), or choose one; Enter keeps it",
                       lots, "Lot", Rhino.DocObjects.ObjectType.Curve)
        facts = logic.after_lot_pick(facts, picked)
        _highlight(doc, facts)
    if len(buildings) > 1:
        picked = _pick(doc, "Click the main building (a solid on the Building layer), or choose one; Enter keeps it",
                       buildings, "Building")
        if picked:
            facts["main_building"] = picked
        _highlight(doc, facts)
    facts, _ = logic.corner_answered(facts, {}, _yes_no("Corner lot (two streets meet at it)?",
                                                        facts.get("corner_lot")))   # the box's own helper
    _highlight(doc, facts)
    lot = _find(doc, facts.get("lot_id") or "")
    if lot is not None:
        picked = []
        while True:                      # every lot line on a street (both streets on a corner lot)
            keeps = not picked and logic.street_enter_keeps(facts)
            prompt = "Click a lot line on the street" + (" (Enter when done)" if picked else
                                                         " (Enter keeps the blue one)" if keeps else "")
            rc, point = Rhino.Input.RhinoGet.GetPoint(prompt, True)      # Enter: done, keep, or asked again
            _go_on(rc)
            if rc != Rhino.Commands.Result.Success:
                if picked or keeps:
                    break
                Rhino.RhinoApp.WriteLine("Gordium: this lot has no street line yet; click one (Esc cancels)")
                continue
            a, b = min(_segments(lot.Geometry), key=lambda s: rg.Line(s[0], s[1]).DistanceTo(point, True))
            line = [_feet_point(doc, a)[:2], _feet_point(doc, b)[:2]]
            if line not in picked:
                picked.append(line)
            if not facts.get("corner_lot"):
                break
        if picked:
            logic.set_street_lines(facts, picked)          # unnamed: the lines picked here, never the old names
        _highlight(doc, facts)
    facts["ground_is_flat"] = _yes_no("Is the ground flat?", facts.get("ground_is_flat"))
    ground = Rhino.Input.RhinoGet.GetNumber("Ground level (z, in model units)", True,
                                            _model_length(doc, facts.get("grade_elevation") or 0.0))
    _go_on(ground[0])
    if ground[0] == Rhino.Commands.Result.Success:
        facts["grade_elevation"] = _feet_length(doc, ground[1])
    facts["lot_surveyed"] = _yes_no("Is the lot outline from a survey?", facts.get("lot_surveyed"))
    return facts


def edit_facts():
    """Edit site… (and GordiumFacts): the start box, prefilled with what is saved. Bedrooms and parking spaces
    are entered from their own rows ("Enter…")."""
    doc = Rhino.RhinoDoc.ActiveDoc
    options = ask({"cmd": "options", "jurisdiction": JURISDICTION})
    try:
        saved = current_facts(doc)
    except ValueError:                  # unreadable: start again from the suggestions
        saved = {}
    try:
        facts = confirm(doc, logic.with_suggestions(saved, suggested_facts(doc, options["zones"])), options, "check")
    finally:                            # the editing outline and names never stay on screen
        o = overlay()
        o.confirm, o.labels = None, []
        doc.Views.Redraw()
    if facts is not None:
        save_facts(doc, facts)
    run_check(doc, report=False)


def report_path(doc):
    folder = os.path.dirname(doc.Path) if doc.Path else os.path.expanduser("~/Documents")
    name = os.path.splitext(os.path.basename(doc.Path))[0] if doc.Path else "untitled"
    return os.path.join(folder, name + "_gordium_report.xlsx")


def _clear(o):
    """Nothing from an earlier check is left on screen."""
    o.red, o.red_ids, o.dims, o.envelope, o.box = [], set(), [], None, rg.BoundingBox.Empty
    o.encroach, o.yard_dims, o.edge_labels, o.lot_outline, o.yards_zone, o.grade_points = [], [], [], None, None, []
    o.yard_required, o.height_dim, o.yard_options, o.yard_tags, o.footprint, o.placed = [], None, {}, {}, [], {}
    o.plan_lines = []
    o.confirm, o.labels = None, []
    o.envelope_lines, o.height_limit, o.north, o.unmeasured = None, None, None, []
    o.doc = None


def check_facts(doc, facts):
    """The facts as the checker gets them: the spot grades read from the model, or the terrain sampled at the
    walls now, so the grade follows the building (C4)."""
    out = dict(facts)
    if facts.get("grade_from") in ("spot", "finished_spots"):    # which points: the facts saved at Draw say
        points = _grade_points(doc, facts["grade_from"] == "finished_spots")
    elif facts.get("grade_from") == "terrain":
        points = _terrain_points(doc, _ui_state(doc).get("terrain_id"))
    else:
        points = []
    if points:
        out["grade_points"] = points
    else:
        out.pop("grade_points", None)
    return out


def _plan_edges(geometry):
    """A building's edges as straight lines (a curved edge by its chord), for labels to stay off."""
    brep = geometry if isinstance(geometry, rg.Brep) else (
        geometry.ToBrep() if isinstance(geometry, rg.Extrusion) else None)
    if brep is not None:
        return [rg.Line(e.PointAtStart, e.PointAtEnd) for e in brep.Edges]
    box = geometry.GetBoundingBox(True)
    c = box.GetCorners()
    return [rg.Line(c[i], c[(i + 1) % 4]) for i in range(4)]


def _draw_plan(doc, o, result, facts):
    """What the viewport shows for a result (F): the property line, each lot edge's length, the required yards
    shaded, the envelope (dashed, see-through), each yard as measured with its status, and red only on the part
    of the building inside a yard or above the height limit (the massing stays neutral)."""
    plan = result.get("plan") or {}
    lot = _find(doc, facts.get("lot_id") or "")
    if lot is not None:
        ok, poly = lot.Geometry.TryGetPolyline()
        o.lot_outline = list(poly) if ok else None
    # the lengths alone: the header and the status box say the tax map's ±2'-0" once (the review: "(approx.)" on
    # every edge was noise)
    o.edge_labels = [(_model_point(doc, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)), e["length"],
                      rg.Line(_model_point(doc, a), _model_point(doc, b)))         # the edge: labelled beside it
                     for e in plan.get("edges") or [] for a, b in [e["points"]]]
    o.yard_dims = [(rg.Line(_model_point(doc, y["points"][0], 0.1), _model_point(doc, y["points"][1], 0.1)),
                    y["label"], y["status"]) for y in plan.get("yards") or [] if y.get("points")]
    # each yard's required line, faint, square across its dimension; the height's vertical dimension (elevations)
    o.yard_required = [(rg.Line(_model_point(doc, r[0], 0.1), _model_point(doc, r[1], 0.1)), y["status"])
                       for y in plan.get("yards") or [] if y.get("points") for r in y.get("required_lines") or []]
    # every position check.plan offers for each yard's dimension, with its required lines; the "min" tags; the
    # buildings' outline (a label never sits inside it)
    o.yard_options = {k: [(rg.Line(_model_point(doc, c["points"][0], 0.1), _model_point(doc, c["points"][1], 0.1)),
                           [rg.Line(_model_point(doc, r[0], 0.1), _model_point(doc, r[1], 0.1))
                            for r in c.get("required_lines") or []])
                          for c in y.get("candidates") or []]
                      for k, y in enumerate(y for y in plan.get("yards") or [] if y.get("points"))}
    o.yard_tags = {k: y.get("required_tags") or [] for k, y in enumerate(y for y in plan.get("yards") or []
                                                                           if y.get("points"))}
    o.footprint = [[_model_point(doc, p, 0.1) for p in ring] for ring in plan.get("footprint") or []]
    h = plan.get("height")
    o.height_dim = (rg.Line(_model_point(doc, h["at"], h["base"]), _model_point(doc, h["at"], h["top"])), h["label"],
                    h["status"], _model_point(doc, h["at"], h["limit"]) if h.get("limit") is not None else None) \
        if h else None
    # what is drawn, each piece with its rule and building: the one list draw_scene draws and the in-Rhino checks
    # read (logic.coloured_info)
    blocks = plan.get("encroach") or []
    made = _solids_for(doc, blocks)                  # each building made once, whatever its number of blocks
    o.encroach = [(_proud(doc, piece), status, logic.coloured_info(e))   # coloured from the rule's result only
                  for e, status in ((e, e.get("status") or "does_not_comply") for e in blocks)
                  if logic.highlight(status) for piece in _offending(doc, e, made)]
    # every line a label must stay off (model space): the yard dimensions, the lot's edges, the house's edges
    pts = o.lot_outline or []
    # (the faint required lines too: a yard's words never cover one, review round 1, F3)
    o.plan_lines = [line for line, _, _ in o.yard_dims] + [line for line, _ in o.yard_required] + \
        [rg.Line(p, q) for p, q in zip(pts, pts[1:])] + \
        [line for b in _buildings(doc) for line in _plan_edges(b.Geometry)]
    o.yards_zone = None
    if lot is not None and plan.get("buildable"):
        inner = rg.PolylineCurve([_model_point(doc, p) for p in plan["buildable"] + plan["buildable"][:1]])
        zone = rg.Brep.CreatePlanarBreps([lot.Geometry, inner], doc.ModelAbsoluteTolerance)
        o.yards_zone = zone[0] if zone else None
    o.grade_points = [_model_point(doc, p[:2], p[2]) for p in facts.get("grade_points") or []]


def run_check(doc, report=True):
    """Measure and check the model now; draw the result; update the panel. If the check can't run, the old
    result is cleared from the view and the panel says why, with Retry (H2): never left showing. While a start box
    is open it does nothing at all (its overlay, the panel and the "before" statuses stay): the box's own edits
    would otherwise be checked mid-box; live mode checks once the box closes."""
    if STATE.get("running") or not logic.allowed("check", _box_open()):
        return None
    o = overlay()
    facts = {}
    try:
        STATE["running"] = True
        if not STATE.get("headless"):            # the message line tells of this check's action only, whatever happens
            ui.say(STATE.get("panel_parts"), "")
        facts = current_facts(doc)
        if logic.missing(facts):
            raise ValueError("lot facts missing: " + ", ".join(logic.missing(facts)) + " (run GordiumCheck)")
        path = os.path.join(tempfile.gettempdir(), "gordium_live_" + str(doc.RuntimeSerialNumber) + ".3dm")
        problems = export(doc, path)
        sent = check_facts(doc, facts)
        extras = _extras(doc, facts)
        extras["before"] = STATE.setdefault("statuses_by_doc", {}).get(doc.RuntimeSerialNumber)
        had_report = bool(report) and os.path.exists(report_path(doc))    # before this check tries to write one
        result = ask({"cmd": "check", "model": path, "facts": sent, "building_problems": problems,
                      "report": report_path(doc) if report else None, "extras": extras})
        _clear(o)
        o.doc = doc.RuntimeSerialNumber
        view = result["view"]
        head = view["header"]
        second = [head["draft"].split(" · ")[0]] + [t for t in (head["lot"], head["grade"])
                                                     if "approximate" in t or "not set" in t or "existing" in t]
        o.message = (view["state"], view["summary"], [" · ".join(second)])
        env = _envelope_brep(doc, _drawn_envelope(doc, facts, result.get("envelope"))) \
            if STATE.get("envelope_on", True) else None
        o.envelope = env
        o.box = env.GetBoundingBox(True) if env else rg.BoundingBox.Empty
        drawn = _drawn_envelope(doc, facts, result.get("envelope")) if env is not None else None
        o.envelope_lines = _envelope_lines(doc, drawn) if drawn else None
        o.height_limit = (o.envelope_lines[1], logic.height_limit_text((result.get("envelope") or {}).get("top"),
                                                                       _ft_text(drawn["top"] - drawn["base"]))) \
            if o.envelope_lines else None
        o.north = _north(doc, facts)
        o.unmeasured = _unmeasured_outlines(doc, extras.get("not_included"))
        _draw_plan(doc, o, result, sent)
        STATE["statuses_by_doc"][doc.RuntimeSerialNumber] = result["statuses"]
        STATE["last"] = {"summary": result["summary"], "view_summary": view["summary"], "state": view["state"],
                         "rows": [{k: r.get(k) for k in ("Requirement", "Table limit", "Proposed", "Units",
                                                          "Error", "Rule id", "Why", "Provisional")}
                                  for r in result["rows"]],
                         "items": [{k: i.get(k) for k in ("id", "name", "status", "proposed", "required", "margin",
                                                          "delta", "approx", "colour", "note", "points", "reason",
                                                          "group", "needs", "hint", "refused")}
                                   for i in view["items"]],
                         "header": head, "interior": [r["Rule id"] for r in result.get("interior", [])],
                         "encroach": len(o.encroach), "plan_encroach": len((result.get("plan") or {}).get("encroach") or []),
                         "envelope": result.get("envelope"), "at": time.time()}
        STATE.setdefault("checked_at", {})[doc.RuntimeSerialNumber] = time.time()     # a real check, of this document
        if not STATE.get("live"):   # results on screen: edits are noticed from now on, whichever command drew them
            live(True)              # (Edit site…, GordiumFacts, Check: review round 3 of the Check button)
        if result.get("notice"):
            STATE.setdefault("toasts", []).append([result["notice"]])
            if not STATE.get("headless"):
                _toast([result["notice"]])
        shown = logic.labels_on(_ui_state(doc))       # this document's Show on-screen labels
        STATE.setdefault("labels_by_doc", {})[doc.RuntimeSerialNumber] = shown
        if not STATE.get("headless"):
            ui.show(panel(), view)
            ui.set_labels_tick(STATE.get("panel_parts"), shown)
            ui.set_auto_tick(STATE.get("panel_parts"), _auto(doc))
            ui.set_context_tick(STATE.get("panel_parts"), _context_on(doc))
        if report and result.get("report_error"):   # every caller that asked for a report hears it wasn't written
            path = report_path(doc)
            say(logic.report_message(path, False, result["report_error"], stale=had_report))
        return result
    except Exception as e:
        _clear(o)
        o.doc = doc.RuntimeSerialNumber
        o.message = ("needs_review", "⚠ Check could not run", [str(e)[:120]])
        STATE["last"] = {"error": str(e), "at": time.time()}
        if not STATE.get("headless"):
            ui.show(panel(), None, error=str(e)[:300])
            ui.set_auto_tick(STATE.get("panel_parts"), _auto(doc))
        return None
    finally:
        STATE["running"] = False
        doc.Views.Redraw()


# ---- "now fails": a short note, only when a rule starts failing --------------------------------------------

def _toast(lines):
    """The notice, drawn bottom left in the active view (no window, no button); it clears at the next command or
    after a few seconds."""
    o = overlay()
    o.toast = (list(lines), time.time() + TOAST_SECONDS)
    if STATE.get("command_hook") is None:              # the next command clears it
        hook = _handler(System.EventHandler[Rhino.Commands.CommandEventArgs], lambda s, e: _clear_toast(), "clear the notice")
        _on(Rhino.Commands.Command, "BeginCommand", hook)
        STATE["command_hook"] = hook
    timer = STATE.get("toast_timer")
    if timer is None:
        timer = ef.UITimer()
        timer.Interval = 0.5
        timer.Elapsed += logic.guard(logic.current_only(lambda s, e: _toast_tick(), _is_current), "time the notice")
        STATE["toast_timer"] = timer
        LEFTOVERS["toast_timer"] = timer.Stop
    timer.Start()
    _redraw()


def _toast_tick():
    o = STATE.get("overlay")
    if getattr(o, "toast", None) and time.time() >= o.toast[1]:
        _clear_toast()


def _clear_toast():
    """Clear the notice, if any. Never makes the drawing (overlay() would also turn the document hooks back on, so
    off() left them attached: found 2026-10-21 counting Rhino's event handlers)."""
    o = STATE.get("overlay")
    if getattr(o, "toast", None):
        o.toast = None
        if STATE.get("toast_timer"):
            STATE["toast_timer"].Stop()
        _redraw()


# ---- live mode -------------------------------------------------------------------------------------------

def _changed(sender, e):
    STATE["dirty"] = time.time()


def _new_document(sender, e):
    """Another document (new, opened, or switched to): nothing from the last one stays drawn or listed."""
    o = STATE.get("overlay")
    if o is not None:
        _clear(o)
        o.message = None
    STATE["last"] = {"error": "no check yet for this document", "at": time.time()}
    p = STATE.get("panel_parts")
    if p is not None and p["form"].Visible:
        p["view"] = None
        ui.set_auto_tick(p, _auto(Rhino.RhinoDoc.ActiveDoc))      # this document's own setting
        ui.show(p, None, error="no check yet for this document (press Check)")
    STATE["dirty"] = None               # the last document's edits are not this one's (it is checked below)
    STATE["check_front"] = True         # check the document now in front once, if it has lot facts (not an edit:
    #                                     whatever Check after every edit says: review round 1 of the Check button)


def _opened(sender, e):
    """A file opened: another document; or merged into this one (Import, Insert, a reference): an edit."""
    if e.Merge or e.Reference:
        STATE["dirty"] = time.time()
    else:
        _new_document(sender, e)


def _idle(sender, e):
    t = STATE.get("dirty")
    front = Rhino.RhinoDoc.ActiveDoc
    last_at = logic.last_check_at(STATE.get("checked_at"), front.RuntimeSerialNumber if front is not None else None)
    if t and last_at is not None and last_at >= t and not _box_open():   # a check since the edit covered it
        STATE["dirty"] = t = None
    p = STATE.get("panel_parts")
    if t and time.time() - t >= ui.STALE_SECONDS and STATE.get("stale_shown") != t:
        # out of date: no marks until the re-check, or until Check (H1, F7): the viewport greys whether or not the
        # panel is open (it works "out of date" out as it draws, so it is redrawn now; review round 2, P0)
        STATE["stale_shown"] = t
        if p is not None and p["form"].Visible:
            ui.set_auto_tick(p, _auto(front))
            p["checked_before"] = last_at is not None
            ui.show(p, None, checking=True)
        _redraw()
    if logic.should_check_front(STATE.get("check_front"), STATE.get("running"), _box_open()):
        STATE["check_front"] = False
        if front is not None and front.Strings.GetValue(SECTION, ENTRY):   # it has lot facts: checked once
            run_check(front, report=False)
    elif logic.should_recheck(t, time.time(), STATE.get("running"), _box_open(), IDLE_SECONDS, last_at,
                            auto=_auto(front)):
        STATE["dirty"] = None
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is not None and doc.Strings.GetValue(SECTION, ENTRY):    # checked before: run_check says why
            run_check(doc, report=False)


def documents(on):
    """Hooks for another document coming to the front (new, opened, switched to); on while Gordium is."""
    hooks = STATE.pop("doc_hooks", None)
    if hooks:
        new_doc, opened, active = hooks
        _off(Rhino.RhinoDoc, "NewDocument", new_doc)
        _off(Rhino.RhinoDoc, "EndOpenDocument", opened)
        _off(Rhino.RhinoDoc, "ActiveDocumentChanged", active)
    if on:
        new_doc = _handler(System.EventHandler[Rhino.DocumentEventArgs], _new_document, "follow a new document")
        opened = _handler(System.EventHandler[Rhino.DocumentOpenEventArgs], _opened, "follow an opened document")
        active = _handler(System.EventHandler[Rhino.DocumentEventArgs], _new_document, "follow the active document")
        _on(Rhino.RhinoDoc, "NewDocument", new_doc)
        _on(Rhino.RhinoDoc, "EndOpenDocument", opened)
        _on(Rhino.RhinoDoc, "ActiveDocumentChanged", active)
        STATE["doc_hooks"] = (new_doc, opened, active)


def _unhook():
    hooks = STATE.pop("hooks", None)
    if hooks and len(hooks) == 3:            # set by an earlier version of this script, before a reload
        hooks = (hooks[0], hooks[1], None, None, None, hooks[2])
    if hooks and len(hooks) == 6:            # also an earlier version: the document hooks were here
        objects, replaced, attributes, new_doc, opened, idle = hooks
        if attributes is not None:
            _off(Rhino.RhinoDoc, "NewDocument", new_doc)
            _off(Rhino.RhinoDoc, "EndOpenDocument", opened)
        hooks = (objects, replaced, attributes, idle)
    if hooks:
        objects, replaced, attributes, idle = hooks
        if attributes is not None:
            _off(Rhino.RhinoDoc, "ModifyObjectAttributes", attributes)
        for name in ("AddRhinoObject", "DeleteRhinoObject", "UndeleteRhinoObject"):
            _off(Rhino.RhinoDoc, name, objects)
        _off(Rhino.RhinoDoc, "ReplaceRhinoObject", replaced)
        _off(Rhino.RhinoApp, "Idle", idle)


def live(on):
    """Notice each edit (objects added, deleted, moved or changed, a layer change or hiding one): the results grey
    out until a check; the idle handler checks by itself only with Check after every edit ticked."""
    _unhook()
    STATE["live"] = on
    if not on:
        return
    objects = _handler(System.EventHandler[Rhino.DocObjects.RhinoObjectEventArgs], _changed, "notice an edit")
    replaced = _handler(System.EventHandler[Rhino.DocObjects.RhinoReplaceObjectEventArgs], _changed, "notice an edit")
    attributes = _handler(System.EventHandler[Rhino.DocObjects.RhinoModifyObjectAttributesEventArgs], _changed,
                          "notice an edit")
    idle = _handler(System.EventHandler, _idle, "re-check after an edit")
    for name in ("AddRhinoObject", "DeleteRhinoObject", "UndeleteRhinoObject"):
        _on(Rhino.RhinoDoc, name, objects)
    _on(Rhino.RhinoDoc, "ReplaceRhinoObject", replaced)
    _on(Rhino.RhinoDoc, "ModifyObjectAttributes", attributes)
    _on(Rhino.RhinoApp, "Idle", idle)
    STATE["hooks"] = (objects, replaced, attributes, idle)


def toggle_live():
    """GordiumLive: Check after every edit on or off for this file (the panel's tick). Edits are always noticed (the
    results grey out until checked): turning the edit hooks off would leave old marks showing as current after an
    edit (review round 2 of the Check button)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if not STATE.get("live"):
        live(True)
    set_auto_check(not _auto(doc))


def toggle_envelope():
    STATE["envelope_on"] = not STATE.get("envelope_on", True)
    run_check(Rhino.RhinoDoc.ActiveDoc, report=False)


def say(text):
    """What a button did, or why it couldn't: on the command line and in the panel's message line. Never silent
    (an action that can't do its job says so). Kept in STATE["said"] for the in-Rhino tests."""
    Rhino.RhinoApp.WriteLine("Gordium: " + text)
    STATE.setdefault("said", []).append(text)
    if not STATE.get("headless"):
        ui.say(STATE.get("panel_parts"), text)


def open_report():
    """Zoning report…: the report for the model as it is now (a fresh check that writes it), then opened with the
    Mac's default app for .xlsx (Excel or Numbers). The panel says where it was saved, or why it wasn't."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        say(logic.NO_DOCUMENT)
        return
    if STATE.get("running"):
        say(logic.BUSY)
        return
    path = report_path(doc)
    before = os.path.getmtime(path) if os.path.exists(path) else None
    result = run_check(doc, report=True)          # the check's result stays, even if the file can't be written
    written = result is not None and not result.get("report_error") and os.path.exists(path) and \
        os.path.getmtime(path) != before
    if not written:
        if not (result or {}).get("report_error"):    # a report error: run_check has said it
            say(logic.report_message(path, False, (STATE.get("last") or {}).get("error") or
                                     ("the report file wasn't written to " + os.path.dirname(path))))
        return
    opened, why = ui.open_target(path)            # os.startfile on Windows, `open` on macOS
    say(logic.report_message(path, True, opened=opened, open_error=why))


def off():
    _unhook()
    documents(False)
    hook = STATE.pop("command_hook", None)
    if hook is not None:
        _off(Rhino.Commands.Command, "BeginCommand", hook)
    _clear_toast()
    STATE["live"] = False
    o = STATE.get("overlay")
    if o is not None:
        _clear(o)
        o.message = None
        o.Enabled = False
    p = STATE.pop("panel_parts", None)
    if p is not None:
        p["form"].Close()
    _redraw()


# ---- GordiumCheck ----------------------------------------------------------------------------------------

def gordium_check():
    """Confirm the lot facts whenever any required one is missing (keeping what is saved), then check."""
    doc = Rhino.RhinoDoc.ActiveDoc
    _recover(doc)                       # anything an unfinished start box set aside (Rhino closed), back first
    if not _buildings(doc) and not _lot_candidates(doc):    # an empty model: a new project starts here
        return gordium_start()
    options = ask({"cmd": "options", "jurisdiction": JURISDICTION})
    try:
        facts = current_facts(doc)
    except ValueError:                  # unreadable: confirm again from the suggestions
        facts = {}
    if logic.missing(facts):
        facts = confirm(doc, logic.with_suggestions(facts, suggested_facts(doc, options["zones"])), options)
        if facts is None:               # closed or Esc: nothing saved, nothing checked
            Rhino.RhinoApp.WriteLine("Gordium: the lot facts weren't confirmed; nothing was saved")
            return None
        save_facts(doc, facts)
    result = run_check(doc, report=True)
    live(True)                                      # edits noticed (checked at Check, or each edit if ticked)
    if result is not None:
        Rhino.RhinoApp.WriteLine("Gordium: " + result["view"]["summary"])     # the panel's own words (D3)
    if not STATE.get("headless"):       # the command brings the panel forward (a live re-check never does)
        logic.guard(lambda: panel()["form"].BringToFront(), "bring the panel forward")()
    return result


# ---- GordiumStart ----------------------------------------------------------------------------------------

def _layer(doc, path):
    """The layer at a full path ("Gordium::Massing"), made (with its parents) if it isn't there."""
    index = doc.Layers.FindByFullPath(path, -1)
    if index >= 0:
        return index
    parent = None
    for depth, name in enumerate(path.split("::")):
        full = "::".join(path.split("::")[:depth + 1])
        index = doc.Layers.FindByFullPath(full, -1)
        if index < 0:
            layer = Rhino.DocObjects.Layer()
            layer.Name = name
            if parent is not None:
                layer.ParentLayerId = doc.Layers[parent].Id
            index = doc.Layers.Add(layer)
        parent = index
    return index


def _add_lot(doc, sample):
    """The sample lot (in feet) as a closed outline on the Site layer, named for where it came from."""
    points = [_model_point(doc, p) for p in sample["lot"]]
    curve = rg.PolylineCurve(points + [points[0]])
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = _layer(doc, LAYERS["lot"])
    attrs.Name = sample["lot_name"]
    return doc.Objects.AddCurve(curve, attrs)


def add_floors(doc, start):
    """The starting building: one solid per story, stacked, as one group on Gordium::Massing (so a Move moves the
    house), named Floor 1, 2… None, with nothing added, if a floor isn't a box Rhino can make."""
    breps = []
    for floor in start["floors"]:
        corners = [_model_point(doc, (x, y), z) for z in (floor["base"], floor["top"]) for x, y in floor["outline"]]
        breps.append(rg.Brep.CreateFromBox(corners) if len(corners) == 8 else None)
    if not breps or any(b is None for b in breps):
        return None                     # nothing added: the caller says so
    group = doc.Groups.Add("Gordium starting building")
    ids = []
    for i, (floor, brep) in enumerate(zip(start["floors"], breps)):
        a = Rhino.DocObjects.ObjectAttributes()
        a.LayerIndex = _layer(doc, logic.MASSING)
        a.Name = "Floor " + str(i + 1)
        # one story, at the height drawn: what makes it count as a story (a stretched block no longer does)
        a.SetUserString(logic.FLOOR_KEY, str(i + 1) + ";" + repr(floor["top"] - floor["base"]))
        a.AddToGroup(group)
        ids.append(doc.Objects.AddBrep(brep, a))
    return ids


def gordium_start():
    """A new project: the prefilled facts (address, building type, zone, street side) for the architect to confirm,
    then the lot and the largest legal starting building as stacked floors, checked, with live mode on. Starts
    from a model with no building in it (an existing design is checked with GordiumCheck)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    _recover(doc)                       # anything an unfinished start box set aside (Rhino closed), back first
    if _buildings(doc):
        Rhino.RhinoApp.WriteLine("Gordium: this model already has a building; GordiumStart begins from an empty lot "
                                 "(use GordiumCheck to check a design)")
        return None
    options = ask({"cmd": "options", "jurisdiction": JURISDICTION})
    if not _lot_candidates(doc):        # an empty model: the sample project, its lot and its facts, prefilled
        sample = ask({"cmd": "sample_site"})
        sample_lot = str(_add_lot(doc, sample))
        # its facts are the sample project's; a lookup may replace its lot (never one the architect drew or picked)
        _save_ui_state(doc, dict(_ui_state(doc), from_sample=True, replaceable_lot=sample_lot,
                                 street_name=sample.get("street_name"),     # its street, as the lookup named it
                                 street_source=sample.get("street_source")))
        facts = logic.with_suggestions(dict(sample["facts"], address=sample["address"]),
                                       suggested_facts(doc, options["zones"]))
        facts["lot_id"] = str(_lot_candidates(doc)[0].Id)
    else:                               # the architect's own lot: their saved facts, else the suggestions
        try:
            saved = current_facts(doc)
        except ValueError:
            saved = {}
        facts = logic.with_suggestions(saved or {}, suggested_facts(doc, options["zones"]))
    path = os.path.join(tempfile.gettempdir(), "gordium_start_" + str(doc.RuntimeSerialNumber) + ".3dm")
    facts = confirm(doc, facts, options, "start")
    if facts is None:
        Rhino.RhinoApp.WriteLine("Gordium: nothing was started (the facts weren't confirmed)")
        return None
    save_facts(doc, facts)
    export(doc, path)                   # the model as the box left it (a lookup may have drawn a new lot)
    _set_source(doc, "starting_house", None, None)           # an earlier start's margin is gone with its house
    saved_ui = _ui_state(doc)
    # always the envelope and the 3-floor starting house (hide it from the panel); floor to floor 11'-8" unless
    # GordiumFacts set another
    start = ask({"cmd": "start", "model": path, "facts": check_facts(doc, facts),
                 "floor_to_floor": logic.parse_feet(saved_ui.get("floor_to_floor")) or logic.FLOOR_TO_FLOOR,
                 "design_buffer": logic.parse_feet(saved_ui.get("design_buffer")) or 0.0})   # Draw is off if unread
    STATE["start"] = {k: start.get(k) for k in ("stories", "height", "area", "coverage_allowed", "notes", "floors")}
    for note in start.get("notes") or []:
        Rhino.RhinoApp.WriteLine("Gordium: " + note)
    if not start.get("floors"):
        Rhino.RhinoApp.WriteLine("Gordium: no starting building could be drawn; " + logic.draw_one_hint(_auto(doc)))
        live(True)                   # the architect draws one: checked at Check (or after each edit, if ticked)
        documents(True)
        return None
    if Rhino.RhinoDoc.ActiveDoc is None or Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber != doc.RuntimeSerialNumber:
        Rhino.RhinoApp.WriteLine("Gordium: the document in front changed while the box was open; nothing was drawn "
                                 "(run GordiumStart again in " + _doc_name(doc) + ")")
        return None
    Rhino.RhinoApp.WriteLine("Gordium: drawing in " + _doc_name(doc))
    if add_floors(doc, start) is None:
        Rhino.RhinoApp.WriteLine("Gordium: the starting building couldn't be drawn; " + logic.draw_one_hint(_auto(doc)))
        live(True)
        documents(True)
        return None
    fact = logic.starting_house_fact(start.get("margin_note"), logic.city_day())   # Gordium's figure
    if fact:
        _set_source(doc, "starting_house", fact["value"], fact["source"], fact["confirmed_by"])
    doc.Views.Redraw()
    result = run_check(doc, report=False)
    live(True)
    documents(True)
    frame_site(doc, facts)
    Rhino.RhinoApp.WriteLine("Gordium: created 1 group (" + str(len(start["floors"])) + " floor solids) on " +
                             logic.MASSING)
    return result


# ---- the context map: the neighbourhood around a looked-up lot (design_checker.context_box) ---------------------
# Drawn after Draw on its own grey layers under Gordium::Context, which the checker never measures
# (rhino_logic.classify; a solid there over the lot makes the check need review: rhino_logic.left_out_candidate).
# Only what rhino_logic.context_objects allows is written into the file (sources whose store is raw: the State's
# parcels, streets and building footprints, and Gordium's own frame, north arrow, scale bar and credits). The
# footprints' layer is left unlocked: the architect drags and edits them, and an edited outline is theirs (Ben,
# 2026-10-21). A source that may not be kept (store: none) would be drawn on screen only, by the overlay.

CONTEXT_GREYS = {"Parcels": (150, 150, 150), "Streets": (120, 120, 120), "Buildings": (135, 135, 135),
                 "Notes": (110, 110, 110)}


def _context_layer(doc, name):
    """A context sublayer, made grey; locked again by _lock_context once its objects are in."""
    index = _layer(doc, logic.CONTEXT + "::" + name)
    r, g, b = CONTEXT_GREYS[name]
    doc.Layers[index].Color = System.Drawing.Color.FromArgb(r, g, b)
    return index


def _context_layer_indexes(doc):
    return [i for i, layer in enumerate(doc.Layers)
            if not layer.IsDeleted and logic.on_layer(layer.FullPath, logic.CONTEXT)]


def _parent_locked(doc, layer):
    """Whether any layer above this one is locked. Rhino then holds the layer locked whatever its own lock says:
    locking a parent gives each sublayer the lock and saves the sublayer's own one as its persistent lock, which
    unlocking the parent puts back (Layer.GetPersistentLocking). Under a locked parent IsLocked reads True for every
    sublayer and says nothing about its own lock (the Rhino job's probe at e631aae)."""
    parent = layer.ParentLayerId
    while parent != System.Guid.Empty:
        above = doc.Layers.FindId(parent)
        if above is None:
            return False
        if above.IsLocked:
            return True
        parent = above.ParentLayerId
    return False


def _own_lock(doc, layer):
    """A layer's own lock: what it is once every layer above it is unlocked (its persistent lock under a locked
    parent, its IsLocked otherwise)."""
    return bool(layer.GetPersistentLocking()) if _parent_locked(doc, layer) else bool(layer.IsLocked)


def _set_own_lock(doc, layer, locked):
    """Give a layer its own lock: under a locked parent as its persistent lock (Rhino keeps it locked until the
    parent is unlocked, then puts this back), otherwise as its lock. Setting only IsLocked under a locked parent left
    every context layer's persistent lock off, so unlocking "Gordium" unlocked Parcels, Streets and Notes (the Rhino
    job, context_in_rhino.py claim 4 at e631aae). A layer added under a locked parent (the first draw in a file whose
    "Gordium" is locked) may never have been locked by Rhino: it is locked like every other sublayer there, then
    given its own lock (review round 1 of the fix)."""
    if _parent_locked(doc, layer):
        if not layer.IsLocked:
            layer.IsLocked = True
        layer.SetPersistentLocking(bool(locked))
    else:
        layer.IsLocked = bool(locked)


def _lock_context(doc, locked):
    """Unlock every context layer, or lock them again: all but the editable footprints (rhino_logic.context_locked).
    Each layer's own lock, so it holds whether or not the architect has locked "Gordium" above them; a parent before
    its sublayers, so a parent's change can't undo a sublayer's set before it."""
    indexes = _context_layer_indexes(doc)
    for i in logic.outermost_first([(i, doc.Layers[i].FullPath) for i in indexes]):
        _set_own_lock(doc, doc.Layers[i], bool(locked) and logic.context_locked(doc.Layers[i].FullPath))


def _outline_points(geometry):
    """An outline's points as Rhino holds them (x, y, z, model units), or None for anything that isn't a polyline."""
    if not isinstance(geometry, rg.Curve):
        return None
    ok, polyline = geometry.TryGetPolyline()
    return [(q.X, q.Y, q.Z) for q in polyline] if ok else None


def _attrs_print(attrs, doc):
    """An outline's attributes for its fingerprint: each of rhino_logic.FINGERPRINT_ATTRIBUTES (one this Rhino lacks or
    won't read is left out, the same on every read), the layer, linetype and material by their ids and the groups by
    theirs (never a table position, which moves when a deleted layer isn't saved: review round 3), and the
    architect's own user text (never Gordium's keys, written after drawing)."""
    out = {}
    for name in logic.FINGERPRINT_ATTRIBUTES:
        try:
            out[name] = logic.attribute_text(getattr(attrs, name))
        except Exception:                      # not in this Rhino, or not readable here: not part of the fingerprint
            continue
    for name, table, index in (("layer", doc.Layers, attrs.LayerIndex), ("linetype", doc.Linetypes, attrs.LinetypeIndex),
                               ("material", doc.Materials, attrs.MaterialIndex)):
        out[name] = _table_id(table, index)
    out["groups"] = sorted(_table_id(doc.Groups, g) for g in (attrs.GetGroupList() or []))
    keys = attrs.GetUserStrings()
    out["user"] = sorted((k, attrs.GetUserString(k)) for k in (keys.AllKeys if keys is not None else [])
                         if k and not str(k).startswith("gordium_"))
    return out


def _table_id(table, index):
    """The id of a layer, linetype, material or group by its index ("" for none, -1: from the layer or the default)."""
    try:
        index = int(index)
        if index < 0:
            return ""
        item = table.FindIndex(index) if hasattr(table, "FindIndex") else table[index]
        return str(item.Id) if item is not None else "#%d" % index
    except Exception:
        return "#%s" % index


def _clear_context(doc, sources=None):
    """Every object Gordium drew on the context layers (each carries its source in CONTEXT_KEY) deleted, whatever the
    layers' state: a hidden or locked layer's objects aren't deleted (Delete without ignoring modes), so each layer
    is shown and unlocked for it, then put back as it was and locked (review round 1: a context hidden in an earlier
    session was drawn twice). The live footprints and the saved snapshot go with it. With `sources`
    (rhino_logic.context_replaces), only those sources' objects go, and the caller rewrites the record and the
    footprints: a layer whose service failed keeps what was saved."""
    dirty = STATE.get("dirty")             # deleting the context changes nothing the check reads (see draw_context)
    indexes = _context_layer_indexes(doc)
    roots = []                             # a locked or hidden parent ("Gordium") holds its sublayers' objects too
    for i in indexes:                      # (review round 4): shown and unlocked for the delete, then put back
        top, parent = doc.Layers[i], doc.Layers[i].ParentLayerId
        while parent != System.Guid.Empty:
            j = doc.Layers.FindId(parent)
            if j is None:
                break
            top, parent = j, j.ParentLayerId
        if top.FullPath not in roots:
            roots.append(top.FullPath)
    # Every layer a parent's IsVisible can reach (in Rhino 8 it gives each sublayer the parent's lock: review round
    # 5), the architect's own Gordium::Grade and Massing too, outermost first; each is put back exactly as it was.
    touched = logic.outermost_first([(i, layer.FullPath) for i, layer in enumerate(doc.Layers) if not layer.IsDeleted
                                     and any(logic.on_layer(layer.FullPath, r) for r in roots)])
    # each layer's own lock (_own_lock): IsLocked under a locked parent reads True for every sublayer, so putting it
    # back left every sublayer's persistent lock off (unlocking "Gordium" unlocked them all: the Rhino job at e631aae)
    was = [(i, doc.Layers[i].IsVisible, doc.Layers[i].IsLocked, _own_lock(doc, doc.Layers[i])) for i in touched]
    for i in touched:                      # a parent before its sublayers: its IsVisible can't lock them again
        doc.Layers[i].IsVisible = True
        doc.Layers[i].IsLocked = False
    left = 0                               # objects Rhino refused to delete or change: returned, never drawn over silently
    for i in indexes:
        for o in list(doc.Objects.FindByLayer(doc.Layers[i]) or []):
            source = o.Attributes.GetUserString(logic.CONTEXT_KEY)
            if not source or (sources is not None and source not in sources):
                continue
            if logic.kept_on_clear(o.Attributes.GetUserString(logic.GEOM_KEY), o.Attributes.GetUserString(
                    logic.DRAWN_KEY), str(o.Id), _outline_points(o.Geometry), _attrs_print(o.Attributes, doc)):
                attrs = o.Attributes.Duplicate()          # the architect edited it: theirs now, never removed
                attrs.SetUserString(logic.CONTEXT_KEY, None)
                attrs.SetUserString(logic.EDITED_KEY, "1")
                left += not doc.Objects.ModifyAttributes(o, attrs, True)
            else:
                left += not doc.Objects.Delete(o, True)
    for i, visible, _, _ in was:           # every visibility first (each passes its lock down), then every lock,
        doc.Layers[i].IsVisible = visible
    for i, _, locked, _ in was:            # a parent before its sublayers (locking it saves theirs as it finds them),
        doc.Layers[i].IsLocked = locked
    for i, _, _, own in was:               # then each layer's own lock, once every lock above it is back
        _set_own_lock(doc, doc.Layers[i], own)
    _lock_context(doc, True)               # the context layers as Gordium keeps them: all but the footprints
    if sources is None:
        if logic.guides_of(STATE.get("context_guides"), doc.RuntimeSerialNumber):
            STATE.pop("context_guides", None)
        doc.Strings.Delete(SECTION, logic.CONTEXT_ENTRY)
    STATE["dirty"] = dirty
    return left                            # the caller puts it in its one line (review round 6)


def _edited_pieces(doc):
    """The outlines the architect has edited (kept on the context layers as theirs): each one's id, the lot it was
    drawn for, the object id it was drawn as and its own (rhino_logic.suppressed decides which hide a redraw)."""
    out = []
    for i in _context_layer_indexes(doc):
        for o in doc.Objects.FindByLayer(doc.Layers[i]) or []:
            a = o.Attributes
            if a.GetUserString(logic.EDITED_KEY):
                out.append({"id": a.GetUserString(logic.PIECE_KEY) or "", "frame": a.GetUserString(logic.FRAME_KEY),
                            "drawn_as": a.GetUserString(logic.DRAWN_KEY), "own": str(o.Id)})
    return out


def _context_record(doc):
    """The record of the neighbourhood in this file (rhino_logic.context_record), or None."""
    try:
        return json.loads(doc.Strings.GetValue(SECTION, logic.CONTEXT_ENTRY) or "null")
    except (ValueError, AttributeError):
        return None


def _context_payload(frame):
    """The context for a saved lookup frame: context_box in its own process (the repo's .venv), stopped after
    CONTEXT_LIMIT_S. None when there is no looked-up lot to centre it on."""
    args = logic.context_command(_python(), frame, STATE.get("lookup_fixture"))
    if args is None:
        return None
    say("Fetching the neighbourhood (up to %d s)…" % logic.CONTEXT_LIMIT_S)   # Rhino waits: say why first (round 4)
    Rhino.RhinoApp.Wait()
    packages = os.path.join(REPO, "packages")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(STATE.get("extra_paths", []) + [
        os.path.join(packages, n) for n in sorted(os.listdir(packages)) if os.path.isdir(os.path.join(packages, n))])
    with open(os.path.join(tempfile.gettempdir(), "gordium_worker.log"), "a", encoding="utf-8") as err:
        try:
            done = ui.spawn(args, run=True, cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=err,   # no console
                            timeout=logic.CONTEXT_LIMIT_S, encoding="utf-8")                   # on Windows
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "message": "The neighbourhood took longer than %d s: the lot is drawn "
                    "without it (Show neighbourhood tries again)." % logic.CONTEXT_LIMIT_S}
    lines = (done.stdout or "").strip().splitlines()
    return json.loads(lines[-1]) if lines else {"status": "error"}


def _context_text(doc, o, anchor):
    """A context note as model text: its lines from the anchor up (bottom-left justified), along the note's turn
    (`rotation_deg`, the square's), o["height_ft"] high."""
    a = math.radians(o.get("rotation_deg") or 0.0)
    plane = rg.Plane(anchor, rg.Vector3d(math.cos(a), math.sin(a), 0), rg.Vector3d(-math.sin(a), math.cos(a), 0))
    text = rg.TextEntity.Create(o.get("text") or "", plane, doc.DimStyles.Current, False, 0, 0)
    # the note's own scale, not the document's: a template's dimension style can carry a model-space scale (the feet
    # template's "Feet Decimal": 12, with annotation scaling on), which multiplied the text to ~30 ft letters (Rhino
    # job's probe, PR #23). At 1 the note is NOTE_HEIGHT_FT high as drawn, whatever the template.
    text.DimensionScale = 1.0
    text.TextHeight = _model_length(doc, o.get("height_ft") or logic.NOTE_HEIGHT_FT)
    text.Justification = rg.TextJustification.BottomLeft
    return text


def draw_context(doc, frame, left=0):
    """The neighbourhood around the looked-up lot: fetched, then drawn in place of any earlier one. Says what it
    drew (or why it didn't), with any of Gordium's objects Rhino refused to remove first (`left`: an earlier clear's
    count; the panel shows one line, so the warning goes in it: review round 6)."""
    payload = _context_payload(frame)
    if payload is None:
        say(logic.with_not_cleared(logic.NO_CONTEXT, left))
        return None
    if payload.get("status") != "found":   # nothing answered: what is saved stays as it is
        say(logic.with_not_cleared(logic.context_says(payload), left))
        return payload
    old = _context_record(doc)
    held = STATE.get("context_guides") or {}
    # one plan for the message, the record, what is deleted and the footprints on screen (review rounds 6-7)
    plan = logic.context_merge(payload, old, frame,
                               live_on_screen=logic.guides_on_screen(held, doc.RuntimeSerialNumber))
    payload, record, sources, keep_guides = plan["payload"], plan["record"], plan["replace"], plan["keep_guides"]
    STATE.pop("context_guides", None)
    dirty = STATE.get("dirty")             # live mode hears every add: the context changes nothing the check reads,
    left += _clear_context(doc, sources)   # so the model's "changed since the check" mark is put back after
    _lock_context(doc, False)
    layers = {logic.CONTEXT + "::" + name: _context_layer(doc, name) for name in CONTEXT_GREYS}
    here = logic.frame_key(frame)
    edited = logic.suppressed(_edited_pieces(doc), here)        # the architect's own edited outlines stay, alone
    for o in logic.skip_edited(logic.context_objects(payload), edited):
        attrs = Rhino.DocObjects.ObjectAttributes()
        attrs.LayerIndex = layers.get(o["layer"]) if o["layer"] in layers else _layer(doc, o["layer"])
        attrs.Name = o.get("name") or ""
        attrs.SetUserString(logic.CONTEXT_KEY, o["source"])
        pts = [_model_point(doc, p) for p in o["points"]]
        if o["kind"] == "dot":
            doc.Objects.AddTextDot(o.get("text") or "", pts[0], attrs)
        elif o["kind"] == "text":          # the sources: wrapped model text from its anchor, turned with the square
            doc.Objects.AddText(_context_text(doc, o, pts[0]), attrs)
        else:
            curve = rg.PolylineCurve(pts + [pts[0]] if o["kind"] == "closed" else pts)
            if o.get("id"):
                attrs.SetUserString(logic.PIECE_KEY, o["id"])
            attrs.SetUserString(logic.FRAME_KEY, here)
            added = doc.Objects.FindId(doc.Objects.AddCurve(curve, attrs))
            if added is not None:          # fingerprinted as Rhino holds it (points, Z, attributes): an edit is seen later
                marked = added.Attributes.Duplicate()
                marked.SetUserString(logic.GEOM_KEY, logic.outline_key(_outline_points(added.Geometry),
                                                                       _attrs_print(added.Attributes, doc)))
                marked.SetUserString(logic.DRAWN_KEY, str(added.Id))
                doc.Objects.ModifyAttributes(added, marked, True)
    _lock_context(doc, True)
    STATE["dirty"] = dirty
    _context_visible(doc, _context_on(doc))
    # the snapshot (records, never data) with the frame it was drawn around: sync_context compares the lot's frame
    # (layer by layer: a failed layer's entries carried over, rhino_logic.context_merge)
    doc.Strings.SetString(SECTION, logic.CONTEXT_ENTRY, json.dumps(record))
    if keep_guides:                        # the footprint service didn't answer: the ones on screen stay
        STATE["context_guides"] = held
    else:
        guides = [rg.Polyline([_model_point(doc, p) for p in pts + [pts[0]]]) for pts in logic.context_guides(payload)]
        box = rg.BoundingBox.Empty
        for line in guides:
            box.Union(line.BoundingBox)
        STATE["context_guides"] = {"doc": doc.RuntimeSerialNumber, "lines": guides, "box": box}
    doc.Views.Redraw()
    say(logic.with_not_cleared(logic.context_says(payload), left))
    return payload


def sync_context(doc, facts):
    """After a box's Draw (GordiumStart or Edit site…): the neighbourhood follows the lot (rhino_logic.context_step).
    A lot the lookup drew gets its own, an earlier one (another address, a lot since drawn or picked) is cleared, the
    same lot keeps what is drawn (review round 2: an Edit site… lookup left the earlier address's neighbourhood)."""
    drawn = (_context_record(doc) or {}).get("frame")
    frame = logic.context_frame(facts, _ui_state(doc))
    on = _context_on(doc)
    step = logic.context_step(frame, drawn, on)
    refetch = logic.needs_refetch(STATE.get("context_guides"), _context_record(doc), doc.RuntimeSerialNumber)
    if step == "keep" and frame and on and refetch:
        # the same lot, with a layer to fetch again (one that failed, or a live-only one not on screen in a reopened
        # file). draw_context replaces what is drawn only once the fetch has worked, so offline what is saved stays
        draw_context(doc, frame)
        return
    left = 0                           # Gordium's objects Rhino refused to remove: put in the one line said
    if step in ("clear", "draw", "off"):
        left = _clear_context(doc)
    if step == "draw":
        draw_context(doc, frame, left)     # says what it drew, or why not
    elif step == "off":
        say(logic.with_not_cleared("Neighbourhood not drawn: Show neighbourhood is off in the panel (tick it to draw "
                                   "it).", left))
    elif step == "clear":
        say(logic.with_not_cleared("Neighbourhood removed: it is drawn only around a lot the start box looked up.",
                                   left))
    elif frame and on:
        _context_visible(doc, True)    # as the tick says (a file saved with it off opens hidden)


def _context_on(doc):
    """This document's Show neighbourhood (rhino_logic.context_shown: its Gordium settings, on unless unticked), also
    kept per document for the drawing (draw_scene runs every frame). On when there is no document."""
    if doc is None:
        return True
    on = logic.context_shown(_ui_state(doc))
    STATE.setdefault("context_by_doc", {})[doc.RuntimeSerialNumber] = on
    return on


def _context_visible(doc, on):
    """Every context layer on or off (a sublayer hidden in the Layers panel too), then locked again: in Rhino 8,
    setting a parent layer's IsVisible (even to what it was) gives its sublayers the parent's lock, and the parent
    (Gordium::Context) is unlocked so the footprints can be dragged, so every context layer came out unlocked (found
    by the Rhino job running context_in_rhino.py at c783ee6, review round 4). Whether there is one."""
    indexes = _context_layer_indexes(doc)
    for i in indexes:
        doc.Layers[i].IsVisible = bool(on)
    _lock_context(doc, True)               # after any visibility change, never before it
    return bool(indexes)


def show_context(on):
    """The panel's "Show neighbourhood": the context layers (and anything shown live) on or off, kept with the file.
    Turned on with a layer to fetch again (rhino_logic.needs_refetch), the neighbourhood is fetched again."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        say(logic.NO_DOCUMENT)
        return
    _save_ui_state(doc, dict(_ui_state(doc), show_context=bool(on)))     # per file (coordinator, 2026-10-21)
    STATE.setdefault("context_by_doc", {})[doc.RuntimeSerialNumber] = bool(on)
    drawn = _context_visible(doc, on)
    refetch = logic.needs_refetch(STATE.get("context_guides"), _context_record(doc), doc.RuntimeSerialNumber)
    loaded = not refetch
    if on and refetch:                     # draw_context says what it drew, or why it couldn't
        try:
            facts = current_facts(doc)
        except ValueError:
            facts = {}
        draw_context(doc, logic.context_frame(facts, _ui_state(doc)))
    elif on:
        doc.Views.Redraw()
        say("Neighbourhood shown (drawing only: the check never measures it).")
    else:
        doc.Views.Redraw()
        say("Neighbourhood hidden." if drawn or loaded else "Neighbourhood off (none drawn in this file).")


def _doc_name(doc):
    """The document as the architect knows it: its file name, or "the untitled document"."""
    return os.path.basename(doc.Path) if doc.Path else (doc.Name or "the untitled document")


FRAME_ROOM = 0.75      # the model framed in the middle 75% of each view: the status box and the "no longer
                       # complies" notice sit in the band around it (architect's review, 2026-10-21: framed
                       # tight, the notice hid the lot's lower edge and dimensions)


def frame_site(doc, facts):
    """Every view framed on the lot and the starting house. A new file's template frames a few millimeters (or
    inches) around the origin, so without this the house sat outside every view (seen in a millimeter template,
    2026-10-20)."""
    lot = _find(doc, facts.get("lot_id") or "")
    if lot is None:
        return
    box = lot.Geometry.GetBoundingBox(True)
    for o in _buildings(doc):
        box.Union(o.Geometry.GetBoundingBox(True))
    box.Inflate(_model_length(doc, 10))                        # 10 ft around, in the model's units
    for view in doc.Views:
        view.ActiveViewport.ZoomBoundingBox(box)
    # a view that isn't on screen (Perspective maximized, as a new Mac file opens) ignores a zoom; Rhino's own
    # Zoom All Selected frames those too, on the lot and the house only (Extents would also take in anything far
    # away in the file). The architect's selection is put back as it was.
    picked = [o.Id for o in doc.Objects.GetSelectedObjects(False, False)]
    try:
        doc.Objects.UnselectAll()
        for o in [lot] + list(_buildings(doc)):
            o.Select(True)
        Rhino.RhinoApp.RunScript("_-Zoom _All _Selected", False)
        for view in doc.Views:               # room around the model for the status box and the notice
            view.ActiveViewport.Magnify(FRAME_ROOM, False)
    except Exception:
        pass
    finally:
        doc.Objects.UnselectAll()
        for i in picked:
            doc.Objects.Select(i)
    doc.Views.Redraw()



def _release(key, value):
    """Release one handle an earlier copy left in STATE, through this copy's tolerant undo (a copy from before
    LEFTOVERS registered nothing there): its hooks (old tuple shapes too), its drawing, panel, timer, checker."""
    if key == "hooks":
        _unhook()
    elif key == "doc_hooks":
        documents(False)
    elif key == "command_hook":
        _off(Rhino.Commands.Command, "BeginCommand", value)
    elif key == "overlay":
        value.Enabled = False
    elif key == "panel":                       # an older copy's panel (a form)
        value.Close()
    elif key == "panel_parts":                 # this PR's (or a later copy's) floating panel ({"form": ...}): updating from it
        form = (value or {}).get("form")
        if form is not None:
            form.Close()
    elif key == "toast_timer":
        value.Stop()
    elif key == "worker":
        _stop_worker()
    elif key == "worker_sends":
        value.put(None)


# an earlier copy's handlers, drawing, panel and checker: undone (LEFTOVERS), released and forgotten (STATE)
logic.sweep(LEFTOVERS, STATE, _release)
if STATE.get("live"):                        # live mode was on before this copy loaded: its hooks back on
    live(True)
# Rhino closing: the checker stopped with it (and any an earlier load left: SERVERS)
_on(Rhino.RhinoApp, "Closing", _handler(System.EventHandler, lambda s, e: _stop_worker(), "stop the checker"))
