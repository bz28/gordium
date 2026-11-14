"""python -m model_measurement.interior <description.yaml>: print each part's measures (inches, sq ft) as YAML."""

import sys

import yaml

from model_measurement.interior import measure_file


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    print(yaml.safe_dump(measure_file(args[0]), sort_keys=False, allow_unicode=True, width=120), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
