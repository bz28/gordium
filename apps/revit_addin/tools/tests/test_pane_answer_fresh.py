"""The Revit pane's saved four-unit apartment answer (tests/Gordium.Revit.Reading.Tests/answers/
four_unit_apartment_check_answer.json, read by ResultViewsTests, ResultViewListTests and the pane renders) is the
checker's own answer to that building's trial request, so the pane is tested on what an architect would see. When a
rulebook change alters the answer, this fails until the file is made again (apps/revit_addin/README.md says how).
PR #181 review round 13: group 1's rules took the answer from 108 results to 247 while the file kept the old 108.
Round 14: the whole view is compared (asks, in_code and contents, every key), not a few fields of it."""

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
    """Whether the saved answer's view differs from the checker's in any key (JSON as written, so tuples are lists)."""
    return json.loads(json.dumps(got, ensure_ascii=False))["result"]["view"] != saved["result"]["view"]


@pytest.fixture(scope="module")
def saved():
    return json.loads(SAVED.read_text(encoding="utf-8"))


def test_the_panes_saved_apartment_answer_is_the_checkers_answer_today(saved):
    got = answer(json.loads(REQUEST.read_text(encoding="utf-8")))
    assert not _stale(saved, got), "make the saved answer again (apps/revit_addin/README.md)"


def test_a_change_to_where_a_result_sits_in_the_code_or_to_an_ask_makes_it_stale(saved):
    placed = next(i for i in saved["result"]["view"]["items"] if i.get("in_code"))
    asked = next(i for i in saved["result"]["view"]["items"] if i.get("asks"))
    for item, change in ((placed, lambda i: i["in_code"].update(piece_title="moved")),
                         (asked, lambda i: i["asks"][0].update(headline="changed"))):
        moved = copy.deepcopy(saved)
        change(next(i for i in moved["result"]["view"]["items"] if i["id"] == item["id"]))
        assert _stale(saved, moved)
