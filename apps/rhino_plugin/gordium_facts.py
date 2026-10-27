#! python3
"""GordiumFacts: change any lot fact (zone, use, lot, main building, corner lot, street lines,
ground, survey), then bedrooms, parking spaces and stories."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gordium_rhino  # noqa: E402

gordium_rhino.edit_facts()
