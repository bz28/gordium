"""Repository-wide pytest options. `--runslow` and the `slow` marker live here so they work from anywhere
(`pytest`, `pytest packages/...`, any one file); the architect stress test's own conftest
(packages/design_checker/tests/stress/conftest.py) decides what `slow` skips.

`--shard K/N` (CI only) runs the K-th of N parts of the collected tests, so N jobs run the suite side by side.
Every collected test goes to exactly one part by construction, and CI checks it: tests/check_shards.py proves the
parts' union is the whole suite and no test is in two parts. The parts are balanced by time: the slow tests listed in
tests/test_durations.json (recorded with `python tests/check_shards.py record`) go longest first to the part with the
least time so far, then every other test likewise at a small fixed cost. A stale or missing list only makes the parts
less even; it never leaves a test out."""

import json
import sys
from pathlib import Path

import pytest

# shared test helpers (tests/host_source.py) import as plain modules from any test file
sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))


def pytest_addoption(parser):
    parser.addoption("--runslow", action="store_true", default=False,
                     help="also run full-size samples marked slow (the architect stress test)")
    parser.addoption("--shard", default=None, metavar="K/N",
                     help="run only part K of N (1-based), the parts balanced by time (tests/test_durations.json); "
                          "every collected test in exactly one part")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: a full-size sample, run only with --runslow or GORDIUM_STRESS_SLOW=1")


def shard_of(text):
    """'2/4' -> (1, 4): the 0-based part and the number of parts; anything else is refused."""
    try:
        k, n = (int(x) for x in text.split("/"))
    except ValueError:
        raise pytest.UsageError(f"--shard takes K/N, such as 2/4, not {text!r}") from None
    if not 1 <= k <= n:
        raise pytest.UsageError(f"--shard {text}: K must be from 1 to N")
    return k - 1, n


DURATIONS = Path(__file__).resolve().parent / "tests/test_durations.json"
UNLISTED = 0.2   # seconds assumed for a test not in the list (the list holds every test of a second or more)


def parts_of(ids, n, seconds):
    """Each test id's 0-based part: longest first, each to the part with the least time so far (ties: the lower
    part, then collection order), so the result is the same on every worker and every job."""
    order = sorted(range(len(ids)), key=lambda i: (-seconds.get(ids[i], UNLISTED), i))
    load, part = [0.0] * n, [0] * len(ids)
    for i in order:
        k = min(range(n), key=lambda j: (load[j], j))
        part[i] = k
        load[k] += seconds.get(ids[i], UNLISTED)
    return part


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    if not config.getoption("--shard"):
        return
    k, n = shard_of(config.getoption("--shard"))
    try:
        seconds = json.loads(DURATIONS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        seconds = {}
    part = parts_of([item.nodeid for item in items], n, seconds)
    keep = [item for item, p in zip(items, part) if p == k]
    gone = [item for item, p in zip(items, part) if p != k]
    if gone:
        config.hook.pytest_deselected(items=gone)
    items[:] = keep


# Every slow test must be in the list, or the balancer counts it at UNLISTED and one part runs long (review round 5,
# 2026-11-24: the tightening walk ran 16 minutes counted as 0.2 s). The list keeps every test whose run (the `call`
# phase) takes a second or more; a part fails only for an unlisted test whose run takes TOO_SLOW or more. Only the run
# counts: a module fixture's setup lands on whichever of its tests runs first, which changes with the order the
# workers take tests (review round 6), and the machines CI runs on are slower or faster than the one the list was
# recorded on, so a test near a second would otherwise fail by chance. A test of a few seconds hardly moves a part's
# time, and its time on CI's machines varies run to run (PR #190, 2026-11-24: four tests of 3.0 to 3.6 s failed two
# parts that had passed before), so a part fails only for an unlisted test of TOO_SLOW, 30 s, or more: CI's run times
# vary a lot run to run (#203, 2026-11-25: a test recorded under a second, so not in the list, took 12 s), and a test
# under 30 s barely moves a part's ~20 minutes; the list still keeps every test of a second or more when recorded.
TOO_SLOW = 30.0
# The list balances the parts by Linux's times, and only a Linux part fails for an unlisted slow test: CI's Windows
# machines take about twice as long (#192, 2026-11-25: two 5 s tests took 11 and 12 s there and failed two Windows
# parts though every test passed), so there the same tests are named but never fail the part.
GUARD_PLATFORM = "linux"


def guard_fails(platform=None):
    """Whether an unlisted slow test fails this machine's part (on Linux only; elsewhere it is only named). The
    platform is read when asked, never once at import."""
    return (sys.platform if platform is None else platform).startswith(GUARD_PLATFORM)
_took = {}


def unlisted_slow(took, listed, limit=TOO_SLOW):
    """The tests whose run (`call`) took `limit` seconds or more and aren't in the list, slowest first. `took` maps
    each test id to its phases' seconds ({"setup": .., "call": .., "teardown": ..})."""
    return sorted(((round(t.get("call", 0.0), 1), i) for i, t in took.items()
                   if t.get("call", 0.0) >= limit and i not in listed), reverse=True)


def pytest_runtest_logreport(report):
    phases = _took.setdefault(report.nodeid, {})
    phases[report.when] = phases.get(report.when, 0.0) + report.duration


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    if not config.getoption("--shard") or hasattr(config, "workerinput"):
        return
    try:
        listed = json.loads(DURATIONS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        listed = {}
    slow = unlisted_slow(_took, listed)
    if slow:
        print(f"\n{len(slow)} test(s) whose run took {TOO_SLOW:g} s or more missing from tests/test_durations.json "
              "(record them with `python tests/check_shards.py record`):")
        for s, i in slow[:20]:
            print(f"  {s} s  {i}")
        if guard_fails():
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
        else:
            print(f"(named only: on {sys.platform} a slow test fails no part; the Linux parts decide)")


# Compile, then freeze (rule_format/published.py; docs/decisions/2026-11-23_laws_validation_speed.md): every state
# law's certificate is current before any test runs. CI publishes before the tests, so there this only checks (about
# 50 ms); a local run publishes the missing or stale ones once, one publisher at a time across pytest-xdist's workers.
# Done at the session's start, before any test file is loaded: a module that reads the laws when it is loaded
# (test_waiting_headline's LAWS) read none on a fresh clone (merge review of main into #228). Again as a session
# fixture, a no-op when nothing changed.
def _publish_laws():
    from rule_format import published
    for note in published.ensure():     # a law that can't be published is said, never a crash (the check refuses it)
        print(f"\nnot published: {note}", file=sys.stderr)


def pytest_sessionstart(session):
    _publish_laws()


@pytest.fixture(scope="session", autouse=True)
def published_laws():
    _publish_laws()
