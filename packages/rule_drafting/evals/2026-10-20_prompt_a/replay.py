"""Baseline: replay a recorded drafting run through TODAY's checks, into this checkout's drafted/ folder.

Run with PYTHONPATH pointing at a scratch checkout's packages; that checkout's 5_zoning_rules/drafted is
rebuilt from scratch. For each unit, the recorded attempts are replayed in order exactly as draft_unit would
judge them now (first attempt with no problems is used; else the last attempt with working rules, its
rejections listed for a person; else failed). No retries are possible (they would need new API calls), so
this is the run as it would stand under today's checks.

Answers recorded before the `numbers` field existed get, for each typed number, every binding policy B could
trust (best case for the answer): a sentence of the piece being drafted, a footnote on a slot's own cell, a
slot's own row label, when it holds the value.
"""
import json
import shutil
import sys
from pathlib import Path

sys.modules["anthropic"] = None
from rule_drafting import __main__ as cli, drafter  # noqa: E402
from rule_drafting.templates import number_places  # noqa: E402
from rule_format.rulebook import source_numbers  # noqa: E402

runs = [Path(p) for p in sys.argv[1:]]          # recorded run files (.jsonl)
i = cli.Inputs()
if i.drafted.exists():
    shutil.rmtree(i.drafted)
log = {"units": {}, "complete": False}


def has(text, v):
    return any(abs(v - x) < 1e-9 for x in source_numbers(text, percent_as_number=False))


def best_bindings(t, unit):
    out = []
    for _, _, v, _ in number_places(t):
        for k, q in enumerate(t["quotes"]):
            if q["document"] == "law" and q["piece"] == unit.get("piece") and has(q["text"], v):
                out.append({"value": v, "from": "law_quote", "quote": k, "slot": "", "footnote": ""})
        for s in t["slots"]:
            for f in s["footnotes"]:
                note = i.notes.get(s["page"], {}).get(f)
                if note and has(note["text"], v):
                    out.append({"value": v, "from": "slot_footnote", "quote": -1, "slot": s["name"], "footnote": f})
            if has(s["row"], v):
                out.append({"value": v, "from": "slot_row_label", "quote": -1, "slot": s["name"], "footnote": ""})
    return out


attempts = {}
for f in runs:
    for line in f.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            attempts.setdefault(r["unit"], []).append(r)
units = {u["id"]: u for u in i.units()}
summary = {}
for uid in [cli.USES_UNIT] + sorted(attempts):
    unit = units[uid]
    if uid == cli.USES_UNIT:
        result = cli.draft_uses(i)
        cli.save_result(i, log, uid, result)
        summary[uid] = {"attempts": 0, "first_try_ok": None, "rules": sum(len(r) for r in result["rules"].values()),
                        "rejected": [], "unresolved": len(result.get("unresolved", [])), "outcome": "code"}
        continue
    context = drafter.gather_context(unit, i.law, {"notes": i.notes}, i.definitions)
    chosen, last, first_ok, notes = None, None, None, []
    for k, rec in enumerate(sorted(attempts[uid], key=lambda r: r["attempt"])):
        if rec["stop_reason"] != "end_turn":
            notes.append(f"attempt {rec['attempt']}: stopped early ({rec['stop_reason']})")
            first_ok = False if k == 0 else first_ok
            continue
        answer = json.loads(rec["answer"])
        if answer.get("templates") and "numbers" not in answer["templates"][0]:
            answer = answer | {"templates": [t | {"numbers": best_bindings(t, unit)} for t in answer["templates"]]}
        result = drafter.check_answer(answer, unit, context, i.law, i.ctx, i.columns, i.cells, i.notes,
                                      rec["model"] and f"rule_drafting/{rec['model']}")
        ok = not result["problems"] and (result["rules"] or answer["no_rule_reason"].strip())
        if k == 0:
            first_ok = bool(ok)
        if ok:
            result["reason"] = "" if result["rules"] else answer["no_rule_reason"].strip()
            chosen = drafter.keep(result, unit, i.cells, i.columns)
            break
        notes.append(f"attempt {rec['attempt']}: " + "; ".join(result["problems"])[:600])
        if result["rules"]:
            last = result
    if chosen is None and last is not None:
        chosen, outcome = drafter.keep(last, unit, i.cells, i.columns, last_attempt=True), "partial (last attempt with working rules kept)"
    elif chosen is None:
        chosen = {"failed": notes[-1] if notes else "no answer", "rules": {}, "unresolved": [], "rejected": [],
                  "proposed": {}, "problems": [], "templates": []}
        outcome = "failed"
    else:
        outcome = "accepted"
    cli.save_result(i, log, uid, chosen)
    summary[uid] = {"attempts": len(attempts[uid]), "first_try_ok": first_ok,
                    "rules": sum(len(r) for r in chosen["rules"].values()),
                    "rejected": [x["rule"] + ": " + x["why"][:300] for x in chosen.get("rejected", [])]
                    + [x["rule"] + ": " + x["why"][:300] for x in chosen.get("unresolved", [])],
                    "unresolved": len(chosen.get("unresolved", [])), "outcome": outcome,
                    "reason": chosen.get("reason", ""), "notes": notes}
(i.records / "drafting_log.yaml").write_text(__import__("yaml").safe_dump(log, sort_keys=False, width=110))
print(json.dumps(summary, indent=1))
