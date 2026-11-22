"""The route eval's file (test_data/answer_keys/portland_me_19_libby_st/eval_comparison.yaml): everything it states
as Gordium's is worked by make_eval_comparison.py running the route code, never written in by hand (what is, sits
under `by_hand` with its working), and the committed file is what the script makes from the model's description."""

import json
import math
import os
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))           # the script and layouts beside this file
import make_eval_comparison as make  # noqa: E402
from test_routes_parts import day_care  # noqa: E402


def test_gordiums_entries_come_from_running_the_code(tmp_path):
    from model_measurement.routes import dead_ends, measure
    from model_measurement.routes.floor import read
    from model_measurement.routes.paths import StoryRoutes
    desc = day_care(branch=26)
    src = tmp_path / "d.json"
    src.write_text(json.dumps(desc), encoding="utf-8")
    got = make.main(src, tmp_path / "out.yaml",
                    {"start_room": "k1", "sheet_exit": "B", "same_pair": ((-0.25, 15), (72.25, 15))})
    assert yaml.safe_load((tmp_path / "out.yaml").read_text(encoding="utf-8")) == got
    story = next(iter(read(desc).stories.values()))
    found = dead_ends.corridors(story, {r["id"]: r.get("use") for r in desc["rooms"]}, StoryRoutes(story))
    assert got["figures"]["dead_end"]["gordium"]["c"]["dead_ends"][0]["length"] == round(
        found["c"].dead_ends[0].length[dead_ends.WITHOUT] / 12, 3) == 30.0
    sp = measure(desc)["parts"]["story"][0]
    assert got["figures"]["travel_distance"]["gordium"]["story"] == {
        "figure": round(sp["measures"]["egress_travel_distance"], 3)}
    assert set(got["by_hand"]) >= {"dead_end_centre_line_reading", "story_sf_correct"}
    # each figure judged against the decision's tolerance by the script (review round 2)
    travel = got["figures"]["travel_distance"]
    sheet, ours = travel["sheet_stated"], travel["gordium"]["to_the_sheets_exit_no_clearance"]
    before = travel["agreement"]["before_2026_11_21"]                 # the first test, still reported
    assert before["within_tolerance"] == (abs(ours - sheet) <= max(0.02 * sheet, 2.0))
    assert before["difference"] == round(ours - sheet, 3)
    # the test since 2026-11-21: one-sided against the sheet's line as drawn, and the figure's verdicts the sheet's
    drawn = travel["sheet_line_as_drawn"]
    rules = ("general.ibc_1016_1_travel_distance", "general.nfpa_16_2_6_2_point_in_room_to_exit")
    assert travel["agreement"]["no_longer"] == (ours <= drawn + max(0.02 * drawn, 2.0))
    own = round(math.dist(travel["gordium"]["from"], travel["gordium"]["to_no_clearance"]), 3)
    assert travel["agreement"]["own_ends_straight"] == own
    assert travel["agreement"]["no_shorter_than_own_straight"] == (ours >= own - 1e-6)
    assert travel["agreement"]["end"]["sheet"] == travel["sheet_line_in_model"][-1]
    common = got["figures"]["common_path"]
    assert common["agreement"]["own_ends_straight"] == round(
        math.dist(common["gordium"]["from"], common["gordium"]["split_no_clearance"]), 3)
    assert travel["agreement"]["verdicts_same"] == {r: got["verdicts"]["rules"][r]["same"] for r in rules}
    assert travel["agreement"]["within_tolerance"] == (travel["agreement"]["no_longer"]
                                                       and travel["agreement"]["no_shorter_than_own_straight"]
                                                       and all(travel["agreement"]["verdicts_same"].values()))
    for name in ("travel_distance", "common_path", "dead_end", "remoteness", "diagonal"):
        assert "within_tolerance" in got["figures"][name]["agreement"] and got["figures"][name]["agreement"]["tolerance"]
    assert "within_tolerance" in got["storage"]["agreement_inside"]
    # the dead end the sheet's line runs along, by position: here none starts within 3 ft of it (not judged); and
    # length and width both judged when one does (review round 3)
    dead = got["figures"]["dead_end"]["agreement"]
    assert dead["within_tolerance"] is None and dead["length"]["within_tolerance"] is None
    assert dead["dead_end"] == "Gordium's dead ends start elsewhere: none within 3 ft of the sheet's line"
    assert make._no_dead_end({"c": {"not_measured": "why"}}) == "Gordium measured no dead end on this corridor: why"
    fake = {"figures": {k: dict(v) for k, v in got["figures"].items()}, "storage": dict(got["storage"]),
            "verdicts": got["verdicts"]}
    line = fake["figures"]["dead_end"]["sheet_line_in_model"]
    fake["figures"]["dead_end"]["gordium"] = {"x": {"dead_ends": [
        {"from": [line[0][0] + 20, line[0][1]], "length": 21.5, "least_width": 10.0},     # elsewhere: never taken
        {"from": list(line[0]), "length": 21.9, "least_width": 9.8}]}}
    make._judge_all(fake)
    dead = fake["figures"]["dead_end"]["agreement"]
    assert dead["dead_end"] == list(line[0]) and dead["length"]["within_tolerance"] is True
    assert dead["least_width"]["within_tolerance"] is False and dead["within_tolerance"] is False   # 2.4 in off
    assert set(got["verdicts"]["rules"]) >= {"general.nfpa_16_2_5_2_dead_end", "general.ibc_508_2_1_accessory_area"}
    assert "every_verdict_the_same" in got["verdicts"] and "judged" in got["storage"]["under_all_four_readings"]
    assert not any("percent" in str(v) or "agree" in str(v) for v in got["by_hand"].values())


def test_a_figure_longer_than_the_sheets_line_or_a_verdict_apart_never_agrees():
    """The test since 2026-11-21 (route note, the eval): no longer than the line as drawn plus 2 percent or 2 ft,
    no shorter than the straight line between its ends less the same, and every verdict the same; the old two-sided
    test would call a figure shorter than the orthogonal line a miss."""
    verdicts = {"a": {"same": True}, "b": {"same": True}, "c": {"same": False}}
    ok = make._no_longer(130.325, 116.034, verdicts, ["a", "b"], "w", 65.92)
    assert ok["within_tolerance"] is True and ok["no_longer"] and ok["no_shorter_than_own_straight"]
    assert make._no_longer(130.325, 116.034, verdicts, ["a", "c"], "w", 65.92)["within_tolerance"] is False
    assert make._no_longer(100.0, 102.0, verdicts, ["a"], "w", 50.0)["within_tolerance"] is True        # 2 ft allowed
    assert make._no_longer(100.0, 102.01, verdicts, ["a"], "w", 50.0)["within_tolerance"] is False
    assert make._no_longer(200.0, 204.0, verdicts, ["a"], "w", 50.0)["within_tolerance"] is True        # 2 percent
    assert make._no_longer(200.0, 204.01, verdicts, ["a"], "w", 50.0)["within_tolerance"] is False
    assert make._no_longer(100.0, None, verdicts, ["a"], "w", 50.0)["within_tolerance"] is None
    assert make._verdict(130.667, 116.034, 2.613, "w")["within_tolerance"] is False              # the old test


def test_a_figure_under_its_own_start_to_end_straight_line_never_agrees():
    """Review rounds 1 and 2: a route measured too short (the false-pass direction) never agrees. The floor is the
    straight line from Gordium's own start to its own end (no route between them can beat it), not the sheet
    line's ends, which needn't be the same two points."""
    verdicts = {"a": {"same": True}}
    got = make._no_longer(130.325, 10.0, verdicts, ["a"], "w", 65.92)
    assert got["no_longer"] is True and got["no_shorter_than_own_straight"] is False
    assert got["within_tolerance"] is False
    assert make._no_longer(48.404, 41.07, verdicts, ["a"], "w", 41.07)["within_tolerance"] is True
    assert make._no_longer(48.404, 41.06, verdicts, ["a"], "w", 41.07)["within_tolerance"] is False   # no tolerance
    end = make._end([117.42, 49.563], [117.0, 49.0], 2.0, "where Gordium's two routes part")
    assert end["within_tolerance"] is True and end["apart"] == 0.702
    assert make._end([117.42, 49.563], [117.42, 52.0], 2.0, "x")["within_tolerance"] is False


def test_a_routes_point_at_a_length_is_on_its_pieces():
    # by hand: a line (0, 0) to (12, 0) then a quarter arc of radius 12 about (12, 12) from -90 degrees, sweeping +90:
    # 6 in along is (6, 0); 12 + 12 * pi / 4 along is the arc's middle, (12 + 12 sin 45, 12 - 12 cos 45)
    pieces = [("line", (0.0, 0.0), (12.0, 0.0)), ("arc", (12.0, 12.0), 12.0, -math.pi / 2, math.pi / 2)]
    assert make._point_at(pieces, 6.0) == pytest.approx((6.0, 0.0))
    assert make._point_at(pieces, 12 + 3 * math.pi) == pytest.approx((12 + 12 * math.sin(math.pi / 4),
                                                                      12 - 12 * math.cos(math.pi / 4)))
    assert make._point_at(pieces, 12 + 6 * math.pi) == pytest.approx((24.0, 12.0))


@pytest.mark.skipif(not os.environ.get("GORDIUM_CO_DESCRIPTION"),
                    reason="the Children's Odyssey model's description stays outside the repo (open question 5): "
                           "set GORDIUM_CO_DESCRIPTION to its path to check the committed file reproduces")
def test_the_committed_file_reproduces_from_the_script(tmp_path):
    got = make.main(os.environ["GORDIUM_CO_DESCRIPTION"], tmp_path / "out.yaml")
    assert got == yaml.safe_load(make.OUT.read_text(encoding="utf-8"))
