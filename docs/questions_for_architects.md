# Questions for the architects

Open questions. Remove each one once answered (and record the answer where it belongs).

## About their 106 Ithaca Road example
1. Their lot is 6,674.5 sf as drawn (6,674 in their spreadsheet); the city's tax parcel is ~7,034 sf with a curved street side. Where did their lot outline come from, and is there a survey? (Zone is confirmed R-1b, no overlays, not historic, not in a flood zone.)
2. Do they agree with `discrepancies_with_architects.md`? Especially the 🔴 items.
3. Rhino model: the building sits ~76 ft off the lot, and the rear setback is 20 ft. The rule requires 25% of the average side lot line (§325-8A(14)(a)): 23.7 ft if the 90.28 and 99.37 ft lines are the side lot lines (see the side lot line question below), and at least 22.6 ft under any reading. Intended (a test) or mistakes?

## About definitions (from `regulations/.../4_term_definitions/definitions.yaml`)
4. **Lot area** isn't defined in Chapter 325. Should we use the area inside the lot lines from a survey? What if there's no survey (the tax map can differ)?
5. **Lot width** is "frontage measured on a public right-of-way". On a curved street (like 106 Ithaca Rd), is that measured along the curve or straight between the corners?
6. **Lot depth** for the rear yard is the average of "the two side lot lines". On a lot with a jog (106 Ithaca Rd's 10.47 ft segment), which lines are the side lot lines?
7. Please read the quoted city text and the open questions of each definition in `definitions.yaml`. Several are interpretation questions only you can answer (how "average height" of a pitched roof is taken, how the grade plane is averaged, whether garages and overhangs count toward coverage, whether yards are measured to the wall or the eave, which entrance is the main entrance).

## About scope
8. Is the NYS Building Code (Chapter 5) needed in the first test, or only zoning?
9. What other documents do they check that aren't on their list?
10. Can they hand-check the rules for 2–3 more districts (answer keys)?
11. Do they have past Ithaca projects with known city decisions (permits, zoning board decisions) we can use to test our rules against real outcomes?
12. Please review `how_rules_are_checked.md`, especially "Choices for the architects to confirm".

## About how they work
13. How long does a zoning check take them today?
14. Their setup: Rhino version, Mac or Windows, plugins.
15. How far around the site should the model show neighbours? (Their model uses ~400 ft each way.)
