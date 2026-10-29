"""Only the offending part is coloured (Ben, 2026-10-21): what the viewport draws for a coloured block, and the
legend that explains it. The blocks themselves (per building, a roof's ridge) are pinned in test_present.py."""

from design_checker import rhino_logic as logic


def test_a_block_draws_the_buildings_own_part_inside_it():
    assert logic.offending_pieces(["the cantilever"], "the block") == ["the cantilever"]
    assert logic.offending_pieces(["a", None, "b"], "the block") == ["a", "b"]


def test_a_block_reaches_the_real_solids_top_a_vault_the_checker_cannot_read_is_coloured_whole():
    """The Rhino check of #28 at fc0b023: walls to 36 ft, a curved vault to 42 ft, the limit 35 ft. The checker
    reads only the walls (the curved roof is left out: height needs review), so its height block ran to 36 ft and
    only the 35-36 ft band was coloured. The block now reaches the real solid's top; a height block still starts
    at the limit; a yard strip reaches the solid's own bottom too."""
    height = {"why": "height", "base": 35.0, "top": 36.0}
    assert logic.block_span(height, 0.0, 42.0) == (35.0, 42.0)
    assert logic.block_span(height) == (35.0, 36.0)            # no solid Rhino can draw: the checker's
    yard = {"why": "yard", "base": 1.0, "top": 36.0}
    assert logic.block_span(yard, 0.5, 42.0) == (0.5, 42.0)
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    body = src[src.index("def _offending("):src.index("def _actions(")]
    assert "logic.block_span(e," in body and "_prism(doc, e[\"outline\"], base, top)" in body


def test_a_failed_intersection_still_colours_the_block_never_nothing():
    # Rhino's boolean gives None when it fails, an empty list when it finds nothing (a mesh or a solid it can't cut
    # is never intersected): the failing part stays coloured either way
    for pieces in (None, [], [None]):
        assert logic.offending_pieces(pieces, "the block") == ["the block"]


def test_rhinos_boolean_runs_only_under_the_guard_so_a_failed_cut_never_stops_the_check():
    """A RhinoCommon error in the cut colours the whole block (offending_pieces' fallback); unguarded it would end
    the check's drawing before its results are kept (review round 2)."""
    import re
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    calls = [m.start() for m in re.finditer(r"CreateBooleanIntersection", src)]
    assert calls, "the cut is gone: update this pin"
    for at in calls:
        assert "logic.guard(lambda: rg.Brep." in src[max(0, at - 40):at], src[at - 80:at + 40]


def test_the_legend_says_red_is_every_reading_amber_some_and_nothing_where_it_complies():
    text = logic.legend_text()
    assert "only the offending part" in text
    assert "RED: it fails there under every reading" in text
    assert "AMBER: it fails there under some readings only" in text and "2'-0\"" in text
    assert "Nothing where it complies" in text
    assert "a roof's ridge, not its eaves" in text and "a cantilever, not the ground under it" in text
    # only solids are cut (gordium_rhino._offending): the legend says so (review round 1, H2)
    assert "a mesh, or a solid Rhino can't cut, is coloured over its whole strip instead" in text
    # a block instance is never measured (a setup problem: explode it): never said to be coloured (review of #28, P2)
    assert "block instance is coloured" not in text and "a block isn't measured until it is exploded" in text


def test_the_scenarios_count_regions_as_the_plan_shows_them_not_blocks_per_floor():
    from design_checker.scenarios import regions
    strip = [[0, 0], [4, 0], [4, 10], [0, 10]]
    floors = [{"outline": strip, "why": "yard", "status": "does_not_comply", "base": z, "top": z + 10}
              for z in (0, 10)]                                      # one strip, cut per floor: one region
    assert regions(floors) == [{"why": "yard", "status": "does_not_comply"}]
    apart = floors[:1] + [dict(floors[0], outline=[[20, 0], [24, 0], [24, 10], [20, 10]])]
    assert len(regions(apart)) == 2                                  # two strips apart: two regions
    beside = floors[:1] + [dict(floors[0], outline=[[4, 0], [8, 0], [8, 10], [4, 10]], status="needs_review")]
    assert sorted(r["status"] for r in regions(beside)) == ["does_not_comply", "needs_review"]   # each colour


def test_the_drawn_list_carries_what_each_piece_is_for_so_the_checks_read_what_is_drawn():
    """The Rhino check of #28 read the rear yard's amber strip as the side yard's (the claims and the screen seemed
    to disagree). Each drawn piece now carries its row, why and building (one list: drawn and read)."""
    from rule_format.rulebook import REPO
    entry = {"outline": [], "why": "yard", "measure": "rear_yard", "row": "Rear yard", "building": "house",
             "status": "needs_review", "base": 0, "top": 20}
    assert logic.coloured_info(entry) == {"why": "yard", "measure": "rear_yard", "row": "Rear yard",
                                          "building": "house"}
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert "o.encroach = [(_proud(doc, piece), status, logic.coloured_info(e))" in src
    assert 'rest, red = logic.red_last(getattr(o, "encroach", None) or [])' in src   # draw_scene draws that list
    assert "for g, status, _ in rest + red:" in src                                   # (#53: the red over the amber)


def test_each_building_is_made_into_a_solid_once_per_check_not_once_per_block():
    """Independent review of #28, P3: every coloured block looked its building up and converted it again."""
    import ast
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    fns = {n.name: ast.get_source_segment(src, n) for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
    assert "_drawable(" not in fns["_offending"] and "_find(" not in fns["_offending"]
    assert "if key not in out:" in fns["_solids_for"]
    plan = fns["_draw_plan"]
    assert "made = _solids_for(doc, blocks)" in plan and "_offending(doc, e, made)" in plan
