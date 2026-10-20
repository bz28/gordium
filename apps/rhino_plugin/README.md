# Gordium in Rhino (rhino_plugin)

`GordiumCheck` checks the open Rhino model against its zone's rules: PASS, FAIL or NEEDS REVIEW for every rule,
the largest legal building drawn see-through on the lot, failing parts in red, and the architects'-format report
saved next to the model. With live mode on (the default), it re-checks after every edit.

## Set up (once)

1. Rhino 8 (tested on Mac; Windows should work but is untested) and this repository with its `.venv` (`python3.12 -m venv .venv && .venv/bin/pip install -e .`).
2. In Rhino: `RunPythonScript`, pick `apps/rhino_plugin/install.py`. That adds the commands `GordiumCheck`,
   `GordiumLive`, `GordiumFacts` and `GordiumOff`.

## What happens

1. **Find:** the lot is the closed outline on the `Site` layer or a sublayer (the largest, if there are
   several); the buildings are the solids and meshes on the `Building` layer and its sublayers
   (`Building::Garage`), hidden or locked ones too. Anything else there that could be part of a building (a block, a loose surface) isn't
   dropped: it is reported, and every rule that measures the building says NEEDS REVIEW until it is exploded or
   made a solid. Any model units work: Gordium works in feet and converts at the edge.
2. **Confirm once:** one small dialog, prefilled: "City of Ithaca · R-1b · one-family dwelling, detached ·
   street side = the blue line · not a corner lot · ground flat at z = 0 · lot outline not from a survey".
   The lot is outlined green, the street line blue (and the main building, when there are several). **OK** keeps
   it; **Change…** asks for each one (zone, use, lot, main building, corner lot, the street lines, flat ground,
   ground level, survey). The answers are saved inside the .3dm (document user text, `Gordium / lot_facts`), so
   the next run doesn't ask, unless one is missing. Bedrooms, parking spaces and stories aren't asked: until they
   are entered (**GordiumFacts**, which also changes any other fact), only the rules that need them say NEEDS
   REVIEW. A prompt skipped with Enter leaves the fact unset, never 0.
3. **Check:** the lot and building objects are copied into a small temporary .3dm and sent to Gordium's own
   Python (3.12, running in the background; `docs/decisions/2026-10-20_rhino_talks_to_python.md`). It measures
   them (`model_measurement`), runs the zone's rules (the same checker and report as `project_report`), and works
   out the envelope (`envelope_builder`). No AI anywhere.
4. **Show:** a message in the corner of every view ("✓ All 10 rules pass", or "✗ 9 pass · 1 fail" and what fails,
   by how much), failing solids in red, each failing distance as the red line it was measured along with its
   numbers (only the ones that fail), the envelope see-through in blue, and a small panel with every rule. The
   envelope is drawn only on flat ground, a lot that isn't a corner lot, and rules it can read; otherwise the
   panel says why. If a check can't run, the old result is cleared and the panel says why. Nothing in the model is changed:
   all of it is drawn on top (a display conduit).
5. **Live:** after every edit (a move, a stretch, a new or deleted object, a layer change), it re-checks once the model has been
   still for half a second. No pop-ups.

The report (`<model>_gordium_report.xlsx`) is written next to the model by `GordiumCheck`, not on every edit.

## How we know it works

- `packages/design_checker/tests`: the 106 Ithaca Rd model gives 9 PASS and the coverage FAIL; moving the house
  3 ft back makes the rear yard FAIL with its measured line; the background worker answers request by request and
  never stops on a bad one; bad lot facts are a plain refusal.
- `packages/envelope_builder/tests`: the envelope's sides sit at the required yards (never inside one), its top at
  the height limit, under every reading of the lot.
- `packages/design_checker/tests/test_check.py::test_rhino_decisions`: which objects are sent, which facts are
  missing, skipped prompts, feet (the Rhino command's decisions, `design_checker/rhino_logic.py`, run in CI).
- In Rhino 8 (Mac), driven by scripts: the steps above on a copy of 106 Ithaca Rd, with viewport captures (see the
  PR description); and `tests/check_in_rhino.py` (run in Rhino on that copy): a check that can't run clears the
  old result, only the failing side yard is drawn, a block on the Building layer gives NEEDS REVIEW, a SubD's red
  copy is drawn.

## Not yet

A proper Rhino plugin package (yak) and installer; Windows tested; the panel as a docked Rhino panel; grouping
street lines on corner lots (corner lots are left for the architects).
