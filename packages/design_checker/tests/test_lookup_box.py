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


def _rules():
    from rule_format.rulebook import load, rulebook_for
    return {r["id"]: r for r in load(rulebook_for(REPO / "regulations/jurisdictions/new_york/ithaca_city", "R-1b"))
            ["rules"]}


RULES = _rules()


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


def box(payload, facts=None, saved=None, replaces=True):
    facts, saved = logic.lookup_choices(payload, facts or {}, saved or {}, ZONES, replaces=replaces)
    return facts, saved, state_of(facts, saved)


def state_of(facts, saved):
    """The box's state as gordium_rhino._box_state builds it from the facts and the box's choices."""
    return {"address": facts.get("address"), "zone": facts.get("zone"), "zone_source": saved.get("zone_source"),
            "corner_lot": facts.get("corner_lot"), "zones_found": saved.get("_zones_found") or [],
            "lookup": saved.get("_lookup") or {}, "doubts": saved.get("doubts") or {}, "live": saved.get("_live") or {},
            "checked": saved.get("checked"), "street_name": saved.get("_street_name") or saved.get("street_name"),
            "street_name_saved": None if saved.get("_street_name") else saved.get("street_name"),
            "lot_area": saved.get("lot_area"), "lot_surveyed": facts.get("lot_surveyed"),
            "lot_source": saved.get("lot_source")}


# ---- found: each fact a suggestion with its source ----------------------------------------------------------

def test_106_fills_the_box_with_suggestions_and_never_confirms_the_district():
    p = looked_up("106_ithaca_rd")
    facts, saved, state = box(p)
    assert p["status"] == "found" and facts["zone"] == "R-1b" and facts["corner_lot"] is False
    assert facts["lot_surveyed"] is False                  # the tax map: ±2'-0" and the starting-house margin apply
    assert saved["zone_source"] == "suggested by Gordium · City of Ithaca zoning map, used live"
    assert saved["_street_name"] == "Ithaca Rd" and saved["lot_source"] == "NYS Tax Parcels Public"
    assert saved["street_source"] == "suggested by Gordium · City of Ithaca roads, used live"
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
    assert sorted(saved["_zones_found"]) == ["R-1b", "R-2a"]
    assert logic.uncertain(state) == "This lot is in two zones: pick the zone that applies"


# ---- needs review: amber, and every item measured from it needs review until checked or changed -------------

def test_a_doubtful_lot_is_amber_unsettled_and_settled_by_i_checked_this():
    fx = T.load("106_ithaca_rd")
    state_pt = next(a for a in fx["answers"] if a["source"] == "geocoder")["body"]["candidates"][0]["location"]
    p = looked_up("106_ithaca_rd", county=(state_pt["x"] + 200, state_pt["y"]))       # County point 200 ft away
    facts, saved, state = box(p)
    rows = {r["key"]: r for r in logic.box_rows(state)}
    assert rows["lot"]["review"] == "? This may be the wrong lot: The State and County place this address 200 ft " \
        "apart: check the lot." and rows["lot"]["check"] == ("I checked this", False)
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
    decides = set(present.UNSETTLED_DECIDES["lot"])
    turned = [n for n, i in plain.items() if i["status"] == present.COMPLIES
              and present._formula_names(i, RULES) & decides]
    assert turned and all(doubt[n]["status"] == present.REVIEW for n in turned)
    assert all("looked-up lot outline, which needs review" in doubt[n]["reason"] for n in turned)
    assert not any(i["status"] == present.COMPLIES and present._formula_names(i, RULES) & decides
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
    assert "dashed guide only" in saved["_live"]["lot"]
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    body = rhino[rhino.index("def _lookup_done("):rhino.index("def _drawn(")]
    assert 'answer["facts"]' not in body and "answer.get(\"facts\")" not in body     # geometry only from writes
    assert 'STATE["lookup_guide"]' in body and "logic.apply_lookup(RhinoTable(doc), session" in body and "AddCurve" not in body


def test_the_lookup_runs_in_its_own_process_and_prints_one_line(capsys):
    assert main(["106 Ithaca Rd, Ithaca, NY 14850", "--fixture", "106_ithaca_rd"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and json.loads(out[0])["status"] == "found"
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert '"-m", "design_checker.lookup_box", address' in rhino and "logic.LOOKUP_LIMIT_S" in rhino
    assert "_lookup_kill(run)" in rhino[rhino.index("def _lookup_poll("):rhino.index("def _lookup_files_done(")]
    assert 'run["proc"].kill()' in rhino[rhino.index("def _lookup_kill("):rhino.index("def _lookup_done(")]


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


# ---- review round 1 of PR #19 (2026-10-20): each finding pinned ------------------------------------------------

def _doubtful_106():
    fx = T.load("106_ithaca_rd")
    pt = next(a for a in fx["answers"] if a["source"] == "geocoder")["body"]["candidates"][0]["location"]
    return looked_up("106_ithaca_rd", county=(pt["x"] + 200, pt["y"]))


@pytest.mark.parametrize("then", [{"status": "timeout"}, {"status": "offline"}, {"status": "not_found"},
                                  {"status": "multiple", "matches": ["a", "b"], "message": "Several."}])
def test_p0_a_failed_re_lookup_keeps_the_doubts_about_the_lot_still_drawn(then):
    """(A) Doubt is the model's: a lookup that didn't replace the lot never erases the doubts about the one drawn."""
    facts, saved, _ = box(_doubtful_106())
    before = logic.unsettled(saved)
    assert "lot" in before
    facts, saved = logic.lookup_choices({**then, "query": "x"}, facts, saved, ZONES)
    assert logic.unsettled(saved) == before
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    start = rhino[rhino.index("def _lookup_start("):rhino.index("def _lookup_poll(")]
    assert 'dict(saved_ui, _lookup={"says"' in start and 'dict(saved_ui, _lookup={"looking": address})' in start
    assert '"doubts"' not in start and "doubts=" not in start          # starting (or an empty address) touches no doubt


@pytest.mark.parametrize("key", ["lot", "street"])
def test_p0_the_height_bonus_never_complies_on_an_unsettled_lot_or_street_side(key):
    """(B) Scenario 03 complies only through the §325-16C bonus, which reads the yards and the lot depth: with the
    lot or the street side unsettled, Building height needs review too."""
    from design_checker import scenarios
    from design_checker.check import check_site
    sc = scenarios.load(next(p for p in scenarios.paths() if p.name.startswith("03_")))
    sc["lot"]["surveyed"] = True
    site, facts, extras = scenarios.site(sc)
    plain = {i["name"]: i for i in check_site(site, facts, extras=extras)["view"]["items"]}
    assert plain["Building height"]["status"] == present.COMPLIES and "38'-6\"" in plain["Building height"]["required"]
    doubt = {i["name"]: i for i in check_site(site, {**facts, "unsettled": {key: "x"}}, extras=extras)["view"]["items"]}
    assert doubt["Building height"]["status"] == present.REVIEW


@pytest.mark.parametrize("key", ["lot", "street", "ground"])
def test_every_r1b_rule_reading_an_unsettled_measurement_needs_review(key):
    """(B) Across every R-1b rule: any item whose formula reads a measurement the unsettled fact decides never
    complies; the others are untouched."""
    from design_checker import scenarios
    from design_checker.check import check_site
    decides = set(present.UNSETTLED_DECIDES[key])
    for path in scenarios.paths():
        sc = scenarios.load(path)
        site, facts, extras = scenarios.site(sc)
        plain = {i["name"]: i for i in check_site(site, facts, extras=extras)["view"]["items"]}
        doubt = {i["name"]: i for i in check_site(site, {**facts, "unsettled": {key: "x"}}, extras=extras)["view"]
                 ["items"]}
        for name, i in doubt.items():
            reads = present._formula_names(i, RULES) & decides
            assert not (reads and i["status"] == present.COMPLIES), (path.name, name)
            if not reads:
                assert i["status"] == plain[name]["status"], (path.name, name)


def test_p1_esc_on_place_spot_grades_settles_nothing():
    """Esc or Enter with no point placed: the ground's doubt and its looked-up source stay."""
    facts, saved, _ = box(_doubtful_106())
    assert "ground" in logic.unsettled(saved) or saved.get("ground_source")
    same = logic.after_ground_pick(saved, "spot", 0)
    assert logic.unsettled(same) == logic.unsettled(saved) and same.get("ground_source") == saved.get("ground_source")
    placed = logic.after_ground_pick({**saved, "doubts": {"ground": "x"}}, "spot", 3)
    assert "ground" not in logic.unsettled(placed) and "ground_source" not in placed
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert "logic.pick_effect(what, _pick_outcome(doc, what, facts, session), facts, saved_ui)" in rhino
    assert "        return placed" in rhino                       # the points placed are the pick's outcome


def test_p1_nothing_from_a_source_that_cant_be_kept_is_written():
    """(D) Everything the Rhino side writes for the box (its choices, the lot facts with their unsettled reasons,
    the facts' sources) holds nothing from the County's points, the City's zoning answers or the City's roads:
    one filter at the write boundary (storable_ui)."""
    facts, saved, state = box(_doubtful_106())
    a, b = T.Fake(T.load("106_ithaca_rd")).square("R-1b", x1=847668), T.Fake(T.load("106_ithaca_rd")).square(
        "R-2a", x0=847668)
    facts2, saved2, state2 = box(looked_up("106_ithaca_rd", zones=[a, b]))
    for f, sv, st in ((facts, saved, state), (facts2, saved2, state2)):
        written = json.dumps({"ui": logic.storable_ui(sv),
                              "facts": {**f, "unsettled": logic.unsettled(sv)},
                              "sources": logic.fact_sources(st, "2026-10-20", confirmed=True)})
        assert "200 ft apart" not in written and "County" not in written      # the County's point (store: none)
        assert "two zones" not in written and "R-2a" not in written           # the City's zoning answer (store: none)
        assert "Ithaca Rd" not in written                                     # the City's roads (store: none)
        assert not any(k.startswith("_") for k in logic.storable_ui(sv))
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert rhino.count("SetString(SECTION, UI_ENTRY") == 1 and "json.dumps(logic.storable_ui(state))" in rhino


def test_p2_overlays_found_and_ask_reasons_are_shown():
    """(F) A historic district the lookup found is shown under the district; a zone that is both asked and doubtful
    keeps its doubt."""
    facts, saved, state = box(looked_up("106_ithaca_rd", historic=["East Hill"]))
    rows = {r["key"]: r for r in logic.box_rows(state)}
    assert "East Hill" in (rows["zone"]["review"] or "")
    p = looked_up("106_ithaca_rd")
    p["details"]["zone"] = {"status": "ask", "reason": "This lot is in R-1b and R-2a: pick the zone that applies. "
                            "Ord. 2025-12 isn't confirmed to be on the City's online map: check the current zoning map.",
                            "source_keys": ["city_zoning"]}
    facts, saved, state = box(p)
    rows = {r["key"]: r for r in logic.box_rows(state)}
    assert "check the current zoning map" in rows["zone"]["review"]


def test_p2_source_labels_come_from_the_services_actually_used():
    """(E) The City's parcels when the State's didn't answer; NYS Streets when the City's roads didn't."""
    from design_checker.lookup_box import labels
    got = labels({"details": {"lot": {"source_keys": ["city_parcels"]},
                              "street_side": {"source_keys": ["state_streets", "state_parcels"]},
                              "corner_lot": {"source_keys": ["state_streets", "state_parcels"]}}})
    assert got["lot"] == "City of Ithaca tax parcels" and got["street_side"].startswith("NYS Streets")
    p = looked_up("106_ithaca_rd")
    p["labels"] = got
    facts, saved, _ = box(p)
    assert saved["lot_source"] == "City of Ithaca tax parcels" and "NYS Streets" in saved["street_source"]


def test_p2_a_lookup_on_the_architects_own_lot_leaves_its_lot_street_and_ground_alone():
    facts, saved, state = box(_doubtful_106(), facts={"lot_id": "survey", "lot_surveyed": True},
                              saved={"doubts": {}, "street_source": "entered by you"}, replaces=False)
    assert facts["lot_surveyed"] is True and facts["lot_id"] == "survey" and facts["zone"] == "R-1b"
    assert "_street_name" not in saved and saved["street_source"] == "entered by you" and saved["doubts"] == {}
    assert "corner_lot" not in facts and "lot_source" not in saved


def test_p2_the_guide_case_offers_draw_my_lot_and_keeps_draw_off_until_there_is_a_lot():
    p = looked_up("106_ithaca_rd")
    p["details"]["lot"]["source_keys"] = ["city_parcels"]
    from design_checker.lookup_box import frame
    p["writes"] = writes({"facts": p["facts"], "details": p["details"]}, frame({"facts": p["facts"]}))
    facts, saved, state = box(p)
    rows = {r["key"]: r for r in logic.box_rows({**state, "lot_missing": True})}
    assert rows["lot"]["actions"][0] == ("draw_lot", "Draw my lot…", True)
    assert logic.draw_reason({"district_confirmed": True, "lot_missing": True}) == "Draw or pick the lot to continue."
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert 'if what == "draw_lot":' in rhino and '"lot_missing": lot is None' in rhino


def test_p2_after_a_lookup_the_district_must_be_ticked_again():
    facts, saved, _ = box(looked_up("106_ithaca_rd"))
    assert saved["_reconfirm"] is True and "_reconfirm" not in logic.storable_ui(saved)
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert 'logic.district_confirmed(mode, zone_fact, facts.get("zone")) and not saved_ui.get("_reconfirm")' in rhino


def test_p2_the_lookups_line_never_hides_the_boxs_questions_and_isnt_kept():
    both = logic.uncertain({"lookup": {"says": "The lookup took too long."}, "corner_lot": None,
                            "zones_found": ["R-1b", "R-2a"]})
    assert both.startswith("Does this lot face two streets?") and "two zones" in both and both.endswith("too long.")
    facts, saved, _ = box({"status": "timeout", "query": "x"})
    assert "_lookup" in saved and "_lookup" not in logic.storable_ui(saved)


def test_p3_the_lookups_files_are_closed_one_time_limit_and_no_silent_failure():
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    files = rhino[rhino.index("def _lookup_files_done("):rhino.index("def _lookup_stop(")]
    assert "handle.close()" in files and 'os.remove(run["out"])' in files
    poll = rhino[rhino.index("def _lookup_poll("):rhino.index("def _lookup_files_done(")]
    assert poll.count("_lookup_files_done(run)") == 2 and "_lookup_files_done(run)" in \
        rhino[rhino.index("def _lookup_stop("):rhino.index("def _lookup_done(")]
    assert "LOOKUP_LIMIT_S = " not in rhino and 'logic.guard(frame_site, "frame the looked-up lot")' in rhino
    assert "frame_site_box" not in rhino
    assert "LOOKUP_LIMIT_S = " not in (REPO / "packages/design_checker/design_checker/lookup_box.py").read_text(
        encoding="utf-8")
    assert "up to %d s" % logic.LOOKUP_LIMIT_S in logic.LOOKING
    guide = (REPO / "apps/rhino_plugin/QUICKSTART.md").read_text(encoding="utf-8")
    assert "doesn't look up the zoning map" not in guide
    assert "doesn't look the zoning map up yet" not in (REPO / "packages/design_checker/design_checker/rhino_logic.py"
                                                       ).read_text(encoding="utf-8")


# ---- the start box as one transaction, by behaviour (review round 2): the real session and lookup logic on a fake
# model (rhino_logic.BoxSession, apply_lookup; gordium_rhino.RhinoTable is only the adapter to Rhino's) ---------------

class FakeTable:
    """A model: objects {id: {"layer", "kind", "held_from"}}, its layers, and its views."""

    def __init__(self, objects, layers=("Site", "Gordium")):
        self.objects = {k: dict(v, held_from=None) for k, v in objects.items()}
        self.layers = set(layers) | {o["layer"] for o in objects.values()}
        self.views, self.n = "the architect's views", 0

    def exists(self, i):
        return i in self.objects

    def delete(self, i):
        del self.objects[i]

    def layer_of(self, i):
        return self.objects[i]["layer"]

    def hold(self, i, token=None):
        self.layers.add(logic.HOLDING_LAYER)
        self.objects[i].update(held_from=self.objects[i]["layer"], layer=logic.HOLDING_LAYER, held_by=token)

    def release(self, i, layer):
        self.layers.add(layer)
        self.objects[i].update(layer=layer, held_from=None, held_by=None)

    def held_objects(self):
        return [(i, o["held_from"], o.get("held_by")) for i, o in self.objects.items()
                if o["layer"] == logic.HOLDING_LAYER]

    def mark_added(self, i, token):
        self.objects[i]["added_by"] = token

    def clear_mark(self, i):
        self.objects[i].pop("added_by", None)

    def added_objects(self):
        return [(i, o["added_by"]) for i, o in self.objects.items() if o.get("added_by")]

    def layer_names(self):
        return sorted(self.layers)

    def remove_layer_if_empty(self, name):
        if not any(o["layer"] == name for o in self.objects.values()) and \
                not any(n.startswith(name + "::") for n in self.layers):
            self.layers.discard(name)

    def save_views(self):
        return self.views

    def restore_views(self, saved):
        self.views = saved

    def _new(self, layer, kind):
        self.n += 1
        self.layers.add(layer)
        self.objects["new%d" % self.n] = {"layer": layer, "kind": kind, "held_from": None}
        return "new%d" % self.n

    def add_lot(self, ring, name):
        return self._new("Site", "lot")

    def add_spot(self, p):
        return self._new("Gordium::Grade", "point")

    def ground_points(self):
        return [i for i, o in self.objects.items() if o["kind"] == "point"
                and o["layer"] in ("Gordium::Grade", "Gordium::Grade::Finished")]

    def snapshot(self):
        return {i: (o["layer"], o["kind"]) for i, o in self.objects.items()}, sorted(self.layers), self.views


def sample_model():
    table = FakeTable({"sample": {"layer": "Site", "kind": "lot"}})
    return table, {"lot_id": "sample"}, {"from_sample": True, "replaceable_lot": "sample"}


def test_cancel_after_a_lookup_leaves_the_model_exactly_as_it_was():
    """Round 1 and 2 (and seen in Rhino): Cancel didn't bring the sample lot back. Held, not deleted: the same
    object, the same id, on its own layer; the lookup's lot and spot grades gone; the layer it made removed; the
    architect's views back."""
    table, facts, saved = sample_model()
    before = table.snapshot()
    session = logic.BoxSession(table)
    f, sv, guide = logic.apply_lookup(table, session, looked_up("106_ithaca_rd"), facts, saved, ZONES)
    assert table.objects["sample"]["layer"] == logic.HOLDING_LAYER and len(table.ground_points()) == 14
    assert f["lot_id"] != "sample" and guide is None
    table.views = "framed on the looked-up lot"
    session.rollback()
    assert table.snapshot() == before


def test_draw_after_a_lookup_deletes_what_was_replaced_and_keeps_the_new():
    table, facts, saved = sample_model()
    session = logic.BoxSession(table)
    f, sv, _ = logic.apply_lookup(table, session, looked_up("106_ithaca_rd"), facts, saved, ZONES)
    session.commit()
    assert "sample" not in table.objects and f["lot_id"] in table.objects
    assert logic.HOLDING_LAYER not in table.layers and len(table.ground_points()) == 14


def test_a_re_lookup_sets_aside_every_spot_grade_of_the_lot_it_replaces():
    """Round 2: the architect's own spot grades for the replaced lot stayed and mixed with the new lot's."""
    table, facts, saved = sample_model()
    session = logic.BoxSession(table)
    f, sv, _ = logic.apply_lookup(table, session, looked_up("106_ithaca_rd"), facts, saved, ZONES)
    mine = [table._new("Gordium::Grade", "point"), table._new("Gordium::Grade::Finished", "point")]
    session.add(mine)                                               # placed with Place spot grades… in this box
    keep = table._new("Gordium::Grade", "point")                    # one placed before the box opened
    f2, sv2, _ = logic.apply_lookup(table, session, looked_up("109_ithaca_rd"), f, sv, ZONES)
    assert len(table.ground_points()) == 6                          # 109's six, nothing of 106's lot
    assert table.objects[keep]["layer"] == logic.HOLDING_LAYER and not any(m in table.objects for m in mine)
    session.rollback()
    assert table.objects[keep]["layer"] == "Gordium::Grade" and table.objects["sample"]["layer"] == "Site"


def test_a_lookup_never_touches_the_architects_own_lot():
    """Round 1 (behaviour, round 2): a lot the architect picked, surveyed or drew is never held or replaced."""
    table = FakeTable({"survey": {"layer": "Site", "kind": "lot"}, "spot": {"layer": "Gordium::Grade", "kind": "point"}})
    before = table.snapshot()
    saved = logic.settle({"replaceable_lot": "survey"}, "lot")       # Use my survey… on it
    f, sv, guide = logic.apply_lookup(table, logic.BoxSession(table), _doubtful_106(),
                                      {"lot_id": "survey", "lot_surveyed": True}, saved, ZONES)
    assert table.snapshot() == before and f["lot_id"] == "survey" and f["lot_surveyed"] is True
    assert sv["_lookup"]["says"].startswith("Your own lot is kept") and logic.unsettled(sv) == {}


def test_esc_or_an_error_anywhere_in_the_box_rolls_it_back():
    """Round 2: Esc inside a pick (Cancelled) or any error escaped the box with its edits left in the model."""
    for raised in (logic.Cancelled(), RuntimeError("a pick failed"), KeyboardInterrupt()):
        table, facts, saved = sample_model()
        before = table.snapshot()
        session = logic.BoxSession(table)

        def loop():
            logic.apply_lookup(table, session, looked_up("106_ithaca_rd"), facts, saved, ZONES)
            raise raised

        with pytest.raises(type(raised)):
            logic.run_box(session, loop)
        assert table.snapshot() == before
    table, facts, saved = sample_model()
    before = table.snapshot()
    session = logic.BoxSession(table)
    assert logic.run_box(session, lambda: (logic.apply_lookup(table, session, looked_up("106_ithaca_rd"), facts,
                                                              saved, ZONES), None)[1]) is None     # Cancel
    assert table.snapshot() == before


def test_esc_at_a_picks_prompt_changes_nothing():
    def pick():
        raise logic.Cancelled()
    assert logic.pick_or_nothing(pick, {"a": 1}, {"b": 2}) == ({"a": 1}, {"b": 2})
    assert logic.pick_or_nothing(lambda: ({"a": 9}, {}), {"a": 1}, {}) == ({"a": 9}, {})


def test_objects_held_when_rhino_closed_are_put_back_and_never_measured():
    """A box Rhino didn't finish: what it held goes back to its own layer at the next GordiumStart or GordiumCheck;
    meanwhile nothing on the holding layer is a lot, a building or a problem for the checker."""
    table = FakeTable({"sample": {"layer": "Site", "kind": "lot"}, "spot": {"layer": "Gordium::Grade", "kind": "point"}})
    table.hold("sample", "a-session-rhino-closed-on")
    table.hold("spot", "a-session-rhino-closed-on")
    assert logic.recover_held(table) == (0, 2)
    assert table.objects["sample"]["layer"] == "Site" and table.objects["spot"]["layer"] == "Gordium::Grade"
    assert logic.HOLDING_LAYER not in table.layers
    for kind, holds in (("PolylineCurve", False), ("Brep", False), ("InstanceReferenceGeometry", True)):
        assert logic.classify(logic.HOLDING_LAYER, kind, holds) is None
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    for command in ("def gordium_start():", "def gordium_check():", "def _confirm("):
        body = rhino[rhino.index(command):]
        assert body.index("_recover(doc)") < body.index("\ndef ")


def test_the_city_outline_guide_holds_the_sample_lot_until_cancel():
    table, facts, saved = sample_model()
    before = table.snapshot()
    p = looked_up("106_ithaca_rd")
    from design_checker.lookup_box import frame
    p["details"]["lot"]["source_keys"] = ["city_parcels"]
    p["writes"] = writes({"facts": p["facts"], "details": p["details"]}, frame({"facts": p["facts"]}))
    session = logic.BoxSession(table)
    f, sv, guide = logic.apply_lookup(table, session, p, facts, saved, ZONES)
    assert guide and "lot_id" not in f and not [o for o in table.objects.values() if o["layer"] == "Site"]
    session.rollback()
    assert table.snapshot() == before


def test_cancel_during_a_lookup_never_raises_before_the_rollback():
    """Round 2 (Windows): the output file was removed right after kill(); a PermissionError there skipped the
    rollback. The process is waited for, removal can't raise, the answer is set first, and run_box rolls back in
    its own handler before confirm's finally stops the lookup."""
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    kill = rhino[rhino.index("def _lookup_kill("):rhino.index("def _lookup_done(")]
    assert 'run["proc"].wait(timeout=5)' in kill
    files = rhino[rhino.index("def _lookup_files_done("):rhino.index("def _lookup_stop(")]
    assert "except OSError:" in files
    poll = rhino[rhino.index("def _lookup_poll("):rhino.index("def _lookup_files_done(")]
    assert poll.index('run["answer"] = {"status": "timeout"') < poll.index("_lookup_kill(run)")
    conf = rhino[rhino.index("def _confirm("):rhino.index("def _box_loop(")]
    assert conf.index("logic.run_box(session") < conf.index("finally:") < conf.index("_lookup_stop()")


def test_the_architects_street_line_keeps_no_looked_up_name():
    """Round 2: after Change… the looked-up (NYS Streets) name was saved as "entered by you"."""
    saved = logic.settle({"street_name": "Mitchell St", "_street_name": "Mitchell St"}, "street")
    assert "street_name" not in saved and "_street_name" not in saved
    assert logic.fact_sources({"street_source": logic.ENTERED}, "d", True)["street"]["value"] == "the highlighted line"


def test_the_overlays_gap_says_what_the_lookup_does():
    text = (REPO / "regulations/jurisdictions/new_york/ithaca_city/not_checked_yet.yaml").read_text(encoding="utf-8")
    assert "doesn't look them up" not in text and "shows the ones it finds" in text



# ---- review round 3 of PR #19 ------------------------------------------------------------------------------------

def test_crash_recovery_leaves_the_model_as_it_was_before_the_box():
    """Round 3: recovery put back what was held but left what the session drew (the looked-up lot and its USGS spot
    grades carried no mark), so grades mixed after a crash. Each drawn object carries the session's mark until
    Draw; recovery deletes those and releases the held."""
    table, facts, saved = sample_model()
    table._new("Gordium::Grade", "point")                       # an architect's spot grade
    before = table.snapshot()
    session = logic.BoxSession(table)
    logic.apply_lookup(table, session, looked_up("106_ithaca_rd"), facts, saved, ZONES)
    session.add([table._new("Gordium::Grade", "point")])         # one placed in the box too
    # Rhino closes here: no rollback, no commit; its session is no longer open. The next GordiumStart:
    logic.OPEN_SESSIONS.discard(session.token)
    # removed: the lot, its 14 spot grades and the one placed; put back: the sample lot and the architect's grade
    assert logic.recover_held(table) == (16, 2)
    assert table.snapshot() == before


def test_draw_keeps_what_it_drew_unmarked():
    table, facts, saved = sample_model()
    session = logic.BoxSession(table)
    f, _, _ = logic.apply_lookup(table, session, looked_up("106_ithaca_rd"), facts, saved, ZONES)
    session.commit()
    assert table.added_objects() == [] and logic.recover_held(table) == (0, 0) and f["lot_id"] in table.objects


def test_draw_commits_last_so_a_failure_before_it_is_rolled_back():
    """Round 3: Draw committed (deleting what was held) before the facts and sources were saved; a failure there
    lost the replaced lot for good. The save runs first; if it raises, nothing is committed and run_box rolls back."""
    table, facts, saved = sample_model()
    before = table.snapshot()
    session = logic.BoxSession(table)

    def loop():
        logic.apply_lookup(table, session, looked_up("106_ithaca_rd"), facts, saved, ZONES)

        def save():
            raise OSError("the file couldn't be written")
        return logic.draw_then_commit(session, save)

    with pytest.raises(OSError):
        logic.run_box(session, loop)
    assert table.snapshot() == before
    calls = []
    s2 = logic.BoxSession(FakeTable({}))
    s2.commit = lambda: calls.append("commit")
    assert logic.draw_then_commit(s2, lambda: calls.append("save") or "facts") == "facts" and calls == ["save", "commit"]



# ---- review round 4 of PR #19 ------------------------------------------------------------------------------------

def test_recovery_never_touches_a_start_box_still_open():
    """Round 4: Edit site… from the panel during a pick opened a second box, whose recovery deleted the open box's
    drawn objects and released what it held. Open sessions are registered; recovery touches only dead ones."""
    table, facts, saved = sample_model()
    session = logic.BoxSession(table)                               # open (not committed, not rolled back)
    f, sv, _ = logic.apply_lookup(table, session, looked_up("106_ithaca_rd"), facts, saved, ZONES)
    during = table.snapshot()
    assert logic.recover_held(table) == (0, 0) and table.snapshot() == during
    session.rollback()                                              # and that box still rolls back exactly
    assert "sample" in table.objects and table.objects["sample"]["layer"] == "Site"
    assert session.token not in logic.OPEN_SESSIONS


def test_a_dead_sessions_objects_are_recovered_while_another_box_is_open():
    table, facts, saved = sample_model()
    dead = logic.BoxSession(table)
    logic.apply_lookup(table, dead, looked_up("106_ithaca_rd"), facts, saved, ZONES)
    logic.OPEN_SESSIONS.discard(dead.token)                          # Rhino closed on it
    live = logic.BoxSession(table)
    mine = table._new("Gordium::Grade", "point")
    live.add([mine])
    assert logic.recover_held(table) == (15, 1)
    assert mine in table.objects and table.objects["sample"]["layer"] == "Site"
    live.rollback()


def test_only_one_start_box_at_a_time():
    gate = logic.BoxGate()
    assert gate.enter() and not gate.enter()                         # the second box refuses
    gate.leave()
    assert gate.enter()
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    conf = rhino[rhino.index("def confirm("):rhino.index("def _confirm(")]
    assert "or not gate.enter():" in conf and "say(logic.BOX_BUSY)" in conf and "gate.leave()" in conf
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert 'parts["box_buttons"] = buttons' in ui and "logic.controls_enabled(is_open, zoom_ok)" in ui


def test_the_recovery_message_says_what_it_did():
    assert logic.recovery_message(15, 1) == \
        "removed 15 objects an unfinished start box drew and put back 1 object it had set aside"
    assert logic.recovery_message(0, 2) == "put back 2 objects it had set aside"
    assert logic.recovery_message(0, 0) is None



# ---- verification round of PR #19 ---------------------------------------------------------------------------------

def test_a_rollback_that_fails_still_closes_its_session_so_recovery_finishes_the_job():
    """The reviewer's repro: a rollback that raised left its token live, so its held objects stayed on the holding
    layer until Rhino restarted. The token is dropped in a finally; the next start recovers what it left."""
    table, facts, saved = sample_model()
    before = table.snapshot()
    session = logic.BoxSession(table)
    logic.apply_lookup(table, session, looked_up("106_ithaca_rd"), facts, saved, ZONES)
    release = table.release

    def broken(i, layer):
        raise RuntimeError("Rhino refused to move it")
    table.release = broken
    with pytest.raises(RuntimeError):
        session.rollback()
    assert session.token not in logic.OPEN_SESSIONS
    table.release = release
    logic.recover_held(table)
    assert table.snapshot()[0] == before[0]          # every object back as it was (the layers it made may stay)


def test_while_a_start_box_is_open_no_panel_action_does_anything_but_say_so():
    """Verification round: the detail pane's buttons (Enter bedrooms…, This is the ground, Not the ground, Add to
    check…, Retry) wrote to the model mid-box and Draw overwrote them silently. Every action of the panel goes
    through one gate."""
    import re
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    body = rhino[rhino.index("def PANEL_ACTIONS():"):rhino.index("\ndef _box_open(")]
    names = re.findall(r'"(\w+)": ', body)
    assert {"enter", "add", "ground", "not_ground", "retry", "edit_site", "survey", "grade", "report", "envelope",
            "massing", "zoom"} <= set(names)
    assert "return logic.gate_actions(PANEL_ACTIONS(), _box_open, say)" in rhino
    calls, said, box = [], [], {"open": True}
    gated = logic.gate_actions({n: (lambda *a, n=n: calls.append(n)) for n in names}, lambda: box["open"], said.append)
    for n in names:
        gated[n]("an argument")
    assert calls == ["legend"] and said == [logic.BOX_BUSY] * (len(names) - 1)   # only the legend shows
    box["open"] = False
    for n in names:
        gated[n]("an argument")
    assert sorted(calls) == sorted(["legend"] + names)
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert 'list(parts.get("greyed") or [])' in ui and "logic.controls_enabled(is_open, zoom_ok)" in ui



def test_live_mode_never_rechecks_under_an_open_start_box():
    """Verification round 2: the box's own edits marked the model changed and an idle re-check during a pick wiped the
    box's overlay and the "before" statuses. The decision, by behaviour:"""
    wait = 0.5
    assert logic.should_recheck(10.0, 11.0, False, False, wait)
    assert not logic.should_recheck(10.0, 11.0, False, True, wait)        # a box open: wait for it
    assert not logic.should_recheck(10.0, 11.0, True, False, wait)        # a check running
    assert not logic.should_recheck(10.0, 10.2, False, False, wait)       # the model not still long enough
    assert not logic.should_recheck(None, 11.0, False, False, wait)       # nothing changed
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    idle = rhino[rhino.index("def _idle("):rhino.index("def documents(")]
    assert 'logic.should_recheck(t, time.time(), STATE.get("running"), _box_open(), IDLE_SECONDS,' in idle
    assert idle.index("should_recheck") < idle.index('STATE["dirty"] = None')   # the pending edit kept until then
    check = rhino[rhino.index("def run_check("):rhino.index("def _toast(")]
    assert 'if STATE.get("running") or not logic.allowed("check", _box_open()):\n        return None' in check
    save = rhino[rhino.index("def save_facts("):rhino.index("def _save_facts(")]
    assert 'if not logic.allowed("save_facts", _box_open()):' in save and "_save_facts(doc, facts)" in save
    conf = rhino[rhino.index("def confirm("):rhino.index("def _confirm(")]
    assert conf.index("gate.leave()") < conf.index('STATE["dirty"] = time.time() - IDLE_SECONDS')


def test_the_legend_stays_usable_while_a_box_is_open():
    """Verification round 2: greying the whole form also turned off the legend the gate keeps."""
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    greyed = ui[ui.index('parts["greyed"] = ['):].split("\n", 1)[0]
    assert "tree" in greyed and "ticks" in greyed and "footer.Items[0]" in greyed and "footer.Items[1]" in greyed
    assert "footer.Items[2]" not in greyed                                   # the "?" legend button
    assert "form.Content.Enabled" not in ui
    gated = logic.gate_actions({"legend": lambda: "shown"}, lambda: True, lambda m: None)
    assert gated["legend"]() == "shown"



class _Control:
    def __init__(self, enabled):
        self.Enabled = enabled


def test_closing_the_box_works_out_each_panel_control_from_the_panel_as_it_is_now():
    """Verification rounds 3-4: closing turned Zoom to on with nothing selected; then restoring a saved list put
    states on the wrong buttons after the header was rebuilt mid-box (a document switch). Now nothing is remembered:
    on closing, every control is on and Zoom to follows the panel's own rule."""
    assert logic.controls_enabled(True, True) == (False, False)              # box open: all off
    assert logic.controls_enabled(False, False) == (True, False)             # nothing selected: Zoom to stays off
    assert logic.controls_enabled(False, True) == (True, True)
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    body = ui[ui.index("def set_box_open("):ui.index("def show_detail(")]
    assert "_was_enabled" not in body and "saved" not in body                # nothing remembered by position
    assert 'zoom_ok = parts.get("selected") in (parts.get("by_id") or {}) and not parts.get("stale")' in body
    show = ui[ui.index("def show("):ui.index("def _header(")]
    assert 'parts["zoom_button"].Enabled = parts["selected"] in by_id and not parts["stale"]' in show   # same rule


def test_a_box_that_edited_is_checked_once_not_twice():
    """Verification round 3: GordiumStart's own check after the box, then live mode's idle re-check of the box's
    edits: twice. A check that finished after the edit covers it."""
    assert not logic.should_recheck(10.0, 11.0, False, False, 0.5, last_at=10.4)   # checked after the edit
    assert logic.should_recheck(10.0, 11.0, False, False, 0.5, last_at=9.0)        # the last check was before it
    assert logic.should_recheck(10.0, 11.0, False, False, 0.5)                     # no check yet
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    idle = rhino[rhino.index("def _idle("):rhino.index("def documents(")]
    assert "logic.last_check_at(STATE.get(\"checked_at\")" in idle and 'STATE["dirty"] = t = None' in idle



def test_switching_documents_with_a_pending_edit_still_rechecks_the_one_in_front():
    """Verification round 4: the new document's "no check yet" placeholder carried a time, so the pending re-check
    of the document now in front was dropped. Only a completed check of that same document counts."""
    checked_at = {"doc A": 12.0}                         # A was checked after the edit; B, now in front, never
    assert logic.last_check_at(checked_at, "doc B") is None
    assert logic.should_recheck(10.0, 13.0, False, False, 0.5, logic.last_check_at(checked_at, "doc B"))
    assert not logic.should_recheck(10.0, 13.0, False, False, 0.5, logic.last_check_at(checked_at, "doc A"))
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    check = rhino[rhino.index("def run_check("):rhino.index("def _toast(")]
    assert 'STATE.setdefault("checked_at", {})[doc.RuntimeSerialNumber] = time.time()' in check
    assert check.index('"envelope": result.get("envelope"), "at": time.time()}') < check.index('"checked_at"') < \
        check.index("except Exception")                  # only after a completed check, never on an error
    new_doc = rhino.index("def _new_document(")
    assert '"checked_at"' not in rhino[new_doc:rhino.index("\ndef ", new_doc + 10)]



# ---- eval-integrity audit (P1-5) and the gate by behaviour --------------------------------------------------------

@pytest.mark.parametrize("what", ["street", "lot", "draw_lot", "terrain", "spot", "regrade"])
def test_esc_at_any_pick_changes_nothing_and_keeps_every_doubt(what):
    """The audit: making Esc on Place spot grades wipe the ground's doubt still passed the source-text pin. Every
    pick's effect is decided in rhino_logic from what the pick gave; Esc, Enter or nothing picked changes nothing."""
    facts, saved, _ = box(_doubtful_106())
    saved = dict(saved, doubts={"lot": "x", "street": "y", "ground": "z"}, checked=[])
    for nothing in (None, [], ""):
        f2, s2 = logic.pick_effect(what, nothing, facts, saved)
        assert (f2, s2) == (facts, saved)
        assert logic.unsettled(s2) == {"lot": "x", "street": "y", "ground": "z"}


@pytest.mark.parametrize("what, outcome, row", [("street", [[0, 0], [10, 0]], "street"), ("lot", "survey-id", "lot"),
                                                 ("draw_lot", "drawn-id", "lot"), ("terrain", "terrain-id", "ground"),
                                                 ("spot", ["p1", "p2"], "ground"), ("regrade", ["p1"], "ground")])
def test_a_real_pick_settles_only_its_own_row(what, outcome, row):
    saved = {"doubts": {"lot": "x", "street": "y", "ground": "z"}, "checked": []}
    facts, after = logic.pick_effect(what, outcome, {"lot_id": "sample", "lot_surveyed": False}, saved)
    assert set(logic.unsettled(after)) == {"lot", "street", "ground"} - {row}
    if what == "lot":
        assert facts["lot_id"] == "survey-id" and facts["lot_surveyed"] is True
    if what == "draw_lot":
        assert facts["lot_surveyed"] is False and after["lot_source"] == "drawn by you"
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    pick = rhino[rhino.index("def _one_pick("):rhino.index("def confirm(")]
    assert "logic.pick_effect(what, _pick_outcome(doc, what, facts, session), facts, saved_ui)" in pick
    assert "logic.settle(" not in pick and "logic.after_ground_pick(" not in pick      # decided only in rhino_logic


def test_nothing_checks_writes_facts_or_opens_a_box_while_one_is_open():
    for action in ("check", "save_facts", "open_box"):
        assert not logic.allowed(action, True) and logic.allowed(action, False)
    assert logic.allowed("legend", True)
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert 'not logic.allowed("check", _box_open())' in rhino[rhino.index("def run_check("):]
    assert 'not logic.allowed("save_facts", _box_open())' in rhino[rhino.index("def save_facts("):]
    assert 'not logic.allowed("open_box", _box_open())' in rhino[rhino.index("def confirm("):]
