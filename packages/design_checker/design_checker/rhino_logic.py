"""The decisions the Rhino command makes, as plain functions (no Rhino, Python 3.9), so CI can test them. The
Rhino script (apps/rhino_plugin/gordium_rhino.py) imports this file directly.
"""

import datetime as _dt
import json
import queue
import threading

LAYERS = {"lot": "Site", "building": "Building"}
ID_KEY = "gordium:id"                   # the same keys as model_measurement.read_3dm (a test keeps them equal)
FLOOR_KEY = "gordium:floor"            # user text on a floor block GordiumStart drew: "<story>;<height drawn, ft>"
MASSING = "Gordium::Massing"            # where GordiumStart draws the starting building: building objects too
SOLIDS = ("Brep", "Extrusion", "Mesh", "SubD")
DRAWING_AIDS = ("Curve", "Point", "PointCloud", "TextDot", "AnnotationBase", "Hatch", "TextEntity", "Dimension",
                "Leader", "LinearDimension", "AngularDimension", "RadialDimension", "OrdinateDimension")
# the grade isn't required: without one the check runs and height and stories need review until it's set (spec C3)
REQUIRED = ("jurisdiction", "zone", "use", "street_line", "lot_surveyed")   # corner lot unanswered: the yards wait (C)


def on_layer(full_path, layer):
    """A layer or one of its sublayers ("Building::Garage")."""
    return full_path == layer or full_path.startswith(layer + "::")


CONTEXT = "Gordium::Context"            # the context map (neighbouring parcels, streets, notes): drawing only
CONTEXT_KEY = "gordium_context"         # on each context object: the endpoints.yaml source it was drawn from
HOLDING_LAYER = "Gordium::Replaced (Cancel restores)"   # objects a start box replaced, until Draw (BoxSession)
HELD_FROM = "gordium_held_from"                          # on each held object: the layer it came from
ADDED_BY = "gordium_added"                               # on each object a start box drew: its session, until Draw
HELD_BY = "gordium_held_by"                              # on each held object: the session holding it
OPEN_SESSIONS = set()          # the sessions of start boxes open now (recovery never touches theirs: review round 4)
BOX_BUSY = "Finish or cancel the open start box first."


class BoxGate:
    """One start box at a time (review round 4: Edit site… from the panel during a pick opened a second box)."""

    def __init__(self):
        self.open = False

    def enter(self):
        if self.open:
            return False
        self.open = True
        return True

    def leave(self):
        self.open = False


def classify(full_path, kind, holds_building=False):
    """What the Rhino command does with one object, from its layer's full path and its geometry's type name:
    "lot" (a curve on the lot layer: a possible lot outline), "building" (a solid or mesh on the building layer),
    None (anything else, ignored), or a problem sentence. Nothing that could be part of a building is dropped:
    a block on the building layer, or a block holding building objects wherever it is placed, and any other
    geometry on the building layer, are problems, so the checker says NEEDS REVIEW."""
    if on_layer(full_path, HOLDING_LAYER):           # held by an open start box: never measured or sent
        return None
    if on_layer(full_path, CONTEXT):                 # the neighbourhood drawn for context: never measured or sent
        return None
    if on_layer(full_path, MASSING):
        full_path = LAYERS["building"]
    if kind.startswith("InstanceReference") and (on_layer(full_path, LAYERS["building"]) or holds_building):
        return "a block on the Building layer can't be measured yet (explode it)"
    if on_layer(full_path, LAYERS["lot"]):
        return "lot" if kind.endswith("Curve") else None
    if not on_layer(full_path, LAYERS["building"]):
        return None
    if kind in SOLIDS:
        return "building"
    if kind in DRAWING_AIDS or kind.endswith("Curve") or kind.endswith("Dimension"):
        return None
    return "a " + kind + " on the Building layer can't be measured yet (explode it or turn it into a solid)"


def panel_header(head):
    """The panel's header lines above the summary and below it, from the check's header: where (place), then the
    draft notice, the lot and the grade. The code's edition line ("Ch. 325 as amended through Ord. No. …") is the
    report's, not the panel's (Ben's team, MVP list, 2026-10-20)."""
    head = head or {}
    return {"above": [head.get("place") or "Gordium"],
            "below": [head.get("draft") or "Draft rulebook", head.get("lot") or "", head.get("grade") or ""]}


def status_words(item):
    """The status a row's detail is headed with: "Does not comply", "Needs review", "Complies", "Not checked"; a rule
    not in Gordium yet, "Not checked yet" (Ben, 2026-10-21: its group's name)."""
    if item.get("group") == "not_covered":
        return "Not checked yet"
    return {"does_not_comply": "Does not comply", "needs_review": "Needs review", "complies": "Complies",
            "not_checked": "Not checked"}[item["status"]]


def row_name(item):
    """A panel row's Item text: the name, "(site)" for a site fact, and its note ("Building height · assuming flat
    ground")."""
    name = item["name"] + (" (site)" if item.get("group") == "site" else "")
    return name + (" · " + item["note"] if item.get("note") else "")


def dock_host(hosts, serial):
    """The docked panel to fill for the document in front: Rhino makes one per document window (keyed by the
    document's number); a panel made without one (key 0) serves when the front document has none."""
    if serial is not None and serial in hosts:
        return hosts[serial]
    return hosts.get(0)


def place_panel_now(placed):
    """Whether to size and place the panel's floating window: only until it has been seen shown (Rhino's own
    200 x 200 window), never again after ("docked" or "floating"): the architect's own size and place stay
    (round 1: it jumped back to the right edge on every live re-check)."""
    return placed is None


def highlight(status):
    """The colour a part of the model is shaded, from its rule's result only (never from the envelope): red for
    does not comply (under every reading), amber for needs review, nothing for complies or anything else."""
    return {"does_not_comply": "red", "needs_review": "amber"}.get(status)


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
            "In the plan: the property line, the required yards (shaded), the buildable envelope (dashed), each yard's "
            "measured distance. Red marks only the part of the building inside a required yard or above the height "
            "limit. Values are measured to 1/8 in. and never rounded toward compliance.\n\n"
            "Delta: how far over or under each limit (+ to spare, − short).\n\n"
            "In the model: RED is the part of the building that does not comply (under every reading); AMBER is the "
            "part a rule that needs review is about (for example inside the 2'-0\" tax-map caution zone of a yard). "
            "The buildable envelope is only a see-through guide: colours come from the rules' results.")
    return text + ("\n\nChecked against: " + code if code else "")


COLUMN_DELTA = "Delta"          # the panel's and the report's column for how far over or under (was "Margin")


def missing(facts):
    """The required lot facts not yet given: the confirm dialog shows whenever any is missing."""
    facts = facts or {}
    return [k for k in REQUIRED if facts.get(k) is None or facts.get(k) == []]


def with_suggestions(saved, suggested):
    """The facts to confirm: what is saved, with suggestions only for what is missing."""
    out = dict(suggested)
    out.update({k: v for k, v in (saved or {}).items() if v is not None})
    return out


# The facts only the architect can state (the model can't show them), in the order they are asked: each with its
# prompt, its kind (a whole number 0 or more, or yes / no) and its name in a row's words. A row waiting on any of
# them says which, and its "Enter …" button asks for exactly those (needs_of, enter_words).
STATED_FACTS = {
    "sleeping_rooms": ("Bedrooms", "count", "bedrooms"),
    "parking_spaces": ("Off-street parking spaces", "count", "parking spaces"),
    "dwelling_units": ("Dwelling units", "count", "dwelling units"),
    "rooms_let_for_profit": ("Rooms let for profit", "count", "rooms let for profit"),
    "conversion": ("Made by converting an existing building, not new construction? (§325-3B)", "yes_no",
                   "whether it is a conversion"),
    # the whole building's count, asked only where the measuring asks for it (a part not drawn as floor blocks):
    # stories_needed; it stands only if at least the floors drawn (the measuring checks, and refused_stories says)
    "stories": ("Stories of the whole building", "count", "the number of stories"),
}
STORIES_ASKED = ("enter the number of stories", "enter the count")      # the measuring's own words when it waits for the count


def stories_needed(record):
    """Whether the stories measurement waits for the architect's count (its reason asks to enter it)."""
    return any(w in ((record or {}).get("reason") or "") for w in STORIES_ASKED)


def refused_stories(items):
    """The message when the count entered was refused by the measuring (its code, stories_refused, on the row:
    never its words, which may be reworded), else None."""
    i = next((i for i in items or [] if i.get("refused")), None)
    if i is None:
        return None
    why = i.get("reason") or ""
    i_said = why.split(": does not comply under that reading. ")[-1].rstrip(".")
    return (i_said[0].upper() + i_said[1:] if i_said else "The count") + ". The count wasn't kept."


def needs_of(names, values):
    """The stated facts a rule reads (`names`) that aren't set yet (`values`), in the order they are asked."""
    return [k for k in STATED_FACTS if k != "stories" and k in names and (values or {}).get(k) is None]


def _and(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def enter_words(needs):
    """The button's words for a row waiting on `needs`: "Enter bedrooms and parking spaces"."""
    return "Enter " + _and([STATED_FACTS[k][2] for k in needs]) if needs else None


def needs_reason(needs):
    """Why the row isn't checked: "Needs bedrooms and parking spaces, which the model doesn't show"."""
    return "Needs " + _and([STATED_FACTS[k][2] for k in needs]) + ", which the model doesn't show" if needs else None


def update_counts(facts, answers):
    """Bedrooms, parking spaces, stories, dwelling units and rooms let for profit (whole numbers, 0 or more) and
    whether the building is a conversion (yes / no) from the Lot facts prompts. An answer of None means the prompt
    was skipped: the fact stays as it was (unset stays unset, so its rules stay NEEDS REVIEW), never 0 or no."""
    out = dict(facts or {})
    for key in ("sleeping_rooms", "parking_spaces", "stories", "dwelling_units", "rooms_let_for_profit"):
        if answers.get(key) is not None:
            n = int(answers[key])
            if n < 0 or n != answers[key]:
                raise ValueError(f"{key} must be a whole number, 0 or more")
            out[key] = n
    if answers.get("conversion") is not None:
        out["conversion"] = bool(answers["conversion"])
    return out


def to_feet(facts, scale):
    """Facts read off the model (street line ends, ground level), in model units, as feet (scale = feet per
    model unit). Everything Gordium measures and stores is in feet."""
    out = dict(facts)
    if out.get("street_line"):
        out["street_line"] = [[[c * scale for c in p] for p in line] for line in out["street_line"]]
    if out.get("grade_elevation") is not None:
        out["grade_elevation"] = out["grade_elevation"] * scale
    return out


def set_street_lines(facts, lines, ids=None):
    """`facts` (changed in place, and returned) with the street lot lines `lines` and the street each is on (`ids`,
    one per line, None where unknown): both set, or both dropped. The one way the street lines change (review round
    7, P1: a lot re-picked kept the old lines' street names, and the lot facts were refused, saved ones unreadable);
    names that don't match the lines one for one are left out (unnamed, never misnamed)."""
    if lines:
        facts["street_line"] = lines
    else:
        facts.pop("street_line", None)
    if lines and _street_lines().matching_ids(lines, ids) is not None:
        facts["street_ids"] = list(ids)
    else:
        facts.pop("street_ids", None)
    return facts


def drop_stale(facts, lot_ids, building_ids):
    """The saved facts without a lot or main building that is no longer in the model (redrawn, joined, deleted):
    the lot's street lines go with it, so the confirm dialog asks again instead of keeping an id nothing has."""
    out = dict(facts or {})
    if out.get("lot_id") and out["lot_id"] not in lot_ids:
        out.pop("lot_id")
        set_street_lines(out, None)
    if out.get("main_building") and out["main_building"] not in building_ids:
        out.pop("main_building")
    return out


def venv_python(root, os_name):
    """Where the repo's virtual environment keeps Python: bin/python (Mac, Linux), Scripts\\python.exe (Windows)."""
    if os_name == "nt":
        return "\\".join((root, ".venv", "Scripts", "python.exe"))
    return "/".join((root, ".venv", "bin", "python"))


def draws_in(checked, viewport):
    """Whether a result is drawn in a viewport: only in the document it is the result for (Rhino for Mac keeps
    several models open side by side; one model's verdict never shows on another)."""
    return checked is not None and checked == viewport


def code_fingerprint(packages_dir):
    """What the checker's code is now: every file under packages/ (code and the data it loads) with its size and
    time, as one text. The
    background checker is started again whenever this changes (an update while Rhino is open), so results never
    come from code that is no longer there."""
    import os
    found = []
    for root, dirs, files in os.walk(packages_dir):         # code and the data it loads (measures.yaml), not caches
        dirs[:] = sorted(d for d in dirs if d != "__pycache__" and not d.startswith(".") and not d.endswith(".egg-info"))
        for name in sorted(files):
            if not name.endswith((".pyc", ".pyo")) and not name.startswith("."):
                path = os.path.join(root, name)
                try:
                    st = os.stat(path)
                    found.append("%s:%d:%d" % (os.path.relpath(path, packages_dir), st.st_size, st.st_mtime_ns))
                except OSError:         # gone between listing and reading (an editor's temporary file): changed
                    found.append("%s:gone" % os.path.relpath(path, packages_dir))
    return "|".join(found)


def restart_checker(alive, started_with, now):
    """Whether to start the background checker again: it stopped, or the code changed since it started."""
    return not alive or started_with != now


def after_confirm(choice):
    """What the confirm dialog's answer means: "keep" (OK), "change" (Change…), or "cancel" (closed, Esc):
    a cancel saves nothing, since nothing is used until the architect says OK."""
    return {"ok": "keep", "change": "change"}.get(choice, "cancel")


def accepts_pick(object_id, candidate_ids):
    """Whether a clicked object can be saved as the lot or the main building: only one of the candidates the
    check reads (a closed outline on the Site layer, a solid on the Building layer); any other pick would be
    saved and then dropped on the next check, so the pick prompt lets only candidates be clicked."""
    return object_id in candidate_ids


def option_names(kind, count):
    """Command-line options naming each candidate ("Lot1", "Lot2"), so one that can't be clicked (locked or
    hidden: Rhino won't select it) can still be chosen."""
    return ["%s%d" % (kind, i + 1) for i in range(count)]


def after_lot_pick(facts, picked_lot):
    """The facts after the lot is (re)picked: a different lot drops the street lines, which belonged to the old
    one (they are asked again on the new lot), and so Enter can't keep them."""
    out = dict(facts)
    if picked_lot and picked_lot != out.get("lot_id"):
        out["lot_id"] = picked_lot
        set_street_lines(out, None)          # the old lot's street lines and their names go with it
        out.pop("plan_north_deg", None)      # the looked-up lot's turn belonged to it
    return out


def street_enter_keeps(facts):
    """Whether Enter at the first street-line prompt keeps the street lines saved for this lot."""
    return bool(facts.get("street_line"))


def corner_answered(facts, saved_ui, corner):
    """(facts, saved_ui) with the Corner lot? answer `corner` (None: unanswered), the one helper the start box and
    the command line both use: a changed answer drops the street lines and their street's name (a corner lot has
    two streets, any other one: picked again; review round 5, P0: the box kept both streets' lines on a lot answered
    No, and a 40 ft lot read 200 ft wide)."""
    was = (facts or {}).get("corner_lot")
    facts = dict(facts or {}, corner_lot=corner)
    if corner is None:
        facts.pop("corner_lot")
    saved_ui = dict(saved_ui or {})
    if was is not None and corner != was:         # a real answer that flips (the first answer, from "Not answered",
        set_street_lines(facts, None)             # keeps the prefilled line and its name: review round 6, P1)
        saved_ui.pop("street_name", None)
    return facts, saved_ui


def suggested_facts(jurisdiction, zones, lots, buildings):
    """The start box's prefilled lot facts, in the model's units (the plugin converts them to feet), for the
    architect to confirm. `lots`: the Site layer's closed outlines, each {"id", "area", "bottom" (its lowest
    level), "segments": [((x, y), (x, y)), ...]}; `buildings`: each {"id", "bottom", "volume" (of its box)}.
    The largest outline is the lot, its lowest line on screen the street side; the ground is flat at the
    buildings' lowest point (or the lot's level); the lot is not from a survey; the first zone with rules; a
    detached one-family house; the largest solid the main building. The corner-lot question is never answered
    here: always None, so the box asks it and the yards wait for the answer."""
    facts = {"jurisdiction": jurisdiction, "zone": zones[0] if zones else None, "use": "one_family_detached",
             "corner_lot": None, "ground_is_flat": True, "lot_surveyed": False}
    lot = max(lots, key=lambda l: l["area"]) if lots else None
    if lot is not None:
        facts["lot_id"] = lot["id"]
        if lot["segments"]:
            a, b = min(lot["segments"], key=lambda s: (s[0][1] + s[1][1]) / 2)
            set_street_lines(facts, [[[a[0], a[1]], [b[0], b[1]]]])
    ground = suggested_ground([b["bottom"] for b in buildings], lot["bottom"] if lot is not None else None)
    if ground is not None:
        facts["grade_elevation"] = ground
    if len(buildings) > 1:
        facts["main_building"] = max(buildings, key=lambda b: b["volume"])["id"]
    facts["corner_lot"] = None                     # never guessed, whatever came before
    return facts


def suggested_ground(building_bottoms, lot_bottom):
    """The ground level to suggest (feet or model units, as given): the lowest point of the buildings, or with no
    building yet (a new project on the architect's own lot) the lot outline's level. Shown in the dialog, never
    used unconfirmed."""
    return min(building_bottoms) if building_bottoms else lot_bottom


def crosses(segment, x, y, w, h):
    """Whether the segment ((x1, y1), (x2, y2)) touches the w × h box at (x, y) (screen pixels): clipped to the
    box's slab in x, then in y (Liang–Barsky)."""
    (x1, y1), (x2, y2) = segment
    t0, t1, dx, dy = 0.0, 1.0, x2 - x1, y2 - y1
    for p, q in ((-dx, x1 - x), (dx, x + w - x1), (-dy, y1 - y), (dy, y + h - y1)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def beside_line(a, b, w, h, gap=6):
    """Where a w × h label for the dimension line a–b goes (its top left, screen pixels): beside the line, never on
    it. A mostly horizontal line has it above, centred; a mostly vertical one to its right, centred."""
    (xa, ya), (xb, yb) = a, b
    if abs(xb - xa) >= abs(yb - ya):
        return (xa + xb) / 2 - w / 2, min(ya, yb) - gap - h
    return max(xa, xb) + gap, (ya + yb) / 2 - h / 2


def hint_text(hint, buttons):
    """The detail pane's hint as words, or None: never the words of a button it already shows ("Pick the main
    building…", "Enter …"), nor "Add to check…" (a row a left-out solid makes cautious names it in its reason; the
    one button is on the left-out row itself: the review, F2)."""
    if not hint or hint.rstrip("…") in {b.rstrip("…") for b in buttons} or hint == "Add to check…":
        # (a button's words end in "…" where the hint's may not: "Enter bedrooms and parking spaces")
        return None
    return hint


LABEL_MIN_LOT_PX = 120      # a lot smaller than this on screen (zoomed out to the neighbourhood): no labels on it


def label_width(text, size):
    """A one-line label's width on screen, pixels (its text and its backing box's margins)."""
    return len(text) * size * 0.58 + 14


def labels_shown(lot_px):
    """Whether the lot's plan labels (its edge lengths, its yards) are drawn at this zoom: not when the lot on
    screen (`lot_px`, its larger side, pixels; None: no lot drawn, nothing to judge by) is under LABEL_MIN_LOT_PX,
    zoomed out to the neighbourhood (Ben, on #23's capture: there they piled into a column with long leaders).
    Every one of them, together; zoomed back in, all of them again. The status box isn't a plan label: it stays.
    At working zoom nothing is hidden for being long (review round 2, R5: judged label by label, a four-view lot
    lost its yard labels, a failing shortfall with them, and 106's 10'-4" edge its length): a short edge's label
    sits beside it with a leader (needs_leader)."""
    return lot_px is None or lot_px >= LABEL_MIN_LOT_PX


def needs_leader(line_px, width):
    """A lot edge shorter on screen than its label: the label goes beside it, off the other lines, with a short
    leader back to the edge's middle (as a dimension too short for its text is drawn)."""
    return line_px < width


def leader_end(point, box):
    """Where a leader from `point` (x, y) meets a label's `box` (left, top, width, height): the box's nearest
    point (on its edge, or `point` itself if inside)."""
    left, top, w, h = box
    return (min(max(point[0], left), left + w), min(max(point[1], top), top + h))


def place_label(line, w, h, obstacles=(), taken=(), gap=6, view=None):
    """Where a w × h label for the dimension `line` ((x1, y1), (x2, y2), screen pixels) goes: (left, top, clear).
    The spots beside its line are tried in turn (a mostly horizontal line: above, below, each centred, then
    shifted to either end; a mostly vertical one: right, left, then shifted up or down); the first that crosses
    no line in `obstacles` (other dimensions, the lot's and the house's edges; its own line always) and covers
    no box in `taken` is used. With `view` (its width and height), only spots wholly on screen are tried (seen in
    Rhino: "Side yard, Southwest …, needs 10'-0" (approx.)" went 15 px off the left edge). If none is clear, the
    first spot, kept on screen, and False (the caller moves it off the others)."""
    (xa, ya), (xb, yb) = line
    x0, x1, y0, y1 = min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)
    # nearest the line's middle first: centred on either side, then shifted along it (a label far along its line
    # reads as another edge's: seen in Rhino, the west edge's length ended up under the front edge)
    if x1 - x0 >= y1 - y0:
        xs = [(x0 + x1) / 2 - w / 2, x1 - w, x0, x0 - w - gap, x1 + gap]
        spots = [(x, top) for x in xs for top in (y0 - gap - h, y1 + gap)]
    else:
        ys = [(y0 + y1) / 2 - h / 2, y0, y1 - h, y0 - h - gap, y1 + gap]
        spots = [(left, y) for y in ys for left in (x1 + gap, x0 - gap - w)]
    lines = list(obstacles) + [line]
    on_screen = [(x, y) for x, y in spots if view is None or (0 <= x and x + w <= view[0] and 0 <= y and y + h <= view[1])]
    for left, top in on_screen:
        if not any(crosses(s, left, top, w, h) for s in lines) and \
                not any(left < a + c and a < left + w and top < b + e and b < top + h for a, b, c, e in taken):
            return left, top, True
    left, top = (on_screen or spots)[0]
    if view is not None:                     # nowhere beside it on screen: the first spot, moved onto the screen
        left, top = min(max(left, 0), max(view[0] - w, 0)), min(max(top, 0), max(view[1] - h, 0))
    return left, top, False


def label_lines(text):
    """A plan label as two lines, for when it won't fit beside its line on one: its name, then its numbers
    ("✕ Side yard, Southwest" / "7'-0 5/8", needs 10'-0" (approx.)"). One line when it has no name before a number
    (a lot edge's length)."""
    words = text.split(" ")
    k = next((i for i, w in enumerate(words) if i and w[:1].isdigit()), None)
    return [text] if k is None else [" ".join(words[:k]), " ".join(words[k:])]


def notice_spot(view_w, view_h, w, h, model, taken=(), gap=12):
    """Where the "no longer complies" notice (w × h) goes in a view (screen pixels): (left, top). The corners are
    tried in turn (top left under the view's name, bottom left above the axes, top right, bottom right); the first
    that covers none of the model (`model`: its on-screen box, x0, y0, x1, y1, or None) and no box in `taken`
    (the status box) is used; if every corner covers some of the model, the one covering least (architect's
    review, 2026-10-21: bottom left, it hid the lot's lower edge and dimensions)."""
    spots = [(gap, 34), (gap, view_h - h - 64), (view_w - w - gap, 34), (view_w - w - gap, view_h - h - 40)]

    def overlap(x, y, box):
        a, b, c, e = box
        return max(0.0, min(x + w, c) - max(x, a)) * max(0.0, min(y + h, e) - max(y, b))
    free = [(x, y) for x, y in spots if not any(overlap(x, y, (a, b, a + c, b + e)) for a, b, c, e in taken)] or spots
    return min(free, key=lambda s: (overlap(s[0], s[1], model) if model else 0.0, free.index(s)))


def clear_spot(taken, x, y, w, h, avoid=()):
    """Where a w × h label wanted at (x, y) (its top left, in screen pixels) covers none already drawn this frame
    (`taken`, a list of (x, y, w, h)): the nearest free position a label's height down or up, tried in turn, never
    moved up off the top of the view; the spot is then taken. If none is free within four steps (a tall box such as
    the status box in the way), the label goes just below everything it would cover."""
    def hits(top):
        return any(x < a + c and a < x + w and top < b + e and b < top + h for a, b, c, e in taken) or \
            any(crosses(s, x, top, w, h) for s in avoid)       # nor any line it must stay off (its dimension)
    top = None
    for k in range(9):
        trial = y + (k + 1) // 2 * (h + 3) * (1 if k % 2 else -1)
        if (trial >= 0 or trial >= y) and not hits(trial):        # never moved up off the top of the view
            top = trial
            break
    if top is None:                   # a tall box in the way (the status box): just below whatever it covers
        below = y
        for _ in range(len(taken) + 1):
            over = [b + e for a, b, c, e in taken if x < a + c and a < x + w and below < b + e and b < below + h]
            if not over:
                top = below
                break
            below = max(over) + 3
    top = y if top is None else top
    taken.append((x, top, w, h))
    return top


def status_box(viewport_width, rows, size=13):
    """Where the status box goes (top right of a view): (x, y, w, h) in screen pixels, the same size
    gordium_ui.draw_text_box draws it. Reserved before the labels, so no label is drawn under it."""
    width = max(len(r) for r in rows) * (size * 0.6) + 22
    height = len(rows) * (size + 9) + 10
    return (viewport_width - width - 14, 14, width, height)


def survey_pick(n_lots, picked, outlined):
    """Pick survey lot lines…: (the lot to mark as surveyed, or None; what to say, or None). Enter, with lots to
    choose from, keeps the one outlined (as the prompt says); no lot at all says how to draw one."""
    if n_lots == 0:
        return None, "No lot outline to pick: draw the surveyed lot as one closed polyline on the Site layer."
    if picked:
        return picked, None
    if outlined:
        return outlined, None
    return None, "No lot is outlined yet: run Pick survey lot lines… again and click the surveyed lot outline."


def could_be_building(kind, solid=False, faces=0):
    """Whether a Rhino object off the Building layer could be a building the check is leaving out (so lot coverage
    needs review): a solid, an extrusion, a SubD, a block, any polysurface of more than one face (a garage missing
    a face is still a garage) and any mesh of more than a few faces, open or closed (an imported shed is often an
    unwelded mesh). Not a single flat surface, a curve or a point. `kind` is the geometry's type name. Size is never
    a reason to leave one out: one mesh holding a garage and a shed spreads over most of the lot as well."""
    if kind in ("Extrusion", "SubD", "InstanceReferenceGeometry"):
        return True
    if kind == "Brep":
        return solid or faces > 1
    if kind == "Mesh":
        return solid or faces > 4
    return False


def looks_like_ground(kind, closed, extents, lot_extents, reach=1.0):
    """Whether a left-out object looks like the ground: an open mesh or surface (never a closed solid, a block, a
    SubD or an extrusion) whose plan extents (x0, y0, x1, y1) span the whole lot's, give or take `reach`. Only a
    label for the panel's "This is the ground"; it is never left out of the check on this guess."""
    if closed or kind not in ("Mesh", "Brep"):
        return False
    x0, y0, x1, y1 = extents
    a0, b0, a1, b1 = lot_extents
    return x0 <= a0 + reach and y0 <= b0 + reach and x1 >= a1 - reach and y1 >= b1 - reach


ON_LOT_REACH = 0.1        # ft: how far into the lot an object must reach to count as on it (a neighbour drawn
                          # touching the lot line, or a hair over it, stays off)


def _ring_area(ring):
    """The signed area of a closed ring of (x, y) points (counterclockwise: positive)."""
    return sum(ring[i - 1][0] * ring[i][1] - ring[i][0] * ring[i - 1][1] for i in range(len(ring))) / 2


def _hull(points):
    """The convex hull of (x, y) points, counterclockwise (Andrew's monotone chain)."""
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) < 3:
        return pts

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _clip(subject, convex):
    """The part of the ring `subject` (any simple polygon) inside the counterclockwise convex ring `convex`
    (Sutherland-Hodgman). Its area is the overlap's area."""
    out = list(subject)
    for i in range(len(convex)):
        a, b = convex[i - 1], convex[i]
        inside = [(b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0 for p in out]
        nxt = []
        for k in range(len(out)):
            p, q, pin, qin = out[k - 1], out[k], inside[k - 1], inside[k]
            if pin != qin:
                dx, dy = q[0] - p[0], q[1] - p[1]
                den = (b[0] - a[0]) * dy - (b[1] - a[1]) * dx
                t = ((b[1] - a[1]) * (p[0] - a[0]) - (b[0] - a[0]) * (p[1] - a[1])) / den if den else 0.0
                nxt.append((p[0] + t * dx, p[1] + t * dy))
            if qin:
                nxt.append(q)
        out = nxt
        if not out:
            break
    return out


def box_near_lot(box, lot_box, reach):
    """Whether a plan box (x0, y0, x1, y1) comes within `reach` of the lot's plan box: a quick test before any
    outline work. Exact in the cautious direction: an object whose box misses the lot's box grown by `reach`
    can't reach into the lot (its footprint lies inside its box, and the lot inside the lot's)."""
    x0, y0, x1, y1 = box
    a0, b0, a1, b1 = lot_box
    return x0 <= a1 + reach and a0 - reach <= x1 and y0 <= b1 + reach and b0 - reach <= y1


def reaches_into_lot(lot_ring, points, reach, box=None):
    """Whether an object whose plan points (any (x, y) of it: vertices, points along its edges) are `points`
    reaches into the lot (`lot_ring`, its outline's points) by more than `reach` (model units): the part of its
    plan footprint (their convex hull) inside the lot, averaged across (twice its area over its perimeter), is
    wider than `reach`. Wholly on the lot, straddling a lot line or mostly past it: on the lot. Touching the
    line from outside, a hair over it, or off the lot but inside the lot's bounding box (a rotated or jogged
    lot, the neighbour's house): not. The hull only ever makes an object bigger, the cautious direction.
    `box`, the object's plan bounding box (x0, y0, x1, y1), is its footprint whenever the points don't outline
    one (fewer than 3, or all in a line, as a sphere's seam is): a solid always covers some ground, so such
    points under-describe it."""
    lot = [(float(x), float(y)) for x, y in lot_ring]
    if len(lot) > 1 and lot[0] == lot[-1]:
        lot = lot[:-1]
    if len(lot) < 3:
        return False
    if _ring_area(lot) < 0:
        lot.reverse()
    hull = _hull(points)
    if (len(hull) < 3 or _ring_area(hull) <= 1e-12) and box is not None:
        x0, y0, x1, y1 = box
        hull = _hull([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    if len(hull) < 3 or _ring_area(hull) <= 1e-12:
        return False
    part = _clip(lot, hull)
    if len(part) < 3:
        return False
    area = abs(_ring_area(part))
    perimeter = sum(((part[i][0] - part[i - 1][0]) ** 2 + (part[i][1] - part[i - 1][1]) ** 2) ** 0.5
                    for i in range(len(part)))
    return perimeter > 0 and 2 * area / perimeter > reach


# ---- every callback Rhino or Eto calls goes through guard() -----------------------------------------------------
# On the Mac an exception that escapes a callback into native code (a view's paint, a cell formatting event, a
# display conduit's draw, an idle or document event) aborts Rhino outright (seen 2026-10-20: an Eto paint handler
# raised; xamarin_process_managed_exception → abort). So no callback may raise: guard() catches everything, writes
# it to the log, says it once on the command line (REPORT, set by the Rhino command), and returns a harmless
# fallback (draw nothing, change nothing). tests/test_check.py scans the plugin for any callback without it.
ERROR_LOG = None          # the log file's path (the Rhino command sets it; else <temp>/gordium_errors.log)
REPORT = None             # a function(text) that writes a line to Rhino's command line
_reported = set()


def guard(fn, where, fallback=None):
    """fn, wrapped so it never raises: an exception is logged (with where it happened) and fallback returned."""
    def safe(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:                      # noqa: BLE001  (any error: native code must never see it)
            import os
            import tempfile
            import time
            import traceback
            path = ERROR_LOG or os.path.join(tempfile.gettempdir(), "gordium_errors.log")
            try:
                with open(path, "a", encoding="utf-8") as log:
                    log.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + where + "\n" + traceback.format_exc() + "\n")
                if REPORT is not None and where not in _reported:
                    _reported.add(where)
                    REPORT("Gordium: ⚠ couldn't " + where + " (it was skipped; details in " + path + ")")
            except Exception:                  # noqa: BLE001  (even the report must not raise)
                pass
            return fallback
    return safe


# ---- the start box (spec A, as approved 2026-10-20): what it shows, decided here so CI can test it ------------
NOT_CHECKED_YET = "Not checked yet: overlays (historic, gorge, flood)"   # (pitched roofs are measured)
ENTERED = "entered by you"
FLOOR_TO_FLOOR = 11 + 8 / 12                 # ft: the starting house's floor height (editable later in GordiumFacts)
CORNER_CHOICES = ["Not answered", "No: one street", "Yes: two streets"]   # the Street side row's question
SUGGESTED = "suggested by Gordium"
GROUND_CHOICES = [("spot", "Place spot grades…"), ("terrain", "Pick terrain…"),
                  ("regrade", "I'll regrade: set finished ground…")]


def lot_size(area):
    """The lot's area as the site facts say it: whole square feet rounded down, as the checker's Lot area row does
    (never in the architect's favour; to the nearest, 106 Ithaca Rd read 7,034 sf here and 7,033 sf in the row)."""
    import math
    return f"{math.floor(area + 1e-9):,} sf" if isinstance(area, (int, float)) else "area not known"


def lot_source(surveyed, source=None):
    """Where the lot came from: your survey, or the tax map (with the map service the lookup read it from)."""
    return "your survey" if surveyed else "the tax map (±2 ft, approximate)" + (" · " + source if source else "")


NO_LOT = "no lot yet: draw it on the Site layer, or Draw puts down the sample lot (106 Ithaca Rd)"
# a file with no lot the box can use (Edit site… in an empty file): its own lot, drawn or picked (never the sample)
LOT_MISSING = "no lot yet: draw it, or pick a closed outline on the Site layer"


def lot_text(area, surveyed, source=None):
    """The Lot row: "6,570 sf · from the tax map (±2 ft, approximate)" or "… · from your survey"; with the map
    service the lookup read it from ("… · NYS Tax Parcels Public")."""
    return lot_size(area) + " · from " + lot_source(surveyed, source)


def ground_text(ground):
    """The Ground row: what the ground is and where it came from ("flat at the lot level · as drawn", "4 spot
    grades, 0'-0" to 3'-0" · placed by you", "terrain · picked by you", or finished ground you set)."""
    kind = ground.get("kind") or "flat"
    if kind == "flat":
        return "flat at the lot level · as drawn"
    span = ground.get("range") or ""
    what = {"spot": f"{ground.get('count', 0)} spot grades", "terrain": "terrain",
            "regrade": f"finished ground you set ({ground.get('count', 0)} spot grades)"}[kind]
    return what + (", " + span if span else "") + " · " + (ground.get("source") or
                                                         ("picked by you" if kind == "terrain" else "placed by you"))


STREET_WORDS = {"road": "rd", "street": "st", "avenue": "ave", "place": "pl", "drive": "dr", "lane": "ln",
                "court": "ct", "boulevard": "blvd", "terrace": "ter", "circle": "cir", "parkway": "pkwy",
                "highway": "hwy", "north": "n", "south": "s", "east": "e", "west": "w"}


def address_street(address, street):
    """The street of `address` in the address's own words ("Ithaca Road" from "106 Ithaca Road, Ithaca, NY"), when
    it is `street` (a looked-up street name: "ITHACA RD"); else None. Compared word by word with the usual
    abbreviations (Road = Rd), never by a part of a name."""
    first = str(address or "").split(",", 1)[0].split()
    while first and any(ch.isdigit() for ch in first[0]):        # the house number (106, 106A, 106-108)
        first = first[1:]

    def words(text):
        return [STREET_WORDS.get(w, w) for w in str(text or "").lower().replace(".", " ").split()]

    return " ".join(first) if first and words(" ".join(first)) == words(street) else None


def street_name(state):
    """The street the highlighted lot line is on, by name, only when that line's street is known (a lookup's
    street, or the sample's); else the line itself, so the architect checks which line it is (the street line
    sets the front, side and rear yards: never named from the address alone)."""
    return state.get("street_name") or "the highlighted line"


def street_name_after_pick(name, lines, picked, tolerance=0.5, ids=None):
    """The street's name to keep when the architect picks the street side again (`picked`: the lot line clicked,
    [[x, y], [x, y]] in feet): when the lines carry their own street names (`ids` matching them one for one,
    street_lines.matching_ids), the clicked line's own name (None if it has none: asked); else `name`, the street's
    name as found, if the line is one of that street's own `lines` (within `tolerance` ft at each end, either way
    round); else None, and the architect is asked (a name is never carried to a line it wasn't found on: a B Ave
    line never saved as A St, arch-fixes-2 review round 9)."""
    def near(p, q):
        return abs(p[0] - q[0]) <= tolerance and abs(p[1] - q[1]) <= tolerance

    a, b = picked
    own = _street_lines().matching_ids(lines, ids)
    for k, (c, d) in enumerate(lines or []):
        if (near(a, c) and near(b, d)) or (near(a, d) and near(b, c)):
            return own[k] if own is not None else (name or None)
    return None


STREET_LABEL = "Front lot line (on the street)"      # the box's row, in an architect's words (Ben, 2026-10-21)
STREET_HELP = "the highlighted blue line is the lot line on the street; Gordium measures the front yard from it"
ZONE_TICK = "This is the lot's district"


def street_pick_prompt(corner, picked):
    """What the command line asks while the architect picks the street side: on a corner lot, every lot line on a
    street, one click each, Enter when done (as Edit site lets it); otherwise the one line."""
    if corner:
        return ("Click each lot line on a street (" + str(picked) + " picked); Enter when done")
    return "Click the lot line on the street"


def street_lines_after_picks(lines, picks, corner):
    """The street lines after the architect's clicks: on a corner lot every line clicked, once each, in order (the
    yards wait for the front to be settled whatever they are: §325-19C); otherwise as street_lines_after_pick. No
    clicks (Esc, or Enter at once): the lines as they were."""
    if not picks:
        return lines
    if not corner:
        return street_lines_after_pick(lines, picks[0])
    out = []
    for p in picks:
        if not any(street_lines_after_pick([q], p) == [list(map(list, q))] for q in out):
            out.append(p)
    return out


def pick_street(old_lines, old_ids, picked, name, tolerance=0.5):
    """(street lines, their street names) after the architect clicks a lot line as the street side (`picked`) and
    names its street (`name`, found or typed; None: unnamed). THE one order of steps (arch-fixes-2 review rounds
    9-11, where a name given for one line kept landing on other lines and two streets, or "one street or two?",
    became one): the name goes on the clicked line ONLY; every other line keeps the street it was known to be on,
    or none; then the street lines follow from those names (street_lines_after_pick: the clicked line's own street
    when the lines are known to be two streets, else every line). A line nobody named stays unnamed, so the
    measuring still reads it from the drawing (a corner: one street or two?, needs review)."""
    def near(p, q):
        return abs(p[0] - q[0]) <= tolerance and abs(p[1] - q[1]) <= tolerance

    a, b = picked
    lines = [list(map(list, line)) for line in old_lines or []]
    hits = [k for k, line in enumerate(lines)
            if (near(a, line[0]) and near(b, line[-1])) or (near(a, line[-1]) and near(b, line[0]))]
    if not hits:                                           # a line not among them: that line alone
        return [list(map(list, picked))], ([name] if name else None)
    ids = list(_street_lines().matching_ids(lines, old_ids) or [None] * len(lines))
    if name:
        ids[hits[0]] = name
    kept = street_lines_after_pick(lines, picked, tolerance, ids=ids)
    out = [ids[next(k for k, line in enumerate(lines) if line == q)] for q in kept]
    return kept, (out if any(out) else None)


def street_lines_after_pick(lines, picked, tolerance=0.5, ids=None):
    """The street lines after the architect clicks a lot line as the street side: the whole street as it was when
    the line is one of its own (106's eight: keeping only the one clicked measured the front yard from part of the
    street, a false pass: review round 3, F4); only that street's lines when the lines are known to be on two
    streets (`ids`); never fewer on a guess from the drawing (a street that bends, or lines nobody named: the
    measuring asks about them; review round 6, P1); a line not among them: that line."""
    def near(p, q):
        return abs(p[0] - q[0]) <= tolerance and abs(p[1] - q[1]) <= tolerance

    a, b = picked
    hits = [k for k, (c, d) in enumerate(lines or []) if (near(a, c) and near(b, d)) or (near(a, d) and near(b, c))]
    if not hits:
        return [picked]
    ids = _street_lines().matching_ids(lines, ids)        # names that don't match the lines: unnamed (round 8)
    if street_verdict(lines, ids)[0] == "two" and ids[hits[0]]:   # two streets, the clicked line's known: its own
        mine = ids[hits[0]]                                # its own lines, by street_verdict's own comparison
        return [list(map(list, line)) for k, line in enumerate(lines) if _street_lines().same_street(ids[k], mine)]
    return [list(map(list, line)) for line in lines]


_STREETS = {}


def _street_lines():
    """model_measurement/street_lines.py, the one decision of one street or two (the measuring's too), loaded by
    its path: inside Rhino only this folder is on the path."""
    if "m" not in _STREETS:
        import importlib.util
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "model_measurement",
                            "model_measurement", "street_lines.py")
        spec = importlib.util.spec_from_file_location("gordium_street_lines", os.path.normpath(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _STREETS["m"] = module
    return _STREETS["m"]


def street_verdict(lines, ids=None):
    """("one" | "two" | "unsure", total swing): street_lines.street_verdict, the measuring's own."""
    return _street_lines().street_verdict(lines, ids)



def box_rows(state, flat=None):
    """The start box, top to bottom: one dict per row {key, label, text, actions [(action, label, enabled)],
    tick (label, checked) or None, review (an amber line) or None, check ("I checked this", ticked) or None}.
    `state`: address, zone, zone_source, district_confirmed, use, use_name, lot_area, lot_surveyed, street_name,
    ground {kind, count, range}, no_regrading, lookup (this session's), doubts, live, checked, lot_missing.
    `flat` (default FLAT_GROUND): the MVP shows no Ground row (flat ground is assumed). Until there is a lot, no
    "Use my survey…" or street "Change…" (nothing to change yet: the architect's second pass, 6); "Draw my lot…"
    when a lookup gave only the City's guide, or there is no lot."""
    look = state.get("lookup") or {}
    doubts, live = state.get("doubts") or {}, state.get("live") or {}
    checked = set(state.get("checked") or [])
    has_lot = bool(state.get("has_lot") or state.get("lot_area") is not None or state.get("lot_surveyed"))

    def review(key):                  # a doubt about what is drawn (or this lookup's zone): amber, why, I checked this
        why = live.get(key) or doubts.get(key)
        if key == "zone":             # the zone's own doubts and the overlays found, together
            why = " ".join(t for t in (live.get("zone"), live.get("overlays")) if t) or None
        return {"review": "? " + why if why else None,
                "check": ("I checked this", key in checked) if key in CHECKABLE and key in doubts else None}

    lot_actions = [("lot", "Use my survey…", not state.get("lot_surveyed"))] if has_lot else []
    if look.get("guide") or state.get("lot_missing"):
        lot_actions.insert(0, ("draw_lot", "Draw my lot…", True))
    rows = [
        {"key": "address", "label": "Address", "text": state.get("address") or "",
         "actions": [("lookup", "Looking up…" if look.get("looking") else "Look up", not look.get("looking"))],
         "tick": None, "matches": look.get("matches") or [],
         "status": LOOKING.format(look["looking"]) if look.get("looking") else None},
        {"key": "zone", "label": "Zoning district", "text": zone_row_text(state),
         "actions": [("zone", "Change", True)], "tick": (ZONE_TICK, bool(state.get("district_confirmed")))},
        {"key": "use", "label": "Use", "text": state.get("use_name") or state.get("use") or "—",
         "actions": [("use", "Change", True)], "tick": None},
        {"key": "lot", "label": "Lot",
         "text": (LOT_MISSING if state.get("lot_missing") else
                  lot_text(state.get("lot_area"), state.get("lot_surveyed"), state.get("lot_source"))
                  if has_lot else NO_LOT),
         "actions": lot_actions, "tick": None},
        {"key": "street", "label": STREET_LABEL, "help": STREET_HELP,
         "text": street_name(state) if (state.get("street_name") or has_lot) else "set from the lot, once there is one",
         "actions": [("street", "Change…", True)] if has_lot else [], "tick": None,   # nothing to change yet: hidden
         "choice": ("Corner lot?", CORNER_CHOICES, {None: 0, False: 1, True: 2}[state.get("corner_lot")])},
        {"key": "ground", "label": "Ground", "text": ground_text(state.get("ground") or {}),
         "actions": [(k, t, True) for k, t in GROUND_CHOICES],
         "tick": ("No regrading near the house", bool(state.get("no_regrading")))},
    ]
    for r in rows:
        r.update(review(r["key"]))
    if FLAT_GROUND if flat is None else flat:      # the MVP: no Ground row (flat ground is assumed)
        rows = [r for r in rows if r["key"] != "ground"]
    return rows


# ---- the address lookup (design_checker.lookup_box runs it; this turns its answer into the box's choices) ----
#
# What the box keeps, and for how long (review round 1 of PR #19):
# - saved_ui["doubts"] {row: reason}: what is doubtful about the lot, street side and ground DRAWN in the model. It
#   changes only when that thing is replaced (a lookup that draws a new lot) or the architect confirms it (I checked
#   this) or changes it; a failed, empty or own-lot lookup never touches it. Only a reason its sources allow keeping
#   is saved; otherwise a plain DOUBT_KEPT.
# - keys starting with "_" belong to this box session only (the lookup's live wording, its asks and matches, the
#   City's zones and street name, the model edits to undo on Cancel) and are never written to the .3dm
#   (storable_ui, the one write boundary).

NO_RULES = "The City map says {zone}; Gordium doesn't have {zone}'s rules yet: pick a district only if you know it applies."


NO_DISTRICT = "The City zoning map gave no district for this lot: pick one"


def city_day(now=None):
    """The City's own day (Ithaca: America/New_York) at `now` (UTC; default the present), as YYYY-MM-DD: the day a
    lookup was checked and a Draw is saved, never the UTC day (after about 8 pm in Ithaca that is tomorrow). US
    Eastern time by the federal rule (15 U.S.C. 260a: from 2 am on the second Sunday of March to 2 am on the
    first Sunday of November, UTC-4; otherwise UTC-5), so no time-zone database is needed in Rhino's Python."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    now = now.astimezone(_dt.timezone.utc).replace(tzinfo=None)

    def sunday(month, nth):              # the nth Sunday of the month in now's year
        first = _dt.datetime(now.year, month, 1)
        return first + _dt.timedelta(days=(6 - first.weekday()) % 7 + 7 * (nth - 1))
    summer = sunday(3, 2) + _dt.timedelta(hours=7) <= now < sunday(11, 1) + _dt.timedelta(hours=6)
    return (now - _dt.timedelta(hours=4 if summer else 5)).date().isoformat()


def two_zones_ask(zones):
    """site_lookup's ask when the City map puts a lot in more than one zone, word for word (lookup._zoning)."""
    return f"This lot is in {' and '.join(zones)}: pick the zone that applies."


def no_rules(said, unknown):
    """The box's line when the City map's district (or one of its districts) has no rules in Gordium."""
    if len(said) == 1:
        return NO_RULES.format(zone=said[0])
    missing = ("the rules for " + " or ".join(unknown)) if len(unknown) > 1 else unknown[0] + "'s rules"
    return (f"The City map puts this lot in {' and '.join(said)}; Gordium doesn't have {missing} yet: pick the "
            "district that applies only if you know it.")


def zone_row_text(state):
    """The district row: the district and where it came from. None set: "not set" (never a past "suggested"). The
    lookup's own words ("City zoning map says R-1b (checked 2026-10-21)") only this session and only for the
    district it said, still suggested; a district the architect picked is theirs."""
    zone, source = state.get("zone"), state.get("zone_source") or ENTERED
    if not zone:
        return "— · not set"
    said = state.get("zone_said") or {}
    if said.get("zone") == zone and source.startswith(SUGGESTED):
        source = SUGGESTED + " · City zoning map says " + zone + " (checked " + said["date"] + ")"
    return zone + " · " + source


def saved_sources(saved_ui, state):
    """The box's choices to keep after it: the district's source as the box ends with it (the architect's pick is
    theirs, so a looked-up "suggested" never outranks it on reopen)."""
    saved_ui = dict(saved_ui)
    if state.get("zone") and state.get("zone_source"):
        saved_ui["zone_source"] = state["zone_source"]
    elif not state.get("zone"):
        saved_ui.pop("zone_source", None)
    return saved_ui


def zone_picked(state, zone, first):
    """The architect picked a district in the box's dropdown: it is set (and theirs, unless it is the one the box
    opened with), so Draw follows at once (draw_reason)."""
    state["zone"] = zone
    if zone != first:
        state["zone_source"] = ENTERED
    return state
LOOKUP_LIMIT_S = 45                               # the whole lookup; the box says so, the Rhino side stops it then
LOOKING = "Looking up {}… (up to %d s)" % LOOKUP_LIMIT_S
CHECKABLE = ("lot", "street", "ground")          # what "I checked this" settles (the district has its own tick)
DOUBT_KEPT = "The lookup found this doubtful (its reason came from a source that can't be kept): check it."
LOOKUP_SAYS = {                                   # the box's line when a lookup couldn't fill it in
    "not_found": "No City of Ithaca address found for {query}: check the spelling, or draw the lot.",
    "outside_city": "{message}",
    "offline": "Couldn't reach the map services (offline?): enter the site by hand.",
    "error": "A map service answered with an error: enter the site by hand.",
    "timeout": "The lookup took too long: enter the site by hand, or try again.",
    "multiple": "{message} Pick one under Address, then Look up again.",
}
ROW_OF = {"address": "lot", "parcel": "lot", "lot": "lot", "street_side": "street", "corner_lot": "street",
          "ground": "ground", "zone": "zone", "overlays": "overlays"}
SOURCE_OF = {"address": "NYS Geocoder", "lot": "NYS Tax Parcels Public", "street": "City roads",
             "ground": "USGS 3DEP, today's ground", "zone": "City zoning map, used live"}   # if the payload has none
GUIDE = ("The State's tax map didn't answer; the City's outline is shown as a dashed guide only (it can't be kept): "
         "Draw my lot… over it, or pick your own outline.")


def storable_ui(saved_ui):
    """What of the box's choices may be written into the .3dm: never a session key ("_…": the lookup's live wording,
    the City's zones and street name, its asks)."""
    return {k: v for k, v in (saved_ui or {}).items() if not str(k).startswith("_")}


def lookup_says(payload):
    """The line for a lookup that didn't find the site (None when it did)."""
    status = (payload or {}).get("status")
    if status in (None, "found"):
        return None
    text = LOOKUP_SAYS.get(status, LOOKUP_SAYS["error"])
    return text.format(query=payload.get("query") or "this address", message=payload.get("message") or "").strip()


def lookup_may_replace(facts, saved_ui):
    """Whether a lookup may replace the model's lot: none yet, or the one a lookup or the sample drew (and still the
    lot). Never one the architect drew, picked or surveyed."""
    lot = (facts or {}).get("lot_id")
    return not lot or lot == (saved_ui or {}).get("replaceable_lot")


def lookup_choices(payload, facts, saved_ui, zones=(), replaces=True):
    """(facts, saved_ui) after a lookup, as a pick returns them. Each found fact a suggestion with its own service's
    name, never confirmed (the district must be ticked again: "_reconfirm"). The lot, street side and ground (and
    their doubts) only when the lookup's lot replaces the model's (`replaces`); for the architect's own lot, only
    the address and the district. A lookup that found nothing changes nothing but its own line."""
    payload = payload or {}
    facts, saved_ui = dict(facts), dict(saved_ui)
    look = {"status": payload.get("status") or "error", "says": lookup_says(payload),
            "asks": list(payload.get("asks") or []), "matches": list(payload.get("matches") or []),
            "query": payload.get("query")}
    saved_ui["_lookup"] = look
    if look["status"] != "found":
        return facts, saved_ui
    got, details = payload.get("facts") or {}, payload.get("details") or {}
    labels, kept = payload.get("labels") or {}, payload.get("kept_reasons") or {}

    def value(name):
        return (got.get(name) or {}).get("value")

    def label(name, row):
        return labels.get(name) or SOURCE_OF[row]

    live, keep = {}, {}
    for name, d in details.items():          # every doubtful or asked fact's reason, by row; reasons add up
        if d.get("status") in ("needs_review", "ask") and d.get("reason"):
            row = ROW_OF.get(name, name)
            live[row] = _merged(live.get(row), d["reason"])
            keep[row] = _merged(keep.get(row), kept.get(name) or DOUBT_KEPT)
    found_overlays = value("overlays") or []
    if found_overlays:                       # what was found, by name, not only that something was
        live["overlays"] = _merged("Found on this lot: " + "; ".join(found_overlays) + ".", live.get("overlays") or "")
    if value("address"):
        facts["address"] = value("address")
        saved_ui["address_source"] = SUGGESTED + " · " + label("address", "address")
    zone = value("zone")
    names = {z.lower(): z for z in zones} if zones else {}
    said = zone if isinstance(zone, list) else [zone] if zone else []
    if len(said) > 1 and live.get("zone"):
        # site_lookup's own two-zones ask: the box says it once, its own way (no_rules on the row, or the amber
        # question), so the lookup's words never say it again beside it (review of 8b8af5e, finding 1)
        live["zone"] = " ".join(live["zone"].replace(two_zones_ask(said), " ").split())
        if not live["zone"]:
            live.pop("zone")
    known = [names[z.lower()] for z in said if z.lower() in names] if zones else list(said)
    unknown = [z for z in said if zones and z.lower() not in names]
    if not said:                                 # found, but the zoning map gave no district: never the last
        # address's district and its "suggested" left standing (zone round 3)
        facts.pop("zone", None)
        for key in ("zone_source", "_zones_found", "_zone_said"):
            saved_ui.pop(key, None)
        live["zone"] = _merged(live.get("zone"), NO_DISTRICT)
    if unknown:
        # the City map names a district Gordium has no rules for (alone or beside one it has): never another
        # district preselected or called suggested in its place; none is set until the architect picks one. With
        # two zones the row's own line names both and asks which applies (no_rules): said once, never again as the
        # amber question too (Rhino check of 7efb1bd, 2026-10-22)
        facts.pop("zone", None)
        saved_ui.pop("zone_source", None)
        saved_ui.pop("_zones_found", None)
        live["zone"] = _merged(live.get("zone"), no_rules(said, unknown))
        known = []
    elif len(known) > 1:                         # two zones: the box asks which applies
        saved_ui["_zones_found"] = known
        facts["zone"] = known[0]
    elif known:
        facts["zone"] = known[0]
        saved_ui.pop("_zones_found", None)
    saved_ui.pop("_zone_said", None)
    if known:                                    # stored: plain, never a date that goes stale on reopen
        saved_ui["zone_source"] = SUGGESTED + " · " + label("zone", "zone")
        when = payload.get("checked") or (got.get("zone") or {}).get("date")   # the City's day it was checked
        if len(known) == 1 and when:             # shown this session only ("_"), as the map says it, with its date
            saved_ui["_zone_said"] = {"zone": known[0], "date": str(when)}
    saved_ui["_reconfirm"] = True                # a looked-up district is the architect's only once ticked again
    saved_ui["_live"] = {k: v for k, v in live.items() if k in ("zone", "overlays")}
    if not replaces:                             # the architect's own lot: its lot, street side and ground stay
        return facts, saved_ui
    side = value("street_side") or {}
    # a street's name and source only with the street line this lookup draws (the State's lot): the City's parcels
    # are a guide only, no line drawn, so nothing is said of a line that isn't there (review round 2 of 8b8af5e)
    w = payload.get("writes") or {}
    draws_line = bool(w.get("lot_ring") and w.get("street_line"))
    if side.get("street") and draws_line:
        # the address's own street is named in the address's words, which are kept: so the name is still there
        # after Draw (it was this session's only, "the highlighted line" on reopen: Rhino check, 2026-10-22);
        # another street's name may be kept only when its source allows
        own = address_street(facts.get("address"), side["street"])
        street_kept = payload.get("street_storable") or own is not None
        saved_ui.pop("street_name" if not street_kept else "_street_name", None)
        saved_ui["street_name" if street_kept else "_street_name"] = own or side["street"].title()
        # credited to where each part came from: a name in the address's words is the address's (its geocoder),
        # never the street service's, which is used live only (review of 8b8af5e, finding 2)
        saved_ui["street_source"] = SUGGESTED + " · " + (
            f"named as in the address ({label('address', 'address')}), the line from {label('street_side', 'street')}"
            if own else label("street_side", "street"))
    else:                                        # the replaced lot's street name goes with its street lines (the
        saved_ui.pop("street_name", None)        # sample's Ithaca Rd never named a looked-up lot's street), and so
        saved_ui.pop("_street_name", None)       # does its source: the street side's own, or none (headless check)
        if side and draws_line:
            saved_ui["street_source"] = SUGGESTED + " · " + label("street_side", "street")
        else:
            saved_ui.pop("street_source", None)
    corner = value("corner_lot")
    streets = side.get("streets") or {}
    if corner == "no":
        facts["corner_lot"] = False
    elif corner == "yes" or (corner == "ask" and len(streets) > 1):
        facts["corner_lot"] = True               # it faces two streets (the box asks which line is the front)
    else:
        facts.pop("corner_lot", None)            # unknown: asked, never guessed
    if corner:
        saved_ui["corner_source"] = SUGGESTED + " · " + label("corner_lot", "street")
    lot = value("lot") or {}
    writes = payload.get("writes") or {}
    if lot:
        facts["lot_surveyed"] = False            # the tax map: ±2'-0" and the 2'-0" starting-house margin apply
        saved_ui["lot_source"] = label("lot", "lot")
        saved_ui["lot_area"] = lot.get("area_sf")
    if writes.get("spots") and not FLAT_GROUND:  # the MVP assumes flat ground: the lookup's ground is never used
        saved_ui["ground_kind"] = "spot"
        saved_ui["ground_source"] = SUGGESTED + " · " + label("ground", "ground")
    zs = [p[2] for p in writes.get("spots") or []]
    if FLAT_GROUND and zs:                       # said, never used: how much the ground the lookup found falls
        saved_ui["ground_fall"] = round(max(zs) - min(zs), 1)
    else:
        saved_ui.pop("ground_fall", None)
    if lot and not writes.get("lot_ring"):      # the City's parcels: a guide only, never kept
        look["guide"] = True
        live["lot"] = GUIDE + (" " + live["lot"] if live.get("lot") else "")
    # the doubts about what is now drawn: this lookup's, for the rows it replaced; earlier ticks don't carry over
    saved_ui["doubts"] = {k: v for k, v in keep.items() if k in checkable()}
    saved_ui["_live"].update({k: v for k, v in live.items() if k in checkable()})
    saved_ui["checked"] = []
    return facts, saved_ui


def _merged(old, reason):
    """Reasons add up, each said once (one that already holds another replaces it)."""
    if not old or old in reason:
        return reason
    return old if reason in old else old + " " + reason


def unsettled(saved_ui, checked=None):
    """The checker's facts["unsettled"]: each doubt about what is drawn the architect hasn't ticked I checked this
    for (or changed). Empty when there are none. Only kept-safe wording (the doubts saved)."""
    done = set(checked if checked is not None else (saved_ui or {}).get("checked") or [])
    return {k: v for k, v in ((saved_ui or {}).get("doubts") or {}).items() if k in checkable() and k not in done}


def checkable():
    """The rows "I checked this" settles, and so the doubts kept: with the MVP's flat ground the ground is not the
    lookup's, so it has no doubt to keep (it would hold height and stories at needs review with no row to clear)."""
    return tuple(k for k in CHECKABLE if not (FLAT_GROUND and k == "ground"))


def settle(saved_ui, row):
    """The architect changed that row (picked another street line, their survey or a lot they drew, other ground):
    it is theirs now, so no doubt about it is left."""
    saved_ui = dict(saved_ui)
    saved_ui["doubts"] = {k: v for k, v in (saved_ui.get("doubts") or {}).items() if k != row}
    saved_ui["_live"] = {k: v for k, v in (saved_ui.get("_live") or {}).items() if k != row}
    saved_ui["checked"] = [k for k in saved_ui.get("checked") or [] if k != row]
    if row == "lot":
        saved_ui["replaceable_lot"] = None           # never replaced by a later lookup
        saved_ui.pop("lot_source", None)
    if row == "street":                          # the architect's own line: no looked-up name stays on it
        saved_ui.pop("_street_name", None)
        saved_ui.pop("street_name", None)
    return saved_ui


UNDER_A_BOX = ("check", "save_facts", "open_box")   # what may not happen while a start box is open


def allowed(action, box_open):
    """Whether `action` may run now: a check, writing the lot facts and opening a second start box never happen while
    a start box is open (its own edits wait for it to close); anything else may."""
    return not (box_open and action in UNDER_A_BOX)


def pick_effect(what, outcome, facts, saved_ui):
    """(facts, saved_ui) after one of the start box's picks, from what the pick gave (the Rhino side only gathers it):
    street: {"picks": the lot lines [a, b] clicked, "name": the clicked line's street (street_name_after_pick, else
    typed; None: unnamed)}; lot (Use my survey…): the outline picked; draw_lot: the outline drawn; terrain: the
    surface picked; spot / regrade: the points placed. Esc, Enter or nothing picked (`outcome` empty): nothing
    changes, every doubt stays (eval-integrity audit: Esc on Place spot grades wiped the ground's doubt).
    The street lines change only through set_street_lines (arch-fixes-2 round 7): on a corner lot every line
    clicked, no one name for them; otherwise pick_street, the name on the clicked line only (rounds 9-11)."""
    facts, saved_ui = dict(facts), dict(saved_ui)
    if not outcome or (what == "street" and not outcome.get("picks")):
        return facts, saved_ui
    if what == "street":
        picks, name = outcome["picks"], outcome.get("name")
        saved_ui = settle(saved_ui, "street")          # the architect's line: no looked-up name stays on it
        if facts.get("corner_lot") is True:            # a corner lot: every line on a street (two streets: unnamed)
            set_street_lines(facts, street_lines_after_picks(facts.get("street_line"), picks, True))
        else:
            lines, ids = pick_street(facts.get("street_line"), facts.get("street_ids"), picks[0], name)
            set_street_lines(facts, lines, ids)        # the name on the clicked line only
            saved_ui["street_name"] = name
        saved_ui["street_source"] = ENTERED
    elif what in ("lot", "draw_lot"):
        facts = after_lot_pick(facts, outcome) if outcome != facts.get("lot_id") else facts
        facts["lot_surveyed"] = what == "lot"          # Use my survey…: a survey; drawn over the guide: not
        saved_ui = settle(saved_ui, "lot")
        if what == "draw_lot":
            saved_ui["lot_source"] = "drawn by you"
    elif what == "terrain":
        saved_ui.update(terrain_id=outcome, ground_kind="terrain")
        saved_ui = settle(saved_ui, "ground")
    elif what in ("spot", "regrade"):
        saved_ui = after_ground_pick(saved_ui, what, len(outcome))
    return facts, saved_ui


def after_ground_pick(saved_ui, what, placed):
    """Place spot grades / I'll regrade, with `placed` points actually added: the ground is the architect's only
    then. Esc or Enter with none placed changes nothing (review round 1: it settled a doubtful ground)."""
    if not placed:
        return dict(saved_ui)
    saved_ui = settle(saved_ui, "ground")
    saved_ui["ground_kind"] = what
    saved_ui.pop("ground_source", None)
    return saved_ui



def parse_feet(text):
    """A length the architect typed, in feet: 11'-8", 1' 6", 6", 6 in, 1.5, 1.5 ft, 2' -> feet; empty -> 0.0;
    anything it can't read -> None, never a silent 0."""
    import re
    t = (text or "").strip().lower()
    if not t:
        return 0.0
    t = re.sub(r"\s*(feet|foot|ft)\b", "'", t)
    t = re.sub(r"\s*(inches|inch|in)\b", '"', t)
    num = r"(\d+(?:\.\d+)?)"
    m = re.fullmatch(num + r"\s*'?", t)                                  # feet: 2, 2', 1.5 ft
    if m:
        return float(m.group(1))
    m = re.fullmatch(num + r"\s*'\s*-?\s*" + num + r'\s*"?', t)        # feet and inches: 11'-8", 1' 6
    if m:
        return float(m.group(1)) + float(m.group(2)) / 12
    m = re.fullmatch(num + r'\s*"', t)                                  # inches alone: 6", 6 in
    if m:
        return float(m.group(1)) / 12
    return None


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


BUFFER_UNREAD = "Design buffer not understood: type it like 1'-6\" or 6\""


def draw_reason(state):
    """Why Draw is off, in one line; "" when it is on."""
    if not state.get("zone"):
        return "Pick the district to continue."
    if not state.get("district_confirmed"):
        return "Confirm the district to continue."
    if parse_feet(state.get("design_buffer")) is None:
        return BUFFER_UNREAD
    if state.get("lot_missing"):
        return "Draw or pick the lot to continue."
    return ""


def can_draw(state):
    """Draw is on only once the district is confirmed (a looked-up district is only a suggestion), the design
    buffer, if typed, can be read, and there is a lot."""
    return draw_reason(state) == ""


def starting_house_fact(note, today):
    """The site fact for how far the starting house keeps back from the limits: Gordium's own figure, so never
    "confirmed by you" (the architect didn't confirm it). None when no house was drawn (`note` None)."""
    if not note:
        return None
    # the panel puts "Starting house: " in front, and it describes the house as Gordium drew it (the architect
    # may since have moved or replaced it), so it says so
    said = note[len("Starting house: "):] if note.startswith("Starting house: ") else \
        "it " + note[len("Starting house "):] if note.startswith("Starting house ") else note
    return {"value": "as first drawn, " + said, "source": SUGGESTED, "confirmed_by": None, "date": today}


def uncertain(state):
    """The one amber line for a case the box can't settle by itself, with what to do; None when there's none."""
    says = (state.get("lookup") or {}).get("says")
    question = _question(state)
    return " · ".join(t for t in (question, says) if t) or None     # never one instead of the other


def _question(state):
    """Every question the box still has (each one, never only the first)."""
    asks = []
    if state.get("corner_lot") is None:          # never guessed: unanswered, the yards wait for it (§325-19C)
        asks.append("Does this lot face two streets? Answer Corner lot? under " + STREET_LABEL)
    elif state.get("corner_lot"):
        asks.append("This lot faces two streets: click Change… and pick each lot line on a street")
    if len(state.get("zones_found") or []) > 1:
        asks.append("This lot is in two zones: pick the zone that applies")
    return " · ".join(asks) or None


# The MVP assumes flat ground (Ben, 2026-10-20): flat at the lot level and finished, so height and stories are
# checked (with "assuming flat ground" on their rows and in the report). The spot-grade, terrain and regrade paths
# stay, behind this one switch: set it to False to bring the Ground row back.
FLAT_GROUND = True
ASSUMED_FLAT = "assuming flat ground"
ASSUMED_SOURCE = "assumed (flat ground, the MVP's rule)"


def ground_facts(state, lot_level, flat=None):
    """The facts the checker gets from the Ground row (the checker never sees where a fact came from). With the MVP's
    flat-ground switch on: flat at the lot level, finished, and said to be assumed. Otherwise: ground you set as
    finished, or ticked "No regrading near the house", counts as the finished grade the code measures from; ground
    only as it is (existing), unticked, gives height and stories needs review (spec C5)."""
    if FLAT_GROUND if flat is None else flat:
        return {"grade_is": "finished", "ground_is_flat": True, "grade_elevation": lot_level, "grade_from": None,
                "ground_assumed": "flat", **({"ground_fall": state["ground_fall"]} if state.get("ground_fall") else {})}
    ground = state.get("ground") or {}
    kind = ground.get("kind") or "flat"
    finished = kind == "regrade" or bool(state.get("no_regrading"))
    out = {"grade_is": "finished" if finished else "existing", "ground_assumed": None}
    if kind == "flat":
        out.update(ground_is_flat=True, grade_elevation=lot_level, grade_from=None)
    else:
        out.update(ground_is_flat=None, grade_elevation=None,     # the facts say which points: never the ui state
                   grade_from={"terrain": "terrain", "regrade": "finished_spots"}.get(kind, "spot"))
    return out


def fact_sources(state, today, confirmed):
    """Every fact the box set, as {value, source, confirmed_by, date}: saved in the .3dm beside the facts and
    shown in the panel and the report. `confirmed`: the architect pressed Draw (the district needs its own tick)."""
    by = "you" if confirmed else None
    ground = state.get("ground") or {}
    kind = ground.get("kind") or "flat"

    def fact(value, source, who=by):
        return {"value": value, "source": source, "confirmed_by": who, "date": today}

    return {
        "address": fact(state.get("address") or None, state.get("address_source") or ENTERED),
        "zone": fact(state.get("zone"), state.get("zone_source") or ENTERED,
                     by if state.get("district_confirmed") else None),
        "use": fact(state.get("use_name") or state.get("use"), state.get("use_source") or SUGGESTED),
        # the size, then where it came from, once ("Lot: 6,570 sf · the tax map (±2 ft, approximate) · confirmed…")
        "lot": fact(lot_size(state.get("lot_area")), lot_source(state.get("lot_surveyed"), state.get("lot_source"))),
        # the street's name only when it may be kept (the City's roads may not: "street_name_saved" then None, and
        # the address's street, a kept fact, says it instead)
        "street": fact(street_name({**state, "street_name": state.get("street_name_saved")})
                       if "street_name_saved" in state else street_name(state),
                       state.get("street_source") or SUGGESTED),
        "corner_lot": fact({None: None, False: "no, one street", True: "yes, two streets"}[state.get("corner_lot")],
                           state.get("corner_source") or SUGGESTED),
        # with the MVP's flat ground, an assumption, credited to no service and confirmed by no one
        "ground": (fact("assumed flat" + (f" (the looked-up ground falls about {state['ground_fall']:g} ft across the "
                        "lot; height is checked as if flat)" if state.get("ground_fall") else ""),
                        ASSUMED_SOURCE, None) if FLAT_GROUND else
                   fact(ground_text(ground) + (" · no regrading near the house" if state.get("no_regrading") else ""),
                        "as drawn" if kind == "flat" else ground.get("source") or
                        ("picked by you" if kind == "terrain" else "placed by you"))),
    }


def district_confirmed(mode, zone_fact, zone):
    """Whether "I confirm" starts ticked: never on a new project (GordiumStart); on an existing one only if this
    same district was confirmed at an earlier Draw (its saved source says who confirmed it)."""
    zone_fact = zone_fact or {}
    return mode != "start" and bool(zone_fact.get("confirmed_by")) and zone_fact.get("value") == zone


def is_elevation_view(parallel, direction_z, tolerance=0.01):
    """Whether a viewport is an elevation (Front, Right, Back, Left): a parallel projection looking level, where the
    height limit is labelled."""
    return bool(parallel) and abs(direction_z) <= tolerance


def north_vector(plan_north_deg):
    """True north as a direction in the plan (x, y): plan north (+y) when the plan isn't turned; a looked-up lot
    is drawn turned `plan_north_deg` (lookup_box.frame), and its north arrow turns with it."""
    import math
    t = math.radians(plan_north_deg or 0.0)
    return (-math.sin(t), math.cos(t))


def shorten(text, most):
    """`text` in at most `most` characters, cut at a word and ended "…" when longer (a link can't wrap: the
    architect's review found one pushing the docked panel's text off its right edge)."""
    text = text or ""
    if len(text) <= most:
        return text
    cut = text[:max(1, most - 1)].rsplit(" ", 1)[0].rstrip(" ,·;:")
    return (cut or text[:max(1, most - 1)]) + "…"


def building_name(layer, name, grouped):
    """What the panel calls a building: the starting house Gordium drew (its floors grouped on the massing layer),
    else the object's name, else its layer ("a solid on Building")."""
    if layer == MASSING:
        return "the starting house"
    if name:
        return name + (" (and its group)" if grouped else "")
    return ("a group on " if grouped else "a solid on ") + layer


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


def prune_hosts(hosts, open_serials):
    """The docked panel's hosts for documents still open (and the one made without a document, key 0): a closed
    document's panel is never kept (review: 125 of them after a day of tests)."""
    keep = set(open_serials) | {0}
    return {k: v for k, v in (hosts or {}).items() if k in keep}


def is_plan_view(parallel, direction_z, tolerance=0.99):
    """Whether a viewport is a plan view, where plan labels belong: a parallel projection looking (nearly) straight
    down. Not a perspective (labels sit on the massing) and not an elevation (Front, Right: every plan label piles
    up on the ground line)."""
    return bool(parallel) and direction_z <= -tolerance


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


class BoxSession:
    def __init__(self, table):
        import uuid
        self.table = table
        self.token = uuid.uuid4().hex                  # marks what this session draws and holds
        OPEN_SESSIONS.add(self.token)                  # live: recovery leaves its objects alone
        self.added, self.held = [], []
        self.layers_before = set(table.layer_names())
        self.views = table.save_views()

    def add(self, ids):
        """Objects this session drew: Cancel deletes them, and so does crash recovery (each carries the session's
        mark in the model until Draw)."""
        for i in ids:
            if i:
                self.table.mark_added(i, self.token)
                self.added.append(i)

    def hold(self, object_id):
        """Take an object out of the model for this session: one it drew is simply deleted; any other is held (Cancel
        brings it back as it was)."""
        if not object_id or not self.table.exists(object_id):
            return
        if object_id in self.added:
            self.added.remove(object_id)
            self.table.delete(object_id)
            return
        self.held.append((object_id, self.table.layer_of(object_id)))
        self.table.hold(object_id, self.token)

    def rollback(self):
        """Cancel, Esc or an error: the model as the box found it (objects, the layers it made, the views). Even if
        a step fails, the session is closed (no longer live), so whatever it left is recovered at the next start
        (verification round of PR #19: a raising rollback left its held objects stranded until Rhino restarted)."""
        try:
            for i in self.added:
                if self.table.exists(i):
                    self.table.delete(i)
            for i, layer in self.held:
                if self.table.exists(i):
                    self.table.release(i, layer)
            made = set(self.table.layer_names()) - self.layers_before
            for name in sorted(made, key=lambda n: -n.count("::")):      # sublayers first
                self.table.remove_layer_if_empty(name)
            self.table.restore_views(self.views)
            self.added, self.held = [], []
        finally:
            OPEN_SESSIONS.discard(self.token)

    def commit(self):
        """Draw: what was replaced goes for good, and what was drawn is kept (its session mark cleared)."""
        for i, _ in self.held:
            if self.table.exists(i):
                self.table.delete(i)
        for i in self.added:
            if self.table.exists(i):
                self.table.clear_mark(i)
        self.table.remove_layer_if_empty(HOLDING_LAYER)
        self.added, self.held = [], []
        OPEN_SESSIONS.discard(self.token)


def recover_held(table, live=None):
    """Box sessions Rhino didn't finish (it closed): what they drew deleted, what they held back on the layer it came
    from, so the model is as it was before those boxes opened. A session still open (`live`, OPEN_SESSIONS) is never
    touched. (removed, put back)."""
    live = OPEN_SESSIONS if live is None else live
    removed = [i for i, token in table.added_objects() if token not in live]
    for i in removed:
        table.delete(i)
    back = [(i, layer) for i, layer, token in table.held_objects() if token not in live]
    for i, layer in back:
        table.release(i, layer)
    table.remove_layer_if_empty(HOLDING_LAYER)
    return len(removed), len(back)


def should_recheck(dirty_at, now, running, box_open, wait, last_at=None):
    """Live mode's re-check after an edit: only once the model has been still for `wait` seconds, no check is running,
    no start box is open (its own edits mark the model changed; the check waits for the box to close, then runs:
    verification round of PR #19), and no check has finished since that edit (`last_at`: GordiumStart's own check
    after its box already covers the box's edits)."""
    if last_at is not None and dirty_at and last_at >= dirty_at:
        return False
    return bool(dirty_at) and now - dirty_at >= wait and not running and not box_open


def controls_enabled(box_open, zoom_ok):
    """(the panel's controls, Zoom to): all off while a start box is open; on closing, worked out from the panel as
    it is now, never restored from a list saved when the box opened (the header's buttons may have been rebuilt in
    between, after a document switch: verification round 4 of PR #19). Zoom to also needs a selected, current item
    (`zoom_ok`, as gordium_ui.show decides it)."""
    return (not box_open, (not box_open) and bool(zoom_ok))


def last_check_at(checked_at, document):
    """When the last completed check of THIS document finished (None: none yet). Never a placeholder's time, and
    never another document's (verification round 4: switching documents dropped the pending re-check)."""
    return (checked_at or {}).get(document)


def gate_actions(actions, box_open, say, open_ok=("legend",)):
    """The panel's actions, each doing nothing but saying BOX_BUSY while a start box is open (one choke point: none of
    them writes to the model, runs a check or opens another box under an open one; verification round of PR #19).
    `open_ok`: the ones that only show something (the legend)."""
    def gated(name, fn):
        def run(*args, **kwargs):
            if box_open() and name not in open_ok:
                say(BOX_BUSY)
                return None
            return fn(*args, **kwargs)
        return run
    return {name: gated(name, fn) for name, fn in actions.items()}


def recovery_message(removed, back):
    """What recovery did, in words (None when it did nothing)."""
    def n(k):
        return "%d object%s" % (k, "s" if k != 1 else "")
    parts = (["removed %s an unfinished start box drew" % n(removed)] if removed else []) + \
        (["put back %s it had set aside" % n(back)] if back else [])
    return " and ".join(parts) or None


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
    guide = None
    if w.get("lot_ring"):
        lot_id = table.add_lot(w["lot_ring"], "Lot · " + (facts.get("address") or "looked up"))
        session.add([lot_id])
        facts["lot_id"] = lot_id
        if w.get("street_line"):
            set_street_lines(facts, w["street_line"])    # unnamed lines: the measuring reads them from the drawing
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


# ---- the context map (design_checker.context_box): the neighbourhood around a looked-up lot ---------------------
CONTEXT_LIMIT_S = 20                    # the whole fetch (three map requests, about 1 s); the Rhino side stops it then
CONTEXT_ENTRY = "context"               # the document string holding the context's snapshot (records, never data)
NO_CONTEXT = ("No neighbourhood to show: it is drawn around a lot the start box looked up (GordiumStart, type the "
              "address, Look up, Draw).")


def context_command(python, frame, fixture=None):
    """The context_box command for a lookup's saved frame (the box's `lookup_frame`), or None when there is no
    looked-up lot to centre it on (the sample lot, a drawn or picked lot, a file saved before the context map)."""
    frame = frame or {}
    origin, shift = frame.get("origin_epsg2261_us_survey_ft"), frame.get("shift_ft")
    if not origin or not shift or frame.get("rotation_deg") is None:
        return None
    args = [python, "-m", "design_checker.context_box", "--origin", repr(float(origin[0])), repr(float(origin[1])),
            "--rotation", repr(float(frame["rotation_deg"])), "--shift", repr(float(shift[0])), repr(float(shift[1]))]
    if frame.get("parcel_id"):
        args += ["--parcel", str(frame["parcel_id"])]
    return args + (["--fixture", fixture] if fixture else [])


def context_frame(facts, saved_ui):
    """The lookup frame to draw the neighbourhood around, only while the lot in the model is the one that lookup drew
    (still its `replaceable_lot`): a lot the architect drew, picked or surveyed, or one a later lookup couldn't
    place (no frame), has no neighbourhood drawn around an earlier address."""
    saved_ui = saved_ui or {}
    lot = (facts or {}).get("lot_id")
    frame = saved_ui.get("lookup_frame")
    if saved_ui.get("from_sample"):      # the sample lot (review round 3: it kept an earlier lookup's frame)
        return None
    return frame if frame and lot and lot == saved_ui.get("replaceable_lot") else None


def same_frame(a, b):
    """Whether two lookup frames are the same placement (one definition for every caller: context_step,
    context_merge, and through it draw_context; review round 7)."""
    return bool(a) and bool(b) and a == b


def is_stored(layer):
    """Whether a context layer's source may be kept in the file (store raw): its objects are in the .3dm. One
    definition for writing (context_objects), keeping (context_merge) and the live footprints (keeps_live)."""
    return (layer or {}).get("store") == "raw"


def guides_of(held, doc_serial):
    """Whether the live footprints held (STATE["context_guides"]) belong to this document."""
    return bool(held) and held.get("doc") == doc_serial


def guides_on_screen(held, doc_serial):
    """Whether this document's footprints are on screen: held for it AND with something to draw. The drawing's and
    the merge's question (keep the ones on screen?). Whether to fetch again is needs_refetch's (review round 8: a
    fetch that worked and found none is not a failure)."""
    return guides_of(held, doc_serial) and bool(held.get("lines"))


def needs_refetch(held, record, doc_serial):
    """Whether the tick or a Draw on the same lot should fetch the neighbourhood again: nothing drawn for this lot
    yet (no record: after a Draw with the tick off, or a first fetch that failed outright; review of the editable
    outlines, round 2), a live-only layer (a source that may not be kept, shown on screen and never saved) with
    nothing on screen for this document (a reopened file), or any layer, stored or live-only, whose last fetch
    failed (review round 9: parcels down on the first Draw were never fetched again). A layer kept from an earlier
    fetch that worked carries that fetch's "found" entry (context_merge), so a kept layer doesn't loop. A fetch that
    worked and found nothing is not fetched again (review round 8). guides_on_screen stays the drawing's and the
    merge's question."""
    layers = list(((record or {}).get("layers") or {}).values())
    if not layers:
        return True              # nothing drawn for this lot: the tick (or Draw) fetches it
    if any(not is_stored(v) for v in layers) and not guides_of(held, doc_serial):
        return True              # (the footprints are kept since 2026-10-21: a reopened file has them, nothing to fetch)
    return any((v or {}).get("status") not in DREW for v in layers)


def context_step(frame, drawn, on):
    """What a box's Draw does to the neighbourhood: frame = the lot's (context_frame), drawn = the frame the one in
    the file was drawn around (context_record), on = the panel's tick.
    "keep": nothing to change (the same lot, or no lot of a lookup's and nothing drawn);
    "clear": the lot isn't a lookup's any more, so the earlier neighbourhood goes;
    "draw": a lookup's lot without its neighbourhood: the earlier one goes, this one is drawn;
    "off": the same, with Show neighbourhood off: the earlier one goes, and the box says it wasn't drawn."""
    if not frame:
        return "clear" if drawn else "keep"
    if same_frame(drawn, frame):
        return "keep"
    return "draw" if on else "off"


def context_record(payload, frame):
    """What the document's strings keep of a drawn neighbourhood: its snapshot (records and the storable layers'
    counts, never a live-only source's data) and the frame it was drawn around."""
    return dict((payload or {}).get("snapshot") or {}, frame=frame)


DREW = ("found", "partial")             # a context layer whose service answered (its objects are replaced)


def context_replaces(payload):
    """The sources whose saved objects a fetch replaces: each layer whose service answered (found or partial), and
    Gordium's own marks when any did. A layer whose service failed keeps what was saved (review of PR #23: one
    service down deleted every layer's objects, and the record then said they had failed)."""
    layers = (payload or {}).get("layers") or {}
    out = set(v.get("source") for v in layers.values() if v.get("status") in DREW and v.get("source"))
    return out | ({"gordium"} if out else set())


LIVE_ONLY = "shown live, not saved in this file."   # site_lookup.context's mark on a live-only layer's credit line
NOTE_WIDTH = 60                          # characters per line of the Sources note (it sits inside the square)
NOTE_HEIGHT_FT = 2.5                     # its text height (about the scale bar label's): ~95 ft wide at 60 characters
NOTE_LINE_FT = 1.7 * NOTE_HEIGHT_FT      # the most one displayed line may take, spacing included (the in-Rhino claim)


def note_text(credits):
    """The Sources note: each credit line wrapped to NOTE_WIDTH characters (Rhino job's screenshots, PR #23: one long
    line ran off the view). One helper for context_box (the first draw) and context_merge (a kept layer's line)."""
    import textwrap
    out = []
    for line in credits or []:
        out += textwrap.wrap(line, NOTE_WIDTH) or [""]
    return "\n".join(out)


def keeps_live(kept, old_record):
    """Whether a live-only layer is among the kept ones (its guides on screen stay, its credit line is carried)."""
    layers = (old_record or {}).get("layers") or {}
    return any(not is_stored(layers.get(n)) for n in kept or [])


def context_merge(payload, old_record, frame, live_on_screen=False):
    """The plan for drawing a fetch over the neighbourhood already in the file: the ONE decision the panel's message,
    the record, the objects deleted and the footprints on screen all follow (review rounds 6-7). A dict:
    payload (what to draw and say), record (what the file keeps), kept (the layers kept), replace (the sources
    whose objects go: rhino_logic.context_replaces around the same frame; None, every one, around another),
    keep_guides (the footprints on screen stay).
    Around the same frame, each layer whose service failed and that is still there is kept: a stored layer is in
    the file; a live-only one (a source that may not be kept) only when its guides are on screen for this document
    (`live_on_screen`, from guides_on_screen). A kept layer's record entries (the layer, its requests, its credit
    line, when it was fetched) are carried over and the Sources dot still lists it. Around another frame (or none
    saved) nothing is carried over: the earlier address's go."""
    record = context_record(payload, frame)
    old = old_record or {}
    plan = {"payload": payload, "record": record, "kept": [], "replace": None, "keep_guides": False}
    if not same_frame(old.get("frame"), frame):
        return plan
    plan["replace"] = context_replaces(payload)
    was = old.get("layers") or {}
    kept = [n for n, v in ((payload or {}).get("layers") or {}).items()
            if v.get("status") not in DREW and (was.get(n) or {}).get("status") in DREW
            and (is_stored(was.get(n)) or live_on_screen)]
    if not kept:
        return plan
    live_kept = keeps_live(kept, old)
    sources = set(was[n]["source"] for n in kept)
    record["layers"] = dict(record.get("layers") or {}, **{n: was[n] for n in kept})
    record["sources"] = list(record.get("sources") or []) + [r for r in old.get("sources") or []
                                                              if r.get("source") in sources]
    credits = list(record.get("credits") or [])
    credits += [c for c in old.get("credits") or [] if c not in credits and (live_kept or LIVE_ONLY not in c)]
    record["credits"] = credits
    # when each layer kept in THIS fetch was really fetched (review round 6: never a layer fetched again since)
    record["kept_from"] = {n: (old.get("kept_from") or {}).get(n) or old.get("fetched") for n in kept}
    objects = []
    for o in payload.get("objects") or []:
        if o.get("source") == "gordium" and o.get("name") == "Sources":
            o = dict(o, text=note_text(credits))
        objects.append(o)
    note = "Kept the %s drawn earlier (the service didn't answer)." % " and ".join(kept)
    counts = dict(payload.get("counts") or {}, **{n: was[n]["count"] for n in kept if "count" in was[n]})
    plan.update(kept=kept, keep_guides=live_kept,
                payload=dict(payload, objects=objects, counts=counts,
                             message=((payload.get("message") or "") + " " + note).strip()))
    return plan


CONTEXT_EDITABLE = (CONTEXT + "::Buildings",)   # left unlocked: the architect drags and edits the footprints (Ben)
GEOM_KEY = "gordium_context_geom"       # on each outline Gordium draws: the fingerprint of its points as drawn
PIECE_KEY = "gordium_context_id"        # on each outline: the parcel, street piece or footprint it is
EDITED_KEY = "gordium_context_edited"   # on an outline the architect edited: it is theirs (Gordium never removes it)
FRAME_KEY = "gordium_context_frame"     # on each outline: the lot (lookup frame) it was drawn around
DRAWN_KEY = "gordium_context_drawn_as"  # on each outline: its own object id when drawn (a copy keeps it, but not as its
                                        # own id: a copy is never the outline itself)


def outermost_first(layers):
    """Layer indexes (from (index, full path) pairs) ordered parent before sublayer, so setting a parent's state can
    never undo a sublayer's set after it (Rhino 8: a parent's IsVisible gives its sublayers its lock; review round 5)."""
    return [i for i, path in sorted(layers, key=lambda x: (x[1].count("::"), x[0]))]


def context_not_cleared(count):
    """What the architect is told when Rhino refused to delete or mark some of Gordium's neighbourhood objects (a
    layer still locked or hidden): never drawn over silently (review round 5)."""
    return ("Gordium could not remove %d neighbourhood object%s it drew earlier (a locked or hidden layer?). Unlock "
            "and show the Gordium layers, then press Draw again, or delete them by hand." % (count, "" if count == 1 else "s"))


def with_not_cleared(text, count):
    """A message with the not-cleared warning first when Rhino refused to remove some of Gordium's objects: the panel
    shows one line, so a warning said on its own is overwritten by the next message (review round 6); a "removed"
    line never stands alone while objects are left."""
    return text if not count else context_not_cleared(count) + " " + text


def context_locked(path):
    """Whether a context layer is locked after drawing: the leaf layers but the editable ones (the footprints), never
    an ancestor of an editable one (Gordium::Context itself): in Rhino a locked parent locks its sublayers' objects,
    so the footprints couldn't be dragged (review of the editable outlines, P1)."""
    if not on_layer(path, CONTEXT) or any(on_layer(path, e) for e in CONTEXT_EDITABLE):
        return False
    return not any(on_layer(e, path) for e in CONTEXT_EDITABLE)


def outline_key(points, attributes=None):
    """The fingerprint of an outline as Rhino holds it: every coordinate of its points, Z included (to a millionth of
    a model unit), and its attributes as the plugin's _attrs_print reads them (each of FINGERPRINT_ATTRIBUTES, the
    layer, linetype and material by their ids, the groups, the architect's own user text). Review of the editable
    outlines, P1: a footprint moved up to the terrain, renamed or recoloured was taken as unedited, deleted and drawn
    again at z = 0."""
    import hashlib
    import json
    flat = [[round(float(c), 6) for c in p] for p in points or []]
    return hashlib.sha1(json.dumps([flat, attributes or {}], sort_keys=True).encode("utf-8")).hexdigest()[:20]


def is_edited(stored_key, points, attributes=None):
    """Whether an outline Gordium drew has been edited since (moved in any direction, reshaped, renamed, recoloured):
    it no longer matches the fingerprint written when it was drawn (Ben, 2026-10-21: Gordium's redraw or clear removes
    only outlines it drew that the architect hasn't edited; an edited one is the architect's and stays). No
    fingerprint: not one of these."""
    return bool(stored_key) and outline_key(points, attributes) != stored_key


def frame_key(frame):
    """A short fingerprint of a lookup frame (which lot, placed how): an outline remembers the lot it was drawn for."""
    import hashlib
    import json
    return hashlib.sha1(json.dumps(frame or {}, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def suppressed(edited, current_frame_key):
    """The ids not to draw again: those of outlines the architect edited that are the very outline Gordium drew (its
    own id is the one it was drawn as: not a copy, which carries the original's user text under a new id) and were
    drawn around this same lot (not one kept from another address, whose ids belong to another square). Review of the
    editable outlines, P2: a copy, or an outline kept from another address, hid an unedited neighbour. `edited`:
    [{id, frame, drawn_as, own}]."""
    return sorted(set(e.get("id") for e in edited or [] if e.get("id") and e.get("frame") == current_frame_key
                      and e.get("drawn_as") and e.get("drawn_as") == e.get("own")))


# The attributes of an outline in its fingerprint (the plugin's _attrs_print), by name: each one an architect can
# change on an outline in Rhino 7 or 8, one that Rhino lacks left out by _attrs_print (review of the editable outlines, round 2: a short list missed print width and
# colour, material, groups). A fixed list, not every property by reflection (round 3): a property one Rhino version
# adds would make every outline drawn under the last one look edited. Table positions are never fingerprinted (the
# layer, linetype and material go by their ids, the groups by theirs: _attrs_print): a deleted layer isn't saved, so
# on reopening a file the later layers' indexes move down, and every untouched outline looked edited, kept forever.
FINGERPRINT_ATTRIBUTES = ("Name", "Url", "Mode", "Visible", "Space", "ViewportId", "DisplayOrder", "WireDensity",
                          "ObjectDecoration", "ColorSource", "ObjectColor", "LinetypeSource", "PlotColorSource",
                          "PlotColor", "PlotWeightSource", "PlotWeight", "MaterialSource", "CastsShadows",
                          "ReceivesShadows", "LinetypePatternScale")   # the last: Rhino 8 only (round 4)


def attribute_text(value):
    """An attribute's value as stable text for the fingerprint (a number, a flag, an enum's name, an id; a colour by
    its ARGB number, never its name, which a colour read back from a file doesn't keep)."""
    if hasattr(value, "ToArgb"):
        return str(int(value.ToArgb()))
    if isinstance(value, float):
        return repr(round(value, 9))
    return str(value)


def kept_on_clear(stored_key, drawn_as, own_id, points, attributes):
    """Whether a clear or redraw keeps an object on the context layers (it is the architect's): any outline that isn't
    exactly the one Gordium drew. A copy (pasted in place too: same points, same attributes) is never the outline
    itself, its own id isn't the one it was drawn as; an edited outline no longer matches its fingerprint. Only
    Gordium's own untouched outlines, and its notes (no fingerprint), are deleted (Ben, 2026-10-21; review round 2)."""
    if not stored_key:
        return False
    return not drawn_as or drawn_as != own_id or is_edited(stored_key, points, attributes)


def skip_edited(objects, edited_ids):
    """The objects to draw, less those the architect has edited and kept (by their parcel, street piece or footprint
    id): an edited outline is not drawn a second time beside it."""
    edited = set(i for i in edited_ids or [] if i)
    return [o for o in objects or [] if not o.get("id") or o["id"] not in edited]


def left_out_candidate(layer_path):
    """Whether a solid on this layer that reaches into the lot is one the check must say it left out (review row:
    "Objects on the lot not included"): every layer but the Building layer and Gordium's own, except the
    neighbourhood's (Gordium::Context), whose footprints the architect may extrude or put a building on (editable
    since Ben's decision, 2026-10-21). Review of the editable outlines, P0: a solid there was never measured and
    never made the check need review."""
    return not on_layer(layer_path, "Gordium") or on_layer(layer_path, CONTEXT)


def context_left_out(layers_by_id):
    """Of the left-out objects (id: its layer), those on the neighbourhood's layers: the review row tells the
    architect to move them to the Building layer."""
    return sorted(i for i, layer in (layers_by_id or {}).items() if on_layer(layer or "", CONTEXT))


def context_objects(payload):
    """What may be written into the .3dm: objects from a source whose store is raw (the payload's layers say which),
    and Gordium's own marks (frame, north arrow, scale bar, credits). Anything else is never written, whatever the
    payload's object list holds."""
    payload = payload or {}
    raw = set(s.get("source") for s in (payload.get("layers") or {}).values() if is_stored(s))
    return [o for o in payload.get("objects") or []
            if (o.get("source") in raw or o.get("source") == "gordium") and on_layer(o.get("layer") or "", CONTEXT)]


def context_guides(payload):
    """What is only shown on screen (never written): every guide, from a source that may not be kept."""
    return [g.get("points") for g in (payload or {}).get("guides") or [] if len(g.get("points") or []) > 1]


def context_says(payload):
    """The line after the neighbourhood is drawn (or why it isn't): what an architect needs, as "Neighbourhood drawn:
    229 parcels, 38 streets, 322 buildings (footprints from 2014)." (architect review of PR #23: the line listed
    agencies and storage rules). "shown only" is added only for footprints from a source that may not be kept. Who
    made the data is on the drawing's Sources note; what a failed service left out follows (the payload's message)."""
    payload = payload or {}
    if payload.get("status") not in ("found",):
        return payload.get("message") or "Couldn't fetch the neighbourhood: the lot is drawn without it."
    n = payload.get("counts") or {}
    said = "%d parcels, %d streets" % (n.get("parcels", 0), n.get("streets", 0))
    if n.get("buildings"):
        layer = (payload.get("layers") or {}).get("buildings") or {}
        dates = ", ".join(layer.get("dates") or [])
        said += ", %d buildings (footprints %s%s)" % (n["buildings"], "from " + dates if dates else "of unknown date",
                                                       "" if is_stored(layer) else ", shown only")
    return "Neighbourhood drawn: " + said + "." + (" " + payload["message"] if payload.get("message") else "")


ASK_LIMIT_S = 60          # s: the longest the plugin waits for one answer (the first also starts Python, loads rules)
ASK_LIMITS_S = {"start": 120}   # s, per command that can take longer: the largest building, on a deep lot


def ask_limit(cmd):
    """How long the plugin waits for the checker's answer to one `cmd` request."""
    return ASK_LIMITS_S.get(cmd, ASK_LIMIT_S)


class CheckerOutOfStep(RuntimeError):
    """The checker's next line can't be trusted to be this request's answer: the plugin restarts the checker and
    shows nothing from it."""


def pipes(process):
    """The checker's two pipes, each served by its own thread: (sends, lines). Rhino's thread never reads or writes
    a pipe, so a checker that stops answering (or stops reading a large request) can never freeze Rhino; the
    plugin only puts on `sends` and waits on `lines` with a time limit (answer_for). Put None on `sends` to end
    the writer."""
    sends, lines = queue.Queue(), queue.Queue()
    threading.Thread(target=_read_lines, args=(process.stdout, lines), daemon=True,
                     name="gordium-reader-%s" % getattr(process, "pid", "")).start()
    threading.Thread(target=_write_lines, args=(process.stdin, sends, process), daemon=True,
                     name="gordium-writer-%s" % getattr(process, "pid", "")).start()
    return sends, lines


def _read_lines(stream, lines):
    """The reader thread: every line the checker writes, then None when it stops."""
    try:
        for line in stream:
            lines.put(line)
    except (OSError, ValueError):            # the pipe closed under it (the checker was stopped)
        pass
    finally:
        lines.put(None)


def _write_lines(stream, sends, process=None):
    """The writer thread: each request, in order, until None, the checker stops reading (then the reader sees it
    stop, or ask's time limit runs out), or the checker process ends (however it was stopped)."""
    try:
        while True:
            try:
                text = sends.get(timeout=1)
            except queue.Empty:
                if process is not None and process.poll() is not None:
                    return
                continue
            if text is None:
                return
            stream.write(text)
            stream.flush()
    except (OSError, ValueError):
        pass


def exchange(sends, lines, request, limit):
    """Send one request (a dict with its "id") and wait at most `limit` s for its answer (answer_for)."""
    sends.put(json.dumps(request) + "\n")
    return answer_for(lines, request["id"], limit)


HANDLES = ("hooks", "doc_hooks", "command_hook", "overlay", "panel", "panel_parts", "toast_timer",
           "worker", "worker_sends", "worker_lines")


def sweep(leftovers, state=None, release=None):
    """Undo everything an earlier copy of the plugin left attached to Rhino (event handlers, its drawing, its
    panel, its checker): `leftovers` maps a name to its undo, kept outside the plugin's state so clearing the
    state can't lose it. Each undo runs even if another fails; returns how many ran. Given the plugin's `state`,
    its handles to those things are forgotten too (so it never says a detached hook is attached), each RELEASED
    first through `release(key, value)`: a copy from before LEFTOVERS existed recorded nothing there, so without
    this its handlers, drawing, panel and checker would stay attached with nothing left to undo them (review
    round 2). Releasing twice is harmless. What the architect asked for (live mode on, the choices) stays."""
    n = 0
    for key in list(leftovers):
        undo = leftovers.pop(key, None)
        try:
            undo()
            n += 1
        except Exception:                      # noqa: BLE001  (already gone: nothing to undo)
            pass
    for key in HANDLES if state is not None else ():
        if key in state and release is not None:
            try:
                release(key, state[key])
            except Exception:                  # noqa: BLE001  (already gone: nothing to release)
                pass
        state.pop(key, None)
    return n


def current_only(fn, is_current):
    """fn, run only while is_current() (this copy of the plugin is the loaded one): an older copy's handler that
    is still attached does nothing, so it can never act on, or wait on, the current copy's checker."""
    def run(*args):
        if not is_current():
            return None
        return fn(*args)
    return run


def answer_for(lines, request_id, limit):
    """The checker's answer to request `request_id`, from `lines` (a queue the plugin's reader thread fills with
    every line the checker writes, then None when it stops); None if it stopped. Raises CheckerOutOfStep when no
    line comes within `limit` seconds, when the line isn't an answer, or when it is another request's answer:
    then later lines may belong to earlier requests, so the plugin restarts the checker rather than ever showing
    an earlier check's result as this one's."""
    try:
        line = lines.get(timeout=limit)
    except queue.Empty:
        raise CheckerOutOfStep("the Gordium checker gave no answer in %d s, so it was restarted" % limit)
    if line is None:
        return None
    try:
        answer = json.loads(line)
    except ValueError:
        answer = None
    if not isinstance(answer, dict) or answer.get("id") != request_id:
        raise CheckerOutOfStep("the Gordium checker's answer didn't match the request, so it was restarted and "
                               "nothing from it is shown")
    return answer


# ---- processes started from Rhino: never a console window (Windows) -----------------------------------------------
CREATE_NO_WINDOW = 0x08000000            # Windows: a console program started from a window program shows no console
STARTF_USESHOWWINDOW, SW_HIDE = 0x00000001, 0


def spawn_options(os_name, subprocess_module):
    """What every process Gordium starts from Rhino is started with (gordium_ui.spawn): on Windows, no console window
    (the cofounders saw a terminal pop up while Gordium ran: Python started from Rhino, a window program, opens one
    unless told not to), and its window hidden too; elsewhere nothing extra."""
    if os_name != "nt":
        return {}
    info = subprocess_module.STARTUPINFO()
    info.dwFlags |= STARTF_USESHOWWINDOW
    info.wShowWindow = SW_HIDE
    return {"creationflags": CREATE_NO_WINDOW, "startupinfo": info}


def open_command(os_name, target):
    """How a file or link is opened with the computer's own app: ("startfile", target) on Windows (os.startfile:
    `open` is macOS's), ("run", ["open", target]) on macOS."""
    return ("startfile", target) if os_name == "nt" else ("run", ["open", target])


class ServerBook:
    """The checker processes Gordium started from Rhino, kept in a small file (`path`) so a later load, a reload,
    or Rhino closing stops the earlier ones still running: exactly one server per Rhino (the coordinator found 30
    orphaned `design_checker serve` children of Rhino, one per plugin load; on Windows each a console window too).
    Each entry: the checker's process number and start time, and the Rhino that started it (`me`: its number and
    start time). A Rhino stops only its own checkers, and those of a Rhino no longer running (a crash); another
    Rhino's are left alone (review round 7, P1: one file for every Rhino, so two open models stopped each other's
    checker). A process is stopped only while it is the one recorded: the same number AND start time (round 7, P2:
    a number the system gave again to another program is never touched). `started_at(pid)`: that process's start
    time, None when it isn't running; `stop(pid)`: the operating system's (gordium_rhino), stand-ins in CI."""

    def __init__(self, path, me, started_at, stop):
        self.path, self.me, self.started_at, self.stop = path, dict(me), started_at, stop

    def entries(self):
        """The record's entries; anything unreadable (an older format: bare numbers) is left out, never stopped."""
        try:
            with open(self.path, encoding="utf-8") as f:
                got = json.load(f)
        except (OSError, ValueError, TypeError):
            return []
        keys = ("pid", "start", "owner", "owner_start")
        return [e for e in got if isinstance(e, dict) and all(k in e for k in keys)] if isinstance(got, list) else []

    def pids(self):
        return [e["pid"] for e in self.entries()]

    def _write(self, entries):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(entries, f)
        except OSError:
            pass

    def _mine_or_orphaned(self, e):
        mine = e["owner"] == self.me["pid"] and e["owner_start"] == self.me["start"]
        return mine or self.started_at(e["owner"]) != e["owner_start"]       # its Rhino is gone

    def stop_all(self, keep=None):
        """Stop this Rhino's recorded checkers (and orphans) still running, but `keep` (an entry); every other
        Rhino's entries stay recorded, as they are."""
        left = []
        for e in self.entries():
            if keep is not None and e["pid"] == keep["pid"] and e["start"] == keep["start"]:
                continue
            running = self.started_at(e["pid"]) == e["start"]                # the same process, not its number reused
            if self._mine_or_orphaned(e):
                if running:
                    self.stop(e["pid"])
            elif running:
                left.append(e)
        self._write(left + ([keep] if keep is not None else []))

    def started(self, pid):
        """A new checker of this Rhino: its earlier ones stopped, this one recorded (another Rhino's untouched)."""
        self.stop_all(keep={"pid": pid, "start": self.started_at(pid), "owner": self.me["pid"],
                            "owner_start": self.me["start"]})
