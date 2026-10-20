"""Grade the drafted/ folder of this checkout with the eval harness's own functions (test_eval.py), printing
every result instead of stopping at the first failing assert. Run from a checkout with PYTHONPATH set."""
import importlib.util
import json
import sys
from pathlib import Path

import openpyxl

root = Path.cwd()
spec = importlib.util.spec_from_file_location("test_eval", root / "packages/rule_drafting/tests/test_eval.py")
te = importlib.util.module_from_spec(spec)
spec.loader.exec_module(te)
from rule_format.rulebook import Context, load, outcome, validate  # noqa: E402

ctx = Context.for_jurisdiction(te.ITHACA)
rules = load(te.DRAFTED / "R-1b.yaml")["rules"]
if (te.DRAFTED / "general.yaml").exists():
    rules += load(te.DRAFTED / "general.yaml")["rules"]
hand = load(te.ITHACA / "5_zoning_rules/R-1b.yaml")["rules"]
out = {"hand_examples": [], "spreadsheet": [], "chart_values": [], "inspector": {}, "foreign_cells": [],
       "uncovered_hand_rules": []}

# 1. every hand example
for h in hand:
    cov = te.covering(h, rules, ctx)
    if not cov:
        out["uncovered_hand_rules"].append(h["id"])
        continue
    for ex in h["examples"]:
        got, notes = te.judge_r1b_example(cov, ex["given"], ctx)
        out["hand_examples"].append({"hand": h["id"], "given": ex["given"], "expect": ex["expect"], "got": got,
                                     "agree": got == ex["expect"], "drafted": [r["id"] for r in cov], "notes": notes})

# 2. the architects' spreadsheet
design = load(te.SITE)
values = {k: m["value"] for k, m in design["measurements"].items()} | {"district": "R-1b"}
book = openpyxl.load_workbook(te.REPO / design["spreadsheet"], data_only=True)
hb = {h["id"]: h for h in hand}
for row in book["Output"].iter_rows(min_row=3):
    label, theirs = row[0].value, row[6].value
    if not label:
        continue
    cov = te.covering(hb[design["compare"][label]], rules, ctx)
    if not cov:
        out["spreadsheet"].append({"row": label, "theirs": theirs, "got": "not drafted", "agree": None})
        continue
    got, notes = te.combined(cov, values, ctx, set(ctx.proposed))
    out["spreadsheet"].append({"row": label, "theirs": theirs, "got": got, "agree": got == theirs.lower(),
                               "drafted": [r["id"] for r in cov], "notes": notes})

# 3. chart values exact (the harness's own check, with its readings)
chart, cells = te.load_chart_test()
cited, enforced, wrong = te.chart_value_results(rules, chart, cells, ctx)
out["chart_values"] = {"cited": sorted(map(list, cited)), "enforced": sorted(map(list, enforced)), "wrong": wrong}

# 3b. law exceptions judged alone never pass what the answer key fails
out["exception_false_passes"] = te.exception_false_passes(hand, rules, ctx)
out["idle_chart_numbers"] = te.idle_chart_numbers(rules, chart, cells, ctx)

# 4. inspector and own cells
for p in sorted(te.DRAFTED.glob("*.yaml")):
    out["inspector"][p.name] = validate(load(p), ctx)
    if p.stem != "general":
        out["foreign_cells"] += [(p.stem, r["id"]) for r in load(p)["rules"] for s in r["sources"]
                                 if "cell" in s and te.district_name(s["cell"]["column"]) != p.stem]
total = sum(len(load(p).get("rules", [])) for p in te.DRAFTED.glob("*.yaml"))
he = out["hand_examples"]
sp = [s for s in out["spreadsheet"] if s["agree"] is not None]
out["summary"] = {"rules_saved": total, "r1b_rules": len(rules),
                  "hand_examples_agree": f"{sum(x['agree'] for x in he)}/{len(he)}",
                  "spreadsheet_agree": f"{sum(x['agree'] for x in sp)}/{len(sp)} (of {len(out['spreadsheet'])} rows)",
                  "chart_rows_enforced_exactly": f"{len(enforced)}/{len(cited)}",
                  "chart_values_wrong": len(wrong),
                  "exception_false_passes": len(out["exception_false_passes"]),
                  "idle_chart_numbers": len(out["idle_chart_numbers"]),
                  "inspector_clean": all(v == [] for v in out["inspector"].values()),
                  "foreign_cells": len(out["foreign_cells"]),
                  "uncovered_hand_rules": out["uncovered_hand_rules"]}
json.dump(out, open(sys.argv[1], "w"), indent=1, default=str)
print(json.dumps(out["summary"], indent=1))
