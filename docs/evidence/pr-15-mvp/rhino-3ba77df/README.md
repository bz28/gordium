# #15 rhino-ui at 3ba77df: the corner step and pass 2, in Rhino 8 (Mac), 2026-10-26 (RHINO_QUEUE 14)

**Purpose:** the corner step after "open" (one click on an Ithaca Rd piece; the side street asked once about its far
corner), claim 12, and the full pass 2.\
**For:** the coordinator, the #15 job, reviewers.\
**Kept current by:** never changed (a dated record).

`pass2_in_rhino.py` as written: **26 of 26** (per-step results here; `corner.json` for the corner step).

## The corner step

- One click on one Ithaca Rd piece keeps all 8: "Ithaca Rd: 8 lot-line pieces, 75'-10" of frontage".
- The side street is asked about once, at its far corner: "Past there the lot line turns 89° over short pieces, a
  corner or a bend (2 more lot-line pieces, 69'-9"). Is that on Street 2 too? (Enter keeps it, to be safe)". The
  answer No keeps "Street 2: 2 lot-line pieces, 91'-10 3/8" of frontage". Kept: 10 lines (Ithaca Rd's 8, named;
  Street 2's 2).
- Claim 12: answering No to Corner lot? drops both streets' lines.
- **The rear is never highlighted** (`corner_top_street_highlight.png`, a crop of the Top view in `corner.jpg`): the
  thick blue street highlight runs along the bottom (Ithaca Rd) and up the right side (Street 2) to its corner, and
  stops there. The rear and the left side show only the selected lot outline's thin yellow and green.

One thing to weigh: the question's default, Enter, keeps the far pieces as Street 2 "to be safe". An architect who
presses Enter by habit makes the rear's 2 pieces street too. That's the cautious reading (more front yards), but it
changes which yards are front.
