"""The code decision's one rule, walked over every combination of the facts it reads (review rounds 5 and 6: each
round found another combination, so the class is pinned here, not the instance).

code_scope.decide gives the Residential Code only if
  1. every fact it reads is stated, or listed in which_code.assumes as a reading the architect can accept (a fact
     with no reading, an ADU's kind, the attached building's units for an attached use, the stories, must be stated);
  2. no two stated facts contradict each other, and none is of a kind Gordium can't read;
  3. no stated fact is read as not stated (one set aside by the measuring, or one a host couldn't send);
and the law agrees: a dwelling is "any building that contains one or two dwelling units" (RCNYS R202 DWELLING),
more in one building is Group R-2 (BCNYS 310.3) unless three or more townhouse units (R202 TOWNHOUSE, "a
single-family dwelling unit" each), an ADU in or on the building is one more of its units, R101.2 allows "not more
than three stories above grade plane", and a care facility, home occupation or rooms let is a person's check.

The oracle below says each of these from the facts and the law alone, never from decide's own code. The walk is
unrestricted (review round 6: a domain narrowed for one use hid the units count for the others): every fact the
decision reads, for every use, over every value class (unstated, 0, 1, 2, more, True, False, text), the whole
cluster crossed in full; the stories, which no other fact's meaning turns on, crossed with every use and the cluster
at a baseline. test_the_walk_covers_every_fact_for_every_use fails if a later change narrows it."""

import itertools

import pytest

from design_checker import code_scope

BUILDING = {"separate_means_of_egress": True, "townhouse_units": True}
# the use words, and what each is under R202: the dwelling units of the building (None: the attached building's
# own count says it), and the lot's (Ithaca's dwelling_units, an ADU left out)
USES = {"one_family_detached": (1, 1), "two_family": (2, 2), "one_family_semi_detached": (2, 1),
        "one_family_attached": (None, 1), "multiple_family": (None, None)}
DOMAIN = {
    "use": tuple(USES),
    "dwelling_units": (None, 0, 1, 2, 3, "two"),
    "attached_units_in_building": (None, 0, 1, 2, 3, 4, "four"),
    "accessory_dwelling_unit": (None, True, False, "yes"),
    "adu_detached": (None, True, False, "no"),
    "adus_on_parcel": (None, 0, 1, 2, "one"),
    "home_occupation": (None, True, False, "no"),
    "rooms_let_for_profit": (None, 0, 1, 2, "none"),
    "care_facility": (None, True, False),
    "stories": (None, 1, 3, 4, "three"),
}
CLASSES = {"unstated": lambda v: v is None, "zero": lambda v: v == 0 and type(v) is int, "one": lambda v: v == 1,
           "more": lambda v: type(v) is int and v >= 2, "yes": lambda v: v is True, "no": lambda v: v is False,
           "text": lambda v: isinstance(v, str)}
COUNT_FACTS = ("dwelling_units", "attached_units_in_building", "adus_on_parcel", "rooms_let_for_profit", "stories")
YES_NO_FACTS = ("accessory_dwelling_unit", "adu_detached", "home_occupation", "care_facility")
ASSUMABLE = {"care_facility", "home_occupation", "rooms_let_for_profit", "accessory_dwelling_unit", "dwelling_units",
             "adus_on_parcel"}


def is_count(v):
    return type(v) is int and v >= 0


def readable(f):
    """Every stated fact is of its kind."""
    return all(f.get(k) is None or is_count(f[k]) for k in COUNT_FACTS) and \
        all(f.get(k) is None or type(f[k]) is bool for k in YES_NO_FACTS)


def law(f):
    """Why the facts can't give the Residential Code, by the rules and the law alone ([] when they may)."""
    use, out = f["use"], []
    if use not in USES or USES[use] == (None, None):
        return ["not one of R101.2's dwellings"]
    if not readable(f):
        return ["a fact Gordium can't read"]
    building_units, lot_units = USES[use]
    adu, det, many = f["accessory_dwelling_unit"], f["adu_detached"], f["adus_on_parcel"]
    no_adu = adu is False or (adu is None and many == 0 and det is None)
    # the ADU's facts agree, and each ADU's kind is known
    if adu is not True and (det is not None or (many or 0) > 0):
        out.append("an ADU's kind or count without the ADU" if not no_adu or adu is None else "no ADU, and its facts")
    if adu is True and (det is None or many == 0 or (many or 1) > 1):
        out.append("an ADU whose facts are missing or disagree, or several ADUs")
    attached_adu = adu is True and det is False
    # the units: the use's own (or the attached building's), the lot's as stated, an attached ADU one more
    stated_building = f["attached_units_in_building"]
    if use == "one_family_attached":
        if stated_building is None:
            return out + ["the attached building's units not stated"]
        building_units = stated_building
        if building_units < 2:
            out.append("an attached dwelling of one unit")
    elif stated_building is not None and stated_building != building_units:
        out.append("the units in the building disagree with the use")       # round 6
    if f["dwelling_units"] is not None and f["dwelling_units"] != lot_units:
        out.append("the lot's dwelling units disagree with the use")
    units = building_units + attached_adu
    townhouse = use == "one_family_attached" and building_units >= 3 and not attached_adu    # townhouse units: stated
    if units > 2 and not townhouse:
        out.append("more than two dwelling units in one building (310.3)")
    if f["care_facility"] is True or f["home_occupation"] is True or (f["rooms_let_for_profit"] or 0) > 0:
        out.append("a use beyond the dwelling")
    if f["stories"] is None or f["stories"] > 3:
        out.append("not known to be three stories or fewer above grade plane")
    return out


def decided(f):
    values = {code_scope.STORIES_DRAWN: True,
              **{k: v for k, v in f.items() if k != "care_facility" and v is not None}}
    building = {**BUILDING, **({"care_facility": f["care_facility"]} if f["care_facility"] is not None else {})}
    return code_scope.decide(values, building)


def check(f, got) -> list[str]:
    """What is wrong with a Residential Code answer for these facts ([] when it stands)."""
    why = law(f)
    assumed = set(got["facts"].get("assumed") or [])
    adu = f["accessory_dwelling_unit"]
    read = ASSUMABLE - {"adus_on_parcel"} | ({"adus_on_parcel"} if adu is True else set())
    stated = lambda k: f.get(k) is not None or (k == "accessory_dwelling_unit" and f["adus_on_parcel"] == 0)
    why += [f"{k} neither stated nor assumed" for k in read if not stated(k) and k not in assumed]
    why += [f"{k} stated but listed as assumed" for k in assumed if stated(k)]
    if not assumed <= ASSUMABLE or len(got["assumes"]) != len(assumed):
        why.append(f"assumes {sorted(assumed)} not all listed as readings")
    return why


CLUSTER = [k for k in DOMAIN if k != "stories"]
BASE = {"use": "one_family_detached", "dwelling_units": 1, "attached_units_in_building": None,
        "accessory_dwelling_unit": True, "adu_detached": True, "adus_on_parcel": 1, "home_occupation": False,
        "rooms_let_for_profit": 0, "care_facility": False, "stories": 2}


def walk():
    """Every combination of the cluster (every use, every fact, every value) at 2 stories; then every stories value
    for every use, with each other fact at every value one at a time."""
    for combo in itertools.product(*(DOMAIN[k] for k in CLUSTER)):
        yield {**dict(zip(CLUSTER, combo)), "stories": 2}
    for use, s in itertools.product(DOMAIN["use"], DOMAIN["stories"]):
        for k in CLUSTER:
            for v in DOMAIN[k]:
                yield {**BASE, "use": use, "stories": s, k: v}


def test_the_walk_covers_every_fact_for_every_use():
    # every fact the decision reads is walked, over every value class its kind has, for every use word
    assert set(DOMAIN) == set(code_scope.READS), set(code_scope.READS) ^ set(DOMAIN)
    for k, values in DOMAIN.items():
        if k == "use":
            continue
        kinds = {"unstated", "text"} | ({"zero", "one", "more"} if k in COUNT_FACTS else {"yes", "no"})
        if k == "care_facility":
            kinds -= {"text"}            # a building-block fact: its kind is checked where it is read (_given)
        if k == "stories":
            kinds -= {"zero"}            # a story count is 1 or more where it is measured
        assert all(any(CLASSES[c](v) for v in values) for c in kinds), (k, kinds)
    seen = {(f["use"], k, repr(f[k])) for f in walk() for k in DOMAIN}
    assert all((u, k, repr(v)) in seen for u in DOMAIN["use"] for k in DOMAIN if k != "use" for v in DOMAIN[k])


def test_the_residential_code_only_where_the_rules_and_the_law_allow():
    walked, residential, wrong = 0, 0, []
    for f in walk():
        walked += 1
        got = decided(f)
        if got["code"] != code_scope.RESIDENTIAL:
            continue
        residential += 1
        if why := check(f, got):
            wrong.append(({k: v for k, v in f.items() if v is not None}, why))
    assert walked > 200000 and residential > 100                  # both sides of the line are walked
    assert wrong == [], f"{len(wrong)} cases break the rule, e.g. {wrong[:3]}"


def test_the_baseline_is_the_residential_code_with_nothing_assumed():
    got = decided(BASE)
    assert got["code"] == code_scope.RESIDENTIAL and got["assumes"] == []


@pytest.mark.parametrize("key", code_scope.READS)
@pytest.mark.parametrize("how", ["set aside", "not sent"])
def test_a_fact_set_aside_or_not_sent_is_never_read_as_not_stated(key, how):
    values = {code_scope.STORIES_DRAWN: True, **{k: v for k, v in BASE.items() if k != "care_facility" and v is not None}}
    building = {**BUILDING, "care_facility": False}
    if how == "set aside":
        values[code_scope.SET_ASIDE] = {key: "it contradicts another"}
    else:
        values.pop(key, None)                                     # the host left it out ...
        building.pop(key, None)
        building["facts_not_sent"] = [key]                        # ... and says so
    got = code_scope.decide(values, building)
    assert got["code"] is None and key.replace("_", " ") in got["why"]
