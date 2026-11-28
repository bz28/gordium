# The interior description (`gordium.interior/1`)

**Purpose:** the host-neutral format a design tool sends so Gordium can measure a house's inside for egress: rooms, escape openings, stairs, guards and the exit door, as simple geometry.\
**For:** engineers writing a reader that produces it (Rhino tags, the Revit add-in, an IFC reader) and anyone writing a test house by hand.\
**Kept current by:** the engineer who changes `packages/model_measurement/model_measurement/interior/` in that PR.

The measuring code is `model_measurement.interior` (`measure(description)`); what each measure means and which code section it serves is in [interior_measurements.md](interior_measurements.md). Six worked houses written in this format are in [test_data/interior_houses/](../../test_data/interior_houses/README.md).

## Why a format of its own

The zoning measurements read massing solids from a Rhino file. Egress needs the inside of the house: which room is a bedroom, which window the architect marks as its escape opening, how far that window's sash lets it open, where each stair nosing is. No host stores these the same way (a Revit window family, a Rhino block with tags, an IFC `IfcWindow` with a lining and panels), so each host's reader turns its own model into this one plain description, and the measuring code reads only this. The measuring code never looks at a host's model, and a host's reader never measures.

## The rules for every value

- **Units are stated, once.** `units` is one of `in`, `ft`, `mm`, `m`, and every length and coordinate in the file is in it (angles are degrees). The measures come out in inches and square feet whatever the units in.
- **Coordinates.** Plan points are `[x, y]`; 3D points `[x, y, z]`, z up. Elevations are absolute (the same z for every part of the house) and are **finished** surfaces: the finished floor, the finished ground, the tread's walking surface without carpet (R318.7.5: "exclusive of carpets, rugs or runners").
- **An element's own elevation.** A window, door or level guard is drawn in its own elevation: `u` along the wall (any origin, increasing to the right as seen from the room, or from the walking surface for a guard), `z` the same absolute elevation as everywhere else. A door's plan adds `n`, across the wall, positive toward the side the door swings into.
- **Not given is not zero.** A key left out means "not known", never a default. A list left out entirely (`stairs` missing) means that kind wasn't read, and every rule about it needs review; an empty list (`stairs: []`) means the house has none.
- **None is said, never inferred.** For the kinds the format has no list for (ramps, sleeping lofts…), the house has none only where `has_none` says so, with its source. Silence is "not read" (needs review), never "none".
- **Flags are required.** Every room says `sleeping: true|false`, every opening `escape: true|false`, every door `exit: true|false`. One missing and none of that kind is read: a bedroom nobody labelled is never quietly not a bedroom.

## The file

```yaml
format: gordium.interior/1
units: in
rooms: [...]
unknown_spaces: [...]     # optional: enclosed spaces with no room drawn in them
openings: [...]
stairs: [...]
doors: [...]
guards: [...]
has_none: [...]
```

Every part has an `id` (unique across the whole house) and may have a `name` (what the architect calls it: "Bedroom 2", "Window 5"; the id stands in otherwise).

### rooms

| Key | Meaning |
|---|---|
| `sleeping` | true for a room used or meant for sleeping, as the architect labels it (a sleeping loft too) |
| `floor` | the finished floor's outline inside the finished walls, plan points, at least 3, not crossing itself |
| `floor_elevation` | the finished floor's elevation |
| `ceiling_height` | a flat ceiling's height above the finished floor; **or** |
| `ceilings` | the finished ceiling's underside as flat pieces, each a list of 3D points, together covering the whole floor (give one or the other, never both) |

### unknown_spaces

`rooms` lists every room. A host that finds an enclosed space with no room drawn in it (walls all round, no Room: in Revit, a plan circuit with no Room) can't say what it is, and it may be a bedroom nobody drew a room in. Each such space is one entry here, `{id, name}` (the name says where it is: "Enclosed area on L1, 331.4 sq ft, around x 12, y 40"). Left out, or `[]`: there are none.

Each is measured as a sleeping room that may not be one: nothing of it is measured, and every rule row about it (its floor area, its escape openings, "a sleeping room with no escape opening fails") needs review, never a pass and never a fail, with the reason "an enclosed space with no room drawn in it: its use isn't known…". The rooms drawn are still checked as usual, so a drawn bedroom that fails still fails, and a rule over every sleeping room can't pass while a space may be one. A "no basements", "no habitable attics" or "no sleeping lofts" claim (`has_none`) isn't taken beside any unknown space. An unknown space is only given with `rooms`; an entry that isn't a mapping with a text `id` leaves every room not read.

### openings

Every window and door that could be an escape opening (only those marked `escape: true` in a sleeping room are measured; one marked in another room is listed as not checked).

| Key | Meaning |
|---|---|
| `room` | the id of the room it opens from |
| `escape` | true if the architect marks it as the room's emergency escape and rescue opening |
| `operation` | `casement`, `side_hinged_door` (hinged); `double_hung`, `single_hung`, `horizontal_slider`, `sliding_door` (sliding); `fixed`; or `awning`, `hopper`, `pivot`, `tilt_turn`, `other` (these need `stated_clear`) |
| `frame` | the frame's clear inside opening in the opening's own elevation: `{left, right, bottom, top}` (u, u, z, z) |
| `sashes` | a sliding window or door: each sash (rails and stiles included: glass isn't a way out) as `{left, right, bottom, top}`, **in its fully open position**, within the frame |
| `hinged` | a hinged one: `{side: left|right, open_angle, sash_width, sash_thickness, hinge_offset}` (one sash closing the whole frame; a pair or a sash beside fixed glass isn't measured yet): the jamb it hinges on, the angle it opens to by its normal operation (its hardware's stop, in degrees from closed), and how far its hinge edge stands off that jamb when open (0 for a sash hinged right at the jamb; hardware that slides the sash in from the jamb makes it more) |
| `stated_clear` | the maker's net clear opening: `{width, height, bottom, source}`, bottom an elevation. Required for the operations that need it; allowed for any (then it and the drawn one must agree within 1/16 in) |
| `ground_outside` | the finished ground level adjacent to the opening outside: one elevation, or a list (at each end, for sloping ground) |
| `area_well` | for an opening below the ground: `{floor_elevation, width, projection}`: the well's floor, its size along the wall and out from it |

### stairs

One entry per **flight** (a run of treads between landings; R318 calls it a flight). Only straight flights with rectangular treads are measured now.

| Key | Meaning |
|---|---|
| `bottom_elevation` | the finished floor or landing at the flight's foot |
| `spiral` | optional, true or false: whether the flight is a spiral stairway (R202), from the host's own record of its shape (a Revit run's style). `false` is taken only for a flight whose nosings make it straight; `true` isn't taken yet (nothing measured shows R202's closed circular form around a column, and a curved stair isn't one); left out, it is not known (the rules that turn on it need review) |
| `nosings` | the leading edge of each tread, bottom to top, then the leading edge of the floor or landing at the top: each `[[x, y, z], [x, y, z]]`, its two ends across the stair's width |
| `sides` | `{left, right}`, looking up the stair: the plan line of what bounds the flight above handrail height (a finished wall face, a guard's inside face), from before the first nosing to past the top one, standing at the tread ends (no more than 1 1/2 in, a skirt or stringer, out beyond them; the treads may run past it into the wall); or `open` for a side with neither (then the tread ends bound it) |
| `handrails` | a list (empty for none) of `{side: left|right, inner_edge}`: the plan line of the handrail's edge nearest the middle of the stair, as far as it runs |
| `overhead` | the underside of everything above the flight (ceiling, the floor above and its framing, a beam, a soffit), as flat pieces of 3D points, together covering the whole flight seen from above (an empty list is refused: nothing above can't be told from nothing sent) |

### doors

| Key | Meaning |
|---|---|
| `exit` | true for the door the architect marks as the dwelling's required exit door |
| `operation` | `side_hinged`, `sliding`, `folding`, `pocket`, `other` |
| `hinge_side` | `left` or `right`, in the door's own elevation |
| `stops` | `{hinge, latch}`: the u of the face of each jamb stop |
| `hinge_pin` | `[u, n]`: the hinge pin's centre in the door's plan: at the leaf's hinge-side corner on the face it swings toward, or beyond it (a pin more than 1/16 in behind that face, or back toward the hinge jamb, doesn't hang the leaf: no clear width) |
| `leaf_closed` | `[[u, n], [u, n]]`: two opposite corners of the leaf, closed, in the door's plan: thicker than nothing, spanning the opening: reaching the latch-side stop, and no more than 3/4 in (a stop's lap) behind the hinge-side stop |
| `threshold_top`, `head_stop_bottom` | the top of the threshold and the bottom of the head stop, elevations |
| `stated_clear` | optional: the maker's clear opening, `{width, height, source}`, both sizes required and more than zero, measured as R318.2 measures them (the width between the face of the door and the stop with the door open 90 degrees, the height from the top of the threshold to the bottom of the stop; a maker's "door size" or rough opening is not it), and `source` the maker's publication it comes from (required, not empty). No other key. Given with the drawn values, the less favourable (the smaller) of the two counts for each size; given alone (none of that size's drawn keys), it counts; given but malformed, neither size counts (never dropped, never defaulted). The measured door says in `from` which each size came from ([interior_measurements.md](interior_measurements.md#the-exit-door-egress_door)) |

A door's `stated_clear` was added within `gordium.interior/1` (2026-11-20): an optional key, so a description without it measures exactly as before. How the Revit add-in will fill it: [revit_interior_reading_design.md](../revit/revit_interior_reading_design.md), section 4 (Doors).

### guards

Either a guard at a level walking surface, or one along a stair (give `walking_surface` or `stair`, not both).

| Key | Meaning |
|---|---|
| `walking_surface` | the finished walking surface the guard protects (a loft's floor, a landing) |
| `top` | the top of the guard |
| `extent` | `{left, right}`: the u of what the guard ends against at each end (a wall, a newel post): solid beyond |
| `members` | every rail, baluster, post and panel in the guard's elevation, `{left, right, bottom, top}`; the members (the top rail) must reach `top` all along the guard, or it gets no height |
| `stair` | for a guard along a stair: the stair's id |
| `top_line` | for a guard along a stair: the top of the guard as 3D points, running the flight's whole length, in plan on the side of the stair it stands along (the same line as that side's guard inside face in the stair's `sides`, within 1/16 in), else it gets no height |

### has_none

What the house has none of, each claim with where it comes from ([decision](../decisions/2026-11-16_interior_absent_parts.md)). Each entry:

| Key | Meaning |
|---|---|
| `kind` | one of the kinds below |
| `source` | where the claim comes from: the sheet and callout ("none drawn: A-2, A-3"), or the host and who ticked it ("no Ramp elements in the model; ticked by the architect"). Required: a claim without one isn't taken |
| `reading` | optional, `true` where the claim rests on a reading of the law, not the drawings alone ("an unfinished attic is not a habitable attic"): the checker shows it as one to confirm (needs review) |

| Kind | What it settles |
|---|---|
| `basement`, `habitable_attic`, `ramp`, `alternating_tread_device`, `ships_ladder` | that part kind (`rule_format/parts.yaml`) is an empty list: its rules, and the rules for what sits within it (R319.1's escape opening in a basement or habitable attic), are not applicable |
| `sleeping_loft` | the same for sleeping lofts and for the room a sleeping loft is open to (`loft_room`); and every stair given gets `stair_serves_sleeping_loft: false` |
| `patio_cover` | every escape opening measured gets `opening_into_patio_cover: false` |
| `deck_porch_or_cantilever_over_escape_opening` | every escape opening measured gets `opening_under_projection: false` (a claim about the openings: a house may have a porch over none of them) |

A claim isn't taken (its kind stays not read, its rules need review, and the reason is one of the description's problems) when: `has_none` isn't a list; an entry has no `kind`, or one not in the table (the kinds the format lists itself are said with their own list: `stairs: []`, `openings: []`, `doors: []`, `guards: []`; a room that isn't a sleeping room says `sleeping: false`, since `rooms: []` is a house not drawn yet); its `source` is missing or empty; `reading` isn't true or false; it has a key other than `kind`, `source` and `reading` (a mistyped `reading` must never read as settled); the same kind is named twice; or the description also gives that kind's list as anything but an empty list (`ramps`, `basements`, `habitable_attics`, `sleeping_lofts`, `alternating_tread_devices`, `ships_ladders`, `patio_covers`: the lists a later reader will fill), which contradicts it. A "no basements" claim is also refused beside a space the description shows below the ground, or may: an opening with an `area_well`; a room's `floor_elevation` or a stair's `bottom_elevation` below the highest `ground_outside` given at any opening (a walk-out below the uphill ground is one to confirm too); or a ground, floor or stair foot given that isn't a number. A "no sleeping lofts" claim is refused beside a room drawn within another room's height (its floor over the other's in plan, above the other's floor and below the highest point of its ceiling), or a room whose floor or ceiling is given but can't be read; a room upstairs is at or above the ceiling of the room below, so it never is. Both checks are partial: with no ground given, nothing is compared; a room drawn with no floor at all (a room that isn't a sleeping room needn't be) isn't compared; and a loft over a low room, open only to a taller room beside it, isn't caught. The claim about openings has no list to contradict yet.

**How each reader fills it.** Always from the architect's statement, never from not finding something:

- **Rhino:** a "the house has none of" list the architect ticks per kind, with the sheet or a note as the source.
- **Revit** knows every element in the model, so it can *propose* a claim (no Ramp elements; no stair of a ship's-ladder type; no Room tagged as a loft), but a ramp drawn as a sloped floor, or a ship's ladder as a generic family, is invisible to that scan. A proposal is sent only once the architect ticks it, and the source says both ("no Ramp elements in the model; ticked by the architect"). The add-in's status list (`Answers.cs`) doesn't know the checker's `not_applicable` item status yet: it sends no interior today, so it never receives one, but it must learn the status before it sends `has_none`.
- **An IFC reader** proposes the same way from element types (`IfcRamp`, `IfcStair` of type `LADDER`) and sends a claim only once it is ticked.

## The route additions (a commercial story's escape routes)

Added within `gordium.interior/1` (2026-11-21) for measuring a story's routes: travel distance, and later common
path, dead ends, remoteness and areas ([the design](../decisions/2026-11-20_route_measurement.md)). Every key is
optional, so a house description measures exactly as before; the route code reads them
(`model_measurement/routes/floor.py`) and **a key left out is "not read", never a default**: what each absence does
is in the last column. Coordinates are plan points in `units`, like everything else.

| Key | Where | What it says | Left out |
|---|---|---|---|
| `levels: [{id, name, elevation}]` | the description | the stories | no story's routes are measured |
| `all_levels: [{id, name, elevation}]` | the description | every level of the model, one with nothing drawn on it too (an open parking story, a roof, a datum): the Revit reader sends every one. A level in both `levels` and `all_levels` has the same elevation in each (within 1/16 in): where they disagree no story is placed. Read only for where each story sits against the grade plane (`routes/story_place.py`): each level with no rooms is tried as a story and as not | no story's place against the grade plane is measured (a story with nothing drawn may be missing from `levels`) |
| `not_a_story` | an `all_levels` level | true where the architect states the level is no story of the building (in Revit, the level mark Gordium: Not a story: a reference or datum level, a roof level): the story places never try it as a story nobody drew rooms on, nor as a level within a story's floors or the lowest level ([story facts, step 1](../decisions/2026-11-25_story_facts_from_the_model.md)). A level so marked with rooms, or an enclosed space with no room, on it disagrees with the mark, and no story is placed; a value other than true or false (left out or null: not said) places nothing | not said: a level with no rooms is tried both as a story and not |
| `level` | each room, door and unknown space | the id of the story it is on | no story's routes are measured (a part that can't be placed) |
| `use` | a room | one of `corridor`, `lobby`, `day_care`, `accessory_storage`, `kitchen`, `toilet`, `closet`, `workroom`, `other` | the room is end-only (a route may start in it, never cross it) |
| `lockable`, `pass_through` | a room | true or false: whether it can be locked; whether the architect states it is accessory to the rooms it serves, with a discernible path to an exit (IBC 1014.2 item 1) | the room is end-only |
| `not_occupied` | a room | true or false: the architect states nobody occupies it (an abandoned space, a door permanently fixed shut, a shaft or chase; not a room visited for storage, maintenance, testing or inspection, NFPA 101 A.3.3.21.6). True: NFPA 101's travel and common path aren't measured from its points (7.6.1(1) "starting from the most remote point subject to occupancy"; A.3.3.47), each such figure saying which rooms it left out; the IBC's still are (1016.1 "the most remote point within a story"); it is crossed only where it otherwise could be. Refused on a sleeping room or a `day_care` room (the room isn't read) ([route note decision 1b](../decisions/2026-11-20_route_measurement.md)) | occupied: measured like any room |
| `function` | a room | its Table 1004.5 function (BCNYS 1004.5), as the architect states it (in Revit, the room mark Gordium: Function), one of: `accessory_storage_mechanical`, `agricultural`, `aircraft_hangar`, `airport_baggage_claim`, `airport_baggage_handling`, `airport_concourse`, `airport_waiting`, `gaming_floor`, `exhibit_gallery_museum`, `assembly_fixed_seats`, `assembly_concentrated`, `assembly_standing`, `assembly_unconcentrated`, `bowling_center`, `business`, `concentrated_business`, `courtroom`, `day_care`, `dormitory`, `classroom`, `vocational_shop`, `exercise_room`, `h5_fabrication`, `industrial`, `information_technology`, `inpatient_treatment`, `outpatient`, `institutional_sleeping`, `commercial_kitchen`, `library_reading_room`, `library_stack`, `locker_room`, `mall`, `mercantile`, `storage_stock_shipping`, `parking_garage`, `residential`, `rink_pool`, `pool_deck`, `stage_platform`, `warehouse` (the table's rows, in its order: `new_york_state_building/5_building_code_rules/drafted/records/occupant_load_factors.yaml` gives each one's factor, gross or net, and row). Stated, never guessed: a host may suggest one from the room's name (BEDROOM, LIVING: `residential`; STORAGE: `storage_stock_shipping`), shown with its basis and written only when the architect accepts it. The Building Code's occupant loads are worked out from it (`design_checker/occupant_load.py`: area inside the walls / the factor; a gross factor as two readings, the room's own area and grossed up by the story's corridors, stairs and walls; at most one occupant per 7 sq ft where 1004.5.1's increase isn't ruled out). A value not in the list is said, and the room's load not worked out | the room's occupant load, and its story's, aren't worked out (needs review); a corridor, an exit enclosure, or a closet or toilet with none holds no load of its own (an accessory storage room with none is like any other room: Table 1004.5 gives it its own factor; a function stated on a room marked `corridor`, or on an exit enclosure, leaves its story's load not worked out); a room a closet, storeroom or toilet with a load is served through (or a chain of them) has its own load left not worked out (1004.2: theirs adds to it) |
| `unit` | a room | the name of the dwelling unit the room belongs to, as the architect states it (in Revit, the room mark Gordium: Unit; text, or a whole number): where any room of a story has one, the story's dwelling units (`story_dwelling_units`, BCNYS Table 1006.3.4(1)) are counted from the names, one unit per name, instead of grouped from the drawing ([story facts, step 3](../decisions/2026-11-25_story_facts_from_the_model.md)); blank text is no mark. Not measured where a mark isn't one name (two or more, "1A, 1B"; not text or a whole number), two names differ only in capitals or in where spaces stand, a unit's rooms on the story aren't joined through its own rooms, its lived-in rooms all state a listed other use, a room the drawing takes as an exit has one, a lived-in room with none may be a unit's (any function but a listed other use, or none), a corridor or lobby with none states such a function and opens into rooms of fewer than two named units, or an exit with none states any function. The limit left, said beside the count: a unit's room left unmarked and marked a corridor, lobby or exit can't be told from a room shared between units | no room of the story marked: its units are grouped from the drawing |
| `fire_rating_hours` | a room whose `use` is `corridor` | the fire-resistance rating of the corridor's walls, in hours (`0` where they aren't rated; the least, where its walls differ), as the architect states the assemblies (BCNYS Table 1020.2; the NFPA 101 corridor rules Maine reads). A wall type's rating is the architect's statement of its assembly, so it is stated, never measured; in Revit the room mark Gordium: Corridor rating minutes, in minutes | the corridor's rating isn't stated: every rule reading it needs review |
| `walls_smoke_partitions` | a room whose `use` is `corridor` | true or false: the corridor's walls form smoke partitions (NFPA 101 2012 8.4), as the architect states it (in Revit, the room mark Gordium: Smoke partition walls) | the same, for the rules reading it |
| `holes` | a room | the outline of each column or chase inside it (`[]` for none) | the room isn't read: its story's routes need review |
| `obstructions: [{outline, kind, fixed}]` | a room | the plan footprint of each piece of casework, furniture, equipment or fixture (`kind`: `casework`, `furniture`, `equipment`, `fixture`; `fixed` true or false); every one counts (`[]` for none) | the room isn't read: its story's routes need review |
| `plan: {centre, along, clear_width, wall_thickness}` | a door | its clear opening's centre in the middle of the wall, a direction along the wall, the clear width, the wall's thickness | the door isn't read: its story's routes need review |
| `sides: [a, b]` | a door | what it joins: two room ids, or a room id and `outside` | the same |
| `exit_kind` | a door | which exit it is, in IBC 1016.1's own list: `exterior_at_discharge`, `exit_enclosure`, `exit_passageway`, `horizontal_exit`, `exterior_stair_or_ramp` | not an exit (exits are marked, never guessed) |
| `exit_id` | a door with `exit_kind` | which exit it enters: every door into one stair enclosure carries the same id | the door isn't read (an `exit_id` with no `exit_kind` isn't read either) |
| `stated_clear` | a door (as in the doors table above) | for the 2025 Building Code's door rules (BCNYS 1010.1.1, `model_measurement/routes/doors.py`) the door's ONLY source of its clear width and height: never its size, its leaf or a plan width alone. Every other figure given for a size (the plan's `clear_width`; the drawn door's stops, hinge pin and leaf, or its threshold and head stop) must agree with it within 1/16 in, the smallest counting where they agree; where one disagrees or the drawing can't be measured, that size isn't measured (the house reading instead takes the smaller of drawn and stated) | the door's clear width and height aren't measured: the Building Code's door size rules need review for it |
| `operation` | a door (as in the doors table above) | for the Building Code's door rules (section group 6b): `side_hinged` is a swinging door (BCNYS 1010.1.2's side-hinged, pivoted or balanced kinds); `sliding`, `folding` and `pocket` aren't; `other` may be a pivoted or balanced door or not | the door's kind isn't known: 1010.1.2's flag and 1010.1.2.1's swing need review for it |
| `swings_into` | a door | which of its two sides (a room id, or `outside`) its leaf swings into, as the architect states it (in Revit, read from the swing its plan symbol draws, never from its facing or hand: not sent where that drawing doesn't settle it). Against the side egress travel goes into through it, as the routes find it (known only where travel crosses the door one way alone: into an exit stair or passageway where it can't be the exit's discharge, its room having its own door marked an exterior exit door at discharge on the story, or the story none to outside; outside through an exterior exit door at discharge only (any door to outside not marked an exterior exit door at discharge, a stair's own included, not known: it may be a patio's, a walkway's or a balcony's way in), not known through any other exit door to outside (a stair's door onto a roof); else away from the one room it is an exit access door of, where that room is stated end-only (a horizontal exit: not known)), it says whether the door swings in the direction of egress travel (BCNYS 1010.1.2.1) | not measured: the swing rule needs review wherever the door may serve 50 or more or a Group H occupancy |
| `leaves` | a door | how many leaves its opening has: `1`, or `2` for a pair with no mullion between them (BCNYS 1010.1.1 asks one leaf of such a pair for the 32 in clear); a pair with a mullion is two openings, each needing the 32 in: `1` only where its stated clear width is the narrower leaf's own opening, else `2`, as the architect states it (in Revit, the door type's Gordium: Leaves) | not measured: the Building Code's door width rule needs review at 32 in or more (a pair isn't ruled out); under 32 in it fails as for any door (one leaf is never wider than the opening) |
| `hardware` | a door | what latches or locks it, as the architect states it (no Revit mark yet), for the Building Code's panic hardware rule (BCNYS 1010.2.8, section group 6e): `panic` (its only latch or lock is panic hardware or fire exit hardware), `panic_electric` (panic or fire exit hardware and an electric lock it releases: 1010.2.8 exception 2 allows it only in Groups A and E, per 1010.2.10, never in Group H), `latch` (any other latch or lock) or `none` (no latch or lock) | not measured: 1010.2.8 needs review for a swinging door in a building that may be Group H, or Group A or E unless the door's load is stated under 50 (two or more groups, or none stated, included); a door stated under 50 in Group A or E, or in a building of one other group, complies whatever its hardware |
| `passages: [{rooms: [a, b], line}]` | the description | two rooms joined with no wall or door between them (a room separation line), the line where they meet (`[]` for none) | no story's routes are measured |
| `story_outlines: [{level, outer, inner}]` | the description | the outside faces and the inside faces of each story's exterior walls | the diagonal and the story's area aren't measured |
| `outline` | an unknown space | where it is | (an unknown space on a story makes its routes need review either way) |

Which rooms a route may cross (decision 1a): a **corridor**, or a room marked `pass_through: true`, either one with
`lockable: false` and `pass_through` given. Every other room is **end-only**: kitchens, accessory storage, toilets,
closets, workrooms, sleeping rooms, a room that can be locked, and a room whose `use`, `lockable` or `pass_through`
isn't given. `pass_through: true` on an end-only use, a sleeping room or a room with `lockable: true` is refused:
the room isn't read and its story's routes need review. A closet, accessory storage or toilet whose every opening is
a door into one end-only room with its `use` given and `lockable: false` is taken as part of that room (Gordium's
reading, shown with the figures it reaches, which never pass until it is confirmed: route note decision 1a and
open question 11): its route leaves through
that room, never across another end-only room.

A door's centre sits in the middle of its wall, so each of its rooms is found by geometry: that room's face of the
opening (half the wall's thickness from the centre) is on the room's outline, within 1/16 in. A door under 24 in
clear needs review (its centre is inside its jambs' 12-in rings), as does an exit to an exterior stair or ramp
(travel along it isn't measured yet). A story also needs review while it has an unknown space, a room with no
`floor`, a room or door that isn't read, a door onto a room that isn't read, two rooms that overlap, or no door
marked as an exit.

## The building block (which New York code governs)

An optional `building` mapping: the architect's statements about the whole building that decide which New York code
its egress is checked against and that the Building Code's rules read (`design_checker/code_scope.py`;
[docs/decisions/2026-11-22_which_ny_code.md](../decisions/2026-11-22_which_ny_code.md)). Each key only when stated
(the Revit add-in sends one only from a mark that is set, `BuildingFacts`); a key left out is not stated, and where
the decision needs it the check says which to state. A value of the wrong kind is said, never used.

```yaml
building:
  follows_building_code: true          # RCNYS R101.2's exception: the Building Code applied to a house it covers
  stories_above_grade_plane: 2         # RCNYS R202 STORY ABOVE GRADE PLANE, a whole number 1 or more
  separate_means_of_egress: true       # each dwelling unit has its own (R101.2 item 2)
  townhouse_units: true                # every unit is an R202 TOWNHOUSE UNIT
  care_facility: false                 # people outside the household receive care here (BCNYS 308.2.4, 310.4.1)
  occupancy_groups: [R-2]              # BCNYS Chapter 3 groups (A-1 ... U)
  sprinkler_system: none               # none, nfpa_13 (903.3.1.1), nfpa_13r (903.3.1.2), nfpa_13d (903.3.1.3)
  egress_balcony_increase_taken: false # BCNYS 1017.2.1 (a fact the Building Code's flags read)
  building_has_atrium: false
  assembly_fixed_seating: false        # rooms used for assembly with fixed seating (BCNYS Table 1006.2.1 note c);
                                       # true whatever is stated where a room states assembly_fixed_seats
  r2_sleeping_units: false             # every Group R-2 unit a sleeping unit (true) or a dwelling unit (false); left out
                                       # for a building of both (Table 1006.3.4(1) note b: neither table fits every story)
  emergency_escape_openings_1031: true # emergency escape and rescue openings per BCNYS 1031 (Table 1006.3.4 note a)
  special_egress_spaces: false         # a space the BCNYS gives its own exits or travel limit: a covered or open
                                       # mall (402.8), a Group I-2 care suite (407.4.4), a special amusement area
                                       # (411), an aircraft manufacturing facility (412.6), a boiler, incinerator or
                                       # furnace room (1006.2.2.1), a refrigeration machinery room (1006.2.2.2), a
                                       # refrigerated room (1006.2.2.3), an electrical room (1006.2.2.4), a vehicular
                                       # ramp (1006.2.2.5), a temporary structure (3103.4), a pedestrian walkway (3104.9)
  merchandise_pads: false              # Group M merchandise pads (BCNYS 1018.4: their own common path)
  occupant_load_increased: false       # the design takes BCNYS 1004.5.1's increased occupant load (up to one per
                                       # 7 sq ft); not stated, the occupant loads' upper reading is at least that
  mezzanines: false                    # the building has a mezzanine (BCNYS 505.2: an intermediate level within a
                                       # story); its occupants add to a room on an adjacent level (1004.2.2)
  loads_not_by_area: false             # any area's occupant load Table 1004.5 counts by something other than its
                                       # floor area, in any use or group: fixed seats or benches (1004.6), bowling
                                       # lanes, a concentrated business use (1004.8), a mall (402.8.2); only where
                                       # this, mezzanines and occupied_outdoor_areas are all false is a story's
                                       # floor area / 5 the most its spaces hold (design_checker/occupant_load.py)
  other_level_egress_into_corridors: false  # another level's occupants reach a corridor: an unenclosed exit access
                                       # stairway or ramp (BCNYS 1019), a mezzanine (1004.2.2), stairs converging
                                       # (1005.6) or an exit stair discharging into one; only where false is a
                                       # corridor's occupant load bounded by its story's (1004.2.3; Table 1020.3)
  ambulatory_care_facility: false      # the building is or holds an ambulatory care facility (BCNYS 202, 422):
                                       # Section 422's flags (false sets them aside), Table 1020.2's Group B
                                       # corridor rating (422.2's fire partition) and Table 1020.3's 72 in for
                                       # corridors serving stretcher traffic
  corridors_within_dwelling_units: false  # a corridor is inside a dwelling unit or sleeping unit (BCNYS 1020.2
                                       # exception 2: no rating there in Groups I-1 and R; Table 1020.3: 36 in)
  emergency_voice_alarm_system: false  # an emergency voice/alarm communication system per BCNYS 907.5.2.2 (with a
                                       # 903.3.1.1 or 903.3.1.2 sprinkler system: 1005.3's smaller capacity factors)
  high_rise_building: false            # a high-rise (BCNYS 202: an occupied floor or occupiable roof more than 75 ft
                                       # above the lowest level of fire department vehicle access) or more than 420 ft
                                       # in building height (403.2.2, 403.5.2): Section 403's flags and the story exit
                                       # rules' additional stairway (403.5.2)
  underground_building: false          # a floor level used for human occupancy more than 30 ft below the finished
                                       # floor of the lowest level of exit discharge (BCNYS 405.1): Section 405's flags
                                       # and each floor level's two exits (405.7.1)
  stages_or_platforms: false           # a stage, a platform or a technical production area (BCNYS 202): Section
                                       # 410.5's flags, and Table 1006.2.1's 125 ft rows (Groups R-2, R-3 and R-4)
                                       # held to 410.5.3.3's 100 ft common path
  aircraft_related_occupancy: false    # an airport traffic control tower, an aircraft hangar (a residential one
                                       # too), an aircraft paint hangar, an aircraft manufacturing facility, a
                                       # heliport or a helistop (BCNYS Section 412): its flags, and Table
                                       # 1006.2.1's Group U row held to 412.4.2's two means of egress
  service_corridors: false             # a service corridor (BCNYS 202: a fully enclosed passage used for
                                       # transporting HPM and purposes other than required means of egress): in
                                       # Group H-5 or two or more groups, 415.11.3's flags and 1020.3's capacity
                                       # held to 415.11.3.4; in Group H-5, Table 1017.2's H-5 row, Table
                                       # 1006.3.4(2)'s one-exit stories, 1020.5's dead ends and Table 1020.3's width
                                       # held to 415.11.3.3 and 415.11.3.4
  assembly_spaces: false               # a room or space used for assembly purposes, whatever the building's group
                                       # (BCNYS 1030.1; 303.1.1 and 303.1.2 put small ones in Group B or the main
                                       # occupancy): Section 1030's checks show where true or not stated. Also true
                                       # where any room states a Table 1004.5 Assembly function (gaming_floor,
                                       # exhibit_gallery_museum, assembly_fixed_seats, assembly_concentrated,
                                       # assembly_standing, assembly_unconcentrated, bowling_center), whatever is
                                       # stated; a stated false is not read where a room states courtroom,
                                       # library_reading_room, exercise_room, rink_pool, pool_deck, stage_platform or
                                       # airport_waiting (each may be an assembly use). Never false from the rooms: a
                                       # description may hold only some floors
  facts_not_sent: [dwelling_units]     # lot facts the host had a value for but couldn't send
```

`facts_not_sent` names lot facts whose value the host holds but couldn't send. An example is a count below its least (Gordium: Dwelling units 0), sent with the Revit add-in's Check now anyway. The code decision reads each one as stated but unread, so it needs review and names the fact. It never reads one as not stated. A fact the architect simply left blank is not listed: it is not stated.

## What comes back

```yaml
format: gordium.interior_measured/1
units: {length: in, area: sf}
parts:
  sleeping_room: [{id, name, measures: {...}, not_measured: {measure: reason}, more: {...}}]
  emergency_escape_opening: [{id, name, within: <room id>, measures, not_measured, more}]
  stair: [...]
  egress_door: [{id, name, measures, not_measured, more, from: {measure: {used, drawn, stated, source, why}}}]
  guard: [...]            # not a part kind in rule_format/parts.yaml yet
problems: [...]           # why a kind wasn't read (a has_none claim not taken among them)
not_checked: [...]        # escape openings in rooms that aren't sleeping rooms
has_none: {kind: {source, reading, words, parts, openings, stairs}}   # every claim taken
```

A claim taken makes each of its part kinds `[]` in `parts`, and gives each escape opening (or stair) its measures, each such part naming in `stated` which claim gave which measure. The checker shows one item per claim, "Ramps: not applicable", with the source and every rule it set aside (a claim marked `reading`, needs review: "… not applicable if this reading is confirmed"); never a pass, and never hidden.

`parts` is exactly what `rule_format.parts.rows` and `design_checker.each_part.check_parts` read: a kind not read is `null`, so its rules need review. `measures` holds only the names `rule_format/parts.yaml` gives the part's kind; `more` holds other values worked out but not yet handed to the rules; a `parts.yaml` measure kept there is listed in `not_measured` as `in_more_not_rules`, and one not worked out at all as `not_measured_yet`.

Running one by hand: `python -m model_measurement.interior <description.yaml>`.
