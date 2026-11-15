"""Small made-up IFC4 models for the tests, built with ifcopenshell's own API (never read by the code under test
to make them). Every number is given in the model's own length unit, so the tests also prove the unit conversion.

    house(unit="foot" | "millimetre" | "metre") -> a Builder; add parts, then .write(path)
"""

import numpy as np


class Builder:
    def __init__(self, unit="foot"):
        import ifcopenshell
        import ifcopenshell.api
        self.api = ifcopenshell.api
        self.guid = ifcopenshell.guid.new
        self.f = ifcopenshell.api.run("project.create_file", version="IFC4")
        run = self.run
        project = run("root.create_entity", ifc_class="IfcProject", name="Test")
        if unit == "foot":
            length = run("unit.add_conversion_based_unit", name="foot")
            area = run("unit.add_conversion_based_unit", name="square foot")
        elif unit == "millimetre":
            length = run("unit.add_si_unit", unit_type="LENGTHUNIT", prefix="MILLI")
            area = run("unit.add_si_unit", unit_type="AREAUNIT")
        else:
            length = run("unit.add_si_unit", unit_type="LENGTHUNIT")
            area = run("unit.add_si_unit", unit_type="AREAUNIT")
        angle = self.f.create_entity("IfcSIUnit", UnitType="PLANEANGLEUNIT", Name="RADIAN")
        run("unit.assign_unit", units=[length, area, angle])
        self.metres = {"foot": 0.3048, "millimetre": 0.001}.get(unit, 1.0)   # ifcopenshell's shape API takes metres
        model = run("context.add_context", context_type="Model")
        self.body = run("context.add_context", context_type="Model", context_identifier="Body",
                        target_view="MODEL_VIEW", parent=model)
        site = run("root.create_entity", ifc_class="IfcSite", name="Site")
        building = run("root.create_entity", ifc_class="IfcBuilding", name="House")
        self.storey = run("root.create_entity", ifc_class="IfcBuildingStorey", name="Level 1")
        run("aggregate.assign_object", products=[site], relating_object=project)
        run("aggregate.assign_object", products=[building], relating_object=site)
        run("aggregate.assign_object", products=[self.storey], relating_object=building)
        for p in (site, building, self.storey):
            run("geometry.edit_object_placement", product=p)

    def run(self, usecase, /, **kw):
        return self.api.run(usecase, self.f, **kw)

    def place(self, product, origin, x_axis=(1, 0, 0)):
        x = np.array(x_axis, dtype=float)
        z = np.array((0, 0, 1.0))
        m = np.eye(4)
        m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x, np.cross(z, x), z, origin
        self.run("geometry.edit_object_placement", product=product, matrix=m, is_si=False)

    def box(self, product, length, depth, height):
        m = self.metres
        rep = self.run("geometry.add_wall_representation", context=self.body, length=length * m, height=height * m,
                       thickness=depth * m)
        self.run("geometry.assign_representation", product=product, representation=rep)

    def space(self, long_name, origin, size, name="1", quantities=None, flags=None):
        s = self.run("root.create_entity", ifc_class="IfcSpace", name=name)
        s.LongName = long_name
        self.run("aggregate.assign_object", products=[s], relating_object=self.storey)
        self.place(s, origin)
        self.box(s, *size)
        if quantities:
            q = self.run("pset.add_qto", product=s, name="Qto_SpaceBaseQuantities")
            self.run("pset.edit_qto", qto=q, properties=quantities)
        if flags:
            self.pset(s, "Gordium_Egress", flags)
        return s

    def pset(self, product, name, values):
        p = self.run("pset.add_pset", product=product, name=name)
        self.run("pset.edit_pset", pset=p, properties=values)

    def window(self, name, wall_origin, wall_axis, along, sill, width, height, lining=0.0, panels=("SIDEHUNGLEFTHAND",),
               space=None, psets=None, mullion=False, upright=True):
        """A window in its own wall (the wall runs from wall_origin along wall_axis, 1 unit thick), at `along`
        from the wall's start and `sill` above it; its opening fills exactly width x height."""
        wall = self.run("root.create_entity", ifc_class="IfcWall", name=f"wall for {name}")
        self.run("spatial.assign_container", products=[wall], relating_structure=self.storey)
        self.place(wall, wall_origin, wall_axis)
        self.box(wall, along + width + 1, 1, sill + height + 1)
        opening = self.run("root.create_entity", ifc_class="IfcOpeningElement", name=f"opening for {name}")
        self.box(opening, width, 1, height)
        axis = np.array(wall_axis, dtype=float)
        at = np.array(wall_origin, dtype=float) + axis * along + np.array((0, 0, sill))
        self.place(opening, at, wall_axis)
        self.run("feature.add_feature", feature=opening, element=wall)
        w = self.run("root.create_entity", ifc_class="IfcWindow", name=name)
        w.OverallWidth, w.OverallHeight = width, height
        self.run("spatial.assign_container", products=[w], relating_structure=self.storey)
        if upright:
            self.place(w, at, wall_axis)
        else:                                   # tipped back 30 degrees, as a roof window
            m = np.eye(4)
            c, s = np.cos(np.radians(30)), np.sin(np.radians(30))
            m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = axis, np.cross((0, 0, 1), axis) * c + np.array((0, 0, s)), \
                np.array((0, 0, c)) - np.cross((0, 0, 1), axis) * s, at
            self.run("geometry.edit_object_placement", product=w, matrix=m, is_si=False)
        self.box(w, width, 0.25, height)
        self.run("feature.add_filling", opening=opening, element=w)
        t = self.run("root.create_entity", ifc_class="IfcWindowType", name=f"type of {name}")
        t.PartitioningType = "SINGLE_PANEL" if len(panels) == 1 else "DOUBLE_PANEL_VERTICAL"
        t.ParameterTakesPrecedence = True        # its lining and panel records define it exactly
        sets = [self.f.create_entity("IfcWindowLiningProperties", GlobalId=self.guid(), LiningDepth=0.25,
                                     LiningThickness=lining, MullionThickness=lining if mullion else None,
                                     FirstMullionOffset=0.5 if mullion else None)]
        sets += [self.f.create_entity("IfcWindowPanelProperties", GlobalId=self.guid(), OperationType=op,
                                      PanelPosition="MIDDLE") for op in panels]
        t.HasPropertySets = sets
        self.run("type.assign_type", related_objects=[w], relating_type=t)
        if space is not None:
            self.boundary(space, w)
        for set_name, values in (psets or {}).items():
            self.pset(w, set_name, values)
        return w

    def boundary(self, space, element):
        self.f.create_entity("IfcRelSpaceBoundary", GlobalId=self.guid(), RelatingSpace=space,
                             RelatedBuildingElement=element, PhysicalOrVirtualBoundary="PHYSICAL",
                             InternalOrExternalBoundary="EXTERNAL")

    def door(self, name, origin, operation="SINGLE_SWING_LEFT", width=3, height=7, spaces=(), psets=None):
        d = self.run("root.create_entity", ifc_class="IfcDoor", name=name)
        d.OverallWidth, d.OverallHeight, d.OperationType = width, height, operation
        self.run("spatial.assign_container", products=[d], relating_structure=self.storey)
        self.place(d, origin)
        self.box(d, width, 0.2, height)
        for s in spaces:
            self.boundary(s, d)
        for set_name, values in (psets or {}).items():
            self.pset(d, set_name, values)
        return d

    def flight(self, name, risers=None, treads=None, riser=None, tread=None, pset=None):
        stair = self.run("root.create_entity", ifc_class="IfcStair", name=f"stair of {name}")
        self.run("spatial.assign_container", products=[stair], relating_structure=self.storey)
        fl = self.run("root.create_entity", ifc_class="IfcStairFlight", name=name)
        fl.NumberOfRisers, fl.NumberOfTreads, fl.RiserHeight, fl.TreadLength = risers, treads, riser, tread
        self.run("aggregate.assign_object", products=[fl], relating_object=stair)
        if pset:
            self.pset(fl, "Pset_StairFlightCommon", pset)
        return fl

    def write(self, path):
        self.f.write(str(path))
        return path


def house(unit="foot") -> Builder:
    return Builder(unit)
