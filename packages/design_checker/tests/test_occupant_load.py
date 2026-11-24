"""The Building Code's occupant loads from each room's stated function (design_checker/occupant_load.py, section group 3
of docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md), worked by hand on the four-unit eval building
(test_data/test_sites/new_york/ithaca_city/four_unit_apartment/apartment.yaml): the inside of the exterior walls is
60 x 30 = 1,800 sq ft a story (202 FLOOR AREA, GROSS); each apartment 60 x 11.5 = 690 sq ft inside its walls, function
residential (Table 1004.5: 200 gross); the stairs are exits and the corridor a corridor, so they hold no load of their
own and their area is the apartments' support."""

import copy
import sys

import pytest

from design_checker import occupant_load
from design_checker.egress import OCCUPANT_LOAD_FACTORS
from model_measurement.routes import measure
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
import make_ny_build_data as build  # noqa: E402

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
FACTORS = occupant_load.factors_of(NY / OCCUPANT_LOAD_FACTORS)


_MEASURED = {}


def _loads(desc, building=None):
    """The routes measured once (a room's function changes no geometry, and measuring takes half a minute)."""
    if "parts" not in _MEASURED:
        _MEASURED["parts"] = measure(desc)["parts"]
    parts = copy.deepcopy(_MEASURED["parts"])
    occupant_load.apply(parts, desc, FACTORS, building)
    return parts


def _values(part, name):
    if name in part["measures"]:
        return [part["measures"][name]]
    return [r["value"] for r in (part.get("readings") or {}).get(name) or []]


@pytest.fixture(scope="module")
def apartment():
    return build.interior_of()


def test_each_apartment_and_story_by_hand_with_the_increase_ruled_out(apartment):
    parts = _loads(apartment, {"occupant_load_increased": False})
    share = 1800 / 1380                                      # the story's gross over the gross rooms' areas
    for p in parts["space"]:
        if p["name"].startswith("Apartment"):
            assert _values(p, "space_occupant_load") == pytest.approx([690 / 200, 690 * share / 200])
        else:                                                # the stair enclosures: exits, no load of their own
            assert _values(p, "space_occupant_load") == []
    for s in parts["story"]:
        assert s["measures"]["story_gross_floor_area"] == pytest.approx(1800)
        assert _values(s, "story_occupant_load") == pytest.approx([2 * 690 / 200, 1800 / 200])


def test_the_upper_reading_is_one_per_7_sq_ft_while_1004_5_1_isnt_ruled_out(apartment):
    parts = _loads(apartment)
    apt = next(p for p in parts["space"] if p["name"].startswith("Apartment"))
    assert _values(apt, "space_occupant_load") == pytest.approx([690 / 200, 690 / 7])
    assert _values(parts["story"][0], "story_occupant_load") == pytest.approx([2 * 690 / 200, 1800 / 7])


def test_a_room_with_no_function_leaves_it_and_its_story_unmeasured(apartment):
    desc = copy.deepcopy(apartment)
    for r in desc["rooms"]:
        r.pop("function", None)
    parts = _loads(desc, {"occupant_load_increased": False})
    apt = next(p for p in parts["space"] if p["name"].startswith("Apartment"))
    assert _values(apt, "space_occupant_load") == []
    assert "Gordium: Function" in apt["not_measured"]["space_occupant_load"]
    assert "story_occupant_load" not in parts["story"][0]["measures"]
    assert "Apartment" in parts["story"][0]["not_measured"]["story_occupant_load"]


def test_a_net_function_is_one_value_and_a_function_sent_elsewhere_is_a_persons(apartment):
    desc = copy.deepcopy(apartment)
    for r in desc["rooms"]:
        if r.get("function"):
            r["function"] = "classroom"                       # 20 net
    parts = _loads(desc, {"occupant_load_increased": False})
    apt = next(p for p in parts["space"] if p["name"].startswith("Apartment"))
    assert apt["measures"]["space_occupant_load"] == pytest.approx(690 / 20)
    assert parts["story"][0]["measures"]["story_occupant_load"] == pytest.approx(2 * 690 / 20)
    for r in desc["rooms"]:
        if r.get("function"):
            r["function"] = "assembly_fixed_seats"            # 1004.6: the seats
    parts = _loads(desc, {"occupant_load_increased": False})
    apt = next(p for p in parts["space"] if p["name"].startswith("Apartment"))
    assert "1004.6" in apt["not_measured"]["space_occupant_load"]
    for r in desc["rooms"]:
        if r.get("function"):
            r["function"] = "apartment"                       # no such function
    apt = next(p for p in _loads(desc)["space"] if p["name"].startswith("Apartment"))
    assert "none of Table 1004.5's" in apt["not_measured"]["space_occupant_load"]


def test_every_factor_is_its_rows_number_on_the_second_reading():
    """Each frozen factor is a number the second reading of Table 1004.5 holds (text_verification.yaml), on the row
    the file quotes, and its quote ends in the factor and its 'gross' or 'net'."""
    from rule_format.rulebook import load
    data = load(NY / OCCUPANT_LOAD_FACTORS)
    second = load(NY / "text_verification.yaml")["pieces"]["Table 1004.5"]["second_reading_numbers"]
    for fid, e in data["functions"].items():
        q = e["source"]["quote"]
        if e["factor"] is None:
            assert e["elsewhere"] and e["area"] is None, fid
            continue
        # numbers.py reads "gross" as the number's unit, "net" not: a gross cell is "300 gross", a net one "30"
        assert (f"{e['factor']} gross" if e["area"] == "gross" else str(e["factor"])) in second, fid
        assert q.endswith(f"{e['factor']} {e['area']}"), (fid, q)
    assert data["increase_cap"]["sq_ft_per_occupant"] == 7
    assert "one occupant per 7 square feet" in data["increase_cap"]["source"]["quote"]


def test_a_walk_over_every_function_never_gives_less_than_the_table_or_the_increase_cap(apartment):
    """Section group 3's tightenings, walked: for every Table 1004.5 function with a factor, each room's occupant
    load is never less than its area / factor (1004.5: 'not less than'); a gross factor's upper reading is at least
    its grossed-up share; and unless 1004.5.1's increase is stated not taken (no, or not stated), the upper reading is
    at least one per 7 sq ft, for the room and for the story. A function the table sends elsewhere never gives one."""
    for fid, e in FACTORS["functions"].items():
        for increase in (False, True, None):
            desc = copy.deepcopy(apartment)
            for r in desc["rooms"]:
                if r.get("function"):
                    r["function"] = fid
            building = None if increase is None else {"occupant_load_increased": increase}
            parts = _loads(desc, building)
            for p in parts["space"]:
                if not p["name"].startswith("Apartment"):
                    continue
                got = _values(p, "space_occupant_load")
                if e["factor"] is None:
                    assert got == [], fid
                    continue
                assert min(got) == pytest.approx(690 / e["factor"]), fid
                if e["area"] == "gross":
                    assert max(got) >= 690 * 1800 / 1380 / e["factor"] - 1e-9, fid
                if increase is not False:
                    assert max(got) >= 690 / 7 - 1e-9, (fid, increase)
            story = _values(parts["story"][0], "story_occupant_load")
            if e["factor"] is not None:
                assert min(story) == pytest.approx(2 * 690 / e["factor"]), fid
                if increase is not False:
                    assert max(story) >= 1800 / 7 - 1e-9, (fid, increase)
