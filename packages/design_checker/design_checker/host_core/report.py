"""What the panel says about the zoning report, and the words of long work: its steps, Cancel, and a model
that changed while Gordium worked.

Moved here unchanged from rhino_logic.py, which still offers every name (so the Rhino plugin is
unchanged). Python 3.9 and the standard library only: Rhino 8 imports this into its own Python 3.9,
where none of the .venv's packages are installed."""


__all__ = ['report_message', 'BUSY', 'NO_DOCUMENT', 'WorkCancelled', 'WAIT_WINDOW_S', 'CANCELLING', 'STOP_HINT',
    'STOP_HINT_CLICK', 'FIRST_STEP', 'CHECK_CANCELLED', 'CHECK_CANCELLED_NOTE', 'DRAW_CANCELLED', 'REPORT_CANCELLED',
    'REPORT_CANCELLED_LATE', 'report_cancelled', 'SETTLING', 'CHECK_OUTDATED', 'REPORT_OUTDATED', 'NOT_IN_FRONT',
    'outdated_report_message', 'HOUSE_OUTDATED', 'DRAW_OUTDATED', 'ModelChanged']


def report_message(path, written, error=None, opened=True, open_error=None, stale=False):
    """What the panel says after a report was asked for (Zoning report… or GordiumCheck): never nothing (Ben's
    test, 2026-10-20: the button did nothing after GordiumStart, because only GordiumCheck wrote the report).
    `stale`: an earlier report is still at that path, so it is said to be out of date."""
    if not written:
        return ("Zoning report not saved: " + (error or "the check could not run") + "." +
                (" The report already at " + path + " is from an earlier check: out of date." if stale else ""))
    if opened:
        return "Report saved to " + path + " (opened)."
    return ("Report saved to " + path + ". It couldn't be opened here" + (": " + open_error if open_error else "") +
            "; open it with Excel, Numbers or any spreadsheet app.")


BUSY = "A check is running: try again in a moment."
NO_DOCUMENT = "Open a Rhino model first."


# ---- long work: a line that says what Gordium is doing, and a Cancel that stops it --------------------------------
# The checker's and the lookup's work runs in their own processes; the plugin waits for them on a Job's thread,
# never on Rhino's, so Rhino keeps drawing and answering while they work (a slow one shows a small window after
# WAIT_WINDOW_S with the current step, the seconds so far and Cancel). Cancel stops the process: its answer is never
# used, so nothing it would have changed changes.

class WorkCancelled(Exception):
    """The architect pressed Cancel while Gordium worked: the work was stopped and nothing it would have changed was
    changed."""


WAIT_WINDOW_S = 0.4        # s: work quicker than this shows no window at all (no flash on a quick check)
CANCELLING = "Cancelling…"
STOP_HINT = "Esc or Cancel to stop"     # the wait window's own hint, while it has the keyboard (Esc reaches it)
STOP_HINT_CLICK = "Click Cancel to stop"   # ... and while it hasn't: never a promise Esc can't keep
FIRST_STEP = {"check": "Checking…", "start": "Finding the largest building that complies…",
              "options": "Starting Gordium's checker…", "facts": "Reading the lot facts…",
              "sample_site": "Loading the sample lot…"}
CHECK_CANCELLED = "Check cancelled"
CHECK_CANCELLED_NOTE = ("Nothing in the model changed. Nothing is shown as checked until the next check: press "
                        "Check again.")
DRAW_CANCELLED = ("Draw cancelled: nothing was drawn, and the model is as it was before the box opened (Draw again "
                  "when you're ready).")
REPORT_CANCELLED = "Zoning report cancelled: the report file wasn't changed."
REPORT_CANCELLED_LATE = ("Zoning report cancelled as it finished: the new report had already been saved to {path} "
                         "(not opened).")


def report_cancelled(path, changed):
    """What Zoning report… says when its check was cancelled: the file as it was, or (Cancel pressed in the moment
    after the checker moved the new report in) that it was saved anyway."""
    return REPORT_CANCELLED_LATE.format(path=path) if changed else REPORT_CANCELLED
SETTLING = "Finishing the check that is running…"
CHECK_OUTDATED = "The model changed while it was being checked: nothing is shown as checked. Press Retry."
SITE_SUFFIX = ".site.json"   # the site description kept beside a report (design_checker.check.SITE_SUFFIX)
REPORT_OUTDATED = ("The zoning report at {path} is of the model as it was when this check began (it was edited "
                   "meanwhile, or another file came to the front): run the check again (Zoning report… in the "
                   "panel) for a report of the model now.")
NOT_IN_FRONT = ("Another file came to the front while Gordium was getting ready, so nothing was started: run the "
                "command again in the file you want.")
def outdated_report_message(path, report_error, had_report):
    """What a check whose model changed while it ran says of its report: written, but of the model as it was; or,
    when the checker couldn't write it, that it wasn't written and why (never that it was: independent review of
    #32)."""
    if report_error:                     # (its own full stop dropped: report_message adds one)
        return report_message(path, False, str(report_error).rstrip(". "), stale=bool(had_report))
    return REPORT_OUTDATED.format(path=path)


HOUSE_OUTDATED = ("The model changed while Gordium worked out the starting house, so none was drawn: draw one, and "
                  "Gordium will check it.")
DRAW_OUTDATED = ("The model changed while Gordium worked out the starting house, so nothing was drawn and the model "
                 "is as it was: Draw again.")


class ModelChanged(WorkCancelled):
    """The model was edited (or another document came to the front) while Gordium worked out something to draw for
    it: nothing is drawn; `said` is what the architect is told."""
    said = DRAW_OUTDATED
