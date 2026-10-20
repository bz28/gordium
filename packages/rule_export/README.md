# rule_export

Writes each jurisdiction's rules as a spreadsheet people can read and check: every rule, definition, open
question and section label, each with the city's exact words and a link that opens the city's document at
that page. Plain code, no AI. Generated from the rule files and never edited by hand.

```
python -m rule_export            # writes regulations/jurisdictions/<state>/<place>/<place>_rules.xlsx
python -m rule_export --check    # CI: fails if the committed workbook differs from a fresh build
```

For Ithaca: `regulations/jurisdictions/new_york/ithaca_city/ithaca_city_rules.xlsx`. The file is rewritten
only when its content changes. `--check` compares what the workbook says (sheets, cell values, links),
not its bytes, because Excel files carry timestamps.

## The tabs

Styled like the architects' own spreadsheet: Arial, a bold title in row 1, headers in row 2 (frozen),
wrapped text.

| Tab | One row per | Columns |
|---|---|---|
| **Rules** | source of a rule, in every rulebook in `5_zoning_rules/` (hand or AI drafted, any subfolder) | Zone · Rulebook · Rule id · Title · Status · Drafted by · Kind · Topic · Check (formula) · Applies when · Needs review when · Worked examples · Source (1 of 3) · Document · Page · Lines · City's exact words · Link · Open questions · Answers · Notes |
| **Definitions** | source of a definition | Id · Term · Status · Drafted by · Measures · Source · Document · Page · Lines · City's exact words · Link · Open questions · Answers · Notes |
| **Uses** | source of a use name (the only values a rule's `use` may take) | Id · Name · Status · Drafted by · Source · Document · Page · Lines · City's exact words · Link · Notes |
| **Questions** | open question anywhere (rules, definitions, uses, section labels) | About · In (which file) · Id · Question · Document · Page · Link |
| **Coverage** | piece of each cut law (all 626 of Chapter 325), in order | Document · Piece · Title · Pages · Label · Topic · Reason · Quote(s) · Link · Status · Drafted by · Changed after the AI · Open questions · Answers · Notes |
| **Sources** | source document | File · Title · Publisher · Official URL · Downloaded · Pages · Fingerprint · Quotable · Why not quotable |

**One row per source.** A rule quoting three passages has three rows, so each quote sits next to its own page
and link. What identifies the rule (zone, rulebook, rule id, title, status, drafted by) repeats on every row,
so sorting and filtering keep a rule together and two rulebooks with the same rule id stay apart; the long
fields (check, conditions, examples, questions, answers, notes) are on the rule's first row only.

**Every field is accounted for.** `workbook.SHOWN` lists the fields each tab shows and `workbook.HIDDEN` the ones
left out on purpose, with the reason (the approval fields, while approval is deferred; fingerprints and run-record
paths, which are for code). A test holds both to the formats' own field lists, so a new field can't silently go
missing.

**Status and Drafted by.** Every rule is a draft: human approval is deferred (see `CLAUDE.md`). "Drafted by"
says where it came from: `claude` for rules drafted in conversation (the hand-written R-1b), a script name
(e.g. `section_labeling/claude-haiku-5-5`) for output of a recorded AI run. "Changed after the AI" lists each
later change in order: from → to, who, when, why.

**Text stays text.** Every cell holding words is stored as text, so a quote or an AI-written note that happens to
start with `=` is shown, never run as a formula; characters Excel can't hold appear as `�`.

## Links

- **The city's own URL** when it serves the PDF itself (an address ending in `.pdf`, or a city DocumentCenter
  file): the zoning charts, the maps, the Southside ordinance. Links add `#page=N`, which browsers' PDF viewers
  honor.
- **Otherwise the fingerprinted copy in this repository** (`https://github.com/bz28/gordium/blob/main/…#page=N`):
  Chapter 325, whose official home (eCode360) is an HTML page where our page numbers mean nothing.

Known limits:
- The repository is private, so repository links open only for people with access to it.
- Links point at `main`, so they work once the PR adding the file is merged.
- GitHub's built-in PDF viewer may ignore `#page=N`; the page number is always shown in its own column.
- The city may replace a document at the same address. The fingerprint in the Sources tab identifies the exact
  version every quote was checked against.
