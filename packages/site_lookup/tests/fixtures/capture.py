"""Re-capture the test fixtures from the live services (run by hand, never in CI):

    PYTHONPATH=packages/site_lookup python packages/site_lookup/tests/fixtures/capture.py

What is saved, per address: only the answers of the sources whose terms allow storing them (endpoints.yaml
`store: raw`): the NYS Geocoder, NYS Tax Parcels, NYS Streets and USGS 3DEP. Nothing from the City or County
layers (`store: none` / `derived`): the tests' stand-ins for those are synthetic (test_lookup.py).

The stand-in for the City's roads is built from the NYS Streets centerlines near the lot. The lookup only asks
NYS Streets when the City's roads fail, so for a City lot capture() asks for them explicitly, with exactly the
request the lookup's fallback makes (test_capture_records_what_the_fake_replays checks the two agree).
"""

import datetime as dt
import json
from pathlib import Path

from site_lookup import geometry as g
from site_lookup.http import Http
from site_lookup.lookup import CITY_SWIS, lookup
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


def capture(address: str, http) -> dict:
    """One fixture: every storable answer the lookup gets, plus the NYS Streets near a City lot."""
    rec = Recording(http)
    result = lookup(address, rec)                    # every request the lookup makes, as it makes it
    f = Fetcher(rec)
    cands = [c for c in f.geocode(address) if c["type"] == "PointAddress" and c["score"] >= 90]
    if cands:
        parcels = [p for p in f.state_parcels_at(cands[0]["point"]) if p["swis"] == CITY_SWIS]
        if parcels:
            f.state_streets_near(max(parcels[0]["rings"], key=g.area))
    return {"address": address, "captured": dt.date.today().isoformat(), "answers": rec.saved,
            "live_status": result["status"]}


def main():
    for name, address in ADDRESSES.items():
        fixture = capture(address, Http())
        (HERE / f"{name}.json").write_text(json.dumps(fixture, indent=1))
        print(name, len(fixture["answers"]), "answers saved")


if __name__ == "__main__":
    main()
