# Revit port: how the add-in reads a house's inside for egress (design note)

**Purpose:** the plan for how the Revit add-in turns a Revit model's rooms, windows, doors, stairs and railings into Gordium's [interior description](../interior/interior_description_format.md) (`gordium.interior/1`), and how that reaches the checker, so New York's egress rules can run on a Revit model end to end. Agreed by Ben (section 8) before any code.\
**For:** Ben; whoever writes the Revit interior reader; reviewers checking that nothing it sends could turn a "needs review" into a "complies".\
**Kept current by:** the PR that builds each step below, as it settles a "to check"; any PR that changes the interior description, the worker's `check_site`, or one of the decisions here.

**Status: agreed by Ben, 2026-11-19** (his four decisions are in section 8). Each step of section 7 is its own
PR; step 1 (protocol 1.2: the worker and the C# client take an interior) is built; step 2 (the marks and the marking
list, [the add-in's README](../../apps/revit_addin/README.md#the-architects-marks-interior-step-2)) is built and
tried in Revit 2027.4 on Snowdon Towers (section 9); step 3 (rooms and marked escape windows,
[README](../../apps/revit_addin/README.md#rooms-and-escape-windows-interior-step-3)) is built and tested on fake
records and recorded in Revit 2027.4 (houses 1, 2 and 5, trial run 6, 2026-11-20: every measure of the step equal
to the hand-worked one); step 4 (stairs, [README](../../apps/revit_addin/README.md#stairs-interior-step-4)) is built
and tested on fake records and recorded in Revit 2027.4 (houses 1, 2, 3 and 5, 0 problems each: house 2's stair
16 risers of 7.5 in, 10 in treads, 85.5 in headroom, 36 in wide; house 3's tall riser at the head held for review); the
rest are not yet.

The outside of the building (the lot, the massing, the yards and height) has its own note:
[revit_reading_design.md](revit_reading_design.md). This note is the inside: what egress needs. Words used here:
a **host** is a design program (Rhino, Revit); a **reader** is the add-in code that looks at the model and writes a
description; the **worker** is Gordium's checker running as its own program; a **mark** is a yes/no the architect
sets on an element (this room is a bedroom; this window is its escape window).

## 1. Egress end to end, and what is missing

How a Revit model would get an egress verdict, start to finish. Steps 1 to 3 and 6 to 7 are built and tested; steps
4 and 5 are this note.

| # | Step | Who | Built? |
|---|---|---|---|
| 1 | New York's Residential Code (2025) brought in, its numbers double-checked | Code | Yes ([2026-11-12](../decisions/2026-11-12_building_code_text.md)) |
| 2 | Egress sections drafted into rules by AI, checked by code and against an independent answer key | AI drafts, code checks | Yes, 47 sections ([2026-11-13](../decisions/2026-11-13_house_egress_rules.md), [2026-11-14](../decisions/2026-11-14_house_egress_remaining.md)) |
| 3 | The interior description: rooms, escape openings, stairs, doors, guards as plain geometry, the same whatever the host | Engineers | Yes ([format](../interior/interior_description_format.md)) |
| 4 | **The Revit reader writes that description from the model** | Engineers, this note | **No** |
| 5 | **The add-in sends it with each check** (the worker's `check_site` takes an `interior`) | Engineers, this note | **Partly** (protocol 1.2, section 7 step 1): the worker's `check_site` and the C# client take and send one; the add-in has nothing to send until the reader exists (row 4), and keeping each check's interior beside its saved report comes with section 7's step 3, the first that sends one (section 5) |
| 6 | The interior measured (clear opening, riser height, guard height…) | Engineer code, no AI | Yes ([measurements](../interior/interior_measurements.md); five hand-worked houses pass) |
| 7 | The rules run on the measures; rows shown, each citing its section | Code | Yes (Ithaca's check runs New York's house rules since 2026-11-14) |

Today a Revit check says "Egress waiting: no rooms drawn yet" (seen in the trial, 2026-11-19), which is correct:
no interior is sent, so egress waits, never passes.

## 2. The rule behind every choice: the architect marks, the model measures, the reader never guesses

Egress turns on facts only the architect can state: which room is a bedroom, which window is its escape window,
which door is the required exit door. The interior description already insists on this: every room must say
`sleeping: true|false`, every opening `escape`, every door `exit`, and **one missing means none of that kind is
read** (needs review), so a bedroom nobody marked is never quietly not a bedroom. The Revit reader keeps that
exactly:

- **A mark never set is sent as not given**, so the whole kind is not read and its rules need review. It is never
  read as "no".
- **Nothing found is never "none".** An empty list (`stairs: []`, `openings: []`, `doors: []`, `guards: []`) tells the
  checker the house has none, so their rules become not applicable. The reader sends one only when the architect
  has ticked "this house has none" in the marking list (the same flow as `has_none`). With no tick and no element
  found (a stair drawn as a generic model, a guard drawn as a wall), the list is **left out**: not read, needs review.
- **"All of them" is said too, for the kinds where a missing one hides a failure.** A stairs list with one stair
  found and another missed would let the missed one go unchecked (its rules run once per part found). So rooms,
  stairs and guards are sent only when (a) the reader finds nothing that could be one of them outside what it reads:
  no in-place or generic family in the Stairs, Railings or Generic Models categories, no sketched stair, no
  multistory stair (`MultistoryStairs`, or a `Stairs` with a `MultistoryStairsId`: its copies on other levels are
  not runs of any stair the reader walks, so reading them is designed and tested first), no closed workset, no
  unloaded link, no coordination model (for rooms: the completeness rule below); and (b) for stairs and
  guards, the architect has ticked "these are all the stairs" / "all the guards" in the marking list. Otherwise that
  kind's list is left out (not read, needs review). Windows and doors don't need it: one missed can only make a
  bedroom or the house fail (no escape opening, no exit door), never pass.
- **A part found is never dropped.** The format has no place for a reader to report a problem, so the only safe ways
  to say "can't read this" are the format's own: a part found but not readable exactly is sent **with only the
  values it can't read left out** (a winder flight with no `nosings`), so those measures get no value and their rules
  need review; and where a whole kind can't be read (a sketched stair), that kind's list is left out. Dropping a part
  would make the house look like it has fewer of them, with nothing to say so. The format carries no reason for a
  value left out (the checker shows the measuring code's own words, such as "not given"), so the add-in shows its own
  reason beside the row ("this window's Clear width was entered for a 34 x 48 type"), never in the description.
- **Every room counts, Room element or not.** A bedroom drawn as walls with no Revit Room in it would never reach
  `rooms`. So the reader also looks for enclosed areas with no Room on each level, and for Rooms that are unplaced,
  not enclosed or redundant, and for any closed workset or unloaded link (a room could be in it); while any exists,
  it is listed first in the marking list and `rooms` is left out (not read), until the architect places a Room or
  says the area isn't a room. **Built in step 3:** the enclosed areas are Revit's own plan circuits, every level's
  for the last phase (`Document.get_PlanTopology(level, phase).Circuits`, each `PlanCircuit.IsRoomLocated`), the
  ones Revit's own "place rooms" uses; an area that isn't a room is said by placing a Room in it marked Sleeping
  room No (no other way of saying it is built yet). To confirm in the trial: that a circuit with no Room shows as one
  on real models.
- **The reader may propose, never decide.** A room named "Bedroom 2" can be shown as a suggestion in the add-in's
  marking list, marked "suggested"; it is sent as `sleeping: true` only once the architect has accepted it
  themselves, a fact about their own design. A suggestion alone is never sent.
- **Measured from what is drawn; a typed number is a cross-check.** Revit stores some values twice: what the
  architect typed (a stair's "Actual Riser Height") and the shape drawn. The reader sends the drawn shape, and
  where the typed value disagrees with it by more than 1/16 in (the measuring code's drawing-noise allowance), the
  drawn values it checks are left out (as above), so their rules need review. (This answers Ben's best-practice
  question of 2026-11-19, item 3.)
- **Anything the reader can't read exactly is left out**, never smoothed (a curved stair, a sloped ceiling with
  curved faces), the add-in naming why beside the row: as the outside reader does, principle 4.

## 3. The marks: how the architect states the facts

**Agreed (Ben, 2026-11-19, section 8): Gordium shared parameters**, added to the project by the add-in on first use:

| Parameter | On | Values | Feeds |
|---|---|---|---|
| `Gordium: Sleeping room` | Rooms | Yes / No / unset | `rooms[].sleeping` |
| `Gordium: Escape opening` | Windows, Doors (instance) | Yes / No / unset | `openings[].escape` |
| `Gordium: Exit door` | Doors (instance) | Yes / No / unset | `doors[].exit` |
| `Gordium: Operation` | Windows, Doors (type) | One architect-facing list (casement, double hung, side-hinged door, sliding door, …) | `openings[].operation` and `doors[].operation`, each through a fixed table to that list's own word (`side_hinged_door` for an opening, `side_hinged` for a door): the two lists use different words |
| `Gordium: Clear width`, `Clear height`, `Clear offset`, `Clear source`, `Clear confirmed` | Windows (type) | The maker's net clear opening; the height of its bottom above the window's sill line (the line Revit's Sill Height places), required (blank: no clear opening sent, never read as 0); the maker's publication it came from; and **the confirmation stamp**: written by the add-in only when the architect ticks the values on a section of that window type (facts about their own design), it records exactly what was confirmed, who and when: **the type itself** (its `UniqueId`), its width and height, its `Gordium: Operation`, the clear width, height and offset, the `Clear source`, and, where the clear opening was copied from a maker's family parameter, that parameter's name and value. The reader sends a clear opening only when every one of these, read now, equals the stamp: so a duplicated or copied type (Duplicate, Transfer Project Standards and copying between projects carry the stamp with them, but not the original's `UniqueId`), a resized type, any edited value (an offset typed or bulk-filled as 0 in a schedule, a changed source or operation), or a maker's value that has since changed (a hardware option switched) all leave the window unconfirmed until the architect ticks it again. Confirmed per type: the add-in offers the value of another type of the same family as a suggestion, never as a confirmation | `openings[].stated_clear` |
| `Gordium: Top rail is handrail` | Railings (type) | Yes / No / unset | whether a stair railing's top rail is also its handrail (unset on a stair railing with a top rail: that flight's `handrails` left out, not read) |
| `Gordium: These are all the stairs` | Project Information | Yes / No / unset | `stairs` sent only on Yes (section 2's "all the stairs"; No or unset: not read). **Decided (2026-11-20, step 4):** the project-wide ticks ("these are all the stairs", later "all the guards", "this house has none of ...") are Gordium shared parameters on Project Information (Yes/No; unset is not stated), added by Mark for egress like the other marks and listed in the marking list; each step adds its own |

Why shared parameters: architects already fill parameters, in bulk, in schedules ("select all bedroom windows, tick
Escape opening"); they are visible, print on sheets and survive export and upgrades. Considered: Revit's hidden
extensible storage (invisible to the architect, so not checkable by them, which breaks principle 5); reading room
names ("Bedroom") alone (a guess: rejected, kept only as a suggestion).

A dockable "Mark for egress" list (after the trial's go) shows every room, window and door with its marks, the
unset ones first, so nothing is left unset by accident.

## 4. From Revit elements to the interior description

Units: Revit works in feet internally, so the description is sent with `units: ft`. Coordinates: the same
shared-coordinates turn as the outside reader ([revit_reading_design.md](revit_reading_design.md), section 3), in
one place, so the interior and the site line up.

**Which elements.** The outside reader's rules apply to every interior element, from the same one place: the last
phase only (nothing demolished or temporary by then), and the main model plus the option being edited or each set's
primary ([revit_reading_design.md](revit_reading_design.md), section 1). Rooms, windows, doors, stairs or railings
found inside a linked model leave that kind not read (its list left out) until reading a linked interior is
designed: a house drawn in a link can't pass egress unread.

**What is over or beside a part, links included.** A stair's `overhead` and `sides`, a room's `ceilings` and the
floor cross-checks are gathered from everything there, whatever its category: a beam, a duct, a soffit, a column. A
house's structure is often in a loaded structural link, and a beam there over a stair would never be seen in the
main model, making the headroom look higher than it is. So, until reading a linked model's elements (through the
link's placement, at any depth of links inside links) is built and tested, **any loaded link whose box reaches a
flight's or a room's plan leaves that flight's `overhead`, `sides`, `bottom_elevation` and `nosings`, or that room's
`ceilings`, `floor` and `floor_elevation`, out** (needs review). The add-in names the link beside the row.

**A cross-check that can't be made counts as a failed one.** Wherever a value is sent only once something drawn
agrees with it (a room's floor against its slab, a flight's foot and head against the floors there, a window's
bottom and size against the window), finding nothing to check against (no slab under the whole room, two slab tops
at different heights, no floor face under the first riser) means the value is not sent, exactly as when the two
disagree.

### Rooms (`rooms`)

| Field | From Revit | To check |
|---|---|---|
| `id`, `name` | `Room.UniqueId`; the room's Name and Number | |
| `sleeping` | The `Gordium: Sleeping room` mark (unset: not given) | |
| `floor` | `Room.GetBoundarySegments` with `SpatialElementBoundaryLocation.Finish` (the finished wall faces, which the format asks for), whatever the project's own room setting is. Checked against what stands inside it: a wall, column or other building element (not furniture, casework or fixtures, as for ceilings; nor a window or door hosted in a wall bounding the room, which is part of that boundary, though its trim may reach in: only windows and doors, anything else such a wall hosts, a bulkhead or a shelf, counts like any other element) crossing the room's plan inside the outline that doesn't bound the room (its "Room Bounding" off, or a wall shorter than the room's computation height) means no `floor` (the room may be two rooms, or smaller than its outline). A room with more than one boundary loop (a column or a chase standing inside it) has no `floor` sent (needs review): the format's floor is one outline with no holes, and a hole is a format change of its own | That Finish gives the wall finish face for every wall type; a curved boundary segment: the room's floor not sent (needs review), never its chord |
| `floor_elevation` | The room's level elevation plus its base offset, sent only when the top face of the floor slab under the whole room agrees with it within 1/16 in. No slab top found under the whole room, more than one at different heights, or a disagreement: not given (a window's sill height is worked from this floor, so an unchecked floor could make a high sill read low) | Finding the slab top under a room |
| `ceilings` | The lowest undersides over the room's plan, between its floor and the floor above, of everything there that is building or services (a ceiling, a beam, a bulkhead, a soffit, a duct, a pipe, the floor or roof above): furniture, casework, furniture systems, plumbing fixtures, specialty equipment and lighting fixtures are not ceilings and are left aside, as is a window or door hosted in a wall bounding the room (never anything else that wall hosts: a wall-hosted bulkhead is a ceiling), and anything in a category the reader can't place in either list leaves `ceilings` out, so what is unknown stays on the safe side: their downward planar faces, as flat pieces of absolute 3D points covering the whole floor. Anything there it can't read exactly (a curved face, a link: above): no `ceilings`. Always `ceilings`, never `ceiling_height` (a height above the floor would be worked from a floor elevation the reader may have held back): the measuring code works the height from `floor_elevation`, and gives none when it is missing | How to collect "what is above the room" exactly (each element's lowest faces clipped to the room's plan); a curved ceiling face: not given |

The room's own "Unbounded Height" or "Limit Offset" is never used as the ceiling: it is a calculation volume, not
a drawn ceiling.

### Escape openings (`openings`)

| Field | From Revit | To check |
|---|---|---|
| `room` | The window's or door's `FromRoom` / `ToRoom` for the last phase: the room inside | Which of the two is inside for a door between two rooms |
| `escape` | The `Gordium: Escape opening` mark | |
| `operation` | The `Gordium: Operation` type parameter (Revit families don't say how they open in any standard way) | |
| `stated_clear` | Width and height from the `Gordium: Clear …` parameters (makers publish the net clear opening), with `Clear source`, sent only when every check holds: everything the type's `Clear confirmed` stamp records (section 3: the type's `UniqueId`, size and operation, the clear width, height, offset and source, and a mapped maker parameter's current value) equals its value read now (a duplicated or resized type, or any value edited or changed since the architect ticked it, then sends none; a family sized per window, or with size parameters of other names, has no type Width and Height to match, so none is sent either), and the clear opening fits inside the window as placed, in absolute heights (the clear bottom no lower than the placed geometry's lowest point, the clear top no higher than its highest, Clear width no more than its width, 1/16 in to spare). `bottom` = the instance's level elevation + its Sill Height + `Clear offset` (the maker's height of the clear opening's bottom above that sill line). `Clear offset` blank (never read as 0): no `stated_clear`. **The sill line is checked against something drawn that doesn't come from the Sill Height parameter**: the bottom of the opening the window cuts in its host wall (or the family's Bottom reference); disagreeing by more than 1/16 in, or not found: no `stated_clear`. Not the family's lowest drawn point: exterior sills and trim hang below the unit on most real windows. **Shown possible in the trial** (section 9; step 3): the wall opening is the host wall's faces whose `Element.GetGeneratingElementIds` name the window, and on houses 1, 2 and 5 its bottom equals the sill line exactly. A window that cuts nothing found sends no `stated_clear`, so its size and sill need review: a sill read from a typed number alone is never enough for R319.2.3 (44 in at most). `HostObject.FindInserts` is not used: it listed no inserts even on walls the windows had cut | The Bottom reference (`FamilyInstance.GetReferences`), and real makers' families (whose rough openings may be larger than the unit): to try |
| `frame`, `sashes`, `hinged` | **Not sent by the first reader.** A family's sash geometry is modelled differently by every maker and firm (or not at all), so reading it would be guessing. The measuring code uses the maker's opening alone when no frame is given (`model_measurement/interior/openings.py`); a window with neither gets no value (needs review) | Later, perhaps: families that carry Gordium's own frame and sash parameters |
| `ground_outside` | The ground at the opening's outside face, only from a ground the architect gave: the Toposolid picked as the ground (as the outside reader's `terrain`), probed 1 ft outside each end of the opening, or finished spot grades there; else **not given**. Never the lot facts' flat ground: that is often Gordium's own assumption (`ground_assumed: "flat"`), and an assumed ground could make a window a grade-floor opening, which needs only 5 sq ft (R319.2.1 exception) | Probing a Toposolid (as the outside reader's to-check) |
| `area_well` | Not in Revit's vocabulary. First reader: not given. An opening whose clear bottom is below the ground outside is sent with no `ground_outside` (its grade-floor reading needs review), and the marking list asks the architect to draw its well; R319.4's well rules, which need the well, need review | How firms draw wells (a generic model, an in-place family) |

### Stairs (`stairs`): one entry per flight

| Field | From Revit | To check |
|---|---|---|
| a flight | Each `StairsRun` of a component `Stairs`, every one sent (the list only as section 2's "all the stairs" allows). A winder or spiral run (the format measures only straight flights) is sent with its `bottom_elevation` and no `nosings`, so its measures have no value and its rules need review | A sketched (non-component) stair: the whole `stairs` list left out (not read) |
| `bottom_elevation` | The top face of the floor or landing drawn under the first riser, in the same shared coordinates as the nosings; cross-checked against the run's own base (made absolute). More than 1/16 in apart, or no floor or landing face found under the first riser: not sent (the flight's measures need review). The top nosing is checked the same way against the floor or landing at the head; none found there, or a disagreement: no `nosings` | Finding the floor face under the first riser |
| `nosings` | From the run's drawn geometry: the front edge of each tread's top face, bottom to top, then the landing or floor edge at the top | That tread top faces are separate planar faces in the run's solid; nosing profiles (a rounded nosing) |
| cross-check | The stair's typed `Stairs.ActualRiserHeight` and `Stairs.ActualTreadDepth`, and the run's `StairsRun.ActualRisersNumber`, against the run's drawn nosings: more than 1/16 in apart, the flight is sent without `nosings` (its rules need review) | |
| `sides` | The reader searches the whole band on each side of the flight, from well inside the tread ends to past them, from the treads up to the headroom height, for anything at all. A wall face found there is the side line; else a railing's inside face above handrail height. `open` only when that search finds nothing (a wall or railing missed would make the stair look wider than it is: R318.7.1). Anything found that it can't read exactly (a generic model, a curved face): `sides` left out, the width needs review | Searching that band exactly |
| `handrails` | The stair's railings (`Stairs.GetAssociatedRailings()`): their handrails (`Railing.GetHandRails`), inner edge in plan, with their side. A top rail (`TopRail`) counts as a handrail only where the railing's type is marked `Gordium: Top rail is handrail` (a guard's top rail is usually 36 in or more up, above the handrail's 34 to 38 in) | |
| `overhead` | The downward planar faces of everything above the flight (floors, ceilings, roofs, beams), clipped to the flight's plan. Nothing found, or a curved face: `overhead` left out (the format refuses an empty list), so the headroom has no value and needs review; the flight is still sent | Collecting it exactly, as for ceilings |

**As built in step 4** (`Gordium.Revit.Reading/StairReader.cs`; the Revit layer `RevitInterior.StairsOf`), where the
table above needed settling:

- *Treads*: the run's own upward flat faces, grouped by height (a face lying wholly under another of the run's own, a
  riser board's top under its tread, is inside the run and set aside); one group per tread the run says it has, each a
  rectangle square to the run's path (`StairsRun.GetStairsPath`), its front edge the nosing. A curved face anywhere
  in the run (a rounded nosing) sends no nosings. A run ending with a riser carries that riser up to its top, so its
  geometry has one top face more than its treads (Revit 2027.4, trial step 4 runs 1 and 2: 16 for 15, house 3 13 for
  12; house 2's a sliver 1/2 in deep along the path just past the last tread, at the run's top less the 3 in tread):
  only when exactly one too many, the top one, past the last tread, no deeper than 2 in along the run and not above
  the run's top, is it taken as that riser board's top, the head's edge, never a tread. The **top nosing** is its front edge (the last riser's line), else the top tread's back edge, at the height
  of the floor or landing found there, only if that floor stops at the last riser's line: a floor at the head reaching
  back over the last tread (a landing nosing, a slab edge past the line) makes the last tread shallower than the line
  says, so no nosings are sent (review round 1); a floor's opening (the stairwell, its edge on the riser line) is
  taken out of it first, and anything there that can't be read (a mesh, a geometry Revit refused, a face with no
  outline) refuses the nosings too (review round 2). The drawing draws house 2's upper floor the way a real model has
  it: one floor at the head with the stairwell as an opening, its underside the house's 9 ft piece over the foot.
  Beside a flight, an element with only flat straight-edged faces is judged face by face (an upper floor's box spans
  its opening, so its box alone would stand it in the width). Every top group's height and extent is kept in the evidence.
- *For Ben (noted, no mark added now)*: under section 2's rule any Generic Model anywhere in a project stops stairs
  being read, with no way yet to say "this one isn't a stair".
- *Foot and head*: the floor or landing top is looked for in a 1 in strip in front of the first nosing and past the
  last riser, across the stair's width: one flat top within a foot covering the whole strip, else not found.
- *The cross-check*: every drawn riser (from the floor at the foot to the floor at the head) against
  `Stairs.ActualRiserHeight`, every tread (nosing to nosing, the last to the head's edge) against `ActualTreadDepth`,
  the counts against `StairsRun.ActualRisersNumber` / `ActualTreadsNumber`; a run that doesn't begin and end with a
  riser isn't read yet. Any of these failing, or the foot not confirmed (the first riser can't be checked), sends no
  `nosings`. A winder, spiral or sketched run sends neither `nosings` nor `bottom_elevation` (only straight flights
  are measured; its foot is read with the first straight tread, which a turning run hasn't).
- *Sides*: the band on each side, from the flight's middle to 6 in past the tread ends, from 1 in under the line of
  nosings to 80 in over it (from the first nosing to the top one). The innermost wall face there facing the flight is
  the side line, if it covers the whole band; nothing there is `open`; anything else (furniture and fixtures too, a
  column, a pipe in front of the wall, a railing, the stair's own support over its treads or rising 34 in over them)
  leaves `sides` out (review round 1: a cabinet or a light is in a stair's way, unlike a room's ceiling, so stairs
  never set furniture and fixtures aside, beside or overhead). Extents are read from flat faces' corners (exact), else from Revit's box (only ever bigger).
- *Handrails and guards*: railings are read in step 5 with the guards (the same reading of a Railing's geometry), so
  step 4 sends no `handrails` (the width at the handrail and the handrail sides need review) and a railing beside or
  over a flight leaves its `sides` or `overhead` out.
- *Overhead*: a face's opening (a floor's stairwell opening) is taken out of it exactly
  (`PlanGeometry.Subtract`); an element with some of its flat pieces over the flight under the line of nosings and
  some over it crosses the flight and leaves `overhead` out; one wholly under it (a slab under the stair) is set aside.
- *The stair element itself*: its geometry may be all its components together. With one run and no landing or
  support it is the run; else, if it has faces, a flight's sides and overhead are left out until the trial shows how
  Revit gives it (to check).
- *Nothing that could be a stair unread* (section 2): no stair not made of components (`Stairs.IsByComponent`), no
  multistory stair (`MultistoryStairsId`, or any `MultistoryStairs`), nothing else in Stairs, Railings or Generic
  Models (an in-place or loadable family, a DirectShape), no closed workset, no unloaded link, no link holding links,
  stairs, railings or generic models, no coordination model (`CoordinationModelLinkUtils`); each is listed first in
  the marking list. With no stair found, `stairs` is left out (never `[]`: that is the has-none tick, step 6).

### Doors (`doors`)

The exit door's clear width is measured from drawn geometry (`model_measurement/interior/doors.py`: the stops,
the hinge pin, the closed leaf), which door families don't model consistently. **Agreed (Ben, 2026-11-19, section 8):** add a maker's
stated clear width and height to the format for doors, as windows have (`stated_clear`), with its source, the less
favourable of drawn and stated counting when both are given. That is a change to the format and the measuring code
(engineers, its own PR, with a hand-worked house), before the Revit reader sends doors. Until then the reader sends
each door's `exit` mark and `operation` only: the width and height have no value (needs review), which is safe.

### Guards (`guards`)

Railings not on a stair (a `Railing` that no stair lists among its `GetAssociatedRailings()`; its `HostId` the floor whose edge it guards): `walking_surface` from the host
floor's top, `top` from the railing's top rail, `members` from the railing's rails, balusters and posts in its
elevation. A guard drawn as something other than a Railing (a low wall, a generic family) is not found, which is
why `guards` is sent, empty or not, only on the architect's tick (section 2). **To check:** reading balusters from a railing's geometry exactly (their spacing decides the 4 in
sphere rule). Guards along a stair: the stair's railing, `top_line` along its top rail.

### What the house has none of (`has_none`)

As the format says: the reader **proposes** (no Ramp elements; no stair of a ship's-ladder type), the architect
ticks, and only then is the claim sent, its `source` naming both ("no Ramp elements in the
model; ticked by the architect"). The add-in already reads the checker's `not_applicable` status (PR #115), which
these claims produce. Sleeping lofts are the architect's tick alone: the reader has no loft mark to propose from.

## 5. Sending it: the worker takes an `interior`

A small, additive change (protocol **1.2**, a minor version: a 1.1 worker refuses nothing it knew before):

- `check_site` gains an optional `interior` field; the worker's handler (`_check_site`,
  `design_checker/__main__.py`) passes `request.get("interior")` to `check.check_description`, which already takes it
  and hands it to `check.check_site`, which already runs egress on it and fingerprints it in the report (`interior_sha256`), so every result can be
  traced to exactly the interior it was worked out from (principle 5).
- `WorkerClient.CheckSiteAsync` gains `interior`; the add-in keeps each check's interior beside its site
  description, as decided for the site (2026-11-06). Built in step 1: the worker and the client. Built in step 3:
  a saved report keeps its interior beside it (`<report name>.interior.json`, `check.check_description`), written
  first, moved in with the site, the earlier report's set aside and put back if the new report can't be moved in,
  and never an earlier check's interior left beside a new report (a check with no interior drops it); the report
  also names it by its fingerprint (`interior_sha256`), so its egress rows can be worked out again from what is kept
  beside it.
- **Only to a worker that says it understands it.** A 1.1 worker ignores a field it doesn't know, so it would answer
  "Egress waiting: no rooms drawn yet" for a house with rooms. The add-in sends `interior` only when the worker's
  `hello` says protocol 1.2 or later; with an older worker it shows that egress can't be checked with this checker
  version, never the waiting row as if no rooms were drawn.
- This can be built and tested on the Mac first, with the five hand-worked houses sent through the worker.

## 5a. Seen from the architect's desk

What it asks of an architect, and what a real Ithaca house will still show as "needs review", said plainly so no
one mistakes a waiting row for a missing feature.

**What the architect does, once per project.** Tick each bedroom (3 to 4 Rooms), each bedroom's escape window and
the exit door (Gordium fields, which a schedule fills in bulk), and give each escape window type its maker's net
clear opening, which makers publish for egress. Many makers' Revit families already carry their own clear-opening
parameter: the architect can point Gordium at it once per family. For each type, the add-in then copies the width
and height into the `Gordium: Clear …` fields and asks the architect to confirm them, with the offset, on the
type's section; only that confirmation writes the `Clear confirmed` stamp, and nothing re-stamps it on a later
read. A later change to the type's size or to the maker's value no longer equals the stamp, so the window is
unconfirmed (no clear opening sent) until the architect ticks it again: a comparison when the model is read,
never a write to the model. `Clear source` stays the maker's publication (catalogue, product
line, a hardware option such as egress hinges), with the family parameter named beside it. The maker's parameter
gives width and height only: the offset of the clear opening above the sill line is always confirmed on the
type's section the add-in shows. Every room, window and door needs its Yes or No (a schedule fills the No's in
bulk): one left blank leaves that whole kind not read. Then tick what the house has none of, and "these are all the
stairs / guards". The marking list puts anything unset first.

**What a real house will still show as needing review**, until each is built or drafted:

| Common in Ithaca houses | Why it waits | What would end the wait |
|---|---|---|
| A basement or habitable attic | R319.1 needs an escape opening in each, but the interior format has no list for them yet (only a "has none" tick) | Basements and habitable attics added to the format and the reader (a format PR, with a hand-worked house) |
| Winders (an L-shaped stair with turning treads) | The measuring code reads straight flights only, and R318.7.5.2.1 (winders) isn't drafted | Winder measuring, and the section drafted |
| A basement escape window in an area well | Wells aren't in Revit's vocabulary; the first reader sends none | A way to draw and read wells (section 4) |
| The exit door's clear width | Door families can't be measured reliably | Doors' stated clear width (decision 2, section 8) |
| A structural or services link over a stair or room | Links aren't read yet (section 4) | Reading linked elements |

Each of these is "needs review" with its reason in the add-in, never "complies". An existing house being altered
also brings Appendix BO's questions (is the stair existing, was it lawful when built), which stay the architect's
answers: they are flags in the rules, not readings of the model.

## 6. How we will know it is right: interior conformance

The same idea as the outside's conformance suite, which caught every reader mistake it was built for:

1. **The five hand-worked houses** (`test_data/interior_houses/`: a ranch, a two-storey house with a small window, a
   tall riser, a loft, a basement window well), whose every measure was worked out by hand before the code ran,
   are drawn in Revit, read by the add-in, and recorded (`recorded/revit/<house>.json`). CI compares each recorded
   description's **measures** with the house's `expected.yaml` on every push, as it does for the outside scenes.
   Each building step (section 7) has a stated Revit scope per house: every measure in scope must equal
   `expected.yaml` exactly; every measure out of scope (a door's clear width before the doors step, a frame-drawn
   sash, an area well) must come back **not measured**, never a value. A Revit
   reading that differs either way fails. `expected.yaml` is never edited to fit Revit.
2. **New scenes for Revit's own traps**, each hand-worked first: a room bounded at wall centres instead of finish
   faces; a stair whose typed riser height disagrees with its drawn treads; a bedroom left unmarked; a bedroom with
   no Room element; a window with no stated clear opening; a floor slab offset from its level; a stair drawn as a
   generic model (stairs must come back not read, never none); a winder-only stair; a wall just inside a stair's
   tread ends; a window and a stair in a linked model; a demolished window marked as an escape opening; a window
   type duplicated to a smaller size with its clear numbers left (no stated clear opening must be sent); a component
   main stair beside a basement stair drawn as an in-place family, and a stair in a closed workset (stairs must
   come back not read); a stair whose run base disagrees with the floor at its foot; a room around a column; a
   stair under a beam in a loaded structural link (its headroom must come back not measured); a multistory stair
   (stairs not read); a bedroom with a soffit under its ceiling; a room crossed by a wall set not to bound rooms; a furnished bedroom
   (its bed and wardrobe change nothing); a bedroom whose slab is in a loaded structural link, its window 44 in above
   the level (the sill must come back not measured); and for escape windows, each expecting no stated clear opening
   (clear and sill measures not measured): Clear offset blank; Clear offset set to 0 in a schedule after the type was
   confirmed; a family whose wall opening sits 1 in below its Sill Height line; a family with no findable wall opening
   or Bottom reference; a maker's mapped value changed after confirmation; a confirmed type duplicated at the same
   size (its operation then changed, and also left unchanged); a confirmed type's Clear source edited.
3. **A real house**: 106 Ithaca Road (the architects' R-1b lot) drawn with an interior, so one Revit model gives
   zoning and egress together; its egress answers worked out by hand first.

## 7. Order of building

Each step is its own PR, through the review loop, with its tests:

1. **Protocol 1.2: `interior` on `check_site`** (Python worker + C# client), tested with the five houses on the Mac
   and CI. Small, and it unblocks every host.
2. **The marks** (shared parameters, created by the add-in) and the marking list.
3. **Rooms and marked escape windows** with the maker's clear opening: R319 (escape openings), the most common
   egress failures. A room's floor area and ceiling height are measured and recorded too, but no rule reads them
   yet (R312 and R313, room size and ceiling height, aren't brought in). The step builds the sill line's check
   against the wall opening (section 4) and shows on the five houses that it can be made; only then are the escape
   openings' clear measures in its scope. If it can't be made, they stay not measured, and the step says so.
   **Shown (Revit 2027.4, trial run 6, 2026-11-20):** on houses 1, 2 and 5 every escape window's wall opening (the
   wall faces the window generates) has its bottom on the sill line exactly, so the clear measures are in scope, and
   the three recordings give every in-scope measure as worked by hand. It includes finding enclosed areas with no Room (section 2), without which no
   `rooms` can be sent. Recorded houses 1, 2 and 5. The step's PR lists every `parts.yaml` measure of each kind as in
   or out of scope, and the `more` values compared: in scope `sleeping_room_floor_area` (and `floor_area_drawn`,
   `least_ceiling_height`), `opening_net_clear_width`, `_height`, `_area`, `opening_sill_height`, `opening_is_door`
   and `opening_door_hinged_or_sliding`; `opening_at_grade` only in a house drawn with a Toposolid, else expected not
   measured; out of scope, expected not measured: the area well, patio cover and projection measures,
   `sleeping_room_in_addition`, `opening_operable`, `opening_opens_to_yard`, `opening_fully_openable` and
   `opening_below_grade` (the measuring code doesn't work these out yet). Before it sends a real interior, it keeps
   each check's interior beside its saved report, as the site description is kept (written first, the earlier
   report's set aside and put back if the new report can't be moved in, and never an earlier check's interior left
   beside a new report), so egress rows can be worked out again (section 5).
4. **Stairs** (straight component runs, the cross-check), houses 2 and 3: risers, treads, widths, headroom.
   **Built** (section 4, "As built in step 4"). Scope (`recordings.py`, `STEPS[4]`): house 2's flight in scope for
   `stair_riser_height`, `stair_riser_variation`, `stair_total_rise`, `stair_risers`, `stair_tread_depth`,
   `stair_tread_variation`, `stair_headroom` and `stair_clear_width`; out of scope, expected not measured,
   `stair_clear_width_at_handrail` and `stair_handrail_sides` (railings: step 5). **House 3's tall riser** can't be
   drawn inside a component run (Revit makes a run's risers equal: `ActualRiserHeight` = height / risers), so it is
   drawn where a tall riser arises in Revit: 13 risers of 7 1/2 in, the floor at the head 1 1/2 in above the run's
   top (the 9 in riser moved from the 7th to the 13th, which changes none of house 3's hand-worked stair measures).
   The cross-check then sends no nosings, so every stair measure of house 3 must come back not measured (its stair
   read, its rooms and window as step 3): never 7.6 in, never a pass. The drawing puts each stair 10 ft clear of the
   house with its own side walls and floors (a stair's measures don't depend on where it stands), since houses 2 and
   3 draw their stairs inside bedrooms' plans, which a real model can't. Each house is recorded at the latest step
   that draws it (houses 1 and 5 stay step 3). The tick "these are all the stairs" is on Project Information (section 3).
5. **Doors** (after the PR adding doors' stated clear width to the format, decision 2), then **guards**, house 4.
6. **`has_none` ticks.**

## 8. Decisions (Ben, 2026-11-19: "go w ur recs")

1. **Shared parameters as the architect's marks** (section 3). Agreed.
2. **A stated clear width for doors in the format** (section 4, doors), the less favourable of drawn and stated
   counting when both are given. Agreed: door families can't be measured reliably; the maker's number, with its
   source, can. A format and measuring-code PR of its own, before step 5.
3. **Suggestions from room names** (a "Bedroom" shown as a suggestion, sent only once the architect accepts it). Agreed: a
   time-saver that can't cause a false pass.
4. **Order** (section 7): step 1 first, on the Mac side, while the trial's outside reading goes on. Agreed.

## 9. To check in the trial (the Revit API on real models)

`SpatialElementBoundaryLocation.Finish` on every wall type; a room's finished floor against its slab; collecting
the undersides above a room or a flight exactly; tread top faces in a `StairsRun`'s geometry; `Stairs.ActualRiserHeight`
against each run's drawn risers; finding enclosed areas with no Room; the bottom of the wall opening a window cuts (or its Bottom reference), and its placed
width and height; the floor face under a stair's first riser; a multistory stair's levels;
reading a loaded link's elements through its placement; `FromRoom`/`ToRoom` for the last phase; a railing's balusters from its geometry; probing a
Toposolid outside a window. For the marks (step 2), **answered on Snowdon Towers (Revit 2027.4, 2026-11-19)**:
Revit accepts the colon in the marks' names (all 10 added in one step); a Yes/No mark reads not set
(`Parameter.HasValue` false) on every element that had it added (57 of 57 rooms, 297 of 297 windows and doors) and
on a room placed afterwards (58 of 58), so an unmarked room never reads as No; a second Mark for egress adds
nothing. Still to check: that a type's marks read through `Element.GetTypeId()` (Operation set on a window type), and that a Room's placement reads as Revit names it (no `Location`: unplaced;
`Area` 0 with no boundary loop: not enclosed; `Area` 0 with one: redundant) and its phase from `ROOM_PHASE`. Snowdon Towers has rooms, stairs, railings and windows to try each on (as a reading
test only: it is not a house, and gives no verdict).

For rooms and escape windows (step 3), **answered on houses 1, 2 and 5 drawn by the add-in (Revit 2027.4, trial runs
1 to 6, 2026-11-20; `test_data/interior_houses/recorded/revit/`)**: the bottom of the opening a window cuts is read
from the host wall's faces whose `Element.GetGeneratingElementIds` name the window, and equals its sill line (level +
Sill Height) exactly on all six escape windows; `HostObject.FindInserts` listed no inserts even on those cut walls, so
nothing relies on it; `SpatialElementBoundaryLocation.Finish` gave each room's outline at the walls' faces and the
room separation lines; the slab top under each room agreed with its level; the enclosed areas (`PlanTopology`) are
worked out by Revit only in a document it can change, so they are read inside a transaction that is rolled back;
`FromRoom`/`ToRoom` for the last phase gave each window's room. Two lessons for drawing: Revit cuts a hosted window's wall only once the document is regenerated right after
the window is placed and its Sill Height set (`Document.Regenerate()` there; without it, in runs 2 to 5 and again on
830fbedc, every window was hosted but cut nothing; the walls are also committed first), and walls reaching past the level above enclose an area on it too (house 5's basement walls, first drawn a
foot past its ceiling). Still to try on real models: real makers' window families (their rough openings may be
larger than the unit), the Bottom reference, sloped and curved ceilings, links and worksets.

For stairs (step 4), to check on houses 2 and 3 drawn by the add-in, then on real stairs: that a `StairsRun`'s
geometry gives each tread top as its own flat face (monolithic and assembled run types; a riser board's top under its
tread); that `Stairs.BaseElevation` plus `StairsRun.BaseElevation` / `TopElevation` is the run's foot and top in
internal coordinates; that a straight run created from a path (N-1) treads long gets N risers; whether the `Stairs`
element's own geometry repeats its runs' (step 4 leaves a multi-run stair's sides and overhead out while it does);
`GetStairsPath`'s direction; a run type's nosing length (a nosing on the run but none drawn on the floor at the head
makes the last tread read deeper than typed, so no nosings are sent: to settle with real stairs); real stair types'
supports beside the treads.

## Sources

The interior format, the measuring code and the egress decisions named above (read 2026-11-19). The Revit API
members named here (`Room.GetBoundarySegments`, `SpatialElementBoundaryOptions`, `FamilyInstance.FromRoom`/`ToRoom`,
`Stairs.ActualRiserHeight`/`ActualTreadDepth`, `StairsRun.ActualRisersNumber`, `Stairs.GetAssociatedRailings`,
`Railing.HostId`/`GetHandRails`/`TopRail`) were each found in the trial laptop's Revit 2027.4 `RevitAPI.dll` (2026-11-19), and the class each
belongs to was checked in this note's first review round (the stair's typed riser and tread are on `Stairs`, not
`StairsRun`); how each behaves on real models is checked in the trial before code relies on it (section 9).
