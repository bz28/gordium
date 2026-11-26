# The worker protocol, version 1 (`1.3`)

**Purpose:** how a design tool (Rhino now, Revit later) talks to Gordium's checker: the message format, every command, and how versions change.\
**For:** engineers writing a design-tool add-in; reviewers checking that the worker answers exactly what the tool's own copy of the logic would.\
**Kept current by:** every PR that adds or changes a command (a test fails until the version and [CHANGELOG.md](CHANGELOG.md) say so; another keeps the command reference below equal to the code).

The checker runs as its own process, the **worker** (`python -m design_checker serve`). A design tool sends it one
JSON request per line and reads one JSON answer per line. Rhino's plugin keeps calling the same logic directly
inside Rhino (`host_core/`, through `rhino_logic.py`), as it always has; the protocol is how a second tool gets
exactly the same answers without its own copy of that logic. What a tool sends about the model itself, the site
description, has its own page: [site_description_v1.md](site_description_v1.md).

## Messages

A request is one JSON object on one line: `{"id": 7, "cmd": "box.view", "protocol": "1.3", ...its fields}`
(a tool written for `1.0` may keep sending `"1.0"`: the same major version, answered the same).

- `id`: any value; the answer carries it back.
- `cmd`: the command.
- `protocol`: required for every command on this page; `"1.x"` is understood, any other major version refused.
- `progress` (optional, `check`, `start`, `check_site` and `start_site`): progress lines before the answer, `{"id": 7, "step": "Measuring the building…"}`, one as each stage starts and the same again, marked `"again": true`, every 15 s while it runs (a host that shows or records stages skips the repeats); the answer is always the request's last line. The Revit add-in asks for them on `check_site` and stops the worker when it says nothing for 60 s, or when the whole check passes its ceiling (ten times the silence, at least 10 minutes); "Try again with more time" doubles both.
- `want` (optional, session commands only): the answers asked for ([below](#session-commands)).

The answer: `{"id": 7, "ok": true, "result": {...}, "about": {...}}`, or `{"id": 7, "ok": false, "error":
"words"}` (and `"trace"` for a crash). `about` is what `hello` returns, on every answer, so any answer can be traced
to the exact code and rules that gave it.

**The older commands** `check`, `start`, `facts`, `options` and `sample_site` are the only ones answered without
`protocol`, and their answers are exactly what they were before the protocol, to the last character (the golden
answers and the recorded session's replay prove it).

## `hello` and the model commands

- `hello`: `{protocol, site_schema, worker_fingerprint, rulebook}`, the protocol, the site description version,
  a fingerprint of the worker's code and data, and one of each place's rules.
- `read_model`, `check_site`, `start_site`: [site_description_v1.md](site_description_v1.md#how-the-worker-uses-it).

## Session commands

These are the start box, the panel and the live check's decisions, the plain logic the Rhino plugin calls in
`host_core/`. Each command is a fixed list of parts, and each part is **one named host_core function** (or one of
its constants) with the fields it reads. The worker serves only the commands below
(`packages/design_checker/design_checker/protocol.py`, `COMMANDS`); there is no "call any function by name".

**Stateless.** The worker keeps nothing between requests. The tool sends what it holds (`facts`: the lot facts;
`saved_ui`: the start box's choices; `state`: what the box shows) and gets the new values back to store in its own
document, so a restarted worker loses nothing.

**How a command is answered.**

1. A field the command doesn't read is refused, and so is a number that isn't finite. Nothing is quietly ignored.
2. `want` (optional: a list of answer names, such as `["rows", "can_draw"]`) asks for those parts only; one that
   lacks a field it **needs** is refused. Without `want`, each part runs when every field it needs is in the
   request, with any of the optional ones that are; then one part's error fails the whole request, so a tool that
   needs one answer names it. A request that runs no part is refused, and so is one with a field no running part
   reads (a field sent without the others it is used with).
3. Each part gets its own copy of the fields.
4. Each part's answer is under its own name in `result`. A part that refuses its input (a typed answer that isn't
   one) gives its words under `result.refused`, keyed by the part's first answer name; the other parts still answer.
5. An answer that JSON can't carry exactly (a key that isn't text, NaN, an object) is an error, never changed.

**JSON's own forms.** A pair or more returned in Python (`(facts, saved_ui)`) is answered as separate named fields.
A tuple inside a value (a start-box row's `actions`, a picked point) comes as a JSON array, and a set the
Rhino plugin passes (the model's lot and building ids, `facts.drop_stale`) is sent as an array. Defaults below are
shown as Python writes them (`None` is JSON `null`, `()` an empty array). One value has its own form: a pending
lookup's undo list (`saved_ui._pending.undo`) marks a key that had no value with an in-process marker, which goes
as `{"$missing": true}` in both directions (read so only there: the old and new value of each undo step); the tool stores it as it came and sends it back unchanged. Any other
object with a `"$missing"` key is refused. **Key order counts:** some words follow the order of an object's keys
(a lookup's doubtful facts are said in the order the lookup listed them), so a tool keeps objects in the order it
received them.

**Questions to the architect.** `streets.pick` may need to ask whether an unclear stretch of the outline is still
the street. The worker can't ask, so the tool sends the answers it has, in order (`answers`: `true`, `false` or
`null`), and the answer lists every question asked after those ran out (`unasked`, answered `null` meanwhile:
kept as street, and the command line's words say so). A tool with an architect at hand asks each one, adds the
answer and sends the request again; the answers are always asked in the same order.

**Which objects are left out** (`objects.left_out`, from 1.1). The tool picks the objects that could be a
building and aren't measured (Rhino: by layer and geometry type; Revit: by category) and sends what it saw of each:
its `id`, its 3D `box` (`null` when it has none), its plan `points`, and for a placed block or linked model its
`definition` (left out entirely for anything else: `null` means a block whose definition is missing, so no box), with every definition it holds, at any depth, once in `definitions` (each with its `status`, the
tool's word for whether what it holds is the design, and its `parts`). The worker decides the rest, the same for
every tool: which are on the lot (`left_out`), which may be part of the house (`touching`), and which have no box
that covers all of them (`no_box`: a linked file missing, unreadable or out of date at any depth, an empty block,
no box given), which always count as left out and touching. Each answer is one entry per object sent, in order,
with a code saying why (`host_core/left_out.py`, `NO_BOX` and `WHY`). Lengths are in the model's units, with
`feet_per_unit` saying how long one is; the field-by-field form is at the top of `host_core/left_out.py`.

<!-- the command reference: written by protocol.reference() (python -m design_checker.protocol --write-doc); a test keeps it equal -->

### `facts.validate`

A typed answer read as the fact's value: `value` (null when blank), `problem` (the words beside a field whose text isn't an answer, else null), `feet` (a typed length: null when it can't be read).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `value` | `facts.parse_answer` | `kind`, `text` | `key` (None) |
| `problem` | `facts.answer_problem` | `kind`, `text` | `key` (None) |
| `feet` | `facts.parse_feet` | `feet_text` |  |

### `facts.missing`

The required lot facts not yet given (`missing`), and the doubts about what is drawn the architect hasn't ticked I checked this for (`unsettled`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `missing` | `facts.missing` | `facts` |  |
| `unsettled` | `facts.unsettled` | `saved_ui` | `checked` (None) |

### `facts.suggest`

The start box's prefilled facts from the model's lots and buildings (`suggested`, in model units); the facts to confirm, saved with suggestions only for what is missing (`facts`); and the saved facts without a district the model only guessed (`no_guess`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `suggested` | `facts.suggested_facts` | `jurisdiction`, `zones`, `lots`, `buildings` |  |
| `facts` | `facts.with_suggestions` | `saved`, `suggested` |  |
| `no_guess` | `start_box.no_guessed_district` | `saved`, `suggested` |  |

### `facts.drop_stale`

The saved facts without a lot or building that is no longer in the model (`facts`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `facts` | `facts.drop_stale` | `facts`, `lot_ids`, `building_ids` |  |

### `facts.sources`

Where each fact came from: every fact the box set (`sources`), the saved sources Draw keeps (`kept`), after a row's dialog (`row_sources`) and after the box's typed answers (`typed_sources`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `sources` | `facts.fact_sources` | `state`, `today`, `confirmed` |  |
| `kept` | `facts.sources_kept` | `saved`, `facts` |  |
| `row_sources` | `facts.row_sources` | `sources`, `needs`, `facts`, `day` |  |
| `typed_sources` | `facts.typed_sources` | `sources`, `track`, `facts`, `day` |  |

### `facts.row`

A row's dialog: its questions (`fields`), the facts after OK (`facts`; refused with words when an entry isn't an answer) and what the dialog says at OK (`problem`, null when it may close).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `fields` | `facts.row_fields` | `needs`, `facts` |  |
| `facts` | `facts.row_answers_applied` | `facts`, `needs`, `answers` |  |
| `problem` | `facts.row_problem` | `facts`, `needs`, `answers` |  |

### `box.view`

The start box as it shows: its rows (`rows`), whether Draw is on (`can_draw`), why not (`draw_reason`) and the reason line under Draw (`box_reason`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `rows` | `start_box.box_rows` | `state` | `flat` (None) |
| `can_draw` | `start_box.can_draw` | `state` |  |
| `draw_reason` | `start_box.draw_reason` | `state` |  |
| `box_reason` | `start_box.box_reason` | `state` |  |

### `box.pick`

After one of the box's picks: the facts and the box's choices (`facts`, `saved_ui`), the facts after the lot is (re)picked (`lot_facts`) and the ticks the box keeps (`ticks`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `facts`, `saved_ui` | `facts.pick_effect` | `what`, `outcome`, `facts`, `saved_ui` |  |
| `lot_facts` | `facts.after_lot_pick` | `facts`, `picked_lot` |  |
| `ticks` | `start_box.ticks_after_pick` | `what`, `ticks` | `answer` (None), `moved` (True) |

### `lookup.choices`

After a lookup's answer, decided as an edit plan: (`facts`, `saved_ui`, `guide`, `plan`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `facts`, `saved_ui`, `guide`, `plan` | `edits.lookup_edits` | `answer`, `facts`, `saved_ui`, `ground_points` | `zones` (()) |

### `lookup.preview`

After a lookup's answer, shown only (nothing in the model changes): (`facts`, `saved_ui`, `ring`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `facts`, `saved_ui`, `ring` | `start_box.preview_lookup` | `answer`, `facts`, `saved_ui` | `zones` (()) |

### `lookup.reset`

At Draw, the pending answer drawn for good, as an edit plan: (`facts`, `saved_ui`, `redraw_house`, `guide`, `plan`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `facts`, `saved_ui`, `redraw_house`, `guide`, `plan` | `edits.reset_edits` | `facts`, `saved_ui`, `choice`, `massing`, `buildings`, `ground_points` | `zones` (()) |

### `streets.pick`

A click on a lot line as the street side: the street lines and their street names (`lines`, `ids`) with what the command line says (`said`) and any question left to ask (`unasked`); whether the click is refused (`click_refused`); a corner lot's runs after one more click (`runs`, `run_said`, `run_unasked`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `lines`, `ids`, `said`, `unasked` | `streets.pick_street` | `old_lines`, `old_ids`, `picked`, `name` | `tolerance` (0.5), `outline` (None), `answers` (answers to its questions, in order) |
| `click_refused` | `streets.refused_click` | `outline`, `picked` | `tolerance` (0.5) |
| `runs`, `run_said`, `run_unasked` | `streets.add_street_pick` | `runs`, `outline`, `picked` | `names` (None), `tolerance` (0.5), `run_answers` (answers to its questions, in order) |

### `streets.lines`

The street lines from the runs kept (`lines`, `ids`), after a corner lot's clicks (`after_picks`), and each outline piece's known street (`names`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `lines`, `ids` | `streets.street_lines_of` | `outline`, `runs` | `names` (None), `clicks` (None), `labels` (None) |
| `after_picks` | `streets.street_lines_after_picks` | `lines`, `picks`, `corner` |  |
| `names` | `streets.outline_names` | `outline`, `lines`, `ids` | `tolerance` (0.5) |

### `streets.verdict`

Whether street lines are one street, two, or unsure, and their total swing (`verdict`, `swing`): the measuring's own.

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `verdict`, `swing` | `streets.street_verdict` | `lines` | `ids` (None) |

### `streets.words`

What the command line says a click kept (`words`), the street pick's prompt (`prompt`), and a corner lot's words so far (`so_far`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `words` | `streets.street_words` | `label`, `lines` | `ids` (False) |
| `prompt` | `streets.street_pick_prompt` | `corner`, `picked` |  |
| `so_far` | `streets.so_far` | `words` |  |

### `session.freshness`

Whether to check again after an edit (`recheck`), whether the result shown is out of date (`stale`), whether the model counts as changed after a start box closes (`changed`), and whether a check still shows the model (`still`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `recheck` | `freshness.should_recheck` | `dirty_at`, `now`, `running`, `box_open`, `wait` | `last_at` (None), `auto` (True) |
| `stale` | `freshness.result_stale` | `dirty_at`, `shown_at`, `now`, `after`, `rechecking` |  |
| `changed` | `freshness.changed_after_box` | `box_before`, `box_now`, `drawn` | `failed` (False) |
| `still` | `freshness.checked_while_still` | `begun_at`, `dirty_at` |  |

### `session.undo`

The undo steps' names (`words`), whether an undo event means check again (`recheck`), and when the model last changed after an Undo or Redo (`dirty_at`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `words` | `freshness.UNDO_WORDS` (a constant) | nothing: always given | |
| `recheck` | `freshness.after_undo_redo` | `is_end_undo`, `is_end_redo` |  |
| `dirty_at` | `freshness.dirty_after_undo` | `dirty_at`, `now` |  |

### `report.message`

What the panel says after a report was asked for (`message`), of a report whose model changed meanwhile (`outdated`), and when its check was cancelled (`cancelled`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `message` | `report.report_message` | `path`, `written` | `error` (None), `opened` (True), `open_error` (None), `stale` (False) |
| `outdated` | `report.outdated_report_message` | `path`, `report_error`, `had_report` |  |
| `cancelled` | `report.report_cancelled` | `path`, `changed` |  |

### `panel.rows`

The panel's words: its header (`header`), a row's status words (`status`), name (`name`) and list cells (`cell_name`, `proposed`), the colour a status shades (`highlight`), a detail's parts (`detail`) and a cell's text (`cell`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `header` | `panel_words.panel_header` | `head` |  |
| `status` | `panel_words.status_words` | `item` |  |
| `name` | `panel_words.row_name` | `item` |  |
| `cell_name`, `proposed` | `panel_words.list_cells` | `item` |  |
| `highlight` | `panel_words.highlight` | `status` |  |
| `detail` | `panel_words.detail_parts` | `det` |  |
| `cell` | `panel_words.cell_text` | `cell_text` |  |

### `objects.left_out`

Of the objects a host sends that could be a building and aren't measured (host_core/left_out.py says what each is): whether each is left out of the check, on the lot or with no box to tell (`left_out`), whether it may be part of the house (`touching`; null when it has no box, which counts as touching), and why it has no box that covers all of it (`no_box`).

| Answer | host_core | Needs | May also send |
|---|---|---|---|
| `left_out` | `left_out.left_out_decisions` | `lot`, `objects` | `definitions` (None), `feet_per_unit` (1.0) |
| `touching` | `left_out.touching_decisions` | `objects`, `buildings` | `definitions` (None), `feet_per_unit` (1.0) |
| `no_box` | `left_out.no_box_reasons` | `objects` | `definitions` (None) |

<!-- end of the command reference -->

## Edit plans

`lookup.choices` and `lookup.reset` change the model, so they answer with a **plan** of edits instead of making
them. The tool carries the plan out in its own transaction (Rhino: `BoxSession`; Revit: a TransactionGroup), in
order, and stops at a step it doesn't know (never skips it):

| Step | What the tool does |
|---|---|
| `{"op": "hold", "id"}` | Holds that object out of the model until the box closes: deleted at Draw, put back on Cancel |
| `{"op": "add_lot", "ring", "name", "ref"}` | Draws the lot outline `ring` (points in feet) named `name`; `ref` (`"$lot"`) stands for its id |
| `{"op": "add_spot", "point", "ref"}` | Places a spot grade; `ref` (`"$spot1"`…) stands for its id |
| `{"op": "own", "refs"}` | Marks those new objects as made by the box (so Cancel takes them away) |

Then it swaps each `$ref` in `facts` and `saved_ui` for the real id it made (`host_core.edits.carry_out` and
`with_ids` are the reference). A `$ref` used before it is made, or made twice, is an error.

## The lookup and the neighbourhood map

The address lookup and the neighbourhood map are not worker commands: each runs as its own short-lived process,
so a lookup given up on (the 45 s limit, Cancel) can never leave the worker out of step.

- `python -m design_checker.lookup_box "<address>"` prints `{"step": ...}` lines, then one JSON line: the
  lookup's result, where the lot lands in the model (`frame`) and what may be written into the model (`writes`).
  That last line is what `lookup.preview` and `lookup.choices` take as `answer`.
- `python -m design_checker.context_box --origin X Y --rotation R --shift SX SY [--parcel ID]` prints one JSON line:
  `objects` (what may be written into the model) and `guides` (what may only be shown).

## Versions

The same rule as the site description ([site_description_v1.md](site_description_v1.md#versions)):

- **Minor** (`1.1`): new commands, new answer fields, new optional request fields whose absence means exactly the
  old behaviour.
  A new optional site field is minor too, even when it can change a verdict, provided every older worker refuses
  it as unknown (site_json's strict field check) and never drops it, and its absence means exactly the old
  behaviour (1.3's `left_out[].slab`).
- **Major** (`2.0`): anything else: a rename, a removal, a change of meaning or units, a new required field.
- Each side refuses a different major version.

A test hashes the site description's schema file together with the command table (`protocol.table()`: every
command, part, field and default) and looks for that hash in [CHANGELOG.md](CHANGELOG.md), so the commands can't
change without a version and a changelog line.

## How we know the worker answers what Rhino would

`packages/design_checker/tests/test_protocol.py` replays the headless session,
`test_data/sessions/headless_calls/calls.jsonl`: host_core calls the plugin's own logic made while the tests drove
the start box, the lookup, the street picks, the row dialog, the freshness and undo rules and the panel's words
(recorded by `host_core.worker_client.CallRecorder`, `python -m design_checker.call_session --record`). For every
recorded call it checks that the function, called directly, still gives the recorded answer, and that the
worker's JSON answer to the same call, sent as a request line through `serve`, is that same answer.
