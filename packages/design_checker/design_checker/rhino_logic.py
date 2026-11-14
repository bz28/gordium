"""The decisions the Rhino command makes, as plain functions (no Rhino, Python 3.9), so CI can test them. The
Rhino script (apps/rhino_plugin/gordium_rhino.py) imports this file directly.
"""

import contextlib
import datetime as _dt
import json
import math
import os
import queue
import re
import threading
import time

# The place the plugin checks (its only place, for now), from the place registry: its settings file,
# regulations/jurisdictions/<state>/<place>/jurisdiction.yaml, copied for Rhino's Python (which can't read YAML) into
# place.json beside this file by `python -m rule_format place --write` (CI checks the copy is current). Every value
# below that names the place (its name, the address tail, its own words and ZIP codes, its time zone) comes from it.
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "place.json"), encoding="utf-8") as _f:
    PLACE = json.load(_f)
_ADDRESSES = PLACE["addresses"]

LAYERS = {"lot": "Site", "building": "Building"}
ID_KEY = "gordium:id"                   # the same keys as model_measurement.read_3dm (a test keeps them equal)
FLOOR_KEY = "gordium:floor"            # user text on a floor block GordiumStart drew: "<story>;<height drawn, ft>"
MASSING = "Gordium::Massing"            # where GordiumStart draws the starting building: building objects too
MASSING_ROOF = MASSING + "::Roof"       # its roof's sublayer (the architect's own roof goes there too): a building
SOLIDS = ("Brep", "Extrusion", "Mesh", "SubD")
DRAWING_AIDS = ("Curve", "Point", "PointCloud", "TextDot", "AnnotationBase", "Hatch", "TextEntity", "Dimension",
                "Leader", "LinearDimension", "AngularDimension", "RadialDimension", "OrdinateDimension")
# the grade isn't required: without one the check runs and height and stories need review until it's set (spec C3)
REQUIRED = ("jurisdiction", "zone", "use", "street_line", "lot_surveyed")   # corner lot unanswered: the yards wait (C)


def massing_floor(n):
    """The sublayer of the starting house's floor n (1 up): Gordium::Massing::Floor 1, … (Ben, 2026-10-21)."""
    return MASSING + "::Floor " + str(int(n))


def on_layer(full_path, layer):
    """A layer or one of its sublayers ("Building::Garage")."""
    return full_path == layer or full_path.startswith(layer + "::")


CONTEXT = "Gordium::Context"            # the context map (neighbouring parcels, streets, notes): drawing only
ENVELOPE = "Gordium::Envelope"          # the curves the architect snaps to (the buildable outline, the yard lines)
ENVELOPE_KEY = "gordium_envelope"       # on each of those curves: what it is (Gordium's own, redrawn each check)
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


def envelope_outlines(env, plan):
    """The buildable outline(s) the blue envelope is drawn on (feet): on a tax-map lot the cautious one, every lot
    line 2'-0" nearer (each piece of it; none where nothing is left: the as-drawn outline is then only the dashed
    curve on Gordium::Envelope), so the envelope shows where a building complies however the tax map's lines lie
    (Ben, 2026-10-21: "cautious envelope on tax-map lots"); on a survey the outline as drawn. Largest first, by the
    shoelace area (_ring_area): plain Python, because Rhino's own Python runs this module and has no shapely (every
    check in Rhino failed "No module named 'shapely'")."""
    outline = (env or {}).get("outline")
    if not outline:
        return []
    plan = plan or {}
    cautious = plan.get("buildable_cautious")
    if not plan.get("lot_from_tax_map") or cautious is None:
        return [outline]
    rings = [cautious] if cautious and isinstance(cautious[0][0], (int, float)) else list(cautious)
    return sorted(rings, key=lambda r: -abs(_ring_area(r)))


def envelope_curves(plan):
    """The curves drawn on Gordium::Envelope for the architect to snap to (Osnap), from check.plan, in feet: each
    {"points" [[x, y], ...], "closed", "dashed", "what"}. The buildable outline (on a tax-map lot the cautious one,
    every lot line 2'-0" nearer, solid; the outline as drawn dashed) and each yard's required line in full (dashed
    on a tax-map lot: it is as drawn). Never measured (classify); redrawn at every check."""
    plan = plan or {}
    tax = bool(plan.get("lot_from_tax_map"))        # dashed whenever the lot is the tax map's, whatever is left 2'-0"
    cautious, drawn = plan.get("buildable_cautious") or [], plan.get("buildable")   # in (review of feature 4, F3)
    if cautious and isinstance(cautious[0][0], (int, float)):       # (one ring)
        cautious = [cautious]
    out = []
    for ring in cautious if tax else []:
        out.append({"points": ring, "closed": True, "dashed": False, "what": "buildable outline (cautious)"})
    if drawn:
        out.append({"points": drawn, "closed": True, "dashed": tax,
                    "what": "buildable outline" + (" (as drawn, tax map)" if tax else "")})
    for y in plan.get("yard_lines") or []:
        out.append({"points": y["points"], "closed": False, "dashed": tax,
                    "what": "required line: " + (y.get("name") or y.get("measure") or "yard")})
    return out


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
    if on_layer(full_path, ENVELOPE) and kind.endswith("Curve"):   # the curves to snap to: Gordium's, never
        return None                                  # measured (anything else there is judged as anywhere: F7)
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


def own_buildings(objects):
    """The ids of the architect's buildings among `objects` ((id, layer full path, geometry type name, whether it is
    a block holding a building)), as the checker sees them (classify): solids on Building and its sublayers, and
    everything there it can't measure (a block, a surface: each a problem the check names), and a block holding a
    building wherever it is placed; never the starting house (Gordium::Massing) or what a start box holds. What a
    reset asks about and clears (re-lookup review round 2: blocks and surfaces on Building were left behind)."""
    return [i for i, layer, kind, holds in objects
            if not on_layer(layer, MASSING) and classify(layer, kind, holds) not in (None, "lot")]


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


def block_span(entry, solid_bottom=None, solid_top=None):
    """The heights (feet) a coloured block is cut from in Rhino: the checker's (check.plan), reaching to the real
    solid's own top (and, for a yard strip, its own bottom) when Rhino's solid goes further. The checker measures
    only the faces it can read (a curved vault is left out: its height needs review), so its top can be the wall
    tops, while the vault above them is just as much over the limit (the Rhino check of #28 at fc0b023: only the
    band from 35 to 36 ft was coloured, under a vault to 42 ft). A height block always starts at the limit."""
    base, top = entry["base"], entry["top"]
    if solid_top is not None:
        top = max(top, solid_top)
    if solid_bottom is not None and entry.get("why") != "height":
        base = min(base, solid_bottom)
    return base, top


def offending_pieces(pieces, block):
    """What a coloured block draws: the building's own part inside it (Rhino's boolean intersection, `pieces`), or
    the block itself when the intersection gave nothing (it failed, or the building is a mesh or a solid Rhino
    can't cut; a block instance is never measured: it is a setup problem, "explode it"), so a failing part is never
    left uncoloured because a boolean failed."""
    kept = [p for p in pieces or [] if p is not None]
    return kept or [block]


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


def missing(facts):
    """The required lot facts not yet given: the confirm dialog shows whenever any is missing."""
    facts = facts or {}
    return [k for k in REQUIRED if facts.get(k) is None or facts.get(k) == []]


def with_suggestions(saved, suggested):
    """The facts to confirm: what is saved, with suggestions only for what is missing. The street lines and their
    street ids are one fact: saved lines keep only their own saved ids, never the suggestion's (ids that name other
    lines: two streets one id, a frontage read along both; street ids review round 3, F1), and suggested lines only
    the suggestion's."""
    out = dict(suggested)
    out.update({k: v for k, v in (saved or {}).items() if v is not None})
    own = (saved or {}) if (saved or {}).get("street_line") else suggested or {}   # whose lines: their ids alone
    return set_street_lines(out, out.get("street_line"), own.get("street_ids"))


# The facts only the architect can state (the model can't show them), in the order they are asked: each with its
# prompt, its kind (a whole number 0 or more, or yes / no) and its name in a row's words. A row waiting on any of
# them says which, and its "Enter …" button asks for exactly those (needs_of, enter_words).
STATED_FACTS = {
    "sleeping_rooms": ("Bedrooms", "count", "bedrooms"),
    "parking_spaces": ("Off-street parking spaces", "count", "parking spaces"),
    "dwelling_units": ("Dwelling units on this lot (a semi-detached or attached building split along its party walls: "
                       "this lot's units only)", "count", "dwelling units"),
    "rooms_let_for_profit": ("Rooms let for profit", "count", "rooms let for profit"),
    "conversion": ("Made by converting an existing building, not new construction? (§325-3B)", "yes_no",
                   "whether it is a conversion"),
    "occupants": ("Occupants on this lot, all dwelling units together (§325-3B OCCUPANT: in R-2c, every person with the "
                  "right to occupy, living there yet or not)", "count", "occupants"),
    "occupants_most_in_one_unit": ("Most occupants in any one dwelling unit (optional: how they are split)", "count",
                                   "the most occupants in one unit"),
    "attached_units_in_building": ("Dwelling units in the whole attached building, every lot it stands on (§325-3B: "
                                   "three to six)", "count", "the units in the whole building"),
    "abuts_r1_district": ("Is any R-1a or R-1b land touching this lot (even at a corner), or across a street, alley, creek or other waterway, railroad or other right-of-way from it? (§325-19E)",
                          "yes_no", "whether the lot abuts R-1 land"),
    # who lives there (§325-3B's one-family and two-family dwellings) and a home occupation: blank until said, so
    # the rules that read them need review (never 0 or no)
    "unrelated_persons": ("Most people in any one dwelling unit not related by blood, marriage or adoption to its "
                          "household's family (minor dependent children in a parent's or relative's care left out)",
                          "count", "unrelated people per unit"),
    # asked alone in R-3 and RU, so it says the whole count itself (review round 2: "the same count" pointed at a
    # question never asked there)
    "unrelated_persons_with_children": ("Most people in any one dwelling unit not related by blood, marriage or adoption "
                                        "to its household's family, minor dependent children counted too", "count",
                                        "unrelated people per unit, children counted"),
    # the house itself, not only an accessory dwelling unit on the lot; with an ADU on the lot the allowance needs
    # review (the owner-and-ADU open question, #38 review)
    "owner_occupied": ("Does the owner (§325-3B OWNER) live in the one-family dwelling itself (not only in an "
                       "accessory dwelling unit on the lot)?", "yes_no", "whether the owner lives there"),
    "accessory_dwelling_unit": ("Is there an accessory dwelling unit (ADU) on the lot (§325-3B, §325-28)?", "yes_no",
                                "whether an ADU is on the lot"),
    "functional_family_unit": ("Is the household to be shown to the City to be a functional family unit (§325-3B)?",
                               "yes_no", "whether the household is a functional family unit"),
    "home_occupation": ("Is a home occupation planned (§325-3B: a business, studio or office run by a resident)?",
                        "yes_no", "whether a home occupation is planned"),
    # floor areas in square feet, any number 0 or more (never rounded: 500.4 sq ft typed as 500 would pass the
    # 500 sq ft limit; review round 1)
    "home_occupation_area": ("Home occupation's indoor floor area, accessory buildings included (sq ft)", "area",
                             "the home occupation's floor area"),
    "home_occupation_unit_area": ("Floor area of the dwelling unit it is in (sq ft)", "area",
                                  "its dwelling unit's floor area"),
    # how many primary buildings the lot holds (§325-8B(1), §325-7B, §325-8E): read from the drawing where it can
    # be (one building, or none standing apart that could hold a home); asked where it can't
    "primary_buildings": ("Primary buildings on the lot, the main one included: each separate building holding a home "
                          "or other primary use, not a garage, shed or accessory dwelling unit (§325-8B(1))", "count",
                          "the primary buildings on the lot"),
    "primary_buildings_same_use": ("Does every primary building on the lot hold the use entered for the lot?",
                                   "yes_no", "whether every primary building holds the lot's use"),
    # a stream or inlet near the lot (§325-26): the model doesn't show the water; the distance in feet as typed
    # (never rounded: 19.96 ft typed as 20 would pass)
    "stream_near_lot": ("Is any inlet wall, or the bank of an inlet channel or stream (at average water level), within "
                        "20 ft of the lot? (§325-26)", "yes_no", "whether a stream or inlet is within 20 ft of the lot"),
    "stream_distance": ("Least horizontal distance from any new structure (house, addition, garage, deck, fence; not a "
                        "patio) to that wall or bank, at average water level (ft)", "length",
                        "the distance from the stream"),
    "south_hill_overlay": ("Is the lot in the South Hill Overlay District (§325-8E; the City's zoning map)?", "yes_no",
                           "whether the lot is in the South Hill Overlay"),
    # the chart's private garage limit (p.2 notes 6 and 7): the cars all the lot's garages hold together, and, only once
    # that is over the limit, how many garages (ROW_ONLY_FACTS)
    "garage_cars": ("Cars the lot's private garages hold, all together: every enclosed garage, attached or detached (0 if "
                    "there is none; a carport isn't enclosed)", "count", "the cars the private garages hold"),
    "private_garages": ("Private garages on the lot (an attached garage counts)", "count",
                        "the private garages on the lot"),
    # an accessory dwelling unit (§325-28): what kind it is, then, only once an ADU is said to be on the lot, what its
    # rules read (ROW_ONLY_FACTS); a detached one's building is picked in the model (adu_building), never typed
    "adu_detached": ("Is the accessory dwelling unit detached: in its own building, not in or on the main building? "
                     "(§325-3B)", "yes_no", "whether the ADU is detached"),
    "adu_existing_building": ("Is the detached ADU in an accessory building that already exists (not new "
                              "construction)? (§325-28C(7)(b))", "yes_no", "whether the ADU's building already exists"),
    "adus_on_parcel": ("Accessory dwelling units on the parcel, any already there included (§325-28C(1))", "count",
                       "the ADUs on the parcel"),
    "adu_bedrooms": ("Bedrooms in the accessory dwelling unit (§325-28C(3))", "count", "the ADU's bedrooms"),
    # floor areas as typed, never rounded (as the home occupation's)
    "adu_floor_area": ("Floor area of the attached accessory dwelling unit (sq ft)", "area", "the ADU's floor area"),
    "primary_floor_area": ("Floor area of the whole main building the ADU is in, the ADU included (sq ft)", "area",
                           "the main building's floor area"),
    # the whole building's count, asked only where the measuring asks for it (a part not drawn as floor blocks):
    # stories_needed; it stands only if at least the floors drawn (the measuring checks, and refused_stories says)
    "stories": ("Stories of the whole building", "count", "the number of stories"),
}
# The least whole number each counted fact may be: its own definition's (a unit's most occupants, a building's units:
# at least one), else 0. The answer fields (parse_answer) and update_counts both use it, so a field can't accept what
# the check refuses (#r2 review round 2).
MINIMUM = {"occupants_most_in_one_unit": 1, "attached_units_in_building": 1, "primary_buildings": 1,
           "private_garages": 1, "adus_on_parcel": 1}
# Facts a row can be decided without, each with the fact that bounds it from above (the most occupants in one unit
# is 1 to occupants): asked only where some value in that range would change the row (present.could_settle).
OPTIONAL = {"occupants_most_in_one_unit": "occupants"}


def minimum(key):
    return MINIMUM.get(key, 0)


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


INTERIOR_FACTS = ("sleeping_rooms", "parking_spaces")    # inside the building (on hold): never asked in the box
# Read from the drawing (the main building is one; solids standing apart that could hold a home are readings), so the
# box never asks them up front: the panel's Enter flow still does, where the drawing can't say (measure._primary_buildings)
DRAWN_FACTS = ("primary_buildings", "primary_buildings_same_use")
# Use details (Ben, 2026-10-27: ask up front only what an architect knows at the start and what shapes the exterior or the
# envelope): who lives there, rooms let for profit (a use detail, the coordinator for Ben, 2026-10-27; the number of homes
# and new-or-converted stay up front), and a home business. Not asked in the start box; answered later, when the interior is planned,
# with the panel's Enter flow. Their rules never pass while unanswered (they stay "needs review"); the panel lists them
# in their own collapsed group, apart from the building's problems (is_use_detail). Ben will settle the exact questions
# later, so this tuple is the one place that moves them: a fact added here leaves the start box and joins that group.
DEFERRED_FACTS = ("unrelated_persons", "unrelated_persons_with_children", "occupants", "occupants_most_in_one_unit",
                  "owner_occupied", "functional_family_unit",
                  "home_occupation", "home_occupation_area", "home_occupation_unit_area", "rooms_let_for_profit",
                  "adu_bedrooms", "adu_floor_area", "primary_floor_area")
# Facts the measuring checks against each other (a count with the children counted can't be smaller than the count
# without: model_measurement.project.fact_conflict_rows): kept or dropped together, so a contradiction is never hidden
# by dropping half of it.
CHECKED_TOGETHER = (("unrelated_persons", "unrelated_persons_with_children"),)
# the group's title is short, so the narrow panel shows it whole with its count ("Use details (for later) · 3"); when to
# answer is said in each row's reason instead (coordinator for Ben, 2026-10-28)
USE_DETAILS_TITLE = "Use details (for later)"
USE_DETAILS_WHEN = "Answer when you plan the interior"
# Facts never asked in the start box, each with the fact that must be entered before a row asks it: the number of
# private garages matters only when the cars they hold are over the chart's limit (a lot of three cars or fewer passes
# whatever the count), so asking it up front would ask every architect with a garage a question that rarely matters.
# A row waiting on the garage's car limit asks the cars first (needs_of); entered over the limit, it then asks this.
# An accessory dwelling unit's facts likewise wait for "is there an ADU" (asked in the start box: a detached ADU is a
# building, so it shapes the exterior, Ben 2026-10-30), and a detached one's for
# "detached?": a lot without an ADU is never asked them (its rules are not applicable once that is answered no).
ROW_ONLY_FACTS = {"private_garages": "garage_cars", "adu_detached": "accessory_dwelling_unit",
                  "adus_on_parcel": "accessory_dwelling_unit", "adu_bedrooms": "accessory_dwelling_unit",
                  "adu_existing_building": "adu_detached", "adu_floor_area": "adu_detached",
                  "primary_floor_area": "adu_detached"}
BOX_ASKS = tuple(k for k in STATED_FACTS if k != "stories" and k not in INTERIOR_FACTS + DRAWN_FACTS + DEFERRED_FACTS
                 and k not in ROW_ONLY_FACTS)   # what the box can ask


def is_use_detail(item, facts=None):
    """Whether a panel row is a use detail still waiting to be answered: it needs review, and everything it is waiting
    on (its "needs") is a deferred fact that is still blank in `facts`. Only then: a row waiting on anything else too,
    one with no named need, a row about facts that disagree (they are filled in), and any row that has been decided
    (complies, fails) stays among the building's rows, so an answer that fails counts as a failure and a question left
    open never reads as a pass."""
    needs = item.get("needs") or []
    return (item.get("status") == "needs_review" and bool(needs) and all(k in DEFERRED_FACTS for k in needs)
            and all((facts or {}).get(k) is None for k in needs)
            and not str(item.get("id") or "").startswith("facts.conflict"))


# What a use itself says about a fact, from the City's own definitions, so it is never asked (Ben, 2026-10-25):
# §325-3 "DWELLING, ONE-FAMILY — A dwelling unit…" (chapter p.7) and "DWELLING, TWO-FAMILY — A building containing two
# dwelling units…" (p.9). Exactly these uses: a semi-detached or attached one-family dwelling is one unit of a
# building the rules count as a whole (R-3a's note 7 reads the row's dwelling units), so its count is asked, never
# taken as 1 (a row of six would pass a lot sized for three).
IMPLIED_BY_USE = {"one_family_detached": {"dwelling_units": 1}, "two_family": {"dwelling_units": 2}}
IMPLIED_SOURCE = "said by the use (City definition, §325-3)"


def implied_facts(use):
    """What the use itself says (IMPLIED_BY_USE), for this use only: never a prefix or a guess."""
    return dict(IMPLIED_BY_USE.get(use) or {})


# A fact that only matters once another is "yes": its rules are gated by it (a stream's distance by "a stream is within
# 20 ft", the home occupation's floor areas by "a home occupation is planned"), so it is asked only after that answer.
# Until then the rules say they need the first answer, never the second.
ASKED_AFTER = {"home_occupation_area": "home_occupation", "home_occupation_unit_area": "home_occupation",
               "stream_distance": "stream_near_lot"}


def follow_up_keys(options, zone, use, answers=None):
    """The facts the box asks after Use for this district and use (options["follow_ups"], from the rulebook). With
    `answers` (the facts as entered so far), a fact in ASKED_AFTER is asked only when the one it waits on is yes;
    without them, every fact the rules read."""
    keys = [k for k in (((options or {}).get("follow_ups") or {}).get(zone) or {}).get(use) or [] if k in BOX_ASKS]
    if answers is None:
        return keys
    return [k for k in keys if k not in ASKED_AFTER or answers.get(ASKED_AFTER[k]) is True]


def gate_of(answers):
    """The answers that decide which follow-up questions are asked (the ones ASKED_AFTER names): what the box compares
    to know it must open again."""
    return {p: (answers or {}).get(p) is True for p in sorted(set(ASKED_AFTER.values()))}


# What each question is called in the box's compact "About this project" section (the full question is its hover text
# and the panel's Enter prompt), and the one-click answers it offers after "Not answered". A yes / no question offers
# its two answers in the architect's words; a count with a small range offers the numbers. Never a default: the
# dropdown starts on "Not answered" and the rules that read the fact say so (NEVER a false pass).
ABOUT_LABELS = {
    "unrelated_persons": "Unrelated people in one home",
    "unrelated_persons_with_children": "Unrelated people in one home",
    "occupants": "Occupants on the lot",
    "occupants_most_in_one_unit": "Most occupants in one unit",
    "rooms_let_for_profit": "Rooms let for profit",
    "dwelling_units": "Homes on this lot",
    "attached_units_in_building": "Homes in the attached building",
    "owner_occupied": "Owner lives in the house",
    "accessory_dwelling_unit": "Accessory dwelling unit",
    "functional_family_unit": "Functional family unit",
    "home_occupation": "Home business",
    "home_occupation_area": "Business floor area (sq ft)",
    "home_occupation_unit_area": "Its home's floor area (sq ft)",
    "stream_near_lot": "Stream or inlet",
    "stream_distance": "Distance to it (ft)",
    "south_hill_overlay": "South Hill Overlay",
    "garage_cars": "Private garage, cars",
    "abuts_r1_district": "Next to R-1 land",
    "conversion": "New or converted",
}
ABOUT_WORDS = {            # (the "no" answer, the "yes" answer)
    "owner_occupied": ("Owner lives elsewhere", "Owner lives in the house"),
    "accessory_dwelling_unit": ("No ADU on the lot", "ADU on the lot"),
    "adu_detached": ("Attached (in or on the house)", "Detached (its own building)"),
    "adu_existing_building": ("New construction", "In an existing accessory building"),
    "functional_family_unit": ("Not relying on one", "Will show it to the City"),
    "home_occupation": ("No home business", "Home business planned"),
    "stream_near_lot": ("No stream within 20 ft", "Stream or inlet within 20 ft"),
    "south_hill_overlay": ("Not in the South Hill Overlay", "In the South Hill Overlay"),
    "abuts_r1_district": ("No R-1 land touches it", "R-1 land touches or faces it"),
}
ABOUT_COUNTS = {            # a count's one-click numbers (a typed number is not offered here: the panel's Enter flow)
    "unrelated_persons": [("0 (one family)", 0)] + [(str(n), n) for n in range(1, 7)],
    "unrelated_persons_with_children": [("0 (one family)", 0)] + [(str(n), n) for n in range(1, 7)],
    "rooms_let_for_profit": [("None", 0)] + [(str(n), n) for n in range(1, 7)],
    "attached_units_in_building": [(str(n), n) for n in range(2, 9)],
    "dwelling_units": [(str(n), n) for n in range(1, 9)],
    "garage_cars": [("No garage", 0)] + [(str(n), n) for n in range(1, 7)],
}
# Several answers in one click (shown only when the district and use ask at least one of them; it fills the others
# that are asked and leaves the rest as they were). Each is a statement the architect makes by picking it.
QUICK_ANSWERS = (
    ("1 family, no roomers", {"unrelated_persons": 0, "unrelated_persons_with_children": 0, "rooms_let_for_profit": 0,
                              "functional_family_unit": False}),
    ("Owner lives there", {"owner_occupied": True}),       # whether an ADU is on the lot: asked up front, alone
    ("No home business", {"home_occupation": False}),
    ("No stream, not in South Hill", {"stream_near_lot": False, "south_hill_overlay": False}),
)


ABOUT_LABEL_WIDTH, ABOUT_FIELD_WIDTH, ABOUT_TYPED_WIDTH, ABOUT_QUICK_WIDTH = 190, 215, 100, 215   # px
ABOUT_NOTE_WIDTH = 560
QUICK_HINT = "Pick to fill several answers…"


def about_label(key):
    return ABOUT_LABELS.get(key) or STATED_FACTS[key][2][:1].upper() + STATED_FACTS[key][2][1:]


def choices_for(key, kind, value=None):
    """The one-click answers a question offers, [(words, value)], or None when it is typed (areas, distances, the
    counts without a small range). A value already set that the list lacks (typed in the panel) stays among them."""
    if kind == "yes_no":
        no, yes = yes_no_words(key)
        return [(no, False), (yes, True)]
    listed = ABOUT_COUNTS.get(key)
    if listed is None:
        return None
    if value is not None and value not in [v for _, v in listed]:
        listed = listed + [(str(value), value)]
    return list(listed)


def quick_answers(keys):
    """The one-click answers for several questions at once: [(words, {fact: value})], each only with the facts that are
    asked (`keys`), and only when it fills at least one."""
    out = []
    for words, sets in QUICK_ANSWERS:
        mine = {k: v for k, v in sets.items() if k in keys}
        if mine:
            out.append((words, mine))
    return out


def follow_up_rows(options, zone, use, facts):
    """The box's questions after Use: the facts the district's rules need for this use (follow_up_keys), each
    {"key", "label" (the full question), "short" (its name in the compact section), "kind" (count / yes_no / area /
    length), "value" (as entered, or None), "choices" (its one-click answers, or None when typed)}; none when the
    district has no such rule or the use says them."""
    return [{"key": k, "label": STATED_FACTS[k][0], "short": about_label(k), "kind": STATED_FACTS[k][1],
             "value": (facts or {}).get(k), "choices": choices_for(k, STATED_FACTS[k][1], (facts or {}).get(k))}
            for k in follow_up_keys(options, zone, use, facts or {})]


# The words a yes / no question's dropdown offers after "Not answered": (the "no" answer, the "yes" answer)
YES_NO_WORDS = {"conversion": ("New construction", "Conversion of an existing building")}
NOT_ANSWERED = "Not answered"
FOLLOW_UP_HELP = ("Your answers. Leave one blank and the rules that need it say needs review (never read as 0 "
                  "or No).")      # a sentence, never a fragment (the architect's review, 2026-10-28)


def yes_no_words(key):
    return YES_NO_WORDS.get(key) or ABOUT_WORDS.get(key) or ("No", "Yes")


def _listed(options, zone):
    return ((options or {}).get("district_uses") or {}).get(zone) or []


def use_note(options, zone, use):
    """What the box says under Use when the pick isn't permitted by right in the district: the chart's own words
    (a special permit), or, for a use the district's chart doesn't list at all, that its Use row won't comply.
    None when it is permitted (or the district lists no uses)."""
    listed = _listed(options, zone)
    for u in listed:
        if u["id"] == use:
            return u.get("note")
    if listed and use:
        name = ((options or {}).get("uses") or {}).get(use, use)
        return f"{name} isn't on {zone}'s list of uses in the zoning chart: its Use row won't comply."
    return None


def district_use_names(options, zone, current=None):
    """The Use dropdown's choices for the district: [(id, name)], permitted first, as the chart lists them; every
    city use when the district has none listed. The use already set stays among them even when the district doesn't
    list it (last), so opening the box never changes it unasked (use_note says why it won't comply)."""
    names = (options or {}).get("uses") or {}
    out = [(u["id"], u["name"]) for u in _listed(options, zone)] or list(names.items())
    if current and current not in [k for k, _ in out]:
        out.append((current, names.get(current, current)))
    return out


def box_needs_refresh(options, shown, now):
    """Whether the box must open again after a pick in its Use or district dropdown, or in a question another waits on
    (a stream's yes opens its distance): `shown` and `now` are (zone, use) or (zone, use, gate_of(answers)) as laid
    out and as picked. Again when the uses offered, the note under Use or the questions after it differ (their fields
    are laid out once); never for a pick that changes none of them."""
    def layout(zone, use, gate=None):
        asked = None if gate is None else {p: True for p, yes in gate.items() if yes}
        return district_use_names(options, zone, use), use_note(options, zone, use), \
            follow_up_keys(options, zone, use, asked)
    return layout(*shown) != layout(*now)


def answers_applied(facts, answers, zone, use, options, track=None):
    """The facts after the box (box_applied) and the keys the architect answered in it with a value. `track`: what
    the box knows this session (box_track); without it, from the facts alone."""
    out, after = box_applied(facts, answers, zone, use, options, track if track is not None else box_track(facts))
    shown = [k for k in (answers or {}) if k in BOX_ASKS and k not in after["said"]]
    return out, sorted(k for k in shown if out.get(k) is not None)


def box_track(facts, sources=None):
    """What the box carries across its picks (session only, saved_ui["_answers"]): "said", the facts whose stored
    value the use itself said (their saved source is IMPLIED_SOURCE; with no sources, those equal to what the facts'
    use says: implied_facts); "held", an architect's answer set aside while a use says that fact instead; "typed", the
    facts the architect answered in the box this session (each saved "entered by you" at Draw: typed_sources)."""
    facts = facts or {}
    if sources is None:
        said = [k for k, v in implied_facts(facts.get("use")).items()
                if k in BOX_ASKS and facts.get(k) == v and type(facts.get(k)) is type(v)]
    else:
        said = [k for k in BOX_ASKS if facts.get(k) is not None
                and ((sources or {}).get(k) or {}).get("source") == IMPLIED_SOURCE]
    return {"said": said, "held": {}, "typed": []}


def box_applied(facts, answers, zone, use, options, track):
    """The facts after the box, which changes only what it shows (Rhino runs, 2026-10-28, P0s: a Use or district
    picked and picked back blanked every answer, or brought back an older one). Returns (facts, track).
    1. Each field the box showed (a BOX_ASKS key in `answers`, laid out for the use the box opened with: None when
       blank) is set from its answer, or unset when blank or refused (its rules need review, never 0 or no), whatever
       the use picked now: what was typed is never dropped nor replaced by an older answer.
    2. A fact the old use said (track "said": by its source, never by its value) goes when the new use doesn't say
       it, and the architect's own answer set aside for it ("held") comes back: a two-family's 2 units are never read
       as a multiple dwelling's count, and a semi-detached pair's typed 2 survives a look at two-family.
    3. What the new use says for the facts its rules read (implied_by) is set; an architect's answer there is held.
    4. A fact asked only after another's yes (ASKED_AFTER) goes when that question is answered no in the box: it no
       longer applies (a blank keeps it: nothing contradicts it, and its rule needs review either way).
    Every other fact stays as stored, never read unshown: any fact this district's rules read for this use is asked
    (follow_up_keys) and shown with its value when the box opens laid out for it (box_needs_refresh). A fact asked
    only after another's yes (ASKED_AFTER: a stream's distance) is read only by rules gated by that yes. The use
    details (DEFERRED_FACTS, answered in the panel's row dialog, never in the box) stay as stored whatever the use or
    district: where the new use's rules don't read one it decides nothing, and where they do it is the architect's
    answer, shown in its row; so the facts checked together (CHECKED_TOGETHER) always stay together, and a
    contradiction between them is never hidden by dropping half of it."""
    now = implied_by(options, zone, use)
    out = dict(facts or {})
    said, held = list((track or {}).get("said") or []), dict((track or {}).get("held") or {})
    typed = list((track or {}).get("typed") or [])
    given = {}
    for k, v in (answers or {}).items():
        if k not in BOX_ASKS:
            continue
        out.pop(k, None)
        held.pop(k, None)
        said = [x for x in said if x != k]
        typed = typed + [k] if k not in typed else typed
        if v is not None:
            given[k] = v
    out = update_counts(out, given)
    for k, gate in ASKED_AFTER.items():   # "no" said in the box to the question it waits on: moot, so it goes (#45: a
        if given.get(gate) is False:      # stream's old 5 ft beside a new "no stream within 20 ft" would make the
            out.pop(k, None)              # facts disagree)
    for k in [k for k in said if k not in now]:
        out.pop(k, None)
        said.remove(k)
        if k in held:
            out[k] = held.pop(k)
    for k, v in now.items():
        if k not in said and out.get(k) is not None:
            held[k] = out[k]
        out[k] = v
        said = said + [k] if k not in said else said
    return out, {"said": said, "held": held, "typed": typed}


def typed_sources(sources, track, facts, day):
    """The sources after Draw for the facts the architect answered in the box this session (track "typed"), shown
    or not by then: each set "entered by you" with its value now, each unset with no source (row_sources); what a
    use says keeps the use's (fact_sources)."""
    return row_sources(sources, [k for k in (track or {}).get("typed") or [] if k not in (track or {}).get("said", [])],
                       facts, day)


def implied_by(options, zone, use):
    """What the use says for the facts this district's rules read (options["implied"]): never asked."""
    return dict((((options or {}).get("implied") or {}).get(zone) or {}).get(use) or {})


def parse_answer(kind, text, key=None):
    """A follow-up field's text as the fact's value: a whole number (count: `key`'s least, 0 unless MINIMUM says
    more), a number of square feet or feet (area, length: 0 or more, as typed, never rounded), yes / no (yes_no);
    blank: None (unanswered: its rules stay NEEDS REVIEW, never 0 or no); anything else raises ValueError."""
    text = (text or "").strip().lower()
    if not text:
        return None
    if kind == "yes_no":
        if text in ("yes", "y"):
            return True
        if text in ("no", "n"):
            return False
        raise ValueError("answer yes or no")
    if kind in ("area", "length"):
        # commas only as thousands separators (1,200): "2,5" is not 25 (a European decimal comma is refused, not misread)
        if not re.fullmatch(r"((\d+|\d{1,3}(,\d{3})+)(\.\d+)?|\.\d+)", text, re.ASCII):
            raise ValueError("a number of " + ("square feet" if kind == "area" else "feet") + ", 0 or more")
        number = float(text.replace(",", ""))
        return int(number) if number == int(number) else number
    least = minimum(key) if key else 0
    if not (text.isascii() and text.isdigit()) or int(text) < least:
        raise ValueError(f"a whole number, {least} or more")
    return int(text)


def answer_problem(kind, text, key=None):
    """What the box says beside a follow-up field whose text isn't an answer (None when it is, or is blank): the
    entry is not kept, so the rules that need it say so (never read as 0)."""
    try:
        parse_answer(kind, text, key)
    except ValueError as e:
        return f"Not kept: {e}. Its rules need review until it is."
    return None


# The box's questions after Use, each as its words wrapped at QUESTION_WIDTH with its answer beside them, and one note
# under them all: the start box stays laptop-sized (≤ ~900 px wide) with the longest questions (#38's household ones
# ran ~1,200 px on one line and pushed the box to 1,560-2,020 px: Rhino run of demo 2c0a5c0). Pinned in
# test_box_width.py, which lays the real box out and bounds its width.
QUESTION_WIDTH = 360
ANSWER_WIDTH = 300     # every answer dropdown in a row's dialog one width, lined up ("Conversion of an existing
                       # building" fits; the architect's review, 2026-10-28)


TEXT_PX = 6.0      # px a character at size 12, a little over the system font's (~5.5 measured in Rhino): errs wide


def text_wider(text, size, px):
    """Whether `text` at `size` (13 when not set) runs wider than `px` on one line (by TEXT_PX), so its label wraps."""
    return len(text or "") * TEXT_PX * (size or 13) / 12 > px


def answers_note(entries):
    """The note under the box's questions, for `entries` [(key, kind, text)] in the order asked: FOLLOW_UP_HELP, or
    every entry not kept, each named by its fact ("Rooms let for profit: Not kept: …"), so each is said at once and
    never read as 0. Returns (text, refused)."""
    said = []
    for key, kind, text in entries:
        try:
            parse_answer(kind, text, key)
        except ValueError as e:
            said.append((STATED_FACTS[key][2] if key in STATED_FACTS else key.replace("_", " "), str(e)))
    if not said:
        return FOLLOW_UP_HELP, False
    if len(said) == 1:
        name, why = said[0]
        return f"{name[0].upper() + name[1:]}: Not kept: {why}. Its rules need review until it is.", True
    listed = ", ".join(f"{name} ({why})" for name, why in said)
    return f"Not kept: {listed}. Their rules need review until they are.", True


def needs_of(names, values, settles=None):
    """The stated facts a rule reads (`names`) that aren't set yet (`values`), in the order they are asked; never the
    stories count (asked only where the measuring asks for it: stories_needed). An optional one (OPTIONAL) only where
    `settles(key)` says entering it could change the row. A row-only fact (ROW_ONLY_FACTS) only once the fact it
    follows is entered."""
    return [k for k in STATED_FACTS if k != "stories" and k in names and (values or {}).get(k) is None
            and (k not in OPTIONAL or (settles is not None and settles(k)))
            and (k not in ROW_ONLY_FACTS or (values or {}).get(ROW_ONLY_FACTS[k]) is not None)]


def _and(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def enter_words(needs):
    """The button's words for a row waiting on `needs`: "Enter bedrooms and parking spaces"."""
    return "Enter " + _and([STATED_FACTS[k][2] for k in needs]) if needs else None


def answer_words(needs):
    """The words on a row's button and its dialog's title: the facts' own words while they fit a button ("Enter
    bedrooms and parking spaces"); longer, how many ("Answer 4 questions"): the whole list ran to ~25 words and was
    cut off on the button and in the title bar (the architect's review, 2026-10-28). The dialog lists each question
    and the row's reason still names them."""
    if not needs:
        return None
    words = enter_words(needs)
    return words if len(needs) == 1 or len(words) <= BUTTON_WORDS else "Answer %d questions" % len(needs)


BUTTON_WORDS = 40       # characters a row's button holds at the panel's width (380-460 px) without being cut off


def needs_reason(needs):
    """Why the row isn't checked: "Needs bedrooms and parking spaces, which the model doesn't show" (its button,
    enter_words, asks exactly those in a small dialog: row_fields)."""
    if not needs:
        return None
    return "Needs " + _and([STATED_FACTS[k][2] for k in needs]) + ", which the model doesn't show"


# ---- a row's own dialog (coordinator, 2026-10-28, agreed with Ben): the row's "Enter …" button asks only the
# stated facts that row waits for (its `needs`), in a small modal dialog; OK saves exactly those, each "entered by
# you" with the day, as one Undo step, and checks again; Cancel, Esc or closing it changes nothing. It never touches
# the address, the lookup, the district, the use, the lot, the street side or any other fact: those stay in the
# start box (Edit site…), whose follow-up questions read the same facts, so an answer given here shows there.

SITE_HINT = "Edit site…"            # a row whose missing fact comes from the site (present.py's hint for it)
SITE_ASKS = ("Corner lot?",)        # the start box's own question a measuring's reason names (stops.py)


def row_fields(needs, facts):
    """The dialog's questions for a row waiting on `needs`, in the row's order: each {"key", "label", "kind"
    (count / yes_no), "value" (as saved, or None)}. Only stated facts (STATED_FACTS): never a site fact."""
    return [{"key": k, "label": STATED_FACTS[k][0], "kind": STATED_FACTS[k][1], "value": (facts or {}).get(k)}
            for k in needs or [] if k in STATED_FACTS]


def row_choice(value):
    """A yes / no question's dropdown index for a saved value: Not answered (0), the no answer (1), the yes (2)."""
    return {None: 0, False: 1, True: 2}[value]


def row_choice_text(index):
    """A yes / no dropdown's pick as parse_answer reads it: Not answered is blank (never no)."""
    return {1: "no", 2: "yes"}.get(index, "")


def row_answers_applied(facts, needs, answers):
    """The facts after OK in a row's dialog: each key in `needs` set from its answer (`answers`: key -> the text
    typed, or "yes" / "no" / "" from a dropdown: row_choice_text); a blank (or missing) answer leaves that fact unset,
    so its rules need review (never 0 or no). Every other key is exactly as it was. Any entry that isn't an answer
    raises ValueError with words for the dialog, and nothing changes."""
    out = dict(facts or {})
    bad = []
    for k in [k for k in needs or [] if k in STATED_FACTS]:
        try:
            value = parse_answer(STATED_FACTS[k][1], (answers or {}).get(k), k)
        except ValueError as e:
            bad.append(f"{STATED_FACTS[k][0]}: {e}")
            continue
        if value is None:
            out.pop(k, None)
        else:
            out[k] = value
    if bad:
        raise ValueError("Not saved. " + "; ".join(bad) + ". Correct it, or leave it blank (it then needs review).")
    return out


def row_problem(facts, needs, answers):
    """What the row's dialog says at OK when an entry isn't an answer (row_answers_applied's words; it stays open
    and nothing is saved), or None when OK may close it."""
    try:
        row_answers_applied(facts, needs, answers)
    except ValueError as e:
        return str(e)
    return None


def row_sources(sources, needs, facts, day):
    """The saved sources after OK in a row's dialog: each fact in `needs` that is set, "entered by you" on `day`;
    one left blank, none (an unset fact has no source). Every other source is exactly as it was."""
    out = dict(sources or {})
    for k in [k for k in needs or [] if k in STATED_FACTS]:
        v = (facts or {}).get(k)
        if v is None:
            out.pop(k, None)
        else:
            out[k] = {"value": {True: "yes", False: "no"}.get(v, v) if isinstance(v, bool) else v,
                      "source": ENTERED, "confirmed_by": "you", "date": day}
    return out


def site_row(item):
    """Whether a row waits on a site fact (address, lot, district, street side, corner lot): only the start box
    gives those, so the row keeps its Edit site… button."""
    item = item or {}
    return item.get("hint") == SITE_HINT or any(q in (item.get("reason") or "") for q in SITE_ASKS)


def row_buttons(item):
    """A row's buttons, as (words, action): its own dialog for the stated facts it waits on ("Enter dwelling
    units…", action "enter"), then, where a site fact is missing too, Edit site… ("edit_site") as the second."""
    out = []
    if (item or {}).get("needs"):
        out.append((answer_words(item["needs"]) + "…", "enter"))
    if site_row(item):
        out.append((SITE_HINT, "edit_site"))
    return out


def box_answers(options, zone, use, facts):
    """What the start box's follow-up questions show as answered: read from the saved facts themselves (the box
    keeps no copy of its own), so an answer given in a row's dialog shows in the box and Draw sets it again."""
    return {k: (facts or {}).get(k) for k in follow_up_keys(options, zone, use)}


def update_counts(facts, answers):
    """Bedrooms, parking spaces, stories, dwelling units and rooms let for profit (whole numbers, 0 or more) and
    whether the building is a conversion and whether the lot abuts R-1 land (yes / no) from the Lot facts prompts. An answer of None means the prompt
    was skipped: the fact stays as it was (unset stays unset, so its rules stay NEEDS REVIEW), never 0 or no."""
    out = dict(facts or {})
    counts = list(dict.fromkeys(["stories"] + [k for k, (_, kind, _) in STATED_FACTS.items() if kind == "count"]))
    for key in counts:
        if answers.get(key) is not None:
            n = int(answers[key])
            if n < minimum(key) or n != answers[key]:
                raise ValueError(f"{key} must be a whole number, {minimum(key)} or more")
            out[key] = n
    for key in [k for k, (_, kind, _) in STATED_FACTS.items() if kind in ("area", "length")]:
        if answers.get(key) is not None:
            a = answers[key]
            if type(a) not in (int, float) or not math.isfinite(a) or a < 0:
                raise ValueError(f"{key} must be a number of {'square feet' if STATED_FACTS[key][1] == 'area' else 'feet'}, 0 or more")
            out[key] = a
    for key in [k for k, (_, kind, _) in STATED_FACTS.items() if kind == "yes_no"]:
        if answers.get(key) is not None:
            out[key] = bool(answers[key])
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
    """The saved facts without a lot, main building or ADU's building that is no longer in the model (redrawn, joined, deleted):
    the lot's street lines go with it, so the confirm dialog asks again instead of keeping an id nothing has."""
    out = dict(facts or {})
    if out.get("lot_id") and out["lot_id"] not in lot_ids:
        out.pop("lot_id")
        set_street_lines(out, None)
    if out.get("main_building") and out["main_building"] not in building_ids:
        out.pop("main_building")
    if out.get("adu_building") and out["adu_building"] not in building_ids:      # the ADU's building, the same way
        out.pop("adu_building")
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
        out.pop("ground_fall", None)         # and so did its ground (lot_ground_dropped: the saved state's too)
    return out


def lot_ground_dropped(saved_ui):
    """The saved state once the architect puts another lot in place of the looked-up one (their survey, a lot they
    drew, another outline picked): the looked-up ground fall was read on the old lot, so it no longer shows the lot
    level (review round 3: a level reading kept after the lookup's doubtful lot was replaced let height and stories
    pass on ground never read). Height and stories need review until the address is looked up again."""
    saved_ui = dict(saved_ui)
    saved_ui.pop("ground_fall", None)
    return saved_ui


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
    here: always None, so the box asks it and the yards wait for the answer. A lot's "segments_ft" (the same
    segments in feet, when given) decide the street's lengths and turns, in feet as everywhere (review round 6,
    F2: a 6 mm slip in a millimetre model read as a 6 ft line)."""
    facts = {"jurisdiction": jurisdiction, "zone": zones[0] if zones else None, "use": "one_family_detached",
             "corner_lot": None, "ground_is_flat": True, "lot_surveyed": False}
    lot = max(lots, key=lambda l: l["area"]) if lots else None
    if lot is not None:
        facts["lot_id"] = lot["id"]
        if lot["segments"]:
            outline = [[[p[0], p[1]], [q[0], q[1]]] for p, q in lot["segments"]]
            feet = [[list(p[:2]) for p in line] for line in lot.get("segments_ft") or outline]
            # the lowest piece a street can start from (never a point drawn twice: round 4; an arc drawn in short
            # chords is a line: round 7)
            run = next((r for k in sorted(range(len(feet)), key=lambda k: (outline[k][0][1] + outline[k][1][1]) / 2)
                        for r in [street_run(feet, feet[k], tolerance=0.0)] if r is not None), None)
            # the whole street it is on (review round 1, F1: a tax-map street suggested as one piece), only when
            # both its ends are sure; else no suggestion, so the box asks for the click and the click asks the
            # question (round 3, F1: a curving street suggested as its first 30°, the front yard from part of it)
            if run and run["maybe"] == [[], []]:            # (an id on every line: "Street 1")
                set_street_lines(facts, [outline[k] for k in run["pieces"]], ["Street 1"] * len(run["pieces"]))
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


DIM_TICK_PX = 10        # a dimension's architectural tick: this long on screen, at 45° to its line
HALO_PX = 1           # a dimension's halo: this many pixels each side of its line
FAINT_ALPHA = 110       # the required line, faint: the status colour at this opacity (of 255)


# a yard's dimension and its label, placed on screen as a drawing would (Rhino checks of #29, 2026-10-25)
DIM_RGB = {"complies": ((92, 96, 100), (176, 180, 184)),          # (light viewport, dark viewport): neutral grey,
           "needs_review": ((138, 88, 0), (233, 180, 76)),          # amber, red: colour only what's wrong
           "does_not_comply": ((184, 55, 31), (240, 122, 112))}
REQUIRED_RGB = ((96, 96, 96), (190, 190, 190))     # the required line: a clear dashed grey, with its "min" tag
# (darker on a light viewport, lighter on a dark one than the first version: Rhino check of #29 at f6642a9)
DIM_LABEL_H_PX = 18     # a dimension's label: its height on screen
DIM_LABEL_GAP_PX = 4    # and its gap from the dimension line (and past the line's outer end)


def dim_rgb(status, dark):
    """A dimension's colour (r, g, b): red fails, amber needs review, a neutral dark grey (light on a dark viewport)
    complies: drafting's convention, and Ben's "colour only what's wrong"."""
    return DIM_RGB.get(status, DIM_RGB["complies"])[1 if dark else 0]


def rect_quad(box):
    """An (x, y, w, h) screen box as its four corners."""
    x, y, w, h = box
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _segments_cross(p, q, r, s_):
    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2, d3, d4 = side(r, s_, p), side(r, s_, q), side(p, q, r), side(p, q, s_)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def _point_in(pt, poly):
    x, y = pt
    hit = False
    for k in range(len(poly)):
        (x0, y0), (x1, y1) = poly[k - 1], poly[k]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def shapes_hit(a, b):
    """Whether two screen polygons (lists of corners) overlap: an edge of one crosses the other's, or one lies
    inside the other."""
    for k in range(len(a)):
        for j in range(len(b)):
            if _segments_cross(a[k - 1], a[k], b[j - 1], b[j]):
                return True
    return bool(a and b) and (_point_in(a[0], b) or _point_in(b[0], a))


def _along(a, b):
    n = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
    return ((b[0] - a[0]) / n, (b[1] - a[1]) / n), n


def _point_segment(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    t = 0.0 if n <= 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return ((p[0] - a[0] - t * dx) ** 2 + (p[1] - a[1] - t * dy) ** 2) ** 0.5


TAG_SIZE = 11            # a "min" tag's text size (readable at the default zoom: Rhino check of #29 at f6642a9)
VIEW_MARGIN_PX = 3      # every number and tag stays this far inside the view


def dim_number(mark, proposed, status):
    """What a dimension shows on the drawing, as a drawing does: its number only, "✕ " or "? " before it when the
    yard fails or needs review (colour says the rest). Its name, what it needs and "(approx.)" are the panel's and
    the notice's (Rhino checks of #29: a long label never fit a plan)."""
    return (mark + " " if status in ("does_not_comply", "needs_review") and mark else "") + proposed


def inside_view(shape, view, margin=VIEW_MARGIN_PX):
    """Whether a screen polygon lies wholly inside the view (w, h), `margin` px in. True without a view."""
    if not view:
        return True
    return all(margin <= x <= view[0] - margin and margin <= y <= view[1] - margin for x, y in shape)


PRIORITY = {"does_not_comply": 0, "needs_review": 1}      # what is wrong placed first: it gets the clear spots


#                                        (0.7 × 11 px ≈ 8 px: the smallest that still reads)


#                        of #29 at 5891efc: the rear number touched an edge length)


def limit_label_spot(line, house, w, h=18, view=None, gap=8, taken=()):
    """Where an elevation's "Height limit 35'-0"" label goes (screen): past an end of the limit line, outside the
    building's extent (`house`: its box on screen, x0, y0, x1, y1), centred on the line's height, in view; the
    left end first, and the end whose spot covers nothing drawn (`taken`, boxes: the height's number, the status
    box, the notice) before one that does. It never covers the coloured parts (Rhino check of #28 at fc0b023).
    (x, y) of its top left, or None when neither end has room in view."""
    (ax, ay), (bx, by) = sorted(line)
    spots = [(min(ax, house[0] if house else ax) - gap - w, ay - h / 2),
             (max(bx, house[2] if house else bx) + gap, by - h / 2)]
    shown = [(x, y) for x, y in spots if inside_view(rect_quad((x, y, w, h)), view)]
    for x, y in shown:
        if not any(shapes_hit(rect_quad((x, y, w, h)), rect_quad(t)) for t in taken):
            return x, y
    return shown[0] if shown else None


def _bbox(shape):
    xs, ys = [p[0] for p in shape], [p[1] for p in shape]
    return min(xs), min(ys), max(xs), max(ys)


def dim_ticks(a, b, size=DIM_TICK_PX):
    """A drawing-style dimension's two end ticks on screen: at each end of the line a to b, a short slash at 45°
    to the line (as an architect draws one, whichever way the line runs), `size` pixels long. [] for a line of no
    length on screen (seen end on)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = (dx * dx + dy * dy) ** 0.5
    if n < 1e-9:
        return []
    ux, uy = dx / n, dy / n
    sx, sy = (ux - uy) * 0.5 ** 0.5 * size / 2, (uy + ux) * 0.5 ** 0.5 * size / 2   # the line turned 45°
    return [((p[0] - sx, p[1] - sy), (p[0] + sx, p[1] + sy)) for p in (a, b)]


def dims_shown(zoomed_in, elevation=False):
    """Whether a yard's dimension (its line, ticks, faint required line) is drawn at all: only at working zoom
    (zoomed out to the neighbourhood every dimension gives way with the labels, labels_shown), and never in an
    elevation (Front, Right…), where every yard's line would lie flat on the ground line. Its words also follow
    Show on-screen labels (yard_label_shown) and show in plan only. The height's dimension is the other way round:
    elevations only."""
    return bool(zoomed_in) and not elevation


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


def _point_seg(px, py, line):
    """A point's distance from a segment (screen pixels)."""
    (ax, ay), (bx, by) = line
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def box_gap(line, box):
    """How far a box (left, top, w, h) is from a screen line ((x1, y1), (x2, y2)), exactly: 0 when they touch."""
    left, top, w, h = box
    if crosses(line, left, top, w, h):
        return 0.0
    corners = ((left, top), (left + w, top), (left, top + h), (left + w, top + h))
    ends = [((max(left - x, 0, x - left - w) ** 2 + max(top - y, 0, y - top - h) ** 2) ** 0.5) for x, y in line]
    return min(ends + [_point_seg(x, y, line) for x, y in corners])


LABEL_MIN_SIZE = 9                 # a plan label's text is never smaller (readable on screen)
LABEL_LEAD_REACH = 3               # how far a led label may sit from its line: this many label heights
LABEL_STEP = 6                     # the lattice the spots near a line are tried on, screen pixels


def label_height(rows, size):
    """A plan label's height on screen: its lines (size + 5 px each: 16 px at 11 pt) and 4 of margin."""
    return 4 + (size + 5) * rows


def _over(box, other):
    """Whether two (left, top, w, h) boxes overlap (touching edges don't)."""
    return min(box[0] + box[2], other[0] + other[2]) > max(box[0], other[0]) and \
        min(box[1] + box[3], other[1] + other[3]) > max(box[1], other[1])


def _inside(x, y, poly):
    """Whether a point is inside a polygon (screen points; even-odd)."""
    inside = False
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def box_over_shape(box, poly):
    """Whether a box (left, top, w, h) covers any of a polygon (its screen points), 3 px around it included."""
    left, top, w, h = box[0] - 3, box[1] - 3, box[2] + 6, box[3] + 6
    if len(poly) < 3:
        return False
    if any(crosses(edge, left, top, w, h) for edge in zip(poly, poly[1:] + poly[:1])):
        return True
    if any(left <= x <= left + w and top <= y <= top + h for x, y in poly):
        return True
    return _inside(left + w / 2, top + h / 2, poly)


LABEL_INSET = 4                    # a plan label stays this far inside the view (#29 at e4e5018: one on its edge)
AXIS_ICON_PX = 80                  # Rhino's world-axis icon, bottom left of every view: a square this wide kept clear
# (the Rhino job at 8bfabdd: it spans x 34-76, y 593-634 in a 657 x 668 view), 3 px more around it
AXIS_ICON_SCALE = 1.0              # the display's scaling where screen pixels are physical (set by the plugin)


def axis_icon_box(view):
    """Where Rhino draws the world-axis icon in a view (w, h): its bottom-left corner, AXIS_ICON_PX (scaled by
    AXIS_ICON_SCALE) and 3 px around it (#29 at e4e5018: a label on it)."""
    side = int(round(AXIS_ICON_PX * AXIS_ICON_SCALE)) + 3
    return 0, view[1] - side, side, side


def label_breaks_hard(line, box, view, hard_boxes=(), hard_lines=(), hard_shapes=(), placed=()):
    """Which HARD rule a plan label's box (left, top, w, h) breaks, or None. HARD: on screen; over no building
    footprint nor coloured part (`hard_shapes`: their outlines on screen, 3 px around them), nor the notice, the
    status box or the north arrow (`hard_boxes`, 3 px around them), nor a label already placed (`placed`: a label is
    never hidden under another, the Rhino job at 4bb6d4d); 3 px off its own dimension `line` (the front yard's ran along
    its own label's edge, the Rhino job at 822fb6f) and every line in
    `hard_lines` (every other yard's dimension, 3 px around it: the southwest label sat 1 px beside the front's)."""
    left, top, w, h = box
    if view is not None:
        i_ = LABEL_INSET
        if left < i_ or top < i_ or left + w > view[0] - i_ or top + h > view[1] - i_:
            return "off screen or on its edge"
        if _over(box, axis_icon_box(view)):
            return "over the world-axis icon"
    if any(box_over_shape(box, shape) for shape in hard_shapes):
        return "over a building or its coloured part"
    if any(_over(box, (a - 3, b - 3, c + 6, e + 6)) for a, b, c, e in hard_boxes):
        return "over the notice, the status box or the north arrow"
    if any(_over(box, other) for other in placed):
        return "over another label"
    if crosses(line, left - 3, top - 3, w + 6, h + 6):
        return "on its own line"
    if any(crosses(other, left - 3, top - 3, w + 6, h + 6) for other in hard_lines if other != line):
        return "on another yard's dimension"
    return None


def label_spots(line, w, h, reach, step=LABEL_STEP):
    """Every spot for a w × h label within `reach` of its dimension `line` (screen pixels), on a `step` lattice from
    the line's own corner, nearest first."""
    (xa, ya), (xb, yb) = line
    x0, x1, y0, y1 = min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)
    spots = []
    nx, ny = int((x1 - x0 + w + 2 * reach) / step) + 1, int((y1 - y0 + h + 2 * reach) / step) + 1
    for j in range(ny):
        top = y0 - h - reach + j * step
        for i in range(nx):
            left = x0 - w - reach + i * step
            gap = box_gap(line, (left, top, w, h))
            if gap <= reach:
                spots.append((gap, left, top))
    spots.sort()
    return spots


def _seg_x_in_band(seg, ylo, yhi):
    """The x extent of a segment's part inside the horizontal band ylo..yhi (screen pixels), or None."""
    (x1, y1), (x2, y2) = seg
    if max(y1, y2) < ylo or min(y1, y2) > yhi:
        return None
    if abs(y2 - y1) < 1e-12:
        return min(x1, x2), max(x1, x2)
    ta, tb = (ylo - y1) / (y2 - y1), (yhi - y1) / (y2 - y1)
    t0, t1 = max(0.0, min(ta, tb)), min(1.0, max(ta, tb))
    xa_, xb_ = x1 + t0 * (x2 - x1), x1 + t1 * (x2 - x1)
    return min(xa_, xb_), max(xa_, xb_)


class _LabelField:
    """The things a plan label must keep off, prepared once for a label (the Rhino job at 822fb6f: testing every
    spot against every obstacle took up to 309 ms a label). For one row of spots (a top, a w × h label) each
    obstacle is the stretch of lefts it rules out, worked out once for the row: a box or a placed label its width
    plus the label's; a line or a building's outline the extent of its part inside the row's band (3 px around),
    plus the label's width. That is exact for boxes, lines and convex outlines, and never less than the truth for
    others (a spot it lets through always keeps the HARD rules; label_breaks_hard still checks the one chosen)."""

    def __init__(self, line, view, hard_boxes=(), hard_lines=(), hard_shapes=(), placed=(), soft_lines=()):
        self.view = view
        self.rects = [(a - 3, b - 3, c + 6, e + 6) for a, b, c, e in hard_boxes] + [tuple(p)[:4] for p in placed]
        if view is not None:
            self.rects.append(axis_icon_box(view))
        self.segs = [(line, 3)] + [(d, 3) for d in hard_lines if d != line]
        self.polys = []
        for shape_ in hard_shapes:
            if len(shape_) >= 3:
                pts = [tuple(q) for q in shape_]
                self.polys.append((list(zip(pts, pts[1:] + pts[:1])), min(q[1] for q in pts), max(q[1] for q in pts)))
        self.soft = [s_ for s_ in soft_lines if s_ != line]

    def _blocked(self, top, w, h):
        out = []
        for rx, ry, rw, rh in self.rects:
            if min(top + h, ry + rh) > max(top, ry):
                out.append((rx - w, rx + rw))
        for seg, m in self.segs:
            r = _seg_x_in_band(seg, top - m, top + h + m)
            if r is not None:
                out.append((r[0] - m - w, r[1] + m))
        ylo, yhi = top - 3, top + h + 3
        for edges, pymin, pymax in self.polys:
            if pymax < ylo or pymin > yhi:
                continue
            lo = hi = None
            for edge in edges:
                r = _seg_x_in_band(edge, ylo, yhi)
                if r is not None:
                    lo = r[0] if lo is None else min(lo, r[0])
                    hi = r[1] if hi is None else max(hi, r[1])
            if lo is not None:
                out.append((lo - 3 - w, hi + 3))
        return out

    def pieces(self, top, w, h, base, step, n):
        """The runs of lattice spots (lefts base + i·step, i < n) on the row at `top` that keep every HARD rule,
        each cut where the number of lot lines a label there crosses changes: [(i0, i1, crossed)]."""
        if self.view is not None and (top < LABEL_INSET or top + h > self.view[1] - LABEL_INSET):
            return []
        lo_i, hi_i = 0, n - 1
        if self.view is not None:
            lo_i = max(lo_i, int(math.ceil((LABEL_INSET - base) / step - 1e-9)))
            hi_i = min(hi_i, int(math.floor((self.view[0] - LABEL_INSET - w - base) / step + 1e-9)))
        if lo_i > hi_i:
            return []

        def index_span(a, b):
            return int(math.ceil((a - base) / step - 1e-9)), int(math.floor((b - base) / step + 1e-9))
        blocked = sorted(index_span(a, b) for a, b in self._blocked(top, w, h))
        free, at = [], lo_i
        for a, b in blocked:
            if b < at:
                continue
            if a > at:
                free.append((at, min(a - 1, hi_i)))
            at = max(at, b + 1)
            if at > hi_i:
                break
        if at <= hi_i:
            free.append((at, hi_i))
        free = [(a, b) for a, b in free if a <= b]
        if not free or not self.soft:
            return [(a, b, 0) for a, b in free]
        soft = []
        for seg in self.soft:
            r = _seg_x_in_band(seg, top, top + h)
            if r is not None:
                soft.append(index_span(r[0] - w, r[1]))
        out = []
        for a, b in free:
            cuts = sorted({a, b + 1} | {c for s0, s1 in soft for c in (s0, s1 + 1) if a < c <= b})
            for c0, c1 in zip(cuts, cuts[1:]):
                out.append((c0, c1 - 1, sum(s0 <= c0 <= s1 for s0, s1 in soft)))
        return out


def _nearest_index(line, top, w, h, base, step, i0, i1):
    """The spot in the run i0..i1 nearest its line (a label's distance from its line along a row is convex: one
    least; worked out directly for a level or plumb line, else by a ternary search)."""
    (xa, ya), (xb, yb) = line
    if abs(xa - xb) < 1e-9 or abs(ya - yb) < 1e-9:      # level or plumb: the x gap alone decides along a row
        lo = int(math.ceil((min(xa, xb) - w - base) / step - 1e-9))
        hi = int(math.floor((max(xa, xb) - base) / step + 1e-9))
        return i0 if hi < i0 else i1 if lo > i1 else max(i0, lo)

    def g(i):
        return box_gap(line, (base + i * step, top, w, h))
    a, b = i0, i1
    while b - a > 2:
        m1, m2 = a + (b - a) // 3, b - (b - a) // 3
        if g(m1) <= g(m2):
            b = m2
        else:
            a = m1
    return min(range(a, b + 1), key=lambda i: (g(i), i))


def place_dim_label(line, text, size, view, hard_boxes=(), hard_lines=(), soft_boxes=(), soft_lines=(),
                    hard_shapes=(), placed=()):
    """Where a plan label for the dimension `line` goes (screen pixels), by one complete set of rules (the Rhino job
    at 319dc5d: each round's fix moved the southwest yard's label onto the next obstacle nobody had listed):
    - HARD, never broken (label_breaks_hard): on screen; over no building footprint or coloured part
      (`hard_shapes`), nor the notice, the status box or the north arrow (`hard_boxes`), nor a label placed before
      (`placed`); 3 px off its own line and every other yard's dimension (`hard_lines`).
    - SOFT, least first: other labels covered (`soft_boxes`), then, for a led label, the HARD things its leader
      crosses, then lines crossed (`soft_lines`: the lot's edges), then its distance from its own line.
    - Within one label height of its line, on one line, then on two (name, then numbers: label_lines), the spots
      on a LABEL_STEP lattice; then smaller, a point at a time down to LABEL_MIN_SIZE; then, at its own size, up to
      LABEL_LEAD_REACH label heights away; then the nearest spots anywhere on screen that break no HARD rule, at
      its own size, then the smallest. A label more than 8 px from its line is led to it (`led`). Only when no spot
      on the whole screen keeps every HARD rule is one broken (`forced`, never silent; still over no label placed
      before), so a failing yard's label is never dropped.
    Fast (the Rhino job at 822fb6f: up to 309 ms a label): each row of spots is worked out as runs that keep the
    HARD rules (_LabelField), only the nearest spot of each run is weighed, and the rows nearest the line go first
    (then those nearest its middle), stopping at the first spot beside the line with nothing SOFT against it.
    Returns {"left", "top", "w", "h", "rows", "size", "led", "forced", "gap"}."""
    (xa, ya), (xb, yb) = line
    mx, my = (xa + xb) / 2, (ya + yb) / 2
    x0, x1, y0, y1 = min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)
    two = label_lines(text)
    variants = [[text]] + ([two] if len(two) == 2 else [])
    field = _LabelField(line, view, hard_boxes, hard_lines, hard_shapes, placed, soft_lines)
    lead_boxes = list(hard_boxes) + list(soft_boxes)

    def shape(rows, pt):
        return max(label_width(r, pt) for r in rows), label_height(len(rows), pt)

    def result(rows, pt, left, top, w, h, forced=False):
        gap = box_gap(line, (left, top, w, h))
        return {"left": left, "top": top, "w": w, "h": h, "rows": rows, "size": pt, "led": gap > 8,
                "forced": forced, "gap": gap}

    def score(box, gap):
        left, top, w, h = box
        covered = sum(_over(box, other) for other in soft_boxes)
        led_hits = 0
        if gap > 8:                      # its leader: from its line's middle to the label's nearest edge
            lead = ((mx, my), leader_end((mx, my), box))
            led_hits = sum(_seg_hits_shape(lead, shape_) for shape_ in hard_shapes) + \
                sum(_seg_hits_box(lead, b_) for b_ in lead_boxes)
        crossed = sum(crosses(s_, left, top, w, h) for s_ in field.soft)
        return covered, led_hits, crossed, gap, left, top

    def candidates(w, h, base_x, base_y, step, nx, ny, reach, enough=None):
        """The nearest spot of each HARD-keeping run, rows nearest the line first (then nearest its middle); with
        `enough`, stop once that many are found and no row left is nearer; else at the first row with a spot
        beside the line (unled) with nothing SOFT against it, or once no row left could beat the best."""
        rows_ = sorted((max(0.0, y0 - (base_y + j * step + h), base_y + j * step - y1),
                        abs(base_y + j * step + h / 2 - my), j) for j in range(ny))   # nearest, then mid-line
        found, best_ = [], None
        for ydist, _, j in rows_:
            if ydist > reach:
                break
            if best_ is not None and best_[:3] == (0, 0, 0) and ydist >= best_[3]:
                break                                    # nothing in the rows left can beat it
            if enough is not None and len(found) >= enough and ydist >= found[enough - 1][0]:
                break
            top = base_y + j * step
            for i0, i1, _ in field.pieces(top, w, h, base_x, step, nx):
                i = _nearest_index(line, top, w, h, base_x, step, i0, i1)
                order_ = [i] + [k for d in range(1, i1 - i0 + 1) for k in (i - d, i + d) if i0 <= k <= i1]
                for k in order_:                         # the nearest; a neighbour only if label_breaks_hard
                    box = (base_x + k * step, top, w, h)  # refuses it (never expected: the runs are exact)
                    gap = box_gap(line, box)
                    if gap <= reach and not label_breaks_hard(line, box, view, hard_boxes, hard_lines, hard_shapes,
                                                              placed):
                        break
                else:
                    continue
                if enough is not None:
                    found.append((gap, box))
                    found.sort(key=lambda q: (q[0], q[1][0], q[1][1]))
                    continue
                s_ = score(box, gap)
                if s_[1]:                                # a led label's leader across something: the rest of
                    for k in range(i0, i1 + 1):          # the run weighed too (the review of 9d021d8)
                        box_ = (base_x + k * step, top, w, h)
                        gap_ = box_gap(line, box_)
                        if gap_ <= reach and not label_breaks_hard(line, box_, view, hard_boxes, hard_lines,
                                                                   hard_shapes, placed):
                            s_ = min(s_, score(box_, gap_))
                if best_ is None or s_ < best_:
                    best_ = s_
            if best_ is not None and best_[:3] == (0, 0, 0) and best_[3] <= 8:
                break                                    # beside its line, nothing SOFT against it: taken
        return found if enough is not None else best_

    def near(rows, pt, reach):
        w, h = shape(rows, pt)
        nx = int((x1 - x0 + w + 2 * reach) / LABEL_STEP) + 1
        ny = int((y1 - y0 + h + 2 * reach) / LABEL_STEP) + 1
        got = candidates(w, h, x0 - w - reach, y0 - h - reach, LABEL_STEP, nx, ny, reach)
        return None if got is None else result(rows, pt, got[4], got[5], w, h)

    for pt in range(int(size), LABEL_MIN_SIZE - 1, -1):          # within one label height: its size, then smaller
        for rows in variants:
            got = near(rows, pt, shape(rows, pt)[1])
            if got is not None:
                return got
    for rows in variants:                                        # led, up to LABEL_LEAD_REACH heights away
        got = near(rows, size, LABEL_LEAD_REACH * shape(rows, size)[1])
        if got is not None:
            return got
    if view is not None:                                         # the nearest spots on screen that keep the rules
        for pt in (int(size), LABEL_MIN_SIZE):
            for rows in variants:
                w, h = shape(rows, pt)
                nx, ny = int((view[0] - w) // 12) + 1, int((view[1] - h) // 12) + 1
                clear = candidates(w, h, 0, 0, 12, nx, ny, float("inf"), enough=40)[:40]
                if clear:
                    s_ = min(score(box, gap) for gap, box in clear)
                    return result(rows, pt, s_[4], s_[5], w, h)
    rows = variants[-1]                                          # nowhere keeps them all: never over another
    w, h = shape(rows, LABEL_MIN_SIZE)                           # label still (the review of 3446e94), else
    if view is not None:                                         # beside its line; said either way, never dropped
        i_ = LABEL_INSET
        free = sorted((box_gap(line, (left, top, w, h)), left, top) for top in range(i_, int(view[1] - h - i_) + 1, 12)
                      for left in range(i_, int(view[0] - w - i_) + 1, 12)
                      if not any(_over((left, top, w, h), other)
                                 for other in list(placed) + [axis_icon_box(view)]))   # nor on the axis icon
        if free:
            return result(rows, LABEL_MIN_SIZE, free[0][1], free[0][2], w, h, forced=True)
    left, top = min(xa, xb), max(ya, yb) + 6
    if view is not None:
        i_ = LABEL_INSET
        left = min(max(left, i_), max(view[0] - w - i_, i_))
        top = min(max(top, i_), max(view[1] - h - i_, i_))
        if _over((left, top, w, h), axis_icon_box(view)):          # off the axis icon: above it (review of 7e6d824)
            top = max(i_, axis_icon_box(view)[1] - h)
    return result(rows, LABEL_MIN_SIZE, left, top, w, h, forced=True)


def hull(points):
    """The convex hull of screen points, counter-clockwise (a building's footprint on screen when its outline isn't
    given in order: never smaller than the footprint, and turned with it, never its whole bounding box)."""
    pts = sorted(set((round(x, 3), round(y, 3)) for x, y in points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


LABEL_ORDER = {"does_not_comply": 0, "needs_review": 1, "complies": 2}   # failing first, the edges' lengths last
LABEL_SETTLE_S = 0.08        # the view still this long: the labels are placed (never while it moves)


class LabelRun:
    """Placing a frame's plan labels a few at a time (place_dim_label), outside the drawing loop: failing yards
    first, then those needing review, those that comply, the edges' lengths last; each one placed is HARD for the
    ones after (never hidden under another, the Rhino job at 4bb6d4d). `step` places labels until its time budget
    is spent (one at least), so Rhino stays responsive between steps (the review of 3446e94: the whole search at
    once froze it each time the view came to rest). `items`: dicts with "key", "text", "line" (screen), "size" and
    "status" (None for an edge). `spots`: {key: placement}, each with the line it was placed for ("line") and its
    place in the order ("order")."""

    def __init__(self, items, view, keep=(), dims=(), shapes=(), lines=(), carried=None):
        self.view, self.keep, self.shapes, self.carried = view, list(keep), list(shapes), dict(carried or {})
        self.dims = [tuple(map(tuple, d)) for d in dims]
        self.lines = [tuple(map(tuple, s_)) for s_ in lines if tuple(map(tuple, s_)) not in self.dims]
        self.todo = [item for _, item in sorted(enumerate(items), key=lambda ki: (
            LABEL_ORDER.get(ki[1].get("status"), 3), ki[0]))]
        self.placed, self.spots, self.slowest = [], {}, 0.0

    def kept(self, item, own):
        """The label's place carried with the view while it moved, when it still keeps every HARD rule beside its
        line at its own size with nothing SOFT against it (no jump when the view comes to rest), else None."""
        was = self.carried.get(item["key"])
        if not was or was.get("forced") or was["size"] != item["size"]:
            return None
        box = (was["left"], was["top"], was["w"], was["h"])
        gap = box_gap(own, box)
        if gap > 8 or label_breaks_hard(own, box, self.view, self.keep, self.dims, self.shapes, self.placed):
            return None
        if any(crosses(s_, *box) for s_ in self.lines if s_ != own):
            return None
        return dict(was, led=False, gap=gap)

    def step(self, budget_s=None):
        """Place labels until the next would pass `budget_s` seconds (by the slowest so far; one at least; None:
        all). Whether every one is placed."""
        import time as time_
        start, done = time_.perf_counter(), 0
        while self.todo:
            if budget_s is not None and done and time_.perf_counter() - start + self.slowest > budget_s:
                break
            done += 1
            began = time_.perf_counter()
            item = self.todo.pop(0)
            own = tuple(map(tuple, item["line"]))
            got = self.kept(item, own) or place_dim_label(
                own, item["text"], item["size"], self.view, hard_boxes=self.keep, hard_lines=self.dims,
                soft_lines=self.lines, hard_shapes=self.shapes, placed=list(self.placed))
            got = dict(got, line=own, order=len(self.spots))
            self.placed.append((got["left"], got["top"], got["w"], got["h"]))
            self.spots[item["key"]] = got
            self.slowest = max(self.slowest, time_.perf_counter() - began)
        return not self.todo


def place_labels(items, view, keep=(), dims=(), shapes=(), lines=()):
    """Every plan label of a frame placed at once (LabelRun to the end): {key: placement}."""
    run = LabelRun(items, view, keep, dims, shapes, lines)
    run.step()
    return run.spots


def shown_while_moving(carried, view, keep=(), dims=(), shapes=()):
    """Which labels carried along with a moving view (logic.follow) may be drawn this frame: only those that keep
    every HARD rule where they are now (label_breaks_hard: on screen, off the buildings, the boxes, the dimensions
    and the labels shown before them), in the order they were placed; the rest are hidden until the view rests and
    they are placed again (the Rhino job at 5b46c99: old places on screen, then a jump). `carried`: [(item, got)]
    with item["line"] the line on screen now. Returns the same pairs, those shown."""
    out, taken = [], []
    dims = [tuple(map(tuple, d)) for d in dims]
    for item, got in sorted(carried, key=lambda ig: ig[1].get("order", 0)):
        box = (got["left"], got["top"], got["w"], got["h"])
        if label_breaks_hard(tuple(map(tuple, item["line"])), box, view, list(keep), dims, list(shapes), taken):
            continue
        out.append((item, got))
        taken.append(box)
    return out


def follow(got, line):
    """A placement carried along while the view moves (never searched in the drawing loop): the same offset from
    its line's middle as when it was placed, at the line's middle on screen now."""
    (xa, ya), (xb, yb) = got["line"]
    (xc, yc), (xd, yd) = line
    dx, dy = (xc + xd) / 2 - (xa + xb) / 2, (yc + yd) / 2 - (ya + yb) / 2
    return dict(got, left=got["left"] + dx, top=got["top"] + dy, line=tuple(map(tuple, line)))


def _seg_hits_box(seg, box):
    return crosses(seg, box[0], box[1], box[2], box[3])


def _seg_hits_shape(seg, poly):
    """Whether a segment touches a polygon (crosses an edge, or lies inside it)."""
    (ax, ay), (bx, by) = seg
    if len(poly) < 3:
        return False
    for (cx, cy), (dx, dy) in zip(poly, poly[1:] + poly[:1]):
        d = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx)
        if abs(d) < 1e-12:
            continue
        t = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / d
        u = ((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / d
        if 0 <= t <= 1 and 0 <= u <= 1:
            return True
    return _inside((ax + bx) / 2, (ay + by) / 2, poly)


LABEL_KEEP = (                     # spaces never broken in a plan label (#29 at e4e5018: "101'-1" / "1/2"")
    r"(\d+'-\d+) (\d+/\d+\")",            # a measurement: 101'-1 1/2", 7'-0 5/8" (as NOTICE_KEEP's first)
    r"^([✕?✓]) (\S)",                     # a status mark with its first word: never alone on a line
    r"\b(min|max|needs) (\d)",             # the word that says what the number is, with it
)


def label_lines(text):
    """A plan label as two lines, for when it won't fit beside its line on one: its name, then its numbers
    ("✕ Side yard, Southwest" / "7'-0 5/8", needs 10'-0" (approx.)"). One line when it has no name before a number
    (a lot edge's length), never broken inside a measurement nor after a status mark alone (LABEL_KEEP)."""
    import re
    kept = text
    for keep in LABEL_KEEP:
        kept = re.sub(keep, lambda m: "\u00a0".join(m.groups()), kept)
    words = kept.split(" ")

    def number(w):
        return w.lstrip("✕?✓\u00a0")[:1].isdigit() or w.split("\u00a0")[-1][:1].isdigit() and "\u00a0" in w
    k = next((i for i, w in enumerate(words) if i and number(w)), None)
    if k is None or any(number(w) for w in words[:k]):     # no name before the numbers: one line
        return [text]
    return [" ".join(words[:k]).replace("\u00a0", " "), " ".join(words[k:]).replace("\u00a0", " ")]


NOTICE_SHARES = (0.4, 0.5, 0.6, 0.7, 0.8)   # the notice's boxes, narrowest first: a share of the view's width each
NOTICE_MAX_SHARE = NOTICE_SHARES[-1]         # never wider (a two-line band above the model, never a bar over it)
NOTICE_MIN_CHARS = 24                        # ...never narrower than this many characters a line


NOTICE_KEEP = (                    # spaces never broken in the notice (each becomes a non-breaking one)
    r"(\d+'-\d+) (\d+/\d+\")",            # a measurement: 7'-0 5/8"
    r"(\d[\d,.]*) (sf|%|ft)\b",             # an area, a share, a length: 7,033 sf, 35 %
    r"([\d\"'%]) (short|over|proposed|required)\b",   # the word that says what the number is
    r"^(✕) (\S)",                           # the mark with its first word
)


def notice_lines(lines, view_w, share=NOTICE_MAX_SHARE, size=13):
    """The notice's lines wrapped to at most `share` of the view's width (gordium_ui text_box_size's measure: size *
    0.6 pixels a character, 22 of margin), never under NOTICE_MIN_CHARS a line. Broken between its " · " parts first;
    a part is broken between its words only when it is too long even for NOTICE_MAX_SHARE (a heading kept whole where
    a wider box allows it: review of 87e105d), and never at a space in NOTICE_KEEP (7'-0 5/8" stays whole: review
    round 1); each notice line's rest indented under its first. Zoomed in tight, one long line was a bar across the
    whole plan, over the drawing being judged (architect's eye, #28 at 92cf742)."""
    import re
    import textwrap
    chars = max(NOTICE_MIN_CHARS, int((view_w * share - 22) / (size * 0.6)))
    widest = max(NOTICE_MIN_CHARS, int((view_w * NOTICE_MAX_SHARE - 22) / (size * 0.6)))
    out = []
    for line in lines:
        start, row = len(out), ""
        for part in line.split(" · "):
            for keep in NOTICE_KEEP:
                part = re.sub(keep, lambda m: "\u00a0".join(m.groups()), part)
            if row and len(row) + 3 + len(part) <= chars:
                row += " · " + part
                continue
            if row:
                out.append(row)
            indent = "  " if len(out) > start else ""
            if len(indent) + len(part) <= widest:          # whole, even past this share: the limit allows it
                pieces = [part]
            else:
                pieces = textwrap.wrap(part, chars - 2, break_long_words=False, break_on_hyphens=False) or [part]
            for k, piece in enumerate(pieces[:-1]):
                out.append((indent if k == 0 else "  ") + piece)
            row = (indent if len(pieces) == 1 else "  ") + pieces[-1]
        out.append(row)
    return [t.replace("\u00a0", " ") for t in out]


def notice_box(lines, size=13):
    """The (width, height) the notice's box takes on screen: gordium_ui.text_box_size's measure."""
    return max(len(t) for t in lines) * (size * 0.6) + 22, len(lines) * (size + 9) + 10


def notice_place(view_w, view_h, lines, model, taken=(), size=13):
    """The notice as drawn in a view: (lines, (left, top), width, height), or None. Its most compact box first (lines
    of at most 40 % of the view's width), then wider ones up to NOTICE_MAX_SHARE, never a box wider than that (fewer, longer lines: a band that fits above or
    below the model where a tall box can't), each in the first corner clear of the model and of every box in `taken`
    (notice_spot); None when no box fits a clear corner: then it is not drawn over the model, and the panel's
    message line says it (review round 1: one narrow box alone hid the side yard's notice in the default framed
    view; the Rhino job at a9a9a45: in the real docked Top view, 657 x 668 px, three lines at most 60 % wide were
    4 px too tall for the band above the model, so it wasn't drawn: two lines at 80 % fit)."""
    for share in NOTICE_SHARES:
        wrapped = notice_lines(lines, view_w, share, size)
        w, h = notice_box(wrapped, size)
        if w > view_w * NOTICE_MAX_SHARE:    # a part that won't break narrower: never wider than the limit (review)
            continue
        spot = notice_spot(view_w, view_h, w, h, model, taken)
        if spot is not None:
            return wrapped, spot, w, h
    return None


def notice_spot(view_w, view_h, w, h, model, taken=(), gap=12):
    """Where a w × h notice goes in a view (screen pixels): (left, top), or None. The corners are tried in turn (top
    left under the view's name, bottom left above the axes, top right, bottom right); the first that covers none of
    the model (`model`: its on-screen box, x0, y0, x1, y1, or None) and no box in `taken` (the status box) is used;
    None when there is none: the notice is never drawn over the building or lot being judged, nor over the status box
    (architect's review, 2026-10-21: bottom left, it hid the lot's lower edge and dimensions; #28 at 92cf742: zoomed
    in tight, a bar across the plan)."""
    spots = [(gap, 34), (gap, view_h - h - 64), (view_w - w - gap, 34), (view_w - w - gap, view_h - h - 40)]

    def overlap(x, y, box):
        a, b, c, e = box
        return max(0.0, min(x + w, c) - max(x, a)) * max(0.0, min(y + h, e) - max(y, b))
    clear = [(x, y) for x, y in spots if 0 <= x and x + w <= view_w and 0 <= y and y + h <= view_h   # on screen
             and not any(overlap(x, y, (a, b, a + c, b + e)) for a, b, c, e in taken)
             and not (model and overlap(x, y, model))]
    return clear[0] if clear else None


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


NO_STREET_YET = "the street is set when the lot is drawn"
# a new, empty file (Ben, 2026-10-27): no sample prefilled; the site comes from a lookup, or by hand
FILL_BY_LOOKUP = "Look up an address to fill these in"
LOOK_UP_FIRST_SITE = "Look up the address first. It finds the lot, zoning district and neighbourhood."
BY_HAND = "Enter the site by hand"
BY_HAND_NOTE = ("Entered by hand: draw the lot, pick the district and the street side. No neighbourhood is drawn "
                "(only a lookup finds one).")
NO_LOT = "no lot yet: draw it on the Site layer, or look up the address"
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
    own = _real_names(_street_lines().matching_ids(lines, ids))   # (Gordium's own "Street N": no name, asked: F2)
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


def pick_street(old_lines, old_ids, picked, name, tolerance=0.5, outline=None, ask=None, said=None):
    """(street lines, their street names) after the architect clicks a lot line as the street side (`picked`) and
    names its street (`name`, found or typed; None: unnamed). THE one order of steps (arch-fixes-2 review rounds
    9-11, where a name given for one line kept landing on other lines and two streets, or "one street or two?",
    became one): the name goes on the clicked line ONLY; every other line keeps the street it was known to be on,
    or none; then the street lines follow from those names (street_lines_after_pick: the clicked line's own street
    when the lines are known to be two streets, else every line). A line nobody named stays unnamed, so the
    measuring still reads it from the drawing (a corner: one street or two?, needs review). A line not among them:
    the whole street it is on along the lot `outline` (street_pick: never round a corner; an unclear end asked with
    `ask`), else that line alone. `said` (a list): gets {"words", "refused"}, what the command line says and
    whether the click was refused (a point clicked: the street lines and their name stay as they were)."""
    if said is None:
        said = []

    def near(p, q):
        return abs(p[0] - q[0]) <= tolerance and abs(p[1] - q[1]) <= tolerance

    a, b = picked
    lines = [list(map(list, line)) for line in old_lines or []]
    at = _piece_at(outline, picked, tolerance) if outline else None
    if at is not None:
        # on the lot outline: every street line is one of its pieces. The saved lines are snapped to the pieces
        # they are (a lot nudged under 0.5 ft: the piece, never the stale line beside it; round 10), each with
        # the street it was known to be on; the clicked piece takes the name given, and no other. The saved
        # pieces around the click, of its own street or none, are kept as they are (never asked again, never
        # shrunk on a guess: round 10), and the street grows on from them.
        n = len(outline)
        own_ids = _real_names(_street_lines().matching_ids(lines, old_ids))   # (Gordium's own ids: no name)
        names, saved = [None] * n, set()
        for k, line in enumerate(lines):
            q = _piece_at(outline, line, tolerance)
            if q is not None:
                saved.add(q)
                names[q] = names[q] or (own_ids[k] if own_ids is not None else None)
        mine = name or names[at]
        if name:
            names[at] = name                               # the name on the clicked line only
        label = mine or "Street 1"                         # (the id its unnamed lines get: one street)
        refused = refused_click(outline, picked, tolerance)
        if refused:                                        # a point clicked, not a line: nothing changes
            said.append({"words": refused, "refused": True})
            return lines, (list(old_ids) if own_ids is not None else None)

        def with_me(q):
            return names[q] is None or (mine is not None and _street_lines().same_street(names[q], mine))

        seed = [at]
        if at in saved:
            while (seed[0] - 1) % n in saved and (seed[0] - 1) % n not in seed and with_me((seed[0] - 1) % n):
                seed.insert(0, (seed[0] - 1) % n)
            while (seed[-1] + 1) % n in saved and (seed[-1] + 1) % n not in seed and with_me((seed[-1] + 1) % n):
                seed.append((seed[-1] + 1) % n)
        got = street_pick(outline, picked, names, (), ask, label, tolerance, seed=seed)
        if got is None:                 # an outline that doesn't run end to end: the saved street, else that line
            hits = [k for k, line in enumerate(lines)
                    if (near(a, line[0]) and near(b, line[-1])) or (near(a, line[-1]) and near(b, line[0]))]
            if hits:                    # never fewer on a guess (round 11): the saved street as it was
                ids = list(own_ids or [None] * len(lines))
                if name:
                    ids[hits[0]] = name
                kept = street_lines_after_pick(lines, picked, tolerance, ids=ids)
                out = [ids[next(k for k, line in enumerate(lines) if line == q)] for q in kept]
                if street_verdict(*_end_to_end(kept, out))[0] == "one":     # (one id only for one street)
                    fill = next((i for i in out if i), None) or label           # (its known name first: D2)
                    out = [i or fill for i in out]
                why = "the lot outline doesn't run end to end in order here, so Gordium can't follow the street along it"
                said.append({"words": (f"{label}: the street lines kept as they were ({why})" if kept == lines else
                                       f"{street_words(label, kept, out)} ({why})"), "refused": False})   # (round 12)
                return kept, out
            said.append({"words": f"{label}: only the lot line clicked (the lot outline doesn't run end to end in "
                                  f"order here, so Gordium can't follow the street along it)", "refused": False})
            return [list(map(list, picked))], [label]
        said.append({"words": got[1], "refused": False})
        return street_lines_of(outline, [got[0]], names, labels=[label])
    # no outline (or a line not on it): the street lines themselves
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


# A joint between two lot-line pieces that turns no more than this is the same street's wobble: a tax-map outline
# draws a straight street in short pieces (106 Ithaca Rd: 8 pieces of about 10 ft, joints turning up to 7.5°). A
# joint turning more than street_lines.TURN_LIMIT_DEG is a corner (the measuring's own limit for one street or
# two); in between, or a run of small joints that swings past that limit in all, is unclear, and the architect is
# asked (demo 00c04f1: one click on one of the 8 pieces kept that 9.8 ft piece as the whole street).
PIECE_TURN_DEG = 15.0
SHORT_PIECE_FT = 0.5   # a piece shorter than this (6 in) has no direction of its own (is_tiny)
JOINT = 0.01      # ft: two pieces of one outline meet where they share an end (a click is matched within `tolerance`:
                  # 106's 0.24 ft piece has both ends within 0.5 ft of its neighbours' ends)


def is_tiny(line):
    """A lot-line piece shorter than SHORT_PIECE_FT (6 in): a corner point drawn twice, a slip of the
    pen or float noise, with no direction of its own: never a street of its own (it would be 0'-0" of frontage,
    the front yard read from a point), never a corner or a bend (street-run review rounds 3 to 5); passed through
    inside a street."""
    import math
    return math.dist(line[0][:2], line[-1][:2]) < SHORT_PIECE_FT


def _same_piece(line, picked, tolerance):
    (a, b), (c, d) = (line[0], line[-1]), (picked[0], picked[-1])
    near = lambda p, q: abs(p[0] - q[0]) <= tolerance and abs(p[1] - q[1]) <= tolerance   # noqa: E731
    return (near(a, c) and near(b, d)) or (near(a, d) and near(b, c))


def _in_ring_order(outline):
    """Whether the outline's pieces run end to end in order round the lot (as the measuring needs)."""
    near = lambda p, q: abs(p[0] - q[0]) <= JOINT and abs(p[1] - q[1]) <= JOINT   # noqa: E731
    lines = [[list(x[0][:2]), list(x[-1][:2])] for x in outline or []]
    if len(lines) < 3:
        return False
    a, b = lines[0]
    if not (near(b, lines[1][0]) or near(b, lines[1][1])):
        a, b = b, a
    first, end = a, b
    for x, y in lines[1:]:
        if near(y, end) and not near(x, end):
            x, y = y, x
        elif not near(x, end):
            return False
        end = y
    return near(end, first)


def _piece_at(outline, picked, tolerance):
    """The outline piece a click names: the one it is exactly (within JOINT), else the first within `tolerance`
    (a short piece beside another short one is never mistaken for it)."""
    for tol in (JOINT, tolerance):
        k = next((k for k, line in enumerate(outline or []) if _same_piece(line, picked, tol)), None)
        if k is not None:
            return k
    return None


def generated_id(name):
    """Whether a street id is Gordium's own ("Street 1", "Street 2"... given to a run nobody named), not a name:
    never read back as a street's identity (a new pick numbers its streets afresh: round ids, F4)."""
    return _street_lines().generated_id(name)            # (street_lines: the measuring's own comparison)


def _real_names(ids):
    return [None if generated_id(i) else i for i in ids] if isinstance(ids, list) else ids


def outline_names(outline, lines, ids, tolerance=0.5):
    """The street each piece of the lot outline is known to be on (one per piece, None where unknown): a piece that
    is one of the street lines `lines` takes that line's own name (`ids`, only when they match the lines one for one:
    street_lines.matching_ids); every other piece None."""
    own = _real_names(_street_lines().matching_ids(lines or [], ids))      # (Gordium's own ids: no name)
    out = []
    for piece in outline or []:
        k = next((k for k, line in enumerate(lines or []) if _same_piece(line, piece, tolerance)), None)
        out.append(own[k] if own is not None and k is not None else None)
    return out


def street_run(outline, picked, names=None, taken=(), tolerance=0.5, seed=None):
    """Where the street of the lot line the architect clicked (`picked`, [[x, y], [x, y]] in feet) runs along the lot
    outline (`outline`: its pieces in order round the lot, each [[x, y], [x, y]], as Rhino gives a closed curve's
    segments and as the measuring requires): the clicked piece and its neighbours, both ways round, for as long as
    they are surely on the same street.

    The outline is read as strokes: each long piece (SHORT_PIECE_FT or longer) is one; consecutive short pieces
    are grouped into strokes whose ends are at least SHORT_PIECE_FT apart (an arc drawn as short chords keeps its
    shape); short pieces left over between two strokes (a corner point drawn twice, a slip, a spike) have no
    direction and stand in the gap between them. Going on from the last stroke kept to the next one:
    - the next one is another click's street (`taken`): a sure stop (the gap before it is asked);
    - both are named (`names`, one per piece, None where unknown): the same street joins, however it bends;
      another street is a sure stop for it (the gap before it is asked);
    - else a joint between two long pieces with nothing between them turning more than TURN_LIMIT_DEG is a sure
      stop (a corner: never round onto the other street). Nothing else is ever a sure stop: no short piece
      decides one (street-run review round 7);
    - it joins when the joint turns PIECE_TURN_DEG or less, the run then swings no more than TURN_LIMIT_DEG in all
      and the gap is under SHORT_PIECE_FT;
    - anything else is unclear: the gap and the next stroke (and on over strokes in line with no gap, while that
      stretch swings no more than TURN_LIMIT_DEG) are returned apart, never added on a guess, so the architect
      is asked.
    `seed`: a run already kept (its pieces in order round the lot), grown on from its ends.

    {"pieces": the run's piece numbers in order round the lot, "maybe": [before, after] (the unclear pieces past
    each end, nearest first; [] where the end is sure), "turn": [the swing of each unclear stretch from the run's
    end, in degrees, or None when it is short pieces only]}; None when `picked` isn't a piece of the outline, is
    already taken, is a short piece standing alone (a point, not a line), or the outline doesn't run end to end
    in order (the measuring refuses such a lot)."""
    import math
    sl = _street_lines()
    pieces = [[list(line[0][:2]), list(line[-1][:2])] for line in outline or [] if len(line) >= 2]
    n = len(pieces)
    hit = _piece_at(pieces, picked, tolerance)
    taken = set(taken)
    if hit is None or hit in taken or n < 3:
        return None
    near = lambda p, q: abs(p[0] - q[0]) <= JOINT and abs(p[1] - q[1]) <= JOINT   # noqa: E731
    # each piece turned to run round the lot (its end the next one's start): the order Rhino and the measuring use
    start, vec = [None] * n, [None] * n
    a, b = pieces[0]
    if not (near(b, pieces[1][0]) or near(b, pieces[1][1])):
        a, b = b, a
    end = b
    start[0], vec[0] = a, (b[0] - a[0], b[1] - a[1])
    for i in range(1, n):
        a, b = pieces[i]
        if near(b, end) and not near(a, end):
            a, b = b, a
        elif not near(a, end):
            return None                                    # not end to end in order: nothing extended
        start[i], vec[i], end = a, (b[0] - a[0], b[1] - a[1]), b
    if not near(end, start[0]):
        return None
    length = [math.hypot(*v) for v in vec]
    tiny = [x < SHORT_PIECE_FT for x in length]
    names = list(names) if isinstance(names, list) and len(names) == n else [None] * n

    # the strokes, in order round the lot from a long piece; each {"pieces", "dir", "long"}; gap[m]: the short
    # pieces between stroke m and stroke m + 1
    first = next((i for i in range(n) if not tiny[i]), 0)
    strokes, gap, group = [], [], []

    def close_group(final):
        nonlocal group
        while group:
            g0 = start[group[0]]
            cut = None
            for c in range(len(group)):
                e = group[c]
                tip = (start[e][0] + vec[e][0], start[e][1] + vec[e][1])
                if math.hypot(tip[0] - g0[0], tip[1] - g0[1]) >= SHORT_PIECE_FT:
                    cut = c
                    break
            if cut is None:
                if final:
                    gap[-1] += group if strokes else []
                    if not strokes:
                        strokes.append({"pieces": list(group), "dir": None, "long": False})
                        gap.append([])
                group = []
                return
            part, group = group[:cut + 1], group[cut + 1:]
            e = part[-1]
            tip = (start[e][0] + vec[e][0], start[e][1] + vec[e][1])
            strokes.append({"pieces": part, "dir": (tip[0] - g0[0], tip[1] - g0[1]), "long": False})
            gap.append([])

    for step_ in range(n):
        i = (first + step_) % n
        if tiny[i]:
            group.append(i)
            continue
        close_group(True)
        strokes.append({"pieces": [i], "dir": vec[i], "long": True})
        gap.append([])
    close_group(True)
    m_of = {}
    for m, s_ in enumerate(strokes):
        for q in s_["pieces"]:
            m_of[q] = m
    if hit not in m_of:                                    # a short piece standing alone: a point, not a line
        return None
    S = len(strokes)

    def name_of(m):
        got = {names[q] for q in strokes[m]["pieces"]}
        return got.pop() if len(got) == 1 else None

    def turn(u, v):                                        # signed, degrees, from direction u to direction v
        return math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1]))

    def swing(ms):                                         # the spread of the running heading over strokes
        dirs = [strokes[m]["dir"] for m in ms if strokes[m]["dir"] is not None]
        run_, low, high = 0.0, 0.0, 0.0
        for u, v in zip(dirs, dirs[1:]):
            run_ += turn(u, v)
            low, high = min(low, run_), max(high, run_)
        return high - low

    def between(m, d):                                     # the gap from stroke m to its neighbour going d
        return list(gap[m]) if d > 0 else list(reversed(gap[(m - 1) % S]))

    def pieces_of(ms):
        return [q for m in ms for q in strokes[m]["pieces"]]

    hm = m_of[hit]
    own = name_of(hm) or names[hit]
    run = [hm]
    if seed and hit in seed and not set(seed) & taken:     # the strokes the seed holds, grown out from the hit's
        held = {m_of[q] for q in seed if q in m_of}
        while (run[0] - 1) % S in held and (run[0] - 1) % S not in run:
            run.insert(0, (run[0] - 1) % S)
        while (run[-1] + 1) % S in held and (run[-1] + 1) % S not in run:
            run.append((run[-1] + 1) % S)
    held_gaps = set(seed or ()) - set(pieces_of(run))       # gap pieces a Yes already kept past the ends
    maybe, swings = [[], []], [None, None]
    for side, d in ((0, -1), (1, 1)):
        while True:
            last = run[0] if side == 0 else run[-1]
            g = [q for q in between(last, d) if q not in held_gaps]
            j = (last + d) % S
            if j in run:                                   # the lot comes round
                maybe[side] = g
                break
            jp = strokes[j]["pieces"]
            if set(jp) & taken or set(g) & taken:          # another click's street: sure; the gap is asked
                maybe[side] = [q for q in g if q not in taken] if not set(g) & taken else []
                break
            nj = name_of(j)
            order = [j] + run if side == 0 else run + [j]
            if own and nj:                                 # both named: the street's identity decides
                if sl.same_street(own, nj) and not g:
                    run[:] = order
                    continue
                if not sl.same_street(own, nj):
                    maybe[side] = g                        # another street: sure for it, the gap asked
                    break
            u, v = strokes[last]["dir"], strokes[j]["dir"]
            t = abs(turn(u, v)) if u is not None and v is not None else 180.0
            if not g and strokes[last]["long"] and strokes[j]["long"] and t > sl.TURN_LIMIT_DEG:
                break                                      # a corner, long piece to long piece
            g_len = sum(length[q] for q in g)
            # (onto a long piece only from a long one, or with one in the run already: a click on a rounded
            # corner's chord never takes the side line unasked, round 8)
            sure_dir = strokes[j]["long"] is False or strokes[last]["long"] or any(strokes[m]["long"] for m in run)
            if t <= PIECE_TURN_DEG and swing(order) <= sl.TURN_LIMIT_DEG and g_len < SHORT_PIECE_FT and sure_dir:
                run[:] = order
                if g:                                       # (the gap joins with it)
                    held_gaps.update(g)
                continue
            more_m, k = [j], j
            while True:                                    # on over strokes in line with no gap
                g2 = between(k, d)
                nxt = (k + d) % S
                if (g2 or nxt in run or nxt in more_m or set(strokes[nxt]["pieces"]) & taken
                        or t > PIECE_TURN_DEG or strokes[k]["dir"] is None or strokes[nxt]["dir"] is None
                        or abs(turn(strokes[k]["dir"], strokes[nxt]["dir"])) > PIECE_TURN_DEG
                        or (name_of(nxt) and not (own and sl.same_street(own, name_of(nxt))))
                        or swing([last] + more_m + [nxt]) > sl.TURN_LIMIT_DEG):
                    break
                more_m.append(nxt)
                k = nxt
            stretch = g + [q for m in more_m for q in (strokes[m]["pieces"] if d > 0 else
                                                       list(reversed(strokes[m]["pieces"])))]
            maybe[side] = stretch
            swings[side] = swing([last] + more_m)
            break
    flat = []
    for idx, m in enumerate(run):
        flat += strokes[m]["pieces"]
        if idx < len(run) - 1:
            flat += gap[m]
    before = [q for q in reversed(gap[(run[0] - 1) % S]) if q in held_gaps][::-1] if S > 1 else []
    after = [q for q in gap[run[-1]] if q in held_gaps] if S > 1 else []
    pieces_out = before + flat + after
    seen = set()
    pieces_out = [q for q in pieces_out if not (q in seen or seen.add(q))]
    return {"pieces": pieces_out, "maybe": maybe, "turn": swings}


def feet_words(feet):
    """A length for the command line, rounded DOWN to the nearest 1/8 in (never in the architect's favour):
    75.83 -> 75'-9 7/8"."""
    import math
    eighths = int(math.floor(feet * 96 + 1e-6))
    ft, rest = divmod(eighths, 96)
    inch, frac = divmod(rest, 8)
    if frac:
        g = math.gcd(frac, 8)
        return f"{ft}'-{inch} {frac // g}/{8 // g}\""
    return f"{ft}'-{inch}\""


def _length(lines):
    import math
    return sum(math.dist(line[0][:2], line[-1][:2]) for line in lines)


def _end_to_end(lines, ids=None):
    """(lines, ids) in order end to end along the street, as the measuring reads them (measure.Lot puts the street
    lines in outline order before its street_verdict): a click on a street line appends the rest of its street
    after the old lines (street-run review round 2). Lines that don't run end to end: as they were."""
    near = lambda p, q: abs(p[0] - q[0]) <= JOINT and abs(p[1] - q[1]) <= JOINT   # noqa: E731
    n = len(lines)
    ids = list(ids) if isinstance(ids, list) and len(ids) == n else None
    ends = [(line[0], line[-1]) for line in lines]

    def touches(k, p):
        return [j for j in range(n) if j != k and (near(ends[j][0], p) or near(ends[j][1], p))]

    starts = [k for k in range(n) if not touches(k, ends[k][0]) or not touches(k, ends[k][1])]
    if not starts:
        return lines, ids
    order, k = [starts[0]], starts[0]
    at = ends[k][1] if not touches(k, ends[k][0]) else ends[k][0]
    while len(order) < n:
        nxt = [j for j in touches(k, at) if j not in order]
        if len(nxt) != 1:
            return lines, ids
        k = nxt[0]
        at = ends[k][1] if near(ends[k][0], at) else ends[k][0]
        order.append(k)
    return [lines[k] for k in order], ([ids[k] for k in order] if ids is not None else None)


def street_words(label, lines, ids=False):
    """What the command line says a click kept: "Ithaca Rd: 8 lot-line pieces, 75'-10" of frontage". With `ids`
    given (the lines' street names, or None: unnamed), lines that aren't surely one street (street_verdict) say so
    instead of one frontage: the measuring asks one street or two."""
    n = len(lines)
    pieces = f"{label}: {n} lot-line piece{'s' if n != 1 else ''}"
    if ids is not False and n > 1 and street_verdict(*_end_to_end(lines, ids))[0] != "one":
        return pieces + ", not surely one street: Gordium asks one street or two before measuring along them"
    return pieces + f", {feet_words(_length(lines))} of frontage"


STREET_ANSWER_NEEDED = ("Gordium needs a Yes or a No here (Esc: nothing changes): kept as street, a "
                        "line that isn't can pass lot width; left out, a line that is can pass the front yard. ")


ESC_STREET = "Esc: nothing changed — the street side is as it was; this pick wasn't kept"


def so_far(words):
    """A corner lot's street click, said while the picking goes on: kept only when Enter ends it, so "so far"
    ("Ithaca Rd: 8 lot-line pieces, 75'-10" so far — Enter when done"), never read as kept before an Esc."""
    if words.endswith(" of frontage"):
        return words[:-len(" of frontage")] + " so far — Enter when done"
    return words + " (so far — Enter when done)"


def street_more_question(label, outline, more, swing):
    """The question when it isn't clear where a street ends (street_run's "maybe" pieces past one end)."""
    lines = [outline[k] for k in more]
    n = len(lines)
    count = f"{n} more lot-line piece{'s' if n != 1 else ''}, {feet_words(_length(lines))}"
    tail = f" Is that on {label} too? (Yes or No)"
    if swing is None:                                  # short pieces only (no direction to give)
        return f"Past there is a short piece of lot line ({count}), with no direction of its own.{tail}"
    if swing > _street_lines().TURN_LIMIT_DEG:         # a corner, but with short pieces in it, or a bend
        return f"Past there the lot line turns {round(swing)}° over short pieces, a corner or a bend ({count}).{tail}"
    return f"Past there the lot line bends {round(swing)}° with no clear corner ({count}).{tail}"


def refused_click(outline, picked, tolerance=0.5):
    """What the command line says when a click can't start a street (a short piece standing alone: a point, not a
    line), or None: asked before anything else (the street's name), so nothing is asked of a refused click
    (street-run review round 9)."""
    hit = _piece_at(outline, picked, tolerance)
    if hit is not None and is_tiny(outline[hit]) and _in_ring_order(outline) \
            and street_run(outline, outline[hit], None, (), 0.0) is None:
        return "that piece is under 6 in long (a corner point drawn twice?), not a street line: click the lot line beside it"
    return None


def street_pick(outline, picked, names=None, taken=(), ask=None, label="This street", tolerance=0.5, seed=None):
    """One click on the street side, the whole street it is on: (piece numbers in order along it, what to say);
    street_run's run, with each unclear stretch past an end asked (`ask`: question -> True Yes, False No, None not
    answered) and left out only on a No. The plugin's question takes only Yes or No (round 14: neither default is
    safe, see gordium_rhino._ask_street_more); None (no one to ask: tests, headless runs) keeps it and says so.
    ([], words) when the click is on a street already kept (`taken`) or on a short piece standing alone (a point,
    not a line); None when it isn't a piece of the outline, or the outline doesn't run end to end in order."""
    found = street_run(outline, picked, names, taken, tolerance, seed=seed)
    if found is None:
        hit = _piece_at(outline, picked, tolerance)
        if hit is not None and hit in set(taken):
            return [], "that lot line is on a street already kept"
        if hit is not None and refused_click(outline, outline[hit], 0.0):
            return [], refused_click(outline, outline[hit], 0.0)
        return None
    run, closed, skipped = list(found["pieces"]), set(), False
    while True:            # each unclear stretch asked in turn; a Yes grows the street on from there, a No ends it
        grew = False
        for side in (0, 1):
            more = found["maybe"][side]
            if not more or side in closed:
                continue
            said = ask(street_more_question(label, outline, more, found["turn"][side])) if ask is not None else None
            if said is False:                              # the architect's No: the street ends there
                closed.add(side)
            else:
                run, grew = (list(reversed(more)) + run if side == 0 else run + more), True
                skipped = skipped or said is not True
        if not grew:
            break
        found = street_run(outline, picked, names, taken, tolerance, seed=run)
        run = list(found["pieces"])
    # what it says checks the street as the measuring will (a Yes past a bend: not surely one street)
    known = list(names) if isinstance(names, list) and len(names) == len(outline) else [None] * len(outline)
    words = street_words(label, [outline[k] for k in run], [known[k] for k in run])
    return run, words + ("; a bend not answered is kept as street (answer No to leave it out)" if skipped else "")


def add_street_pick(runs, outline, picked, names=None, ask=None, tolerance=0.5):
    """A corner lot's street side, one click at a time: (`runs` with the clicked street's run added, what to say).
    Each click keeps the whole street it is on (street_pick), never one already kept; the street is called by its
    known name, else "Street 1", "Street 2"... in click order."""
    hit = _piece_at(outline, picked, tolerance)
    own = names[hit] if hit is not None and isinstance(names, list) and len(names) == len(outline) else None
    label = own or f"Street {len(runs) + 1}"
    got = street_pick(outline, picked, names, {k for run in runs for k in run}, ask, label, tolerance)
    if got is None:
        if hit is None:
            return runs, "that isn't one of the lot's lines"
        return runs + [[hit]], (f"{label}: only the lot line clicked (the lot outline doesn't run end to end in "
                                f"order here, so Gordium can't follow the street along it: click each street line)")
    run, words = got
    return (runs + [run] if run else runs), words


def street_lines_of(outline, runs, names=None, clicks=None, labels=None):
    """(street lines, their street ids, one per line) from the runs kept (piece numbers), in click order, each piece
    once (the measuring reads a corner lot's streets from the ids, never from the drawing: #18): a piece's own name
    where it is known (`names`; Gordium's own "Street N" ids are no name), else its run's: the run's known name,
    else `labels[i]`, else "Street 1", "Street 2"... by the run's place in the click order (as the command line
    calls it), but only where the run is surely one street (street_verdict): else its unnamed lines stay unnamed,
    and the measuring asks, never one frontage along two streets. No run (no click was a piece of the outline): the lines
    clicked, each its own street; every click refused: nothing ([], None)."""
    if not any(runs) and clicks:
        if all(_piece_at(outline, c, JOINT) is None for c in clicks):   # none is a piece of the outline
            lines = street_lines_after_picks(None, clicks, True)
            return lines, [f"Street {i + 1}" for i in range(len(lines))]
        return [], None          # every click refused (a point, a street already kept): nothing changes (round 8)
    names = list(names) if isinstance(names, list) and len(names) == len(outline or []) else [None] * len(outline or [])
    seen, lines, ids = set(), [], []
    for i, run in enumerate(runs):
        mine = [k for k in run if k not in seen]
        # a run gets one id only where it is surely one street (street_verdict over its lines and known names,
        # the measuring's own test): else its unnamed lines stay unnamed and the measuring asks (round ids: a
        # Yes round a rounded corner, a name across a corner, never one id for two streets)
        sure = street_verdict(*_end_to_end([outline[k] for k in mine], [names[k] for k in mine]))[0] == "one" \
            if mine else False
        known = next((names[k] for k in mine if names[k]), None)
        base = known or (labels[i] if labels and i < len(labels) and labels[i] else f"Street {i + 1}")
        for k in mine:
            seen.add(k)
            lines.append([list(outline[k][0][:2]), list(outline[k][-1][:2])])
            ids.append(names[k] or (base if sure else None))
    return lines, (ids if lines else None)


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

    after = AFTER_DRAW if state.get("after_draw") else ""     # the looked-up lot, not drawn yet (show_pending_lot)
    lot_actions = [("lot", "Use my survey…", not state.get("lot_surveyed"))] if has_lot and not after else []
    if (look.get("guide") or state.get("lot_missing")) and not state.get("needs_lookup"):
        lot_actions.insert(0, ("draw_lot", "Draw my lot…", True))
    if state.get("needs_lookup"):                 # an empty file: the lookup fills the rows, or the site by hand
        lot_actions = [("by_hand", BY_HAND + "…", True)]
    rows = [
        {"key": "address", "label": "Address", "text": state.get("address") or "",
         # while it runs, the button stops it (the box as it was before Look up: lookup_cancelled)
         "actions": [("lookup_cancel", CANCEL_LOOKUP, True) if look.get("looking") else ("lookup", "Look up", True)]
         + ([("use_saved", USE_SAVED.format(date=look["saved_offer"]), True)]
            if look.get("saved_offer") and not look.get("looking")
            and same_site_address(state.get("address") or "", look.get("saved_for") or "") else []),
         # (an address retyped since the offer: no button, as pressing it would do nothing: round 6)
         "tick": None, "matches": look.get("matches") or [],
         "status": lookup_status(look["looking"], None, 0.0) if look.get("looking") else None},
        {"key": "zone", "label": "Zoning district", "text": zone_row_text(state),
         "actions": [("zone", "Change", True)], "tick": (ZONE_TICK, bool(state.get("district_confirmed")))},
        {"key": "use", "label": "Use", "text": state.get("use_name") or state.get("use") or "—",
         "actions": [("use", "Change", True)], "tick": None},
        {"key": "lot", "label": "Lot",
         "text": (FILL_BY_LOOKUP if state.get("needs_lookup") else LOT_MISSING if state.get("lot_missing") else
                  lot_text(state.get("lot_area"), state.get("lot_surveyed"), state.get("lot_source")) + after
                  if has_lot else NO_LOT),
         "actions": lot_actions, "tick": None,
         "help": (BY_HAND_NOTE + (" " + IN_CITY_SAID.format(date=state["city_by_hand"])
                                  if state.get("city_by_hand") else "")) if state.get("by_hand") else None},
        {"key": "street", "label": STREET_LABEL, "help": STREET_HELP,
         "text": FILL_BY_LOOKUP if state.get("needs_lookup") else
         ((street_name(state) if state.get("street_name") or not after else NO_STREET_YET) + after)
         if (state.get("street_name") or has_lot)
         else "set from the lot, once there is one",
         "actions": [("street", "Change…", True)] if has_lot and not after else [], "tick": None,   # nothing to change yet: hidden
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


NO_DISTRICT = "The City zoning map gave no district for this lot: pick one."
SAVED_NO_DISTRICT = "A saved lookup never keeps the district (the City's map is used live only): pick it."
OVERLAYS_NOT_KEPT = "Overlays may apply here (a saved lookup can't keep them): check them by hand."


def city_day(now=None):
    """The place's own day (its time zone: PLACE, e.g. Ithaca's America/New_York) at `now` (UTC; default the present),
    as YYYY-MM-DD: the day a lookup was checked and a Draw is saved, never the UTC day (after about 8 pm in Ithaca
    that is tomorrow). Its standard offset, one hour more by the US federal rule when it keeps daylight time (15
    U.S.C. 260a: from 2 am on the second Sunday of March to 2 am on the first Sunday of November; Ithaca: UTC-4,
    otherwise UTC-5), so no time-zone database is needed in Rhino's Python."""
    zone = PLACE["time_zone"]
    standard = zone["standard_utc_offset_hours"]
    if zone["daylight_saving"] not in ("us_federal", "none"):
        raise ValueError("unknown daylight-saving rule " + repr(zone["daylight_saving"]) + " in place.json")
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    now = now.astimezone(_dt.timezone.utc).replace(tzinfo=None)

    def sunday(month, nth):              # the nth Sunday of the month in now's year
        first = _dt.datetime(now.year, month, 1)
        return first + _dt.timedelta(days=(6 - first.weekday()) % 7 + 7 * (nth - 1))
    summer = (zone["daylight_saving"] == "us_federal" and         # 2 am local: standard time, then daylight time
              sunday(3, 2) + _dt.timedelta(hours=2 - standard) <= now < sunday(11, 1) + _dt.timedelta(hours=1 - standard))
    return (now + _dt.timedelta(hours=standard + 1 if summer else standard)).date().isoformat()


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
    # the architect's own answers stay theirs once the box has them, whatever the box's ticks do next (a Draw that
    # stopped, a lookup started, a pick: re-lookup review round 2, the use saved under the sample's source)
    for key in ("address_source", "use_source", "corner_source"):
        if state.get(key) == ENTERED:
            saved_ui[key] = ENTERED
    return saved_ui


def zone_picked(state, zone, first):
    """The architect picked a district in the box's dropdown: it is set (and theirs, unless it is the one the box
    opened with), so Draw follows at once (draw_reason). A different district unticks "I confirm": a tick given to
    one district is never carried to another (never a false pass); the box shows the tick as unticked."""
    if zone != state.get("zone"):
        state["district_confirmed"] = False
    state["zone"] = zone
    if zone != first:
        state["zone_source"] = ENTERED
    return state
LOOKUP_LIMIT_S = 45                               # the whole lookup; the box says so, the Rhino side stops it then
LOOKING = "Looking up {}… (up to %d s)" % LOOKUP_LIMIT_S
CANCEL_LOOKUP = "Cancel lookup"
LOOKUP_CANCELLED = "Look up of {address} cancelled: nothing changed."
LOOKUP_FIRST_STEP = "Starting the lookup…"


def lookup_status(address, step, elapsed, limit=LOOKUP_LIMIT_S):
    """The box's live line while a lookup runs: which address, what it is doing now (the lookup's own latest step),
    a moving mark and the seconds so far, and when it stops by itself."""
    return "Looking up %s · %s  %s" % (address, step or LOOKUP_FIRST_STEP, progress_line(elapsed, limit))


def lookup_step(text):
    """The lookup's latest step from what it has printed so far ({"step": ...} lines), or None."""
    latest = None
    for line in str(text or "").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("step"), str) and "status" not in d:
            latest = d["step"]
    return latest


def lookup_answer(text, query=None):
    """The lookup's answer: its last line that is one ({"status": ...}); a run that printed none (stopped, crashed)
    is an error the box can say, never an answer made up from a progress line."""
    for line in reversed(str(text or "").strip().splitlines()):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict) and "status" in d:
            return d
    return {"status": "error", "query": query, "detail": "the lookup printed no answer"}


def box_ticks(state):
    """The ticks and sources the start box keeps across picks, as `state` has them (_box_loop's `ticked`)."""
    return {k: state[k] for k in ("district_confirmed", "zone_source", "address_source", "use_source",
                                  "corner_source", "checked") if k in state}


BOX_FIELDS = ("zone", "address", "use", "corner_lot")     # what the box's ticks and sources are about


def box_moved(facts_before, ui_before, facts_after, ui_after):
    """Whether a pick changed what the start box's ticks and sources are about: the district, address, use or corner
    answer, the doubts "I checked this" settles, or an earlier lookup's preview put back (drop_pending: its district,
    sources and address go back to what they were before it)."""
    facts_before, facts_after = facts_before or {}, facts_after or {}
    ui_before, ui_after = ui_before or {}, ui_after or {}
    return (any(facts_before.get(k) != facts_after.get(k) for k in BOX_FIELDS)
            or (ui_before.get("doubts") or {}) != (ui_after.get("doubts") or {})
            or (ui_before.get("_pending") is not None and ui_after.get("_pending") is not ui_before.get("_pending")))


def ticks_after_pick(what, ticks, answer=None, moved=True):
    """The start box's ticks and sources kept after a pick (_box_loop's `ticked`; `ticks`: box_ticks of the box as
    the architect left it; `answer`: the status of a lookup answer the pick put in the box, None for none; `moved`:
    box_moved for this pick). A lookup's answer (or a saved one used) replaces them, so the district must be confirmed
    again, unless it filled nothing and moved nothing (not found, offline, outside the City, too slow, a saved one
    refused, with no earlier preview put back): then the box is as the architect left it, and so are its ticks.
    Everything else keeps them exactly as the box shows them: Look up (while it runs the box shows the architect's
    own ticks; Draw is off meanwhile) and Cancel lookup. So no tick or source from before Look up is ever brought
    back, onto a district, use, address or corner changed during the lookup ("suggested by Gordium" on a district the
    architect picked) or after they took it off; no tick is kept on a district a lookup's answer put in or back; and
    a district they took off is never shown ticked again from the file (review of #32, 2026-10-28): an answer that
    replaces them leaves the district unconfirmed outright, never the earlier Draw's confirmation again (an earlier
    preview put back also puts back the file's tick, and the architect may have taken it off: sceptic of round 4)."""
    if what in ("pick:lookup_done", "pick:use_saved") and (answer == "found" or moved):
        return {"district_confirmed": False}
    return dict(ticks or {})


def lookup_cancelled(saved_ui, before):
    """The box's choices after Cancel lookup: as they were before Look up was pressed (`before`: the lookup line
    then, None for none), saying it was cancelled. Nothing else changes: the lookup only ever fills the box when its
    answer is in."""
    saved_ui = dict(saved_ui or {})
    address = ((saved_ui.get("_lookup") or {}).get("looking")) or "the address"
    restored = dict(before or {})
    restored.pop("looking", None)
    earlier = (before or {}).get("says") or ""
    if (before or {}).get("cancelled"):            # the line before was an earlier Cancel's: said once, not again
        earlier = (before or {}).get("said_before") or ""
    restored.update(says=" ".join(t for t in (LOOKUP_CANCELLED.format(address=address), earlier) if t),
                    cancelled=True, said_before=earlier)
    saved_ui["_lookup"] = restored
    return saved_ui
CHECKABLE = ("lot", "street", "ground")          # what "I checked this" settles (the district has its own tick)
DOUBT_KEPT = "The lookup found this doubtful (its reason came from a source that can't be kept): check it."
LOOKUP_SAYS = {                                   # the box's line when a lookup couldn't fill it in
    "not_found": "No City of Ithaca address found for {query}: check the spelling and Look up again, or put back "
                 "the lot's own address (or clear it) and draw the lot.",
    "outside_city": "{message}",
    "offline": "Couldn't reach the map services (offline?): Look up again later, or put back the lot's own address "
               "(or clear it) and enter the site by hand.",
    "error": "A map service answered with an error: Look up again, or put back the lot's own address (or clear it) "
             "and enter the site by hand.",
    "timeout": "The lookup took too long: try Look up again, or put back the lot's own address (or clear it) and "
               "enter the site by hand.",
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


STILL_SHOWN = "The lot shown is still {address}'s: nothing in the model changed."
NOTHING_CHANGED = "Nothing in the model changed."


def still_shown(saved_ui):
    """After a lookup that found no lot: which lot the model still shows (the one drawn, else the lot's own address
    when the box opened), so the architect never wonders whether the old lot is the new address's."""
    saved_ui = saved_ui or {}
    address = saved_ui.get("drawn_address") or saved_ui.get("_box_address")
    return STILL_SHOWN.format(address=address.split(",")[0].strip()) if address else NOTHING_CHANGED


# ---- address type-ahead (the place's site_lookup adapter's suggest, in lookup_box's own process; the box shows the list) ----
SUGGEST_DELAY_S = 0.3          # s after the last key before the City's address layer is asked
SUGGEST_LIMIT_S = 4.0          # s: slower than this, it is no help: "Suggestions unavailable"
SUGGEST_MIN_CHARS = 4
SUGGESTIONS_UNAVAILABLE = "Suggestions unavailable: type the full address and press Look up."
NO_MATCH = "No matching address suggested: type the full address and press Look up."
CITY_SUFFIX = _ADDRESSES["tail"]           # the place's own: ", Ithaca, NY" (PLACE)


BOX_TEXT_WIDTH = 560           # px: the start box's long lines wrap here (one unbroken amber line stretched the box
                               # across the screen: Rhino run of #33 a3eb1d7)
LIST_ROW_PX, LIST_PAD_PX = 20, 2   # (2: the frame's border, so a row's text sits centred, not high: Rhino run of ee8f2ce)


def list_height(rows, row_px=LIST_ROW_PX):
    """The suggestion list's height in px: as tall as its rows (1 to 8) at `row_px` each (the pitch Rhino lays its
    rows out at, read from the list where it can be), never rows of empty space (Rhino run of a3eb1d7: one suggestion
    sat above five empty rows)."""
    return max(1, min(int(rows or 0), 8)) * int(row_px) + LIST_PAD_PX


def wants_suggestions(text, chosen=None):
    """Whether to ask for suggestions for what is typed: at least SUGGEST_MIN_CHARS characters, and not the
    suggestion just picked (picking one never opens the list again)."""
    text = str(text or "")
    return len(text.lstrip()) >= SUGGEST_MIN_CHARS and text != chosen


HINT_NOTE_PX = 20          # the quiet note's one line (size 10) and its row spacing


def hint_rows_px(list_shown, list_px, note):
    """How much taller the start box is while its suggestion rows show: the list (and its spacing) and the note's
    line, each only while shown (review round 1: an offline note showed with nothing added, pushing Draw down)."""
    return ((list_px + 6) if list_shown else 0) + (HINT_NOTE_PX if note else 0)


def hint_rows_shown(list_shown, note):
    """Whether the start box's suggestion rows (the type-ahead list and its quiet note) take any room: only while
    one of them has something to show (the architect's review, 2026-10-28: an empty gap under Address)."""
    return bool(list_shown) or bool(note)


def suggestions_shown(answer, typed):
    """(the list, a quiet note) for a type-ahead answer, or None when it is for something no longer typed (a stale
    answer is dropped). Offline, an error or too slow: no list and the note that suggestions are unavailable (the
    box still works by typing). None found: a quiet note says so, so the architect can tell the list is working
    (UX review 2026-10-27: "312 Hudson St" showed nothing at all)."""
    answer = answer or {}
    if answer.get("query") != typed:
        return None
    if answer.get("status") == "ok":
        found = [str(s) for s in answer.get("suggestions") or []]
        return found, "" if found else NO_MATCH
    return [], SUGGESTIONS_UNAVAILABLE


def list_step(index, count, key):
    """The list's selection after Down or Up in the address box (none selected: -1). Stays within the list."""
    if count <= 0:
        return -1
    if key == "down":
        return min(index + 1, count - 1)
    if key == "up":
        return max(index - 1, 0)
    return index


def with_city(address):
    """The address as the lookup is asked for it: ", Ithaca, NY" added when no town or ZIP is typed (Ben, 2026-10-21:
    "106 Ithaca Rd" is the City's). Only when the address plainly ends with its street ("106 Ithaca Rd", "120 North
    Cayuga Street"): anything after the street type ("106 Ithaca Rd Dryden", "12 Main St Cayuga Heights", a ZIP)
    may be another town and is kept as typed, so another town stays another town (review round 1), and anything
    after a comma is kept as typed too."""
    text = " ".join(str(address or "").split())
    if not text or "," in text:
        return text
    words = text.lower().replace(".", " ").split()
    street_types = {w for k, v in STREET_WORDS.items() if k not in ("north", "south", "east", "west") for w in (k, v)}
    if len(words) >= 3 and words[0][:1].isdigit() and words[-1] in street_types:
        return text + CITY_SUFFIX
    return text


def clean_address(text):
    """An address as the architect reads it: the geocoder's "96 Ithaca Road, Ithaca, NY, 14850" as "96 Ithaca Road,
    Ithaca, NY 14850" (no comma before the ZIP; Rhino run of #33 df08fc0). Anything else as it is."""
    import re
    return re.sub(r",\s*(\d{5}(?:-\d{4})?)\s*$", r" \1", str(text or "").strip())


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


def looked_up_corner(payload, facts, saved_ui):
    """(facts, saved_ui) with a found lookup's Corner lot? answer: No where it found one street (road widths known),
    Yes where it found two or more, else unanswered (asked, never guessed; its old source goes too), credited to the
    street service. The one reading the box's preview (preview_lookup: shown for the architect to keep or change)
    and Draw's reset (lookup_choices) both use, so the box shows the answer Draw saves (UX walkthrough 2026-10-28:
    the box said "Not answered" while Draw saved the lookup's "no" as "confirmed by you")."""
    got, labels = (payload or {}).get("facts") or {}, (payload or {}).get("labels") or {}
    corner = (got.get("corner_lot") or {}).get("value")
    streets = ((got.get("street_side") or {}).get("value") or {}).get("streets") or {}
    facts, saved_ui = dict(facts or {}), dict(saved_ui or {})
    if corner == "no":
        facts["corner_lot"] = False
    elif corner == "yes" or (corner == "ask" and len(streets) > 1):
        facts["corner_lot"] = True               # it faces two streets (the box asks which line is the front)
    else:
        facts.pop("corner_lot", None)            # unknown: asked, never guessed
    if corner:
        saved_ui["corner_source"] = SUGGESTED + " · " + (labels.get("corner_lot") or SOURCE_OF["street"])
    else:
        saved_ui.pop("corner_source", None)
    return facts, saved_ui


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
    # the map's "outside the City" holds for this box session, each address said (round 14: one slot, cleared by
    # a found lookup of another address), through any later lookup that finds no lot (round 13: offline undid it);
    # a found lookup of that same address ends it for that address only
    # (a live one only: a copy saved earlier never outranks the City map's newer answer: round 15)
    outside = [a for a in saved_ui.get("_outside_for") or []
               if not (look["status"] == "found" and not payload.get("saved_on")
                       and same_site_address(a, look["query"] or ""))]
    if look["status"] == "outside_city":
        outside.append(look["query"] or facts.get("address") or "the address")
    saved_ui["_outside_for"] = outside
    if look["status"] != "found":
        look["says"] = " ".join(t for t in (look["says"], still_shown(saved_ui)) if t)
        return facts, saved_ui
    got, details = payload.get("facts") or {}, payload.get("details") or {}
    labels, kept = payload.get("labels") or {}, payload.get("kept_reasons") or {}

    def value(name):
        return (got.get(name) or {}).get("value")

    def label(name, row):
        return labels.get(name) or SOURCE_OF[row]

    live, keep = {}, {}
    for name, d in details.items():          # every doubtful or asked fact's reason, by row; reasons add up
        # (a doubt without its reason is still a doubt: a saved lookup keeps the status but not a reason worked out
        # from a source that may not be kept; dropped, the saved lot was more certain than the live one: a false
        # pass, start-flow round 7)
        if d.get("status") in ("needs_review", "ask"):
            row = ROW_OF.get(name, name)
            live[row] = _merged(live.get(row), d.get("reason") or (OVERLAYS_NOT_KEPT if row == "overlays" else DOUBT_KEPT))
            keep[row] = _merged(keep.get(row), kept.get(name) or DOUBT_KEPT)
    found_overlays = value("overlays") or []
    if found_overlays:                       # what was found, by name, not only that something was
        live["overlays"] = _merged("Found on this lot: " + "; ".join(found_overlays) + ".", live.get("overlays") or "")
    if value("address"):
        facts["address"] = clean_address(value("address"))
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
        live["zone"] = _merged(live.get("zone"), SAVED_NO_DISTRICT if payload.get("saved_on") else NO_DISTRICT)
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
        # (a saved lookup keeps the line, not the street side's value, used live: its source still says where the
        # line came from and when it was saved: start-flow round 6)
        if (side or payload.get("saved_on")) and draws_line:
            saved_ui["street_source"] = SUGGESTED + " · " + label("street_side", "street")
        else:
            saved_ui.pop("street_source", None)
    facts, saved_ui = looked_up_corner(payload, facts, saved_ui)
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
    # how much the ground the lookup found falls: said, and from 0.5 ft (measure.FLAT_FALL_FT) it holds height and
    # stories at needs review; the points themselves are never used. Only from a whole reading: with points missing
    # (the elevation service's doubt) or fewer than three, a fall can't be told (one point reads 0.0, "level": a
    # false pass, slope review round 1), so none is kept and the ground counts as unknown
    whole = (details.get("ground") or {}).get("status") not in ("needs_review", "ask") and len(zs) >= GROUND_POINTS
    if FLAT_GROUND and zs and whole:
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
    street: {"lines", "ids": the street lines worked out at the pick (rhino-ui's street runs), "name"} or
    {"picks": the lot lines [a, b] clicked, "name": the clicked line's street (street_name_after_pick, else
    typed; None: unnamed)}; lot (Use my survey…): the outline picked; draw_lot: the outline drawn; terrain: the
    surface picked; spot / regrade: the points placed. Esc, Enter or nothing picked (`outcome` empty): nothing
    changes, every doubt stays (eval-integrity audit: Esc on Place spot grades wiped the ground's doubt).
    The street lines change only through set_street_lines (arch-fixes-2 round 7): on a corner lot every line
    clicked, no one name for them; otherwise pick_street, the name on the clicked line only (rounds 9-11)."""
    facts, saved_ui = dict(facts), dict(saved_ui)
    if not outcome or (what == "street" and not (outcome.get("picks") or outcome.get("lines"))):
        return facts, saved_ui
    if what == "street" and outcome.get("lines"):     # the street lines worked out at the pick (street runs)
        saved_ui = settle(saved_ui, "street")
        set_street_lines(facts, outcome["lines"], outcome.get("ids"))
        if facts.get("corner_lot") is True:            # two streets: no one name for them
            saved_ui.pop("street_name", None)
        else:
            saved_ui["street_name"] = outcome.get("name")      # the name on the clicked line only
        saved_ui["street_source"] = ENTERED
    elif what == "street" and facts.get("corner_lot") is not True:   # (a corner lot's clicks come as "lines"
        picks, name = outcome["picks"], outcome.get("name")              # with their ids, never bare: #18 reads a
        saved_ui = settle(saved_ui, "street")          # corner lot's streets only from them)
        lines, ids = pick_street(facts.get("street_line"), facts.get("street_ids"), picks[0], name)
        set_street_lines(facts, lines, ids)            # the name on the clicked line only
        saved_ui["street_name"] = name
        saved_ui["street_source"] = ENTERED
    elif what in ("lot", "draw_lot"):
        if outcome != facts.get("lot_id"):             # another lot: the looked-up ground was read on the old one
            facts, saved_ui = after_lot_pick(facts, outcome), lot_ground_dropped(saved_ui)
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
    unlooked = address_reason(state)
    if unlooked:
        return unlooked
    if state.get("needs_lookup"):                 # an empty file: a found lookup first, or the site by hand
        return LOOK_UP_FIRST_SITE
    if not state.get("zone"):
        return "Pick the district to continue."
    if not state.get("district_confirmed"):
        return "Confirm the district to continue."
    if parse_feet(state.get("design_buffer")) is None:
        return BUFFER_UNREAD
    if state.get("lot_missing"):
        return "Draw or pick the lot to continue."
    return ""


def box_reason(state):
    """The box's own reason line under Draw: draw_reason's, except when it would only repeat the amber line a lookup
    that found no lot already shows (what happened, what to do, the lot still shown): said once (Rhino run of #33
    ee8f2ce: the no-lot state said it twice)."""
    reason = draw_reason(state)
    look = state.get("lookup") or {}
    if reason and look.get("says") and look.get("status") in LOOKUP_SAYS and reason == address_reason(state) \
            and same_site_address(state.get("address"), look.get("query")):    # (that lookup's address, not another)
        return ""
    return reason


def can_draw(state):
    """Draw is on only once the address typed is one already found (address_reason), the district is confirmed (a
    looked-up district is only a suggestion), the design buffer, if typed, can be read, and there is a lot."""
    return draw_reason(state) == ""


START_KEY = "gordium:start"          # on each floor block GordiumStart drew: how it was drawn (start_tag), for Switch
SWITCH_LABEL = "Switch side yards"
SIDE_YARDS_SAID = "Side yards: "       # how the starting house's note names the larger side yard's side (check.side_words)


def start_tag(start, story, floor_to_floor, design_buffer):
    """What a floor block of the starting house carries (START_KEY), so Switch side yards can redraw the house as it
    was asked for and tell whether it is still as drawn: its floor (outline, base, top, in feet), where the larger
    side yard is ("left" or "right", seen from the street; None when the zone's side yards are the same), and the
    floor-to-floor height and design buffer it was drawn with."""
    floor = start["floors"][story]
    split = start.get("side_split") or {}
    ring = floor["outline"]
    area = abs(sum(ring[i - 1][0] * ring[i][1] - ring[i][0] * ring[i - 1][1] for i in range(len(ring)))) / 2
    return json.dumps({"volume": area * (floor["top"] - floor["base"]), "story": story, "stories": len(start["floors"]), "outline": floor["outline"],
                       "base": floor["base"], "top": floor["top"], "larger_side": split.get("larger_side"), "floor_to_floor": floor_to_floor,
                       "design_buffer": design_buffer or 0.0})


def can_switch(source_line):
    """The panel's Switch side yards button goes under the Starting house site fact when the house has one larger
    side yard (its note says which side)."""
    return bool(source_line) and source_line.startswith("Starting house") and SIDE_YARDS_SAID in source_line


def _start_record(text):
    """One floor's START_KEY record (start_tag), or None when it can't be read (one record, not a JSON-lines file)."""
    try:
        tag = json.loads(text)
    except (TypeError, ValueError):
        return None
    return tag if isinstance(tag, dict) and {"outline", "base", "top"} <= set(tag) else None


def switch_plan(found, tolerance=0.01):
    """What Switch side yards does with the starting house's floor blocks found in the model, each (its START_KEY
    text, its bounding box in feet: (x0, y0, z0), (x1, y1, z1), its volume in cubic feet or None, and whether it is
    locked or hidden, itself or by its layer): {"larger_side": the other side, "floor_to_floor",
    "design_buffer"} to redraw it, or {"refused": why} when there is nothing to switch, or the house is no longer as
    Gordium drew it (moved, stretched, a floor deleted): the architect's edits are never thrown away."""
    if not found:
        return {"refused": "There is no starting house in this file to switch (GordiumStart draws one)."}
    tags = []
    if any(len(f) > 3 and f[3] for f in found):     # the architect's lock is kept: nothing deleted from under it
        return {"refused": "The starting house is locked or hidden (itself or its layer), so it isn't redrawn. "
                           "Unlock and show it, then press " + SWITCH_LABEL + " again."}
    for text, (low, high), volume, *_ in found:
        tag = _start_record(text)
        if tag is None:
            return {"refused": "The starting house's record can't be read, so it isn't redrawn."}
        xs, ys = [p[0] for p in tag["outline"]], [p[1] for p in tag["outline"]]
        want = (min(xs), min(ys), tag["base"]), (max(xs), max(ys), tag["top"])
        same_box = all(abs(a - b) <= tolerance for a, b in zip(want[0] + want[1], tuple(low) + tuple(high)))
        # the same box but a different solid (a notch, a chamfered corner): changed too (review round 1, F5b)
        same_solid = volume is not None and tag.get("volume") is not None and \
            abs(volume - tag["volume"]) <= 1e-6 * tag["volume"] + 1e-4   # a box measures exactly (round 2, F2)
        if not (same_box and same_solid):
            return {"refused": "The starting house has changed since Gordium drew it, so it isn't redrawn (your "
                               "edits are kept). Delete it and run GordiumStart for a new one."}
        tags.append(tag)
    if sorted(t.get("story", -1) for t in tags) != list(range(tags[0].get("stories") or 0)):
        return {"refused": "The starting house has changed since Gordium drew it (a floor is missing or added), so "
                           "it isn't redrawn (your edits are kept). Delete it and run GordiumStart for a new one."}
    sides = {t.get("larger_side") for t in tags}
    inputs = {(t.get("floor_to_floor"), t.get("design_buffer")) for t in tags}
    if len(sides) != 1 or len(inputs) != 1:
        return {"refused": "The starting house's floors weren't drawn together, so it isn't redrawn."}
    side = sides.pop()
    if side not in ("left", "right"):
        return {"refused": "This district's side yards are the same on both sides: there is nothing to switch."}
    floor_to_floor, buffer = inputs.pop()
    return {"larger_side": "right" if side == "left" else "left", "floor_to_floor": floor_to_floor,
            "design_buffer": buffer or 0.0}


def starting_house_fact(note, today):
    """The site fact for how far the starting house keeps back from the limits: Gordium's own figure, so never
    "confirmed by you" (the architect didn't confirm it). None when no house was drawn (`note` None)."""
    if not note:
        return None
    # the panel puts "Starting house: " in front, and it describes the house as Gordium drew it (the architect
    # may since have moved or replaced it), so it says so
    said = note[len("Starting house: "):] if note.startswith("Starting house: ") else \
        "it " + note[len("Starting house "):] if note.startswith("Starting house ") else \
        "the l" + note[1:] if note.startswith("Largest house") else note
    return {"value": "as first drawn, " + said, "source": SUGGESTED, "confirmed_by": None, "date": today}


# what the box's Change… on the street row does on a corner lot (_box_pick): one click per street keeps that whole
# street, and Enter ends it (never "pick each lot line": a click already takes the street's every piece)
CORNER_HINT = ("This lot faces two streets: click Change… on " + STREET_LABEL + ", then click once on each street "
               "(one click keeps the whole street) and press Enter")


def grown_height(client_height, content_height, padding):
    """The start box's new inner height when a line shown again needs more room (the amber line back after "Corner
    lot?" is set to Not answered): the content's own height plus the box's padding above and below, if that is more
    than the box has; else None. Never smaller: the box doesn't jump as answers change (a box opened with the line
    hidden had no room for it, and Cancel and Draw were cut off at the bottom: the Rhino walk, 2026-10-28)."""
    want = int(math.ceil(content_height)) + padding
    return want if want > client_height else None


def uncertain(state):
    """The one amber line for a case the box can't settle by itself, with what to do; None when there's none. A
    lookup that went wrong (not found, offline…) says so here; what a found lookup only tells (the lot shown dashed,
    nothing drawn until Draw) is lookup_note's plain line, never amber (the architect's review, 2026-10-28: the
    question and the information read as one warning)."""
    says = None if lookup_note(state) else (state.get("lookup") or {}).get("says")
    question = _question(state)
    return " · ".join(t for t in (question, says) if t) or None     # never one instead of the other


LOOKUP_INFO = ("found", "set_aside")      # a lookup's own line that only informs: shown plain


def lookup_note(state):
    """The plain line under the amber one: what a found (or set-aside) lookup tells, or None."""
    look = state.get("lookup") or {}
    says = look.get("says") if look.get("status") in LOOKUP_INFO else None
    # the offline safety net (a saved copy shown: the services didn't answer, pick the district again) asks for
    # something: it stays on the amber line (review round 1 of this change)
    # and so does the guide-only note (the State's tax map didn't answer: draw your lot over the guide; round 2)
    asks = says and (says.startswith(SAVED_SAYS.split("{")[0]) or says == GUIDE_PREVIEW)
    return None if asks else says


def _question(state):
    """Every question the box still has (each one, never only the first)."""
    asks = []
    if state.get("corner_lot") is None:          # never guessed: unanswered, the yards wait for it (§325-19C)
        asks.append("Does this lot face two streets? Answer Corner lot? under " + STREET_LABEL)
    elif state.get("corner_lot"):
        asks.append(CORNER_HINT)
    if len(state.get("zones_found") or []) > 1:
        asks.append("This lot is in two zones: pick the zone that applies")
    return " · ".join(asks) or None


# The MVP assumes flat ground (Ben, 2026-10-20): flat at the lot level and finished (with "assuming flat ground" on
# the height and stories rows and in the report). Height and stories are checked on it only where the lookup found
# the lot level (measure.flat_assumption_unsafe: a fall under 0.5 ft); a sloping lot, or one with no ground looked
# up, gives them needs review (2026-10-29). The spot-grade, terrain and regrade paths stay, behind this one switch:
# set it to False to bring the Ground row back.
FLAT_GROUND = True
GROUND_POINTS = 3          # the fewest looked-up ground points a fall is read from (the lookup reads every corner + 1)
ASSUMED_FLAT = "assuming flat ground"
ASSUMED_SOURCE = "assumed (flat ground, the MVP's rule)"


def ground_facts(state, lot_level, flat=None):
    """The facts the checker gets from the Ground row (the checker never sees where a fact came from). With the MVP's
    flat-ground switch on: flat at the lot level, finished, and said to be assumed. Otherwise: ground you set as
    finished, or ticked "No regrading near the house", counts as the finished grade the code measures from; ground
    only as it is (existing), unticked, gives height and stories needs review (spec C5)."""
    if FLAT_GROUND if flat is None else flat:
        return {"grade_is": "finished", "ground_is_flat": True, "grade_elevation": lot_level, "grade_from": None,
                "ground_assumed": "flat",
                # the looked-up fall, 0 too (level, known); None (unknown) removes one saved for an earlier lookup
                # (Draw sets every key given and drops each None: slope review round 1, a stale 0.0 passed)
                "ground_fall": state.get("ground_fall")}
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


# the box's own choices that Gordium fills in (the use, the street, the corner lot): the architect's word only once
# changed (their source then ENTERED); left as they were, never "confirmed by you" (fact_sources, source_lines)
BOX_DEFAULTS = ("use", "street", "corner_lot")
UNTOUCHED = "default, not changed by you"


def fact_sources(state, today, confirmed):
    """Every fact the box set, as {value, source, confirmed_by, date}: saved in the .3dm beside the facts and
    shown in the panel and the report. `confirmed`: the architect pressed Draw (the district needs its own tick).
    A box default the architect left as it was (BOX_DEFAULTS) is confirmed by no one: pressing Draw is not saying
    yes to a dropdown never opened (the architect's review, 2026-10-28: "Use: One-family dwelling, detached ·
    suggested by Gordium · confirmed by you" for a use never changed)."""
    by = "you" if confirmed else None
    ground = state.get("ground") or {}
    kind = ground.get("kind") or "flat"

    def fact(value, source, who=by):
        return {"value": value, "source": source, "confirmed_by": who, "date": today}

    def chosen(key):                   # a box default: the architect's only once changed, or ticked "I checked this"
        # (review round 1 of panel-wording, P2: a street ticked as checked read "default, not changed by you")
        # (the corner answer sits on the street's row, ROW_OF: that row's tick confirms it too; round 2, P3)
        row = ROW_OF.get(key + "_lot", key) if key == "corner" else key
        mine = state.get(key + "_source") == ENTERED or row in (state.get("checked") or [])
        return by if mine else None

    city = (" · " + IN_CITY_SAID.format(date=state["city_by_hand"])) if state.get("city_by_hand") else ""
    return {     # (the architect's Yes, by hand, on the address's source: shown in the panel and report, round 12)
        "address": fact(state.get("address") or None,     # (an earlier Draw's Yes, read back, never twice)
                        (state.get("address_source") or ENTERED).split(" · " + IN_CITY_SAID.split(" (")[0])[0] + city),
        "zone": fact(state.get("zone"), state.get("zone_source") or ENTERED,
                     by if state.get("district_confirmed") else None),
        "use": fact(state.get("use_name") or state.get("use"), state.get("use_source") or SUGGESTED, chosen("use")),
        # the follow-up answers (Ben, 2026-10-25): each saved as entered by you, and what the use itself says,
        # shown in the panel and the report (exactly the facts answers_applied sends the checker)
        **follow_up_sources(state, fact),
        # the size, then where it came from, once ("Lot: 6,570 sf · the tax map (±2 ft, approximate) · confirmed…")
        "lot": fact(lot_size(state.get("lot_area")), lot_source(state.get("lot_surveyed"), state.get("lot_source"))),
        # the street's name only when it may be kept (the City's roads may not: "street_name_saved" then None, and
        # the address's street, a kept fact, says it instead)
        "street": fact(street_name({**state, "street_name": state.get("street_name_saved")})
                       if "street_name_saved" in state else street_name(state),
                       state.get("street_source") or SUGGESTED, chosen("street")),
        "corner_lot": fact({None: None, False: "no, one street", True: "yes, two streets"}[state.get("corner_lot")],
                           state.get("corner_source") or SUGGESTED, chosen("corner")),
        # with the MVP's flat ground, an assumption, credited to no service and confirmed by no one
        # (whether that decides height and stories is the measuring's: measure.flat_assumption_unsafe)
        "ground": (fact("assumed flat" + (f" (the looked-up ground falls about {state['ground_fall']:g} ft across the "
                        "lot)" if state.get("ground_fall") is not None else " (ground levels not read in full)"),
                        ASSUMED_SOURCE, None) if FLAT_GROUND else
                   fact(ground_text(ground) + (" · no regrading near the house" if state.get("no_regrading") else ""),
                        "as drawn" if kind == "flat" else ground.get("source") or
                        ("picked by you" if kind == "terrain" else "placed by you"))),
    }


def follow_up_sources(state, fact):
    """The sources of the facts the box sets after Use (answers_applied's): each answer to a question asked,
    "entered by you", and each fact the use says, IMPLIED_SOURCE. An answer kept but not asked keeps its saved
    source (sources_kept)."""
    zone, use, options = state.get("zone"), state.get("use"), state.get("options")
    facts, answered = answers_applied({}, state.get("answers"), zone, use, options)
    return {k: fact({True: "yes", False: "no"}.get(v, v), ENTERED if k in answered else IMPLIED_SOURCE)
            for k, v in facts.items()}


def sources_kept(saved, facts):
    """The saved sources Draw keeps before adding the box's own (fact_sources): of the facts the box can ask (BOX_ASKS)
    and the use details (DEFERRED_FACTS, answered in the panel's row dialog, which saves their "entered by you":
    row_sources), only those still set in `facts` (the facts after Draw: an answer kept, unshown, keeps its source);
    a fact Draw unset or dropped (a blank, what the old use said) loses its source with it. Those Draw asks or the use
    says are given their source again by fact_sources."""
    return {k: v for k, v in (saved or {}).items()
            if k not in BOX_ASKS + DEFERRED_FACTS or (facts or {}).get(k) is not None}


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
    if on_layer(layer, MASSING):                     # its floors and roof each on its own sublayer
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


DIM_LIFT_FT = 0.1       # the yard dimensions stand this far above the lot's level (never in it, never under it)


def dim_level(lot_level_ft):
    """The height (feet) the yard dimensions are drawn at: just above the lot's own level (its outline's lowest
    point), so the ground and a lot drawn above z 0 never hide them where they are depth-tested; 0 + lift
    without a lot."""
    return (lot_level_ft or 0.0) + DIM_LIFT_FT


def lines_on_top(parallel, direction_z):
    """Whether Gordium's lines (the lot line, the envelope's outline, the dimensions, the neighbourhood) are drawn
    over everything in this view: in plan yes, so a line under the roof (the buildable outline, a dimension to the
    wall) stays visible; in every other view (perspective, the elevations, shaded or not) no: depth-tested, hidden
    behind the solids in front of them, as the model's own lines are (Ben, 2026-10-21)."""
    return is_plan_view(parallel, direction_z)


def model_ticks(a, b, size):
    """A dimension's end ticks in the model (drawn depth-tested with it): for a level line, at each end a slash at
    45° to it in plan (dim_ticks on x and y), at that end's own height; for an upright one (the height), a slash
    leaning 45° across x, y and z, so it shows in the Front and the Right views alike. `size` in model units.
    Each tick is a pair of (x, y, z)."""
    if ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 > 1e-9:
        return [((p0[0], p0[1], end[2]), (p1[0], p1[1], end[2]))
                for (p0, p1), end in zip(dim_ticks(a[:2], b[:2], size), (a, b))]
    if abs(b[2] - a[2]) < 1e-9:
        return []
    s = size / 2 / 3 ** 0.5                  # a slash of length `size` along (1, -1, 1)
    return [((p[0] - s, p[1] + s, p[2] - s), (p[0] + s, p[1] - s, p[2] + s)) for p in (a, b)]


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


# ---- edits made without touching an object (the audit of main, 2026-10-29): live mode heard only objects added,
# deleted, replaced or re-attributed, so these left a ✓ showing as current over a model that had changed.
def layer_edit_counts(event, old, new):
    """Whether a layer change can change what Gordium checks. Which objects are the lot and the buildings is decided
    by each object's layer's full path (classify), hidden and locked objects counted too, so a layer renamed or
    moved under another parent counts (`old`, `new`: the layer's (name, parent id) before and after, None if it
    can't be read: then it counts), and so does one deleted or brought back. Its colour, whether it is shown or
    locked, the current layer, a new empty layer and the order of the layer list don't (Gordium itself changes
    those on its own layers at every check: counting them would grey every result it had just shown). `event`:
    Rhino's LayerTableEventType's name (Added, Deleted, Undeleted, Modified, Sorted, Current)."""
    if event in ("Deleted", "Undeleted"):
        return True
    if event == "Modified":
        return old is None or new is None or tuple(old) != tuple(new)
    return event not in ("Added", "Sorted", "Current")       # any other kind Rhino adds: counted, never missed


def block_edit_counts(event):
    """Whether a block definition change can change what Gordium checks: a block's contents edited (BlockEdit),
    redefined, deleted or brought back changes every building placed from it. A new definition (nothing placed from
    it yet: placing one adds an object, heard on its own) and the order of the list don't. `event`: Rhino's
    InstanceDefinitionTableEventType's name."""
    return event not in ("Added", "Sorted")


def units_edit_counts(seen, now):
    """Whether a document properties change changed the model's units, the one property the check reads (every
    length is taken to feet by its scale): `seen`, the units last noted for this document (None: none yet, so it
    counts, never assumed unchanged), `now` the units after the change. Rhino says only that some property
    changed (a render setting, a note), so the units are compared."""
    return seen is None or seen != now


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


@contextlib.contextmanager
def undo_step(doc, words):
    """Everything written to `doc` inside it is one undo step called `words` (Rhino's BeginUndoRecord /
    EndUndoRecord), ended even when the change fails. Serial 0: Rhino is already recording (inside a command), and
    that record holds the change: never ended here."""
    serial = doc.BeginUndoRecord(words)
    try:
        yield
    finally:
        if serial:
            doc.EndUndoRecord(serial)


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
    facts.pop("overlays_none_found", None)       # a found lookup decides it again, for its own lot only
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
        none_found = overlays_none_found(answer, w["lot_ring"])
        if none_found:
            facts["overlays_none_found"] = none_found
        spots = [] if FLAT_GROUND else [table.add_spot(p) for p in w.get("spots") or []]   # flat: none drawn
        session.add(spots)
        saved_ui.update(replaceable_lot=lot_id, lookup_frame=w.get("frame"), lookup_spots=spots)
        if spots:
            saved_ui["ground_kind"] = "spot"
    elif w.get("guide_ring"):
        guide = w["guide_ring"]
    saved_ui["lookup_snapshot"] = w.get("snapshot")
    return facts, saved_ui, guide


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


# ---- long work: a line that says what Gordium is doing, and a Cancel that stops it --------------------------------
# The checker's and the lookup's work runs in their own processes; the plugin waits for them on a Job's thread,
# never on Rhino's, so Rhino keeps drawing and answering while they work (a slow one shows a small window after
# WAIT_WINDOW_S with the current step, the seconds so far and Cancel). Cancel stops the process: its answer is never
# used, so nothing it would have changed changes.

class WorkCancelled(Exception):
    """The architect pressed Cancel while Gordium worked: the work was stopped and nothing it would have changed was
    changed."""


WAIT_WINDOW_S = 0.4        # s: work quicker than this shows no window at all (no flash on a quick check)
SPINNER = ("●○○", "○●○", "○○●")
SPIN_S = 0.3               # s per frame of the moving mark
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


def check_not_done(last, since):
    """Why a Check gave no result, for the command line (STATE["last"], set by that check at or after `since`):
    cancelled, the model changed while it ran, or it could not run; None when nothing was set by it (a box open, a
    check already running: nothing happened, so nothing is said)."""
    last = last or {}
    if not last.get("error") or last.get("at", 0) < since:
        return None
    if last.get("cancelled"):
        return CHECK_CANCELLED + ". " + CHECK_CANCELLED_NOTE
    if last.get("outdated"):
        return CHECK_OUTDATED
    return "Check could not run: " + str(last["error"])[:200]
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


def progress_line(elapsed, limit=None):
    """The moving mark and the seconds so far ("○●○  7 s"), with when the work stops by itself if it has a limit.
    The mark is worked out from the time, so it moves at the same pace whoever draws it."""
    elapsed = max(0.0, float(elapsed or 0))
    text = "%s  %d s" % (SPINNER[int(elapsed / SPIN_S) % len(SPINNER)], int(elapsed))
    return text + (" (stops at %d s)" % limit if limit else "")


class Job:
    """One piece of long work on its own thread, never Rhino's: work(step) returns the result; step(text) says what
    it is doing now. Rhino's thread only reads it (done, step, elapsed()), waits a moment for it (wait), and may
    cancel it: `stop` (run on the caller's thread) stops the process doing the work, and from then on the work's
    result is never used (outcome() says "cancelled" even if an answer still arrives)."""

    def __init__(self, work, step, stop=None, clock=time.monotonic):
        self.step, self.done, self.cancelled = step, False, False
        self.result = self.error = None
        self._stop, self._clock = stop, clock
        self.started = clock()
        self._thread = threading.Thread(target=self._run, args=(work,), daemon=True, name="gordium-job")
        self._thread.start()

    def say(self, text):
        if text and not self.cancelled:
            self.step = text

    def _run(self, work):
        try:
            self.result = work(self.say)
        except BaseException as e:            # noqa: BLE001  (kept for the caller, on its own thread)
            self.error = e
        finally:
            self.done = True

    def elapsed(self):
        return self._clock() - self.started

    def finished(self):
        """Nothing more to wait for: the work is done, or it was cancelled (its answer is dropped)."""
        return self.done or self.cancelled

    def wait(self, timeout):
        """Wait at most `timeout` s for the work; whether there is nothing more to wait for."""
        self._thread.join(timeout)
        return self.finished()

    def cancellable(self):
        return self._stop is not None and not self.finished()

    def cancel(self):
        """Stop the work (once; never after it is done; never work with no way to stop it, whose thread would go on
        reading the checker's answers: review round 2): True when it was stopped."""
        if not self.cancellable():
            return False
        self.cancelled = True
        self.step = CANCELLING
        if self._stop is not None:
            self._stop()
        return True

    def outcome(self):
        """("cancelled", None), ("error", the exception) or ("done", the result)."""
        if self.cancelled:
            return "cancelled", None
        if self.error is not None:
            return "error", self.error
        return "done", self.result


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


LIVE_ONLY = "shown live, not saved in this file."   # site_lookup.adapters.ithaca_city.context's mark on a live-only layer's credit line
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


def exchange(sends, lines, request, limit, on_step=None):
    """Send one request (a dict with its "id") and wait at most `limit` s for its answer (answer_for); each progress
    line before it goes to `on_step`."""
    sends.put(json.dumps(request) + "\n")
    return answer_for(lines, request["id"], limit, on_step)


HANDLES = ("hooks", "doc_hooks", "command_hook", "overlay", "panel", "panel_parts", "toast_timer", "label_timer",
           "worker", "worker_sends", "worker_lines", "live_timer", "live_check")


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


def answer_for(lines, request_id, limit, on_step=None, clock=time.monotonic):
    """The checker's answer to request `request_id`, from `lines` (a queue the plugin's reader thread fills with
    every line the checker writes, then None when it stops); None if it stopped. This request's progress lines
    ({"id", "step"}, sent before its answer) go to `on_step`. Raises CheckerOutOfStep when the answer doesn't come
    within `limit` seconds of asking (progress lines don't extend it), when a line isn't this request's, or isn't
    an answer: then later lines may belong to earlier requests, so the plugin restarts the checker rather than ever
    showing an earlier check's result as this one's."""
    deadline = clock() + limit
    while True:
        try:
            line = lines.get(timeout=max(0.0, deadline - clock()))
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
        if "step" in answer and "ok" not in answer:      # a progress line: what it is doing now
            if on_step is not None:
                on_step(str(answer["step"]))
            continue
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


# ---- re-lookup on a drawn site (Ben, 2026-10-21): Look up previews, Draw resets ------------------------------------
# Look up only fills the box: the answer is kept as a preview (its lot shown dashed on screen, no objects), nothing in
# the model changes. Draw with an address other than the one drawn starts clean: everything Gordium drew is cleared
# (the lot it drew, the starting house as Gordium drew it, the lookup's spot grades) and the new lot and starting
# house drawn, in one undo step. The architect's own work (a lot they drew, picked or surveyed; an edited starting
# house; buildings they drew) is never removed without asking once. A new address is a new site (Ben, 2026-10-25):
# its lot replaces the one in the model whichever they answer, their own lot too; "Keep my building" keeps only their
# buildings, checked on the new lot. The same address and Draw: no reset.

KEEP_MINE = "keep"
START_FRESH = "fresh"
LOOK_UP_FIRST = "Press Look up to find {address} first."
NOT_FOUND_YET = "No lot found for {address} (the line above says why): correct the address and press Look up, or {back}."
LOOKUP_NOT_ANSWERED = "The lookup of {address} didn't finish (the line above says why): press Look up again, or {back}."
PICK_A_MATCH = "Pick one of the matches under Address, then press Look up."
WAIT_LOOKUP = "Looking up {address}: Draw once the answer is in."
GUIDE_PREVIEW = ("The State's tax map didn't answer; the City's outline is shown as a dashed guide only (it can't be "
                 "kept). Draw clears what Gordium drew for the old address; then Draw my lot… over the guide.")
CITY_TAIL = set(_ADDRESSES["own_words"]) | set(_ADDRESSES["state_words"]) | {"usa"}   # Ithaca: ithaca ny new york


def address_words(address):
    """An address's own words for comparing: the part before the first comma (the city, state and ZIP after it set
    aside, and a trailing "Ithaca NY 14850" typed without commas), lower case, the usual abbreviations alike
    (Road = Rd, West = W: STREET_WORDS). "106 Ithaca Rd" keeps its street's name: only the tail is the city's."""
    words = [STREET_WORDS.get(w, w) for w in str(address or "").split(",", 1)[0].lower().replace(".", " ").split()]
    while len(words) > 2 and (words[-1] in CITY_TAIL or (words[-1][:5].isdigit() and len(words[-1]) in (5, 10))):
        words.pop()
    return words


def same_address(a, b):
    """Two addresses the same lot's, as typed or found (address_words): case, commas, spaces, the city/state tail
    and "Rd"/"Road" aside. Nothing is the same as an empty address."""
    words = address_words(a)
    return bool(words) and words == address_words(b)


MISSING = object()
AFTER_DRAW = " · after Draw"       # on a row that describes the looked-up lot, which Draw has yet to draw


def show_pending_lot(state, facts, saved_ui):
    """The box's state with the Lot and Front lot line rows describing the looked-up lot (marked "after Draw")
    when nothing of the architect's or Gordium's is drawn yet: no lot, or only the sample's stand-in (Ben,
    2026-10-27: the rows kept saying the sample's 7,033 sf and Ithaca Rd). Display only: no fact is written
    before Draw. Once a lot is drawn (Gordium's from a lookup, or the architect's own) the rows describe the
    drawing, and the state comes back as it was. A City guide alone is left as it was (its own flow)."""
    pending = (saved_ui or {}).get("_pending")
    sample_only = not (facts or {}).get("lot_id") or (saved_ui or {}).get("from_sample")
    if (not pending or not sample_only or not lookup_may_replace(facts, saved_ui)
            or is_drawn(pending.get("address"), saved_ui)      # Draw draws nothing new for it: no "after Draw"
            or (state.get("lookup") or {}).get("looking")           # another address is being looked up
            or not (same_address(state.get("address") or "", pending.get("address"))      # blank: Draw sets the
                    or same_address(state.get("address") or "", pending.get("query")))):    # preview aside
        return state
    answer = pending.get("answer") or {}
    got = answer.get("facts") or {}
    w = answer.get("writes") or {}
    lot = (got.get("lot") or {}).get("value") or {}
    if not (lot and w.get("lot_ring")):                      # the City's guide only: no lot of it is drawn (its
        return state                                         # own flow: Draw clears, then the architect draws)
    side = (got.get("street_side") or {}).get("value") or {}
    street = None
    if side.get("street") and w.get("street_line"):
        street = address_street(pending.get("address"), side["street"]) or side["street"].title()
    label = (answer.get("labels") or {}).get("lot") or SOURCE_OF["lot"]
    return dict(state, has_lot=True, lot_missing=False, lot_area=lot.get("area_sf"), lot_surveyed=False,
                lot_source=label, street_name=street, after_draw=True)


PREVIEW_SAYS = ("Shown dashed: {address}'s lot. Nothing in the model changes until Draw, which replaces what Gordium "
                "drew with this lot and a new starting house.")
SET_ASIDE = "The lookup of {address} was set aside (the address was changed): Look up to preview another address."


def preview_lookup(answer, facts, saved_ui, zones=()):
    """(facts, saved_ui, preview ring or None) after a lookup's answer. Look up only fills the box (Ben): the
    address and the district (a suggestion, ticked again), nothing else, so the lot, street and corner rows keep
    saying what is drawn; the rest of the answer waits in `_pending` for Draw (apply_reset), its lot shown dashed
    (the ring returned). An earlier preview's box changes are undone first (drop_pending), so a failed lookup or a
    new one never leaves another address's district behind (re-lookup review round 1)."""
    facts, saved_ui = drop_pending(facts, saved_ui)
    before_f, before_s = dict(facts), dict(saved_ui)
    replaces = lookup_may_replace(facts, saved_ui)
    facts, saved_ui = lookup_choices(answer, facts, saved_ui, zones, replaces=False)
    if (answer or {}).get("status") != "found":
        return facts, saved_ui, None
    # the Corner lot? answer Draw will save, shown now for the architect to keep or change (it is an answer, not
    # something drawn; Draw keeps the box's: apply_reset). Only for a new lot: the address already drawn is drawn
    # again by nothing, so its own answer stays (review round 1 of this fix, F1: a re-lookup of the drawn address
    # put the lookup's "no" over the architect's Yes on a corner lot)
    new_lot = not is_drawn(facts.get("address") or answer.get("query"), saved_ui)
    if new_lot:
        facts, saved_ui = looked_up_corner(answer, facts, saved_ui)
    w = answer.get("writes") or {}
    undo = [(where, k, before.get(k, MISSING), after.get(k, MISSING))
            for where, before, after in (("facts", before_f, facts), ("saved", before_s, saved_ui))
            for k in set(before) | set(after) if k not in ("_lookup", "_pending", "_outside_for")   # (the
            # session's, never one preview's: set aside, it brought back an address found since: round 16)
            and before.get(k, MISSING) is not after.get(k, MISSING) and before.get(k, MISSING) != after.get(k, MISSING)]
    if new_lot:                                  # the corner answer always goes back with the preview (drop_pending),
        undo += [(where, k, before.get(k, MISSING), after.get(k, MISSING))   # changed by it or not
                 for where, k in (("facts", "corner_lot"), ("saved", "corner_source")) + PREVIEW_STREET
                 for before, after in [(before_f, facts) if where == "facts" else (before_s, saved_ui)]
                 if not any(u[0] == where and u[1] == k for u in undo)]
    address = facts.get("address") or answer.get("query")
    saved_ui["_pending"] = {"address": address, "query": answer.get("query"), "answer": answer, "undo": undo,
                            "lot_id": facts.get("lot_id")}   # the drawn lot the street lines go back to (drop_pending)
    if not replaces:
        saved_ui["_lookup"]["says"] = ("Your own lot is kept until you press Draw: the lookup filled in the address "
                                       "and the district.")
    elif not is_drawn(address, saved_ui):
        saved_ui["_lookup"]["says"] = (GUIDE_PREVIEW if not w.get("lot_ring") and w.get("guide_ring") else
                                       PREVIEW_SAYS.format(address=address))
    if answer.get("saved_on"):                   # the offline safety net: said, whatever else the line said
        saved_ui["_lookup"]["says"] = SAVED_SAYS.format(address=address, date=answer["saved_on"])
    return facts, saved_ui, w.get("lot_ring") or w.get("guide_ring")


PREVIEW_ANSWERS = ("corner_lot", "corner_source")      # answered for the previewed lot: put back when it is dropped
# the drawn lot's street lines, put back with them: lines picked while another lot was previewed (under its corner
# answer, or under one changed after the pick) never stay on the drawn lot (rounds 2 and 3 of the corner fix: a
# lot answered No kept two streets' lines; one answered Yes kept one)
PREVIEW_STREET = (("facts", "street_line"), ("facts", "street_ids"), ("saved", "street_name"),
                  ("saved", "_street_name"), ("saved", "street_source"))


def previews_new_lot(saved_ui):
    """Whether the box shows a looked-up lot that Draw will draw (a lookup pending, not of the address drawn)."""
    pending = (saved_ui or {}).get("_pending")
    return bool(pending) and not is_drawn(pending.get("address"), saved_ui)


def drop_pending(facts, saved_ui):
    """(facts, saved_ui) with the pending preview gone and the box changes it made undone, each only while it is as
    the preview left it (an architect's later change stays)."""
    facts, saved_ui = dict(facts or {}), dict(saved_ui or {})
    pending = saved_ui.pop("_pending", None) or {}
    def same(a, b):                    # None and no value are the same (the box writes "no district" as None)
        return (MISSING if a is None else a) == (MISSING if b is None else b)

    # the street lines go back only onto the lot they were drawn on: a lot picked during the preview (Use my
    # survey..., Draw my lot...) dropped them, and its street is asked again (review round 4 of the corner fix, F1:
    # the old lot's street line came back on a survey lot, off its outline)
    same_lot = (facts.get("lot_id") or None) == (pending.get("lot_id") or None)
    corner_was = facts.get("corner_lot")
    for where, key, old, new in pending.get("undo") or []:
        target = facts if where == "facts" else saved_ui
        # the Corner lot? answer shown for the previewed lot, or given for it, was that lot's: never the drawn lot's
        # (review round 1 of the corner fix, F2: a No given for the preview stayed on a drawn corner lot), and the
        # drawn lot's street lines as they were (PREVIEW_STREET)
        street = same_lot and (where, key) in PREVIEW_STREET
        if key in PREVIEW_ANSWERS or street or same(target.get(key, MISSING), new):
            if old is MISSING:
                target.pop(key, None)
            else:
                target[key] = old
    if not same_lot and facts.get("corner_lot") != corner_was:   # that lot's lines were picked under the answer
        set_street_lines(facts, None)            # set aside: asked again on it, as when an answer flips
        saved_ui.pop("street_name", None)        # (corner_answered; round 5 of the corner fix: a survey lot kept
    return facts, saved_ui                       # two lines under the drawn lot's No)


def box_opened(saved_ui, facts):
    """The box's choices as a box opens over `facts`: the address the lot had then kept for this session
    (`_box_address`, never saved), so typing it back is never a new address (Ben, 2026-10-25)."""
    return dict(saved_ui or {}, _box_address=(facts or {}).get("address"),   # (a new file: no lot and no address
                _opened_empty=not (facts or {}).get("lot_id") and not (facts or {}).get("address"))   # yet)


def start_gate(state, saved_ui):
    """The box's state with the empty-file rule (Ben, 2026-10-27): a box opened on a file with no lot (a new project)
    starts empty, and Draw stays off until a lookup of the address typed is found (`needs_lookup`), or the architect
    chose to enter the site by hand (`by_hand`: they draw the lot, pick the district and the street side, all theirs;
    no neighbourhood). A file with a lot drawn when the box opened is as before. Display and gating only: no fact
    is written here."""
    saved_ui = saved_ui or {}
    if not saved_ui.get("_opened_empty"):
        return dict(state, needs_lookup=False, by_hand=False, city_by_hand=saved_ui.get("city_by_hand"),
                    outside_for=saved_ui.get("_outside_for") or [])
    pending = saved_ui.get("_pending") or {}
    # a found lookup supersedes "by hand": its address rule applies again (sceptic 2: by hand let another town's
    # address keep the City's lookup)
    by_hand = bool(saved_ui.get("_by_hand")) and not pending
    address = state.get("address") or ""
    found = any(same_site_address(address, a) for a in (pending.get("address"), pending.get("query"),
                                                       # the City's outline only: cleared for it, the box kept
                                                       # open to draw the lot over it (sceptic 2, finding 1)
                                                       saved_ui.get("_redrawn_for"), saved_ui.get("drawn_address"))
                if a)
    return dict(state, needs_lookup=not by_hand and not found, by_hand=by_hand,
                city_by_hand=saved_ui.get("city_by_hand"),      # shown whenever kept (round 12: never seen again)
                outside_for=saved_ui.get("_outside_for") or [])


BY_HAND_CITY_ONLY = ("Gordium checks " + PLACE["name"] + " lots only: {address} is in another place. Correct the "
                     "address (a " + PLACE["name"] + " one), or clear it.")


def no_guessed_district(saved, suggested):
    """The suggestions for a file with no site yet (no lot, no address saved): without the first district's guess
    (Ben, 2026-10-27: the lookup finds it, or the architect picks it). GordiumStart and Edit site… alike (round 5)."""
    suggested = dict(suggested or {})
    if not (saved or {}).get("lot_id") and not (saved or {}).get("address") and not suggested.get("lot_id"):
        suggested["zone"] = None
    return suggested


IN_CITY_QUESTION = ("Is this lot in the " + PLACE["name"] + "?\n\nGordium checks " + PLACE["name"] + " lots only. An "
                    "address that reads \"" + _ADDRESSES["shares_mail_as"] + "\" may instead be in the "
                    + (", ".join(_ADDRESSES["shares_mail_with"][:-1]) + " or " if _ADDRESSES["shares_mail_with"][1:]
                       else "") + _ADDRESSES["shares_mail_with"][-1]
                    + ", which have their own zoning codes. The City's tax map says which.\n\n"
                    "Yes: enter the site by hand as a " + PLACE["name"] + " lot. No: nothing changes.")
IN_CITY_SAID = "You said this lot is in the " + PLACE["name"] + " ({date})."
BY_HAND_OUTSIDE = ("The lookup said {query} is outside the " + PLACE["name"] + ", and Gordium checks " + PLACE["name"]
                   + " lots only: look up a " + PLACE["name"] + " address, or close this box.")


def by_hand_refused(saved_ui):
    """Why "Enter the site by hand" is refused before its question is asked: the lookup said outside the City (round
    12: a Yes, then the address cleared or retyped, opened Draw on that lot). "" when it may be asked."""
    outside = (saved_ui or {}).get("_outside_for") or []     # (kept through later lookups: rounds 13, 14)
    return BY_HAND_OUTSIDE.format(query=outside[-1]) if outside else ""


def choose_by_hand(facts, saved_ui, in_city):
    """(facts, saved_ui) once the architect chose "Enter the site by hand" and answered IN_CITY_QUESTION: `in_city`
    is the date they said Yes (kept in the file as theirs, `city_by_hand`), else nothing changes (start-flow round
    11: "Ithaca, NY 14850" is also the Town's mail, so an address alone can't prove a City lot). Any looked-up
    preview set aside (its box changes undone; else a found lookup kept the gate on the lookup and the button did
    nothing: start-flow round 3)."""
    dropped_f, dropped = drop_pending(facts, saved_ui)
    if by_hand_refused(dropped) or not in_city:    # (asked of the state by hand would leave: round 16)
        return facts, saved_ui
    facts, saved_ui = dropped_f, dropped
    saved_ui["city_by_hand"] = str(in_city)
    saved_ui["_lookup"] = {}                       # ("outside the City" holds in `_outside_for`: by_hand_refused)
    saved_ui["_by_hand"] = True
    return facts, saved_ui


def draw_blocked(state, saved_ui):
    """Why Draw must draw nothing, whatever way it was pressed (the box, where Draw is off then, or a scripted run
    that ticks and draws): an address typed but not looked up (address_reason), or a file that opened empty with
    no found lookup of the address and no "Enter the site by hand" (start_gate). "" when Draw may go on."""
    saved_ui = saved_ui or {}
    state = dict(state, known_addresses=known_addresses(saved_ui), lookup=saved_ui.get("_lookup") or {})
    gated = start_gate(state, saved_ui)
    return address_reason(gated) or (LOOK_UP_FIRST_SITE if gated["needs_lookup"] else "")


# The offline safety net (Ben, 2026-10-27): each found lookup is saved on this computer, only as far as its sources
# allow keeping it (site_lookup's snapshot, endpoints.yaml `store`): the lot and its street line from the State's
# tax parcels, never the district (the City's zoning map is used live, never stored), so the district is picked
# again. When a later lookup of the same address can't reach the map services, the box offers the saved one.
LOOKUP_FAILED = ("offline", "error", "timeout")          # the services didn't answer (never "not found" or "outside")
USE_SAVED = "Use the lookup saved on {date}"
SAVED_SAYS = ("The map services didn't answer. Shown: the lookup of {address} saved on {date} (the lot and its street "
              "line only: pick the district again).")
SAVED_ON = " · saved on {date}"
SAVED_NOT_THIS = "The saved lookup is {saved_for}'s, not {address}'s: press Look up to find {address}."
USED_LIVE = "(used live, not stored)"                     # site_lookup.adapters.ithaca_city.lookup.USED_LIVE: a value never stored


def lookup_key(address):
    """The key a saved lookup is filed under: the address's own words (address_words), "" for none."""
    return " ".join(address_words(address))


def storable_lookup(answer):
    """The copy of a found lookup that may be saved, or None (nothing worth saving: no lot curve the sources allow
    keeping). Only the snapshot's facts (each already within its source's policy) with a value that was kept, the
    lot curve, its street line and placement, the spot grades (writes: all `raw`), its date and query. Never the
    district (used live), nor the City's guide."""
    answer = answer or {}
    w = answer.get("writes") or {}
    if answer.get("status") != "found" or not w.get("lot_ring") or answer.get("saved_on"):
        return None
    snap = w.get("snapshot") or {}
    facts = {k: v for k, v in (snap.get("facts") or {}).items()
             if isinstance(v, dict) and v.get("value") not in (None, USED_LIVE) and k != "zone"}
    if not facts.get("lot"):
        return None
    date = answer.get("checked") or str(snap.get("fetched") or "")[:10] or None
    if not date:
        return None
    return {"status": "found", "query": answer.get("query"), "message": "", "asks": [], "matches": [], "facts": facts,
            # every doubt the lookup had, by its status (the snapshot's details are within every source's policy),
            # even for a fact whose value isn't kept (the street side, the corner): never more certain than live
            "details": {k: v for k, v in (snap.get("details") or {}).items() if k != "zone"},
            "labels": {k: v for k, v in (answer.get("labels") or {}).items()     # (the service names only; the
                       if k in facts or (k == "street_side" and w.get("street_line"))},   # street line's, with it)
            "kept_reasons": {k: v for k, v in (answer.get("kept_reasons") or {}).items() if k != "zone"},
            "street_storable": bool(answer.get("street_storable")),
            "writes": {"lot_ring": w.get("lot_ring"), "guide_ring": None, "street_line": w.get("street_line"),
                       "spots": list(w.get("spots") or []), "frame": w.get("frame"), "snapshot": snap},
            "checked": date, "address": found_address(answer)}


def found_address(answer):
    """The address a lookup found ("106 Ithaca Road, Ithaca, NY, 14850"), or None."""
    value = (((answer or {}).get("facts") or {}).get("address") or {}).get("value")
    return value if isinstance(value, str) and value.strip() else None


def save_lookup(store, answer, address=None):
    """The saved lookups (a dict: key -> storable copy) with this answer added under the address typed and the one
    found; unchanged when nothing may be saved."""
    copy = storable_lookup(answer)
    if copy is None:
        return dict(store or {})
    out = dict(store or {})
    for a in (answer.get("query"), address, copy.get("address")):     # as typed, and as found
        if lookup_key(a):
            out[lookup_key(a)] = copy
    return out


def saved_offer(answer, store, address):
    """The saved lookup to offer for `address` when this lookup failed to reach the services, else None. Only the
    same site's: the key is the street address alone, so the town is checked too (same_site_address: "106 Ithaca
    Rd, Lansing" never gets the City's 106; start-flow sceptic 1, finding 2)."""
    if (answer or {}).get("status") not in LOOKUP_FAILED or not lookup_key(address):
        return None
    copy = (store or {}).get(lookup_key(address))
    if not copy or not any(same_site_address(address, a) for a in (copy.get("query"), copy.get("address")) if a):
        return None
    return copy


def use_saved(offer, offered_for, typed):
    """The saved lookup as the box's answer, only while the address typed is still the one it was offered for
    (start-flow sceptic 1, finding 1: retyped, it went in under the new address, as if that had been looked up);
    else None (the offer is dropped)."""
    if not offer or not same_site_address(typed or "", offered_for or ""):
        return None
    return as_saved(offer)


def saved_refused(look, offered_for, typed):
    """The lookup line once "Use the lookup saved on …" was pressed for an address retyped since (the button was
    still on screen: the box's rows aren't rebuilt while typing): the offer gone, and why."""
    return dict(look or {}, saved_offer=None,
                says=SAVED_NOT_THIS.format(saved_for=offered_for or "another address", address=typed or "the address"))


def as_saved(copy):
    """A saved lookup as an answer the box shows like any other, marked: its date on the line the box says, and on
    every source label ("NYS Tax Parcels Public · saved on 2026-10-27"), so the rows and what Draw saves say so.
    Its own query, never the address typed now. A source's ", used live" goes: what was saved is not live (round 9:
    "City of Ithaca roads, used live · saved on <date>")."""
    date = copy.get("checked")
    return dict(copy, saved_on=date, labels={k: v.replace(", used live", "") + SAVED_ON.format(date=date)
                                             for k, v in (copy.get("labels") or {}).items()})


def known_addresses(saved_ui):
    """The addresses Draw takes as they are, never as a new one to look up: the lot's own when the box opened, the
    one drawn, and the one last looked up and found (as found and as typed)."""
    saved_ui = saved_ui or {}
    pending = saved_ui.get("_pending") or {}
    return [a for a in (saved_ui.get("_box_address"), saved_ui.get("drawn_address"), pending.get("address"),
                        pending.get("query")) if a]


ITHACA_PLACE = set(_ADDRESSES["own_words"]) | set(_ADDRESSES["zip_codes"])   # the place's own name and ZIPs


def address_place(address):
    """The town or ZIP an address names after its first comma, as words (state and country aside), or None when it
    names none; the City's own name and ZIP codes count as none (the lot is in the City of Ithaca). Typed without
    commas, the tail after the street: a ZIP at the end, and the one word before a state or ZIP ("12 Main St Lansing
    NY 14882" names "lansing 14882": start-flow review round 9, it read as the City's), a street word never a town."""
    if "," not in str(address or ""):
        return _place_without_commas(address)
    tail = str(address or "").split(",", 1)[1:]
    text = " ".join(_address_tokens((tail[0] if tail else "").replace(",", " ")))
    text = text.replace("united states of america", "").replace("united states", "")
    words = [w for w in text.split() if w not in STATE_WORDS]
    words = [w[:5] if w[:5].isdigit() else w for w in words if _may_be_place(w)]
    places = [w for w in words if w not in ITHACA_PLACE]
    return " ".join(places) or None


# Words that end a street's name ("Rd", "Way"), so what follows them is the town: STREET_WORDS both ways and the
# other endings of the City's streets (round 10: "1 Willard Way NY 14850" read "way" as a town). Never a word that
# also names a place nearby ("Heights": the Village of Cayuga Heights; "Hill"; "East": East Ithaca, in the Town).
DIRECTIONS = {"north", "south", "east", "west", "n", "s", "e", "w"}
STREET_ENDINGS = ((set(STREET_WORDS) | set(STREET_WORDS.values())) - DIRECTIONS    # "East Ithaca" is the Town's
                  | {"way", "park", "walk", "row", "alley", "aly", "path", "trail", "trl", "ext", "extension", "sq",
                     "square", "plaza", "loop", "run", "crossing", "pike", "tpke", "turnpike", "rte", "route"})
STATE_WORDS = (*_ADDRESSES["state_words"], "usa", "us", *_ADDRESSES["county_words"])   # Ithaca's: ny … tompkins county
UNIT_WORDS = {"apt", "apartment", "unit", "#", "ste", "suite", "fl", "floor", "rm", "room", "bldg", "building"}
NOT_A_PLACE = {"rear", "front", "lower", "upper", "-", "&"}    # a part of a lot or house ("101 N Aurora St Rear")
# Places around the City that share its "Ithaca" mail and ZIPs, read as a town even after a street with no known
# ending ("1 Snyder Hill Dryden": round 11); "town" and "village" too ("Town of Ithaca"). By hand, the architect also
# says the lot is in the City (IN_CITY_QUESTION): an address alone can't prove it.
NEARBY_PLACES = {"town", "village"} | set(_ADDRESSES["nearby_places"])     # (PLACE: Lansing, Dryden, … for Ithaca)


def _address_tokens(text):
    """An address's words for reading its town: lower case, "." dropped ("N.Y."), "#" apart, "NY14850" as
    "ny 14850", the City's own name as "ithaca", and a unit and its number dropped ("Apt 2", "Unit B": round 11,
    read as a town)."""
    text = str(text or "").lower().replace(".", "").replace("#", " # ")
    text = re.sub(r"\bny(\d{5})", r"ny \1", text)
    text = " ".join(text.split())
    for other in _ADDRESSES["also_written"]:                 # "city of ithaca", "ithaca city" -> "ithaca"
        text = text.replace(other, _ADDRESSES["own_words"][0])
    words, out = text.split(), []
    i = 0
    while i < len(words):
        if words[i] in UNIT_WORDS:
            i += 2
            continue
        out.append(words[i])
        i += 1
    return out


def _may_be_place(word):
    """Whether a word after the street may name a town: never a route's number ("Rte 13"), a letter ("St N", "St B":
    round 13), "1/2", "2nd", punctuation, a part of a lot or house (NOT_A_PLACE) or a direction ("NE"). A ZIP may."""
    return not ((word.isdigit() and len(word) < 5) or len(word) < 2 or word in NOT_A_PLACE
                or word in ("ne", "nw", "se", "sw") or re.fullmatch(r"\d*/\d*|\d+(st|nd|rd|th)|\W+", word))


def _place_without_commas(address):
    """address_place for an address typed without commas (round 9: "12 Main St Lansing NY 14882" read as the
    City's). The town is every word after the street's last ending (STREET_ENDINGS), state and the City's own name
    and ZIP codes aside ("12 Main St Town of Ithaca NY" names "town of": round 10, the Town is not the City; "12 Main
    St Lansing" names "lansing"). A street with no known ending: the word before a state or ZIP, if one was typed;
    else a place nearby named anywhere after the street's first word (NEARBY_PLACES); else None."""
    words = _address_tokens(address)
    ends = [i for i, w in enumerate(words) if i >= 1 and w in STREET_ENDINGS]
    if ends:
        tail = words[ends[-1] + 1:]
    else:
        tail, cut = [], len(words)
        while cut > 2 and (words[cut - 1] in STATE_WORDS or (words[cut - 1][:5].isdigit()
                                                            and len(words[cut - 1]) in (5, 10))):
            cut -= 1
        if cut < len(words) and cut > 2:
            tail = words[cut - 1:]
        elif cut == len(words):              # nothing typed after the street but, perhaps, a place nearby
            tail = [w for w in words[2:] if w in NEARBY_PLACES]
    tail = [w[:5] if w[:5].isdigit() else w for w in tail if w not in STATE_WORDS]
    tail = [w for w in tail if _may_be_place(w)]
    places = [w for w in tail if w not in ITHACA_PLACE]
    return " ".join(places) or None


def same_site_address(a, b):
    """same_address, and not another town's (the Draw gate, review round 2 of the typed-address rule: "106 Ithaca
    Rd, Dryden" was taken for the lot's own "106 Ithaca Rd, Ithaca")."""
    return same_address(a, b) and address_place(a) == address_place(b)


def address_reason(state):
    """Why Draw is off because of the address (Ben, 2026-10-25): an address typed that is neither the lot's own nor
    the one last looked up and found must be looked up first, so a new address never ends up as a label on the old
    lot. "" when the address is blank or known (`known_addresses`, in the box's state; absent: no address rule)."""
    address = (state.get("address") or "").strip()
    known = state.get("known_addresses")
    look = state.get("lookup") or {}
    if state.get("by_hand") and not look.get("looking"):   # the site by hand, in a file that was empty: the address
        # is the architect's label (no lot of another to mislabel), but a City of Ithaca one (round 5: another
        # place, or one the lookup already said is outside the City, was checked under the City's rules)
        if state.get("outside_for"):                 # whatever the address now (round 12: cleared or retyped)
            return BY_HAND_OUTSIDE.format(query=state["outside_for"][-1])
        if address and address_place(address) is not None:
            return BY_HAND_CITY_ONLY.format(address=address)
        return ""
    if known is not None and look.get("looking"):         # a lookup running: Draw off, its own address named
        return WAIT_LOOKUP.format(address=look["looking"])
    said = next((o for o in state.get("outside_for") or [] for a in [address] + list(known or [])
                 if a and same_site_address(a, o)), None)   # the address typed, or the lot's own whatever is typed
    if said:                                                 # (round 14: cleared, Draw went on)
        return BY_HAND_OUTSIDE.format(query=said)   # the lot's own address too (round 13: a drawn
        #   lot the lookup now says is outside the City was drawn again and checked under the City's rules)
    if not address or known is None or any(same_site_address(address, k) for k in known):
        return ""
    status = look.get("status")
    if status in LOOKUP_SAYS and same_site_address(address, look.get("query")):    # looked up, no lot came back
        if status == "multiple":
            return PICK_A_MATCH
        back = ("put back " + known[0].split(",")[0]) if known else "clear the address"   # blank: Draw without one
        return (LOOKUP_NOT_ANSWERED if status in ("offline", "error", "timeout") else NOT_FOUND_YET).format(
            address=address, back=back)
    return LOOK_UP_FIRST.format(address=address)


def settle_pending(facts, saved_ui, address):
    """At Draw: the preview stays only while the box's address is still the one looked up (typed or found); an
    address typed since drops it, its box changes undone (re-lookup review round 1: the preview was drawn under the
    typed address)."""
    pending = (saved_ui or {}).get("_pending")
    if pending and not (same_site_address(address, pending.get("address"))
                        or same_site_address(address, pending.get("query"))):   # another town's: dropped too
        facts, saved_ui = drop_pending(facts, saved_ui)
        # its line goes with it: the box never says another address's lot is shown or will be drawn (round 3)
        saved_ui["_lookup"] = {"status": "set_aside", "query": pending.get("query"), "asks": [], "matches": [],
                               "says": SET_ASIDE.format(address=pending.get("address") or pending.get("query"))}
        return facts, saved_ui
    return dict(facts or {}), dict(saved_ui or {})


OWN_LOTS = ("your surveyed lot", "the lot you drew", "your lot")


def own_work(table, facts, saved_ui):
    """What of the architect's own a reset would remove, in words (empty: everything drawn is Gordium's): a lot they
    drew, picked or surveyed (named as theirs: OWN_LOTS); the starting house if it was edited since Gordium drew it
    (or Gordium has no record of drawing it: never assumed to be its own); buildings they drew."""
    out = []
    facts, saved_ui = facts or {}, saved_ui or {}
    lot = facts.get("lot_id")
    if lot and lot != saved_ui.get("replaceable_lot"):
        out.append(OWN_LOTS[0] if facts.get("lot_surveyed") else
                   OWN_LOTS[1] if saved_ui.get("lot_source") == "drawn by you" else OWN_LOTS[2])
    house = table.massing()
    if house and table.fingerprint(house) != saved_ui.get("house_fingerprint"):
        out.append("your changes to the starting house")
    if table.buildings():
        out.append("the buildings you drew")
    return out


def is_drawn(address, saved_ui):
    """Whether `address` is the one a lookup drew in this file (its lot, placed on the map): then Draw draws nothing
    new for it. A drawn sample counts too (coordinator, 2026-10-27, Ben's P0): Look up then Check in Edit site on a
    file drawn from the sample started fresh, redrawing the lot and the house over the architect's work. New files
    no longer start from the sample (start_gate): 106 Ithaca Rd is looked up like any address."""
    drawn = (saved_ui or {}).get("drawn_address")
    return drawn is not None and same_address(address, drawn)


def reset_plan(facts, saved_ui, mine):
    """At Draw: "none" (no answer pending, or the same address as the one drawn: nothing is redrawn), "redraw" (a new
    address over what Gordium drew: cleared and drawn again, no question) or "ask" (the architect's own work, `mine`,
    would be lost: asked once)."""
    pending = (saved_ui or {}).get("_pending")
    if not pending:
        return "none"
    if is_drawn(pending.get("address"), saved_ui):
        return "none"
    return "ask" if mine else "redraw"


def draw_decision(table, facts, saved_ui):
    """What Draw does first, as gordium_rhino._draw_prepare acts on it once the address is known (address_reason
    keeps Draw off before): (plan, mine). plan: reset_plan's "none" / "redraw" / "ask"; `mine`: what of the
    architect's would go."""
    mine = own_work(table, facts, saved_ui or {})
    return reset_plan(facts, saved_ui or {}, mine), mine


def reset_question(address, mine, answer=None):
    """The one question when the architect's own work would go: (the question, Start fresh, Keep my building or
    None). A new address is a new site (Ben, 2026-10-25): its lot replaces the one in the model whichever they
    answer, their own lot too (a lot they surveyed, drew or picked), so the question and the Keep answer both say
    so; only their buildings can be kept, checked on the new address's lot. Keeping is offered only when there is a
    building of theirs (their lot alone: Start fresh or Cancel). `answer`: the lookup's, pending; when it had only
    the City's outline (no lot the State's tax map gives), the new lot is the one they draw over it."""
    place = str(address or "").split(",", 1)[0].strip() or "this address"
    lot = [m for m in mine if m in OWN_LOTS]
    building = [m for m in mine if m not in OWN_LOTS]
    w = (answer or {}).get("writes") or {}
    by = (" (you draw " + place + "'s lot over the City's outline)" if not w.get("lot_ring") and w.get("guide_ring")
          else " by " + place + "'s lot")
    said = []
    if building:
        listed = _joined(building)
        said.append(listed[0].upper() + listed[1:] + " will be removed.")
    if lot:
        said.append(lot[0][0].upper() + lot[0][1:] + " will be replaced" + by + ".")
    keep = "Keep my building and check it on " + place + "'s lot"
    if lot:
        keep += " (" + lot[0] + " will be replaced)"
    return ("Start fresh for " + place + "? " + " ".join(said),
            ("Start fresh", START_FRESH),
            (keep, KEEP_MINE) if building else None)


def _joined(items):
    """'a', 'a and b', 'a, b and c' (named apart from use-questions' _listed(options, zone), #37)."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


BOX_CHOSEN_FACTS = ("address", "zone", "use")
BOX_CHOSEN_UI = ("address_source", "zone_source", "_zone_said", "_reconfirm", "_zones_found", "use_source")
# what of the box's state the reset redraws (the rest is the architect's choices in the box): after_reset_state
RESET_STATE_KEYS = ("has_lot", "lot_missing", "lot_area", "lot_surveyed", "lot_source", "street_name",
                    "street_name_saved", "street_source", "corner_lot", "corner_source", "ground", "ground_fall",
                    "lookup", "live", "doubts", "checked", "address", "address_source", "after_draw",
                    "city_by_hand")    # (the old lot's Yes never on the lot drawn in its place: start-flow round 14)


def after_reset_state(shown, fresh):
    """The box's state to save at Draw after a reset: the architect's choices as the box showed them (`shown`: the
    district and its tick, the use, the design buffer, no regrading), the lot, street side, corner and ground as
    the reset drew them (`fresh`, rebuilt from the model): never the old lot's size, survey or corner answer saved
    over the new lot (re-lookup review round 1, P0). The address too: apply_reset kept the box's, or the address as
    found for a loose query typed back (typed-address rule, review round 2)."""
    return dict(shown, **{k: fresh.get(k) for k in RESET_STATE_KEYS})


def box_facts(facts, saved_ui, state):
    """(facts, saved_ui) with the box's own answers in them: a changed corner answer (corner_answered), the
    address, district, use and whether the lot is a survey. The pure part of gordium_rhino._apply_box."""
    if previews_new_lot(saved_ui):       # the answer is the previewed lot's: the drawn lot's street lines stay (its
        facts = dict(facts, corner_lot=state.get("corner_lot"))    # own come with it at Draw: apply_reset)
        if facts["corner_lot"] is None:
            facts.pop("corner_lot")
    else:
        facts, saved_ui = corner_answered(facts, saved_ui, state.get("corner_lot"))
    facts = dict(facts, address=state.get("address") or None, zone=state.get("zone"), use=state.get("use"),
                 lot_surveyed=bool(state.get("lot_surveyed")))
    if not facts.get("address"):
        facts.pop("address")
    return facts, saved_ui


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


def draw_button(mode, saved_ui):
    """The box's last button, as what it does: "Draw" when pressing it draws (a new project; a new address that
    will be drawn, or was just cleared for), "Check" when it only checks what is there."""
    if mode == "start" or (saved_ui or {}).get("_redrawn_for"):
        return "Draw"
    pending = (saved_ui or {}).get("_pending")
    return "Draw" if pending and not is_drawn(pending.get("address"), saved_ui) else "Check"


START_HAS_BUILDING = ("This model already has a building. To start over on another address, use Edit site… in the "
                      "Gordium panel: Look up the new address and press Draw (the lot and starting house are drawn "
                      "again for it). To check the building you have, use GordiumCheck.")
