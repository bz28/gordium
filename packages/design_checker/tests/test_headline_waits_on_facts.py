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


WAITS = [{"id": "release.overlays", "rule": None, "name": "Overlays · not in this release", "group": "not_checked",
          "status": present.NOT_CHECKED, "reason": "check them by hand"}]
PASSING = [{"Error": "PASS", "Requirement": "Front yard"}]
EITHER_WAY = PASSING + [{"Error": "NEEDS REVIEW", "Requirement": "Rear yard", "Provisional": "passes under every reading"}]


def test_the_results_own_summary_never_passes_with_a_row_waiting():
    assert summary(PASSING)["state"] == "pass" and summary(EITHER_WAY)["state"] == "complies"   # no view: as before
    assert summary(PASSING, WAITS) == {"state": "review", "text": "1 pass · 1 not checked in this release",
                                       "lines": ["Overlays · not in this release: check them by hand"]}
    s = summary(EITHER_WAY, WAITS)                         # complies whichever way the law is read: still waits
    assert s == {"state": "review", "text": "1 pass · 1 pass whichever way open questions go · 1 not checked in this "
                 "release", "lines": ["Rear yard: passes under every reading",      # which open question: kept
                                      "Overlays · not in this release: check them by hand"]}


def test_the_results_own_summary_says_what_waits_beside_a_review_or_a_failure_too():
    survey = PASSING + [{"Error": "NEEDS REVIEW", "Requirement": "Lot coverage by buildings", "Survey": True,
                         "Provisional": "passes with the lot as drawn (confirm the survey)", "Why": "no survey"}]
    s = summary(survey, WAITS)
    assert s["state"] == "review" and s["text"] == "1 pass · 1 need review · 1 not checked in this release"
    assert s["lines"][-1] == "Overlays · not in this release: check them by hand"
    failing = PASSING + [{"Error": "FAIL", "Requirement": "Rear yard", "Line": "Rear yard: 2 ft short"}]
    assert summary(failing, WAITS)["text"] == "1 pass · 1 fail · 1 not checked in this release"


def test_the_results_own_summary_counts_the_views_rows_that_arent_a_rules():
    # "Objects on the lot not included" and "Lot facts disagree" are the view's rows, not a rule's: the view needs
    # review for them, so the result's line never passes beside it
    left_out = {"id": "scope.not_included", "rule": None, "name": "Objects on the lot not included",
                "group": "building", "status": present.REVIEW, "reason": "1 object on the lot isn't measured"}
    s = summary(PASSING, [left_out])
    assert s == {"state": "review", "text": "1 pass · 1 more need review",
                 "lines": ["Objects on the lot not included: 1 object on the lot isn't measured"]}
    assert summary(PASSING, [dict(left_out, status=present.FAILS)])["state"] == "fail"
    ruled = dict(left_out, rule="R-1b.front_yard")         # a rule's row is already among the rows: not counted twice
    assert summary(PASSING, [ruled])["state"] == "pass"
