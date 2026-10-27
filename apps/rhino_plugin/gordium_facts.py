#! python3
"""GordiumFacts: change any lot fact (zone, use, lot, main building, corner lot, street lines,
ground, survey), then bedrooms, parking spaces and stories."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _gordium_load  # noqa: E402
gordium_rhino = _gordium_load.module(HERE)   # this copy's Gordium, never another copy's still loaded

gordium_rhino.edit_facts()
