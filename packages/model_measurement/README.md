# model_measurement

Measures a Rhino model the way the city defines each measurement: lot area, width and depth, the front, side
and rear yards, building area and height. Plain code written by engineers, no AI (principle 6). Same model,
same facts, same numbers, every time.

```
python -m model_measurement <model.3dm> <model_facts.yaml>   # prints each measurement, writes <model>_measured.yaml
python -m model_measurement --check                          # CI: every committed measured model is current
```

The measured file is a project file: `python -m project_report <model>_measured.yaml` writes the architects'
format report from it.

## What goes in

- **The model.** The lot is the closed outline on the `Site` layer; buildings are the solids or closed meshes
  on the `Building` layer (the layers the architects already use). Any units; everything is converted to feet.
- **Lot facts**: what a model can't show, stated by the architect. In Rhino they are asked once (prefilled)
  and saved in the file; on disk they sit next to the model as `<model>_facts.yaml`:

  | Fact | Why it's needed |
  |---|---|
  | `zone`, `jurisdiction`, `use` | pick the rules |
  | `street_line` | **every** lot line on a street, each by its two ends (on a corner lot: both streets and any curve between them); front, side and rear all follow from it |
  | `corner_lot` | yes or no: two streets meet at the lot (§325-19C). Stated, never guessed from the drawing (the city's definition has no angle in it). Without it, everything that depends on the street says "needs review". On a corner lot every yard facing a street is a front yard (§325-19C, the law), the rear yard is opposite the street the address is on (§325-8A(14)(d)), and the one side yard left is checked against Column 13 (Gordium's reading, City practice) |
  | `address_street_line` | on a corner lot: the lot line(s) on the street the lot's address is on (it decides which yard is the rear yard). Not given, each street is read as it, and the yards it changes need review |
  | `accessory_buildings` | the ids of the solids that are accessory buildings (a garage, a shed). A solid standing apart from the main building that isn't listed could be a freestanding deck (part of the building, §325-18A), so both are read. Listing them also picks the main building (the one left) |
  | `accessory_frame` | yes or no: the accessory buildings are frame. Frame ones keep §325-25C's distances by law; for others it is an open question (325-25C#1), read every way |
  | `eaves_confirmed` | a lot fact for one overhang (the panel will ask for it in a later release): [{overhang (its fingerprint, from the check), value: true, source, confirmed_by, date}]. Without it, a yard that meets its minimum only to the walls needs review; a later edit to the overhang asks again |
  | `grade_elevation` | the ground level heights are measured from (a flat site) |
  | `ground_is_flat` | yes or no. Sloped ground needs the ground levels around the walls (the grade plane), not measured yet: without a yes, height, building area and the yards say "needs review" |
  | `lot_surveyed` | yes or no: the lot outline is from a survey. A drawn lot (from a map) isn't: without a yes, the lot area, and so lot size and coverage, say "needs review" (the drawn area is listed as a reading) |
  | `lot_id`, `main_building` | only when there is more than one candidate |
  | `stories`, `sleeping_rooms`, `parking_spaces` | not drawn in a massing model; the rules that need them say "needs review" until they're entered |

## How each number is found

| Measure | How | The city's words (4_term_definitions/definitions.yaml) |
|---|---|---|
| Lot area | area inside the lot lines | |
| Lot width | length of the lot line(s) on the street | lot_width: "frontage measured on a public right-of-way" |
| Lot depth | average length of the two side lot lines | lot_depth: "the average of the two lengths" |
| Front yard | least distance from the street lot line to the main building | front_yard: "the least distance between the front lot line and the front of such main building" |
| Side yards | least distance from each side lot line to the building; the nearer is `side_yard_smaller` | side_yard: "from the nearest point of the side lot line to the nearest part of" |
| Rear yard | least distance from the rear lot line to the main building | rear_yard: "the least distance between the rear lot line and the rear of such main building" |
| Building area | every building on the lot seen from above, principal and accessory (garages count), porches, decks and cantilevered floors included (findings coverage_seen_from_above, garages_count); eaves: every reading of building_area's open question | building_area: "the total area … of the principal building and all accessory buildings" |
| Height | ground level to the highest level of a flat or mansard roof (its highest section is level, or within a drainage slope of level: under 1/2 inch per foot); a pitched roof midway between eave and ridge of its highest section (finding pitched_roof_midpoint), with the eave read every way height_of_building's open question lists: the underside of the lowest eave, the top of the wall plate, the drip edge | height_of_building: "to the highest level of a flat or mansard roof or to the average height of a pitched … roof" |
| Yards to the eaves (`front_yard_eaves`, …) | the same yards measured to the building seen from above, eaves included, for §325-18B (eaves may project up to 2 ft into a required yard) | yard_projections: "shall not project more than two feet into any required yard" |
| Accessory buildings | how many solids stand apart from the main building; their least distance from the street lot line(s), a side lot line and the rear lot line; whether §325-25C's distances apply (`accessory_distances_apply`: frame, by law; otherwise every reading of 325-25C#1) | side_yard: accessory_structures_follow_325_25 |

The yards are measured to the nearest part of the building with its eaves left out (the finding yards_to_nearest_part:
§325-3 YARD, §325-18A): cantilevered floors, porches, decks and steps count (a solid touching the main building is
part of it: steps by Gordium's reading steps_count). Every yard and lot coverage is measured to the full
outline: everything the building's solids cover, seen from above. Gordium never decides from the shape that
something is an eave (a gable volume, a mansard story or a knee wall can look just like one). `_eave_candidate`, the
one helper the height, the yards and coverage share, only suggests what might be eaves: what a pitched roof reaches
past the walls under it. Where there is such a candidate, each yard is also read to the walls (the `model#eave`
reading: eave / not_eave): if the full outline meets the requirement, that is the result; if only the walls do, the
item needs review and asks whether the part reaching that far past the walls is an eave (§325-18B lets eaves
reach up to 2 ft into a required yard; `R-1b.yard_projections` checks that). The answer is a lot fact,
`eaves_confirmed`: [{overhang, value: true, source, confirmed_by, date}], naming the candidate's fingerprint
(`eave_candidates` on the yard, height and coverage records, and in each item's detail). The panel will ask for it
in a later release; until then such an item stays needs review. The fingerprint is a sha256 over the ids of the
solids whose faces make the overhang, every vertex of those solids (to 0.01 ft) and the overhang's outline (to 0.01
ft): any edit to those solids (a deeper fascia, a knee wall, another solid swapped in) gives a new one, and the
question is asked again; the same model gives the same one. The height's eave
readings follow the same rule (unconfirmed, each is also read with the roof edge as the eave). Anything that sticks
out past the walls at the ground and is neither one of Gordium's floor blocks nor a candidate eave is also read to
the walls at the ground (`model#projection`: it may be a bay window or other projection).

## What research settled, and what is still open (`interpretations.py`)

The measuring follows the city's own files, never a copy in the code: an open question with `readings` by id (in
`definitions.yaml`, a rule or a section label) is measured under every reading it lists, each reading named
(`named: {"height_of_building#1": "wall_plate"}`), so the checker can say complies only if all pass, does not
comply only if all fail, and needs review otherwise, naming the readings it fails under. A finding of kind `law`
is applied as the law; kind `reading` is applied and carried in the measurement's `basis`, shown as "Gordium's
reading · confirm with …". An answer from the architects or the City (`answers`, with `reading: <id>`) outranks
both: only that reading is measured. The code finds a question by its entry and the ids of the readings it can
measure, so a renumbered question is still found; a question or finding the files no longer have stops the
measurement.

Side and rear lot lines follow from the street, every way the geometry allows (no angle decides it): walking out
from each end of the street lines, the lines run on as that side lot line for one or more lines, and the rear lot
line is what is left. The line at each end of the street touches the street, so it is a side line, never the rear;
a reading with no rear line isn't one. More than 6 lines that could be either: too many to list (needs review).

## Never a guess

Where the law can be read more than one way, **every reading is measured**. If they give the same number, that
is the value (and the readings are listed in the working); if not, there is **no value**, the readings are
listed, and the reason names the open question for the architects, so the checker says NEEDS REVIEW:

| Case | Readings | Open question |
|---|---|---|
| A lot line that is neither clearly side nor rear (a jog) | the line as a side line / as a rear line | lot_depth: "which lines count" |
| A curved street line | along the curve / straight across | lot_width |
| Something below the roof sticking out past the walls at the ground (an upper floor, a bay window) | to the building / to its walls at ground level | yard_projections (bay windows) |
| A solid standing apart from the main building, not listed in `accessory_buildings` | every yard to the main building (an accessory building, §325-25) / with it as a freestanding deck (§325-18A) | §325-25, §325-18A |
| A pitched roof | midway between eave and ridge, the eave at the underside of the lowest eave / the top of the wall plate / the drip edge (named readings) | height_of_building#1 |
| Eaves, for lot coverage | left out / the part beyond 2 ft counted / counted in full (named readings) | building_area#1 |
| A corner lot whose address street isn't given | each street read as the address street (the rear yard is opposite it) | §325-8A(14)(d) |
| A corner lot's lot width | each street's frontage | lot_width |
| A roof with a level part and sloped sides at its top | a mansard, to its highest level / a pitched or hip roof, to its average height | height_of_building: "flat or mansard" vs "pitched, gabled, hip" |
| Something above the main roof (a parapet, chimney, bulkhead, or a higher part of the building) | leaving it out (the roof read as usual) / to its top; whether it counts is the question (§325-3 leaves out bulkheads and chimneys) | height_of_building |
| More than one solid, for the height | the main building alone / with every other solid as part of it | §325-25 |

Things that stop a measurement. The measurement has no value and gives NEEDS REVIEW, with this reason, word
for word. Every reason is in one table, `model_measurement/stops.py`, and the code gives no other;
`tests/test_stop_list.py` checks each is listed here and builds a case that gives it, and `tests/conftest.py`
checks every reason any test makes has the shape of a table sentence. These checks are backstops, not proof:
a hand-written sentence shaped like one of the table's (say, starting "no" and ending "layer") would pass them.
Every reason the code gives today comes from the table:

- **The readings disagree:** "the readings give different values; …", then the open question from the table
  above (the value is left to the architects; every reading is shown).
- **The file:** "can't read <file>"; "the model's units (<units>) aren't supported" (feet, inches, millimetres,
  centimetres and metres are).
- **The lot outline:** "no Site layer"; "no lot outline"; "no closed lot outline on the Site layer"; "2 closed outlines on the Site layer: pick the
  lot"; "the lot picked isn't a closed outline on the Site layer: pick the lot again"; "a block on the Site layer
  can't be read yet (explode it)"; "the lot outline isn't one closed loop of lot lines"; "the lot outline crosses
  itself (…)". A lot outline not from a survey stops the lot area (and so coverage): "say whether the lot outline
  is from a survey"; "the lot outline isn't from a survey: the lot area needs one (an open question for the
  architects)".
- **The street side:** "the street side isn't given: pick the lot line on the street"; "a street line given
  doesn't match a lot line: pick the street side again"; "the street lot lines given aren't next to each other";
  "every lot line is on a street: which yards are front, side and rear is an open question for the architects".
- **Corner lots** (§325-19C): "say whether this is a corner lot (two streets meet at it, §325-19C): enter corner
  lot yes or no"; "a corner lot, but the street lot lines given run along one street (they never turn more than
  30°): pick the lot lines on both streets"; "the address street given isn't one run of the street lot lines: pick
  the lot line(s) on the street the address is on again"; "the lot line opposite the address street is on a street
  too (a through lot, §325-8A(14)(d)): which yards are rear and front is an open question for the architects";
  "every side lot line is on a street (a lot on three streets): which yard is a side yard is an open question for
  the architects".
- **What research settled** (`interpretations.py`): "the city's files no longer have that finding (answered
  without naming the reading, or removed): the measuring can't follow it" (any finding or open question the code
  follows, named in the reason); "a reading research lists (a_reading, an_entry) has no measuring code yet".
- **Side and rear lot lines:** "the side and rear lot lines can't be told apart (more than 6 lot lines could be
  either: too many readings to list)" (the lot depth and the side and rear yards wait, on a corner lot whatever
  the other address streets give; the frontage and the front yards don't depend on those lines and are still
  measured); "no reading of the lot lines gives two side lot lines and a rear lot line
  (a triangular lot, for one): an open question for the architects".
- **The ground:** "the ground level isn't given: enter it (the grade plane)"; "the ground level (<ground> ft)
  doesn't meet the buildings (they run from <bottom> to <top> ft): check the ground level" (at or above the top
  of all the buildings, or under the lowest point of all of them, as when a survey elevation is typed for a model
  drawn at z = 0; stacked solids and a basement drawn as its own solid are measured as usual); "a solid lies wholly under the
  ground (<ground> ft; it runs from <bottom> to <top> ft) and isn't joined directly under the building: check the
  ground level and where the solid is" (a basement counts when its top meets the bottom of the solid above it and
  it lies within that solid's plan; a sub-basement under it too); "say whether the ground is flat";
  "sloped ground: the grade plane (§325-3) needs the ground levels around the walls, which aren't measured yet".
  With spot grades placed in the model (or the terrain, which the Rhino command samples at the walls each time it
  checks), the grade plane is the average of each of the main building's walls' points within 2 ft of it (a point
  at another building's walls is that building's ground, left out); after the building moves:
  "spot grades no longer at the building's walls (<off> of <count> more than 2 ft from a wall, <bare> walls
  without one): set the grade again". Read with the other solids as part of the building, the grade plane is the
  ground at all of their walls: "with the other solids as part of the building, the grade plane needs spot grades
  at their walls too (§325-3: each side of the building): place spot grades around every solid on the Building
  layer". A round or finely faceted outline: "the building's walls can't be told
  apart in plan (no wall longer than 1 ft, a round or finely faceted outline): set the grade as flat ground
  instead". Measured from existing ground instead of finished: "measured from existing
  grade; the code's grade plane is finished ground level (§325-3): tick No regrading near the house, or set the
  finished ground" (height and stories).
- **Facts a massing model doesn't show,** until they are entered: "choose the use"; "enter the lot's zoning district (zone)"; "no floor blocks
  are drawn for the building, so its stories aren't drawn: draw each story as its own solid standing on the one
  below (as Gordium's starting building is), or enter the number of stories"; "enter bedrooms / parking spaces".
- **Stories, from the shape:** solids stacked one on another are one building. Its stories are the floor blocks
  Gordium drew (each marked as one story, `gordium:floor`) counted; anything else stacked on them (a podium, a bulkhead, a
  roof solid: how many stories it holds can't be told from its height) and any typed count are readings, and if
  they disagree it's a question, never an override. "a floor block below the ground: whether a
  basement or cellar counts as a story (§325-3) isn't measured yet: an open question for the architects";
  "floors misaligned: a floor block sticks out past the one below it (one floor moved on its own?): move the floors
  together, or draw the overhang as part of its floor". Every solid one over another in plan (plain or floor
  blocks) is the same building whatever the gap between them (a tolerance never decides what the building is), and
  a real gap between its levels asks: "parts of the building drawn one over another don't stand on each other (from
  {low} ft to {high} ft): a floor not drawn, or a space open to below? draw the missing floor, or check the
  blocks". Parts at the same level (an L-shaped house of two stacks) are no gap. One starting partly inside the one below
  (a floor moved down into it, a room sunk into the roof) asks too: "part of the building ({what}) starts partly
  inside the one below it (from {low} ft to {high} ft): move it to stand on the one below, or join them". So moving
  a part a tenth of a foot never turns one count into another. Stories are counted only from floor blocks: a part drawn as a plain solid
  (or plain solids stacked) never has its stories guessed from its height or its blocks. Only a plain part standing
  on the ground and lower than 7 ft (the lowest ceiling a habitable room may have, NYS Residential Code R305.1: a
  porch slab or steps) fits inside the first story and is left out; any other (raised, on a roof, reaching below
  the ground: §325-3's STORY has no least height) is a plain part, and with one the count typed stands for the whole building, and only if no part's floor blocks count more: "the stories typed
  ({typed}) are fewer than the floor blocks drawn ({drawn}): check the count, or the floors", nor the solids stacked
  in a plain part: "the stories typed ({typed}) are fewer than the solids stacked on {what} ({blocks}), which may
  each be a story: check the count"; with none typed:
  "part of the building ({what}) isn't drawn as floor blocks, so its stories can't be counted: enter the number of
  stories of the whole building". Any part reaching below the ground, whatever was typed: "part of the building
  ({what}) is below the ground: whether a basement or cellar counts as a story (§325-3) isn't measured yet: an open
  question for the architects".
- **The buildings:** "no building on the Building layer"; "two building objects share the id {id}: one would be left out of the measurements"; "more than one building: pick the main building"; "a building isn't on the lot (is it part of this design?)" (a building
  wholly off the lot: only the rules that would measure it wait: the main yards for the main building, the accessory
  rule for an accessory building, coverage for any. A building partly off the lot is measured, and every rule that
  measures it does not comply, whatever the readings or answers: the main yards, the eaves, the height and the
  stories for the main building, the accessory rule for an accessory building, coverage for any; each building is
  placed on its own, never changed by another); "a building isn't a closed solid"; "a building mesh isn't closed"; "a building
  has a curved surface (not measured yet)"; "a building has a curved edge (not measured yet)"; "a building mesh's
  points may be single precision, too coarse this far from the origin to measure to 0.01 ft (move it nearer the
  origin, or turn it into a solid)"; "a block on the Building layer can't be measured yet (explode it or turn it
  into a solid)" (the same for a surface or anything else that isn't a solid or mesh: it is reported, never left
  out, since leaving it out would undercount coverage).
- **Accessory buildings:** "no accessory building on the lot (every solid is the main building or touches it)".
- **The height:** "no roof plane of the pitched roof's highest section lies over the walls: the wall plate can't
  be found"; "the roof's shape can't be read (no faces open to the sky)"; "another solid's height can't be
  read: …"; "too many solids with open roof questions to list every reading: pick the main building's parts, or
  ask the architects" (more than 200 combinations of readings).

Sublayers count (`Building::Garage`); a block's own definition is never read as a building. Mistyped lot facts (a
ground level that isn't a number) are refused with a plain message before anything is measured.

Every measurement records its working: how it was found, the objects, the definition it follows, and for
distances the two points it was measured between. The project file's `from` carries it, so the report shows it.

## How we know it's right

`tests/`:
- **The architects' design drawn as a model** (`spreadsheet_design_model.3dm`, made by
  `tests/make_spreadsheet_model.py` from their spreadsheet's numbers): every measurement equals their cell, and
  the R-1b results equal their PASS/FAIL on all 11 rows.
- **The architects' own model** (`model.3dm`): measured as sent, and with its house solid moved onto its own
  outline on the Site layer (the shift is found from the vertices). Every number is compared with their
  spreadsheet; each difference is pinned and explained in `docs/discrepancies_with_architects.md` §4.
- **Made-up lots with known answers:** rectangular, tilted 37°, raised ground, a curved street, a jog, a corner
  lot, two buildings, an overhang, a pitched roof; and in `tests/test_stop_list.py`, a case for each reason
  that stops a measurement.
- **Reading Rhino files:** inches, two outlines, a picked lot, a copy keeping its id, a mesh, a curved wall, a
  curved lot line.
- CI re-measures every committed model and fails if a measured file is out of date.

## Not yet

Curved walls and roofs (reported, not measured); sloped ground (one level only); counting stories from floors
in the model (stated by the architect for now); chimneys and other roof features the height definition leaves
out (a part above the main roof gets "needs review", with its top listed).
