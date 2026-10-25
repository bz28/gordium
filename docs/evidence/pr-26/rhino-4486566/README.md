# Re-lookup (#26) at 4486566: checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** the re-lookup check at this head, including its new step 4 (an address typed but not looked up).\
**For:** the coordinator, the #26 job.\
**Kept current by:** never changed (a dated record).

Run in a copy that records every claim without stopping (`re_lookup_all_claims_results.json`): **23 of 41 pass.
Every failure is an Undo claim, or follows from one, and Undo doesn't work in this Rhino session at all**: the
undo probe, with no Gordium code, fails its baseline in the same session (`undo_probe_same_session.json`). Since
Rhino was restarted, its windows are not on the current desktop, so `_Undo` has no key document window. The same
check passed 39 of 39 at cb4b6e0 this morning, before the restart. Re-run once Rhino's window is back in front.

| Part | Result |
|---|---|
| 1 the sample | pass |
| 2 Look up changes nothing while the box is open; the dashed lookup; Draw asks nothing; the sample's lot and house gone; 96's lot drawn; no house on 96 (a corner lot); the file says 96 | pass (7) |
| 2 Undo, Redo, second Undo and Redo, and the checks after each | blocked by Undo (the Redo claims that pass only see that nothing changed) |
| 3 asked once; the Keep answer names 96's lot; Keep my building keeps the floors | pass (3) |
| 4 the same address: no question, nothing changes | pass |
| **4 (new) an address typed and not looked up: Draw says to look it up first, nothing changes** | **pass** |
| **4 (new) the lot's own address (the box opened again on it): Draw goes through and checks it as it is** | **pass** |
| 5 asked once, the question and the Keep answer say the surveyed lot will be replaced; Keep keeps the floors | pass (3) |
| 5 Undo and Redo and the checks after each | blocked by Undo |
