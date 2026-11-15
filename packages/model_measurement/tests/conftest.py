"""In every test here, each reason a measurement gives is checked as it is made: it must have the shape of a
sentence in the stops table (model_measurement/stops.py). A backstop: a hand-written sentence shaped like a
table one would pass (a known limit)."""

import re

import pytest

from model_measurement.places.ithaca_city import measure as measure_module
from model_measurement.stops import STOPS, TOOL_WORDS

# a blank holding another reason or an open question may hold anything; any other blank is a word or a few
_OPEN = {"question", "reason"}


def _template(text: str) -> str:
    parts = re.split(r"(\{[a-z_]+\})", text)
    return "".join((".+" if p[1:-1] in _OPEN else "[^;]+") if p.startswith("{") else re.escape(p) for p in parts)


# the design tool's own words (any words at all) are never a reason the measuring gives
ONE = "(?:" + "|".join(_template(t) for k, t in STOPS.items() if k != TOOL_WORDS) + ")"
FROM_TABLE = re.compile(ONE + "(?:; " + ONE + ")*")


def from_table(reason: str) -> bool:
    """Whether a reason is one or more of the table's sentences (joined with "; "), blanks filled in."""
    return FROM_TABLE.fullmatch(reason) is not None


def pytest_configure(config):
    config.addinivalue_line("markers", "tool_words: the test gives a building the design tool's own words (any words)")


@pytest.fixture(autouse=True)
def reasons_come_from_the_table(monkeypatch, request):
    made = measure_module._record
    # the design tool's own words pass through as a reason whatever they say: only where a test sends them
    tool = request.node.get_closest_marker("tool_words") is not None

    def checked(*args, **kwargs):
        record = made(*args, **kwargs)
        reason = record["reason"]
        assert reason is None or from_table(reason) or tool, f"a reason not from stops.py: {reason!r}"
        return record

    monkeypatch.setattr(measure_module, "_record", checked)
