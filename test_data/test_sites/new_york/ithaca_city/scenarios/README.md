# R-1b design scenarios: hand-worked results

**Who worked them:** Claude (the AI that also helps build Gordium), by hand from the code's own words, before
Gordium was run on them. **Not yet verified by an architect**: until an architect reviews them (and is recorded
here with the date), they are a careful second reading, not an outside check.

Ten designs an architect really draws on a City of Ithaca R-1b lot, each with the result **worked out by hand
from the code's own words before Gordium was run on it**. The expected results are never changed to match
Gordium. When Gordium disagrees, the disagreement is investigated: either the code is fixed, or the question goes
to the architects (written up under `disagreements` in the scenario).

Each `<name>.yaml` holds:

- `lot`: the lot corners (feet; the street runs along the first edge), whether it's from a survey
- `buildings`: each solid on the Building layer. A building with `floors` is stacked floor blocks, each one story,
  the way GordiumStart draws them. `others`: solids on the lot that are **not** on the Building layer.
- `grade`: a flat finished grade (`elevation`) or spot grades placed at the walls (`points`)
- `then` (optional): an edit made after the first check (`move` the buildings by `[dx, dy]`) and its own
  expected results
- `expected`: for each rule, the status (complies / does_not_comply / needs_review), the arithmetic
  (`working`) and the code it comes from (`cites`). A rule's status is the most cautious of its rows in the
  panel (side yards are two rows: West and East).

The same file is checked two ways:

- in code: `packages/design_checker/tests/test_scenarios.py` (in CI) builds each site from the YAML with
  `design_checker.scenarios` and runs the checker on it
- in Rhino: `apps/rhino_plugin/tests/scenarios_in_rhino.py` draws each scenario in a Rhino document (lot on the
  Site layer, floor blocks on the Building layer, the other solids on Default, spot grades on Gordium::Grade)
  and runs the same check the plugin runs live

Where a result depends on an interpretation the architects haven't confirmed, the scenario says so and points
at the open question (in `4_term_definitions/definitions.yaml` or the rule's `open_questions`).
