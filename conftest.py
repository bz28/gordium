"""Repository-wide pytest options. `--runslow` and the `slow` marker live here so they work from anywhere
(`pytest`, `pytest packages/...`, any one file); the architect stress test's own conftest
(packages/design_checker/tests/stress/conftest.py) decides what `slow` skips.

`--shard K/N` (CI only) runs the K-th of N equal parts of the collected tests, so N jobs run the suite side by
side. Every test is in exactly one part by construction (test number i goes to part i mod N + 1), and CI checks
it: tests/check_shards.py proves the parts' union is the whole suite and no test is in two parts."""

import sys
from pathlib import Path

import pytest

# shared test helpers (tests/host_source.py) import as plain modules from any test file
sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))


def pytest_addoption(parser):
    parser.addoption("--runslow", action="store_true", default=False,
                     help="also run full-size samples marked slow (the architect stress test)")
    parser.addoption("--shard", default=None, metavar="K/N",
                     help="run only part K of N (1-based): every N-th collected test, starting at the K-th")


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


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    if not config.getoption("--shard"):
        return
    k, n = shard_of(config.getoption("--shard"))
    # collection order is the same on every worker and every job (pytest sorts files and keeps definition order),
    # so the parts never overlap; round robin spreads each slow file's tests over every part
    keep = [item for i, item in enumerate(items) if i % n == k]
    gone = [item for i, item in enumerate(items) if i % n != k]
    if gone:
        config.hook.pytest_deselected(items=gone)
    items[:] = keep
