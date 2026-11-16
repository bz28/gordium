# The full egress check on a real house: 80 South William Street, Orangetown NY

**Purpose:** what Gordium's egress check says about a real, permit-filed house, rule by rule, set against a hand-check of the same rules worked from the code and the drawings before the checker ran; and every place the two differ, with the reason.\
**For:** Ben, the architects, and anyone changing the egress rules, the interior description or the measuring code.\
**Kept current by:** whoever changes the egress rulebook, `model_measurement.interior` or `design_checker/egress.py`: `packages/design_checker/tests/test_real_house_egress.py` fails when the checker's answers stop matching this page's tables and counts (the reasons and the prose explanations are checked by hand).

## The headline

- **No false pass.** Of New York State's 115 egress rules, the checker says **complies** for 1 (the front door is side-hinged), **not applicable** for 33 (8 of them only if one of 3 readings is confirmed: the panel shows those as needs review), and **needs review** for 81. None fails. Every "complies" and every "not applicable" is the hand-check's own answer; where one rests on a reading rather than the drawings, the panel says so and asks for it to be confirmed.
- **The checker did what it should, every time.** Before the run, the hand-check predicted the checker's answer for each rule from the description and the rules' own formulas. All 115 matched. Each reason the checker gave was compared by hand with the predicted one (the `because` in hand_check.yaml) when this page was written, and they agree. **Checker bugs found: 0. Description errors found: 0.**
- **What changed since the first run (all 115 needed review).** The description can now say what the house has none of (`has_none`: no sleeping lofts, ramps, alternating tread devices, ship's ladders, patio covers, or decks, porches or cantilevers over an escape opening; no habitable attic), each with its sheet. And the measuring now reads two facts the description already held: the front door is side-hinged, and every escape opening is a window. 34 rules moved from needs review to the hand-check's answer ([decision](../../../docs/decisions/2026-11-16_interior_absent_parts.md)).
- **It is cautious in 18 places.** The hand-check could settle 52 rules: 5 the house meets and 47 that don't apply to it. The checker now agrees on 34 of them. It leaves the other 18 rules: 4 the house meets and 14 that don't apply at needs review, for one of five reasons (the "Why they differ" column below). An architect sees 257 items: 7 say what the house has none of (4 not applicable, 3 readings to confirm), 1 complies (the front door is side-hinged), and the rest need review.
- **Rule-drafting points: 2, both on the cautious side.** One rule asks about a patio cover at every exit door (an error). Another applies R319.6 (additions) to every bedroom of a new house (a trade-off already recorded in the rule).
- **Zoning doesn't apply to this lot.** The house is in the Town of Orangetown, Rockland County. Gordium's only zoning rulebook is the City of Ithaca's. So only the state code was checked: the 2025 Residential Code of New York State (RCNYS), which the drawings' title sheet (A-1) cites.

## Words used here

- **Egress**: the ways out of a house in a fire. These are the exit door, stairs and their landings, handrails and guards, and each bedroom's emergency escape and rescue opening (a window big enough to climb out of, low enough to reach).
- **Interior description**: the house's inside written as plain numbers (rooms, windows, stairs, doors, guards) in Gordium's format (`gordium.interior/1`, [format](../../../docs/interior/interior_description_format.md)). The checker measures from this, never from the drawing itself.
- **Checker's answers**: *complies* (passes), *does not comply* (fails), *needs review* (a person must decide; Gordium's answer whenever something is missing or unclear), *not applicable*.
- **Hand-check**: a person working each rule out from the code text and the drawings, without Gordium.

## What was checked, and how

1. **The drawings.** The "Proposed Bennington Model" by Eric Knute Osborn, Architect: five sheets, A-1 to A-5, dated 30 Dec 2025. It was filed with the Town of Orangetown planning board ([public PDF](https://www.orangetown.com/wp-content/uploads/2026/02/68.20-2-76.2-80-South-William-Street-Lot-2-Arch-Plans.pdf), SHA-256 `c6879996…`). It is a new two-story, four-bedroom single-family house with a basement and an attached garage. The drawings are the architect's copyright and are not kept in this repository. Every value here cites a sheet and a callout ([README](README.md)).
2. **The interior description: [house.yaml](house.yaml).** Written by hand from the drawings in PR #97, with a citation for every value. Every value the drawings don't give is listed as absent, with the reason. Since then it also says what the house has none of (`has_none`), each claim with its sheet; three of them (the attic, the attic stair, the porch) rest on a reading of the law and are marked so. It holds the 4 bedrooms (floor, ceiling), the 10 bedroom windows marked as escape openings, the bonus room's 2 and the basement's 2, the front door, the 4 second-floor railings and the guard along the main stair. It has **no stairs**: the drawings give no floor-to-floor height and no tread depths, so the nosings the format needs can't be written without inventing them.
3. **The hand-check: [hand_check.yaml](hand_check.yaml).** Every one of the 115 rules was worked out by hand and committed on its own, before the checker ran (see the PR's commits). For each rule it gives two things:
   - the *truth*: what the code says about the house as drawn. Most of these build on PR #97's [answer_key.yaml](answer_key.yaml), which was worked before any checker existed.
   - the *prediction*: what the checker should say, given what the description holds.
4. **The run.** `design_checker.egress.check` used New York State's rulebook (`regulations/jurisdictions/new_york/new_york_state/5_building_code_rules/drafted/general.yaml`, 115 rules), with one building value: 1 dwelling unit (A-1 project data: single-family dwelling). The checker reads state rules only through a place that inherits them, and Ithaca is the one such place. Ithaca's zoning was not run, because `egress.check` runs only the inherited state law.
5. **The comparison.** The table below. `test_real_house_egress.py` reruns the comparison in CI.

## The results

| | Rules | Checker: complies | Checker: does not comply | Checker: needs review | Checker: not applicable |
|---|---|---|---|---|---|
| All egress rules | 115 | 1 | 0 | 81 | 33 |

| Hand-check (truth) | Rules | Checker agrees | Checker more cautious |
|---|---|---|---|
| complies | 5 | 1 | 4 |
| does not comply | 0 | 0 | 0 |
| needs review | 63 | 63 | 0 |
| not applicable | 47 | 33 | 14 |

Before `has_none` and the two facts: 0 complies, 0 does not comply, 115 needs review, 0 not applicable.

**Why no rule fails although the answer key finds real risks.** The basement stair's risers are 8.31 in at 13 risers with the section's 2x12 joists, over the 8 1/4 in limit. A 3046 double-hung may come in under 5.7 sq ft. The bonus room's step is about 30 in wide. The rear sliders have no landing drawn at the door, over steps that need at least four risers, but no sheet details the steps or a landing, so whether one is built is a question for the drawing's architect (README question 9). The basement stair and the 3046 are each a "does not comply" only under one reading of drawings that disagree with themselves (13 or 14 risers; 2x10 or 2x12 joists), or under assumed sizes; the bonus room's step only if a single step is a stairway (architect question 1). So the hand-check itself says needs review for them, and so does the checker. They are listed for the drawing's architect in the [README](README.md).

The panel shows 257 items. 304 are the rules' rows, one per rule and part: each of the 10 bedroom windows gets every escape-opening rule except the three about basements, habitable attics and loft rooms. The panel shows 244 of them; the other 60 are not applicable, and each of those is listed in its claim's item (or, for R319.3, comes from the windows being windows). The other 13 items are the ones the hand-check predicted:

- "the stairs weren't read"
- the bonus room's 2 marked windows and the basement's 2, each "marked as an escape opening but isn't checked"
- "Not checked yet by Gordium": the 86 egress sections Gordium has no rules for yet, window fall protection (R321.2.1) and hallway width (R318.6) first (added by PR #110)
- one for each thing house.yaml says the house has none of. Four are **not applicable**, with the claim's sheet and every rule it sets aside: "Sleeping lofts: not applicable", "Ramps", "Alternating tread devices", "Decks, porches or cantilevers over an escape opening". Three rest on a reading and **need review** as readings to confirm: "Habitable attics", "Ship's ladders", "Patio covers: not applicable if this reading is confirmed". None is ever a pass; the four not applicable count toward nothing, and the three readings count as needs review

**Why they differ** (only where the hand-check settles a rule and the checker doesn't):

- **D (drawings):** the drawings give no stair geometry, so the description has no stairs and every stair rule needs review. The hand-check settles 12 stair rules anyway: 1 the flights meet (their rise) and 11 that don't apply (spiral, sleeping-loft, non-rectangular landing). The sleeping-loft claim would settle the four sleeping-loft stair rules (`stair_serves_sleeping_loft: false` on every stair), but only once stairs are given.
- **F (format):** the description can say what the house has none of (`has_none`), but not yet that it *has* a basement: R319.6's basement rule needs to know whether the basement is a new one in an addition, and the format has no basement to say it of. (Before `has_none`, 32 more rules were here: sleeping lofts, ramps, alternating tread devices, ship's ladders, habitable attics, loft rooms, patio covers, decks and porches over windows.)
- **G (guards):** the five railings are in the description, read as `guard` parts (nothing about them is measured yet: their members aren't given). But the guard rules read `open_side` parts, which nothing produces yet. So "a guard is required", which the drawings settle (every open side over 30 in has a railing drawn), stays needs review.
- **M (not measured yet):** a fact the description already holds that the measuring doesn't yet turn into the rule's measure. Every escape window is a double-hung or casement, yet `opening_operable` isn't given: it would follow from `operation`, but R319.6's rule (below) would then say "complies" on every bedroom of a new house, where the law doesn't apply, so it waits for that rule's fix (a question for Ben). (`door_side_hinged` and `opening_is_door` are now measured from `operation`.) The basement's two CW14s in their areaways are in the description (`bsw1`, `bsw2`), yet nothing measures `opening_below_grade` yet, and the checker doesn't check those windows at all: they are listed as "not checked" items. The area-well row's truth comes from them.
- **R (rule drafting):** see the two drafting points below.


## Every rule

Grouped by the part the rule repeats over. "Section" is the code section the checker cites, the one each panel row links to with the rule's exact quote. "Hand-check" is the truth column of [hand_check.yaml](hand_check.yaml), which gives each rule's reasoning and sheet citations.

| # | Rule | Section | Part | Checker | Hand-check | Agree | Why they differ |
|---|---|---|---|---|---|---|---|
| 1 | Exit into a patio cover not unenclosed: exits per R318 (`bf103_2_exit_into_patio_cover_r318_exits`) | BF103.2 | egress door | needs review | not applicable | no | R |
| 2 | Egress door clear height at least 78 in (`r318_2_egress_door_clear_height`) | R318.2 | egress door | needs review | needs review | yes |  |
| 3 | Egress door clear width at least 32 in (`r318_2_egress_door_clear_width`) | R318.2 | egress door | needs review | needs review | yes |  |
| 4 | One egress door for each dwelling unit (`r318_2_egress_door_per_dwelling_unit`) | R318.2 | egress door | needs review | needs review | yes |  |
| 5 | Egress doors readily openable without key (`r318_2_egress_door_readily_openable`) | R318.2 | egress door | needs review | needs review | yes |  |
| 6 | Egress door shall be side-hinged (`r318_2_egress_door_side_hinged`) | R318.2 | egress door | complies | complies | yes |  |
| 7 | Egress door not given as an exterior door: its landings unchecked (`r318_3_1_egress_door_given_as_exterior_door`) | R318.3.1 | egress door | needs review | needs review | yes |  |
| 8 | Landing dimension at least 36 in. in direction of travel (`r318_3_exterior_door_landing_depth`) | R318.3 | exterior door | needs review | needs review | yes |  |
| 9 | Landing or floor on each side of each exterior door (`r318_3_exterior_door_landing_each_side`) | R318.3 | exterior door | needs review | needs review | yes |  |
| 10 | Slope at exterior landings not over 1/4 in 12 (`r318_3_exterior_door_landing_slope`) | R318.3 | exterior door | needs review | needs review | yes |  |
| 11 | Landing width not less than the door served (`r318_3_exterior_door_landing_width`) | R318.3 | exterior door | needs review | needs review | yes |  |
| 12 | Exterior landing not at grade: ramp or stairway to grade (`r318_3_1_egress_door_exterior_landing_access_to_grade`) | R318.3.1 | exterior door | needs review | needs review | yes |  |
| 13 | Inside floor at required egress door at most 1 1/2 in below threshold (`r318_3_1_egress_door_inside_floor_drop`) | R318.3.1 | exterior door | needs review | needs review | yes |  |
| 14 | Outside landing drop at required egress door (`r318_3_1_egress_door_outside_floor_drop`) | R318.3.1 | exterior door | needs review | needs review | yes |  |
| 15 | Floor elevation at exterior doors other than the egress door (`r318_3_2_other_exterior_door_floor_elevation`) | R318.3.2 | exterior door | needs review | needs review | yes |  |
| 16 | Escape opening into a patio cover: unenclosed (`bf103_2_escape_opening_into_patio_cover_unenclosed`) | BF103.2 | emergency escape opening | not applicable | not applicable | yes |  |
| 17 | Every basement: operable escape opening (`r319_1_basement_escape_opening_operable`) | R319.1 | emergency escape opening | needs review | needs review | yes |  |
| 18 | Escape openings open to a public way, yard or court (`r319_1_escape_opening_opens_to_public_way_or_yard`) | R319.1 | emergency escape opening | needs review | needs review | yes |  |
| 19 | Every habitable attic: operable escape opening (`r319_1_habitable_attic_escape_opening_operable`) | R319.1 | emergency escape opening | not applicable | not applicable | yes |  |
| 20 | Room a sleeping loft is open to: operable escape opening (`r319_1_loft_room_escape_opening_operable`) | R319.1 | emergency escape opening | not applicable | not applicable | yes |  |
| 21 | Every sleeping room: operable escape opening (`r319_1_sleeping_room_escape_opening_operable`) | R319.1 | emergency escape opening | needs review | complies | no | M |
| 22 | Escape opening minimum net clear area (`r319_2_1_escape_opening_min_net_clear_area`) | R319.2.1 | emergency escape opening | needs review | needs review | yes |  |
| 23 | Escape opening minimum net clear height (`r319_2_2_escape_opening_min_net_clear_height`) | R319.2.2 | emergency escape opening | needs review | needs review | yes |  |
| 24 | Escape opening minimum net clear width (`r319_2_2_escape_opening_min_net_clear_width`) | R319.2.2 | emergency escape opening | needs review | needs review | yes |  |
| 25 | Escape opening bottom of clear opening max height (`r319_2_3_escape_opening_max_sill_height`) | R319.2.3 | emergency escape opening | needs review | needs review | yes |  |
| 26 | Escape openings under decks, porches, cantilevers (`r319_2_4_under_projection_openable_path`) | R319.2.4 | emergency escape opening | not applicable | not applicable | yes |  |
| 27 | Emergency escape and rescue door: side-hinged or sliding (`r319_3_escape_door_side_hinged_or_sliding`) | R319.3 | emergency escape opening | not applicable | not applicable | yes |  |
| 28 | Area well where opening is below grade (`r319_4_area_well_required`) | R319.4 | emergency escape opening | needs review | complies | no | M |
| 29 | Area well size allows opening to fully open (`r319_4_1_area_well_allows_full_opening`) | R319.4.1 | emergency escape opening | needs review | needs review | yes |  |
| 30 | Area well horizontal area at least 9 sf (`r319_4_1_area_well_min_area`) | R319.4.1 | emergency escape opening | needs review | needs review | yes |  |
| 31 | Area well horizontal projection at least 36 in (`r319_4_1_area_well_min_projection`) | R319.4.1 | emergency escape opening | needs review | needs review | yes |  |
| 32 | Area well width at least 36 in (`r319_4_1_area_well_min_width`) | R319.4.1 | emergency escape opening | needs review | needs review | yes |  |
| 33 | Area well deeper than 44 in: ladder or steps (`r319_4_2_area_well_ladder_over_44`) | R319.4.2 | emergency escape opening | needs review | needs review | yes |  |
| 34 | Area well ladder rungs for full height (`r319_4_2_1_area_well_ladder_full_height`) | R319.4.2.1 | emergency escape opening | needs review | needs review | yes |  |
| 35 | Area well ladder projection from wall (`r319_4_2_1_area_well_ladder_projection`) | R319.4.2.1 | emergency escape opening | needs review | needs review | yes |  |
| 36 | Area well ladder rung spacing (`r319_4_2_1_area_well_ladder_rung_spacing`) | R319.4.2.1 | emergency escape opening | needs review | needs review | yes |  |
| 37 | Area well ladder inside width (`r319_4_2_1_area_well_ladder_width`) | R319.4.2.1 | emergency escape opening | needs review | needs review | yes |  |
| 38 | Area well steps: width, tread, riser (`r319_4_2_2_area_well_steps_requirements`) | R319.4.2.2 | emergency escape opening | needs review | needs review | yes |  |
| 39 | Escape opening in each new sleeping room of an addition (`r319_6_addition_sleeping_room_escape_opening`) | R319.6 | emergency escape opening | needs review | not applicable | no | R |
| 40 | Escape opening in the new basement of an addition (`r319_6_addition_basement_escape_opening`) | R319.6 | basement | needs review | not applicable | no | F |
| 41 | Sleeping loft stairway clear width at or above handrail (`r315_5_2_1_sleeping_loft_stair_clear_width_at_or_above_handrail`) | R315.5.2.1 | stair | needs review | not applicable | no | D |
| 42 | Sleeping loft stairway width below handrail (`r315_5_2_1_sleeping_loft_stair_clear_width_below_handrail`) | R315.5.2.1 | stair | needs review | not applicable | no | D |
| 43 | Sleeping loft stair riser height, 7 to 12 in (`r315_5_2_2_sleeping_loft_stair_riser_height`) | R315.5.2.2 | stair | needs review | not applicable | no | D |
| 44 | Sleeping loft stair tread/riser formula (`r315_5_2_2_sleeping_loft_stair_tread_riser_formula`) | R315.5.2.2 | stair | needs review | not applicable | no | D |
| 45 | Stairway clear width above handrail height (`r318_7_1_stair_clear_width_above_handrail`) | R318.7.1 | stair | needs review | needs review | yes |  |
| 46 | Stairway clear width at and below handrail (`r318_7_1_stair_clear_width_at_handrail`) | R318.7.1 | stair | needs review | needs review | yes |  |
| 47 | Spiral stairway clear width at handrails (`r318_7_11_1_spiral_stair_clear_width`) | R318.7.11.1 | stair | needs review | not applicable | no | D |
| 48 | Spiral stairway headroom (`r318_7_11_1_spiral_stair_headroom`) | R318.7.11.1 | stair | needs review | not applicable | no | D |
| 49 | Spiral stairway treads identical (`r318_7_11_1_spiral_stair_identical_treads`) | R318.7.11.1 | stair | needs review | not applicable | no | D |
| 50 | Spiral stairway rise (`r318_7_11_1_spiral_stair_rise`) | R318.7.11.1 | stair | needs review | not applicable | no | D |
| 51 | Spiral stairway tread depth at walkline (`r318_7_11_1_spiral_stair_tread_depth`) | R318.7.11.1 | stair | needs review | not applicable | no | D |
| 52 | Spiral stairway walkline radius (`r318_7_11_1_spiral_stair_walkline_radius`) | R318.7.11.1 | stair | needs review | not applicable | no | D |
| 53 | Floor opening projection into stair headroom (`r318_7_2_stair_floor_opening_headroom`) | R318.7.2 | stair | needs review | needs review | yes |  |
| 54 | Minimum stairway headroom, 6 ft 8 in (`r318_7_2_stair_headroom`) | R318.7.2 | stair | needs review | needs review | yes |  |
| 55 | Maximum vertical rise of a flight of stairs (`r318_7_3_stair_vertical_rise_max`) | R318.7.3 | stair | needs review | complies | no | D |
| 56 | Open risers: 4-inch sphere limit (`r318_7_5_1_stair_open_riser_sphere`) | R318.7.5.1 | stair | needs review | needs review | yes |  |
| 57 | Maximum stair riser height (`r318_7_5_1_stair_riser_height_max`) | R318.7.5.1 | stair | needs review | needs review | yes |  |
| 58 | Riser slope from the vertical (`r318_7_5_1_stair_riser_slope`) | R318.7.5.1 | stair | needs review | needs review | yes |  |
| 59 | Riser height variation within a flight (`r318_7_5_1_stair_riser_variation_max`) | R318.7.5.1 | stair | needs review | needs review | yes |  |
| 60 | Minimum stair tread depth (`r318_7_5_2_stair_tread_depth_min`) | R318.7.5.2 | stair | needs review | needs review | yes |  |
| 61 | Tread depth variation within a flight (`r318_7_5_2_stair_tread_variation_max`) | R318.7.5.2 | stair | needs review | needs review | yes |  |
| 62 | Bottom landing width not less than flight width (`r318_7_6_bottom_landing_width`) | R318.7.6 | stair | needs review | needs review | yes |  |
| 63 | Bottom landing width, exterior stair to grade serving deck (`r318_7_6_deck_stair_bottom_landing_width`) | R318.7.6 | stair | needs review | needs review | yes |  |
| 64 | Top landing at enclosed garage stair, drop below threshold (`r318_7_6_garage_top_landing_drop`) | R318.7.6 | stair | needs review | needs review | yes |  |
| 65 | Landings other than square or rectangular (`r318_7_6_nonrectangular_landing`) | R318.7.6 | stair | needs review | not applicable | no | D |
| 66 | Floor or landing at the bottom of each flight (`r318_7_6_stair_bottom_landing`) | R318.7.6 | stair | needs review | needs review | yes |  |
| 67 | Floor or landing at the top of each flight (`r318_7_6_stair_top_landing`) | R318.7.6 | stair | needs review | needs review | yes |  |
| 68 | Landing depth at a straight run (`r318_7_6_straight_run_landing_depth`) | R318.7.6 | stair | needs review | needs review | yes |  |
| 69 | Top landing width not less than flight width (`r318_7_6_top_landing_width`) | R318.7.6 | stair | needs review | needs review | yes |  |
| 70 | Handrail on one side of flights with four or more risers (`r318_7_8_stair_handrail_one_side`) | R318.7.8 | stair | needs review | needs review | yes |  |
| 71 | Handrail height 34 to 38 in (`r320_2_handrail_height_34_38`) | R320.2 | handrail | needs review | needs review | yes |  |
| 72 | Handrail projection, 4 1/2 in (6 1/2 in at nosings) (`r320_3_handrail_projection`) | R320.3 | handrail | needs review | needs review | yes |  |
| 73 | Handrail clearance from wall (`r320_4_handrail_wall_clearance`) | R320.4 | handrail | needs review | needs review | yes |  |
| 74 | Handrail continuous full length of flight or ramp (`r320_5_handrail_continuity`) | R320.5 | handrail | needs review | needs review | yes |  |
| 75 | Handrail end returned (`r320_5_handrail_end_returned`) | R320.5 | handrail | needs review | needs review | yes |  |
| 76 | Handrail return gap from wall at most 1/4 inch (`r320_5_handrail_return_gap`) | R320.5 | handrail | needs review | needs review | yes |  |
| 77 | Circular handrail outside diameter, Type I (`r320_6_handrail_circular_diameter`) | R320.6 | handrail | needs review | needs review | yes |  |
| 78 | Handrail edge radius (`r320_6_handrail_edge_radius`) | R320.6 | handrail | needs review | needs review | yes |  |
| 79 | Non-circular handrail perimeter and cross section, Type I (`r320_6_handrail_type_i_noncircular`) | R320.6 | handrail | needs review | needs review | yes |  |
| 80 | Handrail with perimeter over 6 1/4 in: finger recess, Type II (`r320_6_handrail_type_ii_recess`) | R320.6 | handrail | needs review | needs review | yes |  |
| 81 | Guard required at open sides over 30 in. drop (`r321_1_1_guard_required_open_side`) | R321.1.1 | open side | needs review | complies | no | G |
| 82 | Guard height, open sides other than stairs (`r321_1_2_guard_height_open_side_not_stair`) | R321.1.2 | open side | needs review | needs review | yes |  |
| 83 | Guard top serving as stair handrail, 34 to 38 in (`r321_1_2_guard_height_stair_guard_as_handrail`) | R321.1.2 | open side | needs review | needs review | yes |  |
| 84 | Guard height, open sides of stairs (`r321_1_2_guard_height_stair_open_side`) | R321.1.2 | open side | needs review | needs review | yes |  |
| 85 | Guard openings stop a 4 inch sphere (`r321_1_3_guard_opening_4_inch_sphere`) | R321.1.3 | open side | needs review | needs review | yes |  |
| 86 | Stair guard openings stop a 4 3/8 inch sphere (`r321_1_3_guard_stair_opening_4_3_8_sphere`) | R321.1.3 | open side | needs review | needs review | yes |  |
| 87 | Stair guard triangle stops a 6 inch sphere (`r321_1_3_guard_stair_triangle_6_inch_sphere`) | R321.1.3 | open side | needs review | needs review | yes |  |
| 88 | Sleeping loft ceiling over 7 ft on at most half the floor area (`r315_2_sleeping_loft_ceiling_height_limit`) | R315.2 | sleeping loft | not applicable | not applicable | yes |  |
| 89 | Sleeping loft floor area less than 70 sf (`r315_2_sleeping_loft_floor_area_limit`) | R315.2 | sleeping loft | not applicable | not applicable | yes |  |
| 90 | Sleeping loft: ceiling height above finished floor (`r315_3_sleeping_loft_ceiling_height`) | R315.3 | sleeping loft | not applicable | not applicable | yes |  |
| 91 | Sleeping loft: clear height below floor construction (`r315_3_sleeping_loft_clear_height_below`) | R315.3 | sleeping loft | not applicable | not applicable | yes |  |
| 92 | The room a sleeping loft is open to has an escape opening (`r319_1_room_a_sleeping_loft_is_open_to`) | R319.1 | sleeping loft | not applicable | not applicable | yes |  |
| 93 | Maximum slope of ramp serving the required egress door (`r318_8_1_ramp_max_slope_egress_door`) | R318.8.1 | ramp | not applicable | not applicable | yes |  |
| 94 | Maximum slope where technically infeasible due to site constraints (`r318_8_1_ramp_max_slope_infeasible`) | R318.8.1 | ramp | not applicable | not applicable | yes |  |
| 95 | Maximum slope of other ramps (`r318_8_1_ramp_max_slope_other`) | R318.8.1 | ramp | not applicable | not applicable | yes |  |
| 96 | Ramp landing depth at least 36 inches (`r318_8_2_ramp_landing_depth`) | R318.8.2 | ramp | not applicable | not applicable | yes |  |
| 97 | Ramp landing width not less than ramp width (`r318_8_2_ramp_landing_width`) | R318.8.2 | ramp | not applicable | not applicable | yes |  |
| 98 | Floor or landing at top and bottom of each ramp (`r318_8_2_ramp_landings_present`) | R318.8.2 | ramp | not applicable | not applicable | yes |  |
| 99 | Handrail on at least one side of ramps steeper than 1 in 12 (`r318_8_3_ramp_handrail_one_side`) | R318.8.3 | ramp | not applicable | not applicable | yes |  |
| 100 | Alternating tread device clear width at handrails (`r318_7_12_atd_clear_width`) | R318.7.12 | alternating tread device | not applicable | not applicable | yes |  |
| 101 | Alternating tread devices not an element of a means of egress (`r318_7_12_atd_not_in_means_of_egress`) | R318.7.12 | alternating tread device | not applicable | not applicable | yes |  |
| 102 | ATD angle of ascent between 50 and 70 degrees (`r318_7_12_1_atd_angle`) | R318.7.12.1 | alternating tread device | not applicable | not applicable | yes |  |
| 103 | ATD initial tread at platform elevation (`r318_7_12_1_atd_first_tread_at_floor`) | R318.7.12.1 | alternating tread device | not applicable | not applicable | yes |  |
| 104 | ATD projected tread depth at least 8 1/2 in (`r318_7_12_1_atd_projected_tread_depth`) | R318.7.12.1 | alternating tread device | not applicable | not applicable | yes |  |
| 105 | ATD riser height at most 9 1/2 in (`r318_7_12_1_atd_riser_height`) | R318.7.12.1 | alternating tread device | not applicable | not applicable | yes |  |
| 106 | ATD tread depth at least 5 in (`r318_7_12_1_atd_tread_depth`) | R318.7.12.1 | alternating tread device | not applicable | not applicable | yes |  |
| 107 | ATD tread width at least 7 in (`r318_7_12_1_atd_tread_width`) | R318.7.12.1 | alternating tread device | not applicable | not applicable | yes |  |
| 108 | Handrails on both sides of alternating tread devices (`r318_7_12_2_atd_handrails_both_sides`) | R318.7.12.2 | alternating tread device | not applicable | not applicable | yes |  |
| 109 | Handrails of alternating tread devices comply with R320 (`r318_7_12_2_atd_handrails_comply_r320`) | R318.7.12.2 | alternating tread device | not applicable | not applicable | yes |  |
| 110 | Ship's ladder clear width at handrails (`r318_7_13_ship_ladder_clear_width`) | R318.7.13 | ships ladder | not applicable | not applicable | yes |  |
| 111 | Ship's ladders not an element of a means of egress (`r318_7_13_ship_ladder_egress_use`) | R318.7.13 | ships ladder | not applicable | not applicable | yes |  |
| 112 | Ship's ladder riser height at most 9 1/2 in (`r318_7_13_1_ships_ladder_riser_height`) | R318.7.13.1 | ships ladder | not applicable | not applicable | yes |  |
| 113 | Ship's ladder tread depth at least 5 in (`r318_7_13_1_ships_ladder_tread_depth`) | R318.7.13.1 | ships ladder | not applicable | not applicable | yes |  |
| 114 | Ship's ladder tread plus nosing at least 8 1/2 in (`r318_7_13_1_ships_ladder_tread_plus_nosing`) | R318.7.13.1 | ships ladder | not applicable | not applicable | yes |  |
| 115 | Handrails on both sides of ship's ladders (`r318_7_13_2_ships_ladder_handrails_both_sides`) | R318.7.13.2 | ships ladder | not applicable | not applicable | yes |  |

## The disagreements, explained

**Checker bugs: none.** For all 115 rules the checker's answer is the predicted one, and its reason is the predicted one (compared by hand). No answer is kinder than the hand-check's.

**Description errors: none found.** The new facts the hand-check needed were read from the drawings for this PR:

- the patio at the rear sliders (A-2 'PATIO', at grade), and the steps down to it from each slider (A-2 'DN'; A-4 'CONC. PAVER STONE STEPS'), drawn with no landing at the door: the main floor (240.4', A-2) is 26.4 in over the rear grade (238.2', A-4), so at least four risers, more than R318.7.6 Exception 3's two;
- the step down at the mudroom door onto the garage landing (A-2 'DN' at the door), and the garage landing's railing ('RAILING AS PER RES. CODE', no height); the sheets disagree on the garage slab's depth (31.2 in by A-2's spot elevations, about 15 in by A-4);
- the garage's side door and overhead door (A-2, A-4), more exterior doors whose landings aren't given;
- the folding attic stair (A-3 'ATTIC STAIR DETAILS': 'FAKRO OR EQUAL INSUL. ATTIC STAIR ASSY.', 'LOCATION TO BE DETERMINED');
- the unfinished attic (A-5 section);
- the single-family use (A-1).

None of them changes house.yaml's values (only its `has_none` claims, added later, rest on some of them). Review rounds 1 to 4 found the rear steps, the garage door step and the garage landing's railing, the area well's projection and steps, and the porch steps ending on bare grade, and seven hand-check truths were corrected from complies or not applicable to needs review, each listed at the top of hand_check.yaml and pinned by the test.

**Rule-drafting points: 2.** Both are cautious, so neither can pass what the law fails.

1. `bf103_2_exit_into_patio_cover_r318_exits` (BF103.2) has no `applies_when`. It asks "does this exit door open into a patio cover?" of *every* egress door, so it needs review on every house, forever. That alone means the Egress section can never say "complies". The law: "Where such exterior openings serve as an exit from the dwelling unit, the patio structure, unless unenclosed, shall be provided with exits conforming to the provisions of Section R318" (RCNYS 2025, PDF p.898). A patio cover is "A structure with open or glazed walls that is used for recreational, outdoor living purposes associated with a dwelling" (same page). Here the front door opens onto an open-sided covered porch, so even read as a patio cover it is "unenclosed" and the rule asks nothing of it. The fix: a measure for "this egress door opens into a patio cover", as its escape-opening twin already has (`opening_into_patio_cover`), and an `applies_when` on it. It goes through the drafting record (`draft_fixes`, `revised`), so it is left for its own PR.
2. `r319_6_addition_sleeping_room_escape_opening` (R319.6, "Where dwelling unit additions contain sleeping rooms") applies to *every* sleeping room, not only those of an addition. This is a known trade-off, already recorded in the rule's `revised` history: a rule over a bedroom's escape openings can't read whether its room is new, and R319.1 asks the same of every room. Today it only adds needs review. Once `opening_operable` is measured, it would show "complies with R319.6" on a new house: a pass where the law doesn't apply. So `opening_operable` is not measured yet, though it follows from `operation`. The real fix, letting a rule read a measure of the part it sits within (or a stated "this is an addition"), is for its own PR.

## Found on the way (for Ben; no false pass today)

- **The Egress section could one day have said "complies" while sections it doesn't check were open.** The rulebook has no rules yet for R321.2.1 (window fall protection), R318.6 (hallway width) and others. On this house that matters: the 3052 double-hungs' bottoms are about 19 in above the floor, under R321.2.1's 24 in, so fall protection is a real question (answer key `window_fall_protection`). **Fixed by PR #110 (Ben, 2026-11-15):** the Egress section now carries one needs-review item, "Not checked yet by Gordium", listing every section with no rules yet, and egress never reads "complies" while it is there.
- **R312 and R313 (room size and ceiling height) aren't in the egress rulebook.** The measuring already gives each bedroom's floor area (128 to 230 sq ft, all over 70) and ceiling (96 in), but no rule reads them. They are habitable-room rules (Chapter 3), not egress, so this is scope, not an error.

## Questions for the architects

Two are questions of the law's meaning that research didn't settle. The rest are questions for this drawing's own architect, kept in the [README](README.md).

1. **Is a single step in a doorway a "stairway" that must be 36 in wide?** The bonus room's 7 1/2 in step down onto the bridge is drawn in its 2'-8" doorway (A-3), about 30 in wide.
   - Searched: RCNYS 2025 R202 ("STAIR. A change in elevation, consisting of one or more risers"; STAIRWAY: "One or more flights of stairs"); R318.7.1 (its only exception is spiral stairs); R318.7.6 Exception 1 (the door at the top); the NY Department of State's Technical Bulletin TB-1005, "Residential Exit Doors, Stairways, Landings, Handrails, and Guards" ([dos.ny.gov](https://dos.ny.gov/system/files/documents/2019/10/tb-1005-rcnys-residential-exit-doors-stairs-and.pdf), read 2026-11-15), which quotes the 36 in width but says nothing of single risers.
   - Building-code forum opinion is split ([thebuildingcodeforum.com](https://www.thebuildingcodeforum.com/forum/threads/measuring-risers-at-thresholds.33867/), read 2026-11-15).
   - Ithaca's own interpretations: nothing found.
   - Still open, because the code calls one riser a stair, but whether a step with no tread is a "flight", and so part of a stairway, isn't settled by the text.
2. **Is bare grade a "floor or landing" at the foot of exterior steps?** The porch steps run 'DOWN' to grade with no walk drawn at their foot (A-2). R318.7.6: "There shall be a floor or landing at the top and bottom of each flight of stairs" (PDF p.101); it says nothing of the landing's material.
   - Searched: RCNYS 2025 R318.7.6 and R202 (R202 defines FLIGHT, STAIR and STAIRWAY, but not LANDING). A web search (2026-11-15) turned up building-department and forum readings of the same IRC wording that disagree on whether ground or gravel can be the landing; none was read in full (the one linked, a City of Raymore, MO, IRC interpretation, returned 404 when opened), so none is cited.
   - Orangetown's and Ithaca's own interpretations: not yet searched.
   - Still open, so the hand-check leaves R318.7.6's bottom landing at needs review.

Three of house.yaml's `has_none` claims rest on Gordium's readings, stated here for the architects to confirm. Each is marked `reading: true`, so the panel and the permit sheets show it as its own needs-review item ("… not applicable if this reading is confirmed"): the rules it sets aside are not applicable, but the egress result can't read as settled while any of the three is unconfirmed.

- **The attic is not a habitable attic.** "ATTIC, HABITABLE. A finished or unfinished habitable space within an attic" (PDF p.35). "HABITABLE SPACE. A space in a building for living, sleeping, eating or cooking. Bathrooms, toilet rooms, closets, halls, storage" … are not (p.44).
- **Its folding attic stair is attic access, not a stairway or ship's ladder** that R318.7 governs.
- **The front porch is not a patio cover.** "PATIO COVER. A structure with open or glazed walls that is used for recreational, outdoor living purposes associated with a dwelling" (Appendix BF, PDF p.898). The porch is the house's covered entry, under its main roof (A-2, A-4). Even read as a patio cover, no bedroom window opens into it (they are all on the second floor), so BF103.2's escape-opening rule wouldn't apply either way.
