"""Each story's floor, as routes walk it: its rooms, the rooms a route may cross, the zones they make, the doors
between them and the 12-in rings, read from the interior description's route additions (decisions 1, 1a, 4, 9 and
10 of docs/decisions/2026-11-20_route_measurement.md; the keys: docs/interior/interior_description_format.md).

    read(description) -> Floor(stops, stories)

`Floor.stops` are reasons every story's route measures need review (no `levels`, a part with no `level`, no
`passages` key). Each `Story` has its own `stops` (an unknown space, a room or door not read, a door under 24 in,
no exit ...): while any is there, paths.py gives the story no route, only the reasons. Nothing is defaulted: a key
left out is "not read", and a room whose crossing isn't stated is end-only (it only removes routes).

Lengths are inches (the interior reader turns the description's units into inches), as in `interior/`.
"""

import math
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from model_measurement.interior.read import FORMAT, INCHES, Reader, choice, name_of, number, tidy
from model_measurement.interior.stops import Stop as InteriorStop
from model_measurement.routes.stops import Stop

CLEARANCE = 12.0        # in: NFPA 101 7.6.1(2) "with a 12 in. (305 mm) clearance therefrom", both books (decision 1)
SAME = 1 / 16           # in: points this close are the same point (decision 9)
NARROWEST = 24.0        # in: a door under this puts its centre inside its jambs' rings (decision 1)
USES = ("corridor", "lobby", "day_care", "accessory_storage", "kitchen", "toilet", "closet", "workroom", "other")
END_ONLY_USES = ("accessory_storage", "kitchen", "toilet", "closet", "workroom")     # IBC 1014.2 item 4, NFPA 7.5.2.1
EXIT_KINDS = ("exterior_at_discharge", "exit_enclosure", "exit_passageway", "horizontal_exit",
              "exterior_stair_or_ramp")                                             # IBC 2009 1016.1's own list
OBSTRUCTION_KINDS = ("casework", "furniture", "equipment", "fixture")
OUTSIDE = "outside"


@dataclass
class Room:
    id: str
    name: str
    level: str
    outline: Polygon                 # inside the finished walls
    holes: list                      # Polygons: columns, chases
    obstructions: list               # Polygons: casework, furniture, equipment, fixtures (every one counts)
    crossable: bool                  # decision 1a: a route may pass through it
    end_only_why: str = ""           # why it isn't crossable (shown with the routes)


@dataclass
class Door:
    id: str
    name: str
    level: str
    centre: tuple
    along: tuple                     # unit vector along the wall
    normal: tuple                    # unit vector across it
    width: float                     # clear width
    thickness: float                 # the wall's
    sides: tuple                     # (room id or "outside", room id or "outside")
    exit_kind: str | None
    exit_id: str | None
    face: dict = field(default_factory=dict)     # room id -> +1 or -1: which way across the wall that room lies

    def jambs(self, room_id: str) -> list[tuple]:
        """The two corners of the clear opening on that room's face of the wall."""
        s = self.face[room_id]
        (cx, cy), (ax, ay), (nx, ny) = self.centre, self.along, self.normal
        w, t = self.width / 2, s * self.thickness / 2
        return [(cx + ax * u + nx * t, cy + ay * u + ny * t) for u in (-w, w)]

    def half(self, room_id: str) -> Polygon:
        """The clear opening from the wall's middle (the door centre's line) to that room's face, reaching 1/16 in
        into the room so it joins the room's outline."""
        s = self.face[room_id]
        (cx, cy), (ax, ay), (nx, ny) = self.centre, self.along, self.normal
        w, t = self.width / 2, s * (self.thickness / 2 + SAME)
        return Polygon([(cx - ax * w, cy - ay * w), (cx + ax * w, cy + ay * w),
                        (cx + ax * w + nx * t, cy + ay * w + ny * t), (cx - ax * w + nx * t, cy - ay * w + ny * t)])


@dataclass
class Zone:
    """Floor a route walks freely (decision 2): crossable rooms joined by passages, or one end-only room (with, for
    a start in it, the crossable zones beyond its passages)."""
    rooms: tuple
    crossable: bool
    floor: object                    # shapely (Multi)Polygon: the free floor, door halves in, holes and obstructions out
    corners: list                    # the floor's corners that stick into it (where a route with no clearance bends)
    rings: list                      # centres of the 12-in rings: those corners, every obstruction corner, every jamb
    doors: list                      # ids of the doors with a half on this zone
    passages: list = field(default_factory=list)   # LineStrings between its rooms and the rooms joined for a start


@dataclass
class Story:
    level: str
    name: str
    rooms: dict = field(default_factory=dict)        # id -> Room (the rooms read)
    doors: dict = field(default_factory=dict)        # id -> Door (the doors read)
    passages: list = field(default_factory=list)     # (room id, room id, LineString)
    zones: list = field(default_factory=list)
    zone_of: dict = field(default_factory=dict)      # crossable room id -> its Zone
    stops: list = field(default_factory=list)        # reasons the story's route measures need review
    outer: Polygon | None = None                     # the exterior walls' outside faces
    inner: Polygon | None = None                     # and their inside faces
    outline_stop: str | None = None                  # why those aren't read (the diagonal and areas need review)

    def exits(self) -> list:
        return [d for d in self.doors.values() if d.exit_kind]


@dataclass
class Floor:
    stops: list
    stories: dict


def read(description) -> Floor:
    """Every story's floor from an interior description (`gordium.interior/1` with the route additions)."""
    try:
        reader = _reader(description)
    except Stop as s:
        return Floor([s.reason], {})
    stops, stories = [], {}
    levels = _levels(description, reader, stops)
    if levels is None:
        return Floor(stops, {})
    for level_id, level_name in levels.items():
        stories[level_id] = Story(level_id, level_name)

    def story_of(item, what) -> Story | None:
        level = item.get("level")
        if level is None:
            stops.append(Stop("no_level", what=what, name=name_of(item)).reason)
            return None
        if not isinstance(level, str) or level not in stories:
            stops.append(Stop("level_unknown", what=what, name=name_of(item), level=level).reason)
            return None
        return stories[level]

    rooms = _list(description, "rooms", "no room is read", stops, required=True)
    if rooms is None:
        return _finish(stops, stories)
    if _twice(rooms, "room", stops):
        return _finish(stops, stories)
    for item in rooms:
        story = story_of(item, "room")
        if story is None:
            continue
        try:
            room = _room(item, reader, story.level)
        except Stop as s:
            story.stops.append(s.reason)
            story.rooms.setdefault(item["id"], None)     # known, not read: a door onto it can't be followed
            continue
        story.rooms[room.id] = room

    spaces = _list(description, "unknown_spaces", "", stops, required=False)
    unknown_ids = set()
    for n, item in enumerate(spaces or [], 1):
        story = story_of(item, "enclosed space")
        if isinstance(item.get("id"), str):
            unknown_ids.add(item["id"])
        if story is None:
            continue
        story.stops.append(Stop("unknown_space", name=name_of(item)).reason)
        if item.get("outline") is not None:
            try:
                reader.outline(item["outline"], "the enclosed space's outline")
            except InteriorStop as s:
                story.stops.append(Stop("unknown_space_not_read", n=n, reason=s.reason).reason)

    doors = _list(description, "doors", "no door is read", stops, required=True)
    if doors is None:
        return _finish(stops, stories)
    if _twice(doors, "door", stops):
        return _finish(stops, stories)
    for item in doors:
        story = story_of(item, "door")
        if story is None:
            continue
        try:
            door = _door(item, reader, story, unknown_ids, stories)
        except Stop as s:
            story.stops.append(s.reason)
            continue
        story.doors[door.id] = door

    passages = _list(description, "passages", "two rooms joined with no wall or door between them can't be told "
                     "from two rooms apart, so no story's routes are measured", stops, required=True)
    for n, item in enumerate(passages or [], 1):
        _passage(n, item, reader, stories)

    outlines = description.get("story_outlines")
    _outlines(outlines, reader, stories)

    if stops:
        return _finish(stops, stories)
    for story in stories.values():
        _coincident_doors(story)
        _zones(story)
        if not story.exits():
            story.stops.append(Stop("no_exit").reason)
    return _finish(stops, stories)


def _finish(stops, stories) -> Floor:
    """A problem with the whole description is every story's: each story carries it, so no story's routes are
    measured while it stands (a story left unzoned is never measured without a reason)."""
    for story in stories.values():
        for reason in stops:
            if reason not in story.stops:
                story.stops.append(reason)
    return Floor(stops, stories)


def _coincident_doors(story) -> None:
    """Two doors with one centre (a door listed twice): which one a route passes is unclear."""
    doors = list(story.doors.values())
    for i, a in enumerate(doors):
        for b in doors[i + 1:]:
            if math.dist(a.centre, b.centre) <= SAME:
                story.stops.append(Stop("doors_same_centre", a=a.name, b=b.name).reason)


# --- reading -------------------------------------------------------------------------------------------------------

def _reader(description) -> Reader:
    if not isinstance(description, dict):
        raise Stop("description", reason="it isn't a mapping")
    if description.get("format") != FORMAT:
        raise Stop("description", reason=f"its format isn't {FORMAT} (it says {description.get('format')})")
    units = description.get("units")
    if not isinstance(units, str) or units not in INCHES:
        raise Stop("description", reason=f"its units ({units}) aren't one of in, ft, mm, m")
    return Reader(units)


def _list(description, key, words, stops, required):
    got = description.get(key)
    if got is None:
        if required:
            stops.append(Stop("key_left_out", key=key, words=words).reason)
        return None
    if not isinstance(got, list) or not all(isinstance(i, dict) for i in got):
        stops.append(Stop("description", reason=f"`{key}` isn't a list of mappings").reason)
        return None
    return got


def _twice(items, what, stops) -> bool:
    ids = [i.get("id") for i in items]
    bad = False
    for n, item in enumerate(items, 1):
        if not isinstance(item.get("id"), str) or not item["id"].strip():
            stops.append(Stop("description", reason=f"{what} #{n} has no text `id`").reason)
            bad = True
    for i in sorted({i for i in ids if isinstance(i, str) and ids.count(i) > 1}):
        stops.append(Stop("id_twice", count=ids.count(i), what=what, id=i).reason)
        bad = True
    return bad


def _levels(description, reader, stops):
    got = description.get("levels")
    if got is None:
        stops.append(Stop("no_levels").reason)
        return None
    if not isinstance(got, list):
        stops.append(Stop("description", reason="`levels` isn't a list").reason)
        return None
    levels = {}
    for n, item in enumerate(got, 1):
        try:
            if not isinstance(item, dict):
                raise InteriorStop("not_a_mapping", what="level", n=n)
            if not isinstance(item.get("id"), str) or not item["id"].strip():
                raise InteriorStop("missing", what="its text `id`")
            if not isinstance(item.get("name"), str):
                raise InteriorStop("missing", what="its `name`")
            reader.length(item.get("elevation"), "its elevation")
        except InteriorStop as s:
            stops.append(Stop("level_entry", n=n, reason=s.reason).reason)
            return None
        if item["id"] in levels:
            stops.append(Stop("level_twice", count=[i.get("id") for i in got].count(item["id"]), id=item["id"]).reason)
            return None
        levels[item["id"]] = item["name"]
    return levels


def _flag(item, key):
    """True, False, or None (not given); anything else isn't read."""
    got = item.get(key)
    if got is None or isinstance(got, bool):
        return got
    raise InteriorStop("choice", what=f"`{key}`", got=got, choices="true, false")


def _room(item, reader, level) -> Room:
    name = name_of(item)
    if item.get("floor") is None:
        raise Stop("room_no_floor", name=name, reason="no `floor`")
    try:
        sleeping = item.get("sleeping")
        if not isinstance(sleeping, bool):
            raise InteriorStop("flag_missing", what="room", name=name, question="a sleeping room", key="sleeping")
        outline = reader.outline(item["floor"], "the room's floor outline")
        use = item.get("use")
        if use is not None:
            choice(use, USES, "the room's `use`")
        lockable, through = _flag(item, "lockable"), _flag(item, "pass_through")
        holes = _outlines_of(item, "holes", reader, "a hole")
        obstructions = []
        got = item.get("obstructions")
        if got is None:
            raise InteriorStop("missing", what="`obstructions` (say `obstructions: []` for none)")
        if not isinstance(got, list):
            raise InteriorStop("not_a_list", key="obstructions")
        for n, ob in enumerate(got, 1):
            if not isinstance(ob, dict):
                raise InteriorStop("not_a_mapping", what="obstruction", n=n)
            obstructions.append(reader.outline(ob.get("outline"), f"obstruction #{n}'s outline"))
            choice(ob.get("kind"), OBSTRUCTION_KINDS, f"obstruction #{n}'s `kind`")
            if not isinstance(ob.get("fixed"), bool):
                raise InteriorStop("missing", what=f"obstruction #{n}'s `fixed` (true or false)")
    except InteriorStop as s:
        raise Stop("room_not_read", name=name, reason=s.reason) from None
    # decision 1a: end-only always wins
    end_only = ("a sleeping room" if sleeping else f"a {use} room" if use in END_ONLY_USES
                else "it can be locked (`lockable: true`)" if lockable is True else "")
    if through is True and end_only:
        raise Stop("pass_through_refused", name=name, why=f"it is {end_only}" if not end_only.startswith("it")
                   else end_only)
    why = (end_only or ("no `use` is given" if use is None else
                        "whether it can be locked isn't given (`lockable`)" if lockable is None else
                        "`pass_through` isn't given" if through is None else
                        "it isn't a corridor, nor marked `pass_through: true`" if not (use == "corridor" or through)
                        else ""))
    return Room(item["id"], name, level, outline, holes, obstructions, crossable=not why, end_only_why=why)


def _outlines_of(item, key, reader, what) -> list:
    got = item.get(key)
    if got is None:
        raise InteriorStop("missing", what=f"`{key}` (say `{key}: []` for none)")
    if not isinstance(got, list):
        raise InteriorStop("not_a_list", key=key)
    return [reader.outline(h, f"{what} #{n}") for n, h in enumerate(got, 1)]


def _door(item, reader, story, unknown_ids, stories) -> Door:
    name = name_of(item)
    plan, sides = item.get("plan"), item.get("sides")
    try:
        if plan is None:
            raise InteriorStop("missing", what="the door's `plan` (where its clear opening is)")
        if sides is None:
            raise InteriorStop("missing", what="the door's `sides` (what it joins)")
        if not isinstance(plan, dict):
            raise InteriorStop("not_a_mapping", what="the door's plan", n=1)
        centre = reader.point(plan.get("centre"), 2, "the door's centre")
        along = plan.get("along")
        if not isinstance(along, (list, tuple)) or len(along) != 2:
            raise InteriorStop("not_a_point", what="the door's `along`", n=2)
        ax, ay = (number(v, "the door's `along`") for v in along)
        size = math.hypot(ax, ay)
        if not (size > 0 and math.isfinite(size)):
            raise InteriorStop("not_positive", what="the length of the door's `along`", value=size)
        width = reader.size(plan.get("clear_width"), "the door's clear width")
        thickness = reader.size(plan.get("wall_thickness"), "the door's wall thickness")
        if not isinstance(sides, list) or len(sides) != 2 or not all(isinstance(s, str) for s in sides):
            raise InteriorStop("choice", what="the door's `sides`", got=sides,
                               choices="two room ids, or a room id and 'outside'")
        kind, exit_id = item.get("exit_kind"), item.get("exit_id")
        if kind is not None:
            choice(kind, EXIT_KINDS, "the door's `exit_kind`")
            if not isinstance(exit_id, str) or not exit_id.strip():
                raise InteriorStop("missing", what="the exit's `exit_id` (which exit the door enters)")
        elif exit_id is not None:
            raise InteriorStop("missing", what="the door's `exit_kind` (it gives an `exit_id`)")
    except InteriorStop as s:
        raise Stop("door_not_read", name=name, reason=s.reason) from None
    if width < NARROWEST:
        raise Stop("door_narrow", name=name, width=tidy(width))
    if kind == "exterior_stair_or_ramp":
        raise Stop("exit_stair_or_ramp", name=name)
    a = (ax / size, ay / size)
    door = Door(item["id"], name, story.level, centre, a, (-a[1], a[0]), width, thickness, tuple(sides), kind,
                exit_id)
    if sides == [OUTSIDE, OUTSIDE]:
        raise Stop("door_side", name=name, side=OUTSIDE, what="on both sides")
    for side in sides:
        if side == OUTSIDE:
            continue
        what = ("an enclosed space with no room drawn in it" if side in unknown_ids else
                "a room that isn't read" if side in story.rooms and story.rooms[side] is None else
                "a room on another story" if any(side in s.rooms for s in stories.values() if s is not story) else
                "not a room given" if side not in story.rooms else "")
        if what:
            raise Stop("door_side", name=name, side=side, what=what)
        door.face[side] = _face(door, story.rooms[side])
    if len(door.face) == 2 and len(set(door.face.values())) == 1:
        raise Stop("door_same_side", name=name)
    return door


def _face(door: Door, room: Room) -> int:
    """Which way across the wall the room lies: its face of the opening is on the room's outline (within 1/16 in)
    and a point 1 in beyond that face is in the room."""
    fits = []
    for s in (1, -1):
        door.face[room.id] = s
        face = door.jambs(room.id)
        mid = ((face[0][0] + face[1][0]) / 2, (face[0][1] + face[1][1]) / 2)
        probe = Point(mid[0] + door.normal[0] * s, mid[1] + door.normal[1] * s)
        if all(room.outline.boundary.distance(Point(p)) <= SAME for p in (*face, mid)) and room.outline.contains(probe):
            fits.append(s)
    del door.face[room.id]
    if len(fits) != 1:
        raise Stop("door_not_in_wall", name=door.name, room=room.name)
    return fits[0]


def _passage(n, item, reader, stories) -> None:
    rooms, line = item.get("rooms"), item.get("line")
    holder = None
    for story in stories.values():
        if isinstance(rooms, list) and any(isinstance(r, str) and r in story.rooms for r in rooms):
            holder = story
            break
    try:
        if not isinstance(rooms, list) or len(rooms) != 2 or not all(isinstance(r, str) for r in rooms) \
                or rooms[0] == rooms[1]:
            raise InteriorStop("choice", what="the passage's `rooms`", got=rooms, choices="two room ids")
        points = reader.points(line, 2, "the passage's line", 2)
        if len(points) != 2 or math.dist(*points) <= SAME:
            raise InteriorStop("not_a_polyline", what="the passage's line (two points apart)")
        if holder is None or not all(r in holder.rooms for r in rooms):
            raise InteriorStop("missing", what="one of the passage's rooms on its story")
    except InteriorStop as s:
        for story in ([holder] if holder else stories.values()):
            story.stops.append(Stop("passage_not_read", n=n, reason=s.reason).reason)
        return
    if any(holder.rooms[r] is None for r in rooms):
        return                                       # a room not read: its story needs review already
    seg = LineString(points)
    for r in rooms:
        if not holder.rooms[r].outline.buffer(SAME).covers(seg):
            holder.stops.append(Stop("passage_off", n=n, room=holder.rooms[r].name).reason)
            return
    holder.passages.append((rooms[0], rooms[1], seg))


def _outlines(outlines, reader, stories) -> None:
    if outlines is None:
        for story in stories.values():
            story.outline_stop = Stop("key_left_out", key="story_outlines", words="the diagonal and the story's "
                                      "area aren't measured").reason
        return
    given = {}
    for n, item in enumerate(outlines if isinstance(outlines, list) else [None], 1):
        level = item.get("level") if isinstance(item, dict) else None
        if level not in stories:
            for story in stories.values():
                story.outline_stop = Stop("outline_not_read", reason=f"`story_outlines` #{n} isn't on a level "
                                          "given").reason
            return
        given.setdefault(level, []).append(item)
    for level, story in stories.items():
        items = given.get(level, [])
        if len(items) != 1:
            story.outline_stop = Stop("outline_not_read", reason=f"{len(items)} outlines are given for it").reason
            continue
        try:
            story.outer = reader.outline(items[0].get("outer"), "the story's outer outline")
            story.inner = reader.outline(items[0].get("inner"), "the story's inner outline")
        except InteriorStop as s:
            story.outline_stop = Stop("outline_not_read", reason=s.reason).reason


# --- zones (decision 1) --------------------------------------------------------------------------------------------

def _zones(story: Story) -> None:
    rooms = {k: r for k, r in story.rooms.items() if r is not None}
    ids = sorted(rooms)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ra, rb = rooms[a], rooms[b]
            if not ra.outline.intersects(rb.outline):
                continue
            area = ra.outline.intersection(rb.outline).area
            if area > SAME * min(ra.outline.length, rb.outline.length):
                story.stops.append(Stop("rooms_overlap", a=ra.name, b=rb.name, area=tidy(area)).reason)
    # crossable rooms joined by passages: one zone each group (an end-only room is never merged)
    group = {k: k for k in rooms if rooms[k].crossable}

    def top(k):
        while group[k] != k:
            k = group[k]
        return k

    for a, b, _ in story.passages:
        if a in group and b in group:
            group[top(a)] = top(b)
    together = {}
    for k in sorted(group):
        together.setdefault(top(k), []).append(k)
    for members in together.values():
        try:
            zone = region(story, members, crossable=True)
        except Stop as s:
            story.stops.append(s.reason)
            continue
        story.zones.append(zone)
        for k in members:
            story.zone_of[k] = zone


def region(story: Story, room_ids, crossable: bool = False, joined=()) -> Zone:
    """The free floor of these rooms (joined by the passages between them), with its corners and rings. `joined`:
    extra passages to take (an end-only room's, for a start in it)."""
    ids = set(room_ids)
    rooms = [story.rooms[k] for k in sorted(ids)]
    lines = [seg for a, b, seg in story.passages if a in ids and b in ids] + list(joined)
    doors = []
    pieces = [r.outline for r in rooms] + [seg.buffer(SAME, cap_style="flat") for seg in lines]
    for door in story.doors.values():
        mine = [k for k in door.face if k in ids]
        if len(mine) == 2:
            raise Stop("door_within_zone", name=door.name)
        if mine:
            doors.append(door.id)
            pieces.append(door.half(mine[0]))
    whole = unary_union(pieces)
    if whole.geom_type != "Polygon":
        raise Stop("zone_in_pieces", rooms=", ".join(r.name for r in rooms), count=len(getattr(whole, "geoms", [])))
    cut = [h for r in rooms for h in r.holes] + [o for r in rooms for o in r.obstructions]
    floor = whole.difference(unary_union(cut)) if cut else whole
    polys = [orient(p, 1.0) for p in getattr(floor, "geoms", [floor]) if p.geom_type == "Polygon" and p.area > 0]
    corners = [v for p in polys for v in _reflex(p)]
    rings = []
    for c in [j for d in doors for k in story.doors[d].face if k in ids for j in story.doors[d].jambs(k)] + corners \
            + [v for r in rooms for o in r.obstructions for v in o.exterior.coords[:-1]]:
        if all(math.dist(c, q) > SAME for q in rings):
            rings.append(tuple(c))
    for d in doors:                                  # decision 2: no route is defined through it
        if any(math.dist(story.doors[d].centre, c) < CLEARANCE - 1e-6 for c in rings):
            raise Stop("door_centre_in_ring", name=story.doors[d].name)
    return Zone(tuple(sorted(ids)), crossable, floor, corners, rings, doors, lines)


def _reflex(poly: Polygon) -> list[tuple]:
    """The corners of a polygon (exterior counter-clockwise, holes clockwise) that stick into it: a right turn."""
    out = []
    for ring in [poly.exterior, *poly.interiors]:
        pts = list(ring.coords)[:-1]
        for i, v in enumerate(pts):
            a, b = pts[i - 1], pts[(i + 1) % len(pts)]
            e1, e2 = (v[0] - a[0], v[1] - a[1]), (b[0] - v[0], b[1] - v[1])
            cross = e1[0] * e2[1] - e1[1] * e2[0]
            if cross < -1e-9 * math.hypot(*e1) * math.hypot(*e2):
                out.append(tuple(v))
    return out
