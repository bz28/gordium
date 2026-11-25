# The story facts, worked out from the model (2026-11-25)

**Purpose:** how Gordium works out the story facts the Building Code's single-exit tables read (which story is the first, second or fourth above grade plane; the dwelling units on a story; whether its rooms exit directly outside) from the model, instead of asking the architect.\
**For:** engineers changing `model_measurement/routes/story_place.py` (and the later story facts); reviewers of the rules that read them.\
**Kept current by:** the engineer who changes how a story fact is worked out, in that same branch.

Ben, 2026-11-25: everything the model can show is worked out by Gordium; only what it can't know for certain goes to the architect. Before this, the five facts had no source at all (no field fed them), so the rules reading them (BCNYS 1006.3.3, Tables 1006.3.4(1) and (2), 1007.1.1) always needed review on a real model.

## The law (2025 Building Code of New York State, quoted from the book)

- **GRADE PLANE** (p.48): "A reference plane representing the average of finished ground level adjoining the building at exterior walls. Where the finished ground level slopes away from the exterior walls, the reference plane shall be established by the lowest points within the area between the building and the lot line or, where the lot line is more than 6 feet (1829 mm) from the building, between the building and a point 6 feet (1829 mm) from the building."
- **STORY ABOVE GRADE PLANE** (p.63): "Any story having its finished floor surface entirely above grade plane, or in which the finished surface of the floor next above is: 1. More than 6 feet (1829 mm) above grade plane; 2. More than 12 feet (3658 mm) above the finished ground level at any point; or 3. More than 6 feet (1829 mm) above the finished ground level for more than 50 percent of the total building perimeter."
- **BASEMENT** (p.34): "A story that is not a story above grade plane".
- Table 1006.3.4(2) (p.317): "First story above or below grade plane", "Second story above grade plane"; Table 1006.3.4(1): "Basement, first, second or third story above grade plane", "Fourth story above grade plane and higher".

## Step 1: a story's place (this PR)

1. **The stories** are the levels with rooms, each with the range of its rooms' finished floor elevations (a sunken room widens it). A split level (two stories' floors overlapping in height) or a level with no rooms between two that have rooms (it may be a story nobody drew) leaves every place not measured. A level with no rooms above or below them (a roof, a foundation datum) is no story.
2. **The ground** is only what the architect stated, from the lot facts:
   - **flat ground** (`ground_is_flat`, `grade_elevation`): the grade plane and the finished ground everywhere: exact. Flat ground the host only *assumed* (`ground_assumed`) is not used.
   - **spot grades** (finished): every wall of the stories' outline must have a spot within 2 ft (the zoning reader's own reach), else nothing is placed. **Gordium's reading** (the usual surveying reading, said with every figure measured from spots and in the rules' notes): the ground between two spots lies between their values, so the average along the walls, and so the grade plane, is at most the highest spot. The slope-away rule can only lower the grade plane, with no lower end the spots show: a story is never proven a basement from spot grades. The lowest spot is a known point of finished ground (item 2).
   - **existing ground** (`grade_is: existing`), or **none**: nothing is placed.
3. **Each story** is certainly above grade plane (at the grade plane's top end, with 1/16 in to spare), certainly a basement (flat ground only), or either. Being above grade plane holds for every story above one that is, so the possible readings are "the lowest b stories are basements" for each b the ground allows; **a fact is measured only where every b gives the same answer**, else it needs review and says which stories it could be. A slab at or above the highest spot is the first story above grade plane in every reading; the story on it is the second (unless the first could be a basement).
4. **Plumbing:** `check._story_ground` reads the lot facts into `story_place.ground_of`; `egress.check(..., ground=)` hands it to `routes.measure`.

**How we know:** `packages/model_measurement/tests/test_routes_story_place.py` walks 13 stacks of floors (basements, sunken rooms, floors on each threshold) over 19 grounds and none: an oracle written from the three definitions lists every world the stated ground allows (a grade plane anywhere in its range, the lowest ground, the ground along half the perimeter, which height of a stepped floor counts as "the floor next above") and every fact measured must be the oracle's one value. It also requires flat ground to settle the floors clear of the thresholds. The real models: the four-unit apartment (as sent it has no ground: not placed; with its flat ground at 0, Level 1 first and Level 2 second; at 5 ft, Level 1 a basement and Level 2 the first above), and 106 Ithaca Rd's levels and four spot grades (Level 1 the first story; the Roof, with no rooms, no story). Through the check (`packages/design_checker/tests/test_story_place_check.py`), a one-exit Group A version of the apartment fails Table 1006.3.4(2) on flat ground at 0 (its second story), passes at 5 ft, and needs review, never a pass, wherever the place isn't measured.

**Not done:** the Residential Code's stated `stories_above_grade_plane` isn't used as a cross-check (a different book: Ben through the coordinator, 2026-11-25). A mezzanine drawn as its own level counts as a story: a higher number than the true one, which only ever makes these tables stricter.

## Steps 2 and 3 (next PRs)

2. **Rooms that exit directly outside** (1006.3.4 item 2): yes only where every room on the story (corridors too; closets and toilets taken as part of the room they serve; exits left out) has its own door marked exterior at discharge; no where one has no door to the outside at all; not measured otherwise.
3. **Dwelling units on a story:** groups of rooms joined by doors and passages without passing through a corridor, lobby, exit or the outside; a group with one entrance and a room whose function is residential is one unit; two or more entrances, no entrance (part of a unit on two stories), an unknown space or a group with no function stated: not measured (or low and high readings, passing only at the high count). If the not-measured case is common on real models, a room mark (Gordium: Unit) follows.
