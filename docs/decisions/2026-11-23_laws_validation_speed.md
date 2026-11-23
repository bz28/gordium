# Why each check validates its laws again, and how that will stop (2026-11-23)

**Purpose:** why the per-process cache of validated laws was taken out of the New York code-decision branch, what each check costs without it, and the fix planned instead (frozen, already-validated published rulebooks).\
**For:** the engineer who builds the published-rulebook follow-up; Ben (the speed numbers and the open finding).\
**Kept current by:** the engineer who changes how `design_checker/egress.py` loads a place's laws, in that PR.

## What happened

Inheriting New York's second book (the 2025 Building Code, [which NY code](2026-11-22_which_ny_code.md)) made every check read and validate two rulebooks instead of one. The branch first kept the validated laws per process. Three review rounds (8, 9 and 10) found four ways that cache could answer from stale laws, on a path that decides pass or fail:

- **Round 8, P1:** the cache key listed its readers by hand and missed the cheap helpers (`_not_checked_yet`, `_sections`, `_scope_settings`, `_title`), so a test's patched result leaked into later tests.
- **Round 8, P2:** the key's file list was kept by hand and missed `regulations/reviewers.yaml` and the extraction guide's `vocabulary.yaml`, so editing either left a long-running worker validating stale.
- **Round 9:** recording the files the validation read missed a file appearing where Python 3.13+ on Windows checks existence without `os.stat`, kept an edit saved during the validation as fresh, and kept a passing read error.
- **Round 10:** the before-and-after snapshot of the repository missed the code cache outside the repo (below), still kept errors caught inside the validators, and its tests changed timestamps in the shared regulations tree under parallel CI.

So the cache is gone: `egress.laws` works out every law fresh on every call, as on main.

## What it costs (measured 2026-11-23, this machine, the box-house check on R-1b)

| | One check | `egress.laws` |
|---|---|---|
| main (the Residential Code only) | 0.69 s | 0.37 s |
| this branch, no cache | 0.99 s | 0.67 s |

The extra 0.30 s a check is the Building Code book's validation. A possible non-caching speed-up, not made in this branch: validate only the books a check runs (a house the Residential Code governs never reads the Building Code's rules). `check` already runs only the books that govern the building, and the permit sheets build their laws from the check's own sections, so the only other caller of `egress.laws` is the Odyssey eval tool (`apps/revit_addin/tools/evals/make_odyssey_answer.py`, which reads Maine). It still changes what `egress.laws` returns, so it needs its own change and review.

## The planned fix: compile, then freeze

Principle 1: documents are turned into rules once per code version, and approved rules are frozen as data. A check should read laws that were validated once, not validate them again each time. The follow-up publishes each state book's validated laws into its `7_published_rulebooks/` with the fingerprints of everything the validation read (the sources, the extracted text, the shared registries), and the checker loads the frozen, already-validated laws and checks only that their fingerprints still match. One validation per published version, the same answer on every machine, and no in-process cache to go stale.

## Open finding (pre-existing, for that follow-up)

`Context.for_jurisdiction(..., use_cache=False)` is meant to read no book from the code cache outside the repo, "so a design's check gives the same answer on every machine". But after the `use_cache` branch it still loads a kept-outside book's extracted text from the cache whenever that text exists there (`rule_format/rulebook.py`, the `if extracted.exists() and name not in ctx.file_problems:` load after the source checks, about line 415). A design's check can therefore differ between a machine with the code cache and one without it. This was on main before this branch. The published-rulebook fix removes the question, since the checker would no longer validate sources at check time.
