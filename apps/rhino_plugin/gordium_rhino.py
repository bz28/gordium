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

LAYERS = logic.LAYERS
ID_KEY = "gordium:id"
SECTION, ENTRY = "Gordium", "lot_facts"
UI_ENTRY = "ui"                              # the start box's own choices (district confirmed, grade source…)
GRADE_LAYER = "Gordium::Grade"               # spot grades: point objects the architect places
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
        env["PYTHONPATH"] = os.pathsep.join(STATE.get("extra_paths", []) + [
            os.path.join(packages, n) for n in sorted(os.listdir(packages)) if os.path.isdir(os.path.join(packages, n))])
        log = open(os.path.join(tempfile.gettempdir(), "gordium_worker.log"), "a")
        p = subprocess.Popen([_python(), "-u", "-m", "design_checker", "serve"], cwd=REPO, env=env,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, universal_newlines=True)
        STATE["worker"] = p
        STATE["worker_code"] = now
    return p


def ask(request):
    """Send one request to the checker and wait for its answer."""
    p = _worker()
    STATE["next_id"] = STATE.get("next_id", 0) + 1
    request = dict(request, id=STATE["next_id"])
    p.stdin.write(json.dumps(request) + "\n")
    p.stdin.flush()
    line = p.stdout.readline()
    if not line:
        STATE.pop("worker", None)
        raise RuntimeError("the Gordium checker stopped (see gordium_worker.log in the temp folder)")
    answer = json.loads(line)
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
    lot, its lowest line on the screen (the bottom of the Top view) as the street side, not a corner lot (one
    street line), flat ground at the lowest point of the buildings, the lot not from a survey (the safe answer:
    lot size and coverage wait for one), the first zone with rules, a detached one-family house, and the largest
    solid as the main building. Every one is shown in the dialog; nothing is used until the architect says OK.
    In feet, whatever the model's units."""
    facts = {"jurisdiction": JURISDICTION, "zone": zones[0] if zones else None, "use": "one_family_detached",
             "corner_lot": False, "ground_is_flat": True, "lot_surveyed": False}
    lots, buildings, _ = _sorted_objects(doc)
    if lots:
        lot = max(lots, key=lambda o: _area(o.Geometry))
        facts["lot_id"] = str(lot.Id)
        a, b = min(_segments(lot.Geometry), key=lambda s: (s[0].Y + s[1].Y) / 2)
        facts["street_line"] = [[[a.X, a.Y], [b.X, b.Y]]]
    boxes = [o.Geometry.GetBoundingBox(True) for o in buildings]
    lot_z = max(lots, key=lambda o: _area(o.Geometry)).Geometry.GetBoundingBox(True).Min.Z if lots else None
    ground = logic.suggested_ground([b.Min.Z for b in boxes], lot_z)
    if ground is not None:
        facts["grade_elevation"] = ground
    if buildings:
        if len(buildings) > 1:
            big = max(zip(buildings, boxes), key=lambda ob: ob[1].Diagonal.X * ob[1].Diagonal.Y * ob[1].Diagonal.Z)
            facts["main_building"] = str(big[0].Id)
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


def _model_point(doc, p, z=0.0):
    """A point in feet (from the facts or the checker), in the model's units."""
    k = 1.0 / _scale(doc)
    return rg.Point3d(p[0] * k, p[1] * k, z * k)


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
    taken = []                               # labels drawn this frame: none covers another
    plan = not e.Viewport.IsPerspectiveProjection   # labels only in plan-like views: in 3D they sit on the massing
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
    state, text, lines = o.message
    if old:                                  # out of date: neutral, no status (F7)
        state, text, lines = "stale", "Checking… (the model changed)", lines[:1]
    color = ui.status_color({"does_not_comply": "does_not_comply", "needs_review": "needs_review"}.get(state, "complies"),
                            dark)
    mark = {"does_not_comply": "✕", "needs_review": "?"}.get(state, "")    # never ✓ (D3), and "–" means not checked
    rows = ["Gordium · " + (mark + " " if mark else "") + text] + list(lines)[:3]
    width = max(len(r) for r in rows) * 13 * 0.6 + 22
    ui.draw_text_box(d, rows, color, int(e.Viewport.Bounds.Width) - width - 14, 14, dark, 13)


def overlay():
    """The one drawing layer (its drawing code is always this script's current functions, see Overlay)."""
    o = STATE.get("overlay")
    if o is None:
        o = Overlay()
        STATE["overlay"] = o
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
    z = lot.Geometry.GetBoundingBox(True).Min.Z * _scale(doc)
    return dict(env, base=z, top=z + env["height"])


def _envelope_brep(doc, env):
    """The envelope (in feet, from the checker) as a solid in the model's units."""
    if not env or not env.get("outline") or env.get("top") is None or env.get("base") is None:
        return None
    k = 1.0 / _scale(doc)
    base, top = env["base"] * k, env["top"] * k
    pts = [rg.Point3d(x * k, y * k, base) for x, y in env["outline"]]
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
    k = 1.0 / _scale(doc)
    pts = [rg.Point3d(x * k, y * k, base * k) for x, y in outline]
    pts.append(pts[0])
    line = rg.Polyline(pts)
    line.DeleteShortSegments(doc.ModelAbsoluteTolerance)   # an edge shorter than that can't be extruded
    if line.Count < 4:
        return None
    curve = rg.PolylineCurve(line)
    ext = rg.Extrusion.Create(curve, (base - top) * k, True)   # extrudes along -normal: sign by winding
    brep = ext.ToBrep() if ext else None
    if brep is not None and brep.GetBoundingBox(True).Max.Z < top * k - 1e-6:
        brep = rg.Extrusion.Create(curve, (top - base) * k, True).ToBrep()
    return brep


def _actions():
    """What the panel's buttons do (gordium_ui.make_panel)."""
    return {"zoom": zoom_to, "report": open_report, "envelope": set_envelope, "edit_site": edit_facts,
            "survey": pick_survey, "grade": set_grade, "enter": enter_rooms, "add": add_to_check, "legend": ui.legend,
            "retry": lambda: run_check(Rhino.RhinoDoc.ActiveDoc, report=False)}


def panel():
    """The Gordium panel, made once and shown. (A floating panel: a docked one needs a Rhino plugin package.)"""
    p = STATE.get("panel_parts")
    if p is None or not p["form"].Visible:
        p = ui.make_panel(_actions())
        STATE["panel_parts"] = p
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
        return
    box = rg.BoundingBox.Empty
    for i in item.get("objects") or []:
        o = _find(doc, i)
        if o is not None:
            box.Union(o.Geometry.GetBoundingBox(True))
    for p in item.get("points") or []:
        box.Union(_model_point(doc, p))
    if not box.IsValid:
        return
    box.Inflate(max(box.Diagonal.Length * 0.25, 5 / _scale(doc)))
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
    doc.Strings.SetString(SECTION, UI_ENTRY, json.dumps(state))


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
        return
    if picked:
        facts = logic.after_lot_pick(facts, picked) if picked != facts.get("lot_id") else facts
        facts["lot_surveyed"] = True
        save_facts(doc, facts)
    run_check(doc, report=False)


def _grade_points(doc):
    """Spot grades: the point objects on Gordium::Grade, in feet."""
    k = _scale(doc)
    index = doc.Layers.FindByFullPath(GRADE_LAYER, -1)
    if index < 0:
        return []
    return [[o.Geometry.Location.X * k, o.Geometry.Location.Y * k, o.Geometry.Location.Z * k]
            for o in doc.Objects.FindByLayer(doc.Layers[index]) or [] if isinstance(o.Geometry, rg.Point)]


def _terrain_points(doc, terrain_id):
    """The terrain sampled just outside each wall of each building, every time the check runs: so the grade
    follows the building when it moves (C4). Feet."""
    terrain = _find(doc, terrain_id or "")
    if terrain is None:
        return []
    k = _scale(doc)
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
            probe = mid + out_dir * (1.0 / k)          # 1 ft outside the wall
            hit = _down_onto(terrain.Geometry, probe)
            if hit is not None:
                out.append([hit.X * k, hit.Y * k, hit.Z * k])
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
        return
    save_facts(doc, logic.update_counts(facts, answers))
    run_check(doc, report=False)


def add_to_check(ids):
    """Add to check…: objects on the lot that aren't measured go on the Building layer, so every rule measures
    them."""
    doc = Rhino.RhinoDoc.ActiveDoc
    index = _layer(doc, LAYERS["building"])
    for i in ids or []:
        o = _find(doc, i)
        if o is not None:
            attrs = o.Attributes.Duplicate()
            attrs.LayerIndex = index
            doc.Objects.ModifyAttributes(o, attrs, True)
    run_check(doc, report=False)


def _not_included(doc, lot):
    """Closed solids and meshes standing on the lot that no rule measures (not on the Building layer, nor the
    Site or Gordium layers): each one makes the check need review (C8)."""
    if lot is None:
        return []
    box = lot.Geometry.GetBoundingBox(True)
    out = []
    every = Rhino.DocObjects.ObjectEnumeratorSettings()          # hidden and locked too, as for the Building layer:
    every.NormalObjects, every.LockedObjects, every.HiddenObjects = True, True, True   # a hidden shed still counts
    terrain = str(_ui_state(doc).get("terrain_id") or "")
    for o in doc.Objects.GetObjectList(every):
        layer = doc.Layers[o.Attributes.LayerIndex].FullPath
        g = o.Geometry
        # anything that could be a building: a solid, a closed mesh, a SubD, a polysurface (open ones too: a garage
        # missing a face is still a garage), a block. Not the lot, the terrain, Gordium's own drawing, the Building
        # layer (measured), curves, points and single flat surfaces.
        could_be = logic.could_be_building(
            type(g).__name__, (isinstance(g, rg.Brep) and g.IsSolid) or (isinstance(g, rg.Mesh) and g.IsClosed),
            g.Faces.Count if isinstance(g, (rg.Brep, rg.Mesh)) else 0)
        if not could_be or str(o.Id) == terrain or logic.on_layer(layer, LAYERS["building"]) \
                or logic.on_layer(layer, "Gordium"):
            continue
        c = g.GetBoundingBox(True).Center
        if box.Min.X <= c.X <= box.Max.X and box.Min.Y <= c.Y <= box.Max.Y:
            out.append(str(o.Id))
    return out


def _extras(doc, facts):
    """What the panel needs to say about the check beyond the measurements: what was sent (C8), objects on the
    lot left out, the use's name."""
    buildings = _buildings(doc)
    groups = {i for o in buildings for i in (o.Attributes.GetGroupList() or [])}
    layers = sorted({doc.Layers[o.Attributes.LayerIndex].FullPath for o in buildings})
    left_out = _not_included(doc, _find(doc, facts.get("lot_id") or ""))
    return {"scope": {"groups": len(groups), "solids": len(buildings), "layer": ", ".join(layers)},
            "not_included": left_out, "touching": _touching(doc, left_out, buildings)}


def _touching(doc, ids, buildings):
    """The left-out solids that may be part of the building: their box within 0.1 ft of a building's box. Boxes
    say "touching" more often than the shapes do, which only ever makes the check more cautious."""
    gap = 0.1 / _scale(doc)
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


def _feet(text, default):
    """11'-8" or 11.5 (feet) -> feet; anything unreadable -> default."""
    import re
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*'?\s*(?:-?\s*(\d+(?:\.\d+)?)\s*\"?)?\s*$", text or "")
    if not m:
        return default
    return float(m.group(1)) + (float(m.group(2)) / 12 if m.group(2) else 0.0)


def _box_state(doc, facts, options, saved_ui):
    """The start box's fields from the facts and the box's own saved choices."""
    k = _scale(doc)
    lines = facts.get("street_line") or []
    length = sum(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for a, b in lines)
    # the facts the check uses decide what the box shows (set from the panel too, not only from the box)
    grade = facts.get("grade_from") if facts.get("grade_from") in ("spot", "terrain") else \
        "not_set" if facts.get("grade_elevation") is None else (saved_ui.get("grade") or "not_set")
    spots = len(_grade_points(doc))
    return {"address": facts.get("address") or "", "zone": facts.get("zone"),
            "district_confirmed": bool(saved_ui.get("district_confirmed")), "use": facts.get("use"),
            "street": ("the highlighted line · " + _ft_text(length) + (" (approx.)" if not facts.get("lot_surveyed") else "")
                       + " · " + ("corner lot" if facts.get("corner_lot") else "interior lot")) if lines else "",
            "lot_source": "survey" if facts.get("lot_surveyed") else "tax_map",
            "lot_picked": "1 curve picked" if facts.get("lot_id") else "none picked",
            "grade": grade, "grade_is": facts.get("grade_is") or "finished",
            "grade_result": (str(spots) + " spot grades" if grade == "spot" else
                             "1 surface picked" if grade == "terrain" and saved_ui.get("terrain_id") else ""),
            "floor_to_floor": saved_ui.get("floor_to_floor") or "11'-8\"", "massing": saved_ui.get("massing") or "both",
            "preview": saved_ui.get("preview") or "", "_scale": k}


def _ft_text(feet):
    inches = int(round(feet * 12 * 8))            # to 1/8 in
    ft, rest = divmod(inches, 96)
    whole, eighth = divmod(rest, 8)
    return "%d'-%d%s\"" % (ft, whole, (" %d/8" % eighth) if eighth else "")


def _apply_box(doc, facts, state, saved_ui):
    """The facts and the box's own choices from what the box says."""
    facts = dict(facts, address=state["address"] or None, zone=state["zone"], use=state["use"],
                 lot_surveyed=state["lot_source"] == "survey", grade_is=state["grade_is"])
    if not facts.get("address"):
        facts.pop("address")
    for key in ("grade_points", "grade_from"):
        facts.pop(key, None)
    if state["grade"] == "not_set":                 # no grade: height and stories wait for one
        facts.pop("ground_is_flat", None)
        facts.pop("grade_elevation", None)
    else:
        facts["grade_from"] = state["grade"]        # the points are read (or sampled) at every check
        facts.pop("ground_is_flat", None)
        facts.pop("grade_elevation", None)
    saved_ui = dict(saved_ui, district_confirmed=state["district_confirmed"], grade=state["grade"],
                    floor_to_floor=state["floor_to_floor"], massing=state["massing"])
    return facts, saved_ui


def _box_pick(doc, what, facts, saved_ui):
    """One pick the start box asked for, with the box hidden (A1). Esc or Enter: nothing changes."""
    scale = _scale(doc)
    try:
        if what == "street":
            lot = _find(doc, facts.get("lot_id") or "")
            if lot is not None:
                rc, point = Rhino.Input.RhinoGet.GetPoint("Click the lot line on the street", True)
                if rc == Rhino.Commands.Result.Success:
                    a, b = min(_segments(lot.Geometry), key=lambda s: rg.Line(s[0], s[1]).DistanceTo(point, True))
                    facts["street_line"] = [[[a.X * scale, a.Y * scale], [b.X * scale, b.Y * scale]]]
        elif what == "lot":
            lots = _lot_candidates(doc)
            picked = _pick(doc, "Click the lot outline (a closed curve on the Site layer); Enter keeps it", lots, "Lot",
                           Rhino.DocObjects.ObjectType.Curve)
            if picked:
                facts = logic.after_lot_pick(facts, picked)
        elif what == "terrain":
            go = Rhino.Input.Custom.GetObject()
            go.SetCommandPrompt("Click the terrain surface or mesh")
            go.GeometryFilter = Rhino.DocObjects.ObjectType.Surface | Rhino.DocObjects.ObjectType.PolysrfFilter | \
                Rhino.DocObjects.ObjectType.Mesh
            if go.Get() == Rhino.Input.GetResult.Object:
                saved_ui["terrain_id"] = str(go.Object(0).ObjectId)
                saved_ui["grade"] = "terrain"
        elif what == "spot":
            layer = _layer(doc, GRADE_LAYER)
            while True:                              # each click places a spot grade; Enter when done
                rc, point = Rhino.Input.RhinoGet.GetPoint("Click a spot grade at a wall (Enter when done)", True)
                if rc != Rhino.Commands.Result.Success:
                    break
                attrs = Rhino.DocObjects.ObjectAttributes()
                attrs.LayerIndex = layer
                doc.Objects.AddPoint(point, attrs)
                doc.Views.Redraw()
            saved_ui["grade"] = "spot"
    finally:
        _highlight(doc, facts)
    return facts, saved_ui


def confirm(doc, facts, options, mode="check"):
    """The start box (A1–A13), prefilled. Draw (or Check) keeps the facts once the district is confirmed; a pick
    closes the box, picks in the model, and shows the box again with the result; closing it (or Esc) saves
    nothing (None)."""
    o = overlay()
    _clear(o)                           # facts are being set: no earlier result (of any model) stays shown
    o.message = None
    _highlight(doc, facts)
    saved_ui = _ui_state(doc)
    try:
        if STATE.get("auto_ok"):          # scripted runs (tests, the demo): accept the prefilled facts
            state = _box_state(doc, facts, options, saved_ui)
            state["district_confirmed"] = True
            if STATE.get("on_confirm"):   # ...after recording what the box shows (the demo captures it)
                STATE["on_confirm"](doc, facts, _describe(facts, options["uses"]), state)
            facts, saved_ui = _apply_box(doc, facts, dict(state, **(STATE.get("box_overrides") or {})), saved_ui)
            _save_ui_state(doc, saved_ui)
            return facts
        while True:
            state = _box_state(doc, facts, options, saved_ui)
            state["_on_shown"] = STATE.get("on_box_shown")     # the dialog capture in the in-Rhino test
            what = ui.start_box(state, options, mode)
            if what is None:
                return None
            facts, saved_ui = _apply_box(doc, facts, state, saved_ui)
            if what == "draw":
                _save_ui_state(doc, saved_ui)
                return facts
            facts, saved_ui = _box_pick(doc, what.split(":", 1)[1], facts, saved_ui)
    finally:
        o.confirm = None
        o.labels = []
        doc.Views.Redraw()


class Cancelled(Exception):
    """Esc at a prompt: the whole edit is cancelled and nothing is saved (Enter keeps what is there)."""


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
    scale = _scale(doc)
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
            line = [[a.X * scale, a.Y * scale], [b.X * scale, b.Y * scale]]
            if line not in picked:
                picked.append(line)
            if not facts.get("corner_lot"):
                break
        if picked:
            facts["street_line"] = picked
        _highlight(doc, facts)
    facts["ground_is_flat"] = _yes_no("Is the ground flat?", facts.get("ground_is_flat"))
    ground = Rhino.Input.RhinoGet.GetNumber("Ground level (z, in model units)", True,
                                            (facts.get("grade_elevation") or 0.0) / scale)
    _go_on(ground[0])
    if ground[0] == Rhino.Commands.Result.Success:
        facts["grade_elevation"] = ground[1] * scale
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
    if facts.get("grade_from") == "spot":
        points = _grade_points(doc)
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
    k = 1.0 / _scale(doc)
    lot = _find(doc, facts.get("lot_id") or "")
    if lot is not None:
        ok, poly = lot.Geometry.TryGetPolyline()
        o.lot_outline = list(poly) if ok else None
    approx = "" if facts.get("lot_surveyed") else " (approx.)"
    o.edge_labels = [(rg.Point3d((a[0] + b[0]) / 2 * k, (a[1] + b[1]) / 2 * k, 0), e["length"] + approx)
                     for e in plan.get("edges") or [] for a, b in [e["points"]]]
    o.yard_dims =[(rg.Line(_model_point(doc, y["points"][0], 0.1), _model_point(doc, y["points"][1], 0.1)),
                    y["label"], y["status"]) for y in plan.get("yards") or [] if y.get("points")]
    o.encroach = [b for b in (_prism(doc, e["outline"], e["base"], e["top"]) for e in plan.get("encroach") or [])
                  if b is not None]
    o.yards_zone = None
    if lot is not None and plan.get("buildable"):
        inner = rg.PolylineCurve([rg.Point3d(x * k, y * k, 0) for x, y in plan["buildable"] + plan["buildable"][:1]])
        zone = rg.Brep.CreatePlanarBreps([lot.Geometry, inner], doc.ModelAbsoluteTolerance)
        o.yards_zone = zone[0] if zone else None
    o.grade_points = [_model_point(doc, p[:2], p[2]) for p in facts.get("grade_points") or []]


def run_check(doc, report=True):
    """Measure and check the model now; draw the result; update the panel. If the check can't run, the old
    result is cleared from the view and the panel says why, with Retry (H2): never left showing."""
    if STATE.get("running"):
        return None
    o = overlay()
    facts = {}
    try:
        STATE["running"] = True
        facts = current_facts(doc)
        if logic.missing(facts):
            raise ValueError("lot facts missing: " + ", ".join(logic.missing(facts)) + " (run GordiumCheck)")
        path = os.path.join(tempfile.gettempdir(), "gordium_live_" + str(doc.RuntimeSerialNumber) + ".3dm")
        problems = export(doc, path)
        sent = check_facts(doc, facts)
        extras = _extras(doc, facts)
        extras["before"] = STATE.setdefault("statuses_by_doc", {}).get(doc.RuntimeSerialNumber)
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
        if result.get("notice"):
            STATE.setdefault("toasts", []).append([result["notice"]])
            if not STATE.get("headless"):
                _toast([result["notice"]])
        if not STATE.get("headless"):
            ui.show(panel(), view)
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
        hook = System.EventHandler[Rhino.Commands.CommandEventArgs](logic.guard(lambda s, e: _clear_toast(), "clear the notice"))
        Rhino.Commands.Command.BeginCommand += hook
        STATE["command_hook"] = hook
    timer = STATE.get("toast_timer")
    if timer is None:
        timer = ef.UITimer()
        timer.Interval = 0.5
        timer.Elapsed += logic.guard(lambda s, e: _toast_tick(), "time the notice")
        STATE["toast_timer"] = timer
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
    p = STATE.get("panel_parts")
    if t and time.time() - t >= ui.STALE_SECONDS and STATE.get("stale_shown") != t and p is not None \
            and p["form"].Visible:          # out of date: no marks until the re-check (H1, F7)
        STATE["stale_shown"] = t
        ui.show(p, None, checking=True)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
    if t and time.time() - t >= IDLE_SECONDS and not STATE.get("running"):
        STATE["dirty"] = None
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is not None and doc.Strings.GetValue(SECTION, ENTRY):    # checked before: run_check says why
            run_check(doc, report=False)


def documents(on):
    """Hooks for another document coming to the front (new, opened, switched to); on while Gordium is."""
    hooks = STATE.pop("doc_hooks", None)
    if hooks:
        new_doc, opened, active = hooks
        Rhino.RhinoDoc.NewDocument -= new_doc
        Rhino.RhinoDoc.EndOpenDocument -= opened
        Rhino.RhinoDoc.ActiveDocumentChanged -= active
    if on:
        new_doc = System.EventHandler[Rhino.DocumentEventArgs](logic.guard(_new_document, "follow a new document"))
        opened = System.EventHandler[Rhino.DocumentOpenEventArgs](logic.guard(_opened, "follow an opened document"))
        active = System.EventHandler[Rhino.DocumentEventArgs](logic.guard(_new_document, "follow the active document"))
        Rhino.RhinoDoc.NewDocument += new_doc
        Rhino.RhinoDoc.EndOpenDocument += opened
        Rhino.RhinoDoc.ActiveDocumentChanged += active
        STATE["doc_hooks"] = (new_doc, opened, active)


def _unhook():
    hooks = STATE.pop("hooks", None)
    if hooks and len(hooks) == 3:            # set by an earlier version of this script, before a reload
        hooks = (hooks[0], hooks[1], None, None, None, hooks[2])
    if hooks and len(hooks) == 6:            # also an earlier version: the document hooks were here
        objects, replaced, attributes, new_doc, opened, idle = hooks
        if attributes is not None:
            Rhino.RhinoDoc.NewDocument -= new_doc
            Rhino.RhinoDoc.EndOpenDocument -= opened
        hooks = (objects, replaced, attributes, idle)
    if hooks:
        objects, replaced, attributes, idle = hooks
        if attributes is not None:
            Rhino.RhinoDoc.ModifyObjectAttributes -= attributes
        Rhino.RhinoDoc.AddRhinoObject -= objects
        Rhino.RhinoDoc.DeleteRhinoObject -= objects
        Rhino.RhinoDoc.UndeleteRhinoObject -= objects
        Rhino.RhinoDoc.ReplaceRhinoObject -= replaced
        Rhino.RhinoApp.Idle -= idle


def live(on):
    """Re-check after each edit: objects added, deleted, moved or changed, a layer change or hiding one
    (attributes)."""
    _unhook()
    STATE["live"] = on
    if not on:
        return
    objects = System.EventHandler[Rhino.DocObjects.RhinoObjectEventArgs](logic.guard(_changed, "notice an edit"))
    replaced = System.EventHandler[Rhino.DocObjects.RhinoReplaceObjectEventArgs](logic.guard(_changed, "notice an edit"))
    attributes = System.EventHandler[Rhino.DocObjects.RhinoModifyObjectAttributesEventArgs](logic.guard(_changed, "notice an edit"))
    idle = System.EventHandler(logic.guard(_idle, "re-check after an edit"))
    Rhino.RhinoDoc.AddRhinoObject += objects
    Rhino.RhinoDoc.DeleteRhinoObject += objects
    Rhino.RhinoDoc.UndeleteRhinoObject += objects
    Rhino.RhinoDoc.ReplaceRhinoObject += replaced
    Rhino.RhinoDoc.ModifyObjectAttributes += attributes
    Rhino.RhinoApp.Idle += idle
    STATE["hooks"] = (objects, replaced, attributes, idle)


def toggle_live():
    live(not STATE.get("live"))
    Rhino.RhinoApp.WriteLine("Gordium live mode " + ("on" if STATE["live"] else "off"))


def toggle_envelope():
    STATE["envelope_on"] = not STATE.get("envelope_on", True)
    run_check(Rhino.RhinoDoc.ActiveDoc, report=False)


def open_report():
    path = report_path(Rhino.RhinoDoc.ActiveDoc)
    if os.path.exists(path):
        if os.name == "nt":
            os.startfile(path)
        else:
            subprocess.Popen(["open", path])


def off():
    _unhook()
    documents(False)
    hook = STATE.pop("command_hook", None)
    if hook is not None:
        Rhino.Commands.Command.BeginCommand -= hook
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
    Rhino.RhinoDoc.ActiveDoc.Views.Redraw()


# ---- GordiumCheck ----------------------------------------------------------------------------------------

def gordium_check():
    """Confirm the lot facts whenever any required one is missing (keeping what is saved), then check."""
    doc = Rhino.RhinoDoc.ActiveDoc
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
    k = 1.0 / _scale(doc)
    breps = []
    for floor in start["floors"]:
        corners = [rg.Point3d(x * k, y * k, z * k) for z in (floor["base"], floor["top"]) for x, y in floor["outline"]]
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


def _preview(start, facts):
    """The start box's preview line (A11): "Starting massing (on tax-map lot): 1 group of 3 floor solids · 35'-0" ·
    53'-0" × 30'-11" · 1,639 sf, 24.95% coverage". Every number is the checker's own text (present.py), so it
    reads the same as the panel (coverage, a maximum, rounded up)."""
    p = start.get("preview")
    if not p:
        return "No starting massing on this lot shape: draw one and Gordium will check it"
    where = "on tax-map lot" if not facts.get("lot_surveyed") else "on the surveyed lot"
    return ("Starting massing (" + where + "): 1 group of " + str(p["floors"]) + " floor solids · " + p["height"] +
            " · " + p["size"] + (" · " + p["area"] if p.get("area") else "") +
            (", " + p["coverage"] + (" of " + p["limit"] if p.get("limit") else " coverage") if p.get("coverage") else ""))


def gordium_start():
    """A new project: the prefilled facts (address, building type, zone, street side) for the architect to confirm,
    then the lot and the largest legal starting building as stacked floors, checked, with live mode on. Starts
    from a model with no building in it (an existing design is checked with GordiumCheck)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if _buildings(doc):
        Rhino.RhinoApp.WriteLine("Gordium: this model already has a building; GordiumStart begins from an empty lot "
                                 "(use GordiumCheck to check a design)")
        return None
    options = ask({"cmd": "options", "jurisdiction": JURISDICTION})
    if not _lot_candidates(doc):        # an empty model: the sample project, its lot and its facts, prefilled
        sample = ask({"cmd": "sample_site"})
        _add_lot(doc, sample)
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
    export(doc, path)
    saved_ui = _ui_state(doc)
    try:                                 # the box's preview line; the box still opens if it can't be worked out
        saved_ui["preview"] = _preview(ask({"cmd": "start", "model": path, "facts": facts,
                                            "floor_to_floor": _feet(saved_ui.get("floor_to_floor"), None)}), facts)
    except Exception as e:
        saved_ui["preview"] = "No preview yet (" + str(e)[:80] + ")"
    _save_ui_state(doc, saved_ui)
    facts = confirm(doc, facts, options, "start")
    if facts is None:
        Rhino.RhinoApp.WriteLine("Gordium: nothing was started (the facts weren't confirmed)")
        return None
    save_facts(doc, facts)
    saved_ui = _ui_state(doc)
    if saved_ui.get("massing") == "envelope":        # envelope only: the site and the envelope, no massing
        result = run_check(doc, report=False)
        live(True)
        documents(True)
        Rhino.RhinoApp.WriteLine("Gordium: drew the site and the buildable envelope (no massing)")
        return result
    start = ask({"cmd": "start", "model": path, "facts": check_facts(doc, facts),
                 "floor_to_floor": _feet(saved_ui.get("floor_to_floor"), None)})
    STATE["start"] = {k: start.get(k) for k in ("stories", "height", "area", "coverage_allowed", "notes", "floors")}
    for note in start.get("notes") or []:
        Rhino.RhinoApp.WriteLine("Gordium: " + note)
    if not start.get("floors"):
        Rhino.RhinoApp.WriteLine("Gordium: no starting building could be drawn")
        live(True)                   # the architect draws one; it is checked as they go
        documents(True)
        return None
    if add_floors(doc, start) is None:
        Rhino.RhinoApp.WriteLine("Gordium: the starting building couldn't be drawn; draw one and Gordium will check it")
        live(True)
        documents(True)
        return None
    doc.Views.Redraw()
    result = run_check(doc, report=False)
    live(True)
    documents(True)
    Rhino.RhinoApp.WriteLine("Gordium: created 1 group (" + str(len(start["floors"])) + " floor solids) on " +
                             logic.MASSING)
    return result
