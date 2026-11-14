"""The AI-drafted house egress rules against the hand answer key, rule by rule (egress step 3).

    python -m rule_drafting.book_eval            # writes evals/2026-11-13_house_egress/comparison.md
    python -m rule_drafting.book_eval --check    # fails if that file is out of date

The answer key (test_data/answer_keys/new_york/new_york_state/houses.yaml) was written by a helper that never saw a
draft; the drafts (new_york_state/5_building_code_rules/drafted/general.yaml) by the recorded drafting run, which
never reads the key. Rules are compared where they come from the same law: each rule belongs to the pieces its
sources sit in, and the rules of one piece for one part kind are taken together on each side (one side may split a
piece's requirement into two rules where the other writes one). Every worked example of either side, a small design,
is run through both sides' rules for that piece and kind, by the checker's own rows (rule_format/parts.py): for each
part (and each "none" row, by the part it sits in) the worst result on each side (fail, then needs review, then pass,
then not applicable). A part where the two differ is a disagreement; so is a piece and kind one side has rules for and
the other none. Each disagreement is resolved by reading the law, in resolutions.yaml beside the report (by its id),
and a test (tests/test_house_egress_key.py) fails while one isn't. Plain code, no AI.
"""

import argparse
import sys
from pathlib import Path

import yaml

from rule_format import code_numbers, parts
from rule_format.rulebook import REPO, Context, load, rules_folder, utf8_console

STATE = REPO / "regulations/jurisdictions/new_york/new_york_state"
KEY = REPO / "test_data/answer_keys/new_york/new_york_state/houses.yaml"
DRAFTS = rules_folder(STATE) / "drafted/general.yaml"
HERE = Path(__file__).resolve().parents[1] / "evals/2026-11-13_house_egress"
REPORT, RESOLUTIONS = HERE / "comparison.md", HERE / "resolutions.yaml"
WORST = ("fail", "needs_review", "pass", "not_applicable")


def rules_of(path: Path) -> list[dict]:
    return [r for r in (load(path) or {}).get("rules", []) if isinstance(r, dict)] if path.is_file() else []


def groups(rules: list[dict], ctx) -> dict[tuple, list[dict]]:
    """{(piece, part kind): [rules]}: a rule is in the group of every piece its sources sit in. A flag counts too."""
    book = next(iter(ctx.verification.values()))
    out: dict[tuple, list[dict]] = {}
    for r in rules:
        for pid in dict.fromkeys(p for s in r.get("sources", []) for p in code_numbers.pieces_of(s, book)):
            out.setdefault((pid, r.get("for_each") or ""), []).append(r)
    return out


def verdicts(rules: list[dict], ex: dict, allowed: dict) -> dict[tuple, str]:
    """{(part id or "", the id of the part it sits in or ""): the worst result any of the rules gives it}."""
    out: dict[tuple, str] = {}
    for rule in rules:
        if not parts.is_part_rule(rule):
            continue
        for row in parts.rows(rule, ex.get("parts"), ex.get("given") or {}, allowed):
            key = (row["id"] or "", (row.get("within") or {}).get("id") or "")
            old = out.get(key)
            out[key] = row["outcome"] if old is None else min(old, row["outcome"], key=WORST.index)
    return out


def compare(key: list[dict], drafts: list[dict], ctx) -> list[dict]:
    """Every disagreement, each with a stable id: <piece>/<kind>/<whose example>/<rule id>#<n>/<part>."""
    allowed = ctx.allowed()
    k, d = groups(key, ctx), groups(drafts, ctx)
    out = []
    for group in sorted(set(k) | set(d)):
        pid, kind = group
        if group not in k or group not in d:
            side = "the answer key" if group in k else "the drafts"
            ids = sorted(r["id"] for r in (k.get(group) or d.get(group)))
            out.append({"id": f"{pid}/{kind}/only", "piece": pid, "kind": kind,
                        "what": f"only {side} has rules for {pid} for each {kind or 'building'}: {', '.join(ids)}"})
            continue
        for whose, rules in (("key", k[group]), ("draft", d[group])):
            for rule in rules:
                for n, ex in enumerate(rule.get("examples") or [], 1):
                    if not isinstance(ex.get("parts"), dict):
                        continue
                    a, b = verdicts(k[group], ex, allowed), verdicts(d[group], ex, allowed)
                    for part in sorted(set(a) | set(b)):
                        if a.get(part) != b.get(part):
                            label = part[0] or f"none in {part[1]}" if part[1] or part[0] else "the building"
                            out.append({"id": f"{pid}/{kind}/{whose}/{rule['id']}#{n}/{label}", "piece": pid,
                                        "kind": kind, "what": f"{whose} example {n} of {rule['id']}, {label}: "
                                        f"key {a.get(part, 'no row')}, drafts {b.get(part, 'no row')}"})
    return out


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
                         + (f": {' '.join(str(r.get('why', '')).split())}" if r else ""))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m rule_drafting.book_eval")
    parser.add_argument("--check", action="store_true", help="fail if comparison.md is out of date")
    args = parser.parse_args(argv)
    ctx = Context.for_jurisdiction(STATE)
    key, drafts = rules_of(KEY), rules_of(DRAFTS)
    found = compare(key, drafts, ctx)
    resolutions = (load(RESOLUTIONS) or {}) if RESOLUTIONS.is_file() else {}
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
