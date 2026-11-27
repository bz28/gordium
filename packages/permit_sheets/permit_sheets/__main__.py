"""Make a house's egress permit sheets, or check the golden ones are current.

    python -m permit_sheets <house.yaml> --model <model.3dm> --facts <facts.yaml> --project <project.yaml> --out <folder>
    python -m permit_sheets <house.yaml> --site <site.json> --facts <facts.yaml> --project <project.yaml> --out <folder>
    python -m permit_sheets --check      # every golden matches a fresh build
    python -m permit_sheets --write      # record the goldens again (only when an answer should change)

The command checks the design itself (design_checker, exactly as the plugin does: the model or site description, its
lot facts and the interior description), then writes the sheets from that answer: a check result from elsewhere
can't say which rules decided it. <project.yaml> gives the title block: `title`, `address` (optional) and `date`
(YYYY-MM-DD: the sheets, and the check's day, never read the clock).
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from model_measurement.project import load_facts
from rule_format import published
from rule_format.rulebook import utf8_console

from . import goldens
from .build import files, project_problems, workbook
from .source import checked
from .words import Refused

SHEET = re.compile(r"^(G|LS|A)-\d{3}\.svg$")          # the sheet files this command writes, and only those
OURS = {"permit_sheets.pdf", "code_analysis.csv", "escape_window_schedule.csv", "permit_sheets.xlsx"}


def make(house_path: Path, facts_path: Path, project_path: Path, out: Path, model: Path | None = None,
         site: Path | None = None) -> list[Path]:
    """Check the design and write its sheets into `out`; the files written."""
    from design_checker.check import check, check_description
    project = yaml.safe_load(project_path.read_text(encoding="utf-8"))
    problems = project_problems(project)
    if problems:
        raise Refused(f"{project_path}: " + "; ".join(problems))
    house = yaml.safe_load(house_path.read_text(encoding="utf-8"))
    facts = load_facts(facts_path)
    day = project["date"]
    if model is not None:
        run = lambda: check(model, facts, today=day, interior=house)                       # noqa: E731
    else:
        doc = json.loads(site.read_text(encoding="utf-8"))
        run = lambda: check_description(doc, facts, today=day, interior=house)             # noqa: E731
    got = checked(run, house)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():           # an earlier set's pages never stay beside this one (fewer pages this time)
        if old.is_file() and (SHEET.match(old.name) or old.name in OURS):
            old.unlink()
    written = []
    for name, data in files(got, project).items():
        (out / name).write_bytes(data)
        written.append(out / name)
    workbook(got, project).save(out / "permit_sheets.xlsx")
    return written + [out / "permit_sheets.xlsx"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m permit_sheets")
    parser.add_argument("house", nargs="?", type=Path, help="the interior description (gordium.interior/1)")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--model", type=Path, help="the Rhino model (.3dm)")
    where.add_argument("--site", type=Path, help="a site description (gordium.site/1 JSON)")
    parser.add_argument("--facts", type=Path, help="the lot facts file")
    parser.add_argument("--project", type=Path, help="the title block: title, address, date")
    parser.add_argument("--out", type=Path, help="the folder to write the sheets into")
    parser.add_argument("--check", action="store_true", help="compare the golden sheets with fresh builds")
    parser.add_argument("--write", action="store_true", help="record the golden sheets again")
    args = parser.parse_args(argv)
    # a missing law certificate is published first (rule_format/published.py); before writing goldens a stale one too,
    # since a check reads no stale law (every row of it needs review) and those rows would be written as the goldens.
    # A law that can't be published stops a write: its rows would be written as needs review
    notes = published.ensure(missing_only=not args.write)
    for note in notes:
        print(f"– {note}")
    if args.write and notes:
        print("✗ not written: a law can't be published (above), so its rows would be written as needs review")
        return 1
    if args.check or args.write:
        if args.house or args.check == args.write:
            parser.error("--check or --write, alone")
        failed = 0
        for name in goldens.names():
            try:
                if args.write:
                    goldens.write(name)
                    print(f"wrote {name}")
                    continue
                diffs = goldens.differences(name)
            except Refused as e:
                diffs = [f"{name}: refused: {e}"]
            print(f"{'✗' if diffs else '✓'} {name}" + "".join(f"\n    differs: {d}" for d in diffs))
            failed += bool(diffs)
        return 1 if failed else 0
    if not (args.house and (args.model or args.site) and args.facts and args.project and args.out):
        parser.error("give the house, --model or --site, --facts, --project and --out")
    try:
        written = make(args.house, args.facts, args.project, args.out, args.model, args.site)
    except (Refused, ValueError) as e:
        print(f"✗ {e}")
        return 1
    for p in written:
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    utf8_console()
    sys.exit(main(sys.argv[1:]))
