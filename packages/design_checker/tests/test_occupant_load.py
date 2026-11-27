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
from rule_format.rulebook import REPO, Context, load

sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))       # the route tests' small layouts
import make_ny_build_data as build  # noqa: E402
from routes_layouts import description, door, rect, room  # noqa: E402

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
FACTORS = occupant_load.factors_of(NY / OCCUPANT_LOAD_FACTORS)
ALLOWED = Context.for_jurisdiction(REPO / "regulations/jurisdictions/new_york/ithaca_city").allowed()   # its uses


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
    assert apt["not_measured"]["space_occupant_load"] == occupant_load.NOT_GIVEN
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
    """Decision 1a's chain (test_routes_served.py's storeroom chain, 13 drawn here as a closet: a closet off closet 13
    off storeroom 14 off the corridor): a closet stating a function (12 sq ft, exhibit gallery, 30 net) egresses
    through 13 and 14, so 14's own load (100 sq ft, vocational shop, 50 net: 2) isn't its cumulative one, though 13
    between them holds none."""
    def chain(closet_fn):
        return description([CORRIDOR, room("s14", rect(10, 6.5, 20, 16.5), use="accessory_storage", lockable=False,
                                           function="vocational_shop"),
                            room("s13", rect(10, 17, 20, 27), use="closet", lockable=False),
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


def test_a_function_on_a_room_marked_a_corridor_or_an_exit_is_said_never_dropped(apartment):
    """A room marked a corridor is never a space, and a space that is itself an exit holds no load, so a function
    stated on either would give none: its story's load is left not worked out, saying why; the other story's still is
    (an exit's: review of group 3, round 1, 2026-11-24)."""
    for rid, words in (("L1C", "'s use is corridor, yet it states the function 'mercantile'"),
                       ("L1SW", "is itself an exit (a door into it is an exit enclosure's or passageway's), yet "
                                "states the function 'mercantile'")):
        desc = copy.deepcopy(apartment)
        next(r for r in desc["rooms"] if r["id"] == rid)["function"] = "mercantile"
        parts = _loads(desc, {"occupant_load_increased": False})
        l1, l2 = parts["story"]
        assert "story_occupant_load" not in l1["measures"] and not (l1.get("readings") or {}).get(
            "story_occupant_load"), rid
        assert words in l1["not_measured"]["story_occupant_load"], rid
        assert _values(l2, "story_occupant_load") == pytest.approx([2 * 690 / 200, 1800 / 200])


def test_a_room_holding_no_load_says_why_in_words_that_are_true():
    """Review of group 3, round 1 (P3, 2026-11-24): an exit, a closet with no function, and a story of no loaded
    room each say why they hold none (never the routes' old 'no mark for it in the model yet': the Function mark
    exists); a story whose rooms outgrow its gross floor area says that, not that the area isn't measured."""
    parts = {"story": [{"id": "L1", "measures": {"story_gross_floor_area": 100}, "not_measured": {}}],
             "space": [{"id": "x", "within": "L1", "measures": {"space_is_exit": True, "space_floor_area": 50},
                        "not_measured": {"space_occupant_load": "Gordium has no mark for it in the model yet"}},
                       {"id": "cl", "within": "L1", "measures": {"space_is_exit": False, "space_floor_area": 20},
                        "not_measured": {"space_occupant_load": "Gordium has no mark for it in the model yet"}}]}
    desc = {"rooms": [{"id": "x", "use": "other"}, {"id": "cl", "use": "closet"}]}
    occupant_load.apply(parts, desc, FACTORS, {"occupant_load_increased": False})
    x, cl = parts["space"]
    assert x["not_measured"]["space_occupant_load"] == occupant_load.IS_EXIT
    assert "a closet with no function stated holds no occupant load" in cl["not_measured"]["space_occupant_load"]
    assert parts["story"][0]["not_measured"]["story_occupant_load"] == occupant_load.STORY_NONE
    over = {"story": [{"id": "L1", "measures": {"story_gross_floor_area": 100}, "not_measured": {}}],
            "space": [{"id": "b", "within": "L1", "measures": {"space_is_exit": False, "space_floor_area": 300},
                       "not_measured": {}}]}
    occupant_load.apply(over, {"rooms": [{"id": "b", "use": "other", "function": "business"}]}, FACTORS,
                        {"occupant_load_increased": False})
    assert over["space"][0]["not_measured"]["space_occupant_load"] == occupant_load.AREAS_OVER
    over["story"][0]["measures"].pop("story_gross_floor_area")
    over["space"][0]["not_measured"].clear()
    occupant_load.apply(over, {"rooms": [{"id": "b", "use": "other", "function": "business"}]}, FACTORS,
                        {"occupant_load_increased": False})
    assert over["space"][0]["not_measured"]["space_occupant_load"] == occupant_load.GROSS_NOT_MEASURED


# The walk over group 3's facts through the whole Building Code check: each apartment's function (net, gross, sent
# elsewhere, none, not the table's), whether others pass through it, a function on a stair (an exit: none) or on the
# corridor, the building's group, sprinkler system and 1004.5.1 increase. The routes are the apartment's as measured
# (a function changes no geometry; `pass_through` is read here only by occupant_load.py, so the routes' own figures
# stay the drawn building's).
WALK_FUNCTIONS = (None, "residential", "business", "dormitory", "classroom", "assembly_concentrated", "mercantile",
                  "exercise_room", "storage_stock_shipping", "assembly_fixed_seats", "concentrated_business",
                  "no_such_function")
WALK_GROUPS = (["R-2"], ["B"], ["A-2"], ["M"], ["E"], ["S-1"], ["F-1"], ["R-1"], ["I-1"], ["I-2"], ["R-2", "B"])
WALK_CASES = 40
LOADS = ("space_occupant_load", "story_occupant_load", "corridor_occupant_load")
APARTMENTS = ("S", "N")                                     # each 60 x 11.5 = 690 sq ft inside its walls
EPS = 1e-9


def _load_rules():
    """The Building Code rules that read an occupant load (their check, review_when or applies_when names one)."""
    rules = load(NY / "5_building_code_rules/drafted/general.yaml")["rules"]
    return {r["id"] for r in rules if re.search(r"(space|story|corridor)_occupant_load", str(
        [r.get(k) for k in ("check", "review_when", "applies_when")]))}


def _collapse(parts, how):
    """One reading of the occupant loads: `low` / `high` puts each two-reading load at that end; `zero` / `huge`
    gives each load not worked out 0 or a million (a pass on a load not worked out must hold whatever it is)."""
    for kind, name in (("space", LOADS[0]), ("story", LOADS[1]), ("corridor", LOADS[2])):
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
        elif kind in ("SW", "SE") and rng.random() < 0.15:
            r["function"] = rng.choice(WALK_FUNCTIONS[1:])      # an exit enclosure holds none: a function on it is said
        elif kind == "C" and rng.random() < 0.1:
            r["function"] = "mercantile"
        if r.get("function") is None:
            r.pop("function", None)
    increase = rng.choice((None, True, False))
    others = rng.choice((None, True, False, False))        # section group 4: other levels reach a corridor
    amb = rng.choice((None, True, False))                   # Table 1020.3: an ambulatory care facility
    desc["building"] = {"occupancy_groups": rng.choice(WALK_GROUPS),
                        "sprinkler_system": rng.choice(("none", "nfpa_13")),
                        **({} if increase is None else {"occupant_load_increased": increase}),
                        **({} if others is None else {occupant_load.OTHER_LEVELS: others}),
                        **({} if amb is None else {"ambulatory_care_facility": amb})}
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
        # section group 4: the corridor's load is none and the whole story's (its upper end), only where the
        # building says no other level's occupants reach it (1004.2.2, 1004.2.3, 1005.6); else not worked out
        corridor = next(c for c in parts["corridor"] if c["id"] == level + "C")
        if desc["building"].get(occupant_load.OTHER_LEVELS) is False and got:
            assert _values(corridor, LOADS[2]) == pytest.approx([0, max(got)]), level
        else:
            assert _values(corridor, LOADS[2]) == [] and corridor["not_measured"][LOADS[2]], level
        if not all(worked) or any(rooms[level + k].get("function") for k in ("C", "SW", "SE")):
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
    monkeypatch.setattr(egress, "measure_routes", lambda interior, **_: copy.deepcopy(routes))
    applied = occupant_load.apply
    laws = egress.laws("regulations/jurisdictions/new_york/ithaca_city")
    rules, rng, seen = _load_rules(), random.Random(1004), set()
    values = {"use": "multiple_family", "dwelling_units": 4}

    def run(desc, how=None):
        monkeypatch.setattr(occupant_load, "apply",
                            applied if how is None else lambda *a: _collapse(applied(*a), how))
        return egress.check(laws, desc, values, ALLOWED)

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


def test_a_storeroom_with_no_function_is_never_a_room_of_no_one():
    """Review of group 3, round 1 (2026-11-24): Table 1004.5 gives accessory storage its own factor (300 gross), and
    202 NET FLOOR AREA leaves out only closets and toilet rooms, so a storeroom with no function stated is a room
    like any other: its load, and its story's, aren't worked out. Before, it held none, and a story of net rooms only
    (a 100 sq ft classroom, 20 net, with a 12 sq ft storeroom off it) gave the classroom's 5 as the story's."""
    k = room("k", rect(10, 6.5, 20, 16.5), use="kitchen", lockable=False, function="classroom")
    st = room("st", rect(10, 17, 14, 20), use="accessory_storage", lockable=True)
    desc = description([CORRIDOR, k, st], [EXIT, door("kc", (15, 6.25), (1, 0), ("k", "c")),
                                           door("stk", (12, 16.75), (1, 0), ("st", "k"))])
    parts = measure(desc)["parts"]
    occupant_load.apply(parts, desc, FACTORS, {"occupant_load_increased": False})
    story = parts["story"][0]
    assert "story_occupant_load" not in story["measures"] and not (story.get("readings") or {}).get(
        "story_occupant_load")
    assert "st" in story["not_measured"]["story_occupant_load"]
    assert _space(parts, "st")["not_measured"]["space_occupant_load"] == occupant_load.NOT_GIVEN
    st["function"] = "accessory_storage_mechanical"                    # stated: 12 / 300 = 0.04, served through k
    parts = measure(desc)["parts"]
    occupant_load.apply(parts, desc, FACTORS, {"occupant_load_increased": False})
    assert "space_occupant_load" not in _space(parts, "k")["measures"]


def test_an_exits_reason_never_says_no_rule_asks_for_its_load(apartment, monkeypatch):
    """Review of group 3, round 2 (P3, 2026-11-24): an exit's reason once said 'the rules for the rooms exits serve
    ask nothing of it', which no rule's own words guarantee: it says only that an exit holds no load, so a rule
    reading one is a person's check. Group I-4's 1006.2.1 now lets an exit be (group 1's space_is_exit guard): on the
    apartment taken as I-4, with no sprinkler system, each stair enclosure's row passes, never a fail."""
    assert "ask nothing" not in occupant_load.IS_EXIT and "person's check" in occupant_load.IS_EXIT
    routes = _routes(apartment)
    monkeypatch.setattr(egress, "measure_routes", lambda interior, **_: copy.deepcopy(routes))
    desc = copy.deepcopy(apartment)
    desc["building"] = {"occupancy_groups": ["I-4"], "sprinkler_system": "none"}
    got = egress.check(egress.laws("regulations/jurisdictions/new_york/ithaca_city"), desc,
                       {"use": "multiple_family", "dwelling_units": 4}, ALLOWED)
    rows = [r for r in got["rows"] if r["rule"] == "general.bc_1006_2_1_two_exits"
            and r["id"] in {"L1SW", "L1SE", "L2SW", "L2SE"}]
    assert len(rows) == 4 and {r["outcome"] for r in rows} == {"pass"}, rows

def test_the_panel_never_asks_for_a_mark_revit_does_not_have():
    """Group 3 review rounds 4 and 14: the panel never asks to mark an occupant load (no host has that mark). On
    Ben's trial request (the four-unit apartment as Revit sends it), a room with no function is asked for its function,
    the room mark Gordium: Function (PR #191: 'Set the room's function', field rooms[].function), selecting the rooms
    only (never a story's level: round 14); a closet or toilet with none is never asked to set it (the mark's tooltip
    says to leave it blank there: round 14); and every 'Gordium: ...' mark the answer or these words name is one the
    add-in defines (apps/revit_addin/src/Gordium.Revit.Reading/Marks.cs)."""
    import json
    from design_checker.__main__ import answer
    request = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json"
    sent = json.loads(request.read_text(encoding="utf-8"))
    text = json.dumps(answer(sent), ensure_ascii=False)
    assert "Mark the occupant load in the model" not in text
    assert "Fix the model so the occupant load can be measured" not in text
    assert "Set the room's function" in text and '"rooms[].function"' in text   # its own mark (PR #191)
    rooms = {r["id"] for r in sent["interior"]["rooms"]}
    asks = [a for i in json.loads(text)["result"]["view"]["items"] for a in i.get("asks") or []
            if a.get("field") == occupant_load.FUNCTION_FIELD]
    assert asks and all(set(a.get("elements") or []) <= rooms for a in asks), asks      # round 14: never a level
    for use in ("closet", "toilet"):                     # round 5: a closet or toilet Revit marks, with no function
        marked = copy.deepcopy(sent)
        marked["interior"]["rooms"][0]["use"] = use
        got = json.dumps(answer(marked), ensure_ascii=False)
        assert f"a {use} with no function stated" in got, use
        assert "Fix the model so the occupant load can be measured" not in got, use
        assert "Mark the occupant load in the model" not in got, use
        closet = marked["interior"]["rooms"][0]["id"]
        assert not any(closet in (a.get("elements") or []) for i in json.loads(got)["result"]["view"]["items"]
                       for a in i.get("asks") or [] if a.get("field") == occupant_load.FUNCTION_FIELD), use   # round 14
    text += got
    marks = set(re.findall(r'"(Gordium: [^"]+)"',
                           (REPO / "apps/revit_addin/src/Gordium.Revit.Reading/Marks.cs").read_text(encoding="utf-8")))
    words = " ".join([text, *(v for v in vars(occupant_load).values() if isinstance(v, str)),
                      load(NY / "state.yaml")["waiting_why"]])
    named = set(re.findall(r"Gordium: [A-Z][A-Za-z ]*[a-z]", words))
    assert {"Gordium: Use", "Gordium: Exit"} <= named        # the waiting sentence names the marks it means
    assert all(any(n == m or n.startswith(m + " ") for m in marks) for n in named), named


def test_a_story_names_a_missing_function_only_where_a_room_lacks_one():
    """Group 3 review round 5 (P3, 2026-11-24): a story whose rooms are open for another reason (a floor area not
    measured, a function the table sends elsewhere) never says a function is what's missing; one with a room of no
    function does, asking for that function (the room mark Gordium: Function, round 14)."""
    stated = occupant_load.FUNCTION_STATED
    def story_words(rooms, measures):
        parts = {"story": [{"id": "L1", "measures": {"story_gross_floor_area": 1000}, "not_measured": {}}],
                 "space": [{"id": r["id"], "within": "L1", "measures": dict(m, space_is_exit=False), "not_measured": {}}
                           for r, m in zip(rooms, measures)]}
        occupant_load.apply(parts, {"rooms": rooms}, FACTORS, {"occupant_load_increased": False})
        return parts["story"][0]["not_measured"]["story_occupant_load"]
    other = story_words([{"id": "a", "use": "other", "function": "business"},
                         {"id": "b", "use": "other", "function": "assembly_fixed_seats"}],
                        [{}, {"space_floor_area": 100}])
    assert "a, b" in other and stated not in other
    missing = story_words([{"id": "a", "use": "other", "function": "business"}, {"id": "c", "use": "other"}],
                          [{"space_floor_area": 100}, {"space_floor_area": 100}])
    assert "(c)" in missing and missing.endswith(stated)
    elsewhere = story_words([{"id": "m", "use": "other", "function": "mall"}], [{"space_floor_area": 100}])
    assert "(m)" in elsewhere and elsewhere.endswith(occupant_load.STORY_STATED)      # round 7: by hand, as its room


def _asked(why):
    """The panel's ask for a one-door space whose occupant load isn't worked out for `why` (panel_data.causes, then
    ui_data's headline), on 1006.2.1.1, a rule that reads it."""
    from design_checker import panel_data, ui_data
    from design_checker.each_part import GORDIUM_GAPS
    rule = next(r for r in load(NY / "5_building_code_rules/drafted/general.yaml")["rules"]
                if r["id"] == "general.bc_1006_2_1_1_three_or_more_exits")
    part = {"id": "p", "measures": {"space_is_exit": False, "space_exit_count": 2},
            "not_measured": {"space_occupant_load": why}}
    row = {"outcome": "needs_review", "id": "p", "values": dict(part["measures"])}
    found = panel_data.causes(rule, row, None, part, None, part["not_measured"],
                              {}, ALLOWED, GORDIUM_GAPS)
    return [ui_data._from_cause(c, "space")["headline"] for c in found]


def _asked_corridor(why):
    """The panel's ask for a corridor whose occupant load isn't worked out for `why`, on Table 1020.3's rule."""
    from design_checker import panel_data, ui_data
    from design_checker.each_part import GORDIUM_GAPS
    rule = next(r for r in load(NY / "5_building_code_rules/drafted/general.yaml")["rules"]
                if r["id"] == "general.bc_table_1020_3_corridor_width")
    # the building facts the rule reads stated (group 4b's dwelling-unit fact too), so only the load is asked
    part = {"id": "c", "measures": {"corridor_width": 40}, "not_measured": {"corridor_occupant_load": why}}
    stated = {"occupancy_group": "R-2", "ambulatory_care_facility": False, "corridors_within_dwelling_units": True}
    row = {"outcome": "needs_review", "id": "c", "values": {**part["measures"], **stated}}
    law = Context.for_jurisdiction(NY).allowed()           # the Building Code's own facts, each with its kind
    found = panel_data.causes(rule, row, None, part, None, part["not_measured"], stated, law, GORDIUM_GAPS)
    return [ui_data._from_cause(c, "corridor")["headline"] for c in found]


def test_every_reason_for_a_load_not_worked_out_is_asked_the_way_it_can_be_answered():
    """Group 3 review rounds 6 and 7 (2026-11-25): a load Gordium or a person must work out (no function, a room
    others pass through or a loaded room is served through, a function the table sends elsewhere, an exit, a closet or
    toilet with no function, a story of no loaded room, or one left open by a room sent elsewhere) is asked for by
    hand; a room with no function, and a story left open by one, is asked for that function, the room mark Gordium:
    Function (PR #191, round 14); only what the model itself can fix (an outline, a floor area, a function value no
    table row has, a use or exit against a function) is a model fix; none is ever an occupant load to mark. The class: every reason occupant_load.py defines, so a
    new one can't slip through unclassified; and none says a function 'is stated' when it isn't."""
    ol = occupant_load
    by_hand, model, function = "by hand", "model", "function"
    reasons = {
        "NOT_GIVEN": (ol.NOT_GIVEN, function), "NO_LOAD": (ol.NO_LOAD.format(use="closet"), by_hand),
        "THROUGH": (ol.THROUGH, by_hand), "SERVED": (ol.SERVED.format(names="st", es="es", their="its"), by_hand),
        "ELSEWHERE": (ol.ELSEWHERE.format(f="mall", where="402.8.2"), by_hand), "IS_EXIT": (ol.IS_EXIT, by_hand),
        "STORY_NONE": (ol.STORY_NONE, by_hand),
        "STORY_OPEN": (ol.STORY_OPEN.format(names="k"), model),                   # its rooms' floor areas, say
        "UNKNOWN": (ol.UNKNOWN.format(f="apartment"), model),
        "EXIT_FUNCTION": (ol.EXIT_FUNCTION.format(name="s", f="business"), model),
        "CORRIDOR_FUNCTION": (ol.CORRIDOR_FUNCTION.format(name="c", f="business"), model),
        "GROSS_NOT_MEASURED": (ol.GROSS_NOT_MEASURED, model), "AREAS_OVER": (ol.AREAS_OVER, model),
        "UNREAD_ROOMS": (ol.UNREAD_ROOMS, model),                   # a room of the description that can't be read
        # section group 4: a corridor's (asked on the corridor, below: _asked_corridor)
        "CORRIDOR_NOT_RULED_OUT": (ol.CORRIDOR_NOT_RULED_OUT, "mark"),    # Gordium: Other levels reach corridors
        "CORRIDOR_OTHER_LEVELS": (ol.CORRIDOR_OTHER_LEVELS, by_hand),
        "CORRIDOR_NO_STORY": (ol.CORRIDOR_NO_STORY, by_hand),
    }
    fragments = {"QUESTION", "LOWER", "UPPER", "FUNCTION_STATED", "FUNCTION_FIELD", "FUNCTION_ROOMS", "LOAD_STATED",
                 "STORY_STATED", "STORY_FUNCTION", "OTHER_LEVELS", "OTHER_LEVELS_FIELD", "CORRIDOR_QUESTION", "CORRIDOR_NONE", "CORRIDOR_STORY", "CORRIDOR_BY_HAND",
                 "CORRIDOR_READINGS",     # the readings' own words: a load given, never asked
                 "SEATING_STORY", "SEATING_SPACE"}        # the assembly seating measures' names (1030.7), never a reason
    defined = {k for k, v in vars(ol).items() if k.isupper() and isinstance(v, str)} - fragments
    assert defined == set(reasons), defined ^ set(reasons)
    corridor = {k: reasons[k] for k in ("CORRIDOR_NOT_RULED_OUT", "CORRIDOR_OTHER_LEVELS", "CORRIDOR_NO_STORY")}
    for why, kind in corridor.values():
        heads = _asked_corridor(why)
        assert heads and not any(h.startswith(("Mark the", "Fix the model")) for h in heads), (why, heads)
        # the building's other-levels fact not stated: its own Revit mark (Gordium: Other levels reach corridors) is
        # the card to set (the Revit-fields PR for groups 4 and 5; before it, asked by hand); a load that is the
        # architect's to work out (other levels do reach the corridors, or the story's isn't known): by hand
        if kind == "mark":
            assert heads == ["Say whether another level's occupants reach the corridors"], (why, heads)
        else:
            assert any(h.startswith("Work out") for h in heads) and not any(h.startswith("Say whether") for h in heads), \
                (why, kind, heads)
        assert "is stated by the architect" not in why, why
    # round 2: every host is told the statement that settles it (the command line can state it), not only Revit's gap
    assert "say on the building that none do" in ol.CORRIDOR_NOT_RULED_OUT
    assert ol.OTHER_LEVELS in ol.CORRIDOR_NOT_RULED_OUT
    cases = [(w, kind) for k, (w, kind) in reasons.items() if k not in corridor] + [
        ("the room's floor area isn't measured", model),
        (ol.STORY_OPEN.format(names="k") + ol.STORY_FUNCTION, function),            # a room with no function
        (ol.STORY_OPEN.format(names="k") + ": " + ol.STORY_STATED, by_hand),       # one sent elsewhere
        # round 8: a name or value a reason quotes never reads as a mark ("Supermarket", a function "market")
        (ol.STORY_OPEN.format(names="Supermarket"), model), (ol.UNKNOWN.format(f="market"), model),
        (ol.CORRIDOR_FUNCTION.format(name="Landmark hall", f="business"), model),
        (ol.EXIT_FUNCTION.format(name="Bookmark stair", f="business"), model)]
    for why, kind in cases:
        heads = _asked(why)
        assert heads and not any(h.startswith("Mark the") for h in heads), (why, heads)
        assert any(h.startswith("Fix the model") for h in heads) == (kind == model), (why, kind, heads)
        assert ("Set the room's function" in heads) == (kind == function), (why, kind, heads)   # PR #191's mark
        assert "is stated by the architect" not in why, why     # round 6: never says it was stated
    # the reviewer's layout: a closet with no function, a storeroom behind it, off a kitchen: asked by hand
    desc = description([CORRIDOR, room("k", rect(10, 6.5, 20, 16.5), use="kitchen", lockable=False),
                        room("s13", rect(10, 17, 20, 27), use="closet", lockable=False),
                        room("st", rect(13, 27.5, 17, 30.5), use="accessory_storage", lockable=True)],
                       [EXIT, door("kc", (15, 6.25), (1, 0), ("k", "c")), door("s13", (15, 16.75), (1, 0), ("s13", "k")),
                        door("sts13", (15, 27.25), (1, 0), ("st", "s13"))])
    parts = measure(desc)["parts"]
    occupant_load.apply(parts, desc, FACTORS, {"occupant_load_increased": False})
    closet = _space(parts, "s13")["not_measured"]["space_occupant_load"]
    assert "st egresses through it" in closet
    assert not any(h.startswith(("Fix the model", "Mark the")) for h in _asked(closet)), closet


@pytest.mark.parametrize("bad", [["X"], {"id": "X"}, 5, None, "SHARED", 7.5])
def test_a_room_id_that_isnt_one_rooms_text_leaves_every_load_unknown(apartment, bad):
    """A description room whose id isn't text (a list, a mapping, a number, none) or is another room's is never
    indexed, never a crash, and never quietly left out of a story's total: every load is not known (needs review),
    never one with a room missing."""
    desc = copy.deepcopy(apartment)
    room = next(r for r in desc["rooms"] if r.get("function"))
    room["id"] = next(r["id"] for r in desc["rooms"] if r is not room) if bad == "SHARED" else bad
    parts = _routes(apartment)["parts"]                 # the routes as drawn: only the description's ids are odd
    occupant_load.apply(parts, desc, FACTORS, {"occupant_load_increased": False})
    for s in parts["story"]:
        assert not _values(s, "story_occupant_load"), (bad, s["id"])
        assert "can't be read" in s["not_measured"]["story_occupant_load"]
    for p in parts["space"]:
        assert not _values(p, "space_occupant_load"), bad


def test_rooms_that_arent_a_list_are_never_a_crash():
    for bad in (5, True, "x", {"a": 1}):
        assert occupant_load.readable_rooms({"rooms": bad}) == ({}, False)
    assert occupant_load.readable_rooms({}) == ({}, True)


# ---- assembly seating on a story (BCNYS 1030.7, p.354 lines 50-51; 1030.9; 1030.13.1) -------------------------------

def test_the_assembly_functions_are_exactly_table_1004_5s_rows_under_its_assembly_heading():
    """Table 1004.5 prints "Assembly" on p.312, line 19, its rows on lines 20 to 27 (Gaming floors to Bowling centers),
    "Business areas" on line 28: the functions that name a room used for assembly purposes are those rows, read from
    the frozen table's own sources; the ones that may be an assembly use are among its other rows."""
    rows = load(NY / OCCUPANT_LOAD_FACTORS)["functions"]
    under = {f for f, v in rows.items() if v["source"]["page"] == 312 and 20 <= v["source"]["lines"][0] <= 27}
    assert set(occupant_load.ASSEMBLY_FUNCTIONS) == under
    assert set(occupant_load.ASSEMBLY_LIKE_FUNCTIONS) <= set(rows) - under and len(occupant_load.ASSEMBLY_LIKE_FUNCTIONS) == 7


_SEATING_PARTS = {}


def _seating_story(fn=None, use="other", more=None):
    r = room("r", rect(0, 0, 20, 15), use=use, **({"function": fn} if fn is not None else {}))
    desc = description([r, room("c", rect(-20, 15.5, 40, 23.5))],
                       [door("d", (10, 15.25), (1, 0), ("r", "c")),
                        door("w", (-20.25, 19.5), (0, 1), ("c", "outside"), exit_id="A"),
                        door("e", (40.25, 19.5), (0, 1), ("c", "outside"), exit_id="B")])
    desc.update(more or {})
    if not _SEATING_PARTS:                          # a function or use changes no geometry: measured once (the
        _SEATING_PARTS["r"] = measure(desc)["parts"]   # seating reads each room's function and use from the description)
    parts = copy.deepcopy(_SEATING_PARTS["r"])
    occupant_load.assembly_seating(parts, desc, FACTORS)
    story = parts["story"][0]
    assert all(p["measures"][occupant_load.SEATING_SPACE] == story["measures"][occupant_load.SEATING_STORY]
               for p in parts["space"])
    return story["measures"][occupant_load.SEATING_STORY]


@pytest.mark.parametrize("fn", sorted(FACTORS["functions"]) + [None, "not a function"])
def test_a_story_may_seat_people_served_by_aisles_unless_every_room_states_another_function(fn):
    """1030.7 (p.354, lines 50-51): "Where aisles are provided for seating, the distance shall be measured along the
    aisles and aisle accessways without travel over or on the seats", fixed seats or loose (1030.9: aisles wherever
    seats, tables or displays are; 1030.13.1: aisle accessways for seating at tables). A story with a room stating an
    Assembly function (a restaurant's assembly_unconcentrated among them), one that may be an assembly use, one
    that is none of the table's, or none at all may hold such seating; only rooms all stating the table's other
    functions rule it out. The corridor with no function holds none."""
    want = fn is None or fn not in FACTORS["functions"] or fn in occupant_load.ASSEMBLY_FUNCTIONS + \
        occupant_load.ASSEMBLY_LIKE_FUNCTIONS
    assert _seating_story(fn) is want, fn


def test_a_room_unseen_never_rules_seating_out():
    """An enclosed space with no room drawn in it, a room that can't be read, or a room no story holds may be such a
    room: every story may hold seating then, whatever the rooms read say."""
    assert _seating_story("business") is False
    assert _seating_story("business", more={"unknown_spaces": [{"id": "u", "name": "Enclosed area"}]}) is True
    _seating_story("business")
    base = _SEATING_PARTS["r"]                      # the same rooms: r and the corridor c
    for extra in ({"id": "ghost", "name": "ghost"}, "not a room", {"id": 7}):     # placed nowhere, or unreadable
        parts = copy.deepcopy(base)
        occupant_load.assembly_seating(parts, _seating_desc_with_extra(extra), FACTORS)
        assert all(s["measures"][occupant_load.SEATING_STORY] is True for s in parts["story"]), extra
        assert all(p["measures"][occupant_load.SEATING_SPACE] is True for p in parts["space"]), extra
    parts = copy.deepcopy(base)
    parts["space"].append({"id": "lost", "measures": {}, "not_measured": {}})     # a space no story holds
    occupant_load.assembly_seating(parts, _seating_desc_with_extra(None), FACTORS)
    assert parts["space"][-1]["measures"][occupant_load.SEATING_SPACE] is True
    for use in occupant_load.SUPPORT_USES:                  # a closet or toilet with no function: no seats
        assert _seating_story(None, use=use) is (use not in occupant_load.SUPPORT_USES)


def _seating_desc_with_extra(extra):
    desc = description([room("r", rect(0, 0, 20, 15), use="other", function="business"),
                        room("c", rect(-20, 15.5, 40, 23.5))],
                       [door("d", (10, 15.25), (1, 0), ("r", "c")),
                        door("w", (-20.25, 19.5), (0, 1), ("c", "outside"), exit_id="A"),
                        door("e", (40.25, 19.5), (0, 1), ("c", "outside"), exit_id="B")])
    if extra is not None:
        desc["rooms"].append(extra)
    return desc


def test_the_apartments_stories_seat_no_one_served_by_aisles(apartment):
    """The four-unit apartment: its apartments state residential, its stairs are exits and its corridors state no
    function, so neither story may hold seating served by aisles; with one apartment's function left out, its story
    may (the room may be anything)."""
    parts = _loads(apartment)
    assert {s["id"]: s["measures"][occupant_load.SEATING_STORY] for s in parts["story"]} == {"L1": False, "L2": False}
    desc = copy.deepcopy(apartment)
    next(r for r in desc["rooms"] if r["id"] == "L2N").pop("function")
    parts = _loads(desc)
    assert {s["id"]: s["measures"][occupant_load.SEATING_STORY] for s in parts["story"]} == {"L1": False, "L2": True}
