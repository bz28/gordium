"""Compare the AI-drafted rules with every hand answer key, rule by rule (queue item 11, 2026-10-27). Plain code, no AI.

For each hand key rule: the drafted rules that answer the same question (evals/2026-10-20_stage1/hand_to_drafted.yaml,
reviewed from the law), how its worked examples come out (graded as the checker reads the drafts: tests/test_eval.py
grade_hand_key), and what differs: numbers, conditions (applicability), citations, kind. Each rule is one of
  match            every example agrees
  verdict          a drafted verdict that isn't only more cautious (pass/fail swapped, a fail where the key reviews,
                   a verdict where the key says it doesn't apply): each needs a law decision (decisions.yaml)
  cautious         the drafts say "needs review" where the key decides: grouped by cause, the drafter's to-do list
  missing          nothing drafted answers it
and the drafted rules no key asks. Writes report.md and compare.json next to this file.

    python packages/rule_drafting/evals/2026-10-27_rule_by_rule/compare.py <drafts commit> <keys commit>

Run from the repository root of a checkout holding both the drafts (PR #21) and every hand key (PR #20/#24/#30)."""

import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from rule_format import formula
from rule_format.rulebook import MEASURE_KINDS, load, outcome

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("test_eval", Path.cwd() / "packages/rule_drafting/tests/test_eval.py")
te = importlib.util.module_from_spec(spec)
spec.loader.exec_module(te)
from rule_format.rulebook import Context  # noqa: E402

CAUTIOUS = "needs_review"
DECISIONS = HERE / "decisions.yaml"


def kind_of(expect: str, got: str) -> str:
    """A disagreement's kind: cautious when the drafts only say "needs review" where the key decides (or doesn't apply)."""
    return "cautious" if got == CAUTIOUS else "verdict"


def _numbers(rules) -> list[float]:
    out = set()
    for r in rules:
        for t in [r.get("applies_when"), r.get("check")] + [w["when"] for w in r.get("review_when") or []]:
            if t:
                out |= set(formula.numbers(t))
    return sorted(out)


def _pages(rules) -> list[str]:
    return sorted({f"{'chart' if 'chart' in (s.get('file') or '') else 'ch.325'} p.{s.get('page')}"
                   for r in rules for s in r.get("sources") or [] if s.get("page")})


def cause(rule: dict, given: dict, ctx) -> str:
    """Why one drafted rule says "needs review" on an example: the drafter's to-do, in its words."""
    if rule.get("kind") == "flag":
        return "drafted as a flag (always needs review): draft a check"
    kinds = MEASURE_KINDS | {k: v if isinstance(v, str) else frozenset(v) for k, v in ctx.allowed().items()}
    for w in rule.get("review_when") or []:        # read as the checker reads them (outcome: the uses described too)
        try:
            if formula.evaluate(w["when"], given, kinds) is True:
                why = (w.get("reason") or "").split(". ")[0]
                if "as the AI drafted it" in (w.get("reason") or ""):
                    return "an exception not proven yet (complies only through it as drafted): prove it"
                return f"a review condition fires: {why}"
        except Exception:                       # unknown inputs: not this one's cause
            continue
    names = set()
    for t in [rule.get("applies_when"), rule.get("check")] + [w["when"] for w in rule.get("review_when") or []]:
        if t:
            names |= formula.names(t)
    missing = sorted(n for n in names - set(given) - {"district"})
    if missing:
        return "reads an input the key's example doesn't give: " + ", ".join(missing)
    return "the formula can't settle it on these inputs (three-valued logic)"


def compare(ctx) -> dict:
    mapping = te.mapping()
    out = {"keys": {}, "general_unmatched": sorted(mapping.get("general_unmatched") or {})}
    for path in te.hand_keys():
        book = load(path)
        district = book["district"]
        entries = mapping["keys"].get(path.name, {})
        drafted = {r["id"]: r for r in te.drafted_as_checked(district)}
        g = te.grade_hand_key(path, ctx)
        per = defaultdict(lambda: {"agree": 0, "disagree": [], "undrafted": 0})
        for x in g["agree"]:
            per[x["hand"]]["agree"] += 1
        for x in g["disagree"]:
            per[x["hand"]]["disagree"].append(x)
        for x in g["undrafted"]:
            per[x["hand"]]["undrafted"] += 1
        rules = []
        for h in book["rules"]:
            e = entries.get("rules", {}).get(h["id"], {})
            ids = [i for u in e.get("judge") or [] for i in u] + list(e.get("parts") or [])
            mine = [drafted[i] for i in ids if i in drafted]
            p = per[h["id"]]
            kinds = Counter(kind_of(x["expect"], x["got"]) for x in p["disagree"])
            status = ("missing" if not ids else "verdict" if kinds["verdict"] else "cautious" if kinds["cautious"]
                      else "match")
            causes = Counter()
            for x in p["disagree"]:
                if kind_of(x["expect"], x["got"]) != "cautious":
                    continue
                given = {"district": district} | x["given"]
                said = {cause(r, given, ctx) for r in mine if outcome(r, given, ctx.allowed()) == CAUTIOUS}
                causes.update(said or {"the rules together can't settle it"})   # each example once per cause
            rules.append({
                "hand": h["id"], "status": status, "drafted": ids, "examples": p["agree"] + len(p["disagree"]) + p["undrafted"],
                "agree": p["agree"], "disagree": [{"given": x["given"], "key": x["expect"], "drafts": x["got"]}
                                                   for x in p["disagree"]],
                "why_undrafted": e.get("reason") if not ids else None,
                "numbers": {"key": _numbers([h]), "drafts": _numbers(mine)},
                "cited": {"key": _pages([h]), "drafts": _pages(mine)},
                "kind": {"key": h.get("kind"), "drafts": sorted({r.get("kind") for r in mine})},
                "applies": {"key": h.get("applies_when"), "drafts": [r.get("applies_when") for r in mine if r.get("applies_when")]},
                "causes": dict(sorted(causes.items()))})
        out["keys"][path.name] = {"district": district, "rules": rules,
                                  "unmatched": sorted(entries.get("unmatched") or {}),
                                  "summary": g.get("summary") or {k: len(g[k]) if isinstance(g[k], list) else g[k]
                                                                  for k in ("total", "agree", "disagree", "undrafted",
                                                                            "false_pass")}}
    return out


def report(data: dict, drafts: str, keys: str, decisions: dict) -> str:
    lines = ["# Drafts against the hand answer keys, rule by rule", "",
             f"Drafts: PR #21 (drafting-stage1) at `{drafts}`. Hand keys: PR #20, #24 and #30 (r3-hand) at `{keys}`,",
             "merged into one checkout. Graded as the checker reads the drafts (tests/test_eval.py grade_hand_key: an",
             "exception composed into the rule it relaxes, an AI one widening only once proven). Generated by",
             "`compare.py`; never edited by hand. Law decisions: `decisions.yaml`.", ""]
    count = Counter(r["status"] for k in data["keys"].values() for r in k["rules"])
    lines += ["## Summary", "", "| District | Key rules | Match | Cautious | Verdict | Missing | Examples agreeing | False passes |",
              "|---|---|---|---|---|---|---|---|"]
    for name, k in data["keys"].items():
        c = Counter(r["status"] for r in k["rules"])
        ex = sum(r["examples"] for r in k["rules"])
        ag = sum(r["agree"] for r in k["rules"])
        lines.append(f"| {k['district']} | {len(k['rules'])} | {c['match']} | {c['cautious']} | {c['verdict']} | "
                     f"{c['missing']} | {ag}/{ex} | {k['summary'].get('false_pass', 0)} |")
    lines += ["", f"All keys: {count['match']} match, {count['cautious']} cautious, {count['verdict']} verdict, "
              f"{count['missing']} missing.", ""]
    lines += ["## Verdict differences, decided by the law", ""]
    for name, k in data["keys"].items():
        for r in (r for r in k["rules"] if r["status"] == "verdict"):
            d = decisions.get(r["hand"]) or {}
            ex = ", ".join(f"{x['given']} key {x['key']}, drafts {x['drafts']}" for x in r["disagree"]
                           if kind_of(x["key"], x["drafts"]) == "verdict")
            lines += [f"### {r['hand']}", f"- Examples: {ex}", f"- Drafted: {', '.join(r['drafted'])}",
                      f"- **Law:** {d.get('law', 'NOT DECIDED')}", f"- **Matches the law:** {d.get('side', 'NOT DECIDED')}",
                      f"- **Done:** {d.get('done', 'NOT DECIDED')}", ""]
    lines += ["## Cautious differences, by cause (the drafter's to-do list)", "",
              "The drafts say \"needs review\" where the key decides: never a false pass, but each is a check the "
              "drafts could make. Counted in examples (an example two drafted rules hold back for two different causes "
              "counts under each, once); the rules under each cause follow.", ""]
    by_cause = defaultdict(lambda: [0, set()])
    for k in data["keys"].values():
        for r in k["rules"]:
            for c, n in r["causes"].items():        # each review condition under its own reason (the to-do)
                by_cause[c][0] += n
                by_cause[c][1].add(r["hand"])
    for c, (n, hands) in sorted(by_cause.items(), key=lambda kv: (-kv[1][0], kv[0])):   # ties by name: stable
        lines += [f"- **{c}** — {n} examples: {', '.join(sorted(hands))}"]
    lines += ["", "## Missing from the drafts (no drafted rule answers the key's question)", ""]
    for k in data["keys"].values():
        for r in (r for r in k["rules"] if r["status"] == "missing"):
            lines.append(f"- {r['hand']} ({r['examples']} examples): {r['why_undrafted']}")
    lines += ["", "## Drafted rules no key asks", ""]
    for k in data["keys"].values():
        if k["unmatched"]:
            lines.append(f"- {k['district']}: {', '.join(k['unmatched'])}")
    lines.append(f"- every district (general.yaml): {', '.join(data['general_unmatched'])}")
    lines += ["", "## Rule by rule", "",
              "| Key rule | Status | Drafted | Agree | Numbers key / drafts | Cited key / drafts |", "|---|---|---|---|---|---|"]
    for k in data["keys"].values():
        for r in k["rules"]:
            nums = f"{_short(r['numbers']['key'])} / {_short(r['numbers']['drafts'])}"
            cited = f"{', '.join(r['cited']['key'])} / {', '.join(r['cited']['drafts'])}"
            lines.append(f"| {r['hand']} | {r['status']} | {', '.join(r['drafted']) or '—'} | "
                         f"{r['agree']}/{r['examples']} | {nums} | {cited} |")
    return "\n".join(lines) + "\n"


def _short(xs):
    return ", ".join(f"{x:g}" for x in xs[:8]) + (" …" if len(xs) > 8 else "") if xs else "—"


def main(argv):
    drafts, keys = argv
    ctx = Context.for_jurisdiction(te.ITHACA)
    data = compare(ctx)
    decisions = load(DECISIONS) if DECISIONS.exists() else {}
    (HERE / "compare.json").write_text(json.dumps(data, indent=1, default=str) + "\n", encoding="utf-8")
    (HERE / "report.md").write_text(report(data, drafts, keys, decisions or {}), encoding="utf-8")
    print("wrote", HERE / "report.md")


if __name__ == "__main__":
    main(sys.argv[1:])
