"""Repository-wide pytest options. `--runslow` and the `slow` marker live here so they work from anywhere
(`pytest`, `pytest packages/...`, any one file); the architect stress test's own conftest
(packages/design_checker/tests/stress/conftest.py) decides what `slow` skips."""


def pytest_addoption(parser):
    parser.addoption("--runslow", action="store_true", default=False,
                     help="also run full-size samples marked slow (the architect stress test)")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: a full-size sample, run only with --runslow or GORDIUM_STRESS_SLOW=1")
