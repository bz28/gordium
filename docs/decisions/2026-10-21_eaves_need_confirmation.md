# An overhang is an eave only when the architect says so (2026-10-21)

**Purpose:** why Gordium never decides on its own that part of a building is an eave, and what it does instead.\
**For:** architects using the checker, and engineers working on measurement.\
**Kept current by:** the engineer who changes how overhangs are measured (`packages/model_measurement`), in that PR.

An **eave** is the edge of a roof that overhangs the wall below it. Ithaca lets eaves reach up to 2 ft into a required [yard](../glossary.md#yard) (§325-18B), while the walls themselves must stay out. So whether an overhang "is an eave" can decide whether a house complies. Words in links are defined in the [glossary](../glossary.md).

## Decision

1. **Yards and lot coverage are measured to the building's full outline**, overhangs included.
2. **Gordium never decides by itself that something is an eave.**
3. **An overhang that reaches into a required yard makes that yard "needs review"** until the architect marks it, in the panel, with "These are eaves".
4. **The confirmation is tied to that exact overhang.** It is saved as the lot fact `eaves_confirmed`, with a fingerprint of the overhang's whole 3D shape. Any change to the overhang changes the fingerprint, so Gordium asks again.
5. **The 2 ft limit is still checked.** A confirmed eave that reaches more than 2 ft into a yard still does not comply (§325-18B).

### Worked example

A house on 106 Ithaca Rd has walls 26'-0" from the front lot line; R-1b needs 25'-0". Its roof overhangs 1'-6", so the full outline is 24'-6" from the line.

| What the architect has done | Front yard result |
|---|---|
| Nothing yet | **Needs review**: complies to the walls (26'-0"), not to the full outline (24'-6") |
| Ticks "These are eaves" for that overhang | **Complies**: the walls meet the 25'-0" yard, and the eave reaches only 0'-6" into it (2'-0" allowed) |
| Then stretches the overhang to 3'-6" | **Needs review** again: the shape changed, so the confirmation no longer applies |
| Confirms the 3'-6" overhang | **Does not comply**: its edge, at 22'-6", reaches 2'-6" into the yard; eaves may reach only 2'-0" |

## Why

Three review rounds on the measurement PR each found a shape rule ("an overhang is an eave if…") that passed something that is not an eave: a gable volume, a mansard story, a knee wall. Each would have been a **false pass**, which Gordium promises never to give. The shape of a 3D model can't tell an eave from living space reliably; the architect can, in one click.

## What we rejected

- **Guessing from the shape** (for example "a thin roof solid with nothing below it"): failed three times in review, as above.
- **Measuring to the walls only**: passes every cantilever and gable that really is in the yard.
- **Always failing overhangs in a yard**: wrong for ordinary eaves, which the law allows.

## Consequences

- Most houses with eaves will show "needs review" on a yard until the architect marks each overhang once.
- The panel needs a "These are eaves" button (queued for the Rhino side after the measurement PR is clean).
- The decision is recorded with the project: who confirmed, when, and for which shape.

## Date and status

- **Date:** 2026-10-21
- **Status:** decided. Lands with PR #18 (`measurement-2`: pitched roofs, yard projections, accessory buildings, corner lots).
