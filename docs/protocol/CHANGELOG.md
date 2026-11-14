# Protocol and site description changes

**Purpose:** each version of the worker protocol and the site description, and what changed in it.\
**For:** engineers writing or updating a design-tool add-in.\
**Kept current by:** every PR that changes the schema or the commands (a test fails until a line is added).

One line per version, newest first. Each site description version names its schema file's sha256: the test
`packages/design_checker/tests/test_site_json.py` fails when the schema file changes and this line doesn't, so a
change can't land without a version and a word here (the rules for minor and major versions are in
[site_description_v1.md](site_description_v1.md#versions)). Each protocol version names the sha256 of the schema
and the command table together (`protocol.table()`: every command, part, field and default), pinned the same way
by `packages/design_checker/tests/test_protocol.py` ([worker_protocol_v1.md](worker_protocol_v1.md#versions)).

- **2026-11-06 · protocol 1.0 · site description `gordium.site/1`** (schema sha256 `0aec44ae2f9e296c70565351c4a5191e7b28e3e7302c194ce8aa0322402702b7`): first version.
  Commands `hello`, `read_model`, `check_site` and `start_site`; the five older commands answer as before
  (`check` and `start` now go through the site description themselves). Problem code `tool_words` for a tool's own words.
  The session commands ([worker_protocol_v1.md](worker_protocol_v1.md#session-commands)): `facts.validate`,
  `facts.missing`, `facts.suggest`, `facts.drop_stale`, `facts.sources`, `facts.row`, `box.view`, `box.pick`,
  `lookup.choices`, `lookup.preview`, `lookup.reset` (edit plans), `streets.pick`, `streets.lines`,
  `streets.verdict`, `streets.words`, `session.freshness`, `session.undo`, `report.message`, `panel.rows`
  (command table sha256 `c5f2e4085c950f33566757a55cf943fc7069b889a66df536268c2c28443e715e`).
