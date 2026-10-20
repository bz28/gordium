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

LAYERS = logic.LAYERS
ID_KEY = "gordium:id"
SECTION, ENTRY = "Gordium", "lot_facts"
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
        sys.modules[__name__].cull(self, e)

    def CalculateBoundingBox(self, e):
        sys.modules[__name__].bounds(self, e)

    def PostDrawObjects(self, e):
        sys.modules[__name__].draw_scene(self, e)

    def DrawForeground(self, e):
        sys.modules[__name__].draw_screen(self, e)


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


def draw_scene(o, e):
    if not _here(o, e):
        return
    d = e.Display
    for g in o.red:                          # failing solids, in red
        if isinstance(g, rg.Mesh):
            d.DrawMeshShaded(g, Rhino.Display.DisplayMaterial(RED, 0.1))
            d.DrawMeshWires(g, System.Drawing.Color.Black)
        else:
            d.DrawBrepShaded(g, Rhino.Display.DisplayMaterial(RED, 0.1))
            d.DrawBrepWires(g, System.Drawing.Color.Black, 1)
    if o.envelope is not None:               # see-through, drawn after the solids so they show through it
        d.DrawBrepShaded(o.envelope, Rhino.Display.DisplayMaterial(BLUE, 0.85))
        d.DrawBrepWires(o.envelope, BLUE, 2)
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
    for line, label in o.dims:               # each failing distance: the line it was measured along, on top
        a, b = e.Viewport.WorldToClient(line.From), e.Viewport.WorldToClient(line.To)
        d.Draw2dLine(System.Drawing.PointF(a.X, a.Y), System.Drawing.PointF(b.X, b.Y), RED, 4)
        for p in (a, b):
            d.Draw2dRectangle(System.Drawing.Rectangle(int(p.X) - 4, int(p.Y) - 4, 8, 8), RED, 1, RED)
        # the label beside the lot-line end, on a white card, clear of the building's edges
        width = len(label) * 8 + 16
        x, y = int(a.X) - width - 12 if a.X <= b.X else int(a.X) + 12, int(a.Y) - 30
        d.Draw2dRectangle(System.Drawing.Rectangle(x, y, width, 24), RED, 1, System.Drawing.Color.White)
        d.Draw2dText(label, RED, rg.Point2d(x + 8, y + 4), False, 14)
    toast = getattr(o, "toast", None)
    active = Rhino.RhinoDoc.ActiveDoc.Views.ActiveView
    if toast and time.time() < toast[1] and active is not None and e.Viewport.Id == active.ActiveViewportID:
        rows = ["✕ " + line for line in toast[0]]         # bottom left, active view only
        width = max(len(row) for row in rows) * 8 + 28
        x, y = 14, int(e.Viewport.Bounds.Height) - (22 * len(rows) + 14) - 14
        d.Draw2dRectangle(System.Drawing.Rectangle(x, y, width, 22 * len(rows) + 14), RED, 2,
                          System.Drawing.Color.FromArgb(245, 255, 251, 250))
        for i, row in enumerate(rows):
            d.Draw2dText(row, RED, rg.Point2d(x + 14, y + 9 + i * 22), False, 14)
    if not o.message:
        return
    state, text, lines = o.message
    color = {"pass": GREEN, "complies": GREEN, "fail": RED, "review": AMBER}.get(state, AMBER)
    mark = {"pass": "✓", "complies": "✓", "fail": "✗", "review": "?"}.get(state, "?")
    rows = ["Gordium · " + mark + " " + text] + list(lines)[:6]
    x, y, h = 14, 14, 22
    width = max(len(r) for r in rows) * 8 + 24
    d.Draw2dRectangle(System.Drawing.Rectangle(x, y, width, h * len(rows) + 12),
                      color, 2, System.Drawing.Color.FromArgb(235, 255, 255, 255))
    for i, row in enumerate(rows):
        d.Draw2dText(row, color if i == 0 else System.Drawing.Color.FromArgb(40, 40, 40),
                     rg.Point2d(x + 12, y + 8 + i * h), False, 15 if i == 0 else 13)


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

def _label(text, color=None, bold=False):
    lab = ef.Label()
    lab.Text = text
    lab.Wrap = ef.WrapMode.Word
    if color is not None:
        lab.TextColor = color
    if bold:
        lab.Font = ed.Font(ed.SystemFont.Bold)
    return lab


class Panel(ef.Form):
    """A small floating window: every rule with its result (or why there are none), and the buttons."""

    def __init__(self):
        ef.Form.__init__(self)
        self.Title = "Gordium"
        self.ClientSize = ed.Size(460, 520)
        self.Topmost = True
        self.Resizable = True


def show_panel(p, result, facts, error=None):
    """Fill the panel: every rule with its result, or why there are none. A module function, not a Panel
    method: like the Overlay, the Panel class keeps its first methods for the whole Rhino session."""
    layout = ef.DynamicLayout()
    layout.Spacing = ed.Size(6, 4)
    layout.Padding = ed.Padding(10)
    layout.AddRow(_label(CITY + " · " + str(facts.get("zone")) + " · " + str(facts.get("use", "")).replace("_", " "),
                         bold=True))
    layout.AddRow(_label("Rules: draft rules, checked by code"))
    colors = {"PASS": ed.Color.FromArgb(31, 122, 77), "FAIL": ed.Color.FromArgb(200, 50, 43),
              "NEEDS REVIEW": ed.Color.FromArgb(154, 100, 0)}
    if error is not None:                   # nothing is shown as checked when the check didn't run
        layout.AddRow(_label("Can't check this model: " + error, colors["NEEDS REVIEW"], True))
    def row(into, r):
        detail = str(r["Table limit"]) + " · you have " + str(r["Proposed"]) + " " + str(r["Units"])
        if r["Error"] == "NEEDS REVIEW":
            detail = r["Why"] + (("\n✗ " if r.get("Fails") else "\n✓ ") + r["Provisional"] if r.get("Provisional") else "")
        into.AddRow(_label(r["Error"], colors.get(r["Error"]), True), _label(r["Requirement"] + "\n" + detail))

    for r in (result or {}).get("rows", []):
        row(layout, r)
    interior = (result or {}).get("interior") or []
    if interior:                            # the inside of the building isn't checked in this phase: folded away
        inside = ef.DynamicLayout()
        inside.Spacing = ed.Size(6, 4)
        for r in interior:
            row(inside, r)
        fold = ef.Expander()
        fold.Header = _label("Not checked yet: interior (" + str(len(interior)) + ")")
        fold.Content = inside
        fold.Expanded = False
        layout.AddRow(fold)
    env = (result or {}).get("envelope") or {}
    if env.get("coverage") and env["coverage"].get("over") is not None:
        c = env["coverage"]
        word = "over" if c["over"] > 0 else "left"
        layout.AddRow(_label("Coverage: " + format(abs(c["over"]), ",.1f") + " sf " + word +
                             " (allowed " + format(c["allowed"], ",.1f") + " sf)"))
    for note in env.get("notes") or []:
        layout.AddRow(_label("Envelope: " + note))
    buttons = ef.StackLayout()
    buttons.Orientation = ef.Orientation.Horizontal
    buttons.Spacing = 6
    for text, action in (("Lot facts…", lambda s, e: edit_facts()), ("Open report", lambda s, e: open_report()),
                         ("Envelope on/off", lambda s, e: toggle_envelope()), ("Live on/off", lambda s, e: toggle_live())):
        b = ef.Button()
        b.Text = text
        b.Click += action
        buttons.Items.Add(ef.StackLayoutItem(b))
    layout.AddRow(buttons)
    layout.Add(None)
    scroll = ef.Scrollable()
    scroll.Content = layout
    p.Content = scroll


def panel():
    p = STATE.get("panel")
    if p is None or not p.Visible:
        p = Panel()
        STATE["panel"] = p
        p.Show()
    return p


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


def confirm(doc, facts, options):
    """One small prefilled dialog. OK keeps the facts; Change… lets the architect set each one, then the dialog
    shows again with the new answers outlined, so nothing is saved unseen; closing it (or Esc) saves nothing."""
    o = overlay()
    _clear(o)                           # facts are being set: no earlier result (of any model) stays shown
    o.message = None
    _highlight(doc, facts)
    try:
        if STATE.get("auto_ok"):          # scripted runs (tests, the demo): accept the prefilled facts
            if STATE.get("on_confirm"):   # ...after recording what the box shows (the demo captures it)
                STATE["on_confirm"](doc, facts, _describe(facts, options["uses"]))
            return facts
        dialog = ef.Dialog[bool]()
        dialog.Title = "Gordium"
        dialog.Padding = ed.Padding(12)
        chosen = {}                     # which button closed it: none if closed or Esc (a cancel)
        ok, change = ef.Button(), ef.Button()
        ok.Text, change.Text = "OK", "Change…"
        ok.Click += lambda s, e: (chosen.update(choice="ok"), dialog.Close(True))
        change.Click += lambda s, e: (chosen.update(choice="change"), dialog.Close(False))
        layout = ef.DynamicLayout()
        layout.Spacing = ed.Size(8, 8)
        layout.AddRow(_label(_describe(facts, options["uses"])))
        layout.AddRow(None, change, ok)
        dialog.Content = layout
        dialog.DefaultButton = ok
        dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
        what = logic.after_confirm(chosen.get("choice"))
        if what == "keep":
            return facts
        if what == "cancel":
            return None
        changed = change_facts(doc, facts, options)
        return None if changed is None else confirm(doc, changed, options)     # shown again before it is saved
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
    """Lot facts…: every lot fact, then bedrooms, parking spaces and stories (skipped prompts stay unset)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    options = ask({"cmd": "options", "jurisdiction": JURISDICTION})
    try:
        saved = current_facts(doc)
    except ValueError:                  # unreadable: start again from the suggestions
        saved = {}
    try:
        _edit_counts_and_save(doc, saved, options)
    finally:                            # the editing outline and names never stay on screen
        o = overlay()
        o.confirm, o.labels = None, []
        doc.Views.Redraw()
    run_check(doc, report=False)


def _edit_counts_and_save(doc, saved, options):
    facts = change_facts(doc, logic.with_suggestions(saved, suggested_facts(doc, options["zones"])), options)
    if facts is None:                   # Esc: nothing changes
        return
    try:
        answers = {key: _count(prompt) for key, prompt in (("sleeping_rooms", "Bedrooms"),
                                                           ("parking_spaces", "Off-street parking spaces"),
                                                           ("stories", "Stories"))}
    except Cancelled:
        return
    save_facts(doc, logic.update_counts(facts, answers))


# ---- checking --------------------------------------------------------------------------------------------

def report_path(doc):
    folder = os.path.dirname(doc.Path) if doc.Path else os.path.expanduser("~/Documents")
    name = os.path.splitext(os.path.basename(doc.Path))[0] if doc.Path else "untitled"
    return os.path.join(folder, name + "_gordium_report.xlsx")


def _clear(o):
    """Nothing from an earlier check is left on screen."""
    o.red, o.red_ids, o.dims, o.envelope, o.box = [], set(), [], None, rg.BoundingBox.Empty
    o.confirm, o.labels = None, []
    o.doc = None


def run_check(doc, report=True):
    """Measure and check the model now; draw the result; update the panel. If the check can't run, the old
    result is cleared from the view and the panel, never left showing."""
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
        result = ask({"cmd": "check", "model": path, "facts": facts, "building_problems": problems,
                      "report": report_path(doc) if report else None})
        _clear(o)
        o.doc = doc.RuntimeSerialNumber
        s = result["summary"]
        o.message = (s["state"], s["text"], s["lines"])
        failing = [(g, _red_copy(g.Geometry)) for g in (_find(doc, i) for i in result["red"]) if g is not None]
        o.red = [copy for _, copy in failing if copy is not None]
        o.red_ids = {str(g.Id) for g, copy in failing if copy is not None}     # hidden only if drawn in red
        z = (facts.get("grade_elevation") or 0.0) + 0.1     # just above the ground, so it isn't hidden by it
        o.dims = [(rg.Line(_model_point(doc, a, z), _model_point(doc, b, z)), dim["label"])
                  for dim in result.get("dims", []) for a, b in [dim["points"]]]
        env = _envelope_brep(doc, result.get("envelope")) if STATE.get("envelope_on", True) else None
        o.envelope = env
        o.box = env.GetBoundingBox(True) if env else rg.BoundingBox.Empty
        STATE["last"] = {"summary": s, "rows": [{k: r.get(k) for k in ("Requirement", "Table limit", "Proposed", "Units",
                                                                        "Error", "Rule id", "Why", "Provisional")}
                                                for r in result["rows"]],
                         "interior": [r["Rule id"] for r in result.get("interior", [])],
                         "red": result["red"], "dims": result.get("dims"), "envelope": result.get("envelope"),
                         "at": time.time()}
        _newly_failing(doc, result)
        if not STATE.get("headless"):
            show_panel(panel(), result, facts)
        return result
    except Exception as e:
        _clear(o)
        o.doc = doc.RuntimeSerialNumber
        o.message = ("review", "can't check: " + str(e)[:160], [])
        STATE["last"] = {"error": str(e), "at": time.time()}
        if not STATE.get("headless"):
            show_panel(panel(), None, facts, str(e)[:300])
        return None
    finally:
        STATE["running"] = False
        doc.Views.Redraw()


# ---- "now fails": a short note, only when a rule starts failing --------------------------------------------

def _newly_failing(doc, result):
    """A short note for each rule that fails now and didn't at this document's last check: never for a failure
    that was already there, never on the first check, and never in a dialog (it goes by itself)."""
    seen = STATE.setdefault("fails_by_doc", {})
    seen[doc.RuntimeSerialNumber], notice = logic.notice(seen.get(doc.RuntimeSerialNumber), result["rows"])
    if not notice:
        return []
    STATE.setdefault("toasts", []).append(notice)      # kept for scripted runs (tests, the demo)
    if not STATE.get("headless"):
        _toast(notice)
    return notice


def _toast(lines):
    """The notice, drawn bottom left in the active view (no window, no button); it clears at the next command or
    after a few seconds."""
    o = overlay()
    o.toast = (list(lines), time.time() + TOAST_SECONDS)
    if STATE.get("command_hook") is None:              # the next command clears it
        hook = System.EventHandler[Rhino.Commands.CommandEventArgs](lambda s, e: _clear_toast())
        Rhino.Commands.Command.BeginCommand += hook
        STATE["command_hook"] = hook
    timer = STATE.get("toast_timer")
    if timer is None:
        timer = ef.UITimer()
        timer.Interval = 0.5
        timer.Elapsed += lambda s, e: _toast_tick()
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
    p = STATE.get("panel")
    if p is not None and p.Visible:
        show_panel(p, None, {}, "no check yet for this document (run GordiumCheck)")
    STATE["dirty"] = time.time()        # re-check the document now in front, if it has lot facts


def _opened(sender, e):
    """A file opened: another document; or merged into this one (Import, Insert, a reference): an edit."""
    if e.Merge or e.Reference:
        STATE["dirty"] = time.time()
    else:
        _new_document(sender, e)


def _idle(sender, e):
    t = STATE.get("dirty")
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
        new_doc = System.EventHandler[Rhino.DocumentEventArgs](_new_document)
        opened = System.EventHandler[Rhino.DocumentOpenEventArgs](_opened)
        active = System.EventHandler[Rhino.DocumentEventArgs](_new_document)
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
    objects = System.EventHandler[Rhino.DocObjects.RhinoObjectEventArgs](_changed)
    replaced = System.EventHandler[Rhino.DocObjects.RhinoReplaceObjectEventArgs](_changed)
    attributes = System.EventHandler[Rhino.DocObjects.RhinoModifyObjectAttributesEventArgs](_changed)
    idle = System.EventHandler(_idle)
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
    p = STATE.get("panel")
    if p is not None:
        p.Close()
        STATE.pop("panel", None)
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
        Rhino.RhinoApp.WriteLine("Gordium: " + result["summary"]["text"])
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
    house), named Floor 1, 2…"""
    k = 1.0 / _scale(doc)
    group = doc.Groups.Add("Gordium starting building")
    ids = []
    for i, floor in enumerate(start["floors"]):
        corners = [rg.Point3d(x * k, y * k, z * k) for z in (floor["base"], floor["top"]) for x, y in floor["outline"]]
        brep = rg.Brep.CreateFromBox(corners)
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
    facts = confirm(doc, facts, options)
    if facts is None:
        Rhino.RhinoApp.WriteLine("Gordium: nothing was started (the facts weren't confirmed)")
        return None
    save_facts(doc, facts)
    path = os.path.join(tempfile.gettempdir(), "gordium_start_" + str(doc.RuntimeSerialNumber) + ".3dm")
    export(doc, path)
    start = ask({"cmd": "start", "model": path, "facts": facts})
    STATE["start"] = {k: start.get(k) for k in ("stories", "height", "area", "coverage_allowed", "notes", "floors")}
    for note in start.get("notes") or []:
        Rhino.RhinoApp.WriteLine("Gordium: " + note)
    if not start.get("floors"):
        Rhino.RhinoApp.WriteLine("Gordium: no starting building could be drawn")
        return None
    add_floors(doc, start)
    doc.Views.Redraw()
    result = run_check(doc, report=False)
    live(True)
    documents(True)
    Rhino.RhinoApp.WriteLine("Gordium: created 1 group (" + str(len(start["floors"])) + " floor solids) on " +
                             logic.MASSING)
    return result
