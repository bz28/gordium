"""The decisions the Rhino command makes, as plain functions (no Rhino, Python 3.9), so CI can test them. The
Rhino script (apps/rhino_plugin/gordium_rhino.py) imports this file directly.
"""

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


def classify(full_path, kind, holds_building=False):
    """What the Rhino command does with one object, from its layer's full path and its geometry's type name:
    "lot" (a curve on the lot layer: a possible lot outline), "building" (a solid or mesh on the building layer),
    None (anything else, ignored), or a problem sentence. Nothing that could be part of a building is dropped:
    a block on the building layer, or a block holding building objects wherever it is placed, and any other
    geometry on the building layer, are problems, so the checker says NEEDS REVIEW."""
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
}


def needs_of(names, values):
    """The stated facts a rule reads (`names`) that aren't set yet (`values`), in the order they are asked."""
    return [k for k in STATED_FACTS if k in names and (values or {}).get(k) is None]


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


def drop_stale(facts, lot_ids, building_ids):
    """The saved facts without a lot or main building that is no longer in the model (redrawn, joined, deleted):
    the lot's street lines go with it, so the confirm dialog asks again instead of keeping an id nothing has."""
    out = dict(facts or {})
    if out.get("lot_id") and out["lot_id"] not in lot_ids:
        out.pop("lot_id")
        out.pop("street_line", None)
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
        out.pop("street_line", None)
    return out


def street_enter_keeps(facts):
    """Whether Enter at the first street-line prompt keeps the street lines saved for this lot."""
    return bool(facts.get("street_line"))


def after_corner_answer(facts, was_corner):
    """The facts after the corner-lot answer: a changed answer drops the street lines (a corner lot has two
    streets, any other lot one), so they are picked again and Enter can't keep the old ones."""
    out = dict(facts)
    if out.get("corner_lot") != was_corner:
        out.pop("street_line", None)
    return out


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
            facts["street_line"] = [[[a[0], a[1]], [b[0], b[1]]]]
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


def lot_source(surveyed):
    return "your survey" if surveyed else "the tax map (±2 ft, approximate)"


NO_LOT = "no lot yet: draw it on the Site layer, or Draw puts down the sample lot (106 Ithaca Rd)"


def lot_text(area, surveyed):
    """The Lot row: "6,570 sf · from the tax map (±2 ft, approximate)" or "… · from your survey"."""
    return lot_size(area) + " · from " + lot_source(surveyed)


def ground_text(ground):
    """The Ground row: what the ground is and where it came from ("flat at the lot level · as drawn", "4 spot
    grades, 0'-0" to 3'-0" · placed by you", "terrain · picked by you", or finished ground you set)."""
    kind = ground.get("kind") or "flat"
    if kind == "flat":
        return "flat at the lot level · as drawn"
    span = ground.get("range") or ""
    what = {"spot": f"{ground.get('count', 0)} spot grades", "terrain": "terrain",
            "regrade": f"finished ground you set ({ground.get('count', 0)} spot grades)"}[kind]
    return what + (", " + span if span else "") + " · " + ("picked by you" if kind == "terrain" else "placed by you")


def street_name(state):
    """The street the highlighted lot line is on, by name, only when that line's street is known (a lookup's
    street, or the sample's); else the line itself, so the architect checks which line it is (the street line
    sets the front, side and rear yards: never named from the address alone)."""
    return state.get("street_name") or "the highlighted line"


def street_name_after_pick(name, lines, picked, tolerance=0.5):
    """The street's name to keep when the architect picks the street side again (`picked`: the lot line clicked,
    [[x, y], [x, y]] in feet): `name`, the street's name as found, if the line is one of that street's own `lines`
    (within `tolerance` ft at each end, either way round); else None, and the architect is asked (a name is never
    carried to a line it wasn't found on)."""
    if not name:
        return None

    def near(p, q):
        return abs(p[0] - q[0]) <= tolerance and abs(p[1] - q[1]) <= tolerance

    a, b = picked
    for c, d in lines or []:
        if (near(a, c) and near(b, d)) or (near(a, d) and near(b, c)):
            return name
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


def street_lines_after_pick(lines, picked, tolerance=0.5):
    """The street lines after the architect clicks a lot line as the street side: the whole street as it was when
    the line is one of its own (a street of several segments, 106's eight: keeping only the one clicked measured the
    front yard from part of the street, a false pass: review round 3, F4); else the line clicked."""
    def near(p, q):
        return abs(p[0] - q[0]) <= tolerance and abs(p[1] - q[1]) <= tolerance

    a, b = picked
    if any((near(a, c) and near(b, d)) or (near(a, d) and near(b, c)) for c, d in lines or []):
        return [list(map(list, line)) for line in lines]
    return [picked]


def box_rows(state, flat=None):
    """The start box, top to bottom: one dict per row {key, label, text, actions [(action, label, enabled)],
    tick (label, checked) or None}. `state`: address, zone, zone_source, district_confirmed, use, use_name,
    lot_area, lot_surveyed, street_name, ground {kind, count, range}, no_regrading."""
    has_lot = bool(state.get("has_lot") or state.get("lot_area") is not None or state.get("lot_surveyed"))
    rows = [
        {"key": "address", "label": "Address", "text": state.get("address") or "",
         "actions": [("lookup", "Look up (coming soon)", False)], "tick": None},
        {"key": "zone", "label": "Zoning district",
         "text": (state.get("zone") or "—") + " · " + (state.get("zone_source") or ENTERED),
         "actions": [("zone", "Change", True)], "tick": (ZONE_TICK, bool(state.get("district_confirmed")))},
        {"key": "use", "label": "Use", "text": state.get("use_name") or state.get("use") or "—",
         "actions": [("use", "Change", True)], "tick": None},
        {"key": "lot", "label": "Lot", "text": lot_text(state.get("lot_area"), state.get("lot_surveyed"))
         if has_lot else NO_LOT,
         "actions": [("lot", "Use my survey…", not state.get("lot_surveyed"))] if has_lot else [], "tick": None},
        {"key": "street", "label": STREET_LABEL, "help": STREET_HELP, "text": street_name(state) if (state.get("street_name") or has_lot)
            else "set from the lot, once there is one",
         "actions": [("street", "Change…", True)] if has_lot else [], "tick": None,   # nothing to change yet: hidden
         "choice": ("Corner lot?", CORNER_CHOICES, {None: 0, False: 1, True: 2}[state.get("corner_lot")])},
        {"key": "ground", "label": "Ground", "text": ground_text(state.get("ground") or {}),
         "actions": [(k, t, True) for k, t in GROUND_CHOICES],
         "tick": ("No regrading near the house", bool(state.get("no_regrading")))},
    ]
    if FLAT_GROUND if flat is None else flat:      # the MVP: no Ground row (flat ground is assumed)
        rows = [r for r in rows if r["key"] != "ground"]
    return rows


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
    if not state.get("district_confirmed"):
        return "Confirm the district to continue."
    if parse_feet(state.get("design_buffer")) is None:
        return BUFFER_UNREAD
    return ""


def can_draw(state):
    """Draw is on only once the district is confirmed (Gordium doesn't look the zoning map up yet) and the design
    buffer, if typed, can be read."""
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
    if state.get("corner_lot") is None:          # never guessed: unanswered, the yards wait for it (§325-19C)
        return "Does this lot face two streets? Answer Corner lot? under " + STREET_LABEL
    if state.get("corner_lot"):
        return "This lot faces two streets: pick the front"
    if len(state.get("zones_found") or []) > 1:
        return "This lot is in two zones: pick the zone that applies"
    return None


# The MVP assumes flat ground (Ben, 2026-10-20): flat at the lot level and finished, so height and stories are
# checked (with "assuming flat ground" on their rows and in the report). The spot-grade, terrain and regrade paths
# stay, behind this one switch: set it to False to bring the Ground row back.
FLAT_GROUND = True
ASSUMED_FLAT = "assuming flat ground"


def ground_facts(state, lot_level, flat=None):
    """The facts the checker gets from the Ground row (the checker never sees where a fact came from). With the MVP's
    flat-ground switch on: flat at the lot level, finished, and said to be assumed. Otherwise: ground you set as
    finished, or ticked "No regrading near the house", counts as the finished grade the code measures from; ground
    only as it is (existing), unticked, gives height and stories needs review (spec C5)."""
    if FLAT_GROUND if flat is None else flat:
        return {"grade_is": "finished", "ground_is_flat": True, "grade_elevation": lot_level, "grade_from": None,
                "ground_assumed": "flat"}
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
        "lot": fact(lot_size(state.get("lot_area")), lot_source(state.get("lot_surveyed"))),
        "street": fact(street_name(state),
                       state.get("street_source") or SUGGESTED),
        "corner_lot": fact({None: None, False: "no, one street", True: "yes, two streets"}[state.get("corner_lot")],
                           state.get("corner_source") or SUGGESTED),
        "ground": fact("assumed flat" if FLAT_GROUND else
                       ground_text(ground) + (" · no regrading near the house" if state.get("no_regrading") else ""),
                       "as drawn" if kind == "flat" else ("picked by you" if kind == "terrain" else "placed by you")),
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
