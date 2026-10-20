#! python3
"""GordiumLive: turn live re-checking on or off."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gordium_rhino  # noqa: E402

gordium_rhino.toggle_live()
