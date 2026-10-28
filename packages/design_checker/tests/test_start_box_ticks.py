"""The start box itself (apps/rhino_plugin/gordium_ui.start_box), driven off Rhino: a small stand-in for Eto (the
window toolkit) lets the real box code run here, so a test can tick, pick and press Draw as the architect would, and
read what the box would hand back. Never a district checked that the architect didn't confirm (never a false pass)."""
import importlib
import sys
import types
from pathlib import Path

import pytest

from design_checker import rhino_logic as logic

REPO = Path(__file__).resolve().parents[3]
EVENTS = {"CheckedChanged", "SelectedIndexChanged", "KeyDown", "TextChanged", "Shown", "Closed", "Elapsed", "Click",
          "LoadComplete"}


class Event:
    """An Eto event: `+=` adds a handler, fire() calls them in order."""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self

    def fire(self, sender):
        for fn in list(self.handlers):
            fn(sender, None)


class Thing:
    """Any Eto object: attributes are kept, events are Events, anything else is another Thing."""

    def __init__(self, *args, **kwargs):
        self.__dict__["_events"] = {}
        self.__dict__["args"] = args

    def __getattr__(self, name):
        if name in EVENTS:
            return self._events.setdefault(name, Event())
        if name.startswith("__"):
            raise AttributeError(name)
        value = Thing()
        self.__dict__[name] = value
        return value

    def __setattr__(self, name, value):
        if name in EVENTS:                      # `x.Click += f` sets the Event back
            self._events[name] = value
        else:
            self.__dict__[name] = value

    def __call__(self, *args, **kwargs):
        return Thing(*args, **kwargs)

    def __iadd__(self, fn):                     # any other event (`x.MouseUp += f`): kept, never fired
        self.__dict__.setdefault("handlers", []).append(fn)
        return self

    def __getitem__(self, _):
        return Thing


class Items(list):
    def Add(self, x):
        self.append(x if isinstance(x, Thing) else _item(x))


def _item(text):
    t = Thing()
    t.Text = text
    return t


class CheckBox(Thing):
    """Checked as Eto has it: setting a new value fires CheckedChanged."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.__dict__["_checked"] = False

    @property
    def Checked(self):
        return self._checked

    @Checked.setter
    def Checked(self, value):
        changed = bool(value) != self._checked
        self.__dict__["_checked"] = bool(value)
        if changed:
            self.CheckedChanged.fire(self)

    def __setattr__(self, name, value):
        if name == "Checked":
            object.__setattr__(self, name, value)
        else:
            super().__setattr__(name, value)


class DropDown(Thing):
    """SelectedIndex and SelectedValue as Eto has them: a new selection fires SelectedIndexChanged."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.__dict__.update(Items=Items(), _index=-1)

    def _select(self, index):
        changed = index != self._index
        self.__dict__["_index"] = index
        if changed:
            self.SelectedIndexChanged.fire(self)

    def __setattr__(self, name, value):
        if name == "SelectedIndex":
            self._select(value)
        elif name == "SelectedValue":
            self._select(self.Items.index(value) if value is not None else -1)
        else:
            super().__setattr__(name, value)

    def __getattr__(self, name):
        if name == "SelectedIndex":
            return self._index
        if name == "SelectedValue":
            return self.Items[self._index] if self._index >= 0 else None
        return super().__getattr__(name)


class Dialog(Thing):
    script = None                              # what the architect does while the box is shown

    def ShowModal(self, owner=None):
        self.Shown.fire(self)
        Dialog.script(self)

    def Close(self, result=None):
        self.__dict__["closed"] = result


@pytest.fixture
def box(monkeypatch):
    """gordium_ui imported over the Eto stand-in; returns run(state, script) -> (what the box returned, its controls)."""
    made = {"CheckBox": [], "DropDown": [], "Button": []}

    def maker(cls, kind):
        def make(*a, **k):
            obj = cls(*a, **k)
            made[kind].append(obj)
            return obj
        return make

    forms = Thing()
    forms.__dict__.update(CheckBox=maker(CheckBox, "CheckBox"), DropDown=maker(DropDown, "DropDown"),
                          Button=maker(Thing, "Button"), Dialog={bool: Dialog}, TextBox=Thing, Label=Thing)
    fake = {"System": Thing(), "Eto": Thing(), "Eto.Drawing": Thing(), "Eto.Forms": forms, "Rhino": Thing(),
            "Rhino.Geometry": Thing()}
    fake["Eto"].Drawing, fake["Eto"].Forms = fake["Eto.Drawing"], forms
    for name, mod in fake.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setitem(sys.modules, "rhino_logic", logic)
    monkeypatch.setattr(logic, "guard", lambda fn, where, fallback=None: fn)     # errors surface in the test
    monkeypatch.syspath_prepend(str(REPO / "apps/rhino_plugin"))
    sys.modules.pop("gordium_ui", None)
    ui = importlib.import_module("gordium_ui")
    monkeypatch.setattr(ui, "_dark_panel", lambda: False)
    monkeypatch.setattr(ui, "button", lambda text, action, enabled=True: _button(made, text, action, enabled))

    def run(state, script, options=None, mode="start"):
        for v in made.values():
            v.clear()
        options = options or {"zones": ["R-1a", "R-1b", "R-2a", "R-3a"], "uses": {"single_family": "One-family"}}

        def act(dialog):
            zone, confirm, draw = made["DropDown"][0], made["CheckBox"][0], made["Button"]
            script(zone, confirm, {b.Text: b for b in draw})

        Dialog.script = act
        what = ui.start_box(state, options, mode)
        sys.modules.pop("gordium_ui", None)
        return what

    return run


def _button(made, text, action, enabled):
    b = Thing()
    b.Text, b.Enabled, b.action = text, enabled, action
    made["Button"].append(b)
    return b


def _pick(zone, name):
    zone.SelectedIndex = [x.Text for x in zone.Items].index(name)


def _press(buttons, text):
    """Press a button as the architect can: only when it is on (the box's Draw is off until it may draw)."""
    if buttons[text].Enabled:
        buttons[text].action()


def _state(**kw):
    return dict({"zone": "R-1b", "zone_source": "suggested by Gordium", "district_confirmed": False,
                 "use": "single_family", "design_buffer": "0'-0\""}, **kw)


def test_picking_another_district_after_i_confirm_unticks_it(box):
    """The bug (from #19): tick I confirm on R-1b, pick R-2a, press Draw: the box drew with R-2a marked confirmed,
    a district the architect never confirmed. Picking a district unticks I confirm and Draw waits for it."""
    state = _state()
    seen = {}

    def script(zone, confirm, buttons):
        confirm.Checked = True                                  # the architect confirms R-1b
        assert buttons["Draw"].Enabled
        _pick(zone, "R-2a")                                     # ...then picks another district
        seen.update(ticked=confirm.Checked, draw_on=buttons["Draw"].Enabled)
        _press(buttons, "Draw")

    what = box(state, script)
    assert seen == {"ticked": False, "draw_on": False}
    assert state["zone"] == "R-2a" and not state["district_confirmed"] and not logic.can_draw(state)
    assert what is None                                         # Draw was off: nothing drawn


def test_picking_another_district_with_no_lookup_at_all(box):
    """No lookup, an existing project whose R-1b was confirmed at an earlier Draw (starts ticked): picking R-1a
    unticks it; ticking again confirms R-1a and Draw comes on."""
    state = _state(district_confirmed=True, zone_source=logic.ENTERED)
    seen = {}

    def script(zone, confirm, buttons):
        _pick(zone, "R-1a")
        seen["after_pick"] = (confirm.Checked, buttons["Check"].Enabled)
        confirm.Checked = True
        seen["after_tick"] = buttons["Check"].Enabled
        _press(buttons, "Check")

    assert box(state, script, mode="check") == "draw"
    assert seen == {"after_pick": (False, False), "after_tick": True}
    assert state["zone"] == "R-1a" and state["district_confirmed"]


def test_picking_a_district_then_going_elsewhere_keeps_it_unconfirmed(box):
    """A pick (lot, street side) closes the box and opens it again: the district picked meanwhile goes out
    unconfirmed in the state the box hands back (the state _box_loop's ticks are copied from)."""
    state = _state(has_lot=True, lot_area=5000.0)

    def script(zone, confirm, buttons):
        confirm.Checked = True
        _pick(zone, "R-3a")
        buttons["Use my survey…"].action()

    what = box(state, script)
    assert what == "pick:lot" and state["zone"] == "R-3a" and state["district_confirmed"] is False


def test_zone_picked_unticks_only_on_a_change():
    """The logic under the box: a different district unticks; the same one (no change) leaves the tick alone."""
    state = {"zone": "R-1b", "district_confirmed": True}
    logic.zone_picked(state, "R-1b", "R-1b")
    assert state["district_confirmed"]
    logic.zone_picked(state, "R-2a", "R-1b")
    assert not state["district_confirmed"] and not logic.can_draw(state)
    logic.zone_picked(state, "R-1b", "R-1b")                    # back to the first: confirm it again
    assert not state["district_confirmed"]
