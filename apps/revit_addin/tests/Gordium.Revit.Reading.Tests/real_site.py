"""A real Rhino model drawn in Revit, read back by the Revit reader, and held to what Rhino's own reading gives.

The conformance scenes are small and hand-worked; this takes a real model (the architects' 106 Ithaca Road) the same
way: the Rhino reference reader (conformance_rhino.describe_file, the description the Rhino command sends) is the
expected answer, and the Revit add-in must send the same description (design_checker.conformance.differences: the
same ids through its map, every point within a millionth of a foot, the same problems) and get exactly the same
verdicts from check_site.

    python real_site.py export <model.3dm> <facts.yaml>     what the add-in draws: JSON on standard output
    python real_site.py compare <model.3dm> <facts.yaml> <revit.json>
                                                             [] when Revit's reading is Rhino's, else every difference

The export draws exactly what the Rhino reader reads, in Revit's terms: each closed outline on the Site layer a
property line (the lot is picked by the facts' lot_id, as in Rhino), each solid on the Building layer one element in
a building category, made from the faces Rhino's reader sends; every other curve (the Map layer's neighbours, the
setback lines) a model line, which neither reader takes for a building or a lot.
"""

import json
import sys
from pathlib import Path

import rhino3dm as r
import yaml

from design_checker import conformance as c
from design_checker import conformance_rhino as cr
from design_checker import site_json


def _facts(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))["lot_facts"]


def _points(curve) -> list[list[float]]:
    if isinstance(curve, r.PolylineCurve):
        return [[curve.Point(i).X, curve.Point(i).Y, curve.Point(i).Z] for i in range(curve.PointCount)]
    return [[p.X, p.Y, p.Z] for p in (curve.PointAtStart, curve.PointAtEnd)]


def export(model_path: str, facts_path: str) -> dict:
    model = r.File3dm.Read(model_path)
    if str(model.Settings.ModelUnitSystem) != "UnitSystem.Feet":
        raise SystemExit("only a model in feet is drawn (Revit's own unit)")
    facts = _facts(facts_path)
    rhino = cr.describe_file(Path(model_path), facts)
    names = [layer.FullPath for layer in model.Layers]
    lots, lines = [], []
    for o in model.Objects:
        g, layer = o.Geometry, names[o.Attributes.LayerIndex]
        if not isinstance(g, r.Curve):
            continue
        if layer == "Site" and g.IsClosed:
            pts = _points(g)
            lots.append({"id": str(o.Attributes.Id), "points": [p[:2] for p in pts[:-1]]})
        else:
            lines.append(_points(g))
    return {
        "lots": lots,
        "picked": facts.get("lot_id"),
        "buildings": [{"id": b["id"], "faces": [f["points"] for f in b["faces"]]} for b in rhino["buildings"]],
        "lines": lines,
        "facts": {k: v for k, v in facts.items() if k != "lot_id"},
    }


def compare(model_path: str, facts_path: str, revit_path: str) -> list[str]:
    facts = _facts(facts_path)
    want = cr.describe_file(Path(model_path), facts)
    got = site_json.loads(Path(revit_path).read_text(encoding="utf-8"))
    out = c.differences(got["site"], want, got["ids"])
    if any(d.startswith("not a valid description") for d in out):
        return out
    revit_facts = {**facts, "lot_id": got["site"]["lot"]["id"] if got["site"].get("lot") else None}
    return out + [f"verdict {d}" for d in c.verdict_differences(c.verdicts(got["site"], revit_facts),
                                                                c.verdicts(want, facts))]


def main(argv: list[str]) -> int:
    if argv[:1] == ["export"] and len(argv) == 3:
        sys.stdout.write(json.dumps(export(argv[1], argv[2])) + "\n")
        return 0
    if argv[:1] == ["compare"] and len(argv) == 4:
        sys.stdout.write(json.dumps(compare(argv[1], argv[2], argv[3])) + "\n")
        return 0
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
