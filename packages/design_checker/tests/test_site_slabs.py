"""A slab on the ground outside the building (a site description's left_out[].slab, protocol 1.3): what Chapter 325
says of it decides its rows, and nothing it can't know is ever a pass or a failure.

The law (§325-3B BUILDING AREA, p. 5): building area includes "porches, attached or free standing decks, balconies
projecting more than two feet from a building or structure, ramps, and/or landings"; it "shall not include parking
areas and parking spaces. Pergolas and terraces and patios shall be exempt from total lot coverage requirements.
However, neither pergolas or terraces and patios above grade shall be located in a required yard." §325-18A (p. 49):
"All porches, attached or freestanding decks, ... ramps, and/or landings shall be considered a part of the building
in both the determination of required yards and lot coverage." TERRACE OR PATIO (p. 19): "less than 18 inches above
grade, ... Terraces and patios above grade shall not encroach into required yards."

The house is conformance scene 01's box house (every zoning row it measures complies), with one slab beside it on
the lot, not touching it (a freestanding deck counts in the yards too, so "not touching" must not clear them)."""

import copy
import json

import pytest

from design_checker import conformance, present, site_json
from design_checker.check import check_description
from design_checker.__main__ import answer
from rule_format.rulebook import REPO

SCENE = conformance.scenes()["01_box_house"]
SITE = json.loads((REPO / "test_data/host_conformance/expected/01_box_house.site.json").read_text(encoding="utf-8"))
FACTS = conformance.facts(SCENE)
NAME = 'Concrete 10"'
COVERAGE = "R-1b.lot_coverage"
YARDS = ("R-1b.front_yard", "R-1b.side_yards#east", "R-1b.side_yards#west", "R-1b.rear_yard", "R-1b.yard_projections")


def with_slab(kind, touching=False, name=NAME):
    doc = copy.deepcopy(SITE)
    slab = {"id": "slab-1", "layer": "Floors", "could_be_building": True, "touching": touching, "ground_like": False,
            "context": False, "slab": kind}
    if name is not None:
        slab["name"] = name
    doc["left_out"] = [slab]
    return doc


def statuses(doc):
    items = check_description(doc, dict(FACTS))["view"]["items"]
    return {i["id"]: i for i in items}


BEFORE = statuses(SITE)


def test_the_house_alone_complies_on_the_rows_a_slab_could_change():
    assert all(BEFORE[r]["status"] == present.COMPLIES for r in (COVERAGE,) + YARDS)
    assert "scope.not_included" not in BEFORE


def test_an_unmarked_slab_makes_lot_coverage_and_every_yard_need_review_naming_it_never_a_failure():
    after = statuses(with_slab("unmarked"))
    for r in (COVERAGE,) + YARDS:
        assert after[r]["status"] == present.REVIEW, r
        assert NAME in after[r]["reason"] and "slab-1" in after[r]["reason"], after[r]["reason"]
        assert "porch, deck, landing or ramp" in after[r]["reason"]
    assert not any(i["status"] == present.FAILS for i in after.values())
    # it is an object on the lot not measured, the row naming it as a slab to mark
    row = after["scope.not_included"]
    assert row["objects"] == ["slab-1"] and NAME in row["reason"] and "mark what it is" in row["reason"]
    # every other row as without it, but those whose rule reads a yard (the height's: §325-16C's bonus reads the yards)
    changed = {k for k in BEFORE if after[k]["status"] != BEFORE[k]["status"]} - {COVERAGE, *YARDS}
    assert changed == {"R-1b.height"}
    assert after["R-1b.height"]["status"] == present.REVIEW and NAME in after["R-1b.height"]["reason"]


def test_a_generic_left_out_object_not_touching_leaves_the_yards_alone_so_the_slab_is_what_reviews_them():
    """The difference the slab makes: a left-out object that doesn't touch the house only reviews lot coverage;
    an unmarked slab, which may be a freestanding deck (§325-18A), reviews the yards too."""
    doc = with_slab("unmarked")
    del doc["left_out"][0]["slab"]
    plain = statuses(doc)
    assert plain[COVERAGE]["status"] == present.REVIEW
    assert all(plain[r]["status"] == present.COMPLIES for r in YARDS)


def test_a_patio_is_not_in_lot_coverage_but_every_yard_needs_review_naming_it():
    after = statuses(with_slab("patio"))
    assert after[COVERAGE]["status"] == BEFORE[COVERAGE]["status"] == present.COMPLIES
    assert after[COVERAGE]["reason"] == BEFORE[COVERAGE]["reason"]
    for r in YARDS:
        assert after[r]["status"] == present.REVIEW, r
        assert NAME in after[r]["reason"] and "above grade" in after[r]["reason"], after[r]["reason"]
    assert "scope.not_included" not in after            # not an object that may be a building
    assert not any(i["status"] == present.FAILS for i in after.values())


def test_a_parking_area_or_driveway_changes_nothing():
    after = statuses(with_slab("parking", touching=None, name=None))
    assert {k: (v["status"], v.get("reason")) for k, v in after.items()} == \
        {k: (v["status"], v.get("reason")) for k, v in BEFORE.items()}


def test_a_slab_without_a_name_is_named_by_its_id():
    after = statuses(with_slab("unmarked", name=None))
    assert "slab-1" in after[COVERAGE]["reason"] and '"' not in after[COVERAGE]["reason"].split("the slab ")[1][:2]


def test_a_failure_the_house_has_stays_a_failure():
    """A slab never clears a row: the yards fail for a house over the front line, slab or no slab."""
    doc = with_slab("patio")
    for b in doc["buildings"]:
        for f in b["faces"]:
            f["points"] = [[x, y - 25, z] for x, y, z in f["points"]]
    before = statuses({**doc, "left_out": []})
    after = statuses(doc)
    failing = [r for r in YARDS if before[r]["status"] == present.FAILS]
    assert failing and all(after[r]["status"] == present.FAILS for r in failing)


@pytest.mark.parametrize("change, why", [
    (lambda o: o.update(slab="garage"), "left_out[0].slab: should be one of unmarked, patio, parking, not 'garage'"),
    (lambda o: o.update(slab=None), "left_out[0].slab: should be one of unmarked, patio, parking, not None"),
    (lambda o: o.update(name=3), "left_out[0].name: should be text"),
])
def test_a_slab_the_description_doesnt_know_is_refused(change, why):
    doc = with_slab("unmarked")
    change(doc["left_out"][0])
    with pytest.raises(site_json.SiteRefused) as e:
        site_json.validate(doc)
    assert any(r.startswith(why) for r in e.value.reasons), e.value.reasons


def test_extras_naming_slabs_are_refused_one_source():
    with pytest.raises(site_json.SiteRefused, match="site_slabs belongs in the site description"):
        site_json.for_measuring(site_json.to_site(with_slab("patio")), dict(FACTS), {site_json.SITE_SLABS: []})


def test_the_schema_file_names_the_slab_kinds_the_code_reads():
    schema = json.loads((REPO / "docs/protocol/site_description_v1.schema.json").read_text(encoding="utf-8"))
    assert schema["$defs"]["left_out"]["properties"]["slab"]["enum"] == list(site_json.SLAB_KINDS)


def test_the_worker_checks_a_slab_sent_as_json():
    reply = answer(json.loads(json.dumps({"id": 1, "cmd": "check_site", "protocol": "1.3",
                                          "site": with_slab("unmarked"), "facts": dict(FACTS)})))
    assert reply["ok"], reply
    row = next(i for i in reply["result"]["view"]["items"] if i["id"] == COVERAGE)
    assert row["status"] == present.REVIEW and NAME in row["reason"]
