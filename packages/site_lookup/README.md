# site_lookup

Type an address, get the site: the tax lot and its outline, which lot lines face a street, whether it's a
corner lot, the ground levels, and a zoning suggestion. Plain code asking public map services, no AI. Every
answer is a **suggestion with its source**, shown in the start box with its source and a Change button.

```
python -m site_lookup "106 Ithaca Rd, Ithaca, NY 14850"          # asks the live services, prints the facts
python -m site_lookup "106 Ithaca Rd, Ithaca, NY 14850" --json   # the full result, as the start box receives it
```

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
| **Street side and corner lot** | A lot line faces a street when it runs within 30° of the street's centerline and its midpoint is within half the right-of-way + 10 ft of it (tax-map lines sit a few feet off the right-of-way edge). A street counts with at least 10 ft of frontage. Corner lot is `yes`/`no`/`ask`: one street → `no`; two streets → `ask` (it looks like a corner lot, so the start box asks which line is the front). The address on a street the lot doesn't touch → needs review | City of Ithaca roads (with right-of-way widths, live only); NYS Streets as a fallback (width unknown → 50 ft assumed, noted) |
| **Ground** | The elevation at each lot corner and the centre, in feet above NAVD88. It's **today's** ground; finished ground is set in the start box | USGS 3DEP (1 m, the 2020 LiDAR here) |
| **Zone** | The City zoning polygon(s) under a grid of points inside the lot; more than one zone covering 2%+ of the lot → Gordium asks. Always a suggestion: the start box's "I confirm" tick is the architect's statement | City of Ithaca zoning map (online, informational; live only, never stored) |
| **Rezonings since the map** | `amendments.yaml`: ordinances adopted after the map's last edit. A lot on a street the ordinance names → needs review (Ord. 2025-12, Southside) | kept by hand |
| **Overlays** | Historic districts, gorge protection zones, secondary zones and landmark flags on the parcel. Not checked in this release, so any found → needs review | City of Ithaca layers (live only) |

## Each fact's shape

Every fact in `result["facts"]` is exactly `{value, source, confirmed_by, date}`, the shape the start box
stores, so a looked-up fact and a typed one are handled alike. `source` is a start-box label: `from tax map`
for the lot, `suggested by Gordium` for everything else. `confirmed_by` is always empty here: a lookup never
confirms anything. Beside each fact, `result["details"][name]` is `{status, reason?, note?, source_detail,
source_url}`: `status` is `suggested`, `needs_review` (something is doubtful; `reason` says what) or `ask`
(the lookup can't choose: a corner lot, two zones), and `source_detail` names the service asked. The result's `status` is
`found`, `not_found`, `multiple`, `outside_city`, `offline` or `error`, with a plain `message`; `asks` lists
the amber lines the start box shows.

## What a project keeps (licensing)

`result["snapshot"]` is what a project saves: the facts Gordium may keep, and for every request the source,
URL, date and SHA-256 of the answer, never the answer itself. Sources and what may be kept are listed in
`endpoints.yaml`:

- **Kept:** State and USGS data (public, no redistribution limit) and numbers Gordium computed.
- **Used live, never kept:** the City of Ithaca zoning and overlay layers ("may not be reproduced or
  redistributed without the express written consent") and the County address points ("please do not
  redistribute"). The snapshot records that they were used, when, and the answer's fingerprint.

Permission emails to the City and the County are on hold (Ben's call). Until then the zone stays a live
suggestion, and the start box's "I confirm" tick stays unticked until the architect ticks it.

## How we know it's right

`tests/test_lookup.py`, offline: the State and USGS answers recorded from the live services
(`tests/fixtures/capture.py`), and stand-in City layers built from numbers derived from them.

- **106 Ithaca Rd:** parcel 84.-2-6, 7,033.7 sf from the State Plane outline, 75.8 ft of frontage on Ithaca Rd
  (its 8-segment curve), an interior lot, ground 735–749 ft, zone suggestion R-1b, nothing confirmed.
- **109 Ithaca Rd:** touches Ithaca Rd and Mitchell St → a corner lot, asks for the front.
- **96 Ithaca Rd:** touches both streets too. The research's first test (a 3 ft margin) matched only Mitchell
  St, which looked like an address/street mismatch; with the 10 ft margin and the parallel rule the tax map
  shows lines along both Ithaca Rd and Mitchell St, so it's treated as a corner lot and Gordium asks.
- **A Town of Ithaca address** (953 Danby Rd) is refused; an unknown address is not found; offline is a plain
  state; a failing zoning map leaves the rest and asks for the district.
- **Synthetic checks:** an address on a street the lot doesn't touch, a lot in two zones, a Southside street,
  a historic district, County and State points 200 ft apart, a shallow lot whose side lines must not count as
  frontage.
- **Never kept:** the snapshot contains no City value (the zone is nowhere in it) and no answer bodies;
  fixtures contain no owner or mailing fields and only storable sources.
- A live check: `GORDIUM_LIVE=1 pytest packages/site_lookup`.

## Not yet

Wiring into the Rhino start box (after the start box PR lands); confirming the zone suggestion against the
City's official map; the Southside boundary as a polygon (it's only on the ordinance's map); more cities.
