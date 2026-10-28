"""Queue item 12: real City of Ithaca lots with results worked out by hand from the law (not from Gordium's code).

Deep run (test_data/test_sites/new_york/ithaca_city/deep_run/): one full design per district family (R-1, R-2,
R-3/RU) on a real tax lot, every rule that applies worked out by hand; checked here headless with the scenario
machinery, and in Rhino by apps/rhino_plugin/tests/deep_run_in_rhino.py.
Light run (light_run/expected.yaml): one real address per district, for the in-Rhino start flow
(apps/rhino_plugin/tests/light_run_in_rhino.py, live lookups); checked here for completeness and licensing only."""
import json

import pytest
import yaml

from design_checker import scenarios
from design_checker.check import check_site
from rule_format.rulebook import REPO

DEEP = scenarios.paths(scenarios.SITES)
LIGHT = REPO / "test_data/test_sites/new_york/ithaca_city/light_run"
DISTRICTS = ["R-1a", "R-1b", "R-2a", "R-2b", "R-2c", "R-3a", "R-3aa", "R-3b", "RU"]


def test_one_deep_site_per_district_family_each_rule_with_working_and_a_citation():
    families = sorted(scenarios.load(p)["district"][:3] for p in DEEP)
    assert families == ["R-1", "R-2", "R-3"]
    for p in DEEP:
        sc = scenarios.load(p)
        for block in [sc["expected"], (sc.get("then") or {}).get("expected") or {}]:
            for rule, want in block.items():
                assert want["status"] in scenarios.CAUTION and want.get("working") and want.get("cites"), (p.name, rule)


@pytest.mark.parametrize("path", DEEP, ids=[p.stem for p in DEEP])
def test_every_rule_gordium_shows_has_a_hand_worked_answer(path):
    """'Every rule's expected answer': each rule row Gordium shows for the design as drawn is worked out by hand."""
    sc = scenarios.load(path)
    s, f, extras = scenarios.site(sc)
    view = check_site(s, f, extras=extras)["view"]
    shown = {i["rule"] for i in view["items"] if i.get("rule")}
    assert shown == set(sc["expected"]), (sorted(shown - set(sc["expected"])), sorted(set(sc["expected"]) - shown))


@pytest.mark.parametrize("path", DEEP, ids=[p.stem for p in DEEP])
def test_gordium_gives_the_hand_worked_answer(path):
    sc = scenarios.load(path)
    known = sc.get("disagreements") or {}
    for step in scenarios.run(sc):
        for r in step["rows"]:
            if r["match"]:
                assert r["rule"] not in known, f"{r['rule']} now matches: drop it from disagreements"
            assert r["match"] or (known.get(r["rule"]) or {}).get("gordium") == r["gordium"], \
                f"{path.stem} {step['step']}: {r['rule']} expected {r['expected']}, Gordium {r['gordium']} ({r['why']})"


@pytest.mark.parametrize("path", DEEP, ids=[p.stem for p in DEEP])
def test_never_a_false_pass(path):
    sc = scenarios.load(path)
    for step in scenarios.run(sc):
        for r in step["rows"]:
            assert not (r["expected"] == "does_not_comply" and r["gordium"] == "complies"), (path.stem, r)


def test_the_light_run_has_one_real_address_per_district_with_a_nudge_that_must_fail():
    doc = yaml.safe_load((LIGHT / "expected.yaml").read_text(encoding="utf-8"))
    assert list(doc["sites"]) == DISTRICTS
    for district, site in doc["sites"].items():
        assert site["zone"]["expect"] == district and site["parcel"].startswith("500700-")   # City of Ithaca SWIS
        assert site["lot"]["corner_lot"] == "no" and site["lot"]["area_sf"] > 0
        nudge = site["expected"]["nudge"]
        assert nudge["rule"] == f"{district}.front_yard" and nudge["status"] == "does_not_comply"
        assert nudge["proposed_ft"] == nudge["required_ft"] - 3                # beyond the ±2 ft tax-map tolerance
        assert site["expected"]["largest_house"].startswith("limited by")


def test_the_light_run_keeps_only_what_each_source_allows():
    """The saved lookups are site_lookup's snapshots: the City's zoning, roads and overlays and the County's points
    are used live and never kept (their terms); the State's parcels and USGS ground are kept."""
    for district in DISTRICTS:
        snap = json.loads((LIGHT / "lookups" / f"{district}.json").read_text(encoding="utf-8"))
        for name in ("zone", "street_side", "corner_lot", "overlays"):
            assert snap["facts"][name]["value"] == "(used live, not stored)", (district, name)
        assert snap["facts"]["lot"]["value"]["outline_ft"]


# Review round 1 (cold reviewer + 2 sceptics).

def test_each_drawn_solid_knows_its_design_building_so_rhino_can_map_stated_ids():
    """In Rhino the garage gets a GUID: scenarios_in_rhino.draw maps the stated accessory id to it through `building`."""
    sc = scenarios.load(scenarios.SITES / "r1_111_eastwood_ave.yaml")
    garage = [s for s in scenarios.solids(sc)["buildings"] if s["building"] == "garage"]
    assert len(garage) == 1 and garage[0]["name"] == "garage"
    assert {s["building"] for s in scenarios.solids(sc)["buildings"]} == {"house", "garage"}
    draw = (REPO / "apps/rhino_plugin/tests/scenarios_in_rhino.py").read_text(encoding="utf-8")
    assert 'guids.get(b, [b])' in draw and 'facts["accessory_buildings"] = ' in draw


def test_the_deep_run_wrapper_never_leaves_its_folder_set():
    src = (REPO / "apps/rhino_plugin/tests/deep_run_in_rhino.py").read_text(encoding="utf-8")
    assert "finally:" in src and 'os.environ.pop("GORDIUM_SCENARIO_FOLDER", None)' in src


def test_the_largest_house_names_the_chart_notes_that_may_limit_it():
    doc = yaml.safe_load((LIGHT / "expected.yaml").read_text(encoding="utf-8"))
    assert "note 13" in doc["sites"]["RU"]["expected"]["largest_house"]
    assert "note 2" in doc["sites"]["R-3aa"]["expected"]["largest_house"]


def test_the_light_run_nudge_measures_to_every_street_line():
    src = (REPO / "apps/rhino_plugin/tests/light_run_in_rhino.py").read_text(encoding="utf-8")
    assert "for ln in street_lines(facts)" in src and "street_line\"][0]" not in src



# Review round 2.

def test_the_drawn_area_is_the_area_of_the_stored_corners():
    """Rhino draws the lot from the stored corners (to 0.01 ft): the light run compares with their area, not the
    lookup's unrounded area_sf (R-2a differs by 1.16 sf)."""
    doc = yaml.safe_load((LIGHT / "expected.yaml").read_text(encoding="utf-8"))
    for district, site in doc["sites"].items():
        pts = json.loads((LIGHT / "lookups" / f"{district}.json").read_text(encoding="utf-8"))["facts"]["lot"]["value"]["outline_ft"]
        n = len(pts)
        area = abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2
        assert abs(site["lot"]["drawn_area_sf"] - area) < 0.01, district
    src = (REPO / "apps/rhino_plugin/tests/light_run_in_rhino.py").read_text(encoding="utf-8")
    assert 'lot["drawn_area_sf"]' in src and 'lot["area_sf"]) <= 0.5' not in src


def test_rus_green_space_cap_uses_the_area_the_yards_leave():
    doc = yaml.safe_load((LIGHT / "expected.yaml").read_text(encoding="utf-8"))
    assert "5,746.0 − 2,873.0 = 2,873.0" in doc["sites"]["RU"]["expected"]["largest_house"]



# Review round 3.

def test_the_sites_table_runs_from_the_command_line(capsys):
    assert scenarios.main(["--sites"]) == 0
    out = capsys.readouterr().out
    assert "r1_111_eastwood_ave" in out and "r3_423_n_cayuga_st" in out and "01_every_limit_at_the_line" not in out


def test_the_sites_rhino_comparison_reads_the_deep_run(tmp_path, capsys):
    """`--sites rhino <out.json>` judges a Rhino run against the deep-run sites (here: an empty run must fail)."""
    ran = tmp_path / "rhino_out.json"
    ran.write_text(json.dumps({"scenarios": {}}), encoding="utf-8")
    assert scenarios.main(["--sites", "rhino", str(ran)]) == 1
    assert "r2_316_e_falls_st: no result for 'as drawn'" in capsys.readouterr().out


def test_each_deep_site_names_the_parcel_its_light_run_lookup_found():
    """Each deep-run lot is traceable to its tax parcel: the id in its description is the one the stored lookup for
    the same address returned (the light run uses the same three addresses)."""
    import re
    light = yaml.safe_load((LIGHT / "expected.yaml").read_text(encoding="utf-8"))["sites"]
    for p in DEEP:
        sc = scenarios.load(p)
        found = re.findall(r"parcel (500700-[\d.]+-\d+-\d+)", sc["what"])
        assert found == [light[sc["district"]]["parcel"]], (p.name, found)


@pytest.mark.parametrize("path", DEEP, ids=[p.stem for p in DEEP])
def test_every_measured_row_has_its_numbers_worked_by_hand(path):
    """Status alone would let a measurement off by feet 'match' on a wide margin: every row Gordium shows with a
    number has the hand-worked proposed and required values written down, in both steps."""
    sc = scenarios.load(path)
    for moved, expected in [(False, sc["expected"]), (True, (sc.get("then") or {}).get("expected") or {})]:
        if not expected:
            continue
        s, f, extras = scenarios.site(sc, moved)
        view = check_site(s, f, extras=extras)["view"]
        for i in view["items"]:
            # R-1a's occupancy row shows the rule's first limit (1 unrelated person), which this design meets; the
            # law's limit for an owner-occupied R-1 house is 2 (§325-3B DWELLING, ONE-FAMILY), so a hand-worked
            # [1, 2] can't be compared with the display: its count is checked through the status only
            if i.get("rule") in expected and scenarios.number(i.get("proposed")) and \
                    i["rule"] != "R-1a.occupancy_one_family":
                name = (i.get("id") or "").partition("#")[2] or "row"
                assert name in (expected[i["rule"]].get("values") or {}), (path.stem, moved, i["id"])


def test_a_house_off_by_feet_on_a_wide_margin_is_caught():
    """The 111 Eastwood house moved 5 ft east: every status stays the same, but the side yards no longer match the
    hand-worked 29.98 / 30.01 ft."""
    sc = scenarios.load(next(p for p in DEEP if p.stem == "r1_111_eastwood_ave"))
    for b in sc["buildings"]:
        if b["id"] == "house":
            b["outline"] = [[x + 5, y] for x, y in b["outline"]]
    rows = {r["rule"]: r for r in scenarios.run(sc)[0]["rows"]}
    assert rows["R-1a.side_yards"]["gordium"] == "complies" and not rows["R-1a.side_yards"]["match"]
    assert "worked by hand 29.98" in rows["R-1a.side_yards"]["why"]


def test_displayed_values_read_back_as_numbers():
    assert scenarios.number("29'-11 5/8\"") == (29 + 11.625 / 12, 0.125 / 12)
    assert scenarios.number("12,990 sf") == (12990.0, 1.0) and scenarios.number("18.8%") == (18.8, 0.1) and scenarios.number("20%", "required") == (20.0, 0.0)
    assert scenarios.number("-0'-6\"") == (-0.5, 0.125 / 12) and scenarios.number("-1'-6\"")[0] == -1.5
    assert scenarios.number("3") == (3.0, 0.0) and scenarios.number("—") is None


def test_the_light_run_nudge_claims_its_distance_and_numbers():
    """light_run_in_rhino.py runs only in Rhino; here its feet reader is run and its nudge claims are read: the house's
    measured front yard after the move, and the row's proposed and required values, are claimed against
    proposed_ft / required_ft (not only the status)."""
    import ast
    src = (REPO / "apps/rhino_plugin/tests/light_run_in_rhino.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "feet")
    ns = {}
    exec(compile(ast.Module([fn], []), "feet", "exec"), ns)
    assert ns["feet"]("22'-0 1/8\"") == 22 + 0.125 / 12 and ns["feet"]("25'-0\"") == 25 and ns["feet"]("—") is None
    assert ns["feet"]("-0'-6\"") == -0.5
    # the house is found as the plugin finds building objects (GordiumStart draws it on Gordium::Massing, not on
    # the Building layer), or the nudge never runs
    massing = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "massing")
    assert "g._buildings(doc)" in ast.get_source_segment(src, massing)
    assert 'abs(now - nudge["proposed_ft"]) <= 0.1' in src
    assert 'abs(a - nudge["proposed_ft"])' in src and 'abs(b - nudge["required_ft"])' in src


def test_a_percent_rounded_up_one_step_still_matches():
    """Gordium rounds a proposed percent up (cautious) and drops trailing zeros: 18.71% shows as 18.8% and 18.95% as
    19%, and both must still match; a required percent is the law's figure and must match exactly."""
    rows = [{"id": "X.lot_coverage", "proposed": "18.8%", "required": "20%"}]
    assert scenarios.values_problems(rows, {"row": [18.71, 20]}) == []
    assert scenarios.values_problems(rows, {"row": [18.6, 20]})            # two steps off is a mismatch
    assert scenarios.values_problems([{"id": "X", "proposed": "19%", "required": "35%"}], {"row": [18.95, 35]}) == []
    assert scenarios.values_problems([{"id": "X", "proposed": "19%", "required": "35%"}], {"row": [18.95, 34.9]})
    near = [{"id": "X", "proposed": "25.02%", "required": "25%"}]     # 2 places near the limit: a step of 0.01
    assert scenarios.values_problems(near, {"row": [25.015, 25]}) == []
    assert scenarios.values_problems(near, {"row": [24.95, 25]})
    assert scenarios.values_problems([{"id": "X", "proposed": "24.95%", "required": "25%"}], {"row": [25.01, 25]})


def test_the_light_run_finds_rows_by_the_id_the_plugin_keeps():
    """The plugin's STATE["last"] items keep "id" but not "rule" (gordium_rhino.py, STATE["last"]): the light run's
    row lookup must work from the id, or the nudge's row is never found."""
    import ast
    src = (REPO / "apps/rhino_plugin/tests/light_run_in_rhino.py").read_text(encoding="utf-8")
    fns = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name in ("row_for", "rule_of")]
    ns = {}
    exec(compile(ast.Module(fns, []), "rows", "exec"), ns)
    items = [{"id": "R-1a.front_yard", "status": "does_not_comply"}, {"id": "R-1a.side_yards#east", "status": "complies"}]
    assert ns["row_for"](items, "R-1a.front_yard") == items[:1]
    assert ns["row_for"](items, "R-1a.side_yards") == items[1:]
