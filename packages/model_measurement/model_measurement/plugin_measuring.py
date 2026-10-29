"""The measuring of the place the Rhino plugin checks (rule_format.place.plugin_place: the City of Ithaca's,
places/ithaca_city/measure.py, for now), for shared code that reads its names without lot facts at hand (the
checker's display, the envelope builder, the coverage audit). This module *is* that place's measure module: importing
it gives the same module object, so a name read or changed here is the place's own. A measurement of a lot is asked
of its own place instead (places.measuring(facts["jurisdiction"])), as project.project and the checker do."""

import sys

from rule_format.place import plugin_place

from .places import measuring

sys.modules[__name__] = measuring(plugin_place())
