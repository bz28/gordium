"""A hint for the architect's high-rise question, never a decision (Chapter 4: docs/decisions/
2026-11-26_ny_building_chapter_4_egress.md, part b and the marks PR).

BCNYS 202 HIGH-RISE BUILDING (p.50, lines 3-4): "A building with an occupied floor or occupiable roof located more
than 75 feet (22 860 mm) above the lowest level of fire department vehicle access." Where fire department vehicles
reach the building isn't in the model, and the road may be lower than any ground the model shows (off the modeled
site, down a slope), so the model never settles it: `high_rise_building` stays the architect's stated fact, and
unstated, Section 403's flags show and 403.5.2's band holds the story exit rules.

What the model can show, as a figure on the question card only: how far the highest level it holds (a roof level
included where the model has one: an occupiable roof counts) is above the lowest FINISHED ground it states (the flat finished ground or the
lowest finished spot grade the lot facts give, and the lowest finished ground stated at any opening or area well's
floor). Existing ground is never used, and with no finished ground, no level list or a level that can't be read,
there is no figure. Shown only where it is under 75 ft, with what would still make the building a high-rise (vehicle
access that much lower, a higher occupied floor or roof, or one in a linked model: the description holds this
document's levels only), as Gordium's reading for the architect to answer."""

import math

from model_measurement.interior.read import Reader
from model_measurement.interior.stops import Stop as InteriorStop
from model_measurement.routes.story_place import _stated_ground

LIMIT_IN = 75 * 12.0          # 202 HIGH-RISE BUILDING: more than 75 feet


def figure(description, ground) -> dict | None:
    """{"height_in": the highest level's elevation over the lowest finished ground, "level": its name,
    "ground_in": that ground} in inches, or None where the model can't give one (see the module's words)."""
    if not isinstance(description, dict) or not isinstance(ground, dict) or "none" in ground:
        return None
    levels = description.get("all_levels")
    if not isinstance(levels, list) or not levels or not isinstance(description.get("units"), str):
        return None
    try:
        reader = Reader(description["units"])
    except Exception:
        return None
    top, name = None, None
    for item in levels:
        if not isinstance(item, dict):
            return None
        try:
            z = reader.length(item.get("elevation"), "its elevation")
        except (InteriorStop, TypeError, ValueError):
            return None
        if top is None or z > top:
            top, name = z, item.get("name") if isinstance(item.get("name"), str) else item.get("id")
    lows = []
    if "flat" in ground:
        lows.append(float(ground["flat"]) * 12.0)
    elif "spots" in ground:
        try:
            lows += [float(p[2]) * 12.0 for p in ground["spots"]]
        except (TypeError, ValueError, IndexError):
            return None
    stated = _stated_ground(description, reader)
    if stated is None:
        return None
    lows += stated
    if not lows or top is None:
        return None
    low = min(lows)
    return {"height_in": top - low, "level": name, "ground_in": low}


def words(fig: dict | None) -> str | None:
    """The card's hint, only where the figure is under 75 ft; None otherwise. It says what the model shows and what
    would still make the building a high-rise, never that it likely isn't one (review round 1 of the marks PR): the
    figure is rounded down, so a figure under 75 ft never reads 75.0."""
    if not fig or not fig["height_in"] < LIMIT_IN:
        return None
    ft = math.floor(fig["height_in"] / 12.0 * 10) / 10
    margin = math.floor((LIMIT_IN - fig["height_in"]) / 12.0 * 10) / 10
    return (f"From the model: its highest level ({fig['level']}) is {ft:.1f} ft above the lowest finished ground it "
            f"states. The building is still a high-rise if fire department vehicles reach it more than {margin:.1f} ft "
            "below that ground, or if an occupied floor or occupiable roof is higher than that level or in a linked "
            "model. Gordium's reading only: decided by your answer.")
