# Only the offending part coloured (PR #28) at 92cf742: checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** the re-run after the fixes from the dcbc926 run, and what the screenshots show to an architect's eye.\
**For:** the coordinator, the #28 job, reviewers.\
**Kept current by:** never changed (a dated record).

`offending_part_in_rhino.py` at this head (it now records every claim): **18 of 18** (`offending_results.json`).

| Scene | What it shows |
|---|---|
| 1 Cantilever, tax-map readings (`1_cantilever_amber_*`) | The side yard needs review (to the wall it complies, to the cantilever not); amber only; the cantilever coloured, the air under it not |
| 2 Cantilever, deep enough to fail under every reading (`2_cantilever_red_*`) | Red in the cantilever; nothing under it; the house's own strip within 8 ft of the line red; past 8 ft amber |
| 3 Gable over the limit (`3_gable_*`) | Near the ridge coloured; the sky over the slope not; the coloured volume is the wedge above the limit (within 5 %) |

To an architect's eye the colouring is right in every scene: only the part that breaks the rule is coloured, red
where it fails under every reading, amber where only under some.

**One thing looks wrong (not a claim of this PR):** in scene 3 the red notice "Side yard, Southwest no longer
complies · 3'-0 5/8" to 7'-0 5/8" proposed …" is still on screen (`3_gable_perspective.jpg`). It belongs to scene 2;
the gable house is back on the original footprint. Either the notice outlives the model it was about, or the script
changes the model too fast for it to clear. Worth a look: an architect would read it as true of the house on
screen.
