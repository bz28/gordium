# Drafting rules

How to write a definition or a rule from a city's documents. They apply to every zone and every city, and to anyone drafting, AI or person. The inspector (`python -m rule_format`) enforces what code can check; the rest is checked in review (architect review is deferred for now, decided 2026-10-19).

## 1. Say only what the quotes say

**Definitions have no paraphrase:** a definition is the city's own whole sentences in `sources`. (Restating definitions kept dropping limiting words, so we stopped.)

**Rules have no paraphrase either:** a rule is its quotes (the city's words), its `check` (the formula) and its `examples`. Its `title` is a one-line label of at most 80 characters, e.g. "Rear yard minimum (chart p.3, note 16)". Explanations that help a reader (arithmetic like 35 ft + 10% = 38.5 ft) go in `notes`; they're never needed to decide a result.

- ✗ a formula or note that measures height to the **midpoint** of a pitched roof (the code says "average height", not midpoint)
- ✓ the height definition's open question about what "average height" means

## 2. Interpretations go to `open_questions`, never into a formula or note

When the law leaves something unsettled (a word it doesn't define, a measurement it doesn't explain, a case it doesn't mention), write the question for the architects in `open_questions`. A definition or rule with open questions can't be approved until they're answered. The answer is recorded in `answers` (question, answer, answered_by, answered_on), and the rule's `check` is updated to match. Both are part of what's approved, so they can't change afterwards without re-approval (approval is deferred for now; this applies once it is switched on).

## 3. Every number comes from a quote

Every number in a `check` formula (35 ft, 25%, 6,000 sf) must appear in a quoted source. Numbers we compute ourselves (like 38.5 ft = 35 ft + 10%) must show the arithmetic in `notes` and quote every input; the worked examples prove it (38.5 ft passes, 39 ft fails).

## 4. Quote the exact words, including footnote markers

Copy quotes from the extracted text (`2_extracted_text/`), not from memory or the PDF viewer. Quote whole sentences: a sentence cut in the middle can drop the words that limit it ("except as hereinafter specified", "that are united by a common interest"). Chart rows are quoted from the row label to the value. Footnotes appear as `[fn11]` and are part of the words. When a chart value has a footnote, quote the footnote's text too.

Each source gives `page`, `lines: [first, last]` and `quote`. The quote must be one unbroken passage (no `…`) that starts on the first line, ends on the last, and occurs only once on the page. A bare chart value like `35 ft` repeats across the row, so quote the row label with it. `python -m rule_format cite <place> <file> <page> "<quote>"` prints the lines.

## 5. Say where each part of a rule comes from

A rule can combine a chart value with conditions from the law (R-1b's height: 35 ft from the chart, the 10% bonus from §325-16C). Quote both. Later, the chart-reading code reproduces only the chart part, so this keeps the comparison honest.

## 6. Use the city's own scope words

If the law says "corner lot or through-block lot", don't shorten it to "corner lot". If it says "main building", don't write "building". Small scope changes change outcomes.

## 7. Prefer "needs review" to a confident guess

If a rule can't be decided from the measurements we have (an irregular lot whose side lot lines are unclear), add a `review_when` with the reason, so the checker says "needs review" instead of guessing.
