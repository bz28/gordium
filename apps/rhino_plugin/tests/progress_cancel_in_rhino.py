#! python3
"""Live progress and Cancel (PR: progress-cancel), in Rhino 8, each claim asserted. Run in Rhino, not in CI; the
logic is tested in CI (packages/design_checker/tests/test_progress.py). The checker is slowed down for the test
(tests/slow_checker.py: "Slow test: waiting…" then SLOW seconds before each check or start) so there is time to
see the work and cancel it; the lookup uses recorded answers paused at each step (lookup_box --slow). A fresh feet
document, then:
1. A check with the slow checker: Rhino keeps running while it waits (a separate timer ticks at least 8 times in
   the 3 s), the wait window's job says the checker's own steps ("Slow test: waiting…", then its stages), the panel
   says "Checking…" with that live line; the check then finishes normally.
2. The same check cancelled after 1 s (the Cancel button's own action, job.cancel): run_check returns within 2.5 s,
   says "Check cancelled", the drawing is cleared, the model's objects and the file's saved strings are unchanged,
   and the next check (the real checker again) works.
3. Zoning report… cancelled after 1 s: the report file already there is byte for byte as it was, and no half-written
   copy is left beside it; Gordium said the report was cancelled and the file unchanged.
4. GordiumStart on an empty file, the slow checker on "start", Cancel after 1 s while it finds the largest
   building: nothing is drawn, the model and the file's strings are as they were before GordiumStart (the sample
   lot it put down before its box is taken back), and Gordium said "Draw cancelled". Then GordiumStart again with
   the real checker draws the house. (GordiumStart's one undo step for a Draw with its house is not claimed here:
   this script runs outside a command, as the panel's buttons do; re_lookup_in_rhino.py claims one undo step for
   Edit site's Draw of a new address.)
5. Live mode: an edit starts a background re-check (Rhino not waiting: the script's own timer keeps ticking), the
   panel shows "Checking…" with its line and Cancel; Cancel: "Check cancelled", nothing drawn, not running.
6. Live mode: a second edit while a background re-check runs: its answer is dropped (the model changed after it
   read it), and the model is then checked again and shown.
7. The real start box: Look up of 96 Ithaca Rd (recorded, 1 s per step): the box's line changes as the lookup goes
   (its step and seconds), the button reads "Cancel lookup"; pressed: the lookup process is stopped, the box opens
   again without the running line, saying "Look up of … cancelled: nothing changed.", Draw as it was with the
   address typed before Look up (off: "Press Look up to find … first."), the model unchanged; then the box is closed.
Writes <temp>/gordium_progress_cancel/out.json ("done": true at the end); closes its documents."""
import json
import os
import sys
import tempfile
import time
import traceback

import Rhino
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "packages", "design_checker", "design_checker"))
import rhino_logic as logic  # noqa: E402  (its guard: no callback may raise into Rhino)

S = os.path.join(tempfile.gettempdir(), "gordium_progress_cancel") + "/"
os.makedirs(S, exist_ok=True)
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SLOW = 3.0
log = {"claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


def fresh_module():
    state = sc.sticky.setdefault("gordium_state", {})
    w = state.pop("worker", None)
    if w is not None:
        w.terminate()
    for name in ("gordium_rhino", "rhino_logic", "gordium_ui"):
        sys.modules.pop(name, None)
    state.clear()
    state.update({"repo": WT, "extra_paths": [], "auto_ok": True})
    app = WT + "/apps/rhino_plugin"
    if app in sys.path:
        sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino
    return gordium_rhino


def objects(doc):
    return {str(o.Id): doc.Layers[o.Attributes.LayerIndex].FullPath for o in doc.Objects}


def strings(g, doc):
    return {k: doc.Strings.GetValue(g.SECTION, k) for k in (g.ENTRY, g.UI_ENTRY, g.SOURCES_ENTRY)}


def slow(g, on):
    """The slow checker (or the real one again), started fresh at the next request."""
    g._stop_worker()
    if on:
        g.STATE["worker_command"] = [g._python(), "-u", os.path.join(WT, "apps/rhino_plugin/tests/slow_checker.py"),
                                     str(SLOW)]
    else:
        g.STATE.pop("worker_command", None)


class Watch:
    """A UI timer of the script's own: proves Rhino keeps running while Gordium waits, records what the job it
    waits for says, and presses Cancel (the button's own action) after `cancel_at` s."""

    def __init__(self, g, cancel_at=None, key="asking"):
        import Eto.Forms as ef
        self.g, self.cancel_at, self.key, self.ticks, self.steps, self.panel = g, cancel_at, key, 0, [], []
        self.cancelled = []                  # the step each cancelled job was on
        self.began = time.time()
        self.timer = ef.UITimer()
        self.timer.Interval = 0.1
        self.timer.Elapsed += logic.guard(self.tick, "watch the wait")
        self.timer.Start()

    def job(self):
        v = self.g.STATE.get(self.key)
        return v.get("job") if isinstance(v, dict) else v

    def tick(self, s, e):
        try:
            self.ticks += 1
            job = self.job()
            if job is not None:
                if job.step not in self.steps:
                    self.steps.append(job.step)
                lab = (self.g.STATE.get("panel_parts") or {}).get("progress_label")
                if lab is not None and lab.Text not in self.panel:
                    self.panel.append(lab.Text)
                # only work the architect could cancel (a check, the house, the report: never the checker starting)
                if self.cancel_at is not None and time.time() - self.began >= self.cancel_at and job.cancellable():
                    self.cancelled.append(job.step)
                    job.cancel()
        except Exception:
            log.setdefault("watch_errors", []).append(traceback.format_exc())

    def stop(self):
        self.timer.Stop()


def pump_until(cond, limit):
    """Let Rhino run (idle, timers) until cond() or `limit` s."""
    end = time.time() + limit
    while not cond() and time.time() < end:
        Rhino.RhinoApp.Wait()
        time.sleep(0.05)
    return cond()


def add_box(doc, layer, at=0.0):
    import Rhino.Geometry as rg
    index = doc.Layers.FindByFullPath(layer, -1)
    if index < 0:
        l = Rhino.DocObjects.Layer()
        l.Name = layer
        index = doc.Layers.Add(l)
    a = Rhino.DocObjects.ObjectAttributes()
    a.LayerIndex = index
    box = rg.Box(rg.Plane.WorldXY, rg.Interval(10 + at, 20 + at), rg.Interval(30, 40), rg.Interval(0, 10))
    return doc.Objects.AddBrep(box.ToBrep(), a)


def main():
    doc = None
    try:
        docs = TestDocs("progress_cancel").__enter__()
        g = fresh_module()
        doc = docs.open("Large Objects - Feet")
        g.gordium_check()                                  # an empty file: the sample and its house, real checker
        g.live(False)
        claim("0 the sample is drawn and checked", g.STATE.get("last", {}).get("summary") is not None,
              g.STATE.get("last"))

        # 1. a slow check: Rhino keeps running, the steps are the checker's own
        slow(g, True)
        g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})     # (the slow checker started first)
        w = Watch(g)
        frames = []                          # the wait window's own lines, as it sets them (ui.WAIT_SHOWN)
        g.ui.WAIT_SHOWN = lambda step, line: frames.append([round(time.time(), 2), step, line])
        began = time.time()
        result = g.run_check(doc, report=False)
        w.stop()
        g.ui.WAIT_SHOWN = None
        log["window_frames"] = frames
        marks = {f[2].split()[0] for f in frames}
        seconds = [int(f[2].split()[1]) for f in frames]
        claim("1 the wait window's own mark moves and its seconds count up (never frozen)",
              len(marks) == 3 and seconds and seconds[-1] >= 2 and seconds == sorted(seconds),
              {"marks": sorted(marks), "seconds": sorted(set(seconds)), "frames": len(frames)})
        claim("1 Rhino kept running while the check waited", w.ticks >= 8, {"ticks": w.ticks,
                                                                            "s": round(time.time() - began, 1)})
        claim("1 the wait said the checker's own steps", "Slow test: waiting…" in w.steps and
              any(s in w.steps for s in ("Reading the model…", "Measuring the building…", "Checking the rules…")),
              w.steps)
        claim("1 the panel said Checking… with the live line (the checker's step and the seconds)",
              any(t.startswith("Slow test: waiting…") and " s" in t for t in w.panel), w.panel)
        claim("1 the slow check finished normally", result is not None, g.STATE.get("last"))

        # 2. cancelled
        before, said_before = objects(doc), strings(g, doc)
        w = Watch(g, cancel_at=1.0)
        began = time.time()
        result = g.run_check(doc, report=False)
        took = time.time() - began
        w.stop()
        o = g.STATE.get("overlay")
        claim("2 Cancel: run_check returned within 2.5 s, nothing shown as checked",
              result is None and took < 2.5 and (g.STATE.get("last") or {}).get("cancelled") and
              o is not None and not (o.red or o.encroach or o.yard_dims) and o.message[1] == g.logic.CHECK_CANCELLED,
              {"took": round(took, 2), "last": g.STATE.get("last")})
        claim("2 Cancel: the model and the file are as they were", objects(doc) == before and
              strings(g, doc) == said_before)
        slow(g, False)
        claim("2 the next check (a fresh checker) works", g.run_check(doc, report=False) is not None,
              g.STATE.get("last"))

        # 3. the zoning report, cancelled
        path = g.report_path(doc)
        g.run_check(doc, report=True)
        old = open(path, "rb").read() if os.path.exists(path) else None
        slow(g, True)
        g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})     # (the slow checker started first)
        w = Watch(g, cancel_at=1.0)
        g.open_report()
        w.stop()
        claim("3 the report's own check was the work cancelled", w.cancelled == ["Slow test: waiting…"], w.cancelled)
        part = os.path.join(os.path.dirname(path), "." + os.path.basename(path) + ".part")
        claim("3 Cancel: the report file is as it was, no half-written copy",
              old is not None and open(path, "rb").read() == old and not os.path.exists(part),
              {"path": path, "part_left": os.path.exists(part)})
        claim("3 Gordium said the report was cancelled", g.logic.REPORT_CANCELLED in (g.STATE.get("said") or [])[-1:],
              (g.STATE.get("said") or [])[-3:])

        # 4. Draw cancelled while the starting house is worked out
        doc2 = docs.open("Large Objects - Feet")
        g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})     # (the slow checker started again first)
        seen = {}
        empty, empty_strings = objects(doc2), strings(g, doc2)    # before GordiumStart: an empty file
        g.STATE["on_confirm"] = lambda d, facts, text, state: seen.update(objects=objects(d), strings=strings(g, d))
        w = Watch(g, cancel_at=1.0)
        got = g.gordium_start()
        w.stop()
        g.STATE.pop("on_confirm", None)
        claim("4 the work cancelled was the starting house's", w.cancelled == ["Slow test: waiting…"], w.cancelled)
        now = objects(doc2)
        # the sample lot GordiumStart put down before its box is taken back too (Rhino run of aea73b8: left behind,
        # the next GordiumStart took it for the architect's lot and drew no house)
        claim("4 Cancel during Draw: nothing drawn, the model as before GordiumStart (the sample taken back)",
              got is None and now == empty and seen.get("objects") and now != seen.get("objects"),
              {"now": now, "before": empty, "at_box": seen.get("objects")})
        claim("4 Cancel during Draw: the file's strings as before GordiumStart", strings(g, doc2) == empty_strings,
              {"now": strings(g, doc2), "before": empty_strings})
        claim("4 Gordium said Draw was cancelled", g.logic.DRAW_CANCELLED in (g.STATE.get("said") or []),
              (g.STATE.get("said") or [])[-3:])
        slow(g, False)
        g.gordium_start()
        drawn = objects(doc2)
        claim("4 Draw again (nothing cancelled) draws the starting house", [p for p in drawn.values() if "Massing" in p],
              {"drawn": len(drawn)})

        # 5. live mode: a background re-check, cancelled from the panel
        g.gordium_check()                                  # the sample again, checked; live on
        g.live(True)
        slow(g, True)
        g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})
        add_box(doc2, "Building")
        w = Watch(g, key="live_check")
        pump_until(lambda: g.STATE.get("live_check") is not None, 10)
        job = (g.STATE.get("live_check") or {}).get("job")
        pump_until(lambda: len(w.panel) >= 2, 3)
        ticks = w.ticks
        claim("5 a background re-check started; Rhino not waiting on it; the panel's line moves",
              job is not None and ticks >= 5 and len(w.panel) >= 2, {"ticks": ticks, "panel": w.panel})
        job.cancel()                                      # (the panel's Cancel button's own action)
        pump_until(lambda: g.STATE.get("live_check") is None, 5)
        w.stop()
        claim("5 Cancel: Check cancelled, nothing drawn, not running",
              (g.STATE.get("last") or {}).get("cancelled") and not g.STATE.get("running") and
              not (g.STATE["overlay"].red or g.STATE["overlay"].encroach), g.STATE.get("last"))

        # 6. an edit while a background re-check runs: its answer dropped, then checked again
        add_box(doc2, "Building", at=30)
        pump_until(lambda: g.STATE.get("live_check") is not None, 10)
        first = g.STATE["live_check"]["begun"]["at"]
        add_box(doc2, "Building", at=60)                  # edited while it runs
        pump_until(lambda: g.STATE.get("live_check") is None, SLOW + 10)
        claim("6 the stale answer was dropped", g.logic.last_check_at(g.STATE.get("checked_at"),
                                                                       doc2.RuntimeSerialNumber) != first)
        pump_until(lambda: (g.logic.last_check_at(g.STATE.get("checked_at"), doc2.RuntimeSerialNumber) or 0) > first
                   and g.STATE.get("live_check") is None, 2 * SLOW + 15)
        claim("6 then the model as it is was checked and shown",
              (g.logic.last_check_at(g.STATE.get("checked_at"), doc2.RuntimeSerialNumber) or 0) > first and
              (g.STATE.get("last") or {}).get("summary") is not None, g.STATE.get("last"))
        g.live(False)
        slow(g, False)

        # 7. the real start box: the lookup's live line and Cancel lookup
        g.STATE["auto_ok"] = False
        g.STATE.update(lookup_fixture="96_ithaca_rd", lookup_slow=1)
        model = objects(doc2)
        boxes = []

        def shown(dialog):
            import Eto.Forms as ef
            texts = [c.Text for c in dialog.Children if isinstance(c, ef.Label)]
            buttons = {c.Text: c for c in dialog.Children if isinstance(c, ef.Button)}
            draw = next((c for t, c in buttons.items() if t in ("Draw", "Check")), None)
            run = g.STATE.get("lookup")
            boxes.append({"texts": texts, "buttons": sorted(buttons), "draw_on": bool(draw and draw.Enabled),
                          "lookup_running": run is not None and run["proc"].poll() is None})
            n = len(boxes)
            if n == 1:                                   # the box: the address typed, Look up
                box = next(c for c in dialog.Children if isinstance(c, ef.TextBox))
                box.Text = "96 Ithaca Rd, Ithaca, NY 14850"         # (TextChanged sets Draw and its reason)
                draw = next((c for t, c in buttons.items() if t in ("Draw", "Check")), None)
                boxes[-1]["draw_typed"] = bool(draw and draw.Enabled)
                boxes[-1]["reason_typed"] = [c.Text for c in dialog.Children if isinstance(c, ef.Label)
                                             and (c.Text or "").startswith("Press Look up")]
                buttons["Look up"].PerformClick()
            elif n == 2:                                 # looking: read the line twice, then Cancel lookup
                lines = []
                t = ef.UITimer()
                t.Interval = 1.2

                def later(s, e):
                    lab = [c.Text for c in dialog.Children if isinstance(c, ef.Label) and c.Text.startswith("Looking up")]
                    lines.append(lab[0] if lab else None)
                    if len(lines) == 2:
                        t.Stop()
                        boxes[-1]["lines"] = lines
                        buttons["Cancel lookup"].PerformClick()
                t.Elapsed += logic.guard(later, "read the lookup line")
                t.Start()
            else:                                        # after Cancel lookup: close the box
                buttons["Cancel"].PerformClick()

        g.STATE["on_box_shown"] = shown
        g.edit_facts()
        g.STATE.pop("on_box_shown", None)
        log["boxes"] = boxes
        looking = boxes[1] if len(boxes) > 1 else {}
        lines = looking.get("lines") or [None, None]
        claim("7 while looking: the button reads Cancel lookup and the line moves (step, seconds)",
              "Cancel lookup" in looking.get("buttons", []) and lines[0] and lines[1] and lines[0] != lines[1], looking)
        after = boxes[2] if len(boxes) > 2 else {}
        claim("7 after Cancel lookup: no running line, says cancelled, Look up back",
              "Look up" in after.get("buttons", []) and
              not any((t or "").startswith("Looking up") for t in after.get("texts", [])) and
              any("cancelled: nothing changed" in (t or "") for t in after.get("texts", [])), after)
        claim("7 Cancel lookup stopped the lookup while the box was still open, the model unchanged",
              not after.get("lookup_running", True) and objects(doc2) == model, after)
        reason = [t for t in after.get("texts", []) if (t or "").startswith("Press Look up to find 96 Ithaca Rd")]
        claim("7 after Cancel lookup, Draw is as it was with the address typed before Look up (off, saying why)",
              after.get("draw_on") == boxes[0].get("draw_typed") is False and reason and
              reason == boxes[0].get("reason_typed"), {"boxes": boxes})
        log["ok"] = True
    except Exception:
        log["ok"] = False
        log["error"] = traceback.format_exc()
        raise                                # a failed claim fails the run loudly
    finally:
        log["done"] = True                   # always: the run ended, passed or not ("ok" says which)
        try:
            g = sys.modules.get("gordium_rhino")
            if g is not None:                # the slow checker never outlives the run
                g.STATE.pop("worker_command", None)
                g._stop_worker()
                g.ui.WAIT_SHOWN = None
        except Exception:
            pass
        json.dump(log, open(S + "out.json", "w", encoding="utf-8"), indent=1, default=str)
        try:
            g = sys.modules.get("gordium_rhino")
            if g is not None:                    # never left on the slow checker or the test's hooks
                for k in ("worker_command", "lookup_fixture", "lookup_slow", "on_box_shown", "on_confirm"):
                    g.STATE.pop(k, None)
                g.STATE["auto_ok"] = False
                g.off()
                g._stop_worker()
        except Exception:
            pass
        for d in list(Rhino.RhinoDoc.OpenDocuments())[:-1]:
            close(d)


def run_as_the_architect():
    """main() outside any command, as the panel's buttons run (re_lookup_in_rhino.py does the same): now if no
    command is running, else at the next idle once this one has ended. From the idle nothing may raise into Rhino: a
    failure is in out.json ("error") and on the command line."""
    if os.path.exists(S + "out.json"):          # never an earlier run's result read as this one's
        os.remove(S + "out.json")

    def guarded():
        try:
            main()
        except Exception:
            Rhino.RhinoApp.WriteLine("progress_cancel_in_rhino FAILED: see " + S + "out.json")
        else:
            Rhino.RhinoApp.WriteLine("progress_cancel_in_rhino: all claims pass")
    if not Rhino.Commands.Command.InCommand():
        guarded()
        return

    def once(sender, e):
        Rhino.RhinoApp.Idle -= idle
        guarded()
    idle = System.EventHandler(logic.guard(once, "run outside a command"))
    Rhino.RhinoApp.Idle += idle
    Rhino.RhinoApp.WriteLine("progress_cancel_in_rhino: runs when this command ends; wait for " + S +
                             "out.json to say \"done\": true")


run_as_the_architect()
