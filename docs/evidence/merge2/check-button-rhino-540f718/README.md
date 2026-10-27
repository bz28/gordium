# #27 at 540f718 in Rhino 8 (2026-10-27)

- undo_steps: 32 of 62, same pattern and same caveat as #19 8e9fc22 (two_in_a_row records [282, 283], one _Undo took [283, 282, 281]; control passes).
- demo smoke (smoke/): 7 of 7.
- pass2 step scale at 540f718: FAILS claim 7 'the lot's zoom came to rest (its labels placed)': all 8 labels (4 yards, 4 edge lengths) were painted but STATE drawn settled stayed False for the lot (neighbourhood settled True). Twice at rhino-ui e8c3654, once here. See wip/rhino-ui-rhino-e8c3654 for the files (pass2_scale).
