"""python -m site_lookup "106 Ithaca Rd, Ithaca, NY 14850" [--json]
prints the looked-up site facts (asks the live services)."""

import json
import sys

from .http import Http
from .lookup import lookup


def describe(name: str, v) -> str:
    if v is None:
        return "—"
    if name == "lot":
        return f"{v['area_sf']:,.0f} sf, {len(v['outline_ft'])} corners"
    if name == "ground":
        return f"{v['min_ft']:.1f}–{v['max_ft']:.1f} ft ({len(v['points'])} points)"
    if name == "street_side":
        others = [n for n in v["streets"] if n != v["street"]]
        return f"{v['street']}, {v['frontage_ft']} ft of frontage" + (f" (also {', '.join(others)})" if others else "")
    if name == "overlays":
        return "; ".join(v) if v else "none found"
    return str(v)


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    args = [a for a in argv if a != "--json"]
    if len(args) != 1 or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 2
    r = lookup(args[0], Http())
    print(f"{r['query']}: {r['status']}" + (f" · {r['message']}" if r["message"] else ""))
    for name, f in r["facts"].items():
        d = r["details"][name]
        print(f"  {name:12} {describe(name, f['value'])}  [{d['status']}] · {f['source']} · {d['source_detail']}")
        if d.get("reason"):
            print(f"  {'':12} ↳ {d['reason']}")
    for a in r["asks"]:
        print(f"  ? {a}")
    if as_json:
        print(json.dumps(r, indent=1, default=str))
    return 0 if r["status"] == "found" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
