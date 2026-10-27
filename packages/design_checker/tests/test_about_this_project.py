"""The start box's "About this project" section (queue item 14): the facts only the architect knows are asked up front,
only the ones the chosen district's and use's rules need, each with one-click answers and NO default. Unanswered, the
rows that wait on a fact say so exactly as before (never a false pass).

Expected values come from the rulebooks read by hand (R-1b.yaml lines 386-491 for the stream and South Hill rules,
1076 for the household rule, 1262 for the home occupation): R-1b with a one-family house reads exactly these seven
facts; its floor areas and the stream's distance wait on a yes."""

import copy

import pytest

from design_checker import check, present, scenarios
from design_checker import rhino_logic as logic
from design_checker.check import check_site

CITY = "regulations/jurisdictions/new_york/ithaca_city"
R1B_ASKS = ["unrelated_persons", "owner_occupied", "accessory_dwelling_unit", "functional_family_unit",
            "home_occupation", "stream_near_lot", "south_hill_overlay"]


@pytest.fixture(scope="module")
def options():
    return check.options(CITY)


def test_r1b_one_family_asks_exactly_the_facts_its_rules_read(options):
    rows = logic.follow_up_rows(options, "R-1b", "one_family_detached", {})
    assert [r["key"] for r in rows] == R1B_ASKS
    assert all(r["value"] is None for r in rows), "no default: every question starts unanswered"


def test_what_the_drawing_shows_is_never_asked_up_front(options):
    for zone, uses in options["follow_ups"].items():
        for use in uses:
            asked = logic.follow_up_keys(options, zone, use)
            assert not set(asked) & set(logic.DRAWN_FACTS), (zone, use)
            assert not set(asked) & set(logic.INTERIOR_FACTS), (zone, use)


def test_the_floor_areas_and_the_distance_wait_for_their_yes(options):
    ask = lambda facts: [r["key"] for r in logic.follow_up_rows(options, "R-1b", "one_family_detached", facts)]
    base = ask({})
    assert "home_occupation_area" not in base and "stream_distance" not in base
    assert "home_occupation_area" not in ask({"home_occupation": False})
    assert "stream_distance" not in ask({"stream_near_lot": False})
    assert {"home_occupation_area", "home_occupation_unit_area"} <= set(ask({"home_occupation": True}))
    assert "stream_distance" in ask({"stream_near_lot": True})


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
    quick = dict(logic.quick_answers(R1B_ASKS))
    assert quick["1 family, no roomers"] == {"unrelated_persons": 0, "functional_family_unit": False}
    assert quick["No stream, not in South Hill"] == {"stream_near_lot": False, "south_hill_overlay": False}
    assert logic.quick_answers(["stream_near_lot"]) == [("No stream, not in South Hill", {"stream_near_lot": False})]
    assert logic.quick_answers(["occupants"]) == []


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
    """The distance typed before the stream answer flipped to No is dropped, so the facts never disagree."""
    answers = {"stream_near_lot": False, "stream_distance": 5, "home_occupation": False, "home_occupation_area": 300}
    facts, answered = logic.answers_applied({}, answers, "R-1b", "one_family_detached", options)
    assert facts == {"stream_near_lot": False, "home_occupation": False}
    assert answered == ["home_occupation", "stream_near_lot"]
    facts, _ = logic.answers_applied({}, {**answers, "stream_near_lot": True}, "R-1b", "one_family_detached", options)
    assert facts["stream_distance"] == 5


def test_the_box_reopens_when_a_yes_opens_a_question(options):
    shown = ("R-1b", "one_family_detached", logic.gate_of({}))
    assert not logic.box_needs_refresh(options, shown, ("R-1b", "one_family_detached", logic.gate_of({"stream_near_lot": False})))
    assert logic.box_needs_refresh(options, shown, ("R-1b", "one_family_detached", logic.gate_of({"stream_near_lot": True})))
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


def test_the_box_asks_every_stated_fact_a_review_row_waits_on(options):
    """In every district, the stated facts the rows wait on (with nothing answered) are all ones the box asks, so a
    single visit to the box can clear them (the interior's and the drawn ones are asked elsewhere)."""
    for zone in options["zones"]:
        rows = _rows(zone)
        waiting = {k for i in rows.values() if i["status"] == present.REVIEW for k in i.get("needs") or []}
        outside = waiting & set(logic.STATED_FACTS) - set(logic.BOX_ASKS) - {"stories"}
        assert not outside - set(logic.INTERIOR_FACTS) - set(logic.DRAWN_FACTS), (zone, outside)
        missing = (waiting & set(logic.BOX_ASKS)) - set(logic.follow_up_keys(options, zone, "one_family_detached"))
        assert not missing, (zone, missing)


def test_unanswered_still_needs_review_and_answering_decides_the_row(options):
    rows = _rows()
    for rule, fact in (("R-1b.stream_setback" if "R-1b.stream_setback" in rows else None, "stream_near_lot"),):
        pass
    waiting = {k for i in rows.values() if i["status"] == present.REVIEW for k in i.get("needs") or []}
    # (the South Hill row is shown only with a second primary building: R-1b.south_hill_overlay applies_when)
    assert {"stream_near_lot", "unrelated_persons", "home_occupation"} <= waiting, waiting
    answers = {"unrelated_persons": 0, "owner_occupied": True, "accessory_dwelling_unit": False,
               "functional_family_unit": False, "home_occupation": False, "stream_near_lot": False,
               "south_hill_overlay": False}
    facts, _ = logic.answers_applied({}, answers, "R-1b", "one_family_detached", options)
    after = _rows(**facts)
    still = {k for i in after.values() if i["status"] == present.REVIEW for k in i.get("needs") or []}
    assert not still & set(answers), still
    # one answer at a time clears only its own rows: the others stay needs review
    one, _ = logic.answers_applied({}, {"stream_near_lot": False}, "R-1b", "one_family_detached", options)
    left = {k for i in _rows(**one).values() if i["status"] == present.REVIEW for k in i.get("needs") or []}
    assert "stream_near_lot" not in left and {"unrelated_persons", "home_occupation"} <= left


def test_a_close_stream_is_a_fail_and_a_far_one_a_pass_once_the_distance_is_typed(options):
    near, _ = logic.answers_applied({}, {"stream_near_lot": True, "stream_distance": 19.96}, "R-1b",
                                    "one_family_detached", options)
    far, _ = logic.answers_applied({}, {"stream_near_lot": True, "stream_distance": 20}, "R-1b",
                                   "one_family_detached", options)
    unsaid, _ = logic.answers_applied({}, {"stream_near_lot": True}, "R-1b", "one_family_detached", options)
    status = lambda f: next(i["status"] for r, i in _rows(**f).items() if "stream" in r)
    assert status(near) == present.FAILS
    assert status(far) == present.COMPLIES
    assert status(unsaid) == present.REVIEW          # "yes", no distance: still needs review


def test_floor_areas_are_typed_square_feet_not_a_yes_no(options):
    """The demo found #38's floor-area questions as a No/Yes dropdown once #37 and #38 met: they are typed entries
    (no choices), decimals kept, blank = unanswered (the rule needs review)."""
    rows = {r["key"]: r for r in logic.follow_up_rows(options, "R-1b", "one_family_detached", {"home_occupation": True})}
    for k in ("home_occupation_area", "home_occupation_unit_area"):
        assert rows[k]["kind"] == "area" and rows[k]["choices"] is None, rows[k]
    assert logic.parse_answer("area", "500.4") == 500.4          # never rounded down to the 500 sq ft limit
    assert logic.parse_answer("area", "  ") is None
    facts, _ = logic.answers_applied({}, {"home_occupation": True, "home_occupation_area": 500.4}, "R-1b",
                                     "one_family_detached", options)
    assert facts["home_occupation_area"] == 500.4 and "home_occupation_unit_area" not in facts
