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
| `level` | each room, door and unknown space | the id of the story it is on | no story's routes are measured (a part that can't be placed) |
| `use` | a room | one of `corridor`, `lobby`, `day_care`, `accessory_storage`, `kitchen`, `toilet`, `closet`, `workroom`, `other` | the room is end-only (a route may start in it, never cross it) |
| `lockable`, `pass_through` | a room | true or false: whether it can be locked; whether the architect states it is accessory to the rooms it serves, with a discernible path to an exit (IBC 1014.2 item 1) | the room is end-only |
| `holes` | a room | the outline of each column or chase inside it (`[]` for none) | the room isn't read: its story's routes need review |
| `obstructions: [{outline, kind, fixed}]` | a room | the plan footprint of each piece of casework, furniture, equipment or fixture (`kind`: `casework`, `furniture`, `equipment`, `fixture`; `fixed` true or false); every one counts (`[]` for none) | the room isn't read: its story's routes need review |
| `plan: {centre, along, clear_width, wall_thickness}` | a door | its clear opening's centre in the middle of the wall, a direction along the wall, the clear width, the wall's thickness | the door isn't read: its story's routes need review |
| `sides: [a, b]` | a door | what it joins: two room ids, or a room id and `outside` | the same |
| `exit_kind` | a door | which exit it is, in IBC 1016.1's own list: `exterior_at_discharge`, `exit_enclosure`, `exit_passageway`, `horizontal_exit`, `exterior_stair_or_ramp` | not an exit (exits are marked, never guessed) |
| `exit_id` | a door with `exit_kind` | which exit it enters: every door into one stair enclosure carries the same id | the door isn't read (an `exit_id` with no `exit_kind` isn't read either) |
| `passages: [{rooms: [a, b], line}]` | the description | two rooms joined with no wall or door between them (a room separation line), the line where they meet (`[]` for none) | no story's routes are measured |
| `story_outlines: [{level, outer, inner}]` | the description | the outside faces and the inside faces of each story's exterior walls | the diagonal and the story's area aren't measured |
| `outline` | an unknown space | where it is | (an unknown space on a story makes its routes need review either way) |

Which rooms a route may cross (decision 1a): a **corridor**, or a room marked `pass_through: true`, either one with
`lockable: false` and `pass_through` given. Every other room is **end-only**: kitchens, accessory storage, toilets,
closets, workrooms, sleeping rooms, a room that can be locked, and a room whose `use`, `lockable` or `pass_through`
isn't given. `pass_through: true` on an end-only use, a sleeping room or a room with `lockable: true` is refused:
the room isn't read and its story's routes need review.

A door's centre sits in the middle of its wall, so each of its rooms is found by geometry: that room's face of the
opening (half the wall's thickness from the centre) is on the room's outline, within 1/16 in. A door under 24 in
clear needs review (its centre is inside its jambs' 12-in rings), as does an exit to an exterior stair or ramp
(travel along it isn't measured yet). A story also needs review while it has an unknown space, a room with no
`floor`, a room or door that isn't read, a door onto a room that isn't read, two rooms that overlap, or no door
marked as an exit.

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
