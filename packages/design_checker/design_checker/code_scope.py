"""Which New York code a building's egress is checked against: the 2025 Residential Code of New York State (RCNYS)
or the 2025 Building Code of New York State (BCNYS). Plain code over stated facts, no AI; decided
2026-11-22 (docs/decisions/2026-11-22_which_ny_code.md).

    decide(values, building) -> {"code": "residential_code" | "building_code" | None, "why": words, "cites": [...]}

The law (both books say the same, in their own words):

- RCNYS R101.2 (PDF p.24): "The provisions of this code shall apply to ... the following buildings and structures,
  provided that such building or structure is not more than three stories above grade plane in height with a
  separate means of egress ...: 1. Detached one-family dwellings. 2. Detached two-family dwellings in which each
  dwelling unit has a separate means of egress. 3. Townhouses. 4. Bed and breakfast dwellings. 5. Live/work units
  located in townhouses ... 6. Owner-occupied lodging houses that have five or fewer guestrooms and are provided with
  an automatic sprinkler system ... 7. Manufactured homes used as dwelling units." Its exception lets the BCNYS be
  applied to them instead, "provided that all applicable provisions of the Building Code of New York State are
  applied".
- BCNYS 101.2 (PDF p.22): the BCNYS covers "every building or structure", exception 1 sending the same list (1.1 to
  1.7) to the RCNYS.

`code` None is needs review: a fact the decision needs is missing or the facts leave both books possible; `why` says
which, in plain words. Never a guess for the Residential Code (principle 4).

`values` are the check's building values (Ithaca's measures: `use`, `stories`, `dwelling_units`,
`attached_units_in_building`, `home_occupation`, `rooms_let_for_profit`, `accessory_dwelling_unit`, `adu_detached`);
`building` the interior description's `building` block (the architect's statements for the state's code: FACTS).
"""

RESIDENTIAL = "residential_code"
BUILDING = "building_code"
CODES = (RESIDENTIAL, BUILDING)

# The interior description's `building` block (docs/interior/interior_description_format.md), each with its kind
FACTS = {
    "stories_above_grade_plane": "count",     # RCNYS R202 STORY ABOVE GRADE PLANE, the architect's count
    "separate_means_of_egress": "yes_no",     # every dwelling unit has a separate means of egress (R101.2 item 2)
    "townhouse_units": "yes_no",              # every unit is an R202 TOWNHOUSE UNIT (foundation to roof, two open sides)
    "care_facility": "yes_no",                # people other than the household receive care or day care here
    "follows_building_code": "yes_no",        # the architect applies the BCNYS (R101.2 exception)
    "occupancy_groups": "groups",             # BCNYS Chapter 3 groups, as the architect classifies the building
    "sprinkler_system": "sprinkler",          # none, nfpa_13 (903.3.1.1), nfpa_13r (903.3.1.2), nfpa_13d (903.3.1.3)
    "egress_balcony_increase_taken": "yes_no",
    "building_has_atrium": "yes_no",
}
GROUPS = ("A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "H-1", "H-2", "H-3", "H-4", "H-5", "I-1",
          "I-2", "I-3", "I-4", "M", "R-1", "R-2", "R-3", "R-4", "S-1", "S-2", "U")
SPRINKLERS = ("none", "nfpa_13", "nfpa_13r", "nfpa_13d")

R101 = "RCNYS R101.2"
B101 = "BCNYS 101.2 exception 1"
# Ithaca's use words (4_term_definitions/uses.yaml) that name a dwelling R101.2 lists, with its item and units
HOUSES = {"one_family_detached": ("a detached one-family dwelling", "item 1", 1),
          "one_family_detached_zero_lot_line": ("a detached one-family dwelling", "item 1", 1),
          "two_family": ("a detached two-family dwelling", "item 2", 2),
          # one of two one-family dwellings joined by a common wall: R202 DWELLING counts the units of the building
          # ("Any building that contains one or two dwelling units"), lot lines aside, so the pair is a two-family one
          "one_family_semi_detached": ("a two-family dwelling (two semi-detached units in one building)", "item 2", 2)}
ATTACHED = "one_family_attached"                  # three to six units in a row (§325-3B): a townhouse if R202's
# uses R101.2 lists only with conditions the use word doesn't settle
EITHER = {"bed_and_breakfast_inn": ("a bed and breakfast is under the Residential Code only as R202's BED AND "
                                    "BREAKFAST DWELLING (an owner-occupied conversion of a one-family dwelling, not "
                                    "more than ten transient lodgers, not more than five bedrooms for them; R101.2 "
                                    "item 4), else the Building Code (BCNYS 310.2, 310.4)")}

ASK_STORIES = ("state the building's stories above grade plane (Gordium: Stories above grade plane, as RCNYS R202 "
               "STORY ABOVE GRADE PLANE counts them)")


def _given(building: dict | None) -> tuple[dict, list[str]]:
    """The `building` block's facts of the right kind, and what is wrong with the others (each said, never used)."""
    out, bad = {}, []
    for k, v in (building or {}).items() if isinstance(building, dict) else []:
        kind = FACTS.get(k)
        ok = (kind == "count" and type(v) is int and v >= 1) or (kind == "yes_no" and type(v) is bool) or \
             (kind == "groups" and isinstance(v, list) and v and all(g in GROUPS for g in v)) or \
             (kind == "sprinkler" and v in SPRINKLERS)
        if ok:
            out[k] = v
        elif kind is not None:
            bad.append(f"the building's {k.replace('_', ' ')} is {v!r}, which Gordium can't read")
    return out, bad


def building_measures(building: dict | None) -> dict:
    """The BCNYS rulebook's building measures (its drafted/records/proposed_measures.yaml) the `building` block
    states: occupancy_group_i4 and other_occupancy_present from the groups, the two sprinkler systems the limits
    name from the system, and the two stated yes/no facts. A fact not stated is left out (its rules need review)."""
    facts, _ = _given(building)
    out = {}
    if "occupancy_groups" in facts:
        out["occupancy_group_i4"] = "I-4" in facts["occupancy_groups"]
        out["other_occupancy_present"] = any(g != "I-4" for g in facts["occupancy_groups"])
    if "sprinkler_system" in facts:
        out["sprinklered_903_3_1_1"] = facts["sprinkler_system"] == "nfpa_13"
        out["sprinklered_903_3_1_2"] = facts["sprinkler_system"] == "nfpa_13r"
    for k in ("egress_balcony_increase_taken", "building_has_atrium"):
        if k in facts:
            out[k] = facts[k]
    return out


def _answer(code, why, cites, used):
    return {"code": code, "why": why, "cites": list(cites), "facts": used}


def stories_bound(values: dict, facts: dict) -> tuple[int | None, str]:
    """The most stories above grade plane the building can have (RCNYS R202), and where that comes from.

    The architect's count where stated. Else Ithaca's own count (`stories`), which can only be as many or more: the
    measuring gives it only when nothing drawn is below the ground (a part below it is the basement question, and
    the count needs review: places/ithaca_city/measure.py _stories_whole), so no basement or cellar R202 could count
    and Ithaca doesn't (R202 item 3, 6 ft for more than half the perimeter, is the State's alone); and what Ithaca
    leaves out the State does too: a mezzanine (both: "an intermediate level ... between the floor and ceiling of any
    story", R202 MEZZANINE), an attic "unfinished and without human occupancy" (R202 ATTIC is the space between the
    ceiling assembly and the roof assembly, inside the top STORY, which runs to "the floor or roof next above"; only
    a habitable attic is a story above grade plane, R316.3, and Ithaca counts that one, having human occupancy)."""
    if "stories_above_grade_plane" in facts:
        return facts["stories_above_grade_plane"], "stated by the architect (stories above grade plane, R202)"
    s = values.get("stories")
    if type(s) in (int, float) and s >= 1 and float(s).is_integer():
        return int(s), ("at most Ithaca's count of stories, " + f"{int(s)} (§325-3B STORY: nothing is drawn below "
                        "the ground, so every story the State counts above grade plane Ithaca counts too)")
    return None, "not known"


def decide(values: dict, building: dict | None) -> dict:
    """Which book governs the building's egress (module docstring), with why and the sections behind it."""
    values = values or {}
    facts, bad = _given(building)
    used = dict(facts)
    if bad:
        return _answer(None, "; ".join(bad) + ": which code governs can't be told", [R101], used)
    if facts.get("follows_building_code") is True:
        return _answer(BUILDING, "the architect applies the Building Code of New York State, as R101.2's exception "
                       "permits (\"provided that all applicable provisions of the Building Code of New York State are "
                       "applied\")", [R101 + " exception"], used)
    use = values.get("use")
    used["use"] = use
    if not isinstance(use, str) or not use:
        return _answer(None, "the building's use isn't stated (Gordium: Use), so which code governs can't be told",
                       [R101, B101], used)
    if facts.get("occupancy_groups") and any(g != "R-3" for g in facts["occupancy_groups"]):
        others = ", ".join(g for g in facts["occupancy_groups"] if g != "R-3")
        if use in HOUSES or use == ATTACHED:
            return _answer(None, f"the use is a dwelling the Residential Code can cover, but the occupancy groups "
                           f"stated include {others}, which only the Building Code classifies (BCNYS Chapter 3): "
                           "say which is right", [R101, B101], used)
        return _answer(BUILDING, f"its occupancy groups ({', '.join(facts['occupancy_groups'])}) are the Building "
                       "Code's; the Residential Code covers only the dwellings R101.2 lists", [R101, "BCNYS 101.2"],
                       used)
    if use in EITHER:
        return _answer(None, EITHER[use] + ": say which it is (Gordium: Follows Building Code)", [R101], used)
    if use not in HOUSES and use != ATTACHED:
        return _answer(BUILDING, f"its use ({use}) is none of the dwellings R101.2 lists (detached one- "
                       "and two-family dwellings, townhouses, bed and breakfast dwellings, live/work units in "
                       "townhouses, small owner-occupied lodging houses, manufactured homes), so the Building Code "
                       "covers it (101.2: \"every building or structure\")", [R101, "BCNYS 101.2"], used)
    # a dwelling R101.2 can cover: each condition it sets
    for key, words, cite in (
            ("care_facility", "people outside the household receive care or day care here: five or fewer may stay "
             "under the Residential Code only as BCNYS 305.2.3, 308.2.4, 308.3.2, 308.5.4 or 310.4.1 allow (most with "
             "a P2904 or 903.3.1.3 sprinkler system), more are a Building Code occupancy (Group E, I or R-4)",
             "BCNYS 308.2.4, 310.4.1"),
            ("home_occupation", "a home occupation is planned: if a significant part of the unit is a nonresidential "
             "use run by the tenant it is a live/work unit (BCNYS 202 LIVE/WORK UNIT), which R101.2 keeps under the "
             "Residential Code only in a townhouse (item 5; BCNYS 508.5)", "BCNYS 508.5")):
        if values.get(key) is True or facts.get(key) is True:
            used[key] = True
            return _answer(None, words + ": which code governs needs a person's check", [R101, cite], used)
    rooms = values.get("rooms_let_for_profit")
    if type(rooms) in (int, float) and rooms > 0:
        used["rooms_let_for_profit"] = rooms
        return _answer(None, f"{rooms:g} rooms let for profit: a lodging house is under the Residential Code only "
                       "owner-occupied with five or fewer guestrooms and a P2904 sprinkler system (R101.2 item 6), "
                       "else the Building Code (310.2, 310.4.2): which code governs needs a person's check",
                       [R101, "BCNYS 310.4.2"], used)
    if use == ATTACHED:
        units = values.get("attached_units_in_building")
        used["attached_units_in_building"] = units
        if type(units) is not int:
            return _answer(None, "an attached one-family dwelling: how many units the whole attached building has "
                           "isn't stated, so whether it is a townhouse (three or more townhouse units, R202) can't be "
                           "told", [R101], used)
        if units < 3:
            what, item, n = "a two-family dwelling (two attached units in one building)", "item 2", 2
        elif facts.get("townhouse_units") is None:
            return _answer(None, f"{units} attached units: a townhouse (R101.2 item 3) only if each is a townhouse "
                           "unit (R202: \"extends from foundation to roof, that has a yard or public way on not less "
                           "than two sides, and has a separate means of egress\"); say whether they are (Gordium: "
                           "Townhouse units)", [R101, "RCNYS R202 TOWNHOUSE UNIT"], used)
        elif facts["townhouse_units"] is False:
            return _answer(BUILDING, f"{units} attached units that are not townhouse units (R202), so not a "
                           "townhouse: none of R101.2's dwellings, so the Building Code covers it",
                           [R101, "RCNYS R202 TOWNHOUSE UNIT"], used)
        else:
            what, item, n = f"a townhouse of {units} townhouse units", "item 3", None
    else:
        what, item, n = HOUSES[use]
        units = values.get("dwelling_units")
        if type(units) in (int, float) and n == 1 and units != 1:
            used["dwelling_units"] = units
            return _answer(None, f"the use is a one-family dwelling but {units:g} dwelling units are stated: say "
                           "which is right", [R101], used)
        if values.get("accessory_dwelling_unit") is True and values.get("adu_detached") is not True and n == 1:
            if values.get("adu_detached") is None:
                return _answer(None, "an accessory dwelling unit is on the lot and whether it is detached isn't "
                               "stated: inside the house it makes it a two-family dwelling (R101.2 item 2, which needs "
                               "a separate means of egress for each unit)", [R101], used)
            what, item, n = "a two-family dwelling (the house and its attached accessory dwelling unit)", "item 2", 2
    cites = [f"{R101} {item}"]
    if n == 2:
        egress = facts.get("separate_means_of_egress")
        if egress is None:
            return _answer(None, f"{what}: the Residential Code covers it only where each dwelling unit has a separate "
                           "means of egress (R101.2 item 2), which isn't stated (Gordium: Separate means of egress)",
                           cites, used)
        if egress is False:
            return _answer(BUILDING, f"{what} whose units don't each have a separate means of egress: not one R101.2 "
                           "lists, so the Building Code covers it (Group R-3, 310.4)", cites + ["BCNYS 310.4"], used)
    most, where = stories_bound(values, facts)
    used["stories_above_grade_plane"] = most
    if most is None:
        return _answer(None, f"{what}, but how many stories it has above grade plane isn't known (R101.2: \"not more "
                       f"than three stories above grade plane\"): {ASK_STORIES}", cites + ["RCNYS R202"], used)
    if most > 3:
        if "stories_above_grade_plane" in facts:
            return _answer(BUILDING, f"{what} of {most} stories above grade plane (stated): more than R101.2's three, "
                           "so the Building Code covers it", cites + ["RCNYS R202"], used)
        return _answer(None, f"{what}; Ithaca counts {most} stories, and a habitable attic Ithaca counts may not be a "
                       "story above grade plane (R316.3's exceptions), so whether it is over R101.2's three can't be "
                       f"told: {ASK_STORIES}", cites + ["RCNYS R316.3"], used)
    return _answer(RESIDENTIAL, f"{what} of not more than three stories above grade plane ({where}): R101.2 {item}",
                   cites + ["RCNYS R202"], used)
