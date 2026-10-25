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

## The docked panel's tick, clicked (64d1425: the MVP panel merged in, the tick kept per file)

`apps/rhino_plugin/tests/context_tick_in_rhino.py` (written by the Rhino job) clicks the docked panel's own "Show
neighbourhood" checkbox (its handler runs as a click's does): **10 of 10 claims true** at 64d1425
(`context_tick_results.json`). The first run, at 2526115 before the tick was kept per file, was 9 of 9.

| Claim | Result |
|---|---|
| 1 The panel is Rhino's docked panel, the tick on a row of its own | Yes |
| 2 The neighbourhood is drawn and the tick starts on | Every neighbourhood layer visible |
| 2 Unticking through the panel hides every neighbourhood layer; ticking shows them again | Hidden, then shown |
| 3 A rebuilt panel starts the tick as last set | Off after unticking |
| 4 While a start box is open the tick is greyed, and a change to it does nothing | Greyed; the change said "Finish or cancel the open start box first." and left the layers as they were |
| 4 After the box closes the tick is back on | Enabled, layers visible |
| 5 The tick is kept in the file: a saved copy has it off | The saved .3dm's Gordium settings: `show_context` false |

The tick is kept per file, in the document's Gordium settings like Show on-screen labels (it was per Rhino session
until 64d1425); the script reads the setting from the document.

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

## Re-run at 955d97f (2026-10-22): the context layers stay locked

**What changed since the run above:** at c783ee6 the run failed its first claim: every neighbourhood layer came out
unlocked. The cause was found in Rhino 8. Setting a parent layer's visibility (`IsVisible`, even to "shown" when it
is already shown) gives each sublayer the parent's lock setting. `Gordium::Context` is left unlocked on purpose, so
the footprints can be dragged, and it is shown at the end of every draw. So Parcels, Streets and Notes were
unlocked too. At 955d97f the layers are locked again after any show or hide.

The test as run: 955d97f's own `apps/rhino_plugin/tests/context_in_rhino.py`, with recorded answers for 106 Ithaca
Rd (no live calls). **15 of 15 claims true** (`context_results_955d97f.json`). GordiumStart with the neighbourhood
took 9.5 s; drawing it again took 2.6 s.

| Claim | Result |
|---|---|
| 1 Its own grey layers, locked but for the footprints | Parcels (229), Streets (38) and Notes (6) locked; Buildings (322 footprints) unlocked; `Gordium::Context` itself unlocked (a locked parent would lock the footprints) |
| 1 The notes; every note inside the square; the sources note small | All true |
| 2 The footprints are real outlines on the unlocked Buildings layer | 322 outlines, editable |
| 3 The checker never measures the context; the check is the same with or without it | One lot; the same summary |
| 3 Drawn again it replaces, never doubles | 322 before, 322 after |
| 3 An edited footprint stays the architect's | The lifted one kept once; the untouched ones replaced |
| 3 A copy pasted in place, and a footprint given a print width, are the architect's | Both kept once, never doubled (323 before, 323 after) |
| 3 A solid on the neighbourhood layers over the lot | "Objects on the lot not included": needs review; never measured |
| 4 The panel tick hides it and shows it again, and only Parcels, Streets and Notes stay locked | Locks the same after hiding and after showing |
| 5 A saved file keeps the footprints, with their credit and date | 319 outlines; "footprints dated 2014" on the Sources note |
| 5 A saved, reopened file with a layer deleted before it: a clear keeps only the architect's | 4 of theirs before, 4 left; none of Gordium's left |
| 6 A second address clears the first neighbourhood | Frame changed; nothing of 106's left |

The panel tick, clicked (`context_tick_in_rhino.py` at 955d97f): **10 of 10 claims true**
(`context_tick_results_955d97f.json`).

| File | What it shows |
|---|---|
| `106_context_top_955d97f.png` | Top view at 955d97f |
| `106_context_perspective_955d97f.png` | The same in 3D |

## Re-run at 369f389 (2026-10-25): 15 of 16, the locked-parent claim fails

The test as run: 369f389's own `context_in_rhino.py`, in a copy that records every claim rather than stopping at
the first failure (`context_results_369f389.json`), with recorded answers for 106 Ithaca Rd. GordiumStart with the
neighbourhood took 6.7 s. Every claim of the 955d97f run still holds, and three newer claims pass: the copy pasted
in place and the print-width footprint are kept; a saved, reopened file keeps only the architect's outlines.

**Fails: "4 with the Gordium layer and the architect's Gordium::Grade locked, a redraw replaces (never doubles) and
puts both locks back".** The redraw does replace (319 outlines before and after), and both locks are put back. But
a probe (`context_lock_probe_e631aae.json`, the same code in the demo at e631aae) shows:
- While "Gordium" is locked, every neighbourhood layer's own lock (`GetPersistentLocking`) is off. They read locked
  only because their parent is.
- Once "Gordium" is unlocked, Parcels, Streets and Notes are unlocked. They should stay locked. This is a product
  bug: each layer's own lock has to be set while its parent is locked.
- The claim also reads the locks while the parent is still locked. Rhino then reports every sublayer locked, so
  "Buildings unlocked" can never hold at that moment. The claim should read each layer's own lock, or read the
  locks after the parent is unlocked.

| File | What it shows |
|---|---|
| `106_context_top_369f389.png` | Top view at 369f389 |
| `106_context_perspective_369f389.png` | The same in 3D |
