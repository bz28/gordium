#! python3
"""GordiumOff: stop live mode and clear Gordium's drawing."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _gordium_load  # noqa: E402
gordium_rhino = _gordium_load.module(HERE)   # this copy's Gordium, never another copy's still loaded

gordium_rhino.off()
