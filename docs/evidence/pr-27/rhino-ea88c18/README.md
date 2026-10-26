# The Check button (PR #27) at ea88c18: checked in Rhino 8 (Mac), 2026-10-25 (RHINO_QUEUE 12)

**Purpose:** what the Rhino job's runs of `check_button_in_rhino.py` showed.\
**For:** the coordinator, the #27 job, reviewers.\
**Kept current by:** never changed (a dated record).

| Run | Result |
|---|---|
| `check_button_in_rhino.py` as written, one script (`one_script_run_results.json`) | stops at "2 the header says press Check and the rows are greyed" (2 of 3 claims run passed) |
| The same claims in phases, Rhino really idle between them (`check_button_phases_in_rhino.py`, `phased_run_claims.json`) | **6 of 6** |

**Why the one-script run fails: the test, not the plugin.** The script waits for Rhino's idle by looping on
`RhinoApp.Wait()`. While a script runs, Rhino never raises its Idle event, and the plugin's idle handler is what
greys the panel and runs the automatic check. A probe (`idle_probe_results.json`) shows the edit was recorded
(`dirty` set), 3 s passed, the panel was visible and no command was running. Yet the handler's stale branch never
ran (`stale_shown` null), and claim 4's automatic check didn't run either. The status box claim passes there
because the status box works out "out of date" from the clock as it draws.

**The phased run** ends the script after each step and lets Rhino go idle for real, the way the re-lookup check now
runs after its launching command:
- After the floor moved 3 ft and real idle, no check ran. The panel's header says "Model changed since the last
  check — press Check" and the rows show no marks ("—"). The status box rows say the same. See
  `2_panel_press_check.png`, captured from outside after the script ended; on-screen labels are off in this file,
  so the viewport shows no status box (`2_document_press_check.jpg`).
- Check pressed: one check, and the rows are current again (`3_checked.png`).
- "Check after every edit" ticked: saved in the file. A floor moved, then real idle: checked by itself (2 checks in
  all, `4_checked_by_itself.png`). Unticked again at the end.

Suggested for #27: run the script's steps 2 and 4 across real idle (end the script, continue at the next idle, as
`re_lookup_in_rhino.py` does now), or use the phased copy here.
