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
  | `corner_lot` | yes or no: two streets meet at the lot (§325-19C). Stated, never guessed from the drawing (the city's definition has no angle in it). Without it, everything that depends on the street says "needs review". On a corner lot, the lot width, lot depth and every yard are left for the architects: which yards are front, side and rear, and which frontage is the width, are open questions (and a drawing can't show whether both streets were given) |
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
| Building area | ground area of every building on the lot | building_area: "the total area … of the principal building and all accessory buildings" |
| Height | ground level to the highest level of a flat or mansard roof (its highest section is level, or within a drainage slope of level: under 1/2 inch per foot) | height_of_building: "to the highest level of a flat or mansard roof" |

Side and rear lot lines follow from the street: lines next to the street lines and about square to them
(60° or more) are side lines; lines not next to them and about parallel (30° or less) are rear lines.

## Never a guess

Where the law can be read more than one way, **every reading is measured**. If they give the same number, that
is the value (and the readings are listed in the working); if not, there is **no value**, the readings are
listed, and the reason names the open question for the architects, so the checker says NEEDS REVIEW:

| Case | Readings | Open question |
|---|---|---|
| A lot line that is neither clearly side nor rear (a jog) | the line as a side line / as a rear line | lot_depth: "which lines count" |
| A curved street line | along the curve / straight across | lot_width |
| Something sticking out above the ground floor (an overhang, eaves) | measured to the building seen from above / to its walls at ground level | building_area, yard_projections |
| More than one solid on the Building layer | every yard to the main building / to any solid (a porch or deck drawn as its own solid is part of the building, §325-18A; an accessory building may follow other rules) | yard_projections, §325-25 |
| A pitched roof | midway between eave and ridge / to the ridge | height_of_building: "average height" |
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
  "the street lot lines given are on two streets: a corner lot (§325-19C), so which yards are front, side and rear,
  and which street's frontage is the lot width, are open questions; answer Corner lot?"; "the street lot lines given
  turn 90° in all: do they face one street that bends, or two streets at a corner? Answer Corner lot?, or name the
  street each lot line is on" (lot width is frontage on one public right-of-way, §325-8 Column 7: never measured
  along two streets; one street or two is the street's identity first, the drawing's total swing only when none is
  known: street_lines.py); "the street names saved for the street lot lines no longer match them (the lines were
  picked again): pick the street side again" (names saved before the lines changed are set aside, never used:
  the lot facts are still read and checked);
  "every lot line is on a street: which yards are front, side and rear is an open question for the architects".
- **Corner lots** (§325-19C): "say whether this is a corner lot (two streets meet at it, §325-19C): enter corner
  lot yes or no"; "a corner lot: which yards are front, side and rear yards, and which street's frontage is the
  lot width (§325-19C), are open questions for the architects".
- **Side and rear lot lines:** "the side and rear lot lines can't be told apart (more than 4 lot lines could be
  either: too many readings to list)"; "no reading of the lot lines gives two side lot lines and a rear lot line
  (a triangular lot, for one): an open question for the architects".
- **The ground:** "the ground level isn't given: enter it (the grade plane)"; "the ground level (<ground> ft)
  doesn't meet the buildings (they run from <bottom> to <top> ft): check the ground level" (at or above the top
  of all the buildings, or under the lowest point of all of them, as when a survey elevation is typed for a model
  drawn at z = 0; stacked solids and a basement drawn as its own solid are measured as usual; with spot grades,
  one test whatever the points' positions: each connected building group (touching in plan or one over another,
  so a balcony against the house is part of it) meets the ground if its bottom is at or below the ground the
  points describe at some corner of its footprint, and its top is above it); "the spot grades don't show the
  ground under the building (too few, or in a line): place spot grades around the building"; "a solid lies wholly under the
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
  blocks". Parts at the same level (an L-shaped house of two stacks) are no gap. A plain part starting above the ground
  (a room beside the roof edge or over it, touching in plan or not) asks, whatever was typed: "part of the
  building ({what}) starts above the ground: it may be another story: draw its stories as floor blocks, or check
  the count". One starting partly inside the one below
  (a floor moved down into it, a room sunk into the roof) asks too: "part of the building ({what}) starts partly
  inside the one below it (from {low} ft to {high} ft): move it to stand on the one below, or join them". So moving
  a part a tenth of a foot never turns one count into another. Stories are read from the drawing as far as it allows: floor blocks are
  counted, and a part drawn as a plain solid (or plain solids stacked) h tall can hold at most floor(h / 7 ft)
  stories (7 ft: the lowest ceiling a habitable room may have, NYS Residential Code R305.1), and every
  building at least a first story (§325-3; a count of 0: "the stories typed ({typed}) are fewer than one: every
  building has at least a first story (§325-3): check the count"). So a
  12 ft garage holds one, and a 30 ft plain house one to four: then the count is a question ("a 30 ft solid could
  hold up to 4 stories: draw its floors or enter the count"), and the count entered stands for the whole building
  only within what the drawing allows: "the stories typed ({typed}) are fewer than the floor blocks drawn
  ({drawn}): check the count, or the floors"; "the stories typed ({typed}) are more than the drawing could hold
  ({what}, {height} ft tall: at most {most}, at 7 ft a story, R305.1): check the count, or the drawing". Only a
  plain part standing on the ground and lower than 7 ft (a porch slab or steps) fits inside the first story and is
  left out; one raised, on a roof or reaching below the ground (§325-3's STORY has no least height) asks. Any part reaching below the ground, whatever was typed: "part of the building
  ({what}) is below the ground: whether a basement or cellar counts as a story (§325-3) isn't measured yet: an open
  question for the architects".
- **The buildings:** "no building on the Building layer"; "two building objects share the id {id}: one would be left out of the
  measurements"; "more than one building: pick the main building" (with none picked and exactly one starting house, it is
  the main building, assumed: every measurement from it carries `main_assumed`, and every other building that
  could be a principal one (enclosed, at least 7 ft tall and 70 sf: NYS Residential Code R305.1, R304.1) is also
  read as if it were the main one, so the assumption never passes what a pick wouldn't); "a building object has
  nothing to measure (no faces): check it on the Building layer"; "a
  building isn't inside the lot: {what}" (which one; the yards wait only if it is the main building); "a building isn't a closed solid"; "a building mesh isn't closed"; "a building
  has a curved surface (not measured yet)"; "a building has a curved edge (not measured yet)"; "a building mesh's
  points may be single precision, too coarse this far from the origin to measure to 0.01 ft (move it nearer the
  origin, or turn it into a solid)"; "a block on the Building layer can't be measured yet (explode it or turn it
  into a solid)" (the same for a surface or anything else that isn't a solid or mesh: it is reported, never left
  out, since leaving it out would undercount coverage).
- **The height:** "the roof's shape can't be read (no faces open to the sky)"; "another solid's height can't be
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
