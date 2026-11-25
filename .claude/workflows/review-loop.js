export const meta = {
  name: 'review-loop',
  description: 'One round of PR review — cold reviewer over the branch diff, then N independent skeptics per finding; returns confirmed + refuted',
  phases: [
    { title: 'Review', detail: 'cold reviewer reads the diff + every touched file end-to-end' },
    { title: 'Verify', detail: 'N independent skeptics per finding, strict — default refute' },
  ],
}

// args = {
//   base: 'origin/main',            // what the branch is compared against (fetch first!)
//   head: 'HEAD',                   // the branch tip under review
//   uncommitted: false,             // true: review the working tree (committed + uncommitted changes),
//                                   //   so a large change is reviewed before it is committed
//   round: 1,                       // 1-based; round >= 2 re-checks priorConfirmed
//   priorConfirmed: [...],          // findings confirmed in the previous round (now supposedly fixed)
//   sinceLastRound: '<sha>',        // round >= 2: the commit the previous round reviewed, so the reviewer
//                                   //   can `git diff <sha>..head` to see exactly what the fixes changed
//   skeptics: 2,                    // 2 for anything that could cause a false pass; 1 for a UI- or wording-only diff
//   intent: 'what the PR is trying to do (one paragraph, from the session)',
//   verifyOnly: [...],              // skip the reviewer; run the skeptics on these findings (the
//                                   //   in-session review's own findings, so they earn "confirmed" the same way)
//   cwd: '<abs path>',              // the checkout/worktree where `head` is checked out (default: the session's
//                                   //   working directory). Agents read files from disk, so the tree must be at head.
// }
// Fail loudly on bad input: a review that silently ran with defaults could look clean when it wasn't.
let cfg = args
if (typeof cfg === 'string') {
  try { cfg = JSON.parse(cfg) } catch (e) { throw new Error(`review-loop: args is not valid JSON: ${e.message}`) }
}
cfg = cfg || {}

const BASE = cfg.base || 'origin/main'
const HEAD = cfg.head || 'HEAD'
const UNCOMMITTED = cfg.uncommitted === true
if (UNCOMMITTED && cfg.head && cfg.head !== 'HEAD') {
  throw new Error('review-loop: uncommitted reviews the checked-out working tree; check out the branch (or pass cwd) instead of head')
}
// The diff commands every agent runs. Both modes start from where the branch split off the base (the
// merge-base), so newer commits on the base never look like this branch reverted them. With uncommitted
// work, that split point is compared with the working tree.
const WHOLE = UNCOMMITTED ? `--merge-base ${BASE}` : `${BASE}...${HEAD}`
const ROUND = cfg.round || 1
const PRIOR = cfg.priorConfirmed || []
const SINCE = cfg.sinceLastRound || null
const SKEPTICS = cfg.skeptics || 2
const INTENT = cfg.intent || '(not provided)'
const VERIFY_ONLY = cfg.verifyOnly || null
const CWD = cfg.cwd || null
// At most 3 agents run at once (Ben's limit: a 16 GB Mac that also runs Rhino and the tests).
const MAX_AGENTS = 3
if (ROUND >= 2 && !VERIFY_ONLY && (!SINCE || !PRIOR.length)) {
  throw new Error('review-loop: round >= 2 needs sinceLastRound and priorConfirmed, so the prior fixes are re-checked')
}
const WHERE = CWD
  ? `WORKING DIRECTORY: run every command and read every file inside \`${CWD}\` (\`cd ${CWD}\` first — the branch under review is checked out THERE, not in the session's default directory). NEVER change what is checked out there: no \`git checkout\`, \`git switch\`, \`git reset\`, \`git stash\`, \`git commit\` or file edits (the author is working in it; a reviewer's checkout once detached a branch, so the author's next commits never reached GitHub). To read another commit use \`git show <sha>:<path>\` or \`git diff\`; to run code at another commit, \`git worktree add\` a scratch worktree in your scratchpad and remove it after.\n\n`
  : ''

const FINDING_ITEM = {
  type: 'object',
  required: ['file', 'severity', 'category', 'title', 'detail', 'evidence', 'pin'],
  properties: {
    file: { type: 'string', description: 'repo-relative path' },
    line: { type: 'string', description: 'line number or range' },
    severity: { type: 'string', enum: ['P0', 'P1', 'P2', 'P3'] },
    category: { type: 'string', description: 'false-pass, traceability, approval, code-accuracy, reproducibility, correctness, edge-case, security, regression-in-caller, DRY, consistency, docs' },
    title: { type: 'string' },
    detail: { type: 'string', description: 'what is wrong and what a user would see' },
    evidence: { type: 'string', description: 'the exact code / call sites that prove it — quote them' },
    suggested_fix: { type: 'string', description: 'the reliable fix — no bandages, no hardcoding' },
    pin: { type: 'string', description: 'the test that must FAIL if this fix is reverted (file + what it asserts). For rule data: the validator check or worked example that must fail.' },
    prior_ref: { type: 'string', description: 'round >= 2 only: the prior finding title this relates to (unfixed / shallow-fixed / regression from its fix)' },
  },
}

const FINDINGS_SCHEMA = {
  type: 'object',
  required: ['findings', 'prior_status'],
  properties: {
    findings: { type: 'array', items: FINDING_ITEM },
    prior_status: {
      type: 'array',
      description: 'round >= 2: one entry per prior confirmed finding',
      items: {
        type: 'object',
        required: ['title', 'status', 'reasoning'],
        properties: {
          title: { type: 'string' },
          status: { type: 'string', enum: ['fixed', 'shallow', 'unfixed'] },
          reasoning: { type: 'string' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['refuted', 'reasoning'],
  properties: {
    refuted: { type: 'boolean', description: 'true if the finding does NOT hold up under scrutiny, or you could not independently confirm it' },
    reasoning: { type: 'string', description: 'what you read and why it does / does not hold' },
  },
}

const CHECKLIST = `Read CLAUDE.md first: Gordium's six core principles are the review's top priority.

Check for:
- FALSE PASS: any path where missing, unusable or unclear data could give "pass" instead of "needs review"
- TRACEABILITY: every rule/definition cites file, page and an exact quote; fingerprints and extracted text match the source PDF version
- NO AI IN THE CHECKER: nothing at check time calls a model or depends on non-deterministic output
- APPROVAL INTEGRITY: nothing marked approved without a listed reviewer; AI never approves
- CODE ACCURACY (zoning and egress): numbers and quotes match the source documents (open the PDF page / extracted text); interpretations are flagged, not guessed
- REPRODUCIBILITY: generated files (2_extracted_text, 6_coverage_report, generated rules) come out identical when re-run
- Correctness and logic errors; edge cases and boundaries (empty, zero, NaN, irregular lots, odd PDF layouts)
- Regressions in callers/peers NOT in the diff — a focused diff review misses these
- Security (untrusted input in formulas/YAML/PDFs), silent failure (swallowed exceptions, no-op writes)
- Consistency with existing code patterns; DRY violations and unnecessary complexity
- Docs that claim something the code or tests don't actually do

Tier by blast radius: P0 breaks a core principle (false pass, untraceable rule, AI approval, AI in checker) · P1 correctness bugs / crashes · P2 things architects or Ben would notice · P3 quality / naming / DRY.

Avoid by name:
- Style nits when correctness issues are unaddressed
- "Consider extracting X" when X is used once
- "What about edge case Y?" without checking whether Y can actually happen given upstream guarantees
- Re-stating what the code does without naming a defect
- Suggesting tests for code already covered by an existing test`

function reviewPrompt() {
  const priorBlock = ROUND >= 2 ? `
THIS IS ROUND ${ROUND}. The previous round confirmed these findings and the author says they are fixed:
${JSON.stringify(PRIOR, null, 2)}

Two extra obligations this round:
1. For EACH prior finding, verify it is actually fixed — not shallowly. Read the fix. A guard copied from a sibling's *shape* without its *substance*, an exception check on the wrong type, a fix that covers the reported instance but not the pattern — those are "shallow". Report every prior finding in prior_status.
2. Fixes introduce bugs. Run \`git diff ${UNCOMMITTED ? SINCE : `${SINCE}..${HEAD}`}\` to see exactly what changed since the last round and read THAT code hardest. Two fixes that are each fine can combine into a new defect.
` : `
THIS IS ROUND 1. prior_status should be an empty array.
`
  return `${WHERE}You are a world-class engineer doing a cold, independent review of a branch. You have no context on the conversation that produced it — that is the point. Ground every claim in code you read.

WHAT THE BRANCH IS TRYING TO DO (author's intent, treat as a claim to check, not a fact):
${INTENT}

HOW TO READ IT:
- \`git diff ${WHOLE}\` is the change. \`git diff --stat ${WHOLE}\` lists touched files.${UNCOMMITTED ? ' It includes UNCOMMITTED work: read files from disk, and run `git status` for new untracked files (they are part of the change).' : ''}
- After the diff, read EACH touched file end-to-end (for files > ~500 lines: the touched regions plus their direct callers/peers). Then grep for every caller of anything whose signature, return shape, or behavior changed, and check those callers still work.
- Do not guess from names. Open the file.
- Stay inside this branch: report only defects in code this branch (\`${WHOLE}\`) adds or changes, or that its changes break. A problem in code it doesn't touch belongs to the branch that added it: mention it as pre-existing, don't report it as a finding.
${priorBlock}
${CHECKLIST}

Two-pass rule: after your first sweep, re-verify every finding by re-reading the code and tracing call sites. Discard anything you cannot confirm. Return ONLY survivors. For each: exact file path + line, the code that proves it (quoted), the reliable fix, and the \`pin\` — the test that must fail if the fix is reverted. Your output is data for an adversarial verification stage, not prose — be precise and concrete. Surface everything; do not narrow quietly.`
}

function verifyPrompt(f, i) {
  return `${WHERE}You are an independent skeptic (reviewer #${i + 1}). Your job is to REFUTE the finding below by reading the actual code — not to agree with it.

BRANCH: compare \`${WHOLE}\` (\`git diff ${WHOLE} -- ${f.file}\` shows what changed in the cited file${UNCOMMITTED ? '; the change may be uncommitted or a new untracked file, so read it from disk' : ''}).

FINDING
  file: ${f.file}${f.line ? ':' + f.line : ''}
  severity: ${f.severity}
  category: ${f.category}
  title: ${f.title}
  detail: ${f.detail}
  evidence claimed: ${f.evidence || '(none given)'}

Open the cited file and the surrounding code, and the callers if the claim is about them. Try to prove the finding WRONG: the "bug" is prevented by an upstream guarantee (find it and cite it), the cited line doesn't say what the reviewer claims, the code path is unreachable, the behavior is a deliberate pattern used consistently elsewhere, the "edge case" cannot occur given the data model, or the claim is about code that is unchanged and identical on ${BASE} (a pre-existing issue is still worth knowing — but say so explicitly in reasoning).

Set refuted=true if the finding does not hold up OR you cannot independently confirm it from the code. Only set refuted=false when you have read the code and the finding is unambiguously real. Default to refuted=true when uncertain. In reasoning, name the file:line you read that decided it.`
}

let findings, priorStatus
if (VERIFY_ONLY) {
  log(`Round ${ROUND} (verify-only): ${VERIFY_ONLY.length} in-session finding(s) → ${SKEPTICS} skeptics each, strict.`)
  findings = VERIFY_ONLY
  priorStatus = []
} else {
  log(`Round ${ROUND}: reviewing ${WHOLE}${UNCOMMITTED ? ' (including uncommitted work)' : ''}; ${SKEPTICS} skeptics/finding, strict.${ROUND >= 2 ? ` Re-checking ${PRIOR.length} prior finding(s).` : ''}`)
  phase('Review')
  const review = await agent(reviewPrompt(), { label: `review:round${ROUND}`, phase: 'Review', schema: FINDINGS_SCHEMA })
  if (!review) throw new Error('review-loop: the reviewer returned no result, so this round did not run')
  findings = review.findings || []
  // Every prior finding must get a status; one the reviewer skipped is treated as unfixed, not as fixed.
  const reported = new Set((review.prior_status || []).map(p => p.title))
  priorStatus = [...(review.prior_status || []),
    ...PRIOR.filter(p => !reported.has(p.title))
            .map(p => ({ title: p.title, status: 'unfixed', reasoning: 'the reviewer gave no status for this prior finding' }))]
  log(`Reviewer returned ${findings.length} finding(s).`)
}

if (!findings.length) {
  return { round: ROUND, mode: VERIFY_ONLY ? 'verify-only' : 'review', confirmed: [], refuted: [], priorStatus, stats: { found: 0, confirmed: 0, refuted: 0 } }
}

phase('Verify')
// One task per (finding, skeptic), run MAX_AGENTS at a time.
const tasks = findings.flatMap(f => Array.from({ length: SKEPTICS }, (_, i) => () =>
  agent(verifyPrompt(f, i), { label: `verify:${f.file.split('/').pop()}`, phase: 'Verify', schema: VERDICT_SCHEMA })))
const verdicts = []
for (let k = 0; k < tasks.length; k += MAX_AGENTS) {
  verdicts.push(...await parallel(tasks.slice(k, k + MAX_AGENTS)))
}
const judged = findings.map((f, n) => {
  const answered = verdicts.slice(n * SKEPTICS, (n + 1) * SKEPTICS).filter(Boolean)
  // Strict: survives only if EVERY skeptic answered and NONE refuted it.
  const survives = answered.length === SKEPTICS && answered.every(v => v.refuted === false)
  return { finding: f, survives, votes: answered.map(v => v.reasoning), unanswered: SKEPTICS - answered.length }
})

const confirmed = judged.filter(j => j && j.survives).map(j => ({ ...j.finding, skeptics: j.votes }))
const refuted = judged.filter(j => j && !j.survives).map(j => ({
  ...j.finding,
  skeptics: j.votes,
  reason: j.unanswered ? `${j.unanswered} skeptic(s) did not answer — dropped (strict)` : 'refuted by at least one skeptic',
}))
log(`Round ${ROUND}: ${confirmed.length} confirmed, ${refuted.length} refuted.`)

return {
  round: ROUND,
  mode: VERIFY_ONLY ? 'verify-only' : 'review',
  uncommitted: UNCOMMITTED,
  confirmed,
  refuted,
  priorStatus,
  stats: { found: findings.length, confirmed: confirmed.length, refuted: refuted.length },
}
