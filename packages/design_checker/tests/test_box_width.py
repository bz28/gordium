"""The start box fits a laptop screen (1366 x 768) with the longest questions under Use (coordinator, 2026-10-27:
"aim for <= ~900 px wide"). The Rhino run of demo 2c0a5c0 measured the R-1b box at 1,560-2,020 px: each question's
words sat on one line in the box's first column (#38's household questions run to ~190 characters).

This lays the real start box out (gordium_ui.start_box, run here with small stand-ins for Eto and Rhino that record
the controls and rows) and bounds its width the way Eto sizes a DynamicLayout: the first column as wide as its widest
cell, the second as wide as its widest, plus the padding and spacing. A label with a Width wraps there; one without
is as wide as its text. Text width uses CHAR_PX, a little wider than the system font measured in Rhino (the 2c0a5c0
box: 1,563 px for its widest row works out at ~5.5 px a character at size 12), so the bound errs wide."""

import sys
import types

import pytest

from design_checker import check
from design_checker import rhino_logic as logic
from rule_format.rulebook import REPO

CITY = "regulations/jurisdictions/new_york/ithaca_city"
LAPTOP_PX = 900                 # the box's width on a 1366 x 768 laptop, with room for Rhino around it
CHAR_PX = 6.0                   # px a character at size 12 (Rhino measured ~5.5); scaled by the font's size
PADDING, SPACING, ROW_SPACING = 14, 8, 6
# #38's (occupancy and home occupation) questions, as its rulebooks ask them: the longest the box asks today. Kept
# here so this branch, which comes before #38, is tested with them; on a branch with #38 they are its own words too.
LONG_QUESTIONS = [
    ("unrelated_persons", "count",
     "Most people in any one dwelling unit not related by blood, marriage or adoption to its household's family "
     "(minor dependent children in a parent's or relative's care left out)"),
    ("unrelated_persons_with_children", "count",
     "Most people in any one dwelling unit not related by blood, marriage or adoption to its household's family, "
     "minor dependent children counted too"),
    ("occupants", "count",
     "Occupants on this lot, all dwelling units together (§325-3B OCCUPANT: in R-2c, every person with the right to "
     "occupy, living there yet or not)"),
    ("abuts_r1_district", "yes_no",
     "Is any R-1a or R-1b land touching this lot (even at a corner), or across a street, alley, creek or other "
     "waterway, railroad or other right-of-way from it? (§325-19E)"),
    ("owner_occupied", "yes_no",
     "Does the owner (§325-3B OWNER) live in the one-family dwelling itself (not only in an accessory dwelling unit "
     "on the lot)?"),
    ("conversion", "yes_no", "Made by converting an existing building, not new construction? (§325-3B)"),
    ("home_occupation_area", "area",
     "Home occupation's indoor floor area, accessory buildings included (sq ft)"),
]


# ---- stand-ins for Eto and Rhino: they keep what the box sets, and nothing else ---------------------------------

class _Meta(type):
    def __getattr__(cls, name):            # ef.WrapMode.Word, ed.SystemFont.Bold, System.Drawing.Color …: a thing
        if name.startswith("__"):
            raise AttributeError(name)
        return _Meta(name, (_Thing,), {})

    def __getitem__(cls, _):               # ef.Dialog[bool]
        return cls


class _Thing(metaclass=_Meta):
    def __init__(self, *args, **kwargs):
        self.args = args

    def __getattr__(self, name):           # events (+=), Items, anything not set: another thing
        if name.startswith("__"):
            raise AttributeError(name)
        value = _Items() if name == "Items" else _Thing()
        object.__setattr__(self, name, value)
        return value

    def __iadd__(self, other):
        return self

    def __call__(self, *args, **kwargs):
        return _Thing()


class _Items(list):
    def Add(self, item):
        self.append(item if not isinstance(item, str) else _Text(item))

    def Clear(self):
        del self[:]


class _Text(str):
    @property
    def Text(self):
        return str(self)


class _DynamicLayout(_Thing):
    def __init__(self, *args):
        super().__init__(*args)
        self.rows = []

    def AddRow(self, *cells):
        self.rows.append(cells)


class _StackLayoutItem(_Thing):
    def __init__(self, control=None, *args):
        super().__init__(control, *args)
        self.control = control


def _module(name, **classes):
    m = types.ModuleType(name)

    def anything(attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        cls = classes.get(attr) or _Meta(attr, (_Thing,), {})
        setattr(m, attr, cls)
        return cls

    m.__getattr__ = anything
    for k, v in classes.items():
        setattr(m, k, v)
    return m


@pytest.fixture()
def ui(monkeypatch):
    forms = _module("Eto.Forms", DynamicLayout=_DynamicLayout, StackLayoutItem=_StackLayoutItem)
    drawing = _module("Eto.Drawing")
    eto = _module("Eto", Forms=forms, Drawing=drawing)
    rhino = _module("Rhino")
    for name, mod in {"Eto": eto, "Eto.Forms": forms, "Eto.Drawing": drawing, "Rhino": rhino,
                      "Rhino.Geometry": _module("Rhino.Geometry"), "Rhino.UI": _module("Rhino.UI"),
                      "System": _module("System"), "rhino_logic": logic}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.syspath_prepend(str(REPO / "apps/rhino_plugin"))
    monkeypatch.delitem(sys.modules, "gordium_ui", raising=False)
    import gordium_ui
    shown = {}
    monkeypatch.setattr(gordium_ui, "eto_status_color", lambda status: status)
    yield gordium_ui, shown
    monkeypatch.delitem(sys.modules, "gordium_ui", raising=False)


# ---- the width Eto gives each control, and the box -------------------------------------------------------------

def _text_px(text, size, bold=False):
    return len(text or "") * CHAR_PX * (size or 13) / 12 * (1.1 if bold else 1.0)


def _font(control):
    font = control.__dict__.get("Font")
    if font is None:
        return 13, False
    family, size = font.args
    return size, getattr(family, "__name__", family) == "Bold"


def width(c):
    """The width Eto gives control `c` (a stand-in): its Width if set, else its content's."""
    if c is None:
        return 0
    kind = type(c).__name__
    set_width = c.__dict__.get("Width")
    if isinstance(set_width, (int, float)) and kind != "StackLayout":
        return set_width
    if kind == "Label":
        size, bold = _font(c)
        return _text_px(c.__dict__.get("Text"), size, bold)
    if kind == "StackLayout":
        items = [width(i.control) for i in c.__dict__.get("Items", [])]
        return sum(items) + c.__dict__.get("Spacing", 0) * max(len(items) - 1, 0)
    if kind == "DropDown":
        return max([_text_px(t, 13) for t in c.__dict__.get("Items", [])] + [0]) + 32
    if kind in ("CheckBox", "Button"):
        return _text_px(c.__dict__.get("Text"), 13) + (22 if kind == "CheckBox" else 28)
    if kind == "TextBox":
        return 100
    if kind == "Expander":
        return max(width(c.__dict__.get("Header")), width(c.__dict__.get("Content")))
    raise AssertionError(f"no width for a {kind}: add it to width() (a control sized 0 could hide a wide box)")


def box_width(layout):
    """Eto's DynamicLayout: each column as wide as its widest cell; the box adds its padding on both sides."""
    columns = {}
    for cells in layout.rows:
        for i, cell in enumerate(cells):
            columns[i] = max(columns.get(i, 0), width(cell))
    return 2 * PADDING + sum(columns.values()) + SPACING * max(len(columns) - 1, 0), layout


def texts(layout):
    """Every label's text in the box, in the stack rows too."""
    out = []
    for cells in layout.rows:
        for c in cells:
            for x in [i.control for i in c.__dict__.get("Items", [])] if type(c).__name__ == "StackLayout" else [c]:
                if type(x).__name__ == "Label":
                    out.append(x.__dict__.get("Text"))
    return out


def laid_out(ui, state, options, mode="start"):
    gordium_ui, _ = ui
    seen = {}
    real = gordium_ui.ef.Dialog

    class Dialog(real):
        def ShowModal(self, *_):
            seen["layout"] = self.__dict__["Content"]

    gordium_ui.ef.Dialog = Dialog
    try:
        gordium_ui.start_box(state, options, mode)
    finally:
        gordium_ui.ef.Dialog = real
    return box_width(seen["layout"])


def _state(zone, use, questions):
    return {"address": "106 Ithaca Rd", "zone": zone, "use": use, "district_confirmed": False,
            "use_choices": [(use, "One-family dwelling, detached")], "follow_ups": questions,
            "lot": {"area_sf": 7033}, "zone_source": "City zoning map", "corner_lot": None,
            "street": {"name": "Ithaca Rd"}, "ground": {}, "answers": {}}


def _questions(rows):
    return [{"key": k, "label": text, "kind": kind, "value": None} for k, kind, text in rows]


def test_the_start_box_fits_a_laptop_with_the_longest_questions(ui):
    """Every question #38 asks, and every one this branch asks, in one box: still <= LAPTOP_PX wide."""
    mine = [(k, kind, text) for k, (text, kind, _) in logic.STATED_FACTS.items() if k in logic.BOX_ASKS]
    rows = LONG_QUESTIONS + [r for r in mine if r[0] not in dict((k, 1) for k, _, _ in LONG_QUESTIONS)]
    options = check.options(CITY)
    px, layout = laid_out(ui, _state("R-1b", "one_family_detached", _questions(rows)), options)
    assert rows[0][2] in texts(layout), "the longest question is laid out in the box"
    assert px <= LAPTOP_PX, f"the start box is {px:.0f} px wide with the longest questions"


def test_every_district_and_use_fits_a_laptop(ui):
    """Each district's own questions for each of its uses, as the box asks them (logic.follow_up_rows)."""
    options = check.options(CITY)
    widest = (0, None)
    for zone, uses in sorted(options["follow_ups"].items()):
        for use in uses:
            questions = logic.follow_up_rows(options, zone, use, {})
            px, _ = laid_out(ui, _state(zone, use, questions), options)
            widest = max(widest, (px, (zone, use)))
    assert widest[0] <= LAPTOP_PX, widest


def test_the_model_sizes_the_old_box_at_its_measured_width_or_wider(ui):
    """The 2c0a5c0 box's widest row, built as it was laid out (R-1b's unrelated-persons question unwrapped in the first
    column, a 60 px field and the help note beside it) and sized by width() / box_width: at least the 1,563 px Rhino
    measured, so a box this model passes is no wider in Rhino."""
    gordium_ui, _ = ui
    field = gordium_ui.ef.TextBox()
    field.Width = 60
    layout = gordium_ui.ef.DynamicLayout()
    layout.AddRow(gordium_ui.label(LONG_QUESTIONS[0][2], size=12),
                  gordium_ui.row(field, gordium_ui.label(logic.FOLLOW_UP_HELP, size=11)))
    assert box_width(layout)[0] >= 1563


def test_long_text_in_every_other_row_still_fits(ui, monkeypatch):
    """Every row's own text made long (a lookup's status, the district's source, the lot, the street, the ground,
    a review line, the corner question): each wraps, the box stays <= LAPTOP_PX."""
    long = "a long line of words the box shows, " * 8
    rows = [{"key": "address", "label": "Address", "text": "106", "actions": [("lookup", "Look up", True)],
             "matches": ["106 Ithaca Rd, Ithaca, NY 14850"], "status": long, "review": long, "check": ("I checked this", False)},
            {"key": "zone", "label": "Zoning district", "text": "R-1b · " + long, "tick": ("This is the lot's district",
                                                                                          False), "review": long},
            {"key": "use", "label": "Use", "text": "x"},
            {"key": "lot", "label": "Lot", "text": long, "actions": [("lot", "Change…", True), ("survey", "Use my "
                                                                                             "survey…", True)]},
            {"key": "street", "label": logic.STREET_LABEL, "help": long, "text": long, "actions": [("street",
                                                                                                "Change…", True)],
             "choice": (long, logic.CORNER_CHOICES, 0)},
            {"key": "ground", "label": "Ground", "text": long, "actions": [("ground", "Change…", True)],
             "tick": (long[:40], False)}]
    gordium_ui, _ = ui
    monkeypatch.setattr(gordium_ui.logic, "box_rows", lambda state: rows)
    state = dict(_state("R-1b", "one_family_detached", _questions(LONG_QUESTIONS)), use_note=long)
    px, layout = laid_out(ui, state, check.options(CITY))
    assert long in texts(layout) and px <= LAPTOP_PX, px


def test_each_refused_entry_is_named_in_the_one_note():
    assert logic.answers_note([]) == (logic.FOLLOW_UP_HELP, False)
    assert logic.answers_note([("dwelling_units", "count", "4"), ("rooms_let_for_profit", "count", "lots")]) == (
        "Rooms let for profit: Not kept: a whole number, 0 or more. Its rules need review until it is.", True)
    both = logic.answers_note([("dwelling_units", "count", "x"), ("rooms_let_for_profit", "count", "lots")])[0]
    assert both == ("Not kept: dwelling units (a whole number, 0 or more), rooms let for profit (a whole number, 0 or "
                    "more). Their rules need review until they are.")
    assert logic.answers_note([("dwelling_units", "count", "")]) == (logic.FOLLOW_UP_HELP, False)
