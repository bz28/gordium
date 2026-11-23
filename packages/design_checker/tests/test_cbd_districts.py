"""The CBD districts reach the architect: the Setup form's choices (the worker's options), each flag's scope as its law
states it, a corner lot's yards, and the red above the height plane.

Hand-worked: the expected answers here come from the zoning chart (p.4's CBD column) and Chapter 325's words, not
from a run.
"""
import re

from design_checker import present, scenarios
from design_checker.check import check_site, options
from rule_format.rulebook import REPO, load, outcome

ITHACA = "regulations/jurisdictions/new_york/ithaca_city"
CBD = ["CBD-50", "CBD-60", "CBD-85", "CBD-100", "CBD-120", "CBD-140"]
DWELLINGS = {"one_family_detached", "one_family_semi_detached", "one_family_attached", "two_family"}


def _rules(d):
    return {r["id"].split(".", 1)[1]: r for r in load(REPO / ITHACA / f"5_zoning_rules/{d}.yaml")["rules"]}


def test_the_zone_choices_hold_every_cbd_district_and_never_cbd_52():
    zones = options(ITHACA)["zones"]
    assert set(CBD) <= set(zones)
    assert "CBD-52" not in zones and "CBD" not in zones       # in no chart column (an open question for the City)


def test_the_use_choices_follow_the_cbd_columns_marks_on_chart_p4():
    o = options(ITHACA)
    for z in CBD:
        permitted = {u["id"] for u in o["district_uses"][z] if u["permitted"]}
        special = {u["id"] for u in o["district_uses"][z] if not u["permitted"]}
        assert {"parking_garage", "retail_store_or_service_commercial", "multiple_family", "hotel_motel",
                "business_or_professional_office"} <= permitted
        assert {"cemetery", "public_utility_structure", "neighborhood_commercial_facility", "hospital_or_sanitarium",
                "bed_and_breakfast_inn", "redemption_center"} == special
        assert not {"gasoline_station", "motor_vehicle_sales_and_service", "service_shop"} & (permitted | special)
        assert len(permitted) == 25


# The law's own scope for each CBD flag scoped by use (the lesson of #166's review, P1): every use the district's use
# rule passes or sends to review gets the flag when the law covers it. §325-20 (chart p.15): every use; §325-22: motels;
# §325-8D(3): "All properties located in the CBD district that contain a storefront..." and every property in the
# overlay zone, whatever their use ("Nonactive uses ... include ... any residential uses"); §325-19: every lot.
FLAG_SCOPE = {
    "parking": lambda u: True,
    "motel_standards": lambda u: u == "hotel_motel",
    "active_street_level_use": lambda u: True,
    "transition_yards": lambda u: True,
}


def test_every_use_a_cbd_district_allows_or_reviews_gets_each_flag_its_law_covers_and_no_loading():
    uses = load(REPO / ITHACA / "4_term_definitions/uses.yaml")
    allowed = {"use": set(uses)}
    for d in CBD:
        rules = _rules(d)
        live = [u for u in uses if outcome(rules["use"], {"use": u}, allowed) in ("pass", "needs_review")]
        assert len(live) == 31, d
        for flag, covers in FLAG_SCOPE.items():
            for u in live:
                if covers(u):
                    assert outcome(rules[flag], {"use": u}, allowed) == "needs_review", (d, flag, u)
        # §325-21B ("except for properties located in any CBD district") and §325-21C: no loading at all
        assert "loading" not in rules and not [r for r in rules.values() if "loading" in r["id"]]
        # the one CBD-only stepback and historic review, where §325-8D puts them, on every lot of that district
        assert ("green_street_stepback" in rules) == (d == "CBD-85")
        assert ("historic_review" in rules) == (d == "CBD-50")


def test_a_cbd_corner_lot_never_passes_a_yard():
    """§325-19C's two front yards are for corner lots "in residential districts" only: on a CBD-60 corner lot no yard is
    measured, so the rear yard is never passed on a guess of which street is the front."""
    sc = scenarios.load(scenarios.FOLDER / "16_cbd60_five_story_mixed_use.yaml")
    s, f, extras = scenarios.site(sc)
    f.update(corner_lot=True, street_line=[[[0, 0], [60, 0]], [[60, 0], [60, 120]]], street_ids=["A St", "B St"],
             address_street_line=[[[0, 0], [60, 0]]])
    items = {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}
    yards = [i for name, i in items.items() if name.startswith(("Rear yard", "Front yard", "Side yard"))]
    assert yards and all(i["status"] != present.COMPLIES for i in yards), [(i["name"], i["status"]) for i in yards]


def test_no_cbd_rulebook_says_a_corner_lots_street_yards_are_front_yards():
    for d in CBD:
        for r in _rules(d).values():
            assert "measured as a front yard" not in (r.get("notes") or ""), r["id"]
        assert "no yard is measured" in _rules(d)["rear_yard"]["notes"]


def test_the_central_business_audit_cites_the_cbd_columns_own_marks_never_the_residential_charts():
    """Decisions carried over from the B districts must say the CBD column's own marks: no residential chart page, no
    B district's lot named as this one's, and a "-" decision names the cell (its value is checked to be "-")."""
    j = REPO / ITHACA
    text = (j / "central_business_coverage.yaml").read_text(encoding="utf-8")
    assert not re.findall(r"chart p\.(?:2|3|14)\b|\(p\.(?:2|3|14)\)", text)
    assert not re.findall(r"\bB(?:-\d[a-z]?)? (?:district|lot)|B-district lot|every B district", text)
    data = load(j / "central_business_coverage.yaml")
    gas = data["pieces"]["325-15F"][0]["all"]
    assert gas["status"] == "not_applicable" and gas["cell"] == {"section": "Primary Uses", "row": "Gasoline station"}
    assert data["pieces"]["325-21C"][0]["all"]["status"] == "not_applicable"
    assert data["pieces"]["325-16G"][0]["CBD-50"]["status"] == "not_applicable"


def test_a_cbd_building_over_its_height_is_drawn_red_above_the_plane():
    """CBD-60 has a minimum height too: its "complies" row must not hide the maximum's failure in the viewport (the
    plan's red above the 60 ft plane; before 2026-11-23 the last building-height row won)."""
    sc = scenarios.load(scenarios.FOLDER / "17_cbd60_six_story_office_over_the_height.yaml")
    s, f, extras = scenarios.site(sc)
    plan = check_site(s, f, extras=extras)["plan"]
    red = [e for e in plan["encroach"] if e["why"] == "height"]
    assert red and all(e["base"] == 60 and e["status"] == present.FAILS for e in red)
