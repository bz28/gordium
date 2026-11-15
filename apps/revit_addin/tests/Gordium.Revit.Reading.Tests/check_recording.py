"""Check one recording of a scene by the conformance suite's own rules (design_checker.conformance.recording_problems:
the description matches the expected one, and check_site gives exactly the scene's hand-worked verdicts). Prints
every problem as a JSON list: [] when it passes.

    python check_recording.py <recording.json>
"""

import json
import sys
from pathlib import Path

from design_checker import conformance as c
from design_checker import site_json


def main(path: str) -> int:
    rec = site_json.loads(Path(path).read_text(encoding="utf-8"))
    sys.stdout.write(json.dumps(c.recording_problems(rec["host"], rec["scene"], rec, c.scenes())) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
