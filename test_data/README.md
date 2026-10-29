# test_data

How we prove the system gives the right answers.

- `answer_keys/<state>/<place>/` — rules checked by hand by architects. We compare our rulebooks against these.
- `test_sites/<state>/<place>/<site>/` — real lots and Rhino models, with the results the checker should give.
  - `test_sites/new_york/ithaca_city/deep_run/`: one real lot per district family with a full design, every rule worked out by hand (queue item 12).
  - `test_sites/new_york/ithaca_city/light_run/`: one real address per residential district, for the start flow in Rhino (queue item 12).
