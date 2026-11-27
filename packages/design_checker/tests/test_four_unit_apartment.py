"""The Building Code eval (test_data/test_sites/new_york/ithaca_city/four_unit_apartment): Gordium's two-story,
four-unit building, as the Revit reader reads it once built from revit_build_data.json and marked by eval_marks.yaml
(make_ny_build_data.interior_of), checked against its hand-worked expected.yaml: the Building Code governs, its rules
run on the routes' stories and spaces, each apartment's occupant load is worked out from its stated function (Table
1004.5, two readings: section group 3) so 1006.2.1.1 passes, and with no function stated it needs review, its group's
table rows give real verdicts (2026-11-23), and every flag is its own needs-review line. Never a pass the hand-work
doesn't give."""

import copy
import math
import re
import sys

import pytest

from design_checker import code_scope, egress, present
from rule_format.rulebook import REPO, Context, load

sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
import make_ny_build_data as build  # noqa: E402

FOLDER = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment"
VALUES = {"use": "multiple_family", "dwelling_units": 4}
ALLOWED = Context.for_jurisdiction(REPO / "regulations/jurisdictions/new_york/ithaca_city").allowed()


@pytest.fixture(scope="module")
def laws():
    return egress.laws("regulations/jurisdictions/new_york/ithaca_city")


@pytest.fixture(scope="module")
def routes():
    """The building's routes, measured once (a room's function changes no geometry)."""
    return egress.measure_routes(build.interior_of())


def _check(desc, routes):
    with pytest.MonkeyPatch.context() as m:
        m.setattr(egress, "measure_routes", lambda interior, **_: copy.deepcopy(routes))
        return egress.check(egress.laws("regulations/jurisdictions/new_york/ithaca_city"), desc, VALUES, ALLOWED)


@pytest.fixture(scope="module")
def got(routes):
    return _check(build.interior_of(), routes)


# Chapter 4 part a (2026-11-26): where the building may hold a covered or open mall (no space with its own exits or
# travel limit ruled out), 402.8 governs over Chapter 10, so no story's exits, corridor's width, capacity or rating
# passes on the load its rooms give: the stated-facts tests below state no mall too, and compare with the apartment
# as sent but for that (`no_mall`)
NO_MALL = {"special_egress_spaces": False}


@pytest.fixture(scope="module")
def no_mall(routes):
    desc = build.interior_of()
    desc["building"] = {**(desc.get("building") or {}), **NO_MALL}
    return _check(desc, routes)


@pytest.fixture(scope="module")
def before(routes):
    """The same building with no room function stated: as it was before section group 3."""
    desc = build.interior_of()
    for r in desc["rooms"]:
        r.pop("function", None)
    return _check(desc, routes)


@pytest.fixture(scope="module")
def expected():
    return load(FOLDER / "expected.yaml")


def test_the_building_code_governs_it(got, expected):
    assert [s["title"] for s in got["sections"]] == ["Egress (NY State Building Code 2025)"]
    which = egress.which_code(got)
    assert {k: which[k] for k in ("code", "title", "why")} == expected["which_code"]
    assert which["code"] == code_scope.BUILDING


def test_every_rules_answer_is_the_hand_worked_one(got, expected):
    assert got["results"] == expected["results"]
    assert got["sections"][0]["state"] == expected["state"]


def test_the_story_figures_are_the_hand_worked_ones(got, expected):
    stories = got["interior"]["parts"]["story"]
    assert [s["id"] for s in stories] == ["L1", "L2"]
    for s in stories:
        assert s["measures"]["story_exit_count"] == expected["stories"]["story_exit_count"]
        assert s["measures"]["exit_remoteness_ratio"] == pytest.approx(41 / math.hypot(61, 31), abs=1e-9)
        assert round(s["measures"]["exit_remoteness_ratio"], 4) == expected["stories"]["exit_remoteness_ratio"]
    rows = [r for r in got["rows"] if r["rule"] == "general.bc_1007_1_1_remoteness"]
    assert [(r["id"], r["outcome"]) for r in rows] == [("L1", "pass"), ("L2", "pass")]
    assert all(p["measures"]["space_exit_count"] == expected["spaces"]["space_exit_count"]
               for p in got["interior"]["parts"]["space"])


def test_the_r2_story_rows_wait_only_on_whether_its_units_are_dwelling_units(routes, got):
    """Group 3 review round 12 (2026-11-25): what expected.yaml says of the R-2 story rows and 508.2.3 holds. The
    story's occupant load is at most 500 at both readings (so its two exits satisfy either table), and stating the
    R-2 is of dwelling units settles Table 1006.3.4(1)'s row on both stories; 508.2.3 reads the story's measured gross
    floor area (1,800 sq ft), its net still not measured."""
    for s in got["interior"]["parts"]["story"]:
        values = [r["value"] for r in s["readings"]["story_occupant_load"]]
        assert len(values) == 2 and max(values) <= 500 and s["measures"]["story_gross_floor_area"] == pytest.approx(1800)
    rows = [r for r in got["rows"] if r["rule"] == "general.bc_508_2_3_accessory_area"]
    assert rows and all(r["values"]["story_gross_floor_area"] == pytest.approx(1800)
                        and r["values"].get("story_net_floor_area") is None for r in rows)
    desc = build.interior_of()
    desc["building"] = {**(desc.get("building") or {}), "r2_sleeping_units": False, **NO_MALL}
    stated = _check(desc, routes)
    assert stated["results"]["general.bc_table_1006_3_4_1__r2_dwelling_units"] == "pass"
    assert stated["results"]["general.bc_table_1006_3_4_2__h_i_r"] == "not_applicable"


def test_the_corridor_width_waits_only_on_whether_other_levels_reach_the_corridor(routes, got, no_mall):
    """Section group 4 (2026-11-25), before and after: as sent, the corridor's occupant load isn't worked out
    (another level's occupants reaching it isn't ruled out: 1004.2.2, 1004.2.3, 1005.6), so Table 1020.3 needs review
    though the corridor is 72 in; with the building stating none do, its load is two readings, none and the story's
    upper (its 1,800 sq ft gross / 7, 1004.5.1's increase not ruled out: 257.1), and it passes (72 in: past 44 in
    and past 0.2 in per occupant, 51.4 in, 1005.3.2). Stating they do
    leaves it needing review. 1020.3's capacity rule goes the same way (section group 5a: a rule). Nothing else changes
    either way."""
    rule, capacity = "general.bc_table_1020_3_corridor_width", "general.bc_1020_3_corridor_capacity"
    corridors = got["interior"]["parts"]["corridor"]
    assert [c["measures"]["corridor_width"] for c in corridors] == [72.0, 72.0]
    assert all("corridor_occupant_load" in c["not_measured"] and not (c.get("readings") or {}) for c in corridors)
    assert got["results"][rule] == present.REVIEW and got["results"][capacity] == present.REVIEW
    for others, want, cap in ((False, "pass", "pass"), (True, present.REVIEW, present.REVIEW)):
        desc = build.interior_of()
        desc["building"] = {**(desc.get("building") or {}), "other_level_egress_into_corridors": others, **NO_MALL}
        stated = _check(desc, routes)
        assert stated["results"][rule] == want and stated["results"][capacity] == cap, others
        assert {k for k in got["results"] if stated["results"][k] != no_mall["results"][k]} <= {rule, capacity}, others
        if not others:
            for c in stated["interior"]["parts"]["corridor"]:
                values = [r["value"] for r in c["readings"]["corridor_occupant_load"]]
                assert values == pytest.approx([0, 1800 / 7])


def test_the_corridor_rating_needs_review_however_the_corridor_facts_are_stated(routes, got, no_mall):
    """Section group 4b (2026-11-25), before and after: Table 1020.2's R row needs review as sent (the corridor's load
    isn't worked out). Stating that no other level reaches the corridors and that none is within a dwelling unit
    settles neither way: its load is two readings, none (no rating asked) and the story's 257.1 (more than 10
    occupants, no sprinkler system: Not Permitted), so it still needs review, never a pass; only rules reading those
    facts change, and only between needs review and an answer the law gives."""
    rule = "general.bc_table_1020_2_r"
    assert got["results"][rule] == present.REVIEW
    desc = build.interior_of()
    desc["building"] = {**(desc.get("building") or {}), "other_level_egress_into_corridors": False,
                        "corridors_within_dwelling_units": False, **NO_MALL}
    stated = _check(desc, routes)
    assert stated["results"][rule] == present.REVIEW
    changed = {k for k in got["results"] if stated["results"][k] != no_mall["results"][k]}
    assert changed <= {"general.bc_table_1020_3_corridor_width", "general.bc_1020_3_corridor_capacity"}, changed
    assert stated["results"]["general.bc_table_1020_3_corridor_width"] == "pass"     # 72 in, as group 4a found


def test_each_flags_short_name_names_its_whole_subject():
    """Review round 1 of group 5a (P3): a result line shows a rule's title cut at its first bracket and comma
    (check.short); 1005.3.2's flag read "Doors" there though it covers every component but stairways."""
    from design_checker import check
    rules = {r["id"]: r for r in load(REPO / "regulations/jurisdictions/new_york/new_york_state_building"
                                      / "5_building_code_rules/drafted/general.yaml")["rules"]}
    assert check.short(rules["general.bc_1005_3_2_other_components"]["title"]) == "Other components' capacity"


def test_the_occupant_loads_come_from_each_rooms_function(got):
    """Section group 3 (2026-11-23): each apartment's stated function (residential, 200 gross) gives its occupant
    load as two readings, 690 / 200 from its own area and 690 / 7 while 1004.5.1's increase isn't ruled out; both at
    most 500, so 1006.2.1.1 needs no third exit; the stair enclosures are exits and hold no load."""
    for p in got["interior"]["parts"]["space"]:
        values = [r["value"] for r in (p.get("readings") or {}).get("space_occupant_load") or []]
        if p["name"].startswith("Apartment"):
            assert values == pytest.approx([690 / 200, 690 / 7])
        else:
            assert values == [] and "space_occupant_load" not in p["measures"]
    rows = [r for r in got["rows"] if r["rule"] == "general.bc_1006_2_1_1_three_or_more_exits"]
    assert len(rows) == 8 and {r["outcome"] for r in rows} == {"pass"}


def test_before_and_after_the_functions_only_rules_reading_an_occupant_load_change_and_only_from_needs_review(
        got, before):
    """The apartment before section group 3 (no function stated: 1006.2.1.1 needs review, its reason naming the
    missing function) and after (residential: it passes). Stating a function only settles a rule that
    reads an occupant load and needed review for want of one; it never turns a verdict over."""
    rule = "general.bc_1006_2_1_1_three_or_more_exits"
    assert before["results"][rule] == present.REVIEW and got["results"][rule] == "pass"
    rows = [i for i in before["items"] if i["rule"] == rule]
    assert len(rows) == 8 and sum("Table 1004.5 function" in i["reason"] for i in rows) == 4     # each apartment's
    assert [i["status"] for i in rows].count(present.REVIEW) == 4                            # the stairs are exits
    rules = {r["id"]: r for r in load(REPO / "regulations/jurisdictions/new_york/new_york_state_building"
                                      / "5_building_code_rules/drafted/general.yaml")["rules"]}
    changed = {k for k in got["results"] if got["results"][k] != before["results"].get(k)}
    assert rule in changed
    for k in changed:
        r = rules[k.split(":")[0]] if k.split(":")[0] in rules else None
        assert r is not None and re.search(r"(space|story)_occupant_load", str(
            [r.get(f) for f in ("check", "review_when", "applies_when")])), k
        assert before["results"][k] == present.REVIEW, (k, before["results"][k])


def test_each_flag_is_its_own_line_with_its_section(got):
    """23 of the rulebook's 34 flags show (2026-11-23; 1006.2.2's five rooms by use since review round 1; the
    mixed-occupancy single-exit flags not applicable since section group 2; 1030.8's on its fact alone since round
    2): those narrowed to a building of two or more groups, or to another group (F-1 and S-1's increase, H-5's,
    Group H's sprinkler system), are not applicable to a one-group R-2. Section group 4b adds 1020.2.1's elevator
    hoistway doors (24); its per-corridor flag (a rated corridor's walls) is a corridor's row, not a building line.
    Section group 4c adds 1020.4's and 1020.6's (26); 1020.7's is a corridor's row. Section group 5a adds 1005.3.1's
    stairways and 1005.3.2's doors, ramps and passageways (28); section group 5b 1005.4, 1005.5 and 1005.6 (31); section group 5c 1005.7.1 to 1005.7.3 (34);
    section group 6a 1010.1, 1010.1.1's capacity and 1010.1.1.1 (37); Chapter 4 part a, 402.1 and 402.8's seventeen
    (a mall isn't ruled out) and 404.1, 404.9 to 404.11's four (nor an atrium) (58)."""
    flags = [i for i in got["items"] if i["reason"].startswith("A person checks this")]
    assert len(flags) == 58 and all(i["status"] == present.REVIEW and i["code"]["section"] for i in flags)


def test_its_groups_rows_give_real_verdicts(got, expected):
    """Group R-2, no sprinkler system (2026-11-23): each story's travel within Table 1017.2's 200 ft (a verdict that
    waits on special_egress_spaces, review round 1), no dead end,
    and each apartment's one door fails Table 1006.2.1's R-2 row (Not Permitted without a sprinkler system); the
    stair enclosures are exits, so that row asks nothing of them."""
    for s in got["interior"]["parts"]["story"]:
        assert s["measures"]["egress_travel_distance"] <= expected["egress_travel_distance_at_most"]
    is_exit = {p["name"].split(" L")[0]: p["measures"]["space_is_exit"] for p in got["interior"]["parts"]["space"]}
    assert is_exit == expected["spaces"]["space_is_exit"]
    rows = {(r["name"], r["outcome"]) for r in got["rows"] if r["rule"] == "general.bc_table_1006_2_1_r2"}
    assert {o for n, o in rows if n.startswith("Apartment")} == {"fail"}
    assert {o for n, o in rows if n.startswith("Stair")} == {"pass"}


def test_the_build_data_is_made_from_the_building(tmp_path):
    assert build.main(["--check"]) == 0                      # revit_build_data.json is apartment.yaml's, current


# ---- PR #181 review (2026-11-24): a space that is itself an exit is not one 1006.2.1 or 1007.1 counts ---------------

SPACE_EXIT_RULES = ("general.bc_1006_2_1_two_exits", "general.bc_1006_2_1_1_three_or_more_exits",
                    "general.bc_1007_1_1_space_remoteness", "general.bc_1007_1_2_space_three_or_more")


@pytest.mark.parametrize("sprinkler_system", ["none", "nfpa_13"])
def test_an_exit_stair_is_never_held_to_the_exits_of_the_spaces_it_serves(sprinkler_system):
    """Group I-4's two-exit rule failed each stair enclosure (one door, no sprinkler system) and needed review with
    one: 1006.2.1 and 1007.1 ask for the exits of the spaces exit access serves, never of an exit itself (202 EXIT;
    the routes mark a room entered by an exit-enclosure door as space_is_exit). The same building as Group I-4."""
    import copy
    interior = copy.deepcopy(build.interior_of())
    interior["building"] = {**(interior.get("building") or {}), "occupancy_groups": ["I-4"],
                            "sprinkler_system": sprinkler_system}
    got = egress.check(egress.laws("regulations/jurisdictions/new_york/ithaca_city"), interior, VALUES, ALLOWED)
    stairs = [r for r in got["rows"] if r["rule"] in SPACE_EXIT_RULES and r["name"].startswith("Stair")]
    assert {r["rule"] for r in stairs} >= {"general.bc_1006_2_1_two_exits"}
    assert {(r["rule"], r["outcome"]) for r in stairs} == {(r["rule"], "pass") for r in stairs}


# the five Project Information Yes/No marks Revit sends for the Building Code's Chapter 10 (Marks.cs: Fixed assembly
# seating, Special egress spaces, Merchandise pads, Egress balcony increase, Atrium), by their building block keys
CH10_BUILDING_MARKS = ("assembly_fixed_seating", "special_egress_spaces", "merchandise_pads",
                       "egress_balcony_increase_taken", "building_has_atrium")


@pytest.mark.parametrize("stated", [False, True])
def test_the_five_chapter_10_marks_stated_move_only_the_rules_that_read_them(got, laws, stated):
    """The apartment as built, with the five marks set: No moves exactly the ten rules that wait on them (travel's
    54 ft within Table 1017.2's 200 ft now passes; each flag of a space the building states it hasn't is not
    applicable), and Yes leaves every rule as it was with them blank (needs review: a person checks those spaces),
    never a pass. Left blank they are not sent (the add-in's BuildingFacts), so `got` is the unset reading."""
    interior = build.interior_of()
    interior["building"] = {**interior["building"], **{k: stated for k in CH10_BUILDING_MARKS}}
    now = egress.check(laws, interior, VALUES, ALLOWED)
    moved = {k: (got["results"][k], now["results"][k]) for k in got["results"] if got["results"][k] != now["results"][k]}
    if stated:
        assert moved == {}
        return
    assert moved == {"general.bc_table_1017_2_a_e_f1_m_r_s1": ("needs_review", "pass"),
                     **{f"general.{r}": ("needs_review", "not_applicable") for r in (
                         "bc_1006_2_2_1_boiler_rooms", "bc_1006_2_2_2_refrigeration_machinery_rooms",
                         "bc_1006_2_2_3_refrigerated_rooms", "bc_1006_2_2_4_electrical_rooms",
                         "bc_1006_2_2_5_vehicular_ramps", "bc_table_1017_2_note_a", "bc_1017_2_1_balcony_increase",
                         "bc_1017_3_2_3_atrium", "bc_1030_8_fixed_seating_common_path")},
                     # Chapter 4 part a: every flag of 402 (a mall: a space with its own exits) and 404 (an atrium)
                     **{k: ("needs_review", "not_applicable") for k in got["results"]
                        if re.match(r"general\.bc_40[24]_", k)}}


def test_group_2s_marks_stated_choose_the_r2_table_and_pass_only_on_two_exits(no_mall, laws):
    """The two Revit marks for Table 1006.3.4's notes (Gordium: R-2 sleeping units, Gordium: 1031 escape openings) on
    the apartment (Group R-2, no sprinkler system): stated dwelling units, the sleeping-units table (1006.3.4(2)) is
    not applicable and the dwelling-units row passes on the story's two exits (its occupant loads, read since group 3,
    under 500: Table 1006.3.3's two exits; the same two-exit test in either table, never the one-exit allowance the
    escape openings unlock); stated sleeping units, the other way round. Blank (or Both), both rows need review."""
    moved = {}
    for sleeping in (False, True):
        interior = build.interior_of()
        interior["building"] = {**interior["building"], "r2_sleeping_units": sleeping, "emergency_escape_openings_1031": True,
                                **NO_MALL}
        now = egress.check(laws, interior, VALUES, ALLOWED)["results"]
        moved[sleeping] = {k: (no_mall["results"][k], now[k]) for k in no_mall["results"]
                           if no_mall["results"][k] != now[k]}
    assert moved[False] == {"general.bc_table_1006_3_4_2__h_i_r": ("needs_review", "not_applicable"),
                            "general.bc_table_1006_3_4_1__r2_dwelling_units": ("needs_review", "pass")}
    assert moved[True] == {"general.bc_table_1006_3_4_1__r2_dwelling_units": ("needs_review", "not_applicable"),
                           "general.bc_table_1006_3_4_2__h_i_r": ("needs_review", "pass")}


def test_group_3s_marks_stated_move_only_their_own_rows_and_never_to_a_pass(got, laws):
    """The two Revit marks for group 3's building facts on the apartment: Gordium: Occupied outdoor areas No makes 1004.7's
    flag not applicable and moves nothing else (Yes leaves it a person's check); Gordium: Occupant load increased, either
    way, moves nothing here (an increase not ruled out keeps each room's larger reading at its area / 7 or more:
    occupant_load.py)."""
    moved = {}
    for fact, value in (("occupied_outdoor_areas", False), ("occupied_outdoor_areas", True),
                        ("occupant_load_increased", False), ("occupant_load_increased", True)):
        interior = build.interior_of()
        interior["building"] = {**interior["building"], fact: value}
        now = egress.check(laws, interior, VALUES, ALLOWED)["results"]
        moved[(fact, value)] = {k: (got["results"][k], now[k]) for k in got["results"] if got["results"][k] != now[k]}
    assert moved[("occupied_outdoor_areas", False)] == {"general.bc_1004_7_outdoor_areas": ("needs_review", "not_applicable")}
    assert moved[("occupied_outdoor_areas", True)] == moved[("occupant_load_increased", False)] == \
        moved[("occupant_load_increased", True)] == {}


def test_groups_4_and_5s_marks_stated_on_the_apartment(no_mall, laws):
    """The four Revit marks for groups 4 and 5's building facts on the apartment: Gordium: Other levels reach corridors
    No (its stairs are enclosed exits discharging outside) bounds each corridor's load by its story's, so the corridor
    width and capacity rows pass at the whole story's load (two readings, none and the story's: a pass only if the
    story's passes); Yes leaves them by hand; the other three, either way, move nothing here (Group R-2, no sprinkler
    system, no ambulatory care, the corridors already within Table 1020.3's widths)."""
    moved = {}
    for fact, value in (("other_level_egress_into_corridors", False), ("other_level_egress_into_corridors", True),
                        ("ambulatory_care_facility", False), ("corridors_within_dwelling_units", False),
                        ("corridors_within_dwelling_units", True), ("emergency_voice_alarm_system", False),
                        ("emergency_voice_alarm_system", True)):
        interior = build.interior_of()
        interior["building"] = {**interior["building"], fact: value, **NO_MALL}
        now = egress.check(laws, interior, VALUES, ALLOWED)["results"]
        moved[(fact, value)] = {k: (no_mall["results"][k], now[k]) for k in no_mall["results"]
                                if no_mall["results"][k] != now[k]}
    assert moved.pop(("other_level_egress_into_corridors", False)) == {
        "general.bc_1020_3_corridor_capacity": ("needs_review", "pass"),
        "general.bc_table_1020_3_corridor_width": ("needs_review", "pass")}
    assert all(m == {} for m in moved.values()), moved


# ---- section group 6a (2026-11-25): door size, 1010.1.1, from each door's maker's stated clear opening ----------------

WIDTH, HEIGHT = "general.bc_1010_1_1_door_width", "general.bc_1010_1_1_door_height"


def test_door_size_as_sent_and_with_each_doors_leaves_stated(got):
    """Before: the door width rule needs review on every door (34 in, but how many leaves isn't stated: a pair's
    one leaf must give 32 in), the height complies on every door (80 in, the maker's stated clear height). After,
    every door stated to have one leaf: the width complies too, and nothing else changes."""
    assert got["results"][WIDTH] == present.REVIEW and got["results"][HEIGHT] == "pass"
    rows = [r for r in got["rows"] if r["rule"] in (WIDTH, HEIGHT)]
    assert len(rows) == 20 and {r["values"].get("moe_door_clear_width") for r in rows if r["rule"] == WIDTH} == {34}
    desc = build.interior_of()
    for d in desc["doors"]:
        d["leaves"] = 1
    stated = _check(desc, egress.measure_routes(desc))
    assert stated["results"][WIDTH] == "pass" and stated["results"][HEIGHT] == "pass"
    assert {k for k in got["results"] if stated["results"][k] != got["results"][k]} == {WIDTH}


def test_a_door_with_no_stated_clear_opening_is_never_sized_from_its_leaf(got):
    """The hard condition through the whole check: one door's maker's clear opening taken away (its plan, the routes'
    figure, kept), both its size rows need review, never a pass on its 36 by 84 in leaf or its plan width; the rule's
    answer with it."""
    desc = build.interior_of()
    for d in desc["doors"]:
        d["leaves"] = 1
    desc["doors"][0].pop("stated_clear")
    stated = _check(desc, egress.measure_routes(desc))
    mine = [r for r in stated["rows"] if r["rule"] in (WIDTH, HEIGHT) and r["id"] == desc["doors"][0]["id"]]
    assert len(mine) == 2 and {r["outcome"] for r in mine} == {"needs_review"}
    assert stated["results"][WIDTH] == present.REVIEW and stated["results"][HEIGHT] == present.REVIEW


# ---- section group 6b (2026-11-25): door kind and swing --------------------------------------------------------------

KIND, SWING = "general.bc_1010_1_2_door_types", "general.bc_1010_1_2_1_direction_of_swing"


def test_door_swing_as_sent_and_with_each_doors_swing_stated(got):
    """Before: every door is side-hinged, so 1010.1.2's flag sets it aside, and the swing rule needs review (the side
    each swings into isn't stated). After, each stated to swing into the side egress travel goes into (the corridor
    from an apartment, the stair from the corridor, outside from the stair) with no occupied outdoor areas stated:
    every door complies but Level 1's stair doors (their stairs' outside doors unmarked: either may be a way in, so the
    corridor door may be the discharge, review round 7) and those outside doors (not known which way: rounds 5 and 6),
    and nothing else changes; the other way round, it needs review (how many each door serves isn't worked out, so
    under 50 can't be ruled out), never a pass and never a fail."""
    assert got["results"][KIND] == "not_applicable" and got["results"][SWING] == present.REVIEW
    desc = build.interior_of()
    for d in desc["doors"]:
        d["swings_into"] = d["sides"][1]
    stated = _check(desc, egress.measure_routes(desc))
    assert stated["results"][SWING] == present.REVIEW     # round 1: the stairs' outside doors may lead in from a patio
    desc["building"] = {**desc["building"], "occupied_outdoor_areas": False}
    stated = _check(desc, egress.measure_routes(desc))
    # review rounds 5 and 6: the stairs' outside doors aren't marked exits (the eval marks the exit at the stair door), so
    # which way egress goes through them isn't known: they need review; every other door complies
    rows = {r["id"]: r["outcome"] for r in stated["rows"] if r["rule"] == SWING}
    assert {k for k, v in rows.items() if v != "pass"} == {"L1WO", "L1EO", "L1W", "L1E"}
    assert {rows[k] for k in ("L1WO", "L1EO")} == {present.REVIEW} and stated["results"][SWING] == present.REVIEW
    assert {k for k in got["results"] if stated["results"][k] != got["results"][k]} == {
        "general.bc_1004_7_outdoor_areas"}
    for d in desc["doors"]:
        d["swings_into"] = d["sides"][0]
    wrong = _check(desc, egress.measure_routes(desc))
    assert wrong["results"][SWING] == present.REVIEW
    assert {r["outcome"] for r in wrong["rows"] if r["rule"] == SWING} == {present.REVIEW}


def test_a_stair_that_may_discharge_through_the_corridor_never_passes_on_its_door_swinging_in(got):
    """Review round 1 of group 6b (F2): with the west stair's outside door gone, Level 1's corridor door into it may be
    its discharge (1028.1: through a lobby or corridor), so egress may run out of the stair through it: a door
    swinging into the stair needs review there, never a pass; Level 2's, with no door to outside on its story, still
    leads into the stair."""
    desc = build.interior_of()
    desc["doors"] = [d for d in desc["doors"] if d["id"] != "L1WO"]
    desc["building"] = {**desc["building"], "occupied_outdoor_areas": False}
    for d in desc["doors"]:
        d["swings_into"] = d["sides"][1]
    stated = _check(desc, egress.measure_routes(desc))
    rows = {r["id"]: r["outcome"] for r in stated["rows"] if r["rule"] == SWING}
    assert rows["L1W"] == present.REVIEW and stated["results"][SWING] == present.REVIEW
    assert rows["L2W"] == "pass"


def test_a_door_to_outside_asks_whether_the_occupants_use_outdoor_areas(got):
    """Review round 2 of group 6b (P3): a door to outside that isn't an exit may be an occupied patio's or roof's way in
    (1004.7): its swing row asks the building's fact, which has a Revit mark (Gordium: Occupied outdoor areas), beside
    marking the door an exit where it is one (round 7: an unmarked door to outside is never taken as leading out)."""
    from design_checker import ui_data
    desc = build.interior_of()
    for d in desc["doors"]:
        d["swings_into"] = d["sides"][1]
    for case in (_check(desc, egress.measure_routes(desc)), got):          # swings stated; nothing stated
        items = [i for i in case["items"] if i.get("rule") == SWING and i["status"] == present.REVIEW
                 and "outside door" in i["name"]]
        assert len(items) == 2
        for i in items:
            asks = [ui_data._from_cause(c, "means_of_egress_door") for c in i.get("causes") or []]
            assert "building.occupied_outdoor_areas" in {a.get("field") for a in asks}, i["name"]
