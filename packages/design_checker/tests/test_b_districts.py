"""The B districts reach the architect: the Setup form's choices (the worker's options) and a corner lot's yards.

Hand-worked: the expected answers here come from the zoning chart (p.4 marks) and §325-19C's words, not from a run.
"""
from design_checker import present, scenarios
from design_checker.check import check_site, options

ITHACA = "regulations/jurisdictions/new_york/ithaca_city"
B = ["B-1a", "B-1b", "B-2a", "B-2d", "B-4", "B-5"]


def test_the_zone_choices_hold_every_b_district_with_a_rulebook_and_no_other():
    zones = options(ITHACA)["zones"]
    assert set(B) <= set(zones)
    assert not {"B-2b", "B-2c", "CBD-60"} & set(zones)          # no rulebook (docs/decisions/2026-11-22_commercial_districts.md)


def test_the_use_choices_follow_each_b_columns_marks_on_chart_p4():
    o = options(ITHACA)
    permitted = {z: {u["id"] for u in o["district_uses"][z] if u["permitted"]} for z in B}
    special = {z: {u["id"] for u in o["district_uses"][z] if not u["permitted"]} for z in B}
    # a retail store: "-" in B-1A and B-1B, • in B-2A, B-2D, B-4, B-5
    assert {z for z in B if "retail_store_or_service_commercial" in permitted[z]} == {"B-2a", "B-2d", "B-4", "B-5"}
    # a gasoline station: • in B-4 and B-5 only
    assert {z for z in B if "gasoline_station" in permitted[z]} == {"B-4", "B-5"}
    # a restaurant: - in B-2D
    assert "restaurant_or_tavern" in permitted["B-2a"] and "restaurant_or_tavern" not in permitted["B-2d"]
    # SP everywhere: a bed-and-breakfast inn, a hospital; a redemption center SP except "-" in B-1
    for z in B:
        assert {"bed_and_breakfast_inn", "hospital_or_sanitarium"} <= special[z]
        assert "business_or_professional_office" in permitted[z] and "multiple_family" in permitted[z]
    assert "redemption_center" in special["B-2a"] and "redemption_center" not in special["B-1a"] | permitted["B-1a"]
    note = next(u["note"] for u in o["district_uses"]["B-2a"] if u["id"] == "cemetery")
    assert note.startswith("Not permitted by right in B-2a: Marked SP for B-2A on the zoning chart (p.4)")
    # a commercial use doesn't pass in a residential district (R-3a's use rule lists its uses since 2026-11-22)
    assert "retail_store_or_service_commercial" not in {u["id"] for u in o["district_uses"]["R-3a"] if u["permitted"]}


def test_a_b_district_corner_lot_never_passes_a_street_yard_as_a_front_yard():
    """§325-19C gives two front yards to corner lots "in residential districts" only: on a B-2a corner lot a street
    yard of 6 ft is not passed as a front yard (B-2a sets none) when, as a side yard, one side needs 10 ft."""
    sc = scenarios.load(scenarios.FOLDER / "13_b2a_two_story_retail_office.yaml")
    sc = dict(sc, buildings=[dict(sc["buildings"][0], outline=[[10, 5], [54, 5], [54, 65], [10, 65]])])
    s, f, extras = scenarios.site(sc)
    f.update(corner_lot=True, street_line=[[[0, 0], [60, 0]], [[60, 0], [60, 100]]], street_ids=["A St", "B St"],
             address_street_line=[[[0, 0], [60, 0]]])
    items = {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}
    yards = [i for name, i in items.items() if name.startswith(("Side yard", "Rear yard", "Front yard"))]
    assert yards and all(i["status"] != present.COMPLIES for i in yards), [(i["name"], i["status"]) for i in yards]
    assert any("§325-19C gives two front yards only to corner lots in residential districts" in str(i.get("reason"))
               for i in yards)
