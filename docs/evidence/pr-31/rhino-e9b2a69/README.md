# PR #31 checked in Rhino at e9b2a69: why the house went amber, and the cost of the fix

**Purpose:** what Rhino 8 (Mac) showed on 2026-10-26 for `depth_in_rhino.py`, the probe of where and how the coloured part is drawn, and orbit timing with colouring on.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Result in one line

`depth_in_rhino.py` passes 13 of 13. But the amber front face it guards against is **not real**. It appears only
because Rhino draws the house without its shaded faces while a script is running. In a real, idle Rhino the old
drawing (001b757) already hid the strip behind the house. The new fix, which works out the visible faces for each
camera, triples the time per frame while orbiting.

## 1. `depth_in_rhino.py` as written (`depth_results.json`): 13 of 13

All claims pass, the new 5 and 6 included: the Front face is not amber (`5_front_coloured.png`), and from behind
the rear yard's strip shows on the rear face (`6_back_coloured.png`).

## 2. Where the coloured part is drawn, and with what depth settings

- **Where:** in `PostDrawObjects` (the plugin's `draw_scene` stage, after Rhino has drawn the model's own objects).
- **Depth:** depth **testing on** (hidden behind anything nearer). Depth **writing off** (`_see_through`), so the
  part never hides what lies behind it.
- **The same at both heads:** 001b757 and e9b2a69 draw it this way. e9b2a69 only adds a step that drops the faces
  the camera can't see (`_seen_faces`, a ray cast for each camera).

## 3. Why the whole front face went amber at 001b757 (`in_script_*.json`, `meshed_stages.json`)

**While a script runs, Rhino draws the house as wireframe, even in Shaded.** The house's faces are not shaded, so
the house fills in no depth and hides nothing behind it:

- In-script capture (`D1_red_box_behind_house.png`): a real red box placed behind the house shows its edges
  straight through the house.
- The house's face is the background grey (157, 163, 170).
- Building the render meshes inside the script does not help (`G_after_CreateMeshes.png`): the meshes exist, and
  the frame is still wireframe.

**Once the script returns and Rhino has idled** (two phases, about 8 s apart), the house is shaded: its face is
(209, 216, 220), `E2_meshed_plugin_old_whole.png`. A coloured strip behind the front face, compared on 81 points of
the house's front face, Shaded Front:

| Drawing | In-script (house not shaded) | After idle (house shaded, as an architect sees it) |
|---|---|---|
| the plugin at e9b2a69 (only the faces the camera sees) | 0 of 81 changed | 0 of 81 |
| **the plugin as at 001b757 (the whole piece)** | **72 of 81 amber** | **0 of 81: hidden** |
| own conduit, PreDrawObjects, depth testing on / off | 72 / 72 | 0 / 0 |
| own conduit, PostDrawObjects, testing on / off | 72 / 81 | **0** / 81 |
| own conduit, DrawForeground, testing on / off | 72 / 81 | **0** / 81 |
| own conduit, DrawOverlay (Rhino reports DepthMode AlwaysInFront) | 81 / 81 | 81 / 81 |

Testing on, the old drawing in PostDrawObjects is correct in real use. Only a fill drawn in DrawOverlay, or with
testing off, shows through the house.

The in-Rhino scripts capture before Rhino idles, so their "Shaded" frames are of a wireframe house. This
affects claims 3 to 6 here, and any other script's Shaded frames. To test hiding, a script needs two phases: set up
and return, then capture (as `meshed_phase1.py` and `meshed_phase2.py` do).

## 4. Orbit timing, colouring on and off (40 frames, the camera rotated 0.05 rad about Z per frame)

| | in-script (house not shaded) | after idle (house shaded) |
|---|---|---|
| Perspective, colouring off: median / worst | 8 / 45 ms | 33 / 53 ms |
| **Perspective, colouring on** | 19 / 26 ms | **89 / 235 ms** |
| Front, colouring off | 8 / 15 ms | 32 / 56 ms |
| **Front, colouring on** | 14 / 40 ms | **63 / 106 ms** |
| `_seen_faces`, shaded Perspective: calls / total / worst call | | 126 / 1,937 ms / 171 ms |

- The cache misses on **every** orbit frame: 126 calls for 3 pieces over 40 frames, and 123 entries afterwards.
- With the house shaded, orbiting with colouring on runs at about 11 frames a second, against about 30 without it.
  That is visible lag.

## Files

- **Results:** `depth_results.json` (the check), `in_script_stages.json` (stages and in-script timing),
  `in_script_red_box.json`, `meshed_stages.json`, `meshed_orbit_timing.json`.
- **Scripts:** `fill_stage_probe.py`, `house_occlusion_probe.py`, `meshed_phase1.py`, `meshed_phase2.py`,
  `meshed_timing_phase2.py`.
- **Frames:** the PNGs named above.
