# 106 Ithaca Rd: official lot outlines

Official outlines of this lot (tax parcel 500700-84.-2-6), compared with the lot in the architects' model (`../model.3dm`, layer Site). They are evidence for `docs/questions_for_architects.md` §1.1–1.2. They never decide a result: a GIS outline is a cross-check only.

**`county_parcel_2026-10-20.json`**: Tompkins County `Parcels_Public` (2026), stored as downloaded.
- Terms: the layer (item 505beb987c93401b8445777a8bb9bda6) says "Access: Open to the public", for general reference only; "It does not represent an on-the-ground survey and represents only the approximate relative location of property boundaries."
- URL: `https://services.arcgis.com/oJbAAWNInLrxvF0A/ArcGIS/rest/services/Parcels_Public/FeatureServer/0/query?where=SWISPRINTK%3D%27500700-84.-2-6%27&outSR=2261&outFields=SWISPRINTK,LOCADDR,ZONING,FRONTAGE,DEPTH,PROPCLASS&returnGeometry=true&f=json`
- Downloaded 2026-10-20 with `curl -s -o <file> "<URL>"`; fetching it again gave the same bytes. Only these non-personal fields were requested: no owner or mailing details.
- SHA-256: `ca1420eaa4c8950a7fce0295a582a4acf32e4126febcaa9f16fb1a24b52533ca`

**`city_tax_parcel_facts.yaml`**: measurements we took from the City of Ithaca `Tax_Parcels` outline. The City's data itself is **not stored**: the City's GIS terms don't allow redistributing it without their written consent, which hasn't been asked for yet. The file records the exact URL, the download date and the SHA-256 of the raw response (kept outside the repo), so anyone can re-download the same data and re-measure it. It carries the statement the City asks derived products to include.

Coordinates are in feet (NAD83 / New York Central, EPSG 2261). New York State's 2025 parcel layer has the same outline as the City's (same shape and size).

What they show (`packages/rule_export/tests/test_questions_doc.py` recomputes the County figures from its file, checks its fingerprint, and checks the page against the City facts):
- **City:** 7,033.7 sf; the front along Ithaca Rd is a curve of 8 edges, 75.8 ft; the side toward #104 is 92.12 ft; the rear is 69.51 ft; the jog is 10.35 ft (drawn as two edges); the long side is 101.13 ft.
- **County:** 6,900.4 sf; one straight front of 73.52 ft; 92.00, 68.86, 10.35 and 101.13 ft.
