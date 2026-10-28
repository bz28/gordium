"""The one-family occupancy row shows the limit the law sets for this household, in every district and owner case.

Item 12's deep run: R-1a's owner-occupied row showed "1 required" where §325-3B allows 2 (the verdict was right; the
number shown was the first way's). Expected limits are the law's, read by hand from §325-3B DWELLING, ONE-FAMILY
(chapter p.7): "not more than one unrelated individual"; "In the R-1 Zones ... not more than two unrelated
individuals ... if the dwelling is owner-occupied"; "In the R-2 and R-3 Zones ... two"; RU named apart (one). With an
accessory dwelling unit on the lot the R-1 allowance is the open question (needs review), so the cases here say no ADU.
"""

import copy

import pytest

from design_checker import present, scenarios
from design_checker.check import check_site

SMALL = [[5, 12], [25, 12], [25, 22], [5, 22]]


def law_limit(district, owner):
    if district.startswith("R-1"):
        return 2 if owner else 1
    return 1 if district == "RU" else 2


def _row(district, **facts):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "12_r3a_two_family_at_the_building_limits.yaml"))
    sc["district"], sc["use"] = district, "one_family_detached"
    sc["lot"]["points"] = [[0, 0], [200, 0], [200, 300], [0, 300]]
    for b in sc["buildings"]:
        b["outline"] = SMALL
    s, f, extras = scenarios.site(sc)
    items = check_site(s, {**f, **facts}, extras=extras)["view"]["items"]
    return next(i for i in items if i.get("rule") == f"{district}.occupancy_one_family")


@pytest.mark.parametrize("owner", [True, False])
@pytest.mark.parametrize("district", ["R-1a", "R-1b", "R-2a", "R-2b", "R-2c", "R-3a", "R-3aa", "R-3b", "RU"])
def test_the_occupancy_row_shows_the_laws_limit(district, owner):
    limit = law_limit(district, owner)
    for people in (1, limit, limit + 1):
        row = _row(district, unrelated_persons=people, unrelated_persons_with_children=people, owner_occupied=owner,
                   accessory_dwelling_unit=False, functional_family_unit=False, home_occupation=False)
        assert row["status"] == (present.COMPLIES if people <= limit else present.FAILS), (people, row["status"])
        assert row["required"] == str(limit), (people, row["required"], row["detail"]["line"])
        assert row["proposed"] == str(people), (people, row["proposed"])
