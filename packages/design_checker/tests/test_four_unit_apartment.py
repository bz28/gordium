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

from design_checker import code_scope, egress, occupant_load, present
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
    section group 6a 1010.1, 1010.1.1's capacity and 1010.1.1.1 (37); section group 6c 1010.1.3, 1010.1.4, 1010.1.5,
    1010.1.6 and 1010.1.7 (42; 1010.1.3.2's is a door's row, not a building line); section group 6d 1010.2 to
    1010.2.6 and Table 1010.2.4 (50; 1010.2.7's is for Groups E, B and I-4); section group 6e 1010.2.8.1 to
    1010.2.12.1, 1010.2.14 and 1010.2.15 (61; 1010.2.13's is for Groups I-1 and I-2); section group 8a 1031.2's basements and public way and
    1031.2.1 (64); section group 8c 1031.5.3's drainage and 1031.6's bars (66); section group 9a 1003.2 to 1003.7's nine and 1012's seventeen ramp flags (a building's ramps aren't a fact Gordium is given, so they show for every building) (92); section group 9b 1008's eight and 1013's nine lighting and exit-sign flags but 1008.2.2's (Group I-2) and 1013.2's (Group R-1) (107); section group 9c 1009's twenty-seven accessible-egress flags but 1009.3.3's (the building is Group R-2, exception 5) (133); section group 9d 1018.1's, 1018.5's and 1019.3's flags (1018.3's is for Groups B and M, 1019.4's for I-2 and I-3) (136); section group 9e 1021's four, 1022's three and 1023's nineteen flags, each shown for every building (162); section group 9f 1024's nine flags (1025's fifteen are for Groups A, B, E, I-1, M and R-1) (171); section group 9g 1026's seven, 1027's five, 1028's four and 1029's two flags (18), each shown for every building but 1029.3's not for Group R-3 alone (189); section group 9h Section 1030's twenty-four
    assembly flags but 1030.4's (Group A-1 only): the rooms are residential, but a description may hold only some floors,
    so a room used for assembly purposes isn't ruled out until the building states none (213); section group 9i its
    thirty-seven more, 1030.10 to 1030.17 and Table 1030.13.2.1, the same way (250). Chapter 7 (2026-11-26) adds 104
    more: part a's 28 fire-barrier and shaft-enclosure flags, each shown for every building; part b its 23 building-wide
    opening-protective flags (Table 716.1(2)'s corridor doors are each corridor's row); part c 30 of its 31 fire
    partition, smoke barrier and smoke partition flags (710.5.3 is Group I-2's, not the stated R-2's); part d its 23
    floor, vertical opening and penetration flags (354). Chapter 4 part a, 402.1 and 402.8's seventeen (a mall isn't ruled out) and 404.1, 404.9 to 404.11's four
    (nor an atrium) (+21); Chapter 4 part b, 403's sixteen (a high-rise isn't ruled out) and 405's eight (nor an
    underground building) (+24); Chapter 4 part e, 420.1 to 420.3 (Group R-2's scope and separations) and 422's six (an
    ambulatory care facility isn't ruled out) (+9); Chapter 4 part f, 410.5's nine (a stage, platform or technical
    production area isn't ruled out), 411.4's two (nor a special amusement area) and 412's eleven (nor an
    aircraft-related occupancy) (+22): 430. Chapter 9 part a (2026-11-27) adds 903.1.1's alternative systems and 903.2.5.3's
    pyroxylin plastics (432); its other flags are Group H-5's or a 13R or 13D system's, not this building's. Part b
    adds 903.2.1.6's occupiable roofs, 903.2.2.1's ambulatory care floors (neither fact stated), 903.2.9.2's bulk tire
    storage and 903.2.10.1's and 903.2.10.2's vehicle storage, any group's (437); its other flags are other groups'.
    Part c adds 903.2.11's nine specific areas and 903.2.12's construction (no NFPA 13 system stated), 907.1.3's listed
    equipment, 907.2's fire alarm system and 907.2.2.1's ambulatory care detection (450). Part d adds Group R-2's three
    fire alarm and smoke alarm sections, 907.2.11 and its six for Groups R and I-1, 907.2.11.8's portable alarms (a
    nontransient hotel is Group R-2, 310.3), 907.2.10.2's battery storage and 907.5.2.2's five while the voice/alarm
    system isn't stated (467). Part e adds the standpipe, smoke control, smokeproof enclosure and fire command center
    flags but Group A's standpipes (494). The merge of main's section group 9h shows 903.2.1.5.1's
    grandstands too, an assembly space not ruled out (495)."""
    flags = [i for i in got["items"] if i["reason"].startswith("A person checks this")]
    assert len(flags) == 495 and all(i["status"] == present.REVIEW and i["code"]["section"] for i in flags)
    # review round 4 of section group 9g: the docstring's per-section counts for 9g, pinned
    from collections import Counter
    assert Counter(i["code"]["section"].split(".")[0] for i in flags
                   if i["code"]["section"][:4] in ("1026", "1027", "1028", "1029")) == {
        "1026": 7, "1027": 5, "1028": 4, "1029": 2}
    # section groups 9h and 9i: Section 1030's (Tables 1030.6.2's and 1030.13.2.1's among them), 1030.8's of
    # 2026-11-23 counted with them
    assert sum(i["code"]["section"].removeprefix("Table ").startswith("1030") for i in flags) == 24 + 1 + 37



def _flags_1030(results):
    return {k: v for k, v in results.items() if k.startswith(("general.bc_1030_", "general.bc_table_1030_"))}


def test_section_1030s_flags_show_on_residential_rooms_alone_and_hide_only_on_a_stated_no(got, laws):
    """Section group 9h: Section 1030 applies to any room or space used for assembly purposes, whatever the group
    (303.1.1, 303.1.2). The apartment's rooms are all residential and its group R-2, yet its description may hold only
    some floors, so with the fact unstated every 1030 flag shows but 1030.4's (Group A-1 only). Stated no (and no fixed
    seating) they are not applicable, and nothing else moves. A room stating a Table 1004.5 Assembly function brings
    them back whatever is stated; a room that may be an assembly use (a courtroom) keeps a stated no from standing."""
    shown = _flags_1030(got["results"])
    assert len(shown) == 26 + 37                    # section group 9i's thirty-seven too
    assert shown.pop("general.bc_1030_4_foyers_and_lobbies") == "not_applicable"
    assert set(shown.values()) == {"needs_review"}
    interior = build.interior_of()
    interior["building"] = {**interior["building"], "assembly_spaces": False, "assembly_fixed_seating": False}
    now = egress.check(laws, interior, VALUES, ALLOWED)["results"]
    moved = {k for k in got["results"] if got["results"][k] != now[k]}
    # 903.2.1.5.1's sprinklers under grandstands read the same facts as 1030.1.1.1's separation (the merge review)
    moved -= {"general.bc_903_2_1_5_1_under_grandstands"}
    assert moved == set(shown) and {now[k] for k in moved} == {"not_applicable"}
    for fn, want in (("assembly_unconcentrated", "needs_review"), ("courtroom", "needs_review"),
                     ("business", "not_applicable"), ("assembly_fixed_seats", "needs_review")):
        again = copy.deepcopy(interior)
        again["rooms"][0]["function"] = fn
        now = _flags_1030(egress.check(laws, again, VALUES, ALLOWED)["results"])
        now.pop("general.bc_1030_4_foyers_and_lobbies")
        # 1030.8 and 1030.8.1 read the fixed seating alone: stated no here, but a room stating fixed seats has it
        # (review round 1: the room's yes wins over the stated no)
        fixed = "needs_review" if fn == "assembly_fixed_seats" else "not_applicable"
        assert {k: v for k, v in now.items() if "1030_8" not in k} == {k: want for k in shown if "1030_8" not in k}, fn
        assert {v for k, v in now.items() if "1030_8" in k} == {fixed}, fn


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
    """The apartment as built, with the five marks set: No moves exactly the 36 that wait on them (twelve of Chapter 10's, Chapter 4 part a's 21 flags and part f's
    two of 411.4, and Chapter 9's mall standpipes, 905.3.3) (travel's
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
                         "bc_1010_2_8_1_refrigeration_machinery_rooms",
                         "bc_1006_2_2_3_refrigerated_rooms", "bc_1006_2_2_4_electrical_rooms",
                         "bc_1006_2_2_5_vehicular_ramps", "bc_table_1017_2_note_a", "bc_1017_2_1_balcony_increase",
                         "bc_1017_3_2_3_atrium", "bc_1030_8_fixed_seating_common_path",
                         "bc_1030_8_1_path_through_adjacent_row")},
                     # Chapter 4 part a: every flag of 402 (a mall: a space with its own exits) and 404 (an atrium);
                     # part f: 411.4's two (a special amusement area, a space with its own exits)
                     **{k: ("needs_review", "not_applicable") for k in got["results"]
                        if re.match(r"general\.bc_(40[24]|411_4)_", k)},
                     # Chapter 9 part e: 905.3.3's standpipes in malls (the merge review of Chapter 4)
                     "general.bc_905_3_3_mall_standpipes": ("needs_review", "not_applicable")}


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
    """The two Revit marks for group 3's building facts on the apartment: Gordium: Occupied outdoor areas No makes 1004.7's (and 903.2.1.6's)
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
    assert moved[("occupied_outdoor_areas", False)] == {"general.bc_1004_7_outdoor_areas": ("needs_review", "not_applicable"),
                                                        # Chapter 9 part b: an occupiable roof's assembly use
                                                        "general.bc_903_2_1_6_assembly_on_roofs": ("needs_review",
                                                                                                   "not_applicable")}
    assert moved[("occupied_outdoor_areas", True)] == moved[("occupant_load_increased", False)] == \
        moved[("occupant_load_increased", True)] == {}


def test_groups_4_and_5s_marks_stated_on_the_apartment(no_mall, laws):
    """The four Revit marks for groups 4 and 5's building facts on the apartment: Gordium: Other levels reach corridors
    No (its stairs are enclosed exits discharging outside) bounds each corridor's load by its story's, so the corridor
    width and capacity rows pass at the whole story's load (two readings, none and the story's: a pass only if the
    story's passes); Yes leaves them by hand; the other three, either way, move nothing here (Group R-2, no sprinkler
    system, no ambulatory care, the corridors already within Table 1020.3's widths), but Gordium: Ambulatory care
    facility No, which sets aside 709.5.1's smoke barrier doors (Chapter 7 part c: Group R-2 with none stated)."""
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
    # Chapter 4 part e: no ambulatory care facility (stated) sets 422's six flags aside; Chapter 7's 709.5.1 Group I-2
    # smoke barrier doors flag too
    assert moved.pop(("ambulatory_care_facility", False)) == {
        **{k: ("needs_review", "not_applicable") for k in no_mall["results"] if k.startswith("general.bc_422_")},
        "general.bc_709_5_1_i2_smoke_barrier_doors": ("needs_review", "not_applicable"),
        "general.bc_903_2_2_1_ambulatory_care": ("needs_review", "not_applicable"),      # Chapter 9 part b
        "general.bc_907_2_2_1_ambulatory_care_detection": ("needs_review", "not_applicable")}   # and part c
    # Chapter 9 part d: no voice/alarm system stated sets aside 907.5.2.2's design flags (captions are Group A's)
    assert moved.pop(("emergency_voice_alarm_system", False)) == {
        f"general.bc_907_5_2_2_{k}": ("needs_review", "not_applicable")
        for k in ("voice_alarm_design", "1_voice_alarm_override", "2_voice_alarm_live_messages", "3_voice_alarm_other_uses",
                  "5_voice_alarm_standby_power")}
    assert all(m == {} for m in moved.values()), moved


def test_chapter_4_part_fs_facts_stated_on_the_apartment(no_mall, laws):
    """Chapter 4 part f's three stated facts on the apartment (Group R-2): no stage, platform or technical production
    area sets 410.5's nine flags aside, and no aircraft-related occupancy 412's eleven; each, stated yes, moves nothing
    (the flags already show, and the bands they feed read Group U's and the 125 ft rows' spaces, where the apartment
    has no space with one exit within the row and a common path over 100 ft); a service corridor, either way, moves
    nothing in a building stated Group R-2. Nothing else moves."""
    moved = {}
    for fact, value in (("stages_or_platforms", False), ("stages_or_platforms", True),
                        ("aircraft_related_occupancy", False), ("aircraft_related_occupancy", True),
                        ("service_corridors", False), ("service_corridors", True)):
        interior = build.interior_of()
        interior["building"] = {**interior["building"], fact: value, **NO_MALL}
        now = egress.check(laws, interior, VALUES, ALLOWED)["results"]
        moved[(fact, value)] = {k: (no_mall["results"][k], now[k]) for k in no_mall["results"]
                                if no_mall["results"][k] != now[k]}
    assert moved.pop(("stages_or_platforms", False)) == {
        k: ("needs_review", "not_applicable") for k in no_mall["results"] if k.startswith("general.bc_410_5")}
    assert moved.pop(("aircraft_related_occupancy", False)) == {
        **{k: ("needs_review", "not_applicable") for k in no_mall["results"]
           if k.startswith(("general.bc_412_", "general.bc_table_412_"))},
        # Chapter 9 part e: 905.3.5's standpipes to a rooftop helistop or heliport (the merge review of Chapter 4)
        "general.bc_905_3_5_helistop_standpipes": ("needs_review", "not_applicable")}
    assert len([k for k in no_mall["results"] if k.startswith("general.bc_410_5")]) == 9
    assert len([k for k in no_mall["results"] if k.startswith(("general.bc_412_", "general.bc_table_412_"))]) == 11
    assert all(m == {} for m in moved.values()), moved
    # with special egress spaces stated no (the fixture), 411.4's two are set aside already
    assert {k: v for k, v in no_mall["results"].items() if k.startswith("general.bc_411_4")} == {
        "general.bc_411_4_exit_marking": "not_applicable", "general.bc_411_4_1_photoluminescent_exit_signs": "not_applicable"}
# ---- the corridor's facts and asks (2026-11-26: the egress UI audit's finding 5) ----------------------------------------

RATING_R = "general.bc_table_1020_2_r"


def _corridor_case(rating=None, functions=True, **building):
    desc = build.interior_of()
    for r in desc["rooms"]:
        if not functions:
            r.pop("function", None)
        if r.get("use") == "corridor" and rating is not None:
            r["fire_rating_hours"] = rating
    desc["building"] = {**desc["building"], **building}
    return desc


def test_the_corridor_asks_are_the_rooms_functions_and_its_stated_rating_never_by_hand_for_want_of_a_field(routes):
    """Before: with no room function stated, each corridor's occupant load said "work out by hand: Gordium has no
    field for it yet", though the model gives the load once the rooms' functions are set (the story's load bounds
    the corridor's where no other level reaches it, group 4a); and the corridor's fire rating had no way in at all.
    Now the corridor rows ask for the rooms' functions (selecting the rooms that lack one, never the corridor), and
    for the corridor walls' rating by the corridor room's own field; no ask says "field"."""
    from design_checker import panel_data, ui_data
    from design_checker.each_part import GORDIUM_GAPS
    got = _check(_corridor_case(functions=False, other_level_egress_into_corridors=False), routes)
    apartments = {p["id"] for p in got["interior"]["parts"]["space"] if p["name"].startswith("Apartment")}
    items = [i for i in got["items"] if i["rule"] in (RATING_R, "general.bc_table_1020_3_corridor_width")]
    assert len(items) == 4 and all(i["status"] == present.REVIEW for i in items)
    for i in items:
        asks = [ui_data._from_cause(c, "corridor") for c in i["causes"]]
        assert not any("field" in a["headline"] for a in asks), asks
        fn = [a for a in asks if a.get("field") == "rooms[].function"]
        assert fn and set(fn[0]["elements"]) <= apartments and fn[0]["elements"], (i["name"], asks)
    rated = [i for i in got["items"] if i["rule"] == "general.bc_1020_2_fire_partitions"]
    assert rated and all(ui_data._from_cause(c, "corridor").get("field") == "rooms[].fire_rating_hours"
                         for i in rated for c in i["causes"] if c.get("measure") == "corridor_fire_rating_hours")
    assert panel_data.MEASURE_FIELDS["corridor_fire_rating_hours"] in ui_data.FIELD_HEADLINES and GORDIUM_GAPS


def _rated(routes, desc):
    """The building's routes as measured (`routes`) with each corridor's stated facts read again from `desc` by the
    routes' own reader (model_measurement.routes._corridor_stated): a stated fact changes no geometry."""
    from model_measurement.routes import CORRIDOR_STATED, _corridor_stated
    got = copy.deepcopy(routes)
    items = {r["id"]: r for r in desc["rooms"]}
    for c in got["parts"]["corridor"]:
        for m in CORRIDOR_STATED:
            c["measures"].pop(m, None)
            c["not_measured"].pop(m, None)
        _corridor_stated(c, items.get(c["id"]))
    return got


@pytest.fixture(scope="module")
def unrated(routes):
    """The apartment with an NFPA 13R system and no other level reaching its corridors, no rating stated."""
    return _check(_corridor_case(sprinkler_system="nfpa_13r", other_level_egress_into_corridors=False), routes)


@pytest.mark.parametrize("rating, want", [(1, "pass"), (0.5, "pass"), (0, present.REVIEW), (None, present.REVIEW)])
def test_a_stated_corridor_rating_moves_table_1020_2s_row(routes, unrated, rating, want):
    """Group R-2 with an NFPA 13R system, no other level reaching the corridors: the corridor's load is two readings,
    none and the story's (257.1); Table 1020.2's R row asks a 0.5-hour rating over 10 occupants with the sprinkler
    system. A stated rating of 0.5 or 1 hour complies at both; 0 complies only at none (needs review, never a pass);
    not stated, it needs review as before. Only the rows reading the rating move, and never to a fail here."""
    base = unrated
    desc = _corridor_case(rating, sprinkler_system="nfpa_13r", other_level_egress_into_corridors=False)
    now = _check(desc, _rated(routes, desc))
    assert all(c["measures"].get("corridor_fire_rating_hours") == rating for c in now["interior"]["parts"]["corridor"])
    assert now["results"][RATING_R] == want, now["results"][RATING_R]
    rules = {r["id"]: r for r in load(REPO / "regulations/jurisdictions/new_york/new_york_state_building"
                                      / "5_building_code_rules/drafted/general.yaml")["rules"]}
    for k in (k for k in now["results"] if now["results"][k] != base["results"].get(k)):
        assert "corridor_fire_rating_hours" in str([rules[k].get(f) for f in ("check", "review_when", "applies_when")]), k
        assert base["results"][k] == present.REVIEW and now["results"][k] != "fail", (k, now["results"][k])


# ---- the ceiling on an occupant load not worked out (occupant_load._bounds, 2026-11-26: the egress UI audit's 6) -------

THREE = "general.bc_1006_2_1_1_three_or_more_exits"
CEILING_FACTS = {"loads_not_by_area": False, "occupied_outdoor_areas": False}


def _no_functions(**building):
    desc = build.interior_of()
    for r in desc["rooms"]:
        r.pop("function", None)
    desc["building"] = {**desc["building"], **building}
    return desc


@pytest.mark.parametrize("sprinkler, mezzanines, ceiling", [
    ("none", False, 360),          # 1,800 sq ft / 5
    ("nfpa_13r", False, 360),      # the sprinkler system changes nothing here
    ("nfpa_13r", None, None),      # a mezzanine not ruled out (1004.2.2): no ceiling; the mezzanine fact is asked
])
def test_the_three_exit_rule_settles_on_the_floor_area_with_no_function_stated(routes, before, sprinkler, mezzanines,
                                                                              ceiling):
    """The audit's finding 6: with no room function stated, the four apartments' 1006.2.1.1 rows asked for each
    room's function, though no function can put 501 people on a 1,800 sq ft story. With the building's facts the
    ceiling needs stated (no area counted by seats, lanes or actual load, no outdoor areas the occupants use, no
    mezzanine), each apartment's row complies on the ceiling; the rows that change are only rules reading an
    occupant load, only from needs review, and never to a fail. Where one fact is missing it asks that fact (here
    mezzanines), before the rooms' functions."""
    building = {**CEILING_FACTS, "sprinkler_system": sprinkler, **({} if mezzanines is None else
                                                                   {"mezzanines": mezzanines})}
    now = _check(_no_functions(**building), routes)
    rows = [r for r in now["rows"] if r["rule"] == THREE and r["name"].startswith("Apartment")]
    assert len(rows) == 4
    if ceiling is None:
        assert {r["outcome"] for r in rows} == {present.REVIEW}
        assert all(r["bound_facts"] == ["mezzanines"] for r in rows)
        items = [i for i in now["items"] if i["rule"] == THREE and i["status"] == present.REVIEW]
        assert len(items) == 4 and all(i["causes"][0]["field"] == "building.mezzanines" for i in items), items
        return
    assert {r["outcome"] for r in rows} == {"pass"}
    assert all(f"can be at most {ceiling}" in r["reason"] for r in rows), rows[0]["reason"]
    with pytest.MonkeyPatch.context() as m:          # the same building and facts with no ceiling: what it moves
        m.setattr(occupant_load, "_bounds", lambda *a, **k: None)
        base = _check(_no_functions(**building), routes)
    rules = {r["id"]: r for r in load(REPO / "regulations/jurisdictions/new_york/new_york_state_building"
                                      / "5_building_code_rules/drafted/general.yaml")["rules"]}
    moved = {k: (base["results"][k], now["results"][k]) for k in now["results"]
             if now["results"][k] != base["results"].get(k)}
    assert THREE in moved
    for k, (was, is_) in moved.items():
        r = rules.get(k.split(":")[0])
        assert r is not None and re.search(r"(space|story)_occupant_load", str(
            [r.get(f) for f in ("check", "review_when", "applies_when")])), k
        assert was == present.REVIEW and is_ != "fail", (k, was, is_)


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
        "general.bc_1004_7_outdoor_areas", "general.bc_903_2_1_6_assembly_on_roofs"}     # Chapter 9 part b's too
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


# ---- Chapter 9 part a (2026-11-27): where a sprinkler system is required, 903.2.8 for Group R -----------------------

R_RULE = "general.bc_903_2_8_group_r_sprinklers"


def test_903_2_8_fails_the_apartment_as_stated_and_follows_each_sprinkler_system(got, routes):
    """The apartment, Group R-2 with no sprinkler system: 903.2.8 asks a system throughout every building with a
    Group R fire area, so it fails on each story, whatever its size. Stated NFPA 13 it passes; NFPA 13R needs review
    at its two stories (903.3.1.2's heights aren't in the model) and fails at five, where it is no
    903.3.1.2 system (its flag, naming the four stories, still shown: review round 4); NFPA 13D fails in an R-2 of
    dwelling units, not townhouses (903.3.1.3), and needs review while either isn't stated. 903.3.1.2's two flags show
    only with a 13R system, 903.3.1.3's only with a 13D one; nothing outside Chapter 9 is compared here."""
    rows = [r for r in got["rows"] if r["rule"] == R_RULE]
    assert len(rows) == 2 and {r["outcome"] for r in rows} == {"fail"} and got["results"][R_RULE] == "fail"
    cases = [({"sprinkler_system": "nfpa_13"}, "pass"),
             ({"sprinkler_system": "nfpa_13r", "stories_above_grade_plane": 2}, "needs_review"),
             ({"sprinkler_system": "nfpa_13r", "stories_above_grade_plane": 5}, "fail"),
             ({"sprinkler_system": "nfpa_13r"}, "needs_review"),
             ({"sprinkler_system": "nfpa_13d", "townhouse_units": False, "r2_sleeping_units": False}, "fail"),
             ({"sprinkler_system": "nfpa_13d", "r2_sleeping_units": False}, "needs_review")]
    for stated, want in cases:
        interior = build.interior_of()
        interior["building"] = {**interior["building"], **stated}
        now = _check(interior, routes)["results"]
        assert now[R_RULE] == want, stated
        system = stated["sprinkler_system"]
        # review round 4: 903.3.1.2's flag shows wherever 13R is stated, above four stories too (where it isn't one)
        assert now["general.bc_903_3_1_2_nfpa_13r_limits"] == ("needs_review" if system == "nfpa_13r"
                                                                else "not_applicable"), stated
        assert now["general.bc_903_3_1_3_nfpa_13d_scope"] == ("needs_review" if system == "nfpa_13d"
                                                               else "not_applicable"), stated
        assert now["general.bc_903_2_5_1_group_h_sprinklers"] == "not_applicable"
        assert now["general.bc_903_2_6_group_i_sprinklers"] == "not_applicable"


def test_a_13r_system_above_four_stories_is_said_where_the_architect_reads(routes):
    """Review round 4: with NFPA 13R stated above four stories the sprinkler fact is no (it isn't a 903.3.1.2 system),
    so the lines the architect reads must say why: 903.3.1.2's flag still shows, naming the four stories, and 716.2.2.3's
    flag never says no sprinkler system is stated."""
    interior = build.interior_of()
    interior["building"] = {**interior["building"], "sprinkler_system": "nfpa_13r", "stories_above_grade_plane": 5}
    got = _check(interior, routes)
    by_rule = {i["rule"]: i for i in got["items"] if i.get("rule")}
    assert got["results"]["general.bc_903_3_1_2_nfpa_13r_limits"] == present.REVIEW
    assert "more than four stories" in by_rule["general.bc_903_3_1_2_nfpa_13r_limits"]["reason"]
    assert "no sprinkler system stated" not in by_rule["general.bc_716_2_2_3_exit_enclosure_door_temperature_rise"]["reason"]


# ---- section group 7c (2026-11-26): Section 1011's stairs --------------------------------------------------------------

def test_its_stairs_are_not_described_so_every_stair_line_needs_review(got):
    """Before: no rule read a stair. After: Section 1011's seven rules and two flags each give one line, and the
    apartment's two stairs aren't described (its 9 by 6 ft enclosures can't hold a code-sized stair), so no flight is
    read and every line needs review, never a pass; nothing else changes (expected.yaml holds every other line as it
    was)."""
    stair = {k: v for k, v in got["results"].items() if k.startswith("general.bc_1011_")}
    assert len(stair) == 9 and set(stair.values()) == {present.REVIEW}
    assert got["interior"]["parts"]["stair"] is None
# ---- section group 6e (2026-11-26): panic and fire exit hardware ------------------------------------------------------

PANIC = "general.bc_1010_2_8_panic_hardware"


def test_panic_hardware_as_sent_and_with_each_doors_hardware_stated(got):
    """Before: 1010.2.8 complies on every door, its hardware not stated: it asks panic or fire exit hardware only in
    Groups A, E and H, and the building is one group, R-2. After, every door stated latched by an ordinary latch:
    still every door complies, and nothing else changes; 1010.2.8.1's refrigeration rooms need review (special egress
    spaces not stated), and 1010.2.13's controlled egress (Groups I-1 and I-2) doesn't apply."""
    assert got["results"][PANIC] == "pass"
    rows = [r for r in got["rows"] if r["rule"] == PANIC]
    assert len(rows) == 10 and {r["outcome"] for r in rows} == {"pass"}
    assert got["results"]["general.bc_1010_2_8_1_refrigeration_machinery_rooms"] == present.REVIEW
    assert got["results"]["general.bc_1010_2_13_controlled_egress"] == "not_applicable"
    desc = build.interior_of()
    for d in desc["doors"]:
        d["hardware"] = "latch"
    stated = _check(desc, egress.measure_routes(desc))
    assert {r["outcome"] for r in stated["rows"] if r["rule"] == PANIC} == {"pass"}
    assert {k for k in got["results"] if stated["results"][k] != got["results"][k]} == set()


# ---- section group 8a (2026-11-26): emergency escape and rescue openings, where required ------------------------------

ESCAPE = "general.bc_1031_2_escape_opening_where_required"


def test_escape_openings_as_sent_and_with_one_room_stated_a_sleeping_room(got):
    """Before: each apartment is one room said not to be a sleeping room, so no sleeping room is read and 1031.2's rule
    needs review (a dwelling's bedrooms aren't drawn), never a pass. After, one apartment stated a sleeping room (the
    description gives no openings): it is read and linked to its story, Level 1 with two exits, which doesn't show that
    the room's occupants reach two (review round 1: Group R-2 is asked where they have access to only one), so it still
    needs review with no escape opening marked, never a pass; only that rule's rows change."""
    assert got["results"][ESCAPE] == present.REVIEW
    assert [r["outcome"] for r in got["rows"] if r["rule"] == ESCAPE] == [present.REVIEW]
    desc = build.interior_of()
    desc["rooms"][0]["sleeping"] = True
    stated = _check(desc, egress.measure_routes(desc))
    rows = [r for r in stated["rows"] if r["rule"] == ESCAPE]
    assert [(r["id"], r["outcome"]) for r in rows] == [(desc["rooms"][0]["id"] + " (sleeping room)", present.REVIEW)]
    assert {k for k in got["results"] if stated["results"][k] != got["results"][k]} == set()


SIZES = ("general.bc_1031_3_1_escape_opening_min_area", "general.bc_1031_3_2_escape_opening_min_height",
         "general.bc_1031_3_2_escape_opening_min_width", "general.bc_1031_3_3_escape_opening_max_sill_height",
         "general.bc_1031_4_escape_door_swinging_or_sliding",
         # section group 8c: the area-well rules, per opening the same way
         "general.bc_1031_5_area_well_required", "general.bc_1031_5_1_area_well_min_projection",
         "general.bc_1031_5_1_area_well_min_width", "general.bc_1031_5_1_area_well_allows_full_opening",
         "general.bc_1031_5_2_area_well_ladder_over_44", "general.bc_1031_5_2_1_area_well_ladder",
         "general.bc_1031_5_2_2_area_well_steps")


def test_escape_opening_sizes_as_sent_and_with_the_openings_stated_none(got):
    """Section group 8b. Before: the description gives no openings, so they aren't read and each of the five rules
    needs review, never a pass. After, the openings stated none: no opening to size, each not applicable (1031.2's own
    rule asks for one), and only these five change."""
    assert {got["results"][k] for k in SIZES} == {present.REVIEW}
    desc = build.interior_of()
    desc["openings"] = []
    stated = _check(desc, egress.measure_routes(desc))
    assert {stated["results"][k] for k in SIZES} == {"not_applicable"}
    assert {k for k in got["results"] if stated["results"][k] != got["results"][k]} == set(SIZES)


def test_a_story_whose_room_may_seat_people_served_by_aisles_never_passes_on_travel(got, laws):
    """BCNYS 1030.7 (p.354, lines 50-51): "Where aisles are provided for seating, the distance shall be measured along
    the aisles and aisle accessways without travel over or on the seats", fixed seats or loose (1030.9, 1030.13.1). With
    the five marks No, the apartment's travel passes Table 1017.2 (its rooms all state residential, its corridors and
    exit stairs none: no seating). With one apartment's function left out, that room may be anything, a dining room or
    a meeting room with chairs, so its story's travel, measured across where seats may be, needs review, and with it
    stated a restaurant's (tables and chairs, assembly_unconcentrated) too; never a pass."""
    def row(change):
        interior = build.interior_of()
        interior["building"] = {**interior["building"], **{k: False for k in CH10_BUILDING_MARKS}}
        change(interior)
        return egress.check(laws, interior, VALUES, ALLOWED)["results"]["general.bc_table_1017_2_a_e_f1_m_r_s1"]
    assert row(lambda d: None) == "pass"
    assert row(lambda d: next(r for r in d["rooms"] if r["id"] == "L2N").pop("function")) == "needs_review"
    assert row(lambda d: next(r for r in d["rooms"] if r["id"] == "L1S").update(
        function="assembly_unconcentrated")) == "needs_review"
    assert row(lambda d: next(r for r in d["rooms"] if r["id"] == "L1S").update(function="courtroom")) == "needs_review"

    def group_a(d):                                  # review round 1: a Group A building whose assembly room isn't shown
        d["building"]["occupancy_groups"] = ["A-2"]
        for r in d["rooms"]:
            if r.get("function") is not None:
                r["function"] = "business"
    assert row(group_a) == "needs_review"

    # review round 3: the exit stairs stating a function (an assembly one here) are rooms whose use isn't known
    def stairs(d):
        for r in d["rooms"]:
            if r["id"] in ("L1SW", "L1SE", "L2SW", "L2SE"):
                r["function"] = "assembly_unconcentrated"
    assert row(stairs) == "needs_review"

    def group_a_stair(d):                            # an exit stating an assembly function shows no assembly room
        group_a(d)
        next(r for r in d["rooms"] if r["id"] == "L1SE")["function"] = "assembly_unconcentrated"
    interior = build.interior_of()
    interior["building"] = {**interior["building"], **{k: False for k in CH10_BUILDING_MARKS}}
    group_a_stair(interior)
    parts = egress.check(laws, interior, VALUES, ALLOWED)["interior"]["parts"]
    assert {s["id"]: s["measures"]["story_assembly_seating_possible"] for s in parts["story"]} == {"L1": True, "L2": True}

    # review round 4: a corridor stating a function is the same clash: it may seat people and shows no assembly room
    for fn in ("assembly_unconcentrated", "business"):
        interior = build.interior_of()
        interior["building"] = {**interior["building"], **{k: False for k in CH10_BUILDING_MARKS}}
        group_a(interior)
        next(r for r in interior["rooms"] if r["id"] == "L1C")["function"] = fn
        parts = egress.check(laws, interior, VALUES, ALLOWED)["interior"]["parts"]
        assert {s["id"]: s["measures"]["story_assembly_seating_possible"] for s in parts["story"]} ==             {"L1": True, "L2": True}, fn
    def corridor(d):                                 # not Group A: the corridor's own story only
        next(r for r in d["rooms"] if r["id"] == "L2C")["function"] = "business"
    assert row(corridor) == "needs_review"

    # review round 2: the groups sent in the check's values (which the rules read beside the building block) count too
    interior = build.interior_of()
    interior["building"] = {k: v for k, v in interior["building"].items() if k != "occupancy_groups"}
    interior["building"].update({k: False for k in CH10_BUILDING_MARKS})
    for r in interior["rooms"]:
        if r.get("function") is not None:
            r["function"] = "business"
    sent = egress.check(laws, interior, {**VALUES, "occupancy_groups": ["A-2"]}, ALLOWED)["results"]
    assert sent["general.bc_table_1017_2_a_e_f1_m_r_s1"] == "needs_review"
