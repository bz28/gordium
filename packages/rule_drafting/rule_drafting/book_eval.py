"""The AI-drafted house egress rules against the hand answer key, rule by rule (egress step 3).

    python -m rule_drafting.book_eval            # writes evals/2026-11-13_house_egress/comparison.md
    python -m rule_drafting.book_eval --check    # fails if that file is out of date

The answer key (test_data/answer_keys/new_york/new_york_state/general.yaml) was written by a helper that never saw a
draft; the drafts (new_york_state/5_building_code_rules/drafted/general.yaml) by the recorded drafting run, which
never reads the key. Rules are compared where they come from the same law: each rule belongs to the pieces its
id names (general.<piece>_..., both sides' convention), and the rules of one piece are taken together on each side
(one side may split a piece's requirement into two rules where the other writes one). Every worked example of either side, a small design,
is run through both sides' rules for that piece, by the checker's own rows (rule_format/parts.py): for each
part (and each "none" row, by the part it sits in) the worst result on each side (fail, then needs review, then pass,
then not applicable). A part where the two differ is a disagreement; so is a piece one side has rules for and the other
none. Each disagreement is resolved by reading the law, in resolutions.yaml beside the report: `causes` (one entry
per cause: verdict, why, the law it rests on; a draft that is wrong says whether it could pass what the law fails) and `ids` (each disagreement's id: its cause; many disagreements share
one, a wrong scope shows in every example). A test (tests/test_house_egress_key.py) fails while one isn't. Plain
code, no AI.
"""

import argparse
import sys
from pathlib import Path

import yaml

from rule_format import parts

from .book import SCOPE
from rule_format.rulebook import REPO, Context, load, outcome, rules_folder, utf8_console

STATE = REPO / "regulations/jurisdictions/new_york/new_york_state"
KEY = REPO / "test_data/answer_keys/new_york/new_york_state/general.yaml"
DRAFTS = rules_folder(STATE) / "drafted/general.yaml"
HERE = Path(__file__).resolve().parents[1] / "evals/2026-11-13_house_egress"
REPORT, RESOLUTIONS = HERE / "comparison.md", HERE / "resolutions.yaml"
WORST = ("fail", "needs_review", "pass", "not_applicable")
STRICTNESS = {"fail": 3, "needs_review": 2, "pass": 1, "not_applicable": 1, "no row": 1}   # how far from a pass


def rules_of(path: Path) -> list[dict]:
    return [r for r in (load(path) or {}).get("rules", []) if isinstance(r, dict)] if path.is_file() else []


def own_piece(rule: dict) -> str | None:
    """The piece a rule was written for: its id is "general." plus the piece's id in lowercase with underscores
    (general.r319_2_1_...), the drafter's prefix and the answer key's convention alike; the longest that fits."""
    rid = str(rule.get("id", "")).removeprefix("general.")
    fits = [p for p in SCOPE if rid == slug(p) or rid.startswith(slug(p) + "_")]
    return max(fits, key=len) if fits else None


def slug(pid: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in pid.lower())


def groups(rules: list[dict]) -> dict[str, list[dict]]:
    """{piece: [rules written for it]}; a rule for no piece of this step's scope under "" (reported)."""
    out: dict[str, list[dict]] = {}
    for r in rules:
        out.setdefault(own_piece(r) or "", []).append(r)
    return out


def completed(ex: dict, rules: list[dict]) -> dict:
    """The example with every yes/no measure the rules read and its parts don't give taken as no (the ordinary case:
    not a spiral stair, not under a deck, not into a patio cover). An example is written for its own side's rules, and
    a yes/no it leaves out would make the other side's answer needs review for want of an input, not for the law.
    A number left out stays out: that difference is reported."""
    kinds = {}
    for rule in rules:
        if parts.is_part_rule(rule):
            yes_no = {m for m, k in parts.measure_kinds(rule["for_each"]).items() if k == "boolean"}
            kinds.setdefault(rule["for_each"], set()).update(parts.formula_names(rule) & yes_no)
    given = ex.get("parts") if isinstance(ex.get("parts"), dict) else {}
    out = {}
    for kind, items in given.items():
        out[kind] = [dict(p, measures={**{m: False for m in kinds.get(kind, ())}, **(p.get("measures") or {})})
                     if isinstance(p, dict) else p for p in items] if isinstance(items, list) else items
    return dict(ex, parts=out)


def verdicts(rules: list[dict], ex: dict, allowed: dict) -> dict[tuple, str]:
    """{(part id, ""), or ("", the id of the part it sits in) for a "none" row, or ("", "") for a row about no part
    and for a rule about the whole building (over the example's given values): the worst result any of the rules
    gives it}. A part is the same part whatever the rule groups it by."""
    out: dict[tuple, str] = {}
    for rule in rules:
        if not parts.is_part_rule(rule):                     # a rule for the whole building: the building's row
            got = outcome(rule, ex.get("given") or {}, allowed)
            out[("", "")] = got if ("", "") not in out else min(out[("", "")], got, key=WORST.index)
            continue
        for row in parts.rows(rule, ex.get("parts"), ex.get("given") or {}, allowed):
            key = (row["id"], "") if row["id"] else ("", (row.get("within") or {}).get("id") or "")
            old = out.get(key)
            out[key] = row["outcome"] if old is None else min(old, row["outcome"], key=WORST.index)
    return out


def compare(key: list[dict], drafts: list[dict], ctx) -> list[dict]:
    """Every disagreement, each with a stable id: <piece>/<whose example>/<rule id>#<n>/<part>."""
    allowed = ctx.allowed()
    k, d = groups(key), groups(drafts)
    out = []
    for pid in sorted(set(k) | set(d)):
        if pid not in k or pid not in d or not pid:
            side = "the answer key" if pid in k else "the drafts"
            ids = sorted(r["id"] for r in (k.get(pid) or d.get(pid)))
            out.append({"id": f"{pid or 'no piece'}/only", "piece": pid or "no piece",
                        "what": f"only {side} has rules for {pid or 'no piece of this step'}: {', '.join(ids)}"})
            continue
        for whose, rules in (("key", k[pid]), ("draft", d[pid])):
            for rule in rules:
                for n, ex in enumerate(rule.get("examples") or [], 1):
                    if not isinstance(ex.get("parts"), dict):
                        continue
                    ex = completed(ex, k[pid] + d[pid])
                    a, b = verdicts(k[pid], ex, allowed), verdicts(d[pid], ex, allowed)
                    for part in sorted(set(a) | set(b)):
                        if a.get(part) != b.get(part):
                            label = part[0] or (f"none in {part[1]}" if part[1] else "the building")
                            out.append({"id": f"{pid}/{whose}/{rule['id']}#{n}/{label}", "piece": pid,
                                        "key": a.get(part, "no row"), "draft": b.get(part, "no row"),
                                        "what": f"{whose} example {n} of {rule['id']}, {label}: "
                                        f"key {a.get(part, 'no row')}, drafts {b.get(part, 'no row')}"})
    return out


def resolutions_of(path: Path = None) -> tuple[dict, dict]:
    """(causes, {disagreement id: its cause's entry plus its name}) from resolutions.yaml; ({}, {}) if none."""
    path = path or RESOLUTIONS
    data = (load(path) or {}) if path.is_file() else {}
    causes = data.get("causes") or {}
    return causes, {i: dict(causes.get(c) or {}, cause=c) for i, c in (data.get("ids") or {}).items()}


def report(key: list[dict], drafts: list[dict], found: list[dict], resolutions: dict) -> str:
    lines = ["# House egress: the AI drafts against the hand answer key", "",
             "Generated by `python -m rule_drafting.book_eval` (rule_drafting/book_eval.py says how). Do not edit.", "",
             f"- Answer key: {len(key)} rules (`{KEY.relative_to(REPO)}`)",
             f"- Drafts: {len(drafts)} rules (`{DRAFTS.relative_to(REPO)}`)",
             f"- Disagreements: {len(found)}, resolved {sum(f['id'] in resolutions for f in found)}", ""]
    by_piece: dict[str, list[dict]] = {}
    for f in found:
        by_piece.setdefault(f["piece"], []).append(f)
    for pid, items in by_piece.items():
        lines += [f"## {pid}", ""]
        for f in items:
            r = resolutions.get(f["id"]) or {}
            lines.append(f"- `{f['id']}`: {f['what']}. **{r.get('verdict', 'UNRESOLVED')}**"
                         + (f" (cause `{r['cause']}`)" if r else ""))
        lines.append("")
    causes = {r["cause"]: r for f in found if (r := resolutions.get(f["id"]))}
    if causes:
        lines += ["## Causes, each resolved by reading the law", ""]
        for name, r in sorted(causes.items()):
            n = sum((resolutions.get(f["id"]) or {}).get("cause") == name for f in found)
            risk = " (could pass what the law fails)" if r.get("false_pass_risk") else ""
            lines.append(f"- **`{name}`** ({n} disagreement{"s" if n != 1 else ""}), **{r.get('verdict')}**{risk}: "
                         f"{' '.join(str(r.get('why', '')).split())} Law: {' '.join(str(r.get('law', '')).split())}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m rule_drafting.book_eval")
    parser.add_argument("--check", action="store_true", help="fail if comparison.md is out of date")
    args = parser.parse_args(argv)
    ctx = Context.for_jurisdiction(STATE)
    key, drafts = rules_of(KEY), rules_of(DRAFTS)
    found = compare(key, drafts, ctx)
    resolutions = resolutions_of()[1]
    text = report(key, drafts, found, resolutions)
    if args.check:
        same = REPORT.is_file() and REPORT.read_text(encoding="utf-8") == text
        print("✓ comparison.md is current" if same else "✗ comparison.md is out of date: python -m rule_drafting.book_eval")
        return 0 if same else 1
    HERE.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text, encoding="utf-8")
    print(f"{len(found)} disagreements, {sum(f['id'] in resolutions for f in found)} resolved; wrote {REPORT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    utf8_console()
    sys.exit(main(sys.argv[1:]))
