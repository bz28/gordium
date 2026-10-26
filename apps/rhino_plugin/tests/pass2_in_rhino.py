#! python3
"""The architect's review, pass 2 (2026-10-21): items 1-6, in Rhino 8, each claim asserted (the step fails loudly
otherwise). Run in Rhino, not in CI, one step per run (sc.sticky["gordium_pass2_step"]); a driver captures Rhino's
own windows by window id after each step (the step writes <temp>/gordium_pass2/ready.json). Steps, in order:
- "open": Rhino brought to the front; GordiumStart on the sample (106 Ithaca Rd, its lot from the tax map); its
  Street side reads "Ithaca Rd", the street the lookup found (not the address's, which is there too), sourced to
  the tax map.
- "side_yard" (1): the house moved toward a side lot line until that yard is 3'-0" short as drawn; the row's
  "To comply" says "whatever the survey shows" and gives the move under every reading, the as-drawn one after it.
- "apply_move" (1): every part of the house at least what it said from that side lot line ("keep every part of the
  building at least 12'-0" from the … side lot line as drawn (10'-0" required, …) — now 9'-0" at its closest"): the
  near side wall pulled in to it; that row complies and no other row is worse.
- "zoom" (3): Zoom to on that row selects its objects.
- "button" (2): the row waiting on stated facts (Parking): its "Enter …" button comes right after the reason, on
  screen without scrolling, and its words aren't repeated as text (with the merged measuring the one starting house
  is the main building, assumed, so "Pick the main building…" no longer comes up from a garage alone; the order is
  the same code for every button).
- "grey" (Ben): a rule not in Gordium yet, selected: its group reads "Not checked yet" and its detail "Not in Gordium
  yet — coming in a later version. Check this by hand for now: <section>".
- "labels" (4, 5): labels on, every view redrawn: the "Height limit" label is drawn at 13 pt; the status box is drawn
  in the active view only (and every view was drawn).
- "scale" (Ben, on #23): labels on, Top zoomed out to a 1,500 ft square round the lot: no plan label is drawn and the
  status box stays; zoomed back to the lot: every edge's length and the yards' labels are back, 106's short
  10'-4 1/8" edge with a leader to its label (nothing hidden at working zoom).
- "box" (6): a new empty file's start box (the real dialog): no "Use my survey…" or "Change…" button; it closes
  itself after 10 s and the file is closed.
- "close": closes the documents this run opened.
Writes <temp>/gordium_pass2/<step>.json (claims) and <step>_view.png (a viewport capture)."""
import json
import math
import os
import re
import sys
import tempfile
import time
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close, leftovers  # noqa: E402

OUT = os.path.join(tempfile.gettempdir(), "gordium_pass2") + "/"
os.makedirs(OUT, exist_ok=True)
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
step = sc.sticky.pop("gordium_pass2_step", "open")
A = sc.sticky.setdefault("gordium_pass2", {})
log = {"step": step, "claims": {}}
ready = {}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


def feet(text):
    """4'-11 3/8" -> 4.921875."""
    ft, inch, frac = re.fullmatch(r"(\d+)'-(\d+)(?: (\d+/\d+))?\"", text).groups()
    num, den = (frac or "0/1").split("/")
    return int(ft) + (int(inch) + int(num) / int(den)) / 12


def module():
    if step == "open":
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


def the_doc():
    return next((d for d in Rhino.RhinoDoc.OpenDocuments() if d.RuntimeSerialNumber == A.get("serial")), None)


def items(g):
    return {i["name"]: i for i in g.STATE["panel_parts"]["view"]["items"]}


def select(g, item):
    p = g.STATE["panel_parts"]
    p["selected"] = item["id"]
    g.ui.show(p, p["view"])
    Rhino.RhinoApp.Wait()


def quiet(g, most=20.0):
    """Until no re-check is pending or running: an edit marks the model changed and the live re-check follows on
    Rhino's idle (IDLE_SECONDS later); a claim read while it runs sees a frame in between (no view drawn, the last
    check's labels)."""
    end = time.time() + most
    while time.time() < end:
        Rhino.RhinoApp.Wait()
        if not g.STATE.get("dirty") and not g.STATE.get("running"):
            break
        time.sleep(0.1)
    Rhino.RhinoApp.Wait()


def move_house(g, doc, vector):
    xform = rg.Transform.Translation(vector)
    for o in g._buildings(doc):
        doc.Objects.Transform(o.Id, xform, True)
    quiet(g)
    g.run_check(doc, report=False)
    quiet(g)


def pull_wall(g, doc, out, gap):
    """The house's wall nearest a lot line pulled back `gap` ft along `out` (away from that line), its far side kept:
    the house scaled along `out` only, anchored at its far side: every part at least the target from that line.
    With out None, the last pull undone."""
    if out is None:
        plane, s = A.pop("pull")
        plane = rg.Plane(rg.Point3d(*plane[0]), rg.Vector3d(*plane[1]), rg.Vector3d(*plane[2]))
        xform = rg.Transform.Scale(plane, 1.0 / s, 1.0, 1.0)
    else:
        box = rg.BoundingBox.Empty
        for o in g._buildings(doc):
            box.Union(o.Geometry.GetBoundingBox(True))
        corners = list(box.GetCorners())
        proj = [rg.Vector3d(q) * out for q in corners]
        far = corners[proj.index(max(proj))]
        side = rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, out)
        plane = rg.Plane(far, out, side)
        width = max(proj) - min(proj)
        s = (width - gap / g._scale(doc)) / width
        A["pull"] = ([far.X, far.Y, far.Z], [out.X, out.Y, out.Z], [side.X, side.Y, side.Z]), s
        xform = rg.Transform.Scale(plane, s, 1.0, 1.0)
    for o in g._buildings(doc):
        doc.Objects.Transform(o.Id, xform, True)
    quiet(g)
    g.run_check(doc, report=False)
    quiet(g)


def capture(doc, view_name, name, frame=True):
    view = doc.Views.Find(view_name, False)
    if frame:
        doc.Views.ActiveView = view
        box = doc.Objects.BoundingBox
        box.Inflate(box.Diagonal.Length * 0.12)
        view.ActiveViewport.ZoomBoundingBox(box)
    view.Redraw()
    Rhino.RhinoApp.Wait()
    view.CaptureToBitmap(System.Drawing.Size(1000, 640)).Save(OUT + name + "_view.png")


def labels_in(container):
    import Eto.Forms as ef
    return [c for c in container.Children if isinstance(c, ef.Label)]


try:
    import AppKit
    AppKit.NSApplication.SharedApplication.ActivateIgnoringOtherApps(True)   # as the architect works: in front
    g = module()
    doc = the_doc()
    if step != "open":
        quiet(g)                                         # the last step's re-check finished first
    if step == "open":
        A.clear()
        doc = TestDocs("pass2").open("Large Objects - Feet")
        A["serial"] = doc.RuntimeSerialNumber
        g.STATE["on_confirm"] = lambda *a: None
        g.gordium_check()
        for _ in range(20):
            Rhino.RhinoApp.Wait()
            time.sleep(0.1)
        log["surveyed"] = bool(g.current_facts(doc).get("lot_surveyed"))
        claim("0 the sample's lot is from the tax map", not log["surveyed"], log["surveyed"])
        options = g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})
        facts = dict(g.current_facts(doc))               # (the address kept: the name must not come from it)
        state = g._box_state(doc, facts, options, g._ui_state(doc), "check")
        claim("8 the address is there too", bool(state.get("address")), state.get("address"))
        street = next(r for r in g.logic.box_rows(state) if r["key"] == "street")
        log["street"] = {"text": street["text"], "source": state.get("street_source")}
        claim("8 the sample's Street side reads Ithaca Rd, from the lookup", street["text"] == "Ithaca Rd" and
              "tax map" in (state.get("street_source") or ""), log["street"])
    elif step == "side_yard":
        side = next(i for n, i in items(g).items() if n.startswith("Side yard") and i.get("points"))
        a, b = (g._model_point(doc, q) for q in side["points"][:2])
        ring = g.STATE["start"]["floors"][0]["outline"]
        mid = g._model_point(doc, (sum(q[0] for q in ring) / len(ring), sum(q[1] for q in ring) / len(ring)))
        wall, line = (a, b) if a.DistanceTo(mid) < b.DistanceTo(mid) else (b, a)
        out = wall - line
        out.Unitize()                                   # away from that lot line
        ft = 1.0 / g._scale(doc)
        have, need = wall.DistanceTo(line) / ft, feet(side["required"].split(" ")[-1])
        move_house(g, doc, -out * ((have - need + 3.0) * ft))     # 3'-0" short as drawn
        now = items(g)[side["name"]]
        A.update(side=side["name"], out=[out.X, out.Y, out.Z], have=have, need=need)
        select(g, now)
        hint = now.get("hint") or ""
        m = re.fullmatch(r"To comply whatever the survey shows: keep every part of the building at least "
                         r"(\S+(?: \d/\d)?\") from the \w+ side lot line as drawn \((\S+(?: \d/\d)?\") required, the "
                         r"lot lines ±2'-0\"\) — now (\S+(?: \d/\d)?\") at its closest\.", hint)
        log["row"] = {"name": now["name"], "status": now["status"], "hint": hint, "reason": now.get("reason")}
        claim("1 on the tax map: every part at least the requirement plus the 2'-0\" margin, as drawn; now 3'-0\" short",
              m is not None and abs(feet(m.group(1)) - feet(m.group(2)) - 2.0) < 0.02 and
              abs(feet(m.group(2)) - feet(m.group(3)) - 3.0) < 0.02, log["row"])
        A["gap"] = feet(m.group(1)) - feet(m.group(3))     # that side wall pulled in to the target
        shown = [lab.Text for lab in labels_in(g.STATE["panel_parts"]["detail"])]
        claim("1 the panel shows it", hint in shown, shown[:12])
        capture(doc, "Top", "side_yard")
    elif step == "apply_move":
        before = {n: i["status"] for n, i in items(g).items()}
        pull_wall(g, doc, rg.Vector3d(*A["out"]), A["gap"])          # that side wall pulled back, the rest kept
        now = items(g)[A["side"]]
        select(g, now)
        log["row"] = {"name": now["name"], "status": now["status"], "reason": now.get("reason"), "delta": now.get("delta")}
        claim("1 doing exactly what it said: the row complies", now["status"] == "complies", log["row"])
        rank = {"does_not_comply": 0, "needs_review": 1, "complies": 2}
        worse = [(n, before[n], i["status"]) for n, i in items(g).items()
                 if n in before and before[n] in rank and i["status"] in rank and rank[i["status"]] < rank[before[n]]]
        claim("1 and no other row worse", not worse, worse)
    elif step == "zoom":
        now = items(g)[A["side"]]
        g.zoom_to(now)
        Rhino.RhinoApp.Wait()
        picked = [str(o.Id) for o in doc.Objects.GetSelectedObjects(False, False)]
        log["zoom"] = {"objects": now.get("objects"), "selected": picked}
        claim("3 Zoom to selects the row's objects", picked and set(picked) == {str(x) for x in now["objects"]}
              if now.get("objects") else False, log["zoom"])
        capture(doc, "Top", "zoom", frame=False)
    elif step == "button":
        pull_wall(g, doc, None, None)                    # the wall back where it was (the pull undone)
        row_ = next(i for i in g.STATE["panel_parts"]["view"]["items"] if i.get("needs"))   # waits on stated facts
        select(g, row_)
        import Eto.Forms as ef
        detail = g.STATE["panel_parts"]["detail"]
        kids = list(detail.Children)
        texts = [(type(c).__name__, getattr(c, "Text", None)) for c in kids]
        log["detail"] = texts[:30]
        words = g.logic.enter_words(row_["needs"]) + "…"
        log["row"] = {"name": row_["name"], "hint": row_.get("hint"), "button": words}
        b = next(k for k, c in enumerate(kids) if isinstance(c, ef.Button) and c.Text == words)
        reason = next(k for k, c in enumerate(kids) if isinstance(c, ef.Label) and c.Text == row_.get("reason"))
        between = [t for _, t in texts[reason + 1:b] if t]
        claim("2 the button comes right after the reason", reason < b and not between, {"reason": reason, "button": b,
                                                                                         "between": between})
        claim("2 its words aren't repeated as text", not any(isinstance(c, ef.Label) and
                                                             (c.Text or "").rstrip("…") == words.rstrip("…")
                                                             for c in kids), texts[:30])
        scroll = detail.Parent
        import Eto.Drawing as ed
        s0 = scroll.PointToScreen(ed.PointF(0, 0))
        b0 = kids[b].PointToScreen(ed.PointF(0, 0))
        log["screen"] = {"scroll_top": s0.Y, "scroll_height": scroll.Height, "button_top": b0.Y,
                         "button_height": kids[b].Height}
        claim("2 the button is on screen without scrolling", s0.Y <= b0.Y and b0.Y + kids[b].Height <= s0.Y + scroll.Height,
              log["screen"])
    elif step == "corner":
        lot = g._find(doc, g.current_facts(doc).get("lot_id") or "")
        segs = list(g._segments(lot.Geometry))
        street0 = [[list(p) for p in line] for line in g.current_facts(doc).get("street_line") or []]
        on_street = lambda s: any(all(abs(a - b) < 0.05 for a, b in zip(list(g._feet_point(doc, s[0])[:2]) +
                                  list(g._feet_point(doc, s[1])[:2]), line[0] + line[1])) or
                                  all(abs(a - b) < 0.05 for a, b in zip(list(g._feet_point(doc, s[0])[:2]) +
                                  list(g._feet_point(doc, s[1])[:2]), line[1] + line[0])) for line in street0)
        east = max((p for line in street0 for p in line), key=lambda p: p[0])     # Ithaca Rd's east end
        touches = lambda s: any(abs(g._feet_point(doc, q)[0] - east[0]) < 0.05 and
                                abs(g._feet_point(doc, q)[1] - east[1]) < 0.05 for q in s)
        first = next(s for s in segs if on_street(s))
        side = next(s for s in segs if not on_street(s) and touches(s))
        mids = [(s[0] + s[1]) / 2 for s in (first, side)]   # one Ithaca Rd piece, then the side street (Rhino job)
        clicks = [(Rhino.Commands.Result.Success, m) for m in mids] + [(Rhino.Commands.Result.Nothing, None)]
        prompts = []
        real = g._get_point

        def click(prompt):                              # the architect's clicks, then Enter
            prompts.append(prompt)
            return clicks.pop(0)

        facts = dict(g.current_facts(doc), corner_lot=True)
        ithaca = [[list(p) for p in line] for line in facts.get("street_line") or []]     # the sample's 8 pieces
        saved = dict(g._ui_state(doc))
        asked, real_ask = [], g._ask_street_more
        said = len(g.STATE.get("said") or [])
        g._get_point = click
        g._ask_street_more = lambda q: asked.append(q) or False    # the architect's No (see claim 10, third part)
        try:
            g._box_pick(doc, "street", facts, saved)
        finally:
            g._get_point = real
            g._ask_street_more = real_ask
        told = (g.STATE.get("said") or [])[said:]
        log["corner"] = {"prompts": prompts, "lines": facts.get("street_line"), "ids": facts.get("street_ids"),
                         "name": saved.get("street_name"), "said": told, "asked": asked}
        claim("10 a corner lot's street side takes every street clicked, Enter when done",
              prompts[0].startswith("Click each lot line on a street") and "(2 picked); Enter when done" in prompts[-1],
              log["corner"])

        def same(p, q):
            return all(abs(p[i][j] - q[i][j]) < 0.01 for i in (0, 1) for j in (0, 1))

        kept = facts.get("street_line") or []
        # demo 00c04f1: one click on one of Ithaca Rd's 8 tax-map pieces kept only that 9.8 ft piece (frontage
        # 9'-9 5/8"); the whole street is kept now, said, and the side street's own 3 pieces, never round a corner
        claim("10 one click on one piece keeps the whole street, and says so: Ithaca Rd's 8 pieces, 75'-10\"",
              len(ithaca) == 8 and all(any(same(p, q) or same(p, q[::-1]) for q in kept) for p in ithaca)
              and "Ithaca Rd: 8 lot-line pieces, 75'-10\" of frontage" in told, log["corner"])
        # the side street's far corner has a 0.24 ft piece in it, so it is never a sure corner (review round 7):
        # asked once, and No keeps the street to its own 2 pieces; Ithaca Rd's two corners are sure (not asked)
        claim("10 the other street is its own 2 pieces (91'-10 3/8\"), and neither runs round a corner",
              len(kept) == 10 and "Street 2: 2 lot-line pieces, 91'-10 3/8\" of frontage" in told and len(asked) == 1
              and asked[0].startswith("Past there the lot line turns 89° over short pieces, a corner or a bend")
              and facts.get("street_ids") == ["Ithaca Rd"] * 8 + [None] * 2, log["corner"])
        options = g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})
        state = dict(g._box_state(doc, facts, options, saved, "check"), corner_lot=False)   # the box: No
        after, after_ui = g._apply_box(doc, facts, state, saved)
        log["corner_no"] = {"street_line": after.get("street_line"), "corner_lot": after.get("corner_lot")}
        claim("12 answering No in the box drops both streets' lines (picked again: review round 5, P0)",
              not after.get("street_line") and after.get("corner_lot") is False, log["corner_no"])
    elif step == "grey":
        grey = next(i for i in g.STATE["panel_parts"]["view"]["items"] if i["group"] == "not_covered")
        p = g.STATE["panel_parts"]
        p["expanded"] = dict(p.get("expanded") or {}, not_covered=True)
        select(g, grey)
        shown = [lab.Text for lab in labels_in(p["detail"])]
        heads = [gr["title"] for gr in p["view"]["groups"]]
        want = "Not in Gordium yet — coming in a later version. Check this by hand for now: " + grey["detail"]["citation"]
        log["grey"] = {"groups": heads, "row": grey["name"], "detail": shown[:6]}
        claim("9 the rules not in Gordium yet are grouped as Not checked yet", "Not checked yet" in heads, heads)
        claim("9 the row says it's not in Gordium yet and which section to check by hand", want in shown, log["grey"])
        claim("9 its detail is headed Not checked yet", shown and shown[0].endswith(" · Not checked yet"), shown[:1])
    elif step == "labels":
        g._actions()["labels"](True)
        quiet(g)                                         # (turning labels on re-checks)
        o = g.overlay()
        calls, drawn = [], set()
        draw_box, here = g.ui.draw_text_box, g._here

        def record_box(d, rows, *rest):
            calls.append({"view": str(d.Viewport.Id), "rows": list(rows), "size": rest[-1]})
            return draw_box(d, rows, *rest)

        def record_here(o_, e):
            ok = here(o_, e)
            if ok:
                drawn.add(str(e.Viewport.Id))
            return ok

        persp = doc.Views.Find("Perspective", False)
        doc.Views.ActiveView = persp
        g.ui.draw_text_box, g._here = record_box, record_here
        try:
            for _ in range(20):                          # until every view has really drawn a frame
                for v in doc.Views:
                    v.Redraw()
                Rhino.RhinoApp.Wait()
                if len(drawn) >= 4:
                    break
                time.sleep(0.1)
        finally:
            g.ui.draw_text_box, g._here = draw_box, here
        limit = o.height_limit[1] if o.height_limit else None
        height = [c for c in calls if c["rows"] == [limit]]
        box_rows = [list(r) for r in [g._status_rows(o, g.stale(o))]][0]
        status = [c for c in calls if c["rows"] == box_rows]
        active = str(persp.ActiveViewportID)
        log["draws"] = {"views": sorted(drawn), "active": active, "height": height, "status_views": [c["view"] for c in status],
                        "status_rows": status[0]["rows"] if status else None}
        claim("4 the Height limit label is 13 pt", height and all(c["size"] == 13 for c in height), height)
        claim("5 every view was drawn", len(drawn) >= 4, sorted(drawn))
        claim("5 the status box once, in the active view", status and {c["view"] for c in status} == {active}, log["draws"])
        capture(doc, "Front", "labels_front", frame=False)
    elif step == "scale":
        g._actions()["labels"](True)
        quiet(g)                                         # (turning labels on re-checks)
        o = g.overlay()
        top = doc.Views.Find("Top", False)
        doc.Views.ActiveView = top
        ft = 1.0 / g._scale(doc)
        lot = rg.BoundingBox(o.lot_outline)
        c = lot.Center
        placed, boxes = [], []
        put, draw_box = g.ui.label_at, g.ui.draw_text_box
        rows = list(g._status_rows(o, g.stale(o)))

        leaders = []

        def record_label(d, viewport, point, text, *rest, **kw):
            placed.append(text)
            if kw.get("leader") and kw.get("along") is not None:   # an edge shorter than its label: led to it
                a, b = (viewport.WorldToClient(q) for q in kw["along"])
                if g.logic.needs_leader(((b.X - a.X) ** 2 + (b.Y - a.Y) ** 2) ** 0.5, g.logic.label_width(text, 11)):
                    leaders.append(text)
            return put(d, viewport, point, text, *rest, **kw)

        def record_box(d, rows_, *rest):
            boxes.append(list(rows_) == rows)
            return draw_box(d, rows_, *rest)

        frames = []
        here = g._here

        def record_here(o_, e):
            ok = here(o_, e)
            if ok and e.Viewport.Id == top.ActiveViewportID:
                frames.append(1)
            return ok

        def drawn(box, name):
            top.ActiveViewport.ZoomBoundingBox(box)
            quiet(g)
            del placed[:], boxes[:], frames[:], leaders[:]
            g.ui.label_at, g.ui.draw_text_box, g._here = record_label, record_box, record_here
            try:
                for _ in range(20):                      # until Top has really drawn a frame at this zoom
                    top.Redraw()
                    Rhino.RhinoApp.Wait()
                    if frames:
                        break
                    time.sleep(0.1)
            finally:
                g.ui.label_at, g.ui.draw_text_box, g._here = put, draw_box, here
            log.setdefault("frames", {})[name] = len(frames)
            view = top.CaptureToBitmap(System.Drawing.Size(1000, 640))
            view.Save(OUT + name + "_view.png")
            return list(placed), sum(boxes)

        half = 750 * ft                                  # the 1,500 ft square of #23's neighbourhood capture
        far = rg.BoundingBox(rg.Point3d(c.X - half, c.Y - half, 0), rg.Point3d(c.X + half, c.Y + half, 0))
        out_labels, out_box = drawn(far, "scale_neighbourhood")
        near = rg.BoundingBox(lot.Min, lot.Max)
        near.Inflate(lot.Diagonal.Length * 0.15)
        in_labels, in_box = drawn(near, "scale_lot")
        led = sorted(set(leaders))
        edges = sorted({t for _, t, _ in o.edge_labels})
        log["scale"] = {"neighbourhood": {"labels": out_labels, "status_box": out_box},
                        "lot": {"labels": in_labels, "status_box": in_box, "edges": edges, "led": led}}
        claim("7 zoomed out to the 1,500 ft square: no plan labels drawn", out_labels == [], log["scale"])
        claim("7 the status box stays", out_box >= 1 and in_box >= 1, dict(log["scale"], frames=log["frames"]))
        claim("7 zoomed to the lot: every edge's length is back, the yards' too", set(edges) <= set(in_labels)
              and len(set(in_labels) - set(edges)) >= 3, log["scale"])
        claim("7 106's short 10'-4 1/8\" edge keeps its length, led to it", "10'-4 1/8\"" in edges and
              "10'-4 1/8\"" in led, log["scale"])
    elif step == "box":
        A["box_serial"] = None
        empty = TestDocs("pass2box").open("Large Objects - Feet")
        A["box_serial"] = empty.RuntimeSerialNumber
        seen = {}

        def shown(dialog):
            import Eto.Forms as ef
            seen["buttons"] = [c.Text for c in dialog.Children if isinstance(c, ef.Button)]
            seen["labels"] = [c.Text for c in dialog.Children if isinstance(c, ef.Label)]
            seen["ticks"] = [c.Text for c in dialog.Children if isinstance(c, ef.CheckBox)]
            timer = ef.UITimer()
            timer.Interval = 10
            timer.Elapsed += g.logic.guard(lambda s, e: (timer.Stop(), dialog.Close(False)), "close the start box")
            timer.Start()
            json.dump({"title": dialog.Title, "at": time.time()}, open(OUT + "ready.json", "w", encoding="utf-8"))

        g.STATE["auto_ok"] = False
        g.STATE["on_box_shown"] = shown
        try:
            options = g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})
            g.confirm(empty, g.current_facts(empty), options, "start")
        finally:
            g.STATE.pop("on_box_shown", None)
            g.STATE["auto_ok"] = True
        log["box"] = seen
        claim("6 the box was shown with no lot", g.logic.NO_LOT in (seen.get("labels") or []), seen.get("labels"))
        claim("6 no Use my survey… or Change… until a lot exists",
              seen.get("buttons") and "Use my survey…" not in seen["buttons"] and "Change…" not in seen["buttons"],
              seen.get("buttons"))
        claim("11 the box says Front lot line (on the street), what it is, and This is the lot's district",
              "Front lot line (on the street)" in (seen.get("labels") or []) and
              g.logic.STREET_HELP in (seen.get("labels") or []) and "This is the lot's district" in (seen.get("ticks") or []),
              {"labels": seen.get("labels"), "ticks": seen.get("ticks")})
        ready["title"] = None                            # already written (the box is gone by now)
    elif step == "close":
        log["closed"] = [str(d.Path) for d in leftovers() if "pass2" in os.path.basename(d.Path or "") and close(d)]

        def servers():                                   # design_checker processes that are Rhino's children
            out = g.ui.spawn(["ps", "-A", "-o", "pid=,ppid=,command="], run=True, capture_output=True, text=True).stdout
            return [l.split(None, 2)[0] for l in out.splitlines() if len(l.split(None, 2)) == 3
                    and l.split(None, 2)[1] == str(os.getpid()) and "design_checker serve" in l]
        try:
            log["servers"] = {"after the runs": servers()}
            claim("13 after every step, exactly one checker process is Rhino's", len(log["servers"]["after the runs"]) == 1,
                  log["servers"])
        finally:
            g._stop_worker()                             # a test script leaves no server behind
            time.sleep(0.5)
        log["servers"]["after stopping"] = servers()
        claim("13 stopped when the script ends: none left", log["servers"]["after stopping"] == [], log["servers"])
    log["ok"] = True
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    if step == "box" and A.get("box_serial"):
        d = next((x for x in Rhino.RhinoDoc.OpenDocuments() if x.RuntimeSerialNumber == A["box_serial"]), None)
        log["box_closed"] = close(d)
    json.dump(log, open(OUT + step + ".json", "w", encoding="utf-8"), default=str, indent=1)
    if step != "box" or not os.path.exists(OUT + "ready.json"):
        json.dump({"title": None, "at": time.time(), "step": step}, open(OUT + "ready.json", "w", encoding="utf-8"))
