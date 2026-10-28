"""Shows one case side by side: what the oracle measured and decided, and what Gordium said, for the rules named.

    python packages/design_checker/tests/stress/explain.py '<lot>' '<edits as JSON>' [rule ...]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate  # noqa: E402
import harness  # noqa: E402
import oracle  # noqa: E402


def explain(lot, edits, rules=()):
    harness.fast_reads()
    design, done = generate.build(lot, edits)
    print("edits applied:", json.dumps(done))
    for p in design["parts"]:
        print("  part", p["id"], p["kind"], p["group"], [[round(x, 3), round(y, 3)] for x, y in
                                                       p.get("outline") or p.get("corners")],
              {k: p[k] for k in ("z0", "z1", "base", "ridge", "over", "fascia", "inset") if k in p})
    print("  listed", design["listed"], "frame", design["frame"], "grade_is", design["grade_is"])
    v = oracle.verdicts(design)
    m = v.pop("_measured")
    print("oracle measured:", json.dumps({k: m[k] for k in m}, default=str))
    res = harness.gordium(design)
    by = harness.items_by_rule(res)
    for rule in rules or oracle.RULES:
        print("\n", rule, "oracle:", v[rule])
        for i in by.get(rule, []):
            print("   gordium:", i["name"], "|", i["status"], "|", i["proposed"], "|", i.get("required"), "|",
                  i.get("reason"))
    names = sorted({n for rule in (rules or oracle.RULES) for n in _names(rule)})
    for n in names:
        mm = res["measurements"].get(n)
        if mm:
            print("   measured", n, mm.get("value"), [(r.get("named"), r.get("value")) for r in mm.get("readings") or []],
                  (mm.get("reason") or "")[:200])
    return design, res


def _names(rule):
    from rule_format import formula
    from rule_format.rulebook import REPO, load, rulebook_for
    rules = load(rulebook_for(REPO / generate.JURISDICTION, "R-1b"))["rules"]
    r = next(x for x in rules if x["id"] == rule)
    return formula.names(r["check"]) | (formula.names(r["applies_when"]) if r.get("applies_when") else set())


if __name__ == "__main__":
    explain(sys.argv[1], json.loads(sys.argv[2]), sys.argv[3:])
