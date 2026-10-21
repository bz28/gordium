"""Grade the drafted rules against every hand key present (5_zoning_rules/<district>.yaml), with the harness's own
functions (tests/test_eval.py), counting every worked example: agree, disagree, or undrafted (no drafted rule; a
miss, reported apart). Writes the results to the file named on the command line. Run from the repository root."""
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("test_eval", Path.cwd() / "packages/rule_drafting/tests/test_eval.py")
te = importlib.util.module_from_spec(spec)
spec.loader.exec_module(te)
from rule_format.rulebook import Context  # noqa: E402

ctx = Context.for_jurisdiction(te.ITHACA)
out = {}
for path in te.hand_keys():
    g = te.grade_hand_key(path, ctx)
    covered = len(g["agree"]) + len(g["disagree"])
    g["summary"] = {"examples": g["total"], "agree": len(g["agree"]), "disagree": len(g["disagree"]),
                    "undrafted": len(g["undrafted"]), "false_pass": len(g["false_pass"]),
                    "agree_of_all": f"{len(g['agree'])}/{g['total']}", "agree_of_drafted": f"{len(g['agree'])}/{covered}"}
    out[path.name] = g
    print(path.name, g["summary"])
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
