#! python3
"""A row's own "Enter …" button, in Rhino 8, each claim asserted (the run fails loudly otherwise). Run in Rhino, not in
CI. The sample (no bedrooms or parking spaces stated): the Parking row's detail in the panel has one button, named
from exactly the facts that row waits for; clicking it (the button itself) asks exactly those, in order, a whole
number each; a skipped answer stays unset (never 0) and the row then waits only for the other, its button saying
so; answering that one checks the row. The command line's prompts are answered by stand-ins that record what was
asked (a script can't type at Rhino's prompt). Writes <temp>/gordium_needs/out.json; closes its document."""
import json
import os
import sys
import tempfile
import traceback

import Eto.Forms as ef
import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_needs") + "/"
os.makedirs(S, exist_ok=True)
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
log = {"claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


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


def buttons(c, out=None):
    out = [] if out is None else out
    if isinstance(c, ef.Button):
        out.append(c)
    for attr in ("Rows", "Items", "Cells"):
        for x in list(getattr(c, attr, None) or []):
            inner = getattr(x, "Control", None)
            if inner is not None:
                buttons(inner, out)
            for cell in list(getattr(x, "Cells", None) or []):
                if getattr(cell, "Control", None) is not None:
                    buttons(cell.Control, out)
    if getattr(c, "Content", None) is not None:
        buttons(c.Content, out)
    return out


def parking(g):
    return next(i for i in (g.STATE.get("last") or {}).get("items", []) if i.get("id") == "R-1b.parking_one_family")


def enter_button(g, item):
    parts = g.STATE["panel_parts"]
    parts["selected"] = item["id"]
    g.ui.show_detail(parts)
    found = {}
    for b in buttons(parts["detail"]):
        found.setdefault(b.Text, b)         # one per text (a control reached two ways is the same button)
    return [t for t in found if t.startswith("Enter ")], found


docs = TestDocs("needs").__enter__()
doc = None
try:
    g = fresh_module()
    doc = docs.open("Large Objects - Feet")
    g.STATE["on_confirm"] = lambda *a: None
    g.gordium_check()                                    # the sample, no bedrooms or parking stated
    item = parking(g)
    log["first"] = {k: item.get(k) for k in ("name", "status", "needs", "hint", "reason")}
    claim("the Parking row waits for exactly bedrooms and parking spaces",
          item.get("needs") == ["sleeping_rooms", "parking_spaces"] and item["status"] == "not_checked", log["first"])
    texts, found = enter_button(g, item)
    claim("its detail has one Enter button, named from what it waits for",
          texts == ["Enter bedrooms and parking spaces…"], texts)
    asked = []
    answers = {"Bedrooms": 3, "Off-street parking spaces": None}     # parking skipped
    g._count = lambda prompt: asked.append(prompt) or answers[prompt]
    g._ask_yes_no_or_skip = lambda prompt: asked.append(prompt) or None
    found[texts[0]].PerformClick()                       # the button itself
    claim("clicking it asks exactly those, in order", asked == ["Bedrooms", "Off-street parking spaces"], list(asked))
    facts = g.current_facts(doc)
    log["facts_after_first"] = {k: facts.get(k) for k in ("sleeping_rooms", "parking_spaces")}
    claim("the answer is saved; the skipped one stays unset (never 0)",
          facts.get("sleeping_rooms") == 3 and facts.get("parking_spaces") is None, log["facts_after_first"])
    item = parking(g)
    texts, found = enter_button(g, item)
    claim("the row now waits only for parking spaces, and its button says so",
          item.get("needs") == ["parking_spaces"] and texts == ["Enter parking spaces…"], (item.get("needs"), texts))
    asked.clear()
    answers["Off-street parking spaces"] = 2
    found[texts[0]].PerformClick()
    item = parking(g)
    log["last"] = {k: item.get(k) for k in ("name", "status", "needs")}
    claim("answering that one asks only it, and the row is checked", asked == ["Off-street parking spaces"] and
          item["status"] != "not_checked" and not item.get("needs"), (list(asked), log["last"]))
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
