"""The start box: its rows, its buttons and what they say, when Draw is on, a lookup's preview,
and starting again.

Moved here unchanged from rhino_logic.py, which still offers every name (so the Rhino plugin is
unchanged). Python 3.9 and the standard library only: Rhino 8 imports this into its own Python 3.9,
where none of the .venv's packages are installed."""

import datetime as _dt
import json
from .place import PLACE, _ADDRESSES
from .streets import STREET_HELP, STREET_LABEL, ZONE_TICK, address_street, street_name

__all__ = ['NOT_CHECKED_YET', 'ENTERED', 'FLOOR_TO_FLOOR', 'CORNER_CHOICES', 'SUGGESTED', 'GROUND_CHOICES', 'lot_size',
    'lot_source', 'NO_STREET_YET', 'FILL_BY_LOOKUP', 'LOOK_UP_FIRST_SITE', 'BY_HAND', 'BY_HAND_NOTE', 'NO_LOT',
    'LOT_MISSING', 'lot_text', 'ground_text', 'box_rows', 'NO_RULES', 'NO_DISTRICT', 'SAVED_NO_DISTRICT',
    'OVERLAYS_NOT_KEPT', 'city_day', 'two_zones_ask', 'no_rules', 'zone_row_text', 'saved_sources', 'zone_picked',
    'LOOKUP_LIMIT_S', 'LOOKING', 'CANCEL_LOOKUP', 'LOOKUP_CANCELLED', 'LOOKUP_FIRST_STEP', 'lookup_status', 'box_ticks',
    'BOX_FIELDS', 'box_moved', 'ticks_after_pick', 'lookup_cancelled', 'CHECKABLE', 'DOUBT_KEPT', 'LOOKUP_SAYS',
    'ROW_OF', 'SOURCE_OF', 'GUIDE', 'storable_ui', 'STILL_SHOWN', 'NOTHING_CHANGED', 'still_shown', 'BUFFER_UNREAD',
    'draw_reason', 'box_reason', 'can_draw', 'START_KEY', 'SWITCH_LABEL', 'SIDE_YARDS_SAID', 'start_tag', 'can_switch',
    '_start_record', 'switch_plan', 'SPINNER', 'SPIN_S', 'progress_line', 'show_pending_lot', 'PREVIEW_SAYS',
    'SET_ASIDE', 'preview_lookup', 'PREVIEW_ANSWERS', 'PREVIEW_STREET', 'previews_new_lot', 'drop_pending',
    'box_opened', 'start_gate', 'BY_HAND_CITY_ONLY', 'no_guessed_district', 'IN_CITY_QUESTION', 'IN_CITY_SAID',
    'BY_HAND_OUTSIDE', 'by_hand_refused', 'choose_by_hand', 'draw_blocked', 'LOOKUP_FAILED', 'USE_SAVED', 'SAVED_SAYS',
    'SAVED_ON', 'SAVED_NOT_THIS', 'USED_LIVE', 'settle_pending', 'OWN_LOTS', 'own_work', 'is_drawn', 'reset_plan',
    'draw_decision', 'reset_question', '_joined', 'BOX_CHOSEN_FACTS', 'BOX_CHOSEN_UI', 'RESET_STATE_KEYS',
    'after_reset_state', 'box_facts', 'draw_button', 'START_HAS_BUILDING']


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
SPINNER = ("●○○", "○●○", "○○●")
SPIN_S = 0.3               # s per frame of the moving mark


def progress_line(elapsed, limit=None):
    """The moving mark and the seconds so far ("○●○  7 s"), with when the work stops by itself if it has a limit.
    The mark is worked out from the time, so it moves at the same pace whoever draws it."""
    elapsed = max(0.0, float(elapsed or 0))
    text = "%s  %d s" % (SPINNER[int(elapsed / SPIN_S) % len(SPINNER)], int(elapsed))
    return text + (" (stops at %d s)" % limit if limit else "")


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


# Names these functions call from the host_core modules that call back into this one. They are
# imported last, after every definition above, so the modules load in any order.
from .facts import FLAT_GROUND, corner_answered, parse_feet, set_street_lines  # noqa: E402
from .lookup import (  # noqa: E402
    AFTER_DRAW, GUIDE_PREVIEW, KEEP_MINE, MISSING, START_FRESH, address_reason, known_addresses, looked_up_corner,
    lookup_choices, lookup_may_replace, same_address, same_site_address)
