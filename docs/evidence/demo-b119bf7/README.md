# The demo update in Rhino: the start box fits a laptop (2026-10-27)

**Purpose:** the in-Rhino record of demo b119bf7 (the #37 start-box fix and the three script fixes) before cofounders pull it.\
**For:** Ben and the reviewers. A dated record; never updated.

Rhino 8 on Ben's Mac, one instance, each script on a fresh feet document it closes, run from an extracted copy of
b119bf7 (demo 2c0a5c0 + use-questions 55f54ce + the #28 and #33 script fixes + DEMO.md).

| Run | Result | Notes |
|---|---|---|
| Start box, R-1b and R-3b, one-family detached (`box_shots.py`, `R-1b_box.png`, `R-3b_box.png`) | 780 px wide both | R-1b 631 px tall with its 7 questions, R-3b 544 px with 5. Was 1,563 px wide at 2c0a5c0. Each question wraps beside its answer; one note under them. |
| Demo smoke (empty file, Draw, house moved 5 ft, front yard fails, Zoning report opens on Check; `smoke.json`) | 7 / 7 | |
| `use_questions_in_rhino.py` (#37) | 6 / 6 | Claim 6: every district's box for its first use is 780 px wide (R-1a/R-1b 631 px tall, R-2c 595, the rest 544). Was 3 / 5. |
| `offending_part_in_rhino.py` (#28) | 23 / 23 | The side yard row is found by what it measures ("Side yard, narrower" in case 1, "Side yard, Southwest" in case 2). Was 20 / 23. |
| `autocomplete_in_rhino.py` (#33) | 15 / 15 | "Model unchanged" leaves out the Envelope layer each check redraws; claim 7's box is 780 px wide. Was 10 / 11. |

Headless scripts (coordination/headless) still don't load the demo: their stand-ins lack #32's `_ask_waiting` /
`_still_front` and RhinoCommon's `BeginUndoRecord` / `Command.UndoRedo`, and the harness pulls named functions out of
the plugin, so each new helper needs adding there. Recorded in STATUS (owner #32); not counted.
