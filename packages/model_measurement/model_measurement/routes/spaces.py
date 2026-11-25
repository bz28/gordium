"""A story's rooms grouped into spaces: what BCNYS 1006.3.4 item 2's "rooms, areas and spaces" and a dwelling unit
(202) are made of in the model.

    spaces(story, is_exit) -> (spaces, halls)

`spaces`: the groups of rooms joined by doors or passages without crossing a corridor, a lobby, a room that is itself
an exit (a stair enclosure, an exit passageway: routes._is_exit) or the outside, each a frozenset of room ids. `halls`:
the corridors and lobbies, joined to each other the same way, each with the spaces it opens into: [(rooms, {space
index})]. A room whose use isn't given is taken as part of a space (never as a shared corridor), so it can only join
spaces together, never split one."""

HALL_USES = ("corridor", "lobby")


def _components(ids, story) -> list:
    group = {r: {r} for r in ids}

    def join(a, b):
        if a in group and b in group and group[a] is not group[b]:
            both = group[a] | group[b]
            for r in both:
                group[r] = both
    for d in story.doors.values():
        join(*d.sides)
    for a, b, _ in story.passages:
        join(a, b)
    return sorted({frozenset(g) for g in group.values()}, key=sorted)


def _touch(a, b, story) -> bool:
    """Whether a door or a passage joins a room of `a` to a room of `b`."""
    pairs = [tuple(d.sides) for d in story.doors.values()] + [(x, y) for x, y, _ in story.passages]
    return any((x in a and y in b) or (x in b and y in a) for x, y in pairs)


def spaces(story, is_exit) -> tuple:
    exits = {rid for rid in story.rooms if is_exit(story, rid)}
    hall_rooms = {rid for rid, room in story.rooms.items() if rid not in exits and room.use in HALL_USES}
    rooms = [rid for rid in story.rooms if rid not in exits and rid not in hall_rooms]
    found = _components(rooms, story)
    halls = [(h, {i for i, s in enumerate(found) if _touch(h, s, story)}) for h in _components(hall_rooms, story)]
    return found, halls
