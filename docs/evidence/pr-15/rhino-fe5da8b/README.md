# PR #15 checked in Rhino at fe5da8b: plan labels while the view moves and when it stops

**Purpose:** what `apps/rhino_plugin/tests/redraw_timing_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26 at rhino-ui fe5da8b.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

**PASS, 5 of 5** (`redraw_timing_results.json`), Gordium loaded from an extracted copy of fe5da8b:

| Claim | Seen |
|---|---|
| 1 a moving frame's label work at most 16 ms (median, labels on less off) | 0.5 ms more (Top zoom 13.1 vs 12.6 ms median; Perspective orbit 13.5 vs 13.2 ms; 40 frames each) |
| 2 no label drawn while moving breaks a HARD rule | 143 labels checked, none broken |
| 2b none plainly wrong (edge, icon, boxes, other labels) | 143 checked, none wrong |
| 3 every stop placed in ONE pass of at most 120 ms | one pass each stop, at most 45.0 ms placing |
| 4 the frame after the pass is settled | every stop settled, nothing broken at rest |

The two captures are one stop, before and after its pass. "No jump at the stop" by eye was not judged here.
