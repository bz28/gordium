"""A rule drafted from New York's Residential Code may use only the second reading's numbers, the way the second
reading says the law reads them (rule_format/code_numbers.py, egress step 3).

The numbers and comparisons come from the repo's text_verification.yaml and sections file (no code cache needed, so
CI runs these too); each quote here is the book's own words (checked against the book where the cache is, by
`python -m rule_format`, through the answer key and drafts that quote them).
"""

import copy

import pytest

from rule_format import code_numbers
from rule_format.rulebook import REPO, Context, validate

STATE = REPO / "regulations/jurisdictions/new_york/new_york_state"
BOOK = "gov.ny.residential.2025.pdf"
RISERS = {"file": BOOK, "page": 100, "lines": [42, 42],
          "quote": "[NY] R318.7.5.1 Risers. The riser height shall be not more than 8 1/4 inches (209 mm)."}
HEADROOM = {"file": BOOK, "page": 100, "lines": [28, 29],
            "quote": "R318.7.2 Headroom. The headroom in stairways shall be not less than 6 feet 8 inches (2032 mm) measured "
                     "vertically from the sloped line adjoining the tread nosing or from the floor surface of the landing or "
                     "platform on that portion of the stairway."}
AREA = {"file": BOOK, "page": 102, "lines": [48, 50],
        "quote": "R319.2.1 Minimum size. Emergency escape and rescue openings shall have a net clear opening of not less "
                 "than 5.7 square feet (0.530 m[fn2]). Exception: The minimum net clear opening for grade-floor emergency "
                 "escape and rescue openings shall be 5 square feet (0.465 m[fn2])."}
GUARDS = {"file": BOOK, "page": 104, "lines": [35, 37],
          "quote": "R321.1.1 Where required. Guards shall be provided for those portions of open-sided walking surfaces, "
                   "including floors, stairs, ramps and landings that are located more than 30 inches (762 mm) measured "
                   "vertically to the floor or grade below at any point within 36 inches (914 mm) horizontally to the edge "
                   "of the open side."}


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(STATE)


def problems(ctx, check, source, kind, key="check"):
    return code_numbers.problems({key: check, "for_each": kind}, [source], ctx)


def test_the_sources_sit_in_the_pieces_they_quote(ctx):
    book = ctx.verification[BOOK]
    assert code_numbers.pieces_of(RISERS, book) == ["R318.7.5.1"]
    assert code_numbers.pieces_of(AREA, book) == ["R319.2.1"]
    assert code_numbers.pieces_of(GUARDS, book) == ["R321.1.1"]


@pytest.mark.parametrize("check, words", [
    ("stair_riser_height <= 8.25", None),
    ("8.25 >= stair_riser_height", None),                       # the number on the left: read mirrored
    ("not (stair_riser_height > 8.25)", None),                  # a "not" turned round
    ("stair_riser_height > 8.25", "needs > 8.25 to hold, but the law reads <= 8.25"),    # a dropped "not"
    ("not (stair_riser_height <= 8.25)", "needs > 8.25 to hold"),
    ("stair_riser_height < 8.25", "needs < 8.25 to hold, but the law reads <= 8.25"),    # the edge moved
    ("stair_riser_height <= 8", "isn't one of the second-reading numbers"),             # "8 1/4" misread as 8
    ("stair_riser_height <= 209", "isn't one of the second-reading numbers"),           # the millimetres
    ("stair_riser_height == 8.25", "never an equality"),
])
def test_a_riser_limit_is_the_second_readings_number_used_the_laws_way(ctx, check, words):
    got = problems(ctx, check, RISERS, "stair")
    assert (got == []) if words is None else any(words in p for p in got), got


def test_feet_and_inches_are_one_length_in_inches(ctx):
    assert problems(ctx, "stair_headroom >= 80", HEADROOM, "stair") == []
    # 6 (the feet alone) is no length in inches here, and 8 (the inches alone) is part of the one length
    assert any("isn't one of" in p for p in problems(ctx, "stair_headroom >= 6", HEADROOM, "stair"))
    assert any("isn't one of" in p for p in problems(ctx, "stair_headroom >= 8", HEADROOM, "stair"))


def test_a_flagged_number_counts_when_its_flag_resolves_it(ctx):
    # '5 square foot' is flagged in text_verification.yaml: printed "minimum ... shall be 5 square feet" (>=)
    assert problems(ctx, "opening_net_clear_area >= (5 if opening_at_grade else 5.7)", AREA,
                    "emergency_escape_opening") == []
    assert any("needs < 5 to hold" in p for p in problems(
        ctx, "opening_net_clear_area < (5 if opening_at_grade else 5.7)", AREA, "emergency_escape_opening"))


def test_a_flag_that_does_not_resolve_its_number_sends_it_to_a_person(ctx):
    changed = copy.copy(ctx)
    changed.verification = copy.deepcopy(ctx.verification)
    entry = changed.verification[BOOK]["pieces"]["R319.2.1"]
    entry["flags"] = ["'5 square foot': printed so unclearly that the two readings could not be told apart"]
    got = problems(changed, "opening_net_clear_area >= (5 if opening_at_grade else 5.7)", AREA, "emergency_escape_opening")
    assert any("flag doesn't resolve it" in p for p in got), got
    # the unflagged 5.7 of the same piece is still fine alone
    assert problems(changed, "opening_net_clear_area >= 5.7", AREA, "emergency_escape_opening") == []


def test_a_number_the_second_reading_reads_as_no_limit_is_never_compared_with(ctx):
    # R318.7.5.1's "4-inch-diameter sphere": the second reading reads it "none" (its limit is on the opening)
    sphere = dict(RISERS, lines=[45, 46], quote=(
        "At open risers, openings located more than 30 inches (762 mm), as measured vertically, to the floor or grade "
        "below shall not permit the passage of a 4-inch-diameter (102 mm) sphere."))
    variation = dict(RISERS, lines=[43, 44], quote=(
        "The greatest riser height within any flight of stairs shall not exceed the smallest by more than 3/8 inch (9.5 mm)."))
    got = problems(ctx, "stair_riser_variation <= 4", sphere, "stair")
    assert any("sets no limit with it" in p for p in got), got
    assert problems(ctx, "stair_riser_variation <= 0.375", variation, "stair") == []


def test_a_trigger_inside_an_or_may_be_written_either_way_but_keeps_its_edge(ctx):
    # "more than 30 inches": a guard is required above 30 in. In an "or", "drop <= 30" is the same edge turned round
    assert problems(ctx, "open_side_drop <= 30 or guard_present", GUARDS, "open_side") == []
    assert problems(ctx, "open_side_drop > 30", GUARDS, "open_side", key="applies_when") == []
    # ... but "30 or more" moves the edge: refused in either place
    assert any("needs < 30" in p for p in problems(ctx, "open_side_drop < 30 or guard_present", GUARDS, "open_side"))
    assert any("needs >= 30" in p for p in problems(ctx, "open_side_drop >= 30", GUARDS, "open_side", key="applies_when"))


def test_review_when_numbers_are_checked_by_value_only(ctx):
    rule = {"check": "stair_riser_height <= 8.25", "for_each": "stair",
            "review_when": [{"when": "stair_riser_height > 8.25", "reason": "x"}, {"when": "stair_riser_height > 8", "reason": "y"}]}
    got = code_numbers.problems(rule, [RISERS], ctx)
    assert got == ["number 8 in 'review_when' isn't one of the second-reading numbers (text_verification.yaml) of the "
                   "pieces its quotes cite, stated in those quotes, in in"], got


def test_a_quote_that_does_not_state_the_number_backs_nothing(ctx):
    # the third sentence of R318.7.5.1 alone: 8 1/4 is the piece's number, but this quote doesn't state it
    source = dict(RISERS, lines=[43, 44], quote="The greatest riser height within any flight of stairs shall not exceed "
                                                 "the smallest by more than 3/8 inch (9.5 mm).")
    assert any("isn't one of" in p for p in problems(ctx, "stair_riser_height <= 8.25", source, "stair"))


def test_validation_uses_the_second_reading_for_a_rule_citing_the_book(ctx):
    """The whole validator: a per-part rule citing R318.7.5.1 is refused for a reversed limit; a zoning rule's numbers
    are still traced the old way (the quote's own numbers)."""
    def rule(check):
        return {"id": "general.risers", "kind": "rule", "topic": "means_of_egress", "title": "Riser height",
                "for_each": "stair", "when_none": "not_applicable", "check": check, "sources": [RISERS],
                "examples": [{"given": {}, "parts": {"stair": [{"id": "s1", "measures": {"stair_riser_height": 7}}]},
                              "rows": [{"part": "s1", "outcome": "pass"}], "expect": "pass"},
                             {"given": {}, "parts": {"stair": [{"id": "s1", "measures": {"stair_riser_height": 9}}]},
                              "rows": [{"part": "s1", "outcome": "fail"}], "expect": "fail"},
                             {"given": {}, "parts": {"stair": []}, "rows": [{"outcome": "not_applicable"}],
                              "expect": "not_applicable"}],
                "drafted_by": "test", "status": "draft"}
    good = validate({"district": "general", "rules": [rule("stair_riser_height <= 8.25")]}, ctx)
    assert not any("number" in p for p in good), good
    bad = validate({"district": "general", "rules": [rule("stair_riser_height < 8.25")]}, ctx)
    assert any("needs < 8.25 to hold" in p for p in bad), bad


@pytest.mark.parametrize("text, value", [("8 1/4", 8.25), ("3/8", 0.375), ("5.7", 5.7), ("1,000", 1000), ("four", 4),
                                         ("one-half", 0.5), ("two-thirds", 2 / 3), ("one and one third", 4 / 3),
                                         ("twenty-one", 21), ("R318", None)])
def test_values_are_read_exactly(text, value):
    got = code_numbers.value_of(text)
    assert (got is None) if value is None else abs(float(got) - value) < 1e-9


def test_a_number_in_an_ifs_test_only_picks_a_limit_and_is_checked_by_value(ctx):
    width = {"file": BOOK, "page": 100, "lines": [23, 26], "quote": (
        "R318.7.1 Width. Stairways shall be not less than 36 inches (914 mm) in clear width at all points above the "
        "permitted handrail height and below the required headroom height. The clear width of stairways at and below "
        "the handrail height, including treads and landings, shall be not less than 31 1/2 inches (787 mm) where a "
        "handrail is installed on one side and 27 inches (698 mm) where handrails are installed on both sides.")}
    # "one side" is read "none" (it says where, not how much): fine as the test that picks 31 1/2 or 27
    assert problems(ctx, "stair_clear_width_at_handrail >= (31.5 if stair_handrail_sides <= 1 else 27)", width,
                    "stair") == []
    # ... but still only a number the quote states, and never as a limit itself
    assert any("isn't one of" in p for p in problems(
        ctx, "stair_clear_width_at_handrail >= (31.5 if stair_handrail_sides <= 2 else 27)", width, "stair"))
    assert any("sets no limit" in p for p in problems(ctx, "stair_handrail_sides >= 1", width, "stair"))


def test_an_equality_is_refused_even_with_arithmetic_on_one_side(ctx):
    # R315.5.2.2 sets a formula ("15 inches minus three-fourths of the tread depth"): a drafted
    # `riser == 15 - 0.75 * tread` would fail every real stair (a measured length never equals it exactly)
    formula = {"file": BOOK, "page": 98, "lines": [34, 34],
               "quote": "2. The riser height shall be 15 inches (381 mm) minus three-fourths of the tread depth."}
    for check in ("stair_riser_height == 15 - 0.75 * stair_tread_depth",
                  "not (stair_riser_height != 15 - 0.75 * stair_tread_depth)"):
        assert any("never an equality" in p for p in problems(ctx, check, formula, "stair")), check
    # arithmetic in an ordinary comparison is still checked by value only
    assert problems(ctx, "stair_riser_height <= 15 - 0.75 * stair_tread_depth", formula, "stair") == []


WIDTH = {"file": BOOK, "page": 100, "lines": [23, 26], "quote": (
    "R318.7.1 Width. Stairways shall be not less than 36 inches (914 mm) in clear width at all points above the "
    "permitted handrail height and below the required headroom height.")}


@pytest.mark.parametrize("check, source, words", [
    # a chain holds when each comparison does: at the top it must hold, so each keeps the law's comparison
    ("0 <= stair_clear_width < 36", WIDTH, "needs < 36 to hold"),
    ("36 > stair_clear_width > 0", WIDTH, "needs < 36 to hold"),
    ("36 <= stair_clear_width <= 100", WIDTH, "isn't one of"),       # 100 isn't the law's; 36 is right
    # a number in arithmetic keeps its direction: a dropped "not" with a no-op added is still a dropped "not"
    ("stair_riser_height > 8.25 + 0", RISERS, "needs > 8.25 to hold"),
    ("stair_riser_height > max(8.25, stair_riser_variation)", RISERS, "needs > 8.25 to hold"),
    ("stair_riser_height > -(-8.25)", RISERS, None),                 # read as -8.25 (no reading): refused below
    ("8.25 - stair_riser_height < 0", RISERS, "needs > 8.25 to hold"),
    ("stair_riser_height <= 8.25 + 0", RISERS, ""),
    ("stair_riser_height - 0 <= 8.25", RISERS, ""),
])
def test_a_chain_or_arithmetic_keeps_the_laws_comparison(ctx, check, source, words):
    got = problems(ctx, check, source, "stair")
    if words == "":
        assert got == [], got
    elif words is None:
        assert got, check
    else:
        assert any(words in p for p in got), got


def test_a_degree_or_a_count_never_backs_a_length(ctx):
    slope = {"file": BOOK, "page": 100, "lines": [44, 45],
             "quote": "an angle not more than 30 degrees (0.51 rad) from the vertical."}
    assert any("isn't one of" in p for p in problems(ctx, "stair_riser_height <= 30", slope, "stair"))


SPHERE = {"file": BOOK, "page": 104, "lines": [46, 47],
          "quote": "Required guards shall not have openings from the walking surface to the required guard height that "
                   "allow passage of a sphere 4 inches (102 mm) in diameter."}


@pytest.mark.parametrize("check, source, words", [
    # membership is equality with each item: never a limit, and its numbers are still the law's
    ("stair_riser_height not in [99]", RISERS, "isn't one of"),
    ("stair_riser_height not in [8.25]", RISERS, "never an equality"),
    ("stair_riser_height in [1, 2, 3, 4, 5, 6, 7, 8]", RISERS, "isn't one of"),
    # a number read "none" is no limit, even with a measure added or taken away; only in a formula of the law's kind
    # (a measure times a number) is it a term
    ("guard_opening_sphere - 4 > 0", SPHERE, "can't be compared with"),
    ("guard_opening_sphere > 4 + 0", SPHERE, "can't be compared with"),
    ("guard_opening_sphere < 4", SPHERE, "can't be compared with"),
])
def test_membership_and_none_numbers_with_arithmetic_are_refused(ctx, check, source, words):
    got = problems(ctx, check, source, "open_side" if "guard" in check else "stair")
    assert any(words in p for p in got), got


def test_a_range_reads_its_lower_number_as_at_least_and_its_upper_as_at_most(ctx):
    lengths = [{"comparison": "between", "values": {"in": 10}}, {"comparison": "between", "values": {"in": 14}},
               {"comparison": "<=", "values": {"in": 3}}]
    got = [c["comparison"] for c in code_numbers._between_ends(lengths)]
    assert got == [">=", "<=", "<="]
    lone = code_numbers._between_ends([{"comparison": "between", "values": {"in": 10}}])
    assert lone[0]["comparison"] == "between"          # no partner: no comparison fits it


def test_a_value_the_piece_reads_two_ways_counts_only_as_the_quote_words_it(ctx):
    # R320.2: "not less than 34 inches" (handrails) and "not more than 34 inches" (ship's ladders, not quoted)
    handrail = {"file": BOOK, "page": 103, "lines": [54, 55], "quote": (
        "Handrail height, measured vertically from the sloped plane adjoining the tread nosing, or finish surface of "
        "ramp slope, shall be not less than 34 inches (864 mm) and not more than 38 inches (965 mm).")}
    ok = problems(ctx, "handrail_height >= 34 and handrail_height_max <= 38", handrail, "handrail")
    assert ok == [], ok
    got = problems(ctx, "handrail_height <= 34 and handrail_height_max <= 38", handrail, "handrail")
    assert any("needs <= 34 to hold, but the law reads >= 34" in p for p in got), got


@pytest.mark.parametrize("check, source, kind", [
    ("guard_opening_sphere > 4 + 0 * guard_height", SPHERE, "open_side"),     # a zero coefficient makes no formula
    ("guard_opening_sphere >= 4 - 0 / guard_height", SPHERE, "open_side"),
    ("stair_clear_width - stair_handrail_sides >= 4", {"file": BOOK, "page": 101, "lines": [32, 32], "quote": (
        "R318.7.8 Handrails. Handrails shall be provided on not less than one side of each flight of stairs with four or "
        "more risers.")}, "stair"),                                            # a count beside a length backs nothing
])
def test_a_limit_hidden_by_a_zero_term_or_a_count_measure_is_refused(ctx, check, source, kind):
    assert problems(ctx, check, source, kind), check


def test_an_ifs_test_measure_never_lends_its_unit(ctx):
    risers = {"file": BOOK, "page": 100, "lines": [42, 46], "quote": (
        "[NY] R318.7.5.1 Risers. The riser height shall be not more than 8 1/4 inches (209 mm). The riser height shall "
        "be measured vertically between leading edges of the adjacent treads. The greatest riser height within any "
        "flight of stairs shall not exceed the smallest by more than 3/8 inch (9.5 mm). Risers shall be vertical or "
        "sloped from the underside of the nosing of the tread above at an angle not more than 30 degrees (0.51 rad) "
        "from the vertical. At open risers, openings located more than 30 inches (762 mm), as measured vertically, to "
        "the floor or grade below shall not permit the passage of a 4-inch-diameter (102 mm) sphere.")}
    got = problems(ctx, "stair_riser_height <= (30 if stair_handrail_sides > 0 else 30)", risers, "stair", "applies_when")
    assert got, "30 degrees backed a 30 in limit through an if's test measure"


def _rule(folder, rule_id):
    import yaml
    path = REPO / "regulations/jurisdictions" / folder / "5_building_code_rules/drafted/general.yaml"
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))["rules"]
    return next(r for r in rules if r["id"] == rule_id), Context.for_jurisdiction(path.parents[2])


def test_a_list_items_number_never_backs_a_reading_with_limit_words():
    # 1017.3 reads "more than one" (>); the quote "Exceptions: 1. In open parking garages" prints only the list
    # item's 1. Once the reader stopped taking "In" for inches, that bare 1 backed "more than one": stories > 1 in an
    # applies_when would have made one-storey buildings "not applicable" (review round 1, skeptic)
    rule, ctx = _rule("new_york/new_york_state_building", "general.bc_table_1017_2_f2_s2_u")
    assert code_numbers.problems(rule, rule["sources"], ctx) == []
    got = code_numbers.problems({**rule, "applies_when": "stories > 1"}, rule["sources"], ctx)
    assert any("number 1 in 'applies_when'" in p for p in got), got


def test_a_sections_number_is_never_compared_with_even_in_an_ifs_test():
    # NFPA 101 16.2.5.2: "... in accordance with Section 9.7, in which case dead-end corridors shall not exceed 50 ft"
    rule, ctx = _rule("maine/maine_state", "general.nfpa_16_2_5_2_dead_end")
    assert code_numbers.problems(rule, rule["sources"], ctx) == []
    got = code_numbers.problems({**rule, "check": "corridor_dead_end_length <= (50 if stories > 9.7 else 20)"},
                                rule["sources"], ctx)
    assert any("9.7" in p and "section" in p for p in got), got


@pytest.mark.parametrize("change", [
    {"applies_when": "nfpa_day_care_occupancy and stories * 9.7 <= 50"},      # a term multiplied in (review round 2)
    {"check": "corridor_dead_end_length <= (50 if stories * 9.7 > 20 else 20)"},
    {"review_when": [{"when": "stories > 9.7", "why": "a section's number as a count"}]}])
def test_a_sections_number_backs_no_term_of_a_formula_nor_a_review_when(change):
    rule, ctx = _rule("maine/maine_state", "general.nfpa_16_2_5_2_dead_end")
    got = code_numbers.problems({**rule, **change}, rule["sources"], ctx)
    assert any("9.7" in p and "section" in p for p in got), got


def test_a_list_items_own_number_backs_no_reading_even_one_with_words_after_it():
    # 1016.2 reads "two or more" (>=): limit words after the number, which _has_words doesn't see. Its item "2. In
    # other than Group H occupancies" (once "2 inch") backed it as a bare 2 (review round 3)
    rule, ctx = _rule("new_york/new_york_state_building", "general.bc_1016_2_intervening_spaces_other_groups")
    source = {"file": "gov.ny.building.2025.pdf", "page": 340, "lines": [47, 48], "quote": (
        "direct access to an exit is required by other sections of this code. 2. In other than Group H occupancies, "
        "egress from a room or space is allowed to pass through adjoining or intervening rooms")}
    got = code_numbers.problems({**rule, "applies_when": "stories >= 2"}, rule["sources"] + [source], ctx)
    assert any("number 2 in 'applies_when'" in p for p in got), got
    assert code_numbers.quote_statements("Exceptions: 1. In open parking garages") == set()
    # a number ending a sentence after a word is a quantity, and stays
    assert code_numbers.quote_statements("shall be not more than 2. Where") == {(2, "")}
