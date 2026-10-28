"""One function per question asked of a public service. Each call is recorded (which source, URL, when,
SHA-256 of the response, what may be stored) so a project's snapshot says exactly what was used."""

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import yaml

from . import geometry as g

ENDPOINTS = yaml.safe_load((Path(__file__).parent / "endpoints.yaml").read_text(encoding="utf-8"))
SR = 2261                                   # NAD83 / New York Central, US survey feet
M_TO_FT = 1 / 0.3048                        # elevations: metres to international feet

_SUFFIX = {"STREET": "ST", "ROAD": "RD", "AVENUE": "AVE", "PLACE": "PL", "LANE": "LN", "DRIVE": "DR",
           "COURT": "CT", "BOULEVARD": "BLVD", "TERRACE": "TER", "CIRCLE": "CIR", "PARKWAY": "PKWY",
           "HIGHWAY": "HWY", "SQUARE": "SQ", "ALLEY": "ALY", "TRAIL": "TRL"}
_DIR = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}


def normalize_street(name: str) -> str:
    """'South Cayuga Street' -> 'S CAYUGA ST'; 'Ithaca Road' -> 'ITHACA RD' (how the City writes them)."""
    words = re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper()).split()
    if words and words[0] in _DIR and len(words) > 1:
        words[0] = _DIR[words[0]]
    if words and words[-1] in _SUFFIX:
        words[-1] = _SUFFIX[words[-1]]
    return " ".join(words)


class Fetcher:
    """Asks the services, through an Http-like object (`post(url, params) -> (json, raw)`), and keeps a record
    of every answer it used."""

    def __init__(self, http, now: dt.datetime | None = None):
        self.http = http
        self.now = now or dt.datetime.now(dt.timezone.utc)
        self.records: list[dict] = []

    def _ask(self, key: str, params: dict, url: str | None = None) -> dict:
        ep = ENDPOINTS[key]
        url = url or ep["url"]
        body, raw = self.http.post(url, params)
        self.records.append({"source": key, "name": ep["name"], "url": url, "fetched": self.now.isoformat(),
                             "sha256": hashlib.sha256(raw).hexdigest(), "store": ep["store"]})
        return body

    # ---- address -------------------------------------------------------------------------------------

    def geocode(self, address: str) -> list[dict]:
        body = self._ask("geocoder", {"SingleLine": address, "outSR": SR, "maxLocations": 6,
                                      "outFields": "Addr_type,AddNum,StPreDir,StName,StType,City,Region,Subregion,Postal"})
        out = []
        for c in body.get("candidates", []):
            a = c.get("attributes", {})
            street = normalize_street(" ".join(x for x in (a.get("StPreDir"), a.get("StName"), a.get("StType")) if x))
            out.append({"label": c.get("address", ""), "point": (c["location"]["x"], c["location"]["y"]),
                        "score": c.get("score", 0), "type": a.get("Addr_type", ""), "number": str(a.get("AddNum") or ""),
                        "street": street, "city": a.get("City", ""), "county": a.get("Subregion", "")})
        return out

    def county_point(self, number: str, street: str) -> tuple[float, float] | None:
        """The County's address point for this address (a cross-check; never stored)."""
        full = f"{number} {street}".replace("'", "''")
        body = self._ask("address_points", {"where": f"FullAddr = '{full}'", "outFields": "FullAddr,MsagCom",
                                            "returnGeometry": "true", "outSR": SR})
        feats = body.get("features", [])
        return (feats[0]["geometry"]["x"], feats[0]["geometry"]["y"]) if feats else None

    # ---- parcels ---------------------------------------------------------------------------------------

    def _point_query(self, p) -> dict:
        return {"geometry": json.dumps({"x": p[0], "y": p[1]}), "geometryType": "esriGeometryPoint", "inSR": SR,
                "spatialRel": "esriSpatialRelIntersects", "returnGeometry": "true", "outSR": SR}

    def city_parcels_at(self, p) -> list[dict]:
        body = self._ask("city_parcels", {**self._point_query(p),
                                          "outFields": "SWISPRINTK,SWIS,MUNI,LOCADDR,SecZones,HISTPROP,ILPCREVIEW"})
        out = []
        for f in body.get("features", []):
            a = f["attributes"]
            out.append({"id": a.get("SWISPRINTK"), "swis": str(a.get("SWIS") or ""), "muni": a.get("MUNI") or "",
                        "address": a.get("LOCADDR") or "", "rings": [g.open_ring(r) for r in f["geometry"]["rings"]],
                        "secondary_zones": a.get("SecZones"), "historic_property": a.get("HISTPROP"),
                        "landmarks_review": a.get("ILPCREVIEW"), "source": "city_parcels"})
        return out

    def state_parcels_at(self, p) -> list[dict]:
        body = self._ask("state_parcels", {**self._point_query(p),
                                           "outFields": "SWIS,PRINT_KEY,MUNI_NAME,CITYTOWN_NAME,PARCEL_ADDR"})
        out = []
        for f in body.get("features", []):
            a = f["attributes"]
            swis = str(a.get("SWIS") or "")
            out.append({"id": f"{swis}-{a.get('PRINT_KEY')}", "swis": swis,
                        "muni": (a.get("CITYTOWN_NAME") or a.get("MUNI_NAME") or "").upper(),
                        "address": a.get("PARCEL_ADDR") or "", "rings": [g.open_ring(r) for r in f["geometry"]["rings"]],
                        "secondary_zones": None, "historic_property": None, "landmarks_review": None,
                        "source": "state_parcels"})
        return out

    # ---- streets ---------------------------------------------------------------------------------------

    def _envelope(self, ring, pad) -> dict:
        x0, y0, x1, y1 = g.bounds(ring, pad)
        return {"geometry": f"{x0},{y0},{x1},{y1}", "geometryType": "esriGeometryEnvelope", "inSR": SR,
                "spatialRel": "esriSpatialRelIntersects", "returnGeometry": "true", "outSR": SR}

    def city_roads_near(self, ring, pad: float = 150.0) -> list[dict]:
        body = self._ask("city_roads", {**self._envelope(ring, pad), "outFields": "NAME,ROW_WIDTH"})
        return [{"name": normalize_street(f["attributes"].get("NAME") or ""), "row_ft": f["attributes"].get("ROW_WIDTH"),
                 "paths": [[tuple(p[:2]) for p in path] for path in f["geometry"]["paths"]], "source": "city_roads"}
                for f in body.get("features", []) if f.get("geometry")]

    def state_streets_near(self, ring, pad: float = 150.0) -> list[dict]:
        body = self._ask("state_streets", {**self._envelope(ring, pad), "outFields": "CompleteStreetName"})
        return [{"name": normalize_street(f["attributes"].get("CompleteStreetName") or ""), "row_ft": None,
                 "paths": [[tuple(p[:2]) for p in path] for path in f["geometry"]["paths"]], "source": "state_streets"}
                for f in body.get("features", []) if f.get("geometry")]

    # ---- the context map: everything in a square around the lot (context.py) ---------------------------

    def in_box(self, key: str, box, fields: str, page: int = 1000, cap: int = 5000) -> tuple[list[dict], bool]:
        """Every feature of a layer meeting the box (x0, y0, x1, y1, EPSG:2261), page by page in OBJECTID order
        (a service answers at most its maxRecordCount at a time and says `exceededTransferLimit` when there is
        more). (features, complete): complete is False when `cap` features were reached and more were left."""
        x0, y0, x1, y1 = box
        base = {"geometry": f"{x0},{y0},{x1},{y1}", "geometryType": "esriGeometryEnvelope", "inSR": SR,
                "spatialRel": "esriSpatialRelIntersects", "returnGeometry": "true", "outSR": SR, "outFields": fields,
                "geometryPrecision": 2, "orderByFields": "OBJECTID", "resultRecordCount": page}
        out: list[dict] = []
        offset = 0
        while True:
            body = self._ask(key, {**base, "resultOffset": offset})
            feats = body.get("features") or []
            offset += len(feats)
            out += [f for f in feats if f.get("geometry")]
            if not (body.get("exceededTransferLimit") and feats):
                return out, True
            if offset >= cap:
                return out, False

    # ---- zoning and overlays (live only) --------------------------------------------------------------

    def zoning_near(self, ring) -> list[dict]:
        body = self._ask("city_zoning", {**self._envelope(ring, 0.0), "outFields": "ZONE"})
        return [{"zone": f["attributes"].get("ZONE"), "rings": [g.open_ring(r) for r in f["geometry"]["rings"]]}
                for f in body.get("features", []) if f.get("geometry")]

    def zoning_last_edited(self) -> dt.date | None:
        body = self._ask("city_zoning", {}, url=ENDPOINTS["city_zoning"]["layer"])
        ms = (body.get("editingInfo") or {}).get("dataLastEditDate")
        return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date() if ms else None

    def overlays(self, key: str, field: str, ring) -> list[str]:
        geom = {"rings": [[list(p) for p in ring + ring[:1]]], "spatialReference": {"wkid": SR}}
        body = self._ask(key, {"geometry": json.dumps(geom), "geometryType": "esriGeometryPolygon", "inSR": SR,
                               "spatialRel": "esriSpatialRelIntersects", "returnGeometry": "false", "outFields": field})
        return sorted({str(f["attributes"].get(field)) for f in body.get("features", []) if f["attributes"].get(field)})

    # ---- ground ----------------------------------------------------------------------------------------

    def elevations_ft(self, points) -> list[float | None]:
        geom = {"points": [list(p) for p in points], "spatialReference": {"wkid": SR}}
        body = self._ask("elevation", {"geometry": json.dumps(geom), "geometryType": "esriGeometryMultipoint",
                                       "returnFirstValueOnly": "true", "interpolation": "RSP_BilinearInterpolation"})
        by_id = {s.get("locationId"): s.get("value") for s in body.get("samples", [])}
        out = []
        for i in range(len(points)):
            v = by_id.get(i)
            try:
                out.append(float(v) * M_TO_FT if v not in (None, "", "NoData") else None)
            except (TypeError, ValueError):
                out.append(None)
        return out
