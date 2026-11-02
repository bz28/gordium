"""Each place's own measuring: one folder per place (places/<name>/measure.py), the place's definitions of each
measurement written by engineers (principle 6), chosen by the place's settings (its jurisdiction.yaml
`adapters: measurement:`, read by the registry, rule_format/place.py). Shared here: reading the model (read_3dm),
the street lines, the reasons a measurement stops (stops) and what research settled (interpretations).

A place's measure.py gives the names shared code uses: measure(site, facts), fact_conflicts, Lot, union,
envelope_grade, _projection, TAX_MAP_TOLERANCE, TAX_MAP_SLACK, tax_map_lot_area, STATED, UNITS, ASK, YARDS,
EAVE_YARDS, ACCESSORY_YARDS, LOT_LINE_MEASURES and its open questions' wording (the checker's display reads them)."""

import importlib
import sys

from rule_format.place import UnknownPlace, place


def measuring(where):
    """The measure module of the place `where` (as rule_format.place.place takes it: lot facts' jurisdiction). A place
    with no settings, or whose settings name a measuring folder that isn't here or doesn't serve it (the folder's
    SERVES), is a plain error (UnknownPlace), never another place's measuring."""
    p = place(where)
    name = p.adapter("measurement")
    try:
        found = importlib.import_module(f"{__name__}.{name}.measure")
    except ModuleNotFoundError as e:
        if e.name not in (f"{__name__}.{name}", f"{__name__}.{name}.measure"):
            raise
        raise UnknownPlace(f"{p.key}: its measuring adapter {name!r} isn't in model_measurement/places/") from None
    if p.key not in getattr(sys.modules[f"{__name__}.{name}"], "SERVES", ()):
        raise UnknownPlace(f"{p.key}: the measuring adapter {name!r} doesn't serve it (its SERVES): a place is "
                           "measured by its own law's definitions, so an engineer adds it there, citing both laws")
    return found
