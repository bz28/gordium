"""The headless session of host_core calls the protocol's parity test replays (design_checker/tests/test_protocol.py).

    python -m design_checker.call_session --record     records it again (about 5 minutes)

Recorded without Rhino, by driving the plugin's own logic through the tests that exercise it (the start box, the
lookup, the street picks, the row dialog, freshness, undo, the panel's words, the edit plans with a fake model): each
host_core call the tests make, with its arguments and its answer (worker_client.CallRecorder, through the pytest
plugin tests/record_calls.py). Only calls of the functions the worker serves (protocol.COMMANDS) are kept, each
different call once, at most CAP for each function (picked by a hash of the call, so the same calls are picked again
on the same code), in test_data/sessions/headless_calls/calls.jsonl.

A call recorded in Rhino (CallRecorder installed in the plugin, GORDIUM_RECORD_CALLS set) has the same form and
can be added beside it."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from rule_format.rulebook import REPO, read_jsonl, utf8_console

from . import protocol

SESSION = REPO / "test_data" / "sessions" / "headless_calls" / "calls.jsonl"
CAP = 40
TESTS = ["test_start_box_ticks.py", "test_re_lookup.py", "test_lookup_box.py", "test_row_dialog.py",
         "test_use_questions.py", "test_check_button.py", "test_undo_steps.py", "test_edit_plans.py",
         "test_host_core.py", "test_side_yards.py", "test_highlight.py", "test_box_width.py",
         "test_moved_and_crossing.py", "test_progress.py", "test_present.py", "test_adu_panel.py",
         "test_area_answers.py", "test_occupancy_display.py", "test_fact_conflicts.py", "test_autocomplete.py",
         "test_citation_links.py", "test_no_document.py", "test_primary_buildings_check.py", "test_check.py",
         "test_r3_hand_keys.py", "test_context_box.py"]


def served() -> dict:
    """{host_core function's name ("start_box.box_rows"): (command, part)} for every function the worker serves."""
    return {p.name: (cmd, p) for cmd, c in protocol.COMMANDS.items() for p in c.parts if p.fn is not None}


def entries(path: Path = SESSION) -> list[dict]:
    return read_jsonl(path)


def _key(entry: dict) -> str:
    return hashlib.sha256(json.dumps([entry["fn"], entry["args"], entry.get("tuples"), entry.get("sets"), entry.get("asked")])
                          .encode("utf-8")).hexdigest()       # (key order kept: it can decide host_core's words)


def keep(lines) -> tuple[list[dict], dict]:
    """(the calls kept: served, each different call once, at most CAP per function, in a fixed order; how many
    were seen of each function)."""
    names, seen, kept = served(), {}, {}
    for entry in lines:
        if entry["fn"] not in names:
            continue
        seen[entry["fn"]] = seen.get(entry["fn"], 0) + 1
        kept.setdefault(entry["fn"], {})[_key(entry)] = entry
    out = []
    for fn in sorted(kept):
        out += [kept[fn][k] for k in sorted(kept[fn])[:CAP]]
    return out, seen


def record(target: Path = SESSION) -> int:
    with tempfile.TemporaryDirectory() as folder:
        env = dict(os.environ, GORDIUM_RECORD_CALLS=folder,      # (the plugin, tests/record_calls.py)
                   PYTHONPATH=os.pathsep.join(p for p in (str(REPO / "tests"), os.environ.get("PYTHONPATH")) if p))
        tests = [str(REPO / "packages/design_checker/tests" / t) for t in TESTS]
        done = subprocess.run([sys.executable, "-m", "pytest", "-p", "record_calls", "-q", "-n", "3", "-p",
                               "no:cacheprovider", *tests], cwd=REPO, env=env)
        lines = [e for f in sorted(Path(folder).glob("calls-*.jsonl")) for e in read_jsonl(f)]
        skipped = {}
        for f in Path(folder).glob("skipped-*.json"):
            for k, v in json.loads(f.read_text(encoding="utf-8")).items():
                skipped[k] = skipped.get(k, 0) + v
    out, seen = keep(lines)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        for entry in out:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")     # keys in the order they were given
    for fn in sorted(served()):
        print(f"{fn:40} {seen.get(fn, 0):6} calls seen, {sum(1 for e in out if e['fn'] == fn):3} kept")
    print("not recorded:", json.dumps({k: v for k, v in sorted(skipped.items()) if k.split(":")[0] in served()
                                       or ":" not in k}, indent=1))
    print(f"{len(out)} calls -> {target.relative_to(REPO)} (the tests exited {done.returncode})")
    return 0 if out else 1


if __name__ == "__main__":
    utf8_console()
    if sys.argv[1:] != ["--record"]:
        print(__doc__)
        sys.exit(2)
    sys.exit(record())
