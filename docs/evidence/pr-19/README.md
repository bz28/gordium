# PR #19 evidence: the start box and live mode, in Rhino 8 (Mac)

**Purpose:** what PR #19's in-Rhino scripts proved (the start box, the address lookup, live mode), with their results and screenshots.\
**For:** reviewers checking PR #19; engineers.\
**Kept current by:** never (a dated record); a new in-Rhino run gets its own folder.

Recorded 2026-10-21 on start-box-lookup at d6cd34f, plus this commit's test fixes. Each script asserts every claim it
makes and fails loudly otherwise; each closes the documents it opens.

| File | What it proves |
|---|---|
| `pr19_checks_results.json` | `apps/rhino_plugin/tests/pr19_checks_in_rhino.py`: 12 claims, all true. (1) While a start box is open, Edit site… only says "Finish or cancel the open start box first"; every other panel action (taken from `PANEL_ACTIONS`, so new ones are covered: add, enter, envelope, grade, ground, massing, not_ground, report, retry, survey, zoom) only says the same and does nothing; the legend still runs, the panel's controls are off. (3) No check runs while the box is open (live mode's idle re-check keeps the pending edit) and exactly one runs after it closes. (4) After closing with nothing selected, Zoom to stays off and the other controls are back on. (5) With a pending edit, the document in front is re-checked even though another document was checked after the edit. |
| `1_one_box_panel_greyed_legend_on.png` | The panel while a real start box is open: buttons, ticks, the detail pane, Zoom to and Zoning report… greyed; the "?" legend on. |
| `1_after_the_box_panel_back.png` | The same panel after the box closed: controls back. |
| `box_transaction_results.json` | `apps/rhino_plugin/tests/box_transaction_in_rhino.py`, all true: Cancel through the real box leaves the same objects, ids and layers; a looked-up lot sets the sample lot aside (held, never deleted); a re-lookup keeps only the new lot's spot grades; Cancel after it restores everything; after a session Rhino never finished, recovery puts the model back; the City-outline guide case writes no lot. |
| `2_lookup_106_sample_lot_set_aside.png` | Top view after looking up 106 Ithaca Rd: the looked-up lot and its USGS spot grades; the sample lot held. |
| `2_cancel_model_exactly_as_before.png` | Top view after Cancel: only the sample lot, exactly as before. |
| `2_relookup_109_only_its_spot_grades.png` | Top view after looking up 109 Ithaca Rd in the same session: its lot and only its 6 spot grades. |
| `2_city_outline_guide_only.png` | Top view when the State's parcels didn't answer: the City's outline as a dashed guide only, no lot written. |
| `mvp_lookup_results.json` | `apps/rhino_plugin/tests/mvp_lookup_in_rhino.py` on e5fb0be (this PR merged with #15's MVP), 7 claims, all true: after Look up "106 Ithaca Rd" and Draw, the box has no Ground row (flat ground); the lookup's tax-map lot carries its turn from north (plan_north_deg 306.38), so the side yards read Southwest and Northeast; the panel is Rhino's docked panel; the header says "Ground: assumed flat"; every Delta is in words and never kinder than its row. Its "controls off while the box is open" claim held vacuously (no panel yet in a fresh document); the script now opens the panel first and needs a non-empty, all-off list (to be re-run; `pr19_checks_results.json` proves it with a panel). Run by the Rhino job, 2026-10-21. |
| `mvp_lookup_106_after_lookup_top.png` | Top view after that lookup and Draw. |

### The district box after a lookup with no rules (zone review rounds 1 and 2)

Recorded 2026-10-22 in Rhino 8 (macOS) on start-box-lookup at 7efb1bd by the Rhino job: the real start box driven
through its own controls (address typed, Look up, the dropdown, I confirm, Draw, Edit site… to reopen), never the
scripted path; recorded lookup answers (106 Ithaca Rd) with the City map's district set per case.

| File | What it proves |
|---|---|
| `r2a/r2a_results.json` | 8 of 8 claims true, with what each box showed at each stage. The map says R-2a (no rules in Gordium): nothing preselected, the row reads "not set", the line says "The City map says R-2a; Gordium doesn't have R-2a's rules yet: pick a district only if you know it applies.", Draw off with "Pick the district to continue."; picking R-1b turns the source into "entered by you" at once; ticking turns Draw on; reopened after Draw: "R-1b · entered by you". The map says R-2a and R-1b: nothing preselected, the box asks which zone applies. The map says R-1b: "suggested by Gordium · City zoning map says R-1b (checked 2026-10-20)", the dated words gone on reopen. |
| `r2a/1_r2a_after_lookup.png` … `r2a/7_reopened_suggested.png` | The box at each of those stages. |
