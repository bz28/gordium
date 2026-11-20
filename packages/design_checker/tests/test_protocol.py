"""The worker's session commands (protocol 1.1, design_checker/protocol.py, docs/protocol/worker_protocol_v1.md).

The parity proof: for every host_core call recorded while the tests drove the plugin's own logic headlessly
(test_data/sessions/headless_calls/calls.jsonl, design_checker/call_session.py), the function called directly still
gives the recorded answer, and the worker's JSON answer to the same call, sent as a request line through serve(), is
that same answer. Then the rules of the table itself: only listed commands, nothing quietly ignored, nothing
quietly changed on the way out, and no change to the commands without a version and a changelog line."""

import copy
import hashlib
import io
import json

import pytest

from design_checker import call_session, protocol
from design_checker.__main__ import NEW, answer, serve
from design_checker.goldens import canonical_text
from design_checker.host_core.freshness import UNDO_WORDS
from design_checker.host_core.lookup import MISSING
from design_checker.host_core.worker_client import CallRecorder, NotPlain, plain, unplain, with_tuples
from rule_format.rulebook import REPO

ENTRIES = call_session.entries()
SERVED = call_session.served()
DOCS = REPO / "docs/protocol"
ABOUT = {"protocol": "1.0", "site_schema": "gordium.site/1", "worker_fingerprint": "-", "rulebook": {}}


def _replayed_ask(calls):
    """A question callable giving the recorded answers in order, checking each question is the recorded one."""
    left = list(calls)

    def ask(*question):
        asked, said = left.pop(0)
        assert list(question) == asked
        return said
    return ask


def _in_process(entry):
    """((outcome, value), args after): the function called directly, with its arguments as the plugin had them
    (tuples made tuples again, a question answered as it was), as host_core gives it now."""
    part = SERVED[entry["fn"]][1]
    args = unplain(copy.deepcopy(entry["args"]))
    for name, paths in (entry.get("sets") or {}).items():          # (first: a set's place may be inside a tuple)
        args[name] = with_tuples(args[name], paths, set)
    for name, paths in (entry.get("tuples") or {}).items():
        args[name] = with_tuples(args[name], paths)
    for name, calls in (entry.get("asked") or {}).items():
        args[name] = _replayed_ask(calls)
    if part.said and args.get(part.said) is None:
        args[part.said] = []                                 # (as the function does itself: its words seen)
    try:
        value = part.fn(**args)
    except Exception as e:                                  # noqa: BLE001 (its own error is part of its answer)
        return ("raised", [type(e).__name__, str(e)]), args
    return ("result", plain(value)), args


def _request(n, entry):
    """The recorded call as a session command's request line."""
    cmd, part = SERVED[entry["fn"]]
    field_of = {param: field for field, param in part.params.items()}
    fields = {}
    for name, value in entry["args"].items():
        if name == part.said:
            continue                                         # (the worker gives its own empty list)
        if part.ask and name == part.ask[0]:
            continue                                         # (None: no one to ask, as with no answers)
        fields[field_of[name]] = value
    if part.ask and part.ask[0] in (entry.get("asked") or {}):     # a callable: its answers, in the order asked
        fields[part.ask[1]] = [said for _, said in entry["asked"][part.ask[0]]]
    return {"id": n, "cmd": cmd, "protocol": "1.0", "want": [part.outs[0]], **fields}


def _expected(entry, outcome, args):
    """What the worker's answer must say for this call: {field: value} in `result`, or its error words."""
    part = SERVED[entry["fn"]][1]
    kind, value = outcome
    if kind == "raised":
        if value[0] == "ValueError":
            return {"refused": {part.outs[0]: value[1]}}, None
        return None, f"{value[0]}: {value[1]}"
    names = part.out if isinstance(part.out, tuple) else (part.out,)
    out = dict(zip(names, value)) if isinstance(part.out, tuple) else {part.out: value}
    if part.said:
        given = entry["args"].get(part.said) or []
        out[part.said] = plain(args[part.said])[len(given):]
    if part.ask:
        out[part.ask[2]] = []                                # every question answered as it was
    return out, None


@pytest.fixture(scope="module")
def replies():
    """The worker's answer to every recorded call, all sent through one serve() as request lines."""
    lines = "".join(json.dumps(_request(n, e), allow_nan=False) + "\n" for n, e in enumerate(ENTRIES))
    out = io.StringIO()
    real = protocol.about
    protocol.about = lambda: ABOUT        # (the fingerprints, 30 ms each, are tested in test_site_json.py)
    try:
        serve(io.StringIO(lines), out)
    finally:
        protocol.about = real
    return [json.loads(line) for line in out.getvalue().splitlines()]


def test_the_session_has_calls_of_every_function_the_worker_serves():
    recorded = {e["fn"] for e in ENTRIES}
    assert len(ENTRIES) > 500
    assert set(SERVED) <= recorded, sorted(set(SERVED) - recorded)


def _same_answer(now, recorded) -> bool:
    """Whether host_core's answer now is the recorded one, in the goldens' canonical text (goldens.canonical_text:
    every word, verdict and id exact, true never 1, every number to a millionth): the session was recorded on an Apple-chip Mac, and an
    Intel or AMD computer's maths library can give a number's last binary digit otherwise (a curved street's swing,
    90.00000000000004 degrees on the Mac and 90.00000000000003 on CI's Linux, both "unsure")."""
    return canonical_text(now) == canonical_text(recorded)


def test_each_recorded_call_still_gives_its_recorded_answer():
    stale = []
    for e in ENTRIES:
        outcome, _ = _in_process(e)
        if not _same_answer(outcome, ("result", e["result"]) if "result" in e else ("raised", e["raised"])):
            stale.append(e["fn"])
    assert not stale, f"host_core answers differently now: record again (python -m design_checker.call_session " \
                      f"--record) if that is meant: {sorted(set(stale))}"


def test_a_recorded_answer_is_the_same_to_its_last_digits_but_not_in_a_word_or_a_millionth():
    swing = ("result", ["unsure", 90.00000000000004])
    assert _same_answer(("result", ("unsure", 90.00000000000003)), swing)      # an Intel computer's last digit
    assert not _same_answer(("result", ["one", 90.00000000000003]), swing)     # another verdict
    assert not _same_answer(("result", ["unsure", 90.000002]), swing)          # two millionths of a degree
    assert not _same_answer(("raised", ["ValueError", "unsure"]), swing)
    assert not _same_answer(("result", [1]), ("result", [True]))                    # yes/no is not a number
    assert not _same_answer(("result", [0.0]), ("result", [False]))


def test_no_served_function_changes_what_it_was_given():
    """Stateless: the host gets everything back in the answer, so a function that changed its arguments in place
    would lose that change on the way to the host."""
    for e in ENTRIES:
        part = SERVED[e["fn"]][1]
        changed = set(e.get("mutated") or {}) - {part.said}
        assert not changed, (e["fn"], changed)


def test_every_command_answers_in_json_what_the_function_answers_in_process(replies):
    assert len(replies) == len(ENTRIES)
    differ = []
    for n, (e, reply) in enumerate(zip(ENTRIES, replies)):
        assert reply["id"] == n
        outcome, args = _in_process(e)
        want, error = _expected(e, outcome, args)
        if error is not None:
            if reply["ok"] or reply["error"] != error:
                differ.append((e["fn"], error, reply.get("error")))
            continue
        assert reply["ok"], (e["fn"], reply.get("error"))
        assert reply["about"] == ABOUT
        got = {k: reply["result"].get(k, "(absent)") for k in want}
        if "refused" not in want:
            got.pop("refused", None)
            assert "refused" not in reply["result"] or SERVED[e["fn"]][1].outs[0] not in reply["result"]["refused"]
        if got != want:
            differ.append((e["fn"], n))
    assert not differ, differ[:5]


def test_the_session_has_tuples_and_questions_answered_in_order():
    """The two places JSON differs from Python: tuples (arrays on the wire), and questions to the architect."""
    assert sum(1 for e in ENTRIES if e.get("tuples")) >= 10
    assert any(e.get("sets") for e in ENTRIES if e["fn"] == "facts.drop_stale")     # the model's ids, as sets
    assert any(e.get("asked") for e in ENTRIES if e["fn"] in ("streets.pick_street", "streets.add_street_pick"))


def test_a_preview_gives_the_same_answer_in_every_process():
    """preview_lookup listed its undo steps in a set's order, which changes with each process's string hashing: the
    same call answered in the worker and in Rhino gave the steps in another order (found by the replay above)."""
    import subprocess
    import sys
    call = next(e for e in ENTRIES if e["fn"] == "start_box.preview_lookup" and "result" in e
                and len((e["result"][1].get("_pending") or {}).get("undo") or []) > 3)
    script = ("import json, sys\nfrom design_checker.host_core.start_box import preview_lookup\n"
              "from design_checker.host_core.worker_client import plain, unplain\n"
              "args = unplain(json.loads(sys.stdin.read()))\n"
              "print(json.dumps(plain(preview_lookup(**args)[1]['_pending']['undo'])))\n")
    said = {subprocess.run([sys.executable, "-c", script], input=json.dumps(call["args"]), capture_output=True,
                           text=True, encoding="utf-8", check=True, env={**__import__("os").environ, "PYTHONHASHSEED": seed}).stdout
            for seed in ("1", "2", "3", "4")}
    assert len(said) == 1, said


# ---- the table's rules ------------------------------------------------------------------------------------------

def _ask(cmd, **fields):
    return answer({"id": 1, "cmd": cmd, "protocol": "1.0", **fields})


def test_only_listed_commands_each_part_one_host_core_function():
    assert set(protocol.COMMANDS) <= set(NEW)
    for name, command in protocol.COMMANDS.items():
        for part in command.parts:
            owner = part.fn.__module__ if part.fn is not None else part.constant[0].__name__
            assert owner.startswith("design_checker.host_core."), (name, part.name)
    for cmd in ("facts.missing.__globals__", "facts.parse_answer", "missing", "box.view.rows", "os.system"):
        reply = _ask(cmd, facts={})
        assert not reply["ok"] and reply["error"] == f"unknown command {cmd!r}", reply


def test_the_session_commands_need_the_protocol_and_the_older_ones_dont():
    reply = answer({"id": 1, "cmd": "facts.missing", "facts": {}})
    assert not reply["ok"] and "protocol None not spoken" in reply["error"]
    assert not answer({"id": 1, "cmd": "facts.missing", "protocol": "2.0", "facts": {}})["ok"]
    assert _ask("facts.missing", facts={})["ok"]
    assert answer({"id": 1, "cmd": "facts", "facts": {}})["ok"]              # an older command: as before


def test_a_field_not_read_or_not_usable_is_refused():
    reply = _ask("facts.missing", fact={})
    assert not reply["ok"] and "doesn't read fact" in reply["error"]
    reply = _ask("session.undo", dirty_at=3.0)          # dirty_at without now: dirty_after_undo can't run
    assert not reply["ok"] and "dirty_at sent, but no answer that reads it" in reply["error"]
    reply = _ask("facts.missing")
    assert not reply["ok"] and "send the fields of at least one answer" in reply["error"]


def test_a_number_that_isnt_finite_is_refused_both_ways(monkeypatch):
    reply = _ask("facts.missing", facts={"grade_elevation": float("nan")})
    assert not reply["ok"] and "nan" in reply["error"]
    part = protocol.COMMANDS["facts.missing"].parts[0]
    monkeypatch.setattr(part, "fn", lambda facts: [float("inf")])
    reply = _ask("facts.missing", facts={})
    assert not reply["ok"] and "can't be carried as JSON" in reply["error"]


def test_a_key_that_isnt_text_is_never_quietly_made_text(monkeypatch):
    part = protocol.COMMANDS["facts.missing"].parts[0]
    monkeypatch.setattr(part, "fn", lambda facts: {1: "one"})
    reply = _ask("facts.missing", facts={})
    assert not reply["ok"] and "key that isn't text" in reply["error"]


def test_a_refusal_comes_with_its_words_and_the_other_parts_still_answer():
    reply = _ask("facts.validate", kind="count", text="two", key="attached_units_in_building")
    assert reply["ok"]
    assert reply["result"]["refused"] == {"value": "a whole number, 1 or more"}
    assert reply["result"]["problem"].startswith("Not kept: a whole number, 1 or more")
    assert "value" not in reply["result"]
    assert _ask("facts.validate", kind="count", text="2", key="attached_units_in_building")["result"] == {"value": 2,
                                                                                              "problem": None}


def test_each_part_gets_its_own_copy():
    facts = {"street_line": [[[0, 0], [10, 0]]], "street_ids": ["a"], "lot_id": "old"}
    result = _ask("box.pick", facts=facts, picked_lot="new", what="draw_lot", outcome="new",
                  saved_ui={})["result"]
    assert result["lot_facts"]["lot_id"] == "new" and "street_line" not in result["lot_facts"]
    assert result["facts"]["lot_id"] == "new"


def test_want_asks_for_those_answers_only():
    """panel.rows with a row missing its name: status_words answers, row_name would raise; in Rhino each is called
    on its own, so the host asks for the one it needs (found by the replay: a part it didn't ask for failed it)."""
    item = {"status": "complies", "group": "yard"}
    assert _ask("panel.rows", item=item, want=["status"])["result"] == {"status": "Complies"}
    assert not _ask("panel.rows", item=item)["ok"]                      # all that can run: row_name's KeyError
    reply = _ask("panel.rows", item=item, want=["detail"])
    assert not reply["ok"] and "detail needs det" in reply["error"]
    reply = _ask("panel.rows", item=item, want=["nope"])
    assert not reply["ok"] and "has no answer nope" in reply["error"]
    reply = _ask("panel.rows", item=item, status="red", want=["status"])
    assert not reply["ok"] and "status sent, but no answer that reads it" in reply["error"]


def test_no_answer_is_named_refused_so_a_refusal_never_hides_one():
    """Review round 1: streets.pick's click answer was named "refused", and a part's refusal took its place."""
    assert all("refused" not in p.outs for c in protocol.COMMANDS.values() for p in c.parts)
    result = _ask("streets.pick", old_lines=[], old_ids=[], name="A", picked=[[0, 0]],
                  outline=[[[0, 0], [1, 0]], [[1, 0], [1, 1]]])["result"]
    assert "lines" in result["refused"] and "click_refused" in result


def test_a_constant_is_always_given():
    assert _ask("session.undo")["result"] == {"words": UNDO_WORDS}


def test_a_question_not_answered_is_listed_and_an_answer_sent_is_used():
    """streets.pick: the questions a pick asks come back as `unasked` until the host sends answers for them."""
    asked = [e for e in ENTRIES if e["fn"] == "streets.add_street_pick" and e.get("asked", {}).get("ask")]
    assert asked
    e = asked[0]
    request = _request(0, e)
    request.pop("run_answers", None)
    request["want"] = ["runs"]
    first = answer(request)["result"]
    assert [q for q in first["run_unasked"]] == [q for q, _ in e["asked"]["ask"]]
    again = answer(dict(request, run_answers=[a for _, a in e["asked"]["ask"]]))["result"]
    assert again["run_unasked"] == []
    for bad in (["yes"], [0], [1], [0.0], "tf", {"a": True}):    # (round 1: 0 meant as No was kept as street)
        reply = _ask("streets.pick", runs=[], outline=[[[0, 0], [1, 0]]], picked=[[0, 0], [1, 0]], run_answers=bad)
        assert reply["ok"] is False and "each answer true, false or null" in reply["error"], bad


# ---- the recorder -----------------------------------------------------------------------------------------------

def test_the_session_recorder_still_saves_every_request(tmp_path):
    """Review round 1: a dedupe meant for CallRecorder landed in the session Recorder, which then saved nothing."""
    from design_checker.host_core.worker_client import Recorder
    recorder = Recorder(str(tmp_path))
    for _ in range(2):
        recorder._end(recorder._begin({"cmd": "facts", "facts": {}}), [], {"ok": True})
    assert recorder.failed is None
    assert len((tmp_path / "session.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_the_recorder_saves_a_call_and_never_changes_it(tmp_path):
    import types
    module = types.ModuleType("design_checker.host_core.sample")
    exec("__all__ = ['add', 'kept']\n"
         "def add(items, extra=()):\n    items.append(len(extra))\n    return tuple(items)\n"
         "def kept(value):\n    return add([], value)\n", module.__dict__)
    recorder = CallRecorder(str(tmp_path))
    assert recorder.install([module]) == 2
    assert module.kept((1, 2)) == (2,)
    assert module.add([1], extra=[object()]) == (1, 1)          # an object: not recorded, still answered
    lines = [json.loads(x) for f in tmp_path.glob("calls-*.jsonl") for x in f.read_text(encoding="utf-8").splitlines()]
    by = {line["fn"] for line in lines}
    assert by == {"sample.kept", "sample.add"}            # the call inside a call too
    add = next(x for x in lines if x["fn"] == "sample.add")
    assert add["args"] == {"items": [], "extra": [1, 2]} and add["tuples"] == {"extra": [[]]}
    assert add["result"] == [2] and add["mutated"] == {"items": [2]}
    assert recorder.skipped == {"sample.add: an argument the protocol can't carry": 1}


def test_the_recorder_keeps_key_order_and_skips_a_question_that_raised(tmp_path):
    """Key order can decide host_core's words (a lookup's reasons are said in the order it gave them): a recording
    with sorted keys replayed differently. And a question the architect escaped (it raised) is no call a host can
    send."""
    import types
    module = types.ModuleType("design_checker.host_core.sample3")
    exec("__all__ = ['said', 'asks']\n"
         "def said(details):\n    return ' '.join(details)\n"
         "def asks(ask):\n    return ask('one street?')\n", module.__dict__)
    recorder = CallRecorder(str(tmp_path))
    recorder.install([module])
    assert module.said({"zone": 1, "address": 2}) == "zone address"

    def esc(question):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        module.asks(esc)
    assert module.asks(lambda q: True) is True
    text = "".join(f.read_text(encoding="utf-8") for f in tmp_path.glob("calls-*.jsonl"))
    lines = [json.loads(x) for x in text.splitlines()]
    assert '"details": {"zone": 1, "address": 2}' in text
    assert [x["fn"] for x in lines] == ["sample3.said", "sample3.asks"]
    assert lines[1]["asked"] == {"ask": [[["one street?"], True]]}
    assert recorder.skipped == {"sample3.asks: a question it asked raised": 1}


def test_the_recorder_skips_calls_while_a_test_has_swapped_something(tmp_path):
    import types
    module = types.ModuleType("design_checker.host_core.sample2")
    exec("__all__ = ['f']\nLIMIT = 1\ndef f():\n    return LIMIT\n", module.__dict__)
    recorder = CallRecorder(str(tmp_path))
    recorder.install([module])
    module.LIMIT = 2
    assert module.f() == 2
    assert not list(tmp_path.glob("calls-*.jsonl"))
    assert recorder.skipped == {"host_core swapped by a test": 1}


def test_plain_refuses_what_json_would_change():
    for bad in (float("nan"), float("inf"), {1: "a"}, {"a": {(1, 2): 3}}, object(), {1, 2}):
        with pytest.raises(NotPlain):
            plain(bad)
    paths = []
    assert plain({"a": (1, [2, (3,)])}, (), paths) == {"a": [1, [2, [3]]]}
    assert paths == [["a"], ["a", 1, 1]]
    assert with_tuples({"a": [1, [2, [3]]]}, paths) == {"a": (1, [2, (3,)])}


def test_missing_goes_as_its_own_mark_both_ways_and_nothing_else_looks_like_it():
    """A pending preview's undo list holds lookup.MISSING (a key that had no value): the host stores saved_ui, so
    it travels as {"$missing": true} and comes back as the very same object (drop_pending reads it with `is`)."""
    value = {"undo": [("saved", "zone_source", MISSING, "NYS")]}
    assert plain(value) == {"undo": [["saved", "zone_source", {"$missing": True}, "NYS"]]}
    assert unplain(plain(value))["undo"][0][2] is MISSING
    for bad in ({"$missing": True}, {"$missing": False}, {"a": {"$missing": 1, "b": 2}}):
        with pytest.raises(NotPlain):
            plain(bad)
    assert not _ask("facts.missing", facts={"zone": {"$missing": True, "x": 1}})["ok"]
    # only where host_core puts it (review round 1: sent as a fact, zone stopped being listed as missing)
    for mark in ({"$missing": True}, {"$missing": 1}):
        reply = _ask("facts.missing", facts={"zone": mark})
        assert not reply["ok"] and "$missing" in reply["error"], reply
    assert unplain({"$missing": 1}) == {"$missing": 1}
    assert any("$missing" in json.dumps(e) for e in ENTRIES if e["fn"] == "start_box.preview_lookup")


# ---- the version pin and the docs -------------------------------------------------------------------------------

def _pin():
    schema = (DOCS / "site_description_v1.schema.json").read_text(encoding="utf-8").replace("\r\n", "\n")
    table = json.dumps(protocol.table(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((schema + "\n" + table).encode("utf-8")).hexdigest()


def test_the_commands_cant_change_without_a_version_and_a_changelog_line():
    changelog = (DOCS / "CHANGELOG.md").read_text(encoding="utf-8")
    line = next((x for x in changelog.split("\n- ") if f"command table sha256 `{_pin()}`" in x), None)   # its entry
    assert line is not None, "the schema or the command table changed: bump the protocol version (docs/protocol/" \
                             f"worker_protocol_v1.md#versions) and add a CHANGELOG line with command table sha256 `{_pin()}`"
    assert f"protocol {protocol.PROTOCOL} " in line


def test_the_pin_sees_a_new_field_a_default_and_a_renamed_answer(monkeypatch):
    before = _pin()
    part = protocol.COMMANDS["streets.verdict"].parts[0]
    monkeypatch.setattr(part, "out", ("verdict", "turn"))
    assert _pin() != before
    monkeypatch.undo()
    monkeypatch.setitem(part.params, "tolerance", "ids")
    assert _pin() != before


def test_the_versions_rule_names_when_a_new_site_field_that_can_change_a_verdict_is_minor():
    """Protocol 1.3 added left_out[].slab, which changes verdicts, as a minor version (review round 1: the rule then
    said any such field was major). The rule names the condition that makes it safe, in both pages, and the strict
    field check it rests on still refuses a field it doesn't know."""
    from design_checker import site_json
    for page in ("site_description_v1.md", "worker_protocol_v1.md"):
        text = (DOCS / page).read_text(encoding="utf-8")
        rule = " ".join(text.split("## Versions", 1)[1].split("\n## ", 1)[0].split())
        assert "minor" in rule and "even when it can change a verdict" in rule, page
        assert "refuses it as unknown" in rule and "never drops it" in rule, page
        assert "absence means exactly the old behaviour" in rule, page
    assert "though the field can change a verdict" not in (DOCS / "CHANGELOG.md").read_text(encoding="utf-8")
    doc = json.loads((REPO / "test_data/host_conformance/expected/01_box_house.site.json").read_text(encoding="utf-8"))
    doc["left_out"] = [{"id": "x", "layer": None, "could_be_building": True, "touching": None, "ground_like": False,
                        "context": False, "a_newer_field": "patio"}]
    assert any("unknown field 'a_newer_field'" in r for r in site_json.problems_of(doc))


def test_the_doc_lists_every_command_as_the_table_has_it():
    text = (DOCS / "worker_protocol_v1.md").read_text(encoding="utf-8")
    block = text.split(protocol.REFERENCE[0], 1)[1].split(protocol.REFERENCE[1], 1)[0]
    assert block.strip() == protocol.reference().strip(), "run python -m design_checker.protocol --write-doc"
    for name in protocol.COMMANDS:
        assert f"### `{name}`" in block
