"""Runs Gordium on the stress test's designs and checks the invariants against the oracle.

    python packages/design_checker/tests/stress/harness.py --designs 5000 --workers 8 [--seed N] [--out file.json]

runs the long version (the CI sample is test_stress.py), in parallel, and writes every violation with its shrunk,
fewest-edits reproduction.

Gordium is run through its public entry points only: design_checker.check.check_site (a site as the Rhino command
sends it) and design_checker.check.check (a .3dm file). One thing is changed for speed: the city's own files (the
rulebook, the definitions, the extracted law, its sources) are read once and kept, instead of once per check
(`fast_reads`). They don't change during a run; test_stress.py checks one design both ways and requires identical
results.

The invariants (each violation names its invariant):
  a   never a false pass: Gordium says a rule complies, the oracle says it fails (or can't be met) under every
      reading.                                                                                    P0
  a2  the tax-map promise: on a lot not surveyed, Gordium says complies, but with the lot lines 2 ft closer it
      fails (and on the lot as drawn it passes under every reading).                             P1
  b   no false fail on a clear case: the oracle passes it under every reading by more than 0.5 ft (1% for
      coverage), Gordium says does not comply.                                                     P1
  c   monotonic: moving the house further into a yard never improves that yard's result; shrinking the house never
      worsens coverage.                                                                            P1
  d   the same design drawn differently (outlines reversed or starting elsewhere; feet, inches or millimeters;
      floor blocks, one solid or meshes) gives the same results.                                   P1
  e   live update: checking each edit in turn (the panel's 'before') ends with the same items as a fresh check of
      the final model; checking twice gives identical output.                                      P1
  f   every NEEDS REVIEW item says why; every DOES NOT COMPLY item names a number or a line; nothing crashes.  P2
"""

import argparse
import copy
import json
import math
import os
import random
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import generate  # noqa: E402
import oracle  # noqa: E402

FAILS, REVIEW, COMPLIES, NOT_CHECKED = "does_not_comply", "needs_review", "complies", "not_checked"
RANK = {FAILS: 0, REVIEW: 1, NOT_CHECKED: 2, COMPLIES: 3}
SEVERITY = {"a": "P0", "a2": "P1", "b": "P1", "c": "P1", "d": "P1", "e": "P1", "f": "P2", "crash": "P0"}
YARD_OF_LINE = {"street": ("R-1b.front_yard",), "side": ("R-1b.side_yards",), "rear": ("R-1b.rear_yard",)}


# ---- running Gordium --------------------------------------------------------------------------------------------

_RESTORE = []


def fast_reads():
    """Read the city's unchanging files once per run (see the module docstring). Idempotent; `slow_reads()` puts
    the real readers back (test_stress.py does, so no other test sees the kept copies)."""
    if _RESTORE:
        return
    import yaml
    from rule_format import rulebook

    real_load = yaml.load
    texts = {}

    def load(stream, Loader=None):
        if isinstance(stream, str) and len(stream) > 2000:          # a city file (kept by its text); a project is small
            key = (stream, Loader)
            if key not in texts:
                texts[key] = real_load(stream, Loader=Loader)
            return copy.deepcopy(texts[key])
        return real_load(stream, Loader=Loader)
    real_context = rulebook.Context.for_jurisdiction
    contexts = {}

    def for_jurisdiction(cls, j, use_cache=True):   # built once; nothing changes a Context after it is built
        # the same arguments as the real reader's (egress reads the state's sources with use_cache=False): a kept
        # copy that refused one made the state's rules "can't be read" on this path only
        key = (str(j), use_cache)
        if key not in contexts:
            contexts[key] = real_context.__func__(cls, j, use_cache=use_cache)
        return contexts[key]
    # (the zoning rulebook's checks are no longer run per check: they are frozen, rule_format/published.py)
    yaml.load = load
    rulebook.Context.for_jurisdiction = classmethod(for_jurisdiction)

    def restore():
        yaml.load = real_load
        rulebook.Context.for_jurisdiction = real_context
    _RESTORE.append(restore)


def slow_reads():
    while _RESTORE:
        _RESTORE.pop()()


def run_site(site, facts, extras=None):
    from design_checker.check import check_site
    return check_site(site, facts, extras=extras)


def gordium(design, order="as_drawn", extras=None):
    return run_site(generate.gordium_site(design, order), generate.gordium_facts(design), extras)


def gordium_file(design, units="ft", style="blocks"):
    from design_checker.check import check
    with tempfile.TemporaryDirectory() as tmp:
        path = generate.write_3dm(design, Path(tmp) / "design.3dm", units, style)
        return check(path, generate.gordium_facts(design))


def statuses(result) -> dict:
    """Each rule's status: the most cautious of its rows (side yards are two rows)."""
    out = {}
    for item in result["view"]["items"]:
        rule = item.get("rule")
        if rule in oracle.RULE_FUNCTIONS:
            s = item["status"]
            out[rule] = s if rule not in out or RANK[s] < RANK[out[rule]] else out[rule]
    return out


def items_by_rule(result) -> dict:
    out = {}
    for item in result["view"]["items"]:
        out.setdefault(item.get("rule"), []).append(item)
    return out


def comparable(result) -> list:
    """What the panel shows, as data: every item's name, status, numbers and reason."""
    keys = ("rule", "name", "status", "proposed", "required", "margin", "reason")
    return [{k: i.get(k) for k in keys} for i in result["view"]["items"]]


# ---- the invariants ---------------------------------------------------------------------------------------------

def _v(inv, rule, **detail):
    return {"invariant": inv, "severity": SEVERITY[inv], "rule": rule, **detail}


MARGIN = {"R-1b.lot_coverage": 0.01}


def check_answers(design, result) -> list:
    """Invariants a, a2, b and f on one checked design."""
    out = []
    got = statuses(result)
    want = oracle.verdicts(design)
    tol = oracle.verdicts(design, tolerance=True) if not design["lot"]["surveyed"] else None
    # PR #18 (5f7fc10, by design): a building across a lot line makes every rule that measures it not comply,
    # naming the building and the line. Those rows aren't false fails; they are counted, not reported.
    crossing = any(w == "crossing" for w in want["_measured"]["where"].values())
    by_rule = items_by_rule(result)
    for rule, g in got.items():
        o = want.get(rule)
        if o is None:
            continue
        if g == COMPLIES and o["verdict"] in (oracle.FAIL, oracle.NOT_PASS):
            out.append(_v("a", rule, gordium=g, oracle=o["verdict"], why=o["why"], slack=o["slack"]))
        if (tol and g == COMPLIES and o["verdict"] == oracle.PASS and tol[rule]["slack"] is not None
                and tol[rule]["slack"] < -oracle.EPS):
            out.append(_v("a2", rule, gordium=g, oracle="fails with the lot lines 2 ft closer",
                          slack=tol[rule]["slack"]))
        clear = MARGIN.get(rule, 0.5)
        named = crossing and all("crosses the" in (i.get("reason") or "") for i in by_rule.get(rule, [])
                                 if i["status"] == FAILS)
        if g == FAILS and o["verdict"] == oracle.PASS and o["slack"] is not None and o["slack"] > clear and \
                not named:
            out.append(_v("b", rule, gordium=g, oracle=o["verdict"], slack=o["slack"]))
    for item in result["view"]["items"]:
        if item.get("rule") not in oracle.RULE_FUNCTIONS:
            continue
        text = " ".join(str(item.get(k) or "") for k in ("proposed", "required", "margin", "reason"))
        if item["status"] == REVIEW and not (item.get("reason") or "").strip():
            out.append(_v("f", item["rule"], what="needs review with no reason", item=item["name"]))
        if item["status"] == FAILS and not (any(c.isdigit() for c in text) or "line" in text):
            out.append(_v("f", item["rule"], what="does not comply naming no number or line", item=item["name"]))
    return out


def _toward(design, line, step):
    """The design with the house moved `step` ft toward lot line `line` (along its outward normal)."""
    pts = design["lot"]["points"]
    _, _, (nx, ny) = generate._face([list(p) for p in pts], line)
    return generate.apply(design, {"op": "move_house", "dx": nx * step, "dy": ny * step})


def _kind_of_line(lt, line):
    pts = lt["points"]
    seg = sorted([list(pts[line]), list(pts[(line + 1) % len(pts)])])
    for kind, segs in (("street", lt["streets"]), ("rear", lt["rears"]),
                       ("side", [s for v in lt["sides"].values() for s in v])):
        if any(sorted(map(list, s)) == seg for s in segs):
            return kind
    return None


def _yard_value(design, rule):
    """The oracle's yard for a rule, to the walls (best) and to everything (worst)."""
    y = oracle.measure(design)["yards"]
    key = {"R-1b.front_yard": "front", "R-1b.side_yards": "side", "R-1b.rear_yard": "rear"}[rule]
    return y[key]


def _grouping(design):
    """Which parts make the main building and which stand apart (or within reach of it): a move that joins or
    separates a building changes what is measured, so monotonic checks compare only moves that keep this."""
    main, detached = oracle.main_and_detached(design)
    house = oracle._union(main)
    return (sorted(p["id"] for p in main),
            sorted((sorted(p["id"] for p in g), oracle._union(g).distance(house) <= oracle.NEAR) for g in detached))


def check_monotonic(design, result, probe) -> list:
    """Invariant c: the house moved toward one lot line (it stays on the lot, and the oracle's yard for that rule
    gets no larger: moving toward the east line also moves away from the west one, so only the smaller side
    counts); and the house shrunk by pulling one face in."""
    out = []
    lt = design["lot"]
    line = probe["line"] % len(lt["points"])
    kind = _kind_of_line(lt, line)
    moved = _toward(design, line, probe["step"])
    if kind and moved and oracle.measure(moved)["where"]["main"] == "inside" and \
            oracle.measure(design)["where"]["main"] == "inside" and _grouping(moved) == _grouping(design):
        before, after = statuses(result), statuses(gordium(moved))
        for rule in YARD_OF_LINE[kind]:
            closer = all(b <= a + 1e-9 for a, b in zip(_yard_value(design, rule), _yard_value(moved, rule)))
            if closer and rule in before and rule in after and RANK[after[rule]] > RANK[before[rule]]:
                out.append(_v("c", rule, what=f"moved {probe['step']} ft toward the {kind} line {line}, the yard "
                              "result improved", before=before[rule], after=after[rule]))
    shrunk = generate.apply(design, {"op": "stretch", "face": probe["face"], "amount": -probe["shrink"]})
    if shrunk:
        before, after = statuses(result), statuses(gordium(shrunk))
        rule = "R-1b.lot_coverage"
        if rule in before and rule in after and RANK[after[rule]] < RANK[before[rule]]:
            out.append(_v("c", rule, what=f"face {probe['face']} pulled in {probe['shrink']} ft, coverage got worse",
                          before=before[rule], after=after[rule]))
    return out


def _same_status(a, b, rules=None):
    sa, sb = statuses(a), statuses(b)
    rules = rules or sorted(set(sa) | set(sb))
    return {r: (sa.get(r), sb.get(r)) for r in rules if sa.get(r) != sb.get(r)}


def check_drawings(design, result, files=True) -> list:
    """Invariant d."""
    out = []
    for order in ("reversed", "shifted"):
        other = gordium(design, order)
        diff = [(a, b) for a, b in zip(comparable(result), comparable(other)) if a != b]
        if diff or len(comparable(result)) != len(comparable(other)):
            out.append(_v("d", diff[0][0]["rule"] if diff else None, what=f"outlines drawn {order}",
                          before=diff[0][0] if diff else None, after=diff[0][1] if diff else None))
    if not files:
        return out
    ft = gordium_file(design, "ft")
    base = statuses(ft)
    for units in ("in", "mm"):
        diff = _same_status(ft, gordium_file(design, units))
        if diff:
            rule = sorted(diff)[0]
            out.append(_v("d", rule, what=f"drawn in {units} instead of ft", before=diff[rule][0],
                          after=diff[rule][1]))
    for style in ("mesh", "one_solid"):
        try:
            other = gordium_file(design, "ft", style)
        except ValueError:
            continue                                   # one solid only when the floors share one outline
        so = statuses(other)
        # drawn without floor marks Gordium knows less, so it may need review where the floor blocks gave an answer;
        # it must never give the other answer (complies for does not comply, or the reverse)
        for rule in sorted(set(base) | set(so)):
            a, b = base.get(rule), so.get(rule)
            if rule == "R-1b.stories" and design.get("typed_stories") is not None:
                continue        # drawn without floor blocks, a typed count is the whole building's statement (the
                # agreed rule): with the blocks drawn the floors are counted instead, so the two may differ
            if a in (COMPLIES, FAILS) and b in (COMPLIES, FAILS) and a != b:
                out.append(_v("d", rule, what=f"drawn as {style} instead of floor blocks", before=a, after=b))
    if statuses(result) != base:
        diff = _same_status(result, ft)
        rule = sorted(diff)[0]
        out.append(_v("d", rule, what="sent as faces vs read from a .3dm", before=diff[rule][0], after=diff[rule][1]))
    return out


def check_live(case, design, result) -> list:
    """Invariant e: each step checked with the panel's 'before' ends where a fresh check ends; twice is the same."""
    out = []
    d = generate.starting_design(case["lot"])
    before = None
    last = None
    for e in case["edits"]:
        nxt = generate.apply(d, e)
        if nxt is None:
            continue
        d = nxt
        last = gordium(d, extras={"before": before} if before is not None else None)
        before = last["statuses"]
    if last is not None and comparable(last) != comparable(result):
        diff = [(a, b) for a, b in zip(comparable(last), comparable(result)) if a != b]
        out.append(_v("e", diff[0][0]["rule"] if diff else None, what="after live edits vs fresh check",
                      before=diff[0][0] if diff else None, after=diff[0][1] if diff else None))
    again = gordium(design)
    a = json.dumps(_strip(result), sort_keys=True, default=str)
    b = json.dumps(_strip(again), sort_keys=True, default=str)
    if a != b:
        out.append(_v("e", None, what="checking the same design twice gave different output"))
    return out


def _strip(result):
    return {k: v for k, v in result.items() if k not in ("notice",)}


# ---- one case, all invariants ------------------------------------------------------------------------------------

def run_case(case, deep=None) -> dict:
    """Builds the case's design, checks it, and runs every invariant: a, b and f always; c, d (with or without
    Rhino files) and e as the case says (`deep`), each on a share of the cases."""
    design, done = generate.build(case["lot"], case["edits"])
    deep = deep if deep is not None else case["deep"]
    case = {**case, "edits": done}
    out = {"case": case, "violations": [], "checks": {k: False for k in ("a", "b", "c", "d", "e", "f")}}
    try:
        result = gordium(design)
    except Exception as ex:                                   # noqa: BLE001  (a crash is a finding)
        out["violations"].append(_v("crash", None, what=f"{type(ex).__name__}: {ex}",
                                    trace=traceback.format_exc(limit=3), lot=case["lot"]))
        return out
    out["oracle"] = {k: v["verdict"] for k, v in oracle.verdicts(design).items() if k != "_measured"}
    out["gordium"] = statuses(result)
    out["violations"] += check_answers(design, result)
    out["checks"].update(a=True, b=True, f=True)
    try:
        if deep.get("c"):
            out["violations"] += check_monotonic(design, result, case["probe"])
            out["checks"]["c"] = True
        if deep.get("d") or deep.get("d_files"):
            out["violations"] += check_drawings(design, result, files=deep.get("d_files"))
            out["checks"]["d"] = True
        if deep.get("e"):
            out["violations"] += check_live(case, design, result)
            out["checks"]["e"] = True
    except Exception as ex:                                   # noqa: BLE001
        out["violations"].append(_v("crash", None, what=f"{type(ex).__name__}: {ex}",
                                    trace=traceback.format_exc(limit=3)))
    for v in out["violations"]:
        v.setdefault("lot", case["lot"])
    return out


def signature(v) -> tuple:
    what = v.get("what", "")[:40] if v["invariant"] in ("c", "d", "e", "f", "crash") else ""
    return v["invariant"], v["rule"], v.get("lot"), what


def still_fails(case, v, deep) -> bool:
    res = run_case(case, deep)
    return any(signature(w) == signature(v) for w in res["violations"])


def shrink(case, v) -> dict:
    """The fewest edits that still give the same violation (greedy: drop one edit at a time while it still fails)."""
    deep = {"c": v["invariant"] == "c", "d": v["invariant"] == "d", "d_files": v["invariant"] == "d",
            "e": v["invariant"] == "e"}
    if v["invariant"] in ("c", "d", "e") and not still_fails(case, v, deep):
        return case                                    # depends on the random move or shrink; keep as found
    edits = list(case["edits"])
    changed = True
    while changed:
        changed = False
        for k in range(len(edits)):
            trial = {**case, "edits": edits[:k] + edits[k + 1:]}
            if still_fails(trial, v, deep):
                edits = trial["edits"]
                changed = True
                break
    return {**case, "edits": edits}


def run(designs, seed, workers=1, shrink_each=True, known=None) -> dict:
    """Runs `designs` random cases from `seed`. Returns the counts and every distinct violation, shrunk.
    `known(violation)` names the known finding a violation is (or None). It is asked of EVERY violation before any
    are merged, and violations are merged only with ones it names the same, so a new bug is never folded into a
    known finding's entry (each kept violation carries its "known" name)."""
    fast_reads()
    rng = random.Random(seed)
    cases = [generate.random_case(rng) for _ in range(designs)]
    t = time.time()
    if workers > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(workers, initializer=fast_reads) as pool:
            results = pool.map(_one, cases, chunksize=8)
    else:
        results = [_one(c) for c in cases]
    counts = {k: 0 for k in ("a", "b", "c", "d", "e", "f")}
    found = {}
    for res in results:
        for k, ran in res["checks"].items():
            counts[k] += bool(ran)
        for v in res["violations"]:
            name = known({**v, "case": res["case"]}) if known else None
            found.setdefault((signature(v), name), (v, res["case"], name))
    shrunk = []
    for _, (v, case, name) in sorted(found.items(), key=lambda kv: str(kv[0])):
        small = shrink(case, v) if shrink_each else case
        shrunk.append({**v, "case": small, "found_in": case, "known": name})
    agree = _agreement(results)
    return {"designs": designs, "seed": seed, "seconds": round(time.time() - t, 1), "checks_run": counts,
            "violations": shrunk, "violating_designs": sum(1 for r in results if r["violations"]),
            "agreement": agree, "undecided": _undecided(results)}


def _one(case):
    return run_case(case)


def _agreement(results):
    """How often Gordium and the oracle agree, per rule (the oracle's verdict -> Gordium's status -> count)."""
    out = {}
    for res in results:
        for rule, g in (res.get("gordium") or {}).items():
            o = (res.get("oracle") or {}).get(rule)
            key = f"{o} -> {g}"
            out.setdefault(rule, {}).setdefault(key, 0)
            out[rule][key] += 1
    return out


def _undecided(results):
    out = {}
    for res in results:
        for rule, o in (res.get("oracle") or {}).items():
            if o == oracle.UNDECIDED:
                out[rule] = out.get(rule, 0) + 1
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--designs", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20261020)
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--out", default=None)
    p.add_argument("--no-shrink", action="store_true")
    a = p.parse_args(argv)
    out = run(a.designs, a.seed, a.workers, shrink_each=not a.no_shrink)
    text = json.dumps(out, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("designs", "seed", "seconds", "checks_run", "violating_designs",
                                          "undecided")}, indent=1))
    for v in out["violations"]:
        print(v["severity"], v["invariant"], v["rule"], v.get("what") or "", v.get("gordium") or "",
              v.get("oracle") or "", v["lot"], json.dumps(v["case"]["edits"]))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE.parents[1] / "tests"))
    main()
