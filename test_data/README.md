# test_data

How we prove the system gives the right answers.

- `answer_keys/<state>/<place>/` — rules checked by hand by architects. We compare our rulebooks against these.
- `test_sites/<state>/<place>/<site>/` — real lots and Rhino models, with the results the checker should give.
  - `test_sites/new_york/ithaca_city/deep_run/`: one real lot per district family with a full design, every rule worked out by hand (queue item 12).
  - `test_sites/new_york/ithaca_city/light_run/`: one real address per residential district, for the start flow in Rhino (queue item 12).
- `interior_houses/`: five made-up houses with interiors (bedrooms, escape openings, stairs, guards, exit doors) in the host-neutral interior description, each measure worked out by hand first: egress measuring tested end to end without Rhino or Revit.
- `ifc_models/`: real building models in IFC (KIT's FZK-Haus first), each with the interior description the IFC reader (`packages/ifc_reading`) makes of it, values checked by hand from the file's own lines: egress measuring tried on real models before the Revit add-in.
