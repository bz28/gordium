"""The address lookup in the start box (PR #19), offline: site_lookup's recorded answers (its tests/fixtures, State
and USGS data; stand-ins for the City layers) through design_checker.lookup_box and rhino_logic.lookup_choices, one
test per status the box can meet, where the lot lands, what may be kept, and the whole chain to the starting house."""
import copy
import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

from design_checker import present
from design_checker import rhino_logic as logic
from design_checker.lookup_box import box_payload, frame, main, writes

REPO = Path(__file__).resolve().parents[3]
TESTS = REPO / "packages/site_lookup/tests"
ZONES = ["R-1a", "R-1b", "R-2a", "R-3a"]


def _site_lookup_tests():
    spec = importlib.util.spec_from_file_location("site_lookup_recorded", TESTS / "test_lookup.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(TESTS))
    spec.loader.exec_module(mod)
    return mod


T = _site_lookup_tests()


def looked_up(name, **kw):
    from site_lookup.lookup import lookup
    fx = T.load(name)
    return box_payload(lookup(fx["address"], T.Fake(fx, **kw), T.NOW))


def area(ring):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1]))) / 2


def box(payload, facts=None, saved=None):
    facts, saved = logic.lookup_choices(payload, facts or {}, saved or {}, ZONES)
    state = {"address": facts.get("address"), "zone": facts.get("zone"), "zone_source": saved.get("zone_source"),
             "corner_lot": facts.get("corner_lot"), "zones_found": saved.get("zones_found") or [],
             "lookup": saved.get("lookup"), "checked": saved.get("checked"), "street_name": saved.get("street_name"),
             "lot_area": saved.get("lot_area"), "lot_surveyed": facts.get("lot_surveyed"),
             "lot_source": saved.get("lot_source")}
    return facts, saved, state


# ---- found: each fact a suggestion with its source ----------------------------------------------------------

def test_106_fills_the_box_with_suggestions_and_never_confirms_the_district():
    p = looked_up("106_ithaca_rd")
    facts, saved, state = box(p)
    assert p["status"] == "found" and facts["zone"] == "R-1b" and facts["corner_lot"] is False
    assert facts["lot_surveyed"] is False                  # the tax map: ±2'-0" and the starting-house margin apply
    assert saved["zone_source"] == "suggested by Gordium · City zoning map, used live"
    assert saved["street_name"] == "Ithaca Rd" and saved["lot_source"] == "NYS Tax Parcels Public"
    assert not state.get("district_confirmed") and not logic.can_draw(state)       # I confirm: still the architect's
    rows = {r["key"]: r for r in logic.box_rows(state)}
    assert rows["lot"]["text"] == "7,034 sf · from the tax map (±2 ft, approximate) · NYS Tax Parcels Public"
    assert all(r["review"] is None for r in rows.values()) and logic.unsettled(saved) == {}
    assert "zones_found" not in facts and "street_name" not in facts                # box choices, not lot facts
    from model_measurement.project import fact_problems
    assert fact_problems({**facts, "jurisdiction": "x", "use": "one_family"}) == []


def test_the_lot_lands_with_its_street_at_the_bottom_of_top_view_and_keeps_its_shape():
    p = looked_up("106_ithaca_rd")
    lot = p["facts"]["lot"]["value"]
    placed = frame({"facts": p["facts"]})
    ring = placed["ring"]
    assert min(x for x, _ in ring) == 0 and min(y for _, y in ring) == 0
    street_y = [pt[1] for seg in placed["street_line"] for pt in seg]
    assert max(street_y) < 1.0 and min(y for _, y in ring) == min(street_y)        # the street side at the bottom
    assert area(ring) == pytest.approx(lot["area_sf"], abs=0.5)                      # 7,033.8 sf: same lot
    lengths = [math.dist(a, b) for a, b in zip(ring, ring[1:] + ring[:1])]
    assert lengths == pytest.approx(lot["edge_lengths_ft"], abs=0.01)
    assert placed["street_edges"] == list(range(8))                                  # the curved frontage
    assert min(z for *_, z in placed["spots"]) == 0 and placed["datum_ft"] == pytest.approx(734.81)
    assert max(z for *_, z in placed["spots"]) == pytest.approx(748.96 - 734.81, abs=0.01)


@pytest.mark.parametrize("name", ["109_ithaca_rd", "96_ithaca_rd"])
def test_a_lot_on_two_streets_asks_for_the_front(name):
    p = looked_up(name)
    facts, saved, state = box(p)
    assert p["facts"]["corner_lot"]["value"] == "ask" and facts["corner_lot"] is True
    assert logic.uncertain(state) == "This lot faces two streets: pick the front"
    placed = frame({"facts": p["facts"]})
    assert max(pt[1] for seg in placed["street_line"] for pt in seg) < 2.0          # the address street at the bottom


def test_a_lot_in_two_zones_asks_which():
    a, b = T.Fake(T.load("106_ithaca_rd")).square("R-1b", x1=847668), T.Fake(T.load("106_ithaca_rd")).square(
        "R-2a", x0=847668)
    p = looked_up("106_ithaca_rd", zones=[a, b])
    facts, saved, state = box(p)
    assert saved["zones_found"] == ["R-1b", "R-2a"] or saved["zones_found"] == ["R-2a", "R-1b"]
    assert logic.uncertain(state) == "This lot is in two zones: pick the zone that applies"


# ---- needs review: amber, and every item measured from it needs review until checked or changed -------------

def test_a_doubtful_lot_is_amber_unsettled_and_settled_by_i_checked_this():
    fx = T.load("106_ithaca_rd")
    state_pt = next(a for a in fx["answers"] if a["source"] == "geocoder")["body"]["candidates"][0]["location"]
    p = looked_up("106_ithaca_rd", county=(state_pt["x"] + 200, state_pt["y"]))       # County point 200 ft away
    facts, saved, state = box(p)
    rows = {r["key"]: r for r in logic.box_rows(state)}
    assert rows["lot"]["review"].startswith("? This may be the wrong lot") and rows["lot"]["check"] == \
        ("I checked this", False)
    assert set(logic.unsettled(saved)) >= {"lot"}
    assert logic.unsettled(saved, checked=["lot", "street", "ground"]) == {}
    assert "lot" not in logic.unsettled(logic.settle(saved, "lot"))                # changed by the architect


def test_an_unsettled_lot_makes_every_item_measured_from_it_need_review_never_comply(tmp_path):
    from design_checker.check import check
    model = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/spreadsheet_design_model.3dm"
    from model_measurement.project import load_facts
    facts = load_facts(model.parent / "spreadsheet_design_model_facts.yaml")
    plain = {i["name"]: i for i in check(model, facts)["view"]["items"]}
    doubt = {i["name"]: i for i in check(model, {**facts, "unsettled": {"lot": "This may be the wrong lot."}})["view"]
             ["items"]}
    turned = [n for n, i in plain.items() if i["status"] == present.COMPLIES and i.get("measure")
              and i["measure"] not in ("building_height", "stories")]
    assert turned and all(doubt[n]["status"] == present.REVIEW for n in turned)
    assert all("looked-up lot outline, which needs review" in doubt[n]["reason"] for n in turned)
    assert not any(i["status"] == present.COMPLIES and i.get("measure") not in (None, "building_height", "stories")
                   for i in doubt.values())
    ground = {i["name"]: i for i in check(model, {**facts, "unsettled": {"ground": "Elevations missing."}})["view"]
              ["items"]}
    assert all(ground[n]["status"] != present.COMPLIES for n in ("Building height", "Stories"))
    from model_measurement.project import fact_problems
    assert fact_problems({"unsettled": {"roof": "x"}}) and not fact_problems({"unsettled": {"lot": "x"}})


# ---- what can't be filled in: the box keeps working and says why ---------------------------------------------

@pytest.mark.parametrize("name, kw, says", [
    ("106_ithaca_rd", {"offline": True}, "Couldn't reach the map services (offline?): enter the site by hand."),
    ("not_found", {}, "No City of Ithaca address found for"),
    ("953_danby_rd_town", {}, "not the City of Ithaca"),
])
def test_a_lookup_that_cant_fill_the_box_says_why(name, kw, says):
    p = looked_up(name, **kw)
    facts, saved, state = box(p, facts={"zone": "R-1b"})
    assert says in logic.uncertain(state) and facts == {"zone": "R-1b"}          # manual entry is untouched
    assert p["writes"]["lot_ring"] is None and p["writes"]["spots"] == []


@pytest.mark.parametrize("status, says", [("timeout", "The lookup took too long"), ("error", "answered with an error")])
def test_a_timeout_or_an_error_says_why(status, says):
    facts, saved, state = box({"status": status, "query": "106 Ithaca Rd"})
    assert says in logic.uncertain(state)


def test_several_matches_are_offered_under_the_address():
    p = {"status": "multiple", "message": "Several places match: 10 N Aurora St; 10 S Aurora St.",
         "matches": ["10 N Aurora St", "10 S Aurora St"], "query": "10 Aurora St"}
    facts, saved, state = box(p)
    rows = {r["key"]: r for r in logic.box_rows(state)}
    assert rows["address"]["matches"] == ["10 N Aurora St", "10 S Aurora St"]
    assert logic.uncertain(state).endswith("Pick one under Address, then Look up again.")


def test_looking_up_shows_its_state_and_keeps_draw_off():
    rows = {r["key"]: r for r in logic.box_rows({"lookup": {"looking": "106 Ithaca Rd"}})}
    assert rows["address"]["actions"] == [("lookup", "Looking up…", False)]
    assert rows["address"]["status"] == "Looking up 106 Ithaca Rd… (up to 45 s)"
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert "draw.Enabled = logic.can_draw(state) and not looking" in ui and 'done("pick:lookup_done")' in ui


# ---- what is kept (endpoints.yaml store) -----------------------------------------------------------------------

def test_only_what_each_source_allows_is_written_into_the_model():
    p = looked_up("106_ithaca_rd")
    w = p["writes"]
    assert w["lot_ring"] and w["spots"] and w["guide_ring"] is None                  # State parcels, USGS: raw
    kept = json.dumps({k: v for k, v in w.items() if k != "snapshot"})
    assert "R-1b" not in kept and "ITHACA RD" not in kept.upper().replace("ITHACA RD\"", "")
    city = copy.deepcopy({"facts": p["facts"], "details": p["details"], "snapshot": None, "status": "found"})
    city["details"]["lot"]["source_keys"] = ["city_parcels"]                        # the State's layer down
    cw = writes(city, frame(city))
    assert cw["lot_ring"] is None and cw["frame"] is None and cw["spots"] == [] and cw["guide_ring"]
    facts, saved, state = box({**city, "writes": cw, "query": p["query"]})
    assert "shown as a guide only" in saved["lookup"]["reviews"]["lot"]
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    body = rhino[rhino.index("def _lookup_done("):rhino.index("def frame_site_box(")]
    assert 'answer["facts"]' not in body and "answer.get(\"facts\")" not in body     # geometry only from writes
    assert 'STATE["lookup_guide"]' in body and "AddCurve" not in body.split('elif w.get("guide_ring")')[1]


def test_the_lookup_runs_in_its_own_process_and_prints_one_line(capsys):
    assert main(["106 Ithaca Rd, Ithaca, NY 14850", "--fixture", "106_ithaca_rd"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and json.loads(out[0])["status"] == "found"
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert '"-m", "design_checker.lookup_box", address' in rhino and "LOOKUP_LIMIT_S = 45" in rhino
    assert "p.kill()" in rhino[rhino.index("def _lookup_poll("):rhino.index("def _lookup_stop(")]


# ---- the whole chain: the looked-up lot to the starting house ----------------------------------------------------

def test_from_the_106_lookup_to_a_starting_house_that_complies_at_the_worst_case(tmp_path):
    import rhino3dm as r

    from design_checker.check import check_site, start
    from envelope_builder.start import floor_solids
    from model_measurement.read_3dm import read_site
    p = looked_up("106_ithaca_rd")
    facts, saved, _ = box(p)
    ring = p["writes"]["lot_ring"]
    m = r.File3dm()
    m.Settings.ModelUnitSystem = r.UnitSystem.Feet
    layer = r.Layer()
    layer.Name = "Site"
    m.Layers.Add(layer)
    attrs = r.ObjectAttributes()
    attrs.LayerIndex = 0
    m.Objects.AddPolyline([r.Point3d(x, y, 0) for x, y in ring + ring[:1]], attrs)
    m.Write(str(tmp_path / "lot.3dm"), 8)
    facts = {**facts, "jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "use": "one_family_detached",
             "street_line": p["writes"]["street_line"], "ground_is_flat": True, "grade_elevation": 0.0,
             "grade_is": "finished"}
    got = start(tmp_path / "lot.3dm", facts)
    assert got["floors"] and got["kept_back"] >= 2.0                              # the tax map's 2'-0" margin
    site = {**read_site(tmp_path / "lot.3dm", facts), "buildings": floor_solids(got["floors"])}
    items = check_site(site, facts)["view"]["items"]
    assert not [i["name"] for i in items if i["status"] == present.FAILS]
    assert not [i["name"] for i in items if i["status"] == present.REVIEW and "tax map" in (i.get("reason") or "")]


def test_gordium_start_copies_the_model_for_the_checker_after_the_box():
    """Found in Rhino (106, 109, 96 Ithaca Rd): the model was copied before the box, so the lot the lookup drew
    wasn't in the copy and no starting house was drawn ("the lot picked isn't a closed outline")."""
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    body = rhino[rhino.index("def gordium_start():"):]
    assert body.index('facts = confirm(doc, facts, options, "start")') < body.index("export(doc, path)")


def test_a_starting_house_is_drawn_on_the_looked_up_ground_as_it_is(tmp_path):
    """Found in Rhino (106 Ithaca Rd): with the lookup's spot grades as existing ground, the generator measured the
    house it had just drawn from spot grades at the lot's corners (not at its walls), found its height "not
    measurable" and drew nothing. Their plane sets the drawing level; the check still says the ground is existing."""
    import rhino3dm as r

    from design_checker.check import start
    p = looked_up("106_ithaca_rd")
    facts, _, _ = box(p)
    ring = p["writes"]["lot_ring"]
    m = r.File3dm()
    m.Settings.ModelUnitSystem = r.UnitSystem.Feet
    layer = r.Layer()
    layer.Name = "Site"
    m.Layers.Add(layer)
    attrs = r.ObjectAttributes()
    attrs.LayerIndex = 0
    m.Objects.AddPolyline([r.Point3d(x, y, 0) for x, y in ring + ring[:1]], attrs)
    m.Write(str(tmp_path / "lot.3dm"), 8)
    got = start(tmp_path / "lot.3dm", {**facts, "jurisdiction": "regulations/jurisdictions/new_york/ithaca_city",
                                       "use": "one_family_detached", "street_line": p["writes"]["street_line"],
                                       "grade_from": "spot", "grade_is": "existing",
                                       "grade_points": p["writes"]["spots"]})
    assert len(got["floors"]) == 3 and any("drawn on the ground as it is" in n for n in got["notes"])
    spots = p["writes"]["spots"]
    assert got["floors"][0]["base"] == pytest.approx(sum(z for *_, z in spots) / len(spots), abs=0.01)


def test_tax_map_slivers_get_no_length_label():
    """Seen in Rhino on 106 Ithaca Rd: its tax-map outline has edges of 0.14 and 0.24 ft, each labelled
    (0'-1 5/8"), cluttering the plan. Edges under SHORTEST_LABELLED_EDGE get none; every other edge keeps its own."""
    from design_checker.check import SHORTEST_LABELLED_EDGE, plan
    p = looked_up("106_ithaca_rd")
    ring = p["writes"]["lot_ring"]
    n = len(ring)
    site = {"lot": {"edges": [{"points": [ring[i] + [0.0], ring[(i + 1) % n] + [0.0]]} for i in range(n)]},
            "buildings": []}
    got = plan(site, {"outline": [], "holes": []}, {"items": []}, {})
    long_edges = [i for i in range(n) if math.dist(ring[i], ring[(i + 1) % n]) >= SHORTEST_LABELLED_EDGE]
    assert len(got["edges"]) == len(long_edges) == n - 2
