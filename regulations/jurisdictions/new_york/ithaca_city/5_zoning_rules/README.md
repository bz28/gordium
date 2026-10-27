# 5_zoning_rules

**The rulebook.** One file per district, named exactly as the city writes it (`R-1b.yaml`).

Each rule has:
- **title** — a short label (no retelling of the law)
- **check** — the limit as a formula in a small, fixed formula language (so code can check it, no AI)
- **applies when** — e.g. only to one-family detached houses
- **review when** — cases code mustn't decide, with the reason
- **sources** — file, page, lines, exact quote: the city's own words
- **worked examples** — designs that must pass and fail
- **open questions** and, once architects answer, **answers**
- **drafted by**, **status**, **approved by**, **approved on**

Rules stay marked **draft**: architect approval is deferred for now (decided 2026-10-19), so the checker uses draft rules that have passed every code check (`python -m rule_format`). The approval fields are kept, unused, so approval can be switched on later without a rebuild.
