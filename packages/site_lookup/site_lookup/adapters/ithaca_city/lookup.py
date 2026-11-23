"""Address in, site facts out: the lot, which side faces the street, whether it's a corner lot, the ground,
and a zoning suggestion. Each fact is {value, source, confirmed_by, date}, exactly the shape the start box
stores, so a looked-up fact and one the architect types are treated alike. source is one of the start box's
labels: "from tax map" for the lot (approximate: ±2'-0" downstream), "suggested by Gordium" for the rest.
Beside each fact, result["details"][name] says how sure the lookup is and where the answer came from:
{status, reason?, note?, source_detail, source_url, source_keys} (source_keys: every endpoints.yaml source
the value was worked out from; the strictest one decides what a project's snapshot may keep).

status: "suggested"   looked up, nothing doubtful (the architect still sees it and its source)
        "needs_review" looked up, but something is doubtful (the reason says what)
        "ask"          the lookup can't choose (a corner lot, two zones): the start box asks
A suggestion is never a confirmation: confirmed_by stays empty until the architect confirms.
"""

import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import yaml

from ... import geometry as g
from ...http import Offline, ServiceError
from .sources import ENDPOINTS, NAMES, PLACE, Fetcher, district, normalize_street

OVERLAYS = NAMES["districts"]["overlays"]      # zoning-map codes that are overlays, not districts (exact)

AMENDMENTS = yaml.safe_load((Path(__file__).parent / "amendments.yaml").read_text(encoding="utf-8"))
CITY_SWIS = PLACE.swis                   # 500700, the City of Ithaca (the Town has its own code and SWIS)
PLACES = PLACE.neighbours                # neighbours named in the refusal (the Town of Ithaca's two codes)
# EPSG:2261 coordinates are US survey feet (1200/3937 m); Gordium's feet are international feet (0.3048 m).
US_SURVEY_FT = (1200 / 3937) / 0.3048    # 1.000002 international feet per survey foot (0.03 sf on a 7,000 sf lot)
FROM_TAX_MAP, SUGGESTED = "from tax map", "suggested by Gordium"     # the start box's source labels
TAX_MAP_TOLERANCE_FT = 2.0               # tax-map lines can be about this far off (see the research)
MIN_FRONTAGE_FT = 10.0                   # shorter contact with a street isn't frontage (a corner sliver)
STREET_MARGIN_FT = 10.0                  # an edge faces a street within ROW/2 + this of its centerline: tax-map
                                         # lines sit up to several feet off the ROW edge (96 Ithaca Rd: 4–6 ft)
PARALLEL_MAX_DEG = 30.0                  # ... and runs within this angle of the street (side lines don't)
UNKNOWN_ROW_FT = 50.0                    # right-of-way when the road layer doesn't say (State streets)
WIDEST_ROW_FT = 100.0                    # a road without a width this close to the lot could touch it
COUNTY_POINT_TOLERANCE_FT = 50.0
ZONE_SHARE_MIN = 0.02                    # a zone covering less than 2% of the lot is ignored (edge noise)


RANK = {"suggested": 0, "needs_review": 1, "ask": 2}    # the strongest status wins; never lowered


def fact(value, source: str, url: str, date: str, status: str = "suggested", reason: str = "", note: str = "",
         label: str = SUGGESTED, key: str | tuple = "", lot: dict | None = None) -> dict:
    """A fact with its details while the lookup runs; lookup() splits the details off at the end. key is the
    endpoints.yaml source (or sources) the value came from: the strictest one decides what a project's snapshot
    may keep. lot is given for every fact worked out on the lot's outline: from the moment it exists, the fact
    counts the outline's source and carries every doubt about the lot (so even a lookup that stops half way
    keeps no more than the outline's source allows)."""
    keys = [key] if isinstance(key, str) else list(key)
    out = {"value": value, "source": label, "confirmed_by": None, "date": date, "status": "suggested",
           "source_detail": source, "source_url": url, "source_keys": [k for k in keys if k], "_reasons": []}
    if note:
        out["note"] = note
    if lot:
        uses(out, lot["key"])
        for why, k in lot["doubts"]:
            escalate(out, "needs_review", why, key=k)
    return escalate(out, status, reason)


def escalate(f: dict, status: str, reason: str = "", key: str = "") -> dict:
    """The only way a fact's status changes: raise it to `status` if that's stronger (ask > needs review >
    suggested; never lowered), and add the reason to the ones it has. key names the source a reason was worked
    out from when it isn't the fact's own (a County distance in the address's reason), so the snapshot can
    leave it out. A fact whose evidence is incomplete is never left 'suggested'."""
    if RANK[status] > RANK[f["status"]]:
        f["status"] = status
    if reason and all(reason != r for r, _ in f["_reasons"]):
        f["_reasons"].append((reason, key))
        f["reason"] = " ".join(r for r, _ in f["_reasons"])
    return f


def uses(f: dict, *keys: str) -> dict:
    """Record more sources a fact's value was worked out from (the lot's outline under its ground points)."""
    f["source_keys"] += [k for k in keys if k and k not in f["source_keys"]]
    return f


# What the lookup is doing, in the architect's words, as it goes (the start box shows the latest one live).
STEPS = {"address": "Finding the address…", "parcel": "Finding the tax parcel…",
         "streets": "Finding which lot lines face a street…", "ground": "Reading the ground elevations…",
         "zoning": "Reading the City zoning map…", "overlays": "Checking the historic, gorge and flood maps…"}


def lookup(address: str, http, now: dt.datetime | None = None, step=None) -> dict:
    """`step(text)`, if given, is told each stage as it starts (STEPS), for a live progress line; it never changes
    the answer."""
    f = Fetcher(http, now)
    today = f.now.date().isoformat()
    result = {"query": address, "status": "found", "message": "", "facts": {}, "asks": []}
    try:
        _lookup(address, f, today, result, step or (lambda text: None))
    except Offline as e:
        result.update(status="offline", message="Couldn't reach the map services (offline?): enter the site by hand.",
                      detail=str(e))
    except (ServiceError, KeyError, TypeError, ValueError, IndexError) as e:
        result.update(status="error", message="A map service answered with an error: enter the site by hand.",
                      detail=f"{type(e).__name__}: {e}")
    working = result["facts"]
    result["details"] = {k: {d: v[d] for d in DETAIL_KEYS if d in v} for k, v in working.items()}
    result["facts"] = {k: {d: v[d] for d in FACT_KEYS} for k, v in working.items()}
    result["snapshot"] = snapshot(result, working, f)
    return result


FACT_KEYS = ("value", "source", "confirmed_by", "date")
DETAIL_KEYS = ("status", "reason", "note", "source_detail", "source_url", "source_keys")


def _lookup(address: str, f: Fetcher, today: str, result: dict, say=lambda text: None) -> None:
    facts, asks = result["facts"], result["asks"]
    # ---- 1. address -> point ---------------------------------------------------------------------------
    say(STEPS["address"])
    cands = [c for c in f.geocode(address) if c["score"] >= 90]
    points = [c for c in cands if c["type"] == "PointAddress"]
    chosen = _distinct(points) or _distinct([c for c in cands if c["type"] == "StreetAddress"])
    if not chosen:
        result.update(status="not_found", message="Couldn't find this address: check it, or draw the lot.")
        return
    if len(chosen) > 1:                  # several points: fine if they're all on one parcel (one building)
        by_parcel: dict[str, tuple[dict, dict]] = {}
        unplaced: list[str] = []                             # matches whose parcel couldn't be found
        for cand in chosen:
            try:
                found = f.state_parcels_at(cand["point"])
            except (Offline, ServiceError):
                found = []
            for p in found:
                by_parcel.setdefault(p["id"], (cand, p))
            if not found:
                unplaced.append(cand["label"])
        if len(by_parcel) != 1:
            names = sorted({p["address"] or cand["label"] for cand, p in by_parcel.values()} or
                           {cand["label"] for cand in chosen})
            result.update(status="multiple", message="Several places match: " + "; ".join(names) +
                          ". Add the street direction (N/S/E/W) or the zip code.", matches=names)
            return
        chosen = [next(iter(by_parcel.values()))[0]]
    else:
        unplaced = []
    c = chosen[0]
    addr = facts["address"] = fact(c["label"], ENDPOINTS["geocoder"]["name"], ENDPOINTS["geocoder"]["url"], today,
                                   key="geocoder")
    if c["type"] != "PointAddress":
        escalate(addr, "needs_review", "Found only along the street, not at a building: check the lot it picked.")
    if unplaced:
        escalate(addr, "needs_review", f"Another match ({'; '.join(unplaced)}) couldn't be placed on a parcel: "
                                       "check this is the right address.")
    try:
        cp = f.county_point(c["number"], c["street"])
        if cp and math.dist(cp, c["point"]) > COUNTY_POINT_TOLERANCE_FT:
            escalate(addr, "needs_review", f"The State and County place this address "
                                           f"{math.dist(cp, c['point']):.0f} ft apart: check the lot.",
                     key="address_points")
    except (Offline, ServiceError):
        pass                                                   # a cross-check only; the State point stands
    # ---- 2. point -> parcel (the State copy is the stored outline; the City's adds City-only flags) ---------
    say(STEPS["parcel"])
    try:
        state = f.state_parcels_at(c["point"])
    except (Offline, ServiceError):
        state = []
    try:
        city = f.city_parcels_at(c["point"])
    except (Offline, ServiceError):
        city = []
    parcels = state or city
    if not parcels:
        result.update(status="not_found", message="The address isn't inside any tax parcel: draw the lot.")
        return
    # The City is told apart by its SWIS code: the State names both the City and the Town of Ithaca "ITHACA".
    in_city = [p for p in parcels if p["swis"] in CITY_SWIS]
    if not in_city:
        swis = parcels[0]["swis"]
        where = PLACES.get(swis, f"municipality SWIS {swis}")
        result.update(status="outside_city", message=f"This address is in the {where}, not the {PLACE.name}. "
                      f"Gordium's rules cover the {PLACE.name} only.")
        return
    if len({p["id"] for p in in_city}) > 1:
        result.update(status="multiple", message="The address sits on more than one parcel: pick the lot.",
                      matches=sorted({p["id"] for p in in_city}))
        return
    parcel = in_city[0]
    city_parcel = next((p for p in city if p["id"] == parcel["id"]), None)
    ring = max(parcel["rings"], key=g.area)
    origin = tuple(round(v, 2) for v in g.centroid(ring))
    outline = [[round((x - origin[0]) * US_SURVEY_FT, 2), round((y - origin[1]) * US_SURVEY_FT, 2)] for x, y in ring]
    src = ENDPOINTS[parcel["source"]]
    facts["parcel"] = fact(parcel["id"], src["name"], src["url"], today, key=parcel["source"])
    facts["lot"] = fact({"outline_ft": outline, "area_sf": round(g.area(ring) * US_SURVEY_FT ** 2, 1),
                         "edge_lengths_ft": [round(math.dist(a, b) * US_SURVEY_FT, 2) for a, b in g.edges(ring)],
                         "origin_epsg2261_us_survey_ft": list(origin), "tolerance_ft": TAX_MAP_TOLERANCE_FT},
                        f"{src['name']} (tax map, approximate ±{TAX_MAP_TOLERANCE_FT:.0f} ft)", src["url"], today,
                        label=FROM_TAX_MAP, key=parcel["source"],
                        note="outline_ft: international feet from the centroid (EPSG:2261 US survey feet × "
                             f"{US_SURVEY_FT:.7f}). " + (src.get("attribution") or f"Terms: {src['terms']}"))
    for name in ("parcel", "lot"):                     # a doubtful address point may have picked the wrong lot
        for why, key in addr["_reasons"]:
            escalate(facts[name], addr["status"], "This may be the wrong lot: " + why, key=key)
    if len(parcel["rings"]) > 1:
        escalate(facts["lot"], "needs_review", "This parcel has more than one piece: check the lot outline.")
    # Every fact after this is worked out on the lot's outline: it counts the outline's source and inherits
    # every doubt about the lot, from the moment it's made.
    lot = {"key": parcel["source"],
           "doubts": [("Worked out on a lot that may be the wrong one: " + why, key) for why, key in addr["_reasons"]] +
                     ([("Worked out on the largest piece of a parcel in several pieces: check the lot outline.", "")]
                      if len(parcel["rings"]) > 1 else [])}
    # ---- 3. which lines face a street ------------------------------------------------------------------
    say(STEPS["streets"])
    _streets(f, ring, c["street"], today, facts, asks, lot)
    # ---- 4. ground --------------------------------------------------------------------------------------
    say(STEPS["ground"])
    _ground(f, ring, origin, today, facts, lot)
    # ---- 5. zoning suggestion and overlays (live, never stored) --------------------------------------------
    say(STEPS["zoning"])
    map_overlays = _zoning(f, ring, c["street"], facts, asks, today, city_parcel, lot)
    say(STEPS["overlays"])
    _overlays(f, ring, city_parcel, ENDPOINTS["city_zoning"], today, facts, lot, map_overlays or ())


def _distinct(cands: list[dict]) -> list[dict]:
    """Candidates at different places (the geocoder repeats one match several times)."""
    out: list[dict] = []
    for c in sorted(cands, key=lambda c: -c["score"]):
        if not any(math.dist(c["point"], o["point"]) < 30 for o in out):
            out.append(c)
    return out


def _streets(f: Fetcher, ring, address_street: str, today: str, facts: dict, asks: list,
             lot: dict | None = None) -> None:
    key = "city_roads"
    try:
        roads = f.city_roads_near(ring)
    except (Offline, ServiceError):
        key, roads = "state_streets", None
    if roads is None:
        try:
            roads = f.state_streets_near(ring)
        except (Offline, ServiceError):
            facts["street_side"] = fact(None, "—", "", today, "needs_review",
                                        "Couldn't reach the road maps: pick the front lot line.", key=key, lot=lot)
            facts["corner_lot"] = fact("ask", "—", "", today, "ask", "Is this a corner lot?", key=key, lot=lot)
            asks.append("Couldn't look up the streets: pick the front lot line and say if it's a corner lot.")
            return
    frontage: dict[str, float] = {}
    edges_by: dict[str, list[int]] = {}
    row_unknown = False
    for i, (a, b) in enumerate(g.edges(ring)):
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        best = None
        for r in roads:
            if not r["name"] or not r["paths"]:
                continue
            reach = (r["row_ft"] or UNKNOWN_ROW_FT) / 2 + STREET_MARGIN_FT
            d, seg = min(((g.seg_distance(mid, s, t), (s, t)) for p in r["paths"] for s, t in zip(p, p[1:])),
                         default=(math.inf, None))
            if d <= reach and g.angle_between((a, b), seg) <= PARALLEL_MAX_DEG and (best is None or d < best[1]):
                best = (r["name"], d, not r["row_ft"])
        if best:
            frontage[best[0]] = frontage.get(best[0], 0.0) + math.dist(a, b) * US_SURVEY_FT
            edges_by.setdefault(best[0], []).append(i)
            row_unknown |= best[2]
    # A road near the lot without a width could reach a lot line the assumed width misses (a second street):
    # the answer is incomplete, whatever it found.
    row_unknown |= any(not r["row_ft"] and r["name"] and r["paths"] and
                       min(g.polyline_distance(v, path) for v in ring for path in r["paths"]) <= WIDEST_ROW_FT / 2 +
                       STREET_MARGIN_FT for r in roads)
    streets = {n: v for n, v in frontage.items() if v >= MIN_FRONTAGE_FT}
    src = ENDPOINTS[key]
    unsure = (f"Road widths weren't available ({src['name']}), so a {UNKNOWN_ROW_FT:.0f} ft right-of-way was "
              "assumed: check the street side and whether a second street touches the lot.") if row_unknown else ""
    if not streets:
        facts["street_side"] = fact(None, src["name"], src["url"], today, "needs_review",
                                    "No street found along this lot: pick the front lot line.", key=key, lot=lot)
        facts["corner_lot"] = fact("ask", src["name"], src["url"], today, "ask", "Is this a corner lot?", key=key, lot=lot)
        asks.append("No street found along this lot: pick the front lot line.")
        return
    names = sorted(streets, key=lambda n: (n != address_street, -streets[n]))
    front = names[0]
    value = {"street": front, "edges": edges_by[front], "frontage_ft": round(streets[front], 1),
             "streets": {n: {"edges": edges_by[n], "frontage_ft": round(streets[n], 1)} for n in names}}
    if len(names) > 1:
        facts["street_side"] = fact(value, src["name"], src["url"], today, "ask",
                                    f"This lot faces {len(names)} streets ({', '.join(names)}): pick the front.", key=key, lot=lot)
        facts["corner_lot"] = fact("ask", src["name"], src["url"], today, "ask",
                                   f"It faces {' and '.join(names)}: a corner lot (or a lot running through "
                                   "between two streets): confirm, and pick the front.", key=key, lot=lot)
        if unsure:
            escalate(facts["street_side"], "needs_review", unsure)
        asks.append(f"This lot faces two streets ({' and '.join(names[:2])}): pick the front.")
        return
    if address_street and front != address_street:
        facts["street_side"] = fact(value, src["name"], src["url"], today, "needs_review",
                                    f"The address is on {address_street}, but the lot only touches {front}: "
                                    "check the front lot line.", key=key, lot=lot)
        asks.append(f"The address says {address_street}, but the lot faces {front}: check the front.")
    else:
        facts["street_side"] = fact(value, src["name"], src["url"], today, key=key, lot=lot)
    if unsure:                                   # one street found, but a second could have been missed
        escalate(facts["street_side"], "needs_review", unsure)
        facts["corner_lot"] = fact("ask", src["name"], src["url"], today, "ask",
                                   "Road widths weren't available: is this a corner lot?", key=key, lot=lot)
        asks.append("Road widths weren't available: check the street side and say if it's a corner lot.")
    else:
        facts["corner_lot"] = fact("no", src["name"], src["url"], today, key=key, lot=lot)


def _ground(f: Fetcher, ring, origin, today: str, facts: dict, lot: dict | None = None) -> None:
    pts: list = []
    for p in ring:                                         # lot corners (merging ones closer than 3 ft)
        if all(math.dist(p, q) >= 3 for q in pts):
            pts.append(p)
    pts.append(g.centroid(ring))
    src = ENDPOINTS["elevation"]
    try:
        elev = f.elevations_ft(pts)
    except (Offline, ServiceError):
        facts["ground"] = fact(None, src["name"], src["url"], today, "needs_review",
                               "Couldn't reach the elevation service: set the ground by hand.", key="elevation", lot=lot)
        return
    samples = [{"x": round((p[0] - origin[0]) * US_SURVEY_FT, 2), "y": round((p[1] - origin[1]) * US_SURVEY_FT, 2),
                "ft": round(e, 2)}
               for p, e in zip(pts, elev) if e is not None]
    if not samples:
        facts["ground"] = fact(None, src["name"], src["url"], today, "needs_review",
                               "No elevation data here: set the ground by hand.", key="elevation", lot=lot)
        return
    lo, hi = min(s["ft"] for s in samples), max(s["ft"] for s in samples)
    facts["ground"] = fact({"points": samples, "min_ft": lo, "max_ft": hi, "kind": "existing"},
                           f"{src['name']} · today's ground (existing), an estimate", src["url"], today,
                           note="Elevations in feet above NAVD88. Finished ground after construction is set in the start box.",
                           key="elevation", lot=lot)
    if len(samples) < len(pts):
        escalate(facts["ground"], "needs_review", f"Elevation missing at {len(pts) - len(samples)} of {len(pts)} "
                                                  "points: check the ground.")


def _zoning(f: Fetcher, ring, address_street: str, facts: dict, asks: list, today: str, city_parcel,
            lot: dict | None = None) -> list[str]:
    """The zone suggestion. Returns the overlays the zoning map draws on the lot (or that it couldn't check), which
    _lookup hands to _overlays after it, whatever this finds."""
    src = ENDPOINTS["city_zoning"]
    try:
        polys = f.zoning_near(ring, pad=OVERLAY_MARGIN_FT)
        edited = f.zoning_last_edited()
    except (Offline, ServiceError):
        facts["zone"] = fact(None, src["name"], src["url"], today, "needs_review",
                             "Couldn't reach the City's zoning map: choose the district.", key="city_zoning", lot=lot)
        return ["Overlays on the City's zoning map (" + "; ".join(_overlay_name(c) for c in OVERLAYS)
                + "): couldn't check"]
    samples = g.grid_inside(ring)
    # every polygon under each point counts, never only the first: the map draws overlays (SHOD...) on top of the
    # base districts, and the service returns them in no set order (review of lookup-names, round 1)
    counts: dict[str, int] = {}
    on_map = 0
    off_map_inside = False       # a point the map doesn't cover, well inside the lot (not edge noise)
    for p in samples:
        here = {z["zone"] for z in polys if g.inside_any(p, z["rings"])}
        base = {district(c)[0] for c in here if c not in OVERLAYS}
        for z in base:
            counts[z] = counts.get(z, 0) + 1
        on_map += bool(base)
        off_map_inside |= not base and min(g.seg_distance(p, a, b) for a, b in g.edges(ring)) > MAP_EDGE_FT
    shares = {z: n / len(samples) for z, n in counts.items()} if samples else {}
    zones = sorted((z for z, s in shares.items() if s >= ZONE_SHARE_MIN), key=lambda z: -shares[z])
    # an overlay counts wherever it touches the lot or 2 ft around it, however little (never the 2% a base district
    # needs, nor only where a grid point falls: a thin strip of SHOD along one side is an overlay on the lot)
    near = _shape(ring).buffer(OVERLAY_MARGIN_FT)
    map_overlays = [f"{_overlay_name(c)} on the City's zoning map"
                    for c in sorted({z["zone"] for z in polys if z["zone"] in OVERLAYS and z["rings"]
                                     and _shape_of(z["rings"]).intersects(near)})]
    when = edited.isoformat() if edited else "unknown"
    source = f"{src['name']}, last edited {when}: a suggestion to confirm"
    covered = on_map / len(samples) if samples else 0.0
    # a code the map draws inside the lot (more than the edge noise in) that is neither a district Gordium knows nor a
    # listed overlay may be an overlay names.yaml doesn't list yet: never "none" (however little of the lot it covers)
    inner = _shape(ring).buffer(-MAP_EDGE_FT)
    strange = sorted({z["zone"] for z in polys if z["zone"] not in OVERLAYS and district(z["zone"])[1] == "unknown"
                      and z["rings"] and _shape_of(z["rings"]).intersects(inner)}, key=str)
    if strange:
        map_overlays.append(f"Overlays on the City's zoning map: couldn't check ({', '.join(map(str, strange))} drawn on "
                            "this lot isn't a district or overlay Gordium knows)")
    if off_map_inside or not on_map:   # where the map draws no district it says nothing about overlays: never "none"
        map_overlays.append(f"Overlays on the City's zoning map: couldn't check {'this lot' if not on_map else 'all of this lot'}"
                            " (the map doesn't cover it)")
    if not zones:
        facts["zone"] = fact(None, source, src["url"], today, "needs_review",
                             "This lot isn't on the City's zoning map: choose the district.", key="city_zoning", lot=lot)
        return map_overlays
    z = facts["zone"] = fact(zones[0] if len(zones) == 1 else zones, source, src["url"], today, key="city_zoning", lot=lot)
    if covered < 0.9:
        escalate(z, "needs_review", f"Only {covered:.0%} of this lot is on the City's zoning map: check the district.")
    codes = {c for c in (p["zone"] for p in polys) if district(c)[0] in zones}   # the map's own codes for them
    renamed = sorted(c for c in codes if district(c)[1] == "alias")
    if renamed:
        z["note"] = " ".join(f"The City's map writes {c}, used as {district(c)[0]}: "
                             + " ".join(NAMES["districts"]["aliases"][c]["why"].split()) for c in renamed)
    unknown = [c for c in zones if district(c)[1] == "unknown"]
    if unknown:
        escalate(z, "needs_review", f"The City's zoning map gives {' and '.join(unknown)}, which isn't one of the "
                                    "districts Gordium has rules for: choose the district.")
    for c in (c for c in zones if district(c)[1] == "unresolved"):
        escalate(z, "needs_review", " ".join(NAMES["districts"]["unresolved"][c]["why"].split()))
    if len(zones) > 1:
        asks.append(f"This lot is in {' and '.join(zones)}: pick the zone that applies.")
        escalate(z, "ask", asks[-1])
    notes = []
    streets = {address_street} | set(((facts.get("street_side") or {}).get("value") or {}).get("streets", {}))
    for a in AMENDMENTS:
        adopted = _date(a["adopted"])
        shown = _date(a.get("map_shows_since"))
        if shown and edited and edited >= shown:
            continue                     # someone checked the online map and it shows this amendment
        # Any edit moves the layer's edit date, drawn rezoning or not: only a hand check clears an amendment.
        line = (f"Ord. {a['ordinance']} ({a['title']}, adopted {adopted.isoformat()}) isn't confirmed to be "
                "on the City's online map")
        why = _amendment_reaches(a, ring, streets)
        if why:
            asks.append(f"{line} and {why}: check the current zoning map.")
            escalate(z, "needs_review", asks[-1])
            # the same map may not show what the ordinance drew here: its overlays can't be said to be none either
            map_overlays.append(f"Overlays on the City's zoning map: couldn't check (Ord. {a['ordinance']} may have "
                                "changed this lot's map)")
        else:
            notes.append(line + "; this lot is outside the area it rezoned.")
    if notes:
        z["note"] = " ".join(([z["note"]] if z.get("note") else []) + notes)
    return map_overlays


# The zoning map and the tax map are drawn separately: along a lot line they disagree by a few feet (read 2026-11-11:
# up to 2.3 ft at 106 Ithaca Rd and 601 Hancock St), so a point the zoning map misses that close to the line is that,
# not a lot off the map. Farther in, the map doesn't cover the lot, and its overlays can't be said to be none.
MAP_EDGE_FT = 5.0
OVERLAY_MARGIN_FT = TAX_MAP_TOLERANCE_FT   # an overlay this close to the tax-map lot may be on the real one


def _shape(ring):
    """A ring as a shapely polygon (made valid: a tax-map ring can touch itself)."""
    from shapely.geometry import Polygon
    from shapely.validation import make_valid
    return make_valid(Polygon(ring))


def _shape_of(rings):
    """Several rings (an ArcGIS polygon: outer rings and holes) as one shape: the even-odd union of the rings, as
    ArcGIS draws them."""
    out = None
    for r in rings:
        if len(r) >= 3:
            p = _shape(r)
            out = p if out is None else out.symmetric_difference(p)
    from shapely.geometry import Polygon
    return out if out is not None else Polygon()


def _overlay_name(code: str) -> str:
    """An overlay as the architect reads it: its name from names.yaml, then the map's code ('Adult Use Overlay
    Zone (Adult Us)')."""
    return f"{OVERLAYS[code].split(':')[0].strip()} ({code})"


def _date(v) -> dt.date | None:
    return v if isinstance(v, dt.date) or v is None else dt.date.fromisoformat(str(v))


def _amendment_reaches(a: dict, ring, streets: set) -> str:
    """Why an amendment may have rezoned this lot ('' if it can't have). Its area is a padded box around the
    districts on the ordinance's map; without one, every lot in the City may be affected."""
    area = a.get("area_epsg2261")
    if not area:
        return "its boundary isn't recorded here, so any lot may be affected"
    x0, y0, x1, y1 = g.bounds(ring)
    if x0 <= area[2] and x1 >= area[0] and y0 <= area[3] and y1 >= area[1]:
        return "this lot is in or near the area it rezoned"
    hit = sorted(streets & set(a.get("streets", [])))
    return f"rezoned {', '.join(hit)}" if hit else ""


def _overlays(f: Fetcher, ring, city_parcel, src: dict, today: str, facts: dict, lot: dict | None = None,
              map_overlays=()) -> None:
    """Historic districts, gorge protection, secondary zones and landmark flags on the parcel, and the overlays the
    zoning map draws on it (names.yaml). Not checked in this release, so any found (or any that couldn't be looked
    for) needs review."""
    found: list[str] = list(map_overlays)
    for key, field, label in (("historic_districts", "DISTRICT", "Historic district"),
                              ("gorge_zones", "ZONE", "Gorge protection zone")):
        try:
            found += [f"{label}: {n}" for n in f.overlays(key, field, ring, margin_ft=OVERLAY_MARGIN_FT)]
        except (Offline, ServiceError):
            found.append(f"{label}: couldn't check")
    if not city_parcel:
        found.append("Historic property, landmarks review, secondary and overlay zones on the parcel: couldn't check "
                     "(the City's parcel layer didn't answer for this lot)")
    else:
        if city_parcel.get("secondary_zones"):
            found.append(f"Secondary zones on the parcel: {city_parcel['secondary_zones']}")
        if city_parcel.get("overlay_zones"):   # the parcel's own record of an overlay (SHOD...), beside the map's
            found.append(f"Overlay zones on the parcel: {city_parcel['overlay_zones']}")
        # the City writes YES or NO (and, read 2026-11-11, "NR" on 57 parcels and "chk" on one for the review flag, and
        # no value on 3 for the historic one): only NO is none; any other value, or none, is said and needs review
        for field, name in (("historic_property", "Historic property"),
                            ("landmarks_review", "Landmarks Preservation Commission review")):
            flag = str(city_parcel.get(field) or "").strip()
            if flag.upper() == "YES":
                found.append(name)
            elif flag.upper() != "NO":
                found.append(f"{name}: the City's parcel record says {flag!r}" if flag else
                             f"{name}: the City's parcel record doesn't say")
    found += _flood(f, ring)
    facts["overlays"] = fact(found, "City of Ithaca overlay maps (live) and FEMA's flood maps", src["url"], today,
                             "needs_review" if found else "suggested",
                             "Overlays aren't checked in this release: check these by hand." if found else "",
                             key=("historic_districts", "gorge_zones", "city_parcels", "city_zoning", "fema_flood",
                                  "fema_pending", "fema_preliminary"), lot=lot)


# The one FEMA answer that is "no flood zone": Zone X (unshaded), "the areas of minimal flood hazard, which are the
# areas outside the SFHA and higher than the elevation of the 0.2-percent-annual-chance flood" (FEMA glossary, "Flood
# Zones", fema.gov/about/glossary/flood-zones, read 2026-11-11). Anything else keeps the overlays row: every Special
# Flood Hazard Area (SFHA_TF "T": A, AE and its floodway, AH, AO, AR, A99, V, VE), Zone X shaded (moderate: the 0.2%
# chance flood, or the 1% chance flood under a foot deep), Zone D ("possible but undetermined flood hazards",
# fema.gov/glossary/zone-d), and any value not listed here (FLD_ZONE, ZONE_SUBTY, SFHA_TF, matched exactly).
FLOOD_NONE = ("X", "AREA OF MINIMAL FLOOD HAZARD", "F")
FLOOD_MARGIN_FT = TAX_MAP_TOLERANCE_FT     # the lot and this much around it: a tax-map line may be 2 ft off


# FEMA's shaded Zone X ("moderate flood hazard", fema.gov/about/glossary/flood-zones), as NFHL layer 28 spells it
FLOOD_SHADED_X = ("0.2 PCT ANNUAL CHANCE FLOOD HAZARD", "1 PCT DEPTH LESS THAN 1 FOOT")


def _flood_name(z: dict) -> str:
    """A FEMA zone as the architect reads it."""
    sub = f", {str(z['subtype']).lower()}" if z.get("subtype") else ""
    if z.get("sfha") == "T":
        return f"Zone {z['zone']}{sub} (Special Flood Hazard Area: the 1% annual chance flood)"
    if z.get("zone") == "X" and z.get("subtype") in FLOOD_SHADED_X:
        return f"Zone X{sub} (moderate flood hazard)"
    if z.get("zone") == "X":                     # a subtype FEMA didn't give, or one Gordium doesn't know: no hazard claimed
        return f"Zone X{sub} (outside the Special Flood Hazard Area)"
    if z.get("zone") == "D":
        return "Zone D (possible but undetermined flood hazard)"
    return f"Zone {z.get('zone') or 'not given'}{sub}"


def _flood(f: Fetcher, ring) -> list[str]:
    """FEMA's flood zones on the lot, as overlay lines ([] only when FEMA positively says none). None is said only when
    every zone touching the lot (and 2 ft around it) is Zone X unshaded, the whole lot lies inside one such zone (no
    unmapped part, no second zone), and no pending or preliminary new map covers it. A service that doesn't answer, a
    lot FEMA hasn't mapped, or one that straddles two areas can't be told: the row stays (principle 4)."""
    label = "FEMA flood zone"
    try:
        touching = f.flood_zones(ring, margin_ft=FLOOD_MARGIN_FT)
        if not touching:
            return [f"{label}: couldn't tell (FEMA's flood map shows no zone here)"]
        named = sorted({_flood_name(z) for z in touching if (z["zone"], z["subtype"], z["sfha"]) != FLOOD_NONE})
        if named:                                            # any part of the lot, however small, counts
            return [f"{label}: {n}" for n in named]
        inside = f.flood_zones(ring, within=True, margin_ft=FLOOD_MARGIN_FT)
        if not any((z["zone"], z["subtype"], z["sfha"]) == FLOOD_NONE for z in inside):
            return [f"{label}: couldn't tell (the lot isn't wholly inside one area FEMA maps as minimal flood hazard)"]
        for key, kind in (("fema_pending", "pending"), ("fema_preliminary", "preliminary")):
            if f.flood_study_here(key, ring, margin_ft=FLOOD_MARGIN_FT):
                return [f"{label}: couldn't tell (a {kind} new FEMA flood map covers this lot)"]
        return []
    except (Offline, ServiceError, KeyError, TypeError, AttributeError):   # down, or an answer not as expected:
        return [f"{label}: couldn't check (FEMA's flood map didn't answer)"]   # never the whole lookup lost


USED_LIVE = "(used live, not stored)"


def stored_value(value, store: str):
    """What a project may keep of a value, by its source's `store` in endpoints.yaml: raw keeps it; derived
    keeps only numbers Gordium computed (areas, lengths: plain numbers or a flat list of them, never an
    outline, a position or the source's own words); none keeps nothing."""
    if store == "raw" or value is None:
        return value
    if store == "derived" and isinstance(value, dict):
        kept = {k: v for k, v in value.items() if k in DERIVED_NUMBERS}
        return kept or USED_LIVE
    return USED_LIVE


DERIVED_NUMBERS = {"area_sf", "edge_lengths_ft", "tolerance_ft", "min_ft", "max_ft"}
STRICTNESS = {"raw": 0, "derived": 1, "none": 2}


def strictest(keys) -> str:
    """The store policy that holds for something worked out from all these sources."""
    return max((ENDPOINTS[k]["store"] for k in keys if k), key=STRICTNESS.get, default="raw")


def snapshot(result: dict, working: dict, f: Fetcher) -> dict:
    """What a project keeps: the facts Gordium may store, and for every source the URL, date and SHA-256.
    Each value, reason and note is kept only as far as the strictest source it was worked out from allows."""
    kept, details = {}, {}
    for k, v in result["facts"].items():
        w = working[k]
        store = strictest(w["source_keys"])
        kept[k] = {**v, "value": stored_value(v["value"], store)}
        d = {"status": w["status"], "source_url": w["source_url"], "source_keys": w["source_keys"],
             # the description can carry a source's own data (the zoning map's edit date): names only then
             "source_detail": w["source_detail"] if store == "raw" else
             " + ".join(ENDPOINTS[s]["name"] for s in w["source_keys"])}
        reasons = [r for r, key in w["_reasons"] if strictest(w["source_keys"] + [key]) == "raw"]
        if reasons:
            d["reason"] = " ".join(reasons)
        if w.get("note") and store == "raw":
            d["note"] = w["note"]
        details[k] = d
    body = {"query": result["query"], "status": result["status"], "facts": kept, "details": details,
            "sources": f.records, "fetched": f.now.isoformat()}
    body["fingerprint"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    return body
