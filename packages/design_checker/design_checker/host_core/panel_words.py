"""The panel's words: its header, each row's name, status and details, the legend, the cells and links.

Moved here unchanged from rhino_logic.py, which still offers every name (so the Rhino plugin is
unchanged). Python 3.9 and the standard library only: Rhino 8 imports this into its own Python 3.9,
where none of the .venv's packages are installed."""


__all__ = ['panel_header', 'status_words', 'row_name', 'USE_STATED', 'list_cells', 'list_values', 'highlight',
    'red_last', 'newly_failing', 'WORKED_OUT', 'detail_parts', 'coloured_info', 'labels_on', 'context_shown',
    'yard_label_shown', 'legend_text', 'COLUMN_DELTA', 'CELL_FRACTIONS', 'cell_text', 'shorten', 'link_text',
    'height_limit_text']


def panel_header(head):
    """The panel's header lines above the summary and below it, from the check's header: where (place), then the
    draft notice, the lot and the grade. The code's edition line ("Ch. 325 as amended through Ord. No. …") is the
    report's, not the panel's (Ben's team, MVP list, 2026-10-20)."""
    head = head or {}
    return {"above": [head.get("place") or "Gordium"],
            "below": [head.get("draft") or "Draft rulebook", head.get("lot") or "", head.get("grade") or ""]}


def status_words(item):
    """The status a row's detail is headed with: "Does not comply", "Needs review", "Complies", "Not checked"; a rule
    not in Gordium yet, "Not checked yet" (Ben, 2026-10-21: its group's name); a law waiting for the interior
    (egress, before any room is drawn), "Waiting": a quiet status, never a pass (design_checker/egress.py)."""
    if item.get("group") == "not_covered":
        return "Not checked yet"
    if item.get("waiting"):
        return "Waiting"
    return {"does_not_comply": "Does not comply", "needs_review": "Needs review", "complies": "Complies",
            "not_checked": "Not checked"}[item["status"]]


def row_name(item):
    """A panel row's Item text: the name, "(site)" for a site fact, and its note ("Building height · assuming flat
    ground")."""
    name = item["name"] + (" (site)" if item.get("group") == "site" else "")
    return name + (" · " + item["note"] if item.get("note") else "")


USE_STATED = "stated"


def list_cells(item):
    """A row's Item and Proposed text in the panel's list, and its name heading the detail. The use row names the
    use itself, "Use: One-family dwelling, detached", with "stated" under Proposed: no use's name fits the 64 px
    Proposed column ("One-family" alone takes two lines), and the Item cell has the room (coordinator, 2026-10-28,
    option A: the whole name, no made-up short forms). "Use:" keeps what the row is about; "(site)" is left off:
    measured in Rhino, "Use: One-family dwelling, detached" fits two lines of the Item cell at the panel's 400 px
    only without it. A longer name ("…, semi-detached"), or any at 380 px, ends "…" in the list like every long
    Item; the detail, headed with this same text, has it whole. With no use stated, "Use (site)" and its "—"."""
    proposed = item.get("proposed")
    if item.get("name") == "Use" and proposed and proposed != "—":
        return "Use: " + proposed + (" · " + item["note"] if item.get("note") else ""), USE_STATED
    return row_name(item), proposed


def list_values(item):
    """A row's four cells in the panel's list (Item, Proposed, Required, Delta), before cell_text shortens them: the
    list's own shorter forms where the checker gave one (present: a tax-map lot's Delta, delta_cell, "+2'-0 1/2";
    worst +0'-0 1/2""; a span of readings' tightest pair, cells, "35'-0 5/8" (varies)"), else the row's words. The
    detail below the list always has the words whole (the audit of main, 2026-10-29)."""
    name, proposed = list_cells(item)
    cells = item.get("cells") or {}
    return (name, cells.get("proposed") or proposed, cells.get("required") or item.get("required"),
            item.get("delta_cell") or item.get("delta") or "")


def highlight(status):
    """The colour a part of the model is shaded, from its rule's result only (never from the envelope): red for
    does not comply (under every reading), amber for needs review, nothing for complies or anything else."""
    return {"does_not_comply": "red", "needs_review": "amber"}.get(status)


def red_last(coloured):
    """The coloured parts, (shape, status) each, split into (the rest, the red): the red (does not comply) is drawn
    after everything else, so nothing covers it. In Top view a needs-review amber strip (the eaves) lay over the
    failing red wall below it and hid the one thing that certainly has to change (the architect's review,
    2026-10-28)."""
    rest = [c for c in coloured or [] if highlight(c[1]) != "red"]
    return rest, [c for c in coloured or [] if highlight(c[1]) == "red"]


def newly_failing(before, view):
    """The row to bring into view after a re-check: the first, in the panel's order, that does not comply now and
    did not at the check before (`before`: {item id: status} then, None on a document's first check). None when
    nothing newly fails, so a re-check that changes nothing for the worse never moves the list (the architect's
    review, 2026-10-28: after an edit the newly failing row was out of sight below the rows that need review)."""
    if before is None or not view:
        return None
    status = {i["id"]: i["status"] for i in view.get("items") or []}
    for g in view.get("groups") or []:
        for item_id in g.get("items") or []:
            if status.get(item_id) == "does_not_comply" and before.get(item_id) != "does_not_comply":
                return item_id
    return None


WORKED_OUT = "How it's worked out"


def detail_parts(det):
    """The selected item's detail, split for the panel (the architect's review, 2026-10-28: the formula
    "max(min(25% × lot depth —, 50), 20)", the measuring notes and the chart's shorthand "R-1B: 25%/ 50 ft [fn16]"
    read as jargon). Plain words first, in view: the notes, the result of the working ("Required: 24'-1 7/8" to
    32'-10 1/8"") and the law's own words. Behind WORKED_OUT, collapsed until opened: the formula with the values
    written in, what was measured, the chart's own cell and the precision rule. Nothing is dropped: every quote,
    with where it is from, is in one or the other, and the citation and its links stay in view.
      notes          texts shown in view (at the limit, the colours, the plain result)
      quotes         the law's words and the chart's footnotes, in view
      worked         texts behind the toggle (the whole working, what was measured, the precision)
      worked_quotes  the chart's own cells, behind the toggle"""
    det = det or {}
    calc = det.get("calc") or ""
    head, _, rest = calc.partition(": ")
    working, equals, result = rest.partition(" = ")
    plain = head + ": " + result if equals and head in ("Required", "Allowed") else calc
    quotes = [q for q in det.get("quotes") or [] if q.get("text")]
    return {"notes": [t for t in (det.get("at_limit"), det.get("colours"), plain, det.get("outline")) if t],
            "quotes": [q for q in quotes if not q.get("chart")],
            "worked": [t for t in (calc if plain != calc else None, det.get("scope"), det.get("precision")) if t],
            "worked_quotes": [q for q in quotes if q.get("chart")]}


def coloured_info(entry):
    """What a coloured piece is, kept with it in the drawn list: why (yard or height), the row it is for (its
    measure and name) and its building, from the plan's block (check.plan). The in-Rhino checks read exactly the
    list that is drawn, so a claim can't mistake the rear yard's strip for the side yard's (Rhino check of #28)."""
    return {k: entry.get(k) for k in ("why", "measure", "row", "building")}


def labels_on(ui_state):
    """Whether the viewport shows its on-screen labels (each yard's and lot edge's label, and the status box): off
    unless the architect ticked Show on-screen labels in this document (MVP list, 2026-10-20). The yard lines and the
    red stay either way."""
    return bool((ui_state or {}).get("show_labels", False))


def context_shown(ui_state):
    """Whether the neighbourhood (the context map) is shown: on unless the architect unticked Show neighbourhood in
    this document. Kept per file, like Show on-screen labels (coordinator's decision, 2026-10-21: an architect
    reopening a file expects the same view)."""
    return bool((ui_state or {}).get("show_context", True))


def yard_label_shown(labels, status):
    """A yard's label in plan: with Show on-screen labels on, every one; off, still a failing yard's shortfall
    ("✕ Rear yard 21'-2", needs 22'-6""): it is the live feedback (coordinator, 2026-10-20)."""
    return bool(labels) or status == "does_not_comply"


def legend_text(code=None):
    """The legend ("?"): the marks, what the plan shows, the precision, and which version of the law was checked
    (the code-edition line, no longer in the panel's header)."""
    text = ("✕ does not comply · ? needs review · ✓ complies · – not checked · ⚠ setup problem\n\n"
            "In the plan: the property line, the required yards (shaded), the buildable envelope (dashed), each yard "
            "dimensioned square to its lot line from the wall facing it, as a drawing is: red where it fails, amber "
            "where it needs review, complying ones neutral grey (colour only what's wrong); its number only, on its "
            "line (✕ or ? before it when wrong; its name and what it needs are in the panel), the required line "
            "dashed across it, tagged \"min\" where the yard fails or needs review; in the elevations the height, "
            "dimensioned up from the grade plane, with the limit faint. In plan these lines are drawn over "
            "everything; in every other view they hide behind the solids in front of them, as the model's own lines "
            "do. Values are measured to 1/8 in. and never rounded toward compliance.\n\n"
            "Delta: how far over or under each limit (+ to spare, ≥ + at least that much to spare, − short of a "
            "minimum, over past a maximum).\n\n"
            "In the model, only the offending part of a building is coloured, in its row's colour: the part inside "
            "a required yard, or what rises above the height limit (a cantilever, not the ground under it; a roof's "
            "ridge, not its eaves; a mesh, or a solid Rhino can't cut, is coloured over its whole strip instead; a "
            "block isn't measured until it is exploded). RED: it "
            "fails there under every reading. AMBER: it fails there under some readings only (for example within the tax map's 2'-0\" of a lot line, which a survey settles). "
            "Nothing where it complies. The buildable envelope is only a see-through guide: colours come from the "
            "rules' results.")
    return text + ("\n\nChecked against: " + code if code else "")


COLUMN_DELTA = "Delta"          # the panel's and the report's column for how far over or under (was "Margin")

# eighths of an inch as one character each, in the panel's narrow cells only (the detail and the report keep "7/8")
CELL_FRACTIONS = {"1/8": "⅛", "1/4": "¼", "3/8": "⅜", "1/2": "½", "5/8": "⅝", "3/4": "¾", "7/8": "⅞"}


def cell_text(text):
    """A Proposed, Required or Delta value as the panel's list draws it, in its two lines of a narrow column (the
    architect's review, 2026-10-28: "34'-11 7/8" to 36'-3 3/8"" and "at least 0'-5 1/4" if confirmed" were cut
    off; the panel is not made wider). The same words, shorter: each fraction of an inch one character ("34'-11⅞"")
    and a range one value per line ("34'-11⅞"–" then "36'-3⅜""), so a line never breaks inside a number. The
    selected item's detail below the list shows the words whole, as everywhere else."""
    import re
    text = re.sub(r'(\d) ([1357]/8|1/4|1/2|3/4)"', lambda m: m.group(1) + CELL_FRACTIONS[m.group(2)] + '"', text or "")
    return re.sub(r'(["%]|\d sf) to (?=[\d+−])', "\\1–\n", text)        # after a value, before the next


def shorten(text, most):
    """`text` in at most `most` characters, cut at a word and ended "…" when longer (a link can't wrap: the
    architect's review found one pushing the docked panel's text off its right edge)."""
    text = text or ""
    if len(text) <= most:
        return text
    cut = text[:max(1, most - 1)].rsplit(" ", 1)[0].rstrip(" ,·;:")
    return (cut or text[:max(1, most - 1)]) + "…"


def link_text(citation, most):
    """A citation link's words in at most `most` characters, keeping what tells it apart: "District Regulations
    Chart" said "chart", and if still too long its front cut, never its end (district, column, note: review round
    1, eight links read "Open §325-8, District Regulations Chart…")."""
    text = "Open " + (citation or "").replace("District Regulations Chart", "chart")
    if len(text) <= most:
        return text
    tail = text[len(text) - (most - 7):]
    tail = tail.split(" ", 1)[1] if " " in tail[1:] else tail
    return "Open …" + tail.lstrip(" ,·;")


def height_limit_text(checker_top, height):
    """The height limit's label in an elevation: plain when the checker has the grade plane (its top), else said to
    be shown from the lot's level, a drawing aid ("height" is the limit as text, 35'-0")."""
    if checker_top is not None:
        return "Height limit " + height
    return "Height limit " + height + " (no grade plane yet: shown from the lot's level)"
