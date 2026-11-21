"""An object on the lot that isn't measured and stands apart from the house (a site description's left_out entry with
`touching: false`): a freestanding deck, porch, landing or ramp drawn as anything but the building (a Revit Generic
Model, a family of another category; a Rhino solid off the Building layer) is part of the building in the yards, so
the yards can't comply while it stands unmeasured on the lot (never a false pass).

The law (Chapter 325, 2026-10 text):
- §325-18A (p. 49): "All porches, attached or freestanding decks, balconies projecting more than two feet from a
  building or structure, ramps, and/or landings shall be considered a part of the building in both the
  determination of required yards and lot coverage."
- BUILDING AREA (§325-3B, p. 5): "including porches, attached or free standing decks, ... ramps, and/or landings.
  The total building area shall be used for determining required yards and maximum percentage of allowed lot
  coverage".
- DECK (p. 7): "A structure freestanding or attached to a building".
- YARD (p. 20): "That part of a lot not occupied by the principal building or structure and which shall not be
  occupied by any other building or structure from the ground upward unless specifically authorized".
- STRUCTURE (p. 19): "Anything constructed or erected on the ground or which is attached to another structure or
  building. Structures shall not include patios or terraces."

So an object that could be a structure (`could_be_building: true`), standing apart, keeps every required yard (to
the walls and to the eaves) at needs review, naming it; one that can't be (`could_be_building: false`: a Revit tree
or entourage, or an element the architect marked "Not a structure") doesn't. The check never sees where it stands
(the description has no outline for it), so every yard waits, not only the one it may stand in. Lot coverage already
waits on any object left out (unchanged here).

The house is conformance scene 01's box house (every zoning row it measures complies)."""

import copy
import json

import pytest

from design_checker import conformance, present, site_json
from design_checker.check import check_description
from rule_format.rulebook import REPO

SCENE = conformance.scenes()["01_box_house"]
SITE = json.loads((REPO / "test_data/host_conformance/expected/01_box_house.site.json").read_text(encoding="utf-8"))
FACTS = conformance.facts(SCENE)
COVERAGE = "R-1b.lot_coverage"
YARDS = ("R-1b.front_yard", "R-1b.side_yards#east", "R-1b.side_yards#west", "R-1b.rear_yard", "R-1b.yard_projections")


def with_object(touching=False, could_be_building=True, name=None, **more):
    doc = copy.deepcopy(SITE)
    o = {"id": "deck-1", "layer": "Generic Models", "could_be_building": could_be_building, "touching": touching,
         "ground_like": False, "context": False, **more}
    if name is not None:
        o["name"] = name
    doc["left_out"] = [o]
    return doc


def statuses(doc, extras=None):
    items = check_description(doc, dict(FACTS), extras=extras)["view"]["items"]
    return {i["id"]: i for i in items}


BEFORE = statuses(SITE)


def test_the_house_alone_complies_on_every_yard():
    assert all(BEFORE[r]["status"] == present.COMPLIES for r in (COVERAGE,) + YARDS)


def test_an_object_standing_apart_keeps_every_yard_at_needs_review_naming_it_never_a_failure():
    after = statuses(with_object(name="Deck - freestanding"))
    for r in YARDS:
        assert after[r]["status"] == present.REVIEW, r
        assert '"Deck - freestanding" (deck-1)' in after[r]["reason"], after[r]["reason"]
        assert "§325-18A" in after[r]["reason"] and "freestanding deck" in after[r]["reason"]
    assert after[COVERAGE]["status"] == present.REVIEW          # as before: any object left out
    assert not any(i["status"] == present.FAILS for i in after.values())
    # every other row as with any object left out that doesn't touch, but those whose rule reads a yard (the
    # height's: §325-16C's bonus reads the yards)
    plain = statuses(with_object(could_be_building=False))
    changed = {k for k in plain if after[k]["status"] != plain[k]["status"]}
    assert changed == {*YARDS, "R-1b.height"}, changed


def test_one_without_a_name_is_named_by_its_id():
    after = statuses(with_object())
    assert "deck-1" in after["R-1b.front_yard"]["reason"]


def test_one_that_cant_be_a_structure_leaves_the_yards_alone():
    """A Revit tree or a person (Planting, Entourage) or an element marked "Not a structure": not "constructed or
    erected" (STRUCTURE), so not in a yard's sense; still an object on the lot not measured (lot coverage waits)."""
    after = statuses(with_object(could_be_building=False))
    assert all(after[r]["status"] == present.COMPLIES for r in YARDS)
    assert after[COVERAGE]["status"] == present.REVIEW
    assert after["scope.not_included"]["objects"] == ["deck-1"]


def test_one_touching_or_not_known_to_reviews_the_yards_as_before():
    for touching in (True, None):
        after = statuses(with_object(touching=touching))
        assert all(after[r]["status"] == present.REVIEW for r in YARDS)
        assert "touching the building" in after["R-1b.front_yard"]["reason"]


def test_a_failure_the_house_has_stays_a_failure():
    doc = with_object()
    for b in doc["buildings"]:
        for f in b["faces"]:
            f["points"] = [[x, y - 25, z] for x, y, z in f["points"]]
    before = statuses({**doc, "left_out": []})
    after = statuses(doc)
    failing = [r for r in YARDS if before[r]["status"] == present.FAILS]
    assert failing and all(after[r]["status"] == present.FAILS for r in failing)


def test_extras_naming_objects_apart_are_refused_one_source():
    with pytest.raises(site_json.SiteRefused, match="standing_apart belongs in the site description"):
        site_json.for_measuring(site_json.to_site(with_object()), dict(FACTS), {site_json.STANDING_APART: []})


def test_many_objects_apart_are_named_up_to_five_and_counted():
    apart = [{"id": f"o{k}", "name": None if k % 2 else f"Thing {k}"} for k in range(7)]
    assert present._apart_names(apart) == '"Thing 0" (o0), o1, "Thing 2" (o2), o3, "Thing 4" (o4) and 2 more'
    assert present._apart_names(apart[:1]) == '"Thing 0" (o0)'


def test_the_view_without_the_list_counts_every_object_not_touching_as_apart():
    """present.view's own caution, for a caller that hands it left-out objects without the description's list."""
    items = [{"id": "R-1b.front_yard", "status": present.COMPLIES, "measure": "front_yard"}]
    present._cautious_for_left_out(items, ["deck-1"], [], apart=None)
    assert items[0]["status"] == present.REVIEW and "deck-1" in items[0]["reason"]
