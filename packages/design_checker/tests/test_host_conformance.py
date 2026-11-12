"""The host conformance suite (design_checker/conformance.py; test_data/host_conformance/README.md): every scene's
description from the Rhino reference adapter, and every host's recording, matches the scene's expected description
and gives exactly its hand-worked verdicts through check_site. The guards below pin that the comparison can fail:
a host that sends fewer problems, drops a left-out object, moves a point, changes an id or gets a verdict wrong is
caught, never waved through."""

import copy
import json
import math
import types
import uuid

import pytest

from design_checker import conformance as c
from design_checker import conformance_rhino as cr
from design_checker import site_json

SCENES = c.scenes()
DRAWN = {n: s for n, s in SCENES.items() if c.has_model(s)}
STEPS = [(n, step) for n, s in SCENES.items() for step in c.steps(s)]


def _host_doc(name, step=c.STEPS[0]):
    s = SCENES[name]
    return (cr.describe(s, step), cr.ids(s)) if c.has_model(s) else (copy.deepcopy(s["site"]), {})


# ---- the suite passes, on real files ---------------------------------------------------------------------------

@pytest.mark.parametrize("name, step", STEPS)
def test_the_rhino_reference_adapter_conforms_on_every_scene(name, step):
    doc, ids = _host_doc(name, step)
    assert c.conformance(SCENES[name], doc, ids, step) == []


@pytest.mark.parametrize("name, step", STEPS)
def test_every_expected_description_is_a_valid_description_and_the_committed_file_is_current(name, step):
    scene = SCENES[name]
    want = c.expected_site(scene, step)
    site_json.validate(want)
    if c.has_model(scene):
        assert json.loads(c.expected_path(scene, step).read_text(encoding="utf-8")) == want, \
            "run python -m design_checker.conformance --write"


def test_no_expected_description_is_left_without_its_scene():
    made = {c.expected_path(s, step).name for s in DRAWN.values() for step in c.steps(s)}
    assert {p.name for p in c.EXPECTED.glob("*.json")} == made
    models = {cr.model_path(s, step).name for s in DRAWN.values() for step in c.steps(s)}
    assert {p.name for p in c.MODELS.glob("*.3dm")} == models


@pytest.mark.parametrize("name", sorted(DRAWN))
def test_each_committed_model_reads_as_a_freshly_built_one(name, tmp_path):
    """The .3dm files are written by conformance_rhino.build (and edited, for the step after the edit); a file
    written again reads the same, so the committed model is the scene and not an older drawing of it."""
    scene = DRAWN[name]
    fresh = tmp_path / f"{name}.3dm"
    cr.build(scene).Write(str(fresh), 8)
    facts = c.facts(scene)
    a, b = cr.describe_file(cr.model_path(scene), facts), cr.describe_file(fresh, facts)
    a["host"]["document"] = b["host"]["document"] = ""
    assert a == b
    if scene.get("then"):
        after = tmp_path / f"{name}.after.3dm"
        cr.edited(scene, fresh).Write(str(after), 8)
        a = cr.describe_file(cr.model_path(scene, c.STEPS[1]), facts)
        b = cr.describe_file(after, facts)
        a["host"]["document"] = b["host"]["document"] = ""
        assert a == b


def test_every_recording_passes_and_each_host_records_every_scene():
    recorded = c.recordings()
    assert set(recorded) >= {cr.HOST}, "the reference adapter's recordings exercise the hook on real data"
    bad = [p for host, by in recorded.items() for name, rec in by.items()
           for p in c.recording_problems(host, name, rec, SCENES)]
    assert bad == [] and c.coverage_problems(recorded, SCENES) == []


@pytest.mark.parametrize("name", sorted(DRAWN))
def test_the_reference_adapters_recordings_are_current(name):
    path = c.RECORDED / cr.HOST / f"{name}.json"
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(json.dumps(cr.record(DRAWN[name]))), \
        "run python -m design_checker.conformance --write"


def test_the_revit_folder_waits_for_its_recordings():
    assert (c.RECORDED / "revit").is_dir()
    readme = (c.FOLDER / "README.md").read_text(encoding="utf-8")
    assert "recorded/revit/" in readme and "How to add a host" in readme


def test_the_scenes_cover_what_the_suite_promises():
    """Section 5 of the tidy-up plan (and the stack's reviews) name the cases; each is in some scene's expected
    description, so a scene quietly simplified away is caught."""
    want = {n: c.expected_site(s) for n, s in SCENES.items()}
    codes = {p["code"] for d in want.values() for b in d["buildings"] for p in b["problems"]}
    codes |= {u["problem"]["code"] for d in want.values() for u in d["unsent"]}
    codes |= {p["code"] for d in want.values() for p in d["problems"]}
    assert {"curved_surface", "curved_edge", "open_solid", "not_a_solid", "several_lot_outlines"} <= codes
    left = [o for d in want.values() for o in d["left_out"]]
    assert any(o["touching"] is True for o in left) and any(o["touching"] is False for o in left)
    assert any(o["ground_like"] for o in left) and any(o["context"] for o in left)
    assert any(o.get("block") for s in SCENES.values() for o in s.get("others") or [])      # a block left out
    assert any(e["curved"] for d in want.values() if d["lot"] for e in d["lot"]["edges"])
    assert any(d["grade"]["source"] == "spot" for d in want.values())
    assert any(d["grade"]["source"] == "none" and "elevation" not in (SCENES[n].get("grade") or {})
               for n, d in want.items())
    assert any((s.get("model") or {}).get("units") == "Millimeters" for s in SCENES.values())
    assert any(max(abs(x) for x in (s.get("model") or {}).get("offset", [0])) > 100_000 for s in SCENES.values())
    assert any(c.facts(s).get("corner_lot") for s in SCENES.values())
    assert any(s.get("then") for s in DRAWN.values())
    assert any(d["lot"] is None and not d["problems"] for d in want.values())            # no lot, no reason
    assert any(not d["inventory_complete"] and not d["buildings"] for d in want.values())


# ---- the false-pass guard: a host that sends less fails ----------------------------------------------------------

def _each_problem(doc):
    """(where, a copy of doc with that one problem removed) for every problem in the description."""
    for k in range(len(doc["problems"])):
        d = copy.deepcopy(doc)
        del d["problems"][k]
        yield "site", d
    for i, b in enumerate(doc["buildings"]):
        for k in range(len(b["problems"])):
            d = copy.deepcopy(doc)
            del d["buildings"][i]["problems"][k]
            yield f"building {b['id']}", d
    for i, u in enumerate(doc["unsent"]):
        d = copy.deepcopy(doc)
        del d["unsent"][i]
        yield "unsent", d


@pytest.mark.parametrize("name", sorted(DRAWN))
def test_a_host_that_sends_fewer_problems_than_expected_fails(name):
    """Every problem the expected description holds, dropped one at a time from it, is caught as a FEWER-problems
    difference, even where the verdicts wouldn't change (a curved wall's two codes: either alone still makes the
    building need review, but a host that misses one would miss it where it is the only one)."""
    want = c.expected_site(DRAWN[name])
    for where, fewer in _each_problem(want):
        found = c.differences(fewer, want)
        assert any("FEWER problems" in d for d in found), (where, found)


def test_a_curved_wall_sent_as_if_straight_fails_on_its_faces_its_problems_and_its_verdicts():
    """The false pass the suite exists for: a host that approximates the curved wall by a flat one and says nothing."""
    scene = SCENES["02_curved_wall"]
    doc = c.expected_site(c.load(c.SCENES / "01_box_house.yaml"))      # the same house, every wall flat
    doc["host"]["document"] = scene["name"]
    found = c.conformance(scene, doc)
    assert any("FEWER problems" in d and "curved_surface" in d for d in found)
    assert any("face(s) sent that aren't expected" in d for d in found)
    assert any(d.startswith("verdict R-1b.rear_yard: complies, expected needs_review") for d in found)


def test_a_left_out_object_not_listed_fails():
    want = c.expected_site(SCENES["05_garage_left_out"])
    doc = copy.deepcopy(want)
    doc["left_out"] = []
    assert any("left out garage: not listed" in d for d in c.differences(doc, want))
    found = c.conformance(SCENES["05_garage_left_out"], doc)
    assert any(d.startswith("verdict R-1b.lot_coverage: complies, expected needs_review") for d in found)


def test_touching_unknown_counts_as_touching_and_never_as_apart():
    want = c.expected_site(SCENES["05_garage_left_out"])
    doc = copy.deepcopy(want)
    doc["left_out"][0]["touching"] = None
    assert any("touching None, expected False" in d for d in c.differences(doc, want))
    want_touching = copy.deepcopy(want)
    want_touching["left_out"][0]["touching"] = True
    assert c.differences(doc, want_touching) == []


def test_saying_everything_was_sent_when_it_wasnt_fails_even_where_the_verdicts_dont_change():
    """With no buildings sent, every building measure needs review either way ("no building"), so only the
    description comparison can catch a host that claims it looked at everything: it does."""
    scene = SCENES["14_nothing_sent_and_inventory_incomplete"]
    doc = copy.deepcopy(scene["site"])
    doc["inventory_complete"] = True
    assert c.conformance(scene, doc) == ["inventory_complete True, expected False"]


def test_a_block_counts_alike_sent_as_unsent_or_as_a_faceless_building_and_fails_when_dropped():
    scene = SCENES["04_block_on_building"]
    want = c.expected_site(scene)
    assert want["unsent"] and c.conformance(scene, cr.describe(scene), cr.ids(scene)) == []   # Rhino's own way
    assert [b["id"] for b in cr.describe(scene)["buildings"] if not b["faces"]] == ["a block"]
    doc = copy.deepcopy(want)
    doc["unsent"] = []
    found = c.conformance(scene, doc)
    assert any("objects not sent as solids: FEWER problems" in d for d in found)
    assert any(d.startswith("verdict R-1b.lot_coverage: complies") for d in found)


# ---- points, faces and ids ---------------------------------------------------------------------------------------

def test_points_must_be_within_a_millionth_of_a_foot():
    want = c.expected_site(SCENES["01_box_house"])
    near, far = copy.deepcopy(want), copy.deepcopy(want)
    near["buildings"][0]["faces"][0]["points"][0][0] += 0.9e-6
    far["buildings"][0]["faces"][0]["points"][0][0] += 1.1e-6
    assert c.differences(near, want) == []
    assert any("face(s)" in d for d in c.differences(far, want))
    lot = copy.deepcopy(want)
    lot["lot"]["edges"][1]["points"][0][1] += 1.1e-6
    assert any(d.startswith("lot: its lot lines differ") for d in c.differences(lot, want))
    grade = c.expected_site(SCENES["07_spot_grades_on_a_slope"])
    moved = copy.deepcopy(grade)
    moved["grade"]["points"][0][2] += 1.1e-6
    assert "grade: its points differ from the expected ones" in c.differences(moved, grade)


def test_face_order_where_a_face_starts_and_which_way_it_runs_are_ignored():
    want = c.expected_site(SCENES["01_box_house"])
    doc = copy.deepcopy(want)
    for b in doc["buildings"]:
        b["faces"].reverse()
        for k, f in enumerate(b["faces"]):
            pts = f["points"][1:] + f["points"][:1]
            f["points"] = pts[::-1] if k % 2 else pts
    doc["lot"]["edges"] = [{"points": e["points"][::-1], "curved": e["curved"]} for e in reversed(doc["lot"]["edges"])]
    assert c.differences(doc, want) == []
    doc["buildings"][0]["faces"].pop()
    assert any("1 expected face(s) not sent" in d for d in c.differences(doc, want))


def test_ids_must_be_the_scenes_and_stay_the_same_after_the_edit():
    scene = SCENES["12_ids_stable_after_an_edit"]
    rec = cr.record(scene)
    assert c.recording_problems(cr.HOST, scene["name"], rec, SCENES) == []
    after = rec["steps"][c.STEPS[1]]
    changed = next(b for b in after["buildings"] if b["id"] == c.object_id(scene, "house_floor1"))
    changed["id"] = "a new id, made at the edit"
    found = c.recording_problems(cr.HOST, scene["name"], rec, SCENES)
    assert any("building house_floor1: not sent" in d for d in found)
    assert any("building a new id, made at the edit: sent, but no such building" in d for d in found)


def test_a_recording_with_an_id_map_that_merges_two_objects_fails():
    scene = SCENES["01_box_house"]
    rec = cr.record(scene)
    first = next(iter(rec["ids"]))
    rec["ids"]["another host id"] = rec["ids"][first]
    assert any("two host ids map to one scene id" in d for d in c.recording_problems(cr.HOST, scene["name"], rec, SCENES))


def test_a_host_that_records_some_scenes_must_record_them_all():
    one = {"revit": {"01_box_house": {}}}
    assert c.coverage_problems(one, SCENES) and "02_curved_wall" in c.coverage_problems(one, SCENES)[0]
    assert c.coverage_problems({"revit": {n: {} for n in DRAWN}}, SCENES) == []


def test_a_recording_missing_a_step_or_naming_another_scene_fails():
    scene = SCENES["07_spot_grades_on_a_slope"]
    rec = cr.record(scene)
    del rec["steps"][c.STEPS[1]]
    assert any("steps" in d for d in c.recording_problems(cr.HOST, scene["name"], rec, SCENES))
    rec = cr.record(SCENES["01_box_house"])
    assert any("recorded as" in d for d in c.recording_problems(cr.HOST, "06_no_grade", rec, SCENES))


# ---- the verdicts ------------------------------------------------------------------------------------------------

def test_the_verdicts_must_be_exactly_the_expected_rows():
    want = c.expected_verdicts(SCENES["01_box_house"])
    assert c.verdict_differences(dict(want), want) == []
    extra, missing, wrong = dict(want, **{"R-1b.new_row": "complies"}), dict(want), dict(want)
    del missing["R-1b.height"]
    wrong["R-1b.lot_coverage"] = "needs_review"
    assert c.verdict_differences(extra, want) == ["R-1b.new_row: a row not expected (complies)"]
    assert c.verdict_differences(missing, want) == ["R-1b.height: no such row (expected complies)"]
    assert c.verdict_differences(wrong, want) == ["R-1b.lot_coverage: needs_review, expected complies"]


def test_an_invalid_description_is_reported_as_invalid_and_nothing_else_is_checked():
    scene = SCENES["01_box_house"]
    doc = c.expected_site(scene)
    doc["units"] = "m"
    found = c.conformance(scene, doc)
    assert found and all(d.startswith("not a valid description") for d in found)


# ---- found in review round 1 --------------------------------------------------------------------------------------

def test_a_host_that_says_a_left_out_object_doesnt_touch_when_it_does_fails():
    """The porch against the house's west wall may be part of the house: a host that says it doesn't touch would
    let the yards, height and stories pass with it unmeasured."""
    scene = SCENES["15_objects_left_out_touching_on_context_and_a_block"]
    doc = c.expected_site(scene)
    porch = next(o for o in doc["left_out"] if o["id"] == "porch")
    porch["touching"] = False
    found = c.conformance(scene, doc)
    assert "left out porch: touching False, expected True" in found
    assert any(d.startswith("verdict R-1b.side_yards#west: complies, expected needs_review") for d in found)


@pytest.mark.parametrize("outline, block", [([[2, 50], [12, 50], [12, 60], [2, 60]], False),    # west side, middle
                                            ([[48, 50], [58, 50], [58, 60], [48, 60]], False),  # east side, middle
                                            ([[20, 90], [44, 90], [44, 114], [20, 114]], True)])  # a block on Default
def test_the_reference_adapter_finds_an_object_anywhere_on_the_lot_and_a_block(tmp_path, outline, block):
    """The lot is read as its outline (not its box's corners, which cross over themselves and cover only part of the
    lot), and a block's place is its definition's objects', moved where it is placed."""
    scene = copy.deepcopy(SCENES["05_garage_left_out"])
    scene["others"][0].update(outline=outline, block=block)
    cr.build(scene).Write(str(tmp_path / "m.3dm"), 8)
    left = cr.describe_file(tmp_path / "m.3dm", c.facts(scene))["left_out"]
    assert [o["id"] for o in left] == [c.object_id(scene, "garage")]


def _round_arc(arc, n):
    """The arc as n + 1 points evenly round it, worked out here (not by conformance.arc_points)."""
    cx, cy = arc["center"]
    a0 = math.atan2(arc["start"][1] - cy, arc["start"][0] - cx)
    sweep = c._turn(arc, arc["end"]) * c._sense(arc)
    pts = [[cx + arc["radius"] * math.cos(a0 + sweep * i / n), cy + arc["radius"] * math.sin(a0 + sweep * i / n)]
           for i in range(n + 1)]
    pts[0], pts[-1] = list(arc["start"]), list(arc["end"])
    return pts


def test_a_curved_lot_line_must_follow_the_arc_but_needn_t_have_the_expected_points():
    """The protocol fixes no spacing for a curved lot line, so a host may sample it its own way; but every point
    must be on the arc, in order, no more than 0.25 ft apart, and the line marked curved: never its chord."""
    scene = SCENES["17_curved_rear_lot_line"]
    want = c.expected_site(scene)
    arcs = list(c.lot_arcs(scene).values())
    arc = arcs[0]
    k = next(i for i, e in enumerate(want["lot"]["edges"]) if e["curved"])
    expected_n = len(want["lot"]["edges"][k]["points"]) - 1

    def differs(points, curved=True):
        doc = copy.deepcopy(want)
        doc["lot"]["edges"][k] = {"points": points, "curved": curved}
        return c.differences(doc, want, arcs=arcs)
    assert differs(_round_arc(arc, expected_n)) == []
    assert differs(_round_arc(arc, expected_n * 5 // 4)) == []                 # sampled its own way: fine
    chord = [list(arc["start"]), list(arc["end"])]
    assert differs(chord, curved=False) and differs(chord)                     # the chord, marked or not
    assert differs(_round_arc(arc, expected_n // 4))                           # on the arc, ~1 ft apart
    assert differs(_round_arc(arc, expected_n), curved=False)                  # on the arc, not marked curved
    off = _round_arc(arc, expected_n)
    off[len(off) // 2][1] += 2e-6
    assert differs(off)                                                        # a point off the arc
    back = _round_arc(arc, expected_n)
    back = back[:5] + [back[3]] + back[5:]
    assert differs(back)                                                       # goes back on itself
    for k_end, along_by, ok in [(0, -1e-13, True), (0, -5e-7, True), (-1, 5e-7, True), (0, -2e-6, False)]:
        moved = _round_arc(arc, expected_n)                    # an end a hair off, along the arc: within TOL is fine
        cx, cy = arc["center"]
        p = moved[k_end]
        a = math.atan2(p[1] - cy, p[0] - cx) + c._sense(arc) * along_by / arc["radius"]
        moved[k_end] = [cx + arc["radius"] * math.cos(a), cy + arc["radius"] * math.sin(a)]
        assert (differs(moved) == []) is ok, (k_end, along_by)
    run_back = copy.deepcopy(want)                                             # the whole lot the other way
    run_back["lot"]["edges"] = [{"points": e["points"][::-1], "curved": e["curved"]}
                                for e in reversed(run_back["lot"]["edges"])]
    assert c.differences(run_back, want, arcs=arcs) == []


def test_the_suite_s_arc_spacing_is_the_reader_s():
    from model_measurement.read_3dm import ARC_STEP
    assert c.ARC_STEP == ARC_STEP


def test_a_recording_with_a_key_given_twice_is_refused_as_the_worker_refuses_it(tmp_path, monkeypatch):
    host = tmp_path / "revit"
    host.mkdir()
    text = (c.RECORDED / cr.HOST / "02_curved_wall.json").read_text(encoding="utf-8")
    text = text.replace('"problems": [', '"problems": [], "problems": [', 1)
    (host / "02_curved_wall.json").write_text(text, encoding="utf-8")
    monkeypatch.setattr(c, "RECORDED", tmp_path)
    rec = c.recordings()["revit"]["02_curved_wall"]
    found = c.recording_problems("revit", "02_curved_wall", rec, SCENES)
    assert found and all("can't be read" in d and "given twice" in d for d in found)


@pytest.mark.parametrize("name", sorted(DRAWN))
def test_every_object_a_scene_draws_has_the_same_id_on_every_build(name):
    """Every placed object, blocks included (scenes 04 and 15); not a block's definition's own objects, whose ids
    rhino3dm makes and every reader skips."""
    scene = DRAWN[name]
    a, b = cr.build(scene), cr.build(scene)
    placed = lambda m: [str(o.Attributes.Id) for o in m.Objects if not o.Attributes.IsInstanceDefinitionObject]  # noqa: E731
    assert placed(a) == placed(b)
    assert [str(layer.Id) for layer in a.Layers] == [str(layer.Id) for layer in b.Layers]
    assert len(set(placed(a))) == len(placed(a))


def test_the_reference_adapter_reads_a_lot_by_its_outline_not_its_box(tmp_path):
    """A lot whose north line slopes (y = 60 at the west, 120 at the east): a shed inside the lot's box but past
    that line is the neighbour's, not left out of this check; one inside the line is."""
    scene = copy.deepcopy(SCENES["05_garage_left_out"])
    scene["lots"] = [[[0, 0], [60, 0], [60, 120], [0, 60]]]
    for outline, on_lot in [([[2, 100], [12, 100], [12, 110], [2, 110]], False), ([[2, 40], [12, 40], [12, 50], [2, 50]], True)]:
        scene["others"][0]["outline"] = outline
        cr.build(scene).Write(str(tmp_path / "m.3dm"), 8)
        left = cr.describe_file(tmp_path / "m.3dm", c.facts(scene))["left_out"]
        assert bool(left) is on_lot, outline


# ---- an object with no box: the live command keeps it, as the reference adapter does -----------------------------

class _Pt:
    def __init__(self, x, y, z=0.0):
        self.X, self.Y, self.Z = float(x), float(y), float(z)


class _Box:
    """RhinoCommon's BoundingBox, as much of it as the plugin's left-out code uses."""

    def __init__(self, lo, hi):
        self.Min, self.Max = _Pt(*lo), _Pt(*hi)

    @property
    def IsValid(self):  # noqa: N802 (RhinoCommon's name)
        return all(abs(v) < 1e300 for v in (self.Min.X, self.Min.Y, self.Min.Z, self.Max.X, self.Max.Y, self.Max.Z)) \
            and self.Min.X <= self.Max.X and self.Min.Y <= self.Max.Y and self.Min.Z <= self.Max.Z

    def Inflate(self, d):  # noqa: N802
        if not self.IsValid:        # RhinoCommon, BoundingBox.Inflate: "Invalid boxes can not be inflated."
            return                  # (developer.rhino3d.com/api/rhinocommon/rhino.geometry.boundingbox/inflate)
        self.Min, self.Max = _Pt(self.Min.X - d, self.Min.Y - d, self.Min.Z - d), _Pt(self.Max.X + d, self.Max.Y + d,
                                                                                       self.Max.Z + d)

    @staticmethod
    def Intersection(a, b):  # noqa: N802
        return _Box((max(a.Min.X, b.Min.X), max(a.Min.Y, b.Min.Y), max(a.Min.Z, b.Min.Z)),
                    (min(a.Max.X, b.Max.X), min(a.Max.Y, b.Max.Y), min(a.Max.Z, b.Max.Z)))


EMPTY_BOX = ((1, 0, 0), (-1, 0, 0))                       # RhinoCommon's BoundingBox.Empty
UNSET = -1.23432101234321e308                             # RhinoMath.UnsetValue: BoundingBox.Unset
UNSET_BOX = ((UNSET,) * 3, (UNSET,) * 3)


class _Geometry:
    def __init__(self, box):
        self._box = box

    def GetBoundingBox(self, accurate):  # noqa: N802
        return _Box(*self._box)


class InstanceReferenceGeometry(_Geometry):               # a placed block: the plugin goes by its type's name
    pass


class Extrusion(_Geometry):                               # not rg.Extrusion: told only by its type's name
    pass


class _Definition:
    """RhinoCommon's InstanceDefinition: its parts, and its ArchiveFileStatus (by name; a block not linked to a file
    by default)."""
    walked = 0                                            # GetObjects calls, every definition: a cost counter

    def __init__(self, parts, status="NotALinkedInstanceDefinition"):
        self._parts, self.Id, self.ArchiveFileStatus = parts, uuid.uuid4(), status

    def GetObjects(self):  # noqa: N802
        _Definition.walked += 1
        return tuple(self._parts)


class _InstanceObject:
    """RhinoCommon's InstanceObject (a placed block): its box is its parts' boxes joined, an invalid one left out,
    as Rhino joins them; `parts` None is a definition that isn't there; `status`, its definition's
    ArchiveFileStatus."""

    def __init__(self, oid, parts, layer=2, definition=None, status="NotALinkedInstanceDefinition"):
        self.Id, self.Attributes = oid, types.SimpleNamespace(LayerIndex=layer)
        self.InstanceDefinition = definition or (None if parts is None else _Definition(parts, status))
        parts = definition._parts if definition else parts
        boxes = [p.Geometry.GetBoundingBox(True) for p in parts or []]
        boxes = [b for b in boxes if b.IsValid]
        self.Geometry = InstanceReferenceGeometry(
            ((min(b.Min.X for b in boxes), min(b.Min.Y for b in boxes), min(b.Min.Z for b in boxes)),
             (max(b.Max.X for b in boxes), max(b.Max.Y for b in boxes), max(b.Max.Z for b in boxes)))
            if boxes else EMPTY_BOX)


def _part(box):
    return types.SimpleNamespace(Id="part", Geometry=_Geometry(box), Attributes=types.SimpleNamespace(LayerIndex=2))


def _missing_file_label(at):
    """What live Rhino 8.35 (Mac) puts in a linked block's definition when its file isn't found (seen 2026-11-12):
    one text label, "Missing block file: ...", at the centre of the last known shape: a valid box of one point."""
    return _part((at, at))


def _missing_file_block(oid, at):
    """A placed linked block whose file isn't found, as live Rhino has it: its definition's status
    LinkedFileNotFound, holding only the label (_missing_file_label), so the block's own box is that point."""
    return _InstanceObject(oid, [_missing_file_label(at)], status="LinkedFileNotFound")


class _Curve(_Geometry):
    def __init__(self, ring):
        super().__init__(((min(x for x, _ in ring), min(y for _, y in ring), 0),
                          (max(x for x, _ in ring), max(y for _, y in ring), 0)))
        self._ring = ring

    def TryGetPolyline(self):  # noqa: N802
        return True, [_Pt(x, y) for x, y in self._ring + self._ring[:1]]


def _live_left_out(blocks, lot_at=(1000.0, 2000.0)):
    """gordium_rhino's own _not_included, _touching, _ground_like and _unmeasured_outlines, run on a stub document:
    a 60 × 120 ft lot at survey coordinates (`lot_at`), a house on it, and `blocks` ({id: box}, or a placed
    _InstanceObject with its definition's parts, or any object with a Geometry) placed on Default."""
    import ast
    import types

    from host_source import host_path, host_text

    from design_checker import rhino_logic as logic
    names = ("_not_included", "_seen", "_plan_box", "_plan_points", "_touching", "_ground_like",
             "_unmeasured_outlines")
    tree = ast.parse(host_text("rhino", "plugin", purpose="wiring"))
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert sorted(f.name for f in fns) == sorted(names)
    x, y = lot_at
    lot = types.SimpleNamespace(Id="lot", Geometry=_Curve([(x, y), (x + 60, y), (x + 60, y + 120), (x, y + 120)]),
                                Attributes=types.SimpleNamespace(LayerIndex=0))
    house = types.SimpleNamespace(Id="house", Geometry=_Geometry(((x + 15, y + 30, 0), (x + 45, y + 80, 20))),
                                  Attributes=types.SimpleNamespace(LayerIndex=1))
    placed = [box if hasattr(box, "Geometry") else
              types.SimpleNamespace(Id=i, Geometry=InstanceReferenceGeometry(box),
                                    Attributes=types.SimpleNamespace(LayerIndex=2)) for i, box in blocks.items()]
    every = [lot, house] + placed
    doc = types.SimpleNamespace(Layers=[types.SimpleNamespace(FullPath=p) for p in ("Site", "Building", "Default")],
                                Objects=types.SimpleNamespace(GetObjectList=lambda settings: list(every)))
    rg = types.SimpleNamespace(Brep=type("Brep", (), {}), Mesh=type("Mesh", (), {}),
                               Extrusion=type("Extrusion", (), {}), Curve=_Curve, Point3d=_Pt, BoundingBox=_Box)
    rhino = types.SimpleNamespace(DocObjects=types.SimpleNamespace(ObjectEnumeratorSettings=types.SimpleNamespace,
                                                                   InstanceObject=_InstanceObject))
    ns = {"rg": rg, "Rhino": rhino, "logic": logic, "LAYERS": {"building": "Building"},
          "_model_length": lambda doc, feet: feet, "_scale": lambda doc: 1.0, "_ui_state": lambda doc: {},
          "_find": lambda doc, i: next((o for o in every if o.Id == i), None)}
    exec(compile(ast.Module(body=fns, type_ignores=[]), host_path("rhino", "plugin").name, "exec"), ns)  # noqa: S102
    left = ns["_not_included"](doc, lot)
    return (left, ns["_touching"](doc, left, [house]), ns["_ground_like"](doc, left, lot),
            ns["_unmeasured_outlines"](doc, left))


@pytest.mark.parametrize("no_box", [EMPTY_BOX, UNSET_BOX], ids=["empty", "unset"])
@pytest.mark.parametrize("lot_at", [(0.0, 0.0), (-30.0, -60.0), (1000.0, 2000.0)],
                         ids=["origin", "round_origin", "survey"])
def test_the_live_command_keeps_a_block_with_no_box_as_left_out_and_touching(no_box, lot_at):
    """A placed block with no box to place it by (its definition empty: the viewport shows nothing, but the garage
    it stands for may be part of the design) can't be told off the lot or apart
    from the house. The Rhino command dropped it (its box missed the lot's, or its box's corners outlined nothing;
    had it been kept, its box would also have been taken as not touching), so nothing said a building was left out
    (or touching) and coverage, the yards, height and stories could stay "complies". It now counts as on the lot and
    touching, as the reference adapter lists it (touching unknown); a normal shed apart from the house and one off
    the lot are still told by their boxes. (_ground_like runs too: a block never looks like the ground.)"""
    x, y = lot_at
    shed = ((x + 48, y + 90, 0), (x + 56, y + 98, 8))                 # on the lot, apart from the house
    away = ((x + 500, y, 0), (x + 510, y + 10, 8))                    # far off the lot
    left, touching, ground, outlines = _live_left_out({"nothing": no_box, "shed": shed, "away": away}, lot_at)
    assert left == ["nothing", "shed"]
    assert touching == ["nothing"]
    assert ground == []
    assert len(outlines) == 1                                         # the shed's; the block with no box has none


@pytest.mark.parametrize("where", ["off_the_lot", "apart_from_the_house"])
def test_the_live_command_keeps_a_block_holding_a_part_with_no_box_as_left_out_and_touching(where):
    """A block whose drawn part has a box but which also holds a block with none (a linked block whose file has
    moved, placed inside it): Rhino gives the outer block its drawn part's box alone, so the command judged it by
    that part and dropped it (drawn part off the lot) or took it as not touching (drawn part apart from the house),
    while the part not drawn may be a porch against the house: the yards, height and stories could stay "complies".
    It counts as on the lot and touching, as the reference adapter gives such a block no box (test below). A block
    whose every part has a box is still told by its box."""
    x, y = 1000.0, 2000.0
    drawn = {"off_the_lot": ((x + 500, y, 0), (x + 510, y + 10, 8)),
             "apart_from_the_house": ((x + 48, y + 90, 0), (x + 56, y + 98, 8))}[where]
    holding_nothing = _InstanceObject("inner", [])                   # an empty definition
    partly = _InstanceObject("partly", [_part(drawn), holding_nothing])
    missing = _InstanceObject("missing", [_part(drawn), _InstanceObject("gone", None)])   # no definition at all
    whole = _InstanceObject("whole", [_part(((x + 48, y + 90, 0), (x + 56, y + 98, 8)))])
    left, touching, _, outlines = _live_left_out({"partly": partly, "missing": missing, "whole": whole}, (x, y))
    assert left == ["partly", "missing", "whole"]
    assert touching == ["partly", "missing"]
    assert len(outlines) == 1                 # the whole block's; a box of its drawn part alone would mislead


@pytest.mark.parametrize("lot_at", [(0.0, 0.0), (1000.0, 2000.0)], ids=["origin", "survey"])
def test_the_live_command_keeps_a_linked_block_whose_file_is_not_found_as_left_out_and_touching(lot_at):
    """Live Rhino 8.35 (Mac), 2026-11-12: a linked shed whose file had moved, placed against the house, was neither
    listed as left out nor touching, and the front and side yards read "complies". Rhino gives such a definition
    one text label at the centre of the shed's last known shape (a valid box of one point) and the status
    LinkedFileNotFound: the command took the point box as the whole block, and a point covers no ground, so it was
    "off the lot". It now counts as left out and touching. The same holds when the shed is placed inside another
    block beside a drawn part apart from the house (the live run's second case: listed as left out, but not
    touching, so the side yards read "complies"). A normal block of the same shape is still told by its box."""
    x, y = lot_at
    centre = (x + 11, y + 76, 4)              # an 8 ft shed against the house's west wall (x + 15), at its north end
    linked = _missing_file_block("linked", centre)
    drawn = _part(((x + 2, y + 90, 0), (x + 10, y + 98, 8)))          # on the lot, apart from the house
    nested = _InstanceObject("nested", [drawn, _missing_file_block("inner", centre)])   # box x+2..11: 4 ft off
    normal = _InstanceObject("normal", [_part(((x + 48, y + 90, 0), (x + 56, y + 98, 8)))])
    left, touching, _, outlines = _live_left_out({"linked": linked, "nested": nested, "normal": normal}, lot_at)
    assert left == ["linked", "nested", "normal"]
    assert touching == ["linked", "nested"]
    assert len(outlines) == 1                                         # the normal block's


@pytest.mark.parametrize("status, known", [
    ("NotALinkedInstanceDefinition", True), ("LinkedFileIsUpToDate", True),
    ("LinkedFileNotFound", False), ("LinkedFileNotReadable", False), ("LinkedFileIsNewer", False),
    ("LinkedFileIsOlder", False), ("LinkedFileIsDifferent", False), ("SomeStatusRhinoAddsLater", False),
    ("Rhino.DocObjects.InstanceDefinitionArchiveFileStatus.LinkedFileIsUpToDate", True)])
def test_the_live_command_measures_a_block_only_when_its_contents_are_the_block(status, known):
    """A block's contents are the block only when it isn't linked to a file, or its linked file was read and is up
    to date (rhino_logic.block_contents_known). Otherwise (not found, not readable, or changed since it was read)
    what the document holds may not be the design: even a shed drawn on the lot apart from the house counts as
    having no box, so as left out and touching (needs review), never as a part told apart by a stale box."""
    x, y = 1000.0, 2000.0
    shed = _InstanceObject("shed", [_part(((x + 48, y + 90, 0), (x + 56, y + 98, 8)))], status=status)
    left, touching, _, outlines = _live_left_out({"shed": shed}, (x, y))
    assert left == ["shed"]
    assert touching == ([] if known else ["shed"])
    assert len(outlines) == (1 if known else 0)


@pytest.mark.parametrize("kind", [InstanceReferenceGeometry, Extrusion], ids=["block", "extrusion"])
def test_the_live_command_places_an_object_whose_box_covers_no_ground_by_the_line_it_lies_on(kind):
    """An object whose box is a point or a line in plan (a block of one label, an upright panel drawn as an
    extrusion) has no footprint: reaches_into_lot read it as off the lot, so a panel standing in the side yard
    against the house was dropped. It is now on the lot when some of the line it lies on stands more than the reach
    inside the lot's outline, and touching by its box as any other: the panel against the house is listed and
    touching, the label 4 ft from the house is listed and not touching. A neighbour's fence drawn as a flat
    extrusion on the lot line or a hair outside it, and a cut-out tree 300 ft away, stay off."""
    x, y = 1000.0, 2000.0
    boxes = {"label": ((x + 11, y + 54, 4), (x + 11, y + 54, 4)), "panel": ((x + 15, y + 50, 0), (x + 15, y + 58, 8)),
             "fence_on_line": ((x, y + 10, 0), (x, y + 110, 6)), "fence_outside": ((x - 0.05, y + 10, 0),
                                                                                  (x - 0.05, y + 110, 6)),
             "far": ((x + 300, y, 0), (x + 306, y, 12))}
    placed = {i: types.SimpleNamespace(Id=i, Geometry=kind(box), Attributes=types.SimpleNamespace(LayerIndex=2))
              for i, box in boxes.items()}
    if kind is InstanceReferenceGeometry:                               # placed blocks, their parts whole
        placed = {i: _InstanceObject(i, [_part(box)]) for i, box in boxes.items()}
    left, touching, _, _ = _live_left_out(placed, (x, y))
    assert left == ["label", "panel"] and touching == ["panel"]


def test_the_live_command_walks_each_block_definition_once_however_often_it_is_placed():
    """A facade block placed 20 times, holding a window block placed 100 times: each definition is walked once per
    look (the left-out list, the touching test, the outlines), not once per placing and path (2,020 walks)."""
    x, y = 1000.0, 2000.0
    window = _Definition([_part(((x + 48, y + 90, 0), (x + 49, y + 91, 1)))])
    facade = _Definition([_InstanceObject(f"w{k}", None, definition=window) for k in range(100)])
    placed = {f"f{k}": _InstanceObject(f"f{k}", None, definition=facade) for k in range(20)}
    _Definition.walked = 0
    left, touching, _, outlines = _live_left_out(placed, (x, y))
    assert len(left) == 20 and touching == [] and len(outlines) == 20
    assert _Definition.walked == 2 * 3                  # 2 definitions, in each of the 3 looks


def test_the_live_command_counts_a_block_whose_status_cant_be_read_as_left_out_and_touching():
    """Review round 1: reading a definition's ArchiveFileStatus may fail; the command then sends no status (None),
    which is not known: the block, a shed on the lot apart from the house, is left out and touching, never told by
    its box."""
    x, y = 1000.0, 2000.0

    class Unreadable(_Definition):
        @property
        def ArchiveFileStatus(self):  # noqa: N802
            raise RuntimeError("no status")

        @ArchiveFileStatus.setter
        def ArchiveFileStatus(self, value):  # noqa: N802
            pass
    shed = _InstanceObject("shed", None, definition=Unreadable([_part(((x + 48, y + 90, 0), (x + 56, y + 98, 8)))]))
    left, touching, _, outlines = _live_left_out({"shed": shed}, (x, y))
    assert left == ["shed"] and touching == ["shed"] and outlines == []


def test_the_live_command_sends_each_block_definition_whole_however_deep_it_is_first_seen():
    """Review round 3: the command's look (_seen) stopped walking 32 deep, so a definition first seen 33 deep (inside
    a block host_core gives up on early: it holds an empty block first) was never sent, and the same definition
    placed on its own, far off the lot, came back "not found": left out and touching, where the command had judged
    it by its box. A chain 40 deep still has no box."""
    x, y = 1000.0, 2000.0
    far = _part(((x + 500, y, 0), (x + 510, y + 10, 8)))
    p = _Definition([_InstanceObject("c", None, definition=_Definition([far]))])
    chain = [p]
    for k in range(31):
        chain.append(_Definition([_InstanceObject("q%d" % k, None, definition=chain[-1])]))
    first = _Definition([_InstanceObject("e", None, definition=_Definition([])),
                         _InstanceObject("q", None, definition=chain[-1])])
    placed = {"A": _InstanceObject("A", None, definition=first), "B": _InstanceObject("B", None, definition=p)}
    left, touching, _, _ = _live_left_out(placed, (x, y))
    assert left == ["A"] and touching == ["A"]
    inner = _Definition([_part(((x + 48, y + 90, 0), (x + 56, y + 98, 8)))])
    deep = [inner]
    for k in range(40):
        deep.append(_Definition([_InstanceObject("d%d" % k, None, definition=deep[-1])]))
    left, touching, _, _ = _live_left_out({"deep": _InstanceObject("deep", None, definition=deep[-1])}, (x, y))
    assert left == ["deep"] and touching == ["deep"]


def _live_advice(placed, files):
    """gordium_rhino's own _link_advice (with _seen) on a stub document holding `placed` ({id: _InstanceObject}):
    `files` ({definition: (its SourceArchive, its Name)}) is what the document's InstanceDefinitions.Find gives."""
    import ast

    from host_source import host_path, host_text

    from design_checker import rhino_logic as logic
    tree = ast.parse(host_text("rhino", "plugin", purpose="wiring"))
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("_link_advice", "_seen")]
    assert sorted(f.name for f in fns) == ["_link_advice", "_seen"]
    by_id = {}
    for d, (archive, name) in files.items():
        d.SourceArchive, d.Name = archive, name
        by_id[str(d.Id)] = d
    doc = types.SimpleNamespace(InstanceDefinitions=types.SimpleNamespace(
        Find=lambda guid, ignore_deleted: by_id.get(guid) if ignore_deleted else None))
    rhino = types.SimpleNamespace(DocObjects=types.SimpleNamespace(InstanceObject=_InstanceObject))
    ns = {"Rhino": rhino, "logic": logic, "System": types.SimpleNamespace(Guid=str),
          "_find": lambda doc, i: placed.get(i)}
    exec(compile(ast.Module(body=fns, type_ignores=[]), host_path("rhino", "plugin").name, "exec"), ns)  # noqa: S102
    return ns["_link_advice"](doc, list(placed))


def test_the_live_command_says_which_linked_file_to_put_right_and_how():
    """Ben, 2026-11-12: a linked shed whose file has moved, and a garage placed inside a block whose linked file
    changed since it was read, stay left out and touching (tests above); the review row now names each file and
    what to do in Rhino 8 (the file Rhino looked for, by its own name; Edit > Blocks > Block Definitions). A block
    whose contents are known is given no advice."""
    x, y = 1000.0, 2000.0
    shed = _missing_file_block("shed", (x + 11, y + 76, 4))
    garage_def = _Definition([_part(((x + 48, y + 90, 0), (x + 56, y + 98, 8)))], status="LinkedFileIsNewer")
    holder = _InstanceObject("holder", [_InstanceObject("garage", None, definition=garage_def)])
    normal = _InstanceObject("normal", [_part(((x + 48, y + 90, 0), (x + 56, y + 98, 8)))])
    advice = _live_advice({"shed": shed, "holder": holder, "normal": normal},
                          {shed.InstanceDefinition: ("/Users/me/Projects/106 Ithaca/shed.3dm", "Shed"),
                           garage_def: ("/Users/me/Projects/106 Ithaca/garage.3dm", "Garage")})
    assert advice == {
        "shed": "Linked file 'shed.3dm' can't be found at /Users/me/Projects/106 Ithaca/shed.3dm: relink it to where "
                "the file is now (Edit \u25b8 Blocks \u25b8 Block Definitions, select it, then Properties \u25b8 "
                "Filename: Browse to the file) so Gordium can measure it",
        "holder": "Linked file 'garage.3dm' has changed since it was loaded: reload it (Edit \u25b8 Blocks \u25b8 "
                  "Block Definitions, select it, then Update; or type -BlockManager, Update, All) so Gordium can "
                  "measure it"}
    left, touching, _, _ = _live_left_out({"shed": shed, "holder": holder, "normal": normal}, (x, y))
    assert left == ["shed", "holder", "normal"] and touching == ["shed", "holder"]     # the answer, as before


def test_the_reference_adapter_stops_with_the_workers_words_when_it_refuses():
    """Review round 2: a refused part (a lot with no outline) came back as a bare KeyError, its reason lost; it is
    never read as nothing left out."""
    import rhino3dm as r
    lot = types.SimpleNamespace(Geometry=r.Polyline([r.Point3d(0, 0, 0), r.Point3d(60, 0, 0), r.Point3d(0, 0, 0)])
                                .ToPolylineCurve())
    model = types.SimpleNamespace(Layers=[], Objects=[])
    with pytest.raises(ValueError, match="objects.left_out refused: left_out: lot: its ring is an outline"):
        cr._left_out(model, lot, [], 1.0)


def test_the_reference_adapter_gives_a_block_holding_a_part_with_no_box_no_box(tmp_path):
    """The adapter's half: a block holding a solid far off the lot and a block whose definition isn't in the file is
    listed, touching unknown (counts as touching), as the live command now lists it."""
    import rhino3dm as r
    scene = copy.deepcopy(SCENES["05_garage_left_out"])
    scene["others"] = []
    model = cr.build(scene)
    layer = cr._layer(model, "Default")
    solid = cr._solid({"outline": [[5000, 5000], [5010, 5000], [5010, 5010], [5000, 5010]], "base": 0, "top": 10},
                      1.0)                                          # far off the lot
    inside = r.ObjectAttributes()
    inside.LayerIndex = layer
    index = model.InstanceDefinitions.Add("partly", "", "", "", r.Point3d(0, 0, 0),
                                          (solid, r.InstanceReference(uuid.uuid4(), r.Transform.Identity())),
                                          (inside, inside))
    attrs = r.ObjectAttributes()
    attrs.LayerIndex = layer
    model.Objects.AddInstanceObject(
        r.InstanceReference(model.InstanceDefinitions.FindIndex(index).Id, r.Transform.Identity()), attrs)
    model.Write(str(tmp_path / "m.3dm"), 8)
    left = cr.describe_file(tmp_path / "m.3dm", c.facts(scene))["left_out"]
    assert [(o["layer"], o["touching"]) for o in left] == [("Default", None)]


def test_the_reference_adapter_lists_a_block_with_no_box_as_left_out_and_touching_unknown(tmp_path):
    """The other half of the same decision: a placed block whose definition isn't in the file is listed by the
    rhino3dm adapter, touching unknown, which counts as touching."""
    import rhino3dm as r
    scene = copy.deepcopy(SCENES["05_garage_left_out"])
    scene["others"] = []
    model = cr.build(scene)
    attrs = r.ObjectAttributes()
    attrs.LayerIndex = cr._layer(model, "Default")
    model.Objects.AddInstanceObject(r.InstanceReference(uuid.uuid4(), r.Transform.Identity()), attrs)
    model.Write(str(tmp_path / "m.3dm"), 8)
    left = cr.describe_file(tmp_path / "m.3dm", c.facts(scene))["left_out"]
    assert [(o["layer"], o["touching"]) for o in left] == [("Default", None)]


@pytest.mark.parametrize("update", ["Static", "Embedded", "LinkedAndEmbedded", "Linked"])
def test_the_reference_adapter_gives_every_linked_block_no_box(update):
    """A .3dm can't say whether a linked block's file is found and unchanged: it holds a Linked definition with no
    objects, and a LinkedAndEmbedded one with the copy last read, either way. (rhino3dm can't write a linked
    definition, so this reads a stand-in for the file's definition table; live Rhino's state when the file is
    missing, one label and LinkedFileNotFound, lives only in a running Rhino.) The adapter gives every block not
    Static no box, even one holding a whole shed, as the command does whenever the file isn't found and up to date:
    the cautious side."""
    import rhino3dm as r
    shed = r.Brep.CreateFromBox(r.Box(r.BoundingBox(48, 90, 0, 56, 98, 8)))
    part = types.SimpleNamespace(Geometry=shed)
    definition = types.SimpleNamespace(UpdateType=getattr(r.InstanceDefinitionUpdateType, update),
                                       GetObjectIds=lambda: ["shed"])
    model = types.SimpleNamespace(InstanceDefinitions=types.SimpleNamespace(FindId=lambda i: definition),
                                  Objects=types.SimpleNamespace(FindId=lambda i: part))
    box = cr._box(model, r.InstanceReference(uuid.uuid4(), r.Transform.Identity()))
    assert box == (((48, 90, 56, 98), (0, 8)) if update == "Static" else None)


def test_the_reference_adapter_places_a_block_whose_box_covers_no_ground_by_its_point(tmp_path):
    """A block of only a point 4 ft from the house (its box covers no ground) is listed, not touching, as the live
    command lists it; before, its point box read as off the lot. One far from the lot is not listed."""
    import rhino3dm as r
    scene = copy.deepcopy(SCENES["05_garage_left_out"])
    scene["others"] = []
    model = cr.build(scene)
    layer = cr._layer(model, "Default")
    inside = r.ObjectAttributes()
    inside.LayerIndex = layer
    (x0, y0, x1, y1), _ = cr._box(model, next(o.Geometry for o in model.Objects
                                              if cr.logic.on_layer(model.Layers[o.Attributes.LayerIndex].FullPath,
                                                                   c.BUILDING_LAYER)))
    attrs = r.ObjectAttributes()
    attrs.LayerIndex = layer
    for name, at in (("label", (x0 - 4, (y0 + y1) / 2, 4)), ("far", (x0 + 5000, y0, 4))):
        index = model.InstanceDefinitions.Add(name, "", "", "", r.Point3d(0, 0, 0), (r.Point(r.Point3d(*at)),),
                                              (inside,))
        model.Objects.AddInstanceObject(
            r.InstanceReference(model.InstanceDefinitions.FindIndex(index).Id, r.Transform.Identity()), attrs)
    model.Write(str(tmp_path / "m.3dm"), 8)
    left = cr.describe_file(tmp_path / "m.3dm", c.facts(scene))["left_out"]
    assert [(o["layer"], o["touching"]) for o in left] == [("Default", False)]


def test_the_live_command_s_linked_file_advice_can_never_stop_a_check():
    """The advice is words only: _extras asks for it through logic.guard (an error is logged and the row is said
    without it), never directly, so a failure reading a definition's file can't take the check's answer with it."""
    import ast

    from host_source import host_text
    tree = ast.parse(host_text("rhino", "plugin", purpose="wiring"))
    extras = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_extras")
    calls = [n for n in ast.walk(extras) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_link_advice"]
    guarded = [n for n in ast.walk(extras) if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "guard"
               and any(c in ast.walk(n) for c in calls)]
    assert len(calls) == 1 and len(guarded) == 1
