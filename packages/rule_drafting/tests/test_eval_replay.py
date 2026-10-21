"""The eval replay script rebuilds a drafted/ folder from scratch, so it must never touch the real one
(audit P1-5: it used to delete the drafted rulebooks of whichever checkout Python resolved, at import)."""
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest
from rule_format.rulebook import REPO

REPLAY = Path(__file__).resolve().parents[1] / "evals/2026-10-20_prompt_a/replay.py"


@pytest.fixture
def deletions(monkeypatch):
    """Every shutil.rmtree the replay asks for, recorded instead of done."""
    calls = []
    monkeypatch.setattr(shutil, "rmtree", lambda path, *a, **k: calls.append(Path(path)))
    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.setattr(sys, "argv", ["replay.py", "runs/some_run.jsonl"])
    return calls


def load_replay():
    spec = importlib.util.spec_from_file_location("eval_replay", REPLAY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_importing_the_replay_deletes_nothing(deletions):
    load_replay()
    assert deletions == []


def test_the_replay_refuses_the_checkout_gordium_is_installed_from(deletions, capsys):
    replay = load_replay()
    installed = replay.installed_checkout()
    if installed != REPO.resolve():
        pytest.skip("this test run isn't from an editable install of this checkout")
    assert replay.main(["--checkout", str(REPO), "runs/some_run.jsonl"]) == 2
    assert deletions == []
    assert "installed from" in capsys.readouterr().err


def test_the_replay_refuses_a_checkout_whose_code_is_not_the_one_running(deletions, tmp_path, capsys):
    replay = load_replay()
    assert replay.main(["--checkout", str(tmp_path), "runs/some_run.jsonl"]) == 2
    assert deletions == []
    assert "PYTHONPATH" in capsys.readouterr().err


def test_the_replay_needs_a_checkout_named(deletions):
    replay = load_replay()
    with pytest.raises(SystemExit):
        replay.main(["runs/some_run.jsonl"])
    assert deletions == []


def test_the_replay_refuses_a_drafted_folder_holding_files_git_does_not_have(deletions, tmp_path, monkeypatch):
    """drafted/ is in git on no branch: real AI drafts and their paid-call records exist only on disk, so a
    checkout whose drafted/ holds any file (tracked changes, untracked or ignored) is refused."""
    import subprocess
    replay = load_replay()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    drafted = tmp_path / "drafted"
    monkeypatch.setattr(replay, "REPO", tmp_path)
    monkeypatch.setattr(replay, "installed_checkout", lambda: None)
    assert replay.refusal(tmp_path, drafted) is None                    # nothing there: may rebuild
    (drafted / "records").mkdir(parents=True)
    (drafted / "records/ai_calls.jsonl").write_text("{}\n", encoding="utf-8")
    assert "for good" in replay.refusal(tmp_path, drafted)
    (tmp_path / ".gitignore").write_text("drafted/\n", encoding="utf-8")
    assert "for good" in replay.refusal(tmp_path, drafted)              # ignored files count too
