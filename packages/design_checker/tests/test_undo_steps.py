"""Every panel change is exactly one Rhino undo step (Ben, 2026-10-26). A change written to the .3dm outside any undo
record is skipped by Ctrl+Z, which undoes the architect's own earlier edit instead (found by #32's review: Use my
survey, Enter …, Pick the main building, Add to check). The guard runs every panel action, through the panel's own
gate (_actions), on a fake document that refuses a write with no undo record open and counts the records."""

import json
from pathlib import Path

import pytest

from design_checker import rhino_logic as logic

REPO = Path(__file__).resolve().parents[3]
SRC = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")

# the plugin's own code, run as written (each function's source from gordium_rhino.py)
REAL = ["PANEL_ACTIONS", "_actions", "pick_survey", "enter_rooms", "pick_main_building", "add_to_check",
        "this_is_the_ground", "not_the_ground", "hide_massing", "set_labels", "set_envelope", "zoom_to", "open_report",
        "save_facts", "_save_facts", "_save_ui_state", "_ui_state", "_set_source", "fact_sources"]


class Doc:
    """A model's file: its strings, objects and layers. Writing any of them with no undo record open is the bug."""

    RuntimeSerialNumber = 1

    def __init__(self):
        self.open, self.records, self.outside = [], [], []
        doc = self

        class Strings:
            data = {}

            def SetString(self, section, entry, value):
                doc.wrote("string " + entry)
                self.data[(section, entry)] = value

            def GetValue(self, section, entry):
                return self.data.get((section, entry))

        class Layer:
            _visible = True

            @property
            def IsVisible(self):
                return self._visible

            @IsVisible.setter
            def IsVisible(self, value):
                doc.wrote("layer visibility")
                self._visible = value

        class Layers:
            def FindByFullPath(self, path, default):
                return 0

            def __getitem__(self, i):
                return layer

        class Objects:
            def ModifyAttributes(self, o, attrs, quiet):
                doc.wrote("object attributes")

            def UnselectAll(self):
                pass                                          # selection: never an undo step in Rhino

        layer = Layer()
        self.Strings, self.Layers, self.Objects = Strings(), Layers(), Objects()
        self.Views = type("Views", (), {"Redraw": lambda s: None})()

    def wrote(self, what):
        if not self.open:
            self.outside.append(what)

    def BeginUndoRecord(self, words):
        self.open.append(words)
        self.records.append(words)
        return len(self.records)

    def EndUndoRecord(self, serial):
        assert self.open, "an undo record ended that was never begun"
        self.open.pop()
        return True


def _plugin(doc, said):
    attrs = type("Attrs", (), {"Duplicate": lambda s: type("A", (), {"LayerIndex": 0})()})
    obj = type("Obj", (), {"Attributes": attrs(), "Id": "b2"})
    ns = {"json": json, "os": __import__("os"), "logic": logic, "STATE": {}, "say": said.append,
          "SECTION": "Gordium", "ENTRY": "lot_facts", "UI_ENTRY": "ui", "SOURCES_ENTRY": "sources",
          "LAYERS": logic.LAYERS, "Cancelled": logic.Cancelled,
          "Rhino": type("Rhino", (), {"RhinoDoc": type("RD", (), {"ActiveDoc": doc}),
                                      "DocObjects": type("DO", (), {"ObjectType": type("OT", (), {"Curve": 4})})}),
          "ui": type("UI", (), {"legend": staticmethod(lambda code: None),
                                "open_target": staticmethod(lambda path: (True, None))}),
          "_box_open": lambda: False, "run_check": lambda doc, report=False: {"report_error": "not in a test"},
          "current_facts": lambda doc: {"lot_id": "lot1", "zone": "R-1b"},
          "_lot_candidates": lambda doc: [type("L", (), {"Id": "lot1"})(), type("L", (), {"Id": "lot2"})()],
          "_buildings": lambda doc: [obj(), obj()], "_pick": lambda doc, prompt, objs, kind, *a: "lot2"
          if kind == "Lot" else "b2", "_count": lambda prompt: 2, "_ask_yes_no_or_skip": lambda prompt: True,
          "_layer": lambda doc, name: 0, "_find": lambda doc, i: obj(), "report_path": lambda doc: "/nowhere.xlsx",
          "edit_facts": lambda: None, "set_grade": lambda: None, "hide_massing_tick": None}
    for name in REAL:
        exec(SRC[SRC.index("def %s(" % name):].split("\ndef ", 1)[0], ns)     # noqa: S102
    return ns


# what each panel action is given (the panel's own arguments), and whether it changes the file
CALLS = {"survey": ((), True), "enter": ((["stories"],), True), "main": ((), True), "add": ((["b2"],), True),
         "ground": ((["mesh"],), True), "not_ground": ((), True), "massing": ((True,), True), "labels": ((True,), True),
         "zoom": ((None,), False), "report": ((), False), "envelope": ((True,), False), "legend": ((), False),
         "retry": ((), False),
         # the start box (Edit site…, Set grade…): a transaction of its own, written only by its Draw
         "edit_site": ((), False), "grade": ((), False)}


def test_the_guard_covers_every_panel_action():
    """A new panel button is added here too, so it is held to one undo step."""
    assert sorted(_plugin(Doc(), [])["PANEL_ACTIONS"]()) == sorted(CALLS)


@pytest.mark.parametrize("name", sorted(CALLS))
def test_every_panel_change_is_exactly_one_named_undo_step(name):
    doc, said = Doc(), []
    args, changes = CALLS[name]
    _plugin(doc, said)["_actions"]()[name](*args)
    assert doc.outside == [], f"{name} wrote {doc.outside} outside any undo record (Ctrl+Z would skip it)"
    assert doc.open == []                                                   # every record it began, ended
    assert doc.records == ([logic.UNDO_WORDS[name]] if changes else []), doc.records


def test_a_refused_count_is_put_back_inside_the_same_one_step():
    """Enter …: a story count the measuring refuses is written, checked, then put back: still one step, so one
    Ctrl+Z never lands between the two writes."""
    doc, said = Doc(), []
    ns = _plugin(doc, said)

    def check(doc, report=False):
        ns["STATE"]["last"] = {"items": [{"refused": True, "reason": "x: does not comply under that reading. 1 story"}]}
    ns["run_check"] = check
    ns["_actions"]()["enter"](["stories"])
    assert doc.outside == [] and doc.records == [logic.UNDO_WORDS["enter"]] and said == ["1 story. The count wasn't kept."]


def test_an_undo_step_ends_when_the_change_fails_and_never_ends_rhinos_own():
    doc = Doc()
    with pytest.raises(ValueError):
        with logic.undo_step(doc, "Gordium: x"):
            raise ValueError
    assert doc.open == []
    inside_a_command = type("D", (), {"BeginUndoRecord": lambda s, w: 0,
                                      "EndUndoRecord": lambda s, n: pytest.fail("ended Rhino's own record")})()
    with logic.undo_step(inside_a_command, "Gordium: x"):
        pass
