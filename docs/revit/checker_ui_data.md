# The checker's data for the rebuilt results pane (changes C1 to C9)

**Purpose:** every field the checker adds to its answer for the results pane Ben approved on 2026-11-23 (the UI polish design, changes C1 to C9), what each means, where it comes from and how we know it changes no result.\
**For:** whoever builds the pane (Revit add-in), reviewers of the checker.\
**Kept current by:** any PR that adds, renames or changes one of these fields (`packages/design_checker/design_checker/ui_data.py` and `contents.py`).

The design: [UI polish proposal](https://claude.ai/artifact/LJhsC5ve1TnowK54ENja67) (its `changes.md`, "Checker changes these need", C1 to C9). The pane being rebuilt reads these fields; the add-in on `main` doesn't know them and reads exactly what it read before.

## The rules these fields keep

- **New fields only.** Every field below is added beside the existing ones (`causes`, `code`, `detail`, `name`, `required` …), which keep their meaning. The add-in on `main` ignores what it doesn't know.
- **No verdict, status or figure changes.** These fields are words and data about a row, worked out from what the answer already says (its causes, its reason, its rule's sources, the law's contents). None is read back by the checker. Proof: every golden answer was made again and compared leaf by leaf with the one before; the only differences are the new fields and words (the plain measure names of C4). The diff is in the PR that adds them.
- **Never a guess.** A field that can't be worked out is left out (or a part of it is `null`), never filled in. A row in review always has its `asks`: if they can't be worked out, each of its causes is one ask a person decides.

## On each item (`result.view.items[]`)

### `asks` (C1, C2, C3, C5): what a row in review asks of the architect

Only on a row in review (`status: "needs_review"`). One entry per thing it asks, in order (the first is the one to do first):

| Field | Meaning |
|---|---|
| `kind` | `mark` (state a fact or set a mark), `fix_model` (change the model, as `why` says), `survey` (the lot needs a survey), `measure` (Gordium doesn't read or measure this yet: work it out by hand), `decide` (a person decides: a flag rule, a reading to confirm, the law's own review condition), `open_question` (the law reads more than one way and the readings disagree) |
| `key` | Rows with the same key ask the same thing (one card for them all). `field:<field>` for a fact or mark |
| `headline` | What to do, in a few words ("Set the occupancy group", "Is the lot on two streets? (Corner lot, §325-19C)", "“LS New 6"” isn't a closed solid") |
| `why` | The checker's own words for it, always whole: a cause's words (today's `causes[].words`), one part's words of the row's reason, or one whole open question. The pane shows them behind "Why?" |
| `elements` | The element ids it names: on a zoning row, the row's own `objects` (as its cause has them), narrowed only where a better set is known (the walls that aren't closed solids); on an egress row, its cause's (the rooms with no route, the part the row is about). Never fewer than the row's cause names |
| `field` | On a `mark`: the description field that answers it, so the host names its own mark. A field starting `facts.` or `building.` is a project question (Revit: Project Information): `building.occupancy_groups` (Gordium: Occupancy groups), `building.sprinkler_system`, `facts.corner_lot`, `facts.dwelling_units` … Others name a mark on an element: `doors[].exit`, `openings[].escape`, `rooms[].sleeping`, `stairs` |
| `fields`, `measure`, `rooms`, `questions` | As on the cause it came from (`causes[]`, panel_data.py) |
| `depends_on` | Only on a follow-up question: `{field, moot_if?}`. `field` is the question it hangs on ("Is the ADU detached?" on "Is there an ADU?": `facts.accessory_dwelling_unit`), the same fact the setup waits on before asking it (`host_core/facts.py` `ROW_ONLY_FACTS`). `moot_if` lists that question's answers that make this one moot (`false` for "Is there an ADU?"). The Revit pane (`ProjectQuestions.Of`) holds the follow-up back until its parent is answered, hides it when the answer is in `moot_if` or when its parent is itself held back or hidden, and shows it right after its parent otherwise; the results waiting on a follow-up not shown stay in review, on its parent's question ("In an existing building?" hangs on "Is the ADU detached?", which hangs on "Is there an ADU?") |

How each is found:

- **C1.** A building measure the BCNYS rules read is answered by the fact it is worked out from (`code_scope.DERIVED`, the one table `building_measures` uses): `occupancy_group_i4` and `other_occupancy_present` by `building.occupancy_groups`, `sprinklered_903_3_1_1` and `_2` by `building.sprinkler_system`. Two measures from one fact are one ask. (Today's `causes[].field` still says `facts.occupancy_group_i4`: unchanged, so the add-in on `main` reads what it did.)
- **C2.** A zoning row's reason is kept as data beside its words: `stops` (below), one part per reason the measuring gave (`model_measurement.stops.Said`: each stop's key and blanks travel with its words, through every "; "-join and every rewording, end to end) or per reason the row gives itself. The asks are read from those codes, never from the words. Each fact the row waits on (`needs`) is its own ask; a stop that asks for a fact is that fact's ask (the place's measuring table `ASK`, and the site's own questions: corner lot, survey, flat ground); `not_surveyed` and the tax map's lines are a `survey`; the stops that leave the law's reading open, and the rows whose readings disagree, are `open_question`, one per question the row depends on; a pick is a `mark`; the scope reason ("Complies for the buildings measured …") is one `fix_model` with the row's objects, never a decision; the measuring's stops that are no fault of the model go to a person (`measure`: a reading Gordium has no measuring code for yet, sloped ground, a curved surface; `decide`: the city's files missing a finding); any other stop is the model's to fix. A looked-up fact in doubt (`looked_up`) is a `mark` to confirm or change it. On an egress row, which code governs (`code_scope`) is a `mark` for each fact its ask names (`code_scope.ask_facts`, as data: `building.separate_means_of_egress` …); a code choice to check by hand stays a `decide`. A row's hint and its stop asking for the same pick (the main building, the ADU's building) are one ask. A part kept as plain words (no code) is a person's to `decide`, its words whole. An egress row's causes are already one per clause; each becomes one ask.
- **C3.** `headline` is short; the old words stay as `why`.
- **C5.** A closed-solid stop (`open_solid`, its blank the object's name) names, in `elements`, every building object of that name that isn't a closed solid (the place's own measuring, `_open_ids`), so Show selects them; where none is found, the row's objects.

### `stops`: a zoning row's reason as data

On a zoning row in review: `[{code, params, words, sep?}]`, one per part of its reason, in order; `sep` is the words before a part (none on the first), so the parts joined in order (`sep` + `words`) are the row's reason exactly. `code` is the measuring's stop (`model_measurement/stops.py`'s keys: `corner_unknown`, `open_solid`, `not_surveyed`, `readings_differ` …, `params` its blanks), or the row's own reason by what it is: `depends` (`params.questions`: the open questions it turns on), `tax_map`, `readings`, `scope`, `named`, `reading_applied`, `height_bonus`, `looked_up` (`params.fact`), `use_detail` ("Answer when you plan the interior", the part that says when: it asks nothing itself), `flag`, `review_when`, `review`, `facts_conflict`, `unsettled`; `words` for words no part was kept for. `asks` is made from these.

### `in_code` (C6): where the row's rule is in its document

On every row of a rule, zoning included: `{document, file, chapter, chapter_title, section, section_title, piece, piece_title}`.

- `chapter`: the chapter of an ICC book ("10", "MEANS OF EGRESS"), or the article of the zoning chapter ("II", "Zoning Districts").
- `section`: the section as the book's contents list it ("1006", "325-8"), with its title.
- `piece`: the part the rule's first quote is in ("1006.2.1", "Table 1006.2.1", "325-8A"), with its title. A row quoting the District Regulations Chart is §325-8's (the chart "is hereby made a part of this chapter", §325-8A, p.24).
- Not `code`: the egress rows' `code` (`{section, quote}`) is kept as it is, because the add-in on `main` shows `code.section` as a row's citation, and a zoning row's would then lose its detailed one.

### `rule_name` (C8)

The rule's name without its part and without the law and section in it: "Two exits over 10 occupants or a 75-ft common path, I-4", not "Level 1 › APARTMENT SOUTH L1 (1) · Two exits … (BCNYS 1006.2.1)" (`name`, unchanged). A zoning row's is its name. Room names are what the host sends (`part.name`, `element`), never changed by the checker.

### `limit_words` (C9)

On a zoning row whose limit isn't worked out yet (`required: "—"`): "Limit depends on dwelling units", naming the facts or measures the limit reads that have no value yet.

## On the view: `contents` (C7)

`result.view.contents`: one entry per document of the laws in the answer (the zoning chapter first, then each inherited law's book):

```
{key, document, file, chapters: [{number, kind, title, book_page, coverage, counts,
   sections: [{number, title, book_page, coverage, whole, counts, pieces: [{id, title, coverage, rules}]}]}]}
```

- Every chapter (or article) and section of the document, from its contents list, `2_extracted_text/<doc>.contents.jsonl`: generated by `python -m document_extraction contents` from the book's own contents pages (the ICC books, read from the PDF in the code cache), or from the zoning chapter's own article headings and its sections file. Never typed by hand.
- `coverage`: `rules` (rules check it), `flag` (only flag rules raise it, for a person), `not_checked_yet` (labeled rule or flag, with no rules a check uses yet), `not_for_checking` (brought in, nothing in it to check: a definition, a reference) or `not_brought_in` (not extracted: Gordium hasn't read it). A section's is the most telling of its pieces'; `whole: false` where only some of the section was brought in (the rest isn't); `counts` says how many of each.
- Each piece is placed in its section by one rule shared with the extraction's own check (`rule_format.labels.contents_section`: "1006.2.1" and "Table 1006.2.1" in 1006, an appendix's "BF101.2" in BF101, a definition in its section, "325-8A" in 325-8), so every brought-in piece is in a section of the list (test_ui_data.py checks it for each book).
- From the generated lists only: an ICC book's `6_coverage_report/<doc>.rules.yaml` (the pieces with rules), the zoning chapter's labels (`3_section_labels/`) and the pieces the district's rules cite.
- The pane draws its "By code" tree from it: a chapter or section with no rows is shown greyed as not checked yet by Gordium, never hidden; its status comes from the rows (`in_code`), never from `coverage`, so a chapter never looks like a pass while anything in it needs review.

## How we know

`packages/design_checker/tests/test_ui_data.py` pins each change and the class of rules the asks keep, over every golden answer and the apartment's (every row in review has asks; each part of its reason has an ask of the kind its code calls for; no ask's why is a piece of words; every element a row's cause names is in some ask), (each test fails when its change is reverted), runs the four-unit apartment's real Revit request (`test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json`) end to end, and checks that no row in review is without its asks; `packages/document_extraction/tests/test_contents.py` checks each contents list is current and complete.
