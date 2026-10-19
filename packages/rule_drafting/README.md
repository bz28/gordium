# rule_drafting

Drafts the zoning rules for every residential district, with one recorded AI call per unit, and checks
every draft with code. Nothing it drafts is used to check a design until an architect approves it.

## The units

| Unit | Example | Who drafts it |
|---|---|---|
| A chart section | `chart-p3-yard_dimensions` (front, side and rear yards) | AI: a template per requirement |
| A piece of the law labeled rule or flag (`3_section_labels/`) | `325-16C` (the height bonus) | AI: a template per requirement |
| The permitted uses (chart page 2) | `chart-p2-primary_uses` | Plain code, from the marks •, SP, - (free) |

## Chart numbers are never typed

The AI writes a *template*: a rule whose chart numbers are slots.

```yaml
check: front_yard >= {front}
slots: [{name: front, page: 3, section: Yard Dimensions, row: Front (minimum),
         number: 1, numbers_in_cell: 1, percent: false, footnotes: []}]
```

Code (`templates.py`, `chart_values.py`) fills each slot from each district's own cell and cites that
cell (`{file, page, cell: {section, row, column}}`): R-1b gets `front_yard >= 25`, R-2b `front_yard >= 10`.
A cell that doesn't have the shape the template expects (another count of numbers, other footnotes, a
"-") is never filled: that district's rule goes to a person (the log's `unresolved`). Example: R-2C's lot
coverage "35%/40% /50% [fn12]" depends on the use, so a one-number template can't fill it.

## Every draft is checked

- Every quote is the city's exact words on its exact lines (the inspector's own matcher).
- Every number in a formula is written in one of the rule's own sources: a cited quote, or a cited chart
  cell or its row label (the inspector's number trace). A typed "25" with no source is sent back.
- The worked examples (a pass and a fail) must come out as stated.
- A fact we don't measure yet (e.g. "the accessory dwelling unit has a separate entrance") is never
  invented: the draft lists it in `new_measures`, it goes to `records/proposed_measures.yaml` for an
  engineer, and the rule can't be approved until it's added to `measures.yaml`.
- A rejected answer is sent back with the reason (up to 2 retries); after that the unit is listed for a person.
- The hand-drafted `5_zoning_rules/R-1b.yaml` is never shown to the AI: it's the answer key.

## How the drafts are graded (`tests/test_eval.py`, once drafts exist)

1. The drafted R-1b rules give the hand R-1b's outcome on every one of its worked examples.
2. They pass at each R-1B chart value they cite and fail just past it.
3. The architects' 106 Ithaca Rd spreadsheet still comes out the same on every row.
4. Every district's chart rules cite only that district's cells.
5. Every unit drafted produced rules, a reason, or an entry for a person; when the run is complete,
   every unit was drafted. Every drafted rulebook passes the inspector.

## Running it

```
pip install -e ".[labeling]"                        # the Anthropic SDK; only for real runs
python -m rule_drafting status                      # what's drafted, and what's waiting for a person
python -m rule_drafting estimate --limit 10         # cost first; exact with a key, rough without
python -m rule_drafting draft --limit 10            # shows the estimate, sends nothing
python -m rule_drafting draft --limit 10 --yes      # drafts them; --only UNIT... or --all also work
python -m rule_drafting cost                        # what the recorded runs actually cost
```

Settings are in `rule_drafting/settings.yaml` (default `claude-sonnet-5-5`, effort medium, budget $5.00).
The budget is a hard cap kept in `~/.config/gordium/rule_drafting_ledger.json`, separate from labeling's,
with the same rules: a run whose estimate exceeds what's left is refused, and no call is sent whose worst
case could cross the cap. Drafting never runs in CI; the tests use a fake client.

## Where things go

- `5_zoning_rules/drafted/<district>.yaml` and `general.yaml`: the drafted rulebooks (checked by
  `python -m rule_format` like any rulebook).
- `5_zoning_rules/drafted/records/`: `drafting_log.yaml` (per unit: rules, reason, what goes to a person),
  `proposed_measures.yaml`, and `runs/` (every AI call: prompt and input fingerprints, the raw answer,
  tokens, cost). Re-drafting a unit replaces its drafts, never an approved one.
