# Light run: one real address per residential district

`expected.yaml`: for each of the nine residential districts, one ordinary City of Ithaca lot, looked up with
`site_lookup` on 2026-10-27, and what Gordium must show for it, worked out by hand from the law (queue item 12):

- **the start box:** the district, the tax-map lot (area, frontage, street), corner lot no, no overlays;
- **the largest legal house:** which rule limits it (lot coverage at the worst-case tax-map lot, or the yards), and
  that after Draw no rule fails and every needs-review row says why;
- **a nudge:** the house moved toward the street until its front yard is 3 ft short of the minimum (past the ±2 ft
  tax-map tolerance), and exactly the front-yard rule must fail, showing those numbers.

What the Rhino script claims (pass/fail per site): the zone, corner lot no, the drawn lot area, no fail after Draw
with every needs-review row giving a reason, and for the nudge the measured front yard, the row's proposed and
required values, and that only the front yard fails. The rest (frontage, street, overlays, the largest house's
limiting rule, the lot size and depth) is recorded beside these expected values for a person to compare.

`lookups/<district>.json` is each lookup's snapshot: what `site_lookup` lets a project keep (the State's tax-map
outline and the USGS ground; the City's zoning, roads and overlays and the County's address points are used live and
never stored, per their terms). How the lots were picked, and the tax-map rule used for the worst cases, are at the
top of `expected.yaml`.

Run in Rhino by `apps/rhino_plugin/tests/light_run_in_rhino.py` (Lane C; it needs the address lookup, so a branch
with #19). Not yet run. `packages/design_checker/tests/test_sites.py` checks the file is complete and keeps only
what each source allows.

**To watch for:** 614 University Ave's district comes from the City's map as `R-U`; Gordium's rulebook is `RU`. The
start box must show RU and load its rules: if it shows R-U with no rules, that is a lookup bug (#19). Several of the
first R-1b candidates on E State St came back with the street side needing review ("the address is on E STATE ST,
but the lot only touches E STATE ST M L K JR ST"): the City's road layer names that street differently.
