"""The private garage's two stated facts (chart p.2 notes 6 and 7): the cars all the lot's private garages hold
(garage_cars, a whole number, 0 for none) and how many garages there are (private_garages, 1 or more). A bad value is
refused before checking; a blank is measured as blank with its stop (never 0), so the rule reading it needs review."""

import sys
from pathlib import Path

import pytest

from model_measurement.places.ithaca_city.measure import measure
from model_measurement.project import fact_problems
from model_measurement.stops import stop

sys.path.insert(0, str(Path(__file__).parent))
from test_measure import FACTS, RECT, box  # noqa: E402


@pytest.mark.parametrize("value", [-1, 2.5, 3.0, "3", True, None])
def test_garage_cars_is_a_whole_number_zero_or_more(value):
    said = fact_problems({"garage_cars": value})
    if value is None:
        assert said == []
    else:
        assert said == ["garage_cars must be a whole number, 0 or more"], value


@pytest.mark.parametrize("value", [0, -2, 1.5, "2", False])
def test_private_garages_is_a_whole_number_one_or_more(value):
    assert fact_problems({"private_garages": value}) == ["private_garages must be a whole number, 1 or more"], value


def test_good_values_are_kept():
    assert fact_problems({"garage_cars": 0, "private_garages": 1}) == []
    assert fact_problems({"garage_cars": 9, "private_garages": 3}) == []


def _measured(**facts):
    site = {"units": "ft", "lot": RECT, "buildings": [box(10, 25, 35, 65)], "problems": []}
    return measure(site, {**FACTS, **facts})


def test_stated_values_are_measured_as_stated_and_blanks_stop():
    got = _measured(garage_cars=4, private_garages=2)
    assert (got["garage_cars"]["value"], got["private_garages"]["value"]) == (4, 2)
    blank = _measured()
    assert blank["garage_cars"]["value"] is None and blank["private_garages"]["value"] is None
    assert blank["garage_cars"]["reason"] == stop("no_garage_cars")
    assert blank["private_garages"]["reason"] == stop("no_private_garages")
    assert _measured(garage_cars=0)["garage_cars"]["value"] == 0          # "No garage" is an answer, kept as 0
