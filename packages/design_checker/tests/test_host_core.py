"""host_core/: the host-neutral half of rhino_logic.py (facts, streets, lookup, the start box, the place; since
tidy-up PR 6 also freshness, the report's and the panel's words, the neighbourhood, the box's edits, the worker
client), moved there unchanged so a second host (a Revit add-in) can call it.

What must stay true: rhino_logic still offers every moved name as the very same object; a moved name can't be
rebound on rhino_logic (that would patch a dead copy); host_core runs in Rhino 8's own Python (3.9, standard
library only, no YAML); and its two file paths (place.json, model_measurement's street_lines.py) still resolve.
"""
import ast
import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from design_checker import rhino_logic as logic
from design_checker.host_core import (context, edits, facts, freshness, lookup, panel_words, place, report, start_box,
                                     streets, worker_client)
from host_source import CORE_DIR, core_files, host_path, host_text, host_text_of
from moved_names import patch_moved

HOST_CORE_DIR = CORE_DIR
DESIGN_CHECKER_DIR = HOST_CORE_DIR.parent
MODULES = (place, streets, facts, lookup, start_box, freshness, report, panel_words, context, edits, worker_client)
FILES = core_files()
assert Path(facts.__file__).parent == CORE_DIR


def _top_level_names(tree):
    """The names a module defines itself (def, class, assignment, a `with` block's assignments), not imports."""
    out = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            out.add(n.name)
        for s in ([n] if isinstance(n, ast.Assign) else n.body if isinstance(n, ast.With) else []):
            for t in getattr(s, "targets", []):
                out |= {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
    return out


def test_rhino_logic_offers_every_moved_name_as_the_same_object():
    assert logic.HOST_CORE == MODULES
    for module in MODULES:
        assert module.__all__, module.__name__
        for name in module.__all__:
            assert getattr(logic, name) is getattr(module, name), (module.__name__, name)
            assert logic.MOVED[name] is module
    assert len(logic.MOVED) == sum(len(m.__all__) for m in MODULES)        # no name listed by two modules


def test_each_module_lists_exactly_what_it_defines_and_rhino_logic_keeps_no_copy():
    for module in MODULES:
        defined = _top_level_names(ast.parse(host_text_of(module.__file__, purpose="lint"))) - {"__all__", "_f"}
        assert set(module.__all__) == defined, module.__name__
        for name in module.__all__:
            value = getattr(module, name)
            if isinstance(value, (types.FunctionType, type)):
                assert value.__module__ == module.__name__, name      # defined here, not imported
    kept = _top_level_names(ast.parse(host_text("rhino", "logic", purpose="lint")))
    assert not kept & set(logic.MOVED), sorted(kept & set(logic.MOVED))    # a second definition would be a dead copy


def test_a_moved_name_cannot_be_rebound_on_rhino_logic(monkeypatch):
    with pytest.raises(AttributeError, match="FLAT_GROUND moved to design_checker.host_core.facts"):
        logic.FLAT_GROUND = False
    with pytest.raises(AttributeError, match="box_rows moved to design_checker.host_core.start_box"):
        monkeypatch.setattr(logic, "box_rows", lambda state: [])
    with pytest.raises(AttributeError):
        del logic.street_verdict
    # PR 6's names too: freshness decides whether a result shows as current, so a dead copy here would be a test
    # passing for the wrong reason on exactly the false-pass path
    with pytest.raises(AttributeError, match="result_stale moved to design_checker.host_core.freshness"):
        monkeypatch.setattr(logic, "result_stale", lambda *a: False)
    with pytest.raises(AttributeError, match="UNDO_WORDS moved to design_checker.host_core.freshness"):
        logic.UNDO_WORDS = {}
    with pytest.raises(AttributeError, match="answer_for moved to design_checker.host_core.worker_client"):
        monkeypatch.setattr(logic, "answer_for", None)
    assert logic.result_stale is freshness.result_stale and logic.Job is worker_client.Job
    assert logic.FLAT_GROUND is facts.FLAT_GROUND and logic.box_rows is start_box.box_rows
    monkeypatch.setattr(logic, "ERROR_LOG", "elsewhere.log")       # a name that stays (the plugin sets it) still can
    assert logic.ERROR_LOG == "elsewhere.log"


def test_patch_moved_swaps_every_binding_and_puts_them_back(monkeypatch):
    """FLAT_GROUND is read by facts, lookup and start_box functions and by apply_lookup (host_core/edits.py since
    PR 6), and rhino_logic re-exports it."""
    holders = [m for m in (logic, *MODULES) if "FLAT_GROUND" in vars(m)]
    assert holders == [logic, facts, lookup, start_box, edits]
    with monkeypatch.context() as m:
        patch_moved(m, logic, "FLAT_GROUND", "swapped")
        assert [vars(h)["FLAT_GROUND"] for h in holders] == ["swapped"] * 5
        assert start_box.box_rows.__globals__["FLAT_GROUND"] == "swapped"
        assert logic.apply_lookup.__globals__["FLAT_GROUND"] == "swapped"
    assert all(vars(h)["FLAT_GROUND"] is True for h in holders)


@pytest.mark.parametrize("path", [*FILES, host_path("rhino", "logic")], ids=lambda p: p.name)
def test_every_module_import_is_used(path):
    """Review round 1: the move left rhino_logic importing datetime, which only the moved city_day used."""
    tree = ast.parse(host_text_of(path, purpose="lint"))
    bound = {(a.asname or a.name).split(".")[0] for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
             for a in n.names}
    read = {x.id for x in ast.walk(tree) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}
    assert bound - read - {"__future__"} == set()


@pytest.mark.parametrize("path", [*FILES, host_path("rhino", "logic")], ids=lambda p: p.name)
def test_host_core_and_rhino_logic_parse_as_python_3_9(path):
    ast.parse(host_text_of(path, purpose="lint"), feature_version=(3, 9))


def test_host_core_imports_only_the_standard_library_and_itself():
    for path in FILES:
        for n in ast.walk(ast.parse(host_text_of(path, purpose="lint"))):
            if isinstance(n, ast.Import):
                for a in n.names:
                    assert a.name.split(".")[0] in sys.stdlib_module_names, (path.name, a.name)
            elif isinstance(n, ast.ImportFrom):
                assert n.level == 1 or (n.level == 0 and n.module.split(".")[0] in sys.stdlib_module_names), \
                    (path.name, n.module)


RHINO_IMPORT = """
import sys, types
sys.modules["host_core"] = types.ModuleType("host_core")      # a copy cached before (another checkout)
sys.path.insert(0, sys.argv[1])
import rhino_logic as logic
from host_core import facts, freshness, worker_client
assert logic.FLAT_GROUND is facts.FLAT_GROUND
assert logic.result_stale is freshness.result_stale and logic.Job is worker_client.Job
print(sys.version_info[:2], logic.box_rows.__module__, facts.__file__, logic.PLACE["name"],
      logic.street_verdict([[[0, 0], [100, 0]]])[0], sorted(n for n in sys.modules if n.split(".")[0] in
      ("yaml", "rule_format", "design_checker", "model_measurement")),
      "stale:", logic.result_stale(1.0, 0.0, 10.0, 2.0, False), logic.result_stale(1.0, 5.0, 10.0, 2.0, False),
      logic.Job(lambda step: 7, "x").wait(5) and logic.Job.__module__)
"""


def _rhino_import(python):
    """rhino_logic imported the way Rhino does (its folder on sys.path, no site-packages: -I -S)."""
    out = subprocess.run([python, "-I", "-S", "-c", RHINO_IMPORT, str(DESIGN_CHECKER_DIR)], capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_rhino_imports_this_folders_host_core_without_any_installed_package():
    said = _rhino_import(sys.executable)
    assert "host_core.start_box" in said and str(HOST_CORE_DIR / "facts.py") in said
    assert "City of Ithaca" in said and " one []" in said          # place.json and street_lines.py found; no packages
    assert said.rstrip().endswith("stale: True False host_core.worker_client")    # PR 6's modules load and answer


def _python_3_9():
    for candidate in ("python3.9", "/usr/bin/python3"):
        found = shutil.which(candidate)
        if found and subprocess.run([found, "-c", "import sys; sys.exit(sys.version_info[:2] != (3, 9))"]
                                    ).returncode == 0:
            return found
    return None


@pytest.mark.skipif(_python_3_9() is None, reason="no Python 3.9 on this machine (Rhino 8's version)")
def test_rhino_logic_and_host_core_load_and_answer_in_python_3_9():
    said = _rhino_import(_python_3_9())
    assert said.startswith("(3, 9) host_core.start_box")
    assert said.rstrip().endswith("stale: True False host_core.worker_client")


def test_the_two_file_paths_still_resolve_from_one_folder_deeper():
    assert place.PLACE == json.loads((DESIGN_CHECKER_DIR / "place.json").read_text(encoding="utf-8"))
    loaded = streets._street_lines()
    assert Path(loaded.__file__).resolve() == (DESIGN_CHECKER_DIR.parents[1] / "model_measurement" /
                                              "model_measurement" / "street_lines.py").resolve()


def test_host_core_lists_every_module_on_its_own_row():
    """Review round 1 of PR 6: `edits` was squeezed onto start_box's row, so it read "...buttons and reset edits"."""
    import re
    import design_checker.host_core as host_core
    rows = re.findall(r"^  (\w+) {2,}\S", host_core.__doc__, re.M)
    assert sorted(rows) == sorted(m.__name__.rsplit(".", 1)[1] for m in MODULES)


def _relative_imports(tree, after_line=0):
    return {n.module for n in tree.body if isinstance(n, ast.ImportFrom) and n.level == 1 and n.lineno > after_line}


def test_an_import_said_to_be_last_for_a_cycle_is_one():
    """Review round 1 of PR 6: an end-of-file import's comment said the module it names calls back into this one,
    when nothing did (edits, worker_client). Where the comment stands, a module imported below it imports this one."""
    said = "call back into this one"
    for path in FILES:
        text = host_text_of(path, purpose="lint")
        if said not in text:
            continue
        line = text[:text.index(said)].count("\n") + 1
        tree = ast.parse(text)
        back = [m for m in _relative_imports(tree, line)
                if path.stem in _relative_imports(ast.parse(host_text_of(CORE_DIR / (m + ".py"), purpose="lint")))]
        assert back, path.name


@pytest.mark.parametrize("module", [m.__name__.rsplit(".", 1)[1] for m in MODULES])
def test_each_module_loads_first_on_its_own(module):
    """Imported first, alone, the way Rhino's folder import would reach it: its own imports (top or end) all load."""
    out = subprocess.run([sys.executable, "-I", "-S", "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
                          "import host_core.%s as m; print(len(m.__all__))" % module, str(DESIGN_CHECKER_DIR)],
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0 and int(out.stdout) > 0, out.stderr
