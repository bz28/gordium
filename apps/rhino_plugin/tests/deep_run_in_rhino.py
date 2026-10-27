#! python3
"""Queue item 12, deep run: the three real-lot designs (test_data/test_sites/new_york/ithaca_city/deep_run/; every rule
worked out by hand from the law, not yet verified by an architect), drawn and checked in Rhino 8 exactly as the
scenarios are (scenarios_in_rhino.py): the lot on the Site layer, each story a floor block on the Building layer, the
garage its own solid, the stated facts saved with the lot; then each design's edit (moving the house) and the check
again. Writes <temp>/gordium_deep_run/rhino_out.json and frames/.

Compare with the hand-worked results (in the repo's .venv):
    python -m design_checker.scenarios --sites rhino <temp>/gordium_deep_run/rhino_out.json

How to run: RunPythonScript this file in Rhino 8 (it opens its own test document from Rhino's feet template).
Not yet run in Rhino (Lane C)."""
import os

os.environ["GORDIUM_SCENARIO_FOLDER"] = "deep_run"
try:                                  # Rhino keeps environment variables between runs: never leave it set
    _here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios_in_rhino.py")
    exec(compile(open(_here, encoding="utf-8").read(), _here, "exec"))
finally:
    os.environ.pop("GORDIUM_SCENARIO_FOLDER", None)
