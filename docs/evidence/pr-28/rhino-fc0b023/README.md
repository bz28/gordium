# Only the offending part coloured (PR #28) at fc0b023: checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** the offending and highlight checks at this head, and the coordinator's extra probe: a house over the
height limit with a curved vault roof.\
**For:** the coordinator, the #28 job, reviewers.\
**Kept current by:** never changed (a dated record).

| Run | Result |
|---|---|
| `offending_part_in_rhino.py` (`offending/`) | **18 of 18** |
| `highlight_in_rhino.py`, in a copy recording every claim (`highlight/`) | **18 of 19**: "2 no label crosses a dimension, a lot edge or the house, nor covers another label" fails (the southwest side yard's label crosses 13 lines, as at #15 27c8e5d) |
| The vault probe (`vault/`, `vault_probe_in_rhino.py`) | **5 of 7: the vault above the walls isn't coloured** |

## The vault probe: a failing part left uncoloured

A house where the starting house stood, its walls 36 ft high (over the 35 ft limit), its roof a true curved vault
(an arc) to 42 ft at the middle. Everything above 35 ft is over the limit: a 1 ft band of wall all round, and the
whole vault.
- Pass: the solid is closed and its roof curved; the height row needs colour; its pieces are in its colour; the
  coloured part spans the whole plan (width and depth, within 0.1 ft); nothing is coloured below the limit.
- **Fail: only the band from 35 to 36 ft is coloured.** The coloured pieces' box runs from z 34.96 to 36.04 ft. Under
  the crown at 41 ft nothing is coloured. The coloured volume is 1,451 cu ft, against the 6,822 cu ft that is really
  above the limit (the solid cut by Rhino at the limit). `V_vault_front.png` shows it: a thin amber line at the wall
  tops, and the vault above it uncoloured.
- That breaks the PR's own rule that a failing part is never left uncoloured. The flat gable is right (scene 3:
  its wedge, within 5 %), so the curved roof face is likely the cause: it doesn't seem to be cut at the limit and
  kept the way flat roof faces are.

## Also seen

- Scene 3 (`3_gable_perspective.jpg`): the previous scene's red "Side yard, Southwest no longer complies …" notice is
  still on screen over the gable house. #15 fixed this at 27c8e5d (the notice ends with its model), and this head
  doesn't carry that fix yet.
