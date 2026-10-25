# The demo at e631aae (third update): checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** what the Rhino runs of RHINO_QUEUE item 11 showed before the cofounders are told to pull.\
**For:** Ben, the coordinator, reviewers.\
**Kept current by:** never changed (a dated record).

Each run used an extracted copy of e631aae (never a working tree), with recorded lookup answers (no live calls).
Rhino was left with one empty document.

| Run | Result |
|---|---|
| The smoke: an empty file → GordiumStart, the sample → Draw → the house moved 5 ft toward the street → the front yard fails → Zoning report… opens on the Check sheet (`smoke/`) | **7 of 7** |
| pass2_in_rhino.py, all steps (`pass2/`), incl. the corner-lot street pick (10, 12) and claim 6 (an empty file's box: "no lot yet: draw it, or pick a closed outline on the Site layer", no Use my survey… or Change…) | **26 of 26** |
| re_lookup_in_rhino.py (`re_lookup/`) | **12 of 13: "2 Redo draws 96 again" fails** |
| The panel's neighbourhood tick, context_tick_in_rhino.py (`context/`) | **10 of 10** |
| context_in_rhino.py (`context/`): the layers stay locked | **12 of 13 when it stopped: "4 with the Gordium layer and the architect's Gordium::Grade locked, a redraw replaces (never doubles) and puts both locks back" fails** |

## The two failures

**Redo after a re-lookup (re_lookup step 2).** Look up 96 → Draw → one Undo puts the sample back exactly (passes).
Then Redo does nothing. `doc.Redo()` returns False, and Rhino's own `_Redo` command, run as the architect would,
does nothing either. The model stays the sample's lot and house (`2_after_redo.png`: the sample, with 96's
dotted outline still on screen). So nothing is left to redo after that Undo; this is not the test's way of
calling Redo. The run was continued past this claim (a copy recording it without stopping): steps 3 and 4 pass
(asked once, naming the edited house; Keep my building; the same address again changes nothing).

**The neighbourhood's locks under a locked "Gordium" layer (context claim 4, second part).** With the architect's
"Gordium" layer and Gordium::Grade locked, a redraw replaces without doubling (319 before, 319 after), and both locks
are put back. But a probe (`context_lock_probe.json`) shows:
- While "Gordium" is locked, every context layer's own lock (`GetPersistentLocking`) is off. They read locked
  only because their parent is.
- Once "Gordium" is unlocked, Parcels, Streets and Notes are unlocked. They should stay locked.

That is a product bug. Separately, the claim reads the locks while the parent is still locked. Rhino then reports
every sublayer locked, Buildings included, so "Buildings unlocked" can never hold at that moment. The claim should
read each layer's own lock, or read the locks after the parent is unlocked.

## Notes
- The smoke script's stand-in for opening the report was updated. Later heads open files through
  `gordium_ui.spawn` (no console window on Windows). This was a test-script change only.
- Two images are JPEG to stay under 300 KB.
