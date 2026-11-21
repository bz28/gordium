"""The extractor (extract_build_data.py) reads a drawing script's DATA literal from its text, never running it, and
writes the data only when the add-in can build all of it. The made-up script beside this file raises if it is ever
run; Ben's received script (the Children's Odyssey childcare centre, rebuilt from its life-safety sheet LS1.0) is
checked when GORDIUM_MOCK_REVIT_SCRIPT names it (it is not in the repository)."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("extract_build_data", HERE.parent / "extract_build_data.py")
x = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(x)

TINY = HERE / "tiny_drawing_script.py"


def tiny() -> dict:
    return json.loads(x.data_literal(TINY.read_text(encoding="utf-8")))


def test_the_tiny_script_is_read_from_its_text_and_written_unchanged_with_its_source(tmp_path):
    out = tmp_path / "data.json"
    assert x.main([str(TINY), "--out", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["extracted_from"] == {"file": TINY.name, "sha256": hashlib.sha256(TINY.read_bytes()).hexdigest()}
    assert {k: v for k, v in written.items() if k != "extracted_from"} == tiny()
    assert [len(written[k]) for k in ("walls", "doors", "windows", "rooms")] == [5, 2, 1, 2]


def test_the_script_is_never_run():
    # the tiny script's first statement raises: reading it as text gets past it
    assert "raise RuntimeError" in TINY.read_text(encoding="utf-8")
    assert x.extract(TINY)["project"].startswith("Tiny box")


@pytest.mark.parametrize("text, words", [
    ("x = 1\n", "0 times"),
    ("import json\nDATA = json.loads('{}')\nDATA = json.loads('{}')\n", "2 times"),
    ("import json\nDATA = json.loads(open('a').read())\n", "isn't json.loads of one string literal"),
    ("DATA = eval('{}')\n", "isn't json.loads of one string literal"),
    ("def f(:\n", "isn't valid Python"),
])
def test_a_script_without_one_plain_data_literal_is_refused(text, words):
    with pytest.raises(x.BadScript, match=words):
        x.data_literal(text)


def test_data_that_isnt_json_is_refused_and_nothing_written(tmp_path):
    script = tmp_path / "s.py"
    script.write_text("import json\nDATA = json.loads(r'''{\"walls\": [}''')\n", encoding="utf-8")
    out = tmp_path / "data.json"
    assert x.main([str(script), "--out", str(out)]) == 1
    assert not out.exists()


def _broken(change) -> list[str]:
    data = tiny()
    change(data)
    return x.problems(data)


@pytest.mark.parametrize("change, words", [
    (lambda d: d["doors"][0].__setitem__("host_wall", 99), "door 1: host_wall is 99, not the id of a wall"),
    (lambda d: d["windows"][0].pop("sill_in"), "window 1: no sill_in"),
    (lambda d: d["doors"][1].__setitem__("kind", "triple"), 'door 2: kind is "triple"'),
    (lambda d: d["doors"][0].__setitem__("swing_dir", [1.0, 1.0]), "not a unit vector"),
    (lambda d: d["doors"][0].__setitem__("hinge", "left"), "door 1: hinge is \"left\""),
    (lambda d: d["walls"][4].__setitem__("id", 0), "wall 0: a second wall with this id"),
    (lambda d: d["walls"][0].__setitem__("thickness_in", True), "thickness_in is true"),
    (lambda d: d["walls"][0].__setitem__("status", "Demolished"), 'status is "Demolished"'),
    (lambda d: d["walls"][0].__setitem__("end", [0.0, 0.0]), "its start and end are the same point"),
    (lambda d: d["rooms"][1].__setitem__("boundary", [[0, 0], [1, 1]]), "room 2: boundary"),
    (lambda d: d["rooms"][0].__setitem__("name", " "), "room 1: name"),
    (lambda d: d["footprint"].pop(), "footprint: its last point isn't its first"),
    # the add-in refuses the same (BuildDataTests.Each_bad_part_is_refused_in_words)
    (lambda d: d["walls"][0].pop("fire_rating"), "wall 0: no fire_rating"),
    (lambda d: d["doors"][0].__setitem__("hinge", None), "door 1: hinge is null, not a point"),
    (lambda d: d["level"].__setitem__("name", "   "), "level is"),
    (lambda d: d["rooms"][0].__setitem__("area_sf", None), "room 1: area_sf is null, not a number"),
    (lambda d: d.__setitem__("units", "metres"), 'units is "metres"'),
    (lambda d: d["stats"].__setitem__("doors", 3), "stats: doors says 3, the data has 2"),
])
def test_each_thing_the_add_in_couldnt_build_is_named(change, words):
    found = _broken(change)
    assert any(words in p for p in found), found


@pytest.mark.parametrize("doors, words", [
    (2.0, None),                                              # 2.0 is 2, as the add-in reads it
    (None, "stats: doors says null, the data has 2"),
    ("2", 'stats: doors says "2", the data has 2'),
    (True, "stats: doors says true, the data has 2"),
])
def test_the_stats_are_checked_as_the_add_in_checks_them(doors, words):
    # the same cases as BuildDataTests.The_stats_are_checked_as_the_extractor_checks_them
    found = _broken(lambda d: d["stats"].__setitem__("doors", doors))
    assert found == [] if words is None else any(words in p for p in found), found
    assert _broken(lambda d: d.__setitem__("stats", 5)) == ["stats: not an object"]
    # one window: true is not 1 (Python's True == 1, which the add-in doesn't read as a count)
    assert _broken(lambda d: d["stats"].__setitem__("windows", True)) == ["stats: windows says true, the data has 1"]
    assert _broken(lambda d: d.__setitem__("stats", None)) == []


def test_the_tiny_data_has_no_problems_and_a_door_needs_no_hinge():
    data = tiny()
    assert "hinge" not in data["doors"][1]
    assert x.problems(data) == []
    assert x.problems(copy.deepcopy(data) | {"stats": None}) == []


@pytest.mark.skipif(not os.environ.get("GORDIUM_MOCK_REVIT_SCRIPT"), reason="Ben's received script is not in the repository")
def test_bens_childcare_centre_script_gives_its_122_walls_52_doors_67_windows_25_rooms(tmp_path):
    script = Path(os.environ["GORDIUM_MOCK_REVIT_SCRIPT"])
    out = tmp_path / "children_odyssey.json"
    assert x.main([str(script), "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [len(data[k]) for k in ("walls", "doors", "windows", "rooms")] == [122, 52, 67, 25]
    assert sum(d["kind"] == "double" for d in data["doors"]) == 5
    assert data["level"] == {"name": "Level 1", "elevation_ft": 0.0}
