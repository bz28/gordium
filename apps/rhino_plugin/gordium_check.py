#! python3
"""GordiumCheck: check the open model, show the envelope, turn on live mode."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gordium_rhino  # noqa: E402

gordium_rhino.gordium_check()
