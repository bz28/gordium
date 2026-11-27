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
                                          "egress_balcony_increase_taken": False, "building_has_atrium": False,
                                          "assembly_fixed_seating": False, "special_egress_spaces": False,
                                          "merchandise_pads": False, "r2_sleeping_units": False,
                                          "emergency_escape_openings_1031": False,           # group 2's two
                                          "occupied_outdoor_areas": False,                   # group 3's
                                          "ambulatory_care_facility": False,                 # group 4's
                                          "corridors_within_dwelling_units": False,
                                          "emergency_voice_alarm_system": False})            # group 5a's
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
    """A zoning row in review whose reason is `reason` (a Said, as present makes it), its parts as data (`stops`)
    and its cause as present.zoning_causes gives it."""
    item = {"id": item_id, "status": present.REVIEW, "group": "building", "reason": reason, "needs": list(needs),
            "objects": list(objects), "stops": present.reason_parts(reason)}
    item["causes"] = present.zoning_causes(item)
    return item


SITE = {"buildings": [{"id": "w1", "name": 'LS New 6"', "problems": ["a building isn't a closed solid: LS New 6\""]},
                      {"id": "w2", "name": 'LS New 6"', "problems": []},
                      {"id": "w3", "name": 'LS New 6"', "problems": ["a building isn't a closed solid: LS New 6\""]},
                      {"id": "r1", "name": "Roof", "problems": []}]}


def _ctx():
    from model_measurement.places import measuring
    place = measuring("regulations/jurisdictions/new_york/ithaca_city")
    return {"site": SITE, "place": place, "open_ids": ui_data._open_ids(SITE, place), "rule_kinds": {}}


def test_a_reason_of_two_stops_is_two_asks_each_its_kind():
    from model_measurement.stops import joined, stop
    reason = joined([stop("open_solid", what='LS New 6"'), stop("corner_unknown")])
    got = ui_data.asks_of(_zoning(reason, objects=["w1", "w2", "w3", "r1"]), _ctx())
    assert [a["kind"] for a in got] == [ui_data.FIX_MODEL, ui_data.MARK]
    assert got[0]["elements"] == ["w1", "w3"]           # C5: the open solids called so, not w2 (closed)
    assert got[0]["why"] == stop("open_solid", what='LS New 6"')
    assert got[1]["field"] == "facts.corner_lot" and got[1]["why"] == stop("corner_unknown")
    assert got[1]["headline"] == "Is the lot on two streets? (Corner lot, §325-19C)"
    assert got[1]["elements"] == ["w1", "w2", "w3", "r1"]   # every ask carries the row's objects by default


def test_a_survey_and_an_open_question_are_their_own_kinds():
    from model_measurement.stops import joined, stop
    got = ui_data.asks_of(_zoning(joined([stop("not_surveyed"), stop("all_street")])), _ctx())
    assert [a["kind"] for a in got] == [ui_data.SURVEY, ui_data.OPEN_QUESTION]


def test_a_stop_rewritten_for_the_reader_keeps_its_code():
    # present's _user_text rewrites "an open question for the architects" (review round 1: the words no longer
    # matched any stop): the part keeps its code, its words are the rewritten ones
    from model_measurement.stops import joined, stop
    reason = present._user_text(joined([stop("not_surveyed"), stop("all_street")]))
    assert "open question for the architects" not in reason
    got = ui_data.asks_of(_zoning(reason), _ctx())
    assert [a["kind"] for a in got] == [ui_data.SURVEY, ui_data.OPEN_QUESTION]
    assert [a["why"] for a in got] == [p["words"] for p in present.reason_parts(reason)]


def test_a_stop_with_a_semicolon_of_its_own_is_one_ask():
    from model_measurement.stops import joined, stop
    readings = stop("readings_differ", question="which front yard is the primary one; how a corner lot is read")
    got = ui_data.asks_of(_zoning(joined([readings, stop("corner_unknown")])), _ctx())
    assert [(a["kind"], a["why"]) for a in got] == [(ui_data.OPEN_QUESTION, readings),
                                                   (ui_data.MARK, stop("corner_unknown"))]


def test_each_open_question_a_row_depends_on_is_one_ask_with_the_whole_question():
    from model_measurement.stops import reason_part
    reason = reason_part("depends", "Complies under every reading, but it depends on open questions: a; b, with c; confirm "
                  "with the zoning office", questions=["a", "b, with c"])
    got = ui_data.asks_of(_zoning(reason), _ctx())
    assert [(a["kind"], a["why"]) for a in got] == [(ui_data.OPEN_QUESTION, "a"), (ui_data.OPEN_QUESTION, "b, with c")]


def test_a_scope_reason_is_one_fix_of_the_model_with_the_rows_objects():
    from model_measurement.stops import reason_part
    reason = reason_part("scope", "Complies for the buildings measured; 2 objects touching the building aren't measured "
                  "(a porch or deck is part of the building, §325-18A) · Add to check…")
    got = ui_data.asks_of(_zoning(reason, objects=["o1", "o2"]), _ctx())
    assert [(a["kind"], a["elements"]) for a in got] == [(ui_data.FIX_MODEL, ["o1", "o2"])]


def test_each_fact_a_row_waits_on_is_its_own_ask():
    from model_measurement.stops import joined, stop
    reason = joined([stop("no_units"), stop("not_surveyed")])
    got = ui_data.asks_of(_zoning(reason, needs=["dwelling_units", "rooms_let_for_profit", "conversion"]), _ctx())
    assert [a.get("field") for a in got] == ["facts.dwelling_units", "facts.rooms_let_for_profit",
                                             "facts.conversion", None]
    assert got[0]["why"] == stop("no_units") and got[-1]["kind"] == ui_data.SURVEY


def test_a_rows_own_reason_is_by_its_code():
    from model_measurement.stops import reason_part
    got = ui_data.asks_of(_zoning(reason_part("flag", "A judgment call: a person decides (this rule is a flag).")), _ctx())
    assert [(a["kind"], a["headline"]) for a in got] == [(ui_data.DECIDE, ui_data.JUDGMENT)]
    got = ui_data.asks_of(_zoning("something no part was kept for"), _ctx())
    assert got[0]["kind"] == ui_data.DECIDE and got[0]["why"] == "something no part was kept for"


def test_a_row_not_in_review_has_no_asks():
    assert ui_data.asks_of({"status": present.COMPLIES, "group": "building"}, _ctx()) is None


@pytest.mark.parametrize("cause,kind,headline", [
    ({"kind": "mark", "key": "mark:space:space_occupant_load", "measure": "space_occupant_load",
      "words": "occupant load: stated by the architect (the space's occupant load), and Gordium has no mark for it "
               "in the model yet"}, ui_data.MEASURE,
     "Work out the occupant load by hand (a person's check)"),
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
    # every building measure, not a fixed few, so the next one added can't slip through (PR #181 review round 8)
    from design_checker import each_part
    keys = {*code_scope.DERIVED, "space_occupant_load", "space_is_exit"}
    for key in sorted(keys):
        said = key.replace("_", " ")
        if each_part.MEASURE_NAMES.get(key, "").startswith(said):
            continue                         # its plain name begins with the same words ("merchandise pads (...)")
        assert said not in text, key
    assert "sprinklered 903" not in text


def test_every_building_measure_has_a_plain_name_and_every_asked_fact_a_headline():
    # PR #181 review round 8: a measure added to DERIVED without a name read "sprinklered 903 3 1 3" to the architect
    from design_checker import each_part
    assert set(code_scope.DERIVED) <= set(each_part.MEASURE_NAMES), set(code_scope.DERIVED) - set(each_part.MEASURE_NAMES)
    names = [each_part.MEASURE_NAMES[m] for m in code_scope.DERIVED]
    assert all("_" not in n for n in names)
    for field in {code_scope.field_of(m) for m in code_scope.DERIVED}:
        assert field in ui_data.FIELD_HEADLINES, field


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
    assert egress["coverage"] == "rules" and egress["counts"]["not_brought_in"] == 8   # section group 7c: 1011 (in parts); 9a: 1003 and 1012 brought in (20 before); 9b: 1008 and 1013; 9c: 1009; 9d: 1019 (1018 left the count with 1018.4, round 1 of 2026-11-23); 9e: 1021, 1022 and 1023; 9f: 1024 and 1025
    sections = {s["number"]: s for s in egress["sections"]}
    assert sections["1018"]["whole"] is True and sections["1019"]["whole"] is True   # group 9d review round 1
    assert all(sections[s]["whole"] is True for s in ("1021", "1022", "1023", "1024", "1025"))   # groups 9e and 9f
    assert sections["1006"]["coverage"] == "rules" and sections["1006"]["whole"] is False
    assert sections["1017"]["whole"] is True and sections["1014"]["coverage"] == "not_brought_in"   # handrails (1011: 7c's; 1012: 9a's)
    assert sections["1011"]["coverage"] == "rules" and sections["1011"]["whole"] is False          # group 7c's stairs
    assert sections["1010"]["coverage"] == "rules" and sections["1010"]["whole"] is False   # group 6a: 1010.1, 1010.1.1
    # every row's section is in its book's contents, never as not brought in
    listed = {(b["key"], s["number"]): s for b in apartment["view"]["contents"] for c in b["chapters"]
              for s in c["sections"]}
    for i in apartment["view"]["items"]:
        if "in_code" in i:
            key = i.get("law_key") if i["group"] == present.LAW_GROUP else "zoning"
            got = listed.get((key, i["in_code"]["section"]))
            assert got is not None and got["coverage"] in ("rules", "flag"), (i["id"], i["in_code"], got)


def test_the_apartments_limits_not_worked_out_say_what_they_depend_on(apartment):
    by = {i["id"]: i for i in apartment["view"]["items"]}
    assert "dwelling units" in by["R-3a.lot_area_multiple_family"]["limit_words"]
    assert all(i.get("required") == "—" for i in by.values() if "limit_words" in i)


def test_a_pick_is_the_architects_to_state_and_a_tax_map_row_needs_a_survey():
    from model_measurement.stops import stop
    got, = ui_data.asks_of(_zoning(stop("no_main_building"), objects=["b1", "b2"]), _ctx())
    assert (got["kind"], got["headline"], got["elements"]) == (ui_data.MARK, "Pick the main building", ["b1", "b2"])
    from model_measurement.stops import reason_part
    item = _zoning(reason_part("tax_map", "Lot lines are from the tax map (±2'-0\"): at worst 35'-0\" against 35'-0\" · Pick "
                        "survey lot lines…"), objects=["lot"])
    got, = ui_data.asks_of(item, _ctx())
    assert (got["kind"], got["elements"]) == (ui_data.SURVEY, ["lot"])


def test_a_headline_from_the_measurings_words_leaves_its_figures_to_the_why():
    from model_measurement.stops import stop
    clause = stop("ground_off_building", ground="0.0", bottom="2.25", top="40.25")
    got, = ui_data.asks_of(_zoning(clause), _ctx())
    assert got["headline"] == "The ground level doesn't meet the buildings" and got["why"] == clause


# ---- the class pin: over every golden answer and the apartment's ---------------------------------------------

def _expected(part: dict, ctx: dict) -> list[tuple]:
    """(kind, field or None, why) each part of a row's reason must have an ask for, by its code."""
    code, words = part["code"], part["words"]
    if code in ui_data.NO_ASK_PARTS:            # it says when to answer; the parts after it ask
        return []
    if code in ui_data.SURVEY_STOPS or code == "tax_map":
        return [(ui_data.SURVEY, None, words)]
    if code in ui_data.OPEN_STOPS or code == "readings":
        return [(ui_data.OPEN_QUESTION, None, words)]
    if code == "depends" and (part.get("params") or {}).get("questions"):
        return [(ui_data.OPEN_QUESTION, None, q) for q in part["params"]["questions"]]
    facts = ui_data._stop_facts(code, ctx)
    if facts:
        return [(ui_data.MARK, f"facts.{f}", None) for f in facts]
    if code in ("open_solid", "scope"):
        return [(ui_data.FIX_MODEL, None, words)]
    return [(None, None, words)]


def class_problems(view: dict, ctx: dict) -> list[str]:
    """What breaks the class of rules the asks keep (review round 1): every row in review has asks; each part of its
    reason has an ask of the kind its code calls for; no ask's why is a piece of words (only a whole part's words, a
    whole question, the whole reason or a cause's words); every element its cause names is in some ask."""
    out = []
    for i in view.get("items") or []:
        if i.get("status") != present.REVIEW:
            continue
        asks = i.get("asks") or []
        if not asks:
            out.append(f"{i['id']}: no asks")
            continue
        parts = i.get("stops") or []
        whole = {p["words"] for p in parts} | {str(q) for p in parts for q in (p.get("params") or {}).get("questions")
                                               or []} | {str(i.get("reason") or "")} | \
            {c.get("words") for c in i.get("causes") or []}
        out += [f"{i['id']}: a why that is a piece of words: {a['why'][:80]!r}" for a in asks if a["why"] not in whole]
        for p in parts:
            for kind, field, why in _expected(p, ctx):
                if not any((kind is None or a["kind"] == kind) and (field is None or a.get("field") == field)
                           and (why is None or a["why"] == why) for a in asks):
                    out.append(f"{i['id']}: {p['code']} has no {kind or 'ask'} ask ({field or why!r:.80})")
        picks = [a["key"] for a in asks if a["key"].startswith("pick:") or
                 (a["key"].startswith("stop:") and a["key"].split(":")[1] in ui_data._pick_keys())]
        out += [f"{i['id']}: a pick asked twice or under its stop: {picks}" for _ in [0]
                if len(picks) != len(set(picks)) or any(k.startswith("stop:") for k in picks)]
        out += [f"{i['id']}: a field no host description has: {a['field']}" for a in asks
                if a["kind"] == ui_data.MARK and a.get("field") and a["field"] not in _known_fields()]
        specific = [p["code"] for p in parts if p["code"] not in ("words", "review", "unsettled", "use_detail")]
        scope_facts = (i.get("code_scope") or {}).get("ask_facts") if isinstance(i.get("code_scope"), dict) else None
        if all(a["headline"] == "A person decides this: see why" for a in asks) and (specific or scope_facts):
            out.append(f"{i['id']}: only the generic ask, though it says {specific or scope_facts}")
        seen = [(a["kind"], a["headline"]) for a in asks]
        out += [f"{i['id']}: two asks alike: {k}" for k in dict.fromkeys(seen) if seen.count(k) > 1]
        if parts and "".join(p.get("sep", "") + p["words"] for p in parts) != str(i.get("reason") or ""):
            out.append(f"{i['id']}: its stops aren't its reason")
        out += [f"{i['id']}: a stop's words kept without its code: {p['words'][:80]!r}" for p in parts
                if p["code"] == "words" and _a_stops_words(p["words"])]
        asked = {e for a in asks for e in a.get("elements") or []}
        out += [f"{i['id']}: {e} of its cause is in no ask" for c in i.get("causes") or []
                for e in c.get("elements") or [] if e not in asked]
    return out


_FIELDS = []


def _known_fields() -> set:
    """Every field a host's description has, read from where it is defined, never copied: the Revit add-in's own
    fields (every "building.…", "facts.…" and "kind[].flag" its C# names, and every whole list a mark's Feeds names
    as the pane matches it: stairs, guards, buildings, unknown_spaces), the stated facts the start box and the rows'
    Enter… ask for (host_core.facts.STATED_FACTS), the building block's facts (code_scope.FACTS) and the site's own
    questions (ui_data.SITE_STOPS)."""
    if not _FIELDS:
        import re
        from design_checker.host_core.facts import STATED_FACTS
        found = set()
        for cs in (REPO / "apps/revit_addin/src").rglob("*.cs"):
            if "obj" not in cs.parts:
                found |= set(re.findall(r'"((?:building|facts)\.[a-z0-9_]+|[a-z]+\[\]\.[a-z0-9_]+)"',
                                        cs.read_text(encoding="utf-8")))
                # a whole list a mark feeds, the first word of a part of its Feeds as CauseCards.Fields reads it
                # ("stairs (sent only when Yes)": stairs, Gordium: These are all the stairs)
                for feeds in re.findall(r'MarkBinding\.\w+,\s*\[[^\]]*\],\s*"([^"]+)"', cs.read_text(encoding="utf-8")):
                    found |= {w for w in (p.split(" ")[0] for p in feeds.split(", ")) if re.fullmatch(r"[a-z_]+", w)}
        found |= {f"facts.{k}" for k in STATED_FACTS} | {f"building.{k}" for k in code_scope.FACTS}
        found |= {f"facts.{f}" for facts in ui_data.SITE_STOPS.values() for f in facts}
        _FIELDS.append(found)
    return _FIELDS[0]


def _a_stops_words(words: str) -> bool:
    """Whether words are exactly a measuring stop's (its template, each blank any text): a stop whose code was lost."""
    from model_measurement.stops import PATTERNS
    return any(rx.match(words) for rx in PATTERNS.values())


def _views(answer):
    if isinstance(answer, dict):
        if isinstance(answer.get("items"), list) and any(isinstance(x, dict) and "status" in x
                                                         for x in answer["items"]):
            yield answer
        for v in answer.values():
            yield from _views(v)
    elif isinstance(answer, list):
        for v in answer:
            yield from _views(v)


def test_every_golden_answers_asks_keep_the_class_rules():
    from design_checker import goldens
    _, answers = goldens.stored()
    ctx = _ctx()
    found, problems = 0, []
    for name, answer in answers.items():
        for view in _views(answer):
            found += 1
            problems += [f"{name}: {p}" for p in class_problems(view, ctx)]
    assert found >= 200 and not problems, (len(problems), problems[:10])


def test_the_apartments_asks_keep_the_class_rules(apartment):
    assert not class_problems(apartment["view"], _ctx())


@pytest.mark.parametrize("folder", ["ithaca_city", "new_york_state", "new_york_state_building"])
def test_every_brought_in_piece_lands_in_a_section_of_its_contents(folder):
    from design_checker import contents
    from rule_format.labels import load_pieces
    root = REPO / "regulations/jurisdictions/new_york" / folder
    book, = contents._folder_books(root, folder, {})
    listed = {r["number"] for r in book["rows"] if r.get("kind") == "section"}
    _, pieces = load_pieces(next((root / "2_extracted_text").glob("*.sections.jsonl")))
    lost = [pid for pid, piece in pieces.items() if piece.get("kind") not in ("front_matter", "editors_note")
            and contents.section_of_piece(pid) not in listed]
    assert not lost, lost[:10]
    # the RCNYS's appendices: their pieces are in their own sections (BF101, BO103), never dropped
    if folder == "new_york_state":
        assert contents.section_of_piece("BF101.2") == "BF101" and "BF101" in listed


def test_which_code_governs_asks_for_the_fact_its_ask_names():
    from design_checker import goldens
    _, answers = goldens.stored()
    view = answers["deep_run/r2_316_e_falls_st/check_as_drawn"]["view"]
    row = next(i for i in view["items"] if i["id"].endswith(".code_scope") and i["status"] == present.REVIEW)
    assert row["code_scope"]["ask_facts"] == ["separate_means_of_egress"]
    assert [(a["kind"], a.get("field")) for a in row["asks"]] == [(ui_data.MARK, "building.separate_means_of_egress")]


def test_a_by_hand_code_choice_stays_a_persons_to_decide():
    got = code_scope.decide({"use": "one_family_detached", "care_facility": True}, None)
    assert got["code"] is None and got["ask_facts"] == []


def test_a_looked_up_fact_asks_to_confirm_or_change_it():
    from model_measurement.stops import reason_part
    reason = reason_part("looked_up", "Complies on the looked-up lot area, which needs review: x · confirm it",
                         fact="lot_area", name="lot area")
    got, = ui_data.asks_of(_zoning(reason), _ctx())
    assert (got["kind"], got.get("field"), got["headline"]) == (ui_data.MARK, None,
                                                              "Confirm or change the looked-up lot area")
    # (no field: the looked-up lot, street or ground is changed in the site's own setup, no one fact; review round 3)


def test_the_pick_a_hint_and_a_stop_ask_for_is_one_ask():
    from model_measurement.stops import stop
    item = _zoning(stop("no_main_building"), objects=["b1"])
    item["hint"] = present.PICK_MAIN
    got = ui_data.asks_of(item, _ctx())
    assert [a["headline"] for a in got] == ["Pick the main building"]


def test_a_use_detail_rows_parts_are_still_its_reason():
    from model_measurement.stops import stop
    from design_checker.host_core.facts import USE_DETAILS_WHEN
    parts = [{"code": "use_detail", "params": {}, "words": USE_DETAILS_WHEN},
             {"code": "no_home_occupation", "params": {}, "words": stop("no_home_occupation"), "sep": ": "}]
    item = {"id": "x", "status": present.REVIEW, "group": "building", "needs": ["home_occupation"], "objects": [],
            "reason": f"{USE_DETAILS_WHEN}: {stop('no_home_occupation')}", "stops": parts, "causes": []}
    assert not class_problems({"items": [dict(item, asks=ui_data.asks_of(item, _ctx()))]}, _ctx())


def _code_choices():
    """decide() over a spread of facts: every use, with each building fact stated, unstated, wrong or set aside."""
    from itertools import product
    uses = ["one_family_detached", "two_family", "one_family_semi_detached", "one_family_attached",
            "multiple_family_dwelling", None, "not_a_use"]
    for use, egress, town, stories, units in product(uses, (None, True, False), (None, True, False),
                                                     (None, 2, 4, "x"), (None, 1, 2, "three")):
        building = {k: v for k, v in (("separate_means_of_egress", egress), ("townhouse_units", town),
                                      ("stories_above_grade_plane", stories)) if v is not None}
        yield code_scope.decide({"use": use, "dwelling_units": units}, building)


def test_a_code_choices_ask_facts_are_the_marks_its_ask_names():
    import re
    undecided = [got for got in _code_choices() if got["code"] is None]
    assert len(undecided) > 100
    for got in undecided:
        named = {k for k, m in code_scope.MARK.items() if re.search(re.escape(m) + r"(?![A-Za-z])", got["ask"] or "")}
        named -= {k for k in named for j in named if j != k and code_scope.MARK[k] in code_scope.MARK[j]}
        expected = set() if got["ask"] == code_scope.BY_HAND else named
        assert set(got["ask_facts"]) == expected, (got["ask"], got["ask_facts"])
    one = code_scope.decide({"use": "one_family_detached"}, {"separate_means_of_egress": False})
    assert one["ask_facts"] == ["separate_means_of_egress"]       # a house: never its townhouse units


def test_a_code_choice_on_facts_it_cant_read_asks_for_those_facts():
    got = code_scope.decide({"use": "one_family_detached"}, {"stories_above_grade_plane": 0})
    assert got["code"] is None and got["ask_facts"] == ["stories_above_grade_plane"]
    got = code_scope.decide({"use": "one_family_detached", "dwelling_units": "x"}, None)
    assert got["ask_facts"] == ["dwelling_units"]


def test_an_adu_pick_is_one_ask_under_the_hints_headline():
    from model_measurement.stops import stop
    for code in ("adu_not_found", "adu_is_main", "no_adu_building"):
        item = _zoning(stop(code), objects=["b1"])
        item["hint"] = present.PICK_ADU
        got = ui_data.asks_of(item, _ctx())
        assert [(a["key"], a["headline"]) for a in got] == [("pick:adu_building", present.PICK_ADU.rstrip("…"))], code


def _revit_marks() -> dict:
    """{fact key: its mark's label} from the Revit add-in's own Marks.cs: each MarkDefinition's label and the
    `building.`/`facts.` fields it feeds."""
    import re
    text = (REPO / "apps/revit_addin/src/Gordium.Revit.Reading/Marks.cs").read_text(encoding="utf-8")
    out = {}
    for label, feeds in re.findall(r'new\(\s*"(Gordium: [^"]+)"[^;]*?\]\s*,\s*"([^"]+)"', text):
        for key in re.findall(r"(?:building|facts)\.([a-z0-9_]+)", feeds):
            out.setdefault(key, label)
    return out


def test_every_fact_the_code_choice_reads_has_the_mark_revit_shows_for_it():
    revit = _revit_marks()
    assert revit.get("stories") == "Gordium: Stories" and revit.get("use") == "Gordium: Use"
    keys = (set(code_scope.READS) | set(code_scope.FACTS)) - {"facts_not_sent"}
    for k in sorted(keys):
        if k in revit:
            assert code_scope.MARK.get(k) == revit[k], (k, code_scope.MARK.get(k), revit[k])
        else:                        # no host has a mark for it: never one invented here
            assert k not in code_scope.MARK, k
    # every fact the code choice and the Building Code's rules read has its Revit mark (the BCNYS's balcony, atrium,
    # fixed seating, special egress spaces and merchandise pads were the last without one, PR feat/revit-fields-ch10)
    # group 4's two Building Code facts have no Revit mark yet (Table 1020.3's ambulatory care facility; whether
    # another level's occupants reach a corridor): asked for by name, never by a mark; their marks follow in the
    # Revit-fields work. Groups 2 and 3's facts have theirs (PR #194).
    # and this branch's own: corridors_within_dwelling_units (their marks follow in the Revit-fields work)
    # and this branch's own: emergency_voice_alarm_system (their marks follow in the Revit-fields work)
    # (groups 4 and 5's four have theirs too, the Revit-fields PR for them: the set is empty)
    # (the occupant-load ceiling's mezzanines and loads not by area, 2026-11-26, came with their own)
    assert keys - set(revit) == set()
    assert code_scope.MARK["mezzanines"] == revit["mezzanines"] == "Gordium: Mezzanines"
    assert code_scope.MARK["loads_not_by_area"] == revit["loads_not_by_area"] == "Gordium: Loads not by area"
    for k in ("r2_sleeping_units", "emergency_escape_openings_1031", "occupied_outdoor_areas", "occupant_load_increased",
              "other_level_egress_into_corridors", "ambulatory_care_facility", "corridors_within_dwelling_units",
              "emergency_voice_alarm_system"):
        # a fact a rule reads as a measure is answered by its field (field_of); occupant_load_increased is read by the
        # occupant loads themselves, not as a measure
        assert code_scope.field_of(k) == (f"building.{k}" if k in code_scope.DERIVED else None), k
        assert code_scope.MARK[k] == revit[k], k
    for k in ("egress_balcony_increase_taken", "building_has_atrium", "assembly_fixed_seating", "special_egress_spaces",
              "merchandise_pads"):
        assert code_scope.field_of(k) == f"building.{k}" and code_scope.MARK[k] == revit[k], k


@pytest.mark.parametrize("key", code_scope.READS)
@pytest.mark.parametrize("how", ["not_sent", "set_aside", "unreadable_in_values", "unreadable_in_building"])
def test_a_fact_the_code_choice_cant_use_is_asked_for_by_its_mark(key, how):
    values, building = {"use": "one_family_detached"}, {}
    bad = "not a value" if key not in ("use",) else 12
    if how == "not_sent":
        building["facts_not_sent"] = [key]
    elif how == "set_aside":
        values[code_scope.SET_ASIDE] = {key: "stated twice, the two disagree"}
    elif how == "unreadable_in_values":
        values[key] = bad
    else:
        if key not in code_scope.FACTS:
            pytest.skip(f"{key} is no building fact: a building block can't send it")
        building[key] = bad
    got = code_scope.decide(values, building)
    assert got["code"] is None and got["ask"] != code_scope.BY_HAND, got
    assert key in got["ask_facts"], (got["ask"], got["ask_facts"])


def test_every_plain_measure_name_reads_inside_each_asks_headline():
    # PR #181 review round 9: a name that was a "whether" clause read "Fix the model so the whether the space is
    # itself an exit can be measured"; each name is a noun phrase, so every headline template reads
    from design_checker import each_part
    # story_first_above_or_below_grade's name is main's, read by the Revit add-in's saved answer: a to-do (PR #181)
    for measure, name in each_part.MEASURE_NAMES.items():
        if measure == "story_first_above_or_below_grade":
            continue
        assert not name.lower().startswith(("whether", "if ", "is ", "the ")), (measure, name)
    got = ui_data._from_cause({"kind": "fix_model", "key": "model:space:space_is_exit:x", "words": "w",
                               "measure": "space_is_exit"}, "space")["headline"]
    assert got == "Fix the model so the exit status (whether the space is itself an exit) can be measured"


def test_every_story_fact_a_story_exit_rule_reads_and_nothing_measures_is_a_question_in_words():
    """Group 2's review round 4 (P3, 2026-11-24): the story facts Tables 1006.3.4(1) and (2) read and no measuring
    gives (the story's place, its dwelling units) each ask a plain question, as the first story's does; their names
    read as whole clauses."""
    from design_checker import each_part
    for m in ("story_first_above_or_below_grade", "story_second_above_grade_plane",
              "story_fourth_or_higher_above_grade_plane", "story_dwelling_units"):
        cause = {"kind": "measure_by_hand", "key": f"gap:story:{m}", "measure": m, "words": f"{m}: not measured",
                 "elements": []}
        head = ui_data._from_cause(cause, "story")["headline"]
        assert head.startswith("Check by hand:") and head.endswith("?") and "_" not in head, (m, head)
    for m in ("story_second_above_grade_plane", "story_fourth_or_higher_above_grade_plane"):
        assert "story above grade plane" in each_part.MEASURE_NAMES[m] and "(whether it is the" in each_part.MEASURE_NAMES[m]


def test_the_voice_alarm_ask_is_the_whole_buildings():
    # groups 4 and 5's Revit fields, review round 1: the lower capacity factors are for buildings equipped throughout
    assert "whole building" in ui_data.FIELD_HEADLINES["building.emergency_voice_alarm_system"]


def test_the_r2_sleeping_units_ask_never_reads_as_either_or_for_a_mixed_building():
    # group 2 facts' review rounds 1 and 2: one building-wide fact, so a building with both kinds leaves it blank (both
    # tables' rows need review); the words the architect reads say so, never "sleeping units (not dwelling units)"
    from design_checker import each_part
    assert "all sleeping units, all dwelling units, or both" in ui_data.FIELD_HEADLINES["building.r2_sleeping_units"]
    assert "every Group R-2 unit is a sleeping unit" in each_part.MEASURE_NAMES["r2_sleeping_units"]


def test_the_plan_never_says_a_marked_facts_revit_mark_is_still_to_come():
    # PR #195 review round 7: after PR #194 the plan still said groups 2 and 3's marks were a follow-up
    import re
    doc = (REPO / "docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md").read_text(encoding="utf-8")
    for sentence in re.split(r"(?<=[.;])\s", doc):
        if re.search(r"Revit mark\S* (is|are) a follow-up|marks? join group", sentence):
            named = [k for k in code_scope.MARK if k in sentence]
            assert not named, (named, sentence[:200])


def test_the_corridor_rating_card_names_the_unit_its_revit_mark_takes():
    # corridor asks review round 1 (P2): the card said "in hours" while the Revit mark it opens takes minutes, so an
    # architect typing 1 for one hour sent 1/60 hour; the card and the mark both say minutes
    import re
    text = (REPO / "apps/revit_addin/src/Gordium.Revit.Reading/Marks.cs").read_text(encoding="utf-8")
    m = re.search(r'new\(\s*"(Gordium: [^"]+)", new\("[^"]+"\), MarkValueKind\.(\w+),\s*MarkBinding\.\w+, \[Rooms\], '
                  r'"rooms\[\]\.fire_rating_hours"', text)
    assert m and m.group(2) == "Integer" and "minutes" in m.group(1), m
    headline = ui_data.FIELD_HEADLINES["rooms[].fire_rating_hours"]
    assert "minutes" in headline and "in hours" not in headline


def test_a_door_whose_leaves_arent_given_is_asked_for_by_the_field_its_type_mark_answers():
    # the door-type mark (Revit's Gordium: Leaves, doors[].leaves): before it, "Mark the door leaves in the model", a
    # mark Revit didn't have; now the ask names the field, so the host's card opens its mark
    from model_measurement.routes.stops import STOPS
    why = "door leaves: " + STOPS["door_leaves_not_given"].format(name="D01")
    got = ui_data._from_cause({"kind": "mark", "key": "mark:means_of_egress_door:moe_door_leaves", "words": why,
                               "measure": "moe_door_leaves"}, "means_of_egress_door")
    assert (got["kind"], got["field"], got["key"]) == ("mark", "doors[].leaves", "field:doors[].leaves")
    assert got["headline"] == "Set each door type's leaves (a pair with a mullion: 1 only at the narrower leaf's clear width)"
    assert "no mark for it" not in STOPS["door_leaves_not_given"]


# ---- follow-up questions name the question they hang on (egress UI audit finding 8, 2026-11-26) -----------------

def test_every_follow_up_names_its_parent_and_the_walk_up_ends():
    """Each fact the setup asks only once another is answered (host_core.facts.ROW_ONLY_FACTS) names that one as its
    depends_on; every parent and child is a fact the setup knows; walking up from any follow-up ends (no cycle); and
    every follow-up of a yes/no question says which answer makes it moot (MOOT_WHEN), only follow-ups have one."""
    from design_checker.host_core.facts import ROW_ONLY_FACTS, STATED_FACTS
    assert set(ui_data.MOOT_WHEN) <= set(ROW_ONLY_FACTS)
    for child, parent in ROW_ONLY_FACTS.items():
        assert child in STATED_FACTS and parent in STATED_FACTS, (child, parent)
        got = ui_data.depends_on(f"facts.{child}")
        assert got["field"] == f"facts.{parent}", child
        if STATED_FACTS[parent][1] == "yes_no":
            assert child in ui_data.MOOT_WHEN and got["moot_if"] == ui_data.MOOT_WHEN[child], child
        else:
            assert "moot_if" not in got, child
        seen, at = {child}, parent
        while at in ROW_ONLY_FACTS:
            assert at not in seen, (child, at)
            seen.add(at)
            at = ROW_ONLY_FACTS[at]
    for field in ("facts.accessory_dwelling_unit", "facts.corner_lot", "building.occupancy_groups", None, 3):
        assert ui_data.depends_on(field) is None, field


def test_a_moot_answer_makes_every_rule_reading_the_follow_up_not_apply():
    """MOOT_WHEN is the law's, never a guess: for every Ithaca zoning rule that reads a follow-up fact (in its check,
    applies_when or review_when), the parent's moot answer makes the rule's applies_when false whatever else is
    unknown (three-valued: false and unknown is false). An ADU's size limit (§325-28) reads the attached ADU's floor
    area, so it is moot once the ADU is detached, not once it isn't."""
    import glob
    from rule_format import formula
    from rule_format.rulebook import Context, _kinds, load
    from design_checker.host_core.facts import ROW_ONLY_FACTS
    place = REPO / "regulations/jurisdictions/new_york/ithaca_city"
    kinds = _kinds(Context.for_jurisdiction(place).allowed())
    read = {}
    for f in glob.glob(str(place / "5_zoning_rules" / "*.yaml")):
        for r in load(f).get("rules") or []:
            texts = [r.get("check"), r.get("applies_when")] + [w.get("when") for w in r.get("review_when") or []]
            names = set().union(*(formula.names(t) for t in texts if isinstance(t, str)))
            for child in ui_data.MOOT_WHEN:
                if child in names:
                    read.setdefault(child, []).append(r)
    assert set(read) == set(ui_data.MOOT_WHEN), set(ui_data.MOOT_WHEN) ^ set(read)
    for child, rules in read.items():
        parent = ROW_ONLY_FACTS[child]
        for answer in ui_data.MOOT_WHEN[child]:
            for r in rules:
                assert isinstance(r.get("applies_when"), str), (child, r["id"])
                got = formula.evaluate(r["applies_when"], {parent: answer}, kinds)
                assert got is False, (child, answer, r["id"], r["applies_when"])


def test_the_trial_requests_adu_follow_ups_hang_on_is_there_an_adu(apartment):
    """Ben's trial request (the four-unit apartment, nothing answered): the questions card listed "Is the ADU
    detached?" and "In an existing building?" before "Is there an ADU?" was answered (the audit's finding 8). Each
    ask for them now names the question it hangs on, and the moot answer."""
    asks = [a for i in apartment["view"]["items"] for a in i.get("asks") or []]
    by_field = {}
    for a in asks:
        by_field.setdefault(a.get("field"), []).append(a)
    assert by_field.get("facts.adu_detached") and by_field.get("facts.adu_existing_building"), sorted(
        f for f in by_field if f)
    for a in by_field["facts.adu_detached"]:
        assert a["depends_on"] == {"field": "facts.accessory_dwelling_unit", "moot_if": [False]}
    for a in by_field["facts.adu_existing_building"]:
        assert a["depends_on"] == {"field": "facts.adu_detached", "moot_if": [False]}
    assert all("depends_on" not in a for a in by_field.get("facts.accessory_dwelling_unit") or [])
    from design_checker.host_core.facts import ROW_ONLY_FACTS
    follow = {f"facts.{k}" for k in ROW_ONLY_FACTS}
    assert all(("depends_on" in a) == (a.get("field") in follow) for a in asks)


def test_every_restatement_of_the_leaves_rule_carries_the_mullioned_pair():
    # door leaves review round 3: the card headline and the check's reason restated the rule as "1, or 2 for a pair
    # with no mullion", which read as 1 for a mullioned pair whose clear width is the wider leaf's (a false pass)
    from model_measurement.routes.stops import STOPS
    assert "narrower leaf" in ui_data.FIELD_HEADLINES["doors[].leaves"]
    assert "narrower leaf" in STOPS["door_leaves_not_given"]
    fmt = (REPO / "docs/interior/interior_description_format.md").read_text(encoding="utf-8")
    assert "narrower leaf" in next(line for line in fmt.splitlines() if line.startswith("| `leaves`"))
