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

- **2026-11-20 · protocol 1.3 · site description `gordium.site/1`** (schema sha256 `fb5a1adbbbf567ab89de716537ed9fc207867d7cccc4f5e9a78765add1d8bf82`):
  a left-out object may say it is a slab on the ground outside the building (`slab`: `unmarked`, `patio` or
  `parking`) and give its `name`, both optional
  ([site_description_v1.md](site_description_v1.md#how-the-worker-uses-it)): an unmarked one makes lot coverage and
  every required yard need review, naming it; a patio, terrace or walk is not in lot coverage but makes the yards
  need review; a parking area or driveway changes nothing (§325-3B BUILDING AREA, §325-18A). A minor version
  under the amended rule ([versions](site_description_v1.md#versions)): absent, every answer is exactly as
  before, and a 1.2 worker refuses a description that has it (an unknown field), never drops it, so no tool can
  get a pass from a worker that didn't read it. `check_site` refuses extras naming
  `site_slabs` (the description's own, handed to the view)
  (command table sha256 `7f569908834b515e8022b28f54ec5ffca3314a67afe67fd5afaf286a535537b9`).
- **2026-11-19 · protocol 1.2 · site description `gordium.site/1`** (unchanged): `check_site` takes an optional
  `interior`, the house's inside as an interior description (`gordium.interior/1`), and checks the place's inherited
  laws (New York's egress, for Ithaca) on it, as the command line's `--interior` does; without it they wait, as
  before ([site_description_v1.md](site_description_v1.md#how-the-worker-uses-it); the Revit add-in's reading of
  an interior: [revit_interior_reading_design.md](../revit/revit_interior_reading_design.md)). A minor version: a
  request without `interior` is answered exactly as before; the session commands are unchanged
  (command table sha256 `77acae03c601945bd7834d572afaeb40e8b4251ab37862b3570f74175c40ddc5`).
- **2026-11-12 · protocol 1.1 · site description `gordium.site/1`** (unchanged): the session command
  `objects.left_out` ([worker_protocol_v1.md](worker_protocol_v1.md#session-commands)): which objects a check
  leaves out, which may be touching the house, and which have no box that covers all of them, decided in
  `host_core/left_out.py` for every tool (the Rhino plugin calls the same functions in its own Python). A minor
  version: no other command changed, and a request naming `1.0` is answered as before, but for one thing:
  `check_site` (for a request naming any version) now reads `extras.left_out_advice` ({left-out object id: the tool's words for what the architect can do, such as a
  linked file to reload}, said on the left-out row; words only, the answer is the same) and refuses it when it
  isn't that, or names an id not in the description's `left_out`
  ([site_description_v1.md](site_description_v1.md#how-the-worker-uses-it))
  (command table sha256 `77acae03c601945bd7834d572afaeb40e8b4251ab37862b3570f74175c40ddc5`).
- **2026-11-06 · protocol 1.0 · site description `gordium.site/1`** (schema sha256 `0aec44ae2f9e296c70565351c4a5191e7b28e3e7302c194ce8aa0322402702b7`): first version.
  Commands `hello`, `read_model`, `check_site` and `start_site`; the five older commands answer as before
  (`check` and `start` now go through the site description themselves). Problem code `tool_words` for a tool's own words.
  The session commands ([worker_protocol_v1.md](worker_protocol_v1.md#session-commands)): `facts.validate`,
  `facts.missing`, `facts.suggest`, `facts.drop_stale`, `facts.sources`, `facts.row`, `box.view`, `box.pick`,
  `lookup.choices`, `lookup.preview`, `lookup.reset` (edit plans), `streets.pick`, `streets.lines`,
  `streets.verdict`, `streets.words`, `session.freshness`, `session.undo`, `report.message`, `panel.rows`
  (command table sha256 `c5f2e4085c950f33566757a55cf943fc7069b889a66df536268c2c28443e715e`).
