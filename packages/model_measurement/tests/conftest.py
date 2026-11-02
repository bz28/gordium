"""In every test here, each reason a measurement gives is checked as it is made: it must have the shape of a
sentence in the stops table (model_measurement/stops.py). A backstop: a hand-written sentence shaped like a
table one would pass (a known limit)."""

import re

import pytest

from model_measurement.places.ithaca_city import measure as measure_module
from model_measurement.stops import STOPS

# a blank holding another reason or an open question may hold anything; any other blank is a word or a few
_OPEN = {"question", "reason"}


def _template(text: str) -> str:
    parts = re.split(r"(\{[a-z_]+\})", text)
    return "".join((".+" if p[1:-1] in _OPEN else "[^;]+") if p.startswith("{") else re.escape(p) for p in parts)


ONE = "(?:" + "|".join(_template(t) for t in STOPS.values()) + ")"
FROM_TABLE = re.compile(ONE + "(?:; " + ONE + ")*")


def from_table(reason: str) -> bool:
    """Whether a reason is one or more of the table's sentences (joined with "; "), blanks filled in."""
    return FROM_TABLE.fullmatch(reason) is not None


@pytest.fixture(autouse=True)
def reasons_come_from_the_table(monkeypatch):
    made = measure_module._record

    def checked(*args, **kwargs):
        record = made(*args, **kwargs)
        reason = record["reason"]
        assert reason is None or from_table(reason), f"a reason not from stops.py: {reason!r}"
        return record

    monkeypatch.setattr(measure_module, "_record", checked)
