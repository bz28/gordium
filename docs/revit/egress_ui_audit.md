# Egress in the Revit pane: a hands-on audit (2026-11-26)

**Purpose:** what the Revit pane shows an architect for New York egress, ranked by how much it would confuse or mislead them, with a picture of each and where it is fixed.\
**For:** Ben; whoever builds the add-in's UI or the checker's egress words.\
**Kept current by:** the PR that fixes a finding marks it fixed here; a new audit adds a dated section.

What the pane shows for the four-unit apartment (Ithaca, R-3a, the 2025 Building Code governs) before and after its
questions are answered. Everything below comes from main's checker, not changed, and the pane's own code.

**How it was done.** `tools/pane_renders --audit` writes, for each check answer, every result's place in the list,
its cards and its detail page as text, and the pane's states as pictures. The answers are the trial request checked
three ways: as saved (nothing answered), with the building questions answered as an architect would for this building
(Group R-2 apartments, an NFPA 13R sprinkler system, none of the special cases), and with the lot questions answered
too. The counts are in [what_moves.json](../evidence/egress-ui-audit/what_moves.json).

| | Results | Egress results | Need review | Comply | Don't apply | Questions asked |
|---|---|---|---|---|---|---|
| Nothing answered | 316 | 268 | 276 | 31 | 1 | 25 |
| Building questions answered | 166 | 120 | 94 | 41 | 23 | 20 |
| Everything answered | 155 | 120 | 80 | 44 | 23 | 1 |

These counts are main's before #203 (door swing). Since #203, each door adds a swing row that needs review until its swing side is stated: as saved, 326 results, 286 needing review, 26 questions.

Setting the occupancy group alone decides 20 results and takes away 148 that are for other groups, so the questions
card's order (most results first, the occupancy group at the top) leads to the most decided results. No egress result
shows green when it shouldn't: each one that complies was measured, or meets the stricter of two limits whatever the
unknown fact turns out to be.

## Findings, worst first

| # | What the architect meets | Why it confuses or misleads | Fix |
|---|---|---|---|
| 1 | After every question is answered, the top says "80 results can't be decided until the questions below are answered" ([picture](../evidence/egress-ui-audit/1_headline_after_answers.png)) | Only 2 of the 80 wait on the one question left; the rest need a mark, a fix in the model or a check by hand. The architect answers it and still has 78. | **Fixed** (this audit's first PR): "80 results need review; 2 of them wait on the question below" ([picture](../evidence/egress-ui-audit/1_headline_after_answers_fixed.png)) |
| 2 | 20 Chapter 10 results (and the corridor ones) end "Check this by hand… Check again. Only a check changes a verdict." ([picture](../evidence/egress-ui-audit/2_hand_check_ends_check_again.png)) | A dead end: checking again never changes a result a person decides. The page already has "Mark as looked at", which is what the architect can do. | Pane (PR B) |
| 3 | "33 code questions for you to decide": 29 cards read "Check this by hand: a person decides it" ([picture](../evidence/egress-ui-audit/3_decide_cards_alike.png)) | They can't be told apart without opening each one. | Pane (PR C): a card whose words repeat is named by its result |
| 4 | After answering, What changed says "196 results changed" ([picture](../evidence/egress-ui-audit/4_what_changed_counts_gone.png)) | 161 of them left the check (148 rules for other occupancy groups, 13 the other answers made moot); they didn't change. | Pane (PR D) |
| 5 | "Work out the corridor fire rating hours (occupant load) by hand: Gordium has no field for it yet" | "Field" is an engineer's word, and there is nowhere to enter what was worked out, so the result can't move. | Checker (listed below) |
| 6 | "Three exits from 501-1,000 occupants" asks this four-unit apartment to set each room's function | An architect reads it as irrelevant; it could be decided from the floor area. | Checker (listed below) |
| 7 | A result a person decides stays Needs review for good | "Mark as looked at" records a look, not a verdict, so the check never shows these as done. | Product decision (listed below) |
| 8 | The questions card lists follow-up questions (Is the ADU detached? In an existing building?) before "Is there an ADU?" is answered ([picture](../evidence/egress-ui-audit/5_questions_card_before.png)) | Answering "No ADU" makes them moot, but they stay until the next check. | Low: needs the checker to say which question a follow-up hangs on |

## For the checker (not changed here)

- **5.** The corridor's fire rating hours and occupant load: a plain sentence without "field", and a way to give them
  (a mark or a project fact), so the results can move.
- **6.** One-exit and three-exit rules that wait on room functions where the floor area alone bounds the occupant load
  below the limit (four apartments can't reach 501).
- **7.** A way to record "checked by hand: complies" with who and when (principle 5), so a person's decision counts.
- **8.** Each follow-up question names the question it depends on, so the pane can hold it back until that one is
  answered.
- The door leaves' headline ("a pair with a mullion: 1 only at the narrower leaf's clear width") is dense; its wording
  is being worked on in `docs/leaves-mullioned-pair-wording`.
