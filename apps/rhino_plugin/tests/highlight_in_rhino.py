#! python3
"""Red/amber highlighting in Rhino 8, each claim asserted (the run fails loudly otherwise). Run in Rhino, not in CI.
GordiumStart on the sample (106 Ithaca Rd's tax-map lot: lot lines ±2'-0"), then the house moved 5 ft to the left
(seen from the street), so that side yard is 7'-0 5/8" against the 10'-0" required. The lot line may really be up
to 2 ft either way:
- red: over under every reading, 10 - 2 - the yard wide (about 0.95 ft: worked from the measured yard);
- amber: the rest of the doubt, 4 ft wide (within 12 ft, less the red); anything amber past 12 ft is the rear
  yard's own (it needs review: its minimum moves with the lot depth's ±4'-0" too, review round 1);
- before the move nothing is coloured red (the start house complies); the colours drawn are the status colours.
Captures Top and Perspective. Writes <temp>/gordium_highlight/run_out.json and frames/*.png; phase "close"
(sc.sticky["gordium_highlight_phase"]) closes its document."""
import json
import os
import sys
import tempfile
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close, leftovers  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_highlight") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S + "frames", exist_ok=True)
phase = sc.sticky.pop("gordium_highlight_phase", "run")
log = {"phase": phase, "claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


def fresh_module():
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:                # its hooks, drawing and panel off before it is dropped
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


def draw_now(view):
    """The view's frame drawn now, at its own size: on the Mac Redraw() only schedules it, and a capture draws it,
    the plugin's drawing included (the Rhino job at 6361a3f: the draw record read right after Redraw() was empty)."""
    view.CaptureToBitmap(System.Drawing.Size(view.ActiveViewport.Bounds.Width, view.ActiveViewport.Bounds.Height))


def capture(doc, view_name, name):
    view = doc.Views.Find(view_name, False)
    doc.Views.ActiveView = view
    if view_name == "Perspective":
        view.ActiveViewport.ZoomExtents()
    view.Redraw()
    draw_now(view)
    size = System.Drawing.Size(view.ActiveViewport.Bounds.Width, view.ActiveViewport.Bounds.Height)   # as seen
    view.CaptureToBitmap(size).Save(S + "frames/" + name + ".png")


try:
    if phase == "run":
        g = fresh_module()
        doc = TestDocs("highlight").__enter__().open("Large Objects - Feet")
        g.gordium_check()                                    # GordiumStart's flow on the sample
        items = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
        claim("the sample is 106's tax-map lot, the left side yard 12'-0 5/8\" of 10'-0\"",
              items["Side yard, Southwest"]["proposed"] == "12'-0 5/8\"" and items["Side yard, Southwest"]["required"] == "10'-0\"",
              items["Side yard, Southwest"])
        claim("the start house: nothing red", not any(s == "does_not_comply" for _, s in g.overlay().encroach),
              [s for _, s in g.overlay().encroach])
        ft = 1.0 / g._scale(doc)
        for o in g._buildings(doc):
            doc.Objects.Transform(o.Id, rg.Transform.Translation(-5 * ft, 0, 0), True)
        g.run_check(doc, report=False)
        items = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
        west = items["Side yard, Southwest"]
        claim("moved: the left side yard 7'-0 5/8\", does not comply", west["proposed"] == "7'-0 5/8\"" and
              west["status"] == "does_not_comply", west)
        import math
        yard = math.dist(west["points"][0][:2], west["points"][-1][:2])   # the measured yard, feet
        log["yard_ft"] = round(yard, 4)
        regions = [(s, b.GetBoundingBox(True)) for b, s in g.overlay().encroach]
        log["regions"] = [(s, round((bb.Max.X - bb.Min.X) * g._scale(doc), 3)) for s, bb in regions]
        red = [bb for s, bb in regions if s == "does_not_comply"]
        amber = [bb for s, bb in regions if s == "needs_review"]
        width = lambda bb: (bb.Max.X - bb.Min.X) * g._scale(doc)        # noqa: E731  (feet)
        proud = 2 * g.ui.HIGHLIGHT_PROUD_FT                 # drawn a hair proud of the house on each side
        # each region measured from the lot's own left line (the real lot's is slightly slanted, so a region's x-width
        # is not its width): red is over even if the line is 2 ft out, so within 10 - 2 = 8 ft of it (and no nearer
        # than the wall); amber is the rest of the doubt, 8 to 12 ft from it. Allowing the 0.02 ft drawn proud.
        ring = g.ask({"cmd": "sample_site"})["lot"]
        edges = [(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]
        a_, b_ = min((e for e in edges if math.dist(e[0], e[1]) > 50), key=lambda e: e[0][0] + e[1][0])

        def to_line(p):                                     # feet from the left lot line (a segment, plan)
            ax, ay, bx, by = a_[0], a_[1], b_[0], b_[1]
            t = max(0.0, min(1.0, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)))
            return math.dist(p, (ax + t * (bx - ax), ay + t * (by - ay)))

        def dists(brep):
            return [to_line((v.Location.X * g._scale(doc), v.Location.Y * g._scale(doc))) for v in brep.Vertices]

        def span(brep):
            d = dists(brep)
            return round(min(d), 3), round(max(d), 3)
        red_b = [b for b, st in g.overlay().encroach if st == "does_not_comply"]
        amber_b = [b for b, st in g.overlay().encroach if st == "needs_review"]
        log["bands"] = {"yard": round(yard, 3), "red": [span(b) for b in red_b], "amber": [span(b) for b in amber_b]}
        e = 0.05                                            # proud by scaling about the box centre: a slanted corner moves a bit more
        claim("red: from the wall to 8 ft from the lot line (over even if the line is 2 ft out)", len(red_b) == 1 and
              all(yard - e <= lo and hi <= 8 + e and hi >= 8 - e for lo, hi in log["bands"]["red"]), log["bands"])
        corners = sorted(round(d, 3) for b in amber_b for d in dists(b))
        log["bands"]["amber_corners"] = corners
        claim("amber: from 8 ft from the lot line, beside the red, its side band to 12 ft", len(amber_b) >= 1 and
              all(8 - e <= lo for lo, hi in log["bands"]["amber"]) and
              any(abs(lo - 8) <= e for lo, hi in log["bands"]["amber"]) and
              any(abs(d - 12) <= e for d in corners), log["bands"])
        rows = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
        rear = rows.get("Rear yard") or {}
        claim("amber past 12 ft is the rear yard's own: it needs review, short under some reading",
              all(hi <= 12 + e for lo, hi in log["bands"]["amber"]) or
              (rear.get("status"), rear.get("colour")) == ("needs_review", "amber")
              and (rear.get("delta") or "").startswith("up to "), {"rear": rear, "bands": log["bands"]})
        claim("each colour from the result", [g.logic.highlight(s) for s in ("does_not_comply", "needs_review")] ==
              ["red", "amber"])
        # the architect's polish (2026-10-21), each as the screen has it
        hl = g.ui.HIGHLIGHT
        claim("3 saturated, distinct highlight colours (#D7263D, #F2A900)",
              (hl["red"].R, hl["red"].G, hl["red"].B, hl["amber"].R, hl["amber"].G, hl["amber"].B) ==
              (215, 38, 61, 242, 169, 0) and g.ui.HIGHLIGHT_EDGE["red"] > g.ui.HIGHLIGHT_EDGE["amber"])
        toast = (getattr(g.overlay(), "toast", None) or [[]])[0]
        claim("1 the notice says what holds however the lot lines lie: at least 0'-11 1/4\" short (the red part)",
              any(t.endswith("· at least 0'-11 1/4\" short") for t in toast), toast)
        cells = [[str(v) for v in grp.Children[k].Values] for grp in g.STATE["panel_parts"].get("groups") or []
                 for k in range(grp.Children.Count)]
        west_row = next(c for c in cells if "Side yard, Southwest" in c[0])
        claim("1 the panel's Delta says the same", west_row[3] == "at least 0'-11 1/4\" short", west_row)
        # what the Top view really drew (gordium_rhino.draw_screen keeps it in STATE["drawn"]): the claims read the
        # drawing's own placement, never a sum of their own (the Rhino job at 27c8e5d: a claim's own taken boxes
        # said "no corner clear" while the screen placed the notice correctly)
        top_view = doc.Views.Find("Top", False)
        doc.Views.ActiveView = top_view
        top_vp = top_view.ActiveViewport

        def what_drew(labels_on):
            g.set_labels(labels_on)
            g.STATE.get("drawn", {}).pop(str(top_vp.Id), None)          # never an earlier frame's record
            top_view.Redraw()
            draw_now(top_view)
            g.settle_labels()                         # the labels placed as when the view comes to rest (no idle
            g.STATE.get("drawn", {}).pop(str(top_vp.Id), None)          # in a script: the timer can't run)
            top_view.Redraw()
            draw_now(top_view)
            rec = g.STATE.get("drawn", {}).get(str(top_vp.Id))
            return rec if rec and rec.get("complete") and rec.get("settled") else None   # the whole, settled frame

        def over(box, other):                          # two (x, y, w, h) boxes overlap
            return min(box[0] + box[2], other[0] + other[2]) > max(box[0], other[0]) and \
                min(box[1] + box[3], other[1] + other[3]) > max(box[1], other[1])
        message = lambda: str(g.STATE["panel_parts"]["message"].Text) if g.STATE.get("panel_parts") else ""  # noqa
        held = ["✕ " + t for t in (getattr(g.overlay(), "toast", None) or [[]])[0]]
        for labels_on in (False, True):
            rec = what_drew(labels_on) or {}
            box, m = rec.get("notice"), rec.get("model")
            model_box = (m[0], m[1], m[2] - m[0], m[3] - m[1]) if m else None
            # not drawn only when the placement itself finds no corner for this frame (never just "said in the panel")
            room = bool(rec and held) and g.logic.notice_place(rec["size"][0], rec["size"][1], held, m,
                                                                rec.get("taken") or []) is not None
            claim("1b the notice covers neither the model nor the status box (labels %s): drawn clear of both when a "
                  "corner has room, else not drawn and said in the panel" % ("on" if labels_on else "off"),
                  bool(rec) and bool(held) and ((box is not None and not (model_box and over(box, model_box))
                                                 and not any(over(box, t) for t in rec.get("taken") or []))
                                                or (box is None and not room and "no longer complies" in message())),
                  {"notice": box, "room": room, "model": m, "taken": rec.get("taken"), "view": rec.get("size"),
                   "panel": message()})
        rec = what_drew(True)                          # every label on, as the architect turns them on
        lines = [tuple(map(tuple, s_)) for s_ in rec["lines"]]
        m = rec["model"]
        hard = [tuple(b_) for b_ in rec.get("hard_boxes") or []]   # the notice, status box, north arrow
        shapes = [[tuple(q) for q in shp] for shp in rec.get("hard_shapes") or []]   # buildings, coloured parts
        dims = [tuple(map(tuple, d_)) for d_ in rec.get("dims") or []]
        view = tuple(rec["size"])
        broken, forced, covered, too_far = [], [], [], []
        for k, (text, (left, top, w, h, want), nrows, own, led, size, was_forced, order) in enumerate(rec["labels"]):
            own = tuple(map(tuple, own))
            box = (left, top, w, h)
            why = g.logic.label_breaks_hard(own, box, view, hard, dims, shapes)   # every HARD rule
            if why:
                broken.append((text, why))
            if was_forced:
                forced.append(text)
            gap = g.logic.box_gap(own, box)
            # independently of the placement: is there a spot at full size within one label height of its line that
            # keeps every HARD rule (a 4 px search)? Then the label must be that near, at full size
            for rows in ([text], g.logic.label_lines(text)):
                rw = max(g.logic.label_width(r_, 11) for r_ in rows)
                rh = g.logic.label_height(len(rows), 11)
                (xa, ya), (xb, yb) = own
                others_ = [tuple(b_[1][:4]) for b_ in rec["labels"] if b_[7] < order]   # placed before it only
                near = any(g.logic.box_gap(own, (x_, y_, rw, rh)) <= rh - 6 and
                           all(not g.logic.label_breaks_hard(own, (x_ + dx, y_ + dy, rw, rh), view, hard, dims, shapes,
                                                             others_) for dx in (-3, 0, 3) for dy in (-3, 0, 3))
                           for y_ in range(int(min(ya, yb) - 2 * rh), int(max(ya, yb) + rh) + 1, 4)
                           for x_ in range(int(min(xa, xb) - rw - rh), int(max(xa, xb) + rh) + 1, 4))
                if near and (gap > rh or size < 11):
                    too_far.append((text, round(gap, 1), size, rows))
                    break
            others = [j for j, b_ in enumerate(rec["labels"]) if j != k and over(box, b_[1][:4])]
            if others:
                covered.append((text, others))
            log.setdefault("labels", []).append((text, round(left), round(top), round(gap, 1), bool(led), size,
                                                 why, bool(was_forced)))
        g.set_labels(False)
        # one set of rules (rhino_logic.place_dim_label; the Rhino job at 319dc5d): HARD never broken: on screen, over
        # no building or coloured part, nor the notice, the status box or the north arrow, on neither its own line nor
        # another yard's dimension; never forced here (the sample has room)
        claim("2 every label keeps every HARD rule: on screen, off every building and coloured part, the notice, the "
              "status box and the north arrow, off its own line and every other yard's dimension",
              len(log["labels"]) >= 8 and rec.get("buildings", 0) >= 1 and len(shapes) >= rec.get("buildings", 0)
              and not broken and not forced,
              {"broken": broken, "forced": forced, "buildings": rec.get("buildings"), "labels": log["labels"],
               "view": view})
        claim("2 a label is within one label height of its line at full size whenever a spot there keeps every HARD "
              "rule (an independent 4 px search), and led to its line whenever it is further than 8 px",
              not too_far and all(lab[4] == (lab[3] > 8) for lab in log["labels"]),
              {"too_far": too_far, "labels": log["labels"]})
        claim("2 no label covers another (a placed label is HARD for the later ones)", not covered,
              {"covered": covered})
        sources = ((g.STATE.get("last") or {}).get("header") or {}).get("sources") or []
        lot = [t for t in sources if t.startswith("Lot: ")]
        area = items["Lot area"]["proposed"]                    # the row's own figure: the fact must say the same
        claim("4 the lot's source said once, its size the Lot area row's", len(lot) == 1 and
              lot[0].count("tax map") == 1 and lot[0].startswith("Lot: " + area + " · the tax map (±2 ft, approximate) · "),
              {"fact": lot, "row": area})
        parts = g.STATE["panel_parts"]
        parts["selected"] = west["id"]
        g.ui.show_detail(parts)
        texts = []

        def walk(c):
            if hasattr(c, "Text") and isinstance(getattr(c, "Text", None), str):
                texts.append(c.Text)
            for k in ("Content", "Controls", "Children"):
                v = getattr(c, k, None)
                if v is None or isinstance(v, str):
                    continue
                try:
                    for x in (v if hasattr(v, "__iter__") else [v]):
                        walk(x)
                except TypeError:
                    walk(v)
        walk(parts["detail"])
        log["detail"] = texts[:20]
        claim("5 the selected yard's detail says what red and amber mean",
              any("red is the part over the yard line" in t and "certain" in t for t in texts), texts[:12])
        capture(doc, "Top", "4_red_amber_top")
        g.set_labels(True)
        capture(doc, "Top", "2_labels_on_off_every_line")
        g.set_labels(False)
        capture(doc, "Perspective", "4_red_amber_perspective")
        settings = Rhino.ApplicationSettings.AppearanceSettings
        light = settings.ViewportBackgroundColor
        try:                                                 # the same on a dark background, then put back
            settings.ViewportBackgroundColor = System.Drawing.Color.FromArgb(40, 42, 46)
            claim("3 dark background seen as dark", g.ui.viewport_dark())
            capture(doc, "Top", "4_red_amber_top_dark")
            capture(doc, "Perspective", "4_red_amber_perspective_dark")
        finally:
            settings.ViewportBackgroundColor = light
        claim("3 the background put back", settings.ViewportBackgroundColor.ToArgb() == light.ToArgb())
        log["ok"] = all(c["ok"] for c in log["claims"].values())
    else:
        log["closed"] = [str(d.Path) for d in leftovers() if "highlight" in (d.Path or "") and close(d)]
except Exception:
    log["trace"] = traceback.format_exc()
    raise
finally:
    json.dump(log, open(S + phase + "_out.json", "w", encoding="utf-8"), default=str, indent=1)
