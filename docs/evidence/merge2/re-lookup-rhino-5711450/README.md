# #26 at 5711450 in Rhino 8 (2026-10-27)

re_lookup_in_rhino.py: 10 of 11, stops at claim 2 'one Undo takes back exactly that record': undone [295, 296, 297], draw [297]. Same script-merging effect as undo_steps (see wip/start-box-lookup-rhino-8e9fc22, undo_probe_separate_scripts), so this does not show a product fault; it also means claims 3 onward did not run, so 'all claims pass' is not shown.
