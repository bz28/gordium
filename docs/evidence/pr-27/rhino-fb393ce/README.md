# The Check button (PR #27) at fb393ce: checked in Rhino 8 (Mac), 2026-10-26

**Purpose:** `check_button_in_rhino.py` at this head.\
**For:** the coordinator, the #27 job, reviewers.\
**Kept current by:** never changed (a dated record).

Run as written, waiting for `"done": true`: **6 of 6** (`check_button_results.json`). Check first beside Edit
site… with "Check after every edit" unticked; an edit and real idle (33 idle events in 3.3 s, the stale branch ran):
no check, the header says press Check, the rows greyed, the status box says it too (`2_changed_press_check.png`);
Check: one check, the rows current (`3_checked.png`); ticked: saved, and an edit is checked by itself (8 idle events
in 3.4 s; `4_checked_by_itself.png`).
