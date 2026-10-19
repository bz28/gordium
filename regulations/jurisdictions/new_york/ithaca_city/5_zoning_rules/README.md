# 5_zoning_rules

**The rulebook.** One file per district, named exactly as the city writes it (`R-1b.yaml`).

Each rule has:
- **title** — a short label (no retelling of the law)
- **check** — the limit as a formula in a small, fixed formula language (so code can check it, no AI)
- **applies when** — e.g. only to one-family detached houses
- **review when** — cases code mustn't decide, with the reason
- **sources** — file, page, lines, exact quote: the city's own words; or one cell of the zoning chart (page, section, row, district column)
- **worked examples** — designs that must pass and fail
- **open questions** and, once architects answer, **answers**
- **drafted by**, **status**, **approved by**, **approved on**

Nothing is used by the checker until an architect approves it.

**Two kinds of draft live here:**
- `R-1b.yaml`: R-1b drafted by Claude by hand. It is the answer key the drafting script is graded on, and is
  never shown to the script.
- `drafted/`: every residential district drafted by the drafting script (`packages/rule_drafting`):
  `drafted/<district>.yaml` and `drafted/general.yaml` (rules for every district). Chart numbers in these
  come only from the chart reader's cells. The script's own records are in `drafted/records/`: what it
  did per unit (`drafting_log.yaml`), what goes to a person, the measures it asked for
  (`proposed_measures.yaml`), and every AI call (`runs/`).
