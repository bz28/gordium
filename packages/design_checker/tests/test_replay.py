"""The recorded sessions (test_data/sessions/; design_checker/replay.py): every request a session sent the checker,
answered again by the worker's answer(), gives the recorded answer (in the goldens' canonical form: a number's
last digit may differ between a Mac and Linux or Windows) and the same progress lines.
And the recorder itself (rhino_logic.Recorder): off unless GORDIUM_RECORD_SESSION names a folder, wired into both of
the plugin's exchanges, saving each request, a copy of its model, its progress lines and its exact answer line,
and never stopping a check when it can't save."""
import json
import math
import queue
import re
import shutil
import threading

from design_checker import replay
from design_checker import rhino_logic as logic
from rule_format.rulebook import REPO

RHINO = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")


def test_every_recorded_session_gives_the_same_answers():
    found = replay.sessions()
    assert [p.name for p in found] >= ["seed_without_rhino"]
    for session in found:
        assert replay.entries(session), session
        assert replay.differences(session) == []


def test_the_seed_session_is_the_plugins_requests_with_every_command_and_a_refusal():
    entries = replay.entries(replay.SESSIONS / "seed_without_rhino")
    cmds = [e["request"]["cmd"] for e in entries]
    assert set(cmds) == {"options", "sample_site", "facts", "start", "check"} and cmds.count("check") == 4
    assert all(e["request"]["progress"] is True and e["request"]["id"] == 2 * e["n"] for e in entries)
    replies = [json.loads(e["reply"]) for e in entries]
    assert [r["ok"] for r in replies].count(False) == 1 and "no zone given" in replies[-1]["error"]
    for e in entries:                       # each model the session sent is in it, under the plugin's own name
        if e["request"].get("model"):
            assert re.fullmatch(r"files/\d{4}/gordium_(live|start)_1\.3dm", e["request"]["model"])
            assert (replay.SESSIONS / "seed_without_rhino" / e["request"]["model"]).stat().st_size > 0
    checks = [e for e in entries if e["request"]["cmd"] == "check" and json.loads(e["reply"])["ok"]]
    assert all(e["steps"] == ["Reading the model…", "Measuring the building…", "Checking the rules…"] for e in checks)


def test_a_changed_answer_or_progress_line_is_caught(tmp_path):
    session = tmp_path / "s"
    shutil.copytree(replay.SESSIONS / "seed_without_rhino", session)
    lines = (session / "session.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[2])                       # the facts request: quick
    assert first["request"]["cmd"] == "facts"
    reply = json.loads(first["reply"])
    reply["result"]["problems"] = ["a problem that isn't there"]
    tampered = dict(first, reply=json.dumps(reply), steps=["a step that isn't there"])
    (session / "session.jsonl").write_text(json.dumps(tampered) + "\n", encoding="utf-8")
    problems = replay.differences(session)
    assert len(problems) == 2 and "#3 facts: the answer differs" in problems[0] and "progress lines" in problems[1]


def test_the_recorder_is_off_unless_its_variable_names_a_folder(tmp_path):
    assert logic.Recorder.from_env({}) is None
    assert logic.Recorder.from_env({logic.RECORD_ENV: "  "}) is None
    assert logic.Recorder.from_env({logic.RECORD_ENV: str(tmp_path)}).folder == str(tmp_path)
    assert logic.RECORD_ENV == "GORDIUM_RECORD_SESSION"


def test_the_plugin_records_both_its_exchanges_through_the_recorder_built_from_the_environment():
    job = RHINO[RHINO.index("def _ask_job("):RHINO.index("def _answer(")]
    assert job.count("record=RECORDER)") == 2 == job.count("logic.exchange(") == RHINO.count("logic.exchange(")
    assert RHINO.count("RECORDER = logic.Recorder.from_env(os.environ)") == 1
    assert RHINO.count("RECORDER =") == 1


def _fake_checker(sends, lines, answers):
    """A checker on two queues: each request answered with a progress line, then the answer `answers` gives."""
    def serve():
        while True:
            text = sends.get()
            if text is None:
                return
            request = json.loads(text)
            lines.put(json.dumps({"id": request["id"], "step": "Measuring the building…"}) + "\n")
            lines.put(json.dumps(dict(answers(request), id=request["id"])) + "\n")
    threading.Thread(target=serve, daemon=True).start()


def test_the_recorder_saves_each_request_its_model_its_steps_and_its_exact_answer_line(tmp_path):
    model = tmp_path / "gordium_live_7.3dm"
    model.write_bytes(b"\x00model bytes\xff")
    sends, lines, seen = queue.Queue(), queue.Queue(), []
    _fake_checker(sends, lines, lambda r: {"ok": True, "result": {"a": 1.1000000000000001, "é": "§ 325-8"}})
    rec = logic.Recorder(str(tmp_path / "rec"))
    request = {"cmd": "check", "model": str(model), "facts": {"zone": "R-1b"}, "report": str(tmp_path / "r.xlsx"),
               "id": 4, "progress": True}
    got = logic.exchange(sends, lines, request, 5, on_step=seen.append, record=rec)
    assert got["result"]["a"] == 1.1000000000000001 and seen == ["Measuring the building…"]
    model.write_bytes(b"changed after")               # the copy is what was sent
    saved = [json.loads(x) for x in (tmp_path / "rec/session.jsonl").read_text(encoding="utf-8").splitlines()]
    assert saved == [{"n": 1, "request": dict(request, model="files/0001/gordium_live_7.3dm",
                                              report="files/0001/r.xlsx"),
                      "steps": ["Measuring the building…"], "reply": json.dumps(got)}]
    assert (tmp_path / "rec/files/0001/gordium_live_7.3dm").read_bytes() == b"\x00model bytes\xff"
    assert not (tmp_path / "rec/files/0001/r.xlsx").exists()
    # the answer line exactly as a worker writes it (json.dumps of its reply)
    assert saved[0]["reply"] == json.dumps({"ok": True, "result": {"a": 1.1000000000000001, "é": "§ 325-8"}, "id": 4})
    # a second recorder on the same folder (Rhino started again) carries on after the last request
    rec2 = logic.Recorder(str(tmp_path / "rec"))
    logic.exchange(sends, lines, {"cmd": "facts", "facts": {}, "id": 6, "progress": True}, 5, record=rec2)
    assert [json.loads(x)["n"] for x in (tmp_path / "rec/session.jsonl").read_text(encoding="utf-8").splitlines()] \
        == [1, 2]
    sends.put(None)


def test_a_recording_that_fails_never_stops_the_check(tmp_path):
    sends, lines = queue.Queue(), queue.Queue()
    _fake_checker(sends, lines, lambda r: {"ok": True, "result": "answered"})

    def broken_copy(source, target):
        raise OSError("disk full")
    rec = logic.Recorder(str(tmp_path / "rec"), copy=broken_copy)
    got = logic.exchange(sends, lines, {"cmd": "check", "model": str(tmp_path / "m.3dm"), "id": 2}, 5, record=rec)
    assert got["result"] == "answered" and rec.failed == "OSError: disk full"
    blocked = tmp_path / "file_not_folder"
    blocked.write_text("x", encoding="utf-8")
    rec = logic.Recorder(str(blocked))                 # a folder that can't be made: saving the line fails
    got = logic.exchange(sends, lines, {"cmd": "facts", "id": 4}, 5, record=rec)
    assert got["result"] == "answered" and rec.failed
    sends.put(None)


def test_with_no_recorder_the_exchange_is_unchanged():
    sends, lines = queue.Queue(), queue.Queue()
    _fake_checker(sends, lines, lambda r: {"ok": True, "result": r["cmd"]})
    steps = []
    assert logic.exchange(sends, lines, {"cmd": "options", "id": 2}, 5, on_step=steps.append)["result"] == "options"
    assert steps == ["Measuring the building…"]
    sends.put(None)


def test_a_checker_that_gives_no_answer_is_recorded_as_none_and_replay_says_so(tmp_path):
    sends, lines = queue.Queue(), queue.Queue()
    lines.put(None)                                    # the checker stopped: no answer
    rec = logic.Recorder(str(tmp_path / "s"))
    assert logic.exchange(sends, lines, {"cmd": "facts", "facts": {}, "id": 2, "progress": True}, 5,
                          record=rec) is None
    lines.put(json.dumps({"id": 9, "ok": True}) + "\n")  # another request's line: out of step, raised
    try:
        logic.exchange(sends, lines, {"cmd": "facts", "facts": {}, "id": 4, "progress": True}, 5, record=rec)
    except logic.CheckerOutOfStep:
        pass
    saved = [json.loads(x) for x in (tmp_path / "s/session.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(e["n"], e["reply"]) for e in saved] == [(1, None), (2, None)]
    problems = replay.differences(tmp_path / "s")
    assert problems == ["s #1 facts: no answer was recorded (the checker stopped or timed out)",
                        "s #2 facts: no answer was recorded (the checker stopped or timed out)"]


def test_a_failed_recording_is_told_once_and_numbering_never_reuses_a_copied_model(tmp_path):
    sends, lines = queue.Queue(), queue.Queue()
    _fake_checker(sends, lines, lambda r: {"ok": True, "result": "answered"})
    model = tmp_path / "m.3dm"
    model.write_bytes(b"m")
    rec = logic.Recorder(str(tmp_path / "rec"))
    logic.exchange(sends, lines, {"cmd": "check", "model": str(model), "id": 2}, 5, record=rec)
    (tmp_path / "rec/files/0002").mkdir(parents=True)   # a model copied whose line was then lost
    (tmp_path / "rec/files/\u00b2").mkdir()             # not the recorder's: a digit, but not 0-9
    rec2 = logic.Recorder(str(tmp_path / "rec"))
    logic.exchange(sends, lines, {"cmd": "check", "model": str(model), "id": 4}, 5, record=rec2)
    saved = [json.loads(x) for x in (tmp_path / "rec/session.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["n"] for e in saved] == [1, 3]
    assert rec2.take_failure() is None
    rec2.failed = "OSError: disk full"
    assert rec2.take_failure() == "OSError: disk full" and rec2.take_failure() is None
    sends.put(None)


def test_the_plugin_says_when_it_records_and_when_the_recording_fails():
    assert 'Rhino.RhinoApp.WriteLine("Gordium: recording every check to " + RECORDER.folder)' in RHINO
    answer = RHINO[RHINO.index("def _answer("):]
    answer = answer[:answer.index("\ndef ")]
    assert "failure = RECORDER.take_failure() if RECORDER is not None else None\n    if failure:" in answer
    assert "the session recording failed" in answer


def test_a_numbers_last_digit_is_not_a_change_but_a_millionth_of_a_foot_is(tmp_path):
    session = tmp_path / "s"
    shutil.copytree(replay.SESSIONS / "seed_without_rhino", session)
    lines = (session / "session.jsonl").read_text(encoding="utf-8").splitlines()
    start = json.loads(lines[3])                      # GordiumStart on the lot
    assert start["request"]["cmd"] == "start"
    reply = json.loads(start["reply"])
    height = reply["result"]["floors"][0]["top"]
    for value, caught in ((math.nextafter(height, math.inf), False), (height + 2e-6, True)):   # the last digit
        assert value != height
        reply["result"]["floors"][0]["top"] = value
        (session / "session.jsonl").write_text(json.dumps(dict(start, reply=json.dumps(reply))) + "\n",
                                               encoding="utf-8")
        assert bool(replay.differences(session)) is caught, value
