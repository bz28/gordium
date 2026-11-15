"""Print every conformance scene step as one JSON line: the facts to send and the hand-worked verdicts to expect.

Used by the C# tests (SceneCases.cs): the facts and the verdicts are worked out from the scene files by the
conformance suite's own functions (design_checker.conformance), never retyped. For a drawn scene the C# test reads
the site description itself from test_data/host_conformance/expected/ (`expected_file`); a description-only scene
(13, 14: `site:` in its YAML) has no such file, so its description is printed here (`site`).

    python scene_cases.py
"""

import json
import sys

from design_checker import conformance as c


def main() -> int:
    out = sys.stdout
    for name, scene in c.scenes().items():
        for step in c.steps(scene):
            case = {"scene": name, "step": step, "facts": c.facts(scene),
                    "verdicts": c.expected_verdicts(scene, step)}
            if c.has_model(scene):
                case["expected_file"] = c.expected_path(scene, step).relative_to(c.FOLDER).as_posix()
            else:
                case["site"] = c.expected_site(scene, step)
            out.write(json.dumps(case, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
