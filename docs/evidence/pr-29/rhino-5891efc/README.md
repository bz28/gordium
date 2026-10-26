# PR #29 checked in Rhino at 5891efc: the failing yard's number in the real Top view

**Purpose:** what `dimensions_in_rhino.py` and `mvp_checks_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26, in the docked Top view (656 × 668 px) at the default zoom.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

| Run | Result |
|---|---|
| `dimensions_in_rhino.py` as written (`dimensions_results.json`) | **22 of 23**: "1 every number shown sits clear of the status box, the house and the other numbers" fails |
| `mvp_checks_in_rhino.py`, every claim recorded (`mvp_checks_results.json`) | **13 of 13** |

## Top at the default zoom (`1_top_labels_on.png`), to an architect's eye

- **The failing southwest side yard's number is drawn now:** "✕ 7'-0 5/8"" in red, bottom left. It is readable,
  and sits over the red and amber band along the house's left wall. (At 6d2e01a it wasn't drawn at all.)
- **The front yard's number still runs through the notice:** "? 26'-11 3/4"", vertical at the bottom left, printed
  through the "no longer complies" notice bar. This is the failing claim.
- The rear yard's "? 27'-6 7/8"", vertical, now starts just under the status box (clear of it) and touches the edge
  label "69'-6 1/8"" below it.
- The northeast side yard's "32'-4 1/4"", grey, on its own line: clean.
