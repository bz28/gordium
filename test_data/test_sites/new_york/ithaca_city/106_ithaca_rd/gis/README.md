# 106 Ithaca Rd: official lot outlines

Two official outlines of this lot (tax parcel 500700-84.-2-6), used to compare with the lot in the architects' model (`../model.3dm`, layer Site). They are evidence for `docs/questions_for_architects.md` §1.1–1.2. They are never used to decide a result: a GIS outline is a cross-check only.

| File | Source | Downloaded | SHA-256 |
|---|---|---|---|
| `city_tax_parcel_2026-10-20.json` | City of Ithaca `Tax_Parcels`, https://services5.arcgis.com/R1JbITZvSQHJsl5r/arcgis/rest/services/Tax_Parcels/FeatureServer/0/query?where=SWISPRINTK='500700-84.-2-6'&outSR=2261&outFields=*&f=json | 2026-10-20 | `a2527a5f…1b0f3c05` |
| `county_parcel_2026-10-20.json` | Tompkins County `Parcels_Public` (2026), https://services.arcgis.com/oJbAAWNInLrxvF0A/ArcGIS/rest/services/Parcels_Public/FeatureServer/0, queried by SWISPRINTK 500700-84.-2-6 with outSR=2261; owner and mailing fields removed | 2026-10-20 | `84d1506a…c2f654e2` |

Both are in feet (NAD83 / New York Central, EPSG 2261), unchanged since download. New York State's 2025 parcel layer has the same outline as the City's (same shape and size).

What they show (checked by `packages/rule_export/tests/test_questions_doc.py`):
- **City:** 7,033.7 sf; the front along Ithaca Rd is a curve of 8 segments, 75.8 ft; the side toward #104 is 92.12 ft; the rear is 69.51 ft; the jog is 10.35 ft (drawn as two edges); the long side is 101.13 ft.
- **County:** 6,900.4 sf; one straight front of 73.52 ft; 92.00, 68.86, 10.35 and 101.13 ft.
