"""Measuring a story's escape routes from an interior description (docs/decisions/2026-11-20_route_measurement.md).

Built so far: floor.py reads each story's floor, zones and rings (decisions 1, 1a, 10); paths.py draws decision 2's
routes exactly, defined only from points clear of every ring; remote.py gives decision 3's story travel figure, a
proved upper bound from samples (the clear floor, and each ring cluster's clear edge plus its margin). Common path,
dead ends, remoteness, areas and the parts handed to the rules are later steps of the note's order.
"""
