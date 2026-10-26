# PR #31 checked in Rhino at fc41fea: depth on a shaded house, and orbit timing

**Purpose:** what `depth_in_rhino.py` and `depth_in_rhino_phase2.py` (both as written) showed in Rhino 8 (Mac) on 2026-10-26, run in two phases with Rhino idling about 8 s between, so the house is really shaded.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Result, run twice

| | Run 1 (`depth_results_run1.json`) | Run 2 (`depth_results.json`) |
|---|---|---|
| phase 1 (claims 1, 2) | 6 of 6 | 6 of 6 |
| phase 2 pixel claims 3 to 6, on a shaded house | all pass | all pass |
| 7. orbit, labels and colours on, at most 1.2 × off (median of 40) | **fails: 41.6 / 34.3 ms = 1.21 ×** (worst 79 / 65 ms) | passes: 36.3 / 35.1 ms = 1.03 × (worst **261** / 52 ms) |
| total | 13 of 14 | **14 of 14** |

Claim 7 is borderline: 1.21× in one run, 1.03× in the next, with a single 261 ms frame in the second. That is far
from e9b2a69's 89 ms against 33 ms (2.7×), but close enough to the limit that one run can fail.

## To an architect's eye

- **`5_front_coloured.png`** (Shaded Front, colours on): the house is solid and light grey. Its front face is not
  amber, so the rear yard strip behind it is hidden. The 35'-0" height dimension shows beside it, through the
  see-through envelope.
- **`3_perspective_shaded.png`** (from the street): the house hides the rear yard's dimension. The rear strip shows
  only as a thin amber edge along the roof line, where it is really seen. The front yard's dimension shows in front.
- **`6_back_coloured.png`** (from behind): the rear face is amber, the part of the house in the rear yard.
