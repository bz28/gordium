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
import re
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
        # "sample": the sample project's lot; "looked_up": a lot an earlier lookup drew (Gordium's, on the map);
        # "theirs": the architect's own
        self.saved = {"replaceable_lot": None if lot == "theirs" else "lot1", "from_sample": lot == "sample",
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
        if self.saved.get("replaceable_lot") != self.facts.get("lot_id"):
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
        self.facts, self.saved = dict(site.facts), logic.box_opened(site.saved, site.facts)
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
                 "known_addresses": logic.known_addresses(sv),
                 "checked": sv.get("checked") or []}
        return dict(logic.show_pending_lot(dict(state, **self.typed), f, sv), **self.typed)

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
        """Draw (gordium_rhino._draw_prepare then _drawn): "off" (an address typed and not looked up: Draw is off,
        its reason said), "box-again" (a preview dropped by an address retyped: the box shown again as it was put back), "asked-cancel" (Cancel at the
        question: back to the box), "open" (the City's guide: the box stays open for Draw my lot…), or "drawn"
        (saved, the session committed, the starting house drawn again when it was cleared)."""
        state = self.shown()
        reason = logic.draw_blocked(state, self.saved)
        if reason:                                 # Draw is off (the plugin's _draw_prepare says why on any way in)
            self.said.append(reason)
            return "off"
        self._apply(state)
        previewed = self.saved.get("_pending") is not None
        self.facts, self.saved = logic.settle_pending(self.facts, self.saved, state["address"])
        if previewed and self.saved.get("_pending") is None:
            return "box-again"
        plan, mine = logic.draw_decision(self.table, self.facts, self.saved)
        redraw = False
        if plan == "none":
            self.saved.pop("_pending", None)
        else:
            choice = logic.START_FRESH
            if plan == "ask":
                question = logic.reset_question(self.saved["_pending"].get("address"), mine,
                                                self.saved["_pending"].get("answer"))
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
    for key in ("lot_id", "lot_surveyed", "street_line"):   # its rows still say what is drawn
        assert box.facts.get(key) == site.facts.get(key), key
    # ...but Corner lot? (an answer, not a drawing) shows the lookup's, the one Draw saves (UX walkthrough
    # 2026-10-28): 96 Ithaca Rd's lookup found two streets
    assert box.facts.get("corner_lot") is True and site.facts["corner_lot"] is False
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
    site = Site(lot="looked_up")
    before = site.table.snapshot()
    box = site.box().look_up(answer("106_ithaca_rd"))
    assert box.button() == "Check"
    assert box.draw() == "drawn" and box.asked == []
    assert site.table.snapshot()[0] == before[0]


def test_look_up_then_check_on_a_drawn_sample_never_starts_fresh():
    """Ben's P0 (coordinator, 2026-10-27): on a file drawn from the sample, Edit site's Look up of its own address
    then Check started fresh: the lot and the starting house were redrawn over the architect's work. A drawn sample
    is drawn (is_drawn): the same address draws nothing new, every answer and the drawing stay as they were."""
    site = Site(house="gordium")
    site.facts.update(unrelated_persons=2, home_occupation=True, home_occupation_area=300.0)
    before = site.table.snapshot()
    box = site.box().look_up(answer("106_ithaca_rd"))
    assert box.button() == "Check"
    assert box.draw() == "drawn" and box.asked == []
    assert site.table.snapshot()[0] == before[0] and site.facts["lot_id"] == "lot1"     # nothing redrawn
    assert (site.facts["unrelated_persons"], site.facts["home_occupation"], site.facts["home_occupation_area"]) == \
        (2, True, 300.0)
    edited = Site(house="edited")                       # their own edits: never even asked about
    before = edited.table.snapshot()
    again = edited.box().look_up(answer("106_ithaca_rd"))
    assert again.draw() == "drawn" and again.asked == [] and edited.table.snapshot()[0] == before[0]

def test_cancel_after_the_reset_puts_everything_back():
    site = Site()
    before = site.state()
    box = site.box().look_up(answer("96_ithaca_rd"))
    plan, mine = logic.draw_decision(box.table, box.facts, box.saved)
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
    assert question == "Start fresh for 96 Ithaca Road? Your changes to the starting house will be removed."
    assert fresh == ("Start fresh", logic.START_FRESH)
    assert keep == ("Keep my building and check it on 96 Ithaca Road's lot", logic.KEEP_MINE)
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
    assert question == "Start fresh for 96 Ithaca Road? Your lot will be replaced by 96 Ithaca Road's lot." and keep is None
    assert box.draw(lambda q: logic.START_FRESH) == "drawn" and "lot1" not in site.table.objects


def test_keep_my_building_on_their_surveyed_lot_replaces_the_lot_and_keeps_the_building():
    """Ben (2026-10-25): a new address is a new site. Keep my building keeps only the architect's buildings, checked
    on the new address's lot; their own lot (surveyed here) is replaced too, and both the question and the Keep
    answer say so plainly. All of it in one box session (one undo): Cancel after the reset puts it all back."""
    site = Site(lot="theirs", house="edited", buildings=True, surveyed=True)
    before = site.state()
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.draw() == "asked-cancel"
    question, fresh, keep = box.asked[0]
    assert question == ("Start fresh for 96 Ithaca Road? Your changes to the starting house and the buildings you "
                        "drew will be removed. Your surveyed lot will be replaced by 96 Ithaca Road's lot.")
    assert keep == ("Keep my building and check it on 96 Ithaca Road's lot (your surveyed lot will be replaced)",
                    logic.KEEP_MINE)
    assert site.state() == before                            # nothing done until they answer
    box.facts, box.saved, redraw, _ = logic.apply_reset(box.table, box.session, box.facts, box.saved,
                                                        logic.KEEP_MINE, ZONES)
    assert not redraw and box.table.objects["lot1"]["layer"] == logic.HOLDING_LAYER   # held, in the one session
    box.cancel()
    assert site.state() == before                            # Cancel after the reset: as it was
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.draw(lambda q: logic.KEEP_MINE) == "drawn"
    assert {"floor1", "floor2", "garage"} <= set(site.table.objects)       # their building kept
    assert "lot1" not in site.table.objects                                # their surveyed lot replaced
    lot = site.facts["lot_id"]
    assert site.table.objects[lot]["layer"] == "Site" and site.saved["replaceable_lot"] == lot
    assert site.facts["lot_surveyed"] is False               # the tax map's lot: never carried as their survey
    assert site.saved.get("lot_source") != "your survey"
    assert logic.same_address(site.saved["drawn_address"], "96 Ithaca Rd")


@pytest.mark.parametrize("source, words", [("drawn by you", "the lot you drew"), (None, "your lot")])
def test_the_question_names_their_lot_as_it_came(source, words):
    """Their lot named as it came: surveyed (above), drawn by them, or picked; on the City's outline only, the new
    lot is the one they draw over it."""
    site = Site(lot="theirs", house="edited")
    site.saved["lot_source"] = source
    box = site.box().look_up(answer("96_ithaca_rd"))
    box.draw()
    question, _, keep = box.asked[0]
    assert question.endswith(words[0].upper() + words[1:] + " will be replaced by 96 Ithaca Road's lot.")
    assert keep[0].endswith("(" + words + " will be replaced)")
    guide = Site(lot="theirs", house="edited").box().look_up(guide_only("96_ithaca_rd"))
    guide.draw()
    assert guide.asked[0][0].endswith("Your lot will be replaced (you draw 96 Ithaca Road's lot over the City's "
                                      "outline).")


@pytest.mark.parametrize("start", [dict(), dict(lot="looked_up"), dict(lot="theirs"), dict(lot="theirs", surveyed=True),
                                   dict(lot="theirs", drawn_lot=True), dict(lot="theirs", drawn=None, house=None),
                                   dict(lot="theirs", labelled="12 Oak Ave")],
                         ids=["sample", "looked_up", "picked", "surveyed", "drawn", "empty_file", "own_address"])
def test_an_address_typed_and_not_looked_up_turns_draw_off_on_every_start(start):
    """Ben (2026-10-25): an address in the box that is neither the lot's own nor the one last looked up turns Draw
    off, with the box's usual reason line, "Press Look up to find 96 Ithaca Rd first."; never a label saved on the
    old lot. Typing back the original address turns Draw on again. On every start: the sample, a lot looked up
    before, the architect's own lot (picked, surveyed or drawn), and a file with no address yet."""
    drawn_lot, labelled = start.pop("drawn_lot", False), start.pop("labelled", None)
    site = Site(**start)
    if labelled:                                              # the lot's own address, never the one drawn
        site.facts["address"] = labelled
    if drawn_lot:
        site.saved["lot_source"] = "drawn by you"
    if start.get("drawn", SAMPLE) is None:
        site.facts.pop("address")
    before = site.state()
    box = site.box()
    original = box.shown()["address"]
    assert logic.address_reason(box.shown()) == ""            # as it opened: Draw as before
    box.type_address("96 Ithaca Rd")
    assert logic.address_reason(box.shown()) == "Press Look up to find 96 Ithaca Rd first."
    assert logic.draw_reason(dict(box.shown(), zone=None)) == "Press Look up to find 96 Ithaca Rd first."   # first
    assert box.draw() == "off" and box.said == ["Press Look up to find 96 Ithaca Rd first."]
    assert site.state() == before                             # nothing drawn, nothing saved
    box.type_address(original)                                # typed back: Draw on again
    assert logic.address_reason(box.shown()) == ""
    assert box.draw() == "drawn" and site.table.snapshot()[0] == before[0][0]
    assert site.facts.get("address") == before[1].get("address")      # never another address on the old lot


def test_the_last_look_up_is_the_one_drawn_and_a_failed_one_drops_the_preview():
    site = Site()
    box = site.box().look_up(answer("96_ithaca_rd")).look_up(answer("109_ithaca_rd"))
    assert logic.same_address(box.saved["_pending"]["address"], "109 Ithaca Rd")
    failed = answer("not_found")
    box.look_up(failed)
    assert "_pending" not in box.saved and box.button() == "Check"
    before = site.table.snapshot()
    # the address just not found: Draw off, saying so (never Look up again and again, never a label saved)
    assert box.draw() == "off" and site.table.snapshot() == before
    assert box.said[-1] == logic.NOT_FOUND_YET.format(address=failed["query"], back="put back 106 Ithaca Rd")
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
    assert logic.GUIDE_PREVIEW in logic.uncertain(state) and logic.lookup_note(state) is None   # it asks: amber
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

STARTS = list(itertools.product(("sample", "looked_up", "theirs"), (None, "gordium", "edited", "no record"),
                                (False, True)))
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
        if kind in ("typed", "failed"):                        # an address not looked up, or not found: Draw off
            assert outcome == "off" and box.said[-1] in (logic.LOOK_UP_FIRST.format(address="96 Ithaca Rd"),
                                                         logic.NOT_FOUND_YET.format(address=box.shown()["address"],
                                                                                    back="put back 106 Ithaca Rd")), where
        if outcome in ("off", "asked-cancel"):
            box.cancel()
            assert site.state() == before, where
            continue
        assert outcome == "drawn", where
        left = set(site.table.objects)
        fresh = bool(box.asked) and said == "fresh"
        their_lot = {i for i in mine if i == before[1]["lot_id"]}
        assert mine - their_lot <= left or fresh, where        # their building: gone only on Start fresh
        assert their_lot <= left or box.asked, where           # their lot: only once asked (both answers say so:
        # "…will be replaced by 96 Ithaca Road's lot" / "(your lot will be replaced)")
        if box.asked and kind in ("new", "guide"):             # a new address is a new site (Ben, 2026-10-25):
            assert not their_lot & left, where                 # their lot replaced whichever they answered
            if their_lot:
                assert "will be replaced" in box.asked[0][0] and (
                    box.asked[0][2] is None or "will be replaced)" in box.asked[0][2][0]), where
        assert site.facts.get("lot_id") in left, where         # never a Draw without a lot
        assert not [k for k in site.saved if k.startswith("_")], where
        if kind == "same":                                     # a drawn sample too (Ben's P0, 2026-10-27)
            assert site.table.snapshot()[0] == before[0][0], where   # nothing new drawn, nothing removed
        elif kind in ("new", "guide"):
            kept_house = said == "keep" and bool(box.asked) and box.asked[0][2]
            gone = gordiums - ({"floor1", "floor2"} if kept_house else set())
            assert not gone & left, where                      # nothing Gordium drew for the old address stays
            assert logic.same_address(site.saved["drawn_address"], "96 Ithaca Rd"), where


# ---- the plugin does what the harness does --------------------------------------------------------------------

def test_after_the_city_guide_reset_the_old_address_is_a_new_one_again():
    """Typed-address rule, review round 1 (P1): after the City-guide reset (the box stays open), the address the box
    opened with stayed known, so typing it back saved it on the lot drawn for 96."""
    site = Site()
    box = site.box().look_up(guide_only("96_ithaca_rd"))
    assert box.draw() == "open"
    box.draw_my_lot()
    box.type_address(SAMPLE)
    assert box.draw() == "off" and box.said[-1] == logic.LOOK_UP_FIRST.format(address=SAMPLE)
    box.type_address(box.saved["drawn_address"])            # 96, as found: the lot's address now
    assert box.draw() == "drawn" and logic.same_address(site.facts["address"], "96 Ithaca Rd")


@pytest.mark.parametrize("status, words", [("not_found", "No lot found for"), ("offline", "didn't finish"),
                                           ("timeout", "didn't finish"), ("error", "didn't finish"),
                                           ("multiple", "Pick one of the matches")])
def test_the_reason_says_what_to_do_for_each_failed_lookup(status, words):
    """Typed-address rule, review round 1 (P2, P3): the reason fits how the lookup failed (not found: correct it;
    no answer: Look up again; several: pick one), and the lookup's own line no longer sends the architect to a dead
    end: it says to put back the lot's own address or clear it. With no address known, the way out is to clear it."""
    reason = logic.address_reason({"address": "Q St", "known_addresses": [SAMPLE],
                                   "lookup": {"status": status, "query": "Q St"}})
    assert reason.startswith(words) or words in reason
    if status != "multiple":
        assert reason.endswith("put back 106 Ithaca Rd.")
        alone = logic.address_reason({"address": "Q St", "known_addresses": [], "lookup": {"status": status,
                                                                                           "query": "Q St"}})
        assert alone.endswith("or clear the address.")
        assert "or clear it" in logic.LOOKUP_SAYS[status]


def test_another_towns_address_is_never_taken_for_the_lots_own():
    """Round 2 (P2): the gate compared only the street words, so "106 Ithaca Rd, Dryden" was the lot's own."""
    known = {"known_addresses": [SAMPLE]}
    assert logic.address_reason(dict(known, address="106 Ithaca Rd, Dryden, NY 13053")) == \
        "Press Look up to find 106 Ithaca Rd, Dryden, NY 13053 first."
    assert logic.address_reason(dict(known, address="106 Ithaca Rd, Lansing")) != ""
    for same in ("106 Ithaca Road", "106 ithaca rd, Ithaca NY 14850", "106 Ithaca Rd, Ithaca, NY, 14850-1234",
                 "106 Ithaca Rd, City of Ithaca, NY", "106 Ithaca Rd, Ithaca, United States", "106 Ithaca Rd, Ithaca, N.Y.",
                 "106 Ithaca Rd, Ithaca, New York, United States of America", "106 Ithaca Rd, Ithaca City"):
        assert logic.address_reason(dict(known, address=same)) == "", same
    assert logic.address_reason(dict(known, address="106 Ithaca Rd, Town of Ithaca")) != ""   # another municipality
    failed = {"status": "not_found", "query": "500 Elm St"}            # its failure is never another town's
    assert logic.address_reason(dict(known, address="500 Elm St, Dryden", lookup=failed)) == \
        logic.LOOK_UP_FIRST.format(address="500 Elm St, Dryden")


def test_while_a_lookup_runs_the_reason_never_says_to_press_look_up():
    """Round 2 (P2): while the lookup of the address ran, the reason said "Press Look up to find it first"."""
    site = Site()
    box = site.box().type_address("96 Ithaca Rd")
    box._apply()
    box.saved["_lookup"] = {"looking": "96 Ithaca Rd"}
    assert logic.address_reason(box.shown()) == "Looking up 96 Ithaca Rd: Draw once the answer is in."
    box.type_address(SAMPLE)                                 # the lot's own typed back meanwhile: still waits
    assert logic.address_reason(box.shown()) == "Looking up 96 Ithaca Rd: Draw once the answer is in."
    box.type_address("500 Elm St")                           # another typed: the line names the lookup's address
    assert logic.address_reason(box.shown()) == "Looking up 96 Ithaca Rd: Draw once the answer is in."
    box.type_address("96 Ithaca Rd")
    before = site.state()
    assert box.draw() == "off" and site.state() == before    # the gate stays on (round 3): never a label saved


def test_a_loose_query_typed_back_is_saved_as_found():
    """Round 2 (P3): after a misspelt "96 Ithica Rd" was found as 96 Ithaca Road, typing the query back and drawing
    saved the misspelling, not the address found."""
    site = Site()
    p = answer("96_ithaca_rd")
    p["query"] = "96 Ithica Rd"
    box = site.box().look_up(p)
    box.type_address("96 Ithica Rd")
    box.typed["address_source"] = logic.ENTERED           # as the box marks a field the architect typed in
    assert box.draw() == "drawn" and logic.same_address(site.facts["address"], "96 Ithaca Road")
    assert site.facts["address"] == site.saved["drawn_address"]
    assert site.sources["address"]["source"] != logic.ENTERED      # the lookup's address with the lookup's source


def test_after_the_guide_reset_the_found_address_keeps_the_lookups_source():
    """Round 4 (P2): on the City-guide path the box's loop carried the old box's ticks back, address_source
    ("entered by you") among them, over the address as found; it was saved as the architect's."""
    rhino = (Path(__file__).resolve().parents[3] / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    keeps = eval(rhino.split("\nGUIDE_KEEPS = ", 1)[1].split("\n", 1)[0])       # noqa: S307 (the file's own tuple)
    assert "address_source" not in keeps
    assert "if k in GUIDE_KEEPS}" in rhino[rhino.index("def _box_loop("):]
    site = Site()
    p = guide_only("96_ithaca_rd")
    p["query"] = "96 Ithica Rd"
    box = site.box().look_up(p)
    box.type_address("96 Ithica Rd")
    box.typed["address_source"] = logic.ENTERED
    ticked = {k: box.shown()[k] for k in ("district_confirmed", "zone_source", "address_source", "use_source")}
    assert box.draw() == "open"
    box.typed.update({k: v for k, v in ticked.items() if k in keeps})   # as the plugin's loop carries them
    box.draw_my_lot()
    assert box.draw() == "drawn" and logic.same_address(site.facts["address"], "96 Ithaca Road")
    assert site.sources["address"]["source"] != logic.ENTERED


def test_the_box_turns_draw_off_and_on_as_the_address_is_typed():
    """Ben (2026-10-25): the box's Draw follows the address field as it is typed (off, with its reason, for an
    address not looked up; on again when the lot's own is typed back), not only after a pick; the box opens
    knowing the lot's own address."""
    ui = (Path(__file__).resolve().parents[3] / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    typed = ui[ui.index("    def address_typed(s, e):"):ui.index('address.TextChanged += logic.guard(address_typed')]
    assert 'state["address"] = address.Text' in typed
    assert "draw.Enabled = logic.can_draw(state) and not looking" in typed and \
        "reason.Text = logic.box_reason(state)" in typed   # (draw_reason, said once: #33)
    rhino = (Path(__file__).resolve().parents[3] / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert "saved_ui = logic.box_opened(_ui_state(doc), facts)" in rhino[rhino.index("def _confirm("):]
    assert '"known_addresses": logic.known_addresses(saved_ui),' in rhino[rhino.index("def _box_state("):]


def test_the_plugins_draw_takes_the_same_branches_as_the_harness():
    """gordium_rhino._draw_prepare does what Box.draw does, in its order: the box's answers into the facts, the
    preview settled, the district checked, rhino_logic.draw_decision, the question (Cancel: back to the box), the
    reset in one undo step, the state rebuilt from the new lot (saved by _drawn), and the box kept open on the City's
    guide; _box_loop keeps the architect's ticks when Draw stops; _apply_box is rhino_logic.box_facts; Edit site…
    closes the undo step on any way out, errors included; RhinoTable.buildings is the checker's own buildings."""
    rhino = (Path(__file__).resolve().parents[3] / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    prep = rhino[rhino.index("def _draw_prepare("):rhino.index("def _begin_undo(")]
    steps = ("unlooked = logic.draw_blocked(state, saved_ui)",
             "if unlooked:                                          # Draw is off in the box; any other way in",
             "say(unlooked)\n        return facts, saved_ui, False, state",
             "facts, saved_ui = _apply_box(doc, facts, state, saved_ui)",
             'logic.settle_pending(facts, saved_ui, state.get("address"))',
             'if previewed and saved_ui.get("_pending") is None:',
             'logic.draw_decision(table, facts, saved_ui)', 'if plan == "none":', 'if plan == "ask":',
             # the question is told the pending answer (the City's outline only: "you draw … over the City's outline")
             'logic.reset_question(saved_ui["_pending"].get("address"), mine,\n'
             '                                                     saved_ui["_pending"].get("answer"))',
             "if choice is None:\n            return facts, saved_ui, False, state", "_begin_undo(",
             "logic.apply_reset(table, session, facts, saved_ui, choice",
             "_reset_state(doc, facts, options, saved_ui, mode, state)",   # (logic.after_reset_state, as the dry plan: #32)
             'if guide and not facts.get("lot_id"):', "return facts, saved_ui, True, fresh_state")
    at = [prep.find(step) for step in steps]
    assert -1 not in at and at == sorted(at), [st for st, i in zip(steps, at) if i == -1] or at
    loop = rhino[rhino.index("def _box_loop("):rhino.index("def _lookup_start(")]
    assert loop.count("_draw_prepare(doc, facts, state, saved_ui, session, mode, options)") == 2
    assert "return _drawn(doc, facts, drawn_state, saved_ui, session, mode)" in loop   # the rebuilt state is saved
    draw = loop[loop.index('if what == "draw":'):]
    assert loop.index("ticked = logic.box_ticks(state)") < loop.index('if what == "draw":') and "continue" in draw
    assert "logic.box_facts(facts, saved_ui, state)" in rhino[rhino.index("def _apply_box("):]
    edit = rhino[rhino.index("def edit_facts("):rhino.index("def report_path(")]
    outer = edit.index("    try:                                # one undo step")
    assert outer < edit.index("facts = confirm(") < edit.index("    finally:\n        STATE.pop(\"redraw_house\"")
    assert edit.rstrip().endswith("run_check(doc, report=False)        # the model as it is (as it was, after a "
                                  "Cancel)\n    if cancelled:\n        say(cancelled)") and "_end_undo(doc)" in edit
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
    said = logic.lookup_note(box.shown()) or ""               # its line went with it (round 3)
    assert "Shown dashed" not in said and said.startswith("The lookup of 96 Ithaca")
    assert box.button() == "Check" and not box.saved["_lookup"]["asks"]
    assert box.type_address("96 Ithaca Rd").draw() == "off"      # typed again: to be looked up again, never "not found"
    assert box.said[-1] == "Press Look up to find 96 Ithaca Rd first."
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


def _rows_of(box):
    return {r["key"]: r["text"] for r in logic.box_rows(box.shown())}


def test_in_an_empty_file_a_found_lookup_shows_its_own_lot_and_street_after_draw():
    """Ben, 2026-10-27: after Look up in an empty file (only the sample's stand-in lot) the Lot and Front lot line
    rows kept the sample's 7,033 sf and Ithaca Rd until Draw. They show the looked-up lot, marked "after Draw"."""
    site = Site()
    sample = _rows_of(site.box())
    assert "after Draw" not in sample["lot"] + sample["street"]
    box = site.box().look_up(answer("96_ithaca_rd"))
    found = answer("96_ithaca_rd")["facts"]["lot"]["value"]["area_sf"]
    rows = _rows_of(box)
    assert rows["lot"].startswith(logic.lot_size(found)) and rows["lot"].endswith(" · after Draw")
    assert "from the tax map" in rows["lot"] or "NYS" in rows["lot"]
    assert rows["street"].endswith(" · after Draw") and rows["street"] != sample["street"] + " · after Draw"
    assert logic.lot_size(6570.0) not in rows["lot"]               # never the sample lot's area
    assert all(a[0] not in ("lot", "street") for r in logic.box_rows(box.shown())
               if r["key"] in ("lot", "street") for a in r["actions"])
    assert box.facts.get("lot_id") == "lot1" and "lot_area" not in box.saved     # display only: no fact written


def test_with_a_lot_drawn_a_lookup_leaves_the_lot_and_street_rows_describing_the_drawing():
    for lot in ("looked_up", "theirs"):
        site = Site(lot=lot)
        before = _rows_of(site.box())
        rows = _rows_of(site.box().look_up(answer("96_ithaca_rd")))
        assert rows["lot"] == before["lot"] and rows["street"] == before["street"], lot
        assert "after Draw" not in rows["lot"] + rows["street"]


def test_a_failed_lookup_after_a_found_one_leaves_none_of_its_lot_and_street():
    site = Site()
    before = _rows_of(site.box())
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert _rows_of(box)["lot"] != before["lot"]
    box.look_up(answer("not_found"))
    after = _rows_of(box)
    assert (after["lot"], after["street"]) == (before["lot"], before["street"])
    box.look_up(answer("96_ithaca_rd")).look_up(answer("109_ithaca_rd"))       # a new lookup: only the new one's
    rows = _rows_of(box)
    assert rows["lot"].startswith(logic.lot_size(answer("109_ithaca_rd")["facts"]["lot"]["value"]["area_sf"]))


def test_no_after_draw_when_the_address_is_already_drawn_and_draw_would_draw_nothing():
    """Review round 1: with no lot in the file but drawn_address equal to the looked-up address, Draw draws nothing,
    so the rows must not promise a lot "after Draw"."""
    site = Site(lot="looked_up", drawn="96 Ithaca Rd, Ithaca, NY")
    for k in ("lot_id", "street_line"):
        site.facts.pop(k)
    del site.table.objects["lot1"]
    rows = _rows_of(site.box().look_up(answer("96_ithaca_rd")))
    assert "after Draw" not in rows["lot"] + rows["street"]


def test_rows_do_not_show_the_found_lot_while_another_address_is_typed_or_looked_up():
    """Review round 2: address A found, then B typed (or B being looked up): A's lot must not stay under B."""
    site = Site()
    before = _rows_of(site.box())
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert "after Draw" in _rows_of(box)["lot"]
    box.type_address("109 Ithaca Rd, Ithaca, NY")
    rows = _rows_of(box)
    assert (rows["lot"], rows["street"]) == (before["lot"], before["street"])
    box.type_address("")                       # blank: Draw sets the preview aside, so no promise either
    rows = _rows_of(box)
    assert (rows["lot"], rows["street"]) == (before["lot"], before["street"])
    box.typed.clear()
    box.saved["_lookup"] = dict(box.saved["_lookup"], looking="109 Ithaca Rd")
    rows = _rows_of(box)
    assert (rows["lot"], rows["street"]) == (before["lot"], before["street"])


def test_buildings_on_a_sublayer_are_asked_about():
    """P2: own_work found only objects on the exact Building layer: a garage on Building::Garage was never asked
    about, and removed at a reset."""
    site = Site(buildings=True, building_layer="Building::Garage")
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.draw() == "asked-cancel" and box.asked[0][0].endswith("The buildings you drew will be removed.")


def test_a_lookup_that_failed_offline_says_so_never_not_found():
    """P3: after an offline, timeout or error lookup the box said the address "wasn't found", over the real reason.
    Now the lookup's own line says why, and Draw stays off pointing to it."""
    site = Site()
    box = site.box().look_up({"status": "offline", "query": "96 Ithaca Rd"})
    assert box.draw() == "off" and "wasn't found" not in box.said[-1] and "the line above says why" in box.said[-1]
    assert (logic.uncertain(box.shown()) or "").startswith(logic.LOOKUP_SAYS["offline"])


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


def test_an_outside_city_or_ambiguous_lookup_keeps_its_own_words_and_draw_stays_off():
    """Round 2: the lookup's message (the town it is in, the matches) was lost at Draw. It stays the box's line,
    said once, and Draw stays off for that address."""
    site = Site()
    town = "This address is in the Town of Lansing, not the City of Ithaca."
    box = site.box().look_up({"status": "outside_city", "query": "5 Main St, Lansing", "message": town})
    assert box.draw() == "off" and box.draw() == "off"
    assert (logic.uncertain(box.shown()) or "").count(town) == 1
    many = "2 addresses match: 106 Ithaca Rd, 106 Ithaca St."
    box = site.box().look_up({"status": "multiple", "query": "106 Ithaca", "message": many})
    assert box.draw() == "off" and many in (logic.uncertain(box.shown()) or "")


# ---- Undo and Redo of a Draw (the Rhino job at demo e631aae: Redo did nothing, 96's outline stayed on screen) ----

@pytest.mark.parametrize("held, doc, ends", [
    ((7, 12), 7, True),                 # a record this plugin began, in this document
    ((7, 0), 7, False),                 # 0: Rhino said a command was already recording (its record, not ours)
    ((7, 12), 8, False),                # another document's record
    (None, 7, False), ((7, 12), None, False)])
def test_only_an_undo_record_the_plugin_began_is_ended_by_it(held, doc, ends):
    assert logic.undo_record_to_end(held, doc) is ends


@pytest.mark.parametrize("end_undo, end_redo, clears", [(True, False, True), (False, True, True),
                                                         (False, False, False)])
def test_what_was_drawn_is_cleared_when_an_undo_or_redo_ends(end_undo, end_redo, clears):
    assert logic.after_undo_redo(end_undo, end_redo) is clears


def test_an_undo_right_after_a_check_is_still_checked_again():
    """Review round 2 (P1): the handler set dirty to 0.5 s before the Undo ended, so a check that had finished in
    those 0.5 s (a Draw's own, or the re-check after an Undo just before) counted as covering it: no re-check, the
    screen cleared and the panel showing the model before the Undo."""
    checked, undone = 100.0, 100.3
    dirty = logic.dirty_after_undo(None, undone)
    assert logic.should_recheck(dirty, undone + 1.0, False, False, 0.5, last_at=checked)
    assert logic.dirty_after_undo(100.4, undone) == 100.4         # a later edit's time is kept
    assert logic.dirty_after_undo(99.0, undone) == undone


def test_the_plugin_clears_its_drawing_on_undo_and_redo_and_never_changes_the_document_then():
    """After Undo (or Redo) the last check's drawing (the 96 lot outline, its marks) and any dashed lookup outline
    were of a model no longer there: _undo_redo clears them and asks for a re-check, attached to Rhino's own undo
    event when the plugin loads. It never changes the document (a change while Rhino undoes or redoes breaks the
    Undo/Redo chain); the Draw's record is ended only when the plugin began it."""
    rhino = (Path(__file__).resolve().parents[3] / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    body = rhino[rhino.index("def _undo_redo("):].split("\n\n\n", 1)[0]
    code = "\n".join(line for line in body.split('"""')[2].splitlines())       # the code, not its docstring
    assert "logic.after_undo_redo(e.IsEndUndo, e.IsEndRedo)" in code and "_clear(o)" in code
    assert 'STATE.pop("lookup_guide", None)' in code
    assert 'STATE["dirty"] = logic.dirty_after_undo(STATE.get("dirty"), time.time())' in code
    for change in ("doc", "Objects.", "Strings.", "Layers.", "RunScript", "run_check(", "save"):
        assert change not in code, change
    assert '_on(Rhino.Commands.Command, "UndoRedo", _handler(System.EventHandler[Rhino.Commands.UndoRedoEventArgs], ' \
           "_undo_redo," in rhino
    end = rhino[rhino.index("def _end_undo("):].split("\n\n\n", 1)[0]
    assert "if logic.undo_record_to_end(held, " in end and end.index("undo_record_to_end") < end.index("EndUndoRecord")


def test_draw_the_house_again_belongs_to_the_box_that_set_it():
    """P1 (found 2026-10-26 by the progress-cancel job): GordiumCheck's start box, on a Draw of a new address, set
    "draw the house again" and nothing read it; a later Edit site… whose Draw drew nothing new found it set and drew
    a starting house over the architect's model. The flag is now this box's only: every box opens with it cleared,
    only a Draw of a new address sets it, only Edit site… (the box's caller that draws the house) reads it, and
    GordiumCheck drops it with its box."""
    rhino = (Path(__file__).resolve().parents[3] / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    sets = [line.strip() for line in rhino.splitlines() if 'STATE["redraw_house"] =' in line]
    assert sets == ['STATE["redraw_house"] = redraw and mode == "check"     # (GordiumStart draws its house itself)']
    assert 'STATE["redraw_house"] =' in rhino[rhino.index("def _draw_prepare("):rhino.index("def _begin_undo(")]
    confirm = rhino[rhino.index("def confirm("):rhino.index("def _confirm(")]
    assert confirm.index("gate.enter()") < confirm.index('STATE.pop("redraw_house", None)') < \
        confirm.index("result = _confirm(doc, facts, options, mode)")     # cleared as the box opens, before its Draw
    check = rhino[rhino.index("def gordium_check("):rhino.index("# ---- GordiumStart")]
    assert check.index("facts = confirm(") < check.index('STATE.pop("redraw_house", None)') < \
        check.index("if facts is None:")                                    # GordiumCheck: dropped with its box
    readers = [m.start() for m in re.finditer(r'STATE\.(?:pop|get)\("redraw_house"', rhino)]
    edit = (rhino.index("def edit_facts("), rhino.index("def report_path("))
    outside = [rhino.count("\n", 0, i) + 1 for i in readers if not edit[0] < i < edit[1]
               and not rhino.index("def confirm(") < i < rhino.index("def _confirm(")
               and not rhino.index("def gordium_check(") < i < rhino.index("# ---- GordiumStart")
               # (#32: Draw reads it, in its own box, to work out the house it will draw: logic.plans_house)
               and not rhino.index("def _drawn(") < i < rhino.index("def hide_massing(")]
    assert outside == [], outside                                           # read nowhere else


# ---- a new, empty file: an empty box, Draw off until a lookup is found, or the site by hand (Ben, 2026-10-27) ----

def _empty_box(**saved):
    opened = logic.box_opened(saved, {})                      # no lot when the box opened
    state = {"address": "", "zone": None, "district_confirmed": False, "lot_missing": True, "has_lot": False,
             "design_buffer": "0'-0\"", "known_addresses": logic.known_addresses(opened), "lookup": {}}
    return logic.start_gate(state, opened), opened


def test_a_new_file_opens_an_empty_box_and_draw_waits_for_a_found_lookup():
    state, _ = _empty_box()
    assert state["needs_lookup"] and logic.draw_reason(state) == logic.LOOK_UP_FIRST_SITE
    assert logic.LOOK_UP_FIRST_SITE == ("Look up the address first. It finds the lot, zoning district and "
                                        "neighbourhood.")
    rows = {r["key"]: r for r in logic.box_rows(state)}
    assert rows["lot"]["text"] == rows["street"]["text"] == "Look up an address to fill these in"
    assert [a for a, _, _ in rows["lot"]["actions"]] == ["by_hand"]       # never "Draw my lot…" before choosing
    # ticking the district changes nothing: still no Draw without a lookup (never facts the architect didn't choose)
    assert logic.draw_reason(dict(state, zone="R-1b", district_confirmed=True)) == logic.LOOK_UP_FIRST_SITE
    # a found lookup of the address typed: the gate opens (the rest of Draw's rules still apply)
    found, _ = _empty_box(_pending={"address": "106 Ithaca Rd, Ithaca, NY", "query": "106 Ithaca Rd"})
    found = logic.start_gate(dict(found, address="106 Ithaca Rd"), logic.box_opened(
        {"_pending": {"address": "106 Ithaca Rd, Ithaca, NY", "query": "106 Ithaca Rd"}}, {}))
    assert not found["needs_lookup"]
    # another address typed after it: shut again
    other = logic.start_gate(dict(found, address="96 Ithaca Rd"), logic.box_opened(
        {"_pending": {"address": "106 Ithaca Rd, Ithaca, NY", "query": "106 Ithaca Rd"}}, {}))
    assert other["needs_lookup"]


def test_the_site_by_hand_is_the_architects_own_and_says_no_neighbourhood_is_drawn():
    state, _ = _empty_box(_by_hand=True)
    assert state["by_hand"] and not state["needs_lookup"]
    rows = {r["key"]: r for r in logic.box_rows(state)}
    assert "No neighbourhood is drawn" in rows["lot"]["help"]
    assert [a for a, _, _ in rows["lot"]["actions"]] == ["draw_lot"]       # they draw the lot
    typed = dict(state, address="12 New Lot Ln")                           # no lookup possible: a label only
    assert logic.address_reason(typed) == ""
    assert logic.draw_reason(typed) == "Pick the district to continue."   # and then the district, confirmed
    assert logic.draw_reason(dict(typed, zone="R-1b")) == "Confirm the district to continue."
    assert logic.draw_reason(dict(typed, zone="R-1b", district_confirmed=True)) == "Draw or pick the lot to continue."
    assert logic.draw_reason(dict(typed, zone="R-1b", district_confirmed=True, lot_missing=False)) == ""
    assert "_by_hand" not in logic.storable_ui({"_by_hand": True})        # never saved: only while the box is open


def test_a_file_already_drawn_keeps_working_as_before():
    opened = logic.box_opened({"drawn_address": SAMPLE}, {"lot_id": "lot1", "address": SAMPLE})
    state = logic.start_gate({"address": SAMPLE, "zone": "R-1b", "district_confirmed": True, "has_lot": True,
                              "design_buffer": "0'-0\"", "known_addresses": logic.known_addresses(opened)}, opened)
    assert not state["needs_lookup"] and not state["by_hand"] and logic.draw_reason(state) == ""
    # by hand never applies to a drawn file: a new address typed there must still be looked up
    by_hand = logic.start_gate(dict(state, address="96 Ithaca Rd"), dict(opened, _by_hand=True))
    assert not by_hand["by_hand"] and logic.address_reason(by_hand).startswith("Press Look up")


def test_the_plugin_opens_new_files_empty_and_gates_every_box():
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    start = src[src.index("def gordium_start():"):src.index("def _draw_starting_house(")]
    assert "sample_site" not in start and "from_sample=True" not in start
    assert "logic.no_guessed_district({}, suggested_facts(" in start    # no district guessed in an empty file
    assert "sample" not in logic.NO_LOT
    state = src[src.index("def _box_state(doc"):src.index("\n\n\n", src.index("def _box_state(doc"))]
    assert "logic.start_gate(" in state
    assert 'if what == "by_hand":' in src and "logic.choose_by_hand(facts, saved_ui, in_city)" in src


def test_draw_draws_nothing_on_an_empty_file_without_a_found_lookup_whatever_way_it_is_pressed():
    """The scripted way in ticks the district and draws without the box's Draw button (_box_loop's auto path):
    _draw_prepare asks draw_blocked, so it too never draws a site the architect didn't choose."""
    opened = logic.box_opened({}, {})
    state = {"address": "", "zone": "R-1b", "district_confirmed": True, "lot_missing": True}
    assert logic.draw_blocked(state, opened) == logic.LOOK_UP_FIRST_SITE
    assert logic.draw_blocked(dict(state, address="106 Ithaca Rd"), opened).startswith("Press Look up")
    found = dict(opened, _pending={"address": "106 Ithaca Rd, Ithaca, NY", "query": "106 Ithaca Rd"})
    assert logic.draw_blocked(dict(state, address="106 Ithaca Rd"), found) == ""
    assert logic.draw_blocked(state, dict(opened, _by_hand=True)) == ""
    drawn = logic.box_opened({"drawn_address": SAMPLE}, {"lot_id": "lot1", "address": SAMPLE})
    assert logic.draw_blocked(dict(state, address=SAMPLE), drawn) == ""          # a drawn file: as before
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    prep = src[src.index("def _draw_prepare("):src.index("    facts, saved_ui = _apply_box(", src.index("def _draw_prepare("))]
    assert "unlooked = logic.draw_blocked(state, saved_ui)" in prep and "return facts, saved_ui, False, state" in prep


# ---- the offline safety net: the lookup saved on this computer (Ben, 2026-10-27) ----

def _found_106():
    from site_lookup.lookup import lookup
    from test_lookup_box import T
    from design_checker.lookup_box import box_payload
    fx = T.load("106_ithaca_rd")
    return box_payload(lookup(fx["address"], T.Fake(fx), T.NOW), T.NOW)


def test_a_found_lookup_is_saved_only_as_far_as_its_sources_allow_and_never_with_the_district():
    import json
    found = _found_106()
    assert found["status"] == "found" and found["writes"]["lot_ring"] and found["facts"]["zone"]["value"]
    store = logic.save_lookup({}, found, "106 Ithaca Rd")
    copy = store[logic.lookup_key("106 Ithaca Rd")]
    assert "zone" not in copy["facts"]                                # the City's zoning map: used live, never kept
    assert logic.USED_LIVE not in json.dumps(copy["facts"])           # nor any value a source forbids keeping
    district = found["facts"]["zone"]["value"]                        # (the snapshot kept only its marker)
    assert copy["writes"]["snapshot"]["facts"]["zone"]["value"] == logic.USED_LIVE
    assert json.dumps(district) not in json.dumps({k: v for k, v in copy.items() if k != "writes"})
    assert copy["facts"]["lot"]["value"]["area_sf"] == found["facts"]["lot"]["value"]["area_sf"]
    assert copy["writes"]["lot_ring"] == found["writes"]["lot_ring"] and copy["writes"]["guide_ring"] is None
    assert copy["checked"] == found["checked"]
    json.dumps(store)                                                  # a plain file
    # a failure, a guide only (the City's outline: never kept) and a saved copy itself are never saved
    for answer in ({"status": "offline"}, dict(found, writes=dict(found["writes"], lot_ring=None)),
                   logic.as_saved(copy)):
        assert logic.save_lookup({}, answer, "106 Ithaca Rd") == {}


def test_only_a_lookup_that_couldnt_reach_the_services_offers_the_saved_one_for_the_same_address():
    store = logic.save_lookup({}, _found_106(), "106 Ithaca Rd")
    for status in ("offline", "error", "timeout"):
        assert logic.saved_offer({"status": status}, store, "106 ithaca road, Ithaca NY") is not None, status
    for status in ("not_found", "outside_city", "multiple", "found"):   # an answer is an answer: never replaced
        assert logic.saved_offer({"status": status}, store, "106 Ithaca Rd") is None, status
    assert logic.saved_offer({"status": "offline"}, store, "96 Ithaca Rd") is None       # another address
    assert logic.saved_offer({"status": "offline"}, store, "") is None


def test_the_saved_lookup_is_marked_with_its_date_and_the_district_is_picked_again():
    found = _found_106()
    copy = logic.save_lookup({}, found, "106 Ithaca Rd")[logic.lookup_key("106 Ithaca Rd")]
    date = copy["checked"]
    # offline: the box says so and offers it (the Address row's button)
    facts, saved, _ = logic.preview_lookup({"status": "offline", "query": "106 Ithaca Rd"}, {"address": "106 Ithaca Rd"},
                                           logic.box_opened({}, {}), ZONES)
    saved["_lookup"] = dict(saved["_lookup"], saved_offer=date, saved_for="106 Ithaca Rd")
    rows = {r["key"]: r for r in logic.box_rows({"address": "106 Ithaca Rd", "lookup": saved["_lookup"]})}
    assert ("use_saved", "Use the lookup saved on " + date, True) in rows["address"]["actions"]
    retyped = {r["key"]: r for r in logic.box_rows({"address": "96 Ithaca Rd", "lookup": saved["_lookup"]})}
    assert [a for a, _, _ in retyped["address"]["actions"]] == ["lookup"]     # round 6: no button that does nothing
    # used: shown like a lookup, every label and the line marked with the date; no district suggested
    facts, saved, ring = logic.preview_lookup(logic.use_saved(copy, "106 Ithaca Rd", "106 Ithaca Rd"), facts, saved,
                                              ZONES)
    assert ring == found["writes"]["lot_ring"]
    assert saved["_lookup"]["says"] == logic.SAVED_SAYS.format(address=facts.get("address") or "106 Ithaca Rd",
                                                               date=date)
    assert "saved on " + date in saved["_lookup"]["says"] and "pick the district again" in saved["_lookup"]["says"]
    assert not facts.get("zone")
    labels = saved["_pending"]["answer"]["labels"]
    assert labels and all(v.endswith(" · saved on " + date) for v in labels.values())
    gate = logic.start_gate({"address": "106 Ithaca Rd"}, saved)
    assert not gate["needs_lookup"]                                  # it opens Draw's gate…
    assert logic.draw_reason(dict(gate, zone=None, district_confirmed=False, has_lot=True)) == \
        "Pick the district to continue."                             # …but the district is the architect's to pick


def test_the_plugin_saves_found_lookups_and_offers_the_saved_one_only_when_offline():
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    done = src[src.index("def _lookup_done("):src.index("def _saved_lookups_path(")]
    assert "_saved_lookup, " in done and "saved_offer=offer.get(\"checked\"), saved_for=asked" in done
    saved = src[src.index("def _saved_lookup("):src.index("def _show_answer(")]
    assert "logic.save_lookup(store, answer, asked)" in saved and "logic.saved_offer(answer, store, asked)" in saved
    pick = src[src.index("def _one_pick("):src.index("def _pick_outcome(")]
    assert 'logic.guard(logic.use_saved, "use the saved lookup")(' in pick
    assert 'not STATE.get("lookup_fixture")' in saved and "readable" in saved and "os.getpid()" in saved
    assert "ticked = logic.ticks_after_pick(what, ticked, " in src    # the ticks go, as for any lookup's answer
    assert logic.ticks_after_pick("pick:use_saved", {"district_confirmed": True}, "found") == {
        "district_confirmed": False}


def test_a_saved_lookup_is_never_used_for_another_address_or_another_town():
    """Start-flow sceptic 1: (1) offline at 106, the address retyped to 96, then Use saved: 106's lot went in under
    "96 Ithaca Rd" as if 96 had been looked up; (2) the key is the street address alone, so "106 Ithaca Rd, Lansing"
    was offered the City's 106."""
    found = _found_106()
    store = logic.save_lookup({}, found, "106 Ithaca Rd")
    copy = store[logic.lookup_key("106 Ithaca Rd")]
    assert logic.use_saved(copy, "106 Ithaca Rd", "96 Ithaca Rd") is None                  # retyped: dropped
    answer = logic.use_saved(copy, "106 Ithaca Rd", "106 Ithaca Road")
    assert answer and answer["query"] == copy["query"]                                     # its own query
    facts, saved, _ = logic.preview_lookup(answer, {"address": "106 Ithaca Rd"}, logic.box_opened({}, {}), ZONES)
    assert logic.draw_blocked({"address": "96 Ithaca Rd"}, saved) != ""                     # 96 never looked up
    for other in ("106 Ithaca Rd, Lansing, NY 14882", "106 Ithaca Rd, Town of Ithaca"):
        assert logic.saved_offer({"status": "offline"}, store, other) is None, other
    assert logic.saved_offer({"status": "offline"}, store, "106 Ithaca Rd, Ithaca, NY 14850") is copy


def test_edit_site_on_a_drawn_file_whose_lot_is_gone_is_not_a_new_file():
    """Sceptic 1 (P2): the gate is for a new file only; a drawn file (its address saved) with its lot curve deleted
    keeps "Draw my lot…"."""
    opened = logic.box_opened({}, {"address": SAMPLE})
    state = logic.start_gate({"address": SAMPLE, "lot_missing": True}, opened)
    assert not state["needs_lookup"]
    rows = {r["key"]: r for r in logic.box_rows(state)}
    assert "draw_lot" in [a for a, _, _ in rows["lot"]["actions"]]


def test_sceptic_2_an_outline_only_lookup_and_by_hand_never_skip_the_address_rule():
    """(1) A new file whose lookup found only the City's outline: Draw cleared for it and kept the box open to draw
    the lot over it; the gate shut again (the preview gone) and offered only "by hand". (2) By hand, then a lookup
    of the City's 106 found, then "106 Ithaca Rd, Lansing" typed: Draw went on with the City's lot."""
    opened = logic.box_opened({}, {})
    after_reset = dict(opened, _redrawn_for="106 Ithaca Road, Ithaca, NY, 14850",
                       drawn_address="106 Ithaca Road, Ithaca, NY, 14850")
    state = logic.start_gate({"address": "106 Ithaca Road, Ithaca, NY, 14850", "lot_missing": True}, after_reset)
    assert not state["needs_lookup"]
    assert "draw_lot" in [a for a, _, _ in {r["key"]: r for r in logic.box_rows(state)}["lot"]["actions"]]
    pending = {"address": "106 Ithaca Road, Ithaca, NY, 14850", "query": "106 Ithaca Rd, Ithaca, NY 14850"}
    by_hand = dict(opened, _by_hand=True, _pending=pending)
    lansing = {"address": "106 Ithaca Rd, Lansing, NY", "zone": "R-1b", "district_confirmed": True,
               "lot_missing": False, "has_lot": True}
    assert logic.draw_blocked(lansing, by_hand) != ""
    facts, saved = logic.settle_pending({"address": lansing["address"]}, by_hand, lansing["address"])
    assert saved.get("_pending") is None                                    # another town's: the preview dropped


def test_by_hand_chosen_after_a_found_lookup_works():
    """Round 3: by hand, a found lookup, another address typed: the by-hand button showed again and did nothing."""
    opened = logic.box_opened({}, {})
    found = dict(opened, _by_hand=True, _pending={"address": "106 Ithaca Road, Ithaca, NY, 14850",
                                                  "query": "106 Ithaca Rd", "undo": []})
    assert logic.start_gate({"address": "5 Other St"}, found)["needs_lookup"]
    facts, saved = logic.choose_by_hand({"address": "5 Other St"}, found, "2026-10-27")
    state = logic.start_gate({"address": "5 Other St"}, saved)
    assert state["by_hand"] and not state["needs_lookup"] and "_pending" not in saved
    assert logic.draw_blocked(dict(state, zone="R-1b", district_confirmed=True, lot_missing=False), saved) == ""


def test_by_hand_asks_for_the_district_tick_again():
    """Round 4: the box loop's ticks carried across picks; by hand undid the lookup's district (back to the one
    picked before), so the tick given to the lookup's district moved onto it and Draw went on."""
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    loop = src[src.index("def _box_loop("):src.index("\n\n\n", src.index("def _box_loop("))]
    reset = loop[loop.index('if (what == "pick:by_hand" and saved_ui.get("_by_hand")'):]
    assert "(not was_by_hand or (had_pending and not saved_ui.get(\"_pending\")))):" in reset.split("\n", 2)[1]
    assert reset.split("\n", 3)[2].strip().startswith("ticked = {}")      # (round 12: only once by hand is taken)
    assert loop.index('was_by_hand, had_pending = saved_ui.get("_by_hand"), saved_ui.get("_pending")') < \
        loop.index("_box_pick(doc, what.split")
    pick = src[src.index("def _one_pick("):src.index("def _pick_outcome(")]
    assert pick.index("_lookup_stop()") < pick.index("logic.choose_by_hand(facts, saved_ui, in_city)")


def test_round_5_by_hand_is_for_city_of_ithaca_lots_only():
    """By hand skipped the town check, and choose_by_hand wiped an "outside the City" answer: a Lansing lot could be
    drawn and checked under the City's rules."""
    opened = logic.box_opened({}, {})
    lansing = {"address": "106 Ithaca Rd, Lansing, NY"}
    assert logic.draw_blocked(lansing, dict(opened, _by_hand=True)) == \
        logic.BY_HAND_CITY_ONLY.format(address=lansing["address"])
    _, outside = logic.lookup_choices({"status": "outside_city", "query": "953 Danby Rd, Ithaca, NY"}, {}, opened)
    _, by_hand = logic.choose_by_hand({}, outside, "2026-10-27")
    assert logic.draw_blocked({"address": "953 Danby Rd, Ithaca, NY"}, by_hand) != ""
    assert logic.draw_blocked({"address": "12 New Lot Ln, Ithaca, NY 14850"}, dict(opened, _by_hand=True)) == ""
    assert logic.draw_blocked({"address": "12 New Lot Ln"}, by_hand) != ""   # round 12: refused, whatever address


def test_round_9_by_hand_reads_the_town_of_an_address_typed_without_commas():
    """Round 9: address_place read only after a comma, so "12 Main St Lansing NY 14882" passed as a City lot."""
    opened = dict(logic.box_opened({}, {}), _by_hand=True)
    for other in ("12 Main St Lansing NY 14882", "106 Ithaca Rd Dryden NY", "12 Main St 14882"):
        assert logic.draw_blocked({"address": other}, opened) == logic.BY_HAND_CITY_ONLY.format(address=other)
    for city in ("106 Ithaca Rd", "106 Ithaca Rd Ithaca NY 14850", "106 Ithaca Road NY", "204 Utica St"):
        assert logic.draw_blocked({"address": city}, opened) == ""
    assert not logic.same_site_address("106 Ithaca Rd Dryden NY", "106 Ithaca Road, Ithaca, NY, 14850")
    assert logic.same_site_address("106 Ithaca Rd Ithaca NY 14850", "106 Ithaca Road, Ithaca, NY, 14850")


def test_round_10_the_town_after_the_street_is_read_whatever_the_ending():
    """Round 10: the Town of Ithaca read as the City, a town with no state typed passed, and "Way" read as a town."""
    opened = dict(logic.box_opened({}, {}), _by_hand=True)
    for other in ("12 Main St Town of Ithaca NY", "12 Main St Town of Ithaca NY 14850", "12 Main St Lansing",
                  "12 Main St East Ithaca NY", "12 Main St Cayuga Heights NY", "12 Main St, Town of Ithaca, NY"):
        assert logic.draw_blocked({"address": other}, opened) == logic.BY_HAND_CITY_ONLY.format(address=other)
    for city in ("1 Willard Way NY 14850", "1 Willard Way", "100 Aurora St N", "100 E State St Ithaca",
                 "10 Rte 13 Ithaca NY", "100 Broadway Ithaca NY"):
        assert logic.draw_blocked({"address": city}, opened) == "", city
    assert logic.same_site_address("1 Willard Way NY 14850", "1 Willard Way, Ithaca, NY, 14850")


def test_round_11_by_hand_needs_the_architects_word_that_the_lot_is_the_citys():
    """Round 11: "1 Pine Tree Rd Ithaca NY 14850" is the Town's, yet by hand took it: the City's mail name and ZIP
    also cover the Town, so the architect says Yes to IN_CITY_QUESTION, kept with its date; No changes nothing."""
    opened = logic.box_opened({}, {})
    facts, saved = logic.choose_by_hand({}, dict(opened), None)                  # No: still gated on a lookup
    assert "_by_hand" not in saved and logic.draw_blocked({}, saved) == logic.LOOK_UP_FIRST_SITE
    facts, saved = logic.choose_by_hand({}, dict(opened), "2026-10-27")
    assert saved["city_by_hand"] == "2026-10-27" and "city_by_hand" in logic.storable_ui(saved)
    assert logic.draw_blocked({}, saved) == ""
    state = logic.start_gate({"address": ""}, saved)
    assert state["by_hand"] and state["city_by_hand"] == "2026-10-27"
    assert "Town of Ithaca" in logic.IN_CITY_QUESTION and "No: nothing changes" in logic.IN_CITY_QUESTION
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    pick = src[src.index("def _one_pick("):src.index("def _pick_outcome(")]
    assert pick.index("_ask_in_city()") < pick.index("logic.choose_by_hand(facts, saved_ui, in_city)")
    assert "MessageBoxDefaultButton.No" in src[src.index("def _ask_in_city("):]


def test_round_11_units_a_run_on_zip_and_a_town_after_a_street_with_no_ending():
    opened = dict(logic.box_opened({}, {}), _by_hand=True)
    for other in ("1 Snyder Hill Dryden", "1 Sapsucker Woods Lansing", "1 Lake Ridge Lansing",
                  "1 Eastern Heights Dryden", "1 Main Rdg Lansing"):
        assert logic.draw_blocked({"address": other}, opened) == logic.BY_HAND_CITY_ONLY.format(address=other)
    for city in ("1 Oak Ave Apt 2", "12 Cascadilla St Unit B Ithaca", "1 Mitchell St Ithaca NY14850",
                 "12 Oak Ave, Apt 2, Ithaca, NY", "100 Dryden Rd", "12 Oak Ave #3"):
        assert logic.draw_blocked({"address": city}, opened) == "", city


def test_round_12_outside_the_city_refuses_by_hand_whatever_the_address():
    """Round 12: after the lookup said outside the City, a Yes then a cleared or retyped address opened Draw."""
    opened = logic.box_opened({}, {})
    _, outside = logic.lookup_choices({"status": "outside_city", "query": "12 Main St, Lansing"}, {}, opened)
    assert logic.by_hand_refused(outside) == logic.BY_HAND_OUTSIDE.format(query="12 Main St, Lansing")
    _, saved = logic.choose_by_hand({}, dict(outside), "2026-10-27")
    assert "_by_hand" not in saved and "city_by_hand" not in saved
    later = dict(opened, _by_hand=True, city_by_hand="2026-10-27")             # a Yes, then a lookup said outside
    _, later = logic.lookup_choices({"status": "outside_city", "query": "14 Main St"}, {}, later)
    for address in ("", "12 Main St", "14 Main St"):
        assert logic.draw_blocked({"address": address}, later) == logic.BY_HAND_OUTSIDE.format(query="14 Main St")
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    pick = src[src.index("def _one_pick("):src.index("def _pick_outcome(")]
    assert "in_city = None if refused else _ask_in_city()" in pick


def test_round_12_the_yes_is_shown_and_kept_once_on_the_address_source():
    state = logic.start_gate({"address": "12 New Lot Ln", "has_lot": True}, {"city_by_hand": "2026-10-27"})
    assert state["city_by_hand"] == "2026-10-27"                               # shown after the lot is drawn too
    said = logic.IN_CITY_SAID.format(date="2026-10-27")
    first = logic.fact_sources(dict(state, address_source=logic.ENTERED), "2026-10-27", True)["address"]["source"]
    assert first == logic.ENTERED + " · " + said
    again = logic.fact_sources(dict(state, address_source=first), "2026-10-28", True)["address"]["source"]
    assert again == first                                                      # read back at the next Draw: once
    assert logic.fact_sources(dict(state, city_by_hand=None, address_source=logic.ENTERED), "x", True)[
        "address"]["source"] == logic.ENTERED


def test_round_13_outside_the_city_outlives_a_later_lookup_that_finds_nothing():
    """Round 13: outside the City, then an offline or not-found lookup, and by hand opened Draw on that lot."""
    opened = logic.box_opened({}, {})
    _, saved = logic.lookup_choices({"status": "outside_city", "query": "100 Snyder Hill Rd"}, {}, opened)
    for then in ("offline", "not_found", "error", "multiple"):
        _, later = logic.lookup_choices({"status": then, "query": "100 Snyder Hill Rd"}, {}, dict(saved))
        assert logic.by_hand_refused(later)
        _, tried = logic.choose_by_hand({}, dict(later), "2026-10-27")
        assert "_by_hand" not in tried
    _, found = logic.lookup_choices({"status": "found", "query": "100 Snyder Hill Rd"}, {}, dict(saved))
    assert not logic.by_hand_refused(found)                     # a found lookup of that address ends it (round 14)


def test_round_13_a_drawn_lot_the_lookup_says_is_outside_is_not_drawn_again():
    """Round 13: a by-hand lot (its Yes kept), reopened and looked up outside the City: Draw went on."""
    facts = {"lot_id": "L", "address": "100 Snyder Hill Rd, Ithaca, NY 14850"}
    opened = logic.box_opened({"city_by_hand": "2026-10-27"}, facts)
    _, saved = logic.lookup_choices({"status": "outside_city", "query": facts["address"]}, facts, opened)
    assert saved["city_by_hand"] == "2026-10-27"                               # the Yes kept, as said
    assert logic.draw_blocked({"address": facts["address"]}, saved) == logic.BY_HAND_OUTSIDE.format(
        query=facts["address"])


def test_round_13_parts_of_a_lot_units_and_the_county_are_not_towns():
    opened = dict(logic.box_opened({}, {}), _by_hand=True)
    for city in ("101 N Aurora St Rear", "10 Cayuga St Bldg 2", "100 Cornell St 2nd Fl", "10 Cayuga St B",
                 "1 Esty St 1/2", "10 Cayuga St - Ithaca", "10 Brindley St Lower",
                 "10 Cayuga St Ithaca Tompkins County NY", "10 Cayuga St, Ithaca, Tompkins County, NY"):
        assert logic.draw_blocked({"address": city}, opened) == "", city
    assert logic.address_place("12 Main St Lansing NY 14882") == "lansing 14882"


def test_round_14_the_lots_own_address_said_outside_blocks_draw_whatever_is_typed():
    facts = {"lot_id": "L", "address": "106 Ithaca Rd"}
    opened = logic.box_opened({}, facts)
    _, saved = logic.lookup_choices({"status": "outside_city", "query": "106 Ithaca Rd"}, facts, opened)
    for typed in ("", "106 Ithaca Rd", "106 Ithaca Rd, Ithaca, NY, 14850"):
        assert logic.draw_blocked({"address": typed}, saved) == logic.BY_HAND_OUTSIDE.format(query="106 Ithaca Rd")


def test_round_14_a_found_lookup_of_another_address_keeps_outside_the_city():
    opened = logic.box_opened({}, {})
    _, saved = logic.lookup_choices({"status": "outside_city", "query": "5 Foo Rd"}, {}, opened)
    _, saved = logic.lookup_choices({"status": "found", "query": "106 Ithaca Rd"}, {}, saved)
    assert saved["_outside_for"] == ["5 Foo Rd"] and logic.by_hand_refused(saved)
    assert logic.draw_blocked({"address": "5 Foo Rd"}, saved) == logic.BY_HAND_OUTSIDE.format(query="5 Foo Rd")
    _, saved = logic.lookup_choices({"status": "found", "query": "5 Foo Rd"}, {}, saved)   # found: that one ends
    assert saved["_outside_for"] == [] and not logic.by_hand_refused(saved)


def test_round_14_the_old_lots_yes_is_never_on_the_lot_drawn_in_its_place():
    shown = {"city_by_hand": "2026-10-01", "address": "12 Old Ln", "address_source": logic.ENTERED}
    fresh = {"address": "106 Ithaca Rd", "address_source": "City geocoder"}
    state = logic.after_reset_state(shown, fresh)
    assert logic.fact_sources(state, "2026-10-27", True)["address"]["source"] == "City geocoder"


def test_round_15_a_saved_lookup_never_lifts_a_live_outside_the_city():
    opened = logic.box_opened({}, {})
    _, saved = logic.lookup_choices({"status": "outside_city", "query": "106 Ithaca Rd"}, {}, opened)
    copy = logic.as_saved({"status": "found", "query": "106 Ithaca Rd", "checked": "2026-10-20", "labels": {}})
    _, used = logic.lookup_choices(copy, {}, saved)
    assert used["_outside_for"] == ["106 Ithaca Rd"]
    assert logic.draw_blocked({"address": "106 Ithaca Rd"}, used) == logic.BY_HAND_OUTSIDE.format(
        query="106 Ithaca Rd")
    _, live = logic.lookup_choices({"status": "found", "query": "106 Ithaca Rd"}, {}, used)
    assert live["_outside_for"] == []                                           # a live found one ends it


def test_round_16_a_preview_set_aside_never_brings_back_an_outside_address_found_since():
    opened = logic.box_opened({}, {})
    _, saved = logic.lookup_choices({"status": "outside_city", "query": "12 Main St"}, {}, opened)
    facts, saved, _ = logic.preview_lookup({"status": "found", "query": "12 Main St", "facts": {}}, {}, saved)
    assert saved["_outside_for"] == []
    facts, later, _ = logic.preview_lookup({"status": "not_found", "query": "9 Other St"}, facts, dict(saved))
    assert later["_outside_for"] == [] and not logic.by_hand_refused(later)
    _, by_hand = logic.choose_by_hand(facts, dict(saved), "2026-10-27")
    assert by_hand.get("_by_hand") and logic.draw_blocked({"address": "12 Main St"}, by_hand) == ""


def test_round_16_no_or_refused_over_a_preview_changes_nothing():
    opened = logic.box_opened({}, {})
    facts, saved, _ = logic.preview_lookup({"status": "found", "query": "106 Ithaca Rd", "facts": {}}, {}, opened)
    assert saved.get("_pending")
    assert logic.choose_by_hand(facts, dict(saved), None) == (facts, saved)           # No
    _, outside = logic.lookup_choices({"status": "outside_city", "query": "5 Foo Rd"}, facts, dict(saved))
    outside["_pending"] = saved["_pending"]
    assert logic.choose_by_hand(facts, dict(outside), "2026-10-27") == (facts, outside)   # refused


def test_round_9_a_saved_source_never_says_used_live():
    saved = logic.as_saved({"checked": "2026-10-27", "labels": {"street_side": "City of Ithaca roads, used live"}})
    assert saved["labels"]["street_side"] == "City of Ithaca roads" + logic.SAVED_ON.format(date="2026-10-27")


def test_round_5_a_saved_lookup_is_filed_under_the_address_found_too():
    found = _found_106()
    assert logic.found_address(found) == "106 Ithaca Road, Ithaca, NY, 14850"
    store = logic.save_lookup({}, dict(found, query="106 ithaca"), "106 ithaca")
    assert logic.saved_offer({"status": "offline"}, store, "106 Ithaca Rd") is not None


def test_round_5_no_district_is_guessed_for_a_file_with_no_site_in_edit_site_either():
    suggested = {"zone": "R-1a", "use": "one_family_detached"}
    assert logic.no_guessed_district({}, suggested)["zone"] is None
    assert logic.no_guessed_district({"address": SAMPLE}, suggested)["zone"] == "R-1a"     # a site: as before
    assert logic.no_guessed_district({}, dict(suggested, lot_id="lot1"))["zone"] == "R-1a"  # a lot drawn: as before
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    edit = src[src.index("def edit_facts("):src.index("\n\n\n", src.index("def edit_facts("))]
    assert "logic.no_guessed_district(" in edit
    assert "logic.no_guessed_district({}, suggested_facts(" in src[src.index("def gordium_start("):]


def test_round_6_a_saved_lookups_front_line_keeps_its_source_and_date():
    """The saved copy keeps the street line but not the street side's value (used live): the front line row lost
    its source, and its "saved on" date."""
    found = _found_106()
    copy = logic.save_lookup({}, found, "106 Ithaca Rd")[logic.lookup_key("106 Ithaca Rd")]
    facts, saved = logic.lookup_choices(logic.use_saved(copy, "106 Ithaca Rd", "106 Ithaca Rd"), {}, {}, ZONES)
    assert copy["writes"]["street_line"]                                 # the line is kept (and drawn at Draw)
    assert saved.get("street_source", "").startswith(logic.SUGGESTED + " · ")
    assert saved["street_source"].endswith(" · saved on " + copy["checked"])


def test_round_6_a_stale_use_saved_button_says_why_it_did_nothing():
    look = logic.saved_refused({"status": "offline", "saved_offer": "2026-10-20"}, "106 Ithaca Rd", "96 Ithaca Rd")
    assert look["saved_offer"] is None
    assert look["says"] == "The saved lookup is 106 Ithaca Rd's, not 96 Ithaca Rd's: press Look up to find 96 Ithaca Rd."
    rows = {r["key"]: r for r in logic.box_rows({"address": "96 Ithaca Rd", "lookup": look})}
    assert [a for a, _, _ in rows["address"]["actions"]] == ["lookup"]
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert 'logic.saved_refused(saved_ui.get("_lookup"), offered_for, facts.get("address"))' in src


def test_round_7_a_saved_lookup_is_never_more_certain_than_the_live_one():
    """P0, a false pass (round 7, cold reviewer + 2 sceptics): the State and County placed 106 Ithaca Rd 200 ft
    apart, so the live lookup keeps the lot and street in doubt (their rows NEEDS REVIEW). The saved copy kept the
    statuses but not the reason (the County's, not keepable), and a doubt needed a reason: offline the lot came back
    certain, and Lot width, Front yard and Building height COMPLIED once the corner was answered."""
    from test_lookup_box import T, looked_up

    class Table:
        n = 0

        def add_lot(self, ring, name):
            Table.n += 1
            return "lot%d" % Table.n

        def add_spot(self, p):
            return "s"

        def ground_points(self):
            return []

    class Session:
        def hold(self, x):
            pass

        def add(self, x):
            pass

    fx = T.load("106_ithaca_rd")
    pt = next(a for a in fx["answers"] if a["source"] == "geocoder")["body"]["candidates"][0]["location"]
    live = looked_up("106_ithaca_rd", county=(pt["x"] + 200, pt["y"]))
    store = logic.save_lookup({}, dict(live, checked="2026-10-27"), "106 Ithaca Rd")
    saved = logic.use_saved(logic.saved_offer({"status": "offline"}, store, "106 Ithaca Rd"), "106 Ithaca Rd",
                            "106 Ithaca Rd")
    unsettled = {}
    for tag, answer in (("live", live), ("saved", saved)):
        f0, s0, _ = logic.preview_lookup(answer, {"address": "106 Ithaca Rd"}, logic.box_opened({}, {}), ZONES)
        _, s, _ = logic.apply_lookup(Table(), Session(), s0["_pending"]["answer"], f0, s0, ZONES)
        unsettled[tag] = set(logic.unsettled(s))
    assert unsettled["live"] >= {"lot", "street"}
    assert unsettled["saved"] >= unsettled["live"]


def test_round_8_a_saved_lookups_district_and_overlay_lines_say_what_happened():
    """Offline the zone row said the City map "gave no district for this lot" (it was never asked) and ran on into
    an overlay doubt that didn't say it was about overlays."""
    from test_lookup_box import looked_up
    live = looked_up("106_ithaca_rd", historic=("East Hill",))
    copy = logic.save_lookup({}, dict(live, checked="2026-10-27"), "106 Ithaca Rd")[logic.lookup_key("106 Ithaca Rd")]
    facts, saved, _ = logic.preview_lookup(logic.use_saved(copy, "106 Ithaca Rd", "106 Ithaca Rd"),
                                           {"address": "106 Ithaca Rd"}, logic.box_opened({}, {}), ZONES)
    assert saved["_live"]["zone"] == logic.SAVED_NO_DISTRICT
    assert saved["_live"]["overlays"] == logic.OVERLAYS_NOT_KEPT
    assert logic.NO_DISTRICT.endswith(".")


# ---- UX walkthrough 2026-10-28: the Corner lot? answer the box shows is the one Draw saves ---------------------

OTHER = "200 Elm St, Ithaca, NY"           # a drawn lot that is not the address looked up: Draw draws the new one


def test_after_look_up_the_box_shows_the_lookups_corner_answer_and_no_longer_asks_it():
    """Rhino, demo baadaa38: after Look up the box still said "Corner lot? Not answered" and asked "Does this lot
    face two streets?", while Draw then saved the lookup's "no" as "confirmed by you". The box shows the answer
    Draw will save, credited to the street service, for the architect to keep or change."""
    for name, expected in (("106_ithaca_rd", False), ("96_ithaca_rd", True)):
        box = Site(drawn=OTHER).box().look_up(answer(name))
        shown = box.shown()
        assert shown["corner_lot"] is expected, name
        assert shown["corner_source"].startswith(logic.SUGGESTED + " · "), name
        assert "Does this lot face two streets?" not in (logic.uncertain(shown) or ""), name


def test_p0_a_corner_answer_changed_after_look_up_is_the_one_draw_saves():
    """P0, a false pass (Rhino, demo baadaa38, 2026-10-28): Look up 106 Ithaca Rd (one street found), Corner lot? =
    Yes, Draw: the lookup's "no" was saved ("confirmed by you"), so a corner lot's second street was held to a side
    yard's limit instead of a front yard's. The architect's answer is kept, and the street lines are picked again
    (a corner lot's streets: corner_answered)."""
    site = Site(drawn=OTHER)
    box = site.box().look_up(answer("106_ithaca_rd"))
    box.typed.update(corner_lot=True, corner_source=logic.ENTERED)
    assert box.draw() == "drawn"
    assert site.facts["corner_lot"] is True and not site.facts.get("street_line")
    assert site.sources["corner_lot"]["value"] == "yes, two streets"
    assert site.sources["corner_lot"]["source"] == logic.ENTERED
    # the other way: two streets found, the architect says one (theirs to say: entered by them)
    site = Site(drawn=OTHER)
    box = site.box().look_up(answer("96_ithaca_rd"))
    box.typed.update(corner_lot=False, corner_source=logic.ENTERED)
    assert box.draw() == "drawn" and site.facts["corner_lot"] is False
    assert site.sources["corner_lot"]["source"] == logic.ENTERED
    # put back to Not answered on purpose: saved unanswered (the yards wait for it), never the lookup's "no"
    site = Site(drawn=OTHER)
    box = site.box().look_up(answer("106_ithaca_rd"))
    box.typed.update(corner_lot=None, corner_source=logic.ENTERED)
    assert box.draw() == "drawn" and site.facts.get("corner_lot") is None
    # left as the lookup showed it: the lookup's answer and source, as before
    site = Site(drawn=OTHER)
    assert site.box().look_up(answer("106_ithaca_rd")).draw() == "drawn"
    assert site.facts["corner_lot"] is False and site.facts.get("street_line")
    assert site.sources["corner_lot"]["source"].startswith(logic.SUGGESTED + " · ")


def test_an_answer_given_before_look_up_never_rides_onto_the_new_lot():
    """Re-lookup review round 1 (P0) still holds: the drawn lot's corner answer, even one the architect changed in
    this box before pressing Look up, is replaced by the new lot's shown answer when the lookup comes back."""
    site = Site(drawn=OTHER)                                    # drawn: not a corner lot
    box = site.box()
    box.typed.update(corner_lot=False, corner_source=logic.ENTERED)
    box.look_up(answer("96_ithaca_rd"))                         # two streets found
    assert box.shown()["corner_lot"] is True
    assert box.draw() == "drawn" and site.facts["corner_lot"] is True


def test_a_dropped_preview_puts_the_drawn_lots_corner_answer_back():
    site = Site(drawn=OTHER)
    box = site.box().look_up(answer("96_ithaca_rd"))
    assert box.facts["corner_lot"] is True
    assert box.type_address(OTHER).draw() == "box-again"        # the drawn address typed back: preview set aside
    assert box.facts["corner_lot"] is False and box.saved.get("corner_source") == site.saved.get("corner_source")


def test_p0_in_an_empty_file_too_the_corner_answer_after_look_up_is_kept():
    """The Rhino run's own path: a new, empty file (no lot), Look up, Corner lot? = Yes, Draw."""
    facts, saved, _ = logic.preview_lookup(answer("106_ithaca_rd"), {"address": "106 Ithaca Rd"},
                                           logic.box_opened({}, {}), ZONES)
    assert facts["corner_lot"] is False                          # shown: the lookup's one street
    state = {"address": facts["address"], "zone": facts.get("zone"), "use": "one_family_detached",
             "corner_lot": True, "corner_source": logic.ENTERED}
    facts, saved = logic.box_facts(facts, saved, state)
    saved = logic.saved_sources(saved, state)
    table = FakeTable({})
    facts, saved, _, _ = logic.apply_reset(table, logic.BoxSession(table), facts, saved, logic.START_FRESH, ZONES)
    assert facts["corner_lot"] is True and saved["corner_source"] == logic.ENTERED


def _drawn_corner_lot(address=OTHER):
    """A drawn corner lot the architect answered Yes for, both streets picked."""
    site = Site(drawn=address)
    site.facts.update(corner_lot=True, street_line=[[[0, 0], [60, 0]], [[60, 0], [60, 100]]])
    site.saved["corner_source"] = logic.ENTERED
    return site


def test_review_f1_a_re_lookup_of_the_drawn_address_keeps_the_architects_corner_answer():
    """Review round 1 of the corner fix, F1 (P0): looking up the address already drawn draws nothing new (reset_plan
    "none"), so the lookup's corner answer must not be shown or saved over the architect's Yes on that lot."""
    a = answer("106_ithaca_rd")                               # the lookup finds one street
    site = _drawn_corner_lot(a["facts"]["address"]["value"])
    box = site.box().look_up(a)
    assert box.shown()["corner_lot"] is True and box.shown()["corner_source"] == logic.ENTERED
    assert box.draw() == "drawn"
    assert site.facts["corner_lot"] is True and len(site.facts["street_line"]) == 2
    assert site.sources["corner_lot"]["source"] == logic.ENTERED


def test_review_f2_an_answer_given_for_a_dropped_preview_never_stays_on_the_drawn_lot():
    """Review round 1 of the corner fix, F2 (P1): No picked while 96 Ithaca Rd's lot was previewed, then the drawn
    address typed back (the preview set aside): the drawn corner lot keeps its own Yes and both its streets."""
    site = _drawn_corner_lot()
    box = site.box().look_up(answer("96_ithaca_rd"))
    box.typed.update(corner_lot=False, corner_source=logic.ENTERED)
    box._apply()                                              # e.g. a pick while the preview shows
    assert len(box.facts["street_line"]) == 2                 # the drawn lot's streets untouched meanwhile
    assert box.type_address(OTHER).draw() == "box-again"
    assert box.facts["corner_lot"] is True and box.saved["corner_source"] == logic.ENTERED
    assert box.draw() == "drawn"
    assert site.facts["corner_lot"] is True and len(site.facts["street_line"]) == 2
    # the same when the preview's answer equals the drawn lot's (nothing for the preview's undo to record)
    p = answer("96_ithaca_rd")                                # two streets: Yes, as drawn
    site = _drawn_corner_lot()
    box = site.box().look_up(p)
    assert box.shown()["corner_lot"] is True
    box.typed.update(corner_lot=False, corner_source=logic.ENTERED)
    box._apply()
    assert box.type_address(OTHER).draw() == "box-again" and box.facts["corner_lot"] is True


def test_review_r2_street_lines_picked_under_a_dropped_previews_answer_go_back_with_it():
    """Review round 2 of the corner fix, F1 (P2): a drawn lot that is not a corner lot; 96 Ithaca Rd looked up (two
    streets: shown Yes); Change… on the drawn lot's Front lot line picks two streets under that Yes; the drawn
    address typed back: the drawn lot gets its No back, and its one street line with it (never a lot answered No
    with two streets' lines). A pick under the drawn lot's own answer is kept."""
    one = [[[0, 0], [60, 0]]]
    two = {"lines": [[[0, 0], [60, 0]], [[60, 0], [60, 100]]], "ids": ["Street 1", "Street 2"], "name": None}
    site = Site(drawn=OTHER)
    box = site.box().look_up(answer("96_ithaca_rd"))
    box._apply()                                              # Change… on the Front lot line: _apply_box, then
    assert box.facts["corner_lot"] is True                    # the pick, in corner mode
    box.facts, box.saved = logic.pick_effect("street", two, box.facts, box.saved)
    assert box.type_address(OTHER).draw() == "box-again"
    assert box.facts["corner_lot"] is False and box.facts["street_line"] == one
    assert box.draw() == "drawn" and site.facts["corner_lot"] is False and site.facts["street_line"] == one
    # round 3 (P2): two streets picked under the preview's Yes, then the answer set to No before the preview is set
    # aside (No = the drawn lot's No): the drawn lot still gets its own one line back
    site = Site(drawn=OTHER)
    box = site.box().look_up(answer("96_ithaca_rd"))
    box._apply()
    box.facts, box.saved = logic.pick_effect("street", two, box.facts, box.saved)
    box.typed.update(corner_lot=False, corner_source=logic.ENTERED)
    box._apply()
    assert box.type_address(OTHER).draw() == "box-again" and box.facts["street_line"] == one
    assert box.draw() == "drawn" and site.facts["corner_lot"] is False and site.facts["street_line"] == one
    # round 3 (P3), the mirror: a drawn corner lot (Yes, two lines); 106 previewed (No); one street picked, Yes set:
    # the drawn lot gets both its lines back
    site = _drawn_corner_lot()
    both = site.facts["street_line"]
    box = site.box().look_up(answer("106_ithaca_rd"))
    box._apply()
    box.facts, box.saved = logic.pick_effect("street", {"lines": one, "ids": ["Street 1"], "name": None}, box.facts,
                                             box.saved)
    box.typed.update(corner_lot=True, corner_source=logic.ENTERED)
    box._apply()
    assert box.type_address(OTHER).draw() == "box-again"
    assert box.facts["corner_lot"] is True and box.facts["street_line"] == both


def test_review_r4_a_lot_picked_during_a_preview_never_gets_the_old_lots_street_line():
    """Review round 4 of the corner fix, F1 (P1): a drawn lot (not the sample) with one street line; 96 Ithaca Rd
    looked up; Use my survey… picks another lot during the preview (its street lines dropped: asked again on it);
    the drawn address typed back and Draw: the survey lot keeps no street line (never the old lot's, off its
    outline, where the front yard and lot width would be measured from the wrong edge). With the lot unchanged the
    drawn lot's own line still comes back (round 3)."""
    one = [[[0, 0], [60, 0]]]
    site = Site(lot="looked_up", drawn=OTHER)
    site.table.objects["lot2"] = {"layer": "Site", "kind": "lot", "area": 5000.0}
    assert site.facts["street_line"] == one
    box = site.box().look_up(answer("96_ithaca_rd"))
    box._apply()
    box.facts, box.saved = logic.pick_effect("lot", "lot2", box.facts, box.saved)     # Use my survey…
    assert box.facts["lot_id"] == "lot2" and not box.facts.get("street_line")
    assert box.type_address(OTHER).draw() == "box-again"
    assert box.facts["lot_id"] == "lot2" and not box.facts.get("street_line")
    box.draw()
    assert site.facts.get("lot_id") == "lot2" and not site.facts.get("street_line")
    # round 5 (P2): streets picked on that survey lot under the preview's answer, then the preview set aside: the
    # drawn lot's answer comes back, so those lines go (asked again), never a lot answered No with two streets'
    # lines, nor Yes with one; under the same answer they stay
    two = {"lines": [[[0, 0], [50, 0]], [[50, 0], [50, 100]]], "ids": ["A St", "B St"], "name": None}
    for site, preview, picked, drawn_corner in (
            (Site(lot="looked_up", drawn=OTHER), "96_ithaca_rd", two, False),
            (_drawn_corner_lot(), "106_ithaca_rd", {"lines": one, "ids": ["A St"], "name": None}, True)):
        site.saved.update(replaceable_lot=site.facts["lot_id"], from_sample=False)
        site.table.objects["lot2"] = {"layer": "Site", "kind": "lot", "area": 5000.0}
        box = site.box().look_up(answer(preview))
        box._apply()
        assert box.facts["corner_lot"] is not drawn_corner
        box.facts, box.saved = logic.pick_effect("lot", "lot2", box.facts, box.saved)
        box._apply()
        box.facts, box.saved = logic.pick_effect("street", picked, box.facts, box.saved)
        assert box.facts["street_line"] == picked["lines"]
        assert box.type_address(OTHER).draw() == "box-again"
        box.draw()
        assert site.facts["lot_id"] == "lot2" and site.facts["corner_lot"] is drawn_corner
        assert not site.facts.get("street_line"), (drawn_corner, site.facts.get("street_line"))
    site = Site(lot="looked_up", drawn=OTHER)                  # the same answer (106 looks up No, as drawn): kept
    site.table.objects["lot2"] = {"layer": "Site", "kind": "lot", "area": 5000.0}
    box = site.box().look_up(answer("106_ithaca_rd"))
    box._apply()
    box.facts, box.saved = logic.pick_effect("lot", "lot2", box.facts, box.saved)
    box._apply()
    box.facts, box.saved = logic.pick_effect("street", {"lines": one, "ids": ["A St"], "name": None}, box.facts,
                                             box.saved)
    assert box.type_address(OTHER).draw() == "box-again"
    box.draw()
    assert site.facts["lot_id"] == "lot2" and site.facts["corner_lot"] is False and site.facts["street_line"] == one



def test_a_found_lookups_note_is_a_plain_line_never_the_amber_question():
    """The architect's review (2026-10-28, item 16): one amber line read "? Does this lot face two streets? … ·
    Shown dashed: …'s lot. Nothing in the model changes until Draw…": a question and a piece of information as one
    warning. A found lookup's line is now its own plain line (lookup_note); the amber line keeps the questions and a
    lookup that went wrong (not found, offline: what to do)."""
    looked = {"lookup": {"status": "found", "says": logic.PREVIEW_SAYS.format(address="96 Ithaca Rd")},
              "corner_lot": None}
    assert logic.lookup_note(looked).startswith("Shown dashed") and "Shown dashed" not in logic.uncertain(looked)
    assert logic.uncertain(looked).startswith("Does this lot face two streets?")
    saved = {"lookup": {"status": "found", "says": logic.SAVED_SAYS.format(address="106 Ithaca Rd", date="2026-10-20")},
             "corner_lot": False}                                    # the offline safety net asks: amber
    assert logic.lookup_note(saved) is None and logic.uncertain(saved) == saved["lookup"]["says"]
    offline = {"lookup": {"status": "offline", "says": logic.LOOKUP_SAYS["offline"]}, "corner_lot": False}
    assert logic.lookup_note(offline) is None and logic.uncertain(offline) == logic.LOOKUP_SAYS["offline"]
    ui = (Path(__file__).resolve().parents[3] / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert 'note = label(logic.lookup_note(state) or "", size=11)' in ui and "layout.AddRow(None, row(note))" in ui
    # laid out only when there is a note: an empty label still takes a line (the start box ran 12 px past a laptop's
    # height with every question open: the merge-3 suite's test_box_width)
    assert "    if note.Text:" in ui and ui.index("    if note.Text:") < ui.index("layout.AddRow(None, row(note))")
