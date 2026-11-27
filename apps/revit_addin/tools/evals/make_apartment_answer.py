"""Makes the Revit pane's four-unit apartment answer, the file the add-in's C# tests and the pane renders read
(apps/revit_addin/tests/Gordium.Revit.Reading.Tests/answers/four_unit_apartment_check_answer.json).

It is the checker's own answer to Ben's 2026-11-23 trial request for that building
(test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json), so the pane is tested
on what an architect would see today. It is made, never committed (.gitignore): almost every rule change changed it,
and a committed copy made every waiting pull request conflict with each merge. CI makes it before `dotnet test`
(.github/workflows/ci.yml and windows.yml, the Revit client jobs); on a laptop, run this once before the C# tests and
again after pulling or changing rules (apps/revit_addin/README.md):

    python apps/revit_addin/tools/evals/make_apartment_answer.py

Each state law is published first (`python -m rule_format publish`'s ensure: a missing or stale certificate made
again), since a law with no current certificate gives no rules (rule_format/published.py, frozen) and the answer
would be the checker's without them. A law that can't be published, or a checker error, is never written as the
answer: the tool stops with why and leaves any earlier file as it was.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
REQUEST = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json"
OUT = REPO / "apps/revit_addin/tests/Gordium.Revit.Reading.Tests/answers/four_unit_apartment_check_answer.json"


class CheckerFailed(RuntimeError):
    """The checker answered the request with an error, not a result, or a state law couldn't be published."""


def own_checkout() -> None:
    """Refuses a checker of another checkout: Python imports Gordium from wherever it is installed (a worktree run with
    the main clone's venv and no PYTHONPATH imports the main clone's), which would publish that checkout's laws and
    write its answer here, the rules of another branch, with nothing saying so (merge review of PR #266)."""
    import design_checker
    import rule_format.rulebook
    for name, where in (("rule_format", rule_format.rulebook.REPO), ("design_checker", design_checker.__file__)):
        if not Path(where).resolve().is_relative_to(REPO):
            raise CheckerFailed(f"{name} is imported from {Path(where).resolve()}, not from this checkout ({REPO}): "
                                "set PYTHONPATH to this checkout's packages, or pip install -e it")


def text(request: dict, answer=None, publish=None) -> str:
    """The answer file's text: the checker's answer as the worker writes it (indent 1, UTF-8 kept), after every state
    law is published (`publish`: what couldn't be, as rule_format.published.ensure gives it). The checker and the
    publisher, when not given, are this checkout's (own_checkout)."""
    if publish is None or answer is None:
        own_checkout()
    if publish is None:
        from rule_format.published import ensure as publish
    unpublished = publish()
    if unpublished:
        raise CheckerFailed("a state law isn't published, so the checker would answer without its rules: "
                            + "; ".join(unpublished))
    if answer is None:
        from design_checker.__main__ import answer
    got = answer(request)
    if not isinstance(got, dict) or got.get("ok") is not True or not isinstance(got.get("result"), dict):
        raise CheckerFailed(f"the checker gave no result for {REQUEST.name}: {json.dumps(got, ensure_ascii=False)[:2000]}")
    return json.dumps(got, indent=1, ensure_ascii=False)


def write(out: Path = OUT, request: Path = REQUEST, answer=None, publish=None) -> Path:
    """Writes the answer to `out` whole or not at all (a temporary file, then one replace), so a C# test never reads
    half a file and a failed run keeps the earlier one."""
    made = text(json.loads(request.read_text(encoding="utf-8")), answer, publish)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(made, encoding="utf-8", newline="\n")
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out


def main() -> int:
    try:
        path = write()
    except CheckerFailed as e:
        print(e, file=sys.stderr)
        return 1
    print(f"wrote {path.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
