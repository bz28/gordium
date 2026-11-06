"""The start box's Use and its follow-up questions (Ben, 2026-10-25): the uses the district's chart lists, and only
the facts this district's rules need for the use, derived from the rulebook (no hand-kept list), each answer saved
as entered by you; unanswered, the rule that needs it says so and never passes."""

import json

import pytest

from design_checker import present
from design_checker import rhino_logic as logic
from design_checker.check import follow_up_facts, implied_for, options, use_choices
from rule_format.rulebook import REPO, outcome
from host_source import host_text

CITY = "regulations/jurisdictions/new_york/ithaca_city"
NAMES = {"one_family_detached": "One-family dwelling, detached", "one_family_attached": "One-family dwelling, attached",
         "two_family": "Two-family dwelling", "multiple_family": "Multiple family dwelling", "school": "School"}
# the checker's kinds for the facts (measures.yaml names them on the R-3a stack; described by kind here)
USES = {"use": set(NAMES), "dwelling_units": "number", "rooms_let_for_profit": "number", "conversion": "boolean"}
# R-3a's lot-size rule for a multiple dwelling and for attached one-family dwellings, as written in its hand rulebook
# (r3-hand, chart p.3 note 7): the lot grows with the units past three, each room let for profit, and a conversion
LOT_SIZE = "lot_area >= (7000 if conversion else 6000) + 750 * max(dwelling_units - 3, 0) + 500 * rooms_let_for_profit"
# an R-3aa-like district: the use rule lists the permitted uses in its check, the special-permit ones in review_when
X = [{"id": "X.use", "kind": "rule", "topic": "uses",
      "check": 'use in ["one_family_detached", "one_family_attached", "two_family", "multiple_family"]',
      "review_when": [{"when": 'use in ["school"]', "reason": "Marked SP for X on the zoning chart (p.2). Other."}],
      "sources": [{"file": "zoning_charts_2026-04.pdf", "page": 2}]},
     {"id": "X.lot_mf", "kind": "rule", "applies_when": 'use == "multiple_family"', "check": LOT_SIZE},
     {"id": "X.lot_att", "kind": "rule", "applies_when": 'use == "one_family_attached"', "check": LOT_SIZE},
     {"id": "X.units", "kind": "rule", "applies_when": 'use in ["one_family_detached", "two_family"]',
      "check": "dwelling_units <= 2"},
     {"id": "X.parking", "kind": "rule", "check": "parking_spaces >= 1 + sleeping_rooms"},
     {"id": "X.stories", "kind": "rule", "check": "stories <= 3"}]
# an R-3a-like district: its use rule is a flag on the special-permit uses, every other listed use permitted
FLAG = [{"id": "F.use", "kind": "flag", "topic": "uses", "title": "Uses by special permit (chart p.2)",
         "applies_when": 'use in ["school"]', "sources": [{"file": "zoning_charts_2026-04.pdf", "page": 2}]}]


def _opts(rules=X, zone="X"):
    choices = use_choices(rules, NAMES, zone)
    return {"zones": [zone], "uses": NAMES, "district_uses": {zone: choices},
            "follow_ups": {zone: {u["id"]: follow_up_facts(rules, u["id"], NAMES) for u in choices}},
            "implied": {zone: {u["id"]: implied_for(rules, u["id"], NAMES) for u in choices}}}


def test_the_use_dropdown_lists_the_districts_chart_uses_permitted_first_and_says_what_isnt():
    got = use_choices(X, NAMES, "X")
    assert [(u["id"], u["permitted"]) for u in got] == [
        ("one_family_detached", True), ("one_family_attached", True), ("two_family", True),
        ("multiple_family", True), ("school", False)]
    assert got[-1]["note"] == "Not permitted by right in X: Marked SP for X on the zoning chart (p.2)."
    # a flag on the special-permit uses (R-3a's hand rulebook): every other city use permitted, the flagged ones said
    flag = use_choices(FLAG, NAMES, "F")
    assert [(u["id"], u["permitted"]) for u in flag] == [(k, k != "school") for k in NAMES if k != "school"] + [
        ("school", False)]
    assert flag[-1]["note"] == "Not permitted by right in F: by special permit (zoning chart p.2)."
    assert [u["permitted"] for u in use_choices([], NAMES, "Y")] == [None] * len(NAMES)    # no use rule: all, unmarked
    city = options(CITY)                                          # R-1b's own chart row, from its rulebook
    r1b = city["district_uses"]["R-1b"]
    assert [u["id"] for u in r1b if u["permitted"]] == ["one_family_detached", "church", "public_park_or_playground",
                                                         "library_or_fire_station"]
    assert [u["id"] for u in r1b if not u["permitted"]] == ["cemetery", "public_utility_structure", "school"]
    assert all(u["note"].startswith("Not permitted by right in R-1b: Marked SP") for u in r1b if not u["permitted"])
    assert logic.district_use_names(city, "R-1b")[0] == ("one_family_detached", "One-family dwelling, detached")
    assert logic.use_note(city, "R-1b", "school").endswith("(p.2).") and logic.use_note(city, "R-1b", "church") is None
    assert json.loads(json.dumps(city)) == city                   # it crosses to Rhino as JSON, unchanged


def test_a_use_the_district_doesnt_list_stays_picked_and_is_said():
    """A project saved as two-family, its district now R-1b (the chart: not listed): the box keeps the use (never
    switched to the first in the list, unasked) and says its Use row won't comply."""
    city = options(CITY)
    names = logic.district_use_names(city, "R-1b", "two_family")
    assert names[-1] == ("two_family", "Two-family dwelling") and len(names) == len(city["district_uses"]["R-1b"]) + 1
    assert logic.district_use_names(city, "R-1b", "school") == logic.district_use_names(city, "R-1b")   # listed: once
    assert logic.use_note(city, "R-1b", "two_family") == (
        "Two-family dwelling isn't on R-1b's list of uses in the zoning chart: its Use row won't comply.")
    ui = host_text("rhino", "ui", purpose="wiring")
    box = ui[ui.index("def start_box("):ui.index("def text_box_size(")]
    assert 'logic.district_use_names(options, state.get("zone"), state.get("use"))' in box
    rhino = host_text("rhino", "plugin", purpose="wiring")
    state = rhino[rhino.index("def _box_state("):rhino.index("def _ft_text(")]
    assert '"use_choices": logic.district_use_names(options, facts.get("zone"), facts.get("use"))' in state


def test_only_the_facts_this_districts_rules_need_for_the_use_are_asked():
    """A multiple dwelling: units, rooms let for profit, new or conversion. One-family detached and two-family say
    their units (§325-3), so never asked; parking's and the interior's facts never (on hold); the stories are
    measured."""
    assert follow_up_facts(X, "multiple_family", NAMES) == ["dwelling_units", "rooms_let_for_profit", "conversion"]
    assert follow_up_facts(X, "one_family_detached", NAMES) == []
    assert implied_for(X, "one_family_detached", NAMES) == {"dwelling_units": 1}
    assert implied_for(X, "two_family", NAMES) == {"dwelling_units": 2}
    assert implied_for(X, "school", NAMES) == {}                  # no rule reads its units: nothing sent
    city = options(CITY)
    # R-1b's rules read no unit counts, rooms let or conversion (they read #38's household and home-occupation facts,
    # asked in "About this project"): so nothing is implied for a use, nothing is sent the checker can't use
    unit_facts = {"dwelling_units", "rooms_let_for_profit", "conversion"}
    assert not any(unit_facts & set(v) for v in city["follow_ups"]["R-1b"].values())
    assert all(v == {} for v in city["implied"]["R-1b"].values())


def test_an_attached_dwellings_units_are_asked_never_taken_as_one():
    """A one-family ATTACHED dwelling is one unit of a row the lot-size rule counts as a whole: its units are asked
    (the old prefix match took them as 1, so a row of six on a lot sized for three passed)."""
    assert logic.implied_facts("one_family_attached") == {} and logic.implied_facts("one_family_semi_detached") == {}
    assert follow_up_facts(X, "one_family_attached", NAMES) == ["dwelling_units", "rooms_let_for_profit", "conversion"]
    opts = _opts()
    # rooms let for profit is a use detail (rhino_logic.DEFERRED_FACTS): answered in the panel, so it is in the facts
    # already; the box answers the units and the conversion
    facts, _ = logic.answers_applied({"use": "one_family_attached", "lot_area": 6500, "rooms_let_for_profit": 0},
                                     {"conversion": False}, "X", "one_family_attached", opts)
    assert "dwelling_units" not in facts
    assert outcome(X[2], facts, USES) == "needs_review"           # units unanswered: never a pass
    facts, _ = logic.answers_applied(facts, {"dwelling_units": 6, "conversion": False},
                                     "X", "one_family_attached", opts)
    assert outcome(X[2], facts, USES) == "fail"                   # 6,000 + 750 x 3 = 8,250 sf needed, 6,500 given


@pytest.mark.parametrize("answers, lot, expected", [
    ({}, 9000, "needs_review"),                                                          # nothing answered
    ({"dwelling_units": 4, "rooms_let_for_profit": 0}, 9000, "needs_review"),            # conversion unanswered
    ({"dwelling_units": 4, "rooms_let_for_profit": 0, "conversion": False}, 6750, "pass"),   # 6,000 + 750 = 6,750
    ({"dwelling_units": 4, "rooms_let_for_profit": 0, "conversion": False}, 6749, "fail"),
    ({"dwelling_units": 5, "rooms_let_for_profit": 1, "conversion": True}, 9000, "pass"),    # 7,000 + 1,500 + 500
    ({"dwelling_units": 5, "rooms_let_for_profit": 1, "conversion": True}, 8999, "fail"),
])
def test_the_answers_decide_the_rule_and_a_blank_never_passes(answers, lot, expected):
    """End to end through the checker's own verdict (outcome): the box's answers become the facts; an unanswered
    one leaves the rule needing review even on a lot big enough for any answer. Expected sizes by hand from note 7."""
    # rooms let for profit is a use detail answered in the panel (DEFERRED_FACTS): already in the facts, never the box's
    rooms = {k: answers[k] for k in ("rooms_let_for_profit",) if k in answers}
    box = {k: v for k, v in answers.items() if k not in rooms}
    facts, _ = logic.answers_applied({"use": "multiple_family", "lot_area": lot, **rooms}, box, "X", "multiple_family",
                                     _opts())
    assert outcome(X[1], facts, USES) == expected


def test_an_answer_for_another_use_or_district_never_stays_behind():
    opts = _opts()
    five, answered = logic.answers_applied({"use": "multiple_family"}, {"dwelling_units": 5, "conversion": True},
                                           "X", "multiple_family", opts)
    assert five["dwelling_units"] == 5 and answered == ["conversion", "dwelling_units"]
    # now two-family: its own 2 units (the definition), never the 5 typed for the multiple dwelling
    two, answered = logic.answers_applied(dict(five, use="two_family"), {"dwelling_units": 5, "conversion": True},
                                          "X", "two_family", opts)
    assert two["dwelling_units"] == 2 and answered == ["conversion"]
    # the conversion answer stays stored (P0, 2026-10-28: the box changes only what it shows), never read unshown:
    # no rule of X reads it for a two-family, so it isn't asked
    assert two["conversion"] is True and "conversion" not in logic.follow_up_keys(opts, "X", "two_family")
    # and back to a multiple dwelling: the two-family's own 2 units go (never an architect's count); conversion kept
    back, _ = logic.answers_applied(two, {}, "X", "multiple_family", opts)
    assert "dwelling_units" not in back and back["conversion"] is True
    assert outcome(X[3], two, USES) == "pass"
    # another district that asks nothing: the answers stay stored, unread and unshown (test_answers_survive_…)
    kept, _ = logic.answers_applied(five, {"dwelling_units": 5}, "R-1b", "one_family_detached", options(CITY))
    assert (kept["dwelling_units"], kept["conversion"]) == (5, True)
    # a blank or a refused entry: unset, never 0 or no; facts the box doesn't ask are kept as they were
    kept, answered = logic.answers_applied({"use": "multiple_family", "dwelling_units": 5, "sleeping_rooms": 3,
                                            "stories": 2}, {"dwelling_units": None, "conversion": False},
                                           "X", "multiple_family", opts)
    assert kept == {"use": "multiple_family", "sleeping_rooms": 3, "stories": 2, "conversion": False}
    assert answered == ["conversion"]


def test_the_box_opens_again_only_when_the_use_or_district_changes_what_it_shows():
    opts = _opts()
    assert logic.box_needs_refresh(opts, ("X", "one_family_detached"), ("X", "multiple_family"))     # questions
    assert logic.box_needs_refresh(opts, ("X", "one_family_detached"), ("X", "school"))              # the SP note
    assert not logic.box_needs_refresh(opts, ("X", "one_family_detached"), ("X", "two_family"))      # same rows
    city = dict(options(CITY), zones=["R-1b", "X"])
    city = {k: ({**v, **opts[k]} if isinstance(v, dict) and k != "uses" else v) for k, v in city.items()}
    assert logic.box_needs_refresh(city, ("R-1b", "one_family_detached"), ("X", "one_family_detached"))  # its uses
    ui = host_text("rhino", "ui", purpose="wiring")
    box = ui[ui.index("def start_box("):ui.index("def text_box_size(")]
    assert "logic.box_needs_refresh(" in box and 'pick("refresh")' in box
    assert box.count("        refresh_if_needed()\n") == 3       # the district, the use, and the quick answers (a yes opens a question)
    rhino = host_text("rhino", "plugin", purpose="wiring")
    loop = rhino[rhino.index("def _box_loop("):rhino.index("def _lookup_start(")]
    assert 'if what != "pick:refresh":' in loop                    # a refresh is no pick in the model


def test_the_box_rows_answers_and_their_source():
    opts = {"follow_ups": {"X": {"multiple_family": ["dwelling_units", "conversion"]}},
            "implied": {"X": {"two_family": {"dwelling_units": 2}}}}
    rows = logic.follow_up_rows(opts, "X", "multiple_family", {"dwelling_units": 4})
    assert [(r["key"], r["kind"], r["value"]) for r in rows] == [("dwelling_units", "count", 4),
                                                                 ("conversion", "yes_no", None)]
    assert logic.follow_up_rows(opts, "X", "two_family", {}) == []
    assert logic.yes_no_words("conversion") == ("New construction", "Conversion of an existing building")
    assert logic.yes_no_words("anything_else") == ("No", "Yes")
    assert logic.parse_answer("count", " 5 ") == 5 and logic.parse_answer("count", "") is None
    assert logic.parse_answer("yes_no", "yes") is True and logic.parse_answer("yes_no", "") is None
    for bad in ("-1", "2.5", "lots", "٣"):
        with pytest.raises(ValueError):
            logic.parse_answer("count", bad)
        assert logic.answer_problem("count", bad) == "Not kept: a whole number, 0 or more. Its rules need review " \
                                                     "until it is."
    assert logic.answer_problem("count", "3") is None and logic.answer_problem("count", "") is None
    # Draw saves each answer as entered by you, and what the use says as the use's (exactly the facts sent)
    state = {"zone": "X", "use": "multiple_family", "options": opts,
             "answers": {"dwelling_units": 5, "conversion": False}}
    sources = logic.fact_sources(state, "2026-10-26", True)
    assert sources["dwelling_units"]["source"] == logic.ENTERED and sources["conversion"]["value"] == "no"
    lines = present.source_lines(sources)
    assert any(line.startswith("Dwelling units: 5 · entered by you") for line in lines), lines
    two = logic.fact_sources(dict(state, use="two_family"), "2026-10-26", True)
    assert two["dwelling_units"] == {"value": 2, "source": logic.IMPLIED_SOURCE, "confirmed_by": "you",
                                     "date": "2026-10-26"}          # the use's, never the 5 shown before
    assert two["conversion"]["source"] == logic.ENTERED              # a field shown: the architect's, kept
    # an earlier answer's source never outlives its fact; one kept (not shown for this use) keeps its source
    saved = {"zone": {"value": "X"}, "dwelling_units": {"value": 5}, "conversion": {"value": "no"},
             "ground_marked": {"value": "1 object"}}
    assert logic.sources_kept(saved, {"zone": "X"}) == {"zone": {"value": "X"}, "ground_marked": {"value": "1 object"}}
    assert logic.sources_kept(saved, {"zone": "X", "conversion": False}) == {
        "zone": {"value": "X"}, "ground_marked": {"value": "1 object"}, "conversion": {"value": "no"}}
    # a use detail's (rooms let for profit, #45): its source goes with its fact, and stays while it is set (the row
    # dialog that answers it now saves its "entered by you": row_sources)
    rooms = {**saved, "rooms_let_for_profit": {"value": 2}}
    assert logic.sources_kept(rooms, {"zone": "X"}) == logic.sources_kept(saved, {"zone": "X"})
    assert logic.sources_kept(rooms, {"rooms_let_for_profit": 2})["rooms_let_for_profit"] == {"value": 2}
    rhino = host_text("rhino", "plugin", purpose="wiring")
    drawn = rhino[rhino.index("def _drawn("):rhino.index("def hide_massing(")]
    assert "logic.sources_kept(fact_sources(doc), out)" in drawn


def test_an_unanswered_fact_says_what_it_needs_and_its_button_opens_its_own_dialog():
    """Coordinator, 2026-10-28 (agreed with Ben): a row waiting on stated facts no longer opens the whole start box
    ("Tell Gordium in Edit site…", gone): its one button opens a small dialog asking exactly those facts."""
    assert logic.needs_reason(["dwelling_units"]) == "Needs dwelling units, which the model doesn't show"
    assert logic.needs_reason(["sleeping_rooms", "parking_spaces"]) == (
        "Needs bedrooms and parking spaces, which the model doesn't show")
    assert logic.needs_reason([]) is None
    assert logic.row_buttons({"needs": ["dwelling_units", "conversion"]}) == [
        ("Answer 2 questions…", "enter")]           # too long for a button: how many (answer_words)
    assert logic.row_buttons({"needs": ["sleeping_rooms", "parking_spaces"]}) == [
        ("Enter bedrooms and parking spaces…", "enter")]
    ui = host_text("rhino", "ui", purpose="wiring")
    assert "Tell Gordium in Edit site" not in ui and not hasattr(logic, "answered_in_box")
    detail = ui[ui.index("def show_detail("):ui.index("def row_dialog(")]
    assert "for words, what in logic.row_buttons(i):" in detail
    assert 'buttons.append(button(words, lambda: a["enter"](i["needs"])))' in detail
    assert 'buttons.append(button(words, a["edit_site"]))' in detail
    ui_box = ui[ui.index("def start_box("):ui.index("def row_dialog(")]
    assert 'questions = state.get("follow_ups") or []' in ui_box and 'for q in questions:' in ui_box
    assert 'state["answers"] = answers' in ui_box
    assert "about_section(layout, questions)" in ui_box and '"About this project"' in ui_box   # the compact section
    assert "logic.answers_note(" in ui_box and "note.Text = text" in ui_box     # a refused entry is said at once
    rhino = host_text("rhino", "plugin", purpose="wiring")
    apply_ = rhino[rhino.index("def _apply_box("):rhino.index("def _place_spots(")]
    assert 'logic.box_applied(facts, state.get("answers"), state["zone"], state["use"], state.get("options"),' \
        in apply_
    state = rhino[rhino.index("def _box_state("):rhino.index("def _ft_text(")]
    assert '"follow_ups": logic.follow_up_rows(options, facts.get("zone"), facts.get("use"), facts)' in state


def test_a_condition_false_for_the_use_never_asks_its_facts(monkeypatch):
    """Review rounds 1-2: RU's 500 ft spacing applies to a multiple dwelling, a group house or a dormitory "and not
    conversion". The box asks its facts exactly when the checker's own verdict (outcome) may find it applicable:
    with "conversion" typed (as measures.yaml types it on the R-3a stack) a one-family house is never asked it and
    the rule is not applicable to it; a dormitory is asked. Untyped (this branch's measures.yaml), the checker can't
    settle it either, so it is asked: never a needs-review row the box can't answer."""
    import design_checker.check as check_mod
    from rule_format import rulebook
    spacing = {"id": "RU.spacing_500_ft", "kind": "rule",
               "applies_when": 'use in ["multiple_family", "fraternity_sorority_group_house", "dormitory"] and '
                               "not conversion", "check": "front_yard >= 0"}
    names = dict(NAMES, dormitory="Dormitory", fraternity_sorority_group_house="Group house")

    def agree():
        for use in names:
            asked = "conversion" in follow_up_facts([spacing], use, names)
            verdict = outcome(spacing, {"use": use, "front_yard": 30}, {"use": set(names)})
            assert asked == (verdict != "not_applicable"), (use, asked, verdict)

    agree()
    typed = rulebook.MEASURE_KINDS | {"conversion": "boolean"}
    monkeypatch.setattr(check_mod, "MEASURE_KINDS", typed)
    monkeypatch.setattr(rulebook, "MEASURE_KINDS", typed)
    agree()
    assert follow_up_facts([spacing], "one_family_detached", names) == []
    assert follow_up_facts([spacing], "dormitory", names) == ["conversion"]
    # a saved use the district doesn't list still gets its own questions (never a row the box can't answer)
    city = options(CITY)
    assert set(city["follow_ups"]["R-1b"]) == set(city["uses"]) == set(city["implied"]["R-1b"])


def test_the_box_reopens_with_the_pick_it_was_laid_out_for():
    """Review round 1, F1: the refresh compares with what the Use rows were laid out for; that name is set once in
    start_box (the test hook's own name rebound it, so every pick raised inside the guard and the box never
    opened again)."""
    import re
    ui = host_text("rhino", "ui", purpose="wiring")
    box = ui[ui.index("def start_box("):ui.index("def text_box_size(")]
    assert "                options, laid_out, (z, names[use.SelectedIndex][0]" in box
    assert len(re.findall(r"^\s+laid_out = ", box, re.M)) == 1


def test_rhino_logic_names_each_thing_once():
    """#26 and #37 each defined NOT_ANSWERED and _listed in rhino_logic: merged, the later one won, so the yes / no
    dropdown's first entry read "The lookup of {address} didn't finish…" and the Use list raised (found in the demo
    build; here in #37's merge-3 carry). Every top-level name is defined once."""
    import ast
    import collections
    tree = ast.parse(host_text("rhino", "logic", purpose="wiring"))
    names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    names += [t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)]
    assert [n for n, k in collections.Counter(names).items() if k > 1] == []
    assert logic.NOT_ANSWERED == "Not answered"
    assert logic._listed({"district_uses": {"R-1b": [1]}}, "R-1b") == [1] and logic._joined(["a", "b"]) == "a and b"
