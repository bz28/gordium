"""Which New York code governs a building (design_checker/code_scope.py, docs/decisions/2026-11-22_which_ny_code.md):
the 2025 Residential Code of New York State for the dwellings its R101.2 lists, not more than three stories above
grade plane; the 2025 Building Code of New York State for every other building; needs review, with what to state,
wherever a fact the decision needs is missing (never the Residential Code by default: principle 4).

Pinned: the cases the brief names (a one-family house, a two-family house, a four-story townhouse, a three-unit
building, an office, a house with no stories), each with the section it stands on; the check runs only the chosen
book, a house exactly as before; the answer carries `which_code`; every quote is the book's own words."""

import copy
import re
import sys
from pathlib import Path

import pytest

from design_checker import code_scope, egress, present
from design_checker.check import check_site
from rule_format.rulebook import REPO, code_cache, load

sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_measure import FACTS, box, lot  # noqa: E402

ITHACA = "regulations/jurisdictions/new_york/ithaca_city"
RANCH = REPO / "test_data/interior_houses/1_ranch_compliant/house.yaml"
SITE = {"units": "ft", "lot": lot([(0, 0), (60, 0), (60, 110), (0, 110)]),
        "buildings": [box(10, 25, 40, 75, 0, 30)], "problems": []}


DRAWN = {code_scope.STORIES_DRAWN: True}       # Ithaca's stories count read from the drawing (check.py)


def code(values, building=None):
    got = code_scope.decide({**DRAWN, **values}, building)
    return got["code"], [c["section"] for c in got["cites"]], got


# ---- the brief's cases ------------------------------------------------------------------------------------------------

def test_a_one_family_house_of_two_stories_is_the_residential_codes():
    c, cites, got = code({"use": "one_family_detached", "stories": 2})
    assert c == code_scope.RESIDENTIAL and cites[0] == "RCNYS R101.2 item 1"
    assert got["title"] == "2025 Residential Code of New York State" and got["ask"] is None
    assert got["why"].startswith("a detached one-family dwelling, 2 stories above grade plane at most")


def test_a_two_family_house_needs_each_units_separate_means_of_egress():
    two = {"use": "two_family", "stories": 2}
    c, cites, got = code(two)
    assert c is None and cites == ["RCNYS R101.2 item 2"]           # R101.2 item 2's condition, not stated
    assert "Gordium: Separate means of egress" in got["ask"]
    assert code(two, {"separate_means_of_egress": True})[0] == code_scope.RESIDENTIAL
    c, cites, _ = code(two, {"separate_means_of_egress": False})
    assert c == code_scope.BUILDING and "BCNYS 310.4" in cites      # a Group R-3 building under the Building Code


def test_a_four_story_townhouse_is_the_building_codes():
    row = {"use": "one_family_attached", "attached_units_in_building": 4}
    c, cites, got = code(row, {"townhouse_units": True, "stories_above_grade_plane": 4})
    assert c == code_scope.BUILDING and cites[:2] == ["RCNYS R101.2 item 3", "RCNYS R101.2"]
    assert "4 stories above grade plane, more than R101.2's three" in got["why"]
    assert code(row, {"townhouse_units": True, "stories_above_grade_plane": 3})[0] == code_scope.RESIDENTIAL
    assert code(row, {"stories_above_grade_plane": 3})[0] is None          # townhouse units not said
    assert code(row, {"townhouse_units": False, "stories_above_grade_plane": 3})[0] == code_scope.BUILDING


def test_a_three_unit_building_is_the_building_codes():
    c, cites, got = code({"use": "multiple_family", "dwelling_units": 3, "stories": 2})
    assert c == code_scope.BUILDING and cites == ["RCNYS R101.2", "BCNYS 101.2"]
    assert got["title"] == "2025 Building Code of New York State"


def test_an_office_is_the_building_codes():
    c, cites, got = code({"use": "neighborhood_commercial_facility"}, {"occupancy_groups": ["B"]})
    assert c == code_scope.BUILDING and got["why"].startswith("a building of Group B")
    # an office stated on a house's use word is a contradiction to settle, never the Residential Code
    assert code({"use": "one_family_detached", "stories": 1}, {"occupancy_groups": ["B"]})[0] is None


def test_a_house_with_no_stories_known_needs_review_never_the_residential_code():
    c, cites, got = code({"use": "one_family_detached"})
    assert c is None and got["title"] is None and "RCNYS R202 STORY ABOVE GRADE PLANE" in cites
    assert got["ask"] == ("state the building's stories above grade plane (Gordium: Stories above grade plane, as "
                          "R202 STORY ABOVE GRADE PLANE counts them)")


# ---- the rest of R101.2 ---------------------------------------------------------------------------------------------

def test_the_architects_count_decides_over_ithacas_and_ithacas_stands_in_only_up_to_three():
    house = {"use": "one_family_detached", "stories": 3}
    assert code(house)[0] == code_scope.RESIDENTIAL                         # Ithaca's 3: the State's at most 3
    assert code(dict(house, stories=4))[0] is None                          # a habitable attic may not count (R316.3)
    assert code(dict(house, stories=4), {"stories_above_grade_plane": 3})[0] == code_scope.RESIDENTIAL
    assert code(house, {"stories_above_grade_plane": 4})[0] == code_scope.BUILDING
    assert code(dict(house, stories=None))[0] is None


@pytest.mark.parametrize("more, cite", [({"home_occupation": True}, "BCNYS 202 LIVE/WORK UNIT"),
                                        ({"rooms_let_for_profit": 2}, "BCNYS 310.4.2"),
                                        ({"care_facility": True}, "BCNYS 308.2.4")])
def test_a_house_with_a_use_r101_2_sets_conditions_on_needs_a_persons_check(more, cite):
    c, cites, got = code({"use": "one_family_detached", "stories": 2, **more})
    assert c is None and cite in cites and "Gordium: Follows the Building Code" in got["ask"]


def test_the_exception_lets_the_architect_apply_the_building_code_to_a_house():
    c, cites, got = code({"use": "one_family_detached", "stories": 2}, {"follows_building_code": True})
    assert c == code_scope.BUILDING and cites == ["RCNYS R101.2 exception"]
    assert code({"use": "one_family_detached", "stories": 2}, {"follows_building_code": False})[0] == \
        code_scope.RESIDENTIAL


def test_a_building_fact_gordium_cant_read_is_said_never_used():
    c, _, got = code({"use": "one_family_detached", "stories": 2}, {"stories_above_grade_plane": "three"})
    assert c is None and "stories above grade plane is “three”" in got["why"]
    assert code_scope.building_measures({"occupancy_groups": ["R-2", "office"]}) == {}


def test_the_building_measures_follow_the_groups_and_the_sprinkler_system():
    assert code_scope.building_measures({"occupancy_groups": ["R-2"], "sprinkler_system": "nfpa_13r"}) == {
        "occupancy_group_i4": False, "other_occupancy_present": True, "sprinklered_903_3_1_1": False,
        "sprinklered_903_3_1_2": True}
    assert code_scope.building_measures({"occupancy_groups": ["I-4"], "sprinkler_system": "nfpa_13"}) == {
        "occupancy_group_i4": True, "other_occupancy_present": False, "sprinklered_903_3_1_1": True,
        "sprinklered_903_3_1_2": False}
    assert code_scope.building_measures({"sprinkler_system": "nfpa_13d"}) == {
        "sprinklered_903_3_1_1": False, "sprinklered_903_3_1_2": False}       # 903.3.1.3: neither limit's system


# ---- in the check -----------------------------------------------------------------------------------------------------

def ranch():
    return load(RANCH)


def test_a_house_is_checked_exactly_as_it_was_before_the_building_code_was_inherited():
    """The pin for "the residential path byte for byte": the house code alone (the laws as before 2026-11-22) and
    both laws give the same rows, results, items and sections for a house the Residential Code covers."""
    found = egress.laws(ITHACA)
    before = copy.deepcopy(found)
    before["laws"] = [law for law in before["laws"] if law["key"] == "new_york/new_york_state"]
    for law in before["laws"]:
        law["scope"] = None                                   # as the folder was: no scope, always run
    values = {"use": "one_family_detached", "stories": 1, "dwelling_units": 1, **DRAWN}
    for interior in (ranch(), None, dict(ranch(), rooms=[])):
        old = egress.check(before, interior, values, {"use": set()})
        new = egress.check(found, interior, values, {"use": set()})
        assert new["code_scope"]["code"] == code_scope.RESIDENTIAL
        assert {k: v for k, v in new.items() if k != "code_scope"} == old


def test_an_apartment_building_is_checked_against_the_building_code_alone():
    got = egress.check(egress.laws(ITHACA), None, {"use": "multiple_family"}, {"use": set()})
    assert [s["title"] for s in got["sections"]] == ["Egress (NY State Building Code 2025)"]
    assert [(i["status"], i["name"]) for i in got["items"]] == [
        (present.NOT_CHECKED, "Egress: waiting, no rooms drawn yet"),
        (present.NOT_APPLICABLE, "This building is under the NY State Building Code 2025")]
    assert got["items"][0]["reason"].startswith("Travel distance, common path, the number of exits")   # its own words


def test_where_it_cant_tell_both_run_each_held_at_needs_review_never_the_calm_waiting():
    got = egress.check(egress.laws(ITHACA), None, {"use": "one_family_detached"}, {"use": set()})
    assert [s["state"] for s in got["sections"]] == [present.REVIEW, present.REVIEW]
    scope = [i for i in got["items"] if i["name"] == egress.SCOPE_OPEN_NAME]
    assert len(scope) == 2 and all(i["status"] == present.REVIEW for i in scope)
    assert "To settle it, state the building's stories above grade plane" in scope[0]["reason"]
    view = {"items": [{"id": "z", "rule": "z", "name": "Rear yard", "group": "building", "status": present.COMPLIES}]}
    egress.add_to_view(view, got, "City of Ithaca")
    assert view["state"] == present.REVIEW and view["waiting_only"] is False


def test_the_answer_carries_which_code_in_the_deciders_own_words():
    result = check_site(SITE, dict(FACTS), interior=ranch())
    which = result["which_code"]
    assert set(which) == {"code", "title", "why", "cites", "ask", "assumes"}
    from design_checker.check import _with_stories_bound
    values = _with_stories_bound({k: m["value"] for k, m in result["measurements"].items()}, result["measurements"])
    assert values[code_scope.STORIES_DRAWN] is True                 # the box house: its stories read from the drawing
    assert which == {k: code_scope.decide(values, None)[k] for k in which}
    assert all(set(c) == {"section", "document", "page", "quote"} for c in which["cites"])


def test_a_building_code_flag_for_the_whole_building_is_its_own_needs_review_line():
    found = egress.laws(ITHACA)
    bcnys = next(law for law in found["laws"] if law["scope"] == code_scope.BUILDING)
    flag = next(r for r in bcnys["rules"] if r["id"] == "general.bc_table_1017_2_other_occupancies")
    out = {}
    item = egress._flag_item(bcnys, flag, flag["id"], {"other_occupancy_present": True}, bcnys["kinds"], out)
    assert item["status"] == present.REVIEW and item["reason"].startswith("A person checks this")
    assert item["code"]["section"] and out[flag["id"]] == "needs_review"
    item = egress._flag_item(bcnys, flag, flag["id"], {"other_occupancy_present": False}, bcnys["kinds"], {})
    assert item["status"] == present.NOT_APPLICABLE and "other_occupancy_present: False" in item["reason"]


# ---- the quotes are the books' own words -------------------------------------------------------------------------------

BOOKS = {code_scope.RCNYS: "36490d8c8b11dd2b12c50bb11bd78c4aa228b38245d2fe99225cabe059398451/gov.ny.residential.2025.pdf",
         code_scope.BCNYS: "729d2db7ca361764cc8ce131f89a42a5fef5b22ce819fa96f428865aaacc4ca9/gov.ny.building.2025.pdf"}


def _flat(text: str) -> str:
    """A page's text as one line: a word broken at a line end joined again, every run of spaces one space."""
    text = re.sub(r"-\n(?=[a-z])", "", text)
    return " ".join(text.split())


@pytest.mark.parametrize("key", sorted(code_scope.CITES))
def test_every_quote_is_on_its_page_in_the_book(key):
    book, page, quote = code_scope.CITES[key]
    pdf = code_cache() / BOOKS[book]
    if not pdf.is_file():
        pytest.skip(f"{pdf.name} isn't in the code cache here (kept outside the repo)")
    import pdfplumber
    with pdfplumber.open(pdf) as doc:
        text = _flat(doc.pages[page - 1].extract_text() or "")
    assert " ".join(quote.split()) in text


def test_an_open_stories_count_still_settles_the_code_when_every_reading_is_three_or_fewer():
    """Scenes 18 and 20: a 20 ft solid with no floor marks holds 1 or 2 stories, an open question for Ithaca's
    count, but either way not more than three above grade plane: the Residential Code (check.py passes the most)."""
    house = {"use": "one_family_detached", "stories": None}
    assert code({**house, code_scope.STORIES_AT_MOST: 2})[0] == code_scope.RESIDENTIAL
    assert code({**house, code_scope.STORIES_AT_MOST: 5})[0] is None
    from design_checker.check import _with_stories_bound
    measured = {"stories": {"value": None, "objects": ["b1"], "readings": [{"reading": "at least", "value": 1},
                                                                           {"reading": "at most", "value": 2}]}}
    got = _with_stories_bound({"stories": None}, measured)
    assert (got[code_scope.STORIES_AT_MOST], got[code_scope.STORIES_DRAWN]) == (2, True)
    assert code_scope.STORIES_AT_MOST not in _with_stories_bound({"stories": 2}, measured)   # a count needs no bound
    assert code_scope.STORIES_AT_MOST not in _with_stories_bound({"stories": None}, {"stories": {"value": None}})


# ---- review round 1 (2026-11-22) --------------------------------------------------------------------------------------

@pytest.mark.parametrize("values, why", [
    # F1: a building's units counted for every use word, an attached ADU one more of them (R202 DWELLING: one or two)
    ({"use": "two_family", "stories": 2, "accessory_dwelling_unit": True, "adu_detached": False}, "3 dwelling units"),
    ({"use": "one_family_semi_detached", "stories": 2, "accessory_dwelling_unit": True, "adu_detached": False},
     "3 dwelling units"),
    ({"use": "one_family_attached", "attached_units_in_building": 2, "stories": 2, "accessory_dwelling_unit": True,
      "adu_detached": False}, "3 dwelling units")])
def test_three_units_in_one_building_are_never_the_residential_codes(values, why):
    c, cites, got = code(values, {"separate_means_of_egress": True})
    assert c == code_scope.BUILDING and why in got["why"] and "BCNYS 310.3" in cites


def test_dwelling_units_that_disagree_with_any_use_word_need_review():
    c, _, got = code({"use": "two_family", "dwelling_units": 3, "stories": 2}, {"separate_means_of_egress": True})
    assert c is None and "Gordium: Dwelling units" in got["ask"]
    assert code({"use": "two_family", "dwelling_units": 2, "stories": 2},
                {"separate_means_of_egress": True})[0] == code_scope.RESIDENTIAL


def test_a_townhouse_unit_with_an_accessory_dwelling_unit_needs_review():
    c, cites, _ = code({"use": "one_family_attached", "attached_units_in_building": 4, "accessory_dwelling_unit": True,
                        "adu_detached": False}, {"townhouse_units": True, "stories_above_grade_plane": 3})
    assert c is None and "RCNYS R202 TOWNHOUSE UNIT" in cites


def test_a_house_with_an_attached_adu_is_a_two_family_dwelling_and_an_unknown_adu_needs_review():
    house = {"use": "one_family_detached", "stories": 2, "accessory_dwelling_unit": True}
    assert code({**house, "adu_detached": False})[0] is None                          # separate means of egress?
    assert code({**house, "adu_detached": False}, {"separate_means_of_egress": True})[0] == code_scope.RESIDENTIAL
    assert code({**house, "adu_detached": True})[0] == code_scope.RESIDENTIAL
    c, _, got = code(house)
    assert c is None and "Gordium: ADU detached" in got["ask"]


@pytest.mark.parametrize("values", [
    {"use": "one_family_detached", "stories": 3},                                  # F2: a typed count, nothing drawn
    {"use": "one_family_detached", "stories": 3, code_scope.STORIES_DRAWN: False}])
def test_a_typed_ithaca_count_alone_never_stands_in_for_the_states(values):
    got = code_scope.decide(values, None)
    assert got["code"] is None and "Gordium: Stories above grade plane" in got["ask"]


def test_check_passes_the_drawn_count_only_from_drawn_parts_without_a_geometry_error():
    from design_checker.check import _with_stories_bound
    drawn = {"stories": {"value": 3, "objects": ["b1"], "readings": []}}
    assert _with_stories_bound({"stories": 3}, drawn)[code_scope.STORIES_DRAWN] is True
    typed = {"stories": {"value": 3, "objects": [], "readings": [], "how": "stated by the architect"}}
    assert _with_stories_bound({"stories": 3}, typed)[code_scope.STORIES_DRAWN] is False
    broken = {**drawn, "lot_area": {"value": None, "geometry_error": "the drawing's geometry couldn't be worked out"}}
    assert _with_stories_bound({"stories": 3}, broken)[code_scope.STORIES_DRAWN] is False


def test_with_no_buildings_drawn_a_typed_count_asks_for_the_states_count():
    site = {"units": "ft", "lot": lot([(0, 0), (60, 0), (60, 110), (0, 110)]), "buildings": [], "problems": []}
    which = check_site(site, dict(FACTS, stories=3))["which_code"]
    assert which["code"] is None and "Gordium: Stories above grade plane" in which["ask"]


def test_what_isnt_stated_about_a_house_is_assumed_out_loud_and_a_stated_one_decided_by_the_law():
    # F3: Gordium's reading (decision 2a), listed in the answer and said in its words
    c, _, got = code({"use": "one_family_detached", "stories": 2})
    assert c == code_scope.RESIDENTIAL
    assert got["assumes"] == ["no one outside the household receives care here", "no home occupation",
                              "no rooms let for profit", "no accessory dwelling unit",
                              "the use's own dwelling units on the lot"]
    assert "Gordium assumes no one outside the household receives care here" in got["why"]
    assert "Gordium: Care facility" in got["why"] and "Gordium: Accessory dwelling unit" in got["why"]
    stated = {"use": "one_family_detached", "stories": 2, "home_occupation": False, "rooms_let_for_profit": 0,
              "accessory_dwelling_unit": False, "dwelling_units": 1}
    _, _, got = code(stated, {"care_facility": False})
    assert got["assumes"] == [] and "assumes" not in got["why"]
    for more, building in (({"home_occupation": True}, None), ({"rooms_let_for_profit": 1}, None),
                           ({}, {"care_facility": True})):
        assert code({**stated, **more}, {"care_facility": False, **(building or {})})[0] is None


@pytest.mark.parametrize("building, said", [(["stories_above_grade_plane", 2], "not a mapping"),
                                            ({"stories_above_gradeplane": 2}, "is no fact Gordium reads")])
def test_a_building_block_gordium_cant_read_is_said_never_dropped(building, said):
    # F4: a block that isn't a mapping, or a misspelled fact, needs review naming it
    got = code_scope.decide({"use": "one_family_detached", "stories": 2, **DRAWN}, building)
    assert got["code"] is None and said in got["why"]


def test_every_mark_an_ask_names_is_one_the_add_in_defines():
    # F5: an ask never names a mark the architect can't find
    marks = set(re.findall(r'"(Gordium: [^"]+)", new\("[0-9a-f-]+"\)',
                           (REPO / "apps/revit_addin/src/Gordium.Revit.Reading/Marks.cs").read_text(encoding="utf-8")))
    assert set(code_scope.MARK.values()) <= marks, set(code_scope.MARK.values()) - marks


# ---- review round 2 (2026-11-22) --------------------------------------------------------------------------------------

@pytest.mark.parametrize("values", [
    {"use": "two_family", "stories": 2, "adu_detached": False},                   # an attached ADU, the ADU blank
    {"use": "one_family_semi_detached", "stories": 2, "adu_detached": False},
    {"use": "one_family_detached", "stories": 2, "adu_detached": True},
    {"use": "two_family", "stories": 2, "accessory_dwelling_unit": False, "adu_detached": False}])   # contradiction
def test_an_adus_kind_stated_is_never_read_as_no_adu(values):
    c, _, got = code(values, {"separate_means_of_egress": True})
    assert c is None and "Gordium: Accessory dwelling unit" in got["ask"]


def test_facts_the_measuring_set_aside_are_never_read_as_unstated():
    # three units and ten occupants with at most one in a unit can't all be so (measure.py fact_conflicts): the units
    # and the ADU answer are set aside, so the use's own count never decides
    site = {"units": "ft", "lot": lot([(0, 0), (60, 0), (60, 110), (0, 110)]),
            "buildings": [box(10, 25, 40, 75, 0, 30)], "problems": []}
    facts = dict(FACTS, use="one_family_detached", dwelling_units=3, occupants=10, occupants_most_in_one_unit=1,
                 accessory_dwelling_unit=False)
    interior = {"format": "gordium.interior/1", "units": "ft", "rooms": [], "building": {"stories_above_grade_plane": 2}}
    which = check_site(site, facts, interior=interior)["which_code"]
    assert which["code"] is None and "set aside" in which["why"] and "dwelling units" in which["why"]
    assert "no accessory dwelling unit" not in which["assumes"]


def test_dwelling_units_leave_the_adu_out_and_one_more_beside_an_adu_needs_review():
    # review round 3: one definition, the mark's and Ithaca's: the lot's dwelling units leave an ADU out
    for detached, building in ((True, {}), (False, {"separate_means_of_egress": True})):
        c, _, got = code({"use": "one_family_detached", "dwelling_units": 2, "accessory_dwelling_unit": True,
                          "adu_detached": detached}, {"stories_above_grade_plane": 2, **building})
        assert c is None and "Gordium: Dwelling units" in got["ask"] and "may or may not count" in got["why"]
    c, _, got = code({"use": "one_family_detached", "dwelling_units": 1, "accessory_dwelling_unit": True,
                      "adu_detached": True}, {"stories_above_grade_plane": 2})
    assert c == code_scope.RESIDENTIAL and got["facts"]["building_units"] == 1     # the ADU in its own building
    assert code({"use": "one_family_detached", "dwelling_units": 2}, {"stories_above_grade_plane": 2})[0] is None


def test_a_typed_count_checked_against_the_drawing_is_said_so_unlike_a_count_read_from_floors():
    typed = code({"use": "one_family_detached", "stories": 3, code_scope.STORIES_HOW: "typed"})[2]["why"]
    read = code({"use": "one_family_detached", "stories": 3, code_scope.STORIES_HOW: "read"})[2]["why"]
    assert "Ithaca's count as the architect states it, checked against the drawing: nothing drawn below the ground, " \
           "so at most 3 above grade plane" in typed
    assert "Ithaca's count read from the drawn floors, nothing drawn below the ground, so at most 3" in read
    from design_checker.check import _with_stories_bound
    rec = {"value": 3, "objects": ["b1"], "readings": [], "how": "the stories of the building, ...", "stated": True}
    assert _with_stories_bound({"stories": 3}, {"stories": rec})[code_scope.STORIES_HOW] == "typed"   # the flag
    rec.pop("stated")
    rec["how"] = "stated by the architect for the whole building, ..."                            # never the words
    assert _with_stories_bound({"stories": 3}, {"stories": rec})[code_scope.STORIES_HOW] == "read"


def test_a_typed_count_over_a_house_and_a_garage_is_still_said_to_be_the_architects():
    # review round 3: the merged record over candidate buildings lost the words; the measuring's flag says it
    site = {"units": "ft", "lot": lot([(0, 0), (60, 0), (60, 110), (0, 110)]),
            "buildings": [box(10, 25, 40, 75, 0, 30), box(45, 80, 57, 100, 0, 12, id="garage")], "problems": []}
    got = check_site(site, dict(FACTS, stories=3, main_building="house"))
    record = got["measurements"]["stories"]
    assert record.get("stated") is True and record["how"] == "the stories of the building, read over its candidate buildings"
    why = got["which_code"]["why"]
    assert "as the architect states it" in why and "read from the drawn floors" not in why


# ---- review round 4 (2026-11-22) --------------------------------------------------------------------------------------

@pytest.mark.parametrize("values, building", [
    ({"use": "one_family_detached", "dwelling_units": 1, "accessory_dwelling_unit": True, "adu_detached": False,
      "adus_on_parcel": 2, "stories": 2}, {"separate_means_of_egress": True}),
    ({"use": "two_family", "accessory_dwelling_unit": True, "adu_detached": True, "adus_on_parcel": 2,
      "stories": 2}, {"separate_means_of_egress": True})])
def test_more_than_one_adu_whose_kinds_arent_all_known_needs_review(values, building):
    c, cites, got = code(values, building)
    assert c is None and "BCNYS 310.3" in cites and "whether each is detached" in got["ask"]
    assert code({**values, "adus_on_parcel": 1}, building)[0] == code_scope.RESIDENTIAL      # one ADU: its kind known


def test_a_set_aside_adu_count_is_never_read_as_unstated():
    got = code_scope.decide({**DRAWN, "use": "one_family_detached", "stories": 2,
                             code_scope.SET_ASIDE: {"adus_on_parcel": "the counts disagree"}}, None)
    assert got["code"] is None and "adus on parcel: the counts disagree" in got["why"]


# ---- review round 6 (2026-11-22) --------------------------------------------------------------------------------------

@pytest.mark.parametrize("use", ["one_family_semi_detached", "two_family", "one_family_detached"])
def test_units_in_the_building_that_disagree_with_a_houses_use_need_review(use):
    c, _, got = code({"use": use, "attached_units_in_building": 4, "stories": 2}, {"separate_means_of_egress": True})
    assert c is None and "Gordium: Units in the attached building" in got["ask"]
    own = {"one_family_semi_detached": 2, "two_family": 2, "one_family_detached": 1}[use]
    assert code({"use": use, "attached_units_in_building": own, "stories": 2},
                {"separate_means_of_egress": True})[0] == code_scope.RESIDENTIAL
