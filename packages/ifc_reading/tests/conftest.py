"""The made-up model builder (build_ifc.py) as a fixture; tests needing ifcopenshell skip where it isn't installed."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def build():
    pytest.importorskip("ifcopenshell")
    spec = importlib.util.spec_from_file_location("build_ifc", Path(__file__).with_name("build_ifc.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
