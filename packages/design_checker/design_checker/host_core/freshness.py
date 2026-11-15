"""Whether the results on screen are current: when the model counts as changed, when it is checked again,
what the panel says while the results are out of date (greyed), the undo steps' names, and the
panel's actions refused while a start box is open or Gordium is working.

Moved here unchanged from rhino_logic.py, which still offers every name (so the Rhino plugin is
unchanged). Python 3.9 and the standard library only: Rhino 8 imports this into its own Python 3.9,
where none of the .venv's packages are installed."""

from .facts import enter_words

__all__ = ['BOX_BUSY', 'should_recheck', 'CHANGED_SINCE', 'AUTO_CHECK_LABEL', 'AUTO_CHECK_TIP', 'changed_after_box',
    'auto_check', 'NEVER_CHECKED', 'out_of_date_line', 'draw_one_hint', 'should_check_front', 'controls_enabled',
    'zoom_state', 'last_check_at', 'UNDO_WORDS', 'undo_enter', 'undo_record_to_end', 'after_undo_redo',
    'dirty_after_undo', 'gate_actions', 'WORKING', 'REFUSED', 'busy_actions', 'NotInFront', 'front_actions',
    'recovery_message', 'plans_house', 'result_stale', 'checked_while_still']


BOX_BUSY = "Finish or cancel the open start box first."


def should_recheck(dirty_at, now, running, box_open, wait, last_at=None, auto=True):
    """Live mode's re-check after an edit: only when the architect asked for it (`auto`: Check after every edit,
    off by default; otherwise the Check button checks), once the model has been still for `wait` seconds, no check
    is running, no start box is open (its own edits mark the model changed; the check waits for the box to close,
    then runs: verification round of PR #19), and no check has finished since that edit (`last_at`: GordiumStart's
    own check after its box already covers the box's edits)."""
    if not auto:
        return False
    if last_at is not None and dirty_at and last_at >= dirty_at:
        return False
    return bool(dirty_at) and now - dirty_at >= wait and not running and not box_open


# ---- the Check button (Ben, 2026-10-21): no check after every edit unless asked ---------------------------------
CHANGED_SINCE = "Model changed since the last check — press Check"
AUTO_CHECK_LABEL = "Check after every edit"
AUTO_CHECK_TIP = "Off: the results grey out after an edit until you press Check. On: Gordium checks again by itself."


def changed_after_box(before, now, drawn, failed=False):
    """When the model counts as changed after a start box closes (STATE["dirty"]): Cancel rolled the box's own edits
    back, so the model is as it was when the box opened (`before`: changed then, or not); Draw's edits are checked
    by Draw's own check, and any change left counts (`now`). A box that ended in an error is no Cancel: its rollback
    may have stopped partway, so any edit seen during it counts (`now`, else `before`): the results grey out, never
    shown as current for a model that may differ (the headless check-15, demo review of #26 with #27)."""
    if failed:
        return now or before
    return now if drawn else before


def auto_check(ui_state):
    """Whether this document checks again by itself after every edit: off unless the architect ticked Check after
    every edit in it (saved with the file)."""
    return bool((ui_state or {}).get("auto_check", False))


NEVER_CHECKED = "No check yet for this model — press Check"


def out_of_date_line(auto, checked_before=True):
    """What the panel's header and the viewport's status box say while the results are older than the model: a
    check is on its way ("Checking…") only when one will run by itself; otherwise the architect is told to press
    Check (the results stay greyed, never shown as if current); "since the last check" only when there was one."""
    if auto:
        return "Checking… (the model changed)"
    return CHANGED_SINCE if checked_before else NEVER_CHECKED


def draw_one_hint(auto):
    """GordiumStart's line when no starting house could be drawn: who checks the one the architect draws."""
    return ("draw one and Gordium will check it" if auto else
            "draw one, then press Check in the Gordium panel")


def should_check_front(front_pending, running, box_open):
    """A document come to the front (new, opened, switched to): checked once, whatever Check after every edit says
    (it is not an edit, and nothing of it is on screen yet), when no check is running and no start box is open."""
    return bool(front_pending) and not running and not box_open


def controls_enabled(box_open, zoom_ok):
    """(the panel's controls, Zoom to): all off while a start box is open; on closing, worked out from the panel as
    it is now, never restored from a list saved when the box opened (the header's buttons may have been rebuilt in
    between, after a document switch: verification round 4 of PR #19). Zoom to also needs a selected, current item
    (`zoom_ok`, as gordium_ui.show decides it)."""
    return (not box_open, (not box_open) and bool(zoom_ok))


def zoom_state(selected_ok, stale, box_open):
    """(Zoom to on or off, its tooltip saying why when off): on only for a selected, current item with no start box
    open. Worked out every time the selection, the results or the box change (UX review 2026-10-27: selecting a row
    left it greyed until the panel next redrew, with nothing saying why)."""
    if box_open:
        return False, "Close the start box first."
    if not selected_ok:
        return False, "Select a row to zoom to it."
    if stale:
        return False, "Out of date: press Check, then zoom."
    return True, "Zoom to the selected item (or double-click its row)."


def last_check_at(checked_at, document):
    """When the last completed check of THIS document finished (None: none yet). Never a placeholder's time, and
    never another document's (verification round 4: switching documents dropped the pending re-check)."""
    return (checked_at or {}).get(document)


# Each panel change is one Rhino undo step, named in Edit > Undo by what it did (a change written outside any undo
# record is skipped by Ctrl+Z, which undoes the architect's own earlier edit instead: #32's review, 2026-10-26)
UNDO_WORDS = {"survey": "Gordium: use my survey", "enter": "Gordium: enter the row's facts",   # (enter: undo_enter)
              "main": "Gordium: pick the main building", "adu": "Gordium: pick the ADU's building",
              "add": "Gordium: add to check",
              "ground": "Gordium: this is the ground", "not_ground": "Gordium: not the ground",
              "massing": "Gordium: hide or show the starting house", "labels": "Gordium: on-screen labels",
              "edit_site": "Gordium: the start box", "grade": "Gordium: the start box",
              "context": "Gordium: show or hide the neighbourhood", "auto_check": "Gordium: check after every edit"}


def undo_enter(needs):
    """A row's Enter step, named in Edit > Undo by what was entered ("Gordium: enter the number of stories"), not
    the same words for every row (the audit of main, 2026-10-29); UNDO_WORDS["enter"] with no facts named."""
    words = enter_words(needs)
    return "Gordium: " + words[:1].lower() + words[1:] if words else UNDO_WORDS["enter"]


def undo_record_to_end(held, doc_serial):
    """Whether the plugin ends the Draw's undo record `held` ((document serial, record serial) from
    BeginUndoRecord, or None) in the document `doc_serial`: only a record it began (serial above 0: 0 means a
    command is already recording, or undo is off, and the record is Rhino's to end, RhinoCommon), in the same
    document."""
    return bool(held) and bool(held[1]) and doc_serial is not None and held[0] == doc_serial


def after_undo_redo(is_end_undo, is_end_redo):
    """Whether Rhino's undo event is an Undo or a Redo just finished: then what the last check drew is cleared and
    the model checked again (gordium_rhino._undo_redo). Never on its start, a record begun or ended, or a purge."""
    return bool(is_end_undo or is_end_redo)


def dirty_after_undo(dirty_at, now):
    """When the model last changed, once Rhino's Undo or Redo ended at `now`: never earlier than an edit already
    noted (its object events, gordium_rhino._changed) and never earlier than now, so a check that finished just
    before the Undo can never count as covering it (should_recheck: last_at >= dirty_at; review round 2, P1: an Undo
    within 0.5 s of a check left the screen cleared and the panel showing the model as it was before)."""
    return max(dirty_at or 0, now)


def gate_actions(actions, box_open, say, open_ok=("legend",)):
    """The panel's actions, each doing nothing but saying BOX_BUSY while a start box is open (one choke point: none of
    them writes to the model, runs a check or opens another box under an open one; verification round of PR #19).
    `open_ok`: the ones that only show something (the legend)."""
    def gated(name, fn):
        def run(*args, **kwargs):
            if box_open() and name not in open_ok:
                say(BOX_BUSY)
                return REFUSED              # (a checkbox puts its tick back: gordium_ui._tick)
            return fn(*args, **kwargs)
        return run
    return {name: gated(name, fn) for name, fn in actions.items()}


WORKING = "Gordium is working (its window says on what): wait for it, or press Cancel there."


REFUSED = object()        # what a gated panel action returns when it did nothing (its checkbox puts its tick back)


def busy_actions(actions, busy, say, open_ok=("legend",)):
    """The panel's actions, each saying WORKING instead while Gordium waits for an answer (busy()): the wait window is
    a plain one while Rhino keeps answering, so a button pressed meanwhile must never start a second piece of work
    on top of it (another check, a start box). `open_ok`: the ones that only show something. A refused action
    returns REFUSED, so a checkbox that called it shows its setting as it still is (independent review of #32)."""
    def gated(name, fn):
        def run(*args, **kwargs):
            if busy() and name not in open_ok:
                say(WORKING)
                return REFUSED
            return fn(*args, **kwargs)
        return run
    return {name: gated(name, fn) for name, fn in actions.items()}


class NotInFront(Exception):
    """Another file came to the front while Gordium read this one's facts (Rhino runs during the checker's wait):
    whatever was about to prompt or save stops (gordium_rhino.current_facts)."""


def front_actions(actions, say):
    """The panel's actions, each saying why (NotInFront's words) and doing nothing more when the file it was
    reading is no longer the one in front."""
    def guarded(fn):
        def run(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except NotInFront as e:
                say(str(e))
                return REFUSED
        return run
    return {name: guarded(fn) for name, fn in actions.items()}


def recovery_message(removed, back):
    """What recovery did, in words (None when it did nothing)."""
    def n(k):
        return "%d object%s" % (k, "s" if k != 1 else "")
    parts = (["removed %s an unfinished start box drew" % n(removed)] if removed else []) + \
        (["put back %s it had set aside" % n(back)] if back else [])
    return " and ".join(parts) or None


def plans_house(mode, redraw, caller_draws):
    """Whether Draw works out a starting house before the box commits: GordiumStart's box always draws one; another
    box only when its Draw reset the site (`redraw`) AND its caller draws the house after (`caller_draws`: Edit
    site…). GordiumCheck's box never draws one, so it never asks for one (review round 1: a "start" request for
    nothing, and its Cancel escaped the command)."""
    return mode == "start" or bool(redraw and caller_draws)


def result_stale(dirty_at, shown_at, now, after, rechecking):
    """Whether the result on screen is out of date, so nothing is drawn as complying or not (F7, H1): the model
    changed more than `after` s ago and no check has finished since, or a background re-check is running (live mode
    clears the pending edit when it starts one, and the result on screen is of the model before that edit: review
    round 1, P1, a false pass shown while the re-check ran)."""
    if rechecking:
        return True
    return bool(dirty_at and now - dirty_at >= after and (shown_at or 0) < dirty_at)


def checked_while_still(begun_at, dirty_at):
    """Whether a check that read the model at `begun_at` still shows the model: no edit since (`dirty_at`, the last
    edit not yet re-checked, None for none). A live re-check runs while the architect may keep editing; its result
    is shown only if nothing changed after it read the model, else it is dropped and the model checked again."""
    return not dirty_at or dirty_at < begun_at
