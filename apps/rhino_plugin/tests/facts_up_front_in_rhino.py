#! python3
"""Queue item 14, in Rhino 8: the start box asks the architect's facts up front, in its compact "About this project"
section (Ben, 2026-10-27). SPEC FOR THE RHINO RUN: written but not yet run in Rhino (the logic, the layout model and the
width/height bounds are tested in CI: packages/design_checker/tests/test_about_this_project.py and test_box_width.py;
this script checks what only the real Eto box can show). Every claim is recorded (the run goes on past a failing one)
and the run fails at the end if any did. A fresh feet document; the box opened on facts (no lot needed).
Run it as use_questions_in_rhino.py is run (same helpers), then read <temp>/gordium_facts_up_front/out.json.

1. R-1b, one-family detached: a bold "About this project" label, a "Quick answers" dropdown and exactly the questions
   that shape the envelope (Stream or inlet, South Hill Overlay), every dropdown on "Not answered" (index 0): nothing
   assumed. No household or home-business question is in the box (use details: deferred), and no distance field yet.
2. The box fits a laptop: the dialog is at most 900 px wide and 700 px tall (1366 x 768 less the window's chrome).
3. One click: the stream dropdown lists "Not answered", "No stream within 20 ft", "Stream or inlet within 20 ft";
   Quick answers lists "No stream, not in South Hill".
4. Picking that quick answer fills both dropdowns; the Quick answers dropdown returns to its hint.
5. Picking "Stream or inlet within 20 ft" closes the box to open it again ("pick:refresh"); the box that opens next, on
   the facts that pick saved, shows the "Distance to it (ft)" field.
6. Draw with the stream answered: state["answers"] holds it (No stream -> False), the rest None. Draw with none answered:
   answers_applied sends the checker no stream or overlay fact (those rows say "needs review").
7. Edit site... shows the saved answers on their words.
8. Every district's box for each of its uses stays at most 900 px wide and 700 px tall; an attached-building use asks
   "Homes in the attached building" as a one-click dropdown.
9. The panel: after a check on R-1b with nothing answered, the tree has a collapsed group "Use details — answer when you
   plan the interior" holding the household and home-business rows (each still amber "?"), the header line reads
   "... · N use details to answer" and the header state is not "complies"; the group is not expanded. Enter... on one
   of its rows asks its question (the existing flow) and, answered to fail, moves the row into "Does not comply".
Writes <temp>/gordium_facts_up_front/out.json; closes its document."""
import json
import os
import sys
import tempfile
import traceback

import Eto.Forms as ef
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_facts_up_front") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
log = {"claims": {}}
R1B = ["Unrelated people in one home", "Owner lives in the house", "Accessory dwelling unit", "Functional family unit",
       "Home business", "Stream or inlet", "South Hill Overlay"]
LAPTOP_W, LAPTOP_H = 900, 700


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


def walk(c, seen=None):
    """Every control under `c`, nested layouts too, each once (Eto's Children already lists a container's nested
    controls, so walking each child's again met a nested layout's controls once per level: three times in the demo 7
    Rhino run, 2026-10-28)."""
    seen = set() if seen is None else seen
    key = System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(c)   # the .NET object (a new wrapper each read)
    if key in seen:
        return
    seen.add(key)
    yield c
    kids = getattr(c, "Children", None)
    if kids is not None:
        for k in list(kids):
            yield from walk(k, seen)
    content = getattr(c, "Content", None)
    if content is not None and content is not c:
        yield from walk(content, seen)


def drop_items(d):
    return [d.Items[i].Text for i in range(d.Items.Count)]


def selected(d):
    return d.Items[d.SelectedIndex].Text if d.SelectedIndex >= 0 else None


def drop_with(found, item):
    return next((c for c in found if isinstance(c, ef.DropDown) and item in drop_items(c)), None)


def open_box(g, doc, options, facts, act=None, mode="start", ready=False):
    """The real start box on these facts; `act(dialog, found, seen)` runs once it is shown (the box then closes by
    itself unless `act` closed it). Returns (what the box returned, what was seen, the state the box kept). `ready`:
    the district confirmed and a lot there, as the architect has them before Draw (Draw is off until then: #32, #49).
    It stands in for them: 6a / 6b test which answers Draw keeps, not Draw's gating (CI: test_lookup_box.py)."""
    seen = {}
    state = g._box_state(doc, dict(facts, jurisdiction=g.JURISDICTION), options, {}, mode)
    if ready:
        state.update(district_confirmed=True, lot_missing=False)

    def shown(dialog):
        found = list(walk(dialog.Content))
        seen["labels"] = [c.Text for c in found if isinstance(c, ef.Label)]
        seen["drops"] = [drop_items(c) for c in found if isinstance(c, ef.DropDown)]
        seen["picked"] = [selected(c) for c in found if isinstance(c, ef.DropDown)]
        seen["box"] = {"width": int(dialog.Width), "height": int(dialog.Height)}
        if act is not None:
            act(dialog, found, seen)
        if dialog.Visible:
            timer = ef.UITimer()
            timer.Interval = 0.3
            timer.Elapsed += g.logic.guard(lambda s, e: (timer.Stop(), dialog.Close(False)), "close the box")
            timer.Start()

    state["_on_shown"] = shown
    what = g.ui.start_box(state, options, mode)
    return what, seen, state


def click_draw(found):
    next(c for c in found if isinstance(c, ef.Button) and c.Text in ("Draw", "Check")).PerformClick()


doc = None
try:
    g = fresh_module()
    doc = TestDocs("facts_up_front").__enter__().open("Large Objects - Feet")
    options = g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})
    r1b = {"zone": "R-1b", "use": "one_family_detached"}
    not_answered = g.logic.NOT_ANSWERED
    envelope_qs = ["Stream or inlet", "South Hill Overlay"]
    later = ["Unrelated people in one home", "Owner lives in the house", "Accessory dwelling unit",
             "Functional family unit", "Home business", "Business floor area (sq ft)", "Distance to it (ft)"]
    _, seen, _ = open_box(g, doc, options, r1b)
    log["1"] = seen
    corner_words = g.logic.CORNER_CHOICES[1:]                   # Corner lot?'s own choices (it starts blank too)
    answer_drops = [(d, p) for d, p in zip(seen["drops"], seen["picked"])   # About's (not Corner lot?)
                    if d and d[0] == not_answered and d[1:] != corner_words]
    claim("1 'About this project' with Quick answers and exactly the two envelope questions, all on Not answered",
          seen["labels"].count("About this project") == 1 and "Quick answers" in seen["labels"]
          and all(t in seen["labels"] for t in envelope_qs) and not any(t in seen["labels"] for t in later)
          and len(answer_drops) == 2 and all(p == not_answered for _, p in answer_drops), seen)
    claim("2 the box is at most 900 x 700", 0 < seen["box"]["width"] <= LAPTOP_W and 0 < seen["box"]["height"] <= LAPTOP_H,
          seen["box"])
    stream = next((d for d in seen["drops"] if "No stream within 20 ft" in d), None)
    quick = next((d for d in seen["drops"] if "No stream, not in South Hill" in d), None)
    claim("3 one-click answers: the stream's two answers in words, and the quick answer listed",
          stream == [not_answered, "No stream within 20 ft", "Stream or inlet within 20 ft"] and quick is not None,
          {"stream": stream, "quick": quick})

    def quick_pick(dialog, found, seen):
        picker = drop_with(found, "No stream, not in South Hill")
        picker.SelectedIndex = drop_items(picker).index("No stream, not in South Hill")
        seen["after"] = {"stream": selected(drop_with(found, "No stream within 20 ft")),
                         "south": selected(drop_with(found, "In the South Hill Overlay")),
                         "picker": selected(picker)}

    _, seen, _ = open_box(g, doc, options, r1b, quick_pick)
    after = seen.get("after") or {}
    log["4"] = seen
    claim("4 the quick answer fills both dropdowns; Quick answers returns to its hint",
          after.get("stream") == "No stream within 20 ft" and after.get("south") == "Not in the South Hill Overlay"
          and after.get("picker") == g.logic.QUICK_HINT, after)

    def yes_stream(dialog, found, seen):
        d = drop_with(found, "Stream or inlet within 20 ft")
        d.SelectedIndex = drop_items(d).index("Stream or inlet within 20 ft")

    what, _, _ = open_box(g, doc, options, r1b, yes_stream)
    _, seen_s, _ = open_box(g, doc, options, dict(r1b, stream_near_lot=True))
    log["5"] = {"returned": what, "stream": seen_s["labels"]}
    claim("5 a yes closes the box to open again, with the distance question that waits on it",
          what == "pick:refresh" and "Distance to it (ft)" in seen_s["labels"], log["5"])

    def stream_no(dialog, found, seen):
        d = drop_with(found, "No stream within 20 ft")
        d.SelectedIndex = drop_items(d).index("No stream within 20 ft")
        click_draw(found)

    what, _, state = open_box(g, doc, options, r1b, stream_no, ready=True)
    got = {k: v for k, v in (state.get("answers") or {}).items() if k in ("stream_near_lot", "south_hill_overlay")}
    log["6a"] = {"returned": what, "answers": got}
    claim("6a Draw with the stream answered: it is kept, the other None",
          what == "draw" and got.get("stream_near_lot") is False and got.get("south_hill_overlay") is None, log["6a"])
    what, _, state = open_box(g, doc, options, r1b, lambda dialog, found, seen: click_draw(found), ready=True)
    facts, answered = g.logic.answers_applied({}, state.get("answers"), "R-1b", "one_family_detached", options)
    log["6b"] = {"returned": what, "facts": facts}
    claim("6b Draw with none answered: nothing is sent to the checker for them (their rows say needs review)",
          what == "draw" and answered == [] and "stream_near_lot" not in facts and "south_hill_overlay" not in facts,
          log["6b"])
    _, seen, _ = open_box(g, doc, options, dict(r1b, stream_near_lot=False), mode="edit")
    log["7"] = seen
    claim("7 Edit site... shows the saved answer on its words", "No stream within 20 ft" in seen["picked"], seen["picked"])
    boxes = {}
    for zone in options["zones"]:
        for use in [u["id"] for u in options["district_uses"].get(zone) or []]:
            _, seen, _ = open_box(g, doc, options, {"zone": zone, "use": use})
            boxes["%s/%s" % (zone, use)] = dict(seen["box"], homes="Homes in the attached building" in seen["labels"])
    log["8"] = boxes
    bad = {k: b for k, b in boxes.items() if not (0 < b["width"] <= LAPTOP_W and 0 < b["height"] <= LAPTOP_H)}
    attached = [b["homes"] for k, b in boxes.items() if k.endswith("/one_family_attached")]
    claim("8 every district's box for every use is at most 900 x 700; an attached building asks its homes",
          bool(boxes) and not bad and bool(attached) and all(attached), bad or attached)
    # 9 (the panel): see the spec above; to be driven by the Rhino run with GordiumStart on the sample lot, then Check,
    # reading the Gordium panel tree: group "use_details" collapsed, header summary, state not "complies".
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    log["passed"] = sum(c["ok"] for c in log["claims"].values())
    log["ok"] = bool(log["claims"]) and log["passed"] == len(log["claims"]) and "trace" not in log
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    if doc is not None:
        close(doc)
print("facts_up_front_in_rhino: %d of %d claims pass%s" % (log["passed"], len(log["claims"]),
                                                          "" if "trace" not in log else " (stopped: see trace)"))
assert log["ok"], [n for n, c in log["claims"].items() if not c["ok"]] or log.get("trace")
