# The City of Ithaca's non-residential districts: what is checked now, what later (2026-11-22)

**Purpose:** the inventory of every non-residential district in Chapter 325 and the zoning charts, where each one's regulations live, which have a rulebook now (the six B districts), and the plan for the rest.\
**For:** Ben deciding what comes next; engineers adding a district family; anyone asking why a lot in a given district gets no zoning check.\
**Kept current by:** the PR that adds a district's rulebook, or that finds a source this inventory doesn't list.

## Decision

The six B districts whose rules follow the residential chart pattern (a use list, then one bulk column of lot size,
width, height, coverage and yards) get a rulebook each, drafted by hand from the City's documents the way the
residential ones were: **B-1a, B-1b, B-2a, B-2d, B-4, B-5** (`5_zoning_rules/<district>.yaml`). Every other
non-residential district is written down below with where its regulations live, and is left for later: a lot there
still says the district has no rules in Gordium yet (the Setup form and the address lookup offer only districts that
have a rulebook).

## The inventory

Sources: Chapter 325 as downloaded 2026-10-19 (§325-4's list of districts, p.22-23) and the zoning charts of April
2026 (`1_source_documents/`); the City's zoning map's district codes, looked up 2026-11-22 (informational only).

| Family | Districts (§325-4 / chart / City map) | Where the regulations live | What's special | Now |
|---|---|---|---|---|
| Restricted, general and service business | B-1a, B-1b, B-2a, B-2d, B-4, B-5 | Chart p.4 (uses), p.5 (bulk, notes 1-9), p.15 (parking, loading); §325-8A, §325-16C, §325-16G (two-story minimum in B-1a, B-1b, B-2c, B-2d), §325-19 (transition yards; not in B-2d, §325-19D), §325-22 (motels), §325-15F (gasoline stations) | The same pattern as the residential chart; a minimum height (stories and feet) in B-1a, B-1b, B-2d; coverage note 7 (B-2a: 75% with parking within 500 ft) | **Rulebooks** |
| General business | B-2c | Chart p.4 (uses) only; §325-16G names it | In §325-4 and the use chart, but **no column on the bulk chart** (p.5) and not on the City's map | Later: no dimensions to check (open question below) |
| General business | B-2b | §325-4 only; on the City's map | **In no chart column at all** (uses or bulk) | Later: nothing in the charts to check (open question below) |
| Central business | CBD-50, CBD-60, CBD-85, CBD-100, CBD-120, CBD-140 (map also: CBD-52) | Chart p.4 (uses, one "CBD" column), p.5 (one column: height "see note 5", the sub-district's suffix; CBD-140 12 stories, note 4; coverage 100% note 8); §325-8D (DeWitt Park historic review, the West Green Street stepback, the Street Level Active Use Overlay); no loading (§325-8A(5), §325-21C) | One chart column for six sub-districts, the height from the district's name; the SLAUOZ active-use rule needs a storefront/ground-floor use the model doesn't carry; CBD-52 is on the map but not in the chart or §325-4 | Next (fits the pattern but needs a per-sub-district height and the overlay) |
| Special purpose | C-SU, I-1, P-1, U-1, MH-1 | Chart p.6 (uses), p.7 (bulk), p.16 (parking); Article VIII (C-SU, §325-44); §325-24 (industrial standards, I-1); §325-9B(1)(h) (P-1 near residential); §325-16C(4), §325-16D, §325-18C, §325-20J (U-1) | U-1's height is 175 ft but 15 ft over the adjacent residential limit within 200 ft (note 3); gorge areas A, B, C on a separate map (§325-16D); P-1 uses within 200 ft of residential need a special permit; MH-1 is mobile home parks | Later, one family at a time (each needs facts Gordium doesn't ask: distance to residential land, the U-1 map) |
| West End | WEDZ-1a, WEDZ-1b | Chart p.8 (uses and bulk), p.17 (parking); §325-16F, §325-20H | Height per story (12 ft a story, plus 5 ft cornice); coverage 100%/90% by lot width; view corridors of the West End Urban Design Plan 1999 | Later |
| Southwest | SW-1, SW-2, SW-3 | Chart p.9 (uses and bulk), p.17; §325-29.2 (building setback, minimum store size), §325-20I | A **maximum** front yard and a minimum building frontage (percent of the street frontage): form rules | Later (form-based) |
| Waterfront | WE/WF, CSD (Cherry Street), ND (Newman), MD (Market) | Chart p.10 (uses), p.11 (bulk), p.17; §325-8C (Lookout Point, flood channel no-build, stepback, sidewalk and tree lawn, building length) | Floor-to-floor story heights (note 4), build-to 10 ft from the sidewalk (note 8), rear yards from the top of the bank | Later (form-based) |
| Collegetown | CR-1 to CR-4, MU-1, MU-2 | Chart p.12 (uses), p.13 (bulk), p.17; Article IX (§325-45 to §325-45.4: form and activation requirements) | A form district: minimum height, green space, maximum front yard in MU-2, design standards | Later (form-based) |
| Southside form districts | (Ordinance No. 2025-12, §325-46; not in the April 2026 charts, not on the map yet) | `1_source_documents/ordinance_no_2025-12_southside_form_districts.pdf` | Adopted Nov 2025; rezones parts of some residential districts | Later (form-based), with the rezoning |
| Overlays | SHOD (§325-8E), SLAUOZ (§325-8D(3)), Adult Use (§325-29.1), PUD (§325-12), gorge protection (§325-16D), historic districts (Chapter 228) | Chart p.1 general note 4 lists them | They change the base district's rules | The address lookup shows the ones it finds; checked by hand (`not_checked_yet.yaml`) |

## What was built (the B districts)

- **Uses** (chart p.4): the 17 commercial uses the residential chart doesn't list were added to
  `4_term_definitions/uses.yaml` (retail store, restaurant, office, bank, hotel or motel, gasoline station, …), so
  the Setup form's Use dropdown lists each district's • uses first, then its SP ones ("not permitted by right"). A use
  the commercial chart doesn't list at all (a fraternity) fails, as in the residential districts (§325-8B(3)).
  R-3a's and R-3b's use rules, flags that let "every other listed use" through, now list their permitted uses, so a
  commercial use can't pass in them; their verdicts for the residential uses are unchanged.
- **Rules** per district: the use; the lot size by use (B-1a and B-1b: the multi-family note 2, +750 sf a unit past
  three, +500 sf a room let); a motel's 20,000 sf and 100 ft (§325-22A, stricter than the B-2d, B-4 and B-5 cells);
  the lot width; stories; the height with the §325-16C bonus; the minimum stories and height where the chart sets
  them; the coverage (B-2a: 50%, needs review up to note 7's 75%); the front, side and rear yards (note 9: rear at
  least 10 ft); the eaves (§325-18B); accessory buildings (§325-25); streams (§325-26); occupancy (§325-3B: one
  unrelated person outside R-1, R-2 and R-3); a home occupation's size.
- **Flags** (always needs review where they apply): the transition yards next to residential land (§325-19A, B;
  not in B-2d, §325-19D) on every lot, since Gordium doesn't know the neighbours' districts; parking and loading
  (chart p.15, §325-20, §325-21); accessory dwelling units (§325-28 checked by hand); motels' other standards
  (§325-22); gasoline stations (§325-15F); two primary buildings' yards (§325-7B).
- **A corner lot** in a B district measures no yard (needs review): §325-19C's two front yards are for residential
  districts only, and which street yard is a B lot's front yard isn't settled.
- **The chart reader** reads chart pages 4 and 5 into cells (`jurisdiction.yaml`'s district pattern now includes the
  B columns); page 15 is quoted (its wrapped cells and two "Retail store" rows aren't read into cells).

## How we know it is right

- `python -m rule_format`: every quote is the City's words on its lines, every number is in a cited source, every
  worked example comes out as stated.
- `packages/document_extraction/tests/test_b_districts_match_chart.py`: every p.4 mark decides the use rule (•
  passes, SP needs review, - fails) and every p.5 number is a limit some rule passes exactly at and fails just past,
  in each district's own column; the reader's B cells agree with the plain text, the wrapped rows read by hand
  (`test_cells_match_lines.py`).
- Three hand-worked designs (`test_data/test_sites/new_york/ithaca_city/scenarios/13_…` to `15_…`): a two-story
  B-2a shop with offices (complies), a B-1b office 1 ft under the 25 ft minimum (does not comply), a one-story B-2a
  store at 60% coverage (needs review) with 5 ft side yards (does not comply).
- `6_coverage_report/commercial_districts.md` (`commercial_coverage.yaml`): every rule and flag piece of Chapter 325
  against each B district.

## Open (research done, still unsettled)

Five questions are on the architects' page (`docs/questions_for_architects.md` §5.24 to §5.28): a motel's lot size in
B-4 and B-5 (chart 3,000 sf vs §325-22A 20,000 sf); the height bonus with no front yard required (B-2a, B-4); the
500 sf exception and §325-16G's two stories (B-1a, B-1b, B-2d); an ADU where the chart's cell is blank (B-4, B-5);
"-" on the parking chart (B-1a, B-1b, B-4, B-5). And for the City zoning office: **B-2b** (on the map and in §325-4,
in no chart column) and **B-2c** (on the use chart, not the bulk chart, not on the map): which regulations apply?
Searched: §325-4, §325-8, §325-16G, §325-9B(1)(o) ("B-2 Districts"), the April 2026 charts, the City's map codes.
