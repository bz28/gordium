# Made-up houses with interiors

Six synthetic houses (none is a real house) written in the host-neutral [interior description](../../docs/interior/interior_description_format.md), so egress measuring can be tested end to end on any machine, without Rhino or Revit. Each folder has:

- `house.yaml`: the house's rooms, escape openings, stairs, guards and exit door, as simple geometry;
- `expected.yaml`: every measure worked out **by hand, with its working in a comment, before the measuring code ran on the house** (committed first, in its own commit). A measure the description can't settle is listed under `not_measured`; a list not given at all under `not_read`.

`packages/model_measurement/tests/test_interior_houses.py` checks the code's numbers against `expected.yaml` exactly (to a millionth), then runs the measured parts through the checker's per-part rows with SYNTHETIC rules (made-up rules, never the code's text).

| House | Units | What it tests |
|---|---|---|
| `1_ranch_compliant` | in | One story, two bedrooms, each with an escape window that complies: a casement and a double-hung (grade-floor: within 44 in of the ground); a side-hinged exit door; a fixed window not marked as an escape opening; no stairs |
| `2_two_story_small_window` | in | Bedroom 3's casement is 5.125 sq ft (under 5.7, not grade-floor): the checker names it as failing. Bedroom 4 has a sloped ceiling down to a 4 ft knee wall, so its floor area (R312.3) has no value. A 16-riser stair under the upper floor's edge (headroom 85.5 in), a handrail on one side |
| `3_tall_riser` | ft | A basement stair with one riser 9 in among 7 1/2 in ones (riser 9.0, variation 1.5), open on one side behind a guard whose height is least at the tall riser (35.25 in); a sliding window with no ground level given (grade-floor: no value); no doors read at all |
| `4_loft` | mm | A sleeping loft over a bedroom: a steep loft stair under a roof rising 1 in 2 (headroom 98.5 in), a balustered guard (36 in high, 3 1/2 in gaps); the bedroom's awning window has no maker's clear opening, so nothing about it is measured and its rule needs review |
| `5_basement_window_well` | in | A basement bedroom's casement in an area well (10 sq ft, 66 in deep): grade-floor reads two ways (6 in above the well floor, 60 in below the ground), so no value; an awning window with the maker's clear opening (3.33 sq ft, 20 in high); a stair whose headroom is 76 in under the main floor's edge; a sliding exit door (no clear width: R318.2 measures side-hinged doors) |
| `6_door_stated_clear` | in | A side-hinged exit door both drawn and with the maker's stated clear opening: the less favourable counts for each size. Width: the maker's 33.5 in, under the drawn 34.0 (stated wins); height: the drawn 79.25 in, under the maker's 79.5 (drawn wins). Each says which in `from` |
