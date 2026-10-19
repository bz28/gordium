# section_labeling

Labels every piece of a law with what the system should do with it, using one recorded AI call per piece, and proves nothing was skipped.

## The steps

1. **Cut** (code, no AI; `document_extraction/sections.py`): the law is cut at its own headings into pieces: sections, lettered subsections, one piece per defined term, editor's notes. Saved as `2_extracted_text/<document>.sections.jsonl`, re-made and compared on every change in CI.
2. **Label** (AI, this package): each piece gets one label (`rule`, `flag`, `reference` or `not_for_checking`), a topic, a reason, and the exact words that justify it. The instructions are `regulations/document_extraction_guide/labeling_guide.md`, the same for every piece.
3. **Check** (code): the quote must be the city's words, inside the piece, once on its page, using the same matcher the inspector uses for rules. A bad answer is sent back with the reason (at most 2 retries); after that the piece stays unlabeled.
4. **Record** (code): every call is saved in `3_section_labels/runs/<date>_<model>.jsonl`, with the settings, a fingerprint of the instructions and of the input, the raw answer, the tokens and the cost.
5. **Review** (people): `3_section_labels/<document>.review.md` (generated) lists the labels to look at first: every piece labeled not_for_checking (never checked, so a rule wrongly put there could let a design pass that should fail), and every piece a rule or definition already cites. A reviewer records a doubt as an `open_questions` entry on the label.
6. **Approve** (architects): labels are drafts in `3_section_labels/<document>.yaml` until an architect answers any open questions (`answers`) and approves them, exactly as for rules. `python -m rule_format` checks them.
7. **Cover** (code): `6_coverage_report/<document>.md` lists every piece and its label, and proves every line of the law is in exactly one piece (or is page furniture).

## Running it

```
pip install -e ".[labeling]"                        # the Anthropic SDK; only needed for real runs
python -m section_labeling estimate                 # cost first; works without a key (rough), exact with one
export ANTHROPIC_API_KEY=...                        # read from here only; never committed
python -m section_labeling label --limit 10         # shows the estimate for 10 pieces, sends nothing
python -m section_labeling label --limit 10 --yes   # labels them; then `cost` shows what it really cost
python -m section_labeling coverage                 # refresh the coverage report and the review list
```

The model, effort, token limit and budget are set in one place, `section_labeling/settings.yaml` (default: `claude-haiku-5-5`, effort `low`, budget $1.00).

**A hard spending cap.** A ledger in your home folder (`~/.config/gordium/section_labeling_ledger.json`, shared by every checkout of the repository) keeps the measured cost of every call (the API's token counts × prices), and is never taken as less than the repository's run records add up to. A run whose estimate is more than the budget left is refused. Before each call its worst case (every input token at the dearest input price, plus the full output limit) is reserved in the ledger, under a lock so runs at the same time see each other; a call that could cross the cap is never sent. After the call the reservation becomes the measured cost; a call that failed stays charged at its worst case (it may still have been billed). The SDK's own automatic retries are off, so every request passes this check. Spent and remaining are printed at the end. Prices are in `section_labeling/prices.yaml`, with where they came from; confirm them before a large run. The fixed instructions are cached, so every call after the first pays about a tenth for them.

**Not repeatable bit for bit.** Current models don't accept a temperature setting, so the same piece can get a different answer on another run. That's why every call is recorded, every label is checked by code, and only an architect's approval freezes a label.

Labeling never runs in CI. Tests use a fake client (no key, no network, no cost).
