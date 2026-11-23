"""The words an architect reads in the results panel (the interior and route measuring's reasons), in plain words:
no field of Gordium's file format in back-quotes ("`exit`: true or false", "no `stairs` in the description"), no
raw coordinates ("the point (55.308, 78.082)"), no exit's id: the elements by their own names (a door by its name,
a room by its name and number). The field a reason asks the architect to state is data (interior.asked_field), never
words. Only the words change: every reason still stops the measure it stopped (never a verdict changed)."""

import re
import sys
from pathlib import Path

import pytest

from model_measurement.interior import KINDS, asked_field, measure
from model_measurement.interior.stops import STOPS as INTERIOR_STOPS
from model_measurement.interior.stops import Stop
from model_measurement.routes.stops import STOPS as ROUTE_STOPS

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from test_interior_measures import base  # noqa: E402

COORDINATES = re.compile(r"\{x\}|\{y\}|\(-?\d+(?:\.\d+)?, -?\d+(?:\.\d+)?\)")


@pytest.mark.parametrize("table,key", [("interior", k) for k in INTERIOR_STOPS] + [("routes", k) for k in ROUTE_STOPS])
def test_no_reason_names_a_file_field_in_back_quotes_or_a_point_by_its_coordinates(table, key):
    words = (INTERIOR_STOPS if table == "interior" else ROUTE_STOPS)[key]
    assert "`" not in words, key
    assert not COORDINATES.search(words), key
    assert "the description has" not in words and "in the description" not in words, key


@pytest.mark.parametrize("kind", [k for k, v in KINDS.items() if v[2]])
def test_an_entry_without_its_flag_names_the_field_to_state_and_says_it_plainly(kind):
    key, words, flag, question = KINDS[kind]
    d = base()
    entries = d.get(key) or []
    assert entries, key
    del entries[0][flag]
    got = measure(d)
    problem, = [p for p in got["problems"] if question in p]
    assert "`" not in problem and "true or false" not in problem
    assert problem.endswith(f"doesn't say whether it is {question} (yes or no)")
    assert asked_field(problem) == f"{key}[].{flag}"


@pytest.mark.parametrize("kind", list(KINDS))
def test_a_list_not_given_names_its_field(kind):
    key = KINDS[kind][0]
    d = base()
    d.pop(key, None)
    problem, = [p for p in measure(d)["problems"] if p.startswith(f"the {KINDS[kind][1]} weren't read")]
    assert asked_field(problem) == key
    assert "`" not in problem


@pytest.mark.parametrize("words", [
    "", "door D2 is marked twice", "the doors sent from the model can't be read (they aren't a list)",
    # a flag's words with nothing where the name is: no entry named, so no field
    Stop("flag_missing", what="door", name="", question="the required exit door", key="exit").reason.replace("  ", " "),
    # a question the kind doesn't ask
    Stop("flag_missing", what="door", name="D1", question="a sleeping room", key="sleeping").reason, None, 3])
def test_any_other_words_name_no_field(words):
    assert asked_field(words) is None


def test_the_name_may_hold_anything_the_host_names_an_element_by():
    name = 'Single-Flush: Door 36" x 84" (LS1.0) (D01)'
    words = Stop("flag_missing", what="door", name=name, question="the required exit door", key="exit").reason
    assert words == f"door {name} doesn't say whether it is the required exit door (yes or no)"
    assert asked_field(words) == "doors[].exit"


# ---- review round 1: the reasons as the measuring gives them, not only the table's words --------------------------

def test_a_window_waiting_on_the_makers_size_names_every_part_of_it_it_needs():
    """A window's maker's clear opening needs its bottom too (Revit: Gordium: Clear offset), never only a door's three."""
    words = Stop("operation_needs_clear", n="n", operation="awning").reason
    assert "bottom" in words and "width" in words and "height" in words and "source" in words
    d = base()
    d["openings"][0].update(operation="awning", stated_clear="big")
    d["openings"][0].pop("frame", None)
    why = measure(d)["parts"]["emergency_escape_opening"][0]["not_measured"]["opening_net_clear_area"]
    assert "its clear width, height, bottom and source" in why


@pytest.mark.parametrize("kind", ["stairs", "guards", "rooms"])
def test_a_list_not_given_never_calls_the_building_a_house(kind):
    """The Children's Odyssey is a day care: "all of the house's stairs" wasn't true of it."""
    words = Stop("not_read", what=kind, key=kind).reason
    assert "house" not in words and words.endswith(f"the model doesn't say these are all the {kind} (or that there "
                                                   "are none)")


def _claims(*entries, **lists):
    d = base()
    d["has_none"] = list(entries)
    d.update(lists)
    return d


@pytest.mark.parametrize("entries, lists, words", [
    # a kind with a list of its own, the list not given: never said to be given
    ([{"kind": "stair", "source": "A-2"}], {}, "the model says the house has no stairs, but stairs have a list of "
                                               "their own in the model"),
    ([{"kind": "emergency_escape_opening", "source": "A-2"}], {}, "has no emergency escape openings, but openings"),
    # more than an entry has: said as more, never "values it doesn't know"
    ([{"kind": "ramp", "source": "A-2", "reding": True}], {}, "giving more than a kind, a source and, optionally, a "
                                                             "reading (also reding)"),
    # the text "yes" is no yes/no value: said so, never "isn't yes or no" of a "yes"
    ([{"kind": "ramp", "source": "A-2", "reading": "yes"}], {}, "its reading isn't a yes/no value"),
])
def test_a_claim_not_taken_says_why_truly_and_plainly(entries, lists, words):
    got = measure(_claims(*entries, **lists))
    said = [p for p in got["problems"] if words in p]
    assert said, got["problems"]
    assert all("`" not in p and "_" not in p for p in said), said


def test_the_door_makers_size_with_more_than_it_has_says_so():
    d = base()
    d["doors"][0]["stated_clear"] = {"width": 34, "height": 80, "source": "maker", "bottom": 0}
    m = measure(d)["parts"]["egress_door"][0]["not_measured"]
    assert "gives more than its width, height and source (also bottom)" in m["door_clear_width"]


def test_route_reasons_as_read_have_no_back_quotes_underscored_fields_or_coordinates():
    """The reasons the route reading gives for a description it can't read, as it gives them: the levels not a
    list, a room with no id, a list that isn't of entries, a story outline on no level given, a not-occupied mark
    given as text, obstructions not a list."""
    from model_measurement.routes import measure as routes_measure
    from model_measurement.routes.floor import read
    from routes_layouts import room_on_corridor
    cases = []
    d = room_on_corridor()
    d["levels"] = "x"
    cases.append(d)
    d = room_on_corridor()
    del d["rooms"][0]["id"]
    cases.append(d)
    d = room_on_corridor()
    d["passages"] = [1]
    cases.append(d)
    d = room_on_corridor()
    d["story_outlines"] = [{"level": "nowhere", "outer": [], "inner": []}]
    cases.append(d)
    d = room_on_corridor()
    d["rooms"][0]["not_occupied"] = "yes"
    cases.append(d)
    d = room_on_corridor()
    d["rooms"][0]["obstructions"] = "a desk"
    cases.append(d)
    said = []
    for d in cases:
        floor = read(d)
        said += list(floor.stops) + [r for s in floor.stories.values() for r in s.stops]
        said += [s.outline_stop for s in floor.stories.values() if getattr(s, "outline_stop", None)]
        for kind, parts in (routes_measure(d)["parts"] or {}).items():
            for p in parts or []:
                said += [w for w in (p.get("not_measured") or {}).values() if isinstance(w, str)]
    assert len({w for w in said}) >= 6, said
    for w in said:
        assert "`" not in w and not COORDINATES.search(w), w
        assert "description" not in w, w                            # the model, never Gordium's file
        assert not re.search(r"\b[a-z]+_[a-z_]+\b", w), w            # no field name of the file format
    assert any("Whether it is not occupied is given as the text 'yes', not as a yes/no value" in w for w in said), said
    assert any("story outline #1 isn't on one of the model's levels" in w for w in said), said


def test_a_dead_ends_door_off_its_legs_is_named_without_coordinates():
    from model_measurement.routes.stops import Stop as RouteStop
    words = RouteStop("door_off_legs", name="at one of its closed ends").reason
    assert not COORDINATES.search(words)
    import inspect
    from model_measurement.routes import dead_ends
    assert "at the closed end (" not in inspect.getsource(dead_ends)


@pytest.mark.parametrize("key, question", [("lockable", "Whether it can be locked"),
                                           ("pass_through", "Whether an exit route may pass through it"),
                                           ("not_occupied", "Whether it is not occupied")])
def test_a_yes_no_mark_given_as_text_is_said_as_its_question(key, question):
    """"its lockable is 'no', not one of yes or no" named the field and contradicted itself: said as the question."""
    from model_measurement.routes.floor import read
    from routes_layouts import room_on_corridor
    d = room_on_corridor()
    d["rooms"][0][key] = "no"
    said = [r for s in read(d).stories.values() for r in s.stops]
    assert any(f"{question} is given as the text 'no', not as a yes/no value" in r for r in said), said
    assert not any("not one of yes or no" in r or key in r for r in said), said
    d["rooms"][0][key] = 1
    assert any(f"{question} is given as 1, not as a yes/no value" in r for s in read(d).stories.values()
               for r in s.stops)


def test_the_interiors_own_reasons_say_the_model_not_the_description():
    for key, blanks in (("not_a_description", {}), ("wrong_format", {"got": "x"}), ("units", {"units": "cubits"})):
        assert "description" not in Stop(key, **blanks).reason, key
    from model_measurement.routes.stops import Stop as RouteStop
    assert RouteStop("description", reason="r").reason.startswith("the model can't be read for escape routes")
