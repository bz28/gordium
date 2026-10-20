"""Address in, site facts out: the lot, which side faces the street, whether it's a corner lot, the ground,
and a zoning suggestion. Each fact is {value, source, confirmed_by, date}, exactly the shape the start box
stores, so a looked-up fact and one the architect types are treated alike. source is one of the start box's
labels: "from tax map" for the lot (approximate: ±2'-0" downstream), "suggested by Gordium" for the rest.
Beside each fact, result["details"][name] says how sure the lookup is and where the answer came from:
{status, reason?, note?, source_detail, source_url, source_key} (source_key: the endpoints.yaml source,
which decides what a project's snapshot may keep).

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

from . import geometry as g
from .http import Offline, ServiceError
from .sources import ENDPOINTS, Fetcher, normalize_street

AMENDMENTS = yaml.safe_load((Path(__file__).parent / "amendments.yaml").read_text())
CITY_SWIS = "500700"                     # the City of Ithaca (the Town of Ithaca has its own code and SWIS)
PLACES = {"503089": "Town of Ithaca", "503000": "Town of Ithaca"}   # neighbours named in the refusal
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
         label: str = SUGGESTED, key: str = "") -> dict:
    """A fact with its details while the lookup runs; lookup() splits the details off at the end. key is the
    endpoints.yaml source the value came from: it decides what a project's snapshot may keep."""
    out = {"value": value, "source": label, "confirmed_by": None, "date": date,
           "status": "suggested", "source_detail": source, "source_url": url, "source_key": key}
    if note:
        out["note"] = note
    return escalate(out, status, reason)


def escalate(f: dict, status: str, reason: str = "") -> dict:
    """Raise a fact's status to `status` if that's stronger (ask > needs review > suggested), and add the
    reason to the ones it has. A fact whose evidence is incomplete is never left 'suggested'."""
    if RANK[status] > RANK[f["status"]]:
        f["status"] = status
    if reason and reason not in f.get("reason", ""):
        f["reason"] = f"{f['reason']} {reason}" if f.get("reason") else reason
    return f


def lookup(address: str, http, now: dt.datetime | None = None) -> dict:
    f = Fetcher(http, now)
    today = f.now.date().isoformat()
    result = {"query": address, "status": "found", "message": "", "facts": {}, "asks": []}
    try:
        _lookup(address, f, today, result)
    except Offline as e:
        result.update(status="offline", message="Couldn't reach the map services (offline?): enter the site by hand.",
                      detail=str(e))
    except (ServiceError, KeyError, TypeError, ValueError, IndexError) as e:
        result.update(status="error", message="A map service answered with an error: enter the site by hand.",
                      detail=f"{type(e).__name__}: {e}")
    result["details"] = {k: {d: v[d] for d in DETAIL_KEYS if d in v} for k, v in result["facts"].items()}
    result["facts"] = {k: {d: v[d] for d in FACT_KEYS} for k, v in result["facts"].items()}
    result["snapshot"] = snapshot(result, f)
    return result


FACT_KEYS = ("value", "source", "confirmed_by", "date")
DETAIL_KEYS = ("status", "reason", "note", "source_detail", "source_url", "source_key")


def _lookup(address: str, f: Fetcher, today: str, result: dict) -> None:
    facts, asks = result["facts"], result["asks"]
    # ---- 1. address -> point ---------------------------------------------------------------------------
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
    addr_status, addr_reason = ("suggested", "") if c["type"] == "PointAddress" else (
        "needs_review", "Found only along the street, not at a building: check the lot it picked.")
    if unplaced:
        addr_status, addr_reason = "needs_review", (
            f"Another match ({'; '.join(unplaced)}) couldn't be placed on a parcel: check this is the right address.")
    try:
        cp = f.county_point(c["number"], c["street"])
        if cp and math.dist(cp, c["point"]) > COUNTY_POINT_TOLERANCE_FT:
            addr_status, addr_reason = "needs_review", (
                f"The State and County place this address {math.dist(cp, c['point']):.0f} ft apart: check the lot.")
    except (Offline, ServiceError):
        pass                                                   # a cross-check only; the State point stands
    facts["address"] = fact(c["label"], ENDPOINTS["geocoder"]["name"], ENDPOINTS["geocoder"]["url"], today,
                            addr_status, addr_reason, key="geocoder")
    # ---- 2. point -> parcel (the State copy is the stored outline; the City's adds City-only flags) ---------
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
    in_city = [p for p in parcels if p["swis"] == CITY_SWIS]
    if not in_city:
        swis = parcels[0]["swis"]
        where = PLACES.get(swis, f"municipality SWIS {swis}")
        result.update(status="outside_city", message=f"This address is in the {where}, not the City of Ithaca. "
                      "Gordium's rules cover the City of Ithaca only.")
        return
    if len({p["id"] for p in in_city}) > 1:
        result.update(status="multiple", message="The address sits on more than one parcel: pick the lot.",
                      matches=sorted({p["id"] for p in in_city}))
        return
    parcel = in_city[0]
    city_parcel = next((p for p in city if p["id"] == parcel["id"]), None)
    ring = max(parcel["rings"], key=g.area)
    lot_status, lot_reason = ("suggested", "") if addr_status == "suggested" else (
        "needs_review", "The address point is doubtful, so this may be the wrong lot: " + addr_reason)
    if len(parcel["rings"]) > 1:
        lot_status, lot_reason = "needs_review", "This parcel has more than one piece: check the lot outline."
    origin = tuple(round(v, 2) for v in g.centroid(ring))
    outline = [[round((x - origin[0]) * US_SURVEY_FT, 2), round((y - origin[1]) * US_SURVEY_FT, 2)] for x, y in ring]
    src = ENDPOINTS[parcel["source"]]
    facts["parcel"] = fact(parcel["id"], src["name"], src["url"], today, *(
        ("suggested",) if addr_status == "suggested" else ("needs_review", lot_reason)), key=parcel["source"])
    facts["lot"] = fact({"outline_ft": outline, "area_sf": round(g.area(ring) * US_SURVEY_FT ** 2, 1),
                         "edge_lengths_ft": [round(math.dist(a, b) * US_SURVEY_FT, 2) for a, b in g.edges(ring)],
                         "origin_epsg2261_us_survey_ft": list(origin), "tolerance_ft": TAX_MAP_TOLERANCE_FT},
                        f"{src['name']} (tax map, approximate ±{TAX_MAP_TOLERANCE_FT:.0f} ft)", src["url"], today,
                        lot_status, lot_reason, label=FROM_TAX_MAP, key=parcel["source"],
                        note="outline_ft: international feet from the centroid (EPSG:2261 US survey feet × "
                             f"{US_SURVEY_FT:.7f}). " + (src.get("attribution") or f"Terms: {src['terms']}"))
    # ---- 3. which lines face a street ------------------------------------------------------------------
    _streets(f, ring, c["street"], today, facts, asks)
    # ---- 4. ground --------------------------------------------------------------------------------------
    _ground(f, ring, origin, today, facts)
    # ---- 5. zoning suggestion and overlays (live, never stored) --------------------------------------------
    _zoning(f, ring, c["street"], facts, asks, today, city_parcel)


def _distinct(cands: list[dict]) -> list[dict]:
    """Candidates at different places (the geocoder repeats one match several times)."""
    out: list[dict] = []
    for c in sorted(cands, key=lambda c: -c["score"]):
        if not any(math.dist(c["point"], o["point"]) < 30 for o in out):
            out.append(c)
    return out


def _streets(f: Fetcher, ring, address_street: str, today: str, facts: dict, asks: list) -> None:
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
                                        "Couldn't reach the road maps: pick the front lot line.", key=key)
            facts["corner_lot"] = fact("ask", "—", "", today, "ask", "Is this a corner lot?", key=key)
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
                                    "No street found along this lot: pick the front lot line.", key=key)
        facts["corner_lot"] = fact("ask", src["name"], src["url"], today, "ask", "Is this a corner lot?", key=key)
        asks.append("No street found along this lot: pick the front lot line.")
        return
    names = sorted(streets, key=lambda n: (n != address_street, -streets[n]))
    front = names[0]
    value = {"street": front, "edges": edges_by[front], "frontage_ft": round(streets[front], 1),
             "streets": {n: {"edges": edges_by[n], "frontage_ft": round(streets[n], 1)} for n in names}}
    if len(names) > 1:
        facts["street_side"] = fact(value, src["name"], src["url"], today, "ask",
                                    f"This lot faces {len(names)} streets ({', '.join(names)}): pick the front.", key=key)
        facts["corner_lot"] = fact("ask", src["name"], src["url"], today, "ask",
                                   f"It faces {' and '.join(names)}: a corner lot (or a lot running through "
                                   "between two streets): confirm, and pick the front.", key=key)
        if unsure:
            escalate(facts["street_side"], "needs_review", unsure)
        asks.append(f"This lot faces two streets ({' and '.join(names[:2])}): pick the front.")
        return
    if address_street and front != address_street:
        facts["street_side"] = fact(value, src["name"], src["url"], today, "needs_review",
                                    f"The address is on {address_street}, but the lot only touches {front}: "
                                    "check the front lot line.", key=key)
        asks.append(f"The address says {address_street}, but the lot faces {front}: check the front.")
    else:
        facts["street_side"] = fact(value, src["name"], src["url"], today, key=key)
    if unsure:                                   # one street found, but a second could have been missed
        escalate(facts["street_side"], "needs_review", unsure)
        facts["corner_lot"] = fact("ask", src["name"], src["url"], today, "ask",
                                   "Road widths weren't available: is this a corner lot?", key=key)
        asks.append("Road widths weren't available: check the street side and say if it's a corner lot.")
    else:
        facts["corner_lot"] = fact("no", src["name"], src["url"], today, key=key)


def _ground(f: Fetcher, ring, origin, today: str, facts: dict) -> None:
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
                               "Couldn't reach the elevation service: set the ground by hand.", key="elevation")
        return
    samples = [{"x": round((p[0] - origin[0]) * US_SURVEY_FT, 2), "y": round((p[1] - origin[1]) * US_SURVEY_FT, 2),
                "ft": round(e, 2)}
               for p, e in zip(pts, elev) if e is not None]
    if not samples:
        facts["ground"] = fact(None, src["name"], src["url"], today, "needs_review",
                               "No elevation data here: set the ground by hand.", key="elevation")
        return
    lo, hi = min(s["ft"] for s in samples), max(s["ft"] for s in samples)
    facts["ground"] = fact({"points": samples, "min_ft": lo, "max_ft": hi, "kind": "existing"},
                           f"{src['name']} · today's ground (existing), an estimate", src["url"], today,
                           note="Elevations in feet above NAVD88. Finished ground after construction is set in the start box.",
                           key="elevation")
    if len(samples) < len(pts):
        escalate(facts["ground"], "needs_review", f"Elevation missing at {len(pts) - len(samples)} of {len(pts)} "
                                                  "points: check the ground.")


def _zoning(f: Fetcher, ring, address_street: str, facts: dict, asks: list, today: str, city_parcel) -> None:
    src = ENDPOINTS["city_zoning"]
    try:
        polys = f.zoning_near(ring)
        edited = f.zoning_last_edited()
    except (Offline, ServiceError):
        facts["zone"] = fact(None, src["name"], src["url"], today, "needs_review",
                             "Couldn't reach the City's zoning map: choose the district.", key="city_zoning")
        _overlays(f, ring, city_parcel, src, today, facts)
        return
    samples = g.grid_inside(ring)
    counts: dict[str, int] = {}
    for p in samples:
        z = next((z["zone"] for z in polys if g.inside_any(p, z["rings"])), None)
        if z:
            counts[z] = counts.get(z, 0) + 1
    shares = {z: n / len(samples) for z, n in counts.items()} if samples else {}
    zones = sorted((z for z, s in shares.items() if s >= ZONE_SHARE_MIN), key=lambda z: -shares[z])
    when = edited.isoformat() if edited else "unknown"
    source = f"{src['name']}, last edited {when}: a suggestion to confirm"
    covered = sum(shares.values())
    if not zones:
        facts["zone"] = fact(None, source, src["url"], today, "needs_review",
                             "This lot isn't on the City's zoning map: choose the district.", key="city_zoning")
        _overlays(f, ring, city_parcel, src, today, facts)
        return
    z = facts["zone"] = fact(zones[0] if len(zones) == 1 else zones, source, src["url"], today, key="city_zoning")
    if covered < 0.9:
        escalate(z, "needs_review", f"Only {covered:.0%} of this lot is on the City's zoning map: check the district.")
    if len(zones) > 1:
        asks.append(f"This lot is in {' and '.join(zones)}: pick the zone that applies.")
        escalate(z, "ask", asks[-1])
    notes = []
    streets = {address_street} | set(((facts.get("street_side") or {}).get("value") or {}).get("streets", {}))
    for a in AMENDMENTS:
        adopted = a["adopted"] if isinstance(a["adopted"], dt.date) else dt.date.fromisoformat(str(a["adopted"]))
        if edited and adopted <= edited:
            continue
        line = (f"Ord. {a['ordinance']} ({a['title']}, adopted {adopted.isoformat()}) came after the City's map "
                f"was last edited ({when})")
        why = _amendment_reaches(a, ring, streets)
        if why:
            asks.append(f"{line} and {why}: check the current zoning map.")
            escalate(z, "needs_review", asks[-1])
        else:
            notes.append(line + "; this lot is outside the area it rezoned.")
    if notes:
        z["note"] = " ".join(notes)
    _overlays(f, ring, city_parcel, src, today, facts)


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


def _overlays(f: Fetcher, ring, city_parcel, src: dict, today: str, facts: dict) -> None:
    """Historic districts, gorge protection, secondary zones and landmark flags on the parcel. Not checked in
    this release, so any found (or any that couldn't be looked for) needs review."""
    found: list[str] = []
    for key, field, label in (("historic_districts", "DISTRICT", "Historic district"),
                              ("gorge_zones", "ZONE", "Gorge protection zone")):
        try:
            found += [f"{label}: {n}" for n in f.overlays(key, field, ring)]
        except (Offline, ServiceError):
            found.append(f"{label}: couldn't check")
    if not city_parcel:
        found.append("Historic property, landmarks review and secondary zones on the parcel: couldn't check "
                     "(the City's parcel layer didn't answer for this lot)")
    else:
        if city_parcel.get("secondary_zones"):
            found.append(f"Secondary zones on the parcel: {city_parcel['secondary_zones']}")
        if str(city_parcel.get("historic_property") or "").upper() == "YES":
            found.append("Historic property")
        if str(city_parcel.get("landmarks_review") or "").upper() == "YES":
            found.append("Landmarks Preservation Commission review")
    facts["overlays"] = fact(found, "City of Ithaca overlay maps (live)", src["url"], today,
                             "needs_review" if found else "suggested",
                             "Overlays aren't checked in this release: check these by hand." if found else "",
                             key="historic_districts")


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


DERIVED_NUMBERS = {"area_sf", "edge_lengths_ft", "tolerance_ft"}


def snapshot(result: dict, f: Fetcher) -> dict:
    """What a project keeps: the facts Gordium may store, and for every source the URL, date and SHA-256.
    Facts from sources whose terms don't allow storing are kept as 'used live' with no value."""
    kept, details = {}, {}
    for k, v in result["facts"].items():
        d = result["details"][k]
        store = ENDPOINTS[d["source_key"]]["store"] if d.get("source_key") else "raw"
        kept[k] = {**v, "value": stored_value(v["value"], store)}
        # a reason or note from a City source names what it found there (zones, streets): not kept
        details[k] = d if store == "raw" else {n: d[n] for n in ("status", "source_detail", "source_url",
                                                                  "source_key") if n in d}
    body = {"query": result["query"], "status": result["status"], "facts": kept, "details": details,
            "sources": f.records, "fetched": f.now.isoformat()}
    body["fingerprint"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    return body
