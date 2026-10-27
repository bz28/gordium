"""R-2c's lot sizes by units and occupants against every reading, worked out independently (#r2 review round 4).

Four review rounds each found a hand-merging slip in these rows. So this test does not trust the rule's one merged
formula: it works out each open reading on its own, unit by unit, from chart notes 5 and 6 (every way the stated
occupants can be split between the units; the whole building's lot or each row house's own; note 6's 500 sf instead
of the 300 sf or on top of it), and asserts the rule's verdict is their every-reading combination over thousands of
random designs: complies only if every reading passes, does not comply only if every reading fails, else needs
review. A fact not stated (attached_units_in_building, the most occupants in one unit) is every value it can take.
"""

import itertools
import random

import pytest

from rule_format.rulebook import REPO, load, outcome

RULES = {r["id"]: r for r in load(REPO / "regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/R-2c.yaml")["rules"]}
USES = {"use": {"one_family_semi_detached", "two_family", "one_family_attached"}}


def splits(n, units):
    """Every way n occupants can be split between `units` dwelling units (counts per unit, in order)."""
    if units == 1:
        yield (n,)
        return
    for first in range(n + 1):
        for rest in splits(n - first, units - 1):
            yield (first,) + rest


def note_5(split):
    """Chart note 5: 2,000 sf for the first occupant in each dwelling unit, + 400 sf for each more in that unit."""
    return sum(2000 + 400 * max(o - 1, 0) for o in split)


def note_6(split, on_top):
    """Chart note 6: 1,500 sf for each unit, + 300 sf for each further occupant in it, + 500 sf for each occupant past
    five in it, instead of the 300 sf (on_top False) or on top of it (on_top True)."""
    return sum(1500 + 300 * max(o - 1, 0) + (500 if on_top else 200) * max(o - 5, 0) for o in split)


def combine(requirements, lot, can_pass=True):
    """The every-reading verdict: requirements is every reading's least lot area (None: a reading under which the
    lot can never be shown enough, e.g. unknown occupants elsewhere, though its least known part still decides fail)."""
    known = [r for r, _ in requirements]
    if can_pass and all(open_ is False for _, open_ in requirements) and all(lot >= r for r in known):
        return "pass"
    if all(lot < r for r in known):
        return "fail"
    return "needs_review"


def two_unit_verdict(lot, units, n, most):
    """Semi-detached or two-family: units on the lot (1 or 2), n occupants, the most in one unit (None: not stated)."""
    cases = [s for s in splits(n, units) if most is None or max(s) == most]
    return combine([(note_5(s), False) for s in cases], lot)


def attached_verdict(lot, du, n, building):
    """One-family attached under every reading: this lot's units du (at least one), n occupants on this lot, the
    units in the whole building (None: not stated, any of 3 to 6 or more)."""
    reqs = []
    own = max(du, 1)
    for s in splits(n, own):                                    # each row house's own lot
        for on_top in (False, True):
            reqs.append((note_6(s, on_top), False))
    for b in ([building] if building is not None else range(1, 9)):
        whole = max(du, b, 3)
        # The lot holds the whole building exactly when its units are that building's units: fewer, and the rest of
        # the building (with occupants nobody stated) is on other lots; more, and the extra units belong to some
        # other building, whose other parts and occupants are elsewhere. Only then is every occupant counted.
        holds_all = du == b
        for s in splits(n, whole):                              # the building's lot (others' occupants at least 0)
            for on_top in (False, True):
                reqs.append((note_6(s, on_top), not holds_all))
    can_pass = du >= 1 and building is not None
    return combine(reqs, lot, can_pass)


def _near(rng, values):
    """A lot area at, just under or just over one of the requirements, or anywhere."""
    v = rng.choice(sorted(values))
    return rng.choice([v, v - 1, v + 1, rng.randint(0, 2 * v + 10)])


@pytest.mark.parametrize("use", ["one_family_semi_detached", "two_family"])
def test_the_two_unit_rows_are_the_every_reading_combination(use):
    rule = RULES[f"R-2c.lot_area_{use}"]
    rng = random.Random(20261021)
    tried, seen = 0, set()
    for _ in range(3000):
        units = rng.choice([1, 2]) if use == "one_family_semi_detached" else 2
        n = rng.randint(0, 8)
        most = rng.choice([None, None] + list(range(1, n + 1)))
        if most is not None and not any(max(s) == most for s in splits(n, units)):
            continue                                            # a split no units can have: not a design
        reqs = {note_5(s) for s in splits(n, units)}
        lot = _near(rng, reqs)
        given = {"use": use, "lot_area": lot, "occupants": n}
        if use == "one_family_semi_detached":
            given["dwelling_units"] = units
        if most is not None:
            given["occupants_most_in_one_unit"] = most
        want = two_unit_verdict(lot, units, n, most)
        assert outcome(rule, given, USES) == want, given
        tried, seen = tried + 1, seen | {want}
    assert tried > 2000 and seen == {"pass", "fail", "needs_review"}      # every verdict really exercised


def test_the_attached_row_is_the_every_reading_combination():
    rule = RULES["R-2c.lot_area_one_family_attached"]
    rng = random.Random(20261021)
    tried, seen = 0, set()
    for _ in range(3000):
        du = rng.randint(0, 6)
        n = rng.randint(0, 8)
        building = rng.choice([None, 2, 3, 4, 5, 6, 7])
        reqs = {note_6(s, t) for k in {max(du, 1), max(du, building or 3, 3)} for s in splits(n, k) for t in (0, 1)}
        lot = _near(rng, reqs)
        given = {"use": "one_family_attached", "lot_area": lot, "dwelling_units": du, "occupants": n}
        if building is not None:
            given["attached_units_in_building"] = building
        want = attached_verdict(lot, du, n, building)
        assert outcome(rule, given, USES) == want, given
        tried, seen = tried + 1, seen | {want}
    assert tried == 3000 and seen == {"pass", "fail", "needs_review"}


# Boundary cases written straight from the law (chart p.3 notes 5 and 6, §325-3B), worked by hand, not from the rule
# or the model above: a third check, so a mistake the rule and the model share is still caught.
#   (use, lot area, dwelling units on this lot, occupants, units in the building, most in one unit) -> verdict
LAW = [
    # one-family attached (note 6: 1,500 sf a unit, +300 sf per further occupant in a unit, +500 sf past five)
    ("one_family_attached", 4500, 3, 1, 3, None, "pass"),          # the whole 3-unit building, 1 occupant: 3 x 1,500
    ("one_family_attached", 4499, 3, 1, 3, None, "fail"),          # short of the three units' first occupants
    ("one_family_attached", 1500, 1, 1, 3, None, "needs_review"),  # its own unit fits; the building isn't all here
    ("one_family_attached", 1499, 1, 1, 3, None, "fail"),          # short even for its own unit
    ("one_family_attached", 6000, 4, 1, 3, None, "needs_review"),  # round 5: 4 units here, 3 in the building
    ("one_family_attached", 11000, 6, 6, 6, None, "pass"),         # 6 units, 6 all in one: 9,000 + 5 x 300 + 500
    ("one_family_attached", 10999, 6, 6, 6, None, "needs_review"),
    ("one_family_attached", 8999, 6, 6, 6, None, "fail"),          # under 6 x 1,500 however they are split
    # two-family (note 5: 2,000 sf for the first occupant in each of its two units, +400 sf per further occupant)
    ("two_family", 4000, None, 2, None, 1, "pass"),                # one in each unit: 2 x 2,000
    ("two_family", 4000, None, 2, None, None, "needs_review"),     # both may be in one unit: 4,400 sf
    ("two_family", 4399, None, 2, None, 2, "fail"),                # both in one unit
    ("two_family", 3999, None, 2, None, None, "fail"),             # under 4,000 however they are split
    # semi-detached, one half on its own lot
    ("one_family_semi_detached", 2000, 1, 1, None, None, "pass"),
    ("one_family_semi_detached", 1999, 1, 1, None, None, "fail"),
]


@pytest.mark.parametrize("use, lot, du, n, building, most, want", LAW)
def test_the_rule_and_the_model_both_match_the_law_at_its_boundaries(use, lot, du, n, building, most, want):
    given = {"use": use, "lot_area": lot, "occupants": n}
    given |= {k: v for k, v in (("dwelling_units", du), ("attached_units_in_building", building),
                                ("occupants_most_in_one_unit", most)) if v is not None}
    assert outcome(RULES[f"R-2c.lot_area_{use}"], given, USES) == want
    model = (attached_verdict(lot, du, n, building) if use == "one_family_attached"
             else two_unit_verdict(lot, du or 2, n, most))
    assert model == want
