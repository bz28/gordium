#! python3
"""The docked panel's "Show neighbourhood" tick on #23 (2526115: the MVP panel merged), in Rhino 8, each claim
asserted. 106 Ithaca Rd looked up (recorded answers, its neighbourhood drawn); then, through the panel's own checkbox
(Checked set on the control, so its handler runs as a click's does, never the action called directly):
1. the panel is Rhino's docked panel; the tick is on a row of its own;
2. unticking hides every neighbourhood layer, ticking shows them again;
3. a rebuilt panel starts the tick as last set;
4. while a start box is open the tick is off (greyed), and a change to it then does nothing; after, it is back on;
5. the tick is kept in the file (the document's Gordium settings, like Show on-screen labels): a saved copy, read
   back, has it off after unticking.
Written by the Rhino job (9 of 9 at 2526115); claim 5 and the per-file reads added with the per-file tick.
Writes <temp>/gordium_context_tick/out.json; closes its document."""
import json
import os
import sys
import tempfile
import traceback

import Eto.Forms as ef
import Rhino
import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_context_tick") + "/"
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


def controls(c):
    out = [c]
    for attr in ("Items", "Rows", "Cells"):
        for x in list(getattr(c, attr, None) or []):
            inner = getattr(x, "Control", x)
            if inner is not None and inner is not c:
                out += controls(inner)
    content = getattr(c, "Content", None)
    if content is not None:
        out += controls(content)
    return out


def the_tick(parts):
    """The panel row holding the tick, and that row's own controls (a row is a horizontal StackLayout)."""
    for row in parts.get("greyed") or []:
        items = [it.Control for it in getattr(row, "Items", None) or []]
        if any(isinstance(c, ef.CheckBox) and c.Text == "Show neighbourhood" for c in items):
            return row, items
    return None, []


docs = TestDocs("contexttick").__enter__()
doc = None
try:
    g = fresh_module()
    doc = docs.open("Large Objects - Feet")
    g.STATE.update(box_picks=["lookup"], box_overrides={"address": "106 Ithaca Rd, Ithaca, NY 14850"},
                   lookup_fixture="106_ithaca_rd", on_confirm=lambda *a: None)
    g.gordium_check()
    parts = g.STATE.get("panel_parts") or {}
    layers = lambda: [doc.Layers[i].IsVisible for i in g._context_layer_indexes(doc)]  # noqa: E731
    log["layers_start"] = layers()
    row, boxes = the_tick(parts)
    claim("1 the panel is Rhino's docked panel", bool(getattr(parts.get("form"), "host", None)))
    claim("1 the tick is on a row of its own", row is not None and len(boxes) == 1,
          [getattr(b, "Text", type(b).__name__) for b in boxes])
    tick = boxes[0]
    claim("2 the neighbourhood is drawn and the tick starts on", log["layers_start"] and all(log["layers_start"]) and
          tick.Checked is True, log["layers_start"])
    tick.Checked = False                                 # a click on the panel: its handler runs
    log["after_off"] = layers()
    claim("2 unticking through the panel hides every neighbourhood layer", not any(log["after_off"]) and
          g.logic.context_shown(g._ui_state(doc)) is False, log["after_off"])
    path = S + "saved.3dm"
    doc.Export(path)
    saved = Rhino.FileIO.File3dm.Read(path)
    kept = json.loads(saved.Strings.GetValue(g.SECTION, g.UI_ENTRY) or "{}")
    log["saved_ui"] = {k: kept.get(k) for k in ("show_context", "show_labels")}
    claim("5 the tick is kept in the file: a saved copy has it off", kept.get("show_context") is False,
          log["saved_ui"])
    g.STATE.pop("panel_parts", None)                     # the panel rebuilt (as after a reload or a document switch)
    rebuilt = g.panel()
    _, again = the_tick(rebuilt)
    claim("3 a rebuilt panel starts the tick as last set (off)", again and again[0].Checked is False,
          [b.Checked for b in again])
    again[0].Checked = True
    log["after_on"] = layers()
    claim("2 ticking through the panel shows them again",
          all(log["after_on"]) and g.logic.context_shown(g._ui_state(doc)) is True, log["after_on"])
    inside = {}
    options = g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})

    def during(doc_, facts, text, state):            # the start box is open now
        p = g.STATE.get("panel_parts") or {}
        _, b = the_tick(p)
        inside["enabled"] = b[0].Enabled if b else None
        said = len(g.STATE.get("said") or [])
        b[0].Checked = False                         # a change while the box is open: gated, nothing happens
        inside["said"] = (g.STATE.get("said") or [])[said:]
        inside["layers"] = layers()
        b[0].Checked = True                          # put back (gated too)

    g.STATE["on_confirm"] = during
    g.confirm(doc, g.current_facts(doc), options, "check")
    log["inside"] = inside
    claim("4 while a start box is open the tick is off (greyed)", inside.get("enabled") is False, inside)
    claim("4 and a change to it then does nothing", all(inside.get("layers") or [False]) and
          inside.get("said") and g.logic.BOX_BUSY in inside["said"], inside)
    _, after = the_tick(g.STATE.get("panel_parts") or {})
    claim("4 after the box closes the tick is back on", after and after[0].Enabled is True and all(layers()),
          [b.Enabled for b in after])
    log["ok"] = True
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    if doc is not None:
        try:
            close(doc)
        except Exception:
            pass
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
