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

import functools
import math
from pathlib import Path

RESIDENTIAL = "residential_code"
BUILDING = "building_code"
CODES = (RESIDENTIAL, BUILDING)
STORIES_AT_MOST = "stories_at_most"       # the check's value: the greatest of Ithaca's stories readings (check.py)

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
    "assembly_fixed_seating": "yes_no",       # rooms used for assembly with fixed seating (Table 1006.2.1 note c);
                                              # also true where a room states assembly_fixed_seats (building_measures)
    "r2_sleeping_units": "yes_no",            # Group R-2 of sleeping units, not dwelling units (Table 1006.3.4(1) note b)
    "emergency_escape_openings_1031": "yes_no",   # emergency escape and rescue openings per 1031 (Table 1006.3.4 note a)
    "special_egress_spaces": "yes_no",        # a space with its own exits or travel limit (1006.2.2, Table 1017.2 note a)
    "merchandise_pads": "yes_no",             # Group M merchandise pads (1018.4: their own common path)
    "occupied_outdoor_areas": "yes_no",       # outdoor areas the occupants use (1004.7)
    "occupant_load_increased": "yes_no",      # the design takes 1004.5.1's increased occupant load (up to 1 per 7 sq ft)
    # the building has a mezzanine (505.2: an intermediate level within a story): its occupants add to the room below
    # (1004.2.2), so only where it states none is a story's floor area / 5 the most its spaces can hold (occupant_load)
    "mezzanines": "yes_no",
    # an area whose load Table 1004.5 counts by seats, lanes or actual load, not floor area (fixed seats in any use,
    # bowling lanes, concentrated business use, a mall)
    "loads_not_by_area": "yes_no",
    # section group 4 (corridors): another level's occupants reach a corridor (an unenclosed stairway or ramp, a
    # mezzanine, stairs converging or discharging into one: 1004.2.2, 1004.2.3, 1005.6), so the story's load doesn't
    # bound the corridor's; and the building is (or holds) an ambulatory care facility (Table 1020.3's 72 in)
    "other_level_egress_into_corridors": "yes_no",
    "ambulatory_care_facility": "yes_no",
    # section group 4b: the building has corridors within a dwelling or sleeping unit (1020.2 exception 2; Table
    # 1020.3's 36 in within a dwelling unit)
    "corridors_within_dwelling_units": "yes_no",
    # section group 5a: an emergency voice/alarm communication system per 907.5.2.2 (1005.3.1 and 1005.3.2's
    # exception 1: the smaller capacity factors, with a sprinkler system per 903.3.1.1 or 903.3.1.2)
    "emergency_voice_alarm_system": "yes_no",
    # section group 9h: a room or space used for assembly purposes, whatever the building's group (303.1.1 and 303.1.2
    # put small assembly rooms in Group B or the main occupancy, so the group alone doesn't settle it): Section 1030's
    # flags show where it is true or not stated. True also from a room's Table 1004.5 Assembly function
    # (assembly_spaces_from_rooms); false only as stated (a model may hold only some floors)
    "assembly_spaces": "yes_no",
    # the lot facts a host had but couldn't send (the Revit add-in's Check now anyway: a count under its least), so
    # the decision reads each as stated and unread, never as not stated (review round 5)
    "facts_not_sent": "names",
}
GROUPS = ("A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "H-1", "H-2", "H-3", "H-4", "H-5", "I-1",
          "I-2", "I-3", "I-4", "M", "R-1", "R-2", "R-3", "R-4", "S-1", "S-2", "U")
SPRINKLERS = ("none", "nfpa_13", "nfpa_13r", "nfpa_13d")
MIXED = "mixed"                     # occupancy_group's value for a building of two or more groups

RCNYS = "2025 Residential Code of New York State"
BCNYS = "2025 Building Code of New York State"
TITLES = {RESIDENTIAL: RCNYS, BUILDING: BCNYS}
# Each section the decision stands on: its book, the PDF page and the book's exact words (copies in the code cache:
# the RCNYS's sources.yaml entry, sha256 36490d8c..., and the BCNYS's, 729d2db7...; test_code_scope.py reads each
# quote again from the PDF where the cache has it)
CITES = {
    "R101.2": (RCNYS, 24, "provided that such building or structure is not more than three stories above grade plane "
               "in height with a separate means of egress"),
    "R101.2 item 1": (RCNYS, 24, "1. Detached one-family dwellings."),
    "R101.2 item 2": (RCNYS, 24, "2. Detached two-family dwellings in which each dwelling unit has a separate means "
                      "of egress."),
    "R101.2 item 3": (RCNYS, 24, "3. Townhouses."),
    "R101.2 item 4": (RCNYS, 24, "4. Bed and breakfast dwellings."),
    "R101.2 item 5": (RCNYS, 24, "5. Live/work units located in townhouses and complying with the requirements of "
                      "Section 508.5 of the Building Code of New York State."),
    "R101.2 item 6": (RCNYS, 24, "6. Owner-occupied lodging houses that have five or fewer guestrooms and are "
                      "provided with an automatic sprinkler system complying with Section P2904 of this code."),
    "R101.2 exception": (RCNYS, 24, "Application of the provisions of the Building Code of New York State to the "
                         "construction, alteration, movement, enlargement, replacement, repair, equipment, use and "
                         "occupancy, location, removal and demolition of the buildings and structures listed in Section "
                         "R101.2 is permitted, provided that all applicable provisions of the Building Code of New York "
                         "State are applied."),
    "R202 DWELLING": (RCNYS, 40, "Any building that contains one or two dwelling units"),
    "R202 STORY ABOVE GRADE PLANE": (RCNYS, 52, "Any story having its finished floor surface entirely above grade "
                                     "plane, or in which the finished surface of the floor next above is either of the "
                                     "following:"),
    "R202 TOWNHOUSE": (RCNYS, 53, "A building that contains three or more attached townhouse units."),
    "R202 TOWNHOUSE UNIT": (RCNYS, 53, "A single-family dwelling unit in a townhouse that extends from foundation to "
                            "roof, that has a yard or public way on not less than two sides, and has a separate means "
                            "of egress."),
    "R202 BED AND BREAKFAST DWELLING": (RCNYS, 36, "An owner-occupied residence resulting from a conversion of a "
                                        "one-family dwelling, used for providing overnight accommodations and a morning "
                                        "meal to not more than ten transient lodgers, and containing not more than five "
                                        "bedrooms for such lodgers."),
    "R316.3": (RCNYS, 98, "A habitable attic shall be considered a story above grade plane."),
    "101.2": (BCNYS, 22, "The provisions of this code shall apply to the construction, alteration, relocation, "
              "enlargement, replacement, repair, equipment, use and occupancy, location, maintenance, removal and "
              "demolition of every building or structure"),
    "101.2 exception 1": (BCNYS, 22, "Application of the provisions of the Residential Code of New York State to"),
    "202 LIVE/WORK UNIT": (BCNYS, 52, "A dwelling unit or sleeping unit in which a significant portion of the space "
                           "includes a nonresidential use that is operated by the tenant."),
    "308.2.4": (BCNYS, 78, "A facility with five or fewer persons receiving custodial care shall be classified as Group "
                "R-3 or shall comply with the Residential Code of New York State provided an automatic sprinkler "
                "system is installed"),
    "310.3": (BCNYS, 80, "Residential Group R-2 occupancies containing sleeping units or more than two dwelling units "
              "where the occupants are primarily permanent in nature"),
    "310.4": (BCNYS, 80, "Buildings that do not contain more than two dwelling units"),
    "310.4.1": (BCNYS, 80, "Care facilities for five or fewer persons receiving care that are within a single-family "
                "dwelling are permitted to comply with the Residential Code of New York State provided an automatic "
                "sprinkler system is installed"),
    "310.4.2": (BCNYS, 80, "Owner-occupied lodging houses with five or fewer guest rooms shall be constructed in "
                "accordance with this code or the Residential Code of New York State"),
}
# the marks the architect answers with on Project Information (apps/revit_addin: Marks.cs; every one is a mark there,
# test_code_scope.py), named in each `ask`; Rhino asks the same facts in its start box and rows
MARK = {"stories_above_grade_plane": "Gordium: Stories above grade plane", "stories": "Gordium: Stories",
        "separate_means_of_egress": "Gordium: Separate means of egress", "townhouse_units": "Gordium: Townhouse units",
        "follows_building_code": "Gordium: Follows the Building Code", "occupancy_groups": "Gordium: Occupancy groups",
        "use": "Gordium: Use", "attached_units_in_building": "Gordium: Units in the attached building",
        "dwelling_units": "Gordium: Dwelling units", "care_facility": "Gordium: Care facility",
        "home_occupation": "Gordium: Home occupation", "rooms_let_for_profit": "Gordium: Rooms let for profit",
        "accessory_dwelling_unit": "Gordium: Accessory dwelling unit", "adu_detached": "Gordium: ADU detached",
        "adus_on_parcel": "Gordium: ADUs on parcel", "sprinkler_system": "Gordium: Sprinkler system",
        # what the Building Code's Chapter 10 rules read of the whole building (Revit: each a Yes/No on Project Information)
        "assembly_fixed_seating": "Gordium: Fixed assembly seating", "special_egress_spaces": "Gordium: Special egress spaces",
        "merchandise_pads": "Gordium: Merchandise pads", "egress_balcony_increase_taken": "Gordium: Egress balcony increase",
        "building_has_atrium": "Gordium: Atrium",
        # group 2's: which Table 1006.3.4 a Group R-2 story reads, and its 1031 escape openings
        "r2_sleeping_units": "Gordium: R-2 sleeping units", "emergency_escape_openings_1031": "Gordium: 1031 escape openings",
        # group 3's: outdoor areas the occupants use (1004.7), and 1004.5.1's increased occupant load
        "occupied_outdoor_areas": "Gordium: Occupied outdoor areas", "occupant_load_increased": "Gordium: Occupant load increased",
        # groups 4 and 5's: corridors (1020) and egress capacity (1005.3)
        "other_level_egress_into_corridors": "Gordium: Other levels reach corridors",
        "ambulatory_care_facility": "Gordium: Ambulatory care facility",
        "corridors_within_dwelling_units": "Gordium: Corridors within dwelling units",
        "emergency_voice_alarm_system": "Gordium: Emergency voice/alarm system",
        # the occupant loads' ceiling (occupant_load._bounds): a mezzanine's occupants add to the room below
        "mezzanines": "Gordium: Mezzanines", "loads_not_by_area": "Gordium: Loads not by area"}
# Gordium's reading for a house where these aren't stated (strong common practice, shown as a reading to confirm:
# docs/decisions/2026-11-22_which_ny_code.md decision 2a): none, so the use's own dwelling decides. Each: the fact,
# what is assumed, and how the architect says otherwise
ASSUMED = (("care_facility", "no one outside the household receives care here"),
           ("home_occupation", "no home occupation"),
           ("rooms_let_for_profit", "no rooms let for profit"),
           ("accessory_dwelling_unit", "no accessory dwelling unit"),
           ("dwelling_units", "the use's own dwelling units on the lot"),
           ("adus_on_parcel", "one accessory dwelling unit on the parcel, the one stated"))
# the kinds of the lot facts the decision reads (a value of another kind is said, never used)
COUNTS = ("dwelling_units", "attached_units_in_building", "adus_on_parcel", "rooms_let_for_profit", "stories")
YES_NO = ("accessory_dwelling_unit", "adu_detached", "home_occupation")
# where check.py found Ithaca's stories count read from the drawing with nothing drawn below the ground
STORIES_DRAWN = "stories_from_drawing"
# how that count came: "read" (counted from Gordium's floor blocks or a drawing that allows one count) or "typed"
# (the architect's Gordium: Stories, kept because it lies within what the drawing allows), for the words only
STORIES_HOW = "stories_how"
# the stated facts the measuring set aside because they contradict each other ({name: why}: measure.py
# _set_aside_conflicts), from check.py: a fact the decision reads that is set aside needs review, never "unstated"
SET_ASIDE = "facts_set_aside"
# the facts of the lot the decision reads (its use, units, ADU, uses beyond the dwelling, stories)
READS = ("use", "dwelling_units", "attached_units_in_building", "accessory_dwelling_unit", "adu_detached",
         "adus_on_parcel", "home_occupation", "rooms_let_for_profit", "stories", "care_facility")

# Ithaca's use words (4_term_definitions/uses.yaml) that name a dwelling R101.2 lists: its words, R101.2's item, units
HOUSES = {"one_family_detached": ("a detached one-family dwelling", "R101.2 item 1", 1),
          "one_family_detached_zero_lot_line": ("a detached one-family dwelling", "R101.2 item 1", 1),
          "two_family": ("a detached two-family dwelling", "R101.2 item 2", 2),
          # one of two one-family dwellings joined by a common wall: R202 DWELLING counts the units of the building
          # ("Any building that contains one or two dwelling units"), lot lines aside, so the pair is a two-family one
          "one_family_semi_detached": ("a two-family dwelling (two semi-detached units in one building)",
                                       "R101.2 item 2", 2)}
ATTACHED = "one_family_attached"                  # three to six units in a row (§325-3B): a townhouse if R202's
BED_AND_BREAKFAST = "bed_and_breakfast_inn"       # under the Residential Code only as R202's B&B dwelling
ASK_BY_HAND = "check which code governs by hand, then tick {mark} Yes if it is the Building Code"


def by_use(use) -> str | None:
    """The book that covers a building of this use whatever else is stated (BUILDING: a use none of R101.2's
    dwellings can be, 101.2 "every other building"), or None where the use alone can't tell (a dwelling R101.2 lists,
    or a bed and breakfast, which the decision reads further). decide's own test: a host's Setup form uses it (through
    the options answer, check.options) to ask for the facts the Building Code turns on before the first check."""
    return None if use in HOUSES or use in (ATTACHED, BED_AND_BREAKFAST) else BUILDING


@functools.lru_cache(maxsize=16)
def use_names(place=None) -> dict:
    """{use: its name} from a place's 4_term_definitions/uses.yaml, the place's own words ("Retail store or service
    commercial facility"); with no place, every place's, the first place listing a use naming it (places in their
    stable order), for a direct caller that names none."""
    from rule_format.place import places
    from rule_format.rulebook import load
    out = {}
    for folder in ([place] if place is not None else [p.folder for p in places()]):
        f = Path(folder) / "4_term_definitions/uses.yaml"
        if f.exists():
            for k, v in (load(f) or {}).items():
                if isinstance(v, dict):
                    out.setdefault(k, v.get("name") or k)
    return out


def use_words(use, names: dict | None = None) -> str:
    """A use in the place's own words (`names`: use_names of the place checked), never its key; one it doesn't
    name, quoted exactly as typed."""
    named = (use_names() if names is None else names).get(use) if isinstance(use, str) else None
    return named or value_words(use)


# the use as the architect chose it, for a line saying the facts disagree with it (the verdict lines name R101.2's
# dwelling instead, the law's term): its words and a note to go in the line's brackets
CHOSEN = {"one_family_detached": ("a one-family detached dwelling", ""),
          "one_family_detached_zero_lot_line": ("a one-family detached dwelling on a zero lot line", ""),
          "two_family": ("a two-family dwelling", ""),
          "one_family_semi_detached": ("a one-family semi-detached dwelling", "one of a pair"),
          ATTACHED: ("a one-family attached dwelling", "")}


def chosen_use_words(use: str, count: str, names: dict | None = None) -> str:
    """The use as the architect chose it, with what the line counts in its brackets: "a one-family semi-detached
    dwelling (one of a pair, 2 dwelling units in the building)"."""
    name, note = CHOSEN.get(use) or (use_words(use, names), "")
    return f"{name} ({note + ', ' if note else ''}{count})"


def fact_words(key: str) -> str:
    """A fact by the mark the architect answers it with (MARK), else in words: never its key."""
    return MARK.get(key) or str(key).replace("_", " ")


def value_words(v) -> str:
    """A value the architect stated that Gordium can't read, quoted exactly as stated (“R_3”, “three”: the
    architect's own characters, the one that made it unreadable included); a blank one "blank", a yes/no "Yes" or
    "No"; a list or a set of facts by its parts."""
    if v is None:
        return "blank"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, str):
        return f"“{v}”"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(value_words(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{fact_words(k)}: {value_words(x)}" for k, x in v.items()) + "}"
    if isinstance(v, int):
        return str(v)                         # every digit, as typed: -1234567, never -1.23457e+06
    if isinstance(v, float):
        if math.isnan(v):
            return "not a number"
        if math.isinf(v):
            return "infinity" if v > 0 else "minus infinity"
        return repr(v)                        # 2.0000001 and 2.0 as typed, never rounded to "2"
    return f"“{v}”"


def _given(building) -> tuple[dict, list[str]]:
    """The `building` block's facts of the right kind, and what is wrong with the rest, each said and never used: a
    block that isn't a mapping, a key that isn't one of FACTS (a misspelled fact is never read as "not stated"), a
    value of the wrong kind."""
    if building is None:
        return {}, []
    if not isinstance(building, dict):
        return {}, [f"the building block is {type(building).__name__}, not a mapping of facts, so none is read"]
    out, bad = {}, []
    for k, v in building.items():
        kind = FACTS.get(k)
        ok = (kind == "count" and type(v) is int and v >= 1) or (kind == "yes_no" and type(v) is bool) or \
             (kind == "groups" and isinstance(v, list) and v and all(g in GROUPS for g in v)) or \
             (kind == "sprinkler" and v in SPRINKLERS) or \
             (kind == "names" and isinstance(v, list) and all(isinstance(x, str) for x in v))
        if kind is None:
            bad.append(f"the building block sends {value_words(k)}, which is no fact Gordium reads (it reads "
                       f"{', '.join(fact_words(f) for f in FACTS if f != 'facts_not_sent')})")   # each, marked or not
        elif ok:
            out[k] = v
        else:
            # named by the mark the architect corrects it on (review round 1: "the building's building has atrium is
            # 2"), else in words
            name = MARK.get(k) or f"the building's {k.replace('_', ' ')}"
            bad.append(f"{name} is {value_words(v)}, which Gordium can't read")
    return out, bad


def building_measures(building: dict | None, interior=None) -> dict:
    """The BCNYS rulebook's building measures (its drafted/records/proposed_measures.yaml) the `building` block
    states: occupancy_group_i4, other_occupancy_present and occupancy_group (the one group, or "mixed") from the
    groups, the three sprinkler systems the limits name from the system, and the twelve stated yes/no facts. A fact
    not stated is left out (its rules need review). `interior`, the interior description, settles one more:
    assembly_spaces is true wherever a room states a Table 1004.5 Assembly function, whatever the block says, and a
    stated false is left out (not stated) where a room states a function that may be an assembly use
    (assembly_spaces_from_rooms); and assembly_fixed_seating is true wherever a room states Table 1004.5's "Assembly
    with fixed seats" (review round 1 of section group 9h)."""
    facts, _ = _given(building)
    out = {m: worked(facts[fact]) for m, (fact, worked) in DERIVED.items() if fact in facts}
    seen = assembly_spaces_from_rooms(interior)
    if FIXED_SEATS in room_functions(interior):     # the rooms show fixed seating: never a stated no over them
        out["assembly_fixed_seating"] = True
    if seen == ASSEMBLY_YES:
        out["assembly_spaces"] = True
    elif seen == ASSEMBLY_MAYBE and out.get("assembly_spaces") is False:
        del out["assembly_spaces"]
    return out


# Table 1004.5's rows under its "Assembly" heading (p.312, lines 19-27, to "Business areas" on line 28), by their
# function ids (docs/interior/interior_description_format.md, rooms[].function): a room stating one is used for
# assembly purposes (1030.1), whatever the building's group, so the building has assembly spaces. The one list:
# occupant_load's assembly seating (1030.7) imports this and ASSEMBLY_LIKE_FUNCTIONS
ASSEMBLY_FUNCTIONS = ("gaming_floor", "exhibit_gallery_museum", "assembly_fixed_seats", "assembly_concentrated",
                      "assembly_standing", "assembly_unconcentrated", "bowling_center")
# the table's other rows a room used for assembly purposes may state (Table 1004.5's courtrooms, library reading rooms,
# exercise rooms, rinks, pools and their decks, stages and platforms, airport waiting areas): 303.1 counts "awaiting
# transportation" as assembly (p.68, lines 36-38), 303.4 lists courtrooms, gymnasiums, indoor swimming pools,
# libraries and waiting areas in transportation terminals in Group A-3 (p.69, lines 13-32), 303.5 skating rinks and
# swimming pools with spectator seating in Group A-4 (p.69, lines 33-38), and 303.2's theaters have their stages
# (p.68, line 51). Each may be an assembly use or not, so it is never a yes, and never lets a stated no stand
ASSEMBLY_LIKE_FUNCTIONS = ("courtroom", "library_reading_room", "exercise_room", "rink_pool", "pool_deck",
                           "stage_platform", "airport_waiting")
ASSEMBLY_YES, ASSEMBLY_MAYBE = "yes", "maybe"


def room_functions(interior) -> set:
    """The Table 1004.5 functions the description's rooms state (a function of another kind is occupant_load's to
    say, unread here)."""
    rooms = interior.get("rooms") if isinstance(interior, dict) else None
    if not isinstance(rooms, list):
        return set()
    return {r["function"] for r in rooms if isinstance(r, dict) and isinstance(r.get("function"), str)}


# Table 1004.5's "Assembly with fixed seats" (p.312, line 22): a room stating it has fixed seating (Table 1006.2.1 note
# c, 1030.7, 1030.8), whatever the building block says (review round 1 of section group 9h)
FIXED_SEATS = "assembly_fixed_seats"


def assembly_spaces_from_rooms(interior) -> str | None:
    """What the rooms' stated functions say of assembly_spaces: ASSEMBLY_YES where a room states one of
    ASSEMBLY_FUNCTIONS, else ASSEMBLY_MAYBE where one states one of ASSEMBLY_LIKE_FUNCTIONS, else None. Never a no:
    a description may hold only some of the building's floors (review round 6 of section group 6b), so rooms with no
    assembly function don't rule one out; only the architect's stated `assembly_spaces: false` does."""
    functions = room_functions(interior)
    if functions & set(ASSEMBLY_FUNCTIONS):
        return ASSEMBLY_YES
    if functions & set(ASSEMBLY_LIKE_FUNCTIONS):
        return ASSEMBLY_MAYBE
    return None


# Each building measure the BCNYS rulebook reads: the `building` fact it is worked out from, and how
# (building_measures). The one table, so a cause that lacks a measure names the fact, and the host's field, that
# answers it (field_of: occupancy_group_i4 is answered by building.occupancy_groups, never a field of its own)
DERIVED = {
    "occupancy_group_i4": ("occupancy_groups", lambda groups: "I-4" in groups),
    "other_occupancy_present": ("occupancy_groups", lambda groups: any(g != "I-4" for g in groups)),
    # the building's one group, or MIXED for two or more: the table-row rules read it (docs/decisions/
    # 2026-11-23_ny_building_egress_all_occupancies.md decisions 1 and 3)
    "occupancy_group": ("occupancy_groups", lambda groups: next(iter(set(groups))) if len(set(groups)) == 1 else MIXED),
    "sprinklered_903_3_1_1": ("sprinkler_system", lambda system: system == "nfpa_13"),
    "sprinklered_903_3_1_2": ("sprinkler_system", lambda system: system == "nfpa_13r"),
    "sprinklered_903_3_1_3": ("sprinkler_system", lambda system: system == "nfpa_13d"),
    "egress_balcony_increase_taken": ("egress_balcony_increase_taken", lambda v: v),
    "building_has_atrium": ("building_has_atrium", lambda v: v),
    "assembly_fixed_seating": ("assembly_fixed_seating", lambda v: v),
    "special_egress_spaces": ("special_egress_spaces", lambda v: v),
    "merchandise_pads": ("merchandise_pads", lambda v: v),
    "r2_sleeping_units": ("r2_sleeping_units", lambda v: v),
    "emergency_escape_openings_1031": ("emergency_escape_openings_1031", lambda v: v),
    "occupied_outdoor_areas": ("occupied_outdoor_areas", lambda v: v),
    "ambulatory_care_facility": ("ambulatory_care_facility", lambda v: v),
    "corridors_within_dwelling_units": ("corridors_within_dwelling_units", lambda v: v),
    "emergency_voice_alarm_system": ("emergency_voice_alarm_system", lambda v: v),
    "assembly_spaces": ("assembly_spaces", lambda v: v),
}


def field_of(measure: str) -> str | None:
    """The description's field that answers a building measure ("building.occupancy_groups" for
    occupancy_group_i4: Revit's Gordium: Occupancy groups feeds it), or None for a measure no building fact gives."""
    return f"building.{DERIVED[measure][0]}" if measure in DERIVED else None


BY_HAND = ASK_BY_HAND.format(mark=MARK["follows_building_code"])


def asked_facts(ask: str | None) -> list[str]:
    """The facts an ask names, by their marks (MARK: Gordium's own words for each), in the order it names them: the
    one place they are worked out, from the very words the architect is shown, so the two never drift. Longest mark
    first, each place in the words read once (no mark is read inside another)."""
    if not ask:
        return []
    found, taken = [], [False] * len(ask)
    for key, mark in sorted(MARK.items(), key=lambda km: -len(km[1])):
        start = 0
        while (at := ask.find(mark, start)) >= 0:
            if not any(taken[at:at + len(mark)]):
                taken[at:at + len(mark)] = [True] * len(mark)
                found.append((at, key))
            start = at + len(mark)
    return list(dict.fromkeys(k for _, k in sorted(found)))


def _marks(keys) -> str:
    """Facts by their marks, "A, B and C" (a fact with no mark by its words)."""
    said = [fact_words(k) for k in dict.fromkeys(keys)]
    return said[0] if len(said) == 1 else ", ".join(said[:-1]) + " and " + said[-1]


def _answer(code, why, cites, used, ask=None, assumes=()):
    """The decision: `code` (None: needs review), `title` (the book's name, None when undecided), `why` in plain
    words, `cites` ({section, document, page, quote} each: the book's own words), `ask` (what the architect states
    to settle it, only when undecided), `assumes` (Gordium's reading of what wasn't stated, each a reading to
    confirm: shown with the decision, never hidden), `facts` (what it was decided from)."""
    return {"code": code, "title": TITLES.get(code), "why": why,
            "cites": [{"section": ("RCNYS " if CITES[k][0] == RCNYS else "BCNYS ") + k, "document": CITES[k][0],
                       "page": CITES[k][1], "quote": CITES[k][2]} for k in dict.fromkeys(cites)],
            "ask": ask if code is None else None, "assumes": list(assumes), "facts": used,
            # the facts `ask` asks the architect to state or correct, as data (a host's mark answers each one)
            # (a choice to check by hand asks for no fact: a person decides which code governs)
            "ask_facts": asked_facts(ask) if code is None and ask != BY_HAND else []}


def stories_bound(values: dict, facts: dict) -> tuple[int | None, str]:
    """The most stories above grade plane the building can have (RCNYS R202), and where that comes from.

    The architect's count where stated. Else Ithaca's own count (`stories`), only where check.py found it read from
    the drawing (STORIES_DRAWN: a count over drawn parts, no geometry error; never a typed count kept because nothing
    countable is drawn), which can only be as many or more: read from the drawing, it comes only when nothing drawn
    is below the ground (a part below it is the basement question, and the count needs review:
    places/ithaca_city/measure.py _stories_whole), so no basement or cellar R202 could count and Ithaca doesn't
    (R202 item 3, 6 ft for more than half the perimeter, is the State's alone); and what Ithaca
    leaves out the State does too: a mezzanine (both: "an intermediate level ... between the floor and ceiling of any
    story", R202 MEZZANINE), an attic "unfinished and without human occupancy" (R202 ATTIC is the space between the
    ceiling assembly and the roof assembly, inside the top STORY, which runs to "the floor or roof next above"; only
    a habitable attic is a story above grade plane, R316.3, and Ithaca counts that one, having human occupancy)."""
    if "stories_above_grade_plane" in facts:
        return facts["stories_above_grade_plane"], "stated by the architect"
    if values.get(STORIES_DRAWN) is not True:       # a typed count alone, or no drawing to read: Ithaca's count
        return None, "not known"                    # misses R202's item 3 (a walk-out basement), so it can't stand in
    s = values.get("stories")
    # where Ithaca's count is an open question, the most the drawing allows (its readings' greatest: STORIES_AT_MOST,
    # given by check.py) bounds it the same way
    if s is None and type(values.get(STORIES_AT_MOST)) in (int, float) and values[STORIES_AT_MOST] >= 1:
        return int(math.ceil(values[STORIES_AT_MOST])), ("the most Ithaca's count could be as drawn, nothing drawn "
                                                         "below the ground, so at most that many above grade plane")
    if type(s) in (int, float) and s >= 1 and float(s).is_integer():
        if values.get(STORIES_HOW) == "typed":
            return int(s), ("Ithaca's count as the architect states it, checked against the drawing: nothing drawn "
                            f"below the ground, so at most {int(s)} above grade plane")
        return int(s), ("Ithaca's count read from the drawn floors, nothing drawn below the ground, so at most "
                        f"{int(s)} above grade plane")
    return None, "not known"


def decide(values: dict, building: dict | None, uses=None, place=None) -> dict:
    """Which book governs the building's egress (module docstring), with why and the sections behind it. `uses`: the
    place's listed uses (its allowed values), as they are: an empty one is a place that lists none, where every use
    needs review; None (a direct caller giving no list) is every place's (use_names). A use not among them is one
    Gordium can't place (a typo, a use it doesn't know): needs review, never a code (principle 4). `place`: the
    checked place's folder, whose own names (uses.yaml) say each use."""
    names = use_names(place)
    values = values or {}
    # the building block's facts, and any the check's values carry (a host with no interior description may state
    # them as facts); the building block's own stand where both give one
    given = {k: values[k] for k in FACTS if k in values}
    block = {**given, **building} if isinstance(building, dict) else given if building is None else building
    facts, bad = _given(block)
    used = dict(facts)
    by_hand = BY_HAND
    if bad:
        # every fact of the block that couldn't be read, whether the building block or the check's values sent it
        bad_keys = [k for k in block if k in FACTS and k not in facts] if isinstance(block, dict) else []
        return _answer(None, "; ".join(bad), ["R101.2"], used,
                       f"correct {_marks(bad_keys)} on Project Information" if bad_keys else
                       "correct it on Project Information")
    if facts.get("follows_building_code") is True:
        return _answer(BUILDING, "the architect applies the Building Code to it, as R101.2's exception permits",
                       ["R101.2 exception"], used)
    # a fact the decision reads that the measuring set aside (stated, but contradicting another): never read as
    # unstated, so never the use's own count or an assumed "none" in its place
    aside = dict(values.get(SET_ASIDE)) if isinstance(values.get(SET_ASIDE), dict) else {}
    for k in facts.get("facts_not_sent") or []:         # stated but not sent (a count under its least): unread
        aside.setdefault(k, "stated, but not sent: Gordium can't read what it holds")
    conflicted = [k for k in READS if k in aside]
    if conflicted:
        return _answer(None, "facts this reads are stated but set aside or not sent, so they can't be used ("
                       + "; ".join(f"{k.replace('_', ' ')}: {aside[k]}" for k in conflicted) + ")",
                       ["R202 DWELLING", "R101.2"], used,
                       f"correct the facts that disagree or can't be read ({_marks(conflicted)})")
    # a lot fact of the wrong kind (text for a count, a count under 0): said, never used or read as not stated
    wrong = [k for k in COUNTS if values.get(k) is not None and (type(values[k]) not in (int, float) or values[k] < 0)]
    wrong += [k for k in YES_NO if values.get(k) is not None and type(values[k]) is not bool]
    if wrong:
        return _answer(None, "; ".join(f"the {k.replace('_', ' ')} is {value_words(values[k])}, which Gordium can't "
                                       "read"
                                       for k in wrong), ["R101.2"], used, f"correct {_marks(wrong)}")
    use = values.get("use")
    used["use"] = use
    if not isinstance(use, str) or not use:
        return _answer(None, "the building's use isn't stated", ["R101.2", "101.2 exception 1"], used,
                       f"state the building's use ({MARK['use']})")
    if use not in (set(uses) if uses is not None else names):
        return _answer(None, f"the use {value_words(use)} isn't one Gordium knows: correct {MARK['use']}",
                       ["R101.2"], used, f"correct the use ({MARK['use']})")
    groups = facts.get("occupancy_groups") or []
    if any(g != "R-3" for g in groups):
        if use in HOUSES or use == ATTACHED:
            return _answer(None, f"the use is a dwelling the Residential Code can cover, but the occupancy groups "
                           f"stated ({', '.join(groups)}) are the Building Code's", ["R101.2", "101.2"], used,
                           f"correct the use ({MARK['use']}) or the occupancy groups ({MARK['occupancy_groups']})")
        return _answer(BUILDING, f"a building of Group {', '.join(groups)}, none of the dwellings R101.2 lists (101.2)",
                       ["R101.2", "101.2"], used)
    if use == BED_AND_BREAKFAST:
        return _answer(None, "a bed and breakfast is under the Residential Code only as an R202 bed and breakfast "
                       "dwelling (an owner-occupied conversion of a one-family dwelling, not more than ten transient "
                       "lodgers and five bedrooms for them)", ["R101.2 item 4", "R202 BED AND BREAKFAST DWELLING"],
                       used, by_hand)
    if by_use(use) == BUILDING:
        return _answer(BUILDING, f"its use ({use_words(use, names)}) is none of the dwellings R101.2 lists (101.2: every "
                       "other building)", ["R101.2", "101.2"], used)
    # a dwelling R101.2 can cover: each condition it sets, and how many dwelling units the building holds
    if values.get("care_facility") is True or facts.get("care_facility") is True:
        used["care_facility"] = True
        return _answer(None, "people outside the household receive care here: five or fewer may stay under the "
                       "Residential Code only as 308.2.4 or 310.4.1 allow (with a sprinkler system), more are a "
                       "Building Code occupancy", ["308.2.4", "310.4.1"], used, by_hand)
    if values.get("home_occupation") is True:
        used["home_occupation"] = True
        return _answer(None, "a home occupation is planned: a unit whose significant part is a business run by the "
                       "tenant is a live/work unit, under the Residential Code only in a townhouse (R101.2 item 5)",
                       ["R101.2 item 5", "202 LIVE/WORK UNIT"], used, by_hand)
    rooms = values.get("rooms_let_for_profit")
    if type(rooms) in (int, float) and rooms > 0:
        used["rooms_let_for_profit"] = rooms
        return _answer(None, f"{value_words(rooms)} rooms let for profit: a lodging house is under the Residential Code only "
                       "owner-occupied with five or fewer guestrooms and a P2904 sprinkler system (R101.2 item 6)",
                       ["R101.2 item 6", "310.4.2"], used, by_hand)
    # an accessory dwelling unit on the lot: in or on the building it is one more of the building's dwelling units.
    # Its facts agree or the decision needs review: a kind or a count said without the ADU (or with "none") is never
    # read as no ADU (review rounds 2 and 5); a count of none says none
    adu, detached, many = (values.get("accessory_dwelling_unit"), values.get("adu_detached"),
                           values.get("adus_on_parcel"))
    if adu is None and many == 0 and detached is None:
        adu = False                                    # "0 ADUs on the parcel": none, stated
    if adu is not True and (detached is not None or (many is not None and many > 0)):
        said = " and ".join(x for x in ("whether it is detached" if detached is not None else "",
                                        f"{value_words(many)} on the parcel" if many is not None and many > 0 else "") if x)
        return _answer(None, f"the accessory dwelling unit's facts ({said}) are stated, but "
                       + ("not that there is one" if adu is None else "so is that there is none") +
                       ": in or on the building it would be one more of its dwelling units (R202 DWELLING: one or two)",
                       ["R202 DWELLING", "R101.2 item 2"], used,
                       f"say whether an accessory dwelling unit is on the lot ({MARK['accessory_dwelling_unit']})")
    if adu is True and many is not None and many < 1:
        return _answer(None, "an accessory dwelling unit is stated, and so is that none is on the parcel",
                       ["R202 DWELLING"], used, f"correct the ADU facts ({MARK['accessory_dwelling_unit']}, "
                                                f"{MARK['adus_on_parcel']})")
    if adu is True and detached is None:
        return _answer(None, "an accessory dwelling unit is on the lot and whether it is detached isn't stated: in or "
                       "on the building it is one more of its dwelling units (R202 DWELLING: one or two)",
                       ["R202 DWELLING", "R101.2 item 2"], used,
                       f"say whether the accessory dwelling unit is detached ({MARK['adu_detached']})")
    # more than one ADU on the parcel: ADU detached describes one, and any other may be in or on the building, one
    # more of its units each (review round 4): needs review
    if adu is True and many is not None and many > 1:
        used["adus_on_parcel"] = many
        return _answer(None, f"{value_words(many)} accessory dwelling units are on the parcel, and whether each is detached isn't "
                       "known (ADU detached describes one): each in or on the building is one more of its dwelling "
                       "units, and more than two in one building is Group R-2 (R202 DWELLING, 310.3)",
                       ["R202 DWELLING", "310.3"], used,
                       f"say how many accessory dwelling units are on the parcel ({MARK['adus_on_parcel']}) and whether "
                       "each is detached (or correct the count: Ithaca allows one per parcel, §325-28C(1))")
    attached_adu = adu is True and values.get("adu_detached") is False
    used["attached_adu"] = attached_adu
    if use == ATTACHED:
        units = values.get("attached_units_in_building")
        used["attached_units_in_building"] = units
        if type(units) is not int:
            return _answer(None, "an attached one-family dwelling, the units of the whole attached building not stated",
                           ["R101.2 item 3", "R202 TOWNHOUSE"], used,
                           f"state the units in the whole attached building ({MARK['attached_units_in_building']})")
        if units < 2:
            return _answer(None, f"an attached one-family dwelling, but {units} unit in the whole attached building is "
                           "stated", ["R101.2 item 3", "R202 TOWNHOUSE"], used,
                           f"correct the use ({MARK['use']}) or the units ({MARK['attached_units_in_building']})")
        lot_units, building_units = 1, units + (1 if attached_adu else 0)
    else:
        what, item, n = HOUSES[use]
        lot_units = 2 if use == "two_family" else 1
        building_units = n + (1 if attached_adu else 0)
        # the units of the whole building stated beside a house's use: they must be the use's own (review round 6:
        # a count read only for an attached use was ignored for the others)
        stated_building = values.get("attached_units_in_building")
        if stated_building is not None and stated_building != n:
            used["attached_units_in_building"] = stated_building
            return _answer(None, "the use is " + chosen_use_words(use, f"{n} dwelling unit{'s' if n > 1 else ''} "
                                                                  "in the building", names) + " but "
                           f"{value_words(stated_building)} units in the whole attached building are stated",
                           ["R202 DWELLING", "R101.2"], used,
                           f"correct the use ({MARK['use']}) or the units ({MARK['attached_units_in_building']})")
    # the dwelling units stated for the lot agree with the use, whatever the use word: Ithaca's dwelling_units leaves
    # an ADU out (its own fact, as the occupant counts read it: measure.py fact_conflicts; the mark's tooltip says so),
    # so only the use's own count agrees; one more beside a stated ADU may or may not count it in: needs review
    stated = values.get("dwelling_units")
    if type(stated) in (int, float) and stated != lot_units:
        used["dwelling_units"] = stated
        return _answer(None, "the use is " + chosen_use_words(use, f"{lot_units} dwelling unit"
                                                              f"{'s' if lot_units > 1 else ''} on the lot", names) + " "
                       f"but {value_words(stated)} dwelling units are stated" + (
                           ", which may or may not count the accessory dwelling unit in (Gordium: Dwelling units leaves "
                           "it out)" if adu is True and stated == lot_units + 1 else ""),
                       ["R202 DWELLING", "R101.2"], used,
                       f"correct the use ({MARK['use']}) or the dwelling units ({MARK['dwelling_units']}, an accessory "
                       "dwelling unit not counted)")
    used["building_units"] = building_units
    if use == ATTACHED and units >= 3:
        if attached_adu:
            return _answer(None, f"{units} attached units, one with an accessory dwelling unit: a townhouse unit is "
                           "\"a single-family dwelling unit\" (R202), and whether one holding an accessory dwelling unit "
                           "is one is a person's check", ["R101.2 item 3", "R202 TOWNHOUSE UNIT"], used, by_hand)
        if facts.get("townhouse_units") is None:
            return _answer(None, f"{units} attached units: a townhouse only if each is a townhouse unit (R202: from "
                           "foundation to roof, a yard or public way on two sides, a separate means of egress)",
                           ["R101.2 item 3", "R202 TOWNHOUSE UNIT"], used,
                           f"say whether every unit is a townhouse unit ({MARK['townhouse_units']})")
        if facts["townhouse_units"] is False:
            return _answer(BUILDING, f"{units} attached units that are not townhouse units (R202), so none of the "
                           "dwellings R101.2 lists", ["R101.2 item 3", "R202 TOWNHOUSE UNIT", "101.2"], used)
        what, item, n = f"a townhouse of {units} townhouse units", "R101.2 item 3", None
    elif building_units >= 3:
        return _answer(BUILDING, f"{building_units} dwelling units in one building"
                       f"{' (an accessory dwelling unit among them)' if attached_adu else ''}: more than the one or two "
                       "of a dwelling (R202) and not a townhouse, so a Group R-2 building (310.3)",
                       ["R202 DWELLING", "310.3"], used)
    elif building_units == 2:
        what, item, n = ("a two-family dwelling" + (" (the house and its attached accessory dwelling unit)" if
                                                    attached_adu and use != "two_family" else
                                                    " (two attached units in one building)" if use == ATTACHED else
                                                    "" if use == "two_family" else
                                                    " (two semi-detached units in one building)"),
                         "R101.2 item 2", 2)
    # R101.2 covers its dwellings only "with a separate means of egress", and R202 TOWNHOUSE UNIT "has a separate means
    # of egress" (review round 7: it was read for two units only): said No, never the Residential Code
    egress = facts.get("separate_means_of_egress")
    if egress is False and n != 2:
        return _answer(None, f"{what}, but its means of egress is stated not to be separate: R101.2 covers its "
                       "dwellings only \"with a separate means of egress\""
                       + (", and a townhouse unit \"has a separate means of egress\" (R202)" if n is None else ""),
                       [item, "R101.2"] + (["R202 TOWNHOUSE UNIT"] if n is None else []), used,
                       f"correct {MARK['separate_means_of_egress']}" + (f" or {MARK['townhouse_units']}" if n is None
                                                                       else ""))
    # townhouse units said of a building that isn't three or more attached units: no townhouse (R202 TOWNHOUSE)
    if facts.get("townhouse_units") is True and n is not None:
        return _answer(None, f"{what}, but its units are stated to be townhouse units: a townhouse is \"a building that "
                       "contains three or more attached townhouse units\" (R202)", [item, "R202 TOWNHOUSE"], used,
                       f"correct the use ({MARK['use']}) or {MARK['townhouse_units']}")
    # Gordium's reading of what wasn't stated (decision 2a), each said as a reading to confirm: none of the uses
    # beyond the dwelling, no ADU, the use's own dwelling units, and beside a stated ADU only that one
    unstated = lambda k: values.get(k) is None and facts.get(k) is None
    assumed = [k for k in ("care_facility", "home_occupation", "rooms_let_for_profit") if unstated(k)]
    assumed += ["accessory_dwelling_unit"] if adu is None else []
    assumed += ["dwelling_units"] if unstated("dwelling_units") else []
    assumed += ["adus_on_parcel"] if adu is True and many is None else []
    used["assumed"] = assumed
    words_of = dict(ASSUMED)
    assumes = [words_of[k] for k in assumed]
    cites = [item]
    if n == 2:
        egress = facts.get("separate_means_of_egress")
        if egress is None:
            return _answer(None, f"{what}: the Residential Code covers it only where each unit has a separate means of "
                           f"egress ({item})", cites, used,
                           f"say whether each unit has a separate means of egress ({MARK['separate_means_of_egress']})")
        if egress is False:
            return _answer(BUILDING, f"{what} whose units don't each have a separate means of egress ({item}): a "
                           "Group R-3 building (310.4)", cites + ["310.4"], used)
    most, where = stories_bound(values, facts)
    used["stories_above_grade_plane"] = most
    ask = (f"state the building's stories above grade plane ({MARK['stories_above_grade_plane']}, as R202 STORY "
           "ABOVE GRADE PLANE counts them)")
    if most is None:
        return _answer(None, f"{what}, its stories above grade plane not known (R101.2: not more than three)",
                       cites + ["R101.2", "R202 STORY ABOVE GRADE PLANE"], used, ask)
    if most > 3:
        if "stories_above_grade_plane" in facts:
            return _answer(BUILDING, f"{what} of {most} stories above grade plane, more than R101.2's three",
                           cites + ["R101.2", "101.2"], used)
        return _answer(None, f"{what}: Ithaca's count could be {most} stories, and a habitable attic Ithaca counts may not be a "
                       "story above grade plane (R316.3's exceptions)", cites + ["R101.2", "R316.3"], used, ask)
    said = (f"; Gordium assumes {_joined(assumes)} (not stated): if any is so, say it "
            f"({', '.join(MARK[k] for k in assumed)})" if assumes else "")
    return _answer(RESIDENTIAL, f"{what}, {most} stories above grade plane at most ({where}) ({item}){said}",
                   cites + ["R101.2", "R202 STORY ABOVE GRADE PLANE"], used, assumes=assumes)


def _joined(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]
