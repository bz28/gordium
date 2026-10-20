# 106 Ithaca Rd: official lot outlines

Two official outlines of this lot (tax parcel 500700-84.-2-6), used to compare with the lot in the architects' model (`../model.3dm`, layer Site). They are evidence for `docs/questions_for_architects.md` §1.1–1.2. They never decide a result: a GIS outline is a cross-check only.

Each file is exactly what its URL returned on 2026-10-20 (downloaded with `curl -s -o <file> "<URL>"`); fetching the URL again gave the same bytes. Only non-personal fields were requested, so no owner or mailing details are stored. Coordinates are in feet (NAD83 / New York Central, EPSG 2261).

**`city_tax_parcel_2026-10-20.json`**, City of Ithaca `Tax_Parcels`:
- URL: `https://services5.arcgis.com/R1JbITZvSQHJsl5r/arcgis/rest/services/Tax_Parcels/FeatureServer/0/query?where=SWISPRINTK%3D%27500700-84.-2-6%27&outSR=2261&outFields=SWISPRINTK,LOCADDR,ZONING,CALCACRES&returnGeometry=true&f=json`
- SHA-256: `a2527a5fffa94395fc19d2279ef3ee05e225c94e7a9c0e730431f1ec1b0f3c05`

**`county_parcel_2026-10-20.json`**, Tompkins County `Parcels_Public` (2026):
- URL: `https://services.arcgis.com/oJbAAWNInLrxvF0A/ArcGIS/rest/services/Parcels_Public/FeatureServer/0/query?where=SWISPRINTK%3D%27500700-84.-2-6%27&outSR=2261&outFields=SWISPRINTK,LOCADDR,ZONING,FRONTAGE,DEPTH,PROPCLASS&returnGeometry=true&f=json`
- SHA-256: `ca1420eaa4c8950a7fce0295a582a4acf32e4126febcaa9f16fb1a24b52533ca`

New York State's 2025 parcel layer has the same outline as the City's (same shape and size).

What they show (recomputed from these files by `packages/rule_export/tests/test_questions_doc.py`, which also checks the fingerprints above):
- **City:** 7,033.7 sf; the front along Ithaca Rd is a curve of 8 segments, 75.8 ft; the side toward #104 is 92.12 ft; the rear is 69.51 ft; the jog is 10.35 ft (drawn as two edges); the long side is 101.13 ft.
- **County:** 6,900.4 sf; one straight front of 73.52 ft; 92.00, 68.86, 10.35 and 101.13 ft.
