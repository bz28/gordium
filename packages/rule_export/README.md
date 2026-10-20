# rule_export

Writes each jurisdiction's rules as a spreadsheet people can read and check: every rule, definition, open
question and section label, each with the city's exact words and a link that opens the city's document at
that page. Plain code, no AI. Generated from the rule files and never edited by hand.

```
python -m rule_export            # writes regulations/jurisdictions/<state>/<place>/<place>_rules.xlsx
python -m rule_export --check    # CI: fails if the committed workbook differs from a fresh build
```

For Ithaca: `regulations/jurisdictions/new_york/ithaca_city/ithaca_city_rules.xlsx`. The file is rewritten
only when its content or look changes. `--check` compares what the workbook says and how it looks (sheets;
each cell's value, link, font, fill, left border and alignment; column widths; frozen panes), not its bytes,
because Excel files carry timestamps.

## The tabs

Styled like the architects' own spreadsheet: Arial in their ink color (dark slate), a bold 16-pt title in
row 1, bold 12-pt headers in row 2 (frozen), 11-pt wrapped text.

**Citations.** Every quote has a **Citation** a reader can follow: the document's title (from
`sources.yaml`), the section it is in (for a document cut into sections), the page and the lines, e.g.
"City of Ithaca Code, Chapter 325 Zoning (full text), §325-8A, p.24, lines 15–16" or "City of Ithaca Zoning
Charts (April 2026), p.3, line 31". A rule that cites a chart cell (rather than quoting a line) is cited by
its section, row and district column, e.g. "City of Ithaca Zoning Charts (April 2026), p.3, Yard Dimensions ·
Rear · R-1B", and its exact words are the cell's value as the chart reader read it; a cell the chart reader
can't confirm says "(not verified …)" instead of a blank. The city's exact words are in their own column, and
**Link** ("Open p.N") opens that page.

| Tab | One row per | Columns |
|---|---|---|
| **Rules** | source of a rule, in every rulebook in `5_zoning_rules/` (hand or AI drafted, any subfolder) | Zone · Rulebook · Rule id · Title · Status · Drafted by · Kind · Topic · Check (formula) · Applies when · Needs review when · Worked examples · Source (1 of 3) · Citation · Page · City's exact words · Link · Related sections · Open questions · Research (why still open) · Findings (research settled) · Answers · Notes |
| **Definitions** | source of a definition | Id · Term · Status · Drafted by · Measures · Source · Citation · Page · City's exact words · Link · Related sections · Open questions · Research (why still open) · Findings (research settled) · Answers · Notes |
| **Uses** | source of a use name (the only values a rule's `use` may take) | Id · Name · Status · Drafted by · Source · Citation · Page · City's exact words · Link · Notes |
| **Questions** | open question anywhere (rules, definitions, uses, section labels) | About · In (the file the question is written in) · Id · Question · Searched (the sections read for it) · Why still open · Readings in play · Research report · Citation · Page · Link |
| **Findings** | question research settled | About · In · Id · Finding (its id) · Kind (law / reading) · Strength · Confirm with · Question · Answer ("The law: …" or "Gordium's reading (…) · confirm with …") · Still open (the open questions it leaves open, by tag) · Sources (the code's quotes, then ranked records, with links) · Research report · Link (the first quote's page) |
| **Coverage** | piece of each cut law (all 626 of Chapter 325), in order | Document · Piece · Title · Pages · Label · Topic · Reason · Quote(s), each with its page and lines · Link (the first quote's page) · Status · Drafted by · Changed after the AI · Open questions · Research (why still open) · Findings (research settled) · Answers · Notes |
| **Sources** | source document, then each one not yet downloaded | File · Title · Publisher · Official URL · Downloaded · Adopted · Created · Pages · Fingerprint · Quotable (yes / no / not downloaded) · Why not quotable / not downloaded · Contents · Notes |

**Related sections** come from the term index (`4_term_definitions/term_index.yaml`): for a definition, every
piece of the law that uses its word or a synonym; for a rule, the requirement sections (labeled rule or flag) that
use the words it quotes, most relevant first, less the sections the rule itself cites. Both on an entry's first row.

**One row per source.** A rule quoting three passages has three rows, so each quote sits next to its own page
and link. What identifies the rule and what readers filter on (zone, rulebook, rule id, title, status, drafted by,
kind, topic) repeats on every row, so sorting and filtering keep a rule together and two rulebooks with the same rule id stay apart; the long
fields (check, conditions, examples, questions, answers, notes) are on the rule's first row only.

**Every field is accounted for.** Each tab's columns are declared once in `workbook.COLUMNS`: header, width,
the field it shows, and how to fill it. `workbook.HIDDEN` lists the fields left out on purpose, with the reason
(the approval fields, while approval is deferred; fingerprints, run-record paths and the document `layout`, which
are for code). Tests hold the shown and hidden fields to the formats' own field lists, and fill each field to
check its column really shows it, so a new or dropped field can't silently go missing.

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
