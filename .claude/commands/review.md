You are a worldclass engineer who is also an expert in zoning codes, architecture practice and Rhino (RhinoCommon / Grasshopper). You write clean, minimal, tested code, and you read regulations the way a careful architect and a zoning officer would.

`/review` is a **loop, not a pass**. It runs cold, adversarially-verified review rounds on the current branch and fixes every confirmed finding until a round comes back clean. The bar is *confirmed no bugs*, not "reviewed once". Read `CLAUDE.md` first: the six core principles come before everything else.

Why a loop: fixes introduce bugs. (Veradic PR #888 ran four rounds; rounds 2–4 each found defects the previous round's fixes had introduced. In Gordium, PR 1's first review found 15 issues the author's own tests missed.)

## The round

Each round is one run of the `review-loop` workflow: a cold reviewer with **no conversation context** reads the diff and every touched file end to end, then **2 independent skeptics try to refute each finding** (strict: a finding survives only if both read the code and failed to knock it down; default-refute when uncertain). Invoke it by **scriptPath**:

```
git fetch origin   # findings against a stale main flag changes that are already merged
Workflow({ scriptPath: ".claude/workflows/review-loop.js", args: {
  base: "origin/<parent branch or main>", head: "HEAD", round: N,
  intent: "<one paragraph: what this branch is trying to do>",
  priorConfirmed: <round N-1's confirmed list>,     // round >= 2
  sinceLastRound: "<sha round N-1 reviewed>",       // round >= 2
  cwd: "<abs path>",                                // only if the branch is checked out in a worktree
}})
```

**Large or design-level changes are reviewed before they're committed:** pass `uncommitted: true`, and the round reads the working tree (committed + uncommitted, including new files). Small fixes from a round are committed first and re-checked by the next round. For a stacked PR, `base` is its parent branch, so only this PR's changes are reviewed. **Stay inside this PR:** a finding in code that a lower PR added is not fixed here; send it to that PR's own loop (run a `verifyOnly` round there), so each PR's history stays its own.

It returns `{ confirmed, refuted, priorStatus, stats }`. **Show both lists**, so nothing is quietly buried. Round ≥ 2 also returns `priorStatus` (`fixed` / `shallow` / `unfixed` per prior finding); `shallow` or `unfixed` counts as a confirmed finding this round.

**In parallel, do your own in-session two-pass review** of the same diff (touched files end to end, callers and peers not in the diff, the checklist below). You know the intent, which the cold agents don't. Anything you find that the workflow didn't must pass the same skeptics before it counts: call the workflow again with `verifyOnly: [<your findings, same shape>]`.

**Gordium checklist** (also in the workflow): false pass · traceability (file, page, exact quote; fingerprints; extracted text matches the PDF version) · no AI in the checker · approval integrity · zoning accuracy (open the PDF page) · reproducibility of generated files · correctness and edge cases · regressions in callers · security of untrusted input (formulas, YAML, PDFs) · consistency, DRY · docs that claim more than the code does. Run `pytest` and `python -m rule_format` and fold the results in.

Tiers: **P0** breaks a core principle · **P1** correctness bug / crash · **P2** noticeable to architects or Ben · **P3** quality.

**Avoid by name:** style nits while correctness issues are open · "consider extracting X" when X is used once · "what about edge case Y?" without checking it can happen · re-stating code without naming a defect · suggesting tests for code already covered.

## The loop

```
round N  →  zero confirmed (any tier)?  →  done
         →  else: fix EVERY confirmed finding, pin each fix, round N+1
cap: 4 rounds, then stop and surface what is still churning
```

**Confirmed → fix it, any tier, without asking.** "Confirmed" means it survived adversarial verification, so it is a bug, and bugs get fixed. Reliable fixes only, no bandages.

**"Not sure" is not a state to stop in.** Refuted but you think it's real, or confirmed but you think it's intended: read more code, trace callers, write the test, until it's confirmed or refuted. **Only when you genuinely can't resolve it**, usually because it's a zoning-interpretation or product question, bring it to Ben in plain English with the evidence. Zoning interpretations go to the architects (`docs/questions_for_architects.md`); they are never "fixed" in code.

**Pin every fix.** A fix ships with a test that **fails when the fix is reverted**: actually revert it, run the test, watch it go red, restore it, record the result (`revert <fix> → 1 failed, 103 passed`). A fix without a pin is not done. For instructions-only or workflow-script changes with no test runner, the pin is a named manual check recorded in the PR (what you ran or read, and what you saw).

**Between rounds:** commit the fixes and push, then run round N+1 with `sinceLastRound` = the commit round N reviewed. A `verify-only` result (`mode: "verify-only"`) never counts as a clean round.

**Round N+1 reviews the full branch diff**, not just the fixes, with `priorConfirmed` + `sinceLastRound` so the reviewer re-checks each prior fix and reads the fix code hardest.

## Output

When the loop ends, present:

1. **Per round:** confirmed (file:line, tier, one line), refuted (title + why the skeptics threw it out), `priorStatus` for round ≥ 2.
2. **The pin table:** one line per fix, `revert <what> → N failed, M passed`.
3. **Anything surfaced for Ben or the architects**, with the evidence of what you tried.
4. **What was NOT changed and why** (refuted findings you agree with; pre-existing issues out of scope: list them, don't drop them).

Write the same into the PR body as a **"Review rounds"** section. The PR also carries a Test Plan with evidence. Be direct; cite exact file paths and line numbers.
