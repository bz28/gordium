"""Reading an IFC building model into Gordium's interior description (`gordium.interior/1`,
docs/interior/interior_description_format.md), so egress can be measured on real models before the Revit add-in.

    read(path) -> the description, as a mapping (dump it as YAML; model_measurement.interior.measure reads it)

Rooms come from IfcSpace, openings from IfcWindow (and exterior IfcDoor), the exit door from IfcDoor. Stairs and
guards are left out (not read: their rules need review); what the model says about stair flights is kept under
`source`. Plain code, no AI: every value is the model's own, converted from its stated length unit to metres, or
left out with its reason under the part's `not_given`. Nothing is guessed: a room is a sleeping room, or not, only
when its name or a flag says so; an opening is an escape opening only when the model marks it.
"""

import hashlib
from pathlib import Path

from ifc_reading.model import Model
from ifc_reading.openings import read_door, read_door_opening, read_window
from ifc_reading.rooms import read_room
from ifc_reading.stairs import read_stairs

FORMAT = "gordium.interior/1"
READER = "ifc_reading/1"


def read(path) -> dict:
    path = Path(path)
    model = Model(path)
    rooms = [read_room(model, s) for s in model.by_type("IfcSpace")]
    floors = {r["id"]: r.get("floor_elevation") for r in rooms}
    windows = [read_window(model, w, floors) for w in model.by_type("IfcWindow")]
    doors = model.by_type("IfcDoor")
    door_openings = [o for o in (read_door_opening(model, d, floors) for d in doors) if o is not None]
    source = {
        "reader": READER,
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "schema": model.schema,
        "length_unit": model.length_unit,
        "metres_per_unit": model.metres,
        "not_read": {
            "stairs": "stairs come from the Revit add-in (an IFC export doesn't give each nosing's place); what the "
                      "model says about each flight is under stair_flights",
            "guards": "guards (IfcRailing) aren't read from IFC yet",
        },
        **read_stairs(model),
    }
    return {"format": FORMAT, "units": "m", "rooms": rooms, "openings": windows + door_openings,
            "doors": [read_door(model, d) for d in doors], "source": source}


__all__ = ["read", "FORMAT", "READER"]
