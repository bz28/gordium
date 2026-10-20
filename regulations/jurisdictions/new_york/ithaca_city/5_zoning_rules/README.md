# 5_zoning_rules

**The rulebook.** One file per district, named exactly as the city writes it (`R-1b.yaml`).

Each rule has:
- **limit** — written as a formula in a small, fixed formula language (so code can check it, no AI)
- **applies when** — e.g. only to one-family detached houses
- **exceptions**
- **source** — file, page, position, exact quote
- **plain-English text** and **worked examples**
- **drafted by**, **status**, **approved by**, **approved on**

Rules stay marked **draft**: architect approval is deferred for now (decided 2026-10-19), so the checker uses draft rules that have passed every code check (`python -m rule_format`). The approval fields are kept, unused, so approval can be switched on later without a rebuild.
