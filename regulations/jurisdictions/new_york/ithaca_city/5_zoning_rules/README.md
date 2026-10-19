# 5_zoning_rules

**The rulebook.** One file per district, named exactly as the city writes it (`R-1b.yaml`).

Each rule has:
- **limit** — written as a formula in a small, fixed formula language (so code can check it, no AI)
- **applies when** — e.g. only to one-family detached houses
- **exceptions**
- **source** — file, page, position, exact quote
- **plain-English text** and **worked examples**
- **drafted by**, **status**, **approved by**, **approved on**

Nothing is used by the checker until an architect approves it.
