# #27 check-button 2c7c875, Rhino 8 (2026-10-27)

- pass2 scale (claim 7): PASS (pass2_scale/).
- undo_steps scripted: 32 of 62, FOR THE RECORD only (one scripted _Undo cannot separate records; two_in_a_row and 'only its own record undone' are not counted either way).
- demo smoke: 7 of 7 (smoke/).
- REAL INPUT (real_input/: real clicks via System Events and CGEvent, real Cmd+Z, manual line typed at the command line, state read by read-only scripts read2.py / ticks.sh; screenshots): see the table in the commit STATUS line. All PASS: Hide starting house (layer AND tick back), labels then Check after every edit (one Cmd+Z each, ticks follow), Show neighbourhood (tick back; no neighbourhood drawn in this file, so no layers to see), Use my survey (via the start box, one Cmd+Z), Enter (Bedrooms 2, Parking 1: one Cmd+Z), Add to check (both objects back to Default), This is the ground, Not the ground, Main building (Building2). Each left the typed line (curves 2) in place.
