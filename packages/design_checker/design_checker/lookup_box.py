"""The start box's address lookup, run as its own short-lived process (never in Rhino's Python, and not through
the checker worker, which answers one request at a time: a lookup given up on would leave it out of step):

    python -m design_checker.lookup_box "106 Ithaca Rd, Ithaca, NY 14850"            # the live services
    python -m design_checker.lookup_box "106 Ithaca Rd, Ithaca, NY 14850" --fixture 106_ithaca_rd   # recorded

prints one JSON line: site_lookup's result, where the lot lands in the model (`frame`), and exactly what the
Rhino side may write into the .3dm (`writes`, by each source's store policy in site_lookup/endpoints.yaml).
No AI; the map services' own answers, worked out by plain code."""
import json
import math
import sys
from pathlib import Path

from rule_format.rulebook import utf8_console
from site_lookup.http import Http
from site_lookup.lookup import lookup, strictest

TIMEOUT_S, RETRIES = 8.0, 1        # each map request; the Rhino side stops the whole lookup after LOOKUP_LIMIT_S
LOOKUP_LIMIT_S = 45


def _rotate(p, c, s):
    return [p[0] * c - p[1] * s, p[0] * s + p[1] * c]


def frame(result: dict) -> dict | None:
    """Where the looked-up lot lands in the model, in Gordium's feet: turned so its street side runs along +x at
    the bottom of Top view (the lot on +y), its bounding box's corner at the origin, as the sample lot sits. The
    ring keeps its order, so the street side's edge numbers still name the same lines. Ground points move with
    it; the lowest one is z = 0 (`datum_ft`, feet above NAVD88). None without a lot."""
    lot = ((result.get("facts") or {}).get("lot") or {}).get("value")
    if not lot or not lot.get("outline_ft"):
        return None
    ring = [list(p) for p in lot["outline_ft"]]
    if ring[0] == ring[-1]:
        ring = ring[:-1]
    n = len(ring)
    side = ((result.get("facts") or {}).get("street_side") or {}).get("value") or {}
    edges = [i for i in side.get("edges") or [] if 0 <= i < n]
    angle = 0.0
    if edges:                         # the street's direction: the front edges, end to end, as one chord
        dx = sum(ring[(i + 1) % n][0] - ring[i][0] for i in edges)
        dy = sum(ring[(i + 1) % n][1] - ring[i][1] for i in edges)
        if math.hypot(dx, dy) > 1e-9:
            angle = -math.atan2(dy, dx)
    c, s = math.cos(angle), math.sin(angle)
    turned = [_rotate(p, c, s) for p in ring]
    if edges:                         # the lot above its street: flip if the front ended up on top
        front_y = sum(turned[i][1] + turned[(i + 1) % n][1] for i in edges) / (2 * len(edges))
        centre_y = sum(p[1] for p in turned) / n
        if front_y > centre_y:
            angle += math.pi
            c, s = math.cos(angle), math.sin(angle)
            turned = [_rotate(p, c, s) for p in ring]
    x0, y0 = min(p[0] for p in turned), min(p[1] for p in turned)
    placed = [[round(p[0] - x0, 4), round(p[1] - y0, 4)] for p in turned]
    ground = ((result.get("facts") or {}).get("ground") or {}).get("value") or {}
    pts = ground.get("points") or []
    datum = min((p["ft"] for p in pts), default=None)
    spots = []
    for p in pts:
        q = _rotate([p["x"], p["y"]], c, s)
        spots.append([round(q[0] - x0, 4), round(q[1] - y0, 4), round(p["ft"] - datum, 3)])
    return {"ring": placed, "street_edges": edges,
            "street_line": [[placed[i], placed[(i + 1) % n]] for i in edges],
            "spots": spots, "datum_ft": datum, "rotation_deg": round(math.degrees(angle) % 360, 4),
            "origin_epsg2261_us_survey_ft": lot.get("origin_epsg2261_us_survey_ft")}


def _store(result: dict, name: str) -> str:
    keys = ((result.get("details") or {}).get(name) or {}).get("source_keys") or []
    return strictest(keys) if keys else "none"


def writes(result: dict, placed: dict | None) -> dict:
    """What the Rhino side may put in the .3dm, and nothing else (endpoints.yaml `store`):
    - the lot outline as the lot curve only from a source that may be kept (`raw`: the State's tax parcels); from
      the City's parcels (`derived`) it is a guide drawn on screen, never saved, and the architect draws or picks
      the lot (coordinator, 2026-10-20);
    - the ground points as spot grades only from a `raw` source (USGS);
    - the snapshot (site_lookup's own, already within every source's policy);
    - where the lot was placed (State Plane origin, rotation, datum), only when the lot curve itself may be kept.
    Everything else (the zone, the street side, the corner lot) stays in the box as a suggestion; it is saved only
    as the architect's own statement when they press Draw."""
    out = {"lot_ring": None, "guide_ring": None, "street_line": None, "spots": [], "frame": None,
           "snapshot": result.get("snapshot")}
    if placed is None:
        return out
    if _store(result, "lot") == "raw":
        out["lot_ring"] = placed["ring"]
        out["street_line"] = placed["street_line"]
        out["frame"] = {k: placed[k] for k in ("origin_epsg2261_us_survey_ft", "rotation_deg", "datum_ft")}
    else:
        out["guide_ring"] = placed["ring"]
    if out["lot_ring"] and _store(result, "ground") == "raw":
        out["spots"] = placed["spots"]
    return out


def box_payload(result: dict) -> dict:
    """Everything the start box needs from one lookup."""
    placed = frame(result) if result.get("status") == "found" else None
    return {"status": result.get("status"), "message": result.get("message") or "", "asks": result.get("asks") or [],
            "matches": result.get("matches") or [], "query": result.get("query"),
            "facts": result.get("facts") or {}, "details": result.get("details") or {},
            "writes": writes(result, placed)}


def _fixture_http(name: str):
    """The recorded answers site_lookup's own tests use (packages/site_lookup/tests/fixtures), for the in-Rhino
    run and the CI tests: no live call."""
    import importlib.util
    tests = Path(__file__).resolve().parents[2] / "site_lookup" / "tests"
    spec = importlib.util.spec_from_file_location("site_lookup_fixtures", tests / "test_lookup.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(tests))
    spec.loader.exec_module(mod)
    fx = mod.load(name)
    return mod.Fake(fx), mod.NOW


def main(argv: list[str]) -> int:
    fixture = argv[argv.index("--fixture") + 1] if "--fixture" in argv else None
    args = [a for k, a in enumerate(argv) if a != "--fixture" and (k == 0 or argv[k - 1] != "--fixture")]
    if len(args) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        if fixture:
            http, now = _fixture_http(fixture)
            result = lookup(args[0], http, now)
        else:
            result = lookup(args[0], Http(timeout=TIMEOUT_S, retries=RETRIES))
        print(json.dumps(box_payload(result), default=str))
    except Exception as e:                # never a traceback for the box: a plain state it can say
        print(json.dumps({"status": "error", "message": "The lookup failed: enter the site by hand.",
                          "detail": f"{type(e).__name__}: {e}", "asks": [], "matches": [], "facts": {}, "details": {},
                          "writes": {"lot_ring": None, "guide_ring": None, "street_line": None, "spots": [],
                                     "frame": None, "snapshot": None}}))
    return 0


if __name__ == "__main__":
    utf8_console()
    sys.exit(main(sys.argv[1:]))
