#! python3
"""RHINO_QUEUE 15: the bend question needs an explicit Yes or No. Head from bend_wt.txt. The sample, Corner lot?
Yes, the street side picked again (the box's Change…): one Ithaca Rd piece clicked, then the side street; the
plugin's own question about the side street's far corner is answered through a stand-in for Rhino's GetOption (the
answers scripted, nothing typed into Rhino):
A. Enter: asked again, starting "Gordium needs a Yes or a No here (Esc: nothing changes) …"; then Esc: the command
   line says "Esc: nothing changed (the street side is as it was)", the street lines (the blue line) as before.
B. The same picks, the answer No: the side street kept without the bend, "Street 2: 2 lot-line pieces, …".
Writes bend/out.json ("done": true) and Top captures; closes its document."""
import copy
import json
import os
import sys
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

H = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
WT = open(H + "bend_wt.txt", encoding="utf-8").read().strip()
S = H + "bend/"
os.makedirs(S, exist_ok=True)
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close  # noqa: E402

log, opened, g = {"head": WT, "claims": {}}, [], None


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}


def fresh_module():
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None and hasattr(loaded, "off"):
        loaded.off()
    state = sc.sticky.setdefault("gordium_state", {})
    w = state.pop("worker", None)
    if w is not None:
        try:
            w.terminate()
        except Exception:
            pass
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


class Answers:
    """A stand-in for Rhino.Input.Custom.GetOption: each Get() takes the next scripted answer ("enter", "esc",
    "yes", "no") and records the prompt it was asked with."""
    script, prompts = [], []

    def __init__(self):
        self.options, self.picked = [], None

    def SetCommandPrompt(self, text):
        Answers.prompts.append(str(text))

    def AddOption(self, name):
        self.options.append(name)
        return len(self.options)                         # Rhino's option indexes start at 1

    def AcceptNothing(self, on):
        pass

    def Get(self):
        answer = Answers.script.pop(0) if Answers.script else "esc"
        if answer == "enter":
            return Rhino.Input.GetResult.Nothing
        if answer == "esc":
            return Rhino.Input.GetResult.Cancel
        self.picked = self.options.index("Yes" if answer == "yes" else "No") + 1
        return Rhino.Input.GetResult.Option

    def OptionIndex(self):
        return self.picked


class _Custom(object):
    def __getattr__(self, name):
        return Answers if name == "GetOption" else getattr(Rhino.Input.Custom, name)


class _Input(object):
    Custom = _Custom()

    def __getattr__(self, name):
        return getattr(Rhino.Input, name)


class _Rhino(object):
    Input = _Input()

    def __getattr__(self, name):
        return getattr(Rhino, name)


def capture(doc, name):
    view = doc.Views.Find("Top", False)
    doc.Views.ActiveView = view
    view.Redraw()
    view.CaptureToBitmap(view.ActiveViewport.Size).Save(S + name + ".png")


docs = TestDocs("bend").__enter__()
try:
    g = fresh_module()
    doc = docs.open("Large Objects - Feet")
    opened.append(doc)
    g.gordium_check()                                    # an empty file: GordiumStart, the sample drawn and checked
    base = dict(g.current_facts(doc), corner_lot=True)
    lot = g._find(doc, base.get("lot_id") or "")
    segs = list(g._segments(lot.Geometry))
    street0 = [[list(p) for p in line] for line in base.get("street_line") or []]
    fp = lambda q: g._feet_point(doc, q)[:2]             # noqa: E731
    same = lambda s, line: (all(abs(a - b) < 0.05 for a, b in zip(list(fp(s[0])) + list(fp(s[1])), line[0] + line[1]))
                            or all(abs(a - b) < 0.05 for a, b in zip(list(fp(s[0])) + list(fp(s[1])),
                                                                     line[1] + line[0])))
    on_street = lambda s: any(same(s, line) for line in street0)                                  # noqa: E731
    east = max((p for line in street0 for p in line), key=lambda p: p[0])                         # Ithaca Rd's east end
    touches = lambda s: any(abs(fp(q)[0] - east[0]) < 0.05 and abs(fp(q)[1] - east[1]) < 0.05 for q in s)  # noqa
    first = next(s for s in segs if on_street(s))
    side = next(s for s in segs if not on_street(s) and touches(s))
    mids = [(s[0] + s[1]) / 2 for s in (first, side)]
    real_rhino, real_point = g.Rhino, g._get_point

    def pick(answers):
        facts, saved = copy.deepcopy(base), dict(g._ui_state(doc))
        clicks = [(Rhino.Commands.Result.Success, m) for m in mids] + [(Rhino.Commands.Result.Nothing, None)]
        Answers.script, Answers.prompts = list(answers), []
        said = len(g.STATE.get("said") or [])
        g.Rhino, g._get_point = _Rhino(), (lambda prompt: clicks.pop(0))
        try:
            facts, saved = g._box_pick(doc, "street", facts, saved)
        finally:
            g.Rhino, g._get_point = real_rhino, real_point
        return facts, list(Answers.prompts), (g.STATE.get("said") or [])[said:]

    before = copy.deepcopy(base.get("street_line"))
    log["before_lines"] = len(before or [])
    facts_a, prompts_a, said_a = pick(["enter", "esc"])
    log["A"] = {"prompts": prompts_a, "said": said_a, "lines": len(facts_a.get("street_line") or [])}
    claim("A the bend question is asked, and Enter asks again, starting 'Gordium needs a Yes or a No here (Esc: "
          "nothing changes)'", len(prompts_a) == 2 and prompts_a[1].startswith(
              "Gordium needs a Yes or a No here (Esc: nothing changes)"), prompts_a)
    claim("A Esc: 'Esc: nothing changed (the street side is as it was)'",
          "Esc: nothing changed (the street side is as it was)" in said_a, said_a)
    claim("A the street lines (the blue line) as they were", facts_a.get("street_line") == before,
          {"before": len(before or []), "after": len(facts_a.get("street_line") or [])})
    capture(doc, "A_after_esc_street_as_before")
    facts_b, prompts_b, said_b = pick(["no"])
    log["B"] = {"prompts": prompts_b, "said": said_b, "lines": len(facts_b.get("street_line") or []),
                "ids": facts_b.get("street_ids")}
    claim("B the same picks, No: the side street kept without the bend (Street 2: 2 lot-line pieces)",
          len(prompts_b) == 1 and any(t.startswith("Street 2: 2 lot-line pieces") for t in said_b)
          and len(facts_b.get("street_line") or []) == 10, log["B"])
    g._highlight(doc, facts_b)
    capture(doc, "B_after_no")
    log["ok"] = all(c["ok"] for c in log["claims"].values())
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    if g is not None:
        g.Rhino = Rhino
    for d in opened:
        try:
            close(d)
        except Exception:
            pass
    try:
        if g is not None:
            g._stop_worker()
    except Exception:
        pass
    log["done"] = True
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), indent=1, default=str)
