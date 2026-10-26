#! python3
"""GordiumCheck: check the open model and show the envelope (after an edit the results grey out until Check)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _gordium_load  # noqa: E402
gordium_rhino = _gordium_load.module(HERE)   # this copy's Gordium, never another copy's still loaded

gordium_rhino.gordium_check()
