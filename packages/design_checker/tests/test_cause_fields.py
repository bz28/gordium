"""Each mark cause names the description field it needs the architect to state (`field`, and `fields` when it needs
several facts), so a host names its own mark (the Revit add-in: Gordium: Exit door feeds doors[].exit), and every
reason and cause the panel shows is in plain words: no field of the file format in back-quotes, no raw coordinates,
no element's or exit's id (the Children's Odyssey's answer, every one of its items' reasons and every cause's words).
Words and data only: never a status."""

import json
import re

import pytest

from design_checker import egress, grouping, panel_data, present
from rule_format.rulebook import REPO

ANSWER = REPO / "apps/revit_addin/tests/Gordium.Revit.Reading.Tests/answers/children_odyssey_check_answer.json"
# a field of the file format in back-quotes, a point by its coordinates, an element's or an exit's id (a Revit
# UniqueId: a GUID and a hex suffix)
NOT_PLAIN = re.compile(r"`|\(-?\d+(?:\.\d+)?, -?\d+(?:\.\d+)?\)|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _interior(stop, **blanks):
    from model_measurement.interior.stops import Stop
    return egress.INTERIOR_PROBLEM.format(why=Stop(stop, **blanks).reason)


def _law(n, reason, **more):
    return {"id": f"egress.interior#{n}", "law_short": "Egress", "reason": reason, "group": present.LAW_GROUP,
            "status": present.REVIEW, **more}


@pytest.mark.parametrize("what,key,flag,question", [
    ("door", "doors", "exit", "the required exit door"),
    ("opening", "openings", "escape", "an emergency escape and rescue opening"),
    ("room", "rooms", "sleeping", "a sleeping room")])
def test_an_entry_missing_its_flag_is_a_mark_naming_its_field(what, key, flag, question):
    got, = present.law_causes(_law(1, _interior("flag_missing", what=f"{what} D01", question=f"it is {question}")))
    assert got["kind"] == panel_data.MARK and got["field"] == f"{key}[].{flag}"


@pytest.mark.parametrize("kind", ["stairs", "guards"])
def test_a_kind_the_drawing_doesnt_say_it_has_all_of_is_a_mark_naming_it(kind):
    got, = present.law_causes(_law(2, _interior("not_read", what=kind, key=kind)))
    assert got["kind"] == panel_data.MARK and got["field"] == kind


def test_any_other_drawing_problem_is_the_models_to_fix_with_no_field():
    got, = present.law_causes(_law(3, "The interior drawing: door D2 is marked twice"))
    assert got["kind"] == panel_data.FIX_MODEL and "field" not in got
    # a flag's words in a row that isn't the drawing's: never read as the drawing's mark
    words = _interior("flag_missing", what="door D01", question="it is the required exit door")
    got, = present.law_causes({"id": "egress.general.x", "law_short": "Egress", "reason": words})
    assert "field" not in got


def test_a_zoning_row_waiting_on_facts_names_each_facts_field():
    got, = present.zoning_causes({"needs": ["zone", "stories"], "status": present.REVIEW})
    assert got["field"] == "facts.zone" and got["fields"] == ["facts.zone", "facts.stories"]
    got, = present.zoning_causes({"hint": present.PICK_MAIN, "status": present.REVIEW, "objects": ["a"]})
    assert "field" not in got                                       # a pick: no field to state


def test_a_project_fact_not_stated_names_its_field():
    import sys
    sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
    from test_routes_parts import MAINE, NEW_DAY_CARE, RULES
    from rule_format.rulebook import Context, load
    rule = next(r for r in load(RULES)["rules"] if "existing_change_of_use" in str(r.get("applies_when")) + str(r.get("check")))
    building = dict(NEW_DAY_CARE, day_care_existing=True)          # so the rule reads whether its use changed
    row = {"outcome": "needs_review", "id": "p", "values": {}, "reason": None}
    got = panel_data.causes(rule, row, {}, {"id": "p"}, {}, {}, building, Context.for_jurisdiction(MAINE).allowed(), ())
    fact, = [c for c in got if c["key"] == "fact:existing_change_of_use"]
    assert fact["kind"] == panel_data.MARK and fact["field"] == "facts.existing_change_of_use"


def test_a_card_carries_its_first_causes_field():
    door = _interior("flag_missing", what="door D01", question="it is the required exit door")
    items = [dict(_law(1, door), causes=present.law_causes(_law(1, door))),
             dict(_law(2, "x"), id="z", causes=present.zoning_causes({"needs": ["zone", "stories"]}))]
    by_key = {c["key"]: c for c in grouping.cause_cards(items)}
    assert by_key[f"drawing:{door}"]["field"] == "doors[].exit" and "fields" not in by_key[f"drawing:{door}"]
    assert by_key["facts:stories,zone"]["fields"] == ["facts.zone", "facts.stories"]


def _shown(view):
    """Every reason and cause word the panel shows: each item's reason and detail line, each cause's words and its
    rooms' whys, each card's words."""
    for i in view["items"]:
        yield i["id"], i.get("reason")
        yield i["id"], (i.get("detail") or {}).get("line")
        for c in i.get("causes") or []:
            yield i["id"], c.get("words")
            for r in c.get("rooms") or []:
                yield i["id"], r.get("why")
    for g in view["groups"]:
        for c in g.get("causes") or []:
            yield g["key"], c.get("words")


def test_no_word_the_panel_shows_names_a_file_field_a_coordinate_or_an_id():
    view = json.loads(ANSWER.read_text(encoding="utf-8"))["result"]["view"]
    bad = [(where, w) for where, w in _shown(view) if isinstance(w, str) and NOT_PLAIN.search(w)]
    assert not bad, bad[:5]


def test_the_odysseys_mark_cards_name_their_fields():
    view = json.loads(ANSWER.read_text(encoding="utf-8"))["result"]["view"]
    cards = [c for g in view["groups"] for c in g.get("causes") or []]
    assert {"doors[].exit", "openings[].escape", "stairs", "guards"} <= {c["field"] for c in cards if c.get("field")}
    causes = [c for i in view["items"] for c in i.get("causes") or []]
    assert "facts.existing_change_of_use" in {c.get("field") for c in causes}       # a row's later cause
    assert all(c["kind"] == panel_data.MARK for c in cards + causes if c.get("field"))


def test_a_drawing_problems_line_says_its_name_once():
    """"Interior drawing: The interior drawing: the stairs weren't read…" was its line's title; now said once."""
    item = {"name": "Interior drawing", "reason": "The interior drawing: the stairs weren't read"}
    assert grouping._own_title(item) == "The interior drawing: the stairs weren't read"
    assert grouping._own_title({"name": "Ramps", "reason": "x"}) == "Ramps: x"
