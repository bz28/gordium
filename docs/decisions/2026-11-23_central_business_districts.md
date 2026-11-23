# The City of Ithaca's central business districts: how the law reads, what is checked (2026-11-23)

**Purpose:** how Chapter 325 and the zoning charts regulate the six CBD districts downtown, the readings Gordium's CBD rulebooks rest on (each with its citation), and what is left to a person or to the City.\
**For:** engineers and anyone reading a CBD result; Ben deciding what comes next; the architects and the City zoning office, for the questions at the end.\
**Kept current by:** the PR that changes a CBD rulebook, or that finds a CBD source this note doesn't list.

## Decision

The six central business districts the charts name, **CBD-50, CBD-60, CBD-85, CBD-100, CBD-120 and CBD-140**, get a
rulebook each (`5_zoning_rules/<district>.yaml`), drafted by hand from the City's documents the way the B districts'
were (`2026-11-22_commercial_districts.md`). They share one chart column, so jurisdiction.yaml now says which
districts a column holds (`districts.shared_columns`), and each rulebook cites that column's cells as its own. Nothing
is guessed: what Gordium can't see (a storefront on the Commons, the historic review, the West Green Street stepback,
parking) is a flag, needs review. **CBD-52**, a code the City's online map gives six blocks of West State Street, is in
no chart and not in §325-4: it has no rulebook and is an open question for the City.

## How the law reads

Sources: Chapter 325 as downloaded 2026-10-19 and the zoning charts of April 2026 (`1_source_documents/`); the printed
zoning map of May 2026 and the City's online map (looked up 2026-11-23), informational only.

| Question | What the law says | Gordium's reading |
|---|---|---|
| Which districts? | §325-4 (p.22) lists "CBD Central Business" and "CBD-50 Central Business". The charts (p.4 uses, p.5 dimensions) give one column, headed "CBD-50, -60, -85, -100, -120, -140", with note 1: "See §325-8(D)". | Six districts, one column. The column's heading is the one list of them (`test_cbd_districts_match_chart.py` spells it out and holds it to jurisdiction.yaml). |
| CBD-52 | Not in §325-4, the charts, or the printed map's legend (May 2026, p.5, which colours those blocks like CBD-50). The online map codes the 300 and 400 blocks of West State Street (N Meadow St to N Albany St) "CBD-52". A 2019 proposal would have zoned them so (Ithacating, "News Tidbits 5/11/19"). | An open question for the City (questions §5.30). The address lookup shows CBD-52 as the map gives it, needs review, with the reason; never read as CBD-50 or as a 52 ft district. |
| Height | Chart p.5: "Height in feet: see note 5". Note 5: "Each of the CBD sub-districts have a maximum building height that corresponds with its suffix - for example CBD-50 has a maximum building height of 50 feet, CBD-100 has a maximum building height of 100 feet, etc." Stories: "- [fn4]"; note 4: "CBD-140 has a maximum building height of 12 stories." | Each rulebook's height is its name's number (50, 60, 85, 100, 120, 140 ft); CBD-140 alone has a story limit (12). The height is written in each rulebook as data, so the checker reads no district name. |
| The height bonus | §325-16C (p.47): "In any district" a building may exceed the height by up to 10% when "each required front, side and rear yard is increased one foot on the ground for each one foot of such additional height." | Applies in CBD. The CBD column requires no front or side yard; Gordium asks a building using the bonus for front and side yards of the extra height (the cautious reading, questions §5.25, the same as B-2a's and B-4's front yard). |
| Minimum height | Chart p.5: at least 2 stories and 25 ft, note 6 ("shall not apply ... where the new development ... does not exceed a footprint of 500 square feet"). §325-16G (p.48): "in the CBD-60, CBD-85, CBD-100, CBD-120, CBD-140, B-1a, B-1b, B-2c, and B-2d Zoning Districts, no primary use building shall be erected that is less than two stories", "notwithstanding anything to the contrary". | CBD-60 to CBD-140: two stories; a one-story building of 500 sf or less needs review (§5.26, as in B-1a, B-1b, B-2d). **CBD-50**: §325-16G doesn't name it, so only the chart's minimum holds, with note 6: 500 sf or less is exempt. 25 ft (§325-8A(15)) with the 500 sf exemption everywhere. |
| Lot, coverage, yards | Chart p.5: lot size "-" for every use (a motel's cell blank); width 10 ft; coverage 100%, note 8 "Except as required for rear yard or side yard, as applicable"; front and side yards "-"; rear 10 ft. | No lot-size rule (a motel is held to §325-22A's 20,000 sf and 100 ft, the chart's 10 ft reviewed: §5.24); width 10 ft; coverage 100%; rear yard 10 ft; no front or side yard rule. A corner lot measures no yard (§325-19C's two front yards are residential only), so its rear yard needs review. |
| Uses | Chart p.4's CBD column: • 25 uses (a parking garage among them), SP 6 (cemetery, public utility, neighborhood commercial facility, hospital, bed-and-breakfast inn, redemption center), - 3 (gasoline station, motor vehicle sales, the printing/plumbing shop). | As the B districts: • passes, SP needs review, - and any use the chart omits fails. |
| §325-8D(1) | "The CBD-50 Zone is located within the DeWitt Park Historic District. New construction in any zone that is located within a designated local historic district is subject to review and approval by the Ithaca Landmarks Preservation Commission". | CBD-50: a flag on every lot (`historic_review`). Other CBD lots in a historic district: the address lookup's historic-district overlay, checked by hand (`not_checked_yet.yaml`). |
| §325-8D(2) | In "the portion of the CBD-85 District directly fronting the 100 block of West Green Street, the front façade ... must contain a stepback of between 15 feet to 25 feet after the first two to four stories". | CBD-85: a flag on every lot (`green_street_stepback`): Gordium doesn't know a lot's block or measure a façade's stepback. |
| §325-8D(3) | Properties with a storefront on the Primary Commons, and every property in the Mandatory Street Level Active Use Overlay Zone (July 2017 map), "must contain an active use on the street level"; "Nonactive uses ... include ... any residential uses or commercial activities that have blocked windows." | A flag on every CBD lot, whatever its main use (`active_street_level_use`): the law reaches the street-level part of any building there, and Gordium knows neither the storefronts nor what each floor holds. |
| Loading | §325-8A(5) (p.24): the loading column applies "except for properties located in any CBD district"; §325-21B (p.64) the same; §325-21C: "There shall be no off-street loading requirement for any properties located in any CBD zoning district." Chart p.15: "-". | Answered by the law: no loading flag in any CBD rulebook; the coverage audit marks §325-21 not applicable with §325-21C's words. |
| Parking | §325-8A(4): "The off-street parking spaces listed in this column shall be provided". Chart p.15's CBD column: "-" on every row, "Other Uses" too (where B-2A and B-2D say "See §325-20"). §325-20D(3)(b) footnote 2 (p.55): "See also the District Regulations Chart for districts in which off-street parking is not required." | The strongest reading is none required downtown, but the chart never says which mark means so: a flag on every CBD lot (`parking`), the same open question as the B districts' "-" (§5.28, its research now quoting footnote 2). |
| Transition yards | §325-19A, B: "a lot in a business or industrial district" next to residential land. §325-4 calls CBD "Central Business". | A flag on every CBD lot (`transition_yards`), as in the B districts. |

## What was built

- **Rulebooks:** six files, 20 or 21 entries each: 13 rules in each (14 in CBD-140, its stories) and 7 flags in each (8 in CBD-50, its historic review, and in CBD-85, its stepback). Every quote verified against the PDF text, every number in a cited source, every worked example coming out as stated (`python -m rule_format`).
- **The shared column:** `jurisdiction.yaml districts.shared_columns` ("Central Business" → CBD-50 ... CBD-140), read by rule_format (a rulebook may cite a cell of a column that holds its district) and by the coverage audit.
- **The address lookup:** the City map's CBD codes used as written; CBD-52 needs review with its reason (`site_lookup/adapters/ithaca_city/names.yaml`, `unresolved`).
- **Coverage:** `central_business_coverage.yaml` and its table, `6_coverage_report/central_business_districts.md`: every rule and flag piece against each CBD district; a "-" decision names the CBD column's own cell, whose value the audit checks.
- **Two fixes in the checker found on the way** (`design_checker/check.py`): the plan's red above the height limit took the last building-height row, so in a district with a minimum height (B-1b, B-2d, CBD) the minimum's "complies" hid a height failure: it now takes the worst maximum-height row. And the Setup form's options keep each condition's verdict and each rule's names for one answer (21 districts made them 40% slower; now 5 times faster than before, the same answer).

## How we know it is right

- `packages/document_extraction/tests/test_cbd_districts_match_chart.py`: every p.4 mark decides the use rule in each CBD rulebook; every p.5 number is a limit some rule passes exactly at and fails just past; note 5's height is each name's number and note 4's 12 stories CBD-140's alone; every "-" is no limit; §325-16G's two stories hold in CBD-60 to CBD-140 and not CBD-50; no rulebook has loading.
- `packages/design_checker/tests/test_cbd_districts.py`: the Setup form lists the six districts (never CBD-52) and each one's uses by its marks; each use-scoped flag reaches every use its law covers; a CBD corner lot passes no yard; the audit's own words carry no B district's; the red above the height plane.
- Three hand-worked designs (`test_data/test_sites/new_york/ithaca_city/scenarios/16_…` to `18_…`): a five-story CBD-60 building of shops and apartments (complies; three flags); a six-story CBD-60 office 4 ft over its 60 ft on the street line (does not comply: the bonus needs a 4 ft front yard); a seven-story CBD-85 building on West Green Street's 100 block (complies; the stepback a flag).

## Open

On the architects' page (`docs/questions_for_architects.md`): the CBD districts join §5.24 (a motel's lot size), §5.25
(the height bonus with no front or side yard required), §5.26 (CBD-60 to CBD-140: 500 sf and §325-16G), §5.27 (an
ADU where the chart's cell is blank) and §5.28 (parking "-"). For the City zoning office, §5.30: **CBD-52**, adopted or
not, and its rules.
