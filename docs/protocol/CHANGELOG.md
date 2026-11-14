# Protocol and site description changes

**Purpose:** each version of the worker protocol and the site description, and what changed in it.\
**For:** engineers writing or updating a design-tool add-in.\
**Kept current by:** every PR that changes the schema or the commands (a test fails until a line is added).

One line per version, newest first. Each site description version names its schema file's sha256: the test
`packages/design_checker/tests/test_site_json.py` fails when the schema file changes and this line doesn't, so a
change can't land without a version and a word here (the rules for minor and major versions are in
[site_description_v1.md](site_description_v1.md#versions)).

- **2026-11-06 · protocol 1.0 · site description `gordium.site/1`** (schema sha256 `0aec44ae2f9e296c70565351c4a5191e7b28e3e7302c194ce8aa0322402702b7`): first version.
  Commands `hello`, `read_model`, `check_site` and `start_site`; the five older commands answer as before
  (`check` and `start` now go through the site description themselves). Problem code `tool_words` for a tool's own words.
