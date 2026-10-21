"""The stress folder's two sizes. Every sampled test runs a small fixed sample in CI (the whole folder in about a
minute) and, marked `slow`, the full sample, which runs only when asked:

    pytest --runslow          (from anywhere; or GORDIUM_STRESS_SLOW=1)

The option and the marker are registered in the repository's root conftest.py; README.md gives each test's sizes."""

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow", default=False) or os.environ.get("GORDIUM_STRESS_SLOW") == "1":
        return
    skip = pytest.mark.skip(reason="full-size stress sample: run with --runslow or GORDIUM_STRESS_SLOW=1")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
