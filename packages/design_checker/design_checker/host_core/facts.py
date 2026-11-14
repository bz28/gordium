"""The facts about a site the architect states (use, stories, corner lot, ground...): which are needed,
what each answer means, where each came from, and the use questions and row dialog that ask for them.

Moved here unchanged from rhino_logic.py, which still offers every name (so the Rhino plugin is
unchanged). Python 3.9 and the standard library only: Rhino 8 imports this into its own Python 3.9,
where none of the .venv's packages are installed."""

import math
import re
from .streets import STREET_LABEL, _street_lines, pick_street, street_name, street_run

__all__ = ['REQUIRED', 'missing', 'with_suggestions', 'STATED_FACTS', 'MINIMUM', 'OPTIONAL', 'minimum', 'STORIES_ASKED',
    'stories_needed', 'refused_stories', 'INTERIOR_FACTS', 'DRAWN_FACTS', 'DEFERRED_FACTS', 'CHECKED_TOGETHER',
    'USE_DETAILS_TITLE', 'USE_DETAILS_WHEN', 'ROW_ONLY_FACTS', 'BOX_ASKS', 'is_use_detail', 'IMPLIED_BY_USE',
    'IMPLIED_SOURCE', 'implied_facts', 'ASKED_AFTER', 'follow_up_keys', 'gate_of', 'ABOUT_LABELS', 'ABOUT_WORDS',
    'ABOUT_COUNTS', 'QUICK_ANSWERS', 'ABOUT_LABEL_WIDTH', 'ABOUT_FIELD_WIDTH', 'ABOUT_TYPED_WIDTH', 'ABOUT_QUICK_WIDTH',
    'ABOUT_NOTE_WIDTH', 'QUICK_HINT', 'about_label', 'choices_for', 'quick_answers', 'follow_up_rows', 'YES_NO_WORDS',
    'NOT_ANSWERED', 'FOLLOW_UP_HELP', 'yes_no_words', '_listed', 'use_note', 'district_use_names', 'box_needs_refresh',
    'answers_applied', 'box_track', 'box_applied', 'typed_sources', 'implied_by', 'parse_answer', 'answer_problem',
    'QUESTION_WIDTH', 'ANSWER_WIDTH', 'TEXT_PX', 'text_wider', 'answers_note', 'needs_of', '_and', 'enter_words',
    'answer_words', 'BUTTON_WORDS', 'needs_reason', 'SITE_HINT', 'SITE_ASKS', 'row_fields', 'row_choice',
    'row_choice_text', 'row_answers_applied', 'row_problem', 'row_sources', 'site_row', 'row_buttons', 'box_answers',
    'update_counts', 'to_feet', 'set_street_lines', 'drop_stale', 'after_lot_pick', 'lot_ground_dropped',
    'street_enter_keeps', 'corner_answered', 'suggested_facts', 'suggested_ground', 'unsettled', 'checkable', 'settle',
    'UNDER_A_BOX', 'allowed', 'pick_effect', 'after_ground_pick', 'parse_feet', 'starting_house_fact', 'CORNER_HINT',
    'uncertain', 'LOOKUP_INFO', 'lookup_note', '_question', 'FLAT_GROUND', 'GROUND_POINTS', 'ASSUMED_FLAT',
    'ASSUMED_SOURCE', 'ground_facts', 'BOX_DEFAULTS', 'UNTOUCHED', 'fact_sources', 'follow_up_sources', 'sources_kept',
    'district_confirmed']


# the grade isn't required: without one the check runs and height and stories need review until it's set (spec C3)
REQUIRED = ("jurisdiction", "zone", "use", "street_line", "lot_surveyed")   # corner lot unanswered: the yards wait (C)


def missing(facts):
    """The required lot facts not yet given: the confirm dialog shows whenever any is missing."""
    facts = facts or {}
    return [k for k in REQUIRED if facts.get(k) is None or facts.get(k) == []]


def with_suggestions(saved, suggested):
    """The facts to confirm: what is saved, with suggestions only for what is missing. The street lines and their
    street ids are one fact: saved lines keep only their own saved ids, never the suggestion's (ids that name other
    lines: two streets one id, a frontage read along both; street ids review round 3, F1), and suggested lines only
    the suggestion's."""
    out = dict(suggested)
    out.update({k: v for k, v in (saved or {}).items() if v is not None})
    own = (saved or {}) if (saved or {}).get("street_line") else suggested or {}   # whose lines: their ids alone
    return set_street_lines(out, out.get("street_line"), own.get("street_ids"))


# The facts only the architect can state (the model can't show them), in the order they are asked: each with its
# prompt, its kind (a whole number 0 or more, or yes / no) and its name in a row's words. A row waiting on any of
# them says which, and its "Enter …" button asks for exactly those (needs_of, enter_words).
STATED_FACTS = {
    "sleeping_rooms": ("Bedrooms", "count", "bedrooms"),
    "parking_spaces": ("Off-street parking spaces", "count", "parking spaces"),
    "dwelling_units": ("Dwelling units on this lot (a semi-detached or attached building split along its party walls: "
                       "this lot's units only)", "count", "dwelling units"),
    "rooms_let_for_profit": ("Rooms let for profit", "count", "rooms let for profit"),
    "conversion": ("Made by converting an existing building, not new construction? (§325-3B)", "yes_no",
                   "whether it is a conversion"),
    "occupants": ("Occupants on this lot, all dwelling units together (§325-3B OCCUPANT: in R-2c, every person with the "
                  "right to occupy, living there yet or not)", "count", "occupants"),
    "occupants_most_in_one_unit": ("Most occupants in any one dwelling unit (optional: how they are split)", "count",
                                   "the most occupants in one unit"),
    "attached_units_in_building": ("Dwelling units in the whole attached building, every lot it stands on (§325-3B: "
                                   "three to six)", "count", "the units in the whole building"),
    "abuts_r1_district": ("Is any R-1a or R-1b land touching this lot (even at a corner), or across a street, alley, creek or other waterway, railroad or other right-of-way from it? (§325-19E)",
                          "yes_no", "whether the lot abuts R-1 land"),
    # who lives there (§325-3B's one-family and two-family dwellings) and a home occupation: blank until said, so
    # the rules that read them need review (never 0 or no)
    "unrelated_persons": ("Most people in any one dwelling unit not related by blood, marriage or adoption to its "
                          "household's family (minor dependent children in a parent's or relative's care left out)",
                          "count", "unrelated people per unit"),
    # asked alone in R-3 and RU, so it says the whole count itself (review round 2: "the same count" pointed at a
    # question never asked there)
    "unrelated_persons_with_children": ("Most people in any one dwelling unit not related by blood, marriage or adoption "
                                        "to its household's family, minor dependent children counted too", "count",
                                        "unrelated people per unit, children counted"),
    # the house itself, not only an accessory dwelling unit on the lot; with an ADU on the lot the allowance needs
    # review (the owner-and-ADU open question, #38 review)
    "owner_occupied": ("Does the owner (§325-3B OWNER) live in the one-family dwelling itself (not only in an "
                       "accessory dwelling unit on the lot)?", "yes_no", "whether the owner lives there"),
    "accessory_dwelling_unit": ("Is there an accessory dwelling unit (ADU) on the lot (§325-3B, §325-28)?", "yes_no",
                                "whether an ADU is on the lot"),
    "functional_family_unit": ("Is the household to be shown to the City to be a functional family unit (§325-3B)?",
                               "yes_no", "whether the household is a functional family unit"),
    "home_occupation": ("Is a home occupation planned (§325-3B: a business, studio or office run by a resident)?",
                        "yes_no", "whether a home occupation is planned"),
    # floor areas in square feet, any number 0 or more (never rounded: 500.4 sq ft typed as 500 would pass the
    # 500 sq ft limit; review round 1)
    "home_occupation_area": ("Home occupation's indoor floor area, accessory buildings included (sq ft)", "area",
                             "the home occupation's floor area"),
    "home_occupation_unit_area": ("Floor area of the dwelling unit it is in (sq ft)", "area",
                                  "its dwelling unit's floor area"),
    # how many primary buildings the lot holds (§325-8B(1), §325-7B, §325-8E): read from the drawing where it can
    # be (one building, or none standing apart that could hold a home); asked where it can't
    "primary_buildings": ("Primary buildings on the lot, the main one included: each separate building holding a home "
                          "or other primary use, not a garage, shed or accessory dwelling unit (§325-8B(1))", "count",
                          "the primary buildings on the lot"),
    "primary_buildings_same_use": ("Does every primary building on the lot hold the use entered for the lot?",
                                   "yes_no", "whether every primary building holds the lot's use"),
    # a stream or inlet near the lot (§325-26): the model doesn't show the water; the distance in feet as typed
    # (never rounded: 19.96 ft typed as 20 would pass)
    "stream_near_lot": ("Is any inlet wall, or the bank of an inlet channel or stream (at average water level), within "
                        "20 ft of the lot? (§325-26)", "yes_no", "whether a stream or inlet is within 20 ft of the lot"),
    "stream_distance": ("Least horizontal distance from any new structure (house, addition, garage, deck, fence; not a "
                        "patio) to that wall or bank, at average water level (ft)", "length",
                        "the distance from the stream"),
    "south_hill_overlay": ("Is the lot in the South Hill Overlay District (§325-8E; the City's zoning map)?", "yes_no",
                           "whether the lot is in the South Hill Overlay"),
    # the chart's private garage limit (p.2 notes 6 and 7): the cars all the lot's garages hold together, and, only once
    # that is over the limit, how many garages (ROW_ONLY_FACTS)
    "garage_cars": ("Cars the lot's private garages hold, all together: every enclosed garage, attached or detached (0 if "
                    "there is none; a carport isn't enclosed)", "count", "the cars the private garages hold"),
    "private_garages": ("Private garages on the lot (an attached garage counts)", "count",
                        "the private garages on the lot"),
    # an accessory dwelling unit (§325-28): what kind it is, then, only once an ADU is said to be on the lot, what its
    # rules read (ROW_ONLY_FACTS); a detached one's building is picked in the model (adu_building), never typed
    "adu_detached": ("Is the accessory dwelling unit detached: in its own building, not in or on the main building? "
                     "(§325-3B)", "yes_no", "whether the ADU is detached"),
    "adu_existing_building": ("Is the detached ADU in an accessory building that already exists (not new "
                              "construction)? (§325-28C(7)(b))", "yes_no", "whether the ADU's building already exists"),
    "adus_on_parcel": ("Accessory dwelling units on the parcel, any already there included (§325-28C(1))", "count",
                       "the ADUs on the parcel"),
    "adu_bedrooms": ("Bedrooms in the accessory dwelling unit (§325-28C(3))", "count", "the ADU's bedrooms"),
    # floor areas as typed, never rounded (as the home occupation's)
    "adu_floor_area": ("Floor area of the attached accessory dwelling unit (sq ft)", "area", "the ADU's floor area"),
    "primary_floor_area": ("Floor area of the whole main building the ADU is in, the ADU included (sq ft)", "area",
                           "the main building's floor area"),
    # the whole building's count, asked only where the measuring asks for it (a part not drawn as floor blocks):
    # stories_needed; it stands only if at least the floors drawn (the measuring checks, and refused_stories says)
    "stories": ("Stories of the whole building", "count", "the number of stories"),
}
# The least whole number each counted fact may be: its own definition's (a unit's most occupants, a building's units:
# at least one), else 0. The answer fields (parse_answer) and update_counts both use it, so a field can't accept what
# the check refuses (#r2 review round 2).
MINIMUM = {"occupants_most_in_one_unit": 1, "attached_units_in_building": 1, "primary_buildings": 1,
           "private_garages": 1, "adus_on_parcel": 1}
# Facts a row can be decided without, each with the fact that bounds it from above (the most occupants in one unit
# is 1 to occupants): asked only where some value in that range would change the row (present.could_settle).
OPTIONAL = {"occupants_most_in_one_unit": "occupants"}


def minimum(key):
    return MINIMUM.get(key, 0)


STORIES_ASKED = ("enter the number of stories", "enter the count")      # the measuring's own words when it waits for the count


def stories_needed(record):
    """Whether the stories measurement waits for the architect's count (its reason asks to enter it)."""
    return any(w in ((record or {}).get("reason") or "") for w in STORIES_ASKED)


def refused_stories(items):
    """The message when the count entered was refused by the measuring (its code, stories_refused, on the row:
    never its words, which may be reworded), else None."""
    i = next((i for i in items or [] if i.get("refused")), None)
    if i is None:
        return None
    why = i.get("reason") or ""
    i_said = why.split(": does not comply under that reading. ")[-1].rstrip(".")
    return (i_said[0].upper() + i_said[1:] if i_said else "The count") + ". The count wasn't kept."


INTERIOR_FACTS = ("sleeping_rooms", "parking_spaces")    # inside the building (on hold): never asked in the box
# Read from the drawing (the main building is one; solids standing apart that could hold a home are readings), so the
# box never asks them up front: the panel's Enter flow still does, where the drawing can't say (measure._primary_buildings)
DRAWN_FACTS = ("primary_buildings", "primary_buildings_same_use")
# Use details (Ben, 2026-10-27: ask up front only what an architect knows at the start and what shapes the exterior or the
# envelope): who lives there, rooms let for profit (a use detail, the coordinator for Ben, 2026-10-27; the number of homes
# and new-or-converted stay up front), and a home business. Not asked in the start box; answered later, when the interior is planned,
# with the panel's Enter flow. Their rules never pass while unanswered (they stay "needs review"); the panel lists them
# in their own collapsed group, apart from the building's problems (is_use_detail). Ben will settle the exact questions
# later, so this tuple is the one place that moves them: a fact added here leaves the start box and joins that group.
DEFERRED_FACTS = ("unrelated_persons", "unrelated_persons_with_children", "occupants", "occupants_most_in_one_unit",
                  "owner_occupied", "functional_family_unit",
                  "home_occupation", "home_occupation_area", "home_occupation_unit_area", "rooms_let_for_profit",
                  "adu_bedrooms", "adu_floor_area", "primary_floor_area")
# Facts the measuring checks against each other (a count with the children counted can't be smaller than the count
# without: model_measurement.project.fact_conflict_rows): kept or dropped together, so a contradiction is never hidden
# by dropping half of it.
CHECKED_TOGETHER = (("unrelated_persons", "unrelated_persons_with_children"),)
# the group's title is short, so the narrow panel shows it whole with its count ("Use details (for later) · 3"); when to
# answer is said in each row's reason instead (coordinator for Ben, 2026-10-28)
USE_DETAILS_TITLE = "Use details (for later)"
USE_DETAILS_WHEN = "Answer when you plan the interior"
# Facts never asked in the start box, each with the fact that must be entered before a row asks it: the number of
# private garages matters only when the cars they hold are over the chart's limit (a lot of three cars or fewer passes
# whatever the count), so asking it up front would ask every architect with a garage a question that rarely matters.
# A row waiting on the garage's car limit asks the cars first (needs_of); entered over the limit, it then asks this.
# An accessory dwelling unit's facts likewise wait for "is there an ADU" (asked in the start box: a detached ADU is a
# building, so it shapes the exterior, Ben 2026-10-30), and a detached one's for
# "detached?": a lot without an ADU is never asked them (its rules are not applicable once that is answered no).
ROW_ONLY_FACTS = {"private_garages": "garage_cars", "adu_detached": "accessory_dwelling_unit",
                  "adus_on_parcel": "accessory_dwelling_unit", "adu_bedrooms": "accessory_dwelling_unit",
                  "adu_existing_building": "adu_detached", "adu_floor_area": "adu_detached",
                  "primary_floor_area": "adu_detached"}
BOX_ASKS = tuple(k for k in STATED_FACTS if k != "stories" and k not in INTERIOR_FACTS + DRAWN_FACTS + DEFERRED_FACTS
                 and k not in ROW_ONLY_FACTS)   # what the box can ask


def is_use_detail(item, facts=None):
    """Whether a panel row is a use detail still waiting to be answered: it needs review, and everything it is waiting
    on (its "needs") is a deferred fact that is still blank in `facts`. Only then: a row waiting on anything else too,
    one with no named need, a row about facts that disagree (they are filled in), and any row that has been decided
    (complies, fails) stays among the building's rows, so an answer that fails counts as a failure and a question left
    open never reads as a pass."""
    needs = item.get("needs") or []
    return (item.get("status") == "needs_review" and bool(needs) and all(k in DEFERRED_FACTS for k in needs)
            and all((facts or {}).get(k) is None for k in needs)
            and not str(item.get("id") or "").startswith("facts.conflict"))


# What a use itself says about a fact, from the City's own definitions, so it is never asked (Ben, 2026-10-25):
# §325-3 "DWELLING, ONE-FAMILY — A dwelling unit…" (chapter p.7) and "DWELLING, TWO-FAMILY — A building containing two
# dwelling units…" (p.9). Exactly these uses: a semi-detached or attached one-family dwelling is one unit of a
# building the rules count as a whole (R-3a's note 7 reads the row's dwelling units), so its count is asked, never
# taken as 1 (a row of six would pass a lot sized for three).
IMPLIED_BY_USE = {"one_family_detached": {"dwelling_units": 1}, "two_family": {"dwelling_units": 2}}
IMPLIED_SOURCE = "said by the use (City definition, §325-3)"


def implied_facts(use):
    """What the use itself says (IMPLIED_BY_USE), for this use only: never a prefix or a guess."""
    return dict(IMPLIED_BY_USE.get(use) or {})


# A fact that only matters once another is "yes": its rules are gated by it (a stream's distance by "a stream is within
# 20 ft", the home occupation's floor areas by "a home occupation is planned"), so it is asked only after that answer.
# Until then the rules say they need the first answer, never the second.
ASKED_AFTER = {"home_occupation_area": "home_occupation", "home_occupation_unit_area": "home_occupation",
               "stream_distance": "stream_near_lot"}


def follow_up_keys(options, zone, use, answers=None):
    """The facts the box asks after Use for this district and use (options["follow_ups"], from the rulebook). With
    `answers` (the facts as entered so far), a fact in ASKED_AFTER is asked only when the one it waits on is yes;
    without them, every fact the rules read."""
    keys = [k for k in (((options or {}).get("follow_ups") or {}).get(zone) or {}).get(use) or [] if k in BOX_ASKS]
    if answers is None:
        return keys
    return [k for k in keys if k not in ASKED_AFTER or answers.get(ASKED_AFTER[k]) is True]


def gate_of(answers):
    """The answers that decide which follow-up questions are asked (the ones ASKED_AFTER names): what the box compares
    to know it must open again."""
    return {p: (answers or {}).get(p) is True for p in sorted(set(ASKED_AFTER.values()))}


# What each question is called in the box's compact "About this project" section (the full question is its hover text
# and the panel's Enter prompt), and the one-click answers it offers after "Not answered". A yes / no question offers
# its two answers in the architect's words; a count with a small range offers the numbers. Never a default: the
# dropdown starts on "Not answered" and the rules that read the fact say so (NEVER a false pass).
ABOUT_LABELS = {
    "unrelated_persons": "Unrelated people in one home",
    "unrelated_persons_with_children": "Unrelated people in one home",
    "occupants": "Occupants on the lot",
    "occupants_most_in_one_unit": "Most occupants in one unit",
    "rooms_let_for_profit": "Rooms let for profit",
    "dwelling_units": "Homes on this lot",
    "attached_units_in_building": "Homes in the attached building",
    "owner_occupied": "Owner lives in the house",
    "accessory_dwelling_unit": "Accessory dwelling unit",
    "functional_family_unit": "Functional family unit",
    "home_occupation": "Home business",
    "home_occupation_area": "Business floor area (sq ft)",
    "home_occupation_unit_area": "Its home's floor area (sq ft)",
    "stream_near_lot": "Stream or inlet",
    "stream_distance": "Distance to it (ft)",
    "south_hill_overlay": "South Hill Overlay",
    "garage_cars": "Private garage, cars",
    "abuts_r1_district": "Next to R-1 land",
    "conversion": "New or converted",
}
ABOUT_WORDS = {            # (the "no" answer, the "yes" answer)
    "owner_occupied": ("Owner lives elsewhere", "Owner lives in the house"),
    "accessory_dwelling_unit": ("No ADU on the lot", "ADU on the lot"),
    "adu_detached": ("Attached (in or on the house)", "Detached (its own building)"),
    "adu_existing_building": ("New construction", "In an existing accessory building"),
    "functional_family_unit": ("Not relying on one", "Will show it to the City"),
    "home_occupation": ("No home business", "Home business planned"),
    "stream_near_lot": ("No stream within 20 ft", "Stream or inlet within 20 ft"),
    "south_hill_overlay": ("Not in the South Hill Overlay", "In the South Hill Overlay"),
    "abuts_r1_district": ("No R-1 land touches it", "R-1 land touches or faces it"),
}
ABOUT_COUNTS = {            # a count's one-click numbers (a typed number is not offered here: the panel's Enter flow)
    "unrelated_persons": [("0 (one family)", 0)] + [(str(n), n) for n in range(1, 7)],
    "unrelated_persons_with_children": [("0 (one family)", 0)] + [(str(n), n) for n in range(1, 7)],
    "rooms_let_for_profit": [("None", 0)] + [(str(n), n) for n in range(1, 7)],
    "attached_units_in_building": [(str(n), n) for n in range(2, 9)],
    "dwelling_units": [(str(n), n) for n in range(1, 9)],
    "garage_cars": [("No garage", 0)] + [(str(n), n) for n in range(1, 7)],
}
# Several answers in one click (shown only when the district and use ask at least one of them; it fills the others
# that are asked and leaves the rest as they were). Each is a statement the architect makes by picking it.
QUICK_ANSWERS = (
    ("1 family, no roomers", {"unrelated_persons": 0, "unrelated_persons_with_children": 0, "rooms_let_for_profit": 0,
                              "functional_family_unit": False}),
    ("Owner lives there", {"owner_occupied": True}),       # whether an ADU is on the lot: asked up front, alone
    ("No home business", {"home_occupation": False}),
    ("No stream, not in South Hill", {"stream_near_lot": False, "south_hill_overlay": False}),
)


ABOUT_LABEL_WIDTH, ABOUT_FIELD_WIDTH, ABOUT_TYPED_WIDTH, ABOUT_QUICK_WIDTH = 190, 215, 100, 215   # px
ABOUT_NOTE_WIDTH = 560
QUICK_HINT = "Pick to fill several answers…"


def about_label(key):
    return ABOUT_LABELS.get(key) or STATED_FACTS[key][2][:1].upper() + STATED_FACTS[key][2][1:]


def choices_for(key, kind, value=None):
    """The one-click answers a question offers, [(words, value)], or None when it is typed (areas, distances, the
    counts without a small range). A value already set that the list lacks (typed in the panel) stays among them."""
    if kind == "yes_no":
        no, yes = yes_no_words(key)
        return [(no, False), (yes, True)]
    listed = ABOUT_COUNTS.get(key)
    if listed is None:
        return None
    if value is not None and value not in [v for _, v in listed]:
        listed = listed + [(str(value), value)]
    return list(listed)


def quick_answers(keys):
    """The one-click answers for several questions at once: [(words, {fact: value})], each only with the facts that are
    asked (`keys`), and only when it fills at least one."""
    out = []
    for words, sets in QUICK_ANSWERS:
        mine = {k: v for k, v in sets.items() if k in keys}
        if mine:
            out.append((words, mine))
    return out


def follow_up_rows(options, zone, use, facts):
    """The box's questions after Use: the facts the district's rules need for this use (follow_up_keys), each
    {"key", "label" (the full question), "short" (its name in the compact section), "kind" (count / yes_no / area /
    length), "value" (as entered, or None), "choices" (its one-click answers, or None when typed)}; none when the
    district has no such rule or the use says them."""
    return [{"key": k, "label": STATED_FACTS[k][0], "short": about_label(k), "kind": STATED_FACTS[k][1],
             "value": (facts or {}).get(k), "choices": choices_for(k, STATED_FACTS[k][1], (facts or {}).get(k))}
            for k in follow_up_keys(options, zone, use, facts or {})]


# The words a yes / no question's dropdown offers after "Not answered": (the "no" answer, the "yes" answer)
YES_NO_WORDS = {"conversion": ("New construction", "Conversion of an existing building")}
NOT_ANSWERED = "Not answered"
FOLLOW_UP_HELP = ("Your answers. Leave one blank and the rules that need it say needs review (never read as 0 "
                  "or No).")      # a sentence, never a fragment (the architect's review, 2026-10-28)


def yes_no_words(key):
    return YES_NO_WORDS.get(key) or ABOUT_WORDS.get(key) or ("No", "Yes")


def _listed(options, zone):
    return ((options or {}).get("district_uses") or {}).get(zone) or []


def use_note(options, zone, use):
    """What the box says under Use when the pick isn't permitted by right in the district: the chart's own words
    (a special permit), or, for a use the district's chart doesn't list at all, that its Use row won't comply.
    None when it is permitted (or the district lists no uses)."""
    listed = _listed(options, zone)
    for u in listed:
        if u["id"] == use:
            return u.get("note")
    if listed and use:
        name = ((options or {}).get("uses") or {}).get(use, use)
        return f"{name} isn't on {zone}'s list of uses in the zoning chart: its Use row won't comply."
    return None


def district_use_names(options, zone, current=None):
    """The Use dropdown's choices for the district: [(id, name)], permitted first, as the chart lists them; every
    city use when the district has none listed. The use already set stays among them even when the district doesn't
    list it (last), so opening the box never changes it unasked (use_note says why it won't comply)."""
    names = (options or {}).get("uses") or {}
    out = [(u["id"], u["name"]) for u in _listed(options, zone)] or list(names.items())
    if current and current not in [k for k, _ in out]:
        out.append((current, names.get(current, current)))
    return out


def box_needs_refresh(options, shown, now):
    """Whether the box must open again after a pick in its Use or district dropdown, or in a question another waits on
    (a stream's yes opens its distance): `shown` and `now` are (zone, use) or (zone, use, gate_of(answers)) as laid
    out and as picked. Again when the uses offered, the note under Use or the questions after it differ (their fields
    are laid out once); never for a pick that changes none of them."""
    def layout(zone, use, gate=None):
        asked = None if gate is None else {p: True for p, yes in gate.items() if yes}
        return district_use_names(options, zone, use), use_note(options, zone, use), \
            follow_up_keys(options, zone, use, asked)
    return layout(*shown) != layout(*now)


def answers_applied(facts, answers, zone, use, options, track=None):
    """The facts after the box (box_applied) and the keys the architect answered in it with a value. `track`: what
    the box knows this session (box_track); without it, from the facts alone."""
    out, after = box_applied(facts, answers, zone, use, options, track if track is not None else box_track(facts))
    shown = [k for k in (answers or {}) if k in BOX_ASKS and k not in after["said"]]
    return out, sorted(k for k in shown if out.get(k) is not None)


def box_track(facts, sources=None):
    """What the box carries across its picks (session only, saved_ui["_answers"]): "said", the facts whose stored
    value the use itself said (their saved source is IMPLIED_SOURCE; with no sources, those equal to what the facts'
    use says: implied_facts); "held", an architect's answer set aside while a use says that fact instead; "typed", the
    facts the architect answered in the box this session (each saved "entered by you" at Draw: typed_sources)."""
    facts = facts or {}
    if sources is None:
        said = [k for k, v in implied_facts(facts.get("use")).items()
                if k in BOX_ASKS and facts.get(k) == v and type(facts.get(k)) is type(v)]
    else:
        said = [k for k in BOX_ASKS if facts.get(k) is not None
                and ((sources or {}).get(k) or {}).get("source") == IMPLIED_SOURCE]
    return {"said": said, "held": {}, "typed": []}


def box_applied(facts, answers, zone, use, options, track):
    """The facts after the box, which changes only what it shows (Rhino runs, 2026-10-28, P0s: a Use or district
    picked and picked back blanked every answer, or brought back an older one). Returns (facts, track).
    1. Each field the box showed (a BOX_ASKS key in `answers`, laid out for the use the box opened with: None when
       blank) is set from its answer, or unset when blank or refused (its rules need review, never 0 or no), whatever
       the use picked now: what was typed is never dropped nor replaced by an older answer.
    2. A fact the old use said (track "said": by its source, never by its value) goes when the new use doesn't say
       it, and the architect's own answer set aside for it ("held") comes back: a two-family's 2 units are never read
       as a multiple dwelling's count, and a semi-detached pair's typed 2 survives a look at two-family.
    3. What the new use says for the facts its rules read (implied_by) is set; an architect's answer there is held.
    4. A fact asked only after another's yes (ASKED_AFTER) goes when that question is answered no in the box: it no
       longer applies (a blank keeps it: nothing contradicts it, and its rule needs review either way).
    Every other fact stays as stored, never read unshown: any fact this district's rules read for this use is asked
    (follow_up_keys) and shown with its value when the box opens laid out for it (box_needs_refresh). A fact asked
    only after another's yes (ASKED_AFTER: a stream's distance) is read only by rules gated by that yes. The use
    details (DEFERRED_FACTS, answered in the panel's row dialog, never in the box) stay as stored whatever the use or
    district: where the new use's rules don't read one it decides nothing, and where they do it is the architect's
    answer, shown in its row; so the facts checked together (CHECKED_TOGETHER) always stay together, and a
    contradiction between them is never hidden by dropping half of it."""
    now = implied_by(options, zone, use)
    out = dict(facts or {})
    said, held = list((track or {}).get("said") or []), dict((track or {}).get("held") or {})
    typed = list((track or {}).get("typed") or [])
    given = {}
    for k, v in (answers or {}).items():
        if k not in BOX_ASKS:
            continue
        out.pop(k, None)
        held.pop(k, None)
        said = [x for x in said if x != k]
        typed = typed + [k] if k not in typed else typed
        if v is not None:
            given[k] = v
    out = update_counts(out, given)
    for k, gate in ASKED_AFTER.items():   # "no" said in the box to the question it waits on: moot, so it goes (#45: a
        if given.get(gate) is False:      # stream's old 5 ft beside a new "no stream within 20 ft" would make the
            out.pop(k, None)              # facts disagree)
    for k in [k for k in said if k not in now]:
        out.pop(k, None)
        said.remove(k)
        if k in held:
            out[k] = held.pop(k)
    for k, v in now.items():
        if k not in said and out.get(k) is not None:
            held[k] = out[k]
        out[k] = v
        said = said + [k] if k not in said else said
    return out, {"said": said, "held": held, "typed": typed}


def typed_sources(sources, track, facts, day):
    """The sources after Draw for the facts the architect answered in the box this session (track "typed"), shown
    or not by then: each set "entered by you" with its value now, each unset with no source (row_sources); what a
    use says keeps the use's (fact_sources)."""
    return row_sources(sources, [k for k in (track or {}).get("typed") or [] if k not in (track or {}).get("said", [])],
                       facts, day)


def implied_by(options, zone, use):
    """What the use says for the facts this district's rules read (options["implied"]): never asked."""
    return dict((((options or {}).get("implied") or {}).get(zone) or {}).get(use) or {})


def parse_answer(kind, text, key=None):
    """A follow-up field's text as the fact's value: a whole number (count: `key`'s least, 0 unless MINIMUM says
    more), a number of square feet or feet (area, length: 0 or more, as typed, never rounded), yes / no (yes_no);
    blank: None (unanswered: its rules stay NEEDS REVIEW, never 0 or no); anything else raises ValueError."""
    text = (text or "").strip().lower()
    if not text:
        return None
    if kind == "yes_no":
        if text in ("yes", "y"):
            return True
        if text in ("no", "n"):
            return False
        raise ValueError("answer yes or no")
    if kind in ("area", "length"):
        # commas only as thousands separators (1,200): "2,5" is not 25 (a European decimal comma is refused, not misread)
        if not re.fullmatch(r"((\d+|\d{1,3}(,\d{3})+)(\.\d+)?|\.\d+)", text, re.ASCII):
            raise ValueError("a number of " + ("square feet" if kind == "area" else "feet") + ", 0 or more")
        number = float(text.replace(",", ""))
        return int(number) if number == int(number) else number
    least = minimum(key) if key else 0
    if not (text.isascii() and text.isdigit()) or int(text) < least:
        raise ValueError(f"a whole number, {least} or more")
    return int(text)


def answer_problem(kind, text, key=None):
    """What the box says beside a follow-up field whose text isn't an answer (None when it is, or is blank): the
    entry is not kept, so the rules that need it say so (never read as 0)."""
    try:
        parse_answer(kind, text, key)
    except ValueError as e:
        return f"Not kept: {e}. Its rules need review until it is."
    return None


# The box's questions after Use, each as its words wrapped at QUESTION_WIDTH with its answer beside them, and one note
# under them all: the start box stays laptop-sized (≤ ~900 px wide) with the longest questions (#38's household ones
# ran ~1,200 px on one line and pushed the box to 1,560-2,020 px: Rhino run of demo 2c0a5c0). Pinned in
# test_box_width.py, which lays the real box out and bounds its width.
QUESTION_WIDTH = 360
ANSWER_WIDTH = 300     # every answer dropdown in a row's dialog one width, lined up ("Conversion of an existing
                       # building" fits; the architect's review, 2026-10-28)


TEXT_PX = 6.0      # px a character at size 12, a little over the system font's (~5.5 measured in Rhino): errs wide


def text_wider(text, size, px):
    """Whether `text` at `size` (13 when not set) runs wider than `px` on one line (by TEXT_PX), so its label wraps."""
    return len(text or "") * TEXT_PX * (size or 13) / 12 > px


def answers_note(entries):
    """The note under the box's questions, for `entries` [(key, kind, text)] in the order asked: FOLLOW_UP_HELP, or
    every entry not kept, each named by its fact ("Rooms let for profit: Not kept: …"), so each is said at once and
    never read as 0. Returns (text, refused)."""
    said = []
    for key, kind, text in entries:
        try:
            parse_answer(kind, text, key)
        except ValueError as e:
            said.append((STATED_FACTS[key][2] if key in STATED_FACTS else key.replace("_", " "), str(e)))
    if not said:
        return FOLLOW_UP_HELP, False
    if len(said) == 1:
        name, why = said[0]
        return f"{name[0].upper() + name[1:]}: Not kept: {why}. Its rules need review until it is.", True
    listed = ", ".join(f"{name} ({why})" for name, why in said)
    return f"Not kept: {listed}. Their rules need review until they are.", True


def needs_of(names, values, settles=None):
    """The stated facts a rule reads (`names`) that aren't set yet (`values`), in the order they are asked; never the
    stories count (asked only where the measuring asks for it: stories_needed). An optional one (OPTIONAL) only where
    `settles(key)` says entering it could change the row. A row-only fact (ROW_ONLY_FACTS) only once the fact it
    follows is entered."""
    return [k for k in STATED_FACTS if k != "stories" and k in names and (values or {}).get(k) is None
            and (k not in OPTIONAL or (settles is not None and settles(k)))
            and (k not in ROW_ONLY_FACTS or (values or {}).get(ROW_ONLY_FACTS[k]) is not None)]


def _and(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def enter_words(needs):
    """The button's words for a row waiting on `needs`: "Enter bedrooms and parking spaces"."""
    return "Enter " + _and([STATED_FACTS[k][2] for k in needs]) if needs else None


def answer_words(needs):
    """The words on a row's button and its dialog's title: the facts' own words while they fit a button ("Enter
    bedrooms and parking spaces"); longer, how many ("Answer 4 questions"): the whole list ran to ~25 words and was
    cut off on the button and in the title bar (the architect's review, 2026-10-28). The dialog lists each question
    and the row's reason still names them."""
    if not needs:
        return None
    words = enter_words(needs)
    return words if len(needs) == 1 or len(words) <= BUTTON_WORDS else "Answer %d questions" % len(needs)


BUTTON_WORDS = 40       # characters a row's button holds at the panel's width (380-460 px) without being cut off


def needs_reason(needs):
    """Why the row isn't checked: "Needs bedrooms and parking spaces, which the model doesn't show" (its button,
    enter_words, asks exactly those in a small dialog: row_fields)."""
    if not needs:
        return None
    return "Needs " + _and([STATED_FACTS[k][2] for k in needs]) + ", which the model doesn't show"


# ---- a row's own dialog (coordinator, 2026-10-28, agreed with Ben): the row's "Enter …" button asks only the
# stated facts that row waits for (its `needs`), in a small modal dialog; OK saves exactly those, each "entered by
# you" with the day, as one Undo step, and checks again; Cancel, Esc or closing it changes nothing. It never touches
# the address, the lookup, the district, the use, the lot, the street side or any other fact: those stay in the
# start box (Edit site…), whose follow-up questions read the same facts, so an answer given here shows there.

SITE_HINT = "Edit site…"            # a row whose missing fact comes from the site (present.py's hint for it)
SITE_ASKS = ("Corner lot?",)        # the start box's own question a measuring's reason names (stops.py)


def row_fields(needs, facts):
    """The dialog's questions for a row waiting on `needs`, in the row's order: each {"key", "label", "kind"
    (count / yes_no), "value" (as saved, or None)}. Only stated facts (STATED_FACTS): never a site fact."""
    return [{"key": k, "label": STATED_FACTS[k][0], "kind": STATED_FACTS[k][1], "value": (facts or {}).get(k)}
            for k in needs or [] if k in STATED_FACTS]


def row_choice(value):
    """A yes / no question's dropdown index for a saved value: Not answered (0), the no answer (1), the yes (2)."""
    return {None: 0, False: 1, True: 2}[value]


def row_choice_text(index):
    """A yes / no dropdown's pick as parse_answer reads it: Not answered is blank (never no)."""
    return {1: "no", 2: "yes"}.get(index, "")


def row_answers_applied(facts, needs, answers):
    """The facts after OK in a row's dialog: each key in `needs` set from its answer (`answers`: key -> the text
    typed, or "yes" / "no" / "" from a dropdown: row_choice_text); a blank (or missing) answer leaves that fact unset,
    so its rules need review (never 0 or no). Every other key is exactly as it was. Any entry that isn't an answer
    raises ValueError with words for the dialog, and nothing changes."""
    out = dict(facts or {})
    bad = []
    for k in [k for k in needs or [] if k in STATED_FACTS]:
        try:
            value = parse_answer(STATED_FACTS[k][1], (answers or {}).get(k), k)
        except ValueError as e:
            bad.append(f"{STATED_FACTS[k][0]}: {e}")
            continue
        if value is None:
            out.pop(k, None)
        else:
            out[k] = value
    if bad:
        raise ValueError("Not saved. " + "; ".join(bad) + ". Correct it, or leave it blank (it then needs review).")
    return out


def row_problem(facts, needs, answers):
    """What the row's dialog says at OK when an entry isn't an answer (row_answers_applied's words; it stays open
    and nothing is saved), or None when OK may close it."""
    try:
        row_answers_applied(facts, needs, answers)
    except ValueError as e:
        return str(e)
    return None


def row_sources(sources, needs, facts, day):
    """The saved sources after OK in a row's dialog: each fact in `needs` that is set, "entered by you" on `day`;
    one left blank, none (an unset fact has no source). Every other source is exactly as it was."""
    out = dict(sources or {})
    for k in [k for k in needs or [] if k in STATED_FACTS]:
        v = (facts or {}).get(k)
        if v is None:
            out.pop(k, None)
        else:
            out[k] = {"value": {True: "yes", False: "no"}.get(v, v) if isinstance(v, bool) else v,
                      "source": ENTERED, "confirmed_by": "you", "date": day}
    return out


def site_row(item):
    """Whether a row waits on a site fact (address, lot, district, street side, corner lot): only the start box
    gives those, so the row keeps its Edit site… button."""
    item = item or {}
    return item.get("hint") == SITE_HINT or any(q in (item.get("reason") or "") for q in SITE_ASKS)


def row_buttons(item):
    """A row's buttons, as (words, action): its own dialog for the stated facts it waits on ("Enter dwelling
    units…", action "enter"), then, where a site fact is missing too, Edit site… ("edit_site") as the second."""
    out = []
    if (item or {}).get("needs"):
        out.append((answer_words(item["needs"]) + "…", "enter"))
    if site_row(item):
        out.append((SITE_HINT, "edit_site"))
    return out


def box_answers(options, zone, use, facts):
    """What the start box's follow-up questions show as answered: read from the saved facts themselves (the box
    keeps no copy of its own), so an answer given in a row's dialog shows in the box and Draw sets it again."""
    return {k: (facts or {}).get(k) for k in follow_up_keys(options, zone, use)}


def update_counts(facts, answers):
    """Bedrooms, parking spaces, stories, dwelling units and rooms let for profit (whole numbers, 0 or more) and
    whether the building is a conversion and whether the lot abuts R-1 land (yes / no) from the Lot facts prompts. An answer of None means the prompt
    was skipped: the fact stays as it was (unset stays unset, so its rules stay NEEDS REVIEW), never 0 or no."""
    out = dict(facts or {})
    counts = list(dict.fromkeys(["stories"] + [k for k, (_, kind, _) in STATED_FACTS.items() if kind == "count"]))
    for key in counts:
        if answers.get(key) is not None:
            n = int(answers[key])
            if n < minimum(key) or n != answers[key]:
                raise ValueError(f"{key} must be a whole number, {minimum(key)} or more")
            out[key] = n
    for key in [k for k, (_, kind, _) in STATED_FACTS.items() if kind in ("area", "length")]:
        if answers.get(key) is not None:
            a = answers[key]
            if type(a) not in (int, float) or not math.isfinite(a) or a < 0:
                raise ValueError(f"{key} must be a number of {'square feet' if STATED_FACTS[key][1] == 'area' else 'feet'}, 0 or more")
            out[key] = a
    for key in [k for k, (_, kind, _) in STATED_FACTS.items() if kind == "yes_no"]:
        if answers.get(key) is not None:
            out[key] = bool(answers[key])
    return out


def to_feet(facts, scale):
    """Facts read off the model (street line ends, ground level), in model units, as feet (scale = feet per
    model unit). Everything Gordium measures and stores is in feet."""
    out = dict(facts)
    if out.get("street_line"):
        out["street_line"] = [[[c * scale for c in p] for p in line] for line in out["street_line"]]
    if out.get("grade_elevation") is not None:
        out["grade_elevation"] = out["grade_elevation"] * scale
    return out


def set_street_lines(facts, lines, ids=None):
    """`facts` (changed in place, and returned) with the street lot lines `lines` and the street each is on (`ids`,
    one per line, None where unknown): both set, or both dropped. The one way the street lines change (review round
    7, P1: a lot re-picked kept the old lines' street names, and the lot facts were refused, saved ones unreadable);
    names that don't match the lines one for one are left out (unnamed, never misnamed)."""
    if lines:
        facts["street_line"] = lines
    else:
        facts.pop("street_line", None)
    if lines and _street_lines().matching_ids(lines, ids) is not None:
        facts["street_ids"] = list(ids)
    else:
        facts.pop("street_ids", None)
    return facts


def drop_stale(facts, lot_ids, building_ids):
    """The saved facts without a lot, main building or ADU's building that is no longer in the model (redrawn, joined, deleted):
    the lot's street lines go with it, so the confirm dialog asks again instead of keeping an id nothing has."""
    out = dict(facts or {})
    if out.get("lot_id") and out["lot_id"] not in lot_ids:
        out.pop("lot_id")
        set_street_lines(out, None)
    if out.get("main_building") and out["main_building"] not in building_ids:
        out.pop("main_building")
    if out.get("adu_building") and out["adu_building"] not in building_ids:      # the ADU's building, the same way
        out.pop("adu_building")
    return out


def after_lot_pick(facts, picked_lot):
    """The facts after the lot is (re)picked: a different lot drops the street lines, which belonged to the old
    one (they are asked again on the new lot), and so Enter can't keep them."""
    out = dict(facts)
    if picked_lot and picked_lot != out.get("lot_id"):
        out["lot_id"] = picked_lot
        set_street_lines(out, None)          # the old lot's street lines and their names go with it
        out.pop("plan_north_deg", None)      # the looked-up lot's turn belonged to it
        out.pop("ground_fall", None)         # and so did its ground (lot_ground_dropped: the saved state's too)
    return out


def lot_ground_dropped(saved_ui):
    """The saved state once the architect puts another lot in place of the looked-up one (their survey, a lot they
    drew, another outline picked): the looked-up ground fall was read on the old lot, so it no longer shows the lot
    level (review round 3: a level reading kept after the lookup's doubtful lot was replaced let height and stories
    pass on ground never read). Height and stories need review until the address is looked up again."""
    saved_ui = dict(saved_ui)
    saved_ui.pop("ground_fall", None)
    return saved_ui


def street_enter_keeps(facts):
    """Whether Enter at the first street-line prompt keeps the street lines saved for this lot."""
    return bool(facts.get("street_line"))


def corner_answered(facts, saved_ui, corner):
    """(facts, saved_ui) with the Corner lot? answer `corner` (None: unanswered), the one helper the start box and
    the command line both use: a changed answer drops the street lines and their street's name (a corner lot has
    two streets, any other one: picked again; review round 5, P0: the box kept both streets' lines on a lot answered
    No, and a 40 ft lot read 200 ft wide)."""
    was = (facts or {}).get("corner_lot")
    facts = dict(facts or {}, corner_lot=corner)
    if corner is None:
        facts.pop("corner_lot")
    saved_ui = dict(saved_ui or {})
    if was is not None and corner != was:         # a real answer that flips (the first answer, from "Not answered",
        set_street_lines(facts, None)             # keeps the prefilled line and its name: review round 6, P1)
        saved_ui.pop("street_name", None)
    return facts, saved_ui


def suggested_facts(jurisdiction, zones, lots, buildings):
    """The start box's prefilled lot facts, in the model's units (the plugin converts them to feet), for the
    architect to confirm. `lots`: the Site layer's closed outlines, each {"id", "area", "bottom" (its lowest
    level), "segments": [((x, y), (x, y)), ...]}; `buildings`: each {"id", "bottom", "volume" (of its box)}.
    The largest outline is the lot, its lowest line on screen the street side; the ground is flat at the
    buildings' lowest point (or the lot's level); the lot is not from a survey; the first zone with rules; a
    detached one-family house; the largest solid the main building. The corner-lot question is never answered
    here: always None, so the box asks it and the yards wait for the answer. A lot's "segments_ft" (the same
    segments in feet, when given) decide the street's lengths and turns, in feet as everywhere (review round 6,
    F2: a 6 mm slip in a millimetre model read as a 6 ft line)."""
    facts = {"jurisdiction": jurisdiction, "zone": zones[0] if zones else None, "use": "one_family_detached",
             "corner_lot": None, "ground_is_flat": True, "lot_surveyed": False}
    lot = max(lots, key=lambda l: l["area"]) if lots else None
    if lot is not None:
        facts["lot_id"] = lot["id"]
        if lot["segments"]:
            outline = [[[p[0], p[1]], [q[0], q[1]]] for p, q in lot["segments"]]
            feet = [[list(p[:2]) for p in line] for line in lot.get("segments_ft") or outline]
            # the lowest piece a street can start from (never a point drawn twice: round 4; an arc drawn in short
            # chords is a line: round 7)
            run = next((r for k in sorted(range(len(feet)), key=lambda k: (outline[k][0][1] + outline[k][1][1]) / 2)
                        for r in [street_run(feet, feet[k], tolerance=0.0)] if r is not None), None)
            # the whole street it is on (review round 1, F1: a tax-map street suggested as one piece), only when
            # both its ends are sure; else no suggestion, so the box asks for the click and the click asks the
            # question (round 3, F1: a curving street suggested as its first 30°, the front yard from part of it)
            if run and run["maybe"] == [[], []]:            # (an id on every line: "Street 1")
                set_street_lines(facts, [outline[k] for k in run["pieces"]], ["Street 1"] * len(run["pieces"]))
    ground = suggested_ground([b["bottom"] for b in buildings], lot["bottom"] if lot is not None else None)
    if ground is not None:
        facts["grade_elevation"] = ground
    if len(buildings) > 1:
        facts["main_building"] = max(buildings, key=lambda b: b["volume"])["id"]
    facts["corner_lot"] = None                     # never guessed, whatever came before
    return facts


def suggested_ground(building_bottoms, lot_bottom):
    """The ground level to suggest (feet or model units, as given): the lowest point of the buildings, or with no
    building yet (a new project on the architect's own lot) the lot outline's level. Shown in the dialog, never
    used unconfirmed."""
    return min(building_bottoms) if building_bottoms else lot_bottom


def unsettled(saved_ui, checked=None):
    """The checker's facts["unsettled"]: each doubt about what is drawn the architect hasn't ticked I checked this
    for (or changed). Empty when there are none. Only kept-safe wording (the doubts saved)."""
    done = set(checked if checked is not None else (saved_ui or {}).get("checked") or [])
    return {k: v for k, v in ((saved_ui or {}).get("doubts") or {}).items() if k in checkable() and k not in done}


def checkable():
    """The rows "I checked this" settles, and so the doubts kept: with the MVP's flat ground the ground is not the
    lookup's, so it has no doubt to keep (it would hold height and stories at needs review with no row to clear)."""
    return tuple(k for k in CHECKABLE if not (FLAT_GROUND and k == "ground"))


def settle(saved_ui, row):
    """The architect changed that row (picked another street line, their survey or a lot they drew, other ground):
    it is theirs now, so no doubt about it is left."""
    saved_ui = dict(saved_ui)
    saved_ui["doubts"] = {k: v for k, v in (saved_ui.get("doubts") or {}).items() if k != row}
    saved_ui["_live"] = {k: v for k, v in (saved_ui.get("_live") or {}).items() if k != row}
    saved_ui["checked"] = [k for k in saved_ui.get("checked") or [] if k != row]
    if row == "lot":
        saved_ui["replaceable_lot"] = None           # never replaced by a later lookup
        saved_ui.pop("lot_source", None)
    if row == "street":                          # the architect's own line: no looked-up name stays on it
        saved_ui.pop("_street_name", None)
        saved_ui.pop("street_name", None)
    return saved_ui


UNDER_A_BOX = ("check", "save_facts", "open_box")   # what may not happen while a start box is open


def allowed(action, box_open):
    """Whether `action` may run now: a check, writing the lot facts and opening a second start box never happen while
    a start box is open (its own edits wait for it to close); anything else may."""
    return not (box_open and action in UNDER_A_BOX)


def pick_effect(what, outcome, facts, saved_ui):
    """(facts, saved_ui) after one of the start box's picks, from what the pick gave (the Rhino side only gathers it):
    street: {"lines", "ids": the street lines worked out at the pick (rhino-ui's street runs), "name"} or
    {"picks": the lot lines [a, b] clicked, "name": the clicked line's street (street_name_after_pick, else
    typed; None: unnamed)}; lot (Use my survey…): the outline picked; draw_lot: the outline drawn; terrain: the
    surface picked; spot / regrade: the points placed. Esc, Enter or nothing picked (`outcome` empty): nothing
    changes, every doubt stays (eval-integrity audit: Esc on Place spot grades wiped the ground's doubt).
    The street lines change only through set_street_lines (arch-fixes-2 round 7): on a corner lot every line
    clicked, no one name for them; otherwise pick_street, the name on the clicked line only (rounds 9-11)."""
    facts, saved_ui = dict(facts), dict(saved_ui)
    if not outcome or (what == "street" and not (outcome.get("picks") or outcome.get("lines"))):
        return facts, saved_ui
    if what == "street" and outcome.get("lines"):     # the street lines worked out at the pick (street runs)
        saved_ui = settle(saved_ui, "street")
        set_street_lines(facts, outcome["lines"], outcome.get("ids"))
        if facts.get("corner_lot") is True:            # two streets: no one name for them
            saved_ui.pop("street_name", None)
        else:
            saved_ui["street_name"] = outcome.get("name")      # the name on the clicked line only
        saved_ui["street_source"] = ENTERED
    elif what == "street" and facts.get("corner_lot") is not True:   # (a corner lot's clicks come as "lines"
        picks, name = outcome["picks"], outcome.get("name")              # with their ids, never bare: #18 reads a
        saved_ui = settle(saved_ui, "street")          # corner lot's streets only from them)
        lines, ids = pick_street(facts.get("street_line"), facts.get("street_ids"), picks[0], name)
        set_street_lines(facts, lines, ids)            # the name on the clicked line only
        saved_ui["street_name"] = name
        saved_ui["street_source"] = ENTERED
    elif what in ("lot", "draw_lot"):
        if outcome != facts.get("lot_id"):             # another lot: the looked-up ground was read on the old one
            facts, saved_ui = after_lot_pick(facts, outcome), lot_ground_dropped(saved_ui)
        facts["lot_surveyed"] = what == "lot"          # Use my survey…: a survey; drawn over the guide: not
        saved_ui = settle(saved_ui, "lot")
        if what == "draw_lot":
            saved_ui["lot_source"] = "drawn by you"
    elif what == "terrain":
        saved_ui.update(terrain_id=outcome, ground_kind="terrain")
        saved_ui = settle(saved_ui, "ground")
    elif what in ("spot", "regrade"):
        saved_ui = after_ground_pick(saved_ui, what, len(outcome))
    return facts, saved_ui


def after_ground_pick(saved_ui, what, placed):
    """Place spot grades / I'll regrade, with `placed` points actually added: the ground is the architect's only
    then. Esc or Enter with none placed changes nothing (review round 1: it settled a doubtful ground)."""
    if not placed:
        return dict(saved_ui)
    saved_ui = settle(saved_ui, "ground")
    saved_ui["ground_kind"] = what
    saved_ui.pop("ground_source", None)
    return saved_ui


def parse_feet(text):
    """A length the architect typed, in feet: 11'-8", 1' 6", 6", 6 in, 1.5, 1.5 ft, 2' -> feet; empty -> 0.0;
    anything it can't read -> None, never a silent 0."""
    import re
    t = (text or "").strip().lower()
    if not t:
        return 0.0
    t = re.sub(r"\s*(feet|foot|ft)\b", "'", t)
    t = re.sub(r"\s*(inches|inch|in)\b", '"', t)
    num = r"(\d+(?:\.\d+)?)"
    m = re.fullmatch(num + r"\s*'?", t)                                  # feet: 2, 2', 1.5 ft
    if m:
        return float(m.group(1))
    m = re.fullmatch(num + r"\s*'\s*-?\s*" + num + r'\s*"?', t)        # feet and inches: 11'-8", 1' 6
    if m:
        return float(m.group(1)) + float(m.group(2)) / 12
    m = re.fullmatch(num + r'\s*"', t)                                  # inches alone: 6", 6 in
    if m:
        return float(m.group(1)) / 12
    return None


def starting_house_fact(note, today):
    """The site fact for how far the starting house keeps back from the limits: Gordium's own figure, so never
    "confirmed by you" (the architect didn't confirm it). None when no house was drawn (`note` None)."""
    if not note:
        return None
    # the panel puts "Starting house: " in front, and it describes the house as Gordium drew it (the architect
    # may since have moved or replaced it), so it says so
    said = note[len("Starting house: "):] if note.startswith("Starting house: ") else \
        "it " + note[len("Starting house "):] if note.startswith("Starting house ") else \
        "the l" + note[1:] if note.startswith("Largest house") else note
    return {"value": "as first drawn, " + said, "source": SUGGESTED, "confirmed_by": None, "date": today}


# what the box's Change… on the street row does on a corner lot (_box_pick): one click per street keeps that whole
# street, and Enter ends it (never "pick each lot line": a click already takes the street's every piece)
CORNER_HINT = ("This lot faces two streets: click Change… on " + STREET_LABEL + ", then click once on each street "
               "(one click keeps the whole street) and press Enter")


def uncertain(state):
    """The one amber line for a case the box can't settle by itself, with what to do; None when there's none. A
    lookup that went wrong (not found, offline…) says so here; what a found lookup only tells (the lot shown dashed,
    nothing drawn until Draw) is lookup_note's plain line, never amber (the architect's review, 2026-10-28: the
    question and the information read as one warning)."""
    says = None if lookup_note(state) else (state.get("lookup") or {}).get("says")
    question = _question(state)
    return " · ".join(t for t in (question, says) if t) or None     # never one instead of the other


LOOKUP_INFO = ("found", "set_aside")      # a lookup's own line that only informs: shown plain


def lookup_note(state):
    """The plain line under the amber one: what a found (or set-aside) lookup tells, or None."""
    look = state.get("lookup") or {}
    says = look.get("says") if look.get("status") in LOOKUP_INFO else None
    # the offline safety net (a saved copy shown: the services didn't answer, pick the district again) asks for
    # something: it stays on the amber line (review round 1 of this change)
    # and so does the guide-only note (the State's tax map didn't answer: draw your lot over the guide; round 2)
    asks = says and (says.startswith(SAVED_SAYS.split("{")[0]) or says == GUIDE_PREVIEW)
    return None if asks else says


def _question(state):
    """Every question the box still has (each one, never only the first)."""
    asks = []
    if state.get("corner_lot") is None:          # never guessed: unanswered, the yards wait for it (§325-19C)
        asks.append("Does this lot face two streets? Answer Corner lot? under " + STREET_LABEL)
    elif state.get("corner_lot"):
        asks.append(CORNER_HINT)
    if len(state.get("zones_found") or []) > 1:
        asks.append("This lot is in two zones: pick the zone that applies")
    return " · ".join(asks) or None


# The MVP assumes flat ground (Ben, 2026-10-20): flat at the lot level and finished (with "assuming flat ground" on
# the height and stories rows and in the report). Height and stories are checked on it only where the lookup found
# the lot level (measure.flat_assumption_unsafe: a fall under 0.5 ft); a sloping lot, or one with no ground looked
# up, gives them needs review (2026-10-29). The spot-grade, terrain and regrade paths stay, behind this one switch:
# set it to False to bring the Ground row back.
FLAT_GROUND = True
GROUND_POINTS = 3          # the fewest looked-up ground points a fall is read from (the lookup reads every corner + 1)
ASSUMED_FLAT = "assuming flat ground"
ASSUMED_SOURCE = "assumed (flat ground, the MVP's rule)"


def ground_facts(state, lot_level, flat=None):
    """The facts the checker gets from the Ground row (the checker never sees where a fact came from). With the MVP's
    flat-ground switch on: flat at the lot level, finished, and said to be assumed. Otherwise: ground you set as
    finished, or ticked "No regrading near the house", counts as the finished grade the code measures from; ground
    only as it is (existing), unticked, gives height and stories needs review (spec C5)."""
    if FLAT_GROUND if flat is None else flat:
        return {"grade_is": "finished", "ground_is_flat": True, "grade_elevation": lot_level, "grade_from": None,
                "ground_assumed": "flat",
                # the looked-up fall, 0 too (level, known); None (unknown) removes one saved for an earlier lookup
                # (Draw sets every key given and drops each None: slope review round 1, a stale 0.0 passed)
                "ground_fall": state.get("ground_fall")}
    ground = state.get("ground") or {}
    kind = ground.get("kind") or "flat"
    finished = kind == "regrade" or bool(state.get("no_regrading"))
    out = {"grade_is": "finished" if finished else "existing", "ground_assumed": None}
    if kind == "flat":
        out.update(ground_is_flat=True, grade_elevation=lot_level, grade_from=None)
    else:
        out.update(ground_is_flat=None, grade_elevation=None,     # the facts say which points: never the ui state
                   grade_from={"terrain": "terrain", "regrade": "finished_spots"}.get(kind, "spot"))
    return out


# the box's own choices that Gordium fills in (the use, the street, the corner lot): the architect's word only once
# changed (their source then ENTERED); left as they were, never "confirmed by you" (fact_sources, source_lines)
BOX_DEFAULTS = ("use", "street", "corner_lot")
UNTOUCHED = "default, not changed by you"


def fact_sources(state, today, confirmed):
    """Every fact the box set, as {value, source, confirmed_by, date}: saved in the .3dm beside the facts and
    shown in the panel and the report. `confirmed`: the architect pressed Draw (the district needs its own tick).
    A box default the architect left as it was (BOX_DEFAULTS) is confirmed by no one: pressing Draw is not saying
    yes to a dropdown never opened (the architect's review, 2026-10-28: "Use: One-family dwelling, detached ·
    suggested by Gordium · confirmed by you" for a use never changed)."""
    by = "you" if confirmed else None
    ground = state.get("ground") or {}
    kind = ground.get("kind") or "flat"

    def fact(value, source, who=by):
        return {"value": value, "source": source, "confirmed_by": who, "date": today}

    def chosen(key):                   # a box default: the architect's only once changed, or ticked "I checked this"
        # (review round 1 of panel-wording, P2: a street ticked as checked read "default, not changed by you")
        # (the corner answer sits on the street's row, ROW_OF: that row's tick confirms it too; round 2, P3)
        row = ROW_OF.get(key + "_lot", key) if key == "corner" else key
        mine = state.get(key + "_source") == ENTERED or row in (state.get("checked") or [])
        return by if mine else None

    city = (" · " + IN_CITY_SAID.format(date=state["city_by_hand"])) if state.get("city_by_hand") else ""
    return {     # (the architect's Yes, by hand, on the address's source: shown in the panel and report, round 12)
        "address": fact(state.get("address") or None,     # (an earlier Draw's Yes, read back, never twice)
                        (state.get("address_source") or ENTERED).split(" · " + IN_CITY_SAID.split(" (")[0])[0] + city),
        "zone": fact(state.get("zone"), state.get("zone_source") or ENTERED,
                     by if state.get("district_confirmed") else None),
        "use": fact(state.get("use_name") or state.get("use"), state.get("use_source") or SUGGESTED, chosen("use")),
        # the follow-up answers (Ben, 2026-10-25): each saved as entered by you, and what the use itself says,
        # shown in the panel and the report (exactly the facts answers_applied sends the checker)
        **follow_up_sources(state, fact),
        # the size, then where it came from, once ("Lot: 6,570 sf · the tax map (±2 ft, approximate) · confirmed…")
        "lot": fact(lot_size(state.get("lot_area")), lot_source(state.get("lot_surveyed"), state.get("lot_source"))),
        # the street's name only when it may be kept (the City's roads may not: "street_name_saved" then None, and
        # the address's street, a kept fact, says it instead)
        "street": fact(street_name({**state, "street_name": state.get("street_name_saved")})
                       if "street_name_saved" in state else street_name(state),
                       state.get("street_source") or SUGGESTED, chosen("street")),
        "corner_lot": fact({None: None, False: "no, one street", True: "yes, two streets"}[state.get("corner_lot")],
                           state.get("corner_source") or SUGGESTED, chosen("corner")),
        # with the MVP's flat ground, an assumption, credited to no service and confirmed by no one
        # (whether that decides height and stories is the measuring's: measure.flat_assumption_unsafe)
        "ground": (fact("assumed flat" + (f" (the looked-up ground falls about {state['ground_fall']:g} ft across the "
                        "lot)" if state.get("ground_fall") is not None else " (ground levels not read in full)"),
                        ASSUMED_SOURCE, None) if FLAT_GROUND else
                   fact(ground_text(ground) + (" · no regrading near the house" if state.get("no_regrading") else ""),
                        "as drawn" if kind == "flat" else ground.get("source") or
                        ("picked by you" if kind == "terrain" else "placed by you"))),
    }


def follow_up_sources(state, fact):
    """The sources of the facts the box sets after Use (answers_applied's): each answer to a question asked,
    "entered by you", and each fact the use says, IMPLIED_SOURCE. An answer kept but not asked keeps its saved
    source (sources_kept)."""
    zone, use, options = state.get("zone"), state.get("use"), state.get("options")
    facts, answered = answers_applied({}, state.get("answers"), zone, use, options)
    return {k: fact({True: "yes", False: "no"}.get(v, v), ENTERED if k in answered else IMPLIED_SOURCE)
            for k, v in facts.items()}


def sources_kept(saved, facts):
    """The saved sources Draw keeps before adding the box's own (fact_sources): of the facts the box can ask (BOX_ASKS)
    and the use details (DEFERRED_FACTS, answered in the panel's row dialog, which saves their "entered by you":
    row_sources), only those still set in `facts` (the facts after Draw: an answer kept, unshown, keeps its source);
    a fact Draw unset or dropped (a blank, what the old use said) loses its source with it. Those Draw asks or the use
    says are given their source again by fact_sources."""
    return {k: v for k, v in (saved or {}).items()
            if k not in BOX_ASKS + DEFERRED_FACTS or (facts or {}).get(k) is not None}


def district_confirmed(mode, zone_fact, zone):
    """Whether "I confirm" starts ticked: never on a new project (GordiumStart); on an existing one only if this
    same district was confirmed at an earlier Draw (its saved source says who confirmed it)."""
    zone_fact = zone_fact or {}
    return mode != "start" and bool(zone_fact.get("confirmed_by")) and zone_fact.get("value") == zone


# Names these functions call from the host_core modules that call back into this one. They are
# imported last, after every definition above, so the modules load in any order.
from .lookup import GUIDE_PREVIEW  # noqa: E402
from .start_box import (  # noqa: E402
    CHECKABLE, ENTERED, IN_CITY_SAID, ROW_OF, SAVED_SAYS, SUGGESTED, ground_text, lot_size, lot_source)
