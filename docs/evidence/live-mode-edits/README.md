# Live mode hears layer, block and units edits: Rhino 8 evidence

**Purpose:** the in-Rhino record that live mode greys its results after a layer renamed, a block edited or the units changed.\
**For:** reviewers and engineers.\
**Kept current by:** never (a dated record).

Run with `apps/rhino_plugin/tests/live_more_in_rhino.py` in Ben's Rhino 8 (2026-10-29), from an extracted copy.

| File | What it shows |
|---|---|
| `before_main_out.json`, `before_main_units_changed_not_greyed.png` | On main (ad164beb): the units changed from feet to inches without scaling; the results stayed current ("3 need review · 9 comply") although a check now gives "1 does not comply · 9 need review". |
| `after_out.json` | This branch: every claim passes (units, a layer renamed, a block's contents edited all grey the results; a colour change and a hide-and-show do not). |
| `1_units_changed_greyed.png`, `2_layer_renamed_greyed.png`, `4_block_edited_greyed.png` | This branch: the Top view greyed (no marks) after each edit, until Check. |
| `1_checked_in_inches.png` | After Check in inches: the new result drawn. |
