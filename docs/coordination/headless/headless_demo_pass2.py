"""The Rhino queue's demo smoke (RHINO_QUEUE item 9) and #15's pass 2 (apps/rhino_plugin/tests/pass2_in_rhino.py),
claim by claim, WITHOUT Rhino.

What runs is Gordium's own code: the real checker (`python -m design_checker serve`, started and spoken to by the
plugin's own _worker / ask / _stop_worker), the plugin's functions exec'd from apps/rhino_plugin/gordium_rhino.py
and gordium_ui.py as written (gordium_check, gordium_start, _box_loop, _box_state, _apply_box, _box_pick,
_pick_outcome, export, current_facts, open_report, zoom_to, show_context, draw_screen, show_detail, start_box…),
rhino_logic loaded the way Rhino loads it (top-level, from its file), and every model the checker reads written
with rhino3dm by the plugin's own export(). Only Rhino's document tables, its viewports and the Eto widgets are
stand-ins (fakes.py); every claim that leans on one is "partial", and says what only Rhino can still show.

Run from the demo checkout:
  cd /home/user/wt/dryrun && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(ls -d packages/* | tr '\\n' ':') \\
      /home/user/venv/bin/python <this file>
Prints one JSON line per claim; writes results_demo_pass2.json beside this file."""
import copy
import importlib.util
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

import numpy as np
import rhino3dm as r

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fakes  # noqa: E402

REPO = Path("/home/user/wt/dryrun")
TMP = HERE / "tmp"
TMP.mkdir(exist_ok=True)
os.environ["TMPDIR"] = str(TMP)               # the checker's own temporary files too: nothing outside scratch
tempfile.tempdir = str(TMP)
RHINO_SRC = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
PASS2 = (REPO / "apps/rhino_plugin/tests/pass2_in_rhino.py").read_text(encoding="utf-8")
RESULTS = []
SAID = []                                     # Rhino's command line (fake RhinoApp.WriteLine)
F = fakes.install(SAID)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


# rhino_logic as Rhino loads it: a top-level module from its file (gordium_rhino puts its folder on the path)
logic = load("rhino_logic", REPO / "packages/design_checker/design_checker/rhino_logic.py")
logic.ERROR_LOG = str(TMP / "gordium_errors.log")       # logic.guard swallows errors: they are read back below
logic.REPORT = SAID.append
if os.path.exists(logic.ERROR_LOG):
    os.remove(logic.ERROR_LOG)
ui = load("gordium_ui", REPO / "apps/rhino_plugin/gordium_ui.py")


def guarded_errors():
    try:
        return Path(logic.ERROR_LOG).read_text(encoding="utf-8")
    except OSError:
        return ""


# ---- the plugin's own functions, exec'd as written --------------------------------------------------------------

def source_of(name):
    start = RHINO_SRC.index("\ndef %s(" % name) + 1
    lines = RHINO_SRC[start:].split("\n")
    out = [lines[0]]
    for line in lines[1:]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        out.append(line)
    return "\n".join(out)


PLUGIN_FUNCTIONS = [
    "_scale", "_sorted_objects", "_lot_candidates", "_buildings", "_segments", "_area", "_find", "suggested_facts",
    "load_facts", "current_facts", "save_facts", "_save_facts", "export", "_model_point", "_model_length",
    "_feet_point", "_feet_length", "_feet_area", "street_curve", "_here", "stale", "_model_on_screen", "_notice_box",
    "_screen_size", "_in_active_view", "draw_screen", "_status_rows", "_drawn_envelope", "_envelope_lines", "_north",
    "zoom_to", "set_labels", "_ui_state", "_save_ui_state", "_box_open", "_set_source", "fact_sources", "_lot_level",
    "_box_state", "_ft_text", "_apply_box", "_get_point", "_box_pick", "_one_pick", "_pick_outcome", "_box_loop",
    "_drawn", "report_path", "check_facts", "_plan_edges", "_draw_plan", "say", "open_report", "gordium_check",
    "gordium_start", "_doc_name", "_context_layer_indexes", "_lock_context", "_context_visible", "show_context",
    "_context_on", "_worker", "_stop_worker", "ask", "_actions", "PANEL_ACTIONS", "_describe",
]


def started_at(pid):
    """A process's start time (its identity), None when it isn't running (a zombie counts as gone)."""
    try:
        stat = Path("/proc/%d/stat" % int(pid)).read_text().rsplit(")", 1)[1].split()
        return None if stat[0] == "Z" else stat[19]
    except (OSError, ValueError, IndexError):
        return None


def stop_pid(pid):
    try:
        if "python" in Path("/proc/%d/comm" % int(pid)).read_text().lower():
            os.kill(int(pid), signal.SIGKILL)
    except OSError:
        pass


class Table:
    """rhino_logic.BoxSession's table (gordium_rhino.RhinoTable) on a fake document: no box here draws or holds
    anything (no lookup), so only these calls are reached."""

    def __init__(self, doc):
        self.doc = doc

    def layer_names(self):
        return [x.FullPath for x in self.doc.Layers]

    def save_views(self):
        return []

    def restore_views(self, saved):
        pass

    def exists(self, i):
        return self.doc.Objects.FindId(i) is not None

    def remove_layer_if_empty(self, path):
        pass

    def mark_added(self, i, token):
        pass

    def clear_mark(self, i):
        pass

    def delete(self, i):
        o = self.doc.Objects.FindId(i)
        if o is not None:
            self.doc.Objects.Delete(o)


def plugin():
    """One copy of the plugin: its functions, constants and STATE, as `import gordium_rhino` gives in Rhino."""
    g = {"__name__": "gordium_rhino", "json": json, "math": math, "os": os, "subprocess": subprocess, "sys": sys,
         "time": time, "tempfile": types.SimpleNamespace(gettempdir=lambda: str(TMP)),
         "Rhino": F.Rhino, "rg": F.rg, "System": F.System, "ef": F.ef, "ed": F.ed, "sc": F.sc,
         "logic": logic, "ui": ui, "STATE": {"repo": str(REPO), "extra_paths": [], "headless": True},
         "LEFTOVERS": {}, "REPO": str(REPO)}
    for const in ("JURISDICTION", "CITY"):
        exec(re.search(r"^%s = .*$" % const, RHINO_SRC, re.M).group(0), g)
    exec(RHINO_SRC[RHINO_SRC.index("LAYERS = logic.LAYERS"):RHINO_SRC.index("\n\n\n", RHINO_SRC.index("CONTEXT_GUIDE ="))], g)
    exec('SOURCES_ENTRY = "fact_sources"', g)
    for name in PLUGIN_FUNCTIONS:
        exec(source_of(name), g)
    # stand-ins for what needs the real Rhino (each named; none decides a result)
    g["_python"] = lambda: "/home/user/venv/bin/python"     # the venv we were given (_python looks for <repo>/.venv)
    g["SERVERS"] = logic.ServerBook(str(TMP / "gordium_servers.json"), {"pid": os.getpid(), "start": started_at(os.getpid())},
                                    started_at, stop_pid)
    g["_recover"] = lambda doc: None                # nothing held by an unfinished box in a fresh fake document
    g["_highlight"] = lambda doc, facts: None       # the green/blue outline while picking: drawing only
    g["_grade_points"] = lambda doc, finished=False: []   # no spot grades in these files (flat ground, the MVP)
    g["_lookup_poll"] = g["_lookup_stop"] = lambda *a: None
    g["live"] = g["documents"] = lambda on: None    # Rhino's event hooks
    g["frame_site"] = lambda doc, facts: None       # view framing (Rhino's views)
    g["sync_context"] = lambda doc, facts: None     # the neighbourhood fetch (no lookup was made: nothing to draw)
    g["_context_record"] = lambda doc: None
    g["draw_context"] = lambda doc, frame, left=0: g["say"]("(draw_context: not run headless)")
    g["RhinoTable"] = Table
    g["_add_lot"] = lambda doc, sample: doc.add(r.PolylineCurve([r.Point3d(x, y, 0) for x, y in sample["lot"] + sample["lot"][:1]]),
                                                logic.LAYERS["lot"], sample["lot_name"]).Id
    g["add_floors"] = lambda doc, start: add_floors(doc, start)
    g["confirm"] = lambda doc, facts, options, mode="check": confirm(g, doc, facts, options, mode)
    g["run_check"] = lambda doc, report=True: run_check(g, doc, report)
    g["_extras"] = lambda doc, facts: extras_of(g, doc, facts)
    g["edit_facts"] = g["pick_survey"] = g["set_grade"] = g["enter_rooms"] = g["add_to_check"] = lambda *a: None
    g["this_is_the_ground"] = g["hide_massing"] = g["not_the_ground"] = g["pick_main_building"] = lambda *a: None
    g["set_envelope"] = lambda *a: None
    g["_prism"] = lambda doc, outline, base, top: object() if outline and top is not None and base is not None \
        and top - base > 1e-9 else None             # the red/amber block's solid: drawing only
    g["_proud"] = lambda doc, brep: brep
    return g


def add_floors(doc, start):
    """gordium_rhino.add_floors: one solid per story on Gordium::Massing, named Floor n, marked with its story and
    height (its rg.Brep.CreateFromBox of the outline's corners; every outline GordiumStart draws here is a box
    square to the axes, so the same solid)."""
    ids = []
    for i, floor in enumerate(start["floors"]):
        xs, ys = [p[0] for p in floor["outline"]], [p[1] for p in floor["outline"]]
        brep = r.Brep.CreateFromBoundingBox(r.BoundingBox(min(xs), min(ys), floor["base"], max(xs), max(ys), floor["top"]))
        ids.append(doc.add(brep, logic.MASSING, "Floor " + str(i + 1),
                           {logic.FLOOR_KEY: str(i + 1) + ";" + repr(floor["top"] - floor["base"])}).Id)
    return ids


def confirm(g, doc, facts, options, mode):
    """gordium_rhino.confirm/_confirm's core: one start box at a time, its own session, run_box rolls back any way out
    but Draw's (the overlay and the panel's buttons it also touches are drawing only)."""
    gate = g["STATE"].setdefault("box_gate", logic.BoxGate())
    if not logic.allowed("open_box", g["_box_open"]()) or not gate.enter():
        g["say"](logic.BOX_BUSY)
        return None
    try:
        saved_ui = g["_ui_state"](doc)
        session = logic.BoxSession(Table(doc))
        return logic.run_box(session, lambda: g["_box_loop"](doc, facts, options, mode, saved_ui, session))
    finally:
        gate.leave()


def extras_of(g, doc, facts):
    """gordium_rhino._extras: what was sent, the objects on the lot left out (none in these files: only the lot and
    the house), the main building's name, the sources."""
    buildings = g["_buildings"](doc)
    layers = sorted({doc.Layers[o.Attributes.LayerIndex].FullPath for o in buildings})
    return {"scope": {"groups": 1, "solids": len(buildings), "layer": ", ".join(layers)}, "main_name": None,
            "not_included": [], "touching": [], "context_left_out": logic.context_left_out({}), "ground_like": [],
            "sources": g["fact_sources"](doc)}


def run_check(g, doc, report=True):
    """gordium_rhino.run_check's request, word for word (the model exported by export(), the facts as check_facts
    sends them, "before" for the notice, the report path when asked), and what it keeps (statuses for the next
    notice, the view the panel shows). The drawing it then does is built by overlay_for() when a claim needs it."""
    STATE = g["STATE"]
    facts = g["current_facts"](doc)
    if logic.missing(facts):
        raise ValueError("lot facts missing: " + ", ".join(logic.missing(facts)))
    path = os.path.join(str(TMP), "gordium_live_" + str(doc.RuntimeSerialNumber) + ".3dm")
    problems = g["export"](doc, path)
    sent = g["check_facts"](doc, facts)
    extras = g["_extras"](doc, facts)
    extras["before"] = STATE.setdefault("statuses_by_doc", {}).get(doc.RuntimeSerialNumber)
    result = g["ask"]({"cmd": "check", "model": path, "facts": sent, "building_problems": problems,
                       "report": g["report_path"](doc) if report else None, "extras": extras})
    STATE["statuses_by_doc"][doc.RuntimeSerialNumber] = result["statuses"]
    STATE["view"], STATE["result"], STATE["sent"] = result["view"], result, sent
    STATE["last"] = {"at": time.time(), "summary": result["summary"]}
    if result.get("notice"):
        STATE.setdefault("toasts", []).append([result["notice"]])
    STATE.setdefault("labels_by_doc", {})[doc.RuntimeSerialNumber] = logic.labels_on(g["_ui_state"](doc))
    if report and result.get("report_error"):
        g["say"](logic.report_message(g["report_path"](doc), False, result["report_error"]))
    return result


def overlay_for(g, doc, result, facts):
    """The overlay as run_check fills it from a result (its own lines: the message, the envelope's top and its
    Height limit label, north, then _draw_plan as written)."""
    o = types.SimpleNamespace(red=[], red_ids=set(), dims=[], envelope=None, box=None, encroach=[], yard_dims=[],
                              edge_labels=[], lot_outline=None, yards_zone=None, grade_points=[], plan_lines=[],
                              confirm=None, labels=[], envelope_lines=None, height_limit=None, north=None,
                              unmeasured=[], toast=None)
    o.doc = doc.RuntimeSerialNumber
    view = result["view"]
    head = view["header"]
    second = [head["draft"].split(" · ")[0]] + [t for t in (head["lot"], head["grade"])
                                                 if "approximate" in t or "not set" in t or "existing" in t]
    o.message = (view["state"], view["summary"], [" · ".join(second)])
    drawn = g["_drawn_envelope"](doc, facts, result.get("envelope"))
    o.envelope_lines = g["_envelope_lines"](doc, drawn) if drawn else None
    o.height_limit = (o.envelope_lines[1], logic.height_limit_text((result.get("envelope") or {}).get("top"),
                                                                   g["_ft_text"](drawn["top"] - drawn["base"]))) \
        if o.envelope_lines else None
    o.north = g["_north"](doc, facts)
    g["_draw_plan"](doc, o, result, g["STATE"]["sent"])
    return o


# ---- the model edits the in-Rhino scripts make (doc.Objects.Transform on every building) ----------------------

def transform_buildings(g, doc, m):
    """Every building object transformed by the 4x4 matrix m (Rhino's doc.Objects.Transform(id, xform, True))."""
    x = r.Transform(1.0)
    for i in range(4):
        for j in range(4):
            setattr(x, "M%d%d" % (i, j), float(m[i][j]))
    for o in g["_buildings"](doc):
        assert o.Geometry.raw.Transform(x)


def translation(v):
    m = np.eye(4)
    m[:3, 3] = v
    return m


def scale_along(point, u, s):
    """rg.Transform.Scale(Plane(point, u, Z x u), s, 1, 1): scale by s along the unit vector u, about `point`."""
    u = np.asarray(u, float) / np.linalg.norm(u)
    lin = np.eye(3) + (s - 1) * np.outer(u, u)
    m = np.eye(4)
    m[:3, :3] = lin
    m[:3, 3] = np.asarray(point) - lin @ np.asarray(point)
    return m


def items_of(g):
    return {i["name"]: i for i in g["STATE"]["view"]["items"]}


def feet(text):
    """pass2_in_rhino.feet, as written: 4'-11 3/8" -> 4.921875."""
    ft, inch, frac = re.fullmatch(r"(\d+)'-(\d+)(?: (\d+/\d+))?\"", text).groups()
    num, den = (frac or "0/1").split("/")
    return int(ft) + (int(inch) + int(num) / int(den)) / 12


# ---- the panel's detail and the start box, built by gordium_ui with the stand-in Eto ---------------------------

def detail_of(g, item, view):
    """ui.show_detail(parts) for `item` selected: the panel's detail controls, in order (Container.Children)."""
    parts = {"detail": fakes.DynamicLayout(), "by_id": {i["id"]: i for i in view["items"]}, "selected": item["id"],
             "view": view, "stale": False,
             "actions": {k: (lambda *a: None) for k in ("enter", "main", "add", "ground", "not_ground")}}
    ui.show_detail(parts)
    return parts["detail"]


def click(dialog, text):
    b = next(c for c in dialog.Children if isinstance(c, fakes.Button) and c.Text == text)
    assert b.Enabled, "%s is off" % text
    b.Click.fire(b, None)


# ---- the claims ---------------------------------------------------------------------------------------------------

def claim(cid, group, where, title, needs, offline, rhino_part):
    """Decorator: runs the check (returns (ok, evidence)), records one result line."""
    def run(fn):
        before = guarded_errors()
        try:
            ok, evidence = fn()
        except Exception as e:                       # noqa: BLE001  (a crash is a failed check, said plainly)
            ok, evidence = False, "CRASHED: %s: %s | %s" % (type(e).__name__, e,
                                                            traceback.format_exc().strip().splitlines()[-3:])
            if STEP_ERRORS:
                evidence += " | step errors so far: " + " || ".join(STEP_ERRORS)
        new = guarded_errors()[len(before):]
        if new.strip():                              # an error a guard swallowed during this check
            ok, evidence = False, evidence + " | a guarded error was logged: " + new.strip()[-600:]
        rec = {"id": cid, "group": group, "where": where, "title": title, "needs": needs,
               "offline": offline, "offline_ok": bool(ok), "evidence": evidence, "rhino_part": rhino_part}
        RESULTS.append(rec)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        return fn
    return run


STEP_ERRORS = []


def step(fn):
    """A step that sets up the claims after it (the in-Rhino script's step body); its failure is said in theirs."""
    try:
        fn()
    except Exception as e:                       # noqa: BLE001
        STEP_ERRORS.append("%s failed: %s: %s | %s" % (getattr(fn, "__name__", "step"), type(e).__name__, e,
                                                       traceback.format_exc().strip().splitlines()[-3:]))


def stop_everything(*gs):
    for g in gs:
        try:
            g["_stop_worker"]()
        except Exception:                            # noqa: BLE001
            pass


def checker_children():
    """`design_checker serve` processes that are this process's children (pass2's own `ps` query, on Linux)."""
    out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,stat=,command="], capture_output=True, text=True).stdout
    rows = [l.split(None, 3) for l in out.splitlines()]
    return [x[0] for x in rows if len(x) == 4 and x[1] == str(os.getpid()) and "Z" not in x[2]
            and "design_checker serve" in x[3]]


# ================================================================================================================
# (A) the demo smoke: RHINO_QUEUE item 9
# ================================================================================================================

W9 = "RHINO_QUEUE 9"
G = plugin()
DOC = fakes.FDoc(path=str(TMP / "demo_smoke.3dm"))
F.Rhino.RhinoDoc.ActiveDoc = DOC
D = {}                                               # what the demo steps hand on


@claim("demo_1_empty_file_goes_to_gordium_start", "demo", W9,
       "GordiumStart (or GordiumCheck) in an empty file starts a new project on the sample: 106 Ithaca Rd's tax-map lot "
       "is put on the Site layer and the start box opens prefilled (address, R-1b, one-family, Ithaca Rd)",
       "rhino", "partial",
       "The real command in a real empty Rhino file: the lot curve drawn on the Site layer, the box opening on screen.")
def _():
    shown = []

    def first_box(dialog):                          # the box as the architect first sees it: recorded, then Cancel
        shown.append({"title": dialog.Title,
                      "labels": [c.Text for c in dialog.Children if isinstance(c, fakes.Label)],
                      "buttons": [(c.Text, c.Enabled) for c in dialog.Children if isinstance(c, fakes.Button)],
                      "address": next(c.Text for c in dialog.Children if isinstance(c, fakes.TextBox)),
                      "zone": next(c.SelectedValue.Text for c in dialog.Children
                                   if isinstance(c, fakes.DropDown) and c.SelectedValue is not None
                                   and c.SelectedValue.Text.startswith("R-"))})
        click(dialog, "Cancel")

    probe = fakes.FDoc(path=str(TMP / "demo_probe.3dm"))
    F.Rhino.RhinoDoc.ActiveDoc = probe
    G["STATE"]["on_box_shown"] = first_box
    try:
        went = G["gordium_check"]()                 # GordiumCheck on an empty model hands over to GordiumStart
    finally:
        G["STATE"].pop("on_box_shown", None)
        F.Rhino.RhinoDoc.ActiveDoc = DOC
    lots = G["_lot_candidates"](probe)
    box = shown[0] if shown else {}
    D["first_box"] = box
    ok = (went is None and len(lots) == 1 and box.get("title") == "New zoning check"
          and box.get("address") == "106 Ithaca Rd, Ithaca, NY" and box.get("zone") == "R-1b"
          and "Ithaca Rd" in box.get("labels", []) and ("Draw", False) in box.get("buttons", [])
          and "nothing was started" in " ".join(SAID))
    return ok, ("gordium_check() on an empty fake document went to gordium_start(), which asked the real checker for "
                "sample_site and put one closed lot outline on the Site layer (%d lot candidate). The start box built by "
                "gordium_ui.start_box read: title %r, address %r, district %r, street row %r, Draw enabled=%s before the "
                "district is confirmed; Cancel then left 'nothing was started'." %
                (len(lots), box.get("title"), box.get("address"), box.get("zone"),
                 "Ithaca Rd" if "Ithaca Rd" in box.get("labels", []) else None,
                 dict(box.get("buttons", [])).get("Draw")))


@claim("demo_2_draw_draws_the_starting_house", "demo", W9,
       "Ticking 'This is the lot's district' and clicking Draw draws the starting house (3 floors) and checks it: "
       "nothing fails, the front yard complies",
       "rhino", "partial",
       "The house drawn in the viewport as one group on Gordium::Massing, the panel showing the result.")
def _():
    def tick_and_draw(dialog):
        tick = next(c for c in dialog.Children if isinstance(c, fakes.CheckBox) and c.Text == logic.ZONE_TICK)
        tick.Checked = True
        tick.CheckedChanged.fire(tick, None)
        click(dialog, "Draw")

    G["STATE"]["on_box_shown"] = tick_and_draw
    try:
        result = G["gordium_start"]()
    finally:
        G["STATE"].pop("on_box_shown", None)
    floors = G["_buildings"](DOC)
    items = items_of(G)
    D["start_result"] = result
    D["house_ids"] = [o.Id for o in floors]
    fails = [n for n, i in items.items() if i["status"] == "does_not_comply"]
    front = items.get("Front yard") or {}
    D["front0"] = front
    ok = (result is not None and len(floors) == 3 and not fails and front.get("status") == "complies"
          and G["STATE"]["start"]["stories"] == 3)
    return ok, ("Draw saved the facts and the real checker's 'start' drew %d floor solids (%s, %s tall in all); the check "
                "of the exported .3dm says %r; nothing does_not_comply (%s); Front yard %s, required %s: %s." %
                (len(floors), ", ".join(o.Attributes.Name for o in floors), G["STATE"]["start"]["height"],
                 result and result["view"]["summary"], fails or "none", front.get("proposed"), front.get("required"),
                 front.get("status")))


@claim("demo_3_move_5ft_front_yard_fails", "demo", W9,
       "Moving the house 5 ft toward the street makes the front yard fail (does not comply), with the 'no longer "
       "complies' notice",
       "rhino", "partial",
       "The Move command in Rhino, the live re-check firing on Rhino's idle, the red strip and the notice drawn.")
def _():
    transform_buildings(G, DOC, translation([0, -5.0, 0]))      # toward the street (the bottom of Top view)
    result = run_check(G, DOC, report=False)
    front = items_of(G)["Front yard"]
    D["moved"] = result
    ok = front["status"] == "does_not_comply" and bool(result.get("notice")) and "Front yard" in result["notice"]
    return ok, ("After a 5 ft move toward the street the Front yard went from %s (%s) to %s: %s, required %s, delta %r; "
                "the notice reads %r." % (D["front0"].get("proposed"), D["front0"].get("status"), front["proposed"],
                                          front["status"], front["required"], front.get("delta"), result.get("notice")))


@claim("demo_4_report_opens_on_check_sheet", "demo", W9,
       "Zoning report… writes the report for the model as it is now and it opens on its Check sheet, showing the "
       "front yard failing",
       "rhino", "partial",
       "Excel or Numbers actually opening the file on Ben's Mac / the cofounders' Windows, on the Check tab.")
def _():
    import openpyxl
    opened = []
    real = ui.open_target
    ui.open_target = lambda target: (opened.append(target), (True, None))[1]
    try:
        G["open_report"]()
    finally:
        ui.open_target = real
    path = G["report_path"](DOC)
    wb = openpyxl.load_workbook(path)
    check = wb["Check"]
    rows = [[c.value for c in row] for row in check.iter_rows()]
    front = next((row for row in rows if row and isinstance(row[2], str) and row[2].startswith("Front yard")), None)
    selected = [ws.title for ws in wb.worksheets if ws.sheet_view.tabSelected]
    said = G["STATE"].get("said", [])[-1:]
    mac, win = logic.open_command("posix", path), logic.open_command("nt", path)
    out_rows = [row for row in wb["Output"].iter_rows(values_only=True)]
    out_front = next((row for row in out_rows if row and str(row[0]).startswith("Front yard")), None)
    ok = (opened == [path] and wb.sheetnames[0] == "Check" and wb.active.title == "Check" and selected == ["Check"]
          and front is not None and front[1] == "✕" and out_front is not None and out_front[6] == "FAIL"
          and mac == ("run", ["open", path]) and win == ("startfile", path))
    return ok, ("open_report() ran a fresh check that wrote %s and asked the OS to open it (%s); openpyxl reads sheets %s, "
                "the active one %r, only %s selected; its title %r; the Front yard line %r; the Output sheet's Front yard "
                "row %r. The open command is %s on "
                "the Mac and os.startfile on Windows; the panel said %r." %
                (os.path.basename(path), opened, wb.sheetnames[:3] + ["…"], wb.active.title, selected, rows[0][0],
                 front[:6] if front else None, out_front and (out_front[0], out_front[2], out_front[6]), mac[1][0], said))


@claim("demo_5_corner_pick_both_street_lines", "demo", W9,
       "Corner lot: in the start box (Edit site…), Corner lot? Yes, then Change… on the street row, click both street "
       "lot lines, Enter: both lines are kept as the street lines, and the check runs on them",
       "rhino", "partial",
       "The real Eto box, the command-line prompts and the clicks snapping to the lot lines in the viewport.")
def _():
    facts0 = G["current_facts"](DOC)
    lot = G["_find"](DOC, facts0["lot_id"])
    segs = list(G["_segments"](lot.Geometry))
    mids = [(s[0] + s[1]) / 2 for s in (segs[0], segs[len(segs) // 2])]   # two different lot lines (pass2's pick)
    clicks = [(F.Rhino.Commands.Result.Success, m) for m in mids] + [(F.Rhino.Commands.Result.Nothing, None)]
    prompts, boxes = [], []

    def get_point(prompt):
        prompts.append(prompt)
        return clicks.pop(0)

    def script(dialog):
        rows = [c.Text for c in dialog.Children if isinstance(c, fakes.Label)]
        boxes.append(rows)
        if len(boxes) == 1:                          # Corner lot? Yes: two streets, then Change… on the street row
            corner = next(c for c in dialog.Children if isinstance(c, fakes.DropDown)
                          and [x.Text for x in c.Items] == logic.CORNER_CHOICES)
            corner.choose("Yes: two streets")
            click(dialog, "Change…")
        else:                                        # back from the picks: confirm the district and Check
            tick = next(c for c in dialog.Children if isinstance(c, fakes.CheckBox) and c.Text == logic.ZONE_TICK)
            tick.Checked = True
            tick.CheckedChanged.fire(tick, None)
            click(dialog, "Check")

    real = G["_get_point"]
    G["_get_point"] = get_point
    G["STATE"]["on_box_shown"] = script
    try:
        options = G["ask"]({"cmd": "options", "jurisdiction": G["JURISDICTION"]})
        facts = G["confirm"](DOC, facts0, options, "check")      # Edit site…'s box
    finally:
        G["_get_point"] = real
        G["STATE"].pop("on_box_shown", None)
    G["save_facts"](DOC, facts)
    result = run_check(G, DOC, report=False)
    items = items_of(G)
    want = [[[round(c, 4) for c in G["_feet_point"](DOC, p)[:2]] for p in s] for s in (segs[0], segs[len(segs) // 2])]
    got = [[[round(c, 4) for c in p] for p in line] for line in facts.get("street_line") or []]
    front = {n: (i["status"], i.get("reason")) for n, i in items.items() if n.startswith("Front yard")}
    D["corner_facts"] = facts
    ok = (facts.get("corner_lot") is True and got == want and len(prompts) == 3
          and prompts[0] == "Click each lot line on a street (0 picked); Enter when done"
          and prompts[-1] == "Click each lot line on a street (2 picked); Enter when done"
          and "street_ids" not in facts and result is not None
          and all(s != "complies" for s, _ in front.values()))
    return ok, ("The box (gordium_ui.start_box) answered Yes, Change… returned pick:street; _pick_outcome read 2 clicks then "
                "Enter (prompts %r … %r); the facts now hold %d street lines %s (the two clicked, unnamed), corner_lot=%s. "
                "The check ran: %r; front-yard rows %s (none complies on a corner lot until the front is settled)." %
                (prompts[0], prompts[-1], len(got), got, facts.get("corner_lot"), result and result["view"]["summary"],
                 front))


@claim("demo_6a_tick_on_the_sample", "demo", W9,
       "The panel's Show neighbourhood tick on the smoke's own file (the sample, 106 Ithaca Rd, not looked up): is "
       "there a neighbourhood to hide and show?", "rhino", "partial",
       "Ben's run: on the sample the tester must Look up the address (internet, or the recorded fixture) for a "
       "neighbourhood to exist; then the real fetch, drawing and tick (claim 6b's logic).")
def _():
    F.Rhino.RhinoDoc.ActiveDoc = DOC
    for name in ("draw_context", "_context_payload"):          # the real ones: what the tick does here
        exec(source_of(name), G)
    said = []
    try:
        frame = logic.context_frame(G["current_facts"](DOC), G["_ui_state"](DOC))
        for on in (False, True):
            G["show_context"](on)
            said.append(G["STATE"]["said"][-1])
    finally:
        G["draw_context"] = lambda doc, frame, left=0: G["say"]("(draw_context: not run headless)")
    ok = frame is None and said == ["Neighbourhood off (none drawn in this file).", logic.NO_CONTEXT]
    return ok, ("On the sample the neighbourhood frame is %r (rhino_logic.context_frame: never around the sample, review "
                "round 3), so nothing was drawn at Draw; untick said %r, tick said %r. So the smoke's tick step only "
                "means something after Look up." % (frame, said[0], said[1]))


@claim("demo_6b_tick_hides_shows_layers_stay_locked", "demo", W9,
       "With a neighbourhood drawn (a looked-up lot), the tick hides and shows the neighbourhood layers, saved with "
       "the file, and the layers stay locked as they should (Parcels, Streets, Notes locked; Gordium::Context and "
       "Buildings not)", "rhino", "partial",
       "Real Rhino 8 layers: the parent-visibility-sets-sublayer-locks behaviour is modelled here as the Rhino job "
       "found it (test_context_box.py's _Layer); only Rhino shows the layers really hide and stay locked, and the "
       "real fetch and drawing of the neighbourhood.")
def _():
    class Layer(fakes.FLayer):                       # Rhino 8: a parent's IsVisible gives its sublayers its lock
        def __init__(self, table, path):
            self.table = table
            super().__init__(path)

        @property
        def IsVisible(self):
            return self._v

        @IsVisible.setter
        def IsVisible(self, on):
            self._v = on
            for sub in self.table:
                if sub.FullPath.startswith(self.FullPath + "::"):
                    sub.IsLocked = self.IsLocked

    doc = fakes.FDoc()
    for p in ("Gordium", logic.CONTEXT, logic.CONTEXT + "::Parcels", logic.CONTEXT + "::Streets",
              logic.CONTEXT + "::Buildings", logic.CONTEXT + "::Notes"):
        doc.Layers.append(Layer(doc.Layers, p))
    # what draw_context leaves: the layers locked as it locks them, and its record (every stored layer drawn)
    G["_lock_context"](doc, True)
    doc.Strings.SetString(G["SECTION"], logic.CONTEXT_ENTRY, json.dumps(
        {"frame": {"lot": "106"}, "layers": {k: {"store": "raw", "status": "found"}
                                               for k in ("nys_parcels", "streets", "buildings")}}))
    G["_context_record"] = lambda d: json.loads(d.Strings.GetValue(G["SECTION"], logic.CONTEXT_ENTRY) or "null")
    want = {"Context": False, "Parcels": True, "Streets": True, "Buildings": False, "Notes": True}
    F.Rhino.RhinoDoc.ActiveDoc = doc
    seen = []
    try:
        for on in (False, True, False, True):
            G["show_context"](on)
            ctx = [x for x in doc.Layers if logic.on_layer(x.FullPath, logic.CONTEXT)]
            seen.append({"on": on, "visible": sorted({x.IsVisible for x in ctx}),
                         "locks": {x.FullPath.split("::")[-1]: x.IsLocked for x in ctx},
                         "saved": logic.context_shown(G["_ui_state"](doc)), "said": G["STATE"]["said"][-1]})
    finally:
        F.Rhino.RhinoDoc.ActiveDoc = DOC
        G["_context_record"] = lambda d: None
    ok = (all(s["visible"] == [s["on"]] for s in seen) and all(s["locks"] == want for s in seen)
          and [s["saved"] for s in seen] == [False, True, False, True])
    return ok, ("show_context off, on, off, on with a drawn neighbourhood (its record in the file; Rhino 8's lock "
                "behaviour modelled): visible %s; locks after every tick %s; saved in the file as %s; the panel said "
                "%r / %r." % ([s["visible"] for s in seen], "as wanted" if all(s["locks"] == want for s in seen)
                              else [s["locks"] for s in seen], [s["saved"] for s in seen], seen[0]["said"],
                              seen[1]["said"]))


# ================================================================================================================
# (B) #15's pass 2: every claim in apps/rhino_plugin/tests/pass2_in_rhino.py, step by step
# ================================================================================================================

P = plugin()
PDOC = fakes.FDoc(path=str(TMP / "pass2.3dm"))
A = {}


def pass2_open():
    F.Rhino.RhinoDoc.ActiveDoc = PDOC
    P["STATE"]["auto_ok"] = True                    # as the pass-2 script runs it: the scripted Draw
    P["STATE"]["on_confirm"] = lambda *a: None
    A["result"] = P["gordium_check"]()
    options = P["ask"]({"cmd": "options", "jurisdiction": P["JURISDICTION"]})
    facts = dict(P["current_facts"](PDOC))
    A["state"] = P["_box_state"](PDOC, facts, options, P["_ui_state"](PDOC), "check")
    A["facts"] = facts


step(pass2_open)


@claim("pr15_open_0_tax_map_lot", "pr15", "pass2 step open",
       "The sample's lot is from the tax map (not a survey)", "code", "covered",
       "Nothing beyond the facts: the in-Rhino step reads the same saved fact.")
def _():
    s = bool(P["current_facts"](PDOC).get("lot_surveyed"))
    return (not s and A["result"] is not None), ("GordiumCheck on an empty file went through GordiumStart with the scripted "
                                                 "Draw; the saved lot facts say lot_surveyed=%s; the house was drawn and "
                                                 "checked (%r)." % (s, A["result"] and A["result"]["view"]["summary"]))


@claim("pr15_open_8_address_there", "pr15", "pass2 step open",
       "The box's state keeps the address (106 Ithaca Rd) as well as the street", "code", "covered",
       "Nothing beyond the box's state; the dialog showing it is the demo's box claim.")
def _():
    return bool(A["state"].get("address")), "_box_state after Draw: address %r." % A["state"].get("address")


@claim("pr15_open_8_street_ithaca_rd_from_lookup", "pr15", "pass2 step open",
       "The sample's Street side reads 'Ithaca Rd', the street the lookup found (not taken from the address), sourced "
       "to the tax map", "code", "covered",
       "Nothing beyond the box's rows; the Eto dialog drawing that row is Rhino's.")
def _():
    street = next(r_ for r_ in logic.box_rows(A["state"]) if r_["key"] == "street")
    src = A["state"].get("street_source") or ""
    return (street["text"] == "Ithaca Rd" and "tax map" in src), (
        "logic.box_rows(_box_state(...)) street row text %r, street_source %r." % (street["text"], src))


def pass2_side_yard():
    items = items_of(P)
    side = next(i for n, i in items.items() if n.startswith("Side yard") and i.get("points"))
    a, b = (P["_model_point"](PDOC, q) for q in side["points"][:2])
    ring = P["STATE"]["start"]["floors"][0]["outline"]
    mid = P["_model_point"](PDOC, (sum(q[0] for q in ring) / len(ring), sum(q[1] for q in ring) / len(ring)))
    wall, line = (a, b) if a.DistanceTo(mid) < b.DistanceTo(mid) else (b, a)
    out = wall - line
    out.Unitize()
    have, need = wall.DistanceTo(line), feet(side["required"].split(" ")[-1])
    move = -out * (have - need + 3.0)
    transform_buildings(P, PDOC, translation([move.X, move.Y, move.Z]))
    run_check(P, PDOC, report=False)
    now = items_of(P)[side["name"]]
    A.update(side=side["name"], out=out, have=have, need=need, now=now, before_side=side)


step(pass2_side_yard)


@claim("pr15_side_yard_1_to_comply_text", "pr15", "pass2 step side_yard",
       "With the house moved until a side yard is 3'-0\" short as drawn (tax-map lot), that row's To comply says "
       "'whatever the survey shows', asks for the requirement plus the 2'-0\" margin for every part of the building, "
       "and gives where it is now", "code", "covered",
       "Nothing beyond the row: the panel showing it is the next claim.")
def _():
    hint = A["now"].get("hint") or ""
    m = re.fullmatch(r"To comply whatever the survey shows: keep every part of the building at least "
                     r"(\S+(?: \d/\d)?\") from the \w+ side lot line as drawn \((\S+(?: \d/\d)?\") required, the "
                     r"lot lines ±2'-0\"\) — now (\S+(?: \d/\d)?\") at its closest\.", hint)
    ok = (m is not None and abs(feet(m.group(1)) - feet(m.group(2)) - 2.0) < 0.02
          and abs(feet(m.group(2)) - feet(m.group(3)) - 3.0) < 0.02)
    if m:
        A["gap"] = feet(m.group(1)) - feet(m.group(3))
    return ok, ("%s was %.2f ft from its lot line (needs %.2f); the house moved %.2f ft toward it; the row is now %s, "
                "proposed %s; its hint %r." % (A["side"], A["have"], A["need"], A["have"] - A["need"] + 3.0,
                                               A["now"]["status"], A["now"]["proposed"], hint))


@claim("pr15_side_yard_1_panel_shows_it", "pr15", "pass2 step side_yard",
       "The panel's detail for that row shows the To comply line", "rhino", "partial",
       "The real Eto panel laying out and rendering that label (wrapping, fonts, docked width).")
def _():
    shown = [c.Text for c in detail_of(P, A["now"], P["STATE"]["view"]).Children if isinstance(c, fakes.Label)]
    hint = A["now"].get("hint") or ""
    return (bool(hint) and hint in shown), ("gordium_ui.show_detail built %d labels for the selected row; the hint is "
                                            "among them: %s." % (len(shown), hint in shown))


def pass2_apply_move():
    before = {n: i["status"] for n, i in items_of(P).items()}
    out = A["out"]
    corners = []
    for o in P["_buildings"](PDOC):
        corners += o.Geometry.GetBoundingBox(True).GetCorners()
    box = fakes.FBox.Empty
    for q in corners:
        box.Union(q)
    corners = box.GetCorners()
    proj = [q * out for q in corners]
    far = corners[proj.index(max(proj))]
    width = max(proj) - min(proj)
    s = (width - A["gap"]) / width
    A["pull"] = (far, out, s)
    transform_buildings(P, PDOC, scale_along([far.X, far.Y, far.Z], [out.X, out.Y, out.Z], s))
    run_check(P, PDOC, report=False)
    A["before"], A["after"] = before, items_of(P)


step(pass2_apply_move)


@claim("pr15_apply_move_1_row_complies", "pr15", "pass2 step apply_move",
       "Doing exactly what To comply said (the near side wall pulled in to the distance it gave, the rest kept) makes "
       "that row comply", "code", "covered",
       "Rhino's own Scale on the real solids (the same transform here, applied by rhino3dm).")
def _():
    now = A["after"][A["side"]]
    return now["status"] == "complies", ("The side wall pulled in by %.3f ft (scaled along the yard's direction about the "
                                         "far side, s=%.4f); %s is now %s, proposed %s, delta %r." %
                                         (A["gap"], A["pull"][2], A["side"], now["status"], now["proposed"],
                                          now.get("delta")))


@claim("pr15_apply_move_1_no_other_row_worse", "pr15", "pass2 step apply_move",
       "…and no other row gets worse", "code", "covered", "Nothing beyond the statuses.")
def _():
    rank = {"does_not_comply": 0, "needs_review": 1, "complies": 2}
    worse = [(n, A["before"][n], i["status"]) for n, i in A["after"].items()
             if n in A["before"] and A["before"][n] in rank and i["status"] in rank
             and rank[i["status"]] < rank[A["before"][n]]]
    return not worse, "Rows compared before/after the pull: %d; worse: %s." % (len(A["after"]), worse or "none")


@claim("pr15_zoom_3_selects_row_objects", "pr15", "pass2 step zoom",
       "Zoom to on that row selects exactly its objects (and frames them in Top)", "rhino", "partial",
       "The real viewport zoom and Rhino's selection highlight on screen.")
def _():
    now = items_of(P)[A["side"]]
    P["zoom_to"](now)
    picked = [o.Id for o in PDOC.Objects.GetSelectedObjects(False, False)]
    top = PDOC.Views.ActiveView
    ok = bool(now.get("objects")) and set(picked) == set(now["objects"]) and top.Name == "Top"
    return ok, ("zoom_to(row) selected %d object(s) %s; the row names %s; active view %s; said %r." %
                (len(picked), [P["_find"](PDOC, i).Attributes.Name for i in picked], len(now.get("objects") or []),
                 top.Name, P["STATE"]["said"][-1:]))


def pass2_button():
    far, out, s = A["pull"]
    transform_buildings(P, PDOC, scale_along([far.X, far.Y, far.Z], [out.X, out.Y, out.Z], 1.0 / s))   # undone
    run_check(P, PDOC, report=False)
    row_ = next(i for i in P["STATE"]["view"]["items"] if i.get("needs"))
    kids = detail_of(P, row_, P["STATE"]["view"]).Children
    texts = [(type(c).__name__, getattr(c, "Text", None)) for c in kids]
    words = logic.enter_words(row_["needs"]) + "…"
    A["button"] = (row_, kids, texts, words)


step(pass2_button)


@claim("pr15_button_2_after_reason", "pr15", "pass2 step button",
       "The row waiting on stated facts (Parking): its 'Enter …' button comes right after the reason", "rhino",
       "partial", "The real panel's layout order on screen (Eto's Children of the real detail panel).")
def _():
    row_, kids, texts, words = A["button"]
    b = next(k for k, c in enumerate(kids) if isinstance(c, fakes.Button) and c.Text == words)
    reason = next(k for k, c in enumerate(kids) if isinstance(c, fakes.Label) and c.Text == row_.get("reason"))
    between = [t for _, t in texts[reason + 1:b] if t]
    return (reason < b and not between), ("Row %r, reason %r, button %r: reason at %d, button at %d, text between: %s." %
                                          (row_["name"], row_.get("reason"), words, reason, b, between or "none"))


@claim("pr15_button_2_words_not_repeated", "pr15", "pass2 step button",
       "…and its words aren't repeated as text", "rhino", "partial", "The real panel's labels.")
def _():
    row_, kids, texts, words = A["button"]
    dup = [c.Text for c in kids if isinstance(c, fakes.Label) and (c.Text or "").rstrip("…") == words.rstrip("…")]
    return not dup, "No label repeats %r (%d controls in the detail)." % (words, len(kids))


@claim("pr15_button_2_on_screen_without_scrolling", "pr15", "pass2 step button",
       "…and the button is on screen without scrolling", "rhino", "partial",
       "Pixels: the button's position inside the real panel's scroll area at Rhino's panel size. Proven here only that "
       "it is placed before every long section (the order); not where it lands on screen.")
def _():
    row_, kids, texts, words = A["button"]
    b = next(k for k, c in enumerate(kids) if isinstance(c, fakes.Button) and c.Text == words)
    labels_before = sum(1 for c in kids[:b] if isinstance(c, fakes.Label))
    labels_after = sum(1 for c in kids[b:] if isinstance(c, fakes.Label))
    return labels_before <= 3, ("The button is preceded by %d labels (title, line, reason) and followed by %d (notes, "
                                "quotes, citation): it sits above everything long. Its screen position is not measured "
                                "here." % (labels_before, labels_after))


def pass2_corner():
    lot = P["_find"](PDOC, P["current_facts"](PDOC).get("lot_id") or "")
    segs = list(P["_segments"](lot.Geometry))
    mids = [(s[0] + s[1]) / 2 for s in (segs[0], segs[len(segs) // 2])]
    clicks = [(F.Rhino.Commands.Result.Success, m) for m in mids] + [(F.Rhino.Commands.Result.Nothing, None)]
    prompts = []

    def get_point(prompt):
        prompts.append(prompt)
        return clicks.pop(0)

    facts = dict(P["current_facts"](PDOC), corner_lot=True)
    saved = dict(P["_ui_state"](PDOC))
    real = P["_get_point"]
    P["_get_point"] = get_point
    try:
        facts, saved = P["_box_pick"](PDOC, "street", facts, saved, logic.BoxSession(Table(PDOC)))
    finally:
        P["_get_point"] = real
    options = P["ask"]({"cmd": "options", "jurisdiction": P["JURISDICTION"]})
    state = dict(P["_box_state"](PDOC, facts, options, saved, "check"), corner_lot=False)
    after, after_ui = P["_apply_box"](PDOC, facts, state, saved)
    A["corner"] = (prompts, facts, saved, after, after_ui)


step(pass2_corner)


@claim("pr15_corner_10_takes_every_line", "pr15", "pass2 step corner",
       "A corner lot's street side takes every lot line clicked, Enter when done", "rhino", "partial",
       "Rhino's GetPoint at the command line and the click landing nearest the intended lot line in the viewport.")
def _():
    prompts, facts, *_ = A["corner"]
    lines = facts.get("street_line") or []
    ok = (len(lines) == 2 and prompts[0].startswith("Click each lot line on a street")
          and "(2 picked); Enter when done" in prompts[-1])
    return ok, ("_box_pick('street') on a corner lot: prompts %s; street lines now %d: %s." %
                (prompts, len(lines), [[[round(c, 2) for c in p] for p in l] for l in lines]))


@claim("pr15_corner_12_no_drops_both", "pr15", "pass2 step corner",
       "Answering No (not a corner lot) in the box drops both streets' lines (to be picked again)", "code", "covered",
       "Nothing beyond the facts the box saves.")
def _():
    after = A["corner"][3]
    return (not after.get("street_line") and after.get("corner_lot") is False), (
        "_apply_box with Corner lot? No: street_line=%r, corner_lot=%r, street_ids=%r." %
        (after.get("street_line"), after.get("corner_lot"), after.get("street_ids")))


step(lambda: A.__setitem__("grey", next(i for i in P["STATE"]["view"]["items"] if i["group"] == "not_covered")))


@claim("pr15_grey_9_group_not_checked_yet", "pr15", "pass2 step grey",
       "Rules not in Gordium yet are grouped as 'Not checked yet'", "code", "covered",
       "The tree's group header drawn in the real panel.")
def _():
    heads = [gr["title"] for gr in P["STATE"]["view"]["groups"]]
    return ("Not checked yet" in heads), "The view's groups: %s." % heads


@claim("pr15_grey_9_row_says_not_in_gordium", "pr15", "pass2 step grey",
       "The row's detail says 'Not in Gordium yet — coming in a later version. Check this by hand for now: <section>'",
       "rhino", "partial", "The real Eto label showing it.")
def _():
    g = A["grey"]
    shown = [c.Text for c in detail_of(P, g, P["STATE"]["view"]).Children if isinstance(c, fakes.Label)]
    want = "Not in Gordium yet — coming in a later version. Check this by hand for now: " + g["detail"]["citation"]
    A["grey_shown"] = shown
    return (want in shown), "Row %r; detail labels %s; wanted %r." % (g["name"], shown[:4], want)


@claim("pr15_grey_9_headed_not_checked_yet", "pr15", "pass2 step grey",
       "Its detail is headed '… · Not checked yet'", "rhino", "partial", "The real Eto label (bold, coloured).")
def _():
    shown = A.get("grey_shown") or []
    return (bool(shown) and shown[0].endswith(" · Not checked yet")), "First detail label: %r." % (shown[:1],)


def frame_draws(g, doc, o, views, active):
    """draw_screen(o, e) for each view, Rhino's DrawForeground; ui.draw_text_box / label_at recorded (as pass2 does)."""
    calls, labels = [], []
    put, box = ui.label_at, ui.draw_text_box

    def record_box(d, rows, *rest):
        calls.append({"view": d.view, "rows": list(rows), "size": rest[-1]})
        return box(d, rows, *rest)

    def record_label(d, viewport, point, text, *rest, **kw):
        lead = False
        if kw.get("leader") and kw.get("along") is not None:
            a, b = (viewport.WorldToClient(q) for q in kw["along"])
            lead = logic.needs_leader(((b.X - a.X) ** 2 + (b.Y - a.Y) ** 2) ** 0.5, logic.label_width(text, 11))
        labels.append((d.view, text, lead))
        return put(d, viewport, point, text, *rest, **kw)

    doc.Views.ActiveView = doc.Views.Find(active)
    drawn = []
    ui.label_at, ui.draw_text_box = record_label, record_box
    try:
        for v in views:
            e = types.SimpleNamespace(RhinoDoc=doc, Viewport=v.ActiveViewport,
                                      Display=fakes.Anything())
            e.Display.view = v.Name
            if g["_here"](o, e):
                drawn.append(v.Name)
            g["draw_screen"](o, e)
    finally:
        ui.label_at, ui.draw_text_box = put, box
    return calls, labels, drawn


def pass2_labels():
    F.Rhino.RhinoDoc.ActiveDoc = PDOC
    P["set_labels"](True)
    run_check(P, PDOC, report=False)                 # (turning labels on re-checks)
    o = overlay_for(P, PDOC, P["STATE"]["result"], P["current_facts"](PDOC))
    box = fakes.FBox.Empty
    for q in o.lot_outline:
        box.Union(q)
    for x in P["_buildings"](PDOC):
        box.Union(x.Geometry.GetBoundingBox(True))
    for env in o.envelope_lines or []:
        for q in env:
            box.Union(q)
    box.Inflate(box.Diagonal.Length * 0.12)
    for v in PDOC.Views:
        v.ActiveViewport.ZoomBoundingBox(box)
    A["labels"] = (o,) + frame_draws(P, PDOC, o, list(PDOC.Views), "Perspective")


step(pass2_labels)


@claim("pr15_labels_4_height_limit_13pt", "pr15", "pass2 step labels",
       "With labels on, the 'Height limit' label is drawn at 13 pt (in the elevations)", "rhino", "partial",
       "The text really rendered at 13 pt in Front/Right on Rhino's display pipeline.")
def _():
    o, calls, labels, drawn = A["labels"]
    limit = o.height_limit[1] if o.height_limit else None
    height = [c for c in calls if c["rows"] == [limit]]
    return (bool(height) and all(c["size"] == 13 for c in height)), (
        "draw_screen in Top, Front, Right and Perspective: the label %r was drawn in %s at sizes %s." %
        (limit, [c["view"] for c in height], sorted({c["size"] for c in height})))


@claim("pr15_labels_5_every_view_drawn", "pr15", "pass2 step labels",
       "Every view was drawn (the drawing is for this document in all four views)", "rhino", "partial",
       "That Rhino really redraws all four viewports and calls DrawForeground in each; here only that the overlay "
       "accepts every view of its document (_here) and draws there without error.")
def _():
    o, calls, labels, drawn = A["labels"]
    return len(drawn) == 4, "_here(o, e) was true for %s (4 views), and draw_screen ran in each without error." % drawn


@claim("pr15_labels_5_status_box_active_view_only", "pr15", "pass2 step labels",
       "The status box is drawn once, in the active view only", "rhino", "partial",
       "Which view Rhino treats as active on screen, and the box really appearing there only.")
def _():
    o, calls, labels, drawn = A["labels"]
    rows = P["_status_rows"](o, P["stale"](o))
    status = [c["view"] for c in calls if c["rows"] == rows]
    return status == ["Perspective"], ("The status box %r was drawn in %s with Perspective active." % (rows[0], status))


def pass2_scale(w, h):
    doc = PDOC
    for v in doc.Views:
        v.ActiveViewport.Bounds.Width = v.ActiveViewport.Size.Width = w
        v.ActiveViewport.Bounds.Height = v.ActiveViewport.Size.Height = h
    F.Rhino.RhinoDoc.ActiveDoc = doc
    o = A["labels"][0]
    top = doc.Views.Find("Top")
    lot = fakes.FBox.Empty
    for q in o.lot_outline:
        lot.Union(q)
    c = lot.Center
    half = 750.0
    far = fakes.FBox(fakes.P3(c.X - half, c.Y - half, 0), fakes.P3(c.X + half, c.Y + half, 0))
    top.ActiveViewport.ZoomBoundingBox(far)
    calls_far, labels_far, _ = frame_draws(P, doc, o, [top], "Top")
    near = fakes.FBox(lot.Min, lot.Max)
    near.Inflate(lot.Diagonal.Length * 0.15)
    top.ActiveViewport.ZoomBoundingBox(near)
    calls_near, labels_near, _ = frame_draws(P, doc, o, [top], "Top")
    rows = P["_status_rows"](o, P["stale"](o))
    edges = sorted({t for _, t, _ in o.edge_labels})
    return {"far_labels": [t for _, t, _ in labels_far], "far_box": sum(c_["rows"] == rows for c_ in calls_far),
            "near_labels": [t for _, t, _ in labels_near], "near_box": sum(c_["rows"] == rows for c_ in calls_near),
            "edges": edges, "led": sorted({t for _, t, lead in labels_near if lead}), "size": (w, h)}


step(lambda: A.__setitem__("scale", [pass2_scale(1000, 640), pass2_scale(700, 450)]))


@claim("pr15_scale_7_no_plan_labels_zoomed_out", "pr15", "pass2 step scale",
       "Labels on, Top zoomed out to a 1,500 ft square round the lot: no plan label is drawn", "rhino", "partial",
       "The real Top viewport at Ben's window size; checked here at 1000x640 and 700x450 pixels.")
def _():
    s = A["scale"]
    return all(x["far_labels"] == [] for x in s), "Plan labels drawn zoomed out: %s." % [(x["size"], x["far_labels"]) for x in s]


@claim("pr15_scale_7_status_box_stays", "pr15", "pass2 step scale",
       "The status box stays, zoomed out and zoomed in", "rhino", "partial", "The box really drawn in Rhino's Top view.")
def _():
    s = A["scale"]
    return all(x["far_box"] >= 1 and x["near_box"] >= 1 for x in s), (
        "Status boxes drawn (zoomed out, zoomed in): %s." % [(x["size"], x["far_box"], x["near_box"]) for x in s])


@claim("pr15_scale_7_labels_back_at_the_lot", "pr15", "pass2 step scale",
       "Zoomed back to the lot: every edge's length and the yards' labels are back", "rhino", "partial",
       "Their placement and legibility on the real screen.")
def _():
    s = A["scale"]
    ok = all(set(x["edges"]) <= set(x["near_labels"]) and len(set(x["near_labels"]) - set(x["edges"])) >= 3 for x in s)
    return ok, ("Edge lengths %s; at the lot drawn %s (others: %s)." %
                (s[0]["edges"], [(x["size"], len(x["near_labels"])) for x in s],
                 sorted(set(s[0]["near_labels"]) - set(s[0]["edges"]))))


@claim("pr15_scale_7_short_edge_led", "pr15", "pass2 step scale",
       "106's short 10'-4 1/8\" edge keeps its length, with a leader to its label", "rhino", "partial",
       "The leader line really drawn on screen at Ben's zoom and window size.")
def _():
    s = A["scale"]
    ok = all("10'-4 1/8\"" in x["edges"] and "10'-4 1/8\"" in x["led"] for x in s)
    return ok, "Edges with a leader at the lot zoom: %s." % [(x["size"], x["led"]) for x in s]


def pass2_box():
    empty = fakes.FDoc()
    F.Rhino.RhinoDoc.ActiveDoc = empty
    seen = {}

    def shown(dialog):
        seen["buttons"] = [c.Text for c in dialog.Children if isinstance(c, fakes.Button)]
        seen["labels"] = [c.Text for c in dialog.Children if isinstance(c, fakes.Label)]
        seen["ticks"] = [c.Text for c in dialog.Children if isinstance(c, fakes.CheckBox)]
        dialog.Close(False)                           # pass2 closes it with a 10 ms UITimer

    P["STATE"]["auto_ok"] = False
    P["STATE"]["on_box_shown"] = shown
    try:
        options = P["ask"]({"cmd": "options", "jurisdiction": P["JURISDICTION"]})
        out = P["confirm"](empty, P["current_facts"](empty), options, "start")
    finally:
        P["STATE"].pop("on_box_shown", None)
        P["STATE"]["auto_ok"] = True
        F.Rhino.RhinoDoc.ActiveDoc = PDOC
    A["box"] = (seen, out, empty)


step(pass2_box)


@claim("pr15_box_6_shown_with_no_lot", "pr15", "pass2 step box",
       "A new empty file's start box shows 'no lot yet: … Draw puts down the sample lot (106 Ithaca Rd)'", "rhino",
       "partial", "The real Eto dialog on screen.")
def _():
    seen = A["box"][0]
    lot_text = next((t for t in seen.get("labels") or [] if t.startswith("no lot yet")), None)
    return (logic.NO_LOT in (seen.get("labels") or [])), (
        "pass2 wants the box's Lot row to read logic.NO_LOT %r; the box (gordium_ui.start_box from _box_state on an empty "
        "file) reads %r instead: _box_state sets lot_missing = (no lot), and box_rows shows its own 'no lot yet: draw "
        "it, or pick…' text whenever lot_missing is set, so NO_LOT is never shown from the plugin (with a 'Draw my "
        "lot…' button). Buttons: %s." % (logic.NO_LOT, lot_text, seen.get("buttons")))


@claim("pr15_box_6_no_survey_or_change_buttons", "pr15", "pass2 step box",
       "…with no 'Use my survey…' or 'Change…' button until a lot exists", "rhino", "partial", "The real dialog's buttons.")
def _():
    b = A["box"][0].get("buttons") or []
    return (bool(b) and "Use my survey…" not in b and "Change…" not in b), "Buttons in the box: %s." % b


@claim("pr15_box_11_front_lot_line_words", "pr15", "pass2 step box",
       "The box says 'Front lot line (on the street)', what it is, and has the tick 'This is the lot's district'",
       "rhino", "partial", "The real dialog's labels and tick.")
def _():
    seen = A["box"][0]
    ok = ("Front lot line (on the street)" in (seen.get("labels") or []) and logic.STREET_HELP in (seen.get("labels") or [])
          and "This is the lot's district" in (seen.get("ticks") or []))
    return ok, "Labels %s…; ticks %s." % ([t for t in seen.get("labels") or [] if "lot" in t.lower()][:4], seen.get("ticks"))


@claim("pr15_box_6_closes_and_file_closed", "pr15", "pass2 step box",
       "The box closes itself (Cancel: nothing saved, nothing drawn) and the file is closed", "rhino", "partial",
       "The 10 s UITimer closing the real modal dialog, and Rhino closing the document.")
def _():
    seen, out, empty = A["box"]
    return (out is None and not empty.Objects.all and not empty.Strings.d), (
        "confirm() returned %r after the box closed; the empty document still has %d objects and %d saved strings "
        "(closing the document itself is Rhino's)." % (out, len(empty.Objects.all), len(empty.Strings.d)))


# ---- step close (13): exactly one checker process, none after stopping ----------------------------------------------

@claim("pr15_close_13_exactly_one_checker", "pr15", "pass2 step close",
       "After every step, exactly one checker process is Rhino's (also after a reload of the plugin and a second "
       "document)", "rhino", "partial",
       "Rhino's real child processes on macOS, and on Windows Task Manager showing one python (item 2). Here: the "
       "plugin's own _worker/ServerBook on Linux, with this Python process standing in for Rhino.")
def _():
    one = checker_children()
    reload_ = plugin()                                # a reload: a fresh copy, its STATE empty, the old process alive
    reload_["ask"]({"cmd": "options", "jurisdiction": reload_["JURISDICTION"]})
    time.sleep(0.3)
    after_reload = checker_children()
    A["reload"] = reload_
    ok = len(one) == 1 and len(after_reload) == 1 and after_reload != one
    return ok, ("design_checker serve children of this process (standing in for Rhino): after the demo's and pass 2's "
                "runs (two copies of the plugin, one ServerBook) %s; after a plugin reload's first request %s (ServerBook "
                "stopped the earlier one)." % (one, after_reload))


@claim("pr15_close_13_none_left", "pr15", "pass2 step close",
       "Stopped when the script ends: none left", "rhino", "partial",
       "Rhino's real process tree (and Windows Task Manager).")
def _():
    stop_everything(A["reload"], P, G)
    time.sleep(0.5)
    left = checker_children()
    return left == [], "After _stop_worker(): design_checker serve children left: %s." % (left or "none")


# ================================================================================================================

def main():
    out = HERE / "results_demo_pass2.json"
    out.write_text(json.dumps(RESULTS, indent=1, ensure_ascii=False), encoding="utf-8")
    n = {k: sum(1 for x in RESULTS if x["offline"] == k) for k in ("covered", "partial", "none")}
    ok = sum(1 for x in RESULTS if x["offline_ok"])
    print(json.dumps({"claims": len(RESULTS), **n, "passed": ok, "failed": len(RESULTS) - ok, "file": str(out)}))


if __name__ == "__main__":
    main()
