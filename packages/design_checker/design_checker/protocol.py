"""The worker's protocol version and what it says about itself (`hello`), for any design tool that talks to it.

A request to a new-style command (`hello`, `read_model`) names the protocol it speaks, {"protocol": "1.1", ...}: a
different major version is refused, since the two sides would read the same words differently. The five older
commands (check, start, facts, options, sample_site) are answered with or without it, exactly as before. Every
new-style answer carries `about()`: the protocol, the site description version, and fingerprints of the worker's
code (with the data it loads) and of each place's files a check reads, worked out again for every answer (about
30 ms), so any answer can be traced to exactly what gave it, even after a rule is edited while the worker runs.
"""

import hashlib
from pathlib import Path

from rule_format.place import places
from rule_format.published import place_files, shared_files
from rule_format.rulebook import REPO

from .site_json import SCHEMA

PROTOCOL = "1.3"
LEGACY = ("check", "start", "facts", "options", "sample_site")


def _sha(files, root: Path) -> str:
    """sha256 over files, each by its path under `root` and its bytes, in path order."""
    h = hashlib.sha256()
    for f in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        h.update(f.relative_to(root).as_posix().encode("utf-8") + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def _kept(path: Path) -> bool:
    """A file (its path under packages/) that is part of what the worker runs: not a cache, a test, or a hidden or packaging file."""
    return not any(p in ("__pycache__", "tests") or p.startswith(".") or p.endswith(".egg-info") for p in path.parts) \
        and path.suffix not in (".pyc", ".pyo")


def code_files() -> list[Path]:
    """Every file of every package (its code and the data it loads, such as rule_format/measures.yaml), tests and
    caches left out: a check reaches into most of them (project_report decides each row), so all are counted. And
    the shared files every check reads too: under regulations/ outside any place's folder (the rule topics,
    document_extraction_guide/vocabulary.yaml, and who may approve, reviewers.yaml: rule_format.rulebook), and the
    research reports under docs/research/ that definitions and rules cite (each cited heading must be there)."""
    packages = REPO / "packages"
    return [f for f in packages.rglob("*") if f.is_file() and _kept(f.relative_to(packages))] + shared_files(REPO)


def worker_fingerprint() -> str:
    """sha256 over the checker's code and the data it loads, shared rule files included (code_files), read now."""
    return _sha(code_files(), REPO)


def rulebook_fingerprints() -> dict:
    """{place: sha256 over the files of its folder a check can read (place_files)}, read now: the rules are read
    again at every check, so a rule edited while the worker runs shows here at once. A place that inherits a state's
    law (Ithaca: New York's house code, design_checker/egress.py) has that folder's files counted too: its own
    folder's sha256, then each inherited folder's, by name, hashed together."""
    out = {}
    for p in places():
        own = _sha(place_files(p.folder), p.folder)
        if p.inherits:
            h = hashlib.sha256(own.encode("utf-8"))
            for folder in p.inherits:
                h.update(b"\0" + f"{folder.parent.name}/{folder.name}".encode("utf-8") + b"\0"
                         + _sha(place_files(folder), folder).encode("utf-8"))
            own = h.hexdigest()
        out[p.key] = own
    return out


def about() -> dict:
    return {"protocol": PROTOCOL, "site_schema": SCHEMA, "worker_fingerprint": worker_fingerprint(),
            "rulebook": rulebook_fingerprints()}


def speaks(request: dict) -> None:
    """Refuse (ValueError) a new-style request that doesn't name protocol 1.x."""
    said = request.get("protocol")
    if not isinstance(said, str) or said.split(".")[0] != PROTOCOL.split(".")[0]:
        raise ValueError(f"protocol {said!r} not spoken: this worker speaks {PROTOCOL} (send \"protocol\": "
                         f"\"{PROTOCOL}\"; a different major version is refused)")


# ---- the session commands (protocol 1.0; objects.left_out from 1.1): host_core functions, by a fixed table ----
#
# Each command is a few PARTS, and each part is ONE named host_core function (or one of its constants) with the
# request fields it reads: never "call any function by name". The table below is the whole list; anything not in it
# is refused. Commands are stateless: the host sends what it holds (facts, saved_ui: the box's choices) and gets the
# new ones back, to keep in its own document. docs/protocol/worker_protocol_v1.md lists every command and field.
#
# How a command is answered (run):
#   - a field the command doesn't read is refused (never quietly ignored: a newer host's field that changes a
#     verdict must not be dropped unseen), and so is a number that isn't finite;
#   - `want` (a list of answer names) asks for those parts only, each refused if a field it needs is missing; without
#     it, each part runs when every field it requires (its function's arguments without a default) is in the request,
#     with the optional ones that are; a constant part is always given; a request that runs no part is refused,
#     and so is one with a field no running part reads (sent with too little to use it: never quietly dropped);
#   - each part gets its own copy of the fields, so one part can never see another's changes;
#   - a part's answer goes under its output name (a pair or more, as the function returns them, under one name
#     each); a part that refuses (ValueError: a typed answer that isn't one) gives its words under "refused";
#   - an answer the protocol can't carry as it is (a key that isn't text, NaN, an object) is an error, never changed;
#     the one exception, lookup.MISSING (no value, in a pending preview's undo list), goes as {"$missing": true},
#     both ways.

import copy as _copy
import inspect as _inspect
import json as _json

from .host_core import edits as _edits, facts as _facts, freshness as _freshness, lookup as _lookup
from .host_core import panel_words as _panel_words, report as _report, start_box as _start_box, streets as _streets
from .host_core import left_out as _left_out
from .host_core.worker_client import NotPlain, plain, unplain

ENVELOPE = ("id", "cmd", "protocol", "progress", "want")       # a request's own fields, never a command's


class Part:
    """One host_core function (`fn`) in a command: its answer under `out` (a tuple of names spreads a returned pair or
    more), each request field read as one of its arguments (`fields`: argument -> field name, when they differ).
    `said`: an argument the function adds its words to (a list given empty), answered under that name. `ask`:
    (argument, field, out): a question the function may ask the architect, answered from the request's list of
    answers in order (true, false or null: not answered); each question asked once that list is used up is answered
    null (as with no one to ask) and listed under `out`, so the host can ask the architect and send the answer.
    `value`: a constant of host_core instead of a function (always given)."""

    def __init__(self, out, fn=None, fields=None, said=None, ask=None, constant=None):
        self.out, self.fn, self.said, self.ask = out, fn, said, ask
        self.constant = constant                     # (module, name): a constant, always given
        self.params, self.required = {}, []
        if fn is not None:
            renamed = dict(fields or {})
            skip = {said, ask[0] if ask else None}
            for name, p in _inspect.signature(fn).parameters.items():
                if name in skip:
                    continue
                field = renamed.pop(name, name)
                self.params[field] = name
                if p.default is p.empty:
                    self.required.append(field)
            assert not renamed, (fn.__name__, renamed)
        self.fields = set(self.params) | ({ask[1]} if ask else set())

    @property
    def name(self):
        if self.constant:
            return self.constant[0].__name__.split(".")[-1] + "." + self.constant[1]
        return self.fn.__module__.split(".")[-1] + "." + self.fn.__name__

    @property
    def outs(self):
        return (self.out if isinstance(self.out, tuple) else (self.out,)) + \
            ((self.said,) if self.said else ()) + ((self.ask[2],) if self.ask else ())

    def describe(self):
        """The part as the protocol's pin hashes it: its name, outputs and every field with its default."""
        out = {"part": self.name, "out": list(self.outs)}
        if self.fn is not None:
            sig = _inspect.signature(self.fn).parameters
            out["fields"] = {f: ({"default": repr(sig[p].default)} if sig[p].default is not sig[p].empty else
                                 {"required": True}) for f, p in sorted(self.params.items())}
            if self.ask:
                out["fields"][self.ask[1]] = {"answers_for": self.ask[0]}
        return out

    def runs(self, fields):
        return self.constant is not None or all(f in fields for f in self.required)

    def answer(self, fields, into, refused):
        if self.constant is not None:
            into[self.out] = _copy.deepcopy(getattr(*self.constant))
            return
        kwargs = {p: _copy.deepcopy(fields[f], {id(_lookup.MISSING): _lookup.MISSING})   # (MISSING: the very one,
                  for f, p in self.params.items() if f in fields}                                 # read with `is`)
        if self.said:
            kwargs[self.said] = []
        unasked = []
        if self.ask:
            given = fields.get(self.ask[1], [])
            # identity, never ==: 0 and 1 are not No and Yes (round 1: a 0 meant as No kept the stretch as street)
            if type(given) is not list or not all(a is True or a is False or a is None for a in given):
                raise ValueError("%s: a list, each answer true, false or null" % self.ask[1])
            answers = list(given)

            def ask(*question):
                if answers:
                    return answers.pop(0)
                unasked.append(list(question))
                return None
            kwargs[self.ask[0]] = ask
        try:
            value = self.fn(**kwargs)
        except ValueError as e:
            refused[self.outs[0]] = str(e)
            return
        if isinstance(self.out, tuple):
            if not isinstance(value, tuple) or len(value) != len(self.out):
                raise TypeError("%s gave %r, not %d values" % (self.name, type(value).__name__, len(self.out)))
            into.update(zip(self.out, value))
        else:
            into[self.out] = value
        if self.said:
            into[self.said] = kwargs[self.said]
        if self.ask:
            into[self.ask[2]] = unasked


class Command:
    def __init__(self, doc, *parts):
        self.doc, self.parts = doc, parts
        self.fields = set().union(*(p.fields for p in parts))
        outs = [o for p in parts for o in p.outs]
        assert len(outs) == len(set(outs)), outs          # every output its own name
        assert "refused" not in outs, outs                 # (run's own: the parts that refused, round 1)


COMMANDS = {
    # ---- facts: what the architect states about the lot ----
    "facts.validate": Command(
        "A typed answer read as the fact's value: `value` (null when blank), `problem` (the words beside a field "
        "whose text isn't an answer, else null), `feet` (a typed length: null when it can't be read).",
        Part("value", _facts.parse_answer), Part("problem", _facts.answer_problem),
        Part("feet", _facts.parse_feet, fields={"text": "feet_text"})),
    "facts.missing": Command(
        "The required lot facts not yet given (`missing`), and the doubts about what is drawn the architect hasn't "
        "ticked I checked this for (`unsettled`).",
        Part("missing", _facts.missing), Part("unsettled", _facts.unsettled)),
    "facts.suggest": Command(
        "The start box's prefilled facts from the model's lots and buildings (`suggested`, in model units); the "
        "facts to confirm, saved with suggestions only for what is missing (`facts`); and the saved facts without a "
        "district the model only guessed (`no_guess`).",
        Part("suggested", _facts.suggested_facts), Part("facts", _facts.with_suggestions),
        Part("no_guess", _start_box.no_guessed_district)),
    "facts.drop_stale": Command(
        "The saved facts without a lot or building that is no longer in the model (`facts`).",
        Part("facts", _facts.drop_stale)),
    "facts.sources": Command(
        "Where each fact came from: every fact the box set (`sources`), the saved sources Draw keeps (`kept`), "
        "after a row's dialog (`row_sources`) and after the box's typed answers (`typed_sources`).",
        Part("sources", _facts.fact_sources), Part("kept", _facts.sources_kept),
        Part("row_sources", _facts.row_sources), Part("typed_sources", _facts.typed_sources)),
    "facts.row": Command(
        "A row's dialog: its questions (`fields`), the facts after OK (`facts`; refused with words when an entry "
        "isn't an answer) and what the dialog says at OK (`problem`, null when it may close).",
        Part("fields", _facts.row_fields), Part("facts", _facts.row_answers_applied),
        Part("problem", _facts.row_problem)),
    # ---- the start box ----
    "box.view": Command(
        "The start box as it shows: its rows (`rows`), whether Draw is on (`can_draw`), why not (`draw_reason`) "
        "and the reason line under Draw (`box_reason`).",
        Part("rows", _start_box.box_rows), Part("can_draw", _start_box.can_draw),
        Part("draw_reason", _start_box.draw_reason), Part("box_reason", _start_box.box_reason)),
    "box.pick": Command(
        "After one of the box's picks: the facts and the box's choices (`facts`, `saved_ui`), the facts after the "
        "lot is (re)picked (`lot_facts`) and the ticks the box keeps (`ticks`).",
        Part(("facts", "saved_ui"), _facts.pick_effect),
        Part("lot_facts", _facts.after_lot_pick), Part("ticks", _start_box.ticks_after_pick)),
    # ---- the address lookup: edit plans (docs/protocol/worker_protocol_v1.md#edit-plans) ----
    "lookup.choices": Command(
        "After a lookup's answer, decided as an edit plan: (`facts`, `saved_ui`, `guide`, `plan`).",
        Part(("facts", "saved_ui", "guide", "plan"), _edits.lookup_edits)),
    "lookup.preview": Command(
        "After a lookup's answer, shown only (nothing in the model changes): (`facts`, `saved_ui`, `ring`).",
        Part(("facts", "saved_ui", "ring"), _start_box.preview_lookup)),
    "lookup.reset": Command(
        "At Draw, the pending answer drawn for good, as an edit plan: (`facts`, `saved_ui`, `redraw_house`, "
        "`guide`, `plan`).",
        Part(("facts", "saved_ui", "redraw_house", "guide", "plan"), _edits.reset_edits)),
    # ---- the street side ----
    "streets.pick": Command(
        "A click on a lot line as the street side: the street lines and their street names (`lines`, `ids`) with "
        "what the command line says (`said`) and any question left to ask (`unasked`); whether the click is "
        "refused (`click_refused`); a corner lot's runs after one more click (`runs`, `run_said`, `run_unasked`).",
        Part(("lines", "ids"), _streets.pick_street, said="said", ask=("ask", "answers", "unasked")),
        Part("click_refused", _streets.refused_click),
        Part(("runs", "run_said"), _streets.add_street_pick, ask=("ask", "run_answers", "run_unasked"))),
    "streets.lines": Command(
        "The street lines from the runs kept (`lines`, `ids`), after a corner lot's clicks (`after_picks`), and "
        "each outline piece's known street (`names`).",
        Part(("lines", "ids"), _streets.street_lines_of),
        Part("after_picks", _streets.street_lines_after_picks),
        Part("names", _streets.outline_names)),
    "streets.verdict": Command(
        "Whether street lines are one street, two, or unsure, and their total swing (`verdict`, `swing`): the "
        "measuring's own.",
        Part(("verdict", "swing"), _streets.street_verdict)),
    "streets.words": Command(
        "What the command line says a click kept (`words`), the street pick's prompt (`prompt`), and a corner "
        "lot's words so far (`so_far`).",
        Part("words", _streets.street_words), Part("prompt", _streets.street_pick_prompt),
        Part("so_far", _streets.so_far)),
    # ---- whether the results shown are current ----
    "session.freshness": Command(
        "Whether to check again after an edit (`recheck`), whether the result shown is out of date (`stale`), "
        "whether the model counts as changed after a start box closes (`changed`), and whether a check still "
        "shows the model (`still`).",
        Part("recheck", _freshness.should_recheck), Part("stale", _freshness.result_stale),
        Part("changed", _freshness.changed_after_box, fields={"before": "box_before", "now": "box_now"}),
        Part("still", _freshness.checked_while_still)),
    "session.undo": Command(
        "The undo steps' names (`words`), whether an undo event means check again (`recheck`), and when the model "
        "last changed after an Undo or Redo (`dirty_at`).",
        Part("words", constant=(_freshness, "UNDO_WORDS")), Part("recheck", _freshness.after_undo_redo),
        Part("dirty_at", _freshness.dirty_after_undo)),
    # ---- words ----
    "report.message": Command(
        "What the panel says after a report was asked for (`message`), of a report whose model changed meanwhile "
        "(`outdated`), and when its check was cancelled (`cancelled`).",
        Part("message", _report.report_message), Part("outdated", _report.outdated_report_message),
        Part("cancelled", _report.report_cancelled)),
    "panel.rows": Command(
        "The panel's words: its header (`header`), a row's status words (`status`), name (`name`) and list cells "
        "(`cell_name`, `proposed`), the colour a status shades (`highlight`), a detail's parts (`detail`) and a "
        "cell's text (`cell`).",
        Part("header", _panel_words.panel_header), Part("status", _panel_words.status_words),
        Part("name", _panel_words.row_name), Part(("cell_name", "proposed"), _panel_words.list_cells),
        Part("highlight", _panel_words.highlight), Part("detail", _panel_words.detail_parts),
        Part("cell", _panel_words.cell_text, fields={"text": "cell_text"})),
    # ---- which objects the check leaves out (protocol 1.1) ----
    "objects.left_out": Command(
        "Of the objects a host sends that could be a building and aren't measured (host_core/left_out.py says what "
        "each is): whether each is left out of the check, on the lot or with no box to tell (`left_out`), whether "
        "it may be part of the house (`touching`; null when it has no box, which counts as touching), and why it "
        "has no box that covers all of it (`no_box`).",
        Part("left_out", _left_out.left_out_decisions), Part("touching", _left_out.touching_decisions),
        Part("no_box", _left_out.no_box_reasons)),
}


def _with_missing(fields):
    """`fields` with {"$missing": true} read as lookup.MISSING where, and only where, host_core puts it: the old and
    new value of each step of a pending preview's undo list (saved_ui._pending.undo: start_box.preview_lookup). Any
    "$missing" object anywhere else stays an object, which plain() then refuses (never read as no value)."""
    pending = (fields.get("saved_ui") or {}).get("_pending") if isinstance(fields.get("saved_ui"), dict) else None
    if isinstance(pending, dict) and isinstance(pending.get("undo"), list):
        undo = [[unplain(v) if i in (2, 3) else v for i, v in enumerate(step)] if isinstance(step, list) else step
                for step in pending["undo"]]
        fields = dict(fields, saved_ui=dict(fields["saved_ui"], _pending=dict(pending, undo=undo)))
    return fields


def run(name: str, request: dict) -> dict:
    """The answer to a session command (COMMANDS[name]) for `request` (how: the notes above the table)."""
    command = COMMANDS[name]
    fields = _with_missing({k: v for k, v in request.items() if k not in ENVELOPE})
    unknown = sorted(set(fields) - command.fields)
    if unknown:
        raise ValueError(f"{name} doesn't read {', '.join(unknown)} (it reads: {', '.join(sorted(command.fields))})")
    try:
        plain(fields)
    except NotPlain as e:
        raise ValueError(f"{name}: a value the protocol doesn't carry: {e}")
    want = request.get("want")
    if want is not None:                # only the answers named: each must have what it needs
        outs = {o for p in command.parts for o in p.outs}
        if not isinstance(want, list) or not want or not all(isinstance(w, str) for w in want):
            raise ValueError(f"{name}: want is a list of answer names")
        unknown = sorted(set(want) - outs)
        if unknown:
            raise ValueError(f"{name} has no answer {', '.join(unknown)} (it answers: {', '.join(sorted(outs))})")
        chosen = [p for p in command.parts if set(p.outs) & set(want)]
        short = [p for p in chosen if not p.runs(fields)]
        if short:
            raise ValueError(f"{name}: " + "; ".join(f"{'/'.join(p.outs)} needs {', '.join(p.required)}" for p in short))
        parts = chosen
    else:
        parts = [p for p in command.parts if p.runs(fields)]
    needs = "; ".join(f"{'/'.join(p.outs)} needs {', '.join(p.required) or 'nothing'}" for p in command.parts if p.fn)
    unread = sorted(set(fields) - set().union(*(p.fields for p in parts)))
    if unread:          # sent, but nothing that reads it can run: never quietly dropped
        raise ValueError(f"{name}: {', '.join(unread)} sent, but no answer that reads it has all it needs ({needs})")
    if not parts:
        raise ValueError(f"{name}: send the fields of at least one answer ({needs})")
    result, refused = {}, {}
    for part in parts:
        part.answer(fields, result, refused)
    if refused:
        result["refused"] = refused
    try:
        return _json.loads(_json.dumps(plain(result), allow_nan=False))
    except (NotPlain, ValueError) as e:
        raise TypeError(f"{name}: its answer can't be carried as JSON ({e})")


def table() -> list:
    """The command table as the protocol's pin hashes it (tests/test_protocol.py): every command, part and field."""
    return [{"cmd": n, "parts": [p.describe() for p in c.parts]} for n, c in sorted(COMMANDS.items())]


REFERENCE = ("<!-- the command reference: written by protocol.reference() (python -m design_checker.protocol "
             "--write-doc); a test keeps it equal -->", "<!-- end of the command reference -->")
DOC = REPO / "docs" / "protocol" / "worker_protocol_v1.md"


def reference() -> str:
    """The session commands, one table each, as docs/protocol/worker_protocol_v1.md lists them."""
    out = []
    for name, command in COMMANDS.items():
        out += ["", f"### `{name}`", "", command.doc, "", "| Answer | host_core | Needs | May also send |",
                "|---|---|---|---|"]
        for p in command.parts:
            outs = ", ".join(f"`{o}`" for o in p.outs)
            if p.constant is not None:
                out.append(f"| {outs} | `{p.name}` (a constant) | nothing: always given | |")
                continue
            sig = _inspect.signature(p.fn).parameters
            optional = [f"`{f}` ({sig[q].default!r})" for f, q in p.params.items() if f not in p.required]
            if p.ask:
                optional.append(f"`{p.ask[1]}` (answers to its questions, in order)")
            out.append(f"| {outs} | `{p.name}` | {', '.join(f'`{f}`' for f in p.required) or 'nothing'} | "
                       f"{', '.join(optional)} |")
    return "\n".join(out[1:]) + "\n"


def write_doc() -> None:
    text = DOC.read_text(encoding="utf-8")
    head, _, rest = text.partition(REFERENCE[0])
    _, _, tail = rest.partition(REFERENCE[1])
    DOC.write_text(head + REFERENCE[0] + "\n\n" + reference() + "\n" + REFERENCE[1] + tail, encoding="utf-8",
                   newline="\n")


if __name__ == "__main__":
    import sys

    from rule_format.rulebook import utf8_console
    utf8_console()
    if sys.argv[1:] != ["--write-doc"]:
        print("python -m design_checker.protocol --write-doc    rewrites the command reference in " + str(DOC))
        sys.exit(2)
    write_doc()
