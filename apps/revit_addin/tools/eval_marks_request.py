"""Turns an eval's marks (a YAML file such as test_data/answer_keys/portland_me_19_libby_st/eval_marks.yaml) into the
Revit add-in's set_marks_request.json (apps/revit_addin/src/Gordium.Revit.Reading/MarksRequest.cs): every room's
sleeping, use, lockable and pass_through marks, every exit's Gordium: Exit, and each door type's clear opening (written
on the type with its stamp, signed by the file's `by`). Nothing is guessed here: a room or exit missing a value, or a
value of the wrong kind, stops the tool with why, and nothing is written. The add-in refuses what it can't write.

    python eval_marks_request.py <eval_marks.yaml> --model <model.rvt> --save-as <copy.rvt> --out <set_marks_request.json>
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
    for room in marks.get("rooms") or []:
        number = str(room.get("number", "")).strip()
        where = f"room {number or '?'}"
        if not number or not isinstance(room.get("use"), str):
            raise BadMarks(f"{where}: needs a `number` and a `use`")
        out.append({"room": number, "mark": "Gordium: Sleeping room", "value": _flag(room, "sleeping", defaults, where)})
        out.append({"room": number, "mark": "Gordium: Use", "value": room["use"]})
        out.append({"room": number, "mark": "Gordium: Can be locked", "value": _flag(room, "lockable", defaults, where)})
        out.append({"room": number, "mark": "Gordium: Pass through", "value": _flag(room, "pass_through", defaults, where)})
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


def request(marks: dict, model: str, save_as: str) -> dict:
    if not isinstance(marks, dict) or not isinstance(marks.get("by"), str) or not marks["by"].strip():
        raise BadMarks("the file needs `by`: who the marks stand in for")
    return {"model": model, "save_as": save_as, "by": marks["by"], "date": str(marks.get("date") or ""),
            "marks": entries(marks)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("marks")
    parser.add_argument("--model", required=True)
    parser.add_argument("--save-as", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        marks = yaml.safe_load(Path(args.marks).read_text(encoding="utf-8"))
        made = request(marks, args.model, args.save_as)
    except (BadMarks, yaml.YAMLError) as e:
        print(f"not written: {e}", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps(made, indent=2), encoding="utf-8")
    print(f"{len(made['marks'])} marks written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
