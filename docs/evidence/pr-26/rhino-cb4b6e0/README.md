# Re-lookup (#26) at cb4b6e0: checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** whether Redo works after a re-lookup's Draw (it did nothing at the demo's e631aae), and the rest of
the re-lookup flow.\
**For:** the coordinator, the #26 job, reviewers.\
**Kept current by:** never changed (a dated record).

Both scripts are this head's own, run from an extracted copy with recorded answers.

| Run | Result |
|---|---|
| `re_lookup_in_rhino.py` (`re_lookup_results.json`, Top captures): all 5 steps | **39 of 39** |
| `undo_redo_probe_in_rhino.py` (`undo_redo_probe_results.json`): each kind of change inside one undo step begun outside a command | **8 of 8 cases pass** |

**Redo now works.** With the check running as the architect works, from outside any command, using Rhino's own
_Undo and _Redo:
- after the Draw to 96, Undo puts the sample back exactly and Redo draws 96's lot again;
- a second Undo and a second Redo do the same;
- after each, the file's saved facts, box choices and sources follow the model on screen, nothing of the other
  model is left drawn (no dashed outline), and the model is checked again;
- step 5 (a surveyed lot replaced by 96's, Keep my building) undoes and redoes the same way.

Each Draw's undo record was begun outside a command (`"in_command": false` in `undo_records`). The Rhino undo
events are in `undo_events`.

**No change breaks Redo** in the probe. Each case passes (Undo removes, Redo brings back): the baseline; document
strings; attribute user strings; a layer added then deleted; an object held on a hidden layer then deleted; a
layer's visibility set; a command run inside the record; and all of them at once. The e631aae failure came from
how that head ran its record. That run went through `doc.Redo()` and a script inside Rhino's script command, and
it found nothing to redo. The same steps now pass.
