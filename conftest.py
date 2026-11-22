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
