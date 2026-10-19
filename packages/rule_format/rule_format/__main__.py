"""Validate every rule file in the repo.

    python -m rule_format          # exit code 1 if anything has problems

For each jurisdiction: its source documents (fingerprints, extracted text), then
every rule file in 5_zoning_rules/ and in its test_data/answer_keys/ folder.
"""

import sys

import yaml

from .rulebook import REPO, Context, load, validate


def main() -> int:
    failed = checked = 0
    for jurisdiction in sorted(p for p in (REPO / "regulations/jurisdictions").glob("*/*") if p.is_dir()):
        place = jurisdiction.relative_to(REPO / "regulations/jurisdictions")
        try:
            ctx = Context.for_jurisdiction(jurisdiction)
        except Exception as e:  # report and keep going: one broken folder mustn't hide the rest
            print(f"✗ {place}: can't load sources ({type(e).__name__}: {e})")
            failed += 1
            continue
        for problem in ctx.problems:
            print(f"✗ {place}: {problem}")
        failed += bool(ctx.problems)
        files = sorted(p for folder in (jurisdiction / "5_zoning_rules", REPO / "test_data/answer_keys" / place)
                       for p in folder.rglob("*") if p.suffix in (".yaml", ".yml") and p.is_file())
        for path in files:
            checked += 1
            try:
                problems = validate(load(path), ctx)
            except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
                problems = [f"can't read file ({type(e).__name__}: {e})"]
            print(f"{'✗' if problems else '✓'} {path.relative_to(REPO)}")
            for problem in problems:
                print(f"    {problem}")
            failed += bool(problems)
    print(f"{checked} rule files checked, {failed} with problems")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
