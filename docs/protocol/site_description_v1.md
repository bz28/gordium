# Site description, version 1 (`gordium.site/1`)

**Purpose:** the contract for what a design tool (Rhino now, Revit later) sends Gordium's checker: the lot, the buildings, the ground and what was left out.\
**For:** engineers writing a design-tool add-in; reviewers checking that nothing a tool sends can be quietly ignored.\
**Kept current by:** every PR that changes the site description or the worker's new-style commands (a test fails if the schema changes without a [CHANGELOG](CHANGELOG.md) line).

The site description is the plain list of what a design tool hands Gordium's checker: the lot outline, each
building solid as flat faces, the ground, and anything on the lot that was not sent. Rhino is the first tool; a
Revit add-in can send the same description later and get exactly the same checking.

- **The fields, for a tool's own tests:** [site_description_v1.schema.json](site_description_v1.schema.json)
  (JSON Schema 2020-12).
- **The code that reads it:** `packages/design_checker/design_checker/site_json.py` (`validate`, `to_site`,
  `from_site`). Its tests prove the schema file and the code list the same fields.
- **Changes:** [CHANGELOG.md](CHANGELOG.md).
- **How a tool proves it sends the right description:** the [host conformance suite](../../test_data/host_conformance/README.md)
  (fixed scenes, the description each must give, and the verdicts it must lead to).

## Why it is strict

A description that has anything wrong in it is refused whole, with every reason listed. Nothing is ever skipped
quietly. If the checker skipped a field it didn't know, a newer tool's warning ("this wall is curved") could be
ignored and a design could pass that shouldn't (Gordium's rule: never a false pass). The checker refuses:

1. a field this version doesn't know, or a required field left out;
2. a problem code the measuring doesn't know, or a problem whose text blanks don't match its code;
3. a number that is not finite (NaN, infinity) or is text;
4. a face or hole with fewer than 3 points, a lot line with fewer than 2, or a lot outline with fewer than 3
   different points;
5. an id used twice (across the lot, the buildings, `unsent` and `left_out`);
6. units other than feet, and a `schema` other than `gordium.site/1`.
7. a key given twice in one object (a JSON reader would otherwise keep one of the two without a word).

## The fields

| Field | Meaning |
|---|---|
| `schema` | Always `"gordium.site/1"`. |
| `units` | Always `"ft"`. The tool converts to feet once, where it reads its model. Revit already works in feet. |
| `host` | `{name, version, document, model_units}`: which tool and file sent it. Kept for tracing only; never used in a decision. |
| `lot` | `{id, edges: [{points: [[x, y], …], curved}]}`, or `null` when no lot outline was found; `problems` should then say why (Rhino's reader always does: `no_lot_layer`, `no_lot_outline`, `several_lot_outlines`…). It isn't refused when it doesn't: every measure that needs the lot then needs review, saying "no lot outline". A straight lot line is its two ends; a curved one is points closely along it, with `curved: true`. |
| `buildings` | Each solid on the building layer: `{id, role: "building", layer, name?, floor?, faces: [{points: [[x, y, z], …], holes?: [[…]]}], problems: [problem…]}`. `floor` is a floor block's height as drawn (ft); left out or `null` for any other solid. A face that can't be read exactly is never approximated: it is left out and the building gets a problem (`curved_surface`, `curved_edge`, `open_solid`…). |
| `unsent` | Objects that may be building but couldn't be sent at all (a block, a surface): `{id, layer, kind, problem}`. A tool that can't name each such object may instead send one building per kind with no faces and the problem (`read_model` does: a building with id `"a block"` and a `not_a_solid` problem, as `read_site` reads a file); either way every building's measuring needs review. |
| `left_out` | Objects on the lot that weren't sent: `{id, layer, could_be_building, touching, ground_like, context}`. Each one makes the check need review. `touching: null` means not known, which counts as touching. |
| `grade` | `{source, points: [[x, y, z], …]}`, source one of `spot`, `finished_spots`, `terrain` or `none`. Always present: no ground read is `{"source": "none", "points": []}`, and the measuring then uses the lot facts' flat ground (`ground_is_flat`, `grade_elevation`) if they give one, else says the ground is missing. |
| `inventory_complete` | `true` only when the tool looked at everything on the lot, so `left_out` is the whole list. `false` makes every building's measuring need review. |
| `problems` | Problems with the site as a whole (the file, the lot outline). |

**A problem** is `{code, args}`. The code is a key of the measuring's list of reasons
(`packages/model_measurement/model_measurement/stops.py`), and `args` gives each blank in its words, as text. The
checker writes the words itself. For example `{"code": "several_lot_outlines", "args": {"count": "2", "layer":
"Site"}}` reads "2 closed outlines on the Site layer: pick the lot".

**Ids** are text the tool keeps stable (a Rhino object id, a Revit UniqueId). Results point back to them: the
items shown in red, the main building picked.

**Street lines are not in the site.** The street side is something the architect states, with its
source recorded, so it stays in the lot facts (`street_line`, `street_ids`). Putting it in both places would give
two answers to one question.

## One example

The smallest valid description: a 50 × 100 ft lot, one 20 × 30 × 25 ft box (its six faces cut to two here for
length), flat ground not yet given, and nothing else on the lot.

```json
{"schema": "gordium.site/1", "units": "ft",
 "host": {"name": "rhino", "version": "8.12", "document": "house.3dm", "model_units": "Feet"},
 "lot": {"id": "lot-1", "edges": [{"points": [[0, 0], [50, 0]], "curved": false},
                                  {"points": [[50, 0], [50, 100]], "curved": false},
                                  {"points": [[50, 100], [0, 100]], "curved": false},
                                  {"points": [[0, 100], [0, 0]], "curved": false}]},
 "buildings": [{"id": "house-1", "role": "building", "layer": "Building", "floor": null,
                "faces": [{"points": [[10, 25, 0], [30, 25, 0], [30, 55, 0], [10, 55, 0]]},
                          {"points": [[10, 25, 25], [30, 25, 25], [30, 55, 25], [10, 55, 25]]}],
                "problems": []}],
 "unsent": [], "left_out": [],
 "grade": {"source": "none", "points": []},
 "inventory_complete": true, "problems": []}
```

## How the worker uses it

The worker (`python -m design_checker serve`) answers JSON requests one per line. The new-style commands name
the protocol they speak, `"protocol": "1.0"` (a different major version is refused):

- `hello`: the protocol, the site description version, and fingerprints of the worker's code and of each place's
  rules (`protocol.about()`). Every new-style answer carries the same under `"about"`.
- `read_model {model, facts, inventory_complete?}`: a `.3dm` file read as a site description, for recording test
  fixtures. It reads only the lot and Building layers, so it says `inventory_complete: false` unless the caller
  says it looked at the rest of the lot itself.
- `check_site {site, facts, report?, extras?}`: the check of a site description, the same answer `check` gives.
- `start_site {site, facts, floor_to_floor?, design_buffer?, larger_side?}`: the largest legal starting building
  on the description's lot (its buildings are left out), the same answer `start` gives.

**Rhino takes the same path.** The older `check` and `start` read the model, make it a site description (the
grade from the facts, what Rhino couldn't send as `unsent`, the objects it left out as `left_out`), write it as
JSON text, read it back strictly, and check that, exactly as `check_site` does. So the path a Revit add-in will
use is the one every Rhino check already takes, and both give the same answers (tests/test_check_via_site.py).

**How the checker reads a description** (`site_json.for_measuring`):

- Every `unsent` object's problem goes on one faceless building, so every building measure needs review.
- `inventory_complete: false` puts a problem on every building ("the design tool didn't say everything on the lot
  was sent…"): no building measure complies; lot size and width, which don't depend on the buildings, still can.
- Each `left_out` object makes the check need review (an "Objects on the lot not included" row; lot coverage and
  the accessory building rules need review); one that touches a building, or isn't known to (`touching: null`),
  makes the yards, height and stories need review too.
- The grade points come only from the description. Facts that also give `grade_points`, a `grade_from` other than
  the description's grade source, or extras that also list left-out objects are refused: one source for each
  thing. A flat ground stated in the facts (`ground_is_flat` with `grade_elevation`) is still used when the
  description has no grade points, as it always has been.
- **A problem in the tool's own words.** A tool that found a problem the measuring has no code for sends
  `{"code": "tool_words", "args": {"words": "…"}}`. It still makes the building's measuring need review. Words the
  measuring does have a code for are refused this way (send that code).

**A report keeps its site.** When `check` or `check_site` writes a zoning report, the exact description it was
worked out from is written beside it as `<report name>.site.json` (Ben, 2026-11-06), so any report can be traced
to exactly the site it was worked out from, and worked out again with the same lot facts (the file holds the site
description only, not the lot facts). If the description can't be written, no new report is written either (the answer says
why). The earlier report's site file is replaced only once the new report is in place, so a report that can't be
saved (open in Excel, say) leaves the earlier report beside its own site. Never a report beside another check's
site; at worst, a check stopped between the two leaves a report with no site file.

The older commands (`check`, `start`, `facts`, `options`, `sample_site`) answer exactly as before (the golden
answers and the recorded session prove it, to the last character).

## Versions

A minor version adds things an older reader can safely not know about: new commands, new answer fields, new
optional request fields whose absence means exactly the old behaviour. Anything else is a new major version: a
rename, a removal, a change of meaning or units, a new required field, or any new site field that can change a
verdict. Each side refuses a different major version. A test pins the schema file's fingerprint in
[CHANGELOG.md](CHANGELOG.md), so the schema can't change without a version and a changelog line.
