# Drawing-style dimensions (PR #29) at 6d2e01a: checked in Rhino 8 (Mac), 2026-10-26

**Purpose:** the numbers-only drafting style (the number centred on its own line, outside the house; ✕ / ? for fail
/ review; grey, amber, red; "min" tags only on failing and in-review yards), and an architect's look at Top
(default zoom and Zoom Extents) and Front.\
**For:** the coordinator, the #29 job, reviewers.\
**Kept current by:** never changed (a dated record).

| Run | Result |
|---|---|
| `dimensions_in_rhino.py` as written (`dimensions/`) | **21 of 22**: "1 every number shown sits clear of the status box, the house and the other numbers" fails |
| `mvp_checks_in_rhino.py`, every claim recorded (`mvp_checks/`) | **13 of 13** |

## The failing yard's number is missing at the default zoom

In the real Top viewport (656 × 668 px, the docked panel taking the rest), at the default zoom, **the failing
southwest side yard's number isn't drawn at all**: its placement is "none" (`dimensions_results.json`). The one
number that matters most is the one missing. With more room it is drawn: at Zoom Extents ("✕ 7'-0 5/8"" in red,
just past its line's outer end) and in the MVP check's 1000 × 640 capture.

## To an architect's eye

**Top, default zoom** (`dimensions/1_top_labels_on.png`):
- The southwest side yard (fails): no number.
- The rear yard: "? 27'-6 7/8"", vertical, runs up **through the status box** and over the edge label "69'-6 1/8"".
- The front yard: "? 26'-11 3/4"", vertical, bottom left, **printed through the notice bar**.
- The northeast side yard (complies): "32'-4 1/4"", grey, centred on its own line. Clean, though it sits against the
  edge label "92'-1 3/8"", which is cut off at the view's edge.
- The "min 25'-5 1/2"" tag: faint but readable.

**Top, Zoom Extents** (`dimensions/1b_top_zoom_extents.png`): much cleaner. "✕ 7'-0 5/8"" red past its line's end;
"? 27'-6 7/8"" and "32'-4 1/4"" each on its own line; "min" tags only on the failing and in-review yards. The front
yard's "? 26'-11 3/4"" is on its line, but its end runs into the notice bar.

**Front** (`dimensions/2_front.png`): "35'-0"" centred on its vertical line, beside the house and outside it. Clean.
No height-limit label is seen (expected past the limit line's end); here the height is at the limit, so the faint
limit line lies along the roof line.

**Labels off** (`mvp_checks/1_labels_off_failing_shortfall_only.png`, 1000 × 640): only "✕ 7'-0 5/8"" in red past
its line's end, and the faint "min" tags. Clean.
