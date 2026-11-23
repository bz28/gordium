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
