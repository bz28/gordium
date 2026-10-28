"""Shows how one case's results change with the way it is drawn.

    python packages/design_checker/tests/stress/compare.py '<lot>' '<edits as JSON>' <way> [rule ...]

way: reversed | shifted (outline order), in | mm (units, from a .3dm), mesh | one_solid (from a .3dm), ft (a .3dm in
feet), live (each edit checked in turn)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate  # noqa: E402
import harness  # noqa: E402


def drawn(design, way):
    if way in ("reversed", "shifted"):
        return harness.gordium(design, way)
    if way in ("in", "mm", "ft"):
        return harness.gordium_file(design, way)
    return harness.gordium_file(design, "ft", way)


def compare(lot, edits, way, rules=()):
    harness.fast_reads()
    design, _ = generate.build(lot, edits)
    base = harness.gordium(design) if way in ("reversed", "shifted", "ft") else harness.gordium_file(design, "ft")
    other = drawn(design, way)
    a, b = harness.items_by_rule(base), harness.items_by_rule(other)
    for rule in rules or sorted(set(harness.statuses(base)) | set(harness.statuses(other))):
        for tag, items in (("base", a.get(rule, [])), (way, b.get(rule, []))):
            for i in items:
                print(f"{rule:32} {tag:9} {i['name']:24} {i['status']:16} {i['proposed']!s:22} {(i['reason'] or '')[:160]}")
    names = ("building_height", "stories", "front_yard", "side_yard_smaller", "rear_yard", "building_area")
    for n in names:
        for tag, res in (("base", base), (way, other)):
            m = res["measurements"].get(n) or {}
            print(f"  {n:18} {tag:9} {m.get('value')!s:12} {[(r.get('value')) for r in m.get('readings') or []]}"
                  f" {(m.get('reason') or '')[:200]}")
    return base, other


if __name__ == "__main__":
    compare(sys.argv[1], json.loads(sys.argv[2]), sys.argv[3], sys.argv[4:])
