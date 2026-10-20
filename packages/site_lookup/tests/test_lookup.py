"""The address lookup, offline: real recorded answers from the public State and USGS services (fixtures/,
made by capture.py), and synthetic stand-ins for the City and County layers, whose terms don't allow storing
their data: nothing from those layers is in the fixtures or in this file."""

import copy
import datetime as dt
import json
import os
from pathlib import Path

import pytest
import yaml

import sys

from site_lookup import geometry as g
from site_lookup.http import Offline, ServiceError
from site_lookup.lookup import lookup
from site_lookup.sources import ENDPOINTS

lookup_module = sys.modules["site_lookup.lookup"]        # the module (the package exports the function by the same name)

FIX = Path(__file__).parent / "fixtures"
NOW = dt.datetime(2026, 10, 20, 18, 0, tzinfo=dt.timezone.utc)
REPO = Path(__file__).parents[3]
# Stand-ins for the City layers (test values, not the City's):
STAND_IN_ROW_FT = 60                       # every street's right-of-way width
STAND_IN_MAP_EDITED = "2025-01-01"         # the zoning map's last edit (before Ord. 2025-12)
# 106 Ithaca Rd's district from Gordium's own test site (architect-checked, and the May 2026 PDF map), not the
# City's online layer:
STAND_IN_ZONE = yaml.safe_load((REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/model_facts.yaml")
                               .read_text())["lot_facts"]["zone"]


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
        if key == "city_roads":                      # stand-in: State centerlines with a test width
            feats = [{"attributes": {"NAME": f["attributes"].get("CompleteStreetName"), "ROW_WIDTH": STAND_IN_ROW_FT},
                      "geometry": f["geometry"]} for f in self._streets()]
            body = {"features": feats}
        elif key == "city_zoning" and url == ENDPOINTS["city_zoning"]["layer"]:
            day = dt.datetime.fromisoformat(STAND_IN_MAP_EDITED).replace(tzinfo=dt.timezone.utc)
            body = {"editingInfo": {"dataLastEditDate": int(day.timestamp() * 1000)}}
        elif key == "city_zoning":
            body = {"features": self.zones if self.zones is not None else [self.square(STAND_IN_ZONE)]}
        elif key == "city_parcels":                  # stand-in: the State parcel there, with no City flags
            body = {"features": self.city_parcels if self.city_parcels is not None else self._state_as_city(params)}
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

    def _state_as_city(self, params):
        want = params["geometry"]
        for a in self.fx["answers"]:
            if a["source"] == "state_parcels" and a["params"].get("geometry") == want:
                return [{"attributes": {"SWISPRINTK": f"{f['attributes']['SWIS']}-{f['attributes']['PRINT_KEY']}",
                                        "SWIS": f["attributes"]["SWIS"]}, "geometry": f["geometry"]}
                        for f in a["body"].get("features", [])]
        return []

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
    assert "confirm" in f["zone"]["source_detail"] and STAND_IN_MAP_EDITED in f["zone"]["source_detail"]
    assert "outside the area it rezoned" in f["zone"]["note"]           # Ord. 2025-12 is far from Ithaca Rd
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


def test_a_lot_partly_off_the_zoning_map_needs_review():
    fx = load("106_ithaca_rd")
    ring = g.open_ring(next(a for a in fx["answers"] if a["source"] == "state_parcels")["body"]["features"][0]["geometry"]["rings"][0])
    cx = g.centroid(ring)[0]
    f = Fake(fx)
    f.zones = [f.square("R-1b", 840000, 880000, cx, 890000)]       # only the lot's west half is mapped
    z = both(lookup(fx["address"], f, NOW))["zone"]
    assert z["value"] == "R-1b" and z["status"] == "needs_review" and "of this lot is on the City's zoning map" in z["reason"]


def test_a_point_found_only_along_the_street_makes_the_lot_doubtful():
    """The geocoder's along-the-street guess can land on the neighbour's lot: the lot and parcel it picked
    need review too, not only the address."""
    fx = load("106_ithaca_rd")
    for a in fx["answers"]:
        if a["source"] == "geocoder":
            for c in a["body"]["candidates"]:
                c["attributes"]["Addr_type"] = "StreetAddress"
    f = both(lookup(fx["address"], Fake(fx), NOW))
    assert f["address"]["status"] == "needs_review"
    assert f["lot"]["status"] == "needs_review" and f["parcel"]["status"] == "needs_review"
    assert "wrong lot" in f["lot"]["reason"]


def test_a_malformed_answer_is_an_error_state_not_a_crash():
    fx = load("106_ithaca_rd")
    for a in fx["answers"]:
        if a["source"] == "geocoder":
            for c in a["body"]["candidates"]:
                del c["location"]
    r = lookup(fx["address"], Fake(fx), NOW)
    assert r["status"] == "error" and "by hand" in r["message"]


def test_a_lot_on_a_street_rezoned_after_the_map_needs_review():
    fx = load("106_ithaca_rd")
    for a in fx["answers"]:
        if a["source"] == "geocoder":
            for c in a["body"]["candidates"]:
                c["attributes"].update(StPreDir="S", StName="Cayuga", StType="Street")
    r = lookup(fx["address"], Fake(fx), NOW)
    z = both(r)["zone"]
    assert z["status"] == "needs_review" and "Ord. 2025-12" in z["reason"] and "S CAYUGA ST" in z["reason"]


def test_an_amendment_checked_on_the_map_is_cleared(monkeypatch):
    """map_shows_since is set by hand once someone has seen the rezoning on the online map."""
    monkeypatch.setattr(lookup_module, "AMENDMENTS", [{"ordinance": "old", "title": "x", "adopted": "2020-01-01",
                                                       "map_shows_since": "2020-06-01", "streets": ["ITHACA RD"]}])
    r, _ = run("106_ithaca_rd")
    assert both(r)["zone"]["status"] == "suggested"


def test_a_later_map_edit_alone_never_clears_an_amendment(monkeypatch):
    """Any edit moves the layer's edit date, drawn rezoning or not: a map edited after the ordinance still
    flags lots in its area until someone has checked (map_shows_since)."""
    monkeypatch.setattr(sys.modules[__name__], "STAND_IN_MAP_EDITED", "2026-01-01")
    x0, y0, x1, y1 = g.bounds(ring_of(load("106_ithaca_rd")), 50)
    monkeypatch.setattr(lookup_module, "AMENDMENTS", [{"ordinance": "T", "title": "test", "adopted": "2025-11-19",
                                                       "area_epsg2261": [x0, y0, x1, y1], "streets": []}])
    z = both(run("106_ithaca_rd")[0])["zone"]
    assert z["status"] == "needs_review" and "isn't confirmed to be on the City's online map" in z["reason"]


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


# ---- review round 1: incomplete evidence is never "suggested" ------------------------------------------------

class Failing(Fake):
    """A Fake where the listed sources fail (ServiceError)."""

    def __init__(self, fixture, failing=(), **kw):
        super().__init__(fixture, **kw)
        self.failing = set(failing)

    def post(self, url, params):
        if key_of(url) in self.failing:
            raise ServiceError(url)
        return super().post(url, params)


def ring_of(fx: dict):
    return g.open_ring(next(a for a in fx["answers"] if a["source"] == "state_parcels")["body"]["features"][0]
                       ["geometry"]["rings"][0])


def test_a_second_match_that_couldnt_be_placed_makes_the_chosen_one_doubtful():
    fx = load("106_ithaca_rd")
    geo = next(a for a in fx["answers"] if a["source"] == "geocoder")["body"]
    other = copy.deepcopy(geo["candidates"][0])
    other["location"]["x"] += 3000                       # 106 on another street: its parcel query finds nothing
    other["address"] = "106 Elsewhere Rd, Ithaca, NY, 14850"
    geo["candidates"].append(other)
    f = both(lookup(fx["address"], Fake(fx), NOW))
    assert f["address"]["status"] == "needs_review" and "106 Elsewhere Rd" in f["address"]["reason"]
    assert f["lot"]["status"] == "needs_review" and f["parcel"]["status"] == "needs_review"


def test_missing_elevation_samples_need_review():
    fx = load("106_ithaca_rd")
    body = next(a for a in fx["answers"] if a["source"] == "elevation")["body"]
    total = len(body["samples"])
    body["samples"] = body["samples"][-1:]               # only the centre came back
    gr = both(lookup(fx["address"], Fake(fx), NOW))["ground"]
    assert gr["status"] == "needs_review" and f"missing at {total - 1} of {total} points" in gr["reason"]


def test_unknown_road_widths_never_give_a_confident_interior_lot():
    """The State streets fallback has no widths: a 50 ft right-of-way is assumed, which can miss a wider
    second street, so the street side needs review and the corner lot is asked."""
    fx = load("106_ithaca_rd")
    f = both(lookup(fx["address"], Failing(fx, ["city_roads"]), NOW))
    assert f["street_side"]["value"]["street"] == "ITHACA RD"
    assert f["street_side"]["status"] == "needs_review" and "widths weren't available" in f["street_side"]["reason"]
    assert f["corner_lot"]["value"] == "ask" and f["corner_lot"]["status"] == "ask"


def test_a_city_road_without_a_width_near_the_lot_makes_the_streets_doubtful(monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "STAND_IN_ROW_FT", None)
    f = both(run("106_ithaca_rd")[0])
    assert f["street_side"]["status"] == "needs_review" and f["corner_lot"]["value"] == "ask"


@pytest.mark.parametrize("city", ["fails", "another parcel"])
def test_city_flags_that_couldnt_be_checked_need_review(city):
    fx = load("106_ithaca_rd")
    if city == "fails":
        fake = Failing(fx, ["city_parcels"])
    else:
        fake = Fake(fx, city_parcels=[{"attributes": {"SWISPRINTK": "500700-1.-1-1", "SWIS": "500700"},
                                       "geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}])
    o = both(lookup(fx["address"], fake, NOW))["overlays"]
    assert o["status"] == "needs_review" and any("couldn't check" in v and "Historic property" in v for v in o["value"])


def test_a_two_zone_ask_survives_an_amendment_hit():
    fx = load("106_ithaca_rd")
    for a in fx["answers"]:
        if a["source"] == "geocoder":
            for c in a["body"]["candidates"]:
                c["attributes"].update(StPreDir="S", StName="Cayuga", StType="Street")
    cx = g.centroid(ring_of(fx))[0]
    f = Fake(fx)
    f.zones = [f.square("R-1b", 840000, 880000, cx, 890000), f.square("R-2a", cx, 880000, 850000, 890000)]
    z = both(lookup(fx["address"], f, NOW))["zone"]
    assert z["status"] == "ask" and "pick the zone" in z["reason"] and "Ord. 2025-12" in z["reason"]


# ---- the Southside amendment, by area ------------------------------------------------------------------------

def _dot(x, y):
    return [(x - 1, y - 1), (x + 1, y - 1), (x + 1, y + 1), (x - 1, y + 1)]


def test_the_southside_area_covers_its_streets_and_not_ithaca_rd():
    """Points from the NYS Geocoder: Southside lots are in Ord. 2025-12's area whatever street they're on
    (S Plain St isn't named in its text); 106 Ithaca Rd, on East Hill, isn't."""
    a = next(a for a in lookup_module.AMENDMENTS if a["ordinance"] == "2025-12")
    reaches = lookup_module._amendment_reaches
    assert reaches(a, _dot(841738, 886359), {"S PLAIN ST"})          # S Plain St & Wood St
    assert reaches(a, _dot(843068, 887666), {"S CAYUGA ST"})         # 315 S Cayuga St
    assert reaches(a, _dot(841753, 886005), {"PARK ST"})             # Park St & S Plain St
    assert reaches(a, ring_of(load("106_ithaca_rd")), {"ITHACA RD"}) == ""


def test_a_lot_in_an_amendments_area_needs_review_whatever_its_street(monkeypatch):
    x0, y0, x1, y1 = g.bounds(ring_of(load("106_ithaca_rd")), 50)
    monkeypatch.setattr(lookup_module, "AMENDMENTS", [{"ordinance": "T", "title": "test", "adopted": "2025-11-19",
                                                       "area_epsg2261": [x0, y0, x1, y1], "streets": []}])
    z = both(run("106_ithaca_rd")[0])["zone"]
    assert z["status"] == "needs_review" and "in or near the area it rezoned" in z["reason"]


def test_an_amendment_without_an_area_makes_every_city_lot_need_review(monkeypatch):
    monkeypatch.setattr(lookup_module, "AMENDMENTS", [{"ordinance": "T", "title": "test", "adopted": "2025-11-19",
                                                       "streets": ["S PLAIN ST"]}])
    z = both(run("106_ithaca_rd")[0])["zone"]
    assert z["status"] == "needs_review" and "boundary isn't recorded" in z["reason"]


# ---- licensing: what is kept follows endpoints.yaml ------------------------------------------------------------

def _numbers_only(v) -> bool:
    def num(n):
        return isinstance(n, (int, float)) and not isinstance(n, bool)
    return num(v) or (isinstance(v, list) and all(num(n) for n in v))


ON_THE_LOT = ("street_side", "corner_lot", "ground", "zone", "overlays")    # worked out on the lot's outline


def check_snapshot(r: dict) -> None:
    """Every kept fact obeys the strictest store policy of every source it was worked out from: none keeps no
    value and no reason; derived keeps numbers Gordium computed only (no outline, position or words); answer
    bodies are never kept. Not trusted from each fact's own source_keys: a fact worked out on the lot's outline
    counts the lot's own source (the parcel layer that gave the outline) here, whatever it lists."""
    s = r["snapshot"]
    lot_layers = s["details"]["lot"]["source_keys"] if "lot" in s["details"] else []
    for k, v in s["facts"].items():
        d = s["details"][k]
        keys = list(d["source_keys"]) + (lot_layers if k in ON_THE_LOT else [])
        store = lookup_module.strictest(keys)
        if store == "derived" and isinstance(v["value"], dict):
            assert all(_numbers_only(n) for n in v["value"].values()), k
            assert not {"outline_ft", "origin_epsg2261_us_survey_ft"} & set(v["value"]), k
        elif store != "raw":
            assert v["value"] in (None, lookup_module.USED_LIVE), k
        if store != "raw":
            assert "reason" not in d and "note" not in d, k
    assert all("body" not in rec for rec in s["sources"])


def test_snapshots_keep_only_what_each_source_allows():
    scenarios = [Fake(load("106_ithaca_rd")), Fake(load("109_ithaca_rd")), Fake(load("96_ithaca_rd")),
                 Failing(load("106_ithaca_rd"), ["state_parcels"]), Failing(load("106_ithaca_rd"), ["city_roads"])]
    for fake in scenarios:
        r = lookup(fake.fx["address"], fake, NOW)
        assert r["status"] == "found"
        check_snapshot(r)
        assert STAND_IN_ZONE not in json.dumps(r["snapshot"])


def test_a_city_parcel_outline_is_never_kept():
    """With the State parcels down the lot comes from the City's layer (store: derived): the project keeps its
    area and side lengths, never its outline or position."""
    fx = load("106_ithaca_rd")
    r = lookup(fx["address"], Failing(fx, ["state_parcels"]), NOW)
    assert both(r)["lot"]["source_keys"] == ["city_parcels"] and both(r)["lot"]["value"]["outline_ft"]
    kept = r["snapshot"]["facts"]["lot"]["value"]
    assert set(kept) == {"area_sf", "edge_lengths_ft", "tolerance_ft"}
    assert r["snapshot"]["facts"]["parcel"]["value"] == lookup_module.USED_LIVE


def test_fixtures_hold_only_what_endpoints_yaml_allows():
    """Fixtures keep answers from store: raw sources and nothing else: no block of values from the City or
    County layers (their stand-ins are synthetic, in this file)."""
    for p in FIX.glob("*.json"):
        d = json.loads(p.read_text())
        assert set(d) <= {"address", "captured", "answers", "live_status", "trimmed"}, (p.name, set(d))
        for a in d["answers"]:
            assert ENDPOINTS[a["source"]]["store"] == "raw", (p.name, a["source"])


# ---- review round 2 ---------------------------------------------------------------------------------------

def test_capture_records_what_the_fake_replays():
    """Re-capturing must give fixtures the tests can use: the City-roads stand-in is built from NYS Streets,
    which the lookup itself only asks when the City's roads fail, so capture() asks for them, with exactly the
    request the lookup's fallback makes."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("capture", FIX / "capture.py")
    capture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(capture)
    fx = load("106_ithaca_rd")
    got = capture.capture(fx["address"], Fake(fx))             # the City's roads answer, as they do live
    streets = [a for a in got["answers"] if a["source"] == "state_streets"]

    class Asked:
        def post(self, url, params):
            self.params = params
            return {"features": []}, b"{}"
    asked = Asked()
    lookup_module.Fetcher(asked).state_streets_near(ring_of(fx))
    assert streets and json.dumps(streets[-1]["params"], sort_keys=True) == json.dumps(asked.params, sort_keys=True)
    assert all(ENDPOINTS[a["source"]]["store"] == "raw" for a in got["answers"])


def test_every_doubt_about_the_address_is_kept():
    """Reasons add up: a second match with no parcel and a far County point are both said, on the address and
    on the lot it picked."""
    fx = load("106_ithaca_rd")
    geo = next(a for a in fx["answers"] if a["source"] == "geocoder")["body"]
    p = geo["candidates"][0]["location"]
    other = copy.deepcopy(geo["candidates"][0])
    other["location"]["x"] += 3000
    other["address"] = "106 Elsewhere Rd, Ithaca, NY, 14850"
    geo["candidates"].append(other)
    f = both(lookup(fx["address"], Fake(fx, county=(p["x"] + 200, p["y"])), NOW))
    for name in ("address", "lot", "parcel"):
        assert "106 Elsewhere Rd" in f[name]["reason"] and "200 ft apart" in f[name]["reason"], name


def test_status_changes_only_through_escalate():
    """The rule 'the strongest status wins, reasons add up' holds only if nothing sets a status around it."""
    import inspect
    import re
    src = inspect.getsource(lookup_module)
    esc = inspect.getsource(lookup_module.escalate)
    rest = src.replace(esc, "").replace(inspect.getsource(lookup_module.snapshot), "")   # snapshot copies, never decides
    assert esc.count('f["status"] = status') == 1
    assert not re.search(r"""\[["']status["']\]\s*=[^=]""", rest)
    assert not re.search(r"""\b\w+_(status|reason)\b\s*(,\s*\w+\s*)?=[^=]""", rest)
    assert not re.search(r"""\[["']reason["']\]\s*=[^=]""", rest)


def test_the_snapshot_keeps_nothing_worked_out_from_a_city_or_county_answer():
    """A County distance in the address's reason, the zoning map's edit date in the zone's description: each
    came from a source that may not be kept, so neither is in the snapshot (the State's address is)."""
    fx = load("106_ithaca_rd")
    p = next(a for a in fx["answers"] if a["source"] == "geocoder")["body"]["candidates"][0]["location"]
    r = lookup(fx["address"], Fake(fx, county=(p["x"] + 200, p["y"])), NOW)
    assert "200 ft apart" in both(r)["address"]["reason"]
    kept = json.dumps(r["snapshot"])
    assert "200 ft apart" not in kept and STAND_IN_MAP_EDITED not in kept and STAND_IN_ZONE not in kept
    assert r["snapshot"]["facts"]["address"]["value"] == both(r)["address"]["value"]
    assert r["snapshot"]["details"]["address"]["status"] == "needs_review"
    check_snapshot(r)


def test_the_docs_describe_what_the_code_does():
    methods = (REPO / "docs/methods.md").read_text()
    readme = (Path(__file__).parents[1] / "README.md").read_text()
    assert "matched by street name" not in methods and "padded box" in methods
    assert "50 ft assumed, noted" not in readme and "source_keys" in readme and "map_shows_since" in readme


# ---- review round 3 ---------------------------------------------------------------------------------------

def test_a_lookup_that_stops_half_way_keeps_nothing_from_the_city_outline():
    """The reviewer's reproduction: the State parcels down (the lot comes from the City's layer, store:
    derived) and a malformed zoning answer stops the lookup after the ground. The ground's points are offsets
    of the City outline's corners: they count the City's source from the moment they exist, so they're not kept."""
    fx = load("106_ithaca_rd")
    fake = Failing(fx, ["state_parcels"], zones=[{"geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}])
    r = lookup(fx["address"], fake, NOW)
    assert r["status"] == "error"
    assert "city_parcels" in r["snapshot"]["details"]["ground"]["source_keys"]
    assert "points" not in r["snapshot"]["facts"]["ground"]["value"]
    check_snapshot(r)


@pytest.mark.parametrize("doubt", ["along the street", "several pieces"])
def test_every_fact_on_a_doubtful_lot_is_doubtful(doubt):
    """A lot that may be the wrong one (an address found only along the street), or a parcel in several pieces
    (measured on its largest): the street side, corner lot, ground, zone and overlays were all worked out on it,
    so none of them is 'suggested'."""
    fx = load("106_ithaca_rd")
    for a in fx["answers"]:
        if doubt == "along the street" and a["source"] == "geocoder":
            for c in a["body"]["candidates"]:
                c["attributes"]["Addr_type"] = "StreetAddress"
        if doubt == "several pieces" and a["source"] == "state_parcels":
            for feat in a["body"].get("features", []):
                feat["geometry"]["rings"].append([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]])
    f = both(lookup(fx["address"], Fake(fx), NOW))
    words = "may be the wrong one" if doubt == "along the street" else "largest piece"
    for name in ON_THE_LOT:
        assert f[name]["status"] != "suggested" and words in f[name]["reason"], name
