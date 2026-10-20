# project_report

Fills in a project's compliance report in the architects' own spreadsheet format
(`test_data/answer_keys/new_york/ithaca_city/Gordium_Single_Family_Simple_v1.xlsx`): the same two tabs,
**Inputs** and **Output**, the same headers in the same order, the same plain Arial style. Plain code, no AI.

```
python -m project_report <project.yaml>    # writes <project>_report.xlsx next to the project file
python -m project_report --check           # CI: every committed report matches a fresh build
```

Example: `test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/spreadsheet_design.yaml` →
`spreadsheet_design_report.xlsx` in the same folder.

## The project file

```yaml
title: New single-family home, 106 Ithaca Rd
jurisdiction: regulations/jurisdictions/new_york/ithaca_city
zone: R-1b                       # picks the rulebook
measurements:                    # names from packages/rule_format/rule_format/measures.yaml
  use:       {value: one_family_detached, from: "Output!C3 (Detached one-family)"}
  lot_depth: {value: 90, from: "Inputs!B4"}
  rear_yard: {value: 25, from: "Inputs!B4 - Inputs!B9 - Inputs!B7"}
```

Every measurement says where its value came from (`from`). An unknown field, an unknown measurement name, a
measurement without `from` text, a value that is not a number or text, or a zone with no rulebook stops the report with an error, so a typo can't
silently drop a value.

**Which rulebook:** `5_zoning_rules/<zone>.yaml` (hand-drafted) when it exists, else
`5_zoning_rules/drafted/<zone>.yaml` (AI-drafted). The one rule for this is `rulebook_for()` in
`rule_format.rulebook`; the answer-key test uses it too. Every Output row says which file it used.

## The tabs

**Inputs:** each measurement with its value (yellow, like the architects' typed-in cells), its unit and
meaning, and where it came from. Below that, **Table parameters**: for each rule that applies, the limit as
the table writes it (e.g. `rear_yard ≥ max(min(0.25 * lot_depth, 50), 20)`), with document, page and link.

**Output:** their seven columns, then ours.

| Column | What it holds |
|---|---|
| Requirement | the rule's title |
| Table limit | the limit worked out for this lot: the right-hand side of the rule's comparison, with this project's numbers |
| Proposed | the project's value |
| Units | ft, sf, stories, spaces… |
| Comparison | Within table limit / Outside table limit / Needs review / Not applicable |
| PDF page | the page of the rule's first source |
| Error | **PASS / FAIL / NEEDS REVIEW / NOT APPLICABLE** (their header, kept as is) |
| Rule id · Formula | which rule, and its formula exactly |
| Why it needs review | filled on every NEEDS REVIEW row, found in the same order the checker decides: can't tell whether the rule applies, a flag (a person decides), a review condition that holds, or a measurement missing or unusable (named, with its value) |
| City's exact words · Document · Link | the rule's first source, with a link that opens the document at that page |
| Rulebook | which rulebook file, who drafted it, its status (the Output title says the rules are drafts, checked by code: approval is deferred) |

Rules that apply, or whose applicability can't be decided, come first. Rules that don't apply follow under
their own heading, so nothing is silently dropped.

**The result comes only from `rule_format.outcome()`**, the same plain code the checker uses. The table limit and
proposed value are shown for people to read; they never decide the result. When a rule compares more than one
measure (side yards, the height bonus), each part is named; a formula of another shape shows "see formula".

Text cells are stored as text, so a value starting with `=` is shown, never run as an Excel formula (the cell
writer is shared with `rule_export`).

## How we know it is right

`tests/test_report.py`:
- the 106 Ithaca Rd report gives the architects' PASS/FAIL on all 11 of their rows;
- tab names and their headers match exactly, ours after;
- every result equals `outcome()`; every rule in the zone appears once;
- every row's page, document, quote and link are the rule's first source;
- the rear yard limit is worked out for this lot (≥ 22.5 ft);
- every NEEDS REVIEW row has a reason, and no other row does;
- the hand-drafted rulebook is preferred; bad project files are refused;
- no report from a jurisdiction, term file or rulebook that fails `python -m rule_format`'s per-file checks
  (the same functions, shared): a wrong quote, a district that isn't its file name, a uses list that fails its
  checks, an unreadable file or source list each give a plain refusal, never PASS;
- the same project gives the same workbook; the committed example matches a fresh build (also in CI).
