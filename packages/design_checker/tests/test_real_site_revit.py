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


def test_a_model_the_export_cant_draw_faithfully_is_refused(tmp_path):
    # review round 1: a curved lot outline became one point; now refused, naming it, never drawn differently
    import pytest
    import rhino3dm as r
    rs = _real_site()
    model = r.File3dm()
    model.Settings.ModelUnitSystem = r.UnitSystem.Feet
    for name in ("Site", "Building"):
        layer = r.Layer()
        layer.Name = name
        model.Layers.Add(layer)
    site = r.ObjectAttributes()
    site.LayerIndex = 0
    model.Objects.AddCircle(r.Circle(r.Point3d(30, 60, 0), 25), site)
    path = tmp_path / "round_lot.3dm"
    model.Write(str(path), 8)
    facts = tmp_path / "facts.yaml"
    facts.write_text("lot_facts:\n  zone: R-1b\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="isn.t drawn yet"):
        rs.export(str(path), str(facts))


def test_record_writes_what_compare_reads_with_where_it_came_from(tmp_path):
    rs = _real_site()
    raw = json.loads((SITE / "revit_reading.json").read_text(encoding="utf-8"))
    out = tmp_path / "raw.json"
    out.write_text(json.dumps({"site": raw["site"], "ids": raw["ids"]}), encoding="utf-8")
    rec = rs.record(str(out), "model.3dm", "2026-11-19", "Autodesk Revit 2027.4, Gordium add-in (trial)")
    assert {k: rec[k] for k in ("host", "model", "ids", "site")} == {k: raw[k] for k in ("host", "model", "ids", "site")}
    assert rec["recorded"] == raw["recorded"]


def test_the_export_draws_what_the_rhino_reader_reads():
    rs = _real_site()
    export = rs.export(str(SITE / "model.3dm"), str(SITE / "model_facts.yaml"))
    assert len(export["lots"]) == 2 and export["picked"] in [lot["id"] for lot in export["lots"]]
    assert len(export["buildings"]) == 1 and len(export["buildings"][0]["faces"]) == 6
    assert len(export["lines"]) == 98        # the Map layer's 94 neighbours, 3 setback lines, the Site layer's loose line
    assert "lot_id" not in export["facts"]   # the add-in sets it to the picked property line's own id
