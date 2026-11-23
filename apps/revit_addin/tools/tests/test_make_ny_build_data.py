"""The New York eval's build data (make_ny_build_data.py): current, every element traced to a field of its source,
and what it draws equal to the source's own numbers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "evals"))

import make_ny_build_data as tool  # noqa: E402

HOUSE = REPO / "test_data/real_houses/orangetown_ny_80_south_william"
SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"


@pytest.fixture(scope="module")
def fresh():
    return tool.made()


def load(folder: Path, name: str):
    return yaml.safe_load((folder / name).read_text(encoding="utf-8"))


def test_the_committed_build_data_is_a_fresh_build(fresh):
    for key, data in fresh.items():
        assert tool.OUT[key].read_text(encoding="utf-8") == tool.text(data), f"run {tool.TOOL}"


def test_every_element_names_its_source(fresh):
    for data in fresh.values():
        for key in ("levels", "walls", "doors", "windows", "rooms", "floors", "ceilings", "separations", "spot_grades"):
            for item in data.get(key) or []:
                assert isinstance(item.get("source"), str) and len(item["source"]) > 20, (key, item)
        assert data["lot"]["source"]
        for a in data["assumptions"]:
            assert set(a) == {"what", "why", "effect"}, a
        assert [s["file"] for s in data["made_from"]["sources"]]


def test_every_orangetown_wall_carries_its_own_layout_comment(fresh):
    lay = load(HOUSE, "layout.yaml")
    text = (HOUSE / "layout.yaml").read_text(encoding="utf-8")
    comments, headers = tool.layout_comments(text), tool.layout_headers(text)
    # every wall's comment read, but the three basement walls the layout gives none (cited by the basement's chains)
    assert {(lv["id"], w) for lv in lay["levels"] for w in lv["walls"]} - set(comments) ==         {("basement", "west"), ("basement", "east"), ("basement", "south")}
    assert headers["basement"].startswith("A-2 basement: 8\" concrete walls") and headers["basement"].endswith("(d 238).")
    walls = fresh["orangetown"]["walls"]
    assert len(walls) == 41
    for lv in lay["levels"]:
        for name, rect in lv["walls"].items():
            wall = next(w for w in walls if f"walls.{name} {rect} " in w["source"] and w["level"] == tool.LEVEL_NAMES[lv["id"]])
            assert comments.get((lv["id"], name), headers[lv["id"]]) in wall["source"]
            # drawn as the rectangle it is: along its longer side, as thick as its shorter (inches to feet)
            x0, d0, x1, d1 = rect
            assert wall["thickness_in"] == pytest.approx(min(x1 - x0, d1 - d0))
            (sx, sy), (ex, ey) = wall["start"], wall["end"]
            assert abs(ex - sx) + abs(ey - sy) == pytest.approx(max(x1 - x0, d1 - d0) / 12)


def test_a_wall_is_exterior_by_where_it_stands(fresh):
    # review round 1: the basement's four foundation walls have no "exterior" comment, yet stand on its outline
    walls = {(w["level"], w["source"].split("walls.")[1].split(" ")[0]): w for w in fresh["orangetown"]["walls"]}
    for name in ("north", "west", "east", "south"):
        assert walls[("Basement", name)]["exterior"] is True, name
    # the walls against the unexcavated areas bound the basement too (its outline leaves those areas out)
    assert walls[("Basement", "unexcavated_west")]["exterior"] is True
    assert walls[("Main floor", "garage_north")]["exterior"] is False         # between the garage and the house
    assert walls[("Second floor", "master_east")]["exterior"] is False
    assert walls[("Main floor", "garage_south")]["exterior"] is True
    assert all("lies on the level's outline" in w["source"] for w in walls.values())


def test_the_orangetown_house_is_house_yamls(fresh):
    house, data = load(HOUSE, "house.yaml"), fresh["orangetown"]
    rooms = {r["house_id"]: r for r in data["rooms"]}
    for r in house["rooms"]:
        assert rooms[r["id"]]["sleeping"] is r["sleeping"] and rooms[r["id"]]["name"] == r["name"]
        if "floor" in r:                                      # its area as house.yaml's inside dimensions give it
            xs, ys = [p[0] for p in r["floor"]], [p[1] for p in r["floor"]]
            assert rooms[r["id"]]["area_sf"] == pytest.approx((max(xs) - min(xs)) * (max(ys) - min(ys)) / 144)
            assert r["cite"]["floor"] in rooms[r["id"]]["source"]
    assert [r["number"] for r in data["rooms"]] == [str(n) for n in range(1, 18)]
    windows = {w["house_id"]: w for w in data["windows"]}
    assert set(windows) == {o["id"] for o in house["openings"]}
    lay = load(HOUSE, "layout.yaml")
    for o in house["openings"]:
        w = windows[o["id"]]
        assert (w["escape"], w["operation"]) == (o["escape"], o["operation"])
        size = lay["sizes"][next(p["size"] for lv in lay["levels"] for p in lv.get("windows") or [] if p["id"] == o["id"])]
        assert (w["width_in"], w["height_in"], w["sill_in"]) == (size["width"], size["height"], lay["head"] - size["height"])
        assert ("ASSUMED" in w["source"]) is bool(size.get("assumed"))       # C15 and CW14: the layout's assumed sizes
    door = data["doors"][0]
    assert (door["exit"], door["operation"], door["width_in"], door["height_in"]) == (True, "side_hinged", 36, 96)
    assert "swing_dir" not in door and "hinge" not in door                    # house.yaml gives no hinge side
    assert data["walls"][door["host_wall"] - 1]["level"] == "Main floor"
    assert "STAND-IN" in data["lot"]["source"]
    assert set(data["not_drawn"]) >= {"stairs", "guards"}


def test_the_106_ithaca_rd_box_is_the_spreadsheets(fresh):
    data, design = fresh["106_ithaca_rd"], load(SITE, "spreadsheet_design.yaml")
    m = {k: v["value"] for k, v in design["measurements"].items()}
    # the walls' outer faces: the house's outline, 10 ft from the left side and 30 from the street, 53 x 35
    faces = []
    for w in data["walls"]:
        h = w["thickness_in"] / 24
        (sx, sy), (ex, ey) = w["start"], w["end"]
        faces += [(sx - h, sy - h), (ex + h, ey + h), (sx + h, sy + h), (ex - h, ey - h)]
    x0, y0 = min(p[0] for p in faces), min(p[1] for p in faces)
    x1, y1 = max(p[0] for p in faces), max(p[1] for p in faces)
    assert (x0, y0) == (m["side_yard_smaller"], m["front_yard"])
    assert (m["lot_width"] - x1, m["lot_depth"] - y1) == (m["side_yard_larger"], m["rear_yard"])
    assert (x1 - x0) * (y1 - y0) == m["building_area"]
    assert {w["height_ft"] for w in data["walls"]} == {m["building_height"]}
    assert data["levels"][1]["elevation_ft"] == m["building_height"]
    assert data["lot"]["outline"][:4] == [[0, 0], [73, 0], [73, 90], [0, 90]]
    assert {s["at"][2] for s in data["spot_grades"]} == {0}
    assert data["rooms"] == data["doors"] == data["windows"] == []


def test_check_says_which_file_is_stale(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tool, "OUT", {**tool.OUT, "orangetown": tmp_path / "a.json"})
    assert tool.main(["--check"]) == 1
    assert "differs from a fresh build" in capsys.readouterr().out
    assert not (tmp_path / "a.json").exists()                  # --check writes nothing
