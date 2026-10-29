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
        "edit_facts", "set_grade", "_drawn", "_begin_undo", "_end_undo", "_undo_redo", "_settings_from_file",
        "show_context", "_context_on", "check_now", "set_auto_check", "_auto", "_massing_hidden", "_sync_ticks",
        "switch_side_yards"]


class Doc:
    """A model's file: its strings, objects and layers. Writing any of them with no undo record open is the bug."""

    RuntimeSerialNumber = 1
    UndoRecordingEnabled = True
    ModelAbsoluteTolerance = 0.001

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
            IsDeleted = False                                 # (#35's hide_massing walks every Massing layer)
            FullPath = logic.MASSING

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

            def __iter__(self):
                return iter([layer])

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
          "live": lambda on: None,
          "ui": type("UI", (), {"legend": staticmethod(lambda code: None),
                                "set_auto_tick": staticmethod(lambda parts, on: None),
                                "show": staticmethod(lambda *a, **k: None),
                                "set_labels_tick": staticmethod(lambda parts, on: None),
                                "set_context_tick": staticmethod(lambda parts, on: None),
                                "set_massing_tick": staticmethod(lambda parts, on: None),
                                "set_envelope_tick": staticmethod(lambda parts, on: None),
                                "open_target": staticmethod(lambda path: (True, None))}),
          "_box_open": lambda: False, "run_check": lambda doc, report=False: {"report_error": "not in a test"},
          "current_facts": lambda doc: {"lot_id": "lot1", "zone": "R-1b"},
          "_lot_candidates": lambda doc: [type("L", (), {"Id": "lot1"})(), type("L", (), {"Id": "lot2"})()],
          "_buildings": lambda doc: [obj(), obj()], "_pick": lambda doc, prompt, objs, kind, *a: "lot2"
          if kind == "Lot" else "b2", "_count": lambda prompt, least=0: 2, "_ask_yes_no_or_skip": lambda prompt: True,
          "_layer": lambda doc, name: 0, "_find": lambda doc, i: obj(), "report_path": lambda doc: "/nowhere.xlsx",
          "time": __import__("time"), "_clear": lambda o: None, "JURISDICTION": "ithaca",
          "ask": lambda request: {"zones": []}, "suggested_facts": lambda doc, zones: {},
          "overlay": lambda: type("O", (), {})(), "_apply_box": lambda doc, facts, state, saved_ui: (facts, {}),
          # the start box: the architect presses Draw (the plugin's own _drawn), with the facts it was given
          "confirm": lambda doc, facts, options, mode="check": ns["_drawn"](doc, facts, {}, {}),
          # the context layers and a fetched neighbourhood, written as _context_visible and draw_context write them
          "_context_visible": lambda doc, on: setattr(doc.Layers[0], "IsVisible", on) or True,
          "_context_record": lambda doc: None, "sync_context": lambda doc, facts: None,
          "draw_context": lambda doc, frame, left=0: doc.Strings.SetString("Gordium", "context", "{}"),
          # (#34: the envelope's snap curves shown or hidden in every open document; nothing written in this one)
          "_envelope_everywhere": lambda: None,
          # Switch side yards (#35): no starting house here, so refused and nothing written; its own one Undo step is
          # pinned in test_side_yards. (#35's layer locks: each layer's own lock as it was)
          "_start_floors": lambda doc: [], "_feet_length": lambda doc, x: x,
          "_own_lock": lambda doc, layer: False, "_set_own_lock": lambda doc, layer, own: None}
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
         "context": ((True,), True),
         # Check (#27): a check, nothing written; Check after every edit: the setting saved in the file
         "check": ((), False), "auto_check": ((False,), True),
         # Switch side yards (#35): refused with no starting house (its real step: test_side_yards)
         "switch_sides": ((), False)}


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
    ns["_count"] = lambda prompt, least=0: 4                                      # a count it keeps: one step, one check
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
    done += SRC[SRC.index("def _show_answer("):].split("\ndef ", 1)[0]    # (its answer shown: the start flow)
    assert "_show_answer(doc, answer, facts, saved_ui)" in done
    # (#26: the lookup only previews, the model changed at Draw, inside the box's step; never a table of its own)
    assert ("apply_lookup(session.table," in done or "preview_lookup(" in done) and "RhinoTable(doc)" not in done


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


def test_a_new_addresss_reset_goes_in_the_boxs_own_step():
    """#26 with #19's one step per box: a reset to a new address began a record of its own, ending the box's step
    (Draw my lot or spot grades placed before it): two steps for one box. It begins one only if none is held."""
    prepare = SRC[SRC.index("def _draw_prepare("):].split("\ndef ", 1)[0]
    assert '    if not STATE.get("undo"):' in prepare and prepare.index('if not STATE.get("undo")') < prepare.index(
        '_begin_undo(doc, "Gordium: start fresh for "')


def test_an_undone_check_after_every_edit_is_read_again_from_the_file():
    """Carry review C1: Ctrl+Z on "Gordium: check after every edit" put the file's setting back, but the plugin kept
    its own copy (auto_by_doc): checks after edits (or none) as the undone setting said, the tick too, until the file
    was reopened. After Undo/Redo the setting is read again from the file, and the tick follows it."""
    doc = Doc()
    ns = _plugin(doc, [])
    ticks = []
    ns["ui"].set_auto_tick = staticmethod(lambda parts, on: ticks.append(on))
    ns["_actions"]()["auto_check"](False)
    assert ns["_auto"](doc) is False
    doc.Strings.data[("Gordium", "ui")] = json.dumps({"auto_check": True})     # what Rhino's Undo put back
    ns["_undo_redo"](None, type("E", (), {"IsEndUndo": True, "IsEndRedo": False})())
    assert ns["_auto"](doc) is True and ticks[-1] is True


def test_an_undone_setting_is_read_again_from_the_file():
    """Round 5, R5-1: Ctrl+Z on Show on-screen labels put the file's setting back but the plugin kept its own copy
    (labels_by_doc) and the tick, until the next check. After Undo/Redo both follow the file."""
    doc = Doc()
    ns = _plugin(doc, [])
    ticks = []
    ns["ui"].set_labels_tick = staticmethod(lambda parts, on: ticks.append(on))
    ns["_actions"]()["labels"](True)
    assert ns["STATE"]["labels_by_doc"][1] is True
    doc.Strings.data[("Gordium", "ui")] = json.dumps({"show_labels": False})     # what Rhino's Undo put back
    ns["_undo_redo"](None, type("E", (), {"IsEndUndo": True, "IsEndRedo": False})())
    assert ns["STATE"]["labels_by_doc"][1] is False and ticks[-1] is False


def test_an_undone_show_neighbourhood_is_read_again_from_the_file():
    """Round 5, R5-1 (#23's part): Ctrl+Z on "Gordium: show or hide the neighbourhood" put the file's setting back,
    but the plugin kept its own copy (context_by_doc: the live footprints drawn by it) and the tick, until the next
    check. After Undo/Redo both follow the file."""
    doc = Doc()
    ns = _plugin(doc, [])
    ticks = []
    ns["ui"].set_context_tick = staticmethod(lambda parts, on: ticks.append(on))
    ns["_actions"]()["context"](False)
    assert ns["STATE"]["context_by_doc"][1] is False
    doc.Strings.data[("Gordium", "ui")] = json.dumps({"show_context": True})     # what Rhino's Undo put back
    ns["_undo_redo"](None, type("E", (), {"IsEndUndo": True, "IsEndRedo": False})())
    assert ns["STATE"]["context_by_doc"][1] is True and ticks[-1] is True


def test_every_panel_tick_is_read_again_after_undo():
    """The Rhino job's real-input run at 540f718: Cmd+Z of Hide starting house put the layer back, the tick stayed
    ticked. After Undo/Redo every tick box the panel has (but the session-only envelope, never in the file) is set
    again from the document: by source, each set_*_tick is called by _settings_from_file; by behaviour, the massing
    tick follows its layer."""
    import re
    ui_src = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    ticks = set(re.findall(r"\ndef set_(\w+)_tick\(parts, ", ui_src))
    settings = SRC[SRC.index("def _settings_from_file("):].split("\ndef ", 1)[0]
    sync = SRC[SRC.index("def _sync_ticks("):].split("\ndef ", 1)[0]
    assert "_sync_ticks(doc)" in settings and "massing" in ticks
    assert all("ui.set_%s_tick(" % t in sync for t in ticks), (ticks, sync)
    doc = Doc()
    ns = _plugin(doc, [])
    ticks_set = []
    ns["ui"].set_massing_tick = staticmethod(lambda parts, hidden: ticks_set.append(hidden))
    ns["_actions"]()["massing"](True)
    assert doc.Layers[0].IsVisible is False
    doc.Layers[0]._visible = True                                     # what Rhino's Undo put back
    ns["_undo_redo"](None, type("E", (), {"IsEndUndo": True, "IsEndRedo": False})())
    assert ticks_set[-1] is False
