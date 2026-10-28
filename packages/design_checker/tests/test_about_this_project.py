"""The start box's "About this project" section (queue item 14): the facts only the architect knows are asked up front,
only the ones the chosen district's and use's rules need, each with one-click answers and NO default. Unanswered, the
rows that wait on a fact say so exactly as before (never a false pass).

Expected values come from the rulebooks read by hand (R-1b.yaml lines 386-491 for the stream and South Hill rules,
1076 for the household rule, 1262 for the home occupation): R-1b with a one-family house reads these seven facts, of
which the start box asks the two that shape the envelope (stream, South Hill); the household and home business are use
details (rhino_logic.DEFERRED_FACTS), answered later; the stream's distance waits on a yes."""

import copy

import pytest

from design_checker import check, present, scenarios
from design_checker import rhino_logic as logic
from design_checker.check import check_site

CITY = "regulations/jurisdictions/new_york/ithaca_city"
R1B_ASKS = ["stream_near_lot", "south_hill_overlay"]       # up front: what shapes the envelope (Ben, 2026-10-27)
HOUSEHOLD = ["unrelated_persons", "owner_occupied", "accessory_dwelling_unit", "functional_family_unit",
             "home_occupation"]                             # use details: deferred, answered when the interior is planned


@pytest.fixture(scope="module")
def options():
    return check.options(CITY)


def test_r1b_one_family_asks_exactly_the_facts_its_rules_read(options):
    rows = logic.follow_up_rows(options, "R-1b", "one_family_detached", {})
    assert [r["key"] for r in rows] == R1B_ASKS
    assert all(r["value"] is None for r in rows), "no default: every question starts unanswered"
    # the household and home business are never asked up front, whatever else is answered
    every = logic.follow_up_rows(options, "R-1b", "one_family_detached", {"home_occupation": True, "stream_near_lot": True})
    assert not {r["key"] for r in every} & set(logic.DEFERRED_FACTS)


def test_what_the_drawing_shows_is_never_asked_up_front(options):
    for zone, uses in options["follow_ups"].items():
        for use in uses:
            asked = logic.follow_up_keys(options, zone, use)
            assert not set(asked) & set(logic.DRAWN_FACTS), (zone, use)
            assert not set(asked) & set(logic.INTERIOR_FACTS), (zone, use)


def test_the_distance_waits_for_its_yes_and_the_floor_areas_are_not_asked_up_front(options):
    ask = lambda facts: [r["key"] for r in logic.follow_up_rows(options, "R-1b", "one_family_detached", facts)]
    assert "stream_distance" not in ask({}) and "stream_distance" not in ask({"stream_near_lot": False})
    assert "stream_distance" in ask({"stream_near_lot": True})
    # deferred: not even after a yes (answered in the panel, when the interior is planned)
    assert "home_occupation_area" not in ask({"home_occupation": True})


def test_the_list_is_derived_from_the_rulebook_not_hard_coded():
    """Whatever the options say a rule reads is what the box asks (a made-up district with one rule reading one fact)."""
    fake = {"follow_ups": {"X-1": {"u": ["south_hill_overlay"], "v": ["stream_near_lot", "stream_distance"]}}}
    assert [r["key"] for r in logic.follow_up_rows(fake, "X-1", "u", {})] == ["south_hill_overlay"]
    assert [r["key"] for r in logic.follow_up_rows(fake, "X-1", "v", {})] == ["stream_near_lot"]
    assert logic.follow_up_rows(fake, "X-1", "w", {}) == []


def test_each_yes_no_offers_its_two_answers_in_plain_words():
    words = {k: [w for w, _ in logic.choices_for(k, "yes_no")] for k in
             ("home_occupation", "stream_near_lot", "south_hill_overlay", "accessory_dwelling_unit", "owner_occupied")}
    assert words["home_occupation"] == ["No home business", "Home business planned"]
    assert words["stream_near_lot"] == ["No stream within 20 ft", "Stream or inlet within 20 ft"]
    assert words["south_hill_overlay"] == ["Not in the South Hill Overlay", "In the South Hill Overlay"]
    assert dict(logic.choices_for("home_occupation", "yes_no")) == {"No home business": False,
                                                                    "Home business planned": True}
    # a number typed in the panel stays among a count's choices; a typed kind has none
    assert (12, 12) not in logic.choices_for("unrelated_persons", "count")
    assert ("12", 12) in logic.choices_for("unrelated_persons", "count", 12)
    assert logic.choices_for("stream_distance", "length") is None


def test_quick_answers_fill_only_what_is_asked():
    quick = dict(logic.quick_answers(R1B_ASKS + HOUSEHOLD))
    assert quick["1 family, no roomers"] == {"unrelated_persons": 0, "functional_family_unit": False}
    assert quick["No stream, not in South Hill"] == {"stream_near_lot": False, "south_hill_overlay": False}
    assert logic.quick_answers(["stream_near_lot"]) == [("No stream, not in South Hill", {"stream_near_lot": False})]
    assert logic.quick_answers(["occupants"]) == []
    # R-1b's start box asks neither household question: those quick answers are not offered
    assert [w for w, _ in logic.quick_answers(R1B_ASKS)] == ["No stream, not in South Hill"]


def test_a_typed_number_is_kept_as_typed_and_never_below_its_least():
    assert logic.parse_answer("length", "19.96") == 19.96            # never rounded to 20
    assert logic.parse_answer("area", "1,200") == 1200
    assert logic.parse_answer("area", "") is None
    for bad in ("-1", "abc", "1e3", "nan", "inf", "1.2.3"):
        with pytest.raises(ValueError):
            logic.parse_answer("length", bad)
    with pytest.raises(ValueError, match="1 or more"):
        logic.parse_answer("count", "0", "attached_units_in_building")
    assert logic.parse_answer("count", "0", "unrelated_persons") == 0


def test_a_stale_answer_never_stays_behind(options):
    """The distance typed before the stream answer flipped to No is dropped, so the facts never disagree; a use detail
    answered in the panel is kept, not erased by the box."""
    answers = {"stream_near_lot": False, "stream_distance": 5}
    facts, answered = logic.answers_applied({"unrelated_persons": 2, "home_occupation": True}, answers, "R-1b",
                                            "one_family_detached", options)
    assert facts == {"stream_near_lot": False, "unrelated_persons": 2, "home_occupation": True}
    assert answered == ["stream_near_lot"]
    facts, _ = logic.answers_applied({}, {"stream_near_lot": True, "stream_distance": 5}, "R-1b",
                                     "one_family_detached", options)
    assert facts["stream_distance"] == 5


def test_the_box_reopens_when_a_yes_opens_a_question(options):
    shown = ("R-1b", "one_family_detached", logic.gate_of({}))
    assert not logic.box_needs_refresh(options, shown, ("R-1b", "one_family_detached", logic.gate_of({"stream_near_lot": False})))
    assert logic.box_needs_refresh(options, shown, ("R-1b", "one_family_detached", logic.gate_of({"stream_near_lot": True})))
    # a home business yes opens nothing in the box (deferred)
    assert not logic.box_needs_refresh(options, shown, ("R-1b", "one_family_detached", logic.gate_of({"home_occupation": True})))
    # a district pick still works with the old two-part form
    assert logic.box_needs_refresh(options, ("R-1b", "one_family_detached"), ("R-3b", "one_family_detached"))


# ---- the whole check: unanswered = needs review, as today; answered = decided ---------------------------------------

def _rows(zone="R-1b", use="one_family_detached", **facts):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "12_r3a_two_family_at_the_building_limits.yaml"))
    sc["district"], sc["use"] = zone, use
    sc["lot"]["points"] = [[0, 0], [70, 0], [70, 150], [0, 150]]
    sc["buildings"] = [{"id": "house", "outline": [[15, 40], [50, 40], [50, 80], [15, 80]], "base": 0, "floors": [10, 10]}]
    s, f, extras = scenarios.site(sc)
    res = check_site(s, {**f, "main_building": "house_floor1", **facts}, extras=extras)
    return {i["rule"]: i for i in res["view"]["items"]}


def _view(zone="R-1b", use="one_family_detached", **facts):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "12_r3a_two_family_at_the_building_limits.yaml"))
    sc["district"], sc["use"] = zone, use
    sc["lot"]["points"] = [[0, 0], [70, 0], [70, 150], [0, 150]]
    sc["buildings"] = [{"id": "house", "outline": [[15, 40], [50, 40], [50, 80], [15, 80]], "base": 0, "floors": [10, 10]}]
    s, f, extras = scenarios.site(sc)
    return check_site(s, {**f, "main_building": "house_floor1", **facts}, extras=extras)["view"]


def _waiting(view):
    return {k for i in view["items"] if i["status"] == present.REVIEW for k in i.get("needs") or []}


def test_the_box_asks_every_stated_fact_a_building_row_waits_on_and_the_rest_are_use_details(options):
    """Every stated fact a needs-review row waits on is either asked in the box (a single visit clears it), a use detail
    (deferred, in its own group), or one asked elsewhere (the interior's, the drawn ones)."""
    for zone in options["zones"]:
        waiting = _waiting(_view(zone)) & set(logic.STATED_FACTS) - {"stories"}
        asked = set(logic.follow_up_keys(options, zone, "one_family_detached"))
        elsewhere = set(logic.INTERIOR_FACTS) | set(logic.DRAWN_FACTS) | set(logic.DEFERRED_FACTS)
        assert not waiting - asked - elsewhere, (zone, waiting - asked - elsewhere)


def test_use_details_unanswered_are_their_own_collapsed_group_and_never_a_pass():
    v = _view()
    details = [i for i in v["items"] if i.get("use_detail")]
    assert details, "R-1b's household rule waits on the household"
    assert all(i["status"] == present.REVIEW for i in details)              # still needs review (never pass)
    assert all(set(i["needs"]) <= set(logic.DEFERRED_FACTS) for i in details)
    groups = {g["key"]: g for g in v["groups"]}
    assert groups["use_details"]["title"] == logic.USE_DETAILS_TITLE
    assert set(groups["use_details"]["items"]) == {i["id"] for i in details}
    assert not {i["id"] for i in details} & set(groups.get("review", {"items": []})["items"])
    # not counted among the building's problems, but said, and apart from the passes
    building_review = sum(1 for i in v["items"] if i["status"] == present.REVIEW and not i.get("use_detail"))
    assert f"{len(details)} use detail" in v["summary"] and "to answer" in v["summary"]
    assert v["summary"].count("need review") + v["summary"].count("needs review") == (1 if building_review else 0)
    assert v["state"] != present.COMPLIES, "a question left open is never a pass"
    # with every building row decided, the use details alone still hold the state at needs review
    only = [dict(i, status=present.COMPLIES) for i in v["items"] if not i.get("use_detail")] + details
    assert present.state(only) == present.REVIEW and present.summary(only).endswith("to answer")


def test_only_use_details_left_is_still_not_a_pass():
    """Everything else decided: the header state is needs review, never complies, and the summary still says so."""
    items = [{"id": "a", "status": present.COMPLIES, "group": "building"},
             {"id": "b", "status": present.REVIEW, "group": "building", "use_detail": True}]
    assert present.state(items) == present.REVIEW
    assert present.summary(items) == "1 complies · 1 use detail to answer"
    assert present.state(items[:1]) == present.COMPLIES


def test_an_answered_use_detail_leaves_the_group_and_counts_like_any_row():
    """Answered to fail: it is a failure in the building's rows, counted; answered to pass: complies; a row waiting on
    something besides use details stays among the building's rows."""
    failing = _view(unrelated_persons=5, owner_occupied=False, accessory_dwelling_unit=False,
                    functional_family_unit=False)
    assert [i["status"] for i in failing["items"] if i.get("rule") == "R-1b.occupancy_one_family"] == [present.FAILS]
    assert "does not comply" in failing["summary"]
    mixed = {"status": present.REVIEW, "needs": ["unrelated_persons", "stream_near_lot"]}
    assert not logic.is_use_detail(mixed)
    assert not logic.is_use_detail({"status": present.REVIEW, "needs": []})
    assert not logic.is_use_detail({"status": present.COMPLIES, "needs": ["unrelated_persons"]})
    assert logic.is_use_detail({"status": present.REVIEW, "needs": ["unrelated_persons", "home_occupation"]})


def test_unanswered_stream_still_needs_review_and_answering_decides_it(options):
    waiting = _waiting(_view())
    assert {"stream_near_lot"} <= waiting
    answers = {"stream_near_lot": False, "south_hill_overlay": False}
    facts, _ = logic.answers_applied({}, answers, "R-1b", "one_family_detached", options)
    still = _waiting(_view(**facts))
    assert not still & set(answers), still
    assert "stream_near_lot" in _waiting(_view(**logic.answers_applied({}, {"south_hill_overlay": False}, "R-1b",
                                                                       "one_family_detached", options)[0]))


def test_a_close_stream_is_a_fail_and_a_far_one_a_pass_once_the_distance_is_typed(options):
    near, _ = logic.answers_applied({}, {"stream_near_lot": True, "stream_distance": 19.96}, "R-1b",
                                    "one_family_detached", options)
    far, _ = logic.answers_applied({}, {"stream_near_lot": True, "stream_distance": 20}, "R-1b",
                                   "one_family_detached", options)
    unsaid, _ = logic.answers_applied({}, {"stream_near_lot": True}, "R-1b", "one_family_detached", options)
    status = lambda f: next(i["status"] for i in _view(**f)["items"] if "stream" in (i.get("rule") or ""))
    assert status(near) == present.FAILS
    assert status(far) == present.COMPLIES
    assert status(unsaid) == present.REVIEW          # "yes", no distance: still needs review


def test_floor_areas_are_typed_square_feet_not_a_yes_no():
    """The demo found #38's floor-area questions as a No/Yes dropdown once #37 and #38 met: a typed entry (no choices),
    decimals kept, blank = unanswered. They are use details now, so the Enter flow and the box's code path share this."""
    for k in ("home_occupation_area", "home_occupation_unit_area"):
        assert logic.STATED_FACTS[k][1] == "area" and logic.choices_for(k, "area") is None
    assert logic.parse_answer("area", "500.4") == 500.4          # never rounded down to the 500 sq ft limit
    assert logic.parse_answer("area", "  ") is None
    assert logic.update_counts({}, {"home_occupation_area": 500.4})["home_occupation_area"] == 500.4


# ---- review round 1 (two Opus sceptics + a cold reviewer): pins that fail on revert ---------------------------------

def test_a_use_detail_stays_as_answered_whatever_the_district_or_use(options):
    """Use details are facts about the building (who lives there, a home business), the same whatever district or use
    is picked; the box never shows them, so it never changes them (coordinator, 2026-10-28: no answer is ever lost on a
    Use or district pick and back). Where the new district's rules don't read one, it decides nothing (#45's drop of
    those lost the answer and protected no row); where they do, it is the architect's own answer, shown with its
    source. The counts checked together stay together, so a contradiction is never hidden by dropping half of it."""
    facts = {"unrelated_persons": 3, "occupants": 4, "home_occupation": False}
    for zone in ("R-1b", "R-2c", "R-3b"):
        kept, _ = logic.answers_applied(facts, {}, zone, "one_family_detached", options)
        assert kept == facts, zone
    there, _ = logic.answers_applied(facts, {}, "R-3b", "one_family_detached", options)
    back, _ = logic.answers_applied(there, {}, "R-1b", "one_family_detached", options)
    assert back == facts


def test_facts_that_disagree_are_not_filed_as_use_details_to_answer():
    """Sceptic 1: both counts are filled in but disagree; the rows are the architect's contradiction to fix now, not a
    question to answer later."""
    v = _view("R-3a", unrelated_persons=3, unrelated_persons_with_children=2, functional_family_unit=False,
              home_occupation=False)
    conflict = [i for i in v["items"] if i["id"].startswith("facts.conflict")]
    assert conflict and all(i["status"] == present.REVIEW and not i["use_detail"] for i in conflict)
    assert all(not i["use_detail"] for i in v["items"] if i.get("rule") == "R-3a.occupancy_one_family")
    assert "needs review" in v["summary"] or "need review" in v["summary"]
    row = {"status": present.REVIEW, "needs": ["unrelated_persons"], "id": "x"}
    assert logic.is_use_detail(row, {}) and not logic.is_use_detail(row, {"unrelated_persons": 2})
    assert not logic.is_use_detail(dict(row, id="facts.conflict#1"), {})


def test_a_comma_is_a_thousands_separator_only():
    """A European decimal comma ('2,5' ft) must not become 25 (a false pass against 20 ft)."""
    for bad in ("2,5", "1,2,3", "1,0", ",5", "12,34"):
        with pytest.raises(ValueError):
            logic.parse_answer("length", bad)
    assert logic.parse_answer("area", "1,200") == 1200 and logic.parse_answer("area", "1,200.5") == 1200.5
    assert logic.parse_answer("length", ".5") == 0.5


def test_a_quick_answer_sets_all_its_fields_before_the_box_refreshes():
    """Cold review: picking 'No stream, not in South Hill' while the stream said Yes refreshed the box after the first
    field and lost the second. The fields' own refresh is held back while a quick answer fills, then one refresh."""
    from rule_format.rulebook import REPO
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    box = ui[ui.index("def about_section("):ui.index("    layout = ef.DynamicLayout()\n    layout.Spacing")]
    assert "None if filling else refresh_if_needed()" in box
    fill = box[box.index("def quick_picked"):]
    assert fill.index("filling.append(True)") < fill.index("field.SelectedIndex") < fill.index("filling.clear()") \
        < fill.index("refresh_if_needed()")


def test_two_counts_that_are_checked_against_each_other_are_kept_together(options):
    """Round 2 sceptic: R-3a reads only the with-children count, so dropping the other hid the contradiction and the
    rule passed. Both stay, the 'facts disagree' row stays, and nothing passes."""
    both = {"unrelated_persons": 3, "unrelated_persons_with_children": 1, "functional_family_unit": False,
            "home_occupation": False}
    kept, _ = logic.answers_applied(both, {}, "R-3a", "one_family_detached", options)
    assert kept["unrelated_persons"] == 3 and kept["unrelated_persons_with_children"] == 1
    v = _view("R-3a", **kept)
    assert any(i["id"].startswith("facts.conflict") for i in v["items"])
    rule = next(i for i in v["items"] if i.get("rule") == "R-3a.occupancy_one_family")
    assert rule["status"] == present.REVIEW


def test_rooms_let_for_profit_is_a_use_detail_and_the_units_and_conversion_stay_up_front(options):
    """The coordinator for Ben (2026-10-27): rooms rented out is a use detail, asked later like the household and the
    home business; the number of homes and new-or-converted shape the lot area and stay in the start box. R-3a's
    attached-house lot size (R-3a.yaml: 6,000 sf, or 7,000 converted, + 750 a unit over three + 500 a room let for
    profit) reads all three: with the two box answers given it waits only on the rooms, in the use details group,
    needs review (never a pass); answered 0 on a 70 x 150 ft lot (10,500 sf >= 6,000) it complies."""
    asked = logic.follow_up_keys(options, "R-3a", "one_family_attached")
    assert "rooms_let_for_profit" not in asked and "rooms_let_for_profit" not in logic.BOX_ASKS
    assert {"dwelling_units", "conversion"} <= set(asked)
    facts, given = logic.answers_applied({}, {"dwelling_units": 3, "conversion": False, "rooms_let_for_profit": 2},
                                         "R-3a", "one_family_attached", options)
    assert "rooms_let_for_profit" not in given and facts.get("rooms_let_for_profit") is None   # the box never sets it
    rid = "R-3a.lot_area_one_family_attached"
    v = _view("R-3a", "one_family_attached", dwelling_units=3, conversion=False, attached_units_in_building=3)
    row = next(i for i in v["items"] if i["rule"] == rid)
    assert row["status"] == present.REVIEW and row["needs"] == ["rooms_let_for_profit"] and row["use_detail"], row
    assert row["id"] in {g["key"]: g for g in v["groups"]}["use_details"]["items"]
    assert v["state"] != present.COMPLIES
    done = next(i for i in _view("R-3a", "one_family_attached", dwelling_units=3, conversion=False,
                                 attached_units_in_building=3, rooms_let_for_profit=0)["items"] if i["rule"] == rid)
    assert done["status"] == present.COMPLIES and not done["use_detail"], done
