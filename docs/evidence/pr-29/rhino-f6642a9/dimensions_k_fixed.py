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
   A complying yard's dimension neutral grey; every label shown clear of the status box, the house and the other
   labels (placed by logic.place_dimension: on its line, sliding along the wall to a clear spot).
2. Front: only the height's dimension (no yard dimension lies flat on the ground line), vertical, from the grade
   plane up the measured height, beside the house, coloured as the height row.
3. Zoomed out to the neighbourhood (the lot under 120 px): no dimension at all in Top.
4. Labels off: the dimensions stay, a complying yard's words go, the failing yard's words stay (logic rule).
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

S = os.path.join(tempfile.gettempdir(), "gordium_dimensions_fixed") + "/"
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
    """The dimensions the conduit draws in one view's redraw: [(from, to, colour argb)] (model points)."""
    calls = []
    real = g._dimension

    def spy(d, viewport, line, color):
        calls.append((line.From, line.To, color.ToArgb()))
        return real(d, viewport, line, color)
    view = doc.Views.Find(view_name, False)
    doc.Views.ActiveView = view
    g._dimension = spy
    try:
        view.Redraw()
        if capture:
            view.CaptureToBitmap(System.Drawing.Size(1000, 640)).Save(S + "frames/" + capture + ".png")
    finally:
        g._dimension = real
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
    status = g.logic.rect_quad(g.logic.status_box(vp.Bounds.Width, g._status_rows(o, False)))
    house = [[(q.X, q.Y) for q in (vp.WorldToClient(p) for p in ring)] for ring in o.footprint]
    labels = [(k, placed[1]) for k, placed in sorted(o.placed.items()) if placed[1] is not None]
    hits = [(k, j) for k, q in labels for j, r in labels if k < j and g.logic.shapes_hit(q, r)]
    log["placed"] = {k: (pl[0], [tuple(round(v) for v in p) for p in (pl[1] or [])], pl[2]) for k, pl in o.placed.items()}
    claim("1 every label shown sits on screen clear of the status box, the house and the other labels",
          len(labels) == len(o.yard_dims) and not hits and
          not any(g.logic.shapes_hit(q, status) or (house and g.logic.shapes_hit(q, house[0])) for _, q in labels),
          {"placed": log["placed"], "overlaps": hits})
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
    for n, (_, text, _) in enumerate(o.yard_dims):     # (the Rhino job: k is the scale, not a loop variable)
        line = o.placed[n][3]
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

    g.set_labels(False)
    drawn(g, doc, "Top", "4_top_labels_off")
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
