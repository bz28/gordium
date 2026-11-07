"""The host conformance suite: what any design tool's add-in (a host: Rhino now, Revit later) must send Gordium for
a set of fixed scenes, and what Gordium must then answer (test_data/host_conformance/README.md).

Each scene (test_data/host_conformance/scenes/*.yaml) is a small drawing, written down as data. From it come, by
two separate routes:

- the model a host reads (for Rhino, a .3dm: conformance_rhino.build; for another tool, the same scene drawn in
  it once), and
- the site description the host must send for it (`expected_site`, worked out here from the scene's numbers
  alone, never by reading a model), committed as expected/<scene>.site.json.

A host's description passes when (`differences` gives nothing):

1. it is a valid gordium.site/1 description (site_json.validate);
2. it matches the expected one, every point within TOL ft (face order, where a face's points start and which way
   they run, are ignored: the measuring reads a face the same either way), with the same ids, the same problem
   codes and the same left-out objects. A host that sends FEWER problems than expected fails: that is the
   false-pass guard (a curved wall it doesn't report is a wall measured as if it were straight);
3. it gives exactly the scene's expected verdicts through check_site (`verdicts`): every row of the check, each
   with the status worked out by hand, no row more and none less.

Hosts that can't run on the Mac (Revit) record their descriptions once, on their own machine, as
recorded/<host>/<scene>.json (`recording`); the same test checks them here.

    python -m design_checker.conformance              every scene through the Rhino reference adapter, and
                                                      every recording, with what differs
    python -m design_checker.conformance --write      (re)write the scenes' models, expected descriptions and
                                                      the Rhino reference adapter's recordings
"""

import json
import math
import sys
import uuid
from pathlib import Path

import yaml

from rule_format.place import plugin_place
from rule_format.rulebook import REPO, utf8_console

from . import site_json
from .site_json import SCHEMA, SiteRefused

FOLDER = REPO / "test_data" / "host_conformance"
SCENES = FOLDER / "scenes"
EXPECTED = FOLDER / "expected"
MODELS = FOLDER / "models"
RECORDED = FOLDER / "recorded"
COMMON = FOLDER / "common_verdicts.yaml"
TOL = 1e-6                  # ft: how far any point a host sends may be from the expected one
ARC_STEP = 0.25             # ft: the most a curved lot line's points may be apart (read_3dm.ARC_STEP, tested equal):
                            # the suite's reading of "points closely along it" (site_description_v1.md)
LOT = [[0, 0], [60, 0], [60, 120], [0, 120]]      # the scenes' lot unless one says otherwise (R-1b: 7,200 sf)
SITE_LAYER, BUILDING_LAYER = "Site", "Building"
CONTEXT_LAYER = "Gordium::Context"
FEET = {"Feet": 1.0, "Millimeters": 304.8}        # model units per foot, for the units a scene's model is drawn in
STEPS = ("as drawn", "after the edit")
NAMESPACE = uuid.UUID("6f1d3c55-27f6-4a8e-9b0b-3c6c2a4f0009")   # the scenes' object ids (uuid5 of scene/object)


# ---- scenes ---------------------------------------------------------------------------------------------------

def scene_paths() -> list[Path]:
    return sorted(SCENES.glob("*.yaml"))


def load(path) -> dict:
    scene = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    scene["name"] = Path(path).stem
    return scene


def scenes() -> dict:
    return {p.stem: load(p) for p in scene_paths()}


def has_model(scene: dict) -> bool:
    """Whether the scene is a drawing a host reads (most), or only a description (`site:`, written out in the
    scene): a case no Rhino drawing gives (a lot missing with no reason said), checked for its verdicts."""
    return "site" not in scene


def steps(scene: dict) -> list[str]:
    return list(STEPS if scene.get("then") else STEPS[:1])


def object_id(scene: dict, local: str) -> str:
    """The id the scene's model gives one object (a Rhino object id), the same on every build: so an id the host
    reads from the model can be told apart from one it makes up, and checked to stay the same after the edit."""
    return str(uuid.uuid5(NAMESPACE, f"{scene['name']}/{local}"))


def _offset(scene: dict) -> list:
    return list((scene.get("model") or {}).get("offset") or [0, 0, 0])


def _shift(point, scene: dict, moved=(0, 0)):
    o = _offset(scene)
    out = [point[0] + o[0] + moved[0], point[1] + o[1] + moved[1]]
    return out + [point[2] + o[2]] if len(point) == 3 else out


def lots(scene: dict) -> list[list]:
    """The scene's closed outlines on the lot layer, in feet, survey offset added."""
    given = scene.get("lots", [LOT])
    return [[_shift(p, scene) for p in ring] for ring in given]


def lot_arcs(scene: dict) -> dict:
    """{edge index: arc} for the first lot outline's curved lines (`lot_arcs: {edge: through point}`): each an arc
    from the edge's first point to its second through the given point, as {start, end, through, center, radius}."""
    rings = lots(scene)
    out = {}
    for k, through in (scene.get("lot_arcs") or {}).items():
        a, b, m = rings[0][k], rings[0][(k + 1) % len(rings[0])], _shift(through, scene)
        d = 2 * (a[0] * (b[1] - m[1]) + b[0] * (m[1] - a[1]) + m[0] * (a[1] - b[1]))
        sq = [p[0] ** 2 + p[1] ** 2 for p in (a, b, m)]
        cx = (sq[0] * (b[1] - m[1]) + sq[1] * (m[1] - a[1]) + sq[2] * (a[1] - b[1])) / d
        cy = (sq[0] * (m[0] - b[0]) + sq[1] * (a[0] - m[0]) + sq[2] * (b[0] - a[0])) / d
        out[k] = {"start": a, "end": b, "through": m, "center": [cx, cy], "radius": math.dist(a, (cx, cy))}
    return out


def _ccw(arc: dict, p) -> float:
    """The angle from the arc's start round to the point, anticlockwise about its centre, in [0, 2π)."""
    c = arc["center"]
    return (math.atan2(p[1] - c[1], p[0] - c[0]) - math.atan2(arc["start"][1] - c[1], arc["start"][0] - c[0])) \
        % (2 * math.pi)


def _sense(arc: dict) -> int:
    """1 when the arc runs anticlockwise from its start (through its `through` point to its end), else -1."""
    return 1 if _ccw(arc, arc["through"]) <= _ccw(arc, arc["end"]) else -1


def _turn(arc: dict, p) -> float:
    """How far round the arc a point is from its start (radians, the arc's own way round); more than the end's
    when the point is off the arc's span."""
    return _ccw(arc, p) if _sense(arc) == 1 else (-_ccw(arc, p)) % (2 * math.pi)


def arc_points(arc: dict) -> list[list]:
    """The arc as points along it, evenly round it, no more than ARC_STEP apart (at least 16 pieces), its ends
    exactly the lot outline's corners."""
    c, r, sweep = arc["center"], arc["radius"], _turn(arc, arc["end"])
    n = max(16, math.ceil(sweep * r / ARC_STEP))
    a0 = math.atan2(arc["start"][1] - c[1], arc["start"][0] - c[0])
    pts = [[c[0] + r * math.cos(a0 + _sense(arc) * sweep * k / n), c[1] + r * math.sin(a0 + _sense(arc) * sweep * k / n)]
           for k in range(n + 1)]
    pts[0], pts[-1] = list(arc["start"]), list(arc["end"])
    return pts


def lot_ids(scene: dict) -> list[str]:
    return ["lot" if k == 0 else f"lot_{k + 1}" for k in range(len(lots(scene)))]


def solids(scene: dict, step: str = STEPS[0]) -> list[dict]:
    """Each building solid, in feet with the survey offset: {id, outline, base, top, floor, curved, open, block}.
    A building with `floors` is one floor block per story (ids <id>_floor1, ...), each marked with the height it
    was drawn, as GordiumStart marks them."""
    moved = (scene.get("then") or {}).get("move", [0, 0]) if step == STEPS[1] else [0, 0]
    out = []
    for b in scene.get("buildings") or []:
        z = b.get("base", 0)
        heights = b.get("floors") or [b["top"] - z]
        for k, h in enumerate(heights):
            out.append({"id": f"{b['id']}_floor{k + 1}" if b.get("floors") else b["id"],
                        "outline": [_shift(p, scene, moved) for p in b["outline"]],
                        "base": z + _offset(scene)[2], "top": z + h + _offset(scene)[2],
                        "floor": h if b.get("floors") else None,
                        "curved": {"edge": b["curved"]["edge"], "through": _shift(b["curved"]["through"], scene, moved)}
                        if b.get("curved") else None, "open": bool(b.get("open")), "block": bool(b.get("block"))})
            z += h
    return out


def others(scene: dict) -> list[dict]:
    """The solids on the lot that aren't on the Building layer (each is left out of the check). The scene's edit
    moves only the buildings."""
    return [{**o, "outline": [_shift(p, scene) for p in o["outline"]],
             "base": o.get("base", 0) + _offset(scene)[2], "top": o["top"] + _offset(scene)[2]}
            for o in scene.get("others") or []]


def spot_grades(scene: dict) -> list[list]:
    return [_shift(p, scene) for p in (scene.get("grade") or {}).get("spots") or []]


def facts(scene: dict) -> dict:
    """The lot facts the architect states for the scene (the same for every host): an R-1b house, the street
    along the lot's first edge (or the edges `streets` names), the ground flat at `grade.elevation` if given.
    Spot grades are in the model, not the facts (`grade_from: spot` says to read them)."""
    rings = lots(scene)
    edges = [[list(rings[0][i]), list(rings[0][(i + 1) % len(rings[0])])] for i in range(len(rings[0]))] if rings else []
    out = {"jurisdiction": plugin_place().jurisdiction, "zone": "R-1b", "use": "one_family_detached",
           "corner_lot": False, "street_line": [edges[i] for i in scene.get("streets", [0])] if edges else [],
           "lot_surveyed": True}
    grade = scene.get("grade") or {}
    if "elevation" in grade:
        out.update(ground_is_flat=True, grade_elevation=grade["elevation"] + _offset(scene)[2])
    elif grade.get("spots"):
        out["grade_from"] = "spot"
    out.update(scene.get("facts") or {})
    return out


# ---- the expected description, from the scene's numbers alone ------------------------------------------------

def _ring_faces(outline, z0, z1, curved=None, open_=False):
    """A prism's faces as the site description holds them: floor, roof and one wall per outline edge. A curved
    wall (the edge `curved["edge"]` an arc) can't be read exactly, so it isn't sent, and nor are the floor and
    roof (each has that curved edge); an open solid (walls only) has no floor or roof to send."""
    n = len(outline)
    skip = curved["edge"] if curved else None
    walls = [{"points": [[*outline[i], z0], [*outline[(i + 1) % n], z0], [*outline[(i + 1) % n], z1],
                         [*outline[i], z1]]} for i in range(n) if i != skip]
    caps = [] if (curved or open_) else [{"points": [[x, y, z0] for x, y in outline]},
                                         {"points": [[x, y, z1] for x, y in outline]}]
    return caps + walls


def _problem(code, **args) -> dict:
    return {"code": code, "args": {k: str(v) for k, v in args.items()}}


def expected_site(scene: dict, step: str = STEPS[0]) -> dict:
    """The description a host must send for the scene (before or after its edit), in feet, with the scene's own
    ids (a host's ids are renamed to these by its id map: `rename`)."""
    if not has_model(scene):
        return scene["site"]
    rings, problems = lots(scene), []
    lot = None
    if len(rings) == 1:
        arcs = lot_arcs(scene)
        lot = {"id": "lot", "edges": [{"points": arc_points(arcs[i]), "curved": True} if i in arcs else
                                      {"points": [rings[0][i], rings[0][(i + 1) % len(rings[0])]], "curved": False}
                                      for i in range(len(rings[0]))]}
    elif rings:
        problems.append(_problem("several_lot_outlines", count=len(rings), layer=SITE_LAYER))
    else:
        problems.append(_problem("no_lot_outline", layer=SITE_LAYER))
    buildings, unsent = [], []
    for s in solids(scene, step):
        if s["block"]:
            unsent.append({"id": s["id"], "layer": BUILDING_LAYER, "kind": "block",
                           "problem": _problem("not_a_solid", kind="a block", layer=BUILDING_LAYER)})
            continue
        trouble = ([_problem("curved_edge"), _problem("curved_surface")] if s["curved"] else []) + \
            ([_problem("open_solid", what=s["id"])] if s["open"] else [])
        buildings.append({"id": s["id"], "role": "building", "layer": BUILDING_LAYER, "floor": s["floor"],
                          "faces": _ring_faces(s["outline"], s["base"], s["top"], s["curved"], s["open"]),
                          "problems": trouble})
    left_out = [{"id": o["id"], "layer": o["layer"], "could_be_building": True, "touching": o["touching"],
                 "ground_like": bool(o.get("ground_like")), "context": o["layer"] == CONTEXT_LAYER or o["layer"].startswith(CONTEXT_LAYER + "::")}
                for o in others(scene)]
    spots = spot_grades(scene)
    return {"schema": SCHEMA, "units": "ft",
            "host": {"name": "scene", "version": "", "document": scene["name"], "model_units": "Feet"},
            "lot": lot, "buildings": buildings, "unsent": unsent, "left_out": left_out,
            "grade": {"source": "spot", "points": spots} if spots else {"source": "none", "points": []},
            "inventory_complete": scene.get("inventory_complete", True), "problems": problems}


def expected_path(scene: dict, step: str = STEPS[0]) -> Path:
    return EXPECTED / f"{scene['name']}{'' if step == STEPS[0] else '.after'}.site.json"


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


# ---- comparing a host's description with the expected one --------------------------------------------------

def rename(doc: dict, ids: dict) -> dict:
    """The description with each host id that `ids` names ({host id: scene id}) as the scene's id."""
    doc = json.loads(json.dumps(doc))
    for part in (doc.get("lot"),) if isinstance(doc.get("lot"), dict) else ():
        part["id"] = ids.get(part.get("id"), part.get("id"))
    for key in ("buildings", "unsent", "left_out"):
        for item in doc.get(key) or []:
            if isinstance(item, dict):
                item["id"] = ids.get(item.get("id"), item.get("id"))
    return doc


def _close(p, q) -> bool:
    return len(p) == len(q) and all(abs(a - b) <= TOL for a, b in zip(p, q))


def _same_ring(a, b) -> bool:
    """Two closed rings of points the same within TOL, whichever point each starts at and whichever way it runs."""
    if len(a) != len(b):
        return False
    if not a:
        return True
    for ring in (b, b[::-1]):
        for k in range(len(ring)):
            if all(_close(a[i], ring[(i + k) % len(ring)]) for i in range(len(a))):
                return True
    return False


def _same_face(f, g) -> bool:
    holes_f, holes_g = f.get("holes") or [], g.get("holes") or []
    return _same_ring(f["points"], g["points"]) and _matched(holes_f, holes_g, _same_ring) is True


def _matched(want: list, got: list, same) -> bool | tuple:
    """True when `got` is `want` in some order (each item of one matched to one of the other by `same`), else
    (the wanted items not found, the got items left over)."""
    left = list(got)
    missing = []
    for w in want:
        k = next((i for i, g in enumerate(left) if same(w, g)), None)
        if k is None:
            missing.append(w)
        else:
            left.pop(k)
    return True if not missing and not left else (missing, left)


def _codes(problems) -> list[str]:
    return sorted({p["code"] for p in problems or []})


def _not_sent(doc: dict) -> tuple[list[str], list[dict]]:
    """What the host couldn't send as a solid, as the problem codes it gave (each `unsent` object's, and each
    building it sent with no faces and only such problems instead, as read_site does for a block: one building per
    kind, so the two ways count the same), and the buildings left."""
    codes, kept = [], []
    for b in doc.get("buildings") or []:
        if not b.get("faces") and b.get("problems") and all(p["code"] == "not_a_solid" for p in b["problems"]):
            codes += _codes(b["problems"])
        else:
            kept.append(b)
    codes += _codes(u["problem"] for u in doc.get("unsent") or [])
    return sorted(set(codes)), kept


def _fewer_or_more(where: str, want: list, got: list) -> list[str]:
    out = []
    fewer, more = sorted(set(want) - set(got)), sorted(set(got) - set(want))
    if fewer:
        out.append(f"{where}: FEWER problems than expected, missing {', '.join(fewer)} (a false pass risk)")
    if more:
        out.append(f"{where}: problems not expected: {', '.join(more)}")
    return out


def differences(got: dict, want: dict, ids: dict | None = None, arcs: list | None = None) -> list[str]:
    """Why a host's description (`got`, its ids renamed by `ids`) doesn't match the expected one, or [] when it
    does. Ids, problem codes and left-out objects must be the same; every point within TOL ft; faces in any order,
    each from any point and either way round. A curved lot line (one of `arcs`, the scene's: lot_arcs) must be sent
    curved, from the same end to the same end, every point within TOL of the arc, in order along it and no more
    than ARC_STEP apart: the protocol fixes no spacing, so points needn't be the expected ones. What the host
    couldn't send as a solid counts by its problem codes, not by id or how many (an `unsent` object, or a faceless
    building with not_a_solid, as read_site sends every block on the Building layer: one building named "a block",
    which has no object id)."""
    try:
        site_json.validate(got)
    except SiteRefused as e:
        return [f"not a valid description: {r}" for r in e.reasons]
    got = rename(got, ids or {})
    out = []
    if (got["lot"] is None) != (want["lot"] is None):
        out.append(f"lot: {'none sent' if got['lot'] is None else 'sent'}, expected "
                   f"{'none' if want['lot'] is None else 'one'}")
    elif want["lot"] is not None:
        if got["lot"]["id"] != want["lot"]["id"]:
            out.append(f"lot: id {got['lot']['id']!r}, expected {want['lot']['id']!r}")
        a, b = got["lot"]["edges"], want["lot"]["edges"]
        flat = lambda edges: [(tuple(p for p in e["points"]), e["curved"]) for e in edges]   # noqa: E731
        if not _same_edges(flat(a), flat(b), arcs or []):
            out.append(f"lot: its lot lines differ from the expected ones ({len(a)} sent, {len(b)} expected)")
    out += _fewer_or_more("site", _codes(want["problems"]), _codes(got["problems"]))
    want_unsent, want_buildings = _not_sent(want)
    got_unsent, got_buildings = _not_sent(got)
    out += _fewer_or_more("objects not sent as solids", want_unsent, got_unsent)
    by_id = {b["id"]: b for b in got_buildings}
    expected = {b["id"]: b for b in want_buildings}
    for i in sorted(set(expected) - set(by_id)):
        out.append(f"building {i}: not sent")
    for i in sorted(set(by_id) - set(expected)):
        out.append(f"building {i}: sent, but no such building is expected")
    for i in sorted(set(expected) & set(by_id)):
        g, w = by_id[i], expected[i]
        out += _fewer_or_more(f"building {i}", _codes(w["problems"]), _codes(g["problems"]))
        if (g.get("floor") is None) != (w.get("floor") is None) or \
                (w.get("floor") is not None and abs(g["floor"] - w["floor"]) > TOL):
            out.append(f"building {i}: floor {g.get('floor')!r}, expected {w.get('floor')!r}")
        match = _matched(w["faces"], g["faces"], _same_face)
        if match is not True:
            out.append(f"building {i}: {len(match[0])} expected face(s) not sent, {len(match[1])} face(s) sent that "
                       f"aren't expected")
    left = {o["id"]: o for o in got["left_out"]}
    for o in want["left_out"]:
        g = left.pop(o["id"], None)
        if g is None:
            out.append(f"left out {o['id']}: not listed (it makes the check need review)")
            continue
        for k in ("could_be_building", "ground_like", "context"):
            if g[k] != o[k]:
                out.append(f"left out {o['id']}: {k} {g[k]!r}, expected {o[k]!r}")
        if (g["touching"] is not False) != (o["touching"] is not False):      # null counts as touching
            out.append(f"left out {o['id']}: touching {g['touching']!r}, expected {o['touching']!r}")
    out += [f"left out {i}: listed, but no such object is expected" for i in sorted(left)]
    if got["grade"]["source"] != want["grade"]["source"]:
        out.append(f"grade: source {got['grade']['source']!r}, expected {want['grade']['source']!r}")
    elif _matched(want["grade"]["points"], got["grade"]["points"], _close) is not True:
        out.append("grade: its points differ from the expected ones")
    if got["inventory_complete"] != want["inventory_complete"]:
        out.append(f"inventory_complete {got['inventory_complete']!r}, expected {want['inventory_complete']!r}")
    return out


def _along(points, arc: dict) -> bool:
    """Whether points follow the arc: each within TOL of it, in order from one end to the other (either way round:
    a lot outline may run either way), none more than ARC_STEP (and TOL) apart."""
    if points and _close(points[0], arc["end"]):
        points = points[::-1]
    turns = [_turn(arc, p) for p in points]
    end = _turn(arc, arc["end"])
    return (len(points) >= 2 and all(abs(math.dist(p, arc["center"]) - arc["radius"]) <= TOL for p in points)
            and all(t <= end + 1e-9 for t in turns) and all(t1 >= t0 - 1e-9 for t0, t1 in zip(turns, turns[1:]))
            and all(math.dist(p, q) <= ARC_STEP + TOL for p, q in zip(points, points[1:])))


def _same_edges(a: list, b: list, arcs: list = ()) -> bool:
    """Two lot outlines' lines the same within TOL: the same loop of lines from any line, either way round (a
    line run backwards has its points reversed), each line curved or straight alike. A curved line of `arcs` is
    the same when it runs between the same ends and follows the arc (_along), whatever its points."""
    if len(a) != len(b):
        return False

    def same(x, y):
        if x[1] != y[1] or not x[0] or not _close(x[0][0], y[0][0]) or not _close(x[0][-1], y[0][-1]):
            return False
        arc = next((arc for arc in arcs if {tuple(arc["start"]), tuple(arc["end"])} ==
                    {tuple(y[0][0]), tuple(y[0][-1])}), None) if y[1] else None
        if arc is not None:
            return _along(x[0], arc)
        return len(x[0]) == len(y[0]) and all(_close(p, q) for p, q in zip(x[0], y[0]))
    back = [(tuple(reversed(pts)), curved) for pts, curved in reversed(b)]
    return any(all(same(a[i], ring[(i + k) % len(ring)]) for i in range(len(a)))
               for ring in (b, back) for k in range(len(ring)))


# ---- the verdicts -----------------------------------------------------------------------------------------------

def common_verdicts() -> dict:
    """The rows every scene's check gives the same status (they depend only on the stated facts: the use, what the
    interior holds, the rules not in Gordium yet)."""
    return yaml.safe_load(COMMON.read_text(encoding="utf-8"))["verdicts"]


def expected_verdicts(scene: dict, step: str = STEPS[0]) -> dict:
    own = scene["expected"] if step == STEPS[0] else scene["then"]["expected"]
    return {**common_verdicts(), **own}


def verdicts(doc: dict, scene_facts: dict) -> dict:
    """{row id: status} for every row of the check of the description (check_site, as the worker answers it)."""
    from .check import check_description
    return {i["id"]: i["status"] for i in check_description(doc, scene_facts)["view"]["items"]}


def verdict_differences(got: dict, want: dict) -> list[str]:
    out = [f"{k}: {got[k]}, expected {want[k]}" for k in sorted(set(got) & set(want)) if got[k] != want[k]]
    out += [f"{k}: no such row (expected {want[k]})" for k in sorted(set(want) - set(got))]
    out += [f"{k}: a row not expected ({got[k]})" for k in sorted(set(got) - set(want))]
    return out


def conformance(scene: dict, doc: dict, ids: dict | None = None, step: str = STEPS[0]) -> list[str]:
    """Every reason a host's description of the scene (at that step) fails the suite: [] when it passes."""
    out = differences(doc, expected_site(scene, step), ids,
                      list(lot_arcs(scene).values()) if has_model(scene) else [])
    if any(d.startswith("not a valid description") for d in out):
        return out
    try:
        got = verdicts(doc, facts(scene))
    except (SiteRefused, ValueError) as e:
        return out + [f"check_site refused it: {e}"]
    return out + [f"verdict {d}" for d in verdict_differences(got, expected_verdicts(scene, step))]


# ---- recordings: a host's descriptions, recorded on its own machine ---------------------------------------------

def recordings() -> dict:
    """{host: {scene: recording}} from recorded/<host>/<scene>.json, each read as strictly as the worker reads a
    request (site_json.loads: a key given twice is refused, never one of the two kept unseen). A recording that
    can't be read is {REFUSED: [why]}, a failure of its own (recording_problems)."""
    out = {}
    for path in sorted(RECORDED.glob("*/*.json")):
        try:
            rec = site_json.loads(path.read_text(encoding="utf-8"))
        except SiteRefused as e:
            rec = {REFUSED: e.reasons}
        except ValueError as e:
            rec = {REFUSED: [f"not JSON ({e})"]}
        out.setdefault(path.parent.name, {})[path.stem] = rec
    return out


REFUSED = "refused"


def recording_problems(host: str, name: str, rec: dict, every: dict) -> list[str]:
    """Why a recording fails the suite: its scene must exist and be a drawing; it names its host, the scene and
    how it was made; one id map serves every step (so an id that changed after the edit is caught); and each step's
    description passes `conformance`."""
    scene = every.get(name)
    if scene is None or not has_model(scene):
        return [f"{host}/{name}: no scene {name} with a model"]
    if REFUSED in rec:
        return [f"{host}/{name}: can't be read: {why}" for why in rec[REFUSED]]
    out = [f"{host}/{name}: '{k}' missing" for k in ("host", "scene", "recorded", "ids", "steps")
           if k not in rec]
    if out:
        return out
    if rec["host"] != host or rec["scene"] != name:
        out.append(f"{host}/{name}: recorded as {rec['host']}/{rec['scene']}")
    ids = rec["ids"]
    if len(set(ids.values())) != len(ids):
        out.append(f"{host}/{name}: two host ids map to one scene id")
    if sorted(rec["steps"]) != sorted(steps(scene)):
        out.append(f"{host}/{name}: steps {sorted(rec['steps'])}, expected {sorted(steps(scene))}")
    for step, doc in rec["steps"].items():
        if step in steps(scene):
            out += [f"{host}/{name} {step}: {d}" for d in conformance(scene, doc, ids, step)]
    return out


def coverage_problems(recorded: dict, every: dict) -> list[str]:
    """A host with any recording has one for every scene with a model: a host can't leave out the hard ones."""
    drawn = sorted(n for n, s in every.items() if has_model(s))
    return [f"{host}: no recording for {', '.join(sorted(set(drawn) - set(by)))}"
            for host, by in sorted(recorded.items()) if set(drawn) - set(by)]


# ---- the command line -----------------------------------------------------------------------------------------

def main(argv) -> int:
    from . import conformance_rhino
    every = scenes()
    if argv[:1] == ["--write"]:
        for name, scene in every.items():
            for step in steps(scene):
                if has_model(scene):
                    write_json(expected_path(scene, step), expected_site(scene, step))
            if has_model(scene):
                conformance_rhino.write_models(scene)
                write_json(RECORDED / conformance_rhino.HOST / f"{name}.json", conformance_rhino.record(scene))
        print(f"wrote {len(every)} scenes' expected descriptions, models and recordings")
        return 0
    bad = []
    for name, scene in every.items():
        for step in steps(scene):
            if has_model(scene):
                doc, ids = conformance_rhino.describe(scene, step), conformance_rhino.ids(scene)
            else:
                doc, ids = scene["site"], {}
            found = conformance(scene, doc, ids, step)
            print(f"{'OK  ' if not found else 'FAIL'} {name} ({step})")
            bad += [f"{name} {step}: {d}" for d in found]
    recorded = recordings()
    for host, by in recorded.items():
        for name, rec in by.items():
            found = recording_problems(host, name, rec, every)
            print(f"{'OK  ' if not found else 'FAIL'} recorded/{host}/{name}")
            bad += found
    bad += coverage_problems(recorded, every)
    for b in bad:
        print("  " + b)
    print("OK: every scene conforms" if not bad else f"FAILED: {len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    utf8_console()
    sys.exit(main(sys.argv[1:]))
