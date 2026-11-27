# Revit port: the two-week Windows trial, a runbook

**Purpose:** what the two-week Windows trial of the Revit port must answer, how to set it up, what to do each day, how to record the Revit scenes for the conformance suite, and when to stop or switch machines.\
**For:** Ben, and whoever (a person or Claude) runs the trial on the Windows machine.\
**Kept current by:** whoever runs the trial fills in the results tables and the open items; a PR that changes a command or a scene used here updates this page.

A **host** is a design tool (Rhino, Revit) that reads an architect's model and sends Gordium a description of it; **conformance** is the fixed set of test scenes every host must pass. "Worker" and "site description" are in the [glossary](../glossary.md).
Why Revit gets its own reader and how it is kept honest: the
[decision of 2026-11-06](../decisions/2026-11-06_hosts_talk_to_the_worker.md). The rest of this page is the
practical side.

**The trial in one paragraph.** Gordium's checker is Python and runs on a Mac. Revit runs only on Windows. Before
we write the real Revit add-in, we spend two weeks on a Windows machine finding out whether the plan works at all:
whether Revit is usable on this hardware, whether a very small C# add-in can talk to the same Python checker, and
whether the add-in can read real architects' Revit models well enough, and fast enough, to check after every
edit. The trial ends with a go / no-go and a filled-in results table, not with a finished add-in.

## 1. What the trial must answer

| # | Question | Go if | How it is answered |
|---|---|---|---|
| Q1 | Does Revit run acceptably on the Windows laptop of section 2 (32 GB), first alone, then with the add-in and the worker running? | Opening a model (Snowdon Towers, and each architect model in hand by day 2) and orbiting, selecting and editing is usable with Revit and the add-in both running, and the laptop is not short of memory (Windows RAM in use stays below 90% while working: a proposed number, section 6) | Days 1 to 2 for Revit alone; re-checked on day 4 with the add-in and the worker running. Measured in section 5 |
| Q2 | Can a minimal C# add-in start the Python worker and get an answer back? | The add-in starts `python -m design_checker serve`, sends `hello`, then `check_site` for the box-house scene, and the answer matches what the Mac gives | Days 3 to 4 |
| Q3 | Can it read 3 real architect models: which faces are flat and which curved, stable ids (`UniqueId`), units, survey coordinates? | For each real model (Snowdon Towers alone answers the reading half only, as "provisional (Snowdon)": it has no Ithaca lot, and its survey coordinates stay "not tested"; Q3 is not a go until the architects' models are read), the add-in's site description is valid, curved things are reported (never sent as flat), ids do not change after an edit, and points are in feet | Days 8 to 9 |
| Q4 | How long does reading take after an edit? | Within the targets in section 6, or the miss recorded and the MVP planned as "check on a button" (section 6: a slow read is not a stop) | Day 10, measured in section 5 |
| Q5 | Can the 24 drawn conformance scenes be recorded from Revit and pass? | `python -m design_checker.conformance` on the Mac prints `OK: every scene conforms` with `recorded/revit/` filled | Days 5 to 8, section 4 |

Not in the trial: the dockable pane, the live-check screen, rooms, doors or stairs. Those come after a "go".

## 2. Setup checklist

Do these in order. Tick each when done and write the version you got in the notes column.

| Done | Step | Notes |
|---|---|---|
| [x] | The new Windows laptop set up (GIGABYTE Gaming A16: Intel Core i7-13620H, 32 GB DDR5, RTX 5060, 1 TB SSD, Windows 11 Home, x64; arriving 2026-11-18) | Arrived and set up 2026-11-18 (the machine table, section 5). Windows 11 Home is expected to be fine for Revit (not yet checked against Autodesk's system requirements: confirm when installing). 32 GB meets Autodesk's recommendation for Revit 2027; Q1 still measures it with the add-in running |
| [x] | Windows updated; a note made of the laptop's RAM, cores, disk and graphics | Noted 2026-11-18 (section 5). Updated 2026-11-19: build 10.0.26200.9974, no restart waiting; NVIDIA driver 32.0.15.7676 (`nvidia-smi`: 576.76), and Revit draws on the RTX 5060 (`nvidia-smi` lists `Revit.exe`). On battery, GIGABYTE Control Center's power-saving mode can switch the RTX 5060 off: use Revit on the charger |
| [x] | .NET 10 SDK installed (`dotnet --list-sdks` shows 10.x), and the .NET 8 runtime beside it (`dotnet --list-runtimes` shows Microsoft.NETCore.App 8.x and 10.x) | SDK 10.0.404 (winget), runtime 8.0.10 (came with the laptop). `dotnet test` in `apps/revit_addin` passes on both: 272 + 72 tests on net10.0, 251 + 72 on net8.0 (2026-11-18). The worker client is built for both (see the first check the trial settles, section 7) |
| [x] | Git for Windows installed | 2.56.1 |
| [x] | Python installed: the 64-bit (x64) build of 3.12 from python.org, with "Add to PATH" and the `py` launcher ticked | 3.12.10 (the last 3.12 with an installer on python.org; winget's install failed with "Fast Cache data not found", so the python.org installer was run directly, its signature checked). The repo needs Python 3.12 to 3.14 (`requires-python` in `pyproject.toml`). CI's Windows job tests 3.12 and 3.14 on an x64 machine, so the 64-bit (x64) build is the one proven, and it is what this laptop runs |
| [x] | `git clone https://github.com/bz28/gordium.git`, then check out the branch the trial uses (see Open items) | `main`, after PRs #112 to #115 merged (2026-11-18) |
| [x] | From the clone: `py -3.12 -m venv .venv`, then `.venv\Scripts\activate`, then `pip install -e ".[dev]"` | pip 26.3. Matches the install step of the Windows job in `.github/workflows/windows.yml` |
| [x] | `pytest` passes | 5,810 passed, 41 skipped, in 39.5 minutes with nothing else running (2026-11-18). The slowest test took 220 s; with the C# tests running beside it the same run took twice as long and Python crashed (an access violation, not a failed test); a re-run in 16 parallel groups showed the cause: the old 5-minute hang dump fired 3 times and crashed Python twice: `faulthandler_timeout` is now 15 minutes (`pyproject.toml`). The same step CI's Windows job runs. The Windows job runs more checks after it (rule validation, the audits, the goldens: see `windows.yml`); running them all is optional here, `pytest` is the one that proves the install |
| [x] | `python -m design_checker.conformance` prints `OK: every scene conforms` | Printed 2026-11-18. Proves the Windows install reads the scenes and recordings as the Mac does |
| [x] | The worker answers by hand (below) | 2026-11-18: `hello` answered `ok: true`, protocol 1.1, `gordium.site/1`, a `worker_fingerprint` and a `new_york/ithaca_city` rulebook; an unknown command answered `ok: false` and the worker stayed up |
| [x] | Autodesk's Snowdon Towers sample copied onto the laptop, and each of the architects' 3 models as it arrives (see Open items 1; a model arriving later is added then, without restarting anything) | Snowdon Towers in `Documents/gordium_archive/revit/sample_models/` (2026-11-18). It links five other Snowdon models (Electrical, HVAC, Plumbing, Site, Structural) not copied, so Revit asks about them on opening ("Ignore and continue"). Architects' models: none yet. Keep copies out of the repo clone. The architects' models are the firms' files |
| [x] | Revit 2027 installed. Planned as Autodesk's 30-day free trial, last on the list so the 30 days cover the 14 | Revit 2027.4 (27.4.0.31), 2026-11-19, on an **education licence** (Revit's title bar: "EDUCATION (NON COMMERCIAL)"): Gordium is an education project (Ben, 2026-11-19), so the licence fits, and it has no 30-day clock. Revit 2027 first, because `PropertyLine.GetBoundary` exists only in the 2027 API |
| [ ] | Revit 2026 installed as well, if the licence allows both on the one machine (otherwise note that it did not) | The add-in is built twice: .NET 8 for Revit 2026, .NET 10 for Revit 2027. See the first check the trial settles, section 7 |

**Worker smoke test** (from the clone, venv active). Type or pipe one request per line; each gets one answer line:

```
python -m design_checker serve
{"id": 1, "cmd": "hello", "protocol": "1.1"}
```

Expected answer: `{"id": 1, "ok": true, "result": {"protocol": "1.3", "site_schema": "gordium.site/1", ...` (the
worker's own version, whatever 1.x the request names) with
a `worker_fingerprint` and a `rulebook` entry for `new_york/ithaca_city`. An unknown command answers
`{"id": 2, "ok": false, "error": "unknown command ..."}` and the worker stays up. This was run on the Mac when this
page was written. End it by closing its input (Ctrl+Z then Enter on Windows).

**The scene's facts and verdicts.** `check_site` needs the lot facts the architect states, and the suite compares the
answer with hand-worked verdicts. Neither is in a committed file; both come from the scene in Python. On the Mac or
the laptop (venv active), for scene 01:

```
python -c "import json; from design_checker import conformance as c; s = c.scenes()['01_box_house']; print(json.dumps(c.facts(s))); print(json.dumps(c.expected_verdicts(s), indent=1))"
```

The first line is the `facts` to send; the rest is the verdict of every row the answer must have (`complies`,
`needs_review`, ...). This command was run on the Mac when this page was written.

Two things the add-in's author must know, both from the worker's own code (`design_checker/__main__.py`):

- **Every request line must be UTF-8 without a byte-order mark.** A first line that starts with a BOM is refused
  ("Unexpected UTF-8 BOM"). C#'s default `UTF8Encoding(true)` writes one; use `new UTF8Encoding(false)`.
- **The worker reads the rulebooks from the clone**, so the add-in starts it with the clone as its working folder
  and the venv's Python.

## 3. Day by day

Two weeks: ten working days of work (days 1 to 10), then spare days (11 to 12) and the write-up (13 to 14). Each day ends with the results table (section 5) updated and a few lines of notes.
If a day's question is answered early, move on; if a go / no-go question is answered "no", stop and use section 6.

The trial's test tools (**Check box house**, **Record scenes**, **Read inside**, **Record houses**) are in the Gordium
tab's **Trial** pull-down (on the Help panel), hidden by default (Ben, 2026-11-23: the add-in is demoed to architects).
`apps/revit_addin/install_trial_addin.ps1` installs the build an architect gets, which shows only Check project, Set
up, Results, Summary and About. To turn the developer tools back on, install with `-Dev` (a trial build: the Trial
pull-down always there), or set `GORDIUM_TRIAL=1` in the environment Revit starts in (any build; for example `$env:GORDIUM_TRIAL = "1"`
in PowerShell, then start Revit from that window). The request files (`run_request.json`,
`check_project_request.json` and the others, read while Revit is idle) need no button: they work in either build.
Set up (was Mark facts, and before that Mark for egress), Results (was Panel), About and the four trial tools (now in
the Trial pull-down) were renamed or moved, so a Quick Access Toolbar copy or keyboard shortcut made for them before is
lost once: add it again.

| Day | Do | Done when |
|---|---|---|
| 1 | Section 2 in order, Revit last: Windows, Python, the clone, `pytest`, conformance and the worker smoke test. Then install Revit and start its 30-day clock (only once at least the Snowdon Towers sample is on the laptop: Open items 1). Open Autodesk's Snowdon Towers sample (`Snowdon Towers Sample Architectural.rvt`, saved in Revit 2024; Revit upgrades it on opening) and use it for half an hour: orbit, select, edit a wall. Note memory use in Windows (Task Manager) | Setup list ticked; first Q1 numbers written down |
| 2 | Open Snowdon Towers and each architect model already in hand, timing the open. Use each for a while as an architect would. Decide Q1 for Revit alone on those: go, or switch (section 6); the add-in half is re-checked on day 4. An architect model arriving later is timed when it arrives, and can reopen Q1 | The models in hand open; Q1 has a yes or no, with numbers, and says which models it rests on |
| 3 | Make the smallest add-in that loads in Revit 2027 and adds one ribbon button (nothing else). Build it twice, like the worker client (`net8.0` and `net10.0`). Confirm which .NET runtime Revit 2027 and 2026 load (Revit 2026's may be .NET 10 after an update: section 7), and which build each loads | The button appears in both Revit versions, the note says which build each loaded, or which version refused it |
| 4 | Use the worker client, `Gordium.Worker` ([apps/revit_addin](../../apps/revit_addin/README.md): already tested against the real worker on the Mac), for all of this. The **Check box house** button (Trial panel) starts the worker (venv Python, clone as working folder, `serve`), sends `hello`, shows the `about` fingerprints in a message box, and stops the worker when Revit closes. Then send `check_site` with `test_data/host_conformance/expected/01_box_house.site.json` as the `site` and the scene's facts (see "The scene's facts and verdicts" below) | Q2 answered. The `check_site` answer's rows are exactly the scene's expected verdicts. Q1 re-checked with Revit, the add-in and the worker all running (the second memory row in section 5) |
| 5 | Reading, part 1: a hand-built scene model for scene 01 (box house). The add-in walks its solids and writes a site description: lot, building faces in feet, ids from `UniqueId`. Start from the [reading design note](revit_reading_design.md): how a Revit element maps to a building, what each of the Rhino layers the scenes use (Building, Site, Gordium::Context, Gordium::Grade, Terrain, Default) becomes in Revit, and how the lot outline is found (by default the architect picks a closed outline, the picked-lot flow; reading the property line directly with `PropertyLine.GetBoundary` works only in Revit 2027). Write into the notes where the trial confirms or changes it, and settle its "to check" items as they come up | Scene 01 recorded and passes (section 4): its own `OK  recorded/revit/01_box_house` line appears. Until all 24 drawn scenes are recorded, the run still ends `FAILED`, with a `revit: no recording for ...` line naming the scenes not yet done; that line is expected, not a failure of scene 01 |
| 6 | Reading, part 2: scenes 02 to 06 (curved wall, open solid, block, garage left out, no grade) | Each recorded and passing (its own `OK  recorded/revit/...` line; the `no recording for` line shrinks) |
| 7 | Scenes 07 to 12 (spot grades and the move, millimetres, two lot outlines, survey coordinates, corner lot, ids after an edit) | Each recorded and passing, or the failure explained in the notes |
| 8 | Scenes 15 to 17 (left-out objects, terrain mesh, curved lot line), then 18 to 26 (the scenes from the [reading design note](revit_reading_design.md)'s section 7: a house of native elements, a house in a linked model, a model group moved, the picked-lot flow and open property lines, families with no geometry). Then point the add-in at real model 1 (if no architect model has arrived, Snowdon Towers, recorded as provisional): read it, send it, look at the verdicts. Time every stage (section 5) | The Model 1 column (or the Snowdon column) of the Q3 table filled in |
| 9 | Real models 2 and 3. For each: flat versus curved faces, `UniqueId`s before and after a small edit, units, survey coordinates. Any not yet arrived: its row says so, and Q3 stays open (the trial is not extended for it; Ben decides when it arrives) | The Model 2 and 3 columns filled in, or marked not arrived |
| 10 | Timing runs: the edit loop on every model in hand (Snowdon Towers too), five repeats each. Re-run `python -m design_checker.conformance` on the Mac with the final recordings | Section 5 complete |
| 11 to 12 | Spare. Re-record anything that failed; chase the worst timing; test the other Revit version if only one was used | |
| 13 | Write the go / no-go: answer Q1 to Q5 in section 1 with the numbers, list what surprised us, and what the add-in MVP plan must change | The section 5 tables filled in and signed off by Ben |
| 14 | Commit the recordings and results in a PR (never push to main; Ben merges) and shut the cloud machine down if the section 6 switch was used | PR open |

## 4. Recording the scenes from Revit

The rules are the [conformance README](../../test_data/host_conformance/README.md)'s "How to add a host". The
details that matter here:

- **24 scenes are drawn and recorded; 2 are not.** Scenes 13 and 14 are description-only (they have `site:`
  instead of a drawing) and are never drawn. Scenes 07, 12 and 20 also have a step "after the edit", so the 24
  recordings hold 27 descriptions: 24 "as drawn" and 3 "after the edit". A host with any recording must have one
  for every drawn scene (`coverage_problems` in `conformance.py`), so the hard ones cannot be skipped.
- **Draw each scene from its YAML** (`test_data/host_conformance/scenes/<scene>.yaml`): the lot outline, each
  building's outline, base and floors (a building with `floors` is one solid per floor), the other objects, the
  ground. Everything is in feet. The YAML's `what` says in plain words what the scene tests.
- **Read it with the add-in exactly as a check does**, not with a special code path.
- **Save `test_data/host_conformance/recorded/revit/<scene>.json`** in this shape (the `by`/`date`/`tool` block is
  as the README shows it):

  ```json
  {"host": "revit", "scene": "01_box_house",
   "recorded": {"by": "who", "date": "YYYY-MM-DD", "tool": "Revit 2027, Gordium add-in 0.1"},
   "ids": {"<the UniqueId of an object>": "<the scene's id for it>"},
   "steps": {"as drawn": {"...the description...": 0}}}
  ```

  The scene's ids are the YAML's: `lot` (and `lot_2`, ...), each building's id, or `<id>_floor1`, `_floor2`, ...
  for a building with `floors`, and each other object's id. The step names are exactly `as drawn` and
  `after the edit`. Write the file as UTF-8 (without a BOM, as for requests).
- **One `ids` map serves every step.** For scenes 07, 12 and 20, make the edit in Revit by moving the elements (the
  YAML's `then.move` gives how far; do not redraw them), then record "after the edit". A UniqueId that changes at
  the edit fails the scene.
- **Scenes that need a Revit-specific decision** (write the decision into the notes, and into the PR; the
  [reading design note](revit_reading_design.md) proposes one for each, with the scene that tests it):
  - *04 (a block on the Building layer):* "a block" is whatever Revit cannot send as a solid (for example a family
    instance the add-in cannot read). Either send it as `unsent`, or as a building with no faces and `not_a_solid`.
  - *15 (a block off the Building layer):* the shed block is on the Default layer, so it is not a building and is
    not `unsent`: list it under `left_out` (`could_be_building` true, `touching` false), as for the porch and the
    neighbourhood-layer solid in the same scene.
  - *18 to 26 (the reading design note's scenes):* each YAML's `guards` names the row of the
    [reading design note](revit_reading_design.md) it tests; draw it with the elements that row names. 18: native
    walls, floor and roof slabs, a window, a curtain wall's mullions and panel, an in-place family, and the roof
    slab as a DirectShape of exactly the scene's triangles (a reader that can't tell the mesh is closed sends
    `open_mesh` and fails the cautious way: record which). 19: the house in a linked model, the host file holding
    only the lot. 20: the six parts in one model group; move the group. 21, 23 and 25: pick the lot with the add-in
    (the facts' `lot_id` is then the picked line's `UniqueId`, not the scene's); for 23, pick it, then delete it.
    24 and 25: a property line finished open. 26: a family instance with no geometry, and one nesting a family
    with no geometry beside its own solid.
  - *08 (millimetres):* set the project's display units to millimetres. Revit stores lengths in feet whatever it
    shows, so the add-in should send the same description as scene 01; this scene checks that it does.
  - *09 (two lot outlines):* two closed outlines and no lot picked. The add-in sends no lot and the problem
    `several_lot_outlines`.
  - *10 (survey coordinates):* the scene expects points near 875,000 ft east and 885,000 ft north, and 820 ft up (the scene's offset moves everything, the ground included). Revit has an
    internal origin and survey (shared) coordinates, and warns about elements far from the origin. Decide which
    the description carries (the scene expects the survey ones), and how to make the scene (acquire survey
    coordinates, or draw near the origin with a shared-coordinates offset). Record the decision. This is exactly
    the kind of thing Q3 exists to find out.
  - *17 (curved lot line):* sample the arc every 0.25 ft or closer, each point within a millionth of a foot of the
    arc, and mark the edge `curved: true`.
- **Check on the Mac.** Copy `recorded/revit/` to the Mac (or commit it on a branch and pull it) and run
  `python -m design_checker.conformance`. A recording that fails prints which scene and what differs, saying
  whether the host sent fewer or more problems than expected. Sending fewer is the one that matters most: it is
  the false pass the suite exists to catch. Never edit a recording by hand to make it pass; fix the add-in and
  record again.
- When the site description, a scene or the checker changes, every scene is recorded again.

## 5. What to measure and write down

Fill these in as you go; this page is where the results live. "Mac" below is the reference machine whose answers the laptop must match; Revit and the add-in run on the laptop.

**The machine** (day 1)

| Item | Value |
|---|---|
| Laptop (expected: GIGABYTE Gaming A16, i7-13620H, 32 GB DDR5, RTX 5060, 1 TB SSD; write what Windows reports) | GIGABYTE GAMING A16 CVH; 13th Gen Intel Core i7-13620H; 31.6 GB usable |
| Windows 11 Home build | 25H2, 10.0.26200.9457, 64-bit (before updates) |
| Cores, RAM, disk, graphics driver | 10 cores, 16 threads; 2 × 16 GB DDR5-5600; GIGABYTE AG450E1024-SI NVMe, 954 GB (C: 893 GB, 781 GB free); Intel UHD Graphics driver 32.0.101.6556, NVIDIA GeForce RTX 5060 Laptop GPU with no driver before updates |
| RAM in use by Revit while it is open (Task Manager) | Revit alone at its Home screen 0.8 GB; Snowdon Towers open 1.7 GB, 2.6 GB after the 3D view, orbiting and a plan (working set, 2026-11-19) |
| Revit version(s) installed | Revit 2027.4 (27.4.0.31), education licence |
| .NET runtime each Revit version loads | Revit 2027.4: the `net10.0-windows` build, on .NET 10.0.15 (the add-in's About button and its startup log line, 2026-11-19). Revit 2026 not installed |
| Python and `pip` versions on the laptop | Python 3.12.10 (64-bit), pip 26.3 |

**Q1: is Revit usable here** (days 1 to 2)

| Check | Value | Usable? |
|---|---|---|
| Revit start to ready | 70 s from starting `Revit.exe` to its Home screen, then idle 7 s later (2026-11-19, the Gordium add-in loading; Revit had run once before that day) | Yes |
| Open Snowdon Towers; real model 1 / 2 / 3 (those in hand) | Snowdon: 12 s from Open to its cover sheet, then Revit waits on the missing-links question; 4 s more after it. No upgrade asked. 3D view (Fine detail) 5 s; L1 plan 2 s. No architect model yet | Yes (Snowdon) |
| Orbit and select in each model in hand: smooth, laggy, or unusable | Snowdon, driven by script (Shift + middle-drag, 1.3 s drags, 3 runs): Revit idle again 0.6 to 0.9 s after each drag. Select a wall in plan: 1 s. Nudging a party wall: 3 s, then Revit's own "Can't keep elements joined" error (cancelled, model unchanged). How smooth it *feels* is for Ben to judge by hand | Provisionally yes; Ben's hands-on check open |
| Memory use in Task Manager (percent of RAM in use, and whether it pages heavily), Revit alone (day 2) | 35% before opening; 42% at most with Snowdon open, 3D view, orbits and a plan (day 1, 2026-11-19) | Yes (far below 90%) |
| Memory use in Task Manager, Revit with the add-in and the worker running (day 4) | 43% of RAM in use with Snowdon open, the add-in loaded and the worker running (the worker's two Python processes: 149 MB together) | Yes (far below 90%) |

**Q2: the worker from the add-in** (days 3 to 4)

| Check | Value |
|---|---|
| Worker start to first `hello` answer | 7.0 s (the add-in starting the venv's Python and its `hello`, first time after Revit started); a later `hello` 0.15 s |
| `check_site` for the box-house scene, round trip | 3.1 s the first time (the worker reads its rulebook), then 0.56 to 0.58 s (3 runs) |
| Same rows as the Mac? | Yes: all 32 rows, each with the scene's hand-worked verdict (`conformance.expected_verdicts`, worked out by the same Python the Mac runs), 4 runs out of 4. State needs review: "Zoning: 9 need review · 11 comply · 1 to answer · 1 not checked in this release · 2 use details to answer · Egress waiting: no rooms drawn yet" |
| Worker stops when Revit closes? | Yes: closing Revit logged `worker_stopped` with the worker's process id, and no `python.exe` was left running |

**Q3: the three real models** (days 8 to 9; one column per model; the Snowdon column is provisional and never counts as one of the three)

| Item | Snowdon (provisional) | Model 1 | Model 2 | Model 3 |
|---|---|---|---|---|
| Firm / project (do not put client names in the repo; use a label) | | | | |
| Revit version it was saved in | | | | |
| Project units shown | | | | |
| Survey / shared coordinates set? Origin used by the description | | | | |
| Buildings read | | | | |
| Faces sent flat / faces left out as curved | | | | |
| Problems on the building (codes) | | | | |
| Objects left out (could be a building / touching / ground-like) | | | | |
| Lot outline: picked by hand / found in the model | | | | |
| `UniqueId`s unchanged after a small edit? | | | | |
| Description valid (`gordium.site/1`)? | | | | |
| Anything the add-in could not read, and what it said about it | | | | |

**Q4: time per edit** (day 10; five runs each, write the median and the worst)

| Stage | Snowdon (provisional) | Model 1 | Model 2 | Model 3 |
|---|---|---|---|---|
| Model size (elements, file MB) | | | | |
| Revit API read to a site description | | | | |
| Write JSON and send | | | | |
| Worker's `check_site` | | | | |
| Total, edit to verdicts | | | | |

**Q5: the scenes**

| Result | Count |
|---|---|
| Scenes recorded (of 24) | 24 (Revit 2027.4, 2026-11-19), all in one run with no clicks: 146 s, Revit's start included |
| Scenes passing `python -m design_checker.conformance` | 24 (`OK: every scene conforms`, run on the laptop) |
| Scenes that failed, with the reason for each | None now. On the way: 26, a shared nested family is its own element in Revit (now read as part of its host, [reading design note](revit_reading_design.md) section 8); 18's in-place built-in, which Revit's API can't create (made once by hand, then copied into each scene model). Scene 18's other parts are DirectShapes in their building categories, not native walls, slabs, a window family and a curtain wall, so native elements are still to record ([reading design note](revit_reading_design.md), section 8) |

How they were drawn and recorded: the add-in's "Record scenes" (Trial panel) draws each scene in a new model from the suite's own
numbers (`SceneDraw`), reads it exactly as a check does (`RevitRead`, then `SiteReader`), writes
`recorded/revit/<scene>.json`, and checks it by the suite's rules (`check_recording.py`). A run is asked for by
file (`%LOCALAPPDATA%\Gordium\trial\run_request.json`, read while Revit is idle), so no click is needed.

## 6. Stop and switch criteria

These are proposed numbers for Ben to confirm or change before day 1. They are limits to decide on, not measured facts.

| If | Then |
|---|---|
| By the end of day 2, opening a model (Snowdon Towers or an architect's) takes longer than 3 minutes, orbiting is unusable, or Windows RAM in use reaches 90% or more during ordinary work with only Revit running | Switch to a cloud Windows machine with more memory than the laptop (64 GB or more) and restart the setup list there (Revit's licence there: Open items 3). Keep the days already spent; do not extend the two weeks for the switch more than 2 days |
| Revit runs but the add-in plus Revit takes Windows to 90% or more of RAM in use during ordinary work | Same switch. Q1 is "no" for this laptop, whatever else the trial finds |
| The cloud machine is also too slow | Stop. Report: the Revit plan needs a faster Windows machine before anything else is built |
| The worker cannot be started from the add-in, or its answers differ from the Mac's for the same site and facts | Stop and find out why. A different answer is a bug in the add-in, the install, or the worker, and nothing else is built until it is understood (the same description and the same rulebook must give the same answer) |
| The add-in cannot tell a curved face from a flat one on a real model, or cannot give stable ids | Stop reading work and write up what Revit's API gives. A reader that cannot report curved faces cannot pass the suite, so no check from it can be trusted |
| Read plus check after an edit takes longer than 2 seconds on the models in hand | Not a stop. Live check after every edit is then too slow; note what dominates (read, send, or check) and plan "check on a button" first |
| Longer than 10 seconds on any model | Plan the MVP as "check on a button" with the cause written up |
| One build does not load in both Revit 2026 and 2027 | Not a stop. The MVP builds one assembly per Revit version |

## 7. Open items needing Ben

1. **The 3 real Revit models from the architects.** Not yet in hand. Ask for three, different on purpose: one
   simple (flat walls), one with curved walls or curved roof, and one with survey coordinates set. Ask which
   Revit version each was saved in, and for permission to keep copies on the trial machine only (nothing from them
   goes into the repo). Until they arrive, Autodesk's Snowdon Towers sample stands in (Ben, 2026-11-11; kept outside the
   repo in `~/Documents/gordium_archive/revit/sample_models/`): a multi-storey mixed-use building with real walls,
   floors, roofs and stairs, enough for Q1 and the reading half of Q3 (flat versus curved faces, `UniqueId`s, units).
   It has no Ithaca lot, so it cannot show a real zoning check: the architects' models are still needed for that.
2. **The Windows machine: decided.** A native Windows laptop, a GIGABYTE Gaming A16 (i7-13620H, 32 GB DDR5, RTX 5060, 1 TB SSD, Windows 11 Home, x64), arriving 2026-11-18 (Ben, 2026-11-14). It replaces the plan of 2026-11-05 to run Windows as a virtual machine (a pretend computer) on the Mac. The trial starts when it arrives. The Autodesk account for the
   30-day Revit trial is in hand (Ben, 2026-11-11; its login is kept outside the repo, never in it).
3. **The cloud Windows option**, decided up front so a switch on day 2 costs no time: which provider, and who
   pays, and how Revit is licensed there. The setup list ends with installing Revit, and whether Autodesk allows a
   second 30-day trial on the same account, or moves the first, was not checked; if not, the cloud machine needs
   its own trial account or a paid licence.
4. **Which branch the trial clones.** This page sits on the tidy-up stack's top branch (PR #78); the trial needs
   the stack merged, or that branch, since `recorded/revit/` and the conformance command only exist there.
5. **Confirm the numbers in section 6** (3 minutes to open a model, 90% of RAM in use, 64 GB for a cloud machine, 2 and 10 seconds per edit).

**Checks the trial itself settles** (nothing in the repo answers them today):

- Which .NET runtime each installed Revit loads, and so which build. Revit 2027 runs on .NET 10 (Revit 2027
  "What's new": [Migrating Revit to .NET 10](https://help.autodesk.com/cloudhelp/2027/ENU/Revit-WhatsNew/files/GUID-8D7A4715-EAF8-4BD1-BE78-061F900D0BCE.htm)); Revit 2025 and 2026
  are built on .NET 8, and Autodesk plans to move them to .NET 10 ([call for preview testing](https://blog.autodesk.io/call-for-preview-testing-revit-2026-2025-migration-to-net-10/),
  2026-04-29: a Revit 2026 preview on .NET 10 tested until 2026-06-03, no release date). So the worker client is built
  and tested for both; note the Revit 2026 update installed and the runtime it reports. Whether the .NET 8 build also loads in Revit 2027 is not settled by Autodesk's pages either. **Settled for Revit 2027.4 (2026-11-19):** it loads the `net10.0-windows` build on .NET 10.0.15. Revit 2026 and the .NET 8 build in Revit 2027 are still open (no Revit 2026 installed).
- **How the add-in reads a rule that doesn't apply, and a status it doesn't know.** On the Mac the worker client's
  tests already show both, through the stand-in worker ([apps/revit_addin](../../apps/revit_addin/README.md)): a
  row "not applicable" (the interior description says the house has none of something, PR #112) is read as
  `NotApplicable`, with its reason, on its own line in its law's folded "Complies" group, and counted as neither a
  pass nor a failure; a status word the add-in doesn't know is read as needs review. What only the trial shows:
  that inside Revit, on the runtime it loads, the same answers are read the same way. On day 4, after the scene 01
  check, point the button at the stand-in worker instead of `serve` (`WorkerOptions.Arguments`:
  `apps\revit_addin\tests\Gordium.Worker.Tests\fake_worker.py` and the mode, run with the venv Python and the
  clone as working folder) in mode `not_applicable`, then `unknown_status_in_review`, and list `result.Groups`
  with each row's `Status`, `StatusWord` and `Reason` in the message box. Go if: in `not_applicable`, "Ramps: not
  applicable" is under "IRC · Complies" (folded), with its reason, as `NotApplicable`, and the state is `Complies`;
  in `unknown_status_in_review`, that row is `NeedsReview` with the word `set_aside`, and the state is
  `NeedsReview`. How the panel itself shows them (the mark, the colour, a folded group on screen) waits for the
  dockable pane, after a go. The real worker can't give a row not applicable to the add-in yet: `check_site` doesn't
  carry an interior description.
- Which survey coordinates the description carries (scene 10), and what each Rhino layer becomes in Revit: the
  [reading design note](revit_reading_design.md) proposes both, and lists the rest of its "to check" items.

**Where the facts above come from.** Checked on 2026-11-05 on Autodesk's pages and the projects' own documents:
Autodesk recommends 32 GB of RAM for Revit 2027; Revit has
a 30-day free trial; `PropertyLine.GetBoundary` exists only in the Revit 2027 API; Rhino.Inside.Revit has no
stable Revit 2027 release and pyRevit v7's CPython is experimental, which is why the add-in is C# talking to the
same Python worker. CI already runs the tests on Windows (`.github/workflows/windows.yml`, job `windows`: nightly on main, and on a PR once it is labelled merge-ready). The commands
and file layouts above were read from the repository, and the worker, its BOM refusal and the conformance command
were run on the Mac.

## 8. The New York eval

Two New York buildings, each built in Revit from the repository's own description files, marked, checked with
**Check my project** by request file (no clicks), and compared rule by rule with its answer key. Like the Portland
day-care eval, every mark is an eval assumption standing in for the architect, written with its reason.

| Building | Built from | Marks | Answer key | Checked |
|---|---|---|---|---|
| 80 South William St, Orangetown | `test_data/real_houses/orangetown_ny_80_south_william/revit_build_data.json` (layout.yaml and house.yaml) | its `eval_marks.yaml`: rooms' sleeping, escape windows, the front door, the seven `has_none` ticks, a stand-in lot's facts | `hand_check.yaml` (truth and prediction, 115 rules) | egress only: Ithaca's zoning doesn't apply there |
| 106 Ithaca Rd | `test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/revit_build_data.json` (the architects' spreadsheet) | its `eval_marks.yaml`: Project Information only | the spreadsheet's PASS/FAIL on its 11 rows | zoning (R-1b): the box has no interior |

`apps/revit_addin/tools/evals/make_ny_build_data.py` writes the build data (`--check`: is it current); `eval_marks_request.py`
the three requests; `compare_check_result.py` the comparison. The add-in must be this branch's (it builds several
levels, a lot and spot grades, and marks windows by their Mark). Each request is taken once while Revit is idle, and
in one idle the add-in takes a check before a marks request before a build, so **put each request in place only once
the one before it has its line in `results.jsonl`**.

In PowerShell, from the worktree (`C:\Users\benja\Documents\gordium_nyeval`), Revit closed:

```powershell
$T = "$env:LOCALAPPDATA\Gordium\trial"; $E = "$T\ny_eval"; New-Item -ItemType Directory -Force $E | Out-Null
$py = "C:\Users\benja\Documents\gordium\.venv\Scripts\python.exe"
powershell -ExecutionPolicy Bypass -File apps\revit_addin\install_trial_addin.ps1 -Python $py
foreach ($b in @(@{n="orangetown"; d="test_data\real_houses\orangetown_ny_80_south_william"},
                 @{n="106_ithaca_rd"; d="test_data\test_sites\new_york\ithaca_city\106_ithaca_rd"})) {
  & $py apps\revit_addin\tools\eval_marks_request.py "$($b.d)\eval_marks.yaml" --model "$E\$($b.n)_built.rvt" `
    --save-as "$E\$($b.n)_marked.rvt" --out "$E\$($b.n)_set_marks.json" --build-data "$PWD\$($b.d)\revit_build_data.json" `
    --build-out "$E\$($b.n)_build.json" --check-out "$E\$($b.n)_check.json"
}
```

Then, for each building in turn (Revit running and idle; `$n` = `orangetown`, then `106_ithaca_rd`):

1. `Copy-Item "$E\${n}_build.json" "$T\build_model_request.json"`. Wait for the `build_model` line: `"ok": true` and
   `"all_built": true` (`failed` empty). Orangetown: walls 41, windows 14, the door 1 (`doors` says "no swing in the
   data, left as Revit placed it"), floors 3, ceilings 17, rooms 17 placed and enclosed, each area beside house.yaml's;
   106 Ithaca Rd: walls 4, the roof slab, the lot, 4 spot grades.
2. `Copy-Item "$E\${n}_set_marks.json" "$T\set_marks_request.json"`. Wait for the `set_marks` line: `"ok": true`,
   `refused` empty (Orangetown: 38 applied: the 17 rooms' sleeping marks, the 14 windows' escape marks and their 4
   types' operations, the door's exit and escape marks and its type's operation; 106 Ithaca Rd: none, the copy saved).
3. `Copy-Item "$E\${n}_check.json" "$T\check_project_request.json"`. Wait for the `check_project` line with an
   `answer` (`missing` empty: if it lists a fact, the request's marks didn't take; nothing was checked). Orangetown's
   `notes` should say no clear opening is confirmed on any window or the door, and nothing else is left out.
4. `& $py apps\revit_addin\tools\evals\compare_check_result.py $n "$T\results.jsonl" --model "${n}_marked.rvt"`. It writes
   the building's `revit_eval_comparison.yaml` and exits 0 when nothing differs that wasn't worked out beforehand.

**What to expect** (worked out on the real worker from the same readings, `apps/revit_addin/tools/tests/test_ny_eval.py`):
Orangetown, every one of the 115 egress rules as hand_check.yaml predicts (1 complies, 33 not applicable, 81 needs
review), 18 more cautious than the truth for evaluation.md's reasons, no false pass; its three `has_none` readings
come back as ticks, so they show not applicable rather than as readings to confirm (named, not a failure).
106 Ithaca Rd: 10 of the 11 rows the architects' answer, coverage failing as theirs does; the stories row complies on
the count its `eval_marks.yaml` states in `Gordium: Stories` (3, the spreadsheet's Inputs!B13, an eval assumption
standing in for the architect; the result's line "Stories: 3 stated by the architect, ≤ 3 allowed", the measuring's
record "stated by the architect for the whole building, within what the drawing allows (1 to 5 ...)"; since
2026-11-22, before which it needed review); parking is not checked, because Project Information has
no bedrooms or parking mark (named in its `eval_marks.yaml` with their source). A stories row that needs review now
is a finding (the mark not set or not sent). Anything else is a finding: a Revit reading that differs from the description
(the comparison names the rule), or a build that drew something differently (the `build_model` line says what).

### The Building Code eval (2026-11-22)

A third building, for the 2025 Building Code of New York State: Gordium's own two-story, four-unit apartment
building (`test_data/test_sites/new_york/ithaca_city/four_unit_apartment/`: `apartment.yaml` the building,
`revit_build_data.json` built from it, `eval_marks.yaml` its marks, `expected.yaml` the hand-worked results; why:
[docs/decisions/2026-11-22_which_ny_code.md](../decisions/2026-11-22_which_ny_code.md)). It needs this branch's add-in
(the marks Occupancy groups and Sprinkler system, and `which_code` in the answer). From the worktree
(`C:\Users\benja\Documents\gordium_nycheck`), Revit closed:

```powershell
$T = "$env:LOCALAPPDATA\Gordium\trial"; $E = "$T\ny_eval"; New-Item -ItemType Directory -Force $E | Out-Null
$py = "C:\Users\benja\Documents\gordium\.venv\Scripts\python.exe"; $n = "four_unit_apartment"
$d = "test_data\test_sites\new_york\ithaca_city\four_unit_apartment"
powershell -ExecutionPolicy Bypass -File apps\revit_addin\install_trial_addin.ps1 -Python $py
& $py apps\revit_addin\tools\eval_marks_request.py "$d\eval_marks.yaml" --model "$E\${n}_built.rvt" `
  --save-as "$E\${n}_marked.rvt" --out "$E\${n}_set_marks.json" --build-data "$PWD\$d\revit_build_data.json" `
  --build-out "$E\${n}_build.json" --check-out "$E\${n}_check.json"
```

Then steps 1 to 4 above with `$n = "four_unit_apartment"`. **What to expect:** the build: walls 16, doors 10, rooms 10
placed and enclosed (5 on each level), floors 3, the lot, 4 spot grades. Marks: 44 applied (each room's sleeping,
use, can be locked and pass through; the four stair-enclosure doors' Gordium: Exit) and the one door type's clear
opening stamped (34 in by 80 in, its operation; `eval_marks.yaml` door_types): without that stamp the reader sends no
door's `plan` and no story's routes are measured (the first Revit run, 2026-11-22: three rules needed review for it).
The check's `route_notes` should list no `doors.plan` line. The check: `which_code` is
`building_code`, "a building of Group R-2, none of the dwellings R101.2 lists (101.2)"; only the Building Code's egress
section (no Residential Code section); each story's exits 2, their remoteness 41.0 / 68.425 = 0.599 (complies,
1007.1.1); every rule's verdict as `expected.yaml` (3 comply, 26 need review, 4 not applicable). The comparison exits 0.
A Residential Code section, a story whose routes aren't measured, or an exit count other than 2 is a finding: the
Revit reading differs from `make_ny_build_data.interior_of` (the comparison names the rule).
