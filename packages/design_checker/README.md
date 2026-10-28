# design_checker

Checks a design in one call: measure the model (`model_measurement`), run the zone's rules through the project
report (`project_report.tables`, so every result comes from the checker's `outcome()` and a rulebook that fails
its checks is refused), and work out the envelope (`envelope_builder`). Plain code, no AI.

```
python -m design_checker <model.3dm> <model_facts.yaml>   # prints the summary and every row
python -m design_checker serve                            # for Rhino: one JSON request per line, one answer per line
```

Requests to the worker: `check` (a model and its lot facts), `start` (the largest legal starting building for
the lot in a model, `envelope_builder.start`), `sample_site` (106 Ithaca Rd's lot and facts, as files
drawn from the sample before 2026-10-27 have them; GordiumStart no longer prefills it: a new file starts empty), `options` (zones and uses), `facts` (what's wrong with saved lot facts).

What it adds for the Rhino command, never changing a result:
- **summary:** one line for the viewport corner: "All 10 rules pass", or "9 pass · 1 fail" with what fails and
  by how much ("Rear yard 22 ft, needs ≥ 22.5 ft (0.5 ft short)").
- **Why:** for a NEEDS REVIEW row, the measuring's own reason ("enter bedrooms / parking spaces", "a building
  isn't inside the lot").
- **red:** the objects a failing rule measured (never the lot).
- **dims:** each failing distance as the two points it was measured between, to draw in the model.
- **interior:** a rule waiting only on a fact about the inside of the building (bedrooms, parking spaces) goes in
  its own group, out of the counts: this phase checks the outside. Once those facts are entered, the rule is shown
  like any other, a FAIL included: nothing that fails is hidden.
- **Provisional / Fails:** a NEEDS REVIEW rule waiting only on an open question (a measurement with readings, or a
  lot not yet surveyed, whose one reading is the lot as drawn) is worked out under every combination of readings.
  If it passes under all of them, the row says so ("passes under every reading", "passes with the lot
  as drawn (confirm the survey)"); if it fails under all of them, it counts as failing (red, and in the "now
  fails" note). The result itself stays NEEDS REVIEW: only `outcome()` decides results. The summary then says
  "Complies" when nothing fails and every open question about how the law reads passes whichever way it is
  answered. A rule that passes only with the lot as drawn (no survey yet) stays amber, needs review: a missing
  survey is a missing fact, so it never shows as complying.

The worker stays running, so a re-check after an edit doesn't pay for starting Python again. A bad request gets a
plain error answer; the worker keeps serving.
