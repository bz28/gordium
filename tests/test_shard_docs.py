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
    unlisted test whose run takes TOO_SLOW or more."""
    c = _conftest()
    took = {"a::slow_unlisted": {"call": 960.0}, "a::slow_listed": {"call": 40.0}, "a::quick": {"call": 0.4},
            "a::edge": {"setup": 0.1, "call": c.TOO_SLOW}}
    assert c.unlisted_slow(took, {"a::slow_listed": 38.0}) == [(960.0, "a::slow_unlisted"), (c.TOO_SLOW, "a::edge")]
    assert c.unlisted_slow(took, dict.fromkeys(took)) == []


def test_a_test_slow_only_in_its_module_fixtures_setup_never_fails_the_part():
    """Review round 6 (2026-11-24): a module fixture's setup lands on whichever of its tests runs first, which changes
    with the order the workers take them, so only the run (`call`) decides."""
    c = _conftest()
    took = {"m::first_to_run": {"setup": 60.0, "call": 0.1, "teardown": 0.0}, "m::second": {"call": 0.1}}
    assert c.unlisted_slow(took, {}) == []


def test_record_lists_a_test_by_its_run_at_its_whole_time_and_never_one_slow_only_in_setup():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_shards", ROOT / "tests" / "check_shards.py")
    cs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cs)
    seconds = {"a::run": 12.5, "a::setup_only": 30.0, "a::quick": 1.2}
    run = {"a::run": 10.0, "a::quick": 0.6}
    assert cs.listed(seconds, run) == {"a::run": 12.5}


def test_every_test_listed_as_slow_is_still_a_real_test_id_shape_and_a_second_or_more():
    import json
    listed = json.loads((ROOT / "tests" / "test_durations.json").read_text(encoding="utf-8"))
    assert listed and all("::" in i and s >= 1.0 for i, s in listed.items())


def test_a_test_of_a_few_seconds_never_fails_a_part_by_chance():
    # PR #190 (2026-11-24): four unlisted tests of 3.0 to 3.6 s, quick on the run before, failed two parts on CI;
    # only a test of 30 s or more fails a part (#203: a 12 s run of a usually quick test), and a listed one never does
    c = _conftest()
    took = {"a::few": {"call": 3.6}, "a::twelve": {"call": 12.1}, "a::thirty": {"call": 30.0}}
    assert c.unlisted_slow(took, {}) == [(30.0, "a::thirty")]


def test_only_a_linux_part_fails_for_an_unlisted_slow_test():
    # #192 (2026-11-25): Windows CI runs about twice as slow, so two 5 s tests failed two Windows parts; the list is
    # Linux's, and only Linux parts fail for a test missing from it
    c = _conftest()
    assert c.guard_fails("linux") and not c.guard_fails("win32") and not c.guard_fails("darwin")


def test_the_part_itself_fails_on_linux_and_only_names_the_test_on_windows(monkeypatch, tmp_path):
    # review round 1 (#197): the hook that sets the part's result, not only guard_fails, is what's pinned
    import types
    import pytest
    c = _conftest()
    listed = tmp_path / "durations.json"
    listed.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(c, "DURATIONS", listed)
    monkeypatch.setattr(c, "_took", {"a::slow_unlisted": {"call": c.TOO_SLOW}})
    for platform, failed in (("linux", True), ("win32", False)):
        monkeypatch.setattr(c.sys, "platform", platform)
        config = types.SimpleNamespace(getoption=lambda name: "1/4")
        session = types.SimpleNamespace(config=config, exitstatus=pytest.ExitCode.OK)
        c.pytest_sessionfinish(session, 0)
        assert (session.exitstatus == pytest.ExitCode.TESTS_FAILED) is failed, platform
