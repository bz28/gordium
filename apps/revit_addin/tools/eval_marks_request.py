"""Turns an eval's marks (a YAML file such as test_data/answer_keys/portland_me_19_libby_st/eval_marks.yaml) into the
Revit add-in's set_marks_request.json (apps/revit_addin/src/Gordium.Revit.Reading/MarksRequest.cs): every room's
sleeping mark (and a commercial story's use, lockable and pass_through), each window's escape mark and its type's
operation, each door's exit door and escape marks and its type's operation, every exit's Gordium: Exit, and each door
type's clear opening (written on the type with its stamp, signed by the file's `by`); and, with --check-out, the
check_project_request.json that checks the marked copy with the file's Project Information marks. Nothing is guessed
here: a room, window, door or exit missing a value, or a value of the wrong kind, stops the tool with why, and nothing
is written. The add-in refuses what it can't write.

    python eval_marks_request.py <eval_marks.yaml> --model <model.rvt> --save-as <copy.rvt> --out <set_marks_request.json>
        [--build-data <data.json> --build-out <build_model_request.json>] [--check-out <check_project_request.json>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


class BadMarks(ValueError):
    """The marks file isn't the shape this tool reads."""


def _flag(item: dict, key: str, defaults: dict, where: str) -> bool:
    value = item.get(key, defaults.get(key))
    if not isinstance(value, bool):
        raise BadMarks(f"{where}: `{key}` is {value!r}, not true or false")
    return value


def entries(marks: dict) -> list[dict]:
    """The request's `marks` list from the file's rooms, door types and exits."""
    defaults = marks.get("room_defaults") or {}
    out: list[dict] = []
    for room in (marks.get("rooms") or []) + (marks.get("rooms_to_place") or []):
        number = str(room.get("number", "")).strip()
        where = f"room {number or '?'}"
        if not number:
            raise BadMarks(f"{where}: needs a `number`")
        out.append({"room": number, "mark": "Gordium: Sleeping room", "value": _flag(room, "sleeping", defaults, where)})
        # a commercial story's rooms carry the route marks (all three); a house's carry none (its egress reads no routes)
        if "use" not in room and not ({"lockable", "pass_through"} & set(room)):
            continue
        if not isinstance(room.get("use"), str):
            raise BadMarks(f"{where}: needs a `use` with its lockable and pass_through")
        out.append({"room": number, "mark": "Gordium: Use", "value": room["use"]})
        out.append({"room": number, "mark": "Gordium: Can be locked", "value": _flag(room, "lockable", defaults, where)})
        out.append({"room": number, "mark": "Gordium: Pass through", "value": _flag(room, "pass_through", defaults, where)})
    for window in marks.get("windows") or []:
        mark, where = window.get("window"), f"window {window.get('window')!r}"
        if not isinstance(mark, str) or not isinstance(window.get("operation"), str):
            raise BadMarks(f"{where}: needs a `window` (its Mark) and an `operation` (Gordium: Operation's word)")
        out.append({"window": mark, "mark": "Gordium: Escape opening", "value": _flag(window, "escape", {}, where)})
        out.append({"window": mark, "mark": "Gordium: Operation", "value": window["operation"]})
    for door in marks.get("doors") or []:
        mark, where = door.get("door"), f"door {door.get('door')!r}"
        if not isinstance(mark, str) or not isinstance(door.get("operation"), str):
            raise BadMarks(f"{where}: needs a `door` (its Mark) and an `operation` (Gordium: Operation's word)")
        out.append({"door": mark, "mark": "Gordium: Exit door", "value": _flag(door, "exit_door", {}, where)})
        out.append({"door": mark, "mark": "Gordium: Escape opening", "value": _flag(door, "escape", {}, where)})
        out.append({"door": mark, "mark": "Gordium: Operation", "value": door["operation"]})
    for kind in marks.get("door_types") or []:
        doors = kind.get("doors")
        if not isinstance(doors, list) or not doors:
            raise BadMarks(f"door type {kind.get('leaf_in')}: needs `doors`, a door of the type each")
        clear = {"width_in": kind.get("clear_width_in"), "height_in": kind.get("clear_height_in"),
                 "operation": kind.get("operation"), "source": kind.get("source")}
        if any(v is None for v in clear.values()):
            raise BadMarks(f"door type {kind.get('leaf_in')}: needs clear_width_in, clear_height_in, operation and source")
        out.extend({"door": str(d), "clear": dict(clear)} for d in doors)
    for exit_ in marks.get("exits") or []:
        if not isinstance(exit_.get("door"), str) or not isinstance(exit_.get("exit"), str):
            raise BadMarks(f"exit {exit_!r}: needs a `door` (its Mark) and an `exit` (Gordium: Exit's word)")
        out.append({"door": exit_["door"], "mark": "Gordium: Exit", "value": exit_["exit"]})
    return out


def place_rooms(marks: dict, level: str) -> list[dict]:
    """The Rooms to place (rooms_to_place) on the level named, each at its point with its name and number."""
    out = []
    for room in marks.get("rooms_to_place") or []:
        at = room.get("at")
        if not (isinstance(at, list) and len(at) == 2 and all(isinstance(v, (int, float)) for v in at)) \
                or not isinstance(room.get("name"), str) or not str(room.get("number", "")).strip():
            raise BadMarks(f"room to place {room.get('number')!r}: needs `at` [x, y], a `name` and a `number`")
        out.append({"level": level, "at": at, "name": room["name"], "number": str(room["number"])})
    return out


def request(marks: dict, model: str, save_as: str, level: str = "Level 1") -> dict:
    if not isinstance(marks, dict) or not isinstance(marks.get("by"), str) or not marks["by"].strip():
        raise BadMarks("the file needs `by`: who the marks stand in for")
    return {"model": model, "save_as": save_as, "by": marks["by"], "date": str(marks.get("date") or ""),
            "place_rooms": place_rooms(marks, level), "marks": entries(marks)}


def check_request(marks: dict, model: str) -> dict:
    """The check_project_request.json that checks the marked copy with no clicks (CheckProject.RunRequest): the file's
    Project Information marks (`project_information`), each a mark's name and its value."""
    facts: dict = {}
    for entry in marks.get("project_information") or []:
        name, value = entry.get("mark"), entry.get("value")
        if not isinstance(name, str) or not name.startswith("Gordium: ") or not isinstance(value, (bool, str)):
            raise BadMarks(f"project information {entry!r}: needs a `mark` (a Gordium mark's name) and a `value` "
                           "(true, false or text)")
        if not isinstance(entry.get("why"), str):
            raise BadMarks(f"project information {name}: needs a `why`")
        if name in facts:
            raise BadMarks(f"project information {name}: given twice")
        facts[name] = value
    return {"model": model, "marks": facts}


def build_request(marks: dict, data: str, save_as: str) -> dict:
    """The build request that rebuilds the model with the file's model_corrections (ModelBuild, BuildData.Correct)."""
    corrections = marks.get("model_corrections") or []
    if not all(isinstance(c, dict) and isinstance(c.get("why"), str) for c in corrections):
        raise BadMarks("every model correction needs a `why`")
    return {"data": data, "save_as": save_as, "corrections": corrections}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("marks")
    parser.add_argument("--model", required=True)
    parser.add_argument("--save-as", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--build-data", help="the traced data: also write the build request with model_corrections")
    parser.add_argument("--build-out", help="where to write that build request (its save_as is --model)")
    parser.add_argument("--check-out", help="also write the check_project_request.json that checks the marked copy "
                                            "(--save-as) with the file's project_information marks")
    args = parser.parse_args(argv)
    try:
        marks = yaml.safe_load(Path(args.marks).read_text(encoding="utf-8"))
        made = request(marks, args.model, args.save_as)
        build = build_request(marks, args.build_data, args.model) if args.build_data and args.build_out else None
        check = check_request(marks, args.save_as) if args.check_out else None
    except (BadMarks, yaml.YAMLError) as e:
        print(f"not written: {e}", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps(made, indent=2), encoding="utf-8")
    print(f"{len(made['place_rooms'])} rooms to place and {len(made['marks'])} marks written to {args.out}")
    if build is not None:
        Path(args.build_out).write_text(json.dumps(build, indent=2), encoding="utf-8")
        print(f"{len(build['corrections'])} model corrections written to {args.build_out}")
    if check is not None:
        Path(args.check_out).write_text(json.dumps(check, indent=2), encoding="utf-8")
        print(f"{len(check['marks'])} Project Information marks written to {args.check_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
