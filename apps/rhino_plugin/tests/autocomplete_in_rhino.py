#! python3
"""Address type-ahead in the real start box (PR: address-autocomplete), in Rhino 8, each claim asserted. Run in
Rhino, not in CI; the logic is tested in CI (packages/design_checker/tests/test_autocomplete.py,
packages/site_lookup/tests/test_suggest.py). Stand-in addresses (site_lookup's tests: hand-written, never the
City's data) and recorded lookups: no live call. A fresh feet document, GordiumStart (the sample, 106 Ithaca Rd),
then Edit site… with a script driving the box (typing is setting the address field's text, as a key does):
1. "106" typed: no list after 1 s (fewer than 4 characters).
2. "106 Itha", typed a character at a time 0.05 s apart: ONE request after the pause (not one per key), and within
   3 s the list under the address shows "106 Ithaca Rd, Ithaca, NY"; the list is the box's own (a ListBox).
3. Picking it (the list's own pick: what Enter or a click does): the address field says "106 Ithaca Rd, Ithaca,
   NY", the list closes, and no new request is made for the picked text.
4. A stale answer: the stand-in slowed to 1.5 s; "96 Itha" typed, then 0.5 s later "1060 Ith": the first request is
   stopped, and the list only ever shows 1060's address, never 96's.
5. Offline: the stand-in unreachable; "96 Itha": no list, the quiet note "Suggestions unavailable: type the full
   address and press Look up."; the box still works (Look up still on).
6. "96 Ithaca Rd" (no town) and Look up: the lookup is asked for "96 Ithaca Rd, Ithaca, NY".
7. A lookup that finds no lot ("999 Nowhere St", recorded answers have none): the box says "The lot shown is still
   106 Ithaca Rd's: nothing in the model changed."; the model unchanged. Then the box is closed (Cancel).
By hand (keys can't be scripted in Eto): in the address, type "106 Itha", press Down (the first suggestion
selected), Enter (picked), Enter again (Look up); type "120 N Cay", click a suggestion; with the list open, Esc
closes the list and not the box.
Writes <temp>/gordium_autocomplete/out.json ("done": true at the end); closes its documents."""
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

S = os.path.join(tempfile.gettempdir(), "gordium_autocomplete") + "/"
os.makedirs(S, exist_ok=True)
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
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


class Script:
    """Drives one start box from a UI timer: each step is (seconds to wait, fn(dialog)); the box closes at the end."""

    def __init__(self, steps):
        self.steps, self.at = list(steps), None

    def run(self, dialog):
        import Eto.Forms as ef
        timer = ef.UITimer()
        timer.Interval = 0.05
        self.at = time.time()

        def tick(s, e):
            if not self.steps:
                timer.Stop()
                return
            wait, fn = self.steps[0]
            if time.time() - self.at >= wait:
                self.steps.pop(0)
                self.at = time.time()
                try:
                    fn(dialog)
                except Exception:
                    log.setdefault("step_errors", []).append(traceback.format_exc())
                    self.steps = []
                    timer.Stop()
                    dialog.Close(False)
        timer.Elapsed += logic.guard(tick, "drive the start box")
        dialog.Closed += logic.guard(lambda s, e: timer.Stop(), "stop driving the box")
        timer.Start()


def parts(dialog):
    import Eto.Forms as ef
    kids = list(dialog.Children)
    return {"address": next(c for c in kids if isinstance(c, ef.TextBox)),
            "list": next((c for c in kids if isinstance(c, ef.ListBox)), None),
            "labels": [c.Text for c in kids if isinstance(c, ef.Label)],
            "buttons": {c.Text: c for c in kids if isinstance(c, ef.Button)}}


def main():
    doc = None
    try:
        docs = TestDocs("autocomplete").__enter__()
        g = fresh_module()
        doc = docs.open("Large Objects - Feet")
        g.gordium_check()                                  # an empty file: the sample (106 Ithaca Rd) drawn
        g.live(False)
        g.STATE["auto_ok"] = False
        g.STATE["lookup_fixture"] = "96_ithaca_rd"
        model = objects(doc)
        asked = []
        start = g._suggest_start

        def counted(text):
            asked.append([round(time.time(), 2), text])
            return start(text)
        g._suggest_start = counted
        g.SUGGESTER["start"] = counted
        seen = {}

        def typing(text, gap=0.0):
            steps = []
            for k in range(1, len(text) + 1):
                steps.append((gap, lambda d, t=text[:k]: setattr(parts(d)["address"], "Text", t)))
            return steps

        def note(key):
            def record(d):
                p = parts(d)
                seen[key] = {"items": [str(i.Text) for i in p["list"].Items] if p["list"] is not None else None,
                             "visible": bool(p["list"] is not None and p["list"].Visible),
                             "address": p["address"].Text, "asked": len(asked), "labels": p["labels"],
                             "look_up_on": bool(p["buttons"].get("Look up") and p["buttons"]["Look up"].Enabled)}
            return record

        def pick_first(d):
            p = parts(d)
            p["list"].SelectedIndex = 0
            p["list"].Tag(0)             # the list's own pick, the one Enter, a click and a double click call

        boxes = []

        def shown(dialog):
            boxes.append(len(boxes))
            n = len(boxes)
            if n == 1:
                Script(
                    [(0.2, lambda d: setattr(parts(d)["address"], "Text", "106")), (1.0, note("1"))] +
                    typing("106 Itha", 0.05)[3:] + [(3.0, note("2"))] +
                    [(0.1, pick_first), (1.0, note("3"))] +
                    [(0.0, lambda d: g.STATE.update(suggest_slow=1.5))] +
                    typing("96 Itha", 0.0)[-1:] + [(0.5, lambda d: setattr(parts(d)["address"], "Text", "1060 Ith"))] +
                    [(2.5, note("4"))] +
                    [(0.0, lambda d: g.STATE.update(suggest_slow=0, suggest_offline=True))] +
                    [(0.0, lambda d: setattr(parts(d)["address"], "Text", "96 Itha")), (2.0, note("5"))] +
                    [(0.0, lambda d: g.STATE.update(suggest_offline=False)),
                     (0.0, lambda d: setattr(parts(d)["address"], "Text", "96 Ithaca Rd")),
                     (0.5, lambda d: parts(d)["buttons"]["Look up"].PerformClick())]).run(dialog)
            elif n == 2:                                   # looking up 96: the query asked
                seen["6"] = {"query": (g.STATE.get("lookup") or {}).get("query")}
            elif n == 3:                                   # 96's answer in: now a lookup that finds nothing
                Script([(0.2, lambda d: setattr(parts(d)["address"], "Text", "999 Nowhere St")),
                        (0.3, lambda d: parts(d)["buttons"]["Look up"].PerformClick())]).run(dialog)
            elif n == 4:
                pass                                       # looking up 999: wait for its answer
            else:                                          # its answer in: read the box, then Cancel
                Script([(0.3, note("7")), (0.2, lambda d: parts(d)["buttons"]["Cancel"].PerformClick())]).run(dialog)

        g.STATE["on_box_shown"] = shown
        g.edit_facts()
        log["seen"], log["asked"] = seen, asked
        one, two, three = seen.get("1", {}), seen.get("2", {}), seen.get("3", {})
        claim("1 fewer than 4 characters: no list, nothing asked", not one.get("visible") and one.get("asked") == 0, one)
        claim("2 typed a character at a time: one request after the pause, the list shows 106's address",
              two.get("asked") == 1 and two.get("visible") and two.get("items") == ["106 Ithaca Rd, Ithaca, NY"],
              {"seen": two, "asked": asked})
        claim("3 picked: the address field says it, the list closed, no new request",
              three.get("address") == "106 Ithaca Rd, Ithaca, NY" and not three.get("visible") and
              three.get("asked") == two.get("asked"), three)
        four = seen.get("4", {})
        claim("4 a stale answer is never shown: only 1060's address",
              four.get("items") == ["1060 Ithaca Rd, Ithaca, NY"] or (not four.get("visible") and not four.get("items")),
              four)
        claim("4 the newer typing was asked for", any(t == "1060 Ith" for _, t in asked), asked)
        five = seen.get("5", {})
        claim("5 offline: no list, the quiet note, Look up still on",
              not five.get("visible") and logic.SUGGESTIONS_UNAVAILABLE in five.get("labels", []) and
              five.get("look_up_on"), five)
        claim("6 no town typed: the lookup asked for 96 Ithaca Rd, Ithaca, NY",
              (seen.get("6") or {}).get("query") == "96 Ithaca Rd, Ithaca, NY", seen.get("6"))
        seven = seen.get("7", {})
        claim("7 a lookup that found no lot: the box says the lot shown is still 106's, the model unchanged",
              any("The lot shown is still 106 Ithaca Rd's: nothing in the model changed." in (t or "")
                  for t in seven.get("labels", [])) and objects(doc) == model, seven)
        log["done"] = True
    except Exception:
        log["error"] = traceback.format_exc()
        raise
    finally:
        json.dump(log, open(S + "out.json", "w", encoding="utf-8"), indent=1, default=str)
        try:
            g = sys.modules.get("gordium_rhino")
            if g is not None:                    # never left with the test's hooks
                for k in ("lookup_fixture", "suggest_slow", "suggest_offline", "on_box_shown"):
                    g.STATE.pop(k, None)
                g.STATE["auto_ok"] = False
                g.off()
                g._stop_worker()
        except Exception:
            pass
        for d in list(Rhino.RhinoDoc.OpenDocuments())[:-1]:
            close(d)


def run_as_the_architect():
    """main() outside any command, as the panel's buttons run: now if no command is running, else at the next idle."""
    if os.path.exists(S + "out.json"):
        os.remove(S + "out.json")

    def guarded():
        try:
            main()
        except Exception:
            Rhino.RhinoApp.WriteLine("autocomplete_in_rhino FAILED: see " + S + "out.json")
        else:
            Rhino.RhinoApp.WriteLine("autocomplete_in_rhino: all claims pass")
    if not Rhino.Commands.Command.InCommand():
        guarded()
        return

    def once(sender, e):
        Rhino.RhinoApp.Idle -= idle
        guarded()
    idle = System.EventHandler(logic.guard(once, "run outside a command"))
    Rhino.RhinoApp.Idle += idle
    Rhino.RhinoApp.WriteLine("autocomplete_in_rhino: runs when this command ends; wait for " + S + "out.json")


run_as_the_architect()
