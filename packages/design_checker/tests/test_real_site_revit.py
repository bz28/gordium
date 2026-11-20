"""The architects' 106 Ithaca Road model, drawn in Revit and read back by the Revit add-in (recorded once on the
Windows trial laptop: revit_reading.json beside the model), must be exactly what the Rhino reader reads from the same
model: the same description and the same verdicts (apps/revit_addin/tests/Gordium.Revit.Reading.Tests/real_site.py).
A real lot and a real house, not a hand-made scene: the two hosts must agree on it."""

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
SCRIPT = REPO / "apps/revit_addin/tests/Gordium.Revit.Reading.Tests/real_site.py"


def _real_site():
    spec = importlib.util.spec_from_file_location("real_site", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revit_reads_106_ithaca_road_exactly_as_rhino_does():
    rs = _real_site()
    assert rs.compare(str(SITE / "model.3dm"), str(SITE / "model_facts.yaml"), str(SITE / "revit_reading.json")) == []


def test_a_point_moved_a_hundredth_of_a_foot_is_caught(tmp_path):
    rs = _real_site()
    rec = json.loads((SITE / "revit_reading.json").read_text(encoding="utf-8"))
    rec["site"]["buildings"][0]["faces"][0]["points"][0][0] += 0.01
    moved = tmp_path / "moved.json"
    moved.write_text(json.dumps(rec), encoding="utf-8")
    problems = rs.compare(str(SITE / "model.3dm"), str(SITE / "model_facts.yaml"), str(moved))
    assert problems and "face" in problems[0]


def test_the_export_draws_what_the_rhino_reader_reads():
    rs = _real_site()
    export = rs.export(str(SITE / "model.3dm"), str(SITE / "model_facts.yaml"))
    assert len(export["lots"]) == 2 and export["picked"] in [lot["id"] for lot in export["lots"]]
    assert len(export["buildings"]) == 1 and len(export["buildings"][0]["faces"]) == 6
    assert len(export["lines"]) == 98        # the Map layer's 94 neighbours, 3 setback lines, the Site layer's loose line
    assert "lot_id" not in export["facts"]   # the add-in sets it to the picked property line's own id
