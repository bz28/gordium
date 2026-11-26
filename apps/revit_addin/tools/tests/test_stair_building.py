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
        assert more["stair_handrail_sides"] == 2 and more["stair_clear_width_at_handrail"] == 37   # 1011.11, 1014.9
    assert guards["g1"]["measures"] == {"guard_height": 42, "guard_opening_sphere": 3.5}    # 1015.3, 1015.4 (under 4)
    # the header's own headroom figures (review round 3)
    assert {f: stairs[f]["measures"]["stair_headroom"] for f in stairs} == {"f1": 98.5, "f2": 108}


def test_the_failing_stair_breaks_exactly_the_limits_it_was_built_to():
    stairs, guards = _measured("failing")
    assert {f: stairs[f]["measures"]["stair_riser_height"] for f in stairs} == {"f1": 8, "f2": 8}   # > 7 3/4 in
    assert stairs["f1"]["measures"]["stair_headroom"] == 124                               # its 132 in slab, 8 in up
    assert stairs["f2"]["measures"]["stair_headroom"] == 76                                 # < 80 in under the beam
    assert stairs["f1"]["more"]["stair_handrail_sides"] == 2
    assert stairs["f2"]["more"]["stair_handrail_sides"] == 1                                # its north side has none
    assert guards["g1"]["measures"]["guard_height"] == 34                                   # < 36 in
    # nothing else broken (review round 1): every other figure the rules read as the compliant one's
    for f in ("f1", "f2"):
        m = stairs[f]["measures"]
        assert m["stair_tread_depth"] == 11 and m["stair_clear_width"] == 44 and m["stair_riser_variation"] == 0
    assert stairs["f1"]["more"]["stair_clear_width_at_handrail"] == 37
    assert stairs["f2"]["more"]["stair_clear_width_at_handrail"] == 40.5                  # its one handrail (round 4)
    assert guards["g1"]["measures"]["guard_opening_sphere"] == 3.5


def test_each_handrail_extends_past_its_flights_nosings():
    # 1014.7 (review round 4): handrails not continuous between flights run 12 in past the top nosing and one tread
    # past the bottom one; measured along the run from each flight's own first and top nosings
    import yaml
    for variant in ("compliant", "failing"):
        d = yaml.safe_load((HERE / f"stair_enclosure_{variant}.yaml").read_text(encoding="utf-8"))
        for st in d["stairs"]:
            first, top = st["nosings"][0][0][0], st["nosings"][-1][0][0]
            up = 1 if top > first else -1
            for rail in st["handrails"]:
                xs = [x * up for x, _ in rail["inner_edge"]]
                assert min(xs) <= first * up - 11 and max(xs) >= top * up + 12, (variant, st["id"], rail)


def test_the_stair_is_marked_outside_every_dwelling_unit_and_level_2_is_open_over_the_flights():
    # review round 1: with no exit mark a stair in an R-2 building may be within a dwelling unit, where 1011.5.2,
    # 1011.11 and 1015.3 allow 7 3/4 in risers, one handrail and 36 in guards; and Level 2's floor is only its landing,
    # so its guarded edge really drops onto flight 1
    import yaml
    for variant in ("compliant", "failing"):
        d = yaml.safe_load((HERE / f"stair_enclosure_{variant}.yaml").read_text(encoding="utf-8"))
        doors = {x["level"]: x for x in d["doors"]}
        assert set(doors) == {"L1", "L2"}
        assert all(x["exit_kind"] == "exit_enclosure" and x["sides"][1].endswith("S") for x in doors.values())
        l2 = next(r for r in d["rooms"] if r["id"] == "L2S")
        assert max(x for x, _ in l2["floor"]) <= 44
        # review round 2: each door's exit is the enclosure it enters, so the routes read both stair rooms as the exit
        from model_measurement.routes import measure
        routes = measure(d)
        assert routes["problems"] == [], routes["problems"]
        spaces = {p["id"]: p for p in routes["parts"]["space"]}
        assert spaces["L1S"]["measures"]["space_is_exit"] is True and spaces["L2S"]["measures"]["space_is_exit"] is True


def test_the_two_values_kept_with_the_extra_values_are_given_to_the_rules_as_they_were():
    # section group 7c (approved 2026-11-26): the handrail sides and the clear width at the handrails, worked out and
    # tested since 2026-11-13 and kept in `more`, are now measures the rules read, equal to what `more` holds
    for variant in ("compliant", "failing"):
        stairs, _ = _measured(variant)
        for f, p in stairs.items():
            for name in ("stair_handrail_sides", "stair_clear_width_at_handrail"):
                assert p["measures"][name] == p["more"][name], (variant, f, name)
                assert name not in p["not_measured"]
