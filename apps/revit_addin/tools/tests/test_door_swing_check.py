"""The door swing reading held against Revit itself (docs/revit/revit_interior_reading_design.md, section 10, "Which
side a door swings into"): the add-in's swing check (SwingCheck.cs), run in Revit 2027 on the building
make_swing_build_data.py writes, recorded in test_data/test_sites/revit_door_swing/swing_check_recorded.json. Replayed
here so CI holds the recording to what it shows: every door read on the side it was built to swing, the template's
single door in all four facing and hand states and Gordium's double door, both as built and with every view Coarse and
the door subcategories hidden (the architect's own views never decide it: the reader makes its own plan view)."""

import hashlib
import importlib.util
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
HERE = REPO / "test_data/test_sites/revit_door_swing"
RECORDED = json.loads((HERE / "swing_check_recorded.json").read_text(encoding="utf-8"))
ROW = re.compile(r"^(D\d\d) \((.+?); (single|double)\): facing \(.+?\) flipped (True|False), hand \(.+?\) flipped "
                 r"(True|False), mirrored (True|False): read ([+-]|none), built ([+-]|none) \((agrees|DIFFERS)\)(; .*)?$")


def _rows(run, key):
    rows = run["swing_check"][key]
    out = []
    for r in rows:
        m = ROW.match(r)
        assert m, r
        out.append(m.groups())
    return out


def test_the_recording_is_of_the_build_data_as_it_is_now():
    data = HERE / "revit_build_data.json"
    assert RECORDED["build_data"]["sha256"] == hashlib.sha256(data.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location("make_swing", REPO / "apps/revit_addin/tools/evals/make_swing_build_data.py")
    make = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(make)
    assert make.main(["--check"]) == 0


def test_every_door_is_read_on_the_side_it_was_built_to_swing_in_every_facing_and_hand():
    run = RECORDED["runs"][1]
    assert run["build"]["ok"] and run["build"]["all_built"] and not run["build"]["failed"]
    assert all(line.endswith("swings as the data") or "swings as the data;" in line for line in run["build"]["doors"])
    for key in ("as_built", "views_coarse_swings_hidden"):
        rows = _rows(run, key)
        assert len(rows) == 10, key
        assert all(r[6] in "+-" and r[6] == r[7] and r[8] == "agrees" for r in rows), (key, rows)
        singles = {(r[3], r[4]) for r in rows if r[2] == "single" and r[1].startswith("Single-Flush")}
        assert singles == {("True", "True"), ("True", "False"), ("False", "True"), ("False", "False")}, singles
        assert any(r[2] == "double" for r in rows)
    assert run["swing_check"]["subcategories_hidden"] > 0


def test_each_door_swings_into_the_room_revit_finds_on_the_side_it_was_built_to_swing():
    # the whole reading (InteriorReader.Read: the side, then the room or outside found past the wall's face) beside
    # Revit's own GetRoomAtPoint 1 ft past the face on the built side (door swing review round 1)
    rooms = RECORDED["runs"][1]["swing_check"]["rooms"]
    assert len(rooms) == 10 and all(r.endswith("(agrees)") for r in rooms), rooms
    assert any("swings_into outside;" in r for r in rooms)
    assert len({r.split("swings_into ")[1].split(";")[0] for r in rooms}) >= 4


def test_the_reading_follows_what_revit_draws_not_the_builds_flip_convention():
    # built with the build's defaults, every template door stood turned from the data (the plan pictures showed each
    # swing where the reader read it); the reader never agreed with the data there, and agreed with Gordium's own double
    # door, whose swing it draws itself
    rows = _rows(RECORDED["runs"][0], "as_built")
    single = [r for r in rows if r[2] == "single"]
    assert single and all(r[6] in "+-" and r[7] in "+-" and r[6] != r[7] for r in single)
    assert all(r[8] == "agrees" for r in rows if r[2] == "double")


def test_the_build_flips_each_door_until_what_it_reads_back_is_the_data():
    # the model build's read-back (ModelBuild.SwingDoors), built with no flip convention at all: every door said to
    # swing as the data only from what was read back, the flips it needed covering facing, hand, both and neither on
    # the template's Single-Flush and facing on Gordium's double; then the swing check on the model it saved agrees,
    # side and room (Revit's own GetRoomAtPoint on the built side)
    rec = json.loads((HERE / "build_read_back_recorded.json").read_text(encoding="utf-8"))
    assert rec["build_data"]["sha256"] == RECORDED["build_data"]["sha256"]
    build = rec["build"]
    assert build["ok"] and build["all_built"] and not build["failed"]
    assert len(build["doors"]) == 10
    assert all(line.endswith("; swings as the data") and "read back: swings " in line for line in build["doors"])
    template = [line for line in build["doors"] if "(the template's family" in line]
    flips = {line.split("): ")[1].split("; read back")[0] for line in template}
    assert flips == {"nothing flipped", "facing flipped", "hand flipped", "facing flipped, hand flipped"}, flips
    assert any("(Gordium's family" in line for line in build["doors"])
    for line in build["doors"]:
        m = re.search(r"swings ([+-]) \(the data ([+-])\)", line)
        assert m and m.group(1) == m.group(2), line
        h = re.search(r"hinged ([+-]) \(the data ([+-])\)", line)
        assert h is None or h.group(1) == h.group(2), line
    rows = rec["swing_check"]
    assert all(r.endswith("(agrees)") for r in rows["rooms"]) and len(rows["rooms"]) == 10
    # the hinge and side held against what Revit drew, not the reader (build review round 1): each arc recorded is
    # hinged at the data's jamb (a single door) and bulges to the data's side, in the data's own (internal) feet
    data = json.loads((HERE / "revit_build_data.json").read_text(encoding="utf-8"))["doors"]
    arc = re.compile(r"centre \((-?[\d.]+), (-?[\d.]+)\) r [\d.]+ mid \((-?[\d.]+), (-?[\d.]+)\)")
    for k, line in enumerate(sorted(rows["arcs"])):
        d = data[k]
        assert line.startswith(f"D{k + 1:02}: "), line
        arcs = [tuple(map(float, m)) for m in arc.findall(line)]
        assert len(arcs) == (2 if d["kind"] == "double" else 1), line
        (cx, cy), (sx, sy) = d["center"], d["swing_dir"]
        for ax, ay, mx, my in arcs:
            assert (mx - cx) * sx + (my - cy) * sy > 0.5, (line, d)          # to the data's side
            if d.get("hinge"):
                hx, hy = d["hinge"]
                assert (ax - cx) * (hx - cx) + (ay - cy) * (hy - cy) > 0, (line, d)   # at the data's jamb
    assert all("(agrees)" in r for r in rows["as_built"] + rows["views_coarse_swings_hidden"])
