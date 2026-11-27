"""The code decision's one rule, walked over every combination of the facts it reads (review rounds 5 to 7: each
round found another combination, so the class is pinned here, not the instance).

code_scope.decide gives the Residential Code only if
  1. every fact it reads is stated, or listed in which_code.assumes as a reading the architect can accept (a fact
     with no reading, an ADU's kind, the attached building's units, the stories, must be stated);
  2. no two stated facts contradict each other, and none is of a kind Gordium can't read;
  3. no stated fact is read as not stated (one set aside by the measuring, or one a host couldn't send);
and the law agrees. RCNYS R101.2 covers detached one- and two-family dwellings and townhouses "not more than three
stories above grade plane in height with a separate means of egress", a two-family one "in which each dwelling unit
has a separate means of egress"; its exception lets the architect apply the Building Code instead. R202: a DWELLING
is "any building that contains one or two dwelling units"; a TOWNHOUSE "a building that contains three or more
attached townhouse units", each "a single-family dwelling unit ... that has a separate means of egress". BCNYS 310.3:
more than two dwelling units, Group R-2; Chapter 3's other groups are the Building Code's. An ADU in or on the
building is one more of its units; a care facility, home occupation or rooms let is a person's check.

The oracle below says each of these from the facts and the law alone, never from decide's own code. Completeness is
automatic (review round 7): decide runs over the walk with its fact dictionaries recording every key it reads, and the
walk's domain must be exactly those keys, so a new read that isn't walked fails here by itself. The walk: the ADU and
dwelling cluster crossed in full, and every pair of values of every two facts (the building block's and check.py's
own included), the rest at a baseline that gives the Residential Code."""

import itertools

import pytest

from design_checker import code_scope

USES = {"one_family_detached": (1, 1), "two_family": (2, 2), "one_family_semi_detached": (2, 1),
        "one_family_attached": (None, 1), "multiple_family": (None, None)}
# what the house says, in the lot's facts (values) and the building block (building): every value class each takes
VALUES = {
    "use": tuple(USES),
    "dwelling_units": (None, 0, 1, 2, 3, "two"),
    "attached_units_in_building": (None, 0, 1, 2, 3, 4, "four"),
    "accessory_dwelling_unit": (None, True, False, "yes"),
    "adu_detached": (None, True, False, "no"),
    "adus_on_parcel": (None, 0, 1, 2, "one"),
    "home_occupation": (None, True, False, "no"),
    "rooms_let_for_profit": (None, 0, 1, 2, "none"),
    "stories": (None, 1, 3, 4, "three"),
    code_scope.STORIES_DRAWN: (None, True, False),
    code_scope.STORIES_HOW: (None, "typed", "read"),
    code_scope.STORIES_AT_MOST: (None, 2, 4),
    code_scope.SET_ASIDE: (None, {}, {"dwelling_units": "they disagree"}, {"zone": "they disagree"}),
}
BUILDING = {
    "care_facility": (None, True, False, "yes"),
    "follows_building_code": (None, True, False, "yes"),
    "separate_means_of_egress": (None, True, False, "no"),
    "townhouse_units": (None, True, False, "no"),
    "stories_above_grade_plane": (None, 0, 1, 3, 4, "three"),
    "occupancy_groups": (None, ["R-3"], ["R-2"], ["B", "R-3"], "R-3", ["office"]),
    "sprinkler_system": (None, "none", "nfpa_13", "wet pipe"),
    "egress_balcony_increase_taken": (None, True, False, "no"),
    "building_has_atrium": (None, True, False, "no"),
    "assembly_fixed_seating": (None, True, False, "no"),
    "special_egress_spaces": (None, True, False, "no"),
    "merchandise_pads": (None, True, False, "no"),
    "emergency_escape_openings_1031": (None, True, False, "no"),
    "r2_sleeping_units": (None, True, False, "no"),
    "occupied_outdoor_areas": (None, True, False, "no"),
    "occupant_load_increased": (None, True, False, "no"),
    "other_level_egress_into_corridors": (None, True, False, "no"),     # section group 4
    "ambulatory_care_facility": (None, True, False, "no"),
    "corridors_within_dwelling_units": (None, True, False, "no"),     # section group 4b
    "emergency_voice_alarm_system": (None, True, False, "no"),        # section group 5a
    "mezzanines": (None, True, False, "no"),                          # the occupant-load ceiling (2026-11-26)
    "loads_not_by_area": (None, True, False, "no"),
    "facts_not_sent": (None, [], ["dwelling_units"], ["sprinkler_system"], "use"),
}
DOMAIN = {**VALUES, **BUILDING}
GROUPS = set(code_scope.GROUPS)
ASSUMABLE = {"care_facility", "home_occupation", "rooms_let_for_profit", "accessory_dwelling_unit", "dwelling_units",
             "adus_on_parcel"}
# a baseline that gives the Residential Code with nothing assumed: a one-family house with a detached ADU
BASE = {"use": "one_family_detached", "dwelling_units": 1, "attached_units_in_building": None,
        "accessory_dwelling_unit": True, "adu_detached": True, "adus_on_parcel": 1, "home_occupation": False,
        "rooms_let_for_profit": 0, "stories": 2, code_scope.STORIES_DRAWN: True, code_scope.STORIES_HOW: None,
        code_scope.STORIES_AT_MOST: None, code_scope.SET_ASIDE: None, "care_facility": False,
        "follows_building_code": None, "separate_means_of_egress": True, "townhouse_units": None,
        "stories_above_grade_plane": None, "occupancy_groups": None, "sprinkler_system": None,
        "egress_balcony_increase_taken": None, "building_has_atrium": None, "assembly_fixed_seating": None,
        "special_egress_spaces": None, "merchandise_pads": None,
        "emergency_escape_openings_1031": None, "r2_sleeping_units": None, "occupied_outdoor_areas": None,
        "occupant_load_increased": None, "other_level_egress_into_corridors": None, "ambulatory_care_facility": None,
        "corridors_within_dwelling_units": None, "emergency_voice_alarm_system": None, "mezzanines": None,
        "loads_not_by_area": None, "facts_not_sent": None}


def count(v, least=0):
    return type(v) is int and v >= least


def yes_no(v):
    return v is None or type(v) is bool


def law(f):
    """Why the facts can't give the Residential Code, by the rules and the law alone ([] when they may)."""
    use, out = f["use"], []
    # rule 2: each fact of its kind (a building block Gordium can't read is said, never used)
    kinds = [yes_no(f[k]) for k in ("accessory_dwelling_unit", "adu_detached", "home_occupation", "care_facility",
                                    "follows_building_code", "separate_means_of_egress", "townhouse_units",
                                    "egress_balcony_increase_taken", "building_has_atrium", "assembly_fixed_seating",
                                    "special_egress_spaces", "merchandise_pads", "emergency_escape_openings_1031",
                                    "r2_sleeping_units", "occupied_outdoor_areas", "occupant_load_increased",
                                    "other_level_egress_into_corridors", "ambulatory_care_facility",
                                    "corridors_within_dwelling_units", "emergency_voice_alarm_system", "mezzanines",
                                    "loads_not_by_area")]
    kinds += [f[k] is None or count(f[k]) for k in ("dwelling_units", "attached_units_in_building", "adus_on_parcel",
                                                    "rooms_let_for_profit", "stories")]
    kinds += [f["stories_above_grade_plane"] is None or count(f["stories_above_grade_plane"], 1),
              f["occupancy_groups"] is None or (isinstance(f["occupancy_groups"], list) and f["occupancy_groups"]
                                                and set(f["occupancy_groups"]) <= GROUPS),
              f["sprinkler_system"] in (None, *code_scope.SPRINKLERS),
              f["facts_not_sent"] is None or (isinstance(f["facts_not_sent"], list)
                                              and all(isinstance(x, str) for x in f["facts_not_sent"]))]
    if not all(kinds):
        return ["a fact Gordium can't read"]
    # rule 3: nothing it reads set aside or not sent
    unread = set((f[code_scope.SET_ASIDE] or {})) | set(f["facts_not_sent"] or [])
    if unread & set(code_scope.READS):
        out.append("a fact it reads is set aside or not sent")
    # R101.2's exception; Chapter 3's other groups; R101.2's dwellings only
    if f["follows_building_code"] is True:
        out.append("the architect applies the Building Code")
    if f["occupancy_groups"] and set(f["occupancy_groups"]) - {"R-3"}:
        out.append("an occupancy group the Building Code classifies")
    if USES[use] == (None, None):
        return out + ["not one of R101.2's dwellings"]
    building_units, lot_units = USES[use]
    adu, det, many = f["accessory_dwelling_unit"], f["adu_detached"], f["adus_on_parcel"]
    no_adu = adu is False or (adu is None and many == 0 and det is None)
    if adu is not True and (det is not None or (many or 0) > 0):
        out.append("an ADU's kind or count without the ADU" if not no_adu or adu is None else "no ADU, and its facts")
    if adu is True and (det is None or many == 0 or (many or 1) > 1):
        out.append("an ADU whose facts are missing or disagree, or several ADUs")
    attached_adu = adu is True and det is False
    stated_building = f["attached_units_in_building"]
    if use == "one_family_attached":
        if stated_building is None:
            return out + ["the attached building's units not stated"]
        building_units = stated_building
        if building_units < 2:
            out.append("an attached dwelling of one unit")
    elif stated_building is not None and stated_building != building_units:
        out.append("the units in the building disagree with the use")
    if f["dwelling_units"] is not None and f["dwelling_units"] != lot_units:
        out.append("the lot's dwelling units disagree with the use")
    units = building_units + attached_adu
    townhouse = use == "one_family_attached" and building_units >= 3 and not attached_adu
    if townhouse and f["townhouse_units"] is not True:
        out.append("three or more attached units not stated to be townhouse units (R202 TOWNHOUSE)")
    if not townhouse and f["townhouse_units"] is True:
        out.append("townhouse units in a building that is no townhouse (R202 TOWNHOUSE)")
    if units > 2 and not townhouse:
        out.append("more than two dwelling units in one building (310.3)")
    # R101.2: "with a separate means of egress", for each unit of a two-family dwelling stated
    if f["separate_means_of_egress"] is False:
        out.append("its means of egress stated not separate (R101.2)")
    if units == 2 and f["separate_means_of_egress"] is not True:
        out.append("a two-family dwelling whose units' separate means of egress isn't stated (R101.2 item 2)")
    if f["care_facility"] is True or f["home_occupation"] is True or (f["rooms_let_for_profit"] or 0) > 0:
        out.append("a use beyond the dwelling")
    # R101.2: not more than three stories above grade plane, the State's count or Ithaca's read from the drawing
    if f["stories_above_grade_plane"] is not None:
        if f["stories_above_grade_plane"] > 3:
            out.append("more than three stories above grade plane")
    elif f[code_scope.STORIES_DRAWN] is not True:
        out.append("Ithaca's stories not read from the drawing, the State's not stated")
    elif not ((f["stories"] is not None and f["stories"] <= 3) or
              (f["stories"] is None and f[code_scope.STORIES_AT_MOST] is not None
               and f[code_scope.STORIES_AT_MOST] <= 3)):
        out.append("not known to be three stories or fewer above grade plane")
    return out


class Reads(dict):
    """A dict that records every key decide reads from it."""
    seen: set = set()

    def get(self, k, default=None):
        Reads.seen.add(k)
        return super().get(k, default)

    def __getitem__(self, k):
        Reads.seen.add(k)
        return super().__getitem__(k)

    def __contains__(self, k):
        Reads.seen.add(k)
        return super().__contains__(k)


def decided(f, record=False):
    values = {k: f[k] for k in VALUES if f[k] is not None}
    building = {k: f[k] for k in BUILDING if f[k] is not None}
    if not record:
        return code_scope.decide(values, building)
    real = code_scope._given
    code_scope._given = lambda b: (lambda got: (Reads(got[0]), got[1]))(real(b))   # facts record their reads too
    try:
        return code_scope.decide(Reads(values), building)
    finally:
        code_scope._given = real


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


CLUSTER = ["use", "dwelling_units", "attached_units_in_building", "accessory_dwelling_unit", "adu_detached",
           "adus_on_parcel", "home_occupation", "rooms_let_for_profit"]


# a baseline giving the Residential Code for each of R101.2's dwellings (the pairs are walked from each, so a case
# several facts from the one-family house, a townhouse whose means of egress is said not separate, is two from its own)
BASES = [BASE,
         {**BASE, "use": "two_family", "dwelling_units": 2, "accessory_dwelling_unit": False, "adu_detached": None,
          "adus_on_parcel": None},
         {**BASE, "use": "one_family_semi_detached", "accessory_dwelling_unit": False, "adu_detached": None,
          "adus_on_parcel": None},
         {**BASE, "use": "one_family_attached", "attached_units_in_building": 4, "townhouse_units": True,
          "accessory_dwelling_unit": False, "adu_detached": None, "adus_on_parcel": None},
         {**BASE, "use": "one_family_attached", "attached_units_in_building": 2, "accessory_dwelling_unit": False,
          "adu_detached": None, "adus_on_parcel": None}]


def walk():
    """The cluster crossed in full (the rest at the baseline); then, from each dwelling's baseline, every pair of
    values of every two facts."""
    for combo in itertools.product(*(DOMAIN[k] for k in CLUSTER)):
        yield {**BASE, **dict(zip(CLUSTER, combo))}
    for base in BASES:
        for a, b in itertools.combinations(DOMAIN, 2):
            for va, vb in itertools.product(DOMAIN[a], DOMAIN[b]):
                yield {**base, a: va, b: vb}


def test_the_walk_is_exactly_what_the_decision_reads():
    """Completeness by recording: every key decide reads, over the whole walk, is a fact the walk varies, and every
    fact the walk varies is one decide reads (so the domain is never a hand-kept list that drifts)."""
    Reads.seen = set()
    for f in walk():
        decided(f, record=True)
    assert Reads.seen == set(DOMAIN), {"read, not walked": Reads.seen - set(DOMAIN),
                                       "walked, never read": set(DOMAIN) - Reads.seen}
    # and every pair of values of every two facts is walked, for every use
    seen = {(f["use"], k, repr(f[k])) for f in walk() for k in DOMAIN}
    assert all((u, k, repr(v)) in seen for u in USES for k in DOMAIN if k != "use" for v in DOMAIN[k])


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
    assert walked > 100000 and residential > 100                  # both sides of the line are walked
    assert wrong == [], f"{len(wrong)} cases break the rule, e.g. {wrong[:3]}"


@pytest.mark.parametrize("base", BASES, ids=lambda b: f"{b['use']}-{b['attached_units_in_building']}")
def test_each_baseline_is_the_residential_code_with_nothing_assumed(base):
    got = decided(base)
    assert got["code"] == code_scope.RESIDENTIAL and got["assumes"] == [] and law(base) == []


@pytest.mark.parametrize("key", code_scope.READS)
@pytest.mark.parametrize("how", ["set aside", "not sent"])
def test_a_fact_set_aside_or_not_sent_is_never_read_as_not_stated(key, how):
    f = dict(BASE)
    if how == "set aside":
        f[code_scope.SET_ASIDE] = {key: "it contradicts another"}
    else:
        f[key] = None                                             # the host left it out ...
        f["facts_not_sent"] = [key]                               # ... and says so
    got = decided(f)
    assert got["code"] is None and key.replace("_", " ") in got["why"]
