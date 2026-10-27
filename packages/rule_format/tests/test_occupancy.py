"""Occupancy (§325-3B's one-family and two-family dwellings) and home occupations, in every residential hand
rulebook (research: docs/research/2026-10-27_occupancy_and_home_occupation.md). Expected results are worked out by
hand from the code's words, independently of the rules' own examples; a fact left blank never lets a rule pass."""

import itertools

import pytest

from rule_format.rulebook import REPO, Context, load, outcome, rulebook_for

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
DISTRICTS = ["R-1a", "R-1b", "R-2a", "R-2b", "R-2c", "R-3a", "R-3aa", "R-3b", "RU"]
USES = {"use": Context.for_jurisdiction(ITHACA).uses}
HOUSEHOLD = ("unrelated_persons", "unrelated_persons_with_children", "owner_occupied", "functional_family_unit")
HOME = ("home_occupation", "home_occupation_area", "home_occupation_unit_area")


def rule(district, name):
    rules = {r["id"]: r for r in load(rulebook_for(ITHACA, district))["rules"]}
    return rules[f"{district}.{name}"]


def one_family(district, **facts):
    return outcome(rule(district, "occupancy_one_family"), {"use": "one_family_detached", **facts}, USES)


# §325-3B DWELLING, ONE-FAMILY: an individual or family and not more than one unrelated individual; "In the R-1
# Zones ... two ... if the dwelling is owner-occupied"; "In the R-2 and R-3 Zones ... two"; RU named apart (one).
LIMIT = {"R-1a": 1, "R-1b": 1, "R-2a": 2, "R-2b": 2, "R-2c": 2, "R-3a": 2, "R-3aa": 2, "R-3b": 2, "RU": 1}
# §325-8B(6) and chart note 1 leave minor dependent children out "In R-1 and R-2 Districts" only (research §2)
CHILDREN_LEFT_OUT = {"R-1a", "R-1b", "R-2a", "R-2b", "R-2c"}


@pytest.mark.parametrize("district", DISTRICTS)
def test_the_one_family_limit_each_district_sets(district):
    n = "unrelated_persons" if district in CHILDREN_LEFT_OUT else "unrelated_persons_with_children"
    limit = LIMIT[district]
    owner = {"owner_occupied": False}
    assert one_family(district, **{n: limit}, **owner) == "pass"
    assert one_family(district, **{n: limit + 1}, **owner, functional_family_unit=False) == "fail"
    assert one_family(district, **{n: limit + 1}, **owner, functional_family_unit=True) == "needs_review"
    if district.startswith("R-1"):                    # two if owner-occupied, never three
        assert one_family(district, **{n: 2}, owner_occupied=True) == "pass"
        assert one_family(district, **{n: 3}, owner_occupied=True, functional_family_unit=False) == "fail"


def test_children_count_outside_r1_and_r2_only():
    """Two unrelated adults and a child of one of them: R-2 leaves the child out (2: complies); R-3 counts them
    (3: over two); RU counts them (3: over one)."""
    family = {"unrelated_persons": 2, "unrelated_persons_with_children": 3, "functional_family_unit": False}
    assert one_family("R-2a", **family) == "pass"
    assert one_family("R-3a", **family) == "fail"
    assert one_family("RU", **family) == "fail"


def test_each_unit_of_a_two_family_dwelling():
    two = {"use": "two_family"}
    for d in ("R-2a", "R-2b", "R-2c"):                 # "each unit ... not more than two unrelated individuals"
        r = rule(d, "occupancy_two_family")
        assert outcome(r, {**two, "unrelated_persons": 1}, USES) == "pass"
        # two in each unit is four in the building: "more than two roomers or boarders" if they are roomers (open)
        assert outcome(r, {**two, "unrelated_persons": 2}, USES) == "needs_review"
        assert outcome(r, {**two, "unrelated_persons": 3}, USES) == "fail"
    for d in ("R-3a", "R-3aa", "R-3b", "RU"):          # no per-unit limit; a multiple dwelling past (2) or (3)
        r = rule(d, "occupancy_two_family")
        assert outcome(r, {**two, "unrelated_persons": 1}, USES) == "not_applicable"
        assert outcome(r, {**two, "unrelated_persons": 2}, USES) == "needs_review"   # review round 1: (3)
        assert outcome(r, {**two, "unrelated_persons": 3}, USES) == "needs_review"
    for d in ("R-1a", "R-1b"):                          # not permitted in R-1: the use rule fails it
        assert f"{d}.occupancy_two_family" not in {r["id"] for r in load(rulebook_for(ITHACA, d))["rules"]}
        assert outcome(rule(d, "use"), two, USES) == "fail"


@pytest.mark.parametrize("district", DISTRICTS)
def test_a_home_occupation(district):
    """(f): "no more than 25% of the dwelling unit and no more than a total of 500 indoor square feet"; the chart:
    SP, so once one is planned the flag needs review whatever its size."""
    size, flag = rule(district, "home_occupation_size"), rule(district, "home_occupation")
    house = {"use": "one_family_detached", "home_occupation": True}
    assert outcome(size, {**house, "home_occupation_area": 500, "home_occupation_unit_area": 2000}, USES) == "pass"
    assert outcome(size, {**house, "home_occupation_area": 501, "home_occupation_unit_area": 9000}, USES) == "fail"
    assert outcome(size, {**house, "home_occupation_area": 301, "home_occupation_unit_area": 1200}, USES) == "fail"
    assert outcome(flag, house, USES) == "needs_review"
    for r in (size, flag):
        assert outcome(r, {"use": "one_family_detached", "home_occupation": False}, USES) == "not_applicable"
        assert outcome(r, {"use": "church", "home_occupation": True}, USES) == "not_applicable"
        assert outcome(r, {"use": "one_family_detached"}, USES) == "needs_review"   # not said: never a pass


def _domain(name):
    if name in ("owner_occupied", "functional_family_unit", "home_occupation"):
        return [True, False]
    if name in ("home_occupation_area", "home_occupation_unit_area"):
        return [0, 400, 500, 500.4, 501, 1600, 2000, 2004]
    return [0, 1, 2, 3, 4]


@pytest.mark.parametrize("district", DISTRICTS)
def test_a_blank_never_lets_a_rule_pass_that_some_answer_would_not(district):
    """Never a false pass: for every new rule and every use it can apply to, every complete set of answers to the
    facts it reads (over small values around its limits) and every non-empty set of them left blank (one, two or
    all) gives "pass" only if every way of filling the blanks in passes too (review round 2: pairs only before)."""
    from rule_format import formula
    rules = [r for r in load(rulebook_for(ITHACA, district))["rules"]
             if r["id"].split(".", 1)[1] in ("occupancy_one_family", "occupancy_two_family", "home_occupation_size",
                                             "home_occupation")]
    assert len(rules) == (3 if district.startswith("R-1") else 4)
    checked = 0
    for r in rules:
        read = set().union(*(formula.names(t) for t in [r.get("applies_when"), r.get("check")] +
                             [w["when"] for w in r.get("review_when") or []] if t))
        names = [n for n in HOUSEHOLD + HOME if n in read]
        assert names, r["id"]
        for use in ("one_family_detached", "one_family_attached", "two_family"):
            for values in itertools.product(*[_domain(n) for n in names]):
                facts = dict(zip(names, values))
                for k in range(1, len(names) + 1):
                    for blank in itertools.combinations(names, k):
                        given = {"use": use, **{n: v for n, v in facts.items() if n not in blank}}
                        if outcome(r, given, USES) != "pass":
                            continue
                        for fill in itertools.product(*[_domain(n) for n in blank]):
                            checked += 1
                            assert outcome(r, {**given, **dict(zip(blank, fill))}, USES) == "pass", (r["id"], given)
    assert checked                                    # some blanks did pass (each was then checked every way)


def test_the_r3_and_ru_count_is_asked_on_its_own_and_a_mistyped_pair_is_set_aside():
    """Review round 2: R-3 and RU read only the count with the children, so its prompt says the whole count itself
    ("the same count" pointed at a question never asked there); and a count with the children below the count
    without them is a mistyped pair: set aside with the reason, never a pass."""
    from design_checker import rhino_logic as logic
    from model_measurement.measure import measure
    prompt = logic.STATED_FACTS["unrelated_persons_with_children"][0]
    assert "same count" not in prompt and "not related by blood, marriage or adoption" in prompt
    assert "children counted too" in prompt
    lot = {"id": "lot", "edges": [{"points": [a, b]} for a, b in
                                   zip([[0, 0], [60, 0], [60, 100], [0, 100]], [[60, 0], [60, 100], [0, 100], [0, 0]])]}
    site = {"units": "ft", "lot": lot, "buildings": [], "problems": []}
    facts = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "zone": "R-3a",
             "use": "one_family_detached", "unrelated_persons": 3, "unrelated_persons_with_children": 1}
    m = measure(site, facts)
    assert m["unrelated_persons_with_children"]["value"] is None
    values = {k: v["value"] for k, v in m.items()}
    assert outcome(rule("R-3a", "occupancy_one_family"), values, USES) == "needs_review"
    assert "included (1) is lower than the count without them (3)" in m["unrelated_persons_with_children"]["reason"]
    ok = measure(site, {**facts, "unrelated_persons_with_children": 3})
    assert ok["unrelated_persons_with_children"]["value"] == 3
    # review round 3: also when the drawing's geometry can't be worked out (the facts still stand there)
    import model_measurement.measure as measure_mod
    real = measure_mod._measure

    def broken(*a, **k):
        raise measure_mod.shapely.errors.GEOSException("TopologyException")

    measure_mod._measure = broken
    try:
        g = measure(site, facts)
    finally:
        measure_mod._measure = real
    assert g["unrelated_persons"]["value"] == 3 and g["unrelated_persons_with_children"]["value"] is None
    # and the panel says it in every district, with the button to correct both counts
    from model_measurement.project import fact_conflict_rows
    assert fact_conflict_rows(facts) == [(
        "the count of unrelated people with minor dependent children included (1) is lower than the count without "
        "them (3): check both counts", ("unrelated_persons", "unrelated_persons_with_children"))]
    assert fact_conflict_rows({**facts, "unrelated_persons_with_children": 3}) == []


def test_every_fact_is_one_the_architect_can_state_everywhere():
    """Each new fact is a measure, read from the facts, accepted in a facts file and asked in Rhino."""
    from design_checker.rhino_logic import STATED_FACTS
    from model_measurement.measure import ASK, STATED
    from model_measurement.project import FACT_FIELDS, fact_problems
    from rule_format.rulebook import MEASURE_KINDS
    for k in HOUSEHOLD + HOME:
        assert k in MEASURE_KINDS and k in STATED and k in ASK and k in FACT_FIELDS and k in STATED_FACTS, k
    assert fact_problems({"unrelated_persons": -1, "owner_occupied": "yes", "home_occupation_area": -2.5}) == [
        "unrelated_persons must be a whole number, 0 or more", "home_occupation_area must be a number of square feet, "
        "0 or more", "owner_occupied must be yes or no (true / false)"]


def test_a_floor_area_is_kept_as_typed_never_rounded():
    """Review round 1: "whole sq ft" invited 500.4 typed as 500, which passes the 500 sq ft limit. Areas are any number
    of square feet, kept as typed, and 500.4 fails."""
    from design_checker import rhino_logic as logic
    from model_measurement.project import fact_problems
    for k in ("home_occupation_area", "home_occupation_unit_area"):
        assert logic.STATED_FACTS[k][1] == "area" and "whole" not in logic.STATED_FACTS[k][0]
    facts = logic.update_counts({}, {"home_occupation_area": 500.4, "home_occupation_unit_area": 2400.0})
    assert facts == {"home_occupation_area": 500.4, "home_occupation_unit_area": 2400.0} and fact_problems(facts) == []
    with pytest.raises(ValueError):
        logic.update_counts({}, {"home_occupation_area": -1.0})
    size = rule("R-1b", "home_occupation_size")
    assert outcome(size, {"use": "one_family_detached", "home_occupation": True, **facts}, USES) == "fail"
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert '_square_feet(prompt) if kind == "area"' in rhino and "def _square_feet(prompt):" in rhino and "Rhino.Input.Custom.GetNumber()" in rhino
