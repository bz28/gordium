"""The checker gives exactly the same answer whether the rule files come fresh from disk or from the cache
(rule_format.rulebook._kept), in every district that has a rulebook, and a second check is much faster."""
import json
import sys
import time

import pytest

from design_checker.check import check_site
from rule_format import rulebook
from rule_format.rulebook import REPO, jurisdictions, rulebook_paths

sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_measure import FACTS, box, lot  # noqa: E402

PLAIN = lot([(0, 0), (50, 0), (50, 100), (0, 100)])
HOUSES = [box(10, 25, 40, 75, 0, 30),          # inside every yard
          box(3, 20, 47, 95, 0, 38),           # too close to every line, too tall
          box(8, 22, 41, 78, 0, 36.5)]         # near the limits: rows that turn on the survey


def districts():
    return [(j.relative_to(REPO).as_posix(), p.stem) for j in jurisdictions()
            for p in rulebook_paths(j / "5_zoning_rules") if p.parent == j / "5_zoning_rules"]


def answer(result) -> str:
    return json.dumps(result, sort_keys=True, default=repr)


@pytest.mark.parametrize("city,zone", districts())
def test_every_district_checks_the_same_with_and_without_the_cache(city, zone):
    for surveyed in (True, False):
        facts = {**FACTS, "jurisdiction": city, "zone": zone, "lot_surveyed": surveyed}
        for house in HOUSES:
            site = {"units": "ft", "lot": PLAIN, "buildings": [house], "problems": []}
            rulebook._KEPT.clear()
            cold = answer(check_site(site, facts))          # every file parsed fresh
            warm = answer(check_site(site, facts))          # every file from the cache
            assert warm == cold, (zone, surveyed, house["id"] if isinstance(house, dict) else house)


def test_there_is_a_district_to_check():
    assert districts()


def test_a_rule_edited_in_one_check_never_reaches_the_next(monkeypatch):
    """A caller that edits the rules it was given (here: every check turned to True) can't make the next check
    pass: the cache hands out copies."""
    city, zone = districts()[0]
    facts = {**FACTS, "jurisdiction": city, "zone": zone}
    site = {"units": "ft", "lot": PLAIN, "buildings": [HOUSES[1]], "problems": []}
    before = answer(check_site(site, facts))
    for rule in rulebook.load(rulebook.rulebook_for(REPO / city, zone))["rules"]:
        rule["check"] = "True"
    assert answer(check_site(site, facts)) == before
    assert "FAIL" in before


def test_a_second_check_is_faster_than_a_cold_one():
    city, zone = districts()[0]
    facts = {**FACTS, "jurisdiction": city, "zone": zone}
    site = {"units": "ft", "lot": PLAIN, "buildings": [HOUSES[0]], "problems": []}
    check_site(site, facts)                     # imports and the formula cache warmed for both timings
    cold = []
    for _ in range(3):
        rulebook._KEPT.clear()
        t = time.perf_counter()
        check_site(site, facts)
        cold.append(time.perf_counter() - t)
    warm = []
    for _ in range(3):
        t = time.perf_counter()
        check_site(site, facts)
        warm.append(time.perf_counter() - t)
    assert min(warm) < 0.8 * min(cold), (warm, cold)      # ~0.4x in practice
