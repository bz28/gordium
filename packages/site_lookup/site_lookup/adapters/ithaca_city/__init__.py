"""The City of Ithaca's lookup: its map services (endpoints.yaml: the State's geocoder and tax parcels, the City's
GIS, the County's address points, USGS ground), the City's district and road names (names.yaml), rezonings its
online map may not show yet (amendments.yaml), and how each service's fields are read (sources.py). Its place's
values (the SWIS code, the coordinate system, the address tail) come from its jurisdiction.yaml (sources.PLACE)."""

from . import context, lookup, sources, suggest   # the modules every adapter gives (adapters/__init__.py)

__all__ = ["context", "lookup", "sources", "suggest"]
