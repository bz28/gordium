"""Write a project's compliance report, or check the committed example reports are current.

    python -m project_report <project.yaml>    # writes <project>_report.xlsx next to the project file
    python -m project_report --check           # CI: every committed report matches a fresh build

A project file is any YAML under test_data/test_sites/ with a zone and measurements. A report is rewritten
only when its content changes.
"""

import argparse
import sys
from pathlib import Path

from openpyxl import load_workbook

from rule_export.workbook import contents
from rule_format.rulebook import REPO, load

from .report import build, output_path, tables


def projects() -> list[Path]:
    """The example projects: every test_data/test_sites/**/*.yaml with a zone. Each must have its report
    committed next to it, so --check fails on a missing report rather than skipping it."""
    return sorted(p for p in (REPO / "test_data/test_sites").rglob("*.yaml")
                  if isinstance(data := load(p), dict) and "zone" in data)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m project_report")
    parser.add_argument("project", nargs="?", type=Path, help="a project file (YAML)")
    parser.add_argument("--check", action="store_true", help="compare committed reports with fresh builds")
    args = parser.parse_args(argv)
    if args.check == bool(args.project):
        parser.error("give a project file, or --check")
    failed = 0
    for project in projects() if args.check else [args.project.resolve()]:
        path = output_path(project)
        shown = path.relative_to(REPO) if path.is_relative_to(REPO) else path
        try:
            fresh = build(tables(project))
        except ValueError as e:                  # a malformed project file: say what's wrong, no traceback
            print(f"✗ {e}")
            failed += 1
            continue
        same = path.exists() and contents(load_workbook(path)) == contents(fresh)
        if args.check:
            why = "" if same else ": differs from a fresh build" if path.exists() else ": missing (run the report)"
            print(f"{'✓' if same else '✗'} {shown}{why}")
            failed += not same
        elif not same:
            fresh.save(path)
            print(f"wrote {shown}")
        else:
            print(f"unchanged {shown}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
