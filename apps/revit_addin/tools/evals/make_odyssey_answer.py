"""The Children's Odyssey day care's check answer (19 Libby St, Portland ME), for the Revit add-in's detail tests
(apps/revit_addin/tests/Gordium.Revit.Reading.Tests/DetailTests.cs): the worker's own egress code
(design_checker.egress.check and add_to_view, the code check_site runs) on the interior the add-in read from the
marked model, with the Maine state law (IBC 2009, NFPA 101 2012) and the building's facts from the eval's hand check
(make_eval_comparison.SHEET_VALUES). Only the answer is written (numbers and words the worker made), never by hand.

Maine has no place in the repo yet (no zoning for Portland), so check_site can't be asked for it: the law is loaded
here as egress.laws loads an inherited one, and the answer has the egress section alone (zoning's empty section is
dropped). The route parts (story, space, corridor) are measured by the route code the eval runs
(model_measurement.routes.measure, as make_eval_comparison.py), joined to the interior's own parts: check_site's
interior measuring doesn't join them yet. The routes' door parts (New York's Building Code section group 6a, every
door with its stated clear opening) are never joined: Maine's means of egress door rules read what its architect
marks (swing, latch, panic hardware), which no door part measures, so they stay not read, as the answer records. Everything else is the worker's.

    python make_odyssey_answer.py <interior description .json> <out .json>
"""

import contextlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
for p in ("packages/design_checker", "packages/model_measurement", "packages/rule_format",
          "packages/model_measurement/tests"):
    sys.path.insert(0, str(REPO / p))

from design_checker import egress, protocol  # noqa: E402
from rule_format.place import stand_in  # noqa: E402
from rule_format.rulebook import Context  # noqa: E402

import make_eval_comparison as evalc  # noqa: E402

MAINE = REPO / "regulations/jurisdictions/maine/maine_state"


# a place that inherits only Maine's state law: the real Place (rule_format.place.stand_in). egress.laws reads its
# name, folder and inherited law, which a stand-in has; settings it lacks (time zone, boundary...) raise, and
# test_panel_data's un-skipped test of this script catches a new read in CI
PLACE = stand_in(MAINE, "Portland, ME (the eval)", ["maine/maine_state"])


ROUTE_KINDS = ("story", "space", "corridor")      # the answer's route parts (never the door parts: above)


@contextlib.contextmanager
def as_the_eval():
    """egress as the eval runs it: the place is PLACE, Maine's law may be checked alone, and the interior's parts are
    joined by the route parts the eval measures (its story, space and corridor)."""
    from model_measurement.routes import measure as measure_routes
    real = egress.place_of, egress.refuse_state_alone, egress.measure_interior
    inside = real[2]

    def both(description):
        measured = inside(description)
        for kind, parts in measure_routes(description)["parts"].items():
            if kind in ROUTE_KINDS and measured["parts"].get(kind) is None:
                measured["parts"][kind] = parts
        return measured
    egress.place_of, egress.refuse_state_alone, egress.measure_interior = (lambda folder: PLACE), (lambda j: None), both
    try:
        yield
    finally:
        egress.place_of, egress.refuse_state_alone, egress.measure_interior = real


def answer(interior: dict) -> dict:
    with as_the_eval():
        found = egress.laws(MAINE)
        got = egress.check(found, interior, dict(evalc.SHEET_VALUES), Context.for_jurisdiction(MAINE).allowed())
    view = {"items": []}
    egress.add_to_view(view, got, found["place"])
    view["sections"] = [s for s in view["sections"] if s["key"] != "zoning"]
    return {"id": 1, "ok": True, "result": {"view": view, "report_error": None}, "about": protocol.about()}


def main(src: Path, out: Path) -> dict:
    from rule_format import published
    if notes := published.ensure():        # Maine's certificate current, or no answer written (its rows would be
        raise SystemExit("not written: " + "; ".join(notes))   # needs review: the frozen law refused)
    got = answer(json.loads(src.read_text(encoding="utf-8")))
    out.write_text(json.dumps(got, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return got


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
