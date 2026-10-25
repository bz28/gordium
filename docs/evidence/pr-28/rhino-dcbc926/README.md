# Only the offending part coloured (PR #28) at dcbc926: checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** what `offending_part_in_rhino.py` showed, and what the screenshots show to an architect's eye.\
**For:** the coordinator, the #28 job, reviewers.\
**Kept current by:** never changed (a dated record).

The script as written stops at its second claim (`as_written_results.json`). A copy that records every claim
without stopping (`all_claims_results.json`) gives **4 of 9**.

| Claim | Result |
|---|---|
| 1 the cantilevered house is one closed solid | pass |
| 1 the left side yard is measured to the cantilever and does not comply | **fails**: needs review, "6'-0 5/8" to 12'-0 5/8"" against 10'-0" |
| 1 red and amber both drawn | **fails**: amber only |
| 1 every coloured piece is the cantilever's own: its bottom at 10 ft | **fails**: the recorded piece spans x 6.87–48.83 ft, z 0–20 ft |
| 1 nothing coloured outside the solid | pass |
| 2 the height row needs colour | pass |
| 2 the roof is coloured in the height row's colour | pass (amber) |
| 2 every piece starts at the height limit, never at the eaves | **fails**: one piece starts at the ground (-0.02 ft), one at 34.96 ft |
| 2 the coloured volume is the roof's wedge above the limit (within 5 %) | **fails**: 6,143 against 5,070 cu ft (+21 %) |

## What the screenshots show (an architect's eye)

- **Cantilever** (`1_cantilever_front.png`, `1_cantilever_perspective.jpg`): only the overhanging upper floor is
  coloured, from 10 ft to 20 ft, nothing under it and nothing of the main body. That is what Ben asked for.
- **Gable** (`2_gable_front.png`, `2_gable_perspective.jpg`): only the roof's wedge above the 35'-0" limit is
  coloured (the gable end's triangle and the roof faces above the limit), not the eaves.
- **Amber, not red, is right for this lot.** The sample's lot is from the tax map (each lot line ±2'-0"), and the
  side yard's readings run from 6'-0 5/8" to 12'-0 5/8": it fails only under some readings, so needs review
  (amber). The height row is needs review on this lot too. Red needs a case that fails under every reading.

## Why the claims fail (for the #28 job to settle)

1. **The scene can't give red.** On the tax-map sample, the cantilever's side yard is needs review, never does not
   comply. Claims 1b and 1c ("does not comply"; "red and amber both drawn") need a surveyed lot or a deeper
   cantilever.
2. **The recorded pieces are not what is drawn.** `g.overlay().encroach` holds, for the cantilever, a piece whose box
   is the house's main body at full height (x 6.87–48.83 ft, z 0–20 ft), and for the gable a piece starting at
   the ground. The screen shows only the cut parts. Either the overlay keeps the uncut solid or block and clips it
   when drawing, or the claims read the wrong list. As it stands, the claims and the drawing disagree. Worth
   checking which is true before relying on either.
