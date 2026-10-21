# PR #23 (the context map): evidence from Rhino 8 (Mac), 2026-10-21

**Purpose:** what the scripted Rhino check of the neighbourhood map proved, with its results and screenshots.\
**For:** reviewers, engineers, Ben.\
**Kept current by:** never changed (a dated record); a later run is added beside it.

`apps/rhino_plugin/tests/context_in_rhino.py`, with the recorded answers for 106 Ithaca Rd (no live calls): 9 of 9
claims true (`context_results.json`).

| Claim | Result |
|---|---|
| 1 The neighbourhood is drawn on its own locked, grey layers: Parcels, Streets, Notes | 229 neighbouring parcels, 38 street lines; each layer locked, visible, in its grey |
| 1 The notes: a north arrow, a scale bar and the sources | All three on the Notes layer |
| 2 The building footprints are on screen | 212 footprints, shown live |
| 3 The checker never measures the context | One lot candidate; the check's summary is the same with and without the neighbourhood |
| 3 Drawn again, it replaces | The same object counts, never doubled |
| 4 The panel tick hides it and shows it again | Every context layer hidden, then shown |
| 5 A saved file keeps no live-only source | No footprint (store: none) in the saved .3dm |
| 6 A second address clears the first neighbourhood | Edit site…, 109 Ithaca Rd: the frame changed, nothing of 106's left (109 has no recorded neighbourhood, so none is drawn and Gordium says why) |

| File | What it shows |
|---|---|
| `106_context_top.png` | Top view: the neighbourhood around 106, north arrow and scale bar |
| `106_context_perspective.png` | The same in 3D |

Seen in the screenshots, not covered by a claim (reported for this PR):
- the sources note is one long label that runs off the left edge of the view in both views;
- in Top view the lot's edge-length labels pile up in a column (the label placement this branch inherits; the
  MVP branch places each label beside its own line).
