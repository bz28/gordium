"""The private garage's car limit (chart p.2, line 32 and notes 6 and 7): "(6) For not more than three cars." in R-1a,
R-1b, R-2a and R-2b; "(7) For not more than six cars per building." in R-2c; no limit in R-3a, R-3aa, R-3b and RU.

The expected results don't come from the rules' formulas: they are worked out here by trying every way the cars could
sit in the garages (and, in R-2c, in the buildings) under every reading of the open questions (§5.18, §5.19 of
docs/questions_for_architects.md), and every value a blank answer could take. PASS only if the design complies under
all of them, FAIL only if under none, else NEEDS REVIEW: never a pass on a blank or on a reading not settled."""

import pytest

from rule_format.rulebook import REPO, Context, load, outcome, rulebook_for

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
USES = {"use": Context.for_jurisdiction(ITHACA).uses}
LIMIT = {"R-1a": 3, "R-1b": 3, "R-2a": 3, "R-2b": 3}            # note 6
PER_BUILDING = {"R-2c": 6}                                    # note 7
NO_LIMIT = ["R-3a", "R-3aa", "R-3b", "RU"]                    # a plain • on line 32
BLANK_RANGE = range(1, 5)        # values a blank count of garages or buildings could be (more only adds the same answers)


def rule(district):
    rules = {r["id"]: r for r in load(rulebook_for(ITHACA, district))["rules"]}
    return rules.get(f"{district}.private_garage")


def splits(cars, places):
    """Every way to put `cars` into `places` (each holding 0 or more)."""
    if places == 1:
        return [(cars,)]
    return [(first,) + rest for first in range(cars + 1) for rest in splits(cars - first, places - 1)]


def complies_note_6(cars, garages, limit):
    """{True, False}: the answers over every split of the cars into the garages and both readings (each garage; the
    lot's garages together)."""
    out = set()
    for split in splits(cars, garages):
        out.add(all(c <= limit for c in split))           # each garage
        out.add(cars <= limit)                            # the whole lot
    return out


def complies_note_7(cars, garages, primaries, limit):
    """Every split and reading of "per building": each building holding garages (the garages grouped into 1 to
    `garages` buildings), each primary building (the cars shared out among them), the whole lot."""
    out = set()
    for buildings in range(1, garages + 1):
        out |= {all(c <= limit for c in split) for split in splits(cars, buildings)}
    out |= {all(c <= limit for c in split) for split in splits(cars, primaries)}
    out.add(cars <= limit)
    return out


def expected(answers):
    if answers == {True}:
        return "pass"
    if answers == {False}:
        return "fail"
    return "needs_review"


@pytest.mark.parametrize("district", sorted(LIMIT))
def test_note_6_three_cars(district):
    r, limit = rule(district), LIMIT[district]
    assert r is not None and r["topic"] == "uses" and r["status"] == "draft"
    for cars in range(0, 11):
        for garages in range(1, 5):
            want = expected(complies_note_6(cars, garages, limit))
            got = outcome(r, {"garage_cars": cars, "private_garages": garages}, USES)
            assert got == want, (district, cars, garages)
        # the number of garages not said: every value it could be
        want = expected(set().union(*(complies_note_6(cars, g, limit) for g in BLANK_RANGE)))
        assert outcome(r, {"garage_cars": cars}, USES) == want, (district, cars)
    assert outcome(r, {}, USES) == "needs_review"
    assert outcome(r, {"private_garages": 1}, USES) == "needs_review"
    # the cases the brief names: 2 cars with the garages blank passes; 5 with them blank needs review
    assert outcome(r, {"garage_cars": 2}, USES) == "pass"
    assert outcome(r, {"garage_cars": 5}, USES) == "needs_review"
    assert outcome(r, {"garage_cars": 4, "private_garages": 1}, USES) == "fail"
    assert outcome(r, {"garage_cars": 4, "private_garages": 2}, USES) == "needs_review"


def test_note_7_six_cars_per_building():
    r, limit = rule("R-2c"), PER_BUILDING["R-2c"]
    assert r is not None and r["topic"] == "uses"
    for cars in range(0, 14):
        for garages in range(1, 4):
            for primaries in range(1, 4):
                want = expected(complies_note_7(cars, garages, primaries, limit))
                got = outcome(r, {"garage_cars": cars, "private_garages": garages, "primary_buildings": primaries}, USES)
                assert got == want, (cars, garages, primaries)
            want = expected(set().union(*(complies_note_7(cars, garages, p, limit) for p in BLANK_RANGE)))
            assert outcome(r, {"garage_cars": cars, "private_garages": garages}, USES) == want, (cars, garages)
        want = expected(set().union(*(complies_note_7(cars, g, p, limit) for g in BLANK_RANGE for p in BLANK_RANGE)))
        assert outcome(r, {"garage_cars": cars}, USES) == want, cars
    assert outcome(r, {}, USES) == "needs_review"


@pytest.mark.parametrize("district", NO_LIMIT)
def test_no_limit_in_r3_and_ru(district):
    assert rule(district) is None


@pytest.mark.parametrize("district", sorted(LIMIT) + ["R-2c"])
def test_each_rule_cites_its_own_column_and_note_and_records_the_question(district):
    r = rule(district)
    cells = [s["cell"] for s in r["sources"] if "cell" in s]
    assert cells == [{"section": "Accessory Uses", "row": "Private garage", "column": district.upper()}]
    quotes = " ".join(s.get("quote", "") for s in r["sources"])
    assert ("(7) For not more than six cars per building." if district == "R-2c"
            else "(6) For not more than three cars.") in quotes
    assert "GARAGE, PRIVATE — An enclosed space" in quotes and "(3) Column 3: Permitted Accessory Uses." in quotes
    assert len(r["open_questions"]) == 1 and len(r["research"]) == 1
    assert len(r["research"][0]["readings"]) == (3 if district == "R-2c" else 2)
