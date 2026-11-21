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
2. **What a route is, exactly.** The route from a point p to an exit is **the shortest curve** that (a) lies in the
   zone's free floor: the crossable rooms' outlines (decision 1a) minus walls, holes and obstructions, joined
   through door openings, passing each door at its centre; (b) stays at least 12 in from every corner: each wall
   corner that sticks into the floor, each corner of an obstruction, each door jamb (a ring: a true circle of 12-in
   radius). For a point clear of every ring (at least 12 in from every corner; on a ring's edge counts as clear),
   that is its route, and its length is written D(p). (c) **A point inside a ring** (or several) has no clear curve
   out, so its route first goes straight to the rings' edge, then on clear: its length is
   d(p) = the least, over every point q on the edge of the rings that hold p, clear of every other ring, that p
   reaches by a straight line on the floor running inside those rings, of |pq| + D(q). The same at a door centre
   inside a ring: the route reaches that ring's edge clear, then runs straight to the centre (and leaves it the same
   way). So d is continuous at a ring's edge (there q is p itself), and never shorter than walking out of the ring
   and then round (behind test 1's corner: 35.328 ft). This is Gordium's reading of NFPA 7.6.1(2), not the law's
   words (open question 9). *Rejected:* letting the curve run anywhere within a ring holding p until it left (the
   earlier (c)): the length then jumps at the ring's edge (behind test 1's corner, 35.380 ft just inside the ring and
   36.665 ft just outside: 15.4 in over a hair's step), so no sampling bound (decision 3) holds across it, and a
   point just inside got a shorter route than its neighbour just outside.
   **An opening narrower than 24 in.** Two corners less than 24 in apart have overlapping rings, and a corner less
   than 12 in from a wall has its ring on the wall: no clear curve passes between them. Where every way out of a
   point is closed so, the point has no route: the story needs review (decision 10) with the reason "an opening too
   narrow for NFPA 7.6.1's 12-in clearance from both sides" (test 18: the back of a niche 20 in wide and 2 ft deep).
   A door is the one opening a route passes at its centre (decision 1). Gordium's reading too (open question 10).
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
   So Gordium samples the floor and bounds what lies between samples, in three parts: **F**, the floor clear of every
   ring; **E**, the rings' edges (the arcs of each ring's circle on the floor and clear of every other ring, found
   exactly from the circles); and **B**, the band inside the rings.
   - **F and E: a proved bound.** In F the route's length is D (decision 2), and D can't grow faster than you walk
     along any curve in F (from x, walk to y and take y's route: that is a route for x). Every arc of E is sampled
     at most 3 in apart along it, ends included, so every point of E is within 1.5 in, walking along E, of a sample.
     The floor is cut into triangles, every corner of the floor among their corners, and every triangle corner in F
     is a sample. A triangle no ring reaches lies in F, and each of its points is within h (its farthest from all
     three corners) of one, in a straight line inside it. A triangle a ring reaches: from a point x of it in F, the
     straight line toward the nearest point of that ring in the triangle stays in the triangle, and the first ring
     edge it meets, y, is in E, at most the triangle's longest side away. So, with triangles no longer than 3 in a
     side: **every point of F is within the greatest sample plus 3 in** (a triangle in F; h is under 3 in), **or plus
     4.5 in** (3 in to E, 1.5 in along it), the cautious figure being the triangle's own. (Only where it matters:
     triangles start 2 ft across, and only one whose greatest corner value plus its own margin could beat the best
     found so far is cut smaller; the rest are dropped, which the same bound makes safe.) And a point of F with no
     route is never missed: its straight line to a triangle corner, or to E and along it, reaches a sample that has
     none too, so the story needs review.
   - **B: a margin, and one thing not proved.** For p in B, d(p) is |pq| + D(q) for some q on the edge of the rings
     holding p, and every such q is within 24 in of p (two ring radii). So d(p) is at most 24 in plus the greatest D on
     the edges of that group of overlapping rings, plus 1.5 in for E's sampling: **25.5 in over that group's greatest
     edge sample**, proved for every p that has an exit at all. Whether every point of B has one (a straight line to a
     clear q) isn't proved by sampling: B's points are sampled 3 in apart too and a sample with none needs review,
     but a pocket of B smaller than that could be missed (open question 11).
   The rules get the greatest of these bounds; the panel shows the greatest sample, each part's bound and which part
   gave the figure. (In the note's layouts the far point is a room corner in F, and B's bound is far below it.)
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
   as decision 3's: every corner and the 3-in samples, the triangles cut only where they could matter, and the rules
   get the greatest found plus 3 in, which is never less than the law's greatest. No cells and no cases: it is
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
   becomes a part kind of its own there (`dead_end`, its two measures, one row per dead end); until that change on
   the branch, the corridor gives the cautious pair, the longest length with the least width of any of its dead
   ends, under each reading of open question 7 alike. A corridor that isn't made of straight legs
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
    is an unknown space or a room not read; a point with no route to any exit (shown, never a number; one shut in by an opening narrower than 24 in says
    so, decision 2); obstructions
    or rooms read from a link; a corridor not made of straight legs (dead end only); and any reading that could
    shorten a route; a room that reaches an exit only through an end-only room (decision 1a); an `exit_kind` with
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
doors 36 in clear, each jamb with its 12-in ring). Every figure needing tangents and arcs (tests 1, 2, 4 and 6, the table, the jamb, the behind-corner and the corner starts included) was
worked two ways for this note: by the tangent-and-arc formulas, and by a throwaway brute-force shortest path over
fine 512-sided polygons of the rings (neither kept, neither the route code); they agree to 1/1000 ft. The code's tests hold
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
   common**, not 0. Fails on a door-graph method. The room's `common_path_of_travel` is a number (the greatest
   sample plus 3 in), never needs review.
   **A table in the way:** a room 0 to 20 by 0 to 20, a table 6 by 3 ft (7 to 13 by 8.5 to 11.5) in its middle, a
   start at (10, 0) and the exit door centred at (10, 20.25). The straight line, 20.25 ft, crosses the table; the
   route goes round one side, touching the rings at two of its corners and running along the side 12 in off it:
   8.958 + arc 0.450 (25.8 degrees) + 3 + arc 0.439 (25.1 degrees) + 9.196 = **22.043 ft**. Fails if a line may
   cross an obstruction. **Near a jamb:** test 4's room from (0, 13.5): the straight line to the door centre
   (10.152 ft) passes within 12 in of the jamb at (8.5, 15), so the route curves round its ring: **10.543 ft**.
   **Behind a corner:** test 1's corridor from (34.5, 6.5), inside the ring of the inside corner (34, 6) and behind
   it (decision 2(c)): straight out to the ring's edge, then on clear. The best edge point is where the line from
   (34.5, 6.5) past the corner meets the ring, (34 - 0.7071, 6 - 0.7071): 0.7071 + 1 = 1.7071 to it, then straight
   to the door centre, sqrt(33.5429^2 + 2.2929^2) = 33.6211 (it sees the door clear of the ring): **35.328 ft**.
   Worked two ways: the least of |pq| + D(q) over the ring's edge in steps of 0.001 degree, and the brute force over
   64-sided rings (35.3283 inside, 35.3286 outside). The earlier (c) gave 35.088 (within the ring to the corner and
   straight on), shorter than leaving the ring at all.
   **A start on a corner:** test 1's corridor, from the inside corner (34, 6) itself (inside
   its own ring): out 1 ft toward the door centre, to the ring's edge on the line to it, then straight on: 1 +
   33.381 = **34.381 ft** (the same as straight, as nothing is in the way), never "no route".
   **Two exits and a column:** test 2's room and column, exit A the west door centred at (-0.25, 5), exit B a 36-in
   door in the north wall centred at (2, 10.25), its jambs at x 0.5 and 3.5 (each with its ring). At (30, 5) the two ways round the column to A are equally short (the
   room is symmetric about y = 5); taking the one over the top (the tie toward more shared, decision 5), both
   routes reach the ring at (17, 7) by the same tangent (arriving at 76.89 degrees), 13.115 ft, and go round it
   together until B's leaves at 85.79 degrees on the cross tangent to the ring of B's jamb at (3.5, 10) (A's goes on
   to 90): 13.115 + 0.155 = **13.270 ft common at (30, 5)**. Just below y = 5 the route to A goes under and they part
   at the start (0); just above, a little less than 13.270. The story's figure is 13.270 plus 3 in at most, so
   between 13.270 and **13.520 ft**. Fails if the tie at (30, 5) is broken toward the
   way under (0 there).
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
    their rings overlap across the mouth; (10, 11.5), at the back, is 1.202 ft from each corner, clear of both, and
    shut in: **no route**, needs review with the reason "an opening too narrow for NFPA 7.6.1's 12-in clearance from
    both sides". Fails if the rings are left out (it would get a number) or if a point near the back may cross the
    mouth inside a ring it isn't in.

**The eval: the architect's own sheet.** `test_data/answer_keys/portland_me_19_libby_st/hand_check.yaml` (on the
branch) records sheet LS1.0 of the Children's Odyssey day care (Portland, Oct 2016). Gordium built a Revit model from
the sheet's data; the reader already read it once (it found a 0.4 sq ft sliver between overlapping walls, now an
unknown space, commit `67dd698f`). Measured on that model:

| Sheet figure | Limit | Agreement asked |
|---|---|---|
| Travel distance 130'-8" | 200' | within 2 percent or 2 ft, whichever is larger |
| Common path 48'-6" | 75' | within 2 percent or 2 ft |
| Dead end 21'-6", least width 10' | 2.5 x 10' = 25' | length within 1 ft, width within 1 in |
| Remoteness 183'-10" | 70'-1" (diagonal 210'-2 1/2" / 3) | within 1 ft of Gordium's nearest-edge figure or of its door-centre figure (both reported: the sheet may measure either; they differ by up to half the two doors' widths); diagonal within 6 in |
| Storage 1,428 sf | 1,650 sf (10 percent of the story) | the inside-walls figures within 1 percent; story area against 16,539 sf (the sheet's 16,509 is a recorded error); the rule complies under all four readings (decision 8), or the readings it fails under are a finding |

And every verdict the same as the sheet's (all comply). **Why these tolerances:** the sheet's lengths are hand-drawn
paths on a 1/8 in = 1 ft drawing, where 1/32 in of pencil is 3 in, and the start point and the bends are chosen by
eye; the model is a trace of that sheet, each wall a few inches either way. Route lengths gather those errors over
many bends; straight lines and areas gather few. **The clearance:** a hand path usually hugs corners, so the route
lengths are compared with Gordium's no-clearance figure; the 12-in figure (the one the rules read) is reported beside
it, with its corners, to show the difference is the clearance and nothing else. **A difference outside tolerance is
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
   say how a route starts from a point inside that clearance. Gordium's reading (decision 2(c)): straight out to
   12 in, then on with the clearance. It is never shorter than any route that keeps the clearance once out; the
   Handbook's commentary (not in the repo) may say otherwise.
10. **An opening narrower than 24 in:** the same words, read literally, leave no route through a gap that can't be
    passed 12 in from both sides (a niche, a gap between casework and a column), so a point beyond one has no route
    and the story needs review (decision 2, test 18). Is that the intent, or does the clearance give way where the
    opening is narrower (as it does at a door's centre)? Until answered, needs review, naming the opening.
11. **Pockets inside the clearance band:** decision 3 proves its bound clear of the rings and on their edges; inside
    them it proves the 25.5-in margin only for points that have a straight way out to a clear edge. A pocket smaller
    than the 3-in samples with no such way out isn't ruled out. Accept the sampling there, or ask for an exact check
    (a later build: the pockets of the band, worked from the circles)?
