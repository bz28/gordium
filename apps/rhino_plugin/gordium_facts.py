#! python3
"""GordiumFacts: edit the lot facts (bedrooms, parking spaces, stories)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gordium_rhino  # noqa: E402

gordium_rhino.edit_facts()
