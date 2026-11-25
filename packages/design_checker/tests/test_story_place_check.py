"""The story's place against the grade plane (model_measurement/routes/story_place.py) through the Building Code
check: the ground the lot facts state reaches the routes (check._story_ground, egress.check's `ground`), and a place
not measured never lets a single-exit row pass.

The building is the four-unit apartment (four_unit_apartment, as the Revit reader reads it) with its east stair's
doors unmarked, so each story has one exit (the west stair, travel 53.95 ft; the east stair a storeroom), stated
Group A-3 with no sprinkler system, no fixed seating or special spaces and no occupant load increase (7.1 to 8.9
occupants a story). Table 1006.3.4(2): Group A's first story above or below grade plane
may have one exit (49 occupants, 75 ft); the second story isn't in Group A's row, so one exit there is too few. The
story's rooms exiting directly outside (1006.3.4 item 2) is measured in a later step: set to no here, so only the
place decides."""

import copy
import sys

import pytest

from design_checker import check, egress
from rule_format.rulebook import REPO, Context

sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
import make_ny_build_data as build  # noqa: E402

ROW = "general.bc_table_1006_3_4_2__a_b_e_f_m_u"
PLACE = "regulations/jurisdictions/new_york/ithaca_city"
VALUES = {"use": "multiple_family", "dwelling_units": 4}
SPOTS = [[30, -1.5], [61.5, 15], [30, 31.5], [-1.5, 15]]         # 1.5 ft outside each wall's middle


@pytest.fixture(scope="module")
def one_exit():
    i = build.interior_of()
    names = {r["id"]: r["name"].upper() for r in i["rooms"]}
    for d in i["doors"]:
        if d.get("exit_id") and "EAST" in names.get(d["exit_id"], ""):
            d.pop("exit_kind"), d.pop("exit_id")
    for r in i["rooms"]:                     # the east stair, no longer an exit, holds a load of its own: stated
        if "STAIR EAST" in r["name"].upper():
            r["function"] = "accessory_storage_mechanical"
    i["building"] = {**i["building"], "occupancy_groups": ["A-3"], "sprinkler_system": "none",
                     "assembly_fixed_seating": False, "special_egress_spaces": False, "occupant_load_increased": False}
    return i


def _result(interior, ground, monkeypatch):
    real = egress.measure_routes

    def measured(desc, **kw):
        got = real(desc, **kw)
        for s in got["parts"]["story"]:
            s["not_measured"].pop("story_rooms_exit_directly_outside", None)
            s["measures"]["story_rooms_exit_directly_outside"] = False
        return got
    monkeypatch.setattr(egress, "measure_routes", measured)
    allowed = Context.for_jurisdiction(REPO / PLACE).allowed()
    got = egress.check(egress.laws(PLACE), copy.deepcopy(interior), VALUES, allowed, ground=ground)
    return got["results"][ROW], {s["name"]: s for s in got["interior"]["parts"]["story"]}


def test_on_flat_ground_at_its_floor_level_2_is_the_second_story_and_one_exit_fails(one_exit, monkeypatch):
    result, stories = _result(one_exit, {"flat": 0.0}, monkeypatch)
    assert stories["Level 2"]["measures"]["story_second_above_grade_plane"] is True
    assert result == "fail"


def test_on_ground_5_ft_up_level_2_may_be_the_first_or_second_so_one_exit_needs_review(one_exit, monkeypatch):
    """Ground at 5 ft: Level 1 may be a basement (Level 2 the first story, one exit allowed) or, with ground lower
    somewhere beside it (never ruled out: a basement is never proven), the first story above (Level 2 the second,
    one exit too few): needs review, never a pass."""
    for interior in (one_exit, {**one_exit, "doors": [d for d in one_exit["doors"] if "outside" not in d["sides"]]}):
        result, stories = _result(interior, {"flat": 5.0}, monkeypatch)
        assert stories["Level 1"]["measures"]["story_first_above_or_below_grade"] is True
        assert "story_first_above_or_below_grade" not in stories["Level 2"]["measures"]
        assert result == "needs_review"


@pytest.mark.parametrize("ground", [None, {"none": "none stated"}, {"spots": [p + [4] for p in SPOTS]},
                                    {"spots": [p + [0] for p in SPOTS[:3]]}])
def test_a_place_not_measured_never_passes_the_single_exit_row(one_exit, monkeypatch, ground):
    """Spot grades at 4 ft: Level 2 (10 ft) may be the first story above (a basement below) or the second: not
    measured, and the row needs review, never a pass (it passes on flat ground at 5 ft, fails at 0). Three walls
    spotted, or no ground: nothing placed."""
    result, stories = _result(one_exit, ground, monkeypatch)
    assert "story_first_above_or_below_grade" not in stories["Level 2"]["measures"]
    assert result == "needs_review"


def test_the_lot_facts_ground_reaches_the_routes():
    """check._story_ground: the lot facts' stated flat ground, spot grades, existing ground (none) and ground only
    assumed flat (none, with the place's own reason)."""
    ithaca = {"jurisdiction": PLACE}
    assert check._story_ground({**ithaca, "ground_is_flat": True, "grade_elevation": 2}) == {"flat": 2.0}
    assert check._story_ground({**ithaca, "grade_points": [[0, 0, 1]], "grade_from": "finished_spots"}) ==         {"spots": [[0, 0, 1]]}
    assert "none" in check._story_ground({**ithaca, "grade_points": [[0, 0, 1]]})      # Revit's plain spot grades
    assert "none" in check._story_ground({**ithaca, "grade_is": "existing", "grade_points": [[0, 0, 1]]})
    assumed = check._story_ground({**ithaca, "ground_is_flat": True, "grade_elevation": 0, "ground_assumed": "flat",
                                   "ground_fall": 3})
    assert "none" in assumed and "assumed flat" in assumed["none"]
