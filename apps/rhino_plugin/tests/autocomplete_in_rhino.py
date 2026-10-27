#! python3
"""Address type-ahead in the real start box (PR: address-autocomplete), in Rhino 8, each claim asserted. Run in
Rhino, not in CI; the logic is tested in CI (packages/design_checker/tests/test_autocomplete.py,
packages/site_lookup/tests/test_suggest.py). Stand-in addresses (site_lookup's tests: hand-written, never the
City's data) and recorded lookups: no live call. A fresh feet document, GordiumStart (the sample, 106 Ithaca Rd),
then Edit site… with a script driving the box (typing is setting the address field's text, as a key does):
1. "106" typed: no list after 1 s (fewer than 4 characters). When the list shows, the box grows by its height
   (Cancel and Check stay in it) and stays on screen.
2. "106 Itha", typed a character at a time 0.05 s apart: ONE request after the pause (not one per key), and within
   3 s the list under the address shows "106 Ithaca Rd, Ithaca, NY"; the list is the box's own (a ListBox).
3. Picking it (the list's own pick: what Enter or a click does): the address field says "106 Ithaca Rd, Ithaca,
   NY", the list closes, and no new request is made for the picked text. The list, as Rhino lays it out (measured
   from its table), shows its one row, and eight for "200 ", with no scroll bar and no empty row.
4. A stale answer: the stand-in slowed to 1.5 s; "96 Itha" typed, then 0.5 s later "1060 Ith": the first request is
   stopped (its process gone) and the list shows 1060's address. Then an answer that lands for something no longer
   typed: "96 Itha" asked, new requests held back, "96 Ithac" typed: when 96 Itha's answer comes it is dropped (no
   list); let go, "96 Ithac"'s own answer shows 96's address.
5. Offline: the stand-in unreachable; "96 Itha": no list, the quiet note "Suggestions unavailable: type the full
   address and press Look up."; the box still works (Look up still on).
6. "96 Ithaca Rd" (no town) and Look up: the lookup is asked for "96 Ithaca Rd, Ithaca, NY".
7. A lookup that finds no lot (the recorded "12345 Nowhere Blvd, Ithaca, NY 14850", which the State geocoder
   doesn't know): the box says "No City of Ithaca address found …" and "The lot shown is still 106 Ithaca Rd's:
   nothing in the model changed."; the model unchanged. Then the box is closed (Cancel).
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
sys.modules.pop("rhino_logic", None)   # this checkout's copy, never one a Rhino that loaded another head has cached
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


REDRAWN = "Gordium::Envelope"   # what each check redraws with new ids (#34's snap curves): never the model's own


def objects(doc):
    """The model's objects by id and layer, without what every check redraws (REDRAWN): counting those, "the model
    unchanged" failed on a check with nothing changed (demo 2c0a5c0 run)."""
    out = {}
    for o in doc.Objects:
        path = doc.Layers[o.Attributes.LayerIndex].FullPath
        if path != REDRAWN and not path.startswith(REDRAWN + "::"):
            out[str(o.Id)] = path
    return out


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


def laid_out(listbox):
    """The list as Rhino (Mac) lays it out: the table's height, the scroll view's visible height, the row pitch;
    None where it can't be read (not the Mac's table)."""
    try:
        table = listbox.ControlObject      # Eto.macOS: the NSTableView itself
        scroll = table.EnclosingScrollView
        num = sys.modules["gordium_ui"].native_number          # (Mac native numbers: as the plugin reads them)
        rows = int(num(table.RowCount))
        rect = sys.modules["gordium_ui"].row_rect          # (Rhino's Mac name: RectForRow(IntPtr))
        last = rect(table, rows - 1) if rows else None      # where the last row is laid out (painted)
        return {"visible_h": num(scroll.ContentSize.Height), "rows": rows,
                "rows_bottom": (num(last.Y) + num(last.Height)) if last is not None else 0.0,
                "spacing": num(table.IntercellSpacing.Height), "row_h": num(rect(table, 0).Height),
                "pitch": (num(rect(table, 1).Y) - num(rect(table, 0).Y)) if rows >= 2 else
                         (num(rect(table, 0).Height) + num(table.IntercellSpacing.Height) if rows else 0.0),
                "painted": painted(scroll)}
    except Exception:
        return None


def painted(view):
    """What is drawn, read from pixels (not from the table's numbers, which are what Gordium sizes from): the view
    rendered to a bitmap, scanned from the bottom up for the lowest pixel row that differs from the background
    (text). Returns the view's height and that ink's bottom, in points; or the error, so the claim fails rather
    than passes when it can't look."""
    try:
        num = sys.modules["gordium_ui"].native_number
        bounds = view.Bounds
        rep = view.BitmapImageRepForCachingDisplayInRect(bounds)
        view.CacheDisplay(bounds, rep)
        wide, high = int(num(rep.PixelsWide)), int(num(rep.PixelsHigh))
        scale = high / max(num(bounds.Height), 1.0)

        def rgb(x, y):
            c = rep.ColorAt(System.IntPtr(int(x)), System.IntPtr(int(y)))  # Mac nint args are IntPtr
            try:
                return (num(c.RedComponent), num(c.GreenComponent), num(c.BlueComponent))
            except Exception:
                import AppKit
                c = c.UsingColorSpace(AppKit.NSColorSpace.DeviceRGB)
                return (num(c.RedComponent), num(c.GreenComponent), num(c.BlueComponent))

        inset = int(4 * scale)                               # off the border
        background = rgb(wide - inset, high - inset)
        xs = range(inset, int(wide * 0.6), max(1, wide // 80))   # where the address text runs
        for y in range(high - inset, inset, -1):             # bottom up: stop at the first row with ink
            if any(sum(abs(a - b) for a, b in zip(rgb(x, y), background)) > 0.3 for x in xs):
                return {"view_h": high / scale, "ink_bottom": (y + 1) / scale}
        return {"view_h": high / scale, "ink_bottom": None}
    except Exception as e:
        return {"error": repr(e)}


PAINTED_GAP_PT = 8.0      # most empty space allowed under the lowest drawn text (a fit leaves about 2-5 pt; half a
#                           16 pt row left empty under one row about 9.5-10.5 pt)


def fits(layout):
    """Every row visible (no scroll bar) and no empty row below them: the rows' own height against the visible
    height (the table itself is kept at least as tall as what shows it, so its frame can't tell)."""
    if not layout or layout["rows"] <= 0:
        return False
    rows_h = layout["rows_bottom"]      # the last row's bottom as laid out, not RowHeight
    ink = layout.get("painted") or {}
    if ink.get("ink_bottom") is None:   # couldn't see the pixels, or nothing drawn: not shown to fit
        return False
    # and as painted: under the lowest text only its own row's margin and the border (about 2-5 pt at Rhino's 16 pt
    # rows; the run logs it as "painted"); a fixed bound, not the table's pitch, since the pixels are what check the table's numbers
    return (rows_h <= layout["visible_h"] + 0.5 and layout["visible_h"] - rows_h < layout["pitch"] and
            ink["view_h"] - ink["ink_bottom"] < min(layout["pitch"], PAINTED_GAP_PT))


def screen_bottom(window):
    try:
        return int(window.Screen.WorkingArea.Bottom)
    except Exception:
        return None


def parts(dialog):
    import Eto.Forms as ef
    kids = list(dialog.Children)
    return {"address": next(c for c in kids if isinstance(c, ef.TextBox)),
            "list": next((c for c in kids if isinstance(c, ef.ListBox)), None),
            "labels": [c.Text for c in kids if isinstance(c, ef.Label)],
            "buttons": {c.Text: c for c in kids if isinstance(c, ef.Button)}}


def main():
    doc = None
    docs = None
    try:
        docs = TestDocs("autocomplete").__enter__()
        g = fresh_module()
        doc = docs.open("Large Objects - Feet")
        g.gordium_check()                                  # an empty file: the sample (106 Ithaca Rd) drawn
        g.live(False)
        g.STATE["auto_ok"] = False
        g.STATE["lookup_fixture"] = "96_ithaca_rd"
        model = objects(doc)
        asked, procs, hold = [], [], {"on": False}
        start = g._suggest_start

        def counted(text):
            asked.append([round(time.time(), 2), text, hold["on"]])
            if hold["on"]:                  # held back: the request already running is left to answer
                return None
            before = [p for p in procs if p.poll() is None]
            start(text)
            procs.append(g.STATE["suggest"]["proc"])
            log.setdefault("running_before", []).append([text, len(before),
                                                         sum(1 for p in before if p.poll() is None)])
            return None
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
                             "look_up_on": bool(p["buttons"].get("Look up") and p["buttons"]["Look up"].Enabled),
                             "list_height": int(p["list"].Height) if p["list"] is not None else None,
                             "box_width": int(d.Width), "layout": laid_out(p["list"]),
                             "box_height": int(d.Height), "box_bottom": int(d.Location.Y + d.Height),
                             "screen_bottom": screen_bottom(d)}
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
                    [(0.0, lambda d: setattr(parts(d)["address"], "Text", "200 ")), (2.5, note("2m"))] +
                    [(0.0, lambda d: g.STATE.update(suggest_slow=1.5))] +
                    typing("96 Itha", 0.0)[-1:] + [(0.5, lambda d: setattr(parts(d)["address"], "Text", "1060 Ith"))] +
                    [(3.5, note("4"))] +
                    [(0.0, lambda d: setattr(parts(d)["address"], "Text", "96 Itha")),
                     (0.6, lambda d: hold.update(on=True)),
                     (0.0, lambda d: setattr(parts(d)["address"], "Text", "96 Ithac")),
                     (3.5, note("4b")),
                     (0.0, lambda d: hold.update(on=False)),
                     (0.0, lambda d: setattr(parts(d)["address"], "Text", "96 Itha")),
                     (0.0, lambda d: setattr(parts(d)["address"], "Text", "96 Ithac")),
                     (3.5, note("4c"))] +
                    [(0.0, lambda d: g.STATE.update(suggest_slow=0, suggest_offline=True))] +
                    [(0.0, lambda d: setattr(parts(d)["address"], "Text", "96 Itha")), (2.0, note("5"))] +
                    [(0.0, lambda d: g.STATE.update(suggest_offline=False)),
                     (0.0, lambda d: setattr(parts(d)["address"], "Text", "96 Ithaca Rd")),
                     (0.5, lambda d: parts(d)["buttons"]["Look up"].PerformClick())]).run(dialog)
            elif n == 2:                                   # looking up 96: the query asked
                seen["6"] = {"query": (g.STATE.get("lookup") or {}).get("query")}
            elif n == 3:                                   # 96's answer in: now a lookup that finds nothing
                seen["6"]["labels"] = parts(dialog)["labels"]       # (what the box says of 96's answer)
                Script([(0.0, lambda d: g.STATE.update(lookup_fixture="not_found")),
                        (0.2, lambda d: setattr(parts(d)["address"], "Text", "12345 Nowhere Blvd, Ithaca, NY 14850")),
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
        # as Rhino lays it out (measured, not the height Gordium set): one row, and eight ("200 " on ten streets)
        many = seen.get("2m", {})
        claim("2 the list is as tall as its rows, laid out and painted: one row and eight, no scroll bar, no empty row",
              fits(two.get("layout")) and two["layout"]["rows"] == 1 and fits(many.get("layout")) and
              many["layout"]["rows"] == 8, {"one": two.get("layout"), "eight": many.get("layout")})
        claim("2 typed a character at a time: one request after the pause, the list shows 106's address",
              two.get("asked") == 1 and two.get("visible") and two.get("items") == ["106 Ithaca Rd, Ithaca, NY"],
              {"seen": two, "asked": asked})
        claim("3 picked: the address field says it, the list closed, no new request",
              three.get("address") == "106 Ithaca Rd, Ithaca, NY" and not three.get("visible") and
              three.get("asked") == two.get("asked"), three)
        four = seen.get("4", {})
        # when 1060 Ith was asked: one request (96 Itha's, still waiting on its 1.5 s) was running before, none after
        stopped = [r for r in log.get("running_before", []) if r[0] == "1060 Ith"]
        claim("4 the earlier request was stopped when the newer typing was asked for", stopped == [["1060 Ith", 1, 0]],
              {"running_before": log.get("running_before"), "asked": asked})
        claim("4 the newer typing's list: 1060's address", four.get("visible") and
              four.get("items") == ["1060 Ithaca Rd, Ithaca, NY"], four)
        claim("4 an answer for something no longer typed is dropped (no list for 96 Itha under 96 Ithac)",
              not seen.get("4b", {}).get("visible") and seen.get("4b", {}).get("address") == "96 Ithac",
              seen.get("4b"))
        claim("4 then 96 Ithac's own answer shows 96's address",
              seen.get("4c", {}).get("items") == ["96 Ithaca Rd, Ithaca, NY"], seen.get("4c"))
        five = seen.get("5", {})
        claim("5 offline: no list, the quiet note, Look up still on",
              not five.get("visible") and logic.SUGGESTIONS_UNAVAILABLE in five.get("labels", []) and
              five.get("look_up_on"), five)
        claim("6 no town typed: the lookup asked for 96 Ithaca Rd, Ithaca, NY, and found it (its lot shown dashed)",
              (seen.get("6") or {}).get("query") == "96 Ithaca Rd, Ithaca, NY" and
              any("Shown dashed: " in (t or "") and g.logic.same_address(
                  t.split("Shown dashed: ", 1)[1].split("'s lot", 1)[0], "96 Ithaca Rd, Ithaca, NY")
                  for t in (seen.get("6") or {}).get("labels", [])),
              seen.get("6"))
        seven = seen.get("7", {})
        claim("7 a lookup that found no lot: the box says so and that the lot shown is still 106's, the model "
              "unchanged",
              any("No City of Ithaca address found for 12345 Nowhere Blvd" in (t or "") and
                  "The lot shown is still 106 Ithaca Rd's: nothing in the model changed." in (t or "")
                  for t in seven.get("labels", [])) and objects(doc) == model, seven)
        claim("7 its long amber line wraps: the box stays box-sized (under 1,200 px wide)",
              0 < (seven.get("box_width") or 0) < 1200, {"box_width": seven.get("box_width")})
        labels = " | ".join(t or "" for t in seven.get("labels", []))
        claim("7 said once: what happened and what to do in one line, no second 'No lot found for …' line",
              labels.count("No City of Ithaca address found") == 1 and "No lot found for" not in labels, labels)
        claim("2 the box grows with the list so Cancel and Check stay in it, and it stays on screen",
              two.get("box_height", 0) >= one.get("box_height", 0) + two["layout"]["rows"] * two["layout"]["pitch"]
              if two.get("layout") else False, {"without": one.get("box_height"), "with": two.get("box_height")})
        claim("2 the grown box's bottom is on screen",
              two.get("screen_bottom") is not None and two.get("box_bottom", 10 ** 6) <= two["screen_bottom"],
              {"bottom": two.get("box_bottom"), "screen": two.get("screen_bottom")})
        log["ok"] = True
    except Exception:
        log["ok"] = False
        log["error"] = traceback.format_exc()
        raise
    finally:
        log["done"] = True                   # always: the run ended, passed or not ("ok" says which)
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
        for d in list(docs.opened if docs is not None else []):    # exactly the documents this run opened
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
