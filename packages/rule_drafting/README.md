# rule_drafting

Drafts the zoning rules for every residential district, and a state's building-code rules (New York's house
egress, `--state`, below), with one recorded AI call per unit, and checks every draft with code. Drafts stay marked draft: architect approval is deferred for now (decided 2026-10-19),
so a draft that passes every code check can be used; people read the rules through the rules spreadsheet.

## The units

| Unit | Example | Who drafts it |
|---|---|---|
| A chart section | `chart-p3-yard_dimensions` (front, side and rear yards) | AI: a template per requirement |
| A piece of the law labeled rule or flag (`3_section_labels/`) | `325-16C` (the height bonus) | AI: a template per requirement |
| The permitted uses (chart page 2) | `chart-p2-primary_uses` | Plain code, from the marks •, SP, - (free) |
| The accessory uses (chart page 2) | `chart-p2-accessory_uses` | Not drafted yet: recorded with the reason (no measure of accessory uses yet) |

**Related sections.** Each unit also gets, as background, the requirement sections (labeled rule or flag) that
use the same defined words, from the term index (`4_term_definitions/term_index.yaml`): the yard chart unit reads
§325-18B, the eaves rule. They are the most relevant first (most uses of those words per word of text), at most
12,000 characters, and any left out are named. The AI may not quote them or draft from them (each sets its own
rules, drafted from its own unit); if the unit's rule depends on one, it says so in an open question. A question a
draft raises gets a research entry saying it is pending (nothing searched yet), so it passes the show-your-work
check honestly.

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
"-") is never filled: that district's rule goes to a person (the log's `unresolved`). And every district cell of a
chart section that states something (anything but "-" or empty) must be cited by a saved rule or listed for a person,
whatever the drafter answered, so a row it skipped can't vanish in any district. The permitted-use rules (page 2) are
built by code; the notes on their rows and column headings (occupancy, the South Hill Overlay) are quoted and listed
for a person, since no measure checks them. Every footnote a filled cell
carries must be quoted (and applied): "25%/ 50 ft [fn16]" needs note 16, "But not less than 20 ft." A chart quote must
be a footnote printed under a table, never a table row, so a cell's number can reach a rule only through a slot
filled from that district's own cell. A number the AI types (not a slot) must be bound, in the answer's `numbers`, to one evidence item it names, and code checks that exact item holds the value. Code can check that evidence holds a number, never what the number is about (note 7's "1-3 units" and the parking row's "First three" look alike), so only evidence that belongs to the rule itself is trusted (Ben's decision, 2026-10-20): a footnote whose marker is on the slot's own cell ("50 ft [fn16]": note 16), that slot's own row label ("First three bed or sleeping rooms"), or a sentence of the paragraph being drafted. Anything else (a note on another cell, on the row label or on the section heading, or a sentence of another section of the law) is refused: the unit is retried and then listed for a person, so an untrusted number never reaches a rule. A trusted footnote or row label backs a number only where the number stands with that slot (in the same arithmetic or min/max, or in the condition that picks the slot's value), each place a number is typed checked on its own, and only where that slot occurrence itself decides something (changed alone, some worked example comes out differently), so `0 * {x}` or `min(3, {x})` can't smuggle in a cell's note. A flag has no check. A number that only labels or points ("(3)", "§ 325-20D(1)", "Column 12") doesn't count, and a percent counts only as its fraction (25% is 0.25). The grading tests give a drafted rule's declared new measures the value its own passing example gives them, and name, in the disagreement, every other input the hand example lacks (never filled from the draft), so a missing input never hides a disagreement. Example: R-2C's lot
coverage "35%/40% /50% [fn12]" depends on the use, so a one-number template can't fill it.

## Every draft is checked

- Every quote is the city's exact words on its exact lines (the inspector's own matcher).
- Every number in a formula is written in one of the rule's own sources: a cited quote, or a cited chart
  cell or its row label (the inspector's number trace). A typed "25" with no source is sent back.
- The worked examples (a pass and a fail) must come out as stated.
- A fact we don't measure yet (e.g. "the accessory dwelling unit has a separate entrance") is never
  invented: the draft lists it in `new_measures`, it goes to `records/proposed_measures.yaml` for an
  engineer, and the rule can't be approved until it's added to `measures.yaml`.
- A law piece is drafted from its **whole text**: every line, numbered L1, L2, ... with page breaks marked (the
  labeler's numbering). The lines its reviewed label cites (`3_section_labels/`) are shown only as hints, since an
  older label may cite just a heading; any cited line no drafted rule cites goes to a person.
- A template that works for no district sends the whole answer back with the reasons (up to 2 retries); after the
  last attempt the templates that work are kept and the rest go to a person. So does a rule id another unit took.
- The hand-drafted `5_zoning_rules/R-1b.yaml` is never shown to the AI: it's the answer key. The drafting rules the
  AI reads use neutral examples, not R-1b's.

**Rules for each part** (egress step 3a; building-code text, not yet drafted for real): with `for_parts` (the
answer's shape and the instructions both), a template also says `for_each`, `within` and `when_none`, and each worked
example is a small design: the building's measures, the parts, and every row expected. Code checks it exactly like a
zoning draft (quotes, numbers), and its examples with the checker's own rows; one must show `when_none`, and parts must
pass and fail the check (a "none" row doesn't count), or the draft is sent back. Whether a chart number decides something is judged on the rows, never on `outcome()` (which always
says needs review for a rule for each part). A zoning run sends exactly what it always did. Tests use synthetic text
only (`tests/test_drafting_parts.py`). Design: [the decision](../../docs/decisions/2026-11-12_rules_for_each_part.md),
points 9 to 11.

## How the drafts are graded (`tests/test_eval.py`, once drafts exist)

1. The drafted R-1b rules give the hand R-1b's outcome on every one of its worked examples.
2. They pass at each R-1B chart value they cite and fail just past it, and every number of every cell they cite
   is used in the formula and decides something (changing it changes an outcome).
3. The architects' 106 Ithaca Rd spreadsheet still comes out the same on every row.
4. Every district's chart rules cite only that district's cells.
5. Every unit drafted produced rules, a reason, or an entry for a person; when the run is complete,
   every unit was drafted. Every drafted rulebook passes the inspector.

The answer key's examples are judged as R-1b lots (the checker always knows the district). A rule drafted from a
piece of the law is compared on what it quotes, not on the chart cells it reads as inputs, the answer key's own
convention.

**The 10-unit test batch** (`evals/2026-10-20_prompt_a/`, with its records, scripts and every judged difference):
with the current instructions (prompt A), 202 rules, 9 of 9 units accepted, R-1b examples 29/32, the architects'
spreadsheet 10 of 11, chart rows exact 14/14, no law exception passing what the answer key fails, for $0.499. The
earlier prompt, replayed through today's checks, gave 152 rules, 19/29 and 9 rows. Model choice (Sonnet over
Haiku): `evals/2026-10-19_model_choice/`.

## Running it

```
pip install -e ".[labeling]"                        # the Anthropic SDK; only for real runs
python -m rule_drafting status                      # what's drafted, and what's waiting for a person
python -m rule_drafting estimate --limit 10         # cost first; exact with a key, rough without
python -m rule_drafting draft --limit 10            # shows the estimate, sends nothing
python -m rule_drafting draft --limit 10 --yes      # drafts them; --only UNIT... or --all also work
                                                    # (ends by rewriting the labels' review list, as labeling does)
python -m rule_drafting cost                        # what the recorded runs actually cost
```

Settings are in `rule_drafting/settings.yaml` (default `claude-sonnet-5-5`, effort medium, budget $20.00).
The budget is a hard cap kept in `~/.config/gordium/rule_drafting_ledger.json`, separate from labeling's,
with the same rules: a run whose estimate exceeds what's left is refused, and no call is sent whose worst
case could cross the cap. Drafting never runs in CI; the tests use a fake client.

## A state's building code (`--state`, `rule_drafting/book.py`)

`python -m rule_drafting draft --state new_york/new_york_state --all --yes` drafts New York's house egress: the
units are the book pieces labeled rule in `book.SCOPE`; there is no chart, so no slots; every number must be one
of the piece's second-reading numbers, used the way the law reads it (`rule_format/code_numbers.py`); rules are
for each part (`rule_format/parts.yaml`). Related sections are the pieces labeled rule or flag that name the unit
or a section above it (Appendix BO left out). Drafts go to `<state folder>/5_building_code_rules/drafted/`.
`python -m rule_drafting.book_eval` grades them against the hand answer key, rule by rule
(`evals/2026-11-13_house_egress/`). Why and how: `docs/decisions/2026-11-13_house_egress_rules.md`.

## Where things go

- `5_zoning_rules/drafted/<district>.yaml` and `general.yaml`: the drafted rulebooks (checked by
  `python -m rule_format` like any rulebook).
- `5_zoning_rules/drafted/records/`: `drafting_log.yaml` (per unit: rules, reason, what goes to a person),
  `proposed_measures.yaml`, and `runs/` (every AI call: prompt and input fingerprints, the raw answer,
  tokens, cost). Re-drafting a unit replaces its drafts, never an approved one.
