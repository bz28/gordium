"""Shrink the Town-of-Ithaca fixture: its parcels are a 590-acre campus (188 KB of outline). The test only
needs their SWIS codes, so each outline is replaced by a 10 ft square at the address point. Run once after
capture.py; the change is recorded in the fixture's "trimmed" field."""

import json
from pathlib import Path

p = Path(__file__).parent / "953_danby_rd_town.json"
d = json.loads(p.read_text())
point = None
for a in d["answers"]:
    if a["source"] == "geocoder":
        point = a["body"]["candidates"][0]["location"]
for a in d["answers"]:
    if a["source"] == "state_parcels":
        for feat in a["body"].get("features", []):
            x, y = point["x"], point["y"]
            feat["geometry"] = {"rings": [[[x - 5, y - 5], [x + 5, y - 5], [x + 5, y + 5], [x - 5, y + 5], [x - 5, y - 5]]]}
d["trimmed"] = "state_parcels outlines replaced by 10 ft squares at the address point (only SWIS is tested)"
p.write_text(json.dumps(d, indent=1))
print(p.stat().st_size)
