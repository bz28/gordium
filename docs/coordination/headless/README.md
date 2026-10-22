# Headless checks (no Rhino)

Two scripts run Gordium's own Rhino code without Rhino. They import the plugin files unchanged
(`gordium_rhino.py`, `gordium_ui.py`). Stand-ins replace only Rhino's document, the viewports and the Eto
widgets (`fakerhino.py`, `fake_eto.py`, `fakes.py`). The checker and the lookup run for real, on the recorded
fixtures, with no network calls.

They prove the logic side of each Rhino claim. What only Rhino can show (drawing, real layers, real
dialogs, real Windows processes) is written in each result's `rhino_part`, and the tracker lists it.

| Script | Claims | Result on the demo build (dfac7ab), 2026-10-22 |
|---|---|---|
| `headless_demo_pass2.py` | Demo smoke (RHINO_QUEUE 9) + #15 pass 2 | 35 of 36 pass |
| `headless_context_lookup.py` | #23 neighbourhood (RHINO_QUEUE 7, ticks) + #19 R-2a box and street picks | 36 of 37 pass |

The two failures, both now fixed in #19:
- **Pass 2 claim 6 was out of date.** It expected the old empty-file wording. The claim now asks for
  `LOT_MISSING`, the box's wording since #19.
- **A real bug.** A lookup that replaced the sample's lot kept the sample's street source.
  `repro_street_source.py` shows it.

Run either one from a checkout of the build being tested:

    cd <checkout> && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(ls -d packages/* | tr '\n' ':') \
      /home/user/venv/bin/python <this folder>/headless_demo_pass2.py

Each one writes its `results_*.json` next to itself. The R-2a box check uses `lookup_shim.py`, which sets
the recorded zoning answer to R-2a because no R-2a fixture exists.

## re_lookup/ — the re-lookup branch's plugin code, without Rhino

`re_lookup/headless_re_lookup.py` runs the re-lookup branch's `gordium_rhino.py` unchanged under the same stand-ins,
extended with RhinoCommon's undo records (`BeginUndoRecord`/`EndUndoRecord`: recorded, not replayed) and blocks.

What it covers:
- the in-Rhino proof `re_lookup_in_rhino.py`, step for step and claim for claim;
- a one-street track and Cancel at the question;
- the City's guide (the box stays open);
- a surveyed own lot;
- a retyped address;
- a garage on a sublayer;
- blocks;
- the architect's own answers keeping their sources.

Result at dd6f1c4 (2026-10-22): 46 of 46 checkable pass. 4 can only be checked in Rhino (Undo and Redo themselves).
Along the way it found two real bugs, both fixed in the branch:
- the in-Rhino script expected a starting house on a corner lot;
- a dropped preview lost a district whose own had no rules.

Set `GORDIUM_WT` to a checkout of the branch to run it against another checkout.
