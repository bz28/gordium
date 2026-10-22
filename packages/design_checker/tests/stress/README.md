# The architect stress test

A computer plays the architect: it starts from Gordium's own starting house on six lots, makes 1 to 6 random
edits the way an architect does in Rhino, and checks each result twice: with Gordium (its public entry points
only) and with an independent answer key, the oracle, written from R-1b.yaml and the definitions. If Gordium says
a rule complies where the oracle says it fails under every reading, that is a false pass (principle 4).

| file | what it is |
|---|---|
| `oracle.py` | the answer key: plan geometry (shapely) from the design's own outlines, every unclear point a range, PASS / FAIL / UNDECIDED per rule |
| `generate.py` | the lots, Gordium's starting house on each, the edits, and the design as Gordium's input (faces) or as a Rhino file |
| `harness.py` | runs Gordium, checks the invariants (a, a2, b, c, d, e, f), shrinks each failure to its fewest edits; also the long-run command line |
| `test_oracle.py` | the oracle checked first: every worked example in R-1b.yaml, and hand-worked designs |
| `test_stress.py` | the random sample; each known finding recognised by its cause |
| `test_stress_findings.py` | every finding (F1-F17) shrunk to its fewest edits, as a named test; open ones strict-xfail |
| `explain.py`, `compare.py` | one case side by side (oracle vs Gordium; one drawing vs another) |
| `conftest.py` | skips the full sizes unless asked (the option and marker are in the repository's root `conftest.py`) |

## Two sizes

Every sampled test has a small, fixed CI size and a full size marked `slow`. CI runs the small one (the whole
folder in under a minute of CPU); the full one runs only when asked:

```
pytest --runslow          # from anywhere (registered in the root conftest.py); or GORDIUM_STRESS_SLOW=1
```

| test | CI | full (`slow`) |
|---|---|---|
| `test_the_architect_stress_sample` (all invariants) | 40 designs (`GORDIUM_STRESS_DESIGNS` changes it) | 300 designs |
| `test_every_row_that_needs_review_says_why_over_a_stress_sample` | 20 designs | 60 designs |
| `test_every_measurement_is_the_same_whichever_way_and_from_wherever_the_outlines_are_drawn` | the 6 lots, F16's case and 12 designs | 40 designs |
| `test_drawing_the_house_as_floor_blocks_a_solid_or_a_mesh_never_flips_a_row_between_fails_and_complies` | the 6 lots, F17's case and 5 designs | 15 designs |
| `test_F5_a_side_yard_named_by_compass_only_holds_distances_to_that_line` | turned 0 and 90 degrees | 0, 90, 180 and 270 |

The seeds are fixed (same seed, same designs, same answers).

## Long runs

```
python packages/design_checker/tests/stress/harness.py --designs 2000 --seed 41 --workers 4 --out run.json
```

runs a long sample in parallel and prints every violation with its shrunk reproduction. Run one at a time (the
checker is CPU-heavy). PR #22's description lists every long run so far.
