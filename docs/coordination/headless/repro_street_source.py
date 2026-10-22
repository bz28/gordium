"""Reproduction (no Rhino, no fakes): a lookup that replaces the sample lot and names no street keeps the sample's
street source; Draw then saves the looked-up lot's street fact credited to "the State tax map (the sample's lookup)"."""
import importlib.util, sys
from pathlib import Path
from design_checker import rhino_logic as logic
from design_checker.lookup_box import box_payload
from site_lookup.lookup import lookup
T_PATH = Path("packages/site_lookup/tests/test_lookup.py")
spec = importlib.util.spec_from_file_location("t", T_PATH); T = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(T_PATH.parent)); spec.loader.exec_module(T)
fx = T.load("106_ithaca_rd")
p = box_payload(lookup(fx["address"], T.Fake(fx), T.NOW))
p["facts"] = {k: v for k, v in p["facts"].items() if k != "street_side"}      # the answer names no street
sample = {"street_name": "Ithaca Rd", "street_source": "the State tax map (the sample's lookup)", "from_sample": True}
facts, saved = logic.lookup_choices(p, {}, sample, ["R-1a", "R-1b", "R-3a"])
print("street_name kept:", saved.get("street_name"), "| street_source kept:", saved.get("street_source"))
state = {"street_source": saved.get("street_source"), "street_name": None}
print("Draw saves street fact:", logic.fact_sources(state, "2026-10-22", confirmed=True)["street"])

# the same with a realistic answer: the street services (city_roads, state_streets) offline, the lookup still found
from site_lookup.http import Offline


class Down(T.Fake):
    def post(self, url, params):
        if T.key_of(url) in ("city_roads", "state_streets"):
            raise Offline(url)
        return super().post(url, params)


p = box_payload(lookup(fx["address"], Down(fx), T.NOW))
facts, saved = logic.lookup_choices(p, {}, sample, ["R-1a", "R-1b", "R-3a"])
print("streets offline:", p["status"], "| street_name:", saved.get("street_name"), "| street_source kept:",
      saved.get("street_source"))
