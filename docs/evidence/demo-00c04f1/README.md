# The demo at 00c04f1: smoke in Rhino 8 (Mac), 2026-10-25

**Purpose:** whether the demo can go to the cofounders: each step of the coordinator's smoke, pass or fail.\
**For:** the coordinator, Ben.\
**Kept current by:** never changed (a dated record).

Rhino was restarted first. Every run used an extracted copy of 00c04f1 with recorded answers, each wait capped at
10 minutes.

| Step | Result |
|---|---|
| 1 Smoke: empty file → GordiumStart → the sample → Draw → house moved 5 ft → front yard fails → Check → Zoning report… opens on the Check sheet (`1_smoke/`) | **PASS, 7 of 7** |
| 2 Corner-lot street pick: Change…, both lines, Enter → lot width on one street (`2_corner/`) | **PASS** (pass2's claims 10 and 12; Lot width reads one street at a time, "9'-9 5/8" to 67'-10 7/8"", never both lines' 77'-8"), with a concern below |
| 3 The neighbourhood tick, hide and show (`3_tick/`) | **PASS, 10 of 10**; the locks are step 6 |
| 4 re_lookup_in_rhino.py | **BLOCKED**: in this restarted Rhino, Undo does nothing at all, with or without Gordium (below) |
| 5 pass2 claim 6, the empty file's box (`5_pass2/`) | **PASS** (pass2 at this head: 26 of 26) |
| 6 context_in_rhino.py claim 4 (`6_context/`) | **PASS on substance**: Parcels, Streets and Notes keep their own locks and stay locked after Gordium is unlocked; Buildings and Context don't; the redraw replaces 319 with 319. The claim still asks Grade to stay locked, which plain Rhino doesn't do, so it reads as a fail (15 of 16). |

## Step 4: Undo does nothing in this Rhino session

- The re-lookup check at 00c04f1 fails "2 one Undo puts the sample back exactly" (8 of 9 claims before it stops).
  The Draw's undo record is begun and ended outside a command, but `_Undo` undoes nothing: no undo event follows.
- The same check at cb4b6e0, which passed 39 of 39 this morning in the previous Rhino session, now fails the same
  way (`control_cb4b6e0_now.json`).
- The undo probe, with no Gordium code, also fails every case, the baseline included: a curve added in an undo
  record survives `_Undo` (`undo_probe_now.json`).
- Rhino's undo settings are normal (`undo_settings.json`: at least 1 step, 1,024 MB).
- Since the restart, Rhino's windows are not on the current desktop. System Events lists no window for Rhino and
  none is on screen, although Rhino is frontmost and the screen is unlocked. This morning's passing runs had
  Rhino's window in front. A command such as `_Undo` acts on the key document window, so the likely cause is that
  this session has none.
- So step 4 says nothing about the demo yet. To retry: bring Rhino's window onto the current desktop, then run it
  again.

## DEMO.md "What's new in this preview (2026-10-25)", checked against the screen

- "Keep my building says plainly that your lot is replaced": the re-lookup check's claims 3 and 5 test it, after
  the Undo step. Not reached in this session (step 4). At cb4b6e0 this morning both passed.
- "Undo and Redo of a new-address Draw are exact": blocked here (step 4). At cb4b6e0 this morning it was 39 of 39.
- "The neighbourhood stays locked when you unlock Gordium … Your own layers behave as Rhino normally does": **true**
  (step 6).

## Also noticed

- **Step 2, an architect's eye.** On a corner lot, clicking ONE of the sample's 8 short Ithaca Rd pieces keeps only
  that 9.8 ft piece as the street (the other 7 are dropped), so that street's frontage reads 9'-9 5/8" instead of
  about 69 ft. The Lot width row is needs review either way (which street counts isn't settled), but an architect
  would expect the whole street to be kept.
- Rhino showed a "Software Update" window after the restart (8.36 is available; 8.35 is installed). Nothing was
  installed. It had closed by itself before the Undo checks.
- During step 2's first try, something typed into Rhino's command line ("…cumentProperties", with GridSnap turned
  on) and stopped the script. It was cleared with Esc, and pass2 was run again from the start (26 of 26).
