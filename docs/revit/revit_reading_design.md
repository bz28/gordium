# Revit port: how the add-in reads a Revit model (design note)

**Purpose:** the plan for how the Revit add-in (C#, .NET 10, Revit 2026 and 2027) turns a Revit model into Gordium's [site description](../protocol/site_description_v1.md) (`gordium.site/1`), so day 1 of the [Windows trial](windows_trial_runbook.md) starts from a written plan.\
**For:** whoever writes the Revit reader in the trial; reviewers checking that nothing it sends could turn a "needs review" into a "complies".\
**Kept current by:** the trial, as it settles each "to check" below; any PR that changes the site description, a conformance scene or one of the Rhino reader's decisions this note copies.

A **reader** is the code in a design tool (a **host**) that looks at the model and writes the site description.
Rhino's reader already exists (`model_measurement/read_3dm.py` for the lot and the Building layer;
`apps/rhino_plugin/gordium_rhino.py` and the reference adapter `design_checker/conformance_rhino.py` for everything
else on the lot). The Revit reader **copies its decisions; it invents none**. Where Revit has something Rhino
doesn't (categories, phases, design options, linked models), this note says what the reader does and marks it
**proposed**: those need Ben's agreement, and a new conformance scene, before they count. Why Revit gets its own
reader at all: the [decision of 2026-11-06](../decisions/2026-11-06_hosts_talk_to_the_worker.md).

**The one rule behind every row below** (principle 4, never a false pass): anything the reader can't read exactly
is reported with a problem code, never guessed, never smoothed, never dropped. An object it is unsure about counts
as touching the house.

## 1. What becomes a building, and what is left out

Rhino sorts by layer: solids on the Building layer are the building; any other solid on the lot is "left out" and
makes the check need review. Revit has no layers, so the reader sorts by **category** and by **what the geometry
is** (Rhino's `rhino_logic.could_be_building`, widened on the cautious side, proposed: a Revit solid or mesh with
any face counts, where Rhino needs a closed solid or more than one face, or a closed mesh or more than 4 faces.
Whether a Revit mesh is closed is **to check**, and not knowing it never drops one: the Revit reader counts at least
everything Rhino counts).

**Which elements are looked at.** Every element of the open document (`FilteredElementCollector(doc)`), never a
view's collector: an element hidden, isolated, cropped or in a hidden category still counts, as Rhino counts hidden
and locked objects ("a hidden shed still counts", `gordium_rhino._not_included`). Each element's `layer` in the
description is its category name (`"Walls"`), and an unsent one's `kind` says what it is (`"a linked model"`); both
are for the architect's reading only (proposed).

| Revit element | Sent as | Rhino equivalent | Scene that tests it |
|---|---|---|---|
| Proposed building categories: walls, floors, roofs, columns (architectural and structural), stairs, railings, ramps, doors, windows, curtain wall panels and mullions. A component stair's runs, landings and supports, and a railing's top rail and handrails, are their own elements in their own categories: whether they are read as part of the building or through their stair or railing is **to check** (until then they fall to the "any other element" row: left out, touching, the cautious side; and a stair element with no faces of its own is unsent, row "no face to send"). Left off on purpose for the first reader, so they fall to the "any other element" row (left out, and usually touching: the cautious side): structural framing and foundations, ceilings, roof fascias, gutters and soffits, wall sweeps, slab edges, casework | `buildings`: one per element, id its `UniqueId`, faces of all its solids | A solid on the Building layer | 01 (as floor blocks); native elements: **new scene A** |
| **Site slabs (2026-11-20):** a Floor (a system floor, no Gordium mark of its own) whose plan box (Revit's own) overlaps, by more than the vertex tolerance both ways, the plan box of no wall and no roof in the design checked: a concrete pad, a patio, a driveway or a walk, which the Floor tool draws as it draws the house's floors (found on Autodesk's Pacific Continental sample: a "Concrete 10\"" slab outside the house, partly past the property line, read as a building, so lot coverage did not comply). Chapter 325 counts them by what they are: "All porches, attached or freestanding decks, … ramps, and/or landings shall be considered a part of the building in both the determination of required yards and lot coverage" (§325-18A; §325-3B BUILDING AREA); building area "shall not include parking areas and parking spaces. Pergolas and terraces and patios shall be exempt from total lot coverage requirements. However, neither pergolas or terraces and patios above grade shall be located in a required yard" (§325-3B); TERRACE OR PATIO: "less than 18 inches above grade, without a roof, … Terraces and patios above grade shall not encroach into required yards"; STRUCTURE "shall not include patios or terraces". Revit can't tell which, so the architect says, with the `Gordium: Site slab is` mark ([revit_interior_reading_design.md](revit_interior_reading_design.md), section 3): Porch, Deck, Landing or Ramp; Patio, Terrace or Walk (a walk read as a patio: §325-3B has no walk, TERRACE OR PATIO is "a level plane or surfaced patio", and GREEN SPACE names "sidewalks or patios" together); Parking or Driveway. Every other floor is part of the building, its mark not read (the marking list says so). Either way a wrong sorting is never a false pass: a house floor read as a slab (one drawn only to the walls' inner faces, with no roof drawn yet) makes lot coverage and the yards need review; a slab read as part of the house (one near a diagonal wall's box, under the eaves, or crossed by a garden wall drawn as a Wall) is measured as every floor was before. Not site slabs: an in-place or loadable family in Floors, a floor with no box (read as before). | A porch, deck, landing or ramp: `buildings`, as any floor. Any other: `left_out` with `slab` (`patio`, `parking`, or `unmarked` when unset or a word not in the list) and its `name`; never measured, so never a failure. The checker ([site_description_v1.md](../protocol/site_description_v1.md#how-the-worker-uses-it)): unmarked, lot coverage and every required yard need review, naming it; a patio, the yards need review (its height above the ground isn't measured yet); parking, nothing. An unreadable one is sent as a building part is (unsent) | None (Rhino's Building layer is the architect's choice) | Reader pins (`SiteSlabTests`: the Pacific Continental case, each mark word, the edges of the rule); the checker's: `test_site_slabs.py` |
| **Objects standing apart (2026-11-20):** any element left out (the rows below) that touches no building (`touching: false`): a freestanding deck, porch, landing or ramp drawn as a Generic Model or a family of another category is "part of the building in both the determination of required yards and lot coverage" (§325-18A; DECK: "A structure freestanding or attached to a building"), and a YARD "shall not be occupied by any other building or structure from the ground upward unless specifically authorized" (§325-3B), so the yards could comply while one stood unmeasured in a required yard (the gap PR #135 left). A STRUCTURE is "Anything constructed or erected on the ground or which is attached to another structure or building" (§325-3B): trees and plants (Planting) and people and cars placed for show (Entourage) aren't, so they are sent with `could_be_building: false`; everything else could be one (cautious: a bench, a fitting, a DirectShape or an in-place family of unknown use). The architect can say what one is with `Gordium: Site object is` ([revit_interior_reading_design.md](revit_interior_reading_design.md), section 3): Porch, Deck, Landing or Ramp (sent as a building, measured: standing apart it is read both as a freestanding deck and as an accessory building, `measure._yards`); Garage, shed or carport (an accessory building, §325-25: measured the same way); Not a structure (`could_be_building: false`). Never a slab's word (review round 1): a patio or a driveway leaves every check, so those are read on a Floor alone, whose shape is a slab; typed on anything else they are not understood (a garage drawn as a Generic Model and marked Parking stays in the check). | `left_out` as before, with its `name` when it stands apart; `could_be_building: false` for Planting, Entourage and one marked Not a structure. The checker ([site_description_v1.md](../protocol/site_description_v1.md#how-the-worker-uses-it)): one that could be a structure, standing apart, keeps every required yard (to the walls and to the eaves) at needs review, naming it, wherever it stands: the description has no outline for it, so the check can't tell which yard it is in (one yard alone needs its outline sent: a protocol change, and the Revit scenes recorded again). Lot coverage needs review for any object left out, as before | A solid off the Building layer, apart from the house: the same rows (the checker is shared) | Reader pins (`SiteObjectTests`); the checker's: `test_objects_apart.py`; scene 05's garage (a Generic Model in the Revit recording) |
| Gordium's own floor blocks (drawn by `start_site`; proposed: DirectShapes carrying a Gordium mark with `"<story>;<height>"`, as Rhino's `gordium:floor` user text) | `buildings`, with `floor` = the height drawn | Floor blocks on `Gordium::Massing` | Every drawn scene: each expected building is a floor block with `floor: 10`, so every scene's house (02's curved one and 03's open one too) is drawn as marked floor blocks, built from real solids (`GeometryCreationUtilities` or `BRepBuilder`, never a faceting builder that would turn 02's curve into flat faces: **to check**) |
| Curtain wall (the host wall itself) | Proposed: its panels and mullions are their own elements (row 1); the wall sends its own faces only if it has any (**to check**: whether a curtain wall's own geometry is empty, so no face is sent twice) | | **new scene A** |
| In-place family | Proposed: by its category, like the building-category row; off the building categories, as the family instance row below (left out whatever its geometry unless marked a building with `Gordium: Site object is`, never dropped for having none at Fine detail). `Family.IsInPlace` only names it in the panel | | **new scene A**; empty: **new scene H** |
| A shared nested family (a sub-component: `FamilyInstance.SuperComponent` names the instance it sits in) | **Decided (2026-11-19, section 8):** read as part of the family it sits in, at any depth, never as its own element: its geometry is added to its host's as one nested family (`SiteReader.Fold`), so it makes its host's box bigger, one with no face (empty, lines only) leaves its host with no box (`touching: null`), and one that can't be read makes its host unreadable. Revit lists it as its own element, outside its host's geometry (the trial); a nested family that isn't shared is already inside its host's geometry. Never folded, so read on its own: a sub-component that is a building part (a building category, a floor block, or one marked a porch, deck, landing, ramp, or garage, shed or carport with `Gordium: Site object is`: `SiteReader.IsBuildingPart`) (a window nested in a kit family is a building wherever it sits, and a linked model holding one holds a building: review round 1); one whose host isn't in the model; one in a loop of hosts | A nested block: part of its block | 26 (the shed's empty part); reader pins (a nested window, a loop) |
| Model group | Proposed: never itself: each member element is read on its own (a group has no geometry of its own) | | **new scene E** (ids after editing a group) |
| Any other element with a Revit `Solid` or mesh with faces (closed or not) (generic models, masses, site, planting, specialty equipment, furniture) on the lot | `left_out`, `could_be_building: true` (false for Planting, Entourage and one marked Not a structure: "Objects standing apart" above) | A solid on the Default layer | 05 (garage), 15 (porch); the recorder draws these as Generic Models |
| A family instance off the building categories, loadable or in-place, whatever its geometry (even none at Fine detail), unless marked a building with `Gordium: Site object is` (then a building: "Objects standing apart" above) | `left_out`, `could_be_building: true`; with no box, `touching: null` | A block on another layer: Rhino counts every block, whatever it holds | 15 (`shed_block`); empty: **new scene H** |
| Gordium's own neighbourhood objects (proposed: marked DirectShapes, as Rhino's `Gordium::Context`) | `left_out`, `context: true` | A solid on `Gordium::Context` | 15 (`neighbour_solid`) |
| Proposed: a linked Revit model, wherever it is placed (Rhino reports such a block wherever it is, with no lot test), that holds any building part (a building-category element, a floor block, or an element marked a porch, deck, landing, ramp, or garage, shed or carport with `Gordium: Site object is`: `SiteReader.IsBuildingPart`) at any depth of links inside links (as `_block_holds`), or has a closed workset of its own (its hidden part could hold the house; **to check** that the API says so) | `unsent`, kind `"a linked model"`, `not_a_solid`: every building measure needs review. Also listed in `left_out` under its `UniqueId`, `could_be_building: true`, as Rhino lists every block off the Building layer (scene 19); ids are unique, so the `unsent` entry is then named by its kind, as Rhino's reader names its `"a block"` | A block holding Building-layer objects (`read_3dm._block_holds`) | 19 (new scene B's first case). Not 04: a link is left out too, which 04's block, placed on the Building layer, is not; the Revit tests draw 04's shed as a wall holding geometry the reader doesn't know (section 2) |
| Proposed: a linked model with no building part at any depth, or a 3D CAD import (`ImportInstance`), reaching into the lot | `left_out`, `could_be_building: true` | A block on another layer | **New scene B** (scene 15's block is already the family instance above) |
| A link that isn't loaded, including a link nested as an overlay (not loaded in the host: **to check**) | Can't be looked inside: `inventory_complete: false` | | Verdicts only: 14 (never drawn); the mapping: **new scene B** |
| A coordination model (Navisworks, Revit 2024 and later; `CoordinationModelLinkUtils.IsCoordinationModelInstance`), which Revit draws for show only and gives no geometry for (**to check**) | `left_out`, its contents not known (`contents_not_known`): on the lot and touching wherever it stands, never skipped as an element with no geometry; inside a linked model, the link has no box | A linked block whose file isn't the design | Reader pin (review round 5) |
| Elements in a closed workset | Proposed: `inventory_complete: false` whenever any user workset is closed (`Workset.IsOpen`), whether or not the reader can still read them (**to check**) | | Verdicts only: 14; the mapping: **new scene B** |
| Lines, annotations, levels, grids, reference planes, rooms, areas, views, a 2D CAD import | Not looked at (no solid: not a building) | Curves, points, text | 01 to 17 (none is sent) |
| Toposolid | Proposed: `left_out` (it is a closed solid that could be a building until the architect says it is the ground; then it gives the grade, section 5) | A terrain the architect hasn't picked | **New scene I** (scene 16's terrain is an open flat mesh, drawn in Revit as an open mesh DirectShape, not a Toposolid) |

**Phases (proposed).** The check is of the last phase (the finished design). The reader leaves out only what is
not on the lot then: elements demolished by that phase or temporary in it (and past ones, if Revit has that
status). Everything else is read as above, including elements with no phase at all. It is never built as a list of
statuses to keep, which would quietly drop any element with a status not on the list (`ElementPhaseStatusFilter`;
the exact `ElementOnPhaseStatus` values are **to check**). **New scene C**, which includes an element with no
phase. The panel and the report name the phase checked, as for design options (Ben to agree).

**Design options (proposed).** The main model, plus one option from **every** option set: the option being edited
if it belongs to that set (`DesignOption.GetActiveDesignOptionId`), otherwise that set's primary option, as Revit's
own views show them. The other options are alternative designs, not objects on the lot, so they are neither sent
nor left out. The panel and the report must
name the options checked; recording them in the description needs a new optional `host` field (a minor version of
`gordium.site/1`, since it can't change a verdict), not `host.document`, which is the file's name. **New scene D** (two option sets, one being edited). This is a
false-pass risk if the architect thinks a different option was checked, so the panel must name it (Ben to agree).

**Known consequence, not a bug.** Real Revit families are full of curved geometry (door handles, round columns,
balusters, mullion profiles). Each one puts `curved_surface` on its element, so most real models will need review
until curved faces can be measured. That is the cautious direction, and Q3 of the trial counts how often it
happens. Leaving such details out (for example geometry wholly inside a wall) would be a new decision for both
hosts, with its own scene; it is not in the first reader. The same goes for furniture and fixtures inside the house
(left out and touching, so the yards, height and stories need review on every furnished model): a rule to skip
objects wholly inside the building is **new scene F**, for Ben to decide.

## 2. Faces: flat or curved, never tessellated

| Step | How | Rhino equivalent | Scene |
|---|---|---|---|
| Geometry | Proposed: `Element.get_Geometry(new Options { DetailLevel = Fine })`, no view set (so it doesn't depend on what a view shows), `IncludeNonVisibleObjects` false. A family's `GeometryInstance` is opened with `GetInstanceGeometry()` (already placed in the model). A family instance is also read at Medium and Coarse, so a part shown only there is never missed (section 8, "Detail level") | rhino3dm's Breps | 01 |
| A face | A `PlanarFace` whose every edge is a `Line` is sent: its loops from `GetEdgesAsCurveLoops()`, each curve's start point, the outer loop as `points`, the others as `holes` (which loop is outer: **to check**; proposed the largest in the face's plane) | `_brep_faces` | 01, 10 |
| A curved face | Any other face type (`CylindricalFace`, `ConicalFace`, `RuledFace`, `RevolvedFace`, `HermiteFace`) is left out and the element gets `curved_surface`. `Face.Triangulate` is never called | `curved_surface` | 02 |
| A flat face with a curved edge | Left out; the element gets `curved_edge` | `curved_edge` | 02 |
| An empty solid | A solid with no faces (Revit families often hold some) is skipped: it has nothing to send | | **new scene H** |
| An open solid | A solid with faces and an edge that has only one face (`Edge.GetFace(1)` null): `open_solid` with `what` the element's name (**to check** that Revit gives open shells as solids, and that `GetFace(1)` behaves so) | `open_solid` | 03 |
| A mesh in an element's geometry | Its triangles as faces, with `open_mesh` unless the mesh is known to be closed (**to check** whether Revit can say) | `_mesh_faces`, `open_mesh` | **new scene A** |
| Anything else in the geometry (an object type that is not a solid, mesh, curve, point or family instance), or reading the geometry fails (`get_Geometry` throws, or returns null for a building part (a building category, a floor block, or one marked a porch, deck, landing, ramp, or garage, shed or carport with `Gordium: Site object is`: `SiteReader.IsBuildingPart`)) | The element is `unsent`, `not_a_solid`, kind its category. Null for an element that is not a building part and not a family, a CAD import or a Toposolid (those are left out with no box): skipped, as having nothing that could be a building (proposed in code, Ben to confirm: see "Where the decisions are written") | `not_a_solid` | 04 |
| Curves and points in an element's geometry | Skipped (as `read_3dm` skips curves and points) | | 01 |
| A building part (a building category, a floor block, or one marked a porch, deck, landing, ramp, or garage, shed or carport with `Gordium: Site object is`: `SiteReader.IsBuildingPart`) with no face to send at all (for example a family whose solids show only at Coarse detail) | Never skipped: `unsent`, `not_a_solid`, kind `"a <category> element with no geometry"` (as "a Walls element with no geometry": Revit names its categories in the plural), so every building measure needs review (Rhino sends an empty solid on the Building layer as a building with no faces and `open_solid`) | `read_3dm.read_site` | **new scene H** |

One building per element, not per solid (proposed; Rhino sends one per solid, which is one per object there): Revit gives no stable id to a solid inside an element, and results must
point back to something the architect can click (ids, below).

## 3. Ids, units and coordinates

- **Ids:** every element by `Element.UniqueId` (stable across sessions, upgrades and worksharing, per Autodesk;
  that it stays the same when an element is moved is **to check**: scene 12). A lot picked as several lines has one
  id: their `UniqueId`s joined by `+`, in the order picked (proposed). Scene 12; **new scene E** for groups.
- **Units:** Revit works in feet internally whatever the project shows, so no conversion is made and `units` is
  always `"ft"`; `host.model_units` names the project's length display unit for tracing only. Scene 08.
- **Coordinates (proposed: shared coordinates).** Every point and every box (lot, faces, grade, and the plan points
  and boxes of section 4) is turned once, in one place, from Revit's internal coordinates into the project's
  **shared coordinates** (the survey point's
  system: `ActiveProjectLocation.GetTotalTransform()`, which way round is **to check**). Why: scene 10 expects
  survey numbers (875,000 ft east, 885,000 north, 820 up), and Revit can't draw that far from its internal origin
  (**to check**: the limit), so the scene is drawn near the origin with shared coordinates offset; and the City's
  data the lookup uses is in survey coordinates. A model with no shared coordinates set gives the internal ones
  unchanged (every other scene). The lot facts (street lines, a flat ground's elevation) must be in the same
  coordinates: the add-in shows and takes elevations in shared coordinates. Points are kept as doubles throughout
  (no single precision), which is what scene 10 checks.
- **A box is turned by all 8 of its corners.** Shared coordinates can be turned to true north, and a box turned by
  its two opposite corners alone can come out smaller than the element; the reader turns all 8 corners (after
  applying the box's own `Transform`) and takes the box around them, which is only ever bigger. **New scene J**
  (true north turned 30°).
- **When the shared coordinates change** (the survey point moved after the facts were saved), every point sent
  moves but the saved street lines and flat ground's elevation don't: a height could then be measured from a ground
  that is no longer there. Proposed: the facts keep the transform they were entered under, and at a check with a
  different one the add-in stops sending those facts, so the yards and height need review until they are
  entered again. **New scene K.**

## 4. The lot, touching, and what counts as "on the lot"

**The lot outline.** Rhino's lot is the one closed curve on the Site layer, or the one picked (`lot_id`). Only a
closed outline is ever a lot, in Revit too: Revit lets a property line be finished open (it only warns that its
area can't be worked out), and the site description doesn't check that a lot closes. The measuring refuses such a
lot itself (`lot_not_a_loop`, "the lot outline isn't one closed loop of lot lines": scenes 24 and 25 show it), so
its measures need review either way; but only the reader can say why (it was drawn open, or the picked lot isn't
there), and the suite compares those codes. A property line, or a set of picked lines, whose ends don't meet in one loop
(within the reader's tolerance: **to check** how the API says a property line is closed) is not a lot: picked, it
gives `lot_not_found`; not picked, it counts neither as "one property line" nor towards "two or more", so with no
closed one the lot is `no_lot_outline`.

| Case | Revit reader | Scene |
|---|---|---|
| The architect picked the lot (the default flow) | The picked property line, or the picked lines forming the loop, in the order they run; `lot_id` saved in the facts | **New scene G** (no scene's facts carry a `lot_id` yet) |
| Nothing picked, one property line | That one | 01 |
| Nothing picked, two or more | `lot: null`, `several_lot_outlines` (count, layer `"Property Lines"`) | 09 |
| Nothing picked, none | `lot: null`, `no_lot_outline` | **new scene G** |
| The picked lot no longer there | `lot: null`, `lot_not_found` | **new scene G** |
| A linked model holding a property line, at any depth (in code; Ben to confirm) | `lot_block` on the site, whatever lot is read (as Rhino's block holding anything on the Site layer): the lot may be the link's, not the host's | **new scene G** |
| A straight piece | One lot line: its two ends | 01 |
| An arc (or any curved piece) | Points along it at most 0.25 ft apart (at least 16), `curved: true`, never its chord (as `read_3dm._edges`) | 17 |
| A curve with no ends (`Curve.IsBound` false: a full circle or ellipse drawn as one curve; found on Autodesk's Snowdon Towers sample, where reading its ends failed the whole check) | The Revit layer only counts it (`LotLineElement.Unbound`), never reads it. A property line holding one, nothing picked: `lot: null` and `tool_words` saying so (it may be the lot, so no other property line is taken as the one, and its other curves are never read as a lot without it). A picked line holding one (property line or model line): `lot: null`, `tool_words` saying so. Another lot picked: that lot is read. A model line nobody picked: no lot line, as before. A street-edge click on such a property line keeps no edge | Reader tests (`A_lot_line_with_a_curve_with_no_ends_...`) |

Reading a property line's boundary: `PropertyLine.GetBoundary()` exists only in the Revit 2027 API. In Revit 2026
the reader takes the property line's curves from its geometry (**to check** that `get_Geometry` gives them, and that an arc comes back as an `Arc`, never already broken into
straight pieces: scene 17 would catch it), or the architect picks the lines themselves.

**On the lot and touching** (the same rules and numbers as Rhino's: one copy, in
`design_checker/host_core/left_out.py`. Rhino's `_not_included`, `_touching` and `_unmeasured_outlines` call its
functions in Rhino's own Python; the reference adapter and the C# add-in ask the worker's session command
`objects.left_out` (protocol 1.1; `WorkerClient.LeftOutAsync`). The add-in sends what it saw of each candidate, its
`UniqueId`, its box, its plan points and, for a family instance or a linked model, its definition with what it
holds at every depth and a status (a loaded, current link: `"LinkedFileIsUpToDate"`; a family:
`"NotALinkedInstanceDefinition"`; anything else is not known, so no box), and keeps no second copy of the logic):

| Question | Rule (unchanged from Rhino) | Revit input | Scene |
|---|---|---|---|
| On the lot? | Its plan footprint reaches more than 0.1 ft into the lot (`reaches_into_lot`) | As Rhino's `_plan_points`: the element's vertices, points along its edges (`Edge.Tessellate`) and a 7 × 7 grid of points over each face (`Face.Evaluate` over the face's own range: **to check**), so a dome's bulge counts; used only for this, never sent as faces; its box corners when it has no points | 05, 15 |
| Touching? | Its 3D box within 0.1 ft of any building's box, or of the box around all the buildings together (proposed: a floor block's box holds the whole storey in Rhino, so anything inside the house touches; a single wall's box doesn't, so without this an object hung in the middle of a room would not count) | The box around the points the reader actually read (section 2 and the row above) and `Element.get_BoundingBox(null)` together, so it is never smaller than the geometry; turned by its 8 corners as in section 3, both boxes in shared coordinates | 15 (porch), 16; inside the house: **new scene A** (a loft drawn as a Generic Model, touching no wall or slab) |
| Not known | No box (or, for an element made of parts, any part with none, at any depth): listed as on the lot with `touching: null` (counts as touching), never skipped. No points but a box: its box is its footprint (the box's corners, as Rhino's `_plan_points` gives them); an element near the lot sent with no `points` at all is refused. This is `host_core.left_out`'s rule (`no_box_reasons`), which the live Rhino command (`gordium_rhino._not_included` and `_touching`) and the reference adapter (`conformance_rhino._left_out`) both use. Both also give no box to an element made of parts when any part has none: in Rhino, a block whose definition, at any depth, is missing, is empty or holds a part with no box (a linked block whose file has moved), because Rhino's own box for it would be its drawn part's alone. The Revit reader does the same for an element any of whose nested geometry (a `GeometryInstance` at any depth) gives nothing, or that holds an unloaded link (proposed). The review row then says which link and what to do, sent as `extras.left_out_advice` in the add-in's own menu words (proposed: Manage Links ▸ Reload for a link not up to date, Reload From for one whose file has moved, as Autodesk's Manage Links help names them); the sentence is `host_core.left_out.linked_file_words`'s, which a worker command would serve to the add-in when this reader is built (none does yet) | | **new scene H** |
| Looks like the ground? | `looks_like_ground` unchanged: open meshes or surfaces spanning the lot only (so a Toposolid, being closed, is not labelled in the first reader; labelling it is a later choice, with no effect on verdicts) | | 16 |

A faster first pass (only elements whose box meets the lot's box) must also take every element with no box: a
box filter quietly drops those, which is how an object could go unseen. Revit's own box filter works in internal
coordinates, so it is given the box around the lot's points in internal coordinates, grown by the reach, with no
limit up or down (Rhino's `box_near_lot` is plan only), never the shared-coordinate box (on a survey model that
would meet nothing and drop every left-out object; scene J has left-out objects for this reason, one high above the
lot). It trusts Revit's own boxes, which the touching row doesn't; so the first reader has no such pass, and one is
added only once the trial shows it gives exactly what the full read gives.

## 5. The ground

| Source | Revit reader | Scene |
|---|---|---|
| `spot` | Proposed: Gordium spot-grade markers the architect places (as points on `Gordium::Grade`), read at their location | 07 |
| `finished_spots` | The same, on a separate finished-grade marker (as `Gordium::Grade::Finished`): never mixed with `spot` | **new scene I** |
| `terrain` | The Toposolid the architect picked as the ground, sampled straight down 1 ft outside the middle of each outside edge of the building's footprint (proposed). Rhino's `_terrain_points` probes outward from each solid's own box centre, which works for whole massing blocks but, with one building per element, would probe 1 ft inside the house from a wall's inner face; so the Revit reader probes from the outline of all the buildings' footprints together (Rhino probes from every building), outward only. How to intersect a line with the Toposolid is **to check** | **new scene I**, with native walls |
| `none` | Nothing given: `{"source": "none", "points": []}` | 06 |
| Which one | The source the facts name (`grade_from`, saved when the architect set the grade), never whichever markers happen to exist; no points read means none sent, as `gordium_rhino.check_facts` does | 07; **new scene I** (its facts name the source) |

## 6. Edits and sessions

| Revit | Does | Worker command |
|---|---|---|
| `Application.DocumentChanged` (after a change is committed, undone or redone) on the open document; also a worksharing reload or sync and a link reloaded, if those don't raise it (**to check**: `DocumentReloadedLatest`, `DocumentSynchronizedWithCentral`, link reload) | Marks the model changed (`dirty_at`); the results grey out. Any change counts, as in Rhino | `session.freshness` `stale` |
| Undo or redo (the event's `Operation`) | As Rhino's undo handling | `session.undo` `recheck`, `dirty_at` |
| Revit idle (an `ExternalEvent` or the Idling event: the model may only be read when Revit allows) | After 0.5 s with no edit (Rhino's `IDLE_SECONDS`) and only with "Check after every edit" on: read the model, send `check_site` | `session.freshness` `recheck`, then `check_site` |
| The answer comes back | Shown only if no edit happened since the read began | `session.freshness` `still` |

The model is read on Revit's thread; the worker is waited on off it, so Revit never freezes on a check.

**Speed.** The first reader reads every element at every check: correct first. Its time per edit is Q4 of the
trial (targets in the runbook, section 6). A cache by `UniqueId`, refreshed from `DocumentChanged`'s modified ids,
comes only once a test shows it gives exactly the full read after many edits (a wall's edit also changes the walls
joined to it, which the event may or may not report: **to check**).

## 7. Proposed new scenes

Each case no scene covers yet. Each is hand-worked before it runs, as scenes 15 to 17 were, and recorded by every
host that can draw it. C, D, J and K have no Rhino equivalent, nor do B's unloaded link and closed workset (the
reference adapter always says it looked at everything), and I can't be read by the reference adapter (it
reads files, gives only `spot` grades, and terrain sampling lives only in the live command): those need host-only scenes, a
change to `conformance.py`.

| | Scene | Tests | False-pass risk if missed |
|---|---|---|---|
| A | A house built from parts: four wall solids, a floor slab, a roof slab, a window and an in-place family, touching; a curtain wall; one face meshed | Many solids read and measured as one building; curtain walls; in-place families; mesh faces | Yes: the measuring has only seen massing blocks |
| B | The house is wholly in a linked model; the host file has only the lot. Then a link with no building categories but a 3D shed, a CAD import, the link unloaded, a host workset closed, and a workset closed inside a loaded link | `unsent` from a link; `inventory_complete: false` | Yes |
| C | A shed demolished in the last phase, a garage existing to remain | Phases | Yes (the garage) |
| D | Two option sets: a wing (primary narrow, secondary wider) and a garage (primary only), with a wing option being edited | Which option is sent and named | Yes |
| E | Grouped walls, the group then moved | `UniqueId`s of group members after an edit | No (ids only) |
| F | Furniture inside the house, the same family outside it | Only if Ben adopts the "wholly inside" rule | Yes, if adopted |
| G | Two property lines and facts with a `lot_id` picking one (also as several picked lines); no lot outline; the picked lot then deleted; an open property line, alone and picked (also picked lines that don't close) | The picked-lot flow, `no_lot_outline`, `lot_not_found` | No (the lot then needs review) |
| H | An empty family instance on the lot (loadable, and in-place off the building categories); a building-category family with no Fine geometry; a wall whose family also holds an empty solid; a family holding a nested family with no geometry | `touching: null`; `unsent` | Yes |
| I | Spot grades and finished spots together; a Toposolid under a house of native walls, picked as the ground, higher inside the house than outside | `finished_spots`, `terrain`, probes outside the walls only | Yes (height) |
| J | Scene 15 on a model with survey coordinates and true north turned 30° | Boxes and points turned without shrinking; the box filter in the right coordinates | Yes (touching; left-out objects dropped) |
| K | Scene 01, then the survey point's elevation moved 10 ft | Facts entered under other coordinates aren't used | Yes (height) |

**Drawn so far** (the cases Rhino can draw, built by `conformance_rhino.build` with no Rhino open, their verdicts
worked out by hand before they ran; each scene's `guards` names the row above it stands for):

| | Scene | What waits |
|---|---|---|
| A | 18 (the house of parts: floor and roof slabs, walls, a window, a curtain wall's mullions and panel, a built-in, the roof a closed mesh) | The loft touching no wall or slab: it counts as touching only by the proposed "box around all the buildings" rule, which Rhino doesn't have (Rhino's reader says a loft inside a house of walls touches nothing), so it waits on Ben's decision, and then on Rhino too |
| B | 19 (the house only inside a block placed on another layer) | The link with no building categories and the CAD import are scene 15's block in Rhino; the unloaded link, the closed workset and the workset closed inside a link have no Rhino equivalent: the Windows trial |
| E | 20 (a house of parts in one group, the group moved) | Nothing in Rhino; Revit records it in the trial |
| G | 21 (picked from two), 22 (none), 23 (the picked lot deleted), 24 (an open property line), 25 (it picked) | Several picked lines, and picked lines that don't close: Rhino picks one curve only; the Windows trial |
| H | 26 (a block holding only an empty solid; a shed holding a nested block of an empty solid: in Revit, a nested family that gives no geometry, since one holding only an empty solid takes no room and is read as nothing) | A building-category family with no Fine geometry (Rhino sends an empty Building-layer solid as `open_solid`, Revit `not_a_solid`: no shared expected answer) and a wall whose family holds an empty solid: the Windows trial |
| C, D, I, J, K | none | Host-only (section 7's opening): the Windows trial, or for I a live Rhino recording (the reference adapter reads no terrain or finished spots) |
| F | none | Ben's decision on the "wholly inside" rule |

Found on running: a house drawn as parts with no floor marks, 20 ft tall, has stories needing review (the drawing
allows 1 or 2, `measure._stories_whole`), where the same house as Gordium's floor blocks complies. A native Revit
house will need its stories entered (or its floors marked) before that row can comply.

**Stories of a building drawn as parts (2026-11-21, the New York eval's Revit run).** Revit draws each floor and roof
as its own element, its top at its level and its thickness below, so an upper floor or a roof is a thin part that
starts above the ground, inside the walls in plan and often inside their height (106 Ithaca Rd: 35 ft walls, the roof
a 12 in slab at 34 to 35 ft). The measuring took it as a part that "may be another story" (`part_raised`), or as one
sunk into another (`parts_overlap`), so stories needed review for the wrong reason, one a stated count could never
clear. The law: "STORY — The portion of a building which is between one floor level and the next higher floor level
or the roof" (Chapter 325, §325-3B, p.19); the State's house code words it the same way ("STORY. That portion of a building included between the upper
surface of a floor and the upper surface of the floor or roof next above", 2025 Residential Code of NYS R202,
regulations/jurisdictions/new_york/new_york_state/4_term_definitions/definitions.yaml). A slab is a floor level or the roof that bounds a story, never the portion between,
and a part under 7 ft can hold no story (the lowest habitable ceiling, R305.1 as the measuring cites it, its STORY_ROOM). So, **Gordium's reading** (`measure._slabs_within`): a part that starts above the ground, is under 7 ft
tall, and lies in plan within the outer outline of the parts standing on the ground at least a story tall, lying wholly
within their height (its top no higher than their top), is a floor or roof slab: left out of the raised-part and overlap tests and of the count's
bounds (it held none). What it can't do: lower the most the building could hold (under 7 ft it held none), or clear a
part a story tall over the roof, a thin part reaching past the walls (a balcony), or one floating over them: each
stays a part that may be another story. The count is still read from the walls (1 to floor(height / 7 ft), "draw its
floors or enter the count"), so a native Revit model's stories still need review until the count is stated: the
`Gordium: Stories` mark on Project Information (2026-11-22; section 9) states it, as Rhino's lot facts state `stories`,
and the count stands only within those bounds. Walls drawn per
level (an upper story's walls starting at its level, a story tall) still read as a part that may be another story:
Revit's own Levels ("Building Story") would tell those apart, and are not read yet. Pinned by
`packages/model_measurement/tests/test_stories_slabs.py` and the eval's Revit-parts reading
(`apps/revit_addin/tools/tests/test_ny_eval.py`).

## 8. Left for the trial

Every "to check" above, plus: which category type Revit gives a linked model and a CAD import (the reader looks at
both whatever it is, so skipping one can't hide a house it holds); whether the curtain wall host has faces of its own; whether open shells come back as
solids; how property lines read in 2026; the shared-coordinates transform's direction and Revit's distance limit;
whether `DocumentChanged` reports joined neighbours; whether `ElementOnPhaseStatus` has the values section 1 needs;
how often real models need review only because of curved family details (Q3); how a component stair's and a
railing's parts (runs, landings, supports, top rails, handrails) are read, so a stair is part of the building and
neither left out nor unsent (Snowdon Towers has stairs).

**Answered in the trial (Revit 2027.4, 2026-11-19; every drawn scene recorded from Revit and passing).**

- *Nested families.* A nested family that isn't shared comes back inside its host's geometry (a nested
  `GeometryInstance`); a shared one is its own element, a sub-component, left out of its host's geometry. Decided:
  read as part of its host (section 1's row), the same reading Rhino gives a nested block, so a shed's empty part
  leaves the shed with no box instead of being a second object and the shed touching nothing (scene 26).
- *Detail level.* Decided and built: a family instance is read at Fine, as before, and also at Medium and Coarse
  (`RevitElement.CoarserGeometry`; families are where a part can be set to show at some levels only, so other
  elements are read at Fine alone). For a family off the building categories (and not marked a building with `Gordium: Site object is`,
  which is then a building part like a wall), the coarser geometry is read as part
  of it (`SiteReader.Coarser`): its box, footprint and definition can only grow, so a part drawn only at Coarse is
  never missed; it never gives a place to a family with no face at Fine, which keeps no box (touching unknown). A
  building's faces are still sent from Fine alone (the real shape); its box takes the coarser geometry too, and a
  building whose coarser drawing doesn't repeat its Fine one (a point or a face Fine doesn't have: a part beyond
  Fine's box, or inside it but off its solids) gets a problem saying it may be bigger than measured (`tool_words`;
  a simpler coarser drawing is flagged too, which only asks for review). A part nested in a building adds its
  coarser drawing to that test, never to the building's faces. A nested family that draws nothing at a coarser
  level adds nothing (it is read from Fine). Tried in Revit 2027.4 (`DetailCheck`, 2026-11-19): a Generic Model family holding a 4 ft box shown
  at every level and a 2 ft box shown at Coarse only reads one solid at Fine and both at Coarse; read at Fine alone
  its footprint ran x 0 to 4 ft, read as built x 0 to 12 ft. Reader pins: `A_part_drawn_only_at_a_coarser_detail_level_is_never_missed`.
- *Scene 18 drawn from DirectShapes.* Its walls, slabs, window, curtain panel and mullions are DirectShapes in those
  categories (the roof a closed mesh), not native walls, floors, a roof, a window family or a curtain wall: they
  test the reader's sorting by category and its reading of a closed mesh, not what Revit gives for native elements
  (wall joins, a window's cut, a curtain wall host's own geometry). Native elements stay open: **new scene A** is
  answered for categories, not for native elements, and the curtain wall host's faces stay "to check".
- *In-place families.* Revit's API can't create one, and inside the in-place editor no add-in code runs (no
  Idling event; every add-in button is greyed). Scene 18's built-in was made once by hand in a source model and
  is copied into each scene model (`InPlaceSource`, `SceneDraw.CopyBuiltIn`); it reads by its category (Walls)
  like any building part.
- *Closed meshes.* A `TessellatedShapeBuilder` mesh comes back as a `Mesh` that says it is closed (scene 18's
  roof: 12 triangles, closed), so no `open_mesh` is sent for it.

**Words.** The problem codes stay the same for every host (the conformance suite compares them), but some of their
sentences are Rhino's: `lot_not_found` says "the Site layer", `no_lot_outline` and `several_lot_outlines` say "on
the … layer", `not_a_solid` says "explode it". Host-neutral wording for those is a change to
`model_measurement/stops.py`, its own PR, before the Revit add-in is used on a real project.

## 9. Check my project: the architect's own model, one check

**What it does.** One button, *Check my project*, checks the open project: the outside (this note: `RevitRead`,
then `SiteReader`) and the inside (the [interior note](revit_interior_reading_design.md): `RevitInterior`, then
`InteriorReader`), read one after the other from the same document, sent as **one** `check_site` with the site, the
lot facts and the `interior`. The two reads must name the same phases and design options (the last phase; each
set's option being edited, else its primary), or nothing is sent. Code: `ProjectCheck.cs`, `ResultRows.cs` and
`ResultText.cs` in `Gordium.Revit.Reading` (tested on fake records against the real worker: scene 01 with interior
houses 1 and 5), `CheckProject.cs` and the results panel (`ResultsPane.cs`, `ResultsView.cs`, `PanelActions.cs`)
in the add-in. **Decided (Ben, 2026-11-20, "go with your recommendations").**

**The lot facts are Gordium marks on Project Information**, added by the button's first run (or Mark for egress),
read by GUID like every mark; unset is not stated:

| Mark | Sends | If unset |
|---|---|---|
| `Gordium: Zone` (text) | `zone`, as typed: the district exactly as the architect typed it. An address lookup's suggestion is never sent in its place (v1 has no lookup) | nothing is sent |
| `Gordium: Use` (text) | `use`, Gordium's word (`one_family_detached`); a word the district doesn't list makes the use row need review | nothing is sent |
| `Gordium: Lot surveyed` (Yes/No) | `lot_surveyed` | nothing is sent |
| `Gordium: Street edge` (text, written by Gordium) | `street_line`: the lot's own edges | asked for by a pick; else nothing is sent |
| `Gordium: Corner lot` (Yes/No) | `corner_lot` | not sent: the yards need review |
| `Gordium: Ground from` (text: Spot grades / Finished spot grades) | `grade_from`, the ground from Gordium's spot-grade markers (section 5) | not sent: no ground, so height and stories need review. A Toposolid isn't read for zoning yet (no terrain code), so a Toposolid ground always needs review (the interior reader reads one at each window, a door's not yet: `Gordium: Toposolid is finished ground`) |
| `Gordium: Stories` (whole number, Revit's Integer; added 2026-11-22) | `stories`, the architect's count for the whole building, as Ithaca's STORY counts it (§325-3B: "The portion of a building which is between one floor level and the next higher floor level or the roof"; a basement counts when "the finished surface of the floor next above is 1) more than six feet above grade plane or 2) more than 12 feet above the finished ground level at any point", "A cellar shall not be deemed a story", a mezzanine is not one, nor an attic "if unfinished and without human occupancy"; §325-8A: "computed at the main entrance side"): the mark's tooltip says so. Optional, never required. The measuring keeps it only within what the drawing allows (section 7, "Stories of a building drawn as parts": never fewer than the floors drawn, never more than the walls could hold at 7 ft a story), and the measuring records it so ("stated by the architect for the whole building, within what the drawing allows (1 to 5: ...)"), which the results panel shows as "3 stated by the architect, ≤ 3 allowed" (never "measured": `CheckItem.Stated` reads the worker's record of the row's measure); a count outside that is refused there (needs review, with why). A count under 1 is asked again, nothing sent | not sent: the count is read from the drawing, and where the drawing allows more than one count the stories row needs review ("draw its floors or enter the count") |

`jurisdiction` is fixed to the City of Ithaca (`regulations/jurisdictions/new_york/ithaca_city`). A required fact
(the checker's own list, `host_core.facts.REQUIRED`) missing and **no request is sent**: the results panel lists
exactly which mark to fill in and how.

**The street edge is picked, not typed.** The button asks "click the lot edge along the street" on the property
line (Esc when done; several edges for a frontage drawn in pieces). Revit highlights the whole property line, never
the edge a click lands on, so a click near a corner is **refused** and says so: when the two nearest edges are within
0.5 ft of each other (half the 1 ft pick reach), or the click is within 2 ft (a quarter of a shorter edge) of an end
the edge shares with another. Otherwise the nearest edge is **said back for a Yes** before it is kept: "Use the 60.0 ft
lot edge from (x, y) to (x, y) as the street line?" (shared coordinates; a curved edge by its length along the
curve, "the curved 47.1 ft lot edge ...", never its chord); No forgets the click. Every result's *Checked* line names
the street line it was checked against, in the same words. The mark is written through one helper for every Gordium
mark write (the pick's and a request file's): when Revit's `Parameter.Set` says it didn't set the value, it stops
naming the mark, nothing is checked, and nothing is logged as kept. The edge is kept as its two ends in Revit's **internal**
coordinates, which don't move when the shared coordinates are set again (an edge index was rejected: redrawing the
property line renumbers its edges silently). At each check the kept ends are turned into shared coordinates and
matched to an edge of the lot read (within 0.01 ft); `street_line` is then that edge's own first and last points,
exactly as the site description has them. With the ends the mark keeps whether the edge is straight and its point
halfway along (`x1 y1 x2 y2 line|arc mx my`), and only the lot edge whose ends, kind and middle (within 0.25 ft) all
agree matches, so an arc and its chord (same ends) never match each other; an older mark with the ends alone that
matches two lot edges is refused. An edge the lot no longer has (the property line redrawn), or one matching two,
is never sent: its typed reason (`StreetRefusal`, `StreetEdges.NeedsNewPick`) has the button ask for the edge again
at once, as its message says (a request file has no pick: the message says to give the mark again). With no lot
read at all, the kept edge is sent as it is, named without a length, and the check says there is no lot: the lot's
rows need review, so the check never complies.

**The results panel** (replacing the first version's TaskDialog, as the design doc's "Results panel: first mockup"
agreed). A Revit dockable pane, *Gordium* (titled *Gordium: Check my project* until the ribbon pass), tabbed behind Properties on first use (`ResultsPane.cs`,
`ResultsView.cs`, plain WPF). One Revit-free row model, `ResultRows` (`ResultRows.cs` in `Gordium.Revit.Reading`),
makes every row's words, and both the panel and `check_project_result.txt` (`ResultText`) read it, so the two
never say a row differently.

- **The results list** (PR 3 of `ui_design_pass.md`, `ResultsList.cs`; its decisions in `ResultList.cs`, tested
  without Revit). Pinned at the top: the header (title, *Check again*, when and which project, one status line) and a
  compact toolbar (the filter chips, the search, "Showing N of M"). Under it the list, a virtualized `ListBox` (only
  the rows on screen are made, so 1,000 rows stay instant), its own scrolling, whose first entry is the summary
  (`ResultList.WithSummary`, in `ResultRows.Layout`'s order: the stale notice when there is one, the state, the count
  chips one wrap line per law), never selected or moved to; what wasn't read and a folded *Details* (phase, options,
  street line, files) after the rows. The Revit trial (106 Ithaca Rd, pane docked at about 340 by 430 px) showed a
  pinned summary filling the whole pane, the list getting nothing; it now scrolls away with the rows. Each row: its
  glyph and name with the row's whole width (a section beside it squeezed the name to a word a line), its figures in
  full, wrapped (never cut: the limit and how far off are a failure's most important words) or its short cause (two
  lines at most), then its section on its own line (trimmed, the whole on hover) with *Show*.
- **Never a stale pass.** Revit's `DocumentChanged` on the project checked, for any change but the check's own
  committed transactions (adding the marks, keeping the street edge), and for every undo or redo whatever its
  names (the event's `Operation`: `ResultRows.ChangesTheCheck`), greys everything
  (`ResultRows.Stale`: no green in the state, chips, groups, lines or rows) and says "The model changed since this
  check (14:32): click Check again". `DocumentClosing` of it takes the rows down.
- **Header and counts.** "Gordium", when it was checked and which project, and *Check again*.
  Then the worker's own state, and its counts as **chips in its own words, never recounted**: one line per law
  (`view.sections[]`: "Zoning (City of Ithaca)", "Egress (NY State Residential Code 2025)"), each summary split at
  " · " ("4 do not comply", "5 to review", "4 comply", "10 parts not read yet"); when the sections can't be read,
  the whole summary. A chip is red only for "N do(es) not comply" and green only for exactly "N comply"/"N
  complies"; anything else is amber, so no chip is ever kinder than its words. Then the phase, design options and
  street line checked.
- **Worst first** (`ResultList.Place`): every row in exactly one of four places, by its own verdict as the add-in
  reads it (wherever the worker grouped it): *does not comply* (largest how far off first, read from the worker's
  words only when they state a shortfall or excess as a length; the rest in the worker's order), *needs review*
  (the worker's tier 2, in its order), *check by hand or not checked* (the worker's tier 3, `<law>:by_hand`, and
  zoning's not checked), then *complies* / *not applicable* (titled by what it holds, folded). Only that last place
  is ever folded, and never while a filter or a search is on (a match is never hidden). Within a place a run of
  rows of one worker line or group always has its own sub-heading, so no run reads as more of the one before: the
  line's own title (which may count its rows) only in the place the worker's tier puts the line and only when all
  its rows are there; otherwise a name that claims no count or status (the part, "Window 2"; the law, "Egress";
  "Zoning"; a law still waiting for rooms, its law's name). A row the add-in reads more cautiously than its line
  moves to its own place under its part's name, never the line's words. The list's keys act only on a row (Space on the *Details*
  fold's header opens it, never zooms). **No row is ever cut.** A
  reason repeated per building is said once with its count ("(x12)").
- **Filters and search** (`ResultList.Layout`): chips all / does not comply / needs review (with check by hand and
  not checked) / complies; the search matches every word in a row's name, its section or its elements' labels
  (never a UniqueId). "Showing N of M rows" when narrowed. The chips have no numbers: the worker's counts (the count
  bar) count what an architect counts (a window's 14 rules as one line), the list counts rows, so a number on a
  chip would read as a recount.
- **Each row**: its verdict (a status word the add-in doesn't know is "needs review (the checker said ...)", amber),
  its name, its **figures** and **how far off**, its reason, the law's **section**, and a **Law** expander with the
  rule's exact quotes and where each is (the answer's `detail.quotes`, else `code.quote`: the check_site answer
  already carries them, so no protocol change). How far off is **only the worker's own words**: a zoning row's
  `delta` ("2'-6\" short", "up to 2'-9\" over", "+1,200 sf"; worked out by the worker over every reading, never
  overstated), or its `margin` from a worker that sends no delta; an empty delta says nothing. An egress row carries
  neither, so it shows the figures its reason states ("net clear height 20 in, needs ≥ 24 in") and **no margin is
  worked out**: the figures are the worker's rounded numbers, and their difference could misstate the law.
- **Click a row** (or Up/Down): it is selected, and its elements (a zoning row's `objects`, an egress row's
  `part.id`: Revit UniqueIds) are selected in Revit **without moving the view** (`Selection.SetElementIds`), so
  Properties follows the panel; a row naming no element clears Revit's selection. **Show** (or Space) also zooms
  (`ShowElements`). Enter or a double click opens the row's **detail** in place of the list (UI PR 4,
  `Details` in `ResultDetail.cs`): why (the worker's reason), what to do (the worker's own advice first, its `hint`,
  then by the row's place, ending with Check again; nothing for a row that complies, only Check again once stale),
  the figures against the limit and how far off in the worker's words, the law's words with *Open the law* (the
  worker's `detail.cited` links), and its elements by the names architects use (`ElementNames`: "CLOSET (40)",
  "Door D06"; Revit's id only when nothing else names one); every number it shows is in the worker's item or an
  element's name (`DetailTests`); Ctrl+C
  copies the row as `check_project_result.txt` writes it (once stale, with when it was checked). It says
  plainly when it can't: that project closed or not the active one, or an element not in the model now (deleted, in
  a linked model, or an area Gordium read from the walls).
- **Fixes in place, v1.** Nothing sent because a Project Information fact is missing: the panel lists each, with
  *Open Project Information* (Revit's own command) and *Check again*. Setting an element's egress marks stays in
  Properties for now (the row click selects the element, so its marks are there): editing marks from the panel
  means a transaction per edit and checking each value's kind, kept for when the mockup's "Confirm this type"
  is built.
- **Revit's thread.** Every Revit call the panel makes (Check again, select and zoom, open Project Information)
  goes through **one ExternalEvent** made at startup (`PanelActions.cs`) and runs in Revit's API context; the WPF
  view never calls the Revit API, and each element's label is read when the check runs. A request Revit refuses
  is taken back off the queue (`ActionQueue`: never run later, unasked, with the next one) and Check again is
  usable again. A re-check that fails takes the last check's rows down (never left showing as this one's) and
  says why.
- **The street edge is asked for last, where it can be clicked** (Revit trial: from a sheet view with nothing set,
  the pick waited with no prompt). Only when it is the one fact left and the active view is a plan showing a
  property line (`StreetEdges.Ask`), with the status bar saying "Click the lot edge along the street (Esc to
  skip)"; otherwise the panel lists "open a site plan (or a floor plan) that shows the property line, then click
  Check again".

Every row is also written to `check_project_result.txt` (in full, the same words), and the full request and answer
to the trial log.

**No clicks.** `check_project_request.json` (`{"model": "<path>.rvt", "marks": {"Gordium: Zone": "R-1b", ...}}`,
`marks` optional) in the trial folder: the model opened, the marks given set (each by its own kind: a Yes/No mark
needs true or false, a text mark text; anything else stops the run naming the mark), checked as the button does (no
pick: the log's `lot_edges_internal` lists each property line's edges in the Street edge mark's own words, internal
coordinates, to copy one), logged, its rows written to `check_project_result.txt`, closed unsaved. It never opens
or needs the results panel. A reason the worker repeats per building is shown once with its
count ("(x12)").

## Where the decisions are written

Every decision above that a Revit model doesn't have to be open for is code in
`apps/revit_addin/src/Gordium.Revit.Reading/` (plain C#, no Revit types), tested on the Mac against the real worker
with each drawn conformance scene drawn as fake Revit records ([its README section](../../apps/revit_addin/README.md#the-readers-logic-gordiumrevitreading)).
The trial writes only the layer that fills its records from the API, and confirms each "to check". Two choices the
code makes, for Ben to confirm: one departs from what this note first said (section 2 had null geometry `unsent`
for every element), one it didn't spell out. An element that is not a building part (not a building category, a floor block, or marked a building with `Gordium: Site object is`) whose
geometry Revit returns as null is skipped (nothing that could be a building; one whose reading throws, or that holds a kind of geometry the reader
doesn't know, is still `unsent`, a family, a CAD import and a Toposolid too, and a building part with null geometry is `unsent`, never skipped; a coordination model, which Revit gives no geometry for though it may hold a building, is left out as a linked model whose contents aren't known, so it counts even with no lot; inside a
linked model such an element leaves the link with no box: left out and touching), so a model element that simply has no shape (one Revit gives no geometry, outside the categories and families above) doesn't make every check need review; and a building whose nested
family gives no geometry gets a `tool_words` problem (it may be bigger than measured). Found while writing it: on a
model turned to true north by 30°, Revit's own box of each element, square to its internal axes, is bigger once
turned into shared coordinates, so objects well apart from the house read as touching (scene 15's context solid, 15 ft behind it, does) (the cautious side;
scene J must be hand-worked with this in mind).

## Sources

Autodesk's Revit API reference (2026, API 26.4), fetched 2026-11-09:
[Element.Geometry](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/d8a55a5b-2a69-d5ab-3e1f-6cf1ee43c8ec.htm),
[Options](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/aa41fc13-9f81-836c-4271-82568ba5d7e8.htm),
[Options.DetailLevel](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/887c4c25-fe14-2633-b84c-09d2f1279c9e.htm),
[GeometryInstance.GetInstanceGeometry](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/22d4a5d4-dfc2-7227-2cae-b989729696ec.htm),
[Face](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/e32b3b1f-66fc-57cb-6e1c-aa81d1bf3e63.htm) (its six face types, `GetEdgesAsCurveLoops`, `Triangulate`),
[PlanarFace](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/e5f08848-bd35-4b17-ac7b-ae39fd817d6d.htm),
[Element.UniqueId](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/f9a9cb77-6913-6d41-ecf5-4398a24e8ff8.htm),
[UnitUtils.ConvertFromInternalUnits](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/60c6aac3-8306-c56e-b62f-b7011b9ad7b6.htm) and the developer's guide on [units](https://help.autodesk.com/cloudhelp/2018/ENU/Revit-API/Revit_API_Developers_Guide/Introduction/Application_and_Document/Units.html) (lengths in feet),
[BasePoint](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/154074ae-d653-aaff-b84b-6336a1cbafaa.htm),
[ProjectLocation.GetProjectPosition](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/45724712-d710-eb12-5a48-63a31a54f09f.htm),
[Instance.GetTotalTransform](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/8c8aff2b-5ff9-e43a-3b5c-308cd0174f1f.htm),
[Toposolid](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/7516b682-d489-a462-47ab-192c63d1d9e4.htm),
[Family.IsInPlace](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/eb138fd5-6092-5257-e6e1-073013cb8582.htm),
[Wall.CurtainGrid](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/7d46f445-4739-1877-c9de-e04787d7257b.htm),
[RevitLinkInstance.GetLinkDocument](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/6f81c365-15d9-06b8-48ef-df84914fec60.htm),
[Workset.IsOpen](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/62545a89-c7cd-e8b4-2282-ba4a4c909ff0.htm),
[Element.DesignOption](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/5c20fe58-e301-6ddb-3438-666db5c586ee.htm),
[DesignOption.GetActiveDesignOptionId](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/d0b47e58-a5fc-9424-a94c-2428b4ec4d16.htm),
[ElementPhaseStatusFilter](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/7767020a-2564-2c46-689d-59c2abe6e777.htm),
[ElementOnPhaseStatus](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/bfc481cc-11c8-de0b-1d71-7b2ffa711780.htm),
[DirectShape](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/bfbd137b-c2c2-71bb-6f4a-992d0dcf6ea8.htm),
[Application.DocumentChanged](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/988dd6cf-fcaa-85d2-622d-c50f13917a13.htm),
[DocumentChangedEventArgs](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/8fd170b2-df48-209b-438e-54ec7b01b664.htm),
[ExternalEvent](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/05089477-4612-35b2-81a2-89c4f44370ea.htm);
and for 2027, [API: Expose Property Line API](https://help.autodesk.com/cloudhelp/2027/ENU/Revit-WhatsNew/files/GUID-DC8BFD57-09A4-4792-995C-AECA5855D1B4.htm)
(`PropertyLine.GetBoundary`, new in 2027; before, the class had no members of its own). Everything else said about
Rhino's reader was read from the repository files named beside it.
