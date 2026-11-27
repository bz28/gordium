"""What the rebuilt results pane reads beyond today's fields (the UI polish design Ben approved on 2026-11-23,
changes C1 to C9; docs/revit/checker_ui_data.md says each field). Presentation only, plain code, no AI.

Nothing here reads or changes a status, a verdict or a figure: every field is new, set beside the old ones (so the
add-in on main reads exactly what it read before), and each is worked out from what the answer already says (the
row's causes, its reason, its rule's sources, the law's contents list), never guessed. Where something can't be told,
the field is left out or says so, never filled in.

New fields on an item:

  asks        (C1, C2, C3, C5) on a row in review: one entry per thing it asks of the architect, in order, each
              {kind, key, headline, why, elements, field?, fields?, measure?, rooms?, questions?, depends_on?}.
              depends_on: on a follow-up question, the question it hangs on (depends_on() below).
              kind: "mark" (state a fact or set a mark: `field` names the description's field that answers it, so a
              host names its own mark; a field starting "facts." or "building." is a project question), "fix_model"
              (the model, as `why` says: `elements` the element ids to show), "survey" (the lot needs a survey),
              "measure" (Gordium doesn't read or measure this yet: a person works it out by hand), "decide" (a person
              decides: a flag rule, a reading to confirm, the law's own review condition), "open_question" (the law
              reads more than one way and the readings disagree). headline: what to do, in a few words; why: the
              checker's words for it, whole (today's cause words, or one part of the row's reason: a zoning
              row's reason is read as data, its `stops` (present.reason_parts), never from its words). key: rows sharing a key ask
              the same thing.
  in_code     (C6) on a row of a rule: where it is in its document, {document, file, chapter, chapter_title, section,
              section_title, piece, piece_title}: the chapter (an ICC book) or article (the zoning chapter), the
              section as the book's contents list it ("1006", "§325-8"), and the part the rule's first quote is in
              ("1006.2.1", "Table 1006.2.1", "§325-8A"). A part not known is null.
  rule_name   (C8) on a row of a rule: the rule's name without its part and without the law and section in it
              ("Two exits over 10 occupants or a 75-ft common path, I-4"; the section is in in_code).
  limit_words (C9) on a row whose limit isn't worked out yet ("—"): "Limit depends on dwelling units", naming the
              facts or measures the limit reads that the row has no value for.

New field on the view:

  contents    (C7) one entry per law in the answer (zoning first): {key, document, file, title, chapters: [{number,
              title, coverage, sections: [{number, title, coverage, pieces: [{id, title, coverage, rules}]}]}]}, every
              chapter (article) and section of the document from its contents list (2_extracted_text/*.contents.jsonl),
              with Gordium's coverage: "rules" (rules check it), "flag" (flag rules raise it for a person), "not_checked_yet"
              (labeled rule or flag, no rules yet), "not_for_checking" (brought in, nothing in it to check: a definition,
              a reference) or "not_brought_in" (not extracted: Gordium hasn't read it).
"""

import ast
import re

from rule_format import formula

from design_checker import code_scope, occupant_load, panel_data, present

MARK, FIX_MODEL, SURVEY, DECIDE, MEASURE, OPEN_QUESTION = ("mark", "fix_model", "survey", "decide", "measure",
                                                         "open_question")
KINDS = (MARK, FIX_MODEL, SURVEY, DECIDE, MEASURE, OPEN_QUESTION)

# the headline of a project question, by the field that answers it
FIELD_HEADLINES = {
    "building.occupancy_groups": "Set the occupancy group",
    "building.sprinkler_system": "Set the sprinkler system",
    "building.egress_balcony_increase_taken": "Say whether the design takes the egress balcony travel increase",
    "building.building_has_atrium": "Say whether the building has an atrium",
    "building.assembly_fixed_seating": "Say whether any room has fixed assembly seating",
    "building.special_egress_spaces": "Say whether the building has special egress spaces (boiler or electrical rooms, malls…)",
    "building.merchandise_pads": "Say whether the store has merchandise pads",
    "building.r2_sleeping_units": "Say whether the Group R-2 units are all sleeping units, all dwelling units, or both",
    "building.emergency_escape_openings_1031": "Say whether every sleeping room has an emergency escape opening (1031)",
    "building.occupied_outdoor_areas": "Say whether the occupants use outdoor areas (yards, patios, roofs: 1004.7)",
    "building.ambulatory_care_facility": "Say whether the building is or holds an ambulatory care facility (Table 1020.3)",
    "building.corridors_within_dwelling_units": "Say whether any corridor is inside a dwelling or sleeping unit",
    "building.emergency_voice_alarm_system": "Say whether the whole building has an emergency voice/alarm communication system (907.5.2.2)",
    "building.other_level_egress_into_corridors": "Say whether another level's occupants reach the corridors",
    "doors[].leaves": "Set each door type's leaves (a pair with a mullion: 1 only at the narrower leaf's clear width)",
    "facts.corner_lot": "Is the lot on two streets? (Corner lot, §325-19C)",
    "facts.lot_surveyed": "Say whether the lot outline is from a survey",
    "facts.ground_is_flat": "Say whether the ground is flat",
    "facts.accessory_dwelling_unit": "Is there an ADU on the lot?",
    "facts.home_occupation": "Is a home business planned? (§325-3B)",
    "building.separate_means_of_egress": "Does each unit have a separate means of egress?",
    "building.townhouse_units": "Are the units townhouse units?",
    "building.stories_above_grade_plane": "Set the stories above grade plane",
    "facts.use": "Set the building's use",
    "facts.abuts_r1_district": "Does the lot abut R-1a or R-1b land? (§325-19E)",
    "facts.stream_near_lot": "Is a stream or inlet within 20 ft of the lot? (§325-26)",
    "facts.adu_detached": "Is the ADU detached (its own building)?",
    "facts.adu_existing_building": "Is the detached ADU in an accessory building that already exists?",
    "facts.conversion": "Is it made by converting an existing building? (§325-3B)",
    "facts.primary_buildings_same_use": "Does every primary building hold the lot's use?",
}
# A follow-up question hangs on another: its parent is the fact the setup already waits on before it asks it
# (host_core.facts.ROW_ONLY_FACTS: "is the ADU detached?" only once "is there an ADU?" is answered). The answers to
# the parent that make the follow-up moot (every rule reading it then doesn't apply: its applies_when is false,
# test_ui_data checks each against the rules) are below; a parent missing here (the garage's car count, whose limit
# is the chart's) holds its follow-up back but never makes it moot.
MOOT_WHEN = {"adu_detached": [False], "adus_on_parcel": [False], "adu_bedrooms": [False],
             "adu_existing_building": [False],          # an attached ADU is in no accessory building
             "adu_floor_area": [True], "primary_floor_area": [True]}    # §325-28's size limit is an attached ADU's


def depends_on(field) -> dict | None:
    """{"field": the parent question's field, "moot_if"?: [its answers that make this one moot]} for a follow-up
    question's field ("facts.adu_detached"), else None. The pane holds the follow-up back until the parent is
    answered, and drops it once the parent's answer is one of moot_if."""
    from design_checker.host_core.facts import ROW_ONLY_FACTS
    if not isinstance(field, str) or not field.startswith("facts."):
        return None
    fact = field[len("facts."):]
    if fact not in ROW_ONLY_FACTS:
        return None
    out = {"field": f"facts.{ROW_ONLY_FACTS[fact]}"}
    if fact in MOOT_WHEN:
        out["moot_if"] = list(MOOT_WHEN[fact])
    return out


# the facts the site's own questions answer, by the measuring's stop that asks for them (model_measurement/stops.py)
SITE_STOPS = {"corner_unknown": ["corner_lot"], "two_streets": ["corner_lot"], "one_street_or_two": ["corner_lot"],
              "survey_unknown": ["lot_surveyed"], "ground_unknown": ["ground_is_flat"]}
SURVEY_STOPS = ("not_surveyed",)
OPEN_STOPS = ("readings_differ", "all_street", "rear_on_street", "no_side_line", "no_rear_line",
              "corner_outside_residential", "lines_unclear")
# the questions a by-hand check asks, for the measures Gordium doesn't measure yet, or couldn't on this model
# (strings.md, Checker reasons)
BY_HAND_QUESTIONS = {
    "space_egress_through_locked_room": "Check by hand: does the path pass through a room that can be locked?",
    "space_egress_through_other_room": "Check by hand: does the path pass through another room?",
    "space_egress_through_electrically_locked_lobby":
        "Check by hand: does the path pass through an electrically locked lobby?",
    "space_egress_through_kitchen_storage":
        "Check by hand: does the path pass through a kitchen, storage room or similar space?",
    "space_egress_sleeping_through_sleeping_or_toilet":
        "Check by hand: does the path from a sleeping area pass through another sleeping area or a toilet room?",
    "story_first_above_or_below_grade": "Check by hand: is this the first story above or below grade?",
    "story_second_above_grade_plane": "Check by hand: is this the second story above grade plane?",
    "story_fourth_or_higher_above_grade_plane": "Check by hand: is this the fourth story above grade plane or higher?",
    "story_dwelling_units": "Check by hand: how many dwelling units are on this story?",
    "space_exit_remoteness_ratio": "Check by hand: are the exits far enough apart (1/2 or 1/3 of the diagonal)?",
    "exit_remoteness_ratio": "Check by hand: are the exits far enough apart (1/2 or 1/3 of the diagonal)?",
}
JUDGMENT = "The code leaves this to judgment: read the words and decide"
JUDGMENT_WORDS = "A judgment call: a person decides (this rule is a flag)."   # project_report.report's words
PERSON_CHECKS = "A person checks this (Gordium doesn't decide it): "            # egress.FLAG_WHY's start


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _clause_head(text: str) -> str:
    """A clause's words up to its first colon, its brackets left out, as a headline ("The street side isn't given";
    "The ground level doesn't meet the buildings" from "the ground level (0.0 ft) doesn't meet the buildings (they
    run from 2.25 to 40.25 ft): check the ground level"). The clause whole is the ask's why."""
    head = text.split(": ")[0]
    while True:
        cut = re.sub(r"\s*\([^()]*\)", "", head)
        if cut == head:
            break
        head = cut
    return _cap(" ".join(head.split()).rstrip(".")) or _cap(text.strip())


# ---- asks ---------------------------------------------------------------------------------------------------

def _measure_name(measure: str, kind: str | None) -> str:
    from design_checker.each_part import _words
    return _words({"for_each": kind}, measure)


def _fact_headline(fact: str) -> str:
    from design_checker.host_core.facts import STATED_FACTS
    field = f"facts.{fact}"
    if field in FIELD_HEADLINES:
        return FIELD_HEADLINES[field]
    said = STATED_FACTS.get(fact)
    if said and said[1] == "yes_no":
        return said[0]                                  # the question as the Setup form asks it
    return "Enter " + (said[2] if said else fact.replace("_", " "))


def _fact_ask(fact: str, why: str, elements=()) -> dict:
    return {"kind": MARK, "key": f"field:facts.{fact}", "headline": _fact_headline(fact), "why": why,
            "elements": list(elements), "field": f"facts.{fact}"}


def _from_cause(c: dict, rule_kind: str | None) -> dict:
    """One of panel_data's (or present.law_causes') causes as an ask: the same words as its why, a headline, the
    field that answers it (C1: a building measure by the fact it is worked out from)."""
    from model_measurement.routes.stops import STOPS
    key, words = str(c.get("key") or ""), str(c.get("words") or "")
    base = {"key": key, "why": words, "elements": list(c.get("elements") or [])}
    for k in ("rooms", "questions", "measure"):
        if k in c:
            base[k] = c[k]
    measure = c.get("measure")
    kind = c.get("kind")
    if kind == "mark":
        if key.startswith("fact:") and isinstance(measure, str):
            field = code_scope.field_of(measure) or c.get("field")
            name = _measure_name(measure, rule_kind)
            return {**base, "kind": MARK, "key": f"field:{field}", "field": field,
                    "headline": FIELD_HEADLINES.get(field) or f"Set the {name}"}
        stated = STOPS["stated_not_given"].split("{what}")[0]
        if key.startswith("mark:") and measure in panel_data.MEASURE_FIELDS:   # a measure a host's mark states
            f = panel_data.MEASURE_FIELDS[measure]
            return {**base, "kind": MARK, "key": f"field:{f}", "field": f, "headline": FIELD_HEADLINES[f]}
        if key.startswith("mark:") and occupant_load.FUNCTION_STATED in words:   # a room's function: its own mark
            return {**base, "kind": MARK, "key": f"field:{occupant_load.FUNCTION_FIELD}",
                    "field": occupant_load.FUNCTION_FIELD, "headline": "Set the room's function"}
        # a corridor's load not bounded for want of the building's other-levels fact: that fact's own mark (a card to
        # set), never "work it out by hand" (the Revit-fields PR for groups 4 and 5 gave it one)
        if key.startswith("mark:") and occupant_load.CORRIDOR_NOT_RULED_OUT.split(" (")[0] in words:
            f = occupant_load.OTHER_LEVELS_FIELD
            return {**base, "kind": MARK, "key": f"field:{f}", "field": f, "headline": FIELD_HEADLINES[f]}
        if key.startswith("mark:") and isinstance(measure, str) and stated in words:
            name = _measure_name(measure, rule_kind)
            return {**base, "kind": MEASURE,
                    "headline": f"Work out the {name} by hand: Gordium has no field for it yet"}
        if key.startswith("mark:") and isinstance(measure, str):
            return {**base, "kind": MARK, "headline": f"Mark the {_measure_name(measure, rule_kind)} in the model"}
        out = {**base, "kind": MARK, "headline": _clause_head(words) or "Set the mark this asks for"}
        for k in ("field", "fields"):
            if k in c:
                out[k] = c[k]
        return out
    if kind == "fix_model":
        if key.startswith("rooms:"):
            return {**base, "kind": FIX_MODEL, "headline": _clause_head(words)}
        if key.startswith("model:") and isinstance(measure, str):
            return {**base, "kind": FIX_MODEL,
                    "headline": f"Fix the model so the {_measure_name(measure, rule_kind)} can be measured"}
        return {**base, "kind": FIX_MODEL, "headline": _clause_head(words) or "Fix the model"}
    if kind == "measure_by_hand":
        if isinstance(measure, str) or key.startswith("gap:"):
            m = measure if isinstance(measure, str) else key.rsplit(":", 1)[-1]
            return {**base, "kind": MEASURE, "headline": BY_HAND_QUESTIONS.get(m) or
                    f"Measure the {_measure_name(m, rule_kind)} by hand: Gordium doesn't measure it yet"}
        return {**base, "kind": MEASURE, "headline": _clause_head(words) or "Check this by hand"}
    # a person decides
    if key == "flag":
        return {**base, "kind": DECIDE, "headline": JUDGMENT}
    if key.startswith("question:"):
        return {**base, "kind": OPEN_QUESTION, "headline": "An open question about the law decides this"}
    if key.startswith(("reading:", "has_none:")):
        return {**base, "kind": DECIDE, "headline": "Confirm the reading this depends on"}
    if key.startswith("review_when:"):
        return {**base, "kind": DECIDE, "headline": "The law asks a person to decide here"}
    if words.startswith(PERSON_CHECKS):
        return {**base, "kind": DECIDE, "headline": "Check this by hand: a person decides it"}
    if words == JUDGMENT_WORDS:
        return {**base, "kind": DECIDE, "headline": JUDGMENT}
    return {**base, "kind": DECIDE, "headline": "A person decides this: see why"}


# what a row's own reason part (present.reason_parts: not the measuring's) asks: (kind, headline)
ROW_PARTS = {
    "depends": (OPEN_QUESTION, "An open question about the law decides this"),   # one per question it names
    "readings": (OPEN_QUESTION, "The readings of the law give different answers here"),
    "tax_map": (SURVEY, "Lot lines from a survey settle this (the tax map is good to 2 ft)"),
    "scope": (FIX_MODEL, "Objects on the lot aren't in the check"),
    "named": (DECIDE, "Confirm this reading with the zoning office"),
    "reading_applied": (DECIDE, "Confirm the reading Gordium used"),
    "height_bonus": (DECIDE, "The §325-16C height bonus may raise this limit"),
    "unsettled": (DECIDE, "A person decides this: see why"),
    "flag": (DECIDE, JUDGMENT),
    "review_when": (DECIDE, "The law asks a person to decide here"),
    "review": (DECIDE, "A person decides this: see why"),
    "facts_conflict": (MARK, "Correct the facts that disagree"),
    "words": (DECIDE, "A person decides this: see why"),
    "looked_up": (MARK, "Confirm or change the looked-up fact"),
}
NO_ASK_PARTS = ("use_detail",)          # "Answer when you plan the interior": when to answer; the parts after it ask


def _pick_keys() -> dict:
    """{stop code: its pick's key}: one key for one pick, whether the row's hint or the measuring's stop asks for it,
    read from present's own words for each pick (PICK_MAIN_WHY: the main building's; PICK_ADU_WHYS: the ADU's
    building's), never a second list."""
    from model_measurement.stops import parts_of
    out = {c: "pick:main_building" for c, _, _ in parts_of(present.PICK_MAIN_WHY)}
    out.update({c: "pick:adu_building" for w in present.PICK_ADU_WHYS for c, _, _ in parts_of(w)})
    return out


HINT_KEYS = {present.PICK_MAIN: "pick:main_building", present.PICK_ADU: "pick:adu_building"}
# the measuring's stops that are no fault of the model: a reading Gordium can't follow yet, or the city's files
MEASURE_STOPS = ("reading_unknown", "sloped_ground", "curved_surface", "curved_edge")
DECIDE_STOPS = ("law_missing",)


def _is_pick(key: str) -> bool:
    """Whether the measuring's stop asks the architect to pick something (the main building, the street side):
    its own template says "pick" (model_measurement/stops.py's table, by its key)."""
    from model_measurement.stops import STOPS
    return bool(re.search(r"(^|: )pick ", STOPS.get(key, "")))


def _pick_head(key: str) -> str:
    """A pick's headline: what to pick, from the stop's own template ("Pick the main building")."""
    from model_measurement.stops import STOPS
    m = re.search(r"(?:^|: )(pick [^(:;{]*)", STOPS.get(key, ""))
    return _cap(m.group(1).strip().rstrip(".")) if m else "Pick it again"


def _open_ids(site: dict | None, place) -> list[str]:
    """The site's building objects that aren't closed solids, by the place's own measuring (its _open_ids), else by
    the reader's own problems (each a stop: its key)."""
    from model_measurement.stops import parts_of
    buildings = [b for b in (site or {}).get("buildings") or [] if isinstance(b, dict) and "id" in b]
    finder = getattr(place, "_open_ids", None)
    if finder is not None:
        try:
            return [str(i) for i in finder(buildings)]
        except Exception:
            pass
    return [str(b["id"]) for b in buildings
            if any(c == "open_solid" for p in b.get("problems") or [] for c, _, _ in parts_of(p))]


def _named(site: dict | None, what: str, among: list[str]) -> list[str]:
    """The ids, among `among`, of the objects the measuring names `what` (its name, else its id: its _called)."""
    called = {str(b["id"]): str(b.get("name") or b["id"]) for b in (site or {}).get("buildings") or []
              if isinstance(b, dict) and "id" in b}
    return [i for i in among if called.get(i) == what]


def _stop_facts(code: str, ctx: dict) -> list[str]:
    """The facts a measuring's stop asks the architect for: the site's own questions (SITE_STOPS), else the place's
    table of what each stated fact's absence stops with (its measuring's ASK)."""
    ask_of = getattr(ctx.get("place"), "ASK", None) or {}
    return SITE_STOPS.get(code) or [f for f, k in ask_of.items() if k == code]


def _part_asks(part: dict, item: dict, ctx: dict, objects: list[str], asked: set) -> list[dict]:
    """What one part of a row's reason asks, by its code, never by its words: a measuring's stop by its key (a fact
    the site's questions or the place's table ask for, a survey, an open question, a pick, the model), else the
    row's own part (ROW_PARTS). Every ask carries the row's objects, narrowed only where a better set is known (the
    walls that aren't closed solids)."""
    from model_measurement.stops import STOPS
    code, params, words = part["code"], part.get("params") or {}, part["words"]
    if code in STOPS:
        facts = _stop_facts(code, ctx)
        if facts:
            out = []
            for f in facts:
                if f not in asked:
                    asked.add(f)
                    out.append(_fact_ask(f, words, objects))
            return out
        if code in SURVEY_STOPS:
            return [{"kind": SURVEY, "key": f"stop:{code}", "headline": "The lot area needs a lot outline from a survey",
                     "why": words, "elements": list(objects)}]
        if code in OPEN_STOPS:
            return [{"kind": OPEN_QUESTION, "key": f"stop:{code}:{words}", "headline": _clause_head(words),
                     "why": words, "elements": list(objects)}]
        if code == "open_solid":
            what = str(params.get("what") or "")
            ids = _named(ctx.get("site"), what, ctx.get("open_ids") or [])
            return [{"kind": FIX_MODEL, "key": f"stop:open_solid:{what}", "headline": f"“{what}” isn't a closed solid",
                     "why": words, "elements": ids or list(objects)}]
        if _is_pick(code):
            return [{"kind": MARK, "key": _pick_keys().get(code, f"stop:{code}"), "headline": _pick_head(code),
                     "why": words, "elements": list(objects)}]
        kind = MEASURE if code in MEASURE_STOPS else DECIDE if code in DECIDE_STOPS else FIX_MODEL
        return [{"kind": kind, "key": f"stop:{code}:{words}", "headline": _clause_head(words), "why": words,
                 "elements": list(objects)}]
    if code in NO_ASK_PARTS:
        return []
    if code == "looked_up" and params.get("fact"):
        # no field: the looked-up lot, street or ground is confirmed or changed in the site's own setup (Edit
        # site…), no one fact the description has
        return [{"kind": MARK, "key": f"looked_up:{params['fact']}", "headline": "Confirm or change the looked-up "
                 f"{params.get('name') or str(params['fact']).replace('_', ' ')}", "why": words,
                 "elements": list(objects)}]
    kind, headline = ROW_PARTS.get(code, ROW_PARTS["words"])
    if code == "depends" and params.get("questions"):
        return [{"kind": OPEN_QUESTION, "key": f"question:{q}", "headline": _clause_head(str(q)) or headline,
                 "why": str(q), "elements": list(objects)} for q in params["questions"]]
    out = {"kind": kind, "key": f"{code}:{item.get('id')}:{words}" if kind == DECIDE else f"{code}:{words}",
           "headline": headline, "why": words, "elements": list(objects)}
    if code == "facts_conflict":
        out["fields"] = [f"facts.{n}" for n in item.get("needs") or [] if isinstance(n, str)]
    return [out]


def _zoning_asks(item: dict, ctx: dict) -> list[dict]:
    """A zoning row's asks: each fact it waits on (its `needs`), then what each part of its reason asks, read from
    the parts as data (`stops`: present.reason_parts), never from the words. A part asking for a fact the row
    already asks for is that one ask. Every ask carries the row's objects (as its cause does), narrowed only where a
    better set is known."""
    objects = [o for o in item.get("objects") or [] if isinstance(o, str)]
    needs = [n for n in item.get("needs") or [] if isinstance(n, str)]
    parts = [p for p in item.get("stops") or [] if isinstance(p, dict)]
    why = str(item.get("reason") or "")
    out, asked = [], set()
    for n in needs:
        asked.add(n)
        mine = next((p["words"] for p in parts if n in _stop_facts(p["code"], ctx)), None)
        out.append(_fact_ask(n, mine or why, objects))
    for part in parts:
        out += _part_asks(part, item, ctx, objects, asked)
    hint = item.get("hint")                  # after the parts: a stop asking for the same pick is that one ask,
    if hint in HINT_KEYS:                    # under the hint's own headline (the button the row shows)
        same = next((a for a in out if a["key"] == HINT_KEYS[hint]), None)
        if same is not None:
            same["headline"] = hint.rstrip("…")
        else:
            out.append({"kind": MARK, "key": HINT_KEYS[hint], "headline": hint.rstrip("…"), "why": why,
                        "elements": list(objects)})
    if not out:
        out = [_from_cause(c, None) for c in item.get("causes") or []]
    return _deduped(out)


def _deduped(asks: list[dict]) -> list[dict]:
    """Each key once (its first), in order; the elements of a repeat added to the first."""
    out, by = [], {}
    for a in asks:
        if a["key"] in by:
            first = by[a["key"]]
            first["elements"] += [e for e in a["elements"] if e not in first["elements"]]
            continue
        by[a["key"]] = a
        out.append(a)
    return out


def _scope_field(fact: str) -> str:
    """The description's field for a fact the code choice reads: the `building` block's (code_scope.FACTS), else the
    lot facts'."""
    return f"building.{fact}" if fact in code_scope.FACTS else f"facts.{fact}"


def _scope_headline(fact: str) -> str:
    return FIELD_HEADLINES.get(_scope_field(fact)) or "Set " + code_scope.fact_words(fact)


def asks_of(item: dict, ctx: dict) -> list[dict] | None:
    """A row's asks (the module's note), or None for a row not in review."""
    if item.get("status") != present.REVIEW:
        return None
    if item.get("group") == present.LAW_GROUP:
        facts = (item.get("code_scope") or {}).get("ask_facts") if isinstance(item.get("code_scope"), dict) else None
        if facts:                    # which code governs: the facts its ask names, as data (code_scope.ask_facts)
            return [{"kind": MARK, "key": f"field:{_scope_field(f)}", "headline": _scope_headline(f),
                     "why": str(item.get("reason") or ""), "elements": [], "field": _scope_field(f)} for f in facts]
        kind = (ctx.get("rule_kinds") or {}).get(item.get("rule"))
        return _deduped([_from_cause(c, kind) for c in item.get("causes") or []])
    return _zoning_asks(item, ctx)


# ---- the rule's name and its limit ------------------------------------------------------------------------------

def rule_name(item: dict, rule: dict | None) -> str | None:
    """The rule's name without the law and section in it: its title less a last bracket naming its section
    ("… (BCNYS 1006.2.1)"); a zoning row's own name. None for a row of no rule."""
    if not item.get("rule"):
        return None
    if item.get("group") != present.LAW_GROUP:
        return item.get("name")
    title = (rule or {}).get("title")
    if not isinstance(title, str):
        return None
    section = ((item.get("code") or {}).get("section") or "").strip()
    m = re.search(r"\s*\(([^()]*)\)\s*$", title)
    if m and section and section in m.group(1):
        return title[:m.start()].strip()
    return title.strip()


def limit_words(item: dict, rule: dict | None, values: dict) -> str | None:
    """"Limit depends on dwelling units" for a zoning row whose limit isn't worked out ("—"): the facts or
    measures its limit (the right side of the comparison its measure is on) reads that have no value."""
    if item.get("required") != "—" or not isinstance((rule or {}).get("check"), str):
        return None
    from design_checker.check import plain_name
    from design_checker.host_core.facts import STATED_FACTS
    try:
        compares = present._compares(rule["check"])
    except Exception:
        return None
    measure = item.get("measure")
    node = next((c for c in compares if isinstance(c.left, ast.Name) and c.left.id == measure), None) or \
        (compares[0] if compares else None)
    if node is None:
        return None
    try:
        names = sorted(formula.names(ast.unparse(node.comparators[0])))
    except Exception:
        return None
    missing = [n for n in names if values.get(n) is None]
    if not missing:
        return None
    said = [STATED_FACTS[n][2] if n in STATED_FACTS else plain_name(n) for n in missing]
    said = list(dict.fromkeys(said))
    return "Limit depends on " + (said[0] if len(said) == 1 else ", ".join(said[:-1]) + " and " + said[-1])


# ---- adding them to the view ----------------------------------------------------------------------------------

def add(view: dict, *, rules_by_id: dict, laws: list[dict], site: dict | None, values: dict, place=None,
        place_folder=None, documents: dict | None = None) -> None:
    """Every new field onto the view's items, and the view's `contents` (the module's note). Never a crash: a field
    that can't be worked out is left out, the rest of the answer as it was."""
    from design_checker import contents as contents_mod
    law_rules = {(law["key"], r.get("id")): r for law in laws for r in law.get("rules") or [] if isinstance(r, dict)}
    rule_kinds = {r.get("id"): r.get("for_each") for law in laws for r in law.get("rules") or []
                  if isinstance(r, dict)}
    try:
        open_ids = _open_ids(site, place)
    except Exception:
        open_ids = []
    ctx = {"site": site, "place": place, "open_ids": open_ids, "rule_kinds": rule_kinds}
    try:
        books = contents_mod.books(laws, place_folder, documents)
    except Exception:
        books = {}
    for item in view.get("items") or []:
        law = item.get("group") == present.LAW_GROUP
        rule = law_rules.get((item.get("law_key"), item.get("rule"))) if law else rules_by_id.get(item.get("rule"))
        try:
            got = asks_of(item, ctx)
        except Exception:            # never a row in review without its asks: each cause as a person's to decide
            got = [{"kind": DECIDE, "key": str(c.get("key")), "headline": "A person decides this: see why",
                    "why": str(c.get("words") or ""), "elements": list(c.get("elements") or [])}
                   for c in item.get("causes") or []] if item.get("status") == present.REVIEW else None
        if got is not None:
            for a in got:                # a follow-up question names the one it hangs on
                parent = depends_on(a.get("field"))
                if parent is not None:
                    a["depends_on"] = parent
            item["asks"] = got
        try:
            name = rule_name(item, rule)
            if name:
                item["rule_name"] = name
        except Exception:
            pass
        try:
            words = None if law else limit_words(item, rule, values)
            if words:
                item["limit_words"] = words
        except Exception:
            pass
        try:
            where = contents_mod.in_code(item, rule, books)
            if where:
                item["in_code"] = where
        except Exception:
            pass
    by_law = {law["key"]: law.get("rules") or [] for law in laws}
    try:
        view["contents"] = contents_mod.listing(
            books, view.get("items") or [],
            rules_for=lambda key: list(rules_by_id.values()) if key == "zoning" else by_law.get(key) or [])
    except Exception:
        view["contents"] = []


def place_documents(folder) -> dict:
    """{file: its sources.yaml entry} of a place's own documents (the zoning chapter's title, for in_code)."""
    from pathlib import Path

    from rule_format.rulebook import load
    path = Path(folder) / "1_source_documents" / "sources.yaml"
    try:
        return {d["file"]: d for d in (load(path) or {}).get("documents") or [] if isinstance(d, dict) and "file" in d}
    except Exception:
        return {}
