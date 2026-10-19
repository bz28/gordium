"""The rule-drafting script with a fake API client: no key, no network, no money. Includes the budget cap.

The answers below stand in for the AI's; what's tested is the code around it: chart numbers filled from
each district's own cell (never typed), cells of another shape sent to a person, quotes resolved to their
exact lines, bad answers sent back, every call recorded, and the answer key (R-1b.yaml) never shown.
"""

import copy
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

    def count_tokens(self, model, messages, system=""):
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


def template(suffix, check, slots, examples, quotes=(), kind="rule", applies_when="", new_measures=()):
    return {"id_suffix": suffix, "title": suffix.replace("_", " ").capitalize(), "topic": "dimensions", "kind": kind,
            "applies_when": applies_when, "check": check, "slots": slots, "review_when": [], "quotes": list(quotes),
            "examples": [{"given": [{"measure": m, "value": v} for m, v in g.items()], "expect": e} for g, e in examples],
            "open_questions": [], "new_measures": list(new_measures)}


FRONT = template("front_yard", "front_yard >= {front}", [slot("front", "Front (minimum)")],
                 [({"front_yard": "{front}"}, "pass"), ({"front_yard": "{front} - 1"}, "fail")])
REAR_YARD = template(
    "rear_yard", "rear_yard >= max(min({pct} * lot_depth, {cap}), 20)",
    [slot("pct", REAR, 1, 2, True, ["16"]), slot("cap", REAR, 2, 2, False, ["16"])],
    [({"rear_yard": "50", "lot_depth": "100"}, "pass"), ({"rear_yard": "19", "lot_depth": "60"}, "fail")],
    quotes=[{"document": "chart", "page": 3, "piece": "", "text": "(16) But not less than 20 ft."}])


def unit(inputs, uid):
    return next(u for u in inputs.units() if u["id"] == uid)


def run(inputs, client, uid="chart-p3-yard_dimensions", budget=None):
    u, records = unit(inputs, uid), []
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
    assert {g["rule"] for g in result["unresolved"]} == {"R-3a.use", "R-3b.use"}  # nothing there fails: for a person


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


def test_the_requirements_from_the_label_are_the_drafting_input(inputs):
    u = unit(inputs, "325-16C")
    message = drafter.unit_message(u, drafter.gather_context(u, inputs.law, {"notes": inputs.notes}, inputs.definitions))
    assert u["requirements"] and "draft a rule for each" in message
    assert all(s["quote"] in message for s in u["requirements"])


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
    assert result["rules"] == {} and "number 5 is typed" in records[0]["problem"]


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
