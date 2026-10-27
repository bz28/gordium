# The feature stack #28 to #35 in Rhino 8 (Mac), 2026-10-26

**Purpose:** the in-Rhino scripts of #28, #29, #31, #34 and #35, run on one build each, with each claim's result.\
**For:** the coordinator, the UX builder, Ben.\
**Kept current by:** never changed (a dated record).

Planned: every script on one build, massing-floors f45c991 (#35's head, which contains #28 to #34). At f45c991
**every check in Rhino fails**, so #35's own scripts were run there and #28 to #34's scripts were run on
osnap-curves 0db4b5d (#34's head, which contains #28, #29 and #31 at their current heads; every one of these
scripts is the same file at both heads). Each run loaded Gordium from an extracted copy, one script at a time,
each wait capped at 10 minutes.

| PR | Script | Build | Result |
|---|---|---|---|
| #35 | massing_in_rhino.py | f45c991 | **FAIL, 5 of 8**: floors on Gordium::Massing::Floor N, one group, the Roof sublayer, the note and Hide pass; "the check measures it", "named the starting house" and "the envelope drawn is the cautious one" fail |
| #35 | wrong_document_in_rhino.py | f45c991 | **PASS** (the house only in the document in front: 3 objects, its floors on sublayers; the script records, it has no claim list) |
| #35 | (diagnosis) | f45c991 | the check's own error in Rhino: `No module named 'shapely'` (`f45c991/diag_f45c991_check_error.json`) |
| #28 | offending_part_in_rhino.py | 0db4b5d | **PASS, 23 of 23** (at f45c991: 8 of 23, the same shapely error) |
| #28 | highlight_in_rhino.py (run phase, then close) | 0db4b5d | **PASS, 19 of 19** after a one-character script fix (below); as shipped it stops after 12 of 12 with an IndexError |
| #29 | dimensions_in_rhino.py | 0db4b5d | **PASS, 26 of 26** |
| #31 | depth_in_rhino.py, Rhino left idle 12 s, depth_in_rhino_phase2.py | 0db4b5d | **PASS, 6 of 6 then 14 of 14** (`depth2/out.json` holds both phases) |
| #34 | osnap_in_rhino.py | 0db4b5d | **PASS, 10 of 10** |

## #35: a product bug, every check fails in Rhino (P0)

- Claim: "the check measures it" (massing claim 2). Expected: the sample checked, its rows in the panel. Seen:
  no rows; the check's result is `{"error": "No module named 'shapely'"}`, on every check of a tax-map lot (the
  sample included), so GordiumStart draws the house and then shows no results.
- Cause: `rhino_logic.envelope_outlines` (added in #35's 1e1582b) does `from shapely.geometry import Polygon` to
  sort the cautious outlines by area. `rhino_logic` runs inside Rhino's own Python, which has no shapely (only
  Gordium's .venv, where the checker runs, has it). CI runs `rhino_logic` in the .venv, so CI could not see it.
- Fix (for #35): sort by area without shapely (the shoelace formula on the ring), and pin it with a test that
  imports rhino_logic with shapely unavailable.
- Below #35 (0db4b5d) the same checks run normally, so the bug is #35's alone.

## #28: a script bug in highlight_in_rhino.py (not product)

- Line 216 reads `b_[8] < order`; each label record has 8 fields, so the order is `b_[7]`. IndexError after the
  first 12 claims.
- Already fixed on rhino-ui (#15, 9d021d8, `b_[7]`); highlight-offending carries the older line from 822fb6f.
  It arrives with the next rhino-ui carry into #28. Run here with only that character changed
  (`0db4b5d/highlight/highlight_b7_in_rhino.py`): 19 of 19.
- The newest highlight_in_rhino.py lives only on rhino-ui (#15); the rest of these scripts are newest on this stack.

## The second Rhino instance (an experiment Ben approved)

A second Rhino 8 (`open -n`) started but stayed on its "Please Wait…" window for over 6 minutes, never opened a
document and never answered `rhinocode -r <its id>`. It was stopped (the first Rhino untouched and answering);
memory pressure stayed normal (about 70 % free; the second instance used about 350 MB). Runs stay one at a time.
