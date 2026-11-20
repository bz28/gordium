# design_checker

Checks a design in one call: measure the model (`model_measurement`), run the zone's rules through the project
report (`project_report.tables`, so every result comes from the checker's `outcome()` and a rulebook that fails
its checks is refused), and work out the envelope (`envelope_builder`). Plain code, no AI.

```
python -m design_checker <model.3dm> <model_facts.yaml>   # prints the summary and every row
python -m design_checker serve                            # for Rhino: one JSON request per line, one answer per line
```

Requests to the worker: `check` (a model and its lot facts), `start` (the largest legal starting building for
the lot in a model, `envelope_builder.start`), `sample_site` (the plugin's place's sample lot, from its jurisdiction.yaml: 106 Ithaca Rd's lot and facts, as files
drawn from the sample before 2026-10-27 have them; GordiumStart no longer prefills it: a new file starts empty), `options` (zones and uses), `facts` (what's wrong with saved lot facts).

**The site description** (`site_json.py`; the contract is
[docs/protocol/site_description_v1.md](../../docs/protocol/site_description_v1.md)): the lot and buildings as plain
JSON, `gordium.site/1`, so another design tool (Revit) can send what Rhino sends. `validate` refuses anything not
exactly v1, every reason listed; `to_site` and `from_site` turn a description into the site the measuring reads and
back (each problem goes by its code in `model_measurement.stops`, read back from its words by `stops.code_of`). The
worker's new-style commands name their protocol (`protocol.py`): `hello` (the protocol, the schema version and
fingerprints of the code and rules), `read_model` (a .3dm as a site description), `check_site` and `start_site`
(check and start for a description: `check.check_description`, `check.start_description`). The older commands
answer exactly as before, with or without a protocol, and go the same way: `check()` and `start()` read the
model, make it a description (`site_json.legacy_description`), send it through JSON text and back, and check
that. A zoning report keeps the exact description beside it (`<report name>.site.json`).

**The session commands** (protocol 1.2, `protocol.COMMANDS`; every command and field in
[docs/protocol/worker_protocol_v1.md](../../docs/protocol/worker_protocol_v1.md)): the start box's, the panel's
and the live check's decisions, `host_core/`'s functions served to a second design tool by a fixed table
(`facts.*`, `box.view`, `box.pick`, `lookup.*` with edit plans, `streets.*`, `session.freshness`, `session.undo`,
`report.message`, `panel.rows`, and from 1.1 `objects.left_out`: which objects a check leaves out). Each part of a command is one named host_core function; stateless (the tool sends
its facts and box choices and gets the new ones back). Rhino still calls host_core directly. The proof that each
answer is the in-process one: `tests/test_protocol.py` replays `test_data/sessions/headless_calls/` (host_core
calls recorded while the tests drove the plugin's logic: `python -m design_checker.call_session --record`, through
`host_core.worker_client.CallRecorder`) through the worker.

**The host conformance suite** (`conformance.py`, `conformance_rhino.py`;
[test_data/host_conformance/README.md](../../test_data/host_conformance/README.md)): fixed scenes (a curved wall, a
block, a garage left out, millimetres, survey coordinates, a corner lot…) that any design tool's reading must turn
into the expected description, every point within a millionth of a foot, with the same ids, problem codes and
left-out objects, and exactly the hand-worked verdicts through `check_site`. A tool that sends fewer problems than
expected fails. The Rhino reference adapter (rhino3dm) runs in CI; a tool that can't run on the Mac (Revit)
records its descriptions once on its own machine (`recorded/<host>/`) and the same test checks them.
`python -m design_checker.conformance` runs it.

**Golden answers and recorded sessions** (the yardstick for changes that must not change any answer):
`python -m design_checker.goldens --check` runs `check` and `start` on every test site, scenario (and its edit),
deep-run site and 200 stress designs from a fixed seed, and compares each canonical answer with
`test_data/goldens/` (`--write` writes them again, only when an answer should change). Every verdict, status, word
and number must be exactly the golden's; only a shape's list of points may differ, on an Intel or AMD computer
(CI) where two near-coincident curves give the overlay other crossing points, and then only if each shape is the
same line within 0.00001 ft (`goldens.same_shape`, `GEOMETRY_TOL`). `python -m
design_checker.replay` runs every request of each recorded session in `test_data/sessions/` through the worker's
`answer()` and needs the recorded answer (compared in the goldens' canonical form: a number's last digit
may differ between a Mac and Linux or Windows). Both run in CI.

**Rules for each part** (`each_part.py`, egress step 2): `check_parts(rules, parts, values, allowed)` runs a
rulebook's per-part rules (`for_each`: bedrooms, escape openings, stairs; `rule_format/parts.py`) over the parts
given, one row per part with a line naming it ("Bedroom 2 › Window 5: net clear area 5.1 sq ft, needs ≥ 5.7 sq ft"),
and gives panel items whose overall answer is `present.state`'s with the zoning rows. Parts `None` (the interior
isn't being checked) is one counted "Interior: not checked yet" item, needs review
([decision](../../docs/decisions/2026-11-12_rules_for_each_part.md)).

**Egress** (`egress.py`): every check also runs the building-code rules of each state law its place inherits
(Ithaca: New York's house code, `inherits:`), on the parts `model_measurement.interior` measures from an interior
description given beside the site (`check_site(..., interior=...)`; `python -m design_checker <model> <facts>
--interior <house.yaml>`). The view's `sections` give zoning's and egress's states apart; with no interior drawn,
egress is one "waiting, no rooms drawn yet" item, never a pass (with zoning complying, the headline reads "Zoning
complies · Egress waiting: no rooms drawn yet", shown grey with `waiting_only`, its state still needs review: choice
B, Ben 2026-11-15); handrails, guards and sleeping lofts aren't read
from the drawing yet, so their rules need review (decision item 12). The code sections the law's rulebook has no
rules for yet (the generated `6_coverage_report/<book>.rules.yaml`, `not_checked_yet`) are one needs-review line,
"Not checked yet by Gordium: window fall protection (R321.2.1), hallway width (R318.6) and 84 more: check these by
hand", so egress never reads as complying while whole sections were never checked; their plain names are the state
folder's `section_names.yaml`. While egress waits, the waiting row's detail lists them instead (Ben, 2026-11-15).

**The place.** The plugin checks one place, the registry's only one (`rule_format.place.plugin_place`).
`rhino_logic.py` runs in Rhino's Python, which can't read YAML, so `host_core/place.py` reads `place.json` beside
`rhino_logic.py`: the place's name, time zone and how its addresses are written, copied from its `jurisdiction.yaml`
by `python -m rule_format place --write` and checked current in CI. Never edit `place.json` by hand.

**host_core/** holds the half of the plugin's logic that has nothing to do with Rhino, so a second host (a Revit
add-in) can use it: `facts` (the facts the architect states, the use questions, the row dialog), `streets` (which
lot edges face a street, one street or two), `lookup` (an address lookup's answer, saved addresses), `start_box`
(the start box's rows, buttons and reset), `place`, `freshness` (whether the results on screen are current, the
undo steps' names, the panel's actions refused while a box is open), `report` (the report's and long work's words),
`panel_words`, `context` (the neighbourhood around a looked-up lot), `edits` (the start box's model edits as one
transaction) and `worker_client` (the reference Python client of the checker: its pipes, one request and its
answer, a Job, the session recorder). Like `rhino_logic.py` it is Python 3.9 and the standard
library only, because Rhino 8 imports it into its own Python 3.9. `rhino_logic.py` still offers every one of its
names (`logic.box_rows is host_core.start_box.box_rows`) and refuses `logic.X = ...` for them, since that would
change a copy host_core never reads; a test swaps such a name with `tests/moved_names.py`'s `patch_moved`.

What it adds for the Rhino command, never changing a result:
- **summary:** the check's own answer: its state ("pass", "complies" under every reading, "review", "fail") never
  less cautious than the panel's, its text the panel's own line (`present.summary`, one summary everywhere), and
  its lines what fails and by how much ("Rear yard 22 ft, needs ≥ 22.5 ft (0.5 ft short)") and what waits. A row
  still waiting (a fact to answer, a rule not in this release) is never a pass (Ben, 2026-11-09). An Ithaca result
  lists the overlays row (so never passes) unless the address lookup positively found no overlay on this very lot:
  the lot fact `overlays_none_found`, honoured only while the lot is still the outline (and the address) it was found
  for, and not once the architect says the lot is in the South Hill Overlay
  (`present.overlays_cleared`; Ben, 2026-11-11, option A), and only while it is at most 90 days old on the day the
  host gives (`present.overlays_lookup`, `LOOKUP_FRESH_DAYS`; Ben, 2026-11-12). The site lines say how old it is
  ("flood map and City maps looked up 2 months ago (2026-08-14)"); older, dated after today, or with a date that
  can't be read, the row stays and says to look the address up again or check them by hand; with no day given, to
  check them by hand.
- **today:** the day of the check, `YYYY-MM-DD` (the worker's `"today"`, `check(..., today=)`). The host says it
  (the plugin: `rhino_logic.city_day()`, Ithaca's own day; the command line: the same); the checker never reads the
  clock, so the same design, saved facts and day give the same answer. A request without it still checks; only the
  lookup's age can't be told, so the overlays row stays. A value that isn't a day is refused.
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
- **Unknown:** a NEEDS REVIEW rule waiting on values that aren't measured or given at all (the height, with no
  ground given) fails whatever they are when each missing number is provably truest at 0 (`formula.truth_direction`:
  only +, −, max/min and positive multiples of it, compared with < ≤ > ≥), each missing yes/no is tried both ways,
  and the rule fails under every one of those settings (`check.fails_whatever`; run before a rule waiting on an
  interior fact is set aside, so a proven fail is never hidden). The eaves rule
  is one: front eaves ≥ 25 + max(height − 35, 0) − 2 is at least 23 ft at any height, so eaves 15 ft back don't
  comply. Never the other way: a missing number never causes a pass (24 ft stays needs review); a rule complies with one
  missing only when the known numbers already settle it, whatever the missing one is (three-valued logic).

The worker stays running, so a re-check after an edit doesn't pay for starting Python again. A bad request gets a
plain error answer; the worker keeps serving.
