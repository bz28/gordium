# Interior measurements for egress

**Purpose:** exactly how Gordium measures each egress part (escape openings, stairs, guards, the exit door, sleeping rooms), the code section each measure serves, and every reason a measure is left without a value.\
**For:** engineers changing `model_measurement.interior`, reviewers checking a measure, architects asking "what does this number mean?".\
**Kept current by:** the engineer who changes `packages/model_measurement/model_measurement/interior/` in that PR (a test fails if a reason below is missing).

The input is the [interior description](interior_description_format.md); the checker runs New York's house rules on these measures in every Ithaca check ([rules for each part](../decisions/2026-11-12_rules_for_each_part.md), item 12); the code is `packages/model_measurement/model_measurement/interior/` (one module per kind); the hand-worked houses are in [test_data/interior_houses/](../../test_data/interior_houses/README.md). Plain code written by engineers, no AI (principle 6).

**The code text.** The 2025 Residential Code of New York State (RCNYS), read from the working copy in the code cache (the Public.Resource.Org scan, archive.org `gov.ny.residential.2025`, kept outside the repository). Quotes are short and exact; "p." is the book's own page number.

## The promises

1. **Missing or unclear data gives no number**, never a default or a guess. The measure is left out of `measures` and its reason is in `not_measured`; a rule reading it then says **needs review** (`rule_format.parts`).
2. **Where the law reads two ways, both readings are measured.** The same answer: that is the value. Different answers: no value, and the reason names the question.
3. **Where the drawing and a stated value can disagree.** An exit door's clear width and height take the smaller of the drawn and the maker's stated size, no agreement asked: never more than either. An escape opening's (the maker's clear opening against the drawn sashes) must agree within 1/16 in, and the less favourable one counts (the smaller width and height, the higher sill; grade-floor must come out the same at both bottoms). A maker's opening can never be bigger than its frame, and a fixed window never opens. Sizes (widths, thicknesses, offsets) can't be negative.
4. **Drawing noise read on the cautious side.** A nosing's two ends may differ by 1/16 in: each riser and tread is read with the ends paired the worst way, and the line of the nosings through their higher ends, each at its end nearer the foot (the line rises, so that is as high as it can stand). A maker's clear opening within 1/16 in of its frame is cut back to the frame. A flat surface's points may stand 1/16 in off its plane: the plane is lowered to its lowest point.
5. **Exact, never sampled.** Heights between flat surfaces are found at the corners of where they overlap, the flight cut at every bend of the line of the nosings (the gap between two flat surfaces changes in a straight line, so its least value is at a corner); widths along a flight at every point where a side, handrail or tread end bends.
6. **A part placed against another must stand where it says.** A part that attaches to another by where it is drawn counts only where it actually is: a stair guard only along a side of its stair (its top line on that side's line, within 1/16 in, drawing noise), a handrail is a side's handrail only if it runs the whole flight between the stair's sides, a door leaf only turned about a hinge pin that hangs it (at its hinge-side corner, within 1/16 in, or beyond it, which only narrows the width), and only where it closes its own opening (from the hinge-side stop to the latch-side stop). And what they are checked against is itself checked: a stair's drawn side bounds it only where it stands at the tread ends (no more than a skirt or stringer, 1 1/2 in, out beyond them; treads may run past it into the wall), so a side drawn away from the stair can't carry a guard or a handrail with it. The 3/4 in and 1 1/2 in are Gordium's stated readings of usual construction (a door stop's projection; a 2x stringer's thickness), to be confirmed. Drawn anywhere else, it gets no value: a guard 500 in off to the side of a stair protects none of it.
7. **Every length within reach.** A length more than 1,000,000,000 in (about 15,800 miles) from the origin gets no value (`too_far`). Inside that, every area, sum and difference worked out from lengths stays a finite number, so no check can be passed by an overflow to infinity. As a last guard, any value that still isn't a finite number is left out (`not_finite`).
8. **Units explicit.** Every length in is converted from the description's stated `units`; every measure comes out in inches (`in`) or square feet (`sf`), as `rule_format/parts.yaml` names them. Values are rounded to a millionth (float noise only, far finer than any drawing).

## Sleeping rooms (`sleeping_room`)

| Measure | How | Serves |
|---|---|---|
| `sleeping_room_floor_area` (sf) | The area of the finished floor outline, **only when no part of the ceiling is under 7 ft** above the finished floor. Otherwise no value | R312.1 "a floor area of not less than 70 square feet" (p.73) |
| `floor_area_drawn` (sf, in `more`) | The floor outline's whole area, whatever the ceiling | (context) |
| `least_ceiling_height` (in, in `more`) | The least height from the finished floor to the finished ceiling over the whole room (a flat `ceiling_height`, or the ceiling pieces, which must cover the room) | R312.3, R313.1 |

Why no area under a low ceiling: R312.3 leaves out "Portions of a room with a sloping ceiling measuring less than 5 feet (1524 mm) or a furred ceiling measuring less than 7 feet (2134 mm)" (p.74). Which parts those are (sloping or furred, and where the 5 ft line falls) isn't measured yet; giving the whole drawn area would overstate it. A sleeping loft counts its area differently again (R315.3, under 3 ft), so a loft with a low ceiling also gets no value.

## Emergency escape and rescue openings (`emergency_escape_opening`)

**The clear opening.** R319.2.2: "The net clear opening dimensions shall be the result of normal operation of the opening" (p.79). Gordium measures it seen straight on, perpendicular to the wall (what a person climbing straight out passes through), in the opening's own elevation:

- **Sliding** (double-hung, single-hung, horizontal slider, sliding door): the frame's clear opening less every sash drawn in its fully open position.
- **Hinged** (casement, side-hinged door): less the hinged sash at its open angle. From the jamb it is hinged on, it covers `offset + max(0, w cos a) + t sin a` (w its width, t its thickness, a the angle from closed, offset how far its hinge edge stands off the jamb when open). This is the sash's shadow on the wall plane: anything climbing out straight would hit it.
- **Fixed**: no clear opening (all three measures 0; it has no bottom, so no sill height).
- **Awning, hopper, pivot, tilt-turn, other**: the opening a person can pass depends on how far the sash opens and its hardware, so only the maker's stated net clear opening is used; without it, no value.
- A sliding sash must lie within its frame, and a hinged sash must close the whole frame (as wide, within 1/16 in, and thicker than nothing): otherwise what is drawn contradicts itself, and there is no value.
- What is left must be **one rectangle**; sashes leaving two openings, or an L shape, give no value (which part counts is unclear).

| Measure | How | Serves |
|---|---|---|
| `opening_net_clear_width` (in) | The clear rectangle's width | R319.2.2 "The minimum net clear opening width dimension shall be 20 inches" (p.79) |
| `opening_net_clear_height` (in) | Its height | R319.2.2 "minimum net clear opening height dimension shall be 24 inches" (p.79) |
| `opening_net_clear_area` (sf) | Width times height | R319.2.1 "a net clear opening of not less than 5.7 square feet" (p.79) |
| `opening_sill_height` (in) | The clear rectangle's bottom less the room's finished floor elevation | R319.2.3 "the bottom of the clear opening not greater than 44 inches (1118 mm) above the floor" (p.79) |
| `opening_at_grade` (yes/no) | Yes if the clear opening's bottom is within 44 in of the finished ground outside at every point given; no if at none; mixed: no value | Definition, GRADE FLOOR EMERGENCY ESCAPE AND RESCUE OPENING: "not more than 44 inches (1118 mm) above or below the finished ground level adjacent to the opening" (p.21); R319.2.1 Exception, 5 square feet |
| `opening_is_door` (yes/no) | From the opening's `operation` alone: yes for `side_hinged_door` and `sliding_door`; no for `casement`, `double_hung`, `single_hung`, `horizontal_slider`, `awning`, `hopper` (window types by name); no value for `fixed`, `pivot`, `tilt_turn` and `other`, which are made as doors and as windows | R319.3 "Where a door is provided as the required emergency escape and rescue opening, it shall be a side-hinged door or a sliding door" (p.80) |
| `opening_door_hinged_or_sliding` (yes/no) | Yes for a door (both door operations are one or the other); a window gets no value (`not_a_door`): it is asked only of a door | R319.3 |
| `opening_into_patio_cover`, `opening_under_projection` (yes/no) | No, on every escape opening, only where the description says the house has no patio covers, or no deck, porch or cantilever over an escape opening (`has_none`); else no value | Appendix BF103.2; R319.2.4 |
| `area_well_area` (sf, `more`) | The well's width times its projection | R319.4.1 "The horizontal area of the area well shall be not less than 9 square feet" (p.80) |
| `area_well_width`, `area_well_projection` (in, `more`) | As given | R319.4.1 "a horizontal projection and width of not less than 36 inches" (p.80) |
| `area_well_depth` (in, `more`) | The highest ground given outside less the well's floor | R319.4.2 "vertical depth greater than 44 inches" needs a ladder or steps (p.80) |

**An opening in an area well, read two ways.** "The finished ground level adjacent to the opening" can be the well's own floor or the ground around the well. Both are measured; if one says grade-floor and the other doesn't, `opening_at_grade` has no value (open question for the architects, [questions_for_architects.md](../questions_for_architects.md) §4.6; until answered, a rule that turns on it needs review).

Not measured here (each a rule of its own, later): bars, grilles and screens over the opening (R319.4.4), window opening control devices (R319.1.1, R321.2.2), the 36 in path under a deck or porch (R319.2.4), whether the opening reaches a public way (R319.1).

## Stairs (`stair`)

One part per straight flight. s runs up the flight at a right angle to the first nosing; a runs across it.

| Measure | How | Serves |
|---|---|---|
| `stair_riser_height` (in) | The tallest riser. Each riser is the height between the leading edges (nosings) of adjacent treads; the first from the finished floor at the foot, the last to the top floor's or landing's nosing | R318.7.5.1 "measured vertically between leading edges of the adjacent treads" (p.77) |
| `stair_riser_variation` (in) | Tallest less shortest riser in the flight (each riser at its tallest and shortest) | R318.7.5.1 "shall not exceed the smallest by more than 3/8 inch" (p.77) |
| `stair_tread_depth` (in) | The shallowest tread: the distance along s between adjacent nosings | R318.7.5.2 "measured horizontally between the vertical planes of the foremost projection of adjacent treads and at a right angle to the tread’s leading edge" (p.77) |
| `stair_tread_variation` (in, `more`) | Deepest less shallowest tread | R318.7.5.2 (p.77) |
| `stair_headroom` (in) | The least height from the line connecting the nosings up to anything overhead, over the flight's whole width from its first nosing to its top one (each tread at its own nosing's width, back to the next riser, and out to both ends of every nosing drawn slightly askew, the top one included). The overhead pieces must cover all of it | R318.7.2 "measured vertically from the sloped line adjoining the tread nosing" (p.77) |
| `stair_clear_width` (in) | The least distance across between the two sides above handrail height (wall faces, a guard's inside face; tread ends for an open side, each tread at its own nosing's width back to the next nosing, from its nosing's nearer end to the next one's farther end), over the flight out to the top nosing's farther end | R318.7.1 "not less than 36 inches (914 mm) in clear width at all points above the permitted handrail height" (p.77) |
| `stair_clear_width_at_handrail` (in; given to the rules since 2026-11-26, section group 7c, and kept in `more`) | The same, at and below handrail height: the inmost of the side, the handrail's inner edge (where it runs) and the tread ends (each tread at its own nosing's width back to the next nosing) | R318.7.1 "The clear width of stairways at and below the handrail height, including treads and landings" (p.77) |
| `stair_handrail_sides` (count; given to the rules since 2026-11-26, section group 7c, and kept in `more`) | How many sides have a handrail (0, 1 or 2): the width allowed at the handrail turns on it. A side counts only where one handrail runs the whole flight between the stair's sides (the wall faces, or an open side's tread ends); a side whose handrails run only part of it, or lie outside the sides: no value. The description gives no handrail height, so that isn't checked here | R318.7.1 (31 1/2 in with one side, 27 in with both); R320.5 "continuous for the full length of the flight, from a point directly above the nosing of the landing at the top of the flight to a point directly above the lowest nosing of the flight" (p.81) |
| `stair_headroom_past_bottom` (in; the Building Code check only, section group 7c: interior/stairs.py headroom_past_bottom) | The least height to anything overhead, over the first nosing's width, from the first nosing back to the farther of one tread depth (the flight's deepest; the bottom riser's face stands at or behind the first nosing) and where the line connecting the nosings, carried on down at its first slope, meets the floor or landing at the foot; measured from that line, and from the floor or landing wherever the line is below it. Needs the flight placed in plan; the overhead surfaces must cover the stretch (else no value) | BCNYS 1011.3 "Such headroom shall be continuous above the stairway to the point where the line intersects the landing below, one tread depth beyond the bottom riser" (p.332) |
| `stair_handrail_each_side` (yes/no; the Building Code check only, section group 7c) | Whether `stair_handrail_sides` is 2: a handrail runs the whole flight on each side. No value where the sides aren't worked out | BCNYS 1011.11 "Flights of stairways shall have handrails on each side" (p.334) |
| `stair_in_exit_enclosure` (yes/no; the Building Code check only, section group 7c: model_measurement/routes/stair_rooms.py) | Whether the flight stands wholly in an exit stair enclosure: under each end of each nosing, the room whose floor outline covers it in plan with the highest floor at or below it (a wall's face counts within 1/16 in) is a room the routes read as itself an exit (`space_is_exit`: a door marked `exit_enclosure` or `exit_passageway` enters it). Any such room not an exit: no. A nosing over no room, a room whose floor can't be read, or one whose exit isn't worked out: no value | BCNYS 1011.2, 1011.3, 1011.5.2 and 1011.11's exceptions for stairs within dwelling units (pp.331-334); 1023 (an interior exit stairway is enclosed apart from the building) |
| `stair_riser_count` (count; the Building Code check only, section group 7c, from `more`'s `stair_risers`) | The risers of the flight, as `stair_risers`. The house code's rules aren't given it yet (their results would change: re-recorded with it later) | BCNYS 1011.11 exceptions 3 to 5 (one riser, three or fewer, not more than two; p.334) |
| `stair_total_rise`, `stair_risers` (`more`) | The top nosing less the foot; the number of risers | R318.7.3 "a vertical rise greater than 12 feet 7 inches" (p.77) |
| `stair_spiral` (yes/no) | The description's `spiral` (the host's own record of the flight's shape: Revit's run style), taken only where the nosings agree: `false` only for a flight measured straight with rectangular treads; `true` never yet (nothing measured shows the closed circular form, and a curved stair isn't one: true would set the ordinary R318.7 rules aside); else, or not given, no value | R202 "Spiral stairway": "a stairway with a plan view of closed circular form and uniform section-shaped treads, attached to and radiating from a minimum-diameter supporting column" |

The tread and riser dimensions are "exclusive of carpets, rugs or runners" (R318.7.5, p.77): the description gives finished walking surfaces without them. Not measured yet: winder treads (at the walkline, R318.7.5.2.1: no value), spiral stairs, nosing projections (R318.7.5.3), landings (their size and headroom, R318.7.6), open risers' 4 in sphere.

## Guards (`guard`)

Guard is not a part kind in `rule_format/parts.yaml` yet: these are measured so a guard rule can be added.

| Measure | How | Serves |
|---|---|---|
| `guard_height` (in) | A level guard: its top less the walking surface; the members must reach that top all along the guard (at each point between its ends the highest member there; a member wholly above the stated top isn't part of the guard), else no value. A stair guard: its top above the line connecting the nosings, least over the flight (checked at every nosing and every bend of the top line); only a guard standing along a side of its stair (its top line, in plan, within 1/16 in of a side drawn in the stair's `sides` all along the flight), else no value | R321.1.2 "as measured vertically above the adjacent walking surface or the line connecting the nosings" (p.81) |
| `guard_opening_sphere` (in) | A level guard: the diameter of the largest sphere that passes through it between the walking surface and its top: the largest circle that fits an opening between its members (an opening that is a rectangle: its smaller side). A solid guard: 0. Measured over the guard's whole height (at least the required height: the cautious side) | R321.1.3 "openings from the walking surface to the required guard height that allow passage of a sphere 4 inches (102 mm) in diameter" (p.81) |

Not measured yet: a stair guard's openings (R321.1.3 Exceptions 1 and 2: the 6 in triangle at each step, the 4 3/8 in sphere): no value. Whether a guard is required (more than 30 in above the floor below, R321.1.1) is the rule's question, not a measure here.

## The exit door (`egress_door`)

| Measure | How | Serves |
|---|---|---|
| `door_clear_width` (in) | A side-hinged door only: the leaf, drawn closed, turned 90 degrees about its hinge pin (which must hang it: at the leaf's hinge-side corner on the face it swings toward, within 1/16 in, or beyond it; else no value). The leaf must be thicker than nothing and, closed, span its opening: reach the latch-side stop (within 1/16 in), and stand no farther behind the hinge-side stop than a stop laps a leaf (3/4 in), else no value; from its face toward the latch side (or the hinge-side stop, if that stands further in) to the latch-side stop (with a maker's stated clear opening, see below the table) | R318.2 "measured between the face of the door and the stop, with the door open 90 degrees" (p.76) |
| `door_clear_height` (in) | The bottom of the head stop less the top of the threshold (with a maker's stated clear opening, see below the table) | R318.2 "measured from the top of the threshold to the bottom of the stop" (p.76) |
| `door_side_hinged` (yes/no) | From the door's `operation` alone: yes for `side_hinged`; no for `sliding`, `folding`, `pocket`; no value for `other` | R318.2 "The egress door shall be side-hinged" (p.76) |

Not measured yet: `opening_operable`. It follows from `operation` just as plainly (fixed glass doesn't open; every other operation does), but R319.6's rule checks it on every sleeping room's openings, since a rule for each opening can't read whether its room is new in an addition: measured, R319.6 would say "complies" on every new house, where it doesn't apply ([decision](../decisions/2026-11-16_interior_absent_parts.md), item 5).

A sliding, folding or pocket door gets no clear width: R318.2's measure is defined for a side-hinged door (and requires one), so a maker's stated width doesn't give it one either.

**The maker's stated clear opening** (`stated_clear`, [decision 2](../revit/revit_interior_reading_design.md#8-decisions-ben-2026-11-19-go-w-ur-recs): door families don't model the stops, pin and leaf consistently; a maker's number with its source can be trusted). Each clear size (width, height) is worked out on its own:

- **Drawn only:** as above.
- **Stated only** (none of that size's drawing given: `stops`, `hinge_pin`, `leaf_closed` for the width; `threshold_top`, `head_stop_bottom` for the height): the maker's size.
- **Both:** the less favourable, the smaller. Unlike an escape opening's (which must agree within 1/16 in), no agreement is asked: the smaller can be no more than either, so the larger one can't make the door pass.
- **Drawn but not measurable** (part of the drawing missing, or wrong): no value, even with a maker's size (`door_drawn_unread`): the maker's alone could be more than the door as drawn.
- **A maker's size given but malformed** (not a mapping, a key it doesn't know, no `source`, a size missing, not a length, or not more than zero): neither clear size gets a value. It is never dropped: dropping it would leave the drawn size, which may be the larger.

The door's part says, in `from`, for each clear size it has: `used` (`drawn`, `stated`, or `both` when they are the same), the `drawn` and `stated` values given, the maker's `source`, and `why` in words.

## Every reason a measure can have no value

From `interior/stops.py`, word for word (a blank in braces is filled in with the part's own value).

| Key | Reason |
|---|---|
| `not_a_description` | the interior sent from the model can't be read (it isn't a set of named entries) |
| `wrong_format` | the interior sent from the model is in a form Gordium doesn't read ({got}, not gordium.interior/1) |
| `units` | the interior sent from the model gives its sizes in {units}, not in inches, feet, millimetres or metres |
| `not_read` | the {what} weren't read: the model doesn't say these are all the {what} (or that there are none) |
| `not_a_list` | the {key} sent from the model can't be read (they aren't a list) |
| `not_a_mapping` | {what} #{n} isn't a mapping |
| `flag_missing` | {what} doesn't say whether {question} (yes or no) |
| `flag_not_yes_no` | {what} gives whether {question} as {got}, not as a yes/no value |
| `unknown_spaces_entry` | enclosed space #{n} with no room drawn in it can't be read (it has no id): the rooms aren't read |
| `unknown_space` | an enclosed space with no room drawn in it: its use isn't known, so it may be a sleeping room (draw a room in it and say whether it is a sleeping room) |
| `has_none_not_a_list` | what the model says the house has none of can't be read (it isn't a list, each entry a kind and its source): it isn't read |
| `has_none_entry` | entry #{n} of what the house has none of isn't a kind with its source: it isn't read |
| `has_none_listed` | the model says the house has no {kind}, but {key} have a list of their own in the model: say there are none with an empty list of {key}, not as something the house has none of |
| `has_none_sleeping_room` | the model says the house has no sleeping rooms: a room that isn't a sleeping room says so itself (sleeping room: no), not as something the house has none of |
| `has_none_kind` | the model says the house has none of {kind!r}, not a kind it can say that of (one of: {kinds}): it isn't read |
| `has_none_no_source` | the model says the house has no {words} but not where that comes from (its source, such as the sheet): it isn't taken, so their rules need review |
| `has_none_reading` | the model says the house has no {words}, but gives whether that rests on a reading of the law as {got}, not as a yes/no value: it isn't taken, so their rules need review |
| `has_none_twice` | the model says {count} times that the house has no {words}: it isn't taken, so their rules need review |
| `has_none_keys` | the model says the house has no {words}, giving more than a kind, a source and, optionally, a reading (also {keys}): it isn't taken, so their rules need review |
| `has_none_below_ground` | the model says the house has no basements, yet {what}: which is right is unclear, so their rules need review |
| `has_none_room_within` | the model says the house has no sleeping lofts, yet {what}: which is right is unclear, so their rules need review |
| `has_none_unknown_space` | the model says the house has no {words}, yet it gives {count} enclosed space(s) whose use isn't known (no room drawn in them), any of which could be one: it isn't taken, so their rules need review |
| `stairs_none_several_floors` | the model says there are no stairs, yet {what}: a stair or a ramp joins its floors or leads down to the ground, unless each floor has its own way out at grade, which the model doesn't show, so 'no stairs' isn't taken and the stair rules need review |
| `has_none_contradicted` | the model says the house has no {words}, yet it also gives {key}, and not an empty list: which is right is unclear, so their rules need review |
| `missing` | {what} isn't given |
| `not_a_length` | {what} isn't a length (a number) |
| `too_far` | {what} is more than 1,000,000,000 in (about 15,800 miles) from the origin: not a place in a house |
| `not_finite` | it came out too large to be a number (from lengths far apart) |
| `operation_undecided` | the {what}'s operation ({operation}) doesn't say {question} |
| `not_measured_yet` | Gordium doesn't measure this yet |
| `in_more_not_rules` | Gordium works this out (shown with the extra values) but doesn't give it to the rules yet |
| `negative` | {what} is {value} in: a size can't be less than zero |
| `not_a_point` | {what} isn't a list of {n} numbers |
| `not_an_outline` | {what} isn't an outline of at least 3 points that encloses an area |
| `not_a_polyline` | {what} isn't a line of at least 2 points |
| `not_a_rectangle_given` | {what} isn't a rectangle (left, right, bottom, top, with right > left and top > bottom) |
| `choice` | {what} is {got!r}, not one of {choices} |
| `two_ceilings` | both a ceiling height and ceiling surfaces are given: give one |
| `no_ceiling` | the room's ceiling isn't given (a ceiling height, or the ceiling surfaces) |
| `low_ceiling` | part of the room's ceiling is {height} in above the floor, under 7 ft: which part of the floor counts (R312.3) isn't measured yet |
| `surface_vertical` | {what} is vertical: give the underside of what is overhead |
| `surface_not_flat` | {what} isn't flat (a point is {off} in off its plane): give it as flat pieces |
| `surface_out_of_range` | {what} has coordinates too large to measure |
| `shapes_failed` | {what}: the geometry library couldn't work out the shapes (edges so nearly parallel it can't tell where they meet): check the drawing near there |
| `not_covered` | {what} doesn't cover the whole {region}: give everything above it |
| `nothing_overhead` | nothing above the flight is given: give what is above it (a ceiling, the floor above, a beam) |
| `room_unknown` | the room the opening is in isn't one of the rooms given |
| `room_twice` | {count} rooms have the id {id!r}: which one the opening is in is unclear |
| `operation_needs_clear` | a{n} {operation} window's clear opening depends on how far it opens and its hardware: give the maker's net clear opening (its clear width, height, bottom and source) |
| `no_frame` | the opening's frame isn't given (and no maker's clear opening) |
| `hinge_angle` | the hinged sash's open angle ({angle}°) isn't between 0 and 180 |
| `no_sashes` | the open sashes of a sliding window aren't given |
| `clear_in_pieces` | the open sashes leave the opening in {count} pieces: which is the clear opening is unclear |
| `clear_not_rectangle` | the clear opening left by the open sashes isn't a rectangle |
| `clear_differs` | the maker's clear opening and the drawn one differ ({which}): which is right is unclear |
| `clear_outside_frame` | the maker's clear opening is bigger than its frame, or reaches outside it: which is right is unclear |
| `sash_outside_frame` | open sash {n} reaches outside the frame: a sliding sash opens within it |
| `sash_smaller_than_frame` | the hinged sash ({width} in wide, {thickness} in thick) doesn't close the {frame} in frame: the rest of the frame isn't an opening |
| `not_a_door` | the opening is a window: whether it is a side-hinged or sliding door is asked only of a door |
| `no_clear_opening` | the opening doesn't open (no clear opening), so it has no bottom |
| `sill_below_floor` | the opening's bottom is {sill} in from its room's floor, below it: check the room's floor elevation and the opening's position |
| `no_ground` | the finished ground level outside the opening isn't given |
| `ground_mixed` | the ground outside the opening is within 44 in of its bottom at some points and not at others |
| `readings_differ` | the readings give different answers; {question} |
| `spiral_not_said` | whether the flight is a spiral stairway isn't given (yes or no) |
| `spiral_not_straight` | the flight is said not to be a spiral stairway, but it isn't measured as a straight flight ({reason}): its shape isn't known |
| `spiral_but_straight` | the flight is said to be a spiral stairway, but its nosings make a straight flight with rectangular treads: which is right is unclear |
| `spiral_not_shown` | the flight is said to be a spiral stairway, but nothing measured shows R202's closed circular form around a supporting column (a curved stair isn't one): its shape isn't known |
| `nosings_out_of_range` | the stair's nosings have coordinates too large to measure |
| `too_few_nosings` | the flight needs at least {n} nosings (each tread's leading edge, and the top one) for this |
| `nosing_not_level` | nosing {n} isn't level (its ends are {off} in apart in height) |
| `not_bottom_to_top` | the nosings don't go up from the bottom one at a time (riser {n} is {rise} in) |
| `winders` | the treads aren't rectangular (nosing {n}'s ends are {off} in apart along the run): winder treads are measured at the walkline, not yet |
| `nosings_not_forward` | the nosings don't move forward up the flight (tread {n} is {depth} in deep) |
| `side_not_along` | the {side} {what} doesn't run along the flight from its first nosing to its top one |
| `side_off_treads` | the stair's {side} side stands {off} in out beyond its treads' ends, more than a skirt or stringer between them ({most} in): it doesn't bound this stair (draw it where the treads end, or give that side as open) |
| `sides_cross` | the stair's sides meet or cross (clear width {width} in) |
| `treads_cross` | at the treads, a tread's end meets or crosses the other side (clear width {width} in): check the nosings' ends and the stair's sides |
| `handrails_cross` | at handrail height, a handrail meets or crosses the other side (clear width {width} in): check each handrail's side |
| `handrail_side` | a handrail's side is {got!r}, not left or right |
| `handrail_part_way` | no {side} handrail runs the whole flight between the stair's sides (from above its lowest nosing to above its top one, R320.5): whether that side has a handrail isn't measured |
| `guard_top_not_drawn` | the guard's members don't reach its stated top all along it (at its lowest the drawn guard is {least} in high): which is its height is unclear |
| `guard_kind` | say whether the guard is along a stair or at a level walking surface: give one |
| `guard_opening_shape` | an opening in the guard isn't a rectangle: the largest sphere through it isn't measured yet |
| `stair_unknown` | the stair the guard is along isn't one of the stairs given (by its id) |
| `stair_unread` | the stair the guard is along couldn't be measured: {reason} |
| `guard_no_side` | both of the stair's sides are given as open: a guard along it stands on neither (give the side the guard stands on as the guard's inside face, as that side of the stair) |
| `guard_off_side` | the guard's top line doesn't stand along a side of its stair ({off} in, in plan, from the nearer side drawn, at its farthest; within {on} in is drawing noise): which side it protects is unclear (a side with a guard is given as the guard's inside face, as that side of the stair) |
| `stair_guard_openings` | a stair guard's openings (the 4 3/8 in sphere, the triangle at each step) aren't measured yet |
| `not_side_hinged` | R318.2 measures a side-hinged door open 90 degrees; this door is {operation} |
| `stops_wrong_way` | the latch-side stop isn't on the far side of the opening from the hinge side |
| `leaf_no_thickness` | the door leaf's closed corners give it no thickness: a leaf is thicker than nothing |
| `leaf_not_closing` | the closed leaf stops {short} in short of the latch-side stop (within 1/16 in is drawing noise): the leaf drawn doesn't close this opening |
| `leaf_behind_hinge_stop` | the closed leaf's hinge edge stands {back} in behind the hinge-side stop, more than a stop laps a leaf ({most} in): the leaf drawn doesn't close this opening (a swing-clear hinge isn't measured yet) |
| `pin_off_leaf` | the hinge pin stands {off} in back from the leaf's hinge-side corner (behind the face it swings toward, or toward the hinge jamb; within 1/16 in is drawing noise): the leaf drawn isn't hung on that pin |
| `door_stated_shape` | the door's maker's clear opening isn't a width, a height and a source: neither clear size counts |
| `door_stated_keys` | the door's maker's clear opening gives more than its width, height and source (also {keys}): neither clear size counts |
| `door_stated_no_source` | the door's maker's clear opening doesn't say where it comes from (its source, such as the maker's catalogue): neither clear size counts |
| `door_drawn_unread` | the door's clear {what} is drawn but can't be measured from the drawing ({reason}): the maker's stated one alone could be more than the door as drawn, so neither counts |
| `not_positive` | {what} is {value} in: not more than zero |
