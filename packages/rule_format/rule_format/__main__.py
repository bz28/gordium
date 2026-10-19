"""Validate every rule file in the repo.

    python -m rule_format          # exit code 1 if any rule file has problems

Checks each jurisdiction's 5_zoning_rules/ and its test_data/answer_keys/ files.
"""

import sys

from .rulebook import REPO, Context, load, validate


def main() -> int:
    failed = checked = 0
    for jurisdiction in sorted((REPO / "regulations/jurisdictions").glob("*/*")):
        ctx = Context.for_jurisdiction(jurisdiction)
        place = jurisdiction.relative_to(REPO / "regulations/jurisdictions")
        files = sorted([*(jurisdiction / "5_zoning_rules").glob("*.yaml"),
                        *(REPO / "test_data/answer_keys" / place).glob("*.yaml")])
        for problem in ctx.problems if not files else []:
            print(f"✗ {place}: {problem}")
            failed += 1
        for path in files:
            checked += 1
            problems = validate(load(path), ctx)
            print(f"{'✗' if problems else '✓'} {path.relative_to(REPO)}")
            for problem in problems:
                print(f"    {problem}")
            failed += bool(problems)
    print(f"{checked} rule files checked, {failed} with problems")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
