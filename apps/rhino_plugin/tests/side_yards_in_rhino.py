#! python3
"""Switch side yards in Rhino 8 (UX review 2026-10-27): the Rhino side of it. Every claim is recorded (the run goes on
past a failing one) and the run fails at the end if any did. Run in Rhino, not in CI: which side the larger yard
goes on, and that both houses comply, are tested in CI (packages/design_checker/tests/test_side_yards.py).
A fresh feet document, GordiumStart on the sample (106 Ithaca Rd, R-1b: 10 ft side yards on both sides).
1. Each floor block GordiumStart drew carries how it was drawn (logic.START_KEY); R-1b: no larger side.
2. Switch side yards on R-1b's house says there is nothing to switch, and changes nothing.
3. A house recorded with its larger yard on the left, the real checker asked for the right: R-1b has no larger
   side, so it refuses, says why, and the house is kept (never a house the checker didn't give).
4. The checker's answer stood in for (R-2b is in another PR): a house 5 ft to the west with its larger yard on the
   right. Switch replaces the house (new floors, each on its sublayer, one group, tagged "right"), the Starting
   house fact names the side, the panel offers the button under it (logic.can_switch), and it says what it did.
5. One Undo brings the first house back and removes the new one; Redo brings the new one back.
6. A house the architect has moved is never redrawn: refused, nothing changes.
Writes <temp>/gordium_side_yards/out.json; closes its document."""
import json
import os
import sys
import tempfile
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_side_yards") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
log = {"claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}


def fresh_module():
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:
        loaded.off()
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


def floors(g, doc):
    return sorted(((str(o.Id), json.loads(text)) for o, text, _, _ in g._start_floors(doc)), key=lambda f: f[1]["story"])


def retag(g, doc, side):
    for o, text, _, _ in g._start_floors(doc):
        tag = dict(json.loads(text), larger_side=side)
        attrs = o.Attributes.Duplicate()
        attrs.SetUserString(g.logic.START_KEY, json.dumps(tag))
        doc.Objects.ModifyAttributes(o, attrs, True)


def said(g):
    return (g.STATE.get("said") or [""])[-1]


def undo(doc, redo=False):
    fn = getattr(doc, "Redo" if redo else "Undo", None)
    return fn() if fn is not None else Rhino.RhinoApp.RunScript("_Redo" if redo else "_Undo", False)


doc = None
real_ask = None
g = None
try:
    g = fresh_module()
    doc = TestDocs("side_yards").__enter__().open("Large Objects - Feet")
    g.gordium_check()                                    # GordiumStart's flow on the sample
    first = floors(g, doc)
    log["first"] = [(i, t["larger_side"], t["story"]) for i, t in first]
    claim("1 every floor block tagged with how it was drawn; R-1b: no larger side",
          first and len(first) == len(g._buildings(doc)) and all(t["larger_side"] is None for _, t in first),
          log["first"])
    ids = [i for i, _ in first]
    g.switch_side_yards()
    claim("2 R-1b's house: nothing to switch, nothing changed",
          "same on both sides" in said(g) and [i for i, _ in floors(g, doc)] == ids, said(g))
    retag(g, doc, "left")
    g.switch_side_yards()                                # the real checker: R-1b gives no larger side
    claim("3 the real checker gives no house with the larger yard on the right: refused, house kept",
          "can't go on the right" in said(g) and [i for i, _ in floors(g, doc)] == ids, said(g))
    real_ask = g.ask
    sent = []

    def ask(request):
        if request.get("cmd") != "start" or not request.get("larger_side"):
            return real_ask(request)
        sent.append(request)
        moved = [{**f, "outline": [[x - 5.0, y] for x, y in f["outline"]]} for f in
                 [{"outline": t["outline"], "base": t["base"], "top": t["top"]} for _, t in first]]
        return {"floors": moved, "notes": [], "side_split": {"larger_side": request["larger_side"]},
                "margin_note": "Largest house the rules allow; limited by the yards. Side yards: 10'-0\" on the "
                               "right (east), 5'-0\" on the left (west), seen from the street."}

    g.ask = ask
    g.switch_side_yards()
    second = floors(g, doc)
    note = (g.fact_sources(doc).get("starting_house") or {}).get("value") or ""
    house = list(g._buildings(doc))
    layers = sorted((doc.Layers[o.Attributes.LayerIndex].FullPath, o.Attributes.Name) for o in house)
    groups = {tuple(o.Attributes.GetGroupList() or []) for o in house}
    log.update(second=[(i, t["larger_side"]) for i, t in second], note=note, layers=layers, sent=sent)
    claim("4 asked for the right; the house replaced: new floors, tagged right, on their sublayers, one group",
          sent and sent[-1]["larger_side"] == "right" and len(second) == len(first)
          and not set(ids) & {i for i, _ in second} and all(t["larger_side"] == "right" for _, t in second)
          and layers == [(g.logic.massing_floor(n), "Floor " + str(n)) for n in range(1, len(second) + 1)]
          and len(groups) == 1, {"second": log["second"], "layers": layers})
    claim("4 the Starting house fact names the side, the panel offers the button, and it says what it did",
          "10'-0\" on the right (east)" in note and g.logic.can_switch("Starting house: " + note)
          and "Starting house redrawn" in said(g), [note, said(g)])
    undo(doc)
    back = floors(g, doc)
    claim("5 one Undo brings the first house back and removes the new one",
          sorted(i for i, _ in back) == sorted(ids), [i for i, _ in back])
    undo(doc, redo=True)
    claim("5 Redo brings the new house back", sorted(i for i, _ in floors(g, doc)) == sorted(i for i, _ in second),
          [i for i, _ in floors(g, doc)])
    o = g._start_floors(doc)[0][0]
    doc.Objects.Transform(o, rg.Transform.Translation(g._model_length(doc, 3.0), 0, 0), True)
    before = [i for i, _ in floors(g, doc)]
    g.switch_side_yards()
    claim("6 a moved house is never redrawn: refused, nothing changed",
          "changed since Gordium drew it" in said(g) and [i for i, _ in floors(g, doc)] == before, said(g))
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    if g is not None and real_ask is not None:
        g.ask = real_ask
    log["passed"] = sum(c["ok"] for c in log["claims"].values())
    log["ok"] = bool(log["claims"]) and log["passed"] == len(log["claims"]) and "trace" not in log
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    if doc is not None:
        close(doc)
print("side_yards_in_rhino: %d of %d claims pass%s" % (log["passed"], len(log["claims"]),
                                                      "" if "trace" not in log else " (stopped: see trace)"))
assert log["ok"], [n for n, c in log["claims"].items() if not c["ok"]] or log.get("trace")
