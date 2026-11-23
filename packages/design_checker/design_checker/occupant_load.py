"""The Building Code's occupant loads from each room's stated function (2025 BCNYS 1004.5 and Table 1004.5; section group
3 of docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md): plain arithmetic over the route measuring's
areas and the frozen table of occupant load factors the rulebook keeps
(new_york_state_building/5_building_code_rules/drafted/records/occupant_load_factors.yaml, every factor quoted from
its row of Table 1004.5 and checked against the page images' second reading by rule_format's tests). No AI.

    apply(parts, description, factors, building) -> parts   (the same parts, occupant loads filled where they can be)

A room states its function (`function`, one of the table's ids: docs/interior/interior_description_format.md). The
area is the room's inside its walls (`space_floor_area`):
- a function with a **net** factor: area / factor, one value;
- a **gross** factor: two readings (the coordinator's decision, 2026-11-23: pass only if both pass): the room's own
  area / factor, and that area grossed up by the story's share of what no net room holds (202 FLOOR AREA, GROSS:
  within the exterior walls, without deduction for corridors, stairways, closets, interior walls), i.e. its area x
  (the story's gross floor area - the net rooms' areas) / (the gross rooms' areas), / factor.
1004.5.1 lets a design take more occupants, up to one per 7 sq ft: unless the building states it takes no increase
(`occupant_load_increased: false`), the upper reading is at least the area / 7.

A room that is itself an exit, a corridor, or a closet, toilet or accessory storage room with no function stated
holds no occupant load of its own (its area is the gross rooms' support). Any other room with no function, or a
function the table sends elsewhere (fixed seating, 1004.6; concentrated business, 1004.8; bowling centers; malls,
402.8.2), leaves its load, and its story's, not measured: never a guess. A room others egress through (1004.2:
`pass_through: true`, or one a closet or toilet is served through) carries their loads too: its load is the
cumulative one only where no other room's path is known to pass through it, so such a room's load is left not
measured. Stories are not added together (1004.2.3).
"""

from rule_format.rulebook import load

SUPPORT_USES = ("corridor", "closet", "toilet", "accessory_storage")   # no load of their own unless a function says
QUESTION = "occupant_load_area"
LOWER, UPPER = "room_area", "grossed_up_or_increased"
NOT_GIVEN = ("the room's function (Table 1004.5) isn't stated, so its occupant load isn't worked out "
             "(the room mark Gordium: Function)")
UNKNOWN = "the room's function {f!r} is none of Table 1004.5's (docs/interior/interior_description_format.md)"
ELSEWHERE = "the function {f} takes its occupant load from {where}, not a factor: a person states it"
THROUGH = ("other rooms' egress passes through it (1004.2: their occupant loads add to its own), which isn't summed "
           "yet")
STORY_OPEN = "a room on the story has no occupant load worked out ({names}), so the story's isn't either"


def factors_of(path) -> dict:
    """{function id: {"factor": number or None, "area": "gross"|"net"|None, "elsewhere": section or None}} and the
    1004.5.1 cap, from the rulebook's frozen table."""
    data = load(path)
    return {"functions": data["functions"], "increase_cap": data["increase_cap"]["sq_ft_per_occupant"]}


def apply(parts: dict, description: dict, factors: dict, building: dict | None) -> dict:
    rooms = {r["id"]: r for r in (description or {}).get("rooms") or [] if isinstance(r, dict) and "id" in r}
    increase_ruled_out = isinstance(building, dict) and building.get("occupant_load_increased") is False
    cap = factors["increase_cap"]
    spaces = parts.get("space") or []
    for story in parts.get("story") or []:
        mine = [p for p in spaces if p.get("within") == story["id"]]
        gross = story["measures"].get("story_gross_floor_area")
        loads, open_ = [], []
        plan = []
        for p in mine:
            room = rooms.get(p["id"]) or {}
            fn = room.get("function")
            area = p["measures"].get("space_floor_area")
            if p["measures"].get("space_is_exit") or (fn is None and room.get("use") in SUPPORT_USES):
                plan.append((p, None, None))
                continue
            entry = factors["functions"].get(fn) if isinstance(fn, str) else None
            if area is None or entry is None or entry.get("factor") is None:
                why = ("the room's floor area isn't measured" if area is None else NOT_GIVEN if fn is None else
                       UNKNOWN.format(f=fn) if entry is None else ELSEWHERE.format(f=fn, where=entry["elsewhere"]))
                p["not_measured"]["space_occupant_load"] = why
                open_.append(p.get("name") or p["id"])
                continue
            plan.append((p, entry, area))
        net_area = sum(a for _, e, a in plan if e and e["area"] == "net")
        gross_area = sum(a for _, e, a in plan if e and e["area"] == "gross")
        share = ((gross - net_area) / gross_area) if (gross is not None and gross_area > 0 and gross >= net_area +
                                                     gross_area) else None
        for p, e, a in plan:
            if e is None:
                continue
            low = a / e["factor"]
            high = (a * share / e["factor"]) if e["area"] == "gross" and share is not None else \
                (None if e["area"] == "gross" else low)
            if high is not None and not increase_ruled_out:
                high = max(high, a / cap)
            room = rooms.get(p["id"]) or {}
            if room.get("pass_through"):
                p["not_measured"]["space_occupant_load"] = THROUGH
                loads.append((low, high))
                continue
            loads.append((low, high))
            _give(p, "space_occupant_load", low, high)
        if open_:
            story["not_measured"]["story_occupant_load"] = STORY_OPEN.format(names=", ".join(open_))
        elif loads:
            low = sum(x for x, _ in loads)
            high = None if any(h is None for _, h in loads) else sum(h for _, h in loads)
            if high is not None and not increase_ruled_out and gross is not None:
                high = max(high, gross / cap)
            _give(story, "story_occupant_load", low, high)
    return parts


def _give(part: dict, name: str, low: float, high: float | None) -> None:
    """One value where the readings agree; two named readings where they differ; none where the upper one can't
    be worked out (the gross share isn't known: the story's gross floor area isn't measured)."""
    if high is None:
        part["not_measured"][name] = ("the story's gross floor area isn't measured, so the gross-function rooms' "
                                      "share of it can't be")
        return
    part["not_measured"].pop(name, None)
    if abs(high - low) < 1e-9:
        part["measures"][name] = low
        return
    part.setdefault("readings", {})[name] = [{"value": low, "named": {QUESTION: LOWER}},
                                             {"value": high, "named": {QUESTION: UPPER}}]
    part["not_measured"][name] = (f"given as two readings ({low:.1f} from the room's own area; {high:.1f} grossed "
                                  f"up by the story's corridors, stairs and walls, or at one occupant per 7 sq ft "
                                  f"where 1004.5.1's increase isn't ruled out): a rule reading it complies only if it "
                                  f"complies under both, fails only if it fails under both")
