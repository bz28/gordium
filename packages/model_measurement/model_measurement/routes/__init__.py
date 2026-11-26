"""Measuring a story's escape routes from an interior description (docs/decisions/2026-11-20_route_measurement.md):
the `story`, `space`, `corridor` and `means_of_egress_door` parts the commercial egress rules read (rule_format/parts.yaml), handed over the
way interior/ hands its parts.

    measure(description) -> {"format", "units", "parts": {"story": [...], "space": [...], "corridor": [...],
                                                         "means_of_egress_door": [...]},
                             "problems": [...]}

`parts` is what rule_format.parts.rows reads: each part {"id", "name", "within"?, "measures", "not_measured",
"more"}, measures named as parts.yaml names them, in its units (travel in feet, corridor width in inches, the dead
end's least width in feet, areas in square feet). A measure that can't be settled is left out of `measures` and its
reason put in `not_measured` (a rule reading it then needs review): never a default. A measure given as two named
readings (decisions 6 and 8: open questions 3 and 7) is left out too, its readings in `readings`, {measure: [{value,
named: {question: answer}}]}, the shape the checker's readings take (design_checker/check.py readings_of);
rule_format.parts.rows decides such a rule under every combination of them (pass only if all pass, fail only if all
fail, else needs review). `more` holds the
figures behind each measure: the routes drawn, the bounds, the corridors' centre lines; a space taken as part of the
room it serves (decision 1a) names that room (`served_through`: its egress, and so its occupant load, goes through
it, BCNYS 1004.2). `confirm`, {measure: words},
says a measure stands on Gordium's reading (decision 1a, a room that opens only into the room it serves: the story's
travel and common path, and that room's own exit count and common path), for the checker to show beside each row
that reads it; a row that would comply on it needs review until the reading is confirmed (rule_format.parts.rows).
`architect_stated`, {measure: words}, says a figure leaves out rooms the architect marks `not_occupied` (decision 1b:
NFPA's `egress_travel_distance_occupied`, `common_path_of_travel_occupied` and the room-door travel; the IBC's
figures never leave a room out), shown beside each row that reads it, never holding a pass: the architect's statement.

The pieces (decision 11): floor.py reads each story's floor, zones and rings (decisions 1, 1a, 10); paths.py draws
decision 2's routes; remote.py gives decision 3's travel figure; common_path.py decision 5's; dead_ends.py decision
6's dead ends and corridor widths; straight.py decision 7's remoteness and diagonal; areas.py decision 8's areas.
Here: the story's exit count (distinct `exit_id`s); each space's exit access doors (a door from which a permitted
route reaches an exit without coming back into the room, never one into a closet or toilet: such a door reaches
none) and passages, counted once each; the travel from those doors (`egress_travel_from_room_door`) and within a
sleeping room to them (`egress_travel_in_sleeping_room`, 0 with no sleeping room). A space is every room on the
story not marked `corridor`; a corridor is a room marked so; a room with no `use`, or an enclosed space with no room
drawn in it, may be either (a corridor part marked `maybe`). The architect's own figures (occupant loads, the
corridor's rating and smoke partitions) are marks the description doesn't carry yet: not measured.
"""

import copy
import math

from model_measurement.interior.read import Reader, name_of
from model_measurement.routes import areas, dead_ends, story_place, straight
from model_measurement.routes.common_path import _TravelOnly, at_point, story_figure
from model_measurement.routes.doors import door_parts
from model_measurement.routes.floor import CLEARANCE, OUTSIDE as OUTSIDE_SIDE, READING, read, region
from model_measurement.routes.paths import FOOT, StoryRoutes, _Leg
from model_measurement.routes.remote import farthest
from model_measurement.routes.stops import Stop

MEASURED_FORMAT = "gordium.routes_measured/1"
KINDS = ("story", "space", "corridor", "means_of_egress_door")
SF = FOOT * FOOT
# decision 1b: NFPA 101 measures travel and common path from points "subject to occupancy" (7.6.1(1), A.3.3.47), the
# 2009 IBC from every point within the story (1016.1): each book's figure under its own measure's name
OCCUPIED = {"egress_travel_distance": "egress_travel_distance_occupied",
            "common_path_of_travel": "common_path_of_travel_occupied"}
READ_THROUGH = ("egress_travel_distance", "egress_travel_from_room_door", "common_path_of_travel", *OCCUPIED.values())
ROUTE_MEASURES = ("story_exit_count", "egress_travel_distance", "egress_travel_from_room_door",
                  "egress_travel_in_sleeping_room", "common_path_of_travel", "exit_remoteness_ratio",
                  *OCCUPIED.values())
LEFT_OUT_WORDS = "measured leaving out {n} space{s} marked not occupied by the architect: {names}"
STATED = {"story_occupant_load": "the story's design occupant load", "space_occupant_load": "the space's occupant load",
          "corridor_occupant_load": "the occupant load the corridor serves",
          "corridor_fire_rating_hours": "the corridor walls' fire-resistance rating",
          "corridor_walls_smoke_partitions": "whether the corridor's walls are smoke partitions"}
QUESTIONS = {areas.STORY_AREA_QUESTION: "3", areas.ACCESSORY_AREA_QUESTION: "3", dead_ends.QUESTION: "7"}


def _listed(description, key) -> list:
    """A description's list under `key`, or none where it isn't a list (what isn't read is the floor reading's to
    say: never a crash)."""
    got = description.get(key) if isinstance(description, dict) else None
    return got if isinstance(got, list) else []


def measure(description, clearance: float = CLEARANCE, ground: dict | None = None) -> dict:
    """`ground`: the ground the architect stated, story_place.ground_of's (None: none stated), for where each story
    sits against the grade plane (story_place.py)."""
    out = {"format": MEASURED_FORMAT, "units": {"travel": "ft", "corridor_width": "in", "area": "sf"},
           "parts": {k: None for k in KINDS}, "problems": []}
    floor = read(description)
    out["problems"] = list(floor.stops)
    if not floor.stories:
        return out
    placed = story_place.places(description, Reader(description["units"]),
                                {lid: s.name for lid, s in floor.stories.items()}, floor.stories, ground,
                                floor.stops)
    items = {r["id"]: r for r in _listed(description, "rooms") if isinstance(r, dict) and isinstance(r.get("id"), str)}
    unknown = [u for u in _listed(description, "unknown_spaces") if isinstance(u, dict)]
    parts = {k: [] for k in KINDS}
    toward = {}                                     # door id -> the side egress travel goes into, or why not known
    for level, story in floor.stories.items():
        uses = {rid: (items.get(rid) or {}).get("use") for rid in story.rooms}
        here = [u for u in unknown if u.get("level") == level]
        toward.update(_egress_sides(story, _story_parts(story, uses, items, here, parts, clearance)))
    for sp in parts["story"]:                            # where each story sits against the grade plane
        got = placed[sp["id"]]
        sp["measures"].update(got["measures"])
        sp["not_measured"].update(got["not_measured"])
        sp["more"].update(got["more"])
    parts["means_of_egress_door"] = door_parts(description, floor, toward)   # every door given (section group 6a)
    if floor.stops:                                      # a part that can't be placed on a story: none is "none"
        for u in unknown:
            if not isinstance(u.get("level"), str) or u.get("level") not in floor.stories:
                _maybe_parts(u, None, parts)
    _not_measured_yet(parts)
    out["parts"] = parts
    return out


# --- one story -------------------------------------------------------------------------------------------------------

def _part(pid, name, within=None) -> dict:
    p = {"id": pid, "name": name}
    if within is not None:
        p["within"] = within
    p.update(measures={}, not_measured={}, more={})
    return p


def _readings(part, name, readings, words) -> None:
    """A measure given as two named readings (square inches -> square feet, or inches -> feet, by `scale`)."""
    part["readings"] = part.get("readings", {})
    part["readings"][name] = [{"value": v, "named": {q: a}} for v, q, a in readings]
    question = QUESTIONS[readings[0][1]]
    part["not_measured"][name] = Stop("readings", question=question, words=words).reason


def _story_parts(story, uses, items, unknown, parts, r):
    """The story's parts; returns its rooms' exit access ({room id: {door id: ...}} or a Stop), None where its routes
    aren't measured."""
    sp = _part(story.level, story.name)
    parts["story"].append(sp)
    routes = None
    if story.stops:
        why = Stop("story_not_measured", reasons="; ".join(story.stops)).reason
        for m in ROUTE_MEASURES:
            sp["not_measured"][m] = why
    access, figures = {}, {}
    if not story.stops:
        routes = StoryRoutes(story, r)
        access = _exit_access(story, routes, uses)
        figures = _story_routes(sp, story, routes, uses, items, access)
        if story.served_by:                                  # Gordium's reading reaches these figures: said so
            words = READING.format(rooms="; ".join(
                f"{story.rooms[k].name} through {story.rooms[h].name}" for k, h in sorted(story.served_by.items())))
            sp["confirm"] = {m: words for m in READ_THROUGH}
    _story_areas(sp, story, uses, [name_of(u) for u in unknown])
    for m in ("story_occupant_load",):
        sp["not_measured"][m] = Stop("stated_not_given", what=STATED[m]).reason
    found = dead_ends.corridors(story, uses, routes)
    for rid, room in sorted(story.rooms.items()):
        use, item = uses.get(rid), items.get(rid) or {}
        name = room.name if room is not None else name_of(item)
        if use == "corridor":
            parts["corridor"] += _corridor_parts(rid, name, story, found.get(rid), room)
            continue
        parts["space"].append(_space_part(rid, name, story, routes, room, access.get(rid), figures,
                                          sp["not_measured"].get("common_path_of_travel")))
        if routes is not None and rid in story.served_by:
            words = READING.format(rooms=f"{name} through {story.rooms[story.served_by[rid]].name}")
            parts["space"][-1]["confirm"] = {m: words for m in ("space_exit_count", "space_common_path")}
            parts["space"][-1]["more"]["served_through"] = story.served_by[rid]   # its egress is through that room
            # (1004.2: its occupant load adds to that room's; design_checker/occupant_load.py)
        if use is None:                                   # it may be a corridor: never "no corridors" on its say
            cp = _part(f"{rid} (as a corridor)", name, story.level)
            cp["maybe"] = Stop("area_no_use", name=name).reason
            parts["corridor"].append(cp)
    for u in unknown:
        _maybe_parts(u, story.level, parts)
    return access if routes is not None else None


def _egress_sides(story, access) -> dict:
    """{door id: the side (a room id, or "outside") egress travel goes into through it, or the Stop why that isn't
    known} for each door the story's routes read (section group 6b, 1010.1.2.1: "swing in the direction of egress
    travel"). Known only where the door can carry egress one way alone (review round 1 of section group 6b):

    - A door into an exit enclosure or passageway (the room it enters): into the exit, only where that room has its own
      door to outside on this story marked an exterior exit door at discharge (an unmarked one may be a way in: review
      round 7), or the story has no door to outside at all, so the door can't be the exit's discharge (1028.1's
      discharge through a lobby or corridor runs out of the stair through it). A horizontal exit:
      not known (the routes count it an exit for the rooms on both its sides; it is often used both ways, 1026). An
      exterior exit door at the level of exit discharge: outside; any other exit door with outside on one side (a
      stair's door onto an occupiable roof, whose occupants egress into the stair: 1004.7): not known.
    - Any other door to outside (not marked an exit): not known. Only a door marked an exterior exit door at the level
      of exit discharge surely leads out (exits are marked, never guessed); an unmarked one may be a patio's, an
      exterior walkway's or a balcony's way in, on any story, the building's lowest included where the model holds only
      some of its stories (review rounds 4 to 6).
    - Any other: away from the one room whose exit access it is (a door from which a route reaches an exit without
      coming back into the room), only where that room is stated end-only (sleeping, an end-only use, lockable, or
      pass_through stated false: `end_only_stated`), so no one else's route runs back through the door into it (a
      corridor's occupants crossing a lobby to its own front door); a room whose crossing isn't stated may be crossed
      (review rounds 1 and 2).

    Else not known; a story whose routes aren't measured: every door not known."""
    out = {}
    outside_doors = {d.id for d in story.doors.values() if OUTSIDE_SIDE in d.sides}
    unclear = lambda d: Stop("egress_side_unclear", name=d.name)
    for d in story.doors.values():
        if access is None:
            out[d.id] = Stop("story_not_measured", reasons="; ".join(story.stops))
            continue
        if d.exit_kind:
            if OUTSIDE_SIDE in d.sides:              # only an exterior exit door at discharge surely leads out (round 3:
                out[d.id] = OUTSIDE_SIDE if d.exit_kind == "exterior_at_discharge" else unclear(d)   # a roof's door
            elif d.exit_kind in ("exit_enclosure", "exit_passageway") and d.exit_id in d.sides:
                own_outside = any(d.exit_id in story.doors[o].sides and story.doors[o].exit_kind == "exterior_at_discharge"
                                  for o in outside_doors)       # round 7: an unmarked one may be a way in
                out[d.id] = d.exit_id if own_outside or not outside_doors else unclear(d)
            else:
                out[d.id] = unclear(d)
            continue
        if OUTSIDE_SIDE in d.sides:                  # round 4: only an exit's own way out (a balcony's door back in)
            out[d.id] = unclear(d)
            continue
        rooms = [s for s in d.sides if s != OUTSIDE_SIDE]
        if any(isinstance(access.get(s), Stop) for s in rooms):
            out[d.id] = unclear(d)
            continue
        from_ = [s for s in rooms if d.id in (access.get(s) or {})]
        room = story.rooms.get(from_[0]) if len(from_) == 1 else None
        out[d.id] = next(s for s in rooms if s != from_[0]) if room is not None and room.end_only_stated else unclear(d)
    return out


def _maybe_parts(u, level, parts) -> None:
    name = name_of(u)
    for kind, suffix in (("space", ""), ("corridor", " (as a corridor)")):
        p = _part(f"{u.get('id')}{suffix}", name, level)
        p["maybe"] = Stop("maybe_kind", name=name, kind=kind).reason
        parts[kind].append(p)


def _feet(x) -> float:
    return float(x) / FOOT


def _xy(p) -> list:
    return [round(_feet(p[0]), 4), round(_feet(p[1]), 4)]


def _drawn(route) -> list:
    """A route's pieces in feet, to draw it."""
    out = []
    for q in route.pieces:
        if q[0] == "line":
            out.append({"line": [_xy(q[1]), _xy(q[2])]})
        else:
            out.append({"arc": {"centre": _xy(q[1]), "radius": round(_feet(q[2]), 4),
                                "start_deg": round(math.degrees(q[3]), 4), "sweep_deg": round(math.degrees(q[4]), 4)}})
    return out


def _figure(remote) -> dict:
    return {"figure": _feet(remote.figure), "greatest_sample": _feet(remote.greatest), "at": _xy(remote.at),
            "from": remote.part, "clear_floor_bound": _feet(remote.floor_bound),
            "next_to_rings_bound": None if remote.near_rings_bound is None else _feet(remote.near_rings_bound),
            "clusters": [{"rings": [_xy(c) for c in k.rings], "edge_greatest": _feet(k.edge_greatest),
                          "margin": _feet(k.margin), "how": k.how, "bound": _feet(k.bound)} for k in remote.clusters],
            "samples": remote.samples}


def _try(part, name, work):
    try:
        return work()
    except Stop as s:
        part["not_measured"][name] = s.reason
        return None


def _story_routes(sp, story, routes, uses, items, access) -> dict:
    m, more = sp["measures"], sp["more"]
    m["story_exit_count"] = len(routes.exits)
    travel = _try(sp, "egress_travel_distance", lambda: farthest(routes))
    if travel is not None:
        m["egress_travel_distance"] = _feet(travel.figure)
        more["egress_travel_distance"] = _figure(travel)
        more["egress_travel_distance"]["route"] = _drawn(routes.route(travel.at))
    else:
        more["egress_travel_distance"] = _over_rooms_measured(story, {
            rid: _attempt(lambda rid=rid: farthest(_TravelOnly(routes, {rid})))
            for rid in sorted(k for k, v in story.rooms.items() if v is not None)})
    figures = {}                                  # each space's own common path, or why not (its values kept)
    for rid in sorted(k for k, v in story.rooms.items() if v is not None and uses.get(k) != "corridor"):
        try:
            figures[rid] = story_figure(routes, rooms={rid})
        except Stop as s:
            figures[rid] = s
    _common(sp, story, routes, uses, figures, "common_path_of_travel", None)
    left_out = sorted(k for k, v in story.rooms.items() if v is not None and v.not_occupied)
    _occupied(sp, story, routes, uses, figures, left_out)
    got = _try(sp, "exit_remoteness_ratio", lambda: straight.ratio(story))
    if got is not None:
        far, across, ratio = got
        m["exit_remoteness_ratio"] = float(ratio)
        more["exit_remoteness_ratio"] = {"nearest_edges": _feet(far.length), "door_centres": _feet(far.centres),
                                         "exits": list(far.exits), "doors": list(far.doors),
                                         "diagonal": _feet(across.length), "diagonal_ends": [_xy(p) for p in
                                                                                             across.corners]}
    worst, why, stopped = None, None, {}
    for rid, doors in access.items():
        if rid in left_out:                       # decision 1b: a room nobody occupies is no start (NFPA 7.6.1(1))
            continue
        if isinstance(doors, Stop) or not doors:
            stop = doors if isinstance(doors, Stop) else Stop("no_exit_access", name=story.rooms[rid].name)
            why = why or stop.reason
            stopped[rid] = {"name": story.rooms[rid].name, "why": stop.reason, "stop": stop.key}
            continue
        for did, d in doors.items():
            if d is not None and (worst is None or d > worst[0]):
                worst = (d, rid, did)
    if why or worst is None:
        sp["not_measured"]["egress_travel_from_room_door"] = why or Stop("no_room_doors").reason
        if stopped:                               # every room it stops at, by id, each with its stop's key: the panel's
            sp["more"]["egress_travel_from_room_door"] = {"room_ids_not_measured": stopped}   # (never a figure)
    else:
        m["egress_travel_from_room_door"] = _feet(worst[0])
        more["egress_travel_from_room_door"] = {"room": worst[1], "door": worst[2]}
    sleeping = [rid for rid, room in story.rooms.items() if room is not None and (items.get(rid) or {}).get("sleeping")]
    if not sleeping:
        m["egress_travel_in_sleeping_room"] = 0.0
        return figures
    worst = 0.0
    for rid in sorted(sleeping):
        doors = access.get(rid)
        if isinstance(doors, Stop):
            sp["not_measured"]["egress_travel_in_sleeping_room"] = doors.reason
            return figures
        got = _try(sp, "egress_travel_in_sleeping_room", lambda: _in_room(story, routes, rid, doors or {}))
        if got is None:
            return figures
        worst = max(worst, got)
    m["egress_travel_in_sleeping_room"] = _feet(worst)
    return figures


def _common(sp, story, routes, uses, figures, name, rooms) -> None:
    """The story's common path (decision 5) over `rooms` (None: every room), under `name`, or why not: a room among
    them whose own figure stopped stops it (its reason; the greatest over the rooms measured in `more`)."""
    m, more = sp["measures"], sp["more"]
    within = (lambda k: True) if rooms is None else (lambda k: k in rooms)
    stopped = [f for k, f in figures.items() if isinstance(f, Stop) and within(k)]
    common = None if stopped else _try(sp, name, lambda: story_figure(routes, rooms=rooms))
    if stopped:
        sp["not_measured"][name] = stopped[0].reason
        corridors = {rid: _attempt(lambda rid=rid: story_figure(routes, rooms={rid}))
                     for rid in sorted(k for k, v in story.rooms.items()
                                       if v is not None and uses.get(k) == "corridor" and within(k))}
        more[name] = _over_rooms_measured(story, {**{k: f for k, f in figures.items() if within(k)}, **corridors})
    if common is not None:
        m[name] = _feet(common.figure)
        more[name] = _figure(common)
        pair = at_point(routes, common.at)
        more[name].update(exits=list(pair.exits), routes=[_drawn(x) for x in pair.routes])


def _occupied(sp, story, routes, uses, figures, left_out) -> None:
    """Decision 1b: NFPA's travel and common path, from the points of the rooms not marked `not_occupied` only. With
    none marked, the same figures as the IBC's (copied: the same walk); every room marked, not measured (no point to
    start from, never 0); else measured over the others, and `architect_stated` says which rooms were left out, for
    every row reading these figures (or the room-door travel, which leaves out their doors) to show: the architect's
    statement, never hidden."""
    m, more, gone = sp["measures"], sp["more"], sp["not_measured"]
    if not left_out:
        for ibc, nfpa in OCCUPIED.items():
            if ibc in m:
                m[nfpa] = m[ibc]
            if ibc in gone:
                gone[nfpa] = gone[ibc]
            if ibc in more:
                more[nfpa] = copy.deepcopy(more[ibc])
        return
    names = [story.rooms[k].name for k in left_out]
    words = LEFT_OUT_WORDS.format(n=len(names), s="" if len(names) == 1 else "s", names=", ".join(names))
    sp["architect_stated"] = {name: words for name in (*OCCUPIED.values(), "egress_travel_from_room_door")}
    occupied = {k for k, v in story.rooms.items() if v is not None and not v.not_occupied}
    if not occupied:
        for nfpa in OCCUPIED.values():
            gone[nfpa] = Stop("none_occupied").reason
        return
    name = OCCUPIED["egress_travel_distance"]
    travel = _try(sp, name, lambda: farthest(_TravelOnly(routes, occupied)))
    if travel is not None:
        m[name] = _feet(travel.figure)
        more[name] = _figure(travel)
        more[name]["route"] = _drawn(routes.route(travel.at))
    else:
        more[name] = _over_rooms_measured(story, {rid: _attempt(lambda rid=rid: farthest(_TravelOnly(routes, {rid})))
                                                  for rid in sorted(occupied)})
    _common(sp, story, routes, uses, figures, OCCUPIED["common_path_of_travel"], occupied)
    for nfpa in OCCUPIED.values():                # the rooms left out, beside each figure drawn
        more.setdefault(nfpa, {})["left_out"] = names


def _attempt(work):
    try:
        return work()
    except Stop as s:
        return s


def _over_rooms_measured(story, by_room: dict) -> dict:
    """Where the story's figure is a stop because some rooms aren't measured (no route, or another stop such as a
    tie not worked out: each room's own reason is given, never called "no route" unless it is): the greatest over
    the rooms that are,
    labelled as no verdict (the measure stays not measured, so every rule reading it needs review), for an eval to
    set beside a hand-checked sheet. Each room's own figure is decision 3's bound over its points."""
    good = {rid: f for rid, f in by_room.items() if not isinstance(f, Stop)}
    stopped = {rid: f.reason for rid, f in by_room.items() if isinstance(f, Stop)}
    names = ", ".join(story.rooms[rid].name for rid in sorted(stopped)) or "none"
    out = {"label": f"greatest over the rooms measured; not a verdict, since {names} isn't measured (each room's "
                    f"reason in rooms_not_measured)",
           "rooms_not_measured": {story.rooms[rid].name: why for rid, why in sorted(stopped.items())},
           # the same rooms by id (two rooms may share a name), each with its stop's key ("no_route", …): what the
           # panel selects and groups by (design_checker.panel_data), never a figure
           "room_ids_not_measured": {rid: {"name": story.rooms[rid].name, "why": by_room[rid].reason,
                                           "stop": by_room[rid].key} for rid in sorted(stopped)}}
    if good:
        rid, best = max(good.items(), key=lambda x: x[1].figure)
        out.update(figure=_feet(best.figure), room=story.rooms[rid].name, room_id=rid, at=_xy(best.at),
                   greatest_sample=_feet(best.greatest), rooms=len(good))
    return out


def _story_areas(sp, story, uses, unknown) -> None:
    if story.inner is not None:                 # 202 FLOOR AREA, GROSS: within the inside perimeter of the exterior
        sp["measures"]["story_gross_floor_area"] = story.inner.area / SF   # walls (the outlines have no courts in them)
    else:
        sp["not_measured"]["story_gross_floor_area"] = Stop(
            "outline_needed", reason=story.outline_stop or "no outline is given for it").reason
    got = _try(sp, "story_building_area", lambda: areas.building_area(story))
    if got is not None:
        _readings(sp, "story_building_area", [(x.value / SF, x.question, x.answer) for x in got],
                  "; ".join(f"{x.value / SF:.1f} sf {_words(x.answer, 'the exterior walls')}" for x in got))
    got = _try(sp, "story_accessory_area", lambda: areas.accessory_area(story, uses, unknown))
    if got is not None:
        _readings(sp, "story_accessory_area", [(x.value / SF, x.question, x.answer) for x in got],
                  "; ".join(f"{x.value / SF:.1f} sf {_words(x.answer, 'their walls')}" for x in got))
    got = _try(sp, "story_day_care_net_area", lambda: areas.day_care_net_area(story, uses, unknown))
    if got is not None:
        sp["measures"]["story_day_care_net_area"] = got / SF
        sp["more"]["computed_day_care_occupant_load"] = got / SF / areas.DAY_CARE_FACTOR


def _words(answer, walls) -> str:
    return f"inside {walls}" if answer == "inside" else f"to the outer faces of {walls}"


# --- spaces and their exit access doors (decision 11) ------------------------------------------------------------------

def _exit_access(story, routes, uses) -> dict:
    """{room id: {door id or passage: travel (in) from it to the nearest exit, None for a passage} or the Stop why
    not} for every room read that isn't marked `corridor`: its doors and passages from which a permitted route
    reaches an exit without coming back into it."""
    out = {}
    chain = routes._chain(frozenset(routes.exits))[0]
    for rid, room in sorted(story.rooms.items()):
        if room is None or uses.get(rid) == "corridor":
            continue
        try:
            out[rid] = _room_access(story, routes, room, chain)
        except Stop as s:
            out[rid] = s
    return out


def _room_access(story, routes, room, chain) -> dict:
    zone = story.zone_of.get(room.id)
    if zone is not None and len(zone.rooms) > 1:
        raise Stop("exit_access_unclear", name=room.name)
    if zone is not None:                                     # its own zone left out: never back through it
        from dataclasses import replace
        keep = [z for z in story.zones if z is not zone]
        sub = StoryRoutes(replace(story, zones=keep, zone_of={k: z for k, z in story.zone_of.items() if z in keep}),
                          routes.r)
        sub._engines = routes._engines                       # the zones' graphs, built once
        chain = sub._chain(frozenset(sub.exits))[0]
    got = {}
    for d in story.doors.values():
        if room.id not in d.face:
            continue
        if d.exit_kind:
            got[d.id] = 0.0
        elif math.isfinite(chain.get(d.id, math.inf)):
            got[d.id] = chain[d.id]
        elif room.id in story.served_by:                     # on through the room it serves (decision 1a)
            onward = routes.tied_onward(room, d.id, frozenset(routes.exits), _xy(d.centre), frozenset())
            if onward is not None:
                got[d.id] = onward.length
    if zone is None:                                         # an end-only room: its passages into the floor beyond
        for n, (a, b, seg) in enumerate(story.passages):
            if room.id not in (a, b):
                continue
            beyond = story.zone_of.get(b if a == room.id else a)
            if beyond is None:
                continue
            mid = seg.interpolate(0.5, normalized=True)
            engine = routes._engine(beyond)
            p = (mid.x, mid.y)
            if routes.r > 0 and engine.inside(p):
                raise Stop("passage_in_ring", name=room.name)
            engine.prepare([story.doors[d].centre for d in beyond.doors])
            if any(math.isfinite(engine.dist(p, story.doors[d].centre) + chain.get(d, math.inf)) for d in beyond.doors):
                got[f"passage #{n + 1}"] = None
    return got


def _in_room(story, routes, rid, doors) -> float:
    """The greatest route within a sleeping room to the nearest of its exit access doors (decision 3's bound)."""
    centres = [story.doors[d].centre for d in doors if d in story.doors]
    if not centres:
        raise Stop("no_exit_access", name=story.rooms[rid].name)
    own = region(story, [rid])
    leg = _Leg(own.floor, own.rings if routes.r > 0 else [], own.corners, routes.r)
    leg.prepare(centres)

    class _Within:
        r = routes.r

        class story:                                         # noqa: N801 (what farthest reads)
            rooms = {rid: routes.story.rooms[rid]}

        @staticmethod
        def rings_for(room):
            return own.rings

        @staticmethod
        def travel(p, exit_ids=None):
            if routes.r > 0 and leg.inside(p):
                raise Stop("inside_ring", x=round(p[0] / FOOT, 3), y=round(p[1] / FOOT, 3))
            best = min(leg.dist(p, c) for c in centres)
            if not math.isfinite(best):
                raise Stop("no_route", x=round(p[0] / FOOT, 3), y=round(p[1] / FOOT, 3), exits="its exit access doors")
            return best

    return farthest(_Within).figure


ENTERED_EXITS = ("exit_enclosure", "exit_passageway")    # the exits a door enters as a room (IBC 1016.1's list)


def _is_exit(story, rid) -> bool:
    """Whether the room is itself an exit (an exit stair's enclosure, an exit passageway: exits entered as rooms), not a
    space the exits serve: a door of it marked `exit_enclosure` or `exit_passageway` enters it (its `exit_id` is this
    room, as the format gives an enclosure's doors, docs/interior/interior_description_format.md). A horizontal exit
    leaves the rooms on both its sides spaces (each is a refuge area the other side's exit access reaches, 1026), as
    an exterior exit door at discharge or onto an exterior stair or ramp leaves its room one. No such door of it, or
    each one entering the room on its other side, and it is a space; one whose exit is neither room it joins (a
    stair's own id) leaves it unknown (Stop)."""
    entered = sorted((d for d in story.doors.values() if rid in d.sides and d.exit_kind in ENTERED_EXITS),
                     key=lambda d: d.id)
    if any(d.exit_id == rid for d in entered):
        return True
    for d in entered:
        other = next((s for s in d.sides if s != rid), None)
        if d.exit_id != other:
            raise Stop("exit_side_unclear", name=story.rooms[rid].name if story.rooms.get(rid) else rid,
                       door=d.name, exit_id=d.exit_id)
    return False


def _space_part(rid, name, story, routes, room, access, figures, why_not) -> dict:
    p = _part(rid, name, story.level)
    p["not_measured"]["space_occupant_load"] = Stop("stated_not_given", what=STATED["space_occupant_load"]).reason
    if room is None:
        why = Stop("room_not_measured", name=name, reason="its story's routes need review").reason
        for m in ("space_exit_count", "space_common_path"):
            p["not_measured"][m] = why
        return p
    if routes is None:
        why = Stop("story_not_measured", reasons="; ".join(story.stops)).reason
        for m in ("space_exit_count", "space_common_path"):
            p["not_measured"][m] = why
        return p
    p["measures"]["space_floor_area"] = room.outline.area / SF        # inside its walls (section group 3)
    try:
        p["measures"]["space_is_exit"] = _is_exit(story, rid)
    except Stop as s:
        p["not_measured"]["space_is_exit"] = s.reason
    if isinstance(access, Stop):
        p["not_measured"]["space_exit_count"] = access.reason
    else:
        p["measures"]["space_exit_count"] = len(access or {})
        p["more"]["exit_access"] = sorted(access or {})
    common = figures.get(rid)
    if isinstance(common, Stop) or common is None:
        p["not_measured"]["space_common_path"] = common.reason if common is not None else why_not
        if isinstance(common, Stop):              # the room it stops at (this one), with its stop's key: the panel's
            p["more"]["space_common_path"] = {"room_ids_not_measured": {
                rid: {"name": name, "why": common.reason, "stop": common.key}}}
        common = None
    if common is not None:
        p["measures"]["space_common_path"] = _feet(common.figure)
        p["more"]["space_common_path"] = _figure(common)
    return p


def _corridor_parts(rid, name, story, found, room) -> list:
    """The corridor's part, and one more for each further dead end in it (decision 6: each dead end is its own pair,
    its length with its own least width, never one's length with another's width): the first part holds the
    longest dead end, each further part (id "<corridor> (dead end n)") the corridor's other measures again with
    that dead end's pair, until the branch's `dead_end` part kind exists."""
    p = _part(rid, name, story.level)
    for m in ("corridor_occupant_load", "corridor_fire_rating_hours", "corridor_walls_smoke_partitions"):
        p["not_measured"][m] = Stop("stated_not_given", what=STATED[m]).reason
    if room is None or found is None:
        why = Stop("room_not_measured", name=name, reason="its story's routes need review").reason
        for m in ("corridor_width", "corridor_dead_end_length", "corridor_dead_end_least_width"):
            p["not_measured"][m] = why
        return [p]
    if found.width is not None:
        p["measures"]["corridor_width"] = found.width
    else:
        p["not_measured"]["corridor_width"] = found.width_stop
    p["more"]["centre_lines"] = [[_xy(a), _xy(b)] for a, b in found.centre_lines]
    if found.stop is not None:
        for m in ("corridor_dead_end_length", "corridor_dead_end_least_width"):
            p["not_measured"][m] = found.stop
        return [p]
    mine = sorted((d for d in found.dead_ends if d.room == rid), key=lambda d: -d.length[dead_ends.WITHOUT])
    if found.width is None and not mine:
        for m in ("corridor_dead_end_length", "corridor_dead_end_least_width"):
            p["not_measured"][m] = found.width_stop
        return [p]
    if not mine:                                         # no dead end: 0, with the corridor's own width
        p["measures"]["corridor_dead_end_length"] = 0.0
        p["measures"]["corridor_dead_end_least_width"] = _feet(found.width)
        return [p]
    out, base = [], ({**p["measures"]}, {**p["not_measured"]})
    for n, d in enumerate(mine, 1):
        # each further part built fresh: its own measures, reasons, readings and more, never the first part's
        q = p if n == 1 else {"id": f"{rid} (dead end {n})", "name": f"{name} (dead end {n})", "within": p["within"],
                              "measures": dict(base[0]), "not_measured": dict(base[1]), "more": {}}
        q["more"]["dead_end"] = {"from": _xy(d.start), "length": {k: _feet(v) for k, v in d.length.items()},
                                 "least_width": {k: _feet(v) for k, v in d.width.items()},
                                 "centre_line": {k: [_xy(x) for x in v] for k, v in d.line.items()}}
        pairs = {r: (d.length[r], d.width[r]) for r in (dead_ends.WITHOUT, dead_ends.WITH)}
        if pairs[dead_ends.WITHOUT] == pairs[dead_ends.WITH]:
            q["measures"]["corridor_dead_end_length"] = _feet(d.length[dead_ends.WITHOUT])
            q["measures"]["corridor_dead_end_least_width"] = _feet(d.width[dead_ends.WITHOUT])
        else:
            words = (f"{_feet(pairs[dead_ends.WITHOUT][0]):g} ft without the door into a room with another way out "
                     f"(the defined value), {_feet(pairs[dead_ends.WITH][0]):g} ft with it")
            for k, measure in ((0, "corridor_dead_end_length"), (1, "corridor_dead_end_least_width")):
                _readings(q, measure, [(_feet(pairs[r][k]), dead_ends.QUESTION, r)
                                       for r in (dead_ends.WITHOUT, dead_ends.WITH)], words)
        out.append(q)
    return out


def _not_measured_yet(parts: dict) -> None:
    """A measure parts.yaml lists for a kind that isn't worked out here gets a reason, never silent absence."""
    from rule_format.parts import measure_kinds
    for kind, got in parts.items():
        for part in got or []:
            for name in measure_kinds(kind):
                if name not in part["measures"] and name not in part["not_measured"]:
                    part["not_measured"][name] = Stop("not_measured_yet").reason


__all__ = ["measure", "MEASURED_FORMAT", "KINDS"]
