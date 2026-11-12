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
sys.path.insert(0, os.path.join(REPO, "packages", "design_checker", "design_checker"))
import rhino_logic as logic  # noqa: E402  (plain Python, tested in CI: which objects, which facts)
# the place the plugin checks, from the place registry (its jurisdiction.yaml, through rhino_logic's place.json):
# the only place for now; a place picker would set these
JURISDICTION = logic.PLACE["jurisdiction"]
CITY = logic.PLACE["name"]
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
        command = STATE.get("worker_command") or [_python(), "-u", "-m", "design_checker", "serve"]   # (in-Rhino
        p = ui.spawn(list(command), cwd=REPO, env=env,       # tests: a slow checker) (no console on
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
        try:                                         # gone before anything it was writing is looked at (a Cancel:
            p.wait(timeout=2)                        # on Windows a dying process still holds its files)
        except Exception:
            pass
    SERVERS.stop_all()                               # and any an earlier load left running


# the opt-in session recorder: with GORDIUM_RECORD_SESSION set to a folder before Rhino starts, every request to the
# checker, its answer and a copy of the model it sent are saved there (logic.Recorder; the replay test runs them
# again). Off (None) otherwise: nothing is recorded. When on, the command line says so at load.
RECORDER = logic.Recorder.from_env(os.environ)
if RECORDER is not None:
    Rhino.RhinoApp.WriteLine("Gordium: recording every check to " + RECORDER.folder)


def ask(request, cancel=False, on_tick=None):
    """Send one request to the checker and wait for its answer, never on Rhino's thread: the exchange runs as a
    logic.Job and ui.wait waits for it (a slow one shows what the checker is doing, live; Rhino keeps drawing).
    `cancel`: the wait has Cancel, which stops the checker (the next request starts a fresh one) and raises
    logic.WorkCancelled: its answer is never used. A live re-check still running is finished first (one request
    at a time on the checker's pipe: _settle_live)."""
    if STATE.get("asking") is not None:      # Rhino answers while a wait runs (ui.wait): nothing may put a second
        raise RuntimeError(logic.WORKING)    # request on the checker's pipe meanwhile (a command typed, a button)
    held = STATE.get("undo")                 # never wait inside an undo step this script holds open: the architect's
    resume = None                            # edits meanwhile would be taken into Gordium's. It ends here and is
    if held and held[1]:                     # always begun again after the wait, whoever asked, so whatever Gordium
        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(held[0])   # changes next (a commit, the floors) is in a step
        resume = (doc, STATE.get("undo_words"))   # of its own (independent review of 2781a5d, P1: the City-outline
        _end_undo(doc)                            # Draw committed and drew the house in none)
    try:
        return _ask_waiting(request, cancel, on_tick)
    finally:
        if resume is not None and resume[0] is not None:
            words = resume[1] or "Gordium"     # (its name said once, however many waits it spans)
            _begin_undo(resume[0], words if words.endswith(" (continued)") else words + " (continued)")


def _ask_waiting(request, cancel, on_tick):
    _settle_live()
    job = _ask_job(request, cancel)
    STATE["asking"] = job                    # live mode waits while any answer is awaited (_idle)
    try:
        _watch_edits(True)                   # Rhino runs during the wait: an edit made meanwhile is noted
        ui.wait(job, cancel, STATE.get("headless"), on_tick)
    finally:
        _watch_edits(False)
        STATE.pop("asking", None)
        if not job.finished():               # (an error in the wait): never a request left in flight on the pipe
            if not job.cancel():
                _stop_worker()
    return _answer(job)


def _still_front(doc):
    """Whether `doc` is still the document in front (Rhino runs while Gordium waits): if not, the command says so
    (logic.NOT_IN_FRONT) and stops before its box opens on a model that isn't the one in front."""
    front = Rhino.RhinoDoc.ActiveDoc
    return front is not None and front.RuntimeSerialNumber == doc.RuntimeSerialNumber


def _edited(sender, e):
    STATE["edited_at"] = time.time()


def _watch_edits(on):
    """While Gordium waits (ui.wait lets Rhino run), every object added, deleted, changed or re-layered is noted
    (STATE["edited_at"]), live mode on or off, so an answer about the model as it was read is never shown as the model
    now (_changed_during; review of 9a4eee2)."""
    hooks = STATE.pop("edit_watch", None)
    for name, handler in hooks or []:
        _off(Rhino.RhinoDoc, name, handler)
    if on:
        objects = _handler(System.EventHandler[Rhino.DocObjects.RhinoObjectEventArgs], _edited, "notice an edit")
        replaced = _handler(System.EventHandler[Rhino.DocObjects.RhinoReplaceObjectEventArgs], _edited,
                            "notice an edit")
        attributes = _handler(System.EventHandler[Rhino.DocObjects.RhinoModifyObjectAttributesEventArgs], _edited,
                              "notice an edit")
        # what sorts objects into lot and building without touching them: a layer renamed or moved, a block's
        # contents edited, the model's units (review of 5567b94)
        layers = _handler(System.EventHandler[Rhino.DocObjects.Tables.LayerTableEventArgs], _edited,
                          "notice an edit")
        blocks = _handler(System.EventHandler[Rhino.DocObjects.Tables.InstanceDefinitionTableEventArgs], _edited,
                          "notice an edit")
        props = _handler(System.EventHandler[Rhino.DocumentEventArgs], _edited, "notice an edit")
        hooks = [(name, objects) for name in ("AddRhinoObject", "DeleteRhinoObject", "UndeleteRhinoObject")] + \
            [("ReplaceRhinoObject", replaced), ("ModifyObjectAttributes", attributes), ("LayerTableEvent", layers),
             ("InstanceDefinitionTableEvent", blocks), ("DocumentPropertiesChanged", props)]
        for name, handler in hooks:
            _on(Rhino.RhinoDoc, name, handler)
        STATE["edit_watch"] = hooks


def _changed_during(doc_serial, read_at):
    """Whether the model Gordium read at `read_at` (document `doc_serial`) is no longer the one in front: another
    document came to the front, or the model was edited since (logic.checked_while_still)."""
    front = Rhino.RhinoDoc.ActiveDoc
    if front is None or front.RuntimeSerialNumber != doc_serial:
        return True
    edits = [t for t in (STATE.get("edited_at"), STATE.get("dirty")) if t]
    return not logic.checked_while_still(read_at, max(edits) if edits else None)


def _ask_job(request, cancel, facts_first=None):
    """The request sent on its own thread (logic.Job), its progress lines its live step; the checker started (or
    restarted) here, on Rhino's thread. `cancel`: Cancel stops the checker. `facts_first`: saved facts the checker
    reads first, in the same job (load_facts' check: unreadable facts are refused with its words, never checked)."""
    _worker()
    STATE["next_id"] = STATE.get("next_id", 0) + 2
    request = dict(request, id=STATE["next_id"], progress=True)
    sends, lines, limit = STATE["worker_sends"], STATE["worker_lines"], logic.ask_limit(request.get("cmd"))
    first = {"cmd": "facts", "facts": facts_first, "id": STATE["next_id"] - 1} if facts_first is not None else None

    def work(step):                         # only these requests' answers, within their time limits; no pipe I/O
        if first is not None:               # on Rhino's thread
            read = logic.exchange(sends, lines, first, logic.ask_limit("facts"), record=RECORDER)
            if read is None or not read.get("ok"):
                return read
            if (read.get("result") or {}).get("problems"):
                return {"id": request["id"], "ok": False, "error": UNREADABLE}
        return logic.exchange(sends, lines, request, limit, on_step=step, record=RECORDER)

    return logic.Job(work, logic.FIRST_STEP.get(request.get("cmd"), "Working…"),
                     stop=_stop_worker if cancel else None)


def _answer(job):
    """A finished job's answer, read on Rhino's thread: the result, or why there is none."""
    failure = RECORDER.take_failure() if RECORDER is not None else None
    if failure:                              # the recording stopped working: said once, the check goes on
        Rhino.RhinoApp.WriteLine("Gordium: ⚠ the session recording failed (" + failure + "); checks go on unrecorded")
    how, answer = job.outcome()
    if how == "cancelled":
        raise logic.WorkCancelled()
    if how == "error":
        if isinstance(answer, logic.CheckerOutOfStep):
            _stop_worker()
            raise RuntimeError(str(answer) + " (see gordium_worker.log in the temp folder)")
        raise answer
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


def _classified_objects(doc):
    """Every object in the model, hidden and locked ones too, as (object, layer full path, geometry type name,
    whether it is a block holding a building): the one walk the checker's sorting and a reset's questions share."""
    every = Rhino.DocObjects.ObjectEnumeratorSettings()
    every.NormalObjects, every.LockedObjects, every.HiddenObjects = True, True, True   # hidden still counts
    every.IdefObjects = False
    for o in doc.Objects.GetObjectList(every):
        yield (o, doc.Layers[o.Attributes.LayerIndex].FullPath, type(o.Geometry).__name__,
               isinstance(o, Rhino.DocObjects.InstanceObject) and _holds_building(o.InstanceDefinition))


def _sorted_objects(doc):
    """(lot candidates, buildings, problems) for the whole model."""
    lots, buildings, problems = [], [], []
    for o, layer, kind, holds in _classified_objects(doc):
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
                 "segments": [((a.X, a.Y), (b.X, b.Y)) for a, b in _segments(o.Geometry)],
                 "segments_ft": [(_feet_point(doc, a)[:2], _feet_point(doc, b)[:2]) for a, b in _segments(o.Geometry)]}
                for o in lots]                                     # (the street decided in feet: review round 6)
    boxes = [o.Geometry.GetBoundingBox(True) for o in buildings]
    building_data = [{"id": str(o.Id), "bottom": b.Min.Z, "volume": b.Diagonal.X * b.Diagonal.Y * b.Diagonal.Z}
                     for o, b in zip(buildings, boxes)]
    facts = logic.suggested_facts(JURISDICTION, zones, lot_data, building_data)
    return logic.to_feet(facts, _scale(doc))


UNREADABLE = "the saved lot facts can't be read: run GordiumFacts to enter them again"


def _read_facts(doc):
    """The saved facts as written in the file (None: none), not yet checked by the checker (load_facts does)."""
    text = doc.Strings.GetValue(SECTION, ENTRY)
    try:
        facts = json.loads(text) if text else None
    except ValueError:
        raise ValueError(UNREADABLE)
    if facts is not None and not isinstance(facts, dict):
        raise ValueError(UNREADABLE)
    return facts


def load_facts(doc):
    facts = _read_facts(doc)
    unreadable = ValueError(UNREADABLE)
    try:
        problems = ask({"cmd": "facts", "facts": facts})["problems"] if facts is not None else []
    except ValueError as e:             # the checker failed, not the facts: never treated as unreadable (reset)
        raise RuntimeError("the Gordium checker failed: " + str(e))
    if problems:                        # the same check as a facts file
        raise unreadable
    return facts


def current_facts(doc):
    """The saved facts, without a lot or main building that is no longer in the model. logic.NotInFront when another
    file came to the front while they were read (Rhino runs during the checker's wait): every caller that goes on to
    prompt or save stops there, never answers typed while looking at another file saved into this one (independent
    review of #32: the one place, so no caller can miss it)."""
    try:
        facts = load_facts(doc)        # (it waits on the checker, Rhino running: the model is listed after it)
    finally:                           # on every way out, unreadable facts too (their callers then open the box:
        if not _still_front(doc):      # independent review of 2781a5d, P1)
            raise logic.NotInFront(logic.NOT_IN_FRONT)
    lots, buildings, _ = _sorted_objects(doc)
    return logic.drop_stale(facts, {str(o.Id) for o in lots}, {str(o.Id) for o in buildings})


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


def _feet_volume(doc, model_volume):
    """A volume in the model's units cubed, in cubic feet."""
    return model_volume * _scale(doc) ** 3


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
    return logic.result_stale(STATE.get("dirty"), (STATE.get("last") or {}).get("at", 0), time.time(),
                              ui.STALE_SECONDS, STATE.get("live_check") is not None or bool(STATE.get("recheck_owed")))


def draw_scene(o, e):
    """The model-space drawing. Whatever happens in it (a step that raises is caught by the conduit's guard), depth
    testing and depth writing are back on at the end (Rhino's own setting for this pass; review round 1 of
    depth-lines, F3)."""
    try:
        if not _here(o, e):
            return
        d = e.Display
        dark = ui.viewport_dark()
        old = stale(o)
        # Gordium's lines: over everything in plan, depth-tested (hidden behind solids) in every other view
        on_top = logic.lines_on_top(e.Viewport.IsParallelProjection, e.Viewport.CameraDirection.Z)
        # red (does not comply) is drawn last, below: over the amber and everything else (logic.red_last)
        rest, red = logic.red_last(getattr(o, "encroach", None) or [])
        # the see-through fills never hide what is behind them: they write no depth, so a line behind the envelope or
        # a coloured part still shows (review round 1 of depth-lines, F2); the solids in front still hide them
        _see_through(d, True)
        if getattr(o, "yards_zone", None) is not None:          # the required yards, lightly shaded
            d.DrawBrepShaded(o.yards_zone, Rhino.Display.DisplayMaterial(BLUE, 0.9))
        if o.envelope is not None:               # see-through, drawn after the solids so they show through it
            d.DrawBrepShaded(o.envelope, Rhino.Display.DisplayMaterial(BLUE, 0.88))
        _see_through(d, False)
        if o.envelope is not None:
            # its outline only, the top dashed (the height limit): its faces' edges and isocurves banded the
            # elevations (the architect's review, 2026-10-21)
            bottom, top = getattr(o, "envelope_lines", None) or (None, None)
            if bottom is not None:
                _on_top(d, on_top)
                d.DrawPolyline(bottom, BLUE, 1)
                d.DrawPatternedPolyline(top, BLUE, ui.DASHED, 2, False)
                _on_top(d, False)
        _on_top(d, on_top)
        for pts in getattr(o, "unmeasured", None) or []:     # objects on the lot the check doesn't measure: dashed, light
            d.DrawPatternedPolyline(pts, System.Drawing.Color.FromArgb(150, 150, 150), ui.DASHED, 1, True)
        _on_top(d, False)
        if not old:                              # after the envelope, so its blue never tints them (F5)
            # only the part over: amber review, then red (does not comply) over it, so no amber strip ever covers
            # a failing part (logic.red_last; the architect's review, 2026-10-28: the eaves over the failing wall)
            for g, status, _ in rest + red:
                name = logic.highlight(status)
                colour = ui.HIGHLIGHT[name]
                _see_through(d, True)
                d.DrawBrepShaded(g, Rhino.Display.DisplayMaterial(colour, ui.HIGHLIGHT_TRANSPARENCY))
                _see_through(d, False)
                d.DrawBrepWires(g, colour, ui.HIGHLIGHT_EDGE[name])
        for pt in getattr(o, "grade_points", None) or []:           # spot grades
            d.DrawPoint(pt, Rhino.Display.PointStyle.X, 5, ui.status_color("complies", dark))
        _on_top(d, on_top)
        if getattr(o, "lot_outline", None) is not None:              # the property line: phantom (F2)
            pts = o.lot_outline
            d.DrawPatternedPolyline(pts, ui.status_color("complies", dark), ui.PHANTOM, 2, True)
        if not on_top:                                   # the dimensions, in the model: hidden behind the solids
            _scene_dims(o, e, d, dark, old)
        context = STATE.get("context_guides") or {}
        if logic.guides_on_screen(context, e.RhinoDoc.RuntimeSerialNumber) \
                and (STATE.get("context_by_doc") or {}).get(e.RhinoDoc.RuntimeSerialNumber, True):
            for line in context.get("lines") or []:          # the neighbouring footprints: live only, never in the file
                d.DrawPolyline(line, CONTEXT_GUIDE, 1)
        guide = STATE.get("lookup_guide")
        if guide is not None and getattr(o, "confirm", None) is not None:    # only while the start box is open
            d.DrawPatternedPolyline(guide, ui.status_color("needs_review", ui.viewport_dark()), ui.DASHED, 2, True)
        _on_top(d, False)                                # depth testing back as Rhino set it, for what follows
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
        # last of all, the outline of a failing solid the plan can't show a part of: nothing drawn after it covers it
        for g in o.red:                          # a failing solid the plan can't show a part of (kept for blocks, SubD)
            if isinstance(g, rg.Mesh):
                d.DrawMeshWires(g, ui.status_color("does_not_comply", dark))
            else:
                d.DrawBrepWires(g, ui.status_color("does_not_comply", dark), 2)
    finally:
        _on_top(e.Display, False)
        _see_through(e.Display, False)


def _see_through(d, on):
    """A see-through fill (on): drawn depth-tested but writing no depth, so it never hides what lies behind it."""
    d.EnableDepthWriting(not on)


def _on_top(d, on):
    """Draw what follows over everything (on) or depth-tested as Rhino draws the model (off: the default, and
    always where a drawing step ends)."""
    d.EnableDepthTesting(not on)


def _zoomed_in(o, viewport):
    """Whether the lot is at working zoom on screen (logic.labels_shown): judged from the lot's edges, which a lot
    with arcs has too, else its outline (review round 3, F5)."""
    lot_points = [q for _, _, edge in getattr(o, "edge_labels", None) or [] for q in (edge.From, edge.To)]
    return logic.labels_shown(_screen_size(viewport, lot_points or getattr(o, "lot_outline", None)))


def _model_dimension(d, doc, line, color):
    """A dimension drawn in the model (depth-tested): its line and its ticks (logic.model_ticks, 1 ft long), each
    on the same thin halo as on screen (_dimension), so it reads over the red and amber off plan too."""
    a, b = line.From, line.To
    strokes = [line] + [rg.Line(rg.Point3d(*p), rg.Point3d(*q))
                        for p, q in logic.model_ticks((a.X, a.Y, a.Z), (b.X, b.Y, b.Z), _model_length(doc, 1.0))]
    halo = ui.halo(ui.viewport_dark())
    # the halo writes no depth, so the line drawn over it at the same depth is never hidden by it (round 4 of
    # depth-lines: a halo writing depth first could hide its own coloured line); the solids still hide both
    _see_through(d, True)
    for stroke in strokes:
        d.DrawLine(stroke, halo, 2 + 2 * logic.HALO_PX)
    _see_through(d, False)
    for stroke in strokes:
        d.DrawLine(stroke, color, 2)


def _scene_dims(o, e, d, dark, old):
    """The dimensions in a view that isn't plan (perspective, elevations), in the model so that the solids in
    front of them hide them, in the plan's colours (logic.dim_rgb: complying grey): each yard's with its dashed
    required line (not in an elevation, where they would lie on the ground line), and in an elevation the height's
    with its faint limit. Their numbers stay on screen (draw_screen; off plan the height's only). Nothing zoomed
    out to the neighbourhood."""
    zoomed_in = _zoomed_in(o, e.Viewport)
    elevation = logic.is_elevation_view(e.Viewport.IsParallelProjection, e.Viewport.CameraDirection.Z)
    if logic.dims_shown(zoomed_in, elevation):
        for line, _ in getattr(o, "yard_required", None) or []:
            _required(d, line, dark)                     # dashed grey, as in plan (review of the merge, F2)
        for line, _, status in getattr(o, "yard_dims", None) or []:
            _model_dimension(d, e.RhinoDoc, line, ui.dim_color("complies" if old else status, dark))
    height = getattr(o, "height_dim", None)
    if height is not None and elevation and zoomed_in:
        line, _, status, limit = height
        _model_dimension(d, e.RhinoDoc, line, ui.dim_color("complies" if old else status, dark))
        if limit is not None:                        # the limit, faint, across it (seen in Front and Right alike)
            k = _model_length(e.RhinoDoc, 1.5)
            d.DrawLine(rg.Line(limit + rg.Vector3d(-k, k, 0), limit + rg.Vector3d(k, -k, 0)),
                       ui.faint(ui.status_color("complies" if old else status, dark)), 1)


def _model_on_screen(o, viewport):
    """The model's box on screen (x0, y0, x1, y1): the lot's and the house's edges and the yard dimensions."""
    pts = [viewport.WorldToClient(p) for line in getattr(o, "plan_lines", None) or [] for p in (line.From, line.To)]
    return (min(p.X for p in pts), min(p.Y for p in pts), max(p.X for p in pts), max(p.Y for p in pts)) if pts else None


def _notice_box(o, viewport, taken, old):
    """The "no longer complies" notice, if showing in this view (the active one only, G1): (lines, x, y, w, h),
    placed off the model and off the boxes in `taken` (logic.notice_spot), and then taken itself. Never over a
    model changed since the check it was about (`old`, stale(o)): a verdict outlives its model no more than the
    rows' marks do (the Rhino job at #28 92cf742: an earlier scene's notice stayed over the next house)."""
    toast = getattr(o, "toast", None)
    active = Rhino.RhinoDoc.ActiveDoc.Views.ActiveView
    if not toast or old or time.time() >= toast[1] or active is None or viewport.Id != active.ActiveViewportID:
        return None
    placed = logic.notice_place(viewport.Bounds.Width, viewport.Bounds.Height, ["✕ " + line for line in toast[0]],
                                _model_on_screen(o, viewport), taken)    # compact, in a corner clear of the model
    if placed is None:                 # no corner clear of the model: never drawn over it (the panel says it)
        return None
    lines, (x, y), w, h = placed
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


def _screen_line(viewport, line):
    """A model line's two ends on screen: ((x1, y1), (x2, y2))."""
    a, b = viewport.WorldToClient(line.From), viewport.WorldToClient(line.To)
    return [[a.X, a.Y], [b.X, b.Y]]


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


def _required(d, line, dark):
    """A yard's required line: a clear dashed mid-grey across its dimension (Rhino check of #29: the faint line
    barely registered). Its "min" tag is a plan label, placed with the rest (logic.place_dim_label)."""
    d.DrawPatternedLine(line.From, line.To, ui.required_color(dark), ui.DASHED, 2)


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
    zoomed_in = _zoomed_in(o, e.Viewport)
    north = getattr(o, "north", None)
    if plan and north is not None:           # a small north arrow by the lot, true north (the plan may be turned);
        taken.append(ui.north_arrow(d, e.Viewport, north[0], north[1], ui.status_color("complies", dark)))   # no label on it
    # what this frame draws where, kept per view (STATE["drawn"]): the in-Rhino checks read the drawing's own
    # placement, never a copy of it (the Rhino job at 27c8e5d: a claim's own sum disagreed with the screen)
    drawn = {"size": [e.Viewport.Bounds.Width, e.Viewport.Bounds.Height], "model": _model_on_screen(o, e.Viewport),
             "taken": [list(t) for t in taken], "lines": on_screen, "labels": [], "notice": None}
    STATE.setdefault("drawn", {})[str(e.Viewport.Id)] = drawn
    # the notice first (placed off the model and the status box), so no label is drawn under it either
    notice = _notice_box(o, e.Viewport, taken, old)
    drawn["notice"] = list(notice[1:]) if notice is not None else None
    keep = list(taken)                       # the status box, the north arrow, the notice: no label ever covers them
    elevation = logic.is_elevation_view(e.Viewport.IsParallelProjection, e.Viewport.CameraDirection.Z)
    shown = logic.dims_shown(zoomed_in, elevation)     # drawing-style dimensions: none zoomed out, none flat in elevation
    # the lines on screen (over everything) in plan only; elsewhere draw_scene draws them depth-tested
    flat = logic.lines_on_top(e.Viewport.IsParallelProjection, e.Viewport.CameraDirection.Z)
    yard_dims = (getattr(o, "yard_dims", None) or []) if shown else []
    options = getattr(o, "yard_options", None) or {}
    chosen = {k: (options.get(k) or [(line, [])])[0] for k, (line, _, _) in enumerate(yard_dims)}  # its best position
    height = getattr(o, "height_dim", None) if elevation and zoomed_in else None
    dims = [tuple(map(tuple, _screen_line(e.Viewport, c))) for c, _ in chosen.values()] if plan else []
    if height is not None:
        dims.append(tuple(map(tuple, _screen_line(e.Viewport, height[0]))))
    drawn["dims"] = dims                     # the dimension lines: a label keeps off another's (HARD)
    solids = []                              # each building's footprint and coloured part on screen: never under a
    for kind, pts in getattr(o, "plan_solids", None) or []:          # label (their outlines, never their boxes)
        on = [(q.X, q.Y) for q in (e.Viewport.WorldToClient(q) for q in pts)]
        solids.append(logic.hull(on) if kind == "building" else on)
    drawn["hard_shapes"], drawn["hard_boxes"] = solids, [list(t) for t in keep]
    drawn["buildings"] = sum(kind == "building" for kind, _ in getattr(o, "plan_solids", None) or [])
    # the labels to draw, all placed by the one placer (logic.place_dim_label, through LabelRun: failing first, then
    # in review, then complying, the edges' lengths last; rhino-ui's rules, the Rhino job at #29 fc6fbd6): each
    # yard's number only (the drawing's way), a failing or in-review yard's "min" tag at its required line, the
    # height's number in an elevation, each lot edge's length
    items, colors = [], {}
    numbers = getattr(o, "yard_numbers", None) or {}
    o.placed = {}
    for k, (line, text, status) in enumerate(yard_dims):
        color = ui.dim_color("complies" if old else status, dark)
        best, required = chosen[k]
        tags = [] if old else (getattr(o, "yard_tags", None) or {}).get(k) or []
        if flat:                                    # off plan, draw_scene draws them in the model (depth-tested)
            for r in required:
                _required(d, r, dark)                   # dashed grey; its "min" tag is a label (below)
            _dimension(d, e.Viewport, best, color)
        number = numbers.get(k) or text
        if old:
            number = number.split(" ", 1)[1] if number[:1] in ("?", "✕", "✓") else number
        o.placed[k] = (0, None, None, best, required, number)
        if plan and logic.yard_label_shown(labels, status) and zoomed_in:
            key = ("yard", k, number)
            items.append({"key": key, "text": number, "line": tuple(map(tuple, _screen_line(e.Viewport, best))),
                          "size": 11, "status": status})
            colors[key] = (color, False)
            for j, (r, tag) in enumerate(zip(required, tags)):
                key = ("tag", k, j, tag)
                items.append({"key": key, "text": tag, "line": tuple(map(tuple, _screen_line(e.Viewport, r))),
                              "size": logic.TAG_SIZE, "status": status})
                colors[key] = (ui.required_color(dark), False)
    if height is not None:                   # the height, dimensioned up from the grade plane
        line, text, status, limit = height
        color = ui.dim_color("complies" if old else status, dark)
        number = getattr(o, "height_number", None) or text
        if old:
            number = number.split(" ", 1)[1] if number[:1] in ("?", "✕", "✓") else number
        o.placed["height"] = (0, None, None, line, [], number)
        if logic.yard_label_shown(labels, status):
            key = ("height", number)
            items.append({"key": key, "text": number, "line": tuple(map(tuple, _screen_line(e.Viewport, line))),
                          "size": 11, "status": status})
            colors[key] = (color, False)
    edges = (getattr(o, "edge_labels", None) or []) if plan and labels and zoomed_in else []
    for k, (point, text, edge) in enumerate(edges):
        a, b = e.Viewport.WorldToClient(edge.From), e.Viewport.WorldToClient(edge.To)
        key = ("edge", k, text)
        items.append({"key": key, "text": text, "line": ((a.X, a.Y), (b.X, b.Y)), "size": 11, "status": None})
        colors[key] = (ui.status_color("complies", dark), True)
    # placed only once the view is still (logic.place_labels, from _label_tick): never searched in the drawing
    # loop (the Rhino job at 4bb6d4d: zooming with labels on was 2 fps). The same picture as when they were
    # placed: drawn there. Moving: carried along with their lines (logic.follow) until the view settles again.
    vid = str(e.Viewport.Id)
    sig = (tuple(drawn["size"]), tuple(round(v, 1) for s_ in on_screen for q in s_ for v in q),
           tuple(round(v, 1) for shp in solids for q in shp for v in q),
           tuple(tuple(round(v, 1) for v in t) for t in keep), tuple(i["key"] for i in items))
    cached = (STATE.get("label_cache") or {}).get(vid) or {}
    settled = cached.get("sig") == sig
    pending = STATE.get("label_pending") or {}
    spots = cached.get("spots") or {}
    if not settled and items and (pending.get("sig") != sig or pending.get("view") != vid):   # moved: wait again
        carried = {i["key"]: logic.follow(spots[i["key"]], i["line"]) for i in items if i["key"] in spots}
        STATE["label_pending"] = {"view": vid, "doc": o.doc, "sig": sig, "at": time.time(), "items": items,
                                  "size": tuple(drawn["size"]), "keep": [tuple(t) for t in keep], "dims": dims,
                                  "shapes": solids, "lines": obstacles, "carried": carried}
        _label_timer()
    shown = [(item, spots[item["key"]]) for item in items if item["key"] in spots]   # never placed: at rest
    if not settled:                          # moving: only those carried along that keep every HARD rule here and
        shown = logic.shown_while_moving(    # now, the first placed first; the rest hidden until the view rests
            [(item, logic.follow(got, item["line"])) for item, got in shown], tuple(drawn["size"]), keep, dims, solids)
    for item, got in shown:
        color, edge = colors[item["key"]]
        (xa, ya), (xb, yb) = item["line"]
        ui.paint_label(d, ((xa + xb) / 2, (ya + yb) / 2), got, color, dark, edge_leader=edge, line=item["line"])
        drawn["labels"].append([item["text"], [got["left"], got["top"], got["w"], logic.label_height(
            len(got["rows"]), got["size"]), got["top"]], len(got["rows"]), [list(q) for q in item["line"]],
            got["led"], got["size"], got["forced"], got.get("order")])
    drawn["settled"] = settled or not items
    limit = getattr(o, "height_limit", None)
    if limit is not None and logic.is_elevation_view(e.Viewport.IsParallelProjection, e.Viewport.CameraDirection.Z):
        ends = [e.Viewport.WorldToClient(p) for p in limit[0]]
        line_ = ((min(ends, key=lambda p: p.X).X, min(ends, key=lambda p: p.X).Y),
                 (max(ends, key=lambda p: p.X).X, max(ends, key=lambda p: p.X).Y))
        corners = [e.Viewport.WorldToClient(p) for p in (getattr(o, "house_box", None) or [])]
        house = (min(q.X for q in corners), min(q.Y for q in corners), max(q.X for q in corners),
                 max(q.Y for q in corners)) if corners else None
        w, h = ui.text_box_size([limit[1]], 13)
        view = (e.Viewport.Bounds.Width, e.Viewport.Bounds.Height)
        placed_boxes = [tuple(lb[1][:4]) for lb in drawn["labels"]]
        spot = logic.limit_label_spot(line_, house, w, h, view, taken=taken + placed_boxes)   # past the line's
        if spot is not None:                           # end, off the building and its colours (#28 at fc0b023)
            o.placed["limit"] = spot + (w, h)
            taken.append(spot + (w, h))
            ui.draw_text_box(d, [limit[1]], BLUE, int(spot[0]), int(spot[1]), dark, 13)
    if notice is not None:
        lines, x, y, _, _ = notice
        ui.draw_text_box(d, lines, ui.status_color("does_not_comply", dark), int(x), int(y), dark, 13)
    drawn["complete"] = True                 # every label and the notice really drawn this frame (review round 2)
    if not boxed:
        return
    state = "stale" if old else o.message[0]
    color = ui.status_color({"does_not_comply": "does_not_comply", "needs_review": "needs_review"}.get(state, "complies"),
                            dark)
    rows = _status_rows(o, old)
    x, y, _, _ = logic.status_box(e.Viewport.Bounds.Width, rows)
    ui.draw_text_box(d, rows, color, int(x), y, dark, 13)


def _icon_zoom():
    """The display's scaling where Rhino's screen pixels are physical ones (Windows at 150 %: 1.5), for the size of
    the world-axis icon kept clear; 1 on the Mac (its views count in points: the Rhino job at 8bfabdd) or when
    Rhino doesn't say."""
    try:
        if Rhino.Runtime.HostUtils.RunningOnOSX:
            return 1.0
        return min(max(float(Rhino.UI.Dpi.DpiScale()), 1.0), 4.0)
    except Exception:
        return 1.0


logic.AXIS_ICON_SCALE = _icon_zoom()


def _label_timer():
    """The timer that places the labels once the view has been still for LABEL_SETTLE_S (started on demand)."""
    timer = STATE.get("label_timer")
    if timer is None:
        timer = ef.UITimer()
        timer.Interval = 0.05
        timer.Elapsed += logic.guard(logic.current_only(lambda s, e: _label_tick(), _is_current), "place the labels")
        STATE["label_timer"] = timer
        LEFTOVERS["label_timer"] = timer.Stop
    timer.Start()


def _label_tick():
    pending = STATE.get("label_pending")
    if pending is None:
        if STATE.get("label_timer"):
            STATE["label_timer"].Stop()
        return
    if time.time() - pending["at"] >= logic.LABEL_SETTLE_S:
        settle_labels()                      # all at once, in one pass (the Rhino job at 5b46c99: about 70 ms at most,
        # once, at rest; in budgeted ticks the old places showed meanwhile and then jumped)


def settle_labels(budget_s=None):
    """Place the labels the last frame asked for (logic.LabelRun), a few each call (`budget_s`: one label at least;
    None: all, for the in-Rhino scripts), never in the drawing loop: Rhino stays responsive between the timer's
    ticks, and a newer request (the view moved again) starts a new run. Once all are placed: kept for that view
    and its document redrawn, which then draws them where they were placed. Whether a run finished."""
    pending = STATE.get("label_pending")
    if pending is None:
        return False
    run = pending.get("run")
    if run is None:
        run = pending["run"] = logic.LabelRun(pending["items"], pending["size"], pending["keep"], pending["dims"],
                                              pending["shapes"], pending["lines"], pending.get("carried"))
    if not run.step(budget_s):
        return False
    STATE.pop("label_pending", None)
    STATE.setdefault("label_cache", {})[pending["view"]] = {"sig": pending["sig"], "spots": run.spots}
    doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(pending["doc"]) if pending.get("doc") is not None else None
    doc = doc or Rhino.RhinoDoc.ActiveDoc      # the document it was placed for (review of 3446e94)
    if doc is not None:
        doc.Views.Redraw()
    return True


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
    out, wholes = [], {}
    for i in ids or []:
        o = _find(doc, i)
        if o is None:
            continue
        b = _whole_box(o, wholes)
        if b is None:      # no box that covers all of it (_whole_box): nothing to outline, its review row says it
            continue
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
    solid = (solids if solids is not None else _solids_for(doc, [e])).get(e.get("building") or "")
    box = solid.GetBoundingBox(True) if solid is not None else None
    base, top = logic.block_span(e, _feet_length(doc, box.Min.Z) if box is not None and box.IsValid else None,
                                 _feet_length(doc, box.Max.Z) if box is not None and box.IsValid else None)
    block = _prism(doc, e["outline"], base, top)       # reaching the real solid's own top (a vault: block_span)
    if block is None:
        return []
    pieces = None
    if isinstance(solid, rg.Brep) and solid.IsSolid:       # a boolean that raises colours the block, never stops the check
        pieces = logic.guard(lambda: rg.Brep.CreateBooleanIntersection(
            solid, _proud(doc, block.DuplicateBrep()), doc.ModelAbsoluteTolerance),
            "cut the colour to the building's own shape: its whole block is coloured instead")()
    return logic.offending_pieces(pieces, block)


def _actions():
    """What the panel's buttons do (gordium_ui.make_panel): each one gated, so while a start box is open none of them
    touches the model (rhino_logic.gate_actions)."""
    return logic.front_actions(logic.busy_actions(logic.gate_actions(PANEL_ACTIONS(), _box_open, say),
                                                  lambda: STATE.get("asking") is not None, say), say)


def PANEL_ACTIONS():
    return {"zoom": zoom_to, "report": open_report, "envelope": set_envelope, "edit_site": edit_facts,
            "survey": pick_survey, "grade": set_grade, "enter": enter_rooms, "add": add_to_check,
            "legend": lambda: ui.legend(((STATE.get("last") or {}).get("header") or {}).get("code")),
            "retry": lambda: run_check(Rhino.RhinoDoc.ActiveDoc, report=False), "ground": this_is_the_ground,
            "massing": hide_massing, "switch_sides": switch_side_yards, "not_ground": not_the_ground, "labels": set_labels, "main": pick_main_building,
            "adu": pick_adu_building, "context": show_context, "check": check_now, "auto_check": set_auto_check}


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
                _sync_ticks(doc)            # a panel made again: its ticks as the document has them
            if logic.place_panel_now(p.get("placed")):          # once: then where the architect puts it
                p["placed"] = ui.fit_floating(host, Rhino.UI.RhinoEtoApp.MainWindowForDocument(doc) if doc else None)
            return p
    if p is None or not p["form"].Visible:
        p = ui.make_panel(_actions(), context_on=_context_on(doc))
        ui.set_auto_tick(p, _auto(doc))
        STATE["panel_parts"] = p
        LEFTOVERS["panel"] = p["form"].Close
        _sync_ticks(doc)
        p["form"].Show()
    return p


def show_panel(p, result, facts, error=None):
    """Fill the panel from the checker's view (or say the check couldn't run). Kept by name for the scripted
    tests; the panel's contents come only from `result["view"]`."""
    ui.show(p, (result or {}).get("view"), error=error)


def zoom_to(item):
    """Frame the selected item: yards in Top, height and stories in a front elevation (D9)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
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
    with logic.undo_step(doc, logic.UNDO_WORDS["labels"]):
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
    with logic.undo_step(doc, logic.UNDO_WORDS["auto_check"]):    # the setting saved in the file: one undo step
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
    _envelope_everywhere()
    run_check(Rhino.RhinoDoc.ActiveDoc, report=False)


def _envelope_everywhere():
    """The Envelope layer shown or hidden in every open document at once, a start box open or not (the check that
    follows may not run then: review of feature 4, F11)."""
    for d in Rhino.RhinoDoc.OpenDocuments() or []:
        logic.guard(lambda d=d: _show_envelope_layer(d), "show or hide the curves to snap to")()


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
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
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
    replaced = picked != facts.get("lot_id")
    facts = logic.after_lot_pick(facts, picked) if replaced else facts
    facts["lot_surveyed"] = True
    with logic.undo_step(doc, logic.UNDO_WORDS["survey"]):     # one Ctrl+Z puts it all back (asked first, outside)
        saved_ui = logic.settle(_ui_state(doc), "lot")
        if replaced:                                           # another lot: its ground was never looked up
            saved_ui = logic.lot_ground_dropped(saved_ui)
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
    """A row's "Enter …" button: a small dialog (ui.row_dialog) asking only the stated facts it waits for (`needs`,
    the row's own list, logic.row_fields). OK saves exactly those (logic.row_answers_applied: a blank stays unset,
    never 0 or no), each "entered by you" with the day (logic.row_sources), as ONE Undo step, then checks again.
    Cancel, Esc or closing it changes nothing and makes no Undo step. The address, district, use, lot, street side and
    every other fact are never touched (the facts are read as saved: load_facts, never current_facts, which would
    drop a lot no longer drawn). A count of stories below the floors drawn is refused by the measuring: said in its
    words, and nothing is saved."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
    if not needs:
        say("This row isn't waiting for anything you can enter.")
        return
    if not logic.allowed("save_facts", _box_open()):     # nothing writes the facts under an open start box
        say(logic.BOX_BUSY)
        return
    try:
        facts = load_facts(doc)
    except ValueError as e:
        say(str(e))
        return
    if facts is None:
        say("There are no site facts yet: run GordiumStart (or Edit site…) first.")
        return

    answers = ui.row_dialog(logic.answer_words(needs), logic.row_fields(needs, facts),    # OK: words keep it open
                            lambda got: logic.row_problem(facts, needs, got))
    if answers is None:                 # Cancel, Esc, closed: nothing written, so no Undo step
        say("Cancelled: nothing changed.")
        return
    new = logic.row_answers_applied(facts, needs, answers)
    if new == facts:                    # OK with the answers as they were: nothing to save, no Undo step
        say("Nothing new entered: nothing changed.")
        return
    tried = "stories" in needs and new.get("stories") is not None   # the measuring decides if the count can stand:
    if tried:
        refused = _tried(doc, new)      # tried first, unrecorded and put back as stored (never an Undo step)
        if refused:                     # fewer stories than the floors drawn: refused, so nothing is saved
            run_check(doc, report=False)           # the facts as stored, checked again
            say(refused)
            return
    _save_row(doc, needs, new)
    if not tried:                       # (tried: its check was of these very facts)
        run_check(doc, report=False)


def _save_row(doc, needs, new):
    """A row dialog's answers, saved as one Undo step: the facts and the sources of exactly the row's facts."""
    with logic.undo_step(doc, logic.UNDO_WORDS["enter"]):   # (serial 0, inside a command: that record holds it)
        _save_facts(doc, new)
        sources = logic.row_sources(fact_sources(doc), needs, new, logic.city_day())
        doc.Strings.SetString(SECTION, SOURCES_ENTRY, json.dumps(sources))


def _tried(doc, facts):
    """The measuring's words if it refuses `facts` (else None): checked with them saved while undo recording is off,
    then the facts put back exactly as stored, so nothing is left changed and no undo step made (the last check is
    of `facts`: the caller checks again if it doesn't keep them)."""
    stored, recording = doc.Strings.GetValue(SECTION, ENTRY), doc.UndoRecordingEnabled
    doc.UndoRecordingEnabled = False
    try:
        _save_facts(doc, facts)        # (enter_rooms refuses under an open box first)
        run_check(doc, report=False)
        return logic.refused_stories((STATE.get("last") or {}).get("items"))
    except Exception:
        _put_back(doc, stored)
        run_check(doc, report=False)               # never a result left on screen for facts not kept
        raise
    finally:
        _put_back(doc, stored)
        doc.UndoRecordingEnabled = recording         # as it was (never turned on by Gordium)


def _put_back(doc, stored):
    if stored is None:
        doc.Strings.Delete(SECTION, ENTRY)
    else:
        doc.Strings.SetString(SECTION, ENTRY, stored)


def pick_main_building():
    """Pick the main building… (the panel): with several buildings, the one the yards, height and stories are
    measured to. Click it, or choose one; Enter keeps it."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
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
        with logic.undo_step(doc, logic.UNDO_WORDS["main"]):
            save_facts(doc, facts)
            run_check(doc, report=False)
    else:
        run_check(doc, report=False)


def pick_adu_building():
    """Pick the ADU's building… (the panel): a detached accessory dwelling unit's building, the solid its own size,
    height and setbacks are measured from (§325-28C), never the main building. Click it, or choose one; Enter keeps
    it."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
    facts = current_facts(doc)
    buildings = _buildings(doc)
    if len(buildings) < 2:
        say("There is only one building: the main building. Draw the ADU's building on the Building layer first.")
        return
    try:
        picked = _pick(doc, "Click the ADU's building (a solid on the Building layer), or choose one; Enter keeps it",
                       buildings, "Building")
    except Cancelled:
        say("Cancelled: nothing changed.")
        return
    if picked:
        facts["adu_building"] = picked
        with logic.undo_step(doc, logic.UNDO_WORDS["adu"]):
            save_facts(doc, facts)
            run_check(doc, report=False)
    else:
        run_check(doc, report=False)


def add_to_check(ids):
    """Add to check…: objects on the lot that aren't measured go on the Building layer, so every rule measures
    them."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
    if not ids:
        say("Nothing selected to add to the check: pick the objects in the row first.")
        return
    with logic.undo_step(doc, logic.UNDO_WORDS["add"]):        # the Building layer made, if new, in the same step
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
    architect says "This is the ground". One with no bounding box that covers all of it (_whole_box: a block whose
    definition is empty, or whose linked file is missing, unreadable or changed, at any depth; an empty SubD) can't
    be told off the lot: it counts as on the lot (and, in _touching, as touching), never dropped. One whose box
    covers no ground (a point or a line: rhino_logic.plan_box_has_area; a linked block whose file is missing has a
    point box in live Rhino, an upright panel a line) has no footprint to test: near the lot, it counts as on it
    (and touching); far from it, it is off. As the reference adapter (conformance_rhino._left_out) says."""
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
    wholes = {}                                                 # each block definition walked once (_whole_box)
    for o in doc.Objects.GetObjectList(every):
        layer = doc.Layers[o.Attributes.LayerIndex].FullPath
        g = o.Geometry
        could_be = logic.could_be_building(
            type(g).__name__, (isinstance(g, rg.Brep) and g.IsSolid) or (isinstance(g, rg.Mesh) and g.IsClosed),
            g.Faces.Count if isinstance(g, (rg.Brep, rg.Mesh)) else 0)
        if not could_be or str(o.Id) in known_ground or logic.on_layer(layer, LAYERS["building"]) \
                or not logic.left_out_candidate(layer):        # Gordium's own layers, but for the neighbourhood's
            continue
        b = _whole_box(o, wholes)
        if b is None:                                               # nowhere to place it: on the lot, not dropped
            out.append(str(o.Id))
            continue
        box = (b.Min.X, b.Min.Y, b.Max.X, b.Max.Y)                  # its plan box (_plan_box), worked out once
        if not logic.box_near_lot(box, lot_box, reach):             # far from the lot: no outline work
            continue
        if not logic.plan_box_has_area(box) or logic.reaches_into_lot(ring, _plan_points(g), reach, box):
            out.append(str(o.Id))                                   # no footprint to test, or it reaches in
    return out


def _whole_box(o, wholes, depth=0):
    """An object's bounding box, or None when it has none that covers all of it: no valid box (an empty block, an
    empty SubD); or a block whose definition, at any depth, is missing, is empty, isn't what the block is (a linked
    file not found, not readable or changed since it was read: rhino_logic.block_contents_known) or holds an object
    with no box. A linked block whose file has moved holds, in live Rhino 8.35 (Mac), one text label at the centre
    of the last known shape: a valid box of a single point, which said "whole" and "off the lot" (or, placed inside
    another block, added only a point to its box), while the shed it stands for may touch the house. Rhino leaves an
    invalid box out when it joins a block's parts, so a block holding a part with no box has its other parts' box
    alone. The reference adapter (conformance_rhino._box) gives such a block no box, and so does this. `wholes`
    ({definition id: whether it is whole}, one per check) has each definition walked once, however many times it
    is placed."""
    b = o.Geometry.GetBoundingBox(True)
    if not b.IsValid:
        return None
    if isinstance(o, Rhino.DocObjects.InstanceObject):
        definition = o.InstanceDefinition if depth <= 32 else None
        if definition is None:
            return None
        if definition.Id not in wholes:
            try:
                known = logic.block_contents_known(definition.ArchiveFileStatus)
            except Exception:                                       # no status to read: not known
                known = False
            parts = list(definition.GetObjects()) if known else []
            wholes[definition.Id] = bool(parts) and all(_whole_box(p, wholes, depth + 1) is not None for p in parts)
        if not wholes[definition.Id]:
            return None
    return b


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
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
    if not ids:
        say("Nothing selected to mark as the ground: pick the objects in the row first.")
        return
    with logic.undo_step(doc, logic.UNDO_WORDS["ground"]):
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
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
    with logic.undo_step(doc, logic.UNDO_WORDS["not_ground"]):
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
    layers = sorted({logic.MASSING if logic.on_layer(path, logic.MASSING) else path   # its floors' sublayers said
                     for path in (doc.Layers[o.Attributes.LayerIndex].FullPath for o in buildings)})   # once (F3)
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
    say "touching" more often than the shapes do, which only ever makes the check more cautious. One with no box
    that covers all of it (_whole_box: an empty block, a linked block whose file is missing, unreadable or changed,
    or one holding such a block), or whose box covers no ground (rhino_logic.plan_box_has_area: it has no footprint
    to judge by), may be touching, so it counts as touching."""
    gap = _model_length(doc, 0.1)
    boxes = []
    for b in buildings:
        bb = b.Geometry.GetBoundingBox(True)
        bb.Inflate(gap)
        boxes.append(bb)
    out, wholes = [], {}
    for i in ids:
        o = _find(doc, i)
        if o is None:
            continue
        bb = _whole_box(o, wholes)
        if bb is None or not logic.plan_box_has_area((bb.Min.X, bb.Min.Y, bb.Max.X, bb.Max.Y)) \
                or any(rg.BoundingBox.Intersection(bb, k).IsValid for k in boxes):
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
    """The box's state: what is drawn, except that in a file with nothing drawn yet a found lookup's lot and street
    are shown (marked "after Draw": rhino_logic.show_pending_lot, tested in CI)."""
    return logic.start_gate(logic.show_pending_lot(_box_state_drawn(doc, facts, options, saved_ui, mode), facts,
                                                  saved_ui), saved_ui)


def _box_state_drawn(doc, facts, options, saved_ui, mode="check"):
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
            # the uses the district's chart lists (permitted first; the use set kept even if not listed), what a pick
            # not permitted by right means, and the follow-up questions this district's rules need for the use, each
            # with its saved answer (Ben, 2026-10-25; derived from the rulebook: check.options)
            "use_choices": logic.district_use_names(options, facts.get("zone"), facts.get("use")),
            "use_note": logic.use_note(options, facts.get("zone"), facts.get("use")),
            "follow_ups": logic.follow_up_rows(options, facts.get("zone"), facts.get("use"), facts),
            "answers": logic.box_answers(options, facts.get("zone"), facts.get("use"), facts),   # the saved facts
            "options": options,          # for _apply_box and fact_sources: which facts the district and use read
            "lot_area": area, "has_lot": lot is not None, "lot_surveyed": bool(facts.get("lot_surveyed")),
            # the street's name only with its street line (a survey outline or a corner answer drops the line:
            # review round 3, F6); this session's lookup words first, then the name saved at the last Draw
            "street_name": (saved_ui.get("_street_name") or saved_ui.get("street_name") or facts.get("street_name"))
            if facts.get("street_line") else None,
            "street_name_saved": None if saved_ui.get("_street_name") or not facts.get("street_line")
            else saved_ui.get("street_name"),
            "street_source": saved_ui.get("street_source") or source("street"),
            "ground": {"kind": kind, "count": len(points), "range": span, "source": ground_source},
            "ground_fall": saved_ui.get("ground_fall"),     # the looked-up fall: a slope holds height and stories at review
            "no_regrading": bool(saved_ui.get("no_regrading")), "corner_lot": facts.get("corner_lot"),
            "corner_source": saved_ui.get("corner_source") or source("corner_lot"),
            "zones_found": saved_ui.get("_zones_found") or [],
            "design_buffer": saved_ui.get("design_buffer") or "0'-0\"",
            "lot_source": saved_ui.get("lot_source"), "lookup": saved_ui.get("_lookup") or {},
            "known_addresses": logic.known_addresses(saved_ui),     # Draw is off for any other (address_reason)
            "doubts": saved_ui.get("doubts") or {}, "live": saved_ui.get("_live") or {},
            "checked": list(saved_ui.get("checked") or []), "lot_missing": lot is None,
            "_poll": _lookup_poll if (saved_ui.get("_lookup") or {}).get("looking") else None,
            "_progress": _lookup_progress if (saved_ui.get("_lookup") or {}).get("looking") else None,
            "_suggest": SUGGESTER}


def _ft_text(feet):
    inches = int(round(feet * 12 * 8))            # to 1/8 in
    sign = "-" if inches < 0 else ""
    ft, rest = divmod(abs(inches), 96)
    whole, eighth = divmod(rest, 8)
    return "%s%d'-%d%s\"" % (sign, ft, whole, (" %d/8" % eighth) if eighth else "")


def _apply_box(doc, facts, state, saved_ui):
    """The facts (what the checker gets) and the box's own choices, from what the box says."""
    # only the fields shown change (blank: unset, never 0 or no), and what a use said goes with it (by its source:
    # the box's own track across picks, from the saved sources when it opens); with the old use still in the facts
    track = saved_ui.get("_answers") or logic.box_track(facts, fact_sources(doc))
    facts, track = logic.box_applied(facts, state.get("answers"), state["zone"], state["use"], state.get("options"),
                                     track)
    saved_ui = dict(saved_ui, _answers=track)
    facts, saved_ui = logic.box_facts(facts, saved_ui, state)   # a changed corner answer: the street picked again;
    # then the address, district, use and survey as the box says
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


def _place_spots(doc, prompt, layer_path=GRADE_LAYER, changing=lambda: None):
    """Each click places a spot grade; Enter or Esc when done. The ids of the points placed (none: nothing changed).
    `changing`: called before the model is first changed (the start box's undo step begins there)."""
    changing()
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
    """The model as rhino_logic.BoxSession and apply_reset use it: a few plain calls on one document, and `apply`,
    which carries out a start box's edit plan (host_core.edits) through them. `step`: the
    undo step a start box's edits go in (its first edit begins it, unless one is held; the box's caller ends it with
    the facts saved after Draw: the whole box one step, its Cancel's rollback inside it too). None: recovery's own."""

    def __init__(self, doc, step=None):
        self.doc, self.step = doc, step

    def _changing(self):
        if self.step and not STATE.get("undo"):
            _begin_undo(self.doc, self.step)

    def exists(self, object_id):
        return _find(self.doc, object_id or "") is not None

    def delete(self, object_id):
        o = _find(self.doc, object_id)
        if o is not None:
            self._changing()
            self.doc.Objects.Delete(o, True)

    def layer_of(self, object_id):
        return self.doc.Layers[_find(self.doc, object_id).Attributes.LayerIndex].FullPath

    def _move(self, object_id, layer_path, held_from):
        o = _find(self.doc, object_id)
        self._changing()
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
            self._changing()
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
            self._changing()
            self.doc.Layers.Delete(index, True)

    def save_views(self):
        return [(v.ActiveViewportID, Rhino.DocObjects.ViewportInfo(v.ActiveViewport)) for v in self.doc.Views]

    def restore_views(self, saved):
        for view_id, info in saved or []:
            view = self.doc.Views.Find(view_id)
            if view is not None:
                view.ActiveViewport.SetViewProjection(info, True)
        self.doc.Views.Redraw()

    def apply(self, plan, session, facts, saved_ui):
        """A start box's edit plan (logic.reset_edits, logic.lookup_edits) made in this document, step by step in
        its order, through the box's BoxSession `session` (holds, the new objects marked as its own) and this
        table's add_lot / add_spot: (facts, saved_ui) with each "$..." ref swapped for the id Rhino gave it."""
        return logic.carry_out(plan, self, session, facts, saved_ui)

    def add_lot(self, ring, name):
        self._changing()
        return str(_add_lot(self.doc, {"lot": ring, "lot_name": name}))

    def add_spot(self, p):
        self._changing()
        attrs = Rhino.DocObjects.ObjectAttributes()
        attrs.LayerIndex = _layer(self.doc, GRADE_LAYER)
        return str(self.doc.Objects.AddPoint(_model_point(self.doc, p[:2], p[2]), attrs))

    def _on(self, path):
        """Every object on a layer or its sublayers, hidden and locked ones too."""
        return [str(o.Id) for o, layer, _, _ in _classified_objects(self.doc) if logic.on_layer(layer, path)]

    def massing(self):
        """The starting house's floors (Gordium::Massing and its sublayers)."""
        return self._on(logic.MASSING)

    def buildings(self):
        """The architect's buildings as the checker sees them (rhino_logic.own_buildings over the checker's own walk:
        Building and its sublayers, what it can't measure there too, blocks holding one), never the starting house
        or what a box holds."""
        return logic.own_buildings((str(o.Id), layer, kind, holds) for o, layer, kind, holds in
                                   _classified_objects(self.doc))

    def fingerprint(self, ids):
        """The objects' shapes, to tell a starting house as Gordium drew it from one the architect edited."""
        out = []
        for i in sorted(ids):
            o = _find(self.doc, i)
            if o is not None:
                b = o.Geometry.GetBoundingBox(True)
                out.append((i, tuple(round(v, 4) for v in (b.Min.X, b.Min.Y, b.Min.Z, b.Max.X, b.Max.Y, b.Max.Z))))
        return repr(out)

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


def _draw_lot(doc, changing=lambda: None):
    """Draw my lot…: click each corner (Enter closes it, Esc: nothing drawn). The new closed outline's id, or None.
    `changing`: called before the model is changed (the start box's undo step begins there)."""
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
    changing()
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = _layer(doc, LAYERS["lot"])
    attrs.Name = "Lot · drawn by you"
    return str(doc.Objects.AddCurve(rg.PolylineCurve(corners + [corners[0]]), attrs))


def _get_point(prompt):
    """A point clicked at the command line (Enter accepted as done): the box's picks, one place to stand in for."""
    return Rhino.Input.RhinoGet.GetPoint(prompt, True)


def _ask_street_more(question):
    """True (Yes) or False (No), never a default: Enter asks again, with the reason; Esc cancels (Cancelled: in the
    start box, Edit site… included, the pick changes nothing and the box comes back; in change_facts, the
    command-line edit, the whole edit is cancelled, as Esc does at its every prompt). Neither
    default is safe: kept as street, a stretch that isn't can make the frontage long enough to pass lot width (a
    40 ft street with a 15 ft side line bent 20° from it read 55'-0", complies; the truth 40'-0" does not); left
    out, a stretch that is street lets the front yard pass from part of it (street-run review rounds 14 and 15)."""
    prompt = question
    while True:
        go = Rhino.Input.Custom.GetOption()
        go.SetCommandPrompt(prompt)
        yes = go.AddOption("Yes")
        no = go.AddOption("No")
        go.AcceptNothing(True)
        got = go.Get()
        if got == Rhino.Input.GetResult.Option:
            if go.OptionIndex() == yes:
                return True
            if go.OptionIndex() == no:
                return False
        elif got != Rhino.Input.GetResult.Nothing:      # Esc, or Rhino ending the prompt (another command,
            raise Cancelled()                            # closing): never asked again forever (round 16)
        prompt = logic.STREET_ANSWER_NEEDED + question


def _clicked_piece(doc, lot, point):
    """The piece of the lot outline a click is on: the nearest one, whatever its length, never moved to another
    line (street-run review round 7: a click on an arc drawn in short chords jumped to the side line). A short
    piece standing alone (a point drawn twice) is refused by the logic with words to click beside it."""
    return min(_segments(lot.Geometry), key=lambda s: rg.Line(s[0], s[1]).DistanceTo(point, True))


def _outline(doc, lot):
    """The lot outline's pieces, in feet: [[x, y], [x, y]] each, as a click on one is read."""
    return [[_feet_point(doc, a)[:2], _feet_point(doc, b)[:2]] for a, b in _segments(lot.Geometry)]


def _box_pick(doc, what, facts, saved_ui, session):
    """One pick the start box asked for, with the box hidden. Esc or Enter: nothing changes (Esc at any prompt,
    rhino_logic.pick_or_nothing). Every model edit goes through the box's session."""
    try:
        return logic.pick_or_nothing(lambda: _one_pick(doc, what, dict(facts), dict(saved_ui), session),
                                     facts, saved_ui)
    finally:
        _highlight(doc, facts)


def _one_pick(doc, what, facts, saved_ui, session):
    if what == "by_hand":                      # the site by hand (an empty file): the box shows its own rows, once
        refused = logic.by_hand_refused(saved_ui)     # the lookup said outside the City: refused, not asked
        if refused:
            saved_ui["_lookup"] = dict(saved_ui.get("_lookup") or {}, says=refused)
        # the architect says the lot is the City's (an address can't prove it)
        in_city = None if refused else _ask_in_city()
        if in_city:
            _lookup_stop()                     # a lookup still running is never used after this
            STATE.pop("lookup_guide", None)
        facts, saved_ui = logic.choose_by_hand(facts, saved_ui, in_city)
    elif what == "lookup":                     # no town typed: the City's ("106 Ithaca Rd, Ithaca, NY")
        if facts.get("address"):
            facts["address"] = logic.with_city(facts["address"])
        saved_ui = _lookup_start(facts, saved_ui)
    elif what == "lookup_cancel":
        saved_ui = _lookup_cancel(saved_ui)
    elif what == "lookup_done":
        facts, saved_ui = _lookup_done(doc, facts, saved_ui, session)
    elif what == "use_saved":                  # offline: the lookup saved on this computer, marked with its date
        offered_for = saved_ui.pop("_saved_for", None)
        answer = logic.guard(logic.use_saved, "use the saved lookup")(
            saved_ui.pop("_saved_answer", None), offered_for, facts.get("address"))
        if answer:
            facts, saved_ui = _show_answer(doc, answer, facts, saved_ui)
        else:                                  # the address retyped since: the offer dropped, and said (round 6)
            saved_ui["_lookup"] = logic.saved_refused(saved_ui.get("_lookup"), offered_for, facts.get("address"))
    else:                                      # the pick's outcome only; rhino_logic.pick_effect decides the rest
        facts, saved_ui = logic.pick_effect(what, _pick_outcome(doc, what, facts, saved_ui, session), facts, saved_ui)
    _highlight(doc, facts)
    return facts, saved_ui


def _pick_outcome(doc, what, facts, saved_ui, session):
    """What one pick gave, or None (Esc at any prompt, Enter with nothing clicked). Drawn objects go through the
    session. The street: {"lines", "ids": the street lines worked out from the clicks (the whole street a piece is
    on, rhino_logic.add_street_pick / pick_street, asking at an unclear end), "name": the clicked line's street};
    rhino_logic.pick_effect sets them (through set_street_lines)."""
    if what == "street":
        lot = _find(doc, facts.get("lot_id") or "")
        if lot is None:
            return None
        outline = _outline(doc, lot)
        try:
            if facts.get("corner_lot") is True:      # a corner lot: every street clicked, Enter when done
                picks, runs = [], []
                names = logic.outline_names(outline, facts.get("street_line"), facts.get("street_ids"))
                while True:
                    rc, point = _get_point(logic.street_pick_prompt(True, len(picks)))
                    if rc == Rhino.Commands.Result.Cancel:
                        raise Cancelled()            # Esc: nothing changes, the lines clicked so far too
                    if rc != Rhino.Commands.Result.Success:   # Enter: done
                        break
                    a, b = _clicked_piece(doc, lot, point)
                    line = [_feet_point(doc, a)[:2], _feet_point(doc, b)[:2]]
                    # the whole street that piece is on, never round a corner; said, and an unclear end asked; only
                    # a click that kept a street counts as picked (street-run round 12)
                    grown, said = logic.add_street_pick(runs, outline, line, names, _ask_street_more)
                    say(logic.so_far(said) if grown != runs else said)
                    if grown != runs:
                        picks.append(line)
                    runs = grown
                lines, ids = logic.street_lines_of(outline, runs, names, picks)
                return {"lines": lines, "ids": ids, "name": None} if lines else None   # (every click refused)
            rc, point = _get_point(logic.street_pick_prompt(False, 0))
            if rc == Rhino.Commands.Result.Cancel:
                raise Cancelled()
            if rc != Rhino.Commands.Result.Success:
                return None
            a, b = _clicked_piece(doc, lot, point)
            picked = [_feet_point(doc, a)[:2], _feet_point(doc, b)[:2]]
            refused = logic.refused_click(_outline(doc, lot), picked)   # (before asking its name: round 9)
            if refused:
                say(refused)
                return None
            name = logic.street_name_after_pick(saved_ui.get("street_name"), facts.get("street_line"),
                                                picked, ids=facts.get("street_ids"))   # the line's own street?
            if name is None:                                   # else asked, never guessed
                ask = Rhino.Input.Custom.GetString()   # literal: a street's name has spaces ("Cayuga St")
                ask.SetCommandPrompt("Which street is this lot line on? (Enter leaves it unnamed)")
                ask.AcceptNothing(True)
                got = ask.GetLiteralString()
                if got == Rhino.Input.GetResult.Cancel:
                    raise Cancelled()
                name = (ask.StringResult() or "").strip() or None if got == Rhino.Input.GetResult.String else None
            told = []
            lines, ids = logic.pick_street(facts.get("street_line"), facts.get("street_ids"), picked, name,
                                           outline=_outline(doc, lot), ask=_ask_street_more, said=told)
            say(told[-1]["words"] if told else logic.street_words(name or "This street", lines, ids))
            if told and told[-1]["refused"]:          # (a point clicked: everything stays as it was)
                return None
            return {"lines": lines, "ids": ids, "name": name}
        except Cancelled:                            # Esc (the bend question, a pick): nothing changes
            say(logic.ESC_STREET)
            return None
    if what == "lot":                            # Use my survey: the surveyed outline
        return _pick(doc, "Click your surveyed lot outline (a closed curve on the Site layer); Enter keeps it",
                     _lot_candidates(doc), "Lot", Rhino.DocObjects.ObjectType.Curve)
    if what == "draw_lot":                       # over the City's outline (a guide, never kept)
        drawn = _draw_lot(doc, session.table._changing)       # (in the box's one undo step)
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
                              GRADE_LAYER if what == "spot" else FINISHED_LAYER, session.table._changing)
        session.add(placed)
        return placed
    return None


def confirm(doc, facts, options, mode="check"):
    """The start box, prefilled (spec A). Draw keeps the facts once the district is confirmed, with where each came
    from (saved beside them); a pick closes the box, picks in the model, and shows the box again with the result;
    closing it (or Esc) saves nothing (None)."""
    gate = STATE.setdefault("box_gate", logic.BoxGate())
    if not _box_open():
        _settle_live()                  # a live re-check of the model before the box: finished (or dropped) first
    if not logic.allowed("open_box", _box_open()) or not gate.enter():   # one start box at a time
        say(logic.BOX_BUSY)
        return None
    result = None
    changed_before = STATE.get("dirty")
    failed = True                       # until _confirm returns: an error inside the box (its rollback may have
    try:                                # stopped partway) leaves the model counted as changed
        # "draw the house again" belongs to this box only: set by its own Draw of a new address (_draw_prepare), read
        # by its caller (edit_facts) right after; never one an earlier box left (GordiumCheck's box set it and nothing
        # read it, so a later Edit site… drew a starting house over the architect's model: P1, found 2026-10-26)
        STATE.pop("redraw_house", None)
        ui.set_box_open(STATE.get("panel_parts"), True)
        result = _confirm(doc, facts, options, mode)
        failed = False
    finally:
        gate.leave()
        ui.set_box_open(STATE.get("panel_parts"), False)
        # Cancel put the model back: it is as changed (or not) as it was when the box opened, so current results
        # never grey out for the box's own rolled-back edits (the Check button: nothing re-checks them)
        # (the edit's own time kept: never moved earlier, which could let a check from before it count as covering
        # it; with Check after every edit on, the next idle past IDLE_SECONDS checks: review round 1, P1). An error
        # is no Cancel: the model may not be as it was, so the results grey out, never shown as current (the
        # headless check-15, demo review of #26 with #27)
        STATE["dirty"] = logic.changed_after_box(changed_before, STATE.get("dirty"), result is not None,
                                                 failed=failed)
    if result is not None:              # Draw (GordiumStart or Edit site…): the neighbourhood follows the lot
        logic.guard(sync_context, "draw the neighbourhood")(doc, result)
    return result


def _confirm(doc, facts, options, mode):
    o = overlay()
    _clear(o)                           # facts are being set: no earlier result (of any model) stays shown
    o.message = None
    _highlight(doc, facts)
    _recover(doc)                       # anything an unfinished earlier box set aside, back first
    saved_ui = logic.box_opened(_ui_state(doc), facts)   # the lot's own address, this session only
    session = logic.BoxSession(RhinoTable(doc, logic.UNDO_WORDS["edit_site"]))  # this box's model edits: one step
    try:
        return logic.run_box(session, lambda: _box_loop(doc, facts, options, mode, saved_ui, session))
    finally:
        _lookup_stop()
        _suggest_stop()                   # (a type-ahead still running: never left behind)
        o.confirm = None
        o.labels = []
        STATE.pop("lookup_guide", None)
        doc.Views.Redraw()


# what of the architect's ticks stays after the City-guide reset (the box open again on the new lot): never the
# address's source, which is the reset's (the address as found keeps the lookup's: typed-address rule, round 4)
GUIDE_KEEPS = ("district_confirmed", "zone_source", "use_source")


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
        facts, saved_ui, go, state = _draw_prepare(doc, facts, state, saved_ui, session, mode, options)
        return _drawn(doc, facts, state, saved_ui, session, mode) if go and state is not None else None
    ticked = {}                       # this box session's ticks and changed sources, kept across picks
    while True:
        state = dict(_box_state(doc, facts, options, saved_ui, mode), **ticked)
        state["_on_shown"] = STATE.get("on_box_shown")     # the dialog capture in the in-Rhino test
        state["_draw_label"] = logic.draw_button(mode, saved_ui)   # Draw when it draws, else Check
        STATE["zones"] = options.get("zones") or []
        what = ui.start_box(state, options, mode)
        if what is None:
            return None                      # rolled back by run_box: the model as it was
        ticked = logic.box_ticks(state)      # (saved only at Draw)
        if what == "draw":
            facts, saved_ui, go, drawn_state = _draw_prepare(doc, facts, state, saved_ui, session, mode, options)
            if go:
                return _drawn(doc, facts, drawn_state, saved_ui, session, mode)
            # Draw stopped (a question cancelled, an address not found, the City's guide): the box again, with the
            # architect's ticks and choices kept; a lookup started or a preview dropped asks for the tick again (their
            # own answers' sources are kept in saved_ui: rhino_logic.saved_sources)
            if drawn_state is None or (saved_ui.get("_lookup") or {}).get("looking"):
                ticked = {}
            elif drawn_state is not state:            # after the reset (the guide): its lot rows are the model's
                ticked = {k: v for k, v in ticked.items() if k in GUIDE_KEEPS}
            continue
        facts, saved_ui = _apply_box(doc, facts, state, saved_ui)
        was_by_hand, had_pending = saved_ui.get("_by_hand"), saved_ui.get("_pending")
        facts_before, ui_before = facts, saved_ui
        if what != "pick:refresh":           # refresh: another use or district, the box again with its questions
            facts, saved_ui = _box_pick(doc, what.split(":", 1)[1], facts, saved_ui, session)
        # a lookup's answer replaces them (the district must be confirmed again) unless it filled and moved nothing;
        # Look up and Cancel lookup keep them as the box shows them, never the ticks from before Look up brought
        # back (rhino_logic.ticks_after_pick); by hand undoes them (a tick given its district never moves to another)
        ticked = logic.ticks_after_pick(what, ticked, (saved_ui.get("_lookup") or {}).get("status"),
                                        logic.box_moved(facts_before, ui_before, facts, saved_ui))
        if (what == "pick:by_hand" and saved_ui.get("_by_hand")     # by hand taken, or a lookup's preview set
                and (not was_by_hand or (had_pending and not saved_ui.get("_pending")))):   # aside by it (round
            ticked = {}            # 15): ticks again (No or refused changes nothing: rounds 12, 16)
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
        if STATE.get("lookup_slow"):                     # ...paused at each step, to see it and Cancel it
            args += ["--slow", str(STATE["lookup_slow"])]
    sink = open(out, "w", encoding="utf-8")             # to a file: a long answer never fills a pipe
    err = open(os.path.join(tempfile.gettempdir(), "gordium_worker.log"), "a", encoding="utf-8")
    STATE["lookup"] = {"proc": ui.spawn(args, cwd=REPO, env=env, stdout=sink, stderr=err),   # no console window
                       "out": out, "sink": sink, "err": err, "started": time.time(), "query": address,
                       "before": saved_ui.get("_lookup")}     # the box's lookup line before: Cancel lookup puts it back
    return dict(saved_ui, _lookup={"looking": address})


def _lookup_env():
    packages = os.path.join(REPO, "packages")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(STATE.get("extra_paths", []) + [
        os.path.join(packages, n) for n in sorted(os.listdir(packages)) if os.path.isdir(os.path.join(packages, n))])
    return env


def _suggest_start(text):
    """Type-ahead for the address typed: the City's addresses starting like it, asked in lookup_box's own short
    process (never Rhino's Python). An earlier one still running is stopped first: its answer would be stale."""
    _suggest_stop()
    out = os.path.join(tempfile.gettempdir(), "gordium_suggest_%d.json" % int(time.time() * 1000))
    args = [_python(), "-m", "design_checker.lookup_box", "--suggest", text]
    if STATE.get("lookup_fixture"):                      # the in-Rhino test: stand-in addresses, no live call
        args += ["--fixture"]
        if STATE.get("suggest_offline"):              # ...or the layer unreachable
            args += ["--offline"]
        if STATE.get("suggest_slow"):
            args += ["--slow", str(STATE["suggest_slow"])]
    sink = open(out, "w", encoding="utf-8")
    err = open(os.path.join(tempfile.gettempdir(), "gordium_worker.log"), "a", encoding="utf-8")
    STATE["suggest"] = {"proc": ui.spawn(args, cwd=REPO, env=_lookup_env(), stdout=sink, stderr=err),
                        "out": out, "sink": sink, "err": err, "started": time.time(), "query": text}


def _suggest_poll():
    """None while the type-ahead runs; then its answer ({"status", "query", "suggestions"}). Stopped, and said
    unavailable, after logic.SUGGEST_LIMIT_S."""
    run = STATE.get("suggest")
    if run is None:
        return None
    p = run["proc"]
    if p.poll() is None:
        if time.time() - run["started"] < logic.SUGGEST_LIMIT_S:
            return None
        answer = {"status": "timeout", "query": run["query"]}
    else:
        run["sink"].close()
        try:
            with open(run["out"], encoding="utf-8") as f:
                answer = json.loads(f.read().strip().splitlines()[-1])
        except Exception:
            answer = {"status": "error", "query": run["query"]}
    _suggest_stop()
    return answer


def _suggest_stop():
    run = STATE.pop("suggest", None)
    if run is not None:
        _lookup_kill(run)
        _lookup_files_done(run)


SUGGESTER = {"start": _suggest_start, "poll": _suggest_poll, "stop": _suggest_stop}


def _lookup_progress():
    """The box's live line while the lookup runs: its latest step (it prints one as each stage starts), a moving
    mark and the seconds so far."""
    run = STATE.get("lookup") or {}
    try:
        with open(run.get("out") or "", encoding="utf-8") as f:
            step = logic.lookup_step(f.read())
    except (OSError, ValueError):
        step = None
    return logic.lookup_status(run.get("query") or "the address", step, time.time() - run.get("started", time.time()))


def _lookup_cancel(saved_ui):
    """Cancel lookup: the lookup's process stopped, and the box as it was before Look up (nothing it would have
    filled in is filled in; an earlier preview, dashed, stays as it was)."""
    before = (STATE.get("lookup") or {}).get("before")
    _lookup_stop()
    return logic.lookup_cancelled(saved_ui, before)


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
            run["answer"] = logic.lookup_answer(f.read(), run["query"])   # its last answer line, never a step
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
    """The lookup's answer into the box only (rhino_logic.preview_lookup, tested in CI): nothing in the model
    changes; its lot is shown dashed on screen while the box is open (gone on Cancel), and Draw draws it
    (_draw_prepare). The views framed on it."""
    answer = _lookup_poll() or {"status": "error"}
    asked = (STATE.get("lookup") or {}).get("query") or facts.get("address")
    _lookup_stop()
    offer = logic.guard(_saved_lookup, "keep or find a saved lookup")(answer, asked)
    facts, saved_ui = _show_answer(doc, answer, facts, saved_ui)
    saved_ui.pop("_saved_answer", None)         # an earlier offer never outlives the next lookup
    saved_ui.pop("_saved_for", None)
    if offer:                                   # offline: the box offers the lookup saved on this computer
        saved_ui = dict(saved_ui, _saved_answer=offer, _saved_for=asked)
        saved_ui["_lookup"] = dict(saved_ui.get("_lookup") or {}, saved_offer=offer.get("checked"), saved_for=asked)
    return facts, saved_ui


def _saved_lookups_path():
    """The lookups saved on this computer (the offline safety net), beside Gordium's other per-user files."""
    return STATE.get("saved_lookups_path") or os.path.join(os.path.expanduser("~"), ".gordium", "saved_lookups.json")


def _saved_lookup(answer, asked):
    """A found answer saved (rhino_logic.save_lookup: only what its sources allow); for a failed one, the saved
    lookup of the same address to offer, or None."""
    path = _saved_lookups_path()
    readable = True
    try:
        with open(path, encoding="utf-8") as f:
            store = json.load(f)
    except FileNotFoundError:
        store = {}
    except Exception:                           # unreadable: offered nothing, and never overwritten (its other
        store, readable = {}, False             # saved lookups are kept)
    if (answer or {}).get("status") == "found":
        new = logic.save_lookup(store, answer, asked)
        # recorded answers (the in-Rhino tests) are never saved as the architect's lookups
        if new != store and readable and not STATE.get("lookup_fixture"):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = "%s.%d.%d.tmp" % (path, os.getpid(), int(time.time() * 1000))   # two Rhinos never share one
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(new, f)
            os.replace(tmp, path)
        return None
    return logic.saved_offer(answer, store, asked)


def _show_answer(doc, answer, facts, saved_ui):
    """An answer into the box only: its lot shown dashed, the views framed on it."""
    facts, saved_ui, preview = logic.preview_lookup(answer, facts, saved_ui, STATE.get("zones") or [])
    STATE.pop("lookup_guide", None)
    if preview:
        pts = [_model_point(doc, p) for p in preview]
        STATE["lookup_guide"] = pts + [pts[0]]
        logic.guard(_frame_points, "frame the looked-up lot")(doc, pts)
    return facts, saved_ui


def _frame_points(doc, pts):
    box = rg.BoundingBox(pts)
    box.Inflate(_model_length(doc, 10))
    for view in doc.Views:
        view.ActiveViewport.ZoomBoundingBox(box)
    doc.Views.Redraw()


def _ask_reset(question, fresh, keep):
    """The one question when the architect's own work would go (rhino_logic.reset_question): the answer's key, or
    None (Cancel: back to the box). `keep` None: their lot alone would go, so only Start fresh or Cancel."""
    import Eto.Forms as ef
    answer_with = STATE.get("on_reset_question")     # the in-Rhino test answers it
    if answer_with is not None:
        return answer_with(question, fresh, keep)
    dialog = ef.Dialog[str]()
    dialog.Title = "Gordium · a new address"
    chosen = {"v": None}

    def pick(v):
        chosen["v"] = v
        dialog.Close(v)
    layout = ef.DynamicLayout()
    layout.Padding = ui.ed.Padding(14) if hasattr(ui, "ed") else 14
    layout.AddRow(ui.label(question, size=12))
    buttons = [ui.button(fresh[0], lambda: pick(fresh[1]))]
    if keep is not None:
        buttons.append(ui.button(keep[0], lambda: pick(keep[1])))
    buttons.append(ui.button("Cancel", lambda: pick(None)))
    layout.AddRow(ui.row(*buttons))
    dialog.Content = layout
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    return chosen["v"]


def _draw_prepare(doc, facts, state, saved_ui, session, mode, options):
    """Draw, before anything is saved (rhino_logic.box_facts / settle_pending / draw_decision / reset_question /
    apply_reset / after_reset_state, tested in CI): (facts, saved_ui, go, state to save). An address typed that
    wasn't looked up draws nothing (address_reason: Draw is off in the box, and any other way in, the scripted one
    too, says "Press Look up to find … first."; Ben, 2026-10-25). Then the box's answers;
    a preview for an address since retyped is dropped and the box shown again as it was put back (state None: its
    district ticked again, never saved from the state the box showed before); a new address over what Gordium drew
    is drawn clean, the starting house drawn again after (one undo step), and the box's state rebuilt from the new
    lot (never the old lot's size, survey or corner saved over it); the architect's own work is asked about once
    (Cancel: back to the box). When the answer had only the City's outline, the box stays open after the reset,
    the guide shown, for Draw my lot… (go False; Cancel still puts everything back). The same address: as it is."""
    table = RhinoTable(doc)
    unlooked = logic.draw_blocked(state, saved_ui)        # (an empty file: a found lookup, or the site by hand)
    if unlooked:                                          # Draw is off in the box; any other way in says why
        say(unlooked)
        return facts, saved_ui, False, state
    facts, saved_ui = _apply_box(doc, facts, state, saved_ui)
    previewed = saved_ui.get("_pending") is not None
    facts, saved_ui = logic.settle_pending(facts, saved_ui, state.get("address"))
    if previewed and saved_ui.get("_pending") is None:    # the preview dropped (address retyped): the box again,
        STATE.pop("lookup_guide", None)                   # as it was put back, ticked again (state None)
        return facts, saved_ui, False, None
    plan, mine = logic.draw_decision(table, facts, saved_ui)
    if plan == "none":
        saved_ui.pop("_pending", None)
        return facts, saved_ui, True, state
    choice = logic.START_FRESH
    if plan == "ask":
        question, fresh, keep = logic.reset_question(saved_ui["_pending"].get("address"), mine,
                                                     saved_ui["_pending"].get("answer"))
        choice = _ask_reset(question, fresh, keep)
        if choice is None:
            return facts, saved_ui, False, state
    # the new address's starting house, worked out BEFORE the undo step opens: Rhino runs while Gordium waits, so an
    # undo step held open across the wait would take the architect's own edits into Gordium's (independent review
    # of #32, P2); logic.WorkCancelled here: nothing has changed yet
    STATE["start_plan"] = _plan_reset_house(doc, facts, state, saved_ui, choice, mode, options)
    if not STATE.get("undo"):           # (the box's own step, if its edits began one: the reset goes in it)
        _begin_undo(doc, "Gordium: start fresh for " + (saved_ui["_pending"].get("address") or "a new address"))
    facts, saved_ui, redraw, guide = logic.apply_reset(table, session, facts, saved_ui, choice,
                                                       STATE.get("zones") or [])
    STATE["redraw_house"] = redraw and mode == "check"     # (GordiumStart draws its house itself)
    STATE.pop("lookup_guide", None)
    fresh_state = _reset_state(doc, facts, options, saved_ui, mode, state)
    if guide and not facts.get("lot_id"):                 # the City's outline only: their lot drawn over it first
        STATE.pop("start_plan", None)                     # (no house planned on a lot not drawn yet)
        pts = [_model_point(doc, p) for p in guide]
        STATE["lookup_guide"] = pts + [pts[0]]
        return facts, saved_ui, False, fresh_state
    return facts, saved_ui, True, fresh_state


def _begin_undo(doc, words):
    """One undo step for everything a Draw does (the reset, the new lot, the starting house drawn again)."""
    _end_undo(doc)
    STATE["undo"] = (doc.RuntimeSerialNumber, doc.BeginUndoRecord(words))
    STATE["undo_words"] = words


def _end_undo(doc):
    """Ends the Draw's undo record, only one this script began (rhino_logic.undo_record_to_end: serial 0 is Rhino
    saying a command is already recording, whose record is Rhino's own to end)."""
    held = STATE.pop("undo", None)
    if logic.undo_record_to_end(held, doc.RuntimeSerialNumber if doc is not None else None):
        doc.EndUndoRecord(held[1])


def _undo_redo(sender, e):
    """Rhino's Undo or Redo, finished: what the last check drew (the lot outline, yards, marks) and any dashed
    lookup outline are of a model that is no longer there, so they are cleared (rhino_logic.after_undo_redo) and
    the model is checked again at the next idle (live mode). Nothing in the document is changed here: a change made
    while Rhino undoes or redoes breaks its Undo/Redo chain (RhinoCommon's undo event rule)."""
    if not logic.after_undo_redo(e.IsEndUndo, e.IsEndRedo):
        return
    o = STATE.get("overlay")
    if o is not None:
        _clear(o)
    STATE.pop("lookup_guide", None)
    _settings_from_file(Rhino.RhinoDoc.ActiveDoc)
    STATE["dirty"] = logic.dirty_after_undo(STATE.get("dirty"), time.time())   # re-checked at the next idle (live)


def _settings_from_file(doc):
    """The panel's settings kept in memory, read again from the file after Undo or Redo (a setting undone is put
    back in the file only; memory only, never the document: round 5, R5-1): Show on-screen labels, Hide starting
    house (from its layer), Show neighbourhood (its live footprints are drawn by it), Check after every edit."""
    if doc is None:
        return
    STATE.setdefault("labels_by_doc", {})[doc.RuntimeSerialNumber] = logic.labels_on(_ui_state(doc))
    STATE.pop("auto_by_doc", None)      # Check after every edit: read again from the file, its tick too (#27, C1)
    _sync_ticks(doc)                    # every tick as the document has it now (Hide starting house: its layer)


def _sync_ticks(doc):
    """Every tick the panel has, as the document has it (the session's, for the envelope): the panel never shows a
    tick as last clicked (the Rhino job at 540f718: Hide starting house stayed ticked after Cmd+Z). Run at every
    check, failed ones too, and whenever the panel is made. (A layer switched in Rhino's Layers panel shows at
    the next check, or after an Undo.)"""
    p = STATE.get("panel_parts")             # (each setter does nothing without a panel)
    if doc is None:
        return
    ui.set_labels_tick(p, logic.labels_on(_ui_state(doc)))
    ui.set_massing_tick(p, _massing_hidden(doc))
    ui.set_envelope_tick(p, STATE.get("envelope_on", True))
    ui.set_context_tick(p, _context_on(doc))         # (#23: Show neighbourhood, kept per document)
    ui.set_auto_tick(p, _auto(doc))                  # (#27: Check after every edit, kept per document)


def _massing_hidden(doc):
    """Whether this document's starting house layer (Gordium::Massing) is hidden: the panel's tick follows it."""
    index = doc.Layers.FindByFullPath(logic.MASSING, -1) if doc is not None else -1
    return index >= 0 and not doc.Layers[index].IsVisible


def _drawn(doc, facts, state, saved_ui, session=None, mode=None):
    """Draw: the facts for the checker, and every fact's source and confirmation saved in the .3dm; what the box
    replaced goes for good. One undo step from here to the facts saved after the box closes (its caller ends it:
    _end_undo), unless one is already held. A starting house to draw after (GordiumStart, or a new address drawn
    clean) is worked out first, before anything is saved or committed (_plan_house): Cancel while the checker finds
    it rolls the whole box back (run_box), so nothing is drawn and the model is as it was."""
    if not STATE.get("undo"):
        _begin_undo(doc, logic.UNDO_WORDS["edit_site"])

    def save():
        out, ui_state = _apply_box(doc, facts, state, saved_ui)
        planned = STATE.pop("start_plan", None)         # a new address's: worked out before its undo step opened
        if session is not None and logic.plans_house(mode, STATE.get("redraw_house"), STATE.get("house_after_box")):
            # logic.WorkCancelled: nothing saved. (A reset's plan was worked out before its undo step opened,
            # _plan_reset_house; the City-outline Draw's step is still open here: ask ends it for the wait and begins
            # it again after, so the commit and the house are in a step of Gordium's)
            STATE["start_plan"] = planned or _plan_house(doc, out, ui_state)
        _save_ui_state(doc, ui_state)
        sources = logic.sources_kept(fact_sources(doc), out)   # what the box doesn't set is kept (an answer
        #                                                       kept unshown too; one unset goes with its fact)
        sources.update(logic.fact_sources(state, logic.city_day(), confirmed=True))
        # every answer typed in this box, shown at Draw or not: entered by you, with its value now
        sources = logic.typed_sources(sources, ui_state.get("_answers"), out, logic.city_day())
        doc.Strings.SetString(SECTION, SOURCES_ENTRY, json.dumps(sources))
        return out

    if session is None:
        return save()
    return logic.draw_then_commit(session, save)     # the commit last: a failure before it is rolled back


def hide_massing(hidden):
    """Hide starting house: the Gordium::Massing layer off (still checked: only its drawing is turned off)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
    index = doc.Layers.FindByFullPath(logic.MASSING, -1)
    if index < 0:
        ui.set_massing_tick(STATE.get("panel_parts"), False)    # nothing hidden: never left ticked
        say("There is no starting house in this file to hide (run GordiumStart on a new file to draw one).")
        return
    with logic.undo_step(doc, logic.UNDO_WORDS["massing"]):
        touched = logic.outermost_first([(i, layer.FullPath) for i, layer in enumerate(doc.Layers)
                                         if not layer.IsDeleted and logic.on_layer(layer.FullPath, logic.MASSING)])
        locks = [(i, _own_lock(doc, doc.Layers[i])) for i in touched]   # (a parent's IsVisible passes its lock down)
        for layer in touched:
            doc.Layers[layer].IsVisible = not hidden     # the parent and each floor's sublayer, each set (review of
            #                                              feature 5, F2: never left to what the parent passes down)
        for i, own in locks:                             # each layer's own lock as it was (the architect edits them)
            _set_own_lock(doc, doc.Layers[i], own)
    doc.Views.Redraw()


Cancelled = logic.Cancelled          # Esc at a prompt: the whole edit is cancelled and nothing is saved


def _go_on(rc):
    if rc == Rhino.Commands.Result.Cancel or rc == Rhino.Input.GetResult.Cancel:
        raise Cancelled()


def _yes_no(prompt, current):
    rc = Rhino.Input.RhinoGet.GetBool(prompt, True, "No", "Yes", bool(current))
    _go_on(rc[0])
    return bool(rc[1]) if rc[0] == Rhino.Commands.Result.Success else current


def _ask_in_city():
    """The City's date (logic.city_day) when the architect says Yes to logic.IN_CITY_QUESTION, else None (No, or the dialog closed)."""
    got = ef.MessageBox.Show(Rhino.UI.RhinoEtoApp.MainWindow, logic.IN_CITY_QUESTION, "Gordium",
                             ef.MessageBoxButtons.YesNo, ef.MessageBoxType.Question, ef.MessageBoxDefaultButton.No)
    return logic.city_day() if got == ef.DialogResult.Yes else None


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
        if picked and picked != facts.get("lot_id"):           # another lot: its ground was never looked up
            _save_ui_state(doc, logic.lot_ground_dropped(_ui_state(doc)))
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
        picked, runs, outline = [], [], _outline(doc, lot)
        while True:                      # every lot line on a street (both streets on a corner lot)
            keeps = not runs and logic.street_enter_keeps(facts)        # (what was kept, not what was clicked:
            prompt = "Click a lot line on the street" + (" (Enter when done)" if runs else   # a refused click
                                                         " (Enter keeps the blue one)" if keeps else "")   # keeps none)
            rc, point = Rhino.Input.RhinoGet.GetPoint(prompt, True)      # Enter: done, keep, or asked again
            _go_on(rc)
            if rc != Rhino.Commands.Result.Success:
                if runs or keeps:
                    break
                Rhino.RhinoApp.WriteLine("Gordium: this lot has no street line yet; click one (Esc cancels)")
                continue
            a, b = _clicked_piece(doc, lot, point)
            line = [_feet_point(doc, a)[:2], _feet_point(doc, b)[:2]]
            # the whole street that piece is on, never round a corner (unnamed: from the drawing alone); every
            # click is answered, a refused one too, every time (round 10)
            grown, said = logic.add_street_pick(runs, outline, line, None, _ask_street_more)
            say(logic.so_far(said) if grown != runs and facts.get("corner_lot") else said)   # (corner: so far)
            if grown != runs:
                picked.append(line)
            runs = grown
            if not facts.get("corner_lot") and runs:      # (a refused click: asked again)
                break
        lines, ids = logic.street_lines_of(outline, runs, None, picked) if picked else ([], None)
        if lines:                         # never the old names; every line an id ("Street 1"…, as said): #18
            logic.set_street_lines(facts, lines, ids)
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
    if STATE.get("asking") is not None:   # Gordium is working (Rhino runs during its wait): a command
        say(logic.WORKING)                # typed meanwhile waits its turn, never a second piece of work
        return None
    if Rhino.RhinoDoc.ActiveDoc is None:  # every document closed: say what to do, never crash (nor ask the checker)
        say(logic.NO_DOCUMENT)
        return None
    options = ask({"cmd": "options", "jurisdiction": JURISDICTION})   # (asked first: the model is read after it)
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
    try:
        saved = current_facts(doc)
    except logic.NotInFront:            # another file came to the front while the facts were read
        say(logic.NOT_IN_FRONT)
        return None
    except ValueError:                  # unreadable: start again from the suggestions
        saved = {}
    cancelled = False
    STATE["house_after_box"] = True     # this box's Draw of a new address draws its house (logic.plans_house)
    STATE.pop("redraw_house", None)     # only this box's own Draw sets it (GordiumCheck's box left it set: round 2)
    try:                                # one undo step from the box's first model edit (or its Draw) to the facts
        try:
            facts = confirm(doc, logic.with_suggestions(saved, logic.no_guessed_district(
                saved, suggested_facts(doc, options["zones"]))), options, "check")
        finally:                        # the editing outline and names never stay on screen
            o = overlay()
            o.confirm, o.labels = None, []
            doc.Views.Redraw()
        if facts is not None:
            save_facts(doc, facts)
            if STATE.pop("redraw_house", False):        # a new address drawn clean: its starting house too
                _draw_starting_house(doc, facts)
    except logic.WorkCancelled as stopped:   # Cancel (or the model changed) while the house was worked out: rolled back
        cancelled = getattr(stopped, "said", logic.DRAW_CANCELLED)
    finally:
        STATE.pop("redraw_house", None)
        STATE.pop("start_plan", None)
        STATE.pop("house_after_box", None)
        _end_undo(doc)
    # after a Cancel, `cancelled` says why nothing was drawn (logic.DRAW_CANCELLED, or logic.ModelChanged's words)
    run_check(doc, report=False)        # the model as it is (as it was, after a Cancel)
    if cancelled:
        say(cancelled)


def report_path(doc):
    folder = os.path.dirname(doc.Path) if doc.Path else os.path.expanduser("~/Documents")
    name = os.path.splitext(os.path.basename(doc.Path))[0] if doc.Path else "untitled"
    return os.path.join(folder, name + "_gordium_report.xlsx")


def _clear(o):
    """Nothing from an earlier check is left on screen, its "no longer complies" notice included: every check
    clears before it draws (a check that finds nothing newly failing leaves no notice of an earlier one), and so
    does another document, a failed check and new facts."""
    o.toast = None
    o.red, o.red_ids, o.dims, o.envelope, o.box = [], set(), [], None, rg.BoundingBox.Empty
    o.encroach, o.yard_dims, o.edge_labels, o.lot_outline, o.yards_zone, o.grade_points = [], [], [], None, None, []
    o.yard_required, o.height_dim, o.yard_options, o.yard_tags, o.footprint, o.placed = [], None, {}, {}, [], {}
    o.yard_numbers, o.house_box, o.height_number = {}, [], None
    o.plan_lines, o.plan_solids = [], []
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
    # at the lot's own level, a hair above it: off plan they are depth-tested, and at z 0 a lot drawn higher (or the
    # ground under it) hid them (review round 1 of depth-lines, F1)
    z = logic.dim_level(_lot_level(doc, facts))
    o.yard_dims = [(rg.Line(_model_point(doc, y["points"][0], z), _model_point(doc, y["points"][1], z)),
                    y["label"], y["status"]) for y in plan.get("yards") or [] if y.get("points")]
    # each yard's required line, faint, square across its dimension; the height's vertical dimension (elevations)
    o.yard_required = [(rg.Line(_model_point(doc, r[0], z), _model_point(doc, r[1], z)), y["status"])
                       for y in plan.get("yards") or [] if y.get("points") for r in y.get("required_lines") or []]
    # each yard's dimension where check.plan puts it best (its first position: the one placer moves the number, never
    # the line; review of 86c01ea, F5), with its required lines; the "min" tags; the buildings' outline
    o.yard_options = {k: [(rg.Line(_model_point(doc, c["points"][0], z), _model_point(doc, c["points"][1], z)),
                           [rg.Line(_model_point(doc, r[0], z), _model_point(doc, r[1], z))
                            for r in c.get("required_lines") or []])
                          for c in (y.get("candidates") or [])[:1]]
                      for k, y in enumerate(y for y in plan.get("yards") or [] if y.get("points"))}
    o.yard_tags = {k: y.get("required_tags") or [] for k, y in enumerate(y for y in plan.get("yards") or []
                                                                           if y.get("points"))}
    o.footprint = [[_model_point(doc, p, 0.1) for p in ring] for ring in plan.get("footprint") or []]
    o.yard_numbers = {k: y.get("number") for k, y in enumerate(y for y in plan.get("yards") or [] if y.get("points"))}
    o.height_number = (plan.get("height") or {}).get("number")
    box = rg.BoundingBox.Empty
    for b in _buildings(doc):
        box.Union(b.Geometry.GetBoundingBox(True))
    o.house_box = list(box.GetCorners()) if box.IsValid else []
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
    # what no plan label may cover (logic.place_dim_label's HARD rules): each building's footprint (its plan edges'
    # ends: their hull on screen each frame) and each coloured part's own outline (model space)
    o.plan_solids = [("building", [q for line in _plan_edges(b.Geometry) for q in (line.From, line.To)])
                     for b in _buildings(doc)] + \
        [("coloured", [_model_point(doc, (x, y)) for x, y in e["outline"]]) for e in plan.get("encroach") or []
         if e.get("outline") and logic.highlight(e.get("status") or "does_not_comply")]
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
    would otherwise be checked mid-box; live mode checks once the box closes. The checker works in its own
    process and Rhino keeps drawing while it does (ask); the panel says "Checking…" with what it is doing, and a
    slow check shows a small window with Cancel: cancelled, nothing in the model changes and nothing is shown as
    checked (_check_cancelled). A live re-check still running is finished first (_settle_live)."""
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
    _settle_live()
    if STATE.get("running") or not logic.allowed("check", _box_open()):
        return None
    o = overlay()
    try:
        STATE["running"] = True
        begun = _check_begin(doc, report)
        p = STATE.get("panel_parts")
        tick = None
        if not STATE.get("headless") and p is not None and p["form"].Visible:
            ui.show(p, None, checking=True)          # "Checking…" while it runs, its live line under it (from
            tick = lambda job: ui.follow(p, job)     # the first tick of a slow one: its window's own line too)
        result = ask(begun["request"], cancel=True, on_tick=tick)
        if _changed_during(begun["doc"], begun["at"]):   # edited, or another document in front, while it ran
            _check_outdated(doc, o, report, begun, result)
            return None
        return _check_apply(doc, o, begun, result)
    except logic.NotInFront as e:            # another file came to the front while its facts were read: the check
        _check_outdated(doc, o, report,      # never began, so no report was written (said so, never "of the model")
                        {"had_report": bool(report) and os.path.exists(report_path(doc))}, {"report_error": str(e)})
        return None
    except logic.WorkCancelled:
        _check_cancelled(doc, o)
        if report:                           # any caller that asked for a report (Zoning report…, GordiumCheck):
            _drop_report_part(report_path(doc))   # never a half-written copy left beside it (review round 2)
        return None
    except Exception as e:
        _check_failed(doc, o, e)
        return None
    finally:
        STATE["running"] = False
        doc.Views.Redraw()


def _check_begin(doc, report, facts=None):
    """Everything a check needs from the model, read now on Rhino's thread (the facts, the model copied into a small
    .3dm, what is on the lot): the checker's request, and when the model was read. `facts`: already read (a
    background re-check, whose job has the checker read them: _check_live), else read and checked here."""
    if not STATE.get("headless"):            # the message line tells of this check's action only, whatever happens
        ui.say(STATE.get("panel_parts"), "")
    at = time.time()
    STATE.setdefault("units_seen", {})[doc.RuntimeSerialNumber] = _units(doc)   # the units this check reads
    facts = current_facts(doc) if facts is None else facts
    if logic.missing(facts):
        raise ValueError("lot facts missing: " + ", ".join(logic.missing(facts)) + " (run GordiumCheck)")
    path = os.path.join(tempfile.gettempdir(), "gordium_live_" + str(doc.RuntimeSerialNumber) + ".3dm")
    problems = export(doc, path)
    sent = check_facts(doc, facts)
    extras = _extras(doc, facts)
    extras["before"] = STATE.setdefault("statuses_by_doc", {}).get(doc.RuntimeSerialNumber)
    had_report = bool(report) and os.path.exists(report_path(doc))    # before this check tries to write one
    return {"at": at, "facts": facts, "sent": sent, "extras": extras, "report": bool(report),
            "had_report": had_report, "doc": doc.RuntimeSerialNumber,
            "request": {"cmd": "check", "model": path, "facts": sent, "building_problems": problems,
                        "report": report_path(doc) if report else None, "extras": extras}}


def _check_apply(doc, o, begun, result):
    """A check's answer drawn and listed (Rhino's thread)."""
    facts, sent, extras, report = begun["facts"], begun["sent"], begun["extras"], begun["report"]
    _clear(o)
    STATE.pop("recheck_owed", None)          # a check's answer of the model now: shown as current again
    o.doc = doc.RuntimeSerialNumber
    view = result["view"]
    head = view["header"]
    second = [head["draft"].split(" · ")[0]] + [t for t in (head["lot"], head["grade"])
                                                 if "approximate" in t or "not set" in t or "existing" in t]
    o.message = (view["state"], view["summary"], [" · ".join(second)])
    # on a tax-map lot the cautious envelope, every lot line 2'-0" nearer (logic.envelope_outlines)
    outlines = logic.envelope_outlines(result.get("envelope"), result.get("plan"))
    shown = _drawn_envelope(doc, facts, dict(result.get("envelope") or {}, outline=outlines[0])) if outlines \
        else None
    env = None
    if STATE.get("envelope_on", True) and shown:
        pieces = [_envelope_brep(doc, dict(shown, outline=ring)) for ring in outlines]
        pieces = [b for b in pieces if b is not None]
        if pieces:
            env = pieces[0]
            for b in pieces[1:]:
                env.Append(b)
    o.envelope = env
    o.box = env.GetBoundingBox(True) if env else rg.BoundingBox.Empty
    drawn = shown if env is not None else None
    o.envelope_lines = _envelope_lines(doc, drawn) if drawn else None
    o.height_limit = (o.envelope_lines[1], logic.height_limit_text((result.get("envelope") or {}).get("top"),
                                                                   _ft_text(drawn["top"] - drawn["base"]))) \
        if o.envelope_lines else None
    o.north = _north(doc, facts)
    o.unmeasured = _unmeasured_outlines(doc, extras.get("not_included"))
    _draw_plan(doc, o, result, sent)
    logic.guard(lambda: _envelope_curves(doc, result.get("plan"), sent),   # the curves to snap to, redrawn
                "draw the curves to snap to")()        # (never measured; a failure never stops the check: F9)
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
    # a real check, of this document, of the model as it was when the check read it: an edit made while it ran is
    # newer, so it is checked again (should_recheck)
    STATE.setdefault("checked_at", {})[doc.RuntimeSerialNumber] = begun["at"]
    if not STATE.get("live"):   # results on screen: edits are noticed from now on, whichever command drew them
        live(True)              # (Edit site…, GordiumFacts, Check: review round 3 of the Check button)
    if result.get("notice"):
        STATE.setdefault("toasts", []).append([result["notice"]])
        if not STATE.get("headless"):
            _toast([result["notice"]])
    shown = logic.labels_on(_ui_state(doc))       # this document's Show on-screen labels
    STATE.setdefault("labels_by_doc", {})[doc.RuntimeSerialNumber] = shown
    if not STATE.get("headless"):
        ui.show(panel(), view, select=logic.newly_failing(extras["before"], view))   # brought into view
        _sync_ticks(doc)
        if result.get("notice"):        # the panel says it too: a view with no corner clear of the model never
            ui.say(STATE.get("panel_parts"), "✕ " + result["notice"])   # draws it (notice_spot)
    if report and result.get("report_error"):   # every caller that asked for a report hears it wasn't written
        first = "✕ " + result["notice"] + " · " if result.get("notice") else ""   # the notice kept in the line
        say(first + logic.report_message(report_path(doc), False, result["report_error"], stale=begun["had_report"]))
    return result


def _check_failed(doc, o, e, facts=None):
    """A check that couldn't run: nothing of an earlier result stays shown, and the panel says why, with Retry."""
    _clear(o)
    logic.guard(lambda: _envelope_curves(doc, None, facts), "clear the curves to snap to")()   # no edit (F1)
    o.doc = doc.RuntimeSerialNumber
    o.message = ("needs_review", "⚠ Check could not run", [str(e)[:120]])
    STATE["last"] = {"error": str(e), "at": time.time()}
    if not STATE.get("headless"):
        ui.show(panel(), None, error=str(e)[:300])
        _sync_ticks(doc)                # (a panel made here shows the document's ticks too)


def _check_outdated(doc, o, report, begun=None, result=None):
    """A check whose answer is of a model no longer in front (edited while it ran, or another document came to the
    front): never drawn or listed as current. In its own document, if still in front: nothing shown as checked, the
    panel says why with Retry, and the model is checked again (live mode); the report written, if any, is said to be
    of the model as it was."""
    STATE["dirty"] = STATE.get("dirty") or time.time()
    STATE["recheck_owed"] = True
    front = Rhino.RhinoDoc.ActiveDoc
    STATE["last"] = {"error": logic.CHECK_OUTDATED, "outdated": True, "at": time.time()}
    if report:                               # written for the model as it was, or not written at all (it says why)
        say(logic.outdated_report_message(report_path(doc), (result or {}).get("report_error"),
                                          (begun or {}).get("had_report")))
    if front is None or front.RuntimeSerialNumber != doc.RuntimeSerialNumber:
        return                               # another document's panel: never this model's results there
    _clear(o)
    o.doc = doc.RuntimeSerialNumber
    o.message = ("needs_review", logic.CHECK_OUTDATED, [])
    if not STATE.get("headless"):
        ui.show(panel(), None, error=logic.CHECK_OUTDATED)


def _check_cancelled(doc, o):
    """A check the architect cancelled: the checker was stopped, nothing in the model changed, and nothing of an
    earlier result stays shown as if it were current (never a pass left standing); Check again in the panel."""
    _clear(o)
    o.doc = doc.RuntimeSerialNumber
    o.message = ("needs_review", logic.CHECK_CANCELLED, [logic.CHECK_CANCELLED_NOTE])
    STATE["last"] = {"error": "the check was cancelled", "cancelled": True, "at": time.time()}
    if not STATE.get("headless"):
        ui.show(panel(), None, cancelled=True)


# ---- live mode's re-check: in the background, the architect keeps working --------------------------------------

def _check_live(doc):
    """Live mode's re-check after an edit, never waiting on Rhino's thread: the model is read now, the checker works
    in the background, and the panel says "Checking…" with what it is doing and Cancel; the answer is drawn when it
    comes (_live_tick), only if the model hasn't changed since it was read (logic.checked_while_still)."""
    if STATE.get("running") or not logic.allowed("check", _box_open()):
        return
    o = overlay()
    STATE["running"] = True
    try:                                     # the saved facts read here; the checker reads them in the job (never a
        lots, buildings, _ = _sorted_objects(doc)          # wait on Rhino's thread: review round 1)
        facts = logic.drop_stale(_read_facts(doc), {str(o.Id) for o in lots}, {str(o.Id) for o in buildings})
        begun = _check_begin(doc, False, facts or {})
        job = _ask_job(begun["request"], True, facts_first=facts)
    except Exception as e:
        STATE["running"] = False
        _check_failed(doc, o, e)
        doc.Views.Redraw()
        return
    STATE["live_check"] = {"job": job, "begun": begun}
    p = STATE.get("panel_parts")
    if not STATE.get("headless") and p is not None and p["form"].Visible:
        ui.show(p, None, checking=True, job=job)
    timer = STATE.get("live_timer")
    if timer is None:
        timer = ef.UITimer()
        timer.Interval = 0.2
        timer.Elapsed += logic.guard(logic.current_only(lambda s, e: _live_tick(), _is_current),
                                     "wait for the re-check")
        STATE["live_timer"] = timer
        LEFTOVERS["live_timer"] = timer.Stop
    timer.Start()


def _live_tick():
    running = STATE.get("live_check")
    if running is None:
        if STATE.get("live_timer") is not None:
            STATE["live_timer"].Stop()
        return
    if not running["job"].finished():
        ui.show_progress(STATE.get("panel_parts"), running["job"])
        return
    _live_finish()


def _live_finish():
    """The live re-check's answer, on Rhino's thread: drawn if it still shows the model in front, the document it
    read; cancelled, said so; an edit made while it ran (or another document in front, a box opened): dropped, and
    the model is checked again at the next idle."""
    running = STATE.get("live_check")
    if running is None or not running["job"].finished():     # only ever a finished one (never "done" with no
        return                                                # answer: review round 2)
    STATE.pop("live_check", None)
    if STATE.get("live_timer") is not None:
        STATE["live_timer"].Stop()
    STATE["running"] = False
    job, begun = running["job"], running["begun"]
    doc = Rhino.RhinoDoc.ActiveDoc
    o = overlay()
    try:
        result = _answer(job)
    except logic.WorkCancelled:
        if doc is not None and doc.RuntimeSerialNumber == begun["doc"]:
            _check_cancelled(doc, o)
            doc.Views.Redraw()                   # the cleared drawing on screen now, not at some later redraw
        return
    except Exception as e:
        if doc is not None and doc.RuntimeSerialNumber == begun["doc"]:
            _check_failed(doc, o, e)
            doc.Views.Redraw()
        return
    if doc is None or doc.RuntimeSerialNumber != begun["doc"] or _box_open() or \
            not logic.checked_while_still(begun["at"], STATE.get("dirty")):
        STATE["dirty"] = STATE.get("dirty") or time.time()      # checked again once the model is still;
        STATE["recheck_owed"] = True             # until then nothing on screen is shown as checked (round 2)
        return
    try:
        _check_apply(doc, o, begun, result)
    except Exception as e:
        _check_failed(doc, o, e)
    finally:
        doc.Views.Redraw()


def _settle_live():
    """A live re-check still running is finished before anything else asks the checker (its pipe answers one
    request at a time): waited for, with its window if slow (Cancel stops it), then drawn or dropped (_live_finish)."""
    while STATE.get("live_check") is not None:
        job = STATE["live_check"]["job"]
        STATE["asking"] = job                # live mode starts no other re-check while this one is waited for
        try:
            ui.wait(job, True, STATE.get("headless"))
        finally:
            STATE.pop("asking", None)
        if STATE.get("live_check") is not None and STATE["live_check"]["job"] is job:
            _live_finish()                   # (its timer may have finished it already, while the window was open)


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
    elif not getattr(o, "toast", None) and STATE.get("toast_timer"):    # cleared with a check's results (_clear):
        STATE["toast_timer"].Stop()                                     # nothing left to time


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


def _layer_key(layer):
    """A layer's (name, parent id) as text, None if it can't be read (logic.layer_edit_counts then counts it)."""
    try:
        return (str(layer.Name), str(layer.ParentLayerId)) if layer is not None else None
    except Exception:                                    # noqa: BLE001  (a layer Rhino has let go of)
        return None


def _layer_changed(sender, e):
    """A layer renamed, moved under another parent, deleted or brought back: which objects are the lot and the
    buildings may have changed, so the results grey out (logic.layer_edit_counts; Gordium's own visibility, lock
    and colour changes don't count)."""
    if logic.layer_edit_counts(str(e.EventType), _layer_key(e.OldState), _layer_key(e.NewState)):
        _changed(sender, e)


def _block_changed(sender, e):
    """A block's contents edited, redefined, deleted or brought back: every building placed from it changed."""
    if logic.block_edit_counts(str(e.EventType)):
        _changed(sender, e)


def _units(doc):
    """The model's units as the check reads them: the unit system's name, the one setting export sends the checker
    (it converts in one place, _scale; this only tells one setting from another)."""
    return str(doc.ModelUnitSystem) if doc is not None else None


def _properties_changed(sender, e):
    """The document's properties changed: an edit if its units did (lengths are read in feet by its scale), noted
    for each document by its serial number (logic.units_edit_counts: a document not noted yet counts)."""
    doc = getattr(e, "Document", None) or Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return
    seen = STATE.setdefault("units_seen", {})
    now = _units(doc)
    if logic.units_edit_counts(seen.get(doc.RuntimeSerialNumber), now):
        seen[doc.RuntimeSerialNumber] = now
        _changed(sender, e)


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
        _sync_ticks(Rhino.RhinoDoc.ActiveDoc)   # its own ticks (Check after every edit too, before the header)
        ui.show(p, None, error="no check yet for this document (press Check)")
    STATE["dirty"] = None               # the last document's edits are not this one's (it is checked below)
    front = Rhino.RhinoDoc.ActiveDoc
    if front is not None:               # its units as they are now: only a change from them counts (a render setting
        STATE.setdefault("units_seen", {}).setdefault(front.RuntimeSerialNumber, _units(front))   # never does)
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
        STATE["stale_shown"] = t                 # (a background re-check still running keeps its line and Cancel)
        if p is not None and p["form"].Visible:
            ui.set_auto_tick(p, _auto(front))
            p["checked_before"] = last_at is not None
            ui.show(p, None, stale=True, job=(STATE.get("live_check") or {}).get("job"))
        _redraw()
    busy = STATE.get("running") or STATE.get("asking") is not None     # a check, or any answer awaited
    if logic.should_check_front(STATE.get("check_front"), busy, _box_open()):
        STATE["check_front"] = False
        if front is not None and front.Strings.GetValue(SECTION, ENTRY):   # it has lot facts: checked once, in the
            STATE["dirty"] = None                      # background (#32: Rhino never waits); it reads the model now,
            _check_live(front)                         # so it covers every edit before it, as the re-check below
            #                                            does: a Cancel stays cancelled (demo 7 Rhino run, 2026-10-28)
    elif logic.should_recheck(t, time.time(), busy, _box_open(), IDLE_SECONDS, last_at, auto=_auto(front)):
        STATE["dirty"] = None
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is not None and doc.Strings.GetValue(SECTION, ENTRY):    # checked before: the check says why
            _check_live(doc)                     # in the background: Rhino never waits on it


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
    for name, handler in STATE.pop("live_more", None) or []:     # the layer, block and units hooks
        _off(Rhino.RhinoDoc, name, handler)
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
    """Notice each edit (objects added, deleted, moved or changed; a layer renamed, moved, deleted or brought back;
    a block's contents edited; the model's units changed): the results grey out until a check; the idle handler
    checks by itself only with Check after every edit ticked."""
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
    # what sorts objects into lot and building, or sizes them, without touching an object: a layer renamed or
    # moved, a block's contents edited, the model's units (the audit of main, 2026-10-29: a ✓ stayed current)
    more = [("LayerTableEvent", _handler(System.EventHandler[Rhino.DocObjects.Tables.LayerTableEventArgs],
                                         _layer_changed, "notice an edit")),
            ("InstanceDefinitionTableEvent", _handler(
                System.EventHandler[Rhino.DocObjects.Tables.InstanceDefinitionTableEventArgs], _block_changed,
                "notice an edit")),
            ("DocumentPropertiesChanged", _handler(System.EventHandler[Rhino.DocumentEventArgs],
                                                   _properties_changed, "notice an edit"))]
    for name, handler in more:
        _on(Rhino.RhinoDoc, name, handler)
    STATE["live_more"] = more
    front = Rhino.RhinoDoc.ActiveDoc
    if front is not None:                    # the units as they are now: only a change from them counts
        STATE.setdefault("units_seen", {}).setdefault(front.RuntimeSerialNumber, _units(front))


def toggle_live():
    """GordiumLive: Check after every edit on or off for this file (the panel's tick). Edits are always noticed (the
    results grey out until checked): turning the edit hooks off would leave old marks showing as current after an
    edit (review round 2 of the Check button)."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
    if not STATE.get("live"):
        live(True)
    set_auto_check(not _auto(doc))


def toggle_envelope():
    STATE["envelope_on"] = not STATE.get("envelope_on", True)
    ui.set_envelope_tick(STATE.get("panel_parts"), STATE["envelope_on"])
    _envelope_everywhere()
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
    _settle_live()                                # a live re-check running: finished first, then the report's own
    if STATE.get("running"):
        say(logic.BUSY)
        return
    path = report_path(doc)
    before = os.path.getmtime(path) if os.path.exists(path) else None
    last = STATE.get("last")
    result = run_check(doc, report=True)          # the check's result stays, even if the file can't be written
    if STATE.get("last") is not last and (STATE.get("last") or {}).get("outdated"):    # edited meanwhile: said
        return                                    # (_check_outdated), never opened as the report of the model now
    if STATE.get("last") is not last and (STATE.get("last") or {}).get("cancelled"):   # this check, cancelled:
        after = os.path.getmtime(path) if os.path.exists(path) else None   # (run_check dropped any half-written copy)
        say(logic.report_cancelled(path, after != before))   # moved in just before Cancel: said, never hidden
        return
    written = result is not None and not result.get("report_error") and os.path.exists(path) and \
        os.path.getmtime(path) != before
    notice = (result or {}).get("notice")      # the check's notice kept in the one line (review round 1: a view
    first = "✕ " + notice + " · " if notice else ""   # with no corner clear of the model shows it nowhere else)
    if not written:
        if not (result or {}).get("report_error"):    # a report error: run_check has said it
            say(first + logic.report_message(path, False, (STATE.get("last") or {}).get("error") or
                                             ("the report file wasn't written to " + os.path.dirname(path))))
        return
    opened, why = ui.open_target(path)            # os.startfile on Windows, `open` on macOS
    say(first + logic.report_message(path, True, opened=opened, open_error=why))


def _drop_report_part(path):
    """The half-written copies a stopped checker may leave beside the report and its site description
    (design_checker.check writes each beside it, then moves it in: neither is ever half written), and the earlier
    site description it set aside while the report was moved in (dropped, never put back: the report it was beside
    may already be replaced). Never raises."""
    folder, name = os.path.dirname(path), os.path.basename(path)
    site = os.path.splitext(name)[0] + logic.SITE_SUFFIX        # its site description's, written just before it
    for part in (os.path.join(folder, "." + name + ".part"), os.path.join(folder, "." + site + ".part"),
                 os.path.join(folder, "." + site + ".old")):
        try:
            if os.path.exists(part):
                os.remove(part)
        except OSError:
            pass


def off():
    if STATE.get("asking") is not None:       # GordiumOff: once the work running is done or cancelled
        say(logic.WORKING)                     # (never the panel and drawing pulled from under it)
        return
    running = STATE.pop("live_check", None)      # a background re-check: stopped, its answer never drawn
    if running is not None:
        running["job"].cancel()
        STATE["running"] = False
    if STATE.get("live_timer") is not None:
        STATE["live_timer"].Stop()
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
    if STATE.get("asking") is not None:   # Gordium is working (Rhino runs during its wait): a command
        say(logic.WORKING)                # typed meanwhile waits its turn, never a second piece of work
        return None
    if Rhino.RhinoDoc.ActiveDoc is None:  # every document closed: say what to do, never crash (nor ask the checker)
        say(logic.NO_DOCUMENT)
        return None
    options = ask({"cmd": "options", "jurisdiction": JURISDICTION})   # (asked first: the model is read after it)
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
    _recover(doc)                       # anything an unfinished start box set aside (Rhino closed), back first
    if not _buildings(doc) and not _lot_candidates(doc):    # an empty model: a new project starts here
        return gordium_start()
    try:
        facts = current_facts(doc)
    except logic.NotInFront:            # another file came to the front while the facts were read
        say(logic.NOT_IN_FRONT)
        return None
    except ValueError:                  # unreadable: confirm again from the suggestions
        facts = {}
    if logic.missing(facts):
        try:                            # the box's undo step ends with the facts saved
            try:
                facts = confirm(doc, logic.with_suggestions(facts, suggested_facts(doc, options["zones"])), options)
            finally:                    # GordiumCheck never draws a starting house: its box's flag goes with it
                STATE.pop("redraw_house", None)
            if facts is None:           # closed or Esc: nothing saved, nothing checked
                Rhino.RhinoApp.WriteLine("Gordium: the lot facts weren't confirmed; nothing was saved")
                return None
            save_facts(doc, facts)
        finally:                        # its Draw's undo step (a reset) ends here, on any way out, before the check:
            _end_undo(doc)              # never left open for the architect's own edits (cold review of d7a5675)
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


def add_floors(doc, start, floor_to_floor=None, design_buffer=0.0):
    """The starting building: one solid per story, stacked, as one group (so a Move moves the house), each on its own
    sublayer Gordium::Massing::Floor 1, 2… (named Floor 1, 2…), with Gordium::Massing::Roof made for the roof, each
    carrying how it was drawn (logic.start_tag: what Switch side yards reads). None, with nothing added, if a floor
    isn't a box Rhino can make."""
    breps = []
    for floor in start["floors"]:
        corners = [_model_point(doc, (x, y), z) for z in (floor["base"], floor["top"]) for x, y in floor["outline"]]
        breps.append(rg.Brep.CreateFromBox(corners) if len(corners) == 8 else None)
    if not breps or any(b is None for b in breps):
        return None                     # nothing added: the caller says so
    group = doc.Groups.Add("Gordium starting building")
    ids = []
    _layer(doc, logic.MASSING_ROOF)          # the roof's sublayer, ready for the architect's roof (the starting house
    for i, (floor, brep) in enumerate(zip(start["floors"], breps)):   # is flat-topped: its top floor's top)
        a = Rhino.DocObjects.ObjectAttributes()
        a.LayerIndex = _layer(doc, logic.massing_floor(i + 1))      # each floor on its own sublayer (Ben, 2026-10-21)
        a.Name = "Floor " + str(i + 1)
        # one story, at the height drawn: what makes it count as a story (a stretched block no longer does)
        a.SetUserString(logic.FLOOR_KEY, str(i + 1) + ";" + repr(floor["top"] - floor["base"]))
        a.SetUserString(logic.START_KEY, logic.start_tag(start, i, floor_to_floor, design_buffer))
        a.AddToGroup(group)
        ids.append(doc.Objects.AddBrep(brep, a))
    return ids


def gordium_start():
    """A new project: the prefilled facts (address, building type, zone, street side) for the architect to confirm,
    then the lot and the largest legal starting building as stacked floors, checked, with live mode on. Starts
    from a model with no building in it (an existing design is checked with GordiumCheck)."""
    if STATE.get("asking") is not None:   # Gordium is working (Rhino runs during its wait): a command
        say(logic.WORKING)                # typed meanwhile waits its turn, never a second piece of work
        return None
    if Rhino.RhinoDoc.ActiveDoc is None:  # every document closed: say what to do, never crash (nor ask the checker)
        say(logic.NO_DOCUMENT)
        return None
    # what the checker gives first (Rhino runs while it is asked: ui.wait), then every read of the model, so nothing
    # read can change under a wait (review of 0702d50: a building drawn during the wait got a house beside it)
    options = ask({"cmd": "options", "jurisdiction": JURISDICTION})
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:                     # every document closed: say what to do, never crash
        say(logic.NO_DOCUMENT)
        return None
    _recover(doc)                       # anything an unfinished start box set aside (Rhino closed), back first
    if _buildings(doc):
        Rhino.RhinoApp.WriteLine("Gordium: " + logic.START_HAS_BUILDING)
        if not STATE.get("auto_ok"):
            import Eto.Forms as ef
            ef.MessageBox.Show(Rhino.UI.RhinoEtoApp.MainWindow, logic.START_HAS_BUILDING, "Gordium",
                               ef.MessageBoxButtons.OK, ef.MessageBoxType.Information)
        return None
    put_down = None                     # (the sample lot is no longer put down: an empty file gets an empty box)
    if not _lot_candidates(doc):        # an empty model: an empty box (Ben, 2026-10-27): the site comes from a
        # lookup, or by hand; no district guessed either (the lookup finds it, or the architect picks it)
        facts = logic.with_suggestions({}, logic.no_guessed_district({}, suggested_facts(doc, options["zones"])))
    else:                               # the architect's own lot: their saved facts, else the suggestions
        try:
            saved = current_facts(doc)
        except logic.NotInFront:        # another file came to the front while the facts were read
            say(logic.NOT_IN_FRONT)
            return None
        except ValueError:
            saved = {}
        facts = logic.with_suggestions(saved or {}, suggested_facts(doc, options["zones"]))
        if _buildings(doc):             # a building drawn while the facts were read: GordiumCheck's, not a start
            say(logic.START_HAS_BUILDING)
            return None
    drawn = False
    try:
        facts = confirm(doc, facts, options, "start")
        if facts is None:
            Rhino.RhinoApp.WriteLine("Gordium: nothing was started (the facts weren't confirmed)")
            return None
        drawn = True
        save_facts(doc, facts)
        return _draw_starting_house(doc, facts)
    except logic.WorkCancelled as stopped:   # Cancel (or the model changed) while the house was worked out: rolled back
        say(getattr(stopped, "said", logic.DRAW_CANCELLED))
        return None
    finally:
        STATE.pop("start_plan", None)
        if put_down is not None and not drawn:     # Cancel (the box's, or Draw's): the file as before GordiumStart
            logic.guard(_take_back_sample, "take back the sample lot")(doc, *put_down)
        _end_undo(doc)


def _take_back_sample(doc, lot_id, ui_before, layers_before):
    """The sample lot GordiumStart put down before its box, taken back when the box ended without a Draw (its Cancel,
    or Cancel while Draw worked out the house): the lot, the box's choices it wrote, the layer it made. Left behind,
    the next GordiumStart took it for the architect's own lot with no facts and drew no house (Rhino run of #32
    aea73b8: "Draw again" after a cancelled Draw drew nothing)."""
    table = RhinoTable(doc)
    if table.exists(lot_id):
        table.delete(lot_id)
    if ui_before is None:
        doc.Strings.Delete(SECTION, UI_ENTRY)
    else:                                # (through the one write boundary: it was written through it too)
        _save_ui_state(doc, json.loads(ui_before))
    for path in sorted(set(table.layer_names()) - set(layers_before), key=lambda p: -p.count("::")):
        table.remove_layer_if_empty(path)


def _start_request(doc, facts, saved_ui):
    """The checker's request for the starting house: the model as the box left it (a lookup may have drawn a new
    lot; what the box holds aside is never sent), the facts, the floor to floor (11'-8" unless GordiumFacts set
    another) and the design buffer (Draw is off if it can't be read). Always the envelope and the 3-floor house."""
    path = os.path.join(tempfile.gettempdir(), "gordium_start_" + str(doc.RuntimeSerialNumber) + ".3dm")
    export(doc, path)
    return {"cmd": "start", "model": path, "facts": check_facts(doc, facts),
            "floor_to_floor": logic.parse_feet(saved_ui.get("floor_to_floor")) or logic.FLOOR_TO_FLOOR,
            "design_buffer": logic.parse_feet(saved_ui.get("design_buffer")) or 0.0}


def _start_key(request):
    """What a starting house was worked out for: all but the copy's file name and the lot's id (a new address's
    house is worked out on a copy of its lot before the lot itself is drawn: _plan_reset_house)."""
    facts = {k: v for k, v in (request.get("facts") or {}).items() if k != "lot_id"}
    return json.dumps(dict({k: v for k, v in request.items() if k not in ("model", "facts")}, facts=facts),
                      sort_keys=True, default=str)


DRY_LOT = "gordium-planned-lot"      # the id of a new address's lot in the copy its house is worked out on


class _DryTable:
    """RhinoTable's reads, with a reset's own writes kept aside: what a Draw of a new address would draw (its lot),
    worked out with nothing in the model changed."""

    def __init__(self, doc):
        self.real, self.ring = RhinoTable(doc), None

    def __getattr__(self, name):
        return getattr(self.real, name)

    def add_lot(self, ring, name):
        self.ring = ring
        return DRY_LOT

    def add_spot(self, p):
        return None

    def apply(self, plan, session, facts, saved_ui):
        """The plan carried out on this copy (its own add_lot and add_spot), never on the real table's."""
        return logic.carry_out(plan, self, session, facts, saved_ui)


class _DrySession:
    def add(self, ids):
        pass

    def hold(self, object_id):
        pass


def _reset_state(doc, facts, options, saved_ui, mode, shown):
    """The box's state to save after a reset (logic.after_reset_state): the architect's choices as the box showed
    them, the lot, street side, corner and ground as the reset left them. The one way both the real Draw and its dry
    plan (_plan_reset_house) get it, so the house worked out before the reset is the one Draw draws (cold review of
    f51ed45, P1: the plan used the box's old state and never matched)."""
    return logic.after_reset_state(shown, _box_state(doc, facts, options, saved_ui, mode))


def _plan_reset_house(doc, facts, state, saved_ui, choice, mode, options):
    """A new address's starting house, worked out before Draw opens its undo step and changes the model: the reset
    run dry (logic.apply_reset on _DryTable) gives the new lot and the facts, the checker gets a copy with that lot
    alone. None when this Draw draws no house (Keep my building, the City's outline only, GordiumCheck's box).
    logic.WorkCancelled (Cancel) or logic.ModelChanged (edited meanwhile): nothing has changed."""
    dry = _DryTable(doc)
    f, s, redraw, guide = logic.apply_reset(dry, _DrySession(), dict(facts), dict(saved_ui), choice,
                                            STATE.get("zones") or [])
    # the same test as _drawn's (logic.plans_house with this reset's redraw), and only with a lot to plan it on
    if not (dry.ring and logic.plans_house(mode, redraw and mode == "check", STATE.get("house_after_box"))):
        return None
    out, ui_state = _apply_box(doc, f, _reset_state(doc, f, options, s, mode, state), s)
    read_at = time.time()
    path = os.path.join(tempfile.gettempdir(), "gordium_start_" + str(doc.RuntimeSerialNumber) + ".3dm")
    _export_lot(doc, dry.ring, path)
    request = {"cmd": "start", "model": path, "facts": check_facts(doc, dict(out, lot_id=DRY_LOT)),
               "floor_to_floor": logic.parse_feet(ui_state.get("floor_to_floor")) or logic.FLOOR_TO_FLOOR,
               "design_buffer": logic.parse_feet(ui_state.get("design_buffer")) or 0.0}
    start = ask(request, cancel=True)
    if _changed_during(doc.RuntimeSerialNumber, read_at):
        raise logic.ModelChanged()
    return {"key": _start_key(request), "start": start}


def _export_lot(doc, ring, path):
    """A small .3dm with one lot outline (in feet, on Site, its id DRY_LOT): the copy a new address's starting house
    is worked out on (the house never depends on the buildings: check.start leaves them out)."""
    f = Rhino.FileIO.File3dm()
    f.Settings.ModelUnitSystem = doc.ModelUnitSystem
    for kind in ("lot", "building"):
        layer = Rhino.DocObjects.Layer()
        layer.Name = LAYERS[kind]
        f.AllLayers.Add(layer)
    points = [_model_point(doc, p) for p in ring]
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = 0
    attrs.SetUserString(ID_KEY, DRY_LOT)
    f.Objects.Add(rg.PolylineCurve(points + [points[0]]), attrs)
    f.Write(path, 8)


def _plan_house(doc, facts, saved_ui):
    """The starting house Draw will draw, worked out before the box commits, Cancel allowed (logic.WorkCancelled
    rolls the box back: nothing drawn). The model sent is the one Draw draws on (Gordium's objects held aside by the
    box are never sent)."""
    read_at = time.time()
    request = _start_request(doc, facts, saved_ui)
    start = ask(request, cancel=True)
    if _changed_during(doc.RuntimeSerialNumber, read_at):   # edited meanwhile: never a house for another model
        raise logic.ModelChanged()
    return {"key": _start_key(request), "start": start}


def _draw_starting_house(doc, facts):
    """The largest legal starting house for the lot, as stacked floors, checked (GordiumStart, and Edit site's Draw
    of a new address); its "as first drawn" note and its fingerprint (rhino_logic.own_work: edited or not) saved."""
    plan = STATE.pop("start_plan", None)        # worked out at Draw, before the box committed (_drawn)
    read_at = time.time()
    request = _start_request(doc, facts, _ui_state(doc))
    _set_source(doc, "starting_house", None, None)           # an earlier start's margin is gone with its house
    if plan is not None and plan["key"] == _start_key(request):
        start = plan["start"]
        STATE["start_from"] = "plan"     # (the in-Rhino tests read which way it came)
    else:                               # (no plan, or one for other facts: never another lot's house); the box has
        STATE["start_from"] = "asked"
        start = ask(request)            # committed by now: no Cancel (never a lot without its house); the
                                                 # floors go in a step of Gordium's after the wait
        if _changed_during(doc.RuntimeSerialNumber, read_at):     # edited meanwhile: never a house for the lot
            say(logic.HOUSE_OUTDATED)                              # as it was (review of 5567b94)
            live(True)                  # the architect draws one; it is checked as they go (as when none can be drawn)
            documents(True)
            return None
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
    ids = add_floors(doc, start, request["floor_to_floor"], request["design_buffer"])
    if ids is None:
        Rhino.RhinoApp.WriteLine("Gordium: the starting building couldn't be drawn; " + logic.draw_one_hint(_auto(doc)))
        live(True)
        documents(True)
        return None
    table = RhinoTable(doc)
    _save_ui_state(doc, dict(_ui_state(doc), house_fingerprint=table.fingerprint(table.massing()),
                             drawn_address=facts.get("address")))
    fact = logic.starting_house_fact(start.get("margin_note"), logic.city_day())   # Gordium's figure
    if fact:
        _set_source(doc, "starting_house", fact["value"], fact["source"], fact["confirmed_by"])
    doc.Views.Redraw()
    result = run_check(doc, report=False)
    live(True)
    documents(True)
    frame_site(doc, facts)
    Rhino.RhinoApp.WriteLine("Gordium: created 1 group (" + str(len(start["floors"])) + " floor solids) on " +
                             logic.MASSING + "::Floor 1…" + str(len(start["floors"])))
    return result


def _start_floors(doc):
    """The starting house's floor blocks in the model (each carrying logic.START_KEY), with their bounding boxes in
    feet, their volumes in cubic feet (None when not a solid Rhino can measure: then never redrawn) and whether each
    is locked or hidden, itself or by its layer (then never redrawn: Rhino deletes neither, and the architect's lock
    and Hide starting house are kept; review round 3)."""
    found = []
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.HiddenObjects = True                # every floor, whatever its state (a hidden one is refused, said so)
    settings.LockedObjects = True
    for o in doc.Objects.GetObjectList(settings):
        text = o.Attributes.GetUserString(logic.START_KEY) if not o.IsDeleted else None
        if text:
            b = o.Geometry.GetBoundingBox(True)
            props = rg.VolumeMassProperties.Compute(o.Geometry) if isinstance(o.Geometry, rg.Brep) else None
            volume = _feet_volume(doc, props.Volume) if props is not None else None    # (a notch changes it)
            layer = doc.Layers[o.Attributes.LayerIndex]       # (a locked or hidden parent too: IsLocked, IsVisible)
            locked = bool(o.IsLocked or o.IsHidden or o.IsReference or layer.IsLocked or not layer.IsVisible)
            found.append((o, text, (tuple(_feet_point(doc, b.Min)), tuple(_feet_point(doc, b.Max))), volume, locked))
    return found


def switch_side_yards():
    """Switch side yards (the panel, under the Starting house site fact): where the district lets the two side yards
    differ (R-2b: one 10 ft, the other 5 ft), the starting house is redrawn with the larger one on the other side,
    as one Undo step. The new house is proven by the checker like the first (a house that would break a rule is
    never drawn: the old one stays and the panel says why); a house the architect has changed is never redrawn."""
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:                     # every file closed: say what to do, touch nothing
        say(logic.NO_DOCUMENT)
        return None
    found = _start_floors(doc)
    plan = logic.switch_plan([(text, box, volume, locked) for _, text, box, volume, locked in found], tolerance=_feet_length(
        doc, doc.ModelAbsoluteTolerance) + 0.01)
    if plan.get("refused"):
        say(plan["refused"])
        return None
    try:
        facts = current_facts(doc)
    except ValueError as e:
        say("The site facts can't be read, so the starting house isn't redrawn: " + str(e))
        return None
    path = os.path.join(tempfile.gettempdir(), "gordium_switch_" + str(doc.RuntimeSerialNumber) + ".3dm")
    export(doc, path)                   # (the checker leaves the model's buildings out when it draws a new house)
    start = ask({"cmd": "start", "model": path, "facts": check_facts(doc, facts),
                 "floor_to_floor": plan["floor_to_floor"], "design_buffer": plan["design_buffer"],
                 "larger_side": plan["larger_side"]})
    split = start.get("side_split") or {}
    if not start.get("floors") or split.get("larger_side") != plan["larger_side"]:
        why = "; ".join(start.get("notes") or []) or "no house could be drawn that way"
        say("The larger side yard can't go on the " + plan["larger_side"] + " (" + why + "): the starting house is "
            "kept as it was.")
        return None
    record = doc.BeginUndoRecord("Gordium: " + logic.SWITCH_LABEL.lower())
    STATE["switch_record"] = record              # 0 inside a running command (its own Undo step): for the tests
    try:                                # the new house first: if it can't be drawn, the old one is untouched
        ids = add_floors(doc, start, plan["floor_to_floor"], plan["design_buffer"])
        if ids is None:
            say("The switched starting house couldn't be drawn; the old one is kept.")
            return None
        gone = []
        for o, _, _, _, _ in found:
            if not doc.Objects.Delete(o, True):
                break
            gone.append(o)
        kept = len(found) - len(gone)
        if kept:                        # never two houses: the new one goes again, the old one stays whole (round 2,
            for o in gone:              # F1; round 4: the floors already deleted come back)
                doc.Objects.Undelete(o)
            for i in ids:
                new = doc.Objects.FindId(i)
                if new is not None:
                    doc.Objects.Delete(new, True, True)
            say("The old starting house couldn't be removed (" + str(kept) + " floors), so it is kept as it was.")
            return None
        fact = logic.starting_house_fact(start.get("margin_note"), logic.city_day())
        if fact:
            _set_source(doc, "starting_house", fact["value"], fact["source"], fact["confirmed_by"])
    finally:
        doc.EndUndoRecord(record)
    doc.Views.Redraw()
    result = run_check(doc, report=False)
    say("Starting house redrawn. " + (_said_sides(start) or ""))
    return result


def _said_sides(start):
    """The new house's side yards, as its note says them ("Side yards: 10'-0" on the right (east), …")."""
    note = start.get("margin_note") or ""
    at = note.find(logic.SIDE_YARDS_SAID)
    return note[at:] if at >= 0 else None


# ---- the context map: the neighbourhood around a looked-up lot (design_checker.context_box) ---------------------
# Drawn after Draw on its own grey layers under Gordium::Context, which the checker never measures
# (rhino_logic.classify; a solid there over the lot makes the check need review: rhino_logic.left_out_candidate).
# Only what rhino_logic.context_objects allows is written into the file (sources whose store is raw: the State's
# parcels, streets and building footprints, and Gordium's own frame, north arrow, scale bar and credits). The
# footprints' layer is left unlocked: the architect drags and edits them, and an edited outline is theirs (Ben,
# 2026-10-21). A source that may not be kept (store: none) would be drawn on screen only, by the overlay.

CONTEXT_GREYS = {"Parcels": (150, 150, 150), "Streets": (120, 120, 120), "Buildings": (135, 135, 135),
                 "Notes": (110, 110, 110)}


ENVELOPE_BLUE = (29, 95, 138)


def _envelope_curves(doc, plan, facts):
    """The buildable outline and each yard's required line as real curves on a locked Gordium::Envelope layer, for
    the architect to snap to (Osnap; Ben, 2026-10-21): on a tax-map lot the cautious outline solid and the outline
    as drawn dashed (logic.envelope_curves). Each is tagged Gordium's (ENVELOPE_KEY), never measured
    (logic.classify), and replaced at every check: the old ones deleted first whatever the layer's state (hidden,
    locked, or under a locked "Gordium": deleted ignoring those modes; review of feature 4, F1), and the new ones
    drawn only once none is left, so they never pile up. None of it is recorded for Undo, inside a command too
    (GordiumCheck's Undo step never stops on them: F6). The layer shown only with "Show buildable envelope".
    `plan` None: only the old ones go (no layer made for that: a failed check in a file Gordium never drew in
    leaves no Gordium layers). How many old ones could not be deleted (0: all replaced; else the layer hidden and
    the architect told, so stale curves never pass for current ones). Replacing them is no edit of the model: the
    "model changed" mark (STATE["dirty"], set by live mode's hooks on every add and delete) is left as it was
    (UX review 2026-10-27: after any check but the first, its own redraw greyed the results it had just shown;
    review of feature 4, round 4, F1: a failed check's clearing did the same)."""
    if plan is None and doc.Layers.FindByFullPath(logic.ENVELOPE, -1) < 0:
        return 0
    dirty = STATE.get("dirty")
    was = doc.UndoRecordingEnabled
    doc.UndoRecordingEnabled = False             # the layer too: an Undo never removes it from under the curves
    try:                                         # (review of dd44f1b, F1)
        index = _layer(doc, logic.ENVELOPE)
        layer = doc.Layers[index]
        if layer.Color.ToArgb() == System.Drawing.Color.Black.ToArgb():          # a new layer: Gordium's blue
            layer.Color = System.Drawing.Color.FromArgb(*ENVELOPE_BLUE)
        for old in _envelope_objects(doc, index):
            doc.Objects.Delete(old, True, True)        # quiet, ignoring hidden and locked
        left = len(_envelope_objects(doc, index))
        if left:                                   # never a second set over the first, nor stale ones shown as
            layer.IsVisible = False                # current (review of dd44f1b, F2)
            say("the curves to snap to couldn't be replaced (" + str(left) + " left); hidden until the "
                "next check")
            return left
        z = _lot_level(doc, facts or {})
        dashed = doc.Linetypes.Find("Dashed")
        for c in logic.envelope_curves(plan):
            pts = [_model_point(doc, p, z) for p in c["points"]]
            if c["closed"]:
                pts.append(pts[0])
            if len(pts) < 2:
                continue
            attrs = Rhino.DocObjects.ObjectAttributes()
            attrs.LayerIndex = index
            attrs.Name = "Gordium: " + c["what"]
            attrs.SetUserString(logic.ENVELOPE_KEY, c["what"])
            if c["dashed"] and dashed >= 0:
                attrs.LinetypeSource = Rhino.DocObjects.ObjectLinetypeSource.LinetypeFromObject
                attrs.LinetypeIndex = dashed
            doc.Objects.AddPolyline(pts, attrs)
        _show_envelope_layer(doc)
        return 0
    finally:
        doc.UndoRecordingEnabled = was
        STATE["dirty"] = dirty


def _envelope_objects(doc, index):
    """Gordium's curves on its Envelope layer (tagged ENVELOPE_KEY), whatever the layer's state."""
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.HiddenObjects = True
    settings.LockedObjects = True
    settings.LayerIndexFilter = index
    return [o for o in doc.Objects.GetObjectList(settings) if o.Attributes.GetUserString(logic.ENVELOPE_KEY)]


def _show_envelope_layer(doc):
    """The Envelope layer shown with "Show buildable envelope", hidden without it, and locked (its own lock: under a
    locked "Gordium" too); not recorded for Undo."""
    index = doc.Layers.FindByFullPath(logic.ENVELOPE, -1)
    if index < 0:
        return
    layer = doc.Layers[index]
    was = doc.UndoRecordingEnabled
    doc.UndoRecordingEnabled = False
    try:
        layer.IsVisible = bool(STATE.get("envelope_on", True))
        _set_own_lock(doc, layer, True)
    finally:
        doc.UndoRecordingEnabled = was


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
    locking a parent locks each sublayer, and unlocking it gives each sublayer its persistent lock
    (Layer.GetPersistentLocking), which only SetPersistentLocking under a locked parent records: a sublayer locked
    before its parent comes out unlocked, in plain Rhino too (grade_lock_probe.json at e997f0e). Under a locked parent
    IsLocked reads True for every sublayer and says nothing about its own lock (the Rhino job's probe at e631aae)."""
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
    Each layer's own lock, so a redraw or a first draw under a locked "Gordium" keeps them (the Rhino job at
    e997f0e); a parent before its sublayers, so a parent's change can't undo a sublayer's set before it. Drawn while
    "Gordium" is unlocked, a layer locked by IsLocked records no own lock, so the architect locking and unlocking
    "Gordium" afterwards unlocked Parcels, Streets and Notes (grade_lock_probe.json): so Gordium::Context, Gordium's
    own layer, is locked for a moment while each sublayer is given its own lock, which only a locked layer above lets
    it record, and Rhino keeps it through later locks and unlocks of "Gordium" (lock_probe_994012d.json: relock,
    nested_relock)."""
    indexes = _context_layer_indexes(doc)
    for i in logic.outermost_first([(i, doc.Layers[i].FullPath) for i in indexes]):
        _set_own_lock(doc, doc.Layers[i], bool(locked) and logic.context_locked(doc.Layers[i].FullPath))
    top = doc.Layers.FindByFullPath(logic.CONTEXT, -1)
    if top < 0 or doc.Layers[top].IsLocked or _parent_locked(doc, doc.Layers[top]):
        return                              # under a locked "Gordium" each own lock is already recorded
    doc.Layers[top].IsLocked = True         # a moment: its sublayers can record their own locks
    if not doc.Layers[top].IsLocked:        # refused (the architect's current layer is under it): nothing touched
        return                              # more, not even an unlock of a layer never locked (review round 3)
    for i in indexes:
        if i != top:
            doc.Layers[i].SetPersistentLocking(bool(locked) and logic.context_locked(doc.Layers[i].FullPath))
    doc.Layers[top].IsLocked = False        # each sublayer back as its own lock says


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
    for i, _, locked, _ in was:            # a parent before its sublayers (locking it locks them all),
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
    with logic.undo_step(doc, logic.UNDO_WORDS["context"]):   # the tick, the layers and any fetch drawn: one step
        _save_ui_state(doc, dict(_ui_state(doc), show_context=bool(on)))     # per file (coordinator, 2026-10-21)
        STATE.setdefault("context_by_doc", {})[doc.RuntimeSerialNumber] = bool(on)
        drawn = _context_visible(doc, on)
        refetch = logic.needs_refetch(STATE.get("context_guides"), _context_record(doc), doc.RuntimeSerialNumber)
        loaded = not refetch
        if on and refetch:                 # draw_context says what it drew, or why it couldn't
            try:
                facts = current_facts(doc)
            except ValueError:
                facts = {}
            draw_context(doc, logic.context_frame(facts, _ui_state(doc)))
    if on and not refetch:                 # (fetched: draw_context has said what it drew)
        doc.Views.Redraw()
        say("Neighbourhood shown (drawing only: the check never measures it).")
    elif not on:
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
    elif key == "label_timer":
        value.Stop()
    elif key == "live_timer":                  # the timer an earlier copy's background re-check waited with
        value.Stop()
    elif key == "live_check":                  # a re-check an earlier copy was waiting for: its answer is dropped
        value["job"].cancel()
    elif key == "worker":
        _stop_worker()
    elif key == "worker_sends":
        value.put(None)


# an earlier copy's handlers, drawing, panel and checker: undone (LEFTOVERS), released and forgotten (STATE)
STATE["running"] = False                     # an earlier copy's background re-check, if any, is dropped by the
STATE.pop("asking", None)                    # sweep (nothing of this copy's is running while it loads)
STATE.pop("edit_watch", None)                # (its handlers are an earlier copy's: LEFTOVERS detaches them)
logic.sweep(LEFTOVERS, STATE, _release)
if STATE.get("live"):                        # live mode was on before this copy loaded: its hooks back on
    live(True)
# Rhino closing: the checker stopped with it (and any an earlier load left: SERVERS)
_on(Rhino.RhinoApp, "Closing", _handler(System.EventHandler, lambda s, e: _stop_worker(), "stop the checker"))
# Undo / Redo: what was drawn for the model before it is cleared, never left on screen (the Rhino job, demo e631aae)
_on(Rhino.Commands.Command, "UndoRedo", _handler(System.EventHandler[Rhino.Commands.UndoRedoEventArgs], _undo_redo,
                                                 "clear the drawing after Undo or Redo"))
