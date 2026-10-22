"""Re-lookup on a drawn site (Ben, 2026-10-21), as scenarios: Look up previews (the model untouched), Draw with a
new address starts clean, the architect's own work is never removed without asking once, the same address draws
nothing new, and Cancel (or Esc) at any point leaves the model and the file exactly as they were.

The harness (`Site`, `Box`) does what the plugin's Edit site… does (gordium_rhino._box_loop, _draw_prepare,
edit_facts), step for step, through the same rhino_logic calls: preview_lookup, draw_decision, reset_question,
apply_reset, pick_effect, the box session's commit and rollback, storable_ui. What only Rhino shows (the dashed
preview drawn, the question's dialog, one undo step) is in apps/rhino_plugin/tests/re_lookup_in_rhino.py.

The last test runs every start (whose lot, whose house, buildings or not) against every lookup and every answer,
and holds the promises for all of them."""
import itertools
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_lookup_box import ZONES, FakeTable, looked_up  # noqa: E402

from design_checker import rhino_logic as logic  # noqa: E402
from design_checker.lookup_box import frame, writes  # noqa: E402

SAMPLE = "106 Ithaca Rd, Ithaca, NY"


def answer(name):
    return looked_up(name)


def guide_only(name):
    """The State's parcels didn't answer: the City's outline is a guide only (no lot curve may be written)."""
    p = looked_up(name)
    p["details"]["lot"]["source_keys"] = ["city_parcels"]
    p["writes"] = writes({"facts": p["facts"], "details": p["details"]}, frame({"facts": p["facts"]}))
    return p


class Site:
    """A Rhino file as Gordium left it: the model (FakeTable), the facts and the box's choices saved in the file, and
    the site facts' sources saved at the last Draw."""

    def __init__(self, lot="sample", house="gordium", buildings=False, drawn=SAMPLE, surveyed=False,
                 building_layer="Building", building_type="Brep"):
        objects = {"lot1": {"layer": "Site", "kind": "lot", "area": 6570.0}}
        if house:
            objects.update({"floor1": {"layer": logic.MASSING, "kind": "brep", "geom": "f1"},
                            "floor2": {"layer": logic.MASSING, "kind": "brep", "geom": "f2"}})
        if buildings:
            objects["garage"] = {"layer": building_layer, "kind": "brep", "type": building_type}
        self.table = FakeTable(objects)
        self.facts = {"lot_id": "lot1", "address": drawn, "zone": "R-1b", "use": "one_family",
                      "lot_surveyed": surveyed, "corner_lot": False, "street_line": [[[0, 0], [60, 0]]]}
        self.saved = {"replaceable_lot": "lot1" if lot == "sample" else None, "from_sample": lot == "sample",
                      "zone_source": "entered by you", "lot_source": "your survey" if surveyed else None}
        if drawn is not None:
            self.saved["drawn_address"] = drawn
        if house == "gordium":                    # as Gordium drew it, its fingerprint saved
            self.saved["house_fingerprint"] = self.table.fingerprint(["floor1", "floor2"])
        elif house == "edited":                   # drawn by Gordium, then moved by the architect
            self.saved["house_fingerprint"] = self.table.fingerprint(["floor1", "floor2"])
            self.table.objects["floor2"]["geom"] = "f2 moved"
        # house == "no record": a starting house with no fingerprint saved (a file from before re-lookup)
        self.sources = {}
        self.mine = self._architects()

    def _architects(self):
        """The ids of what is the architect's own at the start (never to go without their yes)."""
        out = set()
        if self.saved.get("replaceable_lot") != self.facts["lot_id"]:
            out.add(self.facts["lot_id"])
        house = self.table.massing()
        if house and self.table.fingerprint(house) != self.saved.get("house_fingerprint"):
            out |= set(house)
        out |= set(self.table.buildings())
        return out

    def state(self):
        return self.table.snapshot(), dict(self.facts), logic.storable_ui(self.saved)

    def box(self):
        return Box(self)


class Box:
    """Edit site…: one box session over the site (its model edits held until Draw or Cancel). Like the plugin's box,
    it has widgets (`typed`: what the architect typed or ticked since the box last showed the facts) over the
    state it builds from the facts (gordium_rhino._box_state), and every Draw goes through what _draw_prepare and
    _drawn do: the box's answers into the facts first, the pending preview settled, the decision, the reset, the
    state rebuilt from the new lot, then the facts and their sources saved from that state."""

    def __init__(self, site):
        self.site, self.table = site, site.table
        self.facts, self.saved = dict(site.facts), dict(site.saved)
        self.session = logic.BoxSession(self.table)
        self.asked, self.preview, self.said, self.open, self.typed = [], None, [], True, {}

    def shown(self):
        """The box's state as gordium_rhino._box_state builds it (the parts these scenarios read), the architect's
        typing and ticks over it."""
        f, sv = self.facts, self.saved
        lot = f.get("lot_id")
        here = bool(lot) and self.table.exists(lot) and self.table.objects[lot]["layer"] == "Site"
        state = {"address": f.get("address") or "", "zone": f.get("zone"), "use": f.get("use"),
                 "district_confirmed": True, "lot_surveyed": bool(f.get("lot_surveyed")),
                 "corner_lot": f.get("corner_lot"), "has_lot": here, "lot_missing": not here,
                 "lot_area": self.table.objects[lot].get("area") if here else None,
                 "lot_source": sv.get("lot_source"), "street_name": sv.get("_street_name") or sv.get("street_name"),
                 "street_source": sv.get("street_source"), "corner_source": sv.get("corner_source"),
                 "zone_source": sv.get("zone_source"), "address_source": sv.get("address_source"),
                 "use_source": sv.get("use_source"),
                 "lookup": sv.get("_lookup") or {}, "live": sv.get("_live") or {}, "doubts": sv.get("doubts") or {},
                 "checked": sv.get("checked") or []}
        return dict(state, **self.typed)

    def _apply(self, state=None):                  # gordium_rhino._apply_box: the box's answers into the facts
        state = state or self.shown()
        self.facts, self.saved = logic.box_facts(self.facts, self.saved, state)
        self.saved = logic.saved_sources(self.saved, state)
        self.typed = {}

    def look_up(self, payload):
        self.typed["address"] = payload.get("query") or self.facts.get("address")    # typed, then Look up
        self._apply()
        self.facts, self.saved, self.preview = logic.preview_lookup(payload, self.facts, self.saved, ZONES)
        return self

    def type_address(self, address):
        self.typed["address"] = address
        return self

    def button(self):
        return logic.draw_button("check", self.saved)

    def rows(self):
        state = self.shown()
        return {r["key"]: r for r in logic.box_rows(state)}, state

    def draw(self, reply=None):
        """Draw (gordium_rhino._draw_prepare then _drawn): "lookup" (the typed address looked up first), "unfound",
        "box-again" (a preview dropped by an address retyped: the box shown again as it was put back), "asked-cancel" (Cancel at the
        question: back to the box), "open" (the City's guide: the box stays open for Draw my lot…), or "drawn"
        (saved, the session committed, the starting house drawn again when it was cleared)."""
        state = self.shown()
        self._apply(state)
        previewed = self.saved.get("_pending") is not None
        self.facts, self.saved = logic.settle_pending(self.facts, self.saved, state["address"])
        if previewed and self.saved.get("_pending") is None:
            return "box-again"
        plan, mine, say = logic.draw_decision(self.table, self.facts, self.saved, state["address"])
        if say:
            self.said.append(say)
        if plan == "unfound":
            self.saved["_lookup"] = logic.lookup_after_unfound(self.saved.get("_lookup"), say)
        if plan in ("lookup", "unfound"):
            return plan
        redraw = False
        if plan == "none":
            self.saved.pop("_pending", None)
        else:
            choice = logic.START_FRESH
            if plan == "ask":
                question = logic.reset_question(self.saved["_pending"].get("address"), mine)
                self.asked.append(question)
                choice = reply(question) if reply else None
                if choice is None:
                    return "asked-cancel"
            self.facts, self.saved, redraw, guide = logic.apply_reset(self.table, self.session, self.facts,
                                                                      self.saved, choice, ZONES)
            state = logic.after_reset_state(state, self.shown())
            if guide and not self.facts.get("lot_id"):
                self.redraw_after = redraw
                return "open"
        redraw = redraw or getattr(self, "redraw_after", False)
        if not self.facts.get("lot_id"):
            raise AssertionError("Draw with no lot: the box should have stayed open")
        # _drawn: the box's state applied once more and saved, with every fact's source
        self._apply(state)
        self.session.commit()
        self.open = False
        site = self.site
        site.facts, site.saved = self.facts, logic.storable_ui(self.saved)
        site.sources = logic.fact_sources(state, "2026-10-22", confirmed=True)
        if redraw:                                 # edit_facts: the starting house drawn again for the new lot
            ids = [self.table._new(logic.MASSING, "brep") for _ in range(2)]
            for k, i in enumerate(ids):
                self.table.objects[i]["geom"] = "new f%d" % (k + 1)
            site.saved.update(house_fingerprint=self.table.fingerprint(ids), drawn_address=self.facts.get("address"))
        return "drawn"

    def draw_my_lot(self):
        new = self.table.add_lot([[0, 0], [50, 0], [50, 100], [0, 100]], "drawn")
        self.session.add([new])
        self.facts, self.saved = logic.pick_effect("draw_lot", new, self.facts, self.saved)
        return new

    def cancel(self):
        self.session.rollback()
        self.open = False


@pytest.fixture
def ground_on(monkeypatch):
    monkeypatch.setattr(logic, "FLAT_GROUND", False)


# ---- the scenarios ---------------------------------------------------------------------------------------------

def test_look_up_previews_only_and_cancel_leaves_the_file_as_it_was():
    site = Site()
    before = site.state()
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert site.table.snapshot() == before[0]                  # the model untouched: nothing drawn, nothing held
    assert box.preview and box.saved["_pending"]["answer"]["status"] == "found"
    assert box.facts["lot_id"] == "lot1" and box.button() == "Draw"
    assert "_pending" not in logic.storable_ui(box.saved)       # a preview is never written into the file
    for key in ("lot_id", "lot_surveyed", "corner_lot", "street_line"):   # its rows still say what is drawn
        assert box.facts.get(key) == site.facts.get(key), key
    box.cancel()
    assert site.state() == before


@pytest.mark.usefixtures("ground_on")
def test_a_new_address_over_gordiums_drawing_is_drawn_clean_without_a_question():
    site = Site()
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.draw() == "drawn" and box.asked == []
    assert not {"lot1", "floor1", "floor2"} & set(site.table.objects)       # Gordium's old drawing gone for good
    lot = site.facts["lot_id"]
    assert site.table.objects[lot]["layer"] == "Site" and site.saved["replaceable_lot"] == lot
    assert len(site.table.massing()) == 2 and site.table.ground_points()   # the house drawn again, the new ground
    assert logic.same_address(site.saved["drawn_address"], "96 Ithaca Rd")
    assert not [k for k in site.saved if k.startswith("_")]                # nothing of the session in the file


def test_the_same_address_draws_nothing_new_and_its_button_says_check():
    site = Site()
    before = site.table.snapshot()
    box = site.box().look_up(answer("106_ithaca_rd"))
    assert box.button() == "Check"
    assert box.draw() == "drawn" and box.asked == []
    assert site.table.snapshot()[0] == before[0]


def test_cancel_after_the_reset_puts_everything_back():
    site = Site()
    before = site.state()
    box = site.box().look_up(answer("96_ithaca_rd"))
    plan, mine, _ = logic.draw_decision(box.table, box.facts, box.saved, box.facts["address"])
    assert (plan, mine) == ("redraw", [])
    box.facts, box.saved, redraw, guide = logic.apply_reset(box.table, box.session, box.facts, box.saved,
                                                            logic.START_FRESH, ZONES)
    assert redraw and guide is None
    assert {box.table.objects[i]["layer"] for i in ("lot1", "floor1", "floor2")} == {logic.HOLDING_LAYER}
    box.cancel()                                     # an error or Esc after the reset: run_box rolls back
    assert site.state() == before


def test_an_edited_house_is_asked_about_once_and_keep_checks_it_on_the_new_lot():
    site = Site(house="edited")
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.draw() == "asked-cancel"                       # Cancel at the question: back to the box
    question, fresh, keep = box.asked[0]
    assert question.startswith("Start fresh for 96 Ithaca") and question.endswith(
        "Your changes to the starting house will be removed.")
    assert fresh == ("Start fresh", logic.START_FRESH)
    assert keep == ("Keep my building and check it on the new lot", logic.KEEP_MINE)
    assert box.table.objects["lot1"]["layer"] == "Site"      # nothing done until they answer
    assert box.draw(lambda q: logic.KEEP_MINE) == "drawn"
    assert {"floor1", "floor2"} <= set(site.table.objects) and "lot1" not in site.table.objects
    assert site.saved["house_fingerprint"] is None           # kept: theirs from now on
    again = site.box().look_up(answer("109_ithaca_rd"))       # so the next new address asks again
    assert again.draw() == "asked-cancel" and "your changes to the starting house" in again.asked[0][0].lower()


def test_start_fresh_over_the_architects_buildings_removes_them_only_after_the_question():
    site = Site(buildings=True)
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.draw(lambda q: logic.START_FRESH) == "drawn"
    assert box.asked[0][0].endswith("The buildings you drew will be removed.")
    assert "garage" not in site.table.objects and len(site.table.massing()) == 2


def test_their_lot_alone_offers_start_fresh_or_cancel_never_keep_my_building():
    site = Site(lot="theirs", house=None)
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.draw() == "asked-cancel"
    question, fresh, keep = box.asked[0]
    assert question.endswith("Your lot will be removed.") and keep is None
    assert box.draw(lambda q: logic.START_FRESH) == "drawn" and "lot1" not in site.table.objects


def test_a_typed_address_is_looked_up_first_and_on_their_own_lot_is_a_label():
    site = Site()
    before = site.state()
    box = site.box().type_address("96 Ithaca Rd")
    assert box.draw() == "lookup" and site.table.snapshot() == before[0]    # looked up first, the box again
    own = Site(lot="theirs")
    box = own.box().type_address("96 Ithaca Rd")
    assert box.draw() == "drawn" and box.said == [logic.OWN_LOT_LABEL]
    assert own.table.exists("lot1") and own.facts["address"] == "96 Ithaca Rd"


def test_the_last_look_up_is_the_one_drawn_and_a_failed_one_drops_the_preview():
    site = Site()
    box = site.box().look_up(answer("96_ithaca_rd")).look_up(answer("109_ithaca_rd"))
    assert logic.same_address(box.saved["_pending"]["address"], "109 Ithaca Rd")
    failed = answer("not_found")
    box.look_up(failed)
    assert "_pending" not in box.saved and box.button() == "Check"
    before = site.table.snapshot()
    # Draw with the address just not found: nothing drawn, said once, never the same lookup again and again
    assert box.draw() == "unfound" and site.table.snapshot() == before
    plan, _, say = logic.draw_decision(box.table, box.facts, box.saved, box.facts["address"])
    assert say == logic.UNFOUND.format(address=failed["query"], drawn=SAMPLE)
    assert box.type_address("106 Ithaca Road").draw() == "drawn"            # the drawn address put back
    assert site.table.snapshot()[0] == before[0]


def test_a_file_with_no_record_of_its_house_never_loses_it_silently():
    site = Site(house="no record", drawn=None)
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.draw() == "asked-cancel" and "starting house" in box.asked[0][0]


def test_the_city_outline_only_clears_gordiums_drawing_then_waits_for_their_lot():
    """The State's tax map didn't answer: nothing to draw the new lot from. The preview offers no Draw my lot… (a
    lot drawn over the old one would be taken for theirs); Draw clears Gordium's old drawing and the box stays open
    on the guide, Draw off until they draw their lot; then Draw keeps it as theirs. Cancel at any point: as it was."""
    site = Site()
    before = site.state()
    box = site.box().look_up(guide_only("96_ithaca_rd"))
    rows, state = box.rows()
    assert not [a for a in rows["lot"]["actions"] if a[0] == "draw_lot"]
    assert logic.GUIDE_PREVIEW in logic.uncertain(state)
    assert box.draw() == "open" and box.open
    assert {box.table.objects[i]["layer"] for i in ("lot1", "floor1", "floor2")} == {logic.HOLDING_LAYER}
    rows, state = box.rows()
    assert ("draw_lot", "Draw my lot…", True) in rows["lot"]["actions"] and not logic.can_draw(state)
    assert box.button() == "Draw"
    lot = box.draw_my_lot()
    assert box.draw() == "drawn" and box.asked == []
    assert site.table.exists(lot) and not {"lot1", "floor1", "floor2"} & set(site.table.objects)
    assert site.saved["replaceable_lot"] is None and len(site.table.massing()) == 2   # their lot; the house again
    cancelled = Site()
    box = cancelled.box().look_up(guide_only("96_ithaca_rd"))
    assert box.draw() == "open"
    box.draw_my_lot()
    box.cancel()
    assert cancelled.state() == before


@pytest.mark.parametrize("a, b, same", [
    ("109 Ithaca Road, Ithaca, NY 14850", "109 ithaca rd", True),
    ("106 ithaca rd, Ithaca NY 14850", "106 Ithaca Road", True),
    ("106 Ithaca Rd Ithaca NY 14850", "106 Ithaca Rd", True),
    ("106 N. Aurora St.", "106 North Aurora Street", True),
    ("106 Ithaca Rd", "106 Rd", False),                 # the street's own name is never the city's tail
    ("109 Ithaca Rd", "106 Ithaca Rd", False),
    ("106 Ithaca Rd", "106 Ithaca St", False),
    ("100 New York Ave", "100 Ave", False),
    ("", "", False),
    (None, "106 Ithaca Rd", False),
])
def test_same_address(a, b, same):
    assert logic.same_address(a, b) is same


# ---- every start, every lookup, every answer -------------------------------------------------------------------

STARTS = list(itertools.product(("sample", "theirs"), (None, "gordium", "edited", "no record"), (False, True)))
LOOKUPS = {"same": lambda: answer("106_ithaca_rd"), "new": lambda: answer("96_ithaca_rd"),
           "guide": lambda: guide_only("96_ithaca_rd"), "failed": lambda: answer("not_found"),
           "typed": None}
REPLIES = {"fresh": lambda q: logic.START_FRESH, "keep": lambda q: q[2] and logic.KEEP_MINE, "cancel": lambda q: None}


@pytest.mark.parametrize("start", STARTS, ids=lambda s: "-".join(map(str, s)))
def test_every_start_lookup_and_answer_keeps_the_promises(start):
    """For every start × lookup × answer: the architect's own building is never removed unless they were asked and
    said Start fresh, and their lot never unless they were asked (the question says it goes); Draw never ends without a lot; a new address drawn fresh leaves nothing Gordium drew for the old
    one; the same address or a failed lookup changes nothing; Cancel leaves the file exactly as it was; nothing of
    the session is ever written into the file."""
    lot, house, buildings = start
    for (kind, lookup), (said, reply) in itertools.product(LOOKUPS.items(), REPLIES.items()):
        site = Site(lot=lot, house=house, buildings=buildings)
        before, mine = site.state(), set(site.mine)
        gordiums = set(site.table.objects) - mine
        box = site.box()
        box = box.type_address("96 Ithaca Rd") if lookup is None else box.look_up(lookup())
        outcome = box.draw(reply)
        if outcome == "open":                                  # the guide: their lot drawn over it, then Draw
            box.draw_my_lot()
            outcome = box.draw(reply)
        where = (kind, said, outcome, box.asked)
        if outcome == "box-again":                             # never in this sweep: no address is retyped
            raise AssertionError(where)
        if outcome in ("lookup", "unfound", "asked-cancel"):
            box.cancel()
            assert site.state() == before, where
            continue
        assert outcome == "drawn", where
        left = set(site.table.objects)
        fresh = bool(box.asked) and said == "fresh"
        their_lot = {i for i in mine if i == before[1]["lot_id"]}
        assert mine - their_lot <= left or fresh, where        # their building: gone only on Start fresh
        assert their_lot <= left or box.asked, where           # their lot: only once asked (both answers say so:
        # "…will be removed" / "check it on the new lot")
        assert site.facts.get("lot_id") in left, where         # never a Draw without a lot
        assert not [k for k in site.saved if k.startswith("_")], where
        if kind in ("same", "failed") or (kind == "typed" and lot == "theirs"):
            assert site.table.snapshot()[0] == before[0][0], where   # nothing new drawn, nothing removed
        elif kind in ("new", "guide"):
            kept_house = said == "keep" and bool(box.asked) and box.asked[0][2]
            gone = gordiums - ({"floor1", "floor2"} if kept_house else set())
            assert not gone & left, where                      # nothing Gordium drew for the old address stays
            assert logic.same_address(site.saved["drawn_address"], "96 Ithaca Rd"), where


# ---- the plugin does what the harness does --------------------------------------------------------------------

def test_the_plugins_draw_takes_the_same_branches_as_the_harness():
    """gordium_rhino._draw_prepare does what Box.draw does, in its order: the box's answers into the facts, the
    preview settled, the district checked, rhino_logic.draw_decision, the question (Cancel: back to the box), the
    reset in one undo step, the state rebuilt from the new lot (saved by _drawn), and the box kept open on the City's
    guide; _box_loop keeps the architect's ticks when Draw stops; _apply_box is rhino_logic.box_facts; Edit site…
    closes the undo step on any way out, errors included; RhinoTable.buildings is the checker's own buildings."""
    rhino = (Path(__file__).resolve().parents[3] / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    prep = rhino[rhino.index("def _draw_prepare("):rhino.index("def _begin_undo(")]
    steps = ("facts, saved_ui = _apply_box(doc, facts, state, saved_ui)",
             'logic.settle_pending(facts, saved_ui, state.get("address"))',
             'if previewed and saved_ui.get("_pending") is None:',
             'logic.draw_decision(table, facts, saved_ui, state.get("address"))', 'if plan == "lookup":',
             'if plan == "unfound":', 'if plan == "none":', 'if plan == "ask":', "logic.reset_question(",
             "if choice is None:\n            return facts, saved_ui, False, state", "_begin_undo(",
             "logic.apply_reset(table, session, facts, saved_ui, choice",
             "logic.after_reset_state(state, _box_state(doc, facts, options, saved_ui, mode))",
             'if guide and not facts.get("lot_id"):', "return facts, saved_ui, True, fresh_state")
    at = [prep.find(step) for step in steps]
    assert -1 not in at and at == sorted(at), [st for st, i in zip(steps, at) if i == -1] or at
    loop = rhino[rhino.index("def _box_loop("):rhino.index("def _lookup_start(")]
    assert loop.count("_draw_prepare(doc, facts, state, saved_ui, session, mode, options)") == 2
    assert "return _drawn(doc, facts, drawn_state, saved_ui, session)" in loop      # the rebuilt state is saved
    draw = loop[loop.index('if what == "draw":'):]
    assert loop.index("ticked = {k: state[k]") < loop.index('if what == "draw":') and "continue" in draw
    assert "logic.box_facts(facts, saved_ui, state)" in rhino[rhino.index("def _apply_box("):]
    edit = rhino[rhino.index("def edit_facts("):rhino.index("def report_path(")]
    outer = edit.index("    try:                                # one undo step")
    assert outer < edit.index("facts = confirm(") < edit.index("    finally:\n        STATE.pop(\"redraw_house\"")
    assert edit.rstrip().endswith("run_check(doc, report=False)") and "_end_undo(doc)" in edit
    table = rhino[rhino.index("class RhinoTable"):]
    assert "return logic.own_buildings(" in table[table.index("def buildings("):]
    # one walk of the model for the checker's sorting and a reset's questions (round 3)
    sort = rhino[rhino.index("def _sorted_objects("):rhino.index("def _lot_candidates(")]
    assert "_classified_objects(doc)" in sort and "ObjectEnumeratorSettings" not in sort
    walks = table[table.index("    def _on("):table.index("def fingerprint(")]
    assert walks.count("_classified_objects(self.doc)") == 2 and "ObjectEnumeratorSettings" not in walks


# ---- review round 1: each confirmed finding, as the architect would meet it --------------------------------------

def test_a_reset_saves_the_new_lot_as_drawn_never_the_old_lots_survey_or_size():
    """P0: Draw saved the box's state from before the reset over the new lot: a surveyed lot's yes and its size
    went onto the tax-map lot that replaced it (the checker would then take ±2 ft lines as exact)."""
    site = Site(lot="theirs", house=None, surveyed=True)
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.draw(lambda q: logic.START_FRESH) == "drawn"
    lot = site.facts["lot_id"]
    assert site.facts["lot_surveyed"] is False and site.facts.get("street_line")
    assert site.sources["lot"]["value"] == logic.lot_size(site.table.objects[lot]["area"]) != logic.lot_size(6570.0)
    assert site.sources["lot"]["source"].startswith("the tax map") and site.saved["lot_source"] != "your survey"
    assert site.facts["zone"] and site.facts["use"] == "one_family"     # the box's own choices kept


def test_an_address_typed_after_look_up_drops_the_preview_and_its_district():
    """P1: the preview was drawn even after the architect typed the drawn address back (the lot then saved under
    it); and the other address's district stayed in the box."""
    site = Site()
    before = site.state()
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.facts["zone"] != "R-1b" or box.saved.get("zone_source") != "entered by you"   # the preview's
    assert box.type_address(SAMPLE).draw() == "box-again"
    assert box.facts["zone"] == "R-1b" and box.saved["zone_source"] == "entered by you"
    said = logic.uncertain(box.shown()) or ""                 # its line went with it (round 3)
    assert "Shown dashed" not in said and said.startswith("The lookup of 96 Ithaca")
    assert box.button() == "Check" and not box.saved["_lookup"]["asks"]
    assert box.type_address("96 Ithaca Rd").draw() == "lookup"   # typed again: looked up again, never "not found"
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.type_address(SAMPLE).draw() == "box-again"
    assert box.draw() == "drawn"
    assert site.table.snapshot()[0] == before[0][0] and site.saved["drawn_address"] == SAMPLE
    assert site.facts["zone"] == "R-1b" and site.saved["zone_source"] == "entered by you"


def test_a_failed_lookup_after_a_preview_leaves_nothing_of_it():
    """P1: a later failed lookup dropped the pending answer but left its facts in the box, saved on the old lot."""
    site = Site()
    box = site.box().look_up(answer("109_ithaca_rd")).look_up(answer("not_found"))
    assert box.facts["zone"] == "R-1b" and box.saved["zone_source"] == "entered by you"
    assert box.facts["corner_lot"] is False and box.facts["street_line"] == [[[0, 0], [60, 0]]]
    assert box.type_address(SAMPLE).draw() == "drawn"            # no preview left to drop (the lookup failed)
    assert site.facts["zone"] == "R-1b" and site.saved["zone_source"] == "entered by you"
    assert "lot_area" not in site.saved and not site.saved.get("street_source")


def test_buildings_on_a_sublayer_are_asked_about():
    """P2: own_work found only objects on the exact Building layer: a garage on Building::Garage was never asked
    about, and removed at a reset."""
    site = Site(buildings=True, building_layer="Building::Garage")
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.draw() == "asked-cancel" and box.asked[0][0].endswith("The buildings you drew will be removed.")


def test_a_lookup_that_failed_offline_says_so_at_draw_never_not_found():
    """P3: Draw after an offline, timeout or error lookup said the address "wasn't found", over the real reason."""
    site = Site()
    box = site.box().look_up({"status": "offline", "query": "96 Ithaca Rd"})
    assert box.draw() == "unfound"
    assert box.said[-1].startswith(logic.LOOKUP_SAYS["offline"]) and "wasn't found" not in box.said[-1]
    box = site.box().look_up(answer("not_found"))
    assert box.draw() == "unfound" and "wasn't found" in box.said[-1]


def test_the_district_the_architect_picked_survives_the_reset():
    """The reset fills the lot, street side, corner and ground from the lookup, never the district, use or address
    the architect set in the box (picked over the lookup's suggestion, then ticked)."""
    site = Site()
    box = site.box().look_up(answer("96_ithaca_rd"))
    suggested = box.facts.get("zone")
    picked = next(z for z in ZONES if z != suggested)
    box.typed.update(zone=picked, use="two_family")
    assert box.draw() == "drawn"
    assert site.facts["zone"] == picked and site.facts["use"] == "two_family"
    assert logic.same_address(site.facts["address"], "96 Ithaca Rd")
    # …and when the box stays open on the City's guide after the reset, it still shows their district
    site = Site()
    box = site.box().look_up(guide_only("96_ithaca_rd"))
    box.typed.update(zone=picked)
    assert box.draw() == "open" and box.shown()["zone"] == picked and box.facts["use"] == "one_family"


def test_a_preview_whose_district_has_no_rules_gives_the_district_back_when_the_address_is_retyped():
    """Headless run of the plugin at ea7963b: 96 looked up where the City map says a district Gordium has no rules
    for (the box then shows no district), the drawn address typed back: the sample's district must come back (the
    box writes "no district" as None, and the preview's undo matched only "no value": R-1b was lost at Draw)."""
    p = answer("96_ithaca_rd")
    p["facts"] = {**p["facts"], "zone": {**p["facts"]["zone"], "value": "R-3b"}}
    site = Site()
    box = site.box().look_up(p)
    assert not box.facts.get("zone")                           # no rules for R-3b: no district set
    assert box.type_address(SAMPLE).draw() == "box-again"     # put back, shown, ticked again
    assert box.facts["zone"] == "R-1b" and box.saved["zone_source"] == "entered by you"
    assert box.draw() == "drawn" and site.facts["zone"] == "R-1b"


# ---- review round 2 ---------------------------------------------------------------------------------------------

def test_own_buildings_are_what_the_checker_sees_on_building_never_the_starting_house():
    """Round 2: RhinoTable.buildings took only measurable solids; a block or a surface on Building (each a problem
    the check names) was never asked about and stayed on the new lot after Start fresh."""
    objects = [("solid", "Building", "Brep", False), ("garage", "Building::Garage", "Surface", False),
               ("block", "Building", "InstanceReferenceGeometry", False),
               ("placed", "Site", "InstanceReferenceGeometry", True),          # a block holding a building
               ("house", logic.MASSING, "Brep", False), ("held", logic.HOLDING_LAYER, "Brep", False),
               ("aid", "Building", "PolylineCurve", False), ("lot", "Site", "PolylineCurve", False),
               ("tree", "Site", "InstanceReferenceGeometry", False)]
    assert logic.own_buildings(objects) == ["solid", "garage", "block", "placed"]
    site = Site(buildings=True, building_type="InstanceReferenceGeometry")
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.draw(lambda q: logic.START_FRESH) == "drawn" and "garage" not in site.table.objects
    assert box.asked[0][0].endswith("The buildings you drew will be removed.")


def test_the_architects_own_answers_keep_their_source_when_draw_stops():
    """Round 2: when Draw stopped (the district put back, a lookup started) the box's ticks went, and the use the
    architect set was saved under the sample's source."""
    p = answer("96_ithaca_rd")
    p["facts"] = {**p["facts"], "zone": {**p["facts"]["zone"], "value": "R-3b"}}
    site = Site()
    box = site.box().look_up(p)
    box.typed.update(use="two_family", use_source=logic.ENTERED)
    assert box.type_address(SAMPLE).draw() == "box-again"
    assert box.draw() == "drawn"
    assert site.sources["use"]["value"] == "two_family" and site.sources["use"]["source"] == logic.ENTERED


def test_draw_after_an_outside_city_or_ambiguous_lookup_keeps_its_own_words():
    """Round 2: the lookup's message (the town it is in, the matches) was rebuilt without it at Draw; a second Draw
    says it once, never wrapped twice."""
    site = Site()
    town = "This address is in the Town of Lansing, not the City of Ithaca."
    box = site.box().look_up({"status": "outside_city", "query": "5 Main St, Lansing", "message": town})
    assert box.draw() == "unfound" and box.said[-1].startswith(town)
    assert box.draw() == "unfound" and box.said[-1].count(town) == 1 and box.said[-1].count("Nothing is drawn") == 1
    many = "2 addresses match: 106 Ithaca Rd, 106 Ithaca St."
    box = site.box().look_up({"status": "multiple", "query": "106 Ithaca", "message": many})
    assert box.draw() == "unfound" and many in box.said[-1]
