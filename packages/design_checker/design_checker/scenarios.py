"""The hand-worked scenarios (test_data/test_sites/new_york/ithaca_city/scenarios/; hand-worked by Claude before Gordium ran, not yet verified by an architect):
each scenario built as a site, checked, and compared with the result worked out by hand. The expected results are never changed to match
Gordium; a disagreement is investigated (a code fix, or a question for the architects).

    python -m design_checker.scenarios               the table: scenario · expected · Gordium · match
    python -m design_checker.scenarios dump <yaml>   the scenario as JSON (lot, solids, facts), for the Rhino test

A scenario is built the way an architect draws it in Rhino: the lot as one closed outline, the street along its
first edge, each story its own floor block (marked with the height it was drawn, as GordiumStart marks them),
solids that aren't on the Building layer left out of the site and listed as not included."""

import json
import sys
from pathlib import Path

import yaml

from design_checker import present
from rule_format.rulebook import REPO, utf8_console

FOLDER = REPO / "test_data/test_sites/new_york/ithaca_city/scenarios"
JURISDICTION = "regulations/jurisdictions/new_york/ithaca_city"
# the most cautious status a rule's rows give is the rule's status
CAUTION = {present.FAILS: 3, present.REVIEW: 2, present.NOT_CHECKED: 1, present.COMPLIES: 0}
TOUCH = 0.1                     # ft: a left-out solid this close to the building may be part of it


def paths() -> list[Path]:
    return sorted(FOLDER.glob("*.yaml"))


def load(path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _prism(outline, z0, z1, id_, floor=None) -> dict:
    n = len(outline)
    walls = [{"points": [[*outline[i], z0], [*outline[(i + 1) % n], z0], [*outline[(i + 1) % n], z1], [*outline[i], z1]]}
             for i in range(n)]
    out = {"id": id_, "faces": [{"points": [[x, y, z0] for x, y in outline]},
                                {"points": [[x, y, z1] for x, y in outline]}, *walls], "problems": []}
    if floor is not None:
        out["floor"] = floor
    return out


def solids(scenario: dict, moved: bool = False) -> dict:
    """{"buildings": [...], "others": [...]}: each solid as {id, outline, base, top, floor (height drawn, for a
    floor block), name}, in feet, after the scenario's edit if `moved`."""
    dx, dy = (scenario.get("then") or {}).get("move", [0, 0]) if moved else (0, 0)
    out = {"buildings": [], "others": []}
    for b in scenario.get("buildings") or []:
        z = b.get("base", 0)
        shift = b.get("move_floor") or {}
        for k, h in enumerate(b.get("floors") or [b["top"] - z]):
            fx, fy = shift.get("by", [0, 0]) if shift.get("floor") == k + 1 else (0, 0)
            outline = [[x + dx + fx, y + dy + fy] for x, y in b["outline"]]
            out["buildings"].append({"id": f"{b['id']}_floor{k + 1}" if b.get("floors") else b["id"],
                                     "outline": outline, "base": z, "top": z + h,
                                     "floor": h if b.get("floors") else None, "name": f"Floor {k + 1}"})
            z += h
    for o in scenario.get("others") or []:
        out["others"].append({"id": o["id"], "outline": [[x + dx, y + dy] for x, y in o["outline"]],
                              "base": o.get("base", 0), "top": o["top"], "floor": None, "name": o["id"]})
    return out


def facts(scenario: dict) -> dict:
    pts = scenario["lot"]["points"]
    out = {"jurisdiction": JURISDICTION, "zone": "R-1b", "use": "one_family_detached", "corner_lot": False,
           "street_line": [[list(pts[0]), list(pts[1])]], "lot_surveyed": scenario["lot"]["surveyed"]}
    grade = scenario.get("grade") or {}
    if "elevation" in grade:
        out.update(ground_is_flat=True, grade_elevation=grade["elevation"])
    elif grade.get("points"):
        out.update(grade_from="spot", grade_points=[list(p) for p in grade["points"]])
    return out


def site(scenario: dict, moved: bool = False) -> tuple[dict, dict, dict]:
    """(site, facts, extras) for the checker: the same thing the Rhino command sends for this drawing."""
    pts = scenario["lot"]["points"]
    n = len(pts)
    lot = {"id": "lot", "edges": [{"points": [list(pts[i]), list(pts[(i + 1) % n])], "curved": False}
                                  for i in range(n)]}
    s = solids(scenario, moved)
    buildings = [_prism(b["outline"], b["base"], b["top"], b["id"], b["floor"]) for b in s["buildings"]]
    extras = {}
    if s["others"]:                     # left out, as the Rhino command finds them, and which touch the building
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        house = unary_union([Polygon(b["outline"]) for b in s["buildings"]])
        extras = {"not_included": [o["id"] for o in s["others"]],
                  "touching": [o["id"] for o in s["others"] if Polygon(o["outline"]).distance(house) <= TOUCH]}
    return {"units": "ft", "lot": lot, "buildings": buildings, "problems": []}, facts(scenario), extras


def rule_rows(view: dict, key: str) -> list[dict]:
    return [i for i in view["items"] if i.get("rule") == key or i.get("id") == key]


def compare(view: dict, plan: dict | None, expected: dict, expected_plan: dict | None = None) -> list[dict]:
    """One row per expected rule: {rule, expected, gordium, match, why}. A rule's status is the most cautious of
    its rows. `match` needs the status and every detail written down (at limit, margin, proposed, required, the
    reason's words, a measured value) to agree."""
    out = []
    for key, want in expected.items():
        rows = rule_rows(view, key)
        if not rows:
            out.append({"rule": key, "expected": want["status"], "gordium": "(no row)", "match": False,
                        "why": "Gordium shows no row for it"})
            continue
        worst = max(rows, key=lambda i: CAUTION[i["status"]])
        got, problems = worst["status"], []
        if got != want["status"]:
            problems.append(f"status {got}")
        if want.get("at_limit") is not None and any(bool(i["detail"].get("at_limit")) for i in rows) != want["at_limit"]:
            problems.append("at limit " + ("not shown" if want["at_limit"] else "shown"))
        for field in ("margin", "proposed", "required"):
            if field in want and worst.get(field) != want[field]:
                problems.append(f"{field} {worst.get(field)!r}, expected {want[field]!r}")
        if want.get("reason_has") and not any(want["reason_has"].lower() in (i.get("reason") or "").lower() for i in rows):
            problems.append("reason: " + "; ".join(i.get("reason") or "" for i in rows)[:160])
        out.append({"rule": key, "expected": want["status"], "gordium": got, "match": not problems,
                    "why": "; ".join(problems), "reason": worst.get("reason") or ""})
    if expected_plan and plan is not None:
        got = plan.get("encroach") or []
        ok = len(got) == expected_plan.get("encroach", len(got)) and (
            "encroach_why" not in expected_plan or sorted(e["why"] for e in got) == sorted(expected_plan["encroach_why"]))
        out.append({"rule": "red in the viewport", "expected": f"{expected_plan.get('encroach')} "
                    f"{'/'.join(expected_plan.get('encroach_why') or [])}".strip(),
                    "gordium": f"{len(got)} {'/'.join(e['why'] for e in got)}".strip(), "match": ok, "why": "",
                    "reason": ""})
    return out


def run(scenario: dict) -> list[dict]:
    """Every step of a scenario (as drawn, then after its edit), checked in code: [{step, rows}]."""
    from design_checker.check import check_site
    steps = []
    for moved, expected, step in [(False, scenario["expected"], "as drawn"),
                                  (True, (scenario.get("then") or {}).get("expected"), "after the edit")]:
        if not expected:
            continue
        s, f, extras = site(scenario, moved)
        r = check_site(s, f, extras=extras)
        steps.append({"step": step, "rows": compare(r["view"], r["plan"], expected,
                                                    scenario.get("plan") if not moved else None)})
    return steps


def table(results: dict) -> str:
    """scenario · rule · expected · Gordium · match, one line per rule."""
    lines = ["| Scenario | Step | Rule | Expected | Gordium | Match |", "|---|---|---|---|---|---|"]
    for name, steps in results.items():
        for st in steps:
            for r in st["rows"]:
                mark = "✓" if r["match"] else "✕ " + r["why"]
                lines.append(f"| {name} | {st['step']} | {r['rule']} | {r['expected']} | {r['gordium']} | {mark} |")
    return "\n".join(lines)


def steps_expected(scenario: dict) -> list[str]:
    """The steps a scenario must have results for: as drawn, and after its edit if it has one."""
    return ["as drawn"] + (["after the edit"] if (scenario.get("then") or {}).get("expected") else [])


def failures(results: dict, scenarios_: dict, trace: str | None = None) -> list[str]:
    """Why a comparison run fails, or [] when it passes: a crash (a trace), a scenario or step with no result, or
    any disagreement the scenario doesn't list as investigated (with the same Gordium answer). A listed
    disagreement is allowed and counted apart."""
    out = [f"the run crashed: {trace.strip().splitlines()[-1] if trace.strip() else 'trace'}"] if trace else []
    for name, sc in scenarios_.items():
        got = {st["step"]: st for st in results.get(name) or []}
        out += [f"{name}: no result for '{step}'" for step in steps_expected(sc) if step not in got]
        known = sc.get("disagreements") or {}
        for st in got.values():
            if not st["rows"]:
                out.append(f"{name} {st['step']}: no rows")
            for r in st["rows"]:
                if not r["match"] and (known.get(r["rule"]) or {}).get("gordium") != r["gordium"]:
                    out.append(f"{name} {st['step']}: {r['rule']} expected {r['expected']}, Gordium {r['gordium']}")
    return out


def main(argv):
    """Prints the table; exits 1 (with every reason) on a crash, a missing scenario or step, or any
    disagreement not already investigated; 0 only when the run is complete and agrees."""
    if argv[:1] == ["dump"]:
        sc = load(argv[1])
        print(json.dumps({"scenario": sc, "solids": solids(sc), "moved": solids(sc, True) if sc.get("then") else None,
                          "facts": facts(sc)}))
        return 0
    every = {p.stem: load(p) for p in paths()}
    trace = None
    if argv[:1] == ["rhino"]:               # the Rhino run's views, judged by the same comparison
        ran = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        trace = ran.get("trace")
        if trace:
            print(trace)
        results = {}
        for name, sc in every.items():
            steps = []
            for st in (ran.get("scenarios") or {}).get(name) or []:
                moved = st["step"] != "as drawn"
                expected = (sc.get("then") or {}).get("expected") if moved else sc["expected"]
                if st.get("view") is None:
                    steps.append({"step": st["step"], "rows": [{"rule": "(check)", "expected": "runs",
                                  "gordium": "error: " + str(st.get("error")), "match": False, "why": ""}]})
                    continue
                steps.append({"step": st["step"], "rows": compare(st["view"], st.get("plan"), expected,
                                                                  None if moved else sc.get("plan"))})
            results[name] = steps
    else:
        results = {name: run(sc) for name, sc in every.items()}
    print(table(results))
    known = sum(1 for name, steps in results.items() for st in steps for r in st["rows"]
                if not r["match"] and r["rule"] in (every[name].get("disagreements") or {}))
    bad = failures(results, every, trace)
    print(f"\n{known} investigated disagreement(s) (listed in the scenarios)")
    if bad:
        print(f"FAILED: {len(bad)} problem(s)")
        for b in bad:
            print("  " + b)
        return 1
    print("OK: every scenario and step ran and agrees")
    return 0


if __name__ == "__main__":
    utf8_console()
    sys.exit(main(sys.argv[1:]))
