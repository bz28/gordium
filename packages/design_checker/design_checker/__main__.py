"""Check a design from the command line, or serve the Rhino command.

    python -m design_checker <model.3dm> <model_facts.yaml>   # prints the summary and every row
    python -m design_checker <model.3dm> <model_facts.yaml> --interior <house.yaml>
                                                              # ... with the house's interior (gordium.interior/1):
                                                              # egress checked too; without it, egress waits
    python -m design_checker serve                            # Rhino: one JSON request per line in, one answer out

Requests (one JSON object per line): {"id": 1, "cmd": "check", "model": "<.3dm>", "facts": {...}, "report":
"<.xlsx or null>", "today": "YYYY-MM-DD"} ("today": the day of the check, the place's own day; optional, and
without it no saved address lookup counts as recent, so the overlays row stays: the checker never reads the clock), {"id": 2, "cmd": "options", "jurisdiction": "regulations/jurisdictions/..."}, {"id": 3, "cmd": "facts",
"facts": {...}} (what's wrong with saved lot facts: the same check as a facts file), {"id": 4, "cmd": "start",
"model": "<.3dm with the lot>", "facts": {...}, "larger_side": null} (the largest legal starting building, as stacked floors;
"larger_side": "left" or "right" puts a zone's larger side yard there), {"id": 5, "cmd": "sample_site"} (the
106 Ithaca Rd lot and facts GordiumStart offers). New-style commands name the protocol they speak (protocol.py,
docs/protocol/): {"id": 6, "cmd": "hello", "protocol": "1.3"} (the protocol, the site description version and the
fingerprints of the worker's code and rules), {"id": 7, "cmd": "read_model", "protocol": "1.3", "model": "<.3dm>",
"facts": {...}} (the model as a site description, gordium.site/1: site_json.read_model), {"id": 8, "cmd":
"check_site", "protocol": "1.3", "site": {...}, "facts": {...}, "report": null, "extras": {...}, "interior":
{...}} (check() for a site description: check.check_description; "interior", from protocol 1.2: the house's inside,
gordium.interior/1, which the egress laws are checked on; without it they wait) and {"id": 9, "cmd": "start_site", "protocol": "1.3", "site": {...}, "facts":
{...}, "floor_to_floor": null, "design_buffer": 0, "larger_side": null} (start() for one); their answers carry
"about" (the same fingerprints) beside "result". The session commands (protocol.COMMANDS: facts.*, box.view,
box.pick, lookup.*, streets.*, session.*, report.message, panel.rows, objects.left_out) are host_core's functions served by a fixed
table, e.g. {"id": 10, "cmd": "box.view", "protocol": "1.3", "state": {...}}: every field in
docs/protocol/worker_protocol_v1.md. Answers:
{"id": 1, "ok": true, "result": {...}} or {"id": 1, "ok": false, "error": "..."}. A request with "progress": true
also gets {"id": 1, "step": "Measuring the building…"} lines before its answer, one as each stage starts (the
plugin's progress line; the answer is always the request's last line), and the same line again, marked
{"again": true}, every HEARTBEAT seconds while a stage runs, so a host that stops a check only when the worker falls
silent (the Revit add-in, which also has a ceiling on the whole check) never stops a long check for being long; a host that shows or records stages (Rhino,
the recorded sessions) skips the repeats. The process stays up, so a
check after an edit doesn't pay for starting Python and loading the rules again.
"""

import json
import os
import sys
import threading
import traceback
from pathlib import Path

from model_measurement.project import fact_problems, load_facts
from rule_format.rulebook import utf8_console

from . import protocol, site_json
from .check import check, check_description, options, sample_site, start, start_description
from .rhino_logic import city_day


def _read_model(request: dict) -> dict:
    inventory = request.get("inventory_complete", False)
    if not isinstance(inventory, bool):
        raise ValueError("inventory_complete should be true or false")
    return {"site": site_json.read_model(Path(request["model"]), request["facts"], inventory)}


def _check_site(request: dict, step) -> dict:
    report = request.get("report")
    return check_description(request["site"], request["facts"], Path(report) if report else None,
                             request.get("extras"), step=step, today=request.get("today"),
                             interior=request.get("interior"))


def _start_site(request: dict, step) -> dict:
    return start_description(request["site"], request["facts"], request.get("floor_to_floor"),
                             request.get("design_buffer") or 0.0, request.get("larger_side"), step=step)


# the new-style commands (protocol 1.x, docs/protocol/): each answer carries "about" (protocol.about)
NEW = {"hello": lambda request, step: protocol.about(), "read_model": lambda request, step: _read_model(request),
       "check_site": _check_site, "start_site": _start_site}
# ... and the session commands, host_core's functions served by a fixed table (protocol.COMMANDS: facts.*, box.*, ...)
NEW.update({name: (lambda name: lambda request, step: protocol.run(name, request))(name) for name in protocol.COMMANDS})


def answer(request: dict, step=None) -> dict:
    """The answer to one request; `step(text)` is told each stage of a check or a start as it begins."""
    try:
        if request.get("cmd") == "check":
            report = request.get("report")
            result = check(Path(request["model"]), request["facts"], Path(report) if report else None,
                           request.get("building_problems"), request.get("extras"), step=step,
                           today=request.get("today"))
        elif request.get("cmd") == "start":
            result = start(Path(request["model"]), request["facts"], request.get("floor_to_floor"),
                           request.get("design_buffer") or 0.0, request.get("larger_side"), step=step)
        elif request.get("cmd") == "sample_site":
            result = sample_site()
        elif request.get("cmd") == "facts":
            result = {"problems": fact_problems(request["facts"])}
        elif request.get("cmd") == "options":
            result = options(request["jurisdiction"])
        elif request.get("cmd") in NEW:
            protocol.speaks(request)
            return {"id": request.get("id"), "ok": True, "result": NEW[request["cmd"]](request, step),
                    "about": protocol.about()}
        else:
            raise ValueError(f"unknown command {request.get('cmd')!r}")
        return {"id": request.get("id"), "ok": True, "result": result}
    except ValueError as e:                   # a plain refusal (bad facts, a rulebook that fails its checks)
        return {"id": request.get("id"), "ok": False, "error": str(e)}
    except Exception as e:                    # never take the Rhino session down: report and keep serving
        return {"id": request.get("id"), "ok": False, "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc()}


def serve(stdin=sys.stdin, stdout=sys.stdout) -> None:
    """One answer per request line. `stdin` gives text lines, or bytes (the worker reads its pipe as bytes, so a
    line that isn't UTF-8 gets an answer saying so, never the end of the worker)."""
    for line in stdin:
        if line.strip():
            try:
                if isinstance(line, bytes):
                    line = line.decode("utf-8")        # strict: never text quietly changed (a file path)
                request = site_json.loads(line)        # a key given twice is refused, never one of them dropped
                if not isinstance(request, dict):
                    raise ValueError(f"a request is a JSON object, not {type(request).__name__}")
            except site_json.SiteRefused as e:
                request, reply = {}, {"id": None, "ok": False, "error": "not JSON: " + "; ".join(e.reasons)}
            except json.JSONDecodeError as e:
                request, reply = {}, {"id": None, "ok": False, "error": f"not JSON: {e}"}
            except (ValueError, RecursionError) as e:  # not UTF-8, a number too long, nesting too deep, not an object
                request, reply = {}, {"id": None, "ok": False, "error": f"not a request: {type(e).__name__}: {e}"[:500]}
            else:
                if request.get("progress"):
                    with _Steps(request, stdout) as step:
                        reply = answer(request, step)
                else:
                    reply = answer(request, None)
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


# How often a request that asked for progress hears its current stage again while it runs (seconds).
HEARTBEAT = 15.0


class _Steps:
    """A request's progress lines: one written (and flushed) as each stage starts, and the current one again every
    HEARTBEAT seconds until the answer, from a second thread (one lock: a line is never written into another). The
    answer is always the request's last line: the beat stops, under the lock, before it is written."""

    def __init__(self, request: dict, stdout):
        self._id = request.get("id")
        self._out = stdout
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._last = "Working…"
        self._beat = threading.Thread(target=self._run, daemon=True)

    def _write(self, line: dict) -> None:
        self._out.write(json.dumps(line) + "\n")
        self._out.flush()

    def __call__(self, text: str) -> None:
        with self._lock:                              # the stage and its line together: a repeat never comes after a newer stage
            if self._done.is_set():
                return
            self._last = text
            self._write({"id": self._id, "step": text})

    def repeat(self) -> None:
        """The current stage again, read under the lock (so never an older one after a newer), marked as a repeat."""
        with self._lock:
            if self._done.is_set():
                return
            self._write({"id": self._id, "step": self._last, "again": True})

    def _run(self) -> None:
        while not self._done.wait(HEARTBEAT):
            self.repeat()

    def __enter__(self):
        self._beat.start()
        return self

    def __exit__(self, *exc) -> None:
        with self._lock:
            self._done.set()
        self._beat.join()


def main(argv: list[str]) -> int:
    if argv == ["serve"]:
        # The plugin reads one answer per line. Anything else written to stdout (a library's print, C code writing
        # to file descriptor 1) would put every later answer one request behind, so answers go out on a copy of
        # the real stdout, and stdout itself, at the file-descriptor level, now goes to the log (stderr).
        replies = os.fdopen(os.dup(1), "w", encoding="utf-8")
        sys.stdout.flush()
        os.dup2(2, 1)
        sys.stdout = sys.stderr
        serve(stdin=sys.stdin.buffer, stdout=replies)
        return 0
    interior = None
    if len(argv) == 4 and argv[2] == "--interior":
        import yaml
        try:
            interior = yaml.safe_load(Path(argv[3]).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
            print(f"✗ the interior description can't be read: {e}")
            return 1
        argv = argv[:2]
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        result = check(Path(argv[0]), load_facts(Path(argv[1])), today=city_day(),   # this host's day, said here
                       interior=interior)
    except ValueError as e:
        print(f"✗ {e}")
        return 1
    v = result["view"]                  # the panel's own summary and rows (D3: one summary everywhere, never a ✓)
    print("Gordium ·", v["summary"])
    for s in v.get("sections") or []:     # each law's own state: zoning's, then egress's
        print(f"  {s['title']}: {s['summary']}")
    for i in v["items"]:
        if i["group"] != "not_covered":
            print(f"  {i['mark'] or ' '} {i['name']:34} {i['proposed']:>14} {i['required']:>12} {i['margin']:>10}"
                  + (f"  · {i['reason']}" if i.get("reason") else ""))
    env = result["envelope"]
    print(f"  envelope: yards {env['yards']}, height {env['height']}, top {env['top']}; notes {env['notes']}")
    return 0


if __name__ == "__main__":
    utf8_console()
    sys.exit(main(sys.argv[1:]))
