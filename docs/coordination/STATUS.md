# Status (one line per lane)

See HANDOFF.md lanes table (2026-10-22 00:45). Update here as lanes move.

## 2026-10-22 01:00 — local coordinator
- #21 round 11 review DONE locally: findings in findings/pr21_round11.json (do not re-run round 11; fix these, then run round 12).
- Rhino job (local): round-6 corner root fix (lot width = frontage on ONE right-of-way, §325-8 col. 7; street_ids; shared street_lines.py), Windows console fix (gordium_ui.spawn, CREATE_NO_WINDOW, os.startfile), process-leak fix (ServerBook) committed on arch-fixes-2 770a1c0, full CI running; Rhino blocked by locked screen. Copy QUICKSTART Windows confirm line into DEMO.md at the demo update. #19 must carry street_ids through pick_effect + lookup.

## 2026-10-22 00:45 — cloud coordinator took over its lanes
- #21 drafting-stage1 84f4920: fixing round-11's 4 findings (R-3b §325-19E demotion, `relaxes` in the approval hash, demote() drops `relaxes`, code-made flag's author), then review round 12. No spend.
- #23 context-map c783ee6 (wip e3a7a64): revert-checks + full suite for the round-2 fixes, push, then review round 3. In-Rhino claims PENDING (RHINO_QUEUE 4).
- r2-hand 1b15c9f: round 8 clean (local). Re-running the full suite here, then opening the PR (base answer-keys).
- #18 measurement-2 ecd820b / #20 answer-keys c342d10: waiting for #15's f1b51a6 to reach term-index (only rhino-ui has it now).
- #22 stress-tests a460e4e: waiting for measurement-2 to move.
- Local lanes (stack-keeper; Rhino job arch-fixes-2, wip 770a1c0): moving; not touched.

## 2026-10-22 01:10 — cloud coordinator
- r2-hand 1b15c9f: PR #24 OPENED (base answer-keys). full_suite re-run here: 1606 passed, 9 skipped, 9 xfailed; CI steps 7 run, all passed. Round 8 clean. Waits for Ben.
- #23: Rhino job found claim 1 fails on c783ee6 (setting the parent Gordium::Context's IsVisible unlocks every sublayer in Rhino 8); fix = re-lock at the end of _context_visible (13/13 in Rhino as a scratch patch). Routed to the #23 owner with round-2 fixes and #19 7efb1bd merge; Rhino job re-runs context_in_rhino.py on the pushed head.
- #19 start-box-lookup moved to 7efb1bd (local round-2 fixes).

## 2026-10-22 01:20 — NEW cloud coordinator (claude.ai/code session_01SmWnLmvUdPFUNqGnscv1y5; Ben started it on the cloud credits)
- I now own every non-Rhino lane in HANDOFF.md: #21, #23, #24/r2-hand, #18, #20, #22, #17 carries, review loops, demo update.
- ANY OTHER "cloud coordinator" (incl. the one launched from the local session): stop, push WIP to wip/<branch>, and add a line here saying where you stopped. Do not push to #21/#23/r2-hand after this line.
- Local stack-keeper + Rhino job: keep going. I take a local lane over only after 2 hours with no push to its branches (wip/* included); I check before touching them.
- Starting: #23 (wip e3a7a64 round-2 fixes + re-lock line in _context_visible + #19 7efb1bd merge), #21 round-11 fixes.

## 2026-10-22 01:30 — local coordinator: the earlier coordinator is STOPPED
It turned out to run locally, not in the cloud. What it left (all unreviewed — review before building on it):
- #21 drafting-stage1 e5e5f09: round-11 fixes (one §325-19E answer for R-3a and R-3b; relaxes in the approval hash and dropped on demote; code-made flag author). Next: review round 12.
- #23 wip/context-map 955d97f (on 7a1b1e1, merge of start-box-lookup): its rounds 3–4 incl. the Rhino job lock fix (context layers stay locked after any show/hide). Not on context-map yet. Next: full CI, push, review, then RHINO_QUEUE 4 re-run.
- #24 opened (R-2 hand rulebooks).
The new cloud session (5549908) owns these lanes from here.

## 2026-10-22 01:35 — correction to the line above
- #23: context-map AND wip/context-map are both at 955d97f, full suite green (1554 passed; 7 CI steps). Rounds 3-4 findings: findings/pr23_round3.json, pr23_round4.json. Round 4 hit the cap with confirmed findings → round-4 fixes need one more cold round. PR description stale (still shows old 11/11 Rhino run as current; mark in-Rhino claims PENDING). RHINO_QUEUE 4 = context_in_rhino.py at 955d97f (local Rhino job will run it).
- #21: e5e5f09 full suite green (1666 passed); round 12 incomplete: cold reviewer raised one minor (demoting a rule another rule widens fails validation), sceptics NOT run → findings/pr21_round12.json (incomplete).
- Any full_suite.py run that exited 143 around 00:50-01:20 was killed by the old coordinator (pkill) — re-run.

## 2026-10-22 01:50 — local Rhino job
- RHINO_QUEUE 4 DONE: #23 context_in_rhino.py at 955d97f 15/15 + context_tick_in_rhino.py 10/10 (lock fix holds). Evidence commit 0516aa7 on wip/pr23-rhino-955d97f (fast-forwards from 955d97f): fast-forward context-map to it and update #23 Test Plan to show these as current.
- RHINO_QUEUE 1 (pass2 26/26) and 3 (#19 R-2a 8/8 at 7efb1bd) DONE. arch-fixes-2 full suite re-running (earlier run was killed by the pkill).

## 2026-10-22 06:00 UTC (02:00 EDT) — cloud coordinator
- #21 drafting-stage1 e5e5f09: review round 12 CLEAN (0 found; 4/4 round-11 fixes confirmed; findings/pr21_round12_cloud.json). Suite here: pytest 1666 passed + 3 CI steps (run timed out in rule_export; reviewer ran rule_export/project_report --check green). PR comment posted. Waits for Ben (spend items unchanged).
- #23 context-map: round 5 (cold, on 0516aa7) confirmed 2 P2s in _clear_context: with "Gordium" locked the parent's IsVisible re-locked the context layers before the delete (drawn twice); and the restore unlocked the architect's Gordium::Grade/Massing. Fixed in a6a74ab (every layer under the top parent opened outermost first, put back exactly; refused delete is said); 4/4 revert checks; new in-Rhino claim. Full suite running; then push (context-map ← 0516aa7 + a6a74ab), round 6. RHINO_QUEUE 7.
- Local stack-keeper + Rhino job are active (pushes 01:32 EDT): not taken over.

## 2026-10-22 06:40 UTC — cloud coordinator
- #23 context-map PUSHED 5298ef4 (= 955d97f + 0516aa7 Rhino evidence + rounds 5-7 fixes). Review round 8 CLEAN. Full suite (cloud): 1557 passed, 7 CI steps all passed. PR body Test Plan rewritten (current state first; b908e99 run superseded). In-Rhino: RHINO_QUEUE 7 (one new claim) PENDING. Next: merge #19 once it settles (beaf9c5 now; wip abe60a0).
- Lesson logged: never run the full suite in a checkout you are editing (two cloud runs were thrown away); suites now run in /home/user/wt/suite_*.
- Local lanes still active (Rhino job 06:00 UTC on wip/arch-fixes-2 round 7; stack-keeper 05:32 UTC). Takeover check for stack-keeper at ~07:32 UTC.

## 2026-10-22 07:38 UTC — cloud coordinator TAKES OVER the stack-keeper (2-hour rule: no push since 05:32 UTC)
- Local stack-keeper: please don't push to start-project/rhino-ui/site-lookup/term-index/measurement-2/answer-keys/drafting-stage1/stress-tests/r2-hand or their wip/* from now on; if you are still running, write a line here and stop.
- Plan: #15 rhino-ui 304e9e6 review round 9 (running) → wip/site-lookup 38f112e and wip/term-index 68a8eec (rhino-ui rounds 6-8 merged in) full suite → push → #18 measurement-2 merge term-index + P2 → #20/#21/#22/#24 catch-ups; each with full suite + review.
- Rhino job (last push 06:00 UTC on wip/arch-fixes-2): takeover of its code lanes after 08:00 UTC if still quiet; Rhino runs stay in RHINO_QUEUE.

## 2026-10-22 08:05 UTC — cloud coordinator TAKES OVER the Rhino job's CODE lanes (2-hour rule: no push since 06:00 UTC)
- arch-fixes-2 (wip 4c76a40, round 7), #19 start-box-lookup (wip abe60a0 = 0f2213b round 3 + site-lookup carry), relookup (wip 1099937). Local Rhino job: don't push these from now on; Rhino RUNS stay yours — they wait in RHINO_QUEUE with exact scripts.
- Stack-keeper lanes (taken 07:38): #15 rhino-ui review round 9 found a P2 (buried check on the house's grade); fixed a0cbb56, round 10 found 2 regressions from it (main building's own parts); fixed eb627d4; round 11 + full suite running. Carries wip/site-lookup 38f112e (1369 passed, 7 CI steps) and wip/term-index 68a8eec (1375 passed, 7 CI steps) green; they'll be re-merged with #15's final head and pushed. #18 merge of term-index (rounds 6-8 port + round-24 P2) in progress.

## 2026-10-22 ~10:00 UTC — cloud coordinator (stack-keeper + Rhino job code lanes held)
- #15 rhino-ui: rounds 9-11 (eb627d4, clean) PUSHED; then the arch-fixes-2 batch LANDED (fast-forward) → rhino-ui = arch-fixes-2 = c37738a. arch-fixes-2 rounds 8-12 (street-name validity rule; a pick names only the clicked line: rhino_logic.pick_street; same_street), round 12 CLEAN; full suite 1347 passed, 7 CI steps. In-Rhino pass2 at c37738a PENDING (RHINO_QUEUE 1 re-run); Windows confirm (RHINO_QUEUE 2) unchanged.
- #16 site-lookup f00cf1b, #17 term-index a7a0be0 PUSHED (eb627d4 carried). Now carrying c37738a: site-lookup 379d258, term-index 74ea32b — suites running.
- #18 measurement-2: merges 20e0e89 (term-index with #15 rounds 5-8 ported into #18's coverage/yards; round-24 P2 done; 'flat' branches removed) + fc2cfd8 (rounds 9-10): suite 1531 passed, 7 CI steps; review round 25 running. Not pushed yet. Then carry 74ea32b.
- For Ben/architects (flagged, not decided): (1) a stray solid with no spot grades now says "place spot grades around it" instead of "under the ground"; (2) an upper floor drawn as a plain separate solid (not Gordium floor blocks) gets #18's upper-floor-or-bay-window question (two readings); (3) once lookups name each street line, should an unnamed line between two named streets be part of the front or asked?
- Next: #19 (wip abe60a0: round-3 fix 0f2213b + carry) review + suite; #20/#21/#22/#24 catch-ups after #18; #23 carry of #19; demo update.

## 2026-10-22 ~15:30 UTC — cloud coordinator
PUSHED (each: full suite + 7 CI steps green; review loop clean where code changed):
- #15 rhino-ui c37738a (arch-fixes-2 landed) · #16 site-lookup 379d258 · #17 term-index 74ea32b (carries)
- #18 measurement-2 0668da2: merges of term-index (rounds 5-10, arch-fixes-2) ported into #18's coverage/yards/advice; rounds 25-28 (one TOUCH for yards+ground; eaves advice = yard requirement eaves included; "To comply: move it back onto the lot" only where the crossing is the row's only failing fact, else "First: …"); round 28 CLEAN; 1562 passed.
- #19 start-box-lookup aa18f7c: round 4 CLEAN (round-3 fixes 0f2213b confirmed); merge with arch-fixes-2 (pick split _pick_outcome/pick_effect; lookup via set_street_lines; replaced sample never keeps "Ithaca Rd"; lookup worker via ui.spawn); 1488 passed.
- #23 context-map 116aa34: #19 carried; round 9 found the fetch's subprocess.run (console on Windows) → ui.spawn; round 10 CLEAN; 1602 passed.
- #20 answer-keys 9d858ab (carry, 1599 passed).
- #22 stress-tests: a609f05 was pushed by mistake with 1 failing test (F15's strict xfail now XPASSes: fixed by #15's ground model). Fixed in c3b2038 (plain test); its full suite running; then push. Pushes now go through a guarded helper that refuses unless the suite log says all passed.
IN PROGRESS: #21 drafting-stage1 2a27101 and #24 r2-hand 3892d20 carries (suites running). demo-dryrun dfac7ab built (rhino-ui, term-index, measurement-2, start-box-lookup+site-lookup, answer-keys, context-map, stress-tests c3b2038; generated files current; full suite running) → demo commit with DEMO.md (2026-10-22), parent = old demo (fast-forward).
RHINO (local side): RHINO_QUEUE 7 (#23 116aa34), 8 (#15 pass2 at c37738a), plus #19 R-2a box re-run at aa18f7c, plus demo smoke (item 6) at the new demo head before Ben tells cofounders to pull.
For Ben: see the PR comments on #18, #19, #15 (flagged UX/zoning points, not decided).

## 2026-10-22 ~17:00 UTC — cloud coordinator: SECOND DEMO UPDATE BUILT
- demo = 4c07e6e (fast-forward from dfe78d1): tree = demo-dryrun-2026-10-22 dfac7ab (rhino-ui c37738a, term-index 74ea32b, measurement-2 0668da2, start-box-lookup aa18f7c + site-lookup 379d258, answer-keys 9d858ab, context-map 116aa34, stress-tests c3b2038) + DEMO.md (2026-10-22: what's new, no pip step, known limits). Full suite on the tree 1928 passed, 7 CI steps all passed; generated files current. AI zones off (#21 not in demo).
- NOT yet smoke-tested in Rhino: RHINO_QUEUE 9 (local side), then Ben tells cofounders to pull.
- #22 stress-tests c3b2038 PUSHED (F15 now fixed by #15's ground model: xfail → plain test). 
- In progress: #21 carry 0638a6f (round 13 fixed: zone gaps in Ben's words with specifics kept in the report; chart units cite "Chart p.N") → round 14 + suite; #24 r2-hand carry 3892d20 (suite green) → round 9.

## 2026-10-22 ~19:00 UTC — cloud coordinator: EVERY LANE CLEAN; demo built
| PR | head | state |
|---|---|---|
| #14 start-project | 0122b15 | unchanged, clean |
| #15 rhino-ui | c37738a | clean (round 11 + arch-fixes-2 round 12); in-Rhino pass2 re-run PENDING (RHINO_QUEUE 8) |
| #16 site-lookup | 379d258 | carry, green |
| #17 term-index | 74ea32b | carry, green |
| #18 measurement-2 | 0668da2 | clean (round 28) |
| #19 start-box-lookup | aa18f7c | clean (round 4); R-2a box re-run at aa18f7c PENDING |
| #20 answer-keys | 9d858ab | carry, green |
| #21 drafting-stage1 | 0638a6f | clean (round 14); stage 2 / spend wait for Ben |
| #22 stress-tests | c3b2038 | green (F15 fixed) |
| #23 context-map | 116aa34 | clean (round 10); in-Rhino PENDING (RHINO_QUEUE 7) |
| #24 r2-hand | 3892d20 | clean (round 9) |
| demo | 4c07e6e | built; smoke PENDING (RHINO_QUEUE 9) before Ben tells cofounders to pull |
Next (local side): RHINO_QUEUE 7, 8, 9 (+ #19 box), Windows confirmations from cofounders. Ben's decisions: flagged points in the #15/#18/#19/#21 PR comments; relookup (wip/relookup 1099937) is the next feature lane after the demo.

## 2026-10-22 18:00 — cloud coordinator: headless checks done, #19 fixes under review
- Headless (no-Rhino) checks ran on the demo build dfac7ab: 71 of 73 pass. Scripts and results are in headless/ (README there), and every claim is in the test tracker with what only Rhino can still show.
- The 2 that failed, both fixed in #19: pass 2 claim 6 was out of date (it now expects LOT_MISSING, #19's empty-file wording), and a real bug where a lookup replacing the sample's lot kept the sample's street source.
- #19 start-box-lookup, local only, not pushed yet:
  - 8b8af5e: ported the local Rhino job's 1099937. The two-zones doubt is said once, and the address's street name is kept through Draw.
  - 7a2ab6b and 87b69b4: fixes for review round 1's two confirmed findings (with the real lookup answer the doubt was still said twice; the kept name was credited to the used-live roads service), plus the two headless fixes. Each fix is revert-checked.
  - Now running: the full suite and review round 2. Then push and carry into #23.
- Next: rebuild re-lookup on the new #19 as its own PR, with scenario evals.

## 2026-10-22 evening — cloud coordinator
- #19 start-box-lookup is at 86ddf9d, pushed. Full suite: 1,492 passed, all 7 CI steps passed. Review rounds 1–3: the round-1 and round-2 findings are fixed, and round 3 was clean. PR comment posted.
- #23 context-map is at 369f389, pushed. It merges #19 86ddf9d. Full suite: 1,606 passed, all 7 CI steps passed. The merge review was clean.
- NEW PR #26 re-lookup, at 6c38707 (base start-box-lookup):
  - Look up previews and Draw resets a new address.
  - Review rounds: round 1 found 6 confirmed, round 2 found 3, round 3 found 2, round 4 found 0.
  - Full suite: 1,540 passed, all 7 CI steps passed. Headless plugin run: 46 of 46 checkable claims pass.
  - Ben decides: whether "Keep my building" should keep his own lot too.
- RHINO_QUEUE: item 5 is rewritten for #26. Item 10 is new: #19's claim 6, plus the R-2a box re-run.
- Next:
  - carry re-lookup into the demo once Ben merges or asks;
  - the queued feature list (Check button / no auto-check first).

## 2026-10-22 late — cloud coordinator
- demo is now at e631aae (it fast-forwards). It is a275dad, which is #19 86ddf9d, #23 369f389 and #26 c94fee8 merged onto the morning dry run, plus DEMO.md.
  - Full suite: 1,989 passed, all 7 CI steps passed.
  - Headless checks: 36 of 36, 37 of 37, and 46 of 46.
  - RHINO_QUEUE item 11.
- #26 re-lookup is at c94fee8, pushed. Building the demo found a bug with #23: looking up the sample's own address drew nothing, so no neighbourhood appeared. Fixed in 21793ea. Review rounds 5 and 6: round 6 was clean. Full suite: 1,549 passed.
- NEW branch check-button, based on #23 (no PR yet):
  - The Check button: nothing re-checks by itself after an edit unless "Check after every edit" is ticked.
  - Review round 1 found 4 issues, all fixed in a8d0b28 plus one test pin.
  - The headless plugin run passes 11 of 11 (headless/check_button/).
  - Next: review round 2, the full suite, then open the PR.
- PR #27 check-button opened (base context-map #23), at 2974913.
  - Review rounds: round 1 found 4 confirmed, round 2 found 2 (one a P0: the viewport kept old marks after an edit, fixed), round 3 found 2, round 4 found 0.
  - Full suite: 1,672 passed, all 7 CI steps passed. Headless plugin run: 14 of 14.
  - RHINO_QUEUE item 12.
- Next feature from the queue: highlight only the offending part, then drawing-style dimensions.
- 2026-10-25 #26 re-lookup at 8c5e664, pushed: Keep my building replaces the architect's own lot too (question and answer say so); after Undo/Redo the drawing clears and the model is re-checked; in-Rhino proof now runs outside a command with Rhino's _Undo/_Redo, plus undo_redo_probe_in_rhino.py to find what kills Redo (cause not proven yet). Full suite 1,562 passed, 7 CI steps passed; headless 52/52; review rounds 0/3/4/3 confirmed, all fixed (cap reached). Next: Rhino runs RHINO_QUEUE 5 again; Ben: typed (not looked-up) address on own lot, new site too?
- 2026-10-25 NEW PR #28 highlight-offending at 74a126a (base check-button #27): only the offending part coloured, cut per building, a roof's ridge not its eaves, Rhino boolean with the block as fallback; legend says red = every reading, amber = some, nothing where it complies. Full suite 1,680 passed, 7 CI steps passed; review rounds 2/1/0 confirmed; headless check_button 14/15 (check-15 fails on base 2974913 too). RHINO_QUEUE: offending_part_in_rhino.py + highlight_in_rhino.py at 74a126a. Next: drawing-style dimensions.
- 2026-10-25 local: #21 drafting-stage1 9c37829 pushed. Approved re-draft ($0.30 cap): $0.228 spent (ledger $5.9744): §325-16C's 2 answers cut off at 8,192 tokens (no answer; its limit now 16,000); §325-18B and lot size not reached under the cap. Verifier refuses the known-bad forms first (exception in parts; always-on flag restating a kept rule); all units replayed; 18B projection rule demoted. Grade 0 false passes vs all six keys (R-1b 38/48, R-1a 64/74, R-2a 84/98, R-2b 84/99, R-2c 85/229, R-3a 88/145). Review rounds 15-17 found 2+4+3 (one P0) confirmed, all fixed and revert-checked; round 18 clean; round 19 1 low (test docstring) fixed. Full suite 1732 passed, 7 CI steps passed. Open (Ben): §325-16C, §325-18B, lot size re-draft ~$0.48 worst case.
- 2026-10-25 #26 re-lookup at cb4b6e0, pushed: review rounds 5-8 on the in-Rhino scripts (4/3/1 confirmed, fixed; round 8 only a whitespace nit, fixed). Full suite 1,562 passed, 7 CI steps passed. Headless harness updated (054da4e, 52/52). Next: Rhino runs re_lookup_in_rhino.py + undo_redo_probe_in_rhino.py for the Redo root cause.
- 2026-10-25 #23 context-map at e997f0e, pushed: the neighbourhood layers keep their own (persistent) locks under a locked Gordium layer (found in Rhino at demo e631aae, context claim 4: unlocking Gordium left Parcels, Streets, Notes and Grade unlocked). Fake layer table now copies parent locks as Rhino does; 5 pins revert-checked; claim 4 reads own locks and the locks after unlocking Gordium. Review round 1 found 1 confirmed (fixed), round 2 found 0. Full suite 1,610 passed, 7 CI steps passed. Carried to #27 check-button at ea88c18 (1,676 passed, 7 CI steps passed): #28 and later branches on check-button should merge it. RHINO_QUEUE: context_in_rhino.py at e997f0e (or check-button ea88c18).
- 2026-10-25 #28 highlight-offending at dcbc926 (check-button ea88c18 merged; suite 1,684 passed, 7 CI steps passed). NEW PR #29 drawing-dims at ca08449 (base #28): each yard dimensioned from the building to its lot line in its status colour with ticks, the required line faint (raised under the bonus), the height dimensioned in elevations; words follow the labels tick, all hidden zoomed out. Suite 1,694 passed, 7 CI steps passed; review rounds 2/0 confirmed. RHINO_QUEUE: dimensions_in_rhino.py at ca08449. Next: depth-tested lines.
- 2026-10-25 demo (fourth update) = da3dce0, fast-forward from e631aae: context-map e997f0e (neighbourhood layers keep their own locks under a locked Gordium layer) and re-lookup 27220c5 (cb4b6e0 + Rhino evidence 39/39 and probe 8/8: Keep my building replaces the lot and says so; Undo/Redo of a new-address Draw exact) merged --no-ff, no conflicts; DEMO.md updated (no pip step). No check-button or later. AI zones off. Full suite 2006 passed, 16 skipped, 9 xfailed; 7 CI steps all passed. RHINO_QUEUE: demo smoke (item 11's steps) + context_in_rhino.py claim 4 at da3dce0, then Ben tells cofounders git pull + restart Rhino.
- 2026-10-25 demo now 00c04f1 (fast-forward from da3dce0): DEMO.md says only parcels, streets and notes stay locked (Rhino itself unlocks a sublayer locked before its parent: Grade not claimed; wip/pr23-rhino-e997f0e 8d510fe). Full suite 2006 passed, 7 CI steps all passed. Smoke at 00c04f1; context claim 4's Grade part is Rhino's own behaviour (15/16 at e997f0e).
- 2026-10-25 #26 re-lookup at 4486566, pushed: Ben's typed-address rule (an address typed and not looked up turns Draw off: "Press Look up to find … first."; typing the original back turns it on; label-only save removed). Review rounds 5/4/4/3 confirmed, all fixed; round 5 clean. Full suite 1,579 passed, 7 CI steps passed; headless 52/52. RHINO_QUEUE 5: re-run re_lookup_in_rhino.py at 4486566 (step 4's two new claims).
- 2026-10-25 local: #21 drafting-stage1 f97506a pushed. Approved retry ($0.50 cap): $0.379 spent (ledger $6.3534): §325-18B cut off at 4,096 x3 (no answer, still demoted; no retry after a cut-off now), lot size answered but again no footnoted forms, §325-16C answered as one relaxing rule but refused for an unbound 20 (retry over the cap); stories limit kept. 0 false passes vs all six keys (R-1b 37/48, R-1a 62/74, R-2a 82/98, R-2b 82/99, R-2c 84/229, R-3a 87/145). Review round 20: 2 confirmed, fixed; round 21 clean. Full suite 1736 passed, 7 CI steps passed. Next: stage 2 ($10 cap, Ben approved).
- 2026-10-25 demo 00c04f1 passed the full Rhino smoke; demo now 91b3c47 (fast-forward, DEMO.md only): known limit for corner-lot street picks (click every piece of the street edge; the sample's is 8 tax-map pieces; fix in the next update). Full suite 2006 passed, 7 CI steps all passed.
- 2026-10-25 (lock/notice job, paused for slots) #23 context-map 917a4e8: claim 4 Grade vs plain-Rhino probe + no-redraw lock fix + fake pinned to lock_probe_994012d (evidence 8649ccc in), full suite 1,617 passed; RHINO: context_in_rhino.py + lock_probe_in_rhino.py at 917a4e8. #27 check-button f6ebaac: phased check_button_in_rhino.py (+ evidence 686e262), 1,689 passed; RHINO: check_button_in_rhino.py at f6ebaac; check-button lacks #23 917a4e8 (carry pending). #15 rhino-ui 27c8e5d: notice never outlives its model (fb31d78, 1,349 passed) + compact notice placement (f2c7574/27c8e5d, test_check.py only, review round 2 pending); RHINO: notice_in_rhino.py + highlight_in_rhino.py at 27c8e5d. Left: check-15 is a real #27 bug (a box error counted as Cancel) - fix scripted, not applied; carries of #15 and #23 into #27.
- 2026-10-25 demo now 5e0a0c3 (fast-forward from 91b3c47, DEMO.md only): first Known limit, bold: R-3a lots: check side-yard eaves by hand (P0 false pass when the two side yards differ; fix in progress). Full suite 2006 passed, 7 CI steps all passed.
- 2026-10-25 #15 rhino-ui at 7a16aa6, pushed: corner street pick (demo 00c04f1 step 2: one click on one of Ithaca Rd's 8 pieces kept only that 9.8 ft piece). One function for every street click (rhino_logic.street_run): a click keeps the whole street (same name, else joints <= 15 deg and <= 30 deg in all), stops for sure at a corner (> 30 deg), another street or another click's street, asks where unclear (only a No leaves a bend out); pieces under 6 in are never a street; the suggestion is the whole street, decided in feet; the command line says "Ithaca Rd: 8 lot-line pieces, 75'-10\" of frontage". Review rounds 2/1/3/1/2 confirmed (all fixed) + extra round 6 (2 found, fixed, not sceptic-checked); 31 pins revert-checked. Full suite at 7f132e6 1,358 passed, 7 CI steps passed; after merging rhino-ui 27c8e5d, design_checker tests 371 passed. Not carried (Ben's rule): comments on #16-#29. Open for #18: a corner lot's Lot width reads every split of the street lines ("9'-7\" to 158'-4 3/8\"" on the sample): split only at corners. RHINO_QUEUE 13.
- 2026-10-25 local: #21 drafting-stage1 d4cc347 pushed. Stage 2 ($10 cap): $3.72 spent (ledger $10.0738), 171 of 173 units drafted (parking 325-20F/G on hold). 0 false passes vs all six keys (R-1b 42/48, R-1a 67/74, R-2a 90/98, R-2b 84/99, R-2c 122/229, R-3a 99/145). 49 demotions/withdrawals with causes. Review rounds 22-25 found 5 (one P0)+4+1+1, all fixed; round 26 clean. Full suite 1761 passed. P0 for #18: eave side yards not paired with wall sides (hand R-3a false COMPLIES; scratchpad/p0_eave_side.json).
- 2026-10-25 evening: #28 highlight-offending at fc0b023 (independent round 5: 3 confirmed + 2 follow-ups fixed: vault-as-walls coloured over its plan, legend never says blocks are coloured, one solid per building per check). #29 drawing-dims at f6642a9 (Rhino check 6f9e3d1 items 1-5 + independent round 5 + own rounds 6-10 fixed: labels on their line in a clear spot, complying grey, dashed required line with min tag). Full suites: #28 1,688 passed, #29 1,725 passed, 7 CI steps passed each. RHINO_QUEUE: offending_part_in_rhino.py + highlight_in_rhino.py at fc0b023; dimensions_in_rhino.py at f6642a9. Next: carry into depth-lines (round-4 halo finding pending), open its PR.
