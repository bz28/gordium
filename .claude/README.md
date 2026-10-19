# Gordium slash commands

The commands in `commands/`, tailored to this repo (kept here, not in `commands/`, so this file doesn't become a `/README` command). If a personal command in `~/.claude/commands/` has the same name, use the project one.

| Command | When to use |
|---|---|
| `/plan` | Before building anything non-trivial: approaches, recommendation, evals. No code. |
| `/implement` | Build commit by commit, pausing after each for Ben. |
| `/autopilot` | Run a scoped PR stack end to end, still stopping before each commit. |
| `/review` | Loop: cold reviewer + 2 skeptics per finding, fix every confirmed finding with a pinned test, until a round comes back clean (cap 4). Runs `workflows/review-loop.js`. |
| `/debug` | Something is wrong: find the root cause, propose a fix. |
| `/explain-simple` | Plain-English summary for architects and shareholders. |

**Loop per PR:** `/plan` → (Ben approves) → `/implement` or `/autopilot` → `/review` → `/explain-simple` → Ben merges.

Every command follows `CLAUDE.md`: the six core principles, the git workflow, and "flag zoning interpretations for the architects, never guess".
