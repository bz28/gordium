"""A small stand-in for RhinoCommon, Eto and scriptcontext, enough to import apps/rhino_plugin/gordium_rhino.py
unchanged and run its context-map and start-box code paths headless.

What is MODELLED here (not proven; only Rhino can prove it):
- Rhino 8 layers: setting a layer's IsVisible gives every sublayer the layer's own lock (the behaviour the Rhino
  job found at c783ee6 and test_context_box._Layer models); an object is locked / hidden when its layer or any
  parent layer is locked / hidden; Delete, Transform and ModifyAttributes fail on a locked object (a hidden one is
  deleted: the 955d97f Rhino run deleted the held sample lot on the hidden holding layer and then the layer);
  Select fails on a locked or hidden one.
- ObjectAttributes: the FINGERPRINT_ATTRIBUTES with RhinoCommon-like defaults; AddCurve copies the attributes and
  gives a new id; Transform keeps the object id.
- Geometry: polylines, boxes, text and dots with plain Python maths (no real text layout).
- A saved file: written with rhino3dm (ids, layers, user strings, document strings kept; model text written as a
  TextDot carrying its words), reopened into a new fake document.
Everything the UI draws (Eto widgets, display conduits, views) is an inert stand-in (Auto)."""
import json
import math
import os
import sys
import types
import uuid

import rhino3dm as r3

EMPTY_GUID = "00000000-0000-0000-0000-000000000000"
WRITTEN = []          # RhinoApp.WriteLine


# ---- inert stand-ins --------------------------------------------------------------------------------------------

class Auto:
    """Anything: every attribute, call, event += / -=, index; iterates as empty. For UI and viewport calls only."""

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        v = Auto()
        object.__setattr__(self, name, v)
        return v

    def __call__(self, *a, **k):
        return Auto()

    def __iadd__(self, other):
        return self

    def __isub__(self, other):
        return self

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __bool__(self):
        return True

    def __getitem__(self, k):
        return Auto()

    def __gt__(self, o):
        return False

    __lt__ = __ge__ = __le__ = __gt__

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    def __index__(self):
        return 0

    def __add__(self, o):
        return self

    __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = __truediv__ = __or__ = __ror__ = __and__ = __add__

    def __hash__(self):
        return id(self)

    def __eq__(self, o):
        return self is o

    def __str__(self):
        return "Auto"


class AutoModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        v = Auto()
        setattr(self, name, v)
        return v


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, h):
        self.handlers.append(h)
        return self

    def __isub__(self, h):
        if h in self.handlers:
            self.handlers.remove(h)
        return self

    def fire(self, s=None, e=None):
        for h in list(self.handlers):
            h(s, e)


# ---- System -----------------------------------------------------------------------------------------------------

class Color:
    def __init__(self, a, r, g, b):
        self.A, self.R, self.G, self.B = a, r, g, b

    @staticmethod
    def FromArgb(*v):
        if len(v) == 3:
            return Color(255, *v)
        if len(v) == 4:
            return Color(*v)
        x = v[0] & 0xFFFFFFFF
        return Color(x >> 24, (x >> 16) & 255, (x >> 8) & 255, x & 255)

    def ToArgb(self):
        x = (self.A << 24) | (self.R << 16) | (self.G << 8) | self.B
        return x - (1 << 32) if x & 0x80000000 else x

    def __eq__(self, o):
        return isinstance(o, Color) and o.ToArgb() == self.ToArgb()

    def __hash__(self):
        return self.ToArgb()

    def __str__(self):
        return "Color [A=%d, R=%d, G=%d, B=%d]" % (self.A, self.R, self.G, self.B)


Color.Black = Color(255, 0, 0, 0)


class _GuidType(type):
    Empty = EMPTY_GUID


class Guid(metaclass=_GuidType):
    def __new__(cls, text):
        return str(uuid.UUID(str(text)))


# ---- geometry ---------------------------------------------------------------------------------------------------

class Point3d:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X, self.Y, self.Z = float(x), float(y), float(z)

    def __add__(self, v):
        return Point3d(self.X + v.X, self.Y + v.Y, self.Z + v.Z)

    def __sub__(self, v):
        return Vector3d(self.X - v.X, self.Y - v.Y, self.Z - v.Z)

    def DistanceTo(self, p):
        return math.dist((self.X, self.Y, self.Z), (p.X, p.Y, p.Z))

    def __repr__(self):
        return "Point3d(%g, %g, %g)" % (self.X, self.Y, self.Z)


class Vector3d(Point3d):
    pass


Vector3d.ZAxis = Vector3d(0, 0, 1)


class Point2d:
    def __init__(self, x=0.0, y=0.0):
        self.X, self.Y = x, y


class Transform:
    def __init__(self, fn):
        self.fn = fn

    @staticmethod
    def Translation(dx, dy=None, dz=None):
        if dy is None:
            dx, dy, dz = dx.X, dx.Y, dx.Z
        return Transform(lambda p: Point3d(p.X + dx, p.Y + dy, p.Z + dz))

    @staticmethod
    def Scale(centre, *k):
        c = centre.Origin if isinstance(centre, Plane) else centre
        kx, ky, kz = (k * 3) if len(k) == 1 else k
        return Transform(lambda p: Point3d(c.X + (p.X - c.X) * kx, c.Y + (p.Y - c.Y) * ky, c.Z + (p.Z - c.Z) * kz))

    def apply(self, p):
        return self.fn(p)


class _BoxType(type):
    @property
    def Empty(cls):
        return BoundingBox()


class BoundingBox(metaclass=_BoxType):
    def __init__(self, *a):
        if len(a) == 6:
            self.Min, self.Max = Point3d(*a[:3]), Point3d(*a[3:])
        elif len(a) == 2:
            self.Min, self.Max = Point3d(a[0].X, a[0].Y, a[0].Z), Point3d(a[1].X, a[1].Y, a[1].Z)
        elif len(a) == 1:                       # points
            pts = list(a[0])
            self.Min = Point3d(min(p.X for p in pts), min(p.Y for p in pts), min(p.Z for p in pts))
            self.Max = Point3d(max(p.X for p in pts), max(p.Y for p in pts), max(p.Z for p in pts))
        else:
            self.Min, self.Max = Point3d(1, 1, 1), Point3d(-1, -1, -1)

    @property
    def IsValid(self):
        return self.Min.X <= self.Max.X and self.Min.Y <= self.Max.Y and self.Min.Z <= self.Max.Z

    @property
    def Center(self):
        return Point3d((self.Min.X + self.Max.X) / 2, (self.Min.Y + self.Max.Y) / 2, (self.Min.Z + self.Max.Z) / 2)

    @property
    def Diagonal(self):
        return self.Max - self.Min

    def Union(self, other):
        if isinstance(other, Point3d):
            other = BoundingBox(other, other)
        if not other.IsValid:
            return
        if not self.IsValid:
            self.Min, self.Max = Point3d(other.Min.X, other.Min.Y, other.Min.Z), Point3d(other.Max.X, other.Max.Y,
                                                                                         other.Max.Z)
            return
        self.Min = Point3d(min(self.Min.X, other.Min.X), min(self.Min.Y, other.Min.Y), min(self.Min.Z, other.Min.Z))
        self.Max = Point3d(max(self.Max.X, other.Max.X), max(self.Max.Y, other.Max.Y), max(self.Max.Z, other.Max.Z))

    def Inflate(self, k, *more):
        self.Min = Point3d(self.Min.X - k, self.Min.Y - k, self.Min.Z - k)
        self.Max = Point3d(self.Max.X + k, self.Max.Y + k, self.Max.Z + k)

    def GetCorners(self):
        a, b = self.Min, self.Max
        return [Point3d(a.X, a.Y, a.Z), Point3d(b.X, a.Y, a.Z), Point3d(b.X, b.Y, a.Z), Point3d(a.X, b.Y, a.Z),
                Point3d(a.X, a.Y, b.Z), Point3d(b.X, a.Y, b.Z), Point3d(b.X, b.Y, b.Z), Point3d(a.X, b.Y, b.Z)]

    @staticmethod
    def Intersection(a, b):
        return BoundingBox(max(a.Min.X, b.Min.X), max(a.Min.Y, b.Min.Y), max(a.Min.Z, b.Min.Z),
                           min(a.Max.X, b.Max.X), min(a.Max.Y, b.Max.Y), min(a.Max.Z, b.Max.Z))


class Plane:
    def __init__(self, origin=None, x=None, y=None):
        self.Origin = origin or Point3d()
        self.XAxis = x or Vector3d(1, 0, 0)
        self.YAxis = y or Vector3d(0, 1, 0)

    def PointAt(self, u, v, w=0.0):
        o, x, y = self.Origin, self.XAxis, self.YAxis
        return Point3d(o.X + u * x.X + v * y.X, o.Y + u * x.Y + v * y.Y, o.Z + u * x.Z + v * y.Z + w)


Plane.WorldXY = Plane()


class Line:
    def __init__(self, a, b):
        self.From, self.To = a, b

    def DistanceTo(self, p, finite=True):
        ax, ay, bx, by = self.From.X, self.From.Y, self.To.X, self.To.Y
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p.X - ax) * dx + (p.Y - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(p.X - ax - t * dx, p.Y - ay - t * dy)


class GeometryBase:
    def Duplicate(self):
        import copy
        return copy.deepcopy(self)


class Curve(GeometryBase):
    pass


class PolylineCurve(Curve):
    def __init__(self, points):
        self.points = [Point3d(p.X, p.Y, p.Z) for p in points]

    @property
    def IsClosed(self):
        return len(self.points) > 2 and self.points[0].DistanceTo(self.points[-1]) < 1e-9

    @property
    def PointAtStart(self):
        return self.points[0]

    @property
    def PointAtEnd(self):
        return self.points[-1]

    def TryGetPolyline(self):
        return True, Polyline(self.points)

    def DuplicateSegments(self):
        return [LineCurve(a, b) for a, b in zip(self.points, self.points[1:])]

    def DuplicateCurve(self):
        return self.Duplicate()

    def GetBoundingBox(self, accurate=True):
        return BoundingBox(self.points)

    def Transform(self, xf):
        self.points = [xf.apply(p) for p in self.points]
        return True

    def Contains(self, p, plane=None, tol=0.0):
        pts = [(q.X, q.Y) for q in self.points]
        inside = False
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            if (y1 > p.Y) != (y2 > p.Y) and p.X < (x2 - x1) * (p.Y - y1) / (y2 - y1) + x1:
                inside = not inside
        return PointContainment.Inside if inside else PointContainment.Outside


class LineCurve(PolylineCurve):
    def __init__(self, a, b):
        super().__init__([a, b])


class Polyline(list):
    def __init__(self, pts=()):
        super().__init__(Point3d(p.X, p.Y, p.Z) for p in pts)

    @property
    def BoundingBox(self):
        return BoundingBox(self)

    @property
    def Count(self):
        return len(self)

    def DeleteShortSegments(self, tol):
        keep = [p for i, p in enumerate(self) if i == 0 or p.DistanceTo(self[i - 1]) > tol]
        self[:] = keep


class PointContainment:
    Inside, Outside, Coincident = "Inside", "Outside", "Coincident"


class _Vertex:
    def __init__(self, p):
        self.Location = p


class _Faces(list):
    Count = 6                 # a box's faces (their points are not needed: the vertices outline a box in plan)


class Brep(GeometryBase):
    def __init__(self, corners):
        self.corners = [Point3d(p.X, p.Y, p.Z) for p in corners]
        self.IsSolid = True
        self.Edges = []
        self.Faces = _Faces()

    @property
    def Vertices(self):
        return [_Vertex(p) for p in self.corners]

    @staticmethod
    def CreateFromBox(arg):
        if isinstance(arg, BoundingBox):
            return Brep(arg.GetCorners())
        pts = list(arg)
        return Brep(pts) if len(pts) == 8 else None

    def GetBoundingBox(self, accurate=True):
        return BoundingBox(self.corners)

    @staticmethod
    def CreatePlanarBreps(curves, tol=0.0):
        return [Brep([p for c in curves for p in c.points])]

    def Transform(self, xf):
        self.corners = [xf.apply(p) for p in self.corners]
        return True


class Mesh(GeometryBase):
    pass


class Extrusion(GeometryBase):
    def __init__(self, ring, height):
        self.ring, self.height = ring, height

    @staticmethod
    def Create(curve, height, cap):
        return Extrusion([Point3d(p.X, p.Y, p.Z) for p in curve.points], height)

    def ToBrep(self, *a):
        return Brep(self.ring + [Point3d(p.X, p.Y, p.Z + self.height) for p in self.ring])

    def GetBoundingBox(self, accurate=True):
        return self.ToBrep().GetBoundingBox()


class SubD(GeometryBase):
    pass


class Point(GeometryBase):
    def __init__(self, p):
        self.Location = p

    def GetBoundingBox(self, accurate=True):
        return BoundingBox(self.Location, self.Location)

    def Transform(self, xf):
        self.Location = xf.apply(self.Location)


class TextDot(GeometryBase):
    def __init__(self, text, point):
        self.Text, self.Point = text, point

    def GetBoundingBox(self, accurate=True):
        return BoundingBox(self.Point, self.Point)

    def Transform(self, xf):
        self.Point = xf.apply(self.Point)


class TextJustification:
    BottomLeft = "BottomLeft"


class TextEntity(GeometryBase):
    """Model text: its words, plane, height and own scale. Its extent is a stand-in (0.6 x height a character, one
    line per text line), not Rhino's text layout."""

    def __init__(self):
        self.Text, self.Plane, self.DimensionScale, self.TextHeight, self.Justification = "", Plane(), 1.0, 1.0, None

    @property
    def PlainText(self):
        return self.Text

    @staticmethod
    def Create(text, plane, style, wrapped, width, rotation):
        t = TextEntity()
        t.Text, t.Plane = text, plane
        t.DimensionScale = getattr(style, "DimensionScale", 1.0)     # the template's (the feet template: 12)
        return t

    def GetBoundingBox(self, accurate=True):
        lines = self.Text.split("\n")
        w, h = max(map(len, lines)) * 0.6 * self.TextHeight, len(lines) * 1.6 * self.TextHeight
        return BoundingBox([self.Plane.PointAt(u, v) for u in (0, w) for v in (0, h)])

    def Transform(self, xf):
        self.Plane = Plane(xf.apply(self.Plane.Origin), self.Plane.XAxis, self.Plane.YAxis)


class AreaMassProperties:
    @staticmethod
    def Compute(curve):
        if not isinstance(curve, PolylineCurve) or not curve.IsClosed:
            return None
        p = curve.points
        a = abs(sum(u.X * v.Y - v.X * u.Y for u, v in zip(p, p[1:]))) / 2
        return types.SimpleNamespace(Area=a)


# ---- the document -----------------------------------------------------------------------------------------------

class Layer:
    """A Rhino 8 layer (modelled). In a table, setting IsVisible gives each sublayer this layer's own lock."""

    def __init__(self):
        self.Name, self.ParentLayerId, self.Id, self.IsDeleted = "", EMPTY_GUID, None, False
        self.Color = Color.Black
        self.IsLocked = False
        self._visible = True
        self.table = None

    @property
    def IsVisible(self):
        return self._visible

    @IsVisible.setter
    def IsVisible(self, on):
        self._visible = bool(on)
        if self.table is not None:
            for sub in self.table.descendants(self):
                sub.IsLocked = self.IsLocked

    @property
    def FullPath(self):
        if self.table is None:
            return self.Name
        parent = self.table.FindId(self.ParentLayerId, deleted=True)
        return (parent.FullPath + "::" if parent is not None else "") + self.Name

    @property
    def Index(self):
        return self.table.index(self)

    def GetChildren(self):
        kids = [x for x in self.table if x.ParentLayerId == self.Id and not x.IsDeleted]
        return kids or None


class LayerTable(list):
    def Add(self, layer):
        new = Layer()
        new.Name, new.ParentLayerId, new.Color = layer.Name, layer.ParentLayerId, layer.Color
        new.Id = layer.Id or str(uuid.uuid4())
        new.IsLocked, new._visible = layer.IsLocked, layer._visible
        new.table = self
        self.append(new)
        return len(self) - 1

    def FindByFullPath(self, path, missing=-1):
        for i, x in enumerate(self):
            if not x.IsDeleted and x.FullPath == path:
                return i
        return missing

    def FindId(self, layer_id, deleted=False):
        for x in self:
            if x.Id == layer_id and (deleted or not x.IsDeleted):
                return x
        return None

    def FindIndex(self, i):
        return self[i] if 0 <= i < len(self) else None

    def Delete(self, index, quiet=True):
        self[index].IsDeleted = True
        return True

    def ancestors(self, layer):
        out, parent = [], self.FindId(layer.ParentLayerId)
        while parent is not None:
            out.append(parent)
            parent = self.FindId(parent.ParentLayerId)
        return out

    def descendants(self, layer):
        return [x for x in self if x is not layer and not x.IsDeleted and x.FullPath.startswith(layer.FullPath + "::")]


class ObjectAttributes:
    DEFAULTS = {"Name": "", "Url": "", "Mode": "Normal", "Visible": True, "Space": "ModelSpace",
                "ViewportId": EMPTY_GUID, "DisplayOrder": 0, "WireDensity": 1, "ObjectDecoration": "None",
                "ColorSource": "ColorFromLayer", "LinetypeSource": "LinetypeFromLayer",
                "PlotColorSource": "PlotColorFromLayer", "PlotWeightSource": "PlotWeightFromLayer", "PlotWeight": 0.0,
                "MaterialSource": "MaterialFromLayer", "CastsShadows": True, "ReceivesShadows": True,
                "LinetypePatternScale": 1.0, "LayerIndex": 0, "LinetypeIndex": -1, "MaterialIndex": -1}

    def __init__(self):
        for k, v in self.DEFAULTS.items():
            setattr(self, k, v)
        self.ObjectColor, self.PlotColor = Color.Black, Color.Black
        self.ObjectId = EMPTY_GUID
        self.groups, self.strings = [], {}

    def Duplicate(self):
        a = ObjectAttributes()
        a.__dict__.update({k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
                           for k, v in self.__dict__.items()})
        return a

    def SetUserString(self, k, v):
        if v is None:
            self.strings.pop(k, None)
        else:
            self.strings[k] = str(v)
        return True

    def GetUserString(self, k):
        return self.strings.get(k)

    def GetUserStrings(self):
        return types.SimpleNamespace(AllKeys=list(self.strings))

    def AddToGroup(self, g):
        self.groups.append(g)

    def GetGroupList(self):
        return list(self.groups) or None


class ObjectPlotWeightSource:
    PlotWeightFromLayer, PlotWeightFromObject = "PlotWeightFromLayer", "PlotWeightFromObject"


class RhinoObject:
    def __init__(self, doc, oid, geometry, attrs):
        self.doc, self.Id, self.Geometry, self.Attributes = doc, oid, geometry, attrs

    @property
    def IsDeleted(self):
        return self.Id not in self.doc.Objects.by_id

    def Select(self, on=True):
        return self.doc.Objects.Select(self.Id, on)


class InstanceReferenceGeometry(GeometryBase):
    """A block placement (RhinoCommon Rhino.Geometry.InstanceReferenceGeometry: ParentIdefId, Xform). Its box is
    the definition's objects' boxes, placed (modelled). The definition is shared, never copied with the geometry."""

    def __init__(self, idef, xform):
        self.ParentIdefId, self._idef, self._xforms = idef.Id, idef, [xform]

    def __deepcopy__(self, memo):
        g = InstanceReferenceGeometry(self._idef, self._xforms[0])
        g._xforms = list(self._xforms)
        return g

    def _place(self, p):
        for xf in self._xforms:
            p = xf.apply(p)
        return p

    def GetBoundingBox(self, accurate=True):
        pts = [self._place(c) for o in self._idef.GetObjects() for c in o.Geometry.GetBoundingBox(True).GetCorners()]
        return BoundingBox(pts) if pts else BoundingBox()

    def Transform(self, xf):
        self._xforms.append(xf)
        return True


class InstanceDefinition:
    """RhinoCommon's InstanceDefinition: Name, Id, Index, GetObjects() (its objects, each with its own layer)."""

    def __init__(self, table, name, objects):
        self.table, self.Name, self.Id, self.objects = table, name, str(uuid.uuid4()), objects
        self.IsDeleted = False

    @property
    def Index(self):
        return self.table.index(self)

    def GetObjects(self):
        return list(self.objects)


class InstanceDefinitionTable(list):
    """doc.InstanceDefinitions: Add(name, description, basePoint, geometry, attributes) -> its index (-1 on failure),
    as RhinoCommon's overload taking IEnumerable<GeometryBase> and IEnumerable<ObjectAttributes>."""

    def __init__(self, doc):
        super().__init__()
        self.doc = doc

    def Add(self, name, description, base_point, geometry, attributes=None):
        geometry = list(geometry)
        attributes = list(attributes) if attributes is not None else [ObjectAttributes() for _ in geometry]
        if not geometry or len(attributes) != len(geometry) or self.Find(name) is not None:
            return -1
        back = Transform.Translation(-base_point.X, -base_point.Y, -base_point.Z)
        objs = []
        for g, a in zip(geometry, attributes):
            g = g.Duplicate()
            g.Transform(back)
            a = a.Duplicate()
            a.ObjectId = str(uuid.uuid4())
            objs.append(RhinoObject(None, a.ObjectId, g, a))     # idef objects: not in doc.Objects
        self.append(InstanceDefinition(self, name, objs))
        return len(self) - 1

    def Find(self, name):
        return next((d for d in self if d.Name == name and not d.IsDeleted), None)

    def FindId(self, idef_id):
        return next((d for d in self if d.Id == idef_id), None)


class InstanceObject(RhinoObject):
    """A block placed in the model: its Geometry an InstanceReferenceGeometry, its InstanceDefinition the doc's."""

    @property
    def InstanceDefinition(self):
        return self.doc.InstanceDefinitions.FindId(self.Geometry.ParentIdefId)


class ObjectEnumeratorSettings:
    def __init__(self):
        self.NormalObjects = self.LockedObjects = self.HiddenObjects = True
        self.IdefObjects = False


class ObjectTable:
    def __init__(self, doc):
        self.doc, self.by_id, self.selected = doc, {}, set()
        self.log = []                       # (action, id, ok)

    # the object's state as Rhino would see it (modelled)
    def _layer_chain(self, o):
        layer = self.doc.Layers[o.Attributes.LayerIndex]
        return [layer] + self.doc.Layers.ancestors(layer)

    def locked(self, o):
        return o.Attributes.Mode == "Locked" or any(x.IsLocked for x in self._layer_chain(o))

    def hidden(self, o):
        return any(not x.IsVisible for x in self._layer_chain(o))

    def _add(self, geometry, attrs, oid=None):
        a = (attrs or ObjectAttributes()).Duplicate()
        oid = oid or str(uuid.uuid4())
        a.ObjectId = oid
        cls = InstanceObject if isinstance(geometry, InstanceReferenceGeometry) else RhinoObject
        self.by_id[oid] = cls(self.doc, oid, geometry, a)
        self.doc._note("add", oid)
        return oid

    def AddCurve(self, curve, attrs=None):
        return self._add(curve.Duplicate(), attrs)

    def AddBrep(self, brep, attrs=None):
        return self._add(brep.Duplicate(), attrs)

    def AddTextDot(self, text, point, attrs=None):
        return self._add(TextDot(text, point), attrs)

    def AddText(self, text, attrs=None):
        return self._add(text.Duplicate(), attrs)

    def AddPoint(self, point, attrs=None):
        return self._add(Point(point), attrs)

    def AddInstanceObject(self, instance_definition_index, instance_xform, attributes=None):
        """RhinoCommon: Guid AddInstanceObject(int instanceDefinitionIndex, Transform instanceXform[,
        ObjectAttributes attributes]); Guid.Empty for an index that names no definition."""
        idefs = self.doc.InstanceDefinitions
        if not 0 <= instance_definition_index < len(idefs) or idefs[instance_definition_index].IsDeleted:
            return EMPTY_GUID
        return self._add(InstanceReferenceGeometry(idefs[instance_definition_index], instance_xform), attributes)

    def _id(self, x):
        return x.Id if isinstance(x, RhinoObject) else str(x)

    def FindId(self, oid):
        return self.by_id.get(str(oid))

    def Delete(self, x, quiet=True):
        o = self.by_id.get(self._id(x))
        ok = o is not None and not self.locked(o)
        if ok:
            del self.by_id[o.Id]
            self.selected.discard(o.Id)
            self.doc._note("delete", o.Id)
        self.log.append(("delete", self._id(x), ok))
        return ok

    def ModifyAttributes(self, x, attrs, quiet=True):
        o = self.by_id.get(self._id(x))
        ok = o is not None and not self.locked(o)
        if ok:
            a = attrs.Duplicate()
            a.ObjectId = o.Id
            o.Attributes = a
            self.doc._note("modify", o.Id)
        self.log.append(("modify", self._id(x), ok))
        return ok

    def Transform(self, x, xf, delete_original=True):
        o = self.by_id.get(self._id(x))
        if o is None or self.locked(o):
            return EMPTY_GUID
        g = o.Geometry.Duplicate()
        g.Transform(xf)
        if delete_original:
            o.Geometry = g                  # Rhino replaces the object, keeping its id (modelled)
            self.doc._note("replace", o.Id)
            return o.Id
        return self._add(g, o.Attributes)

    def FindByLayer(self, layer):
        i = layer.Index if isinstance(layer, Layer) else layer
        return [o for o in self.by_id.values() if o.Attributes.LayerIndex == i]

    def GetObjectList(self, settings=None):
        return list(self.by_id.values())

    def Select(self, x, on=True):
        o = self.by_id.get(self._id(x))
        if o is None or self.locked(o) or self.hidden(o):
            return False
        (self.selected.add if on else self.selected.discard)(o.Id)
        return True

    def UnselectAll(self, *a):
        n = len(self.selected)
        self.selected.clear()
        return n

    def GetSelectedObjects(self, *a):
        return [self.by_id[i] for i in self.selected if i in self.by_id]

    def __iter__(self):
        return iter(list(self.by_id.values()))


class Strings:
    def __init__(self):
        self.d = {}

    def SetString(self, section, key, value=None):
        if value is None:                    # SetString(key, value)
            section, key, value = None, section, key
        self.d[(section, key)] = value

    def GetValue(self, section, key=None):
        if key is None:
            return self.d.get((None, section))
        return self.d.get((section, key))

    def Delete(self, section, key):
        self.d.pop((section, key), None)

    @property
    def Count(self):
        return len(self.d)


class Groups(list):
    def Add(self, name=None):
        self.append(types.SimpleNamespace(Name=name, Id=str(uuid.uuid4())))
        return len(self) - 1

    def FindIndex(self, i):
        return self[i] if 0 <= i < len(self) else None


class Doc:
    serial = 100
    undo_serial = 0

    def __init__(self, dim_scale=12.0):
        Doc.serial += 1
        self.RuntimeSerialNumber = Doc.serial
        self.Layers = LayerTable()
        self.Objects = ObjectTable(self)
        self.Strings = Strings()
        self.Groups = Groups()
        self.InstanceDefinitions = InstanceDefinitionTable(self)
        self.Linetypes, self.Materials = Groups(), Groups()
        self.Linetypes.Add("Continuous")
        self.ModelUnitSystem = "Feet"
        self.ModelAbsoluteTolerance = 0.001
        self.ModelSpaceAnnotationScalingEnabled = True
        # the feet template's current dimension style: model-space scale 12 (the Rhino job's probe, PR #23)
        self.DimStyles = types.SimpleNamespace(Current=types.SimpleNamespace(DimensionScale=dim_scale))
        self.Views = Auto()
        self.Path, self.Name = None, None
        self.journal, self.undo_open = [], []   # every model change and undo record, in order (recorded)
        d = Layer()
        d.Name = "Default"
        self.Layers.Add(d)

    def Export(self, path):
        save_3dm(self, path)
        return True

    # ---- undo records (RhinoCommon: uint BeginUndoRecord(string description), bool EndUndoRecord(uint
    # undoRecordSerialNumber), bool UndoRecordingIsActive). RECORDED only: what Undo would put back is not modelled
    # (Undo / Redo are left out on purpose, so a script calling them fails loudly instead of passing).
    def BeginUndoRecord(self, description):
        assert isinstance(description, str), description
        Doc.undo_serial += 1
        serial = Doc.undo_serial
        self.undo_open.append(serial)
        self.journal.append(("begin_undo", serial, str(description)))
        return serial

    def EndUndoRecord(self, undo_record_serial_number):
        ok = bool(self.undo_open) and self.undo_open[-1] == undo_record_serial_number
        if ok:
            self.undo_open.pop()
        self.journal.append(("end_undo", undo_record_serial_number, ok))
        return ok

    @property
    def UndoRecordingIsActive(self):
        return bool(self.undo_open)

    def _note(self, action, oid):
        self.journal.append((action, str(oid), self.undo_open[-1] if self.undo_open else None))

    def Dispose(self):
        pass


# ---- a saved file -----------------------------------------------------------------------------------------------

def _r3_attrs(m, a, layer_map):
    ra = r3.ObjectAttributes()
    ra.Id = a.ObjectId
    ra.LayerIndex = layer_map.get(a.LayerIndex, 0)
    ra.Name = a.Name or ""
    ra.PlotWeight = a.PlotWeight
    if a.PlotWeightSource == ObjectPlotWeightSource.PlotWeightFromObject:
        ra.PlotWeightSource = r3.ObjectPlotWeightSource.PlotWeightFromObject
    for k, v in a.strings.items():
        ra.SetUserString(k, v)
    return ra


def _ccw(pts):
    s = sum(u.X * v.Y - v.X * u.Y for u, v in zip(pts, pts[1:] + pts[:1]))
    return pts if s > 0 else pts[::-1]


def save_3dm(doc, path, objects=None, layer_names=None):
    """The document as Rhino would save it (deleted layers are not saved), through rhino3dm: every live layer with
    its id and parent, every object with its id, layer, name, print width and user strings, every document string.
    Model text is written as a TextDot carrying its words (rhino3dm makes no model text)."""
    m = r3.File3dm()
    m.Settings.ModelUnitSystem = r3.UnitSystem.Feet
    layer_map = {}
    for i, x in enumerate(doc.Layers):
        if x.IsDeleted:
            continue
        la = r3.Layer()
        la.Name, la.Id = x.Name, x.Id
        if x.ParentLayerId != EMPTY_GUID:
            la.ParentLayerId = x.ParentLayerId
        la.Visible, la.Locked = x.IsVisible, x.IsLocked
        layer_map[i] = m.Layers.Add(la)
    for o in objects if objects is not None else doc.Objects:
        g, ra = o.Geometry, _r3_attrs(m, o.Attributes, layer_map)
        if isinstance(g, PolylineCurve):
            m.Objects.AddCurve(r3.PolylineCurve([r3.Point3d(p.X, p.Y, p.Z) for p in g.points]), ra)
        elif isinstance(g, TextDot):
            m.Objects.AddTextDot(g.Text, r3.Point3d(g.Point.X, g.Point.Y, g.Point.Z), ra)
        elif isinstance(g, TextEntity):
            p = g.Plane.Origin
            ra.SetUserString("fake:model_text", "1")
            m.Objects.AddTextDot(g.Text, r3.Point3d(p.X, p.Y, p.Z), ra)
        elif isinstance(g, Point):
            m.Objects.AddPoint(r3.Point3d(g.Location.X, g.Location.Y, g.Location.Z), ra)
        elif isinstance(g, Brep):
            base = _ccw(g.corners[:4])
            z0, z1 = min(p.Z for p in g.corners), max(p.Z for p in g.corners)
            ring = [r3.Point3d(p.X, p.Y, z0) for p in base]
            ext = r3.Extrusion.Create(r3.PolylineCurve(ring + ring[:1]), z1 - z0, True)
            m.Objects.Add(ext.ToBrep(True), ra)
        else:
            raise TypeError("cannot save %s" % type(g).__name__)
    for (section, key), value in doc.Strings.d.items():
        m.Strings[(section + "\\" if section else "") + key] = value
    m.Write(str(path), 8)
    return path


def open_3dm(path):
    """A saved file opened into a new document (as RhinoDoc.OpenHeadless would)."""
    f = r3.File3dm.Read(str(path))
    doc = Doc()
    del doc.Layers[:]
    for la in f.Layers:
        x = Layer()
        x.Name, x.Id = la.Name, str(la.Id)
        x.ParentLayerId = str(la.ParentLayerId) if str(la.ParentLayerId) != EMPTY_GUID else EMPTY_GUID
        x.IsLocked, x._visible = la.Locked, la.Visible
        x.table = doc.Layers
        doc.Layers.append(x)
    for o in f.Objects:
        ra, g = o.Attributes, o.Geometry
        a = ObjectAttributes()
        a.LayerIndex, a.Name, a.PlotWeight = ra.LayerIndex, ra.Name or "", ra.PlotWeight
        if ra.PlotWeightSource == r3.ObjectPlotWeightSource.PlotWeightFromObject:
            a.PlotWeightSource = ObjectPlotWeightSource.PlotWeightFromObject
        for k in ra.GetUserStrings() or ():
            k = k[0] if isinstance(k, tuple) else k
            if k != "fake:model_text":
                a.SetUserString(k, ra.GetUserString(k))
        if isinstance(g, r3.PolylineCurve):
            geom = PolylineCurve([Point3d(g.Point(i).X, g.Point(i).Y, g.Point(i).Z) for i in range(g.PointCount)])
        elif isinstance(g, r3.TextDot):
            if ra.GetUserString("fake:model_text"):
                geom = TextEntity()
                geom.Text, geom.Plane = g.Text, Plane(Point3d(g.Point.X, g.Point.Y, g.Point.Z))
            else:
                geom = TextDot(g.Text, Point3d(g.Point.X, g.Point.Y, g.Point.Z))
        elif isinstance(g, r3.Point):
            geom = Point(Point3d(g.Location.X, g.Location.Y, g.Location.Z))
        else:
            b = g.GetBoundingBox()
            geom = Brep.CreateFromBox(BoundingBox(b.Min.X, b.Min.Y, b.Min.Z, b.Max.X, b.Max.Y, b.Max.Z))
        doc.Objects._add(geom, a, oid=str(ra.Id))
    for i in range(len(f.Strings)):
        k, v = f.Strings[i]
        section, _, key = k.rpartition("\\")
        doc.Strings.d[(section or None, key)] = v
    doc.Path = str(path)
    return doc


class File3dm:
    """Rhino.FileIO.File3dm as gordium_rhino.export writes it (the checker's copy), and as a reader."""

    def __init__(self):
        self.Settings = types.SimpleNamespace(ModelUnitSystem="Feet")
        self.AllLayers = LayerTable()
        self.objects = []
        self.Objects = types.SimpleNamespace(Add=self._add)

    def _add(self, g, attrs):
        self.objects.append(RhinoObject(None, attrs.GetUserString("gordium:id") or str(uuid.uuid4()), g, attrs))

    def Write(self, path, version=8):
        doc = Doc()
        del doc.Layers[:]
        for la in self.AllLayers:
            doc.Layers.Add(la)
        save_3dm(doc, path, objects=self.objects)
        return True

    @staticmethod
    def Read(path):
        return SavedFile(path)


class SavedFile:
    """File3dm.Read as the in-Rhino scripts use it: Objects (Attributes, Geometry with PlainText), Strings."""

    def __init__(self, path):
        self.doc = open_3dm(path)
        self.Objects = list(self.doc.Objects)
        keys = list(self.doc.Strings.d)
        self.Strings = types.SimpleNamespace(
            Count=len(keys), GetKey=lambda i: (keys[i][0] + "\\" if keys[i][0] else "") + keys[i][1],
            GetValue=lambda a, b=None: self.doc.Strings.d[keys[a]] if isinstance(a, int) else
            self.doc.Strings.GetValue(a, b))


# ---- the modules ------------------------------------------------------------------------------------------------

def _module(name, cls=types.ModuleType, **attrs):
    m = cls(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


def install():
    """Rhino, Rhino.Geometry, Rhino.DocObjects, Rhino.FileIO, scriptcontext, System, Eto into sys.modules."""
    import fake_eto
    rg = _module("Rhino.Geometry", AutoModule, Point3d=Point3d, Vector3d=Vector3d, Point2d=Point2d, Plane=Plane,
                 BoundingBox=BoundingBox, Transform=Transform, Line=Line, Curve=Curve, PolylineCurve=PolylineCurve,
                 LineCurve=LineCurve, Polyline=Polyline, Brep=Brep, Mesh=Mesh, Extrusion=Extrusion, SubD=SubD,
                 Point=Point, TextDot=TextDot, TextEntity=TextEntity, TextJustification=TextJustification,
                 AreaMassProperties=AreaMassProperties, PointContainment=PointContainment,
                 GeometryBase=GeometryBase, InstanceReferenceGeometry=InstanceReferenceGeometry)
    dobj = _module("Rhino.DocObjects", AutoModule, ObjectAttributes=ObjectAttributes, Layer=Layer,
                   ObjectEnumeratorSettings=ObjectEnumeratorSettings, InstanceObject=InstanceObject,
                   InstanceDefinition=InstanceDefinition,
                   RhinoObject=RhinoObject, ObjectPlotWeightSource=ObjectPlotWeightSource)
    fileio = _module("Rhino.FileIO", AutoModule, File3dm=File3dm)

    class RhinoDoc:
        ActiveDoc = None
        open_docs = []

        @staticmethod
        def OpenHeadless(path):
            return open_3dm(path)

        @staticmethod
        def OpenDocuments():
            return list(RhinoDoc.open_docs)

    for ev in ("AddRhinoObject", "DeleteRhinoObject", "UndeleteRhinoObject", "ReplaceRhinoObject",
               "ModifyObjectAttributes", "NewDocument", "EndOpenDocument", "ActiveDocumentChanged"):
        setattr(RhinoDoc, ev, Event())

    class RhinoApp:
        Idle, Closing = Event(), Event()

        @staticmethod
        def WriteLine(text, *a):
            WRITTEN.append(str(text))

        @staticmethod
        def Wait():
            pass

        @staticmethod
        def RunScript(*a):
            return True

    class RhinoMath:
        @staticmethod
        def UnitScale(a, b):
            assert a == b == "Feet", (a, b)
            return 1.0

    class DisplayConduit:
        def __init__(self):
            self.Enabled = False

    display = _module("Rhino.Display", AutoModule, DisplayConduit=DisplayConduit)
    commands = _module("Rhino.Commands", AutoModule)
    commands.Result = types.SimpleNamespace(Success="Success", Cancel="Cancel", Nothing="Nothing")
    commands.Command = types.SimpleNamespace(BeginCommand=Event(), UndoRedo=Event(), __name__="Command")
    rhino = _module("Rhino", AutoModule, Geometry=rg, DocObjects=dobj, FileIO=fileio, RhinoDoc=RhinoDoc,
                    RhinoApp=RhinoApp, RhinoMath=RhinoMath, Display=display, Commands=commands,
                    UnitSystem=types.SimpleNamespace(Feet="Feet"))
    for sub in ("UI", "Input", "PlugIns"):
        setattr(rhino, sub, _module("Rhino." + sub, AutoModule))
    _module("scriptcontext", sticky={}, doc=None)
    drawing = _module("System.Drawing", AutoModule, Color=Color)
    diag = _module("System.Diagnostics", AutoModule)

    class _Process:
        Id = os.getpid()

        @staticmethod
        def GetCurrentProcess():
            return _Process

        @staticmethod
        def GetProcessById(pid):
            raise RuntimeError("no .NET processes here")

    diag.Process = _Process
    _module("System", AutoModule, Drawing=drawing, Diagnostics=diag, Guid=Guid)
    fake_eto.install()
    return rhino
