"""The context map in Rhino, without Rhino: what context_box hands the Rhino side, where it lands, what may be
written into the .3dm (a .3dm written exactly as the plugin writes it, with rhino3dm, and read back), and that the
checker never measures any of it."""

import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest
import rhino3dm as r

from design_checker import context_box as cb
from design_checker import rhino_logic as logic
from design_checker.lookup_box import box_payload
from model_measurement.read_3dm import read_site
from site_lookup.lookup import lookup
from site_lookup.sources import ENDPOINTS

REPO = Path(__file__).parents[3]
spec = importlib.util.spec_from_file_location("site_lookup_t", REPO / "packages/site_lookup/tests/test_lookup.py")
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)
RHINO = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")


def looked_up():
    fx = T.load("106_ithaca_rd")
    return box_payload(lookup(fx["address"], T.Fake(fx), T.NOW))


def context_for(p=None, http=None):
    p = p or looked_up()
    http = http or T.Fake(T.load("106_ithaca_rd"), context=T.load("106_ithaca_rd_context"))
    return cb.fetch(p["writes"]["frame"], http, now=T.NOW), p


# ---- where it lands ---------------------------------------------------------------------------------------------

def test_the_lookups_frame_carries_what_the_context_needs():
    frame = looked_up()["writes"]["frame"]
    assert set(frame) == {"origin_epsg2261_us_survey_ft", "rotation_deg", "datum_ft", "shift_ft", "parcel_id"}
    assert frame["parcel_id"] == "500700-84.-2-6"
    args = logic.context_command("py", frame)
    assert args[:3] == ["py", "-m", "design_checker.context_box"] and args[args.index("--parcel") + 1] == "500700-84.-2-6"
    assert logic.context_command("py", {k: v for k, v in frame.items() if k != "shift_ft"}) is None   # an older file
    assert logic.context_command("py", None) is None


def test_the_neighbours_land_against_the_drawn_lot():
    """The parcel next door shares the lot's corners exactly where the lookup drew the lot (same turn, same shift)."""
    payload, p = context_for()
    lot = p["writes"]["lot_ring"]
    parcels = [o for o in payload["objects"] if o["layer"] == cb.LAYER_OF["parcels"]]
    shared = [c for c in lot if any(math.dist(c, q) < 0.05 for o in parcels for q in o["points"])]
    assert len(shared) >= 4                                   # the side neighbours' corners on the lot's corners
    # Ithaca Road's centerline runs just in front of the lot's street side (half a right-of-way away)
    from site_lookup.geometry import polyline_distance
    ithaca = [o["points"] for o in payload["objects"] if o["layer"] == cb.LAYER_OF["streets"] and o["name"] == "Ithaca Road"]
    front = p["writes"]["street_line"]
    mid = [(front[0][0][0] + front[-1][1][0]) / 2, (front[0][0][1] + front[-1][1][1]) / 2]
    assert ithaca and min(polyline_distance(tuple(mid), [tuple(q) for q in path]) for path in ithaca) < 40


def test_north_points_where_the_lookup_turned_north():
    payload, p = context_for()
    rot = math.radians(p["writes"]["frame"]["rotation_deg"])
    arrow = next(o for o in payload["objects"] if o["name"] == "North (grid north)")["points"]
    tail = [(arrow[0][0] + arrow[2][0]) / 2, (arrow[0][1] + arrow[2][1]) / 2]
    tip = arrow[1]
    got = math.atan2(tip[1] - tail[1], tip[0] - tail[0])
    want = math.atan2(math.cos(rot), -math.sin(rot))         # +y turned by the lot's rotation
    assert abs((got - want + math.pi) % (2 * math.pi) - math.pi) < 1e-6


# ---- what may be kept -----------------------------------------------------------------------------------------

def test_only_storable_sources_become_objects_and_the_footprints_are_guides():
    payload, _ = context_for()
    assert payload["counts"] == {"parcels": 229, "streets": 38, "buildings": 212}
    sources = {o["source"] for o in logic.context_objects(payload)}
    assert sources == {"state_parcels", "state_streets", "gordium"}
    assert all(ENDPOINTS[s]["store"] == "raw" for s in sources - {"gordium"})
    assert len(logic.context_guides(payload)) == 212 and not any(o["source"] == "state_buildings" for o in payload["objects"])


def test_an_object_from_a_live_only_source_is_never_written_whatever_the_payload_says():
    payload, _ = context_for()
    bad = dict(payload, objects=payload["objects"] + [
        {"layer": cb.LAYER_OF["buildings"], "kind": "closed", "points": [[0, 0], [1, 0], [1, 1]], "source": "state_buildings"},
        {"layer": "Site", "kind": "closed", "points": [[0, 0], [1, 0], [1, 1]], "source": "state_parcels"}])
    kept = logic.context_objects(bad)
    assert len(kept) == len(payload["objects"])               # neither the footprint nor an object off the context layer


def write_like_the_plugin(path, lookup_payload, payload):
    """A .3dm as GordiumStart leaves it, written the way gordium_rhino.draw_context writes (the same calls, through
    rhino3dm): the lot on Site, a house on Gordium::Massing, then every rhino_logic.context_objects object on its
    layer with its source in user text, the snapshot in the document's strings. The guides are never written."""
    m = r.File3dm()
    m.Settings.ModelUnitSystem = r.UnitSystem.Feet
    index = {}

    def layer(full):
        if full in index:
            return index[full]
        parent = None
        for depth, name in enumerate(full.split("::")):
            path_ = "::".join(full.split("::")[:depth + 1])
            if path_ not in index:
                la = r.Layer()
                la.Name = name
                if parent is not None:
                    la.ParentLayerId = m.Layers[parent].Id
                index[path_] = m.Layers.Add(la)
            parent = index[path_]
        return index[full]

    def attrs(full, **user):
        a = r.ObjectAttributes()
        a.LayerIndex = layer(full)
        for k, v in user.items():
            a.SetUserString(k, v)
        return a
    lot = lookup_payload["writes"]["lot_ring"]
    m.Objects.AddPolyline(r.Polyline([r.Point3d(x, y, 0) for x, y in lot + lot[:1]]), attrs("Site"))
    m.Objects.AddBrep(r.Brep.CreateFromBoundingBox(r.BoundingBox(30, 20, 0, 50, 40, 30)), attrs(logic.MASSING))
    for o in logic.context_objects(payload):
        a = attrs(o["layer"], **{logic.CONTEXT_KEY: o["source"]})
        a.Name = o.get("name") or ""
        pts = [r.Point3d(x, y, 0) for x, y in o["points"]]
        if o["kind"] == "dot":
            m.Objects.AddTextDot(o.get("text") or "", pts[0], a)
        else:
            m.Objects.AddPolyline(r.Polyline(pts + pts[:1] if o["kind"] == "closed" else pts), a)
    m.Strings["Gordium\\" + logic.CONTEXT_ENTRY] = json.dumps(logic.context_record(payload, lookup_payload["writes"]["frame"]))
    m.Write(str(path), 8)
    return path


def test_the_saved_file_holds_nothing_from_a_live_only_source(tmp_path):
    """Read back from the .3dm: every object's source and user text, every point, every document string. Nothing of
    the footprints (store: none) is in it: no footprint corner, no footprint date, no object drawn from them."""
    payload, p = context_for()
    path = write_like_the_plugin(tmp_path / "m.3dm", p, payload)
    m = r.File3dm.Read(str(path))
    names = [la.FullPath for la in m.Layers]
    footprint_corners = {(round(x, 2), round(y, 2)) for ring in logic.context_guides(payload) for x, y in ring}
    raw = {k for k, e in ENDPOINTS.items() if e["store"] == "raw"}
    seen = 0
    for o in m.Objects:
        a = o.Attributes
        text = json.dumps(list(a.GetUserStrings() or ())) + (a.Name or "")
        assert T.STAND_IN_BUILDINGS_DATE not in text
        if logic.on_layer(names[a.LayerIndex], logic.CONTEXT):
            seen += 1
            assert a.GetUserString(logic.CONTEXT_KEY) in raw | {"gordium"}, a.GetUserString(logic.CONTEXT_KEY)
            g = o.Geometry
            pts = [(g.Point(i).X, g.Point(i).Y) for i in range(g.PointCount)] if isinstance(g, r.PolylineCurve) else \
                [(g.Point.X, g.Point.Y)] if isinstance(g, r.TextDot) else None
            assert pts is not None, type(g).__name__
            assert not ({(round(x, 2), round(y, 2)) for x, y in pts} & footprint_corners)
            if isinstance(g, r.TextDot):
                assert T.STAND_IN_BUILDINGS_DATE not in g.Text
    assert seen == len(logic.context_objects(payload)) == 229 + 38 + 6
    strings = [m.Strings[i] for i in range(len(m.Strings))]
    assert [k for k, _ in strings] == ["Gordium\\" + logic.CONTEXT_ENTRY]
    blob = json.dumps(strings)
    assert T.STAND_IN_BUILDINGS_DATE not in blob and '"ring"' not in blob and '"path"' not in blob
    numbers = {round(float(v), 2) for v in re.findall(r"-?\d+\.\d+", blob)}
    assert footprint_corners and not any(x in numbers and y in numbers for x, y in footprint_corners)


def test_the_checker_measures_the_same_with_or_without_the_context(tmp_path):
    """The lot and the house read from the saved file are the same whether the neighbourhood is drawn or not: 229
    closed parcel outlines beside the lot never become lot candidates, nothing on Gordium::Context is a building."""
    payload, p = context_for()
    facts = {"street_line": p["writes"]["street_line"], "corner_lot": False, "lot_surveyed": False,
             "ground_is_flat": True, "grade_elevation": 0}
    layers = {"lot": "Site", "building": logic.MASSING}
    with_context = read_site(write_like_the_plugin(tmp_path / "a.3dm", p, payload), facts, layers)
    without = read_site(write_like_the_plugin(tmp_path / "b.3dm", p, dict(payload, objects=[])), facts, layers)
    def no_ids(v):                                        # each written file gives its objects new ids
        if isinstance(v, dict):
            return {k: no_ids(x) for k, x in v.items() if k != "id"}
        return [no_ids(x) for x in v] if isinstance(v, list) else v
    assert with_context["problems"] == without["problems"] == []
    assert with_context["lot"]["edges"] and len(with_context["buildings"]) == 1
    assert no_ids(with_context["lot"]) == no_ids(without["lot"])
    assert no_ids(with_context["buildings"]) == no_ids(without["buildings"])


@pytest.mark.parametrize("layer", sorted(set(cb.LAYER_OF.values()) | {cb.NOTES, cb.ROOT}))
@pytest.mark.parametrize("kind", ["PolylineCurve", "NurbsCurve", "TextDot", "Brep", "Extrusion", "Mesh", "SubD",
                                  "InstanceReference", "Hatch"])
def test_the_checker_never_classifies_anything_on_the_context_layers(layer, kind):
    assert logic.classify(layer, kind) is None and logic.classify(layer, kind, holds_building=True) is None


def test_the_context_layers_sit_under_gordium_context_and_nowhere_the_checker_reads():
    for layer in set(cb.LAYER_OF.values()) | {cb.NOTES}:
        assert logic.on_layer(layer, logic.CONTEXT) and cb.ROOT == logic.CONTEXT
        assert not any(logic.on_layer(layer, x) for x in (logic.LAYERS["lot"], logic.LAYERS["building"], logic.MASSING))


def test_a_context_layer_holding_a_block_of_buildings_is_still_ignored():
    """Pinned against revert of classify's context branch: without it, a block placed on a context layer that holds
    building objects would be a problem sentence for the checker (and a parcel curve could be read anywhere the
    lot layer's name is reused)."""
    assert logic.classify(logic.CONTEXT + "::Parcels", "InstanceReference", holds_building=True) is None


# ---- review round 1 ---------------------------------------------------------------------------------------------

def test_the_lot_is_left_out_by_its_parcel_id_not_by_its_centroid():
    """A concave lot's centroid can sit in a neighbour: the lot is left out by the lookup's parcel id. Given another
    parcel's id, that one is left out and the lot's own parcel (under the centroid) is drawn: the id decides."""
    frame = looked_up()["writes"]["frame"]
    http = lambda: T.Fake(T.load("106_ithaca_rd"), context=T.load("106_ithaca_rd_context"))   # noqa: E731
    ids = {o["name"] for o in cb.fetch(frame, http(), now=T.NOW)["objects"] if o["layer"] == cb.LAYER_OF["parcels"]}
    assert len(ids) == 229 and "500700-84.-2-6" not in ids
    other = sorted(ids)[0]
    moved = {o["name"] for o in cb.fetch(dict(frame, parcel_id=other), http(), now=T.NOW)["objects"]
             if o["layer"] == cb.LAYER_OF["parcels"]}
    assert other not in moved and "500700-84.-2-6" in moved


def test_the_neighbourhood_is_drawn_only_around_the_lot_the_lookup_drew():
    """Review round 1: an earlier address's frame stayed for a lot the architect then drew or picked (settle), or
    after a lookup that couldn't place its lot (no frame): its neighbourhood was drawn around the wrong lot."""
    frame = looked_up()["writes"]["frame"]
    saved = {"lookup_frame": frame, "replaceable_lot": "lot-1"}
    assert logic.context_frame({"lot_id": "lot-1"}, saved) == frame
    assert logic.context_frame({"lot_id": "lot-2"}, saved) is None                      # another lot now
    assert logic.context_frame({"lot_id": "lot-1"}, logic.settle(saved, "lot")) is None   # the architect's own
    assert logic.context_frame({"lot_id": "lot-1"}, dict(saved, lookup_frame=None)) is None
    assert logic.context_frame({}, saved) is None and logic.context_frame(None, None) is None


def test_every_draw_of_a_box_brings_the_neighbourhood_in_line_with_the_lot():
    """Review round 2: an Edit site… lookup (the box in check mode) and GordiumStart's early returns replaced the lot
    and left the earlier address's neighbourhood. Now the box itself, after any Draw, runs sync_context."""
    conf = RHINO[RHINO.index("def confirm("):RHINO.index("def _confirm(")]
    assert 'logic.guard(sync_context, "draw the neighbourhood")(doc, result)' in conf
    assert conf.index("gate.leave()") < conf.index("sync_context")
    start = RHINO[RHINO.index("def gordium_start("):RHINO.index("\n# ---- the context map")]
    assert "_clear_context" not in start and "draw_context" not in start      # one way only: through the box
    sync = RHINO[RHINO.index("def sync_context("):RHINO.index("def _context_visible(")]
    assert "logic.context_step(frame, drawn, STATE.get(\"context_on\", True))" in sync
    assert "frame = logic.context_frame(facts, _ui_state(doc))" in sync
    assert 'say("Neighbourhood not drawn: Show neighbourhood is off' in sync                 # never silently skipped
    show = RHINO[RHINO.index("def show_context("):RHINO.index("def _doc_name(")]
    assert "draw_context(doc, logic.context_frame(facts, _ui_state(doc)))" in show


def test_what_a_draw_does_to_the_neighbourhood():
    a, b = {"origin_epsg2261_us_survey_ft": [1, 2], "shift_ft": [0, 0], "rotation_deg": 0}, \
        {"origin_epsg2261_us_survey_ft": [3, 4], "shift_ft": [0, 0], "rotation_deg": 0}
    assert logic.context_step(a, None, True) == "draw"             # a looked-up lot, nothing drawn yet
    assert logic.context_step(b, a, True) == "draw"                # another address: the earlier one goes
    assert logic.context_step(a, a, True) == "keep"                # the same lot (Edit site… without a lookup)
    assert logic.context_step(None, a, True) == "clear"            # the architect's own lot now
    assert logic.context_step(None, None, True) == "keep"
    assert logic.context_step(b, a, False) == "off"                # the tick off: cleared, and said
    payload, p = context_for()
    rec = logic.context_record(payload, p["writes"]["frame"])
    assert rec["frame"] == p["writes"]["frame"] and rec["fingerprint"] == payload["snapshot"]["fingerprint"]


def test_the_footprints_carry_their_source_line_when_shown():
    payload, _ = context_for()
    said = logic.context_says(payload)
    assert "Building footprints: NYS ITS Geospatial Services (NYSERDA/CIESIN; Tompkins County ITS GIS Division)" in said
    assert payload["live_credits"] and all("Building footprints" in c for c in payload["live_credits"])


def test_clearing_reaches_hidden_and_locked_context_layers_and_only_gordiums_objects():
    """Review round 1: Delete without ignoring modes leaves objects on a hidden layer (one hidden in an earlier
    session), so the context was drawn twice. Each layer is shown and unlocked first, then put back."""
    body = RHINO[RHINO.index("def _clear_context("):RHINO.index("def _context_payload(")]
    show, unlock, delete = (body.index(s) for s in ("IsVisible = True", "IsLocked = False", "doc.Objects.Delete("))
    assert show < delete and unlock < delete
    assert body.index("IsVisible = was") > delete and body.index("IsLocked = True") > delete
    assert "if o.Attributes.GetUserString(logic.CONTEXT_KEY):" in body                  # never the architect's own
    assert "doc.Strings.Delete(SECTION, logic.CONTEXT_ENTRY)" in body and 'STATE.pop("context_guides"' in body
    vis = RHINO[RHINO.index("def _context_visible("):RHINO.index("def show_context(")]
    assert "for i in indexes:" in vis                                                    # every sublayer too


def test_the_tick_starts_as_it_was_last_set():
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    box = ui[ui.index("def _context_box("):ui.index("def _envelope_box(")]
    assert "box.Checked = bool(on)" in box and box.index("box.Checked") < box.index("CheckedChanged")
    assert "_context_box(actions, context_on)" in ui and "def make_panel(actions, context_on=True):" in ui
    assert 'ui.make_panel(_actions(), context_on=STATE.get("context_on", True))' in RHINO


def test_the_quickstart_says_how_footprints_come_back_after_reopening():
    guide = (REPO / "apps/rhino_plugin/QUICKSTART.md").read_text(encoding="utf-8")
    assert "fetched again when you reopen" not in guide
    assert "untick and tick **Show neighbourhood** to fetch them again" in guide


# ---- the Rhino side, by its code (it can't run in CI) ------------------------------------------------------------

def test_the_plugin_writes_only_context_objects_and_keeps_guides_on_screen():
    body = RHINO[RHINO.index("def draw_context("):RHINO.index("def _context_visible(")]
    assert "for o in logic.context_objects(payload):" in body
    assert body.count("doc.Objects.Add") == 2                            # a dot or a curve, per context object
    assert 'STATE["context_guides"] = ' in body and "logic.context_guides(payload)" in body
    assert "doc.Strings.SetString(SECTION, logic.CONTEXT_ENTRY, json.dumps(logic.context_record(payload, frame)))" in body
    assert "attrs.SetUserString(logic.CONTEXT_KEY, o[\"source\"])" in body
    assert "_lock_context(doc, True)" in body                            # locked: not selectable, can't be moved
    # live mode hears each add; the context changes nothing checked, so no re-check is set off by it
    assert body.index('dirty = STATE.get("dirty")') < body.index("_clear_context(doc)") < \
        body.index('STATE["dirty"] = dirty')
    scene = RHINO[RHINO.index("def draw_scene("):RHINO.index("def draw_screen(")]
    assert 'STATE.get("context_guides")' in scene and "DrawPolyline" in scene


def test_the_plugin_draws_the_context_after_a_box_draw_guarded_and_has_a_tick():
    conf = RHINO[RHINO.index("def confirm("):RHINO.index("def _confirm(")]
    assert 'logic.guard(sync_context, "draw the neighbourhood")(doc, result)' in conf
    sync = RHINO[RHINO.index("def sync_context("):RHINO.index("def _context_visible(")]
    assert "draw_context(doc, frame)" in sync
    assert '"context": show_context' in RHINO
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    assert re.search(r'CheckedChanged \+= logic\.guard\(lambda s, e: actions\["context"\]', ui)
    greyed = ui[ui.index('parts["greyed"] = ['):].split("\n", 1)[0]
    assert "context_tick" in greyed                                      # off while a start box is open


def test_the_panel_says_what_was_drawn():
    payload, _ = context_for()
    said = logic.context_says(payload)
    assert said.startswith("Neighbourhood drawn: 229 neighbouring parcels and 38 street lines")
    assert "212 building footprints shown live (not saved)" in said
    assert logic.context_says({"status": "offline", "message": "Couldn't fetch the neighbourhood: x"}).endswith(": x")
    assert logic.context_says(None).startswith("Couldn't fetch")


def test_context_box_runs_as_its_own_process_on_the_recorded_answers():
    frame = looked_up()["writes"]["frame"]
    args = logic.context_command(sys.executable, frame, "106_ithaca_rd")
    out = subprocess.run(args, cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=120)
    p = json.loads(out.stdout.strip().splitlines()[-1])
    assert p["status"] == "found" and p["counts"] == {"parcels": 229, "streets": 38, "buildings": 212}


def test_context_box_never_prints_a_traceback():
    out = subprocess.run([sys.executable, "-m", "design_checker.context_box", "--origin", "1", "2", "--rotation", "0",
                          "--shift", "0", "0", "--fixture", "no_such_fixture"], cwd=REPO, capture_output=True,
                         text=True, encoding="utf-8", timeout=120)
    p = json.loads(out.stdout.strip().splitlines()[-1])
    assert p["status"] == "error" and p["objects"] == [] and "Traceback" not in out.stdout
