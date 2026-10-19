# Gordium slash commands

Tailored to this repo. They override the generic versions in `~/.claude/commands/`.

| Command | When to use |
|---|---|
| `/plan` | Before building anything non-trivial: approaches, recommendation, evals. No code. |
| `/implement` | Build commit by commit, pausing after each for Ben. |
| `/autopilot` | Run a scoped PR stack end to end, still stopping before each commit. |
| `/review` | Two-pass review + Gordium checks + mutation test + independent reviewer. |
| `/debug` | Something is wrong: find the root cause, propose a fix. |
| `/explain-simple` | Plain-English summary for architects and shareholders. |

**Loop per PR:** `/plan` → (Ben approves) → `/implement` or `/autopilot` → `/review` → `/explain-simple` → Ben merges.

Every command follows `CLAUDE.md`: the six core principles, the git workflow, and "flag zoning interpretations for the architects, never guess".
