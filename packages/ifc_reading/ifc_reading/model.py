"""Reading an IFC file: its length unit, an element's properties and quantities, where it is, and its shape.

Every length leaves this module in metres, converted from the file's own length unit (IfcUnitAssignment); areas
in square metres from its own area unit. ifcopenshell is imported here and only here, so the rest of the package
(and its word table) loads without it.
"""

import math

import numpy as np

EPS = 1e-6          # m: two coordinates closer than this are the same (a thousandth of a millimetre)
FLAT = 1e-3         # m: a face whose points differ in height by no more than this is level (drawing noise)


class Model:
    """One open IFC file."""

    def __init__(self, path):
        import ifcopenshell
        import ifcopenshell.util.unit
        self.file = ifcopenshell.open(str(path))
        self.schema = self.file.schema
        assignments = self.file.by_type("IfcUnitAssignment")
        units = [u for a in assignments for u in a.Units if getattr(u, "UnitType", None) == "LENGTHUNIT"]
        if len(units) != 1:
            raise ValueError(f"the file states {len(units)} length units: which one its lengths are in is unclear")
        self.length_unit = _unit_name(units[0])
        self.metres = float(ifcopenshell.util.unit.calculate_unit_scale(self.file, "LENGTHUNIT"))
        areas = [u for a in assignments for u in a.Units if getattr(u, "UnitType", None) == "AREAUNIT"]
        self.square_metres = float(ifcopenshell.util.unit.calculate_unit_scale(self.file, "AREAUNIT")) \
            if len(areas) == 1 else None
        self._settings = None

    def by_type(self, name):
        try:
            return list(self.file.by_type(name))
        except RuntimeError:                       # the entity isn't in this schema
            return []

    # -- properties --------------------------------------------------------------------------------------------
    def _holders(self, element):
        """The element's own property and quantity sets, then its type's (the element's own value wins)."""
        own = [r.RelatingPropertyDefinition for r in getattr(element, "IsDefinedBy", []) or []
               if r.is_a("IfcRelDefinesByProperties")]
        own = [d for x in own for d in (x if isinstance(x, tuple) else (x,))]     # IFC4 allows a set of sets
        t = self.type_of(element)
        return own + list(getattr(t, "HasPropertySets", None) or [] if t is not None else [])

    def find(self, element, wanted, name):
        """The first property or quantity called `name` in a set `wanted(set name)` accepts: (value, "Set.Name",
        its own unit or None); (None, None, None) if there is none. The value is the bare number, text or
        true/false the model states."""
        for holder in self._holders(element):
            if not (holder.is_a("IfcPropertySet") or holder.is_a("IfcElementQuantity")) or not wanted(holder.Name):
                continue
            items = holder.HasProperties if holder.is_a("IfcPropertySet") else holder.Quantities
            for item in items or []:
                if item.Name != name:
                    continue
                if item.is_a("IfcPropertySingleValue"):
                    value = item.NominalValue.wrappedValue if item.NominalValue is not None else None
                elif item.is_a("IfcPhysicalSimpleQuantity"):
                    value = item[3]                       # LengthValue, AreaValue…
                else:
                    continue
                if value is not None:
                    return value, f"{holder.Name}.{name}", getattr(item, "Unit", None)
        return None, None, None

    def prop(self, element, sets, name):
        """The first set in `sets` (by name, in order) holding `name`, as (value, "Set.Name"); (None, None) if none."""
        for s in sets:
            value, where, _ = self.find(element, lambda n, s=s: n == s, name)
            if value is not None:
                return value, where
        return None, None

    def measure(self, element, wanted, name, kind):
        """A length (kind "LENGTHUNIT", in metres) or an area ("AREAUNIT", in square metres) the model states:
        (value, where, None), or (None, where, why not). A value carrying its own unit is converted by that unit;
        otherwise by the file's."""
        import ifcopenshell.util.unit
        value, where, unit = self.find(element, wanted, name)
        if value is None:
            return None, None, None
        if not is_number(value):
            return None, where, f"{where} is {value!r}, not a number"
        if unit is not None:
            if getattr(unit, "UnitType", None) != kind:
                return None, where, f"{where} is stated in a unit that isn't a {kind.lower()[:-4]} unit"
            return float(value) * float(ifcopenshell.util.unit.get_unit_scale(unit)), where, None
        scale = self.metres if kind == "LENGTHUNIT" else self.square_metres
        if scale is None:
            return None, where, f"the file states no single area unit, so {where} can't be read"
        return float(value) * scale, where, None

    def quantity(self, element, name, kind="LENGTHUNIT"):
        """A base quantity (a Qto_* set, or IFC2x3's BaseQuantities): (metres or square metres, where, why not)."""
        return self.measure(element, lambda n: bool(n) and (n.startswith("Qto_") or n == "BaseQuantities"), name,
                            kind)

    def type_of(self, element):
        import ifcopenshell.util.element
        return ifcopenshell.util.element.get_type(element)

    def predefined(self, element, entity):
        """The type's predefined property sets of an entity kind (IfcWindowLiningProperties…), then the element's."""
        found = []
        t = self.type_of(element)
        for holder in ([t] if t is not None else []):
            found += [p for p in (getattr(holder, "HasPropertySets", None) or []) if p.is_a(entity)]
        for rel in getattr(element, "IsDefinedBy", []) or []:
            if rel.is_a("IfcRelDefinesByProperties") and rel.RelatingPropertyDefinition.is_a(entity):
                found.append(rel.RelatingPropertyDefinition)
        return found

    # -- where things are --------------------------------------------------------------------------------------
    def placement(self, element):
        """The element's placement as a 4x4 matrix, translation in metres (axes unit length)."""
        import ifcopenshell.util.placement
        m = np.array(ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement), dtype=float)
        m[:3, 3] *= self.metres
        return m

    def storey_of(self, element):
        import ifcopenshell.util.element
        c = ifcopenshell.util.element.get_container(element)
        if c is None:
            for rel in getattr(element, "Decomposes", []) or []:
                c = rel.RelatingObject
        return c

    # -- shape -------------------------------------------------------------------------------------------------
    def triangles(self, element):
        """The element's body as triangles, world coordinates in metres: an (n, 3, 3) array; None if it has none."""
        import ifcopenshell.geom
        if self._settings is None:
            self._settings = ifcopenshell.geom.settings()
            self._settings.set("use-world-coords", True)
        try:
            shape = ifcopenshell.geom.create_shape(self._settings, element)
        except RuntimeError:
            return None
        verts = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3)   # ifcopenshell gives metres
        faces = np.array(shape.geometry.faces, dtype=int).reshape(-1, 3)
        if not len(faces):
            return None
        return verts[faces]


def _unit_name(unit) -> str:
    if unit.is_a("IfcSIUnit"):
        return ((unit.Prefix or "") + unit.Name).lower()
    return str(getattr(unit, "Name", unit)).lower()


def normals(tris):
    """Each triangle's unit normal (zero for a triangle with no area)."""
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    size = np.linalg.norm(n, axis=1)
    out = np.zeros_like(n)
    ok = size > 1e-12
    out[ok] = n[ok] / size[ok, None]
    return out, size


def tidy(value: float) -> float:
    """Float noise off (to a nanometre, far finer than any model): 0.8700000001 is 0.87."""
    return round(float(value), 9) + 0.0


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
