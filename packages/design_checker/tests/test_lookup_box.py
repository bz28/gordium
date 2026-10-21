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
    assert 'STATE["lookup_guide"]' in body and "AddCurve" not in body.split('elif w.get("guide_ring")')[1]


def test_the_lookup_runs_in_its_own_process_and_prints_one_line(capsys):
    assert main(["106 Ithaca Rd, Ithaca, NY 14850", "--fixture", "106_ithaca_rd"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and json.loads(out[0])["status"] == "found"
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert '"-m", "design_checker.lookup_box", address' in rhino and "logic.LOOKUP_LIMIT_S" in rhino
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
    assert "logic.after_ground_pick(saved_ui, what, len(placed))" in rhino and "    return placed" in rhino


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


def test_p1_a_lookup_never_replaces_the_architects_own_lot():
    """(C) Only the lot a lookup or the sample drew may be replaced; a survey picked, or a lot drawn or picked by the
    architect, never (its id is no longer the replaceable one)."""
    saved = {"replaceable_lot": "sample-lot"}
    assert logic.lookup_may_replace({"lot_id": "sample-lot"}, saved)
    assert logic.lookup_may_replace({}, saved)
    picked = logic.settle(saved, "lot")                 # Use my survey… / Draw my lot… / Pick survey lot lines…
    assert not logic.lookup_may_replace({"lot_id": "survey"}, picked)
    assert not logic.lookup_may_replace({"lot_id": "sample-lot"}, picked)
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert "replaceable_lot=sample_lot" in rhino and 'saved_ui = logic.settle(_ui_state(doc), "lot")' in rhino


def test_p1_the_start_box_is_one_transaction():
    """(C) Every model edit the box makes is recorded (added, or removed with its serial number), and Cancel undoes
    them all; nothing in the lookup or a pick deletes an object any other way."""
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    done = rhino[rhino.index("def _lookup_done("):rhino.index("def _drawn(")]
    assert "doc.Objects.Delete(" not in done and "_session_remove(doc, saved_ui, old)" in done
    assert done.count("_session_add(saved_ui, ") == 2                 # the lot and its spot grades
    pick = rhino[rhino.index("def _box_pick("):rhino.index("def confirm(")]
    assert "doc.Objects.Delete(" not in pick and "_session_add(saved_ui, placed)" in pick
    assert "_session_add(saved_ui, [drawn])" in pick
    conf = rhino[rhino.index("def confirm("):rhino.index("def _lookup_start(")]
    assert conf.index("_rollback(doc, saved_ui)") < conf.index("return None")
    rb = rhino[rhino.index("def _rollback("):rhino.index("def _draw_lot(")]
    assert "doc.Objects.Undelete(serial)" in rb


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
    assert 'elif what == "draw_lot":' in rhino and '"lot_missing": lot is None' in rhino


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
