"""Drafting New York's Residential Code (rule_drafting/book.py, egress step 3): the units, what the drafter is shown,
and the code checks on its answers. The answers stand in for the AI's; no key, no network, no money.

Tests that read the book's text need the code cache (the book is kept outside the repo); without it they skip and say
so. The others run anywhere.
"""

import copy
import json
import sys
from types import SimpleNamespace

import pytest

from rule_drafting import book, drafter
from rule_format.rulebook import cached_text, Context

STATE = book.PLACES / "new_york/new_york_state"
USAGE = {"input_tokens": 100, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 50}


def has_cache() -> bool:
    ctx = Context.for_jurisdiction(STATE)
    return cached_text(ctx.sources["gov.ny.residential.2025.pdf"]).exists()


needs_cache = pytest.mark.skipif(not has_cache(), reason="the book is kept outside the repo and isn't in the code "
                                                         "cache here; checked where the cache exists")


@pytest.fixture(autouse=True)
def no_sdk(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)


@pytest.fixture(scope="module")
def inputs():
    return book.BookInputs(STATE)


class FakeClient:
    def __init__(self, *answers):
        self.answers, self.requests = list(answers), []
        self.messages = self

    def create(self, **request):
        self.requests.append(copy.deepcopy(request))
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(self.answers.pop(0)))],
                               stop_reason="end_turn", usage=SimpleNamespace(**USAGE), _request_id="req_test")


def test_references_follow_the_books_numbering():
    pieces = {p: {} for p in ["R319.4", "R319.4.1", "R319.4.2", "R319.4.2.1", "R319.4.2.2", "R319.4.3", "R319.4.4",
                              "R319.5", "R318.7.11.1", "BF101"]}
    got, unfound = book.references("in accordance with Sections R319.4.1 through R319.4.4. See Section R318.7.11.1, "
                                   "Section BF101 and Section R311.7.", pieces)
    assert got == ["R319.4.1", "R319.4.2", "R319.4.2.1", "R319.4.2.2", "R319.4.3", "R319.4.4", "R318.7.11.1", "BF101"]
    assert unfound == ["R311.7"]                   # named, never dropped silently (BO108.4's misnumbered R311.7)


def test_the_second_reading_is_shown_with_its_comparisons_and_flags():
    text = book.second_reading_text({"second_reading_numbers": ["not less than 5.7 square foot", "5 square foot"],
                                     "second_reading_comparisons": [">=", ">="],
                                     "flags": ["'5 square foot': printed ... (>=)"]})
    assert "- 'not less than 5.7 square foot': >=" in text and "- '5 square foot': >=" in text
    assert "Flags on them:\n- '5 square foot'" in text


@needs_cache
def test_the_units_are_the_scoped_rule_pieces_each_with_its_second_reading(inputs):
    units = inputs.units()
    assert [u["id"] for u in units] == list(book.SCOPE)
    risers = next(u for u in units if u["id"] == "R318.7.5.1")
    assert "'not more than 8 1/4 inch': <=" in risers["intro"]
    assert risers["lines"][0][:2] == (100, 42)
    # the patio cover's open question goes with it, never settled by the drafter
    patio = next(u for u in units if u["id"] == "BF103.2")
    assert "Open question" in patio["intro"] and "unenclosed" in patio["intro"]


@needs_cache
def test_the_instructions_say_it_is_a_building_code_with_rules_for_each_part(inputs):
    system = inputs.system()
    assert "## This run: a state building code, not a zoning chart" in system
    assert "## Rules for each part" in system and "- open_side:" in system and "- sleeping_loft:" in system


def risers_template(check="stair_riser_height <= 8.25", value=8.25):
    quote = "[NY] R318.7.5.1 Risers. The riser height shall be not more than 8 1/4 inches (209 mm)."
    stair = lambda h: {"kind": "stair", "id": "s1", "name": "Stair 1", "within": "",
                       "measures": [{"measure": "stair_riser_height", "value": str(h)}]}
    return {"id_suffix": "riser_height", "title": "Riser height", "topic": "means_of_egress", "kind": "rule",
            "applies_when": "", "check": check, "slots": [], "review_when": [],
            "quotes": [{"document": "law", "page": 0, "piece": "R318.7.5.1", "text": quote}],
            "numbers": [{"value": value, "from": "law_quote", "quote": 0, "slot": "", "footnote": ""}],
            "examples": [{"given": [], "parts": [stair(7.5)], "rows": [{"part": "s1", "within": "", "outcome": "pass"}],
                          "expect": "pass"},
                         {"given": [], "parts": [stair(8.5)], "rows": [{"part": "s1", "within": "", "outcome": "fail"}],
                          "expect": "fail"},
                         {"given": [], "parts": [], "rows": [{"part": "", "within": "", "outcome": "not_applicable"}],
                          "expect": "not_applicable"}],
            "open_questions": [], "new_measures": [], "for_each": "stair", "within": "", "when_none": "not_applicable"}


def check(inputs, *templates):
    unit = next(u for u in inputs.units() if u["id"] == "R318.7.5.1")
    return drafter.check_answer({"templates": list(templates), "no_rule_reason": ""}, unit, inputs.context(unit),
                                inputs.law, inputs.ctx, [], {}, {}, "rule_drafting/test")


@needs_cache
def test_a_draft_with_the_second_readings_number_is_kept(inputs):
    got = check(inputs, risers_template())
    assert got["problems"] == [], got["problems"]
    rule = got["rules"]["general"][0]
    assert rule["id"] == "general.r318_7_5_1_riser_height" and rule["check"] == "stair_riser_height <= 8.25"
    assert rule["sources"][0]["page"] == 100 and rule["sources"][0]["lines"] == [42, 42]


@needs_cache
@pytest.mark.parametrize("change, words", [
    # "8 1/4" read as 8: not written in the quote as the second reading reads it
    ({"check": "stair_riser_height <= 8", "value": 8}, "8 isn't written in it"),
    # a dropped "not": the number is right, the comparison backwards (validation, rule_format/code_numbers.py)
    ({"check": "stair_riser_height > 8.25"}, "needs > 8.25 to hold, but the law reads <= 8.25"),
])
def test_a_misread_number_or_comparison_is_sent_back(inputs, change, words):
    got = check(inputs, risers_template(**change))
    assert got["rules"] == {}
    assert any(words in p for p in got["problems"]), got["problems"]


@needs_cache
def test_a_recorded_drafting_call_is_marked_for_parts(inputs):
    unit = next(u for u in inputs.units() if u["id"] == "R318.7.5.1")
    client, calls = FakeClient({"templates": [risers_template()], "no_rule_reason": ""}), []
    result = drafter.draft_unit(client, unit, inputs.context(unit), inputs.system(), inputs.law, inputs.ctx, [], {}, {},
                                calls.append, for_parts=True)
    assert [r["id"] for r in result["rules"]["general"]] == ["general.r318_7_5_1_riser_height"]
    assert calls[0]["for_parts"] is True and calls[0]["unit"] == "R318.7.5.1"
    schema = client.requests[0]["output_config"]["format"]["schema"]
    assert "for_each" in schema["properties"]["templates"]["items"]["properties"]
