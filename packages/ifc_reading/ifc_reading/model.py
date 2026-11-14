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
    def _own(self, element):
        """The element's own property definitions (IFC4 lets one relation hold a set of them: a tuple)."""
        own = [r.RelatingPropertyDefinition for r in getattr(element, "IsDefinedBy", []) or []
               if r.is_a("IfcRelDefinesByProperties")]
        return [d for x in own for d in (x if isinstance(x, tuple) else (x,))]

    def _holders(self, element):
        """The element's own property and quantity sets, then its type's (the element's own value wins)."""
        t = self.type_of(element)
        return self._own(element) + list(getattr(t, "HasPropertySets", None) or [] if t is not None else [])

    def find_all(self, element, wanted, name, holders=None):
        """Every property or quantity called `name` in a set `wanted(set name)` accepts, the element's own first:
        [(value, "Set.Name", its own unit or None)]. The value is the bare number, text or true/false the model
        states; one stored another way (an enumerated or list value…) comes back as UNREADABLE, never skipped."""
        found = []
        for holder in self._holders(element) if holders is None else holders:
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
                    value = Unreadable(item.is_a())
                if value is not None:
                    found.append((value, f"{holder.Name}.{name}", getattr(item, "Unit", None)))
        return found

    def levels(self, element):
        """The element's own property sets, then its type's: IFC's inheritance (the element's own value wins)."""
        t = self.type_of(element)
        return self._own(element), list(getattr(t, "HasPropertySets", None) or [] if t is not None else [])

    @staticmethod
    def from_type(t):
        return f" (from its type {t.Name or t.is_a()} #{t.id()})" if t is not None else ""

    def find(self, element, wanted, name):
        """The first of find_all: (value, "Set.Name", unit); (None, None, None) if there is none."""
        got = self.find_all(element, wanted, name)
        return got[0] if got else (None, None, None)

    def prop(self, element, sets, name):
        """The first set in `sets` (by name, in order) holding `name`, as (value, "Set.Name"); (None, None) if none.
        The element's own statements override its type's (IFC's inheritance); stated more than once at the same
        level (two sets of the same name, say), they must agree, else the value is Unreadable (never the first
        one found, which could be the wrong one)."""
        t = self.type_of(element)
        for s in sets:
            for level, holders in enumerate(self.levels(element)):
                got = self.find_all(element, lambda n, s=s: n == s, name, holders)
                if not got:
                    continue
                # review round 7: a value inherited from the type (every element of it) says so
                where = got[0][1] + (self.from_type(t) if level else "")
                values = [v for v, _, _ in got]
                if len(got) > 1 and any(isinstance(v, Unreadable) or type(v) is not type(values[0]) or
                                        v != values[0] for v in values):
                    return Unreadable(f"{len(got)} statements that differ ({', '.join(map(repr, values))})",
                                      stated=True), where
                return values[0], where
        return None, None

    def _convert(self, value, where, unit, kind):
        import ifcopenshell.util.unit
        if not is_number(value):
            return None, f"{where} is {value!r}, not a number"
        if unit is not None:
            if getattr(unit, "UnitType", None) != kind:
                return None, f"{where} is stated in a unit that isn't a {kind.lower()[:-4]} unit"
            return float(value) * float(ifcopenshell.util.unit.get_unit_scale(unit)), None
        scale = self.metres if kind == "LENGTHUNIT" else self.square_metres
        if scale is None:
            return None, f"the file states no single area unit, so {where} can't be read"
        return float(value) * scale, None

    def measure(self, element, wanted, name, kind, holders=None):
        """A length (kind "LENGTHUNIT", in metres) or an area ("AREAUNIT", in square metres) the model states:
        (value, where, None), or (None, where, why not). A value carrying its own unit is converted by that unit;
        otherwise by the file's. Stated more than once (two quantity sets), every statement must agree, else
        which is right is unclear and there is no value (never the first found, which could be the larger)."""
        got = self.find_all(element, wanted, name, holders)
        if not got:
            return None, None, None
        values = []
        for value, where, unit in got:
            v, bad = self._convert(value, where, unit, kind)
            if bad:
                return None, where, bad
            values.append((v, where))
        low, high = min(v for v, _ in values), max(v for v, _ in values)
        if high - low > 1e-9 * max(1.0, abs(high)):
            said = ", ".join(f"{w} {tidy(v)}" for v, w in values)
            return None, values[0][1], f"the model states {name} more than once, differently ({said}): which is right is unclear"
        return values[0][0], values[0][1], None

    def inherited(self, element, wanted, name, kind):
        """measure() one level at a time: the element's own statement wins, else its type's, which then says so
        in its source ("from its type ..."), since it holds for every element of that type."""
        t = self.type_of(element)
        for level, holders in enumerate(self.levels(element)):
            value, where, bad = self.measure(element, wanted, name, kind, holders)
            if where is not None:
                return value, where + (self.from_type(t) if level else ""), bad
        return None, None, None

    def quantity(self, element, name, kind="LENGTHUNIT"):
        """A base quantity (a Qto_* set, or IFC2x3's BaseQuantities): (metres or square metres, where, why not).
        IFC4's template for these sets is type-driven with override: the element's own value wins, else its
        type's, which then says so (review round 7: a type's NetFloorArea read as if the room stated it)."""
        return self.inherited(element, lambda n: bool(n) and (n.startswith("Qto_") or n == "BaseQuantities"), name,
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
        found += [d for d in self._own(element) if d.is_a(entity)]
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


class Unreadable:
    """A property the model states under the wanted name but in a form not read (an enumerated or list value):
    never taken as absent, so a flag stored that way leaves its part unknown."""

    def __init__(self, kind: str, stated=False):
        self.kind, self.stated = kind, stated

    def __repr__(self):
        return self.kind if self.stated else f"an {self.kind} (not read)"


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
