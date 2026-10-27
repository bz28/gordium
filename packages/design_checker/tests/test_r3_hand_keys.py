"""The R-3aa, R-3b and RU answer keys (r3-hand): what is special about each, checked two ways.

1. A law table: boundary cases worked by hand from the chart and the code (not from the rules' own examples), each
   run through the rule, so a wrong figure or a wrong note in a rule fails here as well as in its own examples.
2. Through the whole checker, as the panel shows it: each district is offered and checked with its own hand
   rulebook, and the parts Gordium can't measure (R-3aa's footprint cap, RU's green space, primary buildings and 500
   ft spacing) are always review rows, never a pass and never missing.
"""

import copy

import pytest

from design_checker import present, scenarios
from design_checker.check import check_site, options
from rule_format.rulebook import REPO, Context, load, outcome, rulebook_for

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
RULES = {r["id"]: r for d in ("R-3aa", "R-3b", "RU") for r in load(ITHACA / f"5_zoning_rules/{d}.yaml")["rules"]}
ALLOWED = Context.for_jurisdiction(ITHACA).allowed()

# (rule, design, what the law says), each worked by hand from the source named
LAW = [
    # R-3aa: chart p.3 R-3AA column; note 7 (6,000 sf new / 7,000 sf by conversion for 1-3 units, +750 per unit, +500
    # per room let)
    ("R-3aa.lot_area_multiple_family", {"use": "multiple_family", "lot_area": 7500, "dwelling_units": 5,
                                        "rooms_let_for_profit": 0, "conversion": False}, "pass"),       # 6,000 + 1,500
    ("R-3aa.lot_area_multiple_family", {"use": "multiple_family", "lot_area": 7499, "dwelling_units": 5,
                                        "rooms_let_for_profit": 0, "conversion": False}, "fail"),
    ("R-3aa.lot_area_multiple_family", {"use": "multiple_family", "lot_area": 11000, "dwelling_units": 7,
                                        "rooms_let_for_profit": 2, "conversion": True}, "pass"),  # 7,000+3,000+1,000
    ("R-3aa.lot_area_multiple_family", {"use": "multiple_family", "lot_area": 10999, "dwelling_units": 7,
                                        "rooms_let_for_profit": 2, "conversion": True}, "fail"),
    ("R-3aa.lot_width_two_family", {"use": "two_family", "lot_width": 49.9}, "fail"),            # 50 ft (R-3a: 40)
    ("R-3aa.lot_width_fraternity", {"use": "fraternity_sorority_group_house", "lot_width": 50}, "pass"),
    ("R-3aa.use", {"use": "dormitory"}, "fail"),                                              # "-" for R-3AA
    ("R-3aa.use", {"use": "nursing_home"}, "pass"),
    # note 11: at most 3, at least 2; §325-8A(15): 500 sf or less may be exempt (the open question)
    ("R-3aa.stories", {"stories": 1, "building_area": 500}, "needs_review"),
    ("R-3aa.stories", {"stories": 1, "building_area": 500.5, "accessory_buildings": 0}, "fail"),
    ("R-3aa.stories", {"stories": 2, "building_area": 300, "accessory_buildings": 0}, "pass"),
    ("R-3aa.stories", {"stories": 4, "building_area": 300}, "fail"),
    # "Buildings hereafter erected" (§325-8A(15)): the minimum may reach a one-story garage, whose stories Gordium
    # doesn't count (review round 4): never a plain pass with accessory buildings on the lot
    ("R-3aa.stories", {"stories": 2, "building_area": 1600, "accessory_buildings": 1}, "needs_review"),
    ("R-3aa.stories", {"stories": 2, "building_area": 1600, "accessory_buildings": 0}, "pass"),
    # a one-story 480 sf cottage and a 200 sf shed: building_area (680) counts both, so the main building may still
    # be under §325-8A(15)'s 500 sf (review round 5); with no accessory building, 680 sf is the main building's
    ("R-3aa.stories", {"stories": 1, "building_area": 680, "accessory_buildings": 1}, "needs_review"),
    ("R-3aa.stories", {"stories": 1, "building_area": 680, "accessory_buildings": 0}, "fail"),
    # 35 ft, bonus 3.5 ft; rear 25% of depth (50 ft cap, 20 ft floor): a 160 ft lot needs 40 ft, + 1 at 36 ft
    ("R-3aa.height", {"building_height": 36, "front_yard": 11, "side_yard_smaller": 6, "side_yard_larger": 11,
                      "rear_yard": 41, "lot_depth": 160}, "pass"),
    ("R-3aa.height", {"building_height": 36, "front_yard": 11, "side_yard_smaller": 6, "side_yard_larger": 11,
                      "rear_yard": 40.9, "lot_depth": 160}, "fail"),
    ("R-3aa.rear_yard", {"rear_yard": 39.9, "lot_depth": 160}, "fail"),
    # each side's eave held to the minimum its side carries (#18's P0, as R-3a): walls 9'-6" and 10'-0" leave only the
    # wider side able to be the 10 ft one, and its eave 6'-6" from its line is 3'-6" into it; walls 12 and 15 ft leave
    # either side, and an eave that fits only one way needs review
    ("R-3aa.yard_projections", {"side_yard_smaller": 9.5, "side_yard_larger": 10, "front_yard_eaves": 12,
                                "side_yard_smaller_eaves": 9, "side_yard_larger_eaves": 6.5, "rear_yard_eaves": 48,
                                "lot_depth": 120, "building_height": 30}, "fail"),
    ("R-3b.yard_projections", {"side_yard_smaller": 12, "side_yard_larger": 15, "front_yard_eaves": 12,
                               "side_yard_smaller_eaves": 7, "side_yard_larger_eaves": 15, "rear_yard_eaves": 48,
                               "lot_depth": 125, "building_height": 38}, "needs_review"),
    ("R-3aa.yard_projections", {"side_yard_smaller": 12, "side_yard_larger": 15, "front_yard_eaves": 12,
                                "side_yard_smaller_eaves": 9, "side_yard_larger_eaves": 7, "rear_yard_eaves": 48,
                                "lot_depth": 120, "building_height": 30}, "needs_review"),
    # R-3b: note 8 (3,500 sf new / 4,000 sf by conversion, +500 per unit past 3, +300 per room let)
    ("R-3b.lot_area_multiple_family", {"use": "multiple_family", "lot_area": 6600, "dwelling_units": 7,
                                       "rooms_let_for_profit": 2, "conversion": True}, "pass"),  # 4,000+2,000+600
    ("R-3b.lot_area_multiple_family", {"use": "multiple_family", "lot_area": 6599, "dwelling_units": 7,
                                       "rooms_let_for_profit": 2, "conversion": True}, "fail"),
    # a dormitory or nursing home: "Other use" (4,000 sf) or the multiple-family row (at least 3,500 sf): under
    # 3,500 sf both readings fail (review round 1)
    ("R-3b.lot_area_other_use", {"use": "dormitory", "lot_area": 3400}, "fail"),
    ("R-3b.lot_area_other_use", {"use": "nursing_home", "lot_area": 3700}, "needs_review"),
    ("R-3b.lot_area_two_family", {"use": "two_family", "lot_area": 3000}, "pass"),
    ("R-3b.lot_width_two_family", {"use": "two_family", "lot_width": 30}, "pass"),
    ("R-3b.lot_coverage", {"building_area": 2000, "lot_area": 5000}, "pass"),                 # 40%
    ("R-3b.lot_coverage", {"building_area": 2001, "lot_area": 5000}, "fail"),
    ("R-3b.rear_yard", {"rear_yard": 32, "lot_depth": 160}, "pass"),                          # 20% of 160
    ("R-3b.abutting_r1", {"use": "multiple_family", "abuts_r1_district": True}, "needs_review"),  # §325-19E names R-3b
    # RU: note 9 (16,500 sf for 1-3 units, +1,500 per unit past 3, nothing per room let)
    ("RU.lot_area_multiple_family", {"use": "multiple_family", "lot_area": 22500, "dwelling_units": 7,
                                     "rooms_let_for_profit": 9, "conversion": False}, "pass"),    # 16,500 + 6,000
    ("RU.lot_area_multiple_family", {"use": "multiple_family", "lot_area": 22499, "dwelling_units": 7,
                                     "conversion": True}, "fail"),
    ("RU.lot_area_two_family", {"use": "two_family", "lot_area": 14999}, "fail"),               # 15,000 sf
    # a dormitory: "Other use" (30,000 sf) or the multiple-family row (at least 16,500 sf) (review round 1)
    ("RU.lot_area_other_use", {"use": "dormitory", "lot_area": 12000}, "fail"),
    ("RU.lot_area_other_use", {"use": "dormitory", "lot_area": 25000}, "needs_review"),
    ("RU.lot_width_one_family_semi_detached", {"use": "one_family_semi_detached", "lot_width": 100}, "pass"),
    ("RU.use", {"use": "hospital_or_sanitarium"}, "fail"),                                    # "-" for RU
    ("RU.use", {"use": "nursery_school_or_child_day_care"}, "needs_review"),                  # SP, §325-9B(1)(e)
    # note 17: the rear yard is at least 30 ft (not note 16's 20 ft): a 110 ft lot's 25% is 27.5 ft
    ("RU.rear_yard", {"rear_yard": 29.9, "lot_depth": 110}, "fail"),
    ("RU.rear_yard", {"rear_yard": 30, "lot_depth": 110}, "pass"),
    ("RU.yard_projections", {"front_yard_eaves": 23, "side_yard_smaller_eaves": 8, "side_yard_larger_eaves": 8,
                             "rear_yard_eaves": 27.9, "lot_depth": 110, "building_height": 30}, "fail"),
    ("RU.front_yard", {"front_yard": 24.9}, "fail"),
    ("RU.side_yards", {"side_yard_smaller": 9.9, "side_yard_larger": 12}, "fail"),
    # the zero-lot-line house is one dwelling unit (§325-3B): the bedroom parking table, as a detached house
    ("R-3b.parking_one_family", {"use": "one_family_detached_zero_lot_line", "sleeping_rooms": 6,
                                 "parking_spaces": 2}, "fail"),                                 # 2 + 1 for the 6th
]


@pytest.mark.parametrize("rule, design, law", LAW, ids=[f"{r}-{i}" for i, (r, _, _) in enumerate(LAW)])
def test_each_rule_says_what_the_law_says_at_its_boundaries(rule, design, law):
    assert outcome(RULES[rule], design, ALLOWED) == law


@pytest.mark.parametrize("zone", ["R-3aa", "R-3b", "RU"])
def test_each_district_is_offered_with_its_own_hand_rulebook(zone):
    assert zone in options(scenarios.JURISDICTION)["zones"]
    assert rulebook_for(ITHACA, zone) == ITHACA / f"5_zoning_rules/{zone}.yaml"


SMALL = [[15, 30], [45, 30], [45, 60], [15, 60]]       # a 30 x 30 ft house well inside every yard below


def _view(zone, use, lot_w=130, lot_d=240, **facts):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "12_r3a_two_family_at_the_building_limits.yaml"))
    sc["district"], sc["use"] = zone, use
    sc["lot"]["points"] = [[0, 0], [lot_w, 0], [lot_w, lot_d], [0, lot_d]]
    for b in sc["buildings"]:
        b["outline"] = SMALL
    s, f, extras = scenarios.site(sc)
    res = check_site(s, {**f, **facts}, extras=extras)
    return {i["rule"]: i for i in res["view"]["items"] if i.get("rule")}


@pytest.mark.parametrize("facts", [{}, {"conversion": False}, {"conversion": True}])
@pytest.mark.parametrize("zone, use, rule", [
    ("R-3aa", "two_family", "R-3aa.footprint_block_front"),
    ("R-3aa", "multiple_family", "R-3aa.footprint_block_front"),
    ("RU", "two_family", "RU.green_space"),
    ("RU", "two_family", "RU.primary_structures"),
])
def test_what_gordium_cant_measure_is_a_review_row_on_every_design(zone, use, rule, facts):
    """Chart notes no measure covers (R-3aa note 2; RU p.3 note 13, p.2 note 3) are shown on the panel as needs
    review, with the note to check by hand, whatever the use and whatever is stated: never a pass, never left off."""
    items = _view(zone, use, **facts)
    assert items[rule]["status"] == present.REVIEW, items[rule]


@pytest.mark.parametrize("facts", [{}, {"conversion": False}])
def test_rus_500_ft_spacing_is_a_review_row_for_new_construction(facts):
    """RU p.2 note 5 ("for new construction"): needs review unless the building is stated as a conversion."""
    items = _view("RU", "multiple_family", **facts)
    assert items["RU.spacing_500_ft"]["status"] == present.REVIEW, items["RU.spacing_500_ft"]
    assert "RU.spacing_500_ft" not in _view("RU", "multiple_family", conversion=True)


def _cell(column, section, row):
    import json
    cells = [json.loads(line) for line in (ITHACA / "2_extracted_text/zoning_charts_2026-04.cells.jsonl")
             .open(encoding="utf-8")][1:]
    return next(c["value"] for c in cells if c.get("page") == 3 and c.get("column") == column
                and c.get("section") == section and c.get("row") == row)


def _options(number, tag):
    """The section's districts (from its tags) and its Options line cut at its "(a)", "(b)", "(c)" options."""
    import re
    doc = (REPO / "docs/questions_for_architects.md").read_text(encoding="utf-8")
    section = doc.split(f"\n### {number} ", 1)[1].split("\n### ", 1)[0]
    line = next(x for x in section.splitlines() if x.startswith("- **Options:**"))
    parts = dict(re.findall(r"\(([abc])\) (.*?)(?= \([abc]\) |$)", line))
    return re.findall(rf"`\[([A-Za-z0-9-]+)\.{tag}#1\]`", section), parts


def _clause(text, district):
    """The ";"-separated clause of an option that names this district (R-3a never matches inside R-3aa)."""
    import re
    found = [c for c in text.split(";") if re.search(rf"(?<![\w-]){re.escape(district)}(?![\w-])", c)]
    assert len(found) == 1, (district, text)
    return found[0]


def test_the_dormitory_question_offers_each_districts_own_figures():
    """§5.3 asks one question for R-3a, R-3aa, R-3b and RU; each option must give, in the clause naming the district,
    that district's own figure, read from the chart reader's cells: (a) the multiple-family row's note, (b) "Other
    use" (review round 2: they gave R-3a's 6,000 sf and note 7 only; round 3: checked clause by clause, since the same
    figures occur in both options)."""
    import re
    districts, parts = _options("5.3", "lot_area_other_use")
    assert sorted(districts) == ["R-3a", "R-3aa", "R-3b", "RU"]
    for d in districts:
        column = d.upper() if d != "RU" else "RU"
        other = _cell(column, "Minimum Lot Size [fn3]", "Other use").split(" [")[0]
        note = re.search(r"\[fn(\d+)\]", _cell(column, "Minimum Lot Size [fn3]",
                                                  "Multiple family dwelling, new construction"))[1]
        assert other in _clause(parts["b"], d), (d, other, parts["b"])
        assert f"note {note}" in _clause(parts["a"], d), (d, note, parts["a"])


def test_the_zero_lot_line_question_offers_each_districts_own_figures():
    """§5.4's option (b) gives, for each district tagged there, its own "Other use" lot size and width (round 3)."""
    districts, parts = _options("5.4", "lot_size_zero_lot_line")
    assert sorted(districts) == ["R-3a", "R-3aa", "R-3b"]
    for d in districts:
        column = d.upper()
        size = _cell(column, "Minimum Lot Size [fn3]", "Other use").split(" [")[0]
        width = _cell(column, "Minimum Lot Width", "Other use").split(" [")[0]
        clause = _clause(parts["b"], d)
        assert size in clause and width in clause, (d, size, width, parts["b"])


def test_the_new_rulebooks_research_rests_on_ithacas_own_records():
    """Research ranks (rule_format SOURCE_RANKS): 4 is other places' codes, and none of these keys' questions rests on
    one. R-3aa's question on §325-19E dates R-3aa from the code itself: §325-4's last amendment (2017) against
    §325-19E's adoption (2019) (round 3: it had cited a citizen's letter as rank 4)."""
    for rule in RULES.values():
        for r in rule.get("research", []):
            assert all(s.get("rank") in (None, 2) for s in r["sources"]), (rule["id"], r["question"][:60])
    # R-3aa's minimum-stories question read the whole chart (round 4): the commercial sheet's note 6 restates the
    # 500 sf exemption on a minimum-stories section, and the waterfront sheet's note 6 frees small accessory structures
    stories = RULES["R-3aa.stories"]["research"][0]
    cited = {(s.get("page"), s.get("lines", [None])[0]) for s in stories["sources"] if s.get("file") == "zoning_charts_2026-04.pdf"}
    assert {(5, 41), (11, 34)} <= cited, cited
    # ... and gives the other side too (round 5): the City's minimums that reach only primary buildings
    assert {(7, 42), (13, 21)} <= cited, cited
    assert any(s.get("file") == "chapter_325_zoning_2026-10.pdf" and s.get("page") == 48 for s in stories["sources"])
    assert "no longer has" not in stories["why_open"]
    first = RULES["R-3aa.abutting_r1"]["research"][0]["sources"]
    quotes = {(s.get("page"), s.get("quote")) for s in first}
    assert (22, "8-2-2017 by Ord. No. 2017-10; 11-1-2017 by Ord. No. 2017-14]") in quotes
    assert (50, "[Added 7-3-2019 by Ord. No. 2019-12]") in quotes


def test_a_dormitory_in_r3aa_does_not_comply_on_use():
    assert _view("R-3aa", "dormitory")["R-3aa.use"]["status"] == present.FAILS


def test_an_ru_two_family_lot_under_15000_sf_does_not_comply():
    """100 x 140 = 14,000 sf: RU's two-family minimum is 15,000 sf (the same house complies in R-3b: 3,000 sf)."""
    assert _view("RU", "two_family", 100, 140)["RU.lot_area_two_family"]["status"] == present.FAILS
    assert _view("R-3b", "two_family", 100, 140)["R-3b.lot_area_two_family"]["status"] == present.COMPLIES


def test_no_worked_example_puts_an_eave_farther_from_its_line_than_its_wall():
    """An eave reaches out from its wall, so on each side the yard to the eaves is never more than the yard to the
    walls (review round 6: some which-side examples had walls 6 ft and eaves 8 ft from the same line, and the chart
    probes started from one of them)."""
    bad = []
    for rule in RULES.values():
        for i, ex in enumerate(rule.get("examples", [])):
            g = ex["given"]
            bad += [(rule["id"], i, y) for y in ("front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard")
                    if y in g and f"{y}_eaves" in g and g[f"{y}_eaves"] > g[y]]
    assert bad == []
