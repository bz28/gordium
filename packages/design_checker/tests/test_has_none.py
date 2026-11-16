"""What the interior description says the house has none of (`has_none`), through the whole egress check: a claim
sets aside its rules as not applicable, shown in the panel with its source, never hidden and never a pass; silence,
or a claim that can't be trusted, stays needs review (docs/decisions/2026-11-16_interior_absent_parts.md).

The rules are New York State's own rulebook, loaded the only way the checker loads it (through Ithaca).
"""

import copy

import pytest

from design_checker import egress, present
from permit_sheets import words as sheet_words

ITHACA = "regulations/jurisdictions/new_york/ithaca_city"
RAMP_RULES = {"general.r318_8_1_ramp_max_slope_egress_door", "general.r318_8_1_ramp_max_slope_other",
              "general.r318_8_1_ramp_max_slope_infeasible", "general.r318_8_2_ramp_landings_present",
              "general.r318_8_2_ramp_landing_width", "general.r318_8_2_ramp_landing_depth",
              "general.r318_8_3_ramp_handrail_one_side"}
SOURCE = "none drawn: A-2 main floor plan"


@pytest.fixture(scope="module")
def found():
    return egress.laws(ITHACA)


def house(*claims, **lists):
    """One bedroom with a casement window and a side-hinged exit door (inches), and what it says it has none of."""
    d = {"format": "gordium.interior/1", "units": "in",
         "rooms": [{"id": "b", "name": "Bedroom", "sleeping": True, "floor": [[0, 0], [120, 0], [120, 120], [0, 120]],
                    "floor_elevation": 0, "ceiling_height": 96}],
         "openings": [{"id": "w", "name": "Window", "room": "b", "escape": True, "operation": "casement",
                       "frame": {"left": 0, "right": 30, "bottom": 20, "top": 60},
                       "hinged": {"side": "left", "open_angle": 90, "sash_width": 30, "sash_thickness": 2,
                                  "hinge_offset": 0},
                       "ground_outside": 0}],
         "doors": [{"id": "d", "name": "Door", "exit": True, "operation": "side_hinged", "hinge_side": "left",
                    "stops": {"hinge": 0, "latch": 34}, "hinge_pin": [0, 1.75], "leaf_closed": [[0, 0], [35, 1.75]],
                    "threshold_top": 0, "head_stop_bottom": 80}],
         "stairs": [], "guards": []}
    if claims:
        d["has_none"] = list(claims)
    d.update(lists)
    return d


def run(found, desc):
    return egress.check(found, desc, {"dwelling_units": 1}, {"use": set()})


def claim_items(got):
    return [i for i in got["items"] if i.get("has_none")]


def test_silence_stays_needs_review(found):
    got = run(found, house())
    assert {got["results"][r] for r in RAMP_RULES} == {"needs_review"}
    assert claim_items(got) == []
    ramp_rows = [r for r in got["rows"] if r["rule"] in RAMP_RULES]
    assert ramp_rows and all(r["reason"] == "the ramps aren't read yet" for r in ramp_rows)


def test_a_claim_gives_not_applicable_shown_with_its_source(found):
    got = run(found, house({"kind": "ramp", "source": SOURCE}))
    assert {got["results"][r] for r in RAMP_RULES} == {"not_applicable"}
    items = claim_items(got)
    assert [i["name"] for i in items] == ["Ramps: not applicable"]
    item = items[0]
    assert item["status"] == present.NOT_APPLICABLE and item["mark"] == present.MARK[present.NOT_APPLICABLE]
    assert item["reason"].startswith("Not applicable: the description says the house has no ramps (" + SOURCE + ")")
    assert set(item["has_none"]["rules"]) == RAMP_RULES
    assert item["has_none"]["source"] == SOURCE
    assert item["detail"]["citation"] == "R318.8.1, R318.8.2, R318.8.3"
    assert item["group"] == present.LAW_GROUP
    # every rule it set aside is named in the item, and each of its rows says why, with the source
    for rule in RAMP_RULES:
        assert next(r for r in item["has_none"]["rules"] if r == rule)
    for row in (r for r in got["rows"] if r["rule"] in RAMP_RULES):
        assert row["outcome"] == "not_applicable" and row["has_none"] == "ramp"
        assert row["line"] == f"Ramps: not applicable: the description says the house has no ramps ({SOURCE})"
    # the panel's own words for its status
    from design_checker.host_core.panel_words import status_words
    assert status_words(item) == "Not applicable"


def test_a_claim_counts_toward_nothing(found):
    """Never a pass, never a reason to review: alone it is nothing checked (needs review), and beside a pass it
    changes nothing (present._building_items leaves it out)."""
    claimed = run(found, house({"kind": "ramp", "source": SOURCE}))
    assert "not applicable" not in claimed["sections"][0]["summary"]
    na = claim_items(claimed)[0]
    passing = dict(na, status=present.COMPLIES, id="x")
    assert present.state([na]) == present.REVIEW
    assert present.state([na, passing]) == present.COMPLIES == present.state([passing])
    assert present._summary([na, passing]) == present._summary([passing])


def test_a_law_whose_only_items_are_claims_is_still_nothing_checked(found):
    law = next(law for law in found["laws"])
    ramp_only = [r for r in law["rules"] if r["id"] in RAMP_RULES]
    measured = egress.measure_interior(house({"kind": "ramp", "source": SOURCE}))
    measured["problems"] = []
    out = egress._law_items({**law, "rules": ramp_only}, measured, {"dwelling_units": 1}, {"use": set()}, [], {})
    assert [i["status"] for i in out] == [present.NOT_APPLICABLE, present.REVIEW]
    assert out[1]["id"].endswith(".nothing_applied")
    assert present.state(out) == present.REVIEW


def test_a_reading_is_one_to_confirm(found):
    got = run(found, house({"kind": "ramp", "source": SOURCE, "reading": True}))
    assert {got["results"][r] for r in RAMP_RULES} == {"not_applicable"}
    item = claim_items(got)[0]
    assert item["status"] == present.REVIEW
    assert item["name"] == "Ramps: not applicable if this reading is confirmed"
    assert item["reason"].startswith("Confirm: the description says the house has no ramps, a reading to confirm (")
    assert SOURCE in item["reason"]
    assert all(r["line"].startswith("Ramps: not applicable if confirmed: ") for r in got["rows"]
               if r["rule"] in RAMP_RULES)


@pytest.mark.parametrize("claims, lists", [
    ([{"kind": "ramp", "source": SOURCE}], {"ramps": [{"id": "r1"}]}),           # contradicted by an actual ramp
    ([{"kind": "ramp"}], {}),                                                    # no source
    ([{"kind": "ramp", "source": SOURCE}, {"kind": "ramp", "source": "A-4"}], {}),   # twice
    ([{"kind": "ramps", "source": SOURCE}], {}),                                 # not a kind it knows
])
def test_a_claim_not_taken_is_a_problem_item_and_its_rules_need_review(found, claims, lists):
    got = run(found, house(*claims, **lists))
    assert {got["results"][r] for r in RAMP_RULES} == {"needs_review"}
    assert claim_items(got) == []
    problems = [i for i in got["items"] if i["name"] == "Interior drawing"]
    assert problems and all(i["status"] == present.REVIEW for i in problems)
    assert got["interior"]["problems"]


def test_a_contradicted_claim_says_which_list(found):
    got = run(found, house({"kind": "ramp", "source": SOURCE}, ramps=[{"id": "r1"}]))
    assert any("yet it also gives `ramps`, which isn't an empty list" in i["reason"] for i in got["items"] if i["name"] == "Interior drawing")


def test_a_claim_about_the_openings_sets_aside_only_the_rules_that_turn_on_it(found):
    got = run(found, house({"kind": "patio_cover", "source": "A-2"},
                           {"kind": "deck_porch_or_cantilever_over_escape_opening", "source": "A-3"}))
    assert got["results"]["general.bf103_2_escape_opening_into_patio_cover_unenclosed"] == "not_applicable"
    assert got["results"]["general.r319_2_4_under_projection_openable_path"] == "not_applicable"
    by_kind = {i["has_none"]["kind"]: i for i in claim_items(got)}
    assert by_kind["patio_cover"]["has_none"]["rules"] == ["general.bf103_2_escape_opening_into_patio_cover_unenclosed"]
    assert by_kind["deck_porch_or_cantilever_over_escape_opening"]["has_none"]["rules"] == [
        "general.r319_2_4_under_projection_openable_path"]
    assert by_kind["deck_porch_or_cantilever_over_escape_opening"]["name"] == \
        "Decks, porches or cantilevers over an escape opening: not applicable"
    # the egress door's patio-cover flag has no applies_when: no claim about openings sets it aside
    assert got["results"]["general.bf103_2_exit_into_patio_cover_r318_exits"] == "needs_review"


def test_the_loft_claim_settles_the_rooms_lofts_are_open_to(found):
    got = run(found, house({"kind": "sleeping_loft", "source": "A-3"}))
    for rule in ("general.r319_1_loft_room_escape_opening_operable", "general.r319_1_room_a_sleeping_loft_is_open_to",
                 "general.r315_2_sleeping_loft_floor_area_limit"):
        assert got["results"][rule] == "not_applicable", rule
    assert set(claim_items(got)[0]["has_none"]["rules"]) >= {"general.r319_1_loft_room_escape_opening_operable"}


def test_the_facts_as_measures_reach_the_rules(found):
    got = run(found, house())
    assert got["results"]["general.r318_2_egress_door_side_hinged"] == "pass"           # operation: side_hinged
    assert got["results"]["general.r319_3_escape_door_side_hinged_or_sliding"] == "not_applicable"   # a casement
    sliding = house()
    sliding["doors"][0]["operation"] = "sliding"
    assert run(found, sliding)["results"]["general.r318_2_egress_door_side_hinged"] == "fail"
    unknown = house()
    unknown["doors"][0]["operation"] = "other"
    unknown["openings"][0]["operation"] = "pivot"
    got = run(found, unknown)
    assert got["results"]["general.r318_2_egress_door_side_hinged"] == "needs_review"
    assert got["results"]["general.r319_3_escape_door_side_hinged_or_sliding"] == "needs_review"


def test_the_permit_sheets_print_it_never_kinder():
    assert sheet_words.result_words(present.NOT_APPLICABLE) == "NOT APPLICABLE"
    assert sheet_words.worst([present.NOT_APPLICABLE, present.COMPLIES]) == present.COMPLIES
    assert sheet_words.worst([present.NOT_APPLICABLE, present.REVIEW]) == present.REVIEW


def test_the_description_given_is_never_changed(found):
    desc = house({"kind": "ramp", "source": SOURCE})
    before = copy.deepcopy(desc)
    run(found, desc)
    assert desc == before


# --- a claim is credited only where it decides the row; a reading never gives a pass (review round 1) ---------------

def _stair_rule(found, rule_id):
    return next(r for law in found["laws"] for r in law["rules"] if r["id"] == rule_id)


def _stair(spiral):
    return {"id": "s1", "name": "Stair", "measures": {"stair_serves_sleeping_loft": False, "stair_spiral": spiral,
                                                      "stair_clear_width": 40},
            "not_measured": {}, "stated": {"stair_serves_sleeping_loft": "sleeping_loft"}}


LOFT = {"sleeping_loft": {"source": "A-3", "reading": False, "words": "the description says the house has no "
                          "sleeping lofts", "parts": ["sleeping_loft", "loft_room"], "openings": {},
                          "stairs": {"stair_serves_sleeping_loft": False}}}


def test_a_row_not_applicable_for_another_reason_is_not_the_claims(found):
    """R318.7.1 applies to a stair that is not a loft stair and not spiral: a spiral stair is not applicable
    whatever the loft claim says, so the row keeps its own reason and the claim doesn't list the rule."""
    from design_checker import each_part
    rule = _stair_rule(found, "general.r318_7_1_stair_clear_width_above_handrail")
    got = each_part.check_parts([rule], {"stair": [_stair(True)], "sleeping_loft": [], "loft_room": []},
                                {"dwelling_units": 1}, {"use": set()}, LOFT)
    row = next(r for r in got["rows"] if r["id"] == "s1")
    assert row["outcome"] == "not_applicable" and "has_none" not in row
    assert got["set_aside"] == {"sleeping_loft": []}


def test_a_pass_that_reads_a_reading_claims_measure_needs_review(found):
    from design_checker import each_part
    rule = _stair_rule(found, "general.r318_7_1_stair_clear_width_above_handrail")
    given = {"stair": [_stair(False)], "sleeping_loft": [], "loft_room": []}
    settled = each_part.check_parts([rule], given, {"dwelling_units": 1}, {"use": set()}, LOFT)
    assert next(r for r in settled["rows"] if r["id"] == "s1")["outcome"] == "pass"     # a stated fact: a real pass
    reading = {"sleeping_loft": dict(LOFT["sleeping_loft"], reading=True)}
    got = each_part.check_parts([rule], given, {"dwelling_units": 1}, {"use": set()}, reading)
    row = next(r for r in got["rows"] if r["id"] == "s1")
    assert row["outcome"] == "needs_review" and row["has_none"] == "sleeping_loft"
    assert row["reason"].startswith("complies only if this reading is confirmed: ")
    assert got["results"]["general.r318_7_1_stair_clear_width_above_handrail"] == "needs_review"


@pytest.mark.parametrize("claims, says", [
    ([], "required in a basement, habitable attic or room a sleeping loft is open to (R319.1), which aren't read"),
    ([{"kind": "basement", "source": "A-1"}, {"kind": "sleeping_loft", "source": "A-3"}],
     "required in a habitable attic (R319.1), which isn't read from the drawing"),
    ([{"kind": "basement", "source": "A-1"}, {"kind": "sleeping_loft", "source": "A-3"},
      {"kind": "habitable_attic", "source": "A-5", "reading": True}],
     "required in a habitable attic (R319.1), which isn't read from the drawing"),
    ([{"kind": "basement", "source": "A-1"}, {"kind": "habitable_attic", "source": "A-5"}],
     "required in a room a sleeping loft is open to (R319.1), which isn't read from the drawing"),
    ([{"kind": "basement", "source": "A-1"}, {"kind": "habitable_attic", "source": "A-5"},
      {"kind": "sleeping_loft", "source": "A-3"}],
     "has no basements, no habitable attics and no sleeping lofts, the other spaces R319.1 asks for one in"),
])
def test_an_unchecked_escape_opening_names_only_the_spaces_not_settled(found, claims, says):
    """An office's escape window isn't checked (not a sleeping room): its words never call a basement "not read"
    beside a "Basements: not applicable" item, and it stays needs review either way (review round 3)."""
    desc = house(*claims)
    desc["rooms"].append({"id": "o", "name": "Office", "sleeping": False, "floor": [[200, 0], [300, 0], [300, 100],
                                                                                    [200, 100]],
                          "floor_elevation": 0, "ceiling_height": 96})
    desc["openings"].append(dict(desc["openings"][0], id="ow", name="Office window", room="o"))
    item = next(i for i in run(found, desc)["items"] if i["name"] == "Office window: not checked")
    assert item["status"] == present.REVIEW and says in item["reason"]
