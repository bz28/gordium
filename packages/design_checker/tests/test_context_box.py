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
        if o["kind"] in ("dot", "text"):          # (the plugin writes "text" as model text; its words are what count)
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
    assert "if source and (sources is None or source in sources):" in body            # never the architect's own
    assert "doc.Strings.Delete(SECTION, logic.CONTEXT_ENTRY)" in body and 'STATE.pop("context_guides"' in body
    vis = RHINO[RHINO.index("def _context_visible("):RHINO.index("def show_context(")]
    assert "for i in indexes:" in vis                                                    # every sublayer too


def test_the_tick_starts_as_it_was_last_set():
    ui = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")
    box = ui[ui.index("def _context_box("):ui.index("def _envelope_box(")]
    assert "box.Checked = bool(on)" in box and box.index("box.Checked") < box.index("CheckedChanged")
    assert "_context_box(actions, context_on)" in ui and "def make_panel(actions, host=None, context_on=True):" in ui
    # both ways the panel is made (docked, the default since the MVP panel; floating when it can't be) start the tick
    # as it was last set
    assert 'ui.make_panel(_actions(), ui.DockHost(dock, host), context_on=STATE.get("context_on", True))' in RHINO
    assert 'ui.make_panel(_actions(), context_on=STATE.get("context_on", True))' in RHINO
    assert RHINO.count("ui.make_panel(") == 2


def test_the_quickstart_says_how_footprints_come_back_after_reopening():
    guide = (REPO / "apps/rhino_plugin/QUICKSTART.md").read_text(encoding="utf-8")
    assert "fetched again when you reopen" not in guide
    assert "untick and tick **Show neighbourhood** to fetch them again" in guide


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
    assert "229 neighbouring parcels" in said and "Kept the parcels drawn earlier" in said


def test_footprints_down_in_a_reopened_file_are_never_said_or_recorded_as_kept():
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


def test_a_failed_footprint_fetch_is_not_on_screen_so_the_next_tick_fetches_again():
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
    assert len(shown) == 212 and logic.guides_on_screen({"doc": DOC, "lines": shown}, DOC)


def test_a_fetch_that_worked_but_found_no_footprints_is_not_fetched_again_and_a_failed_one_is():
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


def test_a_stored_layer_that_failed_is_fetched_again_but_one_kept_from_a_good_fetch_is_not():
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
    clear = RHINO[RHINO.index("def _clear_context("):RHINO.index("def _context_record(")]
    assert "if source and (sources is None or source in sources):" in clear
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
    assert "for o in logic.context_objects(payload):" in body
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
    assert re.search(r'CheckedChanged \+= logic\.guard\(lambda s, e: actions\["context"\]', ui)
    greyed = ui[ui.index('parts["greyed"] = ['):].split("\n", 1)[0]
    ticks = ui[ui.index("    ticks = ["):].split("\n    # while", 1)[0]
    assert "row(_context_box(actions, context_on))" in ticks and "*ticks" in greyed   # off while a box is open


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
