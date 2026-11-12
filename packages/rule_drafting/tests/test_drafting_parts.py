"""The drafting script's code checks on rules for each part (rule_format/parts.py): what the AI drafts is checked by
the same rows the checker gives, quote by quote and number by number, exactly as a zoning rule is.

Every rule and every line of text here is SYNTHETIC (rule_format/tests/test_parts.py): made up for these tests,
never the building code (bringing in the code text waits on the copyright decision). The numbers only look like
egress numbers. The answers stand in for the AI's; no key, no network, no money.
"""

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from rule_drafting import drafter
from rule_drafting.templates import fill_template
from rule_format import parts

_spec = importlib.util.spec_from_file_location(
    "synthetic_parts", Path(__file__).parents[2] / "rule_format/tests/test_parts.py")
synthetic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(synthetic)
CTX, PAGE = synthetic.CTX, synthetic.SYNTHETIC_PAGE

# a synthetic piece of a synthetic law: page 1 of synthetic.pdf, lines 1 to 3
LAW = {"file": "synthetic.pdf", "chart": "synthetic_chart.pdf",
       "pieces": {"S-1": {"id": "S-1", "title": "SYNTHETIC escape openings", "kind": "subsection", "lines": [[1, 1, 3]]}}}
UNIT = {"id": "S-1", "piece": "S-1", "prefix": "s_1_", "intro": "SYNTHETIC piece S-1.",
        "text": "\n".join(PAGE.values())}
CONTEXT = {"pieces": [], "notes": [], "dropped": [], "unfound": [], "definitions": [], "related": [],
           "related_dropped": []}
QUOTE = {"document": "law", "page": 0, "piece": "S-1", "text": f"{PAGE[1]} {PAGE[2]}"}


@pytest.fixture(autouse=True)
def no_sdk(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)


def given(**values):
    return [{"measure": m, "value": str(v)} for m, v in values.items()]


def room(rid):
    return {"kind": "sleeping_room", "id": rid, "name": f"Bedroom {rid[-1]}", "within": "", "measures": []}


def opening(oid, rid, area, at_grade="false", height=30):
    return {"kind": "emergency_escape_opening", "id": oid, "name": "", "within": rid,
            "measures": given(opening_net_clear_area=area, opening_at_grade=at_grade, opening_net_clear_height=height)}


def example(rooms, openings, rows, expect):
    return {"given": [], "parts": [room(r) for r in rooms] + openings,
            "rows": [{"part": p, "within": w, "outcome": o} for p, w, o in rows], "expect": expect}


PASS = example(["br1"], [opening("w1", "br1", 6)], [("w1", "br1", "pass")], "pass")
FAIL = example(["br1"], [opening("w1", "br1", 5.1)], [("w1", "br1", "fail")], "fail")
GRADE = example(["br1"], [opening("w1", "br1", 5.1, "true")], [("w1", "br1", "pass")], "pass")
NONE = example(["br1", "br2"], [opening("w1", "br1", 6)], [("w1", "br1", "pass"), ("", "br2", "fail")], "fail")


def area_template(**change):
    """What the AI would answer for the synthetic escape-opening text, as a template (for_parts schema)."""
    t = {"id_suffix": "escape_area", "title": "SYNTHETIC escape opening area", "topic": "egress", "kind": "rule",
         "applies_when": "",
         "check": "opening_net_clear_area >= (5.0 if opening_at_grade else 5.7) and opening_net_clear_height >= 24",
         "slots": [], "review_when": [], "quotes": [QUOTE],
         "numbers": [{"value": v, "from": "law_quote", "quote": 0, "slot": "", "footnote": ""} for v in (5.0, 5.7, 24)],
         "examples": [PASS, FAIL, GRADE, NONE], "open_questions": [], "new_measures": [],
         "for_each": "emergency_escape_opening", "within": "sleeping_room", "when_none": "fail"}
    return t | change


def check(*templates):
    return drafter.check_answer({"templates": list(templates), "no_rule_reason": ""}, UNIT, CONTEXT, LAW,
                                copy.deepcopy(CTX), [], {}, {}, "rule_drafting/test")


def test_a_rule_for_each_part_drafted_from_the_text_is_kept_with_its_rows_checked():
    got = check(area_template())
    assert got["problems"] == [], got["problems"]
    rule = got["rules"]["general"][0]
    assert (rule["id"], rule["for_each"], rule["within"], rule["when_none"]) == \
        ("general.s_1_escape_area", "emergency_escape_opening", "sleeping_room", "fail")
    assert rule["sources"] == [{"file": "synthetic.pdf", "page": 1, "lines": [1, 2], "quote": QUOTE["text"]}]
    # the example as the rule file writes it: the parts by kind, the rows by id ("" left out)
    assert rule["examples"][3] == {
        "given": {}, "parts": {"emergency_escape_opening": [{"id": "w1", "within": "br1", "measures": {
            "opening_net_clear_area": 6, "opening_at_grade": False, "opening_net_clear_height": 30}}],
            "sleeping_room": [{"id": "br1", "name": "Bedroom 1", "measures": {}},
                              {"id": "br2", "name": "Bedroom 2", "measures": {}}]},
        "rows": [{"part": "w1", "within": "br1", "outcome": "pass"}, {"within": "br2", "outcome": "fail"}],
        "expect": "fail"}
    # and what the checker gives for it is what the example says
    assert parts.worked_example(rule, rule["examples"][3], CTX.allowed())[0] == "fail"


def test_a_draft_without_a_when_none_example_is_refused():
    got = check(area_template(examples=[PASS, FAIL, GRADE]))
    assert got["rules"] == {}
    assert any("no worked example shows when_none (fail)" in p for p in got["problems"]), got["problems"]


@pytest.mark.parametrize("wrong, words", [
    # Bedroom 2's "no escape opening" row said to pass: the checker fails it
    (example(["br1", "br2"], [opening("w1", "br1", 6)], [("w1", "br1", "pass"), ("", "br2", "pass")], "pass"),
     "expected rows pass for w1 in br1; pass in br2; got pass for w1 in br1; fail in br2"),
    # Bedroom 2's row left out
    (example(["br1", "br2"], [opening("w1", "br1", 6)], [("w1", "br1", "pass")], "pass"), "expected rows"),
    # the rows right, the rule's one answer wrong
    (example(["br1", "br2"], [opening("w1", "br1", 6)], [("w1", "br1", "pass"), ("", "br2", "fail")], "pass"),
     "expected pass, got fail"),
])
def test_a_wrong_expected_row_or_answer_is_sent_back(wrong, words):
    got = check(area_template(examples=[PASS, FAIL, GRADE, NONE, wrong]))
    assert got["rules"] == {} and any(f"example 5: {words}" in p for p in got["problems"]), got["problems"]


def test_a_quote_not_in_the_synthetic_text_is_sent_back():
    bad = QUOTE | {"text": "SYNTHETIC TEST TEXT, NOT THE CODE: an escape opening of a sleeping room has 6.0 square feet"}
    got = check(area_template(quotes=[bad]))
    assert got["rules"] == {} and any("isn't in this piece word for word" in p for p in got["problems"])


def test_a_typed_number_not_in_the_text_is_sent_back():
    t = area_template(check=area_template()["check"].replace("24", "22"))
    t["numbers"][2]["value"] = 22
    got = check(t)
    assert got["rules"] == {} and any("22 isn't written in it" in p for p in got["problems"]), got["problems"]


def test_a_part_measure_on_the_building_is_sent_back():
    """A part's measure in a building measures `given`: the AI can't make it a building value."""
    t = area_template(examples=[PASS | {"given": given(opening_net_clear_area=6)}, FAIL, GRADE, NONE])
    got = check(t)
    assert got["rules"] == {} and any("a part's measures go in 'parts'" in p for p in got["problems"])


def test_an_example_part_of_a_kind_the_rule_doesnt_read_is_sent_back():
    stair = {"kind": "stair", "id": "s1", "name": "", "within": "", "measures": given(stair_riser_height=7)}
    t = area_template(examples=[PASS | {"parts": PASS["parts"] + [stair]}, FAIL, GRADE, NONE])
    got = check(t)
    assert got["rules"] == {} and any("not a kind this rule reads" in p for p in got["problems"]), got["problems"]


def test_a_zoning_template_never_carries_parts():
    t = area_template(for_each="", within="", when_none="")
    got = check(t)
    assert got["rules"] == {}
    assert any("isn't for each part" in p for p in got["problems"]), got["problems"]


def test_when_none_needs_for_each_and_pass_is_never_one():
    got = check(area_template(for_each="", examples=[]))
    assert any("only go with 'for_each'" in p for p in got["problems"]), got["problems"]


# --- a chart number in a rule for each part: decided by the rows, not outcome() ------------------------------------

STAIRS, RISER_ROW, COLUMN = "SYNTHETIC Stairs", "Riser (maximum) plus 0.25", "R-1B"
CELLS = {(1, STAIRS, RISER_ROW, COLUMN): {"value": "8"}}
RISER_SLOT = {"name": "riser", "page": 1, "section": STAIRS, "row": RISER_ROW, "number": 1, "numbers_in_cell": 1,
              "percent": False, "footnotes": []}


def riser_template():
    def stair(r):
        return {"kind": "stair", "id": "s1", "name": "", "within": "", "measures": given(stair_riser_height=r)}
    ex = [{"given": [], "parts": [stair("{riser}")], "rows": [{"part": "s1", "within": "", "outcome": "pass"}],
           "expect": "pass"},
          {"given": [], "parts": [stair("{riser} + 0.5")], "rows": [{"part": "s1", "within": "", "outcome": "fail"}],
           "expect": "fail"},
          {"given": [], "parts": [], "rows": [{"part": "", "within": "", "outcome": "not_applicable"}],
           "expect": "not_applicable"}]
    return {"id_suffix": "riser", "title": "SYNTHETIC riser", "topic": "egress", "kind": "rule", "applies_when": "",
            "check": "stair_riser_height <= {riser} + 0.25", "slots": [RISER_SLOT], "review_when": [], "quotes": [],
            "numbers": [], "examples": ex, "open_questions": [], "new_measures": [],
            "for_each": "stair", "within": "", "when_none": "not_applicable"}


def test_a_slot_in_a_rule_for_each_part_is_seen_to_decide():
    """The drafter's test of whether a slot backing a typed number decides anything changes the slot and looks at
    the worked examples. For a rule for each part it must look at the rows: outcome() says needs review for any
    such rule, so through it no slot ever decides and every chart-backed number is refused."""
    t = riser_template()
    rule, why = fill_template(t, COLUMN, CELLS, [], "rule_drafting/test", "synthetic_chart.pdf")
    assert why is None and rule["check"] == "stair_riser_height <= 8 + 0.25"
    valid = [{"value": 0.25, "from": "slot_row_label", "quote": -1, "slot": "riser", "footnote": ""}]
    assert drafter._backing(t, valid, [(COLUMN, rule)], CELLS, [], "rule_drafting/test", CTX.allowed(),
                            "synthetic_chart.pdf") == []
    # a slot that truly decides nothing (multiplied by 0) is still caught
    dead = t | {"check": "stair_riser_height <= 8.25 + 0 * {riser}"}
    rule, _ = fill_template(dead, COLUMN, CELLS, [], "rule_drafting/test", "synthetic_chart.pdf")
    valid = [{"value": 8.25, "from": "slot_row_label", "quote": -1, "slot": "riser", "footnote": ""}]
    assert drafter._backing(dead, valid, [(COLUMN, rule)], CELLS, [], "rule_drafting/test", CTX.allowed(),
                            "synthetic_chart.pdf")


# --- the request: a zoning run asks exactly what it always did --------------------------------------------------------

def test_the_zoning_schema_and_instructions_are_unchanged_and_the_parts_ones_add_the_fields():
    plain = drafter.output_schema(["egress"])
    template = plain["schema"]["properties"]["templates"]["items"]
    assert not set(parts.PART_FIELDS) & set(template["properties"])
    assert set(template["properties"]["examples"]["items"]["properties"]) == {"given", "expect"}
    with_parts = drafter.output_schema(["egress"], for_parts=True)["schema"]["properties"]["templates"]["items"]
    assert set(parts.PART_FIELDS) <= set(with_parts["required"])
    assert "pass" not in with_parts["properties"]["when_none"]["enum"]
    assert {"parts", "rows"} <= set(with_parts["properties"]["examples"]["items"]["required"])
    # the request a drafting run sends: the parts shape only when asked
    sent = []

    class Client:
        messages = None

        def create(self, **request):
            sent.append(request)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(
                {"templates": [area_template()], "no_rule_reason": ""}))], stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=1, output_tokens=1), _request_id="req_test")
    client = Client()
    client.messages = client
    records = []
    got = drafter.draft_unit(client, UNIT, CONTEXT, "SYSTEM", LAW, copy.deepcopy(CTX), [], {}, {}, records.append,
                             for_parts=True)
    assert got["rules"]["general"][0]["for_each"] == "emergency_escape_opening" and records[0]["for_parts"] is True
    assert sent[0]["output_config"]["format"] == drafter.output_schema(sorted(CTX.topics), for_parts=True)


def test_the_parts_instructions_name_every_part_kind_and_never_pass_for_none():
    from rule_drafting import __main__ as cli
    i = cli.Inputs()
    plain = i.system()
    with_parts = drafter.system_prompt(i.ctx, i.uses, [], drafter.chart_table(i.chart_sections, i.rows_of), i.notes,
                                       for_parts=True)
    assert "for_each" not in plain and drafter.PARTS_FORMAT in with_parts
    for kind, d in parts.registry().items():
        assert f"- {kind}: " in with_parts and all(m in with_parts for m in d["measures"])
    assert 'Never "pass"' in drafter.PARTS_FORMAT


@pytest.mark.parametrize("break_it", [
    lambda ex: ex["parts"][0].__setitem__("name", None),
    lambda ex: ex["rows"].__setitem__(0, "w1"),
    lambda ex: ex["rows"][0].__setitem__("part", None),
    lambda ex: ex["parts"][1].__setitem__("within", ["br1"]),
    lambda ex: ex.__setitem__("parts", {"x": 1}),
])
def test_a_malformed_example_in_an_answer_is_sent_back_never_a_crash(break_it):
    """Review round 2: a non-text name or id, or a row that isn't an object, crashed the run (AttributeError) instead
    of sending the answer back."""
    t = area_template()
    t["examples"] = copy.deepcopy(t["examples"])
    break_it(t["examples"][0])
    got = check(t)
    assert got["rules"] == {} and got["problems"], got


def test_the_zoning_answer_shape_is_byte_for_byte_what_it_was():
    """Pinned against origin/egress-2-rules-for-each-part's output_schema (sha256 of its sorted JSON), 2026-11-12."""
    import hashlib
    got = hashlib.sha256(json.dumps(drafter.output_schema(["dimensions", "uses"]), sort_keys=True).encode()).hexdigest()
    assert got == "42a6c92904fccc65ff259ca4c737502ba76fab3f26f0051c9c88802b05cf9098"
    assert hashlib.sha256(drafter.FORMAT.encode()).hexdigest()[:16] == "d35d0ea43228df3e"
