"""Runs `python -m <module> ...` as the plugin spawns it, with one stand-in changed for design_checker.lookup_box's
recorded answers (env GORDIUM_SHIM): "r2a": the City zoning stand-in says R-2a (a district Gordium has no rules
for) instead of the fixture's R-1b; "nostreet": the lookup's answer names no street side (as
test_a_lookup_that_replaces_the_sample_lot_never_keeps_the_samples_street_name strips it). Nothing else changes:
lookup_box.main runs as it would."""
import os
import runpy
import sys

argv = sys.argv[1:]
mode = os.environ.get("GORDIUM_SHIM", "")
if argv[:2] == ["-m", "design_checker.lookup_box"]:
    from design_checker import lookup_box as lb
    original_http, original_payload = lb._fixture_http, lb.box_payload

    def _fixture_http(name):
        http, now = original_http(name)
        if mode == "r2a":
            type(http).post.__globals__["STAND_IN_ZONE"] = "R-2a"     # the fixture module's own stand-in
        return http, now

    def box_payload(result, *a, **k):
        p = original_payload(result, *a, **k)
        if mode == "nostreet":
            p["facts"] = {k2: v for k2, v in p["facts"].items() if k2 != "street_side"}
        return p
    lb._fixture_http, lb.box_payload = _fixture_http, box_payload
    sys.argv = ["lookup_box"] + argv[2:]
    sys.exit(lb.main(argv[2:]))
sys.argv = [argv[1]] + argv[2:]
runpy.run_module(argv[1], run_name="__main__", alter_sys=True)
