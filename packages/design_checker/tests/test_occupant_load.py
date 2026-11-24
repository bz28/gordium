"""The Building Code's occupant loads from each room's stated function (design_checker/occupant_load.py, section group 3
of docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md), worked by hand on the four-unit eval building
(test_data/test_sites/new_york/ithaca_city/four_unit_apartment/apartment.yaml): the inside of the exterior walls is
60 x 30 = 1,800 sq ft a story (202 FLOOR AREA, GROSS); each apartment 60 x 11.5 = 690 sq ft inside its walls, function
residential (Table 1004.5: 200 gross); the stairs are exits and the corridor a corridor, so they hold no load of their
own and their area is the apartments' support."""

import copy
import random
import re
import sys

import pytest

from design_checker import egress, occupant_load
from design_checker.egress import OCCUPANT_LOAD_FACTORS
from model_measurement.routes import measure
from rule_format.rulebook import REPO, load

sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))       # the route tests' small layouts
import make_ny_build_data as build  # noqa: E402
from routes_layouts import description, door, rect, room  # noqa: E402

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
FACTORS = occupant_load.factors_of(NY / OCCUPANT_LOAD_FACTORS)


_MEASURED = {}


def _routes(desc):
    """The apartment's routes measured once (a room's function changes no geometry, and measuring takes a minute)."""
    if "routes" not in _MEASURED:
        _MEASURED["routes"] = measure(desc)
    return copy.deepcopy(_MEASURED["routes"])


def _loads(desc, building=None):
    parts = _routes(desc)["parts"]
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


# decision 1a's layouts (packages/model_measurement/tests/test_routes_served.py, test 20, worked there by hand): a
# corridor 0 to 40 by 0 to 6 with its exit; a room 10 to 20 by 6.5 to 16.5 (100 sq ft) off it; no story outline, so
# only net functions give a load here
CORRIDOR = room("c", rect(0, 0, 40, 6))
EXIT = door("x", (15, -0.25), (1, 0), ("c", "outside"), exit_id="A")


def _kitchen_closet(kitchen_fn, closet_fn):
    """A kitchen (100 sq ft) and a closet 10 to 14 by 17 to 20 (12 sq ft) whose only door opens into the kitchen:
    the closet is served through the kitchen (decision 1a)."""
    k = room("k", rect(10, 6.5, 20, 16.5), use="kitchen", lockable=False, function=kitchen_fn)
    cl = room("cl", rect(10, 17, 14, 20), use="closet", lockable=True,
              **({"function": closet_fn} if closet_fn else {}))
    return description([CORRIDOR, k, cl], [EXIT, door("kc", (15, 6.25), (1, 0), ("k", "c")),
                                            door("clk", (12, 16.75), (1, 0), ("cl", "k"))])


def _space(parts, pid):
    return next(p for p in parts["space"] if p["id"] == pid)


def test_a_room_a_loaded_closet_is_served_through_carries_it_so_its_own_load_isnt_given():
    """1004.2: the occupant load of a room others egress through adds theirs. A closet with no function holds none,
    so the kitchen's is its own, 100 / 20 = 5 (classroom, net); a closet stating one (exhibit gallery, 30 net: 12 /
    30 = 0.4) egresses through the kitchen, so the kitchen's 5 alone would understate it: not given, and why said.
    Review of group 3 (2026-11-24)."""
    desc = _kitchen_closet("classroom", None)
    parts = measure(desc)["parts"]
    assert _space(parts, "cl")["more"]["served_through"] == "k"
    occupant_load.apply(parts, desc, FACTORS, {"occupant_load_increased": False})
    assert _space(parts, "k")["measures"]["space_occupant_load"] == pytest.approx(5)
    desc = _kitchen_closet("classroom", "exhibit_gallery_museum")
    parts = measure(desc)["parts"]
    occupant_load.apply(parts, desc, FACTORS, {"occupant_load_increased": False})
    k = _space(parts, "k")
    assert "space_occupant_load" not in k["measures"] and not (k.get("readings") or {}).get("space_occupant_load")
    assert "cl egresses through it (1004.2" in k["not_measured"]["space_occupant_load"]
    assert _space(parts, "cl")["measures"]["space_occupant_load"] == pytest.approx(12 / 30)
    desc = _kitchen_closet("classroom", "apartment")                  # the closet's own load not worked out
    parts = measure(desc)["parts"]
    occupant_load.apply(parts, desc, FACTORS, {"occupant_load_increased": False})
    assert "space_occupant_load" not in _space(parts, "k")["measures"]


def test_a_load_served_through_a_chain_reaches_every_room_on_it():
    """Decision 1a's chain (test_routes_served.py: a closet off storeroom 13 off storeroom 14 off the corridor): a
    closet stating a function (12 sq ft, exhibit gallery, 30 net) egresses through 13 and 14, so 14's own load (100 sq
    ft, vocational shop, 50 net: 2) isn't its cumulative one, though 13 between them has no function."""
    def chain(closet_fn):
        return description([CORRIDOR, room("s14", rect(10, 6.5, 20, 16.5), use="accessory_storage", lockable=False,
                                           function="vocational_shop"),
                            room("s13", rect(10, 17, 20, 27), use="accessory_storage", lockable=False),
                            room("cl", rect(13, 27.5, 17, 30.5), use="closet", lockable=True,
                                 **({"function": closet_fn} if closet_fn else {}))],
                           [EXIT, door("s14c", (15, 6.25), (1, 0), ("s14", "c")),
                            door("s13", (15, 16.75), (1, 0), ("s13", "s14")),
                            door("cls13", (15, 27.25), (1, 0), ("cl", "s13"))])
    desc = chain(None)
    parts = measure(desc)["parts"]
    occupant_load.apply(parts, desc, FACTORS, {"occupant_load_increased": False})
    assert _space(parts, "s14")["measures"]["space_occupant_load"] == pytest.approx(2)
    desc = chain("exhibit_gallery_museum")
    parts = measure(desc)["parts"]
    occupant_load.apply(parts, desc, FACTORS, {"occupant_load_increased": False})
    s14 = _space(parts, "s14")
    assert "space_occupant_load" not in s14["measures"] and "cl egresses through it" in s14["not_measured"][
        "space_occupant_load"]
    assert _space(parts, "cl")["measures"]["space_occupant_load"] == pytest.approx(12 / 30)


def test_a_function_on_a_room_marked_a_corridor_is_said_never_dropped(apartment):
    """A room marked a corridor is never a space, so a function stated on it would give no load: its story's load is
    left not worked out, saying why; the other story's still is."""
    desc = copy.deepcopy(apartment)
    next(r for r in desc["rooms"] if r["id"] == "L1C")["function"] = "mercantile"
    parts = _loads(desc, {"occupant_load_increased": False})
    l1, l2 = parts["story"]
    assert "story_occupant_load" not in l1["measures"] and not (l1.get("readings") or {}).get("story_occupant_load")
    assert "is marked a corridor, yet states the function 'mercantile'" in l1["not_measured"]["story_occupant_load"]
    assert _values(l2, "story_occupant_load") == pytest.approx([2 * 690 / 200, 1800 / 200])


# The walk over group 3's facts through the whole Building Code check: each apartment's function (net, gross, sent
# elsewhere, none, not the table's), whether others pass through it, a function on a stair (an exit: none) or on the
# corridor, the building's group, sprinkler system and 1004.5.1 increase. The routes are the apartment's as measured
# (a function changes no geometry; `pass_through` is read here only by occupant_load.py, so the routes' own figures
# stay the drawn building's).
WALK_FUNCTIONS = (None, "residential", "business", "dormitory", "classroom", "assembly_concentrated", "mercantile",
                  "exercise_room", "storage_stock_shipping", "assembly_fixed_seats", "concentrated_business",
                  "no_such_function")
WALK_GROUPS = (["R-2"], ["B"], ["A-2"], ["M"], ["E"], ["S-1"], ["F-1"], ["R-1"], ["I-1"], ["R-2", "B"])
WALK_CASES = 40
LOADS = ("space_occupant_load", "story_occupant_load")
APARTMENTS = ("S", "N")                                     # each 60 x 11.5 = 690 sq ft inside its walls
EPS = 1e-9


def _load_rules():
    """The Building Code rules that read an occupant load (their check, review_when or applies_when names one)."""
    rules = load(NY / "5_building_code_rules/drafted/general.yaml")["rules"]
    return {r["id"] for r in rules if re.search(r"(space|story)_occupant_load", str(
        [r.get(k) for k in ("check", "review_when", "applies_when")]))}


def _collapse(parts, how):
    """One reading of the occupant loads: `low` / `high` puts each two-reading load at that end; `zero` / `huge`
    gives each load not worked out 0 or a million (a pass on a load not worked out must hold whatever it is)."""
    for kind, name in (("space", LOADS[0]), ("story", LOADS[1])):
        for p in parts.get(kind) or []:
            rs = (p.get("readings") or {}).get(name)
            if how in ("low", "high") and rs:
                p["measures"][name] = (min if how == "low" else max)(r["value"] for r in rs)
                del p["readings"][name]
                p["not_measured"].pop(name, None)
            elif how in ("zero", "huge") and not rs and name not in p["measures"]:
                p["measures"][name] = 0 if how == "zero" else 1e6
                p["not_measured"].pop(name, None)
    return parts


def _rows(got, rules):
    out = {}
    for r in got["rows"]:
        if r["rule"] in rules:
            out.setdefault((r["rule"], r["id"]), []).append(r["outcome"])
    return out


def _walk_case(rng, apartment):
    desc = copy.deepcopy(apartment)
    for r in desc["rooms"]:
        kind = r["id"][2:]
        if kind in APARTMENTS:
            r["function"] = rng.choice(WALK_FUNCTIONS)
            r["pass_through"] = rng.random() < 0.2
        elif kind in ("SW", "SE") and rng.random() < 0.3:
            r["function"] = rng.choice(WALK_FUNCTIONS[1:])      # an exit enclosure holds none, whatever it states
        elif kind == "C" and rng.random() < 0.1:
            r["function"] = "mercantile"
        if r.get("function") is None:
            r.pop("function", None)
    increase = rng.choice((None, True, False))
    desc["building"] = {"occupancy_groups": rng.choice(WALK_GROUPS),
                        "sprinkler_system": rng.choice(("none", "nfpa_13")),
                        **({} if increase is None else {"occupant_load_increased": increase})}
    return desc, increase


def _check_the_laws_loads(desc, increase, parts):
    """1004.5 (never less than area / factor; gross apportioned over the story's support), 1004.5.1 (at least one per
    7 sq ft while the increase isn't stated not taken), 1004.2 (a room passed through: not given), and a story's
    load given only where every room's is worked out, its lower end their sum."""
    rooms = {r["id"]: r for r in desc["rooms"]}
    for story in parts["story"]:
        level = story["id"]
        apts = [rooms[level + a] for a in APARTMENTS]
        entries = [FACTORS["functions"].get(r.get("function")) if isinstance(r.get("function"), str) else None
                   for r in apts]
        worked = [e is not None and e["factor"] is not None for e in entries]
        net = sum(690 for e, w in zip(entries, worked) if w and e["area"] == "net")
        gross = sum(690 for e, w in zip(entries, worked) if w and e["area"] == "gross")
        for r, e, w in zip(apts, entries, worked):
            p = next(q for q in parts["space"] if q["id"] == r["id"])
            got = _values(p, LOADS[0])
            if not w or r["pass_through"]:
                assert got == [] and p["not_measured"][LOADS[0]], (r["id"], r.get("function"))
                continue
            assert min(got) == pytest.approx(690 / e["factor"]), r["id"]
            if e["area"] == "gross":
                assert max(got) >= 690 * (1800 - net) / gross / e["factor"] - EPS, r["id"]
            if increase is not False:
                assert max(got) >= 690 / 7 - EPS, r["id"]
        for stair in ("SW", "SE"):
            assert _values(next(q for q in parts["space"] if q["id"] == level + stair), LOADS[0]) == []
        got = _values(story, LOADS[1])
        if not all(worked) or rooms[level + "C"].get("function"):
            assert got == [] and story["not_measured"][LOADS[1]], level
            continue
        assert min(got) == pytest.approx(sum(690 / e["factor"] for e in entries)), level
        if increase is not False:
            assert max(got) >= 1800 / 7 - EPS, level


def test_a_walk_over_group_3s_facts_never_passes_where_a_reading_or_a_load_not_worked_out_could_fail(
        apartment, monkeypatch):
    """Every row of every rule reading an occupant load: a pass holds at both ends of the load's readings (and,
    where the load isn't worked out, at no load and at a million), a fail fails at both; the loads themselves are the
    law's (above). 40 seeded cases (the seed fixed, so a failure names its case)."""
    routes = _routes(apartment)
    monkeypatch.setattr(egress, "measure_routes", lambda interior: copy.deepcopy(routes))
    applied = occupant_load.apply
    laws = egress.laws("regulations/jurisdictions/new_york/ithaca_city")
    rules, rng, seen = _load_rules(), random.Random(1004), set()
    values = {"use": "multiple_family", "dwelling_units": 4}

    def run(desc, how=None):
        monkeypatch.setattr(occupant_load, "apply",
                            applied if how is None else lambda *a: _collapse(applied(*a), how))
        return egress.check(laws, desc, values, {"use": set()})

    assert len(rules) >= 20
    for case in range(WALK_CASES):
        desc, increase = _walk_case(rng, apartment)
        base = run(desc)
        _check_the_laws_loads(desc, increase, base["interior"]["parts"])
        rows = _rows(base, rules)
        variants = {how: _rows(run(desc, how), rules) for how in ("low", "high", "zero", "huge")}
        for key, outcomes in rows.items():
            seen.update(outcomes)
            for how, other in variants.items():
                if "pass" in outcomes:
                    assert set(other[key]) <= {"pass", "not_applicable"}, (case, key, how, other[key], desc["building"])
                if "fail" in outcomes and how in ("low", "high"):
                    assert set(other[key]) == {"fail"}, (case, key, how, other[key], desc["building"])
    assert {"pass", "fail", "needs_review"} <= seen          # the walk reaches every verdict
