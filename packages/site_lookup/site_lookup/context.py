"""The context map: what surrounds the lot, in a square around it (1500 ft × 1500 ft by default), as an architect's
site context drawing shows it: the neighbouring parcels, the street centerlines and the neighbouring buildings.
Plain code asking the same public services through the same Fetcher (every answer recorded: source, URL, date,
SHA-256, store policy); no AI. Nothing here is ever measured or checked: it is drawing context only.

    context(lot_ring, http)    lot_ring: the lot's outline in EPSG:2261 (US survey feet), as the services give it

Each layer comes back with its source and that source's `store` (endpoints.yaml): the Rhino side writes into the
.3dm only the layers whose store is `raw` (parcels, streets and, since Ben's decision of 2026-10-21, the building
footprints, as editable outlines) and shows any other live, never saved (the general path for a source that may not
be kept). Coordinates are Gordium's feet from `origin` (the lot's
centroid, as the lookup's lot outline), so the lookup's placement in the model applies to them unchanged.
"""

import datetime as dt
import hashlib
import json

from . import geometry as g
from .http import Offline, ServiceError
from .lookup import US_SURVEY_FT
from .sources import ENDPOINTS, Fetcher

LIVE_ONLY = "shown live, not saved in this file."

HALF_SIZE_FT = 750.0                       # half the square's side: 1500 ft × 1500 ft
LAYERS = {                                 # name: (endpoints.yaml source, the only fields asked for)
    "parcels": ("state_parcels", "SWIS,PRINT_KEY"),          # never owner, mailing or value fields
    "streets": ("state_streets", "CompleteStreetName"),
    "buildings": ("state_buildings", "OBJECTID,SourceDate,NYSGeo_Source"),    # the id: an edited outline is known
                                                                                # on redraw; the source: ODbL is left out
}
PARCEL_NOTE = ("Tax parcels: NYS Tax Parcels Public (from Tompkins County Real Property): for planning and general "
               "use only, not a substitute for a legal parcel survey.")


def context(lot_ring, http, half_size_ft: float = HALF_SIZE_FT, origin=None, now: dt.datetime | None = None,
            layers=tuple(LAYERS), lot_id: str | None = None) -> dict:
    """The parcels, streets and buildings in a square of 2 × half_size_ft (international feet) around the lot's
    centroid. The lot's own parcel is left out (it is the lot): the one with the lookup's parcel id `lot_id`
    (SWIS-PRINT_KEY), or without one the parcel under the centroid (a concave lot's centroid can fall outside it, so
    the id is the one to give). Each layer is asked on its own, so one service down leaves the others."""
    f = Fetcher(http, now)
    ring = g.open_ring(lot_ring)
    centre = tuple(origin) if origin else tuple(round(v, 2) for v in g.centroid(ring))
    half = half_size_ft / US_SURVEY_FT                     # the services' survey feet
    box = (centre[0] - half, centre[1] - half, centre[0] + half, centre[1] + half)

    def feet(p):
        return [round((p[0] - centre[0]) * US_SURVEY_FT, 2), round((p[1] - centre[1]) * US_SURVEY_FT, 2)]

    out = {"status": "found", "message": "", "half_size_ft": half_size_ft, "origin_epsg2261_us_survey_ft": list(centre),
           "fetched": f.now.isoformat(), "layers": {}}
    for name in layers:
        key, fields = LAYERS[name]
        layer = {"source": key, "name": ENDPOINTS[key]["name"], "store": ENDPOINTS[key]["store"], "status": "found",
                 "items": []}
        out["layers"][name] = layer
        try:
            feats, complete = f.in_box(key, box, fields)
        except Offline as e:
            layer.update(status="offline", message=f"Couldn't reach {layer['name']}.", detail=str(e))
            continue
        except (ServiceError, KeyError, TypeError, ValueError) as e:
            layer.update(status="error", message=f"{layer['name']} answered with an error.",
                         detail=f"{type(e).__name__}: {e}")
            continue
        if not complete:
            layer.update(status="partial", message=f"Only the first {len(feats)} of {layer['name']} were drawn.")
        if name == "buildings":                  # only footprints from a source reviewed for keeping (allow-list)
            feats, left = cleared(feats)
            if left:
                layer["message"] = (layer.get("message", "") + " %d footprint%s left out: %s source (%s) isn't "
                                    "cleared for keeping in your file." % (
                                        len(left), "s" if len(left) != 1 else "", "their" if len(left) != 1 else "its",
                                        ", ".join(sorted(set(left))))).strip()
        try:
            layer["items"] = _items(name, feats, box, centre, feet, lot_id)
        except (KeyError, TypeError, ValueError, IndexError) as e:     # a malformed answer: that layer, not a crash
            layer.update(status="error", items=[], message=f"{layer['name']} answered with something unreadable.",
                         detail=f"{type(e).__name__}: {e}")
            continue
        if name == "buildings":
            dates = sorted({str((ft.get("attributes") or {}).get("SourceDate")) for ft in feats
                            if (ft.get("attributes") or {}).get("SourceDate")})
            layer["dates"] = dates
    found = [n for n, v in out["layers"].items() if v["status"] in ("found", "partial")]
    if not found:
        states = {v["status"] for v in out["layers"].values()}
        out.update(status="offline" if states == {"offline"} else "error",
                   message="Couldn't fetch the neighbourhood: the lot is drawn without it.")
    else:                     # every layer's word reaches the architect: a failure, a partial answer, left-out data
        out["message"] = " ".join(v["message"] for v in out["layers"].values() if v.get("message"))
    out["credits"] = list(credits(out).values())
    out["snapshot"] = snapshot(out, f)
    return out


def cleared(feats) -> tuple[list, list]:
    """(footprints kept, the sources of those left out): only footprints whose NYSGeo_Source is in endpoints.yaml's
    reviewed_sources are kept, any other is left out (review of the editable outlines, P2: an exact "Microsoft" match
    let "NYS Geospatial Services - previously, Microsoft", still ODbL, through)."""
    reviewed = {str(s).strip().lower() for s in ENDPOINTS["state_buildings"].get("reviewed_sources") or []}
    kept, left = [], []
    for ft in feats:
        source = str((ft.get("attributes") or {}).get("NYSGeo_Source") or "").strip()
        if source.lower() in reviewed:
            kept.append(ft)
        else:
            left.append(source or "unknown")
    return kept, left


def _items(name, feats, box, centre, feet, lot_id=None) -> list[dict]:
    items = []
    if name == "parcels":
        for ft in feats:
            a = ft.get("attributes") or {}
            pid = f"{a.get('SWIS')}-{a.get('PRINT_KEY')}"
            rings = [g.open_ring(r) for r in ft["geometry"]["rings"]]
            if (pid == lot_id) if lot_id else g.inside_any(centre, rings):
                continue                                     # the lot itself
            for k, r in enumerate(rings):
                clipped = g.clip_ring(r, box)
                if clipped:                       # each ring its own id (one edited ring never hides its siblings)
                    items.append({"id": pid if k == 0 else "%s #%d" % (pid, k + 1), "name": pid,
                                  "ring": [feet(p) for p in clipped]})
    elif name == "streets":
        seen: dict[str, int] = {}
        for ft in feats:
            street = ((ft.get("attributes") or {}).get("CompleteStreetName") or "").strip()
            for path in ft["geometry"]["paths"]:
                for piece in g.clip_path([tuple(p[:2]) for p in path], box):
                    seen[street] = seen.get(street, 0) + 1            # an id per piece (an edited one is known on redraw)
                    items.append({"id": "%s #%d" % (street, seen[street]), "name": street,
                                  "path": [feet(p) for p in piece]})
    else:
        for ft in feats:
            oid = (ft.get("attributes") or {}).get("OBJECTID")
            for k, r in enumerate(ft["geometry"]["rings"]):
                clipped = g.clip_ring(g.open_ring(r), box)
                if clipped:                       # each ring its own id (one edited ring never hides its siblings)
                    base = "footprint-%s" % oid if oid is not None else ""
                    items.append({"id": base if k == 0 or not base else "%s #%d" % (base, k + 1),
                                  "ring": [feet(p) for p in clipped]})
    return items


def credits(out: dict) -> dict[str, str]:
    """The source line a context drawing carries for each layer drawn (by layer name)."""
    lines = {}
    for name, layer in out["layers"].items():
        if layer["status"] not in ("found", "partial") or not layer["items"]:
            continue
        if name == "parcels":
            lines[name] = PARCEL_NOTE
        elif name == "streets":
            lines[name] = "Street centerlines: NYS Streets (NYS ITS Geospatial Services)."
        else:
            when = ", ".join(layer.get("dates") or []) or "date unknown"
            line = ENDPOINTS[layer["source"]].get("attribution") or layer["name"]
            lines[name] = f"{line}; footprints dated {when}" + \
                (": " + LIVE_ONLY if layer["store"] != "raw" else ".")
    return lines


def live_credit(layer: dict) -> str:
    """A live-only layer's credit line as the drawing's Sources note keeps it: its attribution from endpoints.yaml
    (Gordium's own words, so it may be kept), never anything from its answers (the footprints' date is the source's
    data: store none, so it is said on screen only)."""
    return ENDPOINTS[layer["source"]].get("attribution") or layer["name"]


def snapshot(out: dict, f: Fetcher) -> dict:
    """What a project keeps of the context besides the drawn objects: per layer its source, status and count, and
    for every request the URL, date and SHA-256 (never an answer). A layer's credit line is kept only if its source
    may be kept (the footprints' line carries their dates); one used live is only named."""
    # a count is a number worked out from the answer: kept only for a source that may be kept (review round 2)
    layers = {n: {"source": v["source"], "status": v["status"], "store": v["store"],
                  **({"count": len(v["items"])} if v["store"] == "raw" else {})}
              for n, v in out["layers"].items()}
    kept = [line if out["layers"][n]["store"] == "raw" else f"{live_credit(out['layers'][n])}: {LIVE_ONLY}"
            for n, line in credits(out).items()]
    body = {"half_size_ft": out["half_size_ft"], "origin_epsg2261_us_survey_ft": out["origin_epsg2261_us_survey_ft"],
            "status": out["status"], "layers": layers, "sources": f.records, "fetched": out["fetched"],
            "credits": kept}
    body["fingerprint"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    return body
