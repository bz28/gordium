"""The New York Revit eval's comparison: the add-in's Check my project result for a model, rule by rule, beside the
building's answer key, with every difference named. It reads only what the worker answered (the check_site result
the add-in logs) and the answer files; it never works a verdict out itself.

    python compare_check_result.py orangetown    <results.jsonl or answer.json> [--model <.rvt name>] [--out <.yaml>]
    python compare_check_result.py 106_ithaca_rd <results.jsonl or answer.json> [--model <.rvt name>] [--out <.yaml>]

The result: the add-in's trial log (`results.jsonl`: its last `check_project` line with an answer, for the model
named when --model is given) or a file holding the worker's answer (`{"result": {...}}`) or its result alone.

  - orangetown: the 115 rules of New York State's egress rulebook, each Gordium's verdict (`result.egress.results`)
    beside hand_check.yaml's `truth` (what the code says of the house as drawn) and `predicted` (what the checker
    should say from what the description holds), with evaluation.md's reason (D, F, G, M, R) where it is more cautious
    than the truth; a false pass (complies, or not applicable, where the truth isn't), a rule not as predicted and a
    rule missing from the result are each named. Every zoning row is Ithaca's, which doesn't apply in Orangetown:
    not compared (the eval's stand-in lot only lets the check be sent).
  - 106_ithaca_rd: the 11 rows of the architects' spreadsheet (Output, column G: their PASS or FAIL), each Gordium's
    verdict (`result.statuses`) for the rule spreadsheet_design.yaml maps it to, the architects' proposed value beside
    Gordium's measured one, and each difference named by the eval's `expected_differences` (with its source) or, when
    none says why, UNEXPLAINED.

Writes the comparison as YAML (--out; default: revit_eval_comparison.yaml in the building's folder) and prints its
summary. Exit 0 when no false pass and no unexplained or unpredicted difference, else 1.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[4]
HOUSE = REPO / "test_data/real_houses/orangetown_ny_80_south_william"
SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
FOLDERS = {"orangetown": HOUSE, "106_ithaca_rd": SITE}
TOOL = "apps/revit_addin/tools/evals/compare_check_result.py"

# one word per verdict, whoever gives it: the checker's rows (pass...), its statuses (complies...), the hand-check,
# the architects' spreadsheet (PASS, FAIL)
WORDS = {"pass": "complies", "complies": "complies", "fail": "does_not_comply", "does_not_comply": "does_not_comply",
         "needs_review": "needs_review", "not_applicable": "not_applicable", "not_checked": "not_checked"}
# how far each verdict goes toward a pass: a verdict kinder than the truth's is a false pass
KINDNESS = {"does_not_comply": 0, "needs_review": 1, "not_checked": 1, "not_applicable": 2, "complies": 2}
WHY = {"D": "the drawings give no stair geometry, so the description has no stairs (evaluation.md, D)",
       "F": "the format can't yet say the house has a basement (evaluation.md, F)",
       "G": "the guard rules read open sides, which nothing produces yet (evaluation.md, G)",
       "M": "a fact the description holds that the measuring doesn't turn into the rule's measure yet (evaluation.md, M)",
       "R": "a rule-drafting point, on the cautious side (evaluation.md, R)"}
EVAL_ROW = re.compile(r"^\| \d+ \| .*\(`([a-z0-9_]+)`\) \| [^|]* \| [^|]* \| ([a-z ]+) \| ([a-z ]+) \| (yes|no) \| ([A-Z]?) \|$")


class BadResult(ValueError):
    """The file given holds no check result this tool can read."""


def word(v) -> str | None:
    if v is None:
        return None
    w = WORDS.get(str(v).strip().lower().replace(" ", "_"))
    if w is None:
        raise BadResult(f"{v!r} isn't a verdict this tool reads")
    return w


def result_of(path: Path, model: str | None = None) -> dict:
    """The worker's check result: from the trial log's last check_project line with an answer (for `model` when
    given: its file or document ends with that name), or from a JSON file of the answer or the result."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        found = None
        for n, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("what") != "check_project" or not entry.get("answer"):
                continue
            where = f"{entry.get('file') or ''} {entry.get('document') or ''}"
            if model is None or any(p.strip().lower().endswith(Path(model).name.lower()) or
                                    p.strip().lower() == Path(model).stem.lower() for p in where.split(" ") if p):
                found = (n, entry)
        if found is None:
            raise BadResult(f"{path}: no check_project line with an answer" + (f" for {model}" if model else ""))
        n, entry = found
        answer = json.loads(entry["answer"]) if isinstance(entry["answer"], str) else entry["answer"]
        source = {"log": str(path), "line": n, "at": entry.get("at"), "model": entry.get("file") or entry.get("document")}
    else:
        answer = json.loads(text)
        source = {"file": str(path)}
    result = answer.get("result", answer) if isinstance(answer, dict) else None
    if not isinstance(result, dict) or not isinstance(result.get("statuses"), dict):
        raise BadResult(f"{path}: not a check_site result (no statuses)")
    result["_source"] = source
    return result


def false_pass(gordium: str, truth: str) -> bool:
    """A verdict kinder than the truth's: a pass the truth doesn't give, a rule set aside the truth doesn't set aside,
    or anything nearer a pass than the truth (not checked where the truth fails)."""
    return (gordium == "complies" and truth != "complies") or (gordium == "not_applicable" and truth != "not_applicable")         or KINDNESS[gordium] > KINDNESS[truth]


def _load(folder: Path, name: str):
    return yaml.safe_load((folder / name).read_text(encoding="utf-8"))


def evaluation_classes(text: str) -> dict:
    """evaluation.md's table: each rule's reason class (D, F, G, M, R) where the checker is more cautious than the
    truth (an empty class where they agree)."""
    return {m.group(1): m.group(5) for line in text.splitlines() if (m := EVAL_ROW.match(line))}


def compare_orangetown(result: dict) -> dict:
    hand = _load(HOUSE, "hand_check.yaml")
    classes = evaluation_classes((HOUSE / "evaluation.md").read_text(encoding="utf-8"))
    marks = _load(HOUSE, "eval_marks.yaml")
    egress = result.get("egress") or {}
    got = {k: word(v) for k, v in (egress.get("results") or {}).items()}
    rows, false_passes, unpredicted, missing = [], [], [], []
    for r in hand["rules"]:
        rid, truth, predicted = r["id"], word(r["truth"]), word(r["predicted"])
        g = got.get(rid)
        row = {"rule": rid, "gordium": g, "truth": truth, "predicted": predicted}
        if g is None:
            row["difference"] = "NOT IN THE RESULT: the check gave this rule no verdict"
            missing.append(rid)
        elif false_pass(g, truth):
            row["difference"] = f"FALSE PASS: Gordium says {g}, the truth is {truth} ({r['why']})"
            false_passes.append(rid)
        elif g == "does_not_comply" and truth != "does_not_comply":
            row["difference"] = f"FALSE FAIL: Gordium says {g}, the truth is {truth} ({r['why']})"
            unpredicted.append(rid)
        elif g != predicted:
            row["difference"] = (f"NOT AS PREDICTED: Gordium says {g}, the hand-check predicted {predicted} "
                                 f"(because {r['because']})")
            unpredicted.append(rid)
        elif g != truth:
            c = classes.get(rid.removeprefix("general."), "")
            row["difference"] = (f"more cautious than the truth, as predicted: {WHY.get(c, 'evaluation.md gives no class')}")
        rows.append(row)
    extra = sorted(set(got) - {r["id"] for r in hand["rules"]})
    items = (result.get("view") or {}).get("items") or []
    claims = [{"item": i["id"], "status": word(i["status"]), "name": i.get("name")} for i in items
              if i["id"].startswith("egress.has_none.")]
    readings = {c["kind"] for c in _load(HOUSE, "house.yaml")["has_none"] if c.get("reading")}
    for c in claims:
        kind = c["item"].removeprefix("egress.has_none.")
        if kind in readings and c["status"] == "not_applicable":
            c["difference"] = ("ticked on Project Information (an eval assumption standing in for the architect), so "
                               "shown not applicable; house.yaml gives it as Gordium's reading, which the description "
                               "path shows as one to confirm (evaluation.md: 'Three rest on a reading')")
    sections = {s.get("key"): {"state": s.get("state"), "summary": s.get("summary")} for s in result.get("sections") or []}
    counts = {}
    for row in rows:
        key = f"{row['gordium']} (truth {row['truth']})"
        counts[key] = counts.get(key, 0) + 1
    return {
        "building": "80 South William Street (Lot 2), Orangetown NY: egress only",
        "made_by": f"{TOOL} (run it on the add-in's result to reproduce this file)",
        "result": result["_source"], "marks": marks.get("model"),
        "answer_key": "test_data/real_houses/orangetown_ny_80_south_william/hand_check.yaml (truth, predicted); "
                      "evaluation.md (the reason class)",
        "summary": {"rules": len(rows), "same_as_truth": sum(r["gordium"] == r["truth"] for r in rows),
                    "as_predicted": sum(r["gordium"] == r["predicted"] for r in rows),
                    "false_passes": false_passes, "not_as_predicted": unpredicted, "not_in_the_result": missing,
                    "not_in_the_hand_check": extra, "by_verdict": dict(sorted(counts.items())),
                    "egress_section": sections.get("new_york/new_york_state"),
                    "zoning": "not compared: Ithaca's zoning doesn't apply in Orangetown (the lot is a stand-in)"},
        "has_none_items": claims,
        "rules": rows,
        "ok": not (false_passes or unpredicted or missing),
    }


def compare_106(result: dict) -> dict:
    import openpyxl

    design = _load(SITE, "spreadsheet_design.yaml")
    marks = _load(SITE, "eval_marks.yaml")
    book = openpyxl.load_workbook(REPO / design["spreadsheet"], data_only=True)
    statuses = {k: word(v) for k, v in result["statuses"].items()}
    items = {i["id"]: i for i in (result.get("view") or {}).get("items") or []}
    measured = result.get("measurements") or {}
    expected = {d["row"]: d for d in marks.get("expected_differences") or []}
    notes = {n["row"]: n["note"] for n in marks.get("notes") or []}
    sides = marks.get("sides") or {}
    rows, unexplained, false_passes = [], [], []
    for cells in book["Output"].iter_rows(min_row=3):
        label, proposed, theirs = cells[0].value, cells[2].value, cells[6].value
        if not label:
            continue
        rule = design["compare"][label]
        key = rule
        if rule == "R-1b.side_yards":
            side = next((s for words, s in sides.items() if words in label.lower()), None)
            named = f"{rule}#{side}" if side else None
            if named in statuses:
                key = named
            else:                          # not told apart: the most cautious of the side-yard rows
                keys = sorted(k for k in statuses if k.split("#")[0] == rule)
                key = min(keys, key=lambda k: KINDNESS[statuses[k]]) if keys else rule
        g, a = statuses.get(key), word(theirs)
        item = items.get(key) or {}
        row = {"row": label, "rule": key, "architects": a, "gordium": g,
               "architects_proposed": proposed, "gordium_reason": item.get("reason")}
        measure = marks.get("measures", {}).get(label)
        if measure:
            row["gordium_measured"] = (measured.get(measure) or {}).get("value")
        if label in notes:
            row["note"] = notes[label]
        if g is None:
            row["difference"] = "NOT IN THE RESULT: the check gave this rule no verdict"
            unexplained.append(label)
        elif g == a:
            pass
        elif label in expected and expected[label]["gordium"] == g:
            row["difference"] = f"expected: {expected[label]['why']} ({expected[label]['source']})"
        else:
            row["difference"] = f"UNEXPLAINED: Gordium says {g}, the architects {a}"
            unexplained.append(label)
        if g is not None and false_pass(g, a):
            row["difference"] = (row.get("difference", "") + "; GORDIUM PASSES WHAT THE ARCHITECTS FAIL").lstrip("; ")
            false_passes.append(label)
        rows.append(row)
    others = {k: v for k, v in sorted(statuses.items()) if k.startswith("R-1b.") and k.split("#")[0]
              not in set(design["compare"].values())}
    return {
        "building": "106 Ithaca Rd (City of Ithaca, R-1b): the architects' spreadsheet design, zoning",
        "made_by": f"{TOOL} (run it on the add-in's result to reproduce this file)",
        "result": result["_source"],
        "answer_key": f"{design['spreadsheet']} (Output, column G), mapped by spreadsheet_design.yaml compare",
        "summary": {"rows": len(rows), "same": sum(r["gordium"] == r["architects"] for r in rows),
                    "expected_differences": [r["row"] for r in rows if str(r.get("difference", "")).startswith("expected")],
                    "unexplained": unexplained, "gordium_passes_what_they_fail": false_passes,
                    "zoning_section": next(({"state": s.get("state"), "summary": s.get("summary")}
                                            for s in result.get("sections") or [] if s.get("key") == "zoning"), None),
                    "egress": "not part of this eval: the spreadsheet's house has no interior"},
        "rows": rows,
        "other_r1b_rules": others,
        "ok": not (unexplained or false_passes),
    }


COMPARE = {"orangetown": compare_orangetown, "106_ithaca_rd": compare_106}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("building", choices=sorted(COMPARE))
    parser.add_argument("result")
    parser.add_argument("--model", help="the .rvt checked, when the log holds several checks")
    parser.add_argument("--out", help="where to write the comparison (default: the building's revit_eval_comparison.yaml)")
    args = parser.parse_args(argv)
    try:
        made = COMPARE[args.building](result_of(Path(args.result), args.model))
    except (BadResult, json.JSONDecodeError) as e:
        print(f"not compared: {e}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else FOLDERS[args.building] / "revit_eval_comparison.yaml"
    out.write_text(yaml.safe_dump(made, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8", newline="\n")
    print(json.dumps(made["summary"], indent=1, ensure_ascii=False))
    print(f"{'ok' if made['ok'] else 'NOT OK'}: written to {out}")
    return 0 if made["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
