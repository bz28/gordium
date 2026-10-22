#! python3
"""GordiumPanel: register the Gordium panel with Rhino, and nothing else (no check, no checker, the model
untouched). Rhino's "Run these commands every time Rhino starts" list runs it (QUICKSTART, install), so a
Gordium tab Rhino restores at launch is filled ("run GordiumStart or GordiumCheck…"), never "container is empty"."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _gordium_load  # noqa: E402
gordium_rhino = _gordium_load.module(HERE)   # this copy's Gordium, never another copy's still loaded

gordium_rhino.register_dock()
