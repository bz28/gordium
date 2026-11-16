# Grouping the check's results so an architect can read them (2026-11-16)

**Purpose:** how the panel and the permit sheets group a law's results (egress first) so the one real failure is never buried under a hundred "needs review" rows, and why.\
**For:** engineers changing `design_checker/grouping.py`, `present.grouped`/`summary`, the Rhino panel's list or `packages/permit_sheets`; Ben; the architects.\
**Kept current by:** the engineer who changes how results are grouped or counted, in that PR.

## The problem

On a made-up two-story house (`test_data/interior_houses/2_two_story_small_window`) the egress headline reads
"Egress: 1 does not comply · 127 need review · 9 comply". 113 of the 127 need review only because Gordium can't read
that part yet (handrails, guards, ramps… aren't in the model; area wells, landings… aren't measured), and a window's
14 rules are 14 rows. The one real failure, Bedroom 3's window, is one row among 137. On the Orangetown house the
permit sheet G-001 says "310 need review" over 17 pages: a plan reviewer would bounce it.

## The design (one grouping, used by the panel and the sheets)

`design_checker/grouping.py` puts each item of a law in exactly one **line**, each line in one **tier**:

| Tier | What goes in it | One line per | Shown |
|---|---|---|---|
| 1. Does not comply | every failing rule | part ("Bedroom 3 › Window 5") | open, first |
| 2. Needs review | needs review the architect can act on: a judgment (a rule a person decides), a value the drawing can give (the frame isn't given; a list the description left out, such as no `stairs`), a check that already fails on what was measured or worked out ("may not comply: riser variation 1.5 in, needs ≤ 3/8 in"), the drawing's own problems; and anything not plainly Gordium's gap | part, or item that is no part's | open; "may not comply" lines first |
| 3. Check by hand: not read by Gordium yet | needs review **only** because Gordium can't read it: a part kind the interior description has no list for yet ("Not read from the model yet: handrails (10 rules), guards (open sides) (7 rules)…: check by hand"); details of a part that Gordium neither measures nor works out yet, when the rule reads nothing measured of that part (whether a stair is spiral, area well ladders); the code sections with no rules yet (#110's line) | cause | open, each line folded to its rules |
| 4. Complies | complies, and not applicable ("the description says the house has no X", from the absent-parts work) | part | folded |

The **headline** counts what an architect counts: rules that fail (each its own fix), lines to review (one per part),
rules that comply, parts (or a part's details) not read yet, and code sections not checked yet: "Egress: 1 does not
comply · 2 to review · 9 comply · 13 parts not read yet · 86 sections not checked yet". When nothing fails and nothing is to review but egress
still needs review (only Gordium's gaps), it says "needs review" first, so it never reads as a pass.

**Unchanged underneath** (presentation only): every item keeps its status; every item is in exactly one line and
reachable (selectable in the panel, a row in the CSV/XLSX); `present.state` and the view's `state` are not touched; a
law still waiting for rooms (#106: "Egress waiting: no rooms drawn yet", grey) is shown exactly as before. Zoning's
groups are as before (20-odd rules, one each).

**What decides tier 3** (the only fold of a needs review): an item's `open` (each_part.unsettled, from the measuring's
own stop words and the part kinds the description format has, never from the item's text). A needs-review row is
Gordium's gap only when its part kind is one the description has no list for, or every value missing is one the
measuring says "Gordium doesn't measure this yet" / "works this out but doesn't give it to the rules yet" with no
worked-out value, **and** the rule reads nothing measured or worked out of that part, **and** its check doesn't
already fail on what was measured or worked out. Anything else stays in tier 2. A fail is never in tier 3 or 4.

## Before / after: the Rhino panel (made-up house 2)

Before:
```
Zoning: 9 need review · 11 comply · 1 to answer · … · Egress: 1 does not comply · 127 need review · 9 comply
▾ Does not comply · 0 …                                   (zoning's groups)
▾ Egress (NY State Residential Code 2025) · 137
    ✕ Bedroom 3 › Window 5 · Escape opening minimum net clear area (R319.2.1)
    ? Front door · One egress door for each dwelling unit (R318.2)
    ? Front door · Egress door shall be side-hinged (R318.2)
    … 124 more "?" rows …
    ✓ … 9 rows
```
After:
```
Zoning: 9 need review · … · Egress: 1 does not comply · 2 to review · 9 comply · 13 parts not read yet · 86 sections not checked yet
▾ Does not comply · …                                     (zoning's, as before)
▾ Egress · Does not comply · 1
    ✕ Bedroom 3 › Window 5: 1 does not comply (net clear area 5.12 sq ft, needs ≥ 5.7 sq ft: R319.2.1)
▾ Needs review · …                                        (zoning's, as before)
▾ Egress · Needs review · 2
  ▸ ? Front door: 3 need review: a person decides: readily openable without key (R318.2), … · to give: dwelling units
  ▸ ? Main stair: 16 need review: a person decides: riser slope (R318.7.5.1) · worked out, not yet checked by the
        rules: handrail sides 2, riser variation 0 in … · not read yet: riser count, serves sleeping loft
▾ Egress · Check by hand: not read by Gordium yet · 3
  ▸ ? Not read from the model yet: handrails (10 rules), guards (open sides) (7 rules), sleeping lofts (5 rules), … : check by hand
  ▸ ? Not measured from the model yet: escape window details: fully openable, path height … (17 rules on 4 escape
        windows), stair details: serves sleeping loft … (14 rules on Main stair), …: check by hand
    ? Not checked yet by Gordium: 86 code sections: check by hand
▸ Complies · …                                            (zoning's, folded)
▸ Egress · Complies · 9
```
(▸ a folded line: opening it lists its rules, each selectable with its code words and citation as today. A line of
one item is that item's row.)

## Before / after: G-001 (Orangetown)

Before: 17 pages, one row per rule, every one NEEDS REVIEW; heading "310 need review (the check's own count)".

After: G-001 is the grouped table, one row per line, each row naming its rules' code sections and their line numbers
in `code_analysis.csv`; the full per-rule table stays in `code_analysis.csv` and `permit_sheets.xlsx` (unchanged
columns, plus "Shown on G-001 as"), so every rule is traceable:
```
Egress result: NEEDS REVIEW
Egress (NY State Residential Code 2025): 17 to review · 12 parts not read yet · 86 sections not checked yet (the check's own count)
#   Item                                   Rules                         Result        Code sections   Why / what to do
NEEDS REVIEW
1   Front entry door                       5 rules (CSV 1–5, 46)         NEEDS REVIEW  R318.2, BF103.2 a person decides: …; to give: the top of the threshold …
2   Stairs                                 30 rules (CSV 6, 47–75)       NEEDS REVIEW  R315.5.2.1 …    to give: the stairs aren't in the interior drawing (no `stairs` list)
3   Master bedroom › double-hung 1 of 2    4 rules (CSV 7, 17, 27, 37)   NEEDS REVIEW  R319.2.1–R319.2.3 to give: the opening's frame isn't given …
…
CHECK BY HAND: NOT READ BY GORDIUM YET
18  Not read from the model yet: handrails (10 rules)                         NEEDS REVIEW  R320.2 …      check by hand
…   (one row per cause: guards, sleeping lofts, …, ramps; then each part's details not measured yet)
29  Not checked yet by Gordium: 86 code sections                              NEEDS REVIEW  (banner lists every section)
```
The fails tier (when there is one) prints each failing rule on its own row with Required and Proposed, as today.
A-601 and LS-101 are unchanged apart from the shared headline.

## An architect's-eye critique (and what it changed)

- *"Show me what I have to fix, then what I have to decide, then what you couldn't do."* That is the tier order.
  Gordium's own gaps were the bulk of the list; they are now three lines, each saying "check by hand" in so many words.
- *"Don't hide a likely failure behind 'not measured'."* The tall-riser house's riser (9 in, max 8 1/4 in unless it
  serves a sleeping loft) needs review only because Gordium doesn't read "serves a sleeping loft" yet. Folded with
  the gaps it would vanish; instead a check that fails on what was measured is "may not comply" and leads tier 2.
- *"Count windows, not rows."* "17 to review" on Orangetown is ten windows without frames, the door, the stairs the
  drawing left out (and that same drawing problem's own line), and four marked windows not checked: things to act on. Rejected: merging the ten windows into
  one line (it would hide which windows), and counting rules (126 again).
- *"A permit reviewer reads the sheet, not the CSV."* The grouped sheet still names every code section each line
  covers and its CSV lines; failing rules keep their own rows with Required and Proposed. Rejected: printing the
  17-page per-rule table in the set (the reviewer bounces it); the CSV/XLSX carry it.
- *"What can't apply to a house is noise."* Ship's ladders, ramps and alternating tread devices are listed under
  "not read" on every house. Kept, last in the line (handrails and guards first), until the absent-parts work lets a
  description say the house has none (then they are "doesn't apply", folded with what complies).
- *"The headline is long."* Accepted for now: each count is a different action; the not-read count names its noun
  ("13 parts not read yet"). Zoning's own counts are unchanged.

## How we know it is right (pins, each failing on revert)

- No failure is ever folded out of the headline: every failing item is in tier 1 and counted; a fail with an `open`
  saying Gordium's gap is still tier 1.
- Folded items keep their statuses: the statuses of every item before and after grouping are identical.
- Every rule row is reachable: the union of the lines' items is every item, each exactly once; every CSV row maps to
  a G-001 line and back.
- The state is unchanged: `view["state"]` and each section's state equal `present.state` over the same items, on
  every golden house.
- The waiting state is unchanged: the no-rooms view's summary, groups and `waiting_only` are as before.
- Goldens re-recorded with a check that, item by item, no status changed (only grouping and wording).

## Review round 1 on this plan (cold reviewer; uncommitted)

Confirmed and fixed before building on it: (P0) a value the measuring works out but doesn't give the rules yet (a
stair's riser variation 1.5 in, its handrail sides 0) was folded as Gordium's gap, hiding three likely failures on the
made-up houses and their count from the headline: such a value now counts as measured, and a check that fails on it is
"may not comply", tier 2 (pinned on the tall-riser and basement-window-well houses). (P1) a kind the description can
give but left out (Orangetown has no `stairs` list) was folded as Gordium's: it is now the drawing's to give, tier 2.
(P2) fail lines name each rule's code section; a row's own reason ("no egress doors") is no longer called "to give";
the not-read count names its noun.
