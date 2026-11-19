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
   `"protocol": "1.2"` (a 1.0 or 1.1 worker answers it too, all but what it doesn't have: `objects.left_out` is
   1.1's; `check_site`'s `interior`, the house's inside, is 1.2's, and the client sends one only to a worker whose
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
2. **Buildings:** each element of a building category, and each Gordium floor block, is one building: its flat faces
   with straight edges are sent; a curved face or edge, an open solid or a mesh not known to be closed is reported,
   never sent as if it were flat. A building element with nothing to send is never skipped: it is sent as an object
   that couldn't be (`unsent`), so every building measure needs review.
3. **Left out:** every other solid or mesh, every family instance and CAD import whatever it holds (a nested family of lines only is skipped inside it, as at the top), every coordination model (its contents aren't read: on the lot and touching), Gordium's
   neighbourhood objects, a Toposolid. **Which of them are on the lot and which touch the house is the worker's
   decision** (`objects.left_out`, the one copy every host uses), never the reader's.
4. **Linked models:** one holding any building element (at any depth) or a closed workset is not sent (every
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

So far it is the trial's (runbook days 3 and 4): a **Gordium** tab with two buttons.

- **About** shows and logs which build Revit loaded and on which .NET runtime.
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

It builds the add-in, copies the build to `%LOCALAPPDATA%\Gordium\addin\<version>\<time>\` (Revit locks the
files it loads, so the clone stays free to rebuild), writes the clone's path beside it (`gordium_clone.txt`: the
worker reads its rulebooks from the clone), and writes Revit's manifest to
`%APPDATA%\Autodesk\Revit\Addins\<version>\Gordium.addin`. On the trial laptop, Revit 2027.4 picked the add-in up
without a restart and never asked "Always Load" (2026-11-19).

**How we know it works:** the trial ran it in Revit 2027.4 on 2026-11-19 (runbook section 5, Q2): it loaded on
.NET 10.0.15, the box house's 32 rows matched the hand-worked verdicts four times out of four, and closing Revit
stopped the worker. There are no automated tests of this project (Revit can't run in CI); its logic is kept thin, and
what can be tested without Revit lives in `Gordium.Worker` and `Gordium.Revit.Reading`.
