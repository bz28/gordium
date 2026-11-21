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
    assert travel["agreement"]["within_tolerance"] == (abs(ours - sheet) <= max(0.02 * sheet, 2.0))
    assert travel["agreement"]["difference"] == round(ours - sheet, 3)
    for name in ("travel_distance", "common_path", "dead_end", "remoteness", "diagonal"):
        assert "within_tolerance" in got["figures"][name]["agreement"] and got["figures"][name]["agreement"]["tolerance"]
    assert "within_tolerance" in got["storage"]["agreement_inside"]
    assert not any("percent" in str(v) or "agree" in str(v) for v in got["by_hand"].values())


@pytest.mark.skipif(not os.environ.get("GORDIUM_CO_DESCRIPTION"),
                    reason="the Children's Odyssey model's description stays outside the repo (open question 5): "
                           "set GORDIUM_CO_DESCRIPTION to its path to check the committed file reproduces")
def test_the_committed_file_reproduces_from_the_script(tmp_path):
    got = make.main(os.environ["GORDIUM_CO_DESCRIPTION"], tmp_path / "out.yaml")
    assert got == yaml.safe_load(make.OUT.read_text(encoding="utf-8"))
