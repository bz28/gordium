"""The address lookup, offline: real recorded answers from the public State and USGS services (fixtures/,
made by capture.py), and stand-ins for the City and County layers built from numbers derived from them
(their terms don't allow storing their data)."""

import copy
import datetime as dt
import json
import os
from pathlib import Path

import pytest

import sys

from site_lookup import geometry as g
from site_lookup.http import Offline
from site_lookup.lookup import lookup
from site_lookup.sources import ENDPOINTS

lookup_module = sys.modules["site_lookup.lookup"]        # the module (the package exports the function by the same name)

FIX = Path(__file__).parent / "fixtures"
NOW = dt.datetime(2026, 10, 20, 18, 0, tzinfo=dt.timezone.utc)


def load(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text())


def key_of(url: str) -> str:
    return next(k for k, e in ENDPOINTS.items() if url in (e["url"], e.get("layer")))


class Fake:
    """Answers like the services would. Recorded answers for the public sources (matched on the exact
    request); stand-ins for the City and County layers; any piece can be overridden per test."""

    def __init__(self, fixture: dict, zones=None, historic=(), county=None, offline=False, city_parcels=None):
        self.fx, self.offline = fixture, offline
        self.zones, self.historic, self.county, self.city_parcels = zones, list(historic), county, city_parcels
        self.asked: list[str] = []

    def _recorded(self, key, params):
        want = json.dumps(params, sort_keys=True)
        for a in self.fx["answers"]:
            if a["source"] == key and json.dumps(a["params"], sort_keys=True) == want:
                return a["body"]
        if key == "state_parcels":                   # a point the capture didn't ask about: no parcel there
            return {"features": []}
        raise AssertionError(f"no recorded answer for {key} {want[:200]}")

    def _streets(self):
        bodies = [a["body"] for a in self.fx["answers"] if a["source"] == "state_streets"]
        return bodies[-1]["features"] if bodies else []

    def post(self, url, params):
        key = key_of(url)
        self.asked.append(key)
        if self.offline:
            raise Offline(url)
        d = self.fx.get("derived", {})
        if key == "city_roads":                      # stand-in: State centerlines with the City's ROW widths
            feats = [{"attributes": {"NAME": f["attributes"].get("CompleteStreetName"), "ROW_WIDTH": w},
                      "geometry": f["geometry"]} for f, w in zip(self._streets(), d.get("state_street_row_ft", []))]
            body = {"features": feats}
        elif key == "city_zoning" and url == ENDPOINTS["city_zoning"]["layer"]:
            day = dt.datetime.fromisoformat(d.get("zoning_last_edited", "2024-09-26")).replace(tzinfo=dt.timezone.utc)
            body = {"editingInfo": {"dataLastEditDate": int(day.timestamp() * 1000)}}
        elif key == "city_zoning":
            body = {"features": self.zones if self.zones is not None else [self.square(d.get("zone_at_lot"))]}
        elif key == "city_parcels":
            body = {"features": self.city_parcels or []}
        elif key == "address_points":
            body = {"features": [{"attributes": {}, "geometry": {"x": self.county[0], "y": self.county[1]}}]
                    if self.county else []}
        elif key == "historic_districts":
            body = {"features": [{"attributes": {"DISTRICT": n}} for n in self.historic]}
        elif key == "gorge_zones":
            body = {"features": []}
        else:
            body = self._recorded(key, params)
        return body, json.dumps(body, sort_keys=True).encode()

    def square(self, zone, x0=840000, y0=880000, x1=850000, y1=890000):
        return {"attributes": {"ZONE": zone}, "geometry": {"rings": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}}


def both(r: dict) -> dict:
    """Each fact with its details beside it (status, reason, where it came from), for asserting on."""
    return {k: {**v, **r["details"][k]} for k, v in r["facts"].items()}


def run(name, **kw):
    fake = Fake(load(name), **kw)
    return lookup(load(name)["address"], fake, NOW), fake


# ---- the three Ithaca Rd lots ---------------------------------------------------------------------------

def test_106_ithaca_rd_end_to_end():
    r, _ = run("106_ithaca_rd")
    f = both(r)
    assert r["status"] == "found" and r["asks"] == []
    assert f["parcel"]["value"] == "500700-84.-2-6"
    lot = f["lot"]["value"]
    assert abs(lot["area_sf"] - 7033.7) < 0.5                  # measured from the EPSG:2261 outline
    assert f["lot"]["source"] == "from tax map" and lot["tolerance_ft"] == 2.0      # → ±2'-0" downstream
    assert "±2 ft" in f["lot"]["source_detail"]
    assert f["street_side"]["value"]["street"] == "ITHACA RD"
    assert abs(f["street_side"]["value"]["frontage_ft"] - 75.8) < 0.2       # the 8-segment curve
    assert f["corner_lot"]["value"] == "no" and f["corner_lot"]["status"] == "suggested"
    ground = f["ground"]["value"]
    assert 734 <= ground["min_ft"] <= 736 and 748 <= ground["max_ft"] <= 750 and ground["kind"] == "existing"
    assert f["zone"]["value"] == "R-1b" and f["zone"]["status"] == "suggested"
    assert f["zone"]["source"] == "suggested by Gordium"
    assert "confirm" in f["zone"]["source_detail"] and "2024-09-26" in f["zone"]["source_detail"]
    assert f["overlays"]["value"] == []
    assert all(v["confirmed_by"] is None for v in f.values())   # a lookup never confirms anything


def test_every_fact_has_exactly_the_start_box_shape():
    """{value, source, confirmed_by, date} and nothing else; source is one of the start box's labels. How sure
    the lookup is, and the service it asked, sit beside the fact in details."""
    r, _ = run("106_ithaca_rd")
    assert set(r["facts"]) == set(r["details"])
    for name, v in r["facts"].items():
        assert list(v) == ["value", "source", "confirmed_by", "date"], name
        assert v["source"] in ("from tax map", "suggested by Gordium") and v["date"] == "2026-10-20"
        d = r["details"][name]
        assert d["status"] in ("suggested", "needs_review", "ask") and d["source_url"].startswith("https://")


def test_survey_feet_become_gordiums_feet():
    """EPSG:2261 is in US survey feet (1200/3937 m); Gordium works in international feet (0.3048 m)."""
    assert abs(lookup_module.US_SURVEY_FT - 1.000002) < 1e-7
    r, _ = run("106_ithaca_rd")
    lot = r["facts"]["lot"]["value"]
    ring = g.open_ring(next(a for a in load("106_ithaca_rd")["answers"] if a["source"] == "state_parcels")
                       ["body"]["features"][0]["geometry"]["rings"][0])
    assert lot["area_sf"] == round(g.area(ring) * 1.000004, 1)
    (x0, y0), (lx, ly) = lot["origin_epsg2261_us_survey_ft"], lot["outline_ft"][0]
    assert abs((ring[0][0] - x0) * 1.000002 - lx) < 0.006 and abs((ring[0][1] - y0) * 1.000002 - ly) < 0.006


def test_109_ithaca_rd_is_a_corner_lot_and_asks_for_the_front():
    r, _ = run("109_ithaca_rd")
    f = both(r)
    assert f["corner_lot"]["value"] == "ask" and f["corner_lot"]["status"] == "ask"
    assert f["street_side"]["status"] == "ask" and "MITCHELL ST" in f["corner_lot"]["reason"]
    assert set(f["street_side"]["value"]["streets"]) == {"ITHACA RD", "MITCHELL ST"}
    assert f["street_side"]["value"]["street"] == "ITHACA RD"   # the address's street is offered first
    assert any("two streets" in a for a in r["asks"])


def test_96_ithaca_rd_touches_both_streets():
    """The research's first street test matched only Mitchell St here (a 3 ft margin missed both front lines,
    which sit 4–6 ft beyond half the right-of-way on the tax map). With the 10 ft margin and the parallel test
    it touches both Ithaca Rd and Mitchell St: a corner lot, so Gordium asks."""
    r, _ = run("96_ithaca_rd")
    f = both(r)
    assert set(f["street_side"]["value"]["streets"]) == {"ITHACA RD", "MITCHELL ST"}
    assert f["corner_lot"]["value"] == "ask"


def test_an_address_on_a_street_the_lot_doesnt_touch_needs_review():
    fx = load("106_ithaca_rd")
    for a in fx["answers"]:
        if a["source"] == "geocoder":
            for c in a["body"]["candidates"]:
                c["attributes"]["StName"], c["attributes"]["StType"] = "Mitchell", "Street"
    r = lookup(fx["address"], Fake(fx), NOW)
    s = both(r)["street_side"]
    assert s["status"] == "needs_review" and "MITCHELL ST" in s["reason"] and "ITHACA RD" in s["reason"]
    assert any("check the front" in a for a in r["asks"])


def test_side_lines_of_a_shallow_lot_are_not_frontage():
    """A 100 ft wide, 15 ft deep lot on a 50 ft right-of-way: its 15 ft side lines end within reach of the
    street's centerline, but they run across it, not along it, so only the front line is frontage."""
    class Roads:
        records: list = []

        def city_roads_near(self, ring):
            return [{"name": "TEST ST", "row_ft": 50, "paths": [[(-200, -25), (300, -25)]], "source": "city_roads"}]
    facts, asks = {}, []
    lookup_module._streets(Roads(), [(0, 0), (100, 0), (100, 15), (0, 15)], "TEST ST", "2026-10-20", facts, asks)
    v = facts["street_side"]["value"]
    assert v["edges"] == [0] and v["frontage_ft"] == 100.0 and facts["corner_lot"]["value"] == "no"


# ---- refusals and failures ---------------------------------------------------------------------------------

def test_a_town_of_ithaca_address_is_refused():
    r, _ = run("953_danby_rd_town")
    assert r["status"] == "outside_city" and "Town of Ithaca" in r["message"]
    assert "lot" not in both(r)


def test_an_unknown_address_is_not_found():
    r, _ = run("not_found")
    assert r["status"] == "not_found" and "draw the lot" in r["message"]


def test_offline_is_a_plain_state_not_a_crash():
    r, _ = run("106_ithaca_rd", offline=True)
    assert r["status"] == "offline" and "by hand" in r["message"]


def test_a_failing_zoning_map_leaves_the_rest_and_asks_for_the_district():
    class NoZoning(Fake):
        def post(self, url, params):
            if key_of(url) == "city_zoning":
                raise Offline(url)
            return super().post(url, params)
    fx = load("106_ithaca_rd")
    r = lookup(fx["address"], NoZoning(fx), NOW)
    assert r["status"] == "found" and both(r)["lot"]["value"]
    assert both(r)["zone"]["status"] == "needs_review" and "choose the district" in both(r)["zone"]["reason"]


def test_the_county_point_far_from_the_state_point_needs_review():
    fx = load("106_ithaca_rd")
    p = next(a for a in fx["answers"] if a["source"] == "geocoder")["body"]["candidates"][0]["location"]
    r = lookup(fx["address"], Fake(fx, county=(p["x"] + 200, p["y"])), NOW)
    assert both(r)["address"]["status"] == "needs_review" and "200 ft apart" in both(r)["address"]["reason"]


# ---- zoning ------------------------------------------------------------------------------------------------

def test_a_lot_in_two_zones_asks_which_applies():
    fx = load("106_ithaca_rd")
    ring = g.open_ring(next(a for a in fx["answers"] if a["source"] == "state_parcels")["body"]["features"][0]["geometry"]["rings"][0])
    cx = g.centroid(ring)[0]
    f = Fake(fx)
    f.zones = [f.square("R-1b", 840000, 880000, cx, 890000), f.square("R-2a", cx, 880000, 850000, 890000)]
    r = lookup(fx["address"], f, NOW)
    z = both(r)["zone"]
    assert z["status"] == "ask" and set(z["value"]) == {"R-1b", "R-2a"}
    assert any("R-1b and R-2a" in a or "R-2a and R-1b" in a for a in r["asks"])


def test_a_lot_on_a_street_rezoned_after_the_map_needs_review():
    fx = load("106_ithaca_rd")
    for a in fx["answers"]:
        if a["source"] == "geocoder":
            for c in a["body"]["candidates"]:
                c["attributes"].update(StPreDir="S", StName="Cayuga", StType="Street")
    r = lookup(fx["address"], Fake(fx), NOW)
    z = both(r)["zone"]
    assert z["status"] == "needs_review" and "Ord. 2025-12" in z["reason"] and "S CAYUGA ST" in z["reason"]


def test_an_amendment_older_than_the_map_is_ignored(monkeypatch):
    monkeypatch.setattr(lookup_module, "AMENDMENTS", [{"ordinance": "old", "title": "x", "adopted": "2020-01-01",
                                                       "streets": ["ITHACA RD"]}])
    r, _ = run("106_ithaca_rd")
    assert both(r)["zone"]["status"] == "suggested"


def test_overlays_found_need_review():
    r, _ = run("106_ithaca_rd", historic=["East Hill"])
    o = both(r)["overlays"]
    assert o["status"] == "needs_review" and o["value"] == ["Historic district: East Hill"]


# ---- what a project keeps ------------------------------------------------------------------------------------

def test_the_snapshot_keeps_no_city_data_and_fingerprints_every_source():
    r, fake = run("106_ithaca_rd")
    s = r["snapshot"]
    assert s["facts"]["zone"]["value"].startswith("(used live, not stored")
    assert s["facts"]["overlays"]["value"].startswith("(used live, not stored")
    assert s["facts"]["lot"]["value"]["area_sf"] == both(r)["lot"]["value"]["area_sf"]
    assert len(s["sources"]) == len(fake.asked)
    for rec in s["sources"]:
        assert len(rec["sha256"]) == 64 and rec["url"].startswith("https://") and "body" not in rec
    assert len(s["fingerprint"]) == 64
    assert "R-1b" not in json.dumps(s)                  # the City's zone is nowhere in what's kept


def test_the_same_answers_give_the_same_snapshot():
    a, _ = run("106_ithaca_rd")
    b, _ = run("106_ithaca_rd")
    assert a["snapshot"]["fingerprint"] == b["snapshot"]["fingerprint"]


def test_areas_are_never_read_from_a_service():
    src = "".join(p.read_text() for p in (Path(__file__).parents[1] / "site_lookup").glob("*.py"))
    assert "Shape__Area" not in src and "CALCACRES" not in src
    assert "outSR" in src                                # every geometry is asked for in EPSG:2261


def test_fixtures_hold_no_personal_or_city_data():
    for p in FIX.glob("*.json"):
        text = p.read_text()
        for word in ("OWNER", "MAIL_ADDR", "PRIMARY_OWNER"):
            assert word not in text, (p.name, word)
        for a in json.loads(text)["answers"]:
            assert ENDPOINTS[a["source"]]["store"] == "raw", (p.name, a["source"])


@pytest.mark.skipif(not os.environ.get("GORDIUM_LIVE"), reason="asks the live services; run with GORDIUM_LIVE=1")
def test_live_106_ithaca_rd():
    from site_lookup.http import Http
    r = lookup("106 Ithaca Rd, Ithaca, NY 14850", Http())
    assert r["status"] == "found" and both(r)["parcel"]["value"] == "500700-84.-2-6"
    assert both(r)["zone"]["value"] == "R-1b"
