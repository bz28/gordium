# Decisions log

Every significant decision, in plain language: **what** we decided, **why**, what else we **considered**, and **how we know it's right**. Newest decisions are added at the bottom, in the same pull request as the change. If a decision is replaced later, it's marked *superseded* and points to the new one, so the history stays readable.

---

## D1 · Rules are stored as files in git
*Planning, 2026-10* · Status: active

- **Decision:** every source document, definition and rule is a plain file in the git repository. A database, if ever needed, is built from these files.
- **Why:** git keeps a complete, permanent history of who changed what and when, and every change goes through a reviewed pull request. That's the audit trail zoning work needs.
- **Considered:** a database as the main store (harder to review changes; history must be built by hand).
- **How we know it's right:** every change so far is visible line by line in a PR with its review.

## D2 · Compile once, then freeze; the checker never uses AI
*Planning, 2026-10* · Status: active

- **Decision:** the city's documents are turned into rules once per version of the law. Architects approve them, and they're frozen. Checking a design is plain code reading those frozen rules: same design + same rulebook = same answer, every time.
- **Why:** results architects can trust and reproduce. AI may draft rules, but a rule's meaning is fixed by an architect's approval, not by an AI re-reading the law each time.
- **Considered:** asking AI to check each design directly against the law (answers could change run to run, and can't be audited).
- **How we know it's right:** the checker is ordinary code with tests; nothing in it calls an AI.

## D3 · Start with the City of Ithaca's residential districts; only official, fingerprinted sources
*PR 0* · Status: active

- **Decision:** the first city is the City of Ithaca (not the Town). Every source PDF comes from an official city site, is never edited, and is recorded in `sources.yaml` with its link, date and fingerprint (SHA-256).
- **Why:** one well-understood code first. Fingerprints prove a rule cites exactly the document we have.
- **How we know it's right:** the fingerprints were re-checked by downloading again from the city's links. The inspector re-checks them on every change.

## D4 · Rule format: plain English + a formula + an exact source quote + worked examples
*PR 1* · Status: active

- **Decision:** every rule has the same boxes: `says` (plain English), `check` (a yes/no formula), optional `applies_when` and `review_when`, `sources` (file, page, exact quote), `examples` (worked cases), and who drafted or approved it.
- **Why:** architects read `says`, code runs `check`, `sources` make it traceable, and `examples` prove the formula does what `says` claims.
- **Considered:** rules as free-form code (unreadable for architects, could hide logic); rules as plain text only (computers can't check them).
- **How we know it's right:** the inspector enforces every box; the tests break each box on purpose and confirm it's caught.

## D5 · Formulas use a small, fixed math language, not free code
*PR 1* · Status: active

- **Decision:** formulas are everyday math (`rear_yard >= max(min(0.25 * lot_depth, 50), 20)`), read by Python's own parser and then checked against a short whitelist: numbers, measurement names, `+ - * /`, comparisons, `and`/`or`/`not`, `min`/`max`, `in [list]`, `a if b else c`. Everything else is rejected.
- **Why:** readable by architects, impossible to hide anything in, predictable.
- **Considered:** a custom rule language (more to build and learn); JSON-based logic (hard for people to read); full Python (unsafe, unreviewable).
- **How we know it's right:** tests try 20+ kinds of forbidden formulas (running programs, reading files…) and all are rejected.

## D6 · Fixed list of measurements with fixed units
*PR 1* · Status: active

- **Decision:** rules may only use measurements listed in `measures.yaml` (lot area, height, yards…), each with one unit (feet, square feet, count, or text).
- **Why:** no unit mix-ups, and a typo like `rear_yrd` is caught instead of silently ignored.
- **How we know it's right:** the inspector rejects unknown names; tests confirm it.

## D7 · Results fail closed: anything doubtful is "needs review", never "pass"
*PR 1, review rounds 1–4* · Status: active

- **Decision:** a rule's result is decided in a fixed order (not applicable → architect must judge → reason for caution → pass/fail). A missing, broken (not a real number, infinite), negative, wrong-kind or unrecognized value gives **needs review**. The checker refuses to run unless it's given the city's list of use names, so no caller can forget a safeguard.
- **Why:** principle 4: a false "pass" could put an illegal building on paper; "needs review" only costs a second look.
- **How it evolved:** early versions only treated *missing* values as doubtful. Reviews found broken numbers, wrong kinds, and callers who could skip the use list could all produce a false pass. Each was closed at the root by requiring every value to be described and checked.
- **How we know it's right:** tests feed every kind of bad value through `and`/`or`/chains and confirm none can pass; each safeguard is "pinned" (undo it and a test fails).

## D8 · Quotes are matched as whole words and numbers ("tokens")
*PR 1, review round 7 redesign* · Status: active · *Supersedes letter-by-letter matching (rounds 1–6)*

- **Decision:** the page text and the quote are split into tokens with one rule: whole words, whole numbers (`2.5`, `1,500`, `3/2`, `.5`), footnote markers (`[fn11]`), single symbols. A quote matches only as a run of whole tokens.
- **Why:** the earlier design matched letter by letter, then guessed where words and numbers start and end. Over five review rounds it needed one special case after another ("5" in "25", in "2.5", in "1/2", in ".5", a quote ending in a period), and two of those fixes broke earlier ones. That's a symptom-by-symptom patch. Tokens remove the whole family of problems at once, for every city.
- **Considered:** keep patching boundary rules (kept leaking); fuzzy matching (could accept a wrong number, which defeats the purpose).
- **How we know it's right:** every edge case from rounds 1–6 is still a test and still passes, now handled by one rule. The parts of the design are pinned (undo one and tests fail).

## D9 · Approval: only listed architects, never the drafter, tied to the exact content and document versions
*PR 1* · Status: active

- **Decision:** `approved_by` must be on `regulations/reviewers.yaml` (architects only, empty for now) and can't be the drafter. Approval stores a fingerprint of the rule's content, its id, and the fingerprints of the documents it cites. Any edit, move to another zone, or new version of a cited PDF means it needs approving again.
- **Why:** principle 2: AI drafts, architects approve. An approval must cover exactly what was approved.
- **Known limit:** the record shows edits after approval but doesn't *prove* who approved. Until architects approve through their own accounts (GitHub approvals or the planned review app), approvals are trusted through PR review that Ben merges.
- **How we know it's right:** tests: AI approval rejected, self-approval rejected, edited/moved rules and replaced documents flagged.

## D10 · Every rule needs worked examples that pass and that fail
*PR 1, review round 2* · Status: active

- **Decision:** at least one example must pass and one must fail, and each must give the result it states.
- **Why:** an example that only says "needs review" proves nothing about the formula; a pass and a fail show the formula is the right way round and uses the right number.

## D11 · How we review: a repeating loop with independent reviewers
*PR 2* · Status: active

- **Decision:** each PR is reviewed in rounds. A fresh reviewer with no knowledge of how the code was written looks for problems, two "skeptics" try to disprove each one, and only findings both fail to disprove count. Every confirmed finding is fixed with a "pin" (a test that fails if the fix is undone), and rounds repeat until one finds nothing (cap 4, extended with Ben's OK). Each PR's review covers only its own changes. Copied from Ben's Veradic project and adapted.
- **Why:** fixes introduce new bugs; one review pass misses them. On PR 1 the rounds found 15, 10, 9, 4, 3, 2, 1 issues.
- **How we know it's right:** every round and its pins are recorded in the PR description.

## D12 · Ben approves every commit and merges every PR; PRs are stacked
*Process* · Status: partly superseded by D17b (below): commits no longer need approval

- **Decision:** before each commit, the AI stops and explains what, why, what's next, and why it's the right approach. Ben merges. Work is split into stacked PRs (each builds on the one below), each with its own eval, and building continues upward while lower PRs are in review.
- **Why:** Ben stays in control and understands every step; small PRs are easier to review and prove.

## D13 · Plain-language documents and PR descriptions
*Process* · Status: active

- **Decision:** PR descriptions follow a template written for someone who has never coded (words explained, one worked example, how we know it works). Overview documents: `how_gordium_is_built.md`, `how_rules_are_checked.md`, and this log.
- **Why:** the audience includes architects and shareholders.

## D14 · Gordium's own AI instructions take priority on this computer
*Process* · Status: active

- **Decision:** Ben's generic personal slash commands with the same names were moved to `~/.claude/commands-backup/`, because personal commands override a project's own.
- **Why:** otherwise Gordium's tailored `/review` loop and `/autopilot` would silently not run.

## D15 · Fix problems at the root, and surface process problems early
*Process, 2026-10-19* · Status: active

- **Decision:** no bandage fixes. When review findings keep appearing in the same area, stop and redesign (as in D8) instead of adding special cases. Problems with the process that affect accuracy or repeating it for other zones and cities are raised with Ben as soon as they're seen.
- **Why:** the rulebook must stay correct for every zone and every city, not just the cases we've seen.

## D16 · Large changes are reviewed before they're committed
*PR 2 (process), 2026-10-19* · Status: active

- **Decision:** a large or design-level change gets a review round (fresh reviewer + skeptics) on the uncommitted work *before* it's committed (`/review` with `uncommitted: true`). Small fixes from a round are committed first and re-checked by the next round. Nothing reaches `main` until a round comes back clean and Ben merges.
- **Why:** Ben asked whether we should review before committing. Reviewing every small fix before committing would slow the loop without adding safety (the next round re-checks it); reviewing big changes first means no large change enters a PR without an independent review.

## D17 · Rules get an `open_questions` box too
*PR 1, review round 8* · Status: active

- **Decision:** rules can list `open_questions`: interpretations the law leaves open (e.g. how R-1b's height bonus increases each yard). A rule with open questions can be drafted, but can't be approved until the architects' answers are recorded, so the checker (which only uses approved rules) never relies on it.
- **Why:** interpretations must go to the architects as questions, never into a rule's plain-English text (principle: flag, don't guess), and rules had nowhere to put them. The written drafting rules arrive with the definitions (PR 4).
- **Considered:** also putting the questions into the approval fingerprint. Not needed: approval is impossible while any question exists, so adding a question after approval is already caught, and a safeguard that no test can tell apart from its absence is dead code.

## D17b · Commits no longer need Ben's approval; merges do
*Process, 2026-10-19* · Status: active · *Replaces the per-commit stop in D12*

- **Decision:** the AI commits and pushes to PR branches without stopping to ask. Ben approves at merge time: nothing reaches `main` until he merges.
- **Why:** Ben's call. Per-commit stops slowed the work and filled the conversation, while the real safeguards (review loop before merge, review before commit for big changes, CI) are unchanged.
