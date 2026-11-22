"""The route eval's file (test_data/answer_keys/portland_me_19_libby_st/eval_comparison.yaml): everything it states
as Gordium's is worked by make_eval_comparison.py running the route code, never written in by hand (what is, sits
under `by_hand` with its working), and the committed file is what the script makes from the model's description."""

import json
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
    assert travel["agreement"]["verdicts_same"] == {r: got["verdicts"]["rules"][r]["same"] for r in rules}
    assert travel["agreement"]["within_tolerance"] == (travel["agreement"]["no_longer"]
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
    """The one-sided test (route note, the eval, 2026-11-21): no longer than the line as drawn plus 2 percent or 2 ft
    agrees only with every verdict the same; a figure shorter than the line by any amount is no miss; longer by more
    than the tolerance is one. The old two-sided test would call the shorter figure a miss."""
    verdicts = {"a": {"same": True}, "b": {"same": True}, "c": {"same": False}}
    assert make._no_longer(130.325, 116.034, verdicts, ["a", "b"], "w")["within_tolerance"] is True
    assert make._no_longer(130.325, 116.034, verdicts, ["a", "c"], "w")["within_tolerance"] is False
    assert make._no_longer(100.0, 102.0, verdicts, ["a"], "w")["within_tolerance"] is True        # 2 ft allowed
    assert make._no_longer(100.0, 102.01, verdicts, ["a"], "w")["within_tolerance"] is False
    assert make._no_longer(200.0, 204.0, verdicts, ["a"], "w")["within_tolerance"] is True        # 2 percent
    assert make._no_longer(200.0, 204.01, verdicts, ["a"], "w")["within_tolerance"] is False
    assert make._no_longer(100.0, None, verdicts, ["a"], "w")["within_tolerance"] is None
    assert make._verdict(130.667, 116.034, 2.613, "w")["within_tolerance"] is False              # the old test


@pytest.mark.skipif(not os.environ.get("GORDIUM_CO_DESCRIPTION"),
                    reason="the Children's Odyssey model's description stays outside the repo (open question 5): "
                           "set GORDIUM_CO_DESCRIPTION to its path to check the committed file reproduces")
def test_the_committed_file_reproduces_from_the_script(tmp_path):
    got = make.main(os.environ["GORDIUM_CO_DESCRIPTION"], tmp_path / "out.yaml")
    assert got == yaml.safe_load(make.OUT.read_text(encoding="utf-8"))
