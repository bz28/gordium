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


def code(values, building=None):
    got = code_scope.decide(values, building)
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
    assert c is None and "stories above grade plane is 'three'" in got["why"]
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
    values = {"use": "one_family_detached", "stories": 1, "dwelling_units": 1}
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
    assert set(which) == {"code", "title", "why", "cites", "ask"}
    assert which == {k: code_scope.decide(result["measurements"] and {k2: m["value"] for k2, m in
                                                                     result["measurements"].items()},
                                          None)[k] for k in which}
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
    measured = {"stories": {"value": None, "readings": [{"reading": "at least", "value": 1},
                                                         {"reading": "at most", "value": 2}]}}
    assert _with_stories_bound({"stories": None}, measured)[code_scope.STORIES_AT_MOST] == 2
    assert _with_stories_bound({"stories": 2}, measured) == {"stories": 2}          # a count needs no bound
    assert _with_stories_bound({"stories": None}, {"stories": {"value": None}}) == {"stories": None}
