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
