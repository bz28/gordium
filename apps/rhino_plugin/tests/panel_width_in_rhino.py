#! python3
"""The panel at a Rhino panel's width, in Rhino 8, each claim asserted (the run fails loudly otherwise). Run in
Rhino, not in CI. GordiumStart on the sample, the house moved 5 ft west (a failing yard: the longest Delta words),
then the panel made at 380 and 540 px with every group open. At each width, measured with the panel's own text
layout (gordium_ui.cell_text): every cell's text fits its cell, wrapped to at most two lines; the columns fit the
list; every row of buttons and ticks fits the panel. Phase "run" leaves the two windows open for a screenshot
("Gordium 380", "Gordium 540"); phase "close" (sc.sticky["gordium_width_phase"]) closes them and the document.
Writes <temp>/gordium_width/<phase>_out.json."""
import json
import os
import sys
import tempfile
import traceback

import Eto.Drawing as ed
import Eto.Forms as ef
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close, leftovers  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_width") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
phase = sc.sticky.pop("gordium_width_phase", "run")
log = {"phase": phase, "claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


def load():
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:
        loaded.off()
    state = sc.sticky.setdefault("gordium_state", {})
    state.clear()
    state.update({"repo": WT, "extra_paths": [], "auto_ok": True})
    for name in ("gordium_rhino", "rhino_logic", "gordium_ui"):
        sys.modules.pop(name, None)
    app = WT + "/apps/rhino_plugin"
    if app in sys.path:
        sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino
    return gordium_rhino


def controls(c):
    out = [c]
    for k in ("Content", "Controls"):
        v = getattr(c, k, None)
        if v is not None and not isinstance(v, str):
            try:
                for x in (v if hasattr(v, "__iter__") else [v]):
                    out += controls(x)
            except TypeError:
                out += controls(v)
    return out


try:
    if phase == "run":
        g = load()
        doc = TestDocs("width").__enter__().open("Large Objects - Feet")
        g.gordium_check()
        ft = 1.0 / g._scale(doc)
        for o in g._buildings(doc):
            doc.Objects.Transform(o.Id, rg.Transform.Translation(-5 * ft, 0, 0), True)
        g.run_check(doc, report=False)
        view = g.STATE["panel_parts"]["view"]
        forms = []
        for width in (380, 540):
            p = g.ui.make_panel(g._actions())
            p["form"].Title = "Gordium %d" % width
            p["form"].ClientSize = ed.Size(width, 760)
            p["form"].MinimumSize = ed.Size(width, 420)
            p["expanded"] = {"group:" + grp["key"]: True for grp in view["groups"]}
            g.ui.show(p, view)
            p["form"].Show()
            forms.append(p["form"])
            tree = p["tree"]
            Rhino.RhinoApp.Wait()                                  # let it lay out and paint once
            painted = p.get("painted") or {}
            log["w%d_painted" % width] = {str(k): v for k, v in painted.items()}
            # the widths the cells are drawn at (a child row's item is indented under its group's arrow)
            child = [painted.get((i, False)) for i in range(len(g.ui.COLUMNS))]
            group = [painted.get((i, True)) for i in range(len(g.ui.COLUMNS))]
            claim("%d: the cells were painted (widths read from the drawing)" % width,
                  all(w for w in child) and group[0], {"child": child, "group": group})
            item_width = child[0]
            too_big, shortened = [], []
            for grp in p["groups"]:
                rows = [grp] + [grp.Children[k] for k in range(grp.Children.Count)]
                for r in rows:
                    is_group = isinstance(r.Tag, str) and r.Tag.startswith("group:")
                    for i, w in enumerate(group if is_group else child):
                        if not w:
                            continue
                        text = str(r.Values[i] or "")
                        if not text:
                            continue
                        bold = isinstance(r.Tag, str) and r.Tag.startswith("group:")
                        shown = g.ui.fit_text(text, w, bold)          # what the cell draws
                        size = g.ui.cell_text(shown, w, bold).Measure()
                        if size.Height > g.ui.ROW_HEIGHT - 2 or size.Width > w - 2:
                            too_big.append((shown, i, round(w), round(size.Width), round(size.Height)))
                        if shown != text:
                            shortened.append((r.Tag, text))
            log["w%d" % width] = {"tree": tree.Width, "item": item_width, "shortened": [t for _, t in shortened],
                                  "rows": sum(1 + grp.Children.Count for grp in p["groups"])}
            claim("%d: no cell draws beyond itself (two lines at most)" % width,
                  log["w%d" % width]["rows"] >= 10 and not too_big and item_width >= 100, too_big[:6])
            missing = []
            for tag, text in shortened:                          # the whole text, in the selected item's detail
                p["selected"] = tag
                g.ui.show_detail(p)
                said = " ".join(getattr(c, "Text", "") or "" for c in controls(p["detail"]) if isinstance(c, ef.Label))
                if " ".join(text.split()) not in " ".join(said.split()):
                    missing.append(text)
            p["selected"] = None
            g.ui.show_detail(p)
            claim("%d: every shortened cell is whole in its item's detail" % width, not missing, missing)
            inner = p["form"].ClientSize.Width - 20                # the panel's padding
            wide = [(type(c).__name__, getattr(c, "Text", ""), round(c.GetPreferredSize().Width))
                    for c in controls(p["form"].Content) if isinstance(c, ef.StackLayout)
                    and c.GetPreferredSize().Width > inner]
            claim("%d: every row of buttons and ticks fits the panel" % width, not wide, wide)
            delta = [str(grp.Children[k].Values[3]) for grp in p["groups"] for k in range(grp.Children.Count)]
            log["w%d" % width]["deltas"] = sorted(set(d for d in delta if d))
        claim("the long Delta words are among them", "at least 1'-0\" short" in log["w380"]["deltas"],
              log["w380"]["deltas"])
        sc.sticky["gordium_width_forms"] = forms
        log["ok"] = all(c["ok"] for c in log["claims"].values())
    else:
        for f in sc.sticky.pop("gordium_width_forms", None) or []:
            f.Close()
        g = sys.modules.get("gordium_rhino")
        if g is not None:
            g.off()
        log["closed"] = [str(d.Path) for d in leftovers() if "width" in (d.Path or "") and close(d)]
except Exception:
    log["trace"] = traceback.format_exc()
    raise
finally:
    json.dump(log, open(S + phase + "_out.json", "w", encoding="utf-8"), default=str, indent=1)
