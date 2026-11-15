"""The start box's model edits as one transaction: Draw commits last, any other way out rolls back, and a
lookup's answer (or a new address's reset) is decided here as an edit plan, which the host carries out in its
own transaction and whose placeholders it swaps for the ids it made.

Offered unchanged by rhino_logic.py too (so the Rhino plugin calls logic.apply_reset as before). Python 3.9 and
the standard library only: Rhino 8 imports this into its own Python 3.9, where none of the .venv's packages are
installed."""

from .facts import FLAT_GROUND, corner_answered, set_street_lines
from .lookup import KEEP_MINE, MISSING, found_address, lookup_choices, lookup_may_replace, same_address
from .start_box import BOX_CHOSEN_FACTS, BOX_CHOSEN_UI, ENTERED

__all__ = ['Cancelled', 'draw_then_commit', 'run_box', 'pick_or_nothing', 'EDIT_OPS', 'carry_out', 'with_ids',
           'lookup_edits', 'apply_lookup', 'reset_edits', 'apply_reset', 'OVERLAYS_NONE_SOURCE', 'overlays_none_found']


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


# ---- edit plans: what to change in the model, as plain data (tidy-up PR 7) -----------------------------------------
#
# The decisions (lookup_edits, reset_edits) never touch the model: they return the new facts and box choices and an
# edit plan, a list of steps in the order they are made:
#   {"op": "hold", "id": an object's id}           take it out of the model for the session (BoxSession.hold: held,
#                                                  so Cancel puts it back; one this session drew is deleted)
#   {"op": "add_lot", "ring": [[x, y], ...], "name": ..., "ref": "$lot"}    draw the lot outline
#   {"op": "add_spot", "point": [x, y, z], "ref": "$spot1"}                 draw a spot grade
#   {"op": "own", "refs": ["$lot"]}                the session drew these (BoxSession.add: Cancel deletes them)
# A "$..." ref stands for the id the host gives the new object; the facts and box choices name the new objects by
# their refs until the host has made them (with_ids). The host carries the plan out in its own transaction (Rhino:
# RhinoTable.apply inside the box's BoxSession; a Revit host: a TransactionGroup). carry_out is the reference way,
# on a host's table and session: the very calls apply_lookup made itself before plans, in the same order.

EDIT_OPS = ("hold", "add_lot", "add_spot", "own")


def carry_out(plan, table, session, facts, saved_ui):
    """(facts, saved_ui) with each ref swapped for the id `table` gave it, after making the plan's edits in order
    through `session` (hold, own) and `table` (add_lot, add_spot). A step it doesn't know, or a ref used before it
    is made or made twice, stops it (an error, rolled back with the box: run_box): never a step skipped."""
    ids = {}
    for step in plan:
        op = step.get("op")
        if op == "hold":
            session.hold(step["id"])
        elif op in ("add_lot", "add_spot"):
            ref = step["ref"]
            if not (isinstance(ref, str) and ref.startswith("$")) or ref in ids:
                raise ValueError("edit plan: %r is not a new ref" % (ref,))
            ids[ref] = (table.add_lot(step["ring"], step["name"]) if op == "add_lot" else
                        table.add_spot(step["point"]))
        elif op == "own":
            missing = [r for r in step["refs"] if r not in ids]
            if missing:
                raise ValueError("edit plan: %s used before it is made" % ", ".join(map(str, missing)))
            session.add([ids[r] for r in step["refs"]])
        else:
            raise ValueError("edit plan: unknown step %r (known: %s)" % (op, ", ".join(EDIT_OPS)))
    return with_ids(facts, ids), with_ids(saved_ui, ids)


def with_ids(value, ids):
    """`value` (facts, box choices: dicts, lists, tuples, strings) with every string that is a ref in `ids` swapped
    for its id; whatever holds no ref is returned as it is (the very same object)."""
    if isinstance(value, str):
        return ids[value] if value in ids else value
    if type(value) is dict:
        out = {k: with_ids(v, ids) for k, v in value.items()}
        return value if all(out[k] is v for k, v in value.items()) else out
    if type(value) in (list, tuple):
        out = [with_ids(v, ids) for v in value]
        return value if all(a is b for a, b in zip(out, value)) else type(value)(out)
    return value


def lookup_edits(answer, facts, saved_ui, zones=(), *, ground_points):
    """(facts, saved_ui, guide ring or None, edit plan) after a lookup's answer: the lot it may replace
    (lookup_may_replace) and every spot grade drawn for that lot (`ground_points`, the model's: a lookup's or the
    architect's: grades never mix across lots) held; the State's outline drawn as the lot curve and USGS ground as
    spot grades (only what lookup_box.writes allows); the City's outline only as a guide. The architect's own lot,
    its street side and ground are never touched. The new lot and spots are named by their refs ("$lot",
    "$spot1"...) in the facts and saved_ui until the plan is carried out (carry_out). The model's reads have no
    default: one forgotten (an empty list) would leave the old lot's spot grades unheld, mixed with the new lot's."""
    plan = []
    replaces = lookup_may_replace(facts, saved_ui)
    facts, saved_ui = lookup_choices(answer, facts, saved_ui, zones, replaces=replaces)
    if (answer or {}).get("status") != "found":
        return facts, saved_ui, None, plan
    facts.pop("overlays_none_found", None)       # a found lookup decides it again, for its own lot only
    if not replaces:
        saved_ui["_lookup"]["says"] = "Your own lot is kept: the lookup filled in the address and the district only."
        return facts, saved_ui, None, plan
    w = answer.get("writes") or {}
    for old in [facts.get("lot_id")] + list(ground_points):
        plan.append({"op": "hold", "id": old})
    for k in ("lot_id", "plan_north_deg"):
        facts.pop(k, None)
    set_street_lines(facts, None)                # the old lot's street lines and their names go with it
    saved_ui.update(from_sample=False, replaceable_lot=None, lookup_frame=None, ground_kind="flat", lookup_spots=[])
    saved_ui.pop("city_by_hand", None)           # the looked-up lot replaces the one said by hand to be the City's
    guide = None
    if w.get("lot_ring"):
        lot_id = "$lot"
        plan.append({"op": "add_lot", "ring": w["lot_ring"], "name": "Lot · " + (facts.get("address") or "looked up"),
                     "ref": lot_id})
        plan.append({"op": "own", "refs": [lot_id]})
        facts["lot_id"] = lot_id
        if w.get("street_line"):
            set_street_lines(facts, w["street_line"])    # no ids: one street's lines (a corner lot's yards and
            #   lot width wait for the street pick, #18 reading its streets only from the ids; one street: as drawn)
        if (w.get("frame") or {}).get("rotation_deg") is not None:   # the plan is turned: name sides by true north
            facts["plan_north_deg"] = w["frame"]["rotation_deg"]
        none_found = overlays_none_found(answer, w["lot_ring"])
        if none_found:
            facts["overlays_none_found"] = none_found
        spots = [] if FLAT_GROUND else ["$spot%d" % (n + 1) for n in range(len(w.get("spots") or []))]  # flat: none
        plan += [{"op": "add_spot", "point": p, "ref": ref} for p, ref in zip(w.get("spots") or [], spots)]
        plan.append({"op": "own", "refs": spots})
        saved_ui.update(replaceable_lot=lot_id, lookup_frame=w.get("frame"), lookup_spots=spots)
        if spots:
            saved_ui["ground_kind"] = "spot"
    elif w.get("guide_ring"):
        guide = w["guide_ring"]
    saved_ui["lookup_snapshot"] = w.get("snapshot")
    return facts, saved_ui, guide, plan


def apply_lookup(table, session, answer, facts, saved_ui, zones=()):
    """(facts, saved_ui, guide ring or None) after a lookup's answer, its edits (lookup_edits) carried out by the
    host's `table` in the box's `session` (table.apply: gordium_rhino's RhinoTable.apply; carry_out on a fake)."""
    facts, saved_ui, guide, plan = lookup_edits(answer, facts, saved_ui, zones, ground_points=table.ground_points())
    facts, saved_ui = table.apply(plan, session, facts, saved_ui)
    return facts, saved_ui, guide


def reset_edits(facts, saved_ui, choice, zones=(), *, massing, buildings, ground_points):
    """(facts, saved_ui, redraw_house, guide, edit plan) at Draw: the pending answer drawn for good (one Cancel, one
    undo), by lookup_edits itself (only what each source allows is written; the lot drawn and its spot grades
    held), the lot drawn now replaceable whoever drew it (they chose: own_work asked). A new address is a new site
    (Ben, 2026-10-25): the lot is replaced whichever they answer, their own lot too. Unless they keep their building
    (`choice` KEEP_MINE), the starting house (`massing`) and every building on the lot (`buildings`) are held too.
    `ground_points`: every spot grade in the model (lookup_edits). `redraw_house`: the starting house is to be drawn
    again for the new lot. `guide`: the City's outline when that is all the answer had (no lot drawn: the architect
    draws it over the guide, the box still open, then Draw)."""
    pending = (saved_ui or {}).get("_pending") or {}
    saved_ui = dict(saved_ui, replaceable_lot=(facts or {}).get("lot_id"))
    saved_ui.pop("_pending", None)
    keep = choice == KEEP_MINE
    plan = []
    if not keep:
        plan += [{"op": "hold", "id": old} for old in list(massing) + list(buildings)]
    # the box's own choices stay as the architect left them (the district they ticked, the use, the address); the
    # lookup's answer fills only the lot, the street side, the corner and the ground (review round 1)
    chosen_f = {k: facts.get(k, MISSING) for k in BOX_CHOSEN_FACTS}
    chosen_s = {k: saved_ui.get(k, MISSING) for k in BOX_CHOSEN_UI}
    # the box's Corner lot? answer: the lookup's, shown since its preview (preview_lookup), or the architect's
    # change of it, which is theirs and is kept (UX walkthrough 2026-10-28, P0: "Yes: two streets" picked after
    # Look up was saved as the lookup's "no", so a corner lot's second street had a side yard's limit)
    corner, corner_source = facts.get("corner_lot"), saved_ui.get("corner_source")
    facts, saved_ui, guide, drawn = lookup_edits(pending.get("answer") or {}, facts, saved_ui, zones,
                                               ground_points=ground_points)
    plan += drawn
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
    return facts, saved_ui, not keep, guide, plan


def apply_reset(table, session, facts, saved_ui, choice, zones=()):
    """(facts, saved_ui, redraw_house, guide) at Draw: reset_edits over what the model holds now (the starting house,
    the buildings, the spot grades: every one read before any edit), its edits carried out by the host's `table` in
    the box's `session` (table.apply)."""
    facts, saved_ui, redraw, guide, plan = reset_edits(
        facts, saved_ui, choice, zones, massing=table.massing(), buildings=table.buildings(),
        ground_points=table.ground_points())
    facts, saved_ui = table.apply(plan, session, facts, saved_ui)
    return facts, saved_ui, redraw, guide


OVERLAYS_NONE_SOURCE = ("address lookup: FEMA flood maps, the City's historic, gorge and zoning maps and parcel "
                        "record, every one answering none")


def overlays_none_found(answer, lot_ring):
    """The lot fact a live lookup's positive "no overlay on this lot" becomes (project.OVERLAYS_NONE_FIELDS), for the
    lot it draws (`lot_ring`, in feet, as drawn), or None. Only when its overlays fact is "suggested" with nothing in
    it: every overlay source answered, none found, and nothing doubtful about the lot it was worked out on (site_lookup
    raises it to needs review otherwise). Never from a saved lookup (an old answer, offered when the services are
    down), nor without the lot: the checker honours it only while the lot is still this outline."""
    answer = answer or {}
    got = ((answer.get("facts") or {}).get("overlays") or {})
    status = ((answer.get("details") or {}).get("overlays") or {}).get("status")
    if answer.get("status") != "found" or answer.get("saved_on") or status != "suggested":
        return None
    if not isinstance(got.get("value"), list) or got["value"] or not lot_ring or len(lot_ring) < 3:
        return None
    date = answer.get("checked")   # the place's own day (lookup_box: city_day), the day the host compares it with;
    address = found_address(answer)   # never the overlays fact's UTC day (a day ahead after about 8 pm in Ithaca)
    if not date or not address:
        return None
    return {"value": True, "lot_outline": [[float(p[0]), float(p[1])] for p in lot_ring], "address": address,
            "source": OVERLAYS_NONE_SOURCE, "date": str(date)}
