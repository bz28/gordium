"""Validate every rule file in the repo, or find where a quote is.

    python -m rule_format          # exit code 1 if anything has problems
    python -m rule_format cite new_york/ithaca_city zoning_charts_2026-04.pdf 3 "Height in feet 35 ft"
                                   # prints the lines to cite: lines: [31, 31]

For each jurisdiction: its source documents (fingerprints, extracted text), then
every rule file in 5_zoning_rules/ and in its test_data/answer_keys/ folder.
"""

import argparse
import sys
from pathlib import Path

import yaml

from .rulebook import REPO, TERM_SCHEMAS, Context, load, locate, not_quotable, validate, validate_terms


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
        for schema in TERM_SCHEMAS:
            path = jurisdiction / "4_term_definitions" / f"{schema}.yaml"
            if path.exists():
                try:
                    problems = validate_terms(load(path), ctx, schema)
                except Exception as e:
                    problems = [f"validator error ({type(e).__name__}: {e})"]
                checked += 1
                print(f"{'✗' if problems else '✓'} {path.relative_to(REPO)}")
                for problem in problems:
                    print(f"    {problem}")
                failed += bool(problems)
        files = sorted(p for folder in (jurisdiction / "5_zoning_rules", REPO / "test_data/answer_keys" / place)
                       for p in folder.rglob("*") if p.suffix in (".yaml", ".yml") and p.is_file())
        for path in files:
            checked += 1
            try:
                book = load(path)
                problems = validate(book, ctx)
                if isinstance(book, dict) and book.get("district") != path.stem:
                    problems.append(f"district {book.get('district')!r} doesn't match the file name {path.stem!r}")
            except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
                problems = [f"can't read file ({type(e).__name__}: {e})"]
            except Exception as e:  # report and keep going: one broken file mustn't hide the rest
                problems = [f"validator error ({type(e).__name__}: {e})"]
            print(f"{'✗' if problems else '✓'} {path.relative_to(REPO)}")
            for problem in problems:
                print(f"    {problem}")
            failed += bool(problems)
    print(f"{checked} files checked, {failed} with problems")
    return 1 if failed else 0


def cite(argv: list[str]) -> int:
    """Print the `lines` to cite for a quote, so drafters never count lines by hand."""
    parser = argparse.ArgumentParser(prog="python -m rule_format cite")
    for name in ("place", "file", "page", "quote"):
        parser.add_argument(name, type=int if name == "page" else str)
    args = parser.parse_args(argv)
    place = REPO / "regulations/jurisdictions" / args.place
    if not (place / "1_source_documents/sources.yaml").exists():
        print(f"no jurisdiction {args.place!r} (expected regulations/jurisdictions/<state>/<place>)")
        return 1
    ctx = Context.for_jurisdiction(place)
    if args.file not in ctx.sources:
        print(f"{args.file} is not in sources.yaml")
        return 1
    if reason := not_quotable(ctx.sources[args.file]):
        print(f"{args.file} {reason}")
        return 1
    if args.file not in ctx.pages:
        reasons = ctx.file_problems.get(args.file, [])
        if not (place / "2_extracted_text" / f"{Path(args.file).stem}.jsonl").exists():
            reasons = [*reasons, "no extracted text"]
        print("\n".join(f"{args.file}: {r}" for r in reasons))
        return 1
    if args.page not in ctx.pages[args.file]:
        print(f"{args.file} has no page {args.page}")
        return 1
    found = locate(args.quote, ctx.pages[args.file][args.page])
    for first, last in found:
        print(f"lines: [{first}, {last}]")
    if len(found) != 1:
        print("not found on this page" if not found else "appears more than once: quote more words so it's unique")
    return 0 if len(found) == 1 else 1


if __name__ == "__main__":
    sys.exit(cite(sys.argv[2:]) if sys.argv[1:2] == ["cite"] else main())
