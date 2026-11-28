"""Every test file is where CI's plain `pytest` collects it (pyproject's testpaths). PR #266's review (2026-11-27):
tests/test_shard_docs.py sat outside testpaths, so no CI part and no whole-suite count (tests/check_shards.py) ever ran
it. Kept under packages/, which is always collected, so the check runs even if testpaths loses a folder."""
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# A test that imports Rhino runs inside Rhino, never under pytest (the Rhino plugin's README): told by what it
# imports, never by a folder named here (tests name no plugin path: test_host_source.py)
IMPORTS_RHINO = re.compile(r"^\s*(?:import|from)\s+Rhino\b", re.M)


def _testpaths():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]["testpaths"]


def _runs_in_rhino(rel: str) -> bool:
    return bool(IMPORTS_RHINO.search((ROOT / rel).read_text(encoding="utf-8")))


def outside(files, paths, runs_in_rhino=_runs_in_rhino):
    """The test files (test_*.py, *_test.py) no testpaths folder holds, those that run inside Rhino aside."""
    tests = [f for f in files if Path(f).name.startswith("test_") and f.endswith(".py") or f.endswith("_test.py")]
    return [f for f in tests if not any(f.startswith(p.rstrip("/") + "/") for p in paths) and not runs_in_rhino(f)]


def test_every_test_file_is_where_pytest_collects_it():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           check=True).stdout.splitlines()
    assert "tests/test_shard_docs.py" in files
    assert outside(files, _testpaths()) == []


def test_a_test_file_outside_testpaths_is_found_and_one_inside_or_run_in_rhino_is_not():
    files = ["tests/test_shard_docs.py", "packages/a/tests/test_b.py", "apps/host/tests/test_in_host.py",
             "docs/x_test.py", "tests/check_shards.py"]
    in_host = {"apps/host/tests/test_in_host.py"}.__contains__
    assert outside(files, ["packages", "apps/revit_addin/tools"], in_host) == ["tests/test_shard_docs.py", "docs/x_test.py"]
    assert outside(files, ["packages", "tests"], in_host) == ["docs/x_test.py"]
    assert IMPORTS_RHINO.search("import os\nimport Rhino\n") and IMPORTS_RHINO.search("from Rhino.Geometry import Point3d")
    assert not IMPORTS_RHINO.search("import Rhinoceros\n") and not IMPORTS_RHINO.search('"""uses Rhino"""\nimport os\n')
