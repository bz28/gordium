# Deep run: one real lot per district family, every rule worked out by hand

**Who worked them:** Claude, by hand from Chapter 325 and the zoning charts, before comparing with Gordium (queue item
12, 2026-10-27). **Not yet verified by an architect** (architect review is deferred). The expected results are never
changed to match Gordium; a disagreement is investigated and listed.

| File | Lot | District | Design | The edit |
|---|---|---|---|---|
| `r1_111_eastwood_ave.yaml` | 111 Eastwood Ave, parcel 500700-111.-2-2, 12,990.5 sf, 100 ft on Eastwood Ave | R-1a | 40 × 50 ft house, three 10 ft stories, and a 20 × 22 ft frame garage behind it | house and garage 6 ft toward the street: the front yard (24 ft < 25) fails |
| `r2_316_e_falls_st.yaml` | 316 E Falls St, parcel 500700-12.-2-8, 4,763.9 sf, 56 ft on E Falls St | R-2b | two-family house 34 × 40 ft, three 9 ft stories | 1.5 ft west: the smaller side yard (4.52 ft < 5) fails |
| `r3_423_n_cayuga_st.yaml` | 423 N Cayuga St, parcel 500700-49.-1-26, 7,938.0 sf, 52.5 ft on N Cayuga St | R-3aa | one-family house 30 × 60 ft, two 11 ft stories, at the 10 ft front-yard and 2-story limits | none |

**Where the lots come from.** Each lot's corners are the State's tax-map outline (NYS Tax Parcels Public), looked up
with `site_lookup` on 2026-10-27, turned so the street line runs from (0, 0) along +x with the lot in +y (a rotation
only: the real shape). The district was checked live on the City's zoning map that day (its data isn't stored, per
its terms). For this run each lot is treated as surveyed and the ground as flat at elevation 0; the real lots are
from the tax map (±2 ft) and slope (the light run, `../light_run/`, covers the tax-map side).

**How each answer was worked.** From the law's own numbers (chart p.2 uses, p.3 dimensions, p.14 parking; §325-8A;
§325-3B definitions; §325-18B; §325-25), with the arithmetic in each `working`: shoelace areas, and distances to the
slightly slanted lot lines as the perpendicular from the house's nearest corner to the line. Each design states what
a massing model can't show (bedrooms, parking, who lives there) under `stated`. Every rule Gordium shows for the
design as drawn has an answer here (`packages/design_checker/tests/test_sites.py` checks that).

**Checked in code:** `python -m design_checker.scenarios --sites` (and `test_sites.py`, in CI). **In Rhino:**
`apps/rhino_plugin/tests/deep_run_in_rhino.py` (Lane C), then `python -m design_checker.scenarios --sites rhino
<temp>/gordium_deep_run/rhino_out.json`.

**One answer changed before comparing:** 316 E Falls St's two-family occupancy was first worked as complies (two
unrelated people in each unit, R-2's limit per unit). On reading §325-3B DWELLING, MULTIPLE (3) ("one or two
families and more than two roomers or boarders" make a multiple dwelling) it became needs review: four unrelated
people in the building may make it a multiple dwelling, which the law leaves to a person to decide.
