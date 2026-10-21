"""An independent answer key for R-1b, used by the architect stress test (test_stress.py).

What it is: for a design described in plain terms (the lot's corners and which of its lines are street, side and
rear; each building part's plan outline and its bottom and top heights; a pitched roof's walls, overhang, fascia
and ridge), it works out each R-1b number and says, per rule, PASS, FAIL or UNDECIDED. It never reads Gordium's
measuring code (packages/model_measurement/measure.py) and never sees the faces Gordium is given: it works from the
design description itself, with shapely on plan outlines it builds here. The rules are copied by hand from
R-1b.yaml (each formula below quotes the `check` it comes from; test_oracle.py runs every worked example in
R-1b.yaml through these formulas, so a copying mistake fails).

How it decides, so it can be trusted by reading:
- Every number that the law leaves open (is an overhang an eave? which eave for a pitched roof? does a lot line on
  a jog count as side or rear? is an unlisted shed an accessory building or a second main building? is an attic a
  story?) is kept as a RANGE, lowest to highest, never one guess.
- A rule is worked out twice: once with every number at its worst (smallest yards, tallest height, largest
  coverage, largest lot depth) and once at its best. PASS = it passes even at the worst, so it passes under every
  reading. FAIL = it fails even at the best, so it fails under every reading. Anything between is UNDECIDED (the
  readings disagree, or the oracle can't measure it exactly): the stress test then makes no claim.
- NOT_PASS = the rule can't be met at all (a building wholly off the lot can't have a yard on it): Gordium must not
  say it complies.
- A tax-map lot (not surveyed) is worked out on the lot as drawn; `tolerance=True` also works it out with each lot
  line 2 ft closer (Gordium's promise: "complies even if the tax map is 2 ft off", QUICKSTART).

Where it says UNDECIDED on purpose (it can't decide exactly): spot grades not at the house's four walls or a house
that isn't one rectangle in plan on a sloped lot (the grade plane), floor blocks that don't stack (a gap), and
grade "existing" (the finished ground isn't known).

Units: feet. Heights are measured from the grade plane.
"""

import math

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

PASS, FAIL, NOT_PASS, UNDECIDED, NA = "pass", "fail", "not_pass", "undecided", "not_applicable"
EPS = 1e-6                      # ft: a value within a millionth of a foot of its limit is at the limit (passes)
NEAR = 0.25                     # ft: closer than this to the main building, a building may be read as joined
TAX_MAP_TOLERANCE = 2.0         # ft: a tax-map lot line may be this far off (QUICKSTART, "Test it yourself")
ROOF_KINDS = {"roof", "mansard"}
RULES = ("R-1b.front_yard", "R-1b.side_yards", "R-1b.rear_yard", "R-1b.lot_coverage", "R-1b.height", "R-1b.stories",
         "R-1b.yard_projections", "R-1b.accessory_buildings", "R-1b.lot_area_one_family_detached",
         "R-1b.lot_width_one_family_detached")


# ---- the rules, copied from R-1b.yaml ---------------------------------------------------------------------------
# Each takes one "world" (every number fixed) and returns the slack: >= 0 passes (by that many ft, or for coverage
# by that fraction of the lot), < 0 fails.

def rear_required(lot_depth):
    # R-1b.rear_yard: rear_yard >= max(min(0.25 * lot_depth, 50), 20)
    return max(min(0.25 * lot_depth, 50), 20)


def front_rule(w):
    # R-1b.front_yard: front_yard >= 25
    return w["front"] - 25


def side_rule(w):
    # R-1b.side_yards: side_yard_smaller >= 10 and side_yard_larger >= 10   (both: the smaller one decides)
    return w["side"] - 10


def rear_rule(w):
    return w["rear"] - rear_required(w["depth"])


def coverage_rule(w):
    # R-1b.lot_coverage: building_area <= 0.25 * lot_area
    return (0.25 * w["lot_area"] - w["area"]) / w["lot_area"]


def height_rule(w):
    # R-1b.height: building_height <= 35 or building_height <= 35 + 0.1 * 35
    #   and front_yard >= 25 + (building_height - 35) and side_yard_smaller >= 10 + (building_height - 35)
    #   and side_yard_larger >= 10 + (building_height - 35)
    #   and rear_yard >= max(min(0.25 * lot_depth, 50), 20) + (building_height - 35)
    h = w["height"]
    extra = h - 35
    bonus = min(35 + 0.1 * 35 - h, w["front"] - (25 + extra), w["side"] - (10 + extra),
                w["rear"] - (rear_required(w["depth"]) + extra))
    return max(35 - h, bonus)


def stories_rule(w):
    # R-1b.stories: stories <= 3
    return 3 - w["stories"]


def projections_rule(w):
    # R-1b.yard_projections: front_yard_eaves >= 25 + max(building_height - 35, 0) - 2, the same for each side
    #   (10 + ... - 2) and the rear (max(min(0.25 * lot_depth, 50), 20) + ... - 2)
    b = max(w["height"] - 35, 0)
    return min(w["front_eaves"] - (25 + b - 2), w["side_eaves"] - (10 + b - 2),
               w["rear_eaves"] - (rear_required(w["depth"]) + b - 2))


def accessory_rule(w):
    # R-1b.accessory_buildings: accessory_front_yard >= 25
    #   and (not accessory_distances_apply or accessory_side_yard >= 6 and accessory_rear_yard >= 3)
    slack = math.inf
    for front, side, rear in w["accessories"]:
        s = front - 25
        if w["distances_apply"]:
            s = min(s, side - 6, rear - 3)
        slack = min(slack, s)
    return slack


def lot_area_rule(w):
    # R-1b.lot_area_one_family_detached: lot_area >= 6000
    return w["lot_area"] - 6000


def lot_width_rule(w):
    # R-1b.lot_width_one_family_detached: lot_width >= 50
    return w["width"] - 50


# ---- plan geometry (the oracle's own) ---------------------------------------------------------------------------

def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    return dx / n, dy / n, n


def plan(part) -> Polygon:
    """A part as seen from above. A gable roof: its walls rectangle (corners p0..p3, eaves on the p0-p1 ends) widened
    by the overhang along p0 -> p1; everything else: its outline."""
    if part["kind"] == "roof":
        p0, p1, p2, p3 = part["corners"]
        ux, uy, _ = _unit(p0, p1)
        o = part["over"]
        return Polygon([(p0[0] - o * ux, p0[1] - o * uy), (p1[0] + o * ux, p1[1] + o * uy),
                        (p2[0] + o * ux, p2[1] + o * uy), (p3[0] - o * ux, p3[1] - o * uy)])
    return Polygon(part["outline"])


def roof_heights(part):
    """A roof part's height readings (elevations, not yet above grade): (its highest point, lowest reading, highest
    reading). Gable (§325-3 HEIGHT OF BUILDING, "the average height of a pitched ... roof", midway between eave and
    ridge, finding pitched_roof_midpoint); which eave is open (height_of_building#1: the lowest eave = the soffit,
    the roof edge = the top of the fascia, or the top of the wall plate = the roof surface above the wall line).
    Mansard: "to the highest level of a ... mansard roof", its top."""
    if part["kind"] == "mansard":
        return part["z1"], part["z1"], part["z1"]
    _, _, width = _unit(part["corners"][0], part["corners"][1])
    base, ridge, over = part["base"], part["ridge"], part["over"]
    edge = base + part["fascia"]
    run = width / 2 + over
    plate = edge + over * (ridge - edge) / run if run > 0 else edge
    return ridge, (min(base, edge, plate) + ridge) / 2, (max(base, edge, plate) + ridge) / 2


def _dist(shape, segments):
    return min((shape.distance(LineString(s)) for s in segments), default=math.inf)


def _union(parts):
    return unary_union([plan(p) for p in parts]) if parts else Polygon()


# ---- what the design is -----------------------------------------------------------------------------------------

def main_and_detached(design):
    """The main building (the floor blocks, and every part touching them in plan, e.g. a porch or an attached garage:
    finding attached_garage_is_main_building) and the detached buildings (each group of touching parts left)."""
    parts = design["parts"]
    shapes = [plan(p) for p in parts]
    main = {i for i, p in enumerate(parts) if p["kind"] == "floor"} or \
        {i for i, p in enumerate(parts) if p["group"] == "house"}
    grew = True
    while grew:
        grew = False
        for i in range(len(parts)):
            if i not in main and any(shapes[i].distance(shapes[j]) <= EPS for j in main):
                main.add(i)
                grew = True
    rest = [i for i in range(len(parts)) if i not in main]
    groups = []
    for i in rest:
        joined = [g for g in groups if any(shapes[i].distance(shapes[j]) <= EPS for j in g)]
        merged = {i}.union(*joined) if joined else {i}
        groups = [g for g in groups if g not in joined] + [merged]
    return [parts[i] for i in sorted(main)], [[parts[i] for i in sorted(g)] for g in groups]


def grade_plane(design, walls: Polygon):
    """(lowest, highest) grade plane, or None if the oracle can't decide it. Flat ground: the elevation given. Spot
    grades (§325-3 GRADE PLANE, "the average of finished ground level on each side of the building at exterior
    walls"): only for a house that is one rectangle in plan with exactly one spot within 0.5 ft of each of its four
    walls; the two readings (grade_plane#1: a simple average per side, or weighted by wall length) are the range."""
    if design.get("grade_is") == "existing":
        return None
    g = design["lot"]["grade"]
    if "flat" in g:
        return g["flat"], g["flat"]
    if walls.is_empty or walls.geom_type != "Polygon" or len(walls.exterior.coords) != 5:
        return None                               # not one four-sided outline
    corners = list(walls.exterior.coords)[:4]
    for k in range(4):                            # a rectangle: every corner square
        a, b, c = corners[k - 1], corners[k], corners[(k + 1) % 4]
        if abs((a[0] - b[0]) * (c[0] - b[0]) + (a[1] - b[1]) * (c[1] - b[1])) > 1e-6:
            return None
    sides = [LineString([corners[k], corners[(k + 1) % 4]]) for k in range(4)]
    spots = g["spots"]
    at = [[s for s in spots if side.distance(Point(s[0], s[1])) <= 0.5] for side in sides]
    if any(len(a) != 1 for a in at) or len({tuple(a[0]) for a in at}) != 4 or len(spots) != 4:
        return None
    simple = sum(a[0][2] for a in at) / 4
    weighted = sum(a[0][2] * side.length for a, side in zip(at, sides)) / sum(side.length for side in sides)
    return min(simple, weighted), max(simple, weighted)


def _where(shape: Polygon, lot: Polygon) -> str:
    if shape.within(lot.buffer(EPS)):
        return "inside"
    return "crossing" if shape.intersects(lot) and shape.intersection(lot).area > EPS else "off"


def measure(design, tolerance=False, tolerance_ft=TAX_MAP_TOLERANCE):
    """Every number, as a (worst, best) pair for the rules above, plus what each building is and where."""
    lot = design["lot"]
    lot_poly = Polygon(lot["points"])
    main, detached = main_and_detached(design)
    listed = set(design.get("listed") or [])
    # a building within a drawing tolerance (NEAR) of the main one may be read as joined to it (an attached garage,
    # the chart's yards) or apart (an accessory building): both readings, like a building not listed
    house = _union(main)
    near = [g for g in detached if _union(g).distance(house) <= NEAR]
    acc = [g for g in detached if all(p["id"] in listed for p in g) and g not in near]
    unlisted = [g for g in detached if g not in acc]
    full = _union(main)                                                 # everything, overhangs too
    # with every overhang an eave and a dormer past the walls a projection (yard_projections#1 is open on bay
    # windows; a dormer past the walls is read both ways): the floors, porches, decks, steps and attached buildings
    # (§325-18A: part of the building), and a dormer only where it stands over them
    floors_etc = _union([p for p in main if p["kind"] not in ROOF_KINDS | {"dormer"}])
    walls = unary_union([floors_etc] + [plan(p).intersection(floors_etc) for p in main if p["kind"] == "dormer"])
    if walls.is_empty:
        walls = full
    maybe_main = unary_union([full] + [_union(g) for g in unlisted])    # an unlisted building read as a main one
    sides_all = [s for segs in lot["sides"].values() for s in segs] + lot.get("unsure", [])
    tol = tolerance_ft if tolerance and not lot["surveyed"] else 0.0

    def side_hi(shape):
        return min(_dist(shape, segs) for segs in lot["sides"].values())

    off = _where(full, lot_poly) == "off"
    inf = math.inf
    yards = {
        "front": (_dist(maybe_main, lot["streets"]) - tol, _dist(walls, lot["streets"]) + tol),
        "side": (_dist(maybe_main, sides_all) - tol, side_hi(walls) + tol),
        "rear": (_dist(maybe_main, lot["rears"] + lot.get("unsure", [])) - tol, _dist(walls, lot["rears"]) + tol),
        "front_eaves": (_dist(maybe_main, lot["streets"]) - tol, _dist(full, lot["streets"]) + tol),
        "side_eaves": (_dist(maybe_main, sides_all) - tol, side_hi(full) + tol),
        "rear_eaves": (_dist(maybe_main, lot["rears"] + lot.get("unsure", [])) - tol, _dist(full, lot["rears"]) + tol),
    }
    if off:                                       # no yard on this lot at all: the bonus can't be had either
        yards = {k: (-inf, inf) for k in yards}
    every = unary_union([full] + [_union(g) for g in detached])
    on_lot = unary_union([walls] + [_union(g) for g in detached]).intersection(lot_poly)
    area = (every.area, on_lot.area)                                    # (worst, best)
    # with tolerance the lot depth is kept: the worst case for the rear yard is the rear line 2 ft in and the front
    # line 2 ft out (the yard 2 ft less, the depth the same), each within the tax map's 2 ft
    if tol:
        lot_area = (lot_poly.buffer(-tol, join_style="mitre").area, lot_poly.area)
    else:
        lot_area = (lot_poly.area, lot_poly.area)
    width = LineString(lot["address_street"]).length
    grade = grade_plane(design, walls)
    sections = []                                                       # (highest point, lowest, highest reading)
    for p in main:
        if p["kind"] in ROOF_KINDS:
            sections.append(roof_heights(p))
        else:
            sections.append((p["z1"], p["z1"], p["z1"]))
    top = max(s[0] for s in sections)
    h_low = min(s[1] for s in sections if s[0] >= top - EPS)          # the highest section, read lowest
    h_high = max([s[2] for s in sections] + [p["z1"] for g in unlisted for p in g])   # any section, read highest
    height = None if grade is None else (h_high - grade[0], h_low - grade[1])
    floors = sorted((p for p in main if p["kind"] == "floor"), key=lambda p: p["z0"])
    stacked = all(abs(b["z0"] - a["z1"]) <= EPS for a, b in zip(floors, floors[1:]))
    attic = any(p["kind"] in ROOF_KINDS for p in main)                  # an attic may be a story (STORY, §325-3)
    stories = (len(floors) + (1 if attic else 0), len(floors)) if stacked and floors and grade is not None else None
    # Parts drawn as plain solids (no floor marks; the agreed rule, coordinator 2026-10-21): stories are counted only
    # from floor blocks. A plain part 7 ft or taller may hold stories the drawing doesn't show, so the typed count
    # stands only as the whole building's, and only if it is at least the floors counted and the plain blocks
    # stacked; otherwise the count is open (never complies). A plain part reaching below the ground is the basement
    # question (STORY, §325-3: a basement may be a story): never complies.
    plain = [p for p in main if p["kind"] == "solid"]
    typed = design.get("typed_stories")
    stories_typed_short = stories_basement = False
    if plain and grade is not None:
        stacked_plain = max(sum(1 for q in plain if plan(q).intersection(plan(p)).area > EPS) for p in plain)
        counted = len(floors)
        if any(p["z0"] < grade[1] - EPS for p in plain):
            stories_basement = True
        elif any(p["z1"] - p["z0"] >= 7 - EPS for p in plain):
            if typed is not None and typed >= counted and typed >= stacked_plain:
                stories = (typed, typed)
            else:
                stories_typed_short = True
                stories = (math.inf, max(counted, stacked_plain))   # fails only if what is drawn is already too many
    accessories = []
    for g in acc:
        shape = _union(g)
        if _where(shape, lot_poly) == "off":
            accessories.append(None)
            continue
        accessories.append(((_dist(shape, lot["streets"]) - tol, _dist(shape, sides_all) - tol,
                             _dist(shape, lot["rears"] + lot.get("unsure", [])) - tol),
                            (_dist(shape, lot["streets"]) + tol, side_hi(shape) + tol, _dist(shape, lot["rears"]) + tol)))
    return {"yards": yards, "off": off, "area": area, "lot_area": lot_area, "width": (width - 2 * tol, width + 2 * tol),
            "depth": (lot["depth"][1], lot["depth"][0]), "height": height, "stories": stories,
            "accessories": accessories, "unlisted": len(unlisted), "frame": design.get("frame"),
            "stories_typed_short": stories_typed_short, "stories_basement": stories_basement,
            "where": {"main": _where(full, lot_poly), **{",".join(p["id"] for p in g): _where(_union(g), lot_poly)
                                                         for g in detached}}}


def _world(m, k):
    """World k (0 = worst, 1 = best) from the measured ranges."""
    w = {name: v[k] for name, v in m["yards"].items()}
    w.update(area=m["area"][k], lot_area=m["lot_area"][k], width=m["width"][k], depth=m["depth"][k])
    w["height"] = m["height"][k] if m["height"] else None
    w["stories"] = m["stories"][k] if m["stories"] else None
    w["accessories"] = [a[k] for a in m["accessories"] if a is not None]
    w["distances_apply"] = True if k == 0 else m["frame"] is True
    return w


RULE_FUNCTIONS = {"R-1b.front_yard": front_rule, "R-1b.side_yards": side_rule, "R-1b.rear_yard": rear_rule,
                  "R-1b.lot_coverage": coverage_rule, "R-1b.height": height_rule, "R-1b.stories": stories_rule,
                  "R-1b.yard_projections": projections_rule, "R-1b.accessory_buildings": accessory_rule,
                  "R-1b.lot_area_one_family_detached": lot_area_rule,
                  "R-1b.lot_width_one_family_detached": lot_width_rule}


def verdicts(design, tolerance=False, tolerance_ft=TAX_MAP_TOLERANCE) -> dict:
    """Per rule: {"verdict", "slack" (at the worst; ft, or a fraction of the lot for coverage), "why"}."""
    m = measure(design, tolerance, tolerance_ft)
    worst, best = _world(m, 0), _world(m, 1)
    out = {}
    for rule, f in RULE_FUNCTIONS.items():
        why = ""
        if rule in ("R-1b.height", "R-1b.yard_projections") and m["height"] is None:
            out[rule] = {"verdict": UNDECIDED, "slack": None, "why": "grade plane not decidable"}
            continue
        if rule == "R-1b.stories" and m["stories_basement"]:
            out[rule] = {"verdict": NOT_PASS, "slack": None, "why": "a plain part below the ground: the basement question"}
            continue
        if rule == "R-1b.stories" and m["stories_typed_short"] and m["stories"][1] <= 3:
            out[rule] = {"verdict": NOT_PASS, "slack": None,
                         "why": "a plain part 7 ft or taller and no typed count that stands (at least the floors "
                                "counted and the plain blocks stacked)"}
            continue
        if rule == "R-1b.stories" and m["stories"] is None:
            out[rule] = {"verdict": UNDECIDED, "slack": None, "why": "grade unknown or floors not stacked"}
            continue
        if rule == "R-1b.accessory_buildings":
            if m["unlisted"]:
                out[rule] = {"verdict": UNDECIDED, "slack": None, "why": "a building not listed: accessory or main?"}
                continue
            if not m["accessories"]:
                out[rule] = {"verdict": NA, "slack": None, "why": "no accessory building"}
                continue
            if None in m["accessories"]:
                out[rule] = {"verdict": NOT_PASS, "slack": None, "why": "an accessory building wholly off the lot"}
                continue
        if m["off"] and rule in ("R-1b.front_yard", "R-1b.side_yards", "R-1b.rear_yard", "R-1b.yard_projections"):
            out[rule] = {"verdict": NOT_PASS, "slack": None, "why": "the main building is wholly off the lot"}
            continue
        lo, hi = f(worst), f(best)
        verdict = PASS if lo >= -EPS else FAIL if hi < -EPS else UNDECIDED
        out[rule] = {"verdict": verdict, "slack": lo, "why": why}
    out["_measured"] = m
    return out
