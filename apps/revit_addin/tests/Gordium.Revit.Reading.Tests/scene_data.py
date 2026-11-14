"""Print each drawn conformance scene as one JSON line: its drawing in plain numbers, from the conformance suite's own
functions (design_checker.conformance), never retyped. The C# tests (SceneDrawing.cs) draw each one as fake Revit
records from these numbers; what the reader must send for it is the suite's own expected description, never this.

    python scene_data.py
"""

import json
import sys

from design_checker import conformance as c


def main() -> int:
    for name, scene in c.scenes().items():
        if not c.has_model(scene):
            continue                       # a description only (13, 14): no drawing to read
        line = {"name": name, "units": (scene.get("model") or {}).get("units", "Feet"),
                "offset": c._offset(scene), "lots": c.lots(scene), "lot_ids": c.lot_ids(scene),
                "lot_arcs": {str(k): a for k, a in c.lot_arcs(scene).items()}, "others": c.others(scene),
                "open_lots": sorted(c.open_lots(scene)), "picked": c.picked(scene), "group": bool(scene.get("group")),
                "spots": c.spot_grades(scene), "facts": c.facts(scene),
                "steps": {step: {"solids": c.solids(scene, step), "verdicts": c.expected_verdicts(scene, step)}
                          for step in c.steps(scene)}}
        sys.stdout.write(json.dumps(line, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
