# 7_published_rulebooks

The certificates the checker reads: each rulebook's checks, worked out once and frozen ("compile, then freeze", CLAUDE.md principle 1; [the decision](../../../../../docs/decisions/2026-11-23_laws_validation_speed.md)).

- **What one is:** `<district>.published.json` (here one per zoning district, `R-1b.published.json`; a state law's folder has `general.published.json`). It holds the result of every rule check on that rulebook (its sources, definitions, uses), and the sha256 fingerprint of every file it was worked out from: the rulebook, each input file, the code that checked it, the folders it listed, the repo file names its rules mention.
- **How it is made:** `python -m rule_format publish` (in a fresh process; refused if the rulebook has any problem, or if anything outside the repo was read). `python -m rule_format publish --check` proves a fresh compile gives the same bytes and names what changed.
- **How the checker uses it:** at every check it works out the fingerprints again (well under a second). If they match, it uses the frozen result and parses the rules from the very bytes it fingerprinted. If a zoning district's certificate is missing or any input changed, the check is refused (no report, so nothing passes). If a state law's is, that law gives no rows and shows one needs-review item. There is no live check to fall back on.

**While rules are draft (now; approval is deferred, decided 2026-10-19):** the certificates are generated files, not committed (`.gitignore`). CI makes them before the tests, a pytest session makes any that are missing or out of date, the Revit add-in's install script makes them, the checker's worker (`python -m design_checker serve`, which the Rhino plugin and the Revit add-in start) makes any missing or out-of-date ones before its first answer, and the goldens and permit-sheet commands make any that are missing (with `--write`, out-of-date ones too).

**Once approval exists:** a published version is committed here once and never changed. When the city amends its code, a new version is published alongside the old one.
