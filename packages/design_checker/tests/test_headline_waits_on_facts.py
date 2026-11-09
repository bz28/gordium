"""The headline waits on the facts (Ben, 2026-11-09; principle 4: missing data is never a pass). When every decided row
complies but some row is "not checked", the design's overall answer is needs review, never complies, and the line says
what waits, by what the architect does next:

    needs review · 15 comply · 1 to answer · 1 not checked in this release

"1 to answer": a rule waiting on a fact the model doesn't show (R-1b's parking rule, on the bedrooms and parking
spaces); its row's "Enter …" button answers it. "1 not checked in this release": a rule Gordium doesn't check yet (the
overlays), checked by hand. The panel's line, the viewport's status box and its colour, the report's title, the
command line and the worker's `view` all read present.summary and present.state; the result's own summary
(check.summary) says the same.

A real R-1b check: a 30 x 50 ft house on a 60 x 110 ft lot, every other question answered so every decided row
complies."""
import sys

import openpyxl

from design_checker import present
from design_checker.check import check_site, summary
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_measure import FACTS, box, lot  # noqa: E402

SITE = {"units": "ft", "lot": lot([(0, 0), (60, 0), (60, 110), (0, 110)]),
        "buildings": [box(10, 25, 40, 75, 0, 30)], "problems": []}
ANSWERED = dict(FACTS, street_line=[[[0, 0], [60, 0]]], stream_near_lot=False, unrelated_persons=0,
                owner_occupied=True, accessory_dwelling_unit=False, functional_family_unit=False,
                home_occupation=False, garage_cars=0)
BEDROOMS = {"sleeping_rooms": 3, "parking_spaces": 2}


def _waiting(v):
    return sorted(i["id"] for i in present._building_items(v["items"]) if i["status"] != present.COMPLIES)


def test_every_decided_row_complies_but_the_parking_waits_on_the_bedrooms_needs_review(tmp_path):
    report = tmp_path / "r.xlsx"
    r = check_site(SITE, ANSWERED, report_path=report)
    v = r["view"]
    assert _waiting(v) == ["R-1b.parking_one_family", "release.overlays"]     # every other row complies
    assert v["state"] == present.REVIEW
    assert v["summary"] == "needs review · 14 comply · 1 to answer · 1 not checked in this release"
    assert openpyxl.load_workbook(report)["Check"]["A1"].value == "GORDIUM | " + v["summary"]   # the report says it
    s = r["summary"]                                                           # the result's own line too
    assert s["state"] == "review" and s["text"].endswith(" pass · 1 to answer · 1 not checked in this release")
    assert s["lines"][0].startswith("Parking · needs input: Needs bedrooms and parking spaces")


def test_the_bedrooms_answered_leave_only_the_overlays_still_needs_review():
    r = check_site(SITE, dict(ANSWERED, **BEDROOMS))
    v = r["view"]
    assert _waiting(v) == ["release.overlays"]                                 # the parking rule now complies
    assert v["state"] == present.REVIEW and "to answer" not in v["summary"]
    assert v["summary"] == "needs review · 15 comply · 1 not checked in this release"
    assert r["summary"]["state"] == "review"


def test_with_nothing_left_waiting_it_complies_and_says_only_the_counts():
    # the same real rows without the overlays row (a release that checks them): every counted row complies
    v = check_site(SITE, dict(ANSWERED, **BEDROOMS))["view"]
    items = [i for i in v["items"] if not i["id"].startswith(present.RELEASE)]
    assert present.state(items) == present.COMPLIES
    assert present.summary(items) == "15 comply"


def test_each_kind_of_waiting_row_is_said_by_what_to_do_next():
    answer = {"id": "R-1b.parking_one_family", "group": "not_checked", "status": present.NOT_CHECKED,
              "needs": ["sleeping_rooms"]}
    release = {"id": "release.overlays", "group": "not_checked", "status": present.NOT_CHECKED}
    other = {"id": "x", "group": "not_checked", "status": present.NOT_CHECKED}
    ok = {"id": "y", "group": "building", "status": present.COMPLIES}
    not_yet = {"id": "gap.z", "group": "not_covered", "status": present.NOT_CHECKED}   # never counted, never holds it
    assert present.waiting_parts([answer, answer, release, other, not_yet]) == [
        "2 to answer", "1 not checked in this release", "1 not checked"]
    for row, words in ((answer, "1 to answer"), (release, "1 not checked in this release"), (other, "1 not checked")):
        assert present.state([ok, row]) == present.REVIEW
        assert present.summary([ok, row]) == f"needs review · 1 complies · {words}"
    assert present.state([ok, not_yet]) == present.COMPLIES and present.summary([ok, not_yet]) == "1 complies"


def test_a_failing_or_review_row_says_its_own_count_not_a_second_needs_review():
    release = {"id": "release.overlays", "group": "not_checked", "status": present.NOT_CHECKED}
    fails = {"id": "a", "group": "building", "status": present.FAILS}
    review = {"id": "b", "group": "building", "status": present.REVIEW}
    assert present.summary([fails, release]) == "1 does not comply · 1 not checked in this release"
    assert present.summary([review, release]) == "1 needs review · 1 not checked in this release"
    assert present.state([fails, release]) == present.FAILS


def test_the_results_own_summary_never_passes_with_a_row_waiting():
    passing = [{"Error": "PASS", "Requirement": "Front yard"}]
    waits = [{"id": "release.overlays", "name": "Overlays · not in this release", "group": "not_checked",
              "status": present.NOT_CHECKED, "reason": "check them by hand"}]
    assert summary(passing)["state"] == "pass"                                 # no view: as before
    s = summary(passing, waits)
    assert s == {"state": "review", "text": "1 pass · 1 not checked in this release",
                 "lines": ["Overlays · not in this release: check them by hand"]}
    either = passing + [{"Error": "NEEDS REVIEW", "Requirement": "Rear yard", "Provisional": "passes under every reading"}]
    assert summary(either)["state"] == "complies"
    assert summary(either, waits)["state"] == "review"                         # complies whichever way: still waits
