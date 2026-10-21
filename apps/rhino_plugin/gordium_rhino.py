#! python3
"""Gordium in Rhino 8: GordiumCheck checks the open model against its zone's rules, shows the largest legal
building (the envelope), and re-checks after every edit (live mode).

This script only talks to Rhino. All measuring and checking is Gordium's own Python (the repo's packages, run
by its .venv in the background; docs/decisions/2026-10-20_rhino_talks_to_python.md): the lot and building
objects are copied into a small temporary .3dm, sent with the lot facts, and the answer is drawn. Nothing in
the model is changed: highlights, the envelope and the message are drawn on top (a display conduit).

Commands (set up by install.py): GordiumStart (a new project: the lot and the largest legal starting building),
GordiumCheck, GordiumLive (on/off), GordiumFacts (edit the lot facts), GordiumOff (stop and clear the drawing).
"""

import json
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

# no callback may raise into Rhino (on the Mac that aborts Rhino): rhino_logic.guard catches, logs, says it once
logic.ERROR_LOG = os.path.join(tempfile.gettempdir(), "gordium_errors.log")
logic.REPORT = Rhino.RhinoApp.WriteLine
CONDUIT_WORDS = {"cull": "choose what to draw", "bounds": "size the drawing", "draw_scene": "draw in the model",
                 "draw_screen": "draw the labels and status"}


def _conduit(name, o, e):
    """The display conduit's one way in: the named drawing function, guarded (a failure draws nothing this frame
    and is logged and said once, never raised into Rhino's drawing)."""
    logic.guard(globals().get(name) or (lambda *a: None), CONDUIT_WORDS.get(name, name))(o, e)

logic.sweep(LEFTOVERS)                       # an earlier copy's handlers, drawing, panel and checker: undone


def _is_current():
    return sys.modules.get(__name__) is _MODULE


def _on(owner, name, handler):
    """Attach a handler to a Rhino event, remembered in LEFTOVERS so a later copy can always detach it."""
    event = getattr(owner, name)
    event += handler
    LEFTOVERS["%s.%s:%d" % (owner.__name__, name, id(handler))] = lambda: _off(owner, name, handler)


def _off(owner, name, handler):
    event = getattr(owner, name)
    event -= handler
    LEFTOVERS.pop("%s.%s:%d" % (owner.__name__, name, id(handler)), None)


def _handler(kind, fn):
    """An event handler, inert once another copy of this script is loaded."""
    return kind(logic.current_only(fn, _is_current))


def _redraw():
    """Redraw the front document's views; nothing when no document is open (Rhino's start screen)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is not None:
        doc.Views.Redraw()

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
        if p.poll() is None:
            p.terminate()
        p = None
    if p is None:
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"      # UTF-8 everywhere in the checker, third-party code too (Windows uses cp1252)
        env["PYTHONPATH"] = os.pathsep.join(STATE.get("extra_paths", []) + [
            os.path.join(packages, n) for n in sorted(os.listdir(packages)) if os.path.isdir(os.path.join(packages, n))])
        log = open(os.path.join(tempfile.gettempdir(), "gordium_worker.log"), "a", encoding="utf-8")
        p = subprocess.Popen([_python(), "-u", "-m", "design_checker", "serve"], cwd=REPO, env=env,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                             universal_newlines=True, encoding="utf-8")
        # its pipes served by threads: Rhino's thread never reads or writes one (rhino_logic.pipes)
        STATE["worker_sends"], STATE["worker_lines"] = logic.pipes(p)
        STATE["worker"] = p
        STATE["worker_code"] = now
        LEFTOVERS["worker"] = p.kill                     # a later copy of this script stops it
    return p


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
    if not old:
        for g in getattr(o, "encroach", None) or []:   # only the part inside a yard or above the height (F5)
            d.DrawBrepShaded(g, Rhino.Display.DisplayMaterial(ui.status_color("does_not_comply", dark), 0.35))
            d.DrawBrepWires(g, ui.status_color("does_not_comply", dark), 2)
    for g in o.red:                          # a failing solid the plan can't show a part of (kept for blocks, SubD)
        if isinstance(g, rg.Mesh):
            d.DrawMeshWires(g, ui.status_color("does_not_comply", dark))
        else:
            d.DrawBrepWires(g, ui.status_color("does_not_comply", dark), 2)
    if getattr(o, "yards_zone", None) is not None:          # the required yards, lightly shaded
        d.DrawBrepShaded(o.yards_zone, Rhino.Display.DisplayMaterial(BLUE, 0.9))
    if o.envelope is not None:               # see-through, drawn after the solids so they show through it
        d.DrawBrepShaded(o.envelope, Rhino.Display.DisplayMaterial(BLUE, 0.88))
        d.DrawBrepWires(o.envelope, BLUE, 1)
    for pt in getattr(o, "grade_points", None) or []:           # spot grades
        d.DrawPoint(pt, Rhino.Display.PointStyle.X, 5, ui.status_color("complies", dark))
    if getattr(o, "lot_outline", None) is not None:              # the property line: phantom (F2)
        pts = o.lot_outline
        d.DrawPatternedPolyline(pts, ui.status_color("complies", dark), ui.PHANTOM, 2, True)
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
    taken = []                               # labels drawn this frame: none covers another, nor the status box
    if o.message:
        taken.append(logic.status_box(e.Viewport.Bounds.Width, _status_rows(o, stale(o))))
    # labels only in a plan view: parallel and looking straight down (Top). In 3D they sat on the massing, and in
    # the Front and Right elevations every plan label piled up on the ground line (Ben's test, 2026-10-20)
    plan = logic.is_plan_view(e.Viewport.IsParallelProjection, e.Viewport.CameraDirection.Z)
    for line, text, status in getattr(o, "yard_dims", None) or []:   # each yard as measured, status-marked (F4)
        color = ui.status_color("complies" if old else status, dark)
        a, b = e.Viewport.WorldToClient(line.From), e.Viewport.WorldToClient(line.To)
        d.Draw2dLine(System.Drawing.PointF(a.X, a.Y), System.Drawing.PointF(b.X, b.Y), color, 2)
        for p in (a, b):                     # tick ends
            d.Draw2dLine(System.Drawing.PointF(p.X - 5, p.Y + 5), System.Drawing.PointF(p.X + 5, p.Y - 5), color, 2)
        if old:
            text = text.split(" ", 1)[1] if text[:1] in ("?", "✕", "✓") else text
        if plan:
            ui.label_at(d, e.Viewport, (line.From + line.To) / 2, text, color, dark, 11, taken)
    for point, text in (getattr(o, "edge_labels", None) or []) if plan else []:   # each lot edge's length
        ui.label_at(d, e.Viewport, point, text, ui.status_color("complies", dark), dark, 11, taken)
    toast = getattr(o, "toast", None)
    active = Rhino.RhinoDoc.ActiveDoc.Views.ActiveView
    if toast and time.time() < toast[1] and active is not None and e.Viewport.Id == active.ActiveViewportID:
        lines = ["✕ " + line for line in toast[0]]           # bottom left, active view only (G1)
        ui.draw_text_box(d, lines, ui.status_color("does_not_comply", dark), 14,
                         int(e.Viewport.Bounds.Height) - (22 * len(lines) + 12) - 64, dark, 13)
    if not o.message:
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
    if old:                                  # out of date: neutral, no status (F7)
        state, text, lines = "stale", "Checking… (the model changed)", lines[:1]
    mark = {"does_not_comply": "✕", "needs_review": "?"}.get(state, "")
    return ["Gordium · " + (mark + " " if mark else "") + text] + list(lines)[:3]


def overlay():
    """The one drawing layer (its drawing code is always this script's current functions, see Overlay)."""
    o = STATE.get("overlay")
    if o is None:
        o = Overlay()
        STATE["overlay"] = o
        LEFTOVERS["overlay"] = lambda: setattr(o, "Enabled", False)
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


def _actions():
    """What the panel's buttons do (gordium_ui.make_panel): each one gated, so while a start box is open none of them
    touches the model (rhino_logic.gate_actions)."""
    return logic.gate_actions(PANEL_ACTIONS(), _box_open, say)


def PANEL_ACTIONS():
    return {"zoom": zoom_to, "report": open_report, "envelope": set_envelope, "edit_site": edit_facts,
            "survey": pick_survey, "grade": set_grade, "enter": enter_rooms, "add": add_to_check, "legend": ui.legend,
            "retry": lambda: run_check(Rhino.RhinoDoc.ActiveDoc, report=False), "ground": this_is_the_ground,
            "massing": hide_massing, "not_ground": not_the_ground}


def _box_open():
    gate = STATE.get("box_gate")
    return bool(gate is not None and gate.open)


def panel():
    """The Gordium panel, made once and shown. (A floating panel: a docked one needs a Rhino plugin package.)"""
    p = STATE.get("panel_parts")
    if p is None or not p["form"].Visible:
        p = ui.make_panel(_actions())
        STATE["panel_parts"] = p
        LEFTOVERS["panel"] = p["form"].Close             # a later copy of this script closes it
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
    view.Redraw()


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


def enter_rooms():
    """Enter bedrooms and parking spaces…: two prompts (Enter skips; never a default)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    try:
        facts = current_facts(doc)
        answers = {k: _count(p) for k, p in (("sleeping_rooms", "Bedrooms"), ("parking_spaces", "Off-street parking spaces"))}
    except Cancelled:
        say("Cancelled: nothing changed.")
        return
    save_facts(doc, logic.update_counts(facts, answers))
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
                or logic.on_layer(layer, "Gordium"):
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
                        "date": time.strftime("%Y-%m-%d")}
    doc.Strings.SetString(SECTION, SOURCES_ENTRY, json.dumps(sources))


def _extras(doc, facts):
    """What the panel needs to say about the check beyond the measurements: what was sent (C8), objects on the
    lot left out, the use's name."""
    buildings = _buildings(doc)
    groups = {i for o in buildings for i in (o.Attributes.GetGroupList() or [])}
    layers = sorted({doc.Layers[o.Attributes.LayerIndex].FullPath for o in buildings})
    left_out = _not_included(doc, _find(doc, facts.get("lot_id") or ""))
    return {"scope": {"groups": len(groups), "solids": len(buildings), "layer": ", ".join(layers)},
            "not_included": left_out, "touching": _touching(doc, left_out, buildings),
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
            "\nStreet side = the highlighted blue line · " +
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
            "zone": facts.get("zone"), "zone_source": source("zone", logic.ENTERED),
            "district_confirmed": confirmed, "use": facts.get("use"), "use_source": source("use"),
            "use_name": (options.get("uses") or {}).get(facts.get("use"), facts.get("use")),
            "lot_area": area, "lot_surveyed": bool(facts.get("lot_surveyed")),
            "street_name": saved_ui.get("_street_name") or saved_ui.get("street_name") or facts.get("street_name"),
            "street_name_saved": None if saved_ui.get("_street_name") else saved_ui.get("street_name"),
            "street_source": saved_ui.get("street_source") or source("street"),
            "ground": {"kind": kind, "count": len(points), "range": span, "source": ground_source},
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
    facts = dict(facts, address=state["address"] or None, zone=state["zone"], use=state["use"],
                 lot_surveyed=bool(state.get("lot_surveyed")), corner_lot=state.get("corner_lot"))
    if facts.get("corner_lot") is None:             # unanswered: the checker says the yards need review
        facts.pop("corner_lot")
    if not facts.get("address"):
        facts.pop("address")
    facts.pop("grade_points", None)                 # read (or sampled) from the model at every check
    for key, value in logic.ground_facts(state, _lot_level(doc, facts)).items():
        if value is None:
            facts.pop(key, None)
        else:
            facts[key] = value
    saved_ui = dict(saved_ui, ground_kind=(state.get("ground") or {}).get("kind") or "flat",
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
        facts, saved_ui = logic.pick_effect(what, _pick_outcome(doc, what, facts, session), facts, saved_ui)
    _highlight(doc, facts)
    return facts, saved_ui


def _pick_outcome(doc, what, facts, session):
    """What one pick gave, or None (Esc, Enter, nothing picked). Drawn objects go through the session."""
    if what == "street":
        lot = _find(doc, facts.get("lot_id") or "")
        if lot is None:
            return None
        rc, point = Rhino.Input.RhinoGet.GetPoint("Click the lot line on the street", True)
        if rc != Rhino.Commands.Result.Success:
            return None
        a, b = min(_segments(lot.Geometry), key=lambda s: rg.Line(s[0], s[1]).DistanceTo(point, True))
        return [_feet_point(doc, a)[:2], _feet_point(doc, b)[:2]]
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
    try:
        ui.set_box_open(STATE.get("panel_parts"), True)
        return _confirm(doc, facts, options, mode)
    finally:
        gate.leave()
        ui.set_box_open(STATE.get("panel_parts"), False)
        if STATE.get("dirty"):          # edits made while the box was open: live mode checks them at the next idle
            STATE["dirty"] = time.time() - IDLE_SECONDS


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
    STATE["lookup"] = {"proc": subprocess.Popen(args, cwd=REPO, env=env, stdout=sink, stderr=err),
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
        sources.update(logic.fact_sources(state, time.strftime("%Y-%m-%d"), confirmed=True))
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
    was_corner = facts.get("corner_lot")
    facts["corner_lot"] = _yes_no("Corner lot (two streets meet at it)?", was_corner)
    facts = logic.after_corner_answer(facts, was_corner)
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
            facts["street_line"] = picked
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
    o.confirm, o.labels = None, []
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


def _draw_plan(doc, o, result, facts):
    """What the viewport shows for a result (F): the property line, each lot edge's length, the required yards
    shaded, the envelope (dashed, see-through), each yard as measured with its status, and red only on the part
    of the building inside a yard or above the height limit (the massing stays neutral)."""
    plan = result.get("plan") or {}
    lot = _find(doc, facts.get("lot_id") or "")
    if lot is not None:
        ok, poly = lot.Geometry.TryGetPolyline()
        o.lot_outline = list(poly) if ok else None
    approx = "" if facts.get("lot_surveyed") else " (approx.)"
    o.edge_labels = [(_model_point(doc, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)), e["length"] + approx)
                     for e in plan.get("edges") or [] for a, b in [e["points"]]]
    o.yard_dims =[(rg.Line(_model_point(doc, y["points"][0], 0.1), _model_point(doc, y["points"][1], 0.1)),
                    y["label"], y["status"]) for y in plan.get("yards") or [] if y.get("points")]
    o.encroach = [b for b in (_prism(doc, e["outline"], e["base"], e["top"]) for e in plan.get("encroach") or [])
                  if b is not None]
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
        _draw_plan(doc, o, result, sent)
        STATE["statuses_by_doc"][doc.RuntimeSerialNumber] = result["statuses"]
        STATE["last"] = {"summary": result["summary"], "view_summary": view["summary"], "state": view["state"],
                         "rows": [{k: r.get(k) for k in ("Requirement", "Table limit", "Proposed", "Units",
                                                          "Error", "Rule id", "Why", "Provisional")}
                                  for r in result["rows"]],
                         "items": [{k: i.get(k) for k in ("id", "name", "status", "proposed", "required", "margin",
                                                          "reason", "group")} for i in view["items"]],
                         "header": head, "interior": [r["Rule id"] for r in result.get("interior", [])],
                         "encroach": len(o.encroach), "plan_encroach": len((result.get("plan") or {}).get("encroach") or []),
                         "envelope": result.get("envelope"), "at": time.time()}
        STATE.setdefault("checked_at", {})[doc.RuntimeSerialNumber] = time.time()     # a real check, of this document
        if result.get("notice"):
            STATE.setdefault("toasts", []).append([result["notice"]])
            if not STATE.get("headless"):
                _toast([result["notice"]])
        if not STATE.get("headless"):
            ui.show(panel(), view)
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
        hook = _handler(System.EventHandler[Rhino.Commands.CommandEventArgs],
                        logic.guard(lambda s, e: _clear_toast(), "clear the notice"))
        _on(Rhino.Commands.Command, "BeginCommand", hook)
        STATE["command_hook"] = hook
    timer = STATE.get("toast_timer")
    if timer is None:
        timer = ef.UITimer()
        timer.Interval = 0.5
        timer.Elapsed += logic.guard(logic.current_only(lambda s, e: _toast_tick(), _is_current), "time the notice")
        STATE["toast_timer"] = timer
        LEFTOVERS["toast_timer"] = timer.Stop            # a later copy of this script stops it
    timer.Start()
    Rhino.RhinoDoc.ActiveDoc.Views.Redraw()


def _toast_tick():
    o = overlay()
    if getattr(o, "toast", None) and time.time() >= o.toast[1]:
        _clear_toast()


def _clear_toast():
    o = overlay()
    if getattr(o, "toast", None):
        o.toast = None
        if STATE.get("toast_timer"):
            STATE["toast_timer"].Stop()
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()


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
        ui.show(p, None, error="no check yet for this document (run GordiumCheck)")
    STATE["dirty"] = time.time()        # re-check the document now in front, if it has lot facts


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
    if t and time.time() - t >= ui.STALE_SECONDS and STATE.get("stale_shown") != t and p is not None \
            and p["form"].Visible:          # out of date: no marks until the re-check (H1, F7)
        STATE["stale_shown"] = t
        ui.show(p, None, checking=True)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
    if logic.should_recheck(t, time.time(), STATE.get("running"), _box_open(), IDLE_SECONDS, last_at):
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
        new_doc = _handler(System.EventHandler[Rhino.DocumentEventArgs], logic.guard(_new_document, "follow a new document"))
        opened = _handler(System.EventHandler[Rhino.DocumentOpenEventArgs], logic.guard(_opened, "follow an opened document"))
        active = _handler(System.EventHandler[Rhino.DocumentEventArgs], logic.guard(_new_document, "follow the active document"))
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
    """Re-check after each edit: objects added, deleted, moved or changed, a layer change or hiding one
    (attributes)."""
    _unhook()
    STATE["live"] = on
    if not on:
        return
    objects = _handler(System.EventHandler[Rhino.DocObjects.RhinoObjectEventArgs], logic.guard(_changed, "notice an edit"))
    replaced = _handler(System.EventHandler[Rhino.DocObjects.RhinoReplaceObjectEventArgs], logic.guard(_changed, "notice an edit"))
    attributes = _handler(System.EventHandler[Rhino.DocObjects.RhinoModifyObjectAttributesEventArgs], logic.guard(_changed, "notice an edit"))
    idle = _handler(System.EventHandler, logic.guard(_idle, "re-check after an edit"))
    for name in ("AddRhinoObject", "DeleteRhinoObject", "UndeleteRhinoObject"):
        _on(Rhino.RhinoDoc, name, objects)
    _on(Rhino.RhinoDoc, "ReplaceRhinoObject", replaced)
    _on(Rhino.RhinoDoc, "ModifyObjectAttributes", attributes)
    _on(Rhino.RhinoApp, "Idle", idle)
    STATE["hooks"] = (objects, replaced, attributes, idle)


def toggle_live():
    live(not STATE.get("live"))
    Rhino.RhinoApp.WriteLine("Gordium live mode " + ("on" if STATE["live"] else "off"))


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
    opened, why = True, None
    try:
        if os.name == "nt":
            os.startfile(path)
        else:
            done = subprocess.run(["open", path], capture_output=True, text=True, timeout=20, encoding="utf-8")
            opened, why = done.returncode == 0, (done.stderr or "").strip()[:160] or None
    except Exception as e:
        opened, why = False, str(e)[:160]
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
    live(True)                                      # live mode is on by default
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
        _save_ui_state(doc, dict(_ui_state(doc), from_sample=True, replaceable_lot=sample_lot))
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
        Rhino.RhinoApp.WriteLine("Gordium: no starting building could be drawn")
        live(True)                   # the architect draws one; it is checked as they go
        documents(True)
        return None
    if Rhino.RhinoDoc.ActiveDoc is None or Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber != doc.RuntimeSerialNumber:
        Rhino.RhinoApp.WriteLine("Gordium: the document in front changed while the box was open; nothing was drawn "
                                 "(run GordiumStart again in " + _doc_name(doc) + ")")
        return None
    Rhino.RhinoApp.WriteLine("Gordium: drawing in " + _doc_name(doc))
    if add_floors(doc, start) is None:
        Rhino.RhinoApp.WriteLine("Gordium: the starting building couldn't be drawn; draw one and Gordium will check it")
        live(True)
        documents(True)
        return None
    fact = logic.starting_house_fact(start.get("margin_note"), time.strftime("%Y-%m-%d"))   # Gordium's figure
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


def _doc_name(doc):
    """The document as the architect knows it: its file name, or "the untitled document"."""
    return os.path.basename(doc.Path) if doc.Path else (doc.Name or "the untitled document")


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
    except Exception:
        pass
    finally:
        doc.Objects.UnselectAll()
        for i in picked:
            doc.Objects.Select(i)
    doc.Views.Redraw()
