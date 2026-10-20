"""The rule-drafting script with a fake API client: no key, no network, no money. Includes the budget cap.

The answers below stand in for the AI's; what's tested is the code around it: chart numbers filled from
each district's own cell (never typed), cells of another shape sent to a person, quotes resolved to their
exact lines, bad answers sent back, every call recorded, and the answer key (R-1b.yaml) never shown.
"""

import copy
import re
import json
import sys
from types import SimpleNamespace

import pytest

from rule_drafting import __main__ as cli
from rule_drafting import chart_values, drafter
from rule_drafting.templates import SLOT, fill_template
from section_labeling.budget import Budget, BudgetExceeded

USAGE = {"input_tokens": 900, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 9000, "output_tokens": 700}
YARDS = "Yard Dimensions"
REAR = "Rear (minimum, % of depth or feet, whichever is less)"


class FakeClient:
    """Answers each create() with the next canned answer; counts tokens as len // 4."""

    def __init__(self, *answers, stop="end_turn"):
        self.answers, self.stop, self.requests = list(answers), stop, []
        self.messages = self

    def create(self, **request):
        self.requests.append(copy.deepcopy(request))
        text = json.dumps(self.answers.pop(0))
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=self.stop,
                               usage=SimpleNamespace(**USAGE), _request_id="req_test")

    def count_tokens(self, model, messages, system="", output_config=None):
        self.counted = getattr(self, "counted", []) + [{"system": system, "output_config": output_config}]
        return SimpleNamespace(input_tokens=(len(system) + sum(len(m["content"]) for m in messages)) // 4)


@pytest.fixture(autouse=True)
def no_sdk(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)


@pytest.fixture(scope="module")
def inputs():
    return cli.Inputs()


def slot(name, row, number=1, count=1, percent=False, footnotes=(), page=3, section=YARDS):
    return {"name": name, "page": page, "section": section, "row": row, "number": number, "numbers_in_cell": count,
            "percent": percent, "footnotes": list(footnotes)}


def template(suffix, check, slots, examples, quotes=(), kind="rule", applies_when="", new_measures=(), numbers=()):
    return {"id_suffix": suffix, "title": suffix.replace("_", " ").capitalize(), "topic": "dimensions", "kind": kind,
            "applies_when": applies_when, "check": check, "slots": slots, "review_when": [], "quotes": list(quotes),
            "numbers": list(numbers),
            "examples": [{"given": [{"measure": m, "value": v} for m, v in g.items()], "expect": e} for g, e in examples],
            "open_questions": [], "new_measures": list(new_measures)}


def bound(value, source, quote=-1, slot="", footnote=""):
    """One entry of a template's numbers: where a typed number is written."""
    return {"value": value, "from": source, "quote": quote, "slot": slot, "footnote": footnote}


FRONT = template("front_yard", "front_yard >= {front}", [slot("front", "Front (minimum)")],
                 [({"front_yard": "{front}"}, "pass"), ({"front_yard": "{front} - 1"}, "fail")])
REAR_YARD = template(
    "rear_yard", "rear_yard >= max(min({pct} * lot_depth, {cap}), 20)",
    [slot("pct", REAR, 1, 2, True, ["16"]), slot("cap", REAR, 2, 2, False, ["16"])],
    # each slot binds in some example: the percent on a 100 ft lot, the 50 ft cap on a 400 ft lot
    [({"rear_yard": "25", "lot_depth": "100"}, "pass"), ({"rear_yard": "50", "lot_depth": "400"}, "pass"),
     ({"rear_yard": "19", "lot_depth": "60"}, "fail")],
    quotes=[{"document": "chart", "page": 3, "piece": "", "text": "(16) But not less than 20 ft."}],
    numbers=[bound(20, "slot_footnote", slot="cap", footnote="16")])


def unit(inputs, uid):
    return next(u for u in inputs.units() if u["id"] == uid)


def run(inputs, client, uid="chart-p3-yard_dimensions", budget=None, records=None):
    u, records = unit(inputs, uid), [] if records is None else records
    context = drafter.gather_context(u, inputs.law, {"notes": inputs.notes}, inputs.definitions)
    result = drafter.draft_unit(client, u, context, "SYSTEM", inputs.law, inputs.ctx, inputs.columns, inputs.cells,
                                inputs.notes, records.append, budget=budget)
    return result, records


def test_chart_numbers_are_filled_from_each_districts_own_cell(inputs):
    result, records = run(inputs, FakeClient({"templates": [FRONT], "no_rule_reason": ""}))
    checks = {d: rules[0]["check"] for d, rules in result["rules"].items()}
    assert checks["R-1b"] == "front_yard >= 25" and checks["R-2b"] == "front_yard >= 10" and len(checks) == 9
    r2b = result["rules"]["R-2b"][0]
    assert r2b["sources"] == [{"file": "zoning_charts_2026-04.pdf", "page": 3,
                               "cell": {"section": YARDS, "row": "Front (minimum)", "column": "R-2B"}}]
    assert r2b["examples"][1]["given"] == {"front_yard": 9}                    # "{front} - 1" worked out per district
    assert r2b["drafted_by"] == "rule_drafting/claude-sonnet-5-5" and r2b["status"] == "draft"
    assert len(records) == 1 and records[0]["problem"] is None and records[0]["system_sha256"]


def test_a_cell_of_another_shape_goes_to_a_person(inputs):
    result, _ = run(inputs, FakeClient({"templates": [REAR_YARD], "no_rule_reason": ""}))
    assert result["rules"]["R-1b"][0]["check"] == "rear_yard >= max(min(0.25 * lot_depth, 50), 20)"
    assert result["rules"]["R-3a"][0]["check"] == "rear_yard >= max(min(0.2 * lot_depth, 50), 20)"
    gaps = {g["rule"]: g["why"] for g in result["unresolved"]}
    assert "RU" not in result["rules"] and "footnotes ['17']" in gaps["RU.rear_yard"]   # RU's note 17, not 16
    note = [s for s in result["rules"]["R-1b"][0]["sources"] if "quote" in s]
    assert note == [{"file": "zoning_charts_2026-04.pdf", "page": 3, "lines": [66, 66], "quote": "(16) But not less than 20 ft."}]


def test_a_cell_with_more_numbers_than_expected_is_never_guessed():
    shape = slot("pct", "Percent of lot area", section="Maximum lot coverage by buildings", percent=True)
    cell = {"value": "35%/40% /50% [fn12]"}                                   # R-2C: three numbers by use
    assert chart_values.fill(shape, cell) == (None, "the cell '35%/40% /50% [fn12]' has 3 numbers, the rule expects 1")
    assert chart_values.fill(shape, {"value": "-"})[1] == "the chart shows '-' here"
    assert chart_values.fill(shape, {"value": "25%"}) == (0.25, None)


def test_a_typed_chart_number_is_sent_back(inputs):
    typed = template("front_yard", "front_yard >= 25", [], [({"front_yard": "25"}, "pass"), ({"front_yard": "24"}, "fail")])
    client = FakeClient({"templates": [typed], "no_rule_reason": ""}, {"templates": [FRONT], "no_rule_reason": ""})
    result, records = run(inputs, client)
    assert "a chart number must be a slot" in records[0]["problem"] and records[1]["problem"] is None
    assert "can't be used" in client.requests[1]["messages"][-1]["content"] and result["rules"]["R-1b"]


def test_a_quote_not_in_the_text_is_sent_back(inputs):
    made_up = copy.deepcopy(REAR_YARD)
    made_up["quotes"] = [{"document": "chart", "page": 3, "piece": "", "text": "(16) But never less than 20 ft."}]
    client = FakeClient({"templates": [made_up], "no_rule_reason": ""}, {"templates": [REAR_YARD], "no_rule_reason": ""})
    result, records = run(inputs, client)
    assert "occurs 0 times" in records[0]["problem"] and result["rules"]["R-1b"]


def test_a_unit_that_never_gets_a_usable_answer_is_left_for_a_person(inputs):
    typed = template("front_yard", "front_yard >= 25", [], [({"front_yard": "25"}, "pass"), ({"front_yard": "24"}, "fail")])
    answer = {"templates": [typed], "no_rule_reason": ""}
    result, records = run(inputs, FakeClient(answer, answer, answer))
    assert len(records) == drafter.SETTINGS["max_attempts"] and result["failed"] and not result["rules"]


def test_a_law_piece_with_no_residential_rule_records_why(inputs):
    result, _ = run(inputs, FakeClient({"templates": [], "no_rule_reason": "Only for the CBD districts."}), uid="325-16D")
    assert result["rules"] == {} and result["reason"] == "Only for the CBD districts."


def test_a_needed_fact_is_proposed_as_a_measure_not_invented(inputs):
    sheds = template("325_25a_not_in_front_yard", "not accessory_in_required_front_yard", [],
                     [({"accessory_in_required_front_yard": "false"}, "pass"), ({"accessory_in_required_front_yard": "true"}, "fail")],
                     quotes=[{"document": "law", "page": 0, "piece": "325-25A", "text": (
                         "Accessory structures which are wholly or partially above finished grade are permitted in any side "
                         "or rear yard but not in a required front yard, except as permitted under the further provisions "
                         "of this section.")}],
                     new_measures=[{"name": "accessory_in_required_front_yard", "unit": "yes_no",
                                    "meaning": "An accessory structure stands in the required front yard"}])
    sheds["topic"] = "site_features"
    sheds["id_suffix"] = "not_in_front_yard"
    result, records = run(inputs, FakeClient({"templates": [sheds], "no_rule_reason": ""}), uid="325-25A")
    assert records[0]["problem"] is None, records[0]["problem"]
    rule = result["rules"]["general"][0]
    assert rule["id"] == "general.325_25a_not_in_front_yard" and rule["check"] == "not accessory_in_required_front_yard"
    assert result["proposed"] == {"accessory_in_required_front_yard": {
        "unit": "yes_no", "meaning": "An accessory structure stands in the required front yard"}}


def test_every_call_is_charged_against_the_cap_and_refused_past_it(inputs, tmp_path):
    budget = Budget(0.0001, tmp_path / "ledger.json")
    with pytest.raises(BudgetExceeded):
        run(inputs, FakeClient({"templates": [FRONT], "no_rule_reason": ""}), budget=budget)
    budget = Budget(5.0, tmp_path / "ledger2.json")
    run(inputs, FakeClient({"templates": [FRONT], "no_rule_reason": ""}), budget=budget)
    assert 0 < budget.spent < 0.1


def test_the_answer_key_is_never_shown_to_the_drafter(inputs):
    hand = cli.load(cli.PLACE / "5_zoning_rules/R-1b.yaml")
    texts = [inputs.system()] + [drafter.unit_message(u, drafter.gather_context(u, inputs.law, {"notes": inputs.notes},
                                                                                inputs.definitions))
                                 for u in inputs.units() if not u.get("code")]
    for rule in hand["rules"]:
        assert not any(rule["id"] in t for t in texts), rule["id"]
        assert not any(rule["check"] in t for t in texts if "check" in rule), rule["id"]


def test_the_request_asks_for_the_template_shape_with_cached_instructions(inputs):
    client = FakeClient({"templates": [FRONT], "no_rule_reason": ""})
    run(inputs, client)
    request = client.requests[0]
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"} and "temperature" not in request
    assert request["output_config"]["format"]["schema"]["required"] == ["templates", "no_rule_reason"]


def test_permitted_use_rules_follow_the_chart_marks(inputs):
    result = cli.draft_uses(inputs)
    r1b = result["rules"]["R-1b"][0]
    hand = next(r for r in cli.load(cli.PLACE / "5_zoning_rules/R-1b.yaml")["rules"] if r["id"] == "R-1b.use")
    assert r1b["check"] == hand["check"]                                       # same allowed uses as the hand draft
    no_rule = {cli.district_name(c) for c in inputs.columns} - set(result["rules"])
    assert no_rule == {"R-3a", "R-3b"}                                          # nothing there fails: for a person
    assert all(any(g["rule"] == f"{d}.use" and "no failing example" in g["why"] for g in result["unresolved"])
               for d in no_rule)


def test_footnotes_and_section_references_are_read_from_the_page(inputs):
    notes = inputs.notes[3]
    assert notes["16"] == {"lines": [66, 66], "text": "(16) But not less than 20 ft."}
    assert notes["12"]["lines"] == [58, 59]                                    # a note that runs onto a second line
    assert chart_values.section_refs("see §325-8(B)(1) and § 325-16, also §325-29.1") == ["325-8B", "325-16", "325-29.1"]


def test_a_template_with_an_undefined_slot_is_rejected(inputs):
    bad = copy.deepcopy(FRONT)
    bad["slots"] = []
    result, records = run(inputs, FakeClient({"templates": [bad], "no_rule_reason": ""}, {"templates": [FRONT], "no_rule_reason": ""}))
    assert "slot {front} is used but not defined" in records[0]["problem"]     # the drafter is told why
    assert records[1]["problem"] is None and result["rules"]["R-1b"]


def test_a_general_rule_is_filled_once_with_no_district(inputs):
    general = template("front_yard", "front_yard >= 0", [], [({"front_yard": "1"}, "pass")])
    rule, why = fill_template(general, None, inputs.cells, [], "x")
    assert why is None and rule["id"] == "general.front_yard" and not SLOT.search(json.dumps(rule))


ROW_31 = "Height in feet 35 ft 35 ft 35 ft 35 ft 35 ft 40 ft 35 ft 40 ft 35 ft"


def test_a_chart_row_quote_cannot_carry_a_typed_number(inputs):
    """Quoting a whole chart row would let any district's number into a rule for every district."""
    typed = template("max_height", "building_height <= 40", [],
                     [({"building_height": "40"}, "pass"), ({"building_height": "41"}, "fail")],
                     quotes=[{"document": "chart", "page": 3, "piece": "", "text": ROW_31}])
    answer = {"templates": [typed], "no_rule_reason": ""}
    result, records = run(inputs, FakeClient(answer, answer, answer), uid="chart-p3-maximum_building_height")
    assert result["rules"] == {} and result["failed"]
    assert "isn't a footnote under the table" in records[0]["problem"]
    assert "a chart number must be a slot" in records[0]["problem"]
    law = template("325_16c_height", "building_height <= 40", [], [({"building_height": "40"}, "pass"), ({"building_height": "41"}, "fail")],
                   quotes=[{"document": "chart", "page": 3, "piece": "", "text": ROW_31}])
    answer = {"templates": [law], "no_rule_reason": ""}
    result, records = run(inputs, FakeClient(answer, answer, answer), uid="325-16C")   # not from a law piece either
    assert result["rules"] == {} and "isn't a footnote under the table" in records[0]["problem"]


def test_a_filled_cells_footnote_must_be_quoted(inputs):
    """'25%/ 50 ft [fn16]' means nothing without note 16 ('But not less than 20 ft.')."""
    loose = copy.deepcopy(REAR_YARD) | {"quotes": [], "check": "rear_yard >= min({pct} * lot_depth, {cap})"}
    loose["examples"] = [{"given": [{"measure": "rear_yard", "value": "50"}, {"measure": "lot_depth", "value": "100"}],
                          "expect": "pass"},
                         {"given": [{"measure": "rear_yard", "value": "1"}, {"measure": "lot_depth", "value": "100"}],
                          "expect": "fail"}]
    result, records = run(inputs, FakeClient({"templates": [loose], "no_rule_reason": ""},
                                             {"templates": [REAR_YARD], "no_rule_reason": ""}))
    assert "footnote 16 of" in records[0]["problem"] and "isn't quoted" in records[0]["problem"]
    assert records[1]["problem"] is None and result["rules"]["R-1b"]


def test_a_template_that_works_nowhere_is_retried_then_listed_for_a_person(inputs):
    typed = template("front_typed", "front_yard >= 25", [], [({"front_yard": "25"}, "pass"), ({"front_yard": "24"}, "fail")])
    answer = {"templates": [FRONT, typed], "no_rule_reason": ""}
    client = FakeClient(answer, answer, answer)
    result, records = run(inputs, client)
    assert len(records) == drafter.SETTINGS["max_attempts"]                # each answer sent back with the reason
    assert "with every template" in client.requests[1]["messages"][-1]["content"]
    assert result["rules"]["R-1b"][0]["id"] == "R-1b.front_yard"           # the working template is kept
    assert any(g["rule"] == "chart-p3-yard_dimensions.front_typed" for g in result["unresolved"])


def test_a_requirement_no_rule_cites_goes_to_a_person(inputs):
    sentence = ("Accessory structures which are wholly or partially above finished grade are permitted in any side "
                "or rear yard but not in a required front yard, except as permitted under the further provisions "
                "of this section.")
    sheds = template("not_in_front_yard", "not accessory_in_required_front_yard", [],
                     [({"accessory_in_required_front_yard": "false"}, "pass"), ({"accessory_in_required_front_yard": "true"}, "fail")],
                     quotes=[{"document": "law", "page": 0, "piece": "325-25A", "text": sentence}],
                     new_measures=[{"name": "accessory_in_required_front_yard", "unit": "yes_no", "meaning": "m"}])
    sheds["topic"] = "site_features"
    u = unit(inputs, "325-25A")
    u = u | {"requirements": u["requirements"] + [{"file": inputs.law["file"], "page": 67, "lines": [3, 4],
                                                   "quote": "A later requirement of the same piece."}]}
    context = drafter.gather_context(u, inputs.law, {"notes": inputs.notes}, inputs.definitions)
    result = drafter.draft_unit(FakeClient({"templates": [sheds], "no_rule_reason": ""}), u, context, "S", inputs.law,
                                inputs.ctx, inputs.columns, inputs.cells, inputs.notes, lambda r: None)
    assert [g["rule"] for g in result["unresolved"]] == ["325-25A.requirement_p67_l3"]   # the cited one is covered


def test_every_law_piece_is_drafted_from_its_whole_numbered_text_with_the_label_as_hints(inputs):
    """Older labels may cite only a heading or lead-in, so the input is the whole piece: every line, numbered,
    page breaks marked. The label's cited lines are shown as hints, by the same line numbers."""
    from section_labeling.labeler import numbered_lines
    law_units = [u for u in inputs.units() if u.get("piece")]
    assert law_units
    for u in law_units:
        piece = inputs.law["pieces"][u["piece"]]
        message = drafter.unit_message(u, {"notes": [], "pieces": [], "definitions": []})
        lines = numbered_lines(inputs.law["rows"], piece)
        assert all(f"L{i}: {text}" in message for i, (_, _, text) in enumerate(lines, 1)), u["id"]
        pages = [p for p, _, _ in lines]
        breaks = re.findall(r"(?m)^--- page \d+ ---$", message)
        assert len(breaks) == sum(a != b for a, b in zip(pages, pages[1:])), u["id"]
        if u["requirements"]:
            assert "hints only" in message and all(s["quote"] in message for s in u["requirements"])
    u = unit(inputs, "325-16C")
    first = u["requirements"][0]
    i = next(i for i, (p, n, _) in enumerate(u["lines"], 1) if (p, n) == (first["page"], first["lines"][0]))
    assert f"- L{i}-L" in drafter.unit_message(u, {"notes": [], "pieces": [], "definitions": []})


def test_no_answer_key_arithmetic_reaches_the_drafter(inputs):
    system = inputs.system()
    assert not any(k in system for k in ("35 + 0.1 * 35", "38.5", "R-1b's"))


def test_accessory_uses_are_recorded_as_not_drafted_with_a_reason(inputs):
    assert {u["id"] for u in inputs.units() if u.get("code")} == {cli.USES_UNIT, cli.ACCESSORY_UNIT}
    assert all(s[0] != 2 for s in inputs.chart_sections)                      # page 2 is built by code, not the AI
    assert "Not drafted" in cli.draft_accessory()["reason"]


def test_a_typed_number_backed_only_by_a_footnote_marker_is_rejected(inputs):
    """'(5) For the first occupant...' is note 5: its 5 labels the note, it isn't a 5 ft side yard."""
    sneaky = template("front_and_side", "front_yard >= {front} and side_yard_smaller >= 5",
                      [slot("front", "Front (minimum)")],
                      [({"front_yard": "{front}", "side_yard_smaller": "5"}, "pass"),
                       ({"front_yard": "{front} - 1", "side_yard_smaller": "5"}, "fail")],
                      quotes=[{"document": "chart", "page": 3, "piece": "", "text": (
                          "(5) For the first occupant in each dwelling unit; +400 sf for each additional occupant "
                          "in each dwelling unit.")}])
    answer = {"templates": [sneaky], "no_rule_reason": ""}
    result, records = run(inputs, FakeClient(answer, answer, answer))
    assert result["rules"] == {} and "number 5 in" in records[0]["problem"]


def test_two_templates_with_one_id_in_an_answer_are_rejected(inputs):
    client = FakeClient({"templates": [FRONT, FRONT], "no_rule_reason": ""}, {"templates": [FRONT], "no_rule_reason": ""})
    result, records = run(inputs, client)
    assert "used by more than one template" in records[0]["problem"] and len(result["rules"]["R-1b"]) == 1


def test_a_section_headings_footnote_must_be_quoted(inputs):
    """'Minimum Lot Size [fn3]': note 3 ('See §325-8(B)(1).') governs every row under the heading."""
    section = "Minimum Lot Size [fn3]"
    lot = template("lot_area_detached", 'lot_area >= {area}', [slot("area", "One-family dwelling, detached", section=section)],
                   [({"lot_area": "{area}"}, "pass"), ({"lot_area": "{area} - 1"}, "fail")])
    noted = copy.deepcopy(lot) | {"quotes": [{"document": "chart", "page": 3, "piece": "", "text": "(3) See §325-8(B)(1)."}]}
    result, records = run(inputs, FakeClient({"templates": [lot], "no_rule_reason": ""},
                                             {"templates": [noted], "no_rule_reason": ""}), uid="chart-p3-minimum_lot_size")
    assert "footnote 3 of" in records[0]["problem"] and records[1]["problem"] is None
    assert result["rules"]["R-1b"][0]["check"] == "lot_area >= 6000"


def test_no_example_in_the_instructions_has_the_shape_of_a_graded_rule(inputs):
    """The drafter's instructions must not show the answer key's reading of the height bonus (X + 10% of X)."""
    import re
    assert not re.search(r"(\d+(?:\.\d+)?) \+ 0?\.1 \* \1\b", inputs.system())


def chart_quote(text, page=3):
    return {"document": "chart", "page": page, "piece": "", "text": text}


@pytest.mark.parametrize("uid, measure, op, n, quote", [
    # note 7 is about lot area per unit: its "1-3" says nothing about stories
    ("chart-p3-maximum_building_height", "stories", "<=", 3,
     "(7) For the first 1-3 units; +750 sf for each additional unit; +500 sf per room let for profit."),
    # note 13's 50% is 0.5 of an area, not 50 ft of width
    ("chart-p3-minimum_lot_width", "lot_width", ">=", 50, None),
])
def test_a_typed_number_backed_only_by_another_cells_footnote_is_rejected(inputs, uid, measure, op, n, quote):
    if quote is None:
        quote = next(note["text"] for note in inputs.notes[3].values() if note["text"].startswith("(13)"))
    worse = n + 1 if op == "<=" else n - 1
    bad = template("typed", f"{measure} {op} {n}", [], [({measure: str(n)}, "pass"), ({measure: str(worse)}, "fail")],
                   quotes=[chart_quote(quote)])
    answer = {"templates": [bad], "no_rule_reason": ""}
    result, records = run(inputs, FakeClient(answer, answer, answer), uid=uid)
    assert result["rules"] == {} and f"number {n} in" in records[0]["problem"]


def test_a_typed_number_backed_only_by_a_subsection_reference_is_rejected(inputs):
    """'§ 325-20D(1)' points to a subsection; its 1 isn't a parking minimum."""
    bad = template("parking_min", "parking_spaces >= 1", [],
                   [({"parking_spaces": "1"}, "pass"), ({"parking_spaces": "0"}, "fail")],
                   quotes=[{"document": "law", "page": 0, "piece": "325-20F",
                            "text": "No building permit shall be issued unless the requirements of § 325-20D(1) are met."}])
    answer = {"templates": [bad], "no_rule_reason": ""}
    result, records = run(inputs, FakeClient(answer, answer, answer), uid="325-20F")
    assert result["rules"] == {} and "number 1 in" in records[0]["problem"]


def test_a_number_in_a_slots_row_label_may_be_typed(inputs):
    """'First three bed or sleeping rooms', '4-5 bed or sleeping rooms': the 3 and the 5 are the row labels' own."""
    rows = ["First three bed or sleeping rooms per dwelling unit", "4-5 bed or sleeping rooms per dwelling unit",
            "Each additional bed or sleeping room"]
    parking = template(
        "parking_one_family",
        "parking_spaces >= ({first} if sleeping_rooms <= 3 else {mid} + {each} * max(sleeping_rooms - 5, 0))",
        [slot(name, row, page=14, section="Residential") for name, row in zip(("first", "mid", "each"), rows)],
        [({"use": "one_family_detached", "sleeping_rooms": "3", "parking_spaces": "{first}"}, "pass"),
         ({"use": "one_family_detached", "sleeping_rooms": "4", "parking_spaces": "{first}"}, "fail"),
         ({"use": "one_family_detached", "sleeping_rooms": "4", "parking_spaces": "{mid}"}, "pass"),
         ({"use": "one_family_detached", "sleeping_rooms": "6", "parking_spaces": "{mid} + {each}"}, "pass")],
        applies_when='use == "one_family_detached"',
        numbers=[bound(3, "slot_row_label", slot="first"), bound(5, "slot_row_label", slot="mid")])
    result, records = run(inputs, FakeClient({"templates": [parking], "no_rule_reason": ""}), uid="chart-p14-residential")
    assert records[0]["problem"] is None
    assert result["rules"]["R-1b"][0]["check"] == \
        "parking_spaces >= (1 if sleeping_rooms <= 3 else 2 + 1 * max(sleeping_rooms - 5, 0))"
    assert "open_questions" not in result["rules"]["R-1b"][0]          # a slot's own row label is trusted


def test_a_footnote_that_isnt_a_number_is_sent_back_not_a_crash(inputs):
    odd = copy.deepcopy(REAR_YARD)
    for s in odd["slots"]:
        s["footnotes"] = ["fn16"]
    result, records = run(inputs, FakeClient(*[{"templates": [odd], "no_rule_reason": ""}] * 3))
    assert "must be the note's number" in records[0]["problem"] and result["rules"] == {}


def test_a_crash_while_checking_still_records_the_paid_attempt(inputs, monkeypatch):
    monkeypatch.setattr(drafter, "check_answer", lambda *a, **k: 1 / 0)
    records = []
    with pytest.raises(ZeroDivisionError):
        run(inputs, FakeClient({"templates": [FRONT], "no_rule_reason": ""}), records=records)
    assert len(records) == 1 and "crashed" in records[0]["problem"] and records[0]["cost_usd"] > 0


def test_the_docs_describe_the_typed_number_rule_the_code_enforces():
    from pathlib import Path
    root = Path(drafter.__file__).resolve().parents[3]
    for doc in (root / "packages/rule_drafting/README.md", root / "docs/methods.md"):
        text = doc.read_text()
        assert "with no slots may not contain numbers" not in text
        # Ben's policy B, as the code enforces it: only the rule's own evidence, anything else refused, no questions
        assert "a footnote whose marker is on the slot's own cell" in text and "that slot's own row label" in text
        assert "a sentence of the paragraph being drafted" in text and "is refused" in text
        assert "open question for an architect" not in text and "footnote of one of the rule's slots" not in text
        assert "requirement lines its reviewed label cites" not in text and "whole text" in text and "hints" in text


def test_every_eval_result_the_docs_cite_has_its_committed_record():
    """A model or prompt comparison in the docs names the eval folder holding its run records and grades."""
    import re
    from pathlib import Path
    root = Path(drafter.__file__).resolve().parents[3]
    section = root.joinpath("docs/methods.md").read_text().split("## 10.")[1].split("## 11.")[0]
    cited = re.findall(r"packages/rule_drafting/evals/[\w.-]+/", section)
    assert {"packages/rule_drafting/evals/2026-10-19_model_choice/",
            "packages/rule_drafting/evals/2026-10-20_prompt_a/"} <= set(cited)
    for folder in cited:
        runs = list((root / folder / "runs").glob("*.jsonl"))
        assert (root / folder / "README.md").exists() and runs, folder
    for line in section.splitlines():                  # every claim about a model or a test batch cites its eval
        if "Haiku" in line or "Test batch" in line:
            assert "packages/rule_drafting/evals/" in line, line[:120]


def test_the_drafting_prompt_gives_role_purpose_process_and_the_current_number_rule():
    """Prompt A (2026-10-20): who the drafter is, why it matters, the steps in order, and the rules the code
    enforces today; none of the removed ones (open questions for numbers, every slot must decide something)."""
    text = " ".join(drafter.FORMAT.split())                  # one line: phrases may wrap anywhere
    for heading in ("## Who you are, and why this matters", "## The process, in order", "## What to write"):
        assert heading in text
    assert "Never a false pass" in text and "Code checks everything you write" in text
    assert "a sentence of the paragraph being drafted" in text and "Anything else is refused" in text
    assert "a footnote whose marker is on the slot's own cell" in text and "that slot's own row label" in text
    assert "Never write a placeholder test" in text and "an example in every tier, the top one included" in text
    assert "not folded into this rule" in text
    assert "sent to an architect as an open question" not in text            # numbers never go to a question
    assert "Every slot must decide something" not in text
    # only a review_when (or a flag) gives "needs review"; the checker never reads open questions
    assert "open question so the result is" not in text
    assert "An open question records the doubt for the architects but doesn't change any result" in text
    assert "every one gets a rule" in text


def test_the_whole_system_prompt_never_tells_the_drafter_to_do_what_its_rules_forbid(inputs):
    """The drafter reads the shared drafting guide and then its own instructions, in one message. Where the
    guide describes drafting by hand (combining a chart limit with a law exception; typing a chart number), it
    must say the script works differently, so the two never disagree."""
    text = " ".join(inputs.system().split())
    assert "A rule can combine a chart value with conditions from the law" not in text      # unqualified
    assert "When drafting by hand, a rule can combine a chart value" in text
    assert "The drafting script drafts one text at a time, so it drafts only that text's own requirements" in text
    assert "a quoted sentence, or a cited chart cell or its row label. The inspector" in text
    assert "The drafting script is stricter" in text and "it never types a chart number" in text


def test_a_slot_no_formula_uses_cant_lend_its_footnote_to_a_typed_number(inputs):
    """A decoy slot on a cell that carries note 7 ('For the first 1-3 units') must not back 'stories <= 3':
    R-3A's chart says 4 stories."""
    decoy = slot("x", "Multiple family dwelling, new construction", footnotes=["7"], section="Minimum Lot Size [fn3]")
    notes = [chart_quote(n["text"]) for k, n in inputs.notes[3].items() if k in ("3", "7")]
    bad = template("stories", "stories <= 3", [decoy], [({"stories": "3"}, "pass"), ({"stories": "4"}, "fail")],
                   quotes=notes)
    answer = {"templates": [bad], "no_rule_reason": ""}
    result, records = run(inputs, FakeClient(answer, answer, answer), uid="chart-p3-maximum_building_height")
    assert result["rules"] == {} and "no formula uses it" in records[0]["problem"]


DECOY = slot("x", "Multiple family dwelling, new construction", footnotes=["7"], section="Minimum Lot Size [fn3]")
LOT_AREA_X = "{x}"   # the decoy cell's value, for examples


@pytest.mark.parametrize("check, extra, expect", [
    # a slot written in but deciding nothing: caught by changing it, whatever the shape
    ("stories <= 3 + 0 * {x}", {}, "isn't backed where it stands"),
    ("stories <= 3 and {x} == {x}", {}, "isn't backed where it stands"),
    # a slot that decides something, but in another comparison than the 3 it lends its note to
    ("stories <= 3 and lot_area >= {x}", {"lot_area": LOT_AREA_X}, "isn't backed where it stands"),
    # one binding, legitimate where the 3 stands with {x}, must not also back the 3 of 'stories <= 3'
    ("stories <= 3 and lot_area >= 3 * {x}", {"lot_area": "3 * {x}"}, "'stories <= 3 and lot_area >= 3 * {x}' isn't backed"),
    # a slot that only gates the branch can't lend its note to the number the branch picks
    ("stories <= (3 if lot_area >= {x} else 0)", {"lot_area": LOT_AREA_X}, "isn't backed where it stands"),
    # {x} decides in the lot-area clause, but the occurrence next to the 3 decides nothing (round 7)
    ("stories <= 3 + 0 * {x} and lot_area >= {x}", {"lot_area": LOT_AREA_X}, "isn't backed where it stands"),
    ("stories <= min(3, {x}) and lot_area >= {x}", {"lot_area": LOT_AREA_X}, "isn't backed where it stands"),
])
def test_a_slot_lends_its_note_only_to_a_number_it_decides_with(inputs, check, extra, expect):
    """Note 7 ('For the first 1-3 units') is about lot area per unit. Bound to a decoy slot, its 3 must not
    become 'stories <= 3' for R-3a, whose own chart cell says 4 stories."""
    notes = [chart_quote(n["text"]) for k, n in inputs.notes[3].items() if k in ("3", "7")]
    bad = template("stories", check, [DECOY], [({"stories": "3"} | extra, "pass"), ({"stories": "5"} | extra, "fail"),
                                               ({"stories": "3", "lot_area": "1"}, "fail")] if extra else
                   [({"stories": "3"}, "pass"), ({"stories": "5"}, "fail")],
                   quotes=notes, numbers=[bound(3, "slot_footnote", slot="x", footnote="7")])
    answer = {"templates": [bad], "no_rule_reason": ""}
    result, records = run(inputs, FakeClient(answer, answer, answer), uid="chart-p3-maximum_building_height")
    assert result["rules"] == {} and expect in records[0]["problem"], records[0]["problem"]


def test_a_flags_check_is_refused_and_lends_nothing(inputs):
    """A flag's check is thrown away, so it can't carry a slot that lends a note: a flag with a check is refused."""
    notes = [chart_quote(n["text"]) for k, n in inputs.notes[3].items() if k in ("3", "7")]
    bad = template("stories_flag", "lot_area >= {x}", [DECOY], [], kind="flag", applies_when="stories <= 3",
                   quotes=notes, numbers=[bound(3, "slot_footnote", slot="x", footnote="7")])
    answer = {"templates": [bad], "no_rule_reason": ""}
    result, records = run(inputs, FakeClient(answer, answer, answer), uid="chart-p3-maximum_building_height")
    assert result["rules"] == {} and "a flag has no check" in records[0]["problem"]
    assert "isn't one this rule's formulas use" in records[0]["problem"]


@pytest.mark.parametrize("numbers, expect", [
    ([], "isn't backed where it stands"),                                         # typed, never bound
    ([bound(3, "law_quote", quote=0)], "isn't one of this template's law quotes"),   # quote 0 is a chart note
    ([bound(3, "slot_footnote", slot="x", footnote="16")], "isn't marked on slot 'x''s own cell"),  # not its note
])
def test_every_typed_number_is_bound_to_one_checked_evidence_item(inputs, numbers, expect):
    notes = [chart_quote(n["text"]) for k, n in inputs.notes[3].items() if k in ("3", "7")]
    bad = template("lot", "lot_area >= 3 * {x}", [DECOY],
                   [({"lot_area": "3 * {x}"}, "pass"), ({"lot_area": "3 * {x} - 1"}, "fail")],
                   quotes=notes, numbers=numbers)
    answer = {"templates": [bad], "no_rule_reason": ""}
    result, records = run(inputs, FakeClient(answer, answer, answer), uid="chart-p3-maximum_building_height")
    assert result["rules"] == {} and expect in records[0]["problem"], records[0]["problem"]


def test_a_bound_item_must_hold_the_value(inputs):
    sentence = "Each required front, side and rear yard is increased one foot on the ground for each one foot of such additional height."
    piece = next(p for p in inputs.law["pieces"] if sentence[:40] in drafter.piece_text(inputs.law["rows"], inputs.law["pieces"][p]))
    bad = template("yards_up", "front_yard >= 7", [], [({"front_yard": "7"}, "pass"), ({"front_yard": "6"}, "fail")],
                   quotes=[{"document": "law", "page": 0, "piece": piece, "text": sentence}],
                   numbers=[bound(7, "law_quote", quote=0)])
    answer = {"templates": [bad], "no_rule_reason": ""}
    u = unit(inputs, piece) if any(x["id"] == piece for x in inputs.units()) else None
    if u is None:
        pytest.skip(f"{piece} isn't a drafted unit")
    result, records = run(inputs, FakeClient(answer, answer, answer), uid=piece)
    assert result["rules"] == {} and "7 isn't written in it" in records[0]["problem"]


def test_the_drafters_line_numbers_are_the_labelers(inputs):
    """Both steps must call a line by the same number: one numbering function, and every piece's lines in the
    drafter's message are exactly the labeler's."""
    from section_labeling import labeler
    assert drafter.numbered is labeler.numbered
    for u in (u for u in inputs.units() if u.get("piece")):
        labeler_lines = labeler.piece_message(inputs.law["pieces"][u["piece"]], inputs.law["rows"]).split("\n\n", 1)[1]
        assert labeler_lines in drafter.unit_message(u, {"notes": [], "pieces": [], "definitions": []}), u["id"]


def test_the_estimate_uses_the_labelers_prices_and_cost_and_counts_like_a_real_call(inputs):
    from section_labeling import labeler
    assert drafter.PRICES is labeler.PRICES
    client = FakeClient()
    e = cli.estimate(inputs, [unit(inputs, "chart-p3-yard_dimensions")], drafter.SETTINGS["model"], client)
    assert e["cost_usd"] == labeler.cost(e["usage"], drafter.SETTINGS["model"])
    assert client.counted and all(c["system"] and c["output_config"]["format"] for c in client.counted)


@pytest.mark.parametrize("footnote, section, why", [
    # note 3 sits on the section heading "Minimum Lot Size [fn3]", not on the cell
    ("3", "Minimum Lot Size [fn3]", "the section heading's note"),
    # note 7 belongs to another cell when the slot's own cell has none
    ("7", "Minimum Lot Size [fn3]", "another cell's note"),
])
def test_only_a_note_marked_on_the_slots_own_cell_backs_a_number(inputs, footnote, section, why):
    """Ben's policy: a footnote backs a typed number only if its marker is on the slot's own cell."""
    unmarked = slot("x", "Multiple family dwelling, new construction", footnotes=[], section=section)
    t = template("lot", "lot_area >= 3 * {x}", [unmarked],
                 [({"lot_area": "3 * {x}"}, "pass"), ({"lot_area": "3 * {x} - 1"}, "fail")],
                 quotes=[chart_quote(n["text"]) for k, n in inputs.notes[3].items() if k in ("3", "7")],
                 numbers=[bound(3, "slot_footnote", slot="x", footnote=footnote)])
    answer = {"templates": [t], "no_rule_reason": ""}
    result, records = run(inputs, FakeClient(answer, answer, answer), uid="chart-p3-maximum_building_height")
    assert result["rules"] == {} and "isn't marked on slot 'x''s own cell" in records[0]["problem"], why


def test_a_slot_its_examples_dont_exercise_is_fine_when_it_backs_nothing(inputs):
    """The real Sonnet rear-yard draft: examples on a 1000 ft lot, where only the 50 ft cap binds. The percent
    never changes an example, but it backs no number, so it can lend nothing: the rule is kept. (The 20 from
    note 16 is backed by {cap}, which does decide.)"""
    sonnet = copy.deepcopy(REAR_YARD) | {"check": "rear_yard >= max(20, min({pct} * lot_depth, {cap}))"}
    sonnet["examples"] = [{"given": [{"measure": "lot_depth", "value": "1000"}, {"measure": "rear_yard", "value": "50"}],
                           "expect": "pass"},
                          {"given": [{"measure": "lot_depth", "value": "1000"}, {"measure": "rear_yard", "value": "49"}],
                           "expect": "fail"}]
    result, records = run(inputs, FakeClient({"templates": [sonnet], "no_rule_reason": ""}))
    assert records[0]["problem"] is None
    assert result["rules"]["R-1b"][0]["check"] == "rear_yard >= max(20, min(0.25 * lot_depth, 50))"


def test_a_note_on_the_slots_own_cell_backs_its_number(inputs):
    """'25%/ 50 ft [fn16]': note 16 ('But not less than 20 ft.') is on the rear-yard cell itself, so its 20 is trusted."""
    result, records = run(inputs, FakeClient({"templates": [REAR_YARD], "no_rule_reason": ""}))
    assert records[0]["problem"] is None
    assert result["rules"]["R-1b"][0]["check"] == "rear_yard >= max(min(0.25 * lot_depth, 50), 20)"
    assert "open_questions" not in result["rules"]["R-1b"][0]


PARAPET = ("The provisions of this chapter shall not apply to prevent the erection above the building height limit of a "
           "parapet wall or cornice for ornament extending above such height five feet or less.")


def test_a_number_from_another_sections_sentence_is_rejected(inputs):
    """325-16B's parapet 'five feet or less' must not become 'stories <= 5' in a chart rule (R-3a's own cell says
    4 stories): a sentence that isn't the text being drafted never backs a number. Retried, then for a person."""
    notes = [chart_quote(n["text"]) for k, n in inputs.notes[3].items() if k in ("3", "7")]
    t = template("probe", "lot_area >= {x} and stories <= 5", [DECOY],
                 [({"lot_area": "{x}", "stories": "5"}, "pass"), ({"lot_area": "{x} - 1", "stories": "5"}, "fail")],
                 quotes=notes + [{"document": "law", "page": 0, "piece": "325-16B", "text": PARAPET}],
                 numbers=[bound(5, "law_quote", quote=2)])
    answer = {"templates": [t], "no_rule_reason": ""}
    result, records = run(inputs, FakeClient(answer, answer, answer), uid="chart-p3-maximum_building_height")
    assert result["rules"] == {} and len(records) == 3
    assert "is from §325-16B, not the text being drafted" in records[0]["problem"]
    assert any("325-16B" in u["why"] for u in result["unresolved"]) or result.get("failed")


def test_a_number_from_the_paragraph_being_drafted_needs_no_question(inputs):
    t = template("parapet", "parapet_height <= 5", [],
                 [({"parapet_height": "5"}, "pass"), ({"parapet_height": "6"}, "fail")],
                 quotes=[{"document": "law", "page": 0, "piece": "325-16B", "text": PARAPET}],
                 numbers=[bound(5, "law_quote", quote=0)],
                 new_measures=[{"name": "parapet_height", "unit": "ft", "meaning": "height of a parapet above the limit"}])
    result, records = run(inputs, FakeClient({"templates": [t], "no_rule_reason": ""}), uid="325-16B")
    assert records[0]["problem"] is None
    assert "open_questions" not in result["rules"]["general"][0]


def test_a_rule_with_no_number_from_a_chart_note_carries_no_question(inputs):
    result, records = run(inputs, FakeClient({"templates": [FRONT], "no_rule_reason": ""}))
    assert records[0]["problem"] is None and "open_questions" not in result["rules"]["R-1b"][0]


def _stating_cells(inputs, page, section):
    """(row, district) of every district cell in a chart section that states something."""
    return {(row, col) for (pg, sec, row, col), c in inputs.cells.items()
            if (pg, sec) == (page, section) and col in inputs.columns
            and chart_values.FOOTNOTE.sub("", c["value"]).strip() not in chart_values.NOT_APPLICABLE}


def test_a_chart_row_no_template_covers_goes_to_a_person_in_every_district(inputs):
    """The drafter answered only the front yard: every other row of Yard Dimensions, in every district whose
    cell states something, is listed for a person. A skipped row can't vanish (a false pass waiting to happen)."""
    result, _ = run(inputs, FakeClient({"templates": [FRONT], "no_rule_reason": ""}))
    listed = {(row, col) for row, col in _stating_cells(inputs, 3, YARDS)
              if any(g["rule"] == f"{cli.district_name(col)}.chart-p3-yard_dimensions" and repr(row) in g["why"]
                     and f"the {col} cell" in g["why"] for g in result["unresolved"])}
    others = {(row, col) for row, col in _stating_cells(inputs, 3, YARDS) if row != "Front (minimum)"}
    assert others and others <= listed
    assert not any("'Front (minimum)'" in g["why"] and "has no drafted rule" in g["why"] for g in result["unresolved"])


def test_a_chart_unit_answered_with_only_a_reason_still_lists_every_cell(inputs):
    result, _ = run(inputs, FakeClient({"templates": [], "no_rule_reason": "Nothing here sets a requirement."}))
    assert result["reason"] and not result["rules"]
    assert len(result["unresolved"]) == len(_stating_cells(inputs, 3, YARDS)) > 0


def test_the_use_rule_quotes_and_lists_the_notes_on_its_rows_and_column_heading(inputs):
    """Note 4 is on every dwelling row ("See §325-3 for occupancy restrictions") and notes 1, 2 on the R-1/R-2
    headings (occupancy counting, the South Hill Overlay). No measure checks them, so each is quoted in the rule
    and listed for a person, never dropped."""
    result = cli.draft_uses(inputs)
    r1b = result["rules"]["R-1b"][0]
    quoted = {s["quote"][:4] for s in r1b["sources"] if "quote" in s}
    assert {"(1) ", "(2) ", "(4) "} <= quoted
    why = [g["why"] for g in result["unresolved"] if g["rule"] == "R-1b.use"]
    assert any("footnote 4" in w and "One-family dwelling, detached" in w for w in why)
    assert any("footnote 1" in w and "R-1B column heading" in w for w in why)
    assert any("footnote 2" in w and "South Hill Overlay" in w for w in why)
    r3a = [g["why"] for g in result["unresolved"] if g["rule"] == "R-3a.use"]
    assert not any("column heading" in w for w in r3a)     # R-3's page-2 heading carries no note


def test_a_reference_takes_its_lettered_subsections_not_the_next_numbered_section(inputs):
    u = {"id": "x", "text": "See § 325-29.", "page": None}
    ids = [p["id"] for p in drafter.gather_context(u, inputs.law, {"notes": inputs.notes}, inputs.definitions)["pieces"]]
    assert "325-29" in ids and not any(i.startswith("325-29.") for i in ids)


def test_a_long_section_is_named_as_dropped_and_the_short_ones_after_it_still_come(inputs):
    """325-8A points to 325-20D, too long to fit; the small subsections after it (325-20E ...) still come, and
    whatever is left out is named in the message and listed for a person."""
    u = unit(inputs, "325-8A")
    context = drafter.gather_context(u, inputs.law, {"notes": inputs.notes}, inputs.definitions)
    ids = [p["id"] for p in context["pieces"]]
    assert "325-20D" in context["dropped"] and "325-20E" in ids             # the cut didn't stop the loop
    assert "left out for length" in drafter.unit_message(u, context)
    result = drafter.keep({"rules": {}, "unresolved": [], "rejected": [], "problems": []}, u, inputs.cells,
                          inputs.columns, context)
    assert {d for d in context["dropped"]} <= {g["why"].split()[3].rstrip(",") for g in result["unresolved"]
                                                 if "left out of the drafter's input" in g["why"]}


def test_a_drafting_run_rewrites_the_labels_review_list(inputs, tmp_path, monkeypatch):
    """Drafted rules feed the review list's 'cited by' column, so a run must end by rewriting it."""
    refreshed = []
    real = cli.Inputs
    def scratch():
        i = real()
        i.records, i.drafted = tmp_path / "records", tmp_path / "drafted"
        return i
    monkeypatch.setattr(cli, "Inputs", scratch)
    monkeypatch.setattr(cli, "LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(cli, "refresh_review_list", lambda i: refreshed.append(i.j))
    assert cli.main(["draft", "--only", cli.USES_UNIT, "--yes"]) == 0
    assert refreshed == [cli.PLACE]


def test_drafted_rules_are_listed_apart_from_hand_rules_with_the_same_id(tmp_path):
    from section_labeling import coverage
    rule = {"id": "R-1b.x", "sources": [{"file": "law.pdf", "page": 1, "lines": [2, 2], "quote": "q"}]}
    (tmp_path / "5_zoning_rules/drafted").mkdir(parents=True)
    (tmp_path / "4_term_definitions").mkdir()
    for path in ("5_zoning_rules/R-1b.yaml", "5_zoning_rules/drafted/R-1b.yaml"):
        (tmp_path / path).write_text(cli.yaml.safe_dump({"district": "R-1b", "rules": [rule]}))
    pieces = {"p": {"id": "p", "lines": [[1, 1, 3]]}}
    assert coverage.cited_by(tmp_path, "law.pdf", pieces) == {"p": ["R-1b.x", "drafted:R-1b.x"]}


def test_the_methods_doc_counts_the_units_the_script_drafts(inputs):
    """The full-run budget decision rests on this count, so it is worked out from the units, not typed."""
    from rule_format.rulebook import REPO
    doc = (REPO / "docs/methods.md").read_text()
    m = re.search(r"(\d+) AI calls: (\d+) chart sections, (\d+) law pieces", doc)
    ai = [u for u in inputs.units() if not u.get("code")]
    assert m and tuple(map(int, m.groups())) == (len(ai), sum("section" in u for u in ai), sum("piece" in u for u in ai))
