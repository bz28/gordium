# site_lookup

Type an address, get the site: the tax lot and its outline, which lot lines face a street, whether it's a
corner lot, the ground levels, and a zoning suggestion. Plain code asking public map services, no AI. Every
answer is a **suggestion with its source**, shown in the start box with its source and a Change button.

```
python -m site_lookup "106 Ithaca Rd, Ithaca, NY 14850"          # asks the live services, prints the facts
python -m site_lookup "106 Ithaca Rd, Ithaca, NY 14850" --json   # the full result, as the start box receives it
```

**One folder per place.** Shared: `geometry.py` (plane geometry in feet) and `http.py` (asking a service). Each
place's own lookup is `site_lookup/adapters/<place>/`, chosen by the place's `jurisdiction.yaml` (`adapters:
lookup:`) through `adapter(place)`: the City of Ithaca's is `adapters/ithaca_city/` (`lookup.py`, `sources.py`,
`suggest.py`, `context.py`, and its data: `endpoints.yaml`, `names.yaml`, `amendments.yaml`). Its place's values
(the SWIS code, EPSG:2261, the address tail, its name in messages) come from those settings. A place with no
settings, or no adapter folder, is a plain error. Everything below describes the City of Ithaca's.

```
106 Ithaca Rd, Ithaca, NY 14850: found
  parcel       500700-84.-2-6               [suggested] · suggested by Gordium · NYS Tax Parcels Public
  lot          7,034 sf, 15 corners          [suggested] · from tax map · NYS Tax Parcels Public (approximate ±2 ft)
  street_side  ITHACA RD, 75.8 ft of frontage [suggested] · suggested by Gordium · City of Ithaca roads
  corner_lot   no                            [suggested] · suggested by Gordium · City of Ithaca roads
  ground       734.8–749.0 ft (14 points)    [suggested] · suggested by Gordium · USGS 3DEP · today's ground, an estimate
  zone         R-1b                          [suggested] · suggested by Gordium · City of Ithaca zoning map, last edited 2024-09-26
```

## What each fact is, and where it comes from

| Fact | How | Source |
|---|---|---|
| **Address point** | The State's address points (score ≥ 90); the County's address points as a cross-check (more than 50 ft apart → needs review). Never the Census geocoder: it places addresses along the street, 46 ft off at 106 Ithaca Rd | NYS Geocoder; Tompkins County TCAddress (live only) |
| **Parcel and lot outline** | The tax parcel containing the point, asked for in EPSG:2261 (NY State Plane, **US survey feet**); area and lengths computed by Gordium, never read from the service, and converted to Gordium's international feet (× 1200/3937 ÷ 0.3048 = 1.000002: 0.03 sf on a 7,000 sf lot). The outline is stored relative to its centroid, with the centroid's State Plane position (survey feet). Source "from tax map": downstream that means ±2'-0" and the 2 ft starting-house margin | NYS Tax Parcels Public (the State's copy of the County tax map, storable); City of Ithaca tax parcels as a live fallback and for City-only flags |
| **City only** | The parcel's SWIS code must be 500700 (City of Ithaca). The State names both the City and the Town of Ithaca "ITHACA", so the code decides. Anything else is refused | NYS Tax Parcels |
| **Street side and corner lot** | A lot line faces a street when it runs within 30° of the street's centerline and its midpoint is within half the right-of-way + 10 ft of it (tax-map lines sit a few feet off the right-of-way edge). A street counts with at least 10 ft of frontage. Corner lot is `yes`/`no`/`ask`: one street → `no`; two streets → `ask` (it looks like a corner lot, so the start box asks which line is the front). The address on a street the lot doesn't touch → needs review. A City road's name is read through `names.yaml`'s exact table first ("E STATE ST / M.L.K. JR ST" is E State St; one direction of a divided street, "W CLINTON ST EB LANE", is W Clinton St); a name not listed is used as the layer writes it. Road widths unknown (the State fallback, or a City road near the lot without one) → a 50 ft right-of-way is assumed, the street side needs review and the corner lot is `ask` (a wider second street could be missed) | City of Ithaca roads (with right-of-way widths, live only); NYS Streets as a fallback |
| **Ground** | The elevation at each lot corner and the centre, in feet above NAVD88. It's **today's** ground; finished ground is set in the start box | USGS 3DEP (1 m, the 2020 LiDAR here) |
| **Zone** | The City zoning polygon(s) under a grid of points inside the lot; more than one zone covering 2%+ of the lot → Gordium asks. The map's code is matched exactly against `names.yaml`: a residential district as the rulebooks write it is used as is, a listed alias is renamed (the map's `R-U` is the rulebook's `RU`, as §325-4 and the chart write it two ways), and any other code is shown as the map gives it and needs review (never matched by likeness). Always a suggestion: the start box's "I confirm" tick is the architect's statement | City of Ithaca zoning map (online, informational; live only, never stored) |
| **Rezonings the map may not show** | `amendments.yaml`: ordinances the City adopted, each with a padded box around the districts on its map (Ord. 2025-12 Southside: from the May 2026 Southside Form District Map, p.9). A lot touching the box, or on a street the ordinance names → needs review. An ordinance without a box → every City lot needs review. A row is cleared only by `map_shows_since`, set by hand after checking the online map shows the rezoning; the map's own edit date never clears one (any edit moves it) | kept by hand |
| **Overlays** | Historic districts, gorge protection zones, secondary and overlay zones and landmark flags on the parcel, and the overlays the zoning map draws over the districts (`names.yaml`: SHOD, SLAUOZ, the Adult Use Overlay Zone; an overlay is never taken for the district). Each is looked for on the lot and 2 ft around it (the tax map's tolerance), and counts however little it touches: the zoning map's overlays by their outlines (never by a share of the lot), the historic and gorge areas by the layer's own query, an area with no name included. The parcel's flags count unless they say `NO` (read 2026-11-11 the City also writes `NR` and `chk`, and leaves a few blank: each is said). A lot the zoning map doesn't cover (a point more than 5 ft inside the lot off the map: the two maps disagree by up to 2.3 ft along lot lines), or a layer answering without a feature list, can't be said to have none. Not checked in this release, so any found, or any that couldn't be looked for → needs review | City of Ithaca layers (live only) |
| **Flood zone** (in the overlays) | FEMA's flood zones touching the lot and 2 ft around it (the tax map's tolerance), asked without geometry (FEMA's polygons run to 265,000 points). The one "none" is FEMA's Zone X, *area of minimal flood hazard* (SFHA_TF `F`), matched exactly, with the whole lot inside one such area (`within`) and no pending or preliminary new map over it. Any other zone touching any part of the lot is named and needs review: every Special Flood Hazard Area (A, AE and its floodway, AH, AO, AR, A99, V, VE), shaded Zone X (0.2% chance, or 1% chance under a foot deep), Zone D, any value not listed. No zone, a lot across two areas, a new map on the way, or FEMA not answering → "couldn't tell / couldn't check", needs review. Definitions: FEMA's glossary ([Flood Zones](https://www.fema.gov/about/glossary/flood-zones), [Zone D](https://www.fema.gov/glossary/zone-d), read 2026-11-11) | FEMA National Flood Hazard Layer, its pending and preliminary maps (federal, stored) |

**The overlays fact's one positive answer.** The overlays fact is `suggested` with an empty list only when every
overlay source answered and every one said none, on a lot nothing is doubtful about. The start box turns exactly that
(from a live lookup that draws its lot, never a saved one) into the lot fact `overlays_none_found`, with the lot
outline it was found for; the check then leaves the "Overlays · not in this release" row out while the lot is still
that outline (`design_checker.present.overlays_cleared`). The City's layers have no freshness date: their live answer
on the lookup's day is taken as the City's current map (as the zoning suggestion is), and the finding keeps that day.

**Incomplete evidence is never "suggested".** A second address match that couldn't be placed on a parcel,
elevations missing at some corners, road widths unknown (a second street could be missed: the corner lot is
asked), the City's parcel flags unavailable: each makes its fact need review, with the reason. When two things
apply, the strongest status wins (ask > needs review > suggested) and the reasons add up. A lot that may be
the wrong one (a doubtful address point), or the largest piece of a parcel in several pieces, makes every fact
worked out on it need review too: street side, corner lot, ground, zone and overlays.

## Each fact's shape

Every fact in `result["facts"]` is exactly `{value, source, confirmed_by, date}`, the shape the start box
stores, so a looked-up fact and a typed one are handled alike. `source` is a start-box label: `from tax map`
for the lot, `suggested by Gordium` for everything else. `confirmed_by` is always empty here: a lookup never
confirms anything. Beside each fact, `result["details"][name]` is `{status, reason?, note?, source_detail,
source_url, source_keys}`: `status` is `suggested`, `needs_review` (something is doubtful; `reason` says
what) or `ask` (the lookup can't choose: a corner lot, two zones); `source_detail` names the service asked and
`source_keys` every `endpoints.yaml` source the value was worked out from. Statuses only ever go up (ask >
needs review > suggested) and reasons add up. The result's `status` is
`found`, `not_found`, `multiple`, `outside_city`, `offline` or `error`, with a plain `message`; `asks` lists
the amber lines the start box shows.

## What a project keeps (licensing)

`result["snapshot"]` is what a project saves: for every request the source, URL, date and SHA-256 of the
answer (never the answer itself), and each fact as far as **its own source's** `store` in `endpoints.yaml`
allows (`details[name]["source_keys"]` lists every source the value was worked out from, and the strictest
one decides; a reason worked out from another source, like the County point's distance, follows that source's
rule):

- **Kept:** State, USGS and FEMA data (public, no redistribution limit).
- **Numbers only:** a lot from the City's parcel layer (when the State's is down) keeps its area and side
  lengths, never its outline, position or parcel id.
- **Used live, never kept:** the City of Ithaca zoning and overlay layers ("may not be reproduced or
  redistributed without the express written consent") and the County address points ("please do not
  redistribute"). The snapshot records that they were used, when, and the answer's fingerprint.

Permission emails to the City and the County are on hold (Ben's call). Until then the zone stays a live
suggestion, and the start box's "I confirm" tick stays unticked until the architect ticks it.

## How we know it's right

`tests/test_lookup.py`, offline: the State, USGS and FEMA answers recorded from the live services
(`tests/fixtures/capture.py`; `capture.py --flood` added FEMA's to the fixtures captured before the flood lookup,
nothing else re-asked), and synthetic stand-ins for the City layers (every street 60 ft wide, the map
last edited 2025-01-01, 106's zone from Gordium's own test site): nothing from a City or County layer is in
the fixtures. A test checks every fixture and snapshot against `endpoints.yaml`.

- **106 Ithaca Rd:** parcel 84.-2-6, 7,033.7 sf from the State Plane outline, 75.8 ft of frontage on Ithaca Rd
  (its 8-segment curve), an interior lot, ground 735–749 ft, zone suggestion R-1b, nothing confirmed; outside
  the Southside area.
- **109 Ithaca Rd:** touches Ithaca Rd and Mitchell St → a corner lot, asks for the front.
- **96 Ithaca Rd:** touches both streets too. The research's first test (a 3 ft margin) matched only Mitchell
  St, which looked like an address/street mismatch; with the 10 ft margin and the parallel rule the tax map
  shows lines along both Ithaca Rd and Mitchell St, so it's treated as a corner lot and Gordium asks.
- **Flood:** 106, 109 and 96 Ithaca Rd are wholly in Zone X, minimal flood hazard, no new map pending (FEMA,
  2026-11-11): no overlay. 601 Hancock St is in Zone AE: named, needs review. Every other zone, a partial overlap,
  no zone, two areas, a pending or preliminary map, FEMA down, timing out or answering oddly: needs review.
- **A Town of Ithaca address** (953 Danby Rd) is refused; an unknown address is not found; offline is a plain
  state; a failing zoning map leaves the rest and asks for the district.
- **Synthetic checks:** an address on a street the lot doesn't touch, a lot in two zones, a Southside lot on a
  street the ordinance doesn't name (S Plain St), a two-zone lot on a Southside street (still asks), missing
  elevations, unknown road widths, the City's parcel layer down, a second address match with no parcel,
  a historic district, County and State points 200 ft apart, a shallow lot whose side lines must not count as
  frontage.
- **Never kept:** the snapshot contains no City value (the zone is nowhere in it) and no answer bodies;
  fixtures contain no owner or mailing fields and only storable sources.
- A live check: `GORDIUM_LIVE=1 pytest packages/site_lookup`.

## The context map (the neighbourhood around the lot)

`site_lookup.adapters.ithaca_city.context.context(lot_ring, http, half_size_ft=750)` asks for everything in a 1500 ft × 1500 ft square
centred on the lot, the way an architect's site context drawing shows it. Drawing only: nothing in it is ever
measured or checked.

| Layer | Source | Store | In the customer's file? |
|---|---|---|---|
| Neighbouring parcels (the lot's own left out) | NYS Tax Parcels Public (only SWIS and print key asked for: never owner, mailing or value fields) | raw | yes, as locked curves |
| Street centerlines | NYS Streets | raw | yes, as locked curves |
| Building footprints (each with its id; Microsoft's, under the ODbL, left out) | NYS Building Footprints (in Ithaca: Tompkins County ITS GIS Division, 2014) | raw (Ben's decision, 2026-10-21) | yes, as editable outlines (no heights), with their credit and date |

Each layer is asked on its own (one service down leaves the others), page by page (`resultOffset`, OBJECTID order,
a 5,000-feature cap that says so), and clipped to the square. Coordinates are Gordium's feet from the lot's origin,
so the lookup's placement in the model applies unchanged. The `snapshot` keeps, per layer, its source and status (and
its count only if the source may be kept), and for every request the URL, date and SHA-256, never an answer; a
live-only source is only named.

106 Ithaca Rd (live, 2026-10-20): 229 neighbouring parcels, 38 street pieces, 322 footprints, 3 requests,
about 1 s, 160 KB. In CI: `tests/fixtures/106_ithaca_rd_context.json` (the State's parcels, streets and footprints,
175 KB, recorded 2026-10-21 by `capture.py`). The live-only machinery (a source that may not be kept, shown on screen
and never saved) stays for any such source; its tests switch the footprints back to store: none. Tests:
`tests/test_context.py`; the Rhino side's in `design_checker/tests/test_context_box.py`.

## Address type-ahead (suggest.py): which service, and why

The start box's list of addresses as the architect types (`suggest.suggest`, run by
`python -m design_checker.lookup_box --suggest "106 Itha"`). Researched 2026-10-26; every source read that day:

| Service | City-only? | Terms | Verdict |
|---|---|---|---|
| NYS ITS geocoder `suggest` (`.../NYS_Geocoder/GeocodeServer`, capabilities "Geocode,ReverseGeocode,Suggest") | No: every result says City "Ithaca", Town and Cayuga Heights alike; `searchExtent` is only a box | A disclaimer only ("The User accepts the Data provided 'as is'"; https://gis.ny.gov/nys-geocoding-service); NYS says suggest is meant for type-ahead | Not used: each suggestion would need its own City check |
| Tompkins County address points (TCAddress) | Yes, by `MUNICIPALI = 'CITY OF ITHACA'` | "Please do not redistribute data to a third party without permission from Tompkins County GIS" (its ArcGIS item's licenseInfo) | Not used: showing it to architects may count as redistribution; would need the County's permission |
| **City of Ithaca addresses** (`Address_Labels/FeatureServer/0`, "AddressSearchandLabels", 6,588 addresses) | **Yes: City addresses only** | Credit only: "Data contained in this product was originally produced by the GIS Program, City of Ithaca, NY. The originator does not warrant the accuracy or completeness of the information portrayed by the data." (item de917e8fea3c4377808aff5522d4170b, licenseInfo) | **Used** (`city_addresses` in endpoints.yaml, `store: none`, the credit kept with it) |

It covers about 99% of the County's City addresses (6,500 in both; 88 only in the City's, mostly half numbers; 55
only in the County's). A suggestion is only typing help: the address picked is looked up as any typed address is
(the State geocoder, then the tax parcel's SWIS code decides City or Town), so nothing about the lot ever rests on
a suggestion. Asked: `UPPER(FULL_ADDRE) LIKE '<typed, in capitals>%'`, distinct, at most 8, in order. A direction
after the number ("North") and a street-type word ("Road", "Court") may be the City's short form ("N", "RD") or part
of the street's own name ("101 SOUTH ST", "102 E COURT ST"), so both spellings are asked for, as typed first, OR-ed
(at most 8 spellings); a dot after a letter is dropped ("N." is "N"; "106.5" keeps its dot); a finished last word
matches that whole word only; another town after a comma ("…, Dryden") gets no suggestions. Nothing is stored (tests use hand-written
stand-in addresses, `tests/test_suggest.py`). Found on the way: endpoints.yaml's `geocoder.terms` link is the
State's "Legacy Address Geocoder" page (retired after October 2026); the current page is
https://gis.ny.gov/nys-geocoding-service (the service URL itself is already the current one).

## Not yet

Wiring into the Rhino start box (after the start box PR lands); confirming the zone suggestion against the
City's official map; the Southside area as the districts' own outline rather than a padded box; more
cities.
