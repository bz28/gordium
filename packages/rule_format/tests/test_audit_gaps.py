"""The rules the residential coverage audit (PR #39, queue item 15) found missing, in every hand rulebook they apply
to. Expected results are worked out by hand from the code's words, independently of the rules' own examples; a fact
left blank never lets a rule pass."""

import pytest

from rule_format.rulebook import REPO, Context, load, outcome, rulebook_for

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
DISTRICTS = ["R-1a", "R-1b", "R-2a", "R-2b", "R-2c", "R-3a", "R-3aa", "R-3b", "RU"]
USES = {"use": Context.for_jurisdiction(ITHACA).uses}


def rules_of(district):
    return {r["id"]: r for r in load(rulebook_for(ITHACA, district))["rules"]}


# ---- §325-3B ONE-FAMILY ATTACHED DWELLING: "three or more ... A maximum of six" ---------------------------------
# chart p.2: the attached row is SP in R-2c and • in R-3a, R-3aa, R-3b and RU; "-" (not permitted) elsewhere, where
# the use rule already fails it.
ATTACHED_ALLOWED = {"R-2c", "R-3a", "R-3aa", "R-3b", "RU"}


@pytest.mark.parametrize("district", DISTRICTS)
def test_an_attached_building_holds_three_to_six_units(district):
    rules = rules_of(district)
    rid = f"{district}.attached_units_per_building"
    if district not in ATTACHED_ALLOWED:
        assert rid not in rules
        assert outcome(rules[f"{district}.use"], {"use": "one_family_attached"}, USES) == "fail"
        return
    r = rules[rid]
    for units, expect in [(1, "fail"), (2, "fail"), (3, "pass"), (4, "pass"), (5, "pass"), (6, "pass"), (7, "fail"),
                          (12, "fail")]:
        assert outcome(r, {"use": "one_family_attached", "attached_units_in_building": units}, USES) == expect, units
    # the cap is on the whole building, never this lot's units: two units here of a row of eight still fails
    assert outcome(r, {"use": "one_family_attached", "dwelling_units": 2, "attached_units_in_building": 8},
                   USES) == "fail"
    assert outcome(r, {"use": "one_family_attached", "dwelling_units": 3}, USES) == "needs_review"
    assert outcome(r, {"use": "multiple_family", "attached_units_in_building": 9}, USES) == "not_applicable"


@pytest.mark.parametrize("district", sorted(ATTACHED_ALLOWED - {"R-2c"}))
def test_a_row_of_seven_is_never_steered_to_another_use(district):
    """Review round 1 (PR1): whether seven or more joined units may be built as a multiple dwelling (row house) is
    not settled by the code (the definitions point both ways, questions §5.6), so the rule never tells the architect
    to enter that use, and no worked example shows a joined row as settled under it."""
    r = rules_of(district)[f"{district}.attached_units_per_building"]
    notes = " ".join(r["notes"].split())
    assert "enter that use" not in notes and "not settled" in notes and "§5.6" in notes
    assert all(e["given"].get("use") != "multiple_family" for e in r["examples"])


# ---- §325-8B(1): "each square-footage requirement applies separately to the initial permitted primary use and to each
# additional permitted primary use located in a separate building" ----------------------------------------------
# Typed by hand from the chart (p.3, Minimum Lot Size), per district: the fixed figures. A use whose lot area grows
# with units, rooms or occupants (or is a flag or an open question for one building) needs review with two or more
# buildings, since how they split between the buildings isn't known.
FIXED = {
    "R-1a": {"one_family_detached": 10000, "church": 10000},
    "R-1b": {"one_family_detached": 6000, "church": 7500},
    "R-2a": {"one_family_detached": 5000, "one_family_semi_detached": 5000, "two_family": 5000, "church": 6000},
    "R-2b": {"one_family_detached": 3000, "one_family_semi_detached": 3000, "two_family": 3000, "church": 4000},
    "R-2c": {"church": 4000},
    "R-3a": {"one_family_detached": 5000, "one_family_semi_detached": 5000, "two_family": 5000, "fraternity_sorority_group_house": 25000, "church": 6000},
    "R-3aa": {"one_family_detached": 5000, "one_family_semi_detached": 5000, "two_family": 5000, "fraternity_sorority_group_house": 25000, "church": 6000},
    "R-3b": {"one_family_detached": 3000, "one_family_semi_detached": 3000, "two_family": 3000, "fraternity_sorority_group_house": 25000, "church": 4000},
    "RU": {"one_family_detached": 10000, "one_family_semi_detached": 15000, "two_family": 15000,
           "fraternity_sorority_group_house": 30000, "church": 30000},
}
# (and, review round 3: the uses whose one-building lot size is itself a flag or an open question, the zero-lot-line
# house and the nursing home, never fall into the fixed "Other use" figure)
BY_UNITS = {"R-2c": ["one_family_detached", "one_family_detached_zero_lot_line", "one_family_semi_detached",
                     "two_family", "one_family_attached"],
            "R-3a": ["one_family_attached", "multiple_family", "dormitory", "nursing_home",
                     "one_family_detached_zero_lot_line"],
            "R-3aa": ["one_family_attached", "multiple_family", "nursing_home", "one_family_detached_zero_lot_line"],
            "R-3b": ["one_family_attached", "multiple_family", "dormitory", "nursing_home",
                     "one_family_detached_zero_lot_line"],
            "RU": ["one_family_attached", "multiple_family", "dormitory"]}


def each(district, **facts):
    return outcome(rules_of(district)[f"{district}.lot_area_each_primary_building"], facts, USES)


@pytest.mark.parametrize("district", DISTRICTS)
def test_each_primary_building_needs_its_own_lot_area(district):
    for use, f in FIXED[district].items():
        for n in (2, 3):
            same = {"use": use, "primary_buildings": n, "primary_buildings_same_use": True}
            assert each(district, **same, lot_area=n * f) == "pass", (use, n)
            assert each(district, **same, lot_area=n * f - 1) == "fail", (use, n)
        # one primary building: the use's own rule decides (not this one), whatever the lot
        assert each(district, use=use, primary_buildings=1, lot_area=1) == "not_applicable"
        # another use in one of the buildings, or not said: its own figure, by hand; never a pass
        assert each(district, use=use, primary_buildings=2, primary_buildings_same_use=False,
                    lot_area=10 ** 7) == "needs_review"
        assert each(district, use=use, primary_buildings=2, lot_area=10 ** 7) == "needs_review"
        assert each(district, use=use, lot_area=10 ** 7) == "needs_review"          # not counted
    for use in BY_UNITS.get(district, []):
        assert each(district, use=use, primary_buildings=2, primary_buildings_same_use=True,
                    lot_area=10 ** 7) == "needs_review", use
        # one building of it: its own rule (units, rooms, occupants) decides, never this one's fixed figure
        assert each(district, use=use, primary_buildings=1, lot_area=1) == "not_applicable", use
        # two: needs review whatever the fixed "Other use" figure says (review round 3: never that figure)
        assert each(district, use=use, primary_buildings=2, primary_buildings_same_use=True, lot_area=1) == \
            "needs_review", use


def test_the_codes_own_example():
    """§325-8B(1): "in R-2b Districts, an area of 3,000 square feet is required for a one family house or a two-family
    house, and an additional area of 3,000 square feet is required for each additional one-family house or two-family
    house on the property"."""
    for use in ("one_family_detached", "two_family"):
        assert each("R-2b", use=use, primary_buildings=2, primary_buildings_same_use=True, lot_area=6000) == "pass"
        assert each("R-2b", use=use, primary_buildings=2, primary_buildings_same_use=True, lot_area=5999) == "fail"


def test_ru_note_3_counts_the_primary_buildings():
    """Chart p.2 note 3: under 60,000 sf one primary structure; over 60,000 sf two with the ILPC's and the Planning
    Board's approval; at least 90,000 sf as many as three with them. Approvals can't be known: review."""
    r = rules_of("RU")["RU.primary_structures"]
    cases = [(1, 5000, "pass"), (1, 10 ** 6, "pass"), (2, 59999, "fail"), (2, 60000, "needs_review"),
             (2, 60001, "needs_review"), (3, 89999, "fail"), (3, 90000, "needs_review"), (4, 10 ** 6, "fail")]
    for n, area, expect in cases:
        assert outcome(r, {"primary_buildings": n, "lot_area": area}, USES) == expect, (n, area)
    assert r["kind"] == "rule"


# ---- §325-7B: a yard required for one building can't count for another ------------------------------------------
@pytest.mark.parametrize("district", DISTRICTS)
def test_a_second_primary_building_puts_the_shared_yard_question(district):
    """One primary building: nothing on the lot to share its yards (not applicable). Two or more: how their yards are
    divided is open (questions §5.17), so needs review, never a pass; not counted: needs review."""
    r = rules_of(district)[f"{district}.yards_not_shared"]
    assert outcome(r, {"primary_buildings": 1}, USES) == "not_applicable"
    for n in (2, 3):
        assert outcome(r, {"primary_buildings": n}, USES) == "needs_review"
    assert outcome(r, {}, USES) == "needs_review"
    assert len(r["open_questions"]) == 1 and {x["id"] for x in r["research"][0]["readings"]} == {
        "to_lot_lines", "sum_between"}


# ---- §325-8E(1)(a): the South Hill Overlay, R-1 and R-2 only ------------------------------------------------------
SOUTH_HILL = {"R-1a", "R-1b", "R-2a", "R-2b", "R-2c"}


@pytest.mark.parametrize("district", DISTRICTS)
def test_the_south_hill_overlay_allows_one_primary_structure(district):
    """"any property located within the South Hill Overlay District with a zoning designation of R-1 or R-2 is
    prohibited from constructing a primary structure on any parcel already containing one or more primary
    structures, and ... more than one primary structure on a parcel containing no primary structures"."""
    rules = rules_of(district)
    rid = f"{district}.south_hill_overlay"
    if district not in SOUTH_HILL:
        assert rid not in rules
        return
    r = rules[rid]
    cases = [({"south_hill_overlay": True, "primary_buildings": 1}, "not_applicable"),
             ({"south_hill_overlay": True, "primary_buildings": 2}, "fail"),
             ({"south_hill_overlay": True, "primary_buildings": 3}, "fail"),
             ({"south_hill_overlay": False, "primary_buildings": 3}, "pass"),
             ({"primary_buildings": 1}, "not_applicable"),     # one: never asked, no row
             ({"primary_buildings": 2}, "needs_review"),       # in the overlay or not: not said
             ({"south_hill_overlay": True}, "needs_review"),   # not counted
             ({}, "needs_review")]
    for facts, expect in cases:
        assert outcome(r, facts, USES) == expect, facts


# ---- §325-26: "No new structure shall be located nearer than 20 feet to an inlet wall or to the bank of an inlet
# channel or stream, measured at an average water level" -------------------------------------------------------
@pytest.mark.parametrize("district", DISTRICTS)
def test_new_structures_keep_20_ft_from_a_stream_bank(district):
    r = rules_of(district)[f"{district}.stream_setback"]
    cases = [({"stream_near_lot": False}, "pass"),                         # nothing within 20 ft of the lot
             ({"stream_near_lot": True, "stream_distance": 20}, "pass"),   # "nearer than 20 feet" is barred
             ({"stream_near_lot": True, "stream_distance": 25.5}, "pass"),
             ({"stream_near_lot": True, "stream_distance": 19.99}, "fail"),
             ({"stream_near_lot": True, "stream_distance": 0}, "fail"),
             ({"stream_near_lot": True}, "needs_review"),
             ({"stream_distance": 30}, "pass"),                            # 30 ft from it, whatever else is said
             ({"stream_distance": 10}, "needs_review"),                    # near the lot or not: not said
             ({}, "needs_review")]                                         # never a pass on a blank
    for facts, expect in cases:
        assert outcome(r, {"use": "one_family_detached", **facts}, USES) == expect, facts
    assert "applies_when" not in r                                       # every use, every residential district
