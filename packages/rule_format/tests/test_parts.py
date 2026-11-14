"""Rules for each part (rule_format/parts.py): validation and one row per part.

Every rule here is SYNTHETIC: made up for these tests, quoting made-up text on a made-up page, never the building
code (bringing in the code text waits on the copyright decision). The numbers only look like egress numbers.
"""

import copy

import pytest

from rule_format import parts
from rule_format.parts import part_outcome, registry_problems, rule_result, rows
from rule_format.rulebook import Context, approval_hash, outcome, tokenize, validate

SYNTHETIC_PAGE = {
    1: "SYNTHETIC TEST TEXT, NOT THE CODE: an escape opening of a sleeping room has 5.7 square feet",
    2: "SYNTHETIC TEST TEXT, NOT THE CODE: or 5.0 square feet at grade, and is 24 inches high",
    3: "SYNTHETIC TEST TEXT, NOT THE CODE: a stair riser is at most 8.25 inches",
}
CTX = Context(measures={"use", "stories"}, uses={"one_family_detached", "church"}, topics={"egress"},
              sources={"synthetic.pdf": {"file": "synthetic.pdf", "sha256": "a" * 64}},
              pages={"synthetic.pdf": {1: {n: tokenize(t) for n, t in SYNTHETIC_PAGE.items()}}})
ALLOWED = {"use": {"one_family_detached", "church"}}


def src(*lines):
    return {"file": "synthetic.pdf", "page": 1, "lines": [lines[0], lines[-1]],
            "quote": " ".join(SYNTHETIC_PAGE[n] for n in lines)}


def one_room(area, at_grade=False, height=30):
    """A worked example's parts: one bedroom with one escape opening."""
    return {"sleeping_room": [{"id": "br1", "name": "Bedroom 1"}],
            "emergency_escape_opening": [{"id": "w1", "within": "br1", "measures": {
                "opening_net_clear_area": area, "opening_at_grade": at_grade, "opening_net_clear_height": height}}]}


AREA = {  # SYNTHETIC: each sleeping room's escape openings, net clear area (and height)
    "id": "R-1b.synthetic_escape_area", "kind": "rule", "topic": "egress",
    "title": "SYNTHETIC escape opening area", "for_each": "emergency_escape_opening", "within": "sleeping_room",
    "when_none": "fail",
    "check": "opening_net_clear_area >= (5.0 if opening_at_grade else 5.7) and opening_net_clear_height >= 24",
    "sources": [src(1, 2)],
    "examples": [
        {"given": {}, "parts": one_room(6), "rows": [{"part": "w1", "within": "br1", "outcome": "pass"}],
         "expect": "pass"},
        {"given": {}, "parts": one_room(5.1), "rows": [{"part": "w1", "within": "br1", "outcome": "fail"}],
         "expect": "fail"},
        {"given": {}, "parts": one_room(5.1, at_grade=True),
         "rows": [{"part": "w1", "within": "br1", "outcome": "pass"}], "expect": "pass"},
        # when_none: Bedroom 2 has no escape opening, so it gets its own failing row
        {"given": {}, "parts": {"sleeping_room": [{"id": "br1"}, {"id": "br2"}],
                                "emergency_escape_opening": one_room(6)["emergency_escape_opening"]},
         "rows": [{"part": "w1", "within": "br1", "outcome": "pass"}, {"within": "br2", "outcome": "fail"}],
         "expect": "fail"},
    ],
    "drafted_by": "claude", "status": "draft",
}


def stairs(*risers):
    return {"stair": [{"id": f"s{n}", "measures": {"stair_riser_height": r}} for n, r in enumerate(risers, 1)]}


RISER = {  # SYNTHETIC: each stair's riser
    "id": "R-1b.synthetic_riser", "kind": "rule", "topic": "egress", "title": "SYNTHETIC stair riser",
    "for_each": "stair", "when_none": "not_applicable", "check": "stair_riser_height <= 8.25",
    "sources": [src(3)],
    "examples": [{"given": {}, "parts": stairs(7), "rows": [{"part": "s1", "outcome": "pass"}], "expect": "pass"},
                 {"given": {}, "parts": stairs(8.5), "rows": [{"part": "s1", "outcome": "fail"}], "expect": "fail"},
                 {"given": {}, "parts": stairs(), "rows": [{"outcome": "not_applicable"}],      # when_none: no stairs
                  "expect": "not_applicable"}],
    "drafted_by": "claude", "status": "draft",
}


def book(*rules):
    return {"district": "R-1b", "rules": [copy.deepcopy(r) for r in rules]}


def opening(oid, room, area=6.0, height=30, at_grade=False, name=None):
    p = {"id": oid, "within": room, "measures": {"opening_net_clear_area": area, "opening_net_clear_height": height,
                                                 "opening_at_grade": at_grade}}
    return p | ({"name": name} if name else {})


def house(*openings, rooms=("br1", "br2")):
    return {"sleeping_room": [{"id": r, "name": f"Bedroom {r[-1]}"} for r in rooms],
            "emergency_escape_opening": list(openings)}


# --- validation -----------------------------------------------------------------------------------------------------

def test_synthetic_rules_validate():
    assert validate(book(AREA, RISER), CTX) == []


@pytest.mark.parametrize("change, words", [
    ({"for_each": "balcony"}, "unknown part kind 'balcony'"),
    ({"for_each": 3}, "unknown part kind 3"),
    ({"within": "stair"}, "can sit within ['sleeping_room', 'basement', 'habitable_attic'], not 'stair'"),
    ({"when_none": "pass"}, "never pass"),
    ({"when_none": None}, "never pass"),
    ({"check": "stair_riser_height <= 8.25"}, "unknown measure 'stair_riser_height'"),       # another kind's
])
def test_bad_part_fields_are_refused(change, words):
    rule = {k: v for k, v in (AREA | change).items() if v is not None}
    assert any(words in p for p in validate(book(rule), CTX)), validate(book(rule), CTX)


def test_within_or_when_none_without_for_each_is_refused():
    for extra in ({"within": "sleeping_room"}, {"when_none": "fail"}):
        rule = {k: v for k, v in RISER.items() if k not in parts.PART_FIELDS} | extra
        assert any("only go with 'for_each'" in p for p in validate(book(rule), CTX))


def test_missing_when_none_is_refused():
    rule = {k: v for k, v in AREA.items() if k != "when_none"}
    assert any("when_none" in p for p in validate(book(rule), CTX))


def test_a_rule_that_must_find_a_part_cant_rule_parts_out():
    """applies_when on a part measure + when_none fail: every opening of a room ruled out would leave the room
    with no failing row. Refused; the split goes inside check (AREA does)."""
    examples = [ex for ex in AREA["examples"] if not ex["parts"]["emergency_escape_opening"][0]["measures"]["opening_at_grade"]]
    rule = AREA | {"applies_when": "not opening_at_grade",
                   "check": "opening_net_clear_area >= 5.7 and opening_net_clear_height >= 24", "examples": examples}
    assert any("can't rule parts out" in p for p in validate(book(rule), CTX))
    none = {"given": {}, "parts": {"sleeping_room": [{"id": "br1"}], "emergency_escape_opening": []},
            "rows": [{"within": "br1", "outcome": "not_applicable"}], "expect": "not_applicable"}
    assert validate(book(rule | {"when_none": "not_applicable", "examples": examples[:2] + [none]}), CTX) == []
    # a building measure in applies_when is fine: it is the same for every part
    use = AREA | {"applies_when": 'use == "one_family_detached"',
                  "examples": [ex | {"given": {"use": "one_family_detached"}} for ex in AREA["examples"]]}
    assert validate(book(use), CTX) == []


def test_a_building_rule_cant_use_a_part_measure():
    rule = {k: v for k, v in RISER.items() if k not in parts.PART_FIELDS}
    assert any("unknown measure 'stair_riser_height'" in p for p in validate(book(rule), CTX))


def test_worked_examples_are_checked_by_the_rows_the_checker_gives():
    wrong_row = copy.deepcopy(AREA)
    wrong_row["examples"][0]["rows"][0]["outcome"] = "fail"
    assert any("example 1: expected rows fail for w1 in br1; got pass for w1 in br1" in p
               for p in validate(book(wrong_row), CTX)), validate(book(wrong_row), CTX)
    missing_row = copy.deepcopy(AREA)
    missing_row["examples"][3]["rows"].pop()            # Bedroom 2's "no escape opening" row left out
    assert any("example 4: expected rows" in p for p in validate(book(missing_row), CTX))
    wrong_answer = copy.deepcopy(AREA)
    wrong_answer["examples"][3]["expect"] = "pass"
    assert any("example 4: expected pass, got fail" in p for p in validate(book(wrong_answer), CTX))
    # a part's measure in `given` (the building's), or another kind's measure on a part, is refused
    in_given = copy.deepcopy(AREA)
    in_given["examples"][0]["given"] = {"opening_net_clear_area": 6}
    assert any("example 1: unknown measures ['opening_net_clear_area'] (a part's measures go in 'parts')" in p
               for p in validate(book(in_given), CTX))
    other_kind = copy.deepcopy(AREA)
    other_kind["examples"][0]["parts"]["emergency_escape_opening"][0]["measures"]["stair_riser_height"] = 7
    assert any("'stair_riser_height' isn't a measure of a emergency escape opening" in p
               for p in validate(book(other_kind), CTX))
    stair_list = copy.deepcopy(AREA)
    stair_list["examples"][0]["parts"]["stair"] = []
    assert any("'parts' has 'stair', not a kind this rule reads" in p for p in validate(book(stair_list), CTX))
    wrong_value = copy.deepcopy(AREA)
    wrong_value["examples"][0]["parts"]["emergency_escape_opening"][0]["measures"]["opening_at_grade"] = "no"
    assert any("wrong kind of value for 'opening_at_grade'" in p for p in validate(book(wrong_value), CTX))


@pytest.mark.parametrize("drop", ["parts", "rows"])
def test_a_per_part_example_needs_its_parts_and_rows(drop):
    rule = copy.deepcopy(AREA)
    del rule["examples"][0][drop]
    assert any(f"example 1: a rule for each part needs {drop!r}" in p for p in validate(book(rule), CTX))


def test_a_whole_building_rule_has_no_parts_in_its_examples():
    rule = {k: v for k, v in RISER.items() if k not in parts.PART_FIELDS} | {
        "check": "stories <= 3", "examples": [{"given": {"stories": 2}, "parts": {}, "expect": "pass"},
                                               {"given": {"stories": 4}, "expect": "fail"}]}
    assert any("example 1: ['parts'] only go with a rule for each part" in p for p in validate(book(rule), CTX))


@pytest.mark.parametrize("rule", [AREA, RISER])
def test_a_per_part_rule_without_a_when_none_example_is_refused(rule):
    """The law's answer for nothing to check (a bedroom with no escape opening; a house with no stairs) is the
    part a reader is likeliest to get wrong, so every per-part rule shows it in a worked example."""
    without = rule | {"examples": [ex for ex in rule["examples"] if not
                                   any("part" not in r for r in ex["rows"])]}
    assert any("no worked example shows when_none" in p for p in validate(book(without), CTX))
    assert validate(book(rule), CTX) == []           # with it, the rule is kept
    # a flag for each part (no check, so no other example needed) needs it too
    flag = {k: v for k, v in rule.items() if k != "check"} | {"kind": "flag", "examples": []}
    assert any("no worked example shows when_none" in p for p in validate(book(flag), CTX))


@pytest.mark.parametrize("check", ["opening_net_clear_area >= 0 * 5.7 and opening_net_clear_height >= 0 * 24",
                                   "opening_net_clear_area >= (5.0 if opening_at_grade else 5.7) or "
                                   "opening_net_clear_height >= 24"])
def test_the_when_none_row_cant_stand_in_for_a_part_that_fails(check):
    """Review round 1: a "none" row fails whatever the check says, so with it as the only failing example a check
    every part passes (written the wrong way round) was kept, and every real escape opening would pass. A part
    that fails the check is needed, and one that passes it."""
    examples = [AREA["examples"][0], AREA["examples"][3]]           # a part that passes; a room with none
    got = validate(book(AREA | {"check": check, "examples": examples}), CTX)
    assert any("a part that passes its check and a part that fails it" in p for p in got), got
    assert any("a part that fails it" in p for p in validate(book(AREA | {"examples": examples}), CTX))
    # a flag has no check to exercise: only its when_none
    flag = {k: v for k, v in AREA.items() if k != "check"} | {"kind": "flag"}
    assert not any("a part that fails it" in p for p in validate(book(flag | {"examples": []}), CTX))


def test_a_none_row_that_is_not_the_when_none_answer_does_not_count():
    rule = AREA | {"applies_when": 'use == "one_family_detached"'}
    examples = [ex | {"given": {"use": "one_family_detached"}} for ex in AREA["examples"][:3]]
    church = {"given": {"use": "church"}, "parts": {"sleeping_room": [{"id": "br1"}], "emergency_escape_opening": []},
              "rows": [{"within": "br1", "outcome": "not_applicable"}], "expect": "not_applicable"}
    assert any("no worked example shows when_none (fail)" in p
               for p in validate(book(rule | {"examples": examples + [church]}), CTX))


def test_the_registry_is_checked(tmp_path):
    assert parts.load_registry()                          # parts.yaml itself is well formed
    bad = tmp_path / "parts.yaml"
    bad.write_text("room: {meaning: m, measures: {stories: {unit: count, meaning: m}}}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="also a building measure"):
        parts.load_registry(bad)                          # refused, never half used
    good = {"room": {"meaning": "m", "measures": {"room_area": {"unit": "sf", "meaning": "m"}}}}
    assert registry_problems(good, {"stories"}) == []
    assert any("also a building measure" in p for p in registry_problems(good, {"room_area"}))
    two = good | {"hall": {"meaning": "m", "measures": {"room_area": {"unit": "sf", "meaning": "m"}}}}
    assert any("also a measure of room" in p for p in registry_problems(two, set()))
    assert any("within unknown part kind" in p for p in
               registry_problems({"room": good["room"] | {"within": ["house"]}}, set()))
    assert any("needs a unit" in p for p in registry_problems(
        {"room": {"meaning": "m", "measures": {"room_area": {"unit": "acres", "meaning": "m"}}}}, set()))


# --- never answered as a whole-building rule; fingerprints unchanged ------------------------------------------------

def test_outcome_never_answers_a_part_rule():
    values = {"opening_net_clear_area": 6, "opening_net_clear_height": 30, "opening_at_grade": False}
    assert part_outcome(AREA, values, ALLOWED) == "pass"
    assert outcome(AREA, values, ALLOWED) == "needs_review"       # code that doesn't know about parts never passes it
    assert outcome({k: v for k, v in AREA.items() if k != "for_each"}, values, ALLOWED) == "needs_review"
    # even one whose formulas use only building measures (which outcome() could evaluate): no whole-building answer
    on_building = RISER | {"check": "stories <= 3"}
    assert part_outcome(on_building, {"stories": 2}, ALLOWED) == "pass"
    assert outcome(on_building, {"stories": 2}, ALLOWED) == "needs_review"


def test_fingerprints_of_rules_without_part_fields_are_unchanged():
    """The pin: test_rulebook's RULE fingerprinted by origin/main's code (2026-11-12) before parts existed."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("test_rulebook_pin", Path(__file__).with_name("test_rulebook.py"))
    pinned = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pinned)
    RULE, RULE_CTX = pinned.RULE, pinned.CTX
    assert approval_hash(RULE, RULE_CTX) == "2ea4dcb1a97da65340669e8525a911ac25218d08f9fb160b859786b25d592ba0"


def test_part_fields_are_fingerprinted():
    base = approval_hash(AREA, CTX)
    assert approval_hash(AREA | {"when_none": "needs_review"}, CTX) != base
    assert approval_hash(AREA | {"for_each": "stair"}, CTX) != base
    assert approval_hash({k: v for k, v in AREA.items() if k != "within"}, CTX) != base


# --- one row per part -----------------------------------------------------------------------------------------------

def by_name(got):
    return {(r["within"]["name"] if r["within"] else None, r["name"]): r["outcome"] for r in got}


def test_one_bad_bedroom_fails_and_is_named():
    got = rows(AREA, house(opening("w1", "br1", name="Window 1"), opening("w5", "br2", area=5.1, name="Window 5")),
               {}, ALLOWED)
    assert by_name(got) == {("Bedroom 1", "Window 1"): "pass", ("Bedroom 2", "Window 5"): "fail"}
    bad = next(r for r in got if r["outcome"] == "fail")
    assert bad["within"] == {"kind": "sleeping_room", "id": "br2", "name": "Bedroom 2"}
    assert bad["values"]["opening_net_clear_area"] == 5.1
    assert rule_result(got) == "fail"


def test_a_bedroom_with_no_escape_opening_gets_its_own_row():
    got = rows(AREA, house(opening("w1", "br1")), {}, ALLOWED)
    none = [r for r in got if r["id"] is None]
    assert [(r["within"]["name"], r["outcome"], r["reason"]) for r in none] == \
        [("Bedroom 2", "fail", "no emergency escape opening")]
    assert rule_result(got) == "fail"
    # the rule's own words decide: "needs review" when that is what it says
    got = rows(AREA | {"when_none": "needs_review"}, house(opening("w1", "br1")), {}, ALLOWED)
    assert rule_result(got) == "needs_review"


def test_a_missing_measure_needs_review_unless_it_fails_whatever():
    got = rows(AREA, house(opening("w1", "br1", height=None), opening("w2", "br2", area=5.1, height=None)), {},
               ALLOWED)
    assert by_name(got) == {("Bedroom 1", "w1"): "needs_review", ("Bedroom 2", "w2"): "fail"}
    nan = rows(AREA, house(opening("w1", "br1", area=float("nan")), opening("w2", "br2")), {}, ALLOWED)
    assert rule_result(nan) == "needs_review"


HEADROOM = {  # SYNTHETIC: a stair's headroom grows with its riser (made up, to need the proof)
    "id": "R-1b.synthetic_headroom", "kind": "rule", "topic": "egress", "title": "SYNTHETIC stair headroom",
    "for_each": "stair", "when_none": "not_applicable", "check": "stair_headroom >= 72 + stair_riser_height",
    "sources": [src(3)], "examples": [], "drafted_by": "claude", "status": "draft"}


def headroom(rule, **measures):
    return rows(rule, {"stair": [{"id": "s1", "measures": measures}]}, {}, ALLOWED)[0]


def test_a_part_that_fails_whatever_its_missing_number_is_fails():
    """The 2026-10-21 proof, for a part: 70 in of headroom against "72 + riser" fails whatever the riser is (a riser
    is never below 0), so the stair fails, and the row says which measure wasn't given."""
    row = headroom(HEADROOM, stair_headroom=70)
    assert (row["outcome"], row["unknown"]) == ("fail", ["stair_riser_height"])
    # 80 in might pass (a riser of 8 or less): needs review, never pass
    assert headroom(HEADROOM, stair_headroom=80)["outcome"] == "needs_review"
    # a missing number the check is NOT truest at 0 for: no proof, needs review
    assert headroom(HEADROOM | {"check": "stair_headroom >= 72 - stair_riser_height"},
                    stair_headroom=70)["outcome"] == "needs_review"
    # a number the proof can't follow (inside an if's test): no proof
    both = HEADROOM | {"check": "stair_headroom >= (72 if stair_riser_height > 7 else 76)"}
    assert headroom(both, stair_headroom=70)["outcome"] == "needs_review"
    # given but unusable (NaN, below 0) isn't "not given": no proof
    assert headroom(HEADROOM, stair_headroom=70, stair_riser_height=-1)["outcome"] == "needs_review"
    assert headroom(HEADROOM, stair_headroom=70, stair_riser_height=float("nan"))["outcome"] == "needs_review"
    # an unknown in review_when: no proof (the proof never runs over the rule's own doubt)
    doubt = HEADROOM | {"review_when": [{"when": "stair_riser_height > 9", "reason": "a tall riser"}]}
    assert headroom(doubt, stair_headroom=70)["outcome"] == "needs_review"


def test_the_part_proof_is_the_checkers_proof():
    """The shared proof's settings (rulebook.unknown_settings); that parts.rows and check.fails_whatever both use it
    is pinned by design_checker/tests/test_each_part.py::test_one_proof_for_parts_and_zoning_rows."""
    from rule_format import rulebook
    assert rulebook.unknown_settings(HEADROOM, ["stair_riser_height"], parts.measure_kinds("stair")) == \
        [{"stair_riser_height": 0}]
    assert rulebook.unknown_settings(HEADROOM | {"kind": "flag"}, ["stair_riser_height"], parts.measure_kinds("stair")) is None


@pytest.mark.parametrize("given", [
    {},                                                       # nothing read
    {"sleeping_room": [{"id": "br1"}]},                       # the openings not read
    {"emergency_escape_opening": []},                         # the rooms not read: not "no rooms"
    {"sleeping_room": {"br1": {}}, "emergency_escape_opening": []},   # not a list
    None,
])
def test_parts_not_read_need_review(given):
    got = rows(AREA, given, {}, ALLOWED)
    assert [r["outcome"] for r in got] == ["needs_review"] and "aren't read yet" in got[0]["reason"]


def test_no_sleeping_rooms_is_not_applicable_and_no_stairs_as_the_rule_says():
    assert [r["outcome"] for r in rows(AREA, house(rooms=()), {}, ALLOWED)] == ["not_applicable"]
    assert [r["outcome"] for r in rows(RISER, {"stair": []}, {}, ALLOWED)] == ["not_applicable"]
    assert rule_result(rows(RISER | {"when_none": "fail"}, {"stair": []}, {}, ALLOWED)) == "fail"


@pytest.mark.parametrize("given, words", [
    (house(opening("w1", "br1"), opening("w1", "br2")), "two parts have the id 'w1'"),
    (house(opening("w1", "br1"), {"within": "br2"}), "#2 has no id"),
    (house(opening("w1", "br1"), "w2"), "#2 isn't a part"),
    (house(opening("w1", "br1"), opening("w2", "br9")), "w2 isn't within any sleeping room that was read"),
    (house(opening("w1", "br1"), {"id": "w2"}), "w2 isn't within any sleeping room that was read"),
    (house(opening("w1", "br1"), {"id": "w2", "within": "br2", "measures": [5.7]}), "measures aren't a mapping"),
    ({"sleeping_room": [{"id": "br1"}, {"id": "br1"}], "emergency_escape_opening": [opening("w1", "br1")]},
     "two parts have the id 'br1'"),
    # within an id two parts of another kind share (two stairs "x"): never dropped
    (house(opening("w1", "br1"), opening("w2", "x", area=1)) | {"stair": [{"id": "x"}, {"id": "x"}]},
     "w2 isn't within any sleeping room that was read"),
    (house(opening("w1", "br1"), opening("w2", ["br2"])), "what it is within isn't an id"),
    (house(opening("w1", "br1"), opening("w2", {"id": "br2"})), "what it is within isn't an id"),
])
def test_a_malformed_part_is_never_dropped(given, words):
    got = rows(AREA, given, {}, ALLOWED)
    assert any(r["outcome"] == "needs_review" and words in (r["reason"] or "") for r in got), got
    assert rule_result(got) in ("needs_review", "fail")


@pytest.mark.parametrize("bad", [dict(opening("w", "br1"), measures="x"), dict(opening("w", "br1"), id=""),
                                 dict(opening("w", "br1"), within=None) | {"id": 5}])
def test_a_room_whose_opening_cant_be_read_is_never_said_to_have_none(bad):
    got = rows(AREA, house(bad, opening("w2", "br2")), {}, ALLOWED)
    room1 = [r for r in got if r["within"] and r["within"]["id"] == "br1"]
    assert [(r["outcome"], r["reason"]) for r in room1] in ([("needs_review", "an emergency escape opening that may be in it can't be read")],
                                                            [])
    assert not any(r["outcome"] == "fail" for r in got)        # br1 has an opening: unreadable, not missing
    assert rule_result(got) == "needs_review"


def test_an_opening_that_says_no_room_keeps_every_room_from_none():
    got = rows(AREA, house({"id": "w9", "measures": {}}, rooms=("br1", "br2")), {}, ALLOWED)
    assert not any(r["outcome"] == "fail" for r in got) and rule_result(got) == "needs_review"


def test_an_opening_within_a_mistyped_room_keeps_every_room_from_none():
    got = rows(AREA, {"sleeping_room": [{"id": "B1", "name": "Bedroom 1"}],
                      "emergency_escape_opening": [opening("o1", "b1")]}, {}, ALLOWED)
    assert not any(r["outcome"] == "fail" for r in got) and rule_result(got) == "needs_review"


def test_a_proposed_measure_cant_borrow_a_part_measure_name():
    ctx = copy.deepcopy(CTX)
    ctx.proposed = {"stair_riser_height": {"unit": "in", "meaning": "m"}}
    lot_rule = {k: v for k, v in RISER.items() if k not in parts.PART_FIELDS}
    assert any("is a measure of a part" in p and "for each stair" in p for p in validate(book(lot_rule), ctx))
    assert validate(book(RISER), ctx) == []           # the stair rule itself still may


def test_two_openings_sharing_an_id_dont_make_their_room_fail():
    got = rows(AREA, house(opening("w", "br1"), opening("w", "br1"), opening("w2", "br2")), {}, ALLOWED)
    assert not any(r["outcome"] == "fail" for r in got) and rule_result(got) == "needs_review"


def test_a_problem_shared_by_two_kinds_is_said_once():
    got = rows(AREA, {"sleeping_room": [{"id": "x"}], "emergency_escape_opening": [opening("x", "x")]}, {}, ALLOWED)
    reasons = [r["reason"] for r in got if r["reason"]]
    assert reasons.count("two parts have the id 'x'") == 1


def test_a_part_cant_change_a_building_value():
    rule = AREA | {"applies_when": 'use == "one_family_detached"'}
    sneaky = opening("w1", "br1", area=1)
    sneaky["measures"]["use"] = "church"                     # not an opening's measure: ignored
    assert by_name(rows(rule, house(sneaky, rooms=("br1",)), {"use": "one_family_detached"}, ALLOWED)) == \
        {("Bedroom 1", "w1"): "fail"}


def test_a_building_value_never_stands_in_for_a_part_measure():
    got = rows(AREA, house({"id": "w1", "within": "br1"}, rooms=("br1",)),
               {"opening_net_clear_area": 9, "opening_net_clear_height": 30, "opening_at_grade": False}, ALLOWED)
    assert by_name(got) == {("Bedroom 1", "w1"): "needs_review"}


def test_none_follows_the_rule_applying_to_the_building():
    rule = AREA | {"applies_when": 'use == "one_family_detached"'}
    empty = house(rooms=("br1",))
    assert rule_result(rows(rule, empty, {"use": "church"}, ALLOWED)) == "not_applicable"
    assert rule_result(rows(rule, empty, {"use": "one_family_detached"}, ALLOWED)) == "fail"
    assert rule_result(rows(rule, empty, {}, ALLOWED)) == "needs_review"      # use unknown: never a pass


def test_an_invalid_rule_gives_a_review_row():
    got = rows(AREA | {"for_each": "balcony"}, house(), {}, ALLOWED)
    assert [r["outcome"] for r in got] == ["needs_review"]


@pytest.mark.parametrize("change", [{"check": "stair_riser_height <="}, {"review_when": [{"when": "((", "reason": "r"}]},
                                    {"review_when": [{"reason": "no when"}]}])
def test_an_unreadable_rule_gives_a_review_row_never_a_crash(change):
    for given in ({"stair": [{"id": "s1", "measures": {"stair_riser_height": 7}}]}, {"stair": []}):
        assert [r["outcome"] for r in rows(RISER | change, given, {}, ALLOWED)] == ["needs_review"]


def test_rule_result():
    o = lambda *xs: [{"outcome": x} for x in xs]
    assert rule_result(o("pass", "fail", "needs_review")) == "fail"
    assert rule_result(o("pass", "needs_review", "not_applicable")) == "needs_review"
    assert rule_result(o("pass", "not_applicable")) == "pass"
    assert rule_result(o("not_applicable")) == "not_applicable"
    assert rule_result([]) == "needs_review"


def test_a_broken_parts_file_is_a_problem_never_a_crash(monkeypatch):
    def refuse(*args, **kwargs):
        raise ValueError("parts.yaml: part kind '::': a name is lowercase letters, digits and _")
    monkeypatch.setattr(parts, "_REGISTRY", None)
    monkeypatch.setattr(parts, "load_registry", refuse)
    lot_rule = {k: v for k, v in RISER.items() if k not in parts.PART_FIELDS} | {"check": "stories <= 3"}
    for rule in (lot_rule, RISER):
        got = validate(book(rule), CTX)
        assert any("parts.yaml can't be read" in p for p in got), got
