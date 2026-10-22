# Rhino queue (run on Ben's Mac only; one job in Rhino at a time)

Each entry: branch + commit, the script, what must pass. Newest at the bottom.

1. arch-fixes-2 (after the corner root fix): `apps/rhino_plugin/tests/pass2_in_rhino.py` — all claims, incl.
   corner answer No drops both streets; screenshots to docs/evidence/pr-15-mvp/pass2/.
2. Windows console fix: cannot be run on Mac; ask Ben's cofounders to confirm no console window appears and only
   one design_checker process runs (Task Manager).
3. start-box-lookup (#19) after round-2 fixes: R-2a lookup (fixture) → pick R-1b → tick → Draw enabled; label
   refreshes; reopen the file next day shows no "checked today".
4. context-map (#23) after round-2 fixes: `apps/rhino_plugin/tests/context_in_rhino.py` — parent unlocked,
   footprint selectable, dragged/lifted kept, solid on Buildings layer → needs review row, saved file keeps
   footprints with "dated 2014".
5. relookup: sample → Look up preview (model unchanged) → Draw to 96 Ithaca Rd (lot + house redrawn) → Undo.
6. demo (second update): smoke — GordiumStart empty file → sample → Draw → move house 5 ft → front yard fails →
   Zoning report opens on Check.
7. context-map (#23) at a6a74ab or later (cloud, review round 5): `apps/rhino_plugin/tests/context_in_rhino.py` — all claims incl. the new
   "4 with the Gordium layer and the architect's Gordium::Grade locked, a redraw replaces (never doubles) and puts both locks back".
   Commit results beside the 955d97f run (docs/evidence/pr-23/context_results_<sha>.json + README section), push to wip/pr23-rhino-<sha>.
8. rhino-ui (#15) at c37738a (arch-fixes-2 landed; cloud, 2026-10-22): re-run `apps/rhino_plugin/tests/pass2_in_rhino.py` (replaces item 1's 432d1ae run): all claims incl. the corner multi-pick, No drops both streets, exactly one checker process and none left after; plus a single street pick on the sample (Ithaca Rd kept on all 8 lines). Screenshots to docs/evidence/pr-15-mvp/pass2/, commit on wip/rhino-ui-pass2-<sha>.
