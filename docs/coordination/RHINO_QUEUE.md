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
5. re-lookup (PR #26) at 6c38707 or later (cloud, 2026-10-22; replaces the old item 5): `apps/rhino_plugin/tests/re_lookup_in_rhino.py`: all claims. The sample → Look up 96 (model unchanged, dashed preview) → Draw (sample cleared, 96's lot drawn, no question; 96 is a corner lot so no starting house) → one Undo puts the sample back, Redo again; a new file, the sample's house edited → Look up 96 → asked once → Keep; 96 again → nothing changes. Also `box_transaction_in_rhino.py` (updated for the preview flow). Watch: after the City-guide reset, Cancel may leave an empty "Gordium: start fresh…" step in Rhino's Undo list (note it). Logic proven without Rhino: test_re_lookup.py; plugin run headless 46/46 (coordination headless/re_lookup/).
6. demo (second update): smoke — GordiumStart empty file → sample → Draw → move house 5 ft → front yard fails →
   Zoning report opens on Check.
7. context-map (#23) at a6a74ab or later (cloud, review round 5): `apps/rhino_plugin/tests/context_in_rhino.py` — all claims incl. the new
   "4 with the Gordium layer and the architect's Gordium::Grade locked, a redraw replaces (never doubles) and puts both locks back".
   Commit results beside the 955d97f run (docs/evidence/pr-23/context_results_<sha>.json + README section), push to wip/pr23-rhino-<sha>.
8. rhino-ui (#15) at c37738a (arch-fixes-2 landed; cloud, 2026-10-22): re-run `apps/rhino_plugin/tests/pass2_in_rhino.py` (replaces item 1's 432d1ae run): all claims incl. the corner multi-pick, No drops both streets, exactly one checker process and none left after; plus a single street pick on the sample (Ithaca Rd kept on all 8 lines). Screenshots to docs/evidence/pr-15-mvp/pass2/, commit on wip/rhino-ui-pass2-<sha>.
9. demo (second update) at 4c07e6e (cloud, 2026-10-22; replaces item 6's head): the smoke — GordiumStart empty file → sample → Draw → move house 5 ft → front yard fails → Zoning report opens on Check; plus a corner-lot street pick (Change… → pick both street lines → Enter) and the panel tick (neighbourhood hides/shows, layers stay locked). Then Ben tells cofounders: `git pull` and restart Rhino (no pip install this time). Also needs from cofounders on Windows: no console window; one python checker in Task Manager (item 2).
10. start-box-lookup (#19) at 86ddf9d (cloud, 2026-10-22): re-run `pass2_in_rhino.py` claim 6 (now expects LOT_MISSING, "no lot yet: draw it, or pick a closed outline on the Site layer") and the R-2a box run (RHINO_QUEUE 3): the two-zones doubt said once (on the district row only), and after Draw the Street side row still names the address's street ("Ithaca Road").
11. demo (third update) at e631aae (cloud, 2026-10-22 evening; replaces item 9's head): the same smoke as item 9, plus re-lookup (item 5's script `re_lookup_in_rhino.py`, at this head) and pass 2's claim 6. Then Ben tells cofounders: `git pull` and restart Rhino (no pip install).
