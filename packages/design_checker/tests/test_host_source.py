"""Tests read a host's source (the Rhino plugin today) only through tests/host_source.py.

One helper means a second host (a Revit add-in) only adds its file list, and every read says why it reads: `lint`
(a structural rule any host must follow) or `wiring` (only proves the plugin calls X). This file fails when a test
names a plugin file itself instead of asking the helper, and checks the helper.
"""
import ast
import re
import sys
from pathlib import Path

import pytest

from host_source import (HOSTS, PURPOSES, host_dir, host_doc, host_command_files, host_files, host_path, host_script, host_scripts,
                         host_text, host_text_of)

REPO = Path(__file__).resolve().parents[3]
PLUGIN_NAME = re.compile(r"rhino_plugin|rhino_logic\.py|(?<![A-Za-z0-9])_?gordium_[\w*]+\.py")
LOGIC_MODULES = {"logic", "_logic", "logic_", "rhino_logic"}      # a test's names for the imported rhino_logic module
# a test names no plugin file to read. The allowlist is for text the plugin's own install step or guide must contain
# (a command name, a path the guide tells a person to type), which is something the tests expect, not something they open.
_CHECK = "packages/design_checker/tests/test_check.py"
_SETUP = "packages/design_checker/tests/test_quickstart_setup.py"
ALLOWED = {(_CHECK, '"GordiumPanel": "gordium_panel.py"'), (_CHECK, "Gordium: GordiumPanel -> gordium_panel.py"),
           (_SETUP, "/apps/rhino_plugin/install.py"), (_SETUP, "apps\\rhino_plugin\\install.py"),
           (_SETUP, "Resolve-Path apps\\rhino_plugin\\install.py")}


def _test_files():
    skip = {Path(__file__).resolve(), REPO / "tests/host_source.py"}
    found = list(REPO.glob("packages/*/tests/**/*.py")) + list((REPO / "tests").glob("*.py"))
    return sorted(p for p in found if p.resolve() not in skip)


def _plugin_names_in(source):
    """The string constants of a test file that name a plugin file or folder (a docstring or comment is prose)."""
    tree = ast.parse(source)
    prose = {id(n.body[0].value) for n in ast.walk(tree)
             if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
             and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    named = [(n.lineno, n.value) for n in ast.walk(tree)
             if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in prose
             and PLUGIN_NAME.search(n.value)]
    # rhino_logic's own file found through the imported module (`Path(logic.__file__).read_text()`)
    named += [(n.lineno, ast.unparse(n)) for n in ast.walk(tree)
              if isinstance(n, ast.Attribute) and n.attr == "__file__" and isinstance(n.value, ast.Name)
              and n.value.id in LOGIC_MODULES]
    return named


def test_no_test_reads_a_plugin_file_except_through_the_helper():
    offenders = []
    for path in _test_files():
        rel = path.relative_to(REPO).as_posix()
        for lineno, value in _plugin_names_in(path.read_text(encoding="utf-8")):
            if (rel, value) not in ALLOWED:
                offenders.append(f"{rel}:{lineno}: {value[:60]!r}")
    assert offenders == [], "read plugin source with tests/host_source.py (host_text, host_files...):\n" + "\n".join(offenders)


def test_the_guard_catches_a_direct_read_and_ignores_prose():
    direct = 'def test_x():\n    t = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text()\n'
    assert [v for _, v in _plugin_names_in(direct)] == ["apps/rhino_plugin/gordium_ui.py"]
    by_name = 'def test_x():\n    t = (PLUGIN / "gordium_rhino.py").read_text()\n'
    assert [v for _, v in _plugin_names_in(by_name)] == ["gordium_rhino.py"]
    logic = 'T = Path("packages/design_checker/design_checker/rhino_logic.py").read_text()\n'
    assert len(_plugin_names_in(logic)) == 1
    # a file found by glob or through the imported module, and a plugin file the old fixed list did not name
    assert _plugin_names_in('files = PLUGIN.glob("gordium_*.py")') != []
    assert _plugin_names_in('x = "_gordium_load.py"') != [] and _plugin_names_in('x = "gordium_new.py"') != []
    assert _plugin_names_in("tree = ast.parse(Path(logic.__file__).read_text())") != []
    assert _plugin_names_in("tree = ast.parse(Path(measure.__file__).read_text())") == []      # not the plugin's
    assert _plugin_names_in('x = "gordium_site"') == []
    prose = '"""Reads apps/rhino_plugin/gordium_ui.py."""\ndef test_x():\n    """gordium_rhino.py"""\n    # gordium_ui.py\n'
    assert _plugin_names_in(prose) == []


def test_the_helper_knows_the_plugin_files_and_every_read_needs_a_purpose():
    assert [p.name for p in host_files("rhino")] == ["gordium_rhino.py", "gordium_ui.py"]
    assert all(p.name.endswith("_in_rhino.py") for p in host_scripts("rhino")) and host_scripts("rhino")
    assert host_files("rhino", scripts=True)[:2] == host_files("rhino")
    assert len(host_files("rhino", scripts=True)) == 2 + len(host_scripts("rhino"))
    assert [p.name for p in host_command_files("rhino")] == sorted(p.name for p in host_dir("rhino").glob("gordium_*.py"))
    assert "gordium_ui.py" in [p.name for p in host_command_files("rhino")]
    assert host_path("rhino", "logic").name == "rhino_logic.py" and host_dir("rhino").name == "rhino_plugin"
    assert "def start_box(" in host_text("rhino", "ui", purpose="wiring")
    assert host_text_of(host_files("rhino")[0], purpose="lint") == host_text("rhino", "plugin", purpose="lint")
    assert host_doc("rhino", "QUICKSTART.md", purpose="wiring").startswith("#")
    assert PURPOSES == ("lint", "wiring") and "rhino" in HOSTS
    with pytest.raises(ValueError):
        host_text("rhino", "ui", purpose="because")
    with pytest.raises(TypeError):
        host_text("rhino", "ui")                     # a purpose is required
    with pytest.raises(KeyError):
        host_files("revit")


def test_tests_import_the_helper_from_any_folder():
    assert str(REPO / "tests") in sys.path
