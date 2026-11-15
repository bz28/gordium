"""Recorded sessions with the checker, run again: every request a session sent, answered again by the worker's own
`answer()`, must give the same answer and the same progress lines. The answer is compared in the goldens'
canonical form (design_checker/goldens.py: every number to a millionth of a foot): on the computer that recorded
it the line is the same byte for byte, but Linux and Windows can differ from a Mac in a number's last digit
(1.6382695424973557 on one, ...3559 on the other, seen in CI on a plan's yard line), which is not a change.

    python -m design_checker.replay                     every session under test_data/sessions/ (CI: test_replay.py)
    python -m design_checker.replay <folder>            one session
    python -m design_checker.replay --record-seed <folder>   records the seed session (no Rhino; below)

A session is what rhino_logic.Recorder saved (the plugin with GORDIUM_RECORD_SESSION set to a folder):
session.jsonl, one line per request {"n", "request", "steps", "reply"}, and files/<n>/ the copy of each model it
sent. The seed session (test_data/sessions/seed_without_rhino/) was recorded without Rhino, by the same code path
the plugin uses (the worker started as `python -m design_checker serve`, its pipes through rhino_logic.pipes, each
request through rhino_logic.exchange with a Recorder), with requests shaped as the plugin shapes them (GordiumStart
on the sample lot, a check of the house it draws, an edit, a live re-check, a refusal). A session recorded in Rhino
(quickstart_in_rhino.py with the recorder on) goes next to it."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from rule_format.rulebook import REPO, read_jsonl, utf8_console

SESSIONS = REPO / "test_data" / "sessions"


def sessions(folder: Path = SESSIONS) -> list[Path]:
    return sorted(p.parent for p in Path(folder).glob("*/session.jsonl"))


def entries(session: Path) -> list[dict]:
    return read_jsonl(Path(session) / "session.jsonl")


def replayed(session: Path, entry: dict, out: Path) -> tuple[str, list[str]]:
    """(the answer line, the progress lines) the worker's answer() gives the entry's request now: its model the
    session's copy, a report written into `out` (the report is the checker's to write, under its own name)."""
    from design_checker.__main__ import answer
    request = dict(entry["request"])
    if request.get("model"):
        request["model"] = str(Path(session, *request["model"].split("/")))
    if request.get("report"):
        request["report"] = str(Path(out) / request["report"].split("/")[-1])
    steps = []
    reply = answer(request, steps.append if request.get("progress") else None)
    return json.dumps(reply), steps


def _comparable(line):
    """An answer line in the goldens' canonical form (numbers to a millionth of a foot, keys sorted). A crash's
    trace names this computer's files: compared by its last line only."""
    from design_checker.goldens import canonical_text
    if line is None:
        return None
    reply = json.loads(line)
    if "trace" in reply:
        reply = dict(reply, trace=reply["trace"].strip().splitlines()[-1])
    return canonical_text(reply)


def differences(session: Path) -> list[str]:
    """Each recorded request whose answer now differs from the recorded one, or [] when all are the same."""
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for entry in entries(session):
            line, steps = replayed(session, entry, Path(tmp))
            name = f"{Path(session).name} #{entry['n']} {entry['request'].get('cmd')}"
            if entry["reply"] is None:
                out.append(f"{name}: no answer was recorded (the checker stopped or timed out)")
            elif _comparable(line) != _comparable(entry["reply"]):
                out.append(f"{name}: the answer differs ({_first_difference(entry['reply'], line)})")
            if steps != entry["steps"]:
                out.append(f"{name}: the progress lines differ: {entry['steps']} -> {steps}")
    return out


def _first_difference(old: str, new: str) -> str:
    from design_checker.goldens import differences as diff
    found = diff(json.loads(old), json.loads(new), limit=3)
    return "; ".join(found) or "the same data written differently"


# ---- the seed session (no Rhino) ------------------------------------------------------------------------------

def record_seed(folder: Path) -> int:
    """Records the seed session into `folder` (emptied first): the plugin's requests, through the plugin's own
    pipes, exchange and Recorder, to a real worker process. Returns how many requests were recorded."""
    import shutil
    from design_checker import rhino_logic as logic
    from design_checker.goldens import stress_generator
    folder = Path(folder)
    if folder.exists():                       # only ever a session folder is emptied (never `.` by mistake)
        if not {p.name for p in folder.iterdir()} <= {"session.jsonl", "files"}:
            raise ValueError(f"{folder} isn't a recorded session (it holds other files): give a new folder")
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    gen = stress_generator()
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"                   # as the plugin starts it (gordium_rhino._worker)
    worker = subprocess.Popen([sys.executable, "-u", "-m", "design_checker", "serve"], cwd=REPO, env=env,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              universal_newlines=True, encoding="utf-8")
    sends, lines = logic.pipes(worker)
    recorder = logic.Recorder(str(folder))
    asked = [0]

    def ask(request, ok=True):                # gordium_rhino._ask_job: an id, progress on, the exchange recorded
        asked[0] += 2
        request = dict(request, id=asked[0], progress=True)
        reply = logic.exchange(sends, lines, request, logic.ask_limit(request["cmd"]), on_step=lambda t: None,
                               record=recorder)
        if reply is None or bool(reply.get("ok")) != ok:
            raise RuntimeError(f"the worker gave {reply!r} for {request['cmd']}")
        return reply.get("result")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            ask({"cmd": "options", "jurisdiction": logic.PLACE["jurisdiction"]})
            sample = ask({"cmd": "sample_site"})
            facts = dict(sample["facts"])
            ask({"cmd": "facts", "facts": facts})
            ring = [tuple(p[:2]) for p in sample["lot"]]
            lot_path = tmp / "gordium_start_1.3dm"          # the plugin's own names for its copies
            gen._lot_file({"points": ring}, lot_path)
            start = ask({"cmd": "start", "model": str(lot_path), "facts": facts,
                         "floor_to_floor": logic.FLOOR_TO_FLOOR, "design_buffer": 0.0})
            parts = [{"id": f"floor {k + 1}", "kind": "floor", "outline": [list(p[:2]) for p in f["outline"]],
                      "z0": f["base"], "z1": f["top"]} for k, f in enumerate(start["floors"])]
            model = tmp / "gordium_live_1.3dm"
            design = {"lot": {"points": ring}, "parts": parts}

            def extras(before):
                return {"scope": {"groups": 0, "solids": len(parts), "layer": "Building"}, "main_name": None,
                        "not_included": [], "touching": [], "context_left_out": [], "ground_like": [],
                        "sources": {}, "before": before}
            gen.write_3dm(design, model)
            first = ask({"cmd": "check", "model": str(model), "facts": facts, "building_problems": [],
                         "report": None, "extras": extras(None)})
            # an edit: the house moved 6 ft toward the street, then the live re-check (its facts read first)
            for p in parts:
                p["outline"] = [[x, y - 6.0] for x, y in p["outline"]]
            gen.write_3dm(design, model)
            ask({"cmd": "facts", "facts": facts})
            ask({"cmd": "check", "model": str(model), "facts": facts, "building_problems": [], "report": None,
                 "extras": extras(first["statuses"])})
            # the larger side yard on the left, and a block on the Building layer that couldn't be sent
            ask({"cmd": "start", "model": str(lot_path), "facts": facts, "floor_to_floor": logic.FLOOR_TO_FLOOR,
                 "design_buffer": 0.0, "larger_side": "left"})
            ask({"cmd": "check", "model": str(model), "facts": facts, "building_problems": ["a block (Garage)"],
                 "report": None, "extras": extras(None)})
            # a refusal: lot facts with no district
            ask({"cmd": "check", "model": str(model), "facts": {k: v for k, v in facts.items() if k != "zone"},
                 "building_problems": [], "report": None, "extras": extras(None)}, ok=False)
    finally:
        sends.put(None)
        worker.kill()
        worker.wait(timeout=10)
    if recorder.failed:
        raise RuntimeError("the recorder failed: " + recorder.failed)
    return len(entries(folder))


def main(argv: list[str]) -> int:
    if argv[:1] == ["--record-seed"] and len(argv) == 2:
        n = record_seed(Path(argv[1]))
        print(f"recorded {n} requests to {argv[1]}")
        return 0
    folders = [Path(a) for a in argv] or sessions()
    problems = [p for f in folders for p in differences(f)]
    for p in problems:
        print("✗ " + p)
    print(f"{len(folders)} session(s), {sum(len(entries(f)) for f in folders)} requests: "
          + ("every answer is the same" if not problems else f"{len(problems)} differ"))
    return 1 if problems else 0


if __name__ == "__main__":
    utf8_console()
    sys.exit(main(sys.argv[1:]))
