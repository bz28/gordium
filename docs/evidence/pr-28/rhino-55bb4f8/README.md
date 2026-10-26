# Only the offending part coloured (PR #28) at 55bb4f8: checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** the re-run with scene 4, the curved vault over the height limit (the Rhino job's probe at fc0b023).\
**For:** the coordinator, the #28 job, reviewers.\
**Kept current by:** never changed (a dated record).

| Run | Result |
|---|---|
| `offending_part_in_rhino.py` (`offending/`) | **23 of 23**, scene 4 included |
| `highlight_in_rhino.py`, each frame drawn before it is read (`highlight/highlight_sync_draw.py`) | **18 of 19**: "2 no label crosses …" (the southwest label crosses 13 lines). #15 fixed this at 6361a3f; this head doesn't carry it yet. |

**The vault is fixed.** The vault house (walls to 36 ft over the 35 ft limit, a true arc to 42 ft) is coloured above
the limit in full: just inside each wall at +0.5 ft, under the crown at 41 ft, and nothing 1 ft below the limit. The
coloured volume is the vault's own part above the limit (within 5 %). The height row needs review (the curved
vault isn't measured), never complies. In `4_vault_front.png` the whole arc above the limit is amber.

To an architect's eye: the "Height limit 35'-0"" label sits over the left part of the coloured vault. A small thing,
but it covers part of what is wrong. The red "no longer complies" notice over scenes 3 and 4 is the earlier scene's,
the known stale notice that #15 has fixed (this head doesn't carry it yet).
