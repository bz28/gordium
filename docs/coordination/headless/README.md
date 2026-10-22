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
