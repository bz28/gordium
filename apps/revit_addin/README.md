# Gordium in Revit: the worker client

**Purpose:** the C# library the Revit add-in uses to start Gordium's checker and talk to it, what it does when something goes wrong, and how we know it works.\
**For:** engineers writing the Revit add-in; reviewers checking that nothing the checker sends can turn into a pass it didn't give.\
**Kept current by:** every PR that changes this library or a protocol command it sends.

Gordium's checker is Python. Revit add-ins are C#. So the add-in runs the checker as its own process, the
**worker** (`python -m design_checker serve`), and sends it one request per line, as the
[worker protocol](../../docs/protocol/worker_protocol_v1.md) says. Why it works this way, rather than any other way
into Revit: [the decision of 2026-11-06](../../docs/decisions/2026-11-06_hosts_talk_to_the_worker.md).

This folder holds the half of the add-in that doesn't need Revit: `Gordium.Worker`, a class library that starts
the worker and speaks the protocol. It references no Revit API and no packages (only System.Text.Json, part of
.NET), so it is built and tested on the Mac and in CI. It targets .NET 10: the plan (Ben, 2026-11-05) is one .NET 10
build for Revit 2026 and 2027, and whether Revit 2026 loads it is one of the checks the Windows trial settles. If it
doesn't, the library needs a second target, and its refusal of a key given twice in an answer
(`AllowDuplicateProperties`, new in .NET 10) needs another way on the older one. The add-in itself
(the ribbon button, reading the model) comes later, in the [Windows trial](../../docs/revit/windows_trial_runbook.md).

## What it does

```csharp
using var worker = await WorkerClient.StartAsync(new WorkerOptions
{
    PythonPath = @"C:\gordium\.venv\Scripts\python.exe",   // the clone's venv
    WorkingDirectory = @"C:\gordium",                       // the clone: the worker reads its rulebooks
});
var result = await worker.CheckSiteAsync(site, facts);     // site: a gordium.site/1 description
foreach (var row in result.Items)
    Console.WriteLine($"{row.Name}: {row.Status}");        // Complies, DoesNotComply, NeedsReview, NotChecked
```

1. **Starts the worker and says `hello`.** A worker that doesn't speak protocol 1.x, or reads a site description
   other than `gordium.site/1`, is refused (each side refuses a different major version). Every later answer's
   `about` is checked the same way.
2. **Sends one request per line,** UTF-8 without a byte-order mark (the worker refuses one) and in fact plain
   ASCII (any other character is written as a JSON `\u` escape, so no code page can change it), each with the next id,
   `"protocol": "1.0"`, and only the fields the caller gave (an optional field left null is not sent).
3. **Typed commands:** `HelloAsync`, `CheckSiteAsync`, `StartSiteAsync`, `ReadModelAsync`, and `SessionAsync` for
   the 19 session commands (the start box, the panel, the live check's decisions), each answer read by name with
   `Get`. `StartSiteAsync` and `ReadModelAsync` give their result as JSON (a building's floors, a site
   description: no verdicts). `SendAsync` is only for a command a later 1.x worker adds: it refuses every command
   above, so a check's or a session command's answer is always read strictly. The older commands (`check`,
   `start`...) are Rhino's and are not sent.
4. **Reads every answer strictly.** The answer must be JSON, this request's id, `ok` true or false, with its
   `result` and `about`. A check's every row must have an id, a name, a group, a reason (text or null) and one of
   the checker's four statuses; a row given twice, a key given twice, NaN, or a check with no rows is an error. A
   check whose overall state says it complies must have its rows back that (none failing or needing review apart
   from the rules not in Gordium yet, no use detail waiting, at least one row complying), or it is refused. That
   last part is stricter than the worker's own overall state, which would say "complies" for a check whose rows
   are all "not checked" (no real check is known to give one): such an answer is an error, never a pass.
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

- **Every conformance scene** (`test_data/host_conformance/`: 17 scenes, 19 steps): `check_site` with the scene's
  expected description and facts gives exactly the hand-worked verdicts, every row and no row more. The facts and
  verdicts come from the scene files through the conformance suite's own code (`scene_cases.py`), never retyped.
- **`hello`, an unknown command, bad facts, session commands** (a constant, a refused part, `want`, an unknown
  field), and **`start_site`**, on the real worker.
- **The worker killed mid-session:** a clear `WorkerExitedException` within seconds, never a hang or an answer.
- **Every way an answer can go wrong**, given on purpose by `fake_worker.py`: protocol 2.0, another site schema,
  a missing status or one Gordium doesn't give, a row without its id, name, group or reason, no summary or state,
  a key twice, NaN, no rows, a row twice, no `about` or a wrong one on a later answer, another request's id, text
  that isn't JSON or UTF-8, a crash, a hang, a worker that stops reading, a cancel. Each is an error and stops the
  worker.
- **What is sent:** no byte-order mark, only ASCII bytes, one line per request, ids 1, 2, 3..., non-English text
  intact.
- **The protocol copy:** the session commands and their answer names equal the protocol document's command
  reference (a Python test keeps that equal to the worker's own table).

The main guards (the status words, the empty and repeated rows, a key twice, the versions, `about`, the id, the
byte-order mark, a refused part, half an answer, stopping after a timeout) were each undone once to check that
their test then fails.

## Running it

Needs the .NET 10 SDK and a Python with Gordium installed (`pip install -e ".[dev]"` at the repository root).

```bash
cd apps/revit_addin          # dotnet reads global.json (the pinned SDK) from the folder it runs in
GORDIUM_PYTHON=/path/to/.venv/bin/python dotnet test
```

`GORDIUM_PYTHON` defaults to `python` on the PATH. CI runs it on Windows and Ubuntu (`.github/workflows/ci.yml`,
job `revit_worker_client`). The test packages are pinned to exact versions, with lock files (`packages.lock.json`);
CI restores in locked mode.
