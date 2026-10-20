"""Check a design from the command line, or serve the Rhino command.

    python -m design_checker <model.3dm> <model_facts.yaml>   # prints the summary and every row
    python -m design_checker serve                            # Rhino: one JSON request per line in, one answer out

Requests (one JSON object per line): {"id": 1, "cmd": "check", "model": "<.3dm>", "facts": {...}, "report":
"<.xlsx or null>"}, {"id": 2, "cmd": "options", "jurisdiction": "regulations/jurisdictions/..."}, {"id": 3, "cmd": "facts",
"facts": {...}} (what's wrong with saved lot facts: the same check as a facts file), {"id": 4, "cmd": "start",
"model": "<.3dm with the lot>", "facts": {...}} (the largest legal starting building, as stacked floors), {"id": 5, "cmd": "sample_site"} (the
106 Ithaca Rd lot and facts GordiumStart offers). Answers:
{"id": 1, "ok": true, "result": {...}} or {"id": 1, "ok": false, "error": "..."}. The process stays up, so a
check after an edit doesn't pay for starting Python and loading the rules again.
"""

import json
import sys
import traceback
from pathlib import Path

from model_measurement.project import fact_problems, load_facts

from .check import check, options, sample_site, start


def answer(request: dict) -> dict:
    try:
        if request.get("cmd") == "check":
            report = request.get("report")
            result = check(Path(request["model"]), request["facts"], Path(report) if report else None,
                           request.get("building_problems"), request.get("extras"))
        elif request.get("cmd") == "start":
            result = start(Path(request["model"]), request["facts"], request.get("floor_to_floor"))
        elif request.get("cmd") == "sample_site":
            result = sample_site()
        elif request.get("cmd") == "facts":
            result = {"problems": fact_problems(request["facts"])}
        elif request.get("cmd") == "options":
            result = options(request["jurisdiction"])
        else:
            raise ValueError(f"unknown command {request.get('cmd')!r}")
        return {"id": request.get("id"), "ok": True, "result": result}
    except ValueError as e:                   # a plain refusal (bad facts, a rulebook that fails its checks)
        return {"id": request.get("id"), "ok": False, "error": str(e)}
    except Exception as e:                    # never take the Rhino session down: report and keep serving
        return {"id": request.get("id"), "ok": False, "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc()}


def serve(stdin=sys.stdin, stdout=sys.stdout) -> None:
    for line in stdin:
        if line.strip():
            try:
                request = json.loads(line)
            except json.JSONDecodeError as e:
                request, reply = {}, {"id": None, "ok": False, "error": f"not JSON: {e}"}
            else:
                reply = answer(request)
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


def main(argv: list[str]) -> int:
    if argv == ["serve"]:
        serve()
        return 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        result = check(Path(argv[0]), load_facts(Path(argv[1])))
    except ValueError as e:
        print(f"✗ {e}")
        return 1
    v = result["view"]                  # the panel's own summary and rows (D3: one summary everywhere, never a ✓)
    print("Gordium ·", v["summary"])
    for i in v["items"]:
        if i["group"] != "not_covered":
            print(f"  {i['mark'] or ' '} {i['name']:34} {i['proposed']:>14} {i['required']:>12} {i['margin']:>10}"
                  + (f"  · {i['reason']}" if i.get("reason") else ""))
    env = result["envelope"]
    print(f"  envelope: yards {env['yards']}, height {env['height']}, top {env['top']}; notes {env['notes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
