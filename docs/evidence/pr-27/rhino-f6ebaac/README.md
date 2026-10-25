# The Check button (PR #27) at f6ebaac: checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** the re-run of `check_button_in_rhino.py` after it was made to run in phases.\
**For:** the coordinator, the #27 job, reviewers.\
**Kept current by:** never changed (a dated record).

Run as written, started the way the Script Editor starts it (Rhino's `rhinocode`), waiting for `"done": true`:
**6 of 6** (`check_button_results.json`).

| Claim | Result |
|---|---|
| 1 Check first beside Edit site…, and "Check after every edit" unticked | pass |
| 2 an edit, then idle: no check ran | pass |
| 2 the header says press Check and the rows are greyed | pass |
| 2 the status box says it too | pass (`2_changed_press_check.png`) |
| 3 Check: one check, the rows current again | pass (`3_checked.png`) |
| 4 ticked: saved, and an edit is checked by itself | pass (`4_checked_by_itself.png`) |

Rhino really went idle in each wait: step 2 saw 33 idle events in 3.2 s, and the stale branch ran. Step 4 saw 6 idle
events in 3.4 s, and the automatic check ran. The one-script version's problem at ea88c18 is gone.
