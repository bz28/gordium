"""The context map, offline: the State's parcels and streets around 106 Ithaca Rd as recorded from the live
services (fixtures/106_ithaca_rd_context.json, made by capture.py), and synthetic stand-ins for the building
footprints, whose source may not be kept yet (store: none: nothing of them is in any fixture)."""

import importlib.util
import json
import math
import os
from pathlib import Path

import pytest

from site_lookup import geometry as g
from site_lookup.context import HALF_SIZE_FT, LAYERS, LIVE_ONLY, context
from site_lookup.http import Offline, ServiceError
from site_lookup.lookup import US_SURVEY_FT, lookup
from site_lookup.sources import ENDPOINTS, Fetcher

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("site_lookup_test_lookup", HERE / "test_lookup.py")
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)


def ring_and_origin():
    lot = lookup(T.load("106_ithaca_rd")["address"], T.Fake(T.load("106_ithaca_rd")), T.NOW)["facts"]["lot"]["value"]
    ox, oy = lot["origin_epsg2261_us_survey_ft"]
    return [(ox + x / US_SURVEY_FT, oy + y / US_SURVEY_FT) for x, y in lot["outline_ft"]], (ox, oy), lot


def fake(**kw):
    return T.Fake(T.load("106_ithaca_rd"), context=T.load("106_ithaca_rd_context"), **kw)


def run(http=None, **kw):
    ring, origin, _ = ring_and_origin()
    http = http or fake()
    return context(ring, http, origin=origin, now=T.NOW, **kw), http


def test_106_ithaca_rd_context():
    c, http = run()
    assert c["status"] == "found" and c["message"] == ""
    p, s, b = (c["layers"][n] for n in ("parcels", "streets", "buildings"))
    assert len(p["items"]) == 229                     # 230 parcels meet the square; the lot itself is left out
    assert len({i["id"] for i in p["items"]}) == 229 and "500700-84.-2-6" not in {i["id"] for i in p["items"]}
    assert all(i["id"].startswith("500700-") for i in p["items"])      # all City of Ithaca here
    assert len(s["items"]) == 38 and {"Ithaca Road", "Mitchell Street"} <= {i["name"] for i in s["items"]}
    # one stand-in house per recorded parcel (230); the 18 centred outside the square are clipped away
    assert len(b["items"]) == 212 and b["dates"] == [T.STAND_IN_BUILDINGS_DATE]
    assert http.asked.count("state_parcels") >= 1 and http.asked.count("state_buildings") == 1


def test_everything_is_inside_the_square_in_feet_from_the_lot():
    c, _ = run()
    for layer in c["layers"].values():
        for item in layer["items"]:
            for x, y in item.get("ring") or item.get("path"):
                assert abs(x) <= HALF_SIZE_FT + 0.01 and abs(y) <= HALF_SIZE_FT + 0.01
    # some parcel reaches the square's edge (clipped there), so the square is the whole drawing
    edge = [x for i in c["layers"]["parcels"]["items"] for x, _ in i["ring"] if abs(abs(x) - HALF_SIZE_FT) < 0.02]
    assert edge


def test_the_coordinates_are_the_lookups_frame():
    """The context uses the lot's origin and Gordium's feet, so the parcel next door touches the lot's outline."""
    c, _ = run()
    _, _, lot = ring_and_origin()
    corners = lot["outline_ft"]
    near = min(math.dist(p, q) for i in c["layers"]["parcels"]["items"] for p in i["ring"] for q in corners)
    assert near < 0.5                                  # a shared corner, to rounding


def test_only_the_asked_fields_and_never_owner_data():
    asked = []

    class Spy(T.Fake):
        def post(self, url, params):
            asked.append(params)
            return super().post(url, params)
    run(Spy(T.load("106_ithaca_rd"), context=T.load("106_ithaca_rd_context")))
    assert {p["outFields"] for p in asked} == {f for _, f in LAYERS.values()}
    assert all("OWNER" not in p["outFields"] and "MAIL" not in p["outFields"] for p in asked)
    assert all(p["outSR"] == 2261 and p["inSR"] == 2261 for p in asked)


def test_paging_asks_for_the_rest_until_the_service_says_done():
    pages = [{"features": [{"attributes": {"OBJECTID": i}, "geometry": {"rings": []}} for i in range(3)],
              "exceededTransferLimit": True},
             {"features": [{"attributes": {"OBJECTID": 3}, "geometry": {"rings": []}}]}]
    offsets = []

    class Paged:
        def post(self, url, params):
            offsets.append(params["resultOffset"])
            body = pages[len(offsets) - 1]
            return body, json.dumps(body).encode()
    feats, complete = Fetcher(Paged()).in_box("state_parcels", (0, 0, 1, 1), "SWIS")
    assert offsets == [0, 3] and len(feats) == 4 and complete


def test_paging_stops_at_the_cap_and_says_so():
    class Endless:
        def post(self, url, params):
            body = {"features": [{"attributes": {}, "geometry": {"rings": []}}] * 1000, "exceededTransferLimit": True}
            return body, b"{}"
    feats, complete = Fetcher(Endless()).in_box("state_parcels", (0, 0, 1, 1), "SWIS", cap=3000)
    assert len(feats) == 3000 and not complete


def test_one_layer_down_leaves_the_others():
    class Down(T.Fake):
        def post(self, url, params):
            if T.key_of(url) == "state_buildings":
                raise Offline(url)
            if T.key_of(url) == "state_streets":
                raise ServiceError(url)
            return super().post(url, params)
    c, _ = run(Down(T.load("106_ithaca_rd"), context=T.load("106_ithaca_rd_context")))
    assert c["status"] == "found" and len(c["layers"]["parcels"]["items"]) == 229
    assert c["layers"]["buildings"]["status"] == "offline" and c["layers"]["streets"]["status"] == "error"
    assert "Couldn't reach NYS Building Footprints" in c["message"]
    assert len(c["credits"]) == 1                       # only what was drawn is credited


def test_offline_everywhere_is_a_plain_state():
    c, _ = run(fake(offline=True))
    assert c["status"] == "offline" and "without it" in c["message"]
    assert all(not v["items"] for v in c["layers"].values())


def test_a_malformed_answer_is_an_error_for_that_layer_not_a_crash():
    class Broken(T.Fake):
        def post(self, url, params):
            if T.key_of(url) == "state_streets":
                body = {"features": [{"attributes": {}, "geometry": {"rings": "nonsense"}}]}
                return body, b"{}"
            return super().post(url, params)
    c, _ = run(Broken(T.load("106_ithaca_rd"), context=T.load("106_ithaca_rd_context")))
    assert c["layers"]["streets"]["status"] == "error" and c["layers"]["parcels"]["status"] == "found"


def test_the_snapshot_keeps_records_and_counts_never_a_live_sources_data():
    c, http = run()
    s = c["snapshot"]
    assert len(s["sources"]) == len(http.asked) and all(len(r["sha256"]) == 64 and "body" not in r for r in s["sources"])
    # a live-only source keeps no number worked out from it, not even how many (review round 2)
    assert s["layers"]["buildings"] == {"source": "state_buildings", "status": "found", "store": "none"}
    assert s["layers"]["parcels"]["count"] == 229 and s["layers"]["streets"]["count"] == 38
    text = json.dumps(s)
    assert T.STAND_IN_BUILDINGS_DATE not in text      # the footprints' own data (their date) isn't kept
    assert "NYS Building Footprints: " + LIVE_ONLY in s["credits"]
    assert "ring" not in text and "path" not in text   # no geometry at all: the drawn objects are the record
    assert len(s["fingerprint"]) == 64
    a, _ = run()
    assert a["snapshot"]["fingerprint"] == s["fingerprint"]


def test_the_footprints_are_never_storable_until_ben_decides():
    """Context map plan, D1: until Ben decides, the footprints are shown live and never kept."""
    assert ENDPOINTS["state_buildings"]["store"] == "none"
    assert ENDPOINTS["state_parcels"]["store"] == "raw" and ENDPOINTS["state_streets"]["store"] == "raw"


def test_the_context_fixture_holds_only_storable_answers():
    d = T.load("106_ithaca_rd_context")
    assert {a["source"] for a in d["answers"]} == {"state_parcels", "state_streets"}
    for a in d["answers"]:
        assert ENDPOINTS[a["source"]]["store"] == "raw"
        for f in a["body"]["features"]:
            assert set(f["attributes"]) <= {"SWIS", "PRINT_KEY", "CompleteStreetName", "OBJECTID"}


def test_capture_context_records_what_context_asks():
    spec = importlib.util.spec_from_file_location("capture", HERE / "fixtures" / "capture.py")
    capture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(capture)
    got = capture.capture_context(T.load("106_ithaca_rd")["address"], fake())
    want = T.load("106_ithaca_rd_context")["answers"]
    key = lambda a: (a["source"], json.dumps(a["params"], sort_keys=True))        # noqa: E731
    assert sorted(map(key, got["answers"])) == sorted(map(key, want))


def test_clip_ring_and_path():
    box = (0, 0, 10, 10)
    corner = g.clip_ring([(-5, -5), (5, -5), (5, 5), (-5, 5)], box)
    assert abs(g.area(corner) - 25) < 1e-9 and set(corner) == {(0, 0), (5, 0), (5, 5), (0, 5)}
    assert g.clip_ring([(20, 20), (30, 20), (30, 30)], box) == []
    assert abs(g.area(g.clip_ring([(2, 2), (8, 2), (8, 8), (2, 8)], box)) - 36) < 1e-9     # inside: unchanged
    assert g.clip_path([(-5, 5), (5, 5), (15, 5)], box) == [[(0, 5), (5, 5), (10, 5)]]
    assert g.clip_path([(-5, 20), (15, 20)], box) == []
    assert g.clip_path([(5, -5), (5, 15)], box) == [[(5, 0), (5, 10)]]


@pytest.mark.skipif(not os.environ.get("GORDIUM_LIVE"), reason="asks the live services; run with GORDIUM_LIVE=1")
def test_live_106_ithaca_rd_context():
    from site_lookup.http import Http
    ring, origin, _ = ring_and_origin()
    c = context(ring, Http(), origin=origin)
    assert c["status"] == "found" and len(c["layers"]["parcels"]["items"]) > 200
    assert c["layers"]["buildings"]["items"]
