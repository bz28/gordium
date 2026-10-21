"""The stress folder's two sizes. Every sampled test runs a small fixed sample in CI (the whole folder in about a
minute) and, marked `slow`, the full sample, which runs only when asked:

    pytest packages/design_checker/tests/stress --runslow       (or GORDIUM_STRESS_SLOW=1)

See README.md for each test's sizes."""

import os

import pytest


def pytest_addoption(parser):
    parser.addoption("--runslow", action="store_true", default=False,
                     help="also run the stress tests' full-size samples (marked slow)")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: a stress test's full-size sample (runs with --runslow)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow") or os.environ.get("GORDIUM_STRESS_SLOW") == "1":
        return
    skip = pytest.mark.skip(reason="full-size stress sample: run with --runslow or GORDIUM_STRESS_SLOW=1")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
