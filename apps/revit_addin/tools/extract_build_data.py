"""Takes the building data out of a Revit drawing script someone sent us (a pyRevit or Dynamo script that holds its
plan as a JSON literal, `DATA = json.loads(r'''{...}''')`) and writes it as a JSON file the Revit add-in builds a
model from (its build_model_request.json, apps/revit_addin/README.md, "Build a model from data").

The script is untrusted downloaded code, so it is never run or imported: its text is parsed (`ast.parse`, which only
reads the syntax) and the one string literal assigned to DATA is decoded with `json.loads`. Nothing else in the script
is looked at. The data's shape is checked (every wall, door, window and room has what the add-in needs; each door and
window names a wall that exists; the counts are the script's own `stats`); anything wrong is printed and nothing is
written, never a part dropped. The JSON written is the data unchanged, with `extracted_from` (the script's file name and
sha256) added so a model built from it can be traced to the script.

    python extract_build_data.py <script.py> --out <data.json>
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import sys
from pathlib import Path

KINDS = ("single", "double")
STATUSES = ("Existing", "New")


class BadScript(ValueError):
    """The script has no DATA literal this tool can read, or its data isn't the shape the add-in builds from."""


def data_literal(text: str) -> str:
    """The string assigned to DATA as `DATA = json.loads(<one string literal>)`, read from the script's syntax only."""
    try:
        tree = ast.parse(text)
    except SyntaxError as x:
        raise BadScript(f"the script isn't valid Python ({x.msg}, line {x.lineno})") from None
    found = []
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "DATA"):
            continue
        call = node.value
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "loads"
                and isinstance(call.func.value, ast.Name) and call.func.value.id == "json"
                and len(call.args) == 1 and not call.keywords
                and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str)):
            raise BadScript(f"DATA (line {node.lineno}) isn't json.loads of one string literal")
        found.append(call.args[0].value)
    if len(found) != 1:
        raise BadScript(f"the script assigns DATA = json.loads('...') {len(found)} times at its top level, not once")
    return found[0]


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _point(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(_number(c) for c in v)


def problems(data) -> list[str]:
    """Everything about the data the add-in couldn't build from, each in words; empty when it can build all of it."""
    out: list[str] = []
    if not isinstance(data, dict):
        return ["the data isn't a JSON object"]

    def need(where: str, obj: dict, key: str, ok, what: str) -> None:
        if key not in obj:
            out.append(f"{where}: no {key}")
        elif not ok(obj[key]):
            out.append(f"{where}: {key} is {json.dumps(obj[key])}, not {what}")

    positive = lambda v: _number(v) and v > 0            # noqa: E731
    text = lambda v: isinstance(v, str) and v.strip() != ""   # noqa: E731
    need("data", data, "project", lambda v: isinstance(v, str), "text")
    need("data", data, "units", lambda v: v == "feet", '"feet"')
    need("data", data, "level", lambda v: isinstance(v, dict) and text(v.get("name")) and _number(v.get("elevation_ft")),
         "a level with a name and elevation_ft")
    for key in ("walls", "doors", "windows", "rooms", "footprint"):
        need("data", data, key, lambda v: isinstance(v, list), "a list")
    if out:
        return out

    ids: set[int] = set()
    for k, w in enumerate(data["walls"]):
        where = f"wall {k}"
        if not isinstance(w, dict):
            out.append(f"{where}: not an object")
            continue
        need(where, w, "id", lambda v: isinstance(v, int) and not isinstance(v, bool), "a whole number")
        if isinstance(w.get("id"), int):
            where = f"wall {w['id']}"
            if w["id"] in ids:
                out.append(f"{where}: a second wall with this id")
            ids.add(w["id"])
        need(where, w, "start", _point, "a point [x, y]")
        need(where, w, "end", _point, "a point [x, y]")
        if _point(w.get("start")) and _point(w.get("end")) and math.dist(w["start"], w["end"]) < 0.01:
            out.append(f"{where}: its start and end are the same point")
        need(where, w, "thickness_in", positive, "a thickness over 0")
        need(where, w, "status", lambda v: v in STATUSES, " or ".join(map(json.dumps, STATUSES)))
        need(where, w, "smoke_partition", lambda v: isinstance(v, bool), "true or false")
        need(where, w, "fire_rating", lambda v: v is None or text(v), "null or text")
        need(where, w, "height_ft", positive, "a height over 0")
        need(where, w, "exterior", lambda v: isinstance(v, bool), "true or false")

    host = lambda v: isinstance(v, int) and not isinstance(v, bool) and v in ids   # noqa: E731
    for k, d in enumerate(data["doors"]):
        where = f"door {k + 1}"
        if not isinstance(d, dict):
            out.append(f"{where}: not an object")
            continue
        need(where, d, "center", _point, "a point [x, y]")
        need(where, d, "width_in", positive, "a width over 0")
        need(where, d, "height_in", positive, "a height over 0")
        need(where, d, "kind", lambda v: v in KINDS, " or ".join(map(json.dumps, KINDS)))
        need(where, d, "host_wall", host, "the id of a wall in the data")
        need(where, d, "swing_dir", lambda v: _point(v) and abs(math.hypot(*v) - 1) < 0.01, "a unit vector [x, y]")
        if "hinge" in d and not _point(d["hinge"]):
            out.append(f"{where}: hinge is {json.dumps(d['hinge'])}, not a point [x, y]")
    for k, wn in enumerate(data["windows"]):
        where = f"window {k + 1}"
        if not isinstance(wn, dict):
            out.append(f"{where}: not an object")
            continue
        need(where, wn, "center", _point, "a point [x, y]")
        need(where, wn, "width_in", positive, "a width over 0")
        need(where, wn, "height_in", positive, "a height over 0")
        need(where, wn, "sill_in", lambda v: _number(v) and v >= 0, "a sill height of 0 or more")
        need(where, wn, "host_wall", host, "the id of a wall in the data")
    for k, r in enumerate(data["rooms"]):
        where = f"room {k + 1}"
        if not isinstance(r, dict):
            out.append(f"{where}: not an object")
            continue
        need(where, r, "number", text, "text")
        need(where, r, "name", text, "text")
        need(where, r, "tag_point", _point, "a point [x, y]")
        need(where, r, "boundary", lambda v: isinstance(v, list) and len(v) >= 3 and all(map(_point, v)),
             "a list of 3 or more points")
        if "area_sf" in r and not _number(r["area_sf"]):
            out.append(f"{where}: area_sf is {json.dumps(r['area_sf'])}, not a number")
    fp = data["footprint"]
    if not (len(fp) >= 4 and all(map(_point, fp))):
        out.append("footprint: not a list of 4 or more points [x, y]")
    elif math.dist(fp[0], fp[-1]) > 1e-9:
        out.append("footprint: its last point isn't its first (the add-in, as the script, drops the closing point)")
    stats = data.get("stats")
    if stats is not None:
        if not isinstance(stats, dict):
            out.append("stats: not an object")
        else:
            for key in ("walls", "doors", "windows", "rooms"):
                if key in stats and stats[key] != len(data[key]):
                    out.append(f"stats: {key} says {stats[key]}, the data has {len(data[key])}")
    return out


def extract(script: Path) -> dict:
    """The script's data, checked, with where it came from; BadScript when it can't be built from."""
    raw = script.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as x:
        raise BadScript(f"the script isn't UTF-8 text ({x})") from None
    try:
        data = json.loads(data_literal(text))
    except json.JSONDecodeError as x:
        raise BadScript(f"DATA's string isn't JSON ({x})") from None
    found = problems(data)
    if found:
        raise BadScript("the data can't be built from:\n  " + "\n  ".join(found))
    return {"extracted_from": {"file": script.name, "sha256": hashlib.sha256(raw).hexdigest()}, **data}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("script", type=Path, help="the Revit drawing script (read as text, never run)")
    parser.add_argument("--out", type=Path, required=True, help="the JSON file to write")
    args = parser.parse_args(argv)
    try:
        data = extract(args.script)
    except BadScript as x:
        print(f"{args.script}: {x}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(data['walls'])} walls, {len(data['doors'])} doors, {len(data['windows'])} windows, "
          f"{len(data['rooms'])} rooms, a footprint of {len(data['footprint']) - 1} corners "
          f"(from {data['extracted_from']['file']}, sha256 {data['extracted_from']['sha256'][:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
