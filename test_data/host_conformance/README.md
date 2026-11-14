# Host conformance suite

The test any design tool's add-in (a **host**: Rhino now, Revit later) must pass before its checks can be trusted.
A host reads the architect's model and sends Gordium a [site description](../../docs/protocol/site_description_v1.md);
Gordium measures and checks only what it is sent. So a host that misreads a model, or quietly leaves out a problem
it found, could turn a "needs review" into a "complies". This suite is the guard: the same fixed drawings, read by
any host, must give the same description and exactly the same verdicts.

Why a second reader is allowed at all, and the alternatives: [docs/decisions/2026-11-06_hosts_talk_to_the_worker.md](../../docs/decisions/2026-11-06_hosts_talk_to_the_worker.md).

## What is here

| Path | What it is | Made by |
|---|---|---|
| `scenes/*.yaml` | Each scene: a small drawing written as data (the lot, each building, other objects, the ground, an edit), what it tests in plain words, and the verdict of every rule it decides, worked out by hand before Gordium ran (commits 182391ef, 2eab4b11 and 09320095). Scenes 18 on also say which host reading they guard (`guards`: the row of the [Revit reading design note](../../docs/revit/revit_reading_design.md) and the Rhino code it stands for). Rows found only on running are marked "found on running", with why. | By hand |
| `common_verdicts.yaml` | The rows every scene gives the same status (they depend only on facts every scene states alike). A scene's check must give exactly these rows plus its own. | By hand |
| `expected/<scene>.site.json` | The description a host must send for the scene (`.after` for the step after its edit), worked out from the scene's numbers alone, never by reading a model. | `python -m design_checker.conformance --write` |
| `models/<scene>.3dm` | The scene drawn in Rhino's file format, every object and layer with a fixed id (a block's definition and the object inside it excepted: rhino3dm makes their ids, and no reader uses them; so a rewrite reads the same; the files' bytes still differ on each write, as Rhino stamps them). | the same |
| `recorded/<host>/<scene>.json` | A host's descriptions of each scene, recorded once on its own machine. `recorded/rhino3dm/` is the Rhino reference adapter's; `recorded/revit/` is empty until the Revit add-in records its own. | the host |

The 26 scenes: a box house; a curved wall; an open solid; a block on the Building layer; a garage left out
(scenario 06); no grade; spot grades on a slope, then the house moves (scenario 07); a model in millimetres; two lot
outlines; survey coordinates far from the origin; a corner lot; ids that stay the same after an edit; objects left
out that touch the house, sit on the neighbourhood's layer or are a block; a terrain mesh left out (it looks like
the ground); a curved rear lot line; and two descriptions no Rhino drawing gives, checked for their verdicts only:
no lot with no reason said, and no buildings sent by a host that didn't look at everything. Scenes 15 to 17 were
added in review (commit 2eab4b11, hand-worked before running): before them no left-out object touched the house, so a
host that never said "touching" would have passed. Scenes 18 to 26 are the cases of the Revit reading design note's
section 7 that Rhino can draw (commit 09320095, hand-worked before running): a house built from parts (walls, slabs,
a window, a curtain wall, a built-in, the roof a closed mesh); the house only inside a block on another layer (a
linked model); a house of parts in a group, the group moved; the lot picked from two outlines; no lot outline; the
picked lot deleted; an open property line, alone and picked; and blocks with nothing to measure in them. The note's
other cases need Revit (or, for its terrain scene, a live Rhino recording) and wait for the Windows trial.

## What passing means

For each scene (and its step after the edit), a host's description must:

1. **be valid** `gordium.site/1` (refused descriptions fail);
2. **match the expected one**: the same ids (through the recording's id map), every point within a millionth of a
   foot, the same problem codes on the site and on each building, the same left-out objects (could be a building,
   touching, looks like the ground, on the neighbourhood's layers; `touching: null` counts as touching), the same
   grade and the same `inventory_complete`. Faces may come in any order, start at any corner and run either way
   (the measuring reads them the same: `measure._normal_z` and the footprint union ignore it). A curved lot line
   may be sampled the host's own way, but every point must be within a millionth of a foot of the arc, in order,
   no more than 0.25 ft apart (the suite's reading of "points closely along it"), and the line marked curved. An
   object that couldn't be sent counts by its problem code, not by its id or how many (Rhino's reader sends every
   block on the Building layer as one building named "a block", with no faces and `not_a_solid`, which has no
   object id; a host may instead send each as an `unsent` object);
3. **give exactly the expected verdicts** through `check_site`: every row, no row more or less.

**A host that sends fewer problems than expected fails**, even when the verdicts happen to come out the same. That
is the false-pass guard: a host that doesn't report a curved wall, here, would measure a curved wall as straight
somewhere else. A host that sends more problems than expected fails too (it would need review where it shouldn't),
but the message says which way it went.

## Running it

```bash
python -m design_checker.conformance            # every scene through the Rhino reference adapter, and every recording
python -m design_checker.conformance --write    # after changing a scene: the expected descriptions, models, recordings
pytest packages/design_checker/tests/test_host_conformance.py
```

CI runs it on every push. The **Rhino reference adapter** (`design_checker/conformance_rhino.py`) reads each
`.3dm` with rhino3dm, no Rhino needed: the lot and Building layers through `read_site` (the reader the Rhino
command's exported copy goes through), the spot grades from `Gordium::Grade` as the command reads them, and every
other object on the lot looked at with the same decisions the command makes (`rhino_logic.could_be_building`,
`reaches_into_lot`, `looks_like_ground`, `context_left_out`), on the same points (a curve's points along it; a
solid's corners, edges and faces; a block's box, from what it holds, as rhino3dm gives a placed block none). The live command does that inventory in RhinoCommon,
which CI can't run; its Rhino-side tests cover it.

## How to add a host

A host that can't run on the Mac (Revit) is checked from recordings:

1. **Draw each scene in the host**, once, from its YAML (the outlines, heights and layers are all there; a Revit
   scene uses the host's own equivalent of each layer, and "a block" is whatever the host can't send as a solid).
   Description-only scenes (those with `site:`) aren't drawn.
2. **Read each with the add-in** exactly as a check does, and save
   `recorded/<host>/<scene>.json`:

   ```json
   {"host": "revit", "scene": "01_box_house",
    "recorded": {"by": "who", "date": "YYYY-MM-DD", "tool": "Revit 2026, Gordium add-in 0.1"},
    "ids": {"<the host's id for an object>": "<the scene's id for it>"},
    "steps": {"as drawn": {...the description...}, "after the edit": {...}}}
   ```

   The scene's ids are the YAML's: `lot` (and `lot_2`…), each building's id (or `<id>_floor1`, `_floor2`… for a
   building with `floors`), each other object's id. One `ids` map serves every step, so a host whose ids change
   at the edit fails. For a scene with `picked:` (21, 23, 25), pick the lot in the host as the architect would:
   the facts' `lot_id` (`conformance.facts`) is the reference model's Rhino id, not the host's own. For 23,
   whose picked lot is not among its `lots`, draw that lot too, pick it, then delete it. For a scene
   with `then:`, make the edit in the host (move the objects; don't redraw them)
   and record "after the edit" too.
3. **Record every scene**: a host with any recording must have one for every drawn scene, so the hard ones can't
   be left out.
4. **Run the suite on the Mac** (`python -m design_checker.conformance`): it checks the new folder like the
   reference adapter's. Commit the recordings; CI checks them on every push from then on.

When the site description, a scene or the checker changes, the host records again.
