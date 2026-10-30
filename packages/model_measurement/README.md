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
  The model is the whole lot: every building on it, existing ones to stay included, is drawn on the `Building`
  layer, since lot coverage, the count of primary buildings and every rule reading them see only what is drawn.
- **Lot facts**: what a model can't show, stated by the architect. In Rhino they are asked once (prefilled)
  and saved in the file; on disk they sit next to the model as `<model>_facts.yaml`:

  | Fact | Why it's needed |
  |---|---|
  | `zone`, `jurisdiction`, `use` | pick the rules |
  | `street_line` | **every** lot line on a street, each by its two ends (on a corner lot: both streets and any curve between them); front, side and rear all follow from it |
  | `corner_lot` | yes or no: two streets meet at the lot (§325-19C). Stated, never guessed from the drawing (the city's definition has no angle in it). Without it, everything that depends on the street says "needs review". On a corner lot every yard facing a street is a front yard (§325-19C, the law), the rear yard is opposite the street the address is on (§325-8A(14)(d)), and the one side yard left is checked against Column 13 (Gordium's reading, City practice) |
  | `street_ids` | one per `street_line`, in the same order: the street that lot line is on (the street's name, or Gordium's own "Street 1", "Street 2"… for a street nobody named), recorded by the Rhino street pick or the lookup. On a corner lot it is the only way Gordium knows which lines are which street (never guessed from where the lines turn): missing for any street line, saved for other lines, or one street's lines not next to each other, and the lot width, lot depth and every yard from the street lines say "needs review" and ask for the street pick |
  | `address_street_line` | on a corner lot: the lot line(s) on the street the lot's address is on (it decides which yard is the rear yard); any of that street's lines means the whole street (its `street_ids`). Not given, each street is read as it, and the yards it changes need review |
  | `accessory_buildings` | the ids of the solids that are accessory buildings (a garage, a shed). A solid standing apart from the main building that isn't listed could be a freestanding deck (part of the building, §325-18A), so both are read. Listing them also picks the main building (the one left) |
  | `accessory_frame` | yes or no: the accessory buildings are frame. Frame ones keep §325-25C's distances by law; for others it is an open question (325-25C#1), read every way |
  | `eaves_confirmed` | a lot fact for one overhang (the panel will ask for it in a later release): [{overhang (its fingerprint, from the check), value: true, source, confirmed_by, date}]. Without it, a yard that meets its minimum only to the walls needs review; a later edit to the overhang asks again |
  | `grade_elevation` | the ground level heights are measured from (a flat site) |
  | `ground_is_flat` | yes or no. Sloped ground needs the ground levels around the walls (the grade plane), not measured yet: without a yes, height, building area and the yards say "needs review" |
  | `lot_surveyed` | yes or no: the lot outline is from a survey. A drawn lot (from a map) isn't: without a yes, the lot area, and so lot size and coverage, say "needs review" (the drawn area is listed as a reading) |
  | `lot_id`, `main_building` | only when there is more than one candidate |
  | `primary_buildings`, `primary_buildings_same_use` | how many primary buildings stand on the lot, the main one included (§325-3B PRIMARY STRUCTURE), and whether every one holds the lot's use (§325-8B(1): each needs its own lot area). The count is read from the drawing where it can be: one building, or every solid standing apart from the main building touching it, listed in `accessory_buildings`, or too small or low to hold a home (`_could_be_principal`): 1. Otherwise two readings, every one an accessory building (1) / every one that could hold a home a primary building (1 more each), until the count is stated |
  | `garage_cars`, `private_garages` | the cars the lot's private garages hold, all together (every enclosed garage, attached or detached; 0 for none), and how many private garages there are: the chart's car limit (p.2 notes 6 and 7: three cars in R-1a to R-2b, six per building in R-2c). The count of garages matters only when the cars are over the limit (whether the limit is for each garage or the lot is an open question) |
  | `adu_building` | the id of the solid that is the detached accessory dwelling unit's building, picked in Rhino as the main building is (never guessed). While an ADU may be on the lot and may be detached (`accessory_dwelling_unit` and `adu_detached` not no), it is never the main building or a freestanding deck, it is measured on its own (`adu_*` below), and it is left out of §325-25's accessory measurements and of the count of primary buildings: the ADU's own rules hold it to §325-25 as well as §325-28 (research: `docs/research/2026-10-29_accessory_dwelling_units.md`). Said no to either, it is an ordinary building again |
  | `adu_detached`, `adu_existing_building`, `adus_on_parcel`, `adu_bedrooms`, `adu_floor_area`, `primary_floor_area` | the accessory dwelling unit (§325-3B, §325-28C): detached or attached; for a detached one, in an existing accessory building or new; how many ADUs the parcel has; its bedrooms; for an attached one, its floor area and the primary structure's, the ADU included |
  | `stories`, `sleeping_rooms`, `parking_spaces` | not drawn in a massing model; the rules that need them say "needs review" until they're entered |

## How each number is found

**Which drawn lines form each lot line (decided 2026-10-21, review round 20).** A drawn outline's pieces are grouped
into lot lines by cleaning it within its own accuracy: a corner goes when leaving it out moves the outline by no
more than 0.01 ft on a survey, 0.25 ft on the tax map (pieces in line, slivers). A corner where the street meets
the other lines, or at a curved line, always stays. The cleaned outline only decides which drawn pieces form each
line (street, side, rear; the readings of which are which), so it can only drop readings the drawing's noise made.
Every distance is still measured to the pieces drawn, never to a chord across them, and the lot area is the
outline drawn. Lines are named by the architect's own numbering ("line 10 to 11" for two drawn pieces read as
one), and each lot-line measurement says the outline was cleaned (its `from` text and the panel's detail).

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
| Detached ADU (`adu_footprint`, `adu_height`, `adu_stories`, `adu_front_yard`, `adu_side_yard`, `adu_rear_yard`) | the picked building on its own: its footprint seen from above (with a candidate eave, read with and without it: "footprint" isn't defined); its height as the main building's is measured, from the grade plane at its own walls (spot grades given) or the ground level given, waiting whenever the main building's height waits for the ground; its stories read from the drawing only (a plain solid holds at most one story per 7 ft, R305.1: at most two is measured as two, never asked; more needs its floors drawn); its least distances from the street lot line(s), a side lot line and the rear lot line, every reading of which lines are side and rear | §325-28C(7)(c), (8)(b)[2] |
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
| The same solid, if it could hold a home (enclosed, a story tall, a habitable room's floor area), for the count of primary buildings (`primary_buildings`) | every one an accessory building / every one a primary building; a rule the count could change needs review until the architect states it | not a question: the architect states the count |
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
  lot yes or no"; "a corner lot, but the street lot lines given are all on one street: pick the lot lines on both
  streets"; "which street lot lines are on which street isn't recorded: pick the street side so Gordium knows which
  lines are which street (a corner lot's lot width is the frontage on one street, §325-8A col. 7)"; "the street lot
  lines recorded on one street aren't next to each other, or one lot line's pieces are recorded on two streets: pick
  the street side again, one click on each street"; "the address street given isn't one run of the street lot lines
  on one street: pick the lot line(s) on the street the address is on again"; "the lot line opposite the address street is on a street
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
  below (as Gordium's starting building is), or enter the number of stories"; "enter bedrooms / parking spaces"; "enter the dwelling units, the rooms let for profit, and whether it is a conversion" (R-3a chart note 7: the lot size grows with them); "enter the occupants (§325-3B OCCUPANT: in R-2c, every person with the right to occupy)" (R-2c chart notes 4-6: the lot size grows with them); "enter the dwelling units in the whole attached building, every lot it stands on" (R-2c: §325-3B's three to six); "optional: enter the most occupants in any one dwelling unit (R-2c: settles a lot size that depends on how the occupants are split)"; "say whether any R-1a or R-1b land is touching the lot (even at a corner), or across a street, alley, creek or other waterway, railroad or other right-of-way from it (§325-19E)" (R-3a.abutting_r1: no, and the stricter limits don't apply); "enter who lives in the dwelling: the unrelated people in each unit, whether the owner lives there, whether the household is a functional family unit, whether an accessory dwelling unit is on the lot (§325-3B)" (the occupancy rules of §325-3B's one-family and two-family dwellings); "say whether a home occupation is planned and, if so, its floor area and its dwelling unit's (§325-3B HOME OCCUPATION)" (the home-occupation rules); "enter the primary buildings on the lot (each separate building holding a home or other permitted primary use, the main one included; not a garage, shed or accessory dwelling unit) and whether every one holds the use entered (§325-8B(1))" (a second building that could hold a home: §325-8B(1)'s lot area for each, §325-7B, the South Hill Overlay); "say whether the lot is in the South Hill Overlay District (§325-8E, on the City's zoning map)" (R-1 and R-2 with two or more primary buildings); "enter how many cars the lot's private garages hold, all together: every enclosed garage, attached or detached (0 if there is none; a carport isn't enclosed) (chart p.2 notes 6 and 7)" (the private garage's car limit, R-1a to R-2c); "enter how many private garages are on the lot, an attached garage included (chart p.2 notes 6 and 7: needed when the cars are over the limit)" (asked only once the cars are over the limit: whether the limit is for each garage or the whole lot is an open question); "say whether any inlet wall or stream bank (at average water level) is within 20 ft of the lot and, if so, how far the nearest new structure is from it (§325-26)" (the stream setback, every residential district); "no stream or inlet is said to be within 20 ft of the lot, but a new structure is said to be {distance} ft from one: check both answers" (the two stream answers contradict each other: both are set aside); "the count of unrelated people with minor dependent children included ({with_}) is lower than the count without them ({without}): check both counts" and "{here} dwelling units on this lot but {building} in the attached building: part of another building may be on this lot, or one of the counts or the use is off" and "the most occupants in one dwelling unit ({most}) is more than the occupants of every unit on the lot together ({occupants}): check both counts" and "change the use with Edit site… in the start box" (added after a contradiction that sets the use aside: the use has no "Enter …" button) and "{occupants} occupants on the lot, but {units} {unit_words} with at most {most} in any one can hold only {held}, with no accessory dwelling unit on the lot: check {check} and the accessory dwelling unit answer" (facts that contradict each other: every fact in the pair is set aside, so no rule reading either one complies; the panel also shows a "Lot facts disagree" row to re-enter them).
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
  nothing to measure (no faces): check it on the Building layer"; "the drawing's geometry couldn't be worked out ({what}): check the building and lot outlines for faces meeting at slivers" (any geometry failure while measuring: every measurement waits, saying why, never a crash; the architect's stated facts still stand); "a building isn't inside the lot: {what}" (a building wholly off the lot: only the rules that would measure it wait. A building partly off the lot is measured, and every rule that measures it does not comply, whatever the readings or answers; each building is placed on its own, never changed by another); "a building isn't a closed solid: {what}" (which object: its Rhino name, else its id; every row waiting on it points at it, so Zoom to finds it, and a building wholly off the lot is still named beside it); "a building mesh isn't closed"; "a building
  has a curved surface (not measured yet)"; "a building has a curved edge (not measured yet)"; "a building mesh's
  points may be single precision, too coarse this far from the origin to measure to 0.01 ft (move it nearer the
  origin, or turn it into a solid)"; "a block on the Building layer can't be measured yet (explode it or turn it
  into a solid)" (the same for a surface or anything else that isn't a solid or mesh: it is reported, never left
  out, since leaving it out would undercount coverage).
- **Accessory buildings:** "no accessory building on the lot (every solid is the main building or touches it)".
- **A detached accessory dwelling unit** (§325-28C): "pick the detached accessory dwelling unit's building (the solid
  it is in) with Pick the ADU's building…"; "no detached accessory dwelling unit is said to be on the lot" (its rules
  don't apply then); "the solid picked as the accessory dwelling unit's building is no longer in the model: pick it
  again"; "the solid picked as the accessory dwelling unit's building is the main building or touches it (part of it,
  §325-18A): pick the ADU's own building, or say the ADU is attached"; "the spot grades don't give the ground at the
  accessory dwelling unit's own walls (§325-3 GRADE PLANE): place spot grades around its building"; "the accessory
  dwelling unit's building, {height} ft tall, could hold up to {most} stories (7 ft a story, R305.1): draw each story
  as its own solid standing on the one below"; and its stated facts: "say whether the accessory dwelling unit is
  attached (in or on the main building) or detached (its own building) and, if detached, whether it is in an existing
  accessory building or new construction (§325-3B, §325-28C(7))"; "enter how many accessory dwelling units are on the
  parcel (§325-28C(1): one at most)"; "enter the accessory dwelling unit's bedrooms (§325-28C(3): two at most)";
  "enter the attached accessory dwelling unit's floor area and the main building's, the ADU included (§325-28C(7)(a):
  40% at most)".
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
