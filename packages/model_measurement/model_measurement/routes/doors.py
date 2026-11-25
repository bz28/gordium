"""The doors of a commercial story as the Building Code's door rules read them (section group 6a of
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md): one `means_of_egress_door` part
(rule_format/parts.yaml) for every door the interior description gives, whatever the routes made of it, so a door
the routes couldn't read is still a part whose sizes need review, never one left out of a rule that could then pass
on the others.

    door_parts(description, floor) -> [part, ...]     (None where the description's doors aren't read)

Each part says:

- `moe_door_clear_width` and `moe_door_clear_height` (inches): ONLY the maker's stated clear opening
  (`stated_clear`, read and refused as model_measurement.interior.doors.stated_clear reads it), the confirmed
  figure the routes pass the door by. Never the door's size, its leaf, or a plan width alone: a door with no stated
  clear opening (or a malformed one) has neither size measured, so BCNYS 1010.1.1 needs review for it, never a
  pass. Every other figure given for a size must agree with the maker's within 1/16 in, or that size isn't
  measured either (which is the door's is unclear), and where they agree the smallest of them counts: the plan's clear width (the routes' figure), and the drawn door
  where its drawing is given (its stops, hinge pin and closed leaf; its threshold and head stop, measured as the
  house reading measures them, model_measurement.interior.doors), or that drawing can't be measured.
- `moe_door_leaves` (count): the description's `leaves` (1, or 2 for a pair with no mullion): 1010.1.1 asks one
  leaf of a pair for the 32 in, which a pair's clear opening doesn't show. Not given: not measured.
- `moe_door_exit`: the door is marked an exit (`exit_kind`); `moe_door_exterior`: one side is outside;
  `moe_door_to_corridor`: one side is a room marked `corridor`; `moe_door_to_room_under_10_sf`: one side is a room
  under 10 sq ft inside its walls (1010.1.1 exception 3's storage closets). Each from the door's own sides, as the
  routes read them; a side that isn't a room read (or a room with no use given, for the corridor) leaves it not
  measured, never a guess.

Lengths in inches, as interior/ reads them. Plain code, no AI.
"""

from model_measurement.interior.doors import DRAWN, clear_height, clear_width, stated_clear
from model_measurement.interior.read import name_of, tidy
from model_measurement.interior.stops import Stop as InteriorStop
from model_measurement.routes.floor import EXIT_KINDS, OUTSIDE, SAME, _reader
from model_measurement.routes.stops import Stop

KIND = "means_of_egress_door"
SQ_IN = 144.0
CLOSET_MOST = 10.0                       # sq ft: 1010.1.1 exception 3, "storage closets less than 10 square feet"
LEAVES = (1, 2)
SIZES = ("moe_door_clear_width", "moe_door_clear_height")


def door_parts(description, floor) -> list | None:
    """Every door's part, in the description's order; None where the doors (or the description) can't be read."""
    if not isinstance(description, dict):
        return None
    doors = description.get("doors")
    if not isinstance(doors, list) or not all(isinstance(d, dict) for d in doors):
        return None
    try:
        reader = _reader(description)
    except Stop:
        return None
    rooms = {r["id"]: r for r in description.get("rooms") or [] if isinstance(r, dict) and isinstance(r.get("id"), str)}
    read = {}                                         # room id -> Room (None: known, not read), across every story
    for story in floor.stories.values():
        read.update(story.rooms)
    unknown = {u.get("id") for u in description.get("unknown_spaces") or [] if isinstance(u, dict)}
    levels = set(floor.stories)
    out, seen = [], set()
    for n, item in enumerate(doors, 1):
        did = item.get("id")
        pid = did if isinstance(did, str) and did.strip() and did not in seen else f"door #{n}"
        seen.add(pid)
        part = {"id": pid, "name": name_of(item)}
        if isinstance(item.get("level"), str) and item["level"] in levels:
            part["within"] = item["level"]
        part.update(measures={}, not_measured={}, more={})
        _sizes(part, item, reader)
        _leaves(part, item)
        _sides(part, item, rooms, read, unknown)
        out.append(part)
    return out


def _sizes(part, item, reader) -> None:
    m, why = part["measures"], part["not_measured"]
    name = part["name"]
    try:
        maker = stated_clear(item, reader)
    except InteriorStop as s:
        for k in SIZES:
            why[k] = Stop("door_clear_not_read", name=name, reason=s.reason).reason
        return
    if maker is None:
        for k in SIZES:
            why[k] = Stop("door_no_stated_clear", name=name).reason
        return
    stated = {"width": tidy(maker["width"]), "height": tidy(maker["height"])}
    part["more"]["stated_clear"] = {**stated, "source": maker["source"]}
    # every other figure the description gives for a size must agree with the maker's (within 1/16 in), else the
    # size isn't measured: the drawn door (as the house reading draws it: its stops, hinge pin and closed leaf; its
    # threshold and head stop) and, for the width, the plan's clear width the routes pass it by. Where they agree, the
    # smallest counts (drawing noise read on the cautious side, as the house reading reads it). Never the larger of
    # two figures, and never a size taken from anything but the maker's within 1/16 in (review rounds 1 and 2 of
    # section group 6a: a door drawn 70 in high was measured at its stated 84; one drawn 79 31/32 in at its 80)
    plan = item.get("plan")
    others = {"width": [("plan", plan.get("clear_width") if isinstance(plan, dict) else None, None)],
              "height": []}
    for key, fn in (("width", clear_width), ("height", clear_height)):
        if any(item.get(k) is not None for k in DRAWN[key]):
            others[key].append(("drawing", None, fn))
    for key, name_ in (("width", "moe_door_clear_width"), ("height", "moe_door_clear_height")):
        why_not, least = None, stated[key]
        for where, value, fn in others[key]:
            if value is None and fn is None:
                continue
            try:
                got = tidy(fn(item, reader) if fn else reader.size(value, f"the door's {where} clear {key}"))
            except InteriorStop as s:
                why_not = Stop("door_clear_not_read", name=name, reason=s.reason).reason
                break
            part["more"][f"{where}_clear_{key}"] = got
            if abs(got - stated[key]) > SAME:
                why_not = Stop("door_clear_disagree", name=name, where=where, size=key, other=got,
                               stated=stated[key]).reason
                break
            least = min(least, got)          # within 1/16 in: the less favourable counts (review round 2)
        if why_not:
            why[name_] = why_not
        else:
            m[name_] = least


def _leaves(part, item) -> None:
    got = item.get("leaves")
    if got is None:
        part["not_measured"]["moe_door_leaves"] = Stop("door_leaves_not_given", name=part["name"]).reason
    elif isinstance(got, bool) or got not in LEAVES:
        part["not_measured"]["moe_door_leaves"] = Stop("door_leaves_not_read", name=part["name"], got=got).reason
    else:
        part["measures"]["moe_door_leaves"] = int(got)


def _sides(part, item, rooms, read, unknown) -> None:
    m, why = part["measures"], part["not_measured"]
    name = part["name"]
    kind = item.get("exit_kind")
    if kind is None:
        m["moe_door_exit"] = False
    elif isinstance(kind, str) and kind in EXIT_KINDS:
        m["moe_door_exit"] = True
        part["more"]["exit_kind"] = kind
    else:
        why["moe_door_exit"] = Stop("door_exit_kind_not_read", name=name, got=kind).reason
    sides = item.get("sides")
    if not isinstance(sides, list) or len(sides) != 2 or not all(isinstance(s, str) and s.strip() for s in sides):
        reason = Stop("door_sides_not_read", name=name).reason
        for k in ("moe_door_exterior", "moe_door_to_corridor", "moe_door_to_room_under_10_sf"):
            why[k] = reason
        return
    part["more"]["sides"] = list(sides)
    m["moe_door_exterior"] = OUTSIDE in sides
    corridor, small, open_corridor, open_small = False, False, None, None
    for side in sides:
        if side == OUTSIDE:
            continue
        if side in unknown or side not in rooms:
            what = "an enclosed space with no room drawn in it" if side in unknown else "not a room given"
            open_corridor = open_small = Stop("door_side", name=name, side=side, what=what).reason
            continue
        use = rooms[side].get("use")
        if use == "corridor":
            corridor = True
        elif use is None:
            open_corridor = open_corridor or Stop("door_side_no_use", name=name, room=name_of(rooms[side])).reason
        room = read.get(side)
        if room is None:
            open_small = open_small or Stop("door_side_room_not_read", name=name, room=name_of(rooms[side])).reason
        elif room.outline.area / SQ_IN < CLOSET_MOST:
            small = True
    # a side known yes settles it yes; else any side unknown leaves it not measured
    if corridor or open_corridor is None:
        m["moe_door_to_corridor"] = corridor
    else:
        why["moe_door_to_corridor"] = open_corridor
    if small or open_small is None:
        m["moe_door_to_room_under_10_sf"] = small
    else:
        why["moe_door_to_room_under_10_sf"] = open_small


__all__ = ["door_parts", "KIND"]
