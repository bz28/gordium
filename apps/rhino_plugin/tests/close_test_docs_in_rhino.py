#! python3
"""Closes every in-Rhino test document left open (only those under <temp>/gordium_test_docs/), unsaved. Run it as its
own script after a test that must not close its document itself (linked_file_in_rhino.py), once Rhino has idled."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import close, leftovers  # noqa: E402

for d in leftovers():
    close(d)
