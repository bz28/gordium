# Where the address lookup's data comes from, and what we may keep (2026-10-20)

**Purpose:** which public map services the address lookup asks, who owns each, what Gordium may store from each, and when we need written permission.\
**For:** Ben (business and licensing decisions), engineers working on the address lookup, anyone asking "is this data ours to keep?"\
**Kept current by:** whoever adds or changes a source in `packages/site_lookup/site_lookup/adapters/ithaca_city/endpoints.yaml` (in that PR), and Ben when a permission answer comes back.

The **address lookup** is the **Look up** button in the start box: it asks public map services about a typed address and fills in the lot, the street side, the ground and a zoning suggestion (package `site_lookup`, PR #16; in the start box from PR #19). Each source has a **store level**, what a saved project may keep from it:

| Store level | What a project keeps |
|---|---|
| **raw** | The service's answer itself |
| **derived** | Only numbers Gordium worked out from it (an area, a length), plus the link, date and [fingerprint](../glossary.md#fingerprint) of the answer |
| **none** | Nothing from the answer; only its link, date and fingerprint. The data is used live and thrown away |

*Redistribution* means handing someone else's data on to a third party; several of these licences forbid it.

## Decision

1. **City and County data are used live, never stored.** The address lookup asks the City of Ithaca and Tompkins County services each time, shows the answer, and keeps only the link, the date and a fingerprint of what was used. The one partial exception is the City tax parcels, a fallback for the lot outline: only numbers Gordium computes from them (area, lengths) may be kept, never the outline, positions or parcel ids.
2. **State and federal data may be stored** (NYS Geocoder, NYS Tax Parcels, NYS Streets, USGS elevations): they are published for reuse without a redistribution limit.
3. **A value the architect vouches for is saved as their own statement.** For example "R-1b, I confirm" is saved with the source "confirmed by you · suggested by City map", not as City data.
4. **The rule is enforced by code, not memory:** each source's `store` level lives in `endpoints.yaml`; a fact worked out from several sources follows the strictest one; a test scans what a project saves.

## The sources

Copied from `packages/site_lookup/site_lookup/adapters/ithaca_city/endpoints.yaml` on the `site-lookup` branch (PR #16). That file is the source of truth; if this table and the file disagree, the file wins and this table is fixed.

| Source | Question it answers | Owner | May we store it? | Terms |
|---|---|---|---|---|
| NYS Geocoder (address points) | Where is this address? | NYS ITS Geospatial Services | raw | [gis.ny.gov/nys-geocoding-service](https://gis.ny.gov/nys-geocoding-service) (checked 2026-10-26; the earlier gis.ny.gov/address-geocoder is now the "Legacy" page, retired after October 2026) |
| Tompkins County address points (TCAddress) | Cross-check of the address point (more than 50 ft apart → needs review) | Tompkins County GIS Division | none | Stated on the service: "Access: Open. Please do not redistribute data to a third party without permission from Tompkins County GIS." |
| NYS Tax Parcels Public | Which tax lot, and its outline ("from tax map", ±2 ft) | NYS ITS Geospatial Services (from Tompkins County Real Property) | raw | [gis.ny.gov/parcels](https://gis.ny.gov/parcels) |
| City of Ithaca tax parcels | Fallback lot outline; City-only parcel flags | City of Ithaca GIS Program (from Tompkins County Assessment) | derived (numbers only) | The service's attribution: amended by the City GIS Program from a County Assessment file; accuracy not warranted. No reuse terms published |
| City of Ithaca roads | Which lot lines face a street; corner lot? (centerlines with right-of-way widths) | City of Ithaca GIS Program | none | No terms published on the service; treated as City data |
| NYS Streets | Fallback street centerlines when the City roads can't answer | NYS ITS Geospatial Services | raw | [NYS GIS clearinghouse](https://gis.ny.gov/) |
| City of Ithaca zoning map (online) | Which zone the lot is in (a suggestion until the architect's own tick, "I confirm") | City of Ithaca GIS Program / Planning | none | Stated on the layer: "Do not use this data for determinations of zoning." "May not be reproduced or redistributed without the express written consent of the originator." |
| City of Ithaca historic districts | Is the lot in a historic district? (not checked yet → needs review) | City of Ithaca GIS Program | none | No terms published on the service; treated as City data |
| City of Ithaca gorge protection zones | Is the lot in a gorge protection zone? (not checked yet → needs review) | City of Ithaca GIS Program | none | No terms published on the service; treated as City data |
| USGS 3DEP elevation (2020 LiDAR here) | Today's ground level at the lot corners | U.S. Geological Survey | raw | "Free of charge and without use restrictions" ([USGS 3DEP](https://www.usgs.gov/3d-elevation-program)) |

## When permission emails become necessary

Today every lookup runs on the architect's own computer, straight to the public services, so the City and County data never pass through anything of ours. That changes **before we sell Gordium with lookups passing through a Gordium server**: a server that fetches City or County data and hands it on to customers could count as redistribution, which the zoning map's and the County's terms forbid without consent. At that point either:

- **ask first:** send the permission emails to the City GIS Program and Tompkins County GIS (drafted; Ben is holding them), or
- **stay direct:** each customer's copy of Gordium keeps querying the public services itself, and our server never touches City or County data.

## Why

- The City's zoning layer says in so many words that it is not for zoning determinations and may not be redistributed. Using it live, as a *suggestion* that needs the architect's own tick ("I confirm"), respects both.
- Storing only what a licence allows means a saved project can be shared with a client or a consultant without us redistributing anything.
- State and federal data are public for reuse, so keeping them makes a project reproducible later.

## What we rejected

- **Zoneomics** (a commercial zoning data service): its licence forbids redistribution, so its answers could not appear in a customer's project or report.
- **Storing the City's answers "just for the project"**: still a copy of City data handed to whoever receives the project file.
- **The US Census geocoder:** it places an address along the street rather than on its lot (46 ft off at 106 Ithaca Rd).

## Consequences

- A project re-opened later asks the City services again; if they are down, the facts show "needs review" until they answer or the architect types the value.
- The zone is never "known" from the map alone: the architect's **I confirm** tick is what the checker uses.
- **One County file is kept on purpose:** the 106 Ithaca Rd test site keeps the County's `Parcels_Public` outline as evidence for the architects' questions (`test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/gis/`, PR #11). That is a different County layer from the address points, its terms set no reuse limit, and it is test evidence, not lookup data.
- **Open item (Ben to decide):** The City's parcel outline for 106 Ithaca Rd (`gis/city_tax_parcel_2026-10-20.json`) was committed in PR #11's early history (commit 43cd167) before the store rule existed, and later removed (1f990dd). It is still in the git history. Ben decides whether to purge it (rewriting history) or leave it.

## How this compares with an architect's due diligence

What an architect looks into before designing on an Ithaca lot, and where Gordium stands on each.

| Due-diligence step | Gordium today |
|---|---|
| Read the law: Chapter 325 of the City Code (via eCode360) | ✓ The whole chapter, quoted word for word with page and line (`regulations/.../1_source_documents`) |
| The District Regulations Chart (the zoning numbers) | ✓ Read by code, cell by cell |
| The official adopted zoning map | Partly. The online City map is shown only as a **suggestion**; the adopted map wins, and the zone needs the architect's own tick ("I confirm") |
| Recent ordinances not yet in the online code or map | ✓ A hand-kept list (`amendments.yaml`, e.g. the 2025 Southside rezoning); a lot it may touch needs review |
| Zoning Administrator and Board of Zoning Appeals interpretations | ✓ In the research behind each open question (e.g. Appeal #3202 on lot depth) |
| Boundary survey | Partly. The tax-map lot is used (±2 ft, judged at the worst case) until the architect loads a survey |
| Topographic survey | Partly. USGS LiDAR ground levels, good enough for early design only |
| Historic district and gorge protection zone | ✓ Looked up; not yet checked, so they show "needs review" |
| FEMA flood zone | ✓ Looked up (FEMA's National Flood Hazard Layer, and its pending and preliminary maps; federal data, stored in the fixtures); not yet checked, so a lot in or near a flood zone shows "needs review" (2026-11-11) |

**Gaps:**

- **FEMA flood zones:** looked up since 2026-11-11 (the flood rules themselves are not checked yet).
- **Easements and deed restrictions:** not in any public map; they must come from the architect (title report, survey).
- **The zoning office is the final authority.** Gordium's readings of unclear law are shown as readings to confirm; the questions process (`docs/questions_for_architects.md`) is how they reach the architects and the City.

## Date and status

- **Date:** 2026-10-20
- **Status:** decided (coordinator, for Ben). Enforced in PR #16 (`site_lookup`); applied in the start box by PR #19. Open: the history purge above, and the permission emails (held by Ben).
