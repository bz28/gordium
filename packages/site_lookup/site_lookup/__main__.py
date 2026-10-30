"""python -m site_lookup "106 Ithaca Rd, Ithaca, NY 14850" [--json] [--place <state>/<place>]
prints the looked-up site facts (asks the live services), with the place's own lookup (default: the only place
with settings)."""

import json
import sys

from rule_format.rulebook import utf8_console

from rule_format.place import UnknownPlace, only_place

from .adapters import adapter
from .http import Http


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
    where = None
    if "--place" in args:
        k = args.index("--place")
        if k + 1 >= len(args):
            print("--place needs a place: --place <state>/<place>")
            return 2
        where, args = args[k + 1], args[:k] + args[k + 2:]
    if len(args) != 1 or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 2
    try:
        found = adapter(where or only_place("python -m site_lookup", "say which with --place <state>/<place>"))
    except UnknownPlace as e:
        print(e)
        return 2
    r = found.lookup.lookup(args[0], Http())
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
    utf8_console()                     # a ✓ or an en dash in a lookup can't crash a Windows console or pipe
    sys.exit(main(sys.argv[1:]))
