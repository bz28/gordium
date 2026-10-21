# Drafting rules

How to write a definition or a rule from a city's documents. They apply to every zone and every city, and to anyone drafting, AI or person. The inspector (`python -m rule_format`) enforces what code can check; the rest is checked in review (architect review is deferred for now, decided 2026-10-19).

## 1. Say only what the quotes say

**Definitions have no paraphrase:** a definition is the city's own whole sentences in `sources`. (Restating definitions kept dropping limiting words, so we stopped.)

**Rules have no paraphrase either:** a rule is its quotes (the city's words), its `check` (the formula) and its `examples`. Its `title` is a one-line label of at most 80 characters, e.g. "Minimum lot width (chart p.3)". Explanations that help a reader (arithmetic like 2% of a 1,000 sf facade = 20 sf) go in `notes`; they're never needed to decide a result.

- ✗ a formula or note that measures height to the **midpoint** of a pitched roof (the code says "average height", not midpoint)
- ✓ the height definition's open question about what "average height" means

## 2. Interpretations go to `open_questions`, never into a formula or note

When the law leaves something unsettled (a word it doesn't define, a measurement it doesn't explain, a case it doesn't mention), write the question for the architects in `open_questions`. A definition or rule with open questions can't be approved until they're answered. The answer is recorded in `answers` (question, answer, answered_by, answered_on), and the rule's `check` is updated to match. Both are part of what's approved, so they can't change afterwards without re-approval (approval is deferred for now; this applies once it is switched on).

## 3. Every number comes from a quote

Every number in a formula (`check`, `applies_when`, `review_when`: a length, a percent, an area) must be written in one of the rule's own sources: a quoted sentence, or a cited chart cell or its row label. The inspector checks this (0 needs no source; "2%" supports 0.02; number words count, "three" supports 3; a number that only labels or points, like the "(3)" of a list or "§325-16", doesn't count). A number we work out is written as the arithmetic, from cited inputs: `0.02 * 1000`, not 20. The worked examples prove it (20 passes, 21 fails). The drafting script is stricter, because code can check that a source holds a number but not what the number is about: it never types a chart number (each is a slot, filled from the district's own cell), and a number it types is trusted only from a sentence of the paragraph being drafted, a footnote marked on the slot's own cell, or that slot's own row label (its instructions give the details).

## 4. Quote the exact words, including footnote markers

Copy quotes from the extracted text (`2_extracted_text/`), not from memory or the PDF viewer. Quote whole sentences: a sentence cut in the middle can drop the words that limit it ("except as hereinafter specified", "that are united by a common interest"). Chart rows are quoted from the row label to the value. Footnotes appear as `[fn11]` and are part of the words. When a chart value has a footnote, quote the footnote's text too.

Each source gives `page`, `lines: [first, last]` and `quote`. The quote must be one unbroken passage (no `…`) that starts on the first line, ends on the last, and occurs only once on the page. When drafting by hand, a bare chart value repeats across the row, so quote the row label with it, or better, cite the one chart cell: `{file, page, cell: {section, row, column}}` (checked against the chart reader's cells, and the only way to pin the district's column). `python -m rule_format cite <place> <file> <page> "<quote>"` prints the lines. The drafting script (`packages/rule_drafting`) never quotes a chart row: its chart numbers are slots, filled by code from each district's cell, and its chart quotes are only the footnotes under a table (none at all when the section has no footnote: the cell is the source).

## 5. Say where each part of a rule comes from

When drafting by hand, a rule can combine a chart value with conditions from the law (a district's limit from the chart, and an exception to it in a section of the law). Cite both. The chart reader's cells cover only the chart part, so this keeps the comparison honest. The drafting script drafts one text at a time, so it drafts only that text's own requirements: the chart's limit from the chart section, and the exception from the section of the law that sets it, each citing its own sources.

## 6. Use the city's own scope words

If the law says "corner lot or through-block lot", don't shorten it to "corner lot". If it says "main building", don't write "building". Small scope changes change outcomes.

## 7. Prefer "needs review" to a confident guess

If a rule can't be decided from the measurements we have (an irregular lot whose side lot lines are unclear), add a `review_when` with the reason, so the checker says "needs review" instead of guessing.
