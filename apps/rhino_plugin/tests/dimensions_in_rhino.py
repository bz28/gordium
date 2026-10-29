#! python3
"""Drawing-style dimensions (Ben, 2026-10-21), in Rhino 8, each claim asserted (the run fails loudly otherwise). Run
in Rhino, not in CI: the numbers are tested in CI (packages/design_checker/tests/test_dimensions.py); what only
Rhino can show is what the conduit draws in each view. A fresh feet document, GordiumStart on the sample (106 Ithaca
Rd), Show on-screen labels on, then the house moved 5 ft to the left (seen from the street): the left side yard
fails. What the screen draws is recorded by wrapping the plugin's own _dimension (each drawn dimension) while each
view redraws.
1. Top: one dimension per measured yard, each drawn with its dashed required line (two where the limit is read two
   ways), no two starting at the same point; the left side yard's red; its required line 10'-0" from the lot line;
   each yard's dimension square to the lot-line piece it ends on (within 0.1°).
   A complying yard's dimension neutral grey; each shows its number only, on its own line or just past its end
   (measured on screen), in view, clear of the status box, the house and the other numbers; "min" tags drawn only
   on failing or in-review yards.
2. Front: only the height's dimension (no yard dimension lies flat on the ground line), vertical, from the grade
   plane up the measured height, beside the house, coloured as the height row.
3. Zoomed out to the neighbourhood (the lot under 120 px): no dimension at all in Top.
4. Labels off: the dimensions stay, a complying yard's number goes, the failing yard's stays (logic rule).
Captures Top (labels on and off), Front, and Top zoomed out. Writes <temp>/gordium_dimensions/out.json and
frames/*.png; closes its document."""
import json
import math
import os
import sys
import tempfile
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_dimensions") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S + "frames", exist_ok=True)
log = {"claims": {}}


def claim(name, ok, detail=None):
    """Recorded, never stopping the run (the Rhino check of #28/#29 asked for every claim)."""
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


def drawn(g, doc, view_name, capture=None):
    """The dimensions the conduit draws in one view's redraw, on screen (plan) or in the model (any other view,
    depth-tested: draw_scene's _model_dimension; review of 9fa61de, F1): [(from, to, colour argb)] (model points)."""
    calls = []
    real, real_model = g._dimension, g._model_dimension

    def spy(d, viewport, line, color):
        calls.append((line.From, line.To, color.ToArgb()))
        return real(d, viewport, line, color)

    def spy_model(d, doc_, line, color):
        calls.append((line.From, line.To, color.ToArgb()))
        return real_model(d, doc_, line, color)
    view = doc.Views.Find(view_name, False)
    doc.Views.ActiveView = view
    g._dimension, g._model_dimension = spy, spy_model
    try:
        # on the Mac Redraw() only schedules a frame: a capture draws it (and asks for the labels), the labels are
        # placed (as once the view rests), then the settled frame is drawn by a second capture (the Rhino job at
        # e4e5018: as written nothing was drawn, so no label was asked for)
        view.Redraw()
        view.CaptureToBitmap(view.ActiveViewport.Size)
        g.settle_labels()
        del calls[:]
        view.Redraw()
        bitmap = view.CaptureToBitmap(view.ActiveViewport.Size)   # at the view's own size: the frame the claims read
        if capture:
            bitmap.Save(S + "frames/" + capture + ".png")
    finally:
        g._dimension, g._model_dimension = real, real_model
    return calls


doc = None
try:
    g = fresh_module()
    doc = TestDocs("dimensions").__enter__().open("Large Objects - Feet")
    g.gordium_check()                                    # GordiumStart's flow on the sample
    g.set_labels(True)
    k = 1.0 / g._scale(doc)
    for o in g._buildings(doc):
        doc.Objects.Transform(o.Id, rg.Transform.Translation(-5 * k, 0, 0), True)
    g.run_check(doc, report=False)
    items = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
    west = items["Side yard, Southwest"]
    claim("the left side yard does not comply", west["status"] == "does_not_comply", west)
    o = g.overlay()
    top = doc.Views.Find("Top", False)
    top.ActiveViewport.ZoomBoundingBox(o.box if o.box.IsValid else doc.Objects.BoundingBox)
    calls = drawn(g, doc, "Top", "1_top_labels_on")
    # (the panel's items carry no measure key: a yard is named "Front yard", "Side yard, …", "Rear yard")
    yards = [i for i in items.values() if i["name"].split(",")[0] in ("Front yard", "Side yard", "Rear yard")
             and i.get("points")]
    log["top"] = [(str(a), str(b), c) for a, b, c in calls]
    claim("1 Top: one dimension per measured yard", len(calls) == len(o.yard_dims) == len(yards) >= 4,
          {"drawn": len(calls), "dims": len(o.yard_dims), "yards": len(yards)})
    # what is drawn: the position each dimension took (o.placed: index, label, kind, the line, its required lines)
    drawn_lines = {k: placed[3] for k, placed in o.placed.items()}
    claim("1 every yard dimension drawn has its dashed required line (two where the limit is read two ways)",
          len(o.placed) == len(o.yard_dims) and all(placed[4] for placed in o.placed.values()),
          {k: len(placed[4]) for k, placed in o.placed.items()})
    starts = [(round(line.To.X, 4), round(line.To.Y, 4)) for line in drawn_lines.values()]
    claim("1 no two yard dimensions start at the same point", len(set(starts)) == len(starts), starts)
    red = g.ui.dim_color("does_not_comply", g.ui.viewport_dark()).ToArgb()
    claim("1 the failing side yard's dimension is red", any(c == red for _, _, c in calls), log["top"])
    grey = g.ui.dim_color("complies", g.ui.viewport_dark()).ToArgb()
    complying = [st for _, _, st in o.yard_dims if st == "complies"]
    claim("1 a complying yard's dimension is neutral grey (colour only what's wrong)",
          not complying or sum(c == grey for _, _, c in calls) == len(complying), log["top"])
    vp = top.ActiveViewport
    view = (vp.Bounds.Width, vp.Bounds.Height)
    meets = lambda a, b: a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]

    def frame(name="Top"):
        """What the view drew last (STATE["drawn"]: the one placer's own record): its labels as a list of
        (text, box, led, forced, line) (a list: two labels with the same words are two labels, review of 86c01ea,
        F2), the HARD boxes (status box, north arrow, notice), the buildings' shapes."""
        v = doc.Views.Find(name, False).ActiveViewport
        dr = g.STATE["drawn"][str(v.Id)]
        return ([(lb[0], tuple(lb[1][:4]), lb[4], lb[6], lb[3]) for lb in dr["labels"]], dr["hard_boxes"],
                dr["hard_shapes"], dr)
    every, hard, shapes, dr = frame()
    shown = {t: (box, led, forced, line) for t, box, led, forced, line in every}
    numbers = {pl[5]: k for k, pl in o.placed.items() if k != "height"}
    log["labels"] = [x[:4] for x in every]
    claim("1 every number and tag is placed by the one placer, none forced, clear of the status box, the house and "
          "each other (review of 86c01ea, F3: a forced one was let off)",
          every and all(not x[3] and not any(meets(x[1], tuple(h)) for h in hard)
                        and not any(g.logic.shapes_hit(g.logic.rect_quad(x[1]), sh) for sh in shapes)
                        and not any(meets(x[1], y[1]) for j, y in enumerate(every) if j != i)
                        for i, x in enumerate(every)), log["labels"])
    claim("1 every label lies wholly inside the view",
          all(0 <= x[1][0] and x[1][0] + x[1][2] <= view[0] and 0 <= x[1][1] and x[1][1] + x[1][3] <= view[1]
              for x in every), {"view": view})
    wrong_k = [j for j, (_, _, st) in enumerate(o.yard_dims) if st in ("does_not_comply", "needs_review")]
    claim("1 every failing or in-review yard's number is drawn (Rhino check at 6d2e01a: the failing one was missing)",
          wrong_k and all(o.placed[j][5] in shown for j in wrong_k), [o.placed[j][5] for j in wrong_k])
    import time as _time
    o.toast = (["Side yard (left) no longer complies: 3'-2\" short of 10'-0\""], _time.time() + 60)
    roomy = rg.BoundingBox(o.box.Min, o.box.Max)
    roomy.Inflate(o.box.Diagonal.Length * 0.6)           # a corner clear of the model, so the notice is drawn
    vp.ZoomBoundingBox(roomy)                             # (#15's rule: no clear corner, none drawn)
    drawn(g, doc, "Top", "1_top_notice")          # the notice showing, as after an edit (in the view worked in)
    every, hard, shapes, dr = frame()
    shown = {t: (box, led, forced, line) for t, box, led, forced, line in every}
    model = dr.get("model")
    note = dr.get("notice")
    log["notice"] = {"notice": note, "model": model}
    claim("1 the notice is drawn in this failing scene (a corner clear of the model)", note is not None, log["notice"])
    claim("1 the notice is never over the model, nor under any label (#15's rule: no clear corner, not drawn; "
          "the panel says it)",
          note is None or ((not model or not meets(tuple(note), (model[0], model[1], model[2] - model[0],
                                                                  model[3] - model[1])))
                           and not any(meets(tuple(note), x[1]) for x in every)), log["notice"])
    o.toast = None
    vp.ZoomBoundingBox(o.box if o.box.IsValid else doc.Objects.BoundingBox)
    shown_words = [t for t in shown if t in numbers]
    claim("1 each dimension shows its number only (no name, no 'needs', no '(approx.)': the panel says those)",
          shown_words and all("yard" not in t.lower() and "needs" not in t and "approx" not in t for t in shown_words),
          shown_words)
    claim("1 each number sits beside its own line, or is led to it (place_dim_label)",
          all(shown[t][1] or g.logic.box_gap(shown[t][3], shown[t][0]) <= 8 for t in shown_words),
          {t: (shown[t][1], round(g.logic.box_gap(shown[t][3], shown[t][0]), 1)) for t in shown_words})
    wrong = {j for j, (_, _, st) in enumerate(o.yard_dims) if st in ("does_not_comply", "needs_review")}
    wrong_tags = [t for j in wrong for t in o.yard_tags.get(j) or []]
    tags = [t for t in shown if t.startswith("min ")]
    claim("1 'min' tags drawn only for failing or in-review yards (every tag drawn is one of theirs)",
          all(t in wrong_tags for t in tags)
          and all((o.yard_tags.get(j) or []) == [] for j in range(len(o.yard_dims)) if j not in wrong), tags)
    for name in ("Top",):                                # Zoom Extents too: the lot and neighbourhood all in view
        vp.ZoomExtents()
        drawn(g, doc, name, "1b_top_zoom_extents")
        zl, _, _, _ = frame()
        claim("1 at Zoom Extents too, every label shown inside the view",
              all(0 <= x[1][0] and x[1][0] + x[1][2] <= vp.Bounds.Width and 0 <= x[1][1]
                  and x[1][1] + x[1][3] <= vp.Bounds.Height for x in zl), len(zl))
    vp.ZoomBoundingBox(o.box if o.box.IsValid else doc.Objects.BoundingBox)
    drawn(g, doc, "Top")
    ring = g.ask({"cmd": "sample_site"})["lot"]
    edges = [(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]

    def to_edge(p, e):
        (ax, ay), (bx, by) = e
        t = max(0.0, min(1.0, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)))
        return math.dist(p, (ax + t * (bx - ax), ay + t * (by - ay)))
    ft = lambda pt: (pt.X / k, pt.Y / k)                 # noqa: E731
    west = next(k for k, (_, text, _) in enumerate(o.yard_dims) if "Side yard, Southwest" in text)
    wline, req = o.placed[west][3], o.placed[west][4][0]
    mid = ft((req.From + req.To) / 2)
    left = min(edges, key=lambda e: min(to_edge(ft(wline.From), e), to_edge(ft(wline.To), e)))   # its lot line
    log["required_from_line_ft"] = round(to_edge(mid, left), 3)
    claim("1 the side yard's required line is 10'-0\" from its lot line", abs(to_edge(mid, left) - 10) <= 0.05,
          log["required_from_line_ft"])
    turns = []
    for j, (_, text, _) in enumerate(o.yard_dims):     # (j: k is the feet-to-model scale)
        line = o.placed[j][3]
        a, b = ft(line.From), ft(line.To)              # its lot end, then its building end
        e = min(edges, key=lambda e: to_edge(a, e))     # the lot-line piece its lot end lies on
        u = (b[0] - a[0], b[1] - a[1])
        v = (e[1][0] - e[0][0], e[1][1] - e[0][1])
        cos = abs(u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))
        turns.append((text, round(90 - math.degrees(math.acos(min(1.0, cos))), 2)))
    log["square"] = turns
    claim("1 each yard's dimension is square to the lot-line piece it ends on (within 0.1°)",
          all(abs(t) <= 0.1 for _, t in turns), turns)

    front = drawn(g, doc, "Front", "2_front")
    log["front"] = [(str(a), str(b), c) for a, b, c in front]
    h = o.height_dim
    claim("2 Front: only the height's dimension", len(front) == 1 and h is not None, log["front"])
    a, b = front[0][0], front[0][1]
    env = (g.STATE.get("last") or {}).get("envelope") or {}
    height = items["Building height"]
    claim("2 it is vertical, from the grade plane up", abs(a.X - b.X) < 1e-6 and abs(a.Y - b.Y) < 1e-6 and
          env.get("base") is not None and abs(a.Z / k - env["base"]) < 0.01 and b.Z > a.Z,
          {"from": str(a), "to": str(b), "base": env.get("base")})
    claim("2 it measures the height row's figure", g.logic.parse_feet(height["proposed"].lstrip("?✓✕ ")) is not None and
          abs((b.Z - a.Z) / k - g.logic.parse_feet(height["proposed"].lstrip("?✓✕ "))) < 0.1,
          {"dim_ft": (b.Z - a.Z) / k, "row": height["proposed"]})
    box = rg.BoundingBox.Empty
    for x in g._buildings(doc):
        box.Union(x.Geometry.GetBoundingBox(True))
    claim("2 it stands beside the house, not in it", a.X > box.Max.X and a.Y < box.Min.Y, str(a))
    claim("2 coloured as the height row", front[0][2] == g.ui.dim_color(height["status"], g.ui.viewport_dark()).ToArgb(),
          height["status"])
    fvp = doc.Views.Find("Front", False).ActiveViewport
    fl, _, _, _ = frame("Front")
    hq = next(((x[1],) for x in fl if o.placed.get("height") and x[0] == o.placed["height"][5]), None)
    corners = [fvp.WorldToClient(p) for p in o.house_box]
    hx = (min(q.X for q in corners), max(q.X for q in corners), min(q.Y for q in corners), max(q.Y for q in corners))
    claim("2 its number placed by the one placer, outside the house, inside the view (Rhino check at f6642a9: "
          "it sat inside the house)",
          hq is not None and 0 <= hq[0][0] and hq[0][0] + hq[0][2] <= fvp.Bounds.Width and 0 <= hq[0][1]
          and hq[0][1] + hq[0][3] <= fvp.Bounds.Height
          and not meets(hq[0], (hx[0], hx[2], hx[1] - hx[0], hx[3] - hx[2])),
          {"label": hq and hq[0], "house": hx})

    g.set_labels(False)
    vp.ZoomBoundingBox(o.box if o.box.IsValid else doc.Objects.BoundingBox)
    drawn(g, doc, "Top", "4_top_labels_off")
    off, _, _, _ = frame()
    failing_numbers = [o.placed[j][5] for j, (_, _, st) in enumerate(o.yard_dims) if st == "does_not_comply"]
    complying_numbers = [o.placed[j][5] for j, (_, _, st) in enumerate(o.yard_dims) if st == "complies"]
    texts = [x[0] for x in off]
    log["labels_off"] = [(x[0], x[1], round(g.logic.box_gap(x[4], x[1]), 1)) for x in off]
    claim("4 labels off: the failing yard's number still beside its yard (number only, within a label height or "
          "led), the complying yards' gone",
          failing_numbers and all(t in texts for t in failing_numbers)
          and all(x[2] or g.logic.box_gap(x[4], x[1]) <= 20 for x in off if x[0] in failing_numbers)
          and not any(t in texts for t in complying_numbers), log["labels_off"])
    claim("4 labels off: the failing yard's words stay, a complying yard's go",
          g.logic.yard_label_shown(False, "does_not_comply") and not g.logic.yard_label_shown(False, "complies"))
    top.ActiveViewport.ZoomBoundingBox(rg.BoundingBox(rg.Point3d(-3000 * k, -3000 * k, 0), rg.Point3d(3000 * k, 3000 * k, 0)))
    far = drawn(g, doc, "Top", "3_top_zoomed_out")
    claim("3 zoomed out to the neighbourhood: no dimension", far == [], len(far))
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    log["passed"] = sum(c["ok"] for c in log["claims"].values())
    log["ok"] = bool(log["claims"]) and log["passed"] == len(log["claims"]) and "trace" not in log
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    if doc is not None:
        close(doc)
print("dimensions_in_rhino: %d of %d claims pass%s" % (log["passed"], len(log["claims"]),
                                                      "" if "trace" not in log else " (stopped: see trace)"))
assert log["ok"], [n for n, c in log["claims"].items() if not c["ok"]] or log.get("trace")
