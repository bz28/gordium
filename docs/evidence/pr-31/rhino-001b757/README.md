# PR #31 checked in Rhino at 001b757: depth-tested lines, and the amber house in Front

**Purpose:** what `depth_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26, and which row colours the whole house amber in the shaded Front view.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

`depth_in_rhino.py` as written: **10 of 10** (`depth_results.json`), including the new claim that the Perspective
frames the whole house and lot (`2_perspective_shaded.png`: the house, the lot and the see-through envelope, the
rear yard's dimension hidden where the house covers it).

## Why the whole house is amber in Front (`4_front_shaded.png`)

A probe of the coloured pieces Gordium holds for this scene (`colour_rows.json`, `colour_rows_probe.py`): the only
row needing colour is **Rear yard, needs review**. Its three pieces, one per floor, are the back 4.9 ft of the house
(y 60.3–65.2 ft), across the house's whole width (x 12.9–48.8 ft) and full height (0–35 ft).

Seen from the front, that strip is behind the house's front face. In the shaded Front view the whole face shows
amber, so the coloured strip is drawn over the solid house rather than hidden behind it: the colouring isn't
depth-tested, while the lines are. The front face itself isn't what needs review. An architect would read "the
whole house needs review" from this view.
