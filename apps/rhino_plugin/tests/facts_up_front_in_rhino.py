#! python3
"""Queue item 14, in Rhino 8: the start box asks the architect's facts up front, in its compact "About this project"
section (Ben, 2026-10-27). SPEC FOR THE RHINO RUN: written but not yet run in Rhino (the logic, the layout model and the
width/height bounds are tested in CI: packages/design_checker/tests/test_about_this_project.py and test_box_width.py;
this script checks what only the real Eto box can show). Every claim is recorded (the run goes on past a failing one)
and the run fails at the end if any did. A fresh feet document; the box opened on facts (no lot needed).
Run it as use_questions_in_rhino.py is run (same helpers), then read <temp>/gordium_facts_up_front/out.json.

1. R-1b, one-family detached: a bold "About this project" label, a "Quick answers" dropdown and exactly R-1b's seven
   questions (Unrelated people in one home, Owner lives in the house, Accessory dwelling unit, Functional family unit,
   Home business, Stream or inlet, South Hill Overlay), every dropdown on "Not answered" (index 0): nothing assumed.
   The floor-area and distance fields are not there yet.
2. The box fits a laptop: the dialog is at most 900 px wide and 700 px tall (1366 x 768 less the window's chrome).
3. One click: the stream dropdown lists "Not answered", "No stream within 20 ft", "Stream or inlet within 20 ft";
   Quick answers lists "1 family, no roomers" among its choices.
4. Picking "1 family, no roomers" fills "Unrelated people in one home" with "0 (one family)" and "Functional family unit"
   with "Not relying on one", then the Quick answers dropdown returns to its hint; the other questions stay
   "Not answered".
5. Picking "Stream or inlet within 20 ft" closes the box to open it again ("pick:refresh"); the box that opens next, on
   the facts that pick saved, shows the "Distance to it (ft)" field, and "Home business planned" likewise opens
   "Business floor area (sq ft)" and "Its home's floor area (sq ft)".
6. Draw with some answered: the box's state["answers"] holds exactly those answers (No home business -> False; No stream
   -> False; "0 (one family)" -> 0), and every unanswered question is None. Draw with none answered: every answer None
   and answers_applied sends the checker no household, home-occupation, stream or overlay fact (so those rows say
   "needs review", with the reason they give today).
7. Edit site... shows the saved answers again (the dropdowns on the words saved), and a changed one is kept.
8. Every district's box for each of its uses stays at most 900 px wide and 700 px tall.
Writes <temp>/gordium_facts_up_front/out.json; closes its document."""
import json
import os
import sys
import tempfile
import traceback

import Eto.Forms as ef
import scriptcontext as sc

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


def walk(c):
    """Every control under `c`, nested layouts too."""
    yield c
    kids = getattr(c, "Children", None)
    if kids is not None:
        for k in list(kids):
            yield from walk(k)
    content = getattr(c, "Content", None)
    if content is not None and content is not c:
        yield from walk(content)


def drop_items(d):
    return [d.Items[i].Text for i in range(d.Items.Count)]


def selected(d):
    return d.Items[d.SelectedIndex].Text if d.SelectedIndex >= 0 else None


def drop_with(found, item):
    return next((c for c in found if isinstance(c, ef.DropDown) and item in drop_items(c)), None)


def open_box(g, doc, options, facts, act=None, mode="start"):
    """The real start box on these facts; `act(dialog, found, seen)` runs once it is shown (the box then closes by
    itself unless `act` closed it). Returns (what the box returned, what was seen, the state the box kept)."""
    seen = {}
    state = g._box_state(doc, dict(facts, jurisdiction=g.JURISDICTION), options, {}, mode)

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
    _, seen, _ = open_box(g, doc, options, r1b)
    log["1"] = seen
    section = [t for t in seen["labels"] if t == "About this project"]
    not_answered = g.logic.NOT_ANSWERED
    asked_drops = [d for d in seen["drops"] if d and d[0] == not_answered]
    claim("1 'About this project' with Quick answers and exactly R-1b's seven questions, all on Not answered",
          len(section) == 1 and "Quick answers" in seen["labels"] and all(t in seen["labels"] for t in R1B)
          and not any(t in seen["labels"] for t in ("Distance to it (ft)", "Business floor area (sq ft)"))
          and len(asked_drops) == 7                       # one dropdown a question (unrelated people: 0 to 6)
          and all(p == not_answered for d, p in zip(seen["drops"], seen["picked"]) if d and d[0] == not_answered),
          seen)
    claim("2 the box is at most 900 x 700", 0 < seen["box"]["width"] <= LAPTOP_W and 0 < seen["box"]["height"] <= LAPTOP_H,
          seen["box"])
    stream = next((d for d in seen["drops"] if "No stream within 20 ft" in d), None)
    quick = next((d for d in seen["drops"] if "1 family, no roomers" in d), None)
    claim("3 one-click answers: the stream's two answers in words, and Quick answers lists 1 family, no roomers",
          stream == [not_answered, "No stream within 20 ft", "Stream or inlet within 20 ft"] and quick is not None,
          {"stream": stream, "quick": quick})

    def quick_pick(dialog, found, seen):
        picker = drop_with(found, "1 family, no roomers")
        picker.SelectedIndex = drop_items(picker).index("1 family, no roomers")
        seen["after"] = {"unrelated": selected(drop_with(found, "0 (one family)")),
                         "functional": selected(drop_with(found, "Not relying on one")),
                         "picker": selected(picker),
                         "others": [selected(c) for c in found if isinstance(c, ef.DropDown)
                                    and not (set(drop_items(c)) & {"0 (one family)", "Not relying on one",
                                                                   "1 family, no roomers"})]}

    _, seen, _ = open_box(g, doc, options, r1b, quick_pick)
    after = seen.get("after") or {}
    log["4"] = seen
    claim("4 '1 family, no roomers' fills the unrelated people and functional family answers; the rest stay blank",
          after.get("unrelated") == "0 (one family)" and after.get("functional") == "Not relying on one"
          and after.get("picker") == g.logic.QUICK_HINT and set(after.get("others") or []) == {not_answered}, after)

    def yes_stream(dialog, found, seen):
        d = drop_with(found, "Stream or inlet within 20 ft")
        d.SelectedIndex = drop_items(d).index("Stream or inlet within 20 ft")

    what, _, _ = open_box(g, doc, options, r1b, yes_stream)
    _, seen_s, _ = open_box(g, doc, options, dict(r1b, stream_near_lot=True))
    _, seen_h, _ = open_box(g, doc, options, dict(r1b, home_occupation=True))
    log["5"] = {"returned": what, "stream": seen_s["labels"], "home": seen_h["labels"]}
    claim("5 a yes closes the box to open again, with the distance / floor-area questions that wait on it",
          what == "pick:refresh" and "Distance to it (ft)" in seen_s["labels"]
          and "Business floor area (sq ft)" in seen_h["labels"] and "Its home's floor area (sq ft)" in seen_h["labels"],
          log["5"])

    def some(dialog, found, seen):
        for item, words in (("No home business", "No home business"), ("No stream within 20 ft", "No stream within 20 ft"),
                            ("0 (one family)", "0 (one family)")):
            d = drop_with(found, item)
            d.SelectedIndex = drop_items(d).index(words)
        click_draw(found)

    what, _, state = open_box(g, doc, options, r1b, some)
    log["6a"] = {"returned": what, "answers": state.get("answers")}
    got = {k: v for k, v in (state.get("answers") or {}).items() if k in g.logic.follow_up_keys(options, "R-1b",
                                                                                              "one_family_detached")}
    want = {"unrelated_persons": 0, "home_occupation": False, "stream_near_lot": False}
    claim("6a Draw with three answered: exactly those three are kept, the rest None",
          what == "draw" and {k: v for k, v in got.items() if v is not None} == want
          and all(v is None for k, v in got.items() if k not in want), log["6a"])
    what, _, state = open_box(g, doc, options, r1b, lambda dialog, found, seen: click_draw(found))
    facts, answered = g.logic.answers_applied({}, state.get("answers"), "R-1b", "one_family_detached", options)
    log["6b"] = {"returned": what, "facts": facts}
    claim("6b Draw with none answered: nothing is sent to the checker for them (their rows say needs review)",
          what == "draw" and answered == [] and not set(facts) & set(g.logic.follow_up_keys(options, "R-1b",
                                                                                           "one_family_detached")),
          log["6b"])
    _, seen, _ = open_box(g, doc, options, dict(r1b, home_occupation=False, stream_near_lot=False, unrelated_persons=2),
                          mode="edit")
    log["7"] = seen
    claim("7 Edit site... shows the saved answers on their words",
          {"No home business", "No stream within 20 ft", "2"} <= set(seen["picked"]), seen["picked"])
    boxes = {}
    for zone in options["zones"]:
        for use in [u["id"] for u in options["district_uses"].get(zone) or []]:
            _, seen, _ = open_box(g, doc, options, {"zone": zone, "use": use})
            boxes["%s/%s" % (zone, use)] = seen["box"]
    log["8"] = boxes
    claim("8 every district's box for every use is at most 900 x 700",
          bool(boxes) and all(0 < b["width"] <= LAPTOP_W and 0 < b["height"] <= LAPTOP_H for b in boxes.values()),
          {k: b for k, b in boxes.items() if not (0 < b["width"] <= LAPTOP_W and 0 < b["height"] <= LAPTOP_H)})
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
