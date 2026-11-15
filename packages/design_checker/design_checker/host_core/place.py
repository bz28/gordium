"""The place the checker works for (its name, its address words, its time zone), read from place.json.

Moved here unchanged from rhino_logic.py, which still offers every name (so the Rhino plugin is
unchanged). Python 3.9 and the standard library only: Rhino 8 imports this into its own Python 3.9,
where none of the .venv's packages are installed."""

import json
import os

__all__ = ['PLACE', '_ADDRESSES']


# The place the plugin checks (its only place, for now), from the place registry: its settings file,
# regulations/jurisdictions/<state>/<place>/jurisdiction.yaml, copied for Rhino's Python (which can't read YAML) into
# place.json one folder up by `python -m rule_format place --write` (CI checks the copy is current). Every value
# below that names the place (its name, the address tail, its own words and ZIP codes, its time zone) comes from it.
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "place.json"), encoding="utf-8") as _f:
    PLACE = json.load(_f)
_ADDRESSES = PLACE["addresses"]
