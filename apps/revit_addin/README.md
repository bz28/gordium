# Gordium in Revit: the worker client

**Purpose:** the C# library the Revit add-in uses to start Gordium's checker and talk to it, what it does when something goes wrong, and how we know it works.\
**For:** engineers writing the Revit add-in; reviewers checking that nothing the checker sends can turn into a pass it didn't give.\
**Kept current by:** every PR that changes these libraries or a protocol command they send.

Gordium's checker is Python. Revit add-ins are C#. So the add-in runs the checker as its own process, the
**worker** (`python -m design_checker serve`), and sends it one request per line, as the
[worker protocol](../../docs/protocol/worker_protocol_v1.md) says. Why it works this way, rather than any other way
into Revit: [the decision of 2026-11-06](../../docs/decisions/2026-11-06_hosts_talk_to_the_worker.md).

This folder holds the half of the add-in that doesn't need Revit: `Gordium.Worker`, a class library that starts
the worker and speaks the protocol. It references no Revit API and no packages (only System.Text.Json, part of
.NET), so it is built and tested on the Mac and in CI. It is built twice, for .NET 8 and .NET 10, and every test
runs on both. Revit 2027 runs on .NET 10 (Autodesk's Revit 2027 "What's new",
[Migrating Revit to .NET 10](https://help.autodesk.com/cloudhelp/2027/ENU/Revit-WhatsNew/files/GUID-8D7A4715-EAF8-4BD1-BE78-061F900D0BCE.htm)).
Revit 2025 and 2026 are built on .NET 8 ([Autodesk's call for preview testing](https://blog.autodesk.io/call-for-preview-testing-revit-2026-2025-migration-to-net-10/),
2026-04-29), and a .NET 10 build can't load on .NET 8, so the Nov 5 plan of one .NET 10 build for both doesn't hold
for Revit 2026 as it first shipped. The same post says Autodesk plans to move Revit 2025 and 2026 to .NET 10 (a
Revit 2026 preview was tested until 2026-06-03; no release date given), so which runtime the installed Revit 2026
uses is checked in the Windows trial. The refusal of a key given twice
in an answer is the library's own (`StrictJson.RefuseDuplicateKeys`), one code path for both: .NET 10's built-in
switch doesn't exist on .NET 8, and a .NET 10 test checks ours says the same as it on every case. Beside it is
`Gordium.Revit.Reading`, the reader's decisions (below). The add-in itself, `Gordium.Revit.Addin` (the ribbon
buttons, and later the thin layer that fills the reader's records from the Revit API), is built during the
[Windows trial](../../docs/revit/windows_trial_runbook.md): see [The add-in in Revit](#the-add-in-in-revit-windows-only).

## What it does

```csharp
using var worker = await WorkerClient.StartAsync(new WorkerOptions
{
    PythonPath = @"C:\gordium\.venv\Scripts\python.exe",   // the clone's venv
    WorkingDirectory = @"C:\gordium",                       // the clone: the worker reads its rulebooks
});
var result = await worker.CheckSiteAsync(site, facts);     // site: a gordium.site/1 description
foreach (var group in result.Groups)                      // the panel's headings, as the Rhino panel shows them
    foreach (var id in group.Items)
        Console.WriteLine($"{group.Title}: {id}: {result.ById()[id]}");
// Complies, DoesNotComply, NeedsReview, NotChecked, NotApplicable (a word the add-in doesn't know: NeedsReview)
```

1. **Starts the worker and says `hello`.** A worker that doesn't speak protocol 1.x, or reads a site description
   other than `gordium.site/1`, is refused (each side refuses a different major version). Every later answer's
   `about` is checked the same way.
2. **Sends one request per line,** UTF-8 without a byte-order mark (the worker refuses one) and in fact plain
   ASCII (any other character is written as a JSON `\u` escape, so no code page can change it), each with the next id,
   `"protocol": "1.3"` (a 1.0, 1.1 or 1.2 worker answers it too, all but what it doesn't have: `objects.left_out` is
   1.1's; a site description with a slab (`left_out[].slab`, 1.3's) a 1.2 or older worker refuses, never checks; `check_site`'s `interior`, the house's inside, is 1.2's, and the client sends one only to a worker whose
   `hello` said 1.2 or later, refusing with `WorkerVersionException` before sending anything otherwise: an older
   worker would ignore it and say egress waits, as if no rooms were drawn), and only the fields the caller gave (an
   optional field left null is not sent).
3. **Typed commands:** `HelloAsync`, `CheckSiteAsync`, `StartSiteAsync`, `ReadModelAsync`, and `SessionAsync` for
   the 20 session commands (the start box, the panel, the live check's decisions, which objects are left out), each
   answer read by name with `Get`; `LeftOutAsync` is `objects.left_out` with its fields typed. `StartSiteAsync` and `ReadModelAsync` give their result as JSON (a building's floors, a site
   description: no verdicts). `SendAsync` is only for a command a later 1.x worker adds: it refuses every command
   above, so a check's or a session command's answer is always read strictly. The older commands (`check`,
   `start`...) are Rhino's and are not sent.
4. **Reads every answer strictly.** The answer must be JSON, this request's id, `ok` true or false, with its
   `result` and `about`. A check's every row must have an id, a name, a group, a reason (text or null) and a
   status as text; a row given twice, a key given twice, NaN, or a check with no rows is an error.
   **The statuses** are the checker's five: complies, does not comply, needs review, not checked, and **not
   applicable** (`NotApplicable`: a rule the interior description sets aside by saying the house has none of a
   kind, "Not applicable: the description says the house has no ramps (A-2)"; PR #112). A row not applicable is
   shown with its reason, is counted as neither a pass nor a failure, and one that gives no reason is read as needs
   review. A status word the add-in doesn't know (one a later 1.x worker adds) is read as `NeedsReview`, never as
   anything kinder, and its own word is kept (`StatusWord`), as the Rhino panel's grouping does
   (`design_checker/grouping.py`: anything unknown is to review); an overall state other than complies, does not
   comply, needs review or not checked is needs review too.
   **The groups** (`Groups`) are the worker's own (`present.grouped`, PR #111): zoning's by status, then each
   law's tiers (does not comply, needs review, check by hand, complies) as lines, a not-applicable row on its own
   line in its law's folded "Complies" group, exactly as the Rhino panel lists them (`panel_words.list_tree`). Every
   row must be in exactly one group, and in a group with lines in exactly one line (else a row would be hidden), and
   a line is never read kinder than its rows. A
   check whose overall state says it complies must have its rows back that (every row the check counts complying: none
   failing, needing review, not checked or of a status the add-in doesn't know, whether waiting on a fact or not
   checked in this release; apart from the rules not in Gordium yet and the rules not applicable with their reason;
   no use detail waiting; at least one row complying), or it is refused. This is the
   worker's rule from Ben's decision of 2026-11-09 (`present.state`, PR #82, which merges before this library);
   the library enforces it again, so an answer from a worker without it (one saying "complies" beside a row not
   checked) is an error, never a pass.
   A session command's part that refused its input gives its words as a `PartRefusedException`; an answer not
   given is an `AnswerMissingException`. Never a default in place of a missing value, and a `Verdict` never set
   (C#'s default, or `GetValueOrDefault` for a row that isn't there) is `NeedsReview`, never `Complies`.
5. **Stops the worker when it can't trust the next line:** a timeout (60 s; 120 s for `start_site`, the Rhino
   plugin's own limits, for sending the request and its answer together), a cancel, an answer it can't read, or
   the worker ending. A late answer would otherwise be
   read as the next request's. After that every call throws `WorkerStoppedException`; start a new client (the
   worker keeps nothing between requests, so nothing is lost).
6. **A refusal is not a failure of the worker.** `"ok": false` gives a `WorkerRefusedException` with the worker's
   words (and its Python traceback if it crashed on the request); the worker keeps serving.

Anything the worker did or didn't answer is a `WorkerException`; a cancel is .NET's own
`OperationCanceledException`; a request the client won't send (a request's own field, a NaN, a command with a typed
method sent through `SendAsync`) is an `ArgumentException`, before anything is sent. In every case the add-in shows
the message and no verdicts.

## How we know it works

`dotnet test` (run in `apps/revit_addin`) runs against the real Python worker and a stand-in one:

- **Every conformance scene** (`test_data/host_conformance/`: 26 scenes, 29 steps): `check_site` with the scene's
  expected description and facts gives exactly the hand-worked verdicts, every row and no row more. The facts and
  verdicts come from the scene files through the conformance suite's own code (`scene_cases.py`), never retyped.
- **`hello`, an unknown command, bad facts, session commands** (a constant, a refused part, `want`, an unknown
  field), and **`start_site`**, on the real worker.
- **The worker killed mid-session:** a clear `WorkerExitedException` within seconds, never a hang or an answer.
- **Every way an answer can go wrong**, given on purpose by `fake_worker.py`: protocol 2.0, another site schema,
  a missing status, a row without its id, name, group or reason, no summary or state, a key twice, NaN, no rows, a
  row twice, a row in no group, in two, or in none of its group's lines, no groups, a check said to comply beside a
  row of a status the add-in doesn't know or with only rules not applicable, no `about` or a wrong one on a later
  answer, another request's id, text that isn't JSON or UTF-8, a crash, a hang, a worker that stops reading, a
  cancel. Each is an error and stops the worker.
- **Not applicable and unknown statuses**, from the stand-in worker with groups made by the worker's own grouping
  code (`present.grouped`): a row not applicable is read as `NotApplicable` with its reason, on its own line in its
  law's folded "Complies" group, and a check that complies beside it still complies; one without a reason, an
  unknown status word (row, line or overall state) are each read as needs review, a line is read as its most cautious row
  when its own word is kinder, and a failure, or a row read more cautiously than the worker said, is never folded: never a pass. (The real worker doesn't give a row not applicable yet: PR #112 adds it, and `check_site` doesn't
  carry an interior description yet.)
- **What is sent:** no byte-order mark, only ASCII bytes, one line per request, ids 1, 2, 3..., non-English text
  intact.
- **The protocol copy:** the session commands and their answer names equal the protocol document's command
  reference (a Python test keeps that equal to the worker's own table).

The main guards (the status words, the empty and repeated rows, a key twice, an escape or line that isn't whole text, the versions, `about`, the id, the
byte-order mark, a refused part, half an answer, stopping after a timeout) were each undone once to check that
their test then fails (the strict reading on both .NET 8 and .NET 10), and so were the guards of not applicable, of a status word not known, of the groups and lines, and of a failure never folded.

## The reader's logic: `Gordium.Revit.Reading`

The **reader** turns a Revit model into the site description (`gordium.site/1`, the same JSON the worker builds from the copied `.3dm` the Rhino plugin
sends: `check.py`, `site_json.legacy_description`), with every decision of the [design note](../../docs/revit/revit_reading_design.md). It has no Revit types at
all: it works on plain **records** of what Revit says about the model (`Records.cs`: each element's `UniqueId`,
category, kind, phase created and demolished, design option, workset, Revit's own box, its geometry as faces, edges
and meshes; the property lines; the worksets, option sets, phases and links; the turn into shared coordinates). The
Revit layer, written later on Windows, only fills those records from the API named beside each field; it decides
nothing. So the decisions are built and tested here, on the Mac.

1. **What is on the lot in the design checked:** the last phase (only what is demolished by then is gone), the main
   model and one option from every option set (the one being edited, else the primary). The panel must name both
   (`ReadResult.PhaseChecked`, `OptionsChecked`).
2. **Buildings:** each element of a building category, each Gordium floor block, and each element marked a porch,
   deck, landing, ramp, or garage, shed or carport with `Gordium: Site object is` (`SiteReader.IsBuildingPart`) is one building: its flat faces
   with straight edges are sent; a curved face or edge, an open solid or a mesh not known to be closed is reported,
   never sent as if it were flat. A building element with nothing to send is never skipped: it is sent as an object
   that couldn't be (`unsent`), so every building measure needs review.
3. **Left out:** every other solid or mesh, every family instance and CAD import not marked a building, whatever it holds (a nested family of lines only is skipped inside it, as at the top), every coordination model (its contents aren't read: on the lot and touching), Gordium's
   neighbourhood objects, a Toposolid. **Which of them are on the lot and which touch the house is the worker's
   decision** (`objects.left_out`, the one copy every host uses), never the reader's.
4. **Linked models:** one holding any building part (at any depth; `SiteReader.IsBuildingPart`) or a closed workset is not sent (every
   building measure needs review); one not loaded, or a closed workset in the model, means not everything was
   looked at (`inventory_complete: false`).
5. **The lot:** the lot picked, else the one closed property line; never an open one; arcs followed closely. A
   property line inside a linked model makes the lot need review (`lot_block`): the lot may be the link's.
6. **Coordinates:** every point turned once into shared (survey) coordinates; a box turned by all 8 corners.
   Units are always feet (Revit's own).

How we know it is right (`tests/Gordium.Revit.Reading.Tests`, run with the rest by `dotnet test`):

- **Every drawn conformance scene (24 of the 26; 13 and 14 are descriptions only) drawn as fake Revit records**,
  the way the trial would draw it in Revit (`SceneDrawing.cs`: floor blocks as marked DirectShapes, the lot as a
  property line, the shed of scene 04 as a linked model, the block of scene 15 as a family instance, the survey
  scene near Revit's origin with shared coordinates moved), read by the reader with the real worker deciding what
  is left out. Each must pass the conformance suite's own check of a recording (`recording_problems`: the expected
  description, then exactly the hand-worked verdicts) and give the same verdicts again through `check_site` from C#.
  Four of them are also drawn with shared coordinates turned a quarter turn.
- **Revit-only decisions, pinned on fakes, each to confirm on Windows** (`ReaderTests.cs`): phases, design
  options, worksets, links (unloaded, nested, closed workset, holding a wall two links deep), curtain walls,
  groups, in-place and empty families, building elements with no geometry, meshes, faces with holes, the picked
  lot and open property lines, the grade markers, a box turned 30°, and the strict reading of the worker's answer.
- Each main guard was undone once to check its test then fails (15 of them: arcs read as chords, the shared
  coordinates, curved edges, open solids, touching, phases, the option being edited, the 8 corners, unloaded links,
  empty families, empty building elements, closed worksets, links holding a wall, open property lines, open meshes).

What the fakes can't show, and the trial must: that Revit's API gives what each record says (every "to check" in
the design note), and the scenes that need real Revit behaviour (the note's proposed scenes A to K: native walls
and slabs, links and worksets, phases, design options, groups, the picked lot, empty families, Toposolids and
terrain, true north turned, the survey point moved). Not in this reader yet: the ground sampled from a Toposolid
(`grade_from: terrain` is refused with words, never read as no ground), and checking that the saved facts were
entered under the same shared coordinates (scene K).

## The architect's marks (interior step 2)

Egress needs facts only the architect can state: which room is a bedroom, which window is its escape window,
which door is the exit door. They are Gordium **shared parameters** (Ben, 2026-11-19; the
[interior design note](../../docs/revit/revit_interior_reading_design.md), section 3), written as data in
`Gordium.Revit.Reading/Marks.cs`: each name, its fixed GUID (never changed: a new GUID is a different parameter, and
every mark set on the old one would read as not set), Yes/No, text or length, on each element or on its type, and
the categories it is bound to. The operation list (`Operations`) maps each architect's word ("Side-hinged door")
to the interior description's own word for an opening (`side_hinged_door`) and for a door (`side_hinged`); a word
not in the list, or a window's word on a door, is not stated, never a near guess.

- **Adding them** (`MarkSetup.Plan`, done by the add-in's `RevitMarks.AddMarks`): each mark not in the project is
  added; one bound to fewer categories than it should be is extended, keeping any the architect added; one bound
  the wrong way (type instead of instance, another data type), or another parameter of the same name, is a
  conflict: nothing is changed and the marking list says why first. The add-in writes a shared-parameter file of
  its own for this and puts the architect's own back afterwards.
- **Reading them** (`MarkReading`): by GUID only (a firm's own "Gordium: Sleeping room" is never read as
  Gordium's), and only the rooms, windows and doors in the design checked (the outside reader's phase and option
  rule, `SiteReader.InDesignChecked`; a room belongs to one phase, so only the last phase's rooms are read).
  While any Room is unplaced, not enclosed or redundant, `MarkReading.Rooms` gives null: rooms not read (the
  description leaves `rooms` out), never the placed rooms without it (design note, section 2).
  **A mark never set is not stated** (null), never No: Revit's `Parameter.HasValue` false reads as null whatever
  `AsInteger()` says; a blank length is null, never 0. A door's operation must be a door's word ("Casement" on a
  door is not stated, for the opening as for the door): one rule (`Operations.ForOpening(word, isDoor)`) for the
  reader and the list.
- **The marking list** (`MarkingList.Build`): every room, window and door with its marks, anything not set (or set
  to a word Gordium doesn't read) first; a line per mark saying what an unset one leaves not read ("1 of 2 rooms not
  marked, so no room is read for egress"). A room named "Bedroom…" or "Sleeping…" with its mark unset shows
  "suggested: Yes" (Ben's decision 3); a suggestion is never read as the mark, and No is never suggested. A
  Room that is unplaced, not enclosed or redundant (or whose placement couldn't be read) is listed first, as what
  stops every room being read (design note, section 2), never as a row to mark. The headline
  (`MarkingListResult.Headline`) says every room, window and door is marked only when rooms are drawn and nothing
  is unset or in the way.

In Revit, **Mark facts** (the Gordium tab's Check panel; the command is `MarkForEgressCommand`) adds the marks on first use, in one undoable
transaction, then shows the list in a dialog and logs every row to `results.jsonl`. That dialog is the minimal
first view; the dockable list comes with the UI pass. Nothing is sent to the checker yet: the interior reader
(section 7, step 3) builds the description's flags from `MarkReading` alone.

How we know: `MarksTests.cs` (both .NET 8 and 10) pins the table (names, GUIDs, kinds, bindings, categories), the
reading of an unset mark, the operation words against the measuring code's own lists (read from
`model_measurement.interior`, never retyped), every setup case, the design checked, the order of the list and the
suggestions. Two guards were undone once to check their tests then fail: an unset Yes/No read as No, and a
parameter of a mark's name taken for it.

Tried in Revit 2027.4 on Snowdon Towers (2026-11-19; [design note, section 9](../../docs/revit/revit_interior_reading_design.md#9-to-check-in-the-trial-the-revit-api-on-real-models)):
all 10 marks added, the names with a colon accepted; 57 of 57 existing rooms and 297 of 297 windows and doors read
not set, and a room placed afterwards too (58 of 58); a second run added nothing. Still to check: that a type's
marks read through `doc.GetElement(e.GetTypeId())` (Operation set on a window type), and the room placement
states (unplaced, not enclosed, redundant) on real rooms.

## Rooms and escape windows (interior step 3)

The **interior reader** (`Gordium.Revit.Reading/InteriorReader.cs`) turns the rooms and the windows and doors into
the [interior description](../../docs/interior/interior_description_format.md) (`gordium.interior/1`, feet, shared
coordinates), by the [design note](../../docs/revit/revit_interior_reading_design.md)'s rules (sections 2 to 4). Its
records (`InteriorRecords.cs`) are filled by the Revit layer (`Gordium.Revit.Addin/RevitInterior.cs`), which decides
nothing. What it sends, and what it leaves out:

- **`rooms`**, only when every room counts: no Room unplaced, not enclosed or redundant; **no enclosed area without a
  Room** on any level (Revit's own plan circuits, `PlanTopology.Circuits` and `PlanCircuit.IsRoomLocated`, for the
  last phase); no closed workset; no linked model not loaded, holding Rooms or holding links of its own. Each is
  listed first in the marking list. The way to clear an enclosed area that isn't a room (a chase, a closet) is to
  place a Room in it, marked Sleeping room No. With no Room at all, `rooms` is left out, never `[]`.
- Each room's **`floor`**: its boundary at the finished faces (`SpatialElementBoundaryLocation.Finish`), sent only as
  one loop of straight segments, with nothing standing inside it that doesn't bound it (a wall set not to bound rooms,
  a column; furniture, casework and fixtures don't count, nor a window or door in a wall bounding it: only those, never anything else the wall hosts), from just above
  the floor to the level's room computation height. **`floor_elevation`**: the level and base offset, sent only when
  one slab top (a floor or a foundation slab) within a foot of it agrees within 1/16 in and covers the whole room.
  **`ceilings`**: the downward flat faces of everything building or services over the room, clipped to its floor
  (exact polygon clipping, `PlanGeometry.cs`), the lowest counting in the measuring code; anything over it that can't
  be read exactly (a curved face, a mesh, a category in neither list) leaves `ceilings` out. A loaded linked model
  reaching over a room leaves all three out.
- **`openings`**: every window and door in the design checked, with its marks (step 2); `room` from `FromRoom` /
  `ToRoom` for the last phase (left out when it is between two rooms or in none). A window's maker's clear opening,
  **`stated_clear`**, is sent only when (1) its type's `Gordium: Clear confirmed` stamp (`ClearStamp.cs`) equals
  every value read now (the type's `UniqueId`, its own Width and Height, Operation, Clear width, height, offset and
  source, and a maker's parameter it names); (2) its **sill line** (level + Sill Height) agrees within 1/16 in with
  the bottom of the opening it cuts in its wall (the wall's faces whose `GetGeneratingElementIds` name it); and (3)
  the clear opening fits inside the window's own geometry as placed. `bottom` is the sill line plus `Clear offset`.
  Never a frame or sash, a ground outside (no Toposolid is read yet) or an area well. Doors get no clear opening (the
  doors step). With no window or door found, `openings` is left out, never `[]`; a window or door in a linked model
  leaves it out too.
- **`stairs`, `doors`, `guards`, `has_none`**: left out (not read): later steps. Step 6 (`HasNone.cs`): an empty
  `stairs`, `doors` or `guards` and each `has_none` claim only on the architect's "This house has no ..." tick on
  Project Information, with nothing of the kind drawn and nothing that could hide one; a tick against what is drawn is
  never sent and is listed first in the marking list.

Every value left out has its reason in `InteriorReadResult.Notes`; for each escape window, `Evidence` records the
sill line, the wall opening's bottom and the window's placed extents the check used.

**Read inside** (the Trial panel, a test tool) reads the open project this way and logs the description and every note.

**How we know (without Revit):** `InteriorTests.cs` draws houses 1, 2 and 5 as fake Revit records from the houses'
own data (`InteriorDrawing.cs`, through `python -m model_measurement.interior.recordings draw`) and checks the
reading with the same interior conformance CI applies to a Revit recording
(`model_measurement/interior/recordings.py`: every measure in the step's scope equal to the hand-worked one, every
other not measured, stairs, doors and guards not read), also under shared coordinates turned 30 degrees and moved
875,000 ft. Then each trap one at a time: an enclosed area with no Room, an unplaced Room, a closed workset, links,
nothing drawn, an unmarked room, two boundary loops, a curved segment, a wall inside not bounding, furniture, slabs
missing, an inch high, at two heights or under part of the room, a soffit, a category not known, a curved face over
the room, and fifteen ways a window's clear opening can't be trusted (no stamp, Clear offset blank or set to 0 after
confirming, source or operation edited, a duplicated or resized type, a changed maker's value, the wall opening an
inch below the sill line or not found, a clear opening wider than the window, no geometry...). Eight guards were
undone once to check their tests then fail (the sill line check, the enclosed areas, never `[]`, the slab covering
the whole room, the stamp's type, the clear opening fitting the window, what stands inside a room).

**How we will know in Revit (the recordings):** **Record houses** (the Trial panel, or the request file below)
draws houses 1, 2 and 5 in new projects (`HouseDraw.cs`: the houses' numbers from the same Python, exterior walls
with their inside faces on the rooms' outline, a slab under each level, room separation lines, Rooms named and
marked, ceilings as thin DirectShapes whose undersides are the house's ceilings, one `Window.rft` family per window
with a frame solid of its size, its maker's clear opening confirmed with the stamp), reads each through the Revit
layer, writes `test_data/interior_houses/recorded/revit/<house>.json` (the description, the notes and the
evidence), and checks it as CI will (`python -m model_measurement.interior.recordings check <file>`). The earlier
recording is deleted first, so a failed run leaves none. Asked for with no click by writing
`%LOCALAPPDATA%\Gordium\trial\interior_request.json` (`{}` for all three, or `{"houses": ["1_ranch_compliant"]}`)
while Revit is idle: taken once, results in `results.jsonl` (`record_house` lines). CI checks every recording
committed, and a host with any recording must have all three (`test_interior_recordings.py`).

**Recorded in Revit 2027.4 (trial run 6, 2026-11-20):** all three houses pass with no problem: rooms read, and every
escape window's wall opening (the wall faces whose `GetGeneratingElementIds` name it) with its bottom on its sill line
exactly, so the clear measures are in the step's scope. `FindInserts` listed no inserts even on the cut walls, so
nothing relies on it. Lessons from runs 1 to 5, in the drawer: Window.rft's head plane is "Top"; Revit cuts a window's wall only
after a `Document.Regenerate()` right after the window is placed and its Sill Height set (without it, runs 2 to 5 and
a re-recording of 830fbedc: hosted, nothing cut; the walls are also committed first); the walls stop at the ceilings' top (higher, house 5's basement walls closed an area on the level
above); the enclosed areas are read inside a rolled-back transaction (Revit works them out only in a document it can
change).

**Makers' clear openings, filled as drafts** (`MakerClearOpenings.cs`, data in
[`data/maker_clear_openings.json`](data/maker_clear_openings.json), embedded in the library; design note, section
5a). Mark facts and Check project fill an empty window type's `Clear width`, `Clear height` and `Clear
source` from its maker's published formula when its Manufacturer and a call-number Model (Marvin's "UCA3648") match an
entry, its Gordium: Operation is the entry's or unset, its Width and Height are surely the maker's frame size, and the family's own Vent Area, when it has
one, agrees; never `Clear confirmed`, so nothing is sent until that type is confirmed. The
data is not a rule and not measuring code: a hand-curated list of makers' figures, each entry pinned by
`MakerClearOpeningsTests` to rows of the maker's own table (first entry: Marvin Ultimate Casement, CN 2864 and three
more rows).

For a clone with no venv of its own (a git worktree), install with the main clone's Python:
`install_trial_addin.ps1 -Python C:\...\gordium\.venv\Scripts\python.exe`; the add-in then runs Python with this
clone's packages first (`PYTHONPATH`), so the code run is always this clone's.

## Stairs (interior step 4)

The **stair reader** (`Gordium.Revit.Reading/StairReader.cs`, called by `InteriorReader`) sends each run of a
component stair as one flight of `stairs`, by the [design note](../../docs/revit/revit_interior_reading_design.md)'s
section 4 ("As built in step 4"):

- **Only on the architect's tick and with nothing hidden.** `stairs` is sent only when `Gordium: These are all the
  stairs` on Project Information says Yes (a mark added by Mark facts; unset or No: not read) and nothing could
  be a stair the reader doesn't walk: a stair not made of components, a multistory stair, anything else in Stairs,
  Railings or Generic Models (an in-place or loadable family, a DirectShape), a closed workset, an unloaded link, a
  link holding stairs, a coordination model. Each is listed first in the marking list (`MarkingListResult.StairBlockers`),
  with a summary line for the tick. With no stair found, `stairs` is left out, never `[]`. An element the architect
  marks `Gordium: Not a stair` Yes (Generic Models, Stairs, Railings; added by Mark facts) is cleared, and listed
  as cleared ("Not a stair (architect): ... x N, ids in the log": `MarkingListResult.NotAStair`,
  `InteriorReadResult.NotAStair`); on a Revit Stair or Railing the mark is a conflict, listed first, and doesn't count.
- **Each flight from what is drawn.** `bottom_elevation`: the floor or landing in front of the first riser, as drawn
  (below the first tread). `nosings`: each tread's front edge from the run's own flat faces, then the floor's edge at
  the head as drawn (above the top tread, nothing of the run above it), so a first or last riser taller or shorter than
  the run's is measured as drawn (R318.7.5.1); sent only when the run's own risers (base to top) and treads agree with
  the stair's typed `ActualRiserHeight` / `ActualTreadDepth` (and the counts with the run's). `sides`: the innermost
  wall face beside the flight running from its treads to 80 in over them, `open` when nothing is there; anything
  else beside it (a column, a railing) leaves `sides` out. `overhead`: the undersides over the flight clipped to its
  plan, a stairwell opening taken out exactly. No `handrails` (railings come with the guards, step 5).
- A flight found is never dropped: whatever can't be read is left out with its reason (`InteriorReadResult.Notes`;
  the flight's numbers and what was compared in `Evidence["stairs"]`).

**How we know (without Revit):** `StairTests.cs` draws houses 2 and 3's stairs as fake records (`InteriorDrawing.cs`)
and checks them with the interior conformance CI applies: house 2's risers, treads, headroom (85.5 in) and clear width
(36 in) as worked by hand; house 3's tall riser, drawn at the head, measured as drawn (9 in, variation 1.5 in); both
under turned shared coordinates.
Then each trap: no tick, No, never set; nothing found; each blocker; a typed riser or tread disagreeing; the run's
counts and ends; a winder, a curved face, a run whose geometry fails; a riser board's top under its tread; the floor at
the foot missing, an inch high or under half the width; a link reaching the flight; a wall inside the tread ends
(34 in); a railing, a column, a chair or a wall cabinet beside it (furniture and fixtures count for a stair), a pipe behind the wall; a light in the headroom; a floor at the head reaching over the last tread; a wall not running the whole flight; the
stair's own stringer low and outside, or over the treads; a beam over it (84 in); a mass, a failed duct, a beam
through the flight, a handrail over it; a floor with a stairwell opening.

**In Revit:** Record houses draws houses 2 and 3 with their stairs (`HouseDraw.DrawStairs`: a duplicated stair type
with no supports and a run type with no nosing, the side walls, the floor at the foot and head and the overhead as
DirectShapes, the walls and floors committed and regenerated before the `StairsEditScope`, the document regenerated
after; any railing Revit adds is deleted: step 5), ticks "these are all the stairs", and records each house at its
step (houses 1 and 5 at step 3, 2 and 3 at step 4). The recording keeps `stairs_not_read`, the drawing's notes and
what Revit gave back for each stair (`drawn`), and each run's faces, numbers and surroundings in its evidence.

## Doors, handrails and guards (interior step 5)

By the [design note](../../docs/revit/revit_interior_reading_design.md)'s section 4 ("As built in step 5"):

- **Doors** (`InteriorReader.ReadDoor`): every door is a `doors` entry with its `Gordium: Exit door` mark, its
  type's operation (the door's word) and `stated_clear` `{width, height, source}`, the maker's clear opening, sent
  only when the type's `Gordium: Clear confirmed` stamp, made for a door, confirms every value now (the type itself,
  its size and operation, the clear width and height, the source, a mapped maker's parameter: exactly as windows'),
  and it fits inside the door as placed. `Clear width`, `Clear height`, `Clear source` and `Clear confirmed` are now
  bound to Doors too (Mark facts extends an existing project's binding); a door has no `Clear offset`. Nothing
  drawn is sent (stops, hinge pin, leaf, threshold): door families don't model them consistently.
- **Handrails** (`StairReader`): a railing on the stair beside a wall, read exactly, between the wall face and the
  flight's middle and no higher than 38 in over the nosings, with nothing of it but its handrails standing farther in
  than the innermost handrail edge sent, is that side's handrail (not its side, never its
  headroom): its handrails, and its top rail where the railing type says `Gordium: Top rail is handrail` Yes, each as
  the edge nearest the middle. Any other railing beside a flight leaves its `sides` and `handrails` out.
- **Guards** (`GuardReader.cs`): each railing on no stair is a guard at a level walking surface: its members (every
  solid of the railing, its top rail and handrails, each a box square to it), its top, the floor along it (checked
  against its base), and its ends (a wall or post face at each). Guards along a stair aren't read yet, so a railing
  on a stair that isn't a handrail beside a wall, or a railing on no stair standing beside a flight, leaves `guards` out.
- **The tick:** `guards` and every flight's `handrails` are sent only when `Gordium: These are all the guards and
  handrails` on Project Information says Yes (unset or No: not read; with it, a flight with no railing found sends
  `handrails: []`). Nothing found is never "none": no door or guard found leaves that list out.

**How we know (without Revit):** `DoorGuardTests.cs` draws houses 1, 2, 4, 5 and 6 as fake records and checks them
with the interior conformance CI applies (house 6's door 33.5 x 79.25 in, house 4's loft guard 36 in high with 3 1/2 in
openings, house 2's and house 4's handrails), also under turned shared coordinates. Then each trap: a door type
duplicated, resized, its clear width, source or operation edited, a window's stamp on it, its clear opening wider
than the door; an unmarked door; no door; a round baluster, an L-shaped post, an unreadable baluster, an end wall
missing, short or an inch back, the floor off the railing's base or at two heights or missing, a curved or bent path,
a link; the top rail's mark unset or No; a round, too high, off-stair or past-the-middle railing beside a flight; no
tick, No, never set; no railings read.

**In Revit:** Record houses draws, in houses of step 5 (`HouseDraw`): each door as a family of its own from Door.rft
(a leaf of its size) in an outside wall with no window, placed and regenerated as the windows are, marked and its
type's clear opening confirmed with a door's stamp; each stair handrail as a railing Revit makes on the stair's treads,
its path moved to the drawing's, the other side's deleted, its type's top rail (a square profile from Profile-Rail.rft)
the handrail; house 4's loft guard as a railing from a wall's face to a post's along a floor's edge, its type's top
rail, bottom rail and balusters (a box family from Baluster.rft, one per 5 in pattern) house.yaml's; and ticks "these
are all the guards and handrails". The recording keeps `doors_not_read` and `guards_not_read`; the log every railing's
parts, solid by solid.

## Escape routes (a commercial story)

By the [design note](../../docs/revit/revit_interior_reading_design.md)'s section 10, `RouteReader.cs` adds the
format's route keys for `model_measurement.routes`: `levels` and each part's `level`; each room's `use`, `lockable`
and `pass_through` from the marks `Gordium: Use` (now bound to Rooms too), `Gordium: Can be locked` and `Gordium: Pass
through` (a room's name is only a suggestion in the marking list); its `holes` (a room marked not a sleeping room
only) and `obstructions` (casework, furniture, equipment and fixtures lower than 80 in, by their faces' footprints;
anything else that low leaves them out); each door's `plan` (its centre between its wall's side faces, the confirmed
clear width), `sides` (`FromRoom`/`ToRoom`, or `outside` when no room is drawn beyond) and, from `Gordium: Exit`,
`exit_kind` and `exit_id` (every door into one stair is one exit); and `passages` along room separation lines.
Anything not read exactly is left out with its reason. **How we know:** `RouteTests.cs` reads a fake story
(`RouteDrawing.cs`) and hands the description to the real route code, which draws its routes; each trap is pinned.
**In Revit:** Read inside logs a `routes` line counting what was read, and `evidence.route_doors` each door's place.

## Check my project

(The **Check project** button; the command is `CheckProjectCommand`.) The first button for an architect's own model: one click reads the open project outside (zoning) and inside
(egress) and sends **one** `check_site`, with the lot facts the architect states as Gordium marks on Project
Information (`Gordium: Zone`, `Use`, `Lot surveyed`, `Street edge`, and optionally `Corner lot` and `Ground from`;
the jurisdiction is the City of Ithaca). Why each choice:
[reading design note, section 9](../../docs/revit/revit_reading_design.md#9-check-my-project-the-architects-own-model-one-check).

- **`ProjectCheck`** (`ProjectCheck.cs`): the marks read as facts (`ProjectFacts`: a required one unset and no
  request is made, only the list of what to fill in); the two reads checked to be of the same design (phases,
  design options); the outside described (`SiteReader`), the street edge kept in the mark matched to the lot's own
  edge (`StreetEdges`: an edge the lot no longer has is asked for again, never sent); the inside read
  (`InteriorReader`); one request.
- **`ResultRows`** (`ResultRows.cs`): the answer as rows, the one model the results panel and the text file both
  read. Per row: its verdict (a status word not known is needs review, amber), name, figures (a zoning row's
  measured against allowed; an egress row's as its reason states them), how far off **in the worker's own words
  only** (its `delta`, or `margin` from a worker with no delta; never worked out by the add-in), its reason said
  once, the law's section and exact quotes (from the answer's `detail.quotes`), and its elements. The counts are the
  worker's own summary words per law (`view.sections`), never recounted; red and green only for exactly "N do not
  comply" and "N comply".
- **`ResultText`** (`ResultText.cs`): the same rows as text (`check_project_result.txt`, the log). The headline is
  the worker's state and summary; groups in the worker's order with its counts; failures, rows that need review and
  rows not checked are never cut, other rows past 30 with "N more (in the log)" (the result file has every row).
- **The button** (`CheckProject.cs`): adds the marks on first use, asks the architect to click the street edge
  when it isn't set, reads both on Revit's thread, sends off it, opens the **results panel** and writes every row to
  `check_project_result.txt` and the request and answer to the log. `check_project_request.json`
  (`{"model": "<.rvt>", "marks": {...}}`) runs it with no clicks and never uses the panel.
- **The results panel** (`ResultsPane.cs`, `ResultsView.cs`, `PanelActions.cs`): a dockable pane, *Gordium: Check
  my project*, tabbed behind Properties the first time. Header with *Check again*; the worker's state and count
  chips; its groups in its order (does not comply first, complies folded), every row in a scrolling list; each row
  with its figures, how far off, reason, section and a *Law* expander with the law's words. Click a row (or *Show
  in model*) to select and zoom to its elements. Nothing sent for a missing Project Information fact: the panel
  lists each, with *Open Project Information*. Element marks are still set in Properties (the click selects the
  element). Every Revit call from the panel runs through one ExternalEvent on Revit's thread (`ActionQueue`: a
  refused request is dropped). One scrolling list, rows straight after the counts, *Details* folded after them. An
  edit to the checked project greys everything (no green) and says to check again; closing it takes the rows
  down. The street edge is asked for only when it is the last fact and the view is a plan showing a property line.
  Its look follows Revit's light or dark theme (`UIThemeManager.CurrentTheme` at startup, `ThemeChanged` after):
  one token dictionary per theme (`PanelLook.cs`, from `PanelTokens` in `Gordium.Revit.Reading`), the controls
  restyled (`PanelStyles.xaml`), and every status drawn as its own glyph beside its words (`StatusLook`: fail an
  octagon, needs review a triangle, complies a circle with a check, not applicable a dash, stale a clock), never
  by colour alone; green only for the worker's "complies", never once stale.
  Why each choice: the reading design note, section 9, and the UI design pass (`docs/revit/ui_design_pass.md`,
  section 2.5).

How we know: `ProjectCheckTests` (scene 01 as fake Revit records with interior houses 1 and 5, checked by the real
worker: the scene's hand-worked zoning verdicts, the houses' egress verdicts, a project with no lot never complies,
each missing fact sends nothing), `ResultTextTests` (200 rows with every status, including a word the add-in
doesn't know and a "not applicable" with no reason: nothing shown as a pass that the worker didn't say passes) and
`ResultRowsTests` (the panel's rows: 200 rows all shown once in the worker's groups with its counts, never
recounted; the worker's delta and never a margin it didn't give; egress figures from the reason with no margin
worked out; sections and quotes; count chips coloured only by their words; every text-file row word for word the
panel's; and a real answer's egress failure, R319.2.2, with its figures, section and quote) and `PanelThemeTests`
(every text colour at least 4.5:1 on every background it sits on in both themes, every status mark at least 3:1,
every status its own glyph and word, green only for complies and never stale, no fixed colour in the view). The WPF
panel itself is checked in Revit (it needs Revit to run).

## Build a model from data

A real .rvt built with no click from a drawing script's building data: the C# port of the pyRevit/Dynamo script Ben
received (the Children's Odyssey childcare centre, 19 Libby St, Portland ME, rebuilt from its life-safety sheet
LS1.0: 122 walls, 52 doors, 67 windows, 25 rooms, a floor; feet, origin at the SW corner).

1. **The data, out of the script's text** (`tools/extract_build_data.py`): the script is untrusted downloaded code,
   so it is never run or imported. Its syntax is parsed (`ast.parse`) and the one string literal of
   `DATA = json.loads(r'''...''')` decoded; the data's shape is checked (each door and window's wall exists, the counts
   are the script's own `stats`) and written with `extracted_from` (the script's name and sha256). Anything wrong is
   printed and nothing written.
   `python -I apps/revit_addin/tools/extract_build_data.py <script.py> --out <data.json>`
2. **The model** (`ModelBuild.cs`, its Revit-free decisions in `Gordium.Revit.Reading/BuildData.cs`): the request
   `%LOCALAPPDATA%\Gordium\trial\build_model_request.json`
   (`{"data": "<data.json>", "template": "<optional .rte>", "save_as": "<model>.rvt"}`, plus the script's toggles
   `swing_opposite_facing`, `hinge_opposite_hand`, `use_phases`, each true when left out, and optional
   `corrections`: `[{"wall": "W16", "extend_end_to": [x, y], "why": "..."}]`, each moving a wall's end along its own
   line before drawing, logged as applied, or refused and not applied past 2 ft or off the wall's line) builds, as the script does:
   a new project from Revit's `English-Imperial\default.rte`; Level 1 and its plan; a wall type per status, thickness
   and rating (`LS Existing 12"`, `LS New 4.5" 1 HR`), each wall on its centre line with its Comments and Mark, Existing
   walls in the first phase; a door type per kind and size (the template's family; where there is none, as for double
   doors in Revit 2027's install, a family made from Revit's Door.rft with its leaves' swing drawn in plan), each door
   flipped to swing (`swing_dir`) and hinge (`hinge`) as the data says; windows at their sill; the floor under the
   footprint; a Room at each tag point with its Name (in capitals, as the script) and Number, tagged. Saved, closed.
   The log line `build_model` gives the counts drawn beside the data's, **every element not built with Revit's
   reason** (the script dropped them quietly), each door's flips and each room's area beside the sheet's.

How we know: `test_extract_build_data.py` (a made-up script that raises if run is read whole; every malformed part
named; Ben's script, when `GORDIUM_MOCK_REVIT_SCRIPT` names it, gives 122/52/67/25) and `BuildDataTests` (the
extractor's output read whole by the add-in; the script's names, marks, keyword picks and door flips; the floor
outline; the request). The model itself is checked in Revit.

## Running it

Needs the .NET 10 SDK, the .NET 8 runtime beside it (`dotnet --list-runtimes` shows Microsoft.NETCore.App 8.x and
10.x) and a Python with Gordium installed (`pip install -e ".[dev]"` at the repository root).

```bash
cd apps/revit_addin          # dotnet reads global.json (the pinned SDK) from the folder it runs in
GORDIUM_PYTHON=/path/to/.venv/bin/python dotnet test                       # both, one after the other
GORDIUM_PYTHON=/path/to/.venv/bin/python dotnet test --framework net8.0    # or one at a time
```

`GORDIUM_PYTHON` defaults to `python` on the PATH. CI runs it on Windows and Ubuntu (`.github/workflows/ci.yml`,
job `revit_worker_client`). The test packages are pinned to exact versions, with lock files (`packages.lock.json`);
CI restores in locked mode.

## The add-in in Revit (Windows only)

`src/Gordium.Revit.Addin` is the part that runs inside Revit. It needs Revit's own `RevitAPI.dll` and
`RevitAPIUI.dll`, so it builds only on a Windows machine with Revit installed, and it is left out of
`Gordium.Worker.slnx` (which CI and the Mac build and test). It is built once per Revit version installed:
`net10.0-windows` against Revit 2027, `net8.0-windows` against Revit 2026.

**The Gordium tab** (`Ribbon.cs`, built from `RibbonPlan` in `Gordium.Revit.Reading`; design pass section 2.2):

| Panel | Button | What it does |
|---|---|---|
| Check | **Check project** | the check above |
| Check | **Mark facts** | the marking list above (for now in a dialog: the checklist in the panel comes later) |
| Results | **Panel** | shows the results panel, or hides it when it is showing; usable with no project open |
| Help | **About** | shows and logs which build Revit loaded and on which .NET runtime; usable with no project open |
| Trial | **Check box house**, **Record scenes**, **Read inside**, **Record houses** | the trial's test tools, only in a trial build or with `GORDIUM_TRIAL=1` |

Each button has a one-line tooltip and up to three lines more on a longer hover (Revit's `LongDescription`), and an
icon at 16 and 32 px in Revit's light and dark themes: simple strokes drawn to PNG by `RibbonIcons` from the panel's
colour tokens (the outline in `text`, the mark in `accent`), swapped on `ThemeChanged` (Revit doesn't switch an
add-in's images by theme itself). No Settings button: there is nothing to set yet. `install_trial_addin.ps1` builds
a trial build (`-p:GordiumTrial=true`, the Trial panel always there); `-Architect` installs the build an architect
gets. Revit names an add-in button's Quick Access Toolbar copy and keyboard shortcut by tab, panel and name, so the
four buttons that moved panels in this pass (Mark facts, About, Read inside, Record houses) lose an existing copy or
shortcut once: add them again. The request files the trial runs by (read in `App`'s Idling handler) never use a button, so they work in both.
How we know: `RibbonTests.cs` (which buttons exist with the switch off and on, the tooltips' length, every icon a
valid PNG at both sizes in both themes, never the pass green).

- **Check box house** starts the worker with the clone's venv Python (or reuses the running one), says `hello`,
  sends `check_site` for conformance scene 01 (`test_data/host_conformance/expected/01_box_house.site.json`, with
  the scene's facts), and compares every row with the scene's hand-worked verdicts. The facts and verdicts come
  from `design_checker.conformance` in Python, never copied into C#. The worker stops when Revit closes.

Each button appends one JSON line to `%LOCALAPPDATA%\Gordium\trial\results.jsonl` (timings, the worker's
`about`, every row that differs), so the trial's numbers are read from a file, not off the screen.

To install it for the current Windows user (from the clone, PowerShell):

```
powershell -ExecutionPolicy Bypass -File apps\revit_addin\install_trial_addin.ps1        # Revit 2027
powershell -ExecutionPolicy Bypass -File apps\revit_addin\install_trial_addin.ps1 -Revit 2026
```

It builds the add-in, copies the build to one fixed folder, `%LOCALAPPDATA%\Gordium\addin\<version>\current\` (it refuses while Revit is running: Revit locks the files it loads), writes the clone's path beside it
(`gordium_clone.txt`: the worker reads its rulebooks from the clone), and writes Revit's manifest to
`%APPDATA%\Autodesk\Revit\Addins\<version>\Gordium.addin`. The fixed folder only keeps one copy; it doesn't stop
Revit asking. Revit asks "Always Load" again whenever an unsigned add-in's file changes (seen on the trial laptop,
2026-11-19, in a new folder or the same one), so each build is signed: run once, per Windows user,

```
powershell -ExecutionPolicy Bypass -File apps\revit_addin\trust_trial_addin.ps1
```

which makes a code-signing certificate that exists only on this machine ("Gordium trial add-in (this machine)", its
private key not exportable) and trusts it for this user (Trusted Publishers, and Trusted Root, where Windows asks once
to confirm). Every install then signs `Gordium*.dll` with it, and Revit loads a build from a trusted publisher without
asking. Without the certificate the build is installed unsigned and Revit asks. To undo it, remove that certificate
from `certmgr.msc` (Personal, Trusted Publishers and Trusted Root Certification Authorities).

**How we know it works:** the trial ran it in Revit 2027.4 on 2026-11-19 (runbook section 5, Q2): it loaded on
.NET 10.0.15, the box house's 32 rows matched the hand-worked verdicts four times out of four, and closing Revit
stopped the worker. There are no automated tests of this project (Revit can't run in CI); its logic is kept thin, and
what can be tested without Revit lives in `Gordium.Worker` and `Gordium.Revit.Reading`.
