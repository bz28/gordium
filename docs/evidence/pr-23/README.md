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

## Re-run at e997f0e (2026-10-25): the neighbourhood keeps its own locks; Grade's part of claim 4 is Rhino's

The test as run: e997f0e's own `context_in_rhino.py`, in a copy that records every claim rather than stopping
(`context_results_e997f0e.json`), with recorded answers. **15 of 16.** Every claim passes but claim 4's second
part.

**The fix holds.** With Grade, then "Gordium" locked, the redraw replaces (319 outlines before and after) and puts
both locks back. Each neighbourhood layer's own lock is right: Parcels, Streets and Notes on; Buildings and
Context off. Once "Gordium" is unlocked, Parcels, Streets and Notes are locked and Buildings isn't. A first draw
in a file whose "Gordium" was locked beforehand gives the same locks (`first_draw_locked.json`, 595 objects drawn).

**What fails is Grade, and that is Rhino, not Gordium.** Grade's own lock reads off already before the redraw
(`grade_own_lock_before: false`), and Grade is unlocked once "Gordium" is. A probe with no Gordium code
(`grade_lock_probe.json`) shows Rhino 8 does this by itself: a sublayer locked by `IsLocked`, or by
`SetPersistentLocking` while its parent is unlocked, records no lock of its own. When its parent is locked and
unlocked, it comes out unlocked. So "Grade still locked after unlocking Gordium" can't hold for a layer locked
before its parent. The claim should drop that part, or lock Grade after "Gordium" is locked.

| File | What it shows |
|---|---|
| `106_context_top_e997f0e.png` | Top view at e997f0e |
| `106_context_perspective_e997f0e.png` | The same in 3D |

## Re-run at 994012d (2026-10-25): 17 of 17, and the lock probe

The test as run: 994012d's own `context_in_rhino.py`, in a copy that records every claim
(`context_results_994012d.json`), with recorded answers. **17 of 17.** Both reworked claim-4 cases pass: Grade locked
before "Gordium", and Grade locked after it. In each, the redraw replaces without doubling; unlocking "Gordium"
leaves Parcels, Streets and Notes locked and Buildings not; and Grade is exactly as plain Rhino leaves it.

`lock_probe_in_rhino.py` (Rhino's own layer locks, no Gordium), cases 1–5 (`lock_probe_994012d.json`). The two
"layer_command" cases were left out: they type Rhino's `-_Layer` command, and the script asks for it to be typed by
hand first, which the Rhino job doesn't do (no interactive commands).
- **1, 2: a sublayer locked by `IsLocked`** (with `SetPersistentLocking` first or not), its top then locked and
  unlocked: it comes out unlocked, and it never has an own lock. Plain Rhino, as Grade.
- **3: `SetPersistentLocking(True)` alone, the top unlocked**: no own lock is recorded.
- **4: relock**, with the top locked, the sublayer locked and given its own lock (as Gordium's `_set_own_lock`
  does), then the top unlocked: the sublayer stays locked. Locked and unlocked again: it still stays locked, and
  its own lock is kept. Rhino **keeps** an own lock through a later lock and unlock of the parent; it doesn't
  reset it.
- **5: nested** (an unlocked Mid between the top and the sublayer, as `Gordium::Context` sits): the same as 1 and 4.

## Re-run at 917a4e8 (2026-10-25): 18 of 18, and the lock probe 1–5b

The test as run: 917a4e8's own `context_in_rhino.py`, in a copy that records every claim
(`context_results_917a4e8.json`): **18 of 18**. That includes the new case: drawn with "Gordium" unlocked, then
"Gordium" locked and unlocked with no redraw, Parcels, Streets and Notes are still locked and Buildings isn't. Both
Grade orders pass too.

`lock_probe_in_rhino.py`, cases 1–5b, without the two manual `-_Layer` cases (`lock_probe_917a4e8.json`): as at
994012d for cases 1–5. The new **mid_relock**: the sublayer's own lock set while only Mid is locked survives Mid
being unlocked, and the top then being locked and unlocked (the sublayer stays locked, its own lock kept).
