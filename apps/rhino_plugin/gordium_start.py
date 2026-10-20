#! python3
"""GordiumStart: a new project: confirm the prefilled facts, then draw the lot and the largest legal building."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gordium_rhino  # noqa: E402

gordium_rhino.gordium_start()
