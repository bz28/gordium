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
        "save_facts", "_save_facts", "_save_ui_state", "_ui_state", "_set_source", "fact_sources", "_tried", "_put_back",
        "edit_facts", "set_grade", "_drawn", "_begin_undo", "_end_undo", "_undo_redo", "show_context"]


class Doc:
    """A model's file: its strings, objects and layers. Writing any of them with no undo record open is the bug."""

    RuntimeSerialNumber = 1
    UndoRecordingEnabled = True

    def __init__(self):
        self.open, self.records, self.outside, self.unrecorded = [], [], [], []
        doc = self

        class Strings:
            data = {}

            def SetString(self, section, entry, value):
                doc.wrote("string " + entry)
                self.data[(section, entry)] = value

            def GetValue(self, section, entry):
                return self.data.get((section, entry))

            def Delete(self, section, entry):
                doc.wrote("string " + entry)
                self.data.pop((section, entry), None)

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

            def Delete(self, o, quiet):
                doc.wrote("object deleted")

            def AddCurve(self, curve, attrs):
                doc.wrote("curve added")
                return "curve"

            def AddPoint(self, point, attrs):
                doc.wrote("point added")
                return "point"

            def UnselectAll(self):
                pass                                          # selection: never an undo step in Rhino

        layer = Layer()
        self.Strings, self.Layers, self.Objects = Strings(), Layers(), Objects()
        self.Views = type("Views", (), {"Redraw": lambda s: None})()

    def wrote(self, what):
        if not self.UndoRecordingEnabled:
            self.unrecorded.append(what)          # undo off: allowed only when it leaves the file as it was
        elif not self.open:
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
          "time": __import__("time"), "_clear": lambda o: None, "JURISDICTION": "ithaca",
          "ask": lambda request: {"zones": []}, "suggested_facts": lambda doc, zones: {},
          "overlay": lambda: type("O", (), {})(), "_apply_box": lambda doc, facts, state, saved_ui: (facts, {}),
          # the start box: the architect presses Draw (the plugin's own _drawn), with the facts it was given
          "confirm": lambda doc, facts, options, mode="check": ns["_drawn"](doc, facts, {}, {}),
          # the context layers and a fetched neighbourhood, written as _context_visible and draw_context write them
          "_context_visible": lambda doc, on: setattr(doc.Layers[0], "IsVisible", on) or True,
          "_context_record": lambda doc: None, "sync_context": lambda doc, facts: None,
          "draw_context": lambda doc, frame, left=0: doc.Strings.SetString("Gordium", "context", "{}")}
    for name in REAL:
        exec(SRC[SRC.index("def %s(" % name):].split("\ndef ", 1)[0], ns)     # noqa: S102
    exec(SRC[SRC.index("class RhinoTable:"):].split("\ndef ", 1)[0], ns)      # noqa: S102
    return ns


# what each panel action is given (the panel's own arguments), and whether it changes the file
CALLS = {"survey": ((), True), "enter": ((["sleeping_rooms"],), True), "main": ((), True), "add": ((["b2"],), True),
         "ground": ((["mesh"],), True), "not_ground": ((), True), "massing": ((True,), True), "labels": ((True,), True),
         "zoom": ((None,), False), "report": ((), False), "envelope": ((True,), False), "legend": ((), False),
         "retry": ((), False),
         # the start box (Edit site…, Set grade…): its Draw and the facts saved after it closes, one step
         "edit_site": ((), True), "grade": ((), True),
         # Show neighbourhood (#23): the tick saved, the context layers shown, a neighbourhood fetched and drawn
         "context": ((True,), True)}


def test_the_guard_covers_every_panel_action():
    """A new panel button is added here too, so it is held to one undo step."""
    assert sorted(_plugin(Doc(), [])["PANEL_ACTIONS"]()) == sorted(CALLS)


@pytest.mark.parametrize("name", sorted(CALLS))
def test_every_panel_change_is_exactly_one_named_undo_step(name):
    doc, said = Doc(), []
    args, changes = CALLS[name]
    _plugin(doc, said)["_actions"]()[name](*args)
    assert doc.outside == [], f"{name} wrote {doc.outside} outside any undo record (Ctrl+Z would skip it)"
    assert doc.open == [] and doc.unrecorded == []                          # every record it began, ended
    assert doc.records == ([logic.UNDO_WORDS[name]] if changes else []), doc.records


def test_a_refused_count_leaves_the_file_as_it_was_and_no_undo_step():
    """Enter …: a story count the measuring refuses is tried with undo recording off, then the facts put back exactly
    as stored: no step that does nothing (one Ctrl+Z would seem to do nothing), the file unchanged, checked again."""
    doc, said = Doc(), []
    ns = _plugin(doc, said)
    doc.Strings.data[("Gordium", "lot_facts")] = stored = json.dumps({"lot_id": "lot1", "stories": 3})
    checks = []

    def check(doc, report=False):
        facts = json.loads(doc.Strings.GetValue("Gordium", "lot_facts"))
        checks.append(facts.get("stories"))
        refused = facts.get("stories") == 2
        ns["STATE"]["last"] = {"items": [{"refused": refused, "reason": "x: does not comply under that reading. "
                                                                        "1 story"}]}
    ns["run_check"] = check
    ns["_actions"]()["enter"](["stories"])
    assert doc.records == [] and doc.outside == [] and doc.UndoRecordingEnabled
    assert doc.Strings.data[("Gordium", "lot_facts")] == stored and checks == [2, 3]
    assert said == ["1 story. The count wasn't kept."]
    ns["_count"] = lambda prompt: 4                                       # a count it keeps: one step, one check
    checks.clear()
    ns["_actions"]()["enter"](["stories"])
    assert doc.records == [logic.UNDO_WORDS["enter"]] and doc.outside == [] and checks == [4]
    assert json.loads(doc.Strings.data[("Gordium", "lot_facts")])["stories"] == 4


def test_the_start_box_is_one_step_from_its_first_edit_to_the_facts_saved():
    """Undo steps round 2, F1: what the box draws before Draw (the City's lot, spot grades, the old lot held) was
    written with no undo record, so one Ctrl+Z after Draw left the looked-up lot in the model with the old facts.
    The box's own model edits begin its one step; Draw and the facts saved after it close are in it."""
    doc = Doc()
    ns = _plugin(doc, [])

    def box(doc, facts, options, mode="check"):
        ns["RhinoTable"](doc, logic.UNDO_WORDS["edit_site"]).delete("the old lot")   # an edit while the box is open
        return ns["_drawn"](doc, facts, {}, {})
    ns["confirm"] = box
    ns["_actions"]()["edit_site"]()
    assert doc.outside == [] and doc.open == [] and doc.records == [logic.UNDO_WORDS["edit_site"]]
    ns["RhinoTable"](doc).delete("x")                          # recovery's own table: never begins the box's step
    assert doc.records == [logic.UNDO_WORDS["edit_site"]] and "undo" not in ns["STATE"]


def test_the_boxs_own_drawing_is_in_its_step_from_the_first_line():
    """Undo steps round 3, U5: Draw my lot, spot grades and a lookup with nothing to hold wrote the model before the
    box's step began (it began only at the session's mark): the lot drawn, or the points, left by one Ctrl+Z."""
    doc = Doc()
    ns = _plugin(doc, [])
    clicks = [(1, "p1"), (1, "p2"), (1, "p3"), (0, None)]
    result = type("Result", (), {"Success": 1, "Cancel": 2})
    ns["Rhino"].Input = type("Input", (), {"RhinoGet": type("G", (), {"GetPoint": staticmethod(
        lambda prompt, ok: clicks.pop(0))})})
    ns["Rhino"].Commands = type("Commands", (), {"Result": result})
    ns["Rhino"].DocObjects.ObjectAttributes = lambda: type("A", (), {})()
    ns.update(rg=type("rg", (), {"PolylineCurve": lambda pts: pts}), GRADE_LAYER="Gordium::Grade")
    for name in ("_draw_lot", "_place_spots"):
        exec(SRC[SRC.index("def %s(" % name):].split("\ndef ", 1)[0], ns)     # noqa: S102
    table = ns["RhinoTable"](doc, logic.UNDO_WORDS["edit_site"])
    ns["_draw_lot"](doc, table._changing)
    clicks[:] = [(1, "q"), (0, None)]
    ns["_place_spots"](doc, "spot", "Gordium::Grade", table._changing)
    assert doc.outside == [] and doc.records == [logic.UNDO_WORDS["edit_site"]]
    pick = SRC[SRC.index("def _pick_outcome("):].split("\ndef ", 1)[0]
    assert "_draw_lot(doc, session.table._changing)" in pick and "session.table._changing)" in pick.split(
        "_place_spots(", 1)[1]
    done = SRC[SRC.index("def _lookup_done("):].split("\ndef ", 1)[0]
    assert "apply_lookup(session.table," in done and "RhinoTable(doc)" not in done


def test_a_tried_count_leaves_undo_recording_as_it_was():
    """Undo steps round 2, F3: recording off before (by someone else) stays off."""
    doc = Doc()
    ns = _plugin(doc, [])
    doc.UndoRecordingEnabled = False
    ns["_tried"](doc, {"stories": 2})
    assert doc.UndoRecordingEnabled is False


def test_a_start_box_closed_without_draw_makes_no_step_and_holds_none():
    doc = Doc()
    ns = _plugin(doc, [])
    ns["confirm"] = lambda doc, facts, options, mode="check": None
    ns["_actions"]()["edit_site"]()
    assert doc.records == [] and doc.outside == [] and "undo" not in ns["STATE"]


def test_an_undone_panel_change_is_checked_again():
    """A panel change undone puts back only the file's strings (no object event notices it): Rhino's Undo or Redo,
    finished, marks the model changed now, so live mode checks it again; never on a record merely begun."""
    ns = _plugin(Doc(), [])
    event = type("E", (), {"IsEndUndo": False, "IsEndRedo": False})
    ns["_undo_redo"](None, event())
    assert "dirty" not in ns["STATE"]
    event.IsEndUndo = True
    ns["_undo_redo"](None, event())
    assert ns["STATE"]["dirty"] > 0
    assert '_on(Rhino.Commands.Command, "UndoRedo", _handler(' in SRC          # hooked for every document


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


def test_the_plugin_still_compiles():
    """Undo steps round 4: a re-indented try left gordium_rhino.py unloadable, unseen by the guard (it runs functions
    cut from the source). The whole file must compile."""
    compile(SRC, "gordium_rhino.py", "exec")
