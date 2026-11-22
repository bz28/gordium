"""The words that explain the test split say what conftest.parts_of does: the parts are balanced by time, not
every N-th test (review round 1, 2026-11-22)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_split_is_described_as_balanced_by_time_wherever_it_is_explained():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    conftest = (ROOT / "conftest.py").read_text(encoding="utf-8")
    assert "def parts_of(" in conftest                      # the split is the time-balanced one
    assert "mod 4" not in ci and "every N-th" not in conftest
    assert "parts_of" in ci and "balanced by time" in conftest
