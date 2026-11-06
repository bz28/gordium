"""The start box's model edits as one transaction: Draw commits last, any other way out rolls back, and a
lookup's answer is drawn through the session.

Moved here unchanged from rhino_logic.py, which still offers every name (so the Rhino plugin is
unchanged). Python 3.9 and the standard library only: Rhino 8 imports this into its own Python 3.9,
where none of the .venv's packages are installed."""

from .facts import FLAT_GROUND, set_street_lines
from .lookup import lookup_choices, lookup_may_replace

__all__ = ['Cancelled', 'draw_then_commit', 'run_box', 'pick_or_nothing', 'apply_lookup']


# ---- the start box as one transaction (review rounds 1-2 of PR #19) ----------------------------------------------
#
# The box's model edits go through one BoxSession, owned by the box (gordium_rhino.confirm) and never copied. An object
# the session replaces is never deleted while the box is open: it is HELD, moved to a hidden holding layer with the
# layer it came from written on it, so Cancel (or Esc, or any error) puts the very same object back, and so does the
# next GordiumStart if Rhino closed in between (recover_held). Draw deletes what is held. Nothing on the holding layer
# is ever measured or sent to the checker (classify). `table` is the model, as a few plain calls (gordium_rhino's
# RhinoTable; a fake in the tests).

class Cancelled(Exception):
    """Esc at a prompt: the whole edit is cancelled and nothing is saved (Enter keeps what is there)."""


def draw_then_commit(session, save):
    """Draw: everything that can fail first (the facts, the box's choices, the sources: `save`), the session's
    commit last, so a failure leaves the session to be rolled back (run_box) with nothing lost."""
    result = save()
    session.commit()
    return result


def run_box(session, loop):
    """The box's loop: any way out but Draw's (Cancel returns None from it; Esc, an error) rolls the session back."""
    try:
        result = loop()
    except BaseException:
        session.rollback()
        raise
    if result is None:
        session.rollback()
    return result


def pick_or_nothing(pick, facts, saved_ui):
    """One pick the box asked for: Esc at its prompt changes nothing."""
    try:
        return pick()
    except Cancelled:
        return facts, saved_ui


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
