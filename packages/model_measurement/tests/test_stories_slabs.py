"""Stories of a building drawn as parts (a Revit model: each wall, floor and roof its own element): a slab resting in
the building is a floor level or the roof (§325-3B STORY), never a part that may be another story
(measure._slabs_within; docs/revit/revit_reading_design.md, section 7, "Stories of a building drawn as parts")."""

import sys
from pathlib import Path

from model_measurement.places.ithaca_city.measure import measure

sys.path.insert(0, str(Path(__file__).parent))
from test_measure import FACTS, RECT, box  # noqa: E402

NO_COUNT = {**FACTS, "stories": None}


def walls(x0, y0, x1, y1, z0=0, z1=35, t=0.5):
    """A ring of four walls, their outer faces on the rectangle (one part each, as Revit sends them)."""
    return [box(x0, y0, x1, y0 + t, z0, z1, id="wall_s"), box(x1 - t, y0, x1, y1, z0, z1, id="wall_e"),
            box(x0, y1 - t, x1, y1, z0, z1, id="wall_n"), box(x0, y0, x0 + t, y1, z0, z1, id="wall_w")]


def stories(buildings, facts=NO_COUNT):
    return measure({"units": "ft", "lot": RECT, "buildings": buildings, "problems": []}, facts)["stories"]


def test_a_roof_slab_inside_the_walls_is_the_roof_not_a_raised_part():
    # 106 Ithaca Rd as Revit read it (2026-11-21): four 35 ft walls and the roof a 1 ft floor at 34 to 35 ft
    got = stories(walls(10, 25, 35, 65) + [box(10, 25, 35, 65, 34, 35, id="roof")])
    assert got["value"] is None
    assert "starts above the ground" not in got["reason"] and "partly inside" not in got["reason"]
    assert "could hold up to 5 stories" in got["reason"]                    # 35 ft walls: 1 to 5, a question


def test_with_the_slabs_taken_as_floor_levels_a_count_stated_stands_within_what_the_walls_allow():
    parts = walls(10, 25, 35, 65, z1=30) + [box(10, 25, 35, 65, 9, 10, id="floor 2"),
                                           box(10, 25, 35, 65, 19, 20, id="floor 3"),
                                           box(10, 25, 35, 65, 29, 30, id="roof")]
    assert stories(parts, {**FACTS, "stories": 3})["value"] == 3          # within 1 to 4 (30 ft)
    assert stories(parts, {**FACTS, "stories": 5})["value"] is None       # more than 30 ft can hold: refused


def test_a_part_that_may_be_a_story_stays_one():
    # a part a story tall over the roof, a thin part past the walls' outline, and one floating over them: each may
    # still be another story (never taken as a slab)
    for extra in (box(12, 27, 20, 35, 35, 45, id="room over the roof"),
                  box(30, 25, 45, 65, 20, 21, id="balcony past the outline"),
                  box(10, 25, 35, 65, 36, 37, id="slab floating over the walls")):
        got = stories(walls(10, 25, 35, 65) + [extra], {**FACTS, "stories": 3})
        assert got["value"] is None, extra["id"]
