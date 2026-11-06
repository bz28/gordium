"""The address lookup's answer turned into the start box's choices, and the saved and typed addresses.

Moved here unchanged from rhino_logic.py, which still offers every name (so the Rhino plugin is
unchanged). Python 3.9 and the standard library only: Rhino 8 imports this into its own Python 3.9,
where none of the .venv's packages are installed."""

import json
import re
from .place import _ADDRESSES
from .streets import STREET_WORDS, address_street

__all__ = ['lookup_step', 'lookup_answer', 'CITY_SUFFIX', 'with_city', 'clean_address', 'lookup_says',
    'lookup_may_replace', 'looked_up_corner', 'lookup_choices', '_merged', 'KEEP_MINE', 'START_FRESH', 'LOOK_UP_FIRST',
    'NOT_FOUND_YET', 'LOOKUP_NOT_ANSWERED', 'PICK_A_MATCH', 'WAIT_LOOKUP', 'GUIDE_PREVIEW', 'CITY_TAIL',
    'address_words', 'same_address', 'MISSING', 'AFTER_DRAW', 'lookup_key', 'storable_lookup', 'found_address',
    'save_lookup', 'saved_offer', 'use_saved', 'saved_refused', 'as_saved', 'known_addresses', 'ITHACA_PLACE',
    'address_place', 'DIRECTIONS', 'STREET_ENDINGS', 'STATE_WORDS', 'UNIT_WORDS', 'NOT_A_PLACE', 'NEARBY_PLACES',
    '_address_tokens', '_may_be_place', '_place_without_commas', 'same_site_address', 'address_reason']


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
CITY_SUFFIX = _ADDRESSES["tail"]           # the place's own: ", Ithaca, NY" (PLACE)


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


# Names these functions call from the host_core modules that call back into this one. They are
# imported last, after every definition above, so the modules load in any order.
from .facts import FLAT_GROUND, GROUND_POINTS, checkable  # noqa: E402
from .start_box import (  # noqa: E402
    BY_HAND_CITY_ONLY, BY_HAND_OUTSIDE, DOUBT_KEPT, GUIDE, LOOKUP_FAILED, LOOKUP_SAYS, NO_DISTRICT,
    OVERLAYS_NOT_KEPT, ROW_OF, SAVED_NOT_THIS, SAVED_NO_DISTRICT, SAVED_ON, SOURCE_OF, SUGGESTED, USED_LIVE,
    no_rules, still_shown, two_zones_ask)
