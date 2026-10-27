"""The start box's Use and its follow-up questions (Ben, 2026-10-25): the uses the district's chart lists, and only
the facts this district's rules need for the use, derived from the rulebook (no hand-kept list), each answer saved
as entered by you; unanswered, the rule that needs it says so and never passes."""

from design_checker import present
from design_checker import rhino_logic as logic
from design_checker.check import follow_up_facts, implied_for, options, use_choices
from rule_format.rulebook import REPO

CITY = "regulations/jurisdictions/new_york/ithaca_city"
NAMES = {"one_family_detached": "One-family dwelling, detached", "two_family": "Two-family dwelling",
         "multiple_dwelling": "Multiple dwelling", "school": "School"}
# an R-3a-like district (its note 7: a lot size that grows with the units, the rooms let and a conversion)
R3 = [{"id": "X.use", "topic": "uses", "check": 'use in ["one_family_detached", "two_family", "multiple_dwelling"]',
       "review_when": [{"when": 'use in ["school"]', "reason": "Marked SP for X on the zoning chart (p.2). Other."}],
       "sources": [{"file": "zoning_charts_2026-04.pdf", "page": 2}]},
      {"id": "X.lot", "applies_when": 'use == "multiple_dwelling"', "check": "lot_area >= 6000",
       "review_when": [{"when": "dwelling_units > 3 or rooms_let_for_profit > 0 or conversion", "reason": "note 7"}]},
      {"id": "X.units", "applies_when": 'use in ["one_family_detached", "two_family"]', "check": "dwelling_units <= 2"},
      {"id": "X.parking", "check": "parking_spaces >= 1 + sleeping_rooms"},
      {"id": "X.stories", "check": "stories <= 3"}]


def test_the_use_dropdown_lists_the_districts_chart_uses_permitted_first_and_says_what_isnt():
    got = use_choices(R3, NAMES, "X")
    assert [(u["id"], u["permitted"]) for u in got] == [("one_family_detached", True), ("two_family", True),
                                                        ("multiple_dwelling", True), ("school", False)]
    assert got[3]["note"] == "Not permitted by right in X: Marked SP for X on the zoning chart (p.2)."
    city = options(CITY)                                          # R-1b's own chart row, from its rulebook
    r1b = city["district_uses"]["R-1b"]
    assert [u["id"] for u in r1b if u["permitted"]] == ["one_family_detached", "church", "public_park_or_playground",
                                                         "library_or_fire_station"]
    assert all(u["note"].startswith("Not permitted by right in R-1b: Marked SP") for u in r1b if not u["permitted"])
    assert logic.district_use_names(city, "R-1b")[0] == ("one_family_detached", "One-family dwelling, detached")
    assert logic.use_note(city, "R-1b", "school").endswith("(p.2).") and logic.use_note(city, "R-1b", "church") is None


def test_only_the_facts_this_districts_rules_need_for_the_use_are_asked():
    """R-3a + multiple dwelling: units, rooms let for profit, new or conversion; one-family and two-family say their
    units (never asked); parking's and the interior's facts never (on hold); the stories are measured."""
    assert follow_up_facts(R3, "multiple_dwelling", NAMES) == ["dwelling_units", "rooms_let_for_profit", "conversion"]
    assert follow_up_facts(R3, "one_family_detached", NAMES) == []         # its units: the use says 1
    assert implied_for(R3, "one_family_detached", NAMES) == {"dwelling_units": 1}
    assert implied_for(R3, "two_family", NAMES) == {"dwelling_units": 2}
    assert implied_for(R3, "school", NAMES) == {}                           # (a school: no units rule reads it)
    city = options(CITY)
    assert all(v == [] for v in city["follow_ups"]["R-1b"].values())       # R-1b's rules need none of them today
    assert all(v == {} for v in city["implied"]["R-1b"].values())          # so nothing is sent the checker can't use


def test_the_box_rows_answers_and_their_source():
    opts = {"follow_ups": {"X": {"multiple_dwelling": ["dwelling_units", "conversion"]}},
            "implied": {"X": {"two_family": {"dwelling_units": 2}}}}
    rows = logic.follow_up_rows(opts, "X", "multiple_dwelling", {"dwelling_units": 4})
    assert [(r["key"], r["kind"], r["value"]) for r in rows] == [("dwelling_units", "count", 4), ("conversion", "yes_no", None)]
    assert logic.follow_up_rows(opts, "X", "two_family", {}) == []
    assert logic.parse_answer("count", " 5 ") == 5 and logic.parse_answer("count", "") is None
    assert logic.parse_answer("yes_no", "yes") is True and logic.parse_answer("yes_no", "") is None
    for bad in ("-1", "2.5", "lots"):
        try:
            logic.parse_answer("count", bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    facts, answered = logic.answers_applied({"use": "multiple_dwelling", "conversion": True},
                                            {"dwelling_units": 5, "conversion": None})
    assert facts == {"use": "multiple_dwelling", "dwelling_units": 5} and answered == ["dwelling_units"]   # blank: unset
    facts, _ = logic.answers_applied({"use": "two_family"}, {}, logic.implied_by(opts, "X", "two_family"))
    assert facts["dwelling_units"] == 2
    sources = logic.fact_sources({"answers": {"dwelling_units": 5, "conversion": False}}, "2026-10-26", True)
    assert sources["dwelling_units"]["source"] == logic.ENTERED and sources["conversion"]["value"] == "no"
    lines = present.source_lines(sources)
    assert any(line.startswith("Dwelling units: 5 · entered by you") for line in lines), lines


def test_an_unanswered_fact_says_tell_gordium_and_its_button_opens_the_box():
    assert logic.needs_reason(["dwelling_units"]).startswith("Tell Gordium the dwelling units (Edit site…)")
    assert logic.answered_in_box(["dwelling_units", "conversion"]) and not logic.answered_in_box(["sleeping_rooms"])
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert 'if i.get("needs") and logic.answered_in_box(i["needs"]):' in ui and 'a["edit_site"]' in ui
    box = ui[ui.index("def start_box("):ui.index("def text_box_size(")]
    assert 'names = list(state.get("use_choices") or options["uses"].items())' in box
    assert 'for q in state.get("follow_ups") or []:' in box and 'state["answers"] = answers' in box
    assert 'pick("refresh")' in box                               # another use: its own questions
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    apply_ = rhino[rhino.index("def _apply_box("):rhino.index("def _place_spots(")]
    assert "logic.answers_applied(facts, state.get(\"answers\")," in apply_
    state = rhino[rhino.index("def _box_state("):rhino.index("def _ft_text(")]
    assert '"follow_ups": logic.follow_up_rows(options, facts.get("zone"), facts.get("use"), facts)' in state
