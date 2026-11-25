"""The Revit pane's saved four-unit apartment answer (tests/Gordium.Revit.Reading.Tests/answers/
four_unit_apartment_check_answer.json, read by ResultViewsTests, ResultViewListTests and the pane renders) is the
checker's own answer to that building's trial request, so the pane is tested on what an architect would see. When a
rulebook change alters the answer, this fails until the file is made again (apps/revit_addin/README.md says how).
PR #181 review round 13: group 1's rules took the answer from 108 results to 247 while the file kept the old 108.
Round 14: the whole view, not a few fields of it; round 15: the whole result (the pane also reads
result.which_code and result.measurements); round 16: the result only, never the answer's `about` fingerprints, which
change with any file of the worker's and which the pane never reads (its tests stand in an About of their own)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from design_checker.__main__ import answer

REPO = Path(__file__).resolve().parents[4]
REQUEST = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json"
SAVED = REPO / "apps/revit_addin/tests/Gordium.Revit.Reading.Tests/answers/four_unit_apartment_check_answer.json"


def _stale(saved: dict, got: dict) -> bool:
    """Whether the saved answer's result (all the pane reads) differs from the checker's in any key (JSON as written,
    so tuples are lists)."""
    return json.loads(json.dumps(got["result"], ensure_ascii=False)) != saved["result"]


@pytest.fixture(scope="module")
def saved():
    return json.loads(SAVED.read_text(encoding="utf-8"))


def test_the_panes_saved_apartment_answer_is_the_checkers_answer_today(saved):
    got = answer(json.loads(REQUEST.read_text(encoding="utf-8")))
    assert not _stale(saved, got), "make the saved answer again (apps/revit_addin/README.md)"


def test_any_change_the_pane_reads_makes_it_stale(saved):
    placed = next(i for i in saved["result"]["view"]["items"] if i.get("in_code"))
    asked = next(i for i in saved["result"]["view"]["items"] if i.get("asks"))
    for item, change in ((placed, lambda i: i["in_code"].update(piece_title="moved")),
                         (asked, lambda i: i["asks"][0].update(headline="changed"))):
        moved = copy.deepcopy(saved)
        change(next(i for i in moved["result"]["view"]["items"] if i["id"] == item["id"]))
        assert _stale(saved, moved)
    for change in (lambda r: r["which_code"].update(why="changed"),
                   lambda r: next(iter(r["measurements"].values())).update(how="changed")):
        moved = copy.deepcopy(saved)
        change(moved["result"])
        assert _stale(saved, moved)


def test_a_new_fingerprint_alone_never_makes_it_stale(saved):
    moved = copy.deepcopy(saved)
    moved["about"]["worker_fingerprint"] = "0" * 64
    moved["about"]["rulebook"] = {k: "0" * 64 for k in moved["about"].get("rulebook") or {"x": 0}}
    assert not _stale(saved, moved)
