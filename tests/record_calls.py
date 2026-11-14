"""A pytest plugin that records every host_core call the tests make (design_checker/call_session.py runs it):

    GORDIUM_RECORD_CALLS=<folder> pytest -p record_calls <tests...>

Off unless that variable is set. host_core's functions are wrapped once, before any test module is imported, so every
served function's call through rhino_logic (the Rhino plugin's own name for them) or host_core is seen (worker_client.CallRecorder)."""

import json
import os


def pytest_configure(config):
    from design_checker import rhino_logic as logic
    from design_checker.call_session import served
    from design_checker.host_core.worker_client import CallRecorder
    recorder = CallRecorder.from_env(os.environ)
    if recorder is not None:            # (only the functions the worker serves: the parity test's)
        recorder.install(logic.HOST_CORE, also=(logic,), only=set(served()))
        config._gordium_calls = recorder


def pytest_unconfigure(config):
    recorder = getattr(config, "_gordium_calls", None)
    if recorder is not None:
        os.makedirs(recorder.folder, exist_ok=True)
        with open(os.path.join(recorder.folder, "skipped-%d.json" % os.getpid()), "w", encoding="utf-8") as f:
            json.dump(recorder.skipped, f, sort_keys=True)
