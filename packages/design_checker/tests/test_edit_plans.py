"""Tidy-up PR 7: the start box's model edits became edit plans (host_core/edits.py). The decisions (lookup_edits,
reset_edits) now return a plan of edits, which the host's table carries out (gordium_rhino.RhinoTable.apply ->
carry_out), instead of calling the table and the box session themselves.

The proof that nothing changed: BEFORE below is apply_lookup and apply_reset exactly as they were on tidy-6
(0b2f93c5: host_core/edits.py and rhino_logic.py, copied character for character). Every start-box path (lookup,
re-lookup, the architect's own lot kept, not found, the City's outline only, reset with Start fresh and Keep my
building, a pick before the reset, Draw, Cancel, Rhino closing mid-box and recover_held, the dry run of a new
address's house) runs twice on the same fake model, once BEFORE and once now. Both runs must make the very same
calls to the model and to the box session, in the same order with the same arguments and answers, and give the same
facts, box choices, guide and model. The one difference allowed: the plans' reads of the model (the starting house,
the buildings, the spot grades) are all made first, before any edit, where BEFORE read some of them between edits;
each read gives the same answer either way (the edits before it never touch those layers), which the test checks."""
import copy
import json
import sys
from pathlib import Path

import pytest

from design_checker import rhino_logic as logic
from design_checker.host_core import edits
from host_source import host_text
from moved_names import patch_moved

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lookup_box import ZONES, FakeTable, looked_up  # noqa: E402

BEFORE = '''
def apply_lookup(table, session, answer, facts, saved_ui, zones=()):
    """(facts, saved_ui, guide ring or None) after a lookup's answer, with its model edits made through the session:
    the lot it may replace (lookup_may_replace) and every spot grade drawn for that lot (a lookup's or the
    architect's: grades never mix across lots) held; the State's outline drawn as the lot curve and USGS ground as
    spot grades (only what lookup_box.writes allows); the City's outline only as a guide. The architect's own lot,
    its street side and ground are never touched."""
    replaces = lookup_may_replace(facts, saved_ui)
    facts, saved_ui = lookup_choices(answer, facts, saved_ui, zones, replaces=replaces)
    if (answer or {}).get("status") != "found":
        return facts, saved_ui, None
    if not replaces:
        saved_ui["_lookup"]["says"] = "Your own lot is kept: the lookup filled in the address and the district only."
        return facts, saved_ui, None
    w = answer.get("writes") or {}
    for old in [facts.get("lot_id")] + list(table.ground_points()):
        session.hold(old)
    for k in ("lot_id", "plan_north_deg"):
        facts.pop(k, None)
    set_street_lines(facts, None)                # the old lot's street lines and their names go with it
    saved_ui.update(from_sample=False, replaceable_lot=None, lookup_frame=None, ground_kind="flat", lookup_spots=[])
    saved_ui.pop("city_by_hand", None)           # the looked-up lot replaces the one said by hand to be the City's
    guide = None
    if w.get("lot_ring"):
        lot_id = table.add_lot(w["lot_ring"], "Lot · " + (facts.get("address") or "looked up"))
        session.add([lot_id])
        facts["lot_id"] = lot_id
        if w.get("street_line"):
            set_street_lines(facts, w["street_line"])    # no ids: one street's lines (a corner lot's yards and
            #   lot width wait for the street pick, #18 reading its streets only from the ids; one street: as drawn)
        if (w.get("frame") or {}).get("rotation_deg") is not None:   # the plan is turned: name sides by true north
            facts["plan_north_deg"] = w["frame"]["rotation_deg"]
        spots = [] if FLAT_GROUND else [table.add_spot(p) for p in w.get("spots") or []]   # flat: none drawn
        session.add(spots)
        saved_ui.update(replaceable_lot=lot_id, lookup_frame=w.get("frame"), lookup_spots=spots)
        if spots:
            saved_ui["ground_kind"] = "spot"
    elif w.get("guide_ring"):
        guide = w["guide_ring"]
    saved_ui["lookup_snapshot"] = w.get("snapshot")
    return facts, saved_ui, guide


def apply_reset(table, session, facts, saved_ui, choice, zones=()):
    """(facts, saved_ui, redraw_house, guide) at Draw: the pending answer drawn for good through the session (one
    Cancel, one undo), by apply_lookup itself (only what each source allows is written; the lot drawn and its spot
    grades held), the lot drawn now replaceable whoever drew it (they chose: own_work asked). A new address is a new
    site (Ben, 2026-10-25): the lot is replaced whichever they answer, their own lot too. Unless they keep their
    building (`choice` KEEP_MINE), the starting house and every building on the lot are held too. `redraw_house`:
    the starting house is to be drawn again for the new lot. `guide`: the City's outline when that is all the
    answer had (no lot drawn: the architect draws it over the guide, the box still open, then Draw)."""
    pending = (saved_ui or {}).get("_pending") or {}
    saved_ui = dict(saved_ui, replaceable_lot=(facts or {}).get("lot_id"))
    saved_ui.pop("_pending", None)
    keep = choice == KEEP_MINE
    if not keep:
        for old in list(table.massing()) + list(table.buildings()):
            session.hold(old)
    # the box's own choices stay as the architect left them (the district they ticked, the use, the address); the
    # lookup's answer fills only the lot, the street side, the corner and the ground (review round 1)
    chosen_f = {k: facts.get(k, MISSING) for k in BOX_CHOSEN_FACTS}
    chosen_s = {k: saved_ui.get(k, MISSING) for k in BOX_CHOSEN_UI}
    # the box's Corner lot? answer: the lookup's, shown since its preview (preview_lookup), or the architect's
    # change of it, which is theirs and is kept (UX walkthrough 2026-10-28, P0: "Yes: two streets" picked after
    # Look up was saved as the lookup's "no", so a corner lot's second street had a side yard's limit)
    corner, corner_source = facts.get("corner_lot"), saved_ui.get("corner_source")
    facts, saved_ui, guide = apply_lookup(table, session, pending.get("answer") or {}, facts, saved_ui, zones)
    if facts.get("corner_lot") != corner:       # changed in the box: theirs (its street lines picked again)
        facts, saved_ui = corner_answered(facts, saved_ui, corner)
        saved_ui["corner_source"] = corner_source or ENTERED
    found_source = saved_ui.get("address_source")          # the lookup's, for the address as found
    for target, chosen in ((facts, chosen_f), (saved_ui, chosen_s)):
        for k, v in chosen.items():
            if v is MISSING:
                target.pop(k, None)
            else:
                target[k] = v
    # the lot is the new address's now: the address the box opened with is no longer this lot's (typed back, it is
    # a new address, to be looked up: review round 1 of the typed-address rule, P1)
    saved_ui.update(drawn_address=pending.get("address"), house_fingerprint=None, _box_address=pending.get("address"))
    if (pending.get("address") and same_address(facts.get("address"), pending.get("query"))
            and not same_address(facts.get("address"), pending.get("address"))):
        facts["address"] = pending["address"]   # the address as found, never a loose query typed back (round 2),
        if found_source:                        # with the lookup's source: value and source agree (round 3)
            saved_ui["address_source"] = found_source
    if not keep:
        saved_ui["_redrawn_for"] = pending.get("address")     # Draw now draws (the box's button says so)
    return facts, saved_ui, not keep, guide
'''

READS = ("massing", "buildings", "ground_points")            # what the drivers read before planning
TABLE_CALLS = ("exists", "delete", "layer_of", "hold", "release", "mark_added", "clear_mark", "added_objects",
               "held_objects", "layer_names", "remove_layer_if_empty", "save_views", "restore_views", "add_lot",
               "add_spot", "massing", "buildings", "fingerprint", "ground_points")


def before():
    """BEFORE's apply_lookup and apply_reset, reading host_core's names as they are now (FLAT_GROUND patched too)."""
    ns = dict(vars(edits))
    exec(compile(BEFORE, "before (tidy-6)", "exec"), ns)       # noqa: S102
    return ns["apply_lookup"], ns["apply_reset"]


class Logged(FakeTable):
    """The fake model, every call to it written down: (call, its arguments, its answer)."""

    def __init__(self, objects, log):
        super().__init__(objects)
        self.log = log

    def __getattribute__(self, name):
        attr = object.__getattribute__(self, name)
        if name not in TABLE_CALLS:
            return attr

        def call(*args):
            got = attr(*args)
            object.__getattribute__(self, "log").append(("table." + name, copy.deepcopy(args), copy.deepcopy(got)))
            return got
        return call


class LoggedSession(logic.BoxSession):
    def __init__(self, table, log):
        self.log = log
        super().__init__(table)

    def hold(self, object_id):
        self.log.append(("session.hold", (object_id,), None))
        return super().hold(object_id)

    def add(self, ids):
        self.log.append(("session.add", (list(ids),), None))
        return super().add(ids)

    def commit(self):
        self.log.append(("session.commit", (), None))
        return super().commit()

    def rollback(self):
        self.log.append(("session.rollback", (), None))
        return super().rollback()


def model(*, spots=0, massing=0, buildings=0, lot="sample"):
    objects = {}
    if lot:
        objects[lot] = {"layer": "Site", "kind": "lot"}
    for n in range(spots):
        objects["spot%d" % n] = {"layer": "Gordium::Grade", "kind": "point"}
    for n in range(massing):
        objects["floor%d" % n] = {"layer": logic.massing_floor(n + 1), "kind": "brep"}
    for n in range(buildings):
        objects["garage%d" % n] = {"layer": "Building", "kind": "brep"}
    return objects


def run(steps, objects, facts, saved_ui, now):
    """The steps on a fresh fake model, BEFORE's functions or the plans' (`now`): for each step what it gave and the
    calls it made; the model and its layers at the end."""
    apply_lookup, apply_reset = (logic.apply_lookup, logic.apply_reset) if now else before()
    log, out = [], []
    table = Logged(objects, log)
    session = LoggedSession(table, log)
    for step, *arg in steps:
        mark, gave = len(log), None
        if step == "lookup":
            gave = facts, saved_ui, _ = apply_lookup(table, session, copy.deepcopy(arg[0]), facts, saved_ui, ZONES)
        elif step == "preview":                    # Look up: nothing in the model
            gave = facts, saved_ui, _ = logic.preview_lookup(copy.deepcopy(arg[0]), facts, saved_ui, ZONES)
        elif step == "reset":                      # Draw of a new address (gordium_rhino._draw_prepare)
            gave = facts, saved_ui, _, _ = apply_reset(table, session, facts, saved_ui, arg[0], ZONES)
        elif step == "pick_spot":                  # gordium_rhino._box_pick "spot": placed, then the session's
            session.add([table.add_spot(arg[0])])
        elif step == "draw":
            session.commit()
        elif step == "cancel":
            session.rollback()
        elif step == "rhino_closed":               # the box never finished: its session is no longer live
            logic.OPEN_SESSIONS.discard(session.token)
            gave = logic.recover_held(table)
        out.append({"step": step, "gave": gave, "calls": log[mark:]})
    logic.OPEN_SESSIONS.discard(session.token)
    snap = {i: dict(o) for i, o in table.objects.items()}
    text = json.dumps([out, snap, sorted(table.layers)], default=str).replace(session.token, "<the session>")
    return json.loads(text)


def same(steps, objects, facts, saved_ui):
    """BEFORE and now: the same calls (reads aside, all made first now), the same answers, the same model. Now's
    run: (each step's {"gave", "calls"}, the model at the end)."""
    was, now = (run(steps, copy.deepcopy(objects), copy.deepcopy(facts), copy.deepcopy(saved_ui), n)
                for n in (False, True))
    assert was[1:] == now[1:]                                            # the model and its layers at the end
    assert len(was[0]) == len(now[0]) == len(steps)
    for step_was, step_now in zip(was[0], now[0]):
        assert step_was["gave"] == step_now["gave"]                     # facts, saved_ui, guide, redraw
        edits_was = [c for c in step_was["calls"] if c[0][6:] not in READS]
        edits_now = [c for c in step_now["calls"] if c[0][6:] not in READS]
        assert edits_was == edits_now                                    # every edit and session call, in order
        reads_now = [c for c in step_now["calls"] if c[0][6:] in READS]
        assert step_now["calls"][:len(reads_now)] == reads_now           # now: every read before the first edit
        for c in step_was["calls"]:                                      # each read BEFORE made: the same answer
            if c[0][6:] in READS:
                assert c in reads_now, c
    return now[0], now[1]


def answer(name="106_ithaca_rd"):
    return looked_up(name)


def city_outline_only():
    p = looked_up("106_ithaca_rd")
    p["details"]["lot"]["source_keys"] = ["city_parcels"]
    p["writes"] = edits_writes(p)
    return p


def edits_writes(p):
    from design_checker.lookup_box import frame, writes
    return writes({"facts": p["facts"], "details": p["details"]}, frame({"facts": p["facts"]}))


SAMPLE = ({"lot_id": "sample"}, {"from_sample": True, "replaceable_lot": "sample"})


@pytest.fixture(params=[False, True], ids=["spot_ground", "flat_ground"])
def ground(request, monkeypatch):
    """Every path with the lookup's spot grades drawn (FLAT_GROUND off) and with the MVP's flat ground (none)."""
    patch_moved(monkeypatch, logic, "FLAT_GROUND", request.param)
    return request.param


def test_a_lookup_over_the_sample_lot_then_draw(ground):
    """The sample's lot and the architect's own spot grades held (grades never mix across lots), the State's lot and
    the lookup's spots drawn and marked as the session's, then Draw: the same calls, the same facts."""
    steps, snap = same([("lookup", answer()), ("draw",)], model(spots=2), *SAMPLE)
    calls = [c[0] for c in steps[0]["calls"]]
    assert calls.count("session.hold") == 3 and "table.add_lot" in calls            # the lot and both spots held
    assert (calls.count("table.add_spot") > 0) is (not ground)
    assert "sample" not in snap and "spot0" not in snap and "spot1" not in snap     # Draw: gone for good
    assert steps[0]["gave"][0]["lot_id"] in snap


def test_a_re_lookup_in_the_same_box_deletes_what_the_first_drew_then_cancel(ground):
    """Two lookups in one box: the second holds the first one's lot and spots, which this session drew, so they are
    deleted, not held; Cancel brings the sample back."""
    steps, snap = same([("lookup", answer()), ("lookup", answer("109_ithaca_rd")), ("cancel",)], model(spots=1),
                       *SAMPLE)
    assert set(snap) == {"sample", "spot0"}
    assert "table.delete" in [c[0] for c in steps[1]["calls"]]


def test_the_architects_own_lot_is_never_touched(ground):
    steps, _ = same([("lookup", answer()), ("cancel",)], model(lot="mine", spots=1), {"lot_id": "mine"}, {})
    assert not [c for c in steps[0]["calls"] if c[0].startswith("session.")]
    assert steps[0]["gave"][1]["_lookup"]["says"].startswith("Your own lot is kept")


@pytest.mark.parametrize("status", ["not_found", "offline", "outside"])
def test_a_lookup_that_found_nothing_changes_nothing(ground, status):
    steps, _ = same([("lookup", {"status": status}), ("draw",)], model(spots=1), *SAMPLE)
    assert not [c for c in steps[0]["calls"] if c[0][6:] not in READS]


def test_the_citys_outline_only_holds_the_lot_and_draws_none(ground):
    steps, snap = same([("lookup", city_outline_only()), ("cancel",)], model(spots=1), *SAMPLE)
    assert steps[0]["gave"][2] and "lot_id" not in steps[0]["gave"][0]
    assert "table.add_lot" not in [c[0] for c in steps[0]["calls"]] and set(snap) == {"sample", "spot0"}


@pytest.mark.parametrize("choice", [logic.START_FRESH, logic.KEEP_MINE])
@pytest.mark.parametrize("end", ["draw", "cancel"])
def test_a_new_addresss_reset_at_draw(ground, choice, end):
    """Look up (a preview: nothing in the model), then Draw's reset: the starting house and the buildings held
    unless they keep theirs, the old lot and every spot grade held, the new lot drawn; Draw or Cancel after."""
    facts = {"lot_id": "sample", "address": "1 Old St"}
    saved = logic.box_opened({"from_sample": True, "replaceable_lot": "sample"}, facts)
    steps, snap = same([("preview", answer()), ("reset", choice), (end,)],
                       model(spots=2, massing=2, buildings=1), facts, saved)
    held = [c[1][0] for c in steps[1]["calls"] if c[0] == "session.hold"]
    kept = {"floor0", "floor1", "garage0"}
    assert (kept <= set(held)) is (choice == logic.START_FRESH)
    assert {"sample", "spot0", "spot1"} <= set(held)
    if end == "cancel":
        assert set(model(spots=2, massing=2, buildings=1)) == set(snap)


def test_a_spot_picked_in_the_box_then_the_reset_deletes_it(ground):
    """A spot grade the architect placed in this box (the session's own) is deleted by the reset, not held."""
    facts = {"lot_id": "sample", "address": "1 Old St"}
    saved = logic.box_opened({"from_sample": True, "replaceable_lot": "sample"}, facts)
    steps, snap = same([("preview", answer()), ("pick_spot", [1.0, 2.0, 3.0]), ("reset", logic.START_FRESH),
                        ("cancel",)], model(spots=1), facts, saved)
    assert ["table.delete", ["new1"], None] in steps[2]["calls"]


def test_a_reset_in_an_empty_file(ground):
    steps, snap = same([("preview", answer()), ("reset", logic.START_FRESH), ("draw",)], model(lot=None),
                       {}, logic.box_opened({}, {}))
    assert steps[1]["gave"][0]["lot_id"] in snap


def test_rhino_closing_mid_box_then_recover_held(ground):
    """A box left open when Rhino closed: the next start's recover_held deletes what it drew and puts back what it
    held, the same calls either way."""
    steps, snap = same([("lookup", answer()), ("rhino_closed",)], model(spots=2), *SAMPLE)
    assert set(snap) == {"sample", "spot0", "spot1"}
    assert steps[1]["gave"][1] == 3 and steps[1]["gave"][0] >= 1            # (the lot and its spots; 3 held back)


def test_the_dry_run_of_a_new_addresss_house_draws_nothing(ground):
    """gordium_rhino._plan_reset_house runs the reset on _DryTable (the real table's reads, its own add_lot and
    add_spot) with _DrySession. The real _DryTable and _DrySession, run here over a logged fake model: BEFORE and now
    give the same facts, box choices and the lot's ring, and the model is never edited (only read). Without
    _DryTable's own apply, the real table's would draw the lot: this fails then."""
    src = host_text("rhino", "plugin", purpose="wiring")
    dry_src = src[src.index("class _DryTable"):src.index("def _reset_state(")]
    facts = {"lot_id": "sample", "address": "1 Old St"}
    saved = logic.box_opened({"from_sample": True, "replaceable_lot": "sample"}, facts)
    facts, saved, _ = logic.preview_lookup(answer(), facts, saved, ZONES)
    got = []
    for apply_reset in (before()[1], logic.apply_reset):
        log = []
        ns = {"logic": logic, "DRY_LOT": "gordium-planned-lot", "RhinoTable": lambda doc: doc}
        exec(dry_src, ns)                                                          # noqa: S102
        dry = ns["_DryTable"](Logged(model(spots=2, massing=1, buildings=1), log))
        out = apply_reset(dry, ns["_DrySession"](), copy.deepcopy(facts), copy.deepcopy(saved), logic.START_FRESH,
                          ZONES)
        assert {c[0] for c in log} <= {"table." + r for r in READS}               # read only, nothing edited
        got.append((out, dry.ring))
    assert got[0] == got[1]
    assert got[1][0][0]["lot_id"] == "gordium-planned-lot" and got[1][1]


def test_rhino_tables_apply_carries_the_plan_out_on_itself():
    """RhinoTable.apply hands the plan to carry_out with the table itself (so its own add_lot / add_spot draw)."""
    src = host_text("rhino", "plugin", purpose="wiring")
    table = src[src.index("class RhinoTable"):src.index("def _recover(")]
    body = table[table.index("    def apply("):].split("\n    def ", 2)[0]
    assert "return logic.carry_out(plan, self, session, facts, saved_ui)" in body


# ---- the plans themselves -----------------------------------------------------------------------------------------

def test_a_plan_is_plain_json_and_names_new_objects_by_ref(ground):
    facts, saved = logic.preview_lookup(answer(), {"lot_id": "sample", "address": "1 Old St"},
                                        logic.box_opened(*reversed(SAMPLE)), ZONES)[:2]
    f, s, redraw, guide, plan = logic.reset_edits(facts, saved, logic.START_FRESH, ZONES, massing=["floor0"],
                                                  buildings=["garage0"], ground_points=["spot0"])
    assert json.loads(json.dumps(plan)) == plan
    assert [p["op"] for p in plan[:4]] == ["hold"] * 4 and [p["id"] for p in plan[:4]] == [
        "floor0", "garage0", "sample", "spot0"]
    assert plan[4]["op"] == "add_lot" and plan[4]["ref"] == "$lot" == f["lot_id"] == s["replaceable_lot"]
    spots = [p["ref"] for p in plan if p["op"] == "add_spot"]
    assert s["lookup_spots"] == spots and plan[-1] == {"op": "own", "refs": spots}
    assert bool(spots) is (not ground)


def test_the_model_reads_are_never_left_out_by_default():
    """Review round 1 (2 sceptics): with an empty default, a host that forgot a read got a plan holding none of the
    old lot's spot grades (or its house and buildings), and no error: grades mixed across lots."""
    with pytest.raises(TypeError):
        logic.lookup_edits(answer(), *SAMPLE, ZONES)
    for left_out in ("massing", "buildings", "ground_points"):
        reads = {k: [] for k in ("massing", "buildings", "ground_points") if k != left_out}
        with pytest.raises(TypeError):
            logic.reset_edits(*SAMPLE, logic.START_FRESH, ZONES, **reads)


def test_carry_out_swaps_each_ref_for_the_id_the_table_gave():
    table = FakeTable({"old": {"layer": "Site", "kind": "lot"}})
    session = logic.BoxSession(table)
    plan = [{"op": "hold", "id": "old"}, {"op": "add_lot", "ring": [[0, 0], [1, 0], [1, 1]], "name": "Lot", "ref": "$lot"},
            {"op": "own", "refs": ["$lot"]}, {"op": "add_spot", "point": [0, 0, 1], "ref": "$spot1"},
            {"op": "own", "refs": ["$spot1"]}]
    kept = {"street": ["Ithaca Rd"]}
    f, s = logic.carry_out(plan, table, session, {"lot_id": "$lot", "other": kept}, {"lookup_spots": ["$spot1"]})
    assert f == {"lot_id": "new1", "other": kept} and f["other"] is kept     # (no ref inside: the same object)
    assert s == {"lookup_spots": ["new2"]} and session.added == ["new1", "new2"]
    assert session.held == [("old", "Site")]
    session.rollback()
    logic.OPEN_SESSIONS.discard(session.token)


@pytest.mark.parametrize("plan", [
    [{"op": "draw_house"}],                                                     # a step it doesn't know
    [{"op": "own", "refs": ["$lot"]}],                                          # used before it is made
    [{"op": "add_spot", "point": [0, 0, 0], "ref": "spot"}],                    # not a ref
    [{"op": "add_spot", "point": [0, 0, 0], "ref": "$s"}, {"op": "add_spot", "point": [0, 0, 0], "ref": "$s"}],
])
def test_carry_out_stops_at_a_step_it_cannot_make(plan):
    """Never a step skipped: an error, which the box rolls back (run_box)."""
    table = FakeTable({})
    session = logic.BoxSession(table)
    with pytest.raises(ValueError):
        logic.carry_out(plan, table, session, {}, {})
    session.rollback()
