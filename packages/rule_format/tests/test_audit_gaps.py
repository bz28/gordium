"""The rules the residential coverage audit (PR #39, queue item 15) found missing, in every hand rulebook they apply
to. Expected results are worked out by hand from the code's words, independently of the rules' own examples; a fact
left blank never lets a rule pass."""

import pytest

from rule_format.rulebook import REPO, Context, load, outcome, rulebook_for

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
DISTRICTS = ["R-1a", "R-1b", "R-2a", "R-2b", "R-2c", "R-3a", "R-3aa", "R-3b", "RU"]
USES = {"use": Context.for_jurisdiction(ITHACA).uses}


def rules_of(district):
    return {r["id"]: r for r in load(rulebook_for(ITHACA, district))["rules"]}


# ---- §325-3B ONE-FAMILY ATTACHED DWELLING: "three or more ... A maximum of six" ---------------------------------
# chart p.2: the attached row is SP in R-2c and • in R-3a, R-3aa, R-3b and RU; "-" (not permitted) elsewhere, where
# the use rule already fails it.
ATTACHED_ALLOWED = {"R-2c", "R-3a", "R-3aa", "R-3b", "RU"}


@pytest.mark.parametrize("district", DISTRICTS)
def test_an_attached_building_holds_three_to_six_units(district):
    rules = rules_of(district)
    rid = f"{district}.attached_units_per_building"
    if district not in ATTACHED_ALLOWED:
        assert rid not in rules
        assert outcome(rules[f"{district}.use"], {"use": "one_family_attached"}, USES) == "fail"
        return
    r = rules[rid]
    for units, expect in [(1, "fail"), (2, "fail"), (3, "pass"), (4, "pass"), (5, "pass"), (6, "pass"), (7, "fail"),
                          (12, "fail")]:
        assert outcome(r, {"use": "one_family_attached", "attached_units_in_building": units}, USES) == expect, units
    # the cap is on the whole building, never this lot's units: two units here of a row of eight still fails
    assert outcome(r, {"use": "one_family_attached", "dwelling_units": 2, "attached_units_in_building": 8},
                   USES) == "fail"
    assert outcome(r, {"use": "one_family_attached", "dwelling_units": 3}, USES) == "needs_review"
    assert outcome(r, {"use": "multiple_family", "attached_units_in_building": 9}, USES) == "not_applicable"
