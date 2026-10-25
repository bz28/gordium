"""The drafting gaps after stage 1 (R-2c's footnoted cells, footnote 7, residential parking, the §325-16C height bonus,
§325-18B's eaves), fixed in code and instructions before any re-draft: for each, a correct answer written by hand is
accepted and the known-bad forms are refused or kept for a person. No API call."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_drafting import bound, cli, drafter, slot, template, unit  # noqa: E402

from rule_format.rulebook import apply_relaxes, outcome  # noqa: E402

COVERAGE = "Maximum lot coverage by buildings"
HEIGHT = "Maximum Building Height [fn10]"
YARDS = "Yard Dimensions"
REAR = "Rear (minimum, % of depth or feet, whichever is less)"
LOT_SIZE = "Minimum Lot Size [fn3]"
OPENING = ("C. Height and open space. In any district, any main building may be erected to a height in excess of that "
           "specified for the district, provided that:")
YARDS_GROW = ("(1) Each required front, side and rear yard is increased one foot on the ground for each one foot of "
              "such additional height.")
TEN_PERCENT = ("(3) In each district, the number of additional feet may not exceed 10% of the maximum building height "
               "allowed in that district.")


@pytest.fixture(scope="module")
def inputs():
    return cli.Inputs()


def law(text, piece="325-16C"):
    return {"document": "law", "page": 0, "piece": piece, "text": text}


def chart_note(n, text, page=3):
    return {"document": "chart", "page": page, "piece": f"fn{n}", "text": text}


def judge(inputs, uid, templates, drafted=None):
    u = unit(inputs, uid)
    context = drafter.gather_context(u, inputs.law, {"notes": inputs.notes}, inputs.definitions)
    if drafted is not None:
        context |= {"drafted": drafted}
    return drafter.check_answer({"templates": templates, "no_rule_reason": ""}, u, context, inputs.law, inputs.ctx,
                                inputs.columns, inputs.cells, inputs.notes, "rule_drafting/test")


def coverage(name, number, uses_when, fn=("12",), count=3):
    return template(name, "building_area <= {pct} * lot_area",
                    [slot("pct", "Percent of lot area", number, count, True, fn, section=COVERAGE)],
                    [({"building_area": "{pct} * 1000", "lot_area": "1000", "use": uses_when[1]}, "pass"),
                     ({"building_area": "{pct} * 1000 + 1", "lot_area": "1000", "use": uses_when[1]}, "fail")],
                    quotes=[chart_note(12, "(12) The first number applies to one-family detached dwellings, one-family "
                                           "detached zero lot line dwellings, and other uses; the second number applies "
                                           "to one-family semi- detached dwelling and two-family dwellings; and the "
                                           "third number applies to one-family attached dwellings.")] if fn else [],
                    applies_when=uses_when[0])


PLAIN = template("max_coverage", "building_area <= {pct} * lot_area",
                 [slot("pct", "Percent of lot area", 1, 1, True, section=COVERAGE)],
                 [({"building_area": "{pct} * 1000", "lot_area": "1000"}, "pass"),
                  ({"building_area": "{pct} * 1000 + 1", "lot_area": "1000"}, "fail")])
FIRST = coverage("coverage_first", 1, ('use not in ["one_family_semi_detached", "two_family", "one_family_attached"]',
                                       "one_family_detached"))
SECOND = coverage("coverage_second", 2, ('use in ["one_family_semi_detached", "two_family"]', "two_family"))
THIRD = coverage("coverage_third", 3, ('use == "one_family_attached"', "one_family_attached"))


def test_a_cell_filled_by_the_template_for_its_form_is_no_gap_and_a_partly_used_cell_stays_one(inputs):
    """R-2C's coverage cell '35%/40% /50% [fn12]' doesn't fit the plain template; the three fn12 templates fill it
    (one number per use). It was still listed for a person ("has 3 numbers, the rule expects 1"), 469 such lines in
    the log. With a number of the cell unused (no rule for attached houses), it stays a gap: never silent."""
    got = judge(inputs, "chart-p3-maximum_lot_coverage_by_buildings", [PLAIN, FIRST, SECOND, THIRD])
    assert len(got["rules"]["R-2c"]) == 3
    assert not [g for g in got["unresolved"] if g["rule"].startswith("R-2c.")]
    got = judge(inputs, "chart-p3-maximum_lot_coverage_by_buildings", [PLAIN, FIRST, SECOND])
    assert [g["rule"] for g in got["unresolved"] if g["rule"].startswith("R-2c.")] == ["R-2c.max_coverage"]
    every_use = FIRST | {"applies_when": ""}         # every use covered, but the cell's third number used by none
    got = judge(inputs, "chart-p3-maximum_lot_coverage_by_buildings", [PLAIN, every_use, SECOND])
    assert [g["rule"] for g in got["unresolved"] if g["rule"].startswith("R-2c.")] == ["R-2c.max_coverage"]


def test_the_use_list_says_which_uses_are_buildings_of_several_dwelling_units(inputs):
    """The residential parking drafts kept passing semi-detached and attached houses (one unit's sleeping rooms
    can't count a building of several units) across three attempts; the drafter is now told which uses those are,
    from the same definitions the check reads."""
    lines = [x for x in inputs.system().splitlines() if x.startswith("- ") and "several dwelling units" in x]
    assert sorted(x.split(":")[0][2:] for x in lines) == ["multiple_family", "one_family_attached",
                                                         "one_family_semi_detached", "two_family"]


PARKING = "Residential"


def test_a_parking_rule_for_one_dwelling_unit_is_kept_and_one_passing_a_building_of_several_is_refused(inputs):
    rows = ("First three bed or sleeping rooms per dwelling unit", "4-5 bed or sleeping rooms per dwelling unit",
            "Each additional bed or sleeping room")
    slots = [slot(n, r, page=14, section=PARKING) for n, r in zip(("first", "second", "extra"), rows)]
    check = ("parking_spaces >= ({first} if sleeping_rooms <= 3 else {second} if sleeping_rooms <= 5 "
             "else {second} + {extra} * (sleeping_rooms - 5))")
    examples = [({"use": "one_family_detached", "sleeping_rooms": "3", "parking_spaces": "{first}"}, "pass"),
                ({"use": "one_family_detached", "sleeping_rooms": "3", "parking_spaces": "{first} - 1"}, "fail"),
                ({"use": "one_family_detached", "sleeping_rooms": "5", "parking_spaces": "{second}"}, "pass"),
                ({"use": "one_family_detached", "sleeping_rooms": "5", "parking_spaces": "{second} - 1"}, "fail"),
                ({"use": "one_family_detached", "sleeping_rooms": "7", "parking_spaces": "{second} + 2 * {extra}"}, "pass"),
                ({"use": "one_family_detached", "sleeping_rooms": "7", "parking_spaces": "{second} + 2 * {extra} - 1"}, "fail")]
    numbers = [bound(3, "slot_row_label", slot="first"), bound(5, "slot_row_label", slot="second")]
    good = template("parking_one_dwelling_unit", check, slots, examples, numbers=numbers,
                    applies_when='use in ["one_family_detached", "one_family_detached_zero_lot_line"]')
    got = judge(inputs, "chart-p14-residential", [good])
    assert set(got["rules"]) >= {"R-1a", "R-1b", "R-2a", "R-2c"} and got["rejected"] == [], got["problems"][:2]
    # the uses the rule leaves out (buildings of several units, other uses: §325-20) get a code-made flag, never
    # silently unchecked: needs review for them, and not applicable where the drafted rule decides
    flag = next(r for r in got["rules"]["R-2a"] if r["id"].endswith("_undecided_uses"))
    assert flag["kind"] == "flag" and drafter.validate({"district": "R-2a", "rules": [flag]}, inputs.ctx) == []
    # review round 11: code made it, so it says so (not the model's name), and names the drafted rule it came from
    assert flag["drafted_by"] == "rule_drafting/chart_code"
    assert "Made from R-2a." in flag["notes"]
    for use, want in (("two_family", "needs_review"), ("one_family_attached", "needs_review"), ("church", "needs_review"),
                      ("one_family_detached", "not_applicable")):
        assert outcome(flag, {"use": use}, inputs.ctx.allowed()) == want, use
    bad = good | {"applies_when": 'use in ["one_family_detached", "one_family_semi_detached"]'}
    assert "it passes one_family_semi_detached" in " ".join(judge(inputs, "chart-p14-residential", [bad])["problems"])


def bonus(applies_when=None, relaxes="height"):
    grow = "(building_height - {height})"
    when = applies_when if applies_when is not None else (
        f"front_yard >= {{front}} + {grow} and side_yard_larger >= {{side_one}} + {grow}"
        f" and side_yard_smaller >= {{side_other}} + {grow}"
        f" and rear_yard >= max(min({{pct}} * lot_depth, {{cap}}), 20) + {grow}")
    big = {"building_height": "{height} + 3", "front_yard": "{front} + 3", "side_yard_larger": "{side_one} + 3",
           "side_yard_smaller": "{side_other} + 3", "lot_depth": "100", "rear_yard": "max(min({pct} * 100, {cap}), 20) + 3"}
    return template(
        "height_bonus", "building_height <= {height} + 0.1 * {height}",
        [slot("height", "Height in feet", section=HEIGHT), slot("front", "Front (minimum)"),
         slot("side_one", "Side (one side minimum)"), slot("side_other", "Side (other side minimum)"),
         slot("pct", REAR, 1, 2, True, ["16"]), slot("cap", REAR, 2, 2, False, ["16"])],
        [(big, "pass"), ({k: v.replace("+ 3", "+ 5") for k, v in big.items()}, "fail"),     # 5 ft over: past 10%
         (big | {"front_yard": "{front}"}, "not_applicable"),
         (big | {"lot_depth": "1000", "rear_yard": "{cap} + 3"}, "pass"),
         (big | {"lot_depth": "40", "rear_yard": "23"}, "pass")],
        quotes=[law(OPENING), law(YARDS_GROW), law(TEN_PERCENT), chart_note(10, "See §325-16."),
                chart_note(16, "But not less than 20 ft.")],
        numbers=[bound(0.1, "law_quote", quote=2), bound(20, "slot_footnote", slot="cap", footnote="16")],
        applies_when=when) | {"relaxes": relaxes}


def test_the_height_bonus_is_one_rule_that_relaxes_each_districts_chart_height(inputs):
    """§325-16C allows up to 10% more height when every yard grows by the extra height. Drafted as parts (each
    'when taller, this yard is larger') the chart's 35 ft still failed a 37 ft house with every yard enlarged, where
    the law (and every hand key) passes it. As one relaxing rule, linked by code to the district's chart rule."""
    drafted = cli.drafted_rules(inputs)
    got = judge(inputs, "325-16C", [bonus()], drafted)
    assert got["rejected"] == [], got["problems"][:2]
    r1a = got["rules"]["R-1a"][0]
    chart = [r for r in drafted["R-1a"] if r["id"] == r1a["relaxes"]]
    assert len(chart) == 1 and chart[0]["check"] == "building_height <= 35"
    yards = {"front_yard": 25 + 2, "side_yard_larger": 10 + 2, "side_yard_smaller": 10 + 2, "rear_yard": 25 + 2,
             "lot_depth": 100}
    # as the AI drafted it, the bonus never passes on its own word (round 10): needs review until proven
    drafted_only = {r["id"]: r for r in apply_relaxes(drafted["R-1a"] + [r1a])}[r1a["relaxes"]]
    assert outcome(drafted_only, yards | {"building_height": 37}, inputs.ctx.allowed()) == "needs_review"
    height = {r["id"]: r for r in apply_relaxes(drafted["R-1a"] + [r1a], frozenset({r1a["id"]}))}[r1a["relaxes"]]
    assert outcome(height, yards | {"building_height": 37}, inputs.ctx.allowed()) == "pass"
    assert outcome(height, yards | {"building_height": 37, "front_yard": 26}, inputs.ctx.allowed()) == "fail"
    assert outcome(height, {"building_height": 37}, inputs.ctx.allowed()) == "needs_review"     # yards unknown
    assert outcome(height, yards | {"building_height": 39}, inputs.ctx.allowed()) == "fail"     # over 10%


def test_a_relaxing_rule_without_its_conditions_or_its_target_is_never_kept(inputs):
    drafted = cli.drafted_rules(inputs)
    loose = judge(inputs, "325-16C", [bonus(applies_when="")], drafted)
    assert loose["rules"] == {} and "needs its conditions" in " ".join(loose["problems"])
    wrong = judge(inputs, "325-16C", [bonus(relaxes="nothing")], drafted)
    assert wrong["rules"] == {} and "must be the name of one of this template's slots" in " ".join(wrong["problems"])
    alone = judge(inputs, "325-16C", [bonus()], {})            # the chart's height rule isn't drafted: nothing widens
    assert alone["rules"] == {} and "not drafted for this district" in " ".join(alone["problems"])


FN4 = ("(4) For the first occupant; +500 sf for each additional occupant. (Could remove notes 1 - 6, if a single "
       "standard is created for these uses.)")
FN7 = "(7) For the first 1-3 units; +750 sf for each additional unit; +500 sf per room let for profit."
OCCUPANTS = {"name": "occupants", "unit": "count", "meaning": "Occupants of the dwelling units on the lot"}


def lot_area(name, row, fn, quote, check, examples, numbers, use, new=()):
    return template(name, check, [slot("area", row, footnotes=[fn], section=LOT_SIZE)], examples,
                    quotes=[chart_note(fn, quote), chart_note(3, "(3) See §325-8(B)(1).")], numbers=numbers,
                    applies_when=f'use == "{use}"',
                    new_measures=new)


def test_a_footnoted_lot_size_is_drafted_with_its_note_applied_and_never_with_it_dropped(inputs):
    """R-2C's '2,500 sf [fn4]' (+500 sf per occupant after the first) and R-3A's '6,000 sf [fn7]' (+750 sf per unit
    after three, +500 sf per room let) got no rule: the template written for the plain cells can't take a note.
    A template for the note's form is kept for the districts whose cell carries it; one that quotes the note and
    leaves out what it adds is refused."""
    good = lot_area("lot_area_one_family_detached_fn4", "One-family dwelling, detached", "4", FN4,
                    "lot_area >= {area} + 500 * max(occupants - 1, 0)",
                    [({"use": "one_family_detached", "occupants": "1", "lot_area": "{area}"}, "pass"),
                     ({"use": "one_family_detached", "occupants": "3", "lot_area": "{area} + 999"}, "fail"),
                     ({"use": "one_family_detached", "occupants": "3", "lot_area": "{area} + 1000"}, "pass")],
                    [bound(500, "slot_footnote", slot="area", footnote="4"),
                     bound(1, "slot_footnote", slot="area", footnote="4")], "one_family_detached", [OCCUPANTS])
    got = judge(inputs, "chart-p3-minimum_lot_size", [good])
    assert got["rejected"] == [] and [r["check"] for r in got["rules"]["R-2c"]] == [
        "lot_area >= 2500 + 500 * max(occupants - 1, 0)"], got["problems"][:2]
    dropped = good | {"check": "lot_area >= {area}", "numbers": [], "new_measures": [],
                      "examples": [{"given": [{"measure": "use", "value": "one_family_detached"},
                                              {"measure": "lot_area", "value": v}], "expect": e}
                                   for v, e in (("{area}", "pass"), ("{area} - 1", "fail"))]}
    assert judge(inputs, "chart-p3-minimum_lot_size", [dropped])["rules"] == {}
    units = "lot_area >= {area} + 750 * max(dwelling_units - 3, 0) + 500 * rooms_let_for_profit"
    fn7 = lot_area("lot_area_multiple_family_fn7", "Multiple family dwelling, new construction", "7", FN7, units,
                   [({"use": "multiple_family", "dwelling_units": "3", "rooms_let_for_profit": "0",
                      "lot_area": "{area}"}, "pass"),
                    ({"use": "multiple_family", "dwelling_units": "5", "rooms_let_for_profit": "0",
                      "lot_area": "{area} + 1499"}, "fail"),
                    ({"use": "multiple_family", "dwelling_units": "5", "rooms_let_for_profit": "2",
                      "lot_area": "{area} + 2500"}, "pass"),
                    ({"use": "multiple_family", "dwelling_units": "5", "rooms_let_for_profit": "2",
                      "lot_area": "{area} + 2499"}, "fail")],
                   [bound(750, "slot_footnote", slot="area", footnote="7"),
                    bound(3, "slot_footnote", slot="area", footnote="7"),
                    bound(500, "slot_footnote", slot="area", footnote="7")], "multiple_family")
    got = judge(inputs, "chart-p3-minimum_lot_size", [fn7])
    assert got["rejected"] == [] and "R-3a" in got["rules"], got["problems"][:2]


def test_a_notes_amounts_are_its_numbers_with_units_not_its_markers_or_pointers():
    assert drafter.note_amounts(FN4) == [500]
    assert drafter.note_amounts(FN7) == [3, 750, 500]
    assert drafter.note_amounts("(13) 50% of the developable lot area, after the required setbacks") == [0.5]
    assert drafter.note_amounts("(3) See §325-8(B)(1).") == [] and drafter.note_amounts("(16) But not less than 20 ft.") == [20]


EAVES_TEXT = ("The space in any required yard shall be open and unobstructed except for ordinary projections of "
              "windowsills, belt courses, cornices, eaves and other architectural features; provided, however, that "
              "such features shall not project more than two feet into any required yard.")


def test_eaves_are_checked_against_each_yard_less_two_feet_and_reviewed_where_the_yard_is_enlarged(inputs):
    """§325-18B: features may project at most 2 ft into a required yard. Drafted as an always-review flag, every
    design with eaves needed review (the keys pass or fail them). Checked with the yards measured to the eaves; a
    building over the chart height (§325-16C enlarges its required yards) goes to review, never a looser pass."""
    grow = [("front", "Front (minimum)", "front_yard_eaves"),
            ("side_one", "Side (one side minimum)", "side_yard_larger_eaves"),
            ("side_other", "Side (other side minimum)", "side_yard_smaller_eaves")]
    check = " and ".join(f"{m} >= {{{n}}} - 2" for n, _, m in grow)
    ok = {m: f"{{{n}}} - 2" for n, _, m in grow} | {"building_height": "{height}"}
    eaves = template("eaves_into_yards", check,
                     [slot(n, r) for n, r, _ in grow] + [slot("height", "Height in feet", section=HEIGHT)],
                     [(ok, "pass")] + [(ok | {m: f"{{{n}}} - 2.5"}, "fail") for n, _, m in grow],
                     quotes=[law(EAVES_TEXT, "325-18B"), chart_note(10, "See §325-16.")],
                     numbers=[bound(2, "law_quote", quote=0)])
    eaves["review_when"] = [{"when": "building_height > {height}",
                             "reason": "§325-16C enlarges the required yards of a building over the chart height"}]
    got = judge(inputs, "325-18B", [eaves])
    assert got["rejected"] == [] and "R-1a" in got["rules"], got["problems"][:2]
    rule = got["rules"]["R-1a"][0]
    tall = {"front_yard_eaves": 24, "side_yard_larger_eaves": 9, "side_yard_smaller_eaves": 9, "building_height": 37}
    assert outcome(rule, tall | {"building_height": 30}, inputs.ctx.allowed()) == "pass"
    assert outcome(rule, tall, inputs.ctx.allowed()) == "needs_review"


def test_a_later_session_that_never_answered_does_not_erase_the_last_answered_one(inputs, monkeypatch):
    """The gap re-draft's lot size: three calls cut off at the output limit (no answer) replaced 33 rules by none.
    A session with no whole answer says nothing about the law; the last answered session stands, in a replay and
    in the draft run itself."""
    old = [{"unit": "u", "attempt": 1, "stop_reason": "end_turn", "answer": "old"}]
    cut = [{"unit": "u", "attempt": k, "stop_reason": "max_tokens", "answer": ""} for k in (1, 2, 3)]
    new = [{"unit": "u", "attempt": 1, "stop_reason": "max_tokens"}, {"unit": "u", "attempt": 2, "stop_reason": "end_turn"}]
    monkeypatch.setattr(cli, "run_records", lambda i: old + cut)
    assert cli.last_recorded_attempts(inputs, "u") == old
    monkeypatch.setattr(cli, "run_records", lambda i: old + cut + new)
    assert cli.last_recorded_attempts(inputs, "u") == new         # answered (on its retry): the newest stands
    monkeypatch.setattr(cli, "run_records", lambda i: cut)
    assert cli.last_recorded_attempts(inputs, "u") == cut         # nothing ever answered: the newest, which fails



def test_a_flag_exempts_a_notes_amount_only_where_it_is_kept_and_cites_the_note_whole(inputs):
    """Round 10 (P0): the exemption was read from the raw answer and by substring, so a refused flag quoting the
    fragment 'each additional' let R-2C keep 'lot_area >= 2500' without fn4's +500 sf per extra occupant. Now only
    a flag kept for that district, citing the note whole, sends the note to a person."""
    dropped = lot_area("lot_area_one_family_detached_fn4", "One-family dwelling, detached", "4", FN4,
                       "lot_area >= {area}",
                       [({"use": "one_family_detached", "lot_area": "{area}"}, "pass"),
                        ({"use": "one_family_detached", "lot_area": "{area} - 1"}, "fail")], [], "one_family_detached")
    fragment = template("broken_flag", "", [], [], kind="flag", quotes=[chart_note(4, "each additional")])
    got = judge(inputs, "chart-p3-minimum_lot_size", [dropped, fragment])
    assert "R-2c" not in got["rules"]
    elsewhere = template("fn4_flag_r3a", "", [], [], kind="flag", applies_when='district == "R-3a"',
                         quotes=[chart_note(4, FN4)])
    got = judge(inputs, "chart-p3-minimum_lot_size", [dropped, elsewhere])
    assert not any(r["id"].endswith("_fn4") for r in got["rules"].get("R-2c", []))
    part = template("fn4_part_flag", "", [], [], kind="flag",
                    quotes=[chart_note(4, "(Could remove notes 1 - 6, if a single standard is created for these uses.)")])
    got = judge(inputs, "chart-p3-minimum_lot_size", [dropped, part])          # kept, but cites only part of fn4
    assert any(r["id"].endswith("part_flag") for r in got["rules"].get("general", []))
    assert not any(r["id"].endswith("_fn4") for r in got["rules"].get("R-2c", []))
    whole = template("fn4_flag", "", [], [], kind="flag", quotes=[chart_note(4, FN4)])
    got = judge(inputs, "chart-p3-minimum_lot_size", [dropped, whole])
    assert [r["check"] for r in got["rules"]["R-2c"] if r["id"].endswith("_fn4")] == ["lot_area >= 2500"]


def test_a_relaxing_rule_missing_a_condition_its_law_names_is_never_kept(inputs):
    """Round 10 (P0): a bonus whose applies_when has only the front yard was kept in all nine districts and passed a
    37 ft house with 1 ft side and rear yards. Every yard the quoted law names must be a condition that decides it."""
    drafted = cli.drafted_rules(inputs)
    front_only = bonus(applies_when="front_yard >= {front} + (building_height - {height})")
    front_only["slots"] = [x for x in front_only["slots"] if x["name"] in ("height", "front")]
    front_only["numbers"] = [front_only["numbers"][0]]
    front_only["quotes"] = [q for q in front_only["quotes"] if "20 ft" not in q["text"]]
    front_only["examples"] = [{"given": [g for g in ex["given"] if g["measure"] in ("building_height", "front_yard")],
                               "expect": ex["expect"]} for ex in front_only["examples"][:3]]
    got = judge(inputs, "325-16C", [front_only], drafted)
    assert got["rules"] == {} and "isn't in applies_when" in " ".join(got["problems"]), got["problems"][:1]
    # named but deciding nothing (any side yard meets it): refused too
    stub = bonus(applies_when=bonus()["applies_when"].replace(
        "side_yard_smaller >= {side_other} + (building_height - {height})", "side_yard_smaller >= 0"))
    stub["slots"] = [x for x in stub["slots"] if x["name"] != "side_other"]
    stub["examples"] = [{"given": [g | ({"value": "{side_one} + 3"} if g["measure"] == "side_yard_smaller" else {})
                                   for g in ex["given"]], "expect": ex["expect"]} for ex in stub["examples"]]
    got = judge(inputs, "325-16C", [stub], drafted)
    assert got["rules"] == {} and "it still applies" in " ".join(got["problems"]), got["problems"][:1]


def test_the_bonus_links_to_the_height_rule_not_another_rule_citing_the_height_cell(inputs):
    """Round 10 (P2): the eaves rule cites 'Height in feet' too (its review above the chart height); the bonus was
    then refused everywhere as 'cited by several rules'. It links to the rule limiting building_height."""
    grow = [("front", "Front (minimum)", "front_yard_eaves")]
    eaves = template("eaves_into_yards", "front_yard_eaves >= {front} - 2",
                     [slot("front", "Front (minimum)"), slot("height", "Height in feet", section=HEIGHT)],
                     [({"front_yard_eaves": "{front} - 2", "building_height": "{height}"}, "pass"),
                      ({"front_yard_eaves": "{front} - 2.5", "building_height": "{height}"}, "fail")],
                     quotes=[law(EAVES_TEXT, "325-18B"), chart_note(10, "See §325-16.")],
                     numbers=[bound(2, "law_quote", quote=0)])
    eaves["review_when"] = [{"when": "building_height > {height}", "reason": "x"}]
    drafted = cli.drafted_rules(inputs)
    for d, rules in judge(inputs, "325-18B", [eaves])["rules"].items():
        drafted[d] = drafted.get(d, []) + rules
    got = judge(inputs, "325-16C", [bonus()], drafted)
    assert got["rejected"] == [] and all(r["relaxes"].endswith(".max_height_ft") for rs in got["rules"].values() for r in rs)


def test_a_gap_stays_when_the_kept_rules_dont_cover_every_use_the_failed_template_did(inputs):
    """Round 10 (P2): with fn12's first number narrowed to one-family detached (the note also gives it to zero lot
    line and other uses), all three numbers were used and R-2C's gap vanished, leaving those uses unchecked."""
    narrow = FIRST | {"applies_when": 'use == "one_family_detached"'}
    got = judge(inputs, "chart-p3-maximum_lot_coverage_by_buildings", [PLAIN, narrow, SECOND, THIRD])
    assert [g["rule"] for g in got["unresolved"] if g["rule"].startswith("R-2c.")] == ["R-2c.max_coverage"]



def _recorded(inputs, uid):
    import json
    return json.loads(cli.last_recorded_attempts(inputs, uid)[-1]["answer"])


def _stage1(inputs, uid):
    """The unit's last answer before the 2026-10-25 re-drafts: stage 1's (the known-bad forms these tests pin)."""
    import json
    session = [x for x in cli.recorded_sessions(inputs, uid) if cli.answered(x) and str(x[0].get("date")) < "2026-10-25"][-1]
    return json.loads(session[-1]["answer"])


def test_the_height_bonus_drafted_in_parts_is_refused_and_one_relaxing_rule_is_kept(inputs):
    """Stage 1's §325-16C answer drafted the bonus as parts ("when taller than the chart's height: this yard is
    larger", "the extra feet at most 10%"): the chart rule still failed a 37 ft house with every yard enlarged.
    The guard refuses the parts that limit the measure above the chart's limit, not the stories part (a different
    measure). In check_answer the stories part shares the refused parts' condition, so all-or-none drops it with
    them: none of stage 1's answer is kept, and a person checks §325-16C. A single relaxing rule is not refused."""
    old = _stage1(inputs, "325-16C")
    parts = [x for x in old["templates"] if "{height_ft}" in (x.get("applies_when") or "")]
    assert len(parts) == 5
    refused = {x["id_suffix"] for x in parts if drafter.exception_in_parts(x)}
    assert refused == {"extra_height_limit", "extra_height_front_yard", "extra_height_side_yards", "extra_height_rear_yard"}
    got = judge(inputs, "325-16C", old["templates"], cli.drafted_rules(inputs))
    assert got["rules"] == {}
    assert any(g["rule"].endswith("extra_height_stories") and "none of its parts is kept" in g["why"]
               for g in got["unresolved"])
    assert drafter.exception_in_parts(bonus()) == []


def test_an_always_on_flag_restating_a_kept_rule_is_set_aside_but_never_for_a_narrower_or_refused_rule(inputs):
    """Stage 1's §325-18B answer: the projection rule, and an always-on flag quoting the same sentence (every design
    with eaves needed review): the flag is set aside, listed for a person. Review round 16: a rule narrowed by a
    condition (two-family only) or refused never takes the flag's place: the flag stays."""
    old = _stage1(inputs, "325-18B")
    rule = next(x for x in old["templates"] if x["kind"] == "rule")
    flag = next(x for x in old["templates"] if x["kind"] == "flag")
    got = judge(inputs, "325-18B", [rule, flag])
    assert [r["id"] for rs in got["rules"].values() for r in rs] == ["general.325_18b_architectural_feature_projection_limit"]
    assert any(g["rule"].endswith("required_yard_open_unobstructed") and "set aside" in g["why"] for g in got["unresolved"])
    narrow = rule | {"applies_when": 'use == "two_family"',
                     "examples": [{"given": ex["given"] + [{"measure": "use", "value": "two_family"}], "expect": ex["expect"]}
                                  for ex in rule["examples"]]}
    got = judge(inputs, "325-18B", [narrow, flag])
    kept = {r["id"] for rs in got["rules"].values() for r in rs}
    assert "general.325_18b_required_yard_open_unobstructed" in kept, got["problems"][:2]
    refused = rule | {"check": "architectural_feature_projection <= 1"}       # 1 isn't backed: the rule is refused
    got = judge(inputs, "325-18B", [refused, flag])
    assert "general.325_18b_required_yard_open_unobstructed" in {r["id"] for rs in got["rules"].values() for r in rs}


def test_the_guards_refuse_the_recorded_stage1_answers_in_check_answer(inputs):
    """Judged by check_answer, as replay judges them: stage 1's parts and its always-on flag are refused."""
    bonus_parts = judge(inputs, "325-16C", _stage1(inputs, "325-16C")["templates"], cli.drafted_rules(inputs))
    assert any("relaxes it" in p for p in bonus_parts["problems"])
    eaves = judge(inputs, "325-18B", _stage1(inputs, "325-18B")["templates"])
    assert any("set aside" in g["why"] for g in eaves["unresolved"]) and not eaves["problems"]



@pytest.mark.parametrize("condition", ["building_height > {height_ft}", "building_height >= {height_ft}",
                                       "{height_ft} < building_height", "not (building_height <= {height_ft})",
                                       "building_height - {height_ft} > 0", "(building_height > {height_ft})",
                                       "building_height > {height_ft} or stories > {stories_max}",
                                       "stories > {stories_max} or building_height > {height_ft}"])
def test_the_parts_form_is_refused_however_its_condition_is_written(inputs, condition):
    """Review round 15: only `measure > {slot}` was recognised; `{height_ft} < building_height` let stage 1's parts
    through in six districts. Judged by what the condition does, every spelling is refused, in check_answer too."""
    old = _stage1(inputs, "325-16C")
    stories = next(sl for x in old["templates"] for sl in x["slots"] if sl["name"] == "stories_max")

    def rewrite(x):          # the condition as written, the slots it names defined, its examples consistent with it
        if "{height_ft}" not in (x.get("applies_when") or ""):
            return x
        out = x | {"applies_when": condition}
        if "{stories_max}" in condition and all(sl["name"] != "stories_max" for sl in x["slots"]):
            out["slots"] = x["slots"] + [stories]
            out["examples"] = [ex | {"given": ex["given"] + [{"measure": "stories", "value": "{stories_max}"}]}
                               if all(g["measure"] != "stories" for g in ex["given"]) else ex for ex in x["examples"]]
        return out
    rewritten = [rewrite(x) for x in old["templates"]]
    got = judge(inputs, "325-16C", rewritten, cli.drafted_rules(inputs))
    assert got["rules"] == {} and sum("relaxes it" in p for p in got["problems"]) >= 4, got["problems"][:2]



def test_a_size_tier_keyed_to_a_minimum_is_not_an_exception_in_parts(inputs):
    """Review round 16: 'names the measure' was taken for 'widens a limit on it', so a tier keyed to the chart's
    minimum lot area ('when lot_area > {min_lot}: building_area <= 0.3 * lot_area') was refused as a bonus in parts.
    Only a chart MAXIMUM (the height) is widened by an exception; with the drafted chart rules known, the tier passes
    this guard and the height parts are still refused."""
    drafted = cli.drafted_rules(inputs)
    tier = {"kind": "rule", "relaxes": "", "applies_when": "lot_area > {min_lot}", "check": "building_area <= 0.3 * lot_area",
            "slots": [slot("min_lot", "One-family dwelling, detached", section=LOT_SIZE)]}
    assert drafter.exception_in_parts(tier, drafted) == []
    old = _stage1(inputs, "325-16C")
    limit = next(x for x in old["templates"] if x["id_suffix"] == "extra_height_limit")
    assert drafter.exception_in_parts(limit, drafted)



def test_a_flag_that_sends_a_dropped_note_to_a_person_is_never_set_aside(inputs):
    """Review round 17 (P0): a rule leaving out fn16's "not less than 20 ft" was kept because a flag cites fn16 whole,
    then that flag was set aside as 'restating' the rule (the rule quotes fn16 too): the rule passed a 10 ft rear
    yard on a 40 ft lot with nothing sending fn16 to a person. The flag stays."""
    rule = template("rear_min", "rear_yard >= min({pct} * lot_depth, {cap})",
                    [slot("pct", REAR, 1, 2, True, ["16"]), slot("cap", REAR, 2, 2, False, ["16"])],
                    [({"rear_yard": "{pct} * 100", "lot_depth": "100"}, "pass"),
                     ({"rear_yard": "{pct} * 100 - 1", "lot_depth": "100"}, "fail"),
                     ({"rear_yard": "{cap}", "lot_depth": "1000"}, "pass")],
                    quotes=[law(OPENING), law(YARDS_GROW), chart_note(16, "But not less than 20 ft.")])
    flag = template("fn16_flag", "", [], [], kind="flag", quotes=[chart_note(16, "But not less than 20 ft.")])
    got = judge(inputs, "325-16C", [rule, flag], cli.drafted_rules(inputs))
    kept = [r for rs in got["rules"].values() for r in rs]
    assert any(r["id"].endswith("rear_min") for r in kept), got["problems"][:2]        # kept because of the flag
    assert any(r["id"].endswith("fn16_flag") for r in kept), [g["rule"] for g in got["unresolved"]][:4]



def test_a_chart_maximum_is_known_by_what_its_rule_does_and_assumed_when_nothing_shows_otherwise(inputs):
    """Review round 17: the chart maximum was found by spelling ('^building_height <='), so '35 >= building_height',
    '(building_height <= 35)' or no drafted chart rule yet ({}) switched the parts guard off."""
    import copy
    limit = next(x for x in _stage1(inputs, "325-16C")["templates"] if x["id_suffix"] == "extra_height_limit")
    drafted = cli.drafted_rules(inputs)
    flipped = copy.deepcopy(drafted)
    import re as _re
    for rules in flipped.values():                  # every height maximum written the other way round
        for r in rules:
            if m := _re.fullmatch(r"building_height <= (\d+)", r.get("check") or ""):
                r["check"] = f"{m[1]} >= building_height"
    assert not any((r.get("check") or "").startswith("building_height <=") for rules in flipped.values() for r in rules)
    for d in (drafted, flipped, {}, None):
        assert drafter.exception_in_parts(limit, d), d and sorted(d)[:2]



@pytest.mark.parametrize("condition", ["building_height > {height_ft} and lot_area > {min_lot}",
                                       "building_height > {height_ft} and lot_area >= 5000",
                                       "building_height > {height_ft} and lot_width > 2000"])
def test_the_parts_guard_sees_a_condition_whose_other_part_needs_a_value_no_single_probe_gives(inputs, condition):
    """Review round 17: the other measures at exactly 0 or 1000 made these conditions false in every probe."""
    limit = next(x for x in _stage1(inputs, "325-16C")["templates"] if x["id_suffix"] == "extra_height_limit")
    with_slot = limit | {"applies_when": condition,
                         "slots": limit["slots"] + [slot("min_lot", "One-family dwelling, detached", section=LOT_SIZE)]}
    assert drafter.exception_in_parts(with_slot, cli.drafted_rules(inputs))



def test_versions_of_one_rule_for_different_cell_forms_are_not_parts_of_each_other(inputs):
    """2026-10-25 §325-16C answer: the stories limit for '3' and for R-3AA's '3/2 [fn11]' share their condition, and
    all-or-none took them for two parts of one exception: every district missed one of them, so both were dropped
    everywhere. Filled from the same chart rows, they are one part in two forms: each district keeps the one it fits."""
    stories = [x for x in _recorded(inputs, "325-16C")["templates"] if "stories_not_exceeded" in x["id_suffix"]]
    assert len(stories) == 2
    got = judge(inputs, "325-16C", stories, cli.drafted_rules(inputs))
    kept = {d: [r["id"].split(".", 1)[1] for r in rs] for d, rs in got["rules"].items()}
    assert kept["R-1a"] == ["325_16c_height_exception_stories_not_exceeded"]
    assert kept["R-3aa"] == ["325_16c_height_exception_stories_not_exceeded_fn11"]
    # real parts still go together: stage 1's parts (four refused) keep nothing
    assert judge(inputs, "325-16C", _stage1(inputs, "325-16C")["templates"], cli.drafted_rules(inputs))["rules"] == {}
