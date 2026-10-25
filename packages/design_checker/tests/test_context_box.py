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


# an outline's attributes as _attrs_print reads them: each of FINGERPRINT_ATTRIBUTES, the tables' ids, groups, user text
ATTRIBUTES = {"Name": "footprint-1", "Url": "", "Mode": "Normal", "Visible": "True", "Space": "ModelSpace",
              "ViewportId": "00000000-0000-0000-0000-000000000000", "DisplayOrder": "0", "WireDensity": "1",
              "ObjectDecoration": "None", "ColorSource": "ColorFromLayer", "ObjectColor": "-16777216",
              "LinetypeSource": "LinetypeFromLayer", "PlotColorSource": "PlotColorFromLayer", "PlotColor": "-16777216",
              "PlotWeightSource": "PlotWeightFromLayer", "PlotWeight": "0.0", "MaterialSource": "MaterialFromLayer",
              "CastsShadows": "True", "ReceivesShadows": "True", "LinetypePatternScale": "1.0",
              "layer": "9f1e-buildings", "linetype": "",
              "material": "", "groups": [], "user": []}


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
    assert set(ATTRIBUTES) == set(logic.FINGERPRINT_ATTRIBUTES) | {"layer", "linetype", "material", "groups", "user"}
    assert not any(n.endswith("Index") or n.endswith("Count") for n in logic.FINGERPRINT_ATTRIBUTES)  # no positions
    assert logic.attribute_text(0.1 + 0.2) == logic.attribute_text(0.3)                 # stable text
    att = RHINO[RHINO.index("def _attrs_print("):].split("\ndef ", 1)[0]
    assert "for name in logic.FINGERPRINT_ATTRIBUTES:" in att and "GetProperties" not in att
    assert "attrs.GetGroupList()" in att and 'startswith("gordium_")' in att
    clear = RHINO[RHINO.index("def _clear_context("):RHINO.index("def _edited_pieces(")]
    kept = clear.index("if logic.kept_on_clear(o.Attributes.GetUserString(logic.GEOM_KEY), o.Attributes.GetUserString(")
    assert "logic.DRAWN_KEY), str(o.Id), _outline_points(o.Geometry), _attrs_print(o.Attributes, doc)):" in clear
    assert kept < clear.index('attrs.SetUserString(logic.EDITED_KEY, "1")') < clear.index("doc.Objects.Delete(o, True)")


class _Colour:
    """A System.Drawing.Color: its text has its name when made from one, never when read back from a file."""

    def __init__(self, argb, named=False):
        self.argb, self.named = argb, named

    def ToArgb(self):
        return self.argb

    def __str__(self):
        return "Color [Black]" if self.named else "Color [A=255, R=0, G=0, B=0]"


class _Table:
    """A layer, linetype, material or group table: items by index, each with its id."""

    def __init__(self, ids):
        self.ids = ids

    def FindIndex(self, i):
        return type("Item", (), {"Id": self.ids[i]})() if 0 <= i < len(self.ids) else None


class _Attrs:
    """ObjectAttributes as the plugin reads them in Rhino: table positions (layer, linetype, material, groups), a
    colour, a property this Rhino throws on, and Gordium's own keys in the user strings."""

    def __init__(self, layer_index=1, plot_weight=0.0, groups=None, named=False):
        self.Name, self.Url, self.Mode, self.Visible, self.DisplayOrder = "footprint-1", "", "Normal", True, 0
        self.LayerIndex, self.LinetypeIndex, self.MaterialIndex = layer_index, -1, -1
        self.ObjectColor, self.PlotWeight, self.groups = _Colour(-16777216, named), plot_weight, groups
        self.LinetypePatternScale = 1.0          # Rhino 8's per-object linetype scale
        self.strings = {"gordium_context": "state_buildings", "gordium_context_id": "footprint-1"}

    @property
    def CastsShadows(self):
        raise RuntimeError("TargetInvocationException: not readable here")

    def GetGroupList(self):
        return self.groups                       # None when the object is in no group, as RhinoCommon gives it

    def GetUserStrings(self):
        return type("NV", (), {"AllKeys": list(self.strings)})()

    def GetUserString(self, k):
        return self.strings.get(k)


class _Doc:
    def __init__(self, layers):
        self.Layers, self.Linetypes = _Table(layers), _Table(["lt-dashed"])
        self.Materials, self.Groups = _Table([]), _Table(["g-0", "g-1", "g-2", "g-their-linework"])


def test_the_attribute_fingerprint_is_stable_in_rhino_and_sees_print_width_and_groups():
    """Review of the editable outlines, rounds 2 and 3: _attrs_print run as written, over attributes shaped like
    RhinoCommon's. Read again after Gordium writes its own keys, and after a save and reopen in which a deleted layer
    before the context layers moved their indexes down (Gordium deletes its holding layer itself), an untouched
    outline has the same fingerprint, so it is Gordium's and is cleared; a print width, a group or the architect's
    own user text is an edit."""
    src = RHINO[RHINO.index("def _attrs_print("):RHINO.index("def _clear_context(")]
    ns = {"logic": logic}
    exec(src, ns)
    attrs_print = ns["_attrs_print"]
    pts = [(0.0, 0.0, 0.0), (30.0, 0.0, 0.0), (30.0, 40.0, 0.0), (0.0, 0.0, 0.0)]
    drawn_doc = _Doc(["default", "gordium-holding", "9f1e-buildings"])    # holding layer deleted later, still a slot
    a = _Attrs(layer_index=2, named=True)
    key = logic.outline_key(pts, attrs_print(a, drawn_doc))              # as draw_context fingerprints it
    a.strings.update({logic.GEOM_KEY: key, logic.DRAWN_KEY: "5d2c-own"})   # then writes its own keys
    first = attrs_print(a, drawn_doc)
    assert first["user"] == [] and first["groups"] == [] and first["ObjectColor"] == "-16777216"
    assert not logic.kept_on_clear(key, "5d2c-own", "5d2c-own", pts, first)            # untouched: Gordium's
    reopened = _Attrs(layer_index=1)                       # saved and reopened: the deleted layer gone, index 2 -> 1
    reopened.strings.update(a.strings)
    assert not logic.kept_on_clear(key, "5d2c-own", "5d2c-own", pts, attrs_print(reopened, _Doc(["default", "9f1e-buildings"])))
    assert first["layer"] == "9f1e-buildings" and first["linetype"] == "" and "CastsShadows" not in first
    a.PlotWeight = 0.35                                                                 # a print width set
    assert logic.kept_on_clear(key, "5d2c-own", "5d2c-own", pts, attrs_print(a, drawn_doc))
    b = _Attrs(layer_index=2, groups=[3])                                               # grouped with their linework
    assert logic.kept_on_clear(key, "5d2c-own", "5d2c-own", pts, attrs_print(b, drawn_doc))
    c = _Attrs(layer_index=2)
    c.strings["storeys"] = "4"                                                          # their own user text
    assert logic.kept_on_clear(key, "5d2c-own", "5d2c-own", pts, attrs_print(c, drawn_doc))
    d = _Attrs(layer_index=2)
    d.LinetypeIndex = 0                                                                 # a dashed linetype
    assert logic.kept_on_clear(key, "5d2c-own", "5d2c-own", pts, attrs_print(d, drawn_doc))
    e = _Attrs(layer_index=2)
    e.LinetypePatternScale = 2.0                                                        # its linetype scale (Rhino 8)
    assert logic.kept_on_clear(key, "5d2c-own", "5d2c-own", pts, attrs_print(e, drawn_doc))
    check = (REPO / "apps/rhino_plugin/tests/context_in_rhino.py").read_text(encoding="utf-8")
    assert "a copy pasted in place and a footprint given a print width are the architect's" in check  # Rhino proves it
    assert "a saved and reopened file, a layer deleted before it" in check
    doc = " ".join(logic.outline_key.__doc__.split())                  # its docstring says what is fingerprinted
    assert "FINGERPRINT_ATTRIBUTES" in doc and "by their ids" in doc and "name, colour, linetype, their own" not in doc


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
    assert "_attrs_print(o.Attributes, doc)" in clear[edited:edited + 250]
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
    assert 'say(logic.with_not_cleared("Neighbourhood removed: it is drawn only around a lot the start box looked up.",' in sync
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
    assert 'say(logic.with_not_cleared("Neighbourhood not drawn: Show neighbourhood is off' in sync   # never silent
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
    assert body.index("doc.Layers[i].IsVisible = visible") > delete                       # put back as it was
    assert body.rindex("_lock_context(doc, True)") > delete                              # all but the footprints
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
    assert "ParentLayerId" in body and "for i in touched:" in body
    assert body.index("for i in touched:") < body.index("doc.Objects.Delete(")
    assert body.index("doc.Objects.Delete(") < body.index("doc.Layers[i].IsLocked = locked")
    fetch = RHINO[RHINO.index("def _context_payload("):RHINO.index("def draw_context(")]
    assert fetch.index('say("Fetching the neighbourhood') < fetch.index("ui.spawn(args, run=True")


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


_NO_ID = "00000000-empty"


class _Layer:
    """A Rhino 8 layer as the Rhino job found it, set through RhinoCommon:
    - setting a layer's IsVisible, even to what it was, gives every sublayer the layer's own lock (context_in_rhino.py
      at c783ee6, review round 4);
    - locking a layer locks its sublayers without recording their own locks; unlocking it gives each sublayer its
      persistent lock (GetPersistentLocking), off when none was set, so a sublayer locked before its parent comes
      out unlocked (grade_lock_probe.json at e997f0e, no Gordium code);
    - a sublayer of a locked layer stays locked whatever IsLocked is set to, and setting it records no own lock (the
      probe at e631aae: the old redraw set IsLocked, and every context layer's GetPersistentLocking read off);
    - SetPersistentLocking records a sublayer's own lock only while a layer above it is locked (set alone with the
      parent unlocked it records nothing: lock_probe_994012d.json, persistent_alone), and the own lock is kept: the
      parent unlocked gives it back, and a later lock and unlock of the parent keep it (relock, nested_relock, with
      an unlocked layer between, as Gordium::Context sits). test_the_fake_layers_do_what_rhino_did replays every
      case of that probe on this table."""

    def __init__(self, table, path, parent):
        self.table, self.FullPath, self.Id, self.IsDeleted = table, path, "id-" + path, False
        self.ParentLayerId = parent.Id if parent is not None else _NO_ID
        self._visible, self._locked, self._persistent = True, False, None

    @property
    def Index(self):
        return self.table.index(self)

    def _subs(self):
        return [x for x in self.table if x.FullPath.startswith(self.FullPath + "::")]

    def _held(self):
        """Whether a layer above this one is locked."""
        return any(x._locked for x in self.table if self.FullPath.startswith(x.FullPath + "::"))

    @property
    def IsVisible(self):
        return self._visible

    @IsVisible.setter
    def IsVisible(self, on):
        self._visible = on
        for sub in self._subs():
            sub._locked = self._locked

    @property
    def IsLocked(self):
        return self._locked

    @IsLocked.setter
    def IsLocked(self, locked):
        if self._held():                       # Rhino holds a sublayer of a locked layer locked
            self._locked = True
            return
        current = getattr(self.table, "current", None)
        if locked and current and (current == self.FullPath or current.startswith(self.FullPath + "::")):
            return                             # Rhino never locks the current layer, nor a layer above it
        was, self._locked = self._locked, bool(locked)
        if was == self._locked:
            return
        for sub in sorted(self._subs(), key=lambda x: x.FullPath.count("::")):
            if self._locked:
                sub._locked = True
            elif not sub._held():
                sub._locked = sub.GetPersistentLocking()

    def GetPersistentLocking(self):
        return bool(self._persistent)

    def SetPersistentLocking(self, locked):
        if self._held():
            self._persistent = bool(locked)


class _Layers(list):
    current = None                             # the current layer's full path (the architect's working layer)

    def FindByFullPath(self, path, default):
        return next((i for i, x in enumerate(self) if x.FullPath == path), default)

    def FindId(self, layer_id):
        return next((x for x in self if x.Id == layer_id), None)


def _context_doc():
    layers = _Layers()
    for path in ("Gordium", logic.CONTEXT, logic.CONTEXT + "::Parcels", logic.CONTEXT + "::Streets",
                 logic.CONTEXT + "::Buildings", logic.CONTEXT + "::Notes"):
        parent = next((x for x in layers if path.rsplit("::", 1)[0] == x.FullPath and "::" in path), None)
        layers.append(_Layer(layers, path, parent))
    objects = type("Objects", (), {"FindByLayer": lambda self, layer: []})()
    strings = type("Strings", (), {"Delete": lambda self, section, key: None})()
    return type("Doc", (), {"Layers": layers, "Objects": objects, "Strings": strings, "RuntimeSerialNumber": DOC})()


def _locks(doc):
    return {x.FullPath.split("::")[-1]: x.IsLocked for x in doc.Layers if logic.on_layer(x.FullPath, logic.CONTEXT)}


def test_showing_or_hiding_the_neighbourhood_keeps_its_layers_locked_in_rhino_8():
    """The Rhino job, review round 4: every context layer came out unlocked after GordiumStart. Showing the layers
    set the parent Gordium::Context's IsVisible, which in Rhino 8 gives the sublayers the parent's lock (unlocked, so
    the footprints can be dragged). After the tick off and on, and after a clear, only Parcels, Streets and Notes are
    locked; the parent and Buildings never."""
    ns = {"logic": logic, "STATE": {}, "SECTION": "gordium",
          "System": type("System", (), {"Guid": type("Guid", (), {"Empty": _NO_ID})})}
    for name in ("_parent_locked", "_own_lock", "_set_own_lock", "_context_layer_indexes", "_lock_context",
                 "_context_visible", "_clear_context"):
        exec(RHINO[RHINO.index("def %s(" % name):].split("\ndef ", 1)[0], ns)
    want = {"Context": False, "Parcels": True, "Streets": True, "Buildings": False, "Notes": True}
    doc = _context_doc()
    ns["_lock_context"](doc, True)
    assert _locks(doc) == want                                   # as draw_context leaves them
    for on in (True, False, True):                               # draw_context's last step, then the tick off, on
        ns["_context_visible"](doc, on)
        assert _locks(doc) == want, on
    ns["_clear_context"](doc)                                    # the parent "Gordium" put back as it was
    assert _locks(doc) == want


def _clear_ns():
    ns = {"logic": logic, "STATE": {}, "SECTION": "gordium", "said": [],
          "System": type("System", (), {"Guid": type("Guid", (), {"Empty": _NO_ID})})}
    ns["say"] = ns["said"].append
    ns["_outline_points"], ns["_attrs_print"] = (lambda geometry: None), (lambda attrs, doc: {})
    for name in ("_parent_locked", "_own_lock", "_set_own_lock", "_context_layer_indexes", "_lock_context",
                 "_context_visible", "_clear_context"):
        exec(RHINO[RHINO.index("def %s(" % name):].split("\ndef ", 1)[0], ns)
    return ns


def test_a_clear_under_a_locked_gordium_layer_deletes_on_unlocked_layers_and_puts_every_layer_back():
    """Review round 5: the clear showed the context layers before the parent "Gordium", so with "Gordium" locked its
    IsVisible (Rhino 8) locked them all again and every delete failed silently (the neighbourhood drawn twice); and
    the parent's IsVisible unlocked the architect's own Gordium::Grade. Now every layer under "Gordium" is opened
    parent first and put back exactly as it was; a delete Rhino refuses is said."""
    ns = _clear_ns()
    doc = _context_doc()
    grade = _Layer(doc.Layers, "Gordium::Grade", doc.Layers[0])
    doc.Layers.append(grade)
    ns["_lock_context"](doc, True)
    grade.IsLocked, doc.Layers[0].IsLocked = True, True            # the architect locked their grades and "Gordium"
    seen = []
    drawn = type("O", (), {"Id": "o1", "Geometry": None, "Attributes": type("A", (), {
        "GetUserString": lambda self, k: "nys_parcels" if k == logic.CONTEXT_KEY else None})()})()

    def find(layer):
        seen.append((layer.FullPath, layer.IsLocked, layer.IsVisible))
        return [drawn] if layer.FullPath.endswith("::Parcels") else []
    deleted = []
    doc.Objects = type("Objects", (), {"FindByLayer": lambda self, layer: find(layer),
                                       "Delete": lambda self, o, quiet: deleted.append(o.Id) or True})()
    ns["_clear_context"](doc)
    assert seen and all(not locked and visible for _, locked, visible in seen), seen   # open when read
    assert deleted == ["o1"] and ns["said"] == []
    assert doc.Layers[0].IsLocked and grade.IsLocked                                    # put back as they were
    assert _own_locks(doc) == _WANT   # each own lock (under a locked parent Rhino reads every sublayer locked)
    doc.Objects = type("Objects", (), {"FindByLayer": lambda self, layer: find(layer),
                                       "Delete": lambda self, o, quiet: False})()       # Rhino refuses
    assert ns["_clear_context"](doc) == 1 and ns["said"] == []      # counted for the caller's one line (round 6)
    assert "could not remove 1 neighbourhood object " in logic.context_not_cleared(1)
    assert logic.outermost_first([(5, "A::B::C"), (2, "A"), (9, "A::B"), (1, "A::D")]) == [2, 1, 9, 5]


_WANT = {"Context": False, "Parcels": True, "Streets": True, "Buildings": False, "Notes": True}


def _own_locks(doc):
    """Each context layer's own lock, as GetPersistentLocking reads it (what it is once "Gordium" is unlocked)."""
    return {x.FullPath.split("::")[-1]: x.GetPersistentLocking() for x in doc.Layers
            if logic.on_layer(x.FullPath, logic.CONTEXT)}


def _redraw_ns():
    """draw_context run for real on the fake layers: a found neighbourhood with nothing new to add."""
    ns = _clear_ns()
    for name in ("draw_context",):
        exec(RHINO[RHINO.index("def %s(" % name):].split("\ndef ", 1)[0], ns)

    class Logic:
        def __getattr__(self, name):
            return getattr(logic, name)
        context_merge = staticmethod(lambda payload, old, frame, live_on_screen: {
            "payload": payload, "record": {"frame": frame}, "replace": None, "keep_guides": True})
        context_objects = staticmethod(lambda payload: [])
        context_says = staticmethod(lambda payload: "Neighbourhood drawn.")
    ns["logic"] = Logic()
    ns["_context_payload"] = lambda frame: {"status": "found"}
    ns["_context_record"] = lambda doc: None
    ns["_edited_pieces"] = lambda doc: []
    ns["_context_on"] = lambda doc: True
    ns["CONTEXT_GREYS"] = {"Parcels": 0, "Streets": 0, "Buildings": 0, "Notes": 0}
    ns["json"] = json
    ns["_context_layer"] = lambda doc, name: doc.Layers.index(next(
        x for x in doc.Layers if x.FullPath == logic.CONTEXT + "::" + name))
    return ns


def _locked_gordium_doc():
    doc = _context_doc()
    grade = _Layer(doc.Layers, "Gordium::Grade", doc.Layers[0])
    doc.Layers.append(grade)
    doc.Strings = type("Strings", (), {"Delete": lambda self, section, key: None,
                                       "SetString": lambda self, section, key, value: None})()
    doc.Views = type("Views", (), {"Redraw": lambda self: None})()
    return doc, grade


def _with_probe(doc):
    """A "Probe" layer with its own Grade beside "Gordium", which no Gordium code touches: the architect's layer as
    plain Rhino leaves it, for Gordium::Grade to be compared with (the Rhino job's probe at e997f0e)."""
    probe = _Layer(doc.Layers, "Probe", None)
    doc.Layers.append(probe)
    doc.Layers.append(_Layer(doc.Layers, "Probe::Grade", probe))
    return probe, doc.Layers[-1]


def _architect_locks(parent, grade, order):
    """The architect locks their grades before or after the parent layer: before, by its lock; after (the parent
    already locked), by the lock it is to have once the parent is unlocked (SetPersistentLocking)."""
    if order == "before":
        grade.IsLocked, parent.IsLocked = True, True
    else:
        parent.IsLocked = True
        grade.SetPersistentLocking(True)


def _state(layer):
    return layer.IsLocked, layer.GetPersistentLocking()


@pytest.mark.parametrize("order", ["before", "after"])
def test_a_redraw_under_a_locked_gordium_layer_keeps_each_layers_own_lock(order):
    """The Rhino job at e631aae (context_in_rhino.py claim 4): with the architect's "Gordium" layer and Gordium::Grade
    locked, a redraw replaced the neighbourhood and every layer read locked, but each one's own (persistent) lock was
    off, so unlocking "Gordium" unlocked Parcels, Streets and Notes. The redraw read IsLocked under the locked parent,
    where it says nothing about a sublayer's own lock. Now each context layer's own lock is set: after "Gordium" is
    unlocked, Parcels, Streets and Notes are locked, Buildings and Context not. The architect's Grade is left exactly
    as plain Rhino leaves it (at e997f0e: locked before "Gordium", Rhino itself unlocks it with "Gordium"; locked
    after, it stays locked)."""
    ns = _redraw_ns()
    doc, grade = _locked_gordium_doc()
    probe, probe_grade = _with_probe(doc)
    ns["_lock_context"](doc, True)                                 # the first draw, "Gordium" unlocked
    assert _locks(doc) == _WANT
    _architect_locks(doc.Layers[0], grade, order)
    _architect_locks(probe, probe_grade, order)
    assert _state(grade) == _state(probe_grade)
    ns["draw_context"](doc, {"lot": "here"})                       # the redraw (Draw again, the tick, a re-lookup)
    assert ns["said"] == ["Neighbourhood drawn."]
    assert doc.Layers[0].IsLocked and _state(grade) == _state(probe_grade)
    assert _own_locks(doc) == _WANT, _own_locks(doc)
    doc.Layers[0].IsLocked, probe.IsLocked = False, False          # the architect unlocks "Gordium"
    assert _locks(doc) == _WANT, _locks(doc)
    assert _state(grade) == _state(probe_grade) and grade.IsLocked == (order == "after"), (_state(grade), order)


@pytest.mark.parametrize("order", ["before", "after"])
def test_drawing_clearing_or_showing_under_a_locked_gordium_layer_keeps_each_layers_own_lock(order):
    """Every path that changes the context layers' locks or visibility (draw_context's lock after adding, a clear, the
    panel tick) with "Gordium" locked: each layer's own lock is Gordium's (Parcels, Streets, Notes locked; Buildings and
    Context not), so unlocking "Gordium" gives exactly that; Grade is as plain Rhino leaves it."""
    ns = _redraw_ns()
    for step in ("lock", "clear", "tick off", "tick on", "unlock and relock"):
        doc, grade = _locked_gordium_doc()
        probe, probe_grade = _with_probe(doc)
        _architect_locks(doc.Layers[0], grade, order)              # locked before any context lock was set
        _architect_locks(probe, probe_grade, order)
        if step == "lock":
            ns["_lock_context"](doc, True)                         # draw_context's lock after adding the objects
        elif step == "clear":
            ns["_lock_context"](doc, True)
            ns["_clear_context"](doc)
        elif step.startswith("tick"):
            ns["_lock_context"](doc, True)
            ns["_context_visible"](doc, step == "tick on")
        else:
            ns["_lock_context"](doc, False)                        # draw_context opens them to add, then locks
            ns["_lock_context"](doc, True)
        assert doc.Layers[0].IsLocked and _state(grade) == _state(probe_grade), step
        assert _own_locks(doc) == _WANT, (step, _own_locks(doc))
        doc.Layers[0].IsLocked, probe.IsLocked = False, False
        assert _locks(doc) == _WANT, (step, _locks(doc))
        assert _state(grade) == _state(probe_grade) and grade.IsLocked == (order == "after"), step


def test_the_first_draw_onto_layers_added_under_a_locked_gordium_layer_locks_them():
    """Review round 1 of the fix: a context layer added under an already-locked "Gordium" (the first lookup in a file
    whose Gordium layer holds only the architect's Grade) may never have been locked by Rhino, and giving it only its
    persistent lock left Parcels, Streets and Notes editable while "Gordium" stayed locked. Now every one is locked
    while "Gordium" is, with its own lock kept for when "Gordium" is unlocked (Rhino at e997f0e:
    first_draw_locked.json)."""
    ns = _redraw_ns()
    doc, grade = _locked_gordium_doc()
    del doc.Layers[1:-1]                                           # no context layers yet: "Gordium" and Grade only
    assert [x.FullPath for x in doc.Layers] == ["Gordium", "Gordium::Grade"]
    probe, probe_grade = _with_probe(doc)
    _architect_locks(doc.Layers[0], grade, "after")
    _architect_locks(probe, probe_grade, "after")

    def add(doc, name):                                            # _layer: each missing layer added, parent first
        for path in (logic.CONTEXT, logic.CONTEXT + "::" + name):
            if not any(x.FullPath == path for x in doc.Layers):
                doc.Layers.append(_Layer(doc.Layers, path, next(x for x in doc.Layers
                                                                if x.FullPath == path.rsplit("::", 1)[0])))
        return doc.Layers.index(next(x for x in doc.Layers if x.FullPath == logic.CONTEXT + "::" + name))
    ns["_context_layer"] = add
    ns["draw_context"](doc, {"lot": "here"})
    assert len(_locks(doc)) == 5 and all(_locks(doc).values()), _locks(doc)   # all held while "Gordium" is locked
    assert _own_locks(doc) == _WANT, _own_locks(doc)
    doc.Layers[0].IsLocked, probe.IsLocked = False, False
    assert _locks(doc) == _WANT and grade.IsLocked and _state(grade) == _state(probe_grade), _locks(doc)


def test_the_fake_layers_do_what_rhino_did_without_gordium():
    """The fake layer table against the Rhino job's probe at e997f0e (grade_lock_probe.json, no Gordium code): a
    sublayer locked (by IsLocked, or SetPersistentLocking) while its parent is unlocked records no own lock, reads
    locked under its locked parent and comes out unlocked when the parent is unlocked."""
    for how in ("IsLocked", "SetPersistentLocking"):
        layers = _Layers()
        parent = _Layer(layers, "P", None)
        layers.append(parent)
        sub = _Layer(layers, "P::S", parent)
        layers.append(sub)
        if how == "IsLocked":
            sub.IsLocked = True
        else:
            sub.SetPersistentLocking(True)
            sub.IsLocked = True
        assert not sub.GetPersistentLocking() and sub.IsLocked                 # own_after_lock, locked_after_lock
        parent.IsLocked = True
        assert not sub.GetPersistentLocking() and sub.IsLocked                 # own_under_locked_parent
        parent.IsLocked = False
        assert not sub.IsLocked                                                # locked_after_parent_unlocked
    probe = json.loads((REPO / "docs/evidence/pr-23/grade_lock_probe.json").read_text(encoding="utf-8"))
    assert all(v == {"own_after_lock": False, "locked_after_lock": True, "own_under_locked_parent": False,
                     "locked_after_parent_unlocked": False} for k, v in probe.items() if k != "done")


def test_a_clear_puts_an_unlocked_grade_back_unlocked_under_a_locked_gordium_layer():
    """The other way round: a layer the architect left unlocked under a locked "Gordium" comes back unlocked once
    "Gordium" is unlocked (its own lock kept, never Rhino's inherited one)."""
    ns = _redraw_ns()
    doc, grade = _locked_gordium_doc()
    ns["_lock_context"](doc, True)
    doc.Layers[0].IsLocked = True                                  # "Gordium" locked, Grade itself not
    ns["_clear_context"](doc)
    assert grade.IsLocked and not grade.GetPersistentLocking()
    doc.Layers[0].IsLocked = False
    assert not grade.IsLocked and _locks(doc) == _WANT


def test_a_full_clear_still_drops_the_record_the_footprints_held_and_puts_the_changed_mark_back():
    """Review round 7: round 6's `return left` sat above the clear's tail, so a full clear no longer deleted the
    record, dropped the footprints held on screen or put the "changed since the check" mark back (the panel said
    "Neighbourhood removed" on every later Draw; the tick fetched nothing for a new lot). Run, not searched."""
    ns = _clear_ns()
    doc = _context_doc()
    deleted = []
    doc.Strings = type("Strings", (), {"Delete": lambda self, section, key: deleted.append((section, key))})()
    drawn = type("O", (), {"Id": "o1", "Geometry": None, "Attributes": type("A", (), {
        "GetUserString": lambda self, k: "nys_parcels" if k == logic.CONTEXT_KEY else None})()})()

    def delete(o, quiet):
        ns["STATE"]["dirty"] = 9                                   # live mode hears the delete
        return False
    doc.Objects = type("Objects", (), {"FindByLayer": lambda self, layer: [drawn] if layer.FullPath.endswith("Parcels")
                                       else [], "Delete": lambda self, o, quiet: delete(o, quiet)})()
    ns["STATE"].update(context_guides={"doc": DOC, "lines": [1]}, dirty=5)
    assert ns["_clear_context"](doc) == 1                          # one refused: counted for the caller
    assert ("gordium", logic.CONTEXT_ENTRY) in deleted and "context_guides" not in ns["STATE"]
    assert ns["STATE"]["dirty"] == 5
    deleted.clear()
    ns["STATE"].update(context_guides={"doc": DOC, "lines": [1]}, dirty=5)
    assert ns["_clear_context"](doc, {"nys_parcels"}) == 1         # some sources only: the caller rewrites the record
    assert deleted == [] and "context_guides" in ns["STATE"] and ns["STATE"]["dirty"] == 5


def test_a_refused_delete_is_in_the_panels_one_line_and_never_beside_neighbourhood_removed():
    """Review round 6: the panel shows one line, so the "could not remove" warning said inside the clear was
    overwritten by the caller's next message ("Neighbourhood removed", "Neighbourhood drawn"...). Now the clear returns
    the count and each caller's one line starts with the warning."""
    ns = _clear_ns()
    for name in ("sync_context", "draw_context"):
        exec(RHINO[RHINO.index("def %s(" % name):].split("\ndef ", 1)[0], ns)
    doc = _context_doc()
    drawn = type("O", (), {"Id": "o1", "Geometry": None, "Attributes": type("A", (), {
        "GetUserString": lambda self, k: "nys_parcels" if k == logic.CONTEXT_KEY else None})()})()
    doc.Objects = type("Objects", (), {"FindByLayer": lambda self, layer: [drawn] if layer.FullPath.endswith("Parcels")
                                       else [], "Delete": lambda self, o, quiet: False})()
    record = {"frame": {"lot": "an earlier address"}, "layers": {}}
    ns.update(_context_record=lambda doc: record, _ui_state=lambda doc: {}, _context_on=lambda doc: True)
    assert logic.context_step(logic.context_frame({}, {}), record["frame"], True) == "clear"
    ns["sync_context"](doc, {})
    assert ns["said"] == [logic.with_not_cleared("Neighbourhood removed: it is drawn only around a lot the start box "
                                                 "looked up.", 1)]
    assert ns["said"][0].startswith("Gordium could not remove 1 neighbourhood object ")
    ns["said"].clear()
    ns["_context_payload"] = lambda frame: None                    # the draw step: the fetch could not start
    ns["draw_context"](doc, {"lot": "here"}, 2)
    assert ns["said"] == [logic.context_not_cleared(2) + " " + logic.NO_CONTEXT]
    assert logic.with_not_cleared("Drawn.", 0) == "Drawn."
    ns["said"].clear()                                             # sync's draw step: its clear's count reaches the line

    class Logic:                                                   # a new lot the lookup drew: step "draw"
        def __getattr__(self, name):
            return getattr(logic, name)
        context_frame = staticmethod(lambda facts, ui: {"lot": "here"})
        context_step = staticmethod(lambda frame, drawn, on: "draw")
    ns["logic"] = Logic()
    ns["sync_context"](doc, {})
    assert ns["said"] == [logic.context_not_cleared(1) + " " + logic.NO_CONTEXT]
    check = (REPO / "apps/rhino_plugin/tests/context_in_rhino.py").read_text(encoding="utf-8")
    assert '"tick_off_locks"' in check and '"tick_on_locks"' in check                  # Rhino proves it


def _probe_on_fake(case):
    """lock_probe_in_rhino.py's steps for one case, on the fake layer table: its rows as the probe records them."""
    layers = _Layers()
    top = _Layer(layers, "LockProbe_" + case, None)
    layers.append(top)
    mid = None
    if case.startswith(("nested", "mid")):
        mid = _Layer(layers, top.FullPath + "::Mid", top)
        layers.append(mid)
    sub = _Layer(layers, (mid or top).FullPath + "::Sub", mid or top)
    layers.append(sub)

    def state():
        row = {"sub_locked": sub.IsLocked, "sub_own": sub.GetPersistentLocking()}
        if mid is not None:
            row.update(mid_locked=mid.IsLocked, mid_own=mid.GetPersistentLocking())
        return row
    if case == "persistent_then_is_locked":
        sub.SetPersistentLocking(True)
        sub.IsLocked = True
    elif case in ("is_locked", "nested_is_locked"):
        sub.IsLocked = True
    elif case == "persistent_alone":
        sub.SetPersistentLocking(True)
    rows = [["sub set", state()]]
    if case == "mid_relock":
        mid.IsLocked = True
        if not sub.IsLocked:
            sub.IsLocked = True
        sub.SetPersistentLocking(True)
        rows.append(["mid locked, sub's own lock set", state()])
        mid.IsLocked = False
        rows.append(["mid unlocked", state()])
    if case in ("relock", "nested_relock"):
        top.IsLocked = True
        if not sub.IsLocked:
            sub.IsLocked = True
        sub.SetPersistentLocking(True)
        rows.append(["top locked, sub's own lock set", state()])
        top.IsLocked = False
        rows.append(["top unlocked", state()])
    top.IsLocked = True
    rows.append(["top locked", state(), {"ran": True, "top_locked": True}])
    top.IsLocked = False
    rows.append(["top unlocked", state(), {"ran": True, "top_locked": False}])
    return rows


def test_the_fake_layers_do_what_rhino_did():
    """Every case of the Rhino job's lock probe at 994012d (lock_probe_994012d.json: plain Rhino 8, no Gordium code),
    replayed on the fake layer table, gives exactly the rows Rhino gave: no own lock from IsLocked or from
    SetPersistentLocking with the parent unlocked; an own lock set under a locked parent kept through a later lock and
    unlock, with an unlocked layer between too ("keeps", not "resets")."""
    probe = json.loads((REPO / "docs/evidence/pr-23/lock_probe_994012d.json").read_text(encoding="utf-8"))
    cases = [k for k in probe if k not in ("done", "case", "trace")]
    assert sorted(cases) == sorted(["is_locked", "persistent_then_is_locked", "persistent_alone", "relock",
                                    "nested_is_locked", "nested_relock"])    # mid_relock: next run (Gordium's route)
    for case in cases:
        assert _probe_on_fake(case) == probe[case], case
    assert probe["relock"][-1][1] == {"sub_locked": True, "sub_own": True}          # kept


def test_drawn_with_gordium_unlocked_the_neighbourhood_stays_locked_when_the_architect_locks_and_unlocks_gordium():
    """Review round 3 of the claim change (P3, confirmed), fixable once the Rhino job's probe at 994012d showed an own
    lock recorded under a locked layer is kept: a neighbourhood drawn while "Gordium" was unlocked had no own locks,
    so the architect locking and unlocking "Gordium" (no redraw) unlocked Parcels, Streets and Notes. Now each
    sublayer records its own lock under a moment's lock of Gordium::Context, so they stay locked and Buildings and
    Context unlocked; the architect's Grade is left as plain Rhino leaves it."""
    ns = _clear_ns()
    doc, grade = _locked_gordium_doc()
    ns["_lock_context"](doc, True)                                 # the first draw, "Gordium" unlocked
    assert _locks(doc) == _WANT and _own_locks(doc) == dict(_WANT, Context=False)
    for _ in range(2):                                             # the architect locks and unlocks "Gordium", twice
        doc.Layers[0].IsLocked = True
        assert all(_locks(doc).values())
        doc.Layers[0].IsLocked = False
        assert _locks(doc) == _WANT, _locks(doc)
    ns["_context_visible"](doc, False)                             # the tick off and on: the same
    ns["_context_visible"](doc, True)
    doc.Layers[0].IsLocked, doc.Layers[0].IsLocked = True, False
    assert _locks(doc) == _WANT, _locks(doc)
    ns["_lock_context"](doc, False)                                # opened to add: every own lock off, all unlocked
    assert not any(_locks(doc).values()) and not any(_own_locks(doc).values())


def test_with_the_footprints_layer_current_the_locks_stand_and_nothing_breaks():
    """Review of the moment's lock (P3): Rhino never locks the current layer or a layer above it, so with the
    architect working on Gordium::Context::Buildings the moment's lock of Gordium::Context is refused. The locks set
    stand (Parcels, Streets, Notes locked; Buildings, Context not), no own lock is half written, nothing raises; once
    another layer is current, the next lock records them."""
    ns = _clear_ns()
    doc, grade = _locked_gordium_doc()
    doc.Layers.current = logic.CONTEXT + "::Buildings"
    ns["_lock_context"](doc, True)
    assert _locks(doc) == _WANT and not any(_own_locks(doc).values())
    doc.Layers.current = "Gordium::Grade"
    ns["_lock_context"](doc, True)
    assert _locks(doc) == _WANT and _own_locks(doc) == dict(_WANT, Context=False)


def test_the_lock_probe_on_the_fake_is_the_probe_in_rhino():
    """The replay follows lock_probe_in_rhino.py's own steps (its case list, and Gordium's route, mid_relock, which
    the fake expects kept: the own lock recorded under a moment's lock of Mid survives the top's lock and unlock)."""
    probe = (REPO / "apps/rhino_plugin/tests/lock_probe_in_rhino.py").read_text(encoding="utf-8")
    cases = eval(probe.split("CASES = ", 1)[1].split(")", 1)[0] + ")")             # noqa: S307  (a tuple literal)
    assert set(cases) == {"is_locked", "persistent_then_is_locked", "persistent_alone", "relock", "nested_is_locked",
                          "nested_relock", "mid_relock"}
    rows = _probe_on_fake("mid_relock")
    assert rows[-1][1]["sub_locked"] and rows[-1][1]["sub_own"], rows
