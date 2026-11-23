"""What the rebuilt results pane reads beyond today's fields (design_checker/ui_data.py, changes C1 to C9 of the UI
polish design, 2026-11-23): each pinned so it fails when its change is reverted. Words and data only: none of these
fields is a status, and the goldens prove no status, verdict or figure changed (docs/revit/checker_ui_data.md)."""

import json

import pytest

from design_checker import code_scope, each_part, panel_data, present, ui_data
from rule_format import parts
from rule_format.rulebook import REPO

APARTMENT = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json"


# ---- C1: a cause names the field that answers it ------------------------------------------------------------

def test_a_building_measure_is_answered_by_the_fact_it_is_worked_out_from():
    assert code_scope.field_of("occupancy_group_i4") == "building.occupancy_groups"
    assert code_scope.field_of("other_occupancy_present") == "building.occupancy_groups"
    assert code_scope.field_of("sprinklered_903_3_1_1") == "building.sprinkler_system"
    assert code_scope.field_of("sprinklered_903_3_1_2") == "building.sprinkler_system"
    assert code_scope.field_of("space_occupant_load") is None
    # the one table: every measure building_measures gives is one field_of names, and the other way round
    given = code_scope.building_measures({"occupancy_groups": ["R-2"], "sprinkler_system": "nfpa_13",
                                          "egress_balcony_increase_taken": False, "building_has_atrium": False})
    assert set(given) == set(code_scope.DERIVED)
    assert given["occupancy_group_i4"] is False and given["other_occupancy_present"] is True
    assert given["sprinklered_903_3_1_1"] is True and given["sprinklered_903_3_1_2"] is False


def test_two_measures_from_one_fact_are_one_ask_naming_its_field():
    causes = [{"kind": "mark", "key": f"fact:{m}", "words": f"{m}: not stated", "elements": [], "measure": m,
               "field": f"facts.{m}"} for m in ("occupancy_group_i4", "other_occupancy_present",
                                                 "sprinklered_903_3_1_1")]
    got = ui_data.asks_of({"status": present.REVIEW, "group": present.LAW_GROUP, "causes": causes}, {})
    assert [a["field"] for a in got] == ["building.occupancy_groups", "building.sprinkler_system"]
    assert [a["headline"] for a in got] == ["Set the occupancy group", "Set the sprinkler system"]
    assert all(a["kind"] == ui_data.MARK for a in got)


# ---- C2, C3, C5: one ask per clause, each with its kind, headline and elements ------------------------------

def _zoning(reason, needs=(), objects=(), item_id="R-3a.height"):
    return {"id": item_id, "status": present.REVIEW, "group": "building", "reason": reason, "needs": list(needs),
            "objects": list(objects), "causes": [{"kind": "decide", "key": "reason:x", "words": reason, "elements": []}]}


SITE = {"buildings": [{"id": "w1", "name": 'LS New 6"', "problems": ["a building isn't a closed solid: LS New 6\""]},
                      {"id": "w2", "name": 'LS New 6"', "problems": []},
                      {"id": "w3", "name": 'LS New 6"', "problems": ["a building isn't a closed solid: LS New 6\""]},
                      {"id": "r1", "name": "Roof", "problems": []}]}


def _ctx():
    from model_measurement.places import measuring
    place = measuring("regulations/jurisdictions/new_york/ithaca_city")
    return {"site": SITE, "place": place, "open_ids": ui_data._open_ids(SITE, place), "rule_kinds": {}}


def test_a_reason_of_two_asks_is_two_asks_each_its_kind():
    from model_measurement.stops import stop
    reason = stop("open_solid", what='LS New 6"') + "; " + stop("corner_unknown")
    got = ui_data.asks_of(_zoning(reason), _ctx())
    assert [a["kind"] for a in got] == [ui_data.FIX_MODEL, ui_data.MARK]
    assert got[0]["elements"] == ["w1", "w3"]           # C5: the open solids called so, not w2 (closed)
    assert got[0]["why"] == stop("open_solid", what='LS New 6"')
    assert got[1]["field"] == "facts.corner_lot" and got[1]["why"] == stop("corner_unknown")
    assert got[1]["headline"] == "Is the lot on two streets? (Corner lot, §325-19C)"


def test_a_survey_and_an_open_question_are_their_own_kinds():
    from model_measurement.stops import stop
    reason = stop("not_surveyed") + "; " + stop("all_street")
    got = ui_data.asks_of(_zoning(reason), _ctx())
    assert [a["kind"] for a in got] == [ui_data.SURVEY, ui_data.OPEN_QUESTION]


def test_a_clause_with_its_own_bracketed_semicolon_stays_whole():
    from model_measurement.stops import stop
    clause = stop("corner_unknown") + " (more if the §325-16C height bonus applies; the height isn't measured yet)"
    got = ui_data.asks_of(_zoning(stop("open_solid", what="Roof") + "; " + clause), _ctx())
    assert [a["kind"] for a in got] == [ui_data.FIX_MODEL, ui_data.MARK]
    assert got[1]["why"] == clause


def test_each_fact_a_row_waits_on_is_its_own_ask():
    from model_measurement.stops import stop
    reason = "enter the dwelling units, the rooms let for profit, and whether it is a conversion; " + \
        stop("not_surveyed")
    got = ui_data.asks_of(_zoning(reason, needs=["dwelling_units", "rooms_let_for_profit", "conversion"]), _ctx())
    assert [a.get("field") for a in got] == ["facts.dwelling_units", "facts.rooms_let_for_profit",
                                             "facts.conversion", None]
    assert got[-1]["kind"] == ui_data.SURVEY


def test_words_no_stop_gives_are_a_persons_to_decide_in_their_own_words():
    got = ui_data.asks_of(_zoning("A judgment call: a person decides (this rule is a flag)."), _ctx())
    assert [(a["kind"], a["headline"]) for a in got] == [(ui_data.DECIDE, ui_data.JUDGMENT)]
    got = ui_data.asks_of(_zoning("something no measuring says"), _ctx())
    assert got[0]["kind"] == ui_data.DECIDE and got[0]["why"] == "something no measuring says"


def test_a_row_not_in_review_has_no_asks():
    assert ui_data.asks_of({"status": present.COMPLIES, "group": "building"}, _ctx()) is None


@pytest.mark.parametrize("cause,kind,headline", [
    ({"kind": "mark", "key": "mark:space:space_occupant_load", "measure": "space_occupant_load",
      "words": "occupant load: stated by the architect (the space's occupant load), and Gordium has no mark for it "
               "in the model yet"}, ui_data.MEASURE,
     "Work out the occupant load by hand: Gordium has no field for it yet"),
    ({"kind": "measure_by_hand", "key": "gap:space:space_egress_through_locked_room",
      "words": "egress through locked room: Gordium doesn't measure this yet: measure it by hand"}, ui_data.MEASURE,
     "Check by hand: does the path pass through a room that can be locked?"),
    ({"kind": "decide", "key": "flag", "words": panel_data.FLAG_WORDS}, ui_data.DECIDE, ui_data.JUDGMENT),
    ({"kind": "decide", "key": "question:q3", "words": "under either reading"}, ui_data.OPEN_QUESTION,
     "An open question about the law decides this"),
    ({"kind": "fix_model", "key": "rooms:a,b", "words": "2 rooms have no route to an exit: A, B"},
     ui_data.FIX_MODEL, "2 rooms have no route to an exit"),
])
def test_each_cause_has_its_kind_and_a_short_headline_and_keeps_its_words(cause, kind, headline):
    got, = ui_data.asks_of({"status": present.REVIEW, "group": present.LAW_GROUP,
                            "causes": [{"elements": ["e"], **cause}]}, {"rule_kinds": {}})
    assert (got["kind"], got["headline"]) == (kind, headline)
    assert got["why"] == cause["words"] and got["elements"] == ["e"]


# ---- C4: plain names for measures ---------------------------------------------------------------------------

def test_a_measure_is_said_by_its_plain_name():
    w = lambda m, k=None: each_part._words({"for_each": k}, m)
    assert w("occupancy_group_i4") == "occupancy group (whether Group I-4)"
    assert w("sprinklered_903_3_1_1") == "sprinkler system (NFPA 13)"
    assert w("space_occupant_load", "space") == "occupant load"
    assert w("moe_door_latched", "means_of_egress_door") == "door latched"
    assert w("space_egress_through_locked_room", "space") == "egress through locked room"
    assert w("opening_net_clear_area", "emergency_escape_opening") == "net clear area"


def test_no_two_measures_a_rule_may_read_are_said_alike():
    building = list(code_scope.DERIVED)
    for kind, entry in parts.registry().items():
        names = list(entry["measures"]) + building
        said = [each_part._words({"for_each": kind}, m) for m in names]
        assert len(set(said)) == len(said), (kind, sorted(s for s in said if said.count(s) > 1))


# ---- C8, C9 -------------------------------------------------------------------------------------------------

def test_a_rule_name_leaves_the_law_and_section_to_in_code():
    item = {"rule": "general.bc_1006_2_1_two_exits", "group": present.LAW_GROUP, "code": {"section": "1006.2.1"}}
    rule = {"title": "Two exits over 10 occupants or a 75-ft common path, I-4 (BCNYS 1006.2.1)"}
    assert ui_data.rule_name(item, rule) == "Two exits over 10 occupants or a 75-ft common path, I-4"
    # a bracket that isn't its section stays
    assert ui_data.rule_name(item, {"title": "Exits (two or more)"}) == "Exits (two or more)"
    assert ui_data.rule_name({"rule": "R-3a.height", "group": "building", "name": "Building height"}, {}) == \
        "Building height"
    assert ui_data.rule_name({"rule": None, "group": "building", "name": "x"}, {}) is None


def test_a_limit_not_worked_out_says_what_it_depends_on():
    rule = {"check": "lot_area >= 3000 * dwelling_units"}
    item = {"required": "—", "measure": "lot_area"}
    assert ui_data.limit_words(item, rule, {"lot_area": 9000}) == "Limit depends on dwelling units"
    assert ui_data.limit_words(item, rule, {"lot_area": 9000, "dwelling_units": 4}) is None
    assert ui_data.limit_words({**item, "required": "12,000 sf"}, rule, {}) is None


# ---- the four-unit apartment's real Revit request, end to end ------------------------------------------------

@pytest.fixture(scope="module")
def apartment():
    from design_checker.__main__ import answer
    got = answer(json.loads(APARTMENT.read_text(encoding="utf-8")))
    assert got["ok"], got.get("error")
    return got["result"]


def test_every_row_in_review_has_its_asks_and_no_other_row_has_any(apartment):
    items = apartment["view"]["items"]
    assert any(i["status"] == present.REVIEW for i in items)
    for i in items:
        if i["status"] != present.REVIEW:
            assert "asks" not in i, i["id"]
            continue
        assert i["asks"], i["id"]
        for a in i["asks"]:
            assert a["kind"] in ui_data.KINDS and a["headline"] and len(a["headline"]) <= 100, (i["id"], a)
            assert isinstance(a["why"], str) and a["why"], (i["id"], a)


def test_the_apartments_occupancy_and_sprinkler_asks_name_their_project_fields(apartment):
    fields = [a.get("field") for i in apartment["view"]["items"] for a in i.get("asks") or []]
    assert fields.count("building.occupancy_groups") >= 20 and fields.count("building.sprinkler_system") >= 20
    assert not any(f and f.startswith(("facts.occupancy_group", "facts.sprinklered", "facts.other_occupancy"))
                   for f in fields)
    # today's cause field is as it was: the add-in on main reads what it read before
    old = [c.get("field") for i in apartment["view"]["items"] for c in i.get("causes") or []]
    assert "facts.occupancy_group_i4" in old


def test_the_open_walls_are_named_by_id(apartment):
    request = json.loads(APARTMENT.read_text(encoding="utf-8"))
    ids = {b["id"] for b in request["site"]["buildings"]}
    walls = [a for i in apartment["view"]["items"] for a in i.get("asks") or [] if a["key"].startswith("stop:open_solid")]
    assert walls and all(a["elements"] and set(a["elements"]) <= ids for a in walls)
    assert all(a["kind"] == ui_data.FIX_MODEL for a in walls)


def test_no_engineer_key_in_the_apartments_words(apartment):
    text = json.dumps([[i.get("reason"), i.get("detail", {}).get("line"), [c["words"] for c in i.get("causes") or []]]
                       for i in apartment["view"]["items"]], ensure_ascii=False)
    for key in ("occupancy group i4", "sprinklered 903", "space occupant load", "other occupancy present"):
        assert key not in text, key


def test_every_rule_row_has_its_place_in_its_document(apartment):
    rows = [i for i in apartment["view"]["items"] if i.get("rule")]
    assert rows and all("in_code" in i for i in rows), [i["id"] for i in rows if "in_code" not in i][:5]
    two = next(i for i in rows if i["rule"] == "general.bc_1006_2_1_two_exits")
    assert {k: two["in_code"][k] for k in ("chapter", "chapter_title", "section", "section_title", "piece")} == {
        "chapter": "10", "chapter_title": "MEANS OF EGRESS", "section": "1006",
        "section_title": "Number of Exits and Exit Access Doorways", "piece": "1006.2.1"}
    assert two["rule_name"] == "Two exits over 10 occupants or a 75-ft common path, I-4"
    use = next(i for i in rows if i["rule"] == "R-3a.use")
    assert (use["in_code"]["chapter"], use["in_code"]["chapter_title"], use["in_code"]["section"]) == \
        ("II", "Zoning Districts", "325-8")


def test_the_contents_list_every_chapter_and_never_hide_a_rows_section(apartment):
    books = {b["key"]: b for b in apartment["view"]["contents"]}
    assert list(books)[0] == "zoning"
    bc = books["new_york/new_york_state_building"]
    chapters = [c for c in bc["chapters"] if c["kind"] == "chapter"]
    assert [c["number"] for c in chapters] == [str(n) for n in range(1, 36)]
    egress = next(c for c in chapters if c["number"] == "10")
    assert egress["coverage"] == "rules" and egress["counts"]["not_brought_in"] >= 20
    sections = {s["number"]: s for s in egress["sections"]}
    assert sections["1006"]["coverage"] == "rules" and sections["1006"]["whole"] is False
    assert sections["1017"]["whole"] is True and sections["1010"]["coverage"] == "not_brought_in"
    # every row's section is in its book's contents, never as not brought in
    listed = {(b["key"], s["number"]): s for b in apartment["view"]["contents"] for c in b["chapters"]
              for s in c["sections"]}
    for i in apartment["view"]["items"]:
        if "in_code" in i:
            key = i.get("law_key") if i["group"] == present.LAW_GROUP else "zoning"
            got = listed.get((key, i["in_code"]["section"]))
            assert got is not None and got["coverage"] != "not_brought_in", (i["id"], i["in_code"])


def test_the_apartments_limits_not_worked_out_say_what_they_depend_on(apartment):
    by = {i["id"]: i for i in apartment["view"]["items"]}
    assert "dwelling units" in by["R-3a.lot_area_multiple_family"]["limit_words"]
    assert all(i.get("required") == "—" for i in by.values() if "limit_words" in i)


def test_a_pick_is_the_architects_to_state_and_a_tax_map_row_needs_a_survey():
    from model_measurement.stops import stop
    got, = ui_data.asks_of(_zoning(stop("no_main_building"), objects=["b1", "b2"]), _ctx())
    assert (got["kind"], got["headline"], got["elements"]) == (ui_data.MARK, "Pick the main building", ["b1", "b2"])
    item = _zoning("Lot lines are from the tax map (±2'-0\"): at worst 35'-0\" against 35'-0\" · Pick survey lot lines…",
                   objects=["lot"])
    item["causes"] = present.zoning_causes(item)
    got, = ui_data.asks_of(item, _ctx())
    assert (got["kind"], got["elements"]) == (ui_data.SURVEY, ["lot"])


def test_a_headline_from_the_measurings_words_leaves_its_figures_to_the_why():
    from model_measurement.stops import stop
    clause = stop("ground_off_building", ground="0.0", bottom="2.25", top="40.25")
    got, = ui_data.asks_of(_zoning(clause), _ctx())
    assert got["headline"] == "The ground level doesn't meet the buildings" and got["why"] == clause
