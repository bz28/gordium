#! python3
"""Gordium in Rhino 8: GordiumCheck checks the open model against its zone's rules, shows the largest legal
building (the envelope), and re-checks after every edit (live mode).

This script only talks to Rhino. All measuring and checking is Gordium's own Python (the repo's packages, run
by its .venv in the background; docs/decisions/2026-10-20_rhino_talks_to_python.md): the lot and building
objects are copied into a small temporary .3dm, sent with the lot facts, and the answer is drawn. Nothing in
the model is changed: highlights, the envelope and the message are drawn on top (a display conduit).

Commands (set up by install.py): GordiumCheck, GordiumLive (on/off), GordiumFacts (edit the lot facts),
GordiumOff (stop and clear the drawing).
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
LAYERS = {"lot": "Site", "building": "Building"}
ID_KEY = "gordium:id"
SECTION, ENTRY = "Gordium", "lot_facts"
IDLE_SECONDS = 0.5                           # a re-check waits this long after the last edit

GREEN, RED, AMBER = System.Drawing.Color.FromArgb(31, 122, 77), System.Drawing.Color.FromArgb(200, 50, 43), \
    System.Drawing.Color.FromArgb(154, 100, 0)
BLUE = System.Drawing.Color.FromArgb(29, 95, 138)


# ---- the background checker ------------------------------------------------------------------------------

def _python():
    """The repo's .venv Python (3.12): this checkout's, or the main checkout's for a worktree."""
    d = REPO
    while True:
        candidate = os.path.join(d, ".venv", "bin", "python")
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(d)
        if parent == d:
            raise RuntimeError("no .venv found above " + REPO)
        d = parent


def _worker():
    p = STATE.get("worker")
    if p is None or p.poll() is not None:
        packages = os.path.join(REPO, "packages")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(STATE.get("extra_paths", []) + [
            os.path.join(packages, n) for n in sorted(os.listdir(packages)) if os.path.isdir(os.path.join(packages, n))])
        log = open(os.path.join(tempfile.gettempdir(), "gordium_worker.log"), "a")
        p = subprocess.Popen([_python(), "-u", "-m", "design_checker", "serve"], cwd=REPO, env=env,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, universal_newlines=True)
        STATE["worker"] = p
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

def _on_layer(doc, layer):
    found = doc.Objects.FindByLayer(layer)
    return list(found) if found else []


def _lot_candidates(doc):
    return [o for o in _on_layer(doc, LAYERS["lot"]) if isinstance(o.Geometry, rg.Curve) and o.Geometry.IsClosed]


def _buildings(doc):
    return [o for o in _on_layer(doc, LAYERS["building"])
            if isinstance(o.Geometry, (rg.Brep, rg.Extrusion, rg.Mesh, rg.SubD))]


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
    lot size and coverage wait for one), the first zone with rules, a detached one-family house. Every one is
    shown in the dialog; nothing is used until the architect says OK."""
    facts = {"jurisdiction": JURISDICTION, "zone": zones[0] if zones else None, "use": "one_family_detached",
             "corner_lot": False, "ground_is_flat": True, "lot_surveyed": False}
    lots = _lot_candidates(doc)
    if lots:
        lot = max(lots, key=lambda o: _area(o.Geometry))
        facts["lot_id"] = str(lot.Id)
        a, b = min(_segments(lot.Geometry), key=lambda s: (s[0].Y + s[1].Y) / 2)
        facts["street_line"] = [[[a.X, a.Y], [b.X, b.Y]]]
    buildings = _buildings(doc)
    if buildings:
        boxes = [o.Geometry.GetBoundingBox(True) for o in buildings]
        facts["grade_elevation"] = min(b.Min.Z for b in boxes)
        if len(buildings) > 1:
            big = max(zip(buildings, boxes), key=lambda ob: ob[1].Diagonal.X * ob[1].Diagonal.Y * ob[1].Diagonal.Z)
            facts["main_building"] = str(big[0].Id)
    return facts


def load_facts(doc):
    text = doc.Strings.GetValue(SECTION, ENTRY)
    return json.loads(text) if text else None


def save_facts(doc, facts):
    doc.Strings.SetString(SECTION, ENTRY, json.dumps(facts))


def export(doc, path):
    """The lot outlines and buildings, copied into a small .3dm (each copy keeps its object's id)."""
    f = Rhino.FileIO.File3dm()
    f.Settings.ModelUnitSystem = doc.ModelUnitSystem
    for kind in ("lot", "building"):
        layer = Rhino.DocObjects.Layer()
        layer.Name = LAYERS[kind]
        f.AllLayers.Add(layer)
    for index, objects in enumerate((_lot_candidates(doc), _buildings(doc))):
        for o in objects:
            attrs = Rhino.DocObjects.ObjectAttributes()
            attrs.LayerIndex = index
            attrs.SetUserString(ID_KEY, str(o.Id))
            g = o.Geometry
            if isinstance(g, rg.SubD):
                g = g.ToBrep(rg.SubDToBrepOptions.Default)
            f.Objects.Add(g, attrs)
    f.Write(path, 8)


def street_curve(facts):
    lines = facts.get("street_line") or []
    return [rg.Line(rg.Point3d(a[0], a[1], 0), rg.Point3d(b[0], b[1], 0)) for a, b in lines]


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


def cull(o, e):
    if e.RhinoObject is not None and str(e.RhinoObject.Id) in o.red_ids:
        e.CullObject = True                  # drawn by draw_scene in red instead


def bounds(o, e):
    if o.box.IsValid:
        e.IncludeBoundingBox(o.box)


def draw_scene(o, e):
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


def draw_screen(o, e):
    d = e.Display
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
    if not o.message:
        return
    state, text, lines = o.message
    color = {"pass": GREEN, "fail": RED, "review": AMBER}.get(state, AMBER)
    mark = {"pass": "✓", "fail": "✗", "review": "?"}.get(state, "?")
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
    return o


def _red_copy(g):
    """A failing object's copy for drawing in red: a hair (about 0.03 ft) larger than the object, so it wraps
    it instead of flickering against its faces. Only drawn; the model is never changed."""
    g = g.ToBrep() if isinstance(g, rg.Extrusion) else g.Duplicate()
    box = g.GetBoundingBox(True)
    size = max(box.Diagonal.X, box.Diagonal.Y, box.Diagonal.Z, 1e-6)
    g.Transform(rg.Transform.Scale(box.Center, 1 + 0.06 / size))
    return g


def _envelope_brep(env):
    if not env or not env.get("outline") or env.get("top") is None or env.get("base") is None:
        return None
    pts = [rg.Point3d(x, y, env["base"]) for x, y in env["outline"]]
    pts.append(pts[0])
    curve = rg.PolylineCurve(pts)
    ext = rg.Extrusion.Create(curve, env["base"] - env["top"], True)   # extrudes along -normal: sign by winding
    brep = ext.ToBrep() if ext else None
    if brep is not None and brep.GetBoundingBox(True).Max.Z < env["top"] - 1e-6:
        brep = rg.Extrusion.Create(curve, env["top"] - env["base"], True).ToBrep()
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
    """A small floating window: every rule with its result, and the buttons."""

    def __init__(self):
        ef.Form.__init__(self)
        self.Title = "Gordium"
        self.ClientSize = ed.Size(460, 520)
        self.Topmost = True
        self.Resizable = True

    def show(self, result, facts):
        rows = result["rows"]
        layout = ef.DynamicLayout()
        layout.Spacing = ed.Size(6, 4)
        layout.Padding = ed.Padding(10)
        layout.AddRow(_label(CITY + " · " + str(facts.get("zone")) + " · " + str(facts.get("use", "")).replace("_", " "),
                             bold=True))
        layout.AddRow(_label("Rules: draft rules, checked by code"))
        colors = {"PASS": ed.Color.FromArgb(31, 122, 77), "FAIL": ed.Color.FromArgb(200, 50, 43),
                  "NEEDS REVIEW": ed.Color.FromArgb(154, 100, 0)}
        for r in rows:
            detail = str(r["Table limit"]) + " · you have " + str(r["Proposed"]) + " " + str(r["Units"])
            if r["Error"] == "NEEDS REVIEW":
                detail = r["Why"]
            layout.AddRow(_label(r["Error"], colors.get(r["Error"]), True), _label(r["Requirement"] + "\n" + detail))
        env = result.get("envelope") or {}
        if env.get("coverage") and env["coverage"].get("over") is not None:
            c = env["coverage"]
            word = "over" if c["over"] > 0 else "left"
            layout.AddRow(_label("Coverage: " + format(abs(c["over"]), ",.1f") + " sf " + word +
                                 " (allowed " + format(c["allowed"], ",.1f") + " sf)"))
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
        self.Content = scroll


def panel():
    p = STATE.get("panel")
    if p is None or not p.Visible:
        p = Panel()
        STATE["panel"] = p
        p.Show()
    return p


# ---- the confirm dialog ----------------------------------------------------------------------------------

def _describe(facts, uses):
    ground = facts.get("grade_elevation")
    return (CITY + " · " + str(facts.get("zone")) + " · " + uses.get(facts.get("use"), str(facts.get("use"))) +
            "\nStreet side = the highlighted blue line · " +
            ("a corner lot (two streets)" if facts.get("corner_lot") else "not a corner lot") +
            "\nGround: " + ("flat" if facts.get("ground_is_flat") else "sloped") + " at z = " +
            ("?" if ground is None else format(ground, "g")) + " ft · lot outline " +
            ("from a survey" if facts.get("lot_surveyed") else "not from a survey (lot size and coverage wait for one)"))


def confirm(doc, facts, options):
    """One small prefilled dialog. OK keeps the facts; Change… lets the architect pick each one."""
    lot = _find(doc, facts.get("lot_id") or "")
    main = _find(doc, facts.get("main_building") or "") if facts.get("main_building") else None
    o = overlay()
    o.confirm = (lot.Geometry if lot else None, street_curve(facts), main.Geometry if main else None)
    doc.Views.Redraw()
    try:
        if STATE.get("auto_ok"):          # scripted runs (tests, the demo): accept the prefilled facts
            return facts
        dialog = ef.Dialog[bool]()
        dialog.Title = "Gordium"
        dialog.Padding = ed.Padding(12)
        ok, change = ef.Button(), ef.Button()
        ok.Text, change.Text = "OK", "Change…"
        ok.Click += lambda s, e: dialog.Close(True)
        change.Click += lambda s, e: dialog.Close(False)
        layout = ef.DynamicLayout()
        layout.Spacing = ed.Size(8, 8)
        layout.AddRow(_label(_describe(facts, options["uses"])))
        layout.AddRow(None, change, ok)
        dialog.Content = layout
        dialog.DefaultButton = ok
        if dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow):
            return facts
        return change_facts(doc, facts, options)
    finally:
        o.confirm = None
        doc.Views.Redraw()


def change_facts(doc, facts, options):
    facts = dict(facts)
    zone = Rhino.Input.RhinoGet.GetString("Zone (" + ", ".join(options["zones"]) + ")", True, facts.get("zone") or "")
    if zone[0] == Rhino.Commands.Result.Success and zone[1] in options["zones"]:
        facts["zone"] = zone[1]
    names = list(options["uses"].items())
    use = Rhino.UI.Dialogs.ShowListBox("Gordium", "Use of the lot", [n for _, n in names],
                                       options["uses"].get(facts.get("use"), ""))
    if use:
        facts["use"] = next(k for k, n in names if n == use)
    lots = _lot_candidates(doc)
    if len(lots) > 1:
        go = Rhino.Input.Custom.GetObject()
        go.SetCommandPrompt("Click the lot outline")
        go.GeometryFilter = Rhino.DocObjects.ObjectType.Curve
        if go.Get() == Rhino.Input.GetResult.Object:
            facts["lot_id"] = str(go.Object(0).ObjectId)
    corner = Rhino.Input.RhinoGet.GetBool("Corner lot (two streets meet at it)?", True, "No", "Yes",
                                          bool(facts.get("corner_lot")))
    if corner[0] == Rhino.Commands.Result.Success:
        facts["corner_lot"] = bool(corner[1])
    lot = _find(doc, facts.get("lot_id") or "")
    if lot is not None:
        picked = []
        while True:                      # every lot line on a street (both streets on a corner lot)
            prompt = "Click a lot line on the street" + (" (Enter when done)" if picked else "")
            rc, point = Rhino.Input.RhinoGet.GetPoint(prompt, bool(picked))
            if rc != Rhino.Commands.Result.Success:
                break
            a, b = min(_segments(lot.Geometry), key=lambda s: rg.Line(s[0], s[1]).DistanceTo(point, True))
            if [[a.X, a.Y], [b.X, b.Y]] not in picked:
                picked.append([[a.X, a.Y], [b.X, b.Y]])
            if not facts.get("corner_lot"):
                break
        if picked:
            facts["street_line"] = picked
    ground = Rhino.Input.RhinoGet.GetNumber("Ground level (z, ft)", True, facts.get("grade_elevation") or 0.0)
    if ground[0] == Rhino.Commands.Result.Success:
        facts["grade_elevation"] = ground[1]
    return facts


def edit_facts():
    """Lot facts…: bedrooms, parking spaces and stories (not drawn in a massing model), and the rest."""
    doc = Rhino.RhinoDoc.ActiveDoc
    facts = load_facts(doc) or {}
    for key, prompt in (("sleeping_rooms", "Bedrooms"), ("parking_spaces", "Off-street parking spaces"),
                        ("stories", "Stories")):
        rc = Rhino.Input.RhinoGet.GetInteger(prompt, True, facts.get(key) or 0)
        if rc[0] == Rhino.Commands.Result.Success:
            facts[key] = rc[1]
    save_facts(doc, facts)
    run_check(doc, report=False)


# ---- checking --------------------------------------------------------------------------------------------

def report_path(doc):
    folder = os.path.dirname(doc.Path) if doc.Path else os.path.expanduser("~/Documents")
    name = os.path.splitext(os.path.basename(doc.Path))[0] if doc.Path else "untitled"
    return os.path.join(folder, name + "_gordium_report.xlsx")


def run_check(doc, report=True):
    """Measure and check the model now; draw the result; update the panel."""
    if STATE.get("running"):
        return None
    STATE["running"] = True
    o = overlay()
    try:
        facts = load_facts(doc)
        if not facts:
            return None
        path = os.path.join(tempfile.gettempdir(), "gordium_live_" + str(doc.RuntimeSerialNumber) + ".3dm")
        export(doc, path)
        result = ask({"cmd": "check", "model": path, "facts": facts,
                      "report": report_path(doc) if report else None})
        s = result["summary"]
        o.message = (s["state"], s["text"], s["lines"])
        failing = [g for g in (_find(doc, i) for i in result["red"]) if g is not None]
        o.red = [_red_copy(g.Geometry) for g in failing]
        o.red_ids = {str(g.Id) for g in failing}
        z = (facts.get("grade_elevation") or 0.0) + 0.1     # just above the ground, so it isn't hidden by it
        o.dims = [(rg.Line(rg.Point3d(a[0], a[1], z), rg.Point3d(b[0], b[1], z)), dim["label"])
                  for dim in result.get("dims", []) for a, b in [dim["points"]]]
        env = _envelope_brep(result.get("envelope")) if STATE.get("envelope_on", True) else None
        o.envelope = env
        o.box = env.GetBoundingBox(True) if env else rg.BoundingBox.Empty
        STATE["last"] = {"summary": s, "rows": [{k: r[k] for k in ("Requirement", "Table limit", "Proposed", "Units",
                                                                    "Error", "Rule id", "Why")} for r in result["rows"]],
                         "red": result["red"], "dims": result.get("dims"), "envelope": result.get("envelope"),
                         "at": time.time()}
        if not STATE.get("headless"):
            panel().show(result, facts)
        return result
    except Exception as e:
        o.message = ("review", "can't check: " + str(e)[:160], [])
        STATE["last"] = {"error": str(e), "at": time.time()}
        return None
    finally:
        STATE["running"] = False
        doc.Views.Redraw()


# ---- live mode -------------------------------------------------------------------------------------------

def _changed(sender, e):
    STATE["dirty"] = time.time()


def _idle(sender, e):
    t = STATE.get("dirty")
    if t and time.time() - t >= IDLE_SECONDS and not STATE.get("running"):
        STATE["dirty"] = None
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is not None and load_facts(doc):
            run_check(doc, report=False)


def _unhook():
    hooks = STATE.pop("hooks", None)
    if hooks:
        changed, replaced, idle = hooks
        Rhino.RhinoDoc.AddRhinoObject -= changed
        Rhino.RhinoDoc.DeleteRhinoObject -= changed
        Rhino.RhinoDoc.UndeleteRhinoObject -= changed
        Rhino.RhinoDoc.ReplaceRhinoObject -= replaced
        Rhino.RhinoApp.Idle -= idle


def live(on):
    _unhook()
    STATE["live"] = on
    if on:
        changed = System.EventHandler[Rhino.DocObjects.RhinoObjectEventArgs](_changed)
        replaced = System.EventHandler[Rhino.DocObjects.RhinoReplaceObjectEventArgs](_changed)
        idle = System.EventHandler(_idle)
        Rhino.RhinoDoc.AddRhinoObject += changed
        Rhino.RhinoDoc.DeleteRhinoObject += changed
        Rhino.RhinoDoc.UndeleteRhinoObject += changed
        Rhino.RhinoDoc.ReplaceRhinoObject += replaced
        Rhino.RhinoApp.Idle += idle
        STATE["hooks"] = (changed, replaced, idle)


def toggle_live():
    live(not STATE.get("live"))
    Rhino.RhinoApp.WriteLine("Gordium live mode " + ("on" if STATE["live"] else "off"))


def toggle_envelope():
    STATE["envelope_on"] = not STATE.get("envelope_on", True)
    run_check(Rhino.RhinoDoc.ActiveDoc, report=False)


def open_report():
    path = report_path(Rhino.RhinoDoc.ActiveDoc)
    if os.path.exists(path):
        subprocess.Popen(["open", path])


def off():
    _unhook()
    STATE["live"] = False
    o = STATE.get("overlay")
    if o is not None:
        o.Enabled = False
    p = STATE.get("panel")
    if p is not None:
        p.Close()
        STATE.pop("panel", None)
    Rhino.RhinoDoc.ActiveDoc.Views.Redraw()


# ---- GordiumCheck ----------------------------------------------------------------------------------------

def gordium_check():
    doc = Rhino.RhinoDoc.ActiveDoc
    options = ask({"cmd": "options", "jurisdiction": JURISDICTION})
    facts = load_facts(doc)
    if not facts:
        facts = confirm(doc, suggested_facts(doc, options["zones"]), options)
        save_facts(doc, facts)
    result = run_check(doc, report=True)
    _unhook()
    live(True)                                      # live mode is on by default
    if result is not None:
        Rhino.RhinoApp.WriteLine("Gordium: " + result["summary"]["text"])
    return result
