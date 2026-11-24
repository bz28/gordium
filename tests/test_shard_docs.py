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


def _conftest():
    import importlib.util
    spec = importlib.util.spec_from_file_location("root_conftest", ROOT / "conftest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_slow_test_missing_from_the_durations_list_is_found_and_a_listed_or_quick_one_is_not():
    """Review round 5 (2026-11-24): a 16-minute test the list lacked was counted at 0.2 s; a part now fails for an
    unlisted test of TOO_SLOW or more."""
    c = _conftest()
    took = {"a::slow_unlisted": 960.0, "a::slow_listed": 40.0, "a::quick": 0.4, "a::edge": c.TOO_SLOW}
    assert c.unlisted_slow(took, {"a::slow_listed": 38.0}) == [(960.0, "a::slow_unlisted"), (c.TOO_SLOW, "a::edge")]
    assert c.unlisted_slow(took, dict.fromkeys(took)) == []


def test_every_test_listed_as_slow_is_still_a_real_test_id_shape_and_a_second_or_more():
    import json
    listed = json.loads((ROOT / "tests" / "test_durations.json").read_text(encoding="utf-8"))
    assert listed and all("::" in i and s >= 1.0 for i, s in listed.items())
