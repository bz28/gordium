"""The architect stress test's designs: six lots, Gordium's own starting house on each, and random sequences of the
edits an architect makes in Rhino (move the house, move one floor, stretch a face, raise the roof, add or delete a
floor, add a garage, a shed, a porch, steps, a pitched roof with eaves, a mansard, a dormer, rotate, push across a
lot line, drag off the lot, set the grade).

A design is plain data (the lot, each part's plan outline and heights, the facts), so the oracle reads the same
description Gordium is given, but Gordium gets it as faces (`gordium_site`) or as a Rhino file (`write_3dm`), the
way the Rhino command sends it. Every edit is a small dict ({"op": ..., parameters}), so a failing sequence can be
replayed, shrunk to its fewest edits, and written down as a regression test.

Units: feet, except in `write_3dm`, which can write millimeters or inches."""

import copy
import functools
import math
import random
import tempfile
from pathlib import Path

import rhino3dm as r
from shapely.geometry import LineString, Polygon

JURISDICTION = "regulations/jurisdictions/new_york/ithaca_city"
FLOOR_KEY = "gordium:floor"         # the mark GordiumStart puts on a floor block (read_3dm.FLOOR_KEY)
ID_KEY = "gordium:id"


def _seg(a, b):
    return [list(a), list(b)]


def _rect_lot(name, w, d, surveyed, **extra):
    pts = [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]
    lot = {"name": name, "points": pts, "streets": [_seg(pts[0], pts[1])], "address_street": _seg(pts[0], pts[1]),
           "sides": {"west": [_seg(pts[3], pts[0])], "east": [_seg(pts[1], pts[2])]}, "rears": [_seg(pts[2], pts[3])],
           "unsure": [], "depth": (d, d), "surveyed": surveyed, "corner": False, "grade": {"flat": 0.0}}
    lot.update(extra)
    return lot


def _sample_points():
    from design_checker.check import sample_site
    return [tuple(map(float, p)) for p in sample_site()["lot"]]


@functools.lru_cache(maxsize=None)
def lot(name: str) -> dict:
    """The six lots. sample_tax: 106 Ithaca Rd as GordiumStart offers it (73'-0" x 90'-0", from the tax map, not
    surveyed); sample_survey: the same lot surveyed; narrow: 52 x 130; jog: 70 x 120 with the east line stepping in
    8 ft at 80 ft back (the 8 ft line may be a side or a rear line, and the depth is 100 or 120 by the two readings of
    the perpendicular method); corner: 80 x 100, streets along the south (the address) and the east; sloped: 60 x
    120 with four spot grades of finished ground at the starting house's walls (front 1.0, rear 3.0, sides 2.0)."""
    if name in ("sample_tax", "sample_survey"):
        pts = _sample_points()
        assert pts == [(0.0, 0.0), (73.0, 0.0), (73.0, 90.0), (0.0, 90.0)], pts
        return _rect_lot(name, 73.0, 90.0, surveyed=name == "sample_survey")
    if name == "narrow":
        return _rect_lot(name, 52.0, 130.0, True)
    if name == "jog":
        pts = [(0.0, 0.0), (70.0, 0.0), (70.0, 80.0), (62.0, 80.0), (62.0, 120.0), (0.0, 120.0)]
        return {"name": name, "points": pts, "streets": [_seg(pts[0], pts[1])], "address_street": _seg(pts[0], pts[1]),
                "sides": {"west": [_seg(pts[5], pts[0])], "east": [_seg(pts[1], pts[2]), _seg(pts[3], pts[4])]},
                "rears": [_seg(pts[4], pts[5])], "unsure": [_seg(pts[2], pts[3])], "depth": (100.0, 120.0),
                "surveyed": True, "corner": False, "grade": {"flat": 0.0}}
    if name == "corner":
        pts = [(0.0, 0.0), (80.0, 0.0), (80.0, 100.0), (0.0, 100.0)]
        return {"name": name, "points": pts, "streets": [_seg(pts[0], pts[1]), _seg(pts[1], pts[2])],
                "address_street": _seg(pts[0], pts[1]), "sides": {"west": [_seg(pts[3], pts[0])]},
                "rears": [_seg(pts[2], pts[3])], "unsure": [], "depth": (100.0, 100.0), "surveyed": True,
                "corner": True, "grade": {"flat": 0.0}}
    if name == "sloped":
        base = _rect_lot(name, 60.0, 120.0, True)
        floors = _gordium_start({**base, "grade": {"flat": 0.0}})
        xs = [p[0] for p in floors[0]["outline"]]
        ys = [p[1] for p in floors[0]["outline"]]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        base["grade"] = {"spots": [[xm, y0 - 0.25, 1.0], [xm, y1 + 0.25, 3.0], [x0 - 0.25, ym, 2.0],
                                   [x1 + 0.25, ym, 2.0]], "base": 2.0}
        return base
    raise KeyError(name)


LOTS = ("sample_tax", "sample_survey", "narrow", "jog", "corner", "sloped")


def lot_facts(lt: dict) -> dict:
    """The lot facts GordiumStart would save for this lot."""
    f = {"jurisdiction": JURISDICTION, "zone": "R-1b", "use": "one_family_detached", "corner_lot": lt["corner"],
         "street_line": [s for s in lt["streets"]], "lot_surveyed": lt["surveyed"]}
    if lt["corner"]:
        f["address_street_line"] = [lt["address_street"]]
    if "flat" in lt["grade"]:
        f.update(ground_is_flat=True, grade_elevation=lt["grade"]["flat"])
    else:
        f.update(grade_from="finished_spots", grade_points=[list(p) for p in lt["grade"]["spots"]])
    return f


def _lot_file(lt: dict, path: Path):
    m = r.File3dm()
    m.Settings.ModelUnitSystem = r.UnitSystem.Feet
    layer = r.Layer()
    layer.Name = "Site"
    m.Layers.Add(layer)
    a = r.ObjectAttributes()
    a.LayerIndex = 0
    m.Objects.AddPolyline(r.Polyline([r.Point3d(x, y, 0) for x, y in list(lt["points"]) + [lt["points"][0]]]), a)
    m.Write(str(path), 8)


def _gordium_start(lt: dict):
    """Gordium's own starting house for the lot (design_checker.check.start, as GordiumStart draws it)."""
    from design_checker.check import start
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "lot.3dm"
        _lot_file(lt, path)
        facts = {**lot_facts({**lt, "grade": {"flat": 0.0}}), "grade_is": "finished"}
        return start(path, facts).get("floors") or []


CORNER_HOUSE = [[12.0, 27.0], [52.0, 27.0], [52.0, 62.0], [12.0, 62.0]]   # Gordium draws none on a corner lot


@functools.lru_cache(maxsize=None)
def _start_floors(name: str):
    lt = lot(name)
    floors = _gordium_start(lt)
    if not floors:      # a corner lot: "which yards are front, side and rear is an open question; no envelope drawn"
        floors = [{"outline": CORNER_HOUSE, "base": 35 * k / 3, "top": 35 * (k + 1) / 3}
                  for k in range(3)]
    lift = lt["grade"].get("base", 0.0)
    return tuple((tuple(map(tuple, f["outline"])), f["base"] + lift, f["top"] + lift) for f in floors)


def starting_design(name: str, grade_is="finished") -> dict:
    parts = [{"id": f"floor {k + 1}", "kind": "floor", "group": "house", "outline": [list(p) for p in o],
              "z0": z0, "z1": z1} for k, (o, z0, z1) in enumerate(_start_floors(name))]
    return {"lot": lot(name), "parts": parts, "listed": [], "frame": None, "grade_is": grade_is, "counter": len(parts)}


# ---- geometry helpers for edits ---------------------------------------------------------------------------------

def _floors(d):
    return sorted((p for p in d["parts"] if p["kind"] == "floor"), key=lambda p: p["z0"])


def _house(d):
    return [p for p in d["parts"] if p["group"] == "house"]


def _point_lists(p):
    return [p[k] for k in ("outline", "corners") if k in p]


def _transform(parts, f):
    for p in parts:
        for pts in _point_lists(p):
            for q in pts:
                q[0], q[1] = f(q[0], q[1])


def _new_id(d, kind):
    d["counter"] += 1
    return f"{kind} {d['counter']}"


def _roofs(d):
    return [p for p in d["parts"] if p["kind"] in ("roof", "mansard")]


def _top_z(d):
    fl = _floors(d)
    return fl[-1]["z1"] if fl else None


def _valid(d):
    for p in d["parts"]:
        for pts in _point_lists(p):
            poly = Polygon(pts)
            if not poly.is_valid or poly.area < 4:
                return False
    for p in d["parts"]:
        if p["kind"] == "roof" and p["ridge"] <= p["base"] + p["fascia"] + 0.5:
            return False
        if p["kind"] == "mansard" and Polygon(p["corners"]).buffer(-p["inset"]).is_empty:
            return False
        if p.get("z1", 1) <= p.get("z0", 0) or p["kind"] == "floor" and p["z1"] - p["z0"] < 6:
            return False
    return True


def _face(outline, k):
    """Edge k of an outline: its two ends and its outward normal (the outline counterclockwise or not)."""
    a, b = outline[k % len(outline)], outline[(k + 1) % len(outline)]
    ux, uy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(ux, uy)
    nx, ny = uy / n, -ux / n
    c = Polygon(outline).centroid
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    if (mx - c.x) * nx + (my - c.y) * ny < 0:
        nx, ny = -nx, -ny
    return a, b, (nx, ny)


def _rect_on(a, b, normal, t0, t1, depth):
    """A rectangle standing on edge a-b from t0 to t1 of its length, reaching `depth` along the normal."""
    p = [a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0]
    q = [a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1]
    nx, ny = normal
    return [p, q, [q[0] + nx * depth, q[1] + ny * depth], [p[0] + nx * depth, p[1] + ny * depth]]


# ---- the edits --------------------------------------------------------------------------------------------------

def _move_house(d, e):
    _transform(_house(d), lambda x, y: (x + e["dx"], y + e["dy"]))


def _move_floor(d, e):
    fl = _floors(d)
    if not fl:
        return False
    _transform([fl[e["k"] % len(fl)]], lambda x, y: (x + e["dx"], y + e["dy"]))


def _stretch(d, e):
    fl = _floors(d)
    if not fl:
        return False
    a, b, (nx, ny) = _face(fl[0]["outline"], e["face"])
    edge = max(x * nx + y * ny for p in fl for x, y in p["outline"])
    amount = e["amount"]

    def f(x, y):
        return (x + nx * amount, y + ny * amount) if x * nx + y * ny >= edge - 1e-6 else (x, y)
    _transform([p for p in _house(d) if p["kind"] in ("floor", "roof", "mansard")], f)


def _raise_roof(d, e):
    roofs = _roofs(d)
    if roofs:
        for p in roofs:
            if p["kind"] == "roof":
                p["ridge"] += e["dz"]
            else:
                p["z1"] += e["dz"]
        return
    fl = _floors(d)
    if not fl:
        return False
    fl[-1]["z1"] += e["dz"]


def _lift_above(d, z, dz):
    for p in d["parts"]:
        if p["kind"] == "roof" and p["base"] >= z - 1e-6:
            p["base"] += dz
            p["ridge"] += dz
        elif p["kind"] in ("mansard", "dormer") and p["z0"] >= z - 1e-6:
            p["z0"] += dz
            p["z1"] += dz


def _add_floor(d, e):
    fl = _floors(d)
    if not fl or len(fl) >= 5:
        return False
    top = fl[-1]
    _lift_above(d, top["z1"], e["h"])
    d["parts"].append({"id": _new_id(d, "floor"), "kind": "floor", "group": "house",
                       "outline": copy.deepcopy(top["outline"]), "z0": top["z1"], "z1": top["z1"] + e["h"]})


def _delete_floor(d, e):
    fl = _floors(d)
    if len(fl) < 2:
        return False
    if e["which"] == "top":
        gone = fl[-1]
        d["parts"].remove(gone)
        _lift_above(d, gone["z1"], -(gone["z1"] - gone["z0"]))
    else:                                     # a middle floor: the ones above stay where they are (a gap)
        if len(fl) < 3:
            return False
        d["parts"].remove(fl[1])


def _add_accessory(d, e):
    lt = d["lot"]
    poly = Polygon(lt["points"])
    minx, miny, maxx, maxy = poly.bounds
    w, dp, h = e["w"], e["d"], e["h"]
    where = e["where"]
    if where == "attached":
        fl = _floors(d)
        if not fl:
            return False
        a, b, n = _face(fl[0]["outline"], e["face"])
        outline = _rect_on(a, b, n, 0.0, min(1.0, w / max(LineString([a, b]).length, 1e-9)), dp)
    else:
        if where == "rear":
            x = minx + 3 + e["fx"] * max(maxx - minx - w - 6, 0)
            y = maxy - dp - e["gap"]
        elif where == "front":
            x = minx + 3 + e["fx"] * max(maxx - minx - w - 6, 0)
            y = miny + e["gap"]
        else:                                 # side: beside the house, in a side yard
            x = (minx + e["gap"]) if e["fx"] < 0.5 else (maxx - w - e["gap"])
            y = miny + 30 + e["fy"] * max(maxy - miny - 30 - dp, 0)
        outline = [[x, y], [x + w, y], [x + w, y + dp], [x, y + dp]]
    pid = _new_id(d, e["kind"])
    d["parts"].append({"id": pid, "kind": e["kind"], "group": "accessory", "outline": outline, "z0": _ground(d),
                       "z1": _ground(d) + h})
    if e["listed"]:
        d["listed"].append(pid)
    if e.get("frame") is not None:
        d["frame"] = e["frame"]


def _ground(d):
    fl = _floors(d)
    return fl[0]["z0"] if fl else d["lot"]["grade"].get("base", 0.0)


def _add_porch(d, e):
    fl = _floors(d)
    if not fl:
        return False
    a, b, n = _face(fl[0]["outline"], e["face"])
    outline = _rect_on(a, b, n, e["t0"], e["t0"] + e["span"], e["depth"])
    z0 = fl[0]["z0"]
    d["parts"].append({"id": _new_id(d, e["kind"]), "kind": e["kind"], "group": "house", "outline": outline,
                       "z0": z0, "z1": z0 + e["h"]})


def _add_roof(d, e):
    fl = _floors(d)
    if not fl or _roofs(d) or len(fl[-1]["outline"]) != 4:
        return False
    top = fl[-1]
    corners = copy.deepcopy(top["outline"])
    k = e["axis"] % 2
    corners = corners[k:] + corners[:k]
    if e["kind"] == "roof":
        d["parts"].append({"id": _new_id(d, "roof"), "kind": "roof", "group": "house", "corners": corners,
                           "base": top["z1"], "ridge": top["z1"] + e["rise"], "over": e["over"],
                           "fascia": e["fascia"]})
    else:
        d["parts"].append({"id": _new_id(d, "mansard"), "kind": "mansard", "group": "house", "corners": corners,
                           "over": e["over"], "inset": e["inset"], "z0": top["z1"], "z1": top["z1"] + e["rise"]})
    _sync_mansard(d)


def _add_dormer(d, e):
    """A flat-roofed dormer standing on the roof's base at one eave wall: `past` ft beyond the wall, 5 ft in."""
    roofs = [p for p in d["parts"] if p["kind"] == "roof"]
    if not roofs:
        return False
    roof = roofs[0]
    a, b, (nx, ny) = _face(roof["corners"], 1 if e["side"] == 0 else 3)        # the eave walls
    t0, t1 = e["t0"], e["t0"] + e["span"]
    p = [a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0]
    q = [a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1]
    out, inn = e["past"], 5.0
    outline = [[p[0] - nx * inn, p[1] - ny * inn], [q[0] - nx * inn, q[1] - ny * inn],
               [q[0] + nx * out, q[1] + ny * out], [p[0] + nx * out, p[1] + ny * out]]
    z1 = min(roof["base"] + e["h"], roof["ridge"] - 1.0)
    d["parts"].append({"id": _new_id(d, "dormer"), "kind": "dormer", "group": "house", "outline": outline,
                       "z0": roof["base"], "z1": z1})


def _rotate(d, e):
    fl = _floors(d)
    if not fl:
        return False
    c = Polygon(fl[0]["outline"]).centroid
    t = math.radians(e["deg"])
    cos, sin = math.cos(t), math.sin(t)
    _transform(_house(d), lambda x, y: (c.x + (x - c.x) * cos - (y - c.y) * sin, c.y + (x - c.x) * sin + (y - c.y) * cos))


def _target(d, which):
    if which == "accessory":
        acc = [p for p in d["parts"] if p["group"] == "accessory"]
        return [acc[-1]] if acc else None
    return _house(d)


def _push(d, e, past):
    parts = _target(d, e["target"])
    if not parts:
        return False
    lt = d["lot"]
    pts = lt["points"]
    k = e["line"] % len(pts)
    a, b = pts[k], pts[(k + 1) % len(pts)]
    _, _, (nx, ny) = _face([list(p) for p in pts], k)        # outward from the lot
    proj = [x * nx + y * ny for p in parts for f in part_faces(p) for x, y, _ in f]
    line_c = a[0] * nx + a[1] * ny
    far, near = max(proj), min(proj)
    shift = (line_c - far + e["amount"]) if not past else (line_c - near + e["amount"])
    if shift <= 0 and not past:
        shift = e["amount"]
    _transform(parts, lambda x, y: (x + nx * shift, y + ny * shift))


def _cross_line(d, e):
    return _push(d, e, past=False)


def _off_lot(d, e):
    return _push(d, e, past=True)


def _plain_wing(d, e):
    """The main house redrawn as ONE plain solid (no floor marks: its stories can't be counted from the drawing),
    with a wing of `n` Gordium floor blocks stacked against one of its walls, and a typed story count (the
    architect's `stories` fact), often lower than the floor blocks drawn."""
    fl = _floors(d)
    if not fl or any(p["kind"] == "solid" for p in d["parts"]):
        return False
    main = {"id": _new_id(d, "house"), "kind": "solid", "group": "house", "outline": copy.deepcopy(fl[0]["outline"]),
            "z0": fl[0]["z0"], "z1": fl[-1]["z1"]}
    d["parts"] = [p for p in d["parts"] if p["kind"] != "floor"] + [main]
    a, b, n = _face(main["outline"], e["face"])
    wing = _rect_on(a, b, n, 0.2, 0.7, e["depth"])
    for k in range(e["n"]):
        d["parts"].append({"id": _new_id(d, "floor"), "kind": "floor", "group": "house",
                           "outline": copy.deepcopy(wing), "z0": main["z0"] + k * e["h"],
                           "z1": main["z0"] + (k + 1) * e["h"]})
    d["typed_stories"] = e["typed"]


def _floor_wing(d, e):
    """Gordium's floor stack kept, with a PLAIN wing joined to one of its walls: one plain solid, or two stacked
    (`heights`, 6 to 25 ft each), its bottom `below` ft under the house's ground (a walk-out) or at it, and a typed
    story count (none, below, equal to or above the floors)."""
    fl = _floors(d)
    if not fl or any(p["kind"] == "solid" for p in d["parts"]):
        return False
    a, b, n = _face(fl[0]["outline"], e["face"])
    wing = _rect_on(a, b, n, 0.2, 0.7, e["depth"])
    z = fl[0]["z0"] - e["below"]
    for h in e["heights"]:
        d["parts"].append({"id": _new_id(d, "wing"), "kind": "solid", "group": "house", "outline": copy.deepcopy(wing),
                           "z0": z, "z1": z + h})
        z += h
    counted = len(fl)
    d["typed_stories"] = {"none": None, "below": max(1, counted - 1), "equal": counted,
                          "above": counted + 1}[e["typed"]]


def _shift_floor(d, e):
    """One floor block raised or lowered on its own (`dz`), the rest left where they are: a gap above or below it,
    or an overlap with its neighbour. With `carry`, every block above it moves too (a story made taller or
    shorter, the stack still touching where it was)."""
    fl = _floors(d)
    if not fl:
        return False
    k = e["k"] % len(fl)
    moving = fl[k:] if e.get("carry") else [fl[k]]
    if e.get("carry"):
        _lift_above(d, fl[-1]["z1"], e["dz"])
    for p in moving:
        p["z0"] += e["dz"]
        p["z1"] += e["dz"]


def _grade(d, e):
    d["grade_is"] = e["value"]


def _sync_mansard(d):
    """A mansard's outlines follow its walls rectangle: base `over` past it, top `inset` inside it."""
    for p in d["parts"]:
        if p["kind"] == "mansard":
            p["outline"] = _offset_rect(p["corners"], p["over"])
            p["top_outline"] = _offset_rect(p["corners"], -p["inset"])


def _offset_rect(c, o):
    p0, p1, p2, p3 = c
    ux, uy = p1[0] - p0[0], p1[1] - p0[1]
    n = math.hypot(ux, uy)
    ux, uy = ux / n, uy / n
    vx, vy = p3[0] - p0[0], p3[1] - p0[1]
    m = math.hypot(vx, vy)
    vx, vy = vx / m, vy / m
    return [[p0[0] - o * ux - o * vx, p0[1] - o * uy - o * vy], [p1[0] + o * ux - o * vx, p1[1] + o * uy - o * vy],
            [p2[0] + o * ux + o * vx, p2[1] + o * uy + o * vy], [p3[0] - o * ux + o * vx, p3[1] - o * uy + o * vy]]


OPS = {"move_house": _move_house, "move_floor": _move_floor, "stretch": _stretch, "raise_roof": _raise_roof,
       "add_floor": _add_floor, "delete_floor": _delete_floor, "add_accessory": _add_accessory,
       "add_porch": _add_porch, "add_roof": _add_roof, "add_dormer": _add_dormer, "rotate": _rotate,
       "cross_line": _cross_line, "off_lot": _off_lot, "grade": _grade, "plain_wing": _plain_wing, "floor_wing": _floor_wing, "shift_floor": _shift_floor}


def apply(design: dict, edit: dict):
    """The design after one edit (a new copy), or None if the edit doesn't apply (nothing to move, a shape it can't
    make)."""
    d = copy.deepcopy(design)
    if OPS[edit["op"]](d, edit) is False:
        return None
    _sync_mansard(d)
    return d if _valid(d) else None


def build(lot_name: str, edits: list, grade_is="finished"):
    """The starting house on the lot after the edits; edits that don't apply are skipped. Returns (design, the edits
    that applied)."""
    d = starting_design(lot_name, grade_is)
    done = []
    for e in edits:
        nxt = apply(d, e)
        if nxt is not None:
            d = nxt
            done.append(e)
    return d, done


def random_edit(rng: random.Random) -> dict:
    """One architect edit, its numbers drawn the way an architect drags things: mostly small, sometimes large."""
    op = rng.choices(list(WEIGHTS), weights=list(WEIGHTS.values()))[0]
    u = rng.uniform
    q = lambda x: round(x * 4) / 4                                                 # noqa: E731  (quarter feet)
    if op == "move_house":
        return {"op": op, "dx": q(u(-12, 12)), "dy": q(u(-12, 12))}
    if op == "move_floor":
        return {"op": op, "k": rng.randrange(4), "dx": q(u(-6, 6)), "dy": q(u(-6, 6))}
    if op == "stretch":
        return {"op": op, "face": rng.randrange(4), "amount": q(u(-5, 8))}
    if op == "raise_roof":
        return {"op": op, "dz": q(u(-3, 6))}
    if op == "add_floor":
        return {"op": op, "h": rng.choice([10.0, 11.0, 11.6666666667])}
    if op == "delete_floor":
        return {"op": op, "which": rng.choice(["top", "top", "middle"])}
    if op == "add_accessory":
        return {"op": op, "kind": rng.choice(["garage", "shed"]), "w": q(u(8, 24)), "d": q(u(8, 24)),
                "h": q(u(8, 15)), "where": rng.choice(["rear", "rear", "side", "front", "attached"]),
                "face": rng.randrange(4), "fx": round(u(0, 1), 2), "fy": round(u(0, 1), 2), "gap": q(u(1, 12)),
                "listed": rng.random() < 0.75, "frame": rng.choice([True, False, None])}
    if op == "add_porch":
        kind = rng.choice(["porch", "deck", "steps"])
        return {"op": op, "kind": kind, "face": rng.randrange(4), "t0": round(u(0, 0.5), 2),
                "span": round(u(0.15, 0.5), 2), "depth": q(u(2, 9)),
                "h": {"porch": 10.0, "deck": 2.5, "steps": 1.5}[kind]}
    if op == "add_roof":
        return {"op": op, "kind": rng.choice(["roof", "roof", "mansard"]), "axis": rng.randrange(2),
                "over": rng.choice([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]), "fascia": rng.choice([0.0, 0.0, 0.5, 1.0]),
                "inset": q(u(2, 5)), "rise": q(u(6, 14))}
    if op == "add_dormer":
        return {"op": op, "side": rng.randrange(2), "t0": round(u(0.1, 0.5), 2), "span": round(u(0.15, 0.3), 2),
                "past": rng.choice([0.0, 0.0, 0.5, 1.0, 1.5]), "h": q(u(5, 8))}
    if op == "rotate":
        return {"op": op, "deg": round(u(-10, 10), 1)}
    if op in ("cross_line", "off_lot"):
        return {"op": op, "target": rng.choice(["house", "house", "accessory"]), "line": rng.randrange(6),
                "amount": q(u(0.5, 10))}
    if op == "plain_wing":
        n = rng.randint(1, 4)
        return {"op": op, "n": n, "face": rng.randrange(4), "depth": q(u(8, 16)), "h": 10.0,
                "typed": rng.choice([None, rng.randint(1, n), max(1, n - 1), n + 1])}
    if op == "shift_floor":
        return {"op": op, "k": rng.randrange(4), "dz": rng.choice([q(u(-4, -0.25)), q(u(0.25, 6))]),
                "carry": rng.random() < 0.3}
    if op == "floor_wing":
        k = rng.choice([1, 2])
        return {"op": op, "heights": [q(u(6, 25)) for _ in range(k)], "face": rng.randrange(4),
                "depth": q(u(8, 16)), "below": rng.choice([0.0, 0.0, q(u(3, 8))]),
                "typed": rng.choice(["none", "below", "equal", "above"])}
    if op == "grade":
        return {"op": op, "value": rng.choice(["finished", "existing"])}
    raise KeyError(op)


WEIGHTS = {"move_house": 12, "move_floor": 8, "stretch": 12, "raise_roof": 8, "add_floor": 6, "delete_floor": 4,
           "add_accessory": 10, "add_porch": 8, "add_roof": 10, "add_dormer": 4, "rotate": 5, "cross_line": 3,
           "off_lot": 2, "grade": 2, "plain_wing": 4, "floor_wing": 5, "shift_floor": 6}


def random_case(rng: random.Random) -> dict:
    """A lot and 1 to 6 edits; which deeper invariants to run on it (c on a quarter of the cases, d on a fifth, with
    Rhino files on 1 in 16, e on a tenth), and the moves invariant c makes (toward which lot line, how far; which
    face is pulled in, how far)."""
    return {"lot": rng.choice(LOTS), "edits": [random_edit(rng) for _ in range(rng.randint(1, 6))],
            "deep": {"c": rng.random() < 0.25, "d": rng.random() < 0.2, "d_files": rng.random() < 0.0625,
                     "e": rng.random() < 0.1},
            "probe": {"line": rng.randrange(6), "step": round(rng.uniform(0.5, 3), 2), "face": rng.randrange(4),
                      "shrink": round(rng.uniform(1, 3), 2)}}


# ---- Gordium's input: faces, as the Rhino command sends them ----------------------------------------------------

def _prism_faces(outline, z0, z1):
    n = len(outline)
    walls = [[[*outline[i], z0], [*outline[(i + 1) % n], z0], [*outline[(i + 1) % n], z1], [*outline[i], z1]]
             for i in range(n)]
    return [[[x, y, z0] for x, y in outline], [[x, y, z1] for x, y in outline], *walls]


def _gable_faces(p):
    """A gable roof solid (as test_every_reading.roof draws one): level soffit at `base` reaching `over` past the
    two eave walls, a `fascia` deep vertical edge, slopes up to the ridge over the middle; built in the walls'
    own frame (p0 -> p1 across, p0 -> p3 along the ridge)."""
    p0, p1, _, p3 = p["corners"]
    ux, uy = p1[0] - p0[0], p1[1] - p0[1]
    w = math.hypot(ux, uy)
    ux, uy = ux / w, uy / w
    vx, vy = p3[0] - p0[0], p3[1] - p0[1]
    dl = math.hypot(vx, vy)
    vx, vy = vx / dl, vy / dl

    def at(x, y, z):
        return [p0[0] + x * ux + y * vx, p0[1] + x * uy + y * vy, z]
    xa, xb, xm, base, lo, ridge = -p["over"], w + p["over"], w / 2, p["base"], p["base"] + p["fascia"], p["ridge"]
    y0, y1 = 0.0, dl
    faces = [[(xa, y0, base), (xb, y0, base), (xb, y1, base), (xa, y1, base)],
             [(xa, y0, lo), (xm, y0, ridge), (xm, y1, ridge), (xa, y1, lo)],
             [(xm, y0, ridge), (xb, y0, lo), (xb, y1, lo), (xm, y1, ridge)]]
    if p["fascia"]:
        faces += [[(xa, y0, base), (xa, y1, base), (xa, y1, lo), (xa, y0, lo)],
                  [(xb, y0, base), (xb, y1, base), (xb, y1, lo), (xb, y0, lo)],
                  [(xa, y0, base), (xb, y0, base), (xb, y0, lo), (xm, y0, ridge), (xa, y0, lo)],
                  [(xa, y1, base), (xb, y1, base), (xb, y1, lo), (xm, y1, ridge), (xa, y1, lo)]]
    else:
        faces += [[(xa, y0, base), (xb, y0, base), (xm, y0, ridge)], [(xa, y1, base), (xb, y1, base), (xm, y1, ridge)]]
    return [[at(*q) for q in f] for f in faces]


def _mansard_faces(p):
    lo, hi, z0, z1 = p["outline"], p["top_outline"], p["z0"], p["z1"]
    return [[[*q, z0] for q in lo], [[*q, z1] for q in hi]] + [
        [[*lo[i], z0], [*lo[(i + 1) % 4], z0], [*hi[(i + 1) % 4], z1], [*hi[i], z1]] for i in range(4)]


def part_faces(p):
    if p["kind"] == "roof":
        return _gable_faces(p)
    if p["kind"] == "mansard":
        return _mansard_faces(p)
    return _prism_faces(p["outline"], p["z0"], p["z1"])


def gordium_site(design: dict, order: str = "as_drawn") -> dict:
    """The site as the Rhino command sends it (lot lines and each solid's faces, in feet). `order`: "reversed" draws
    every outline and face the other way round, "shifted" starts each one at its next point (the same design)."""
    def o(points):
        if order == "reversed":
            return list(reversed(points))
        if order == "shifted":
            return points[1:] + points[:1]
        return points
    pts = [list(p) for p in o(list(design["lot"]["points"]))]
    n = len(pts)
    buildings = []
    for p in design["parts"]:
        b = {"id": p["id"], "faces": [{"points": o(f)} for f in part_faces(p)], "problems": []}
        if p["kind"] == "floor":
            b["floor"] = p["z1"] - p["z0"]
        buildings.append(b)
    return {"units": "ft", "problems": [], "buildings": buildings,
            "lot": {"id": "lot", "edges": [{"points": [pts[i], pts[(i + 1) % n]], "curved": False} for i in range(n)]}}


def gordium_facts(design: dict) -> dict:
    f = lot_facts(design["lot"])
    f["grade_is"] = design["grade_is"]
    if design["listed"]:
        f["accessory_buildings"] = list(design["listed"])
    if design["frame"] is not None and design["listed"]:
        f["accessory_frame"] = design["frame"]
    if design.get("typed_stories") is not None:
        f["stories"] = design["typed_stories"]
    return f


# ---- the same design as a Rhino file (units, one solid, mesh) ---------------------------------------------------

SCALE = {"ft": (r.UnitSystem.Feet, 1.0), "in": (r.UnitSystem.Inches, 12.0), "mm": (r.UnitSystem.Millimeters, 304.8)}


def _mesh(faces, s):
    m = r.Mesh()
    index = {}
    for f in faces:
        ids = []
        for x, y, z in f:
            key = (round(x, 9), round(y, 9), round(z, 9))
            if key not in index:
                index[key] = len(index)
                m.Vertices.AddPoint3d(x * s, y * s, z * s)        # double precision, as Rhino keeps them
            ids.append(index[key])
        for k in range(1, len(ids) - 1):
            m.Faces.AddFace(ids[0], ids[k], ids[k + 1])
    m.Normals.ComputeNormals()
    m.Compact()
    return m


def _box(outline, z0, z1, s):
    c = r.PolylineCurve([r.Point3d(x * s, y * s, z0 * s) for x, y in list(outline) + [outline[0]]])
    e = r.Extrusion.Create(c, (z1 - z0) * s, True)
    b = e.ToBrep(True)
    zs = [b.Vertices[i].Location.Z for i in range(len(b.Vertices))]
    if max(zs) < z1 * s - 1e-6:
        b = r.Extrusion.Create(c, -(z1 - z0) * s, True).ToBrep(True)
    return b


def write_3dm(design: dict, path: Path, units: str = "ft", style: str = "blocks") -> Path:
    """The design as a .3dm: the lot on Site, every part on Building. style "blocks": floors (and other boxes) as
    solids, the floors marked as GordiumStart marks them, roofs as closed meshes; "mesh": every part a closed
    mesh (no floor marks: a mesh can't carry them); "one_solid": the stacked floors drawn as one solid with no
    marks (only when they share one outline and stack without gaps)."""
    unit, s = SCALE[units]
    m = r.File3dm()
    m.Settings.ModelUnitSystem = unit
    for name in ("Site", "Building"):
        layer = r.Layer()
        layer.Name = name
        m.Layers.Add(layer)

    def attrs(layer, floor=None, oid=None):
        a = r.ObjectAttributes()
        a.LayerIndex = layer
        if floor:
            a.SetUserString(FLOOR_KEY, floor)
        if oid:
            a.SetUserString(ID_KEY, oid)
        return a
    pts = design["lot"]["points"]
    m.Objects.AddPolyline(r.Polyline([r.Point3d(x * s, y * s, 0) for x, y in list(pts) + [pts[0]]]), attrs(0))
    parts = design["parts"]
    if style == "one_solid":
        fl = _floors(design)
        same = fl and all(Polygon(f["outline"]).equals(Polygon(fl[0]["outline"])) for f in fl) and all(
            abs(b["z0"] - a["z1"]) < 1e-9 for a, b in zip(fl, fl[1:]))
        if not same:
            raise ValueError("floors don't stack on one outline")
        m.Objects.AddBrep(_box(fl[0]["outline"], fl[0]["z0"], fl[-1]["z1"], s), attrs(1, oid="house"))
        parts = [p for p in parts if p["kind"] != "floor"]
    for k, p in enumerate(parts):
        if style == "mesh" or p["kind"] in ("roof", "mansard"):
            m.Objects.AddMesh(_mesh(part_faces(p), s), attrs(1, oid=p["id"]))
        else:
            mark = f"{k + 1};{p['z1'] - p['z0']}" if p["kind"] == "floor" else None
            m.Objects.AddBrep(_box(p["outline"], p["z0"], p["z1"], s), attrs(1, mark, p["id"]))
    m.Write(str(path), 8)
    return path
