"""The Building Code's sleeping rooms, as BCNYS 1031.2 reads them (section group 8a of
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md): the interior measuring's own sleeping rooms and
marked escape openings (design_checker.egress._escape_openings), each sleeping room then linked to what the
Building Code's own reading of the building already knows of it, with no new geometry:

- `sleeping_room_escape_openings`: how many emergency escape and rescue openings the description marks in it (the
  interior measuring's openings within it); the openings not read, not measured.
- `sleeping_room_fourth_or_higher`: its story's `story_fourth_or_higher_above_grade_plane`, the routes' story part
  of the room's own `level` (1031.2: "sleeping rooms below the fourth story above grade plane").
- `sleeping_room_story_one_exit`: yes where the room's story has one exit (its `story_exit_count` under two:
  1031.2 item 1, Group R-2 "in stories with only one exit or access to only one exit"); a story with two or more
  doesn't show that the room's occupants have access to more than one (each dwelling unit may reach only one, as
  Table 1006.3.4(1) permits: review round 1), so there it is no only where the routes show every way out of the
  room reaches two or more separate and distinct exits that surely lead the story out, through its own space and,
  where the building states no corridor is within a dwelling unit, the corridors only (the routes' space part,
  `exits_reached`: 1006.3, 202 COMMON PATH OF EGRESS TRAVEL, 1016.2.1), else not measured. A
  `confirm` the routes give the room's exit count is said beside it too.
- `sleeping_room_door_to_outside`: whether any door of the room (the routes' door parts whose sides name it) has
  outside on its other side (1031.2 exception 2: an exit door or exit access door that opens directly into a public
  way, yard, court or exterior egress balcony); no, only where every door of the description has both its sides
  read and none of the room's is to outside.

Each one the description or the routes don't give is not measured, with its reason: never a guess, so a rule
reading it needs review. A sleeping room is only a room the description states is one (`sleeping: true`), or an
enclosed space with no room drawn in it (the interior measuring's `maybe`, every row about it a review): never a
room the description says isn't one.

Section group 8d: which openings comply. Each escape-opening rule of the law carries its `limit`, the opening's own
requirement (rule_format/parts.py: the check is exactly "(<limit>) or <set-aside>", so the two can't drift). Each
opening is held to every such limit with the rulebook's own three-valued evaluator (rule_format.formula.evaluate):
it complies only where every limit is known true, it doesn't where any is known false, and otherwise it isn't known.
Then:

- `sleeping_room_compliant_openings`: how many openings in the room are known to comply; not measured where none
  is known to and one isn't known either way (or the openings, or the rules, aren't read).
- `opening_room_other_compliant` on each opening: another opening in its room is known to comply (yes), or every
  other is known not to (no, none other counting no); else not measured.

The limits are the rulebook's (never a size written in this code). Plain code, no AI.
"""

from rule_format import formula
from rule_format import parts as part_rules
from rule_format.parts import measure_kinds

KIND = "sleeping_room"
OPENINGS = "emergency_escape_opening"
OUTSIDE = "outside"
LINKED = {"sleeping_room_fourth_or_higher": ("story_fourth_or_higher_above_grade_plane", lambda v: v),
          "sleeping_room_story_one_exit": ("story_exit_count", lambda v: True if v < 2 else None)}
WHY = {
    "no_room": "the sleeping room {name} isn't one room of the description's (no room, or more than one, has its id)",
    "no_level": "the sleeping room {name} doesn't say which level it is on",
    "no_story": "the sleeping room {name}'s level {level} isn't a story the Building Code's routes read",
    "story_not_measured": "the sleeping room {name}'s story: {reason}",
    "openings_not_read": "the description's emergency escape and rescue openings aren't read",
    "doors_not_read": "the description's doors aren't read, so whether the sleeping room {name} has a door to "
                      "outside isn't known",
    "door_sides_not_read": "a door's sides aren't read, so whether the sleeping room {name} has a door to outside "
                           "isn't known",
    "two_exits": "the sleeping room {name}'s story has two or more exits, but whether its occupants have access to "
                 "more than one (not only one, as Table 1006.3.4(1) permits) isn't worked out: {why}",
    "opening_stray": "an emergency escape and rescue opening of the description is within no sleeping room read (none "
                     "named, a room not read, or one that can't be read), so it may be this room's",
    "room_id_shared": "the sleeping room {name}'s id is more than one room's, so which openings and doors are its "
                      "isn't known",
}
NEW_MEASURES = ("sleeping_room_escape_openings", *LINKED, "sleeping_room_door_to_outside")
# section group 8b: each escape opening carries its room's facts that decide whether 1031.2 requires it, so the size
# rules (1031.3, 1031.4) fail only an opening the law asks for (a rule reads only its own part's measures)
FROM_ROOM = {"opening_room_fourth_or_higher": "sleeping_room_fourth_or_higher",
             "opening_room_one_exit": "sleeping_room_story_one_exit",
             "opening_room_door_to_outside": "sleeping_room_door_to_outside"}
COMPLIES = "opening_room_other_compliant"           # section group 8d: on each opening
COUNT = "sleeping_room_compliant_openings"           # section group 8d: on each sleeping room


def _stray(parts, openings) -> bool:
    """An opening that may be any room's, as rule_format.parts.rows reads it: one that can't be read (not a mapping,
    no id, an id two parts share), or one within no part of a kind it may sit in (no `within`, a mistyped room, an id
    two parts share); one within a part of another such kind (a basement) is that part's."""
    from rule_format import parts as part_rules
    ids = part_rules._ids(parts)
    kind_of = {p["id"]: k for k, given in parts.items() if isinstance(given, list)
               for p in given if isinstance(p, dict) and isinstance(p.get("id"), str)}
    may = part_rules.registry()[OPENINGS].get("within", [])
    for o in openings:
        if not (isinstance(o, dict) and isinstance(o.get("id"), str) and o["id"].strip() and ids.get(o["id"]) == 1
                and isinstance(o.get("measures", {}), dict)):
            return True
        where = o.get("within")
        if not isinstance(where, str) or ids.get(where) != 1 or kind_of.get(where) not in may:
            return True
    return False


def _count(v) -> bool:
    """A whole count of exits, never negative (a hand-built story's null, text, true, NaN, 1.5 or -3 is none)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return v >= 0 and (isinstance(v, int) or (v - v == 0 and v.is_integer()))     # a float: finite and whole


def link(parts: dict, description, rules=None) -> None:
    """Add the four measures to every sleeping room part in `parts` (the routes' parts and the interior measuring's
    sleeping rooms and openings, together), in place; with the law's `rules`, which openings comply (8d)."""
    rooms = parts.get(KIND)
    if not isinstance(rooms, list):
        return
    given = description.get("rooms") if isinstance(description, dict) else None
    by_id = {}
    for r in given if isinstance(given, list) else []:
        if isinstance(r, dict) and isinstance(r.get("id"), str):
            by_id.setdefault(r["id"], []).append(r)
    stories = {}                                         # one story per id: two sharing one are no one story
    for s in parts.get("story") if isinstance(parts.get("story"), list) else []:
        if isinstance(s, dict) and isinstance(s.get("id"), str):
            stories.setdefault(s["id"], []).append(s)
    spaces = {}                                          # the routes' space parts, by (room id, level)
    for s in _list(parts.get("space")):
        if isinstance(s, dict) and isinstance(s.get("id"), str) and isinstance(s.get("within"), str):
            spaces.setdefault((s["id"], s["within"]), []).append(s)
    openings = parts.get(OPENINGS)
    doors = parts.get("means_of_egress_door")
    stray = isinstance(openings, list) and _stray(parts, openings)
    for part in rooms:
        if not isinstance(part, dict) or part.get("maybe"):
            continue                 # an enclosed space that may not be a room at all: every row of it needs review
        if not isinstance(part.get("not_measured", {}), dict):
            part["not_measured"] = {}    # reasons that can't be read: the link's own (its values are popped below)
        if not isinstance(part.setdefault("measures", {}), dict):
            continue                 # a room that can't be read: its rows say so (rule_format.parts)
        part.setdefault("not_measured", {})
        m, why = part["measures"], part["not_measured"]
        for k in NEW_MEASURES:           # the house measuring's "not measured yet" for these, and any value a part
            why.pop(k, None)             # arrives with: this link decides them, never a stale one beside its reason
            m.pop(k, None)
            if isinstance(part.get("confirm"), dict):      # nor a reading it arrives with for one (merge review)
                part["confirm"].pop(k, None)
        name = part.get("name") or part.get("id")
        pid = part.get("id")
        more = part.get("more") if isinstance(part.get("more"), dict) else {}
        rid = more.get("described_id", pid)       # the description's id (egress._escape_openings)
        same = by_id.get(rid, []) if isinstance(rid, str) else []
        # the openings marked in it (none counted where the id is more than one room's: review round 1)
        if len(same) > 1:
            why["sleeping_room_escape_openings"] = WHY["room_id_shared"].format(name=name)
        elif stray:
            why["sleeping_room_escape_openings"] = WHY["opening_stray"]
        elif isinstance(openings, list):
            m["sleeping_room_escape_openings"] = sum(1 for o in openings if isinstance(o, dict) and o.get("within") == pid)
        else:
            why["sleeping_room_escape_openings"] = WHY["openings_not_read"]
        # its story's place and exits
        level = same[0].get("level") if len(same) == 1 else None
        if len(same) != 1:
            reason = WHY["no_room"].format(name=name)
        elif not isinstance(level, str):
            reason = WHY["no_level"].format(name=name)
        elif len(stories.get(level, [])) != 1:
            reason = WHY["no_story"].format(name=name, level=level)
        else:
            reason = None
        for mine, (theirs, worked) in LINKED.items():
            story = stories[level][0] if reason is None else None
            given = story.get("measures") if story is not None else None
            raw = given.get(theirs) if isinstance(given, dict) else None
            known = isinstance(given, dict) and theirs in given
            if known and mine == "sleeping_room_story_one_exit" and not _count(raw):
                # a count that isn't a whole count (null, text, NaN, 1.5, -3): not known, never a crash or two exits
                why[mine] = WHY["story_not_measured"].format(name=name, reason=f"its {theirs} is not a number")
            elif known:
                value = worked(raw)
                if value is None and mine == "sleeping_room_story_one_exit":    # two or more exits: the room's reach
                    value, said = _reach(spaces.get((rid, level)) or [], name)
                    if value is None:
                        why[mine] = WHY["two_exits"].format(name=name, why=said)
                    else:
                        m[mine] = value
                        _own_map(part, "more")["exits_reached"] = said
                        confirm = _map(spaces[(rid, level)][0].get("confirm")).get("space_exit_count")
                        if confirm:                      # its routes run through the room it serves: the reading
                            _own_map(part, "confirm")[mine] = confirm
                elif value is None:                      # a story value that settles nothing (null): never a value
                    why[mine] = WHY["story_not_measured"].format(name=name, reason=f"its {theirs} is not given")
                else:
                    m[mine] = value
            elif story is not None:
                why[mine] = WHY["story_not_measured"].format(
                    name=name, reason=_map(story.get("not_measured")).get(theirs, "not measured"))
            else:
                why[mine] = reason
        # a door of its own to outside
        if len(same) > 1:
            why["sleeping_room_door_to_outside"] = WHY["room_id_shared"].format(name=name)
            continue
        if not isinstance(doors, list):
            why["sleeping_room_door_to_outside"] = WHY["doors_not_read"].format(name=name)
            continue
        sides = [(d["more"].get("sides") if isinstance(d.get("more"), dict) else None)
                 for d in doors if isinstance(d, dict)]
        if any(not isinstance(s, list) for s in sides) or len(sides) != len(doors):
            if any(isinstance(s, list) and rid in s and OUTSIDE in s for s in sides):
                m["sleeping_room_door_to_outside"] = True
            else:
                why["sleeping_room_door_to_outside"] = WHY["door_sides_not_read"].format(name=name)
            continue
        m["sleeping_room_door_to_outside"] = any(rid in s and OUTSIDE in s for s in sides)
    _to_openings(rooms, openings)
    _compliance(parts, rooms, openings, rules)


def _when(rule) -> str:
    w = rule.get("applies_when")
    return " ".join(w.split()) if isinstance(w, str) else repr(w)


def limits(rules) -> list[str]:
    """Every escape-opening rule's `limit` (section group 8d), in the rulebook's order. None at all (so no opening is
    known to comply) where one such rule has no limit (review round 1 of 8d: never count an opening compliant past a
    rule whose requirement isn't known), or where any such rule's `applies_when` isn't word for word the one of the
    rules that count compliant openings (1031.2's): a limit is held to every opening only because its rule applies
    wherever 1031.2 does (review round 2 of 8d: a narrower rule held where it doesn't apply would be a wrong fail)."""
    rules = [r for r in rules or [] if isinstance(r, dict)]
    over = [r for r in rules if r.get("for_each") == OPENINGS]
    counting = [r for r in rules if isinstance(r.get("check"), str) and COUNT in r["check"]]
    if not over or any(not isinstance(r.get("limit"), str) for r in over):
        return []
    if any(r.get("within") != KIND for r in over):       # review round 4: a rule held within another kind (a
        return []                                         # basement's) isn't a sleeping room opening's requirement
    if any(part_rules.rule_problems(r) for r in over + counting):   # review round 3: a rule its own validation
        return []                                                     # refuses (a drifted limit) never counts
    if len({_when(r) for r in over + counting}) != 1:
        return []
    return [r["limit"] for r in over]


def complies(opening: dict, held: list[str]):
    """True where every limit is known true of the opening's own measures, False where any is known false, else None
    (never compliant on an unknown). An opening whose measures aren't a mapping, or that gives a reading to confirm
    (`confirm`) or named readings (`readings`) for a figure a limit reads, isn't known either way: its rows never pass
    on those (review round 2 of 8d)."""
    kinds = measure_kinds(OPENINGS)
    values = opening.get("measures") if isinstance(opening, dict) else None
    if not isinstance(values, dict):
        return None
    read = set().union(*(formula.names(t) for t in held)) if held else set()
    for extra in ("confirm", "readings"):
        given = opening.get(extra)
        if given is not None and (not isinstance(given, dict) or read & set(given)):
            return None
    answers = []
    for text in held:
        try:
            answers.append(bool(formula.evaluate(text, values, kinds)))
        except (formula.MissingMeasure, formula.EvaluationError, formula.FormulaError, ArithmeticError):
            answers.append(None)
    if False in answers:
        return False
    return True if held and all(a is True for a in answers) else None


def _missing(opening, held) -> list[str]:
    """The figures an opening doesn't give that its limits read (for a reason a person can act on)."""
    values = opening.get("measures") if isinstance(opening, dict) else None
    if not isinstance(values, dict):
        return []
    unsure = [t for t in held if complies(opening, [t]) is None]       # only the limits it isn't known on
    return sorted({n for t in unsure for n in formula.names(t)} & set(measure_kinds(OPENINGS)) - set(values))


def _unknown_why(answers, held) -> str:
    names = [f"{o.get('name') or o.get('id')} ({', '.join(_missing(o, held)) or 'a reading to confirm'})"
             for o, a in answers if a is None and isinstance(o, dict)]
    return ("whether its escape openings comply isn't known: " + "; ".join(names)) if names else \
        "whether its escape openings comply isn't known (one of them can't be read)"


def _compliance(parts, rooms: list, openings, rules) -> None:
    held = limits(rules)
    by_room, unread = {}, set()
    good, _, doubtful = part_rules._read(parts, OPENINGS, part_rules._ids(parts)) if isinstance(openings, list) \
        else ([], [], set())
    anywhere = any(d is part_rules.ANYWHERE for d in doubtful) or _stray(parts, good or [])
    unread = {d for d in doubtful if isinstance(d, str)}
    for o in good or []:
        by_room.setdefault(o.get("within"), []).append(o)
    good_ids = {id(o) for o in good or []}
    for r in rooms:
        if not isinstance(r, dict) or r.get("maybe") or not isinstance(r.get("measures"), dict) \
                or not isinstance(r.get("not_measured"), dict):
            continue                             # a room link left alone (it can't be read): its rows say so
        m, why = r["measures"], r["not_measured"]
        why.pop(COUNT, None)
        m.pop(COUNT, None)
        if not isinstance(openings, list):
            why[COUNT] = WHY["openings_not_read"]
            continue
        if not held:
            why[COUNT] = "the law's escape-opening limits aren't read"
            continue
        if "sleeping_room_escape_openings" not in m:            # its openings can't be told apart (a shared id)
            why[COUNT] = why.get("sleeping_room_escape_openings", "its openings aren't known")
            continue
        if not isinstance(r.get("id"), str):
            why[COUNT] = "the sleeping room's id isn't text, so which openings are its isn't known"
            continue
        pairs = [(o, complies(o, held)) for o in by_room.get(r["id"], [])]
        answers = [a for _, a in pairs]
        if anywhere or r.get("id") in unread:     # an opening that may be in it can't be read: never counted as none
            answers.append(None)
        if True in answers or None not in answers:
            m[COUNT] = answers.count(True)
        else:
            why[COUNT] = _unknown_why(pairs, held)
    for o in openings if isinstance(openings, list) else []:
        if not isinstance(o, dict) or not isinstance(o.get("measures", {}), dict) \
                or not isinstance(o.get("not_measured", {}), dict):
            continue
        m, why = o.setdefault("measures", {}), o.setdefault("not_measured", {})
        why.pop(COMPLIES, None)
        m.pop(COMPLIES, None)
        if not held:
            why[COMPLIES] = "the law's escape-opening limits aren't read"
            continue
        where = o.get("within") if isinstance(o.get("within"), str) else None
        others = [complies(x, held) for x in by_room.get(where, []) if x is not o]
        if anywhere or where is None or where in unread or id(o) not in good_ids:
            others.append(None)
        if True in others:
            m[COMPLIES] = True
        elif None not in others:
            m[COMPLIES] = False
        else:
            why[COMPLIES] = "whether another escape opening in its room complies isn't known"


def _to_openings(rooms: list, openings) -> None:
    """Copy each sleeping room's four facts onto the escape openings within it (FROM_ROOM): its value, or its reason
    for having none; an opening within no sleeping room read (or a `maybe` one) gets neither, so its rows need review."""
    if not isinstance(openings, list):
        return
    by_id = {}
    for r in rooms:
        if isinstance(r, dict) and isinstance(r.get("id"), str):
            by_id.setdefault(r["id"], []).append(r)
    for o in openings:
        if not isinstance(o, dict):
            continue
        if isinstance(o.get("measures"), dict):            # the room's facts are only ever the room's: none given
            for mine in FROM_ROOM:                         # by the opening itself stands (review of 4d2cd872)
                o["measures"].pop(mine, None)
        if not isinstance(o.setdefault("measures", {}), dict) or not isinstance(o.setdefault("not_measured", {}), dict):
            continue                              # an unreadable opening: its rows say so (rule_format.parts)
        m, why = o["measures"], o["not_measured"]
        where = o.get("within")
        same = by_id.get(where, []) if isinstance(where, str) else []
        room = same[0] if len(same) == 1 and not same[0].get("maybe") else None
        if room is not None and not (isinstance(room.get("measures"), dict)
                                     and isinstance(room.get("not_measured", {}), dict)):
            room = None                                    # a room that can't be read gives its openings nothing
        if isinstance(o.get("confirm"), dict):             # a reading of the room's is only ever the room's
            for mine in FROM_ROOM:
                o["confirm"].pop(mine, None)
        for mine, theirs in FROM_ROOM.items():
            why.pop(mine, None)
            given, said = (room["measures"], room.get("not_measured") or {}) if room is not None else ({}, {})
            if room is not None and theirs in given and theirs not in said:     # its own value, no reason beside it
                m[mine] = given[theirs]
                read = _map(room.get("confirm")).get(theirs)
                if read:                                   # the room's value stands on a reading (its routes run
                    if not isinstance(o.get("confirm"), dict):     # through a room it serves): said on the opening
                        o["confirm"] = {}                  # too, so a size rule set aside on it is never a pass
                    o["confirm"][mine] = read
            elif room is not None:
                why[mine] = said.get(theirs, "its room's isn't known")
            else:
                why[mine] = "the room it is in isn't one sleeping room read"


def _map(x) -> dict:
    """A part's field as a mapping, or none where it isn't one (parts built by hand: never a crash)."""
    return x if isinstance(x, dict) else {}


def _own_map(part: dict, key: str) -> dict:
    """The part's own mapping under `key`, made one where it is missing or isn't one (parts built by hand: never a
    crash; merge review of the R-2 reach)."""
    if not isinstance(part.get(key), dict):
        part[key] = {}
    return part[key]


def _list(x) -> list:
    return x if isinstance(x, list) else []


def _reach(found: list, name):
    """(False, the doors and the exits each reaches) where the routes show every way out of the sleeping room reaches
    two or more separate and distinct exits; (None, why not) otherwise. `found`: the routes' space parts for the room
    on its level (one expected)."""
    if len(found) != 1:
        return None, f"the routes give {'no' if not found else len(found)} space part(s) for {name}"
    got = _map(found[0].get("more")).get("exits_reached")
    if not isinstance(got, dict):
        return None, str(_map(found[0].get("not_measured")).get("space_exit_count") or "its routes aren't measured")
    whole = (got.get("two") is True and isinstance(got.get("doors"), dict) and bool(got["doors"])
             and all(isinstance(v, list) and all(isinstance(x, str) for x in v) and len(set(v)) >= 2
                     for v in got["doors"].values()))
    if not whole:
        return None, str(got.get("why") or "not every way out of it reaches two exits")
    return False, got["doors"]


__all__ = ["link", "NEW_MEASURES", "complies", "limits"]
