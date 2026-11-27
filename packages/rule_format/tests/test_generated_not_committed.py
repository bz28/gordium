"""Files made by a tool before the tests run are never committed: git ignores them and doesn't track them. The Revit
pane's apartment answer (made by apps/revit_addin/tools/evals/make_apartment_answer.py) changed with almost every rule,
and its committed copy made every waiting PR conflict with each merge (2026-11-27). Kept here, not under apps/, where
nothing may start a process (packages/design_checker/tests/test_check.py's console-window check)."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MADE = ["apps/revit_addin/tests/Gordium.Revit.Reading.Tests/answers/four_unit_apartment_check_answer.json"]


def _git(*args: str) -> int:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True).returncode


@pytest.mark.parametrize("path", MADE)
def test_a_made_file_is_ignored_and_never_tracked(path):
    if _git("rev-parse", "--is-inside-work-tree") != 0:
        pytest.skip("not a git checkout")
    assert _git("check-ignore", "-q", "--no-index", path) == 0
    assert _git("ls-files", "--error-unmatch", path) != 0
