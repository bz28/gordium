# 106 Ithaca Road (City of Ithaca, R-1b)

A hypothetical new single-family house the architects worked through by hand. (The city map shows a house already on this lot; the example ignores it.)

- `model.3dm` — the architects' `Gordium_Envelope_Example_v1.3dm` (received 2026-10-17, unedited, renamed). Rhino 8, units feet; created by Borys, last edited by lukeh.
- Zone: **R-1b, confirmed** (checked 2026-10-19). See the official record below.

## Official record (City of Ithaca GIS, tax parcel layer, checked 2026-10-19)

| Item | Value |
|---|---|
| Tax parcel | 84.-2-6 |
| Zone | R-1b (also matches the May 2026 zoning map, p.1 and p.8) |
| Overlay zone | none |
| Historic district / property | no / no |
| FEMA flood zone | no |
| Existing use | 1-family residence |
| Official lot area | ~7,034 sf (0.1615 acres) |

Note: the lot in the architects' model is **6,674.5 sf** (their spreadsheet types 6,674), about 5% smaller than the official parcel. The official parcel's street side is curved; the model draws it as one straight 73 ft line. Tax maps are not surveys, so neither is exact; a survey would settle it. This matters because coverage (25% of lot area) depends on it.

## What's in the model

| Layer | Contents |
|---|---|
| Map | 94 outlines of neighbouring buildings (named with OpenStreetMap-style IDs) |
| Site | The lot (5 sides: 73.00 front, 90.28 and 99.37 sides, 67.72 rear, 10.47 jog; 6,674.5 sf), **plus** the buildable-area outline (~53.3 × 40.8 ft, 2,169.2 sf) and one loose line |
| Setback | 3 loose construction lines (the setbacks used were 30 front / 10 / 10 / 20 rear) |
| Building | One 35 ft tall solid |

## Known problems

The model has several errors (building off the lot, rear setback too small, over coverage). They're useful as checker test cases. See `docs/discrepancies_with_architects.md` (sections 1 and 4).

`spreadsheet_design.yaml` is the architects' spreadsheet version of this house as our measurements; `packages/rule_format/tests/test_answer_keys.py` checks our draft R-1b gives their PASS/FAIL on every row. Expected results for the Rhino model itself come once models can be measured.

`spreadsheet_design_report.xlsx` is Gordium's own report for this design, in the architects' format
(`python -m project_report spreadsheet_design.yaml`; generated, never hand-edited; CI checks it is current).

## Read in Revit

`revit_reading.json` is this model drawn in Revit 2027.4 and read back by the Revit add-in (recorded on the Windows
trial laptop, 2026-11-19): each closed Site outline a property line (the lot picked by `lot_id`, as in Rhino), the
house one element in a building category made of exactly the faces Rhino's reader sends, every other curve a model
line. `packages/design_checker/tests/test_real_site_revit.py` holds it to what the Rhino reader reads from the same
model: the same description (every point within a millionth of a foot) and the same verdicts (5 complies, 18 needs
review, 9 not checked: the house reaches past the lot, so its yards and coverage can't be measured, in either host).
To re-record (on the Windows trial laptop, with `real_site.py` from `apps/revit_addin/tests/Gordium.Revit.Reading.Tests/`):

1. `real_site.py export model.3dm model_facts.yaml > export.json` (it refuses a model it can't draw as Rhino reads
   it, naming what).
2. Write `%LOCALAPPDATA%\Gordium\trial\real_site_request.json` as `{"model": "<export.json>", "out": "<revit.json>"}`
   and start Revit: the add-in draws, reads and writes `revit.json` (and deletes any earlier one first), logging a
   `real_site` line to `results.jsonl` (an `error` there means no result).
3. `real_site.py record <revit.json> model.3dm <date> "<Revit version>, Gordium add-in (trial)" revit_reading.json`.
4. `real_site.py compare model.3dm model_facts.yaml revit_reading.json` prints `[]`, and the test passes.
