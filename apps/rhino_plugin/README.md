# Gordium in Rhino (rhino_plugin)

New to it? Start with [QUICKSTART.md](QUICKSTART.md). `GordiumCheck` checks the open Rhino model against its zone's rules: PASS, FAIL or NEEDS REVIEW for every rule,
the largest legal building drawn see-through on the lot, failing parts in red, and the architects'-format report
saved next to the model. With live mode on (the default), it re-checks after every edit.

## Set up (once)

Step by step, from a new Mac: [QUICKSTART.md](QUICKSTART.md#what-you-need-once) (access, Python 3.12, the
repository in `~/Documents/gordium` with its `.venv`, then `install.py` run once in Rhino's ScriptEditor, which adds
`GordiumStart`, `GordiumCheck`, `GordiumLive`, `GordiumFacts` and `GordiumOff`). After `git pull`, quit and reopen
Rhino: it keeps the old code loaded until then.

## What happens

1. **Find:** the lot is the closed outline on the `Site` layer or a sublayer (the largest, if there are
   several); the buildings are the solids and meshes on the `Building` layer and its sublayers
   (`Building::Garage`), hidden or locked ones too. Anything else there that could be part of a building (a block, a loose surface) isn't
   dropped: it is reported, and every rule that measures the building says NEEDS REVIEW until it is exploded or
   made a solid. Any model units work: Gordium works in feet and converts at the edge.
2. **The start box** (spec A; `gordium_ui.start_box`): one box, prefilled, in the order an architect works:
   address, zoning district (Draw stays off until "I confirm the district" is ticked), use, street frontage
   (Pick line…), lot lines (tax map ±2'-0" or survey; Pick curves…), grade (not set, a terrain surface or mesh,
   or spot grades: Pick… / Place points…), finished or existing ground, and for a new project floor-to-floor
   height, massing (envelope and starting massing, or envelope only) and a preview of the starting massing. A
   pick closes the box, runs the pick in the model, and opens it again. The answers are saved inside the .3dm
   (document user text, `Gordium / lot_facts` and `Gordium / ui`). **Edit site…** in the panel opens it again.
   Without a grade the check still runs: the yards and coverage are measured, height and stories need review.
3. **Check:** the lot and building objects are copied into a small temporary .3dm and sent to Gordium's own
   Python (3.12, running in the background; `docs/decisions/2026-10-20_rhino_talks_to_python.md`). It measures
   them (`model_measurement`), runs the zone's rules (the same checker and report as `project_report`), and works
   out the envelope (`envelope_builder`). No AI anywhere.
4. **Show** (spec D, F): the panel (`gordium_ui.make_panel`) lists every item, bad news first (does not comply ·
   needs review · complies · not checked · not covered), each with its mark, proposed, required and margin
   (feet-inches to 1/8", never rounded toward compliance); the selected item shows the code's words, the
   examiner's citation and links, and how it was measured. The viewport draws the property line with each edge's
   length, each yard as measured with its status, the required yards shaded, the envelope see-through, and red
   only on the part of the building inside a required yard or above the height limit (the massing stays
   neutral). A status box (never a ✓) sits top right; a short notice bottom left when an item newly fails.
   Every word and number comes from the checker's `view` (`design_checker/present.py`); the Rhino side decides
   nothing. If a check can't run, the old result is cleared and the panel says why, with Retry.
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
- `packages/design_checker/tests/test_scenarios.py`: the architect's answer key
  (`test_data/test_sites/new_york/ithaca_city/scenarios/`), ten designs with the results worked out by hand
  before Gordium ran; every row matches or is an investigated disagreement, and a "does not comply" is never
  shown as complies.
- In Rhino 8 (Mac), driven by scripts (run in Rhino, not CI): `tests/ui_flow_in_rhino.py` (from an empty file:
  the start box, the starting building, then each realistic edit and its fix, with viewport captures and the
  panel's rows); `tests/scenarios_in_rhino.py` (the answer key drawn in Rhino; compare with
  `python -m design_checker.scenarios rhino <rhino_out.json>`); `tests/windows_in_rhino.py` (puts the panel or
  the start box on show for a window capture, `screencapture -l<window id>`); `tests/check_in_rhino.py`.

## Not yet

A proper Rhino plugin package (yak) and installer; Windows tested; the panel as a docked Rhino panel (it floats: docking needs a plugin package); grouping
street lines on corner lots (corner lots are left for the architects).
