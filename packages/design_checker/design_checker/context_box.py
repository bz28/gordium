"""The context map for the Rhino side, run as its own short-lived process (like lookup_box, never in Rhino's Python):

    python -m design_checker.context_box --origin X Y --rotation R --shift SX SY [--parcel ID]        # live services
    python -m design_checker.context_box --origin X Y --rotation R --shift SX SY --fixture 106_ithaca_rd   # recorded

X Y: the looked-up lot's origin (EPSG:2261, US survey feet), R and SX SY: how the lookup placed the lot in the
model (lookup_box.frame: turned by R degrees, then moved by -SX, -SY), ID: its parcel (left out of the map), all
saved in the box's `lookup_frame`.
Prints one JSON line: `objects`, exactly what the Rhino side may write into the .3dm (only layers whose source's
store is `raw`: the State's parcels and streets, plus Gordium's own frame, north arrow, scale bar and credits), and
`guides`, what it may only show on screen (store `none`: the building footprints, never saved). No AI."""
import json
import math
import sys
from pathlib import Path

from rule_format.rulebook import utf8_console
from site_lookup.context import HALF_SIZE_FT, context, credits
from site_lookup.http import Http

from .rhino_logic import is_stored     # one definition of "may be kept in the file" for both sides

TIMEOUT_S, RETRIES = 6.0, 1          # each request; the Rhino side stops the whole fetch at CONTEXT_LIMIT_S
ROOT = "Gordium::Context"
LAYER_OF = {"parcels": ROOT + "::Parcels", "streets": ROOT + "::Streets", "buildings": ROOT + "::Buildings"}
NOTES = ROOT + "::Notes"
GORDIUM = "gordium"                  # the source of what Gordium draws itself (the frame, north arrow, scale bar)
SCALE_BAR_FT = 100.0


def placer(frame: dict):
    """A point in feet from the lot's origin (as site_lookup gives it) -> where it lands in the model, exactly as
    lookup_box.frame placed the lot: turned by rotation_deg, then moved by -shift_ft."""
    a = math.radians(frame["rotation_deg"])
    c, s = math.cos(a), math.sin(a)
    sx, sy = frame["shift_ft"]

    def place(p):
        return [round(p[0] * c - p[1] * s - sx, 4), round(p[0] * s + p[1] * c - sy, 4)]
    return place


def notes(half: float, credits: list[str]) -> list[dict]:
    """Gordium's own marks, in feet from the lot's origin (placed with everything else): the square's edge, a north
    arrow (grid north of NY State Plane Central: within 0.1° of true north in Ithaca), a 100 ft scale bar and the
    credit lines."""
    m = 40.0                                           # margin inside the square's corner
    tip = (half - m, half - m)
    arrow = [(tip[0] - 12, tip[1] - 50), tip, (tip[0] + 12, tip[1] - 50), (tip[0], tip[1] - 38), (tip[0] - 12, tip[1] - 50)]
    bar_y = -half + m
    bar = [(half - m - SCALE_BAR_FT, bar_y + 6), (half - m - SCALE_BAR_FT, bar_y), (half - m, bar_y), (half - m, bar_y + 6)]
    out = [{"layer": NOTES, "kind": "closed", "points": [(-half, -half), (half, -half), (half, half), (-half, half)],
            "name": "Context square, %d ft × %d ft" % (2 * half, 2 * half), "source": GORDIUM},
           {"layer": NOTES, "kind": "open", "points": arrow, "name": "North (grid north)", "source": GORDIUM},
           {"layer": NOTES, "kind": "dot", "points": [(tip[0], tip[1] + 14)], "text": "N", "name": "North",
            "source": GORDIUM},
           {"layer": NOTES, "kind": "open", "points": bar, "name": "Scale bar, %d ft" % SCALE_BAR_FT, "source": GORDIUM},
           {"layer": NOTES, "kind": "dot", "points": [(half - m - SCALE_BAR_FT / 2, bar_y + 16)],
            "text": "%d ft" % SCALE_BAR_FT, "name": "Scale bar", "source": GORDIUM}]
    if credits:
        out.append({"layer": NOTES, "kind": "dot", "points": [(-half + m, -half + m)], "text": "\n".join(credits),
                    "name": "Sources", "source": GORDIUM})
    return out


def payload(ctx: dict, frame: dict) -> dict:
    """What the Rhino side draws, placed in the model: objects (may be saved) and guides (shown only). A layer goes
    to objects only if its source's store is `raw`; anything else is a guide. The credit lines saved in the file
    are the snapshot's (a source used live is only named there)."""
    place = placer(frame)
    objects, guides = [], []
    for name, layer in ctx["layers"].items():
        for item in layer["items"]:
            pts = item.get("ring") or item.get("path")
            if is_stored(layer):
                objects.append({"layer": LAYER_OF[name], "kind": "closed" if "ring" in item else "open",
                                "points": [place(p) for p in pts], "name": item.get("id") or item.get("name") or "",
                                "source": layer["source"]})
            else:
                guides.append({"layer": name, "source": layer["source"], "points": [place(p) for p in pts]})
    saved_credits = (ctx.get("snapshot") or {}).get("credits") or []
    if any(v["items"] for v in ctx["layers"].values()):
        for o in notes(ctx["half_size_ft"], saved_credits):
            objects.append(dict(o, points=[place(p) for p in o["points"]]))
    counts = {n: len(v["items"]) for n, v in ctx["layers"].items()}
    # a layer shown only live carries its source line on screen (the panel's message), never in the file
    live = [line for n, line in credits(ctx).items() if not is_stored(ctx["layers"][n])]
    return {"status": ctx["status"], "message": ctx.get("message") or "", "objects": objects, "guides": guides,
            "credits": ctx.get("credits") or [], "live_credits": live, "counts": counts, "snapshot": ctx.get("snapshot"),
            "layers": {n: {"status": v["status"], "store": v["store"], "name": v["name"], "source": v["source"]}
                       for n, v in ctx["layers"].items()}}


def fetch(frame: dict, http, half_size_ft: float = HALF_SIZE_FT, now=None) -> dict:
    origin = frame["origin_epsg2261_us_survey_ft"]
    return payload(context([origin], http, half_size_ft=half_size_ft, origin=origin, now=now,
                           lot_id=frame.get("parcel_id")), frame)


def _fixture_http(name: str):
    """site_lookup's recorded answers (tests/fixtures/<name>_context.json) and its stand-in footprints: no live call."""
    import importlib.util
    tests = Path(__file__).resolve().parents[2] / "site_lookup" / "tests"
    spec = importlib.util.spec_from_file_location("site_lookup_fixtures", tests / "test_lookup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Fake(mod.load(name), context=mod.load(name + "_context")), mod.NOW


def _args(argv: list[str]) -> dict:
    def after(flag, n):
        i = argv.index(flag)
        return [float(v) for v in argv[i + 1:i + 1 + n]]
    out = {"frame": {"origin_epsg2261_us_survey_ft": after("--origin", 2), "rotation_deg": after("--rotation", 1)[0],
                     "shift_ft": after("--shift", 2),
                     "parcel_id": argv[argv.index("--parcel") + 1] if "--parcel" in argv else None},
           "half": after("--half", 1)[0] if "--half" in argv else HALF_SIZE_FT,
           "fixture": argv[argv.index("--fixture") + 1] if "--fixture" in argv else None}
    return out


def main(argv: list[str]) -> int:
    try:
        a = _args(argv)
    except (ValueError, IndexError):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        if a["fixture"]:
            http, now = _fixture_http(a["fixture"])
        else:
            http, now = Http(timeout=TIMEOUT_S, retries=RETRIES), None
        print(json.dumps(fetch(a["frame"], http, a["half"], now), default=str))
    except Exception as e:                 # never a traceback for the Rhino side: a plain state it can say
        print(json.dumps({"status": "error", "message": "Couldn't fetch the neighbourhood: the lot is drawn without it.",
                          "detail": f"{type(e).__name__}: {e}", "objects": [], "guides": [], "credits": [],
                          "counts": {}, "snapshot": None, "layers": {}}))
    return 0


if __name__ == "__main__":
    utf8_console()
    sys.exit(main(sys.argv[1:]))
