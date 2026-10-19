# 3_section_labels

What kind of text each piece of a law is, so nothing is skipped and every rule is found. One file per document (`chapter_325_zoning_2026-10.yaml`).

- The pieces come from code: the law cut at its own headings (`2_extracted_text/<document>.sections.jsonl`).
- Each piece gets one **label**: **rule** (code can check it), **flag** (an architect must judge it), **reference** (sets no requirement itself, but rules depend on it: definitions, how to measure, cross-references) or **not_for_checking** (procedures, administration, penalties). Plus a **topic**, a **reason**, and the exact words that justify the label (page, lines, quote), checked against the PDF like any rule's source.
- Labels are drafted by the labeling script (`packages/section_labeling`, one recorded AI call per piece; the calls are in `runs/`) and stay drafts until an architect approves them. Approval works exactly as for rules: a listed reviewer, not the drafter, frozen by a fingerprint. If the piece is re-cut or the PDF changes, the label must be redone.
- The instructions every label follows: `regulations/document_extraction_guide/labeling_guide.md`.
- `<document>.review.md` (generated, never hand-edit) lists the labels a person should check first, in four sections: every piece labeled not_for_checking (never checked, so a rule wrongly put there could let a design pass that should fail); every piece labeled reference whose text uses requirement wording (found by plain code, whatever the AI said); every label with an open question for the architects; and every piece a rule or definition already cites. A doubt goes in the label's `open_questions`; the architect's reply in `answers`; then approval, as for rules.

`python -m rule_format` checks these files. All 626 pieces of Chapter 325 are labeled (Haiku, 2026-10-19, $0.085); 70 labels were then corrected by an AI review, each with a `revised` record. All are drafts until architects approve.
