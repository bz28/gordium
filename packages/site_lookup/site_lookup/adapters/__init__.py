"""Each place's own lookup: one folder per place (adapters/<name>/), chosen by the place's settings (its
jurisdiction.yaml `adapters: lookup:`, read by the registry, rule_format/place.py). Each folder gives the same four
modules, with the names the start box uses: lookup (lookup, strictest, STEPS, USED_LIVE), suggest (suggest), context
(context, HALF_SIZE_FT, LIVE_ONLY) and sources (ENDPOINTS, the store policy of every source)."""

import importlib

from rule_format.place import UnknownPlace, place


def adapter(where):
    """The lookup code of the place `where` (as rule_format.place.place takes it). A place with no settings, or whose
    settings name a lookup folder that isn't here, or one that serves another place (a folder holds its own place's
    boundary codes and address ending: sources.PLACE), is a plain error (UnknownPlace), never another place's lookup."""
    p = place(where)
    name = p.adapter("lookup")
    try:
        found = importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError as e:
        if e.name != f"{__name__}.{name}":
            raise
        raise UnknownPlace(f"{p.key}: its lookup adapter {name!r} isn't in site_lookup/adapters/") from None
    serves = getattr(getattr(found, "sources", None), "PLACE", None)
    if getattr(serves, "key", None) != p.key:
        raise UnknownPlace(f"{p.key}: its lookup adapter {name!r} serves "
                           f"{getattr(serves, 'key', 'no place')}, not {p.key}: give the place a lookup of its own")
    return found
