# The sixth demo update in Rhino (2026-10-27)

**Purpose:** the in-Rhino record of the demo build before cofounders pull it.\
**For:** Ben and the reviewers. A dated record; never updated.

Rhino 8 on Ben's Mac, one instance, each script on a fresh feet document it closes. Code under test: the demo
merge at f4ab8b3 (smoke and the five PR scripts) and fd924dd (after the one merge fix below; the re-runs and the
districts check). The demo head 2c0a5c0 adds only DEMO.md to fd924dd.

| Run | Result | Notes |
|---|---|---|
| Demo smoke (`1_smoke/`: GordiumStart on an empty file, Draw, house moved 5 ft, front yard fails, Zoning report opens on Check) | 7 / 7 | |
| `massing_in_rhino.py` (#35) | 8 / 8 | |
| `progress_cancel_in_rhino.py` (#32) | 21 / 21 | |
| `offending_part_in_rhino.py` (#28) | 20 / 23 | the 3 fails are case 1's: with #18's readings of 106 the cantilever's row is "Side yard, narrower" (and front/rear need review too); the script looks for "Side yard, Southwest". Its cantilever piece is amber as intended. Script, owner #28 (carry #18). |
| `use_questions_in_rhino.py` (#37) | 3 / 5 at f4ab8b3 and fd924dd | claim 1: R-1b now asks #38's household and home occupation questions (expected: #37's box asks what the rules need). Claim 3: the script finds "Dwelling units" by its old label (#24 lengthened it). At f4ab8b3 claim 3 also showed a MERGE BUG: the yes / no dropdown's first entry read "The lookup of {address} didn't finish…" (rhino_logic defined NOT_ANSWERED twice, #26 and #37): fixed in fd924dd, pinned, "Not answered" again. |
| `autocomplete_in_rhino.py` (#33) | 10 / 11, stopped at claim 7 | "model unchanged" counts Gordium::Envelope's snap curves (#34), which every check replaces with new ids; with them left out (`autocomplete_diag_in_rhino.py`) claim 7's message passes, then "the box stays under 1,200 px wide" FAILS: 1,563 px (2,021 px in the first run). |
| R-2a and R-3b (`3_districts/`): start box set to the district, Draw, Check | 6 / 6 | R-2a: 5 need review, 9 comply, 2 not checked; R-3b: 5 / 8 / 2. In both, One-family occupancy, Home occupation and Home occupation size are needs review, each waiting for its facts. |

PRODUCT BUG (not fixed in the demo: owner #37, with #38's labels): the start box's questions under Use are long
sentences laid out without wrapping, so with R-1b's seven household / home occupation questions the box is about
1,560 px wide (wider than a 1,470-point laptop screen). DEMO.md says so under Known limits.

Headless scripts (coordination/headless): they no longer load this build (their stand-ins lack #32's `_ask_waiting`
/ `_still_front`, `Command.UndoRedo`, `BeginUndoRecord`): 0 of 36 / 0 of 4 / setup failed / 0 of 10, all harness.
