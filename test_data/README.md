# test_data

How we prove the system gives the right answers.

- `answer_keys/<state>/<place>/` — rules checked by hand by architects. We compare our rulebooks against these.
- `test_sites/<state>/<place>/<site>/` — real lots and Rhino models, with the results the checker should give.
  - `test_sites/new_york/ithaca_city/deep_run/`: one real lot per district family with a full design, every rule worked out by hand (queue item 12).
  - `test_sites/new_york/ithaca_city/light_run/`: one real address per residential district, for the start flow in Rhino (queue item 12).
- `interior_houses/`: five made-up houses with interiors (bedrooms, escape openings, stairs, guards, exit doors) in the host-neutral interior description, each measure worked out by hand first: egress measuring tested end to end without Rhino or Revit.
- `ifc_models/`: real building models in IFC (KIT's FZK-Haus first), each with the interior description the IFC reader (`packages/ifc_reading`) makes of it, values checked by hand from the file's own lines: egress measuring tried on real models before the Revit add-in.
- `real_houses/`: real houses transcribed by hand from public drawings into the same interior description, every value cited to its sheet and callout (the drawings themselves stay outside the repository), with a hand-worked answer key for every egress rule. First: `orangetown_ny_80_south_william/`, a four-bedroom house in Orangetown, NY, under the 2025 Residential Code of New York State.
- `goldens/` — what the checker answers today for every test site, scenario and 200 stress designs (`check` and `start`), as canonical JSON and sha256. Written by code (`python -m design_checker.goldens --write`), never by hand; CI checks every answer is still the same, so a tidy-up can prove it changed no answer.
- `host_conformance/` — the test any design tool's add-in (Rhino now, Revit later) must pass: fixed scenes, the site description each must give, and the hand-worked verdicts; a tool that can't run on the Mac records its descriptions in `recorded/<host>/` ([README](host_conformance/README.md)).
- `sessions/<name>/` — recorded sessions with the checker: each request, a copy of the model it sent, and the exact answer. CI runs every request again and needs the same answer, every number to a millionth of a foot (`python -m design_checker.replay`). `seed_without_rhino/` was recorded without Rhino; a session recorded in Rhino (with `GORDIUM_RECORD_SESSION` set) goes beside it. `headless_calls/calls.jsonl` is different: host_core calls (arguments and answers) recorded while the tests drove the plugin's logic, which the protocol's parity test sends through the worker (`python -m design_checker.call_session --record`; docs/protocol/worker_protocol_v1.md).
