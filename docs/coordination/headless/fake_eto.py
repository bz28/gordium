"""Eto stand-ins: a CheckBox whose Checked setter fires CheckedChanged on a change (as Eto does for a click), rows
(StackLayout with Items of StackLayoutItem.Control), buttons with Enabled; every other widget inert (Auto)."""
import sys
import types

from fakerhino import Auto, AutoModule, Event


class Widget:
    """Enabled as Eto reports it (modelled on the Rhino run at 64d1425, where a checkbox in a greyed row read
    Enabled=False): the control's own setting and its parent row's."""

    def __init__(self, *a, **k):
        object.__setattr__(self, "_parent", None)
        self.Enabled = True
        self.Visible = False
        self.Text = ""

    @property
    def Enabled(self):
        parent = self.__dict__.get("_parent")
        return self.__dict__.get("_enabled", True) and (parent is None or parent.Enabled)

    @Enabled.setter
    def Enabled(self, v):
        self.__dict__["_enabled"] = bool(v)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        v = Event() if name in ("Click", "CheckedChanged", "Shown", "Closed", "LoadComplete", "SelectedItemChanged",
                                "CellDoubleClick", "Paint", "Elapsed", "SelectedIndexChanged") else Auto()
        object.__setattr__(self, name, v)
        return v

    def Show(self):
        self.Visible = True

    def Close(self, *a):
        self.Visible = False


class CheckBox(Widget):
    def __init__(self):
        super().__init__()
        self._checked = False

    @property
    def Checked(self):
        return self._checked

    @Checked.setter
    def Checked(self, v):
        changed = bool(v) != self._checked
        self._checked = bool(v)
        if changed:
            self.CheckedChanged.fire(self, None)


class _Items(list):
    def Add(self, x):
        self.append(x)
        control = getattr(x, "Control", None)
        if isinstance(control, Widget):
            control.__dict__["_parent"] = self.owner


class StackLayout(Widget):
    def __init__(self):
        super().__init__()
        self.Items = _Items()
        self.Items.owner = self


class StackLayoutItem:
    def __init__(self, control=None, *a):
        self.Control = control


class Button(Widget):
    pass


class DynamicLayout(Widget):
    def __init__(self):
        super().__init__()
        self.rows = []

    def Add(self, *a, **k):
        self.rows.append(a)

    def AddRow(self, *a, **k):
        self.rows.append(a)

    def Clear(self):
        self.rows = []


class Collection(list):
    def Add(self, x):
        self.append(x)


class TreeGridView(Widget):
    def __init__(self):
        super().__init__()
        self.Columns = Collection()
        self.SelectedItem = None


class ListItem:
    def __init__(self, text):
        self.Text = text


class _ListItems(list):
    def Add(self, x):
        self.append(x if isinstance(x, ListItem) else ListItem(x))


class DropDown(Widget):
    """Eto's DropDown: SelectedIndexChanged fires on a change of selection (made by the code or the architect)."""

    def __init__(self):
        super().__init__()
        self.Items = _ListItems()
        self._index = -1

    @property
    def SelectedIndex(self):
        return self._index

    @SelectedIndex.setter
    def SelectedIndex(self, i):
        changed = i != self._index
        self._index = i
        if changed:
            self.SelectedIndexChanged.fire(self, None)

    @property
    def SelectedValue(self):
        return self.Items[self._index] if 0 <= self._index < len(self.Items) else None

    @SelectedValue.setter
    def SelectedValue(self, v):
        self.SelectedIndex = next((k for k, x in enumerate(self.Items) if x is v), -1)


class TextBox(Widget):
    pass


class Label(Widget):
    pass


TIMERS = []
USER = []          # the scripted architect: USER[0](dialog) runs while a dialog is shown (modal)


class UITimer(Widget):
    def __init__(self):
        super().__init__()
        self.running = False
        TIMERS.append(self)

    def Start(self):
        self.running = True

    def Stop(self):
        self.running = False


class Dialog(Widget):
    def __class_getitem__(cls, item):
        return cls

    def ShowModal(self, owner=None):
        self.Visible = True
        self.Shown.fire(self, None)
        if USER:
            USER[0](self)
        return False

    def Close(self, result=None):
        if self.Visible:
            self.Visible = False
            self.Closed.fire(self, None)


def controls(c):
    """Every control under a layout (rows, StackLayout items, an Expander's content), depth first."""
    out = [c]
    for r in getattr(c, "rows", None) or []:
        for x in r:
            if x is not None and not isinstance(x, (str, int, float)):
                out += controls(x)
    for it in c.__dict__.get("Items") or [] if isinstance(c, StackLayout) else []:
        out += controls(it.Control)
    content = c.__dict__.get("Content")
    if content is not None:
        out += controls(content)
    return out


class EtoForms(AutoModule):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name[:1].isupper() and name not in ("WrapMode", "TextAlignment", "Orientation", "VerticalAlignment",
                                               "HorizontalAlignment", "DialogResult", "MessageBox"):
            cls = type(name, (Widget,), {})
            setattr(self, name, cls)
            return cls
        return super().__getattr__(name)


def install():
    ef = EtoForms("Eto.Forms")
    ef.__dict__.update(CheckBox=CheckBox, StackLayout=StackLayout, StackLayoutItem=StackLayoutItem, Button=Button,
                       DynamicLayout=DynamicLayout, TreeGridView=TreeGridView, DropDown=DropDown,
                       TextBox=TextBox, Label=Label, UITimer=UITimer, Dialog=Dialog, Panel=Widget, Form=type("Form", (Widget,), {}))
    ed = AutoModule("Eto.Drawing")
    eto = types.ModuleType("Eto")
    eto.Forms, eto.Drawing = ef, ed
    sys.modules.update({"Eto": eto, "Eto.Forms": ef, "Eto.Drawing": ed})
