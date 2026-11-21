"""The eval marks file turns into a set-marks request with every room, door type and exit, and refuses a gap."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(TOOLS))

import eval_marks_request as tool  # noqa: E402

LIBBY = REPO / "test_data/answer_keys/portland_me_19_libby_st/eval_marks.yaml"


def test_the_libby_street_marks_make_a_request_for_every_room_and_exit():
    marks = yaml.safe_load(LIBBY.read_text(encoding="utf-8"))
    made = tool.request(marks, "m.rvt", "c.rvt")
    entries = made["marks"]
    rooms = {e["room"] for e in entries if "room" in e}
    assert len(rooms) == 25
    assert sum(1 for e in entries if e.get("mark") == "Gordium: Use") == 25
    assert [e["door"] for e in entries if e.get("mark") == "Gordium: Exit"] == ["D41", "D02", "D03", "D12"]
    assert made["by"].startswith("eval assumption")
    corridor = [e for e in entries if e.get("room") == "26"]
    assert {"room": "26", "mark": "Gordium: Use", "value": "Corridor"} in corridor
    assert {"room": "26", "mark": "Gordium: Can be locked", "value": False} in corridor


def test_a_room_missing_a_flag_stops_the_tool():
    with pytest.raises(tool.BadMarks):
        tool.request({"by": "x", "rooms": [{"number": "1", "use": "Other", "lockable": True}]}, "m", "c")
    with pytest.raises(tool.BadMarks):
        tool.request({"rooms": []}, "m", "c")
