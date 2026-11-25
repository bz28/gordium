"""The Revit pane's saved four-unit apartment answer (tests/Gordium.Revit.Reading.Tests/answers/
four_unit_apartment_check_answer.json, read by ResultViewsTests, ResultViewListTests and the pane renders) is the
checker's own answer to that building's trial request, so the pane is tested on what an architect would see. When a
rulebook change alters the answer, this fails until the file is made again (apps/revit_addin/README.md says how).
PR #181 review round 13: group 1's rules took the answer from 108 results to 247 while the file kept the old 108."""

from __future__ import annotations

import json
from pathlib import Path

from design_checker.__main__ import answer

REPO = Path(__file__).resolve().parents[4]
REQUEST = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json"
SAVED = REPO / "apps/revit_addin/tests/Gordium.Revit.Reading.Tests/answers/four_unit_apartment_check_answer.json"


def _shape(a: dict) -> dict:
    view = a["result"]["view"]
    return {"items": [(i.get("id"), i.get("status"), [k.get("field") for k in i.get("asks") or []])
                      for i in view["items"]],
            "contents": view.get("contents")}


def test_the_panes_saved_apartment_answer_is_the_checkers_answer_today():
    got = answer(json.loads(REQUEST.read_text(encoding="utf-8")))
    saved = json.loads(SAVED.read_text(encoding="utf-8"))
    assert _shape(saved) == _shape(got), "make the saved answer again (apps/revit_addin/README.md)"
