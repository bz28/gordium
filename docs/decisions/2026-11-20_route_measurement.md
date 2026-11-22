# How Gordium will measure egress routes in a commercial building (2026-11-20)

**Purpose:** the plan, before any code, for measuring a story's escape routes from a model's interior description: travel distance, common path, dead ends, exit remoteness, and the areas the occupant load and storage limits read. First use: a day-care centre checked against the 2009 IBC and NFPA 101 (2012), as Maine's codes.\
**For:** Ben (the open questions at the end), the engineer who builds it, a Revit reader's authors, and architects who want to know how Gordium draws a route.\
**Kept current by:** the engineer who builds each step below, in that PR.

**Status: a proposal, not built.** The measures are defined in words on branch `feat/maine-commercial-egress`
(`packages/rule_format/rule_format/parts.yaml`: part kinds `story`, `space`, `corridor`). Principle 6 says the code
that measures them is written by engineers and tested on real models; principle 4 says anything Gordium can't
measure for certain gives "needs review", never a pass. This note is how both will hold.

## What the law asks us to measure

Quotes are from the copies on branch `feat/maine-commercial-egress` (its `sources.yaml`, the code cache). The IBC
copy is an OCR text, so **every IBC quote is "read from an OCR copy only: not verified"** until checked against a
purchased ICC copy (that branch's decision note); run-together words are separated here. NFPA 101 is NFPA's own PDF.

| Measure | The law (edition, section, page of the PDF) |
|---|---|
| Travel distance | IBC 2009 1016.1 (p.267): "measured from the most remote point within a story along the natural and unobstructed path of egress travel to an exterior exit door at the level of exit discharge, an entrance to a vertical exit enclosure, an exit passageway, a horizontal exit, an exterior exit stairway or an exterior exit ramp". NFPA 101 2012 16.2.6.1 (p.174): "Travel distance shall be measured in accordance with Section 7.6." 7.6.1 (p.81): "(1) Along the centerline of the natural path of travel, starting from the most remote point subject to occupancy (2) Curving around any corners or obstructions, with a 12 in. (305 mm) clearance therefrom (3) Terminating at one of the following: (a) Center of the doorway". 7.6.1 is not yet a brought-in piece on that branch (quoted from the cached text; to bring in). |
| Common path | IBC 2009 1002.1 (p.244): "That portion of exit access which the occupants are required to traverse before two separate and distinct paths of egress travel to two exits are available. Paths that merge are common paths of travel." Limit 1014.3 (p.265): "shall not exceed 75 feet". NFPA 3.3.47 (p.31) says the same in fewer words; 16.2.5.3.1: 100 ft sprinklered. |
| Dead end | IBC 2009 1018.4 (p.269): "no dead ends in corridors more than 20 feet (6096 mm) in length", exception 3: "A dead-end corridor shall not be limited in length where the length of the dead-end corridor is less than 2.5 times the least width of the dead-end corridor." NFPA 16.2.5.2 (p.174): 20 ft, 50 ft sprinklered. |
| Remoteness | IBC 2009 1015.2.1 (p.266): "not less than one-half of the length of the maximum overall diagonal dimension of the building or area to be served measured in a straight line between exit doors or exit access doorways"; exception 2 (sprinklered per 903.3.1.1 or 903.3.1.2): "not be less than one-third". NFPA 7.5.1.3.2 (p.80) says where: "measured in a straight line between the nearest edge of the exits" (not yet a brought-in piece on that branch: from the cached text). |
| Rooms a route may cross | IBC 2009 1014.2 (p.264, not yet brought in: from the cached text): "1. Egress from a room or space shall not pass through adjoining or intervening rooms or areas, except where such adjoining rooms or areas and the area served are accessory to one or the other, are not a Group H occupancy and provide a discernible path of egress travel to an exit." "2. An exit access shall not pass through a room that can be locked to prevent egress." "4. Egress shall not pass through kitchens, storage rooms, closets or spaces used for similar purposes." NFPA 101 2012 7.5.2.1 (p.80, not yet brought in): "Access to an exit shall not be through kitchens, storerooms ..., restrooms, workrooms, closets, bedrooms or similar spaces, or other rooms or spaces subject to locking"; 7.5.1.6 (p.80, not yet brought in): "Foyers, lobbies, and reception rooms constructed as required for corridors shall not be construed as intervening rooms." |
| Areas, occupant load | IBC 2009 508.2.1 (10 percent of "the building area of the story"); 1004.1.1 (p.246): "dividing the floor area under consideration by the occupant per unit of area factor"; Table 1004.1.1, day care 35 net. 502.1 AREA, BUILDING (p.106, brought in: the branch's `definitions.yaml`): "The area included within surrounding exterior walls (or exterior walls and fire walls) exclusive of vent shafts and courts." |

## What the description holds today, and what it lacks

The interior description (`gordium.interior/1`, [format](../interior/interior_description_format.md)) was made for
houses. Measured by `packages/model_measurement/model_measurement/interior/` (`rooms.py`, `doors.py`, `geometry.py`, ...).
What the Revit reader (`apps/revit_addin/src/Gordium.Revit.Reading/InteriorReader.cs`) sends today:

- **rooms:** `id`, `name`, `sleeping`, `floor` (one outline at the finished wall faces, no holes), `floor_elevation`,
  `ceilings`. A room with a column inside it (two boundary loops) or a curved wall gets no `floor`.
- **doors:** `exit` (the *dwelling's* exit door, R318.2), `operation`, `stated_clear`. **No position, no rooms on
  either side, no wall thickness.** The reader holds them (`OpeningRecord.Location`, `Along`, `FromRoom`, `ToRoom`)
  but doesn't send them.
- **openings** (windows and doors as escape openings, each with its `room`), **unknown_spaces** (`{id, name}`: an
  enclosed area with no Room; no outline), stairs, guards, `has_none`. **No levels:** a room has an elevation, not
  a story.

So a route can't be drawn yet: nothing says where a door is or which rooms it joins. The reader must add (all
optional keys, so a house description measures exactly as before):

| Addition | What it says | From Revit |
|---|---|---|
| `levels: [{id, name, elevation}]`; `level` on rooms, doors, unknown spaces | which story each part is on | `Room.LevelId`, the door's `LevelId` |
| room `use`: `corridor`, `lobby`, `day_care`, `accessory_storage`, `kitchen`, `toilet`, `closet`, `workroom`, `other`; room `lockable`, `pass_through` (true or false) | a corridor is a room marked as one (IBC 1002.1 CORRIDOR); which rooms a route may cross (decision 1a); the areas | a new `Gordium: Use` mark; a room's name may *propose* one, sent only once ticked |
| room `holes` | the outline of each column or chase inside it, so a room with a column is read, not dropped | the second and later boundary loops |
| room `obstructions: [{outline, kind, fixed}]` | the plan footprint of casework, furniture, equipment, fixtures | elements of those categories over the room, as the ceilings' collection already finds them |
| door `plan: {centre, along, clear_width, wall_thickness}`, `sides: [room id or "outside", ...]` | where its clear opening is and what it joins | `Location`, `HandOrientation`, `FromRoom`/`ToRoom`, the host wall's width, `stated_clear` |
| door `exit_kind`: `exterior_at_discharge`, `exit_enclosure`, `exit_passageway`, `horizontal_exit`, `exterior_stair_or_ramp`; with it `exit_id` | which doors are exits, in 1016.1's own list, and **which exit** each enters: every door into one stair enclosure (or both entries of a scissor stair, 1015.2.1: "counted as one exit stairway") carries the same `exit_id` | a new `Gordium: Exit` mark (never inferred; a door in an outside wall with nothing beyond may *propose* `exterior_at_discharge`); `exit_id`: the enclosure's Room or the stair's `UniqueId`, an exterior door's own |
| `passages: [{rooms, line}]` | two rooms joined with no wall or door between (a Revit Room Separation line) | boundary segments whose element is a separation line |
| `story_outlines: [{level, outer, inner}]` | the outside faces and the inside faces of the story's exterior walls | the exterior walls' faces at the level |
| unknown space `outline` | where it is | the enclosed area's loop |

A house reader sends `exit: true|false` on every door as now; a commercial building with no dwelling sends `false`.

**A key left out is "not read", never a default** (the format's own rule). No `levels`, or a part with no `level`:
every route measure of the building (or of that story) needs review. A room with no `use`: it can't be crossed
(decision 1a), and every area that counts uses needs review. No `lockable` or `pass_through`: not crossable. No
`obstructions` key (as against `[]`) or no `passages` key: the story's route measures need review. A door with no
`plan` or `sides`, or an `exit_kind` with no `exit_id`: needs review. No `story_outlines`: the diagonal and the story
area need review.

## Decisions

1. **The path: shortest walk on the real floor, around obstacles, with NFPA's 12-in clearance.** The floor is the
   rooms' outlines (minus holes and obstructions), joined at door openings and passages. A route goes in straight
   lines, turning only around corners. Around every corner that sticks into the walking space (a wall's end, a
   column, a cabinet) it keeps 12 in away, curving round (7.6.1(2)), and it passes through every door at the centre
   of its clear opening, in the middle of the wall (7.6.1(3)(a) "Center of the doorway"). A door's jambs are corners
   too and get their 12-in rings: a route that turns just past a door keeps 12 in off the jamb. A door less than
   24 in clear puts its own centre inside its jambs' rings: needs review. Exactly: **crossable** rooms (decision 1a)
   joined by passages form one zone; an end-only room is always a zone of its own, never merged across a passage.
   Inside each zone, routes as decision 2 defines them; between zones, through the door centres. A start point in an end-only room is the one exception: its own room is joined, for its routes only, to
   each **crossable** zone beyond its passages (a route may leave it that way, never come back in). A passage into
   another end-only room (a kitchen open to a pantry) is no way out for anyone (test 17).
   The IBC's "natural and unobstructed path" names no clearance; Gordium uses NFPA's 12 in for both books. That can
   only lengthen a route, so it can make a borderline design need review or fail, never pass one that shouldn't.
   *Rejected:* **a grid** (a walk on squares): never exact, its error depends on direction (up to 8 percent at 45
   degrees on an 8-way grid) and on where the grid falls; **rectilinear** (along x and y only): up to 41 percent
   long, not "natural"; **corridor centre lines** for the whole route: 7.6.1(1) says "centerline of the natural
   path", which Gordium reads as the middle of the path walked, with (2) setting how close it comes to corners; the
   corridor-centreline reading is open question 1. **One graph for the whole story**: slow, and it would let a
   straight line cut across an end-only room joined by a passage; between zones every route passes a door centre,
   so splitting by zone gives the same lengths as one graph over the crossable floor.
1a. **Which rooms a route may cross** (IBC 1014.2, NFPA 7.5.1.6 and 7.5.2.1). A route may start anywhere, ends at an
   exit, and passes only through the room it starts in, corridors, and rooms marked `pass_through: true` (the
   architect stating the room is accessory to the ones it serves, with a discernible path to an exit: 1014.2 item 1,
   which NFPA 7.5.1.6 also allows). A `lobby` is no exception: the IBC names none, and NFPA's covers only lobbies
   "constructed as required for corridors", so a lobby is crossed only with `pass_through: true`. Every crossable
   room also states `lockable: false`. Kitchens, storage, toilets, closets, workrooms, sleeping rooms, rooms with
   `lockable: true` or no `lockable`, and rooms with no `use` are **end-only**: a route may start in them, never
   cross them. End-only always wins: `pass_through: true` on an end-only use or with `lockable: true` is refused on
   read (that room not read, so its story needs review). A room whose only way to an exit crosses an end-only room
   needs review (an exception, such as 1014.2's for a kitchen, may allow it; Gordium doesn't assume one). This only
   removes routes, so it only lengthens them.
   **A room that opens only into the room it serves** (amended 2026-11-21; Gordium's reading, open question 11). A
   closet, a storeroom or a toilet (`use` `closet`, `accessory_storage` or `toilet`) whose every opening is a door
   into one end-only room, and no door of it an exit, is taken as part of that room, the room it serves: its route
   starts in it, leaves by one of those doors into the room it serves, and goes on as a route that started there (that
   room's own doors and passages, never across any other end-only room). The room served must state its `use` and
   `lockable: false`: one that can be locked, or whose locking isn't given, still blocks (1014.2 item 2, 7.5.2.1
   "subject to locking"), and the inner room keeps no route, the reason named. It chains: a closet that opens only
   into a storeroom that opens only into another is part of both (its doors into rooms that open only into it don't count as
   ways out). A room with a passage, a room of any other use (a classroom, a kitchen, an electrical room marked
   `other`) and a room with two rooms beyond it (not counting rooms that open only into it) are not covered: they keep decision 1a's rule. A door from such a room
   into the room it serves is an exit access door (decision 11). Every figure this reading reaches says so beside it
   ("Gordium's reading · confirm with the architects"), the part's `confirm`, and the checker puts it in each row that
   reads that figure. **Such a figure never passes until the reading is confirmed** (principle 4; amended 2026-11-21,
   review round 2: the words forbid it and the strict reading has no figure): a row that would comply needs review,
   "complies only if this reading is confirmed: ...", as the checker already does for a has-none reading
   (`each_part.check_parts`); a row that fails still fails, with its comparison and the reading beside it (it fails
   under the reading, and under the strict one the room has no legal way out at all). It only adds routes where none
   were (never shortens a route that existed): a room it covers had no route before, so its story needed review.
   *Why (resolved before asking, 2026-11-21).* The whole law: IBC 2009 1014.2 (read from the OCR copy only: not
   verified) item 1 "Egress from a room or space shall not pass through adjoining or intervening rooms or areas,
   except where such adjoining rooms or areas and the area served are accessory to one or the other, are not a Group
   H occupancy and provide a discernible path of egress travel to an exit"; item 2 "An exit access shall not pass
   through a room that can be locked to prevent egress"; item 4 "Egress shall not pass through kitchens, storage
   rooms, closets or spaces used for similar purposes", whose only exceptions are "a kitchen area serving adjoining
   rooms constituting part of the same dwelling unit or sleeping unit" and Group M stockrooms (2.1 to 2.4: same hazard,
   "Not more than 50 percent of the exit access is through the stockroom", "not subject to locking from the egress
   side", a 44-inch demarcated aisle). NFPA 101 2012 7.5.1.6 (p.80): "Exit access from rooms or spaces shall be
   permitted to be through adjoining or intervening rooms or areas, provided that such rooms or areas are accessory
   to the area served"; 7.5.2.1 (p.80): "Access to an exit shall not be through kitchens, storerooms other than as
   provided in Chapters 36 and 37, restrooms, workrooms, closets, bedrooms or similar spaces, or other rooms or spaces
   subject to locking, unless passage through such rooms or spaces is permitted for the occupancy by Chapter 18, 19,
   22, or 23" (day care, Chapter 16, is not among them); A.7.5.2.1: "It is not the intent that an area with equipment
   such as a beverage brewpot, microwave oven, and a toaster be considered a kitchen"; 7.6.1(1) (p.81) measures travel
   "starting from the most remote point subject to occupancy"; and, for day care, 16.2.2.2.4 (p.174): "Every door
   latch to closets, storage areas, kitchens, and other similar spaces or areas shall be such that clients can open
   the door from inside the space or area", A.16.2.2.2.4 (p.412): "The purpose of this requirement is to prevent
   arrangements whereby a client can be trapped in a space or area". So the books expect people inside closets and
   storerooms, measure travel from them, and send them out by the door they came in; none says where that door may
   lead, and item 4's words, read alone, forbid even a pantry's way out through its kitchen. Interpretations found on
   the public web (no ICC or NFPA viewer read): the North Carolina Department of Insurance's appeal decision on egress
   of a Group B office through a Group S-1 warehouse (Fleming / Town of Apex, 2021-10-26,
   https://ncosfm.gov/appeals/20211026-fleming-empire-distributers-ncdoi-decision/open, read 2026-11-21) quotes the
   2015 IBC Commentary on 1016.2 (2009's 1014.2): "it is not the intent of this provision to address the situation of
   egress for offices through an associated warehouse space", and concludes the item's intent "was to disallow egress
   from one area though another area where the possibility of a blocked means of egress path is probable either by
   hazard or locked doorways. It appears that 'storage rooms' are listed because of the possibility of locked doors in
   the path of egress and because of uncertain egress path through such rooms". Wisconsin's commercial-buildings egress
   FAQ (https://dsps.wi.gov/Documents/Programs/CommercialBuildings/FAQEgress.pdf, cited in search results 2026-11-21,
   the page itself not found when fetched) is reported to allow egress through a storage room accessory to the area
   served with a discernible path, and to caution against a small storeroom that can become crowded. Forum threads
   (thebuildingcodeforum.com, not readable by script) lean both ways; they are not interpretations. **Classified:
   strong common practice, not answered by the law** (the words forbid it, the measuring and day-care sections
   assume it, the stated intent is a path another area's occupants can't trust or that can be locked, which a room's
   own closet isn't): Gordium's reading, always shown, to confirm (open question 11). Not adopted: two named readings
   (a strict one beside it): the strict reading gives such a room no route, so no figure, and a rule could then never
   pass under both: the same as needs review, with nothing gained. *Not covered, a separate to-do:* a space not
   subject to occupancy (7.6.1(1); the sheet's abandoned spaces, "DOOR PERMANENTLY FIXED SHUT", the electrical room):
   the description has no mark for it, so such a room keeps decision 1a's rule (no route, needs review) until a
   "not occupied" mark exists.
2. **What a route is, exactly.** The route from a point p to an exit is **the shortest curve** that (a) lies in the
   zone's free floor: the crossable rooms' outlines (decision 1a) minus walls, holes and obstructions, joined
   through door openings, passing each door at its centre; (b) stays at least 12 in from every corner: each wall
   corner that sticks into the floor, each corner of an obstruction, each door jamb (a ring: a true circle of 12-in
   radius). **A route is defined only from a point clear of every ring** (at least 12 in from every corner; on a
   ring's edge counts as clear); its length is written D(p). No route is defined from inside a ring: what the story
   figure owes the points there is decision 3's cluster margin (the walk out to the clear edge, then that edge's
   route), and that is Gordium's reading (open question 9). A door centre inside a ring (a door within 12 in of
   another corner) needs review, named, as no route through it is defined. *Rejected:* defining a route from inside a
   ring, two ways. Letting the curve run anywhere within a ring holding p until it left: the length jumps at the
   ring's edge (behind test 1's corner, 35.380 ft just inside, 36.665 ft just outside, over a hair's step). Going
   straight out to the ring's clear edge first: still a jump (1.04 ft at the same place, since a straight line
   across the ring beats the arc round it). Neither gives a figure a sampling bound can hold, and neither is the law's.
   **An opening narrower than 24 in.** Two corners less than 24 in apart have overlapping rings, and a corner less
   than 12 in from a wall has its ring on the wall: no clear curve passes between them. Where every way out of a
   point is closed so, the point has no route of its own: it is in a **pocket** shut in by that ring cluster, and
   (decided 2026-11-21, Ben through the coordinator: such nooks, beside jambs, behind doors, small alcoves, are in
   almost every real story, and needs review for each made nearly every real story need review) the pocket belongs
   to the cluster: decision 3 bounds its points as it bounds the points inside the rings (test 18: the back of a
   niche 20 in wide and 2 ft deep is now a number). Only a pocket with no routed clear edge round it (truly shut in)
   needs review. A door is the one opening a route passes at its centre (decision 1). Gordium's reading (open
   question 10).
   **Two lengths within 10^-6 ft of each other are a tie**, broken toward the cautious
   reading (decision 5: the route that shares more). It is computed exactly (shortest paths among circles and
   polygon obstacles are a standard, exact computation); the build PR's code and its tests are the procedure, and
   each test's figure here comes from this definition, worked two ways. *Rejected:* rings as polygons (an earlier
   draft): the length round a polygon depends on how it is turned, enough to move test 6's figures and lose its tie.
3. **The most remote point: every corner, plus a fine sampling with a stated bound.** For one exit and a room with no
   column, the farthest point is always a corner of the room: the route to any point ends in a straight line from
   the last corner it turns at, distance from that corner grows toward the edges of the area it sees, and where two
   last corners meet the two lengths agree smoothly, so the maximum can't sit there (a known result: S. Suri, J.
   Computer and System Sciences 39, 1989; Aronov, Fortune and Wilfong, Discrete Comput. Geom. 9, 1993: in a simple
   polygon the geodesic farthest point is a vertex). **It is not true in general:** with two exits the farthest
   point is where the two routes are equal (a corridor with an exit at each end: the middle, on a wall); with three,
   it can be in the open floor; with a column, it can be behind it where the two ways round are equal (test 2 below).
   So the story's figure is the greater of two parts, each a proved upper bound: **F**, the floor clear of every
   ring, where routes are defined (with **E**, the rings' clear edges: the arcs of each ring's circle on the floor
   and clear of every other ring, found exactly from the circles); and **the clusters**, each group of overlapping
   rings, for the points inside them.
   - **F: sampled, with a proved bound.** In F the route's length is D (decision 2), and D can't grow faster than you walk
     along any curve in F (from x, walk to y and take y's route: that is a route for x). Every arc of E is sampled
     at most 3 in apart along it, ends included, so every point of E is within 1.5 in, walking along E, of a sample.
     The floor is cut into triangles, every corner of the floor among their corners, and every triangle corner in F
     is a sample. A triangle no ring reaches lies in F, and each of its points is within h (its farthest from all
     three corners) of one, in a straight line inside it. A triangle a ring reaches: from a point x of it in F, the
     straight line toward the nearest point of that ring in the triangle stays in the triangle, and the first ring
     edge it meets, y, is in E, at most the triangle's longest side away. So, with triangles no longer than 3 in a
     side: **every point of F is within the greatest sample plus 3 in** (a triangle in F; h is under 3 in), **or plus
     4.5 in** (3 in to E, 1.5 in along it), the cautious figure being the triangle's own. (Only where it matters:
     triangles start 2 ft across, and a triangle no ring reaches is dropped only when its greatest corner value plus
     its own h (the greatest distance from any of its points to its nearest corner: about 1 ft for a 2-ft triangle,
     under 3 in only once cut to 3 in) can't beat the best found so far, which that bound makes safe (test 19); a
     triangle a ring reaches is never dropped, but cut to 3 in and every corner taken.) And a point of F with no route is never missed: its straight line to a triangle
     corner, or to E and along it, reaches a sample that has none too, so the story needs review.
   - **Each cluster: its clear edge's greatest route plus its margin.** For a cluster (one ring, or rings that
     overlap), take the greatest D over its clear edge (its arcs of E that have a route, each sampled as above, plus
     1.5 in), and add the cluster's **margin**: an upper bound on the walk on the floor, with no clearance, from any
     point inside the cluster to that edge. For a lone ring whose floor is all in sight of its corner (no floor edge
     but the corner's own two meets the ring), the margin is 12 in: the walk straight out from the corner through the
     point. Otherwise it is worked like D: W(p), the shortest walk from p to the cluster's routed clear edge, can't
     grow faster than you walk, so it is sampled at the corners of 3-in triangles covering the cluster's floor and
     bounded by the greatest sample plus 3 in. This is cautious by construction: from inside a ring, the law's route
     is at most that walk plus the edge's route (open question 9). **A pocket** (clear floor whose points have a
     route only with no clearance, shut in by rings: the back of a niche under 24 in, test 18) is bounded the same
     way: the greatest route on the routed clear edge of the clusters round it, plus 1.5 in, plus the greatest walk
     on the floor with no clearance from any point of the pocket or of those rings to that edge (sampled at the
     corners of 3-in triangles, plus 3 in). It is an upper bound on what Gordium gives a pocket's points (the walk
     out, then that edge point's route) for the same reason as a cluster's: the walk can't grow faster than you
     walk, and the edge's routes are bounded as E's are. An edge arc facing a pocket has no route and is no part of
     the routed edge; a pocket (or cluster) with no routed clear edge round it needs review, the reason named.
     Every arc of E is found exactly from the circles and every arc sampled, ends included, so a pocket shut in by
     rings is found from its own arcs, never left to where samples fall.
   The rules get the greatest of these bounds; the panel shows the greatest sample, each bound and which part (the
   clear floor, or which cluster) gave the figure.
4. **Exits are marked, never guessed.** A route ends at the centre of the doorway of a door marked with `exit_kind`.
   No exit marked on the story: every route measure there needs review. `exterior_stair_or_ramp`, and any route
   through an unenclosed stair (1016.1's "measurement along stairways"), need review until built.
5. **Common path: measured on the routes themselves, until they part for good.** IBC 1002.1: "Paths that merge are
   common paths of travel." From a point, Gordium takes its shortest route (decisions 1 and 1a) to each distinct
   exit (by `exit_id`, never by door). For two routes, the common path is the travel distance from the point to the
   **last point the two routes share** (a door centre, a ring, a stretch walked together); so a stretch where they
   meet again after parting counts, and two routes that share only the start give 0. The point's common path is the
   least over the pairs of distinct exits: the law ends it as soon as two distinct paths are available, whichever
   two. Where two routes to one exit are equally short (within 10^-6 ft, decision 2), the one that shares more is
   taken (the cautious side). Taken
   on the real geometry, two doors of one room still give a common path when both routes go round the same corner
   first (test 6).
   **Why the bound of decision 3 holds.** The law's figure at a point p is the least, over every pair of paths a
   person could take to two distinct exits, of the distance to their last shared point. It changes no faster than
   you walk: from a nearby p', walk straight to p and follow p's best pair; both paths share that first straight
   stretch, so the figure at p' is at most the straight distance plus the figure at p. Gordium's shortest routes are
   one such pair, so its figure at a sample is never less than the law's. So the story's figure is worked exactly
   as decision 3's, with decision 3's margins: on the clear floor the greatest sample plus 3 in (or 4.5 in in a
   triangle a ring reaches; a triangle dropped only on its greatest corner value plus its own h, as in decision 3, the walk to E and along it being shared by both routes); for each cluster, the greatest
   common path over its routed clear edge plus 1.5 in plus the cluster's margin (the walk out is shared by both
   routes, so it adds to the common path in full); the rules get the greatest of these, never less than the law's
   greatest. No cells and no cases: it is
   decidable on any floor: per sample, its route to each exit (decision 2), and per pair of exits a walk back along
   the two routes to their last shared point. One exit on the story: the
   common path is the travel distance.
6. **Dead end: from the corridor's shape.** A corridor (a room marked `corridor`) is split into its straight legs
   (each a stretch between parallel walls; recesses shallower than 12 in, such as a door's, ignored); the centre line
   runs midway between each leg's walls and legs meet where their centre lines cross. Only corridors count here
   (the corridor and the corridors joined to it): reaching an exit means reaching, along **crossable** corridors
   (decision 1a: `lockable: false`), a door of an exit (`exit_kind`); a route through a room, or through a corridor
   that is end-only, never counts (test 16). A point on the centre line is in a dead end when, cut
   there, one side reaches no exit. The dead end runs along the centre line from the closed end wall to the first
   point from which **routes in two different directions each reach a distinct exit** (by `exit_id`), without coming
   back: a crossing whose two ways both lead to exits, or an exit door in the corridor itself. A crossing whose other
   ways are closed doesn't end it (test 11). A door into a room with another way out never ends it (that room would
   be an intervening room, 1014.2 item 1 and 7.5.1.6). Where such a door would end it sooner, the length is given
   as two named readings for open question 7 (without the door, the defined value; with it), the way the checker
   already takes readings (`design_checker/check.py`, `readings_of` and `named_result`): the row complies only if it
   complies under both, fails if it fails under both, and otherwise needs review. Measuring to the crossing's centre
   line (not its near edge) is the longer reading (open question 2). The least width (exception 3) is the narrowest
   distance between that dead end's own legs' walls (and obstructions in it). **Several dead ends in one corridor:**
   each is its own pair (its length, its own least width). The branch's `corridor` part holds one pair, so it
   becomes a part kind of its own there (`dead_end`, its two measures, one row per dead end); until then the
   corridor gives one part per dead end (built 2026-11-21, review: the cautious pair, the longest length with the
   least width of any, could fail a corridor whose every dead end complies): the corridor's part holds its longest
   dead end's own pair, each further one a part "<corridor> (dead end n)" with the corridor's other measures. A
   closed end is the farthest point of the real floor across the leg's whole width (a recess under 12 in, filled to
   find the legs, never moves it); any recess the closed end runs into is part of the dead end (walls only: an
   obstruction never shortens it). A dead end's least width is one figure: the narrowest cross-section of the clear
   floor (the real floor less every obstruction and hole) across its legs' whole width, over its own stretches and
   any recess at its closed end, each slice's clear pieces added; a sliver under 1/16 in is no floor. A corridor that isn't made of straight legs
   meeting at right angles (at any rotation) needs review in this first version.
7. **Remoteness and the diagonal: straight lines, exact.** The distance between two exits is the straight line
   between the nearest edges of their clear openings (NFPA's words; the IBC names no point, and the nearest edge is
   the shortest choice), through walls, as the books say "in a straight line". Between two exits with several doors
   each, their closest pair of doors counts; the two farthest-apart exits (by `exit_id`) count. Fewer than two
   distinct exits: no remoteness (needs review where two are required).
   The diagonal is the longest straight line between two corners of the story's **outer** outline (the longest line
   in a polygon always ends at corners, so this is exact; the outer faces give the longer diagonal, the cautious
   side). The ratio is the branch's `exit_remoteness_ratio`.
8. **Areas: two readings each, as the checker takes readings.** 502.1 measures building area "within surrounding
   exterior walls" without saying which face, and nothing says where a storage room's area stops. So
   `story_building_area` is given as two named readings for one open question (inside the exterior walls; to their
   outer faces), and `story_accessory_area` (the rooms marked `accessory_storage`) as two for a second question
   (inside their walls; to the outer faces of the walls around them), with no single value. The checker
   (`readings_of`, which combines readings question by question, so two questions give all four pairs, and
   `named_result`) then gives the 10 percent rule (508.2.1): complies if it passes under all four, which is the
   largest accessory area over the smallest story area; fails if it fails under all four; else needs review,
   naming the readings it fails under. The branch's `story_accessory_area` meaning ("to the inside of the walls")
   must change to say so, on that branch. Day-care net area: the rooms marked `day_care`, inside their walls (Table
   1004.1.1 "net"); the computed occupant load is that divided by 35, and a stated load below it needs review
   (1004.1.1's exception needs the building official).
9. **Tolerances.** Points within 1/16 in are the same point, as elsewhere in the interior code. Route lengths are
   exact to floating point (decision 2); the greatest over a story carries decision 3's margins (added). A measure is compared with
   its limit as given; a measure exactly at a limit is what the model says (20'-0" is "not more than 20 feet").
10. **What always gives needs review (the story's route measures), with the reason shown:** an unknown space on the
    story (its outline unknown, it may hold the most remote point or a route; with its outline, one no door or
    passage reaches stays needs review until open question 4 is settled); a room on the story with no `floor`
    (a curved wall: never its chord, which would shorten routes); a door with no `plan` or `sides`; a door whose side
    is an unknown space or a room not read; a point of the clear floor with no route to any exit even with no
    clearance, or a cluster or pocket with no routed clear edge round it (decision 3: shown, never a number); obstructions
    or rooms read from a link; a corridor not made of straight legs (dead end only); and any reading that could
    shorten a route; a room that reaches an exit only through an end-only room (decision 1a; a closet, storeroom or
    toilet opening only into the room it serves goes through it, the reading said beside the figure, which never
    passes until it is confirmed); an `exit_kind` with
    no `exit_id`; a door under 24 in clear; any key of the additions left out. Readings that only lengthen one
    (decisions 1, 1a, 3, 5, 6) don't hold a pass: a pass under them is a
    pass under the shorter reading too.
11. **Every measure the branch's rules read** (its `parts.yaml`), and how:

| Measure | How |
|---|---|
| `egress_travel_distance`, `common_path_of_travel` | decisions 1 to 5, the greatest over the story |
| `egress_travel_from_room_door` | from each **exit access door** of a room (a door from which a permitted route reaches an exit without coming back into the room: the doors `space_exit_count` counts; never one into a closet or toilet) to the nearest exit, the greatest |
| `egress_travel_in_sleeping_room` | from each point of a `sleeping` room to the nearest of that room's exit access doors (as above, never a closet or toilet door); a sleeping room with none needs review; 0 with no sleeping room on the story |
| `story_exit_count`, `space_exit_count` | distinct `exit_id`s on the story; a space's doors and passages from which a permitted route reaches an exit without coming back into it, each counted once |
| `space_common_path` | decision 5 over the space's own points |
| `exit_remoteness_ratio` | decision 7 |
| `story_building_area`, `story_accessory_area`, `story_day_care_net_area` | decision 8 |
| `corridor_width`, `corridor_dead_end_length`, `corridor_dead_end_least_width` | decision 6; the width is the least distance between the corridor's walls and obstructions; a door swinging into it isn't in the description, so a rule needing the width with doors open needs review |
| `story_occupant_load`, `space_occupant_load`, `corridor_occupant_load`, `corridor_fire_rating_hours`, `corridor_walls_smoke_partitions` | stated by the architect (a mark), as the branch defines them; the computed day-care load (decision 8) is shown beside a stated one |

## How we will know it is right

**Synthetic tests, answers worked by hand** (feet; walls 6 in thick, so a door's centre sits 0.25 ft outside the room;
doors 36 in clear, each jamb with its 12-in ring). Every figure needing tangents and arcs (tests 1, 2, 4 and 6, the table and the jamb) was
worked two ways for this note: by the tangent-and-arc formulas, and by a throwaway brute-force shortest path over
fine 512-sided polygons of the rings (neither kept, neither the route code); they agree to 1/1000 ft. Test 1's corner
cluster was checked by a coarser bracket instead (64-sided rings inside and outside each circle, holding the formula's
figure), as test 1 says. The code's tests hold
these hand figures as written in the test file, never taken from the code under test, which is the third way.

1. **An L-shaped corridor:** legs 0 to 40 by 0 to 6, and 34 to 40 by 6 to 30; exit door centre at (-0.25, 3). The
   farthest point is the corner (40, 30). Its route curves round the inside corner (34, 6) at 12 in: tangent
   24.718 + arc 1.308 (74.9 degrees) + tangent 34.367 = **60.393 ft (60'-4 11/16")**; with no clearance it would be
   59.120 (one corner adds 1.27 ft). Pinned: the measure, the point, and that the clearance figure exceeds the other.
2. **A room with a column:** room 0 to 30 by 0 to 10, a 4-ft column 13 to 17 by 3 to 7, exit door centre (-0.25, 5).
   The farthest point is **not a corner**: it is the middle of the far wall, (30, 5), where the ways over and under
   the column are equal: **30.931 ft (30'-11 3/16")**, against 30.704 from the corners. Pinned: a sampler that only
   took corners would report 30.704 and fail this test.
3. **Dead ends at the limit:** a corridor 8 ft wide, 60 ft long, an exit at each end, and a branch 8 ft wide with its
   end wall 16 ft beyond the corridor's wall: dead end 16 + 4 = **20'-0" exactly, complies** with 1018.4; 1/16 in
   longer fails (2.5 x 8 = 20 is not "less than"). Corridor and branch 10 ft wide, dead end 25'-0" exactly: fails
   (exception 3 needs less than 25); 24'-11 15/16" complies by exception 3.
4. Also: an open room with two doors to two exits, seen directly (common path 0: the two lines part at the start);
   a room 0 to 20 by 0 to 15 whose one 36-in door, centred at (10, 15.25), opens on a corridor with an exit each way:
   from (0, 0) the route to the door centre is a straight 18.236 ft (it passes the jamb's ring at 1.12 ft), and the
   two routes part there, turning opposite ways, so the common path is **18.236 ft**, not the figure to the
   corridor's centre line; two exits in a rectangle (remoteness by nearest edges, diagonal corner to
   corner); each needs-review case of decision 10 and each key left out, one test each, failing on revert.
5. **A storeroom shortcut:** two rooms side by side, each with an exit, the far room's only short way to the near
   exit through a room marked `accessory_storage`: the travel distance is the long way round; with no other way,
   needs review. Fails if routes may cross the storeroom.
6. **Common path in an L-shaped room:** legs 0 to 30 by 0 to 10 and 20 to 30 by 10 to 40, exit doors centred at
   (22, 40.25) and (28, 40.25), each its own exit. From (0, 0) both routes go round the inside corner (20, 10):
   tangent 22.338 + arc together 0.925 (53.0 degrees, until the route to (28, 40.25) leaves) = **23.263 ft
   common**, not 0. Fails on a door-graph method. The room's `common_path_of_travel` is a number (decision 3's
   bound, with decision 5's margins), never needs review.
   **A table in the way:** a room 0 to 20 by 0 to 20, a table 6 by 3 ft (7 to 13 by 8.5 to 11.5) in its middle, a
   start at (10, 0) and the exit door centred at (10, 20.25). The straight line, 20.25 ft, crosses the table; the
   route goes round one side, touching the rings at two of its corners and running along the side 12 in off it:
   8.958 + arc 0.450 (25.8 degrees) + 3 + arc 0.439 (25.1 degrees) + 9.196 = **22.043 ft**. Fails if a line may
   cross an obstruction. **Near a jamb:** test 4's room from (0, 13.5): the straight line to the door centre
   (10.152 ft) passes within 12 in of the jamb at (8.5, 15), so the route curves round its ring: **10.543 ft**.
   **The points inside a ring: test 1's story figure.** No route is defined from inside a ring (decision 2), so
   test 1's corridor is measured as decision 3 says. Its clusters: the inside corner (34, 6), a lone ring whose
   floor is all in sight of it (margin 12 in), and the exit door's two jamb rings. The corner's clear edge runs from
   (34, 7), on the wall x = 34, clockwise round the corner to (33, 6); its greatest route is at (34, 7): round the
   ring 176.661 degrees, 3.0833 ft, to the tangent toward the door centre, then 34.3666 = **37.450 ft**, so the
   corner's cluster bound is 37.450 + 1.5 in + 12 in = **38.575 ft**. Worked two ways: the arc-and-tangent
   formula (37.4499), and the brute force from (34, 7) over 64-sided rings: inside 37.4487, outside 37.4524, a bracket 0.004 ft wide that holds 37.4499. The
   clear floor's greatest is test 1's 60.393 at (40, 30), so the story's figure is the clear floor's bound, between
   60.393 and 60.643 ft; the points behind the corner (once 35.088 ft from (34.5, 6.5) under the first definition
   from inside a ring, then 35.328 under the second, and 34.381 from the corner (34, 6) itself) are covered by
   38.575 and never govern it. Fails if a point inside a ring is given a route of its own, or if the corner's margin
   is left out of its bound.
   **Two exits and a column:** test 2's room and column, exit A the west door centred at (-0.25, 5), exit B a 36-in
   door in the north wall centred at (2, 10.25), its jambs at x 0.5 and 3.5 (each with its ring). At (30, 5) the two ways round the column to A are equally short (the
   room is symmetric about y = 5); taking the one over the top (the tie toward more shared, decision 5), both
   routes reach the ring at (17, 7) by the same tangent (arriving at 76.89 degrees), 13.115 ft, and go round it
   together until B's leaves at 85.79 degrees on the cross tangent to the ring of B's jamb at (3.5, 10) (A's goes on
   to 90): 13.115 + 0.155 = **13.270 ft common at (30, 5)**. Just below y = 5 the route to A goes under and they part
   at the start (0); just above, a little less than 13.270. Fails if the tie at (30, 5) is broken toward the way
   under (0 there). **(30, 5) is not the story's greatest** (corrected 2026-11-21; this said the figure was at most
   13.520 ft): along the south wall both shortest routes go under the column, by one tangent to the ring at
   (13, 3) and round it until A's leaves for its door centre, so the common path there is that tangent plus 0.104 ft
   of arc: 16.547 at (29.2, 0), 16.746 at (29.4, 0), rising until B's shortest way flips to over the column, at
   x 29.422 to 29.426 (the 64-sided brute force's bracket; the formula's tangent-and-arc figure agrees with the
   code's to 1e-6 ft), where it is **16.769 ft** (16.767 to 16.772), and 0 just past (B's route then parts at the
   start). So Gordium's common path at a point jumps where a shortest route flips sides. The story's figure is
   still a proved bound on the law's greatest (the law's figure changes no faster than you walk, decision 5), but
   not on Gordium's own pointwise figure near such a jump: the build gives 16.755 here, between 13.270 and
   16.772 + 4.5 in = 17.147, which the test checks.
7. **One stair, two doors:** a story whose only exit is one stair enclosure entered by two doors 80 ft apart, both
   `exit_enclosure` with one `exit_id`: `story_exit_count` 1, remoteness needs review, common path equals travel
   distance. Fails if doors are taken as exits.
8. **A classroom door in a dead end:** a branch 8 ft wide, its end wall 26 ft beyond an 8-ft corridor with an exit
   at each end (dead end 26 + 4 = 30 ft), a classroom door 5 ft from the end, the classroom with its own exterior exit: the dead end is 30 ft, not
   5; the readings are 30 ft (fails) and 5 ft (complies), so needs review. Fails if the door ends the dead end
   (5 ft, complies).
9. **Storage on the line:** a storage room under 10 percent of the story's inside area when measured inside its
   own walls, over it when measured to their outer faces: needs review, not complies. It needs review unless all
   four pairs of readings fail; it fails only when the storage is over 10 percent even inside its walls and of the
   story's outer area.
10. **A jamb:** a route turning 90 degrees just past a 36-in door keeps 12 in off the jamb (longer than with no
    ring there); a 22-in door: needs review.
11. **A dead end that branches:** a corridor 8 ft wide with an exit at each end; a stem 8 ft wide reaching 10 ft
    past its wall; at the stem's end a leg 8 ft wide running 15 ft each side of the stem's centre line, both ends
    closed. From a closed end: 15 + (4 + 10 + 4) = **33 ft, fails** 1018.4 (2.5 x 8 = 20). Fails if the dead end
    stops at the stem's crossing (15 ft).
12. **A storage alcove on a passage:** a corridor with a storage alcove (`accessory_storage`) joined to it by a
    separation line, the straight line from a far point to the exit cutting across the alcove: the travel distance
    is the route that stays out of it. Fails if the zone includes the alcove for routes not starting there.
13. **A sleeping room's closet:** a sleeping room 60 by 20 ft, its corridor door at one end, a closet door at the
    far end: `egress_travel_in_sleeping_room` about 60 ft, failing 16.2.6.2(3)'s 50 ft. Fails if any door counts.
14. **A lobby:** two exits reached from a wing only through a room marked `lobby` with no `pass_through`: the travel
    distance takes the way round, or needs review if there is none. Fails if a lobby is crossable by its use. And a
    storage room marked `pass_through: true`: refused on read, its story needs review.
15. **The area readings:** a checker test on the 10 percent rule with both areas given as readings: all four pairs
    are worked, the outer-accessory over inside-story pair among them; complies only when all four pass.
16. **A locked corridor:** a corridor 8 ft wide from a closed end; 15 ft along it, a single side corridor with
    `lockable: true` leads to exit B (the other side a plain wall); the main corridor goes on to a crossing whose
    centre line is 30 ft from the closed end and whose two ways reach exits A and C. With the fix: **30 ft, fails**
    1018.4 (over 20; 2.5 x 8 = 20). With the locked way counted, the dead end would stop at 15 ft (two directions,
    to B and onward to A and C) and comply: so it fails on revert.
17. **A kitchen and its pantry:** a start in a kitchen joined by a separation line to a pantry (`accessory_storage`)
    whose door is near an exit: the route leaves by the kitchen's own door (needs review if it has none). Fails if
    the route crosses the pantry. And an H-plan corridor with dead ends of 30 by 14 ft and 22 by 8 ft: two pairs,
    the first complying by exception 3 (30 < 2.5 x 14 = 35), the second failing (22 > 20, and 22 is not less than
    20); until `dead_end` exists, the pair 30 ft and 8 ft (fails). Fails if the 14-ft width is paired with 22 ft.
18. **A niche too narrow:** a room 0 to 20 by 0 to 10, its exit door centred at (-0.25, 5), a niche 20 in wide and
    2 ft deep in the north wall (x 10 - 0.833 to 10 + 0.833, y 10 to 12). Its mouth's corners are 20 in apart, so
    their rings overlap across the mouth; (10, 11.5), at the back, is sqrt(0.833^2 + 1.5^2) = 1.716 ft from each corner, clear of both, and
    shut in: no route of its own, a pocket (decided 2026-11-21: before, the story needed review). Its bound: the
    mouth cluster's greatest routed edge route plus 1.5 in plus the walk out, whose greatest is from a back corner
    (10 -+ 0.833, 12) straight to the rings' cusp (10, 9.447), sqrt(0.8333^2 + 2.5528^2) = 2.6854 ft; sampled and
    plus 3 in, a margin of 2.935 to 3.060 ft. The story's figure is the far corners', 20.858 ft plus at most 3 in.
    Fails if the pocket's bound is left out; a pocket with no routed edge round it still needs review.
19. **A coarse triangle not dropped on 3 in:** a corridor 0 to 40 by 0 to 6, exit doors centred at (-0.25, 3) and
    (40.25, 3). The triangle (19, 0), (21, 0), (19, 1.5) has corner values 19.482, 19.482 and 19.308, so corners plus
    3 in is 19.732, which the sample (20.5, 3) at 19.75 beats; yet (20, 0) inside it has sqrt(20.25^2 + 3^2) =
    **20.471 ft**, the story's true greatest (on the wall, where the two exits' routes are equal). It is a right
    triangle with a 2.5-ft hypotenuse, so its own h is exactly **1.25 ft** (at (20, 0.75), the hypotenuse's middle):
    19.482 + 1.25 = 20.732 beats 19.75, so it is kept and cut. Pinned two ways, so it fails whatever mesh the build
    uses: the drop test itself, given this triangle and a best so far of 19.75, must say "kept" (it fails if h is
    replaced by 3 in: 19.732 < 19.75, dropped); and the story's figure is at least 20.471.
20. **Rooms that open only into the room they serve** (decision 1a, amended 2026-11-21). A corridor 0 to 40 by 0 to
    6 with its exit in the south wall, centred at (15, -0.25); north of it a kitchen 10 to 20 by 6.5 to 16.5
    (`lockable: false`), its door to the corridor centred at (15, 6.25); a closet 10 to 14 by 17 to 20 whose only
    door, centred at (12, 16.75), opens into the kitchen. From the closet's (12, 18): straight to its door 1.25,
    straight across the kitchen to the kitchen's door, sqrt(3^2 + 10.5^2) = 10.920 (1.37 ft off the nearest jamb,
    clear of every ring), then straight across the corridor to the exit, 6.5: **18.670 ft**. Fails on revert (no
    route). And: the kitchen `lockable: true` (or
    not given): no route, the reason naming the kitchen; a classroom (`day_care`, not crossable) between the closet
    and the kitchen: still no route (the closet is part of the classroom, but the classroom's only way out crosses the
    kitchen, and a classroom is never taken as part of a kitchen); a storeroom whose only door opens into another
    storeroom whose own door opens on the corridor: a route, through both (and a closet off the inner one: a route
    through all three; with the inner storeroom `lockable: true`, it keeps its own route and the closet has none); the
    common path of a blocked room stops for the same reason as its travel; a closet with a
    second door, into the corridor: its own route, never through the kitchen; a room `other` (the electrical room)
    off the kitchen: no route. The door from the closet is its exit access door, and the story's figure carries the
    reading's `confirm`.

**The eval: the architect's own sheet.** `test_data/answer_keys/portland_me_19_libby_st/hand_check.yaml` (on the
branch) records sheet LS1.0 of the Children's Odyssey day care (Portland, Oct 2016). Gordium built a Revit model from
the sheet's data; the reader already read it once (it found a 0.4 sq ft sliver between overlapping walls, now an
unknown space, commit `67dd698f`). Measured on that model:

| Sheet figure | Limit | Agreement asked |
|---|---|---|
| Travel distance 130'-8" | 200' | Gordium's no-clearance figure from the sheet's start to the sheet's exit no longer than the sheet's line as drawn plus 2 percent of it or 2 ft, whichever is larger, and no shorter than the straight line between that line's ends less the same, and the verdicts the same (changed 2026-11-21, below; the old test, within 2 percent or 2 ft of the stated figure, still reported) |
| Common path 48'-6" | 75' | the same test (no longer than the line as drawn plus 2 percent or 2 ft, no shorter than the straight line between its ends less the same, verdicts the same; the old one still reported) |
| Dead end 21'-6", least width 10' | 2.5 x 10' = 25' | length within 1 ft, width within 1 in |
| Remoteness 183'-10" | 70'-1" (diagonal 210'-2 1/2" / 3) | within 1 ft of Gordium's nearest-edge figure or of its door-centre figure (both reported: the sheet may measure either; they differ by up to half the two doors' widths); diagonal within 6 in |
| Storage 1,428 sf | 1,650 sf (10 percent of the story) | the inside-walls figures within 1 percent; story area against 16,539 sf (the sheet's 16,509 is a recorded error); the rule complies under all four readings (decision 8), or the readings it fails under are a finding |

And every verdict the same as the sheet's (all comply). **Why these tolerances:** the sheet's lengths are hand-drawn
paths on a 1/8 in = 1 ft drawing, where 1/32 in of pencil is 3 in, and the start point and the bends are chosen by
eye; the model is a trace of that sheet, each wall a few inches either way. Route lengths gather those errors over
many bends; straight lines and areas gather few. **The clearance:** a hand path usually hugs corners, so the route
lengths are compared with Gordium's no-clearance figure; the 12-in figure (the one the rules read) is reported beside
it, with its corners, to show the difference is the clearance and nothing else. **Why the travel and common-path
test changed (2026-11-21, after the first run, not to make it pass).** The first run measured both well short of
the sheet (116.03 ft against 130'-8", 41.07 against 48'-6", no clearance), and the reason is a difference of
method, not of model: the sheet's lines are drawn orthogonally, along the grid, every turn a right angle
(`sheet_line_in_model` in the eval file), while the books measure "along the natural and unobstructed path of egress
travel" (IBC 2009 1016.1, OCR copy only) and "Along the centerline of the natural path of travel ... Curving around
any corners or obstructions, with a 12 in. (305 mm) clearance therefrom" (NFPA 101 2012 7.6.1(1) and (2)). An
orthogonal line between the same two points is never shorter than the natural path (no path between two points is
shorter than the shortest one, and up to 41 percent longer, decision 1's *rejected* rectilinear), so a two-sided
tolerance would mark the code wrong for measuring what the books say. The test is now one-sided against the sheet's
own line: Gordium's figure, from the sheet's start to the sheet's exit, must be no longer than that line as drawn
plus the tolerance (a longer figure is a finding: a farther point or a longer path than the architect found), and
each of its rules' verdicts must be the sheet's. One-sided is not unbounded below (added 2026-11-21, review round 1): a
route measured too short is the false-pass direction, so the figure must also be no shorter than the straight line
between the sheet line's own first and last points less the tolerance, the floor no path between those points can go
under (`no_shorter_than_straight`). The old two-sided comparison stays in the eval file beside it
(`agreement.before_2026_11_21`), and a miss under it is still logged, so nothing it found is hidden. **A difference outside tolerance is
investigated, never tuned away:** Gordium draws each route back on the model, and if it found a farther point or a
longer dead end than the sheet shows, that is recorded as a finding on the sheet (as its story area is), not a fix
to the code. The model and its description stay outside the repo, as the sheet does (open question 5); the eval
runs where they are and says it skipped where they aren't.

## Where the code would go

- `packages/model_measurement/model_measurement/routes/`: `floor.py` (each story's zones from rooms, holes,
  obstructions, doors, passages, with the decision 10 checks), `paths.py` (decision 2's routes, shortest paths
  from the exits), `remote.py` (corners and the 3-in triangles, the bound), `common_path.py`, `dead_ends.py`
  (corridor legs, centre lines), `straight.py` (remoteness, diagonal), `areas.py`, and `__init__.py` giving the
  `story`, `space` and `corridor` parts with their measures, `not_measured` reasons and `more` (the paths drawn).
  Same rules as `interior/`: a `Stop` with a reason, never a crash, never a default. Geometry by shapely, already
  used; no new library.
- The format: the additions above in [the format](../interior/interior_description_format.md), checked on read.
- The Revit reader: the marks `Gordium: Use` and `Gordium: Exit`, and the door, level, passage, hole, obstruction and
  outline fields, with fake-record tests and a recorded trial ([Revit interior design](../revit/revit_interior_reading_design.md) gains a section).

Order: format and `floor.py` with the left-out-key tests; paths and the most remote point; common path; dead ends;
remoteness and areas; the reader; then the eval on the Children's Odyssey model. Each its own PR.

## Open questions for Ben (and, through him, the architects)

1. **Which centre line?** NFPA 7.6.1(1) "along the centerline of the natural path": Gordium reads it as the walked
   path, 12 in off corners. Another reading is the corridor's own centre line, longer at every turn. The eval shows
   which the sheet used; the NFPA Handbook's commentary would settle it (not in the repo).
2. **Where a dead end ends:** at the crossing corridor's centre line (Gordium's, the longer) or its near edge? They differ by
   half the crossing corridor's width; the sheet's 21'-6" may be either.
3. **Areas:** 502.1 says "within surrounding exterior walls": the inside or the outer faces? And a storage room's
   area: inside its walls, or to their outer faces? Until answered, the less favourable governs (decision 8).
4. **Tiny unknown spaces:** a sliver between overlapping walls holds no one, but Gordium can't tell a sliver from a
   room nobody placed. Proposed: needs review, named, until the model is fixed; or a smallest area that counts
   (needs a source).
5. **The Children's Odyssey model:** may its interior description go in the repo as a test file, or stay outside it
   like the sheet?
6. **Movable furniture:** Gordium counts every drawn obstruction (only lengthens routes). Should a "movable" mark
   let routes pass through tables and chairs, as many hand paths do?
7. **A door into a room with another way out, in a dead end:** does it end the dead end (IBC 1014.2 item 1 and NFPA
   7.5.1.6 allow exit access through an accessory room)? Gordium says no, and needs review where it decides.
8. **Which rooms may be crossed:** is `pass_through`, stated in the model, the right test of 1014.2 item 1
   ("accessory to one or the other ... a discernible path")? Day-care rooms opening into each other are common.
9. **A point within 12 in of a corner:** NFPA 7.6.1 measures "(1) ... starting from the most remote point subject to
   occupancy (2) Curving around any corners or obstructions, with a 12 in. (305 mm) clearance therefrom". It doesn't
   say how a route starts from a point inside that clearance. Gordium defines no route from there (decision 2): the
   story's figure covers such points by each cluster's bound, the greatest route on its clear edge plus the walk out
   to that edge with no clearance (decision 3), which is never less than any route from inside that keeps the
   clearance once out. Is a figure that covers those points, rather than one for each, the right reading? The
   Handbook's commentary (not in the repo) may say how a start inside the clearance is measured.
10. **An opening narrower than 24 in:** the same words, read literally, leave no route through a gap that can't be
    passed 12 in from both sides (a niche, a gap between casework and a column), so a point beyond one has no route
    of its own. Gordium (decided 2026-11-21) bounds such a pocket's points through the ring cluster that shuts it in:
    the walk out with no clearance, then the cluster's greatest routed edge route (decision 3, test 18), an upper
    bound, so no false pass. Is that the intent, or does the clearance give way where the opening is narrower (as it
    does at a door's centre)? Either answer gives no more than Gordium's figure.
11. **A closet, storeroom or toilet that opens only into the room it serves** (2026-11-21, decision 1a): IBC 1014.2
    item 4 and NFPA 7.5.2.1 forbid egress through kitchens, storerooms and closets, with no exception for a room's own
    closet; read literally, a pantry off a kitchen, or an inner storeroom off a storeroom, has no legal way out.
    Gordium's reading (strong common practice, sources in decision 1a): such a room is part of the room it serves, so
    its route leaves through that room, but never through a room that can be locked or across any other end-only
    room. Is that how the architects and the City read it? And, on this model: the eval marks the kitchen and the
    storerooms `lockable: true` ("kept locked"), so the closet off the kitchen and the inner storeroom still have no
    route. NFPA 16.2.2.2.4 requires every latch to a day care's closets, storage and kitchens to open from inside: if
    those rooms lock only against entry, they can't be "locked to prevent egress" (1014.2 item 2) and the mark would
    be `lockable: false`; which is the architect's to say.
