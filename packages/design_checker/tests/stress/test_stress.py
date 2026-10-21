"""The architect stress test, CI sample: random designs built from Gordium's own starting house by the edits an
architect makes, each checked by Gordium and by the independent oracle (oracle.py), with the invariants in
harness.py (a: never a false pass; a2: the tax-map promise; b: no false fail on a clear case; c: monotonic; d: the
same design drawn differently; e: live update and determinism; f: reasons and no crash).

    GORDIUM_STRESS_DESIGNS=3000 GORDIUM_STRESS_SEED=7 pytest packages/design_checker/tests/stress/test_stress.py -s

runs a longer one (the default sample keeps CI near a minute); harness.py runs one in parallel from the command
line. Same seed, same designs, same answers.

A violation that is a known finding (KNOWN, each with its regression test in test_stress_findings.py, marked
xfail until the PR that owns the code fixes it) is reported, not failed; anything else fails this test."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate  # noqa: E402
import harness  # noqa: E402

DESIGNS = int(os.environ.get("GORDIUM_STRESS_DESIGNS", "100"))
SEED = int(os.environ.get("GORDIUM_STRESS_SEED", "20261020"))


def _jog_stepped_line(v):
    return v["invariant"] == "a" and v["lot"] == "jog" and v["rule"] in ("R-1b.side_yards",
                                                                         "R-1b.accessory_buildings")


def _tax_map_area(v):
    return v["invariant"] == "a2" and v["rule"] in ("R-1b.lot_coverage", "R-1b.lot_area_one_family_detached")


def _drawing_changes_height(v):
    return v["invariant"] == "d" and v["rule"] == "R-1b.height" and "floor blocks" not in v.get("what", "")


def _side_names_swap(v):
    return v["invariant"] == "d" and v["rule"] == "R-1b.side_yards" and "outlines drawn" in v.get("what", "")


# finding id -> how to recognise it (test_stress_findings.py has each one's regression test)
KNOWN = {"F1": _jog_stepped_line, "F2": _tax_map_area, "F3": _drawing_changes_height, "F5": _side_names_swap}


def known(v):
    return next((fid for fid, match in KNOWN.items() if match(v)), None)


@pytest.fixture(scope="module")
def fast():
    harness.fast_reads()
    yield
    harness.slow_reads()


def test_reading_the_citys_files_once_changes_no_result():
    """The stress test keeps the city's files after the first read (for speed). The same design checked with the
    real readers and with the kept copies gives exactly the same output."""
    harness.slow_reads()
    design, _ = generate.build("sample_tax", [{"op": "add_roof", "kind": "roof", "axis": 1, "over": 1.5,
                                               "fascia": 0.5, "inset": 3, "rise": 8}])
    slow = harness.gordium(design)
    harness.fast_reads()
    try:
        quick = harness.gordium(design)
    finally:
        harness.slow_reads()
    assert json.dumps(slow, sort_keys=True, default=str) == json.dumps(quick, sort_keys=True, default=str)


def test_the_architect_stress_sample(fast, capsys):
    out = harness.run(DESIGNS, SEED, workers=1, shrink_each=False)
    unknown = [v for v in out["violations"] if not known(v)]
    with capsys.disabled():
        print(f"\nstress test: {out['designs']} designs (seed {out['seed']}) in {out['seconds']} s; invariants run: "
              f"{out['checks_run']}; designs with a violation: {out['violating_designs']}; oracle undecided by rule: "
              f"{out['undecided']}")
        for v in out["violations"]:
            print(f"  {known(v) or 'NEW'} {v['severity']} {v['invariant']} {v['rule']} {v.get('what', '')} "
                  f"{v['lot']} {json.dumps(v['case']['edits'])}")
    if os.environ.get("GORDIUM_STRESS_OUT"):
        Path(os.environ["GORDIUM_STRESS_OUT"]).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    assert out["checks_run"]["a"] == DESIGNS and out["checks_run"]["f"] == DESIGNS
    assert min(out["checks_run"][k] for k in ("c", "d", "e")) > 0
    assert not unknown, "new violations (not a known finding): " + json.dumps(unknown, default=str)[:4000]
