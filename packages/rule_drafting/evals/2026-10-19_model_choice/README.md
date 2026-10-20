# Eval 2026-10-19: which model drafts (Haiku vs Sonnet)

**Question:** can the cheaper model, Haiku, draft rules, or is Sonnet needed?

**How:** the same 10 test units (chart page 2 uses, built by code, plus 9 AI units: chart page 3 lot size, lot
width, building height, lot coverage and yards, chart page 14 residential parking, and law pieces 325-16C,
325-18A and 325-19C) were drafted with each model. Both runs used the same prompt (commit 6f3bdd8), the same
settings (effort medium, 8,192 output tokens, up to 3 attempts per unit) and the same checks.

| | Haiku (`runs/2026-10-19_claude-haiku-5-5.jsonl`) | Sonnet (`../2026-10-20_prompt_a/runs/baseline_2026-10-19_claude-sonnet-5-5.jsonl`) |
|---|---|---|
| AI units with a usable answer | **4 of 9** | 9 of 9 |
| Why a unit failed | 4 units ran out of room on every attempt (lot size, lot width, yards, 325-16C stopped at the token limit); 1 unit (lot coverage) was cut off twice, then gave an answer code rejected | none |
| Corner lots (325-19C) | a checkable rule on two measures it proposed (`corner_lot`, and one `yards_facing_public_street_min_depth` standing for every street-facing yard), plus a flag, with open questions on what a corner lot is and which yards face a street | no rule, with the reason: no measure says whether a lot is a corner lot or which yards face a street |
| AI calls / cost | 25 / $0.090 | 17 / $0.549 |

**Choice: Sonnet.** Haiku is about 6 times cheaper, but it left more than half the units undrafted (mostly
answers too long for the token limit, which a larger limit would also make dearer). On corner lots, Haiku's rule
settles in the formula a question it lists as open itself (which yards face a street), while Sonnet declined. Both
are safe until an engineer adds the measures; the undrafted units decide it. The
numbers above are computed from the two run records (each line is one recorded AI call: its unit, attempt,
stop reason, raw answer, the problem code found, and cost).
