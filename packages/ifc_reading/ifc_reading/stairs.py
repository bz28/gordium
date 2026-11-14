"""Stairs: what an IFC model says about each stair flight (risers, treads, riser height, tread length), kept with
where each number came from. Not turned into the description's `stairs`: those need every nosing's place, which
IFC exports don't give reliably (Revit's least of all), so stairs come from the Revit add-in. The description
leaves `stairs` out, and every stair rule needs review.
"""

from ifc_reading.model import is_number, tidy

# IFC4 IfcStairFlight attributes, then Pset_StairFlightCommon (IFC4 names; IFC2x3's NumberOfRiser too)
COUNTS = {"risers": ("NumberOfRisers", ("NumberOfRiser", "NumberOfRisers")),
          "treads": ("NumberOfTreads", ("NumberOfTreads",))}
LENGTHS = {"riser_height": ("RiserHeight", ("RiserHeight",)), "tread_length": ("TreadLength", ("TreadLength",))}


def read_flight(model, flight) -> dict:
    out = {"id": flight.GlobalId, "name": flight.Name or flight.GlobalId, "entity": flight.is_a(),
           "step_id": flight.id()}
    sources, unread = {}, {}
    for key, (attr, props) in {**COUNTS, **LENGTHS}.items():
        value, where = getattr(flight, attr, None), f"{flight.is_a()}.{attr}"
        if is_number(value):                     # an attribute: in the file's own unit
            value = float(value) * model.metres if key in LENGTHS else value
        else:
            value, where = None, None
            for p in props:
                if key in LENGTHS:               # a property may state its own unit
                    # review round 8: the flight's own wins over its type's, which says so
                    v, w, bad = model.inherited(flight, lambda n: n == "Pset_StairFlightCommon", p, "LENGTHUNIT")
                    if bad:
                        unread[key] = bad
                else:
                    v, w = model.prop(flight, ["Pset_StairFlightCommon"], p)
                    if v is not None and not is_number(v):     # review round 9: never dropped without a reason
                        unread[key] = f"{w} is {v!r}, not a number"
                if is_number(v):
                    value, where = v, w
                    break
        if value is None:
            continue
        out[key] = int(value) if key in COUNTS and float(value).is_integer() else \
            tidy(value) if key in LENGTHS else value
        sources[key] = where
    out["source"] = sources
    if unread:
        out["not_given"] = {k: v for k, v in unread.items() if k not in out}
    parent = [r.RelatingObject for r in getattr(flight, "Decomposes", []) or []]
    if parent:
        out["stair"] = parent[0].GlobalId
    return out


def read_stairs(model) -> dict:
    stairs = [{"id": s.GlobalId, "name": s.Name or s.GlobalId, "entity": s.is_a(), "step_id": s.id(),
               "shape": getattr(s, "PredefinedType", None) or getattr(s, "ShapeType", None)}
              for s in model.by_type("IfcStair")]
    return {"stairs_seen": stairs, "stair_flights": [read_flight(model, f) for f in model.by_type("IfcStairFlight")]}
