# PR #32 and #33 in Rhino at c4ad070 (one build), second run, 2026-10-26

**Purpose:** what `progress_cancel_in_rhino.py` (#32) and `autocomplete_in_rhino.py` (#33) showed in Rhino 8 (Mac) on address-autocomplete c4ad070, which contains progress-cancel 9540311.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

Each script was run as written (it stops at its first failed claim), then as a copy whose only change is that a
failed claim is recorded instead of stopping the run (`*_soft.json`), so every later claim is seen.

| Script | As written | Every claim recorded |
|---|---|---|
| progress_cancel_in_rhino.py (#32) | 2 of 3, stops at claim 1 | **28 of 29**: only "the wait window has the keyboard … 'Esc or Cancel to stop'" fails |
| autocomplete_in_rhino.py (#33) | 1 of 2, stops at claim 2 | **13 of 15**: both claim 2 parts fail (list height not measured; box grows 345 → 351 pt only) |

## #32 claim 1: the desktop, not Gordium

During the run another app (Google Chrome) kept the front, so no Rhino window could have the keyboard. The wait
window then rightly says "Click Cancel to stop" (its rule: "Esc or Cancel" only while it has the keyboard). Bringing
Rhino forward from inside Rhino did not hold. Left for a human: run it again with Rhino in front and nothing else
taking focus.

## #33 claim 2: the product bug found at c4ad070 earlier today is still there

`gordium_ui.list_row_px` calls `table.RectOfRow(...)`, which Eto's Mac list table doesn't have (it has
`RectForRow(IntPtr)`), so it always falls back to 20 px a row and the box grows by too little (see
`docs/evidence/pr-33/rhino-c4ad070/` on wip/address-autocomplete-rhino-c4ad070). No new commit on #33 since; owner #33.

## Left for a human

The keys (Down, Enter, Enter; a click on a suggestion; Esc closes only the list) and #32's Esc: another app held
the front throughout, and keys are sent only to Rhino in front.
