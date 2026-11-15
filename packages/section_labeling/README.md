# section_labeling

Labels every piece of a law with what the system should do with it, using one recorded AI call per piece, and proves nothing was skipped.

## The steps

1. **Cut** (code, no AI; `document_extraction/sections.py`): the law is cut at its own headings into pieces: sections, lettered subsections, one piece per defined term, editor's notes. Saved as `2_extracted_text/<document>.sections.jsonl`, re-made and compared on every change in CI.
2. **Label** (AI, this package): the piece's lines are numbered (L1, L2, ...) with page breaks shown. The answer lists the requirements first, as line numbers, then one label (`rule`, `flag`, `reference` or `not_for_checking`), a topic, a reason, and the exact words that justify it. The instructions are `regulations/document_extraction_guide/labeling_guide.md`, the same for every piece.
3. **Check** (code): code takes each requirement's exact words from its cited lines (one part per page; the words must occur once on their page and once in the piece) and checks the quote with the same matcher the inspector uses for rules. The label must agree with the requirements (any: rule or flag; none: reference or not_for_checking); a rule's or flag's sources are the requirement lines it found plus the quote; they justify the label, and the drafting step still reads the whole piece. A bad answer is sent back with the reason (at most 2 retries); after that the piece stays unlabeled.
4. **Record** (code): every call is saved in `3_section_labels/runs/<date>_<model>.jsonl`, with the settings, a fingerprint of the instructions and of the input, the raw answer, the tokens and the cost.
5. **Review** (people): `3_section_labels/<document>.review.md` (generated) lists the labels to look at first, in four sections: every piece labeled not_for_checking (never checked, so a rule wrongly put there could let a design pass that should fail); every piece labeled reference whose text uses requirement wording (found by plain code, whatever the AI said); every label with an open question for the architects; and every piece a rule or definition already cites. A reviewer records a doubt as an `open_questions` entry on the label.
6. **Approve** (architects; deferred for now, decided 2026-10-19): labels stay drafts in `3_section_labels/<document>.yaml`. When approval is switched on, an architect answers any open questions (`answers`) and approves each label, exactly as for rules. `python -m rule_format` checks them.
7. **Cover** (code): `6_coverage_report/<document>.md` lists every piece and its label, and proves every line of the law is in exactly one piece (or is page furniture).
8. **Audit each district** (code, `district_audit.py`): `6_coverage_report/residential_districts.md` puts every rule and flag piece against each residential district: in the district's rulebook (which rules), flagged, not applicable, parked (deliberately deferred: Ben's later list, or the brief that parked it), an open question, or MISSING (ranked). A not applicable, parked or flag decision quotes the law, and code checks only that the quote is the law's words, once, exactly where it says; each such cell is marked [R#] and listed with its quote for a person to check. A person's decisions are in `<jurisdiction>/residential_coverage.yaml`; code refuses any the files don't back: a rule named must exist and cite the piece (a source, a finding's source, or a definition of a measure it uses) or the decision must say why (`mapped`, shown as such); every rule that cites a piece must be named; a piece with several parts shows its worst part. It also lists every rule with where each of its measures comes from (model_measurement, the architect, or nothing) and the tests that check it on a model.
9. **Index the terms** (code, `term_index.py`): `4_term_definitions/term_index.yaml` lists, for every defined term (`definitions.yaml`) and every word that means the same (`regulations/document_extraction_guide/term_synonyms.yaml`), every piece that uses it, with the page and line of each use: whole words, any case, a plain plural, a phrase split across a line break. Like the index at the back of a book: "yard" lists §325-18B (eaves may project 2 ft into a yard), which the yard definition never mentions. A definition with no synonyms entry is an error, so a new term can't be skipped. The drafter reads it (related sections), the rules spreadsheet shows it, and research on an open question starts from it.

## Running it

```
pip install -e ".[labeling]"                        # the Anthropic SDK; only needed for real runs
python -m section_labeling estimate                 # cost first; works without a key (rough), exact with one
export ANTHROPIC_API_KEY=...                        # read from here only; never committed
export ANTHROPIC_WORKSPACE_ID=...                   # only if the key isn't tied to one workspace (the API says so)
python -m section_labeling label --limit 10         # shows the estimate for 10 pieces, sends nothing
python -m section_labeling label --limit 10 --yes   # labels them; then `cost` shows what it really cost
python -m section_labeling coverage                 # refresh the coverage report, the review list and the term index
python -m section_labeling coverage --check         # (CI) fail if any of them is out of date
python -m section_labeling audit                    # refresh the residential coverage audit (no AI)
python -m section_labeling audit --check            # (CI) fail if it is out of date or a decision isn't backed
```

The model, effort, token limit and budget are set in one place, `section_labeling/settings.yaml` (default: `claude-haiku-5-5`, effort `low`, budget $1.00).

**A hard spending cap.** A ledger in your home folder (`~/.config/gordium/section_labeling_ledger.json`, shared by every checkout of the repository) keeps the measured cost of every call (the API's token counts × prices), and is never taken as less than the repository's run records add up to. A run whose estimate is more than the budget left is refused. Before each call its worst case (every input token at the dearest input price, plus the full output limit) is reserved in the ledger, under a lock so runs at the same time see each other; a call that could cross the cap is never sent. After the call the reservation becomes the measured cost; a call that failed stays charged at its worst case (it may still have been billed). The SDK's own automatic retries are off, so every request passes this check. Spent and remaining are printed at the end. Prices are in `section_labeling/prices.yaml`, with where they came from; confirm them before a large run. The fixed instructions are cached, so every call after the first pays about a tenth for them.

**Not repeatable bit for bit.** Current models don't accept a temperature setting, so the same piece can get a different answer on another run. That's why every call is recorded, every label is checked by code, and, once approval is switched on (deferred for now), an architect's approval would freeze a label.

Labeling never runs in CI. Tests use a fake client (no key, no network, no cost).
