"""Lot facts in, project file out: the bridge from a measured model to the checker and the report (PR 10).

A project file (see packages/project_report/README.md) is title, jurisdiction, zone and measurements, each
measurement with `from`: where its value came from. Here `from` is the working: how it was measured, between
which points, or why there is no value.
"""

import math
from pathlib import Path

from rule_format.rulebook import load

from .measure import fact_conflicts as measure_conflicts
from .measure import measure
from .read_3dm import read_site

FACT_FIELDS = {"title", "address", "jurisdiction", "zone", "use", "lot_id", "lot_surveyed", "street_line", "corner_lot",
               "grade_elevation", "ground_is_flat", "main_building", "stories", "sleeping_rooms", "parking_spaces",
               "dwelling_units", "rooms_let_for_profit", "conversion", "occupants",
               "occupants_most_in_one_unit", "attached_units_in_building", "abuts_r1_district",
               "unrelated_persons", "unrelated_persons_with_children", "owner_occupied", "functional_family_unit",
               "home_occupation", "home_occupation_area", "home_occupation_unit_area", "accessory_dwelling_unit",
               "primary_buildings", "primary_buildings_same_use", "south_hill_overlay",
               "stream_near_lot", "stream_distance",
               "grade_points", "grade_from", "grade_is", "address_street_line", "accessory_buildings", "accessory_frame",
               "eaves_confirmed", "ground_assumed", "plan_north_deg", "street_ids"}
CONFIRMATION_FIELDS = {"overhang", "value", "source", "confirmed_by", "date"}


def _number(x) -> bool:
    return type(x) in (int, float) and math.isfinite(x)


def _point(p) -> bool:
    return isinstance(p, list) and len(p) == 2 and all(_number(v) for v in p)


def fact_conflicts(facts: dict) -> list[str]:
    """Lot facts that are each well formed but disagree with each other. Not a refusal (the check runs; the rows they
    decide need review): the panel shows each one, so the architect can correct the count."""
    return [message for message, _ in fact_conflict_rows(facts)]


def fact_conflict_rows(facts: dict) -> list[tuple[str, tuple]]:
    """fact_conflicts, each with the facts to correct it (the panel's "Enter …" button asks those). The measuring sets
    each of those facts aside with the same reason (measure.fact_conflicts: one list). The use is set aside too when it
    is one of the answers, but it is changed in the start box (Edit site…), not by the Enter button."""
    return [(why, tuple(n for n in names if n != "use")) for why, names in measure_conflicts(facts)]


def fact_problems(facts: dict) -> list[str]:
    """What's wrong with lot facts, by field. One check for every way facts arrive (a file, the Rhino command)."""
    problems = [f"unknown lot fact {k!r}" for k in sorted(set(facts) - FACT_FIELDS)]
    text = {"title", "address", "jurisdiction", "zone", "use", "lot_id", "main_building"}
    problems += [f"{k} must be text" for k in sorted(text & set(facts))
                 if facts[k] is not None and not isinstance(facts[k], str)]
    if facts.get("plan_north_deg") is not None and not _number(facts["plan_north_deg"]):
        problems.append("plan_north_deg must be a number (degrees the plan is turned from true north)")
    if facts.get("grade_elevation") is not None and not _number(facts["grade_elevation"]):
        problems.append("grade_elevation must be a number (the ground level, in feet)")
    for k in ("stories", "sleeping_rooms", "parking_spaces", "dwelling_units", "rooms_let_for_profit", "occupants",
              "unrelated_persons", "unrelated_persons_with_children"):
        if facts.get(k) is not None and not (type(facts[k]) is int and facts[k] >= 0):
            problems.append(f"{k} must be a whole number, 0 or more")
    for k in ("home_occupation_area", "home_occupation_unit_area"):               # square feet, never rounded
        if facts.get(k) is not None and not (_number(facts[k]) and facts[k] >= 0):
            problems.append(f"{k} must be a number of square feet, 0 or more")
    if facts.get("stream_distance") is not None and not (_number(facts["stream_distance"]) and facts["stream_distance"] >= 0):
        problems.append("stream_distance must be a number of feet, 0 or more")       # as typed, never rounded
    for k in ("occupants_most_in_one_unit", "attached_units_in_building",       # at least one, by definition
              "primary_buildings"):
        if facts.get(k) is not None and not (type(facts[k]) is int and facts[k] >= 1):
            problems.append(f"{k} must be a whole number, 1 or more")
    for k in ("corner_lot", "lot_surveyed", "ground_is_flat", "accessory_frame", "conversion", "abuts_r1_district",
              "owner_occupied", "functional_family_unit", "home_occupation", "accessory_dwelling_unit",
              "primary_buildings_same_use", "south_hill_overlay", "stream_near_lot"):
        if facts.get(k) is not None and not isinstance(facts[k], bool):
            problems.append(f"{k} must be yes or no (true / false)")
    points = facts.get("grade_points")
    if points is not None and not (isinstance(points, list) and points and all(
            isinstance(p, list) and len(p) == 3 and all(_number(v) for v in p) for p in points)):
        problems.append("grade_points must be a list of spot grades, each [x, y, z] in feet")
    if facts.get("grade_from") not in (None, "spot", "terrain", "finished_spots"):
        problems.append("grade_from must be spot, terrain or finished_spots")
    if facts.get("ground_assumed") not in (None, "flat"):
        problems.append("ground_assumed must be flat (or not given)")
    if facts.get("grade_is") not in (None, "finished", "existing"):
        problems.append("grade_is must be finished or existing")
    for k in ("street_line", "address_street_line"):
        street = facts.get(k)
        if street is not None and not (isinstance(street, list) and street and all(
                isinstance(s, list) and len(s) == 2 and all(_point(p) for p in s) for s in street)):
            problems.append(f"{k} must be a list of lot lines, each two points [[x, y], [x, y]]")
    confirmed = facts.get("eaves_confirmed")
    if confirmed is not None and not (isinstance(confirmed, list) and all(
            isinstance(c, dict) and c.keys() == CONFIRMATION_FIELDS and isinstance(c["overhang"], str)
            and c["value"] is True and all(isinstance(c[k], str) and c[k].strip() for k in ("source", "confirmed_by"))
            and c["date"] for c in confirmed)):
        problems.append("eaves_confirmed must be a list of {overhang (the overhang's fingerprint, as the check names "
                        "it), value: true, source, confirmed_by, date}: an architect's confirmation that it is eaves")
    listed = facts.get("accessory_buildings")
    if listed is not None and not (isinstance(listed, list) and all(isinstance(i, str) for i in listed)):
        problems.append("accessory_buildings must be a list of object ids (the solids that are accessory buildings)")
    # street_ids (the street each street line is on) is never refused here: names that don't match the lines one
    # for one are set aside by the measuring, which says so (stop street_names_stale); refusing them made the check
    # fail and saved facts unreadable (review round 7, P1)
    return problems


def load_facts(path: Path) -> dict:
    """A lot facts file: `lot_facts:` with the fields above. Anything else is an error, so a typo can't
    silently drop a fact."""
    data = load(path) or {}
    facts = data.get("lot_facts") if isinstance(data, dict) else None
    if not isinstance(facts, dict) or set(data) != {"lot_facts"}:
        raise ValueError(f"{path}: a lot facts file has exactly one field, lot_facts")
    problems = fact_problems(facts)
    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    return facts


def _num(x) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def working(record: dict, model: str) -> str:
    """The `from` text for one measurement: how it was found, or why it couldn't be."""
    if record["value"] is None:
        text = f"not measured: {record['reason']}"
    elif record["how"].startswith("stated"):
        return f"{record['how']} (lot facts)"
    else:
        text = f"measured from {model}: {record['how']}"
        if record["points"]:
            (ax, ay), (bx, by) = record["points"]
            text += f"; between ({_num(ax)}, {_num(ay)}) and ({_num(bx)}, {_num(by)})"
    if record["readings"]:
        shown = "; ".join(f"{r['reading']} = {_num(r['value'])}" for r in record["readings"])
        text += f" [readings: {shown}]"
    if record.get("outline"):           # the lot lines read from a cleaned outline: said, so it can be traced
        text += f" ({record['outline']})"
    return text


def project(model_path: Path, facts: dict) -> dict:
    """The project file for a model: the facts' title, jurisdiction and zone, and every measurement."""
    problems = fact_problems(facts)
    if problems:
        raise ValueError("lot facts: " + "; ".join(problems))
    measured = measure(read_site(model_path, facts), facts)
    return {"title": facts.get("title") or Path(model_path).stem, "jurisdiction": facts.get("jurisdiction"),
            "zone": facts.get("zone"),
            "measurements": {name: {"value": r["value"], "from": working(r, Path(model_path).name)}
                             for name, r in measured.items()}}
