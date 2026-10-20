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
