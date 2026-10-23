# Gordium: shared context for every job (kept current by the coordinator)

Read this before each major step and before opening a PR. If your work changes something here, tell the coordinator; don't edit this file yourself.

## TOP PRIORITY (Ben, 2026-10-20 14:45)
Ben must be able to test the R-1b flow end to end in Rhino: start box → auto-generated maximum legal house → live feedback on every edit. Anything that blocks or breaks that flow beats every other task. Ben is testing on 17fb77f (15:50, his try-it copy updated): 20:15: Rhino FREE (PR #19 in-Rhino run done; nobody uses it until the coordinator says). 19:50: the PR #15/#19 job had it (lookup in Rhino on 106/109/96). Earlier 16:15: Ben had it. (16:00–16:15 the PR #15 job had it (verify the report fix, zoom check, 14 QUICKSTART tests, fresh demo into ~/Desktop/gordium_demo_kit). Nobody else uses Rhino. Pushing to rhino-ui is fine (his copy is a detached checkout).

Ben's test 14:45 on d8d6b3d: the house now appears (zoom fix confirmed). Found: plan labels (yard/lot dimension labels) are drawn in the Front and Right elevation views and pile up there; they must appear only in plan (Top) views. Fix after Ben finishes testing. (Fixed in a934dc6, but Ben's Rhino at 15:49 had not been restarted since 12:39, so the old drawing code was still loaded.)

Ben's test 15:55: the panel's "Zoning report…" button did nothing after GordiumStart (only GordiumCheck writes the report). Fix sent to the PR #15 job: the button writes + opens + says where it saved; no silent buttons.

PR #16 site-lookup: review round 4 CLEAN (46f0c89). Ready for Ben.

## Stack and who owns what (never write another job's branch)
- PRs #1–14: done, waiting for Ben to merge. Linear: 1 → 3 → … → 14 (2 any time).
- PR #15 `rhino-ui` (base start-project): UI. Owns apps/rhino_plugin, packages/design_checker, envelope_builder, model_measurement. The ONLY job allowed to use Ben's Rhino right now.
- PR 16 `term-index` (base rhino-ui): term index + synonyms, "show your work" check on open questions, research answers filed in.
- Address lookup `site-lookup` = **PR #16** (base rhino-ui): packages/site_lookup only; wiring into the start box comes after #15 lands. Output: `facts` {value, source, confirmed_by, date} + a separate `details` part per fact (status suggested/needs_review/ask, reason, service). Lot source "from tax map"; others "suggested by Gordium"; corner lot yes/no/ask. 96 Ithaca Rd is a corner lot (Ithaca Rd + Mitchell St), not a street mismatch.
- Licensing in snapshots (PR #16, 2947a64): each fact carries `source_keys` (a list of every contributing source; the strictest store policy wins); amendments are cleared only by a hand-set `map_shows_since`; a project snapshot keeps a fact only as far as endpoints.yaml `store` allows (none → no value; derived → numbers only, never outlines/positions/parcel ids). A value the ARCHITECT confirms (e.g. "R-1b, I confirm") is saved as the architect's own statement (source "confirmed by you · suggested by City map"), with no raw City data; the start-box wiring must follow this. (Coordinator decision, tell Ben.)
- PR #17 term-index (opened): field names are `research` (open questions: searched, sources, why_open, readings by name) and `findings` (kind law|reading, with quotes/sources/strength). `answers` stays reserved for architects/City (reviewers.yaml) and outranks a reading. Open questions: 19. Findings carry `still_open: [tag]` (27c5767): a finding settles only what it doesn't name there; the checker treats named parts as open (every reading). PR #18 reads each open question's named readings to apply "complies only if all pass".
- #11 renamed gis/city_tax_parcel_facts.yaml → city_tax_parcel_measurements.yaml (9e4cede) so measurement's *_facts.yaml glob doesn't pick it up.
- PR #18 `measurement-2` (base term-index) STARTED 16:00: pitched roofs, yard projections, accessory buildings, corner lots, the every-reading rule. Does not touch apps/rhino_plugin or Rhino; lists Rhino-side needs for the coordinator.
- PR #15 CLEAN at 7355105 (review round 13 clean, 980 tests). PR #16 and #17 clean. Next: `start-box-lookup` (base site-lookup, becomes #19), owned by the PR #15 job: plan first, coordinator reviews. It owns apps/rhino_plugin now.
- 20:40 PR #15 READY (rhino-ui 1932ba9; Windows fix + spot-grade fix reviews clean). Ben's try-it copy at 1932ba9.
- 21:50 Ben APPROVED drafting STAGE 1 only (~40 units, budget cap raised to $20 total): branch drafting-stage1 (base measurement-2). Stage 2 (the rest) needs Ben's OK after coordinator verification. Hand answer keys R-1A and R-3A in parallel on branch answer-keys (base measurement-2), independent of AI output.
- 23:35 Ben APPROVED up to $1 to re-run 2 drafting units (minimum lot width, §325-19E) AFTER the free fixes (cell-citation source for footnote-less chart rows; per-unit max_tokens override 325-19E: 32000). Stage 2 still needs Ben's OK.
- PR #18 design: eaves never auto-decided; full outline; eaves_confirmed fact (overhang fingerprint). Rhino panel needs 'These are eaves' confirm (queued after #18 clean).
- Ben 22:05: interior items (bedrooms, parking) OUT OF SCOPE until exterior is right. Ben's test: moving ONE floor into a yard showed 'needs review' (two readings) vs whole house 'does not comply'. PR #18 already makes it 'does not comply' (cantilever = building). Queued for PR #18 after round 4: pin one-floor-moved cases (probe: scratchpad/floor_probe.py); building crossing the lot line → 'does not comply: crosses the lot line' instead of needs review.
- STACK-KEEPER QUEUE (fixes for lower PRs, applied in the owning PR then carried up): (1) flaky timing test model_measurement/tests/test_measure.py::test_a_meshed_building_is_measured_quickly (12.1 s vs 10 s on a slow Windows runner; owner PR #12; #18 already loads rules before the clock); (2) Windows/UTF-8 fix STAYS in #15 (Ben approved 2026-10-21; noted as an exception in #15's description); (3) code-audit findings (P1s in progress); (3b) FLOAT AT EXACT LIMIT: the rule engine compares unrounded floats, so 0.2*132=26.400000000000002 → a rear yard drawn at exactly 26.4 ft FAILS (false fail at limit; owner rule_format/formula, PR #1) — verify in PR #20's review, then fix in #1; (4) docs patches per PR (pending).
- OVERLAP EXCEPTION (Ben approved 2026-10-21): where #18 already rewrites the same lines a lower-PR fix would touch, that fix goes into #18, with a line in #18's description naming the PR it belongs to. Everything else goes to its owning PR.
- AUDIT P1s: fixes on HOLD until two independent skeptics (skepticA.md / skepticB.md) confirm + map blast radius.
- PR #23 context-map (base #19): neighbourhood parcels/streets/notes saved on locked Gordium::Context::* layers; building footprints ON SCREEN ONLY (provenance unclear: County/NYSEG; Ben can allow saving later via the County email = one line in endpoints.yaml). Checker never measures Context layers. In-Rhino check queued for the Rhino job after the MVP checks (apps/rhino_plugin/tests/context_in_rhino.py).
- LATER (when real ground returns after the MVP): the lot outline and the envelope must follow the ground (spot grades/terrain), not stay flat at the lowest point while the house is drawn at its ground level (cofounder screenshot 00:21: house looked 'floating' on 106's 14 ft slope; height '—' because spot grades were at the lot edges, not the walls).
- NUMBERING: the term-index PR will get the next GitHub number (#17); the measurement PR (pitched roofs, projections, accessory, corner lots) becomes #18.
- Queued: PR 17 (base term-index): measurement + rules for pitched roofs, yard projections, accessory buildings, corner lots, "every reading" rule. Then the Rhino installer.

## Decisions that affect everyone (2026-10-20)
- **Start box (approved):** address, zoning district + "I confirm" (unticked by default; Draw disabled until ticked), use; lot, street side, ground, corner lot shown with their source + Change; one "No regrading near the house" tick. Removed: existing building, roof, floor-to-floor, ground type, massing radio.
- **Every fact** = {value, source, confirmed_by, date}. Sources: "suggested by Gordium", "the sample project", "from City map" (later), "from tax map", "survey", "entered by you". The checker is source-agnostic. site_lookup must output exactly this shape.
- **Units:** Gordium works in feet internally and converts once at the Rhino boundary (PR #15 d8d6b3d, enforced by a CI scan). EPSG:2261 is US survey feet: state the conversion used.
- **Starting house:** on a tax-map (approximate) lot it keeps 2'-0" back from every limit and under coverage at the worst case; exactly at the limits on a survey; optional design buffer (default 0). After Draw, every view is zoomed to the lot and house. Sample (106 Ithaca Rd, 73'×90'): tax map → 49'-0" × 31'-10", 35'-0", front 27'-0", sides 12'-0", rear 31'-2", coverage 23.8%; survey → 53'-0" × 30'-11" at the limits. Plan labels draw only in plan (Top) views.
- **Needs review display:** when a value was measured but the result needs review, show the value with "?" (e.g. "? 35'-0"") plus the reason; "—" only when nothing could be measured.
- **Tax-map tolerance:** ±2'-0" PER LOT LINE, applied consistently to everything (yards, lot area/width/depth, coverage, the starting house) — Ben decided 2026-10-21 after stress-test F2 (73×90 tax-map lot → worst case 69×86 = 5,934 sf). A survey removes it (exact). Long term: accuracy per data source, survey import from the start box.
- **Research results (scratchpad/code_research/answers.md):** 11 answered by the code text, 8 readings, 6 open, 3 split. Key: lot depth on irregular lots uses the Zoning Administrator's perpendicular method (Appeal #3202); corner lots treat Column 12 as a "2nd front" yard; garages count toward coverage; eaves may project ≤2'-0" into yards (§325-18B); porch steps count in yard measurements; ADUs need no parking (§325-28C(2)). For still-open items: compute every reading → complies only if all pass, fails only if all fail, else needs review.
- **Readings** are shown to the architect as "Gordium's reading · confirm with the zoning office"; City or architect answers outrank them.
- **Resolve before asking** (CLAUDE.md): whole law via the term index + synonyms, ranked research, then classify. Only the genuinely unclear goes to the architects.
- **Design doc:** the System Map (https://claude.ai/artifact/BMkp3eyrgemdqcwhi9oFxf) stays high level; only the coordinator edits it. Detailed reasoning goes in repo docs and PR descriptions.

- **Text encoding (16:55, first Windows test):** every text-mode file read/write must pass encoding="utf-8" (Windows defaults to cp1252 → "—" became "â€”" and rule_format refused). LANDED on rhino-ui (a64d1e0; review round 2 CLEAN) (Windows CI green on 3.12 and 3.14). Was: a fix job adding encodings repo-wide, PYTHONUTF8=1 for the worker, a CI scan, and a Windows CI job on rhino-ui. New code in every job must follow this.
- **Python:** 3.12 or newer works (suite passes on 3.14.8).

- BEN'S TEAM MVP LIST (2026-10-21, decisions): ground ASSUMED FLAT for the MVP (height/stories comply with a note 'assuming flat ground'; report states it; spot-grade code kept behind one switch, lookup's USGS grades unused); on-screen labels OFF by default with a 'Show on-screen labels' tick (a FAILING yard's red shortfall dimension still shows); remove the 'Ch. 325 as amended…' header line from the panel (kept in the report and the '?' legend); rename Margin → Delta everywhere (sign unmistakable: +2'-0" to spare / −1'-4" short); panel becomes a dockable Rhino panel; sample lot = the real 106 parcel outline if storable; model highlighting: RED = fails under every reading, AMBER shading = needs review, on the part involved (Ben agreed 2026-10-21); 1500×1500 ft neighbour-parcel context map queued (new feature on top of #19). Owner of the UI items: the #19/rhino job, pushing to rhino-ui only after the stack-keeper finishes #15.

## !! GITHUB ACTIONS BLOCKED (~23:45): 'recent account payments have failed or your spending limit needs to be increased' — no CI job starts; red CI is NOT a code failure. Until Ben fixes billing: run EVERY CI step locally (full pytest + rule_format + document_extraction --check + section_labeling coverage --check + rule_export --check + model_measurement --check + project_report --check) before pushing, and report local results instead of CI. Windows can't be checked locally — say so.

## MORNING DEMO TARGET (Ben, ~01:00 2026-10-21; refresh demo only with reviewed + Rhino-proven work)
demo = rhino-ui (#15: audit fixes, Rhino-freeze fix, Ben's team MVP list: flat ground, labels toggle w/ failing shortfalls, Delta wording, law line in '?' legend, dockable panel, real 106 outline, red/amber shading; 2 ft/line tax-map) + #18 (lot-line readings, per-building lot rule, roofs/eaves/garages) + #19 (lookup in start box) + #20 (hand R-1a/R-3a selectable) + #21's dropdown/code fixes WITH offer_ai_drafted_zones OFF + #23 neighbour map if its Rhino check passes + #22 stress tests (tests only; Ben: why not everything — include every PR once its review is clean; nothing half-fixed). ALSO regenerate the Desktop gordium_demo_kit to match demo (setup guide incl. QUICKSTART steps changed by the 2 ft tax-map tolerance; rules spreadsheet with new R-1b examples + R-1a/R-3a; sample zoning report; new screenshots). Morning message to Ben: what's in demo, the one command for cofounders (git pull + restart Rhino), what to try, what's still in progress.

## LANES (who may write where; the coordinator sequences overlaps)
- Stack-keeper: #1–#15 branches, and carrying fixes into site-lookup (#16) and term-index (#17); STOPS before start-box-lookup (#19) and measurement-2 (#18).
- Rhino job: start-box-lookup (#19); Ben's team UI list prepared LOCALLY off rhino-ui, pushed to rhino-ui only when the coordinator says (after the stack-keeper finishes #15).
- PR #18 job: measurement-2 only. Drafting job: drafting-stage1 only. Answer keys job: answer-keys only (never reads drafted output). Stress test: stress-tests only (findings → coordinator). Context map: context-map only (base #19). Docs: patches only, applied by the stack-keeper. Eval audit: read-only.
- Rhino app: Ben (2026-10-21): 'for mac rhino i wont be using it so u dont need to ask just use it.' Still ONE job at a time, handed over by the coordinator; jobs close every document they open and leave one empty document. Currently: the Rhino job (#19 / MVP UI) has it.
- Heavy test runs: the Mac hit load ~100 on 8 cores (timing tests fail, runs take 5x longer). While iterating run TARGETED tests only. For the FULL suite always use the slot queue (max 2 at once): from your checkout root, `/Users/benzhao/Documents/Gordium/.venv/bin/python /private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/full_suite.py`. A timing-test failure under load is environmental: re-run it alone before treating it as real.

- REVIEW CHECKOUTS (coordinator): one scratch checkout per PR under review, never shared (scratchpad/review_pr18 = #18 only, review_pr20 = #20 only). A #20 review briefly switched review_pr18 at ~23:20; PR #18 round 7 (wazh73598) may be contaminated — re-run it if its findings look off.

## Ground rules
- EVIDENCE FOR VISIBLE CHANGES (Ben, 2026-10-21): every change a user can see in Rhino gets an in-Rhino scripted check that ASSERTS the outcome, with screenshots saved under docs/evidence/<pr>/ (small PNGs) and referenced in the PR's Test Plan. Code tests alone are not enough for UI. Rhino: one job at a time (currently the Rhino job), close every document opened.
- OPS BOARD (coordinator only): https://claude.ai/artifact/KU4L2xD83xfUmXEpeok143 — on every job report, edit scratchpad/ops_board/status.json and republish ops_board.html with files {status.json}. Ben uses it to follow everything.
- NO CLEANUP PRs (Ben, 2026-10-21): any fix to code or docs that a lower PR introduced goes INTO that PR's branch, then is carried up by normal merges in stack order, done by one stack-keeper job only. Feature jobs change only their own PR's code; if you find a problem in lower-PR code, report it to the coordinator instead of fixing it in your branch.
- After every push, verify `git fetch && git log -1 origin/<branch>` equals your HEAD before reporting 'pushed' (PR #19's rounds 2-3 never left the machine because the worktree was on a detached HEAD). Push with `git push origin HEAD:<branch>`.
- In Ben's Rhino: only one job at a time, never while Ben is testing; every script closes the documents it opens (finally block), never runs interactive commands like `_-Close` from scripts, and leaves one empty document open.
- Never merge; no AI API spend; never print the API key; don't send the City/County emails (Ben is holding them).
- Review loop on every PR until a clean round, scoped to real defects. Pins must fail on revert. Beginner-friendly PR descriptions.

## HANDOFF (~03:40 2026-10-21, usage limit reached)
- Stack-keeper: #12 plane grouping must become linear (running moments + hull check, pin numpy); #13 release panel_parts; #14 stories P0 (detect duplicate ids before _stacks); #15 tax-map verdict both ways (f1784e3, local) → push in order, carry up.
- #18: generic 'fails at every height' evaluation; adopt #12 fitted-plane grouping; merge term-index when it moves.
- #23: sources-note wrap + merge 0e88250; push pending suite. Code review clean (round 10); in-Rhino 9/9.
- Rhino job (mvp-ui, local): dock 400 px + startup cmd done; next the real 106 outline in #19's frame AFTER f1784e3 merges; check why height needs review on the real outline.
- #21 done (review loop closed); stage-1 report at scratchpad/stage1_report_for_ben.md, checked.
- demo NOT yet refreshed; morning target unchanged (see MORNING DEMO TARGET).
- (later) #18 at cd18972 ready for review round 13 (fails-at-every-height via formula.truth_direction + check.fails_whatever; one _planes definition; f1784e3 merged; best case takes unmeasured at 0). NOT yet reviewed.
- #23 at da9025b: sources note wrapped (model text inside square); in-Rhino re-run of 10 claims pending.
- Rhino job: mvp-ui merged f1784e3 (0212a5e), all Rhino checks re-run green; dock floats sized/placed when no dock showing; building 106 outline in #19's frame (defaults approved). Wording for #15: name the open question in 'confirm with the zoning office'.
- (later still) Rhino job hit its turn limit mid QUICKSTART re-derivation for the real 106 outline (mvp-ui local; lot_outline_tax_map.yaml generated with #19's frame(), pure rotation 306.38°). RESUME it.
- NEW for #15/#19 owner: present._side_name names sides assuming plan north = +y; looked-up lots are rotated (106: 'East' really faces NE). Fix: facts carry plan_north_deg from the frame; name with 8-point compass after turning; drawn lots unchanged. Pins: 106 sides NE/SW; drawn rectangle East/West.
- NEW wording for #15: 'Complies under every reading, but it depends on an open question: <short name>; confirm with the zoning office.'
- #23: Sources text height too large (fails new in-Rhino claim); scale-bar claim must test curve points not bbox. Sent to its job.
- #18 cd18972 still needs review round 13.
- RULE (04:30): scratch folders are per job. Use scratchpad/<your-job-name>/... only; never write to, extract into, or clean another job's folder (scratchpad/ctx was emptied by someone; #23 now uses ctx23/). Extracted branch copies for Rhino runs go under scratchpad/rhino_ui/extract_<sha>/.

## 2026-10-21 15:20 — full_suite.py now runs ALL CI steps
scratchpad/full_suite.py (no extra args) runs pytest, then every `python -m ...` step from the checkout's own .github/workflows/ci.yml (document_extraction, rule_format, coverage, rule_export, model_measurement, project_report), and ends with "[full_suite] CI steps: N run, all passed" or the failures. Use it before every push; quote that line in reports. (Found: #18 pushed a regenerated yaml with a stale report xlsx because only pytest + one --check had run.)

## 2026-10-21 18:00 — Ben-approved queue after tonight's second demo update
- demo updated 17:40 to dfe78d1 (fast-forward; DEMO.md + PDF guide with 2 known limits). Rhino smoke 7/7 PASS.
- USER GUIDE in repo: move scratchpad/demo_review/demo_review.html content into apps/rhino_plugin/GUIDE.md (owned by #15), PDF generated from it; rule: any PR changing what an architect sees updates it; drift test compares guide's button names, districts, rule limits, not-checked list against code + rule files. Also System Map one-liners: stories from geometry (h/7 ft bound, ask only if needed), uncovered-district message, relaxes link, flat ground.
- row_verdict refinement (after Rhino batch lands): exhaustive-assumption readings (which building is main) all comply → COMPLIES with note; open LEGAL questions stay NEEDS REVIEW.
- Parking-from-drawing proposal (later, needs Ben): Building::Garage sublayer = garage; Parking layer stall rectangles counted; stall size from §325-20; typed override.
- 'Not checked yet' wording: "Not in Gordium yet — coming in a later version. Check this by hand for now: <section>" (Rhino batch).

## 2026-10-21 18:40 — Ben UX principles (apply everywhere)
- Reassure in place: anything on screen that could look like an error carries its short reason right there (e.g. starting house note "largest that complies even if tax-map lines are 2 ft off; limited by coverage 25%"; cautious envelope on tax-map lots). The architect should never need to cross-check another source to understand Gordium.
- Re-lookup to a new address = clean start: clear everything Gordium drew, draw the new lot/neighbourhood/starting house; never silently delete the architect's own work (ask once); one undo step.

## 2026-10-21 19:10 — Ben UX decisions (Rhino job, after the batch)
- Highlight only the offending part (volume beyond the yard line / above height), not the whole building.
- Drawing-style dimensions: perpendicular from building to lot line, labelled, coloured by status; vertical for height.
- On-screen lines respect depth in perspective (hidden behind solids); visible in plan.
- No auto-check by default: a Check button; results greyed + "Model changed since the last check — press Check" after edits; optional "Check after every edit" tick (off).

## 2026-10-21 19:05 — stale .pyc hazard in revert-checks
Python can keep using a cached .pyc when a file is restored to the same size within the same second, so a revert-check can make the suite run the reverted code. full_suite.py now deletes __pycache__ under packages/ and apps/ and sets PYTHONDONTWRITEBYTECODE=1. In your own revert scripts, clear __pycache__ (or run with PYTHONDONTWRITEBYTECODE=1) after each restore.

## 2026-10-23 — demo rule (Ben agreed)
Every PR goes into the demo the same day its review loop returns zero confirmed and its full suite is green; don't wait to be asked. How:
1. Rebuild the demo dry run from the pushed PR heads, in stack order (`--no-ff` merges). Never hand-edit the demo.
2. Any conflict between PRs is resolved in the dry-run merge, then reviewed: a cold round on the merge, about how the features interact. Note the resolution on both PRs, because the same one is needed when they reach main.
3. The combined build must pass the full suite and every headless check (coordination headless/).
4. The demo commit is the dry-run tree plus DEMO.md, with the old demo as a parent, so pulls fast-forward. Update DEMO.md's "What's new" and RHINO_QUEUE with the new demo head.
5. Cofounders pull only when Ben says, after his Rhino run.
If Ben rejects a PR, rebuild the demo without it.
