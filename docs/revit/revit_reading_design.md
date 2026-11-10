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
is** (the same tests as Rhino's `rhino_logic.could_be_building`).

**Which elements are looked at.** Every element of the open document (`FilteredElementCollector(doc)`), never a
view's collector: an element hidden, isolated, cropped or in a hidden category still counts, as Rhino counts hidden
and locked objects ("a hidden shed still counts", `gordium_rhino._not_included`). Each element's `layer` in the
description is its category name (`"Walls"`), and an unsent one's `kind` says what it is (`"a linked model"`); both
are for the architect's reading only (proposed).

| Revit element | Sent as | Rhino equivalent | Scene that tests it |
|---|---|---|---|
| Proposed building categories: walls, floors, roofs, columns (architectural and structural), stairs, railings, ramps, doors, windows, curtain wall panels and mullions. Left off on purpose for the first reader, so they fall to the "any other element" row (left out, and usually touching: the cautious side): structural framing and foundations, ceilings, roof fascias, gutters and soffits, wall sweeps, slab edges, casework | `buildings`: one per element, id its `UniqueId`, faces of all its solids | A solid on the Building layer | 01 (as floor blocks); native elements: **new scene A** |
| Gordium's own floor blocks (drawn by `start_site`; proposed: DirectShapes carrying a Gordium mark with `"<story>;<height>"`, as Rhino's `gordium:floor` user text) | `buildings`, with `floor` = the height drawn | Floor blocks on `Gordium::Massing` | Every drawn scene: each expected building is a floor block with `floor: 10`, so every scene's house (02's curved one and 03's open one too) is drawn as marked floor blocks, built from real solids (`GeometryCreationUtilities` or `BRepBuilder`, never a faceting builder that would turn 02's curve into flat faces: **to check**) |
| Curtain wall (the host wall itself) | Proposed: its panels and mullions are their own elements (row 1); the wall sends its own faces only if it has any (**to check**: whether a curtain wall's own geometry is empty, so no face is sent twice) | | **new scene A** |
| In-place family | Proposed: by its category, like the building-category row or the "any other element" row (`Family.IsInPlace` only names it in the panel) | | **new scene A** |
| Model group | Proposed: never itself: each member element is read on its own (a group has no geometry of its own) | | **new scene E** (ids after editing a group) |
| Any other element with a Revit `Solid` with faces (closed or not) or a mesh of more than 4 faces (generic models, masses, site, planting, specialty equipment, furniture) on the lot | `left_out`, `could_be_building: true` | A solid on the Default layer | 05 (garage), 15 (porch); the recorder draws these as Generic Models |
| A loadable family instance off the building categories, whatever its geometry (even none at Fine detail) | `left_out`, `could_be_building: true`; with no box, `touching: null` | A block on another layer: Rhino counts every block, whatever it holds | 15 (`shed_block`); empty: **new scene H** |
| Gordium's own neighbourhood objects (proposed: marked DirectShapes, as Rhino's `Gordium::Context`) | `left_out`, `context: true` | A solid on `Gordium::Context` | 15 (`neighbour_solid`) |
| Proposed: a linked Revit model, wherever it is placed (Rhino reports such a block wherever it is, with no lot test), that holds any building-category element at any depth of links inside links (as `_block_holds`), or has a closed workset of its own (its hidden part could hold the house; **to check** that the API says so) | `unsent`, kind `"a linked model"`, `not_a_solid`: every building measure needs review | A block holding Building-layer objects (`read_3dm._block_holds`) | 04 (the shed drawn as a linked model); **new scene B** |
| Proposed: a linked model with no building-category element at any depth, or a 3D CAD import (`ImportInstance`), reaching into the lot | `left_out`, `could_be_building: true` | A block on another layer | **New scene B** (scene 15's block is already the family instance above) |
| A link that isn't loaded, including a link nested as an overlay (not loaded in the host: **to check**) | Can't be looked inside: `inventory_complete: false` | | Verdicts only: 14 (never drawn); the mapping: **new scene B** |
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
| Geometry | Proposed: `Element.get_Geometry(new Options { DetailLevel = Fine })`, no view set (so it doesn't depend on what a view shows), `IncludeNonVisibleObjects` false. A family's `GeometryInstance` is opened with `GetInstanceGeometry()` (already placed in the model). Fine, never Coarse: a coarser level can leave real parts out (**to check** on real families) | rhino3dm's Breps | 01 |
| A face | A `PlanarFace` whose every edge is a `Line` is sent: its loops from `GetEdgesAsCurveLoops()`, each curve's start point, the outer loop as `points`, the others as `holes` (which loop is outer: **to check**; proposed the largest in the face's plane) | `_brep_faces` | 01, 10 |
| A curved face | Any other face type (`CylindricalFace`, `ConicalFace`, `RuledFace`, `RevolvedFace`, `HermiteFace`) is left out and the element gets `curved_surface`. `Face.Triangulate` is never called | `curved_surface` | 02 |
| A flat face with a curved edge | Left out; the element gets `curved_edge` | `curved_edge` | 02 |
| An empty solid | A solid with no faces (Revit families often hold some) is skipped: it has nothing to send | | **new scene H** |
| An open solid | A solid with faces and an edge that has only one face (`Edge.GetFace(1)` null): `open_solid` with `what` the element's name (**to check** that Revit gives open shells as solids, and that `GetFace(1)` behaves so) | `open_solid` | 03 |
| A mesh in an element's geometry | Its triangles as faces, with `open_mesh` unless the mesh is known to be closed (**to check** whether Revit can say) | `_mesh_faces`, `open_mesh` | **new scene A** |
| Anything else in the geometry (an object type that is not a solid, mesh, curve, point or family instance), or reading the geometry fails (`get_Geometry` returns null or throws) | The element is `unsent`, `not_a_solid`, kind its category | `not_a_solid` | 04 |
| Curves and points in an element's geometry | Skipped (as `read_3dm` skips curves and points) | | 01 |
| A building-category element with no face to send at all (for example a family whose solids show only at Coarse detail) | Never skipped: `unsent`, `not_a_solid`, kind `"a <category> with no geometry"`, so every building measure needs review (Rhino sends an empty solid on the Building layer as a building with no faces and `open_solid`) | `read_3dm.read_site` | **new scene H** |

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

**The lot outline.** Rhino's lot is the one closed curve on the Site layer, or the one picked (`lot_id`).

| Case | Revit reader | Scene |
|---|---|---|
| The architect picked the lot (the default flow) | The picked property line, or the picked lines forming the loop, in the order they run; `lot_id` saved in the facts | **New scene G** (no scene's facts carry a `lot_id` yet) |
| Nothing picked, one property line | That one | 01 |
| Nothing picked, two or more | `lot: null`, `several_lot_outlines` (count, layer `"Property Lines"`) | 09 |
| Nothing picked, none | `lot: null`, `no_lot_outline` | **new scene G** |
| The picked lot no longer there | `lot: null`, `lot_not_found` | **new scene G** |
| A straight piece | One lot line: its two ends | 01 |
| An arc (or any curved piece) | Points along it at most 0.25 ft apart (at least 16), `curved: true`, never its chord (as `read_3dm._edges`) | 17 |

Reading a property line's boundary: `PropertyLine.GetBoundary()` exists only in the Revit 2027 API. In Revit 2026
the reader takes the property line's curves from its geometry (**to check** that `get_Geometry` gives them, and that an arc comes back as an `Arc`, never already broken into
straight pieces: scene 17 would catch it), or the architect picks the lines themselves.

**On the lot and touching** (the same rules and numbers as Rhino's `_not_included` and `_touching` in
`apps/rhino_plugin/gordium_rhino.py`, which use `rhino_logic.reaches_into_lot` and `box_near_lot`; the box test
itself is written inline there and in the reference adapter. Proposed: these decisions become one host-neutral
function in `host_core`, served as a worker session command, so the C# add-in sends each candidate's plan points
and boxes and never keeps a second copy of the logic):

| Question | Rule (unchanged from Rhino) | Revit input | Scene |
|---|---|---|---|
| On the lot? | Its plan footprint reaches more than 0.1 ft into the lot (`reaches_into_lot`) | As Rhino's `_plan_points`: the element's vertices, points along its edges (`Edge.Tessellate`) and a 7 × 7 grid of points over each face (`Face.Evaluate` over the face's own range: **to check**), so a dome's bulge counts; used only for this, never sent as faces; its box corners when it has no points | 05, 15 |
| Touching? | Its 3D box within 0.1 ft of any building's box, or of the box around all the buildings together (proposed: a floor block's box holds the whole storey in Rhino, so anything inside the house touches; a single wall's box doesn't, so without this an object hung in the middle of a room would not count) | The box around the points the reader actually read (section 2 and the row above) and `Element.get_BoundingBox(null)` together, so it is never smaller than the geometry; turned by its 8 corners as in section 3, both boxes in shared coordinates | 15 (porch), 16; inside the house: **new scene A** (a loft drawn as a Generic Model, touching no wall or slab) |
| Not known | No box or no points: listed as on the lot with `touching: null` (counts as touching), never skipped. This is the reference adapter's rule (`conformance_rhino._left_out`); the live Rhino command can drop an object with no box altogether (`_not_included` finds it nowhere near the lot), a gap to fix there | | **new scene H** |
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
| G | Two property lines and facts with a `lot_id` picking one (also as several picked lines); no lot outline; the picked lot then deleted | The picked-lot flow, `no_lot_outline`, `lot_not_found` | No (the lot then needs review) |
| H | An empty family instance on the lot; a building-category family with no Fine geometry; a wall whose family also holds an empty solid | `touching: null`; `unsent` | Yes |
| I | Spot grades and finished spots together; a Toposolid under a house of native walls, picked as the ground, higher inside the house than outside | `finished_spots`, `terrain`, probes outside the walls only | Yes (height) |
| J | Scene 15 on a model with survey coordinates and true north turned 30° | Boxes and points turned without shrinking; the box filter in the right coordinates | Yes (touching; left-out objects dropped) |
| K | Scene 01, then the survey point's elevation moved 10 ft | Facts entered under other coordinates aren't used | Yes (height) |

## 8. Left for the trial

Every "to check" above, plus: whether the curtain wall host has faces of its own; whether open shells come back as
solids; how property lines read in 2026; the shared-coordinates transform's direction and Revit's distance limit;
whether `DocumentChanged` reports joined neighbours; whether `ElementOnPhaseStatus` has the values section 1 needs;
how often real models need review only because of curved family details (Q3).

**Words.** The problem codes stay the same for every host (the conformance suite compares them), but some of their
sentences are Rhino's: `lot_not_found` says "the Site layer", `no_lot_outline` and `several_lot_outlines` say "on
the … layer", `not_a_solid` says "explode it". Host-neutral wording for those is a change to
`model_measurement/stops.py`, its own PR, before the Revit add-in is used on a real project.

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
