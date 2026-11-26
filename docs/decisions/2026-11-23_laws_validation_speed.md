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

## The planned fix: compile, then freeze (design agreed 2026-11-26)

Principle 1: documents are turned into rules once per code version, and approved rules are frozen as data. A check should read laws that were validated once, not validate them again each time. Measured 2026-11-26 (this machine, quiet, the Ithaca box check): `egress.laws` takes about 2.0 s on a process's first call and about 0.84 s on each call after (a long-running worker's case), of a check of about 1.27 s: about two thirds of every check. Nearly all of it is validation (each book's sources read and checked, then its rules); reading a rulebook is 4 ms.

**What is frozen.** For each state book a place inherits, a certificate: the result of `egress.compile_law` (the book's problems, which must be none; its sources; the measures its rules may name), with the sha256 of every input the validation read and of the code that validated it. The rules themselves stay in `5_` (one home), pinned by the rulebook's sha256 in the certificate.

**Why this is not the cache that was taken out.** The cache trusted its own key at run time with nothing recomputing behind it. Here CI recompiles every law from scratch and compares it with the certificate, so an input the fingerprint misses still fails CI. The inputs are not listed by hand: the compile records every file it opened and every module it imported, plus every file of the law folder (a file that appears is caught). A compile that reads anything outside the repo, such as the code cache, is refused.

**Built (PR 2, 2026-11-26):** `python -m rule_format publish` and `publish --check` (`rule_format/published.py`). Building it found one more kind of input: the answer can turn on which file *names* exist, not only on what files say. The plain-words check lets a rule's notes name a repo file (`rulebook._in_repo` walks the names of the repo's top folders), so Maine's rules pass only while a file they mention exists anywhere in the repo. So the certificate also records every folder the compile listed (the same audit hook's `os.scandir` and `os.listdir`) with a fingerprint of its names; names tools make as they run (Python's caches, the add-in's `bin`/`obj`, hidden files, the certificates) are left out. A copy of the repo with the same names and Maine's folder gives byte-identical certificates; a copy missing the names gave Maine a problem, which is how this was found. Review round 1 found two more: the compile also asks whether a file *exists* (a copy of a book kept outside the repo in `1_source_documents` is a problem), which no audit event shows, so every folder of the law folder and of the shared files is listed whatever the compile lists; and the `7_published_rulebooks` folders publish makes changed another law's listings, so they and the certificates are left out of every listing and of the repo walk alike (`rulebook.generated_name`). A rule's `report` must now be under `docs/research/`, a folder every certificate lists.

**How a check reads it.** Each check recomputes the certificate's fingerprints (about 50 ms) and, when they match, takes its result and loads the rules from `5_`. A missing, unreadable or stale certificate gives the law a problem that says what changed and to run `python -m rule_format publish`, and no rules: every row of that law needs review, never a pass. There is no live fallback and no in-process state.

**Two phases.**

1. *While rules are draft (now; approval is deferred, principle 2).* Certificates are generated files, not committed (gitignored), built by `python -m rule_format publish`: by CI before the tests (so every check in the suite is tested through the frozen path), by a session-wide pytest fixture for local runs, by the Revit add-in's install script (so the worker reads a certificate of exactly the installed files), and by the goldens and permit-sheet commands when one is missing. Not committing them keeps every rule PR free of certificate merge conflicts. The run-time fingerprint check is the same as in phase 2, so a stale certificate still refuses.
2. *Once approval exists.* A published version is committed to `7_published_rulebooks/` once and never changed, as its README says; a new code version is published beside the old one.

**The PRs.** (1) `egress.laws` split into `compile_law` (the validation, unchanged) and the reading around it, and the code-cache read below fixed; (2) the `publish` command, its certificate format and its check; (3) the checker reads the certificate, refusing a stale or missing one; (4) zoning's rulebook on the same certificate (the check validates R-1b again in `project_report`, about 0.2 s); (5) the System Map and CLAUDE.md.

**Built (PR 3, 2026-11-26):** `egress.laws` reads each law's validation with `published.frozen`: the certificate's fingerprints are worked out again (every input and code file hashed, every listed folder listed, the law folder globbed), and the rules are parsed from the very rulebook bytes that were hashed. A missing, stale, unknown or unusable certificate gives the law one needs-review item ("the frozen copy can't be used", with what changed and `python -m rule_format publish`) and no rules; there is no live validation to fall back on. Measured on this laptop (busy, the box check with the ranch interior): `egress.laws` after a process's first call 1.66 s before, 0.10 s after; one check 2.6 s before, 0.66 s after.

## Open finding (fixed 2026-11-26, PR 1 above)

`Context.for_jurisdiction(..., use_cache=False)` is meant to read no book from the code cache outside the repo, "so a design's check gives the same answer on every machine". But after the `use_cache` branch it still loaded a kept-outside book's extracted text from the cache whenever that text existed there (on this laptop both New York books' text was read on every check). The answer was the same with and without the cache (checked 2026-11-26 for Ithaca and Maine), but nothing made it so. Now that load is skipped with `use_cache=False`, and `test_a_designs_check_reads_no_book_text_from_the_code_cache_even_where_the_cache_has_it` pins it on any machine by building a code cache that has the text.
