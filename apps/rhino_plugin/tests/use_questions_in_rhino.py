#! python3
"""The start box's Use and its follow-up questions (Ben, 2026-10-25), in Rhino 8: what only the real box can show.
Every claim is recorded (the run goes on past a failing one) and the run fails at the end if any did. Run in Rhino,
not in CI: the logic is tested in CI (packages/design_checker/tests/test_use_questions.py).
A fresh feet document; the box opened on facts (no lot needed), closed by itself after each claim.
1. R-1b, one-family detached: the Use dropdown lists R-1b's chart uses, the permitted four first, then the three by
   special permit; one-family detached picked; exactly the questions R-1b's rules need for it (the worker's
   follow_ups: none before #38, its household and home occupation questions after), the box under 900 px wide.
2. R-1b, school: the amber line under Use says it isn't permitted by right in R-1b, with the chart's page.
3. A district whose rules need the units, rooms let and new-or-conversion for a multiple dwelling (the options as
   the worker would send them for R-3a): three questions after Use, two number fields and a dropdown reading
   Not answered / New construction / Conversion of an existing building; typing "lots" in the last number field
   says at once, in the one note under the questions, that it isn't kept.
4. Picking another use whose questions differ closes the box asking to open it again ("pick:refresh").
5. A saved use the district doesn't list (two-family in R-1b) stays picked, with its line saying the Use row won't
   comply.
6. Each district's box for its first use, as the worker sends it: under 900 px wide (a 1366 x 768 laptop), its
   longest question's words wrapped beside its answer (the R-1b box was 1,560 px with #38's questions on one line).
Writes <temp>/gordium_use_questions/out.json; closes its document."""
import json
import os
import sys
import tempfile
import traceback

import Eto.Forms as ef
import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_use_questions") + "/"
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


def controls(dialog):
    return list(dialog.Content.Children)


def drop_items(d):
    return [d.Items[i].Text for i in range(d.Items.Count)]


def open_box(g, doc, options, facts, act=None):
    """The real start box on these facts; `act(dialog, seen)` runs once it is shown (then it closes by itself
    unless `act` closed it). Returns (what the box returned, what was seen)."""
    seen = {}
    state = g._box_state(doc, dict(facts, jurisdiction=g.JURISDICTION), options, {}, "start")

    def shown(dialog):
        found = controls(dialog)
        seen["labels"] = [c.Text for c in found if isinstance(c, ef.Label)]
        seen["drops"] = [drop_items(c) for c in found if isinstance(c, ef.DropDown)]
        seen["picked"] = [c.SelectedValue.Text if c.SelectedValue else None for c in found
                          if isinstance(c, ef.DropDown)]
        seen["texts"] = [c for c in found if isinstance(c, ef.TextBox)]
        seen["box"] = {"width": int(dialog.Width), "height": int(dialog.Height)}
        if act is not None:
            act(dialog, found, seen)
        if dialog.Visible:
            timer = ef.UITimer()
            timer.Interval = 0.3
            timer.Elapsed += g.logic.guard(lambda s, e: (timer.Stop(), dialog.Close(False)), "close the box")
            timer.Start()

    state["_on_shown"] = shown
    what = g.ui.start_box(state, options, "start")
    seen.pop("texts", None)
    return what, seen


doc = None
try:
    g = fresh_module()
    doc = TestDocs("use_questions").__enter__().open("Large Objects - Feet")
    options = g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})
    r1b = options["district_uses"]["R-1b"]
    names = [u["name"] for u in r1b]
    _, seen = open_box(g, doc, options, {"zone": "R-1b", "use": "one_family_detached"})
    use_drop = next((d for d in seen["drops"] if names[0] in d), None)
    log["1"] = seen
    want = [g.logic.STATED_FACTS[k][0] for k in g.logic.follow_up_keys(options, "R-1b", "one_family_detached")]
    claim("1 the Use dropdown lists R-1b's chart uses, permitted first, one-family detached picked, its questions",
          use_drop == names and [u["permitted"] for u in r1b] == [True] * 4 + [False] * 3
          and names[0] in seen["picked"] and all(t in seen["labels"] for t in want)
          and any(g.logic.FOLLOW_UP_HELP in t for t in seen["labels"]) == bool(want)
          and 0 < seen["box"]["width"] <= 900, dict(seen, want=want))
    _, seen = open_box(g, doc, options, {"zone": "R-1b", "use": "school"})
    log["2"] = seen
    claim("2 school in R-1b: the amber line says not permitted by right, with the chart's page",
          any(t.startswith("Not permitted by right in R-1b: Marked SP") and "p.2" in t for t in seen["labels"]), seen)
    # a district whose rules need the three facts for a multiple dwelling (as the worker sends R-3a's)
    x = dict(options, zones=list(options["zones"]) + ["X"])
    x["district_uses"] = dict(options["district_uses"], X=[
        {"id": "one_family_detached", "name": "One-family dwelling, detached", "permitted": True, "note": None},
        {"id": "multiple_family", "name": "Multiple family dwelling", "permitted": True, "note": None}])
    x["follow_ups"] = dict(options["follow_ups"], X={"one_family_detached": [],
                                                     "multiple_family": ["dwelling_units", "rooms_let_for_profit",
                                                                         "conversion"]})
    x["implied"] = dict(options["implied"], X={"one_family_detached": {}, "multiple_family": {}})

    def typed(dialog, found, seen):
        boxes = seen["texts"]
        if boxes:
            boxes[-1].Text = "lots"            # the last text field laid out: rooms let for profit
        seen["after_typing"] = [c.Text for c in controls(dialog) if isinstance(c, ef.Label)]

    _, seen = open_box(g, doc, x, {"zone": "X", "use": "multiple_family"}, typed)
    log["3"] = seen
    asked = [t for t in seen["labels"] if t in [g.logic.STATED_FACTS[k][0] for k in ("dwelling_units",
                                                                                     "rooms_let_for_profit",
                                                                                     "conversion")]]
    claim("3 three questions after Use, the conversion dropdown in its own words, 'lots' said at once as not kept",
          len(asked) == 3 and [g.logic.NOT_ANSWERED, "New construction", "Conversion of an existing building"]
          in seen["drops"] and any("Not kept: a whole number" in t for t in seen.get("after_typing") or []),
          seen)

    def other_use(dialog, found, seen):
        use = next(c for c in found if isinstance(c, ef.DropDown) and "Multiple family dwelling" in drop_items(c))
        use.SelectedIndex = drop_items(use).index("One-family dwelling, detached")

    what, seen = open_box(g, doc, x, {"zone": "X", "use": "multiple_family"}, other_use)
    log["4"] = {"returned": what}
    claim("4 another use with other questions: the box closes to open again with them", what == "pick:refresh", what)
    _, seen = open_box(g, doc, options, {"zone": "R-1b", "use": "two_family"})
    log["5"] = seen
    claim("5 a saved use R-1b doesn't list stays picked, and the box says its Use row won't comply",
          "Two-family dwelling" in seen["picked"] and any("isn't on R-1b's list of uses" in t for t in seen["labels"]),
          seen)
    boxes = {}
    for zone in options["zones"]:
        first = (options["district_uses"].get(zone) or [{}])[0].get("id")
        _, seen = open_box(g, doc, options, {"zone": zone, "use": first})
        boxes[zone] = dict(seen["box"], use=first, questions=len(g.logic.follow_up_keys(options, zone, first)))
    log["6"] = boxes
    claim("6 every district's box for its first use is under 900 px wide",
          bool(boxes) and all(0 < b["width"] <= 900 for b in boxes.values()), boxes)
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    log["passed"] = sum(c["ok"] for c in log["claims"].values())
    log["ok"] = bool(log["claims"]) and log["passed"] == len(log["claims"]) and "trace" not in log
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    if doc is not None:
        close(doc)
print("use_questions_in_rhino: %d of %d claims pass%s" % (log["passed"], len(log["claims"]),
                                                         "" if "trace" not in log else " (stopped: see trace)"))
assert log["ok"], [n for n, c in log["claims"].items() if not c["ok"]] or log.get("trace")
