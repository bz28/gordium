"""python -m ifc_reading <model.ifc> [<out.yaml>]: read an IFC model into Gordium's interior description.
python -m ifc_reading --check: every committed description in test_data/ifc_models matches a fresh read.

Without <out.yaml> it prints the description. The measures: python -m model_measurement.interior <out.yaml>.
"""

import sys
from pathlib import Path

import yaml

from ifc_reading import read
from rule_format.rulebook import utf8_console

MODELS = Path(__file__).resolve().parents[3] / "test_data" / "ifc_models"


def dump(description) -> str:
    return yaml.safe_dump(description, sort_keys=False, allow_unicode=True, width=120)


def check() -> int:
    stale = 0
    models = sorted(MODELS.glob("*/*.ifc"))
    if not models:                      # review round 6: a check that finds nothing must not pass
        print(f"no models found in {MODELS}: nothing was checked")
        return 1
    for ifc in models:
        want = ifc.with_name(ifc.stem + "_interior.yaml")
        got = dump(read(ifc))
        if not want.exists() or want.read_text(encoding="utf-8") != got:
            print(f"stale: {want.relative_to(MODELS.parents[0])} (run: python -m ifc_reading {ifc} {want})")
            stale += 1
    print("all current" if not stale else f"{stale} stale")
    return 1 if stale else 0


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--check"]:
        return check()
    if len(args) not in (1, 2):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    text = dump(read(args[0]))
    if len(args) == 2:
        Path(args[1]).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    utf8_console()                     # a room named Küche or "m²" can't crash a Windows console or pipe
    sys.exit(main())
