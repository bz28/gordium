"""Minimal repro (pure rhino_logic, no Rhino): Look up an address whose district Gordium has no rules for, then
retype the drawn address before Draw. gordium_rhino._draw_prepare applies the box first (box_facts writes
zone=None), then settle_pending -> drop_pending, whose undo entry for zone has new=MISSING, so None != MISSING and
the sample's district is never put back. Run from /home/user/wt/re-lookup with PYTHONPATH=packages/*."""
from design_checker import rhino_logic as logic

facts = {"zone": "R-1b", "address": "106 Ithaca Rd, Ithaca, NY", "lot_id": "lot1"}
saved = {"replaceable_lot": "lot1", "drawn_address": "106 Ithaca Rd, Ithaca, NY"}
answer = {"status": "found", "query": "96 Ithaca Rd", "facts": {
    "address": {"value": "96 Ithaca Rd, Ithaca, NY 14850", "source": "NYS Geocoder", "confirmed_by": None,
                "date": "2026-10-20"},
    "zone": {"value": "R-2a", "source": "suggested by Gordium", "confirmed_by": None, "date": "2026-10-20"}},
    "details": {}, "labels": {}, "writes": {}}
f, s, _ = logic.preview_lookup(answer, facts, saved, zones=["R-1b"])
print("after Look up (preview):", {"zone": f.get("zone", "<missing>"), "pending": s["_pending"]["address"]}, "undo:", [u[:3] for u in s["_pending"]["undo"]
                                                                              if u[1] == "zone"])
state = {"address": "106 Ithaca Rd, Ithaca, NY", "zone": f.get("zone"), "use": f.get("use")}   # the box as shown
f2, s2 = logic.box_facts(f, s, state)                     # _draw_prepare step 1 (_apply_box)
f3, s3 = logic.settle_pending(f2, s2, state["address"])   # _draw_prepare step 2
print("at Draw after settle_pending: zone =", repr(f3.get("zone")), "(expected 'R-1b')")
f4, s4 = logic.settle_pending(f, s, state["address"])     # the same without box_facts first
print("settle_pending alone (no box_facts first): zone =", repr(f4.get("zone")))
