"""Queue item 12: real City of Ithaca lots with results worked out by hand from the law (not from Gordium's code).

Deep run (test_data/test_sites/new_york/ithaca_city/deep_run/): one full design per district family (R-1, R-2,
R-3/RU) on a real tax lot, every rule that applies worked out by hand; checked here headless with the scenario
machinery, and in Rhino by apps/rhino_plugin/tests/deep_run_in_rhino.py.
Light run (light_run/expected.yaml): one real address per district, for the in-Rhino start flow
(apps/rhino_plugin/tests/light_run_in_rhino.py, live lookups); checked here for completeness and licensing only."""
import json

import pytest
import yaml

from design_checker import scenarios
from design_checker.check import check_site
from rule_format.rulebook import REPO

DEEP = scenarios.paths(scenarios.SITES)
LIGHT = REPO / "test_data/test_sites/new_york/ithaca_city/light_run"
DISTRICTS = ["R-1a", "R-1b", "R-2a", "R-2b", "R-2c", "R-3a", "R-3aa", "R-3b", "RU"]


def test_one_deep_site_per_district_family_each_rule_with_working_and_a_citation():
    families = sorted(scenarios.load(p)["district"][:3] for p in DEEP)
    assert families == ["R-1", "R-2", "R-3"]
    for p in DEEP:
        sc = scenarios.load(p)
        for block in [sc["expected"], (sc.get("then") or {}).get("expected") or {}]:
            for rule, want in block.items():
                assert want["status"] in scenarios.CAUTION and want.get("working") and want.get("cites"), (p.name, rule)


@pytest.mark.parametrize("path", DEEP, ids=[p.stem for p in DEEP])
def test_every_rule_gordium_shows_has_a_hand_worked_answer(path):
    """'Every rule's expected answer': each rule row Gordium shows for the design as drawn is worked out by hand."""
    sc = scenarios.load(path)
    s, f, extras = scenarios.site(sc)
    view = check_site(s, f, extras=extras)["view"]
    shown = {i["rule"] for i in view["items"] if i.get("rule")}
    assert shown == set(sc["expected"]), (sorted(shown - set(sc["expected"])), sorted(set(sc["expected"]) - shown))


@pytest.mark.parametrize("path", DEEP, ids=[p.stem for p in DEEP])
def test_gordium_gives_the_hand_worked_answer(path):
    sc = scenarios.load(path)
    known = sc.get("disagreements") or {}
    for step in scenarios.run(sc):
        for r in step["rows"]:
            assert r["match"] or (known.get(r["rule"]) or {}).get("gordium") == r["gordium"], \
                f"{path.stem} {step['step']}: {r['rule']} expected {r['expected']}, Gordium {r['gordium']} ({r['why']})"


@pytest.mark.parametrize("path", DEEP, ids=[p.stem for p in DEEP])
def test_never_a_false_pass(path):
    sc = scenarios.load(path)
    for step in scenarios.run(sc):
        for r in step["rows"]:
            assert not (r["expected"] == "does_not_comply" and r["gordium"] == "complies"), (path.stem, r)


def test_the_light_run_has_one_real_address_per_district_with_a_nudge_that_must_fail():
    doc = yaml.safe_load((LIGHT / "expected.yaml").read_text(encoding="utf-8"))
    assert list(doc["sites"]) == DISTRICTS
    for district, site in doc["sites"].items():
        assert site["zone"]["expect"] == district and site["parcel"].startswith("500700-")   # City of Ithaca SWIS
        assert site["lot"]["corner_lot"] == "no" and site["lot"]["area_sf"] > 0
        nudge = site["expected"]["nudge"]
        assert nudge["rule"] == f"{district}.front_yard" and nudge["status"] == "does_not_comply"
        assert nudge["proposed_ft"] == nudge["required_ft"] - 3                # beyond the ±2 ft tax-map tolerance
        assert site["expected"]["largest_house"].startswith(("limited by lot coverage", "limited by the yards"))


def test_the_light_run_keeps_only_what_each_source_allows():
    """The saved lookups are site_lookup's snapshots: the City's zoning, roads and overlays and the County's points
    are used live and never kept (their terms); the State's parcels and USGS ground are kept."""
    for district in DISTRICTS:
        snap = json.loads((LIGHT / "lookups" / f"{district}.json").read_text(encoding="utf-8"))
        for name in ("zone", "street_side", "corner_lot", "overlays"):
            assert snap["facts"][name]["value"] == "(used live, not stored)", (district, name)
        assert snap["facts"]["lot"]["value"]["outline_ft"]
