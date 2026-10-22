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

@pytest.fixture
def live_footprints(monkeypatch):
    """The footprints as a source that may not be kept (store: none), as they were until Ben's decision of 2026-10-21
    (now kept, as editable outlines). The live-only machinery stays for any such source: these tests pin it."""
    monkeypatch.setitem(ENDPOINTS["state_buildings"], "store", "none")


def test_the_footprints_layer_is_really_unlocked_its_parent_too():
    """Review of the editable outlines, P1: the parent Gordium::Context was locked, and in Rhino a locked parent locks
    its sublayers' objects: the footprints couldn't be dragged. Only the leaf layers are locked now."""
    assert not logic.context_locked(logic.CONTEXT) and not logic.context_locked(logic.CONTEXT + "::Buildings")
    assert all(logic.context_locked(logic.CONTEXT + "::" + n) for n in ("Parcels", "Streets", "Notes"))
    assert not logic.context_locked("Gordium") and not logic.context_locked("Site")


def test_the_footprints_are_kept_as_editable_outlines_on_their_own_layer():
    """Ben, 2026-10-21: the footprints are always drawn as real outlines (curves, no invented heights) on an
    unlocked Gordium::Context::Buildings layer, each with its id; none is a guide."""
    payload, _ = context_for()
    assert payload["counts"] == {"parcels": 229, "streets": 38, "buildings": 322}
    feet = [o for o in logic.context_objects(payload) if o["source"] == "state_buildings"]
    assert len(feet) == 322 and logic.context_guides(payload) == []
    assert all(o["layer"] == cb.LAYER_OF["buildings"] == logic.CONTEXT + "::Buildings" and o["kind"] == "closed"
               and o["id"].startswith("footprint-") for o in feet)
    assert not logic.context_locked(cb.LAYER_OF["buildings"])                  # left unlocked: drag and edit them
    assert all(logic.context_locked(cb.LAYER_OF[n]) for n in ("parcels", "streets")) and logic.context_locked(cb.NOTES)


def test_an_outline_the_architect_edited_is_known_and_never_drawn_twice():
    """Ben, 2026-10-21: Gordium's redraw or clear removes only outlines it drew that the architect hasn't edited. Each
    outline carries the fingerprint of its points (Z too) and of the attributes an architect can change: moved in any
    direction, reshaped, renamed or recoloured, it no longer matches (review of the editable outlines, P1)."""
    drawn = [(0.0, 0.0, 0.0), (30.0, 0.0, 0.0), (30.0, 40.0, 0.0), (0.0, 40.0, 0.0), (0.0, 0.0, 0.0)]
    attrs = {"name": "footprint-1", "colour_source": 0, "colour": -16777216, "linetype_source": 0, "linetype": -1,
             "user": []}
    key = logic.outline_key(drawn, attrs)
    assert not logic.is_edited(key, drawn, attrs) and not logic.is_edited(key, [(x + 1e-9, y, z) for x, y, z in drawn], attrs)
    assert logic.is_edited(key, [(x + 2.0, y, z) for x, y, z in drawn], attrs)            # dragged 2 units
    assert logic.is_edited(key, drawn[:2] + [(30.0, 45.0, 0.0)] + drawn[3:], attrs)      # one corner moved
    assert logic.is_edited(key, [(x, y, z + 3.0) for x, y, z in drawn], attrs)            # moved up to the terrain
    assert logic.is_edited(key, drawn, dict(attrs, name="4 storeys"))                     # renamed
    assert logic.is_edited(key, drawn, dict(attrs, colour_source=1, colour=-65536))       # recoloured
    assert logic.is_edited(key, drawn, dict(attrs, user=[["storeys", "4"]]))              # their own note
    assert not logic.is_edited(None, [(5.0, 5.0, 0.0)]) and not logic.is_edited("", drawn)   # not one Gordium drew
    objects = [{"id": "footprint-1"}, {"id": "footprint-2"}, {"id": ""}, {"name": "North"}]
    assert logic.skip_edited(objects, ["footprint-2", ""]) == [{"id": "footprint-1"}, {"id": ""}, {"name": "North"}]
    show = RHINO[RHINO.index("def _outline_points("):RHINO.index("def _attrs_print(")]
    assert "(q.X, q.Y, q.Z)" in show


# every attribute Rhino gives an outline (as _attrs_print reads them by reflection), and the two it adds
ATTRIBUTES = {"Name": "footprint-1", "ColorSource": "ColorFromLayer", "ObjectColor": "Color [A=255, R=0, G=0, B=0]",
              "LinetypeSource": "LinetypeFromLayer", "LinetypeIndex": "-1", "PlotColorSource": "PlotColorFromLayer",
              "PlotColor": "Color [A=255, R=0, G=0, B=0]", "PlotWeightSource": "PlotWeightFromLayer",
              "PlotWeight": "0.0", "MaterialSource": "MaterialFromLayer", "MaterialIndex": "-1", "Mode": "Normal",
              "Visible": "True", "WireDensity": "1", "DisplayOrder": "0", "LayerIndex": "7",
              "ObjectDecoration": "None", "Url": "", "groups": [], "user": []}


def test_changing_any_attribute_or_copying_keeps_the_outline_and_only_gordiums_own_go():
    """Review of the editable outlines, round 2: a listed handful of attributes missed print width and colour,
    material and groups, and a copy pasted in place (same points, same attributes) was deleted. Now every attribute
    is fingerprinted, and a clear deletes only an object that is exactly what Gordium drew."""
    drawn = [(0.0, 0.0, 0.0), (30.0, 0.0, 0.0), (30.0, 40.0, 0.0), (0.0, 0.0, 0.0)]
    key = logic.outline_key(drawn, ATTRIBUTES)
    assert not logic.kept_on_clear(key, "A", "A", drawn, dict(ATTRIBUTES))             # untouched: Gordium's, goes
    for name in ATTRIBUTES:                                                              # any one change: theirs
        changed = dict(ATTRIBUTES, **{name: [7] if name == "groups" else [["k", "v"]] if name == "user" else "changed"})
        assert logic.kept_on_clear(key, "A", "A", drawn, changed), name
    assert logic.kept_on_clear(key, "A", "B", drawn, dict(ATTRIBUTES))                  # a copy pasted in place
    assert logic.kept_on_clear(key, None, "B", drawn, dict(ATTRIBUTES))                 # no record of being drawn
    assert not logic.kept_on_clear(None, None, "C", None, {})                           # a note: Gordium's, goes
    assert not logic.attribute_counts("UserStringCount") and logic.attribute_counts("PlotWeight")
    assert logic.attribute_text(0.1 + 0.2) == logic.attribute_text(0.3)                 # stable text
    att = RHINO[RHINO.index("def _attrs_print("):].split("\ndef ", 1)[0]
    assert "attrs.GetType().GetProperties()" in att and "logic.attribute_counts(prop.Name)" in att
    assert "attrs.GetGroupList()" in att and 'startswith("gordium_")' in att
    clear = RHINO[RHINO.index("def _clear_context("):RHINO.index("def _edited_pieces(")]
    kept = clear.index("if logic.kept_on_clear(o.Attributes.GetUserString(logic.GEOM_KEY), o.Attributes.GetUserString(")
    assert "logic.DRAWN_KEY), str(o.Id), _outline_points(o.Geometry), _attrs_print(o.Attributes)):" in clear
    assert kept < clear.index('attrs.SetUserString(logic.EDITED_KEY, "1")') < clear.index("doc.Objects.Delete(o, True)")


class _Prop:
    """A .NET PropertyInfo as pythonnet hands it to the plugin (Name, CanRead, GetIndexParameters, GetValue)."""

    def __init__(self, name, read=None, can_read=True, indexed=False):
        self.Name, self.CanRead, self._read, self._indexed = name, can_read, read, indexed

    def GetIndexParameters(self):
        return type("P", (), {"Length": 1 if self._indexed else 0})()

    def GetValue(self, obj, index):
        assert index is None
        return self._read(obj)


class _NetObject:
    """A .NET object without its own ToString: str() is its type name, the same on every read."""

    def __str__(self):
        return "Rhino.Render.Decals"


class _Attrs:
    """ObjectAttributes as the plugin reads them in Rhino: reflection over the real kinds of property (an id, a
    document flag, an object reference, one Rhino throws on, an indexed one, a write-only one) and Gordium's own keys
    counted in UserStringCount."""

    def __init__(self, obj_id="5d2c-own", plot_weight=0.0, groups=None):
        self.obj_id, self.plot_weight, self.groups = obj_id, plot_weight, groups
        self.strings = {"gordium_context": "state_buildings", "gordium_context_id": "footprint-1"}
        self.decals = _NetObject()

    def GetType(self):
        def boom(a):
            raise RuntimeError("TargetInvocationException: not readable here")
        props = [_Prop("ObjectId", lambda a: a.obj_id), _Prop("IsDocumentControlled", lambda a: True),
                 _Prop("PlotWeight", lambda a: a.plot_weight), _Prop("Decals", lambda a: a.decals),
                 _Prop("UserStringCount", lambda a: len(a.strings)), _Prop("CustomMeshingParameters", boom),
                 _Prop("Item", lambda a: 1 / 0, indexed=True), _Prop("WriteOnly", lambda a: 1 / 0, can_read=False)]
        return type("T", (), {"GetProperties": staticmethod(lambda: props)})()

    def GetGroupList(self):
        return self.groups                       # None when the object is in no group, as RhinoCommon gives it

    def GetUserStrings(self):
        return type("NV", (), {"AllKeys": list(self.strings)})()

    def GetUserString(self, k):
        return self.strings.get(k)


def test_the_attribute_fingerprint_is_stable_in_rhino_and_sees_print_width_and_groups():
    """Review of the editable outlines, round 3 (finishing round 2): _attrs_print run as written, over attributes
    shaped like RhinoCommon's. Reading them again after Gordium writes its own keys (the user-string count grows)
    gives the same fingerprint, so an untouched outline is Gordium's; a property Rhino throws on, an indexed or a
    write-only one is left out; a print width or a group is an edit."""
    src = RHINO[RHINO.index("def _attrs_print("):].split("\ndef ", 1)[0]
    ns = {"logic": logic}
    exec(src, ns)
    attrs_print = ns["_attrs_print"]
    pts = [(0.0, 0.0, 0.0), (30.0, 0.0, 0.0), (30.0, 40.0, 0.0), (0.0, 0.0, 0.0)]
    a = _Attrs()
    key = logic.outline_key(pts, attrs_print(a))                       # as draw_context fingerprints it
    a.strings.update({logic.GEOM_KEY: key, logic.DRAWN_KEY: "5d2c-own"})   # then writes its own keys
    first = attrs_print(a)
    assert set(first) == {"ObjectId", "IsDocumentControlled", "PlotWeight", "Decals", "groups", "user"}
    assert first["user"] == [] and first["groups"] == [] and first["Decals"] == "Rhino.Render.Decals"
    assert not logic.kept_on_clear(key, "5d2c-own", "5d2c-own", pts, attrs_print(a))   # untouched: Gordium's
    a.plot_weight = 0.35                                                                # a print width set
    assert logic.kept_on_clear(key, "5d2c-own", "5d2c-own", pts, attrs_print(a))
    b = _Attrs(groups=[3])                                                              # grouped with their linework
    b.strings.update({logic.GEOM_KEY: key, logic.DRAWN_KEY: "5d2c-own"})
    assert logic.kept_on_clear(key, "5d2c-own", "5d2c-own", pts, attrs_print(b))
    c = _Attrs()
    c.strings["storeys"] = "4"                                                          # their own user text
    assert logic.kept_on_clear(key, "5d2c-own", "5d2c-own", pts, attrs_print(c))
    check = (REPO / "apps/rhino_plugin/tests/context_in_rhino.py").read_text(encoding="utf-8")
    assert "a copy pasted in place and a footprint given a print width are the architect's" in check  # Rhino proves it


def test_only_the_very_outline_edited_around_this_lot_is_kept_from_a_redraw():
    """Review of the editable outlines, P2: skipping by id alone hid unedited neighbours. A copy the architect moved
    carries the original's id (Rhino copies user text) but not as its own object id: it never hides the original. An
    outline kept from another address was drawn for another lot: it never hides this square's footprint. And each
    ring has its own id, so one edited ring never hides its siblings."""
    here, there = logic.frame_key({"origin": [1, 2]}), logic.frame_key({"origin": [3, 4]})
    assert here != there and here == logic.frame_key({"origin": [1, 2]})
    moved = {"id": "footprint-1", "frame": here, "drawn_as": "A", "own": "A"}           # the outline itself, moved
    copy = {"id": "footprint-2", "frame": here, "drawn_as": "B", "own": "C"}            # a copy of footprint-2
    elsewhere = {"id": "footprint-3", "frame": there, "drawn_as": "D", "own": "D"}      # kept from another address
    assert logic.suppressed([moved, copy, elsewhere], here) == ["footprint-1"]
    objects = [{"id": "footprint-1"}, {"id": "footprint-2"}, {"id": "footprint-3"}]
    assert logic.skip_edited(objects, logic.suppressed([moved, copy, elsewhere], here)) == objects[1:]
    draw = RHINO[RHINO.index("def draw_context("):RHINO.index("def sync_context(")]
    assert "edited = logic.suppressed(_edited_pieces(doc), here)" in draw
    assert "attrs.SetUserString(logic.FRAME_KEY, here)" in draw
    assert "marked.SetUserString(logic.DRAWN_KEY, str(added.Id))" in draw
    pieces = RHINO[RHINO.index("def _edited_pieces("):RHINO.index("def _context_record(")]
    assert '"own": str(o.Id)' in pieces and "logic.DRAWN_KEY" in pieces and "logic.FRAME_KEY" in pieces
    from site_lookup import context as site_context                      # each ring its own id
    feet = lambda p: [round(p[0], 2), round(p[1], 2)]                    # noqa: E731
    two = [{"attributes": {"OBJECTID": 7}, "geometry": {"rings": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                                                                  [[20, 0], [30, 0], [30, 10], [20, 10], [20, 0]]]}}]
    ids = [i["id"] for i in site_context._items("buildings", two, (-100, -100, 100, 100), (0, 0), feet)]
    assert ids == ["footprint-7", "footprint-7 #2"]
    parcel = [{"attributes": {"SWIS": "500700", "PRINT_KEY": "1"}, "geometry": two[0]["geometry"]}]
    pids = [i["id"] for i in site_context._items("parcels", parcel, (-100, -100, 100, 100), (50, 50), feet, "x")]
    assert pids == ["500700-1", "500700-1 #2"]


def test_the_plugin_keeps_an_edited_outline_as_the_architects_and_marks_every_outline():
    clear = RHINO[RHINO.index("def _clear_context("):RHINO.index("def _edited_pieces(")]
    edited = clear.index("if logic.kept_on_clear(o.Attributes.GetUserString(logic.GEOM_KEY)")
    assert "_attrs_print(o.Attributes)" in clear[edited:edited + 250]
    assert edited < clear.index("attrs.SetUserString(logic.CONTEXT_KEY, None)") < clear.index("doc.Objects.Delete(o, True)")
    assert 'attrs.SetUserString(logic.EDITED_KEY, "1")' in clear      # theirs now: no later clear touches it
    draw = RHINO[RHINO.index("def draw_context("):RHINO.index("def sync_context(")]
    # fingerprinted after it is added, as Rhino holds it (points, Z, attributes)
    added = draw.index("added = doc.Objects.FindId(doc.Objects.AddCurve(curve, attrs))")
    assert added < draw.index("marked.SetUserString(logic.GEOM_KEY, logic.outline_key(_outline_points(added.Geometry),")
    assert 'attrs.SetUserString(logic.PIECE_KEY, o["id"])' in draw
    lock = RHINO[RHINO.index("def _lock_context("):RHINO.index("def _outline_points(")]
    assert "logic.context_locked(doc.Layers[i].FullPath)" in lock
    assert '"Buildings": (135, 135, 135)' in RHINO


def test_a_solid_on_the_neighbourhood_layers_over_the_lot_makes_the_check_need_review():
    """Review of the editable outlines, P0: a solid on the (now unlocked) footprints' layer over the lot was never
    measured and only said once; the check could still say comply. Now it is a left-out object like any other
    (found with reaches_into_lot, every kind blocks included): the review row stays until it is moved."""
    assert logic.left_out_candidate(logic.CONTEXT + "::Buildings") and logic.left_out_candidate(logic.CONTEXT)
    assert logic.left_out_candidate("Default") and logic.left_out_candidate("Site::Sheds")
    assert not logic.left_out_candidate(logic.MASSING) and not logic.left_out_candidate(logic.HOLDING_LAYER)
    assert not logic.left_out_candidate("Gordium::Grade")
    assert logic.context_left_out({"a": logic.CONTEXT + "::Buildings", "b": "Default", "c": None}) == ["a"]
    body = RHINO[RHINO.index("def _not_included("):].split("\ndef ", 1)[0]
    assert "or not logic.left_out_candidate(layer):" in body and 'logic.on_layer(layer, "Gordium")' not in body
    assert "logic.reaches_into_lot(ring, _plan_points(g), reach, box)" in body           # the lot's outline, not a centre
    extras = RHINO[RHINO.index("def _extras("):].split("\ndef ", 1)[0]
    assert '"context_left_out": logic.context_left_out(' in extras
    assert "_note_context_solids" not in RHINO and not hasattr(logic, "context_solids_says")
    for kind in ("Brep", "Extrusion", "Mesh", "SubD"):                     # and the checker still never measures it
        assert logic.classify(logic.CONTEXT + "::Buildings", kind) is None


def test_only_storable_sources_become_objects_and_the_footprints_are_guides(live_footprints):
    payload, _ = context_for()
    assert payload["counts"] == {"parcels": 229, "streets": 38, "buildings": 322}
    sources = {o["source"] for o in logic.context_objects(payload)}
    assert sources == {"state_parcels", "state_streets", "gordium"}
    assert all(ENDPOINTS[s]["store"] == "raw" for s in sources - {"gordium"})
    assert len(logic.context_guides(payload)) == 322 and not any(o["source"] == "state_buildings" for o in payload["objects"])


def test_an_object_from_a_live_only_source_is_never_written_whatever_the_payload_says(live_footprints):
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
        if o["kind"] in ("dot", "text"):          # (the plugin writes "text" as model text; its words are what count)
            m.Objects.AddTextDot(o.get("text") or "", pts[0], a)
        else:
            m.Objects.AddPolyline(r.Polyline(pts + pts[:1] if o["kind"] == "closed" else pts), a)
    m.Strings["Gordium\\" + logic.CONTEXT_ENTRY] = json.dumps(logic.context_record(payload, lookup_payload["writes"]["frame"]))
    m.Write(str(path), 8)
    return path


def test_the_saved_file_holds_nothing_from_a_live_only_source(tmp_path, live_footprints):
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
        assert "footprints dated" not in text
        if logic.on_layer(names[a.LayerIndex], logic.CONTEXT):
            seen += 1
            assert a.GetUserString(logic.CONTEXT_KEY) in raw | {"gordium"}, a.GetUserString(logic.CONTEXT_KEY)
            g = o.Geometry
            pts = [(g.Point(i).X, g.Point(i).Y) for i in range(g.PointCount)] if isinstance(g, r.PolylineCurve) else \
                [(g.Point.X, g.Point.Y)] if isinstance(g, r.TextDot) else None
            assert pts is not None, type(g).__name__
            assert not ({(round(x, 2), round(y, 2)) for x, y in pts} & footprint_corners)
            if isinstance(g, r.TextDot):
                assert "footprints dated" not in g.Text
    assert seen == len(logic.context_objects(payload)) == 229 + 38 + 6
    strings = [m.Strings[i] for i in range(len(m.Strings))]
    assert [k for k, _ in strings] == ["Gordium\\" + logic.CONTEXT_ENTRY]
    blob = json.dumps(strings)
    assert "footprints dated" not in blob and '"ring"' not in blob and '"path"' not in blob
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
    # review round 3: the sample lot added to an emptied model kept an earlier lookup's frame
    assert logic.context_frame({"lot_id": "lot-1"}, dict(saved, from_sample=True)) is None


def test_a_draw_on_the_same_lot_brings_back_what_a_reopened_file_lost_and_says_every_removal():
    """Review round 3: in a reopened file the footprints (never saved) weren't fetched again on Draw, and a hidden
    context layer stayed hidden with the tick on; the "clear" step removed the neighbourhood without a word."""
    sync = RHINO[RHINO.index("def sync_context("):RHINO.index("def _context_visible(")]
    keep = sync[sync.index('if step == "keep" and frame and on and refetch:'):sync.index('if step in ("clear"')]
    assert "draw_context(doc, frame)" in keep and "_clear_context" not in keep    # offline keeps what is saved
    draw = RHINO[RHINO.index("def draw_context("):RHINO.index("def sync_context(")]
    assert draw.index('if payload.get("status") != "found":') < draw.index("_clear_context(doc, sources)")
    assert 'say("Neighbourhood removed: it is drawn only around a lot the start box looked up.")' in sync
    assert "_context_visible(doc, True)" in sync


def test_every_draw_of_a_box_brings_the_neighbourhood_in_line_with_the_lot():
    """Review round 2: an Edit site… lookup (the box in check mode) and GordiumStart's early returns replaced the lot
    and left the earlier address's neighbourhood. Now the box itself, after any Draw, runs sync_context."""
    conf = RHINO[RHINO.index("def confirm("):RHINO.index("def _confirm(")]
    assert 'logic.guard(sync_context, "draw the neighbourhood")(doc, result)' in conf
    assert conf.index("gate.leave()") < conf.index("sync_context")
    start = RHINO[RHINO.index("def gordium_start("):RHINO.index("\n# ---- the context map")]
    assert "_clear_context" not in start and "draw_context" not in start      # one way only: through the box
    sync = RHINO[RHINO.index("def sync_context("):RHINO.index("def _context_visible(")]
    assert "step = logic.context_step(frame, drawn, on)" in sync
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


def test_live_only_footprints_are_credited_on_the_drawing_and_their_date_said_on_screen_only(live_footprints):
    """Architect review of PR #23: the panel's line listed agencies and storage rules. Who made the footprints is on
    the drawing's Sources note (Gordium's own attribution text, endpoints.yaml: it may be kept); a live-only source's
    date is said in the panel's short line only, never in the file (it is that source's data: store none)."""
    payload, _ = context_for()
    note = " ".join(next(o for o in payload["objects"] if o["name"] == "Sources")["text"].split("\n"))
    assert "%s: %s" % (ENDPOINTS["state_buildings"]["attribution"], logic.LIVE_ONLY) in note
    assert "footprints dated" not in note and "2014" not in note           # the date never reaches the saved note
    said = logic.context_says(payload)
    assert "NYSERDA" not in said and "Geospatial" not in said and "kept in this file" not in said
    assert "(footprints from 2014, shown only)" in said


def test_kept_footprints_carry_their_date_on_the_drawing():
    """Kept since Ben's decision: who made them and their date are on the Sources note; the line says the date
    without "shown only"."""
    payload, _ = context_for()
    note = " ".join(next(o for o in payload["objects"] if o["name"] == "Sources")["text"].split("\n"))
    assert ENDPOINTS["state_buildings"]["attribution"] in note and "footprints dated 2014" in note
    assert logic.LIVE_ONLY not in note
    assert logic.context_says(payload).endswith("322 buildings (footprints from 2014).")


def test_clearing_reaches_hidden_and_locked_context_layers_and_only_gordiums_objects():
    """Review round 1: Delete without ignoring modes leaves objects on a hidden layer (one hidden in an earlier
    session), so the context was drawn twice. Each layer is shown and unlocked first, then put back."""
    body = RHINO[RHINO.index("def _clear_context("):RHINO.index("def _context_payload(")]
    show, unlock, delete = (body.index(s) for s in ("IsVisible = True", "IsLocked = False", "doc.Objects.Delete("))
    assert show < delete and unlock < delete
    assert body.index("IsVisible = was") > delete
    assert body.index("IsLocked = logic.context_locked(doc.Layers[i].FullPath)") > delete   # all but the footprints
    assert "if not source or (sources is not None and source not in sources):" in body   # never the architect's own
    assert "doc.Strings.Delete(SECTION, logic.CONTEXT_ENTRY)" in body and 'STATE.pop("context_guides"' in body
    vis = RHINO[RHINO.index("def _context_visible("):RHINO.index("def show_context(")]
    assert "for i in indexes:" in vis                                                    # every sublayer too


def test_the_tick_is_kept_per_file_like_the_labels_tick():
    """Coordinator's decision (2026-10-21): Show neighbourhood is kept per file, in the document's Gordium settings,
    like Show on-screen labels (an architect reopening a file expects the same view); it was per Rhino session."""
    assert logic.context_shown({}) is True and logic.context_shown(None) is True          # on unless unticked
    assert logic.context_shown({"show_context": False}) is False
    assert logic.storable_ui({"show_context": False})["show_context"] is False            # it is written to the file
    show = RHINO[RHINO.index("def show_context("):RHINO.index("def _doc_name(")]
    assert "_save_ui_state(doc, dict(_ui_state(doc), show_context=bool(on)))" in show
    on = RHINO[RHINO.index("def _context_on("):RHINO.index("def _context_visible(")]
    assert "logic.context_shown(_ui_state(doc))" in on
    assert 'STATE["context_on"]' not in RHINO and 'STATE.get("context_on"' not in RHINO   # never per session again
    # the panel, both ways it is made (docked, the default; floating when it can't be), and every check after a
    # document switch or a reopen: the tick as this document has it
    assert 'ui.make_panel(_actions(), ui.DockHost(dock, host), context_on=_context_on(doc))' in RHINO
    assert 'ui.make_panel(_actions(), context_on=_context_on(doc))' in RHINO and RHINO.count("ui.make_panel(") == 2
    assert 'ui.set_context_tick(STATE.get("panel_parts"), _context_on(doc))' in RHINO
    scene = RHINO[RHINO.index("def draw_scene("):RHINO.index("def draw_screen(")]
    assert '(STATE.get("context_by_doc") or {}).get(e.RhinoDoc.RuntimeSerialNumber, True)' in scene
    sync = RHINO[RHINO.index("def sync_context("):RHINO.index("def _context_on(")]
    assert "on = _context_on(doc)" in sync
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    box = ui[ui.index("def _context_box("):ui.index("def set_context_tick(")]
    assert "box.Checked = bool(on)" in box and box.index("box.Checked") < box.index("CheckedChanged")
    assert 'if not parts.get("_setting_context"):' in box                                # set from the file: no fetch
    tick = ui[ui.index("def set_context_tick("):].split("\ndef ", 1)[0]
    assert 'parts["_setting_context"] = True' in tick and 'parts["_setting_context"] = False' in tick
    check = (REPO / "apps/rhino_plugin/tests/context_tick_in_rhino.py").read_text(encoding="utf-8")
    assert "5 the tick is kept in the file" in check and "g.logic.context_shown(g._ui_state(doc))" in check


def test_the_quickstart_says_the_footprints_are_kept_and_editable():
    guide = (REPO / "apps/rhino_plugin/QUICKSTART.md").read_text(encoding="utf-8")
    assert "drawn on screen only" not in guide and "to fetch them again" not in guide     # no longer live-only
    assert "unlocked `Gordium::Context::Buildings` layer" in guide and "an outline you edit is yours" in guide


def test_clearing_also_opens_a_locked_or_hidden_parent_layer_and_says_before_waiting():
    """Review round 4: a locked or hidden "Gordium" layer holds its sublayers' objects too (the delete skipped them,
    and the neighbourhood was drawn twice); and Rhino waited for the fetch without a word."""
    body = RHINO[RHINO.index("def _clear_context("):RHINO.index("def _context_payload(")]
    assert "ParentLayerId" in body and "for i in indexes + [k for k, _, _ in parents]:" in body
    assert body.index("for i in indexes + [k for k, _, _ in parents]:") < body.index("doc.Objects.Delete(")
    assert body.index("doc.Objects.Delete(") < body.index("doc.Layers[k].IsLocked = was_locked")
    fetch = RHINO[RHINO.index("def _context_payload("):RHINO.index("def draw_context(")]
    assert fetch.index('say("Fetching the neighbourhood') < fetch.index("subprocess.run(")


# ---- review of PR #23 (coordinator's round): one service down must not delete the other layers -------------------

DOC = 7                                    # the document's serial in these replays


def redraw(model, record, payload, frame, guides=None):
    """What gordium_rhino.draw_context does to the file and the screen, step by step with the same rhino_logic calls
    (the model is a list of (source, object) as the context layers hold them; `guides` the footprints on screen for
    this document, None after a reopen): merge with the saved record (JSON round-tripped, as the file keeps it),
    then follow the merge's one plan: delete its `replace` sources' objects (all of them around another frame), add
    the new objects, keep the footprints on screen only if it says so. (model, record, payload shown, guides held)."""
    record = json.loads(json.dumps(record)) if record is not None else None
    held = {"doc": DOC, "lines": guides} if guides is not None else {}
    plan = logic.context_merge(payload, record, frame, live_on_screen=logic.guides_on_screen(held, DOC))
    payload, sources = plan["payload"], plan["replace"]
    kept_objects = [(s, o) for s, o in model if not (sources is None or s in sources)]
    shown = guides if plan["keep_guides"] else logic.context_guides(payload)
    return kept_objects + [(o["source"], o) for o in logic.context_objects(payload)], plan["record"], payload, shown


class Down(T.Fake):
    def __init__(self, *a, down=(), **kw):
        super().__init__(*a, **kw)
        self.down = set(down)

    def post(self, url, params):
        from site_lookup.http import Offline
        if T.key_of(url) in self.down:
            raise Offline(url)
        return super().post(url, params)


def fetch_with(frame, down=()):
    return cb.fetch(frame, Down(T.load("106_ithaca_rd"), context=T.load("106_ithaca_rd_context"), down=down), now=T.NOW)


def test_one_service_down_keeps_that_layer_and_replaces_the_others():
    """Parcels offline, streets answering, the same lot: the saved parcels stay (and the record still says they are
    drawn, with their requests and credit line), the streets are replaced, not doubled."""
    frame = looked_up()["writes"]["frame"]
    first = fetch_with(frame)
    model, record, _, _ = redraw([], None, first, frame)
    parcels_before = [o for s, o in model if s == "state_parcels"]
    assert len(parcels_before) == 229
    again = fetch_with(frame, down={"state_parcels"})
    assert again["status"] == "found" and again["layers"]["parcels"]["status"] == "offline"
    assert logic.context_replaces(again) == {"state_streets", "state_buildings", "gordium"}
    model2, record2, shown, _ = redraw(model, record, again, frame)
    assert [o for s, o in model2 if s == "state_parcels"] == parcels_before          # kept, untouched
    assert len([o for s, o in model2 if s == "state_streets"]) == 38                 # replaced, not doubled
    assert len([o for s, o in model2 if s == "gordium"]) == 6
    assert record2["layers"]["parcels"] == record["layers"]["parcels"]               # still drawn, count 229
    assert any(r["source"] == "state_parcels" for r in record2["sources"])           # its requests carried over
    assert record2["kept_from"] == {"parcels": record["fetched"]}
    dot = next(o for s, o in model2 if s == "gordium" and o.get("name") == "Sources")
    assert "Tax parcels: NYS Tax Parcels Public" in dot["text"]                       # still credited
    said = logic.context_says(shown)
    assert "229 parcels" in said and "Kept the parcels drawn earlier" in said


def test_footprints_down_in_a_reopened_file_are_never_said_or_recorded_as_kept(live_footprints):
    """Review round 6: with no footprints on screen (a reopened file) and their service down, the panel said "Kept the
    buildings drawn earlier" and the record still said "found". One decision now: a live-only layer is kept only
    when its guides are on screen."""
    frame = looked_up()["writes"]["frame"]
    model, record, _, guides = redraw([], None, fetch_with(frame), frame)
    assert guides                                                              # drawn, this session
    # the same file reopened: nothing on screen
    _, record2, shown, on_screen = redraw(model, record, fetch_with(frame, down={"state_buildings"}), frame, None)
    assert "Kept the buildings" not in logic.context_says(shown)
    assert record2["layers"]["buildings"]["status"] == "offline" and not on_screen
    assert not any("Building Footprints" in c for c in record2["credits"]) and "kept_from" not in record2
    # the same session, footprints still on screen: they are kept, and said so
    _, record3, shown3, on3 = redraw(model, record, fetch_with(frame, down={"state_buildings"}), frame, guides)
    assert on3 == guides and "Kept the buildings" in logic.context_says(shown3)
    assert record3["layers"]["buildings"]["status"] == "found" and set(record3["kept_from"]) == {"buildings"}
    draw = RHINO[RHINO.index("def draw_context("):RHINO.index("def sync_context(")]
    assert "logic.keeps_live" not in draw and '"state_buildings" not in' not in draw      # the plan decides
    from site_lookup.context import LIVE_ONLY
    assert logic.LIVE_ONLY == LIVE_ONLY                    # the mark that tells a live-only credit line apart


def test_kept_from_names_only_the_layers_kept_in_this_fetch():
    """Review round 6: parcels down, then streets down (parcels answering again): kept_from said both."""
    frame = looked_up()["writes"]["frame"]
    model, record, _, guides = redraw([], None, fetch_with(frame), frame)
    model, record, _, guides = redraw(model, record, fetch_with(frame, down={"state_parcels"}), frame, guides)
    assert set(record["kept_from"]) == {"parcels"}
    model, record, _, guides = redraw(model, record, fetch_with(frame, down={"state_streets"}), frame, guides)
    assert set(record["kept_from"]) == {"streets"}
    assert record["layers"]["parcels"]["status"] == "found" and len([1 for s, _ in model if s == "state_parcels"]) == 229


def test_a_failed_footprint_fetch_is_not_on_screen_so_the_next_tick_fetches_again(live_footprints):
    """Review round 7: after a footprint fetch that failed, the plugin holds an empty entry for the document, and the
    tick and Draw took the document match alone as "loaded": the footprints could never be fetched again. One
    definition now (guides_on_screen): held for this document AND something to draw."""
    frame = looked_up()["writes"]["frame"]
    model, record, _, shown = redraw([], None, fetch_with(frame, down={"state_buildings"}), frame)
    held = {"doc": DOC, "lines": shown}                       # what draw_context stores after that fetch
    assert shown == [] and logic.guides_of(held, DOC) and not logic.guides_on_screen(held, DOC)
    assert not logic.guides_on_screen({"doc": DOC + 1, "lines": [[0, 0]]}, DOC) and not logic.guides_on_screen(None, DOC)
    # so the next tick (or Draw on the same lot) fetches, and this time the footprints come
    model, record, _, shown = redraw(model, record, fetch_with(frame), frame, shown)
    assert len(shown) == 322 and logic.guides_on_screen({"doc": DOC, "lines": shown}, DOC)


def test_no_reader_text_still_says_the_footprints_are_never_saved():
    """Review of the editable outlines, P3: after the switch to store raw, docstrings and comments still said the
    footprints were shown only on screen and never saved, and the fixture docstring said nothing of them was recorded."""
    texts = {p: (REPO / p).read_text(encoding="utf-8") for p in (
        "apps/rhino_plugin/gordium_rhino.py", "packages/site_lookup/site_lookup/context.py",
        "packages/design_checker/design_checker/context_box.py", "packages/design_checker/design_checker/rhino_logic.py",
        "packages/site_lookup/tests/test_context.py")}
    for stale in ("only drawn on screen by the overlay, never saved", "the building footprints, never saved",
                  "nothing of them is in any fixture", "its footprints (never saved) fetched again",
                  "the footprints are never saved", "the footprints, never saved", "until Ben decides"):
        assert not [p for p, t in texts.items() if stale in t], stale


def test_with_nothing_drawn_for_the_lot_the_tick_fetches_it():
    """Review of the editable outlines, round 2: after a Draw with the tick off, or a first fetch that failed outright,
    there is no record; ticking Show neighbourhood said "shown" and drew nothing."""
    assert logic.needs_refetch(None, None, DOC) and logic.needs_refetch({"doc": DOC, "lines": []}, None, DOC)
    assert logic.needs_refetch(None, {"frame": {}}, DOC)                    # a record with no layers: the same


def test_kept_footprints_in_a_reopened_file_are_not_fetched_again():
    """Since the footprints are kept, a reopened file has them: nothing held on screen is no reason to fetch again
    (review of the editable outlines, P3)."""
    frame = looked_up()["writes"]["frame"]
    _, record, _, shown = redraw([], None, fetch_with(frame), frame)
    assert shown == [] and not logic.needs_refetch(None, record, DOC)
    _, record, _, _ = redraw([], None, fetch_with(frame, down={"state_parcels"}), frame)
    assert logic.needs_refetch(None, record, DOC)                          # a failed layer still is


def test_a_fetch_that_worked_but_found_no_footprints_is_not_fetched_again_and_a_failed_one_is(live_footprints):
    """Review round 8: "on screen" (something to draw) also decided "fetch again", so a fetch that worked and found no
    footprints was fetched again (a wait of up to 20 s and a redraw) on every Draw and tick. needs_refetch is its
    own question: nothing held for this document, or any layer whose last fetch failed (stored ones too since
    round 9: see the next test)."""
    frame = looked_up()["writes"]["frame"]

    class NoFootprints(Down):
        def post(self, url, params):
            if T.key_of(url) == "state_buildings":
                return {"features": []}, b"{}"
            return super().post(url, params)
    empty = cb.fetch(frame, NoFootprints(T.load("106_ithaca_rd"), context=T.load("106_ithaca_rd_context")), now=T.NOW)
    assert empty["layers"]["buildings"]["status"] == "found" and empty["counts"]["buildings"] == 0
    _, record, _, shown = redraw([], None, empty, frame)
    held = {"doc": DOC, "lines": shown}
    assert shown == [] and not logic.guides_on_screen(held, DOC)          # nothing to draw ...
    assert not logic.needs_refetch(held, record, DOC)                      # ... and nothing to fetch again
    _, record, _, shown = redraw([], None, fetch_with(frame, down={"state_buildings"}), frame)
    assert logic.needs_refetch({"doc": DOC, "lines": shown}, record, DOC)  # the footprints' service failed
    assert logic.needs_refetch(None, record, DOC)                          # a reopened file: nothing held
    _, record, _, shown = redraw([], None, fetch_with(frame), frame)
    assert not logic.needs_refetch({"doc": DOC, "lines": shown}, record, DOC)
    assert logic.needs_refetch({"doc": DOC + 1, "lines": shown}, record, DOC)   # another document's


def test_a_stored_layer_that_failed_is_fetched_again_but_one_kept_from_a_good_fetch_is_not(live_footprints):
    """Review round 9: needs_refetch retried only live-only layers, so parcels down on the first Draw (footprints
    answering) stayed at "0 neighbouring parcels" for good."""
    frame = looked_up()["writes"]["frame"]
    model, record, _, shown = redraw([], None, fetch_with(frame, down={"state_parcels"}), frame)
    assert record["layers"]["parcels"]["status"] == "offline" and shown
    assert logic.needs_refetch({"doc": DOC, "lines": shown}, record, DOC)        # nothing kept: try again
    # an earlier good draw, then parcels down: they are kept (found, from the earlier fetch), so no loop
    model, record, _, shown = redraw([], None, fetch_with(frame), frame)
    model, record, _, shown = redraw(model, record, fetch_with(frame, down={"state_parcels"}), frame, shown)
    assert record["layers"]["parcels"]["status"] == "found" and set(record["kept_from"]) == {"parcels"}
    assert not logic.needs_refetch({"doc": DOC, "lines": shown}, record, DOC)


def test_every_state_of_the_context_has_one_definition():
    """Review round 7, swept: on screen, belongs to this document, same frame, stored, the live layer kept, what is
    replaced: each decided by one rhino_logic function, used everywhere."""
    import inspect
    assert not re.search(r'get\("doc"\)\s*==', RHINO)                         # never a document match of its own
    for fn in ("def draw_context(", "def draw_scene(", "def bounds("):          # on screen: drawing and the merge
        body = RHINO[RHINO.index(fn):].split("\ndef ", 1)[0]
        assert "logic.guides_on_screen(" in body, fn
    for fn in ("def sync_context(", "def show_context("):                      # fetch again: round 8
        body = RHINO[RHINO.index(fn):].split("\ndef ", 1)[0]
        assert "logic.needs_refetch(STATE.get(\"context_guides\"), _context_record(doc), doc.RuntimeSerialNumber)" \
            in body and "guides_on_screen" not in body, fn
    assert not re.search(r"loaded = \(STATE", RHINO)
    assert "logic.guides_of(STATE.get(\"context_guides\"), doc.RuntimeSerialNumber)" in RHINO     # _clear_context
    assert 'get("frame") ==' not in RHINO and 'get("frame") !=' not in RHINO and "same = " not in RHINO
    src = inspect.getsource(logic)
    rest = src.replace(inspect.getsource(logic.is_stored), "")
    assert '"store") == "raw"' not in rest and '"store") != "raw"' not in rest and '["store"] == "raw"' not in rest
    box = inspect.getsource(cb)
    assert '["store"] == "raw"' not in box and '["store"] != "raw"' not in box and "is_stored(" in box
    merge = inspect.getsource(logic.context_merge)
    assert "live_kept = keeps_live(kept, old)" in merge and "same_frame(" in merge
    assert "same_frame(drawn, frame)" in inspect.getsource(logic.context_step)
    assert "logic.context_replaces(" not in RHINO and "logic.keeps_live(" not in RHINO   # only through the plan


def test_around_another_lot_nothing_of_the_earlier_one_is_kept():
    frame = looked_up()["writes"]["frame"]
    model, record, _, _ = redraw([], None, fetch_with(frame), frame)
    other = dict(frame, rotation_deg=frame["rotation_deg"] + 90)          # another placement: another frame
    model2, record2, _, _ = redraw(model, record, fetch_with(other, down={"state_parcels"}), other)
    assert not [o for s, o in model2 if s == "state_parcels"] and "kept_from" not in record2
    assert record2["layers"]["parcels"]["status"] == "offline"


def test_nothing_answering_leaves_the_saved_neighbourhood_alone_and_the_plugin_passes_the_sources():
    assert logic.context_replaces({"layers": {"parcels": {"source": "state_parcels", "status": "offline"}}}) == set()
    draw = RHINO[RHINO.index("def draw_context("):RHINO.index("def sync_context(")]
    assert "plan = logic.context_merge(payload, old, frame," in draw
    assert 'payload, record, sources, keep_guides = plan["payload"], plan["record"], plan["replace"], plan["keep_guides"]' in draw
    assert "_clear_context(doc, sources)" in draw and "json.dumps(record)" in draw
    assert draw.index('if payload.get("status") != "found":') < draw.index("_clear_context(doc, sources)")
    clear = RHINO[RHINO.index("def _clear_context("):RHINO.index("def _edited_pieces(")]
    assert "if not source or (sources is not None and source not in sources):" in clear
    assert clear.index("if sources is None:") < clear.index("doc.Strings.Delete(SECTION, logic.CONTEXT_ENTRY)")


# ---- the Sources note (PR #23's Rhino screenshots: one long dot ran off the view) ---------------------------------

def test_the_sources_note_is_wrapped_model_text_inside_the_square_clear_of_the_scale_bar():
    """The note is model text (not a dot, which is drawn at screen size, centred on its point), wrapped to
    NOTE_WIDTH characters, growing up from the square's bottom-left corner, turned with the square. Its extent,
    worked out generously (each character 0.7 × the text height wide, each line 1.7 × high), lies inside the square
    and left of the scale bar. Rhino measures the real text in context_in_rhino.py."""
    half = 750.0
    credits = ["Tax parcels: NYS Tax Parcels Public (from Tompkins County Real Property): for planning and general "
               "use only, not a substitute for a legal parcel survey.", "Street centerlines: NYS Streets (NYS ITS "
               "Geospatial Services).", "NYS Building Footprints: " + logic.LIVE_ONLY]
    note = next(o for o in cb.notes(half, credits) if o["name"] == "Sources")
    lines = note["text"].split("\n")
    assert note["kind"] == "text" and note["height_ft"] == logic.NOTE_HEIGHT_FT
    assert all(len(ln) <= logic.NOTE_WIDTH for ln in lines) and len(lines) >= 4
    assert " ".join(lines).replace("  ", " ") == " ".join(credits)          # every word kept, in order
    (x, y), h = note["points"][0], note["height_ft"]
    right, top = x + max(map(len, lines)) * 0.7 * h, y + len(lines) * 1.7 * h
    bar = next(o for o in cb.notes(half, credits) if o["name"].startswith("Scale bar,"))
    assert -half < x and -half < y and right < half and top < half
    assert right < min(px for px, _ in bar["points"])                       # clear of the scale bar
    payload, p = context_for()
    placed = next(o for o in payload["objects"] if o["name"] == "Sources")
    assert placed["kind"] == "text" and placed["rotation_deg"] == p["writes"]["frame"]["rotation_deg"]
    assert all(len(ln) <= logic.NOTE_WIDTH for ln in placed["text"].split("\n"))


def test_the_note_is_small_text_at_its_own_scale_not_the_templates():
    """Root cause, proven in Rhino by the Rhino job (PR #23): the feet template's current dimension style ("Feet
    Decimal") has a model-space scale of 12 and annotation scaling is on, so text made from it displays at 12 × its
    height (~30 ft letters). A bounding box measures the unscaled text, so a measure-and-shrink guard never fired.
    The note now sets its own DimensionScale to 1, right after it is made and before its height."""
    assert logic.NOTE_HEIGHT_FT <= 3.0 and logic.NOTE_LINE_FT == pytest.approx(1.7 * logic.NOTE_HEIGHT_FT)
    lines = 6                                       # the whole block: deep inside a 1500 ft square
    assert logic.NOTE_WIDTH * 0.7 * logic.NOTE_HEIGHT_FT < 150 and lines * logic.NOTE_LINE_FT < 40
    body = RHINO[RHINO.index("def _context_text("):RHINO.index("def draw_context(")]
    made = body.index("rg.TextEntity.Create(")
    assert made < body.index("text.DimensionScale = 1.0") < body.index("text.TextHeight = ")
    assert "note_shrink" not in RHINO and not hasattr(logic, "note_shrink")    # the guard that never fired: gone
    # every annotation Gordium makes (swept): this note is the only one, the labels are drawn by the overlay
    assert RHINO.count("rg.TextEntity.Create(") == 1 and "AddLinearDimension" not in RHINO and "AddLeader" not in RHINO
    check = (REPO / "apps/rhino_plugin/tests/context_in_rhino.py").read_text(encoding="utf-8")
    assert "ok, polyline = geom.TryGetPolyline()" in check      # curves by their own points, not a world box
    assert "the sources note is small" in check and "line_height_ft" in check
    assert "geom.DimensionScale" in check and "dimension_scale" in check and "text_height_ft" in check


def test_a_kept_layers_note_is_wrapped_the_same_way():
    frame = looked_up()["writes"]["frame"]
    model, record, _, shown = redraw([], None, fetch_with(frame), frame)
    _, _, shown_payload, _ = redraw(model, record, fetch_with(frame, down={"state_parcels"}), frame, shown)
    note = next(o for o in shown_payload["objects"] if o["name"] == "Sources")
    assert "Tax parcels" in note["text"] and all(len(ln) <= logic.NOTE_WIDTH for ln in note["text"].split("\n"))


def test_the_plugin_writes_the_note_as_bottom_left_model_text():
    body = RHINO[RHINO.index("def _context_text("):RHINO.index("def draw_context(")]
    assert "rg.TextEntity.Create(" in body and "rg.TextJustification.BottomLeft" in body
    assert "_model_length(doc, o.get(\"height_ft\")" in body and "rotation_deg" in body
    draw = RHINO[RHINO.index("def draw_context("):RHINO.index("def sync_context(")]
    assert 'elif o["kind"] == "text":' in draw and "doc.Objects.AddText(_context_text(doc, o, pts[0]), attrs)" in draw
    check = (REPO / "apps/rhino_plugin/tests/context_in_rhino.py").read_text(encoding="utf-8")
    assert "every note lies inside the neighbourhood square" in check


# ---- the Rhino side, by its code (it can't run in CI) ------------------------------------------------------------

def test_the_plugin_writes_only_context_objects_and_keeps_guides_on_screen():
    body = RHINO[RHINO.index("def draw_context("):RHINO.index("def _context_visible(")]
    assert "for o in logic.skip_edited(logic.context_objects(payload), edited):" in body
    assert body.count("doc.Objects.Add") == 3                            # a dot, a text or a curve, per object
    assert 'STATE["context_guides"] = ' in body and "logic.context_guides(payload)" in body
    assert "doc.Strings.SetString(SECTION, logic.CONTEXT_ENTRY, json.dumps(record))" in body
    assert "plan = logic.context_merge(payload, old, frame," in body
    assert "attrs.SetUserString(logic.CONTEXT_KEY, o[\"source\"])" in body
    assert "_lock_context(doc, True)" in body                            # locked: not selectable, can't be moved
    # live mode hears each add; the context changes nothing checked, so no re-check is set off by it
    assert body.index('dirty = STATE.get("dirty")') < body.index("_clear_context(doc, sources)") < \
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
    assert 'box.CheckedChanged += logic.guard(changed, "show or hide the neighbourhood")' in ui
    assert 'actions["context"](bool(box.Checked))' in ui
    greyed = ui[ui.index('parts["greyed"] = ['):].split("\n", 1)[0]
    ticks = ui[ui.index("    ticks = ["):].split("\n    # while", 1)[0]
    assert "row(_context_box(actions, parts, context_on))" in ticks and "*ticks" in greyed   # off while a box is open


def test_the_panel_says_what_was_drawn():
    payload, _ = context_for()
    said = logic.context_says(payload)
    assert said == "Neighbourhood drawn: 229 parcels, 38 streets, 322 buildings (footprints from 2014)."
    # (what an architect needs, nothing more)
    assert len(said) < 100
    assert logic.context_says({"status": "offline", "message": "Couldn't fetch the neighbourhood: x"}).endswith(": x")
    assert logic.context_says(None).startswith("Couldn't fetch")


def test_context_box_runs_as_its_own_process_on_the_recorded_answers():
    frame = looked_up()["writes"]["frame"]
    args = logic.context_command(sys.executable, frame, "106_ithaca_rd")
    out = subprocess.run(args, cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=120)
    p = json.loads(out.stdout.strip().splitlines()[-1])
    assert p["status"] == "found" and p["counts"] == {"parcels": 229, "streets": 38, "buildings": 322}


def test_context_box_never_prints_a_traceback():
    out = subprocess.run([sys.executable, "-m", "design_checker.context_box", "--origin", "1", "2", "--rotation", "0",
                          "--shift", "0", "0", "--fixture", "no_such_fixture"], cwd=REPO, capture_output=True,
                         text=True, encoding="utf-8", timeout=120)
    p = json.loads(out.stdout.strip().splitlines()[-1])
    assert p["status"] == "error" and p["objects"] == [] and "Traceback" not in out.stdout
