"""Re-capture the test fixtures from the live services (run by hand, never in CI):

    PYTHONPATH=packages/site_lookup python packages/site_lookup/tests/fixtures/capture.py

What is saved, per address:
- the real answers of the sources whose terms allow storing them (endpoints.yaml `store: raw`): the NYS
  Geocoder, NYS Tax Parcels, NYS Streets and USGS 3DEP;
- for the City and County layers (`store: none` / `derived`), only numbers derived from them: the
  right-of-way width of each State street segment (from the nearest City road of the same name), the zone
  code at the lot and the zoning map's last-edit date. The tests build stand-in City answers from these.
"""

import datetime as dt
import json
import math
from pathlib import Path

from site_lookup import geometry as g
from site_lookup.http import Http
from site_lookup.lookup import lookup
from site_lookup.sources import ENDPOINTS, Fetcher

HERE = Path(__file__).parent
ADDRESSES = {"106_ithaca_rd": "106 Ithaca Rd, Ithaca, NY 14850",
             "109_ithaca_rd": "109 Ithaca Rd, Ithaca, NY 14850",
             "96_ithaca_rd": "96 Ithaca Rd, Ithaca, NY 14850",
             "953_danby_rd_town": "953 Danby Rd, Ithaca, NY 14850",
             "not_found": "12345 Nowhere Blvd, Ithaca, NY 14850"}


class Recording:
    """Passes requests through, keeping the answers of sources whose terms allow storing them."""

    def __init__(self, http):
        self.http, self.saved = http, []

    def post(self, url, params):
        body, raw = self.http.post(url, params)
        key = next((k for k, e in ENDPOINTS.items() if url in (e["url"], e.get("layer"))), None)
        if key and ENDPOINTS[key]["store"] == "raw":
            self.saved.append({"source": key, "params": params, "body": body})
        return body, raw


def main():
    for name, address in ADDRESSES.items():
        rec = Recording(Http())
        result = lookup(address, rec)                # every request the lookup makes, as it makes it
        f = Fetcher(rec)
        fixture = {"address": address, "captured": dt.date.today().isoformat(), "answers": rec.saved,
                   "live_status": result["status"]}
        cands = [c for c in f.geocode(address) if c["type"] == "PointAddress"]
        if cands:
            parcels = f.state_parcels_at(cands[0]["point"])
            if parcels and parcels[0]["swis"] == "500700":
                ring = max(parcels[0]["rings"], key=g.area)
                streets = f.state_streets_near(ring)
                roads = f.city_roads_near(ring)
                widths = []
                for s in streets:                  # derived: ROW of the nearest City road with that name
                    same = [r for r in roads if r["name"] == s["name"] and r["paths"] and r["row_ft"]]
                    mid = s["paths"][0][len(s["paths"][0]) // 2]
                    near = min(same, key=lambda r: min(g.polyline_distance(mid, p) for p in r["paths"]), default=None)
                    widths.append(near["row_ft"] if near else None)
                zones = f.zoning_near(ring)
                c = g.centroid(ring)
                fixture["derived"] = {
                    "state_street_row_ft": widths,
                    "zone_at_lot": next((z["zone"] for z in zones if g.inside_any(c, z["rings"])), None),
                    "zoning_last_edited": str(f.zoning_last_edited()),
                    "note": "Derived from City of Ithaca layers (not stored): ROW widths, zone code, edit date."}
        (HERE / f"{name}.json").write_text(json.dumps(fixture, indent=1))
        print(name, len(rec.saved), "answers saved")


if __name__ == "__main__":
    main()
