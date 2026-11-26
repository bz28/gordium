# 7_published_rulebooks

The certificates the checker reads: each rulebook's checks, worked out once and frozen ("compile, then freeze", CLAUDE.md principle 1; [the decision](../../../../../docs/decisions/2026-11-23_laws_validation_speed.md)).

- **What one is:** `<district>.published.json` (here one per zoning district, `R-1b.published.json`; a state law's folder has `general.published.json`). It holds the result of every rule check on that rulebook (its sources, definitions, uses), and the sha256 fingerprint of every file it was worked out from: the rulebook, each input file, the code that checked it, the folders it listed, the repo file names its rules mention.
- **How it is made:** `python -m rule_format publish` (in a fresh process; refused if the rulebook has any problem, or if anything outside the repo was read). `python -m rule_format publish --check` proves a fresh compile gives the same bytes and names what changed.
- **How the checker uses it:** at every check it works out the fingerprints again (about 0.1 s). If they match, it uses the frozen result and parses the rules from the very bytes it fingerprinted. If the certificate is missing or any input changed, that rulebook gives no rows: everything in it needs review, never a pass. There is no live check to fall back on.

**While rules are draft (now; approval is deferred, decided 2026-10-19):** the certificates are generated files, not committed (`.gitignore`). CI makes them before the tests, a pytest session makes any that are missing or out of date, the Revit add-in's install script makes them, and so do the goldens and permit-sheet commands.

**Once approval exists:** a published version is committed here once and never changed. When the city amends its code, a new version is published alongside the old one.
