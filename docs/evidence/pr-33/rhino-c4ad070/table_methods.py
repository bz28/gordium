#! python3
"""Lists the row-geometry methods of Eto's Mac ListBox table (writes table_methods.json)."""
import json

import Eto.Forms as ef

H = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
out = {}
try:
    lb = ef.ListBox()
    t = lb.ControlObject
    out["type"] = str(type(t))
    out["names"] = sorted(n for n in dir(t) if ("Rect" in n or "Row" in n) and not n.startswith("_"))
    try:
        out["RectForRow(0)"] = str(t.RectForRow(0))
    except Exception as e:
        out["RectForRow_error"] = repr(e)
except Exception as e:
    out["error"] = repr(e)
out["done"] = True
json.dump(out, open(H + "table_methods.json", "w", encoding="utf-8"), indent=1)
