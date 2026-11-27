"""Every test file is where CI's plain `pytest` collects it (pyproject's testpaths). PR #266's review (2026-11-27):
tests/test_shard_docs.py sat outside testpaths, so no CI part and no whole-suite count (tests/check_shards.py) ever ran
it. Kept under packages/, which is always collected, so the check runs even if testpaths loses a folder."""
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# The in-Rhino tests run inside Rhino (they import Rhino), never under pytest (apps/rhino_plugin/README.md)
NOT_PYTEST = ("apps/rhino_plugin/tests/",)


def _testpaths():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]["testpaths"]


def outside(files, paths):
    """The test files (test_*.py, *_test.py) no testpaths folder holds, the in-Rhino tests aside."""
    tests = [f for f in files if Path(f).name.startswith("test_") and f.endswith(".py") or f.endswith("_test.py")]
    return [f for f in tests if not any(f.startswith(p.rstrip("/") + "/") for p in paths) and not f.startswith(NOT_PYTEST)]


def test_every_test_file_is_where_pytest_collects_it():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           check=True).stdout.splitlines()
    assert "tests/test_shard_docs.py" in files
    assert outside(files, _testpaths()) == []


def test_a_test_file_outside_testpaths_is_found_and_one_inside_or_in_rhino_is_not():
    files = ["tests/test_shard_docs.py", "packages/a/tests/test_b.py", "apps/rhino_plugin/tests/test_docs_in_rhino.py",
             "docs/x_test.py", "tests/check_shards.py"]
    assert outside(files, ["packages", "apps/revit_addin/tools"]) == ["tests/test_shard_docs.py", "docs/x_test.py"]
    assert outside(files, ["packages", "tests"]) == ["docs/x_test.py"]
