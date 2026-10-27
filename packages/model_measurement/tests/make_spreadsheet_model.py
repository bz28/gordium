"""Write spreadsheet_design_model.3dm: the 106 Ithaca Rd design exactly as the architects' spreadsheet describes it.

    python packages/model_measurement/tests/make_spreadsheet_model.py

A 73 x 90 ft lot (Inputs!B3, B4) with the street along its 73 ft side, and a 53 x 35 x 35 ft house (Inputs!B6,
B7, B12) 30 ft from the street (B9) and 10 ft from the left side (B8). The spreadsheet's lot area (6,674 sf,
B5) is the real lot's, which has a jog; a 73 x 90 rectangle is 6,570 sf. Everything else matches the spreadsheet
exactly, so this model checks the whole chain (Rhino file -> measurements -> rules) against their numbers.
The committed file is checked against a fresh one by tests/test_models.py.
"""

from pathlib import Path

import rhino3dm as r

HERE = Path(__file__).resolve()
OUT = HERE.parents[3] / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/spreadsheet_design_model.3dm"
LOT = [(0, 0), (73, 0), (73, 90), (0, 90)]
HOUSE = ((10, 30, 0), (63, 65, 35))


def build() -> r.File3dm:
    model = r.File3dm()
    model.Settings.ModelUnitSystem = r.UnitSystem.Feet
    for name in ("Site", "Building"):
        layer = r.Layer()
        layer.Name = name
        model.Layers.Add(layer)
    site = r.ObjectAttributes()
    site.LayerIndex = 0
    lot = r.Polyline([r.Point3d(x, y, 0) for x, y in LOT + LOT[:1]])
    model.Objects.AddPolyline(lot, site)
    house = r.ObjectAttributes()
    house.LayerIndex = 1
    (x0, y0, z0), (x1, y1, z1) = HOUSE
    model.Objects.AddBrep(r.Brep.CreateFromBoundingBox(r.BoundingBox(x0, y0, z0, x1, y1, z1)), house)
    return model


if __name__ == "__main__":
    build().Write(str(OUT), 8)
    print(f"wrote {OUT}")
