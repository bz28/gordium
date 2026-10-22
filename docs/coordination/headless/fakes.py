"""Stand-ins for Rhino 8, RhinoCommon, Eto and .NET, just enough to run the plugin's OWN functions headless.

Nothing here decides a Gordium result: geometry is rhino3dm (Rhino's own file library), the checker is the real
`design_checker serve` process, and the plugin's functions are exec'd from gordium_rhino.py / gordium_ui.py as
written. What these fakes stand in for (Eto widgets, the viewport, Rhino's document tables) is exactly the part
only Rhino can finally show, and every claim that leans on them is marked "partial"."""
import math
import sys
import types
import uuid

import rhino3dm as r


# ---- permissive "anything" (for colours, fonts, drawing calls whose result nobody reads) -----------------------

class Anything:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        v = Anything()
        object.__setattr__(self, n, v)
        return v

    def __call__(self, *a, **k):
        return Anything()

    def __getitem__(self, k):
        return Anything

    def __iadd__(self, o):
        return self

    def __isub__(self, o):
        return self

    def __iter__(self):
        return iter(())


class FakeModule(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        v = Anything()
        setattr(self, n, v)
        return v


# ---- geometry stand-ins for the drawing code (points, lines, boxes) --------------------------------------------

class P3:
    """Point3d / Vector3d / Point2d as the plugin's drawing code uses them."""

    def __init__(self, x=0.0, y=0.0, z=0.0):
        if hasattr(x, "X"):
            x, y, z = x.X, x.Y, getattr(x, "Z", 0.0)
        self.X, self.Y, self.Z = float(x), float(y), float(z)

    def __add__(self, o):
        return P3(self.X + o.X, self.Y + o.Y, self.Z + o.Z)

    def __sub__(self, o):
        return P3(self.X - o.X, self.Y - o.Y, self.Z - o.Z)

    def __mul__(self, k):
        if isinstance(k, P3):
            return self.X * k.X + self.Y * k.Y + self.Z * k.Z
        return P3(self.X * k, self.Y * k, self.Z * k)

    __rmul__ = __mul__

    def __truediv__(self, k):
        return P3(self.X / k, self.Y / k, self.Z / k)

    def __neg__(self):
        return P3(-self.X, -self.Y, -self.Z)

    def DistanceTo(self, o):
        return math.dist((self.X, self.Y, self.Z), (o.X, o.Y, o.Z))

    @property
    def Length(self):
        return math.sqrt(self * self)

    def Unitize(self):
        n = self.Length
        self.X, self.Y, self.Z = self.X / n, self.Y / n, self.Z / n
        return True

    def __repr__(self):
        return "P3(%.3f, %.3f, %.3f)" % (self.X, self.Y, self.Z)


P3.ZAxis = P3(0, 0, 1)


class FLine:
    def __init__(self, a, b):
        self.From, self.To = P3(a), P3(b)

    def DistanceTo(self, p, finite=True):
        a, b, p = self.From, self.To, P3(p)
        d = b - a
        t = ((p - a) * d) / (d * d) if d * d else 0.0
        if finite:
            t = min(1.0, max(0.0, t))
        return p.DistanceTo(a + d * t)

    @property
    def Length(self):
        return self.From.DistanceTo(self.To)


class _EmptyBox(type):
    @property
    def Empty(cls):
        return cls()


class FBox(metaclass=_EmptyBox):
    def __init__(self, a=None, b=None):
        self.Min, self.Max = (P3(a), P3(b)) if a is not None else (None, None)

    @property
    def IsValid(self):
        return self.Min is not None

    def Union(self, o):
        lo, hi = (o.Min, o.Max) if isinstance(o, FBox) else (P3(o), P3(o))
        if lo is None:
            return
        if self.Min is None:
            self.Min, self.Max = P3(lo), P3(hi)
        else:
            self.Min = P3(min(self.Min.X, lo.X), min(self.Min.Y, lo.Y), min(self.Min.Z, lo.Z))
            self.Max = P3(max(self.Max.X, hi.X), max(self.Max.Y, hi.Y), max(self.Max.Z, hi.Z))

    def Inflate(self, k):
        self.Min, self.Max = self.Min - P3(k, k, k), self.Max + P3(k, k, k)

    @property
    def Diagonal(self):
        return self.Max - self.Min

    @property
    def Center(self):
        return (self.Min + self.Max) / 2

    def GetCorners(self):
        a, b = self.Min, self.Max
        return [P3(x, y, z) for z in (a.Z, b.Z) for x, y in ((a.X, a.Y), (b.X, a.Y), (b.X, b.Y), (a.X, b.Y))]


def bbox_of(g):
    b = g.GetBoundingBox()
    return FBox(P3(b.Min.X, b.Min.Y, b.Min.Z), P3(b.Max.X, b.Max.Y, b.Max.Z))


# ---- rhino3dm geometry behind RhinoCommon-shaped document objects ----------------------------------------------

class Geo:
    """A rhino3dm geometry with RhinoCommon's few extra calls (GetBoundingBox(True), DuplicateSegments,
    TryGetPolyline). Its class name is the RhinoCommon one ("PolylineCurve", "Brep"), as logic.classify reads it."""

    def __init__(self, raw):
        object.__setattr__(self, "raw", raw)

    def __getattr__(self, n):
        return getattr(self.raw, n)

    def GetBoundingBox(self, accurate=True):
        return bbox_of(self.raw)

    def points(self):
        return [P3(self.raw.Point(i).X, self.raw.Point(i).Y, self.raw.Point(i).Z) for i in range(self.raw.PointCount)]

    def DuplicateSegments(self):
        pts = self.points()
        return [types.SimpleNamespace(PointAtStart=a, PointAtEnd=b) for a, b in zip(pts, pts[1:])]

    def TryGetPolyline(self):
        return True, self.points()


def geo(raw):
    cls = type(type(raw).__name__, (Geo,), {})
    return cls(raw)


class FAttrs:
    def __init__(self, layer_index, name=None, strings=None):
        self.LayerIndex, self.Name, self.strings = layer_index, name, dict(strings or {})

    def GetUserString(self, k):
        return self.strings.get(k)

    def SetUserString(self, k, v):
        if v is None:
            self.strings.pop(k, None)
        else:
            self.strings[k] = v

    def GetGroupList(self):
        return [0]


class FObj:
    def __init__(self, raw, layer_index, name=None, strings=None):
        self.Id = str(uuid.uuid4())
        self.Geometry = geo(raw)
        self.Attributes = FAttrs(layer_index, name, strings)
        self.selected = False

    def IsSelectable(self):
        return True

    def Select(self, on):
        self.selected = bool(on)


class FLayer:
    def __init__(self, path):
        self.FullPath, self.IsDeleted, self.IsVisible, self.IsLocked = path, False, True, False


class FLayers(list):
    def FindByFullPath(self, path, default):
        return next((i for i, x in enumerate(self) if x.FullPath == path and not x.IsDeleted), default)

    def add_path(self, path):
        i = self.FindByFullPath(path, -1)
        if i < 0:
            self.append(FLayer(path))
            i = len(self) - 1
        return i


class FObjects:
    def __init__(self):
        self.all = []

    def GetObjectList(self, settings=None):
        return list(self.all)

    def FindId(self, object_id):
        return next((o for o in self.all if o.Id == str(object_id)), None)

    def UnselectAll(self):
        for o in self.all:
            o.selected = False

    def GetSelectedObjects(self, a=False, b=False):
        return [o for o in self.all if o.selected]

    def Delete(self, o, quiet=True):
        self.all.remove(o)
        return True


class FStrings:
    def __init__(self):
        self.d = {}

    def GetValue(self, section, key):
        return self.d.get((section, key))

    def SetString(self, section, key, value):
        self.d[(section, key)] = value

    def Delete(self, section, key):
        self.d.pop((section, key), None)


class FViewport:
    """A viewport: Top (plan), Front/Right (elevations) or Perspective, `w` x `h` pixels, parallel projection
    zoomed by ZoomBoundingBox (fit, centred), as Rhino frames a box."""
    _n = 0

    def __init__(self, kind, w=1000, h=640):
        FViewport._n += 1
        self.Id = "vp-%s-%d" % (kind, FViewport._n)
        self.kind = kind
        self.Bounds = types.SimpleNamespace(Width=w, Height=h)
        self.Size = types.SimpleNamespace(Width=w, Height=h)
        self.IsParallelProjection = kind != "Perspective"
        self.CameraDirection = P3(*{"Top": (0, 0, -1), "Front": (0, 1, 0), "Right": (-1, 0, 0),
                                    "Perspective": (-0.5, 0.6, -0.6)}[kind])
        self.c, self.k = P3(0, 0, 0), 1.0

    def _uv(self, p):
        return {"Top": (p.X, p.Y), "Front": (p.X, p.Z), "Right": (p.Y, p.Z),
                "Perspective": (p.X - 0.5 * p.Y, p.Z + 0.3 * (p.X + p.Y))}[self.kind]

    def ZoomBoundingBox(self, box):
        us, vs = zip(*[self._uv(q) for q in box.GetCorners()])
        self.c = ((min(us) + max(us)) / 2, (min(vs) + max(vs)) / 2)
        self.k = min(self.Bounds.Width / max(max(us) - min(us), 1e-9), self.Bounds.Height / max(max(vs) - min(vs), 1e-9))
        return True

    def WorldToClient(self, p):
        u, v = self._uv(P3(p))
        return P3((u - self.c[0]) * self.k + self.Bounds.Width / 2, self.Bounds.Height / 2 - (v - self.c[1]) * self.k)


class FView:
    def __init__(self, name, w=1000, h=640):
        self.Name = name
        self.ActiveViewport = FViewport(name, w, h)
        self.ActiveViewportID = self.ActiveViewport.Id

    def Redraw(self):
        pass


class FViews(list):
    def __init__(self, w=1000, h=640):
        super().__init__(FView(n, w, h) for n in ("Top", "Front", "Right", "Perspective"))
        self.ActiveView = self[3]

    def Find(self, name, _=False):
        return next((v for v in self if v.Name == name), None)

    def Redraw(self):
        pass


class FDoc:
    _serial = 100

    def __init__(self, path=None, w=1000, h=640):
        FDoc._serial += 1
        self.RuntimeSerialNumber = FDoc._serial
        self.Path, self.Name = path, None
        self.ModelUnitSystem = r.UnitSystem.Feet
        self.ModelAbsoluteTolerance = 0.001
        self.Strings, self.Objects, self.Layers, self.Views = FStrings(), FObjects(), FLayers(), FViews(w, h)

    def add(self, raw, layer_path, name=None, strings=None):
        o = FObj(raw, self.Layers.add_path(layer_path), name, strings)
        self.Objects.all.append(o)
        return o


class File3dmAdapter:
    """Rhino.FileIO.File3dm (RhinoCommon) on rhino3dm.File3dm: what gordium_rhino.export writes."""

    def __init__(self):
        self.f = r.File3dm()
        self.Settings = self.f.Settings
        self.AllLayers = self.f.Layers
        self.Objects = types.SimpleNamespace(Add=lambda g, a: self.f.Objects.Add(getattr(g, "raw", g), a))

    def Write(self, path, version):
        return self.f.Write(path, version)


def area_props(g):
    pts = g.points()
    a = abs(sum(p.X * q.Y - q.X * p.Y for p, q in zip(pts, pts[1:]))) / 2
    return types.SimpleNamespace(Area=a)


# ---- Eto.Forms: the widgets the panel and the start box build, with their events ------------------------------

class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, h):
        self.handlers.append(h)
        return self

    def __isub__(self, h):
        self.handlers.remove(h)
        return self

    def fire(self, sender=None, e=None):
        for h in list(self.handlers):
            h(sender, e)


EVENTS = {"Click", "CheckedChanged", "SelectedIndexChanged", "KeyDown", "TextChanged", "LoadComplete", "Shown",
          "Closed", "Elapsed"}


class Control:
    def __init__(self, *a, **k):
        self.Enabled, self.Visible = True, True

    def __getattr__(self, n):
        if n in EVENTS:
            ev = Event()
            object.__setattr__(self, n, ev)
            return ev
        raise AttributeError(n)

    def kids(self):
        return []

    @property
    def Children(self):
        out = []
        for c in self.kids():
            if c is None:
                continue
            out.append(c)
            out.extend(c.Children if isinstance(c, Control) else [])
        return out


class Label(Control):
    def __init__(self):
        super().__init__()
        self.Text = ""


class Button(Control):
    def __init__(self):
        super().__init__()
        self.Text = ""


class LinkButton(Control):
    def __init__(self):
        super().__init__()
        self.Text = ""


class CheckBox(Control):
    def __init__(self):
        super().__init__()
        self.Text, self.Checked = "", False


class TextBox(Control):
    def __init__(self):
        super().__init__()
        self.Text = ""


class ListItem:
    def __init__(self, text):
        self.Text = text


class Items(list):
    def Add(self, x):
        self.append(ListItem(x) if isinstance(x, str) else x)


class DropDown(Control):
    def __init__(self):
        super().__init__()
        self.Items, self._i = Items(), -1

    @property
    def SelectedIndex(self):
        return self._i

    @SelectedIndex.setter
    def SelectedIndex(self, i):
        self._i = i

    @property
    def SelectedValue(self):
        return self.Items[self._i] if 0 <= self._i < len(self.Items) else None

    @SelectedValue.setter
    def SelectedValue(self, item):
        self._i = self.Items.index(item) if item is not None and item in self.Items else -1

    def choose(self, text):
        self._i = [x.Text for x in self.Items].index(text)
        self.SelectedIndexChanged.fire(self, None)


class StackLayoutItem:
    def __init__(self, c, *a):
        self.Control = c


class StackLayout(Control):
    def __init__(self):
        super().__init__()
        self.Items = Items()

    def kids(self):
        return [i.Control for i in self.Items]


class DynamicLayout(Control):
    def __init__(self):
        super().__init__()
        self.rows = []

    def AddRow(self, *controls):
        self.rows.append(list(controls))

    def Add(self, c):
        self.rows.append([c])

    def Clear(self):
        self.rows = []

    def Create(self):
        pass

    def kids(self):
        return [c for row in self.rows for c in row]


class Expander(Control):
    def kids(self):
        return [getattr(self, "Header", None), getattr(self, "Content", None)]


class Dialog(Control):
    def __class_getitem__(cls, item):
        return cls

    def __init__(self):
        super().__init__()
        self.Content, self.closed_with, self.shown = None, "never", 0

    def kids(self):
        return [self.Content]

    def Close(self, result=None):
        self.closed_with = result

    def ShowModal(self, owner=None):
        self.shown += 1
        self.Shown.fire(self, None)
        return self.closed_with


class UITimer(Control):
    def Start(self):
        pass

    def Stop(self):
        pass


def eto_forms():
    m = FakeModule("Eto.Forms")
    for c in (Label, Button, LinkButton, CheckBox, TextBox, DropDown, StackLayout, StackLayoutItem, DynamicLayout,
              Expander, Dialog, UITimer):
        setattr(m, c.__name__, c)
    m.ImageView = type("ImageView", (Control,), {})
    return m


# ---- System, Rhino, scriptcontext ---------------------------------------------------------------------------

class Col:
    def __init__(self, *argb):
        self.A, self.R, self.G, self.B = ((255,) + argb)[-4:] if len(argb) == 3 else argb

    @staticmethod
    def FromArgb(*a):
        return Col(*a)


class PointF:
    def __init__(self, x, y):
        self.X, self.Y = x, y


class Result:
    Success, Cancel, Nothing = "Success", "Cancel", "Nothing"


def install(said):
    """Put the stand-ins in sys.modules; `said` collects Rhino's command line."""
    system = FakeModule("System")
    drawing = FakeModule("System.Drawing")
    drawing.Color, drawing.PointF = Col, PointF
    system.Drawing = drawing
    system.Guid = lambda s: str(s)

    rg = FakeModule("Rhino.Geometry")
    rg.Point3d, rg.Vector3d, rg.Point2d, rg.Line, rg.BoundingBox = P3, P3, P3, FLine, FBox
    rg.PolylineCurve = lambda pts: types.SimpleNamespace(points=list(pts))
    rg.Brep = type("Brep", (), {"CreatePlanarBreps": staticmethod(lambda curves, tol: [object()])})
    rg.Mesh, rg.SubD, rg.Extrusion, rg.Point = (type(n, (), {}) for n in ("Mesh", "SubD", "Extrusion", "Point"))
    rg.AreaMassProperties = types.SimpleNamespace(Compute=area_props)

    rhino = FakeModule("Rhino")
    rhino.Geometry = rg
    rhino.Commands = types.SimpleNamespace(Result=Result, Command=Anything())
    rhino.RhinoApp = types.SimpleNamespace(WriteLine=lambda t: said.append(t), Wait=lambda: None)
    rhino.RhinoDoc = types.SimpleNamespace(ActiveDoc=None)
    rhino.RhinoMath = types.SimpleNamespace(UnitScale=lambda a, b: 1.0)       # every fake document is in feet
    rhino.UnitSystem = types.SimpleNamespace(Feet=r.UnitSystem.Feet)
    rhino.FileIO = types.SimpleNamespace(File3dm=File3dmAdapter)
    rhino.DocObjects = types.SimpleNamespace(Layer=r.Layer, ObjectAttributes=r.ObjectAttributes,
                                             InstanceObject=type("InstanceObject", (), {}),
                                             ObjectEnumeratorSettings=lambda: types.SimpleNamespace())
    rhino.ApplicationSettings = types.SimpleNamespace(AppearanceSettings=types.SimpleNamespace(
        ViewportBackgroundColor=Col(255, 255, 255)))

    eto = FakeModule("Eto")
    ef, ed = eto_forms(), FakeModule("Eto.Drawing")
    eto.Forms, eto.Drawing = ef, ed
    sc = FakeModule("scriptcontext")
    sc.sticky = {}
    for name, m in {"System": system, "System.Drawing": drawing, "Rhino": rhino, "Rhino.Geometry": rg,
                    "Eto": eto, "Eto.Forms": ef, "Eto.Drawing": ed, "scriptcontext": sc}.items():
        sys.modules[name] = m
    return types.SimpleNamespace(System=system, Rhino=rhino, rg=rg, ef=ef, ed=ed, sc=sc)
