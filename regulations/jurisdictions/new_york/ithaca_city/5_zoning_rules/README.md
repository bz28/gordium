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

Rules stay marked **draft**: architect approval is deferred for now (decided 2026-10-19), so the checker uses draft rules that have passed every code check (`python -m rule_format`). The approval fields are kept, unused, so approval can be switched on later without a rebuild.

**Two kinds of draft live here:**
- `R-1b.yaml`, `R-1a.yaml`, `R-2a.yaml`, `R-2b.yaml`, `R-2c.yaml`, `R-3a.yaml`, `R-3aa.yaml`, `R-3b.yaml`,
  `RU.yaml`: every residential district, drafted by Claude by hand from the
  City's documents only (never from anything the script drafted). They are the answer keys the drafting script is
  graded on, and are never shown to the script. R-1a is R-1b's closest sibling (the next chart column: it catches a
  column mix-up); R-2a and R-2b are the two-family districts (semi-detached and two-family houses, R-2b's unequal
  side yards); R-2c has stacked chart cells (one figure per use) and lot sizes that grow with the occupants (chart
  notes 4 to 6); R-3a is a multi-family district (it catches single-family assumptions); R-3aa is R-3a's look-alike
  (every lot 50 ft wide, no dormitories, at most 3 and at least 2 stories, a footprint cap); R-3b has the smallest
  lots and its own lot-size note (note 8); RU has large lots, a 30 ft rear-yard floor (note 17), a green-space rule
  and limits on primary buildings (chart p.2 notes 3 and 5). Each chart number is checked against the chart
  reader's cells for its own column (`packages/document_extraction/tests/test_r1b_matches_chart.py`). A hand
  rulebook is the one the checker uses for its zone (`rulebook.rulebook_for`).
- `drafted/`: every residential district drafted by the drafting script (`packages/rule_drafting`):
  `drafted/<district>.yaml` and `drafted/general.yaml` (rules for every district). Chart numbers in these
  come only from the chart reader's cells. The script's own records are in `drafted/records/`: what it
  did per unit (`drafting_log.yaml`), what goes to a person, the measures it asked for
  (`proposed_measures.yaml`), and every AI call (`runs/`).
