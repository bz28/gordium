"""The story's areas (decision 8 of docs/decisions/2026-11-20_route_measurement.md): two readings each, the less
favourable governing, as the checker takes readings.

    building_area(story)             -> [Reading inside the exterior walls, Reading to their outer faces]
    accessory_area(story, uses)      -> [Reading inside its walls, Reading to the outer faces of the walls round them]
    day_care_net_area(story, uses)   -> square inches

IBC 2009 502.1 measures building area "within surrounding exterior walls" without saying which face, and nothing
says where a storage room's area stops, so each is two named readings, one open question each (the route note's open
question 3): `story_building_area` the story outline's inner and outer faces (the outlines have no holes: vent shafts
and courts are outside them); `story_accessory_area` the rooms marked `accessory_storage`, inside their walls, and to
the outer faces of the walls round them. The walls round a room aren't each given a thickness, so the outer reading
takes the room's outline grown by the thickest wall the story shows (each door's wall, and the exterior walls'
greatest thickness between the two outlines) and clipped to the story's outer outline less every other room: it can
only take in more than the walls (at a wall's junction with another), never less, the less favourable side for a
limit on storage. A room's columns are counted in (the larger area, again the less favourable).

Day-care net area: the rooms marked `day_care`, inside their walls (Table 1004.1.1 "net"); the computed occupant load
is that divided by 35 (shown beside a stated one).

Every area that counts uses needs review while a room on the story isn't read, has no `use`, two rooms overlap, or
an enclosed space has no room drawn in it (its use unknown). Square inches here; the parts give square feet.
"""

from dataclasses import dataclass

from shapely.geometry import JOIN_STYLE
from shapely.ops import unary_union

from model_measurement.routes.floor import SAME, Story
from model_measurement.routes.stops import Stop

STORY_AREA_QUESTION = "story_area_face"            # 502.1: inside the exterior walls, or to their outer faces
ACCESSORY_AREA_QUESTION = "accessory_area_face"    # a storage room: inside its walls, or to their outer faces
DAY_CARE_FACTOR = 35                               # sq ft per occupant, net (IBC 2009 Table 1004.1.1; NFPA 7.3.1.2)


@dataclass
class Reading:
    value: float              # sq in
    question: str
    answer: str               # "inside" or "outer_faces"


def building_area(story: Story) -> list[Reading]:
    if story.outer is None or story.inner is None:
        raise Stop("outline_needed", reason=story.outline_stop or "no outline is given for it")
    return [Reading(story.inner.area, STORY_AREA_QUESTION, "inside"),
            Reading(story.outer.area, STORY_AREA_QUESTION, "outer_faces")]


def _rooms_known(story: Story, uses: dict, unknown_spaces: list) -> None:
    """Stop unless every room on the story is read, says its use, and no two overlap, and no space is unknown."""
    for name in unknown_spaces:
        raise Stop("area_unknown_space", name=name)
    for rid, room in sorted(story.rooms.items()):
        if room is None:
            raise Stop("area_room_not_read", name=rid)
        if uses.get(rid) is None:
            raise Stop("area_no_use", name=room.name)
    rooms = sorted(story.rooms.values(), key=lambda r: r.id)
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            if a.outline.intersection(b.outline).area > SAME * min(a.outline.length, b.outline.length):
                raise Stop("area_rooms_overlap", a=a.name, b=b.name)


def _thickest_wall(story: Story) -> float:
    walls = [d.thickness for d in story.doors.values()]
    if story.outer is not None and story.inner is not None:
        walls.append(story.inner.exterior.hausdorff_distance(story.outer.exterior))
    return max(walls, default=0.0)


def accessory_area(story: Story, uses: dict, unknown_spaces=()) -> list[Reading]:
    _rooms_known(story, uses, list(unknown_spaces))
    storage = [r for r in story.rooms.values() if uses[r.id] == "accessory_storage"]
    inside = sum(r.outline.area for r in storage)
    if story.outer is None:
        raise Stop("outline_needed", reason=story.outline_stop or "no outline is given for it")
    t = _thickest_wall(story)
    others = unary_union([r.outline for r in story.rooms.values() if uses[r.id] != "accessory_storage"])
    room_for_walls = story.outer.difference(others) if not others.is_empty else story.outer
    grown = unary_union([r.outline.buffer(t, join_style=JOIN_STYLE.mitre) for r in storage]) if storage else None
    outer = grown.intersection(room_for_walls).area if grown is not None else 0.0
    return [Reading(inside, ACCESSORY_AREA_QUESTION, "inside"),
            Reading(max(outer, inside), ACCESSORY_AREA_QUESTION, "outer_faces")]


def day_care_net_area(story: Story, uses: dict, unknown_spaces=()) -> float:
    _rooms_known(story, uses, list(unknown_spaces))
    return sum(r.outline.area for r in story.rooms.values() if uses[r.id] == "day_care")
