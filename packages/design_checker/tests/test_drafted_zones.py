"""A zone with only AI-drafted rules (stage 1 of drafting, 2026-10-20): it is checked with its own drafted rulebook
and the drafted rules for every district (drafted/general.yaml), and never shows a design as complying because a
rule was left out."""
import pytest

from design_checker.check import check_site
from rule_format.rulebook import REPO, is_ai_drafted, rulebook_for, zone_rulebooks

ITHACA = "regulations/jurisdictions/new_york/ithaca_city"
J = REPO / ITHACA


def prism(outline, z0, z1, id):
    """A solid: walls, floor and a flat roof over an outline (as model_measurement's tests draw one)."""
    n = len(outline)
    walls = [{"points": [[*outline[i], z0], [*outline[(i + 1) % n], z0], [*outline[(i + 1) % n], z1], [*outline[i], z1]]}
             for i in range(n)]
    return {"id": id, "faces": [{"points": [[x, y, z0] for x, y in outline]}, {"points": [[x, y, z1] for x, y in outline]},
                                *walls], "problems": []}


def box(x0, y0, x1, y1, z0=0, z1=30, id="house"):
    return prism([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1, id)


def site(*buildings):
    pts = [(0, 0), (50, 0), (50, 100), (0, 100)]                     # 50 x 100 ft, street along y = 0
    edges = [{"points": [list(pts[i]) + [0.0], list(pts[(i + 1) % 4]) + [0.0]], "curved": False} for i in range(4)]
    return {"units": "ft", "lot": {"id": "lot", "edges": edges}, "buildings": list(buildings), "problems": []}


FACTS = {"jurisdiction": ITHACA, "street_line": [[[0, 0], [50, 0]]], "corner_lot": False, "lot_surveyed": True,
         "ground_is_flat": True, "grade_elevation": 0, "use": "one_family_detached", "stories": 2,
         "main_building": "house", "accessory_buildings": ["shed"]}


@pytest.fixture
def drafts_on(monkeypatch):
    """Ben's setting turned on, as checking a drafted zone needs."""
    from design_checker import check
    monkeypatch.setattr(check, "offer_ai_drafted_zones", lambda: True)


def test_general_rules_come_with_a_drafted_district_and_never_with_a_hand_rulebook():
    assert is_ai_drafted(J, "R-1a") and not is_ai_drafted(J, "R-1b")
    assert [p.name for p in zone_rulebooks(J, "R-1a")] == ["R-1a.yaml", "general.yaml"]
    assert [p.name for p in zone_rulebooks(J, "R-1b")] == ["R-1b.yaml"]         # the hand R-1b carries its own
    assert rulebook_for(J, "general") is None and zone_rulebooks(J, "general") == []   # never a zone


def test_a_shed_4_ft_from_an_r1_side_line_in_a_drafted_only_district_does_not_comply(drafts_on):
    """§325-25C: in R-1 districts an accessory building may not be less than 6 ft from a side lot line. R-1a has no
    hand rulebook; the rule is in drafted/general.yaml. Without it the shed's only row was the front-yard rule
    (drafted/R-1a.yaml), which passes: the shed was shown as complying."""
    shed = box(40, 75, 46, 85, 0, 10, id="shed")                    # 50 - 46 = 4 ft from the east side line
    got = check_site(site(box(10, 25, 35, 65), shed), {**FACTS, "zone": "R-1a"})
    side = [r for r in got["rows"] if r["Rule id"].startswith("general.325_25c_frame_accessory_side_setback_r1")]
    assert side and all(r["Error"] != "PASS" for r in side)
    assert got["summary"]["state"] not in ("pass", "complies")


ZONES = ["R-1a", "R-1b", "R-2a", "R-2b", "R-2c", "R-3a", "R-3aa", "R-3b", "RU"]


@pytest.mark.parametrize("zone", ZONES)
def test_every_chart_row_the_zone_states_is_checked_by_a_rule_or_listed_as_not_checked(zone):
    """Stage 1 drafted no minimum lot width rule, and the result simply had no lot-width row. Now every cell of the
    zone's chart column that states something is cited by one of the zone's rules or listed as not checked (the
    loading row, never drafted, is listed for every zone)."""
    from design_checker.gaps import _cells, _cites, _clean, EMPTY, chart_gaps
    from rule_format.rulebook import district_name, zone_rules
    rules = zone_rules(J, zone)
    found = chart_gaps(J, zone, rules)
    gaps, rows = {g["id"] for g in found}, {g["row"] for g in found}
    sources = [s for r in rules for s in r.get("sources") or []]
    stated = [c for c in _cells(J) if district_name(c["column"]) == zone and str(c["value"]).strip() not in EMPTY]
    assert stated
    for c in stated:
        listed = (c["page"], _clean(c["section"]), _clean(c["row"])) in rows
        assert any(_cites(s, c) for s in sources) or listed, (c["page"], c["section"], c["row"])
    assert any(g.startswith("chart.p14.minimum_loading_requirement") for g in gaps)     # not drafted: listed


def test_a_missing_rule_shows_as_a_not_checked_item_on_the_panel(drafts_on):
    got = check_site(site(box(10, 25, 35, 65)), {**FACTS, "zone": "R-1a", "accessory_buildings": []})
    items = {i["id"]: i for i in got["view"]["items"]}
    loading = [i for k, i in items.items() if k.startswith("gap.chart.p14.minimum_loading_requirement")]
    assert loading and all(i["status"] == "not_checked" and i["group"] == "not_covered" for i in loading)
    assert "gap.drafting.325-19A" in items              # a law piece the drafting run gave no rule: listed


def test_the_start_box_offers_drafted_zones_only_behind_bens_setting_labeled_draft_and_never_general():
    from design_checker import check
    assert check.offer_ai_drafted_zones() is False                       # default off until Ben turns it on
    off = check.options(ITHACA)
    assert off["zones"] == ["R-1b"] and off["labels"] == {"R-1b": "R-1b"} and off["default_zone"] == "R-1b"
    on = check.options(ITHACA, offer_drafted=True)
    assert "general" not in on["zones"] and {"R-1a", "R-2a", "RU"} <= set(on["zones"])
    assert on["labels"]["R-2a"] == "R-2a (draft)" and on["labels"]["R-1b"] == "R-1b"
    assert on["default_zone"] == "R-1b"                     # the sample project's zone, not the first (R-1a)


def test_the_zone_is_never_preselected_alphabetically(monkeypatch):
    """With drafts on, the first zone in the list is R-1a; the start box pre-selected it (zones[0], SelectedIndex 0)
    instead of the sample project's R-1b. The pre-selection is the looked-up or sample zone, or none."""
    from design_checker import check
    monkeypatch.setattr(check, "load_facts", lambda path: {"zone": "R-9z"})     # a sample zone that isn't offered
    assert check.options(ITHACA, offer_drafted=True)["default_zone"] is None
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert "zones[0]" not in rhino and '"zone": default_zone if default_zone in zones else None' in rhino
    assert rhino.count('suggested_facts(doc, options["zones"], options.get("default_zone"))') == 4
    assert "zone.SelectedIndex = 0" not in ui and 'logic.preselect_zone(' in ui
    assert "zone_of.get(zone.SelectedValue.Text)" in ui            # the label "(draft)" never reaches the facts


def test_with_the_setting_off_a_saved_drafted_zone_is_never_checked_and_never_swapped():
    """Review round 1: the setting only filtered the zone list. A model saved as R-2a (while drafts were offered) was
    still checked with the AI's R-2a rules, and Edit site pre-selected R-1b in its place with "I confirm" still
    ticked. Now the checker refuses it with a clear message, the check command asks for the zone again, and the
    start box selects nothing and unticks "I confirm"."""
    from design_checker import check, rhino_logic as logic
    assert check.offer_ai_drafted_zones() is False
    with pytest.raises(ValueError, match="R-2a's rules are AI drafts, not yet verified, and are turned off"):
        check_site(site(box(10, 25, 35, 65)), {**FACTS, "zone": "R-2a", "accessory_buildings": []})
    options = check.options(ITHACA)
    assert logic.zone_not_offered({"zone": "R-2a"}, options) == ["zone"]
    assert logic.zone_not_offered({"zone": "R-1b"}, options) == [] and logic.zone_not_offered({}, options) == []
    assert logic.preselect_zone("R-2a", options) == (None, False)          # never R-1b in its place, unticked
    assert logic.preselect_zone("R-1b", options) == ("R-1b", True)
    assert logic.preselect_zone(None, options) == ("R-1b", True)            # nothing saved: the sample zone
    rhino = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert "if logic.missing(facts) or logic.zone_not_offered(facts, options):" in rhino
    assert 'wanted, keep_confirmed = logic.preselect_zone(state.get("zone"), options)' in ui
    assert 'confirm.Checked = bool(state.get("district_confirmed")) and keep_confirmed' in ui


def test_every_drafting_entry_for_a_person_about_the_zone_is_listed_as_not_checked():
    """Review round 1: only entries named "<zone>." without cells were listed. §325-19E's 75% coverage for R-3a carries
    the coverage cell, which R-3a's own 35% rule cites, so it vanished; the template rejected for every district
    (the footnoted lot-size rows: multiple family, group house) and the sections left out for length are named for
    the unit, so they vanished in every zone."""
    from design_checker.gaps import drafting_gaps
    from rule_format.rulebook import zone_rules
    names = {g["name"] for g in drafting_gaps(J, "R-3a", zone_rules(J, "R-3a"))}
    assert "R-3a.325_19e_r3_abut_r1_max_coverage" in names                  # its cell is cited by another rule
    assert "325-19E.325_19e_r3_abut_r1_min_lot_area_footnoted_rows" in names  # rejected for every district
    assert "325-20D" in names                                               # a section left out for length
    whys = [g["why"] for g in drafting_gaps(J, "R-3a", zone_rules(J, "R-3a"))]
    assert any("fraternity_sorority_group_house" in w for w in whys)        # a group house next to R-1: not checked
    assert drafting_gaps(J, "R-1b", zone_rules(J, "R-1b")) == []          # the hand R-1b: not the drafting log's
