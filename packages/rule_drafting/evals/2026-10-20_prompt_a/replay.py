"""Baseline: replay a recorded drafting run through TODAY's checks, into a scratch checkout's drafted/ folder.

    python replay.py --checkout <scratch checkout> runs/<run>.jsonl ...

Run with PYTHONPATH pointing at that scratch checkout's packages; its 5_zoning_rules/drafted is rebuilt from
scratch. It refuses (and deletes nothing) unless the checkout named is the one whose code is running, is not the
checkout Gordium is installed from, and its drafted/ holds no file git lacks. Importing this file does nothing.
For each unit, the recorded attempts are replayed in order exactly as draft_unit would judge them now (first
attempt with no problems is used; else the last attempt with working rules, its rejections listed for a person;
else failed). No retries are possible (they would need new API calls), so this is the run as it would stand
under today's checks.

Answers recorded before the `numbers` field existed get, for each typed number, every binding policy B could
trust (best case for the answer): a sentence of the piece being drafted, a footnote on a slot's own cell, a
slot's own row label, when it holds the value.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from rule_drafting import __main__ as cli, drafter  # noqa: E402
from rule_drafting.templates import number_places  # noqa: E402
from rule_format.rulebook import REPO, source_numbers  # noqa: E402


def installed_checkout() -> Path | None:
    """The checkout Gordium is installed from (pip install -e): where rule_format comes from when PYTHONPATH and
    the current folder are ignored. None when it isn't installed."""
    found = subprocess.run([sys.executable, "-I", "-c", "import rule_format.rulebook as r; print(r.REPO)"],
                           capture_output=True, text=True, encoding="utf-8", cwd=Path(sys.executable).parent)
    return Path(found.stdout.strip()).resolve() if found.returncode == 0 and found.stdout.strip() else None


def refusal(checkout: Path, drafted: Path) -> str | None:
    """Why the replay must not rebuild this checkout's drafted/ folder, or None when it may."""
    checkout = checkout.resolve()
    if checkout != REPO.resolve():
        return (f"the code running is from {REPO}, not {checkout}: set PYTHONPATH to {checkout}/packages/* so the "
                "replay reads and writes the same checkout")
    if checkout == installed_checkout():
        return (f"{checkout} is the checkout Gordium is installed from (its real drafted rulebooks); replay into a "
                "scratch checkout made with git worktree add --detach")
    status = subprocess.run(["git", "-C", str(checkout), "status", "--porcelain", "--ignored", "--", str(drafted)],
                            capture_output=True, text=True, encoding="utf-8")
    if status.returncode != 0:
        return f"could not ask git whether {drafted} holds files git does not have: {status.stderr.strip()}"
    if status.stdout.strip():
        return (f"{drafted} holds files git does not have (drafted rulebooks, paid-call records), which the replay "
                "would delete for good; move them yourself or use a fresh scratch checkout")
    return None


def has(text, v):
    return any(abs(v - x) < 1e-9 for x in source_numbers(text, percent_as_number=False))


def best_bindings(i, t, unit):
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkout", type=Path, required=True,
                        help="the scratch checkout whose drafted/ folder is rebuilt")
    parser.add_argument("runs", nargs="+", type=Path, help="recorded run files (.jsonl)")
    args = parser.parse_args(argv)
    sys.modules["anthropic"] = None                     # a replay never calls the API
    i = cli.Inputs()
    if why := refusal(args.checkout, i.drafted):
        print(f"replay refused, nothing deleted: {why}", file=sys.stderr)
        return 2
    if i.drafted.exists():
        shutil.rmtree(i.drafted)
    log = {"units": {}, "complete": False}

    attempts = {}
    for f in args.runs:
        for line in f.read_text(encoding="utf-8").splitlines():
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
                answer = answer | {"templates": [t | {"numbers": best_bindings(i, t, unit)} for t in answer["templates"]]}
            result = drafter.check_answer(answer, unit, context, i.law, i.ctx, i.columns, i.cells, i.notes,
                                          rec["model"] and f"rule_drafting/{rec['model']}")
            ok = not result["problems"] and (result["rules"] or answer["no_rule_reason"].strip())
            if k == 0:
                first_ok = bool(ok)
            if ok:
                result["reason"] = "" if result["rules"] else answer["no_rule_reason"].strip()
                chosen = drafter.keep(result, unit, i.cells, i.columns, context, chart=i.chart)
                break
            notes.append(f"attempt {rec['attempt']}: " + "; ".join(result["problems"])[:600])
            if result["rules"]:
                last = result
        if chosen is None and last is not None:
            chosen = drafter.keep(last, unit, i.cells, i.columns, context, last_attempt=True, chart=i.chart)
            outcome = "partial (last attempt with working rules kept)"
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
    (i.records / "drafting_log.yaml").write_text(__import__("yaml").safe_dump(log, sort_keys=False, width=110),
                                                 encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
