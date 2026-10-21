"""The decisions the Rhino command makes, as plain functions (no Rhino, Python 3.9), so CI can test them. The
Rhino script (apps/rhino_plugin/gordium_rhino.py) imports this file directly.
"""

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


def missing(facts):
    """The required lot facts not yet given: the confirm dialog shows whenever any is missing."""
    facts = facts or {}
    return [k for k in REQUIRED if facts.get(k) is None or facts.get(k) == []]


def with_suggestions(saved, suggested):
    """The facts to confirm: what is saved, with suggestions only for what is missing."""
    out = dict(suggested)
    out.update({k: v for k, v in (saved or {}).items() if v is not None})
    return out


def update_counts(facts, answers):
    """Bedrooms, parking spaces and stories from the Lot facts prompts. An answer of None means the prompt was
    skipped: the fact stays as it was (unset stays unset, so its rules stay NEEDS REVIEW), never 0."""
    out = dict(facts or {})
    for key in ("sleeping_rooms", "parking_spaces", "stories"):
        if answers.get(key) is not None:
            out[key] = int(answers[key])
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


def suggested_ground(building_bottoms, lot_bottom):
    """The ground level to suggest (feet or model units, as given): the lowest point of the buildings, or with no
    building yet (a new project on the architect's own lot) the lot outline's level. Shown in the dialog, never
    used unconfirmed."""
    return min(building_bottoms) if building_bottoms else lot_bottom


def clear_spot(taken, x, y, w, h):
    """Where a w × h label wanted at (x, y) (its top left, in screen pixels) covers none already drawn this frame
    (`taken`, a list of (x, y, w, h)): the nearest free position a label's height down or up, tried in turn, never
    moved up off the top of the view; the spot is then taken. If none is free within four steps (a tall box such as
    the status box in the way), the label goes just below everything it would cover."""
    def hits(top):
        return any(x < a + c and a < x + w and top < b + e and b < top + h for a, b, c, e in taken)
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
NOT_CHECKED_YET = "Not checked yet: overlays (historic, gorge, flood) · pitched roofs"
ENTERED = "entered by you"
FLOOR_TO_FLOOR = 11 + 8 / 12                 # ft: the starting house's floor height (editable later in GordiumFacts)
CORNER_CHOICES = ["Not answered", "No: one street", "Yes: two streets"]   # the Street side row's question
SUGGESTED = "suggested by Gordium"
GROUND_CHOICES = [("spot", "Place spot grades…"), ("terrain", "Pick terrain…"),
                  ("regrade", "I'll regrade: set finished ground…")]


def lot_text(area, surveyed, source=None):
    """The Lot row: "6,570 sf · from the tax map (±2 ft, approximate)" or "… · from your survey"; with the map
    service the lookup read it from ("… · NYS Tax Parcels Public")."""
    size = f"{area:,.0f} sf" if isinstance(area, (int, float)) else "area not known"
    return size + " · from " + ("your survey" if surveyed else "the tax map (±2 ft, approximate)") + \
        (" · " + source if source and not surveyed else "")


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


def box_rows(state):
    """The start box, top to bottom: one dict per row {key, label, text, actions [(action, label, enabled)],
    tick (label, checked) or None, review (an amber line) or None, check ("I checked this", ticked) or None}.
    `state`: address, zone, zone_source, district_confirmed, use, use_name, lot_area, lot_surveyed, street_name,
    ground {kind, count, range}, no_regrading, lookup (this session's), doubts, live, checked, lot_missing."""
    look = state.get("lookup") or {}
    doubts, live = state.get("doubts") or {}, state.get("live") or {}
    checked = set(state.get("checked") or [])

    def review(key):                  # a doubt about what is drawn (or this lookup's zone): amber, why, I checked this
        why = live.get(key) or doubts.get(key)
        if key == "zone":             # the zone's own doubts and the overlays found, together
            why = " ".join(t for t in (live.get("zone"), live.get("overlays")) if t) or None
        return {"review": "? " + why if why else None,
                "check": ("I checked this", key in checked) if key in CHECKABLE and key in doubts else None}

    lot_actions = [("lot", "Use my survey…", not state.get("lot_surveyed"))]
    if look.get("guide") or state.get("lot_missing"):
        lot_actions.insert(0, ("draw_lot", "Draw my lot…", True))
    rows = [
        {"key": "address", "label": "Address", "text": state.get("address") or "",
         "actions": [("lookup", "Looking up…" if look.get("looking") else "Look up", not look.get("looking"))],
         "tick": None, "matches": look.get("matches") or [],
         "status": LOOKING.format(look["looking"]) if look.get("looking") else None},
        {"key": "zone", "label": "Zoning district",
         "text": (state.get("zone") or "—") + " · " + (state.get("zone_source") or ENTERED),
         "actions": [("zone", "Change", True)], "tick": ("I confirm", bool(state.get("district_confirmed")))},
        {"key": "use", "label": "Use", "text": state.get("use_name") or state.get("use") or "—",
         "actions": [("use", "Change", True)], "tick": None},
        {"key": "lot", "label": "Lot",
         "text": ("no lot yet: draw it, or pick a closed outline on the Site layer" if state.get("lot_missing") else
                  lot_text(state.get("lot_area"), state.get("lot_surveyed"), state.get("lot_source"))),
         "actions": lot_actions, "tick": None},
        {"key": "street", "label": "Street side", "text": state.get("street_name") or "the highlighted line",
         "actions": [("street", "Change…", True)], "tick": None,
         "choice": ("Corner lot?", CORNER_CHOICES, {None: 0, False: 1, True: 2}[state.get("corner_lot")])},
        {"key": "ground", "label": "Ground", "text": ground_text(state.get("ground") or {}),
         "actions": [(k, t, True) for k, t in GROUND_CHOICES],
         "tick": ("No regrading near the house", bool(state.get("no_regrading")))},
    ]
    for r in rows:
        r.update(review(r["key"]))
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
    if isinstance(zone, list):                   # two zones: the box asks which applies
        found = [names.get(z.lower(), z) for z in zone]
        saved_ui["_zones_found"] = found
        facts["zone"] = found[0]
    elif zone:
        facts["zone"] = names.get(zone.lower(), zone)
        saved_ui.pop("_zones_found", None)
    if zone:
        saved_ui["zone_source"] = SUGGESTED + " · " + label("zone", "zone")
    saved_ui["_reconfirm"] = True                # a looked-up district is the architect's only once ticked again
    saved_ui["_live"] = {k: v for k, v in live.items() if k in ("zone", "overlays")}
    if not replaces:                             # the architect's own lot: its lot, street side and ground stay
        return facts, saved_ui
    side = value("street_side") or {}
    if side.get("street"):
        street_kept = payload.get("street_storable")
        saved_ui.pop("street_name" if not street_kept else "_street_name", None)
        saved_ui["street_name" if street_kept else "_street_name"] = side["street"].title()
        saved_ui["street_source"] = SUGGESTED + " · " + label("street_side", "street")
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
    if writes.get("spots"):
        saved_ui["ground_kind"] = "spot"
        saved_ui["ground_source"] = SUGGESTED + " · " + label("ground", "ground")
    if lot and not writes.get("lot_ring"):      # the City's parcels: a guide only, never kept
        look["guide"] = True
        live["lot"] = GUIDE + (" " + live["lot"] if live.get("lot") else "")
    # the doubts about what is now drawn: this lookup's, for the rows it replaced; earlier ticks don't carry over
    saved_ui["doubts"] = {k: v for k, v in keep.items() if k in CHECKABLE}
    saved_ui["_live"].update({k: v for k, v in live.items() if k in CHECKABLE})
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
    return {k: v for k, v in ((saved_ui or {}).get("doubts") or {}).items() if k in CHECKABLE and k not in done}


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
        asks.append("Does this lot face two streets? Answer Corner lot? under Street side")
    elif state.get("corner_lot"):
        asks.append("This lot faces two streets: pick the front")
    if len(state.get("zones_found") or []) > 1:
        asks.append("This lot is in two zones: pick the zone that applies")
    return " · ".join(asks) or None


def ground_facts(state, lot_level):
    """The facts the checker gets from the Ground row (the checker never sees where a fact came from). Ground you
    set as finished, or ticked "No regrading near the house", counts as the finished grade the code measures
    from; ground only as it is (existing), unticked, gives height and stories needs review (spec C5)."""
    ground = state.get("ground") or {}
    kind = ground.get("kind") or "flat"
    finished = kind == "regrade" or bool(state.get("no_regrading"))
    out = {"grade_is": "finished" if finished else "existing"}
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
        "lot": fact(lot_text(state.get("lot_area"), state.get("lot_surveyed")),
                    "your survey" if state.get("lot_surveyed") else
                    "the tax map (±2 ft)" + (" · " + state["lot_source"] if state.get("lot_source") else "")),
        # the street's name only when it may be kept (the City's roads may not: "street_name_saved" then None)
        "street": fact((state.get("street_name_saved") if "street_name_saved" in state else state.get("street_name"))
                       or "the highlighted line",
                       state.get("street_source") or SUGGESTED),
        "corner_lot": fact({None: None, False: "no, one street", True: "yes, two streets"}[state.get("corner_lot")],
                           state.get("corner_source") or SUGGESTED),
        "ground": fact(ground_text(ground) + (" · no regrading near the house" if state.get("no_regrading") else ""),
                       "as drawn" if kind == "flat" else ground.get("source") or
                       ("picked by you" if kind == "terrain" else "placed by you")),
    }


def district_confirmed(mode, zone_fact, zone):
    """Whether "I confirm" starts ticked: never on a new project (GordiumStart); on an existing one only if this
    same district was confirmed at an earlier Draw (its saved source says who confirmed it)."""
    zone_fact = zone_fact or {}
    return mode != "start" and bool(zone_fact.get("confirmed_by")) and zone_fact.get("value") == zone


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
        """Cancel, Esc or an error: the model as the box found it (objects, the layers it made, the views)."""
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
    for k in ("lot_id", "street_line"):
        facts.pop(k, None)
    saved_ui.update(from_sample=False, replaceable_lot=None, lookup_frame=None, ground_kind="flat", lookup_spots=[])
    guide = None
    if w.get("lot_ring"):
        lot_id = table.add_lot(w["lot_ring"], "Lot · " + (facts.get("address") or "looked up"))
        session.add([lot_id])
        facts["lot_id"] = lot_id
        if w.get("street_line"):
            facts["street_line"] = w["street_line"]
        spots = [table.add_spot(p) for p in w.get("spots") or []]
        session.add(spots)
        saved_ui.update(replaceable_lot=lot_id, lookup_frame=w.get("frame"), lookup_spots=spots)
        if spots:
            saved_ui["ground_kind"] = "spot"
    elif w.get("guide_ring"):
        guide = w["guide_ring"]
    saved_ui["lookup_snapshot"] = w.get("snapshot")
    return facts, saved_ui, guide
