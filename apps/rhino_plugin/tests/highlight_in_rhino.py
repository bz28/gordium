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


def capture(doc, view_name, name):
    view = doc.Views.Find(view_name, False)
    doc.Views.ActiveView = view
    if view_name == "Perspective":
        view.ActiveViewport.ZoomExtents()
    view.Redraw()
    view.CaptureToBitmap(System.Drawing.Size(1000, 640)).Save(S + "frames/" + name + ".png")


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
        floors = len(g._buildings(doc))                     # each floor of the starting house: its own red piece
        claim("red: from the wall to 8 ft from the lot line (over even if the line is 2 ft out)", len(red_b) == floors and
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
        top_vp = doc.Views.Find("Top", False).ActiveViewport
        doc.Views.ActiveView = doc.Views.Find("Top", False)
        model = g._model_on_screen(g.overlay(), top_vp)
        for labels_on in (False, True):
            taken = [g.logic.status_box(top_vp.Bounds.Width, g._status_rows(g.overlay(), False))] if labels_on else []
            status = list(taken)
            box = g._notice_box(g.overlay(), top_vp, taken)
            claim("1b the notice covers neither the model nor the status box (labels %s)" % ("on" if labels_on else "off"),
                  box is not None and not any(min(box[1] + box[3], a + c) > max(box[1], a) and
                                              min(box[2] + box[4], b + e) > max(box[2], b)
                                              for a, b, c, e in [(model[0], model[1], model[2] - model[0],
                                                                  model[3] - model[1])] + status),
                  {"notice": box[1:] if box else None, "model": model, "status": status})
        vp = doc.Views.Find("Top", False).ActiveViewport
        screen = lambda line: tuple((p.X, p.Y) for p in (vp.WorldToClient(line.From), vp.WorldToClient(line.To)))  # noqa
        obstacles = [screen(line) for line in g.overlay().plan_lines]
        taken, placed = [], []
        every = [(line, text) for line, text, _ in g.overlay().yard_dims] + \
            [(edge, text) for _, text, edge in g.overlay().edge_labels]
        for line, text in every:      # every label, in the order the screen draws them (yards, then edge lengths)
            left, top, w, _, rows = g.ui.label_box(vp, (line.From + line.To) / 2, text, 11, taken,
                                                   along=(line.From, line.To), obstacles=obstacles)
            h = 4 + g.ui.LINE_H * len(rows)                   # one line or two (name, then numbers)
            hits = [o for o in obstacles if g.logic.crosses(o, left, top, w, h)]
            others = [b for b in placed if left < b[0] + b[2] and b[0] < left + w and top < b[1] + b[3] and b[1] < top + h]
            placed.append((left, top, w, h))
            inside = 0 <= left and left + w <= vp.Bounds.Width and 0 <= top and top + h <= vp.Bounds.Height
            (ax, ay), (bx, by) = screen(line)                 # next to its own line: the gap between them
            near = min(((max(left - x, 0, x - left - w) ** 2 + max(top - y, 0, y - top - h) ** 2) ** 0.5)
                       for x, y in ((ax + (bx - ax) * k / 50, ay + (by - ay) * k / 50) for k in range(51)))
            log.setdefault("labels", []).append((text, round(left), round(top), len(hits), len(others), inside,
                                                 round(near, 1)))
            log.setdefault("label_rows", []).append(len(rows))
        claim("2 no label crosses a dimension, a lot edge or the house, nor covers another label",
              len(log["labels"]) >= 8 and all(n == 0 and m == 0 for *_, n, m, _, _ in log["labels"]) and
              len(obstacles) >= 4 + 4 + 4, {"labels": log["labels"], "lines": len(obstacles)})
        claim("2 every label next to its own line (within 12 px: beside it, or just past its end when it is short)",
              all(near <= 12 for *_, near in log["labels"]), log["labels"])
        claim("2 every label on screen", all(i for *_, i, _ in log["labels"]),
              {"labels": log["labels"], "view": (vp.Bounds.Width, vp.Bounds.Height)})
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
