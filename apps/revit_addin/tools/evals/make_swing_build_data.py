"""The door swing check's building (docs/revit/revit_interior_reading_design.md, section 10, "Which side a door swings
into"): the four-unit apartment's build data (make_ny_build_data.py's revit_build_data.json) with each of its ten doors
given a swing the add-in's build flips it to (`swing_dir`, the side its leaf opens to; `hinge`, a single door's hinge
jamb), so that the template's single door stands in every facing and hand on the walls running north-south, three of
the four on those running east-west, and one door is a double (in Revit 2027 a family Gordium makes from Door.rft, its
leaves' swing drawn in plan: a second family). The add-in's swing check (SwingCheck.cs) then holds the side each door's
plan symbol is read to swing to against these.

    python apps/revit_addin/tools/evals/make_swing_build_data.py            write it
    python apps/revit_addin/tools/evals/make_swing_build_data.py --check    exit 1 when it isn't current

Not a real building, and not a rulebook. Plain code, no AI.
"""

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SOURCE = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_build_data.json"
OUT = REPO / "test_data/test_sites/revit_door_swing/revit_build_data.json"

# each door in the data's order: (the side its leaf opens to, + toward larger x on a north-south wall or larger y on an
# east-west one; its hinge jamb, + toward larger y or x along the wall; its kind)
SWINGS = [(+1, -1, "single"), (-1, +1, "single"), (+1, +1, "single"), (-1, -1, "single"), (-1, -1, "single"),
          (-1, +1, "single"), (-1, -1, "single"), (+1, +1, "single"), (+1, None, "double"), (+1, -1, "single")]


def build() -> dict:
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    walls = {w["id"]: w for w in src["walls"]}
    out = json.loads(json.dumps(src))
    out["project"] = "Door swing check (Gordium's four-unit eval building, each door given a swing; not a real project)"
    out["type_suffix"] = "swing check"
    out["made_from"] = {"tool": "apps/revit_addin/tools/evals/make_swing_build_data.py",
                        "sources": [{"file": SOURCE.relative_to(REPO).as_posix(),
                                     "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest()}]}
    if len(out["doors"]) != len(SWINGS):
        raise SystemExit(f"the apartment has {len(out['doors'])} doors, not the {len(SWINGS)} this gives swings to")
    for d, (swing, hinge, kind) in zip(out["doors"], SWINGS):
        w = walls[d["host_wall"]]
        (x0, y0), (x1, y1) = w["start"], w["end"]
        north_south = abs(x1 - x0) < 1e-9
        if not north_south and abs(y1 - y0) > 1e-9:
            raise SystemExit(f"door at {d['center']}: its wall isn't north-south or east-west")
        cx, cy = d["center"]
        d["swing_dir"] = [float(swing), 0.0] if north_south else [0.0, float(swing)]
        d["kind"] = kind
        if hinge is None:
            d.pop("hinge", None)
        else:
            half = d["width_in"] / 12 / 2
            d["hinge"] = [cx, cy + hinge * half] if north_south else [cx + hinge * half, cy]
        d["source"] = (f"{d.get('source', '')}; swing check: opens to {'+' if swing > 0 else '-'}"
                       f"{'x' if north_south else 'y'}, " + (f"hinged at its {'+' if hinge > 0 else '-'} jamb" if hinge
                                                             else "a double door"))
    return out


def main(argv: list[str]) -> int:
    text = json.dumps(build(), indent=1, ensure_ascii=False) + "\n"
    if "--check" in argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.relative_to(REPO)} isn't current: run make_swing_build_data.py")
            return 1
        print("current")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
