# How Gordium keeps its rules trustworthy

For architects, shareholders and new engineers. No coding knowledge needed.

## The idea in one minute

Gordium makes **promises** to architects (the core principles in `CLAUDE.md`). For each promise, the software runs a **check** on every rule, so a rule that would break the promise is rejected before anyone can use it. For each check, there is a **test** that proves the check works.

```
Promise to architects   →   Check on every rule   →   Test that proves the check works
```

Like a building department: the code (promise) says exits must be marked; the plan examiner (check) rejects drawings without exit signs; a training exam (test) proves the examiner catches the missing signs.

The software that runs the checks is called the **inspector** (`python -m rule_format`). It runs automatically on every change to the project.

## What a rule looks like

Every rule is written the same way. Here is R-1b's rear yard, with what each line means:

| Line | Example | Meaning |
|---|---|---|
| `says` | Rear yard must be at least 25% of lot depth or 50 ft, whichever is less, but never under 20 ft. | The rule in plain English (what an architect reads, and approves once approval is switched on) |
| `check` | `rear_yard >= max(min(0.25 * lot_depth, 50), 20)` | The same rule as a yes/no question the computer can answer |
| `applies_when` | `use == "one_family_detached"` | Which buildings it applies to (optional) |
| `review_when` | lot depth unclear on an irregular lot | When the computer must hand it to an architect instead of deciding |
| `sources` | zoning charts, page 3, lines 42–43, "Rear (minimum, % of depth or feet, 25%/ …" (the exact row) | Exactly where in the city's documents it comes from, down to the line |
| `examples` | rear yard 25 ft, lot 90 ft deep → **pass** | Worked examples, like the ones in a code commentary |
| `status`, `approved_by`, `approved_on`, `approved_hash` | draft · (architect) · (date) · (fingerprint) | Who approved it, when, and a fingerprint of the rule as approved (so any later edit shows) |

## The promises and their checks

| Promise to architects | Why it matters | So the inspector rejects a rule that… | Example test |
|---|---|---|---|
| **Every rule shows where it came from** | You can always ask "says who?" and get the page and the words | has no source · cites a document we don't hold · cites a document that has changed since we recorded it · doesn't say exactly where on the page its quote is (page and line numbers) · quotes words that aren't exactly on those lines · quotes "5 feet" where the page says "25 feet" | A rule quoting "30%" where page 3 says "25%" → rejected |
| **Approval, when it's switched on, can't be faked or go stale** (approval is deferred for now, decided 2026-10-19: rules stay drafts and are used once every other check passes) | AI can draft, but only a licensed person approves | is marked approved by someone not on the architects list (`regulations/reviewers.yaml`) · is approved by the person who drafted it · still has open questions for the architects · has no approval date · was **changed or moved to another district after it was approved**, or **a document it cites was replaced by a new version** (its fingerprint no longer matches, so it needs approving again) | A rule "approved by claude" → rejected |
| **Checking never uses AI; same design = same answer** | Results are predictable and repeatable, like a calculator | uses anything other than plain math in its formula | A formula that tries to run a program → rejected |
| **Never a false pass** | A wrong "pass" could put an illegal building on paper; a "needs review" only costs a second look | has a formula that isn't a clear yes/no question · has worked examples that don't come out as stated · doesn't have at least one example that passes and one that fails (so the formula is really tried both ways) | "rear yard minus 20" (a number, not a yes/no) → rejected |
| **Rules are consistent** | Every rule reads the same way; a typo can't silently break one | uses a measurement, use or topic name that isn't on the official lists · has missing or unknown fields · repeats an id or a line | "rear_yrd" instead of "rear_yard" → rejected |

## How a design gets its result

For each rule, in this order:

1. Doesn't apply to this building → **not applicable**
2. Something only an architect can judge → **needs review**
3. A reason for caution (e.g. irregular lot) → **needs review**
4. Otherwise the yes/no question → **pass** or **fail**

At any step, if a measurement is missing or unusable (no value, not a real number, negative, text where a number belongs, a use name the city doesn't have), or the math can't be done (like dividing by zero) → **needs review**. Only a clean "yes" can ever become **pass**.

## How we know the checks themselves work

| Method | What it shows | Status |
|---|---|---|
| **Tests**: mostly "take a good rule, break one thing, confirm it is rejected", plus "confirm good rules pass" | The checks do their job | All passing; GitHub re-runs them on every change (counts are in each PR) |
| **Repeated independent review**: a fresh reviewer who didn't write the code looks for holes, two skeptics try to disprove each one, survivors get fixed, and it repeats until a round finds nothing | Catches what the author didn't think of, including problems the fixes themselves created | Recorded per round in the PR |
| **Breaking each fix on purpose** ("pins"): undo a fix and confirm a test notices | No fix is unguarded | Every fix pinned; recorded per review round in the PR |
| **Planted mistakes in real rules**: wrong numbers, wrong pages, invented quotes in copies of the real R-1b | How many real-world mistakes get caught | Planned with R-1b |
| **The architects' own mistakes** from their worked example | Real errors from practice are caught | Planned with R-1b |
| **Every escape becomes a check**: any bad rule found later gets a new check and test | The inspector improves over time | Ongoing |

## What the inspector can't do

It can tell whether a rule is **well-formed and traceable**, not whether it **reads the law correctly**. That is confirmed separately:

1. **The quote is real and in the right place**: checked automatically against the exact lines of the document's extracted text. Once the text-extraction step is merged, the extracted text is re-made from the PDF on every change and must match exactly, so it can't be edited by hand. For chart values, the right *column* (district) is confirmed by step 2 and by architects, until the chart reader cites table cells.
2. **Two independent versions agree**: R-1b written by hand from reading must match R-1b produced by code from the chart tables.
3. **An architect approves it** (deferred for now: until approval is switched on, people read and check the rules through the generated rules spreadsheet, with links to the city's exact words).
4. **Real city decisions** (planned): run the rules on real Ithaca projects the city has already ruled on (permits, zoning board decisions). A mismatch means a rule or an exception is wrong.

## What approval records can and can't prove (today)

The approval lines say *who* approved and *when*, and the fingerprint shows whether the rule changed afterwards. They do **not** prove the named architect really clicked "approve": anyone who can edit the files could type those lines and compute the fingerprint. Until approvals come through the architects' own accounts (GitHub approvals or the planned review app), approvals are trusted only because every change is reviewed in a pull request that Ben merges.

## Choices for the architects to confirm

These are engineering judgment calls, not facts from the code:

- A source cites the exact lines its quote sits on, and the quote must match those lines as whole words and numbers ("tokens"): "5 feet" never matches inside "2.5 feet" or "25 feet", "R-1" never inside "R-1b". One quote is one unbroken passage.
- Lengths are always in feet, areas in square feet.
- The list of measurements rules may use (`packages/rule_format/rule_format/measures.yaml`).
- The list of topics (`regulations/document_extraction_guide/vocabulary.yaml`).
- The order results are decided in (above).
