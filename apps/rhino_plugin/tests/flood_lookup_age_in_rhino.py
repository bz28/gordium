#! python3
"""How old the address lookup's "no overlay here" is (#92), in Rhino 8, each claim asserted. Run in Rhino, not in CI;
the logic is tested in CI (packages/design_checker/tests/test_flood_lookup_age.py). A fresh feet document:
1. GordiumCheck on the empty file, 106 Ithaca Rd typed and Look up pressed (its recorded answers, no live call), Draw.
   The recorded lookup is dated by its recording (2026-10-20), so its site line says how long ago that was.
   Every check request the plugin sends carries "today": Ithaca's own day (America/New_York, worked out here
   independently with zoneinfo), never the UTC day; city_day also agrees with zoneinfo at evening UTC instants.
2. The saved finding's date set to today: the site line says "looked up today (<today>)", no overlays row.
3. Set to 91 days before today: the overlays row is back, saying "91 days ago" and "look the address up again";
   no "Overlays: none found" site line.
4. Set to exactly 90 days before today (the limit): cleared again, the site line back.
Writes <temp>/gordium_flood_age/out.json ("ok": true at the end); closes its document."""
import datetime
import json
import os
import sys
import tempfile
import traceback
import zoneinfo

import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close, look_up_106  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_flood_age") + "/"
os.makedirs(S, exist_ok=True)
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
log = {"claims": {}, "steps": {}}


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


def seen(g):
    """What the last check showed: the overlays row (or None) and the header's Overlays line (or None)."""
    last = g.STATE.get("last") or {}
    items = last.get("items") or []
    row = next((i for i in items if i.get("id") == "release.overlays"), None)
    lines = (last.get("header") or {}).get("sources") or []
    line = next((t for t in lines if t.startswith("Overlays:")), None)
    return {"row": row and row.get("reason"), "line": line}


def set_date(g, doc, day):
    facts = g.load_facts(doc)
    facts["overlays_none_found"] = dict(facts["overlays_none_found"], date=day)
    g._save_facts(doc, facts)


docs = TestDocs("floodage").__enter__()
doc = None
try:
    g = fresh_module()
    sent = []
    begin = g._check_begin

    def spy(*a, **k):
        out = begin(*a, **k)
        sent.append(out["request"].get("today", "<missing>"))
        return out

    g._check_begin = spy
    ithaca = datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date()
    utc = datetime.datetime.now(datetime.timezone.utc).date()
    log["days"] = {"ithaca_zoneinfo": str(ithaca), "utc": str(utc), "city_day": g.logic.city_day()}
    # Rhino's own Python, at the evening hours where the UTC day is already tomorrow (both offsets, both changes)
    nyc, bad = zoneinfo.ZoneInfo("America/New_York"), []
    for at in ("2026-11-14T01:30", "2026-11-14T04:59", "2026-07-04T03:59", "2026-03-08T06:59", "2026-03-08T07:00",
               "2026-11-01T05:59", "2026-11-01T06:00", "2027-01-01T04:30"):
        t = datetime.datetime.fromisoformat(at).replace(tzinfo=datetime.timezone.utc)
        if g.logic.city_day(t) != str(t.astimezone(nyc).date()):
            bad.append((at, g.logic.city_day(t), str(t.astimezone(nyc).date())))
    claim("city_day in Rhino equals America/New_York's day at evening UTC instants and DST changes", not bad, bad)
    doc = docs.open("Large Objects - Feet")
    look_up_106(g, g.gordium_check)
    found = (g.load_facts(doc) or {}).get("overlays_none_found") or {}
    log["found"] = {k: found.get(k) for k in ("value", "date", "address", "source")}
    claim("the recorded lookup saved a 'no overlay here' finding with its date", found.get("value") is True and
          found.get("date"), log["found"])
    a = log["steps"]["1_recorded"] = seen(g)
    log["sent_after_lookup"] = list(sent)
    claim("the plugin sends today as Ithaca's day (zoneinfo), every check", sent and
          all(d == str(ithaca) for d in sent), {"sent": sent, "ithaca": str(ithaca), "utc": str(utc)})
    age = (ithaca - datetime.date.fromisoformat(found["date"])).days
    claim("recorded lookup (%d days old): site line with its age and date, no overlays row" % age,
          a["row"] is None and a["line"] and "(%s)" % found["date"] in a["line"], a)

    set_date(g, doc, str(ithaca))
    g.check_now()
    b = log["steps"]["2_today"] = seen(g)
    claim("dated today: 'looked up today (<today>)', no overlays row", b["row"] is None and b["line"] and
          ("looked up today (%s)" % ithaca) in b["line"], b)

    old = str(ithaca - datetime.timedelta(days=91))
    set_date(g, doc, old)
    g.check_now()
    c = log["steps"]["3_91_days"] = seen(g)
    claim("91 days old: overlays row back, says 91 days and to look the address up again, no site line",
          c["row"] and "look the address up again" in c["row"] and "91 days ago (%s)" % old in c["row"]
          and c["line"] is None, c)

    edge = str(ithaca - datetime.timedelta(days=90))
    set_date(g, doc, edge)
    g.check_now()
    d = log["steps"]["4_90_days"] = seen(g)
    claim("exactly 90 days old: still counts (row gone, site line back)", d["row"] is None and d["line"] and
          "(%s)" % edge in d["line"], d)
    log["sent_all"] = list(sent)
    claim("every check sent today as Ithaca's day", len(sent) >= 4 and all(s == str(ithaca) for s in sent), sent)
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
