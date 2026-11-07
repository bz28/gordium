"""The host conformance suite (design_checker/conformance.py; test_data/host_conformance/README.md): every scene's
description from the Rhino reference adapter, and every host's recording, matches the scene's expected description
and gives exactly its hand-worked verdicts through check_site. The guards below pin that the comparison can fail:
a host that sends fewer problems, drops a left-out object, moves a point, changes an id or gets a verdict wrong is
caught, never waved through."""

import copy
import json
import math

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


def test_every_object_a_scene_draws_has_the_same_id_on_every_build():
    scene = SCENES["07_spot_grades_on_a_slope"]
    a, b = cr.build(scene), cr.build(scene)
    assert [str(o.Attributes.Id) for o in a.Objects] == [str(o.Attributes.Id) for o in b.Objects]
    assert [str(layer.Id) for layer in a.Layers] == [str(layer.Id) for layer in b.Layers]
    assert len({str(o.Attributes.Id) for o in a.Objects}) == len(list(a.Objects))


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
