# Gordium

A co-pilot inside Rhino for architects. It knows the zoning rules a building must follow and checks each design edit against them: **pass**, **fail**, or **needs review**.

**Try it in Rhino:** [Gordium in Rhino: from scratch](apps/rhino_plugin/QUICKSTART.md), install once, then your first project step by step.

First city: **City of Ithaca, NY** (residential districts first).

## How the repository is organized

| Folder | What's in it |
|---|---|
| `regulations/` | **Data.** The city's original documents and the rulebooks made from them. No code. |
| `packages/` | **Logic.** One package per job (reading documents, measuring models, checking designs…). Created as each is written. |
| `apps/` | **Products** people use (command line, rule review app; later the Rhino plugin). Created as each is written. |
| `test_data/` | Architects' hand-checked rules (answer keys) and real test sites with expected results. |
| `docs/` | Project notes: decisions and open questions. |

## The ground rules

1. Documents are turned into rules once per code version, then frozen.
2. AI drafts rules; code checks every draft (exact quotes, valid formulas, worked examples). Architect approval is deferred for now (decided 2026-10-19): rules stay marked draft, and the approval fields wait unused until it is switched on.
3. The checker never uses AI. Same design + same rulebook = same answer.
4. Never a false pass. Anything uncertain is "needs review".
5. Every rule traces back to its exact source.
6. Measurement code is written and tested by engineers.

Full design doc: https://claude.ai/code/artifact/d980dd22-6b2e-4090-bcc4-d02c871b8a7b

## Running it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                      # all tests
.venv/bin/python -m rule_format       # check every rule file
```
