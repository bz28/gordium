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
| Q1 | Does Revit run acceptably in Parallels on this Mac (16 GB M2)? | Opening a model (Snowdon Towers, and each architect model in hand by day 2) and orbiting, selecting and editing is usable with Revit and the add-in both running, and the Mac is not swapping heavily | Days 1 to 2 for Revit alone; re-checked on day 4 with the add-in and the worker running. Measured in section 5 |
| Q2 | Can a minimal C# add-in start the Python worker and get an answer back? | The add-in starts `python -m design_checker serve`, sends `hello`, then `check_site` for the box-house scene, and the answer matches what the Mac gives | Days 3 to 4 |
| Q3 | Can it read 3 real architect models: which faces are flat and which curved, stable ids (`UniqueId`), units, survey coordinates? | For each real model (Snowdon Towers alone answers the reading half only, as "provisional (Snowdon)": it has no Ithaca lot, and its survey coordinates stay "not tested"; Q3 is not a go until the architects' models are read), the add-in's site description is valid, curved things are reported (never sent as flat), ids do not change after an edit, and points are in feet | Days 8 to 9 |
| Q4 | How long does reading take after an edit? | Within the targets in section 6, or the miss recorded and the MVP planned as "check on a button" (section 6: a slow read is not a stop) | Day 10, measured in section 5 |
| Q5 | Can the 15 drawn conformance scenes be recorded from Revit and pass? | `python -m design_checker.conformance` on the Mac prints `OK: every scene conforms` with `recorded/revit/` filled | Days 5 to 8, section 4 |

Not in the trial: the dockable pane, the live-check screen, rooms, doors or stairs. Those come after a "go".

## 2. Setup checklist

Do these in order. Tick each when done and write the version you got in the notes column.

| Done | Step | Notes |
|---|---|---|
| [ ] | Parallels Desktop installed on the Mac; a Windows 11 ARM virtual machine created | Give the VM at least 8 cores and as much RAM as the Mac can spare (Autodesk recommends 32 GB for Revit 2027; this Mac has 16 GB, which is exactly what Q1 tests) |
| [ ] | Windows updated; a note made of the VM's RAM, cores and disk | Fills the machine rows of the results table |
| [ ] | .NET 10 SDK installed (`dotnet --list-sdks` shows 10.x), and the .NET 8 runtime beside it (`dotnet --list-runtimes` shows Microsoft.NETCore.App 8.x and 10.x) | The worker client is built for both (see the first check the trial settles, section 7) |
| [ ] | Git for Windows installed | |
| [ ] | Python installed: the 64-bit Intel (x64) build of 3.12 from python.org, with "Add to PATH" and the `py` launcher ticked | The repo needs Python 3.12 to 3.14 (`requires-python` in `pyproject.toml`). CI's Windows job tests 3.12 and 3.14 on an Intel machine, so the Intel build is the one proven; it runs on Windows 11 ARM under Windows' own emulation. Whether ARM builds of the pinned packages (`rhino3dm`, `shapely`, `numpy`) exist was not checked |
| [ ] | `git clone https://github.com/bz28/gordium.git`, then check out the branch the trial uses (see Open items) | |
| [ ] | From the clone: `py -3.12 -m venv .venv`, then `.venv\Scripts\activate`, then `pip install -e ".[dev]"` | Matches the install step of the Windows job in `.github/workflows/ci.yml` |
| [ ] | `pytest` passes | The same step CI's Windows job runs. The Windows job runs more checks after it (rule validation, the audits, the goldens: see `ci.yml`); running them all is optional here, `pytest` is the one that proves the install |
| [ ] | `python -m design_checker.conformance` prints `OK: every scene conforms` | Proves the Windows install reads the scenes and recordings as the Mac does |
| [ ] | The worker answers by hand (below) | |
| [ ] | Autodesk's Snowdon Towers sample copied onto the VM, and each of the architects' 3 models as it arrives (see Open items 1; a model arriving later is added then, without restarting anything) | Keep copies out of the repo clone. The architects' models are the firms' files |
| [ ] | Revit 2027 installed from Autodesk's 30-day free trial. **Last on the list, because installing it starts the 30-day clock: do it only when every row above is ticked and at least the Snowdon Towers sample is on the VM**, so the 30 days cover the 14 | Revit 2027 first, because `PropertyLine.GetBoundary` exists only in the 2027 API |
| [ ] | Revit 2026 installed as well, if Autodesk's trial allows both on the one machine (otherwise note that it did not) | The add-in is built twice: .NET 8 for Revit 2026, .NET 10 for Revit 2027. See the first check the trial settles, section 7 |

**Worker smoke test** (from the clone, venv active). Type or pipe one request per line; each gets one answer line:

```
python -m design_checker serve
{"id": 1, "cmd": "hello", "protocol": "1.0"}
```

Expected answer: `{"id": 1, "ok": true, "result": {"protocol": "1.0", "site_schema": "gordium.site/1", ...` with
a `worker_fingerprint` and a `rulebook` entry for `new_york/ithaca_city`. An unknown command answers
`{"id": 2, "ok": false, "error": "unknown command ..."}` and the worker stays up. This was run on the Mac when this
page was written. End it by closing its input (Ctrl+Z then Enter on Windows).

**The scene's facts and verdicts.** `check_site` needs the lot facts the architect states, and the suite compares the
answer with hand-worked verdicts. Neither is in a committed file; both come from the scene in Python. On the Mac or
the VM (venv active), for scene 01:

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

| Day | Do | Done when |
|---|---|---|
| 1 | Section 2 in order, Revit last: Parallels, Windows, Python, the clone, `pytest`, conformance and the worker smoke test. Then install Revit and start its 30-day clock (only once at least the Snowdon Towers sample is on the VM: Open items 1). Open Autodesk's Snowdon Towers sample (`Snowdon Towers Sample Architectural.rvt`, saved in Revit 2024; Revit upgrades it on opening) and use it for half an hour: orbit, select, edit a wall. Note memory use in Windows and on the Mac (Activity Monitor) | Setup list ticked; first Q1 numbers written down |
| 2 | Open Snowdon Towers and each architect model already in hand, timing the open. Use each for a while as an architect would. Decide Q1 for Revit alone on those: go, or switch (section 6); the add-in half is re-checked on day 4. An architect model arriving later is timed when it arrives, and can reopen Q1 | The models in hand open; Q1 has a yes or no, with numbers, and says which models it rests on |
| 3 | Make the smallest add-in that loads in Revit 2027 and adds one ribbon button (nothing else). Build it twice, like the worker client (`net8.0` and `net10.0`). Confirm which .NET runtime Revit 2027 and 2026 load (Revit 2026's may be .NET 10 after an update: section 7), and which build each loads | The button appears in both Revit versions, the note says which build each loaded, or which version refused it |
| 4 | Use the worker client, `Gordium.Worker` ([apps/revit_addin](../../apps/revit_addin/README.md): already tested against the real worker on the Mac), for all of this. The button starts the worker (venv Python, clone as working folder, `serve`), sends `hello`, shows the `about` fingerprints in a message box, and stops the worker when Revit closes. Then send `check_site` with `test_data/host_conformance/expected/01_box_house.site.json` as the `site` and the scene's facts (see "The scene's facts and verdicts" below) | Q2 answered. The `check_site` answer's rows are exactly the scene's expected verdicts. Q1 re-checked with Revit, the add-in and the worker all running (the second memory row in section 5) |
| 5 | Reading, part 1: a hand-built scene model for scene 01 (box house). The add-in walks its solids and writes a site description: lot, building faces in feet, ids from `UniqueId`. Start from the [reading design note](revit_reading_design.md): how a Revit element maps to a building, what each of the Rhino layers the scenes use (Building, Site, Gordium::Context, Gordium::Grade, Terrain, Default) becomes in Revit, and how the lot outline is found (by default the architect picks a closed outline, the picked-lot flow; reading the property line directly with `PropertyLine.GetBoundary` works only in Revit 2027). Write into the notes where the trial confirms or changes it, and settle its "to check" items as they come up | Scene 01 recorded and passes (section 4): its own `OK  recorded/revit/01_box_house` line appears. Until all 15 drawn scenes are recorded, the run still ends `FAILED`, with a `revit: no recording for ...` line naming the scenes not yet done; that line is expected, not a failure of scene 01 |
| 6 | Reading, part 2: scenes 02 to 06 (curved wall, open solid, block, garage left out, no grade) | Each recorded and passing (its own `OK  recorded/revit/...` line; the `no recording for` line shrinks) |
| 7 | Scenes 07 to 12 (spot grades and the move, millimetres, two lot outlines, survey coordinates, corner lot, ids after an edit) | Each recorded and passing, or the failure explained in the notes |
| 8 | Scenes 15 to 17 (left-out objects, terrain mesh, curved lot line). Then point the add-in at real model 1 (if no architect model has arrived, Snowdon Towers, recorded as provisional): read it, send it, look at the verdicts. Time every stage (section 5) | The Model 1 column (or the Snowdon column) of the Q3 table filled in |
| 9 | Real models 2 and 3. For each: flat versus curved faces, `UniqueId`s before and after a small edit, units, survey coordinates. Any not yet arrived: its row says so, and Q3 stays open (the trial is not extended for it; Ben decides when it arrives) | The Model 2 and 3 columns filled in, or marked not arrived |
| 10 | Timing runs: the edit loop on every model in hand (Snowdon Towers too), five repeats each. Re-run `python -m design_checker.conformance` on the Mac with the final recordings | Section 5 complete |
| 11 to 12 | Spare. Re-record anything that failed; chase the worst timing; test the other Revit version if only one was used | |
| 13 | Write the go / no-go: answer Q1 to Q5 in section 1 with the numbers, list what surprised us, and what the add-in MVP plan must change | The section 5 tables filled in and signed off by Ben |
| 14 | Commit the recordings and results in a PR (never push to main; Ben merges) and hand the machine back or shut the cloud VM down | PR open |

## 4. Recording the scenes from Revit

The rules are the [conformance README](../../test_data/host_conformance/README.md)'s "How to add a host". The
details that matter here:

- **15 scenes are drawn and recorded; 2 are not.** Scenes 13 and 14 are description-only (they have `site:`
  instead of a drawing) and are never drawn. Scenes 07 and 12 also have a step "after the edit", so the 15
  recordings hold 17 descriptions: 15 "as drawn" and 2 "after the edit". A host with any recording must have one
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
- **One `ids` map serves every step.** For scenes 07 and 12, make the edit in Revit by moving the elements (the
  YAML's `then.move` gives how far; do not redraw them), then record "after the edit". A UniqueId that changes at
  the edit fails the scene.
- **Scenes that need a Revit-specific decision** (write the decision into the notes, and into the PR; the
  [reading design note](revit_reading_design.md) proposes one for each, with the scene that tests it):
  - *04 (a block on the Building layer):* "a block" is whatever Revit cannot send as a solid (for example a family
    instance the add-in cannot read). Either send it as `unsent`, or as a building with no faces and `not_a_solid`.
  - *15 (a block off the Building layer):* the shed block is on the Default layer, so it is not a building and is
    not `unsent`: list it under `left_out` (`could_be_building` true, `touching` false), as for the porch and the
    neighbourhood-layer solid in the same scene.
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

Fill these in as you go; this page is where the results live. "Mac" below means the Parallels VM host.

**The machine** (day 1)

| Item | Value |
|---|---|
| Parallels version | |
| Windows 11 ARM build | |
| VM cores, RAM, disk | |
| Mac RAM used by Parallels while Revit is open (Activity Monitor) | |
| Revit version(s) installed | |
| .NET runtime each Revit version loads | |
| Python and `pip` versions in the VM | |

**Q1: is Revit usable here** (days 1 to 2)

| Check | Value | Usable? |
|---|---|---|
| Revit start to ready | | |
| Open Snowdon Towers; real model 1 / 2 / 3 (those in hand) | | |
| Orbit and select in each model in hand: smooth, laggy, or unusable | | |
| Memory pressure on the Mac (Activity Monitor: green, yellow, red), Revit alone (day 2) | | |
| Memory pressure on the Mac, Revit with the add-in and the worker running (day 4) | | |
| Windows free RAM with Revit open | | |

**Q2: the worker from the add-in** (days 3 to 4)

| Check | Value |
|---|---|
| Worker start to first `hello` answer | |
| `check_site` for the box-house scene, round trip | |
| Same rows as the Mac? | |
| Worker stops when Revit closes? | |

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
| Scenes recorded (of 15) | |
| Scenes passing `python -m design_checker.conformance` | |
| Scenes that failed, with the reason for each | |

## 6. Stop and switch criteria

These are proposed numbers for Ben to confirm or change before day 1. They are limits to decide on, not measured facts.

| If | Then |
|---|---|
| By the end of day 2, opening a model (Snowdon Towers or an architect's) takes longer than 3 minutes, orbiting is unusable, or the Mac's memory pressure stays red with only Revit running | Switch to a cloud Windows machine (a Windows VM with 32 GB or more) and restart the setup list there (Revit's licence there: Open items 3). Keep the days already spent; do not extend the two weeks for the switch more than 2 days |
| Revit runs but the add-in plus Revit pushes the Mac into red memory pressure | Same switch. Q1 is "no" for the 16 GB Mac, whatever else the trial finds |
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
2. **A Windows ARM machine** (Parallels on the Mac, per the plan taken on 2026-11-05). The Autodesk account for the
   30-day Revit trial is in hand (Ben, 2026-11-11; its login is kept outside the repo, never in it).
3. **The cloud Windows option**, decided up front so a switch on day 2 costs no time: which provider, and who
   pays, and how Revit is licensed there. The setup list ends with installing Revit, and whether Autodesk allows a
   second 30-day trial on the same account, or moves the first, was not checked; if not, the cloud machine needs
   its own trial account or a paid licence.
4. **Which branch the trial clones.** This page sits on the tidy-up stack's top branch (PR #78); the trial needs
   the stack merged, or that branch, since `recorded/revit/` and the conformance command only exist there.
5. **Confirm the numbers in section 6** (3 minutes to open a model, 2 and 10 seconds per edit).

**Checks the trial itself settles** (nothing in the repo answers them today):

- Which .NET runtime each installed Revit loads, and so which build. Revit 2027 runs on .NET 10 (Revit 2027
  "What's new": [Migrating Revit to .NET 10](https://help.autodesk.com/cloudhelp/2027/ENU/Revit-WhatsNew/files/GUID-8D7A4715-EAF8-4BD1-BE78-061F900D0BCE.htm)); Revit 2025 and 2026
  are built on .NET 8, and Autodesk plans to move them to .NET 10 ([call for preview testing](https://blog.autodesk.io/call-for-preview-testing-revit-2026-2025-migration-to-net-10/),
  2026-04-29: a Revit 2026 preview on .NET 10 tested until 2026-06-03, no release date). So the worker client is built
  and tested for both; note the Revit 2026 update installed and the runtime it reports. Whether the .NET 8 build also loads in Revit 2027 is not settled by Autodesk's pages either.
- Whether ARM builds of `rhino3dm`, `shapely` and `numpy` exist, if we ever want a native ARM Python.
- Which survey coordinates the description carries (scene 10), and what each Rhino layer becomes in Revit: the
  [reading design note](revit_reading_design.md) proposes both, and lists the rest of its "to check" items.

**Where the facts above come from.** Checked on 2026-11-05 on Autodesk's pages and the projects' own documents:
Autodesk lists Parallels Desktop on Apple silicon as supported for Revit 2027 and recommends 32 GB of RAM; Revit has
a 30-day free trial; `PropertyLine.GetBoundary` exists only in the Revit 2027 API; Rhino.Inside.Revit has no
stable Revit 2027 release and pyRevit v7's CPython is experimental, which is why the add-in is C# talking to the
same Python worker. CI already runs the tests on Windows (`.github/workflows/ci.yml`, job `windows`). The commands
and file layouts above were read from the repository, and the worker, its BOM refusal and the conformance command
were run on the Mac.
