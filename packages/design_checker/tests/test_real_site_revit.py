"""The architects' 106 Ithaca Road model, drawn in Revit and read back by the Revit add-in (recorded once on the
Windows trial laptop: revit_reading.json beside the model), must be exactly what the Rhino reader reads from the same
model: the same description and the same verdicts (apps/revit_addin/tests/Gordium.Revit.Reading.Tests/real_site.py).
A real lot and a real house, not a hand-made scene: the two hosts must agree on it."""

import importlib.util

import pytest
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


def _tiny(tmp_path, layers, add):
    """A small .3dm in feet with these layers, `add(model, layer_index)` putting objects on it, and plain facts."""
    import rhino3dm as r
    model = r.File3dm()
    model.Settings.ModelUnitSystem = r.UnitSystem.Feet
    for name in layers:
        layer = r.Layer()
        layer.Name = name
        model.Layers.Add(layer)
    add(model, {layer.FullPath: i for i, layer in enumerate(model.Layers)})
    path = tmp_path / "tiny.3dm"
    model.Write(str(path), 8)
    facts = tmp_path / "facts.yaml"
    facts.write_text("lot_facts:\n  zone: R-1b\n", encoding="utf-8")
    return str(path), str(facts)


def _attrs(index, floor=None):
    import rhino3dm as r
    a = r.ObjectAttributes()
    a.LayerIndex = index
    if floor is not None:
        a.SetUserString("gordium:floor", floor)
    return a


def _square(z=0.0):
    import rhino3dm as r
    return r.Polyline([r.Point3d(*p, z) for p in ((0, 0), (60, 0), (60, 120), (0, 120), (0, 0))]).ToPolylineCurve()


def test_a_closed_outline_on_a_site_sublayer_is_a_lot_as_the_reader_reads_it(tmp_path):
    # review round 2: export took only "Site" itself; the reader takes its sublayers too
    rs = _real_site()
    path, facts = _tiny(tmp_path, ["Site"], lambda m, i: None)
    import rhino3dm as r
    model = r.File3dm.Read(path)
    parent = model.Layers[0].Id
    sub = r.Layer()
    sub.Name = "Other"
    sub.ParentLayerId = parent
    model.Layers.Add(sub)
    model.Objects.AddCurve(_square(), _attrs(0))
    model.Objects.AddCurve(_square(), _attrs(1))
    model.Write(path, 8)
    assert [l.FullPath for l in r.File3dm.Read(path).Layers] == ["Site", "Site::Other"]
    assert len(rs.export(path, facts)["lots"]) == 2


def test_a_block_definitions_parts_are_not_drawn(tmp_path):
    # review round 3: an unplaced block's Site outline became a second lot; the reader reads only what is placed
    import rhino3dm as r
    rs = _real_site()

    def add(m, i):
        m.Objects.AddCurve(_square(), _attrs(i["Site"]))
        m.InstanceDefinitions.Add("blk", "", "", "", r.Point3d(0, 0, 0), (_square(),), (_attrs(i["Site"]),))
    path, facts = _tiny(tmp_path, ["Site"], add)
    export = rs.export(path, facts)
    assert len(export["lots"]) == 1 and export["lines"] == []


def test_a_lot_is_named_as_the_reader_names_it(tmp_path):
    # review round 3: a lot carrying gordium:id was drawn under its raw object id, so the picked lot never matched
    rs = _real_site()
    lot = _attrs(0)
    lot.SetUserString("gordium:id", "orig-lot")
    path, facts = _tiny(tmp_path, ["Site"], lambda m, i: m.Objects.AddCurve(_square(), lot))
    Path(facts).write_text("lot_facts:\n  zone: R-1b\n  lot_id: orig-lot\n", encoding="utf-8")
    export = rs.export(path, facts)
    assert [lot["id"] for lot in export["lots"]] == ["orig-lot"] and export["picked"] == "orig-lot"


def test_a_picked_lot_not_drawn_is_refused(tmp_path):
    rs = _real_site()
    path, facts = _tiny(tmp_path, ["Site"], lambda m, i: m.Objects.AddCurve(_square(), _attrs(i["Site"])))
    Path(facts).write_text("lot_facts:\n  zone: R-1b\n  lot_id: not-there\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="isn't one of the lots drawn"):
        rs.export(path, facts)


def test_a_block_on_the_building_layer_is_refused(tmp_path):
    # review round 4: the reader sends a placed block on Building as "a block" with no faces and not_a_solid; the
    # export passed it on, and Revit failed later with an unrelated-looking error
    import rhino3dm as r
    rs = _real_site()

    def add(m, i):
        m.Objects.AddCurve(_square(), _attrs(i["Site"]))
        outline = r.Polyline([r.Point3d(*q, 0) for q in ((15, 30), (45, 30), (45, 80), (15, 80), (15, 30))]).ToPolylineCurve()
        box = r.Extrusion.Create(outline, 10, True).ToBrep(True)
        index = m.InstanceDefinitions.Add("house", "", "", "", r.Point3d(0, 0, 0), (box,), (_attrs(i["Building"]),))
        m.Objects.Add(r.InstanceReference(m.InstanceDefinitions.FindIndex(index).Id, r.Transform.Identity()),
                      _attrs(i["Building"]))
    path, facts = _tiny(tmp_path, ["Site", "Building"], add)
    with pytest.raises(SystemExit, match="read whole"):
        rs.export(path, facts)


def test_a_marked_floor_block_is_refused(tmp_path):
    # review round 2: a floor mark was dropped, so Revit would send floor null where Rhino sends the height
    import rhino3dm as r
    rs = _real_site()
    outline = r.Polyline([r.Point3d(*q, 0) for q in ((15, 30), (45, 30), (45, 80), (15, 80), (15, 30))]).ToPolylineCurve()
    box = r.Extrusion.Create(outline, 10, True).ToBrep(True)
    path, facts = _tiny(tmp_path, ["Site", "Building"],
                        lambda m, i: (m.Objects.AddCurve(_square(), _attrs(i["Site"])),
                                      m.Objects.AddBrep(box, _attrs(i["Building"], "1;10"))))
    with pytest.raises(SystemExit, match="floor block"):
        rs.export(path, facts)


@pytest.mark.parametrize("change, words", [
    (lambda d: d.update(left_out=[{"id": "x"}]), "left_out"),
    (lambda d: d.update(unsent=[{"id": "x"}]), "unsent"),
    (lambda d: d.update(grade={"source": "spot", "points": [[0, 0, 0]]}), "spot grades"),
    (lambda d: d["buildings"][0]["faces"][0].update(holes=[[[1, 1, 0], [2, 1, 0], [2, 2, 0]]]), "holes"),
    (lambda d: d["buildings"][0].update(problems=[{"code": "open_solid", "args": {}}]), "read whole"),
    (lambda d: d["buildings"][0].update(faces=[]), "read whole"),
])
def test_every_refusal_holds(monkeypatch, change, words):
    # review round 2: only the curved-lot refusal was pinned; each of these could be undone with every test passing
    rs = _real_site()
    real = rs.cr.describe_file

    def describe(path, facts):
        doc = real(path, facts)
        change(doc)
        return doc
    monkeypatch.setattr(rs.cr, "describe_file", describe)
    with pytest.raises(SystemExit, match=words):
        rs.export(str(SITE / "model.3dm"), str(SITE / "model_facts.yaml"))


def test_an_object_that_isnt_a_curve_off_the_building_layer_is_refused(tmp_path):
    import rhino3dm as r
    rs = _real_site()
    path, facts = _tiny(tmp_path, ["Site", "Default"],
                        lambda m, i: (m.Objects.AddCurve(_square(), _attrs(i["Site"])),
                                      m.Objects.AddPoint(r.Point3d(5, 5, 0), _attrs(i["Default"]))))
    with pytest.raises(SystemExit, match="Point"):
        rs.export(path, facts)


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
