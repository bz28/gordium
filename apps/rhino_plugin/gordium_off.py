#! python3
"""GordiumOff: stop live mode and clear Gordium's drawing."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gordium_rhino  # noqa: E402

gordium_rhino.off()
