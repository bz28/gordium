"""The hand-worked scenarios (test_data/test_sites/new_york/ithaca_city/scenarios/; hand-worked by Claude before Gordium ran, not yet verified by an architect),
checked in code. The same
scenarios are drawn and checked in Rhino by apps/rhino_plugin/tests/scenarios_in_rhino.py."""
import copy

import pytest

from design_checker import present, scenarios
from design_checker.check import check_site
from host_source import host_doc, host_script

PATHS = scenarios.paths()


def test_there_are_eighteen_scenarios_each_with_working_and_a_citation():
    assert len(PATHS) == 18        # ten R-1b designs, one R-1a, one R-3a, two B-2a, one B-1b, two CBD-60, one CBD-85
    for p in PATHS:
        sc = scenarios.load(p)
        for block in [sc["expected"], (sc.get("then") or {}).get("expected") or {}]:
            for rule, want in block.items():
                assert want["status"] in scenarios.CAUTION and want.get("working") and want.get("cites"), (p.name, rule)


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_gordium_gives_the_answer_key_or_a_disagreement_already_investigated(path):
    sc = scenarios.load(path)
    known = sc.get("disagreements") or {}
    for step in scenarios.run(sc):
        for r in step["rows"]:
            if r["match"]:
                assert r["rule"] not in known, f"{r['rule']} now matches: drop it from disagreements"
                continue
            assert r["rule"] in known, f"{path.stem} {step['step']}: {r['rule']} {r['why']}"
            assert known[r["rule"]]["gordium"] == r["gordium"], f"{r['rule']}: Gordium now says {r['gordium']}"
            assert known[r["rule"]].get("finding") and known[r["rule"]].get("question_for_architects")


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_never_a_false_pass(path):
    """Where the hand-worked result says a rule does not comply, Gordium never says it complies: no exceptions."""
    sc = scenarios.load(path)
    for step in scenarios.run(sc):
        for r in step["rows"]:
            assert not (r["expected"] == present.FAILS and r["gordium"] == present.COMPLIES), (path.stem, r)


def _items(name):
    s, f, extras = scenarios.site(scenarios.load(scenarios.FOLDER / name))
    return {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}


def test_a_rule_with_two_ways_to_comply_says_how_each_falls_short_and_both_fixes():
    h = _items("04_height_bonus_some_yards_increased.yaml")["Building height"]
    assert h["status"] == present.FAILS
    assert h["reason"] == ("Does not comply either way the rule allows: Building height 37'-0\", needs ≤ 35'-0\"; "
                           "or Rear yard 30'-0\", needs ≥ 32'-0\"")
    # moving the whole house forward would take the 2 ft from the front yard, which the bonus needs too
    assert h["hint"] == "To comply: lower the building 2'-0\", or make the rear yard 2'-0\" deeper, keeping the other yards."


def test_an_overhanging_floor_block_is_part_of_the_building_for_yards_and_coverage():
    v = _items("10_one_floor_moved_on_its_own.yaml")
    # the second floor block sticks out 3 ft: a story (yards_to_nearest_part), so the yard is to it, 60 − 48 = 12
    assert (v["Side yard, East"]["proposed"], v["Side yard, East"]["status"]) == ("12'-0\"", present.COMPLIES)
    assert v["Side yard, East"]["points"]
    # coverage counts the overhanging floor (the coverage_seen_from_above finding): 1,320 of 7,200 sf, rounded up
    assert v["Lot coverage"]["proposed"] == "18.4%"
    assert v["Lot coverage"]["required"] == "25%"                    # the limit in the same unit, never sf


def test_a_design_using_the_height_bonus_shows_the_bonus_limit_and_the_raised_yards():
    v = _items("03_height_bonus_every_yard_increased.yaml")
    h = v["Building height"]
    assert (h["status"], h["required"], h["margin"], h["hint"]) == (present.COMPLIES, "38'-6\"", "+1'-6\"", None)
    assert "Front yard ≥ 27'-0\"; Side yards ≥ 12'-0\"; Rear yard ≥ 32'-0\"" in h["reason"]
    for name, req in (("Front yard", "27'-0\""), ("Side yard, West", "12'-0\""), ("Rear yard", "32'-0\"")):
        assert (v[name]["required"], v[name]["margin"]) == (req, "at limit"), name   # not "+2'-0"": the bonus needs it
        assert v[name]["delta"] == "at limit", name             # round 1: the Delta is the raised one's too


def test_a_fix_is_never_rounded_short():
    c = _items("05_coverage_one_square_foot_over.yaml")["Lot coverage"]
    assert c["hint"] == "To comply: reduce the footprint by at least 1 sf."     # 1 sf over, never "0.01%"
    assert present._gap(-0.01, "ft") == "0'-0 1/8\""                            # up, never down to nothing
    assert present._gap(-2.0001, "ft") == "2'-0 1/8\""


def test_the_tax_map_worst_case_applies_to_the_lot_area_too():
    v = _items("08_tax_map_lot_front_yard_within_two_feet.yaml")
    assert v["Lot area"]["status"] == present.COMPLIES
    assert "worst case (lot area 6,496 sf)" in v["Lot area"]["reason"]          # every line 2 ft in: 56 × 116
    assert v["Front yard"]["status"] == present.REVIEW                         # 26 ft: at worst 24 ft


def test_chart_quotes_are_the_districts_own_cell_never_a_whole_row():
    quotes = [q["text"] for q in _items("05_coverage_one_square_foot_over.yaml")["Lot area"]["detail"]["quotes"]]
    assert "Minimum Lot Size · One-family dwelling, detached · R-1B: 6,000 sf" in quotes   # the panel adds the quote marks
    assert not any("10,000 sf 6,000 sf 5,000 sf" in q or q.startswith("R-1A R-1B") for q in quotes)


def _garage(touching: bool):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "06_detached_garage_not_on_the_building_layer.yaml"))
    if touching:                                   # a porch drawn on the wrong layer, against the front wall
        sc["others"] = [{"id": "porch", "outline": [[20, 22], [40, 22], [40, 30], [20, 30]], "base": 0, "top": 10}]
    s, f, extras = scenarios.site(sc)
    return {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}


def test_a_solid_left_out_makes_coverage_need_review_and_one_touching_the_building_the_yards_too():
    detached = _garage(False)
    assert detached["Lot coverage"]["status"] == present.REVIEW
    assert "lot coverage counts every building" in detached["Lot coverage"]["reason"]
    # standing apart, it may be a freestanding deck (§325-18A): the yards wait too, never a pass (test_objects_apart)
    assert detached["Front yard"]["status"] == present.REVIEW and "stands apart" in detached["Front yard"]["reason"]
    assert detached["Building height"]["status"] == present.REVIEW       # its rule reads the yards (§325-16C)
    assert detached["Stories"]["status"] == present.COMPLIES             # a freestanding deck adds no story
    attached = _garage(True)
    for name in ("Front yard", "Rear yard", "Building height", "Stories"):
        assert attached[name]["status"] == present.REVIEW, name
        assert "touching the building" in attached[name]["reason"]


def _bonus(surveyed):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "03_height_bonus_every_yard_increased.yaml"))
    sc["lot"]["surveyed"] = surveyed
    s, f, extras = scenarios.site(sc)
    return {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}


def test_raised_yards_keep_their_detail_and_on_a_tax_map_lot_need_review_and_say_why():
    v = _bonus(True)
    assert v["Front yard"]["detail"]["line"] == "27'-0\" proposed ≥ 27'-0\" required · at the limit"   # not +2'-0"
    t = _bonus(False)
    assert t["Building height"]["status"] == present.REVIEW
    assert "at worst Front yard 25'-0\" against 27'-0\"" in t["Building height"]["reason"]   # the part that fails
    assert t["Front yard"]["status"] == present.REVIEW and t["Front yard"]["required"] == "27'-0\""
    assert t["Front yard"]["delta"] == (    # round 1: the raised 27'-0", the line ±2'-0": at it as drawn, 2'-0" short
        "at limit if confirmed (2'-0\" short if the tax-map lines are 2 ft off)")    # in review: never read as a pass


def test_a_chart_heading_row_is_quoted_in_its_own_words():
    quotes = [q["text"] for q in _bonus(True)["Building height"]["detail"]["quotes"]]
    assert "Maximum Building Height [fn10]" in quotes and not any(q.endswith("R-1B: ") for q in quotes)


def test_a_zero_side_yard_is_never_named_by_a_direction_it_doesnt_have():
    zero = {"side_yard_smaller": {"points": [[0, 40], [0, 40]]}, "side_yard_larger": {"points": [[50, 40], [35, 40]]}}
    assert present._side_name("side_yard_smaller", zero) == "Side yard, narrower"


def test_the_height_detail_has_the_definitions_every_spot_grade_and_a_section(  # spec E5
):
    v = _items("07_spot_grades_on_a_slope_then_the_house_moves.yaml")
    d = v["Building height"]["detail"]
    terms = [t["term"] for t in d["definitions"]]
    assert terms == ["HEIGHT OF BUILDING", "GRADE PLANE"]
    assert "average of finished ground level on each side of the building" in d["definitions"][1]["text"]
    assert d["spots"][0] == "(30'-0\", 29'-0\") · elevation 1'-0\"" and len(d["spots"]) == 4
    dg = d["diagram"]
    assert dg["label"] == "Diagram, not to scale" and dg["height"] == 30 and dg["limit"] == 35
    assert dg["text"]["height"] == "30'-0\"" and dg["text"]["front"] == "30'-0\""
    assert d["zoom_note"] == "Zoom to opens the front elevation"


def _bonus_at(outline, floors=None):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "03_height_bonus_every_yard_increased.yaml"))
    sc["lot"]["surveyed"] = False
    sc["buildings"][0]["outline"] = outline
    if floors:
        sc["buildings"][0]["floors"] = floors
    s, f, extras = scenarios.site(sc)
    return {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}


def test_a_raised_rear_yard_gets_the_full_tax_map_worst_case_lot_depth_too():
    v = _bonus_at([[14, 30], [46, 30], [46, 85.8], [38, 85.8], [38, 50], [14, 50]])     # rear 34.2, needs 32
    # at worst: 2 ft nearer the rear line (32.2) and the lot 4 ft deeper (each side line 2 ft longer): needs 33
    assert v["Rear yard"]["status"] == present.REVIEW and "33'-0\"" in v["Rear yard"]["reason"]


def test_a_yard_already_in_review_is_raised_too():
    v = _bonus_at([[14, 26.5], [46, 26.5], [46, 85], [38, 85], [38, 46.5], [14, 46.5]], [12, 12, 12])   # 36 ft
    f = v["Front yard"]
    assert f["status"] == present.REVIEW and f["required"] == "26'-0\"" and f["margin"] == "+0'-6\""
    assert f["delta"] == (                       # round 1: 26'-6" against the raised 26'-0", ±2'-0"
        "+0'-6\" if confirmed (1'-6\" short if the tax-map lines are 2 ft off)")
    assert "against 26'-0\"" in f["reason"]


def test_nothing_is_left_out_of_the_check_on_a_guess_that_it_is_the_ground():
    """One mesh holding a garage and a shed spreads over most of a 50 × 100 lot (box 50 × 60): it still counts,
    and doesn't even look like the ground. Only an open surface spanning the whole lot looks like it, and even that
    stays left out (needs review) until the architect says "This is the ground"."""
    from design_checker.rhino_logic import could_be_building, looks_like_ground
    lot = (0, 0, 50, 100)
    assert could_be_building("Mesh", solid=False, faces=400)                            # the garage + shed mesh
    assert not looks_like_ground("Mesh", False, (0, 40, 50, 100), lot)
    assert could_be_building("Brep", solid=True, faces=6)
    assert not looks_like_ground("Brep", True, (-5, -5, 55, 105), lot)                  # a closed solid: never
    assert could_be_building("Mesh", solid=False, faces=5000)                           # the topography: counted…
    assert looks_like_ground("Mesh", False, (-10, -10, 60, 110), lot)                   # …and offered as the ground


def test_a_left_out_object_spreading_over_the_lot_still_makes_coverage_need_review():
    """Round 4: the 50 × 100 lot, a 1,000 sf house (20%), and one mesh holding a 400 sf garage and a 100 sf shed
    (30% together: does not comply). The mesh is left out; coverage must not read complies."""
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "06_detached_garage_not_on_the_building_layer.yaml"))
    sc["lot"]["points"] = [[0, 0], [50, 0], [50, 100], [0, 100]]
    sc["buildings"][0]["outline"] = [[15, 30], [35, 30], [35, 80], [15, 80]]
    sc["others"] = [{"id": "garage_and_shed", "outline": [[0, 80], [20, 80], [20, 100], [0, 100]], "base": 0, "top": 10}]
    s, f, extras = scenarios.site(sc)
    v = {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}
    assert v["Lot coverage"]["status"] == present.REVIEW
    assert v["Objects on the lot not included"]["status"] == present.REVIEW


def test_the_comparison_fails_on_a_crash_a_missing_scenario_or_an_unlisted_disagreement(tmp_path, capsys):
    """eval-integrity P1-4: a crashed Rhino run once printed an empty table, "0 disagreement(s)" and exited 0."""
    import json
    crashed = tmp_path / "crashed.json"
    crashed.write_text(json.dumps({"trace": "Traceback: boom", "scenarios": {}}), encoding="utf-8")
    assert scenarios.main(["rhino", str(crashed)]) == 1
    out = capsys.readouterr().out
    assert "the run crashed" in out and "no result for 'as drawn'" in out
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"scenarios": {}}), encoding="utf-8")
    assert scenarios.main(["rhino", str(empty)]) == 1
    every = {p.stem: scenarios.load(p) for p in PATHS}
    name = PATHS[0].stem
    row = {"rule": "R-1b.front_yard", "expected": "complies", "gordium": "does not comply", "match": False, "why": ""}
    results = {n: [{"step": s, "rows": [{**row, "match": True}]} for s in scenarios.steps_expected(sc)]
               for n, sc in every.items()}
    assert scenarios.failures(results, every) == []
    results[name][0]["rows"] = [row]
    assert scenarios.failures(results, every) == [f"{name} as drawn: R-1b.front_yard expected complies, "
                                                  "Gordium does not comply"]


def test_the_code_comparison_passes_with_only_investigated_disagreements(capsys):
    assert scenarios.main([]) == 0
    assert "OK: every scenario and step ran and agrees" in capsys.readouterr().out


def test_the_scenarios_are_never_called_an_architects_answer_key():
    """eval-integrity P1-3: the scenarios were worked by Claude, not an architect; every place that describes them
    says so, and nothing calls them an architect's answer key until an architect has reviewed them."""
    from rule_format.rulebook import REPO
    folder = REPO / "test_data/test_sites/new_york/ithaca_city/scenarios"
    readme = (folder / "README.md").read_text(encoding="utf-8")
    assert "Not yet verified by an architect" in readme and "Claude" in readme
    places = [folder / "README.md", *sorted(folder.glob("*.yaml")), REPO / "packages/design_checker/design_checker/scenarios.py",
              REPO / "packages/design_checker/tests/test_scenarios.py", REPO / "docs/README.md"]
    texts = {p.name: p.read_text(encoding="utf-8") for p in places}
    texts["README.md (plugin)"] = host_doc("rhino", "README.md", purpose="wiring")
    texts["scenarios_in_rhino.py"] = host_script("rhino", "scenarios_in_rhino.py", purpose="wiring")
    for name, text in texts.items():
        text = text.lower().split("def test_the_scenarios_are_never_called")[0]
        for phrase in ("architect's answer key", "architects' answer key", "the answer key"):
            assert phrase not in text, (name, phrase)


LESS_CAUTIOUS = [(p, rule) for p in PATHS for rule, d in (scenarios.load(p).get("disagreements") or {}).items()
                 if d.get("direction") == "gordium_less_cautious"]
NOT_YET = {}      # 09's rear yard: PR #18 measures every lot-line reading, and 09 now agrees (needs review)


@pytest.mark.parametrize("path, rule", [
    pytest.param(p, r, marks=pytest.mark.xfail(strict=True, reason=NOT_YET[(p.stem, r)]) if (p.stem, r) in NOT_YET else ())
    for p, r in LESS_CAUTIOUS], ids=[f"{p.stem}:{r}" for p, r in LESS_CAUTIOUS])
def test_a_less_cautious_disagreement_rests_on_what_gordium_evaluated(path, rule):
    """eval-integrity P1-2: where the hand-worked result says needs review and Gordium says complies, a written
    justification isn't enough (09's worked a reading by hand that Gordium never evaluates). Each must list
    relies_on, and each item is re-checked here: a smaller lot (Gordium must still say complies there, surveyed),
    or a measurement Gordium must have worked out under every lot-line reading."""
    sc = scenarios.load(path)
    relies = (sc["disagreements"][rule] or {}).get("relies_on")
    assert relies, f"{path.stem} {rule}: Gordium is less cautious here; list what it relies_on"
    s, f, extras = scenarios.site(sc)
    measured = check_site(s, f, extras=extras)["measurements"]
    for item in relies:
        assert item.get("why"), item
        if "lot" in item:
            smaller = copy.deepcopy(sc)
            smaller["lot"] = {"points": item["lot"], "surveyed": True}
            s2, f2, e2 = scenarios.site(smaller)
            rows = scenarios.rule_rows(check_site(s2, f2, extras=e2)["view"], rule)
            assert rows and all(r["status"] == present.COMPLIES for r in rows), (path.stem, rule, item["why"])
        else:
            m = measured.get(item["measure"]) or {}
            assert item.get("every_lot_line_reading") and len(m.get("readings") or []) >= 2, \
                f"{path.stem} {rule}: Gordium doesn't work {item['measure']} under every reading ({item['why']})"
