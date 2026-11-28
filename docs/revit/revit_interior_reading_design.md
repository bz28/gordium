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
16 risers of 7.5 in, 10 in treads, 85.5 in headroom, 36 in wide; house 3's tall riser at the head held for review,
now measured as drawn, 9 in, and recorded so with houses 1 to 6 on the stair decisions, 0 problems each);
step 5 (doors, handrails and level guards) is built and tested on fake records, to record in Revit (houses 1, 2, 4,
5 and 6); step 6 is not yet.

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
  no in-place or generic family in the Stairs, Railings or Generic Models categories (unless the architect marks it
  `Gordium: Not a stair` Yes: section 3), no sketched stair, no
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
  **Changed after the first real model (Autodesk's Pacific Continental sample, 2026-11-20).** Its Read inside found 25
  enclosed areas with no Room (a 1.1 sq ft gap and 4 on L1, one of 331.4 sq ft; 19 between the roof's parapets; 1 on
  "Turret - Tall"), and under the rule above any one of them stopped every room in the house being read. That is
  safe but useless on any real model. Decided, as the most accurate rule under principle 4: an unplaced Room, a
  closed workset, an unloaded link or enclosed areas that can't be read still leave `rooms` out (what is hidden
  could be any room, drawn or not); **an enclosed area with no Room no longer does**. Every Room is read as before,
  and each such area is sent as its own entry in the format's `unknown_spaces` (added for this,
  docs/interior/interior_description_format.md), which the measuring code gives the checker as a sleeping room
  that *may not be one* (`maybe`, rule_format/parts.py): every rule row about it, or about an opening in it, needs
  review, never a pass and never a fail (it may be a closet), unless the rule doesn't apply to the house at all. So
  a drawn bedroom that fails still fails, and "every sleeping room has an escape opening" (R319.1, `when_none:
  fail`) can't pass while an area may be a bedroom with none: the space's own row needs review, and the rule's one
  answer with it. A "no basements", "no habitable attics" or "no sleeping lofts" tick isn't sent beside one (the
  checker refuses the claim too). Rejected: keeping the house-wide block (no real model is ever read); dropping
  small areas (an area under 70 sq ft that is a bedroom is a failing one, R304.1: dropping it would hide a fail);
  sending the area as `sleeping: true` (says what isn't known, and fails a closet). Two ways the architect clears
  them besides placing a Room (marked No if no one sleeps there): **an area that lies in a placed Room of the design
  checked** has that Room (its point inside within the Room's own outline, 1/16 in clear of its edges, same level:
  Revit's circuits are the main model's, so a Room in the design option checked can leave its circuit "no Room";
  a Room in an option not checked doesn't count; an area Revit can't give a point inside, a sliver between
  overlapping walls that threw "Could not obtain valid UV point" on the Children's Odyssey model, 2026-11-20, is kept,
  lies in no Room, has the id `enclosed-area:<level>:no-point:<area>sf`, and its words say to fix the walls, since it
  has no place to put a Room in); and **the level mark `Gordium: No rooms on this level`** (Yes/No
  on Levels, added by Mark for egress; a level with an area with no Room, or with the mark set, is a row in the
  marking list): on a level marked Yes its areas aren't sent, but a Room drawn on such a level disagrees with it, so
  the mark doesn't count there and the conflict is listed first (never a Room dropped in silence). To see on the
  sample next: whether the L1 areas are its design options' (the log now lists each area with its point and the
  options, and the rooms' surroundings are now read for the design checked only, section 4).
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
| `Gordium: These are all the guards and handrails` | Project Information | Yes / No / unset | `guards` and every flight's `handrails` sent only on Yes (step 5, section 2's "all the guards"). **Decided (Ben, 2026-11-20, step 5):** one tick for both, since both are railings: a guard drawn as a low wall would go unchecked, and a handrail drawn as a wall sweep would leave the width at the handrail read too wide; with the tick, a flight with no railing found sends `handrails: []` |
| `Gordium: This house has no stairs`, `This house has no doors`, `This house has no guards`, `This house has no basements`, `This house has no habitable attics`, `This house has no sleeping lofts`, `This house has no ramps`, `This house has no alternating tread devices`, `This house has no ship ladders`, `This house has no patio covers`, `This house has no deck or porch or cantilever over an escape opening` | Project Information | Yes / No / unset | step 6: `stairs: []`, `doors: []`, `guards: []`, and each `has_none` claim, sent only on Yes with nothing of the kind drawn and nothing that could hide one (section 4, "What the house has none of"). "Ship ladders": a parameter's name has no apostrophe |
| `Gordium: No rooms on this level` | Levels (instance) | Yes / No / unset | Yes: the level's enclosed areas with no Room aren't sent as `unknown_spaces` (a roof, a turret's top: section 2); a Room drawn on a level marked Yes is a conflict, listed first, and the mark doesn't count. Unset or No: each such area is sent, and every sleeping-room rule needs review (2026-11-20, the Pacific Continental sample) |
| `Gordium: Not a story` | Levels (instance) | Yes / No / unset | Yes: `all_levels[].not_a_story` true, so the Building Code's story places (which story is the first, second or fourth above grade plane) never try the level as a story nobody drew rooms on: a reference or datum level, a roof level. Rooms, or an enclosed area with no Room, on a level ticked Yes disagree with it: no story is placed. No or unset: left out, the level is tried both ways. A cell of the marking list's level row: its blank is shown with that meaning and never makes the row one to mark (a level with every mark unset and no enclosed area without a Room isn't listed; one set either way is) |
| `Gordium: Not a stair` | Generic Models, Stairs, Railings (instance) | Yes / No / unset | Yes: that element (a wall niche, a corbel, trim, a panel drawn as a Generic Model or another family in those categories) no longer stops the stairs and guards being read (section 2's "no in-place or generic family"), and each one cleared is listed in the marking list and the Read inside log ("Not a stair (architect): GenericModel "Corbel" x 6, ids in the log"), every id in the log. It never clears a Revit `Stairs`, `Railing` or multistory stair: Yes on one is a conflict, listed first, and it is read as what it is (a stair checked, never one skipped). Unset or No: not stated, it still stops the stairs being read (Ben, 2026-11-20, Q2: the Pacific Continental sample's 19 standalone Generic Models) |
| `Gordium: Site slab is` | Floors (instance) | Porch, Deck, Landing, Ramp, Patio, Terrace, Walk, Parking, Driveway / unset | The outside reader's, not the interior's: read only on a floor under none of the house's walls or roofs (a site slab, [revit_reading_design.md](revit_reading_design.md) section 1, "Site slabs"). A porch, deck, landing or ramp is sent as a building; any other word, or unset, as a left-out object whose `slab` says `patio`, `parking` or `unmarked`. Added by Mark for egress with the others and listed in the marking list (a row per site slab; a line naming any floor marked under the house, whose mark is not read) |
| `Gordium: Site object is` | Generic Models, Specialty Equipment, Site, Mass, Furniture, Casework, Structural Framing, Structural Foundations, Parking, Mechanical Equipment, Lighting Fixtures (instance) | Porch, Deck, Landing, Ramp, Garage, shed or carport, Not a structure / unset | The outside reader's: what an element on the lot that isn't the building is ([revit_reading_design.md](revit_reading_design.md) section 1, "Objects standing apart"). A porch, deck, landing or ramp, or a garage, shed or carport, is sent as a building (measured); Not a structure as a left-out object with `could_be_building: false` (no yard waits on it; the architect's statement, listed in the marking list with the element). Never the slab words (review round 1): a patio or a driveway leaves every check, so a slab's word is read on a Floor alone (`Site slab is`); on anything else it is not understood (a garage drawn as a Generic Model and marked Parking stays an object that may be a building). Unset, or another word: as before (left out; standing apart, every required yard needs review). Never read on a context object, on one of Gordium's own markers, or on a category it isn't bound to; the marking list shows those as not read here, with why. Added by Mark for egress with the others; the marking list has a row for each element it is set on (not every unset one: a project has hundreds) |
| `Gordium: Clear width`, `Clear height`, `Clear source`, `Clear confirmed` on doors | Doors (type) | As windows' | `doors[].stated_clear` (step 5): the same marks bound to Doors too, confirmed and re-checked exactly as windows' (the stamp, made for a door, records the type's `UniqueId`, size and operation, the clear width and height, the source and a mapped maker's parameter; a window's stamp never confirms a door, nor a door's a window); no `Clear offset` (a door's clear opening has no bottom in the format). The width and height are the maker's figure measured as R318.2 measures it (between the face of the door open 90 degrees and the stop; threshold top to stop bottom), never the door's size or rough opening: the marks' own tooltip says so |
| `Gordium: Leaves` | Doors (type) | a whole number: 1, or 2 for a pair with no mullion / unset | `doors[].leaves` (BCNYS 1010.1.1: where a door opening has two leaves without a mullion, one leaf gives the 32 in): 1, the door's clear width is checked against 32 in; 2, one leaf must give it, which the maker's clear opening of the pair doesn't show, so a person checks; unset or another number, not sent (Read inside's notes say which), the width needs review. A pair with a mullion is two openings, each needing the 32 in: 1 only if the type's clear width is the narrower leaf's. The checker's ask for it opens this mark |
| `Gordium: Hardware` | Doors (instance) | Panic or fire exit hardware, Panic or fire exit hardware with an electric lock, Other latch or lock, No latch or lock / unset | `doors[].hardware` (BCNYS 1010.2.8: `panic`, `panic_electric`, `latch`, `none`). Derive before asking: Revit has no built-in door hardware parameter, door families don't carry one in any standard way, and a firm's own "Hardware Set" names a set in its specification, not what the set holds, so the model can't show it: a mark on each door. Unset or another word: not sent (Read inside's notes say which), the panic hardware rule needs review for the door. The checker's ask for it opens this mark |
| `Gordium: Below grade`; `Gordium: Well area`, `Well width`, `Well projection`, `Well depth`, `Well ladder or steps`, `Well ladder width`, `Well rung projection`, `Well rung spacing`, `Well step tread`, `Well step riser`, `Well ladder full height`, `Well ladder encroachment`, `Well other encroachment` | Windows, Doors (instance) | Yes/No; an area; lengths; Ladder, Steps, Ladder blocked when open, Steps blocked when open, None / unset | `openings[].stated_well` (BCNYS 1031.5; RCNYS R319.4 for a house): whether the escape opening's clear bottom is below the adjacent grade, and its area well's size, depth, ladder or steps and what reaches into it. Derive before asking: a well isn't in Revit's vocabulary (firms draw it as a generic model, an in-place family or a maker's family, each its own way, or not at all; a floor opening or a room doesn't fit, a well being outside the building), so its size, ladder and what reaches into it can't be read for certain: marks on the window or door. Below grade and the depth are measured where a Toposolid shows the finished ground (`Gordium: Toposolid is finished ground`, the next row: the depth only as the least the well can be, its floor not drawn), and there these two marks are a statement the ground is checked against: a mark set wins, and one the ground contradicts by more than 1/16 in needs review, naming both. Every opening sends `stated_well` (empty when none is set), so each blank one reaches the check as not stated, named by its mark; an escape opening's blanks are noted in Read inside. Not in the marking list's rows (most windows have no well: a blank would flag every one) |
| `Gordium: Toposolid is finished ground` | Project Information | Yes / No / unset | `openings[].ground_outside` (GroundReader): Yes, the Toposolids (and older topography surfaces) in the design checked show the finished ground (RCNYS R202 GRADE), so the ground just outside each window is read from them (a door's only where its type's clear height is confirmed: its clear bottom is then bounded, `clear_bottom_between`) and below grade and the well's least depth are measured; blank, it is read only where the phases show it (the existing ground drawn in an earlier phase and demolished, in the design option checked and under every place read at the window, every Toposolid of the design checked created in the last phase: Ben, 2026-11-26; a project's phases alone don't, every template having two), else not read (it may be a survey's existing ground, and Rhino's picked terrain isn't taken as finished either); No, not read (where the phases point to it being the finished ground, Read inside notes that the two disagree); not read, the window's Below grade and Well marks decide, and blank ones need review. On Project Information, as `Ground from` is, so Mark for egress binds it where every mark of that kind is proven to bind. Derive before asking: where the ground is drawn and stated finished, the openings' Below grade and Well depth marks become a statement the ground is checked against |
| `Gordium: Zone`, `Use`, `Lot surveyed`, `Corner lot`, `Street edge`, `Ground from`, `Stories` | Project Information | Text, Yes/No, a whole number (Stories, optional); the street edge written by Gordium's pick | the lot facts *Check my project* sends with the interior in one check (zoning's, not egress's): [reading design note, section 9](revit_reading_design.md#9-check-my-project-the-architects-own-model-one-check) |
| `Gordium: Use` on a Room | Rooms (instance) | Corridor, Lobby, Day care, Accessory storage, Kitchen, Toilet, Closet, Workroom, Other / unset | `rooms[].use` (escape routes, section 10). The same parameter as Project Information's `Use` (one GUID bound to both categories; which use it is follows from the element): Mark for egress extends it to Rooms in a project that already has it. Unset: left out, the room is never crossed by a route. The room's name is only a suggestion in the marking list ("suggested: Corridor (named "Corridor 1")"), never sent |
| `Gordium: Can be locked`, `Gordium: Pass through` | Rooms (instance) | Yes / No / unset | `rooms[].lockable`, `rooms[].pass_through` (section 10). Unset: left out, the room is never crossed by a route |
| `Gordium: Not occupied` | Rooms (instance) | Yes / No / unset | `rooms[].not_occupied` (section 10; [route note decision 1b](../decisions/2026-11-20_route_measurement.md)): the architect's statement that nobody occupies the space (abandoned, its door permanently fixed shut, a shaft; not a room visited for storage, maintenance, testing or inspection, NFPA 101 A.3.3.21.6). Yes: NFPA 101's travel and common path aren't measured from its points (7.6.1(1) "starting from the most remote point subject to occupancy"), each such row saying which rooms it left out; the IBC's still are (1016.1); never changes which rooms a route may cross. Refused on a sleeping room or a `Day care` room (the room not read). Unset or No: occupied, measured (unset is left out of the description, No sent as false). Read inside's log counts the rooms marked |
| `Gordium: Corridor rating minutes` | Rooms (instance) | a whole number of minutes, 0 or more | `rooms[].fire_rating_hours` (sent in hours: 30 is 0.5): the corridor walls' fire-resistance rating as the assemblies are rated (BCNYS Table 1020.2), the least where they differ; unset, the corridor rating rules need review |
| `Gordium: Smoke partition walls` | Rooms (instance) | Yes / No / unset | `rooms[].walls_smoke_partitions` (NFPA 101 2012 8.4): whether the corridor's walls form smoke partitions; unset, the rules reading it need review |
| `Gordium: Function` | Rooms (instance) | one of BCNYS Table 1004.5's 41 rows, in words close to the table's (Residential, Business area, Storage, stock or shipping area...) / unset | `rooms[].function`: the Building Code's occupant loads are worked out from it (its factor, gross or net). A word not in the list is sent as typed and said in Read inside's notes, so the checker leaves the room's load, and its story's, at needs review (never dropped: a closet or toilet would read as holding no load); unset is not stated (the room's load needs review). Never guessed: where the Building Code governs, the Setup form's "Room function" line suggests one from a room's name, only where the name is the room type alone with at most a number or letter ("Bedroom 2", never "Master Bedroom Suite" or "Community Living Room"): Bedroom or Living Room: Residential, only in a building of dwelling units (a one- or two-family or multiple dwelling, never a dormitory or a fraternity, sorority or group house) whose every group the form holds is R-2 or R-3; Storage or Stock Room: Storage, stock or shipping area; Mechanical or Boiler Room, or a room whose use is Accessory storage: Accessory storage or mechanical equipment room. Each with its basis, written only when accepted; none for a corridor, a closet, a toilet or a room an exit enclosure or exit passageway door opens onto, and a room whose Use is Corridor, Closet or Toilet, or the exit enclosure itself (the room the door enters, as the route reader reads it), isn't counted on the line unless one holds a function: on a closet or toilet it counts as set; on a corridor or the exit enclosure it is listed to clear, said in the line's count (it holds no load of its own, and with one stated its story's load isn't worked out) |
| `Gordium: Unit` | Rooms (instance) | the dwelling unit's name (1A, Apt 2) / unset | `rooms[].unit`, sent as typed, trimmed: where any room of a story has one, its dwelling units (BCNYS Table 1006.3.4(1)) are counted from the names instead of grouped from the drawing, which settles a shared room marked residential (blank there: mark it a Corridor or Lobby) and a unit's room marked a corridor or lobby (one taken as an exit and marked with a unit needs review: the two disagree). A mark naming two units, a unit's rooms not joined, or a room left blank that may be a unit's leaves the count at needs review, the reason said. Unset: not stated |
| `Gordium: Follows the Building Code` | Project Information (instance) | Yes / No / unset | `building.follows_building_code`: RCNYS R101.2's exception, the architect's one choice of code (the Building Code applied to a house the Residential Code covers; its tooltip quotes the exception). Unset or No: Gordium decides the code from the building ([which NY code](../decisions/2026-11-22_which_ny_code.md)) |
| `Gordium: Stories above grade plane` | Project Information (instance) | a whole number 1 or more / unset | `building.stories_above_grade_plane` (RCNYS R202 STORY ABOVE GRADE PLANE): decides R101.2's three-story limit. Unset: Ithaca's stories count stands in where nothing is drawn below the ground; else which code governs needs review. Under 1 is asked again |
| `Gordium: Separate means of egress` | Project Information (instance) | Yes / No / unset | `building.separate_means_of_egress` (R101.2 item 2): for a building of two dwelling units |
| `Gordium: Townhouse units` | Project Information (instance) | Yes / No / unset | `building.townhouse_units` (R202 TOWNHOUSE UNIT): for three or more attached units |
| `Gordium: Care facility` | Project Information (instance) | Yes / No / unset | `building.care_facility` (BCNYS 308.2.4, 310.4.1): Yes puts which code governs at needs review |
| `Gordium: Occupancy groups` | Project Information (instance) | BCNYS Chapter 3 groups, comma separated (A-1 ... U) / unset | `building.occupancy_groups`: the code decision and the Building Code's rules (Group I-4's limits). A word not a group is asked again, nothing sent |
| `Gordium: Sprinkler system` | Project Information (instance) | None, NFPA 13, NFPA 13R, NFPA 13D / unset | `building.sprinkler_system` (903.3.1.1, 903.3.1.2, 903.3.1.3): the Building Code limits that change with a sprinkler system. Another word is asked again |
| `Gordium: Fixed assembly seating` | Project Information (instance) | Yes / No / unset | `building.assembly_fixed_seating` (BCNYS Table 1006.2.1 note c, 1030.8): Yes leaves the exits, common path and travel such a room changes to a person; No states there is none; unset, the rules that read it need review |
| `Gordium: Special egress spaces` | Project Information (instance) | Yes / No / unset | `building.special_egress_spaces` (1006.2.2, Table 1017.2 note a: a mall, an I-2 care suite, a boiler, refrigeration or electrical room, a vehicular ramp...): the same three readings |
| `Gordium: Merchandise pads` | Project Information (instance) | Yes / No / unset | `building.merchandise_pads` (1018.4: a 30 ft common path in a Group M merchandise pad): the same three readings |
| `Gordium: Egress balcony increase` | Project Information (instance) | Yes / No / unset | `building.egress_balcony_increase_taken` (1017.2.1: up to 100 ft more travel over an exterior egress balcony): the same three readings |
| `Gordium: Atrium` | Project Information (instance) | Yes / No / unset | `building.building_has_atrium` (1017.3.2.3: 200 ft of travel within an atrium): the same three readings |
| `Gordium: R-2 sleeping units` | Project Information (instance) | All sleeping units, All dwelling units, Both / unset | `building.r2_sleeping_units` (BCNYS Tables 1006.3.4(1) and (2), notes b and c): one building-wide fact, three words (a Yes/No once set can't be cleared): All sleeping units sends true (Table 1006.3.4(2)); All dwelling units false (Table 1006.3.4(1)); Both sends nothing, since neither table fits every story (Table (2) doesn't limit the dwelling units, Table (1) is looser on travel and occupants), so both one-exit rows need review; unset, those one-exit rows need review |
| `Gordium: 1031 escape openings` | Project Information (instance) | Yes / No / unset | `building.emergency_escape_openings_1031` (Tables 1006.3.4(1) and (2) note a: a sprinklered Group R-2 with emergency escape and rescue openings per Section 1031 may have one exit within the table's limits): the architect's statement (Gordium doesn't check 1031's openings under the Building Code); unset, those rows need review |
| `Gordium: Occupied outdoor areas` | Project Information (instance) | Yes / No / unset | `building.occupied_outdoor_areas` (BCNYS 1004.7: yards, patios, occupiable roofs and courts the occupants use need means of egress, their occupant load assigned by the building official): Yes, a person checks; No, not applicable; unset, needs review |
| `Gordium: Occupant load increased` | Project Information (instance) | Yes / No / unset | `building.occupant_load_increased` (BCNYS 1004.5.1: an occupant load above Table 1004.5's, at most one per 7 sq ft): No, each room's load is the table's alone; Yes or unset, each room's larger reading is at least its area / 7, so no rule passes on a load an increase could exceed |
| `Gordium: Other levels reach corridors` | Project Information (instance) | Yes / No / unset | `building.other_level_egress_into_corridors` (BCNYS 1004.2.2, 1004.2.3, 1005.6): No, each corridor's occupant load lies between none and its whole story's (two readings); Yes or unset, worked out by hand; the panel's card for it opens this mark |
| `Gordium: Ambulatory care facility` | Project Information (instance) | Yes / No / unset | `building.ambulatory_care_facility` (Table 1020.3: 72 in for corridors serving stretcher traffic; Section 422: its separation and smoke compartments): Yes or unset, Section 422's flags, a Group B corridor under 72 in and an unrated Group B corridor (Table 1020.2) are a person's check; No, not |
| `Gordium: Corridors within dwelling units` | Project Information (instance) | Yes / No / unset | `building.corridors_within_dwelling_units` (1020.2 exception 2; Table 1020.3's 36 in): Yes or unset, a corridor short of the rating or width is a person's check; No, the table applies to every corridor, and a door onto a corridor gets none of 1010.1.1's exceptions for doors inside a dwelling unit |
| `Gordium: Emergency voice/alarm system` | Project Information (instance) | Yes / No / unset | `building.emergency_voice_alarm_system` (907.5.2.2; 1005.3.1 and 1005.3.2 exception 1, "in buildings equipped throughout"): Yes only for a system throughout the building (part of it: No); with NFPA 13, or 13R in Group R, the lower capacity factors (0.15 in, 0.2 in for stairways); No, the full ones; unset, a capacity met only at the lower factor needs review |
| `Gordium: Mezzanines` | Project Information (instance) | Yes / No / unset | `building.mezzanines` (BCNYS 505.2; 1004.2.2 adds a mezzanine's occupants to a room on an adjacent level): No (with the ceiling's other facts) lets a story's floor area at one occupant per 5 sq ft bound its occupant load where no room function is set; Yes or unset, no such bound |
| `Gordium: Loads not by area` | Project Information (instance) | Yes / No / unset | `building.loads_not_by_area` (BCNYS Table 1004.5's rows with no factor: fixed seats in any use, 1004.6; bowling lanes; concentrated business use, 1004.8; a mall, 402.8.2): No is one of the facts that let a story's floor area bound its occupant load; Yes or unset, no such bound |
| `Gordium: High-rise building` | Project Information (instance) | Yes / No / unset | `building.high_rise_building` (BCNYS 202 HIGH-RISE BUILDING, or more than 420 ft in building height: 403.1, 403.2.2, 403.5.2): Yes or unset, Section 403's flags show and, outside Group R-2, a story with no more exits than 1006.3 asks needs review; No sets them aside. Never worked out from the model (where fire trucks reach the building isn't in it); the question's card may give the model's height of its highest level (or a room's floor above it) over the lowest finished ground as a hint, with what would still make it a high-rise (`design_checker/high_rise_hint.py`, under 75 ft only) |
| `Gordium: Underground building` | Project Information (instance) | Yes / No / unset | `building.underground_building` (BCNYS 405.1: a floor level used for human occupancy more than 30 ft below the finished floor of the lowest level of exit discharge): Yes or unset, Section 405's flags show and a story with one exit needs review (405.7.1); No sets them aside |
| `Gordium: Stages or platforms` | Project Information (instance) | Yes / No / unset | `building.stages_or_platforms` (BCNYS 202 STAGE, PLATFORM, TECHNICAL PRODUCTION AREA; 410.5): Yes or unset, Section 410.5's flags show and, in Groups R-2, R-3 and R-4, a room's one exit with a common path over 100 ft needs review (410.5.3.3); No sets them aside |
| `Gordium: Aircraft-related occupancy` | Project Information (instance) | Yes / No / unset | `building.aircraft_related_occupancy` (Section 412: an airport traffic control tower, an aircraft hangar, a paint hangar, aircraft manufacturing, a heliport or helistop, whatever the group): Yes or unset, Section 412's flags and 905.3.5's show and, in Group U, a room's one exit needs review (412.4.2); No sets them aside |
| `Gordium: Service corridors` | Project Information (instance) | Yes / No / unset | `building.service_corridors` (BCNYS 202 SERVICE CORRIDOR: a passage for transporting HPM, 415.11.3): Yes or unset, in Group H-5 or two or more groups 415.11.3.3's and 415.11.3.4's flags show and a corridor's capacity needs review, in Group H-5 its travel, one-exit stories, dead ends and width too; No sets them aside |
| `Gordium: Assembly spaces` | Project Information (instance) | Yes / No / unset | `building.assembly_spaces` (1030.1: a room or space used for assembly purposes, whatever the group, 303.1.1 and 303.1.2): Yes, Section 1030's checks apply in any group; No, with `Gordium: Fixed assembly seating` No too, sets them aside in a building of one group other than A; unset, they need review there. A room whose `Gordium: Function` is a Table 1004.5 Assembly row makes it Yes whatever the mark; one that may be assembly (a courtroom, a pool, a stage) leaves a No unread (`code_scope.assembly_spaces_from_rooms`) |
| `Gordium: Dwelling units` | Project Information (instance) | a whole number 1 or more / unset | `facts.dwelling_units`: this lot's units, an ADU included; checked against the use for which code governs (R202 DWELLING) and read by Ithaca's zoning |
| `Gordium: Units in the attached building` | Project Information (instance) | a whole number 1 or more / unset | `facts.attached_units_in_building`: a townhouse needs three or more (R202 TOWNHOUSE) |
| `Gordium: Home occupation` | Project Information (instance) | Yes / No / unset | `facts.home_occupation`: Yes puts which code governs at a person's check (live/work, BCNYS 508.5); unset is assumed none, said as a reading |
| `Gordium: Rooms let for profit` | Project Information (instance) | a whole number 0 or more / unset | `facts.rooms_let_for_profit`: any puts which code governs at a person's check (R101.2 item 6); unset is assumed none, said as a reading |
| `Gordium: Accessory dwelling unit` | Project Information (instance) | Yes / No / unset | `facts.accessory_dwelling_unit`: Yes asks whether it is detached; unset is assumed none, said as a reading |
| `Gordium: ADU detached` | Project Information (instance) | Yes / No / unset | `facts.adu_detached`: No makes the ADU one more of the building's units (R202 DWELLING) |
| `Gordium: ADUs on parcel` | Project Information (instance) | a whole number 1 or more / unset | `facts.adus_on_parcel`: more than one keeps which code governs at needs review; unset beside a stated ADU is assumed one, said as a reading |
| `Gordium: Stream within 20 ft` | Project Information (instance) | Yes / No / unset | `facts.stream_near_lot` (§325-26: "No new structure shall be located nearer than 20 feet to an inlet wall or to the bank of an inlet channel or stream"); unset: the rule needs review |
| `Gordium: Distance from stream` | Project Information (instance) | a length 0 ft or more / unset | `facts.stream_distance`, as typed (never rounded); under 0 is said and not sent |
| `Gordium: Unrelated people per unit` | Project Information (instance) | a whole number 0 or more / unset | `facts.unrelated_persons` (§325-3B DWELLING, ONE-FAMILY); unset: the occupancy rule needs review |
| `Gordium: Owner-occupied` | Project Information (instance) | Yes / No / unset | `facts.owner_occupied` (§325-3B: "permitted if the dwelling is owner-occupied") |
| `Gordium: Functional family unit` | Project Information (instance) | Yes / No / unset | `facts.functional_family_unit` (§325-3B FUNCTIONAL FAMILY UNIT; the City's finding, so Yes asks a person) |
| `Gordium: Garage cars` | Project Information (instance) | a whole number 0 or more / unset | `facts.garage_cars` (zoning chart, Private garage, note 6: "For not more than three cars.") |
| `Gordium: Private garages` | Project Information (instance) | a whole number 1 or more / unset | `facts.private_garages`, read only once the cars are over three |
| `Gordium: Abuts R-1 land` | Project Information (instance) | Yes / No / unset | `facts.abuts_r1_district` (§325-19E: a use other than a one- or two-family dwelling in R-3a or R-3b on land that directly abuts R-1a or R-1b land); Gordium reads it the cautious way, across a street included, a reading to confirm; unset: the rules that turn on it need review |
| `Gordium: Conversion` | Project Information (instance) | Yes / No / unset | `facts.conversion` (§325-3B CONVERSION); unset: the rules that turn on it need review |
| `Gordium: Primary buildings` | Project Information (instance) | a whole number 1 or more / unset | `facts.primary_buildings` (§325-3B PRIMARY STRUCTURE, §325-8B(1)); stated, it stands; unset, read from the drawing (two readings where a building standing apart could hold a home); under 1 is said and not sent |
| `Gordium: Primary buildings same use` | Project Information (instance) | Yes / No / unset | `facts.primary_buildings_same_use` (§325-8B(1): each further primary use in a separate building needs its own lot area) |
| `Gordium: Home occupation area`, `Gordium: Home occupation unit area` | Project Information (instance) | an area 0 or more / unset | `facts.home_occupation_area`, `facts.home_occupation_unit_area` (§325-3B HOME OCCUPATION (1)(f): 500 indoor sq ft and 25% of the unit at most). An area is its own kind of mark (Revit's Area), typed and shown in the project's area units (Manage > Project Units), held and sent in square feet, never rounded; under 0 is said and not sent |
| `Gordium: ADU in existing building` | Project Information (instance) | Yes / No / unset | `facts.adu_existing_building` (§325-28C(7)(b) and (c): a detached ADU in an existing accessory building, or new construction) |
| `Gordium: ADU bedrooms` | Project Information (instance) | a whole number 0 or more / unset | `facts.adu_bedrooms` (§325-28C(3): two at most) |
| `Gordium: ADU floor area`, `Gordium: Main building floor area` | Project Information (instance) | an area 0 or more / unset | `facts.adu_floor_area`, `facts.primary_floor_area` (§325-28C(7)(a): an attached ADU at most 40% of the primary structure's floor area; whether of the whole structure or the rest is an open question) |
| `Gordium: Exit` | Doors (instance) | Exterior door at discharge, Exit stair enclosure, Exit passageway, Horizontal exit, Exterior exit stair or ramp / unset | `doors[].exit_kind`, and from it `exit_id` (section 10). Unset: not an exit (exits are marked, never guessed) |

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
primary ([revit_reading_design.md](revit_reading_design.md), section 1). That holds for what is around a part too:
Revit's collectors give every design option's elements, so a secondary option's wall, floor or roof found in, under
or over a room is set aside (as the stairs' and guards' surroundings already were; before 2026-11-20 a room's were
not, which could only refuse a value, never pass one). Revit's own room outlines and plan circuits are the main
model's (main model and primary options); while a secondary option is being edited, the rooms' outlines are still
those (to confirm on a real model with options). Rooms, windows, doors, stairs or railings
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
| `ground_outside` | The ground at the opening's outside face, only from a ground the architect gave: the Toposolids (and older topography surfaces) in the design checked, where Project Information's `Gordium: Toposolid is finished ground` is Yes, or, blank, the phases show them finished (the existing ground drawn in an earlier phase and demolished, every one created in the last); a Toposolid may otherwise be a survey's existing ground. `GroundReader` reads, for each window, the highest ground 1 in beyond the wall's outer face (RCNYS R202 GRADE: "The finished ground level adjoining the building at all exterior walls") at each end of the opening (the wall opening it cuts) and its middle, and the highest and lowest along its whole width where they are neither (exact: the ground is planar on each triangle, so along the line they are at its ends or where it crosses a triangle's edge, each stretch between read at its middle and its plane taken at both ends, so a hole or a cut in the Toposolid there is seen). A door's is sent only with its clear bottom's bounds (`clear_bottom_between`, `InteriorReader.DoorBottom`: its threshold isn't drawn, but its clear opening lies within the door as placed and the opening it cuts, so its bottom is at least the higher of their bottoms and at most the door's top less its stamp-confirmed clear height); without a confirmed clear height, none, since its ground alone could only unsettle its Below grade mark. Sent only where the outside is known (its one room on one side only, no room or enclosed space on the other) and, out to 6 ft at each place along it, one finished ground is drawn (a subdivision on its own host counts as its top), nothing else stands over it below the opening's top (any element whose box reaches anywhere over the outside, from the line 1 in out to 6 ft over the opening's width, above the lowest ground there: an area well drawn as a family, a step, a slab, a deck; never a Room's, an area's or a line's box; a linked model reaching over it, or with no box, or any coordination model, whose contents aren't read, leaves it unread too), and the ground doesn't rise more than 1/16 in above the ground at the face (a well cut into the ground, or ground sloping toward the wall, leaves which ground adjoins the opening unclear). An escape opening says why not in Read inside's notes; no ground drawn changes nothing. Never the lot facts' flat ground, nor a level's elevation: flat ground is often Gordium's own assumption (`ground_assumed: "flat"`), and an assumed ground could make a window a grade-floor opening, which needs only 5 sq ft (R319.2.1 exception). The Revit layer gives each ground's triangles and, only where a ground is drawn, each opening's surroundings (`OpeningRecord.Around`: boxes, no faces) | To try in Revit: a real Toposolid's faces triangulated (`Face.Triangulate()`), a subdivision's `HostTopoId`, an older `TopographySurface`'s mesh; finished spot grades at an opening |
| `area_well` | Not in Revit's vocabulary: not given. An opening whose clear bottom is below the ground outside it (`ground_outside`) gets no grade-floor answer (it stands in a well whose floor isn't drawn: questions_for_architects.md 4.6), and the well's facts come from its marks (`stated_well`) | How firms draw wells (a generic model, an in-place family) |
| `stated_well` | The window's or door's own marks (`Gordium: Below grade` and the `Gordium: Well` marks, section 3), each set one as typed (a length in feet, an area in square feet), a ladder word through its table; always sent, empty when none is set. Where `ground_outside` is sent (a window, or a door with `clear_bottom_between`), the measuring works out below grade and the well's least depth from it for what isn't marked, and a mark the ground contradicts by more than 1/16 in needs review (interior_measurements.md) | A door's threshold, drawn (its clear bottom is bounded, not read) |

### Stairs (`stairs`): one entry per flight

| Field | From Revit | To check |
|---|---|---|
| a flight | Each `StairsRun` of a component `Stairs`, every one sent (the list only as section 2's "all the stairs" allows). A winder or spiral run (the format measures only straight flights) is sent with no `nosings` and no `spiral`, so its measures have no value and its rules need review | A sketched (non-component) stair: the whole `stairs` list left out (not read) |
| `spiral` | Whether the flight is a spiral stairway (R202: "a plan view of closed circular form and uniform section-shaped treads, attached to and radiating from a minimum-diameter supporting column"). `false` only for a run whose `StairsRun.StairsRunStyle` is `Straight` (the Revit 2027 API's members: Straight, Winder, Spiral, Sketched) and whose nosings are sent (its drawn treads read straight and rectangular, square to the run); the measuring code takes it only for a flight it measures straight. **Never `true`** (review round 1, 2026-11-20): Revit's `Spiral` style is every arc run, any sweep and radius, a curved stair too, and `stair_spiral` true sets every R318.7 rule with `applies_when: not stair_spiral` aside (width, headroom, risers, treads, the open-riser sphere): a false-pass path. Every other run, or a straight run whose nosings are left out: not sent, with its reason (the spiral rules and those turning on it need review) | Telling R202's spiral (a column, closed circular form) from the run's geometry, before `true` is ever sent |
| `bottom_elevation` | The top face of the floor or landing drawn in front of the first riser, in the same shared coordinates as the nosings, **as drawn** (Ben, 2026-11-20, Q1: R318.7.5.1 measures a riser "vertically between leading edges of the adjacent treads", so a floor standing off the run's own base makes the first riser taller or shorter, and that is what is checked). No floor or landing face found whole there, or one at or above the first tread: not sent (the flight's measures need review). The top nosing is the edge of the floor or landing at the head, as drawn, the same way: none found whole there, one at or under the top tread, one over the last tread short of the riser line, or **any of the run's own geometry above it** (a riser board standing proud of a lower floor, a lip that would be the real top nosing): no `nosings` | Finding the floor face under the first riser |
| `nosings` | From the run's drawn geometry: the front edge of each tread's top face, bottom to top, then the landing or floor edge at the top | That tread top faces are separate planar faces in the run's solid; nosing profiles (a rounded nosing) |
| cross-check | The stair's typed `Stairs.ActualRiserHeight` and `Stairs.ActualTreadDepth`, and the run's `StairsRun.ActualRisersNumber`, against the run's own drawn risers (its base to its top through its treads: equal by construction) and treads: more than 1/16 in apart, the flight is sent without `nosings` (its rules need review). The risers sent are the drawn ones, the first and last to the floors (above) | |
| `sides` | The reader searches the whole band on each side of the flight, from well inside the tread ends to past them, from the treads up to the headroom height, for anything at all. A wall face found there is the side line; else a railing's inside face above handrail height. `open` only when that search finds nothing (a wall or railing missed would make the stair look wider than it is: R318.7.1). Anything found that it can't read exactly (a generic model, a curved face): `sides` left out, the width needs review | Searching that band exactly |
| `handrails` | The stair's railings (`Stairs.GetAssociatedRailings()`): their handrails (`Railing.GetHandRails`), inner edge in plan, with their side. A top rail (`TopRail`) counts as a handrail only where the railing's type is marked `Gordium: Top rail is handrail` (a guard's top rail is usually 36 in or more up, above the handrail's 34 to 38 in) | |
| `overhead` | The downward planar faces of everything above the flight (floors, ceilings, roofs, beams), clipped to the flight's plan. Nothing found, or a curved face: `overhead` left out (the format refuses an empty list), so the headroom has no value and needs review; the flight is still sent | Collecting it exactly, as for ceilings |

**As built in step 4** (`Gordium.Revit.Reading/StairReader.cs`; the Revit layer `RevitInterior.StairsOf`), where the
table above needed settling:

- *A window's grille is not a stair* (2026-11-20, the Pacific Continental sample: 272 "Muntin Pattern_1x2" Generic
  Models nested in its windows, each a loadable family that stopped the stairs being read). A Generic Model family
  instance nested, at any depth (`FamilyInstance.SuperComponent` to the top, recorded per candidate), in a window
  or door, whose box lies within that window's or door's box (1/16 in to spare), is part of it and doesn't count:
  nothing that fits inside a window's box can be a flight of stairs or a guard along a floor's edge. Anything else
  still does: not nested, nested in anything but a window or door, sticking out of its box, or a box Revit doesn't
  give. A guard built into a door family (a Juliet rail) inside the door's box would be set aside too: that is the
  architect's "all the guards" tick to answer (a guard not drawn as a railing), as for any guard drawn otherwise.

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
- *Generic Models*: under section 2's rule any Generic Model anywhere in a project stops stairs being read, unless it
  is nested inside a window or door, or the architect marks it `Gordium: Not a stair` (section 3); each one cleared
  is listed with its id.
- *Foot and head*: the floor or landing top is looked for in a 1 in strip in front of the first nosing and past the
  last riser, across the stair's width: one flat top within a foot covering the whole strip, else not found.
- *The cross-check*: the run's own risers (its base to its top through its treads: equal by construction) against
  `Stairs.ActualRiserHeight`, every tread (nosing to nosing, the last to the head's edge) against `ActualTreadDepth`,
  the counts against `StairsRun.ActualRisersNumber` / `ActualTreadsNumber`; a run that doesn't begin and end with a
  riser isn't read yet. Any of these failing, or the foot not confirmed (the first riser can't be measured), sends no
  `nosings`. The first and last risers sent are as drawn, to the floor in front and the floor at the head (a house
  whose levels don't divide evenly sends its taller or shorter end riser, and R318.7.5.1 judges it). A winder, spiral or sketched run sends neither `nosings` nor `bottom_elevation` (only straight flights
  are measured; its foot is read with the first straight tread, which a turning run hasn't).
- *Sides*: the band on each side, from the flight's middle to 6 in past the tread ends, from 1 in under the line of
  nosings to 80 in over it (from the first nosing to the top one). The innermost wall face there facing the flight is
  the side line, if it covers the whole band; nothing there is `open`; anything else (furniture and fixtures too, a
  column, a pipe in front of the wall, a railing, the stair's own support over its treads or rising 34 in over them)
  leaves `sides` out (review round 1: a cabinet or a light is in a stair's way, unlike a room's ceiling, so stairs
  never set furniture and fixtures aside, beside or overhead). Extents are read from flat faces' corners (exact), else from Revit's box (only ever bigger).
- *Handrails and guards*: railings are read in step 5 with the guards (the same reading of a Railing's geometry), so
  step 4 sends no `handrails` (the width at the handrail and the handrail sides need review) and a railing beside or
  over a flight leaves its `sides` or `overhead` out. **As built in step 5** (`StairReader.cs`): a railing on the
  stair (it lists it, or hosts it) standing in a side's band where a wall face is found, every part read exactly
  (flat faces, straight edges: a polyhedron's extremes are its corners), every point between the wall face and the
  flight's middle and none more than 38 in (the highest a handrail may be) over the line of nosings, and nothing of
  it that isn't sent as a handrail (a top rail marked No or unset, a post, a baluster) farther toward the middle than
  the innermost handrail edge sent (review round 1: a top rail marked No read the width at the handrail 36 in, drawn
  32.5; with no handrail sent, it is refused), is that side's
  handrail: it never narrows the width above the handrail nor the headroom, so the wall stays the side and the
  railing is set aside overhead. Its `handrails` entries are its handrails (`GetHandRails`) and its top rail where
  the type says `Gordium: Top rail is handrail` Yes (unset with a top rail: `handrails` left out), each the plan line
  of its edge nearest the middle from its first point along the run to its last. `handrails` is sent only on the
  tick "these are all the guards and handrails" and with both sides read; with none found, `[]`. Anything else
  beside the flight (a railing on an open side, which is a guard along a stair; a railing not the stair's; a round
  handrail, whose curved faces aren't read exactly; one rising past 38 in or reaching past the middle) leaves `sides`
  and `handrails` out, and, being a railing on a stair not read as a handrail, the `guards` too. A stair railing at
  or under 38 in over the nosings is never the headroom. Two exactness fixes came with it: a sloped face at the head
  (a handrail rising past it) is judged by its plane over the last tread, not its whole height range; a vertical face
  in a side's band (a sloped roof's side) is judged up the run against the band, not by its height range alone (house
  4's roof, 98.5 in over the top nosing, was read in the band).
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
(engineers, its own PR, with a hand-worked house), before the Revit reader sends doors. **Built (2026-11-20):** doors'
`stated_clear` `{width, height, source}` in the format, each size the smaller of drawn and stated, a door drawn but
not measurable or a malformed stated size giving no value, and `from` saying which counted
([interior_measurements.md](../interior/interior_measurements.md#the-exit-door-egress_door); house 6 in
`test_data/interior_houses/`); how the reader fills it (a confirmed type parameter, as windows' `Clear …` marks) is
step 5's. Until the reader does, it sends
each door's `exit` mark and `operation` only: the width and height have no value (needs review), which is safe.

**As built in step 5** (`InteriorReader.cs`, `ReadDoor`): every door in the design checked is a `doors` entry with
its `Gordium: Exit door` mark (unset: not given, so no door is read), its type's `Gordium: Operation` through the
door's word (a window's word on a door is not stated), and `stated_clear` `{width, height, source}` only when the
type's `Clear confirmed` stamp, made for a door, confirms every value now (section 3) and the clear opening fits
inside the door as placed (its geometry's width along the wall, its height), 1/16 in to spare. Nothing drawn is
sent (`stops`, `hinge_pin`, `leaf_closed`, `threshold_top`, `head_stop_bottom`): door families don't model them
consistently, and a family's leaf read as the door's could make it read wider. So the measured size is the maker's
alone, `from` saying "stated". A door is an opening too (`openings`, its escape mark), sent there with no
`stated_clear` (its clear bottom isn't stated by a door's marks). No door found: `doors` left out (never `[]`); a
link holding windows or doors leaves it out, as it does `openings`.

### Guards (`guards`)

Railings not on a stair (a `Railing` that no stair lists among its `GetAssociatedRailings()`; its `HostId` the floor whose edge it guards): `walking_surface` from the host
floor's top, `top` from the railing's top rail, `members` from the railing's rails, balusters and posts in its
elevation. A guard drawn as something other than a Railing (a low wall, a generic family) is not found, which is
why `guards` is sent, empty or not, only on the architect's tick (section 2). **To check:** reading balusters from a railing's geometry exactly (their spacing decides the 4 in
sphere rule). Guards along a stair: the stair's railing, `top_line` along its top rail.

**As built in step 5** (`GuardReader.cs`): `guards` is sent only on the tick "these are all the guards and handrails",
with none of the stairs' blockers (section 4, stairs), and with every railing on a stair read as a handrail beside a
wall: **a guard along a stair isn't read yet** (its `top_line` and the stair's side as the guard's inside face are
to build), so any other railing on a stair leaves `guards` out, as does a railing on no stair standing beside a
flight (it can't be told from a guard along it), or any railing while stairs are drawn but not read (where it stands
isn't known). "Beside a flight" is judged by where things are drawn, never by how far a flight's reading got
(review round 2: a winder, an unread run, a side refused first): a railing on no stair whose box comes within 1 ft
in plan of a run's own drawn extent, its height between 1 ft under the run's base and 4 ft over its top, is held back; a run
whose extent can't be read holds back every railing on no stair. Each other railing on no stair is a level guard, never
dropped, each value sent only when read exactly:

- its path must be one straight line (else every value out);
- `members`: every solid of the railing, its top rail and its handrails must be a box square to the guard (six flat
  faces, each facing along it, across it or up or down), each its rectangle in the guard's elevation; one that isn't
  (a round or turned baluster, a sloped rail, an L-shaped post) leaves `members` out, since a rectangle around it is
  bigger than it and the openings would read smaller; `top` the highest member's top;
- `walking_surface`: the one flat top within a foot of the railing's base covering a 1 in strip along its whole path
  on one side or the other, every top there at one height, agreeing with the base (level + base offset) within 1/16 in;
- `extent`: at each end a wall or column face square to the guard within 1/16 in of the path's end, covering it from
  the walking surface to the top across the members' depth, its place along the guard the extent (the format reads
  past each end as solid, so a guard ending in the air sends none); a member's end within a millionth of a foot of
  it is put on it (Revit's number noise, never a drawn gap);
- a loaded link reaching it leaves every value out.

- the openings are read in one plane only when every infill member (each under the guard's top) has its face toward
  the walking side in one plane within 1/16 in (with the floor on both sides, both faces): members at different
  depths projected together could block a sphere that weaves between them (two staggered rows, each with 4.5 in
  gaps, offset by half, overlap to 1.5 in in elevation), so otherwise `members` is left out, the note naming the
  members' depths (Ben, 2026-11-20).

No level guard found: `guards` left out (never `[]`).

### What the house has none of (`has_none`)

As the format says: the reader **proposes** (no Ramp elements; no stair of a ship's-ladder type), the architect
ticks, and only then is the claim sent, its `source` naming both ("no Ramp elements in the
model; ticked by the architect"). The add-in already reads the checker's `not_applicable` status (PR #115), which
these claims produce. Sleeping lofts are the architect's tick alone: the reader has no loft mark to propose from.

**As built in step 6** (`HasNone.cs`). One Yes/No tick on Project Information per kind (section 3): the three lists
the format has itself (`This house has no stairs`, `... no doors`, `... no guards`: sent as `stairs: []`, `doors: []`,
`guards: []`) and each of the format's `has_none` kinds (`... no basements`, `no habitable attics`, `no sleeping lofts`,
`no ramps`, `no alternating tread devices`, `no ship ladders`, `no patio covers`, `no deck or porch or cantilever over an
escape opening`: sent as a claim whose `source` names the tick and what the reader found, "ticked by the architect
(Gordium: This house has no ramps: Yes, on Project Information); no Ramp elements in the model"). Rooms and openings
get no tick (`rooms: []` is a house not drawn; a missed escape opening or door can only fail). A tick is sent only when:

- it says **Yes** (No or unset: not stated; with no tick, nothing found is still never "none");
- **nothing drawn contradicts it** (a conflict, listed first of all in the marking list, and that kind not read: the
  two disagree): a stair for "no stairs" (or `These are all the stairs` No, which says a stair isn't drawn as one); a
  door for "no doors"; a railing on no stair for "no guards" (or `These are all the guards and handrails` No); an
  element in Ramps for "no ramps". The other kinds have nothing the reader can find (a basement, a patio cover): the
  checker's own refusals still apply (a room within another's height refuses "no sleeping lofts");
- **nothing could hide one**, each kind's list's own blockers: for stairs, ramps, ship ladders and alternating tread
  devices the stairs' (a generic or in-place family, a sketched or multistory stair, a closed workset, an unloaded or
  nested link, a link holding stairs, railings or generic models, a coordination model), with a link holding ramps
  and Ramps not read for ramps; for guards the guards' (every railing on a stair read as a handrail beside a wall,
  which needs the stairs read); for doors a link holding windows or doors; for basements, habitable attics and sleeping
  lofts the rooms' (every room read, so the checker can hold the claim against them); for every kind a closed workset,
  an unloaded or nested link and a coordination model.

**A later check (review round 1):** a "no basements" tick on a house that draws a level of rooms below the
ground is caught only where the ground outside is read (`ground_outside`, from a Toposolid stated to be the finished
ground): the checker's own below-ground refusal (`has_none.below_ground`) then holds the tick back when a room's floor
is below it. With no ground read it still compares nothing.

The marking list (built by Mark for egress from the model with its inside read, `RevitInterior.Model`, so its ticks
are the reader's own) shows a line per tick: sent; not sent and why; or not set, with what the reader found as a proposal
("Gordium found no Ramp elements in the model: tick Yes if the house has none"), never sent without the tick. Every
tick's reading is kept in the evidence (`evidence.has_none`).

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
type's section the add-in shows.

**Makers' formulas, filled as a draft** (2026-11-20). Most real families carry only frame or rough sizes, so the
add-in also keeps a short, hand-curated file of makers' own clear-opening formulas
(`apps/revit_addin/data/maker_clear_openings.json`, embedded in `Gordium.Revit.Reading`; `MakerClearOpenings.cs`).
Each entry names the maker and product line, the Revit type values it matches (for Marvin, read from Marvin's own
Revit family, 2026-11-20: the type's Manufacturer "Marvin Windows and Doors", and either its shared Window Type
parameter "Ultimate Casement", read by GUID, those two ignoring case, or a Model that is a call number written exactly
as Marvin writes it, such as "UCA3648", case and all; only a call-number Model is ever filled), the formula from the frame size, where it holds, the PDF (URL, fingerprint, page, exact
quote, date opened) and the hardware caveats, and is pinned by a test that reproduces rows of the maker's own table.
First entry: **Marvin Ultimate Casement** (full frame), from Marvin's Architectural Detail Manual: "Clear Opening
Width = Frame OSM Width - 7 1/8"" for frames 20 in and wider, "Clear Opening Height = Frame OSM Height - 5 1/8""
(page UCA UCANF-25). From CN 2864's frame (28 by 63 1/8 in, page UCA UCANF-29) it gives 20 7/8 by 58 in; Marvin's
table (page UCA UCANF-6) prints "2864 1-8 57/64 (531) 4-10 1/64 (1473) 8.42": 1/64 in more on each, so the formula
is the smaller and the tests hold it within 1/64 in of every row checked and never above. Andersen's A-Series hung
size guide prints formulas but no clear-opening row to reproduce, so it isn't an entry (only its PDF is named). How
it works, in **Mark for egress** and **Check my project**:

- **Only the frame is read.** A family's Width may be the frame or the rough opening. Marvin's standard frame,
  rough and masonry sizes never coincide (a test checks it), so a type's Width and Height that are both a standard
  frame size can only be the frame; a rough or masonry opening, or a custom size, is not filled, and the list says why.
  Marvin's frames are filled only 20 to 36 in wide and up to 71 1/8 in high (larger frames may get custodial sash
  limiters). Marvin's family carries the frame as Width and Height (UCA3648: 3'-0" by 3'-11 1/8", with Rough_Width
  3'-1" beside it).
- **Cross-checks from the family.** Every fill needs a Model that is a call number, and it must be the frame's
  (UCA3648 is 36 by 47 1/8 in), else nothing is filled: Marvin's mulled families (4W_1H, MultiW_1H, 1W_2H...) carry
  the same Window Type and one unit's Model, and a mulled unit can be a standard frame size overall (two 18 in units,
  36 in), so a Window Type with no call-number Model is never filled (review round 1). The type's `Gordium:
  Operation`, when set, must be the formula's (Casement), else nothing is filled; unset, the line asks for it. And when the type has Marvin's
  shared Vent Area (by GUID), the formula's area must agree within 0.02 sq ft, else nothing is filled and the list
  says why (UCA3648: 28 7/8 by 42 in = 8.42 sq ft by the formula, Vent Area 8.43). The family's "Egress Window"
  Yes/No is never read.
- **A draft, never a confirmation.** Only a window type whose `Clear width`, `Clear height` and `Clear source` are
  all empty is filled (never over a value typed by hand, never half of one; never a type with a `Clear
  confirmed` stamp), and `Clear confirmed` is never written: the reader sends no clear opening until the type's own
  stamp is made (section 3), so a draft alone always leaves the window's clear measures not measured (needs
  review). `Clear offset` stays the architect's. The `Clear source` holds facts only (it is sent as the clear
  opening's source once confirmed): the maker, page, formula, frame size and call number, starting "Gordium filled
  from", so a later read knows the values are Gordium's (and says so if the type was resized or its operation changed
  since). "Draft" is said in the marking list, never in the source.
- **The marking list says it**: "Gordium will fill ..." for a type still empty, and "Gordium filled the clear opening
  from Marvin UCA UCANF-25 ...: confirm it (check the hinge/hardware: ...)" once its marks hold the values. **A write
  that fails** (a type Revit won't set, or a transaction Revit rolls back: its status, not an exception) counts as
  nothing filled (`ClearPrefills.Outcome`), and the reason is shown, not only logged (`clear_fill_failed`): Mark for
  egress's dialog opens with it, and Check my project's results panel shows it in its status line (beside the marks
  added) and first in check_project_result.txt: "Gordium couldn't write the makers' clear openings (<reason>): fill them by hand from the maker's
  tables; until then their clear opening needs review", and each type left empty says the same in the marking list,
  never "will fill"; the list and the check go on. A maker's "E" mark in its table is never read, and never turns
  into a pass.
- **No match**: nothing changes (each type is asked, as before); when its Manufacturer is a maker Gordium knows
  (Marvin, Andersen, Pella) the list names that maker's clear-opening PDF, saying whether the type's marks are empty
  or hold values typed on it. A type whose `Clear source` is Gordium's ("Gordium filled from") but that no longer
  matches an entry (whatever its Manufacturer) says "its clear opening was filled by Gordium from <maker> earlier, but
  the type no longer matches: re-check it", never that its values were typed.
- **Not yet shown in Revit end to end** (2026-11-20): Marvin's UCA3648 family wouldn't place in Autodesk's Pacific
  Continental sample (every wall: "There exist geometry collision"), so the fill has been checked on records made from
  the family's own PartAtom and type catalog only (section 9 lists what is still to check).

Every room, window and door needs its Yes or No (a schedule fills the No's in
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
   `stair_tread_variation`, `stair_headroom`, `stair_clear_width` and `stair_spiral` (false: a Straight run whose
   treads read straight; house 3's flight the same); out of scope, expected not measured,
   `stair_clear_width_at_handrail` and `stair_handrail_sides` (railings: step 5). **House 3's tall riser** can't be
   drawn inside a component run (Revit makes a run's risers equal: `ActualRiserHeight` = height / risers), so it is
   drawn where a tall riser arises in Revit: 13 risers of 7 1/2 in, the floor at the head 1 1/2 in above the run's
   top (the 9 in riser moved from the 7th to the 13th, which changes none of house 3's hand-worked stair measures).
   **Changed (Ben, 2026-11-20, Q1):** the first and last risers are measured as drawn, to the floor in front and the
   floor at the head (R318.7.5.1: "The riser shall be measured vertically between leading edges of the adjacent
   treads"; the floor at the head is the top tread's neighbour), so house 3's flight is in scope for the same measures
   as house 2's and comes back as worked by hand: risers 12 x 7 1/2 in and one of 9 in (-0.75 ft to 0), riser height
   9, variation 9 - 7.5 = 1.5, total rise 99 in, 13 risers; never 7.5 in, never a pass. (Before, the cross-check
   held the whole flight for review.) The run's own risers, base to top, are still the cross-check against the typed
   riser height. The drawing puts each stair 10 ft clear of the
   house with its own side walls and floors (a stair's measures don't depend on where it stands), since houses 2 and
   3 draw their stairs inside bedrooms' plans, which a real model can't. Each house is recorded at the latest step
   that draws it (houses 1 and 5 stay step 3). The tick "these are all the stairs" is on Project Information (section 3).
5. **Doors** (after the PR adding doors' stated clear width to the format, decision 2), then **guards**, house 4.
   **Built, tested on fake records; to record in Revit** (section 4, the doors', handrails' and guards' "As built in
   step 5"). Scope (`recordings.py`, `STEPS[5]`): houses 1, 2 and 6 `door_clear_width`, `door_clear_height`,
   `door_side_hinged` (from the maker's clear opening the drawing confirms on each door's type: the less favourable of
   house.yaml's drawn and stated, as the measuring code works it out); house 5 `door_side_hinged` only (its sliding
   door has no clear width worked by hand, so no maker's clear opening is made up: its height expected not
   measured); houses 2 and 4 the stair measures with `stair_clear_width_at_handrail` and `stair_handrail_sides` (each
   handrail a railing on the stair whose top rail is the handrail); house 4 `guard_height` and `guard_opening_sphere`
   (its loft guard a railing between a wall and a post, its rails and balusters house.yaml's), and its rooms and
   window as step 3. House 4's loft is drawn clear of its bedroom (its floor over the bedroom would be the bedroom's
   ceiling, which the hand-worked house doesn't give), and the bedroom's walls stop at the loft's level (walls
   through a level enclose an area on it). House 3 isn't drawn again (its guard is along a stair: not read in this
   step; its stair is measured in step 4 already): it stays step 4. Each door is drawn in an outside wall with
   no window (where it stands doesn't change its measures).
6. **`has_none` ticks.** **Built, tested on fake records; to record in Revit** (section 4, "What the house has none
   of", as built in step 6). Scope (`recordings.py`, `STEPS[6]`): each list a hand-worked house gives empty is ticked in
   the drawing and must come back as that empty list (houses 1 and 6 `stairs: []`; houses 1, 2, 5 and 6 `guards: []`;
   house 4 `doors: []`), every step-5 measure as before. No hand-worked house has a `has_none` claim, so none is ticked
   and the recording's claims must be none (`recording_problems` compares the claims sent and taken with the house's
   own). House 3 has no empty list: it stays step 4. The real house (`test_data/real_houses/orangetown_ny_80_south_william/`,
   placed by its `layout.yaml`) is the first with claims: its seven are ticked and, nothing of those kinds being drawn,
   must each come back, bringing into scope what `has_none.KINDS` says each brings (`recordings.claimed`): its part
   kinds as empty lists, and on every escape opening `opening_into_patio_cover` and `opening_under_projection` (false).
   A claim that doesn't come back fails the recording. A host sends every underside over a room, the floor above's
   rooms' ceilings over its own, so "no sleeping lofts" takes a room's ceiling as the pieces not wholly over lower
   ones (`has_none._top`): before, every two-storey reading refused it.

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

For a real model (Autodesk's Pacific Continental sample, Read inside 2026-11-20), to check at the next run: that each
grille's `SuperComponent` chain reaches its window and its box lies within the window's (the log counts the generic
models set aside and names up to 10 nested ones that weren't); which of the enclosed areas with no Room lie in a
Room of the design checked, and whether the L1 ones are the design options' (the log lists each area's size and
point, and the options with the one checked); that the roof and turret levels take the new level mark; and that no
window's cut is left unread by a wall face Revit gives no edges for (`RevitInterior.Cut` now says so, never a crash).

For stairs (step 4), to check on houses 2 and 3 drawn by the add-in, then on real stairs: that a `StairsRun`'s
geometry gives each tread top as its own flat face (monolithic and assembled run types; a riser board's top under its
tread); that `Stairs.BaseElevation` plus `StairsRun.BaseElevation` / `TopElevation` is the run's foot and top in
internal coordinates; that a straight run created from a path (N-1) treads long gets N risers; whether the `Stairs`
element's own geometry repeats its runs' (step 4 leaves a multi-run stair's sides and overhead out while it does);
`GetStairsPath`'s direction; a run type's nosing length (a nosing on the run but none drawn on the floor at the head
makes the last tread read deeper than typed, so no nosings are sent: to settle with real stairs); real stair types'
supports beside the treads.

For the makers' formulas (section 5a), **not yet verified in Revit**: Marvin's UCA3648 family wouldn't place in the
Pacific Continental sample (every wall: "There exist geometry collision", 2026-11-20); to try in a plain project with
a plain wall. To check on a real Marvin Ultimate Casement family (Marvin's own Revit
download, Window-Casement-Marvin-Ultimate.rfa, loaded into a project) at the next run: that the type's
Manufacturer, Model and shared Window Type and Vent Area read through the Revit API as its PartAtom and type catalog
give them (UCA3648: "Marvin Windows and Doors", "UCA3648", "Ultimate Casement", 8.43 sq ft); that UCA3648 is filled
28 7/8 by 42 in and UCA2864 20 7/8 by 58 in, and a mulled family's type (4W_1H) is not; that the three marks are
written once and a second Mark for egress writes nothing; that `Clear confirmed` stays empty.

For doors, handrails and guards (step 5), to check on houses 1, 2, 4, 5 and 6 drawn by the add-in: that a door made
from Door.rft gives its placed width along `HandOrientation` and its height as its type's; that `Railing.Create` on a
stair's treads then `SetPath` gives a railing the stair lists (`GetAssociatedRailings`) with its top rail along the
new path; that a profile drawn in Profile-Rail.rft with its top on its origin puts a rail's top at its height (the
top rail's and the other rails'); that a baluster family from Baluster.rft, placed from the host at its base offset,
is the height it was drawn (not stretched to the top rail); that the baluster pattern (one baluster, its distance
from the pattern's start, the end space, justified at the beginning) places the drawing's balusters; that the top
rail, other rails and balusters come back as solids of six flat faces; `STAIRS_RAILING_BASE_LEVEL_PARAM` and
`STAIRS_RAILING_HEIGHT_OFFSET` as a railing's base. Then real railings: round handrails (Revit's default profiles are
circular: their curved faces leave a stair's sides and handrails out, to settle), real balusters and posts.

## 10. Escape routes: what the reader sends for a commercial story

**Built 2026-11-21** (branch `feat/revit-route-fields`, on the route measurement of
[docs/decisions/2026-11-20_route_measurement.md](../decisions/2026-11-20_route_measurement.md)): the reader sends the
format's route additions ([the format](../interior/interior_description_format.md#the-route-additions-a-commercial-storys-escape-routes)),
which `model_measurement.routes` reads to draw each story's escape routes. Every key is optional, so a house's
description measures exactly as before. The code: `Gordium.Revit.Reading/RouteReader.cs` (every decision, on plain
records) and `Gordium.Revit.Addin/RevitInterior.cs` (copies the API's values into the records, decides nothing). The
rule is section 2's: a value is sent only when it is read exactly; anything else is left out, its reason in the
notes, and the route code then measures nothing it could get wrong (a key left out is "not read", never a default).

### The marks (section 3's table)

- **`Gordium: Use` on a Room, `Gordium: Can be locked`, `Gordium: Pass through`.** The format decides which rooms a
  route may cross (decision 1a: a corridor, or a room marked pass-through, either one marked not lockable). Each is
  sent only as the architect set it, a word through a fixed table (`RoomUses`: a word not in it is not stated, never a
  near guess). The room's name is a suggestion in the marking list, never sent: a room named "Corridor" whose use is
  unset is still end-only. **Why one `Use` parameter:** Project Information already has `Gordium: Use` (the building's
  use), and Mark for egress refuses to add a parameter whose name another one has, so a second "Gordium: Use" can't
  exist; the same parameter on a Room says the room's use (its tooltip says both).
- **`Gordium: Exit` on a door**, in IBC 2009 1016.1's own list. Unset is not an exit.
- **Blank is shown with its meaning, not as "to mark".** A house never needs these marks, so a blank one is
  `LeftBlank` in the marking list ("not set: an escape route never passes through this room"; "not set: not an exit")
  and doesn't stop "every room, window and door is marked"; a word Gordium doesn't read is "to mark" as any other.
  Once any of them is set, a summary line counts the rooms with all three room marks and the doors marked as exits.

### What is sent, and from what

| Key | From Revit | Left out (with its reason) when |
|---|---|---|
| `levels` | every `Level` holding a room, door or unknown space sent: `UniqueId`, `Name`, `ProjectElevation` in shared coordinates (a roof level with nothing on it isn't a story to walk) | the levels couldn't be read |
| `level` on rooms, doors, unknown spaces | `Room.Level`, the door's `LevelId`, the enclosed area's level | its level isn't one of the levels read |
| room `holes` | a room's second and later boundary loops (the outline is the loop of largest area: Revit doesn't promise the outer loop first); `[]` for none | a loop isn't wholly inside the outline (1/16 in clear), two overlap, or the room is marked a sleeping room: **a floor with a hole is never sent for a room marked Sleeping room Yes**, since the house's floor area reads the outline alone and a bedroom's would count the column (then no `floor`, as before). A room not marked is sent with its holes: with a sleeping flag missing the house's measures read no room at all (the Children's Odyssey KITCHEN, 2026-11-21) |
| room `obstructions` | the room's `Over` collection (every element whose box reaches over it), cut to the room's band: in the Revit layer each of its solids is intersected with a slab over the room's box from 1/16 in above the floor to 80 in up (IBC 1003.3.1's headroom; `BooleanOperationsUtils.ExecuteBooleanOperation`, Intersect), and its footprint is the plan outlines of the result's faces that aren't vertical (a flat face's outline, a curved face's points' convex hull), together exactly what of it stands in the band, whatever its shape (review round 3: picking faces by height kept a standing wall's door threshold and lost the wall). Nothing in the band, no obstruction. `[]` for none | anything not an obstruction category lower than 80 in over the floor (a beam, a bulkhead, a generic model, a low ceiling), any element whose geometry couldn't be read or cut to the band (Revit refused, a mesh, an open shell of surfaces with no volume reaching the band; unless its box is wholly above 80 in), an obstruction the room's solid test found that wasn't read with its geometry, or the floor's elevation unknown |
| door `plan` | `centre`: half way between the host wall's two side faces (`HostObjectUtils.GetSideFaces`, exterior and interior), at the middle along it of the opening the door cuts in the wall (the wall's faces Revit generates from it; never its casing), or, only when no cut is found, of what is drawn of it strictly between the wall's faces (more than 1/16 in from each); `along`: the wall's direction, turned as `HandOrientation`; `clear_width`: the stamp-confirmed `stated_clear` width only, never the type's size; `wall_thickness`: between the faces | no confirmed clear width; the host isn't a straight wall (a curved wall, a curtain wall: no flat side faces); a side isn't one plane (faces more than 1/16 in apart), the sides aren't parallel, or `HandOrientation` isn't along them; no cut found and none of its geometry strictly between the faces; that opening wider than the door and 8 in of frame (a sidelight, a pocket), or its middle more than 1 in from where the door is placed |
| door `sides` | `FromRoom`, `ToRoom` (the last phase), both among the rooms read; or one room and `outside` when Revit gives no room on the other side, the room is found on exactly one side (1 in beyond the wall's face) and no room read is drawn on the other | no room either side, the same room both sides, a room not read (another phase or design option), or Revit's "no room" contradicted by a room drawn there. An enclosed area with no Room beyond a door is an unknown space, which keeps its story needing review whatever its doors say |
| door `swings_into` | the swing the door's own plan symbol draws (below): the side of its wall its leaf's arc lies on, and the room (or `outside`) of its `sides` found there (1 in beyond the wall's face) | the swing isn't read (the model can't be changed for the moment, or Revit gives no plan geometry), none is drawn (never read as a door that doesn't swing), none of its arcs is a leaf's swing from a jamb, swings are drawn on both sides (a double-acting door, a pair hung opposite ways), an arc ends within the wall, its operation is sliding, folding or pocket, or its sides' rooms aren't found one on each side where it swings |
| door `exit_kind` | `Gordium: Exit` | unset (not an exit), or a word not in the table (read as not an exit, with a note; the marking list shows it to mark) |
| door `exit_id` | below | below: the door then isn't read, so its story's routes need review |
| `passages` | each pair of rooms on one level whose boundaries have a straight segment drawn by the same room separation line (`OST_RoomSeparationLines`), on one line within 1/16 in, sharing more than 1/16 in: the shared piece; `[]` for none | the separation lines couldn't be listed |

**Which exit a door enters (`exit_id`).** Two doors into one stair must be one exit (1015.2.1: a scissor stair is
"counted as one exit stairway"), so the id is the stair's, not the door's. For an exterior door at discharge (or to an
exterior stair or ramp) it is the door's own id, and it must open to outside. For a door into an exit stair enclosure
or exit passageway it is the Room it enters: of the two rooms it joins, the one whose every door either opens to
outside or is marked the same kind of exit, and that is open to no room along a separation line (a lobby with only an
exterior door and a stair door is open to the corridor). Both or neither qualifying, or the door opening to outside,
leaves the id out with why ("mark every door into the enclosure"). A horizontal exit's id isn't read yet (the area
beyond its wall isn't one Room): such a door isn't read. The rule is cautious: a stair Room with an unmarked door into
it (a closet) gives no id, never a guess.

**Which side a door swings into (`swings_into`), from its plan symbol** (BCNYS 1010.1.2.1; `RevitInterior.SwingsOf`,
`RouteReader.SwingsInto`). A door's facing and hand flips say which way it swings only by its family's own convention
(the build needs a setting per family, `swing_opposite_facing`), so they are never read for it. The swing is read
from what the family draws: for each level with a door, a floor plan is made inside a transaction always rolled back
(the model unchanged), at Fine detail, with no view template and no filters, the Doors category, every one of its
subcategories (Plan Swing among them) and every user workset shown, so a coarse view, a filter or a hidden
subcategory in the architect's own views never drops the arcs. Each door's geometry in that view gives its arcs in
a horizontal plane (nested families' too). An arc is a leaf's swing when its centre (the hinge) is in the wall (within
2 in of its faces) at a jamb (within 6 in of half the door's width from its centre) and its radius is a leaf's (9 in,
under a pair's narrowest leaf so it always counts, to the door's width and 6 in); its middle must stand clear of a face of the wall, and that face is
the side it swings into. A pair whose leaves swing the same way swings that way. Anything else leaves `swings_into`
out with the reason in the notes: the checker's swing rule then needs review, never a pass.

**`story_outlines` (decision 8's two readings), from Revit's own room logic** (`StoryOutlines.cs`; the Revit layer's
part, `RingOf`, is thin). **outer:** in a transaction group always rolled back (its transactions committed: Revit works a
plan's enclosed areas out again only on a commit, so lines drawn in a sub-transaction were never seen), room separation lines are drawn as a
rectangle 20 ft beyond the level's walls, a Room is placed in the ring between it and the building, and its boundary
at the finished faces is read, the rectangle's loop dropped: the exterior walls' outer faces, each side with the wall
bounding it (doors and windows don't break a room's boundary; interior walls never touch this one). The trial's log
gives each loop's corners and area, and each side with what bounds it. On the Children's Odyssey (2026-11-21, run by
the agent in Revit 2027.4): 46 sides, 16,539.9 sq ft to the outer faces (the sheet's 16,539), 15,970.0 inside. Three earlier readings didn't serve on the Children's Odyssey (2026-11-21): the
walls' cut faces didn't join into loops, the walls' centre lines widened logged every interior T-junction as a gap,
and an area plan made through the API has no area boundary lines (Revit closed no gross area); a slab's edge says
nothing reliable (it may stop at the core, the inside face or past the walls). **inner:** that outline with each side
moved in by the thickness of the wall Revit says bounds it (`Wall.Width`), the corners where the moved sides meet.
A short side Revit gives no element for (at most 2 ft, between two walls: a wall's end showing where two walls in
line stand a hair apart, or a jamb ends at an opening) is kept where it is. Exact for straight walls of one
thickness along a side, since a wall's inside face is its outside face moved by its thickness; read from the rooms instead it would lose what no room covers inside the walls (a shaft, a chase). Left
out, with the reason in the notes, when the ring Room isn't enclosed, Revit's outline is more than one piece
(separate buildings), a side is curved or bounded by something other than a wall (its thickness unknown), two walls
of different thickness run along one straight side, or the level has an enclosed area with no Room (it may be a
courtyard, which the ring never sees and the outline would count as floor); then the diagonal and the story's areas
need review.

**Why the footprints, not the boxes.** A box is bigger than the piece (a desk turned 30 degrees fills twice its area
in an axis-aligned box), and a bigger obstruction is not always the cautious side: routes around it may part sooner,
shortening the common path of travel. The faces give the shadow exactly, flat faces exactly and a curved face by its
points' hull (larger only within that one face).

**`fixed`.** Revit can't tell a movable piece from a fixed one, so each category says it once: furniture movable;
casework, systems furniture, plumbing and lighting fixtures and equipment fixed. Every obstruction counts in the route
code either way; `fixed` is for the measures that come later.

### How we know

`RouteTests` (fake records, `RouteDrawing.cs`: one story with two offices, a corridor, a lobby open to it along a
separation line, a stair room, five doors, a desk and a column). The description read from it goes to the real route
code (`model_measurement.routes.floor.read`, then `paths.StoryRoutes.route`), which reads every story with no reason
to stop and draws the routes: office A out through its door and along the corridor into the stair (exit: the stair
Room), office B along the corridor and across the passage out of the lobby's door, the lobby out of its own. Under
shared coordinates turned 30 degrees and 875,000 ft out the same. Each decision that keeps a false pass out is pinned,
one change at a time: a use, lock or pass-through mark unset or not a word is left out (the route code then never
crosses the corridor: office B gets no route); a room's name is never its use; an unset exit mark is no exit (the
story needs review); two doors into one stair are one exit; a stair Room with a closet door into it gives no id (the
door isn't read); an exterior-door mark on a door between rooms, and a horizontal exit, give no id; a door with no
confirmed clear width, non-parallel wall faces or no flat faces has no `plan` (never the type's width); a door Revit
says opens to no room, with a room drawn there, has no `sides`; a beam at 6 ft, a generic model on the floor, an
obstruction whose geometry failed, or furniture the solid test found but whose geometry wasn't read, leaves the
room's obstructions out, while a beam at 7 ft and a light at 8 ft are no obstruction; a wall cabinet from 4 ft 6 in
counts, and a round table by its hull; a column is a hole only in a room marked not a sleeping room, an inner loop
crossing the outline is no hole, and the outline is found by area whatever the loops' order; no separation lines or
no levels read leaves `passages` or `levels` out (never `[]`); a house's description measures as before; a project
whose `Use` is on Project Information only gets it extended to Rooms. The use and exit words equal the route code's
own tables (`floor.USES`, `floor.EXIT_KINDS`), read from Python.

**A wall standing in a room** (not bounding it: Revit's solid test finds it inside the room's outline) leaves a
sleeping room's floor out, as before (its floor area would count the wall). In any other room the floor is sent and
the wall is an obstruction (kind `fixture`, fixed: the format has no wall kind), its footprint from its faces as any
obstruction's, so routes only lose floor. Anything else standing in a room (a column that doesn't bound it, a generic
model, a stair) still leaves the floor out (the Children's Odyssey ADMINISTRATION, 2026-11-21).

### The eval's marks: set_marks_request.json

The architect hasn't marked the Children's Odyssey model, so the route eval's marks are data, each an eval assumption
with its reason: `test_data/answer_keys/portland_me_19_libby_st/eval_marks.yaml` (every room's use, lock and
pass-through, each door type's clear opening, the exits read from LS1.0's exit arrows and matched to the model's doors by
position). `apps/revit_addin/tools/eval_marks_request.py` turns it into a request, and the add-in writes it by request
file while Revit is idle (`set_marks_request.json` beside the trial log: `{"model", "save_as", "by", "date", "marks"}`,
`SetMarks.cs`, its decisions `MarksRequest.cs`): only a model and a copy under the trial folder are opened and saved,
never the architect's files; Gordium's marks are added to the copy first; a room is found by its number, a door by its
Mark; a word Gordium doesn't read, a value of the wrong kind, a mark not bound to the element, an element not found or
found twice, or two values for one mark are refused with why; a door's clear opening writes its type's operation,
clear width, height and source and the stamp, signed with `by` ("eval assumption (Gordium, not the architect)"), so
the stamp itself says who stood in. Each entry applied or refused is logged (`set_marks` in results.jsonl).

**A door's side with no Room is never called outside on a guess** (the Children's Odyssey's first marked read: 19
doors "to outside", many into classroom toilets and closets with no Room). The Revit layer outlines each enclosed area
with no Room (a Room placed in it for the moment, inside a `SubTransaction` always rolled back; the outline is also sent
as the unknown space's `outline`). A door whose far side Revit gives no room on joins its room and the unknown space
there, by that space's id (the route code then doesn't read the door: its story needs review); while any such area on
its level has no outline, the side isn't sent at all; only with every one outlined and none beyond it is it `outside`.

**The eval's Rooms and model corrections.** The request also places Rooms (`place_rooms`: a level, a point, the sheet's
name and a number no Room has) before it marks: each where Revit gives it an area, in the last phase and on no Room
already there, else taken back and logged. eval_marks.yaml classifies each of the 18 enclosed areas: 14 spaces the
sheet draws (the west vestibule, two sprinklered abandoned spaces, six toilet rooms, five closets) get a Room; the two
slivers Revit can't locate come from the trace's five overlapping wall pairs, which the build's new trims remove
(`trim_end_to`, `trim_start_to`: a wall shortened along its own line by at most 2 ft, never lengthened or turned,
BuildData.Correct); the two 1.4 sq ft triangles inside the east entry's angled jambs are solid wall on the sheet, so a
`fill` adds a short wall over each (at most 3 ft long and 2 ft thick, every corner within 2 ft of a wall of the data:
a fill between walls, never a wall standing alone). The Revit layer lists every collector before it changes the
model (the outlines' Rooms placed for the moment made a live iterator throw on the first run). `eval_marks_request.py --build-data
--build-out` writes the build request with the corrections too.

### To try in Revit (the Children's Odyssey model)

Read inside by request (`read_inside_request.json`, `{"model": "<path>.rvt"}`, section 9): the log's `routes` line
counts what was read (levels; rooms with a level, floor, holes and obstructions; doors with a place in the wall, sides
and exits; passages), `evidence.route_doors` gives each door's centre and wall thickness as read (sent or not), and
`interior` is the description, for `model_measurement.routes` to read. Unmarked, no door has a confirmed clear width
or an exit, so the first run checks the Revit layer: that `GetSideFaces` gives each door's wall faces, `FromRoom` and
`ToRoom` its rooms, separation lines the passages, and which categories stand in the rooms. Where a door is along its wall is the opening it cuts in it (the wall's faces Revit generates from the door, never the casing on
the wall's faces, review round 3), else what is drawn of it strictly between the faces; an opening wider than the
door and 8 in of frame (a sidelight, a pocket) or centred more than 1 in from where the door is placed leaves `plan`
out. To check there: that each
door's centre lies in the middle of its wall within 1/16 in of both rooms' faces (the route code's own test); that a
real door family's frame is centred on its clear opening (a side-hinged door's clear opening sits off the frame's
centre by up to half the difference between the frame and the clear width, about 1 in on a 3 ft door; the route
code places the jambs' 12 in rings from it); what a stair Room with its stair drawn in it gives (open question 1).

### Open questions

1. **A stair Room with its stair in it isn't read.** A stair standing in a room leaves its floor out (section 4, the
   room's own rule), and a stair is none of the format's obstruction kinds; so a door into it isn't read and a story
   whose exits are stair Rooms needs review. The format needs a way to say a door enters the exit (its far side the
   exit itself, not a room): the route code's question, asked there.
2. **The clear opening's centre** is the door frame's (above), to measure on real families.
3. **Systems furniture and equipment as fixed**, a reading for the measures after travel distance.

## Sources

The interior format, the measuring code and the egress decisions named above (read 2026-11-19). The Revit API
members named here (`Room.GetBoundarySegments`, `SpatialElementBoundaryOptions`, `FamilyInstance.FromRoom`/`ToRoom`,
`Stairs.ActualRiserHeight`/`ActualTreadDepth`, `StairsRun.ActualRisersNumber`, `Stairs.GetAssociatedRailings`,
`Railing.HostId`/`GetHandRails`/`TopRail`) were each found in the trial laptop's Revit 2027.4 `RevitAPI.dll` (2026-11-19), and the class each
belongs to was checked in this note's first review round (the stair's typed riser and tread are on `Stairs`, not
`StairsRun`); how each behaves on real models is checked in the trial before code relies on it (section 9).

Makers' clear openings (section 5a), each downloaded and read 2026-11-20: Marvin's Ultimate Casement Revit families,
https://www.marvin.com/f/1019562/x/b07c991491/marvin-ultimate-casement-revit.zip (from
https://www.marvin.com/support/technical-specifications/ultimate-casement-window; never committed here):
Window-Casement-Marvin-Ultimate.txt's row "UCA3648,Marvin Windows and Doors,Ultimate Casement,36,48,Yes,DP50,3648
CSMT,UCA3648", and the .rfa's PartAtom (Window Type, shared, eafa4376-701d-423a-906c-e9e76dd752ca; Vent Area, shared,
0d21ad7d-0db0-489a-a1fa-10d502d650b7, 8.43 SF; Width 3' - 0", Height 3' - 11 1/8", Rough Width 3' - 1"). Marvin, Architectural Detail Manual,
Ultimate Casement, Awning and Picture (UCA UCANF, 14131101),
https://marvin.com/f/1019562/x/eaabd5bb0d/adm-ultimate-casement-awning-picture.pdf (SHA-256 19e504b6...b411), pages
UCA UCANF-1, -2, -6, -25 and -29; Andersen, A-Series double-hung size guide (2023-24 A-Series Product Guide),
https://www.andersenwindows.com/-/media/aw/files/technical-docs/sizing/sizing-windows--a-series-hung.pdf, page 3 of 3
("Clear Opening* Width = window width - 4.06"" and its heights; no clear-opening rows); Pella, Reserve casement ADM,
https://media.pella.com/professional/adm/Clad-Wood/Pella-Reserve_Casement.pdf ("Clear opening (egress) information does
not take into consideration the addition of a Rolscreen (or any other accessory) to the product", page 20 of the PDF).
