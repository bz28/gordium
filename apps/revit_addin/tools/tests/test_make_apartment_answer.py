"""The Revit pane's four-unit apartment answer (tests/Gordium.Revit.Reading.Tests/answers/
four_unit_apartment_check_answer.json, read by ResultViewsTests, ResultViewListTests, the other pane tests and the pane
renders) is made by tools/evals/make_apartment_answer.py from the checker, never committed. Until 2026-11-27 it was committed
and test_pane_answer_fresh.py failed whenever a rule change moved it (PR #181 review rounds 13 to 16), so almost every
rule PR changed it and conflicted with every other waiting PR. These tests hold what replaced that: the tool writes the
checker's answer exactly as the worker writes it and never writes an error; every CI job that runs the C# tests
makes it first; and a C# build without it stops and says how to make it. That git never tracks it is held by
packages/rule_format/tests/test_generated_not_committed.py (nothing under apps/ may start a process: test_check.py's
console-window check; and pytest collects only packages/ and apps/revit_addin/tools, never the top-level tests/)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(TOOLS / "evals"))

import make_apartment_answer as tool  # noqa: E402

ANSWER = "apps/revit_addin/tests/Gordium.Revit.Reading.Tests/answers/four_unit_apartment_check_answer.json"


def test_the_tool_answers_the_apartments_trial_request_into_the_file_the_pane_tests_read():
    assert tool.OUT == REPO / ANSWER
    assert tool.REQUEST == REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json"
    assert tool.REQUEST.is_file()


def test_it_writes_the_checkers_answer_as_the_worker_writes_it(tmp_path):
    given = []
    made = {"id": 1, "ok": True, "result": {"view": {"items": [{"id": "a", "sign": "≥", "status": "needs_review"}]}},
            "about": {"protocol": "1.3"}}

    def answer(request):
        given.append(request)
        return made

    order = []
    out = tool.write(tmp_path / "answers" / "a.json", answer=lambda r: order.append("answer") or answer(r),
                     publish=lambda: order.append("publish") or [])
    assert order == ["publish", "answer"]                    # the laws are published before the checker answers
    assert given == [json.loads(tool.REQUEST.read_text(encoding="utf-8"))]
    assert out.read_bytes() == json.dumps(made, indent=1, ensure_ascii=False).encode("utf-8")   # "≥" kept, LF only
    assert [p.name for p in out.parent.iterdir()] == ["a.json"]                                  # no temporary file left


@pytest.mark.parametrize("bad", [{"id": 1, "ok": False, "error": {"message": "boom"}}, {"id": 1, "ok": True}, None,
                                 {"id": 1, "ok": False, "result": {"view": {"items": []}}}])
def test_a_checker_error_is_never_written_and_the_earlier_file_stays(tmp_path, bad):
    out = tmp_path / "a.json"
    out.write_text("earlier", encoding="utf-8")
    with pytest.raises(tool.CheckerFailed):
        tool.write(out, answer=lambda request: bad, publish=lambda: [])
    assert out.read_text(encoding="utf-8") == "earlier"
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_a_law_that_cant_be_published_is_never_answered_without_and_the_earlier_file_stays(tmp_path):
    """A law with no current certificate gives no rules (rule_format.published.frozen): an answer made then would be
    the checker's without that law, so the tool stops before asking the checker (merge of #228, 2026-11-27)."""
    out = tmp_path / "a.json"
    out.write_text("earlier", encoding="utf-8")
    asked = []
    with pytest.raises(tool.CheckerFailed, match="isn't published"):
        tool.write(out, answer=lambda request: asked.append(request) or {"ok": True, "result": {}},
                   publish=lambda: ["new_york_state: a problem"])
    assert asked == [] and out.read_text(encoding="utf-8") == "earlier"


def test_by_default_it_publishes_with_the_same_ensure_the_tests_and_ci_use(monkeypatch, tmp_path):
    from rule_format import published
    monkeypatch.setattr(published, "ensure", lambda: ["stand-in law"])
    with pytest.raises(tool.CheckerFailed, match="stand-in law"):
        tool.write(tmp_path / "a.json", answer=lambda request: {"ok": True, "result": {}})


def _steps_running(job: dict, words: str) -> list[int]:
    return [n for n, step in enumerate(job.get("steps") or []) if words in str(step.get("run") or "")]


def test_every_ci_job_that_runs_the_csharp_tests_makes_the_answer_first_after_installing_the_checker():
    jobs = 0
    for workflow in sorted((REPO / ".github/workflows").glob("*.yml")):
        for name, job in (yaml.safe_load(workflow.read_text(encoding="utf-8")).get("jobs") or {}).items():
            tests = _steps_running(job, "dotnet test")
            if not tests:
                continue
            jobs += 1
            made = _steps_running(job, "python apps/revit_addin/tools/evals/make_apartment_answer.py")
            installed = _steps_running(job, "pip install")
            published = [n for n in _steps_running(job, "python -m rule_format publish")
                         if "--check" not in job["steps"][n]["run"]]
            assert made and installed and published, f"{workflow.name} {name}: make the apartment answer before dotnet test"
            assert installed[0] < published[0] < made[0] < tests[0],                 f"{workflow.name} {name}: install, publish the laws, then make the answer, then test"
            assert "working-directory" not in job["steps"][made[0]], "the tool runs from the repository folder"
    assert jobs >= 2                        # the Ubuntu leg (ci.yml) and the Windows leg (windows.yml)


def test_a_csharp_build_that_reads_the_answers_stops_without_the_apartments_and_says_how_to_make_it():
    projects = [p for p in sorted((REPO / "apps/revit_addin").rglob("*.csproj")) if "/bin/" not in p.as_posix()
                and "/obj/" not in p.as_posix()]
    readers = [p for p in projects
               if p.parent == REPO / "apps/revit_addin/tests/Gordium.Revit.Reading.Tests" or "answers/" in p.read_text(encoding="utf-8")]
    assert len(readers) >= 2                # the pane tests and the pane renders
    for p in readers:
        text = p.read_text(encoding="utf-8")
        at = text.index('<Target Name="GordiumApartmentAnswerMade" BeforeTargets="Build"')
        target = text[at:text.index("</Target>", at)]
        checked = target.split("!Exists('$(MSBuildThisFileDirectory)", 1)[1].split("')", 1)[0]
        assert (p.parent / checked).resolve() == (REPO / ANSWER).resolve(), p
        assert "<Error Text=" in target and "python apps/revit_addin/tools/evals/make_apartment_answer.py" in target
