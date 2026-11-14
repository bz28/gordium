# Plain panel words: Rhino 8 evidence

**Purpose:** the in-Rhino record of the panel's list before (main) and after the plain-words change: the Delta column, a rear yard's span, and Check's line on the command line.\
**For:** reviewers and engineers.\
**Kept current by:** never (a dated record).

Run in Ben's Rhino 8 on 2026-10-29. Later wording fixes from review rounds 2 and 3 ("at limit if confirmed", "at limit at worst", "see why" on a failing row) change no cell on this lot and are pinned by unit tests (`test_present.py`), not re-captured. The runs used extracted copies: main at ad164beb and this branch at 1fa72c09 (the command history and the rows that comply) and 62950a79 (the rows in review, after review round 1's fix to the list's short Delta). The script looks up 106 Ithaca Rd (R-1b, tax-map lot lines ±2 ft), draws the starting house, writes "Cancelled: nothing changed." as an earlier button would, then presses Check. It records every list cell, whether the cell fits its column, and the last lines of Rhino's command history.

| File | What it shows |
|---|---|
| `before_main_needs_review.png`, `before_main_complies.png` | Main: the rear yard shows a range in both Proposed and Required. Delta shows only the worst case ("≥ +0'-5¼" if confirmed", "≥ +357 sf"). |
| `after_needs_review.png` | This branch at 62950a79: the rear yard shows its tightest pair ("36'-3⅜" (varies)" against "32'-10⅛" (varies)"). A row in review with room under every reading shows its certain room "if confirmed" ("worst +0'-5¼" / if confirmed"), never a bare "+". |
| `after_complies.png` | This branch at 1fa72c09: a row that complies shows the margin as drawn, then the worst case if the tax-map lines are 2 ft off ("+1,033 sf / worst +357 sf"). These cells are the same at 62950a79 (`after_out.json`). |
| `before_main_out.json` | Main: every list cell. (On main, Check writes nothing to the command line, so the last Gordium line stays "Gordium: Cancelled: nothing changed.".) |
| `after_out.json` | This branch at 62950a79: every list cell, none cut short (`cut` all false for the Proposed, Required and Delta columns). Its `command_line_last` was read inside the run script, before Rhino's history window filled in, so it does not show Check's line yet. |
| `after_command_history.json` | This branch at 1fa72c09 (Check's line is unchanged since): Rhino's command history read by a second script after the run. It ends "Gordium: Cancelled: nothing changed." then "Gordium: 3 need review · 9 comply · 2 not checked · 3 use details to answer", so Check's words are the last Gordium line. |
