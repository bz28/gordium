"""The code decision's one rule, walked over every combination of the dwelling's facts (review round 5: each round
found another combination of the same facts, so the class is pinned here, not the instance).

code_scope.decide gives the Residential Code only if
  1. every fact it reads is stated, or listed in which_code.assumes as a reading the architect can accept (a fact
     with no reading, an ADU's kind or the attached building's units, must be stated);
  2. no two stated facts contradict each other, and none is of a kind Gordium can't read;
  3. no stated fact is read as not stated (one set aside by the measuring, or one a host couldn't send).
And never where the law decides otherwise: more than two dwelling units in one building unless three or more
townhouse units, more than one ADU whose kinds aren't all known, a care facility, a home occupation or rooms let.

The oracle below says each of these from the facts alone, never from decide's own code. The ADU and dwelling cluster
is walked in full (about 60,000 cases, a few seconds); set aside and not sent are walked fact by fact."""

import itertools

import pytest

from design_checker import code_scope

DRAWN = {code_scope.STORIES_DRAWN: True, "stories": 2}
BUILDING = {"separate_means_of_egress": True, "townhouse_units": True}
USES = {"one_family_detached": 1, "two_family": 2, "one_family_semi_detached": 2, "one_family_attached": None}
LOT_UNITS = {"one_family_detached": 1, "two_family": 2, "one_family_semi_detached": 1, "one_family_attached": 1}
DOMAIN = {
    "dwelling_units": (None, 0, 1, 2, 3, "two"),
    "accessory_dwelling_unit": (None, True, False, "yes"),
    "adu_detached": (None, True, False),
    "adus_on_parcel": (None, 0, 1, 2),
    "home_occupation": (None, True, False),
    "rooms_let_for_profit": (None, 0, 1),
    "care_facility": (None, True, False),
}
ATTACHED_UNITS = (None, 1, 2, 3, 4)
ASSUMABLE = {"care_facility", "home_occupation", "rooms_let_for_profit", "accessory_dwelling_unit", "dwelling_units",
             "adus_on_parcel"}


def is_count(v):
    return type(v) in (int, float) and v >= 0


def problems(use, f):
    """Why the facts can't give the Residential Code, by the rule and the law alone ([] when they may)."""
    out = []
    adu, det, many = f["accessory_dwelling_unit"], f["adu_detached"], f["adus_on_parcel"]
    for k in ("dwelling_units", "adus_on_parcel", "rooms_let_for_profit", "attached_units_in_building"):
        if f.get(k) is not None and not is_count(f[k]):
            out.append(f"{k} unreadable")
    for k in ("accessory_dwelling_unit", "adu_detached", "home_occupation"):
        if f.get(k) is not None and type(f[k]) is not bool:
            out.append(f"{k} unreadable")
    no_adu = adu is False or (adu is None and many == 0 and det is None)
    if not adu is True and not no_adu and (det is not None or (is_count(many) and many > 0)):
        out.append("an ADU's kind or count without the ADU")            # rule 2 (and never "no ADU": rule 3)
    if adu is False and (det is not None or (is_count(many) and many > 0)):
        out.append("no ADU, and its kind or count")
    if adu is True and many == 0:
        out.append("an ADU, and none on the parcel")
    if adu is True and det is None:
        out.append("an ADU whose kind isn't stated")                     # rule 1: no reading for it
    if adu is True and is_count(many) and many > 1:
        out.append("several ADUs, their kinds unknown")                  # the law (R202 DWELLING, 310.3)
    if is_count(f["dwelling_units"]) and f["dwelling_units"] != LOT_UNITS[use]:
        out.append("dwelling units disagree with the use")             # rule 2
    if f["care_facility"] is True or f["home_occupation"] is True or (is_count(f["rooms_let_for_profit"])
                                                                        and f["rooms_let_for_profit"] > 0):
        out.append("a use beyond the dwelling")                         # the law: a person's check
    attached = adu is True and det is False
    if use == "one_family_attached":
        units = f["attached_units_in_building"]
        if units is None:
            out.append("the attached building's units not stated")      # rule 1: no reading for it
        elif is_count(units) and units < 2:
            out.append("an attached dwelling of one unit")              # rule 2
        elif is_count(units) and units >= 3 and attached:
            out.append("a townhouse unit holding an ADU")
        elif is_count(units) and units + attached >= 3 and units < 3:
            out.append("three units in one building")                   # the law (310.3)
    elif USES[use] + attached >= 3:
        out.append("three units in one building")
    return out


def cases():
    for use in USES:
        keys = list(DOMAIN)
        units = ATTACHED_UNITS if use == "one_family_attached" else (None,)
        for combo in itertools.product(*(DOMAIN[k] for k in keys), units):
            f = dict(zip(keys + ["attached_units_in_building"], combo))
            yield use, f


def decided(use, f):
    values = {**DRAWN, "use": use, **{k: v for k, v in f.items() if k != "care_facility" and v is not None}}
    building = {**BUILDING, **({"care_facility": f["care_facility"]} if f["care_facility"] is not None else {})}
    return code_scope.decide(values, building)


def test_the_residential_code_only_where_every_fact_is_stated_or_assumed_and_none_contradicts():
    walked, residential, wrong = 0, 0, []
    for use, f in cases():
        got = decided(use, f)
        walked += 1
        if got["code"] != code_scope.RESIDENTIAL:
            continue
        residential += 1
        why = problems(use, f)                                     # rules 2 and the law
        # rule 1: each fact read is stated or assumed (and only an assumable one may be assumed)
        # an ADU's kind and the parcel's count of them are read only beside a stated ADU
        read = ASSUMABLE - {"adus_on_parcel"} | ({"adu_detached", "adus_on_parcel"} if f["accessory_dwelling_unit"]
                                                  is True else set())
        assumed = set(got["facts"].get("assumed") or [])
        # "0 ADUs on the parcel" states there is none
        stated = lambda k: f.get(k) is not None or (k == "accessory_dwelling_unit" and f["adus_on_parcel"] == 0)
        for k in read:
            if not stated(k) and k not in assumed:
                why.append(f"{k} neither stated nor assumed")
        if not assumed <= ASSUMABLE or len(got["assumes"]) != len(assumed):
            why.append(f"assumes {sorted(assumed)} not listed as readings")
        for k in assumed:
            if stated(k):
                why.append(f"{k} stated but listed as assumed")
        if why:
            wrong.append((use, f, why))
    assert walked > 50000 and residential > 50                     # the walk covers both sides
    assert wrong == [], f"{len(wrong)} cases break the rule, e.g. {wrong[:3]}"


BASE = {"use": "one_family_detached", "dwelling_units": 1, "accessory_dwelling_unit": True, "adu_detached": True,
        "adus_on_parcel": 1, "home_occupation": False, "rooms_let_for_profit": 0}


def test_the_baseline_is_the_residential_code_with_nothing_assumed():
    got = code_scope.decide({**DRAWN, **BASE}, {**BUILDING, "care_facility": False})
    assert got["code"] == code_scope.RESIDENTIAL and got["assumes"] == []


@pytest.mark.parametrize("key", code_scope.READS)
@pytest.mark.parametrize("how", ["set aside", "not sent"])
def test_a_fact_set_aside_or_not_sent_is_never_read_as_not_stated(key, how):
    values = {**DRAWN, **BASE}
    if how == "set aside":
        values[code_scope.SET_ASIDE] = {key: "it contradicts another"}
        building = {**BUILDING, "care_facility": False}
    else:
        values.pop(key, None)                                     # the host left it out ...
        building = {**BUILDING, "care_facility": False, "facts_not_sent": [key]}     # ... and says so
        if key == "care_facility":
            building.pop("care_facility")
    got = code_scope.decide(values, building)
    assert got["code"] is None and key.replace("_", " ") in got["why"]
