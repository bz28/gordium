"""The overlays row is left out only when the address lookup positively found no overlay on this very lot (Ben,
2026-11-11, option A; principle 4: any doubt keeps the row, and the row holds the design at needs review).

    address lookup (site_lookup): the City's historic, gorge and zoning-map overlays, the parcel's own record and FEMA's
        flood maps all answer, and all say none  ->  the overlays fact is "suggested" with nothing in it
    start box (rhino_logic.apply_lookup): a live lookup that draws its lot  ->  lot fact overlays_none_found
        {value: true, lot_outline (the lot as drawn), source, date}, saved with the other facts
    check (check_site -> present.overlays_cleared): the lot in the model is still exactly that outline  ->  the
        "Overlays · not in this release" row is left out; else it stays

The real recorded answers: 106 Ithaca Rd is in Zone X, minimal flood hazard; 601 Hancock St is in Zone AE (FEMA, read
2026-11-11). The real R-1b check of test_headline_waits_on_facts: a 30 x 50 ft house on a 60 x 110 ft lot, every
question answered, so every other row complies."""
import copy
import json
import sys

import pytest

from design_checker import present
from design_checker import rhino_logic as logic
from design_checker.check import check_site
from model_measurement.project import fact_problems
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "packages/design_checker/tests"))
sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_headline_waits_on_facts import ANSWERED, BEDROOMS, SITE  # noqa: E402
from test_lookup_box import ZONES, FakeTable, T, looked_up  # noqa: E402
from test_measure import box, lot  # noqa: E402

CORNERS = [(0, 0), (60, 0), (60, 110), (0, 110)]          # SITE's lot
NONE_FOUND = {"value": True, "lot_outline": [list(p) for p in CORNERS], "source": logic.OVERLAYS_NONE_SOURCE,
              "date": "2026-11-11"}
EVERY = dict(ANSWERED, **BEDROOMS)                        # every question answered: only the overlays row waits


def release_rows(v):
    return [i["id"] for i in v["items"] if i["id"].startswith(present.RELEASE)]


# ---- the check: the row goes only for the lot it was found on ------------------------------------------------------

def test_no_overlay_found_on_this_lot_leaves_the_row_out_and_the_design_complies():
    r = check_site(SITE, dict(EVERY, overlays_none_found=NONE_FOUND))
    v = r["view"]
    assert release_rows(v) == []
    assert v["state"] == present.COMPLIES and v["summary"] == "15 comply"
    assert r["summary"]["state"] != "review"
    assert present.OVERLAYS_NONE_LINE.format(date="2026-11-11") in v["header"]["sources"]   # said where it came from


def test_without_the_finding_the_row_stays_and_holds_needs_review():
    v = check_site(SITE, EVERY)["view"]
    assert release_rows(v) == ["release.overlays"] and v["state"] == present.REVIEW
    assert not any(s.startswith("Overlays: none found") for s in v["header"]["sources"])


@pytest.mark.parametrize("outline", [
    [(0, 0), (60, 0), (60, 110), (0, 110.5)],            # one corner moved half a foot
    [(0, 0), (60, 0), (60, 110.02), (0, 110)],           # ... or two hundredths
    [(5, 0), (65, 0), (65, 110), (5, 110)],              # the whole lot moved
    [(0, 0), (60, 0), (60, 110)],                        # another lot (three corners)
    [(0, 0), (30, 0), (60, 0), (60, 110), (0, 110)],     # a corner added
    [(0, 0), (60, 110), (60, 0), (0, 110)],              # the same corners, in another order (another shape)
])
def test_a_lot_that_isnt_the_outline_it_was_found_for_keeps_the_row(outline):
    found = dict(NONE_FOUND, lot_outline=[list(p) for p in outline])
    v = check_site(SITE, dict(EVERY, overlays_none_found=found))["view"]
    assert release_rows(v) == ["release.overlays"] and v["state"] == present.REVIEW


@pytest.mark.parametrize("outline", [
    [(60, 110), (0, 110), (0, 0), (60, 0)],              # from another corner
    [(0, 110), (60, 110), (60, 0), (0, 0)],              # the other way round
    [(0, 0), (60, 0), (60, 110), (0, 110), (0, 0)],      # written closed
    [(0.004, 0), (60, 0.004), (60, 110), (0, 110)],      # within a hundredth of a foot (units round trip)
])
def test_the_same_outline_written_another_way_is_the_same_lot(outline):
    found = dict(NONE_FOUND, lot_outline=[list(p) for p in outline])
    assert present.overlays_cleared(SITE["lot"], dict(EVERY, overlays_none_found=found)) == "2026-11-11"


def test_a_curved_lot_line_or_no_lot_keeps_the_row():
    curved = lot(CORNERS, curved=(2,))
    assert present.overlays_cleared(curved, dict(EVERY, overlays_none_found=NONE_FOUND)) is None
    assert present.overlays_cleared(None, dict(EVERY, overlays_none_found=NONE_FOUND)) is None
    assert present.overlays_cleared({"id": "lot", "edges": []}, dict(EVERY, overlays_none_found=NONE_FOUND)) is None


def test_the_caller_can_never_say_it_for_the_checker():
    """The Rhino command's extras never carry the finding into the check: only the facts and the model decide."""
    v = check_site(SITE, EVERY, extras={"overlays_none_found": "2026-11-11"})["view"]
    assert release_rows(v) == ["release.overlays"]


def test_a_saved_and_reopened_project_decides_the_same():
    """The facts as the plugin saves them (JSON in the document) and reads them back: the same answer."""
    facts = dict(EVERY, overlays_none_found=NONE_FOUND)
    reopened = json.loads(json.dumps(facts))
    assert fact_problems(reopened) == []
    live, again = check_site(SITE, facts)["view"], check_site(SITE, reopened)["view"]
    assert (live["state"], live["summary"], release_rows(live)) == (again["state"], again["summary"],
                                                                    release_rows(again))


@pytest.mark.parametrize("bad", [
    True, {"value": True}, dict(NONE_FOUND, value=False), dict(NONE_FOUND, lot_outline=[[0, 0], [1, 1]]),
    dict(NONE_FOUND, lot_outline=[[0, 0], [1, 0], ["a", 1]]), dict(NONE_FOUND, date=""), dict(NONE_FOUND, extra=1),
    {k: v for k, v in NONE_FOUND.items() if k != "source"},
])
def test_a_malformed_finding_is_refused_like_any_bad_fact(bad):
    assert any("overlays_none_found" in p for p in fact_problems(dict(EVERY, overlays_none_found=bad)))


# ---- the start box: only a live lookup's positive none, for the lot it draws ----------------------------------------

def _apply(payload, facts=None, saved=None):
    table = FakeTable({"sample": {"layer": "Site", "kind": "lot"}})
    facts = {"lot_id": "sample"} if facts is None else facts
    saved = {"from_sample": True, "replaceable_lot": "sample"} if saved is None else saved
    f, sv, _ = logic.apply_lookup(table, logic.BoxSession(table), payload, facts, saved, ZONES)
    return f, sv


def test_a_lookup_that_found_none_on_its_lot_records_it_for_that_lot():
    payload = looked_up("106_ithaca_rd")
    f, _ = _apply(payload)
    found = f["overlays_none_found"]
    assert found["value"] is True and found["lot_outline"] == payload["writes"]["lot_ring"]
    assert found["date"] == "2026-10-20" and fact_problems({**f, "jurisdiction": "x", "zone": "R-1b"}) == []


@pytest.mark.parametrize("why, payload", [
    ("Zone AE", lambda: looked_up("601_hancock_st")),
    ("FEMA down", lambda: _flood_down()),
    ("a historic district", lambda: looked_up("106_ithaca_rd", historic=["East Hill"])),
    ("a doubtful lot", lambda: _doubtful()),
    ("a saved lookup", lambda: logic.as_saved(logic.storable_lookup(dict(looked_up("106_ithaca_rd"),
                                                                         checked="2026-10-20")))),
])
def test_a_lookup_with_any_doubt_records_nothing(why, payload):
    f, _ = _apply(payload())
    assert "overlays_none_found" not in f, why


def _flood_down():
    from site_lookup.adapters.ithaca_city.lookup import lookup
    from design_checker.lookup_box import box_payload
    fx = T.load("106_ithaca_rd")
    return box_payload(lookup(fx["address"], T.Failing(fx, ["fema_flood"]), T.NOW))


def _doubtful():
    from site_lookup.adapters.ithaca_city.lookup import lookup
    from design_checker.lookup_box import box_payload
    fx = copy.deepcopy(T.load("106_ithaca_rd"))
    for a in fx["answers"]:
        if a["source"] == "geocoder":
            for c in a["body"]["candidates"]:
                c["attributes"]["Addr_type"] = "StreetAddress"     # found only along the street: the lot may be wrong
    return box_payload(lookup(fx["address"], T.Fake(fx), T.NOW))


def test_a_later_lookup_decides_again_and_the_architects_own_lot_gets_none():
    f, sv = _apply(looked_up("106_ithaca_rd"))
    assert "overlays_none_found" in f
    f2, _ = _apply(looked_up("601_hancock_st"), f, sv)                 # another address, in Zone AE
    assert "overlays_none_found" not in f2
    own = {"lot_id": "mine", "overlays_none_found": NONE_FOUND}         # the architect's own lot: never replaced
    f3, _ = _apply(looked_up("106_ithaca_rd"), own, {"replaceable_lot": None})
    assert f3["lot_id"] == "mine" and "overlays_none_found" not in f3


def test_a_lookup_that_found_nothing_changes_nothing():
    f, sv = _apply(looked_up("106_ithaca_rd"))
    f2, _ = _apply({"status": "offline", "query": "106 Ithaca Rd"}, f, sv)
    assert f2["overlays_none_found"] == f["overlays_none_found"]


# ---- end to end: lookup -> box -> check, on the lookup's own lot -----------------------------------------------------

def test_end_to_end_the_lookups_lot_leaves_the_row_out_and_an_edit_brings_it_back():
    payload = looked_up("106_ithaca_rd")
    f, _ = _apply(payload)
    ring = [tuple(p) for p in payload["writes"]["lot_ring"]]
    facts = dict(EVERY, lot_id="lot", overlays_none_found=f["overlays_none_found"])
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    site = {"units": "ft", "lot": lot(ring), "buildings": [box(cx - 10, cy - 10, cx + 10, cy + 10, 0, 20)],
            "problems": []}
    assert release_rows(check_site(site, facts)["view"]) == []
    moved = [ring[0]] + ring[1:-1] + [(ring[-1][0] + 1, ring[-1][1])]   # the architect drags one corner a foot
    site_edited = dict(site, lot=lot(moved))
    assert release_rows(check_site(site_edited, facts)["view"]) == ["release.overlays"]
