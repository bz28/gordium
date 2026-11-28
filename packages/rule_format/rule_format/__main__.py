"""Validate every rule file in the repo, or find where a quote is.

    python -m rule_format          # exit code 1 if anything has problems
    python -m rule_format place --write   # writes the plugin's copy of its place's settings (place.py)
    python -m rule_format cite new_york/ithaca_city zoning_charts_2026-04.pdf 3 "Height in feet 35 ft"
                                   # prints the lines to cite: lines: [31, 31]
    python -m rule_format publish [folder ...]      # freezes each rulebook's checks (rule_format/published.py)
    python -m rule_format publish --check [folder]  # a fresh compile must give the same certificate, byte for byte

For each place and each state law folder (a state's own law, e.g. New York's Residential Code, with a state.yaml
instead of a jurisdiction.yaml; its text_verification.yaml too): its settings file (jurisdiction.yaml, read by the registry in place.py), its source documents (fingerprints, extracted text), its definitions and
uses (4_term_definitions/), its section labels (3_section_labels/<document>.yaml, against the pieces in
2_extracted_text/<document>.sections.jsonl), then every rule file in 5_zoning_rules/ (a state folder: 5_building_code_rules/) and in its
test_data/answer_keys/ folder. Then that the plugin's copy of its place's settings (place.json) is current.
"""

import argparse
import sys
from pathlib import Path

from . import parts
from . import place as places
from .labels import load_pieces, validate_labels
from .rulebook import (PROPOSED_MEASURES, REPO, STATE_SETTINGS, Context, finding_conflicts, law_folders, load, locate,
                       needed_by_problems, not_quotable, research_entries, rulebook_file_problems, rulebook_paths,
                       rules_folder, term_file_problems, utf8_console)
from .state_law import VERIFICATION, state_settings_problems, verification_problems


def main() -> int:
    failed, checked = 0, 1
    shown = parts.PARTS_FILE.relative_to(parts.PARTS_FILE.parents[3])   # the code's own repository
    try:                                  # the part kinds per-part rules repeat over (parts.yaml)
        parts.load_registry()
        print(f"✓ {shown}")
    except (ValueError, OSError, AttributeError, TypeError) as e:
        failed = 1
        print(f"✗ {shown}: {e}")
    for jurisdiction in law_folders(REPO):
        place = jurisdiction.relative_to(REPO / "regulations/jurisdictions")
        state = (jurisdiction / STATE_SETTINGS).is_file()
        checked += 1
        try:
            ctx = Context.for_jurisdiction(jurisdiction)
        except Exception as e:  # report and keep going: one broken folder mustn't hide the rest
            print(f"✗ {place}: can't load sources ({type(e).__name__}: {e})")
            failed += 1
            continue
        if state:
            problems = state_settings_problems(jurisdiction, ctx)
            print(f"{'✗' if problems else '✓'} {place}/{STATE_SETTINGS}" + "".join(f"\n    {p}" for p in problems))
            failed += bool(problems)
        else:
            try:
                places.place(jurisdiction)
                print(f"✓ {place}/{places.SETTINGS}")
            except places.UnknownPlace as e:
                print(f"✗ {place}: {e}")
                failed += 1
        for problem in ctx.problems:
            print(f"✗ {place}: {problem}")
        failed += bool(ctx.problems)
        for path, problems in term_file_problems(jurisdiction, ctx).items():
            checked += 1
            print(f"{'✗' if problems else '✓'} {path.relative_to(REPO)}")
            for problem in problems:
                print(f"    {problem}")
            failed += bool(problems)
        for path in sorted((jurisdiction / "3_section_labels").glob("*.yaml")):
            checked += 1
            pieces_file = jurisdiction / "2_extracted_text" / f"{path.stem}.sections.jsonl"
            try:
                problems = (validate_labels(load(path), ctx, *load_pieces(pieces_file)) if pieces_file.exists()
                            else [f"no sections file {pieces_file.relative_to(REPO)} (set layout in sources.yaml)"])
            except Exception as e:  # report and keep going: one broken file mustn't hide the rest
                problems = [f"validator error ({type(e).__name__}: {e})"]
            print(f"{'✗' if problems else '✓'} {path.relative_to(REPO)}")
            for problem in problems:
                print(f"    {problem}")
            failed += bool(problems)
        files = [p for folder in (rules_folder(jurisdiction), REPO / "test_data/answer_keys" / place)
                 for p in rulebook_paths(folder)]
        for path in files:
            checked += 1
            problems = rulebook_file_problems(path, ctx)
            print(f"{'✗' if problems else '✓'} {path.relative_to(REPO)}")
            for problem in problems:
                print(f"    {problem}")
            failed += bool(problems)
        proposed = rules_folder(jurisdiction) / PROPOSED_MEASURES
        if proposed.exists():
            checked += 1
            problems = needed_by_problems(proposed, list(rulebook_paths(rules_folder(jurisdiction))))
            print(f"{'✗' if problems else '✓'} {proposed.relative_to(REPO)}" + "".join(f"\n    {p}" for p in problems))
            failed += bool(problems)
        if state:
            checked += 1
            try:
                problems, notes = verification_problems(jurisdiction, ctx)
            except Exception as e:  # report and keep going
                problems, notes = [f"validator error ({type(e).__name__}: {e})"], []
            print(f"{'✗' if problems else '✓'} {place}/{VERIFICATION}" + "".join(f"\n    {p}" for p in problems))
            failed += bool(problems)
            for note in notes:
                print(f"– {place}: {note}")
        for name, why in ctx.uncached.items():            # skipped here, never passed: said once per document
            count = sum(s.startswith(f"{name} ") for s in ctx.skipped)
            print(f"– {place}: {count} quotes of {name} not checked here: {why}")
        try:                                              # across files: a question is settled or open, not both
            conflicts = finding_conflicts(research_entries(jurisdiction))
        except Exception as e:  # report and keep going
            conflicts = [f"validator error ({type(e).__name__}: {e})"]
        for problem in conflicts:
            print(f"✗ {place}: {problem}")
        failed += bool(conflicts)
    checked += 1
    try:
        current = places.PLUGIN_FILE.is_file() and places.PLUGIN_FILE.read_text(encoding="utf-8") == places.plugin_file_text()
        why = "" if current else ": differs from a fresh build (python -m rule_format place --write)"
    except places.UnknownPlace as e:
        current, why = False, f": {e}"
    print(f"{'✓' if current else '✗'} {places.PLUGIN_FILE.relative_to(places.REPO)}{why}")
    failed += not current
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
    utf8_console()
    if sys.argv[1:] == ["place", "--write"]:
        places.PLUGIN_FILE.write_text(places.plugin_file_text(), encoding="utf-8")
        print(f"wrote {places.PLUGIN_FILE.relative_to(REPO)}")
        sys.exit(0)
    if sys.argv[1:2] == ["publish"]:                     # compile, then freeze: published.py
        from . import published
        sys.exit(published.main(sys.argv[2:]))
    sys.exit(cite(sys.argv[2:]) if sys.argv[1:2] == ["cite"] else main())
