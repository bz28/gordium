"""A real Rhino model drawn in Revit, read back by the Revit reader, and held to what Rhino's own reading gives.

The conformance scenes are small and hand-worked; this takes a real model (the architects' 106 Ithaca Road) the same
way: the Rhino reference reader (conformance_rhino.describe_file, the description the Rhino command sends) is the
expected answer, and the Revit add-in must send the same description (design_checker.conformance.differences: the
same ids through its map, every point within a millionth of a foot, the same problems) and get exactly the same
verdicts from check_site.

    python real_site.py export <model.3dm> <facts.yaml>     what the add-in draws: JSON on standard output
    python real_site.py record <revit.json> <model name> <date> <tool> <out.json>
                                                             the add-in's result as a committed recording
    python real_site.py compare <model.3dm> <facts.yaml> <revit.json>
                                                             [] when Revit's reading is Rhino's, else every difference

The export draws what the Rhino reader reads, in Revit's terms: each closed outline on the Site layer a property line
(the lot is picked by the facts' lot_id, as in Rhino), each solid on the Building layer one element in a building
category, made from the faces Rhino's reader sends; every other curve (the Map layer's neighbours, the setback lines) a
model line, which neither reader takes for a building or a lot. It draws only that: a model with anything else the
Rhino reader reads (a curved lot outline, a building it can't read whole, a face with holes, a marked floor block, an
object left out or unsent, spot grades) is refused,
naming it, never drawn differently (review round 1).
"""

import json
import sys
from pathlib import Path

import rhino3dm as r
import yaml

from design_checker import conformance as c
from design_checker import conformance_rhino as cr
from design_checker import rhino_logic as logic
from design_checker import site_json
from model_measurement import read_3dm


def _facts(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))["lot_facts"]


def _points(curve) -> list[list[float]]:
    if isinstance(curve, r.PolylineCurve):
        return [[curve.Point(i).X, curve.Point(i).Y, curve.Point(i).Z] for i in range(curve.PointCount)]
    if isinstance(curve, r.LineCurve):
        return [[p.X, p.Y, p.Z] for p in (curve.PointAtStart, curve.PointAtEnd)]
    raise SystemExit(f"a {type(curve).__name__} isn't drawn yet (only polylines and lines): this model can't be exported")


def export(model_path: str, facts_path: str) -> dict:
    model = r.File3dm.Read(model_path)
    if str(model.Settings.ModelUnitSystem) != "UnitSystem.Feet":
        raise SystemExit("only a model in feet is drawn (Revit's own unit)")
    facts = _facts(facts_path)
    rhino = cr.describe_file(Path(model_path), facts)
    for key in ("left_out", "unsent"):
        if rhino.get(key):
            raise SystemExit(f"the Rhino reader has {key} objects ({[o.get('id') for o in rhino[key]]}): not drawn yet")
    if rhino["grade"]["source"] != "none":
        raise SystemExit("the Rhino reader reads spot grades: not drawn yet")
    for b in rhino["buildings"]:
        if b.get("problems") or not b["faces"]:   # a block, a curved or open solid, a mesh: not read whole (round 4)
            raise SystemExit(f"building {b['id']} isn't read whole by Rhino "
                             f"({[p.get('code') for p in b.get('problems') or []]}): not drawn yet")
        if any(f.get("holes") for f in b["faces"]):
            raise SystemExit(f"building {b['id']} has a face with holes: not drawn yet")
        if b.get("floor") is not None:
            raise SystemExit(f"building {b['id']} is a marked floor block: not drawn yet")
    names = [layer.FullPath for layer in model.Layers]
    lots, lines = [], []
    for o in model.Objects:
        if o.Attributes.IsInstanceDefinitionObject:
            continue                      # a block's definition: the reader reads only what is placed (review round 3)
        g, layer = o.Geometry, names[o.Attributes.LayerIndex]
        if not isinstance(g, r.Curve):
            if not logic.on_layer(layer, c.BUILDING_LAYER):   # the building is drawn from Rhino's faces, below
                raise SystemExit(f"{o.Attributes.Id} on {layer} is a {type(g).__name__}: not drawn yet")
            continue
        pts = _points(g)
        if logic.on_layer(layer, c.SITE_LAYER) and g.IsClosed:   # the Site layer and its sublayers, as the reader
            lots.append({"id": read_3dm._id(o), "points": [p[:2] for p in pts[:-1]]})   # the reader's own id
        else:
            lines.append(pts)
    ids = [lot["id"] for lot in lots]
    if facts.get("lot_id") and facts["lot_id"] not in ids:
        raise SystemExit(f"the facts' lot_id {facts['lot_id']} isn't one of the lots drawn ({ids})")
    if rhino.get("lot") and rhino["lot"]["id"] not in ids:
        raise SystemExit(f"the Rhino reader's lot {rhino['lot']['id']} isn't one of the lots drawn ({ids})")
    return {
        "lots": lots,
        "picked": facts.get("lot_id"),
        "buildings": [{"id": b["id"], "faces": [f["points"] for f in b["faces"]]} for b in rhino["buildings"]],
        "lines": lines,
        "facts": {k: v for k, v in facts.items() if k != "lot_id"},
    }


def record(revit_path: str, model: str, date: str, tool: str) -> dict:
    """The add-in's result ({"site", "ids"}) as the committed recording, with where it came from."""
    got = site_json.loads(Path(revit_path).read_text(encoding="utf-8"))
    return {"host": "revit", "model": model,
            "recorded": {"by": "Gordium add-in, real_site_request (Windows trial)", "date": date, "tool": tool},
            "ids": got["ids"], "site": got["site"]}


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
    if argv[:1] == ["record"] and len(argv) == 6:
        Path(argv[5]).write_text(json.dumps(record(*argv[1:5]), indent=2) + "\n", encoding="utf-8", newline="\n")
        return 0
    if argv[:1] == ["compare"] and len(argv) == 4:
        sys.stdout.write(json.dumps(compare(argv[1], argv[2], argv[3])) + "\n")
        return 0
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
