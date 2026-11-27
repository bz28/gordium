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
   property line inside a linked model makes the lot need review (`lot_block`): the lot may be the link's. A curve
   with no ends (`Curve.IsBound` false: a full circle or ellipse drawn as one curve) is never read as a lot line and
   never left out: a property line holding one makes the lot need review (unless another lot was picked), and so
   does a picked line holding one; a model line nobody picked is no lot line at all.
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

In Revit, **Set up** (was Mark facts; the Gordium tab's Check panel; the command is `MarkForEgressCommand`) adds the marks on first use, in one undoable
transaction, logs every row of the list to `results.jsonl`, and opens the **Setup form** in the Gordium pane (below;
it replaced the list's dialog). Nothing is sent to the checker: the interior reader (section 7, step 3) builds the
description's flags from `MarkReading` alone.

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
5a). Set up and Check project fill an empty window type's `Clear width`, `Clear height` and `Clear
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
  stairs` on Project Information says Yes (a mark added by Set up; unset or No: not read) and nothing could
  be a stair the reader doesn't walk: a stair not made of components, a multistory stair, anything else in Stairs,
  Railings or Generic Models (an in-place or loadable family, a DirectShape), a closed workset, an unloaded link, a
  link holding stairs, a coordination model. Each is listed first in the marking list (`MarkingListResult.StairBlockers`),
  with a summary line for the tick. With no stair found, `stairs` is left out, never `[]`. An element the architect
  marks `Gordium: Not a stair` Yes (Generic Models, Stairs, Railings; added by Set up) is cleared, and listed
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
  bound to Doors too (Set up extends an existing project's binding); a door has no `Clear offset`. Nothing
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

## The Setup form

(Design pass pieces 7 and 9, merged and built; [decision](../../docs/decisions/2026-11-22_setup_form.md); redrawn as
numbered steps by the UI polish, changes 1 to 11, Ben 2026-11-23: only what the check needs, numbered, each with one
help line and the law behind ⓘ; the occupancy group and the sprinkler system required where the Building Code governs,
from the worker's `options.building_code_uses`; every optional fact in one "More facts (optional)" fold; one footer,
**Save and check**; the street pick's confirmation says the edge by its side and length and ends the pick with **Use
this edge**, **Use it, and pick another street edge** or **Pick a different edge**, the pane saying what Revit waits
for meanwhile.) When
**Check project** finds a fact the check needs missing, the Gordium pane shows the Setup form instead of a check;
**Set up** opens it too. Every decision is in `Gordium.Revit.Reading/Setup.cs` and `SetupSteps.cs`, tested without
Revit (`SetupTests.cs`, `SetupStepsTests.cs`); the Revit side is `SetupFlow.cs` (reads, writes, through the panel's one ExternalEvent) and
`SetupView.cs` (the WPF form, in the panel's theme tokens; the dropdown's style is in `PanelStyles.xaml`).

- **Project facts** (`SetupFacts`): every mark `Marks.All` binds to Project Information is a field (data: a mark
  added to Marks.cs appears with no change here), under a heading found from what it feeds. Zone and Use are dropdowns
  of the worker's `options` (`WorkerClient.OptionsAsync`: the districts with a rulebook, the use words with their
  names, the district's permitted ones first), typed until the worker answers; Yes/No toggles; a number for counts;
  **Pick on plan** for the street edge (Revit's pick, `CheckProjectCommand.PickEdges`, kept in the draft as "not
  saved yet" and written by Save with the other facts; the check's own pick, `PickStreet`, still writes at once). Each shows the law
  it answers (the mark's tooltip, "house" said as "building" unless the use is a one- or two-family dwelling).
- **What a Save writes** (`SetupDraft.Writes`): only the fields the architect chose a value for that differs from the
  mark, as one transaction "Gordium: project facts" (`RevitMarks.Write`, the one writer, which the request file's
  `SetMarks` uses too). A field never touched is never written; a value not among its choices is refused, said, and
  not written.
- **The checklist** (`SetupChecklist`): a line per fact inside (sleeping room, escape opening, exit door: needed;
  operation and clear opening per type; for a building that isn't a house, room use, can be locked, pass through and
  exits), each with its counts, why Gordium asks, what a blank leaves, **Select them** (and Properties brought up), its
  suggestions with what each is based on (**Accept**, one or all, as one transaction "Gordium: suggestions accepted"),
  and folded once done. The openings' rooms on each side (`RevitMarks.Sides`: `FromRoom`/`ToRoom` in the last phase)
  are what the escape-opening and exit-door suggestions read; they are never sent.
- **When the check runs** (`SetupGate`): the form shows while a needed fact is missing (the four required project
  facts, a project fact Gordium can't read, the three needed inside lines); after a Save, an accept, a value set in
  Properties or an undo (the form reads its facts again on Revit's DocumentChanged) the check runs by itself once the
  form was waiting and nothing needed is left. **Check now anyway** sends what is set (`ProjectCheck.PrepareAsync`'s
  `anyway`: each fact left out listed in `ProjectPrepared.NotStated`, and said first in the results with **Set up the
  facts**); never without the zone. For the same facts missing, Check project doesn't show the form again this session.
- Results go stale after any Save or accept (neither is one of the check's own transactions), as after any edit.

## Check my project

(The **Check project** button; the command is `CheckProjectCommand`.) The first button for an architect's own model: one click reads the open project outside (zoning) and inside
(egress) and sends **one** `check_site`, with the lot facts the architect states as Gordium marks on Project
Information (`Gordium: Zone`, `Use`, `Lot surveyed`, `Street edge`, and optionally `Corner lot`, `Ground from` and `Stories`;
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
- **The button** (`CheckProject.cs`): adds the marks on first use, shows the Setup form when a fact the check needs
  is missing (above), reads both on Revit's thread, sends off it, opens the **results panel** and writes every row to
  `check_project_result.txt` and the request and answer to the log. `check_project_request.json`
  (`{"model": "<.rvt>", "marks": {...}}`) runs it with no clicks and never uses the panel (and waits on Revit's
  thread: no one is working in Revit then).
- **A check that doesn't freeze Revit** (`CheckRun.cs`; every decision in `Gordium.Revit.Reading/CheckFlow.cs`;
  design pass PR 8). Revit's API can be called only on Revit's own thread, so the read stays there and Revit waits
  for it; everything after it doesn't. In order: the panel comes up saying *Reading the model... Revit waits until
  the read ends.* and its button becomes **Cancel** (the read is queued for after the panel has drawn that line: the
  read blocks Revit's thread, so nothing is drawn during it); the worker's Python is started on a pool thread at the
  same moment, so it starts while Revit reads (Revit's thread waits for it only if the read asks it which objects
  are left out: the step `worker_wait`); after the read the request is sent and waited for on a pool thread
  (`CheckFlow.Send`), the panel says *Checking (Gordium's checker, 12 s)... You can keep working: an edit now makes
  this answer stale.*, and Revit is free; the answer comes back to Revit's thread through the panel's ExternalEvent
  and is shown. The stages are `CheckStage`: idle → reading → checking → done, cancelled or failed. The rules:
  - **An answer is shown fresh only for the model it read.** Every committed change to the project being checked
    that isn't the check's own (`ResultRows.ChangesTheCheck`, as for the panel's stale) is counted from Revit's
    DocumentChanged (`CheckFlow.Edited`); the count is kept when the read ends; an answer handled after a later edit
    is shown **stale** ("The model changed while this check ran (read at 14:32): these results may not hold"),
    greyed, never green. Its "Checked HH:mm" is when the model was read.
  - **Cancel** (the header button while a check runs, or the project being checked closing) cancels the wait: the
    worker is stopped (the client kills it on a cancel; the next check starts a new one) and its answer, or its
    stopped worker's error, is ignored if it still comes. The panel goes back to what it showed before: the earlier
    results **marked stale** ("These results are from 14:32, before the check you cancelled"), never shown as the new
    ones; or the empty, the "fill these in first" or the error state; its words say which was restored (never "the
    results below" with none below). Clicked during the read, it is handled when the read ends (Revit's thread is
    busy until then) but before anything is sent: the read's end keeps the edit count at once, and the send is
    queued behind the input Revit queued during the read (WPF runs Background work only once no input is pending),
    so the click comes first; nothing is sent, the worker keeps running (never killed and restarted), and the log
    line says `cancelled_before_send`.
  - **The street edge is clicked only in the project being checked**, while it is the active one: the read is
    queued after the click, and if the architect switched projects meanwhile, no pick is asked for (a pick, and the
    Street edge mark it writes, would land in the other project); the panel lists "switch to it ... and click Check
    again" (`StreetAsk.NotActive`). The rest of the read is of the project clicked, whichever is active.
  - **One worker per session**: every start and stop goes through `Trial.WorkerAsync` and `Trial.StopWorker`, under
    one lock (the box house's trial command too); a start still running when Revit closes stops its worker.
  - **One check at a time.** A second Check while one runs is refused, with a dialog saying to wait or Cancel (the
    panel's own button is Cancel meanwhile): the read is the part that freezes Revit, and a check started on top
    would read the model twice; an edit meanwhile already makes the coming answer stale.
  - **A crash, a timeout (60 s), an unreadable answer, a worker that won't start** is the error state ("Gordium's
    checker stopped before answering (...): nothing was checked"): every row of the last check taken down, never part
    of an answer shown. The earlier results stay on screen during the check (stale-styled if the model changed),
    not dimmed: dimming would break the 4.5:1 contrast PR 1 tests; the progress line and the header's time say they
    are the earlier check's.
- **The results panel** (`ResultsPane.cs`, `ResultsView.cs`, `PanelActions.cs`): a dockable pane, *Gordium: Check
  my project*, tabbed behind Properties the first time. Header with *Check again*; which code the building was
  checked against and why (`WhichCode`: the worker's `which_code`, its words only, the law's quoted words on hover;
  "Which code: needs review" with the worker's ask when it couldn't decide; never green; no line at all when the
  answer doesn't say); the worker's state and the **compact count bar** (`CountBar`: one line per law, its most
  important counts with every "does not comply" always shown, the rest behind "+N", which opens them in place, and
  every count in the line's tooltip; a line that would wrap keeps one count fewer; the worker's words, never
  recounted: Revit trial, 106 Ithaca Rd, 2026-11-22, the 9 counts took 6 lines at the docked pane); filter chips (all, does not comply, needs review, complies) and a search (rule names, sections, element
  names); then the **results list** (`ResultsList.cs`, its decisions in `Gordium.Revit.Reading/ResultList.cs`): a
  virtualized list, worst first (does not comply, largest how far off first where the worker's figure is a length;
  needs review, the worker's tier 2; check by hand or not checked; complies and not applicable, folded), every row in
  exactly one place, each row: glyph and name (the row's whole width, wrapped), its figures in full or short cause,
  then its section (trimmed, the whole on hover) with *Show*. A click selects the row
  and its elements in Revit without moving the view; *Show* (or Space) zooms; Enter or a double click opens its
  **detail** in place of the list (`DetailView.cs`, its decisions in `Gordium.Revit.Reading/ResultDetail.cs`):
  *Back* and "3 of 8" with previous and next (Alt+Up/Down); the verdict, rule and section; *Why* (the worker's
  reason in full); *What to do* (the worker's own advice first, its `hint`; then by the row's place: change the
  design, resolve what the reason says or decide it by hand, check it by hand; *Show*, *Open the law* and *Check
  again* as buttons; nothing to do for a row that complies, and only *Check again* once stale); *Measured against
  the limit* (each figure, its limit and how far off, the worker's words split, never a number of the add-in's);
  *The law's words* (each quote with where it is, and *Open the law* for each of the worker's `detail.cited` links,
  opened in the browser at its page; egress rows have no link yet, and the detail says so); *Elements* by the names
  architects use (`ElementNames`: "CLOSET (40)", "Door D06"; one no longer in the model said so, never its
  UniqueId), each with *Show*, and *Show all*. Backspace or Esc returns to the same row and scroll position; a stale
  detail says so first and is never green. Up/Down move; Ctrl+C copies the row as the result file says it;
  Ctrl+F searches, Esc clears the search. Nothing sent for a missing Project Information fact: the panel
  lists each, with *Open Project Information*. Element marks are still set in Properties (the click selects the
  element). Every Revit call from the panel runs through one ExternalEvent on Revit's thread (`ActionQueue`: a
  refused request is dropped). Only the filter chips, the search and "Showing N of M" stay pinned; the state and the
  counts are the list's first entry and scroll away with the rows (Revit trial, 106 Ithaca Rd: pinned, they filled
  the whole docked pane), with what wasn't read and *Details* folded after the rows (shown when no filter or search narrows the list). An
  edit to the checked project greys everything (no green) and says to check again; closing it takes the rows
  down. The street edge is asked for only when it is the last fact and the view is a plan showing a property line.
  Its look follows Revit's light or dark theme (`UIThemeManager.CurrentTheme` at startup, `ThemeChanged` after):
  one token dictionary per theme (`PanelLook.cs`, from `PanelTokens` in `Gordium.Revit.Reading`), the controls
  restyled (`PanelStyles.xaml`), and every status drawn as its own glyph beside its words (`StatusLook`: fail an
  octagon, needs review a triangle, complies a circle with a check, not applicable a dash, stale a clock), never
  by colour alone; green only for the worker's "complies", never once stale.
  Why each choice: the reading design note, section 9, and the UI design pass (`docs/revit/ui_design_pass.md`,
  section 2.5).
- **Fix these first** (UI PR 6; `CauseCardsView.cs`, its decisions in `Gordium.Revit.Reading/CauseCards.cs`,
  `LookedAt.cs`, `CheckChanges.cs`, `MeasureBar.cs`). Right under the needs-review heading (or check by hand's, when
  nothing is in review), with the filter on all or needs review and no search: at most three of the worker's
  **cause cards** (each review and by-hand group's `causes`), in the worker's order, the rest behind "+N more
  causes". Each card: the worker's words (three lines, the whole on hover), how many rows it holds ("11 rows · 7
  rules", the worker's rule count), what to set where when it names a mark, and one button by its kind: *fix the
  model* → **Show** (selects its elements and zooms to them; no button when the project has none of them, such as an
  interior-drawing cause with no element id); *mark* → **Show and open Properties** when it names a Gordium mark set
  on its elements (selected, zoomed, Properties brought up, and the line names the mark: the API can't scroll
  Properties to a field), **Open Project Information** when every mark it names is a project fact's ("Set Gordium:
  Stories on Project Information"), **Show** alone when it names no mark (the Odyssey's occupant loads: "the
  description has no mark for it yet"), saying it names none, never a mark guessed (`CauseCards.MarksOf`: a mark
  named in its words, the one mark an interior field in back-quotes feeds, or the Project Information mark each fact
  of a `fact:`/`facts:` key is fed by); *measure by hand* → **Check by hand** and *decide* → **Decide**, which open
  the card on its rows with what that means. **Rows (N)** opens a card: the rooms it names (the 5 rooms with no
  route, each with the worker's why and Show) and its rows, each opening its detail. **Looked at** ticks, on each
  card, each row in review or to check by hand (in the list, in a card's rows, in the detail) and "Looked at: 2 of 15
  causes · 5 of 183 rows": the architect's own note, never a verdict (the tooltip says so; nothing reads it but the
  progress line); kept per project for the Revit session; a new check of the project carries a tick only to a card
  of the same key, words and rows and to a row with the same verdict, reason, figures and how far, still to look at
  (`LookedAt.Carry`); a stale redraw keeps them. **What changed**, under the counts after a new check of the same
  project: "9 rows changed since 09:10: Lot coverage: needs review → does not comply; Building height now complies;
  Front yard now complies; and 6 more. 2 more say something new with the same verdict." (`CheckChanges`: rows matched
  by id, the worker's verdicts only, worst now first; new and gone rows said as such; an answer that arrives stale
  isn't compared, nor is it what the next is compared with). The detail's **measured-vs-limit bar** is drawn only
  from the worker's `limit_length` (two numbers in one unit: the remoteness row's 187.16 ft apart against 71 ft),
  the row's status colour (never green for a row in review, hatched once stale), the worker's words under it; no
  other row has one (zoning's figures and egress reasons are words, never read as numbers). Failures sort by the
  worker's `how_far` lengths, decimal feet and inches too ("2.5 ft short", "4 in over").

How we know: `ProjectCheckTests` (scene 01 as fake Revit records with interior houses 1 and 5, checked by the real
worker: the scene's hand-worked zoning verdicts, the houses' egress verdicts, a project with no lot never complies,
each missing fact sends nothing), `ResultTextTests` (200 rows with every status, including a word the add-in
doesn't know and a "not applicable" with no reason: nothing shown as a pass that the worker didn't say passes) and
`ResultRowsTests` (the panel's rows: 200 rows all shown once in the worker's groups with its counts, never
recounted; the worker's delta and never a margin it didn't give; egress figures from the reason with no margin
worked out; sections and quotes; count chips coloured only by their words; every text-file row word for word the
panel's; and a real answer's egress failure, R319.2.2, with its figures, section and quote), `DetailTests` (a
snapshot of every row's detail of the box house's real answer and of the Children's Odyssey's,
`tests/.../snapshots/`; every number a detail shows is in the worker's item for its row, or an element's name; what
to do never says a row will comply, ends with Check again, and a stale detail is never green; links only the
worker's web or file addresses), `CountBarTests` (every count reachable in the worker's order, a failure never
hidden), `WhichCodeTests` (the line in the worker's words, absent without the field, never green, greyed when
stale), `CheckFlowTests` (PR 8: the stages; an edit after the read makes the answer stale, one before it doesn't;
Cancel goes back to what the panel had, the earlier results stale, its token cancelled and its late answer or error
ignored; a second check refused while one runs and a late answer never the new check's; a crash, a timeout, an
unreadable answer or a worker that won't start the error state; the send returns at once while the stand-in worker
hangs, and Cancel kills it; the real worker's answer fresh, and stale after an edit made while it worked; the words,
the button, the redraw while a check runs; the blocked time; and the add-in's wiring of each, in its source),
`CauseCardsTests` (PR 6: the Odyssey's 15 cards are the worker's in its order, the 5 rooms first with their names;
each card's button by its kind and what the project has; a mark's Properties or Project Information by where its
mark is, never a mark guessed; only the answer's own rows; the cards under the needs-review heading only, never with
a search; a tick never changes a verdict and is carried only where nothing changed; what changed by row id in the
worker's verdicts, a stale answer not compared, an unknown word never "now complies"; the bar only from two numbers
in one unit; failures by decimal how-far lengths), `ElementNamesTests` and `PanelThemeTests`
(every text colour at least 4.5:1 on every background it sits on in both themes, every status mark at least 3:1,
every status its own glyph and word, green only for complies and never stale, no fixed colour in the view). The WPF
panel itself is checked in Revit (it needs Revit to run). The Children's Odyssey's answer
(`tests/Gordium.Revit.Reading.Tests/answers/children_odyssey_check_answer.json`) is made by
`tools/evals/make_odyssey_answer.py` from the add-in's read of the marked model (the worker's egress code with Maine's
law and the eval's building facts; the route parts as the eval measures them); the read stays outside the repo with
the sheet it was built from. `GORDIUM_UPDATE_SNAPSHOTS=1` rewrites the snapshots (read the diff before committing).
The four-unit apartment's answer (`answers/four_unit_apartment_check_answer.json`, for `ResultViewsTests`: the
results as "What to fix" and "By code", UI polish PR 2, and the other pane tests and renders) is the worker's answer to
Ben's 2026-11-23 trial request,
`test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json`: `design_checker.__main__.answer`
on that request, written with `json.dumps(answer, indent=1, ensure_ascii=False)` by
`python apps/revit_addin/tools/evals/make_apartment_answer.py` (run from the repository folder). It is **made, never
committed** (`.gitignore`): almost every rule change changed it, and a committed copy made every waiting PR conflict with
each merge (2026-11-27). CI makes it before `dotnet test` in both Revit client jobs; a build of the tests (or of
`tools/pane_renders`) without it stops and says how to make it; a checker error is never written as the answer. The
tests that read it count what they compare from the answer itself (its statuses and asks), never numbers a rule change
moves; the counting and its words are pinned with numbers on a small answer made in `ResultViewsTests` (`Small`).
How we know: `tools/tests/test_make_apartment_answer.py` (the tool writes the checker's answer exactly and never an
error, git never tracks it, every CI job running `dotnet test` makes it first, the builds stop without it).

**Where Revit's thread went: `ui_thread`** (PR 8). Each `check_project` line from the button or the panel ends
with `ended` (`shown`, `shown_stale`, `nothing_sent`, `cancelled`, `failed`), `answer_use`, `cancelled` (the stage
and time, when cancelled) and `ui_thread`, kept by `UiThreadTime` (`Gordium.Revit.Reading`):

```json
"ui_thread": {
  "blocked_s": 49.31,
  "blocked":    { "start": {"seconds": 0.004, "calls": 1}, "read": {"seconds": 49.1, "calls": 1}, "show": {"seconds": 0.21, "calls": 1} },
  "architect":  { "street_pick": {"seconds": 6.2, "calls": 1} },
  "off_thread": { "check": {"seconds": 3.1, "calls": 1} }
}
```

(made-up numbers). `blocked_s` is the time Revit's thread ran the add-in's code for this check, Revit frozen: `start`
(the click to the panel's line), `read` (marks, the drafts, the read, `prepare` and the request; the architect's
picks taken out) and `show` (the answer made into the panel's rows and labels, on Revit's thread). `architect` is
Revit's thread waiting for the architect's street pick (Revit answers then: never counted as blocked);
`off_thread.check` (also `check_s`) the wait for the worker, Revit free. Before PR 8 all of `read_s`, `check_s` and the
showing were blocked; now only `blocked_s` is. A check asked for by file logs no `ui_thread` (it waits on Revit's
thread, as before). How we know: `CheckFlowTests`.

**Where a slow read spends its time: `read_steps`.** The `check_project`, `read_interior` and `record_house` lines
in `results.jsonl` carry a `read_steps` object beside `read_s` (added after Snowdon Towers froze Revit for 408 s,
all of it in the read, 2026-11-22). It is only a measurement: kept by `ReadSteps` (`Gordium.Revit.Reading`) on
Revit's thread for one run, never part of a record, never in the request (the worker gets the same bytes with it
or without), and logged on a failure too (then the steps read before it). A stopwatch reading per step and a
counter add; no line per element. Its shape:

```json
"read_steps": {
  "steps":  { "outside": {"seconds": 212.4, "calls": 1}, "outside.get_geometry.fine": {"seconds": 96.1, "calls": 48210}, ... },
  "counts": { "outside.elements": 48210, "outside.family_instances": 9120, "outside.fine.faces": 702311, "inside.rooms": 412, ... },
  "max":    { "inside.over.candidates_per_call": 3911, ... },
  "links":  [ {"link": "Snowdon Towers Sample Structural.rvt : 2 : location <Not Shared>", "depth": 1, "seconds": 61.2, "elements": 20114} ]
}
```

(the numbers are made up, to show the shape). `steps` are seconds (to the millisecond) and how many times each step
ran, summed over the run; a step's time includes the steps inside it (`outside` includes every `outside.*`).
`counts` are summed, `max` is the largest one room (or call) gave, `links` one entry per linked model read (its
seconds include its own links; its elements are its own). The names:

- **Check project's run:** `outside` (the outside read, `RevitRead`), `inside` (`RevitInterior`),
  `prepare` (the marks read as facts, the lot, `SiteReader`, `InteriorReader` and the request made:
  `ProjectCheck.PrepareAsync`), in it `worker_wait` (the worker, started on a pool thread before the read, waited for
  when the read asks it which objects are left out; PR 8: it was `worker_start`, all of Python's start on Revit's
  thread), `log_request` (the request written for the log). Read inside and Record houses log
  `inside` and `interior_reader`.
- **The outside read** (`RevitRead`; totals include linked models' elements): `outside.collect` (listing every
  element), `outside.get_geometry.fine|medium|coarse` (Revit's `get_Geometry`; medium and coarse are read for
  family instances only) and `outside.copy_geometry.*` (the faces, their 7 × 7 samples and the edges copied),
  `outside.element_rest` (the rest of each element: box, marks, kind), `outside.model_rest` and `outside.lot_lines`.
  Counts: `outside.elements` (the project's own), `outside.family_instances`, and per detail level
  `outside.fine|medium|coarse.solids|faces|edges|meshes`.
- **The inside read** (`RevitInterior`): `inside.marks_model`, `inside.internal_to_shared`, `inside.read`, and in it
  `inside.rooms`, `inside.openings`, `inside.stairs`, `inside.railings`, `inside.enclosed_areas`, `inside.links`,
  `inside.ramps`, `inside.separation_lines`, `inside.gross_areas`. Per room: `inside.room.boundary`
  (`GetBoundarySegments`, counted as `inside.room.boundary_calls`), `inside.room.inside` (the room's solid against
  the model; hits `inside.room.inside_hits`, largest `inside.room.inside_hits_per_room`), `inside.room.under` and
  `inside.room.over` (the box under the floor, and over it to +1000 ft in any category), `inside.room.band_solid`.
  In each of those two, `inside.under|over.collect` (the box filter), `.faces` (each element's faces), `.band`
  (over only: each element cut by the room's band), counts `.candidates` (elements the box found) and `.read` (model
  elements kept), largest `.candidates_per_call` and `.read_per_call` (one call per room). The same box search round
  each stair run (to +1000 ft, any category) and each railing is logged apart, as `inside.stair_run.near.*` and
  `inside.railing.near.*` (the same names, no band). The band's boolean cuts:
  `inside.boolean_op`, counted `inside.boolean_ops`; open shells skipped `inside.open_shells`. Faces read
  (`inside.faces`), of them curved and triangulated (`inside.faces_triangulated`, time `inside.triangulate`).
  Windows and doors: `inside.opening.faces`, `inside.opening.cut`. Each element's geometry is worked out once per
  read (`ReadMemo`, kept by element and geometry options for the rooms, openings, stairs and railings, let go before
  the enclosed areas change the model): its faces, counted `inside.cache.faces.hits` (asks answered from what was
  kept) and `.misses` (worked out), and its geometry walked for the band, `inside.cache.band_pieces.hits|misses`
  (the band's cuts are still made per room). So `inside.faces`, `inside.faces_triangulated` and `inside.triangulate`
  count each element's own faces once (the band's cut faces still once per room), and `.faces` and `.band` keep one call per element per box. The transactions: `inside.enclosed_areas.topology`,
  `.outline` (a Room placed in an area with none, rolled back), `.rollback`; per level of the outer outlines
  (`inside.gross_areas.levels`) `inside.gross_areas.ring`, `.lines_commit`, `.topology`, `.room_commit`, `.rollback`.

How we know: `ReadStepsTests` (kept only while a read has begun them, on its own thread; added by name; seconds to
the millisecond; a step that throws still timed; geometry tallied with instances' items; no record, request or
reader type holds them and no Revit-free file but their own names them; and every hook in `RevitRead`,
`RevitInterior`, `CheckProject` and `RecordHouses` pinned in their source, with what they read unchanged) and
`ProjectCheckTests.The_request_is_byte_for_byte_the_same_with_the_read_steps_kept_or_not`.

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

3. **Data with several levels** (the New York eval, `tools/evals/make_ny_build_data.py`, from the repository's own
   description files, each element citing its source field): `levels` in place of `level`, each wall and room naming
   its level (a door or window is on its wall's); `floors` (each slab's level, outline, thickness and top offset) in
   place of the footprint; `ceilings` (thin solids in Ceilings whose undersides are the rooms' ceilings, as Record
   houses draws them); `separations` (room separation lines); `lot` (a property line) and `spot_grades` (Gordium's
   spot-grade markers); `type_suffix` (what the door and window types are named after). A door with no `swing_dir` is
   left as Revit places it, never flipped on a guess. The template's levels the data doesn't have are deleted. The
   steps of the eval: [the runbook, section 8](../../docs/revit/windows_trial_runbook.md#8-the-new-york-eval).

How we know: `test_extract_build_data.py` (a made-up script that raises if run is read whole; every malformed part
named; Ben's script, when `GORDIUM_MOCK_REVIT_SCRIPT` names it, gives 122/52/67/25) and `BuildDataTests` (the
extractor's output read whole by the add-in; the script's names, marks, keyword picks and door flips; the floor
outline; the request; the two New York buildings read whole on their levels, each Orangetown room closed by its own
level's walls, and each malformed part of data with levels refused in words), `test_make_ny_build_data.py` (the
committed data is a fresh build, every element names its source, and what is drawn equals the sources' numbers) and
`test_ny_eval.py` (the marks, the requests and the comparison). The model itself is checked in Revit.

## Running it

Needs the .NET 10 SDK, the .NET 8 runtime beside it (`dotnet --list-runtimes` shows Microsoft.NETCore.App 8.x and
10.x) and a Python with Gordium installed (`pip install -e ".[dev]"` at the repository root).

```bash
python apps/revit_addin/tools/evals/make_apartment_answer.py   # first, from the repository folder (see below); ~30 s
cd apps/revit_addin          # dotnet reads global.json (the pinned SDK) from the folder it runs in
GORDIUM_PYTHON=/path/to/.venv/bin/python dotnet test                       # both, one after the other
GORDIUM_PYTHON=/path/to/.venv/bin/python dotnet test --framework net8.0    # or one at a time
```

The first line makes the four-unit apartment's answer the pane tests read (below, "The four-unit apartment's
answer"); it is made, never committed, and a build of the tests without it stops with that line. Run it again after
pulling or changing rules, so the tests read today's answer (CI always makes it fresh). `GORDIUM_PYTHON` defaults to
`python` on the PATH. CI runs it on Ubuntu on every push (`.github/workflows/ci.yml`, job `revit_worker_client`) and on Windows
once a PR is labelled merge-ready and every night on main (`.github/workflows/windows.yml`, job
`revit_worker_client_windows`). The test packages are pinned to exact versions, with lock files (`packages.lock.json`);
CI restores in locked mode.

## The add-in in Revit (Windows only)

`src/Gordium.Revit.Addin` is the part that runs inside Revit. It needs Revit's own `RevitAPI.dll` and
`RevitAPIUI.dll`, so it builds only on a Windows machine with Revit installed, and it is left out of
`Gordium.Worker.slnx` (which CI and the Mac build and test). It is built once per Revit version installed:
`net10.0-windows` against Revit 2027, `net8.0-windows` against Revit 2026.

**The Gordium tab** (`Ribbon.cs`, built from `RibbonPlan` in `Gordium.Revit.Reading`; design pass section 2.2; UI
polish change 48, Ben 2026-11-23):

| Panel | Button | What it does |
|---|---|---|
| Check | **Check project** | the check above |
| Check | **Set up** (was Mark facts) | the Setup form in the Gordium pane (the numbered steps and More facts) |
| Results | **Results** (was Panel) | shows the Gordium pane, or hides it when it is showing; usable with no project open |
| Results | **Summary** | the printable summary of the last check |
| Help | **About** | shows and logs which build Revit loaded and on which .NET runtime; usable with no project open |
| Help | **Trial** pull-down: **Check box house**, **Record scenes**, **Read inside**, **Record houses** | the trial's test tools, only in a trial build or with `GORDIUM_TRIAL=1` |

Each button has a one-line tooltip and up to three lines more on a longer hover (Revit's `LongDescription`), and an
icon at 16 and 32 px in Revit's light and dark themes: simple strokes drawn to PNG by `RibbonIcons` from the panel's
colour tokens (the outline in `text`, the mark in `accent`), swapped on `ThemeChanged` (Revit doesn't switch an
add-in's images by theme itself). No Settings button: there is nothing to set yet. `install_trial_addin.ps1` installs
the build an architect gets by default (no Trial pull-down: Ben, 2026-11-23, for demos to architects); `-Dev` installs a
trial build (`-p:GordiumTrial=true`, the Trial pull-down always there), and `GORDIUM_TRIAL=1` in Revit's environment turns
it on in any build. Revit names an add-in button's Quick Access Toolbar copy and keyboard shortcut by tab, panel and name, so a
button renamed or moved loses an existing copy or shortcut once (the UI polish renamed Mark facts to Set up and Panel to
Results, and moved the four trial tools into the Help panel's Trial pull-down): add them again. The request files the trial runs by (read in `App`'s Idling handler) never use a button, so they work in both.
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
