"""A row's own dialog (coordinator, 2026-10-28, agreed with Ben): a needs-review row waiting on stated facts asks
exactly those in a small modal dialog, never the whole start box. OK saves only those facts, each "entered by you"
with the day, as one Undo step, and checks again; Cancel, Esc or closing it changes nothing and makes no Undo step.
A blank stays unset (needs review, never 0 or no). An answer given here shows in the start box and is kept by its
next Draw for the same district and use. A row missing a site fact keeps Edit site…."""

import json
import random

import pytest

from design_checker import rhino_logic as logic
from rule_format.rulebook import REPO

RHINO = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
UI = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
STATED = list(logic.STATED_FACTS)
# an R-3a-like district (test_use_questions.X): a multiple dwelling's lot size reads its units, rooms let and conversion
OPTS = {"follow_ups": {"X": {"multiple_family": ["dwelling_units", "rooms_let_for_profit", "conversion"],
                             "two_family": ["rooms_let_for_profit", "conversion"]}},
        "implied": {"X": {"two_family": {"dwelling_units": 2}}}}
# what a saved project holds besides the stated facts: none of it may change in a row's dialog
SITE = {"jurisdiction": "new_york/ithaca_city", "address": "106 Ithaca Rd", "zone": "X", "use": "multiple_family",
        "lot_id": "4b1c-lot", "lot_surveyed": False, "street_line": [[[0, 0], [50, 0]]], "corner_lot": False,
        "main_building": "9f-bldg", "grade_from": "spot", "unsettled": {"lot": "approximate"},
        "street_name": "Ithaca Rd"}


def _value(kind, rng):
    """An answer as the dialog gives it, and what it means: (text, value, bad)."""
    if kind == "yes_no":
        return rng.choice([("", None, False), ("yes", True, False), ("no", False, False)])
    return rng.choice([("", None, False), ("0", 0, False), ("3", 3, False), (" 12 ", 12, False),
                       ("-1", None, True), ("2.5", None, True), ("lots", None, True)])


def test_only_the_rows_facts_change_whatever_is_saved_and_answered():
    """Property: over many saved projects and answers, every key outside the row's `needs` (the address, district,
    use, lot, street, the start box's own facts) is identical after OK; each key in `needs` is its answer, a blank
    leaves it unset (never 0 or no), and any bad entry raises with words and changes nothing at all."""
    rng = random.Random(20261028)
    for _ in range(2000):
        facts = {k: v for k, v in SITE.items() if rng.random() < 0.8}
        for k in STATED:
            if rng.random() < 0.4:
                facts[k] = rng.choice([True, False]) if logic.STATED_FACTS[k][1] == "yes_no" else rng.randint(0, 9)
        needs = rng.sample(STATED, rng.randint(1, len(STATED)))
        given = {k: _value(logic.STATED_FACTS[k][1], rng) for k in needs}
        answers = {k: t for k, (t, _, _) in given.items() if rng.random() < 0.95}   # one missing: blank
        before = json.loads(json.dumps(facts))
        if any(given[k][2] for k in answers):
            with pytest.raises(ValueError) as e:
                logic.row_answers_applied(facts, needs, answers)
            assert str(e.value).startswith("Not saved. ")
            assert facts == before                                   # nothing changed, not even in place
            continue
        out = logic.row_answers_applied(facts, needs, answers)
        assert facts == before
        assert {k: v for k, v in out.items() if k not in needs} == {k: v for k, v in before.items() if k not in needs}
        for k in needs:
            want = given[k][1] if k in answers else None
            if want is None:
                assert k not in out                                  # unset: its rules need review
            else:
                assert out[k] == want and type(out[k]) is type(want)


def test_a_blank_stays_unset_and_a_bad_entry_says_why():
    facts = dict(SITE, dwelling_units=4)
    out = logic.row_answers_applied(facts, ["dwelling_units", "conversion"], {"dwelling_units": "", "conversion": ""})
    assert "dwelling_units" not in out and "conversion" not in out       # never 0, never "new construction"
    with pytest.raises(ValueError) as e:
        logic.row_answers_applied(facts, ["sleeping_rooms", "parking_spaces"],
                                  {"sleeping_rooms": "three", "parking_spaces": "2"})
    assert str(e.value) == ("Not saved. Bedrooms: a whole number, 0 or more. Correct it, or leave it blank (it then "
                            "needs review).")
    assert logic.row_answers_applied({}, ["conversion"], {"conversion": logic.row_choice_text(1)}) == {
        "conversion": False}
    assert logic.row_choice_text(0) == "" and logic.row_choice_text(2) == "yes"
    assert [logic.row_choice(v) for v in (None, False, True)] == [0, 1, 2]


def test_the_dialog_asks_exactly_the_rows_facts():
    fields = logic.row_fields(["sleeping_rooms", "conversion"], {"sleeping_rooms": 3, "zone": "X"})
    assert fields == [{"key": "sleeping_rooms", "label": "Bedrooms", "kind": "count", "value": 3},
                      {"key": "conversion", "label": logic.STATED_FACTS["conversion"][0], "kind": "yes_no",
                       "value": None}]
    assert logic.row_fields(["zone", "address", "lot_id"], SITE) == []       # never a site fact


def test_each_answer_is_entered_by_you_with_the_day_and_no_other_source_changes():
    sources = {"zone": {"value": "X", "source": "the City map", "confirmed_by": "you", "date": "2026-10-01"},
               "ground_marked": {"value": "1 object"}, "dwelling_units": {"value": 9, "source": "old"}}
    new = logic.row_answers_applied(SITE, ["dwelling_units", "conversion"], {"dwelling_units": "", "conversion": "no"})
    out = logic.row_sources(sources, ["dwelling_units", "conversion"], new, "2026-10-28")
    assert out == {"zone": sources["zone"], "ground_marked": sources["ground_marked"],
                   "conversion": {"value": "no", "source": logic.ENTERED, "confirmed_by": "you",
                                  "date": "2026-10-28"}}            # the blank's old source gone with its fact


def test_an_answer_from_the_dialog_shows_in_the_start_box_and_draw_keeps_it():
    """The box keeps no copy of the answers: it reads them from the saved facts (box_answers, used by _box_state),
    so the dialog's answer is the box's answer, and Draw for the same district and use sets it again with its source
    "entered by you" (never dropped or overwritten)."""
    facts = dict(SITE, dwelling_units=None)
    facts.pop("dwelling_units")
    new = logic.row_answers_applied(facts, ["dwelling_units", "conversion"], {"dwelling_units": "5", "conversion": "yes"})
    shown = logic.box_answers(OPTS, "X", "multiple_family", new)
    assert shown == {"dwelling_units": 5, "rooms_let_for_profit": None, "conversion": True}
    rows = logic.follow_up_rows(OPTS, "X", "multiple_family", new)
    assert {r["key"]: r["value"] for r in rows} == shown
    drawn, answered = logic.answers_applied(new, shown, "X", "multiple_family", OPTS)    # Edit site… → Check / Draw
    assert drawn["dwelling_units"] == 5 and drawn["conversion"] is True and answered == ["conversion", "dwelling_units"]
    assert {k: v for k, v in drawn.items() if k not in logic.BOX_ASKS} == {
        k: v for k, v in new.items() if k not in logic.BOX_ASKS}
    sources = logic.fact_sources({"zone": "X", "use": "multiple_family", "options": OPTS, "answers": shown},
                                 "2026-10-29", True)
    assert sources["dwelling_units"]["value"] == 5 and sources["dwelling_units"]["source"] == logic.ENTERED
    # the interior's (bedrooms, parking) and the stories, never asked in the box: kept by Draw as given
    inside = logic.row_answers_applied(new, ["sleeping_rooms", "parking_spaces", "stories"],
                                       {"sleeping_rooms": "3", "parking_spaces": "2", "stories": "2"})
    kept, _ = logic.answers_applied(inside, logic.box_answers(OPTS, "X", "multiple_family", inside), "X",
                                    "multiple_family", OPTS)
    assert (kept["sleeping_rooms"], kept["parking_spaces"], kept["stories"]) == (3, 2, 2)
    state = RHINO[RHINO.index("def _box_state("):RHINO.index("def _ft_text(")]
    assert '"answers": logic.box_answers(options, facts.get("zone"), facts.get("use"), facts)' in state
    assert "saved_ui" not in RHINO[RHINO.index("def enter_rooms("):RHINO.index("def pick_main_building(")]


def test_a_row_missing_a_site_fact_keeps_edit_site():
    assert logic.row_buttons({"hint": "Edit site…", "needs": []}) == [("Edit site…", "edit_site")]
    assert logic.row_buttons({"reason": "the yards are open questions; answer Corner lot?"}) == [
        ("Edit site…", "edit_site")]
    assert logic.row_buttons({"hint": "Edit site…", "needs": ["dwelling_units"]}) == [
        ("Enter dwelling units…", "enter"), ("Edit site…", "edit_site")]     # the dialog first, Edit site… second
    assert logic.row_buttons({"needs": ["stories"], "reason": "enter the number of stories"}) == [
        ("Enter the number of stories…", "enter")]
    assert logic.hint_text("Edit site…", ["Edit site…"]) is None            # its words never said twice


# ---- the plugin's wiring, run headless: enter_rooms and _save_row with a stand-in document and dialog -----------

class _Strings:
    def __init__(self, doc, values):
        self.doc, self.values = doc, dict(values)

    def GetValue(self, section, key):
        return self.values.get(key)

    def SetString(self, section, key, value):
        self.doc.log.append(("set", key, self.doc.recording))
        self.values[key] = value


class _Doc:
    def __init__(self, facts, sources):
        self.log, self.recording, self.records = [], False, 0
        self.Strings = _Strings(self, {"lot_facts": json.dumps(facts), "fact_sources": json.dumps(sources)})

    def BeginUndoRecord(self, name):
        assert not self.recording
        self.recording, self.records = True, self.records + 1
        self.log.append(("begin", name, True))
        return 7

    def EndUndoRecord(self, record):
        assert self.recording and record == 7
        self.recording = False
        self.log.append(("end", None, False))

    def facts(self):
        return json.loads(self.Strings.values["lot_facts"])

    def sources(self):
        return json.loads(self.Strings.values["fact_sources"])


def _plugin(doc, dialog, refused=None):
    """enter_rooms and its helpers from gordium_rhino.py, with a stand-in document, dialog and check."""
    ns = {"logic": logic, "json": json, "STATE": {}, "SECTION": "Gordium", "ENTRY": "lot_facts",
          "SOURCES_ENTRY": "fact_sources", "said": [], "checks": [], "_box_open": lambda: False}
    ns["say"] = ns["said"].append
    ns["Rhino"] = type("Rhino", (), {"RhinoDoc": type("RhinoDoc", (), {"ActiveDoc": doc})})
    ns["load_facts"] = lambda d: d.facts()
    ns["ui"] = type("ui", (), {"row_dialog": staticmethod(dialog)})

    def run_check(d, report=True):
        ns["checks"].append(d.facts())
        ns["STATE"]["last"] = {"items": [{"refused": "x", "reason": refused}] if refused and d.facts().get(
            "stories") else []}

    ns["run_check"] = run_check
    for name in ("enter_rooms", "_save_row", "_save_facts", "fact_sources"):
        exec(RHINO[RHINO.index("def %s(" % name):].split("\ndef ", 1)[0], ns)      # noqa: S102
    return ns


SOURCES = {"zone": {"value": "X", "source": "entered by you", "confirmed_by": "you", "date": "2026-10-01"}}


def test_cancel_changes_nothing_and_makes_no_undo_step():
    doc = _Doc(dict(SITE), SOURCES)
    asked = []
    ns = _plugin(doc, lambda title, fields, check: asked.append((title, fields)) or None)   # Cancel / Esc / closed
    ns["enter_rooms"](["dwelling_units", "conversion"])
    assert asked[0][0] == "Enter dwelling units and whether it is a conversion"
    assert [f["key"] for f in asked[0][1]] == ["dwelling_units", "conversion"]
    assert doc.log == [] and doc.records == 0                          # nothing written, no Undo record
    assert doc.facts() == SITE and doc.sources() == SOURCES and ns["checks"] == []
    assert ns["said"] == ["Cancelled: nothing changed."]


def test_ok_saves_exactly_the_rows_facts_as_one_undo_step_then_checks():
    doc = _Doc(dict(SITE), SOURCES)
    seen = {}

    def dialog(title, fields, check):
        seen["bad"] = check({"dwelling_units": "five", "conversion": "no"})   # a bad entry: words, dialog stays open
        return {"dwelling_units": "5", "conversion": "no"}

    ns = _plugin(doc, dialog)
    ns["enter_rooms"](["dwelling_units", "conversion"])
    assert seen["bad"].startswith("Not saved. Dwelling units: a whole number")
    assert doc.records == 1
    assert [e[0] for e in doc.log] == ["begin", "set", "set", "end"]
    assert all(rec for kind, _, rec in doc.log if kind == "set")          # every write inside the one record
    assert doc.facts() == dict(SITE, dwelling_units=5, conversion=False)
    assert doc.sources()["conversion"]["source"] == logic.ENTERED and doc.sources()["zone"] == SOURCES["zone"]
    assert ns["checks"] == [doc.facts()]                                   # checked again, once, after the save


def test_a_refused_count_of_stories_saves_nothing():
    """Fewer stories than the floors drawn: the measuring refuses the count (its words said); the facts and sources
    are as before and no Undo step is made. Accepted, it is saved as one Undo step."""
    doc = _Doc(dict(SITE), SOURCES)
    ns = _plugin(doc, lambda title, fields, check: {"stories": "1"},
                 refused="Stories: 1 entered, 2 floors drawn: does not comply under that reading. 1 is fewer than "
                         "the 2 floors drawn.")
    ns["enter_rooms"](["stories"])
    assert doc.facts() == SITE and doc.sources() == SOURCES and doc.records == 0
    assert ns["said"] == ["1 is fewer than the 2 floors drawn. The count wasn't kept."]
    doc = _Doc(dict(SITE), SOURCES)
    ns = _plugin(doc, lambda title, fields, check: {"stories": "3"})
    ns["enter_rooms"](["stories"])
    assert doc.facts() == dict(SITE, stories=3) and doc.records == 1


def test_the_panel_row_wiring():
    detail = UI[UI.index("def show_detail("):UI.index("def row_dialog(")]
    assert "logic.row_buttons(i)" in detail and "Tell Gordium" not in UI
    dialog = UI[UI.index("def row_dialog("):UI.index("def text_box_size(")]
    # Cancel and Esc (AbortButton) close without answers; only OK, once check says nothing, sets them
    assert 'cancel = button("Cancel", lambda: dialog.Close(False))' in dialog and "dialog.AbortButton = cancel" in dialog
    assert dialog.index("problem = check(got)") < dialog.index('chosen["answers"] = got')
    assert 'return chosen.get("answers")' in dialog
    assert '"enter": enter_rooms' in RHINO


def test_ok_with_nothing_new_makes_no_undo_step():
    doc = _Doc(dict(SITE, dwelling_units=4), SOURCES)
    ns = _plugin(doc, lambda title, fields, check: {"dwelling_units": "4"})
    ns["enter_rooms"](["dwelling_units"])
    assert doc.log == [] and doc.records == 0 and ns["said"] == ["Nothing new entered: nothing changed."]
