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
  Table 1006.3.4(1) permits: review round 1), so not measured there.
- `sleeping_room_door_to_outside`: whether any door of the room (the routes' door parts whose sides name it) has
  outside on its other side (1031.2 exception 2: an exit door or exit access door that opens directly into a public
  way, yard, court or exterior egress balcony); no, only where every door of the description has both its sides
  read and none of the room's is to outside.

Each one the description or the routes don't give is not measured, with its reason: never a guess, so a rule
reading it needs review. A sleeping room is only a room the description states is one (`sleeping: true`), or an
enclosed space with no room drawn in it (the interior measuring's `maybe`, every row about it a review): never a
room the description says isn't one. Plain code, no AI.
"""

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
                 "more than one (not only one, as Table 1006.3.4(1) permits) isn't worked out",
    "opening_stray": "an emergency escape and rescue opening of the description is within no sleeping room read (none "
                     "named, a room not read, or one that can't be read), so it may be this room's",
    "room_id_shared": "the sleeping room {name}'s id is more than one room's, so which openings and doors are its "
                      "isn't known",
}
NEW_MEASURES = ("sleeping_room_escape_openings", *LINKED, "sleeping_room_door_to_outside")


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


def link(parts: dict, description) -> None:
    """Add the four measures to every sleeping room part in `parts` (the routes' parts and the interior measuring's
    sleeping rooms and openings, together), in place."""
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
                why[mine] = WHY["story_not_measured"].format(name=name, reason=f"its {theirs} is not a count")
            elif known:
                value = worked(raw)
                if value is None:
                    why[mine] = WHY["two_exits"].format(name=name)
                else:
                    m[mine] = value
            elif story is not None:
                said = story.get("not_measured") if isinstance(story.get("not_measured"), dict) else {}
                why[mine] = WHY["story_not_measured"].format(name=name, reason=said.get(theirs, "not measured"))
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


__all__ = ["link", "NEW_MEASURES"]
