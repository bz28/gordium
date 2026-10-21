# PR #23 (the context map): evidence from Rhino 8 (Mac), 2026-10-21

**Purpose:** what the scripted Rhino check of the neighbourhood map proved, with its results and screenshots.\
**For:** reviewers, engineers, Ben.\
**Kept current by:** never changed (a dated record); a later run is added beside it.

The test as run: this commit's `apps/rhino_plugin/tests/context_in_rhino.py` (b8322b6, with its own-axes measurement
of turned text), with the plugin at b908e99 and the recorded answers for 106 Ithaca Rd (no live calls): **11 of 11
claims true** (`context_results.json`). The first run (9 of 9, before the sources note was fixed) is in git history
at 0e88250.

| Claim | Result |
|---|---|
| 1 The neighbourhood is drawn on its own locked, grey layers: Parcels, Streets, Notes | 229 neighbouring parcels, 38 street lines; each layer locked, visible, in its grey |
| 1 The notes: a north arrow, a scale bar and the sources | All three on the Notes layer |
| 1 Every note lies inside the neighbourhood square | All 6 notes inside (each measured by its own points); the sources wrapped, 60 characters at most a line |
| 1 The sources note is small | Its own scale 1 (not the template's 12), 2.5 ft text, 3.88 ft a line as displayed |
| 2 The building footprints are on screen | 212 footprints, shown live |
| 3 The checker never measures the context | One lot candidate |
| 3 The check is the same with and without the neighbourhood | The same summary both ways |
| 3 Drawn again, it replaces | The same object counts, never doubled |
| 4 The panel tick hides it and shows it again | Every context layer hidden, then shown |
| 5 A saved file keeps no live-only source | No footprint (store: none) in the saved .3dm |
| 6 A second address clears the first neighbourhood | Edit site…, 109 Ithaca Rd: the frame changed, nothing of 106's left (109 has no recorded neighbourhood, so none is drawn and Gordium says why) |

## The docked panel's tick, clicked (2526115, the MVP panel merged in)

`apps/rhino_plugin/tests/context_tick_in_rhino.py` (written by the Rhino job) clicks the docked panel's own "Show
neighbourhood" checkbox (its handler runs as a click's does): **9 of 9 claims true** (`context_tick_results.json`).

| Claim | Result |
|---|---|
| 1 The panel is Rhino's docked panel, the tick on a row of its own | Yes |
| 2 The neighbourhood is drawn and the tick starts on | Every neighbourhood layer visible |
| 2 Unticking through the panel hides every neighbourhood layer; ticking shows them again | Hidden, then shown |
| 3 A rebuilt panel starts the tick as last set | Off after unticking |
| 4 While a start box is open the tick is greyed, and a change to it does nothing | Greyed; the change said "Finish or cancel the open start box first." and left the layers as they were |
| 4 After the box closes the tick is back on | Enabled, layers visible |

Since that run the tick is kept per file, in the document's Gordium settings like Show on-screen labels (it was per
Rhino session). The script now reads the setting from the document and has a claim 5, "the tick is kept in the file:
a saved copy has it off"; the Rhino job re-runs it.

| File | What it shows |
|---|---|
| `106_context_top.png` | Top view: the neighbourhood around 106, north arrow, scale bar, and the sources note as a small block inside the square's left corner (2.5 ft text: readable when zoomed in, as drawing text is) |
| `106_context_perspective.png` | The same in 3D |

What the first run's screenshots showed, and what came of it:
- the sources note was one long label running off the view: fixed (wrapped model text inside the square, at its own
  scale; the first fix's 12 ft text inherited the template's dimension scale of 12 and drew ~30 ft letters, found
  and fixed in the next runs);
- in Top view the lot's edge-length labels pile up in a column: the label placement this branch inherits from
  #15/#19; the MVP branch's `place_label` puts each beside its own line and reaches this PR when #15 carries it.
