# PR #32 checked in Rhino at 6ba061b: progress and Cancel

**Purpose:** what `progress_cancel_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26, and the wait window watched on screen.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Result

| Run | Claims |
|---|---|
| As written | 18 of 19, then it stops: claim 5 fails ("a background re-check started…": `{'ticks': 127, 'panel': []}`) |
| Copy that records every claim | still stops at claim 5: `job` is None (`'NoneType' object has no attribute 'cancel'`) |
| **Copy whose wait loop calls the plugin's `_idle()`** (`progress_cancel_results.json`) | **26 of 26**, run twice |

## Why claims 5 and 6 can't pass as written (a test-script problem, not the plugin)

- Live mode starts its background re-check only from Rhino's **Idle** event (`_idle` is the only caller of
  `_check_live`).
- Rhino raises no Idle while a script runs, even inside `RhinoApp.Wait()`. So in `pump_until` the edit is noticed,
  but no re-check ever starts.
- The copy adds one step to `pump_until`'s loop: while live mode is on, it calls `g._idle(None, None)`, standing in
  for Rhino's Idle. Nothing else changed.

With that, all of these pass:

- **5:** the re-check runs in the background, and the panel line moves ("Slow test: waiting… ●○○ 0 s", then
  "○●○"). Cancel says "Check cancelled", draws nothing, and leaves nothing running.
- **6:** an edit during a re-check drops the stale answer, and the model is checked again and shown.
- **7:** the lookup's Cancel works.
- **New 2b passes:** an edit made while a check waits drops its answer, and nothing is shown as checked.
- **"Draw again after cancel draws the house" passes** (4).

## Second test-script bug: it leaves its document open

At the end the script closes `OpenDocuments()[:-1]`, every document but the last. Here the last was its own test
document (`progress_cancel_Large_Objects_-_Feet.3dm`), which stayed open and on screen after both full runs. I
closed it with the test-docs leftovers rule. The script should close the documents it opened.

## The wait window, by eye (`wait_window_sheet.png`, `onscreen_windows_log.json`)

On-screen windows were logged every 0.27 s (only windows really on screen), and each wait window was captured.

- **It animates.** The mark moves (●○○, ○●○, ○○●), the step changes ("Slow test: waiting…", then "Checking the
  rules…") and the seconds count. 41 of 67 consecutive captures differ.
- **It closes at once.** Each time, the window was off screen by the next sample, within 0.3 s of its last frame.
  No window stayed open after its work ended, and none was left at the end. The exact gap between pressing Cancel and
  the close can't be timed from outside Rhino; claim 2 shows `run_check` returns within 2.5 s of Cancel.
- The window reads clearly: what it is doing, a moving mark with seconds, and one Cancel button.
