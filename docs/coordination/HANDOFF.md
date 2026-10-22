# Gordium coordination handoff (2026-10-22, ~00:45 EDT)

You are taking over as **coordinator** of Gordium's parallel work, running in a cloud session on the repo
`bz28/gordium`. The previous coordinator ran locally on Ben's Mac and is out of plan usage. Read, in order:
`CLAUDE.md` (repo root, on `main`), this file, then `docs/coordination/SHARED_CONTEXT.md` (the full running
log of decisions; newest at the bottom). This branch (`coordination`) is notes only: never open a PR for it,
never merge it.

## Hard rules (Ben's, unchanged)
- **Never merge a PR. Never push to `main`.** Push only to the PR branches named below. Ben merges.
- **Never a false pass.** Missing/unclear → needs review. Every-reading rule: complies only if every reading passes.
- **No AI API spend.** The drafting CLI must not be run with a live key; you have no key in the cloud anyway.
  Remaining drafting work that needs spend (§325-16C ~$0.09, §325-18B ~$0.03, lot size ~$0.10) waits for Ben.
- **Don't send the City/County emails.** City/County data used live, never stored, except what endpoints.yaml allows.
- **Fix in the owning PR** (base = the PR below it). No cleanup PRs. Exceptions: Windows fixes stay in #15;
  overlaps with #18's rewrites go into #18.
- **Review loop on every push** before calling anything ready: a cold reviewer (no context) + 2 independent
  sceptics per finding; a finding counts only if confirmed; every confirmed finding is fixed and pinned with a
  test that fails on revert; repeat until a round returns zero confirmed. `docs/coordination/review-loop.js` is
  the workflow script used so far (args: base, head, round, sinceLastRound + priorConfirmed when round ≥ 2, cwd,
  intent). If you have no Workflow tool, run the same roles with subagents.
- **Full CI before every push:** pytest + every `python -m …` step in `.github/workflows/ci.yml`
  (`docs/coordination/full_suite.py` does exactly that from a checkout root; GitHub CI can't start: billing).
  Clear `__pycache__` after any revert-check (stale .pyc hazard).
- PR descriptions follow `.github/pull_request_template.md`, written so an architect can follow them.
- Write for Ben in plain, short language. He reads summaries, not logs.

## What needs Rhino (stays with the LOCAL side; do not attempt in the cloud)
Rhino-only work waits in `docs/coordination/RHINO_QUEUE.md` for the local side (after Ben's weekly reset,
Sunday 4:00 AM). Prepare code + logic-layer tests for these so the local side only has to run Rhino.

## Lanes (heads as of this handoff)

| PR | Branch | Head | State | Next |
|---|---|---|---|---|
| #14 | start-project | 0122b15 (CI green) | stories structured refusal codes | carried up by stack work |
| #15 | rhino-ui | 86a3a16 | round 7 fixes in CI (ground cut per solid + 5-shape table; stories `stories_refused` codes; open_solid names objects f1b51a6) | review round 8 on #15 since 7201d49 |
| #15 batch | arch-fixes-2 | 8e3582f | NOT landed on rhino-ui. Round 6 found P0 corner false pass (findings/arch_round6.json) | Rhino job redoing corner fix at the root (law's lot-width definition from §325-3; street identity; total-heading safety net shared by measure + rhino_logic; corner_answered None→No keeps prefilled line), then Windows console fix + design_checker server process leak (one server per Rhino; stop on reload/close) |
| #17 | term-index | a7557f7 | carries #15 | carry after #15 clean |
| #18 | measurement-2 | ecd820b | round 24 P3s done; P2 (name open objects on every waiting row; delete unreachable 'flat' branches; assert without monkeypatch) waits for #15 f1b51a6 to reach term-index | do P2 after carry; review round 25 |
| #19 | start-box-lookup | 5937781 | round-2 fixes local in stack work (7efb1bd: map wording only in session key `_zone_said` with the lookup date; stored source plain; architect's pick stored as theirs; label refresh) — a #19 suite was hung/starved; re-run file by file | push, review round 3. Do NOT carry arch-fixes-2's corner code until its root fix is reviewed clean |
| #20 | answer-keys | c342d10 | clean (abuts_r1_district, rounds 1–3) | catch up with #18 when it moves |
| #21 | drafting-stage1 | 84f4920 | round 11 review pending; 0 false passes on six keys; spend $5.75 of $20 cap | review round 11; fix findings (no spend) |
| #22 | stress-tests | a460e4e | clean | merge measurement-2 when it moves; F15 last case on #15 |
| #23 | context-map | c783ee6 | round 2 findings (findings/pr23_round2.json): needs_refetch with no record → True; fingerprint EVERY ObjectAttributes property (reflection) + groups + user strings, copies (own id ≠ DRAWN_KEY) are the architect's in `_clear_context` too; in-Rhino claims pending | fix, review round 3 |
| (new) | r2-hand | 1b15c9f | hand R-2a/b/c, clean through round 7; merge of answer-keys under review (round 8) | after clean: open PR base `answer-keys`, title "Hand-written R-2a, R-2b and R-2c rulebooks (answer keys, selectable later)", body draft below |
| (new) | relookup | 706e13d | Rhino job's re-lookup clean start, based on #19 374b525 | after demo update |
| — | demo | dfe78d1 | cofounders' preview (pull fast-forwards). Second update waits for: #19 round-2 clean, #15 round 7 clean, corner root fix clean, Windows fix | build with the same merge order as before; AI zones OFF |

## Second demo update (Ben is waiting on this)
When the items above are clean: rebuild `demo` from rhino-ui (incl. arch-fixes-2 landed), term-index,
measurement-2, start-box-lookup, answer-keys, context-map, stress-tests — merged `--no-ff` in stack order, AI
zones off — as a commit whose parents include the previous `demo` (so `git pull` fast-forwards). Run full CI.
The local side must still run the in-Rhino smoke before Ben tells cofounders to pull.

## Ben's open UX decisions (approved, queued after the demo update; mostly Rhino job)
Re-lookup = clean start on Draw with a new address (Look up previews only; ask once only if the architect's
own work would be lost; one undo); live progress + Cancel; address autocomplete (public State/County suggest,
live only) and append ", Ithaca, NY" when no town given; after a failed lookup say the old lot is still shown;
multi-piece parcels: let the architect pick the piece(s), say each doubt once, never contradict the street;
offending part coloured by status (red/amber), drawing-style dimensions, depth-tested lines, Check button
(no auto-check by default), Osnap: envelope ground outline + yard lines as real locked curves; starting house on
Massing::Floor N / Massing::Roof sublayers; starting-house note + cautious envelope on tax-map lots; editable
neighbourhood (#23). Later milestone: Gordium reads real walls/slabs/roof models (option 2).

## How to report
- Each finished step: push, then a short PR comment saying what changed and the evidence.
- Keep `docs/coordination/STATUS.md` on this branch current (one line per lane: head, state, next).
- Rhino-needed steps go in `docs/coordination/RHINO_QUEUE.md` with the exact script to run.
