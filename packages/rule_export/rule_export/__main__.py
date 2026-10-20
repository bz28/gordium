"""Write each jurisdiction's rules workbook, or check the committed one is current.

    python -m rule_export            # writes regulations/jurisdictions/<state>/<place>/<place>_rules.xlsx
    python -m rule_export --check    # exit 1 if a committed workbook differs from a fresh build (CI)

A workbook is rewritten only when its content changes, so regenerating doesn't churn the file.
"""

import argparse
import sys

from openpyxl import load_workbook

from rule_format.rulebook import REPO

from .workbook import build, contents, output_path, tables


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m rule_export")
    parser.add_argument("--check", action="store_true", help="compare with a fresh build; write nothing")
    args = parser.parse_args(argv)
    failed = 0
    for j in sorted(p for p in (REPO / "regulations/jurisdictions").glob("*/*") if (p / "5_zoning_rules").is_dir()):
        path = output_path(j)
        shown = path.relative_to(REPO) if path.is_relative_to(REPO) else path
        fresh = build(tables(j))
        same = path.exists() and contents(load_workbook(path)) == contents(fresh)
        if args.check:
            print(f"{'✓' if same else '✗'} {shown}" + ("" if same else ": differs from a fresh build"))
            failed += not same
        elif not same:
            fresh.save(path)
            print(f"wrote {shown}")
        else:
            print(f"unchanged {shown}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
