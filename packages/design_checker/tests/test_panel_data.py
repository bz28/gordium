"""What the results panel needs beyond a row's words (docs/revit/ui_design_pass.md section 4, PR 5;
design_checker/panel_data.py): each needs-review row's causes as data, how far off in words with their direction,
a ratio rule's limit as a length, each quote's source. Never a status: every verdict here is the checker's.

The eval: the Children's Odyssey day care (test_data/answer_keys/portland_me_19_libby_st/, read-only): its route rows
come out grouped by cause, the rooms with no route as the 5 rooms of eval_comparison.yaml, by their element ids.
"""

import ast
import json
import os
import random
import re
import sys
from pathlib import Path

import pytest
import yaml

from design_checker import each_part, egress, grouping, panel_data, present
from rule_format.rulebook import REPO, Context, load

sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_routes_parts import MAINE, NEW_DAY_CARE, RULES, day_care, storage_in_storage  # noqa: E402

ANSWER = REPO / "apps/revit_addin/tests/Gordium.Revit.Reading.Tests/answers/children_odyssey_check_answer.json"
EVAL = REPO / "test_data/answer_keys/portland_me_19_libby_st/eval_comparison.yaml"
ROUTE_RULES = ("general.ibc_1016_1_travel_distance", "general.nfpa_16_2_6_2_point_in_room_to_exit",
               "general.ibc_1014_3_common_path", "general.nfpa_16_2_5_3_1_common_path_sprinklered",
               "general.ibc_1018_4_dead_end", "general.nfpa_16_2_5_2_dead_end",
               "general.ibc_1015_2_1_remoteness", "general.ibc_508_2_1_accessory_area")
DIRECTION = re.compile(r"to spare|short|over|at the limit|past the limit|at limit|room here")


@pytest.fixture(scope="module")
def maine():
    return load(RULES)["rules"], Context.for_jurisdiction(MAINE).allowed()


def _items(maine, description, values=None):
    from model_measurement.routes import measure
    rules, allowed = maine
    return each_part.check_parts(rules, measure(description)["parts"], dict(values or NEW_DAY_CARE), allowed)["items"]


def _of(items, rule):
    return [i for i in items if i["rule"] == rule]


# ---- how far off ------------------------------------------------------------------------------------------------

def test_a_how_far_is_never_larger_than_the_margin_under_any_reading():
    """Room to spare is the least over the readings, rounded down; a certain shortfall ("at least") is the least,
    rounded down; "up to" is the worst reading's own, rounded up. Each always says its direction."""
    rng = random.Random(5)
    for _ in range(3000):
        margins = [round(rng.uniform(-40, 40), rng.choice((0, 2, 4, 6))) for _ in range(rng.randint(1, 4))]
        for status in (present.COMPLIES, present.REVIEW, present.FAILS):
            words = panel_data.how_far_words(status, margins, "ft", rng.random() < 0.5)
            assert DIRECTION.search(words), (margins, words)
            assert not re.search(r"(^|\s)[+−-]\d", words), words           # never a bare signed number
            amount = float(re.search(r"[\d,]+(?:\.\d+)?", words.replace(",", "")).group()) \
                if re.search(r"\d", words) else 0.0
            if min(margins) >= 0:
                assert amount <= min(margins) + 1e-9, (margins, words)
            elif max(margins) < 0 and "at least" in words:
                assert amount <= -max(margins) + 1e-9, (margins, words)
            elif min(margins) < 0 <= max(margins):
                assert words.startswith("up to") and amount >= -min(margins) - 1e-9, (margins, words)


@pytest.mark.parametrize("status,margins,maximum,want", [
    (present.COMPLIES, [50.0], True, "50 ft to spare"),
    (present.REVIEW, [116.169], False, "116.16 ft to spare if confirmed"),     # rounded down, never kinder
    (present.FAILS, [-10.0], True, "10 ft over"),
    (present.FAILS, [-2.501], False, "2.51 ft short"),                         # one reading's shortfall: up
    (present.REVIEW, [-3.0, -5.0], True, "at least 3 ft over; see why"),
    (present.REVIEW, [-3.0, 4.0], True, "up to 3 ft over under some reading; see why"),
    (present.COMPLIES, [0.004], True, "at the limit"),                         # rounds to nothing: no "0 ft"
    (present.FAILS, [6.0], True, "6 ft room here; see why"),                  # room on a row failing another way
    (present.FAILS, [-0.005, -5.0], True, "over under every reading"),         # review round 1: never "less than
    (present.FAILS, [-0.004], True, "0.01 ft over"),                           # 0.01 over" beside a 5 ft one
])
def test_how_far_words(status, margins, maximum, want):
    assert panel_data.how_far_words(status, margins, "ft", maximum) == want


def test_a_dead_end_that_fails_says_how_far_over_and_one_that_complies_its_room(maine):
    """day_care(branch=26): the branch's dead end is 26 + 11 - 11 = 30 ft... measured by the route code; NFPA 101
    16.2.5.2 allows 20 ft unsprinklered: 10 ft over. Its common path complies with room the worker's figures give."""
    items = _items(maine, day_care(branch=26))
    dead, = _of(items, "general.nfpa_16_2_5_2_dead_end")
    assert dead["status"] == present.FAILS and dead["how_far"] == "10 ft over"
    common, = _of(items, "general.nfpa_16_2_5_3_2_common_path_not_sprinklered")
    assert common["status"] == present.COMPLIES and common["how_far"].endswith(" ft to spare")


def test_the_remoteness_limit_is_said_as_a_length(maine):
    """IBC 1015.2.1: exits at least 1/2 the diagonal apart (unsprinklered). day_care(branch=26) measures the exits 72
    ft apart (nearest edges) against a 79.31 ft diagonal: the limit is 39.66 ft (79.31 / 2, rounded up), the room
    72 - 39.655 = 32.345, said 32.34 (rounded down). A flag rule: never "complies", the room "if confirmed"."""
    items = _items(maine, day_care(branch=26))
    row, = _of(items, "general.ibc_1015_2_1_remoteness")
    got = row["limit_length"]
    assert row["status"] == present.REVIEW
    assert got["measured"] / got["of"] == pytest.approx(got["measured"] / got["of"])
    assert got["limit"] == pytest.approx(got["of"] / 2) and got["ratio"] == 0.5 and got["unit"] == "ft"
    assert got["words"] == "exits 72 ft apart, needs ≥ 39.66 ft (1/2 of the 79.31 ft diagonal)"
    assert row["how_far"] == "32.34 ft to spare if confirmed"


def test_no_length_is_made_from_a_ratio_its_lengths_dont_give():
    """Only where the ratio is exactly the two lengths' quotient: else no length, never a guess."""
    more = {"nearest_edges": 72.0, "diagonal": 79.31}
    assert panel_data._ratio_lengths("exit_remoteness_ratio", [72.0 / 79.31], [0.5], more) is not None
    assert panel_data._ratio_lengths("exit_remoteness_ratio", [0.9], [0.5], more) is None
    assert panel_data._ratio_lengths("exit_remoteness_ratio", [0.9, 0.8], [0.5, 0.5], more) is None


# ---- causes -----------------------------------------------------------------------------------------------------

def test_a_room_with_no_route_is_a_cause_naming_its_room_by_id(maine):
    """storage_in_storage: s2 opens only into s1, which can be locked: no route. Each travel and common-path row
    names s2 by id (what Show selects), the same key on each so they make one card."""
    items = _items(maine, storage_in_storage())
    rows = [i for r in ("general.ibc_1016_1_travel_distance", "general.ibc_1014_3_common_path",
                        "general.nfpa_16_2_6_2_point_in_room_to_exit") for i in _of(items, r)]
    assert rows and all(i["status"] == present.REVIEW for i in rows)
    for i in rows:
        first = i["causes"][0]
        assert first["kind"] == panel_data.FIX_MODEL and first["elements"] == ["s2"] and first["key"] == "rooms:s2"
        assert first["words"] == "1 room has no route to an exit: s2"
        assert first["rooms"][0]["why"].startswith("the room s2 has no route")     # by its name, never a point
    cards = grouping.cause_cards(rows)
    assert len(cards) == 1 and cards[0]["items"] == [i["id"] for i in rows] and cards[0]["elements"] == ["s2"]


def test_a_flag_rule_is_a_person_decides_after_what_the_model_must_give(maine):
    items = _items(maine, storage_in_storage())
    travel, = _of(items, "general.ibc_1016_1_travel_distance")
    assert [c["kind"] for c in travel["causes"]] == [panel_data.FIX_MODEL, panel_data.DECIDE]
    assert travel["causes"][1] == {"kind": "decide", "key": "flag", "words": panel_data.FLAG_WORDS,
                                   "elements": [travel["part"]["id"]]}


def test_a_measure_the_formula_never_reaches_is_no_cause():
    """NFPA's `not day_care_existing or existing_change_of_use`: a new day care never needs the change of use, so it
    is no cause (each_part.unsettled lists every name the rule reads, for its words)."""
    rule = {"applies_when": "nfpa_day_care_occupancy and (not day_care_existing or existing_change_of_use)",
            "check": "egress_travel_distance_occupied <= 150", "review_when": []}
    kinds = {"nfpa_day_care_occupancy": "boolean", "day_care_existing": "boolean",
             "existing_change_of_use": "boolean", "egress_travel_distance_occupied": "number"}
    new = {"nfpa_day_care_occupancy": True, "day_care_existing": False}
    assert panel_data.needed(rule, new, kinds) == ["egress_travel_distance_occupied"]
    assert panel_data.needed(rule, {**new, "day_care_existing": True}, kinds) == [
        "existing_change_of_use", "egress_travel_distance_occupied"]


def test_a_fact_the_project_states_is_a_mark(maine):
    rule = {"id": "r", "kind": "rule", "for_each": "story", "check": "egress_travel_distance_occupied <= 150",
            "applies_when": "not day_care_existing or existing_change_of_use"}
    row = {"outcome": "needs_review", "id": "L1", "values": {"egress_travel_distance_occupied": 20.0}, "reason": None}
    got = panel_data.causes(rule, row, {}, None, {}, {}, {"day_care_existing": True}, maine[1], ())
    assert got == [{"kind": "mark", "key": "fact:existing_change_of_use",
                    "words": "existing change of use: not stated for the project", "elements": [],
                    "measure": "existing_change_of_use", "field": "facts.existing_change_of_use"}]


def test_every_row_in_review_has_a_cause_and_no_other_row_has_one(maine):
    for d in (storage_in_storage(), day_care(branch=26)):
        for i in _items(maine, d):
            assert bool(i.get("causes")) == (i["status"] == present.REVIEW), i["id"]
            for c in i.get("causes") or []:
                assert c["kind"] in panel_data.KINDS and c["key"] and c["words"]


def test_cards_hold_each_row_once_in_the_order_the_architect_can_act():
    items = [{"id": f"i{n}", "rule": f"r{n}", "status": present.REVIEW, "causes": [c]} for n, c in enumerate([
        {"kind": "decide", "key": "flag", "words": "f", "elements": ["L1"]},
        {"kind": "fix_model", "key": "rooms:a", "words": "1 room", "elements": ["a"]},
        {"kind": "decide", "key": "flag", "words": "f", "elements": ["L1"]},
        {"kind": "mark", "key": "fact:x", "words": "x", "elements": []}])]
    items.append({"id": "ok", "status": present.COMPLIES, "causes": [{"kind": "decide", "key": "flag"}]})
    cards = grouping.cause_cards(items)
    assert [c["key"] for c in cards] == ["rooms:a", "fact:x", "flag"]
    assert cards[2]["items"] == ["i0", "i2"] and cards[2]["rules"] == 2 and cards[2]["elements"] == ["L1"]
    assert sorted(x for c in cards for x in c["items"]) == ["i0", "i1", "i2", "i3"]


# ---- zoning's how far, in words -----------------------------------------------------------------------------------

@pytest.mark.parametrize("delta,want", [
    ("+2'-0\"", "2'-0\" to spare"),
    ("≥ +3'-0\" if confirmed", "at least 3'-0\" to spare if confirmed"),
    ("−1'-4\" short", "1'-4\" short"),
    ("1'-6\" over", "1'-6\" over"),
    ("at least 1'-0\" short; see why", "at least 1'-0\" short; see why"),
    ("+213 sf", "213 sf to spare"),
    ("+2'-0 1/2\" (+0'-0 1/2\" if the tax-map lines are 2 ft off)",
     "2'-0 1/2\" to spare (0'-0 1/2\" to spare if the tax-map lines are 2 ft off)"),
    ("at limit", "at limit"),
])
def test_a_zoning_delta_said_with_its_direction(delta, want):
    assert present.how_far_of({"delta": delta, "margin": "+9'-9\""}) == want


def test_a_bare_signed_margin_is_never_sent_without_its_words():
    """Review of PR 4: with no Delta, a margin's sign alone said its direction; the words now say it, or nothing."""
    assert present.how_far_of({"delta": "", "margin": "+2'-0\""}) == "2'-0\" to spare"
    assert present.how_far_of({"delta": "", "margin": "−1'-4\""}) == "1'-4\" past the limit"
    assert present.how_far_of({"delta": "", "margin": "at limit"}) == "at the limit"
    assert present.how_far_of({"delta": "", "margin": "3"}) is None
    assert present.how_far_of({"margin": ""}) is None


def test_every_zoning_row_with_a_delta_says_its_direction():
    from design_checker.check import check_site
    sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
    from test_measure import FACTS, box, lot
    site = {"units": "ft", "lot": lot([(0, 0), (60, 0), (60, 110), (0, 110)]),
            "buildings": [box(5, 25, 58, 75, 0, 30)], "problems": []}
    view = check_site(site, dict(FACTS))["view"]
    shown = [i for i in view["items"] if i.get("delta")]
    assert shown
    for i in shown:
        assert DIRECTION.search(i["how_far"]) and not re.search(r"(^|[\s(])[+−]\d", i["how_far"]), i["how_far"]
    review = [i for i in view["items"] if i["status"] == present.REVIEW]
    assert all(i.get("causes") for i in review)


# ---- each quote's source ------------------------------------------------------------------------------------------

def test_each_law_quote_carries_its_file_page_and_lines():
    item = {"id": "x", "group": present.LAW_GROUP, "law_key": "maine/maine_state",
            "detail": {"quotes": [{"text": "a", "where": "1014.3"}, {"text": "b", "where": "1014.3"}],
                       "sources": [{"file": "icc.ibc.2009.pdf", "page": 265, "lines": [76, 78]},
                                   {"file": "gov.law.nfpa.101.2012.pdf", "page": 174, "lines": [66, 69]}]}}
    present.law_quote_sources([item])
    first, second = item["detail"]["quotes"]
    assert (first["file"], first["page"], first["lines"]) == ("icc.ibc.2009.pdf", 265, [76, 78])
    assert first["document"] == "2009 International Building Code (IBC)" and first["in_repo"] is False
    assert first["url"] == "https://archive.org/details/gov.law.icc.ibc.2009"
    assert second["page"] == 174 and second["file"] == "gov.law.nfpa.101.2012.pdf"
    off = {"id": "y", "group": present.LAW_GROUP, "law_key": "maine/maine_state",
           "detail": {"quotes": [{"text": "a"}, {"text": "b"}],
                      "sources": [{"file": "icc.ibc.2009.pdf", "page": 265, "lines": [76, 78]}]}}
    present.law_quote_sources([off])
    assert not any("file" in q for q in off["detail"]["quotes"])   # lists that don't match: never another's source


def test_a_part_row_carries_its_rules_sources_in_its_quotes_order(maine):
    rules, _ = maine
    items = _items(maine, day_care(branch=26))
    row, = _of(items, "general.ibc_1015_2_1_remoteness")
    rule = next(r for r in rules if r["id"] == "general.ibc_1015_2_1_remoteness")
    assert row["detail"]["sources"] == [{"file": s["file"], "page": s["page"], "lines": s["lines"]}
                                        for s in rule["sources"]]


# ---- the eval: the Children's Odyssey day care ---------------------------------------------------------------------

def _eval_rooms():
    e = yaml.safe_load(EVAL.read_text(encoding="utf-8"))
    return {f: set(e["figures"][f]["gordium"]["story"]["rooms_not_measured"])
            for f in ("travel_distance", "common_path")}


def _odyssey_route_rows(view):
    return [i for i in view["items"] if i["rule"] in ROUTE_RULES and i["status"] == present.REVIEW]


def _check_odyssey(view):
    """The route rows of the eval's 8 rules (eval_comparison.yaml verdicts) by first cause: the 4 travel and common
    path rows on one card, the 5 rooms with no route by id; every IBC flag (the dead ends, remoteness, storage) a
    person decides; NFPA's dead ends turn on the open question of where a dead end with a door is measured; and
    NFPA 16.2.5.2's dead end 5 needs review because its own review condition holds (over 20 ft, at most 50 ft
    sprinklered: open question 2 of the Maine README). Returns {first cause key: [rules]}."""
    rows = _odyssey_route_rows(view)
    assert {i["rule"] for i in rows} == set(ROUTE_RULES)
    by = {}
    for i in rows:
        by.setdefault(i["causes"][0]["key"], []).append(i)
    rooms = [k for k in by if k.startswith("rooms:")]
    assert len(rooms) == 1, rooms
    card = by[rooms[0]]
    assert sorted(i["rule"] for i in card) == sorted(ROUTE_RULES[:4])
    want = _eval_rooms()
    assert want["travel_distance"] == want["common_path"]
    names = {r["id"]: r["name"] for r in card[0]["causes"][0]["rooms"]}
    assert set(names.values()) == want["travel_distance"] and len(names) == 5
    assert card[0]["causes"][0]["elements"] == sorted(names)
    # each id is that room's own: the answer's space rows name each room by the same id
    spaces = {i["part"]["id"]: i["part"]["name"] for i in view["items"]
              if isinstance(i.get("part"), dict) and i["part"].get("part") == "space"}
    assert all(spaces[rid] == name for rid, name in names.items())
    flags = by["flag"]
    assert {i["rule"] for i in flags} == {"general.ibc_1018_4_dead_end", "general.ibc_1015_2_1_remoteness",
                                          "general.ibc_508_2_1_accessory_area"}
    question = [k for k in by if k.startswith("question:")]
    assert question == ["question:door_ends_dead_end"]
    assert {i["rule"] for i in by[question[0]]} == {"general.nfpa_16_2_5_2_dead_end"}
    rest = set(by) - {rooms[0], "flag", question[0]}
    assert all(k.startswith("review_when:") for k in rest) and len(rest) == 1
    assert {i["rule"] for k in rest for i in by[k]} == {"general.nfpa_16_2_5_2_dead_end"}
    # the remoteness limit as a length: 1/3 of the 212.985 ft diagonal (sprinklered), 71.0 ft
    remote, = [i for i in rows if i["rule"] == "general.ibc_1015_2_1_remoteness"]
    assert remote["limit_length"]["words"] == "exits 187.16 ft apart, needs ≥ 71 ft (1/3 of the 212.99 ft diagonal)"
    assert remote["how_far"] == "116.16 ft to spare if confirmed"
    # the cards: one per first cause, every route row on one
    groups = [g for g in view["groups"] if g.get("causes") is not None and g["key"].endswith(":review")]
    cards = {c["key"]: c for g in groups for c in g["causes"]}
    # the card holds every row with that first cause: the 4 route rows, and any other rule reading those figures
    # (NFPA 16.2.6.3's sprinkler increase reads the travel too)
    assert set(cards[rooms[0]]["items"]) >= {i["id"] for i in card} and cards[rooms[0]]["kind"] == "fix_model"
    assert cards[rooms[0]]["elements"] == card[0]["causes"][0]["elements"]
    return {k: sorted({i["rule"] for i in v}) for k, v in by.items()}


def test_the_odyssey_route_rows_come_out_by_cause_in_the_committed_answer():
    """The committed answer (made by apps/revit_addin/tools/evals/make_odyssey_answer.py from the model's
    description, which stays outside the repo)."""
    view = json.loads(ANSWER.read_text(encoding="utf-8"))["result"]["view"]
    _check_odyssey(view)


@pytest.mark.skipif(not os.environ.get("GORDIUM_CO_DESCRIPTION"),
                    reason="the Children's Odyssey model's description stays outside the repo (open question 5): "
                           "set GORDIUM_CO_DESCRIPTION to its path to make the answer again (about 11 minutes)")
def test_the_committed_odyssey_answer_is_what_the_worker_makes():
    sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
    import make_odyssey_answer
    got = make_odyssey_answer.answer(json.loads(Path(os.environ["GORDIUM_CO_DESCRIPTION"]).read_text(encoding="utf-8")))
    committed = json.loads(ANSWER.read_text(encoding="utf-8"))
    for a in (got, committed):
        a["about"].pop("worker_fingerprint", None)
    assert got == committed
    _check_odyssey(got["result"]["view"])


def test_a_row_with_no_reason_on_a_part_with_readings_has_its_own_causes(maine):
    """The Odyssey's NFPA travel rows (round 1 of the eval): a story part with readings (its areas) and a row with no
    reason once fell to the catch-all ("reason: <rule id>") from a crash on the missing reason; they name the rooms
    with no route."""
    rules, allowed = maine
    rule = next(r for r in rules if r["id"] == "general.nfpa_16_2_6_2_point_in_room_to_exit")
    part = {"id": "L1", "readings": {"story_building_area": [{"value": 1.0, "named": {"q": "a"}}]}}
    row = {"outcome": "needs_review", "id": "L1", "values": {}, "reason": None}
    more = {"egress_travel_distance_occupied": {"room_ids_not_measured": {
        "r9": {"name": "CLOSET (40)", "why": "the point (1, 2) has no route to any exit", "stop": "no_route"}}}}
    got = panel_data.causes(rule, row, {}, part, more, {}, dict(NEW_DAY_CARE), allowed, ())
    assert [c["key"] for c in got] == ["rooms:r9"] and got[0]["words"] == "1 room has no route to an exit: CLOSET (40)"


def test_a_zoning_row_waiting_on_facts_names_them_in_the_architects_words():
    """The seed session's ADU row: its card says the facts as the "Enter …" button does, never the facts' names."""
    got = present.zoning_causes({"needs": ["accessory_dwelling_unit"], "status": present.REVIEW})
    assert got == [{"kind": "mark", "key": "facts:accessory_dwelling_unit", "words": "Enter whether an ADU is on the lot",
                    "elements": [], "needs": ["accessory_dwelling_unit"], "field": "facts.accessory_dwelling_unit",
                    "fields": ["facts.accessory_dwelling_unit"]}]


# ---- review round 1 (2026-11-22) -----------------------------------------------------------------------------------

def test_several_readings_short_whose_least_rounds_to_nothing_never_say_less_than():
    words = panel_data.how_far_words(present.FAILS, [-0.005, -5.0], True, True)
    assert not words.startswith("less than") and words == "over under every reading"


def _odyssey_view():
    return json.loads(ANSWER.read_text(encoding="utf-8"))["result"]["view"]


def test_every_cause_naming_a_room_with_no_route_is_on_the_one_rooms_card():
    """The 5 rooms were on 7 cards: the room-door travel and each room's own common path had their own, keyed by
    their words, and the room-door one named the story. Now each names its rooms by id and every one is on the rooms
    card, keyed by all of them."""
    view = _odyssey_view()
    eval_rooms = _eval_rooms()["travel_distance"]
    items = {i["id"]: i for i in view["items"]}
    ids = {r["id"] for i in view["items"] for c in i.get("causes") or [] for r in c.get("rooms") or []
           if r.get("name") in eval_rooms}
    assert len(ids) == 5
    door, = [i for i in view["items"] if i["rule"] == "general.nfpa_16_2_6_2_room_door_to_exit"
             and i["status"] == present.REVIEW]
    assert set(door["causes"][0]["elements"]) <= ids and door["causes"][0]["elements"]
    assert door["part"]["id"] not in door["causes"][0]["elements"]          # the rooms, never the story
    for g in view["groups"]:
        if not g["key"].endswith(":review"):
            continue
        rooms_cards = [c for c in g["causes"] if c["key"].startswith("rooms:")]
        assert len(rooms_cards) == 1 and set(rooms_cards[0]["elements"]) == ids
        for c in g["causes"]:
            if c is rooms_cards[0] or c["kind"] != "fix_model":
                continue
            for x in c["items"]:
                first = items[x]["causes"][0]
                assert not set(first.get("elements") or []) & ids, (c["key"], x)
                assert not any(r.get("id") in ids for r in first.get("rooms") or []), (c["key"], x)


def test_every_law_row_in_review_is_on_one_card():
    """37 of the law's own rows (the interior drawing's, the rules not written for each part, the sections not
    checked yet) had no cause and were on no card. Now every row in review has one, and each group's cards hold
    exactly its rows in review."""
    view = _odyssey_view()
    items = {i["id"]: i for i in view["items"]}
    for g in view["groups"]:
        if not g["key"].endswith((":review", ":by_hand")):
            continue
        review = {x for x in g["items"] if items[x]["status"] == present.REVIEW}
        assert all(items[x].get("causes") for x in review), g["key"]
        on_cards = [x for c in g["causes"] for x in c["items"]]
        assert set(on_cards) == review and len(on_cards) == len(set(on_cards)), g["key"]


def _interior(stop, **blanks):
    from model_measurement.interior.stops import Stop
    return "The interior drawing: " + Stop(stop, **blanks).reason


@pytest.mark.parametrize("item,kind", [
    ({"id": "egress.interior#1", "law_short": "Egress", "objects": ["w1"],
      "reason": _interior("flag_missing", what="opening W1",
                          question="it is an emergency escape and rescue opening")}, "mark"),
    # the stairs the drawing doesn't say it has all of: the architect's to state (a mark), its field the stairs
    ({"id": "egress.interior#2", "law_short": "Egress", "reason": _interior("not_read", what="stairs", key="stairs")},
     "mark"),
    ({"id": "egress.general.ibc_308_5", "law_short": "Egress", "reason": None}, "decide"),
    ({"id": "egress.not_checked_yet", "law_short": "Egress", "reason": "x"}, "measure_by_hand"),
    ({"id": "egress.has_none.stair", "law_short": "Egress", "reason": "Confirm: no stairs"}, "decide"),
    # review round 2: classed by the row's id, never by its words ("is marked as an escape opening")
    ({"id": "egress.skipped#1", "law_short": "Egress", "reason": "Window 5 is marked as an escape opening but isn't "
      "checked: no sill height. Check it by hand"}, "measure_by_hand"),
    ({"id": "egress.nothing_applied", "law_short": "Egress", "reason": "None of the rules applied: check it by hand"},
     "measure_by_hand"),
    ({"id": "egress.rules#maine/maine_state", "law_short": "Egress", "law_key": "maine/maine_state",
      "reason": "The rules don't pass the rule checks"}, "measure_by_hand"),
    ({"id": "egress.interior#3", "law_short": "Egress", "reason": "The interior drawing: door D2 is marked twice"},
     "fix_model"),
])
def test_a_laws_own_row_has_a_cause_by_what_it_is(item, kind):
    from design_checker import egress
    if item["id"] == "egress.general.ibc_308_5":
        item = dict(item, reason=egress.NOT_PER_PART)
        kind = "measure_by_hand"
    got, = present.law_causes(item)
    assert got["kind"] == kind and got["words"] == (item["reason"] or "needs review")
    assert got["elements"] == (item.get("objects") or [])


def test_the_measuring_names_the_room_it_stops_at_by_id_for_the_room_door_travel_and_a_rooms_common_path():
    from model_measurement.routes import measure
    got = measure(storage_in_storage())["parts"]
    story, = got["story"]
    door = story["more"]["egress_travel_from_room_door"]["room_ids_not_measured"]
    assert set(door) == {"s2"} and door["s2"]["stop"] == "no_exit_access" and door["s2"]["name"] == "s2"
    s2, = [p for p in got["space"] if p["id"] == "s2"]
    own = s2["more"]["space_common_path"]["room_ids_not_measured"]
    assert set(own) == {"s2"} and own["s2"]["why"] == s2["not_measured"]["space_common_path"]


def test_room_causes_sharing_a_room_are_one_card_keyed_and_named_by_all_its_rooms(maine):
    """storage_in_storage: s2 stops the story's travel, its room-door travel and its own common path: one card."""
    items = [i for i in _items(maine, storage_in_storage()) if i["status"] == present.REVIEW]
    cards = [c for c in grouping.cause_cards(items) if c["key"].startswith("rooms:")]
    assert len(cards) == 1 and cards[0]["key"] == "rooms:s2" and cards[0]["elements"] == ["s2"]
    door, = _of(items, "general.nfpa_16_2_6_2_room_door_to_exit")
    space = [i for i in items if (i.get("part") or {}).get("id") == "s2" and i["causes"][0]["key"] == "rooms:s2"]
    assert door["causes"][0]["elements"] == ["s2"] and space
    assert {door["id"]} | {i["id"] for i in space} <= set(cards[0]["items"])
    # two cards sharing a room are one, keyed by every room, words from every room
    a = {"kind": "fix_model", "key": "rooms:a,b", "words": "2", "elements": ["a", "b"],
         "rooms": [{"id": "a", "name": "A", "stop": "no_route"}, {"id": "b", "name": "B", "stop": "no_route"}]}
    b = {"kind": "fix_model", "key": "rooms:b,c", "words": "2", "elements": ["b", "c"],
         "rooms": [{"id": "b", "name": "B", "stop": "no_route"}, {"id": "c", "name": "C", "stop": "no_exit_access"}]}
    got = grouping.cause_cards([{"id": "1", "status": present.REVIEW, "causes": [a]},
                                {"id": "2", "status": present.REVIEW, "causes": [b]}])
    assert [(c["key"], c["elements"], c["items"]) for c in got] == [("rooms:a,b,c", ["a", "b", "c"], ["1", "2"])]
    assert got[0]["words"] == "3 rooms have no route to an exit: A, B, C"


def test_grouping_a_laws_items_gives_its_own_rows_their_causes():
    """The hook, on the Odyssey's items with the law's own rows' causes taken away: present.grouped gives them back,
    and every row in review is on a card."""
    items = _odyssey_view()["items"]
    for i in items:
        if "@" not in i["id"]:
            i.pop("causes", None)
    groups = present.grouped(items)
    review = {i["id"] for i in items if i["group"] == present.LAW_GROUP and i["status"] == present.REVIEW}
    assert all(i.get("causes") for i in items if i["id"] in review)
    on_cards = {x for g in groups for c in g.get("causes") or [] for x in c["items"]}
    assert review <= on_cards


def test_the_odyssey_answer_maker_loads_maines_law_with_no_model_description():
    """Review round 7 (P1): the script that makes the committed Odyssey answer crashed in egress.laws once it read a
    place's folder (its stand-in place had a name and inherited rulebooks only), and CI missed it: the test above is
    skipped without the model's description. This runs its patching (as_the_eval) and egress.laws, which need none.
    Its place is the real Place (rule_format.place.stand_in), so a field egress reads later can't break it."""
    from dataclasses import fields

    from design_checker import egress
    from rule_format.place import Place
    sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
    import make_odyssey_answer as maker
    assert isinstance(maker.PLACE, Place)
    assert {f.name for f in fields(Place)} <= set(vars(maker.PLACE))
    real = egress.place_of
    with maker.as_the_eval():
        found = egress.laws(maker.MAINE)
    assert found["place"] == "Portland, ME (the eval)" and found["folder"] == maker.MAINE
    assert [law["key"] for law in found["laws"]] == ["maine/maine_state"] and found["laws"][0]["rules"]
    assert egress.place_of is real                                     # the patching undone
    # the stand-in for the interior measuring takes the measuring's keywords (no-stairs PR, round 2: it crashed once
    # egress passed whole= and stated_stories=)
    with maker.as_the_eval():
        got = egress.measure_interior({"format": "gordium.interior/1", "units": "in", "rooms": [], "stairs": []},
                                      whole=None, stated_stories=2)
    assert got["parts"]["stair"] is None


def test_the_odyssey_answers_route_join_never_adds_the_building_codes_door_parts():
    """Section group 6a's review: the routes now give a door part for every door (New York's door size rules), but
    the committed Odyssey answer was made with Maine's means of egress door rules not read (they read what the
    architect marks: swing, latch, panic hardware, which no door part measures). The eval's join takes the story,
    space and corridor parts only, so the answer the script makes stays the committed one."""
    sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
    import make_ny_build_data as build
    import make_odyssey_answer
    desc = build.interior_of()
    with make_odyssey_answer.as_the_eval():
        got = egress.measure_interior(desc)
    assert got["parts"].get("means_of_egress_door") is None
    assert got["parts"]["story"] and got["parts"]["corridor"]
