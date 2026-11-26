"""The stair test building (test_data/test_sites/new_york/stair_enclosure/, written by
apps/revit_addin/tools/evals/make_stair_building.py): both variants current, and each measuring exactly as its header
works it by hand, so section group 7's rules (1011, 1014, 1015) can be held to it end to end: the compliant one within
every limit the measuring gives the rules, the failing one past each limit it was built to break, nothing else."""

import importlib.util
from pathlib import Path

from model_measurement.interior import measure_file

REPO = Path(__file__).resolve().parents[4]
HERE = REPO / "test_data/test_sites/new_york/stair_enclosure"


def _maker():
    spec = importlib.util.spec_from_file_location("make_stair", REPO / "apps/revit_addin/tools/evals/make_stair_building.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _measured(variant):
    got = measure_file(HERE / f"stair_enclosure_{variant}.yaml")
    assert got["problems"] == [], got["problems"]
    return {p["id"]: p for p in got["parts"]["stair"]}, {g["id"]: g for g in got["parts"]["guard"]}


def test_both_variants_are_current():
    assert _maker().main(["--check"]) == 0


def test_the_compliant_stair_measures_within_every_limit():
    stairs, guards = _measured("compliant")
    for f in ("f1", "f2"):
        m, more = stairs[f]["measures"], stairs[f]["more"]
        assert m["stair_riser_height"] == 6.5 and 4 <= m["stair_riser_height"] <= 7          # 1011.5.2
        assert m["stair_tread_depth"] == 11                                                 # 1011.5.2
        assert m["stair_riser_variation"] == 0                                              # 1011.5.4
        assert m["stair_headroom"] >= 80                                                    # 1011.3
        assert m["stair_clear_width"] == 44                                                 # 1011.2
        assert more["stair_handrail_sides"] == 2 and more["stair_clear_width_at_handrail"] == 37   # 1014.1, 1014.8
    assert guards["g1"]["measures"] == {"guard_height": 42, "guard_opening_sphere": 4}      # 1015.3, 1015.4


def test_the_failing_stair_breaks_exactly_the_limits_it_was_built_to():
    stairs, guards = _measured("failing")
    assert {f: stairs[f]["measures"]["stair_riser_height"] for f in stairs} == {"f1": 7.5, "f2": 7.5}   # > 7 in
    assert stairs["f1"]["measures"]["stair_headroom"] >= 80
    assert stairs["f2"]["measures"]["stair_headroom"] == 76                                 # < 80 in under the beam
    assert stairs["f1"]["more"]["stair_handrail_sides"] == 2
    assert stairs["f2"]["more"]["stair_handrail_sides"] == 1                                # its north side has none
    assert guards["g1"]["measures"]["guard_height"] == 36                                   # < 42 in
    for f in ("f1", "f2"):
        assert stairs[f]["measures"]["stair_tread_depth"] == 11 and stairs[f]["measures"]["stair_clear_width"] == 44
