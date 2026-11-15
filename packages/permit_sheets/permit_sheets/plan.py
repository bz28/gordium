"""The life-safety plan's content: each floor's rooms, stairs, escape-opening tags and exit door, from the interior
description, each tag's result from the check. Plain code, no AI; it draws and labels, it never checks anything (the
way out shown is a schematic, labelled so: no rule checks a route).

What the interior description can't place is said, never drawn as if it were known (docs/permit_sheets/plan.md):
windows and doors have no position in plan (each is drawn in its own elevation), so escape openings are tagged in
their room and the exit door is named; rooms that overlap on one floor have no place in the house, so they are drawn
apart; a room with no outline or floor elevation is listed; a list left out (no `stairs`) is "not read", never none.
"""

from shapely.geometry import Polygon

from design_checker import present

from .words import worst

TO_INCHES = {"in": 1.0, "ft": 12.0, "mm": 1 / 25.4, "m": 1000 / 25.4}


def _poly(points, k):
    try:
        p = Polygon([(float(x) * k, float(y) * k) for x, y in points])
    except (TypeError, ValueError):
        return None
    return p if p.is_valid and p.area > 0 else None


def _door_lines(got: dict, interior: dict) -> list[dict]:
    """The exit door(s), each with its result (the most cautious of its rows), or the statement of what wasn't read.
    "Not read" is judged from what the check read (its measured parts), never the description's key: a `doors` list
    left out or malformed is "not read", never "none marked"."""
    parts = (got["measured"] or {}).get("parts") or {}
    doors = interior.get("doors")
    if parts.get("egress_door") is None or not isinstance(doors, list):
        return [{"text": "Exit door: not read from the drawing", "status": present.REVIEW}]
    xs = [x for law in got["laws"] for x in law["items"] if (x["item"].get("part") or {}).get("part") == "egress_door"]
    exits = [d for d in doors if isinstance(d, dict) and d.get("exit") is True]
    if not exits:
        return [{"text": "Exit door: none marked", "status": worst(x["status"] for x in xs
                                                                   if (x["item"]["part"] or {}).get("id") is None)}]
    out = []
    for d in exits:
        mine = [x["status"] for x in xs if x["item"]["part"].get("id") == d.get("id")]
        out.append({"text": f"Exit door {str(d.get('id')).upper()}: {d.get('name') or d.get('id')} "
                            "(its place in the plan isn't given in the drawing)", "status": worst(mine)})
    return out


def levels(got: dict, schedule: list[dict]) -> dict:
    """{"levels": [{elevation, rooms, stairs, apart}], "undrawn": rooms that can't be drawn, "notes", "doors"}."""
    interior = got["interior"] or {}
    k = TO_INCHES.get(interior.get("units"), 1.0)
    tags = {}
    for s in schedule:
        tags.setdefault(s.get("Room id"), []).append(s)
    by_level, undrawn, notes = {}, [], []
    sleeping = {r["id"] for r in ((got["measured"] or {}).get("parts") or {}).get("sleeping_room") or []}
    for r in interior.get("rooms") or []:
        if not isinstance(r, dict):
            continue
        room = {"id": r.get("id"), "name": r.get("name") or r.get("id"), "sleeping": r.get("sleeping") is True,
                "checked": r.get("id") in sleeping, "tags": tags.get(r.get("id"), [])}
        poly = _poly(r.get("floor") or [], k) if isinstance(r.get("floor"), list) else None
        elev = r.get("floor_elevation")
        if poly is None or type(elev) not in (int, float):
            undrawn.append(room)
            continue
        room["poly"] = poly
        by_level.setdefault(round(float(elev) * k, 6), []).append(room)
    # stairs read or not: from what the check read (its measured parts), never the description's key
    read_stairs = ((got["measured"] or {}).get("parts") or {}).get("stair")
    stairs = interior.get("stairs") if read_stairs is not None else None
    if read_stairs is None:
        notes.append({"text": "Stairs: not read from the drawing", "status": present.REVIEW})
    elif not read_stairs:
        notes.append({"text": "No stairs in the drawing", "status": None})
    stair_rows = [x for law in got["laws"] for x in law["items"] if (x["item"].get("part") or {}).get("part") == "stair"]
    out = []
    for elev in sorted(by_level):
        rooms = by_level[elev]
        apart = any(a["poly"].intersection(b["poly"]).area > 1e-6 for i, a in enumerate(rooms) for b in rooms[i + 1:])
        out.append({"elevation": elev, "rooms": rooms, "stairs": [], "apart": apart})
    for s in stairs or []:
        if not isinstance(s, dict):
            continue
        try:
            nos = [[(float(a[0]) * k, float(a[1]) * k, float(a[2]) * k), (float(b[0]) * k, float(b[1]) * k,
                                                                          float(b[2]) * k)]
                   for a, b in s["nosings"]]
            foot = float(s["bottom_elevation"]) * k
        except (KeyError, TypeError, ValueError, IndexError):
            notes.append({"text": f"Stair {s.get('name') or s.get('id')}: can't be drawn from the drawing",
                          "status": present.REVIEW})
            continue
        status = worst(x["status"] for x in stair_rows if x["item"]["part"].get("id") == s.get("id"))
        stair = {"id": s.get("id"), "name": s.get("name") or s.get("id"), "nosings": nos, "status": status}
        top = nos[-1][0][2]
        placed = False
        for lv in out:
            if lv["apart"]:
                continue
            if abs(lv["elevation"] - foot) < 0.5:
                lv["stairs"].append({**stair, "way": "UP"})
                placed = True
            elif abs(lv["elevation"] - top) < 0.5:
                lv["stairs"].append({**stair, "way": "DN"})
                placed = True
        if not placed:
            notes.append({"text": f"Stair {stair['name']}: no floor drawn at its foot or head to show it on",
                          "status": status})
    # what the check read (its measured parts), never the description's keys: a list left out or malformed is "not
    # read", never "none"
    parts = (got["measured"] or {}).get("parts") or {}
    rooms_read = parts.get("sleeping_room") is not None
    if parts.get("emergency_escape_opening") is None:
        notes.insert(0, {"text": "Escape openings: not read from the drawing", "status": present.REVIEW})
    if not rooms_read:
        notes.insert(0, {"text": "Rooms: not read from the drawing", "status": present.REVIEW})
    # an escape opening the schedule lists whose room is on no floor drawn here (its room not read, or unknown):
    # named in the notes with its result, never dropped from the plan
    known = {r["id"] for lv in out for r in lv["rooms"]} | {r["id"] for r in undrawn}
    for s in schedule:
        if not s.get("statement") and s.get("Room id") not in known:
            notes.append({"text": f"{tag_words(s)} (in {s.get('Room') or 'a room not read'}, not on this plan)",
                          "status": s["status"], "tag": True})
    return {"levels": out, "undrawn": undrawn, "notes": notes, "doors": _door_lines(got, interior),
            "rooms_read": rooms_read}


def tag_words(row: dict, short: bool = False) -> str:
    """An escape opening's tag: its mark (the schedule's) and its result; `short` leaves out its name (on the plan,
    where the schedule names it)."""
    if row["Mark"] == "-":
        return (f"No escape opening marked: {row['Result']}" if row["Opening"] == "none marked"
                else f"{row['Opening'].capitalize()}: {row['Result']}")
    return f"{row['Mark']}: {row['Result']}" if short else f"{row['Mark']} {row['Opening']}: {row['Result']}"

