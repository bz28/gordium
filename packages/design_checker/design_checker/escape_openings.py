"""The Building Code's sleeping rooms, as BCNYS 1031.2 reads them (section group 8a of
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md): the interior measuring's own sleeping rooms and
marked escape openings (design_checker.egress._escape_openings), each sleeping room then linked to what the
Building Code's own reading of the building already knows of it, with no new geometry:

- `sleeping_room_escape_openings`: how many emergency escape and rescue openings the description marks in it (the
  interior measuring's openings within it); the openings not read, not measured.
- `sleeping_room_fourth_or_higher`: its story's `story_fourth_or_higher_above_grade_plane`, the routes' story part
  of the room's own `level` (1031.2: "sleeping rooms below the fourth story above grade plane").
- `sleeping_room_story_one_exit`: that story has one exit, from its `story_exit_count` (1031.2 item 1: Group R-2
  "in stories with only one exit or access to only one exit"; two or more: no, Gordium's reading that no Table
  1006.3.4 one-exit allowance is taken there).
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
          "sleeping_room_story_one_exit": ("story_exit_count", lambda v: v < 2)}
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
}
NEW_MEASURES = ("sleeping_room_escape_openings", *LINKED, "sleeping_room_door_to_outside")


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
    stories = {s.get("id"): s for s in parts.get("story") or [] if isinstance(s, dict)}
    openings = parts.get(OPENINGS)
    doors = parts.get("means_of_egress_door")
    for part in rooms:
        if not isinstance(part, dict) or part.get("maybe"):
            continue                 # an enclosed space that may not be a room at all: every row of it needs review
        m = part.setdefault("measures", {})
        why = part.setdefault("not_measured", {})
        for k in NEW_MEASURES:           # the house measuring's "not measured yet" for these: this link decides them
            why.pop(k, None)
        name = part.get("name") or part.get("id")
        pid = part.get("id")
        rid = (part.get("more") or {}).get("described_id", pid)       # the description's id (egress._escape_openings)
        # the openings marked in it
        if isinstance(openings, list):
            m["sleeping_room_escape_openings"] = sum(1 for o in openings if isinstance(o, dict) and o.get("within") == pid)
        else:
            why["sleeping_room_escape_openings"] = WHY["openings_not_read"]
        # its story's place and exits
        same = by_id.get(rid, [])
        level = same[0].get("level") if len(same) == 1 else None
        if len(same) != 1:
            reason = WHY["no_room"].format(name=name)
        elif not isinstance(level, str):
            reason = WHY["no_level"].format(name=name)
        elif level not in stories:
            reason = WHY["no_story"].format(name=name, level=level)
        else:
            reason = None
        for mine, (theirs, worked) in LINKED.items():
            story = stories.get(level) if reason is None else None
            if story is not None and theirs in (story.get("measures") or {}):
                m[mine] = worked(story["measures"][theirs])
            elif story is not None:
                why[mine] = WHY["story_not_measured"].format(
                    name=name, reason=(story.get("not_measured") or {}).get(theirs, "not measured"))
            else:
                why[mine] = reason
        # a door of its own to outside
        if not isinstance(doors, list):
            why["sleeping_room_door_to_outside"] = WHY["doors_not_read"].format(name=name)
            continue
        sides = [((d.get("more") or {}).get("sides")) for d in doors if isinstance(d, dict)]
        if any(not isinstance(s, list) for s in sides) or len(sides) != len(doors):
            if any(isinstance(s, list) and rid in s and OUTSIDE in s for s in sides):
                m["sleeping_room_door_to_outside"] = True
            else:
                why["sleeping_room_door_to_outside"] = WHY["door_sides_not_read"].format(name=name)
            continue
        m["sleeping_room_door_to_outside"] = any(rid in s and OUTSIDE in s for s in sides)


__all__ = ["link", "NEW_MEASURES"]
