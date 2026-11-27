"""Makes the Revit pane's four-unit apartment answer, the file the add-in's C# tests and the pane renders read
(apps/revit_addin/tests/Gordium.Revit.Reading.Tests/answers/four_unit_apartment_check_answer.json).

It is the checker's own answer to Ben's 2026-11-23 trial request for that building
(test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json), so the pane is tested
on what an architect would see today. It is made, never committed (.gitignore): almost every rule change changed it,
and a committed copy made every waiting pull request conflict with each merge. CI makes it before `dotnet test`
(.github/workflows/ci.yml and windows.yml, the Revit client jobs); on a laptop, run this once before the C# tests and
again after pulling or changing rules (apps/revit_addin/README.md):

    python apps/revit_addin/tools/evals/make_apartment_answer.py

A checker error is never written as the answer: the tool stops with the error and leaves any earlier file as it was.
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
    """The checker answered the request with an error, not a result."""


def text(request: dict, answer=None) -> str:
    """The answer file's text: the checker's answer as the worker writes it (indent 1, UTF-8 kept)."""
    if answer is None:
        from design_checker.__main__ import answer
    got = answer(request)
    if not isinstance(got, dict) or got.get("ok") is not True or not isinstance(got.get("result"), dict):
        raise CheckerFailed(f"the checker gave no result for {REQUEST.name}: {json.dumps(got, ensure_ascii=False)[:2000]}")
    return json.dumps(got, indent=1, ensure_ascii=False)


def write(out: Path = OUT, request: Path = REQUEST, answer=None) -> Path:
    """Writes the answer to `out` whole or not at all (a temporary file, then one replace), so a C# test never reads
    half a file and a failed run keeps the earlier one."""
    made = text(json.loads(request.read_text(encoding="utf-8")), answer)
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
